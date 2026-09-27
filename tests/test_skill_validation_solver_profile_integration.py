"""Reliable solver integration via fabricated API/execution receipts only.

Qualification overrides are engineering controls, not natural method evidence.
No model, SSH, Docker or candidate code is executed by these tests.
"""
import json

import pytest

from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation import curriculum_study, mechanism_study, public_revision
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.rule_solver import solve_rule_condition
from skillopt.skill_validation.solver_profile import SolverProfile
from tests import test_skill_validation_curriculum_study as curriculum_fixtures
from tests import test_skill_validation_mechanism_study as mechanism_fixtures
from tests.test_skill_validation_public_revision import REVISED, FixtureExecutor, fixture_row
from tests.test_skill_validation_rule_solver import CachedFixtureCalls, skill

PROFILE = SolverProfile.named("reliable_v1")


class ProfileCachedCalls(CachedFixtureCalls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api.service["initial_health_policy"] = PROFILE.to_dict()["initial_health_policy"]
        self.output_token_limits = PROFILE.output_token_limits()


class ProfileMechanismAPI(mechanism_fixtures.StudyAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = kwargs
        if "initial_health_policy" in kwargs:
            self.service["initial_health_policy"] = kwargs["initial_health_policy"]


class ProfileCurriculumAPI(curriculum_fixtures.FakeAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = kwargs
        if "initial_health_policy" in kwargs:
            self.service["initial_health_policy"] = kwargs["initial_health_policy"]


@pytest.fixture
def mechanism_run(monkeypatch, tmp_path):
    result = mechanism_fixtures.runner.__wrapped__(monkeypatch, tmp_path)
    monkeypatch.setattr(mechanism_study, "CachedAPI", ProfileMechanismAPI)
    mechanism_fixtures.fixture_qualification(monkeypatch)
    return result


@pytest.fixture
def curriculum_run(monkeypatch, tmp_path):
    result = curriculum_fixtures.prepared_run.__wrapped__(monkeypatch, tmp_path)
    monkeypatch.setattr(curriculum_study, "CachedAPI", ProfileCurriculumAPI)
    curriculum_fixtures.allow_fixture_control_path(monkeypatch)
    return result


def read(path):
    return verify(json.loads(path.read_text()))


def assert_uniform_records(root, profile):
    exposures = [(p, read(p)) for p in root.rglob("rule_exposure.json")]
    assert exposures
    assert any("development" in p.parts for p, _ in exposures)
    assert any("confirmation" in p.parts for p, _ in exposures)
    assert {r["condition"] for _, r in exposures} == {"no_skill", "current", "candidate"}
    for path, exposure in exposures:
        assert exposure["solver_profile"] == profile.to_dict()
        assert not exposure["deployment_authorized"] and not exposure["hidden_feedback_used"]
        records = list((path.parent / "public_initial").glob("*.json"))
        assert len(records) == 1
        initial = read(records[0])
        assert initial["max_tokens"] == profile.max_tokens
        assert initial["format_policy"] == public_revision.COMPACT_JSON_POLICY
        receipt = initial["api_receipt"]
        assert receipt["request"]["max_tokens"] == profile.max_tokens
        assert public_revision.COMPACT_JSON_POLICY in receipt["request"]["system"]
        records = list((path.parent / "public_revision").glob("*/record.json"))
        assert len(records) == 1
        revision = read(records[0])
        request = revision["request"]
        assert request["max_tokens"] == profile.max_tokens
        assert request["format_policy"] == public_revision.COMPACT_JSON_POLICY
        assert request["clean_timeout_revision_policy"] == public_revision.CLEAN_TIMEOUT_POLICY
        assert request["public_selection_policy"] == public_revision.PUBLIC_NONREGRESSION_POLICY
        if revision["api_receipt"] is not None:
            assert revision["api_receipt"]["request"]["max_tokens"] == profile.max_tokens
        assert not revision["hidden_feedback_used"] and not revision["retry_authorized"]


def assert_solver_and_learning_budgets(api, updater_kind, *, curriculum=False):
    requests = api.fresh_requests
    for kind in ("public-initial", "public-revision"):
        group = [r for r in requests if r["kind"] == kind]
        assert group and all(r["max_tokens"] == 4096 for r in group)
        assert len({r["system"] for r in group}) == 1  # All conditions share the same protocol.
        assert all(public_revision.COMPACT_JSON_POLICY in r["system"] for r in group)
    updates = [r for r in requests if r["kind"] == updater_kind]
    assert len(updates) == 2 and all(r["max_tokens"] == 2048 for r in updates)
    assert all(public_revision.COMPACT_JSON_POLICY not in r["system"] for r in updates)
    assert api.options["initial_health_policy"] == "completed_response_v1"
    if curriculum:
        planning = [r for r in requests if r["kind"] == "capability-goal-plan"]
        teachers = [r for r in requests if r["kind"].startswith("curriculum-spec-")]
        assert len(planning) == 2 and all(r["max_tokens"] == 2048 for r in planning)
        assert len(teachers) == 3 and all(r["max_tokens"] == curriculum_study.GENERATION_TOKEN_CAP for r in teachers)


def test_reliable_rule_adapter_all_conditions_same_protocol_and_exact_replay(tmp_path):
    systems = []
    for condition in ("no_skill", "current", "candidate"):
        rules = RuleSkill("h0", ()) if condition == "no_skill" else skill()
        row, calls, executor = fixture_row(), ProfileCachedCalls(), FixtureExecutor()
        root = tmp_path / condition
        result = solve_rule_condition(row, rules, condition, 0, calls, executor, root, solver_profile=PROFILE)
        assert result["exposure"]["solver_profile"] == PROFILE.to_dict()
        assert all(r["max_tokens"] == 4096 for r in calls.calls)
        assert len(calls.calls) == 2 and len(executor.calls) == 1
        systems.append([r["system"] for r in calls.calls])
        assert solve_rule_condition(row, rules, condition, 0, calls, executor, root,
                                    solver_profile=PROFILE) == result
        assert len(calls.calls) == 2 and len(executor.calls) == 1
    assert systems[0] == systems[1] == systems[2]


@pytest.mark.parametrize("replacement", [None, SolverProfile.named("reliable_v1", 8192)])
def test_rule_adapter_profile_cannot_change_without_new_output(tmp_path, replacement):
    row, rules, calls, executor = fixture_row(), skill(), ProfileCachedCalls(), FixtureExecutor()
    solve_rule_condition(row, rules, "candidate", 0, calls, executor, tmp_path, solver_profile=PROFILE)
    before = len(calls.calls), len(executor.calls)
    if replacement is not None:
        # The replacement runtime is internally valid, but cannot rebind the
        # already frozen position to a different execution budget.
        calls.output_token_limits = replacement.output_token_limits()
    with pytest.raises(ValueError, match="another rule exposure"):
        solve_rule_condition(row, rules, "candidate", 0, calls, executor, tmp_path, solver_profile=replacement)
    assert (len(calls.calls), len(executor.calls)) == before


def test_reliable_rule_adapter_retains_complete_rejected_attempt(tmp_path):
    row, rules = fixture_row(), skill()
    calls = ProfileCachedCalls(revision=json.dumps({"solution.py": REVISED}))
    executor = FixtureExecutor({"actual": True}, {"actual": False})
    result = solve_rule_condition(row, rules, "candidate", 0, calls, executor, tmp_path, solver_profile=PROFILE)
    record = result["revision"]["record"]
    assert result["artifact"] == result["initial_artifact"]
    assert record["status"] == "retained" and record["public_status"] == "pass"
    assert record["revised_artifact"] is not None and record["revised_stage"]["report"]["status"] == "fail"
    assert record["revision_opportunity_completed"] and not record["retry_authorized"]
    assert record["api_receipt"]["response"] == json.dumps({"solution.py": REVISED})
    assert len(calls.calls) == 2 and len(executor.calls) == 2


@pytest.mark.parametrize("mismatch", ["health_missing", "health_legacy", "budget_missing",
                                     "initial_budget", "revision_budget"])
def test_profile_runtime_mismatch_stops_before_any_side_effect(tmp_path, mismatch):
    row, rules, calls, executor = fixture_row(), skill(), ProfileCachedCalls(), FixtureExecutor()
    if mismatch == "health_missing":
        del calls.api.service["initial_health_policy"]
    elif mismatch == "health_legacy":
        calls.api.service["initial_health_policy"] = "legacy_success_only"
    elif mismatch == "budget_missing":
        del calls.output_token_limits
    elif mismatch == "initial_budget":
        calls.output_token_limits["public-initial"] = 2048
    else:
        calls.output_token_limits["public-revision"] = 8192
    with pytest.raises(ValueError, match="differs from|budgets differ"):
        solve_rule_condition(row, rules, "candidate", 0, calls, executor, tmp_path, solver_profile=PROFILE)
    assert not calls.calls and not executor.calls and not list(tmp_path.iterdir())


def test_mechanism_full_fixture_has_uniform_profile_budget_and_replay(mechanism_run):
    invoke, root, executor = mechanism_run
    result = invoke(solver_profile="reliable_v1")
    assert result["status"] == "completed_shadow_pilot" and result["provenance"] == "engineering_fixture"
    assert not result["deployment_authorized"]
    protocol = read(root / "protocol.json")
    assert protocol["solver_profile"] == PROFILE.to_dict() and protocol["updater_token_cap"] == 2048
    assert "solver_updater_token_cap" not in protocol
    assert_uniform_records(root, PROFILE)
    assert_solver_and_learning_budgets(ProfileMechanismAPI.instances[-1], "same-feedback-rule-update")
    before = len(executor.calls)
    assert invoke(solver_profile="reliable_v1") == result
    assert len(executor.calls) == before and not ProfileMechanismAPI.instances[-1].fresh_requests


@pytest.mark.parametrize("changed", [{"solver_profile": "legacy"},
                                    {"solver_profile": "reliable_v1", "solver_max_tokens": 8192}])
def test_mechanism_rejects_same_directory_changed_profile_before_calls(mechanism_run, changed):
    invoke, _, executor = mechanism_run
    invoke(solver_profile="reliable_v1", stop_after="prepare")
    before = len(executor.calls)
    with pytest.raises(ValueError):
        invoke(stop_after="prepare", **changed)
    assert not ProfileMechanismAPI.instances[-1].fresh_requests and len(executor.calls) == before


def test_curriculum_full_fixture_applies_profile_to_both_pools_and_confirmation(curriculum_run):
    invoke, root, _ = curriculum_run
    result = invoke(solver_profile="reliable_v1")
    assert result["status"] == "completed_shadow_pilot" and not result["deployment_authorized"]
    protocol = read(root / "protocol.json")
    assert protocol["solver_profile"] == PROFILE.to_dict() and protocol["updater_token_cap"] == 2048
    assert "solver_updater_token_cap" not in protocol
    assert_uniform_records(root, PROFILE)
    assert_solver_and_learning_budgets(ProfileCurriculumAPI.instances[-1], "conditional-rule-update", curriculum=True)
    assert invoke(solver_profile="reliable_v1") == result
    assert not ProfileCurriculumAPI.instances[-1].fresh_requests


@pytest.mark.parametrize("changed", [{"solver_profile": "legacy"},
                                    {"solver_profile": "reliable_v1", "solver_max_tokens": 8192}])
def test_curriculum_changed_profile_rejected_before_any_new_model_call(curriculum_run, changed):
    invoke, _, _ = curriculum_run
    invoke(solver_profile="reliable_v1", stop_after="prepare")
    with pytest.raises(ValueError):
        invoke(stop_after="prepare", **changed)
    assert not ProfileCurriculumAPI.instances[-1].fresh_requests
