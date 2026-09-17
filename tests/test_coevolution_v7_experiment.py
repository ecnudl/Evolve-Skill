"""Offline plumbing only: fake solver knows fixtures, never efficacy evidence."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import experiment as e
from skillopt.coevolution_v7.tasks import calibration_tasks, development_tasks, final_coding_tasks, final_native_tasks
from skillopt.validator_pilot.api import digest, write_immutable_json


def patch():
    return {"changes": [{"check_id": "coding_probe", "search": "Exercise legal public boundaries and unaffected paths.",
                         "when": "Only use active task constraints.", "limits": "No safety proof from finite probes."}],
            "rationale": "Offline new strategy fixture, not a model Research finding.", "source_refs": []}


class Fake:
    model = "glm-5.3"
    service = {"max_retries": 2, "fake_transport": "v7-offline-known-fixtures"}

    def __init__(self, root, tasks, calls):
        self.root, self.tasks, self.calls = Path(root), tasks, calls

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        h = digest(request)
        path = self.root / "calls" / f"{h}.json"
        if path.exists():
            return json.loads(path.read_text())
        p = json.loads(user)
        if kind == "v7_skill":
            response = ("Preserve the active contract, enumerate changed and unchanged dependencies, test legal boundaries, "
                        "and fall back when evidence is unavailable. Replace obsolete rules only when explicitly superseded. "
                        "Do not impose source code formats on other domains. Offline candidate " + key[:12] + ".")
        elif kind == "v5_coding_generate":
            task = self.tasks[p["task"]["id"]].task
            files = task.reference_files if p["skill"] else task.files
            response = "\n".join("<<<FILE " + name + ">>>\n" + files[name] + "<<<END FILE>>>"
                                 for name in task.editable_paths)
        elif kind == "v5_coding_revision":
            response = "KEEP"
        elif kind == "v6_native_generate":
            response = json.dumps(self.tasks[p["task"]["id"]].task["reference_artifact"])
        elif kind == "v6_native_revision":
            response = "KEEP"
        elif kind == "v5_validator_probe":
            response = json.dumps({"inputs": [self.tasks[p["task"]["id"]].task.public_cases[0]["input"]]})
        else:
            raise AssertionError(kind)
        record = {"request": request, "request_hash": h, "response": response, "ok": True,
                  "returned_model": self.model, "finish_reason": "stop", "http_attempt_count": 1,
                  "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
        write_immutable_json(path, record)
        self.calls.append(record)
        return record

    def parallel(self, jobs, fn, label):
        return [fn(job) for job in jobs]

    def close(self):
        pass


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        repo = tmp_path_factory.mktemp("v7-offline-driver")
        panel = {"development": development_tasks(), "calibration": calibration_tasks(),
                 "final": final_coding_tasks() + final_native_tasks()}
        indexed = {e.identifier(a): a for tasks in panel.values() for a in tasks}
        calls = []
        sources = {"hash": digest("offline freeze")}
        mp.setattr(e.Study, "_sources", lambda _: {"fake_source": sources["hash"]})
        mp.setattr(e.research, "evolve", lambda *a, **kw: core.seal({
            "proposed_rubric": core.apply_rubric_patch(core.initial_rubric(), patch()),
            "offline_fixture_not_research": True}))
        def factory(repo, root, max_calls, workers):
            return BudgetedAPI(repo, root, max_calls, workers, api=Fake(root, indexed, calls))
        study = e.Study(repo, repo / "outputs/coevolution_v7/offline", panel=panel, histories=1, blocks=1)
        result = study.run(api_factory=factory)
        yield study, result, calls, sources


def test_complete_with_real_native_executor(completed):
    study, result, calls, _ = completed
    assert result["status"] == "complete"
    assert result["ledger"]["cached_logical_calls"] == len(calls)
    assert result["ledger"]["unresolved_reservations"] == []
    assert result["approved_deployment_scope"] == []
    assert result["final_feedback_used"] is False
    assert result["calibration_labels_in_optimizer_feedback"] is False
    assert e.read(study.root / "validator_candidate_frozen.json")["historical_fallback_used"] is False


def test_rejected_validator_still_explicit_shadow_not_active(completed):
    study, result, _, _ = completed
    assert result["validator_activation"]["activate_next_round"] is False
    assert "fewer_than_four_repeated_blocks" in result["validator_activation"]["reasons"]
    branch = e.read(study.root / "skills_frozen.json")["histories"][0]
    assert branch["selected_arm"] == "fixed"
    assert branch["shadow_is_counterfactual"]
    assert branch["candidates"]["research_shadow"] != branch["candidates"]["fixed"]


def test_final_exact_aliases_and_shared_feedback(completed):
    study, _, _, _ = completed
    rows = e.read(study.root / "final_rows.json")["rows"]
    for task in {r["task_id"] for r in rows}:
        p = {r["policy"]: r for r in rows if r["task_id"] == task}
        assert p["gated_validator_candidate"]["request_hashes"] == p["fixed_validator_candidate"]["request_hashes"]
        selected = "gated_validator_candidate" if p["gated_validator_routed"]["route"]["apply"] else "no_skill"
        assert p["gated_validator_routed"]["request_hashes"] == p[selected]["request_hashes"]
    branch = e.read(study.root / "source_next/h0.json")
    probes = branch["feedback"]
    assert {k: len(v) for k, v in probes.items()} == {"old_a": 3, "old_b": 3, "new": 3}
    fixed = e.read(study.root / "skill_proposals/h0-fixed.json")["feedback_hashes"]
    new = e.read(study.root / "skill_proposals/h0-research_shadow.json")["feedback_hashes"]
    assert set(fixed) & set(new) == {p["record_hash"] for p in probes["old_a"]}


def test_optimizer_sees_grounded_views_no_calibration_labels(completed):
    _, _, calls, _ = completed
    for call in calls:
        if call["request"]["kind"] != "v7_skill":
            continue
        user = json.loads(call["request"]["user"])
        assert user["calibration_or_final_labels_available"] is False
        assert "original_task_fixture_NOT_execution" in call["request"]["user"]
        assert "oracle_label" not in call["request"]["user"]
        assert all("evaluated_artifact" in view for view in user["development_evidence"])


def test_completed_resume_does_not_construct_api(completed):
    study, result, calls, _ = completed
    before = len(calls)

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed resume must be offline")

    assert study.run(api_factory=forbidden) == result
    assert len(calls) == before


def test_frozen_source_tamper_rejected(completed):
    study, _, _, source = completed
    before = source["hash"]
    try:
        source["hash"] = digest("tampered")
        with pytest.raises(ValueError, match="Frozen V7"):
            study.verify()
    finally:
        source["hash"] = before


def test_activation_never_from_invalid_or_unavailable_proposal():
    decision = e.validator_activation(None, None)
    assert not decision["activate_next_round"] and not decision["deployment_approval"]


def test_exact_p_required_even_if_bootstrap_support(completed):
    _, result, _, _ = completed
    summary = deepcopy(result["calibration"])
    summary["primary_gate"].update(action="Support", reasons=[])
    m = summary["comparisons"]["portfolio_vs_old_double"]["metrics"]["bad_detection"]
    m["sign_flip"]["p_two_sided"] = 0.1
    proposal = result["research"]["proposed_rubric"]
    assert not e.validator_activation(summary, proposal)["activate_next_round"]
    m["sign_flip"]["p_two_sided"] = 0.03125
    assert e.validator_activation(summary, proposal)["activate_next_round"]


def test_delivery_reminder_does_not_repair_model_output():
    class Recorder:
        def call(self, system, user, kind, key, **kwargs):
            return {"system": system, "response": "invalid prose", "user": user}
    result = e.DeliveryAPI(Recorder()).call("original", "raw user", "v5_coding_generate", "key")
    assert "DELIVERY REMINDER" in result["system"]
    assert result["response"] == "invalid prose" and result["user"] == "raw user"


def test_reject_broad_output_root(tmp_path):
    with pytest.raises(ValueError, match="separate"):
        e.Study(tmp_path, tmp_path / "outputs/coevolution_v7")


def test_invalid_fresh_research_does_not_calibrate_or_use_history(completed, tmp_path, monkeypatch):
    original, _, _, _ = completed
    study = e.Study(tmp_path, tmp_path / "outputs/coevolution_v7/invalid", panel=original.panel, histories=1, blocks=1)
    monkeypatch.setattr(e.research, "evolve", lambda *args, **kwargs: core.seal({"proposed_rubric": None, "status": "invalid"}))

    def forbidden(*args):
        raise AssertionError("Invalid fresh research cannot calibrate a made-up fallback")

    monkeypatch.setattr(study, "_calibrate", forbidden)
    packets = e.read(original.root / "research_inputs.json")["host_fixture_packets"]
    candidate, _, calibration, activation = study._research_and_screen(None, packets)
    assert candidate is None and calibration is None and not activation["activate_next_round"]
    assert e.read(study.root / "validator_candidate_frozen.json")["historical_fallback_used"] is False


def test_feedback_view_rejects_final_phase_in_optimizer(completed):
    study, _, _, _ = completed
    packet = deepcopy(e.read(study.root / "research_inputs.json")["host_fixture_packets"][0])
    packet["task_context"]["source_split"] = "final"
    packet.pop("record_hash")
    packet = core.seal(packet)
    with pytest.raises(ValueError, match="development|provenance"):
        e.optimizer_payload("", "", [packet])


def test_whole_design_budget_checked_before_any_api(completed, tmp_path, monkeypatch):
    original, _, _, _ = completed
    monkeypatch.setattr(e.Study, "_sources", lambda _: {"offline": digest("frozen")})
    study = e.Study(tmp_path, tmp_path / "outputs/coevolution_v7/too-small", panel=original.panel,
                    histories=1, blocks=1, max_calls=1)
    with pytest.raises(ValueError, match="complete predeclared design"):
        study.prepare()


@pytest.mark.parametrize("error_type,expected", [("http_status", "transport_unavailable"),
                                                   ("invalid_response", "response_unavailable")])
def test_source_binding_distinguishes_transport_and_response(completed, tmp_path, error_type, expected):
    study, _, _, _ = completed
    adapter = study.panel["development"][0]
    request_hash = digest(error_type)
    root = tmp_path / "api"
    write_immutable_json(root / "calls" / (request_hash + ".json"), {"ok": False, "error_type": error_type})

    class API:
        pass

    api = API()
    api.root = root
    solver = {"target_ok": False, "artifact_hash": digest(None), "skill_hash": digest(""),
              "request_hashes": [request_hash], "delivery_status": "unavailable"}
    assessed = adapter.evaluate(None, core.initial_rubric(), phase="development")
    result = study._bind(api, assessed, solver)
    assert all(r["details"]["reason"] == expected for r in result if r["status"] == "unknown")
