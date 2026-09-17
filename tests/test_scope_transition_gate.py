"""Pure transition semantics; no real artifacts, provider configuration or API."""

import json
from copy import deepcopy

import pytest

from skillopt.cross_domain.gate import decide_scope
from skillopt.scope_evolution_v2.scope_gate import content_sha256, decide_transition

CONTENT = "Verify all requested relations without overriding explicit exceptions."
VERSION = "skill-content-v1"
POLICY_HASH = content_sha256("unchanged source execution and routing branch")
CONFIG = {"source_domains": ["coding"]}


def _contract(**changes):
    result = {"status": "committed", "version": VERSION, "content_sha256": content_sha256(CONTENT),
              "source_domains": ["coding"], "source_policy_sha256": POLICY_HASH,
              "evidence_sha256": content_sha256("reference to trusted prior source evidence")}
    result.update(changes)
    return result


def _cell(domain, group, outcomes, mechanism="verification"):
    return [{"id": f"{domain}-{group}-{mechanism}-{i}", "domain": domain, "group": group,
             "mechanism": mechanism, "baseline": b, "current": c, "candidate": s}
            for i, (b, c, s) in enumerate(outcomes)]


def _evidence(*, update=False):
    result = []
    for domain in ("coding", "spreadsheet"):
        result += _cell(domain, "positive", [(1, 1, 1)] * 100 +
                        [(0, int(domain == "coding" and not update), 1)] * 100)
        result += _cell(domain, "near_miss", [(1, 1, 1)] * 200)
        result += _cell(domain, "unrelated", [(1, 1, 1)] * 200)
    return result


def _identity(row, **changes):
    row["candidate_is_current"] = True
    for prefix in ("candidate", "current"):
        row[f"{prefix}_content_sha256"] = content_sha256(CONTENT)
        row[f"{prefix}_version"] = VERSION
        row[f"{prefix}_source_policy_sha256"] = POLICY_HASH
    row.update(changes)
    return row


def _run(rows, **kwargs):
    arguments = {"transition": "scope_expansion", "current_content": CONTENT, "candidate_content": CONTENT,
                 "current_version": VERSION, "committed_source": _contract(), "config": CONFIG}
    arguments.update(kwargs)
    return decide_transition(rows, **arguments)


def _audit(result, domain, group):
    return next(a for a in result["group_audits"] if a["domain"] == domain and a["group"] == group)


def test_v1_reproduces_local_tie_block_even_with_bare_prior_flag():
    result = decide_scope(_evidence(), {**CONFIG, "local_already_committed": True})
    assert result["action"] == "pending"
    assert not result["local_accepted"]
    local = _audit(result, "coding", "positive")
    assert local["comparisons"]["baseline"]["checks"]["gain"] == "pass"
    assert local["comparisons"]["current"]["checks"]["gain"] != "pass"


def test_unchanged_source_tie_needs_preservation_not_second_positive_gain():
    result = _run(_evidence())
    assert result["action"] == "cross_domain_commit"
    local = _audit(result, "coding", "positive")
    assert local["required_gain_references"] == ["baseline"]
    assert local["comparisons"]["current"]["checks"]["gain"] != "pass"
    assert local["comparisons"]["current"]["checks"]["safety"] == "pass"
    assert not local["comparisons"]["current"]["structural_identity"]
    assert _audit(result, "spreadsheet", "positive")["required_gain_references"] == ["baseline", "current"]


def test_content_update_preserves_original_dual_reference_requirement():
    result = _run(_evidence(update=True), transition="content_update", committed_source=None,
                  candidate_content=CONTENT + " New content.")
    old = decide_scope(_evidence(update=True), CONFIG)
    assert result["action"] == old["action"] == "cross_domain_commit"
    assert result["group_audits"] == old["group_audits"]
    tied = _run(_evidence(), transition="content_update", committed_source=None,
                candidate_content=CONTENT + " New content.")
    assert tied["action"] == "pending"
    assert not tied["local_accepted"]


@pytest.mark.parametrize("transition", ["content_update", "scope_expansion"])
def test_bare_prior_flag_is_never_a_transition_certificate(transition):
    with pytest.raises(ValueError, match="Bare local_already_committed"):
        _run(_evidence(), transition=transition, config={**CONFIG, "local_already_committed": True})


def test_content_update_cannot_borrow_scope_contract_or_identity():
    with pytest.raises(ValueError, match="cannot bypass"):
        _run(_evidence(update=True), transition="content_update")
    rows = _evidence(update=True)
    _identity(rows[0])
    with pytest.raises(ValueError, match="content_update"):
        _run(rows, transition="content_update", committed_source=None)


@pytest.mark.parametrize("changed", [CONTENT + " ", "changed", ""])
def test_changed_content_cannot_impersonate_scope_expansion(changed):
    with pytest.raises(ValueError, match="unchanged"):
        _run(_evidence(), candidate_content=changed)


@pytest.mark.parametrize("contract", [None, {}, _contract(status="pending"), _contract(version="v0"),
                                     _contract(content_sha256=content_sha256("another skill")),
                                     _contract(evidence_sha256="unverified"), _contract(source_policy_sha256="short"),
                                     _contract(source_domains=[]), _contract(source_domains=["coding", "coding"]),
                                     _contract(source_domains=["spreadsheet"])])
def test_missing_or_mismatched_commit_contract_fails_closed(contract):
    with pytest.raises(ValueError):
        _run(_evidence(), committed_source=contract)


def test_config_can_inherit_but_not_rewrite_committed_source_domains():
    assert _run(_evidence(), config={})["cross_domain_accepted"]
    with pytest.raises(ValueError, match="source domains"):
        _run(_evidence(), config={"source_domains": ["spreadsheet"]})


def test_source_group_cannot_smuggle_an_uncommitted_domain_into_local_role():
    rows = _evidence() + _cell("research", "source", [(1, 1, 1)] * 200)
    with pytest.raises(ValueError, match="absent from the committed scope"):
        _run(rows)


def test_no_source_rows_cannot_reuse_prior_gain_without_fresh_evidence():
    result = _run([r for r in _evidence() if r["domain"] != "coding"])
    assert not result["local_accepted"] and not result["cross_domain_accepted"]
    assert result["action"] == "pending"
    assert {"group": "source", "domain": "coding", "mechanism": "*"} in result["missing_cells"]


def test_every_previously_committed_source_domain_needs_fresh_local_evidence():
    result = _run(_evidence(), committed_source=_contract(source_domains=["coding", "research"]),
                  config={"source_domains": ["coding", "research"]})
    assert not result["local_accepted"]
    assert {"group": "source", "domain": "research", "mechanism": "*"} in result["missing_cells"]


def test_prior_contract_does_not_waive_fresh_source_gain_against_base():
    rows = _evidence()
    for row in rows:
        if row["domain"] == "coding":
            row["baseline"] = row["current"] = row["candidate"] = 1
            _identity(row)
    result = _run(rows)
    assert not result["local_accepted"]
    assert result["action"] == "pending"


def test_cross_domain_gain_must_still_beat_current_not_just_base():
    rows = _evidence()
    for row in rows:
        if row["domain"] == "spreadsheet" and row["group"] == "positive":
            row["current"] = row["candidate"]
    result = _run(rows)
    assert result["action"] == "keep_current_scope"
    assert result["local_accepted"] and not result["cross_domain_accepted"]


@pytest.mark.parametrize("domain", ["coding", "spreadsheet"])
def test_missing_protective_cells_block_expansion(domain):
    result = _run([r for r in _evidence() if not (r["domain"] == domain and r["group"] == "unrelated")])
    assert not result["cross_domain_accepted"]
    assert any(m["domain"] == domain and m["group"] == "unrelated" for m in result["missing_cells"])
    if domain == "coding":
        assert not result["local_accepted"]


def test_preregistered_missing_mechanism_cell_is_not_hidden_by_existing_domain():
    result = _run(_evidence(), config={**CONFIG, "expected_cells": [
        {"domain": "spreadsheet", "group": "near_miss", "mechanism": "another_mechanism"}]})
    assert result["action"] == "keep_current_scope"
    assert result["missing_cells"]


@pytest.mark.parametrize("outcomes", [[(1, 1, 0)] * 200, [(0, 1, 0)] * 200])
def test_source_protective_harm_cannot_be_bypassed(outcomes):
    rows = _evidence() + _cell("coding", "unrelated", outcomes, "harmful")
    result = _run(rows)
    assert result["action"] == "reject"
    assert not result["local_accepted"]
    assert "source_scope_harm_detected" in result["reason_codes"]


def test_cross_domain_harm_restricts_without_recommitting_source_content():
    rows = _evidence() + _cell("spreadsheet", "near_miss", [(1, 1, 0)] * 200, "harmful")
    result = _run(rows)
    assert result["action"] == "restrict"
    assert result["local_accepted"] and not result["cross_domain_accepted"]


def _tiny_source_protection():
    rows = [r for r in _evidence() if not (r["domain"] == "coding" and r["group"] == "near_miss")]
    tiny = _cell("coding", "near_miss", [(1, 1, 1)] * 2)
    for row in tiny:
        # Trusted identity against Base, but this alone cannot imply Current
        # identity: that needs its own committed execution contract.
        row["candidate_is_baseline"] = True
        row["applied"] = False
    return rows + tiny, tiny


def test_verified_current_identity_can_preserve_small_source_cell():
    rows, tiny = _tiny_source_protection()
    for row in tiny:
        _identity(row, candidate_applied=False, current_applied=False)
    result = _run(rows)
    assert result["action"] == "cross_domain_commit"
    comparison = _audit(result, "coding", "nearmiss")["comparisons"]["current"]
    assert comparison["structural_identity"]
    assert comparison["delta_interval"] == comparison["conditional_harm_interval"] == [0, 0]
    assert comparison["checks"]["gain"] != "pass"


def test_equal_scores_without_explicit_identity_do_not_prove_safety():
    rows, _ = _tiny_source_protection()
    result = _run(rows)
    comparison = _audit(result, "coding", "nearmiss")["comparisons"]["current"]
    assert not comparison["structural_identity"]
    assert comparison["conditional_harm_interval"][1] > 0.1
    assert comparison["checks"]["safety"] == "pending"
    assert not result["cross_domain_accepted"]


@pytest.mark.parametrize("field,value", [
    ("candidate_content_sha256", content_sha256("other")), ("current_content_sha256", content_sha256("other")),
    ("candidate_version", "v0"), ("current_version", "v0"),
    ("candidate_source_policy_sha256", content_sha256("other")),
    ("current_source_policy_sha256", content_sha256("other")),
    ("candidate", 0), ("candidate_applied", True), ("current_applied", "false"),
    ("candidate_is_current", "true"),
])
def test_identity_contract_checks_each_hash_version_score_and_application(field, value):
    rows, tiny = _tiny_source_protection()
    _identity(tiny[0], candidate_applied=False, current_applied=False)
    tiny[0][field] = value
    with pytest.raises(ValueError):
        _run(rows)


def test_identity_application_metadata_must_not_be_one_sided():
    rows, tiny = _tiny_source_protection()
    _identity(tiny[0], current_applied=False)
    with pytest.raises(ValueError, match="application"):
        _run(rows)


def test_identity_marker_without_row_provenance_is_not_enough():
    rows, tiny = _tiny_source_protection()
    tiny[0]["candidate_is_current"] = True
    with pytest.raises(ValueError, match="content hashes"):
        _run(rows)


def test_current_identity_cannot_be_claimed_outside_committed_source_scope():
    rows = _evidence()
    _identity(next(r for r in rows if r["domain"] == "spreadsheet"))
    with pytest.raises(ValueError, match="only inside"):
        _run(rows)


def test_current_identity_does_not_waive_baseline_harm():
    # Same current/candidate execution can already harm Base. Its prior commit
    # is not a blanket exemption for newly observed source counterexamples.
    rows = _evidence() + _cell("coding", "unrelated", [(1, 0, 0)] * 200, "already_harmful")
    for row in rows:
        if row["mechanism"] == "already_harmful":
            _identity(row)
    result = _run(rows)
    assert result["action"] == "reject"
    audit = next(a for a in result["group_audits"] if a["mechanism"] == "already_harmful")
    assert audit["comparisons"]["current"]["checks"]["safety"] == "pass"
    assert audit["comparisons"]["baseline"]["checks"]["safety"] == "fail"


def test_only_partially_identical_cell_does_not_gain_structural_exemption():
    rows, tiny = _tiny_source_protection()
    _identity(tiny[0])
    result = _run(rows)
    assert not _audit(result, "coding", "nearmiss")["comparisons"]["current"]["structural_identity"]
    assert not result["cross_domain_accepted"]


def test_input_immutability_json_serialization_and_empty_evidence_fail_closed():
    rows, config, contract = _evidence(), deepcopy(CONFIG), _contract()
    before = deepcopy((rows, config, contract))
    result = _run(iter(rows), config=config, committed_source=contract)
    assert (rows, config, contract) == before
    assert json.loads(json.dumps(result, allow_nan=False))["cross_domain_accepted"]
    empty = _run([])
    assert empty["action"] == "pending" and not empty["cross_domain_accepted"]
    json.dumps(empty, allow_nan=False)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), None, "1", 0.5])
def test_invalid_observations_fail_closed(score):
    rows = _evidence()
    rows[0]["candidate"] = score
    with pytest.raises(ValueError, match="binary"):
        _run(rows)


def test_duplicate_ids_and_unknown_transition_fail_closed():
    rows = _evidence()
    with pytest.raises(ValueError, match="Duplicate"):
        _run(rows + [rows[0]])
    with pytest.raises(ValueError, match="transition"):
        _run(rows, transition="scope_only_if_helpful")
