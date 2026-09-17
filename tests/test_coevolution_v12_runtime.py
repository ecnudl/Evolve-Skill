"""Synthetic offline receipts and native sandbox fixtures, no model service."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.coevolution_v12 import runtime as r
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def forbidden(*args, **kwargs):
    pytest.fail("Completed replay may not execute or call a live model")


def native(domain="spreadsheet", split="development"):
    common = {"split": split, "contract": {"change_scope": "partial_update",
        "preserve_obligations": ["Preserve unrelated facts or cells."], "supersedes_old_policy": False},
        "prompt": "Apply the explicitly requested public behavior.", "cluster_id": "synthetic-family"}
    if domain == "spreadsheet":
        task = {**common, "id": "runtime-sheet", "domain": domain, "inputs": {"A1": 7},
            "formulas": {"B1": "=A1"}, "editable_cells": ["B1"],
            "public_cases": [{"id": "public-sheet", "overrides": {}, "expected": {"B1": 9}}],
            "hidden_cases": [{"id": "PRIVATE_SHEET_SENTINEL", "overrides": {"A1": 113}, "expected": {"B1": 115}}]}
    else:
        task = {**common, "id": "runtime-rule", "domain": domain,
            "rules": [{"id": "r", "if": ["ready"], "then": "done"}], "editable_rule_ids": ["r"],
            "vocabulary": ["ready", "done", "blocked"], "answer_facts": ["done"],
            "public_cases": [{"id": "public-rule", "facts": ["ready"], "expected": ["done"]}],
            "hidden_cases": [{"id": "PRIVATE_RULE_SENTINEL", "facts": ["ready", "done"], "expected": ["done"]}]}
    return NativeAdapter(task)


def coding():
    files = {"api.py": 'from helper import compute\ndef solve(data): return {"answer":compute(data["x"])}\n',
             "helper.py": "def compute(x): return x+1\n"}
    def case(label, x, public):
        return {"label": label, "input": {"x": x}, "expected": {"answer": x+1}, "exception": None,
                "dimension": "requested_behavior", "public": public}
    return CodingAdapter(RepoTask(id="runtime-coding", split="development", family="synthetic-family",
        cluster_id="synthetic-family", prompt="Return input x plus one without mutating the input.", files=files,
        reference_files=deepcopy(files), editable_paths=["api.py", "helper.py"],
        input_domain={"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]},
        public_cases=[case("public-code", 1, True)], private_cases=[case("PRIVATE_CODE_SENTINEL", 113, False)], metadata={}))


class FakeAPI:
    model = "glm-5.3"
    service = {"max_retries": 2, "synthetic": True}

    def __init__(self, root, state):
        self.root, self.state = root / "api", state

    def call(self, system, user, kind, key, max_tokens, repeat):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
            "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        self.state["calls"] += 1
        if self.state.get("interrupt_call"):
            raise RuntimeError("synthetic unresolved transport")
        payload = json.loads(user)
        stage, task = payload["stage"], payload["task"]
        if task["id"] == "runtime-coding":
            response = "<<<FILE helper.py>>>\ndef compute(x): return x+1\n<<<END FILE>>>"
        elif task["domain"] == "spreadsheet":
            response = json.dumps({"formulas": {"B1": "=A1+2"}})
        else:
            response = json.dumps({"rules": task["rules"]})
        if stage == "generation" and self.state.get("bad_first"):
            response = "not a legal artifact"
        if stage == "revision" and self.state.get("keep"):
            response = "KEEP"
        if stage == "revision" and self.state.get("bad_revision"):
            response = "not a legal artifact"
        ok = not self.state.get("fail_all") and not (stage == "generation" and self.state.get("fail_first"))
        receipt = {"request": request, "request_hash": digest(request), "ok": ok,
            "response": response if ok else "", "http_attempt_count": 1,
            "usage": {"total_tokens": 2}, "finish_reason": "stop"}
        put(self.root / "calls" / (receipt["request_hash"] + ".json"), receipt)
        self.state["receipts"].append(receipt)
        return receipt


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = {"calls": 0, "evaluations": 0, "receipts": []}
    api = FakeAPI(tmp_path, state)
    original = r.legacy.evaluate
    def counted(*args, **kwargs):
        state["evaluations"] += 1
        return original(*args, **kwargs)
    monkeypatch.setattr(r.legacy, "evaluate", counted)
    def run(adapter=None, phase="development", **kwargs):
        return r.solve(adapter or native(split=phase), api, "Skill guidance.", key="history0-round0",
                       repeat=0, root=tmp_path, phase=phase, **kwargs)
    return tmp_path, state, api, run


@pytest.mark.parametrize("domain", ["spreadsheet", "rule_reasoning"])
@pytest.mark.parametrize("phase", ["development", "selection", "final"])
def test_uniform_two_stage_solver_never_sends_private_tests(setup, domain, phase):
    _, state, _, run = setup
    result = run(native(domain, phase), phase)
    assert state["calls"] == 2
    assert len(result["request_hashes"]) == 2 and len(set(result["request_hashes"])) == 2
    assert result["score"]["all_attempt_success"] == 1
    assert result["score"]["oracle_available"] and result["score"]["semantic_success"] == 1
    assert result["optimizer_feedback_allowed"] is (phase == "development")
    for receipt in state["receipts"]:
        visible = receipt["request"]["system"] + receipt["request"]["user"]
        assert "PRIVATE_" not in visible and "hidden_cases" not in visible
        assert "reference_files" not in visible and "reference_artifact" not in visible
    revision = json.loads(state["receipts"][1]["request"]["user"])
    assert "structured_public_feedback" in revision
    assert revision["structured_public_feedback"]["unknown_is_not_semantic_failure"]
    assert "PRIVATE_" in json.dumps(result["private_evaluation"])
    if phase != "development":
        assert "PRIVATE_" not in json.dumps(result["trace"])


def test_completed_replay_does_not_call_or_evaluate_and_changes_no_bytes(setup, monkeypatch):
    root, state, api, run = setup
    expected = run()
    before, counts = tree(root), (state["calls"], state["evaluations"])
    monkeypatch.setattr(api, "call", forbidden)
    monkeypatch.setattr(r.legacy, "evaluate", forbidden)
    monkeypatch.setattr(r, "write_immutable_json", forbidden)
    assert run() == run(completed=True) == expected
    assert before == tree(root) and counts == (state["calls"], state["evaluations"])


@pytest.mark.parametrize("directory", ["runtime/solves", "runtime/stages", "runtime/request_intents",
                                      "runtime/execution_intents", "runtime/executions", "api/calls"])
def test_missing_completed_evidence_not_repaired(setup, directory, monkeypatch):
    root, _, api, run = setup
    run()
    next((root / directory).glob("*.json")).unlink()
    before = tree(root)
    monkeypatch.setattr(api, "call", forbidden)
    monkeypatch.setattr(r.legacy, "evaluate", forbidden)
    with pytest.raises((ValueError, FileNotFoundError)):
        run(completed=True)
    assert before == tree(root)


def test_unresolved_api_intent_blocks_resampling(setup):
    _, state, _, run = setup
    state["interrupt_call"] = True
    with pytest.raises(RuntimeError, match="unresolved transport"):
        run()
    state["interrupt_call"] = False
    with pytest.raises(ValueError, match="unresolved actual request"):
        run()
    assert state["calls"] == 1


def test_unresolved_execution_blocks_reexecution(setup, monkeypatch):
    _, state, _, run = setup
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic execution interrupted")
    monkeypatch.setattr(r.legacy, "evaluate", fail)
    with pytest.raises(RuntimeError, match="execution interrupted"):
        run()
    monkeypatch.setattr(r.legacy, "evaluate", forbidden)
    with pytest.raises(ValueError, match="unresolved execution"):
        run()
    assert state["calls"] == 1


def test_first_api_failure_can_recover_without_extra_calls(setup):
    _, state, _, run = setup
    state["fail_first"] = True
    result = run()
    assert state["calls"] == 2 and result["stage_api_ok"] == [False, True]
    assert result["api_ok"] is False and result["score"]["semantic_success"] == 1


def test_both_api_failures_unknown_not_semantic_zero(setup):
    _, state, _, run = setup
    state["fail_all"] = True
    result = run()
    assert state["calls"] == 2 and result["stage_api_ok"] == [False, False]
    assert result["score"]["all_attempt_success"] == 0
    assert result["score"]["semantic_success"] is None and not result["score"]["oracle_available"]


def test_invalid_first_artifact_receives_structured_error_and_one_revision(setup):
    _, state, _, run = setup
    state["bad_first"] = True
    result = run()
    assert state["calls"] == 2 and result["score"]["all_attempt_success"] == 1
    revision = json.loads(state["receipts"][1]["request"]["user"])
    assert revision["initial_artifact_valid"] is False
    assert revision["structured_public_feedback"]["delivery_status"] == "fail"
    assert revision["structured_public_feedback"]["delivery"]["type"]


def test_bad_revision_does_not_silently_keep_valid_initial(setup):
    _, state, _, run = setup
    state["bad_revision"] = True
    result = run()
    assert result["artifact"] is None and result["score"]["semantic_success"] is None


def test_keep_is_exact_and_reuses_native_execution(setup):
    _, state, _, run = setup
    state["keep"] = True
    result = run()
    assert result["score"]["all_attempt_success"] == 1
    assert state["evaluations"] == 2  # Shared public artifact plus full private evaluation.
    assert result["execution_ids"][0] == result["execution_ids"][1]


def test_invalid_keep_without_initial_stays_unknown(setup):
    _, state, _, run = setup
    state.update(keep=True, bad_first=True)
    result = run()
    assert result["artifact"] is None and result["score"]["semantic_success"] is None


@pytest.mark.parametrize("split,phase", [("final", "development"), ("selection", "development"),
                                        ("development", "final"), ("development", "selection")])
def test_phase_cannot_launder_hidden_data_as_development(setup, split, phase):
    _, state, _, run = setup
    with pytest.raises(ValueError, match="relabel"):
        run(native(split=split), phase)
    assert state["calls"] == 0


@pytest.mark.parametrize("target,field,value", [("solves", "score", {}), ("stages", "public_score", {}),
                                               ("executions", "intent_hash", "a"*64)])
def test_resealed_evidence_tampering_rejected(setup, target, field, value):
    root, _, _, run = setup
    run()
    path = next((root / "runtime" / target).glob("*.json"))
    record = json.loads(path.read_text())
    record.pop("record_hash")
    record[field] = value
    put(path, seal(record))
    with pytest.raises(ValueError):
        run(completed=True)


def test_bounded_trace_marks_omission_without_slicing_code():
    adapter = native()
    artifact = {"oversized": "x"*100000}
    trace = r._trace(adapter, artifact, {}, {}, "development")
    assert len(json.dumps(trace)) < r.MAX_TRACE_CHARS
    assert trace["artifact"] is None and trace["artifact_hash"] == digest(artifact)
    assert "artifact_inline_omitted" in trace


def test_memory_error_projection_unknown_and_raw_evidence_unchanged():
    adapter = coding()
    original = {"hard": False, "execution_ok": True, "public_pass": False,
        "case_results": [{"passed": False}], "public_observations": [{"exception": "MemoryError", "passed": False}],
        "private_diagnostics": []}
    before = deepcopy(original)
    projected = r._resource_unknown(adapter, original)
    assert original == before and projected["hard"] is None
    assert projected["error_category"] == "resource_unknown" and projected["case_results"] == []
    score = r.legacy.score(adapter, {"present": "artifact"}, projected)
    assert score["semantic_success"] is None and score["all_attempt_success"] == 0


@pytest.mark.skipif(sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file(),
                    reason="Actual native Coding requires OS isolation")
def test_real_synthetic_coding_uses_native_sandbox(setup):
    _, state, _, run = setup
    result = run(coding())
    assert result["score"]["all_attempt_success"] == 1
    assert result["private_evaluation"]["total_tests"] == 4
    assert state["calls"] == 2
    assert "PRIVATE_CODE_SENTINEL" not in "".join(receipt["request"]["user"] for receipt in state["receipts"])


def test_frozen_grammar_does_not_accept_repaired_model_json(setup):
    adapter = native()
    receipt = {"ok": True, "response": '{"formulas":{"B1":"=A1+2"},}', "request_hash": "a"*64}
    result = r._delivery(r.legacy.public_task(adapter), receipt, adapter.domain, None, "generation", "development")
    assert result["artifact"] is None and result["status"] == "fail"
