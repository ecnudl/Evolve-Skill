"""V15 synthetic protocol receipts: no live models or downloaded execution."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v15 import runtime as r
from skillopt.coevolution_v15 import tasks as t
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
@pytest.mark.parametrize("phase", ["development", "calibration", "selection", "final"])
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
        assert receipt["request"]["kind"].startswith("v15_solve_")
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
@pytest.mark.parametrize("phase", ["development", "calibration"])
def test_actual_probe_source_phase_and_zero_execution_replay(tmp_path, monkeypatch, phase):
    panel = t.build_panel(smoke=True)
    adapter = panel["train"][1][0] if phase == "development" else panel["calibration"][0][1]
    probe = t.probe_adapter(adapter, t.canonical_inputs(adapter))
    artifact = t.calibration_artifacts(adapter)["reference"]
    result = r.evaluate_probe(probe, artifact, root=tmp_path, key="source-bound", phase=phase)
    assert result["score"]["all_attempt_success"] == 1
    assert result["source_task_hash"] == digest(t.payload(adapter))
    assert result["source_task_id"] == t.payload(adapter)["id"]
    assert result["phase"] == phase and result["api_calls"] == 0
    assert result["native_evaluations"] == 1
    before = tree(tmp_path)
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: pytest.fail("Replay executed"))
    assert r.evaluate_probe(probe, artifact, root=tmp_path, key="source-bound", phase=phase, completed=True) == result
    assert tree(tmp_path) == before


@pytest.mark.parametrize("corruption", ["phase", "source_hash", "input_hash", "id", "hidden"])
def test_probe_binding_tampering_rejected_before_execution(tmp_path, monkeypatch, corruption):
    adapter = t.build_panel(smoke=True)["train"][1][0]
    probe = t.probe_adapter(adapter, t.canonical_inputs(adapter))
    if corruption == "phase":
        probe.task["metadata"]["partition"] = "final"
    elif corruption == "source_hash":
        probe.task["metadata"]["source_task_hash"] = "not-hash"
    elif corruption == "input_hash":
        probe.task["public_cases"][0]["overrides"]["A1"] += 1
    elif corruption == "id":
        probe.task["id"] += "-forged"
    else:
        probe.task["hidden_cases"] = deepcopy(probe.task["public_cases"])
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: pytest.fail("Invalid probe executed"))
    with pytest.raises(ValueError):
        r.evaluate_probe(probe, t.calibration_artifacts(adapter)["reference"], root=tmp_path, key="bad")
    assert not list(tmp_path.iterdir())


def test_probe_unresolved_intent_and_missing_receipt_stop_not_retry(tmp_path, monkeypatch):
    adapter = t.build_panel(smoke=True)["train"][1][0]
    probe = t.probe_adapter(adapter, t.canonical_inputs(adapter))
    artifact = t.calibration_artifacts(adapter)["reference"]
    result = r.evaluate_probe(probe, artifact, root=tmp_path, key="interrupted")
    directory = tmp_path / "runtime/probes"
    (directory / "executions" / (result["execution_id"] + ".json")).unlink()
    for path in (directory / "solves").glob("*.json"):
        path.unlink()
    before = tree(tmp_path)
    monkeypatch.setattr(r.legacy, "evaluate", lambda *a, **k: pytest.fail("Unresolved intent retried"))
    with pytest.raises((ValueError, RuntimeError)):
        r.evaluate_probe(probe, artifact, root=tmp_path, key="interrupted")
    assert tree(tmp_path) == before


@pytest.mark.parametrize("phase", ["development", "final", "selection", "audit"])
def test_calibration_probe_wrong_phase_rejected(tmp_path, phase):
    adapter = t.build_panel(smoke=True)["calibration"][0][1]
    probe = t.probe_adapter(adapter, t.canonical_inputs(adapter))
    with pytest.raises(ValueError):
        r.evaluate_probe(probe, t.calibration_artifacts(adapter)["reference"], root=tmp_path, key="wrong", phase=phase)
    assert not list(tmp_path.iterdir())


def test_explicit_sheet_equality_and_rule_complete_contract():
    assert "==" in r._system("spreadsheet")
    assert "COMPLETE" in r._system("rule_reasoning")
    sheet = t.build_panel(smoke=True)["train"][1][0]
    public = t.public_task(sheet)
    valid = t.calibration_artifacts(sheet)["reference"]
    valid["formulas"]["B1"] = "=IF(A1==0,0,A1)"
    assert r._parse(public, json.dumps(valid), "spreadsheet", None, "generation") == valid
    invalid = deepcopy(valid)
    invalid["formulas"]["B1"] = "=IF(A1=0,0,A1)"
    with pytest.raises((ValueError, SyntaxError)):
        r._parse(public, json.dumps(invalid), "spreadsheet", None, "generation")
    rule = t.build_panel(smoke=True)["final"][2]
    reference = t.calibration_artifacts(rule)["reference"]
    assert r._parse(t.public_task(rule), json.dumps(reference), "rule_reasoning", None, "generation") == reference
    reference["rules"] = [item for item in reference["rules"] if item["id"] != "audit_rule"]
    with pytest.raises(ValueError):
        r._parse(t.public_task(rule), json.dumps(reference), "rule_reasoning", None, "generation")


def test_probe_symlink_root_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    root = tmp_path / "link"
    root.symlink_to(target, target_is_directory=True)
    adapter = t.build_panel(smoke=True)["train"][1][0]
    with pytest.raises(ValueError):
        r.evaluate_probe(t.probe_adapter(adapter, t.canonical_inputs(adapter)), None, root=root, key="link")
    assert not list(target.iterdir())


def test_actual_source_bound_coding_memory_error_is_unknown_not_semantic_zero(tmp_path, monkeypatch):
    adapter = t.build_panel(smoke=True)["train"][0][0]
    probe = t.probe_adapter(adapter,t.canonical_inputs(adapter))
    artifact = t.calibration_artifacts(adapter)["reference"]
    labels = [case["label"] for case in t.payload(probe)["public_cases"]]
    raw = {"files":artifact,"hard":False,"execution_ok":True,
        "public_observations":[{"label":label,"passed":False,"exception":"MemoryError"} for label in labels],
        "private_diagnostics":[],"case_results":[{"id":label+":"+dimension,"passed":False}
            for label in labels for dimension in ("behavior","input_unchanged")],
        "passed_tests":0,"total_tests":2*len(labels)}
    monkeypatch.setattr(r.legacy,"evaluate",lambda *a,**k:deepcopy(raw))
    result = r.evaluate_probe(probe,artifact,root=tmp_path,key="resource-only")
    assert result["score"]["semantic_success"] is None
    assert result["score"]["native_error"] == "resource_unknown"
    assert result["score"]["delivery_valid"] is True
    assert result["score"]["all_attempt_success"] == 0
    original = json.loads((tmp_path / "runtime/probes/executions" / (result["execution_id"]+".json")).read_text())
    assert original["native_evaluation"]["public_observations"][0]["exception"] == "MemoryError"
