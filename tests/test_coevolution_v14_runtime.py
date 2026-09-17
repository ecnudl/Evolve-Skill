"""V14 synthetic protocol receipts: no live models or downloaded execution."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v14 import runtime as r
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v12_runtime import coding, native, put, tree


class FakeAPI:
    model = "glm-5.3"
    service = {"synthetic": True}

    def __init__(self, root, state):
        self.root, self.state = root / "api", state

    def call(self, **arguments):
        self.state["calls"] += 1
        request = {**arguments, "model": self.model, "service": self.service}
        payload = json.loads(arguments["user"])
        name, task = payload["stage"], payload["task"]
        first = name == "generation"
        artifact = {"formulas": {"B1": "=A1+2"}} if task["domain"] == "spreadsheet" else {"rules": task["rules"]}
        if first and self.state.get("wrong_first"):
            artifact = {"formulas": {"B1": "=A1+3"}}
        response = json.dumps(artifact) if first else json.dumps({"action": "keep"})
        if self.state.get("apply") and not first:
            response = json.dumps({"action": "apply", "artifact": artifact})
        if self.state.get("wrong_revision") and not first:
            response = json.dumps({"action": "apply", "artifact": {"formulas": {"B1": "=A1+3"}}})
        if (first and self.state.get("bad_first")) or (not first and self.state.get("bad_revision")):
            response = "{ invalid delivery"
        ok = not self.state.get("fail_all") and not (first and self.state.get("fail_first")) and not (not first and self.state.get("fail_revision"))
        receipt = {"request": request, "request_hash": digest(request), "ok": ok,
            "response": response if ok else "", "http_attempt_count": 1, "finish_reason": "stop" if ok else None}
        put(self.root / "calls" / (receipt["request_hash"] + ".json"), receipt)
        self.state["receipts"].append(receipt)
        return receipt


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = {"calls": 0, "evaluations": 0, "receipts": []}
    api = FakeAPI(tmp_path, state)
    actual = r.legacy.evaluate

    def evaluate(*args, **kwargs):
        state["evaluations"] += 1
        return actual(*args, **kwargs)

    monkeypatch.setattr(r.legacy, "evaluate", evaluate)

    def run(adapter=None, phase="development", completed=False):
        return r.solve(adapter or native(split=phase), api, "Optional synthetic Skill", root=tmp_path,
                       key="history0-task0", phase=phase, completed=completed)

    return tmp_path, state, api, run


@pytest.mark.parametrize("domain", ["spreadsheet", "rule_reasoning"])
@pytest.mark.parametrize("phase", ["development", "selection", "final"])
def test_uniform_two_calls_keep_and_private_boundary(setup, domain, phase):
    root, state, _, run = setup
    solved = run(native(domain, phase), phase=phase)
    assert state["calls"] == 2 and state["evaluations"] == 2
    assert solved["chosen_stage"] == "revision" and solved["rollback_reason"] is None
    assert solved["score"]["all_attempt_success"] == 1
    assert solved["optimizer_feedback_allowed"] is (phase == "development")
    assert len(solved["execution_ids"]) == 3 and solved["execution_ids"][0] == solved["execution_ids"][1]
    assert solved["semantic_guard"] is False
    for receipt in state["receipts"]:
        assert "PRIVATE_" not in receipt["request"]["user"]
        assert receipt["request"]["kind"].startswith("v14_solve_")
    assert len(list((root / "runtime/stages").glob("*.json"))) == 2


@pytest.mark.parametrize("failure,reason", [("bad_revision", "revision_delivery_invalid"), ("fail_revision", "revision_api_unknown")])
def test_revision_failure_retains_initial_but_not_failure_evidence(setup, failure, reason):
    root, state, _, run = setup
    state[failure] = True
    solved = run()
    assert state["calls"] == 2
    assert solved["chosen_stage"] == "generation" and solved["rollback_reason"] == reason
    assert solved["score"]["all_attempt_success"] == 1
    assert solved["public_evaluation"]["score"] == 1
    assert solved["private_evaluation"]["passed_cases"] == 2
    revision = json.loads((root / "runtime/stages" / (solved["request_hashes"][1] + ".json")).read_text())
    assert revision["delivery"]["artifact"] is None
    assert revision["public_score"]["semantic_success"] is None
    assert solved["execution_ids"][0] != solved["execution_ids"][1]


def test_delivery_guard_never_claims_retained_artifact_semantically_correct(setup):
    _, state, _, run = setup
    state.update(wrong_first=True, bad_revision=True)
    solved = run()
    assert solved["chosen_stage"] == "generation"
    assert solved["score"]["semantic_success"] == 0
    assert solved["score"]["oracle_available"] is True


def test_valid_public_regression_not_rolled_back(setup):
    _, state, _, run = setup
    state["wrong_revision"] = True
    solved = run()
    assert solved["chosen_stage"] == "revision" and solved["rollback_reason"] is None
    assert solved["score"]["semantic_success"] == 0
    assert solved["public_evaluation"]["score"] == 0


@pytest.mark.parametrize("initial_failure", ["bad_first", "fail_first", "fail_all"])
def test_no_legal_initial_no_fabricated_fallback(setup, initial_failure):
    _, state, _, run = setup
    state[initial_failure] = True
    solved = run()
    assert state["calls"] == 2 and solved["chosen_stage"] == "revision"
    assert solved["rollback_reason"] is None and solved["artifact"] is None
    assert solved["score"]["semantic_success"] is None


@pytest.mark.parametrize("initial_failure", ["bad_first", "fail_first"])
def test_apply_revision_can_recover_missing_initial(setup, initial_failure):
    _, state, _, run = setup
    state.update({initial_failure: True, "apply": True})
    solved = run()
    assert solved["chosen_stage"] == "revision" and solved["score"]["semantic_success"] == 1


@pytest.mark.parametrize("response", ['KEEP', '{"answer":"KEEP"}', '{"formulas":{"B1":"=A1+2"},"keep":true}',
                                      '{"action":"keep","extra":1}', '{"action":"keep","action":"apply"}',
                                      '{"action":"apply","artifact":"not-object"}', '```json\n{"action":"keep"}\n```'])
def test_ambiguous_old_keep_and_malformed_actions_rejected(response):
    adapter = native()
    with pytest.raises((ValueError, SyntaxError)):
        r._parse(adapter.public_task(), response, "spreadsheet", {"formulas": {"B1": "=A1+2"}}, "revision")


def test_native_apply_merges_initial_without_rewriting_formula_text():
    public = native().public_task()
    original = {"formulas": {"B1": "=A1+2"}}
    artifact = r._parse(public, '{"action":"apply","artifact":{"formulas":{"B1":"=2+A1"}}}',
                        "spreadsheet", original, "revision")
    assert artifact == {"formulas": {"B1": "=2+A1"}}
    assert original == {"formulas": {"B1": "=A1+2"}}


def test_coding_revision_file_or_typed_keep_without_execution():
    public = r.legacy.public_task(coding())
    raw = "<<<FILE helper.py>>>\ndef compute(x): return x+1\n<<<END FILE>>>"
    first = r._parse(public, raw, "coding", None, "generation")
    assert r._parse(public, '{"action":"keep"}', "coding", first, "revision") == first
    assert r._parse(public, raw, "coding", first, "revision") == first
    with pytest.raises(ValueError):
        r._parse(public, '{"action":"apply","artifact":{"files":{}}}', "coding", first, "revision")


def test_completed_rollback_replay_has_zero_calls_execution_or_writes(setup, monkeypatch):
    root, state, api, run = setup
    state["bad_revision"] = True
    result = run()
    before = tree(root)

    def forbidden(*args, **kwargs):
        pytest.fail("Completed replay attempted new activity")

    monkeypatch.setattr(api, "call", forbidden)
    monkeypatch.setattr(r.legacy, "evaluate", forbidden)
    assert run(completed=True) == result and tree(root) == before


@pytest.mark.parametrize("kind", ["stages", "executions"])
def test_missing_completed_evidence_cannot_be_reconstructed(setup, monkeypatch, kind):
    root, _, _, run = setup
    result = run()
    identifier = result["request_hashes"][0] if kind == "stages" else result["execution_ids"][0]
    (root / "runtime" / kind / (identifier + ".json")).unlink()
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: pytest.fail("Unexpected replay"))
    with pytest.raises(ValueError):
        run(completed=True)


def test_probe_persists_source_identity_and_replays_without_execution(tmp_path, monkeypatch):
    adapter = native()
    adapter.task["metadata"] = {"source_task_id": "source-dev", "source_task_hash": "f" * 64,
                                "case_obligations": {"public-sheet": "units"}}
    artifact = {"formulas": {"B1": "=A1+2"}}
    result = r.evaluate_probe(adapter, artifact, root=tmp_path, key="history0-probe0")
    assert result["score"]["semantic_success"] == 1 and result["api_calls"] == 0
    assert result["source_task_id"] == "source-dev" and result["case_obligations"] == {"public-sheet": "units"}
    assert result["artifact_hash"] == digest(artifact)
    before = tree(tmp_path)
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: pytest.fail("Probe re-executed"))
    assert r.evaluate_probe(adapter, artifact, root=tmp_path, key="history0-probe0", completed=True) == result
    assert tree(tmp_path) == before


@pytest.mark.parametrize("phase", ["selection", "final", "holdout"])
def test_probe_never_admits_non_development(tmp_path, phase):
    with pytest.raises(ValueError):
        r.evaluate_probe(native(split=phase), {"formulas": {"B1": "=A1+2"}}, root=tmp_path, key="probe")
    assert list(tmp_path.iterdir()) == []


def test_unresolved_probe_intent_never_blindly_reexecutes(tmp_path, monkeypatch):
    adapter = native()
    artifact = {"formulas": {"B1": "=A1+2"}}
    actual = r.legacy.evaluate
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("Synthetic interrupted execution")

    monkeypatch.setattr(r.legacy, "evaluate", interrupted)
    with pytest.raises(RuntimeError):
        r.evaluate_probe(adapter, artifact, root=tmp_path, key="probe")
    monkeypatch.setattr(r.legacy, "evaluate", actual)
    with pytest.raises(ValueError, match="unresolved"):
        r.evaluate_probe(adapter, artifact, root=tmp_path, key="probe")
    assert len(calls) == 1


def test_probe_does_not_mutate_candidate(tmp_path):
    artifact = {"formulas": {"B1": "=A1+3"}}
    before = deepcopy(artifact)
    result = r.evaluate_probe(native(), artifact, root=tmp_path, key="probe")
    assert result["score"]["semantic_success"] == 0 and artifact == before


def test_probe_memory_error_is_closed_resource_unknown_not_semantic_zero(tmp_path, monkeypatch):
    adapter = coding()
    artifact = deepcopy(adapter.task.files)
    raw = {"files": artifact, "hard": False, "execution_ok": True,
        "public_observations": [{"label": "public-code", "passed": False, "exception": "MemoryError"}],
        "private_diagnostics": [], "case_results": [
            {"id": label + ":" + dimension, "passed": False}
            for label in ("public-code", "PRIVATE_CODE_SENTINEL") for dimension in ("behavior", "input_unchanged")],
        "passed_tests": 0, "total_tests": 4}
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: deepcopy(raw))
    result = r.evaluate_probe(adapter, artifact, root=tmp_path, key="resource-probe")
    assert result["score"]["semantic_success"] is None
    assert result["score"]["native_error"] == "resource_unknown"
    assert result["score"]["delivery_valid"] is True
    original = json.loads((tmp_path / "runtime/probes/executions" / (result["execution_id"] + ".json")).read_text())
    assert original["native_evaluation"]["public_observations"][0]["exception"] == "MemoryError"


def test_probe_symlink_runtime_is_rejected_before_execution(tmp_path, monkeypatch):
    destination = tmp_path / "elsewhere"
    destination.mkdir()
    (tmp_path / "runtime").symlink_to(destination, target_is_directory=True)
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: pytest.fail("Unsafe probe executed"))
    with pytest.raises(ValueError, match="Symlink"):
        r.evaluate_probe(native(), {"formulas": {"B1": "=A1+2"}}, root=tmp_path, key="k")
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("code", ["import os\ndef compute(x): return x+1\n",
                                  "def compute(x): return eval(str(x))\n"])
def test_coding_parser_retains_existing_static_guards(code):
    public = r.legacy.public_task(coding())
    raw = "<<<FILE helper.py>>>\n" + code + "<<<END FILE>>>"
    with pytest.raises(ValueError):
        r._parse(public, raw, "coding", None, "generation")
