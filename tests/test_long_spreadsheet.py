"""Authored source/qualification fixtures, not new Sheet model or Calc runs."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import prepare_long_spreadsheet as prepare
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import BENCHMARKS, build_plan, freeze_plan, read_json, write_json
from tests.test_continual_eval_sheet_recalc_adapter import setup as qualification_fixture


def inputs(tmp_path, monkeypatch):
    (tmp_path / "authored").mkdir()
    public, private, _, qualified, _, _ = qualification_fixture(tmp_path / "authored", monkeypatch)
    legacy, approved = tmp_path / "old", tmp_path / "reviewed-adapter"
    tasks = [{"task_id": str(i), "family_id": f"family-{i}", "project_id": "", "partition": "development",
              "public": deepcopy(public), "private": deepcopy(private)} for i in range(80)]
    for task in tasks:
        task["private"]["asset_sha256"].update({p: prepare._sha(p) for p in public["input_files"]})
    panel = legacy / "data/panel.json"
    write_json(panel, {"version": "continual-panel-v1", "benchmark": "spreadsheetbench", "provenance": "natural",
                      "dataset_revision": "authored-fixture-only", "tasks": tasks})
    runtime = {"image": "sha256:" + "b" * 64, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1,
               "spreadsheet_scorer": "spreadsheetbench-official-quote-and-string-cache-v1"}
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
        "panels": {b: str(panel) if b == "spreadsheetbench" else None for b in BENCHMARKS},
        "methods": ["no_skill"], "histories": ["h0"], "partition": "development", "repeats": 2,
        "project_disjoint": False, "exposure_manifest": None, "runtime": {"spreadsheetbench": runtime},
        "model": {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 4096,
                  "reasoning_effort": "low", "proxy": prepare.PROXY}}
    old = build_plan(config)
    old.pop("record_hash")
    package = Path(backends.__file__).parents[1]
    old["source_identity"] = {}
    for name in ("continual_eval/backends.py", "continual_eval/native_worker.py"):
        source = legacy / "skillopt" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((package / name).read_bytes())
        old["source_identity"][name] = prepare._sha(source)
    write_json(legacy / "run/plan.json", seal(old))
    for name in prepare.OVERLAYS:
        source = approved / "skillopt" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((package / name).read_bytes())
    shared = deepcopy(config)
    shared["version"] = "continual-eval-v2"
    shared["model"].update(max_tokens=65536, transport=deepcopy(prepare.TRANSPORT))
    common = tmp_path / "common"
    shared_plan = freeze_plan(shared, common)
    shared_plan.pop("record_hash")
    # Authored stand-in for the older common scorer: ONLY the approved overlay
    # slots may differ; API and native generation worker must remain common.
    for name in prepare.OVERLAYS:
        if name.endswith("sheet_recalc_adapter.py"):
            shared_plan["source_identity"].pop(name)
        else:
            shared_plan["source_identity"][name] = "0" * 64
    (common / "plan.json").write_text(json.dumps(seal(shared_plan)))
    service = {"provider": "BIGMODEL", "host": "open.bigmodel.cn", "path": "/api/paas/v4/chat/completions",
        "model": "glm-5.3", "reasoning_effort": "low", "proxy": prepare.PROXY, "stream": True,
        "stream_max_wall_seconds": 1800, "initial_health_policy": "completed_response_v1",
        "trust_env": False, "stream_transport": "async-whole-attempt-deadline-v1", "timeout_seconds": {"read": 300}}
    write_json(common / "model_service.json", seal(service))
    return legacy, common, approved, Path(qualified["recalculation"]["qualification_path"])


def test_whole_panel_fresh_outputs_offline_and_replay(tmp_path, monkeypatch, capsys):
    args = inputs(tmp_path, monkeypatch)
    legacy, common, approved, qpath = args
    old = legacy / "run/predictions/old-position/prediction.json"
    old.parent.mkdir(parents=True)
    old.write_text("DO_NOT_IMPORT_OLD_MODEL_WORKBOOKS")
    def forbidden(*args, **kwargs):
        pytest.fail("Preparation must not execute models, generated code or Calc")
    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", forbidden)
    monkeypatch.setattr(backends, "_native", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.sheet_recalc.Recalculator.run", forbidden)
    before = {str(p): p.read_bytes() for r in (legacy, common, approved, qpath.parent) for p in r.rglob("*") if p.is_file()}
    output = tmp_path / "new"
    value = prepare.prepare(*args, output)
    assert (value["tasks"], value["families"], value["positions"]) == (80, 80, 160)
    assert value["model_calls"] == value["container_calls"] == 0
    assert value["public_case_executions_max"] == 160 and value["recalculation_container_calls_max"] == 320
    assert value["qualification_controls"] == 17 and value["workers"] == 2
    assert not any(value[k] for k in ("old_answers_imported", "old_scores_replaced", "unknowns_filtered", "excel_equivalence_proven"))
    assert prepare.check(output) == value
    assert before == {str(p): p.read_bytes() for r in (legacy, common, approved, qpath.parent) for p in r.rglob("*") if p.is_file()}
    plan = read_json(output / "run/plan.json", sealed=True)
    runtime = plan["config"]["runtime"]["spreadsheetbench"]
    assert runtime["spreadsheet_scorer"] == prepare.SCORER
    assert {k: runtime[k] for k in ("image", "timeout_seconds", "memory_mb", "cpus")} == {
        k: value["original_generation_runtime"][k] for k in ("image", "timeout_seconds", "memory_mb", "cpus")}
    assert runtime["image"] != runtime["recalculation"]["image"]
    assert not (output / "run/predictions").exists() and not (output / "run/api").exists()
    assert prepare.main(["--check", "--output", str(output)]) == 0
    assert "DO_NOT_IMPORT" not in capsys.readouterr().out
    with pytest.raises(ValueError, match="independent"):
        prepare.prepare(*args, output)


@pytest.mark.parametrize("change", ["subset", "source", "adapter", "api", "worker", "runtime", "budget", "final", "model", "host", "service", "asset", "qualification", "q_path_source", "q_receipt"])
def test_modified_inputs_cannot_create_run(tmp_path, monkeypatch, change):
    legacy, common, approved, qpath = args = inputs(tmp_path, monkeypatch)
    if change in {"source", "adapter"}:
        path = (legacy if change == "source" else approved) / "skillopt/continual_eval/backends.py"
        path.write_text("# changed source")
    elif change == "asset":
        next((tmp_path / "authored").glob("private-reference.xlsx")).write_bytes(b"modified")
    elif change == "q_receipt":
        next((qpath.parent / "receipts").glob("*.json")).write_text("modified")
    else:
        path = common / "plan.json" if change in {"budget", "api", "worker"} else legacy / "run/plan.json"
        if change == "service":
            path = common / "model_service.json"
        elif change in {"qualification", "q_path_source"}:
            path = qpath
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        if change == "subset":
            value["tasks"] = value["tasks"][:-1]
        elif change == "runtime":
            value["config"]["runtime"]["spreadsheetbench"]["memory_mb"] = 8192
        elif change == "budget":
            value["config"]["model"]["max_tokens"] = 8192
        elif change in {"api", "worker"}:
            value["source_identity"]["validator_pilot/api.py" if change == "api" else "continual_eval/native_worker.py"] = "f" * 64
        elif change == "final":
            value["config"]["partition"] = "final"
        elif change == "model":
            value["config"]["model"]["name"] = "another-model"
        elif change == "host":
            value["host_runtime"]["python"] = "0.0.0"
        elif change == "service":
            value["stream_max_wall_seconds"] = 300
        elif change == "qualification":
            value["controls"].pop()
        else:
            value["engine"]["sources"] = {"/wrong/absolute/source.py": "0" * 64}
        path.write_text(json.dumps(seal(value)))
    output = tmp_path / "new"
    with pytest.raises(ValueError):
        prepare.prepare(*args, output)
    assert not output.exists()


def test_changed_generation_algorithm_cannot_hide_behind_resealed_old_source(tmp_path, monkeypatch):
    args = inputs(tmp_path, monkeypatch)
    source = args[0] / "skillopt/continual_eval/backends.py"
    source.write_text(source.read_text().replace('trace[-5:]', 'trace[-4:]').replace('"input.xlsx"', '"other.xlsx"'))
    path = args[0] / "run/plan.json"
    old = read_json(path, sealed=True)
    old.pop("record_hash")
    old["source_identity"]["continual_eval/backends.py"] = hashlib.sha256(source.read_bytes()).hexdigest()
    path.write_text(json.dumps(seal(old)))
    with pytest.raises(ValueError, match="generation/worker"):
        prepare.prepare(*args, tmp_path / "new")


@pytest.mark.parametrize("target", ["asset", "qualified_receipt", "approved_overlay"])
def test_check_revalidates_sources_assets_and_qualification(tmp_path, monkeypatch, target):
    args = inputs(tmp_path, monkeypatch)
    output = tmp_path / "new"
    prepare.prepare(*args, output)
    path = (tmp_path / "authored/private-reference.xlsx" if target == "asset" else
        next((args[3].parent / "receipts").glob("*.json")) if target == "qualified_receipt" else
        args[2] / "skillopt/continual_eval/sheet_recalc.py")
    path.write_text("changed")
    with pytest.raises(ValueError):
        prepare.check(output)
