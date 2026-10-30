"""The multi-arm test read (protocol ``fivebench-execskill-v1``; registration §8.1, §9.3, §11; Codex F16, F17;
implementation plan §1 evaluation row, §2.10, T-EVAL-1..5): a copy of ``coevo5.evaluation`` (evaluation.py:43-450)
with the route-B arms, the hash-only persistence and the new unseal order.

Copied: one benchmark's read is one unit; one process owns it (``.lock``); an attempt runs in its own numbered directory
and an attempt after a pause needs the owner's ``recovery.json`` (``attempts``/``_next_attempt`` imported, as units.py
does); whatever the process writes to stdout or stderr goes to the sealed diagnostics file (``contained``, imported
unchanged with its process-wide state); the test panel's hash is registered by the first read and must be found again
(``_registry``, evaluation.py:190-199); SpreadsheetBench reads only its reference-qualified test items, qualified once
for all chains (evaluation.py:202-224, through ``execskill.qualify``); a unit whose cells are more than 10 %
infrastructure-unknown pauses (evaluation.py:391-395); anything escaping is replaced by a fresh exception without
context (evaluation.py:262-305). What changes:

- consent (§8.1): ``shared/consent.json`` with exactly ``CONSENT_FIELDS`` = {test_evaluation, sheet_test_qualification,
  multi_arm_arms, by, date, note}, ``multi_arm_arms`` naming exactly ``TEST_ARMS``; any other key set is refused
  (evaluation.py:43, :152-159);
- arms (§8.1): F (the final package), C (the card arm: the empty package), P_F (F with every procedure shammed from the
  sealed donor corpus), T_F (the frozen descriptions, ``solver.solve(text=)``) and the withholding twins F∖p; one run
  per item (``TEST_RUNS``); every arm's cells of the unit in one seeded interleaved order;
- the plan (``test_plan``, zero model calls): F routed on every item's routing view; an item on which F enables nothing
  is a structural zero -- F, P_F, T_F share its C cell (``cells.share_cell``), nothing is sent; on the others each
  enabled procedure is withheld on a seeded half of its items, at most ``MAX_TWINS_PER_ITEM`` per item, by enable
  count (``router.draw_twins``, §6.5's cap), seeded by ``"test/<bench>"`` without the chain, so chains G and D
  withhold the same halves on the same items (registrar decision 2026-10-22; acceptance twins stay per chain and
  unit); F = C (nothing accepted) is not read at all;
- ALFWorld test games carry only ``{game_file}`` (datasets.py:27-35): their routing view is made inside this unit by
  one zero-call reset of the frozen environment per game (``alfworld_reset``), kept in memory only, and the solver's
  live reset re-checks its hash; each game's room (``supply.task_folder``) rides in its cells for the room-clustered
  readouts (§6.4; isolation review 2, statistics review 7);
- SpreadsheetBench routing and placebo-length replay (Codex finding #1 of 2026-10-22; §2.5-§2.6, §8.1): the read binds
  a read-local map of each test item to its PUBLIC input workbook (``public_inputs``: the frozen public view's first
  input file, never a workbook the private record names) and every routing worker of ``test_plan`` and every
  placebo-length worker of ``placebo_arm`` mounts it read-only as /input/input.xlsx in an isolated directory removed
  afterwards (``mounting``), exactly as training mounts it (``step._item_workers``); the cells mount it themselves
  (``solver._solve_sheet``). Without it a valid ``applies()`` reading ``public_workbook()`` would fault in the plan, the
  item would become a structural zero and F/P_F/T_F would silently share C's result;
- persistence (Codex F16): ``EvaluationStore`` keeps raw predictions, scores, scorer directories (under
  ``transient/host_only/scorer_artifacts``: the frozen v7 adapter requires a ``host_only`` grandparent,
  sheet_recalc_adapter.py:73-75) and full cell records under ``<attempt>/transient/`` only; the sealed cell records
  (``fivebench-execskill-v1-evaluation-cell``) hold the request and reply hashes, the visible completion tokens, the
  judge's tokens and flags and the fault kinds -- no text; the transient store is deleted once every cell is scored
  (re-execution included: it happens inside the cell) and on every pause, and the deletion manifest's hash is
  recorded; a transient store left by a killed process is deleted, with its record, before the next attempt starts;
  the test-side SpreadsheetBench qualification keeps no scorer artifact: on EVERY exit of its attempt (complete,
  pause, exception, interrupt), once its scoring workers have drained, everything but the sanitized results
  (``QUALIFICATION_KEPT``: the sealed record, status, the owner's recovery decision, the score records of statuses,
  reasons and hashes, the deletion records) is deleted -- the recalculated reference workbooks under ``host_only/``
  included -- with a deletion record (file count, manifest hash); an attempt a killed process left is swept the same
  way before any later qualification or retry, and no kept file may be a workbook (Codex finding #3 of 2026-10-22;
  §8.1/F16, registrar fixer-1); the copied evaluation never calls the training persistence
  (cells.py:97/:187/:224 → ``TrainingStore``);
- canaries (Codex F16; registrar decisions C3-1 (b), PR-C31-3): the registered test-content canaries (``canary``: a
  length and a sha256 prefix, never the text) are the S0 exclusion unit's sealed record (``shared/test-canaries.json``:
  SearchQA and ALFWorld) merged with a second sealed record (``shared/test-read-canaries.json``: OfficeQA, LiveMath and
  SpreadsheetBench; ``load_canaries``) that the pilot's first read unit makes once, under the owner's test-read consent
  and before its attempt (``make_read_canaries``, with the S0 selection ``select_canaries``), skipping every test text
  that occurs verbatim in the same public field of one of the bench's training-side pool items (the pools the
  manifest pins in ``data.pools``, read when the record is made; ``training_duplicates``: counted, never kept); before
  a new attempt
  starts and on every exit (complete, pause, exception), every artifact of the unit (every attempt), the diagnostics
  and child logs (``shared/host_only/diagnostics``) and the test side's shared files (``shared/test``) are searched for
  them; a hit pauses the unit before ``unit.json``; a clean read writes ``canary_scan.json`` with ``hits: 0``;
- unseal (Codex F17, §8.1 "封存与解封顺序"): keyed by (arm, task_id, run); refused until EVERY chain of the run root is
  complete or terminated AND the owner's ``shared/owner-continuation.json`` exists; with ``continue`` the formal-chain
  addendum must have been sealed (``seal_addendum``: the document ``shared/formal-addendum.md``, its sha256 and the
  sealing time in the write-once record ``shared/formal-addendum.json``; the document is re-hashed at every unseal)
  before the unseal, else every later test read is labelled ``repeated_test_development`` (``read_label``); before the
  chain's first unseal the whole run root -- every unit of both chains, the research store, the generated sets -- is
  searched for every canary (``root_scan``, its files shared by a process pool, ``scan_workers``, with the
  one-process result; one attempt under ``<chain root>/root-scan``, its sealed ``scan.json``) and a hit pauses for the
  owner before any score is read (registrar decision C3-1 (b)) -- unless the owner's ``recovery.json`` in the paused
  attempt releases exactly that scan (``release <its record_sha256>``, ``release_check``) and the next scan finds the
  same hits: the unseal marker names the release; nothing is released otherwise (registrar decision PR-C31-3);
- the child entry (``run_unit_spec``, ticket A13-1): one unit from the verified manifest, its arms built from the
  chain's records -- F the final package, C the empty card package, P_F F shammed from the sealed donor corpora of the
  rounds that accepted its procedures (``placebo_arm``), T_F the frozen descriptions of the chain's freeze units
  (``frozen_texts``) -- with the unit's tag on every container and the unit drained before ``unit.json`` (ticket
  C5-1);
- v2 stage reads (``protocol.STAGE_READ``, main-v2; owner decision 2026-10-23 16:0x): the unit also runs the stage
  arms "S<k>", the packages earlier steps passed on (``stage_rows``, from the chain's sealed step records), in the
  same seeded interleaved order; each is routed on every item with zero calls (``stage_plan``) and a stage cell sends
  nothing where its enabled procedures are those a cell of the unit runs with -- none (C's cell, ``share_cell``), F's
  or an earlier stage arm's (``cells.share_same``: the same request); where the source cell did not run with the
  planned procedures, or recorded a fault, the stage cell runs after the blocks (``fallback``); F's routing of an item
  is reused only where none of the stage package's procedures faulted in it (Codex stage review #1, #2). The unit
  record of every stage read names the rows of the stage table (``stages``; rows of C and F alone run no stage arm)
  and counts the stage cells sent and shared; the consent names the stage arms (``consent``, checked in the unit
  before its attempt opens: Codex stage review #3, #4).
"""
from __future__ import annotations

import functools
from . import profiles
import hashlib
import html
import io
import itertools
import json
import multiprocessing
import os
import re
import shutil
import threading
import time
import traceback
import zipfile
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from skillopt.coevo5 import data
from skillopt.coevo5.cells import _claim, exclusive
from skillopt.coevo5.evaluation import ContainmentFailure, _next_attempt, attempts, contained, recovered
from skillopt.coevo5.outcomes import INFRASTRUCTURE, UNCLASSIFIED, UNKNOWN, public
from skillopt.coevo5.step import answered
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import budgets, describer, donors, placebo, qualify, router, solver, units
from .cells import Arm, Pause, cell_id, run_cells, share_cell, share_same
from .chain import EXIT_AWAITING, EXIT_COMPLETE, EXIT_PAUSED, unit_root as read_root
from .errors import CleanupUnconfirmed, stop_kind
from .manifest import setting_of
from .package import Package, empty, load
from .profiles import (BENCHES, SUPPORTED_BENCHES, ZEBRA_PC_V1, is_zebra, is_alfworld, read_benches, CANARIES, CHAINS, CONFIGURATIONS, CONSENT_FIELDS, FORMAL_ADDENDUM,
                       FORMAL_ADDENDUM_DOCUMENT, INFRA_UNKNOWN_MAX, OFFICEQA_TEST_BLOCKS, ORDER, OWNER_CONTINUATION,
                       RECORD_HASH, STAGE_ARM, STAGE_READ, TEST_RUNS, configuration_of, discourage_tag, ledger_bound,
                       order_of, read_arms_of, record, round_tag, verified)
from .sandbox import client as sandbox
from .rounds import _order
from .supply import routing_view as alfworld_routing_view
from .supply import task_folder

__all__ = ("ARMS", "EvaluationStore", "LABELS", "alfworld_reset", "attempts", "canary", "canary_scan", "consent",
           "continuation", "continuation_check", "donor_corpora", "evaluate", "frozen_texts", "load_canaries",
           "make_read_canaries", "monitor", "mounting", "placebo_arm", "public_inputs", "read_label", "release_check",
           "root_scan", "run_unit_spec", "scan_workers", "seal_addendum", "sealed_cell", "select_canaries",
           "stage_plan", "stage_rows", "test_plan", "test_tasks", "training_duplicates", "twin_unit", "unit_scan",
           "unseal")

ARMS = ("F", "C", "P_F", "T_F")  # the arms the caller builds; the twins F\p are the plan's (§8.1)
ARM_KINDS = {"F": "candidate", "C": "card", "P_F": "placebo_y", "T_F": "text", "B": "blank"}
TWIN = "withhold:"
STAGE_LABEL = re.compile(r"%s([1-9][0-9]*)" % STAGE_ARM)  # a stage arm "S<k>" (protocol.STAGE_ARM)
SHEET_QUALIFICATION = "spreadsheetbench-qualification"
# Codex finding #3 of 2026-10-22 (§8.1/F16; registrar fixer-1): what a test-side qualification attempt keeps -- the
# sealed record, its status, the owner's recovery decision, the score records (statuses, reasons, hashes; never a
# workbook) and its deletion records: the exit's, and a later sweep's for an attempt a killed process left
QUALIFICATION_DELETED = "scorer-artifacts-deleted.json"
QUALIFICATION_SWEPT = "scorer-artifacts-swept.json"
QUALIFICATION_KEPT = frozenset({"qualification.json", "status.json", "recovery.json", "scores", QUALIFICATION_DELETED,
                                QUALIFICATION_SWEPT})
WORKBOOK_MAGIC = b"PK\x03\x04"  # a workbook is a zip archive
TRANSIENT = "transient"
CONTINUATION_FIELDS = frozenset({"by", "date", "decision", "note"})
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
SHA256 = re.compile(r"[0-9a-f]{64}")
CANARY_HEX = 16  # the stored sha256 prefix of a canary
CANARY_BYTES = CANARY_HEX // 2
MIN_CANARY_CHARS = 24
# §8.1 "每个测试集固定抽几段原文" (Codex F16; tickets fixer-4, C3-1): the S0 exclusion unit's canary selection
# (scripts/run_execskill.py make_canaries), the test read's as well
CANARIES_PER_BENCH = 5
CANARY_TAG = "execskill-v1:canaries:"
# registrar decision C3-1 (b), implementation-time registration: the test read's second canary record (run-root
# relative), the TestAccess it is made under and the public field each of its three test sets gives
READ_CANARIES = "shared/test-read-canaries.json"
READ_CANARY_UNIT = "test-read/canaries"
READ_CANARY_SOURCES = {"livemath": "question", "officeqa": "question", "spreadsheetbench": "instruction"}
ROOT_SCAN = "root-scan"  # <chain root>/root-scan/attempt-N: the run-root scan before the chain's first unseal
ROOT_SCAN_SHOWN = 200  # the hits a scan record lists (every hit is counted)
DECODE_DEPTH = 3  # JSON documents inside JSON strings (a stored request) are read this many levels deep
CACHE_MIN_CHARS = 256  # a scan hashes a text this long once; a shorter one is cheap to hash again
# registrar decision PR-C31-3 (addendum 2026-10-22 14:1x), implementation-time registrations: (1b) the owner's release
# of one paused run-root scan is the decision of its recovery.json naming that scan's record hash; (3) the scan's
# process pool over files (5 processes on dl's 7 CPUs; 2.7x measured, notes/P2-A3.md) leaves CPUs to a running chain
RELEASE = re.compile(r"release ([0-9a-f]{64})")
ROOT_SCAN_WORKERS = 5
ROOT_SCAN_SPARE_CPUS = 2
ROOT_SCAN_POOL_BYTES = 1 << 20  # a smaller root is scanned in this process (starting the workers would cost more)
ROOT_SCAN_SHARES = 8  # contiguous runs of files per worker: load balance, and a unit's repeated texts stay together
UNSEALED = "unsealed.json"
SPEC_FIELDS = frozenset({"chain", "bench", "package_sha256", "unit_root"})  # ``chain.launch_child``'s spec
# §8.1 (Codex F17): the pilot read's label and the label every later read inherits
LABELS = {"continue_on_time": ("interim_read_addendum_before_unseal", "confirmatory"),
          "continue_late": ("interim_read_without_prior_addendum", "repeated_test_development"),
          "stop": ("read_after_stop_decision", "repeated_test_development")}


# ---------------------------------------------------------------------------------------------- consent (§8.1)
def consent(shared, configuration=None):
    """The owner's recorded consent to the multi-arm test read (``shared/consent.json``; exact key set):
    ``multi_arm_arms`` names exactly the read arms of a run configuration (``protocol.read_arms_of``: ``TEST_ARMS``,
    with "stages" in a stage-read configuration); with ``configuration``, exactly that configuration's -- the chain's
    read gate (``chain.read_consent``) and the read unit (``run_unit_spec``) check it so, and a stage read never runs
    under a consent that does not name its stage arms."""
    path = safe_path(shared) / "consent.json"
    require(path.exists(), "No recorded owner consent to evaluate on the test sets")
    value = read_json(path)
    allowed = [read_arms_of(configuration)] if configuration is not None else sorted(
        {read_arms_of(name) for name in CONFIGURATIONS if not profiles.is_zebra_fc(name)})
    arms = value.get("multi_arm_arms") if isinstance(value, dict) else None
    require(isinstance(value, dict) and set(value) == CONSENT_FIELDS and value["by"] == "owner"
            and value["test_evaluation"] is True and type(value["sheet_test_qualification"]) is bool
            and isinstance(arms, list) and all(type(arm) is str for arm in arms)
            and any(len(arms) == len(found) and set(arms) == set(found) for found in allowed)
            and isinstance(value["date"], str) and isinstance(value["note"], str) and value["note"].strip(),
            "No recorded owner consent to the multi-arm test read")
    if profiles.is_zebra_fc(configuration):
        require(value["sheet_test_qualification"] is False, "Zebra read consent does not qualify sheet test data")
    if profiles.is_v214(configuration):
        require(value["sheet_test_qualification"] is True,
                "main-v5 read consent includes SpreadsheetBench test qualification")
    return value


# ------------------------------------------------------------------------------------------- the test items
def _registry(shared, bench, entry, evidence):
    """Write-once registry of the test panel a bench is read on (evaluation.py:190-199)."""
    base = safe_path(shared) / "test"
    path = base / ("%s.json" % bench)
    with exclusive(base / ("%s.lock" % bench), wait=True):
        if path.exists():
            require(verified(read_json(path), "test-panel")["entry"] == entry,
                    "The test panel differs from the first evaluation's")
        else:
            write_json(path, record("test-panel", evidence, {"entry": entry}))


def _sheet_qualification(shared, tasks, runtime, *, allowed, native, workers, evidence):
    """The test-side reference qualification, once for all chains (evaluation.py:202-224), stamped by
    ``execskill.qualify``; a paused attempt needs the owner's recorded decision. Codex finding #3 of 2026-10-22: under
    the lock, every earlier attempt's leftovers are swept first (``_swept_qualifications``: an attempt a killed
    process left), and the attempt's own artifacts go on every exit (``_qualification_cleaned``)."""
    base = safe_path(shared) / "test"
    pointer, root = base / (SHEET_QUALIFICATION + ".json"), base / SHEET_QUALIFICATION
    with exclusive(base / (SHEET_QUALIFICATION + ".lock"), wait=True):
        _swept_qualifications(root, evidence)
        if not pointer.exists():
            require(allowed["sheet_test_qualification"] is True, "No owner consent to qualify the test references")
            attempt = _next_attempt(root)
            if attempt is None:
                raise Pause("qualification_paused", attempts(root)[-1].name, SHEET_QUALIFICATION)
            when = "interrupted"  # a BaseException (an interrupt) leaves this label
            try:
                found = qualify.qualify(tasks, attempt, runtime, side="test", native=native, workers=workers,
                                        evidence=evidence)
                when = "complete"
            except Pause as pause:
                when = "paused"
                write_json(attempt / "status.json", record("unit-status", evidence, {
                    "status": "paused", "kind": pause.kind, "reason": pause.reason, "cell": pause.cell}))
                raise
            except Exception as error:  # a configuration check or a crash: the attempt pauses, its type alone kept
                when = "exception"
                if attempt.is_dir():
                    write_json(attempt / "status.json", record("unit-status", evidence, {
                        "status": "paused", "kind": "configuration" if isinstance(error, ValueError) else "exception",
                        "reason": type(error).__name__, "cell": None}))
                raise
            finally:
                # isolation review 10, Codex finding #3: the scorer artifacts hold the recalculated test reference
                # workbooks (sheet_recalc.py:579-593); only the sanitized results are read again, so they go on every
                # exit -- after qualify's workers drained: ``run_parallel`` joins every started scoring before it
                # returns or raises
                _qualification_cleaned(attempt, evidence, when)
            write_json(pointer, record("test-qualification-pointer", evidence, {
                "attempt": attempt.name, "qualification_sha256": qualify.record_digest(found)}))
        link = verified(read_json(pointer), "test-qualification-pointer")
        found = qualify.load(root / link["attempt"] / "qualification.json")
        require(qualify.record_digest(found) == link["qualification_sha256"], "The test qualification changed")
    return found


def _swept_qualifications(root, evidence):
    """Codex finding #3 of 2026-10-22: before any test qualification or its retry (``_sheet_qualification``, under its
    lock, so no live process is inside an attempt), each earlier attempt's leftovers -- an attempt a killed process
    left, or whose exit cleanup failed -- are deleted with a record (``_qualification_cleaned`` ``swept``); returns the
    names of the attempts swept."""
    return [earlier.name for earlier in attempts(root) if _qualification_cleaned(earlier, evidence, "swept")]


def _qualification_cleaned(attempt, evidence, when):
    """Codex finding #3 of 2026-10-22 (§8.1/F16; isolation review 10; registrar fixer-1): delete every entry of a
    test-side qualification attempt but its sanitized results (``QUALIFICATION_KEPT``; the scorer artifacts under
    ``host_only/`` hold the recalculated reference workbooks) and write the deletion record once
    (``transient-deletion``: the file count and manifest hash of ``_delete_entries``, the deleted entries' names,
    ``when``): at the attempt's exit (``QUALIFICATION_DELETED``; ``when`` complete, paused, exception or interrupted --
    written even when nothing was left) or at a later sweep (``QUALIFICATION_SWEPT``, ``when`` swept; only when
    something was left). Then no kept file may be a workbook. Returns the record, or None (no attempt directory; a
    sweep with nothing to delete)."""
    attempt = safe_path(attempt)
    if not attempt.is_dir():
        return None
    left = sorted(entry.name for entry in attempt.iterdir() if entry.name not in QUALIFICATION_KEPT)
    if when == "swept" and not left:
        return None
    path = attempt / (QUALIFICATION_SWEPT if when == "swept" else QUALIFICATION_DELETED)
    require(not path.exists(), "A test qualification attempt's artifacts are deleted once")
    value = record("transient-deletion", evidence, {**_delete_entries(attempt, left), "entries": left, "when": when})
    write_json(path, value)
    require(not any(_holds_workbook(p) for p in attempt.rglob("*") if p.is_file()),
            "A test qualification keeps sanitized results only, never a workbook")
    return value


def _holds_workbook(path):
    with open(path, "rb") as handle:
        return handle.read(len(WORKBOOK_MAGIC)) == WORKBOOK_MAGIC


def _delete_entries(base, names):
    """Delete the entries ``names`` of ``base`` (files, links or folders) and return their deletion manifest's fields as
    ``_delete_tree`` does: the file count and the sha256 of the [{path, sha256}] list -- paths relative to ``base``, a
    link hashed by its target text, never content."""
    files = []
    for name in sorted(names):
        entry = base / name
        found = [entry] if entry.is_symlink() or not entry.is_dir() else sorted(
            p for p in entry.rglob("*") if p.is_symlink() or p.is_file())
        for path in found:
            content = ("link:" + os.readlink(path)).encode("utf-8") if path.is_symlink() else path.read_bytes()
            files.append({"path": str(path.relative_to(base)), "sha256": hashlib.sha256(content).hexdigest()})
    for name in names:
        entry = base / name
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        require(not entry.exists() and not entry.is_symlink(), "A test qualification artifact could not be deleted")
    return {"files": len(files), "manifest_sha256": digest(files)}


def test_tasks(shared, pinned, bench, unit, *, run, runtime, native, workers, evidence, panel=data.test_panel,
               configuration=None):
    """The tasks a bench is read on (the evaluation unit only; evaluation.py:227-247). ``panel``: the frozen
    ``data.test_panel`` (a unit test passes a synthetic one)."""
    allowed = consent(shared, configuration)
    if bench == "zebralogic" and panel is data.test_panel:
        from .zebralogic import test_panel as panel
        if profiles.is_v214(configuration):
            require(isinstance(pinned, dict) and bench in pinned, "main-v5 pins its sealed Zebra panel separately")
            pinned = pinned[bench]
    tasks, report = panel(pinned, bench, access=data.TestAccess(unit))
    entry = {"run": run, "benchmark": bench, "panel_hash": report["panel_hash"],
             "tasks": sorted(t["task_id"] for t in tasks), "excluded_without_pages": report["excluded_without_pages"],
             "source_files": report["source_files"]}
    _registry(shared, bench, entry, evidence)
    if bench != "spreadsheetbench":
        return tasks
    found = _sheet_qualification(shared, tasks, runtime, allowed=allowed, native=native, workers=workers,
                                 evidence=evidence)
    require(found["side"] == "test" and found["task_hashes"] == {t["task_id"]: digest(t) for t in tasks},
            "The test qualification belongs to other items")
    if not found["qualified"]:
        raise Pause("no_qualified_test_items", "spreadsheetbench", unit)
    keep = set(found["qualified"])
    return [t for t in tasks if t["task_id"] in keep]


def prepare_test_qualification(setting, chain, *, panel=data.test_panel, pinned=None):
    """main-v5's root-wide prerequisite, before any test unit starts (zero solver calls).

    Both chains enter the same locked, idempotent qualification and wait for its cleanup. The normal sheet unit
    subsequently verifies that same pointer; it cannot create a competing qualification. Direct unit launches use
    this prerequisite too. Only sanitized qualification records survive the containment boundary.
    """
    configuration = configuration_of(setting)
    require(profiles.is_v214(configuration), "The qualification prerequisite belongs to main-v5")
    consent(setting.shared, configuration)
    base = safe_path(setting.shared) / "test"
    pointer = base / (SHEET_QUALIFICATION + ".json")
    if pointer.exists():
        link = verified(read_json(pointer), "test-qualification-pointer")
        found = qualify.load(base / SHEET_QUALIFICATION / link["attempt"] / "qualification.json")
        require(qualify.record_digest(found) == link["qualification_sha256"] and found["side"] == "test",
                "The shared test qualification prerequisite changed")
        if not found["qualified"]:
            raise Pause("no_qualified_test_items", "spreadsheetbench", SHEET_QUALIFICATION)
        return
    from .slots import NATIVE
    manifest = setting.extra.get("manifest")
    if pinned is None and manifest is not None:
        manifest = manifest if isinstance(manifest, dict) else read_json(safe_path(manifest))
        pinned = manifest.get("data", {}).get("pinned")
    with contained(setting.shared):
        test_tasks(setting.shared, pinned, "spreadsheetbench", "%s/test/qualification" % chain,
                   run=setting.run, runtime=setting.runtime["spreadsheetbench"], native=setting.slots[NATIVE],
                   workers=setting.workers, evidence=setting.evidence, panel=panel, configuration=configuration)


# ------------------------------------------------------------------------------------------------- the plan
def alfworld_reset(runtime, episodes):
    """The production reset that makes an ALFWorld test game's routing view (zero model calls): one reset of the
    frozen session (``backends._new_alfworld``) under an episode slot, closed at once; ``reset(public) -> (initial
    observation, admissible commands)``."""
    from skillopt.continual_eval import backends

    def reset(public):
        with episodes.hold():
            env = backends._new_alfworld({"game_file": public["game_file"]}, runtime)
            try:
                observations, _, infos = env.reset()
            finally:
                env.close()
        return str(observations[0]), list(infos[0].get("admissible_commands", []))

    return reset


def _with_views(tasks, bench, reset):
    """The tasks a read routes on: on ALFWorld each frozen-shaped test game (public ``{game_file}`` only) gets its
    routing view from ``reset`` here, in memory only (isolation review 2); the solver's live reset re-checks the hash."""
    if bench != "alfworld":
        return list(tasks)
    require(reset is not None, "An ALFWorld read makes its routing views with a reset")
    out = []
    for task in tasks:
        public = task["public"]
        require("routing_view" not in public and "routing_view_sha256" not in public,
                "A test game's routing view is made inside the read")
        view = alfworld_routing_view(*reset(public))
        out.append({**task, "public": {**public, "routing_view": view, "routing_view_sha256": digest(view)}})
    return out


def twin_unit(bench):
    """The seed unit of the test read's withholding twins: ``"test/<bench>"``, the chain dropped (registrar decision
    2026-10-22), so chains G and D withhold the same seeded halves on the same items."""
    require(bench in SUPPORTED_BENCHES, "Unknown bench")
    return "test/%s" % bench


def public_inputs(bench, tasks):
    """Codex finding #1 of 2026-10-22 (§2.5-§2.6, §8.1): the read-local map {item: its PUBLIC input workbook} of a
    SpreadsheetBench read -- the first input file of the frozen public view (``_public_view``: the public keys only),
    the workbook training mounts (``step._sheet_inputs``) -- and {} on the other benches. ``tasks``: {item: task}. A
    workbook the item's private record names (its reference/answer workbooks, ``test_files``) is refused, so it is never
    mounted (the frozen loader's own rule, datasets.py:151, checked again on the paths; no workbook is opened here)."""
    if bench != "spreadsheetbench":
        return {}
    found = {}
    for item, task in tasks.items():
        files = solver._public_view(bench, task["public"])["input_files"]
        require(files, "A SpreadsheetBench item has a public workbook")
        hidden = [str(p) for p in (task.get("private") or {}).get("test_files") or ()]
        require(not {files[0], os.path.realpath(files[0])} & {*hidden, *map(os.path.realpath, hidden)},
                "A reference workbook is never mounted as a public input")
        found[item] = files[0]
    return found


def mounting(workers, inputs):
    """Codex finding #1 of 2026-10-22: ``workers(package, item)`` mounting a mapped item's public workbook (``inputs``:
    ``public_inputs``) as the worker's read-only /input, exactly as training does (``step._item_workers`` with
    ``step._sheet_inputs``): a fresh directory holding that workbook alone as ``input.xlsx`` (``solver._inputs_dir``;
    the sandbox refuses any other entry, client.py ``Worker.start``), handed to ``workers(package, item,
    inputs_dir=)`` and removed once the worker is closed. Without a map (the other benches) ``workers`` itself; on a
    SpreadsheetBench read every item is mapped."""
    if not inputs:
        return workers

    @contextmanager
    def factory(package, item):
        require(item in inputs, "A SpreadsheetBench item of this read has its public workbook")
        directory = solver._inputs_dir(inputs[item])
        try:
            with workers(package, item, inputs_dir=directory) as worker:
                yield worker
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    return factory


def test_plan(tasks, final, *, bench, unit, runtime, workers, reset=None, run_configuration=None):
    """The read's zero-call plan (§8.1): {"tasks": the tasks with their routing views (ALFWorld: made by ``reset``,
    ``_with_views``), "routes": {item: RouteLog of F}, "zero": [items F enables nothing on], "twins": {item: [procedure
    ids withheld]}, "not_withheld": {...}, "sha256"}. ``workers(package, item)``: a context manager yielding a started
    sandbox worker holding ``package`` for ``item`` (router.plan's convention); on SpreadsheetBench it is called as
    ``workers(package, item, inputs_dir=)`` with the item's public workbook mounted (``mounting``, Codex finding #1).
    ``unit``: the chain's read unit ``<chain>/test/<bench>``; its twins are drawn under ``twin_unit(bench)``."""
    require(isinstance(final, Package) and bench in SUPPORTED_BENCHES, "Plan the read of a package on a known bench")
    require(isinstance(unit, str) and unit.partition("/")[0] in CHAINS and unit.partition("/")[2] == twin_unit(bench),
            "A chain's read unit <chain>/test/<bench>")
    tasks = _with_views(tasks, bench, reset)
    workers = mounting(workers, public_inputs(bench, {task["task_id"]: task for task in tasks}))
    routes = {}
    for task in tasks:
        view = solver.routing_view(bench, task["public"], runtime=runtime)
        if profiles.is_v210(run_configuration) and not final.for_bench(bench):
            routes[task["task_id"]] = router.route(final, bench, view, None)
        else:
            with workers(final, task["task_id"]) as worker:
                routes[task["task_id"]] = router.route(final, bench, view, worker)
    items = [t["task_id"] for t in tasks]
    firing = {p.id: [i for i in items if p.id in routes[i].enabled] for p in final.for_bench(bench)}
    priority = sorted((p for p in firing if firing[p]), key=lambda p: (-len(firing[p]), final.order.index(p)))
    twins, skipped = (router.draw_twins(firing, priority, {p: "withhold" for p in priority}, twin_unit(bench))
                      if profiles.TEST_WITHHOLDING.get(run_configuration, True) else ({}, {}))
    zero = [i for i in items if not routes[i].enabled]
    summary = {"package_sha256": final.sha256, "routes": {i: routes[i].sha256 for i in items}, "zero": zero,
               "twins": {i: [t["procedure"] for t in twins[i]] for i in sorted(twins)},
               "not_withheld": {i: skipped[i] for i in sorted(skipped)}}
    return {"tasks": tasks, "routes": routes, "zero": zero, "twins": summary["twins"],
            "not_withheld": summary["not_withheld"], "sha256": digest(summary)}


def stage_rows(chain_root, chain, order, final, start):
    """v2 stage reads (``protocol.STAGE_READ``; zero calls): ``{"rows", "packages"}`` of chain ``chain`` whose steps
    ran in ``order``: rows[k] (k = 0 .. len(order)) the label of the arm that reads the package after step k -- "C"
    where it holds no procedure (k = 0 always), "F" where it is ``final``, else "S<j>", j the first step that passed it
    on -- and packages {"S<j>": that package}. Each step's sealed ``step.json`` names the package it passed on (the
    chain's empty start ``start``, or one of its saved packages); the last is ``final``."""
    chain_root = safe_path(chain_root)
    rows, packages, first, sha = ["C"], {}, {}, None
    for k, bench in enumerate(order, 1):
        path = chain_root / ("s%d-%s" % (k, bench)) / "step.json"
        require(path.exists(), "Every step of the chain has finished before its read")
        step = verified(read_json(path), "step")
        require(step["chain"] == chain and step["k"] == k and step["bench"] == bench, "The record of step %d" % k)
        sha = step["package_sha256"]
        package = final if sha == final.sha256 else start if sha == start.sha256 else load(
            chain_root / "packages" / (sha + ".json"))
        require(package.sha256 == sha, "The package step %d passed on" % k)
        if not package.procedures:
            rows.append("C")
        elif sha == final.sha256:
            rows.append("F")
        else:
            label = first.setdefault(sha, "%s%d" % (STAGE_ARM, k))
            packages[label] = package
            rows.append(label)
    require(sha == final.sha256, "The last step passed on the final package")
    return {"rows": rows, "packages": packages}


def _signature(package, route):
    """The procedures a route enables, in order, as their hashes (byte-identical procedures send the same request)."""
    return tuple(package.get(pid).sha256 for pid in route.enabled)


def _derived(package, final, route):
    """The route of ``package`` on an item as the per-procedure entries of F's ``route`` there, when every procedure of
    ``package`` that may run on the bench is one of F's (the same id, byte-identical) and none of them faulted in F's
    routing of the item; else None. A predicate runs in a namespace of its own (sandbox worker.py), so its result
    depends only on its procedure and the routing view; a fault (a timeout, say) is no such result, so that item is
    routed in the stage package's own worker (Codex stage review #2)."""
    entries, own = route.per_procedure, {p.id: p.sha256 for p in final.for_bench(route.bench)}
    procedures = package.for_bench(route.bench)
    if not all(own.get(p.id) == p.sha256 for p in procedures) or any(entries[p.id]["fault"] is not None
                                                                     for p in procedures):
        return None
    ids = {p.id for p in procedures}
    return router.RouteLog(route.bench, package.sha256, route.routing_view_sha256,
                           {p.id: dict(entries[p.id]) for p in procedures},
                           tuple(dict(f) for f in route.faults if f.get("procedure") in ids), package.evidence)


def stage_plan(plan, final, packages, *, bench, runtime, workers):
    """v2 stage reads (zero calls): {"routes": {label: {item: RouteLog}}, "sources": {label: {item: source}},
    "derived": {label: the number of items whose route was taken from F's}, "sha256"} of the stage arms ``packages``
    ({"S<k>": package}) on the items of the read's plan ``plan`` (``test_plan``: its tasks' routing views and F's
    routes). A stage package whose procedures for the bench are all F's takes its route on an item from F's there
    (``_derived``: no worker starts) unless one of them faulted in F's routing of the item; every other item is routed
    in a worker of its own (``router.route``; ``workers`` as in ``test_plan``, mounting a SpreadsheetBench item's public
    workbook). An item's source, the stage arms in step order: "C" where the stage package enables nothing (the card
    arm's cell), "F" where it enables F's procedures (``_signature``), an earlier stage arm where it enables the
    procedures of that arm's running cell, else None (its cell runs)."""
    require(all(STAGE_LABEL.fullmatch(label) for label in packages), "Stage arms are S<k>")
    labels = sorted(packages, key=lambda label: int(label[len(STAGE_ARM):]))
    tasks = {t["task_id"]: t for t in plan["tasks"]}
    workers = mounting(workers, public_inputs(bench, tasks))
    routes, derived = {}, {}
    for label in labels:
        package = packages[label]
        found = {item: _derived(package, final, plan["routes"][item]) for item in sorted(tasks)}
        derived[label] = sum(route is not None for route in found.values())
        for item in sorted(tasks):
            if found[item] is not None:
                continue
            view = solver.routing_view(bench, tasks[item]["public"], runtime=runtime)
            if package.for_bench(bench):
                with workers(package, item) as worker:
                    found[item] = router.route(package, bench, view, worker)
            else:
                found[item] = router.route(package, bench, view, None)
        routes[label] = found
    sources = {label: {} for label in labels}
    for item in sorted(tasks):
        own = _signature(final, plan["routes"][item])
        running = {}
        for label in labels:
            signature = _signature(packages[label], routes[label][item])
            if not signature:
                sources[label][item] = "C"
            elif signature == own:
                sources[label][item] = "F"
            elif signature in running:
                sources[label][item] = running[signature]
            else:
                sources[label][item] = None
                running[signature] = label
    summary = {label: {"package_sha256": packages[label].sha256, "derived": derived[label],
                       "routes": {i: routes[label][i].sha256 for i in sorted(tasks)},
                       "sources": dict(sorted(sources[label].items()))} for label in labels}
    return {"routes": routes, "sources": sources, "derived": derived, "sha256": digest(summary)}


# -------------------------------------------------------------------------------------- hash-only persistence
def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None


def _completion_tokens(receipt):
    """The visible completion tokens of a receipt (§6.2, §8.3 reply length; statistics review 5), else None."""
    if not isinstance(receipt, dict):
        return None
    visible = receipt.get("visible_completion_tokens")
    if type(visible) is int:
        return visible
    usage = receipt.get("usage")
    found = usage.get("completion_tokens") if isinstance(usage, dict) else None
    return found if type(found) is int else None


completion_tokens = _completion_tokens  # the public name (``acceptance.series``; ticket P2-A2-1)


def sealed_cell(full):
    """The sealed evaluation cell of a full cell record (plan §2.10, Codex F16): hashes, judge tokens and flags,
    fault kinds, the solver route (M4: chain D's route and model id, so the read reports chain D by route); no
    prediction, receipt, reply, message or reason text."""
    full = verified(full, "cell")
    sends = full["sends"]
    calls = []
    for entry in full["logical_calls"]:
        receipt = sends[entry["send_indices"][-1]].get("receipt") if entry["send_indices"] else None
        reply = receipt.get("response") if isinstance(receipt, dict) else None
        calls.append({"purpose": entry["purpose"], "request_sha256": entry["request_sha256"],
                      "reply_sha256": _sha(reply), "completion_tokens": _completion_tokens(receipt)})
    final, judged = full["final"], full["judge"]
    return {
        "cell": full["cell"], "arm_kind": full["arm_kind"], "package_sha256": full["package_sha256"],
        **({"card": full["card"]} if full["arm_kind"] == "blank" else {}),
        "enabled": full["enabled"], "withheld": full["withheld"], "restored": full["restored"], "calls": calls,
        "sends": len(sends), "deciding_receipt": full["deciding_receipt"], "worst_delivery": full["worst_delivery"],
        "faults": [{k: f.get(k) for k in ("procedure", "hook", "kind", "exc_type", "step")} for f in full["faults"]],
        "fault_kinds": full["fault_kinds"],
        "final": None if final is None else {"token": final["token"], "outcome": final["outcome"],
                                             "kind": final["kind"], "public": public(final)},
        "judge": None if judged is None else {
            "official": judged["official"]["status"], "final": judged["final"]["token"],
            "v2": judged["v2"]["token"], "lenient": judged["lenient"]["pass"], "format": judged["format"],
            "flags": judged["flags"], "carrier": judged["carrier"]},
        "shared_with": full["shared_with"], "dispatch_ts": full["dispatch_ts"], "finish_ts": full["finish_ts"],
        "answered": answered(full),  # §6.3's mask: whether the provider delivered any reply in this cell
        "solver_route": full.get("solver_route"),  # {"route", "model"} (cells.py); route None on chain G
        **({key: full[key] for key in ("configuration", "keyword_hits", "applies", "returned_model", "returned_models")}
           if full.get("configuration") in ("zebra-pc-v7", "alfworld-v4", "zebra-pc-v8", "alfworld-v5", "zebra-pc-v9", "alfworld-v6", "zebra-pc-v10", "alfworld-v7", "zebra-pc-v11", "alfworld-v8", "zebra-pc-v12", "alfworld-v9", "alfworld-v10", "alfworld-v11", "zebra-pc-v13", "zebra-hp-v3r4", "main-v5") else {}),
        "stop": None if full["stop"] is None else {"kind": full["stop"]["kind"]}}


class EvaluationStore:
    """The test read's persistence adapter (cells.py's four store methods; Codex F16): raw predictions, scores,
    scorer directories and full records live under ``<attempt>/transient/`` only; ``cells/<id>.json`` is the sealed
    hash-only record. ``save`` returns the full record (in memory) so a C cell can be shared (``cells.share_cell``)."""

    def __init__(self, attempt, *, evidence):
        self.attempt = safe_path(attempt)
        self.transient = self.attempt / TRANSIENT
        self.evidence = evidence
        self.lock = threading.Lock()

    def claim(self, cell):
        require(not (self.attempt / "cells" / (cell + ".json")).exists(), "A cell runs once per unit attempt")
        _claim(self.attempt / "cells" / (cell + ".claim"))

    def artifact(self, value, summary):
        """Stored by content in the transient store; the summary goes into the full record only (``sealed_cell``
        never copies a cell's attempts)."""
        sha = digest(value)
        write_json(self.transient / "artifacts" / (sha + ".json"), value)
        return {"sha256": sha, **summary}

    def scorer_dir(self, position):
        """Inside the transient store, under the ``host_only`` grandparent the frozen v7 adapter requires
        (sheet_recalc_adapter.py:73-75; isolation review 3): deleted with the store, receipts included."""
        return self.transient / "host_only" / "scorer_artifacts" / position

    def save(self, value, trajectory):
        cell = value["cell"]["id"]
        write_json(self.transient / "cells" / (cell + ".json"), value)
        write_json(self.attempt / "cells" / (cell + ".json"),
                   record("evaluation-cell", self.evidence, sealed_cell(value)))
        return value

    def finish(self):
        """Delete the transient store (every cell scored, or the attempt paused); returns the deletion record's
        fields."""
        return _delete_tree(self.transient)


def _delete_tree(root):
    """Delete ``root`` (when it exists) and return its deletion manifest's fields: the file count and the sha256 of
    the [{path, sha256}] list -- paths relative to ``root``, never content."""
    files = []
    if root.exists():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            files.append({"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        shutil.rmtree(root)
    require(not root.exists(), "The transient store could not be deleted")
    return {"files": len(files), "manifest_sha256": digest(files)}


# ------------------------------------------------------------------------------------------- canaries (F16)
def canary(text):
    """A registered canary of a test text: its length and its sha256 prefix -- never the text itself."""
    require(type(text) is str and len(text) >= MIN_CANARY_CHARS, "A canary is a test text of at least %d characters"
            % MIN_CANARY_CHARS)
    return {"chars": len(text), "sha256_16": hashlib.sha256(text.encode("utf-8")).hexdigest()[:CANARY_HEX]}


def _canary_order(bench, text):
    return hashlib.sha256((CANARY_TAG + bench + ":" + text).encode("utf-8")).hexdigest()


def select_canaries(texts, *, skip=None):
    """The registered selection (§8.1 "每个测试集固定抽几段原文", Codex F16; tickets fixer-4, C3-1), the S0 exclusion
    unit's (scripts/run_execskill.py ``make_canaries``): per bench, the distinct texts of at least ``MIN_CANARY_CHARS``
    characters in the seeded order sha256(``CANARY_TAG`` + bench + ":" + text), the first ``CANARIES_PER_BENCH``, each
    kept as ``canary(text)`` only. ``texts``: {bench: [text]}; ``skip``: {bench: texts never chosen} -- the test read's
    record passes its test texts that occur verbatim on the training side (``training_duplicates``, registrar decision
    PR-C31-3 (1a)) and the seeded order of the others is unchanged; returns (the canaries in bench-name order, {bench:
    count})."""
    found, counts = [], {}
    for bench, values in sorted(texts.items()):
        never = frozenset((skip or {}).get(bench, ()))
        eligible = sorted({t for t in values if len(t) >= MIN_CANARY_CHARS and t not in never},
                          key=functools.partial(_canary_order, bench))
        require(eligible, "No %s test text is long enough for a canary%s" % (
            bench, " and absent from the training side" if never else ""))
        chosen = eligible[:CANARIES_PER_BENCH]
        found += [canary(text) for text in chosen]
        counts[bench] = len(chosen)
    return found, counts


def training_duplicates(texts, training):
    """Registrar decision PR-C31-3 (1a): {bench: the distinct test texts of at least ``MIN_CANARY_CHARS`` characters
    that occur verbatim in the same public field of one of the bench's training-side pool items}. The run-root scan
    would find such a text in the training records although nothing leaked, so it is never a canary
    (``select_canaries``'s ``skip``). ``texts``, ``training``: {bench: [text]}; a bench without training texts skips
    nothing."""
    out = {}
    for bench, values in sorted(texts.items()):
        known = training.get(bench) or ()
        out[bench] = frozenset(t for t in set(values) if len(t) >= MIN_CANARY_CHARS and any(t in s for s in known))
    return out


def read_canary_sources(configuration=None):
    """The three panels not opened by S0; the main-v5 roster contains no LiveMath."""
    if profiles.is_v214(configuration):
        return {"officeqa": "question", "zebralogic": "question", "spreadsheetbench": "instruction"}
    return READ_CANARY_SOURCES


def _training_side(pools, order=ORDER, *, configuration=None):
    """The training side the test read's canaries avoid (registrar decision PR-C31-3 (1a)): ``pools`` is the manifest's
    ``data.pools`` ({bench: {"path", "sha256"}}, naming the benches of ``order``, the run configuration's order --
    registrar 17:0x; the pilot's ``ORDER`` by default); for each bench of
    ``READ_CANARY_SOURCES`` it pins, the same public field of every pool item, read now from the pinned file, whose
    bytes must still hash to the pin (as ``manifest._items`` reads it). Returns ({bench: [texts]}, {bench: the pin's
    sha256, or None when the run pins no pool of that bench -- nothing of it is trained on})."""
    require(isinstance(pools, dict) and set(order) <= set(pools) and all(
        isinstance(entry, dict) and {"path", "sha256"} <= set(entry) for entry in pools.values()),
        "The test read's canaries need the manifest's data.pools pins")
    texts, pins = {}, {}
    for bench, field in sorted(read_canary_sources(configuration).items()):
        entry = pools.get(bench)
        texts[bench], pins[bench] = [], None
        if entry is None:
            continue
        raw = safe_path(entry["path"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == entry["sha256"], "The %s pool file differs from its pin" % bench)
        if profiles.is_v214(configuration) and bench == profiles.ZEBRA:
            from .zebralogic import load_pool
            items = load_pool(entry["path"], expected_sha256=entry["sha256"])
        else:
            items = json.loads(raw.decode("utf-8"))
        require(isinstance(items, list) and items and all(
            isinstance(item, dict) and isinstance(item.get("public"), dict)
            and type(item["public"].get(field)) is str for item in items),
            "Every %s pool item has a public %s" % (bench, field))
        texts[bench], pins[bench] = [item["public"][field] for item in items], entry["sha256"]
    return texts, pins


def _checked(value, *, configuration=None):
    """A sealed canary record: its canaries are lengths with sha256 prefixes, as many as its per-bench counts."""
    found, counts = value["canaries"], value["counts"]
    require(isinstance(found, list) and found and all(
        isinstance(c, dict) and set(c) == {"chars", "sha256_16"} and type(c["chars"]) is int
        and c["chars"] >= MIN_CANARY_CHARS and re.fullmatch(r"[0-9a-f]{%d}" % CANARY_HEX, str(c["sha256_16"]))
        for c in found), "Registered canaries are lengths with sha256 prefixes")
    benches = read_benches(configuration)
    require(isinstance(counts, dict) and counts and set(counts) <= set(benches) and all(
        type(n) is int and n > 0 for n in counts.values()) and sum(counts.values()) == len(found),
        "Registered canaries are counted per bench")
    return value


def _canary_records(root, *, read, configuration=None):
    """The run root's sealed canary records: the S0 exclusion unit's (``CANARIES``) and the test read's
    (``READ_CANARIES``), which must extend it with the three other benches and name, per bench, the training pool its
    selection checked and the number of test texts it skipped (registrar decision PR-C31-3 (1a)); the second is None
    before it is made (refused when ``read``). ``configuration`` comes from the verified run manifest or Setting;
    without one the historical two-record validation applies, never a branch selected by record content."""
    root = safe_path(root)
    if is_zebra(configuration):
        require((root / READ_CANARIES).is_file(), "The isolated test read's canaries are not made yet")
        isolated = verified(read_json(root / READ_CANARIES), "test-read-canaries")
        require(isolated.get("configuration") == configuration and set(isolated["counts"]) == {"zebralogic"}
                and isolated.get("extends") is None, "The trusted ZebraLogic run needs isolated ZebraLogic canaries")
        return _checked(isolated, configuration=configuration), None
    if is_alfworld(configuration):
        require((root / READ_CANARIES).is_file(), "The isolated ALFWorld test read's canaries are not made yet")
        isolated = verified(read_json(root / READ_CANARIES), "test-read-canaries")
        require(isolated.get("configuration") == configuration and set(isolated["counts"]) == {"alfworld"}
                and isolated.get("extends") is None, "The trusted ALFWorld run needs isolated ALFWorld canaries")
        return _checked(isolated, configuration=configuration), None
    require((root / CANARIES).is_file(), "No registered test canaries in the run root")
    sources = read_canary_sources(configuration)
    first = _checked(verified(read_json(root / CANARIES), "test-canaries"), configuration=configuration)
    second = None
    if (root / READ_CANARIES).exists():
        second = _checked(verified(read_json(root / READ_CANARIES), "test-read-canaries"), configuration=configuration)
        require(second.get("extends") == first[RECORD_HASH] and set(second["counts"]) == set(sources)
                and not set(second["counts"]) & set(first["counts"]),
                "The test read's canaries extend this run root's S0 canaries with the other benches")
        skipped, pools = second.get("skipped"), second.get("training_pools")
        require(isinstance(skipped, dict) and set(skipped) == set(sources)
                and all(type(n) is int and n >= 0 for n in skipped.values()) and isinstance(pools, dict)
                and set(pools) == set(sources)
                and all(p is None or SHA256.fullmatch(str(p)) for p in pools.values()),
                "The test read's canaries skip the texts of the training side (registrar decision PR-C31-3)")
        if configuration == profiles.BASELINE_V210:
            require(second.get("training_side") == {"skipped": True, "reason": "baseline_has_no_training",
                                                     "pool_reads": 0}
                    and all(pin is None for pin in pools.values()) and all(n == 0 for n in skipped.values()),
                    "The baseline canaries skip training-side pools because the baseline has no training")
    require(second is not None or not read, "The test read's canaries are not made yet")
    return first, second


def load_canaries(root, *, read=False, configuration=None):
    """The run root's registered canaries, merged (§8.1, Codex F16; registrar decision C3-1 (b)): the S0 exclusion
    unit's sealed ``test-canaries`` record (``shared/test-canaries.json``), followed by the test read's sealed
    ``test-read-canaries`` record (``shared/test-read-canaries.json``) once it is made. ``read``: the second record is
    required (a read unit; the run-root scan before an unseal)."""
    first, second = _canary_records(root, read=read, configuration=configuration)
    return first["canaries"] + (second["canaries"] if second is not None else [])


def _benches(first, second):
    """The bench of each merged canary (a record lists its canaries in bench-name order, ``select_canaries``)."""
    return [bench for value in (first, second) if value is not None
            for bench in sorted(value["counts"]) for _ in range(value["counts"][bench])]


def make_read_canaries(root, pinned, *, pools, run, evidence, panel=data.test_panel, order=ORDER, configuration=None):
    """Registrar decision C3-1 (b): the test read's second sealed canary record ``shared/test-read-canaries.json``
    (``test-read-canaries``), made once per run root at the start of the pilot's test read -- under the owner's
    test-read consent only (``consent``, checked first: never before it) and before the first read unit's attempt
    (``run_unit_spec``) -- from the three test sets the S0 exclusion unit does not open: OfficeQA's and LiveMath's
    public questions and SpreadsheetBench's public instructions (``READ_CANARY_SOURCES``, opened with one
    ``TestAccess(READ_CANARY_UNIT)``), selected as registered (``select_canaries``) and kept as lengths and sha256
    prefixes only. Registrar decision PR-C31-3 (1a): a test text that occurs verbatim in the same public field of one of
    the bench's training-side pool items is never chosen (``training_duplicates``); ``pools``: the manifest's
    ``data.pools`` pins, whose files are read when the record is made (``_training_side``, before any test set is
    opened); the record counts the skipped texts per bench (``skipped``) and names each pool's pin (``training_pools``),
    never a text. One process makes it; the others wait for it and read it (a lock). It extends the run root's S0
    record (``extends``: its record hash) and names the run, the consent's hash and each panel's hash. Prints nothing;
    returns the record. ``panel``: the frozen ``data.test_panel`` (a unit test passes a synthetic one)."""
    root = safe_path(root)
    if is_zebra(configuration):
        require(tuple(order) == ("zebralogic",), "The trusted ZebraLogic run has one benchmark")
        return _make_zebra_canaries(root, pinned, pools=pools, run=run, evidence=evidence, panel=panel, configuration=configuration)
    if is_alfworld(configuration):
        require(tuple(order) == ("alfworld",), "The trusted ALFWorld run has one benchmark")
        return _make_alfworld_canaries(root, pinned, pools=pools, run=run, evidence=evidence, panel=panel,
                                      configuration=configuration)
    allowed = (consent(root / "shared", configuration) if profiles.is_v210(configuration)
               else consent(root / "shared"))
    first, _ = _canary_records(root, read=False, configuration=configuration)
    path = root / READ_CANARIES
    with exclusive(root / "shared" / "test-read-canaries.lock", wait=True):
        if not path.exists():
            baseline = configuration == profiles.BASELINE_V210
            sources = read_canary_sources(configuration)
            training, pins = (({}, {bench: None for bench in sources}) if baseline else
                              _training_side(pools, order, configuration=configuration))
            access, texts, panels = data.TestAccess(READ_CANARY_UNIT), {}, {}
            for bench, field in sorted(sources.items()):
                chosen_panel = panel
                chosen_pin = pinned
                if bench == "zebralogic" and panel is data.test_panel:
                    from .zebralogic import test_panel as chosen_panel
                    if profiles.is_v214(configuration):
                        require(isinstance(pinned, dict) and bench in pinned,
                                "main-v5 pins its sealed Zebra panel separately")
                        chosen_pin = pinned[bench]
                tasks, report = chosen_panel(chosen_pin, bench, access=access)
                texts[bench], panels[bench] = [task["public"][field] for task in tasks], report["panel_hash"]
            skip = training_duplicates(texts, training)
            found, counts = select_canaries(texts, skip=skip)
            write_json(path, record("test-read-canaries", evidence, {
                "canaries": found, "counts": counts, "per_bench": CANARIES_PER_BENCH, "seed_tag": CANARY_TAG,
                "sources": {bench: "the public " + sources[bench] for bench in counts},
                "skipped": {bench: len(skip[bench]) for bench in counts}, "training_pools": pins,
                **({"training_side": {"skipped": True, "reason": "baseline_has_no_training", "pool_reads": 0}}
                   if baseline else {}),
                "unit": READ_CANARY_UNIT, "run": run, "panels": panels, "consent_sha256": digest(allowed),
                "extends": first[RECORD_HASH]}))
        _, value = _canary_records(root, read=True, configuration=configuration)
    require(value.get("run") == run and value.get("consent_sha256") == digest(allowed),
            "The test read's canaries belong to another run or consent")
    return value


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _texts(path):
    """A file's raw text and, for JSON, its decoded strings (escaped quotes or non-ASCII would hide a raw match)."""
    raw = path.read_bytes().decode("utf-8", errors="replace")
    yield raw
    if path.suffix in (".json", ".jsonl"):
        for line in raw.splitlines() if path.suffix == ".jsonl" else [raw]:
            try:
                yield "\n".join(_strings(json.loads(line)))
            except ValueError:
                continue


def _utf8_width(character):
    point = ord(character)
    return 1 if point < 0x80 else 2 if point < 0x800 else 3 if point < 0x10000 else 4


class _Windows:
    """The canary search of one scan: every window of a canary's length (in characters) hashed with sha256 and compared
    with the registered prefixes (``canary``). A text of at least ``CACHE_MIN_CHARS`` characters is hashed once per
    scan: its blake2b digest maps to the canaries found in it -- the text itself is never kept."""

    def __init__(self, canaries):
        self.wanted = {}
        for index, found in enumerate(canaries):
            self.wanted.setdefault(found["chars"], {}).setdefault(bytes.fromhex(found["sha256_16"]), index)
        self.shortest = min(self.wanted, default=None)
        self.seen = {}

    def find(self, text):
        """The indices of the canaries whose text occurs in ``text`` (sorted)."""
        if self.shortest is None or len(text) < self.shortest:
            return ()
        data = text.encode("utf-8", "surrogatepass")
        if len(text) < CACHE_MIN_CHARS:
            return self._hashed(text, data)
        key = hashlib.blake2b(data, digest_size=16).digest()
        if key not in self.seen:
            self.seen[key] = self._hashed(text, data)
        return self.seen[key]

    def _hashed(self, text, data):
        sha, found = hashlib.sha256, set()
        if len(data) == len(text):  # one byte per character
            for chars, prefixes in self.wanted.items():
                for start in range(len(data) - chars + 1):
                    index = prefixes.get(sha(data[start:start + chars]).digest()[:CANARY_BYTES])
                    if index is not None:
                        found.add(index)
        else:  # a window of ``chars`` characters spans the bytes between their UTF-8 offsets
            bounds = [0, *itertools.accumulate(map(_utf8_width, text))]
            for chars, prefixes in self.wanted.items():
                for start in range(len(text) - chars + 1):
                    index = prefixes.get(sha(data[bounds[start]:bounds[start + chars]]).digest()[:CANARY_BYTES])
                    if index is not None:
                        found.add(index)
        return tuple(sorted(found))


def canary_scan(attempt_dir, canaries, *, configuration=None, vanished=None):
    """``(files scanned, hits)``: every file under ``attempt_dir`` searched for every canary -- each window of a
    canary's length hashed and compared with its prefix (``_Windows``). A hit is {"path", "canary"} (its index), never
    text."""
    root = safe_path(attempt_dir)
    windows, files, hits = _Windows(canaries), 0, []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        found = set()
        try:
            for text in _texts(path):
                found.update(windows.find(text))
        except FileNotFoundError:
            if not profiles.is_v214(configuration) or path.exists():
                raise
            if vanished is not None:
                vanished.append({"path": str(path.relative_to(root))})
            continue
        files += 1
        hits += [{"path": str(path.relative_to(root)), "canary": index} for index in sorted(found)]
    return files, hits


def unit_scan(unit_root, shared, canaries, *, configuration=None, vanished=None):
    """``(files scanned, hits)`` over every artifact of a test-read unit (§8.1; isolation review 10): the unit root
    (every attempt), the diagnostics and child logs (``shared/host_only/diagnostics``) and the test side's shared files
    (``shared/test``). A hit is {"where": "unit"|"diagnostics"|"shared_test", "path", "canary"}, never text."""
    shared = safe_path(shared)
    files, hits = 0, []
    for where, root in (("unit", safe_path(unit_root)), ("diagnostics", shared / "host_only" / "diagnostics"),
                        ("shared_test", shared / "test")):
        if root.exists():
            missing = []
            found, found_hits = (canary_scan(root, canaries, configuration=configuration, vanished=missing)
                                 if profiles.is_v214(configuration) else canary_scan(root, canaries))
            files += found
            hits += [{"where": where, **hit} for hit in found_hits]
            if vanished is not None:
                vanished.extend({"where": where, **entry} for entry in missing)
    return files, hits


def _document(text, depth):
    """A JSON document's decoded strings (``_decoded``), or the text itself when it does not parse."""
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        yield text
    else:
        yield from _decoded(value, depth)


def _decoded(value, depth):
    """The strings of a decoded JSON value, keys included; a string that is itself a JSON document (a stored request)
    is read as its own decoded strings, at most ``DECODE_DEPTH`` levels deep."""
    for text in _strings(value):
        if depth < DECODE_DEPTH and text[:1] in ("{", "["):
            yield from _document(text, depth + 1)
        else:
            yield text


def _root_texts(path):
    """The texts ``root_scan`` reads of one file: a zip archive's (a workbook's) members with their XML entities
    resolved; a ``.json`` file's decoded strings, a ``.jsonl`` file's line by line (``_document``: escaped quotes or
    non-ASCII would hide a raw match); any other file's raw text (undecodable bytes replaced)."""
    raw = path.read_bytes()
    if raw[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = [archive.read(info) for info in archive.infolist() if not info.is_dir()]
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError, ValueError, zlib.error):
            members = None  # not a readable archive: read as raw bytes below
        if members is not None:
            for member in members:
                yield html.unescape(member.decode("utf-8", errors="replace"))
            return
    text = raw.decode("utf-8", errors="replace")
    if path.suffix == ".json":
        yield from _document(text, 0)
    elif path.suffix == ".jsonl":
        for line in text.splitlines():
            yield from _document(line, 0)
    else:
        yield text


def _where(relative):
    """The place a hit names: the run root's first two folders (``D/s2-officeqa``, ``shared/research``), or the first
    one for a file directly below it."""
    parts = relative.parts
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def scan_workers(cpus=None):
    """The run-root scan's processes (registrar decision PR-C31-3 (3)): at most ``ROOT_SCAN_WORKERS``, leaving
    ``ROOT_SCAN_SPARE_CPUS`` of this process's CPUs to a running chain, at least one. ``cpus``: given in tests."""
    if cpus is None:
        cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    return max(1, min(ROOT_SCAN_WORKERS, cpus - ROOT_SCAN_SPARE_CPUS))


def _root_files(root, *, configuration=None, vanished=None):
    """The regular files under ``root`` in the scan's one order (folders and names sorted, top down), each as (path
    relative to ``root``, size); a link anywhere in the root is refused (a linked file or folder would go unread)."""
    found = []
    for folder, folders, names in os.walk(root):
        folders.sort()
        here = Path(folder)
        for name in folders + names:
            require(not (here / name).is_symlink(), "A link in the run root: %s" % (here / name).relative_to(root))
        for name in sorted(names):
            path = here / name
            if path.is_file():
                try:
                    size = path.stat().st_size
                except FileNotFoundError:
                    if not profiles.is_v214(configuration) or path.exists():
                        raise
                    if vanished is not None:
                        vanished.append({"path": str(path.relative_to(root))})
                    continue
                found.append((path.relative_to(root), size))
    return found


def _found(path, windows):
    """The sorted indices of the canaries found in one file of the root (``_root_texts``, ``windows.find``)."""
    found = set()
    for text in _root_texts(path):
        found.update(windows.find(text))
    return tuple(sorted(found))


_SCAN = {}  # a scan process's matcher (``_scan_process``)


def _scan_process(canaries, configuration=None):
    """A scan process's initializer: its own ``_Windows``, whose repeated-text cache lasts as long as the process."""
    _SCAN["windows"] = _Windows(canaries)
    _SCAN["configuration"] = configuration


def _found_or_vanished(path, windows, configuration):
    try:
        return _found(path, windows)
    except FileNotFoundError:
        if not profiles.is_v214(configuration) or path.exists():
            raise
        return None


def _scan_share(root, paths):
    """One share of the files, in a scan process: ``_found`` of each, in the order given."""
    return [_found_or_vanished(root / path, _SCAN["windows"], _SCAN.get("configuration")) for path in paths]


def _shares(sizes, count):
    """About ``count`` contiguous runs ``(start, end)`` of the files, about equal in bytes; a unit's files stay
    together, so its repeated texts are mostly hashed in one process."""
    target, shares, start, held = max(1, -(-sum(sizes) // count)), [], 0, 0
    for index, size in enumerate(sizes):
        held += size
        if held >= target:
            shares.append((start, index + 1))
            start, held = index + 1, 0
    return shares + ([(start, len(sizes))] if start < len(sizes) else [])


def root_scan(root, canaries, *, workers=1, configuration=None, vanished=None):
    """``(files scanned, hits)`` over the whole run root (registrar decision C3-1 (b); §8.1, Codex F16): every regular
    file under ``root`` -- both chains' step and read units with every attempt (cell records, trajectories, artifacts
    and the generated sets of the generate units), the packages and markers, the research store (``shared/research``),
    the ledgers, the diagnostics and child logs and the test side's shared files -- read as ``_root_texts`` gives it and
    searched for every canary (``_Windows``: sha256 windows, a repeated text hashed once, no text kept). A link anywhere
    in the root is refused (a linked file or folder would go unread). ``workers`` > 1 (registrar decision PR-C31-3 (3),
    ``scan_workers``): the files are shared, in contiguous runs (``_shares``), among that many spawned processes, each
    with its own matcher, and each file's result is put back in the file order -- the same files, hits and order as one
    process gives, whatever the number of processes (a root of less than ``ROOT_SCAN_POOL_BYTES`` is scanned here). A
    hit is {"where", "path", "canary"} (``_where``; the canary's index), never text."""
    root = safe_path(root)
    files = (_root_files(root, configuration=configuration, vanished=vanished)
             if profiles.is_v214(configuration) else _root_files(root))
    paths, sizes = [str(relative) for relative, _ in files], [size for _, size in files]
    if workers > 1 and canaries and len(paths) > 1 and sum(sizes) >= ROOT_SCAN_POOL_BYTES:
        runs = [paths[start:end] for start, end in _shares(sizes, workers * ROOT_SCAN_SHARES)]
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                 initializer=_scan_process, initargs=(canaries, configuration)) as pool:
            found = [indices for share in pool.map(_scan_share, itertools.repeat(root), runs) for indices in share]
    else:
        windows = _Windows(canaries)
        found = [_found_or_vanished(root / path, windows, configuration) for path in paths]
    require(len(found) == len(paths), "Every file of the run root is scanned once")
    if vanished is not None:
        vanished.extend({"path": path} for path, indices in zip(paths, found) if indices is None)
    hits = [{"where": _where(relative), "path": path, "canary": index}
            for (relative, _), path, indices in zip(files, paths, found) for index in (indices or ())]
    return sum(indices is not None for indices in found), hits


# --------------------------------------------------------------------------------------------- the read unit
def _own(error):
    """Whether route B raised ``error`` (its messages are fixed text, ids and paths; evaluation.py:262-267)."""
    frames = traceback.extract_tb(error.__traceback__)
    raiser = frames[-2] if len(frames) > 1 and frames[-1].name == "require" else (frames[-1] if frames else None)
    return raiser is not None and Path(raiser.filename).resolve().parent == Path(__file__).resolve().parent


def _stack(error):
    frames = traceback.extract_tb(error.__traceback__)[-8:]
    return ["%s:%d:%s" % (Path(f.filename).name, f.lineno, f.name) for f in frames]


def _diagnose():
    try:
        traceback.print_exc()
    except Exception:  # noqa: BLE001 -- the status and the raised exception still follow
        pass


def _public_exception(error, unit):
    """What ``evaluate`` raises in place of ``error`` (evaluation.py:289-305): a fresh exception without context."""
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


def configuration(context, bench):
    """What makes two reads of the same packages interchangeable: the solver and the frozen runtime."""
    return digest({"benchmark": bench, "model": context.endpoint.model, "max_tokens": context.endpoint.max_tokens,
                   "runtime": context.runtime[bench]})


def _infrastructure(cell):
    final = cell["final"]
    return final is not None and final["outcome"] == UNKNOWN and final["kind"] in (INFRASTRUCTURE, UNCLASSIFIED)


def _counts(sealed):
    """Completed cells and unknowns by arm -- never a pass or fail count."""
    unknown = [c for c in sealed if c["final"] is not None and c["final"]["outcome"] == UNKNOWN]
    return {"cells": len(sealed), "shared": sum(c["shared_with"] is not None for c in sealed),
            "by_arm": dict(sorted(Counter(c["cell"]["arm"] for c in sealed).items())), "unknown": len(unknown),
            "unknown_by_kind": dict(Counter(c["final"]["kind"] for c in unknown)),
            "infrastructure": sum(_infrastructure(c) for c in sealed)}


def _blocks(items, bench, unit):
    """{item: block}: OfficeQA's test items in ``OFFICEQA_TEST_BLOCKS`` seeded halves dispatched one after the other
    and read as strata (§8.1); one block elsewhere."""
    if bench != "officeqa":
        return {item: "b1" for item in items}
    order = _order(list(items), round_tag(unit) + ":test-blocks")
    size = -(-len(order) // OFFICEQA_TEST_BLOCKS)
    return {item: "b%d" % (1 + n // size) for n, item in enumerate(order)}


def _arm(arms, label, cell, task):
    chosen = arms[label] if isinstance(arms[label], Arm) else arms[label](cell, task)
    require(isinstance(chosen, Arm) and chosen.kind == ARM_KINDS[label], "Arm %s has kind %s" % (label,
                                                                                               ARM_KINDS[label]))
    return chosen


def evaluate(unit_root, *, run, shared, pinned, chain, bench, arms, context, workers, route_workers, canaries,
             panel=data.test_panel, reset=None, drain=None, stages=None, run_configuration=None):
    """One test-read unit of chain ``chain`` on ``bench`` (module docstring). ``arms``: {"F", "C", "P_F", "T_F"} ->
    an ``Arm``, or a function ``(cell, task)`` giving the cell's Arm (P_F's per-item sham content); F's package is the
    final package, C's the card arm's empty package; ``context``: a ``cells.Context`` for the next attempt directory;
    ``route_workers``: ``test_plan``'s worker factory (on SpreadsheetBench called with ``inputs_dir=``: Codex finding
    #1); ``canaries``: the registered canaries (``load_canaries``); ``reset``: ALFWorld's routing-view reset (default
    ``alfworld_reset`` on the frozen runtime); ``drain``: the unit drain (``units.drainer``, ticket C5-1), run once the
    attempt has ended, before ``unit.json``; ``stages``: a stage read's ``stage_rows`` (None: no stage arm), only with
    ``run_configuration``, a stage-read run configuration whose exact consent (``consent``) is checked before an
    attempt opens or a panel is read (Codex stage review #4). Returns the unit record; raises ``Pause`` (written to the attempt's
    status) when the read must stop."""
    unit = "%s/test/%s" % (chain, bench)
    try:
        require(isinstance(run, str) and run, "A unit belongs to a run")
        unit_root = safe_path(unit_root)
        unit_root.mkdir(parents=True, exist_ok=True)
        with exclusive(unit_root / ".lock"):
            with contained(shared):
                try:
                    try:
                        found = _evaluate(unit_root, unit, run=run, shared=shared, pinned=pinned, chain=chain,
                                          bench=bench, arms=arms, context=context, workers=workers,
                                          route_workers=route_workers, canaries=canaries, panel=panel, reset=reset,
                                          stages=stages, run_configuration=run_configuration)
                    finally:
                        _drained(drain, context, unit,
                                 **({"configuration": run_configuration} if profiles.is_v292(run_configuration) else {}))
                except BaseException:  # noqa: B036 -- recorded in full while still contained
                    _diagnose()
                    raise
            write_json(unit_root / "unit.json", found)
            return found
    except BaseException as error:  # noqa: B036 -- replaced below, outside this handler: no context
        replacement = _public_exception(error, unit)
    raise replacement


def _drained(drain, context, unit, *, configuration=None):
    """The unit drain after the attempt (ticket C5-1): CleanupUnconfirmed (the unit's containers remain) pauses the
    unit as a stop, its status written unless the attempt already has one."""
    if drain is None:
        return
    try:
        drain()
    except CleanupUnconfirmed as error:
        kind_ = stop_kind(error) or "exception"
        if context.attempt.is_dir() and not (context.attempt / "status.json").exists():
            _paused(context.attempt, context.evidence, kind_, "unit_drain: %s" % str(error)[:200])
        raise Pause(kind_, "unit_drain", unit) from None
    finally:
        cleanups = getattr(drain, "cleanups", None) if profiles.is_v292(configuration) else None
        if cleanups:
            write_json(context.attempt / "sandbox-cleanups.json", {"cleanups": cleanups})
        starts = getattr(drain, "starts", None) if profiles.is_v292(configuration) else None
        if starts:
            write_json(context.attempt / "sandbox-starts.json", {"starts": starts})


def _paused(attempt, evidence, kind_, reason, **extra):
    write_json(attempt / "status.json", record("unit-status", evidence, {
        "status": "paused", "kind": kind_, "reason": reason, "cell": None, **extra}))


def _closed(store, evidence):
    """Delete the attempt's transient store and write its deletion record (every exit; isolation review 11)."""
    deleted = store.finish()
    write_json(store.attempt / "transient-deleted.json", record("transient-deletion", evidence, deleted))
    return deleted


def _leftovers(unit_root, evidence):
    """Before a new attempt: the transient store an earlier attempt left behind (a killed process never ran
    ``finish``) is deleted with its deletion record (isolation review 11); returns the attempts cleaned."""
    cleaned = []
    for earlier in attempts(unit_root):
        if (earlier / TRANSIENT).exists():
            require(not (earlier / "transient-deleted.json").exists(), "An attempt's transient store is deleted once")
            _closed(EvaluationStore(earlier, evidence=evidence), evidence)
            cleaned.append(earlier.name)
    return cleaned


def _scanned(unit_root, shared, canaries, *, configuration=None):
    missing = []
    files, hits = (unit_scan(unit_root, shared, canaries, configuration=configuration, vanished=missing)
                   if profiles.is_v214(configuration) else unit_scan(unit_root, shared, canaries))
    return {"artifacts_scanned": files, "hits": hits,
            **({"vanished": len(missing), "vanished_paths": missing} if profiles.is_v214(configuration) else {})}


def _linked(context, linked, sources, plan, staged, final, packages, *, store):
    """The stage cells ``stage_plan`` linked to a source ((job, source) pairs): "C" shares the card arm's cell
    (``share_cell``), "F" or an earlier stage arm the cell that ran there (``cells.share_same``) -- when that cell ran
    with exactly the planned procedures and recorded no fault (Codex stage review #1); otherwise the job is returned,
    to run."""
    fallback = []
    for (cell, task, arm), source in linked:
        item, run_index, label = cell["task_id"], cell["run"], cell["arm"]
        route = staged["routes"][label][item]
        found = sources[(source, item, run_index)]
        if source == "C":
            share_cell(context, cell, task, arm, found, route.to_json(), store=store)
            continue
        source_route = plan["routes"][item] if source == "F" else staged["routes"][source][item]
        if list(found.get("enabled") or []) != list(route.enabled) or found.get("faults"):
            fallback.append((cell, task, arm))
            continue
        share_same(context, cell, task, arm, found, route.to_json(), source_route.to_json(),
                   final if source == "F" else packages[source], store=store)
    return fallback


def _stage_arms(stages, final):
    """A stage read's rows and packages, checked (``stage_rows``): row 0 C, every row C, F or a stage arm of the
    packages, each stage package used, holding a procedure and neither F nor another stage package."""
    rows, packages = stages["rows"], stages["packages"]
    require(isinstance(rows, list) and rows and rows[0] == "C" and isinstance(packages, dict)
            and all(STAGE_LABEL.fullmatch(label) and isinstance(p, Package) for label, p in packages.items())
            and set(rows) <= {"C", "F", *packages} and set(packages) <= set(rows)
            and all(p.procedures and p.sha256 != final.sha256 for p in packages.values())
            and len({p.sha256 for p in packages.values()}) == len(packages), "The stage arms of the read")
    return rows, packages


def _evaluate(unit_root, unit, *, run, shared, pinned, chain, bench, arms, context, workers, route_workers, canaries,
              panel, reset, stages=None, run_configuration=None):
    require(not (unit_root / "unit.json").exists(), "This unit is complete")
    main_v5 = profiles.is_v214(run_configuration)
    child = profiles.is_v210(run_configuration)
    reduced = child or profiles.is_zebra_fc(run_configuration)
    expected = read_arms_of(run_configuration) if reduced else ARMS
    if main_v5:
        expected = tuple(arm for arm in expected if arm != profiles.STAGES)
    require(set(arms) == set(expected), "The read's arms must match the configuration exactly")
    if reduced:
        require(context.configuration == run_configuration,
                "The read context belongs to its v2.10 configuration" if child else
                "The read context belongs to its zebra-hp-v3r4 configuration" if profiles.is_v213(run_configuration) else
                "The read context belongs to its zebra-pc-v13 configuration")
        consent(shared, run_configuration)
    final, card = arms.get("F", arms["C"]).package, arms["C"].package
    require(child or final.sha256 != card.sha256, "F = C: nothing was accepted, the read is not made (§8.1)")
    if child:
        require(not arms["B"].package.procedures, "B runs no procedure")
    require(not card.for_bench(bench), "The card arm runs no procedure")
    rows, packages = _stage_arms(stages, final) if stages is not None else (None, {})
    if main_v5:
        require(rows is not None and len(rows) == len(profiles.CONFIGURATIONS[run_configuration]["order"]) + 1
                and rows[-1] == ("F" if final.procedures else "C")
                and all(label == "%s%d" % (STAGE_ARM, rows.index(label))
                        and 1 <= rows.index(label) < len(rows) - 1 for label in packages),
                "main-v5 reads every frozen step, including its final row")
    if stages is not None:  # Codex stage review #4: the stage arms are read only under their exact consent
        require(run_configuration in CONFIGURATIONS and STAGE_READ[run_configuration],
                "A stage read belongs to a stage-read configuration")
        consent(shared, run_configuration)
    evidence = context.evidence
    config = configuration(context, bench)
    identity = {"run": run, "unit": unit, "chain": chain, "bench": bench, "config": config,
                "packages": ({label: arm.package.sha256 for label, arm in arms.items()} if child else
                             {"F": final.sha256, "C": card.sha256,
                              **{label: p.sha256 for label, p in sorted(packages.items())}})}
    if main_v5:
        identity["packages"].update({label: p.sha256 for label, p in sorted(packages.items())})
    if child:
        from .instruction_start import START, blank_definition
        identity.update(instruction_start=START, blank_arm=blank_definition())
    attempt = context.attempt
    require(attempt == _next_attempt(unit_root) and not attempt.exists(),
            "A unit attempt runs in the next attempt directory; after a pause, only with the owner's recorded decision")
    cleaned = _leftovers(unit_root, evidence)
    scan_options = {"configuration": run_configuration} if main_v5 else {}
    before = _scanned(unit_root, shared, canaries, **scan_options)
    attempt.mkdir()
    if before["hits"]:
        _paused(attempt, evidence, "canary_hit", "%d canary hits before the attempt" % len(before["hits"]),
                hits=before["hits"], cleaned=cleaned, **({"scan": before} if main_v5 else {}))
        raise Pause("canary_hit", "%d hits" % len(before["hits"]), unit)
    store = EvaluationStore(attempt, evidence=evidence)
    try:
        if bench == "alfworld":
            require(os.environ.get("ALFWORLD_DATA") == context.runtime["alfworld"]["alfworld_data"],
                    "Set ALFWORLD_DATA to the frozen runtime path before launch")
            if reset is None:
                reset = alfworld_reset(context.runtime["alfworld"], context.episodes)
        tasks = test_tasks(shared, pinned, bench, unit, run=run, runtime=context.runtime[bench],
                           native=context.native, workers=workers, evidence=evidence, panel=panel,
                           **({"configuration": run_configuration}
                              if profiles.is_zebra_fc(run_configuration) or main_v5 else {}))
        plan = test_plan(tasks, final, bench=bench, unit=unit, runtime=context.runtime[bench], workers=route_workers,
                         reset=reset, **({"run_configuration": run_configuration} if reduced else {}))
        staged = stage_plan(plan, final, packages, bench=bench, runtime=context.runtime[bench],
                            workers=route_workers) if packages else None
        by_id = {t["task_id"]: {"public": t["public"], "private": t["private"]} for t in plan["tasks"]}
        rooms = {i: task_folder(by_id[i]["public"]["game_file"])[0] for i in by_id} if bench == "alfworld" else {}
        blocks = _blocks(sorted(by_id), bench, unit)
        zero = set(plan["zero"])
        jobs, shares, linked, blank_shares = [], [], [], []
        for item in sorted(by_id):
            for run_index in range(TEST_RUNS):
                labels = list(expected) if reduced else ["C"] + ([] if item in zero else ["F", "P_F", "T_F"])
                labels += [TWIN + p for p in plan["twins"].get(item, [])]
                for label in labels + (["F", "P_F", "T_F"] if item in zero and not reduced else []) + sorted(
                        packages, key=lambda found: int(found[len(STAGE_ARM):])):
                    cell = {"id": cell_id(unit, label, item, run_index), "unit": unit, "arm": label,
                            "benchmark": bench, "task_id": item, "run": run_index, "block": blocks[item],
                            **({"room": rooms[item]} if rooms else {})}
                    if label.startswith(TWIN):
                        jobs.append((cell, by_id[item], Arm(label, final, withhold={label[len(TWIN):]})))
                    elif label in packages:  # a stage arm: it runs, or shares the cell of its source
                        source = staged["sources"][label][item]
                        job = (cell, by_id[item], Arm("candidate", packages[label]))
                        if source is None:
                            jobs.append(job)
                        else:
                            linked.append((job, source))
                    elif main_v5 and bench == profiles.ZEBRA and label == "B":
                        # The Zebra shell never sends the instruction card: B's request is exactly C's.
                        blank_shares.append((cell, by_id[item], _arm(arms, label, cell, by_id[item])))
                    else:
                        (shares if item in zero and label in (("F",) if reduced else ("F", "P_F", "T_F")) else jobs).append(
                            (cell, by_id[item], _arm(arms, label, cell, by_id[item])))
        sources = {}
        for block in sorted(set(blocks.values())):
            members = [job for job in jobs if job[0]["block"] == block]
            members = [members[i] for i in _order(list(range(len(members))), round_tag(unit) + ":test:" + block)]
            ran = run_cells(context, members, workers=workers, store=store)
            sources.update({(c["arm"], c["task_id"], c["run"]): found for (c, _, _), found in zip(members, ran)})
        for cell, task, arm in shares:
            share_cell(context, cell, task, arm, sources[("C", cell["task_id"], cell["run"])],
                       plan["routes"][cell["task_id"]].to_json(), store=store)
        for cell, task, arm in blank_shares:
            route = router.route(arm.package, bench,
                                 solver.routing_view(bench, task["public"], runtime=context.runtime[bench]), None)
            share_cell(context, cell, task, arm, sources[("C", cell["task_id"], cell["run"])],
                       route.to_json(), store=store)
        fallback = _linked(context, linked, sources, plan, staged, final, packages, store=store)
        if fallback:  # the source cell did not run with the planned procedures: the stage cell runs, after the blocks
            fallback = [fallback[i] for i in _order(list(range(len(fallback))), round_tag(unit) + ":test:fallback")]
            run_cells(context, fallback, workers=workers, store=store)
        deleted = _closed(store, evidence)
    except Pause as pause:
        _closed(store, evidence)
        _paused(attempt, evidence, pause.kind, pause.reason, scan=_scanned(unit_root, shared, canaries, **scan_options),
                **({"before_scan": before} if main_v5 else {}))
        raise
    except Exception as error:  # a configuration check above, or an unexpected error (like a crash): the unit pauses
        _diagnose()
        _closed(store, evidence)
        kind_ = "configuration" if isinstance(error, ValueError) else "exception"
        reason = (type(error).__name__ + (":" + str(error)[:200] if _own(error) else "")) if kind_ == "configuration" \
            else type(error).__name__
        _paused(attempt, evidence, kind_, reason, stack=_stack(error),
                scan=_scanned(unit_root, shared, canaries, **scan_options),
                **({"before_scan": before} if main_v5 else {}))
        raise Pause(kind_, reason, unit) from None
    sealed = [verified(read_json(p), "evaluation-cell") for p in sorted((attempt / "cells").glob("*.json"))]
    counts = _counts(sealed)
    after = _scanned(unit_root, shared, canaries, **scan_options)
    files, hits = after["artifacts_scanned"], after["hits"]
    if hits:
        _paused(attempt, evidence, "canary_hit", "%d canary hits in %d files" % (len(hits), files), hits=hits,
                **({"scan": after, "before_scan": before} if main_v5 else {}))
        raise Pause("canary_hit", "%d hits" % len(hits), unit)
    if counts["infrastructure"] > INFRA_UNKNOWN_MAX * counts["cells"]:
        _paused(attempt, evidence, "infrastructure_incomplete", "%d of %d cells" % (counts["infrastructure"],
                                                                                   counts["cells"]),
                scan=after if main_v5 else {"artifacts_scanned": files, "hits": []},
                **({"before_scan": before} if main_v5 else {}))
        raise Pause("infrastructure_incomplete", "%d of %d cells" % (counts["infrastructure"], counts["cells"]), unit)
    scan = record("canary-scan", evidence, {"artifacts_scanned": files, "hits": 0, "canaries": len(canaries),
                                            "canaries_sha256": digest(canaries), "cleaned_attempts": cleaned,
        **({"vanished": before["vanished"] + after["vanished"],
            "vanished_paths": [{"phase": phase, **entry} for phase, part in (("before", before), ("after", after))
                               for entry in part["vanished_paths"]]} if main_v5 else {})})
    write_json(attempt / "canary_scan.json", scan)
    return record("evaluation", evidence, {
        **identity, "status": "complete", "attempt": attempt.name, "counts": counts, "plan_sha256": plan["sha256"],
        "structural_zero": len(zero), "twins": sum(len(v) for v in plan["twins"].values()),
        "rooms": len(set(rooms.values())) if rooms else None, "cells": sorted(c["cell"]["id"] for c in sealed),
        "transient_deleted_sha256": deleted["manifest_sha256"], "canary_scan_sha256": scan["record_sha256"],
        **({"blank_sharing": {"source": "C", "cells": len(blank_shares), "dispatches": 0,
                              "reason": "Zebra shell omits the card sentence"}}
           if main_v5 and bench == profiles.ZEBRA else {}),
        **({"stages": {"rows": rows, "plan_sha256": staged["sha256"] if staged else None,
                       "derived": staged["derived"] if staged else {},
                       "sources": {label: dict(sorted(Counter("sent" if source is None else source for source in
                                                              staged["sources"][label].values()).items()))
                                   for label in sorted(packages)},
                       "fallback": len(fallback)}} if rows is not None else {})})


# ----------------------------------------------------------------------------- the child entry (ticket A13-1)
def donor_corpora(chain_root):
    """{procedure id: the sealed donor corpus of the acceptance round that accepted it}: each accepted step's
    ``accept/sealed.json`` in step order (a later step's corpus names only the procedures it changed)."""
    out = {}
    steps = sorted(safe_path(chain_root).glob("s*-*/step.json"), key=lambda p: int(p.parent.name[1:].split("-")[0]))
    for path in steps:
        if verified(read_json(path), "step")["decision"] == "accept":
            corpus = verified(read_json(path.parent / "accept" / "sealed.json"), "acceptance-sealed")["corpus"]
            out.update({procedure: corpus for procedure in corpus["outputs"]})
    return out


def frozen_texts(chain_root, final):
    """T_F's texts (§8.1, ticket A10-3): {procedure id: frozen description} of F's describer entries, from the chain's
    freeze units, each text's hash equal to its entry in F."""
    records = []
    for path in sorted(safe_path(chain_root).glob("s*-*/freeze/unit.json")):
        records += verified(read_json(path), "unit")["result"]["descriptions"]
    found = describer.texts(records)
    require(all(p in found and digest(found[p]) == e["text_sha256"] for p, e in final.describer.items()),
            "Every frozen description of F is in the chain's freeze records")
    return {p: found[p] for p in final.describer}


def placebo_arm(final, corpora, *, bench, unit, runtime, workers):
    """``arms["P_F"]`` (§8.1, ticket A12-1 item 3): a function (cell, task) -> Arm giving F with every procedure that
    may run on ``bench`` shammed from the sealed donor corpus of the round that accepted it (``donor_corpora``): one
    donor per item and procedure (``donors.pair`` seeded by the unit and the item, ``yoke_seed``, as the items are
    known only inside the unit), each sham at the length of F's real note on the item (``placebo.real_lengths``, zero
    calls; ``workers``: ``test_plan``'s factory, which on SpreadsheetBench mounts the item's public workbook as in the
    plan: ``mounting``, Codex finding #1). An item's sham content is built once, inside the read unit, from
    training-side donors only."""
    procedures = final.for_bench(bench)
    require(all(p.id in corpora for p in procedures), "Every procedure of F has its acceptance's sealed donor corpus")
    built = {}

    def arm(cell, task):
        item = cell["task_id"]
        if item not in built:
            view = solver.routing_view(bench, task["public"], runtime=runtime)
            mounted = mounting(workers, public_inputs(bench, {item: task}))
            content = {}
            for procedure in procedures:
                changed, corpus = [("new", procedure, "candidate")], corpora[procedure.id]
                lengths = placebo.real_lengths(changed, {item: view}, mounted, bench=bench,
                                               packages={"candidate": final})
                pairs = donors.pair([item], corpus, yoke_seed(unit, item))["pairs"]
                content.update(placebo.build_y(corpus, pairs, lengths, changed=changed)[item]["procedures"])
            built[item] = {item: {"procedures": content}}
        return Arm("placebo_y", final, placebo=placebo.arm(built[item], item, seed=discourage_tag(unit, cell["id"])))

    return arm


def yoke_seed(unit, item):
    """The unit ``donors.pair`` seeds one test item's donor with (``protocol.yoke_tag``): ``<unit>/<the first 16 hex
    digits of sha256(item)>``. ``protocol._tag`` admits no ':' or whitespace in a tag part, so the earlier
    ``"<unit>:<item>"`` was refused for every item -- every P_F arm raised ValueError at its first cell -- and an
    item id may itself hold either character; its hash never does (M round, builder V)."""
    return "%s/%s" % (unit, hashlib.sha256(item.encode("utf-8")).hexdigest()[:16])


def run_unit_spec(manifest, *, spec, docker=None, transport=None, panel=data.test_panel, reset=None):
    """``run_execskill.py evaluate-unit --manifest M --spec S`` (ticket A13-1, A12-1 item 3): the test-read unit
    ``chain.launch_child`` started, ``spec`` the JSON file it wrote ({"chain", "bench", "package_sha256",
    "unit_root"}). Consent first; then the chain's Setting from the verified manifest (``manifest.setting_of``), the
    unit's own Setting (``units.for_unit``: its tag on every container, ALFWorld's 6 workers), the solver endpoint on
    ``<chain>:test`` with the ledger bound B, the arms (module docstring), the run root's merged canaries -- the test
    read's second record made first when no unit has made it yet (``make_read_canaries`` with the manifest's
    ``data.pools`` pins, registrar decisions C3-1 (b), PR-C31-3 (1a)) -- and the unit drain; in a stage-read
    configuration (``protocol.STAGE_READ``) also the stage arms (``stage_rows``) under a consent naming them.
    Returns ``chain.EXIT_COMPLETE``, ``EXIT_AWAITING`` (a paused attempt awaits the owner's recorded decision) or
    ``EXIT_PAUSED``. ``docker`` / ``transport`` / ``panel`` / ``reset``: fakes in tests."""
    found = read_json(spec)
    require(isinstance(found, dict) and set(found) == SPEC_FIELDS, "An evaluate-unit spec names chain, bench, "
            "package_sha256 and unit_root")
    chain, bench = found["chain"], found["bench"]
    require(chain in CHAINS and bench in SUPPORTED_BENCHES, "A read unit of a chain and a bench")
    setting = setting_of(manifest, chain, docker=docker, transport=transport)
    configuration = configuration_of(setting)
    require(bench in read_benches(configuration), "A read unit belongs to its configuration read roster")
    if bench == "zebralogic" and panel is data.test_panel and not profiles.is_v214(configuration):
        from .zebralogic import test_panel as panel
    consent(setting.shared, configuration)  # a stage read's consent names its stage arms
    if profiles.is_v210(configuration):
        from .chain import confirmation
        confirmation(setting.root, setting.run, chain, route="B" if chain == "D" else None,
                     configuration=configuration)
    if profiles.is_v214(configuration):
        from .chain import heavy
        try:
            pointer = safe_path(setting.shared) / "test" / (SHEET_QUALIFICATION + ".json")
            if pointer.exists():
                prepare_test_qualification(setting, chain, panel=panel, pinned=manifest["data"].get("pinned"))
            else:
                with heavy(setting, "spreadsheetbench"):
                    prepare_test_qualification(setting, chain, panel=panel, pinned=manifest["data"].get("pinned"))
        except Pause as pause:
            return EXIT_AWAITING if pause.kind == "awaiting_owner_decision" else EXIT_PAUSED
    unit_root = read_root(setting, chain, bench)
    require(safe_path(found["unit_root"]) == unit_root, "The read unit's registered directory")
    attempt = _next_attempt(unit_root)
    if (unit_root / "unit.json").exists():
        return EXIT_COMPLETE
    if attempt is None:
        return EXIT_AWAITING
    chain_root = safe_path(setting.root) / chain
    start = empty(step="%s/s0" % chain, evidence=setting.evidence)  # chain.run's start, which is never saved
    # a stage read whose later steps deleted every procedure reads with F the empty start (``chain.run``)
    final = start if (STAGE_READ[configuration] or profiles.is_v210(configuration)) and found["package_sha256"] == start.sha256 else load(
        chain_root / "packages" / (found["package_sha256"] + ".json"))
    require(final.sha256 == found["package_sha256"], "The final package of the chain")
    stages = stage_rows(chain_root, chain, order_of(setting), final, start) if STAGE_READ[configuration] else None
    unit = "%s/test/%s" % (chain, bench)
    own = units.for_unit(setting, chain, bench, unit)
    if profiles.is_v292(configuration):
        own.sandbox["cleanup_events"].clear()
        own.sandbox["start_events"].clear()
    model = CHAINS[chain]
    glm = model == CHAINS["G"]
    endpoint = budgets.endpoint(own, budgets.solver_scopes(chain, None, None, "test"), client=own.clients(model, bench),
                                max_tokens_bound=ledger_bound(model, bench, branch=None if glm else own.branch,
                                                              longest=None if glm else own.longest))
    route_workers = functools.partial(_route_worker, own)
    runtime = setting.runtime[bench]
    card = final if configuration == profiles.BASELINE_V210 else empty(step="%s/card" % chain, evidence=setting.evidence)
    if profiles.is_v210(configuration):
        arms = {"C": Arm("card", card), "B": Arm("blank", card)}
        if configuration != profiles.BASELINE_V210:
            arms = {"F": Arm("candidate", final), **arms}
    elif profiles.is_zebra_fc(configuration):
        arms = {"F": Arm("candidate", final), "C": Arm("card", card)}
    else:
        arms = {"F": Arm("candidate", final), "C": Arm("card", card),
                "P_F": placebo_arm(final, donor_corpora(chain_root), bench=bench, unit=unit, runtime=runtime,
                                   workers=route_workers),
                "T_F": Arm("text", final, text=frozen_texts(chain_root, final))}
    pinned = manifest["data"].get("pinned")
    make_read_canaries(setting.root, pinned,
                       pools=None if configuration == profiles.BASELINE_V210 else manifest["data"].get("pools"), run=setting.run,
                       evidence=setting.evidence, panel=panel, order=order_of(setting), configuration=configuration)
    try:
        evaluate(unit_root, run=setting.run, shared=setting.shared, pinned=pinned, chain=chain, bench=bench, arms=arms,
                 context=units.cell_context(own, attempt, endpoint), workers=own.workers, route_workers=route_workers,
                 canaries=load_canaries(setting.root, read=True, configuration=configuration), panel=panel, reset=reset,
                 drain=None if configuration == profiles.BASELINE_V210 else units.drainer(setting, chain, unit),
                 stages=stages, run_configuration=configuration)
    except Pause as pause:
        return EXIT_AWAITING if pause.kind == "awaiting_owner_decision" else EXIT_PAUSED
    return EXIT_COMPLETE


def _route_worker(setting, package, item, *, inputs_dir=None):
    """``test_plan``'s and the placebo lengths' factory: a started sandbox worker holding ``package`` with the unit's
    sandbox options (its tag included) and the live and per-call pools; ``inputs_dir``: a SpreadsheetBench item's
    public input directory, mounted read-only at /input (``mounting``, Codex finding #1; ``step._item_workers``)."""
    return sandbox.with_worker(package, kind="cell", inputs_dir=inputs_dir, **setting.sandbox,
                               live=setting.slots["execskill-sandbox-live"],
                               per_call=setting.slots["execskill-sandbox"])


def monitor(unit_roots):
    """Infrastructure view of read units: status and counts -- never a score (evaluation.py:414-426)."""
    rows = []
    for unit_root in unit_roots:
        path = safe_path(unit_root) / "unit.json"
        if path.exists():
            found = verified(read_json(path), "evaluation")
            rows.append({"unit": found["unit"], "status": found["status"], **found["counts"]})
        else:
            found = attempts(unit_root)
            done = len(list(found[-1].glob("cells/*.json"))) if found else 0
            rows.append({"unit_root": str(unit_root), "status": "open", "attempts": len(found), "cells_done": done})
    return rows


# ----------------------------------------------------------------------------------------- unseal (Codex F17)
def continuation(root):
    """The owner's continue/stop file (``shared/owner-continuation.json``; exact key set)."""
    path = safe_path(root) / OWNER_CONTINUATION
    require(path.exists(), "Test scores stay sealed until the owner's continuation file exists")
    value = read_json(path)
    require(isinstance(value, dict) and set(value) == CONTINUATION_FIELDS and value["by"] == "owner"
            and value["decision"] in ("continue", "stop") and isinstance(value["date"], str)
            and isinstance(value["note"], str), "Not the owner's continuation file")
    return value


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _document_sha(root):
    document = safe_path(root) / FORMAL_ADDENDUM_DOCUMENT
    require(document.is_file() and document.read_bytes().strip(), "No formal-chain addendum document")
    return hashlib.sha256(document.read_bytes()).hexdigest()


def seal_addendum(root, *, evidence, clock=_now):
    """Seal the formal-chain addendum (§8.1, owner #32; isolation review 12): the owner's document
    ``shared/formal-addendum.md`` is hashed and the sha256 with the time of sealing -- this code's clock, never a
    declared time -- written once as the record ``shared/formal-addendum.json``."""
    path = safe_path(root) / FORMAL_ADDENDUM
    require(not path.exists(), "The formal-chain addendum is sealed once")
    sha, now = _document_sha(root), clock()
    require(UTC.fullmatch(now), "The sealing time is a UTC timestamp")
    value = record("formal-addendum", evidence, {"document": FORMAL_ADDENDUM_DOCUMENT, "sha256": sha,
                                                 "written_at": now})
    write_json(path, value)
    return value


def _addendum(root):
    """The sealed formal-chain addendum ({sha256, written_at}), or None; the document must still hash to its seal."""
    path = safe_path(root) / FORMAL_ADDENDUM
    if not path.exists():
        return None
    value = verified(read_json(path), "formal-addendum")
    require(value["document"] == FORMAL_ADDENDUM_DOCUMENT and SHA256.fullmatch(str(value["sha256"]))
            and UTC.fullmatch(str(value["written_at"])), "Not the formal-chain addendum record")
    require(_document_sha(root) == value["sha256"], "The formal-chain addendum document differs from its seal")
    return {"sha256": value["sha256"], "written_at": value["written_at"]}


def _case(owner, added, now):
    """The ``LABELS`` case of an unseal at ``now`` (§8.1, Codex F17)."""
    if owner["decision"] == "stop":
        return "stop"
    return "continue_on_time" if added is not None and added["written_at"] < now else "continue_late"


def _marker(root, chain_root, *, evidence, clock, scan):
    """The chain's write-once unseal marker: the read's label, the label every later read inherits and the run-root
    canary scan it followed (``_root_scanned``: clean, or accepted under the owner's release, which it names)."""
    path = safe_path(chain_root) / UNSEALED
    if path.exists():
        return verified(read_json(path), "unseal")
    owner, added, now = continuation(root), _addendum(root), clock()
    require(UTC.fullmatch(now), "The unseal time is a UTC timestamp")
    label, later = LABELS[_case(owner, added, now)]
    value = record("unseal", evidence, {"unsealed_at": now, "decision": owner["decision"],
                                        "continuation_sha256": digest(owner),
                                        "addendum": added, "label": label, "later_reads": later, "canary_scan": scan})
    write_json(path, value)
    return value


def continuation_check(manifest, *, chain, clock=_now):
    """``run_execskill.py continuation-check`` (ticket A13-1): whether ``chain`` has ended, the owner's continuation
    decision, the formal-chain addendum and the label an unseal would carry now (or the label it carried) -- reads no
    score and writes nothing."""
    require(chain in CHAINS, "Unknown chain")
    root = safe_path(manifest["root"])
    chain_root = root / chain
    found = {"chain": chain, "ended": [name for name in ("chain-complete.json", "chain-terminated.json")
                                       if (chain_root / name).exists()]}
    if (chain_root / UNSEALED).exists():
        marker = verified(read_json(chain_root / UNSEALED), "unseal")
        return {**found, "unsealed": True, "continuation": marker["decision"], "addendum": marker["addendum"],
                "label": marker["label"], "later_reads": marker["later_reads"]}
    owner = continuation(root) if (root / OWNER_CONTINUATION).exists() else None
    added = _addendum(root)
    label, later = LABELS[_case(owner, added, clock())] if owner is not None else (None, None)
    return {**found, "unsealed": False, "continuation": None if owner is None else owner["decision"],
            "addendum": added, "label": label, "later_reads": later}


def read_label(chain_roots):
    """The label of a test read made after the given chains' unseals (Codex F17): ``repeated_test_development`` when
    any of them unsealed without the hashed addendum predating it (or after a stop), else ``confirmatory``."""
    later = [verified(read_json(safe_path(r) / UNSEALED), "unseal")["later_reads"] for r in chain_roots
             if (safe_path(r) / UNSEALED).exists()]
    return "repeated_test_development" if "repeated_test_development" in later else "confirmatory"


def _ended(chain_root):
    return (chain_root / "chain-complete.json").exists() or (chain_root / "chain-terminated.json").exists()


def _scan_attempt(base):
    """The next scan attempt directory under ``base`` (``attempts``' numbering), or None while the last scan's hit
    awaits the owner's recorded decision (``recovery.json`` in that attempt: ``run_execskill.py recover``). A clean or
    interrupted scan never blocks the next one."""
    earlier = attempts(base)
    if earlier and (earlier[-1] / "status.json").exists() and not recovered(earlier[-1]):
        return None
    return safe_path(base) / ("attempt-%d" % (int(earlier[-1].name.rpartition("-")[2]) + 1 if earlier else 1))


def release_check(attempt, decision):
    """Registrar decision PR-C31-3 (1b), the owner's release of a paused run-root scan, checked before
    ``run_execskill.py recover`` writes it (its ``recovery.json`` is write-once) and again at every unseal
    (``_release``): a decision ``release <sha256>`` (``RELEASE``) is accepted only in a paused scan attempt
    ``<chain root>/root-scan/attempt-N`` (its ``canary_hit`` status names the scan) and only when it names that
    attempt's own scan record_sha256; the first word "release" is reserved for it (as ``recover`` reserves it), so a
    decision starting with it in any other form or place is refused. Any other decision is free text and releases
    nothing (a unit's redo, or a new scan). Returns the released scan's record hash, or None."""
    attempt = safe_path(attempt)
    if decision.split(None, 1)[:1] != ["release"]:
        return None
    match = RELEASE.fullmatch(decision)
    require(match is not None, "A release decision is exactly 'release <the record_sha256 of the scan paused there>'")
    require(attempt.parent.name == ROOT_SCAN, "A release is the owner's decision on a paused run-root canary scan only")
    require((attempt / "scan.json").is_file() and (attempt / "status.json").is_file(),
            "A release names the scan paused in that attempt")
    scan = verified(read_json(attempt / "scan.json"), "root-canary-scan")
    status = verified(read_json(attempt / "status.json"), "unit-status")
    require(scan["hits"] > 0 and status["kind"] == "canary_hit" and status.get("scan_sha256") == scan[RECORD_HASH]
            == match.group(1), "The release in %s names another scan than the one paused there" % attempt.name)
    return match.group(1)


def _release(base, attempt):
    """The owner's release in force for the scan in ``attempt`` (registrar decision PR-C31-3 (1b)): the decision
    recorded in the last paused scan attempt before it. Returns (None, None) without one (no paused scan, no owner
    decision, or one that asks for a new scan only); ({"attempt", "scan_sha256", "recovery_sha256"}, the released scan
    record) for the owner's release of that attempt's own scan (``release_check``); ({"attempt", "refused"}, None) for
    any other release: it releases nothing, so the next scan with hits pauses again in a new attempt, where the owner
    can decide anew (a recovery file is written once), and its status says why."""
    number = int(attempt.name.rpartition("-")[2])
    paused = [a for a in attempts(base) if int(a.name.rpartition("-")[2]) < number and (a / "status.json").exists()]
    if not paused or not recovered(paused[-1]):
        return None, None
    recovery = read_json(paused[-1] / "recovery.json")
    try:
        if release_check(paused[-1], recovery["decision"]) is None:
            return None, None
    except ValueError as refused:  # its message is fixed text and an attempt name, never a test text
        return {"attempt": paused[-1].name, "refused": str(refused)}, None
    scan = verified(read_json(paused[-1] / "scan.json"), "root-canary-scan")
    return {"attempt": paused[-1].name, "scan_sha256": scan[RECORD_HASH], "recovery_sha256": digest(recovery)}, scan


def _same_hits(scan, released):
    """Whether ``scan`` found exactly the released scan's hits: the same canaries and the same list of hits (place, path
    and canary of each, ``hits_sha256``)."""
    keys = ("hits", "hits_sha256", "canaries_sha256")
    return released is not None and all(scan[key] == released.get(key) for key in keys)


def _root_scanned(root, chain_root, chain, *, evidence, configuration=None):
    """Registrar decision C3-1 (b): before the chain's first unseal (every chain of the root has ended), the whole run
    root is searched for every registered canary (``load_canaries(read=True)``, ``root_scan`` with ``scan_workers``
    processes) in a new attempt ``<chain root>/root-scan/attempt-N``, whose ``scan.json`` (``root-canary-scan``) is
    written once: files scanned, hits by place and by bench, the digest of every hit (``hits_sha256``), the first
    ``ROOT_SCAN_SHOWN`` hits as place, path and canary index -- never text. A hit pauses for the owner (``status.json``,
    kind ``canary_hit``) and no score is read; every later unseal of the chain raises ``awaiting_owner_decision`` until
    the owner's decision is recorded in that attempt (``recovery.json``, ``run_execskill.py recover``), then scans
    again. Registrar decision PR-C31-3 (1b): when that decision releases the paused scan (``release <its
    record_sha256>``, ``release_check``), a later scan that finds exactly the same hits (``_same_hits``) is accepted;
    a scan with any other hits, or after a release that names another scan (``_release``), pauses again (its status
    names that release), and another chain's scan is its own. Returns {"attempt", "record_sha256", "release"} of the
    accepted scan -- "release" None for a clean scan, else {"attempt", "scan_sha256", "recovery_sha256"} of the
    owner's release; a chain already unsealed: its marker's, verified again (a release's recovery file included)."""
    base = chain_root / ROOT_SCAN
    if (chain_root / UNSEALED).exists():
        scan = verified(read_json(chain_root / UNSEALED), "unseal")["canary_scan"]
        found = verified(read_json(base / scan["attempt"] / "scan.json"), "root-canary-scan")
        release, released = _release(base, base / scan["attempt"]) if found["hits"] else (None, None)
        require(found[RECORD_HASH] == scan["record_sha256"] and scan.get("release") == release
                and (found["hits"] == 0 or _same_hits(found, released)),
                "The chain was unsealed after a clean or owner-released run-root canary scan")
        return scan
    unit = "%s/%s" % (chain, ROOT_SCAN)
    with exclusive(base / ".lock"):
        attempt = _scan_attempt(base)
        if attempt is None:
            raise Pause("awaiting_owner_decision", attempts(base)[-1].name, unit)
        release, released = _release(base, attempt)
        attempt.mkdir()
        first, second = _canary_records(root, read=True, configuration=configuration)
        canaries = first["canaries"] + (second["canaries"] if second is not None else [])
        benches = _benches(first, second)
        missing = []
        scan_options = {"configuration": configuration, "vanished": missing} if profiles.is_v214(configuration) else {}
        files, hits = root_scan(root, canaries, workers=scan_workers(), **scan_options)
        value = record("root-canary-scan", evidence, {
            "chain": chain, "files_scanned": files, "hits": len(hits), "files_hit": len({h["path"] for h in hits}),
            "hits_sha256": digest(hits), "canaries": len(canaries), "canaries_sha256": digest(canaries),
            "by_where": dict(sorted(Counter(h["where"] for h in hits).items())),
            "by_bench": dict(sorted(Counter(benches[h["canary"]] for h in hits).items())),
            "shown": hits[:ROOT_SCAN_SHOWN],
            **({"vanished": len(missing), "vanished_paths": missing} if profiles.is_v214(configuration) else {})})
        write_json(attempt / "scan.json", value)
        if hits and not _same_hits(value, released):
            covered = "" if release is None else "; the owner's release in %s does not cover them" % release["attempt"]
            _paused(attempt, evidence, "canary_hit", "%d canary hits in %d files of the run root%s" % (
                len(hits), value["files_hit"], covered), scan_sha256=value[RECORD_HASH], release=release)
            raise Pause("canary_hit", "%d hits" % len(hits), unit)
    return {"attempt": attempt.name, "record_sha256": value[RECORD_HASH], "release": release if hits else None}


def unseal(root, chain_root, chain, unit_roots, *, run, evidence, clock=_now, configuration=None):
    """{"label", "later_reads", "units": {bench: {(arm, task_id, run): {"token", "v2", "official", "final",
    "lenient", "kind", "shared_with", "shared_arm", "answered", "enabled", "block", "room", "format", "flags",
    "carrier", "fault_kinds", "worst_delivery", "dispatch_ts", "finish_ts", "completion_tokens", "solver_route"}}}} --
    and in a stage read "stages": {bench: the rows of its stage table} -- of the chain's completed read units of
    ``run`` -- once EVERY chain of the run root is complete or terminated (no chain's scores are seen while another
    chain still decides; isolation review 12), the owner's continuation file exists (Codex F17) and the whole run root
    passed the canary scan (``_root_scanned``, registrar decision C3-1 (b): a hit pauses for the owner, before any
    score is read, unless the owner released exactly that scan, registrar decision PR-C31-3 (1b)); the first unseal
    writes the chain's marker, which names that scan and the release."""
    chain_root = safe_path(chain_root)
    require(_ended(chain_root), "Test scores stay sealed until the chain is complete or terminated")
    if profiles.is_v214(configuration):
        require(all(_ended(safe_path(root) / name) for name in CHAINS),
                "main-v5 test scores stay sealed until both chains have ended")
    require(all(_ended(safe_path(root) / name) for name in CHAINS if (safe_path(root) / name).exists()),
            "Test scores stay sealed until every chain of the run root is complete or terminated")
    continuation(root)
    scan = _root_scanned(safe_path(root), chain_root, chain, evidence=evidence, configuration=configuration)
    units, stages = {}, {}
    for unit_root in unit_roots:
        unit_root = safe_path(unit_root)
        own = verified(read_json(unit_root / "unit.json"), "evaluation")
        require(chain_root in unit_root.parents and own["chain"] == chain and own["run"] == run,
                "A unit of another chain or run")
        cells, arm_of = {}, {}
        for cell in own["cells"]:
            value = verified(read_json(unit_root / own["attempt"] / "cells" / (cell + ".json")), "evaluation-cell")
            key = (value["cell"]["arm"], value["cell"]["task_id"], value["cell"]["run"])
            require(key not in cells, "One cell per arm, item and run")
            arm_of[value["cell"]["id"]] = value["cell"]["arm"]
            judged = value["judge"]
            cells[key] = {"token": value["final"]["token"], "v2": judged["v2"], "official": judged["official"],
                          "final": judged["final"], "lenient": judged["lenient"], "kind": value["final"]["kind"],
                          "shared_with": value["shared_with"], "answered": value["answered"],
                          "enabled": value["enabled"], "block": value["cell"]["block"],
                          "room": value["cell"].get("room"),
                          "format": judged["format"], "flags": judged["flags"], "carrier": judged["carrier"],
                          "fault_kinds": value["fault_kinds"], "worst_delivery": value["worst_delivery"],
                          "dispatch_ts": value["dispatch_ts"], "finish_ts": value["finish_ts"],
                          "completion_tokens": [c["completion_tokens"] for c in value["calls"]],
                          "solver_route": value.get("solver_route")}
        for value in cells.values():  # the arm whose cell a shared cell reads: C's, or in a stage read F's or S<j>'s
            value["shared_arm"] = None if value["shared_with"] is None else arm_of[value["shared_with"]]
        units[own["bench"]] = cells
        if "stages" in own:
            stages[own["bench"]] = list(own["stages"]["rows"])
    marker = _marker(root, chain_root, evidence=evidence, clock=clock, scan=scan)
    return {"label": marker["label"], "later_reads": marker["later_reads"], "units": units,
            **({"stages": stages} if stages else {})}


def _make_zebra_canaries(root, pinned, *, pools, run, evidence, panel, configuration=ZEBRA_PC_V1):
    """The single-panel canary record is created only under end-of-chain read consent."""
    from . import zebralogic
    allowed = consent(root / "shared", configuration)
    require(set(pools or {}) == {"zebralogic"}, "Only the ZebraLogic training pool is visible")
    if panel is data.test_panel:
        panel = zebralogic.test_panel
    path = root / READ_CANARIES
    with exclusive(root / "shared" / "test-read-canaries.lock", wait=True):
        if not path.exists():
            entry = pools["zebralogic"]
            training = zebralogic.load_pool(entry["path"], expected_sha256=entry["sha256"])
            tasks, report = panel(pinned, "zebralogic", access=data.TestAccess(READ_CANARY_UNIT))
            texts = {"zebralogic": [t["public"]["question"] for t in tasks]}
            skip = training_duplicates(texts, {"zebralogic": [t["public"]["question"] for t in training]})
            found, counts = select_canaries(texts, skip=skip)
            write_json(path, record("test-read-canaries", evidence, {
                "configuration": configuration, "canaries": found, "counts": counts,
                "per_bench": CANARIES_PER_BENCH, "seed_tag": CANARY_TAG,
                "sources": {"zebralogic": "the public question"},
                "skipped": {"zebralogic": len(skip["zebralogic"])},
                "training_pools": {"zebralogic": entry["sha256"]}, "unit": READ_CANARY_UNIT,
                "run": run, "panels": {"zebralogic": report["panel_hash"]},
                "consent_sha256": digest(allowed), "extends": None}))
        value, second = _canary_records(root, read=True, configuration=configuration)
    require(second is None and value.get("run") == run and value.get("consent_sha256") == digest(allowed),
            "The isolated read canaries belong to this run and consent")
    return value


def _make_alfworld_canaries(root, pinned, *, pools, run, evidence, panel, configuration):
    """ALF-only read canaries use the historical release-relative game paths, after owner consent only."""
    from .exclusion import release_path
    allowed = consent(root / "shared", configuration)
    require(set(pools or {}) == {"alfworld"}, "Only the ALFWorld training pool is visible")
    path = root / READ_CANARIES
    with exclusive(root / "shared" / "test-read-canaries.lock", wait=True):
        if not path.exists():
            entry = pools["alfworld"]
            pool_path = safe_path(entry["path"])
            require(hashlib.sha256(pool_path.read_bytes()).hexdigest() == entry["sha256"],
                    "The ALFWorld training pool differs from its pin")
            training = read_json(pool_path)
            require(isinstance(training, list) and training, "The ALFWorld pool lists training games")
            tasks, report = panel(pinned, "alfworld", access=data.TestAccess(READ_CANARY_UNIT))
            texts = {"alfworld": [release_path(task["public"]["game_file"])[1] for task in tasks]}
            skip = training_duplicates(texts, {
                "alfworld": [release_path(task["public"]["game_file"])[1] for task in training]})
            found, counts = select_canaries(texts, skip=skip)
            write_json(path, record("test-read-canaries", evidence, {
                "configuration": configuration, "canaries": found, "counts": counts,
                "per_bench": CANARIES_PER_BENCH, "seed_tag": CANARY_TAG,
                "sources": {"alfworld": "the release-relative game path"},
                "skipped": {"alfworld": len(skip["alfworld"])},
                "training_pools": {"alfworld": entry["sha256"]}, "unit": READ_CANARY_UNIT,
                "run": run, "panels": {"alfworld": report["panel_hash"]},
                "consent_sha256": digest(allowed), "extends": None}))
        value, second = _canary_records(root, read=True, configuration=configuration)
    require(second is None and value.get("run") == run and value.get("consent_sha256") == digest(allowed),
            "The isolated read canaries belong to this run and consent")
    return value
