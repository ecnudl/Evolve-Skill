"""V14 projection verifies actual synthetic runtime files, including rollback."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v13 import evidence as old
from skillopt.coevolution_v14 import evidence as e
from skillopt.coevolution_v14 import runtime
from tests.test_coevolution_v12_runtime import native, tree
from tests.test_coevolution_v14_runtime import FakeAPI


def closed(root, *, phase="development", **conditions):
    state = {"calls": 0, "receipts": [], **conditions}
    api = FakeAPI(root, state)
    solve = runtime.solve(native(split=phase), api, "synthetic-guidance", root=root, key="k", phase=phase)
    def read(path):
        return json.loads(path.read_text())
    return {"solve": solve,
        "stages": [read(root / "runtime/stages" / (h + ".json")) for h in solve["request_hashes"]],
        "api_receipts": [read(root / "api/calls" / (h + ".json")) for h in solve["request_hashes"]],
        "executions": {h: read(root / "runtime/executions" / (h + ".json")) for h in solve["execution_ids"]}}


def reseal(row):
    return seal({k: v for k, v in row.items() if k != "record_hash"})


def test_normal_projection_and_source_version_are_v14(tmp_path):
    bundle = closed(tmp_path)
    result = e.project_development_feedback(**bundle)
    verify(result)
    assert result["version"] == e.VERSION
    assert result["provenance"]["source_version"] == runtime.VERSION
    assert result["chosen_stage"] == "revision" and result["rollback_reason"] is None
    assert result["final_execution"]["score"]["semantic_success"] == 1
    assert len(result["stages"]) == 2
    with pytest.raises(ValueError, match="source version"):
        old.project_development_feedback(**bundle)


@pytest.mark.parametrize("failure,reason", [("bad_revision", "revision_delivery_invalid"), ("fail_revision", "revision_api_unknown")])
def test_rollback_projection_does_not_erase_failed_revision(tmp_path, failure, reason):
    bundle = closed(tmp_path, **{failure: True})
    result = e.project_development_feedback(**bundle)
    assert result["chosen_stage"] == "generation" and result["rollback_reason"] == reason
    assert result["final_execution"]["score"]["semantic_success"] == 1
    assert result["stages"][1]["execution"]["score"]["semantic_success"] is None
    assert result["stages"][1]["delivery_diagnostic"] is not None
    assert result["stages"][1]["execution"]["outcome_category"] == ("api_unknown" if failure == "fail_revision" else "delivery_failure")
    assert result["semantic_guard"] is False


@pytest.mark.parametrize("conditions,chosen,semantic", [({"wrong_first": True, "bad_revision": True}, "generation", 0),
    ({"wrong_revision": True}, "revision", 0), ({"bad_first": True}, "revision", None),
    ({"bad_first": True, "apply": True}, "revision", 1)])
def test_actual_chosen_score_not_optimistic_fallback(tmp_path, conditions, chosen, semantic):
    result = e.project_development_feedback(**closed(tmp_path, **conditions))
    assert result["chosen_stage"] == chosen
    assert result["final_execution"]["score"]["semantic_success"] == semantic


@pytest.mark.parametrize("phase", ["selection", "final"])
def test_non_development_never_projected(tmp_path, phase):
    bundle = closed(tmp_path, phase=phase)
    with pytest.raises(ValueError, match="development"):
        e.project_development_feedback(**bundle)


@pytest.mark.parametrize("field,value", [("chosen_stage", "revision"), ("rollback_reason", None),
                                        ("semantic_guard", True), ("artifact", None)])
def test_resealed_rollback_tampering_fails_closed(tmp_path, field, value):
    bundle = closed(tmp_path, bad_revision=True)
    bundle["solve"][field] = value
    bundle["solve"] = reseal(bundle["solve"])
    with pytest.raises(ValueError):
        e.project_development_feedback(**bundle)


def test_missing_actual_chosen_execution_is_rejected(tmp_path):
    bundle = closed(tmp_path, bad_revision=True)
    bundle["executions"].pop(bundle["solve"]["execution_ids"][2])
    with pytest.raises(ValueError):
        e.project_development_feedback(**bundle)


def test_stage_hash_or_unknown_semantic_tampering_rejected(tmp_path):
    bundle = closed(tmp_path, bad_revision=True)
    changed = deepcopy(bundle)
    changed["stages"][1]["public_score"]["semantic_success"] = 0
    changed["stages"][1] = reseal(changed["stages"][1])
    with pytest.raises(ValueError, match="unknown"):
        e.project_development_feedback(**changed)
    changed = deepcopy(bundle)
    changed["api_receipts"][1]["response"] = "repaired response"
    with pytest.raises(ValueError, match="hash"):
        e.project_development_feedback(**changed)


def test_projection_zero_execution_zero_api_zero_writes(tmp_path, monkeypatch):
    from pathlib import Path

    bundle = closed(tmp_path, bad_revision=True)
    before = tree(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("Projection performed activity beyond in-memory verification")
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(FakeAPI, "call", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    result = e.project_development_feedback(**bundle)
    assert result["api_calls"] == result["native_executions"] == 0
    assert tree(tmp_path) == before
    assert "PRIVATE_SHEET_SENTINEL" in json.dumps(result)
    assert "reference_files" not in json.dumps(result)
