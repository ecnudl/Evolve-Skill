"""One route-B cell (protocol ``fivebench-execskill-v1``; registration §2.3-§2.5, §4.4 rows P1-P7, §6.1-§6.3, §8.1;
implementation plan §1 cells row, §2.8; T-CELLS-1..4): a copy of ``coevo5.cells`` (cells.py:1-263) in which an arm's
procedure package solves one task once through the shell (``solver.solve``, injectable through ``Context.solve``),
the frozen call wrapper, the decision table with the route-B rows (``outcomes_ext``) and the judge (``judge.judge``).

Copied unchanged: the claim before the cell runs and the record written once, then ``Pause`` raised for a stop
(cells.py:166-234); the remedies and their limits (:44, :176-181, :205-214); predictions and scores stored once by
content (:97-101); a SpreadsheetBench scoring directory per scoring (:152-163). ``Pause``, ``cell_id``, ``run_parallel``,
the claim and the two summaries are imported from the frozen module. What changes:

- the record is this protocol's (``protocol.record("cell", ...)``) with the keys of plan §2.8: ``package_sha256``,
  ``arm_kind``, ``enabled``, ``withheld``, ``restored``, ``faults`` (every procedure fault of the cell's shell runs,
  P1/P2, each with its step, and a P3 re-execution mismatch) and ``fault_kinds`` ({kind: n}), ``deciding_receipt`` (of
  the final solve's receipts), ``worst_delivery`` (P5: over every receipt of the cell; recorded, never deciding),
  ``logical_calls``, ``judge``, ``shared_with``, ``dispatch_ts`` / ``finish_ts`` (epoch seconds, §6.2), ``sandbox``
  (ticket C5-4: every container restart and confirmed removal of the cell's shell runs' workers, each with its step,
  so S2 can report them by kind and arm; neither is a procedure fault nor P4), and the cell's
  ``arm``, ``task_id``, ``run`` (and ``set``, ``block`` when the round has them) at the top level for the round
  readers (acceptance.py's cell contract);
- stops are looked up subclass-aware (``errors.stop_kind``): the frozen exact-type table (:215-216) would record the
  route-B stops as "exception" (B1 open item 2);
- no ``on_reply`` native grab (:126-129): the shell holds the native slot around each container run only, never across
  a model call (§2.5); an ALFWorld cell still holds its episode slot for the whole episode (:130-131);
- the frozen preflight and classify (:196, :202) are ``outcomes_ext``'s, read on the deciding receipt (Codex F12);
- re-execution (:139-149) replays the LOGICAL calls in order (Codex F13). ``Calls`` logs each logical call of a solve:
  its texts, the receipt the frozen Recorder returned after its resends (calls.py:268-279) or the exception it raised,
  and the indices of its transport sends in the record's ``sends``. ``Replay`` gives the k-th call of the re-executed
  shell the k-th stored logical receipt (or raises the stored exception again) when it presents the identical
  request; transport sends stay in ``sends`` for the ledger and are never served. Another request, or another number
  of calls, is P3: the prediction ``REPLAY_MISMATCH``, the token ``unknown_fault``. The shell runs again on a fresh
  worker and reads its stored pre-check report back (§2.5);
- persistence goes through a store with four methods (``claim``, ``artifact``, ``scorer_dir``, ``save``):
  ``TrainingStore`` keeps the record, the trajectory and the enable-log line (``trajectories``); the test read's
  adapter keeps hashes only (plan §2.10, Codex F16);
- ``share_cell``: structural-zero sharing in the test read (§8.1);
- a unit whose cells run on several benches (a self-test's earlier generated sets, §5.5) gives each cell the endpoint
  of its own bench (``Context.endpoints``: that bench's client, nominal M, read timeout and bound B, the unit's
  scopes; ``units.solver_endpoint(..., cell_bench=)``; Codex finding #4), so a cell never runs with another bench's
  client beside its own bench's truncation threshold (``nominal``);
- a shortcut-probe cell carries ``shortcut`` (registration §7.2: SpreadsheetBench's "no_workbook"); the shell gets it
  as ``solver.solve(..., shortcut=...)``, on re-execution too. The record keeps the request in ``cell`` and, at the top
  level, ``shortcut``: the mode the shell's own record states for its latest run (None when it ran without one), which
  ``examiner.shortcut`` checks (ticket C1-2).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path

from skillopt.coevo5.calls import _request_hash
from skillopt.coevo5.cells import Pause, _claim, _prediction_summary, _score_summary, cell_id, run_parallel
from skillopt.coevo5.outcomes import REEXECUTE, RESCORE, RESTART
from skillopt.coevo5.protocol import MAX_EPISODE_RESTARTS, MAX_REEXECUTIONS, MAX_RESCORES
from skillopt.continual_eval import backends
from skillopt.continual_eval.backends import _prediction_unknown
from skillopt.continual_eval.core import require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import judge as judges
from . import outcomes_ext, solver, trajectories, zebralogic, notes
from .profiles import is_v29
from . import profiles
from .client import route_of
from .errors import AssumptionBroken, ConfigurationError, LedgerFailure, stop_kind
from .outcomes_ext import REPLAY_MISMATCH
from .package import Package
from .profiles import SUPPORTED_BENCHES as BENCHES, EVIDENCE, record, verified

__all__ = ("ARM_KINDS", "Arm", "Calls", "Context", "Pause", "Replay", "TrainingStore", "cell_id", "run_cell",
           "run_cells", "run_parallel", "share_cell", "share_same")

LIMITS = {REEXECUTE: MAX_REEXECUTIONS, RESCORE: MAX_RESCORES, RESTART: MAX_EPISODE_RESTARTS}  # cells.py:44
ARM_KINDS = ("candidate", "parent", "card", "placebo_y", "placebo_i", "dup", "text", "blank")
ARM_PREFIXES = ("withhold:", "restore:", "gen:")
CELL_KEYS = ("id", "unit", "arm", "benchmark", "task_id", "run")
ROUND_KEYS = ("arm", "task_id", "run", "set", "block")  # copied to the record's top level when the cell has them


# ------------------------------------------------------------------------------------------------ arms, context
@dataclass(frozen=True)
class Arm:
    """One cell's arm (plan §2.8 ``arm_kind``): the package and the shell's arm keywords for this cell
    (``solver.solve``): ``withhold``, ``restore``, ``placebo`` (this cell's {procedures, seed}, ``placebo.arm``) and
    ``text`` (T_F's frozen descriptions)."""
    kind: str
    package: Package
    withhold: frozenset = frozenset()
    restore: frozenset = frozenset()
    placebo: dict | None = None
    text: dict | None = None

    def __post_init__(self):
        require(type(self.kind) is str and (self.kind in ARM_KINDS or any(
            self.kind.startswith(prefix) and len(self.kind) > len(prefix) for prefix in ARM_PREFIXES)),
            "Unknown arm kind")
        require(isinstance(self.package, Package), "An arm runs a procedure package")
        object.__setattr__(self, "withhold", frozenset(self.withhold))
        object.__setattr__(self, "restore", frozenset(self.restore))


@dataclass
class Context:
    """What the cells of one unit attempt share (frozen cells.py:74-81 plus the route-B parts). ``attempt``: the
    attempt's directory; ``endpoint``: the attempt's solver endpoint (``budgets.endpoint``); ``runtime``: the frozen
    runtime per bench; ``cards``: {bench: the active bench card} (§2.2); ``native`` / ``episodes``: the
    spreadsheet-native and alfworld-episode pools; ``worker(bench)``: an unstarted ``sandbox.client.Worker``;
    ``evidence``: the records' label; ``nominal``: {bench: M} of chain D's margin rule (§4.1; empty for chain G);
    ``solve``: the shell; ``clock``: dispatch and finish times; ``endpoints``: {bench: endpoint} of a unit whose cells
    run on several benches (module docstring; Codex finding #4) -- when given, every cell takes its bench's and a
    bench without one is refused; empty, every cell takes ``endpoint``."""
    attempt: Path
    endpoint: object
    runtime: dict
    cards: dict
    native: object
    episodes: object
    worker: object
    evidence: str
    nominal: dict = field(default_factory=dict)
    solve: object = solver.solve
    clock: object = time.time
    endpoints: dict = field(default_factory=dict)
    configuration: str | None = None

    def __post_init__(self):
        self.attempt = safe_path(self.attempt)
        if profiles.is_v210(self.configuration):
            from .instruction_start import active_cards
            self.cards = active_cards(self.cards, self.configuration)
        require(self.evidence in EVIDENCE and set(self.nominal) <= set(BENCHES), "Invalid cell context")
        require(set(self.endpoints) <= set(BENCHES) and all(
            getattr(found, "model", None) == getattr(self.endpoint, "model", None)
            for found in self.endpoints.values()), "Per-bench endpoints of the unit's one solver model")

    def endpoint_of(self, bench):
        """The endpoint of a cell on ``bench``: its bench's in ``endpoints`` (Codex finding #4), else ``endpoint``."""
        if self.endpoints:
            require(bench in self.endpoints, "A cell on a bench the unit has no endpoint for: " + str(bench))
            return self.endpoints[bench]
        return self.endpoint


def _check_cell(cell):
    require(isinstance(cell, dict) and set(CELL_KEYS) <= set(cell) and cell["benchmark"] in BENCHES
            and cell["id"] == cell_id(cell["unit"], cell["arm"], cell["task_id"], cell["run"]),
            "A cell names its id, unit, arm, bench, task and run")


def _worker(context, bench, package):
    """An unstarted sandbox worker for one cell or episode (plan §4); None when the package holds no procedure for a
    QA or SpreadsheetBench item. An ALFWorld episode always gets one: the shell pings it, so every arm takes the same
    slot path (§6.2)."""
    if (bench != "alfworld" or context.configuration == profiles.BASELINE_V210) and not package.for_bench(bench):
        return None
    return context.worker(bench)


def _shell(context, cell, task, arm, call, **extra):
    bench = cell["benchmark"]
    if cell.get("shortcut") is not None:  # a shortcut-probe cell (§7.2, ticket C1-2); absent otherwise
        extra["shortcut"] = cell["shortcut"]
    card = context.cards[bench]
    if arm.kind == "blank":
        require(profiles.is_v210(context.configuration) and not arm.package.procedures,
                "B has empty guidance and no procedure in v2.10 only")
        card = ""
    return context.solve(bench, deepcopy(task["public"]), card, arm.package, call,
                         runtime=deepcopy(context.runtime[bench]), worker=_worker(context, bench, arm.package),
                         withhold=arm.withhold, restore=arm.restore, placebo=arm.placebo, text=arm.text,
                         native=context.native, nominal_tokens=context.nominal.get(bench), **extra)


# ---------------------------------------------------------------------------------------------- logical calls
class Calls:
    """A solve's call function: the frozen Recorder (resends, cooldown, ledger) behind a log of the LOGICAL calls
    (Codex F13). Each entry: purpose (from the shell's call log, ``label``), system, user, request_sha256, receipt (the
    Recorder's returned receipt) or error (the exception it raised), receipt_index (among this solve's receipts) and
    send_indices (in the cell record's ``sends``)."""

    def __init__(self, recorder, *, offset, solve):
        self.recorder, self.offset, self.solve, self.entries = recorder, offset, solve, []

    def __call__(self, system, user):
        sends, index = len(self.recorder.sends), len(self.recorder.receipts)
        entry = {"purpose": None, "system": system, "user": user, "request_sha256": _request_hash(system, user),
                 "receipt": None, "error": None, "receipt_index": None, "send_indices": []}
        self.entries.append(entry)
        try:
            receipt = self.recorder(system, user)
        except Exception as error:  # the frozen _response turns it into the call's reason; kept for a replay
            entry["error"] = error
            raise
        finally:
            entry["send_indices"] = list(range(self.offset + sends, self.offset + len(self.recorder.sends)))
        entry["receipt"], entry["receipt_index"] = receipt, index
        return receipt

    def label(self, prediction):
        """Name each logical call by the shell's purpose (the shell logs one entry per call, in order)."""
        shell = prediction.get("shell") if isinstance(prediction, dict) else None
        logged = shell.get("calls") if isinstance(shell, dict) else []
        require(isinstance(logged, list) and len(logged) == len(self.entries) and all(
            entry["request_sha256"] == call["request_sha256"] for entry, call in zip(self.entries, logged)),
            "The shell logs every logical call, in order")
        for entry, call in zip(self.entries, logged):
            entry["purpose"] = call["purpose"]

    def logical(self):
        """This solve's entries of the record's ``logical_calls``."""
        return [{"solve": self.solve, "purpose": e["purpose"], "request_sha256": e["request_sha256"],
                 "receipt_index": e["receipt_index"], "send_indices": e["send_indices"],
                 "exception": None if e["error"] is None else type(e["error"]).__name__} for e in self.entries]


class ReplayMismatch(Exception):
    """A re-executed shell presented another request than the stored logical call, or one call too many (P3). Raised
    inside the call function only: the frozen ``_response`` turns it into the call's reason."""


class Replay:
    """The call function of a re-execution (Codex F13): the k-th call gets the k-th stored logical call's receipt, or
    its exception again, when it presents the identical request; never a transport send's receipt."""

    def __init__(self, entries):
        self.entries, self.served, self.mismatched = list(entries), 0, False

    def __call__(self, system, user):
        k = self.served
        if self.mismatched or k == len(self.entries) or _request_hash(system, user) != self.entries[k]["request_sha256"]:
            self.mismatched = True
            raise ReplayMismatch("logical call %d" % k)
        self.served += 1
        if self.entries[k]["error"] is not None:
            raise self.entries[k]["error"]
        return self.entries[k]["receipt"]

    def matched(self):
        return not self.mismatched and self.served == len(self.entries)


# ---------------------------------------------------------------------------------------------------- stores
class TrainingStore:
    """Persistence of a training-side unit attempt: claims and records under ``cells/``, predictions and scores once by
    content under ``artifacts/`` (cells.py:88-101), scorer directories under ``host_only/scorer_artifacts/``, the
    trajectory and the enable-log line (``trajectories``)."""

    def __init__(self, attempt):
        self.attempt = safe_path(attempt)

    def claim(self, cell):
        require(not (self.attempt / "cells" / (cell + ".json")).exists(), "A cell runs once per unit attempt")
        _claim(self.attempt / "cells" / (cell + ".claim"))

    def artifact(self, value, summary):
        sha = digest(value)
        write_json(self.attempt / "artifacts" / (sha + ".json"), value)
        return {"sha256": sha, **summary}

    def scorer_dir(self, position):
        return self.attempt / "host_only" / "scorer_artifacts" / position

    def save(self, value, trajectory):
        write_json(self.attempt / "cells" / (value["cell"]["id"] + ".json"), value)
        if trajectory is not None:
            trajectories.write(self.attempt, value["cell"]["id"], trajectory)
            if trajectory["route"] is not None:
                trajectories.append_enable(self.attempt, value, trajectory["route"])
        return value


# ---------------------------------------------------------------------------------------- solve, replay, score
def _solve(context, cell, task, arm, recorders, logs):
    """A fresh solve (cells.py:122-136 without the native grab); its recorder and call log are kept before any call,
    so every send reaches the record."""
    with context.episodes.hold() if cell["benchmark"] == "alfworld" else nullcontext():
        recorder = context.endpoint_of(cell["benchmark"]).recorder(label="%s/%s" % (cell["unit"], cell["id"]))
        log = Calls(recorder, offset=sum(len(r.sends) for r in recorders), solve=len(recorders))
        recorders.append(recorder)
        logs.append(log)
        prediction = _shell(context, cell, task, arm, log)
    log.label(prediction)
    return recorder, log, prediction


def _replay(context, cell, task, arm, previous, log):
    """Re-execute the same program (cells.py:139-149) over the ORDERED logical calls of ``log`` with the stored
    pre-check report of ``previous`` (module docstring); P3 when the shell asks for anything else. No slot is held
    here: the shell takes the native slot around each container run."""
    replay = Replay(log.entries)
    stored = (previous.get("shell") or {}).get("precheck")
    prediction = _shell(context, cell, task, arm, replay, precheck_report=stored)
    if replay.matched():
        return prediction
    return _prediction_unknown(REPLAY_MISMATCH, replay={"served": replay.served, "stored": len(log.entries)})


def _score(context, cell, task, prediction, index, store):
    """The frozen native score (cells.py:152-163); SpreadsheetBench in a scoring directory of its own."""
    bench = cell["benchmark"]
    runtime = deepcopy(context.runtime[bench])
    if bench == zebralogic.BENCH:
        return zebralogic.score(task["public"], task["private"], prediction, runtime=runtime)
    if bench != "spreadsheetbench":
        return backends.score(bench, task["public"], task["private"], prediction, runtime=runtime)
    request = {"benchmark": bench, "unit": cell["unit"], "cell": cell["id"], "scoring": index}
    position = digest(request)
    runtime["_score_context"] = {"artifact_dir": str(store.scorer_dir(position)), "position": position,
                                 "request": request, "prediction_hash": digest(prediction)}
    with context.native.hold():
        return backends.score(bench, task["public"], task["private"], prediction, runtime=runtime)


def _faults(runs, verdict):
    """Every procedure fault of the cell's shell runs ({procedure, hook, kind, exc_type, message, step}) and a P3
    re-execution mismatch."""
    found = [{**fault, "step": step} for step, prediction in runs
             for fault in ((prediction.get("shell") or {}).get("faults") or [])]
    if verdict is not None and verdict.kind == outcomes_ext.FAULT:
        found.append({"procedure": None, "hook": None, "kind": REPLAY_MISMATCH, "exc_type": None, "message": None,
                      "step": "reexecute"})
    return found


def _sandbox(runs):
    """The sandbox lifecycle of the cell's shell runs (ticket C5-4): {"restarts", "cleanups"}, each event of a run's
    ``shell.sandbox`` with the run's step; empty lists when no run had a worker.
    Opted-in start measurements retain their container and the same step association."""
    found = {"restarts": [], "cleanups": []}
    for step, prediction in runs:
        events = (prediction.get("shell") or {}).get("sandbox") or {}
        if events.get("starts"):
            found.setdefault("starts", [])
        for name, entries in found.items():
            entries += [{**event, "step": step} for event in events.get(name) or []]
    return found


def _shortcut(runs):
    """The shell mode the cell's latest shell run states (``shell.shortcut``; None when it ran without one)."""
    for _, prediction in reversed(runs):
        shell = prediction.get("shell")
        if isinstance(shell, dict):
            return shell.get("shortcut")
    return None


def _route(runs):
    """The route of the cell's latest shell run (None when no run routed)."""
    for _, prediction in reversed(runs):
        shell = prediction.get("shell")
        if isinstance(shell, dict):
            return shell.get("route")
    return None


def _solver_route(context, recorders, bench):
    """The solver route of the cell (registrar row "deepseek route B", M4): ``client.route_of`` the client of the
    endpoint its calls went through (its first recorder's, else the context's for ``bench``) -- chain D's route id
    and the model id the requests named; route None for a client without routes (chain G)."""
    endpoint = recorders[0].endpoint if recorders else context.endpoints.get(bench, context.endpoint)
    return route_of(getattr(endpoint, "client", None), getattr(endpoint, "model", None))


def _audited_fields(context, runs, recorders, route):
    """v2.9 per-cell metadata, including explicit zero hits for the card arm."""
    if not is_v29(context.configuration):
        return {}
    rows = [row for _, pred in runs for entry in (pred.get("shell") or {}).get("notes", [])
            for row in entry.get("dropped", [])]
    receipts = [receipt for rec in recorders for receipt in rec.receipts]
    models = list(dict.fromkeys(receipt.get("returned_model") for receipt in receipts
                               if isinstance(receipt, dict) and receipt.get("returned_model")))
    return {"configuration": context.configuration, "keyword_hits": notes.keyword_summary(rows),
            "applies": {pid: row["applies"] for pid, row in (route or {}).get("per_procedure", {}).items()},
            "returned_models": models, "returned_model": models[-1] if models else None}


def _shared_audited_fields(context, source, route):
    if not is_v29(context.configuration):
        return {}
    return {"configuration": context.configuration,
            "keyword_hits": deepcopy(source.get("keyword_hits", {"count": 0, "sentences": []})),
            "applies": {pid: row["applies"] for pid, row in route.get("per_procedure", {}).items()},
            "returned_models": list(source.get("returned_models", [])), "returned_model": source.get("returned_model")}


# -------------------------------------------------------------------------------------------------- the cell
def run_cell(context, cell, task, arm, *, store):
    """``cell``: {"id", "unit", "arm", "benchmark", "task_id", "run"} (plus "set", "block", "source_item" when the
    round has them, "shortcut" on a shortcut-probe cell); ``task``: {"public", "private"}; ``arm``: the cell's
    ``Arm``; ``store``: ``TrainingStore`` or the test read's adapter. Returns the stored record; raises ``Pause`` after
    storing it when the run must stop."""
    _check_cell(cell)
    require(isinstance(arm, Arm), "A cell runs one Arm")
    store.claim(cell["id"])
    dispatched = context.clock()
    bench = cell["benchmark"]
    attempts, recorders, logs, runs, counts, spent = [], [], [], [], Counter(), set()
    scorings, stop, verdict, judged, deciding, score = 0, None, None, None, None, None
    recorder = log = prediction = None

    def decide(judge):
        while True:
            found = judge(frozenset(spent))
            if found is None or found.remedy is None or counts[found.remedy] < LIMITS[found.remedy]:
                return found
            spent.add(found.remedy)

    try:
        recorder, log, prediction = _solve(context, cell, task, arm, recorders, logs)
        step = "solve"
        while True:
            if step != "rescore":
                runs.append((step, prediction))
            current = {"step": step, "prediction": store.artifact(prediction, _prediction_summary(prediction)),
                       "score": None, "verdict": None}
            attempts.append(current)  # a stop below leaves it without a verdict
            if recorder.failed:
                raise LedgerFailure(recorder.failed)
            if recorder.broken:
                raise AssumptionBroken(recorder.broken)
            if recorder.invalid:
                raise ConfigurationError("invalid_model_receipt")
            deciding = outcomes_ext.deciding_receipt(prediction, recorder.receipts)
            score = None
            verdict = decide(lambda used: outcomes_ext.preflight(bench, prediction, recorder.receipts,
                                                                 deciding=deciding, refused=recorder.refused,
                                                                 spent=used))
            if verdict is None:
                score = _score(context, cell, task, prediction, scorings, store)
                scorings += 1
                current["score"] = store.artifact(score, _score_summary(score))
                verdict = decide(lambda used: outcomes_ext.classify(bench, prediction, score, recorder.receipts,
                                                                    deciding=deciding, refused=recorder.refused,
                                                                    spent=used))
            current["verdict"] = json.loads(json.dumps(asdict(verdict)))  # as stored: tuples are lists
            if verdict.remedy is None:
                break
            counts[verdict.remedy] += 1
            if verdict.remedy == REEXECUTE:
                prediction, step = _replay(context, cell, task, arm, prediction, log), "reexecute"
            elif verdict.remedy == RESCORE:
                step = "rescore"
            else:  # RESTART: a new episode; the failed one delivered nothing
                recorder, log, prediction = _solve(context, cell, task, arm, recorders, logs)
                step = "restart"
        judged = judges.judge(bench, task["public"], task["private"], prediction, recorder.receipts,
                              runtime=deepcopy(context.runtime[bench]), score=score, verdict=verdict,
                              deciding=deciding)
    except Exception as exc:  # a stop of the run, or an unexpected error that interrupts the unit like a crash
        kind = stop_kind(exc)
        stop = {"kind": kind, "reason": str(exc)} if kind is not None else {"kind": "exception",
                                                                             "reason": type(exc).__name__}
    finished = context.clock()
    final = attempts[-1]["verdict"] if attempts and stop is None else None
    scored = attempts[-1]["score"] if final is not None else None
    faults = _faults(runs, verdict if final is not None else None)
    route = _route(runs)
    worst = outcomes_ext.worst_delivery([r for rec in recorders for r in rec.receipts])
    logical = [entry for one in logs for entry in one.logical()]
    fields = {
        "cell": cell, **{name: cell[name] for name in ROUND_KEYS if name in cell},
        **({"shortcut": _shortcut(runs)} if cell.get("shortcut") is not None else {}),
        "package_sha256": arm.package.sha256, "arm_kind": arm.kind,
        **({"card": ""} if arm.kind == "blank" else {}),
        "enabled": None if route is None else list(route["enabled"]),
        "withheld": sorted(arm.withhold), "restored": sorted(arm.restore),
        "attempts": attempts, "remedies": dict(counts), "spent": sorted(spent),
        "sends": [entry for r in recorders for entry in r.sends], "refused": any(r.refused for r in recorders),
        "logical_calls": logical, "deciding_receipt": deciding if final is not None else None,
        "worst_delivery": worst, "faults": faults,
        "fault_kinds": dict(sorted(Counter(str(f.get("kind")) for f in faults).items())),
        "final": None if final is None else {**final, "token": outcomes_ext.token(verdict)},
        "official": None if final is None else (
            {"status": scored["status"], "reason": scored["reason"]} if scored is not None
            else {"status": None, "reason": "not_scored:decided_before_scoring"}),
        "judge": judged if final is not None else None, "shared_with": None, "sandbox": _sandbox(runs),
        "solver_route": _solver_route(context, recorders, cell["benchmark"]),
        "dispatch_ts": dispatched, "finish_ts": finished, "stop": stop}
    fields.update(_audited_fields(context, runs, recorders, route))
    revised = context.runtime.get(bench, {}).get("code_extraction_version") == "explicit-python-fences-v2"
    sealed = record("cell-v2-3" if revised else "cell", context.evidence, fields)
    trajectory = None
    if final is not None:
        trajectory = trajectories.build(
            cell, evidence=context.evidence, arm_kind=arm.kind, package_sha256=arm.package.sha256, calls=log.entries,
            prediction=prediction, judge=judged, deciding=deciding, worst=worst, logical_calls=log.logical(),
            dispatch_ts=dispatched, finish_ts=finished,
            **({"configuration": context.configuration, "solver_route": fields["solver_route"],
                "keyword_hits": fields["keyword_hits"]} if is_v29(context.configuration) else {}))
    stored = store.save(sealed, trajectory)
    if stop is not None:
        raise Pause(stop["kind"], stop["reason"], cell["id"])
    return stored


def share_cell(context, cell, task, arm, source, route, *, store):
    """Structural-zero sharing in the test read (§8.1): an arm whose package enables no procedure on the item (its
    sealed ``route`` there, ``router.route``: zero model calls) is the card arm on it, so its cell is the C cell
    ``source`` -- the same item and run, run in this unit -- linked by ``shared_with``. Nothing runs and nothing is
    sent; the route's predicate faults (P2) are the cell's. Returns the stored record."""
    _check_cell(cell)
    require(isinstance(arm, Arm), "A cell runs one Arm")
    source, route = verified(source, "cell"), verified(route, "route")
    require(source["stop"] is None and source["final"] is not None and source["shared_with"] is None,
            "Share a completed cell that ran")
    require(all(source["cell"][name] == cell[name] for name in ("unit", "benchmark", "task_id", "run")),
            "Share a cell of the same unit, item and run")
    bench = cell["benchmark"]
    require(route["package_sha256"] == arm.package.sha256 and route["bench"] == bench and not route["enabled"],
            "Only an arm whose package enables nothing on the item shares the card cell")
    require(route["routing_view_sha256"] == digest(solver.routing_view(bench, task["public"],
                                                                       runtime=context.runtime[bench])),
            "The route was made on this item's routing view")
    store.claim(cell["id"])
    now = context.clock()
    faults = [{**fault, "step": "route"} for fault in route["faults"]]
    fields = {
        "cell": cell, **{name: cell[name] for name in ROUND_KEYS if name in cell},
        "package_sha256": arm.package.sha256, "arm_kind": arm.kind, "enabled": [],
        "withheld": sorted(arm.withhold), "restored": sorted(arm.restore),
        "attempts": [], "remedies": {}, "spent": [], "sends": [], "refused": False, "logical_calls": [],
        "deciding_receipt": source["deciding_receipt"], "worst_delivery": source["worst_delivery"],
        "faults": faults, "fault_kinds": dict(sorted(Counter(str(f.get("kind")) for f in faults).items())),
        "final": source["final"], "official": source["official"], "judge": source["judge"],
        "shared_with": source["cell"]["id"], "sandbox": _sandbox([]), "dispatch_ts": now, "finish_ts": now,
        "solver_route": source.get("solver_route"), "stop": None}
    fields.update(_shared_audited_fields(context, source, route))
    return store.save(record("cell", context.evidence, fields), None)


def share_same(context, cell, task, arm, source, route, source_route, source_package, *, store):
    """v2 stage reads (``protocol.STAGE_READ``; ``evaluation.stage_plan``): a stage arm whose package enables on the
    item exactly the procedures -- the same ids, in the same order, byte-identical (``Procedure.sha256``) -- that the
    cell ``source`` of another plain package arm of the unit ran with (F's, or an earlier stage arm's) sends the same
    solver request, so its cell is ``source``, linked by ``shared_with``. ``route``: the stage package's sealed route
    on the item; ``source_route``: the source package's (``source_package``), on the same routing view; the source
    cell itself ran with that route's procedures (its ``enabled``) and recorded no fault (a faulted hook drops its
    notes without changing ``enabled``, so the request a fault-free run sends differs: Codex stage review #1). Nothing
    runs and nothing is sent; the route's predicate faults are the cell's. Returns the stored record."""
    _check_cell(cell)
    require(isinstance(arm, Arm) and isinstance(source_package, Package), "A cell runs one Arm of a package")
    require(arm.kind == "candidate" and not (arm.withhold or arm.restore) and arm.placebo is None and arm.text is None,
            "Only a plain package arm shares another arm's cell")
    source, route, source_route = verified(source, "cell"), verified(route, "route"), verified(source_route, "route")
    require(source["stop"] is None and source["final"] is not None and source["shared_with"] is None,
            "Share a completed cell that ran")
    require(not source["faults"], "Share a cell that ran without a fault (Codex stage review #1)")
    require(all(source["cell"][name] == cell[name] for name in ("unit", "benchmark", "task_id", "run")),
            "Share a cell of the same unit, item and run")
    require(source["arm_kind"] == "candidate" and not source["withheld"] and not source["restored"]
            and source["package_sha256"] == source_package.sha256 == source_route["package_sha256"],
            "The source cell ran its plain package arm")
    bench = cell["benchmark"]
    view = digest(solver.routing_view(bench, task["public"], runtime=context.runtime[bench]))
    require(route["package_sha256"] == arm.package.sha256 and route["bench"] == source_route["bench"] == bench
            and route["routing_view_sha256"] == source_route["routing_view_sha256"] == view,
            "Both routes were made on this item's routing view")
    enabled = list(route["enabled"])
    require(enabled and enabled == list(source_route["enabled"]) == list(source["enabled"] or []),
            "The stage arm enables exactly the procedures the source cell ran with")
    require(all(arm.package.get(pid).sha256 == source_package.get(pid).sha256 for pid in enabled),
            "The shared procedures are byte-identical")
    store.claim(cell["id"])
    now = context.clock()
    faults = [{**fault, "step": "route"} for fault in route["faults"]]
    fields = {
        "cell": cell, **{name: cell[name] for name in ROUND_KEYS if name in cell},
        "package_sha256": arm.package.sha256, "arm_kind": arm.kind, "enabled": enabled,
        "withheld": [], "restored": [],
        "attempts": [], "remedies": {}, "spent": [], "sends": [], "refused": False, "logical_calls": [],
        "deciding_receipt": source["deciding_receipt"], "worst_delivery": source["worst_delivery"],
        "faults": faults, "fault_kinds": dict(sorted(Counter(str(f.get("kind")) for f in faults).items())),
        "final": source["final"], "official": source["official"], "judge": source["judge"],
        "shared_with": source["cell"]["id"], "sandbox": _sandbox([]), "dispatch_ts": now, "finish_ts": now,
        "solver_route": source.get("solver_route"), "stop": None}
    fields.update(_shared_audited_fields(context, source, route))
    return store.save(record("cell", context.evidence, fields), None)


def run_cells(context, jobs, *, workers, store):
    """Run ``(cell, task, arm)`` jobs (``run_parallel``); each cell stores its record before a pause is raised."""
    return run_parallel(lambda job: run_cell(context, *job, store=store), jobs, workers=workers)
