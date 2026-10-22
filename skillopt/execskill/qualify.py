"""SpreadsheetBench reference qualification with importable versions (protocol ``fivebench-execskill-v1``;
registration §1 "v3 资产复用" (owner #7) and "复制并换版本号", §7.2 SpreadsheetBench family, §10 S0; Codex F15;
implementation plan §1 qualify row, T-QUAL-1..2; ticket A11-1).

``qualify`` is a copy of the record-producing closure of the frozen ``coevo5.qualify.qualify`` (qualify.py:85-131):
every case of an item submits its own reference workbook as the answer and the frozen v7 scorer judges the item twice,
each time in a fresh scoring directory; an item qualifies when both scorings pass every case. The frozen function
stamps v3's version (it imports ``VERSION`` at qualify.py:24 and stamps it at :124), so importing it would stamp this
protocol's new records ``fivebench-coevolution-v3-sheet-qualification``; the copy stamps
``fivebench-execskill-v1-sheet-qualification`` (``protocol.record``) and keeps the frozen scoring helpers imported
unchanged (``reference_prediction``, ``_check``, ``_passed``, ``_first_failure``, ``category``, ``backends.score``).
The signature and the fields ``qualified`` / ``scorings_per_item`` stay the frozen ones (ticket A11-1:
``generators.sheet.Engine.qualify``); ``evidence`` is the one added keyword (a run binds it with
``functools.partial(qualify, evidence=setting.evidence)``).

``load`` reads this protocol's record, or a v3 record only through the explicit table ``IMPORTABLE`` (the frozen
``load``, qualify.py:134-138, refuses any other version); ``reverify`` is the zero-call re-check before launch: the
record's own hash, the hash pinned in the manifest and, given the items, their content hashes.

The recalculation engine (ticket C7b1-3, registrar addendum 2026-10-22 12:0x). The frozen v7 engine identity keys
its scorer sources by absolute path (``continual_eval/sheet_recalc_v7.py:154-159``), so a v7 engine qualification
revalidates only from the checkout that made it (``scripts/replay_sheet_v6.py:133``). As v3 did per snapshot
(``coevo5.prelaunch.engine_runtime``), the execskill snapshot gets its own zero-call qualification:

- ``engine_runtime(base, path)``: the v3 manifest's SpreadsheetBench runtime with only the three qualification fields
  of ``recalculation`` replaced, then revalidated (``revalidate``, the frozen offline ``qualified_engine``);
- ``same_engine_sources(new, old)``: the two qualifications' engine identities, equal in every non-source field and in
  their sources as {path relative to each identity's own snapshot root: sha256} -- what keeps the imported v3
  training qualification valid next to the new engine qualification (owner #7, Codex F15).
"""
from __future__ import annotations

import hashlib
import os
from collections import Counter
from copy import deepcopy
from pathlib import PurePosixPath

from skillopt.coevo5.qualify import CATEGORIES, PASSES, _check, _first_failure, _passed, category, reference_prediction
from skillopt.coevolution_v5.core import verify
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from .cells import run_parallel
from .protocol import IMPORTABLE, RECORD_HASH, kind, record, verified

__all__ = ("CATEGORIES", "KIND", "PASSES", "SCORER", "engine_runtime", "load", "qualify", "record_digest",
           "revalidate", "reverify", "same_engine_sources", "snapshot_root", "summary")

KIND = "sheet-qualification"  # fivebench-execskill-v1-sheet-qualification
SCORE_KIND = "sheet-qualification-score"
V3_HASH = "record_hash"  # the frozen seal's field (coevolution_v5/core.py:46)
SCORER = "qualified_lo_recalc_v7_v1"  # the frozen v7 scorer (sheet_numeric_adapter.VERSION)
ENGINE_PROFILE = "v7"  # scripts/replay_sheet_v6.py qualify --engine-version v7
REPLACED = ("qualification_path", "qualification_sha256", "qualification_hash")  # C7b1-3: the only fields replaced
PACKAGE = "skillopt"  # the scorer sources are modules of this package; the directory holding it is the snapshot root


def qualify(tasks, root, runtime, *, side, native, workers, evidence):
    """Score every item's references twice in the new directory ``root``; write and return the sealed record
    (frozen qualify.py:85-131 with this protocol's stamp). The scorer artifacts under ``root/host_only`` are derived
    from the references (the recalculated reference workbooks); ``run_parallel`` joins every started scoring before it
    returns or raises, and on the test side ``evaluation._sheet_qualification`` then deletes everything but the
    sanitized results on every exit and sweeps an interrupted attempt before any retry (Codex finding #3 of
    2026-10-22)."""
    require(side in ("train", "test") and tasks, "Qualify a nonempty training or test side")
    require(runtime.get("spreadsheet_scorer") == SCORER, "The frozen v7 scorer is required")
    root = safe_path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError:
        raise ValueError("A qualification runs in a new directory") from None
    jobs = [(task, scoring) for task in tasks for scoring in range(PASSES)]

    def score(job):
        task, scoring = job
        request = {"benchmark": "spreadsheetbench", "qualification": side, "task_id": task["task_id"],
                   "scoring": scoring}
        position = digest(request)
        prediction = reference_prediction(task)
        context = {"artifact_dir": str(root / "host_only" / "scorer_artifacts" / position), "position": position,
                   "request": request, "prediction_hash": digest(prediction)}
        with native.hold():
            result = backends.score("spreadsheetbench", task["public"], task["private"], prediction,
                                    runtime={**deepcopy(runtime), "_score_context": context})
        write_json(root / "scores" / (position + ".json"),
                   record(SCORE_KIND, evidence, {"task_id": task["task_id"], "scoring": scoring, "score": result}))
        _check(result, "%s/%s" % (task["task_id"], scoring))
        return result

    results = run_parallel(score, jobs, workers=workers)
    by_task = {}
    for (task, scoring), result in zip(jobs, results):
        by_task.setdefault(task["task_id"], [None] * PASSES)[scoring] = result
    qualified, excluded = [], {}
    for task_id, scores in sorted(by_task.items()):
        failing = [s for s in scores if not _passed(s)]
        if failing:
            excluded[task_id] = category(_first_failure(failing[0]))
        else:
            qualified.append(task_id)
    value = record(KIND, evidence, {
        "side": side, "tasks": len(by_task), "qualified": qualified, "excluded": excluded,
        "counts": {name: sum(c == name for c in excluded.values()) for name in CATEGORIES},
        "scorings_per_item": PASSES, "model_calls": 0, "scorer": runtime["spreadsheet_scorer"],
        "recalculation": runtime["recalculation"], "task_hashes": {t["task_id"]: digest(t) for t in tasks}})
    write_json(root / "qualification.json", value)
    return value


def record_digest(value):
    """The record's own hash: ``record_sha256`` for this protocol's records, ``record_hash`` for an imported v3 one."""
    return value[RECORD_HASH] if RECORD_HASH in value else value[V3_HASH]


def load(path, *, importable=IMPORTABLE):
    """A sealed qualification record: this protocol's own, or a v3 record whose version is listed in ``importable``
    (registration §1, owner #7, Codex F15). Its hash is verified; it made no model call."""
    value = read_json(path)
    require(isinstance(value, dict), "Not a qualification record")
    version = value.get("version")
    if version == kind(KIND):
        value = verified(value, KIND)
    else:
        require(version in tuple(importable), "Not an importable qualification record: %s" % (version,))
        value = verify(value, field=V3_HASH)
    require(value["model_calls"] == 0 and value["side"] in ("train", "test")
            and value["scorings_per_item"] == PASSES, "Not a zero-call qualification record")
    require(set(value["qualified"]).isdisjoint(value["excluded"])
            and set(value["qualified"]) | set(value["excluded"]) == set(value["task_hashes"]),
            "A qualification record lists every item once")
    return value


def reverify(value, *, pinned, tasks=None):
    """The zero-call re-check before launch (§1, §10 S0): the record's hash is intact and equals ``pinned`` (the hash
    the manifest pins); given ``tasks``, their content hashes equal the record's. Raises ValueError otherwise."""
    payload = {k: v for k, v in value.items() if k not in (RECORD_HASH, V3_HASH)}
    found = record_digest(value)
    require(found == digest(payload), "The qualification record's hash does not match its content")
    require(found == pinned, "The qualification record is not the pinned one")
    if tasks is not None:
        require({t["task_id"]: digest(t) for t in tasks} == value["task_hashes"],
                "The qualification belongs to other items")


def summary(value):
    """Counts only (no item content): what the manifest and the reports state (frozen qualify.py:141-144)."""
    return {"side": value["side"], "items": value["tasks"], "qualified": len(value["qualified"]),
            "excluded": dict(Counter(value["excluded"].values()))}


# ------------------------------------------------------------------------- the recalculation engine (C7b1-3)
def revalidate(runtime):
    """The frozen offline revalidation of a SpreadsheetBench runtime's v7 engine qualification
    (``sheet_numeric_adapter.qualified_engine``: the record and its file hash, its protocol, every control receipt and
    judgment, and the engine identity of THIS checkout; zero model calls, Calc is never run). Returns the qualified
    record's ``record_hash``; raises ValueError naming the frozen refusal otherwise."""
    from skillopt.continual_eval.sheet_numeric_adapter import qualified_engine

    try:
        _, qualified = qualified_engine(runtime)
    except (OSError, ValueError, KeyError, TypeError) as error:  # the frozen readiness() catches the same four
        raise ValueError("The SpreadsheetBench engine qualification does not revalidate from this checkout (ticket "
                         "C7b1-3): %s: %s" % (type(error).__name__, error)) from None
    return qualified[V3_HASH]


def _engine_record(path):
    """(absolute path, record) of a sealed, qualified v7 engine qualification (``replay_sheet_v6 qualify``)."""
    path = safe_path(path)
    require(path.is_file(), "No engine qualification at %s" % path)
    value = read_json(path, sealed=True)
    engine = value.get("engine")
    require(value.get("status") == "qualified" and value.get("engine_profile") == ENGINE_PROFILE
            and value.get("model_api_calls") == 0 and isinstance(engine, dict)
            and isinstance(engine.get("sources"), dict) and engine["sources"],
            "Not a qualified zero-call v7 engine qualification: %s" % path)
    return path, value


def engine_runtime(base_runtime, qualification_path, *, check=None):
    """The execskill SpreadsheetBench runtime (ticket C7b1-3): ``base_runtime`` -- the v3 manifest's
    ``runtime.spreadsheetbench`` -- with ONLY ``recalculation.{qualification_path, qualification_sha256,
    qualification_hash}`` replaced by the v7 engine qualification at ``qualification_path`` (its absolute path, the
    file's sha256, the sealed record's ``record_hash``); the image, the timeout and every other field are kept (the
    record's engine must be of that image and timeout). Then ``check(runtime)`` -- by default ``revalidate``, the
    frozen offline ``qualified_engine`` (zero model calls) -- so a stale block fails here, not as every cell scored
    unknown. Returns the checked runtime (a new dict)."""
    require(isinstance(base_runtime, dict) and base_runtime.get("spreadsheet_scorer") == SCORER
            and isinstance(base_runtime.get("recalculation"), dict)
            and set(REPLACED) <= set(base_runtime["recalculation"]),
            "The v3 SpreadsheetBench runtime with the frozen v7 scorer")
    path, value = _engine_record(qualification_path)
    old = base_runtime["recalculation"]
    require(value["engine"].get("image_id") == old.get("image")
            and value["engine"].get("timeout_seconds") == old.get("timeout_seconds"),
            "The engine qualification is not of the runtime's image and timeout")
    runtime = deepcopy(base_runtime)
    runtime["recalculation"] = {**deepcopy(old), "qualification_path": str(path),
                                "qualification_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "qualification_hash": value[V3_HASH]}
    (check or revalidate)(runtime)
    return runtime


def snapshot_root(sources):
    """The snapshot root of an engine identity's ``sources`` ({absolute path: sha256}): the directory holding the
    ``skillopt`` package the scorer modules were loaded from (the last ``skillopt`` component of their common
    directory)."""
    require(isinstance(sources, dict) and sources
            and all(isinstance(p, str) and PurePosixPath(p).is_absolute() for p in sources),
            "Engine sources are keyed by absolute path")
    parts = PurePosixPath(os.path.commonpath(list(sources))).parts
    found = [n for n, part in enumerate(parts) if part == PACKAGE]
    require(found, "The engine sources are not modules of the %s package" % PACKAGE)
    return PurePosixPath(*parts[:found[-1]])


def _relative(sources):
    root = snapshot_root(sources)
    found = {PurePosixPath(p).relative_to(root).as_posix(): sha for p, sha in sources.items()}
    require(len(found) == len(sources), "Two engine sources share a relative path")
    return root, found


def same_engine_sources(new_qualification_path, old_qualification_path):
    """Whether two v7 engine qualifications name one engine wherever its sources lie (ticket C7b1-3; zero calls; both
    records' seals verified): every non-source field of their ``engine`` identities equal (version, image_id,
    timeout, memory, cpus, pids, network, ..., comparison_view) and ``sources`` equal as {path relative to each
    identity's own snapshot root: sha256}. Returns {"same", "fields": {"compared", "differing"}, "sources": {"new",
    "old", "equal", "differing"}, "roots": {"new", "old"}}; "differing" lists field names and relative paths."""
    new = _engine_record(new_qualification_path)[1]["engine"]
    old = _engine_record(old_qualification_path)[1]["engine"]
    names = sorted((set(new) | set(old)) - {"sources"})
    fields = [name for name in names if name not in new or name not in old or new[name] != old[name]]
    new_root, new_sources = _relative(new["sources"])
    old_root, old_sources = _relative(old["sources"])
    paths = sorted(set(new_sources) | set(old_sources))
    differing = [p for p in paths if p not in new_sources or p not in old_sources or new_sources[p] != old_sources[p]]
    return {"same": not fields and not differing, "fields": {"compared": len(names), "differing": fields},
            "sources": {"new": len(new_sources), "old": len(old_sources), "equal": len(paths) - len(differing),
                        "differing": differing},
            "roots": {"new": str(new_root), "old": str(old_root)}}
