"""The route-B command line (implementation plan §6, §10 step 3): ``smoke-make`` dry run and write with fakes, the stage
and summary subcommands, the launch environment (OPENAI keys unset, no bytecode), the delegated run subcommands, and
the S0/S1 subcommands: ``exclude-tests`` (persisted records and test canaries, tickets fixer-4/fixer-8) with the
``make-manifest`` binding, ``import-texts``, ``import-sheet-qualification``, ``make-items``, ``probe`` and ``replay``;
``make-fixtures``, ``s0-pool-views``, ``s0-collect``, ``smoke-run``, ``make-manifest --s0-pins`` and the runcli
subcommands (tickets C6-2, C6-3; row C7b-1); integrator I1: ``s0-collect --engine-qualification``, ``sheet-runtime``
and the ``make-manifest`` revalidation (C7b1-3), ``export-pools`` (C7b1-2, C6-3), the ``smoke-run`` verdict or stopped
report and ``smoke-recovery`` (C7c-1), and ``--help`` on every subcommand; phase 2a: the trimmed smoke's optional
``smoke-make`` inputs (registrar addenda 13:0x, 13:4x), ``smoke-run --fake`` without credentials (C7d-3), the canary
selection, ``recover``'s release of a run-root scan and ``monitor``'s scans (PR-C31-1, PR-C31-3), and the SearchQA
supply's provenance (OPS1); registrar addendum 2026-10-22 14:10 (P2C): ``test-read-estimate`` (row 8) and
``recover``'s refusal of a finished acceptance round (row 17); phase 2b (c): the manual ``smoke --stage`` path for
S0 and S1 only, ``probe --fake``, ``make-manifest`` without ``--s0-pins`` (15:5x R6 (d)), and the CLI rehearsal of
the trimmed smoke (S2 and S3 as two processes).
Offline: the environment probe, the test panels, the dataset loader, the reset and the gateway are fakes (no docker,
no sandbox, no network, no test-pool file); item files are synthetic."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import types
from argparse import Namespace
from fractions import Fraction
from pathlib import Path

import httpx
import pytest

from scripts import run_execskill as cli
from skillopt.coevo5 import data
from skillopt.coevo5.budget import Budget
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, chain, evaluation, fixtures, manifest, prelaunch, protocol, qualify, runcli,
                                s0, smoke, supply)
from skillopt.execskill.errors import ConfigurationError
from skillopt.validator_pilot.api import digest
from tests import test_execskill_smoke as smoke_tests
from tests.execskill_fakes import ELUCID_MODEL, FAKE_KEYS, fake_config

REPO = Path(__file__).resolve().parents[1]
ENVIRONMENT = {"python": "3.11.16", "openpyxl": "3.1.5", "docker": "27.3.1", "image_digests": {},
               "in_image_libs": {}, "in_image_pip_freeze_sha256": "0" * 64}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "environment", lambda **_: dict(ENVIRONMENT))
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://example.invalid")
    args = []
    for name in smoke.ITEM_SETS:
        path = tmp_path / "in" / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"task_id": name + "-1", "public": {}}]))
        args += ["--items", "%s=%s" % (name, path)]
    (tmp_path / "in" / "control.json").write_text(json.dumps(["S2/searchqa/X/fx-crash/q1/1"]))
    (tmp_path / "in" / "anchor.json").write_text(json.dumps({"searchqa": 0.3, "alfworld": 0.45}))
    return args + ["--control-cells", str(tmp_path / "in" / "control.json"),
                   "--noise-anchor", str(tmp_path / "in" / "anchor.json"),
                   "--selftest", smoke_tests.selftest(tmp_path / "in")]


def test_smoke_make_dry_run_writes_nothing_and_cleans_the_environment(tmp_path, inputs, capsys):
    root = tmp_path / "pre" / "smoke"
    assert cli.main(["smoke-make", "--root", str(root), "--dry-run", *inputs]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["written"] is False and set(shown["items"]) == set(smoke.ITEM_SETS) and not root.exists()
    assert "OPENAI_API_KEY" not in os.environ and "OPENAI_BASE_URL" not in os.environ
    assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1" and sys.dont_write_bytecode


def test_smoke_make_writes_once_then_stages_and_summary(tmp_path, inputs, test_side, capsys):
    root = tmp_path / "pre" / "smoke"
    write_json(root / protocol.EXCLUSION_CONSENT, CONSENT)  # S0's supply row needs the persisted exclusion unit
    assert cli.main(test_side.argv) == 0 and test_side.root == root
    capsys.readouterr()
    assert cli.main(["smoke-make", "--root", str(root), *inputs]) == 0
    spec = read_json(root / smoke.SPEC)
    assert json.loads(capsys.readouterr().out)["spec"] == spec["record_sha256"]
    with pytest.raises(ValueError):
        cli.main(["smoke-make", "--root", str(root), *inputs])
    checks = tmp_path / "s0.json"
    checks.write_text(json.dumps({"checks": {row: True for row in smoke.S0_ROWS}}))
    assert cli.main(["smoke", "--spec", str(root / smoke.SPEC), "--stage", "S0", "--input", str(checks)]) == 0
    roles = tmp_path / "s3.json"
    roles.write_text(json.dumps({"ran": {row: True for row in smoke.S3_ROWS}}))
    for stage in ("S2", "S3", "SE6", "SN1", "S4"):  # registrar addendum 15:0x: S2, S3, S-E6 only through smoke-run
        with pytest.raises(SystemExit):
            cli.main(["smoke", "--spec", str(root / smoke.SPEC), "--stage", stage, "--input", str(roles)])
        with pytest.raises(ValueError, match="S0 or S1 only"):
            cli.smoke_stage(Namespace(spec=str(root / smoke.SPEC), stage=stage, input=str(roles)))
    wrong = tmp_path / "s1.json"
    wrong.write_text(json.dumps({"checks": {}}))
    with pytest.raises(ValueError, match="inputs"):
        cli.main(["smoke", "--spec", str(root / smoke.SPEC), "--stage", "S1", "--input", str(wrong)])
    capsys.readouterr()
    assert cli.main(["smoke-summary", "--spec", str(root / smoke.SPEC)]) == 3
    stages = json.loads(capsys.readouterr().out)["stages"]
    assert stages["S0"] == "pass" and stages["S3"] == "missing" and stages["S1"] == "missing"
    assert not (root / smoke.STAGES_DIR / "S3.json").exists() and not (root / smoke.RESULT).exists()


def test_every_plan_subcommand_group_parses_and_run_subcommands_delegate(monkeypatch):
    parser = cli.parser()
    for argv in (["run", "--manifest", "m", "--chain", "G"], ["step-unit", "--manifest", "m", "--spec", "s"],
                 ["evaluate-unit", "--manifest", "m", "--spec", "s"], ["report", "--manifest", "m", "--out", "o"],
                 ["terminate", "--manifest", "m", "--chain", "D", "--decision", "stop"],
                 ["continuation-check", "--manifest", "m", "--chain", "G"], ["leftovers"],
                 ["verify-snapshot", "--list", "l", "--git-head", "0" * 40], ["make-manifest", "--out", "o", "--pins", "p"],
                 ["consent", "--root", "r"], ["recover", "--attempt", "a", "--decision", "redo"],
                 ["resume-ledger", "--root", "r", "--chain", "G", "--decision", "go"], ["show-package", "--package", "p"],
                 ["monitor", "--root", "r"], ["smoke-summary", "--spec", "s"], ["zero-call-checks"],
                 ["seal-addendum", "--manifest", "m"], ["make-fixtures", "--out", "o"],
                 ["s0-pool-views", "--manifest", "m", "--out", "o"],
                 ["s0-collect", "--items", "searchqa=f", "--fixtures", "d", "--selftest", "t", "--pins-out", "p"],
                 ["smoke-run", "--spec", "s", "--manifest", "m", "--stage", "SN1"]):
        assert parser.parse_args(argv).command == argv[0]
    for argv in (["run", "--manifest", "m", "--chain", "smoke"],
                 ["smoke-run", "--spec", "s", "--manifest", "m", "--stage", "S1"]):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)
    # the run subcommands are runcli's handlers (ticket C6-2); only continuation-check is delegated
    assert all(cli.HANDLERS[name] is handler for name, handler in runcli.HANDLERS.items())
    assert set(cli.ENTRY) == {"continuation-check"}

    def missing(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(cli.importlib, "import_module", missing)
    with pytest.raises(ConfigurationError, match="A13-1"):
        cli.main(["continuation-check", "--manifest", "m", "--chain", "G"])


def test_consent_validates_without_writing(tmp_path, capsys):
    shared = tmp_path / "run" / "shared"
    shared.mkdir(parents=True)
    assert cli.main(["consent", "--root", str(tmp_path / "run")]) == 0
    assert json.loads(capsys.readouterr().out) == {"consent": "none recorded"}
    (shared / "exclusion-consent.json").write_text(json.dumps(
        {"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner",
         "date": "2026-10-22", "note": "synthetic"}))
    (shared / "consent.json").write_text(json.dumps({"test_evaluation": True, "by": "owner"}))
    with pytest.raises(ValueError, match="consent"):
        cli.main(["consent", "--root", str(tmp_path / "run")])
    # the read's own rule (evaluation.consent): the exact key set is not enough, the arms must be the registered ones
    value = {"test_evaluation": True, "sheet_test_qualification": False, "multi_arm_arms": ["F", "C"], "by": "owner",
             "date": "2026-10-22", "note": "synthetic"}
    (shared / "consent.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="consent"):
        cli.main(["consent", "--root", str(tmp_path / "run")])
    (shared / "consent.json").write_text(json.dumps({**value, "multi_arm_arms": list(protocol.TEST_ARMS)}))
    capsys.readouterr()
    assert cli.main(["consent", "--root", str(tmp_path / "run")]) == 0
    assert json.loads(capsys.readouterr().out) == {"test_read": "valid", "exclusion": "valid"}
    assert sorted(p.name for p in shared.iterdir()) == ["consent.json", "exclusion-consent.json"]


def test_the_script_starts_without_the_openai_keys_and_writes_no_bytecode(tmp_path):
    env = {**prelaunch.launch_env(), "OPENAI_API_KEY": "synthetic-not-a-key"}
    done = subprocess.run([sys.executable, "-B", str(REPO / "scripts" / "run_execskill.py"), "--help"], cwd=REPO,
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    assert done.returncode == 0 and b"smoke-make" in done.stdout
    assert not list((REPO / "scripts").glob("__pycache__/run_execskill*"))


def test_recover_writes_the_owner_decision_once(tmp_path):
    attempt = tmp_path / "unit" / "attempt-1"
    attempt.mkdir(parents=True)
    cli.recover(Namespace(attempt=str(attempt), decision="redo the block"))
    assert read_json(attempt / "recovery.json")["decision"] == "redo the block"
    (tmp_path / "unit" / "unit.json").write_text("{}")
    with pytest.raises(ValueError):
        cli.recover(Namespace(attempt=str(attempt), decision="again"))


def test_resume_ledger_names_its_chain_and_monitor_shows_every_ledger(tmp_path, capsys):
    """Ticket C2-1: each chain runs on its own ledger (``budgets.ledger_root``); the owner resumes the halted one by
    name, and ``monitor`` shows every ledger of the root without creating one."""
    root = tmp_path / "run"
    ledgers = {chain: Budget(budgets.ledger_root(root, chain)) for chain in ("G", "D")}
    for chain, ledger in ledgers.items():
        ledger.declare(budgets.chain_caps(chain))
    ledgers["G"].halt("synthetic breach", label="G/s1-officeqa/run")
    with pytest.raises(ValueError, match="not halted"):
        cli.main(["resume-ledger", "--root", str(root), "--chain", "D", "--decision", "go"])
    with pytest.raises(ValueError, match="No ledger of smoke"):
        cli.main(["resume-ledger", "--root", str(root), "--chain", "smoke", "--decision", "go"])
    assert cli.main(["resume-ledger", "--root", str(root), "--chain", "G", "--decision", "owner: go on"]) == 0
    assert "halted" not in ledgers["G"].snapshot()
    capsys.readouterr()
    assert cli.main(["monitor", "--root", str(root)]) == 0
    shown = json.loads(capsys.readouterr().out)["ledgers"]
    assert sorted(shown) == ["ledger-D", "ledger-G"] and "halted" not in shown["ledger-G"]
    assert set(shown["ledger-G"]) == set(budgets.chain_caps("G")) and not (root / protocol.LEDGER).exists()


def test_delegated_entries_take_the_manifest_and_print_their_report(tmp_path, monkeypatch, capsys):
    """Integration B5: the delegated subcommand reaches only an entry whose first parameter is the manifest -- an
    entry taking a units.Setting (``chain.run``) is refused before the manifest is loaded (ticket A13-1); a dict result
    (continuation-check) is printed."""
    def no_load(path, **_):
        raise AssertionError("the manifest is loaded only for an entry that takes it")

    monkeypatch.setattr(manifest, "load", no_load)
    monkeypatch.setitem(cli.ENTRY, "continuation-check", ("chain", "run"))
    with pytest.raises(ConfigurationError, match="taking the manifest"):
        cli.main(["continuation-check", "--manifest", "m", "--chain", "G"])
    monkeypatch.setitem(cli.ENTRY, "continuation-check", ("evaluation", "continuation_check"))
    root = tmp_path / "run"
    (root / "G").mkdir(parents=True)
    monkeypatch.setattr(manifest, "load", lambda path, **_: {"root": str(root)})
    assert cli.main(["continuation-check", "--manifest", "m", "--chain", "G"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown == {"chain": "G", "ended": [], "unsealed": False, "continuation": None, "addendum": None,
                     "label": None, "later_reads": None}


# ------------------------------------------------------------------------------- S0: exclusion, canaries, manifest
QUESTIONS = ["Which river flows through the synthetic city of Examplegrad?",
             "Who wrote the synthetic novel about the lighthouse keeper?", "short one"]
TEST_GAMES = ["/x/json_2.1.1/valid_unseen/pick_and_place_simple-Book-None-Desk-308/trial_T1/game.tw-pddl",
              "/x/json_2.1.1/valid_unseen/look_at_obj_in_light-Pen-None-DeskLamp-309/trial_T2/game.tw-pddl"]
CONSENT = {"exclusion_runs": ["alfworld_test_identity_check", "searchqa_test_exclusion"], "by": "owner",
           "date": "2026-10-22", "note": "synthetic"}


@pytest.fixture
def test_side(tmp_path, monkeypatch):
    """Synthetic test panels behind ``data.TestAccess`` (no test-pool file is read) and two synthetic supply files."""
    opened = []

    def panel(pinned, bench, *, access):
        assert isinstance(access, data.TestAccess) and access.unit == cli.EXCLUSION_UNIT
        opened.append(bench)
        if bench == "searchqa":
            return [{"task_id": "t%d" % i, "public": {"question": q}} for i, q in enumerate(QUESTIONS)], {}
        return [{"task_id": "g%d" % i, "public": {"game_file": g}} for i, g in enumerate(TEST_GAMES)], {}

    monkeypatch.setattr(data, "test_panel", panel)
    monkeypatch.setattr(data, "test_ids", lambda pinned, bench: frozenset({"t0"}))
    sq_items = [{"task_id": "t0", "position": 4_001, "public": {"question": "anything"}},
                {"task_id": "s1", "position": 4_002, "public": {"question": QUESTIONS[1]}},
                {"task_id": "s2", "position": 4_003, "public": {"question": "a kept supply question"}}]
    alf_items = [{"task_id": "alfworld-xs:%016d" % i, "room": "1%02d" % i, "task_type": "pick_and_place_simple",
                  "gamefile": "json_2.1.1/train/pick_and_place_simple-Mug-None-Shelf-1%02d/trial_T%d/game.tw-pddl"
                  % (i, i)} for i in range(3)]
    files = {}
    for name, bench, found in (("searchqa-tail", "searchqa", sq_items), ("alfworld-xs", "alfworld", alf_items)):
        files[bench] = tmp_path / "history" / (name + ".json")
        write_json(files[bench], supply.supply_record(name, bench, found, sources={}, evidence="smoke"))
    (tmp_path / "pinned.json").write_text("{}")
    root = tmp_path / "pre" / "smoke"
    argv = ["exclude-tests", "--root", str(root), "--pinned", str(tmp_path / "pinned.json"),
            "--searchqa-supply", str(files["searchqa"]), "--alfworld-supply", str(files["alfworld"])]
    return types.SimpleNamespace(root=root, argv=argv, opened=opened)


def test_exclude_tests_refuses_without_consent_then_persists_records_and_canaries(test_side, capsys):
    with pytest.raises(ValueError, match="consent"):
        cli.main(test_side.argv)
    assert test_side.opened == []  # the consent is checked before any test panel is opened
    write_json(test_side.root / protocol.EXCLUSION_CONSENT, CONSENT)
    assert cli.main(test_side.argv) == 0
    shown = capsys.readouterr().out
    assert not any(text in shown for text in QUESTIONS[:2] + TEST_GAMES + ["t0", "Examplegrad"])
    printed = json.loads(shown)
    assert printed["records"]["searchqa_test_exclusion"]["counts"] == {
        "supply": 3, "test_items": 3, "dropped_by_id": 1, "dropped_by_question": 1, "kept": 1}
    assert printed["canaries"]["counts"] == {"alfworld": 2, "searchqa": 2}  # "short one" is below the minimum
    found = cli.exclusion_records(test_side.root)
    assert set(found) == {*protocol.EXCLUSION_RUNS, "test_canaries"}
    canaries = found["test_canaries"][1]
    assert canaries["version"] == "fivebench-execskill-v1-test-canaries" and canaries["evidence"] == "smoke"
    eligible = QUESTIONS[:2] + [cli.exclusion.release_path(game)[1] for game in TEST_GAMES]
    assert sorted(map(json.dumps, canaries["canaries"])) == sorted(json.dumps(evaluation.canary(t)) for t in eligible)
    files = sorted(p.name for p in (test_side.root / cli.EXCLUSION_DIR).iterdir())
    assert files == ["alfworld_test_identity_check.json", "searchqa_test_exclusion.json", "test-canaries.json"]
    for path in (test_side.root / cli.EXCLUSION_DIR).iterdir():  # counts and hashes only, never a test text
        assert not any(text in path.read_text() for text in QUESTIONS[:2] + TEST_GAMES)


def test_make_manifest_binds_the_exclusion_and_writes_the_run_roots_canaries(test_side, tmp_path, monkeypatch,
                                                                             capsys):
    write_json(test_side.root / protocol.EXCLUSION_CONSENT, CONSENT)
    cli.main(test_side.argv)
    made = {}

    def make(out, **given):
        made.update(given, out=out)
        return {protocol.RECORD_HASH: "f" * 64, "root": given["root"]}

    monkeypatch.setattr(manifest, "make", make)
    run_root = tmp_path / "pilot"
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"root": str(run_root), "data": {"supply": "x"}, "limits": {}, "evidence": "pilot",
                                "measured": {}, "configuration": "default"}))
    assert cli.main(["make-manifest", "--out", str(tmp_path / "m.json"), "--pins", str(pins),
                     "--exclusion-root", str(test_side.root)]) == 0
    assert set(made["data"]["exclusion"]) == {*protocol.EXCLUSION_RUNS, "test_canaries"}
    assert made["data"]["supply"] == "x"
    assert evaluation.load_canaries(run_root) == cli.exclusion_records(test_side.root)["test_canaries"][1]["canaries"]
    # without the persisted, consented exclusion unit there is no manifest
    with pytest.raises(ValueError, match="Missing record"):
        cli.main(["make-manifest", "--out", str(tmp_path / "m2.json"), "--pins", str(pins),
                  "--exclusion-root", str(tmp_path / "elsewhere")])


def test_the_s0_supply_row_needs_the_persisted_exclusion_unit(tmp_path, inputs, capsys):
    root = tmp_path / "pre" / "smoke"
    cli.main(["smoke-make", "--root", str(root), *inputs])
    checks = tmp_path / "s0.json"
    checks.write_text(json.dumps({"checks": {row: True for row in smoke.S0_ROWS}}))
    assert cli.main(["smoke", "--spec", str(root / smoke.SPEC), "--stage", "S0", "--input", str(checks)]) == 3
    stage = read_json(root / smoke.STAGES_DIR / "S0.json")
    assert stage["result"]["rows"]["supply"] is False and stage["result"]["rows"]["pytest"] is True


# ---------------------------------------------------------------------------------------- imports (zero calls)
def test_import_texts_accepts_exactly_the_v3_texts_import(tmp_path, monkeypatch, capsys):
    cards = {bench: "card text of %s " % bench * 20 for bench in protocol.BENCHES}
    identity = {b: (len(t), hashlib.sha256(t.encode()).hexdigest()[:8]) for b, t in cards.items()}
    found = {"version": protocol.TEXTS_IMPORT, "instructions": cards, "record_hash": "a" * 64}
    monkeypatch.setattr(cli.frozen_prelaunch, "verify_texts", lambda path: dict(found))
    source = tmp_path / "texts.json"
    source.write_text("{}")
    with pytest.raises(ValueError, match="registered one"):  # the registered lengths and sha256 prefixes (§2.2)
        cli.main(["import-texts", "--source", str(source), "--out", str(tmp_path / "a")])
    monkeypatch.setattr(cli, "CARD_IDENTITY", identity)
    assert cli.main(["import-texts", "--source", str(source), "--out", str(tmp_path / "b")]) == 0
    value = read_json(tmp_path / "b" / "texts.json")
    assert value["version"] == "fivebench-execskill-v1-texts-import" and value["cards"] == cards
    assert value["source"]["version"] == protocol.TEXTS_IMPORT
    monkeypatch.setattr(cli.frozen_prelaunch, "verify_texts",
                        lambda path: {**found, "version": "fivebench-coevolution-v3-texts"})
    with pytest.raises(ValueError, match="texts-import"):
        cli.main(["import-texts", "--source", str(source), "--out", str(tmp_path / "c")])


def test_import_sheet_qualification_reverifies_the_pinned_hash(tmp_path, capsys):
    tasks = {"sb-1": {"task_id": "sb-1"}, "sb-2": {"task_id": "sb-2"}}
    value = protocol.record(qualify.KIND, "smoke", {
        "side": "train", "tasks": 2, "qualified": ["sb-1"], "excluded": {"sb-2": "scorer"}, "counts": {},
        "scorings_per_item": qualify.PASSES, "model_calls": 0, "scorer": "qualified_lo_recalc_v7_v1",
        "recalculation": "x", "task_hashes": {k: "0" * 64 for k in tasks}})
    source = tmp_path / "qualification.json"
    write_json(source, value)
    with pytest.raises(ValueError, match="pinned"):
        cli.main(["import-sheet-qualification", "--source", str(source), "--sha256", "0" * 64,
                  "--out", str(tmp_path / "a")])
    assert cli.main(["import-sheet-qualification", "--source", str(source), "--sha256",
                     value[protocol.RECORD_HASH], "--out", str(tmp_path / "b")]) == 0
    found = read_json(tmp_path / "b" / "sheet-qualification-import.json")
    assert found["summary"]["qualified"] == 1 and found["source"]["record_digest"] == value[protocol.RECORD_HASH]


# --------------------------------------------------------------------------------------------------- make-items
def test_make_items_alfworld_dry_run_prints_counts_and_writes_nothing(tmp_path, monkeypatch, capsys):
    data_root = tmp_path / "alf"
    games = []
    for i in range(4):
        game = data_root / ("json_2.1.1/train/pick_and_place_simple-Mug-None-Shelf-1%02d/trial_T%d/game.tw-pddl"
                            % (i % 2, i))
        game.parent.mkdir(parents=True)
        game.write_text("game %d" % i)
        games.append(game)
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps({"pool-1": str(games[0])}))
    history = tmp_path / "history"
    base = ["make-items", "--bench", "alfworld", "--history-root", str(history), "--data-root", str(data_root),
            "--pool-games", str(pool)]
    assert cli.main([*base, "--dry-run"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["counts"]["items"] == 3 and shown["counts"]["rooms"] == 2 and not history.exists()
    with pytest.raises(ValueError, match="--runtime"):
        cli.main(base)
    monkeypatch.setattr(supply, "slices", lambda bench, order, sizes: {"smoke": order[:2]})
    monkeypatch.setattr(supply, "alfworld_reset", lambda root, runtime: lambda item: (
        "You are in a room.\nYour task is to: put a mug on the shelf.", ["look", "go to shelf 1"]))
    runtime = {"alfworld_data": str(data_root), "seed": 42}
    (tmp_path / "runtime.json").write_text(json.dumps(runtime))
    assert cli.main([*base, "--runtime", str(tmp_path / "runtime.json")]) == 0
    shown = json.loads(capsys.readouterr().out)
    views = protocol.verified(read_json(history / "supply" / "alfworld-xs-views.json"), supply.VIEWS_KIND)
    assert shown["preset"] == 2 and len(views["views"]) == 2 and views["slices"]["smoke"]
    assert views["runtime_sha256"] == digest(runtime)  # supply.views_record (M round 18:2x)
    assert read_json(history / "supply" / "alfworld-xs.json")["counts"]["items"] == 3


def test_make_items_searchqa_dry_run_shows_counts_only(tmp_path, monkeypatch, capsys):
    loaded = {}
    monkeypatch.setitem(sys.modules, "datasets", types.SimpleNamespace(
        load_dataset=lambda name, revision: loaded.setdefault("dataset", (name, revision)), __version__="3.4.1"))
    item = {"task_id": "sq-1", "position": 4_001, "public": {"question": "A synthetic tail question?"}}
    monkeypatch.setattr(supply, "searchqa_tail", lambda path, dataset, *, exclude, cache_sha256: [item])
    for name in ("fresh.json", "exclude.json", "cache.json"):
        (tmp_path / name).write_text("{}")
    assert cli.main(["make-items", "--bench", "searchqa", "--dry-run", "--history-root", str(tmp_path / "h"),
                     "--fresh-manifest", str(tmp_path / "fresh.json"), "--dataset", "synthetic/searchqa",
                     "--revision", "r1", "--exclude", str(tmp_path / "exclude.json"),
                     "--cache-sha256", str(tmp_path / "cache.json")]) == 0
    shown = capsys.readouterr().out
    assert json.loads(shown)["counts"] == {"items": 1} and "synthetic tail question" not in shown
    assert loaded["dataset"] == ("synthetic/searchqa", "r1") and not (tmp_path / "h").exists()
    # the written supply pins its exclusion file and the datasets version too (OPS1 provenance gap)
    (tmp_path / "exclude.json").write_text(json.dumps({"ids": ["x"], "questions": []}))
    assert cli.main(["make-items", "--bench", "searchqa", "--history-root", str(tmp_path / "h"),
                     "--fresh-manifest", str(tmp_path / "fresh.json"), "--dataset", "synthetic/searchqa",
                     "--revision", "r1", "--exclude", str(tmp_path / "exclude.json"),
                     "--cache-sha256", str(tmp_path / "cache.json")]) == 0
    written = read_json(tmp_path / "h" / "supply" / "searchqa-tail.json")
    assert written["sources"]["exclude_sha256"] == hashlib.sha256((tmp_path / "exclude.json").read_bytes()).hexdigest()
    assert written["sources"]["datasets_version"] == "3.4.1" and written["sources"]["revision"] == "r1"


# ------------------------------------------------------------------------------------------------ probe, replay
def test_probe_prints_counts_and_classes_only(tmp_path, inputs, monkeypatch, capsys):
    root = tmp_path / "pre" / "smoke"
    cli.main(["smoke-make", "--root", str(root), "--probe-root", str(tmp_path / "probe"), *inputs])
    capsys.readouterr()
    real = smoke.run_probe
    monkeypatch.setattr(smoke, "run_probe", lambda spec, **options: real(
        spec, **options, slot_root=tmp_path / "slots", transport=httpx.MockTransport(smoke_tests.Gateway())))
    env = fake_config(tmp_path, ELUCID_MODEL)["env_path"]
    assert cli.main(["probe", "--spec", str(root / smoke.SPEC), "--env-path", env,
                     "--probe-root", str(tmp_path / "probe")]) == 0
    shown = capsys.readouterr().out
    printed = json.loads(shown)
    assert printed["calls"] == 41 and printed["classes"] == {"control": 1, "probe": 40} and printed["branch"] == "E"
    assert FAKE_KEYS[ELUCID_MODEL] not in shown and "SECRET-REPLY-TEXT" not in shown


def test_probe_fake_rehearses_s1_without_a_credential_and_labels_it_a_fixture(tmp_path, inputs, monkeypatch, capsys):
    """Registrar addendum 2026-10-22 15:0x: ``probe --fake`` runs S1 on the scripted gateway behind the real client
    (zero network), names no credential, runs only on the spec's own probe root -- never the registered smoke or
    probe root -- and records its attempt and S1 as an engineering fixture, never as smoke evidence."""
    root, probe_root = tmp_path / "pre" / "smoke", tmp_path / "pre" / "probe"
    assert cli.main(["smoke-make", "--root", str(root), "--probe-root", str(probe_root), *inputs]) == 0
    spec = str(root / smoke.SPEC)
    capsys.readouterr()
    with pytest.raises(ValueError, match="names no credential"):
        cli.main(["probe", "--spec", spec, "--fake", "--env-path", "/root/.config/weak-solver/elucid.env"])
    with pytest.raises(ValueError, match="spec's probe root"):
        cli.main(["probe", "--spec", spec, "--fake", "--probe-root", str(tmp_path / "elsewhere")])
    for name, value in (("SMOKE_ROOT", str(root)), ("PROBE_ROOT", str(probe_root))):  # the registered roots
        with monkeypatch.context() as patch:
            patch.setattr(protocol, name, value)
            with pytest.raises(ValueError, match="registered smoke or probe root"):
                cli.main(["probe", "--spec", spec, "--fake"])
    assert not (probe_root / "attempts").exists() and not (root / smoke.STAGES_DIR).exists()
    assert cli.main(["probe", "--spec", spec, "--fake"]) == 0
    shown = capsys.readouterr().out
    printed = json.loads(shown)
    assert printed["calls"] == 41 and printed["classes"] == {"control": 1, "probe": 40} and printed["branch"] == "E"
    assert printed["passed"] is True and FAKE_KEYS[ELUCID_MODEL] not in shown
    attempt = protocol.verified(read_json(probe_root / "attempts" / "attempt-1.json"), "smoke-probe")
    stage = protocol.verified(read_json(root / smoke.STAGES_DIR / "S1.json"), "smoke-stage")
    assert attempt["evidence"] == stage["evidence"] == smoke.REHEARSAL_EVIDENCE == "engineering_fixture"
    assert stage["result"]["passed"] is True and stage["result"]["branch"] == "E"
    with pytest.raises(ValueError, match="already"):  # S1 is probed once, as the real probe
        cli.main(["probe", "--spec", spec, "--fake"])


@pytest.mark.parametrize("configuration", ["default", "main"])
def test_cli_rehearsal_runs_the_trimmed_smoke_end_to_end_as_an_engineering_fixture(tmp_path, monkeypatch, test_side,
                                                                                    capsys, configuration):
    """Registrar addendum 2026-10-22 15:0x (I1 phase 2b (c)): the zero-call CLI rehearsal of the trimmed smoke on the
    plan-§7 fakes, with zero network -- S0 (``smoke --stage S0`` on the persisted synthetic exclusion unit), S1
    (``probe --fake`` on the spec's own probe root), S2 and S3 as two ``smoke-run --fake`` processes side by side,
    S-E6, ``smoke-summary``, then ``test-read-estimate --configuration`` on the rehearsal root. Every record S1 to S-E6
    writes, the result and the estimate are engineering fixtures, never smoke evidence (pilot-runbook §3.3 refuses the
    estimate); S0 keeps the manual path's label, and the result is labelled by its rehearsal stages. Configuration
    ``main`` (registrar 17:0x/17:3x; integration phase M): the smoke manifest names ``main`` and pins chain D's route
    B (smoke-runbook §5), S-E6 projects main, and main-runbook §3.2/§4 follow on a throwaway main root: the pins from
    the smoke manifest, all five pools and the SearchQA tail, ``make-manifest --s0-pins`` (a ``main_real_run`` on its
    configuration's run root, ``protocol.RUN_ROOTS`` pointed at the throwaway root), the manifest's fields equal to the
    smoke's, both chains' Settings built from it with zero calls and the owner's consent checked."""
    from dataclasses import asdict

    from skillopt.execskill import research, routes, step
    from skillopt.execskill.sandbox import client as sandbox
    from tests import execskill_fakes_research as fake_research
    from tests.fixtures.execskill.items import searchqa_items
    from tests.test_execskill_evaluation import consent_value
    from tests.test_execskill_manifest import (MEASURED, NO_CALLS, FakeDockerCLI, _items, _pinned, fake_environment,
                                               given)
    from tests.test_execskill_routes import northgate_env
    from tests.test_execskill_smoke_rehearsal import _alfworld, _write

    environment = fake_environment()
    monkeypatch.setattr(manifest, "environment", lambda **_: dict(environment))
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))  # the smoke manifest records both roots,
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(tmp_path / "history"))  # which the smoke-run processes use
    root, probe_root = test_side.root, tmp_path / "pre" / "probe"
    write_json(root / protocol.EXCLUSION_CONSENT, CONSENT)
    assert cli.main(test_side.argv) == 0  # the persisted exclusion unit that S0's supply row reads (synthetic panels)
    fixtures.make_fixtures(tmp_path / "fixtures")
    sets = {bench: str(tmp_path / "fixtures" / (bench + ".json")) for bench in ("officeqa", "livemath",
                                                                               "spreadsheetbench")}
    sets["searchqa"] = _write(tmp_path / "items" / "searchqa.json", searchqa_items(280))
    sets["alfworld"] = _write(tmp_path / "items" / "alfworld.json", _alfworld(tmp_path / "games"))
    tested = tmp_path / "s0" / smoke.SELFTEST
    write_json(tested, protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
        "measured": {**{k: MEASURED[k] for k in ("vsz_kib", "rss_kib", "view_bytes_p99")}, "start_seconds": 2.6,
                     "views": 15}, "passed": True}))
    items = [arg for name in smoke.ITEM_SETS for arg in ("--items", "%s=%s" % (name, sets[name]))]
    assert cli.main(["smoke-make", "--root", str(root), "--probe-root", str(probe_root), "--selftest", str(tested),
                     *items]) == 0
    spec = str(root / smoke.SPEC)
    checks = tmp_path / "s0-checks.json"
    write_json(checks, {"checks": {row: True for row in smoke.S0_ROWS}})
    assert cli.main(["smoke", "--spec", spec, "--stage", "S0", "--input", str(checks)]) == 0
    assert cli.main(["probe", "--spec", spec, "--fake"]) == 0  # S1 on the spec's own probe root, where S2 reads it
    capsys.readouterr()
    elucid, glm = fake_config(tmp_path, protocol.CHAINS["D"]), fake_config(tmp_path, protocol.CHAINS["G"])
    archive = fake_research.archive_fixture(tmp_path / "archive")
    path = tmp_path / "smoke-manifest.json"  # smoke-runbook step 5, after S1: chain D's block carries S1's branch
    clients = {"solver": {"D": manifest.solver_block("D", env_path=elucid["env_path"], branch="E"),
                          "G": manifest.solver_block("G", env_path=glm["repo"])}, "roles": dict(manifest.ROLES)}
    if configuration == "main":  # smoke-runbook §5: a smoke of configuration main pins chain D's route B
        clients["routes"] = {"D": {"B": routes.pin("D", "B", env_path=northgate_env(tmp_path),
                                                   solver_block=clients["solver"]["D"])}}
    smoke_m = manifest.make(path, evidence=manifest.SMOKE_EVIDENCE, environment_found=environment, measured=MEASURED,
                            configuration=configuration,
                            **{**given(tmp_path), "root": str(root), "clients": clients,
                               "data": {"research": {"archive": str(archive),
                                                     "index_sha256": research.Archive(archive).index_sha256}}})
    run = [sys.executable, "-B", str(REPO / "scripts" / "run_execskill.py"), "smoke-run", "--spec", spec,
           "--manifest", str(path), "--fake", "--stage"]
    children = {stage: subprocess.Popen(run + [stage], cwd=REPO, env=prelaunch.launch_env(), stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE) for stage in ("S2", "S3")}  # side by side
    shown = {stage: child.communicate(timeout=1500) for stage, child in children.items()}
    assert [children[s].returncode for s in ("S2", "S3")] == [0, 0], {
        s: (out.decode("utf-8", "replace")[-2000:], err.decode("utf-8", "replace")[-3000:])
        for s, (out, err) in shown.items()}
    assert [json.loads(shown[s][0]) for s in ("S2", "S3")] == [{"stage": s, "passed": True} for s in ("S2", "S3")]
    assert cli.main(["smoke-run", "--spec", spec, "--manifest", str(path), "--stage", "SE6", "--fake"]) == 0
    assert cli.main(["smoke-summary", "--spec", spec]) == 0
    capsys.readouterr()
    stages = {stage: protocol.verified(read_json(root / smoke.STAGES_DIR / (stage + ".json")), "smoke-stage")
              for stage in smoke.SMOKE_STAGES}
    assert {stage: value["evidence"] for stage, value in stages.items()} == {
        "S0": "smoke", **{stage: smoke.REHEARSAL_EVIDENCE for stage in ("S1", "S2", "S3", "SE6")}}
    assert all(value["result"]["passed"] is True for value in stages.values())
    result = protocol.verified(read_json(root / smoke.RESULT), "smoke-result")
    assert result["passed"] is True and result["evidence"] == smoke.REHEARSAL_EVIDENCE == "engineering_fixture"
    assert result["required"] == list(smoke.SMOKE_STAGES) and stages["S2"]["result"]["receipts"]["s1e_mismatch"] == [
        True]  # S2 judged the S1-e control receipt of the rehearsal's own probe
    assert stages["SE6"]["result"]["configuration"] == configuration
    out = tmp_path / "test-read-estimate.json"
    assert cli.main(["test-read-estimate", "--smoke", str(root), "--configuration", configuration, "--out",
                     str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["configuration"] == configuration
    estimate = protocol.verified(read_json(out), "test-read-estimate")
    assert estimate["evidence"] == smoke.REHEARSAL_EVIDENCE and estimate["smoke"]["spec"] == stages["S0"]["spec"]
    value = estimate["value"]
    assert estimate["test_read_estimate"] == {"D": value, "G": value} and type(value) is int and value > 0
    assert math.ceil(sum(Fraction(term) for term in estimate["terms"].values())) == value  # ticket P2C-2
    assert set(estimate["terms"]) == set(protocol.BENCHES) and estimate["pilot"] == configuration
    if configuration != "main":
        return
    # main-runbook §3.2 and §4 on a throwaway main root (never the registered one): pins, make-manifest, go checks
    main_root, mm = tmp_path / "main-root", tmp_path / "main-manifest.json"
    monkeypatch.setitem(protocol.RUN_ROOTS, "main", str(main_root))
    write_json(main_root / "shared" / "consent.json", consent_value())  # stands in for the owner's file of 18:06
    tail = tmp_path / "history" / "searchqa-tail.json"  # the tail supply the S0 exclusion unit ran on
    pins = {"root": str(main_root), "evidence": "main_real_run", "configuration": "main",
            "data": {**smoke_m["data"],
                     "pools": {b: _pinned(tmp_path / "pools" / (b + ".json"), _items(tmp_path, b, 4))
                               for b in protocol.BENCHES},
                     "searchqa_tail": {"path": str(tail), "sha256": hashlib.sha256(tail.read_bytes()).hexdigest()},
                     "test_read_estimate": {"G": value, "D": value},
                     "test_read_terms": {"G": estimate["terms"], "D": estimate["terms"]}},
            **{key: smoke_m[key] for key in ("runtime", "cards", "clients", "sheet_qualification", "contracts",
                                             "fixtures", "provenance")}}
    assert set(pins) == manifest.GIVEN | {"evidence", "configuration"}
    write_json(tmp_path / "main-pins.json", pins)
    write_json(tmp_path / "s0-pins.json", {"limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
                                           "measured": dict(MEASURED)})
    assert cli.main(["make-manifest", "--out", str(mm), "--pins", str(tmp_path / "main-pins.json"),
                     "--exclusion-root", str(root), "--s0-pins", str(tmp_path / "s0-pins.json")]) == 0
    shown = json.loads(capsys.readouterr().out)
    found = manifest.load(mm, verify=False)
    assert (shown["configuration"], shown["root"], found["evidence"]) == ("main", str(main_root), "main_real_run")
    assert found["caps"] == budgets.caps("main") and found["data"]["test_read_terms"]["G"] == estimate["terms"]
    assert {key: found[key] == smoke_m[key] for key in (  # main-runbook §4: the manifest's fields are the smoke's
        "code", "environment", "sandbox", "clients", "runtime", "cards", "contracts", "fixtures", "provenance",
        "prompt_sha", "lexicon_sha", "templates", "configuration")} == dict.fromkeys((
            "code", "environment", "sandbox", "clients", "runtime", "cards", "contracts", "fixtures", "provenance",
            "prompt_sha", "lexicon_sha", "templates", "configuration"), True)
    assert sorted(path.relative_to(main_root).as_posix() for path in main_root.rglob("*") if path.is_file()) == [
        "shared/consent.json", "shared/test-canaries.json"]  # main-runbook §2's root check on a retry
    for name in protocol.CHAINS:  # zero calls: what `run --manifest $MM --chain C` builds first
        built = manifest.setting_of(found, name, path=mm, docker=FakeDockerCLI(), transport=NO_CALLS)
        assert (protocol.configuration_of(built), protocol.order_of(built)) == ("main", protocol.BENCHES)
        assert built.extra[step.TAIL]["exclusion"] == found["data"]["exclusion"]["searchqa_test_exclusion"]
        assert set(built.pools) == set(protocol.BENCHES) and built.extra.get("route") == (
            "A" if name == "D" else None)
    assert cli.main(["consent", "--root", str(main_root)]) == 0
    assert json.loads(capsys.readouterr().out) == {"test_read": "valid"}


def test_replay_runs_each_procedure_zero_crash_and_refuses_spreadsheetbench(tmp_path, monkeypatch, capsys):
    procedures = [types.SimpleNamespace(id="fx-note"), types.SimpleNamespace(id="fx-bindings")]
    monkeypatch.setattr(cli.package, "load", lambda path: types.SimpleNamespace(sha256="p" * 64,
                                                                                procedures=procedures))
    stored = [{"bench": "searchqa", "cell": "c1"}, {"bench": "searchqa", "cell": "c2"}]
    monkeypatch.setattr(cli.trajectories, "load_run", lambda unit: list(stored))
    monkeypatch.setattr(cli.replay, "inputs_of", lambda t: {"cell": t["cell"]})
    seen = []

    def zero_crash(procedure, entries, workers):
        seen.append((procedure.id, len(entries), workers.func))
        return {"passed": procedure.id == "fx-note", "trajectories": len(entries), "applied": 1,
                "fault_count": 0}, {}

    monkeypatch.setattr(cli.replay, "zero_crash", zero_crash)
    assert cli.main(["replay", "--package", "p", "--trajectories", "u"]) == 3
    shown = json.loads(capsys.readouterr().out)
    assert shown["procedures"]["fx-note"]["passed"] and not shown["procedures"]["fx-bindings"]["passed"]
    assert [s[:2] for s in seen] == [("fx-note", 2), ("fx-bindings", 2)] and seen[0][2] is cli.sandbox.with_worker
    stored.append({"bench": "spreadsheetbench", "cell": "c3"})
    with pytest.raises(ValueError, match="SpreadsheetBench"):
        cli.main(["replay", "--package", "p", "--trajectories", "u"])


# -------------------------------------------------------------------------- row C7b-1: S0 driver and smoke stages
def test_smoke_run_prints_the_stage_verdict_or_the_stopped_report(monkeypatch, capsys):
    """``smoke-run`` hands spec, manifest and stage to ``smoke.run_stage(spec, manifest_path, stage, *, fake,
    env_path, roles_repo)`` (a stub here). Ticket C7c-1: ``run_stage`` returns the stage record, whose verdict is
    ``result.passed`` (exit 0 / 3), or -- when a unit stopped -- a report without a verdict (S4: the drill's paused
    attempts), printed with exit ``chain.EXIT_PAUSED`` (3)."""
    calls = []
    paused = "/smoke/units/S4/s1-searchqa/accept/attempt-1"

    def run_stage(spec, manifest_path, stage, *, fake=False, env_path=None, roles_repo=None):
        calls.append((spec, manifest_path, stage, fake, env_path, roles_repo))
        if stage == "S4":
            return {"stage": "S4", "complete": False, "stopped": "sandbox", "reason": "drill", "unit": "c1",
                    "paused": [paused]}
        if stage == "SN1":
            return {"stage": "SN1", "complete": False, "stopped": "connectivity", "reason": "r", "unit": "u"}
        return protocol.record("smoke-stage", "smoke", {"stage": stage, "spec": "s" * 64,
                                                        "result": {"passed": stage == "S2", "rows": {}}})

    monkeypatch.setattr(smoke, "run_stage", run_stage)
    base = ["smoke-run", "--spec", "s.json", "--manifest", "m.json", "--stage"]
    assert cli.main(base + ["S2", "--fake"]) == 0
    assert json.loads(capsys.readouterr().out) == {"stage": "S2", "passed": True}
    for named in (["--roles-repo", "/repo"], ["--env-path", "/env"]):  # ticket C7d-3: a rehearsal names no credential
        with pytest.raises(ValueError, match="names no credential"):
            cli.main(base + ["S2", "--fake", *named])
    assert cli.main(base + ["SE6"]) == 3
    assert json.loads(capsys.readouterr().out) == {"stage": "SE6", "passed": False}
    assert cli.main(base + ["S4"]) == chain.EXIT_PAUSED == 3
    assert json.loads(capsys.readouterr().out) == {"stage": "S4", "stopped": "sandbox", "reason": "drill",
                                                   "unit": "c1", "paused": [paused]}
    assert cli.main(base + ["SN1"]) == 3
    assert json.loads(capsys.readouterr().out) == {"stage": "SN1", "stopped": "connectivity", "reason": "r",
                                                   "unit": "u"}
    assert calls[0] == ("s.json", "m.json", "S2", True, None, None) and len(calls) == 4  # the refused two never ran
    assert calls[2] == ("s.json", "m.json", "S4", False, protocol.ELUCID_ENV, None)


def test_smoke_recovery_is_wired_to_the_s4_drills_operator_step(tmp_path, inputs, capsys):
    """Ticket C7c-1 item 2: ``smoke-recovery`` is ``smoke.recovery_cli`` -- the owner-format recovery.json, once, only
    in a paused attempt of the S4 mini-step unit."""
    root = tmp_path / "pre" / "smoke"
    assert cli.main(["smoke-make", "--root", str(root), *inputs]) == 0
    capsys.readouterr()
    units = root / smoke.UNITS_DIR
    attempt = units / smoke.S4_DIR / "s1-searchqa" / "accept" / "attempt-1"
    other = units / "S2" / "searchqa" / "attempt-1"
    for folder in (attempt, other):
        folder.mkdir(parents=True)
        write_json(folder / "status.json", protocol.record("unit-status", "smoke", {
            "status": "paused", "kind": "sandbox", "reason": "drill", "cell": "c1"}))
    assert cli.HANDLERS["smoke-recovery"] is smoke.recovery_cli
    assert "smoke-recovery --spec S --attempt A --decision TEXT" in cli.__doc__
    argv = ["smoke-recovery", "--spec", str(root / smoke.SPEC), "--decision", "redo the accept round", "--attempt"]
    with pytest.raises(ValueError, match="paused attempt of an S4 unit"):
        cli.main(argv + [str(other)])
    assert cli.main(argv + [str(attempt)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["recovery"] == str(attempt / "recovery.json") and printed["by"] == "owner"
    assert read_json(attempt / "recovery.json")["decision"] == smoke.SMOKE_LABEL + ": redo the accept round"
    with pytest.raises(ValueError):  # written once: another decision does not replace it
        cli.main(argv[:-3] + ["--decision", "something else", "--attempt", str(attempt)])
    assert not (other / "recovery.json").exists()


def test_s0_collect_passes_the_exclusion_check_and_prints_the_checks(tmp_path, monkeypatch, capsys):
    seen = {}

    def collect(root, **options):
        seen.update(options, root=root)
        return {"checks": {row: row != "supply" for row in smoke.S0_ROWS}, "passed": False}

    monkeypatch.setattr(s0, "collect", collect)
    argv = ["s0-collect", "--root", str(tmp_path / "smoke"), "--fixtures", "fx", "--selftest", "t.json",
            "--pins-out", "pins.json", "--manifest", "v3.json", "--fake"]
    argv += [x for name in smoke.ITEM_SETS for x in ("--items", "%s=%s.json" % (name, name))]
    assert cli.main(argv) == 3
    shown = json.loads(capsys.readouterr().out)
    assert shown["checks"]["supply"] is False and shown["passed"] is False
    assert seen["exclusion_check"] is cli.exclusion_records and seen["fake"] is True
    assert seen["items"] == {name: name + ".json" for name in smoke.ITEM_SETS}
    assert seen["traces"] == s0.D3_TRACES and seen["snapshot"] == protocol.SNAPSHOT_ROOT
    assert seen["engine_qualification"] is None  # fake mode keeps its injected fakes


def test_s0_collect_needs_this_snapshots_engine_qualification_unless_fake(tmp_path, monkeypatch, capsys):
    """Ticket C7b1-3: the real S0 sheet row runs on the new engine qualification; without it nothing is collected."""
    seen = {}

    def collect(root, **options):
        seen.update(options)
        return {"checks": {row: True for row in smoke.S0_ROWS}, "passed": True}

    monkeypatch.setattr(s0, "collect", collect)
    argv = ["s0-collect", "--root", str(tmp_path / "smoke"), "--fixtures", "fx", "--selftest", "t.json",
            "--pins-out", "pins.json", "--manifest", "v3.json", "--sheet-source", "q.json", "--sheet-sha256", "0" * 64]
    argv += [x for name in smoke.ITEM_SETS for x in ("--items", "%s=%s.json" % (name, name))]
    with pytest.raises(ValueError, match="--engine-qualification"):
        cli.main(argv)
    assert not seen
    argv += ["--engine-qualification", "/data/q23/qualification.json"]
    # Codex review 2026-10-22 #13: the real equivalence row runs on the imported cards and the pinned runtimes
    with pytest.raises(ValueError, match="--texts"):
        cli.main(argv)
    assert not seen
    cards = {bench: "Imported card of %s: the registered v3 instruction." % bench for bench in protocol.BENCHES}
    monkeypatch.setattr(cli, "CARD_IDENTITY", {b: (len(t), hashlib.sha256(t.encode()).hexdigest()[:8])
                                               for b, t in cards.items()})
    write_json(tmp_path / "texts.json", protocol.record("texts-import", "smoke", {"cards": cards}))
    v3_runtime = {"searchqa": {"prompt_layout": "contract-first-v2"}, "spreadsheetbench": {"image": "old"},
                  "alfworld": {"seed": 42}}
    _v3_manifest(tmp_path / "v3.json", runtime=v3_runtime)
    write_json(tmp_path / "sheet-runtime.json", {"image": "new", "recalculation": {}})
    argv = [str(tmp_path / "v3.json") if arg == "v3.json" else arg for arg in argv]
    assert cli.main(argv + ["--texts", str(tmp_path / "texts.json"),
                            "--sheet-runtime", str(tmp_path / "sheet-runtime.json")]) == 0
    assert seen["engine_qualification"] == "/data/q23/qualification.json" and seen["fake"] is False
    assert seen["sheet_source"] == "q.json" and seen["manifest_path"] == str(tmp_path / "v3.json")
    assert seen["cards"] == cards and seen["runtimes"] == {**v3_runtime, "spreadsheetbench": {
        "image": "new", "recalculation": {}}}
    wrong = {**cards, "officeqa": cards["officeqa"] + " (edited)"}  # not the registered card
    write_json(tmp_path / "texts-edited.json", protocol.record("texts-import", "smoke", {"cards": wrong}))
    with pytest.raises(ValueError, match="officeqa card"):
        cli.main(argv + ["--texts", str(tmp_path / "texts-edited.json"),
                         "--sheet-runtime", str(tmp_path / "sheet-runtime.json")])


def _v3_manifest(path, **fields):
    """A sealed record standing in for the v3 run manifest (its sealed fields only)."""
    value = seal({"version": "fivebench-coevolution-v3-manifest", **fields})
    write_json(path, value)
    return value


def test_sheet_runtime_writes_the_revalidated_runtime_once(tmp_path, monkeypatch, capsys):
    """Ticket C7b1-3: the pins' ``runtime.spreadsheetbench`` is v3's block on this snapshot's engine qualification,
    written once after the offline revalidation (``qualify.revalidate``, replaced here)."""
    from tests.test_execskill_qualify import engine_record, identity, v3_sheet_runtime

    _v3_manifest(tmp_path / "v3.json", runtime={"spreadsheetbench": v3_sheet_runtime(), "alfworld": {"seed": 42}})
    engine = tmp_path / "q23" / "qualification.json"
    record = engine_record(engine, identity("/data/execskill-20261021-source"))
    checked = []
    monkeypatch.setattr(qualify, "revalidate", checked.append)
    out = tmp_path / "sheet-runtime.json"
    argv = ["sheet-runtime", "--manifest", str(tmp_path / "v3.json"), "--engine-qualification", str(engine), "--out"]
    assert cli.main(argv + [str(out)]) == 0
    printed, written = json.loads(capsys.readouterr().out), read_json(out)
    assert checked == [written] and printed["recalculation"] == written["recalculation"]
    assert printed["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    expected = v3_sheet_runtime()
    expected["recalculation"].update(qualification_path=str(engine), qualification_hash=record["record_hash"],
                                     qualification_sha256=hashlib.sha256(engine.read_bytes()).hexdigest())
    assert written == expected
    with pytest.raises(ValueError, match="new file"):
        cli.main(argv + [str(out)])

    def stale(runtime):
        raise ValueError("The SpreadsheetBench engine qualification does not revalidate from this checkout")

    monkeypatch.setattr(qualify, "revalidate", stale)
    with pytest.raises(ValueError, match="does not revalidate"):
        cli.main(argv + [str(tmp_path / "stale.json")])
    assert not (tmp_path / "stale.json").exists()
    changed = read_json(tmp_path / "v3.json")
    changed["runtime"]["alfworld"]["seed"] = 7  # an edited v3 manifest no longer verifies
    write_json(tmp_path / "v3-changed.json", changed)
    with pytest.raises(ValueError):
        cli.main(["sheet-runtime", "--manifest", str(tmp_path / "v3-changed.json"), "--engine-qualification",
                  str(engine), "--out", str(tmp_path / "other.json")])


def test_make_manifest_refuses_a_v7_sheet_runtime_that_does_not_revalidate(test_side, tmp_path, monkeypatch):
    """Ticket C7b1-3: a pins ``runtime.spreadsheetbench`` of the frozen v7 scorer is revalidated offline before
    anything is written (no canaries, no manifest); other scorers are not checked."""
    write_json(test_side.root / protocol.EXCLUSION_CONSENT, CONSENT)
    cli.main(test_side.argv)
    made = {}

    def make(out, **given):
        made.update(given)
        return {protocol.RECORD_HASH: "f" * 64, "root": given["root"]}

    monkeypatch.setattr(manifest, "make", make)
    run_root = tmp_path / "pilot"
    sheet = {"spreadsheet_scorer": qualify.SCORER, "recalculation": {"qualification_path": "/q/qualification.json"}}
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps({"root": str(run_root), "data": {}, "limits": {}, "evidence": "pilot", "measured": {},
                                "runtime": {"spreadsheetbench": sheet, "alfworld": {"seed": 42}},
                                "configuration": "default"}))
    argv = ["make-manifest", "--out", str(tmp_path / "m.json"), "--pins", str(pins), "--exclusion-root",
            str(test_side.root)]

    def stale(runtime):
        raise ValueError("The SpreadsheetBench engine qualification does not revalidate from this checkout (ticket "
                         "C7b1-3): ValueError: Engine/source/image changed")

    monkeypatch.setattr(qualify, "revalidate", stale)
    with pytest.raises(ValueError, match="does not revalidate"):
        cli.main(argv)
    assert not made and not (run_root / protocol.CANARIES).exists()
    checked = []
    monkeypatch.setattr(qualify, "revalidate", checked.append)
    assert cli.main(argv) == 0
    assert checked == [sheet] and made["runtime"]["spreadsheetbench"] == sheet
    native = dict(json.loads(pins.read_text()), runtime={"spreadsheetbench": {"spreadsheet_scorer": "native"}})
    pins.write_text(json.dumps(native))
    monkeypatch.setattr(qualify, "revalidate", stale)  # not reached: another scorer is not the v7 engine's
    assert cli.main(argv[:2] + [str(tmp_path / "m2.json")] + argv[3:]) == 0


def test_export_pools_writes_the_five_pools_once_and_prints_the_data_pools_pins(tmp_path, monkeypatch, capsys):
    """Tickets C7b1-2 / C6-3: the frozen pools of the v3 data pins (synthetic here), SpreadsheetBench by the v3
    training qualification the v3 manifest pins; counts, sha256 and the pins block printed, never item content.
    Registrar 17:0x (ALFWorld step, I1-1): ALFWorld's pool is the fresh supply with its views
    (``supply.alfworld_pool``, replaced here), against v3's ``runtime.alfworld``; v3's ALFWorld pool is not opened."""
    from tests.test_execskill_supply import _frozen_pool

    sizes = {"searchqa": 9, "officeqa": 6, "livemath": 6, "spreadsheetbench": 6, "alfworld": 6}
    opened = []

    def pool(pinned, bench):
        opened.append(bench)
        return _frozen_pool(bench, sizes[bench])

    monkeypatch.setattr(data, "pool", pool)
    monkeypatch.setattr(supply, "REGISTERED_POOLS", sizes)
    monkeypatch.setattr(supply, "SHEET_QUALIFIED", 4)
    frozen = _frozen_pool("spreadsheetbench", 6)
    sheet = seal({"version": qualify.IMPORTABLE[0], "side": "train", "tasks": 6,
                  "qualified": [i["task_id"] for i in frozen[:4]],
                  "excluded": {i["task_id"]: "other" for i in frozen[4:]},
                  "counts": {name: 0 for name in qualify.CATEGORIES}, "scorings_per_item": qualify.PASSES,
                  "model_calls": 0, "scorer": qualify.SCORER, "recalculation": {},
                  "task_hashes": {i["task_id"]: digest(i) for i in frozen}})
    write_json(tmp_path / "sheet.json", sheet)
    alfworld_runtime = {"alfworld_data": "/alf", "seed": 42}
    v3 = _v3_manifest(tmp_path / "v3.json", data={"paths": {}, "sha256": {}}, sheet_qualification={
        "path": str(tmp_path / "sheet.json"), "record_hash": sheet["record_hash"]},
        runtime={"alfworld": alfworld_runtime})
    fresh = protocol.record(supply.RECORD_KIND, "smoke", {"name": "alfworld-xs", "n": 1})
    views = protocol.record(supply.VIEWS_KIND, "smoke", {"n": 2})
    write_json(tmp_path / "alfworld-xs.json", fresh)
    write_json(tmp_path / "alfworld-xs-views.json", views)
    seen = []

    def alfworld_pool(supply_value, views_value, *, runtime):
        seen.append((supply_value, views_value, runtime))
        items = [dict(item, part="fresh", room="room-%d" % (n // 2)) for n, item in
                 enumerate(_frozen_pool("alfworld", 5))]
        return items, {"pool": 5, "parts": {"fresh": 5}, "items": 5, "rooms": 3}

    monkeypatch.setattr(supply, "alfworld_pool", alfworld_pool)
    out = tmp_path / "pools"
    argv = ["export-pools", "--manifest", str(tmp_path / "v3.json"), "--out", str(out), "--alfworld-supply",
            str(tmp_path / "alfworld-xs.json"), "--alfworld-views", str(tmp_path / "alfworld-xs-views.json")]
    assert cli.main(argv) == 0
    shown = capsys.readouterr().out
    printed = json.loads(shown)
    record = protocol.verified(read_json(out / supply.POOL_RECORD), supply.POOL_KIND)
    assert sorted(opened) == sorted(set(protocol.BENCHES) - {"alfworld"}) and set(printed["pools"]) == set(
        protocol.BENCHES)
    assert seen == [(fresh, views, alfworld_runtime)] and printed["pools"]["alfworld"]["counts"]["parts"] == {
        "fresh": 5}
    assert record["source"]["alfworld"] == {
        "supply": str(tmp_path / "alfworld-xs.json"), "supply_sha256": fresh[protocol.RECORD_HASH],
        "views": str(tmp_path / "alfworld-xs-views.json"), "views_sha256": views[protocol.RECORD_HASH]}
    assert printed["pins"] == {"pools": supply.pool_pins(record)}
    assert printed["record_sha256"] == record[protocol.RECORD_HASH]
    assert printed["pools"]["spreadsheetbench"]["counts"]["items"] == 4
    assert printed["pools"]["spreadsheetbench"]["counts"]["pool"] == 6
    assert record["source"]["manifest_record_hash"] == v3["record_hash"]
    assert record["source"]["sheet_qualification"]["summary"]["qualified"] == 4
    assert "Synthetic" not in shown  # counts and hashes only
    assert supply.load_pool(out / "searchqa.json", "searchqa") == supply.order("searchqa", _frozen_pool("searchqa", 9))
    with pytest.raises(ValueError, match="once"):
        cli.main(argv)
    _v3_manifest(tmp_path / "v3-other.json", data={"paths": {}, "sha256": {}}, sheet_qualification={
        "path": str(tmp_path / "sheet.json"), "record_hash": "0" * 64}, runtime={"alfworld": alfworld_runtime})
    with pytest.raises(ValueError, match="pinned"):  # the v3 manifest's pin of the training qualification
        cli.main(["export-pools", "--manifest", str(tmp_path / "v3-other.json"), "--out", str(tmp_path / "p2"),
                  *argv[-4:]])
    assert not (tmp_path / "p2").exists()


def test_smoke_make_needs_no_noise_anchor_or_control_cells_in_the_trimmed_smoke(tmp_path, inputs, capsys):
    """Registrar addenda 13:0x / 13:4x: the smoke passes on S0, S1, S2, S3 and S-E6; ``--noise-anchor`` is not required
    (the spec records null with the reason) and ``--control-cells`` defaults to []."""
    bare = [arg for n, arg in enumerate(inputs) if arg not in ("--control-cells", "--noise-anchor")
            and inputs[n - 1] not in ("--control-cells", "--noise-anchor")]
    root = tmp_path / "pre" / "smoke"
    assert cli.main(["smoke-make", "--root", str(root), *bare]) == 0
    shown = json.loads(capsys.readouterr().out)
    spec = read_json(root / smoke.SPEC)
    assert shown["stages"] == spec["stages"] == list(smoke.SMOKE_STAGES) == ["S0", "S1", "S2", "S3", "SE6"]
    assert spec["control_cells"] == [] and spec["noise_anchor"] is None and "13:0x" in spec["noise_anchor_reason"]
    assert (shown["control_cells"], shown["noise_anchor"]) == (0, False)
    assert cli.main(["smoke-make", "--root", str(tmp_path / "again"), "--dry-run", *inputs]) == 0
    shown = json.loads(capsys.readouterr().out)  # given anyway: recorded (a later S-N1 never gates)
    assert (shown["control_cells"], shown["noise_anchor"]) == (1, True)


def _scan_attempt(root, *, hits):
    """A run-root canary scan attempt as ``evaluation._root_scanned`` leaves it: the sealed scan and, on a hit, the
    paused ``canary_hit`` status naming it."""
    attempt = root / "G" / evaluation.ROOT_SCAN / "attempt-1"
    attempt.mkdir(parents=True)
    scan = protocol.record("root-canary-scan", "smoke", {"chain": "G", "files_scanned": 9, "hits": hits,
                                                         "files_hit": min(hits, 1), "canaries": 25,
                                                         "canaries_sha256": "0" * 64, "by_where": {},
                                                         "by_bench": {}, "shown": []})
    write_json(attempt / "scan.json", scan)
    if hits:
        write_json(attempt / "status.json", protocol.record("unit-status", "smoke", {
            "status": "paused", "kind": "canary_hit", "reason": "%d hits" % hits, "cell": None,
            "scan_sha256": scan[protocol.RECORD_HASH]}))
    return attempt, scan[protocol.RECORD_HASH]


def test_recover_releases_only_a_paused_run_root_scan_naming_its_own_scan(tmp_path, capsys):
    """Registrar decision PR-C31-3 (1b), 14:1x: ``recover --decision "release <scan record_sha256>"`` -- only in a
    run-root canary scan attempt whose hits paused the unseal, naming that attempt's own sealed scan; the frozen
    owner format {by, date, decision} (``coevo5.evaluation.recovered``). Any other decision stays free text. The rule
    is ``evaluation.release_check``, the one the unseal applies again (ticket P2-A3-1)."""
    from skillopt.coevo5.evaluation import recovered

    attempt, sha = _scan_attempt(tmp_path / "root", hits=2)
    for decision, message in (("release " + "f" * 64, "names another scan"), ("release " + sha[:12], "exactly"),
                              ("release", "exactly"), (" release " + sha, "exactly")):
        with pytest.raises(ValueError, match=message):
            cli.main(["recover", "--attempt", str(attempt), "--decision", decision])
    unit = tmp_path / "root" / "G" / "xs-officeqa-2" / "accept" / "attempt-1"
    unit.mkdir(parents=True)
    with pytest.raises(ValueError, match="paused run-root canary scan only"):
        cli.main(["recover", "--attempt", str(unit), "--decision", "release " + sha])
    clean, clean_sha = _scan_attempt(tmp_path / "clean", hits=0)
    with pytest.raises(ValueError, match="names the scan paused"):  # a clean scan has no paused status
        cli.main(["recover", "--attempt", str(clean), "--decision", "release " + clean_sha])
    assert not any((p / "recovery.json").exists() for p in (attempt, unit, clean))
    assert cli.main(["recover", "--attempt", str(attempt), "--decision", "release " + sha]) in (0, None)
    value = read_json(attempt / "recovery.json")
    assert set(value) == {"by", "date", "decision"} and value["decision"] == "release " + sha and recovered(attempt)
    other, _ = _scan_attempt(tmp_path / "other", hits=1)  # a new scan after the files were dealt with: free text
    cli.main(["recover", "--attempt", str(other), "--decision", "scan again: the stray file was removed"])
    assert recovered(other)


def test_monitor_lists_root_scans_apart_from_open_attempts(tmp_path, capsys):
    """Ticket PR-C31-1 item 4: a scan attempt never gets a unit.json, so it is listed with its hits, not as open;
    with the record hash a release must name, and whether it paused and was decided (ticket P2-A3-1)."""
    root = tmp_path / "root"
    _, sha = _scan_attempt(root, hits=3)
    (root / "G" / "xs-officeqa-2" / "run" / "attempt-1").mkdir(parents=True)
    assert cli.main(["monitor", "--root", str(root)]) in (0, None)
    shown = json.loads(capsys.readouterr().out)
    assert shown["root_scans"] == {"G/root-scan/attempt-1": {"hits": 3, "paused": True, "decided": False,
                                                             "record_sha256": sha}}
    assert shown["open"] == ["G/xs-officeqa-2/run/attempt-1"]


def test_every_subcommand_has_a_handler_and_answers_help(capsys):
    parser = cli.parser()
    names = set(next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices)
    assert names == set(cli.HANDLERS) and {"export-pools", "sheet-runtime", "smoke-recovery"} <= names
    for name in sorted(names):
        with pytest.raises(SystemExit) as done:
            parser.parse_args([name, "--help"])
        assert done.value.code == 0 and "usage:" in capsys.readouterr().out


def test_make_fixtures_is_wired(tmp_path, capsys):
    assert cli.main(["make-fixtures", "--out", str(tmp_path / "fx")]) == 0
    assert (tmp_path / "fx" / fixtures.RECORD_FILE).is_file()
    assert fixtures.verify(tmp_path / "fx")["evidence"] == "engineering_fixture"


def test_make_manifest_takes_limits_and_measurements_from_the_s0_pins(test_side, tmp_path, monkeypatch):
    write_json(test_side.root / protocol.EXCLUSION_CONSENT, CONSENT)
    cli.main(test_side.argv)
    made = {}

    def make(out, **given):
        made.update(given)
        return {protocol.RECORD_HASH: "f" * 64, "root": given["root"]}

    monkeypatch.setattr(manifest, "make", make)
    limits = {kind: {"pids": 64, "memory_mb": 768, "cpus": 0.5, "address_space_mb": 2304, "frame_bytes": 1 << 20}
              for kind in ("cell", "episode", "detector", "generator")}
    measured = {"vsz_kib": 1, "rss_kib": 2, "view_bytes_p99": 3, "native_peak_rss_kib": 4}
    s0_pins, pins = tmp_path / "s0-pins.json", tmp_path / "pins.json"
    s0_pins.write_text(json.dumps({"limits": limits, "measured": measured}))
    pins.write_text(json.dumps({"root": str(tmp_path / "smoke-run"), "data": {}, "evidence": "smoke",
                                "configuration": "main"}))
    argv = ["make-manifest", "--out", str(tmp_path / "m.json"), "--pins", str(pins), "--exclusion-root",
            str(test_side.root), "--s0-pins", str(s0_pins)]
    assert cli.main(argv) == 0
    assert made["measured"] == measured and made["limits"]["cell"].address_space_mb == 2304
    both = tmp_path / "both.json"  # the operator's pins may not carry limits next to the S0 pins
    both.write_text(json.dumps({"root": str(tmp_path / "smoke-run"), "data": {}, "evidence": "smoke",
                                "configuration": "main", "limits": limits}))
    with pytest.raises(ValueError, match="S0 pins"):
        cli.main(argv[:4] + [str(both)] + argv[5:])
    # registrar addendum 15:5x R6 (d): without --s0-pins, a message instead of a bare KeyError, before any write
    lone = tmp_path / "lone.json"
    lone.write_text(json.dumps({"root": str(tmp_path / "lone-run"), "data": {}, "evidence": "smoke",
                                "configuration": "main"}))
    with pytest.raises(ValueError, match="give --s0-pins"):
        cli.main(argv[:4] + [str(lone)] + argv[5:7])
    assert not (tmp_path / "lone-run").exists()
    lone.write_text(json.dumps({"root": str(tmp_path / "lone-run"), "data": {}}))  # no evidence label
    with pytest.raises(ValueError, match="root, data, evidence and configuration"):
        cli.main(argv[:4] + [str(lone)] + argv[5:])
    assert not (tmp_path / "lone-run").exists()


# ------------------------------------------------ registrar addendum 2026-10-22 14:10 (P2C): rows 8 and 17
def _smoke_with_se6(root, *, per_cell, ratio, passed=True, s3=None, configuration=None):
    """A smoke root as ``smoke.summary`` seals it: its specification (S-E6 its listed stage, and S3 when ``s3`` is
    given: S3's verdict) and S-E6's stage record with ``smoke.se6``'s result fields (per-cell tokens, the
    ledger/actual ratio; ``configuration``: the run configuration it projected, registrar 17:0x)."""
    spec = protocol.record("smoke-spec", "smoke", {"root": str(root), "stages": ["SE6"] + ["S3"] * (s3 is not None)})
    write_json(root / smoke.SPEC, spec)
    if s3 is not None:
        smoke.record(spec, "S3", {"passed": s3, "rows": {"cells": s3}})
    smoke.record(spec, "SE6", {"passed": passed, "rows": {"ratio": passed}, "per_cell": per_cell, "ratio": ratio,
                               **({} if configuration is None else {"configuration": configuration})})
    assert smoke.summary(spec)["passed"] is (passed and s3 is not False)
    return spec


def test_m1_the_test_read_estimate_of_mains_smoke_prices_mains_test_read_with_every_bench_home(tmp_path, capsys):
    """Registrar 17:0x: S-E6 of the main experiment's smoke projected ``main``; its estimate prices main's test-read
    cells with f = 1 on all five benches (``--configuration main``), and a smoke of another configuration is refused."""
    per_cell = {b: {"card": float(protocol.CELL_ANCHORS[b][1]), "procedure": 1.6 * protocol.CELL_ANCHORS[b][1],
                    "procedure_assumed": True} for b in protocol.BENCHES}
    _smoke_with_se6(tmp_path / "smoke", per_cell=per_cell, ratio=1.0, configuration="main")
    out = tmp_path / "ops" / "estimate.json"
    argv = ["test-read-estimate", "--smoke", str(tmp_path / "smoke"), "--out", str(out)]
    with pytest.raises(ValueError, match="projected the run configuration"):
        cli.main(argv + ["--configuration", "default"])
    assert not out.exists()
    assert cli.main(argv + ["--configuration", "main"]) == 0
    found = protocol.verified(read_json(out), "test-read-estimate")
    assert json.loads(capsys.readouterr().out)["configuration"] == "main" == found["pilot"]
    assert found["value"] == 77_268_847 == protocol.estimate_test_read(per_cell, 1.0, "main")  # 93,975,624 x 7.4/9
    assert found["inputs"]["fired"] == {b: "1" for b in protocol.BENCHES}
    assert found["inputs"]["n"] == {b: protocol.TEST_READ_CELLS["main"][b][0] for b in protocol.BENCHES}
    assert math.ceil(sum(Fraction(t) for t in found["terms"].values())) == found["value"]
    _smoke_with_se6(tmp_path / "pilot-smoke", per_cell=per_cell, ratio=1.0)  # no configuration: the default's
    with pytest.raises(ValueError, match="projected the run configuration"):
        cli.main(["test-read-estimate", "--smoke", str(tmp_path / "pilot-smoke"), "--out", str(tmp_path / "e2.json"),
                  "--configuration", "main"])
    assert not (tmp_path / "e2.json").exists()


def test_m1_make_manifest_takes_the_configuration_and_puts_a_real_run_on_its_root(test_side, tmp_path, monkeypatch):
    """Registrar 17:0x: the pins name the run configuration; a real run's manifest carries its configuration's label
    (``main_real_run`` for main) and goes to its configuration's run root (``protocol.RUN_ROOTS``, a tmp root here:
    a test never writes under the registered main root); anything else is refused before a file is written."""
    write_json(test_side.root / protocol.EXCLUSION_CONSENT, CONSENT)
    cli.main(test_side.argv)
    made = {}

    def make(out, **given):
        made.update(given)
        return {protocol.RECORD_HASH: "f" * 64, "root": given["root"], "configuration": given["configuration"]}

    monkeypatch.setattr(manifest, "make", make)
    main_root = tmp_path / "main-root"
    monkeypatch.setitem(protocol.RUN_ROOTS, "main", str(main_root))
    pins, base = tmp_path / "pins.json", {"data": {}, "limits": {}, "measured": {}}
    argv = ["make-manifest", "--out", str(tmp_path / "m.json"), "--pins", str(pins), "--exclusion-root",
            str(test_side.root)]
    for refused in ({"root": str(tmp_path / "elsewhere"), "evidence": "main_real_run", "configuration": "main"},
                    {"root": str(main_root), "evidence": "pilot_real_run", "configuration": "main"},
                    {"root": str(main_root), "evidence": "main_real_run", "configuration": "default"},
                    {"root": str(main_root), "evidence": "main_real_run", "configuration": "pilot"},
                    {"root": str(main_root), "evidence": "main_real_run"}):
        pins.write_text(json.dumps({**base, **refused}))
        with pytest.raises(ValueError, match="configuration"):
            cli.main(argv)
    assert not made and not main_root.exists() and not (tmp_path / "elsewhere").exists()
    pins.write_text(json.dumps({**base, "root": str(main_root), "evidence": "main_real_run", "configuration": "main"}))
    assert cli.main(argv) == 0
    assert (made["configuration"], made["evidence"], made["root"]) == ("main", "main_real_run", str(main_root))
    assert (main_root / protocol.CANARIES).exists()


def test_test_read_estimate_writes_the_sealed_estimate_of_a_passed_smoke_once(tmp_path, capsys):
    """Row 8 (pilot-runbook §3.3, §3.4): zero calls; the S-E6-corrected estimate with its inputs, sealed, written once
    (an existing file is refused, never overwritten); a smoke that did not pass, or whose S-E6 did not, gives none."""
    per_cell = {b: {"card": float(protocol.CELL_ANCHORS[b][1]), "procedure": 1.6 * protocol.CELL_ANCHORS[b][1],
                    "procedure_assumed": True} for b in protocol.BENCHES}  # the high anchors, no procedure measured
    spec = _smoke_with_se6(tmp_path / "smoke", per_cell=per_cell, ratio=1.0)
    out = tmp_path / "ops" / "test-read-estimate.json"
    argv = ["test-read-estimate", "--smoke", str(tmp_path / "smoke"), "--out", str(out)]
    assert cli.main(argv) == 0
    found = protocol.verified(read_json(out), "test-read-estimate")
    assert json.loads(capsys.readouterr().out) == {"out": str(out), "test_read_estimate": {"D": 54_409_087,
                                                                                           "G": 54_409_087},
                                                   "configuration": "default",
                                                   "record_sha256": found[protocol.RECORD_HASH]}
    assert found["value"] == 54_409_087 and found["pilot"] == "default" and found["evidence"] == "smoke"
    assert found["smoke"]["spec"] == spec[protocol.RECORD_HASH] and found["smoke"]["root"] == str(tmp_path / "smoke")
    assert found["inputs"]["ratio"] == 1.0 and found["inputs"]["per_cell"] == per_cell and found["inputs"]["arms"] == 4
    assert found["inputs"]["fired"] == {"searchqa": "7/10", "officeqa": "1", "livemath": "7/10",
                                        "spreadsheetbench": "1", "alfworld": "1/2"}
    assert found["inputs"]["n"] == {b: protocol.TEST_READ_CELLS["default"][b][0] for b in protocol.BENCHES}
    terms = {b: Fraction(text) for b, text in found["terms"].items()}  # ticket P2C-2: data.test_read_terms
    assert terms == protocol.read_estimate_terms(per_cell, 1.0) and math.ceil(sum(terms.values())) == found["value"]
    before = out.read_bytes()
    with pytest.raises(ValueError, match="written once"):
        cli.main(argv)
    assert out.read_bytes() == before
    _smoke_with_se6(tmp_path / "failed", per_cell=per_cell, ratio=1.0, passed=False)
    _smoke_with_se6(tmp_path / "s3-failed", per_cell=per_cell, ratio=1.0, s3=False)  # S-E6 passed, the smoke not
    for name in ("failed", "s3-failed"):
        with pytest.raises(ValueError, match="passed smoke"):
            cli.main(["test-read-estimate", "--smoke", str(tmp_path / name), "--out", str(tmp_path / "f.json")])
    missing = {b: per_cell[b] for b in protocol.BENCHES if b != "alfworld"}
    _smoke_with_se6(tmp_path / "partial", per_cell=missing, ratio=1.0)
    with pytest.raises(ValueError, match="every bench"):
        cli.main(["test-read-estimate", "--smoke", str(tmp_path / "partial"), "--out", str(tmp_path / "p.json")])
    assert not (tmp_path / "f.json").exists() and not (tmp_path / "p.json").exists()


def test_recover_refuses_a_finished_acceptance_round(tmp_path):
    """Row 17 (registrar decision C7e-2, choice 1): an acceptance attempt whose cells are all done and that paused as
    ``acceptance_undetermined`` (or on an error raised by ``acceptance.decide``) is final: ``recover`` writes no
    recovery.json and says to report it to the owner. A round paused inside a block is recovered as before."""
    from skillopt.execskill import acceptance
    from skillopt.execskill.registry import Registry
    from tests.test_execskill_acceptance import paused, stored_round

    done, stopped = tmp_path / "done" / "accept", tmp_path / "stopped" / "accept"
    stored_round(done, Registry(tmp_path / "done" / "history", evidence="smoke"))
    paused(done / "attempt-1", "acceptance_undetermined", "J5")
    assert acceptance.finished_round(done / "attempt-1") == "acceptance_undetermined"
    with pytest.raises(ValueError, match=r"A finished acceptance round is final \(acceptance_undetermined.*owner"):
        cli.main(["recover", "--attempt", str(done / "attempt-1"), "--decision", "redo the round"])
    assert not (done / "attempt-1" / "recovery.json").exists()
    stored_round(stopped, Registry(tmp_path / "stopped" / "history", evidence="smoke"), stop_at=("b2", 3))
    paused(stopped / "attempt-1", "sandbox")
    assert cli.main(["recover", "--attempt", str(stopped / "attempt-1"), "--decision", "redo block b2"]) == 0
    assert read_json(stopped / "attempt-1" / "recovery.json")["decision"] == "redo block b2"
