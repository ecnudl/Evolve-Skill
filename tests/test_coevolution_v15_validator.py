"""Pure hand-authored protocol fixtures: no model, network or generated code."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v15 import validator as v
from skillopt.validator_pilot.api import digest, write_immutable_json


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class API:
    model = "glm-5.3"
    service = {"offline_fixture": True}

    def __init__(self, root):
        self.root = root / "api"
        self.calls = []
        self.raw = None
        self.ok = True

    def call(self, **kwargs):
        self.calls.append(kwargs)
        user = json.loads(kwargs["user"])
        if kwargs["kind"] == "v15_validator_search":
            inputs = [{"x": 1}, {"x": 2}] if user["search_policy"] == "new" else [{"x": 1}]
            raw = json.dumps({"inputs": inputs})
        else:
            raw = json.dumps({"search_policy": "new", "when": "Only legal inputs", "citations": []})
        request = {**kwargs, "model": self.model, "service": self.service}
        receipt = {"request": request, "request_hash": digest(request), "response": self.raw or raw,
                   "ok": self.ok, "finish_reason": "stop" if self.ok else None, "http_attempt_count": 1}
        write_immutable_json(self.root / "calls" / (receipt["request_hash"] + ".json"), receipt)
        return receipt


@pytest.fixture
def setup(tmp_path, monkeypatch):
    api = API(tmp_path)
    counter = {"native": 0}
    monkeypatch.setattr(v.tasks, "payload", lambda a: deepcopy(a))
    monkeypatch.setattr(v.tasks, "public_task", lambda a: {"id": a["id"], "prompt": "Fixture public input x"})
    monkeypatch.setattr(v.tasks, "public_input_schema", lambda a: {"x": "integer0..2"})
    monkeypatch.setattr(v.tasks, "validate_probe_input", lambda a, x:
        type(x) is dict and set(x) == {"x"} and type(x["x"]) is int and 0 <= x["x"] <= 2)
    monkeypatch.setattr(v.tasks, "canonical_inputs", lambda a: [{"x": 1}, {"x": 2}])
    monkeypatch.setattr(v.tasks, "control_inputs", lambda a: [{"x": 1}, {"x": 2}])
    monkeypatch.setattr(v.tasks, "probe_adapter", lambda a, xs: {"source": deepcopy(a), "inputs": deepcopy(xs)})
    monkeypatch.setattr(v.tasks, "calibration_artifacts", lambda a: {k: {"kind": k} for k in
        ("reference", "equivalent", "semantic_mutant", "preservation_mutant")})

    def evaluate(adapter, artifact, *, root, key, completed=False, phase=None):
        identity = {"adapter": adapter, "artifact": artifact, "key": key}
        path = Path(root) / "fake-native" / (digest(identity) + ".json")
        if path.exists():
            return v.research._read(path)
        if completed:
            raise ValueError("No execution on replay")
        counter["native"] += 1
        xs = [x["x"] for x in adapter["inputs"]]
        failed = ((artifact["kind"] == "semantic_mutant" and 1 in xs)
                  or (artifact["kind"] == "preservation_mutant" and 2 in xs)
                  or artifact["kind"] == "all_fail")
        unknown = artifact["kind"] == "unknown"
        score = {"oracle_available": not unknown, "delivery_valid": True,
                 "semantic_success": None if unknown else int(not failed),
                 "all_attempt_success": int(not unknown and not failed)}
        return v._save(path, {"phase": phase, "source_task_hash": digest(adapter["source"]),
            "source_task_id": adapter["source"]["id"], "artifact_hash": digest(artifact),
            "score": score, "evaluation": {"manual_fixture_only": True},
            "execution_id": digest(identity), "execution_receipt_hash": digest(score)})

    monkeypatch.setattr(v.runtime, "evaluate_probe", evaluate)
    adapter = {"id": "manual-dev", "split": "development", "domain": "coding", "reference_files": "NEVER_VISIBLE"}
    return tmp_path, api, counter, adapter


def next_state(parent=None, policy="new"):
    parent = parent or v.initial_state()
    return seal({"version": v.VERSION, "revision": parent["revision"] + 1,
        "parent_hash": parent["record_hash"], "search_policy": policy, "when": "Only legal inputs",
        "provenance": {"fixture": True}})


def evidence(**extra):
    return [seal({"phase": "development", "observations": [], **extra})]


def test_initial_state_and_fixed_schema():
    state = v.initial_state()
    assert v.validate_state(state) == state
    body = {k: x for k, x in state.items() if k != "record_hash"}
    body["oracle"] = "model decides"
    with pytest.raises(ValueError):
        v.validate_state(seal(body))


def test_public_only_search_and_offline_replay(setup, monkeypatch):
    root, api, counter, task = setup
    result = v.search(api, task, v.initial_state(), root=root, key="h0r0")
    assert result["valid"] and len(api.calls) == 1 and counter["native"] == 0
    assert "NEVER_VISIBLE" not in api.calls[0]["user"]
    assert set(json.loads(api.calls[0]["user"])) == {"task", "input_schema", "search_policy", "when"}
    before = tree(root)
    monkeypatch.setattr(api, "call", lambda **k: pytest.fail("Replay attempted API"))
    assert v.search(api, task, v.initial_state(), root=root, key="h0r0", completed=True) == result
    assert tree(root) == before


@pytest.mark.parametrize("raw", ['{"inputs":[]}', '{"inputs":[{"x":1},{"x":3}]}',
    '{"inputs":[{"x":1},{"x":1}]}', '{"inputs":[{"x":true}]}',
    '{"inputs":[{"x":1}],"expected":[1]}', '{"inputs":[{"x":1}],"inputs":[{"x":2}]}',
    '{"inputs":[{"x":NaN}]}', '```json\n{"inputs":[{"x":1}]}\n```', '{"inputs":['])
def test_illegal_delivery_rejects_entire_input_set(setup, raw):
    root, api, counter, task = setup
    api.raw = raw
    result = v.search(api, task, v.initial_state(), root=root, key="invalid")
    assert not result["valid"] and result["inputs"] == []
    assessed = v.assess(task, {"kind": "reference"}, result, root=root, key="assess")
    assert assessed["outcome"] == "unknown" and counter["native"] == 0


def test_api_failure_cached_without_resampling(setup):
    root, api, _, task = setup
    api.ok = False
    row = v.search(api, task, v.initial_state(), root=root, key="fail")
    assert row["error"] == "api_unknown"
    assert v.search(api, task, v.initial_state(), root=root, key="fail") == row
    assert len(api.calls) == 1


def test_missing_durable_api_receipt_is_not_retried(setup):
    root, api, _, task = setup
    row = v.search(api, task, v.initial_state(), root=root, key="lost")
    (api.root / "calls" / (row["request_hash"] + ".json")).unlink()
    with pytest.raises(ValueError, match="unresolved"):
        v.search(api, task, v.initial_state(), root=root, key="lost")
    assert len(api.calls) == 1


@pytest.mark.parametrize("phase", ["final", "selection", "audit", "test"])
def test_final_and_relabelled_phase_forbidden(setup, phase):
    root, api, _, task = setup
    task["split"] = phase
    with pytest.raises(ValueError):
        v.search(api, task, v.initial_state(), root=root, key="wrong")
    assert not api.calls


def test_assess_exact_source_and_no_input_delivery(setup):
    root, api, counter, task = setup
    searched = v.search(api, task, v.initial_state(), root=root, key="s")
    unknown = v.assess(task, None, searched, root=root, key="no-artifact")
    assert unknown["native_evaluations"] == 0 and counter["native"] == 0
    row = v.assess(task, {"kind": "semantic_mutant"}, searched, root=root, key="same")
    assert row["outcome"] == "detected" and row["native_evaluations"] == 1
    before = tree(root)
    assert v.assess(task, {"kind": "semantic_mutant"}, searched, root=root, key="same", completed=True) == row
    assert before == tree(root) and counter["native"] == 1
    altered = {**task, "id": "other"}
    with pytest.raises(ValueError):
        v.assess(altered, {}, searched, root=root, key="wrong-source")


def test_proposal_source_model_provenance_and_deferred_activation(setup):
    root, api, _, _ = setup
    parent = v.initial_state()
    row = v.propose(api, parent, evidence(), arm="adaptive", root=root, key="p")
    assert row["valid"] and row["changed"] and row["activation_authorized"] is False
    assert row["candidate_state"]["parent_hash"] == parent["record_hash"]
    provenance = row["candidate_state"]["provenance"]
    assert provenance["model"] == "glm-5.3" and provenance["request_hash"] == row["request_hash"]
    assert provenance["development_record_hashes"] == [evidence()[0]["record_hash"]]
    before = tree(root)
    assert v.propose(api, parent, evidence(), arm="adaptive", root=root, key="p", completed=True) == row
    assert before == tree(root) and len(api.calls) == 1


@pytest.mark.parametrize("extra", [{"nested": {"phase": "final"}}, {"reference_files": {}},
    {"gold_answer": "bad"}, {"nested": {"split": "calibration"}}, {"hidden_tests": []}])
def test_proposal_rejects_leaked_evidence_before_api(setup, extra):
    root, api, _, _ = setup
    with pytest.raises(ValueError):
        v.propose(api, v.initial_state(), evidence(**extra), arm="adaptive", root=root, key="p")
    assert not api.calls


@pytest.mark.parametrize("raw", ['{"search_policy":"x","when":"y","citations":[],"oracle":"model"}',
    '{"search_policy":"x","when":"y","citations":[{"url":"https://a","quote":"not seen anywhere"}]}',
    '{broken', '{"search_policy":"","when":"y","citations":[]}'])
def test_invalid_proposal_retains_parent_no_repair(setup, raw):
    root, api, _, _ = setup
    api.raw = raw
    row = v.propose(api, v.initial_state(), evidence(), arm="adaptive", root=root, key="p")
    assert not row["valid"] and row["candidate_state"] == v.initial_state() and len(api.calls) == 1


def test_matched_blind_calibration_detects_new_defect_and_natural_diagnostic(setup):
    root, api, counter, task = setup
    task["split"] = "calibration"
    source = seal({"phase": "calibration", "task_id": task["id"], "identity": {"task_hash": digest(task)},
        "artifact": {"kind": "preservation_mutant"},
        "score": {"oracle_available": True, "semantic_success": 1, "all_attempt_success": 1, "delivery_valid": True}})
    row = v.calibrate(api, [task], v.initial_state(), next_state(), root=root, key="cal",
                      natural_artifacts={task["id"]: source})
    assert row["accepted"] and row["activation"] == "next_round_only"
    assert row["metrics"]["old"]["true_detections"] == 1
    assert row["metrics"]["new"]["true_detections"] == 2
    assert row["paired_true_detection_gains"] == row["natural_detection_gains"] == 1
    assert row["logical_search_opportunities"] == len(api.calls) == 2
    assert counter["native"] == 14  # Four canonical + two*(four controls + one natural).
    assert all("mutant" not in c["user"] and "NEVER_VISIBLE" not in c["user"] for c in api.calls)
    assert len(set(row["request_hashes"])) == 2
    before = tree(root)
    assert v.calibrate(api, [task], v.initial_state(), next_state(), root=root, key="cal", completed=True,
                      natural_artifacts={task["id"]: source}) == row
    assert before == tree(root) and counter["native"] == 14 and len(api.calls) == 2


def test_identical_state_queries_separate_but_cannot_promote(setup):
    root, api, _, task = setup
    task["split"] = "calibration"
    row = v.calibrate(api, [task], v.initial_state(), v.initial_state(), root=root, key="same")
    assert not row["accepted"] and len(set(row["request_hashes"])) == 2
    assert api.calls[0]["user"] == api.calls[1]["user"]


def test_control_dispute_blocks_promotion(setup, monkeypatch):
    root, api, _, task = setup
    task["split"] = "calibration"
    original = v.tasks.calibration_artifacts
    monkeypatch.setattr(v.tasks, "calibration_artifacts", lambda a: {**original(a), "reference": {"kind": "unknown"}})
    row = v.calibrate(api, [task], v.initial_state(), next_state(), root=root, key="dispute")
    assert not row["canonical_valid"] and not row["accepted"]


def test_paired_detection_loss_blocks_equal_aggregate_gain(setup, monkeypatch):
    root, api, _, task = setup
    task["split"] = "calibration"
    actual = api.call

    def call(**kwargs):
        api.raw = '{"inputs":[{"x":2}]}' if json.loads(kwargs["user"])["search_policy"] == "new" else None
        return actual(**kwargs)

    monkeypatch.setattr(api, "call", call)
    row = v.calibrate(api, [task], v.initial_state(), next_state(), root=root, key="lost")
    assert row["paired_true_detection_losses"] == row["paired_true_detection_gains"] == 1
    assert not row["accepted"]


def test_whole_control_truth_aggregates_chunks_not_every_case_must_fail(setup, monkeypatch):
    root, api, _, task = setup
    task["split"] = "calibration"
    monkeypatch.setattr(v.tasks, "control_inputs", lambda a: [{"x": 1}] * 4 + [{"x": 2}])
    row = v.calibrate(api, [task], v.initial_state(), next_state(), root=root, key="chunks")
    assert row["canonical_valid"] and row["accepted"]
    assert len(row["canonical_controls"]) == 8
    assert row["control_truth_source"] == "complete_ordinary_inputs_not_canonical_search"


def test_wrong_parent_and_nonindependent_panel_rejected_before_calls(setup):
    root, api, _, task = setup
    with pytest.raises(ValueError):
        v.calibrate(api, [task], v.initial_state(), next_state(), root=root, key="leak")
    task["split"] = "calibration"
    with pytest.raises(ValueError):
        v.calibrate(api, [task], v.initial_state(), next_state(next_state()), root=root, key="orphan")
    assert not api.calls


@pytest.mark.parametrize("value", [float("inf"), 1000001, {"a": "x" * 2049}, list(range(65)), object()])
def test_json_resource_bounds(value):
    with pytest.raises(ValueError):
        v._bounded(value)


def test_real_v15_native_feedback_reaches_policy_without_reference(tmp_path):
    """Actual closed runtime/evidence schema, fixed DSL only; no generated Python."""
    from skillopt.coevolution_v15 import evidence as e

    adapter = v.tasks._sheet(v.tasks.SMOKE_SHEET[0], "development")

    class NativeAPI(API):
        def call(self, **kwargs):
            if not kwargs["kind"].startswith("v15_solve_"):
                return super().call(**kwargs)
            self.calls.append(kwargs)
            public = json.loads(kwargs["user"])["task"]
            response = (json.dumps({"formulas": {c: public["formulas"][c] for c in public["editable_cells"]}})
                        if kwargs["kind"].endswith("generation") else '{"action":"keep"}')
            request = {**kwargs, "model": self.model, "service": self.service}
            receipt = {"request": request, "request_hash": digest(request), "response": response,
                       "ok": True, "finish_reason": "stop", "http_attempt_count": 1}
            write_immutable_json(self.root / "calls" / (receipt["request_hash"] + ".json"), receipt)
            return receipt

    api = NativeAPI(tmp_path)
    solved = v.runtime.solve(adapter, api, "", root=tmp_path, key="h0", phase="development")
    hashes = solved["request_hashes"]
    feedback = e.project_development_feedback(solved,
        [v.research._read(tmp_path / "runtime/stages" / (h + ".json")) for h in hashes],
        api_receipts=[json.loads((api.root / "calls" / (h + ".json")).read_text()) for h in hashes],
        executions={i: v.research._read(tmp_path / "runtime/executions" / (i + ".json")) for i in solved["execution_ids"]})
    assert feedback["final_execution"]["score"]["oracle_available"]
    api.raw = json.dumps({"inputs": v.tasks.canonical_inputs(adapter)})
    searched = v.search(api, adapter, v.initial_state(), root=tmp_path, key="s")
    assessed = v.assess(adapter, solved["artifact"], searched, root=tmp_path, key="a")
    assert assessed["native_evaluations"] == 1
    api.raw = None
    development = seal({"phase": "development", "public_tasks": [v.tasks.public_task(adapter)],
        "observations": [{"role": role, "artifact": solved["artifact"], "feedback": feedback}
                         for role in ("no_skill", "current")], "probes": [assessed, assessed]})
    proposed = v.propose(api, v.initial_state(), [development], arm="adaptive", root=tmp_path, key="p")
    assert proposed["valid"] and len(api.calls) == 4
    sent = json.loads(api.calls[-1]["user"])
    assert sent["development_evidence"] == [development]
    assert '"reference_artifact":' not in api.calls[-1]["user"]
