"""Authored metadata fixtures; no selected real Skill, models or native grading."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import prepare_learned_checkpoint as prepare
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import (
    BENCHMARKS,
    freeze_plan,
    load_checkpoint,
    load_plan,
    output_lock,
    read_json,
    write_json,
)
from skillopt.continual_learning.contracts import manifest
from skillopt.continual_learning.ledger import Ledger
from skillopt.continual_learning.skillopt import native_sources


def inputs(tmp_path, *, benchmark="bigcodebench", branch=False, shadow=None):
    repo = Path(__file__).resolve().parents[1]
    tasks = [{"task_id": str(i), "family_id": str(i if i < 399 else 0), "project_id": "",
              "partition": "development", "public": {"prompt": f"Authored fixture {i}", "entry_point": "solve"},
              "private": {"test": "PRIVATE_FIXTURE_TEST"}} for i in range(400)]
    source_panel = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "provenance": "fixture",
                    "dataset_revision": "authored-selected-fixture-v1", "tasks": tasks}
    panel = deepcopy(source_panel)
    panel["benchmark"] = benchmark
    if benchmark == "searchqa":
        for task in panel["tasks"]:
            task["public"] = {"question": "Authored query", "context": "Authored context"}
            task["private"] = {"answers": ["PRIVATE_FIXTURE_ANSWER"]}
    panel_path = tmp_path / "data/panel.json"
    write_json(panel_path, panel)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                           "initial_health_policy": "completed_response_v1"}}
    runtime = {"bigcodebench": {}}
    config = {"version": "continual-eval-v2", "partition": "development", "order": list(BENCHMARKS),
              "panels": {b: str(panel_path) if b == benchmark else None for b in BENCHMARKS},
              "methods": ["no_skill"], "histories": ["h0"], "repeats": 2, "model": model,
              "runtime": runtime if benchmark == "bigcodebench" else {}, "project_disjoint": False, "exposure_manifest": None}
    baseline, learning = tmp_path / "baseline", tmp_path / "learning"
    freeze_plan(config, baseline)
    write_json(baseline / "model_service.json", seal({"provider": "fixture", "model": "fixture"}))
    selected_panel = {**source_panel, "tasks": tasks[:128] + tasks[-1:]}
    budget = {"max_metric_calls": 512, "max_reflection_calls": 32, "max_api_calls": 600,
              "max_reported_tokens": 2000000, "max_iterations": 2, "minibatch_size": 8,
              "solver_max_tokens": 65536, "reflection_max_tokens": 4096}
    value = manifest(selected_panel, method="skillopt" if branch else "gepa", version="continual-learning-v2",
                     train_families=[str(i) for i in range(64)], selection_families=[str(i) for i in range(64, 128)],
                     model=model, budget=budget, runtime={})
    if branch:
        value.pop("record_hash")
        value["version"] = "skillopt-frozen-evidence-reproposal-v1"
        if shadow:
            value.update(version=prepare.SHADOW_VERSION, method="shadow_" + shadow)
        value = seal(value)
    skill = "Authored selected fixture skill."
    with output_lock(learning):
        write_json(learning / "panel.json", selected_panel)
        costs = Ledger(learning, value, None).snapshot()
        if branch:
            flags = {"arm": shadow, "shadow_only": True, "research_rubric_method": False,
                     "compute_matched_baseline": False} if shadow else {}
            envelope = seal({"version": value["version"], "manifest": value, "native_sources": native_sources(),
                             "current_sources": value["source_identity"], "original_files": {}, "inherited_costs": costs,
                             **flags})
            result = {"protocol_hash": envelope["record_hash"], "new_costs": costs, "inherited_costs": costs,
                      "selected_skill": skill, "gate_action": "accept_new_best", "selection_completed": 64,
                      "selection_unknown": 0, **flags}
            if shadow:
                result.pop("selection_completed")
                result.update(selection_closed=64, selection_not_closed=0)
            write_json(learning / "protocol.json", envelope)
        else:
            envelope = seal({"manifest": value, "official_sources": {}})
            result = {"identity_hash": envelope["record_hash"], "costs": costs,
                      "official_result": {"candidates": [{"skill": ""}, {"skill": skill}], "val_aggregate_scores": [0.5, 0.75]}}
            write_json(learning / "identity.json", envelope)
        write_json(learning / "model_service.json", seal({"provider": "fixture", "model": "fixture"}))
        artifacts = {}
        if shadow:
            write_json(learning / "started.json", seal({"protocol_hash": envelope["record_hash"]}))
            artifacts = {name: prepare._sha(learning / name) for name in ("started.json", "model_service.json")}
        write_json(learning / "result.json", seal({**result, "candidate_skill": skill, "status": "completed",
                   "evidence_kind": "engineering_fixture", "artifacts": artifacts}))
    return {"learning_root": learning, "learning_source": repo, "baseline_root": baseline,
            "eval_source": repo, "output": tmp_path / "new"}


@pytest.mark.parametrize("benchmark", ["bigcodebench", "searchqa"])
@pytest.mark.parametrize("branch", [False, True])
def test_freezes_actual_selected_s1_without_calls_or_imported_s0(tmp_path, monkeypatch, benchmark, branch):
    args = inputs(tmp_path, benchmark=benchmark, branch=branch)
    before = {str(p): p.read_bytes() for root in (args["learning_root"], args["baseline_root"])
              for p in root.rglob("*") if p.is_file()}

    def forbidden(*a, **k):
        raise AssertionError("Preparation cannot infer, grade or load official pickle state")

    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.backends.score", forbidden)
    result = prepare.prepare(**args)
    assert result["positions"] == 800 and result["model_calls"] == 0 and not result["s0_executed"]
    assert result["evidence_kind"] == "engineering_fixture" and not result["baseline_receipts_imported"]
    assert prepare.check(args["output"]) == result
    root = args["output"] / "run"
    plan = load_plan(root)
    cp = load_checkpoint(root, result["method"], "h0", 1, plan)
    assert cp["skill_text"] == "Authored selected fixture skill."
    assert plan["config"]["model"] == load_plan(args["baseline_root"])["config"]["model"]
    assert not (root / "predictions").exists() and not (root / "api").exists()
    if benchmark == "searchqa":
        assert result["evaluation_mode"] == "raw_coding_skill_transfer_no_target_learning"
        assert cp["seen_benchmarks"] == ["bigcodebench"]
    assert before == {str(p): p.read_bytes() for r in (args["learning_root"], args["baseline_root"])
                      for p in r.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="independent"):
        prepare.prepare(**args)


@pytest.mark.parametrize("change", ["pending", "empty", "not_selected", "unknown_cost", "changed_artifact", "no_update"])
def test_bad_learning_never_creates_s1(tmp_path, change):
    args = inputs(tmp_path, branch=change == "no_update")
    path = args["learning_root"] / "result.json"
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    if change == "pending":
        value["status"] = "pending"
    elif change == "empty":
        value["candidate_skill"] = ""
        value["official_result"]["candidates"][1]["skill"] = ""
    elif change == "not_selected":
        value["candidate_skill"] = "unselected-other-skill"
    elif change == "unknown_cost":
        value["costs"]["usage_complete"] = False
    elif change == "changed_artifact":
        value["artifacts"]["calls/missing.json"] = "0" * 64
    else:
        value["gate_action"] = "no_update"
        value["selected_skill"] = ""
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError):
        prepare.prepare(**args)
    assert not args["output"].exists()


def test_active_writer_and_prepared_mutation_rejected(tmp_path):
    args = inputs(tmp_path)
    with output_lock(args["learning_root"]), pytest.raises(ValueError, match="active writer"):
        prepare.prepare(**args)
    prepare.prepare(**args)
    path = args["output"] / "learning_manifest.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="Frozen input"):
        prepare.check(args["output"])


def test_cli_metadata_only(tmp_path, capsys):
    args = inputs(tmp_path)
    argv = [x for k, v in args.items() for x in ("--" + k.replace("_", "-"), str(v))]
    assert prepare.main(argv) == 0
    text = capsys.readouterr().out
    assert "PRIVATE" not in text and "Authored selected" not in text
    assert prepare.main(["--check", "--output", str(args["output"])]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "validated_not_launched"


@pytest.mark.parametrize("change", ["final", "family_overlap", "different_service", "wrong_source"])
def test_invalid_source_or_boundary_fails_before_output(tmp_path, change):
    args = inputs(tmp_path)
    if change == "final":
        path = args["baseline_root"] / "plan.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        value["config"]["partition"] = "final"
        path.write_text(json.dumps(seal(value)))
    elif change == "family_overlap":
        path = args["learning_root"] / "identity.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        value["manifest"].pop("record_hash")
        value["manifest"]["selection_families"].append("0")
        value["manifest"] = seal(value["manifest"])
        value = seal(value)
        path.write_text(json.dumps(value))
        result_path = args["learning_root"] / "result.json"
        result = read_json(result_path, sealed=True)
        result.pop("record_hash")
        result["identity_hash"] = value["record_hash"]
        result_path.write_text(json.dumps(seal(result)))
    elif change == "different_service":
        (args["learning_root"] / "model_service.json").write_text(json.dumps(seal({"provider": "fixture", "model": "other"})))
    else:
        args["learning_source"] = tmp_path / "not-the-frozen-source"
    with pytest.raises((ValueError, FileNotFoundError)):
        prepare.prepare(**args)
    assert not args["output"].exists()


@pytest.mark.parametrize("arm", ["generic_summary", "conditional_mechanism"])
@pytest.mark.parametrize("benchmark", ["bigcodebench", "searchqa"])
def test_shadow_selected_skill_keeps_explicit_non_main_method_labels(tmp_path, arm, benchmark):
    args = inputs(tmp_path, benchmark=benchmark, branch=True, shadow=arm)
    value = prepare.prepare(**args)
    assert value["method"] == "shadow_" + arm and value["shadow_only"]
    assert not value["research_rubric_method"] and not value["compute_matched_baseline"]
    assert value["learning_protocol"] == prepare.SHADOW_VERSION and value["model_calls"] == 0
    assert prepare.check(args["output"]) == value


@pytest.mark.parametrize("change", ["reject", "pending", "unknown", "incomplete", "wrong_arm", "wrong_method", "claim_main_method", "source_changed"])
def test_shadow_cannot_bypass_selection_or_provenance(tmp_path, change):
    args = inputs(tmp_path, branch=True, shadow="generic_summary")
    path = args["learning_root"] / "result.json"
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    if change == "reject":
        value.update(gate_action="reject", selected_skill="")
    elif change == "pending":
        value["status"] = "pending"
    elif change == "unknown":
        value["selection_unknown"] = 1
    elif change == "incomplete":
        value["selection_closed"] = 63
        value["selection_not_closed"] = 1
    elif change == "wrong_arm":
        value["arm"] = "conditional_mechanism"
    elif change == "wrong_method":
        protocol_path = args["learning_root"] / "protocol.json"
        protocol = read_json(protocol_path, sealed=True)
        protocol.pop("record_hash")
        protocol["manifest"].pop("record_hash")
        protocol["manifest"]["method"] = "shadow_conditional_mechanism"
        protocol["manifest"] = seal(protocol["manifest"])
        protocol = seal(protocol)
        protocol_path.write_text(json.dumps(protocol))
        value["protocol_hash"] = protocol["record_hash"]
        started_path = args["learning_root"] / "started.json"
        started_path.write_text(json.dumps(seal({"protocol_hash": protocol["record_hash"]})))
        value["artifacts"]["started.json"] = prepare._sha(started_path)
    elif change == "claim_main_method":
        value["research_rubric_method"] = True
    else:
        args["learning_source"] = tmp_path / "wrong-frozen-source"
    path.write_text(json.dumps(seal(value)))
    with pytest.raises((ValueError, FileNotFoundError)):
        prepare.prepare(**args)
    assert not args["output"].exists()
