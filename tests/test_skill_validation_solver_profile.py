"""Offline reliability configuration and real budget/cache implementation tests."""
import pytest

from skillopt.skill_validation.curriculum_study import CurriculumCalls
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.skill_validation.solver_profile import SolverProfile
from tests.test_skill_validation_single_round import FakeAPI


def test_legacy_has_no_new_model_options_or_widened_budgets():
    profile = SolverProfile.named()
    assert not profile.enabled
    assert profile.initial_options() == profile.revision_options() == {}
    assert profile.output_token_limits() == profile.api_options() == {}
    assert profile.max_tokens == 2048


def test_reliable_defaults_are_explicit_and_frozen():
    profile = SolverProfile.named("reliable_v1")
    assert profile.max_tokens == 4096
    assert profile.initial_options() == {"max_tokens": 4096, "format_policy": "compact_json_v1"}
    assert profile.revision_options()["public_selection_policy"] == "public_nonregression_v1"
    assert profile.revision_options()["allow_clean_timeout_revision"] is True
    assert profile.to_dict()["max_revision_opportunities"] == 1
    assert profile.api_options() == {"initial_health_policy": "completed_response_v1"}
    with pytest.raises(AttributeError):
        profile.max_tokens = 8000


@pytest.mark.parametrize("name,cap", [("unknown", None), (True, None), ([], None),
    ("legacy", 4096), ("reliable_v1", True), ("reliable_v1", 4096.0), ("reliable_v1", 0),
    ("reliable_v1", 16001), ("reliable_v1", "4096")])
def test_invalid_profile_rejected(name, cap):
    with pytest.raises(ValueError):
        SolverProfile.named(name, cap)


@pytest.mark.parametrize("cls", [BoundedCalls, CurriculumCalls])
def test_explicit_solver_caps_do_not_widen_other_roles_or_repeat_requests(tmp_path, cls):
    api = FakeAPI(tmp_path, tmp_path / "api")
    limits = SolverProfile.named("reliable_v1").output_token_limits()
    calls = cls(api, tmp_path / "budget", "a" * 64, 8, output_token_limits=limits)
    limits["public-initial"] = 16000  # Caller mutation must not change the frozen ceiling.
    for kind in ("public-initial", "public-revision"):
        record = calls.call("s", "u", kind, max_tokens=4096)
        assert record == calls.call("s", "u", kind, max_tokens=4096)
        assert record["request"]["max_tokens"] == 4096
        with pytest.raises(ValueError):
            calls.call("s", "u", kind, max_tokens=4097)
    assert api.new_calls == 2
    for kind in ("same-feedback-rule-update", "single-round-verifier-proposal", "single-round-solver"):
        with pytest.raises(ValueError):
            calls.call("s", "u", kind, max_tokens=4096)
    assert api.new_calls == 2
    with pytest.raises(TypeError):
        calls.output_token_limits["public-initial"] = 16000
    assert calls.accounting()["reserved_logical_requests"] == 2


@pytest.mark.parametrize("limits", [{"updater": 4096}, {"public-initial": True},
    {"public-initial": 4096.0}, {"public-initial": 0}, {"public-revision": 16001}])
def test_invalid_budget_configuration_rejected(tmp_path, limits):
    with pytest.raises(ValueError):
        BoundedCalls(FakeAPI(tmp_path, tmp_path / "api"), tmp_path / "budget", "a" * 64, 4,
                     output_token_limits=limits)


@pytest.mark.parametrize("cap", [True, 2048.0, 0, -1, 2049, "2048"])
@pytest.mark.parametrize("cls", [BoundedCalls, CurriculumCalls])
def test_legacy_budget_rejects_bad_or_larger_cap_without_calls(tmp_path, cap, cls):
    api = FakeAPI(tmp_path, tmp_path / "api")
    calls = cls(api, tmp_path / "budget", "a" * 64, 2)
    with pytest.raises(ValueError):
        calls.call("s", "u", "public-initial", max_tokens=cap)
    assert api.new_calls == 0 and not (tmp_path / "budget/intents").exists()


def test_teacher_budget_remains_explicit_6144_only(tmp_path):
    api = FakeAPI(tmp_path, tmp_path / "api")
    calls = CurriculumCalls(api, tmp_path / "budget", "a" * 64, 4,
                            output_token_limits=SolverProfile.named("reliable_v1").output_token_limits())
    for kind in ("curriculum-spec-generic", "curriculum-spec-targeted"):
        assert calls.call("s", "u", kind, max_tokens=6144)["request"]["max_tokens"] == 6144
        with pytest.raises(ValueError):
            calls.call("s", "u", kind, max_tokens=4096)
    assert api.new_calls == 2
