"""Authored receipts only; handoff checks never run Docker or an API."""
from copy import deepcopy

import pytest

from scripts.native_handoff import check_kor_native_handoff as check

IMAGE = "sha256:" + "a" * 64


def native(status="pass"):
    return {"status": status, "cleanup_confirmed": True, "runtime_image_id": IMAGE,
            "execution_costs": {"container_calls": 1, "image_id": IMAGE}}


@pytest.mark.parametrize("status", ["pass", "fail", "unknown"])
def test_executed_known_or_unknown_requires_identical_cleanup_proof(status):
    row = native(status)
    before = deepcopy(row)
    assert check(row, {"status": "available"}, IMAGE) == "native_execution_cleanup_confirmed"
    assert row == before


def test_delivery_unknown_never_assumed_semantic_failure_or_container():
    row = {"status": "unknown", "reason": "model_response_truncated"}
    assert check(row, deepcopy(row), IMAGE) == "delivery_unknown_no_container"


def test_explicit_preflight_zero_container_unknown_is_allowed():
    row = {"status": "unknown", "execution_costs": {"container_calls": 0, "wall_seconds": 0.0}}
    assert check(row, {"status": "available"}, IMAGE) == "pre_execution_unknown_no_container"


@pytest.mark.parametrize("field,value", [
    ("cleanup_confirmed", None), ("cleanup_confirmed", False), ("cleanup_confirmed", 1),
    ("runtime_image_id", "wrong"), ("image_id", "wrong"), ("image_id", None),
    ("container_calls", True), ("container_calls", False), ("container_calls", 1.0),
    ("container_calls", "1"), ("container_calls", -1), ("container_calls", 2),
])
def test_missing_mismatched_or_untyped_proof_blocks(field, value):
    row = native("unknown")
    target = row["execution_costs"] if field in {"image_id", "container_calls"} else row
    target[field] = value
    row["reason"] = "native_timeout"  # A plausible reason is not proof of cleanup.
    with pytest.raises(ValueError):
        check(row, {"status": "available"}, IMAGE)


@pytest.mark.parametrize("row", [
    {"status": "unknown", "reason": "native_timeout"},
    {"status": "pass", "execution_costs": {"container_calls": 0}},
    {"status": "unknown", "execution_costs": {"container_calls": 0, "image_id": IMAGE}},
    {"status": "unknown", "execution_costs": {"container_calls": 0}, "cleanup_confirmed": False},
    {"status": "unknown", "execution_costs": None},
    {"status": "unknown", "execution_costs": []},
])
def test_no_inference_of_missing_execution_evidence(row):
    with pytest.raises(ValueError):
        check(row, {"status": "available"}, IMAGE)


@pytest.mark.parametrize("change", ["reason", "costs", "cleanup", "image", "status", "missing_reason"])
def test_delivery_unknown_contradictions_stop(change):
    row = {"status": "unknown", "reason": "model_response_truncated"}
    pred = deepcopy(row)
    if change == "reason":
        row["reason"] = "another_reason"
    elif change == "costs":
        row["execution_costs"] = {"container_calls": 1}
    elif change == "cleanup":
        row["cleanup_confirmed"] = True
    elif change == "image":
        row["runtime_image_id"] = IMAGE
    elif change == "status":
        row["status"] = "pass"
    else:
        pred.pop("reason")
    with pytest.raises(ValueError):
        check(row, pred, IMAGE)


@pytest.mark.parametrize("row,pred,image", [(None, {}, IMAGE), ({}, [], IMAGE), ({}, {}, 1)])
def test_invalid_outer_types_stop(row, pred, image):
    with pytest.raises(ValueError):
        check(row, pred, image)


@pytest.mark.parametrize("row,pred", [({"status": []}, {"status": "available"}),
                                     ({"status": "unknown"}, {"status": []}),
                                     ({"status": True}, {"status": "available"})])
def test_status_types_fail_closed(row, pred):
    with pytest.raises(ValueError):
        check(row, pred, IMAGE)
