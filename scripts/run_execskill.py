"""Command line of route B, protocol fivebench-execskill-v1 (docs/handoff/execskill-registration-v1-20261021.md;
implementation plan §6, §10). Pattern of scripts/run_coevo5.py:238-311. Every invocation first removes
OPENAI_API_KEY and OPENAI_BASE_URL from its environment and sets PYTHONDONTWRITEBYTECODE=1, so every child it starts
inherits that (``prelaunch.launch_env``); run it as ``python -B`` from the verified snapshot.

Before the pilot (zero calls unless stated):
  verify-snapshot --list L --root R --git-head H   the snapshot against its sha256 list, no .env files (plan §10.1)
  zero-call-checks --root R                         the S0 pytest row on the snapshot
  leftovers                                         route-B containers and processes left (owner #3: D3/D14 apart)
  sandbox-selftest --out DIR --items F ...          S0: escape probe, 13 env keys, VSZ/RSS, start latency, view p99
  import-texts --source F --out DIR                 the v3 task cards (exactly fivebench-coevolution-v3-texts-import)
  import-sheet-qualification --source F --sha256 H --out DIR
                                                    the v3 training qualification, re-verified (zero calls)
  make-items --bench alfworld|searchqa --history-root H ... [--dry-run]
                                                    the registrar's supply file (dry run: counts only)
  exclude-tests --root R --pinned F --searchqa-supply F --alfworld-supply F
                                                    S0 test exclusion under the owner's exclusion consent; persists the
                                                    two records and the test canaries (counts and hashes only)
  s0-pool-views --manifest V3 --out F              S0: public-view bytes of the five training pools (p99 workbook)
  export-pools --manifest V3 --out NEWDIR [--alfworld-supply F] [--alfworld-views F]
                                                    the five pools in supply order, written once with pools.json:
                                                    SearchQA, OfficeQA, LiveMath, SpreadsheetBench from v3 (train +
                                                    val, never test), ALFWorld from the fresh supply and its views
                                                    (registrar 17:0x; $HIST/supply/alfworld-xs*.json by default);
                                                    prints counts, sha256, the data.pools pins
  sheet-runtime --manifest V3 --engine-qualification Q --out F
                                                    the pins' runtime.spreadsheetbench on this snapshot's engine
                                                    qualification, revalidated offline (ticket C7b1-3)
  make-fixtures --out DIR [--p99-workbook-bytes N] the registrar's 20 OfficeQA/LiveMath/SpreadsheetBench fixtures
  smoke-items --out DIR --searchqa-pool F --alfworld-supply F --alfworld-views F --data-root D --fixtures DIR
                                                    the five smoke item sets (§10), the real ones registered (smoke);
                                                    the SearchQA pool is export-pools' searchqa.json
  s0-collect --root R --items SET=FILE ... --fixtures DIR --selftest F --pins-out F --manifest V3
             --sheet-source F --sheet-sha256 H --engine-qualification Q --texts F --sheet-runtime F [--fake]
                                                    every S0 row once: <root>/s0/*.json, checks.json, the pins' limits;
                                                    the equivalence row on the imported cards (--texts) and the pinned
                                                    runtimes (v3's, SpreadsheetBench --sheet-runtime; Codex #13)
  smoke-make --root P/smoke --items SET=FILE ... --selftest F [--control-cells F] [--noise-anchor F] [--dry-run]
             [--probe-root R] [--solver-chain D|G] [--example]
                                                    the sealed smoke specification (§10, trimmed by the registrar's
                                                    addendum 13:0x: stages S0, S1, S2, S3, SE6; control cells default
                                                    [], no noise anchor without S-N1; the probe root P/probe unless a
                                                    rehearsal names its own, 15:0x); --solver-chain G (registrar
                                                    addendum 2026-10-23 02:3x): GLM-5.3 is the smoke solver -- stages
                                                    S0, S2, S3, SE6, no S1, no probe root, no control cells (D, the
                                                    default, is unchanged); --example (v2, owner decision
                                                    2026-10-23 13:3x): the stages plus SX, the example of the
                                                    train-then-accept step, with the example caps
  probe --spec S --env-path F [--probe-root R] [--fake]
                                                    S1 on the spec's probe ledger root (paid: <= 60 calls; counts
                                                    only); --fake: the zero-call rehearsal, no credential (15:0x); a
                                                    chain-G smoke has no S1 and is refused
  smoke --spec S --stage S0|S1 --input F            judge S0's or S1's measured inputs and record it once (S2, S3 and
                                                    S-E6 only through smoke-run, registrar addendum 15:0x)
  smoke-run --spec S --manifest M --stage S2|SN1|S3|S4|SE6|SX [--fake] [--env-path F] [--roles-repo D]
                                                    dispatch one paid smoke stage (smoke.run_stage; recorded once);
                                                    exit 0 passed, 3 failed or stopped (a stopped unit is printed);
                                                    --fake names no credential (ticket C7d-3); a chain-G smoke names
                                                    chain G's credential repository as --env-path and --roles-repo
  smoke-recovery --spec S --attempt A --decision TEXT   the S4 drill's owner-format recovery.json (operator only)
  smoke-summary --spec S                            smoke-result.json once every stage of the spec is recorded
  smoke-waiver --spec S                             the owner's smoke waiver beside the sealed smoke-result (registrar
                                                    addendum 2026-10-23 05:3x; zero calls, writes nothing): prints
                                                    "absent", or "valid" with its rows and sha256; else refused
  test-read-estimate --smoke R --out F [--configuration C]
                                                    the S-E6-corrected test-read estimate of the passed smoke at R
                                                    (or of one under the owner's valid smoke waiver, 10/23 05:3x)
                                                    (registrar addendum 14:10, row 8), a sealed record written once
                                                    to F: the run pins' data.test_read_estimate and its per-bench
                                                    terms, data.test_read_terms (ticket P2C-2), for the configuration
                                                    S-E6 projected (refused if it is not C; registrar 17:0x)
  make-manifest --out M --pins F --exclusion-root R --s0-pins F
                                                    the launch manifest (plan §2.9) from the operator's pins file
                                                    (with its run configuration: default, recommended or main);
                                                    writes the run root's shared/test-canaries.json; refuses a v7
                                                    SpreadsheetBench runtime that does not revalidate (C7b1-3)
  consent --root R                                  validates the owner's consent files; writes nothing
  replay --package P --trajectories UNIT            each procedure's zero-crash replay over a unit's trajectories

Runs (delegated to the chain modules, ticket A13-1):
  run --manifest M --chain G|D                      a chain until it completes or pauses
  step-unit / evaluate-unit --manifest M --spec S   one child unit
  terminate --manifest M --chain C --decision TEXT  the owner's decision
  continuation-check --manifest M --chain C         the owner's continuation file and the formal addendum
  report --manifest M --out NEWDIR                  the registered readouts
  seal-addendum --manifest M                        the owner's formal-chain addendum, sealed once (§8.1)

Owner decisions and views:
  recover --attempt A --decision TEXT               the owner's recovery decision for a paused attempt (a unit's, or
                                                    a run-root canary scan's: <root>/<chain>/root-scan/attempt-N;
                                                    there also "release <scan record_sha256>", PR-C31-3); refused for
                                                    a finished acceptance round (C7e-2, addendum 14:10 row 17)
  resume-ledger --root R --chain G|D|smoke --decision TEXT
                                                    admit reservations again after a halt of that ledger
  switch-route --manifest M --chain D --to B [--reason TEXT]
                                                    chain D's next route (registrar row "deepseek route B"): only an
                                                    idle chain whose latest pause is balance_exhausted (or with a
                                                    reason); prints the recover and run commands that follow
  show-package --package P                          a package's procedures and hooks
  monitor --root R                                  units, open attempts, run-root canary scans (hits) and every
                                                    ledger -- never a score
"""
from __future__ import annotations

import argparse
import datetime
import functools
import hashlib
import importlib
import inspect
import json
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skillopt.coevo5 import data  # noqa: E402
from skillopt.coevo5 import prelaunch as frozen_prelaunch  # noqa: E402
from skillopt.coevo5.budget import Budget  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.execskill import (  # noqa: E402
    acceptance,
    budgets,
    chain,
    client,
    evaluation,
    exclusion,
    fixtures,
    manifest,
    package,
    prelaunch,
    profiles as protocol,
    qualify,
    replay,
    routes,
    runcli,
    s0,
    smoke,
    supply,
    trajectories,
)
from skillopt.execskill import protocol as historical_protocol  # legacy runtime overrides remain observable
from skillopt.execskill.errors import ConfigurationError  # noqa: E402
from skillopt.execskill.sandbox import client as sandbox  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

# ticket A13-1: the entry point the delegated subcommand calls (module, function); the run subcommands are runcli's
ENTRY = {"continuation-check": ("evaluation", "continuation_check")}
# registrar addendum 2026-10-22 15:0x: the manual stage record (``smoke --stage --input``) is for S0 and S1 only; S2,
# S3 and S-E6 run only through ``smoke-run`` (run units, the GLM projection, the leftovers rows)
MANUAL_STAGES = ("S0", "S1")
STAGE_INPUTS = {"S0": ("checks",), "S1": ("probes",)}
# §2.2: the five task cards (the v3 I-ds instructions), by length and sha256 prefix as registered
CARD_IDENTITY = {"searchqa": (1_846, "48b10afc"), "officeqa": (2_926, "2e92500a"), "livemath": (2_068, "9cb3d860"),
                 "spreadsheetbench": (2_907, "48a5df7f"), "alfworld": (2_301, "5ae6ea9b")}
# the S0 test-exclusion unit (registration §8.1, §10 S0; tickets fixer-4, fixer-8)
EXCLUSION_DIR = protocol.EXCLUSION_DIR  # shared/exclusion (ticket C6b-3)
EXCLUSION_UNIT = "smoke/s0/test-exclusion"
CANARY_FILE = "test-canaries.json"
CANARY_SOURCES = {"searchqa": "the public question", "alfworld": "the game file path inside the release"}


def clean_environment(environ=None):
    """Plan §6: OPENAI_API_KEY and OPENAI_BASE_URL removed, PYTHONDONTWRITEBYTECODE=1, in this process (and so in
    every child it starts)."""
    environ = os.environ if environ is None else environ
    cleaned = prelaunch.launch_env(environ)
    for key in list(environ):
        if key not in cleaned:
            del environ[key]
    environ.update(cleaned)
    sys.dont_write_bytecode = True


def _print(value):
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False))


def verify_snapshot(args):
    _print(prelaunch.verify_snapshot(args.list, root=args.root, git_head=args.git_head))


def zero_call_checks(args):
    found = prelaunch.zero_call_checks(args.root)
    _print({key: found[key] for key in ("returncode", "summary", "passed")})
    return 0 if found["passed"] else 1


def leftovers(args):
    found = prelaunch.leftovers()
    _print(found)
    return 0 if found["verdict"] != "leftovers" else 1


# ------------------------------------------------------------------------------------------------ S0 (zero calls)
def sandbox_selftest(args):
    value = smoke.sandbox_selftest(args.out, item_files=args.items)
    _print({"selftest": str(Path(args.out) / smoke.SELFTEST), "escape_rows": value["escape_rows"],
            "measured": value["measured"], "passed": value["passed"]})
    return 0 if value["passed"] else 3


def import_texts(args):
    """§2.2: the v3 task cards by value. The source must be exactly a ``fivebench-coevolution-v3-texts-import``
    record, verified in place by the frozen ``coevo5.prelaunch.verify_texts`` (zero calls; its own source verified
    again); the five instructions are the cards, checked against the registered lengths and sha256 prefixes."""
    out = safe_path(args.out)
    require(not out.exists(), "The import goes to a new directory")
    found = frozen_prelaunch.verify_texts(args.source)
    require(found["version"] == protocol.TEXTS_IMPORT, "Not a %s record" % protocol.TEXTS_IMPORT)
    cards = found["instructions"]
    require(set(cards) == set(CARD_IDENTITY), "One card per bench")
    shas = {bench: hashlib.sha256(text.encode("utf-8")).hexdigest() for bench, text in cards.items()}
    for bench, (chars, prefix) in CARD_IDENTITY.items():
        require(len(cards[bench]) == chars and shas[bench].startswith(prefix),
                "The %s card is not the registered one (length or sha256 prefix)" % bench)
    value = protocol.record("texts-import", "smoke", {
        "cards": dict(cards), "card_sha256": shas, "source": {
            "path": str(safe_path(args.source)), "version": found["version"], "record_hash": found["record_hash"]}})
    out.mkdir(parents=True)
    write_json(out / "texts.json", value)
    _print({"texts": str(out / "texts.json"), "cards": {b: {"chars": len(t), "sha256": shas[b][:8]}
                                                        for b, t in sorted(cards.items())}})


def import_sheet_qualification(args):
    """§1 (owner #7), §10 S0: the v3 SpreadsheetBench training qualification, read through ``qualify.IMPORTABLE`` and
    re-verified against the pinned hash (zero calls); the import record names it by path and hash."""
    out = safe_path(args.out)
    require(not out.exists(), "The import goes to a new directory")
    found = qualify.load(args.source)
    require(found["side"] == "train", "The imported qualification is the training side's")
    qualify.reverify(found, pinned=args.sha256)
    counts = qualify.summary(found)
    value = protocol.record("sheet-qualification-import", "smoke", {
        "source": {"path": str(safe_path(args.source)), "version": found["version"],
                   "record_digest": qualify.record_digest(found)},
        "summary": counts, "reverified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    out.mkdir(parents=True)
    write_json(out / "sheet-qualification-import.json", value)
    _print({"import": str(out / "sheet-qualification-import.json"), "summary": counts})


def _alfworld_items(args):
    items = supply.alfworld_items(args.data_root, read_json(args.pool_games))
    sources = {"data_root": str(safe_path(args.data_root)), "pool_games_sha256": manifest._sha(safe_path(args.pool_games))}
    return supply.supply_record("alfworld-xs", "alfworld", items, sources=sources, evidence="smoke")


def _searchqa_items(args):
    """The SearchQA tail supply; its sources pin the fresh manifest, the dataset and revision, the cache files, the
    exclusion file's sha256 and the ``datasets`` version that loaded it (OPS1 provenance gap)."""
    import datasets  # the frozen builder's loader (make_searchqa_fresh_sample.py:128-130)

    dataset = datasets.load_dataset(args.dataset, revision=args.revision)
    items = supply.searchqa_tail(args.fresh_manifest, dataset, exclude=read_json(args.exclude),
                                 cache_sha256=read_json(args.cache_sha256))
    sources = {"fresh_manifest_sha256": manifest._sha(safe_path(args.fresh_manifest)), "dataset": args.dataset,
               "revision": args.revision, "cache_sha256": read_json(args.cache_sha256),
               "exclude_sha256": manifest._sha(safe_path(args.exclude)), "datasets_version": datasets.__version__}
    return supply.supply_record("searchqa-tail", "searchqa", items, sources=sources, evidence="smoke")


def make_items(args):
    """Plan §10 S0: the supply file of ALFWorld's new games or the SearchQA tail (a dry run prints counts only). For
    ALFWorld the routing views of the cut slices only (smoke 12, run 60, accept 150, select 200) are pre-reset with
    zero model calls (``supply.prereset``) and written once beside the supply."""
    require(args.bench in ("alfworld", "searchqa"), "make-items explicitly supports ALFWorld and SearchQA only; use zpc-s0")
    value = (_alfworld_items if args.bench == "alfworld" else _searchqa_items)(args)
    shown = {"bench": args.bench, "counts": value["counts"], "written": not args.dry_run}
    if not args.dry_run:
        shown["supply"] = str(supply.write_supply(args.history_root, value))
        if args.bench == "alfworld":
            items = value["items"]
            cut = supply.slices("alfworld", supply.order("alfworld", items), supply.registered_sizes("alfworld"))
            runtime = read_json(args.runtime)
            views = supply.prereset(items, cut, reset=supply.alfworld_reset(args.data_root, runtime))
            path = safe_path(args.history_root) / "supply" / "alfworld-xs-views.json"
            # M round 18:2x (M2b): the views record carries the digest of the runtime the resets ran with
            write_json(path, supply.views_record(value, views, cut, runtime=runtime))
            shown.update(views=str(path), preset=len(views))
    _print(shown)


def make_canaries(texts, *, unit, consent_record):
    """The registered test canaries (§8.1, Codex F16; ticket fixer-4): per test set opened in the exclusion unit,
    ``evaluation.select_canaries`` (``evaluation.CANARIES_PER_BENCH`` texts of at least
    ``evaluation.MIN_CANARY_CHARS`` characters in a seeded order), stored as lengths and sha256 prefixes only
    (``evaluation.canary``); a sealed ``test-canaries`` record. The test read's second record uses the same selection
    (``evaluation.make_read_canaries``, registrar decision C3-1 (b); ticket PR-C31-1)."""
    found, counts = evaluation.select_canaries(texts)
    return protocol.record("test-canaries", "smoke", {
        "canaries": found, "counts": counts, "per_bench": evaluation.CANARIES_PER_BENCH,
        "seed_tag": evaluation.CANARY_TAG, "sources": {bench: CANARY_SOURCES[bench] for bench in counts},
        "unit": unit, "consent_sha256": digest(consent_record)})


def exclude_tests(args):
    """§8.1, §10 S0 (tickets fixer-4, fixer-8): the two test-exclusion runs under the owner's exclusion consent (checked
    before any test access exists), with one TestAccess for this unit only; their records and the test canaries (made
    from the same two test sets) written once under ``<root>/shared/exclusion/``. Prints counts and hashes only."""
    root = safe_path(args.root)
    consent_path = root / protocol.EXCLUSION_CONSENT
    consent_record = exclusion.exclusion_consent(consent_path)
    pinned = read_json(args.pinned)
    searchqa = protocol.verified(read_json(args.searchqa_supply), "supply")
    alfworld = protocol.verified(read_json(args.alfworld_supply), "supply")
    require(searchqa["name"] == "searchqa-tail" and alfworld["name"] == "alfworld-xs", "The two supply files")
    access = data.TestAccess(EXCLUSION_UNIT)
    records = {
        exclusion.SEARCHQA_RUN: exclusion.exclude_tests(pinned, searchqa["items"], access=access, consent=consent_path),
        exclusion.ALFWORLD_RUN: exclusion.alfworld_test_identity(pinned, alfworld["items"], access=access,
                                                                 consent=consent_path)}
    questions, _ = data.test_panel(pinned, "searchqa", access=access)
    games, _ = data.test_panel(pinned, "alfworld", access=access)
    texts = {"searchqa": [task["public"]["question"] for task in questions],
             "alfworld": [exclusion.release_path(task["public"]["game_file"])[1] for task in games]}
    canaries = make_canaries(texts, unit=EXCLUSION_UNIT, consent_record=consent_record)
    folder = root / EXCLUSION_DIR
    for run, value in records.items():
        write_json(folder / (run + ".json"), value)
    write_json(folder / CANARY_FILE, canaries)
    _print({"records": {run: {"counts": v["counts"], "exclusion_sha256": v["exclusion_sha256"],
                              "record_sha256": v[protocol.RECORD_HASH]} for run, v in records.items()},
            "canaries": {"counts": canaries["counts"], "record_sha256": canaries[protocol.RECORD_HASH]}})


def exclusion_records(root):
    """The persisted S0 exclusion records and canaries of ``root`` (``exclude-tests``), verified: both runs of one
    consent, the SearchQA digest intact, the ALFWorld test set disjoint, the canaries sealed. {name: (path, record)}."""
    folder = safe_path(root) / EXCLUSION_DIR
    found = {run: verify_kind(folder / (run + ".json"), exclusion.RECORD_KIND) for run in protocol.EXCLUSION_RUNS}
    found["test_canaries"] = verify_kind(folder / CANARY_FILE, "test-canaries")
    searchqa, alfworld = found[exclusion.SEARCHQA_RUN][1], found[exclusion.ALFWORLD_RUN][1]
    require(searchqa["run"] == exclusion.SEARCHQA_RUN and searchqa["exclusion_sha256"] == digest(searchqa["dropped"])
            and alfworld["run"] == exclusion.ALFWORLD_RUN and alfworld["disjoint"] is True
            and len({value["consent_sha256"] for _, value in found.values()}) == 1,
            "The exclusion records are not one consented, passing S0 unit")
    return found


def verify_kind(path, kind):
    path = safe_path(path)
    require(path.is_file(), "Missing record: %s" % path.name)
    return path, protocol.verified(read_json(path), kind)


# --------------------------------------------------------------------------------------------------------- smoke
def smoke_make(args):
    items = dict(entry.split("=", 1) for entry in args.items)
    require(len(items) == len(args.items), "One file per item set")
    stages = None
    if args.example:  # v2: the registered stages of the solver chain's smoke plus SX
        stages = (smoke.G_SMOKE_STAGES if args.solver_chain == "G" else smoke.SMOKE_STAGES) + ("SX",)
    spec = smoke.make(args.root, items=items,
                      control_cells=read_json(args.control_cells) if args.control_cells else [],
                      noise_anchor=read_json(args.noise_anchor) if args.noise_anchor else None,
                      selftest=args.selftest, write=not args.dry_run, probe_root=args.probe_root,
                      solver_chain=args.solver_chain, stages=stages)
    _print({"smoke": str(Path(args.root) / smoke.SPEC), "spec": spec[protocol.RECORD_HASH],
            "written": not args.dry_run, "items": {k: v["count"] for k, v in spec["items"].items()},
            "stages": spec["stages"], "control_cells": len(spec["control_cells"]),
            "noise_anchor": spec["noise_anchor"] is not None, "solver_chain": smoke.solver_of(spec).chain})


def probe(args):
    """S1 (§10): paid, at most 60 calls in all attempts, on the spec's own probe ledger root; prints counts, classes and
    the judged rows only -- never a reply or a credential. ``--fake`` (registrar addendum 2026-10-22 15:0x): the
    zero-call CLI rehearsal only -- a scripted elucid gateway (``tests/execskill_fakes.ProbeGateway``) behind the real
    client with a throwaway fake credential file and slot pool under the probe root; it names no credential, never
    runs on the registered smoke or probe root, and its attempt and S1 record carry ``smoke.REHEARSAL_EVIDENCE``. A
    chain-G smoke has no S1 and is refused (``smoke.NO_S1``, registrar addendum 2026-10-23 02:3x)."""
    spec = smoke.load(args.spec)
    smoke.require_s1(spec)  # registrar addendum 2026-10-23 02:3x: a chain-G smoke has no S1
    if args.fake:
        require(args.env_path is None, "probe --fake names no credential (registrar addendum 15:0x, as C7d-3)")
        smoke.rehearsal_roots(spec, probe=True)
        root = safe_path(spec["probe_root"])
        require(args.probe_root is None or safe_path(args.probe_root) == root,
                "The S1 probe runs on the spec's probe root, where S2 reads its receipts")
        from tests import execskill_fakes as fakes  # the rehearsal's fakes live with the tests (plan §7)

        value = smoke.run_probe(spec, env_path=fakes.fake_config(root / "rehearsal", fakes.ELUCID_MODEL)["env_path"],
                                probe_root=args.probe_root, slot_root=root / "rehearsal" / "slots",
                                transport=fakes.ProbeGateway().transport, evidence=smoke.REHEARSAL_EVIDENCE)
    else:
        value = smoke.run_probe(spec, env_path=args.env_path or protocol.ELUCID_ENV, probe_root=args.probe_root)
    classes = Counter(smoke.receipt_class(entry, spec, ledger_bound={}) for entry in smoke.entries_of(value))
    result = value["result"] or {}
    _print({"attempt": value["attempt"], "complete": value["complete"], "stopped": value["stopped"],
            "calls": len(value["sent"]), "classes": dict(classes), "rows": result.get("rows"),
            "branch": result.get("branch"), "longest": result.get("longest"), "passed": result.get("passed")})
    return 0 if value["complete"] and result["passed"] else 3


def smoke_stage(args):
    """The manual stage record of S0 (``s0-collect``'s checks) or S1 (a judged probe's rows), registrar addendum
    2026-10-22 15:0x: S2, S3 and S-E6 are recorded only by ``smoke-run``."""
    require(args.stage in MANUAL_STAGES, "smoke --stage records S0 or S1 only; S2, S3 and S-E6 run through smoke-run "
            "(registrar addendum 15:0x)")
    spec = smoke.load(args.spec)
    found = read_json(args.input)
    names = STAGE_INPUTS[args.stage]
    require(isinstance(found, dict) and set(found) == set(names), "The stage's inputs: %s" % (names,))
    if args.stage == "S0":  # the item-supply row needs the persisted, consented exclusion unit (ticket fixer-8)
        checks = dict(found["checks"])
        checks["supply"] = bool(checks.get("supply")) and _excluded(spec["root"])
        result = smoke.s0(checks)
    else:
        result = smoke.s1_probe(found["probes"])
    smoke.record(spec, args.stage, result)
    _print({"stage": args.stage, "passed": result["passed"]})
    return 0 if result["passed"] else 3


def _excluded(root):
    try:
        exclusion_records(root)
    except ValueError:
        return False
    return True


def s0_pool_views(args):
    """§10 S0 measurements, first part: the training pools' public-view bytes (``s0.pool_views_record``); its
    ``views.workbook.p99`` is ``make-fixtures --p99-workbook-bytes``."""
    value = s0.pool_views_record(args.manifest, args.out)
    _print({"pool_views": str(args.out), "record_sha256": value[protocol.RECORD_HASH], "views": value["views"]})


def smoke_items(args):
    """§10, §3.4: the five smoke item files (``s0.smoke_items``), the real ones registered in the smoke namespace
    first; prints the ``smoke-make --items`` arguments and counts only."""
    value = s0.smoke_items(args.out, searchqa_pool=args.searchqa_pool, alfworld_supply=args.alfworld_supply,
                           alfworld_views=args.alfworld_views, data_root=args.data_root, fixtures_dir=args.fixtures,
                           run_root=args.run_root, history_root=args.history_root)
    _print({"record": str(Path(args.out) / s0.ITEMS_FILE), "record_sha256": value[protocol.RECORD_HASH],
            "items": ["%s=%s" % pair for pair in sorted(value["items"].items())],
            "stages": {bench: {stage: len(ids) for stage, ids in found.items()}
                       for bench, found in value["stages"].items()}})


def s0_collect(args):
    """§10 S0 (plan §10 step 3): every zero-call row once (``s0.collect``); the supply row needs the persisted,
    consented exclusion records of the smoke root (``exclusion_records``); the sheet row needs this snapshot's engine
    qualification (``--engine-qualification``, ticket C7b1-3) unless ``--fake``. Prints the checks only."""
    require(args.fake or args.engine_qualification, "s0-collect needs --engine-qualification (this snapshot's v7 "
            "engine qualification, ticket C7b1-3) unless --fake")
    items = dict(entry.split("=", 1) for entry in args.items)
    require(len(items) == len(args.items), "One file per item set")
    cards = runtimes = None
    if not args.fake:  # Codex #13: the equivalence row on the imported cards and the pinned runtimes
        require(args.texts and args.sheet_runtime and args.manifest, "s0-collect needs --texts (import-texts' "
                "texts.json), --sheet-runtime (sheet-runtime's file) and --manifest unless --fake (Codex #13)")
        cards = imported_cards(args.texts)
        runtimes = {**read_json(args.manifest, sealed=True)["runtime"], "spreadsheetbench": read_json(args.sheet_runtime)}
    found = s0.collect(args.root, snapshot=args.snapshot, items=items, fixtures_dir=args.fixtures,
                       pins_out=args.pins_out, selftest=args.selftest, manifest_path=args.manifest,
                       traces=args.traces, sheet_source=args.sheet_source, sheet_sha256=args.sheet_sha256,
                       history_root=args.history_root, exclusion_check=exclusion_records, fake=args.fake,
                       scratch=args.scratch, engine_qualification=args.engine_qualification, cards=cards,
                       runtimes=runtimes)
    _print({"checks": found["checks"], "s0": str(Path(args.root) / s0.DIR / s0.CHECKS), "passed": found["passed"]})
    return 0 if found["passed"] else 3


def imported_cards(path):
    """{bench: card text} of an ``import-texts`` record (``texts.json``), verified: the record, and every card the
    registered one by length and sha256 prefix (``CARD_IDENTITY``)."""
    cards = protocol.verified(read_json(path), "texts-import")["cards"]
    require(isinstance(cards, dict) and set(cards) == set(CARD_IDENTITY), "One imported card per bench")
    for bench, (chars, prefix) in CARD_IDENTITY.items():
        text = cards[bench]
        require(type(text) is str and len(text) == chars
                and hashlib.sha256(text.encode("utf-8")).hexdigest().startswith(prefix),
                "The imported %s card is not the registered one" % bench)
    return dict(cards)


def sheet_runtime(args):
    """Ticket C7b1-3: the SpreadsheetBench runtime of the operator's pins (``runtime.spreadsheetbench``), written once
    at ``--out``: the v3 manifest's block with only ``recalculation.{qualification_path, qualification_sha256,
    qualification_hash}`` replaced by this snapshot's zero-call v7 engine qualification, revalidated offline by the
    frozen ``qualified_engine`` (``qualify.engine_runtime``; zero model calls)."""
    out = safe_path(args.out)
    require(not out.exists(), "The runtime goes to a new file")
    runtime = qualify.engine_runtime(read_json(args.manifest, sealed=True)["runtime"]["spreadsheetbench"],
                                     args.engine_qualification)
    write_json(out, runtime)
    _print({"runtime": str(out), "sha256": manifest._sha(out), "recalculation": runtime["recalculation"]})


def export_pools(args):
    """Tickets C6-3, C7b1-2: the five pools, written once into the new directory ``--out`` (``supply.export_pool``,
    ``supply.write_pool_export``; zero calls, never a test item): the frozen ``coevo5.data.pool`` of the v3 manifest's
    data pins in ``supply.order``, each of its registered size; SpreadsheetBench reduced to the qualified items of the
    v3 training qualification the manifest pins (re-verified against its record hash and the pool's task hashes).
    ALFWorld (registrar "Owner instructions 2026-10-22 17:0x and 17:3x", ALFWorld step; closes I1-1): the fresh supply
    ``--alfworld-supply`` with rooms and the pre-reset views ``--alfworld-views`` that ``make-items`` wrote
    (``supply.alfworld_pool``, against v3's ``runtime.alfworld``, the runtime the run pins). Prints counts, each
    file's sha256 and digests, and the ``data.pools`` pins block -- never item content."""
    v3 = read_json(args.manifest, sealed=True)
    entry = v3["sheet_qualification"]
    sheet = qualify.load(entry["path"])
    qualify.reverify(sheet, pinned=entry["record_hash"])
    fresh, views = read_json(args.alfworld_supply), read_json(args.alfworld_views)
    pools = {bench: supply.export_pool(v3["data"], bench, sheet=sheet if bench == "spreadsheetbench" else None)
             for bench in protocol.BENCHES if bench != "alfworld"}
    pools["alfworld"] = supply.alfworld_pool(fresh, views, runtime=v3["runtime"]["alfworld"])
    value = supply.write_pool_export(args.out, pools, source={
        "manifest": str(safe_path(args.manifest)), "manifest_record_hash": v3["record_hash"],
        "sheet_qualification": {"path": entry["path"], "record_hash": entry["record_hash"],
                                "summary": qualify.summary(sheet)},
        "alfworld": {"supply": str(safe_path(args.alfworld_supply)), "supply_sha256": fresh[protocol.RECORD_HASH],
                     "views": str(safe_path(args.alfworld_views)), "views_sha256": views[protocol.RECORD_HASH]}})
    _print({"record": str(safe_path(args.out) / supply.POOL_RECORD), "record_sha256": value[protocol.RECORD_HASH],
            "pools": {bench: {"counts": found["counts"], "sha256": found["sha256"], "ids_digest": found["ids_digest"],
                              "items_digest": found["items_digest"]} for bench, found in value["pools"].items()},
            "pins": {"pools": supply.pool_pins(value)}})


def smoke_run(args):
    """One paid smoke stage (§10 S2, S-N1, S3, S4, S-E6) through ``smoke.run_stage``, which writes the stage record
    once: prints its verdict (exit 0 passed, 3 failed). A unit that stopped (a cap, connectivity, the first reply not
    confirmed, the S4 drill) leaves the stage unjudged: its stopped report is printed (S4: the ``paused`` attempts
    awaiting ``smoke-recovery``) and the exit code is ``chain.EXIT_PAUSED`` (3). A real chain-G smoke stage names
    chain G's credential repository as ``--env-path`` and ``--roles-repo`` (registrar addendum 2026-10-23 02:3x; an
    omitted ``--env-path``, the elucid default, is refused there as not the manifest's)."""
    require(not args.fake or (args.env_path is None and args.roles_repo is None),
            "smoke-run --fake names no credential (ticket C7d-3)")
    env_path = None if args.fake else (args.env_path or protocol.ELUCID_ENV)
    found = smoke.run_stage(args.spec, args.manifest, args.stage, fake=args.fake, env_path=env_path,
                            roles_repo=args.roles_repo)
    if found.get("complete") is False:  # ticket C7c-1: a stopped report has no verdict
        _print({key: found[key] for key in ("stage", "stopped", "reason", "unit", "paused") if key in found})
        return chain.EXIT_PAUSED
    passed = found["result"]["passed"]
    _print({"stage": args.stage, "passed": passed})
    return 0 if passed else 3


def smoke_summary(args):
    result = smoke.summary(smoke.load(args.spec))
    _print({"stages": result["stages"], "rows": result["rows"], "passed": result["passed"]})
    return 0 if result["passed"] else 3


def smoke_waiver(args):
    """Registrar addendum 2026-10-23 05:3x (zero calls, writes nothing): the owner's smoke waiver
    (``protocol.SMOKE_WAIVER``, or ``protocol.SMOKE_WAIVER_V2`` for a smoke that requires v2's example SX
    (``smoke.waiver_name``); only the owner writes it) beside the sealed ``smoke-result.json`` of the smoke at
    ``--spec``, checked by ``smoke.waiver``: prints {"waiver": "absent"} or {"waiver": "valid", "rows", "sha256"};
    an invalid waiver, or one beside a passed result, is refused with the reason (nonzero exit)."""
    spec = smoke.load(args.spec)
    root = safe_path(spec["root"])
    require((root / smoke.RESULT).exists(), "The smoke has no sealed smoke-result.json yet (smoke-summary seals it)")
    result = protocol.verified(read_json(root / smoke.RESULT), "smoke-result")
    require(result["spec"] == spec[protocol.RECORD_HASH], "The result of another smoke")
    found = smoke.waiver(root, result)
    _print({"waiver": "absent"} if found is None else {"waiver": "valid", "rows": found["rows"],
                                                         "sha256": found["sha256"]})
    return 0


def read_estimate(args):
    """Registrar addendum 2026-10-22 14:10, row 8 (zero calls): the S-E6-corrected test-read estimate of the passed
    smoke at ``--smoke``, or of one under the owner's valid smoke waiver (registrar addendum 2026-10-23 05:3x; printed
    as ``waiver``) (``chain.read_estimate_record``: inputs and value, sealed), written once to ``--out`` -- an
    existing file is refused, never overwritten -- for the pilot pins' ``data.test_read_estimate`` and, from its
    ``terms``, ``data.test_read_terms`` (registrar addendum 15:3x, ticket P2C-2; pilot-runbook §3.3), for the run
    configuration S-E6 projected; ``--configuration`` names the one expected (main-runbook: ``main``)."""
    out = safe_path(args.out)
    require(not out.exists(), "%s exists: the test-read estimate is written once" % out)
    value = chain.read_estimate_record(args.smoke, args.configuration)
    write_json(out, value)
    _print({"out": str(out), "test_read_estimate": value["test_read_estimate"], "configuration": value["pilot"],
            "waiver": value["waiver"], "record_sha256": value[protocol.RECORD_HASH]})


# ------------------------------------------------------------------------------------------ manifest and consent
def make_manifest(args):
    """The launch manifest (plan §2.9) from the operator's pins. The persisted S0 exclusion records and canaries of
    ``--exclusion-root`` are verified and bound into ``data.exclusion`` (ticket fixer-8), and the canaries record is
    written once as the run root's ``shared/test-canaries.json`` (ticket fixer-4), before the manifest. ``--s0-pins``:
    the ``limits`` and ``measured`` that ``s0-collect`` registered (A5-1), which the operator's pins then leave out;
    without them (and without ``root``, ``data``, ``evidence``, ``configuration`` in the pins) it refuses before
    anything is written; a real run's manifest (``protocol.REAL_RUN_EVIDENCE``) goes to its configuration's run root
    (``protocol.RUN_ROOTS``: main's ``MAIN_ROOT``; registrar 17:0x).
    A ``runtime.spreadsheetbench`` of the frozen v7 scorer must revalidate offline from this checkout
    (``qualify.revalidate``, ticket C7b1-3: ``sheet-runtime`` writes one that does), checked before anything is
    written."""
    pins = read_json(args.pins)
    if args.s0_pins:
        registered = read_json(args.s0_pins)
        require(set(registered) == {"limits", "measured"} and not {"limits", "measured"} & set(pins),
                "The S0 pins give the limits and measurements; the operator's pins give neither")
        pins.update(registered)
    require({"limits", "measured"} <= set(pins), "make-manifest takes the limits and measurements that s0-collect "
            "registered: give --s0-pins (A5-1; registrar addendum 2026-10-22 15:5x R6 (d))")
    require({"root", "data", "evidence", "configuration"} <= set(pins), "The operator's pins give root, data, evidence "
            "and configuration (plan §2.9; registrar 17:0x)")
    configuration = pins.pop("configuration")
    require(configuration in protocol.CONFIGURATIONS, "Unknown run configuration: %r" % (configuration,))
    require(not protocol.is_alfworld(configuration), "Use alf-manifest with the registered ALFWorld S0 and smoke")
    require(pins["evidence"] not in protocol.REAL_RUN_EVIDENCE.values()
            or (pins["evidence"] == protocol.REAL_RUN_EVIDENCE[configuration]
                and safe_path(pins["root"]) == safe_path((protocol.RUN_ROOTS if protocol.is_zebra(configuration)
                                                               else historical_protocol.RUN_ROOTS)[configuration])),
            "A real run's manifest names its configuration's evidence label and run root (registrar 17:0x)")
    runtime = pins.get("runtime")
    sheet = runtime.get("spreadsheetbench") if isinstance(runtime, dict) else None
    if isinstance(sheet, dict) and sheet.get("spreadsheet_scorer") == qualify.SCORER:
        qualify.revalidate(sheet)  # ticket C7b1-3: before anything is written; zero calls
    if protocol.is_zebra(configuration):
        require(pins["data"].get("zebra_pc") is not None, "ZebraLogic requires its by-value registration")
        limits = {kind: sandbox.Limits(**value) for kind, value in pins.pop("limits").items()}
        record = manifest.make(args.out, evidence=pins.pop("evidence"), measured=pins.pop("measured"), limits=limits,
                               configuration=configuration, **pins)
        _print({"manifest": str(args.out), "run": record[protocol.RECORD_HASH], "root": record["root"],
                "configuration": configuration, "sealed_reads": 0})
        return
    found = exclusion_records(args.exclusion_root)
    root = safe_path(pins["root"])
    write_json(root / protocol.CANARIES, found["test_canaries"][1])
    evaluation.load_canaries(root)
    bound = {name: {"path": str(path), "record_sha256": value[protocol.RECORD_HASH]}
             for name, (path, value) in sorted(found.items())}
    pins["data"] = {**pins["data"], "exclusion": bound}
    limits = {kind: sandbox.Limits(**value) for kind, value in pins.pop("limits").items()}
    record = manifest.make(args.out, evidence=pins.pop("evidence"), measured=pins.pop("measured"), limits=limits,
                           configuration=configuration, **pins)
    _print({"manifest": str(args.out), "run": record[protocol.RECORD_HASH], "root": record["root"],
            "configuration": configuration,
            "exclusion": {name: value["record_sha256"] for name, value in bound.items()}})


def consent(args):
    root = safe_path(args.root)
    found = {}
    if (root / "shared" / "consent.json").exists():
        evaluation.consent(root / "shared")  # the read's own rule: exact key set, the registered arms (§8.1)
        found["test_read"] = "valid"
    path = root / protocol.EXCLUSION_CONSENT
    if path.exists():
        exclusion.exclusion_consent(path)
        found["exclusion"] = "valid"
    _print(found or {"consent": "none recorded"})


def replay_package(args):
    """Zero tokens: each procedure of the package replayed over a completed unit's stored trajectories in two fresh
    sandbox workers (PYTHONHASHSEED 0 and 1, two item orders; ``replay.zero_crash``). Prints counts only.
    SpreadsheetBench trajectories are refused: their hooks need the public input directories, which only the
    engineer's checks bind."""
    found = package.load(args.package)
    stored = trajectories.load_run(args.trajectories)
    require(all(t["bench"] != "spreadsheetbench" for t in stored),
            "Replaying SpreadsheetBench needs the public input directories (the engineer's checks)")
    entries = [e for e in (replay.inputs_of(t) for t in stored) if e is not None]
    workers = functools.partial(sandbox.with_worker, scratch=args.scratch)
    reports = {}
    for procedure in found.procedures:
        report, _ = replay.zero_crash(procedure, entries, workers)
        reports[procedure.id] = {key: report[key] for key in ("passed", "trajectories", "applied", "fault_count")}
    _print({"package": found.sha256, "trajectories": len(entries), "procedures": reports})
    return 0 if all(r["passed"] for r in reports.values()) else 3


def _delegated(args):
    """The delegated subcommand (ticket A13-1): the verified manifest handed to the module's entry point, which
    takes the manifest as its first parameter; a dict result is printed."""
    module_name, function = ENTRY[args.command]
    try:
        module = importlib.import_module("skillopt.execskill." + module_name)
    except ModuleNotFoundError:
        raise ConfigurationError("skillopt.execskill.%s is not in this tree (ticket A13-1)" % module_name) from None
    entry = getattr(module, function, None)
    if entry is None or next(iter(inspect.signature(entry).parameters), None) != "manifest":
        raise ConfigurationError("skillopt.execskill.%s has no %s taking the manifest (ticket A13-1)"
                                 % (module_name, function))
    value = manifest.load(args.manifest)
    options = {name: getattr(args, name) for name in ("chain", "spec", "decision", "out") if hasattr(args, name)}
    found = entry(value, **options)
    if isinstance(found, dict):
        _print(found)
    return found


def recover(args):
    """The owner's ``recovery.json`` (the frozen format {by, date, decision}) in a paused or interrupted attempt: a
    unit's, or a run-root canary scan's (``<root>/<chain>/root-scan/attempt-N``, ticket PR-C31-1). There the decision
    may also be ``release <scan record_sha256>`` (registrar decision PR-C31-3 (1b), 14:1x): it names that attempt's own
    sealed scan, whose hits paused the unseal; the next unseal scans the whole root again in a new attempt and passes
    only on exactly the released hits (ticket P2-A3-4). The rule is the one the unseal applies again
    (``evaluation.release_check``, ticket P2-A3-1): the first word "release" is reserved for it, and a release that is
    not exactly right is refused before anything is written (``recovery.json`` is write-once). An acceptance round that
    paused after its last cell -- ``acceptance_undetermined`` or an error raised by ``acceptance.decide`` -- is final
    (registrar decision C7e-2, choice 1; addendum 14:10 row 17: ``acceptance.finished_round``) and is refused too: a
    redo would reuse every block and pause again. Never automatic."""
    attempt = safe_path(args.attempt)
    require(attempt.is_dir() and attempt.name.startswith("attempt-")
            and not (attempt.parent / "unit.json").exists(), "No paused or interrupted attempt")
    finished = acceptance.finished_round(attempt)
    require(finished is None, "A finished acceptance round is final (%s; registrar decision C7e-2): no recovery.json "
            "is written, report the pause to the owner" % finished)
    evaluation.release_check(attempt, args.decision)
    write_json(attempt / "recovery.json", {"by": "owner", "date": datetime.date.today().isoformat(),
                                           "decision": args.decision})
    print("recorded in", attempt)


def resume_ledger(args):
    """The owner's resume of one halted ledger: chain G's, chain D's (one ledger per chain, ``budgets.ledger_root``,
    ticket C2-1) or the smoke's; a ledger that does not exist is refused, never created."""
    path = budgets.ledger_root(args.root, args.chain)
    require(path.is_dir(), "No ledger of %s under this root" % args.chain)
    Budget(path).resume(decision=args.decision)


def switch_route(args):
    """Registrar row "deepseek route B" (owner instructions 2026-10-22 17:3x; M4): the operator moves chain ``--chain``
    (D) to route ``--to`` (B) after one of its units paused with kind ``balance_exhausted``, or with an explicit
    ``--reason``. Refused unless the chain is idle -- its runner lock free (and held while writing) and no unit lock
    under the chain root owned (``routes.idle``, as ``chain.terminate`` checks) -- and unless the manifest pins the
    route (``clients.routes``) and the route's credential file passes the client's offline checks (read by path,
    never printed; no call). Writes the chain's next write-once route record (``routes.switch``) and prints what
    follows: ``recover`` of every open paused attempt (latest first; a balance_exhausted unit's redo then runs whole
    on the new route) and ``run``."""
    found = manifest.load(args.manifest, verify=False)
    block = routes.block_of(found, args.chain, args.to)
    model = protocol.CHAINS[args.chain]
    probe_client = client.solver_client(model, config=manifest.solver_config(found, args.chain, protocol.BENCHES[0],
                                                                             args.to))
    probe_client.http.close()  # constructed only: the credential file's checks, no request
    done = routes.switch(safe_path(found["root"]) / args.chain, to=args.to, run=found[protocol.RECORD_HASH],
                         evidence=found["evidence"], chain=args.chain, reason=args.reason)
    value, paused = done["record"], done["pause"]
    commands = ["python -B scripts/run_execskill.py recover --attempt %s --decision \"<the owner's decision: %s>\""
                % (attempt, "redo on route %s" % args.to if kind == routes.BALANCE_EXHAUSTED else "its %s pause" % kind)
                for attempt, kind in done["pauses"]]
    commands.append("python -B scripts/run_execskill.py run --manifest %s --chain %s" % (args.manifest, args.chain))
    _print({"chain": args.chain, "from": value["from"], "to": value["to"], "model": block["model"],
            "record": str(done["path"]), "record_sha256": value[protocol.RECORD_HASH],
            "paused_attempt": None if paused is None else str(paused), "next": commands})


def show_package(args):
    found = package.load(args.package)
    _print({"sha256": found.sha256, "procedures": [{"id": p.id, "hooks": list(p.hooks)} for p in found.procedures]})


def monitor(args):
    root = safe_path(args.root)
    units = sorted(str(p.parent.relative_to(root)) for p in root.rglob("unit.json"))
    open_attempts = sorted(str(p.relative_to(root)) for p in root.rglob("attempt-*")
                           if p.is_dir() and not (p.parent / "unit.json").exists()
                           and p.parent.name != evaluation.ROOT_SCAN)
    scans = {}  # per scan attempt: its hits and the record hash a release must name (P2-A3-1); never a text
    for path in sorted(root.glob("*/%s/attempt-*/scan.json" % evaluation.ROOT_SCAN)):
        found = protocol.verified(read_json(path), "root-canary-scan")
        scans[str(path.parent.relative_to(root))] = {
            "hits": found["hits"], "paused": (path.parent / "status.json").exists(),
            "decided": (path.parent / "recovery.json").exists(), "record_sha256": found[protocol.RECORD_HASH]}
    ledgers = sorted(path for path in (root / protocol.LEDGER).parent.glob("ledger*") if path.is_dir())
    _print({"complete": units, "open": open_attempts, "root_scans": scans,  # C3-1 (b)
            "ledgers": {path.name: Budget(path).snapshot() for path in ledgers}})  # G's, D's, the smoke's (C2-1)


def zpc_snapshot(args):
    from skillopt.execskill import zebra_smoke
    _print(zebra_smoke.snapshot(args.out, source=args.source, git_head=args.git_head, configuration=args.configuration))


def zpc_s0(args):
    result = s0.zebra_collect(args.out, pool=args.pool, split_manifest=args.split_manifest,
                             snapshot_root=args.snapshot, selftest=args.selftest, configuration=args.configuration)
    _print({"s0": str(Path(args.out) / "zebra-s0.json"), "passed": result["passed"],
            "slice_counts": result["slice_counts"], "sealed_reads": result["sealed_reads"]})
    return 0 if result["passed"] else 3


def zpc_manifest(args):
    from skillopt.execskill import zebra_smoke
    result = zebra_smoke.make_manifest(args.out, root=args.root, s0_file=args.s0, provenance=args.provenance,
        roles_repo=args.roles_repo, elucid_env=args.elucid_env, route_b_env=args.route_b_env,
        smoke_chain=args.smoke_chain, smoke_results=args.smoke_result, configuration=args.configuration)
    _print({"manifest": str(args.out), "run": result[protocol.RECORD_HASH], "root": result["root"],
            "launchable_chains": result["data"]["launchable_chains"], "sealed_reads": 0})


def zpc_smoke(args):
    result = smoke.zebra_stage(args.manifest, args.chain, args.stage, configuration=args.configuration)
    _print({"stage": args.stage, "chain": args.chain, "passed": result["result"]["passed"]})
    return 0 if result["result"]["passed"] else 3


def alf_snapshot(args):
    from skillopt.execskill import alf_smoke
    _print(alf_smoke.snapshot(args.out, source=args.source, git_head=args.git_head,
                             configuration=getattr(args, "configuration", protocol.ALFWORLD_V1)))


def alf_s0(args):
    from skillopt.execskill import alf_smoke
    value = alf_smoke.collect_s0(args.out, preparation_file=args.preparation, snapshot_root=args.snapshot,
                                 selftest=args.selftest, configuration=getattr(args, "configuration", protocol.ALFWORLD_V1),
                                 confirm_views=getattr(args, "confirm_views", None))
    _print({"s0": str(Path(args.out) / alf_smoke.S0_FILE), "passed": value["passed"],
            "slice_counts": value["slice_counts"], "sealed_reads": value["sealed_reads"]})
    return 0 if value["passed"] else 3


def alf_confirm_views(args):
    from skillopt.execskill import alf_confirm_views as preparation
    value = preparation.prepare(args.out, configuration=args.configuration,
                                preparation_file=args.preparation, data_root=args.data_root)
    _print({"confirm_views": str(safe_path(args.out)), "record_sha256": value[protocol.RECORD_HASH],
            "games": len(value["ids"]), "runtime_sha256": value["runtime_sha256"],
            "confirm_ids_sha256": value["confirm_ids_sha256"], "model_calls": 0})


def alf_manifest(args):
    from skillopt.execskill import alf_smoke
    value = alf_smoke.make_manifest(args.out, root=args.root, s0_file=args.s0, provenance=args.provenance,
        roles_repo=args.roles_repo, elucid_env=args.elucid_env, route_b_env=args.route_b_env,
        smoke_chain=args.smoke_chain, smoke_results=args.smoke_result,
        configuration=getattr(args, "configuration", protocol.ALFWORLD_V1))
    _print({"manifest": str(args.out), "run": value[protocol.RECORD_HASH], "root": value["root"],
            "launchable_chains": value["data"]["launchable_chains"], "sealed_reads": 0})


def alf_smoke(args):
    from skillopt.execskill import alf_smoke as stages
    value = stages.run_stage(args.manifest, args.stage, chain_id=args.chain,
                            configuration=getattr(args, "configuration", protocol.ALFWORLD_V1))
    _print({"stage": args.stage, "chain": args.chain, "passed": value["result"]["passed"]})
    return 0 if value["result"]["passed"] else 3


def parser():
    top = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = top.add_subparsers(dest="command", required=True)
    command = sub.add_parser("verify-snapshot")
    command.add_argument("--list", required=True)
    command.add_argument("--root", default=protocol.SNAPSHOT_ROOT)
    command.add_argument("--git-head", required=True)
    sub.add_parser("zero-call-checks").add_argument("--root", default=protocol.SNAPSHOT_ROOT)
    sub.add_parser("leftovers")
    command = sub.add_parser("sandbox-selftest")
    command.add_argument("--out", default=protocol.PRE_ROOT + "/s0")
    command.add_argument("--items", action="append", required=True)
    command = sub.add_parser("import-texts")
    command.add_argument("--source", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("import-sheet-qualification")
    command.add_argument("--source", required=True)
    command.add_argument("--sha256", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("make-items")
    command.add_argument("--bench", required=True, choices=("alfworld", "searchqa"))
    command.add_argument("--history-root", default=protocol.HISTORY_ROOT)
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--data-root")
    command.add_argument("--pool-games")
    command.add_argument("--runtime")
    command.add_argument("--fresh-manifest")
    command.add_argument("--dataset")
    command.add_argument("--revision")
    command.add_argument("--exclude")
    command.add_argument("--cache-sha256")
    command = sub.add_parser("exclude-tests")
    command.add_argument("--root", default=protocol.SMOKE_ROOT)
    command.add_argument("--pinned", required=True)
    command.add_argument("--searchqa-supply", required=True)
    command.add_argument("--alfworld-supply", required=True)
    command = sub.add_parser("s0-pool-views")
    command.add_argument("--manifest", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("export-pools")
    command.add_argument("--manifest", required=True)
    command.add_argument("--out", required=True)
    command.add_argument("--alfworld-supply", default=protocol.HISTORY_ROOT + "/supply/alfworld-xs.json")
    command.add_argument("--alfworld-views", default=protocol.HISTORY_ROOT + "/supply/alfworld-xs-views.json")
    command = sub.add_parser("sheet-runtime")
    command.add_argument("--manifest", required=True)
    command.add_argument("--engine-qualification", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("smoke-items")
    command.add_argument("--out", required=True)
    command.add_argument("--searchqa-pool", required=True)
    command.add_argument("--alfworld-supply", required=True)
    command.add_argument("--alfworld-views", required=True)
    command.add_argument("--data-root", required=True)
    command.add_argument("--fixtures", required=True)
    command.add_argument("--run-root", default=protocol.SMOKE_ROOT)
    command.add_argument("--history-root", default=protocol.HISTORY_ROOT)
    command = sub.add_parser("s0-collect")
    command.add_argument("--root", default=protocol.SMOKE_ROOT)
    command.add_argument("--snapshot", default=protocol.SNAPSHOT_ROOT)
    command.add_argument("--items", action="append", required=True)
    command.add_argument("--fixtures", required=True)
    command.add_argument("--selftest", required=True)
    command.add_argument("--pins-out", required=True)
    command.add_argument("--manifest")
    command.add_argument("--traces", default=s0.D3_TRACES)
    command.add_argument("--sheet-source")
    command.add_argument("--sheet-sha256")
    command.add_argument("--engine-qualification")  # required unless --fake (checked by the handler; C7b1-3)
    command.add_argument("--texts")  # import-texts' texts.json: the cards (required unless --fake; Codex #13)
    command.add_argument("--sheet-runtime")  # sheet-runtime's file (required unless --fake; Codex #13)
    command.add_argument("--history-root", default=protocol.HISTORY_ROOT)
    command.add_argument("--scratch", default="/tmp")
    command.add_argument("--fake", action="store_true")
    command = sub.add_parser("smoke-run")
    command.add_argument("--spec", required=True)
    command.add_argument("--manifest", required=True)
    command.add_argument("--stage", required=True, choices=("S2", "SN1", "S3", "S4", "SE6", "SX"))
    command.add_argument("--fake", action="store_true")
    command.add_argument("--env-path")  # real stages: protocol.ELUCID_ENV when omitted; --fake: none (C7d-3)
    command.add_argument("--roles-repo")
    smoke.add_arguments(sub)  # smoke-recovery: the S4 drill's operator step (ticket C7c-1)
    command = sub.add_parser("smoke-make")
    command.add_argument("--root", default=protocol.SMOKE_ROOT)
    command.add_argument("--probe-root")  # default protocol.PROBE_ROOT (smoke.make); a rehearsal names its own (15:0x)
    command.add_argument("--solver-chain", default="D", choices=protocol.SMOKE_SOLVER_CHAINS)  # addendum 10/23 02:3x
    command.add_argument("--example", action="store_true")  # v2: SX (owner decision 2026-10-23 13:3x)
    command.add_argument("--items", action="append", required=True)
    command.add_argument("--control-cells")  # optional, default [] (registrar addendum 13:4x)
    command.add_argument("--noise-anchor")  # not required without S-N1 (registrar addendum 13:4x)
    command.add_argument("--selftest", required=True)
    command.add_argument("--dry-run", action="store_true")
    command = sub.add_parser("probe")
    command.add_argument("--spec", required=True)
    command.add_argument("--env-path")  # real: protocol.ELUCID_ENV when omitted; --fake: none (15:0x)
    command.add_argument("--probe-root")  # the spec's probe root (default); another one is refused
    command.add_argument("--fake", action="store_true")
    command = sub.add_parser("smoke")
    command.add_argument("--spec", required=True)
    command.add_argument("--stage", required=True, choices=MANUAL_STAGES)
    command.add_argument("--input", required=True)
    sub.add_parser("smoke-summary").add_argument("--spec", required=True)
    sub.add_parser("smoke-waiver").add_argument("--spec", required=True)  # registrar addendum 2026-10-23 05:3x
    command = sub.add_parser("test-read-estimate")
    command.add_argument("--smoke", required=True)
    command.add_argument("--out", required=True)
    command.add_argument("--configuration", choices=sorted(protocol.CONFIGURATIONS))  # registrar 17:0x
    command = sub.add_parser("make-manifest")
    command.add_argument("--out", required=True)
    command.add_argument("--pins", required=True)
    command.add_argument("--exclusion-root", default=protocol.SMOKE_ROOT)
    command.add_argument("--s0-pins")
    sub.add_parser("consent").add_argument("--root", required=True)
    command = sub.add_parser("replay")
    command.add_argument("--package", required=True)
    command.add_argument("--trajectories", required=True)
    command.add_argument("--scratch", default="/tmp")
    for name in ENTRY:
        command = sub.add_parser(name)
        command.add_argument("--manifest", required=True)
        command.add_argument("--chain", required=True, choices=sorted(protocol.CHAINS))
    runcli.add_arguments(sub)
    command = sub.add_parser("recover")
    command.add_argument("--attempt", required=True)
    command.add_argument("--decision", required=True)
    command = sub.add_parser("resume-ledger")
    command.add_argument("--root", required=True)
    command.add_argument("--chain", required=True, choices=sorted(protocol.CHAINS) + [budgets.SMOKE])
    command.add_argument("--decision", required=True)
    command = sub.add_parser("switch-route")  # M4: registrar row "deepseek route B"
    command.add_argument("--manifest", required=True)
    command.add_argument("--chain", required=True, choices=sorted(routes.ROUTED))
    command.add_argument("--to", required=True, choices=sorted({r for found in routes.ROUTED.values() for r in found}))
    command.add_argument("--reason")
    sub.add_parser("show-package").add_argument("--package", required=True)
    sub.add_parser("monitor").add_argument("--root", required=True)
    command = sub.add_parser("zpc-snapshot")
    command.add_argument("--configuration", choices=(protocol.ZEBRA_PC_V1, protocol.ZEBRA_PC_V2,
                                                    protocol.ZEBRA_PC_V3, protocol.ZEBRA_PC_V4, protocol.ZEBRA_PC_V5, protocol.ZEBRA_PC_V6, protocol.ZEBRA_PC_V7),
                         default=protocol.ZEBRA_PC_V1)
    command.add_argument("--source", default=str(PROJECT_ROOT))
    command.add_argument("--out", required=True)
    command.add_argument("--git-head", required=True)
    command = sub.add_parser("zpc-s0")
    command.add_argument("--configuration", choices=(protocol.ZEBRA_PC_V1, protocol.ZEBRA_PC_V2,
                                                    protocol.ZEBRA_PC_V3, protocol.ZEBRA_PC_V4, protocol.ZEBRA_PC_V5, protocol.ZEBRA_PC_V6, protocol.ZEBRA_PC_V7),
                         default=protocol.ZEBRA_PC_V1)
    command.add_argument("--out", required=True)
    command.add_argument("--snapshot", default=str(PROJECT_ROOT))
    command.add_argument("--pool", default="/data/probe-data-20261025/split-v1/zebralogic/pool.json")
    command.add_argument("--split-manifest", default="/data/probe-data-20261025/split-v1/split-manifest.json")
    command.add_argument("--selftest")
    command = sub.add_parser("zpc-manifest")
    command.add_argument("--configuration", choices=(protocol.ZEBRA_PC_V1, protocol.ZEBRA_PC_V2,
                                                    protocol.ZEBRA_PC_V3, protocol.ZEBRA_PC_V4, protocol.ZEBRA_PC_V5, protocol.ZEBRA_PC_V6, protocol.ZEBRA_PC_V7),
                         default=protocol.ZEBRA_PC_V1)
    command.add_argument("--out", required=True)
    command.add_argument("--root", required=True)
    command.add_argument("--s0", required=True)
    command.add_argument("--provenance", required=True)
    command.add_argument("--roles-repo", required=True)
    command.add_argument("--elucid-env", required=True)
    command.add_argument("--route-b-env", required=True)
    command.add_argument("--smoke-chain", choices=("G", "D"))
    command.add_argument("--smoke-result", action="append", default=[])
    command = sub.add_parser("zpc-smoke")
    command.add_argument("--configuration", choices=(protocol.ZEBRA_PC_V1, protocol.ZEBRA_PC_V2,
                                                    protocol.ZEBRA_PC_V3, protocol.ZEBRA_PC_V4, protocol.ZEBRA_PC_V5, protocol.ZEBRA_PC_V6, protocol.ZEBRA_PC_V7),
                         default=protocol.ZEBRA_PC_V1)
    command.add_argument("--manifest", required=True)
    command.add_argument("--chain", choices=("G", "D"), required=True)
    command.add_argument("--stage", choices=("S1", "S2", "S3", "SE6"), required=True)
    command = sub.add_parser("alf-snapshot")
    command.add_argument("--configuration", choices=(protocol.ALFWORLD_V1, protocol.ALFWORLD_V2, protocol.ALFWORLD_V3, protocol.ALFWORLD_V4),
                         default=protocol.ALFWORLD_V1)
    command.add_argument("--source", default=str(PROJECT_ROOT))
    command.add_argument("--out", required=True)
    command.add_argument("--git-head", required=True)
    command = sub.add_parser("alf-s0")
    command.add_argument("--configuration", choices=(protocol.ALFWORLD_V1, protocol.ALFWORLD_V2, protocol.ALFWORLD_V3, protocol.ALFWORLD_V4),
                         default=protocol.ALFWORLD_V1)
    command.add_argument("--out", required=True)
    command.add_argument("--preparation", required=True)
    command.add_argument("--snapshot", default=str(PROJECT_ROOT))
    command.add_argument("--selftest")
    command.add_argument("--confirm-views", help="Required sealed forty-game pre-reset record for ALFWorld v2.9")
    command = sub.add_parser("alf-confirm-views")
    command.add_argument("--configuration", choices=(protocol.ALFWORLD_V4,), required=True)
    command.add_argument("--preparation", required=True)
    command.add_argument("--data-root", required=True)
    command.add_argument("--out", required=True)
    command = sub.add_parser("alf-manifest")
    command.add_argument("--configuration", choices=(protocol.ALFWORLD_V1, protocol.ALFWORLD_V2, protocol.ALFWORLD_V3, protocol.ALFWORLD_V4),
                         default=protocol.ALFWORLD_V1)
    command.add_argument("--out", required=True)
    command.add_argument("--root", required=True)
    command.add_argument("--s0", required=True)
    command.add_argument("--provenance", required=True)
    command.add_argument("--roles-repo", required=True)
    command.add_argument("--elucid-env", required=True)
    command.add_argument("--route-b-env", required=True)
    command.add_argument("--smoke-chain", choices=("D",))
    command.add_argument("--smoke-result", action="append", default=[])
    command = sub.add_parser("alf-smoke")
    command.add_argument("--configuration", choices=(protocol.ALFWORLD_V1, protocol.ALFWORLD_V2, protocol.ALFWORLD_V3, protocol.ALFWORLD_V4),
                         default=protocol.ALFWORLD_V1)
    command.add_argument("--manifest", required=True)
    command.add_argument("--chain", choices=("D",), default="D")
    command.add_argument("--stage", choices=("S1", "S2", "S3", "SE6"), required=True)
    fixtures.add_arguments(sub)
    return top


BENCH_OPTIONS = {"alfworld": ("data_root", "pool_games"),
                 "searchqa": ("fresh_manifest", "dataset", "revision", "exclude", "cache_sha256")}

HANDLERS = {"alf-confirm-views": alf_confirm_views,
            "alf-snapshot": alf_snapshot, "alf-s0": alf_s0, "alf-manifest": alf_manifest, "alf-smoke": alf_smoke,
            "zpc-snapshot": zpc_snapshot, "zpc-s0": zpc_s0, "zpc-manifest": zpc_manifest, "zpc-smoke": zpc_smoke,
            "verify-snapshot": verify_snapshot, "zero-call-checks": zero_call_checks, "leftovers": leftovers,
            "sandbox-selftest": sandbox_selftest, "import-texts": import_texts,
            "import-sheet-qualification": import_sheet_qualification, "make-items": make_items,
            "exclude-tests": exclude_tests, "make-fixtures": fixtures.make_fixtures_cli,
            "s0-pool-views": s0_pool_views, "export-pools": export_pools, "sheet-runtime": sheet_runtime,
            "smoke-items": smoke_items, "s0-collect": s0_collect, "smoke-run": smoke_run,
            "smoke-recovery": smoke.recovery_cli, "smoke-make": smoke_make, "probe": probe, "smoke": smoke_stage,
            "smoke-summary": smoke_summary, "test-read-estimate": read_estimate, "make-manifest": make_manifest,
            "consent": consent, "smoke-waiver": smoke_waiver,
            "replay": replay_package, "recover": recover, "resume-ledger": resume_ledger, "switch-route": switch_route,
            "show-package": show_package, "monitor": monitor, **{name: _delegated for name in ENTRY},
            **runcli.HANDLERS}


def main(argv=None):
    clean_environment()
    args = parser().parse_args(argv)
    if args.command == "make-items":
        needed = BENCH_OPTIONS[args.bench] + (("runtime",) if args.bench == "alfworld" and not args.dry_run else ())
        missing = [name for name in needed if getattr(args, name) is None]
        require(not missing, "make-items --bench %s needs %s" % (args.bench, ", ".join("--" + m.replace("_", "-")
                                                                                       for m in missing)))
    code = HANDLERS[args.command](args)
    return code if type(code) is int else 0


if __name__ == "__main__":
    sys.exit(main())
