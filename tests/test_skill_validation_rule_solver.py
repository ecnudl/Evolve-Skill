"""Rule solver fixtures reuse the historical public-revision fake transports.

These tests do not call a model or execute model-provided code.
"""
import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.rule_skill import Rule, RuleSkill
from skillopt.skill_validation.rule_solver import solve_rule_condition
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import (
    CODE, REVISED, SECRET, FixtureCalls, FixtureExecutor, fixture_row,
)


class CachedFixtureCalls(FixtureCalls):
    """Same fixture receipts with production-like content-addressed call reuse."""
    def __init__(self, initial=None, revision="KEEP", *, initial_ok=True):
        super().__init__()
        self.responses = {"public-initial": json.dumps({"solution.py": CODE}) if initial is None else initial,
                          "public-revision": revision}
        self.cache, self.initial_ok = {}, initial_ok

    def call(self, system, user, kind, *, repeat, max_tokens):
        key = digest([system, user, kind, repeat, max_tokens])
        if key not in self.cache:
            self.response = self.responses[kind]
            self.ok = self.initial_ok if kind == "public-initial" else True
            self.cache[key] = super().call(system, user, kind, repeat=repeat, max_tokens=max_tokens)
        return deepcopy(self.cache[key])


def skill(history="h0", *, preserve=False):
    scope = ScopeRule(("input_preservation",)) if preserve else ScopeRule(("requested_behavior",))
    rule = Rule("check-contract", "Constraint Preservation", ("Check the explicit public examples.",),
                "Only when the declared public obligation applies.",
                ("Do not infer unstated requirements.",), scope, (SECRET,))
    return RuleSkill(history, (rule,))


def run(tmp_path, *, rules=None, condition="candidate", exposure="conditional", outcomes=(), calls=None):
    row, calls, executor = fixture_row(), calls or CachedFixtureCalls(), FixtureExecutor(*outcomes)
    rules = skill() if rules is None else rules
    result = solve_rule_condition(row, rules, condition, 0, calls, executor, tmp_path, exposure=exposure)
    return result, row, rules, calls, executor


def test_all_conditions_share_exact_initial_and_revision_system_protocol(tmp_path):
    systems = []
    for condition in ("no_skill", "current", "candidate"):
        rules = RuleSkill("h0", ()) if condition == "no_skill" else skill()
        result, _, _, calls, executor = run(tmp_path / condition, rules=rules, condition=condition)
        assert len(calls.calls) == 2 and len(executor.calls) == 1
        systems.append([r["system"] for r in calls.calls])
        assert result["revision"]["record"]["status"] == "kept"
        assert result["record"]["shadow_only"] and not result["record"]["deployment_authorized"]
    assert systems[0] == systems[1] == systems[2]


def test_no_skill_is_actually_empty_not_filtered_nonempty(tmp_path):
    cold = RuleSkill("h0", ())
    result, _, _, calls, _ = run(tmp_path / "cold", rules=cold, condition="no_skill")
    assert all(json.loads(r["user"])["optional_skill"] == "" for r in calls.calls)
    assert result["artifact"].skill_hash == hashlib.sha256(b"").hexdigest()
    assert result["exposure"]["rule_skill_hash"] == cold.content_hash
    with pytest.raises(ValueError, match="empty rule set"):
        run(tmp_path / "filtered", rules=skill(preserve=True), condition="no_skill")


def test_near_miss_disables_advice_but_keeps_candidate_identity(tmp_path):
    result, _, rules, calls, _ = run(tmp_path, rules=skill(preserve=True))
    rendering = result["exposure"]["rendering"]
    assert rendering["selected_rule_ids"] == [] and rendering["disabled_rule_ids"] == [rules.rules[0].id]
    assert all(json.loads(r["user"])["optional_skill"] == "" for r in calls.calls)
    assert result["artifact"].condition == "candidate"
    assert result["exposure"]["rule_skill_hash"] != result["exposure"]["effective_skill_text_hash"]
    assert "syntax_only" in rendering["scope_basis"]


def test_raw_diagnostic_preserves_conditions_and_exceptions_even_if_not_matching(tmp_path):
    result, _, rules, calls, _ = run(tmp_path, rules=skill(preserve=True), exposure="raw")
    advice = json.loads(calls.calls[0]["user"])["optional_skill"]
    assert rules.rules[0].when in advice and rules.rules[0].exceptions[0] in advice
    assert result["exposure"]["rendering"]["selected_rule_ids"] == [rules.rules[0].id]
    assert result["exposure"]["rendering"]["disabled_rule_ids"] == []
    assert result["exposure"]["exposure_mode"] == "raw"


def test_replay_reuses_existing_solver_and_execution_receipts(tmp_path):
    result, row, rules, calls, executor = run(tmp_path)
    replay = solve_rule_condition(row, rules, "candidate", 0, calls, executor, tmp_path)
    assert replay == result
    assert len(calls.calls) == 2 and len(executor.calls) == 1


@pytest.mark.parametrize("change", ["history", "exposure", "condition", "repeat", "rule_scope", "evidence_ids"])
def test_position_cannot_be_rebound_even_when_rendered_text_matches(tmp_path, change):
    rules = skill(preserve=True)  # Scope does not match: several changes still produce empty text.
    _, row, rules, calls, executor = run(tmp_path, rules=rules)
    exposure, condition, repeat = "conditional", "candidate", 0
    if change == "history":
        rules = replace(rules, history_id="h1")
    elif change == "exposure":
        exposure = "raw"
    elif change == "condition":
        condition = "current"
    elif change == "repeat":
        repeat = 1
    elif change == "rule_scope":
        rules = replace(rules, rules=(replace(rules.rules[0],
                             scope=ScopeRule(("input_preservation", "requested_behavior"))),))
    else:
        rules = replace(rules, rules=(replace(rules.rules[0], evidence_ids=("other-host-evidence",)),))
    with pytest.raises(ValueError, match="bound to another"):
        solve_rule_condition(row, rules, condition, repeat, calls, executor, tmp_path, exposure=exposure)
    assert len(calls.calls) == 2 and len(executor.calls) == 1


def test_unbound_legacy_artifact_directory_cannot_be_adopted(tmp_path):
    (tmp_path / "artifacts").mkdir()
    calls, executor = CachedFixtureCalls(), FixtureExecutor()
    with pytest.raises(ValueError, match="unbound"):
        solve_rule_condition(fixture_row(), skill(), "candidate", 0, calls, executor, tmp_path)
    assert calls.calls == [] and executor.calls == []


@pytest.mark.parametrize("status", ["unsupported", "execution_error"])
def test_unknown_execution_is_not_semantic_failure_and_has_no_repair_call(tmp_path, status):
    result, row, rules, calls, executor = run(tmp_path, outcomes=({"status": status},))
    assert result["revision"]["report"]["status"] == "unknown"
    assert result["revision"]["record"]["status"] == "skipped"
    assert len(calls.calls) == 1 and len(executor.calls) == 1
    assert solve_rule_condition(row, rules, "candidate", 0, calls, executor, tmp_path) == result
    assert len(calls.calls) == len(executor.calls) == 1


def test_no_hidden_row_fields_or_host_evidence_enter_model_inputs(tmp_path):
    # fixture_row raises on any access outside the three permitted public keys.
    result, _, _, calls, _ = run(tmp_path)
    assert all(SECRET not in call["system"] + call["user"] for call in calls.calls)
    assert result["exposure"]["hidden_feedback_used"] is False
    assert result["revision"]["record"]["hidden_feedback_used"] is False


def test_actual_revised_artifact_retained_even_if_public_check_worsens(tmp_path):
    calls = CachedFixtureCalls(revision=json.dumps({"solution.py": REVISED}))
    result, _, _, calls, executor = run(tmp_path, calls=calls, outcomes=({"actual": True}, {"actual": False}))
    assert result["artifact"] != result["initial_artifact"]
    assert result["revision"]["record"]["status"] == "revised"
    assert result["revision"]["report"]["status"] == "fail"
    assert result["record"]["artifact_hash"] == result["artifact"].content_hash
    assert len(calls.calls) == 2 and len(executor.calls) == 2


@pytest.mark.parametrize("initial_ok,initial", [(False, "unused"), (True, "not parseable JSON")])
def test_bad_initial_delivery_remains_explicit_unknown(tmp_path, initial_ok, initial):
    result, _, _, calls, executor = run(tmp_path, calls=CachedFixtureCalls(initial=initial, initial_ok=initial_ok))
    assert result["artifact"].availability == ("parse_failure" if initial_ok else "api_failure")
    assert result["revision"]["record"]["public_status"] == "unknown"
    assert len(calls.calls) == 1 and executor.calls == []


@pytest.mark.parametrize("kwargs", [{"exposure": "llm-routing"}, {"condition": "approved"}, {"repeat": True}])
def test_invalid_configuration_stops_before_calls(tmp_path, kwargs):
    args = {"condition": "candidate", "repeat": 0, "exposure": "conditional", **kwargs}
    calls, executor = CachedFixtureCalls(), FixtureExecutor()
    with pytest.raises(ValueError):
        solve_rule_condition(fixture_row(), skill(), calls=calls, executor=executor, root=tmp_path, **args)
    assert calls.calls == [] and executor.calls == []
