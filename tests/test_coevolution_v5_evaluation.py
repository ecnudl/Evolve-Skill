"""Offline tests of paired public-only validation and one-shot repair feedback."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5 import evaluation as e
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v5.core import apply_rubric_patch, feedback_packet, initial_rubric, make_assessment
from skillopt.validator_pilot.api import digest, write_immutable_json


def task_for(index=0, split="dev"):
    files = {"api.py": "import calculation\ndef solve(data):\n    return calculation.double(data['x'])\n",
             "calculation.py": f"# project {index}\ndef double(value):\n    return value\n"}
    reference = {**files, "calculation.py": f"# project {index}\ndef double(value):\n    return value * 2\n"}
    return RepoTask(f"evaluation-{index}", split, "math", f"project-{index}", "Return twice x without changing input.",
                    files, reference, ["calculation.py"],
                    {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"],
                     "additionalProperties": False},
                    [{"label": "public", "input": {"x": 2}, "expected": 4, "exception": None,
                      "public": True, "dimension": "requested_behavior"}],
                    [{"label": "SECRET_PRIVATE_LABEL", "input": {"x": 617}, "expected": 1234, "exception": None,
                      "public": False, "dimension": "preserved_behavior"}], {"secret": "PRIVATE_METADATA"})


class FakeAPI:
    model = "glm-5.3"
    service = {"max_retries": 2, "fake": True}

    def __init__(self, root, responses):
        self.root = root / "api"
        self.responses = list(responses)
        self.calls = []

    def call(self, system, user, *, kind, key, max_tokens, repeat=0):
        request = {"system": system, "user": user, "kind": kind, "key": key, "max_tokens": max_tokens,
                   "repeat": repeat, "model": self.model, "service": self.service}
        path = self.root / "calls" / f"{digest(request)}.json"
        if path.exists():
            return json.loads(path.read_text())
        raw = self.responses.pop(0)
        if callable(raw):
            raw = raw(json.loads(user))
        row = {"request": request, "request_hash": digest(request), "ok": raw is not None,
               "response": json.dumps(raw) if isinstance(raw, dict) else raw,
               "http_attempt_count": 1, "usage": {"total_tokens": 17}, "finish_reason": "stop"}
        self.calls.append(row)
        write_immutable_json(path, row)
        return row


def fake_assess(adapter, files, rubric, *, phase, extra_inputs=None, public_only=None, reference_reviewed=True):
    good = files is not None and "* 2" in files.get("calculation.py", "")
    native = "unknown" if files is None or not reference_reviewed else "pass" if good else "fail"
    probes = "unknown" if not extra_inputs or files is None else "pass" if good else "fail"
    rows = []
    for check in rubric["checks"]:
        if check["id"] not in {"coding_contract", "coding_probe"}:
            status = "not_applicable"
            details = {}
        elif check["id"] == "coding_contract":
            status = native
            details = {"public_only": public_only,
                       "case_results": [{"id": "requested", "passed": good}, {"id": "preserved", "passed": files is not None}],
                       "private_diagnostics": [] if public_only else [{"label": "SECRET_PRIVATE_LABEL", "input": {"x": 617}}]}
        else:
            status = probes
            details = {"receipts": [{"input": value, "passed": good} for value in extra_inputs or []]}
        verified = status in {"pass", "fail"}
        rows.append(make_assessment(check_id=check["id"], task_id=adapter.task.id, domain="coding", phase=phase,
                                    artifact_hash=digest(files), rubric_hash=rubric["rubric_hash"], status=status,
                                    evidence_kind="execution", verified=verified,
                                    gate_eligible=verified and phase in {"development", "promotion"}, details=details))
    return rows


@pytest.fixture
def fake_execution(monkeypatch):
    monkeypatch.setattr(CodingAdapter, "evaluate", fake_assess)


def manifest():
    adapters = [CodingAdapter(task_for(index, "promotion")) for index in range(2)]
    rows = [{"artifact_id": f"{adapter.task.id}-{truth}", "cluster_id": adapter.task.cluster_id,
             "truth": truth, "files": deepcopy(files), "artifact_hash": digest(files), "task_id": adapter.task.id}
            for adapter in adapters for truth, files in (("good", adapter.task.reference_files), ("bad", adapter.task.files))]
    return adapters, rows


def feedback(adapter, rubric):
    rows = adapter.evaluate(adapter.task.files, rubric, phase="development", extra_inputs=[{"x": 3}])
    return feedback_packet(task_id=adapter.task.id, cluster_id=adapter.task.cluster_id, domain="coding",
                           assessments=rows, artifact=adapter.task.files, contract=adapter.task.prompt,
                           hypotheses=["Maybe a missing multiplication; this diagnosis needs execution"])


def delivery():
    return "<<<FILE calculation.py>>>\ndef double(value):\n    return value * 2\n"


def test_probe_only_public_task_code_and_rubric(tmp_path):
    task = task_for()
    api = FakeAPI(tmp_path, [{"inputs": [{"x": 3}]}])
    result = e.probe(api, CodingAdapter(task), task.files, initial_rubric(), key="x")
    assert result["schema_valid"] is True
    assert result["inputs"] == [{"x": 3}]
    prompt = api.calls[0]["request"]["user"]
    assert "SECRET_PRIVATE_LABEL" not in prompt
    assert "PRIVATE_METADATA" not in prompt
    assert "reference_files" not in prompt
    assert "* 2" not in prompt  # Reference source is absent.
    assert api.calls[0]["request"]["max_tokens"] == 6000


@pytest.mark.parametrize("response", [
    {"inputs": []}, {"inputs": [{"x": 1}] * 2}, {"inputs": [{"x": "wrong"}]},
    {"inputs": [{"x": 1}], "verdict": "pass"}, {"inputs": [{"x": i} for i in range(5)]},
    {"inputs": [{"x": 10000000}]}, '{"inputs":[', '{"inputs":[{"x":1,"x":2}]}', None,
])
def test_probe_malformed_unknown_not_retried(tmp_path, response):
    task = task_for()
    api = FakeAPI(tmp_path, [response])
    result = e.probe(api, CodingAdapter(task), task.files, initial_rubric(), key="x")
    assert result["inputs"] == []
    assert result["schema_valid"] is False
    assert len(api.calls) == 1
    assert e.probe(api, CodingAdapter(task), task.files, initial_rubric(), key="x") == result
    assert len(api.calls) == 1


def test_invalid_artifact_no_probe_api_call(tmp_path):
    api = FakeAPI(tmp_path, [])
    result = e.probe(api, CodingAdapter(task_for()), None, initial_rubric(), key="x")
    assert result["error"] == "delivery"
    assert result["request_hash"] is None
    assert api.calls == []


def test_compare_aliases_share_requests_and_keep_distinct_counts(tmp_path, fake_execution):
    adapters, rows = manifest()
    api = FakeAPI(tmp_path, [{"inputs": [{"x": 3}]}] * 8)
    rubrics = {"fixed": initial_rubric(), "feedback": initial_rubric()}
    result = e.compare_validators(api, adapters, rows, rubrics, tmp_path, key="x", repeat=2)
    assert len(api.calls) == 8
    assert result["distinct_artifacts"] == 4
    assert result["distinct_clusters"] == 2
    assert len(result["rows"]["fixed"]) == 8
    assert result["rows"]["fixed"] == result["rows"]["feedback"]
    assert result["costs"]["unique_logical_calls"] == 8
    assert result["costs"]["aliased_rows"] == 8
    assert result["costs"]["total_tokens"] == 8 * 17
    for row in result["rows"]["fixed"]:
        assert row["outcome"] == ("not_detected" if row["truth"] == "good" else "detected")
        assert row["assessments"][0]["details"]["public_only"] is True
    for call in api.calls:
        assert '"truth"' not in call["request"]["user"]
        assert "SECRET_PRIVATE_LABEL" not in call["request"]["user"]


def test_compare_new_rubric_separate_requests_same_artifacts(tmp_path, fake_execution):
    adapters, rows = manifest()
    old = initial_rubric()
    new = apply_rubric_patch(old, {"changes": [{"check_id": "coding_probe", "when": "Always when applicable",
                                                "search": "Search changed and legacy branches", "limits": "Do not alter contract"}],
                                  "rationale": "Probe branch gaps", "source_refs": []})
    api = FakeAPI(tmp_path, [{"inputs": [{"x": 3}]}] * 8)
    result = e.compare_validators(api, adapters, rows, {"old": old, "new": new}, tmp_path, key="x")
    assert len(api.calls) == 8
    assert result["costs"]["aliased_rows"] == 0
    assert [r["artifact_hash"] for r in result["rows"]["old"]] == [r["artifact_hash"] for r in result["rows"]["new"]]


def test_compare_parallel_scheduler_unique_jobs_and_stable_result(tmp_path, fake_execution):
    adapters, rows = manifest()
    api = FakeAPI(tmp_path, [{"inputs": [{"x": 3}]}] * 8)
    scheduled_batches = []

    def parallel(jobs, fn, label):
        scheduled_batches.append(([job[0] for job in jobs], label))
        # Completion order is deliberately reversed: logical report positions
        # and calibration repeat provenance must not depend on wall-clock order.
        return [fn(job) for job in reversed(jobs)]

    api.parallel = parallel
    api.workers = 4
    rubrics = {"fixed": initial_rubric(), "feedback": initial_rubric()}
    result = e.compare_validators(api, adapters, rows, rubrics, tmp_path, key="x", repeat=2)
    assert len(scheduled_batches) == 1
    positions = scheduled_batches[0][0]
    assert len(positions) == len(set(positions)) == 8
    assert len(api.calls) == 8
    assert result["rows"]["fixed"] == result["rows"]["feedback"]
    resumed = e.compare_validators(api, adapters, rows, rubrics, tmp_path, key="x", repeat=2)
    assert resumed == result
    assert scheduled_batches[0] == scheduled_batches[1]
    assert len(api.calls) == 8


def test_compare_rejects_uncapped_parallel_api_before_calls(tmp_path, fake_execution):
    adapters, rows = manifest()
    api = FakeAPI(tmp_path, [])
    api.workers = 8
    api.parallel = lambda *_: pytest.fail("uncapped scheduler ran")
    with pytest.raises(ValueError, match="four-worker"):
        e.compare_validators(api, adapters, rows, {"fixed": initial_rubric()}, tmp_path, key="x")
    assert api.calls == []


def test_compare_duplicate_artifact_preflight_before_api(tmp_path, fake_execution):
    adapters, rows = manifest()
    rows[1]["artifact_hash"] = rows[0]["artifact_hash"]
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="Duplicate"):
        e.compare_validators(api, adapters, rows, {"fixed": initial_rubric()}, tmp_path, key="x")
    assert api.calls == []


def test_compare_development_task_cannot_masquerade_as_calibration(tmp_path):
    adapters, rows = manifest()
    adapters[0] = CodingAdapter(replace(adapters[0].task, split="development"))
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="independently partitioned"):
        e.compare_validators(api, adapters, rows, {"fixed": initial_rubric()}, tmp_path, key="x")


def test_probe_failure_is_unknown_not_clean_detector_pass(tmp_path, fake_execution):
    adapters, rows = manifest()
    api = FakeAPI(tmp_path, ['{"inputs":'] * 4)
    result = e.compare_validators(api, adapters, rows, {"fixed": initial_rubric()}, tmp_path, key="x")
    assert all(row["outcome"] == "unknown" for row in result["rows"]["fixed"] if row["truth"] == "good")
    assert all(row["outcome"] == "detected" for row in result["rows"]["fixed"] if row["truth"] == "bad")


def test_feedback_comparison_same_artifact_budget_and_evaluation(tmp_path, fake_execution):
    adapter, rubric = CodingAdapter(task_for()), initial_rubric()
    packet = feedback(adapter, rubric)
    def choose(payload):
        return delivery() if "development_evidence" in payload else "KEEP"
    api = FakeAPI(tmp_path, [choose, choose])
    result = e.repair_feedback_comparison(api, adapter, adapter.task.files, packet, rubric, tmp_path, key="x")
    assert len(api.calls) == 2
    assert {row["request"]["max_tokens"] for row in api.calls} == {8500}
    payloads = [json.loads(row["request"]["user"]) for row in api.calls]
    score = next(payload for payload in payloads if "development_evidence" not in payload)
    structured = next(payload for payload in payloads if "development_evidence" in payload)
    assert score["initial_code"] == structured["initial_code"]
    assert score["aggregate_feedback"] == structured["aggregate_feedback"]
    assert "development_evidence" not in score
    assert "SECRET_PRIVATE_LABEL" not in json.dumps(score)
    assert "SECRET_PRIVATE_LABEL" in json.dumps(structured)
    assert result["arms"]["score_only"]["metrics"]["repair_success"] is False
    assert result["arms"]["structured_evidence"]["metrics"]["repair_success"] is True
    assert result["arms"]["structured_evidence"]["new_passing_check_losses"] == []
    assert result["no_skill_update"] is True
    assert "no_single_case" in result["interpretation"]


@pytest.mark.parametrize("response", [None, "```python\nreturn 4\n```", "<<<FILE protected.py>>>\nx = 1\n"])
def test_feedback_transport_and_delivery_not_semantic_regression(tmp_path, fake_execution, response):
    adapter, rubric = CodingAdapter(task_for()), initial_rubric()
    def choose(payload):
        return delivery() if "development_evidence" in payload else response
    api = FakeAPI(tmp_path, [choose, choose])
    result = e.repair_feedback_comparison(api, adapter, adapter.task.files, feedback(adapter, rubric), rubric, tmp_path, key="x")
    row = result["arms"]["score_only"]
    assert row["metrics"]["repair_success"] is None
    assert row["error"] in {"transport_unavailable", "delivery"}


def test_feedback_requires_same_initial_artifact(tmp_path, fake_execution):
    adapter, rubric = CodingAdapter(task_for()), initial_rubric()
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="same frozen"):
        e.repair_feedback_comparison(api, adapter, adapter.task.reference_files,
                                     feedback(adapter, rubric), rubric, tmp_path, key="x")
    assert api.calls == []


def test_feedback_good_artifact_not_selected_as_failure(tmp_path, fake_execution):
    adapter, rubric = CodingAdapter(task_for()), initial_rubric()
    artifact = adapter.task.reference_files
    rows = adapter.evaluate(artifact, rubric, phase="development")
    packet = feedback_packet(task_id=adapter.task.id, cluster_id=adapter.task.cluster_id, domain="coding",
                             assessments=rows, artifact=artifact, contract=adapter.task.prompt)
    api = FakeAPI(tmp_path, [])
    with pytest.raises(ValueError, match="confirmed bad"):
        e.repair_feedback_comparison(api, adapter, artifact, packet, rubric, tmp_path, key="x")


def final_row(policy="no_skill", domain="coding", task_id="task0", score=1.0, **kw):
    return {"policy": policy, "domain": domain, "task_id": task_id, "cluster_id": "cluster-" + task_id,
            "history": 0, "repeat": 0, "score": score, "request_hashes": ["request-" + task_id], **kw}


def test_final_summary_macro_domains_not_question_counts():
    rows = [final_row(task_id="code", score=1)] + [final_row(domain="qa", task_id=f"qa-{i}", score=0) for i in range(4)]
    summary = e.summarize_final(rows)
    assert summary["macro"]["no_skill"]["available_score_mean"] == 0.5
    assert summary["by_policy"]["no_skill"]["qa"]["unique_tasks"] == 4


def test_final_summary_repeats_do_not_inflate_tasks_and_aliases_explicit():
    rows = [final_row(repeat=draw) for draw in range(3)] + [final_row(policy="research", repeat=draw) for draw in range(3)]
    summary = e.summarize_final(rows)
    assert summary["logical_rows"] == 6
    assert summary["by_policy"]["no_skill"]["coding"]["unique_tasks"] == 1
    assert summary["unique_model_requests"] == 1
    assert summary["unique_trajectory_receipts"] == 1
    assert summary["aliased_trajectory_rows"] == 5
    assert summary["paired_vs_no_skill"]["research"]["structurally_shared_positions"] == 3


def test_final_unknown_is_separate_from_semantic_score():
    rows = [final_row(score=None, error="transport_unavailable"),
            final_row(task_id="task1", score=1, fallback=True)]
    summary = e.summarize_final(rows)
    domain = summary["by_policy"]["no_skill"]["coding"]
    assert domain["available_score_mean"] == 1
    assert domain["all_attempt_yield_mean"] == 0.5
    assert domain["unknown"] == 1
    assert domain["available_coverage"] == domain["fallback_coverage"] == 0.5


def test_final_pair_wins_losses_and_missing():
    rows = [final_row(task_id="a", score=0), final_row(task_id="b", score=1), final_row(task_id="c", score=1),
            final_row(policy="fixed", task_id="a", score=1, request_hashes=["other-a"]),
            final_row(policy="fixed", task_id="b", score=0, request_hashes=["other-b"]),
            final_row(policy="fixed", task_id="c", score=None, request_hashes=["other-c"])]
    summary = e.summarize_final(rows)["paired_vs_no_skill"]["fixed"]
    assert summary["wins"] == summary["losses"] == summary["missing_positions"] == 1
    assert summary["negative_transfer_fraction"] == 0.5


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.01, 100, True])
def test_final_invalid_scores_rejected(score):
    with pytest.raises(ValueError, match="finite fraction"):
        e.summarize_final([final_row(score=score)])


def test_final_duplicate_position_rejected():
    with pytest.raises(ValueError, match="Duplicate logical"):
        e.summarize_final([final_row(), final_row()])


def test_final_macro_pairs_reports_worst_domain_and_harm_fraction():
    rows = [final_row(domain=domain, task_id=domain, score=0.5) for domain in ("coding", "qa")]
    rows += [final_row(policy="research", task_id="coding", score=0.9, request_hashes=["new-code"]),
             final_row(policy="research", domain="qa", task_id="qa", score=0.4, request_hashes=["new-qa"])]
    result = e.summarize_final(rows)["paired_vs_no_skill"]["research"]
    assert result["worst_domain_delta"] == pytest.approx(-0.1)
    assert result["paired_macro_delta"] == pytest.approx(0.15)
    assert result["negative_domain_fraction"] == 0.5


def test_final_identical_native_trajectory_cannot_have_distinct_scores():
    with pytest.raises(ValueError, match="Identical native-scored"):
        e.summarize_final([final_row(score=0.5), final_row(policy="research", score=1)])
