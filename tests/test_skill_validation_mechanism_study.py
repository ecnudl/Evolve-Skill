"""Nonexecuting fixtures test the actual driver, not experimental benefits."""
import json
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import mechanism_study as study
from skillopt.skill_validation.mechanism_tasks import build_panel
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import CODE, FixtureExecutor


class StudyAPI:
    instances = []
    updater_response = "candidate"

    def __init__(self, repo, root, **kwargs):
        self.root = Path(root)
        self.model = "fixture-no-model"
        self.service = {"fixture": True, "provider": "FIXTURE"}
        self.requests, self.fresh_requests = [], []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def parallel(self, items, fn, label):
        return [fn(item) for item in items]

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.requests.append(request)
        path = self.root / "calls" / (digest(request) + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.fresh_requests.append(request)
        payload = json.loads(user)
        if kind == "public-initial":
            response = json.dumps({"solution.py": CODE})
        elif kind == "public-revision":
            response = "KEEP"
        elif kind == "same-feedback-rule-update":
            if self.updater_response != "candidate":
                response = self.updater_response
            else:
                evidence = payload["evidence_catalog"][0]["id"]
                rule = {"id": "preserve-explicit-input", "mechanism": "Constraint Preservation",
                    "procedure": ["Check explicitly preserved input before and after the change."],
                    "when": "An unchanged input is explicitly required.",
                    "exceptions": ["Do not require unchanged input when in-place mutation is required."],
                    "scope": {"required_obligation_kinds": ["input_preservation"], "forbidden_obligation_kinds": []},
                    "evidence_ids": [evidence]}
                response = json.dumps({"parent_hash": payload["parent_hash"], "edits": [
                    {"operation": "add", "rule_id": rule["id"], "rule": rule, "evidence_ids": [evidence],
                     "reason": "Fixture tests binding, not evidence support or useful learning."}]})
        else:
            raise AssertionError("Unexpected request: " + kind)
        record = {"request": request, "request_hash": digest(request), "ok": True,
                  "response": response, "fixture_only": True, "http_attempt_count": 1,
                  "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record))
        return record


class StudyExecutor(FixtureExecutor):
    transport_identity = {"kind": "nonexecuting-fixture"}


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setattr(study, "CachedAPI", StudyAPI)
    monkeypatch.setattr(StudyAPI, "instances", [])
    monkeypatch.setattr(StudyAPI, "updater_response", "candidate")
    executor, root = StudyExecutor(), tmp_path / "run"
    def invoke(**options):
        defaults = dict(workers=1, histories=1, repeats=1, development_families=1, confirmation_families=1)
        return study.run(tmp_path, root, executor, **(defaults | options))
    return invoke, root, executor


def fixture_qualification(monkeypatch):
    # This override is test-only. A normal fixture cannot pass production
    # qualification; no candidate code is executed by either mock.
    monkeypatch.setattr(study, "qualify_panel", lambda *a: seal({
        "status": "qualified", "formal_eligible": True, "fixture_override_only": True}))
    monkeypatch.setattr(study, "audit_row", lambda *a: seal({
        "status": "pass", "receipt": None, "fixture_override_only": True}))


def test_default_roster_is_complete_and_region_schema_matches():
    panel = build_panel(20260925)
    roster = study.expected_roster(panel, 3, 2)
    assert len(panel["development"]) == 30 and len(panel["confirmation"]) == 78
    assert len(roster) == 78 * 3 * 2 * 4 * 2
    result = study.summarize([], roster, bootstrap_samples=100)
    assert result["missing_positions"] == len(roster)
    assert not result["deployment_authorized"]


def test_fixture_qualification_never_becomes_method_effect(runner):
    invoke, root, _ = runner
    result = invoke()
    assert result["status"] == "pending" and result["stage"] == "qualification"
    assert not result["method_effect_evaluated"]
    assert StudyAPI.instances[-1].fresh_requests == []
    assert not (root / "frozen_panel.json").exists()


def test_prepare_has_no_model_call_and_freezes_full_panel(runner, monkeypatch):
    fixture_qualification(monkeypatch)
    invoke, root, _ = runner
    result = invoke(stop_after="prepare")
    assert result["status"] == "prepared"
    assert StudyAPI.instances[-1].fresh_requests == []
    frozen = verify(json.loads((root / "frozen_panel.json").read_text()))
    assert frozen["before_learning"] and frozen["not_verifier_calibration"]
    assert not (root / "frozen_candidates.json").exists()
    assert invoke(stop_after="prepare") == result


def test_learning_same_parent_feedback_budget_and_independent_history_calls(runner, monkeypatch):
    fixture_qualification(monkeypatch)
    invoke, root, _ = runner
    result = invoke(stop_after="learn", histories=2)
    assert result["status"] == "learned_shadow_candidates"
    api = StudyAPI.instances[-1]
    actual_initial = [r for r in api.fresh_requests if r["kind"] == "public-initial"]
    assert len(actual_initial) == 9 * 2  # 3 related role tasks + 6 controls, two histories.
    assert len({r["key"] for r in actual_initial}) == 18
    assert all(json.loads(r["user"])["optional_skill"] == "" for r in actual_initial)
    for h in ("h0", "h1"):
        updates = [verify(json.loads((root / "histories" / h / "updates" / (a + ".json")).read_text()))
                   for a in study.STRATEGIES]
        assert updates[0]["request"]["user"] == updates[1]["request"]["user"]
        assert updates[0]["update"]["parent_hash"] == updates[1]["update"]["parent_hash"]
        assert all(u["status"] == "candidate" and not u["deployment_authorized"] for u in updates)
        for update in updates:
            visible = update["request"]["user"]
            for hidden in ("hidden_audit", "host_only", "audit_outcomes", "target_related"):
                assert hidden not in visible
    assert not list(root.glob("histories/*/confirmation/*/result.json"))
    count = len(api.fresh_requests)
    assert result["accounting"]["terminal_logical_requests"] == count  # Not multiplied by two histories.
    assert invoke(stop_after="learn", histories=2) == result
    assert StudyAPI.instances[-1].fresh_requests == []


def test_complete_fixture_reports_content_vs_filtering_and_preserves_aliases(runner, monkeypatch):
    fixture_qualification(monkeypatch)
    invoke, root, executor = runner
    result = invoke()
    assert result["status"] == "completed_shadow_pilot"
    assert result["provenance"] == "engineering_fixture"
    assert not result["deployment_authorized"] and not result["cross_domain_evaluated"]
    rows = verify(json.loads((root / "confirmation_rows.json").read_text()))["rows"]
    assert len(rows) == 9 * 4 * 2
    assert all(r["skill_applied"] for r in rows if r["condition"] == "mechanism" and r["exposure"] == "raw")
    assert all(r["skill_applied"] == (r["region"] == "target_related") for r in rows
               if r["condition"] == "mechanism" and r["exposure"] == "conditional")
    assert all(not r["skill_applied"] for r in rows if r["condition"] in {"no_skill", "current"})
    calls_before = len(executor.calls)
    assert invoke() == result
    assert len(executor.calls) == calls_before and StudyAPI.instances[-1].fresh_requests == []


@pytest.mark.parametrize("response,status", [("NO_UPDATE", "no_update"), ("{broken", "invalid")])
def test_rejected_updates_keep_empty_parent_and_cannot_claim_learning(runner, monkeypatch, response, status):
    fixture_qualification(monkeypatch)
    monkeypatch.setattr(StudyAPI, "updater_response", response)
    invoke, root, _ = runner
    result = invoke()
    assert result["update_statuses"] == {"h0": {"local": status, "mechanism": status}}
    rows = verify(json.loads((root / "confirmation_rows.json").read_text()))["rows"]
    assert not any(r["skill_applied"] for r in rows)
    assert all(not arm["learning_gain_established"] for arm in result["metrics"]["arms"].values())


def test_wrong_executor_ping_stops_before_any_paid_request(runner):
    invoke, _, executor = runner
    executor.outcomes = [{"actual": False}]
    with pytest.raises(ValueError, match="preflight"):
        invoke()
    assert StudyAPI.instances[-1].fresh_requests == []


def test_unknown_confirmation_retained_not_silently_dropped(runner, monkeypatch):
    fixture_qualification(monkeypatch)
    monkeypatch.setattr(study, "audit_row", lambda *a: seal({"status": "unknown", "receipt": None}))
    invoke, _, _ = runner
    result = invoke()
    assert all(arm["counts"]["unknown"] == 9 for arm in result["metrics"]["arms"].values())


def test_changed_protocol_cannot_resume_old_output(runner, monkeypatch):
    fixture_qualification(monkeypatch)
    invoke, _, _ = runner
    invoke(stop_after="prepare")
    with pytest.raises(ValueError):
        invoke(stop_after="prepare", repeats=2)


@pytest.mark.parametrize("key,value", [("histories", 0), ("histories", True), ("repeats", 4),
    ("workers", 9), ("development_families", 0), ("confirmation_families", 33), ("seed", -1)])
def test_invalid_budgets_fail_before_api(runner, key, value):
    invoke, _, _ = runner
    with pytest.raises(ValueError):
        invoke(**{key: value})
    assert not StudyAPI.instances
