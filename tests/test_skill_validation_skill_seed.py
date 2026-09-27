"""Seed provenance boundaries; local synthetic files, never live training/API."""
import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.skill_seed import (
    SOURCE_ATTESTATION_VERSION,
    cold_seed,
    import_source_seed,
    legacy_seed,
    seed_model_text,
    validate_seed,
)


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _reseal(record, **changes):
    return seal({**{key: value for key, value in record.items() if key != "record_hash"}, **changes})


def _source(tmp_path, *, final_selection=False):
    """Small fixture with the real trainer's shapes, not a real source run."""
    skill = "Consult the task contract before applying inherited advice."
    checkpoint = "skills/skill_v0001.md"
    selection = ("final_selection_eval/results.jsonl" if final_selection
                 else "steps/step_0001/selection_eval/results.jsonl")
    files = {
        "best_skill.md": skill,
        checkpoint: skill,
        "summary.json": json.dumps({"version": "skillopt-0.1.0", "total_steps": 1, "best_step": 1,
                                    "best_origin": "step_0001", "best_selection_hard": .8,
                                    "test_hard": "PRIVATE_TEST_MARKER",
                                    "config": {"diagnostic": "PRIVATE_CONFIG_MARKER"}}),
        "history.json": json.dumps([{"step": 1, "best_step": 1, "best_origin": "step_0001"}]),
        selection: json.dumps({"task_id": "source-validation-a", "result": "PRIVATE_SELECTION_MARKER"}) + "\n",
    }
    for relative, raw in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw)
    attestation = seal({"version": SOURCE_ATTESTATION_VERSION, "reviewer": "fixture-reviewer",
        "source_run_id": "fixture-only-not-a-natural-run", "source_domain": "coding",
        "selection_split": "valid_seen", "selection_basis": "best_on_source_validation",
        "no_test_or_final_selection": True, "best_step": 1, "best_origin": "step_0001",
        "selected_skill_hash": _sha(skill), "selected_checkpoint": checkpoint,
        "selection_evidence": selection, "file_hashes": {relative: _sha(raw) for relative, raw in files.items()}})
    return skill, attestation


def test_cold_is_empty_rules_and_empty_model_text():
    seed = cold_seed("history-0")
    assert seed_model_text(seed) == ""
    assert seed["structured_skill"] == RuleSkill("history-0", ()).to_dict()
    assert not seed["deployment_authorized"]
    assert not seed["skill_admission_authorized"]
    assert seed == cold_seed("history-0")
    assert seed["record_hash"] != cold_seed("history-1")["record_hash"]


@pytest.mark.parametrize("changes", [
    {"skill_text": "hidden instruction"},
    {"skill_text": " ", "skill_text_hash": _sha(" ")},
    {"structured_skill": None},
    {"deployment_authorized": True},
    {"skill_admission_authorized": True},
    {"source_attestation": {}},
    {"audit_truth": "leak"},
])
def test_cold_cannot_hide_text_evidence_or_authority(changes):
    with pytest.raises(ValueError):
        seed_model_text(_reseal(cold_seed("history-0"), **changes))


def test_legacy_retains_weak_text_and_never_parses_verified_rules():
    prose = "## Rule\nAlways obey this old policy."
    seed = legacy_seed("history-legacy", prose, source_ref="old-parent.md", source_hash=_sha(prose))
    assert seed_model_text(seed) == prose
    assert seed["mode"] == "legacy_diagnostic" and seed["structured_skill"] is None
    assert seed["source_attestation"] is None
    assert "not_authenticated" in seed["provenance_status"]
    assert "source_evidence" not in seed_model_text(seed)
    with pytest.raises(ValueError):
        validate_seed(_reseal(seed, mode="source_trained"))
    with pytest.raises(ValueError):
        validate_seed(_reseal(seed, structured_skill=RuleSkill("history-legacy", ()).to_dict()))


def test_legacy_requires_content_hash_and_has_no_final_selected_mode():
    with pytest.raises(ValueError):
        legacy_seed("history-legacy", "legacy", source_ref="parent.md", source_hash="0" * 64)
    seed = legacy_seed("history-legacy", "legacy", source_ref="parent.md", source_hash=_sha("legacy"))
    with pytest.raises(ValueError):
        validate_seed(_reseal(seed, selection_basis="best_on_final"))


@pytest.mark.parametrize("final_selection", [False, True])
def test_source_import_binds_files_without_exposing_host_fields(tmp_path, final_selection):
    prose, attestation = _source(tmp_path, final_selection=final_selection)
    seed = import_source_seed("history-source", tmp_path, attestation=attestation)
    assert seed["mode"] == "source_trained" and seed["structured_skill"] is None
    assert seed["provenance_status"] == "host_reviewed_attestation_not_automatically_authenticated"
    assert not seed["deployment_authorized"] and not seed["skill_admission_authorized"]
    assert len(seed["source_evidence"]) == 5
    assert seed_model_text(seed) == prose
    serialized = json.dumps(seed)
    assert "PRIVATE_TEST_MARKER" not in serialized
    assert "PRIVATE_CONFIG_MARKER" not in serialized
    assert "PRIVATE_SELECTION_MARKER" not in serialized
    assert "fixture-reviewer" not in seed_model_text(seed)
    assert validate_seed(seed) == seed
    assert seed == import_source_seed("history-source", tmp_path, attestation=attestation)


@pytest.mark.parametrize("changes", [
    {"selection_split": "test"}, {"selection_split": "final"},
    {"selection_split": "valid_unseen"}, {"selection_basis": "best_on_final"},
    {"no_test_or_final_selection": False}, {"best_step": 0},
    {"best_step": True}, {"selection_evidence": "test_eval/results.jsonl"},
    {"selection_evidence": "test_eval_final/results.jsonl"},
    {"selected_checkpoint": "old-parent.md"},
    {"selected_checkpoint": "../other.md"}, {"selected_skill_hash": "0" * 64},
    {"deployment_authorized": True},
])
def test_source_selection_rejects_final_and_unbound_attestations(tmp_path, changes):
    _, attestation = _source(tmp_path)
    with pytest.raises(ValueError):
        import_source_seed("history-source", tmp_path, attestation=_reseal(attestation, **changes))


@pytest.mark.parametrize("file", ["summary.json", "history.json", "best_skill.md", "skills/skill_v0001.md"])
def test_source_modification_cannot_reuse_old_attestation(tmp_path, file):
    _, attestation = _source(tmp_path)
    (tmp_path / file).write_text("changed")
    with pytest.raises(ValueError, match="bytes differ"):
        import_source_seed("history-source", tmp_path, attestation=attestation)


@pytest.mark.parametrize("replacement", [
    {"total_steps": 2}, {"total_steps": True}, {"best_step": 2},
    {"best_origin": "another-checkpoint"}, {"best_selection_hard": None},
    {"version": "arbitrary-text-not-training"},
])
def test_even_rehashed_summary_must_match_actual_training_shapes(tmp_path, replacement):
    _, attestation = _source(tmp_path)
    summary = json.loads((tmp_path / "summary.json").read_text())
    raw = json.dumps({**summary, **replacement})
    (tmp_path / "summary.json").write_text(raw)
    hashes = {**attestation["file_hashes"], "summary.json": _sha(raw)}
    attestation = _reseal(attestation, file_hashes=hashes)
    with pytest.raises(ValueError):
        import_source_seed("history-source", tmp_path, attestation=attestation)


def test_source_snapshot_does_not_follow_later_upstream_changes(tmp_path):
    prose, attestation = _source(tmp_path)
    seed = import_source_seed("history-source", tmp_path, attestation=attestation)
    (tmp_path / "best_skill.md").write_text("later upstream edit")
    # Frozen seed remains the earlier imported bytes; a new import must fail.
    assert seed_model_text(seed) == prose
    with pytest.raises(ValueError):
        import_source_seed("history-source", tmp_path, attestation=attestation)


def test_seed_tampering_and_resealed_provenance_change_are_rejected(tmp_path):
    _, attestation = _source(tmp_path)
    seed = import_source_seed("history-source", tmp_path, attestation=attestation)
    edited = deepcopy(seed)
    edited["skill_text"] += " changed"
    with pytest.raises(ValueError):
        seed_model_text(edited)
    for changes in ({"provenance_status": "automatically_verified_mature_skill"},
                    {"source_evidence": []}, {"limitations": []},
                    {"structured_skill": RuleSkill("history-source", ()).to_dict()}):
        with pytest.raises(ValueError):
            seed_model_text(_reseal(seed, **changes))


def test_source_symlink_rejected(tmp_path):
    _, attestation = _source(tmp_path)
    target = tmp_path / "summary.json"
    moved = tmp_path / "real-summary.json"
    target.rename(moved)
    target.symlink_to(moved)
    with pytest.raises(ValueError, match="Symlink"):
        import_source_seed("history-source", tmp_path, attestation=attestation)
