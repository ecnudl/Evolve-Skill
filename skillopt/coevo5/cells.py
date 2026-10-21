"""One cell (registration §5.4): an arm's Skill solves one task once, through the frozen backends (inference, native
scoring), the call wrapper and the ordered decision table (``outcomes``).

Remedies never replace a delivered answer: the same SpreadsheetBench program is re-executed (its stored reply is
replayed through the frozen solver: no model call), the same workbooks are rescored in a fresh scoring directory, and
an ALFWorld episode that failed before any model call is restarted. Before the official scorer runs, ``preflight``
raises the stops already visible and keeps a SpreadsheetBench answer that its generation or workbooks already decide
away from the native scorer. A cell is claimed exclusively before it runs and its record is written once; predictions
and scores are stored once by content (``artifacts/``) and referenced by hash. A stop of the run -- rows 1-3 of the
table, a broken reservation assumption or a failure of the token ledger (§13.2) -- is recorded and raised as ``Pause``;
a unit then dispatches no further cell (``run_parallel``, which halts on any error).
"""
from __future__ import annotations

import fcntl
import os
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from .calls import _request_hash
from .outcomes import (
    REEXECUTE,
    RESCORE,
    RESTART,
    AssumptionBroken,
    BudgetStop,
    CleanupUnconfirmed,
    ConfigurationError,
    LedgerFailure,
    classify,
    preflight,
)
from .protocol import MAX_EPISODE_RESTARTS, MAX_REEXECUTIONS, MAX_RESCORES, VERSION

LIMITS = {REEXECUTE: MAX_REEXECUTIONS, RESCORE: MAX_RESCORES, RESTART: MAX_EPISODE_RESTARTS}
STOP_KINDS = {ConfigurationError: "configuration", BudgetStop: "budget", CleanupUnconfirmed: "cleanup",
              AssumptionBroken: "assumption", LedgerFailure: "ledger"}


class Pause(Exception):
    """The run pauses (§13.4); nothing continues automatically."""

    def __init__(self, kind, reason, cell):
        super().__init__("%s: %s (cell %s)" % (kind, reason, cell))
        self.kind, self.reason, self.cell = kind, reason, cell


@contextmanager
def exclusive(path, *, wait=False):
    """Ownership of a unit (or a shared qualification) across processes, held until the block ends: without ``wait``
    a second owner fails at once; with it, it waits its turn. A process that dies releases it."""
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ValueError("Another process owns " + str(path)) from None
        yield
    finally:
        os.close(descriptor)


class Context:
    """What the cells of one unit attempt share. ``store``: the attempt's directory; ``endpoint``: the attempt's own
    (``calls.Endpoint``, built when the attempt begins); ``runtime``: the frozen backends' runtime per benchmark;
    ``native`` and ``episodes``: the SpreadsheetBench execution and ALFWorld episode slots."""

    def __init__(self, *, store, endpoint, runtime, native, episodes):
        self.store, self.endpoint, self.runtime = safe_path(store), endpoint, runtime
        self.native, self.episodes = native, episodes


def cell_id(unit, arm, task_id, run):
    return digest({"unit": unit, "arm": arm, "task_id": task_id, "run": run})[:32]


def _claim(path):
    """Exclusive creation: a cell runs once per unit attempt, whichever process tries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        raise ValueError("A cell runs once per unit attempt") from None


def _stored(store, value, summary):
    """Write ``value`` once under its hash (``artifacts/``); the record keeps the hash and a small summary."""
    sha = digest(value)
    write_json(store / "artifacts" / (sha + ".json"), value)
    return {"sha256": sha, **summary}


def _case_fields(cases):
    return [{"status": c.get("status"), "reason": c.get("reason")} for c in cases if isinstance(c, dict)]


def _prediction_summary(prediction):
    output = prediction.get("output")
    cases = output.get("cases") if isinstance(output, dict) else None
    return {"status": prediction.get("status"), "reason": prediction.get("reason"),
            **({"cases": _case_fields(cases)} if isinstance(cases, list) else {})}


def _score_summary(score):
    cases = (score.get("metrics") or {}).get("cases") if isinstance(score.get("metrics"), dict) else None
    return {"status": score.get("status"), "reason": score.get("reason"),
            "cleanup_confirmed": score.get("cleanup_confirmed"),
            **({"cases": _case_fields(cases)} if isinstance(cases, list) else {})}


def _solve(context, cell, task, skill, recorders):
    """A fresh solve; its recorder is kept in ``recorders`` before any call, so every send reaches the record."""
    benchmark = cell["benchmark"]
    with ExitStack() as held:
        on_reply = None
        if benchmark == "spreadsheetbench":  # the program runs right after the reply, inside the frozen solver
            def on_reply():
                held.enter_context(context.native.hold())
        elif benchmark == "alfworld":
            held.enter_context(context.episodes.hold())
        recorder = context.endpoint.recorder(label="%s/%s" % (cell["unit"], cell["id"]), on_reply=on_reply)
        recorders.append(recorder)
        prediction = backends.solve(benchmark, deepcopy(task["public"]), skill, recorder,
                                    runtime=deepcopy(context.runtime[benchmark]))
    return recorder, prediction


def _replay(context, cell, task, skill, recorder):
    """Re-execute the same program: the frozen solver re-extracts it from the stored reply and runs every case."""
    reply, request = recorder.receipts[-1], recorder.sends[-1]["request_sha256"]

    def call(system, user):
        require(_request_hash(system, user) == request, "A replay must present the identical request")
        return reply

    with context.native.hold():
        return backends.solve(cell["benchmark"], deepcopy(task["public"]), skill, call,
                              runtime=deepcopy(context.runtime[cell["benchmark"]]))


def _score(context, cell, task, prediction, index):
    """The frozen native score; SpreadsheetBench in a scoring directory of its own (a new position per scoring)."""
    benchmark = cell["benchmark"]
    runtime = deepcopy(context.runtime[benchmark])
    if benchmark != "spreadsheetbench":
        return backends.score(benchmark, task["public"], task["private"], prediction, runtime=runtime)
    request = {"benchmark": benchmark, "unit": cell["unit"], "cell": cell["id"], "scoring": index}
    position = digest(request)
    runtime["_score_context"] = {"artifact_dir": str(context.store / "host_only" / "scorer_artifacts" / position),
                                 "position": position, "request": request, "prediction_hash": digest(prediction)}
    with context.native.hold():
        return backends.score(benchmark, task["public"], task["private"], prediction, runtime=runtime)


def run_cell(context, cell, task, skill):
    """``cell``: {"id", "unit", "arm", "benchmark", "task_id", "run"}; ``task``: {"public", "private"}. Returns the
    written record; raises ``Pause`` after writing it when the run must stop."""
    path = context.store / "cells" / (cell["id"] + ".json")
    require(not path.exists(), "A cell runs once per unit attempt")
    _claim(context.store / "cells" / (cell["id"] + ".claim"))
    benchmark = cell["benchmark"]
    attempts, recorders, counts, spent = [], [], Counter(), set()
    scorings, stop, verdict = 0, None, None

    def decide(judge):
        while True:
            found = judge(frozenset(spent))
            if found is None or found.remedy is None or counts[found.remedy] < LIMITS[found.remedy]:
                return found
            spent.add(found.remedy)

    try:
        recorder, prediction = _solve(context, cell, task, skill, recorders)
        step = "solve"
        while True:
            current = {"step": step, "prediction": _stored(context.store, prediction, _prediction_summary(prediction)),
                       "score": None, "verdict": None}
            attempts.append(current)  # a stop below leaves it without a verdict
            if recorder.failed:
                raise LedgerFailure(recorder.failed)
            if recorder.broken:
                raise AssumptionBroken(recorder.broken)
            if recorder.invalid:
                raise ConfigurationError("invalid_model_receipt")
            verdict = decide(lambda used: preflight(benchmark, prediction, recorder.receipts,
                                                    refused=recorder.refused, spent=used))
            if verdict is None:
                score = _score(context, cell, task, prediction, scorings)
                scorings += 1
                current["score"] = _stored(context.store, score, _score_summary(score))
                verdict = decide(lambda used: classify(benchmark, prediction, score, recorder.receipts,
                                                       refused=recorder.refused, spent=used))
            current["verdict"] = asdict(verdict)
            if verdict.remedy is None:
                break
            counts[verdict.remedy] += 1
            if verdict.remedy == REEXECUTE:
                prediction, step = _replay(context, cell, task, skill, recorder), "reexecute"
            elif verdict.remedy == RESCORE:
                step = "rescore"
            else:  # RESTART: a new episode; the failed one delivered nothing
                recorder, prediction = _solve(context, cell, task, skill, recorders)
                step = "restart"
    except tuple(STOP_KINDS) as exc:
        stop = {"kind": STOP_KINDS[type(exc)], "reason": str(exc)}
    except Exception as exc:  # an unexpected error interrupts the unit like a crash would; recorded, never scored
        stop = {"kind": "exception", "reason": type(exc).__name__}
    final = attempts[-1]["verdict"] if attempts and stop is None else None
    scored = attempts[-1]["score"] if final is not None else None
    record = seal({
        "version": VERSION + "-cell", "cell": cell, "skill_sha256": digest(skill),
        "attempts": attempts, "remedies": dict(counts), "spent": sorted(spent),
        "sends": [entry for r in recorders for entry in r.sends],
        "refused": any(r.refused for r in recorders),
        "final": None if final is None else {**final, "token": verdict.token},
        "official": None if final is None else (
            {"status": scored["status"], "reason": scored["reason"]} if scored is not None
            else {"status": None, "reason": "not_scored:decided_before_scoring"}),
        "stop": stop})
    write_json(path, record)
    if stop is not None:
        raise Pause(stop["kind"], stop["reason"], cell["id"])
    return record


def run_parallel(function, jobs, *, workers):
    """``function(job)`` for every job on ``workers`` threads. After any error (a ``Pause`` or not) no further job
    starts; the running ones finish and the first error is raised. Returns the results in job order."""
    require(type(workers) is int and workers > 0, "Invalid worker count")
    results, errors = [None] * len(jobs), []
    halted, lock = threading.Event(), threading.Lock()

    def work(index):
        if halted.is_set():
            return
        try:
            results[index] = function(jobs[index])
        except BaseException as error:  # noqa: B036 -- latch the halt whatever escaped, then re-raise below
            halted.set()
            with lock:
                errors.append(error)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, range(len(jobs))))
    if errors:
        raise errors[0]
    return results


def run_cells(context, jobs, *, workers):
    """Run ``(cell, task, skill)`` jobs (``run_parallel``); each cell writes its record before a pause is raised."""
    return run_parallel(lambda job: run_cell(context, *job), jobs, workers=workers)
