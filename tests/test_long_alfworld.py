"""Authored metadata fixtures: no real benchmark episodes or model calls."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import prepare_long_alfworld as prepare
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import BENCHMARKS, build_plan, freeze_plan, read_json, write_json


def inputs(tmp_path, monkeypatch):
    legacy, data_root = tmp_path / "old", tmp_path / "native-data"
    tasks = []
    for i in range(39):
        game = data_root / f"json_2.1.1/train/scenario{i}/trial_0/game.tw-pddl"
        game.parent.mkdir(parents=True)
        game.write_text("Authored inert game fixture, never executed")
        tasks.append({"task_id": str(i), "family_id": f"scenario-{i}", "project_id": "", "partition": "development",
            "public": {"game_file": str(game)}, "private": {"game_metadata": {
                "source_split": "train", "asset_files": [], "private_canary": "HOST_ONLY_SENTINEL"},
                "asset_sha256": {str(game): hashlib.sha256(game.read_bytes()).hexdigest()}}})
    panel = legacy / "data/panel.json"
    write_json(panel, {"version": "continual-panel-v1", "benchmark": "alfworld", "provenance": "natural",
                      "dataset_revision": "authored-fixture-only", "tasks": tasks})
    runtime = {"alfworld_data": str(data_root), "alfworld_split": "train", "max_steps": 50,
               "timeout_seconds": 60, "seed": 42}
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
        "panels": {b: str(panel) if b == "alfworld" else None for b in BENCHMARKS},
        "methods": ["no_skill"], "histories": ["h0"], "partition": "development", "repeats": 2,
        "project_disjoint": False, "exposure_manifest": None, "runtime": {"alfworld": runtime},
        "model": {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 4096,
                  "reasoning_effort": "low", "proxy": prepare.PROXY}}
    old = build_plan(config)
    old.pop("record_hash")
    source = legacy / "skillopt/continual_eval/backends.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(Path(backends.__file__).read_bytes())
    old["source_identity"] = {"continual_eval/backends.py": hashlib.sha256(source.read_bytes()).hexdigest()}
    package = Path(backends.__file__).parents[1]
    for relative, expected in prepare.source_identity().items():
        if relative.startswith("envs/alfworld/vendor/"):
            destination = legacy / "skillopt" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((package / relative).read_bytes())
            old["source_identity"][relative] = expected
    write_json(legacy / "run/plan.json", seal(old))
    shared = deepcopy(config)
    shared["version"] = "continual-eval-v2"
    shared["model"].update(max_tokens=65536, transport=deepcopy(prepare.TRANSPORT))
    common = tmp_path / "common"
    common_plan = freeze_plan(shared, common)
    # Different benchmark Python/packages: shared model/source must still work.
    common_plan.pop("record_hash")
    common_plan["host_runtime"]["packages"]["alfworld"] = "another-native-host"
    (common / "plan.json").write_text(json.dumps(seal(common_plan)))
    service = {"provider": "BIGMODEL", "host": "open.bigmodel.cn", "path": "/api/paas/v4/chat/completions",
               "model": "glm-5.3", "reasoning_effort": "low", "proxy": prepare.PROXY, "stream": True,
               "stream_max_wall_seconds": 1800, "initial_health_policy": "completed_response_v1",
               "trust_env": False, "stream_transport": "async-whole-attempt-deadline-v1",
               "timeout_seconds": {"read": 300}}
    write_json(common / "model_service.json", seal(service))
    monkeypatch.setenv("ALFWORLD_DATA", str(data_root))
    monkeypatch.setattr(backends, "readiness", lambda b, r: {"status": "ready"})
    return legacy, common, data_root


def test_full_panel_offline_prepare_replay_different_native_host(tmp_path, monkeypatch, capsys):
    legacy, common, data = inputs(tmp_path, monkeypatch)
    # These unclosed historical calls deliberately have invalid JSON; a read
    # would fail. The new run must not consume, close, import or retry them.
    for i in range(8):
        path = legacy / "run/api" / f"open-call-{i}/intent.json"
        path.parent.mkdir(parents=True)
        path.write_text("UNCONSUMED_HISTORICAL_OPEN_CALL")
    def forbidden(*args, **kwargs):
        pytest.fail("Preparation must not start models, episodes or read credentials")
    # Preserve CachedAPI's signature inspection, but its configuration must not run.
    monkeypatch.setattr("skillopt.validator_pilot.api._configuration", forbidden)
    monkeypatch.setattr(backends, "_new_alfworld", forbidden)
    monkeypatch.setattr(backends, "score", forbidden)
    before = {str(p): p.read_bytes() for r in (legacy, common, data) for p in r.rglob("*") if p.is_file()}
    real_read = prepare.read_json
    def metadata_only(path, **kwargs):
        assert Path(path).name not in {"prediction.json", "score.json", "report.json"}
        return real_read(path, **kwargs)
    monkeypatch.setattr(prepare, "read_json", metadata_only)
    output = tmp_path / "new"
    value = prepare.prepare(legacy, common, output)
    assert (value["tasks"], value["families"], value["positions"], value["model_calls"], value["episodes_started"]) == (39, 39, 78, 0, 0)
    assert value["max_logical_calls"] == 3900 and value["workers"] == 2
    assert value["alf_host_runtime"] != value["common_host_runtime"]
    assert not value["identical_cross_benchmark_host_claimed"] and not value["native_environment_upgraded"]
    assert not value["old_answers_imported"] and not value["old_open_calls_resumed"]
    assert prepare.check(output) == value
    assert before == {str(p): p.read_bytes() for r in (legacy, common, data) for p in r.rglob("*") if p.is_file()}
    plan = read_json(output / "run/plan.json", sealed=True)
    assert plan["host_runtime"] == read_json(legacy / "run/plan.json", sealed=True)["host_runtime"]
    assert plan["config"]["runtime"] == read_json(legacy / "run/plan.json", sealed=True)["config"]["runtime"]
    assert len(plan["tasks"]) == 39 and not (output / "run/api").exists()
    assert prepare.main(["--check", "--output", str(output)]) == 0
    assert "HOST_ONLY_SENTINEL" not in capsys.readouterr().out
    with pytest.raises(ValueError, match="independent"):
        prepare.prepare(legacy, common, output)


@pytest.mark.parametrize("change", ["subset", "source", "vendor", "panel", "runtime", "budget", "final", "model", "host", "httpx", "service", "environment", "asset", "dependency"])
def test_reject_changed_inputs_before_writes(tmp_path, monkeypatch, change):
    legacy, common, data = inputs(tmp_path, monkeypatch)
    if change == "source":
        (legacy / "skillopt/continual_eval/backends.py").write_text("# changed")
    elif change == "vendor":
        next((legacy / "skillopt/envs/alfworld/vendor").glob("*.py")).write_text("# changed")
    elif change == "panel":
        path = legacy / "data/panel.json"
        panel = read_json(path)
        panel["tasks"] = panel["tasks"][:-1]
        path.write_text(json.dumps(panel))
    elif change == "environment":
        monkeypatch.delenv("ALFWORLD_DATA")
    elif change == "asset":
        next(data.rglob("game.tw-pddl")).write_text("changed asset")
    elif change == "dependency":
        monkeypatch.setattr(backends, "readiness", lambda b, r: {"status": "unsupported"})
    else:
        path = common / "plan.json" if change in {"budget", "httpx"} else legacy / "run/plan.json"
        if change == "service":
            path = common / "model_service.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        if change == "subset":
            value["tasks"] = value["tasks"][:-1]
        elif change == "runtime":
            value["config"]["runtime"]["alfworld"]["max_steps"] = 100
        elif change == "budget":
            value["config"]["model"]["max_tokens"] = 8192
        elif change == "final":
            value["config"]["partition"] = "final"
        elif change == "model":
            value["config"]["model"]["name"] = "another-model"
        elif change == "host":
            value["host_runtime"]["python"] = "0.0.0"
        elif change == "httpx":
            value["host_runtime"]["packages"]["httpx"] = "0.0.0"
        else:
            value["stream_max_wall_seconds"] = 300
        path.write_text(json.dumps(seal(value)))
    output = tmp_path / "new"
    with pytest.raises(ValueError):
        prepare.prepare(legacy, common, output)
    assert not output.exists()


def test_goal_retention_implementation_mismatch_rejected(tmp_path, monkeypatch):
    legacy, common, _ = inputs(tmp_path, monkeypatch)
    source = legacy / "skillopt/continual_eval/backends.py"
    source.write_text(source.read_text().replace('"initial_observation": initial_observation,', '"initial_observation": "",'))
    old = read_json(legacy / "run/plan.json", sealed=True)
    old.pop("record_hash")
    old["source_identity"]["continual_eval/backends.py"] = hashlib.sha256(source.read_bytes()).hexdigest()
    (legacy / "run/plan.json").write_text(json.dumps(seal(old)))
    with pytest.raises(ValueError, match="goal retention"):
        prepare.prepare(legacy, common, tmp_path / "new")


@pytest.mark.parametrize("target", ["asset", "service", "config"])
def test_prepared_check_rejects_later_changes(tmp_path, monkeypatch, target):
    legacy, common, data = inputs(tmp_path, monkeypatch)
    output = tmp_path / "new"
    prepare.prepare(legacy, common, output)
    path = next(data.rglob("game.tw-pddl")) if target == "asset" else common / "model_service.json" if target == "service" else output / "config.json"
    path.write_text("changed")
    with pytest.raises(ValueError):
        prepare.check(output)
