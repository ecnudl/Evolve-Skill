"""CLI is opt-in, development-only, and actually dispatches both learner engines."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

from scripts.run_continual_learning import main
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning.contracts import manifest


def inputs(tmp_path, method="skillopt", *, natural=False):
    panel = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "cli-fixture-v1",
             "provenance": "natural" if natural else "fixture", "tasks": [
                 {"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
                  "public": {"prompt": "Authored fixture contract.", "entry_point": "solve"},
                  "private": {"test": "HOST_ONLY_TEST_SENTINEL"}} for i in range(4)]}
    model = {"provider": "bigmodel" if natural else "fixture", "name": "glm-5.3" if natural else "fixture",
             "max_tokens": 512, "reasoning_effort": "low"}
    budget = {"max_metric_calls": 32, "max_reflection_calls": 10, "max_api_calls": 20,
              "max_reported_tokens": 10000, "max_iterations": 1, "minibatch_size": 2,
              "solver_max_tokens": 512, "reflection_max_tokens": 512}
    value = manifest(panel, train_families=["0", "1"], selection_families=["2", "3"],
                     model=model, budget=budget, method=method)
    write_json(tmp_path / "manifest.json", value)
    write_json(tmp_path / "panel.json", panel)
    return ["--manifest", str(tmp_path / "manifest.json"), "--panel", str(tmp_path / "panel.json")]


def test_default_preview_no_execution(tmp_path, capsys):
    assert main(inputs(tmp_path, natural=True)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "validated_not_executed"
    assert report["model_calls_submitted"] == 0
    assert not (tmp_path / "run").exists()


def test_fixture_cannot_override_natural(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(inputs(tmp_path, natural=True) + ["--execute", "--fixture", "--output", str(tmp_path / "run")])
    assert exc.value.code == 2


def test_method_mismatch(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(inputs(tmp_path) + ["--method", "gepa"])
    assert exc.value.code == 2


def test_execute_requires_output_and_fixture_switch(tmp_path):
    args = inputs(tmp_path)
    with pytest.raises(SystemExit):
        main(args + ["--execute"])
    with pytest.raises(SystemExit):
        main(args + ["--execute", "--output", str(tmp_path / "run")])


def test_skillopt_real_native_fixture_cli(tmp_path, capsys):
    args = inputs(tmp_path) + ["--execute", "--fixture", "--output", str(tmp_path / "run")]
    assert main(args) == 0
    capsys.readouterr()
    result = read_json(tmp_path / "run/result.json", sealed=True)
    assert result["status"] == "completed"
    assert result["selected_score"] == 1.0
    assert "Handle empty inputs." in result["candidate_skill"]
    assert result["evidence_kind"] == "engineering_fixture"
    assert not result["deployment_authorized"]


def test_gepa_real_engine_fixture_cli(tmp_path):
    source = Path(os.environ.get("GEPA_OFFICIAL_SOURCE", Path(__file__).resolve().parents[1] /
                                "outputs/continual_eval/baseline_preparation_20260928/gepa"))
    if not source.is_dir() or importlib.util.find_spec("gepa") is None:
        pytest.skip("Optional pinned GEPA not installed")
    args = inputs(tmp_path, method="gepa") + ["--execute", "--fixture", "--output", str(tmp_path / "run"),
                                               "--gepa-source", str(source)]
    assert main(args) == 0
    result = read_json(tmp_path / "run/result.json", sealed=True)
    assert result["status"] == "completed"
    assert result["official_result"]["val_aggregate_scores"] == [0.0, 1.0]
