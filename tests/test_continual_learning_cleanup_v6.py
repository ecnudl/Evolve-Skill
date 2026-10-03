"""Offline cleanup regression controls; no model or Docker calls are made."""
import json
from copy import deepcopy

import pytest

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning.contracts import HARDENED_VERSION, manifest, validate_manifest
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY_V6, client_options
from skillopt.continual_learning.skillopt import run_stage
from skillopt.skill_validation.sandbox import _Command
from tests.test_continual_learning_delivery_v5 import auth as legacy_auth
from tests.test_continual_learning_domains import API, evaluate, setup


def auth(benchmark="searchqa"):
    _, panel, args = setup(benchmark)
    args.update(version=HARDENED_VERSION, recovery_policy=deepcopy(POLICY_V6))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    if benchmark == "bigcodebench":
        args["runtime"] = {"image": "sha256:" + "a" * 64}
    return manifest(panel, **args), panel


class OfflineAPI(API):
    service = {"fixture": "offline", "max_retries": 2,
               "delivery_retry_policy": "closed_delivery_error_v3"}

    def call(self, *args, **kwargs):
        row = super().call(*args, **kwargs)
        row["attempts"] = [{"usage": dict(row["usage"])}]
        return row


def test_v6_manifest_and_policy_are_opt_in():
    value, panel = auth()
    assert validate_manifest(value, panel) == value
    assert client_options(value) == {"delivery_retry_policy": "closed_delivery_error_v3"}
    assert value["recovery_policy"]["unknown_score"] == "paired_known_exclusion_guarded_v1"


@pytest.mark.parametrize("version", ["v5", "v6"])
def test_cleanup_failure_stops_native_before_second_task_only_in_v6(tmp_path, monkeypatch, version):
    value, panel = auth("bigcodebench") if version == "v6" else legacy_auth()
    if version == "v5":
        _, panel, args = setup("bigcodebench")
        args.update(version=value["version"], recovery_policy=value["recovery_policy"])
        args["model"]["transport"]["stream_wall_seconds"] = 3600
        args["runtime"] = {"image": "sha256:" + "a" * 64}
        value = manifest(panel, **args)
    commands, solver = [], []
    monkeypatch.setattr(backends, "_image_ready", lambda _: {"status": "ready", "image_id": "fixture"})
    monkeypatch.setattr(backends.shutil, "which", lambda _: "docker")

    def command(argv, *args, **kwargs):
        commands.append(argv[1])
        if argv[1] == "rm":
            return _Command(1)
        return _Command(0, json.dumps({"protocol": backends.PROTOCOL, "result": {
            "status": "pass", "score": 1.0, "metrics": {}, "reason": "fixture"}}).encode())

    def solve(*args, **kwargs):
        solver.append(1)
        return {"status": "available", "output": "def f(): return 1", "reason": "fixture"}

    monkeypatch.setattr(backends, "_bounded_command", command)
    monkeypatch.setattr(backends, "solve", solve)
    adapter = Adapter(value, tmp_path, Ledger(tmp_path, value, OfflineAPI()))
    batch = [{"role": "selection", "task": t} for t in panel["tasks"][2:]]
    if version == "v6":
        with pytest.raises(LearningPending, match="cleanup_unconfirmed"):
            adapter.evaluate_rows(batch, {"skill": ""})
        assert commands == ["run", "rm"] and len(solver) == 1
        # A new Adapter must also reject the cached unsafe receipt, with no calls.
        replay = Adapter(value, tmp_path, Ledger(tmp_path, value, OfflineAPI()))
        with pytest.raises(LearningPending, match="cleanup_unconfirmed"):
            replay.evaluate_rows(batch, {"skill": ""})
        assert commands == ["run", "rm"] and len(solver) == 1
    else:
        rows = adapter.evaluate_rows(batch, {"skill": ""})
        assert [r["score"] for r in rows] == [None, None]
        assert commands == ["run", "rm", "run", "rm"] and len(solver) == 2


@pytest.mark.parametrize("location", ["prediction", "score", "nested", "receipt"])
def test_v6_cleanup_guard_preserves_evidence_and_stays_pending(tmp_path, location):
    value, panel = auth()
    seen = []

    def execute(task, skill):
        seen.append(task["task_id"])
        prediction, score = evaluate("searchqa")(task, skill)
        if location == "prediction":
            prediction["cleanup_confirmed"] = False
        elif location == "score":
            score.update(status="unknown", score=None, reason="container_cleanup_unconfirmed")
        elif location == "nested":
            score["metrics"] = {"cases": [{"cleaned_up": False}]}
        else:
            key = next((tmp_path / "evaluation_intents").glob("*.json")).stem
            write_json(tmp_path / "host_only/scorer_artifacts" / key / "native.json",
                       {"cleanup_confirmed": False})
        return prediction, score

    api = OfflineAPI()
    adapter = Adapter(value, tmp_path, Ledger(tmp_path, value, api), fixture_evaluate=execute)
    batch = [{"role": "selection", "task": t} for t in panel["tasks"][2:]]
    with pytest.raises(LearningPending, match="cleanup_unconfirmed"):
        adapter.evaluate_rows(batch, {"skill": ""})
    assert seen == ["2"] and not api.calls
    assert len(list((tmp_path / "evaluations").glob("*.json"))) == 1
    with pytest.raises(LearningPending, match="cleanup_unconfirmed"):
        adapter.evaluate_rows(batch[1:], {"skill": ""})
    assert seen == ["2"]


def test_v6_prediction_cleanup_failure_prevents_scoring(tmp_path, monkeypatch):
    value, panel = auth()
    monkeypatch.setattr(backends, "solve", lambda *a, **k: {
        "status": "unknown", "output": None, "reason": "alfworld_cleanup_unconfirmed"})
    monkeypatch.setattr(backends, "score", lambda *a, **k: pytest.fail("No scorer may run after unsafe cleanup"))
    adapter = Adapter(value, tmp_path, Ledger(tmp_path, value, OfflineAPI()))
    with pytest.raises(LearningPending, match="cleanup_unconfirmed"):
        adapter.evaluate_rows([{"role": "selection", "task": panel["tasks"][2]}], {"skill": ""})
    record = read_json(next((tmp_path / "evaluations").glob("*.json")), sealed=True)
    assert record["score"]["status"] == "unknown"


@pytest.mark.parametrize("guarded", [False, True])
def test_spreadsheet_guard_stops_cases_within_one_task(monkeypatch, guarded):
    calls = []
    monkeypatch.setattr(backends, "_sheet_preview", lambda *a, **k: [])
    monkeypatch.setattr(backends, "_xlsx_bytes", lambda p: b"offline workbook fixture")

    def native(request, runtime):
        calls.append(request)
        return {"status": "unknown", "reason": "container_cleanup_unconfirmed",
                "cleanup_confirmed": False}

    monkeypatch.setattr(backends, "_native", native)
    public = {"instruction": "Fixture only", "input_files": ["one.xlsx", "two.xlsx"],
              "answer_position": "Sheet1!A1"}
    result = backends.solve("spreadsheetbench", public, "", lambda *a: {
        "ok": True, "response": "```python\npass\n```", "finish_reason": "stop"},
        runtime={"_stop_on_cleanup_failure": True} if guarded else {})
    assert len(calls) == (1 if guarded else 2)
    assert len(result["output"]["cases"]) == 2
    if guarded:
        assert result["output"]["cases"][1]["reason"] == "not_executed_after_cleanup_failure"


def test_v6_clean_unknown_can_continue_and_completed_stage_replays(tmp_path):
    value, panel = auth()
    api = OfflineAPI()

    def execute(task, skill):
        prediction, score = evaluate("searchqa")(task, skill)
        score["cleanup_confirmed"] = True
        if task["task_id"] == "3":
            score.update(status="unknown", score=None, reason="fixture_unavailable")
        return prediction, score

    result = run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=execute)
    assert result["status"] == "completed", result
    assert result["steps"][0]["gate_action"] == "accept_new_best"
    calls = len(api.calls)
    assert run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=execute) == result
    assert len(api.calls) == calls


def test_v6_stage_stops_before_reflection_and_pending_replays(tmp_path):
    value, panel = auth()
    api, seen = OfflineAPI(), []

    def execute(task, skill):
        seen.append(task["task_id"])
        prediction, score = evaluate("searchqa")(task, skill)
        score.update(status="unknown", score=None, reason="container_cleanup_unconfirmed")
        return prediction, score

    result = run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=execute)
    assert result["status"] == "pending" and result["reason"] == "native_cleanup_unconfirmed"
    assert seen == ["2"] and api.calls == [] and result["steps"] == []
    assert run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=execute) == result
    assert seen == ["2"] and api.calls == []


def test_v6_offline_cli_smoke(tmp_path):
    from scripts.run_continual_learning import main

    value, panel = auth()
    write_json(tmp_path / "manifest.json", value)
    write_json(tmp_path / "panel.json", panel)
    args = ["--manifest", str(tmp_path / "manifest.json"), "--panel", str(tmp_path / "panel.json"),
            "--execute", "--fixture", "--output", str(tmp_path / "run")]
    assert main(args) == 0
    result = read_json(tmp_path / "run/result.json", sealed=True)
    assert result["status"] == "completed" and result["evidence_kind"] == "engineering_fixture"
    assert main(args) == 0
    assert read_json(tmp_path / "run/result.json", sealed=True) == result
