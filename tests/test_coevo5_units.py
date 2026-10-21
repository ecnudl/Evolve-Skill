"""coevo5 learning units and the launch manifest (registration §0, §13.4): a unit runs once and its record is bound to
the run and its identity; a pause, an error or an interruption stops it until the owner's decision is recorded (the
command line's ``recover``); a manifest builds the chain's setting and refuses a changed pinned file."""
import hashlib
import json

import pytest

from scripts import run_coevo5 as cli
from skillopt.coevo5 import manifest, texts
from skillopt.coevo5.cells import Pause
from skillopt.coevo5.examiner import GENERAL
from skillopt.coevo5.outcomes import AssumptionBroken, BudgetStop, ConfigurationError, LedgerFailure
from skillopt.coevo5.protocol import ORDER, OVERALL_CEILING, RUNTIME, SLOTS, VERSION
from skillopt.coevo5.units import complete, run_unit
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json

RUN = "run-1"
IDENTITY = {"unit": "E-glm/s1/train", "parent": "p1", "previous": None}


# ----------------------------------------------------------------------------------------------------- units
def test_a_unit_runs_once_and_its_record_is_bound_to_the_run_and_identity(tmp_path):
    ran = []

    def work(attempt):
        ran.append(attempt.name)
        return {"value": 1}
    record = run_unit(tmp_path / "u", run=RUN, identity=IDENTITY, work=work)
    assert (record["status"], record["attempt"], record["result"]) == ("complete", "attempt-1", {"value": 1})
    assert run_unit(tmp_path / "u", run=RUN, identity=IDENTITY, work=work) == record and ran == ["attempt-1"]
    assert read_json(tmp_path / "u" / "unit.json", sealed=True) == record
    with pytest.raises(ValueError):
        run_unit(tmp_path / "u", run="run-2", identity=IDENTITY, work=work)
    with pytest.raises(ValueError):
        complete(tmp_path / "u", run=RUN, identity={**IDENTITY, "parent": "p2"})


def test_a_pause_waits_for_the_owner_whose_decision_allows_one_more_attempt(tmp_path):
    root = tmp_path / "u"

    def pause(attempt):
        raise Pause("budget", "budget_stop", "cell-1")
    with pytest.raises(Pause):
        run_unit(root, run=RUN, identity=IDENTITY, work=pause)
    status = read_json(root / "attempt-1" / "status.json", sealed=True)
    assert (status["kind"], status["reason"], status["cell"]) == ("budget", "budget_stop", "cell-1")
    ran = []
    with pytest.raises(Pause) as stopped:
        run_unit(root, run=RUN, identity=IDENTITY, work=ran.append)
    assert (stopped.value.kind, stopped.value.reason, ran) == ("awaiting_owner_decision", "attempt-1", [])
    assert cli.main(["recover", "--unit-root", str(root), "--decision", "the cap was raised"]) == 0
    assert read_json(root / "attempt-1" / "recovery.json")["by"] == "owner"
    record = run_unit(root, run=RUN, identity=IDENTITY, work=lambda attempt: {"attempt": attempt.name})
    assert record["attempt"] == "attempt-2" and record["result"] == {"attempt": "attempt-2"}
    with pytest.raises(ValueError):  # a complete unit has nothing to recover
        cli.main(["recover", "--unit-root", str(root), "--decision", "again"])
    with pytest.raises(ValueError):  # nor has a unit that never ran
        cli.main(["recover", "--unit-root", str(tmp_path / "never"), "--decision", "again"])


@pytest.mark.parametrize("error, kind", [(ValueError("bad configuration"), "configuration"),
                                         (KeyError("crash"), "exception"),
                                         (ConfigurationError("invalid_model_receipt"), "configuration"),
                                         (BudgetStop("cap"), "budget"), (AssumptionBroken("bound"), "assumption"),
                                         (LedgerFailure("ledger_failure:OSError"), "ledger")])
def test_an_error_pauses_the_unit_and_keeps_its_traceback(tmp_path, error, kind):
    def work(attempt):
        raise error
    with pytest.raises(Pause) as stopped:
        run_unit(tmp_path / "u", run=RUN, identity=IDENTITY, work=work)
    attempt = tmp_path / "u" / "attempt-1"
    assert stopped.value.kind == kind and read_json(attempt / "status.json", sealed=True)["kind"] == kind
    assert type(error).__name__ in (attempt / "diagnostics.log").read_text(encoding="utf-8")


def test_an_interrupted_attempt_also_waits_for_the_owner(tmp_path):
    (tmp_path / "u" / "attempt-1").mkdir(parents=True)  # started, then the process ended without a status
    with pytest.raises(Pause) as stopped:
        run_unit(tmp_path / "u", run=RUN, identity=IDENTITY, work=lambda attempt: {})
    assert (stopped.value.kind, stopped.value.reason) == ("awaiting_owner_decision", "attempt-1")


# -------------------------------------------------------------------------------------------------- manifest
def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rubric(scope):
    return {"bench": scope, "items": [{"id": "G1" if scope == GENERAL else "R1", "text": "On topic.", "check": None,
                                       "basis": "The card."}]}


def _manifest(root, *, code=None, environment=None):
    archive = root / "archive"
    archive.mkdir(parents=True)
    (archive / "a.txt").write_text("towns grew", encoding="utf-8")
    (archive / "index.json").write_text(json.dumps({"a.txt": {"sha256": _sha(archive / "a.txt"), "title": "Doc"}}),
                                        encoding="utf-8")
    (archive / "sources.json").write_text(json.dumps({"a.txt": "https://example.org/a"}), encoding="utf-8")
    value = {"version": VERSION + "-manifest", "root": str(root / "run"), "data": {"fixture": True},
             "sheet_qualification": {"path": str(root / "qualification.json"), "record_hash": "q1"},
             "regression": {b: {"items": [], "tolerance": 0} for b in ORDER}, "tolerance": {b: 5 for b in ORDER},
             "cards": texts.CARDS, "instructions": {b: "- Read the task.\n" for b in ORDER},
             "rubrics": {b: _rubric(b) for b in (*ORDER, GENERAL)}, "runtime": RUNTIME,
             "clients": {"repo": str(root), "proxy": None},
             "research": {"archive": str(archive), "index_sha256": _sha(archive / "index.json"),
                          "sources_sha256": _sha(archive / "sources.json"), "proxy": None},
             "baseline": {"model": {"provider": "bigmodel", "name": "glm-5.3"}, "service": {"max_retries": 2},
                          "repo": str(root), "gepa_source": str(root / "gepa")},
             "workers": 4, "code": manifest.pin_code() if code is None else code,
             "provenance": {"prior_glm_tokens": {"total": 7}, **manifest.environment(), **(environment or {})}}
    write_json(root / "manifest.json", seal(value))
    return root / "manifest.json"


@pytest.fixture
def fixture_data(monkeypatch):
    def pool(pinned, bench):
        assert pinned == {"fixture": True}
        return [{"benchmark": bench, "task_id": "%s-%d" % (bench, n), "family_id": "f%d" % n, "part": "train",
                 "public": {}, "private": {}} for n in range(3)]
    qualification = {"record_hash": "q1", "side": "train", "qualified": ["spreadsheetbench-1"]}
    monkeypatch.setattr(manifest.data, "pool", pool)
    monkeypatch.setattr(manifest.qualify, "load", lambda path: qualification)
    return qualification


def test_a_manifest_builds_the_setting(tmp_path, fixture_data):
    path = _manifest(tmp_path)
    value, setting = manifest.load(path)
    assert setting.run == value["record_hash"] and setting.root == tmp_path / "run"
    assert setting.shared == tmp_path / "run" / "shared" and setting.workers == 4
    assert [i["task_id"] for i in setting.pools["spreadsheetbench"]] == ["spreadsheetbench-1"]
    assert len(setting.pools["searchqa"]) == 3 and set(setting.slots) == set(SLOTS)
    assert setting.rubrics[GENERAL] == _rubric(GENERAL) and setting.extra["manifest"] == str(path)
    assert setting.extra["baseline"] == value["baseline"] and setting.extra["overall"] == OVERALL_CEILING - 7
    setting.extra["verify"]()  # the pinned files still have their hashes


def test_a_changed_pinned_file_or_qualification_refuses_the_run(tmp_path, fixture_data):
    path = _manifest(tmp_path, code={**manifest.pin_code(), "skillopt/coevo5/protocol.py": "0" * 64})
    with pytest.raises(ValueError, match="differ"):
        manifest.load(path)
    manifest.load(path, verify=False)  # the monitor and the owner's decisions still read it
    fixture_data["record_hash"] = "q2"
    with pytest.raises(ValueError):
        manifest.load(path, verify=False)
    fixture_data.update(record_hash="q1", side="test")
    with pytest.raises(ValueError):
        manifest.load(path, verify=False)


def test_a_code_map_must_hold_every_loaded_file_and_the_archive_is_bound(tmp_path, fixture_data):
    code = manifest.pin_code()
    assert {"skillopt/coevo5/step.py", "scripts/run_coevo5.py", "skillopt/continual_eval/backends.py",
            "skillopt/prompts/ranking.md", "skillopt/continual_eval/runtime/Dockerfile"} <= set(code)
    assert manifest.loaded_code() <= set(code) and not any(name.startswith("tests/") for name in code)
    del code["skillopt/coevo5/step.py"]
    with pytest.raises(ValueError, match="missing"):
        manifest.load(_manifest(tmp_path / "a", code=code))
    path = _manifest(tmp_path / "b")
    archive = tmp_path / "b" / "archive"
    (archive / "a.txt").write_text("towns shrank", encoding="utf-8")  # a document and its index replaced together
    (archive / "index.json").write_text(json.dumps({"a.txt": {"sha256": _sha(archive / "a.txt"), "title": "Doc"}}),
                                        encoding="utf-8")
    with pytest.raises(ValueError, match="archive"):
        manifest.load(path)
    path = _manifest(tmp_path / "c")
    (tmp_path / "c" / "archive" / "sources.json").write_text(json.dumps({"a.txt": "https://example.org/b"}),
                                                             encoding="utf-8")  # a page from another address
    with pytest.raises(ValueError, match="archive"):
        manifest.load(path)


@pytest.mark.parametrize("environment", [{"openpyxl": "3.0.0"}, {"python": "3.9.0"}, {"openpyxl": None}])
def test_another_interpreter_or_workbook_library_refuses_the_run(tmp_path, fixture_data, environment):
    path = _manifest(tmp_path, environment=environment)
    with pytest.raises(ValueError, match="interpreter or openpyxl"):
        manifest.load(path)
    manifest.load(path, verify=False)  # the monitor and the owner's decisions still read it


def test_no_chain_runs_before_the_baselines_are_checked_for_this_run(tmp_path, fixture_data, monkeypatch):
    path = _manifest(tmp_path)
    ran = []
    monkeypatch.setattr(cli.chains, "run", lambda *a, **k: ran.append(a))
    with pytest.raises(ValueError, match="check-baselines"):
        cli.main(["run", "--manifest", str(path), "--chain", "E-ds"])
    _, setting = manifest.load(path)
    write_json(setting.shared / "baselines-checked.json", seal({"run": "another run", "found": {}}))
    with pytest.raises(ValueError, match="check-baselines"):  # a marker of another run counts for nothing
        cli.main(["run", "--manifest", str(path), "--chain", "E-ds"])
    assert ran == []
