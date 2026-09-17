"""Offline-only selected TRAIN JSON-mode regression checks."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scripts import validator_json_mode_probe as probe
from skillopt.validator_pilot.api import digest, write_immutable_json
from skillopt.validator_pilot.rubrics import initial_rubric


def valid_judgment():
    rubric = initial_rubric()
    return json.dumps({"rubric_version": rubric["version"], "decision": "pass", "feedback": [],
                       "criteria": [{"id": item["id"], "verdict": "pass", "evidence": [
                           {"source": "candidate_code", "observation": "Concrete code preserves the required operation."}]}
                                    for item in rubric["criteria"]]})


def source_case(source, identity="train-a", repeat=0, *, old_response='{"unfinished":', schema_valid=False):
    system = "Review the candidate. Return only JSON."
    user = json.dumps({"rubric": initial_rubric(), "task": {"id": identity}, "candidate_code": "def f(x): return x"})
    request = {"model": "glm-5.3", "system": system, "user": user, "kind": "judge_static_v0",
               "key": "original-target-hash", "max_tokens": 8000, "repeat": repeat,
               "service": {"host": "token.pjlab.org.cn", "temperature": 0, "stream": True, "reasoning_effort": "low"}}
    identifier = digest(request)
    cache = source / "api/calls" / (identifier + ".json")
    write_immutable_json(cache, {"request_hash": identifier, "request": request, "ok": True,
                                "finish_reason": "stop", "response": old_response})
    path = source / "judgments" / (identifier + ".json")
    write_immutable_json(path, {"id": identity, "family": "source-family", "cluster_id": identity,
                               "split": "train", "repeat": repeat, "skill_version": "manual_seed",
                               "request_hash": "original-target-hash", "judge_request_hash": identifier,
                               "judgment": {"schema_valid": schema_valid}, "PRIVATE_TRAIN_FIELD": "not copied"})
    return path, cache


@pytest.fixture
def environment(tmp_path, monkeypatch):
    repo, source, output = tmp_path / "repo", tmp_path / "original", tmp_path / "regression"
    for relative in ("scripts/validator_json_mode_probe.py", "skillopt/validator_pilot/api.py",
                     "skillopt/validator_pilot/rubrics.py"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("frozen source placeholder\n")
    write_immutable_json(source / "protocol.json", {"model": "glm-5.3", "scope": "source pilot"})
    for identity, repeat in (("train-b", 1), ("train-a", 1), ("train-c", 0), ("train-a", 0), ("train-d", 0)):
        source_case(source, identity, repeat)
    # Not even a valid full JSON object: scanning must stop at split metadata.
    holdout = source / "judgments" / "holdout.json"
    holdout.write_text('{\n  "id": "holdout-never-parse",\n  "split": "holdout",\nUNREAD_PRIVATE_HOLDOUT_BODY')
    configuration_calls = []
    def configuration(repo, model):
        configuration_calls.append((repo, model))
        return "https://token.pjlab.org.cn/v1/chat/completions", "SYNTHETIC_NOT_A_REAL_KEY"
    monkeypatch.setattr(probe, "_configuration", configuration)
    return repo, source, output, configuration_calls


def install_network(monkeypatch, handler):
    original = httpx.Client
    calls = []
    def client(**kwargs):
        calls.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(probe.httpx, "Client", client)
    return calls


def sse(content, *, finish="stop"):
    body = {"model": "glm-5.3", "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}}
    return httpx.Response(200, content=("data: " + json.dumps(body) + "\n\ndata: [DONE]\n\n").encode(),
                          headers={"content-type": "text/event-stream"})


def test_prepare_never_loads_credentials_or_network(environment, monkeypatch):
    repo, source, output, configuration_calls = environment
    def forbidden(**kwargs):
        raise AssertionError("No client should be created by default")
    monkeypatch.setattr(probe.httpx, "Client", forbidden)
    result = probe.run(repo, source, output)
    assert result["status"] == "prepared" and result["selected_train_failures"] == 4
    assert result["network_requests"] == 0 and not result["credentials_loaded"] and not configuration_calls
    protocol = json.loads((output / "protocol.json").read_text())
    assert protocol["max_logical_calls"] == 8 and protocol["workers"] == 1
    assert "UNREAD_PRIVATE_HOLDOUT_BODY" not in json.dumps(protocol)
    assert "PRIVATE_TRAIN_FIELD" not in json.dumps(protocol)


def test_selection_order_and_strict_four_case_bound(environment):
    _, source, _, _ = environment
    cases = probe.select_cases(source)
    assert [(case["id"], case["repeat"]) for case in cases] == [
        ("train-a", 0), ("train-a", 1), ("train-b", 1), ("train-c", 0)]
    assert all(not case["old_schema_valid"] and case["split"] == "train" for case in cases)


def test_nontrain_body_is_never_fully_read(environment, monkeypatch):
    _, source, _, _ = environment
    original = Path.read_text
    def guarded(self, *args, **kwargs):
        if self.name == "holdout.json":
            raise AssertionError("Non-TRAIN body was read")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded)
    assert len(probe.select_cases(source)) == 4


def test_non_json_schema_failure_is_not_eligible(environment):
    _, source, _, _ = environment
    path, _ = source_case(source, "train-000", old_response='{"wrong":"schema"}')
    assert path.exists()
    assert all(case["id"] != "train-000" for case in probe.select_cases(source))


def test_valid_original_is_not_eligible(environment):
    _, source, _, _ = environment
    source_case(source, "train-000", old_response=valid_judgment(), schema_valid=True)
    assert all(case["id"] != "train-000" for case in probe.select_cases(source))


@pytest.mark.parametrize("limit", [0, 5, True])
def test_case_budget_validation(environment, limit):
    _, source, _, _ = environment
    with pytest.raises(ValueError):
        probe.select_cases(source, limit)


def test_exact_prompts_and_only_body_difference_is_response_format(environment):
    _, source, _, _ = environment
    case = probe.select_cases(source)[0]
    default = probe._request(case, "default_format")
    mode = probe._request(case, "json_object")
    assert mode["body"].pop("response_format") == {"type": "json_object"}
    assert default["body"] == mode["body"]
    assert default["body"]["messages"] == [{"role": "system", "content": case["system"]},
                                             {"role": "user", "content": case["user"]}]
    assert default["body"]["reasoning_effort"] == "low" and default["body"]["max_tokens"] == 8000


def test_eight_serial_calls_alternating_order_fresh_controls_and_resume(environment, monkeypatch):
    repo, source, output, configuration_calls = environment
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return sse(valid_judgment() if "response_format" in body else "still invalid JSON")
    configurations = install_network(monkeypatch, handler)
    before = {str(path): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    result = probe.run(repo, source, output, execute=True)
    assert result["status"] == "complete" and result["logical_calls"] == result["http_attempts"] == 8
    assert result["fresh_pairs"] == {"complete_transport_successful_pairs": 4, "json_only_schema_valid": 4,
                                    "default_only_schema_valid": 0, "both_schema_valid": 0, "neither_schema_valid": 0}
    assert ["response_format" in request for request in requests] == [False, True, True, False, False, True, True, False]
    assert result["by_arm"]["default_format"]["schema_valid"] == 0
    assert result["by_arm"]["json_object"]["schema_valid"] == 4
    assert result["total_tokens"] == 80
    assert len(configuration_calls) == 1
    assert configurations[0]["trust_env"] is False and configurations[0]["follow_redirects"] is False
    assert probe.run(repo, source, output, execute=True) == result
    assert len(requests) == 8 and len(configuration_calls) == 1
    assert before == {str(path): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    for path in output.rglob("*.json"):
        assert "SYNTHETIC_NOT_A_REAL_KEY" not in path.read_text()


def test_reroll_success_is_not_credited_as_json_only(environment, monkeypatch):
    repo, source, output, _ = environment
    install_network(monkeypatch, lambda _: sse(valid_judgment()))
    result = probe.run(repo, source, output, execute=True, limit=1)
    assert result["fresh_pairs"]["both_schema_valid"] == 1
    assert result["fresh_pairs"]["json_only_schema_valid"] == 0


def test_json_http_400_stops_without_fallback_or_retry(environment, monkeypatch):
    repo, source, output, _ = environment
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return (httpx.Response(400, json={"error": "PRIVATE_BODY_POSSIBLE_UNSUPPORTED_PARAMETER"})
                if "response_format" in body else sse(valid_judgment()))
    install_network(monkeypatch, handler)
    result = probe.run(repo, source, output, execute=True)
    assert result["status"] == "stopped_transport_failure" and result["logical_calls"] == 2
    assert len(requests) == 2 and result["by_arm"]["json_object"]["api_errors"] == 1
    assert result["fresh_pairs"]["complete_transport_successful_pairs"] == 0
    assert "PRIVATE_BODY" not in json.dumps(result)


def test_timeout_stops_and_is_sanitized(environment, monkeypatch):
    repo, source, output, _ = environment
    def handler(request):
        raise httpx.ReadTimeout("PRIVATE_EXCEPTION", request=request)
    install_network(monkeypatch, handler)
    result = probe.run(repo, source, output, execute=True)
    assert result["logical_calls"] == 1 and result["status"] == "stopped_transport_failure"
    cached = json.loads(next((output / "calls").glob("*.json")).read_text())
    assert cached["error_type"] == "timeout" and "PRIVATE_EXCEPTION" not in json.dumps(cached)


def test_source_cache_corruption_rejected(environment):
    _, source, _, _ = environment
    cases = probe.select_cases(source)
    path = Path(cases[0]["source_cache_path"])
    record = json.loads(path.read_text())
    record["request"]["model"] = "other"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="provenance"):
        probe.select_cases(source)


def test_frozen_input_mutation_detected_before_credentials(environment):
    repo, source, output, configuration_calls = environment
    protocol = probe.prepare(repo, source, output)
    path = Path(protocol["cases"][0]["source_cache_path"])
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="evidence changed"):
        probe.run(repo, source, output, execute=True)
    assert not configuration_calls


def test_frozen_code_mutation_detected_before_credentials(environment):
    repo, source, output, configuration_calls = environment
    probe.prepare(repo, source, output)
    (repo / "scripts/validator_json_mode_probe.py").write_text("changed")
    with pytest.raises(ValueError, match="configuration changed"):
        probe.run(repo, source, output, execute=True)
    assert not configuration_calls


@pytest.mark.parametrize("location", ["same", "child", "parent"])
def test_original_run_cannot_be_output(environment, location):
    repo, source, _, _ = environment
    output = source if location == "same" else source / "inside" if location == "child" else source.parent
    with pytest.raises(ValueError, match="separate directory"):
        probe.prepare(repo, source, output)
