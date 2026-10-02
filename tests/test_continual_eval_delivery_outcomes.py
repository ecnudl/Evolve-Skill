"""Engineering fixtures for evidence binding, not new model results."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.continual_eval.delivery_outcomes import VERSION, assess_delivery_outcome


def identity(**changes):
    return {"task_id": "fixture-task", "repeat": 0, "prediction_hash": "1" * 64,
            "original_call_record_hash": "2" * 64, "code_sha256": "3" * 64,
            "diagnostic_record_hash": "4" * 64, **changes}


def semantic(**changes):
    return {"status": "unknown", "score": None, "reason": "original_workbook_unavailable", **changes}


def native(status="execution_failed", **changes):
    return {"identity": identity(), "kind": "native_execution", "status": status,
            "completed": True, "cleanup_confirmed": True,
            "generated_lines": [17] if status == "execution_failed" else [],
            "exception_type": "AttributeError" if status == "execution_failed" else None,
            "artifact_sha256s": ["a" * 64] if status == "delivered" else [],
            "expected_artifacts": 1, **changes}


def reviewed(category="generated_program_defect", **changes):
    return {**identity(), "attribution": category,
            "finding": "Reviewed original bytes explain the matching observed failure.",
            "evidence_limit": "No repair or semantic correctness claim.",
            "generated_line": 17 if category == "generated_program_defect" else None,
            "exception_type": "AttributeError" if category == "generated_program_defect" else None, **changes}


def assess(observation=None, attribution=None, **changes):
    return assess_delivery_outcome(identity=identity(), semantic_score=semantic(),
                                   observation=observation, attribution=attribution, **changes)


def test_confirmed_program_failure_preserves_semantic_unknown_and_serializes():
    score = semantic(metrics={"original": [1, 2]})
    observation, attribution = native(), reviewed()
    originals = deepcopy((score, observation, attribution))
    row = assess_delivery_outcome(identity=identity(), semantic_score=score,
                                  observation=observation, attribution=attribution)
    assert row["version"] == VERSION
    assert row["delivery"]["outcome"] == "generated_program_failure"
    assert row["delivery"]["status"] == "not_delivered"
    assert row["semantic_score"] == score and row["semantic_score"]["score"] is None
    assert row["attribution"]["category"] == "generated_program_defect"
    assert json.loads(json.dumps(row, allow_nan=False)) == row
    assert (score, observation, attribution) == originals
    row["semantic_score"]["metrics"]["original"].append(3)
    row["observation"]["identity"]["task_id"] = "edited-result"
    row["attribution"]["evidence"]["finding"] = "edited-result"
    assert (score, observation, attribution) == originals
    assert row["original_scores_unchanged"] and not row["feedback_allowed"] and not row["is_method_effect"]


@pytest.mark.parametrize("exception", ["TypeError", "FileNotFoundError", "AttributeError", "ModuleNotFoundError", "TimeoutError"])
def test_exception_name_and_generated_frame_alone_do_not_assign_blame(exception):
    row = assess(native(exception_type=exception))
    assert row["delivery"]["outcome"] == "execution_failure_unattributed"
    assert row["attribution"]["status"] == "unresolved"
    assert row["semantic_score"]["status"] == "unknown"


@pytest.mark.parametrize("field,value", [("task_id", "other"), ("repeat", 1), ("prediction_hash", "a" * 64),
    ("original_call_record_hash", "a" * 64), ("code_sha256", "a" * 64), ("diagnostic_record_hash", "a" * 64)])
@pytest.mark.parametrize("location", ["observation", "attribution"])
def test_every_original_identity_must_match(field, value, location):
    observation, attribution = native(), reviewed()
    (observation["identity"] if location == "observation" else attribution)[field] = value
    with pytest.raises(ValueError, match="identity differs"):
        assess(observation, attribution)


@pytest.mark.parametrize("changes", [{"generated_line": 99}, {"generated_line": True},
    {"exception_type": "TypeError"}, {"finding": ""}, {"evidence_limit": ""}])
def test_reviewed_defect_requires_corresponding_failure_evidence(changes):
    with pytest.raises(ValueError):
        assess(native(), reviewed(**changes))


@pytest.mark.parametrize("field", ["completed", "cleanup_confirmed"])
def test_incomplete_native_lifecycle_does_not_establish_attribution(field):
    observation = native(**{field: False})
    assert assess(observation)["delivery"]["status"] == "unknown"
    with pytest.raises(ValueError, match="completed native failure"):
        assess(observation, reviewed())


def test_clean_missing_output_does_not_imply_program_blame_and_can_have_contract_ambiguity():
    observation = native("missing_output")
    assert assess(observation)["delivery"]["outcome"] == "missing_deliverable"
    row = assess(observation, reviewed("task_delivery_contract_ambiguity"))
    assert row["delivery"]["outcome"] == "contract_ambiguity"
    assert row["semantic_score"]["score"] is None
    with pytest.raises(ValueError, match="completed native failure"):
        assess(observation, reviewed())


@pytest.mark.parametrize("status,score", [("unknown", None), ("pass", 1.0), ("fail", 0.0)])
def test_delivered_artifact_and_semantics_are_independent(status, score):
    original = semantic(status=status, score=score, reason="frozen_reason")
    row = assess_delivery_outcome(identity=identity(), semantic_score=original, observation=native("delivered"))
    assert row["delivery"]["status"] == "delivered"
    assert row["semantic_score"] == original
    assert row["attribution"]["status"] == "unresolved"


def test_partial_artifact_set_cannot_be_reported_as_complete_delivery():
    with pytest.raises(ValueError, match="expected cases"):
        assess(native("delivered", expected_artifacts=2))
    with pytest.raises(ValueError, match="complete delivery"):
        assess(native("missing_output", artifact_sha256s=["a" * 64]))


def model_call(**changes):
    return {"identity": identity(), "kind": "model_call", "closed": True, "http_status": 200,
            "stream_complete": True, "finish_reason": "length", "transport_error": False, **changes}


@pytest.mark.parametrize("reason", ["length", "max_tokens"])
def test_completed_budget_exhaustion_is_separate_from_infrastructure_and_semantics(reason):
    row = assess(model_call(finish_reason=reason))
    assert row["delivery"]["outcome"] == "completed_model_budget_exhaustion"
    assert row["attribution"]["status"] == "confirmed"
    assert row["semantic_score"]["status"] == "unknown"


@pytest.mark.parametrize("changes", [{"closed": False}, {"http_status": 503}, {"stream_complete": False},
    {"transport_error": True}, {"finish_reason": "stop"}, {"finish_reason": None}])
def test_partial_response_or_transport_problem_is_not_completed_budget_exhaustion(changes):
    row = assess(model_call(**changes))
    assert row["delivery"]["outcome"] == "unknown"
    assert row["attribution"]["status"] == "unresolved"


@pytest.mark.parametrize("stage,hash_field", [("transport", "original_call_record_hash"),
    ("api_authorization", "original_call_record_hash"), ("container_start", "diagnostic_record_hash"),
    ("dependency_provisioning", "diagnostic_record_hash")])
def test_infrastructure_requires_a_bound_separate_evidence_record(stage, hash_field):
    observation = {"identity": identity(), "kind": "infrastructure_failure", "stage": stage,
                   "failure_confirmed": True, "evidence_record_hash": identity()[hash_field]}
    row = assess(observation)
    assert row["delivery"]["outcome"] == "infrastructure_error"
    assert row["semantic_score"]["status"] == "unknown"
    observation["evidence_record_hash"] = "f" * 64
    with pytest.raises(ValueError, match="original call or diagnostic"):
        assess(observation)


def extraction(**changes):
    return {"identity": identity(), "kind": "extraction", "literal_source_verified": True,
            "response_sha256": "5" * 64, "literal_code_sha256": "6" * 64, "literal_span": [20, 40], **changes}


def extractor_review(**changes):
    return reviewed("extractor_bug", response_sha256="5" * 64, literal_code_sha256="6" * 64,
                    literal_span=[20, 40], **changes)


def test_extractor_bug_requires_review_and_does_not_replace_original_delivery_or_score():
    observation = extraction()
    assert assess(observation)["delivery"]["outcome"] == "unknown"
    row = assess(observation, extractor_review())
    assert row["delivery"] == {"status": "unknown", "outcome": "extractor_bug",
                               "reason": "reviewed_attribution_matches_frozen_evidence"}
    assert row["identity"]["code_sha256"] == "3" * 64
    assert row["semantic_score"]["status"] == "unknown"


@pytest.mark.parametrize("changes", [{"literal_source_verified": False}, {"literal_code_sha256": "3" * 64},
    {"response_sha256": "7" * 64}, {"literal_span": [21, 40]}])
def test_extraction_attribution_requires_matching_literal_evidence(changes):
    with pytest.raises(ValueError):
        assess(extraction(**changes), extractor_review())


def test_no_evidence_remains_unknown_even_if_semantics_are_known():
    row = assess_delivery_outcome(identity=identity(), semantic_score=semantic(status="pass", score=1))
    assert row["delivery"]["status"] == "unknown"
    assert row["semantic_score"]["status"] == "pass"


def test_unavailable_code_is_valid_for_model_budget_but_not_native_attribution():
    original = identity(code_sha256=None, diagnostic_record_hash=None)
    row = assess_delivery_outcome(identity=original, semantic_score=semantic(), observation=model_call(identity=original))
    assert row["delivery"]["outcome"] == "completed_model_budget_exhaustion"
    with pytest.raises(ValueError, match="original code and diagnostic"):
        assess_delivery_outcome(identity=original, semantic_score=semantic(), observation=native(identity=original))


@pytest.mark.parametrize("score", [semantic(score=0), semantic(status="pass", score=None),
    semantic(status="fail", score=float("nan")), semantic(status="pass", score=True),
    semantic(prediction_hash="f" * 64), semantic(task_id="wrong"), semantic(repeat=True)])
def test_invalid_or_mismatched_semantic_evidence_is_rejected(score):
    with pytest.raises(ValueError):
        assess_delivery_outcome(identity=identity(), semantic_score=score)


def test_known_semantics_cannot_be_bound_to_a_missing_original_delivery():
    with pytest.raises(ValueError, match="Known semantic score conflicts"):
        assess_delivery_outcome(identity=identity(), semantic_score=semantic(status="pass", score=1),
                                observation=native(), attribution=reviewed())


@pytest.mark.parametrize("observation", [native(completed=1), model_call(closed="yes"),
    native(extra="ignored"), native(expected_artifacts=True)])
def test_malformed_evidence_does_not_silently_coerce_or_drop_fields(observation):
    with pytest.raises(ValueError):
        assess(observation)


@pytest.mark.parametrize("metrics", [{"bad": float("inf")}, {"bad": object()}])
def test_preserved_score_metadata_must_be_json_serializable(metrics):
    with pytest.raises(ValueError, match="finite JSON"):
        assess_delivery_outcome(identity=identity(), semantic_score=semantic(metrics=metrics))


def test_archived_static_audit_schema_is_accepted_without_rewriting_scores():
    # Schema interoperability only: real record/byte verification is the replay
    # caller's responsibility, and these normalized observations are fixtures.
    path = Path(__file__).resolve().parents[1] / "docs/results/unknown-sheet-delivery-attribution-20261002.json"
    archive = json.loads(path.read_text())
    original = deepcopy(archive)
    outcomes = []
    for attribution in archive["rows"]:
        bound = {key: attribution[key] for key in identity()}
        failed = attribution["attribution"] == "generated_program_defect"
        observation = native("execution_failed" if failed else "missing_output", identity=bound,
                             exception_type=attribution["exception_type"],
                             generated_lines=[attribution["generated_line"]] if failed else [])
        result = assess_delivery_outcome(identity=bound, semantic_score=semantic(),
                                         observation=observation, attribution=attribution)
        outcomes.append(result["delivery"]["outcome"])
        assert result["semantic_score"]["score"] is None
    assert outcomes.count("generated_program_failure") == 5
    assert outcomes.count("contract_ambiguity") == 1
    assert len({row["task_id"] for row in archive["rows"]}) == 5
    assert archive == original
