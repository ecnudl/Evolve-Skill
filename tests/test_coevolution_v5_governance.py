"""Offline synthetic controls, not evidence of actual human review or safety."""

from copy import deepcopy

import pytest

from skillopt.coevolution_v5.governance import (
    CalibrationRegistry,
    eligible_skill,
    evaluate_pairs,
    export_review_queue,
    import_reviews,
    initial_skill_state,
    promote,
    revoke_scope,
    sample_reviews,
    transition_skill,
)
from skillopt.validator_pilot.api import digest


def seal(value, name="receipt_hash"):
    copied = deepcopy(value)
    copied.pop(name, None)
    return {**copied, name: digest(copied)}


def assessment(status, *, check="coding_contract", task="task", domain="coding", kind="execution", skill="", **changes):
    value = {"check_id": check, "task_id": task, "artifact_hash": digest({"task": task, "status": status}),
             "rubric_hash": digest("V0"), "phase": "development", "domain": domain, "status": status,
             "evidence_kind": kind, "verified": True, "gate_eligible": True,
             "details": {"solver_skill_hash": digest(skill), "solver_request_hashes": [digest("synthetic solver request")]}}
    value.update(changes)
    return seal(value)


def pair(before="fail", current="fail", after="pass", *, task="task", cluster="project", domain="coding",
         current_skill="", candidate_skill="better skill"):
    primary = "coding_contract" if domain == "coding" else "qa_answer"
    result = {"task_id": task, "cluster_id": cluster, "domain": domain, "rubric_hash": digest("V0"),
              "required_check_ids": [primary], "skill_hashes": {"baseline": digest(""),
              "current": digest(current_skill), "candidate": digest(candidate_skill)}}
    for arm, status, skill in (("baseline", before, ""), ("current", current, current_skill),
                               ("candidate", after, candidate_skill)):
        core = assessment(status, task=task, domain=domain, check=primary, skill=skill)
        result[arm] = [core]
        for check in ("coding_contract", "coding_probe", "qa_answer", "qa_citation"):
            if check != primary:
                result[arm].append(seal({**core, "check_id": check, "status": "not_applicable",
                                         "gate_eligible": False, "verified": False}))
    return result


def manifest():
    return {"current_rubric_hash": digest("V0"), "artifacts": [
        {"artifact_id": f"{truth}-{cluster}", "artifact_hash": digest(f"{truth}-{cluster}"),
         "cluster_id": cluster, "task_id": "task-" + cluster, "truth": truth}
        for truth in ("good", "bad") for cluster in ("held-project-a", "held-project-b")
    ]}


def calibration(improve=False):
    return [{**artifact, "repeat": repeat,
             "outcome": "detected" if improve and artifact["truth"] == "bad" else "not_detected"}
            for artifact in manifest()["artifacts"] for repeat in range(2)]


def judgments(improve=False, *, rubric="V0"):
    """Synthetic sealed executor observations for registry protocol tests."""
    result = calibration(improve)
    for row in result:
        rows = []
        for check in ("coding_contract", "coding_probe", "qa_answer", "qa_citation"):
            relevant = check in {"coding_contract", "coding_probe"}
            status = "fail" if row["outcome"] == "detected" else "pass"
            rows.append(assessment(status if relevant else "not_applicable", check=check, task=row["task_id"],
                                   phase="promotion", artifact_hash=row["artifact_hash"], rubric_hash=digest(rubric),
                                   verified=relevant, gate_eligible=relevant,
                                   details={"task_split": "promotion", "requested_phase": "promotion"}))
        row["assessments"] = rows
    return result


def reserve(registry, **changes):
    kwargs = {"shard_id": "round0", "manifest": manifest(), "development_clusters": ["learn-project"],
              "development_artifacts": [digest("learn-code")], "final_clusters": ["audit-project"],
              "proposal_hash": digest("V1"), "round_index": 0, "final_artifacts": [digest("audit-code")]}
    kwargs.update(changes)
    return registry.reserve(**kwargs)


def commit():
    return transition_skill(initial_skill_state(), "better skill", {"source": [pair()], "replay": []},
                            [pair("pass", "pass", "pass", task="scope", cluster="scope-project")], 0)


def test_gain_requires_both_references():
    assert evaluate_pairs([pair()], True)["passed"]
    result = evaluate_pairs([pair(current="pass")], True)
    assert not result["passed"]
    assert result["gains"] == {"baseline": 1, "current": 0}


def test_scope_does_not_require_gain():
    assert evaluate_pairs([pair("pass", "pass", "pass")], False)["passed"]


@pytest.mark.parametrize("kind", ["citation_match", "model_assertion", "rubric_score", "unknown_kind"])
def test_verified_soft_assertions_cannot_approve(kind):
    p = pair()
    for arm in ("baseline", "current", "candidate"):
        p[arm][0] = seal({**p[arm][0], "evidence_kind": kind})
    result = evaluate_pairs([p], True)
    assert not result["passed"]
    assert result["unknown"]
    assert result["coverage"] == []


def test_soft_unknown_does_not_overrule_verified_hard_checks():
    p = pair()
    for arm in ("baseline", "current", "candidate"):
        p[arm][-1] = seal({**p[arm][-1], "status": "unknown", "evidence_kind": "citation_match"})
    assert evaluate_pairs([p], True)["passed"]


def test_known_harm_not_erased_by_unknown_other_reference():
    p = pair("pass", "pass", "fail")
    p["current"][0] = seal({**p["current"][0], "status": "unknown", "verified": False, "gate_eligible": False})
    result = evaluate_pairs([p], False)
    assert result["action"] == "Reject"
    assert result["unknown"] and len(result["harms"]) == 1


@pytest.mark.parametrize("status", ["unknown", "not_applicable"])
def test_candidate_cannot_abstain_away_required_check(status):
    result = evaluate_pairs([pair("pass", "pass", status)], False)
    assert not result["passed"]
    assert result["unknown"]


def test_all_inapplicable_cannot_approve():
    assert not evaluate_pairs([pair("not_applicable", "not_applicable", "not_applicable")], False)["passed"]


def test_nonapplicable_extra_check_not_penalty():
    p = pair()
    assert evaluate_pairs([p], True)["passed"]


@pytest.mark.parametrize("arm", ["baseline", "current", "candidate"])
def test_unverified_hard_evidence_blocks_approval(arm):
    p = pair()
    p[arm][0] = seal({**p[arm][0], "verified": False})
    assert not evaluate_pairs([p], True)["passed"]


def test_mismatched_rubrics_rejected():
    p = pair()
    p["candidate"][0] = seal({**p["candidate"][0], "rubric_hash": digest("changed_after_scoring")})
    with pytest.raises(ValueError, match="same frozen Rubric"):
        evaluate_pairs([p], True)


def test_tampered_receipt_rejected():
    p = pair()
    p["candidate"][0]["status"] = "fail"
    with pytest.raises(ValueError, match="integrity"):
        evaluate_pairs([p], True)


@pytest.mark.parametrize("phase", ["final", "audit", "promotion", "holdout"])
def test_non_development_evidence_cannot_train_skill(phase):
    p = pair()
    p["candidate"][0] = seal({**p["candidate"][0], "phase": phase})
    with pytest.raises(ValueError, match="Only development"):
        evaluate_pairs([p], True)


def test_duplicate_positions_and_checks_rejected():
    p = pair()
    with pytest.raises(ValueError, match="Duplicate paired"):
        evaluate_pairs([p, deepcopy(p)], False)
    p["candidate"].append(deepcopy(p["candidate"][0]))
    with pytest.raises(ValueError, match="Duplicate check"):
        evaluate_pairs([p], False)


def test_explicit_repeats_count_observations_not_clusters():
    p, repeated = pair(), pair()
    repeated["repeat"] = 1
    result = evaluate_pairs([p, repeated], True)
    assert result["gains"]["baseline"] == 2
    assert len(result["coverage"]) == 1


def test_empty_evidence_no_approval():
    assert not evaluate_pairs([], False)["passed"]


def test_state_commit_retains_explicit_finite_scope():
    state = commit()
    assert state["working"] == state["approved"] == "better skill"
    assert state["repair_parent"] is None
    assert state["last_transition"]["action"] == "ScopeCommit"
    assert eligible_skill(state, "coding", task_id="scope")["eligible"]
    assert eligible_skill(state, "coding", cluster_id="scope-project")["eligible"]
    assert eligible_skill(state, "qa", task_id="scope")["fallback"]
    assert eligible_skill(state, "coding")["fallback"]
    assert eligible_skill(state, "coding", cluster_id="unseen")["fallback"]


def test_local_commit_not_deployed_when_scope_unknown():
    state = transition_skill(initial_skill_state(), "local skill", {"source": [pair(candidate_skill="local skill")]}, [], 0)
    assert state["working"] == "local skill"
    assert state["approved"] == ""
    assert state["repair_parent"]["eligible_for_execution"] is False
    assert state["last_transition"]["action"] == "LocalCommit"


def test_replay_harm_blocks_source_gain():
    evidence = {"source": [pair(candidate_skill="harmful")],
                "replay": [pair("pass", "pass", "fail", task="old", candidate_skill="harmful")]}
    state = transition_skill(initial_skill_state(), "harmful", evidence, [pair(candidate_skill="harmful")], 0)
    assert state["working"] == state["approved"] == ""
    assert state["last_transition"]["action"] == "Reject"


def test_rejected_candidate_keeps_previous_approved():
    state = commit()
    result = transition_skill(state, "rejected", {"source": [pair("pass", "pass", "fail",
                              current_skill="better skill", candidate_skill="rejected")]},
                              [pair(current_skill="better skill", candidate_skill="rejected")], 1)
    assert result["approved"] == result["working"] == "better skill"
    assert result["repair_parent"]["candidate"] == "rejected"
    assert state["repair_parent"] is None  # caller's state is not mutated.


def test_invalid_candidate_and_backwards_round_rejected():
    with pytest.raises(ValueError, match="rounds"):
        transition_skill(commit(), "x", {"source": [pair()]}, [pair()], 0)
    with pytest.raises(ValueError, match="Candidate"):
        transition_skill(initial_skill_state(), {"content": "x", "valid": False}, {"source": [pair()]}, [pair()], 0)


def test_revocation_recomputes_harm_and_fallback():
    state = commit()
    evidence = evaluate_pairs([pair("pass", "pass", "fail", task="scope")], False)
    revoked = revoke_scope(state, "coding", evidence, "confirmed old interface regression")
    assert eligible_skill(revoked, "coding", task_id="scope")["reason"] == "revoked_scope"
    assert state["revoked_scopes"] == []
    with pytest.raises(ValueError, match="confirmed paired harm"):
        revoke_scope(state, "coding", [pair()], "model thinks harmful")


def test_tampered_state_rejected():
    state = commit()
    state["approved"] = "rogue"
    with pytest.raises(ValueError, match="integrity"):
        eligible_skill(state, "coding", task_id="scope")


def test_promotion_requires_strict_improvement():
    assert not promote(calibration(), calibration())["promote"]
    result = promote(calibration(), calibration(True))
    assert result["promote"]
    assert result["activation"] == "next_round_only"
    assert result["old"]["unique_good"] == 2
    assert result["old"]["good"] == 4


@pytest.mark.parametrize("failure", ["new_false_rejections", "new_unknowns", "lost_detections"])
def test_paired_regression_blocks_aggregate_detection_gain(failure):
    old, new = calibration(), calibration(True)
    if failure == "new_false_rejections":
        new[0]["outcome"] = "detected"
    elif failure == "new_unknowns":
        new[0]["outcome"] = "unknown"
    else:
        old[-1]["outcome"] = "detected"
        new[-1]["outcome"] = "not_detected"
    result = promote(old, new)
    assert not result["promote"]
    assert failure in result["reasons"]


def test_availability_improvement_without_regression_can_promote():
    old, new = calibration(), calibration()
    old[0]["outcome"] = "unknown"
    assert promote(old, new)["promote"]


def test_unknown_oracle_is_not_false_positive_truth_or_free_gain():
    old, new = calibration(), calibration()
    extra = {"artifact_id": "disputed", "artifact_hash": digest("disputed"), "cluster_id": "disputed",
             "truth": "unknown", "outcome": "unknown", "repeat": 0}
    old.append(extra)
    new.append({**extra, "outcome": "detected"})
    result = promote(old, new)
    assert not result["promote"]
    assert result["regressions"]["new_false_rejections"] == 0


def test_duplicate_hashes_cannot_masquerade_as_artifact_diversity():
    rows = calibration()
    for row in rows:
        if row["artifact_id"] == "good-held-project-b":
            row["artifact_hash"] = digest("good-held-project-a")
    with pytest.raises(ValueError, match="masquerade"):
        promote(rows, rows)


def test_one_project_insufficient_even_with_repeated_positions():
    old, new = calibration(), calibration(True)
    for row in old + new:
        row["cluster_id"] = "single-project"
    result = promote(old, new)
    assert not result["promote"]
    assert "insufficient_project_coverage" in result["reasons"]


def test_unpaired_positions_and_changed_truth_rejected():
    with pytest.raises(ValueError, match="matched positions"):
        promote(calibration(), calibration(True)[:-1])
    old, new = calibration(), calibration(True)
    for row in new[:2]:
        row["truth"] = "bad"
    with pytest.raises(ValueError, match="provenance"):
        promote(old, new)


def test_reserve_resume_consume_is_immutable_and_next_round(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserved = reserve(registry)
    assert reserve(registry) == reserved
    assert "truth" not in str(reserved)
    result = registry.consume("round0", judgments(), judgments(True, rubric="V1"), proposal_hash=digest("V1"), round_index=0)
    assert result["active_from_round"] == 1
    assert result["raw_labels_returned"] is False
    assert result["outcomes_recomputed_from_sealed_assessments"]
    assert registry.consume("round0", judgments(), judgments(True, rubric="V1"), proposal_hash=digest("V1"), round_index=0) == result
    with pytest.raises(ValueError, match="Immutable"):
        registry.consume("round0", judgments(), judgments(rubric="V1"), proposal_hash=digest("V1"), round_index=0)


@pytest.mark.parametrize("field,value", [
    ("development_clusters", ["held-project-a"]), ("final_clusters", ["held-project-b"]),
    ("development_artifacts", [digest("good-held-project-a")]),
    ("final_artifacts", [digest("bad-held-project-b")]),
])
def test_reservation_rejects_all_split_overlap(tmp_path, field, value):
    with pytest.raises(ValueError, match="overlap"):
        reserve(CalibrationRegistry(tmp_path), **{field: value})


def test_reservation_requires_unique_good_and_bad_controls(tmp_path):
    data = manifest()
    data["artifacts"][1]["artifact_hash"] = data["artifacts"][0]["artifact_hash"]
    with pytest.raises(ValueError, match="Duplicate"):
        reserve(CalibrationRegistry(tmp_path), manifest=data)
    with pytest.raises(ValueError, match="two unique"):
        reserve(CalibrationRegistry(tmp_path), manifest={"artifacts": manifest()["artifacts"][1:]})


def test_shard_may_not_be_reused_with_new_name_or_candidate(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    with pytest.raises(ValueError, match="already reserved"):
        reserve(registry, shard_id="another")
    with pytest.raises(ValueError, match="Immutable"):
        reserve(registry, proposal_hash=digest("V2"))


def test_consumption_requires_preexisting_reservation_and_matching_identity(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    with pytest.raises(ValueError, match="BEFORE"):
        registry.consume("round0", calibration(), calibration(True), proposal_hash=digest("V1"), round_index=0)
    reserve(registry)
    with pytest.raises(ValueError, match="pre-judgment"):
        registry.consume("round0", calibration(), calibration(True), proposal_hash=digest("V2"), round_index=0)


def test_reserved_artifacts_cannot_be_removed_after_judging(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    with pytest.raises(ValueError, match="drop reserved"):
        registry.consume("round0", calibration()[:-2], calibration(True)[:-2], proposal_hash=digest("V1"), round_index=0)


def test_predeclared_repeats_cannot_be_selected_after_judging(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    old, new = calibration(), calibration(True)
    for row in old + new:
        row["repeat"] += 10
    with pytest.raises(ValueError, match="predeclared repeat"):
        registry.consume("round0", old, new, proposal_hash=digest("V1"), round_index=0)


@pytest.mark.parametrize("repeats", [[], [0, 0], [True, 1], [-1, 0], "0,1"])
def test_invalid_repeat_preregistration_rejected(tmp_path, repeats):
    with pytest.raises(ValueError, match="repeats"):
        reserve(CalibrationRegistry(tmp_path), manifest={**manifest(), "repeats": repeats})


@pytest.mark.parametrize("phase", ["development", "audit", "final"])
def test_registry_rejects_manifest_from_wrong_split(tmp_path, phase):
    with pytest.raises(ValueError, match="promotion split"):
        reserve(CalibrationRegistry(tmp_path), manifest={**manifest(), "phase": phase})


@pytest.mark.parametrize("shard_id", ["../x", "a/b", "", ".", "a.b"])
def test_shard_path_cannot_escape_root(tmp_path, shard_id):
    with pytest.raises(ValueError, match="safe bounded"):
        reserve(CalibrationRegistry(tmp_path), shard_id=shard_id)


def review_rows():
    return [{"feedback_id": f"{domain}-{index}", "domain": domain, "disputed": index % 2 == 0,
             "policy": "hidden-policy", "candidate_hash": digest("skill"),
             "facts": [{"arm": "candidate", "observation": "verified expected/actual difference"}]}
            for domain in ("coding", "qa") for index in range(10)]


def test_sampling_deterministic_and_domain_balanced_separate_disputes():
    selected = sample_reviews(review_rows(), seed=4)
    assert selected == sample_reviews(list(reversed(review_rows())), seed=4)
    assert len(selected["random"]) == len(selected["disputed"]) == 4
    for group in ("random", "disputed"):
        assert sum(row["domain"] == "qa" for row in selected[group]) == 2
    assert not ({r["feedback_id"] for r in selected["random"]}
                & {r["feedback_id"] for r in selected["disputed"]})


def test_review_export_blinds_labels_and_does_not_claim_review_performed(tmp_path):
    queue = export_review_queue(tmp_path / "queue.json", review_rows())
    assert queue["review_performed"] is False
    for entry in queue["entries"]:
        assert "policy" not in entry["evidence"]
        assert "candidate_hash" not in entry["evidence"]
        assert "feedback_id" not in entry["evidence"]
        assert "arm" not in entry["evidence"]["facts"][0]
    assert (tmp_path / "queue.json.private.json").exists()


def human_review(queue):
    return {"queue_hash": queue["queue_hash"], "review_id": queue["entries"][0]["review_id"], "factually_supported": True,
            "applicable": True, "actionable": True, "citation_supported": None, "verdict": "accept",
            "rationale": "Synthetic test fixture; no actual human review was performed."}


def test_human_import_attestation_is_not_gate_oracle(tmp_path):
    queue = export_review_queue(tmp_path / "queue.json", review_rows())
    receipt = import_reviews(tmp_path / "human.json", queue, [human_review(queue)], reviewer_id="synthetic-test")
    assert receipt["gate_eligible"] is False
    assert receipt["trust"] == "external_human_attestation_unverified_by_software"
    assert receipt["unreviewed_count"] == len(queue["entries"]) - 1


@pytest.mark.parametrize("change", [{"review_id": "unknown"}, {"factually_supported": "yes"},
                                     {"verdict": "made-up"}, {"rationale": ""}, {"citation_supported": 1}])
def test_malformed_human_receipts_rejected(tmp_path, change):
    queue = export_review_queue(tmp_path / "queue.json", review_rows())
    with pytest.raises(ValueError):
        import_reviews(tmp_path / "human.json", queue, [{**human_review(queue), **change}], reviewer_id="synthetic-test")


def test_empty_human_reviews_cannot_be_fabricated(tmp_path):
    queue = export_review_queue(tmp_path / "queue.json", review_rows())
    with pytest.raises(ValueError, match="externally supplied"):
        import_reviews(tmp_path / "human.json", queue, [], reviewer_id="synthetic-test")


@pytest.mark.parametrize("field", ["rubric_hash", "skill_hashes", "required_check_ids"])
def test_pair_without_host_freeze_metadata_rejected(field):
    p = pair()
    p.pop(field)
    with pytest.raises(ValueError):
        evaluate_pairs([p], True)


def test_missing_check_in_all_arms_cannot_hide_coverage():
    p = pair()
    for arm in ("baseline", "current", "candidate"):
        p[arm] = [row for row in p[arm] if row["check_id"] != "coding_probe"]
    with pytest.raises(ValueError, match="every frozen check"):
        evaluate_pairs([p], True)


def test_multiple_artifacts_in_one_arm_rejected():
    p = pair()
    p["candidate"][-1] = seal({**p["candidate"][-1], "artifact_hash": digest("other artifact")})
    with pytest.raises(ValueError, match="different artifacts"):
        evaluate_pairs([p], True)


def test_supplemental_unknown_is_reported_not_safety_proof():
    p = pair()
    for arm in ("baseline", "current", "candidate"):
        p[arm][1] = seal({**p[arm][1], "status": "unknown"})
    result = evaluate_pairs([p], True)
    assert result["passed"]
    assert result["unknown"]
    assert not any(row["blocking"] for row in result["unknown"])


def test_supplemental_verified_harm_still_vetoes_core_gain():
    p = pair()
    for arm in ("baseline", "current", "candidate"):
        p[arm][1] = seal({**p[arm][1], "status": "fail" if arm == "candidate" else "pass",
                          "verified": True, "gate_eligible": True})
    result = evaluate_pairs([p], True)
    assert result["action"] == "Reject"
    assert result["gains"] == {"baseline": 1, "current": 1}


def test_supplemental_gain_cannot_replace_core_gain():
    p = pair("pass", "pass", "pass")
    for arm in ("baseline", "current", "candidate"):
        p[arm][1] = seal({**p[arm][1], "status": "pass" if arm == "candidate" else "fail",
                          "verified": True, "gate_eligible": True})
    result = evaluate_pairs([p], True)
    assert not result["passed"]
    assert result["supplemental_gains"] == {"baseline": 1, "current": 1}


def test_native_case_loss_cannot_hide_in_aggregate_failed_task():
    p = pair("fail", "fail", "fail")
    for arm in ("baseline", "current", "candidate"):
        row = p[arm][0]
        cases = [{"id": "old_preserved", "passed": arm != "candidate"},
                 {"id": "not_fixed", "passed": False}]
        p[arm][0] = seal({**row, "details": {**row["details"], "case_results": cases}})
    result = evaluate_pairs([p], False)
    assert result["action"] == "Reject"
    assert result["harms"][0]["kind"] == "verified_native_case_regression"


def test_solver_skill_provenance_cannot_be_substituted():
    p = pair()
    p["skill_hashes"]["candidate"] = digest("some unexecuted skill")
    with pytest.raises(ValueError, match="host solver Skill"):
        evaluate_pairs([p], True)
    with pytest.raises(ValueError, match="candidate and current state"):
        transition_skill(initial_skill_state(), "some unexecuted skill", {"source": [pair()]}, [], 0)


def test_arbitrary_candidate_failure_cannot_revoke_approved_skill():
    with pytest.raises(ValueError, match="current Approved Skill"):
        revoke_scope(commit(), "coding", [pair("pass", "pass", "fail", candidate_skill="unrelated bad skill")],
                     "this is not the deployed Skill")


def test_relabelled_final_details_cannot_enter_gate():
    p = pair()
    row = p["candidate"][0]
    p["candidate"][0] = seal({**row, "details": {**row["details"], "task_split": "final"}})
    with pytest.raises(ValueError, match="cannot become development"):
        evaluate_pairs([p], True)


def test_candidate_object_binding_uses_executed_content_not_metadata():
    candidate = {"content": "better skill", "valid": True, "optimizer_comment": "not a solver input"}
    state = transition_skill(initial_skill_state(), candidate, {"source": [pair()]},
                             [pair("pass", "pass", "pass", task="scope")], 0)
    assert state["approved"] == candidate


def test_human_review_cannot_reuse_ids_from_another_queue(tmp_path):
    first = export_review_queue(tmp_path / "first.json", review_rows(), seed=0)
    second = export_review_queue(tmp_path / "second.json", review_rows(), seed=1)
    assert first["entries"][0]["review_id"] == second["entries"][0]["review_id"]
    with pytest.raises(ValueError, match="exact exported queue_hash"):
        import_reviews(tmp_path / "human.json", second, [human_review(first)], reviewer_id="synthetic-test")


def test_blind_export_omits_asymmetric_reference_comparisons_but_keeps_artifact(tmp_path):
    rows = review_rows()
    for row in rows:
        row.update(artifact={"module.py": "def main(): return 1"}, comparisons=[{"reference": "baseline"}],
                   candidate={"code": "would remove asymmetrically"}, baseline={"code": "should also be absent"},
                   source_path="outputs/research_strategy/candidate")
    queue = export_review_queue(tmp_path / "queue.json", rows)
    for entry in queue["entries"]:
        evidence = entry["evidence"]
        assert evidence["artifact"] == {"module.py": "def main(): return 1"}
        assert not set(evidence) & {"candidate", "baseline", "comparisons", "source_path"}


def test_registry_cannot_promote_arbitrary_unbacked_outcome_labels(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    with pytest.raises(ValueError, match="sealed host assessments"):
        registry.consume("round0", calibration(), calibration(True), proposal_hash=digest("V1"), round_index=0)


def test_current_validator_version_bound_before_judgments(tmp_path):
    data = manifest()
    data.pop("current_rubric_hash")
    with pytest.raises(ValueError, match="predeclare current_rubric_hash"):
        reserve(CalibrationRegistry(tmp_path), manifest=data)


def test_calibration_task_id_required_in_reservation(tmp_path):
    data = manifest()
    data["artifacts"][0].pop("task_id")
    with pytest.raises(ValueError, match="original task_id"):
        reserve(CalibrationRegistry(tmp_path), manifest=data)


@pytest.mark.parametrize("field,value", [
    ("artifact_hash", digest("wrong artifact")), ("task_id", "wrong task"),
    ("rubric_hash", digest("V0")), ("domain", "qa"),
])
def test_calibration_rejects_misbound_assessment(tmp_path, field, value):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    new = judgments(True, rubric="V1")
    new[0]["assessments"][0] = seal({**new[0]["assessments"][0], field: value})
    with pytest.raises(ValueError, match="artifact/task/Rubric identity"):
        registry.consume("round0", judgments(), new, proposal_hash=digest("V1"), round_index=0)


def test_old_validator_assessments_cannot_change_after_reservation(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    with pytest.raises(ValueError, match="artifact/task/Rubric identity"):
        registry.consume("round0", judgments(rubric="different old validator"), judgments(True, rubric="V1"),
                         proposal_hash=digest("V1"), round_index=0)


def test_calibration_receipt_tampering_rejected(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    new = judgments(True, rubric="V1")
    new[0]["assessments"][0]["status"] = "fail"
    with pytest.raises(ValueError, match="integrity mismatch"):
        registry.consume("round0", judgments(), new, proposal_hash=digest("V1"), round_index=0)


@pytest.mark.parametrize("change", [{"phase": "audit"},
                                     {"details": {"task_split": "final", "requested_phase": "promotion"}},
                                     {"details": {"task_split": "promotion", "requested_phase": "final"}},
                                     {"details": {"task_split": "promotion", "requested_phase": "promotion",
                                                  "nested": {"source_phase": "final"}}}])
def test_calibration_cannot_relabel_audit_or_final_receipts(tmp_path, change):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    new = judgments(True, rubric="V1")
    new[0]["assessments"][0] = seal({**new[0]["assessments"][0], **change})
    with pytest.raises(ValueError, match="promotion"):
        registry.consume("round0", judgments(), new, proposal_hash=digest("V1"), round_index=0)


def test_calibration_soft_score_cannot_masquerade_as_execution(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    new = judgments(True, rubric="V1")
    new[0]["assessments"][0] = seal({**new[0]["assessments"][0], "evidence_kind": "citation_match"})
    with pytest.raises(ValueError, match="execution evidence"):
        registry.consume("round0", judgments(), new, proposal_hash=digest("V1"), round_index=0)


def test_calibration_outcome_recomputed_not_trusted(tmp_path):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    new = judgments(True, rubric="V1")
    new[0]["outcome"] = "detected"
    with pytest.raises(ValueError, match="disagrees"):
        registry.consume("round0", judgments(), new, proposal_hash=digest("V1"), round_index=0)


@pytest.mark.parametrize("duplicate", [False, True])
def test_calibration_check_coverage_cannot_be_dropped_or_duplicated(tmp_path, duplicate):
    registry = CalibrationRegistry(tmp_path)
    reserve(registry)
    new = judgments(True, rubric="V1")
    if duplicate:
        new[0]["assessments"][-1] = deepcopy(new[0]["assessments"][0])
    else:
        new[0]["assessments"].pop()
    with pytest.raises(ValueError, match="four sealed|complete and unique"):
        registry.consume("round0", judgments(), new, proposal_hash=digest("V1"), round_index=0)
