"""Offline v3 controls: native optimizers with explicit benchmark adaptation."""
import importlib.util
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_eval.datasets import file_hash
from skillopt.continual_learning.contracts import (
    LONG_RESPONSE_VERSION,
    MULTI_BENCHMARK_VERSION,
    manifest,
    validate_manifest,
)
from skillopt.continual_learning.feedback import artifacts, project
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.gepa import run_stage as run_gepa_stage
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.skillopt import propose_native, run_stage
from skillopt.validator_pilot.api import digest

BENCHMARKS = ("bigcodebench", "searchqa", "korbench", "spreadsheetbench", "alfworld")
PRIVATE_CANARY = "PRIVATE_GOLD_CANARY_DO_NOT_REFLECT"


def setup(benchmark="searchqa", *, method="skillopt", parent="", natural=False, runtime=None):
    public = {
        "bigcodebench": {"prompt": "Return one.", "entry_point": "f"},
        "searchqa": {"question": "What is the capital?", "context": ["The capital is Paris."]},
        "korbench": {"rule": "Reply ONE.", "question": "What is the reply?"},
        "spreadsheetbench": {"instruction": "Set A1 to one.", "input_files": ["public.xlsx"], "answer_position": "Sheet1!A1"},
        "alfworld": {"game_file": "public-game.tw-pddl"},
    }[benchmark]
    private = {
        "bigcodebench": {"test": PRIVATE_CANARY},
        "searchqa": {"answers": ["Paris", PRIVATE_CANARY]},
        "korbench": {"answer": PRIVATE_CANARY, "category": "logic", "rule_id": "0", "upstream_index": "0"},
        "spreadsheetbench": {"test_files": ["private.xlsx"], "answer_position": "Sheet1!A1"},
        "alfworld": {"game_metadata": {"expert": PRIVATE_CANARY}},
    }[benchmark]
    panel = {"version": "continual-panel-v1", "benchmark": benchmark,
             "dataset_revision": "fixture-domain-v1", "provenance": "natural" if natural else "fixture",
             "tasks": [{"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
                        "public": deepcopy(public), "private": deepcopy(private)} for i in range(4)]}
    model = {"provider": "bigmodel" if natural else "fixture", "name": "glm-5.3" if natural else "fixture",
             "max_tokens": 100, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                           "initial_health_policy": "completed_response_v1"}}
    budget = {"max_metric_calls": 24, "max_reflection_calls": 10, "max_api_calls": 30,
              "max_reported_tokens": 100000, "max_iterations": 1, "minibatch_size": 2,
              "solver_max_tokens": 100, "reflection_max_tokens": 100}
    args = {"train_families": ["0", "1"], "selection_families": ["2", "3"], "model": model,
            "budget": budget, "method": method, "parent_skill": parent,
            "runtime": runtime or {}, "version": MULTI_BENCHMARK_VERSION}
    return manifest(panel, **args), panel, args


class API:
    service = {"fixture": "offline-domain-controls"}

    def __init__(self, model="fixture", *, no_update=False):
        self.model, self.calls, self.no_update = model, [], no_update

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        assert PRIVATE_CANARY not in system + user
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.calls.append(request)
        if kind.endswith("solver"):
            response = "<answer>Paris</answer>" if "requested constant" in system else "<answer>wrong</answer>"
        else:
            edits = [] if self.no_update else [{"op": "append", "content": "Use the requested constant result."}]
            response = json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": edits}})
        return {"request": request, "request_hash": digest(request), "response": response,
                "ok": True, "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 20},
                "http_attempt_count": 1}

    def close(self):
        pass


def evaluate(benchmark):
    def execute(task, skill):
        correct = "requested constant" in skill
        output = "one" if correct else "zero"
        extra = {}
        if benchmark == "spreadsheetbench":
            output = {"code": output, "cases": [{"status": "available", "output_base64": PRIVATE_CANARY}]}
        if benchmark == "alfworld":
            output = {"won": correct, "steps": 1}
            extra["trace"] = [{"observation": "Put the mug in the cupboard.", "action": "go to cupboard 1",
                               "post_observation": "You arrive.", "post_observation_status": "complete",
                               "expert_plan": PRIVATE_CANARY}]
        return ({"status": "available", "output": output, "reason": "fixture", **extra},
                {"status": "pass" if correct else "fail", "score": float(correct), "reason": "fixture",
                 "metrics": {"private_detail": PRIVATE_CANARY}})
    return execute


@pytest.mark.parametrize("benchmark", BENCHMARKS)
def test_v3_manifest_explicit_domain_and_roundtrip(benchmark):
    auth, panel, _ = setup(benchmark)
    assert validate_manifest(auth, panel) == auth
    assert auth["benchmark"] == benchmark
    assert auth["algorithm_implementation"] == "repository_native_skillopt"
    assert auth["baseline_scope"] == "native_algorithm_with_benchmark_feedback_adaptation"
    assert auth["feedback_profile"] == "benchmark-public-feedback-v1"


@pytest.mark.parametrize("benchmark", BENCHMARKS[1:])
def test_v1_v2_still_coding_only(benchmark):
    _, panel, args = setup(benchmark)
    args["version"] = LONG_RESPONSE_VERSION
    with pytest.raises(ValueError, match="Coding"):
        manifest(panel, **args)
    args.pop("version")
    args["model"].pop("transport")
    with pytest.raises(ValueError, match="Coding"):
        manifest(panel, **args)


def test_v2_schema_does_not_gain_v3_fields():
    _, panel, args = setup("bigcodebench")
    auth = manifest(panel, **{**args, "version": LONG_RESPONSE_VERSION})
    assert not {"benchmark", "feedback_profile", "asset_identity", "baseline_scope"} & set(auth)
    assert validate_manifest(auth, panel) == auth


@pytest.mark.parametrize("benchmark", BENCHMARKS)
def test_real_native_skillopt_adapter_gate_and_replay_all_domains(tmp_path, benchmark):
    auth, panel, _ = setup(benchmark)
    api = API()
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate(benchmark))
    assert result["status"] == "completed", result
    assert result["initial_selection_score"] == 0 and result["selected_score"] == 1
    assert result["steps"][0]["gate_action"] == "accept_new_best"
    assert len(api.calls) == 1  # Real native reflect -> patch; scorer is the fixture.
    replay = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate(benchmark))
    assert replay == result and len(api.calls) == 1


def test_searchqa_native_solver_scorer_and_optimizer_without_evaluation_callback(tmp_path, monkeypatch):
    """Real SearchQA and SkillOpt routing, offline provider; NOT a natural run."""
    auth, panel, _ = setup(natural=True)
    api = API(model="glm-5.3")
    monkeypatch.setattr("skillopt.continual_learning.skillopt.CachedAPI", lambda *a, **k: api)
    result = run_stage(auth, panel, tmp_path, repo=tmp_path)
    assert result["status"] == "completed", result
    assert result["initial_selection_score"] == 0 and result["selected_score"] == 1
    assert result["costs"]["solver_calls"] == 6 and result["costs"]["reflection_calls"] == 1
    rows = [read_json(path, sealed=True) for path in (tmp_path / "evaluations").glob("*.json")]
    assert len(rows) == 6
    assert {row["score"]["reason"] for row in rows} == {"repository_searchqa_native_em"}


@pytest.mark.parametrize("benchmark", BENCHMARKS[1:])
def test_unchanged_empty_parent_is_completed_and_allows_next_domain(tmp_path, benchmark):
    auth, panel, _ = setup(benchmark)
    result = run_stage(auth, panel, tmp_path / "first", fixture_api=API(no_update=True),
                       fixture_evaluate=evaluate(benchmark))
    assert result["status"] == "completed" and result["candidate_skill"] == ""
    next_auth, next_panel, _ = setup("searchqa", parent=result["candidate_skill"])
    next_result = run_stage(next_auth, next_panel, tmp_path / "next", fixture_api=API(),
                            fixture_evaluate=evaluate("searchqa"))
    assert next_result["status"] == "completed" and next_result["candidate_skill"]


@pytest.mark.parametrize("benchmark", BENCHMARKS[1:])
def test_scalar_unknown_cannot_become_reflection_failure(tmp_path, benchmark):
    auth, panel, _ = setup(benchmark)
    api = API()
    def unknown(task, skill):
        prediction, score = evaluate(benchmark)(task, skill)
        return prediction, {**score, "status": "unknown", "score": None}
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=unknown)
    assert result["status"] == "pending" and result["candidate_skill"] == ""
    assert result["costs"]["logical_calls"] == 0 and not api.calls


def test_alf_identical_prompts_on_different_turns_are_distinct_paid_intents(tmp_path, monkeypatch):
    auth, panel, _ = setup("alfworld", method="gepa")
    api = API()
    ledger = Ledger(tmp_path, auth, api)
    def solve(benchmark, public, skill, call, *, runtime):
        assert benchmark == "alfworld"
        call("same system", "same observation")
        call("same system", "same observation")
        return evaluate("alfworld")(panel["tasks"][0], skill)[0]
    monkeypatch.setattr(backends, "solve", solve)
    adapter = Adapter(auth, tmp_path, ledger)
    item = {"role": "train", "task": panel["tasks"][0]}
    result = adapter.evaluate_rows([item], {"skill": ""})
    assert len(api.calls) == 2 and api.calls[0]["key"] != api.calls[1]["key"]
    assert ledger.snapshot()["solver_calls"] == 2
    assert adapter.evaluate_rows([item], {"skill": ""}) == result and len(api.calls) == 2
    assert "won" not in result[0]["trajectory"]["Generated Outputs"]
    assert PRIVATE_CANARY not in json.dumps(result)


def test_alf_projection_is_bounded_explicit_and_preserves_public_fail_transition():
    auth, panel, _ = setup("alfworld")
    prediction, score = evaluate("alfworld")(panel["tasks"][0], "")
    prediction["trace"] *= 150
    for row in prediction["trace"]:
        row["observation"] = "x" * 12000
        row["post_observation"] = "Nothing happens. " * 1000
    trace = project(auth, panel["tasks"][0]["public"], prediction, score)
    output = json.loads(trace["Generated Outputs"])
    assert output["omitted_steps"] == 144 and len(output["public_steps"]) == 6
    assert output["public_steps"][-1]["step"] == 149
    assert all(row["post_observation_projection_truncated"] for row in output["public_steps"])
    assert len(json.dumps(trace)) < 40000


@pytest.mark.parametrize("benchmark", ["searchqa", "spreadsheetbench", "alfworld"])
def test_feedback_projection_tamper_rejected_before_native_calls(tmp_path, benchmark):
    auth, panel, _ = setup(benchmark)
    api = API()
    ledger = Ledger(tmp_path, auth, api)
    write_json(tmp_path / "panel.json", panel)
    row = Adapter(auth, tmp_path, ledger, fixture_evaluate=evaluate(benchmark)).evaluate_rows(
        [{"role": "train", "task": panel["tasks"][0]}], {"skill": ""})[0]
    trace = {**row["trajectory"], "evidence_hash": row["output"]["evidence_hash"]}
    trace["Generated Outputs"] += " fabricated"
    with pytest.raises(ValueError, match="projection"):
        propose_native("", [trace], tmp_path / "proposal", ledger)
    assert not api.calls


def test_projection_rejects_fractional_hard_feedback():
    auth, panel, _ = setup()
    prediction, score = evaluate("searchqa")(panel["tasks"][0], "")
    with pytest.raises(ValueError, match="hard feedback"):
        project(auth, panel["tasks"][0]["public"], prediction, {**score, "score": 0.5})


def test_natural_asset_identity_freezes_and_rechecks_each_evaluation(tmp_path):
    _, panel, args = setup("alfworld")
    asset = tmp_path / "game.tw-pddl"
    asset.write_text("fixture original asset")
    panel["provenance"] = "natural"
    for task in panel["tasks"]:
        task["public"]["game_file"] = str(asset)
        task["private"]["asset_sha256"] = {str(asset): file_hash(asset)}
    args["model"].update(provider="bigmodel", name="glm-5.3")
    auth = manifest(panel, **args)
    assert auth["asset_identity"][str(asset)]["status"] == "ready"
    asset.write_text("changed")
    adapter = Adapter(auth, tmp_path / "learning", Ledger(tmp_path / "learning", auth, API()))
    with pytest.raises(ValueError, match="asset changed"):
        adapter.evaluate_rows([{"role": "train", "task": panel["tasks"][0]}], {"skill": ""})
    with pytest.raises(ValueError, match="assets"):
        validate_manifest(auth, panel)


def test_sheet_host_only_context_and_artifacts_bind_recalc_prediction(tmp_path, monkeypatch):
    auth, panel, _ = setup("spreadsheetbench")
    auth.pop("record_hash")
    auth = seal({**auth, "runtime": {"spreadsheet_scorer": "qualified_lo_recalc_v5_v1"}})
    ledger = Ledger(tmp_path, auth, API())
    seen = []
    def solve(benchmark, public, skill, call, *, runtime):
        assert benchmark == "spreadsheetbench" and "/host_only/workspaces/" in runtime["work_dir"]
        return evaluate(benchmark)(panel["tasks"][0], skill)[0]
    def score(benchmark, public, private, prediction, *, runtime):
        context = runtime["_score_context"]
        assert benchmark == context["request"]["benchmark"] == "spreadsheetbench"
        assert context["position"] == digest(context["request"])
        record = read_json(tmp_path / "host_only/scorer_artifacts" / context["position"] / "prediction.json", sealed=True)
        assert record["record_hash"] == context["prediction_hash"] and record["prediction"] == prediction
        seen.append(context)
        return evaluate(benchmark)(panel["tasks"][0], "")[1]
    monkeypatch.setattr(backends, "solve", solve)
    monkeypatch.setattr(backends, "score", score)
    Adapter(auth, tmp_path, ledger).evaluate_rows([{"role": "train", "task": panel["tasks"][0]}], {"skill": ""})
    assert len(seen) == 1
    assert any(name.startswith("host_only/scorer_artifacts/") for name in artifacts(ledger))


def test_alf_without_trace_remains_unavailable_to_reflection():
    auth, panel, _ = setup("alfworld")
    prediction, score = evaluate("alfworld")(panel["tasks"][0], "")
    prediction.pop("trace")
    with pytest.raises(ValueError, match="interaction evidence"):
        project(auth, panel["tasks"][0]["public"], prediction, score)


def test_unknown_projection_is_pending_not_numeric_zero():
    auth, panel, _ = setup()
    with pytest.raises(LearningPending):
        project(auth, panel["tasks"][0]["public"], {"output": None}, {"status": "unknown", "score": None})


def test_unavailable_public_projection_latches_adapter_pending(tmp_path):
    auth, panel, _ = setup("alfworld", method="gepa")
    calls = []
    def missing_trace(task, skill):
        calls.append(task["task_id"])
        prediction, score = evaluate("alfworld")(task, skill)
        prediction.pop("trace")
        return prediction, score
    adapter = Adapter(auth, tmp_path, Ledger(tmp_path, auth, API()), fixture_evaluate=missing_trace)
    item = {"role": "train", "task": panel["tasks"][0]}
    for _ in range(2):
        with pytest.raises(LearningPending, match="projection_unavailable"):
            adapter.evaluate_rows([item], {"skill": ""})
    assert len(calls) == 1


@pytest.fixture
def official_source():
    root = Path(__file__).resolve().parents[1]
    source = Path(os.environ.get("GEPA_OFFICIAL_SOURCE", root / "outputs/continual_eval/baseline_preparation_20260928/gepa"))
    if not source.is_dir() or importlib.util.find_spec("gepa") is None:
        pytest.skip("Run official GEPA controls in the pinned baseline preparation environment")
    return source


class GEPAAPI(API):
    def call(self, system, user, kind, key, **kwargs):
        result = super().call(system, user, kind, key, **kwargs)
        if kind.endswith("reflection"):
            result["response"] = "```\nUse the requested constant result.\n```"
        return result


@pytest.mark.parametrize("benchmark", BENCHMARKS)
def test_official_gepa_v3_all_domain_adapters(tmp_path, benchmark, official_source):
    _, panel, args = setup(benchmark, method="gepa")
    args["budget"]["max_iterations"] = 2
    auth = manifest(panel, **args)
    api = GEPAAPI()
    result = run_gepa_stage(auth, panel, tmp_path, gepa_source=official_source,
                            fixture_api=api, fixture_evaluate=evaluate(benchmark))
    assert result["status"] == "completed", result
    assert result["candidate_skill"] == "Use the requested constant result."
    assert result["official_result"]["val_aggregate_scores"][:2] == [0.0, 1.0]
    assert len(api.calls) == 1
    replay_api = GEPAAPI()
    assert run_gepa_stage(auth, panel, tmp_path, gepa_source=official_source,
                          fixture_api=replay_api, fixture_evaluate=evaluate(benchmark)) == result
    assert not replay_api.calls


def test_official_gepa_searchqa_backend_route_without_evaluation_callback(tmp_path, monkeypatch, official_source):
    _, panel, args = setup(natural=True, method="gepa")
    args["budget"]["max_iterations"] = 2
    auth = manifest(panel, **args)
    api = GEPAAPI(model="glm-5.3")
    monkeypatch.setattr("skillopt.continual_learning.gepa.CachedAPI", lambda *a, **k: api)
    result = run_gepa_stage(auth, panel, tmp_path, repo=tmp_path, gepa_source=official_source)
    assert result["status"] == "completed", result
    assert result["official_result"]["val_aggregate_scores"][:2] == [0.0, 1.0]
    assert result["costs"]["reflection_calls"] == 1
    assert result["costs"]["solver_calls"] == 8  # Parent/candidate: train minibatch and full selection.
