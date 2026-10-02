import json
from pathlib import Path

import pytest

from skillopt.continual_eval.core import (
    BENCHMARKS,
    freeze_plan,
    load_plan,
    output_lock,
    public_view,
    read_json,
    register_checkpoint,
    write_json,
)
from skillopt.continual_eval.fixtures import fixture_config, fixture_score, fixture_solve, smoke
from skillopt.continual_eval.runner import close_interrupted, generate, position, report, score_checkpoint


def setup_run(tmp_path, **kwargs):
    root = tmp_path / "run"
    config = fixture_config(root, **kwargs)
    plan = freeze_plan(config, root)
    return root, config, plan


def test_complete_smoke_and_no_new_positions_on_replay(tmp_path):
    first = smoke(tmp_path / "smoke")
    second = smoke(tmp_path / "smoke")
    assert first["positions"] == 30 and first["new_positions"] == 30
    assert second["new_positions"] == 0
    assert first["report_hash"] == second["report_hash"]
    assert first["real_model_calls"] == first["real_benchmark_runs"] == 0


def test_public_view_is_copy_and_whitelist():
    task = {"public": {"question": "q"}, "private": {"answer": "SECRET"}, "condition": "candidate"}
    view = public_view(task)
    assert view == {"question": "q"}
    view["question"] = "other"
    assert task["public"]["question"] == "q"


def test_predictions_before_scores_and_missing_cells(tmp_path):
    root, _, _ = setup_run(tmp_path)
    result = generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa",
                      fixture_solve=fixture_solve)
    assert result["scores_read"] is False
    assert not (root / "host_only" / "scores").exists()
    before = report(root)
    assert before["summary"]["runs"][0]["matrix"]["0"]["searchqa"]["status"] == "pending"
    score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="searchqa", fixture_score=fixture_score)
    after = report(root)
    cell = after["summary"]["runs"][0]["matrix"]["0"]["searchqa"]
    assert cell["status"] == "complete"


def test_immutable_checkpoint_and_ancestry(tmp_path):
    root, _, _ = setup_run(tmp_path, methods=["no_skill", "ours"])
    with pytest.raises(FileNotFoundError):
        register_checkpoint(root, "ours", "h0", 2, "rule", provenance="test")
    register_checkpoint(root, "ours", "h0", 1, "rule", provenance="test")
    with pytest.raises(ValueError, match="Immutable"):
        register_checkpoint(root, "ours", "h0", 1, "new", provenance="test")
    with pytest.raises(ValueError, match="No-Skill"):
        register_checkpoint(root, "no_skill", "h0", 1, "rule", provenance="test")


def test_changed_panel_fails_before_backend(tmp_path):
    root, config, _ = setup_run(tmp_path)
    path = config["panels"]["searchqa"]
    panel = read_json(path)
    panel["tasks"][0]["private"]["answers"] = ["red"]
    with open(path, "w") as handle:
        json.dump(panel, handle)
    with pytest.raises(ValueError, match="Frozen"):
        load_plan(root)


def test_interruption_is_not_resampled(tmp_path):
    root, _, _ = setup_run(tmp_path)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa", fixture_solve=interrupt)
    with pytest.raises(ValueError, match="Interrupted position"):
        generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa", fixture_solve=fixture_solve)
    base = next((root / "predictions").iterdir())
    from skillopt.coevolution_v5.core import seal
    write_json(base / "call_intents" / "request.json", seal({"public_request": True}))
    close_interrupted(root, base.name)
    terminal = read_json(base / "prediction.json", sealed=True)
    assert terminal["costs"]["reported_tokens"] is None
    assert terminal["costs"]["usage_complete"] is False
    result = generate(root, method="no_skill", history="h0", stage=0, benchmark="searchqa", fixture_solve=fixture_solve)
    assert result["new_positions"] == 0 and result["unknown"] == 1


def test_reject_secrets_in_config(tmp_path):
    root = tmp_path / "run"
    config = fixture_config(root)
    config["runtime"] = {"searchqa": {"api_key": "DO_NOT_USE"}}
    with pytest.raises(ValueError, match="Credentials"):
        freeze_plan(config, root)


def test_exposed_family_cannot_enter_final(tmp_path):
    root = tmp_path / "run"
    config = fixture_config(root)
    path = root / "exposure.json"
    write_json(path, {"version": "continual-exposure-v1", "records": [
        {"benchmark": "searchqa", "task_id": "old-other-task", "family_id": "fixture-family", "purpose": "development"}]})
    config["exposure_manifest"] = str(path)
    with pytest.raises(ValueError, match="Historically exposed"):
        freeze_plan(config, root)


def test_partial_suite_remains_pending(tmp_path):
    root = tmp_path / "run"
    config = fixture_config(root)
    for benchmark in BENCHMARKS:
        if benchmark != "searchqa":
            config["panels"][benchmark] = None
    plan = freeze_plan(config, root)
    assert not plan["protocol_complete"] and len(plan["tasks"]) == 1
    assert report(root)["summary"]["runs"][0]["forward_transfer"]["status"] == "pending"


def test_frozen_paths_survive_changing_launch_directory(tmp_path, monkeypatch):
    root = tmp_path / "run"
    config = fixture_config(root)
    monkeypatch.chdir(tmp_path)
    config["panels"] = {b: str(Path(p).relative_to(tmp_path))
                        for b, p in config["panels"].items()}
    original = freeze_plan(config, root)
    monkeypatch.chdir(root)
    assert load_plan(root) == original


def test_output_lock_excludes_second_writer(tmp_path):
    with output_lock(tmp_path):
        with pytest.raises(ValueError, match="Another process"):
            with output_lock(tmp_path):
                pass


def test_native_models_cannot_use_fixture_panels(tmp_path):
    root = tmp_path / "run"
    config = fixture_config(root)
    config["model"].update(provider="bigmodel", name="glm-5.3")
    with pytest.raises(ValueError, match="Fixture"):
        freeze_plan(config, root)


def test_position_prediction_binding(tmp_path):
    root, _, plan = setup_run(tmp_path)
    from skillopt.continual_eval.core import load_checkpoint, panel_tasks
    cp = load_checkpoint(root, "no_skill", "h0", 0, plan)
    task = panel_tasks(plan, "searchqa")[0]
    first, _ = position(root, cp, "searchqa", task, 0)
    second, _ = position(root, cp, "searchqa", task, 1)
    assert first != second


def test_container_metadata_survives_scoring_without_overriding_host(tmp_path):
    root, _, _ = setup_run(tmp_path)
    generate(root, method="no_skill", history="h0", stage=0, benchmark="bigcodebench",
             fixture_solve=fixture_solve)

    def native_receipt(*args, **kwargs):
        return {"status": "pass", "score": 1.0, "metrics": {}, "reason": "fixture_native_pass",
                "runtime_image_id": "sha256:" + "a" * 64, "runtime_architecture": "amd64",
                "cleanup_confirmed": True, "execution_costs": {"container_calls": 1, "wall_seconds": 1.2}}

    score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="bigcodebench",
                     fixture_score=native_receipt)
    row = read_json(next((root / "host_only/scores").glob("*.json")), sealed=True)
    assert row["method"] == "no_skill" and row["runtime_architecture"] == "amd64"
    assert row["execution_costs"]["container_calls"] == 1
    assert report(root)["run_accounting"]["scored_positions"] == 1
