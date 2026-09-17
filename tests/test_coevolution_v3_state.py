from copy import deepcopy

import pytest

from skillopt.coevolution_v3 import state as s


def candidate(text="A reusable local skill with explicit preservation requirements."):
    return {"valid": True, "content": text, "raw": text}


def evaluation(requested=(False, False), preserved=(True, True), available=True):
    cases = {**{f"r{i}": b for i, b in enumerate(requested)}, **{f"p{i}": b for i, b in enumerate(preserved)}}
    return {
        "available": available,
        "case_passes": sum(cases.values()),
        "case_total": len(cases),
        "hard": all(cases.values()),
        "case_results": cases,
        "preserved": {k: v for k, v in cases.items() if k.startswith("p")},
    }


def source(**changes):
    return {
        "id": "source",
        "repeat": 0,
        "mode": "local-update",
        "base": evaluation(),
        "working": evaluation(),
        "candidate": evaluation((True, False)),
        **changes,
    }


def gate(**changes):
    return {
        "id": "gate",
        "repeat": 0,
        "mode": "full-policy-replacement",
        "base": evaluation((True, True)),
        "approved": evaluation((True, True)),
        "candidate": evaluation((True, True)),
        **changes,
    }


def test_partial_case_improvement_can_advance_without_hard_gain():
    result = s.decide_local(candidate(), [source()])
    assert result["passed"] and result["action"] == "LocalCommit"
    assert result["evidence"]["source"]["mean_score_gain_working"] == 0.25
    assert result["evidence"]["source"]["hard_gain_working"] == 0
    assert not result["statistical_safety_certified"]


@pytest.mark.parametrize("policy", sorted(s.POLICIES))
def test_both_gates_pass_updates_both_versions(policy):
    c = candidate()
    local = s.decide_local(c, [source()])
    scope = s.decide_scope(c, local, [gate()])
    initial = s.initial_state(policy)
    result = s.advance_state(initial, c, local, scope, round_index=0)
    assert result["working_local"] == result["approved_deployed"] == c["content"]
    assert initial["working_local"] == ""
    assert result["working_scope"]["deployment_allowed"] is False
    assert result["approved_scope"]["statistical_safety_certified"] is False


@pytest.mark.parametrize("policy", sorted(s.POLICIES))
def test_unknown_scope_retains_only_decoupled_local(policy):
    c = candidate()
    local = s.decide_local(c, [source()])
    scope = s.decide_scope(c, local, [gate(candidate=evaluation((True, True), available=False))])
    result = s.advance_state(s.initial_state(policy), c, local, scope, round_index=0)
    assert result["working_local"] == ("" if policy == "coupled_evolving" else c["content"])
    assert result["approved_deployed"] == "" and result["approved_scope"] is None
    assert result["pending"][0]["candidate"]["raw"] == c["raw"]


def test_scope_only_harm_is_local_research_not_deployment():
    c = candidate()
    local = s.decide_local(c, [source()])
    scope = s.decide_scope(c, local, [gate(candidate=evaluation((False, True)))])
    result = s.advance_state(s.initial_state("decoupled_evolving"), c, local, scope, round_index=0)
    assert result["working_local"] == c["content"] and not result["approved_deployed"]
    assert result["working_scope"] == {
        "usage": "sandbox_development_only",
        "deployment_allowed": False,
        "scope_expansion_approved": False,
    }
    assert result["quarantine"][0]["restricted_scope_harm"] is True


@pytest.mark.parametrize("policy", sorted(s.POLICIES))
def test_local_harm_never_inherited_despite_scope_unknown(policy):
    c = candidate()
    bad = source(candidate=evaluation((True, True), (False, True)))
    uncertain = source(id="unavailable", candidate=evaluation(available=False))
    local = s.decide_local(c, [bad, uncertain])
    scope = s.decide_scope(c, local, [])
    assert local["action"] == "Reject" and local["reason"] == "source_preserved_regression"
    assert "local_evidence_unavailable_or_misaligned" in local["reasons"]
    result = s.advance_state(s.initial_state(policy), c, local, scope, round_index=0)
    assert not result["working_local"] and not result["approved_deployed"] and result["quarantine"]


def test_retention_disallows_requested_case_regression_even_with_source_gain():
    replay = source(id="previous", working=evaluation((True, False)), candidate=evaluation((False, False)))
    result = s.decide_local(candidate(), [source()], [replay])
    assert result["reason"] == "retained_case_regression" and not result["passed"]


def test_gain_must_be_positive_against_base_and_working():
    result = s.decide_local(candidate(), [source(base=evaluation((True, False)))])
    assert result["action"] == "Restrict" and not result["passed"]


def test_hard_net_regression_forbids_positive_case_average():
    first = source(
        id="first", base=evaluation((True, True)), working=evaluation((True, True)), candidate=evaluation((True, False))
    )
    second = source(
        id="second",
        base=evaluation((False, False, False, False)),
        working=evaluation((False, False, False, False)),
        candidate=evaluation((True, True, True, False)),
    )
    result = s.decide_local(candidate(), [first, second])
    assert "source_hard_regression_vs_working" in result["reasons"]


def test_unknown_model_search_does_not_erase_complete_scope_foundation():
    c = candidate()
    local = s.decide_local(c, [source()])
    pair = gate(
        search_unknown="invalid_json", probe_results={a: {"p": None} for a in ("base", "approved", "candidate")}
    )
    result = s.decide_scope(c, local, [pair])
    assert result["passed"] and result["evidence"]["gate"]["search_unknown"]


def test_known_probe_harm_takes_priority_over_unknown_foundation():
    c = candidate()
    local = s.decide_local(c, [source()])
    pair = gate(
        candidate=evaluation((True, True), available=False),
        probe_results={"base": {"probe": True}, "approved": {"probe": None}, "candidate": {"probe": False}},
    )
    result = s.decide_scope(c, local, [pair])
    assert result["reason"] == "known_scope_regression"
    assert "deterministic_scope_evidence_unavailable_or_misaligned" in result["reasons"]


@pytest.mark.parametrize("mutation", ["missing_preserved", "bad_case_count", "missing_case", "boolean_number"])
def test_malformed_evaluation_cannot_pass(mutation):
    pair = source()
    value = pair["candidate"]
    if mutation == "missing_preserved":
        value["preserved"] = {}
    elif mutation == "bad_case_count":
        value["case_total"] = 99
    elif mutation == "missing_case":
        value["case_results"].pop("r0")
    else:
        value["case_results"]["r0"] = 1
    assert not s.decide_local(candidate(), [pair])["passed"]


def test_duplicate_pairs_and_empty_source_fail_closed():
    assert not s.decide_local(candidate(), [source(), source()])["passed"]
    assert not s.decide_local(candidate(), [])["passed"]


def test_invalid_candidate_full_original_is_preserved_but_not_inherited():
    c = {"valid": False, "content": "", "raw": "Original invalid proposal\n" * 100}
    local = s.decide_local(c, [source()])
    scope = s.decide_scope(c, local, [gate()])
    result = s.advance_state(s.initial_state("decoupled_fixed"), c, local, scope, round_index=0)
    assert result["quarantine"][0]["candidate"]["raw"] == c["raw"]
    assert not result["working_local"]


def test_state_tamper_cross_candidate_and_repeated_round_rejected():
    c = candidate()
    local = s.decide_local(c, [source()])
    scope = s.decide_scope(c, local, [gate()])
    state = s.initial_state("decoupled_fixed")
    broken = deepcopy(state)
    broken["working_local"] = "tampered"
    with pytest.raises(ValueError):
        s.advance_state(broken, c, local, scope, round_index=0)
    with pytest.raises(ValueError):
        s.decide_scope(candidate("Different candidate"), local, [gate()])
    new = s.advance_state(state, c, local, scope, round_index=0)
    with pytest.raises(ValueError):
        s.advance_state(new, c, local, scope, round_index=0)


def test_pending_is_bounded_without_changing_execution_parent():
    state = s.initial_state("decoupled_fixed")
    for round_index in range(7):
        c = candidate(f"Candidate {round_index} has no positive source evidence")
        local = s.decide_local(c, [source(candidate=evaluation())])
        scope = s.decide_scope(c, local, [gate()])
        state = s.advance_state(state, c, local, scope, round_index=round_index)
    assert len(state["pending"]) == 4 and state["pending"][0]["round"] == 3
    assert not state["working_local"] and not state["approved_deployed"]
