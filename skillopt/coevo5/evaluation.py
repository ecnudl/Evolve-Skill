"""Evaluation (registration §10) and sealing (§0).

At stage 0 and after every stage, a chain's Skill solves each of the five test sets once per item -- SpreadsheetBench
only its reference-qualified test items. One benchmark's evaluation is one unit (§13.4): one process owns the unit
while it runs; an attempt runs in its own numbered directory, and an attempt after a pause or an interruption needs the
owner's recorded decision (``recovery.json`` in the earlier attempt); the unit's record (written once, when an attempt
completes) holds no score. Every record names the run it belongs to (the launch manifest's hash). Test scores stay
sealed until the chain is complete or terminated (``unseal``, which reads only the run's units of the chain);
``monitor`` reports completed cells and unknowns only. A Skill byte-identical to the one evaluated by the unit's
predecessor -- the chain's previous stage of the same run, or the run's registered shared stage-0 evaluation -- reuses
that unit's records.

Only this module opens a test set (``data.TestAccess``). The first evaluation of each benchmark records the test
panel's hash (and, for SpreadsheetBench, runs the test-side reference qualification once for all chains, under the
same rule for attempts); every later one re-derives the panel and must find the same hash. While a unit runs, whatever
the process writes to stdout or stderr -- a frozen library's warning quoting a workbook, a print, a child process --
goes to a sealed diagnostics file (``contained``); what leaves a unit is fixed categories and counts only.
"""
from __future__ import annotations

import ctypes
import gc
import io
import os
import re
import socket
import sys
import threading
import traceback
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import data, qualify
from .cells import Pause, cell_id, exclusive, run_cells
from .outcomes import INFRASTRUCTURE, UNCLASSIFIED, UNKNOWN, public
from .protocol import MAX_UNKNOWN_SHARE, SHARED_STAGE0, VERSION

CONSENT_FIELDS = {"test_evaluation", "sheet_test_qualification", "by", "date", "note"}
RECOVERY_FIELDS = {"by", "date", "decision"}
SHEET_QUALIFICATION = "spreadsheetbench-qualification"
ATTEMPT = re.compile(r"attempt-([1-9][0-9]*)")  # ASCII digits only, no leading zero
_CONTAINED = {"depth": 0, "saved": None}
_CONTAINED_LOCK = threading.Lock()


class ContainmentFailure(RuntimeError):
    """What was written while contained could not all be put into the sealed file: the process output is discarded
    from then on, never restored."""


@contextmanager
def contained(shared):
    """Everything this process writes to stdout and stderr while the block runs -- Python writes and warnings, C-level
    writes, child processes -- goes to the sealed diagnostics file ``shared/host_only/diagnostics/<host>-<pid>.log``
    (§0: a warning may quote test content). Process-wide and nestable across threads: the first holder redirects, the
    last restores (``_release``). Read only once the chains are complete or terminated."""
    path = safe_path(shared) / "host_only" / "diagnostics" / ("%s-%d.log" % (socket.gethostname(), os.getpid()))
    with _CONTAINED_LOCK:
        if _CONTAINED["depth"] == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            _flush_output()  # what was written before still goes where it was going
            sink = _sink(path)
            saved = (os.dup(1), os.dup(2), sys.stdout, sys.stderr, sink)
            try:
                os.dup2(sink.fileno(), 1)
                os.dup2(sink.fileno(), 2)
                sys.stdout = sys.stderr = sink
            except BaseException:  # noqa: B036 -- undo a partial redirection, then fail
                _release(saved)
                raise
            _CONTAINED["saved"] = saved
        _CONTAINED["depth"] += 1
    try:
        yield path
    finally:
        with _CONTAINED_LOCK:
            _CONTAINED["depth"] -= 1
            if _CONTAINED["depth"] == 0:
                saved, _CONTAINED["saved"] = _CONTAINED["saved"], None
                _release(saved)


def _sink(path):
    return open(path, "a", encoding="utf-8", errors="replace", buffering=1)


def _flush_output(*first):
    """Flush ``first``, every live Python stream writing to fd 1 or 2 (code may hold the replaced sys.stdout, a logging
    handler its own stream) and C stdio (a native library's buffered printf); returns the first error, if any."""
    streams = list(first)
    for value in gc.get_objects():
        # the object's own type, never ``isinstance``: that reads ``__class__``, which a lazy proxy computes by running
        # code (openai's module client raises without a key)
        if issubclass(type(value), io.IOBase):
            try:
                if not value.closed and value.writable() and value.fileno() in (1, 2):
                    streams.append(value)
            except (OSError, ValueError):  # io.UnsupportedOperation is both
                pass
    failure = None
    for flush in [stream.flush for stream in streams] + [_flush_c]:
        try:
            flush()
        except Exception as error:  # noqa: BLE001 -- reported to the caller
            failure = failure or error
    return failure


def _flush_c():
    if ctypes.CDLL(None).fflush(None) != 0:
        raise OSError("fflush")


def _release(saved):
    """Restore the process output -- only once everything written while contained is in the sealed file (the sink,
    the replaced streams and every other stream on fd 1 or 2, C stdio). If any of it cannot be flushed, the output is
    discarded from then on instead of restored, and ``ContainmentFailure`` is raised; the state is reset either way."""
    out, err, stdout, stderr, sink = saved
    failure = _flush_output(sink, stdout, stderr)
    try:
        if failure is None:
            os.dup2(out, 1)
            os.dup2(err, 2)
            sys.stdout, sys.stderr = stdout, stderr
        else:
            null = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(null, 1)
                os.dup2(null, 2)
            finally:
                os.close(null)
            sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    finally:
        for descriptor in (out, err):
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            sink.close()
        except Exception:  # noqa: BLE001 -- what it still held is sealed or lost, never restored
            pass
    if failure is not None:
        raise ContainmentFailure(type(failure).__name__)


def consent(shared):
    """The owner's recorded consent to read test sets (``shared/consent.json``, written from the owner's message)."""
    path = safe_path(shared) / "consent.json"
    require(path.exists(), "No recorded owner consent to evaluate on the test sets")
    value = read_json(path)
    require(isinstance(value, dict) and set(value) == CONSENT_FIELDS and value["by"] == "owner"
            and value["test_evaluation"] is True, "No recorded owner consent to evaluate on the test sets")
    return value


def attempts(root):
    """The attempt directories (``attempt-<n>``, n >= 1) under ``root``, in numeric order; any other entry is
    ignored."""
    found = {}
    for path in safe_path(root).glob("attempt-*"):
        match = ATTEMPT.fullmatch(path.name)
        if match and path.is_dir():
            found[int(match.group(1))] = path
    return [found[n] for n in sorted(found)]


def recovered(attempt):
    """True when the owner's decision to redo a paused or interrupted attempt is recorded in it (§13.4 b)."""
    path = safe_path(attempt) / "recovery.json"
    value = read_json(path) if path.exists() else None
    return (isinstance(value, dict) and set(value) == RECOVERY_FIELDS and value["by"] == "owner"
            and isinstance(value["decision"], str) and bool(value["decision"].strip()))


def _next_attempt(root):
    """The next attempt directory, or None when the last one ended without the owner's decision to redo it."""
    earlier = attempts(root)
    if earlier and not recovered(earlier[-1]):
        return None
    number = int(ATTEMPT.fullmatch(earlier[-1].name).group(1)) + 1 if earlier else 1
    return safe_path(root) / ("attempt-%d" % number)


def _registry(shared, benchmark, entry):
    """Write-once registry of the test panel a benchmark is evaluated on; every later evaluation must match it."""
    base = safe_path(shared) / "test"
    path = base / ("%s.json" % benchmark)
    with exclusive(base / ("%s.lock" % benchmark), wait=True):
        if path.exists():
            require(read_json(path, sealed=True)["entry"] == entry,
                    "The test panel differs from the first evaluation's")
        else:
            write_json(path, seal({"version": VERSION + "-test-panel", "entry": entry}))


def _sheet_qualification(shared, tasks, runtime, *, allowed, native, workers):
    """The test-side reference qualification, once for all chains (§2.1): one process at a time; each attempt in a new
    directory, an attempt after a paused or interrupted one only with the owner's recorded decision (a waiting
    evaluation pauses instead); the completed attempt is named by a write-once pointer."""
    base = safe_path(shared) / "test"
    pointer, root = base / (SHEET_QUALIFICATION + ".json"), base / SHEET_QUALIFICATION
    with exclusive(base / (SHEET_QUALIFICATION + ".lock"), wait=True):
        if not pointer.exists():
            require(allowed["sheet_test_qualification"] is True, "No owner consent to qualify the test references")
            attempt = _next_attempt(root)
            if attempt is None:
                raise Pause("qualification_paused", attempts(root)[-1].name, SHEET_QUALIFICATION)
            try:
                record = qualify.qualify(tasks, attempt, runtime, side="test", native=native, workers=workers)
            except Pause as pause:
                write_json(attempt / "status.json", seal({"status": "paused", "kind": pause.kind,
                                                          "reason": pause.reason, "cell": pause.cell}))
                raise
            write_json(pointer, seal({"attempt": attempt.name, "qualification_hash": record["record_hash"]}))
        link = read_json(pointer, sealed=True)
        record = qualify.load(root / link["attempt"] / "qualification.json")
        require(record["record_hash"] == link["qualification_hash"], "The test qualification changed")
    return record


def test_tasks(shared, pinned, benchmark, unit, *, run, runtime, native, workers):
    """The tasks a benchmark is evaluated on (the evaluation step only). ``runtime``: the frozen backends' runtime of
    the benchmark (SpreadsheetBench: its scorer qualifies the test references)."""
    allowed = consent(shared)
    tasks, report = data.test_panel(pinned, benchmark, access=data.TestAccess(unit))
    entry = {"run": run, "benchmark": benchmark, "panel_hash": report["panel_hash"],
             "tasks": sorted(t["task_id"] for t in tasks), "excluded_without_pages": report["excluded_without_pages"],
             "source_files": report["source_files"]}
    _registry(shared, benchmark, entry)
    if benchmark != "spreadsheetbench":
        return tasks
    record = _sheet_qualification(shared, tasks, runtime, allowed=allowed, native=native, workers=workers)
    require(record["side"] == "test" and record["task_hashes"] == {t["task_id"]: digest(t) for t in tasks},
            "The test qualification belongs to other items")
    if not record["qualified"]:
        raise Pause("no_qualified_test_items", "spreadsheetbench", unit)  # §2.1: no macro average can be read
    keep = set(record["qualified"])
    return [t for t in tasks if t["task_id"] in keep]


def _infrastructure(record):
    final = record["final"]
    return final["outcome"] == UNKNOWN and final["kind"] in (INFRASTRUCTURE, UNCLASSIFIED)


def _counts(records):
    """Completed cells and unknowns (by kind, and by the table's public reason category) -- never a pass or fail
    count, never a raw reason."""
    unknown = [r for r in records if r["final"]["outcome"] == UNKNOWN]
    return {"cells": len(records), "unknown": len(unknown),
            "unknown_by_kind": dict(Counter(r["final"]["kind"] for r in unknown)),
            "unknown_by_reason": dict(Counter(public(r["final"]) for r in unknown)),
            "infrastructure": sum(_infrastructure(r) for r in records)}


def _own(error):
    """Whether coevo5 raised ``error`` (its messages are fixed text, ids and paths): an error raised elsewhere may
    quote test content (§0)."""
    frames = traceback.extract_tb(error.__traceback__)
    raiser = frames[-2] if len(frames) > 1 and frames[-1].name == "require" else (frames[-1] if frames else None)
    return raiser is not None and Path(raiser.filename).resolve().parent == Path(__file__).resolve().parent


def _public_error(error):
    """A configuration error's type, with its message only when coevo5 raised it."""
    return type(error).__name__ + (":" + str(error)[:200] if _own(error) else "")


def _stack(error):
    """Where an error was raised -- code locations only (file:line:function), never its message."""
    frames = traceback.extract_tb(error.__traceback__)[-8:]
    return ["%s:%d:%s" % (Path(f.filename).name, f.lineno, f.name) for f in frames]


def _diagnose():
    """The exception being handled, in full, into the sealed diagnostics (``contained``); best effort."""
    try:
        traceback.print_exc()
    except Exception:  # noqa: BLE001 -- the status and the raised exception still follow
        pass


def _public_exception(error, unit):
    """What ``evaluate`` raises in place of ``error``: a fresh exception, raised without context -- a failure while
    recording an error (its status, its diagnostics) must not carry that error out of the unit (§0). A ``Pause``
    keeps its public fields; coevo5's own configuration error its message (another one: its type and code locations);
    anything else pauses the unit by its type. An interruption (KeyboardInterrupt, SystemExit) stays itself, without
    what it interrupted."""
    if isinstance(error, Pause):
        return Pause(error.kind, error.reason, error.cell)
    if isinstance(error, ContainmentFailure):
        return Pause("containment", str(error), unit)
    if isinstance(error, ValueError):
        located = "%s at %s" % (type(error).__name__, ", ".join(_stack(error)))
        return ValueError(str(error) if _own(error) else located)
    if isinstance(error, Exception):
        return Pause("exception", type(error).__name__, unit)
    error.__context__ = error.__cause__ = None
    return error


def configuration(context, benchmark):
    """What makes two evaluations of the same Skill interchangeable: the solver and the frozen runtime."""
    return digest({"benchmark": benchmark, "model": context.endpoint.model, "max_tokens": context.endpoint.max_tokens,
                   "runtime": context.runtime[benchmark]})


def _predecessor(before, *, run, chain, stage, benchmark, config):
    own = before["chain"] == chain and before["stage"] == stage - 1
    shared = stage == 0 and before["stage"] == 0 and chain in SHARED_STAGE0.get(before["chain"], ())
    return (before["run"] == run and before["benchmark"] == benchmark and before["config"] == config
            and (own or shared))


def evaluate(unit_root, *, run, shared, pinned, chain, stage, benchmark, skill, context, workers, previous=None):
    """One evaluation unit of the run ``run`` (the launch manifest's hash). ``unit_root``: this unit's directory
    (attempts inside); ``context``: a ``cells.Context`` for the next attempt directory ``unit_root/attempt-<n>``;
    ``previous``: the predecessor unit of this benchmark (the chain's previous stage, or the shared stage-0 unit for a
    stage-0 unit of its member chains). Returns the unit record; raises ``Pause`` (written to the attempt's status)
    when the run must stop. Whatever escapes is replaced by a fresh exception without context (``_public_exception``);
    in full, it is in the sealed diagnostics."""
    unit = "%s/s%s/evaluation/%s" % (chain, stage, benchmark)
    try:
        require(isinstance(run, str) and run, "A unit belongs to a run")
        unit_root = safe_path(unit_root)
        unit_root.mkdir(parents=True, exist_ok=True)
        with exclusive(unit_root / ".lock"):
            with contained(shared):
                try:
                    record = _evaluate(unit_root, run=run, shared=shared, pinned=pinned, chain=chain, stage=stage,
                                       benchmark=benchmark, skill=skill, context=context, workers=workers,
                                       previous=previous)
                except BaseException:  # noqa: B036 -- recorded in full while still contained
                    _diagnose()
                    raise
            # the unit is complete only once its sealed output was flushed (a failed flush leaves the attempt open,
            # so its redo needs the owner's decision)
            write_json(unit_root / "unit.json", record)
            return record
    except BaseException as error:  # noqa: B036 -- replaced below, outside this handler: no context
        replacement = _public_exception(error, unit)
    raise replacement


def _evaluate(unit_root, *, run, shared, pinned, chain, stage, benchmark, skill, context, workers, previous):
    require(not (unit_root / "unit.json").exists(), "This unit is complete")
    unit = "%s/s%d/evaluation/%s" % (chain, stage, benchmark)
    config = configuration(context, benchmark)
    identity = {"run": run, "unit": unit, "chain": chain, "stage": stage, "benchmark": benchmark, "config": config,
                "skill_sha256": digest(skill)}
    before = None if previous is None else read_json(safe_path(previous) / "unit.json", sealed=True)
    require(before is None or _predecessor(before, run=run, chain=chain, stage=stage, benchmark=benchmark,
                                           config=config), "The previous unit is not this unit's predecessor")
    attempt = context.store
    require(attempt == _next_attempt(unit_root) and not attempt.exists(),
            "A unit attempt runs in the next attempt directory; after a pause or an interruption, only with the "
            "owner's recorded decision")
    attempt.mkdir()
    if before is not None:
        if before["skill_sha256"] == digest(skill):
            return seal({"version": VERSION + "-evaluation", **identity, "status": "reused",
                         "from": before["record_hash"], "from_root": str(safe_path(previous)),
                         "attempt": attempt.name, "counts": before["counts"]})
    try:
        if benchmark == "alfworld":
            require(os.environ.get("ALFWORLD_DATA") == context.runtime["alfworld"]["alfworld_data"],
                    "Set ALFWORLD_DATA to the frozen runtime path before launch")
        tasks = test_tasks(shared, pinned, benchmark, unit, run=run, runtime=context.runtime[benchmark],
                           native=context.native, workers=workers)
        jobs = [({"id": cell_id(unit, chain, t["task_id"], 0), "unit": unit, "arm": chain, "benchmark": benchmark,
                  "task_id": t["task_id"], "run": 0}, {"public": t["public"], "private": t["private"]}, skill)
                for t in tasks]
        records = run_cells(context, jobs, workers=workers)
    except Pause as pause:
        write_json(attempt / "status.json", seal({"status": "paused", "kind": pause.kind, "reason": pause.reason,
                                                  "cell": pause.cell}))
        raise
    except Exception as error:  # a configuration check above, or an unexpected error (like a crash): the unit pauses
        _diagnose()
        kind = "configuration" if isinstance(error, ValueError) else "exception"
        reason = _public_error(error) if kind == "configuration" else type(error).__name__
        write_json(attempt / "status.json", seal({"status": "paused", "kind": kind, "reason": reason,
                                                  "stack": _stack(error)}))
        raise Pause(kind, reason, unit) from None
    counts = _counts(records)
    if counts["infrastructure"] > MAX_UNKNOWN_SHARE * counts["cells"]:
        write_json(attempt / "status.json", seal({"status": "paused", "kind": "infrastructure_incomplete",
                                                  "counts": counts}))
        raise Pause("infrastructure_incomplete", "%d of %d cells" % (counts["infrastructure"], counts["cells"]), unit)
    return seal({"version": VERSION + "-evaluation", **identity, "status": "complete", "attempt": attempt.name,
                 "counts": counts, "cells": [job[0]["id"] for job in jobs]})


def _resolve(unit_root, run):
    """(directory, record) of the unit whose cells a unit's record stands for (following reuse within the run)."""
    unit_root = safe_path(unit_root)
    record = read_json(unit_root / "unit.json", sealed=True)
    require(record["run"] == run, "A unit of another run")
    while record["status"] == "reused":
        unit_root = safe_path(record["from_root"])
        source = read_json(unit_root / "unit.json", sealed=True)
        require(source["record_hash"] == record["from"] and source["skill_sha256"] == record["skill_sha256"]
                and source["run"] == run, "A reused unit changed or belongs to another run")
        record = source
    return unit_root, record


def monitor(unit_roots):
    """Infrastructure view of evaluation units: status and counts of completed cells and unknowns -- never a score."""
    rows = []
    for unit_root in unit_roots:
        path = safe_path(unit_root) / "unit.json"
        if path.exists():
            record = read_json(path, sealed=True)
            rows.append({"unit": record["unit"], "status": record["status"], **record["counts"]})
        else:
            found = attempts(unit_root)
            done = len(list(found[-1].glob("cells/*.json"))) if found else 0
            rows.append({"unit_root": str(unit_root), "status": "open", "attempts": len(found), "cells_done": done})
    return rows


def unseal(chain_root, chain, unit_roots, *, run, detail=False):
    """{unit: {task_id: final token}} of the chain's completed evaluation units of the run ``run``, once the chain is
    complete or terminated. Every unit must lie in the chain's directory and belong to the chain and the run; a reused
    record must come from the chain itself or from the run's shared stage-0 evaluation the chain is a member of. With
    ``detail``: {unit: {"source": the unit whose cells they are, "cells": {task_id: {"token", "kind", "official"}}}}
    (the report: one value per shared record, the incomplete count, the official basis)."""
    root = safe_path(chain_root)
    require((root / "chain-complete.json").exists() or (root / "chain-terminated.json").exists(),
            "Test scores stay sealed until the chain is complete or terminated")
    units = {}
    for unit_root in unit_roots:
        unit_root = safe_path(unit_root)
        own = read_json(unit_root / "unit.json", sealed=True)
        require(root in unit_root.parents and own["chain"] == chain, "A unit of another chain")
        source_root, source = _resolve(unit_root, run)
        require((source["chain"] == chain and root in source_root.parents)
                or (source["stage"] == 0 and chain in SHARED_STAGE0.get(source["chain"], ())),
                "A reused unit from outside the chain")
        cells = {}
        for cell in source["cells"]:
            value = read_json(source_root / source["attempt"] / "cells" / (cell + ".json"), sealed=True)
            final = value["final"]
            cells[value["cell"]["task_id"]] = ({"token": final["token"], "kind": final["kind"],
                                                "official": (value["official"] or {}).get("status")}
                                               if detail else final["token"])
        units[own["unit"]] = {"source": source["unit"], "cells": cells} if detail else cells
    return units
