"""No API tests for V18 strict delivery, source retention and paired analysis."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v18 import core as c

PARENT = "## When\nAnswer evidence-grounded questions.\n## Procedure\nCheck the evidence.\n"


def receipt(value):
    return {"ok": True, "response": json.dumps(value)}


def grid(phase="final", histories=(1, 2), tasks=("qa1", "qa2", "code1", "code2"), arms=c.ARMS):
    return [{"phase": phase, "task_id": task, "domain": "searchqa" if task.startswith("qa") else "coding",
             "cluster_id": task, "history": history, "arm": arm, "hard": 0, "category": "semantic_failure",
             "request_hash": f"{task}-{history}-{arm}"}
            for task in tasks for history in histories for arm in arms]


def outcome(rows, task, arm, hard, history=None):
    for row in rows:
        if row["task_id"] == task and row["arm"] == arm and (history is None or row["history"] == history):
            row["hard"] = hard
            row["category"] = "api_unknown" if hard is None else "success" if hard == 1 else "semantic_failure"


def test_valid_whole_is_one_exact_skill_on_both_domains():
    text = "## Procedure\nKeep evidence conditional."
    parsed = c.parse_update(receipt({"skill": text}), PARENT, "whole")
    assert parsed["valid"] and not parsed["invalid_alias"]
    assert {c.compile_skills(parsed, PARENT, domain) for domain in c.DOMAINS} == {text}
    with pytest.raises(ValueError):
        c.compile_core(parsed, PARENT)


def test_layered_compilation_has_exact_parent_suffix_but_no_claim_of_behavior_preservation():
    parsed = c.parse_update(receipt({"core": "Use task-specific evidence.", "coding_patch": "Run public unit tests."}), PARENT, "layered")
    source = c.compile_skills(parsed, PARENT, "searchqa")
    code = c.compile_skills(parsed, PARENT, "coding")
    assert source.endswith(PARENT) and source.count(PARENT) == 1
    assert "Use task-specific evidence." in source and "Run public unit tests." not in source
    assert "Run public unit tests." in code and PARENT not in code
    assert c.compile_core(parsed, PARENT) == "Use task-specific evidence."
    assert parsed["skill"] == ""
    with pytest.raises(ValueError):
        c.compile_skills(parsed, PARENT, "secret_near_miss")
    with pytest.raises(ValueError):
        c.compile_skills(parsed, PARENT + "altered", "coding")


@pytest.mark.parametrize("mode,payload,reason", [
    ("whole", {"skill": "x", "extra": "y"}, "invalid_schema"),
    ("whole", {"skill": ""}, "skill_contract_invalid"),
    ("whole", {"skill": "  \n"}, "skill_contract_invalid"),
    ("whole", {"skill": None}, "skill_contract_invalid"),
    ("whole", {"skill": "x" * 6001}, "skill_contract_invalid"),
    ("layered", {"core": "x" * 1401, "coding_patch": "y"}, "core_contract_invalid"),
    ("layered", {"core": "x", "coding_patch": "y" * 2801}, "coding_patch_contract_invalid"),
    ("layered", {"core": "x", "coding_patch": ""}, "coding_patch_contract_invalid"),
    ("layered", {"core": "x", "coding_patch": "y", "source_adapter": "replace parent"}, "invalid_schema"),
    ("layered", {"core": "x\x00", "coding_patch": "y"}, "core_contract_invalid"),
])
def test_invalid_delivery_has_no_repair_no_truncation_and_exact_parent_alias(mode,payload,reason):
    parsed = c.parse_update(receipt(payload), PARENT, mode)
    assert parsed["valid"] is False and parsed["invalid_alias"] is True and parsed["reason"] == reason
    assert all(c.compile_skills(parsed, PARENT, domain) == PARENT for domain in c.DOMAINS)
    if mode == "layered":
        assert c.compile_core(parsed, PARENT) == PARENT


@pytest.mark.parametrize("raw", ["```json\n{\"skill\":\"x\"}\n```", '{"skill":"x","skill":"y"}',
                                '{"skill": NaN}', '{"skill":"x"} trailing'])
def test_strict_json_rejects_duplicate_keys_fences_nonfinite_and_trailing_text(raw):
    result = c.parse_update({"ok": True, "response": raw}, PARENT, "whole")
    assert result["valid"] is False and result["reason"] == "invalid_json"


def test_parse_uses_explicit_api_success_and_validates_parent():
    for value in ({"ok": False, "response": '{"skill":"x"}'}, {"ok": 1}, None):
        assert c.parse_update(value, PARENT, "whole")["reason"] == "api_unknown"
    with pytest.raises(ValueError):
        c.parse_update(receipt({"skill": "x"}), "p" * 6001, "whole")
    with pytest.raises(ValueError):
        c.parse_update(receipt({"skill": "x"}), PARENT, "undeclared_mode")
    assert c.parse_update(receipt({"skill": "x" * 6000}), PARENT, "whole")["valid"]
    parsed = c.parse_update(receipt({"core": "x" * 1400, "coding_patch": "y" * 2800}), "p" * 6000, "layered")
    assert parsed["valid"] and len(c.compile_skills(parsed, "p" * 6000, "searchqa")) > 7400


def test_analysis_is_domain_equal_not_pooled_and_keeps_unknowns():
    rows = grid(tasks=("qa1", "qa2", "qa3", "code1"))
    for task in ("qa1", "qa2", "qa3"):
        outcome(rows, task, "layered", 1)
    outcome(rows, "code1", "layered", None)
    result = c.analyze(rows, expected_tasks=["qa1", "qa2", "qa3", "code1"], expected_histories=[1, 2])
    arm = result["arms"]["layered"]
    assert arm["all_attempt_success_rate"] == .75
    assert arm["macro_success_rate"] == .5
    assert arm["by_domain"]["coding"]["attempts"] == 2
    assert arm["by_domain"]["coding"]["unknown"] == 2
    assert arm["worst_domain_success_rate"] == 0
    assert result["manifest_checked"] is True
    assert result["bootstrap"]["conditional_on_observed_histories"] is True
    assert result["statistical_safety_claim"] is False
    assert result == c.analyze(rows, expected_tasks=["qa1", "qa2", "qa3", "code1"], expected_histories=[1, 2])


def test_primary_contrasts_report_per_history_and_all_attempt_paired_counts():
    rows = grid()
    outcome(rows, "qa1", "layered", 1, history=1)
    outcome(rows, "code1", "whole", 1, history=2)
    outcome(rows, "qa2", "core_only", 1)
    result = c.analyze(rows)
    comparison = result["comparisons"]["layered_vs_whole"]
    assert comparison["paired"] == {"wins": 1, "losses": 1, "ties": 6, "total": 8,
        "unknown_pairs": 0, "same_request_alias_pairs": 0, "delta": 0, "loss_rate": .125,
        "anchor_successes": 1, "loss_rate_given_anchor_success": 1}
    assert comparison["by_history"]["1"]["macro_delta"] == .25
    assert comparison["by_history"]["2"]["macro_delta"] == -.25
    assert result["comparisons"]["core_only_vs_parent"]["paired"]["wins"] == 2


def test_question_alias_clusters_are_resampled_together_not_as_independent_tasks():
    rows = grid(tasks=("qa1", "qa2", "code1"))
    for row in rows:
        if row["domain"] == "searchqa":
            row["cluster_id"] = "same-original-question"
    outcome(rows, "qa1", "layered", 1)
    result = c.analyze(rows)
    assert result["arms"]["layered"]["by_domain"]["searchqa"]["clusters"] == 1
    # With only one question-cluster in each domain, bootstrap cannot invent
    # independent variation between the two question aliases.
    contrast = result["comparisons"]["layered_vs_whole"]
    assert contrast["by_domain"]["searchqa"]["ci95"] == [.5, .5]
    assert contrast["macro_delta_ci95"] == [.25, .25]


def test_cached_aliases_remain_descriptive_positions_not_independent_requests():
    rows = grid()
    parent_hashes = {(row["task_id"],row["history"]): row["request_hash"] for row in rows if row["arm"] == "parent"}
    for row in rows:
        if row["arm"] == "core_only":
            row["request_hash"] = parent_hashes[row["task_id"],row["history"]]
    result = c.analyze(rows)
    assert result["unique_request_hashes"] == len(rows) - 8
    assert result["comparisons"]["core_only_vs_parent"]["paired"]["same_request_alias_pairs"] == 8
    changed = deepcopy(rows)
    outcome(changed,"qa1","core_only",1)
    with pytest.raises(ValueError,match="conflicting"):
        c.analyze(changed)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong_phase", "bool_hard", "changed_cluster"])
def test_closed_grid_rejects_omission_duplication_relabeling_and_wrong_types(fault):
    rows = grid()
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif fault == "wrong_phase":
        rows[0]["phase"] = "confirmation"
    elif fault == "bool_hard":
        rows[0]["hard"] = True
    else:
        rows[0]["cluster_id"] = "invented"
    with pytest.raises(ValueError):
        c.analyze(rows)


def test_frozen_manifests_detect_entirely_missing_task_or_history():
    rows = grid(histories=(1,))
    with pytest.raises(ValueError,match="history manifest"):
        c.analyze(rows, expected_histories=[1, 2])
    with pytest.raises(ValueError,match="task manifest"):
        c.analyze(rows, expected_tasks=["qa1", "qa2", "code1", "code2", "missing"])


def test_gate_approves_domains_independently_only_after_wins_against_both_anchors():
    rows = grid(phase="confirmation",histories=(1,))
    outcome(rows,"qa1","layered",1)
    outcome(rows,"code1","parent",1)
    result = c.empirical_gate(rows,expected_histories=[1])
    assert result["domain_mapping"] == {"coding":"no_skill","searchqa":"layered"}
    assert result["approved_domains"] == ["searchqa"]
    assert result["support"]["coding"]["reason"] == "observed_loss"
    assert result["statistical_safety_claim"] is False
    assert result["final_outcomes_used_for_routing"] is False


def test_gate_blocks_unknown_and_ties_but_ignores_unrelated_arm_unknown():
    rows = grid(phase="confirmation",histories=(1,))
    outcome(rows,"qa1","layered",1)
    outcome(rows,"code1","layered",1)
    outcome(rows,"qa2","no_skill",None)
    outcome(rows,"code2","whole",None)
    result = c.empirical_gate(rows)
    assert result["domain_mapping"] == {"coding":"layered","searchqa":"no_skill"}
    assert result["support"]["searchqa"]["reason"] == "unknown_confirmation_evidence"
    assert c.empirical_gate(grid(phase="confirmation",histories=(1,)))["approved_domains"] == []


def test_gate_requires_gain_against_each_reference_not_only_one():
    rows = grid(phase="confirmation",histories=(1,))
    outcome(rows,"qa1","layered",1)
    outcome(rows,"qa1","parent",1)
    result = c.empirical_gate(rows)
    assert result["support"]["searchqa"]["approved"] is False
    assert result["support"]["searchqa"]["reason"] == "insufficient_positive_evidence"


def test_gate_rejects_final_outcomes_and_cross_history_pooling():
    with pytest.raises(ValueError):
        c.empirical_gate(grid())
    with pytest.raises(ValueError):
        c.empirical_gate(grid(),phase="final")
    with pytest.raises(ValueError,match="one history"):
        c.empirical_gate(grid(phase="confirmation"))
    rows = grid(phase="confirmation",histories=(1,),arms=("no_skill","parent","whole"))
    outcome(rows,"code1","whole",1)
    assert c.empirical_gate(rows,candidate_arm="whole")["domain_mapping"]["coding"] == "whole"


def test_frozen_deployment_replay_accepts_explicitly_declared_derived_arms():
    arms = ("no_skill", "gated_whole", "gated_core_only", "gated_layered")
    rows = grid(arms=arms)
    outcome(rows, "qa1", "gated_layered", 1)
    result = c.analyze(rows, expected_arms=arms, expected_histories=[1, 2],
                       expected_tasks=["qa1", "qa2", "code1", "code2"])
    assert set(result["arms"]) == set(arms)
    assert result["arms"]["gated_layered"]["macro_success_rate"] == .25
    assert result["comparisons"]["gated_layered_vs_no_skill"]["paired"]["wins"] == 2
    assert result["primary_contrasts"] == []
    assert result["manifest_checked"] is True
    with pytest.raises(ValueError):
        c.analyze(rows)
    with pytest.raises(ValueError):
        c.analyze(rows, expected_arms=None)


def test_custom_analysis_arms_do_not_expand_confirmation_gate_candidate_authority():
    rows = grid(phase="confirmation", histories=(1,), arms=("no_skill", "parent", "gated_layered"))
    with pytest.raises(ValueError):
        c.empirical_gate(rows, candidate_arm="gated_layered")
