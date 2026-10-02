"""Paired-report fixtures: authored tasks/results, no model or native execution."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import compare_baseline_checkpoints as pairing
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import (
    BENCHMARKS,
    freeze_plan,
    output_lock,
    read_json,
    register_checkpoint,
    write_json,
)
from skillopt.continual_eval.runner import generate, score_checkpoint
from skillopt.continual_learning.contracts import manifest


def setup(tmp_path, *, run=True, family_overlap=False):
    tasks = [{"task_id": str(i), "family_id": str(0 if family_overlap and i == 5 else i), "project_id": "", "partition": "development",
              "public": {"prompt": str(i), "entry_point": "solve"}, "private": {"test": "PRIVATE_TEST_CANARY"}}
             for i in range(6)]
    panel = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "provenance": "fixture",
             "dataset_revision": "paired-fixture-v1", "tasks": tasks}
    path = tmp_path / "data/panel.json"
    write_json(path, panel)
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                           "initial_health_policy": "completed_response_v1"}}
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
              "panels": {b: str(path) if b == "bigcodebench" else None for b in BENCHMARKS},
              "histories": ["h0"], "repeats": 2, "model": model, "runtime": {},
              "project_disjoint": False, "exposure_manifest": None}
    roots = [tmp_path / "baseline", tmp_path / "candidate"]
    for root, method in zip(roots, ("no_skill", "skillopt")):
        freeze_plan({**deepcopy(config), "methods": ["no_skill"] if method == "no_skill" else ["no_skill", method]}, root)
        stage = int(method != "no_skill")
        if stage:
            register_checkpoint(root, method, "h0", stage, "Authored fixture skill.", provenance="fixture_only")
        write_json(root / "model_service.json", seal({"provider": "fixture", "model": "fixture"}))
        if run:
            generate(root, method=method, history="h0", stage=stage, benchmark="bigcodebench",
                     fixture_solve=lambda *a, **k: {"status": "available", "output": "PRIVATE_ANSWER_CANARY",
                                                    "reason": "fixture"})
            statuses = ("fail", "pass", "pass", "unknown", "fail", "pass") if stage == 0 \
                else ("pass", "fail", "pass", "unknown", "fail", "pass")

            def score(benchmark, public, private, prediction, *, runtime):
                status = statuses[int(public["prompt"])]
                return {"status": status, "score": None if status == "unknown" else float(status == "pass"),
                        "metrics": {}, "reason": "native_timeout" if status == "unknown" else "fixture"}

            score_checkpoint(root, method=method, history="h0", stage=stage, benchmark="bigcodebench", fixture_score=score)
    learning = tmp_path / "learning"
    budget = {"max_metric_calls": 512, "max_reflection_calls": 32, "max_api_calls": 600,
              "max_reported_tokens": 2000000, "max_iterations": 2, "minibatch_size": 8,
              "solver_max_tokens": 65536, "reflection_max_tokens": 4096}
    value = manifest({**panel, "tasks": tasks[:4]}, method="skillopt", version="continual-learning-v2",
                     train_families=["0", "1"], selection_families=["2", "3"], model=model, budget=budget)
    identity = seal({"manifest": value})
    with output_lock(learning):
        write_json(learning / "manifest.json", value)
        write_json(learning / "identity.json", identity)
        write_json(learning / "result.json", seal({"identity_hash": identity["record_hash"], "status": "completed",
            "candidate_skill": "Authored fixture skill.", "artifacts": {},
            "costs": {"logical_calls": 0, "usage_complete": True}}))
    repo = Path(__file__).resolve().parents[1]
    return {"baseline_root": roots[0], "candidate_root": roots[1], "baseline_source": repo,
            "candidate_source": repo, "learning_manifest": learning / "manifest.json",
            "learning_result": learning / "result.json", "method": "skillopt",
            "fixture_group_counts": dict(zip(pairing.GROUPS, (2, 2, 2)))}


def reseal(path, update):
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    update(value)
    path.write_text(json.dumps(seal(value)))


def test_real_schema_pairing_is_read_only_preserves_unknown_and_strata(tmp_path, monkeypatch):
    args = setup(tmp_path)
    original = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    real_read = pairing.read_json

    def metadata_only(path, **kwargs):
        assert path.name != "panel.json", "Must not inspect hidden task/answer data"
        return real_read(path, **kwargs)

    monkeypatch.setattr(pairing, "read_json", metadata_only)
    result = pairing.compare(**args)
    assert result["status"] == "completed"
    assert result["version"] == "cross-run-coding-paired-report-v2"
    assert result["overall"]["pair_counts"] == {"win": 2, "loss": 2, "tie": 6, "unknown": 2, "missing": 0}
    assert result["overall"]["tasks"] == result["overall"]["families"] == 6
    assert result["overall"]["positions"] == 12 and result["overall"]["paired_known_denominator"] == 10
    uncertainty = result["overall"]["uncertainty"]
    assert uncertainty["known_pair_denominator"] == 10 and uncertainty["known_cluster_count"] == 5
    assert uncertainty["excluded_unknown_pairs"] == 2 and uncertainty["mean_paired_delta_known"] == 0
    assert uncertainty["full_roster_completion_bounds"]["lower"] == pytest.approx(-1 / 6)
    assert uncertainty["full_roster_completion_bounds"]["upper"] == pytest.approx(1 / 6)
    assert result["groups"]["selection"]["pair_counts"]["unknown"] == 2
    assert result["groups"]["selection"]["uncertainty"]["status"] == "pending"
    assert result["groups"]["not_used_by_this_learning"]["tasks"] == 2
    assert not any(result["family_overlap_counts"].values())
    assert result["new_model_calls"] == 0 and not result["independent_final_evidence"]
    assert "PRIVATE_TEST_CANARY" not in json.dumps(result) and "PRIVATE_ANSWER_CANARY" not in json.dumps(result)
    assert original == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert pairing.compare(**args) == result


def test_missing_is_not_semantic_failure_and_no_s1_is_fabricated(tmp_path):
    args = setup(tmp_path, run=False)
    result = pairing.compare(**args)
    assert result["status"] == "pending" and result["overall"]["pair_counts"]["missing"] == 12
    assert result["overall"]["paired_known_denominator"] == 0
    (args["candidate_root"] / "checkpoints/skillopt/h0/s1.json").unlink()
    with pytest.raises(FileNotFoundError):
        pairing.compare(**args)


@pytest.mark.parametrize("change", ["model", "runtime", "source", "panel", "final", "repeat", "history", "learning", "empty"])
def test_noncomparable_or_unbound_inputs_rejected(tmp_path, change):
    args = setup(tmp_path)
    root = args["candidate_root"]
    if change in {"learning", "empty"}:
        reseal(args["learning_result"], lambda v: v.update(candidate_skill="other" if change == "learning" else ""))
    else:
        def mutate(value):
            if change == "model":
                value["config"]["model"]["max_tokens"] = 32768
            elif change == "runtime":
                value["config"]["runtime"] = {"bigcodebench": {"timeout_seconds": 30}}
            elif change == "source":
                value["source_identity"]["continual_eval/backends.py"] = "0" * 64
            elif change == "panel":
                value["panels"]["bigcodebench"]["panel_hash"] = "0" * 64
            elif change == "final":
                value["config"]["partition"] = "final"
            elif change == "repeat":
                value["repeats"] = value["config"]["repeats"] = 3
            elif change == "history":
                value["config"]["histories"] = ["other"]
        reseal(root / "plan.json", mutate)
    with pytest.raises(ValueError):
        pairing.compare(**args)


def test_score_binding_and_active_writer_guard(tmp_path):
    args = setup(tmp_path)
    with output_lock(args["candidate_root"]), pytest.raises(ValueError, match="still being written"):
        pairing.compare(**args)
    score = next((args["candidate_root"] / "host_only/scores").glob("*.json"))
    reseal(score, lambda v: v.update(prediction_hash="0" * 64))
    with pytest.raises(ValueError, match="Score/prediction"):
        pairing.compare(**args)


def test_cli_cannot_write_under_protected_evidence(tmp_path):
    args = setup(tmp_path)
    args.pop("fixture_group_counts")
    argv = [item for key, value in args.items() for item in ("--" + key.replace("_", "-"), str(value))]
    with pytest.raises(ValueError, match="outside source/evidence"):
        pairing.main([*argv, "--output", str(args["candidate_root"] / "report.json")])
    assert not (args["candidate_root"] / "report.json").exists()


def test_task_not_used_does_not_imply_unseen_family(tmp_path):
    result = pairing.compare(**setup(tmp_path, family_overlap=True))
    assert result["family_overlap_counts"]["train__not_used_by_this_learning"] == 1
    assert result["groups"]["not_used_by_this_learning"]["tasks"] == 2
    assert not result["independent_final_evidence"]


def test_actual_service_and_intent_identity_checked(tmp_path):
    args = setup(tmp_path)
    service = args["candidate_root"] / "model_service.json"
    reseal(service, lambda v: v.update(transport="other"))
    with pytest.raises(ValueError, match="service differs"):
        pairing.compare(**args)


def test_unclosed_call_cost_does_not_become_zero(tmp_path):
    args = setup(tmp_path, run=False)
    plan = read_json(args["baseline_root"] / "plan.json", sealed=True)
    checkpoint = pairing.load_checkpoint(args["baseline_root"], "no_skill", "h0", 0, plan)
    request = {"plan_hash": plan["record_hash"], "checkpoint_hash": checkpoint["record_hash"],
               "benchmark": "bigcodebench", "task_hash": plan["tasks"][0]["task_hash"], "repeat": 0}
    base = args["baseline_root"] / "predictions" / pairing.digest(request)
    write_json(base / "call_intents/unclosed.json", seal({"fixture_intent": True}))
    result = pairing.compare(**args)
    assert result["costs"]["baseline"]["unclosed_calls"] == 1
    assert result["costs"]["baseline"]["reported_tokens"] is None
    assert result["costs"]["baseline"]["http_attempts"] is None


@pytest.mark.parametrize("corruption", ["service", "tokens"])
def test_nested_solver_receipt_cost_and_actual_service_are_bound(tmp_path, corruption):
    args = setup(tmp_path)
    root = args["baseline_root"]
    score_path = next((root / "host_only/scores").glob("*.json"))
    base = root / "predictions" / score_path.stem
    prediction = read_json(base / "prediction.json", sealed=True)
    service = read_json(root / "model_service.json", sealed=True)
    service.pop("record_hash")
    outer = {"position": prediction["request"], "turn": 0, "system": "fixture system",
             "user": "fixture public task", "max_tokens": 65536}
    key = pairing.digest(outer)
    inner = {"model": "fixture", "system": outer["system"], "user": outer["user"],
             "kind": "continual-eval-solver", "key": key, "max_tokens": 65536,
             "repeat": prediction["request"]["repeat"], "service": service}
    receipt = {"request": inner, "request_hash": pairing.digest(inner), "ok": True,
               "response": "PRIVATE_ANSWER_CANARY", "finish_reason": "stop", "http_attempt_count": 1,
               "usage": {"prompt_tokens": 3, "completion_tokens": 4}}
    write_json(base / "call_intents" / (key + ".json"), seal(outer))
    call_path = base / "calls" / (key + ".json")
    write_json(call_path, seal({"request": outer, "receipt": receipt}))
    costs = pairing._costs([receipt])
    reseal(base / "prediction.json", lambda v: v.update(costs=costs))
    prediction = read_json(base / "prediction.json", sealed=True)
    reseal(score_path, lambda v: v.update(costs=costs, prediction_hash=prediction["record_hash"]))
    reseal(root / "host_only/score_intents" / score_path.name,
           lambda v: v.update(prediction_hash=prediction["record_hash"]))
    result = pairing.compare(**args)
    assert result["costs"]["baseline"]["reported_tokens"] == 7
    assert result["costs"]["baseline"]["logical_calls"] == 1
    assert "PRIVATE_ANSWER_CANARY" not in json.dumps(result)

    def different_service(row):
        row["receipt"]["request"]["service"]["transport"] = "other"
        row["receipt"]["request_hash"] = pairing.digest(row["receipt"]["request"])

    if corruption == "service":
        reseal(call_path, different_service)
    else:
        row = read_json(call_path, sealed=True)
        row.pop("record_hash")
        row["request"]["max_tokens"] = 32768
        new_key = pairing.digest(row["request"])
        row["receipt"]["request"].update(max_tokens=32768, key=new_key)
        row["receipt"]["request_hash"] = pairing.digest(row["receipt"]["request"])
        call_path.unlink()
        (base / "call_intents" / (key + ".json")).unlink()
        write_json(base / "calls" / (new_key + ".json"), seal(row))
        write_json(base / "call_intents" / (new_key + ".json"), seal(row["request"]))
    with pytest.raises(ValueError, match="service binding or token budget"):
        pairing.compare(**args)


def uncertainty_row(family, left, right, repeat=0):
    def side(value):
        if value in (0, 1):
            return {"status": "pass" if value else "fail", "score": float(value)}
        return {"status": value, "score": None}
    comparison = ("missing" if "missing" in (left, right) else "unknown" if "unknown" in (left, right)
                  else "win" if right > left else "loss" if right < left else "tie")
    return {"family_hash": family, "task_hash": family + str(repeat), "repeat": repeat,
            "baseline": side(left), "candidate": side(right), "comparison": comparison}


def test_uncertainty_is_deterministic_and_row_order_invariant():
    rows = [uncertainty_row("b", 1, 0), uncertainty_row("a", 0, 1),
            uncertainty_row("c", 1, 1), uncertainty_row("d", 0, "unknown")]
    result = pairing._paired_uncertainty(rows)
    assert result == pairing._paired_uncertainty(rows)
    assert result == pairing._paired_uncertainty(list(reversed(rows)))
    assert result["bootstrap"]["seed"] == 20261001
    assert result["bootstrap"]["resamples"] == result["bootstrap"]["resamples_executed"] == 10000
    assert result["known_pair_denominator"] == result["known_cluster_count"] == 3
    assert result["excluded_unknown_pairs"] == 1 and result["excluded_missing_pairs"] == 0
    assert result["mean_paired_delta_known"] == 0
    assert not result["bootstrap"]["zero_width_sampling_degeneracy"]
    assert not result["deployment_evidence"]


def test_repeats_stay_in_one_cluster_and_do_not_narrow_interval():
    rows = [uncertainty_row("a", 0, 1), uncertainty_row("b", 1, 0)]
    repeated = [dict(row, repeat=repeat) for row in rows for repeat in range(20)]
    single = pairing._paired_uncertainty(rows)
    result = pairing._paired_uncertainty(repeated)
    assert result["known_cluster_count"] == 2 and result["known_pair_denominator"] == 40
    assert result["bootstrap"]["interval"] == single["bootstrap"]["interval"] == {"lower": -1, "upper": 1}
    assert result["mean_paired_delta_known"] == single["mean_paired_delta_known"] == 0


def test_position_weighted_mean_not_mean_of_unequal_family_means():
    rows = [uncertainty_row("a", 0, 1, repeat) for repeat in range(10)] + [uncertainty_row("b", 1, 0)]
    result = pairing._paired_uncertainty(rows)
    assert result["known_cluster_count"] == 2 and result["known_pair_denominator"] == 11
    assert result["mean_paired_delta_known"] == pytest.approx(9 / 11)
    assert result["full_roster_completion_bounds"]["lower"] == pytest.approx(9 / 11)
    assert result["full_roster_completion_bounds"]["upper"] == pytest.approx(9 / 11)


@pytest.mark.parametrize("right,expected", [(0, 0), (1, 1)])
def test_zero_change_and_all_win_have_expected_degenerate_descriptive_interval(right, expected):
    rows = [uncertainty_row(str(i), 0, right) for i in range(4)]
    result = pairing._paired_uncertainty(rows)
    assert result["status"] == "descriptive_available"
    assert result["mean_paired_delta_known"] == expected
    assert result["bootstrap"]["interval"] == {"lower": expected, "upper": expected}
    assert result["bootstrap"]["zero_width_sampling_degeneracy"]
    assert "does not establish certainty" in result["bootstrap"]["degeneracy_note"]


@pytest.mark.parametrize("rows,known,clusters,mean", [
    ([], 0, 0, None),
    ([uncertainty_row("a", "unknown", "unknown"), uncertainty_row("b", "missing", "unknown")], 0, 0, None),
    ([uncertainty_row("a", 0, 1, repeat) for repeat in range(20)], 20, 1, 1),
])
def test_fewer_than_two_known_clusters_is_pending(rows, known, clusters, mean):
    result = pairing._paired_uncertainty(rows)
    assert result["status"] == "pending" and result["bootstrap"]["interval"] is None
    assert result["bootstrap"]["resamples_executed"] == 0
    assert result["known_pair_denominator"] == known and result["known_cluster_count"] == clusters
    assert result["mean_paired_delta_known"] == mean
    if not rows:
        assert result["full_roster_completion_bounds"]["lower"] is None
    elif not known:
        assert result["full_roster_completion_bounds"]["lower"] == -1
        assert result["full_roster_completion_bounds"]["upper"] == 1


def test_unknown_and_missing_never_enter_known_denominator_as_zero():
    rows = [uncertainty_row("a", 0, 1), uncertainty_row("b", 0, 1),
            uncertainty_row("c", 1, "unknown"), uncertainty_row("d", "missing", 0)]
    summary = pairing._summary(rows)
    result = summary["uncertainty"]
    assert summary["paired_known_denominator"] == result["known_pair_denominator"] == 2
    assert summary["positions"] == result["full_roster_completion_bounds"]["positions"] == 4
    assert result["mean_paired_delta_known"] == 1  # Not 2/4 from silently filling two zeros.
    assert result["excluded_unknown_pairs"] == result["excluded_missing_pairs"] == 1
    assert result["bootstrap"]["interval"] == {"lower": 1, "upper": 1}
    assert result["full_roster_completion_bounds"]["lower"] == 0
    assert result["full_roster_completion_bounds"]["upper"] == 0.5
    assert result["full_roster_completion_bounds"]["unresolved_pairs"] == 2
