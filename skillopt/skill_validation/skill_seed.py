"""Explicit, host-owned learning-history starts; never deployment authority.

SkillOpt training outputs are mutable and have no signed provenance protocol.
Source imports therefore require a host-reviewed selection attestation and exact
file hashes. The checks below freeze and cross-check bytes, not the honesty of
the reviewer, training quality, or causal source-domain improvement. No source
scores, paths, or attestation fields are part of the model-facing view.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify

from .models import file_path, hash_text, require, text
from .rule_skill import RuleSkill, render_skill

VERSION = "skill-history-seed-v1"
SOURCE_ATTESTATION_VERSION = "host-reviewed-skillopt-source-selection-v1"
MAX_SKILL_BYTES = 6000
_FIELDS = {"version", "history_id", "mode", "skill_text", "skill_text_hash",
           "structured_skill", "source_evidence", "selection_basis", "source_attestation",
           "provenance_status", "deployment_authorized", "skill_admission_authorized",
           "limitations", "record_hash"}
_ATTESTATION_FIELDS = {"version", "reviewer", "source_run_id", "source_domain",
                       "selection_split", "selection_basis", "no_test_or_final_selection",
                       "best_step", "best_origin", "selected_skill_hash", "selected_checkpoint",
                       "selection_evidence", "file_hashes", "record_hash"}
_LIMITATIONS = [
    "A seed is not an accepted Skill, a verifier authorization, or evidence of generalization.",
    "Hashes establish content bindings, not origin authenticity or honest source selection.",
    "Imported prose is not automatically converted into validated rules; conversion needs a new proposal.",
]


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record(history_id, mode, skill_text, *, structured=None, evidence=(),
            selection_basis, attestation=None, provenance_status):
    RuleSkill(history_id, ())  # Share the learning-history identifier contract.
    text(skill_text, maximum=MAX_SKILL_BYTES, empty=mode == "cold")
    return seal({"version": VERSION, "history_id": history_id, "mode": mode,
                 "skill_text": skill_text, "skill_text_hash": _sha(skill_text),
                 "structured_skill": structured, "source_evidence": list(evidence),
                 "selection_basis": selection_basis, "source_attestation": attestation,
                 "provenance_status": provenance_status, "deployment_authorized": False,
                 "skill_admission_authorized": False, "limitations": list(_LIMITATIONS)})


def cold_seed(history_id):
    """A genuinely empty RuleSkill, with no hidden procedural seed text."""
    skill = RuleSkill(history_id, ())
    return _record(history_id, "cold", render_skill(skill), structured=skill.to_dict(),
                   selection_basis="empty_initialization", provenance_status="explicit_empty_seed")


def legacy_seed(history_id, skill_text, *, source_ref, source_hash):
    """Retain old text as a weak diagnostic seed, not certified trained memory.

    The reference is host-declared, not a file loaded/authenticated by this API.
    Its hash must bind the supplied text; source migration never invents rules.
    """
    text(skill_text, maximum=MAX_SKILL_BYTES)
    text(source_ref, maximum=1000)
    hash_text(source_hash)
    require(source_hash == _sha(skill_text), "Legacy source hash differs from supplied text")
    return _record(history_id, "legacy_diagnostic", skill_text,
                   evidence=({"role": "legacy_text", "ref": source_ref, "sha256": source_hash},),
                   selection_basis="retained_weak_seed_not_performance_selected",
                   provenance_status="host_declared_legacy_reference_not_authenticated")


def _selection_attestation(value):
    value = verify(value)
    require(set(value) == _ATTESTATION_FIELDS, "Unexpected source-selection attestation fields")
    require(value["version"] == SOURCE_ATTESTATION_VERSION, "Unsupported source attestation")
    for key in ("reviewer", "source_run_id", "source_domain", "best_origin"):
        text(value[key], maximum=500)
    require(value["selection_split"] == "valid_seen"
            and value["selection_basis"] == "best_on_source_validation"
            and value["no_test_or_final_selection"] is True,
            "Only attested source validation may select the parent; test/final selection forbidden")
    require(type(value["best_step"]) is int and value["best_step"] > 0,
            "Source-trained seed must reference a completed non-initial training step")
    hash_text(value["selected_skill_hash"])
    checkpoint, selection = value["selected_checkpoint"], value["selection_evidence"]
    file_path(checkpoint)
    file_path(selection)
    cp, sp = Path(checkpoint), Path(selection)
    require(cp.suffix == ".md" and cp.parts[0] in {"skills", "steps", "slow_updates"},
            "Selected checkpoint must be an explicit training checkpoint, not arbitrary seed prose")
    require(sp.name == "results.jsonl" and sp.parent.name in {"selection_eval", "final_selection_eval"},
            "Expected source-validation results, not test/final evaluation results")
    require(not any(part.startswith(("test", "final_eval")) for part in cp.parts + sp.parts),
            "Test/final evaluation paths cannot establish source selection")
    expected_paths = {"summary.json", "history.json", "best_skill.md", checkpoint, selection}
    hashes = value["file_hashes"]
    require(type(hashes) is dict and set(hashes) == expected_paths,
            "Exact summary/history/best/checkpoint/selection source hashes required")
    for item in hashes.values():
        hash_text(item)
    require(hashes["best_skill.md"] == hashes[checkpoint] == value["selected_skill_hash"],
            "Best text and selected checkpoint must be the same frozen bytes")
    return value


def _read_frozen(root, relative, expected_hash):
    path = root / relative
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink source evidence is unsupported")
    require(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024, "Missing or oversized source evidence")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_hash, "Source bytes differ from attested immutable snapshot")
    return raw.decode("utf-8")


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate source JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Nonfinite source JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def import_source_seed(history_id, source_dir, *, attestation):
    """Read-only import of explicitly attested upstream SkillOpt training bytes.

    ``attestation`` is a sealed host record with SOURCE_ATTESTATION_VERSION and
    the exact fields in _ATTESTATION_FIELDS. In particular it binds all five
    source files by SHA256, names a training checkpoint matching best_skill.md,
    and names valid_seen selection results. final_selection_eval is valid_seen
    in SkillOpt, unlike test_eval_final, which is rejected. Caller/reviewer owns
    the claim that those results actually selected this checkpoint; this API
    does not certify model-call provenance, replay training, or inspect test
    scores. Full source summary/config/results never enter returned model text.
    """
    attestation = _selection_attestation(attestation)
    root = Path(source_dir).absolute()
    files = {relative: _read_frozen(root, relative, sha)
             for relative, sha in attestation["file_hashes"].items()}
    summary, history = _json(files["summary.json"]), _json(files["history.json"])
    require(type(summary) is dict and str(summary.get("version", "")).startswith("skillopt-"),
            "Expected an upstream SkillOpt summary")
    require(type(history) is list and history and all(type(row) is dict for row in history),
            "Expected a nonempty upstream training history")
    require(type(summary.get("total_steps")) is int and summary["total_steps"] == len(history),
            "Training summary/history length mismatch")
    require(type(summary.get("best_step")) is int and summary["best_step"] == attestation["best_step"]
            and summary.get("best_origin") == attestation["best_origin"]
            and any(type(row.get("step")) is int and row["step"] == attestation["best_step"] for row in history),
            "Source selected step/origin lacks matching training evidence")
    score = summary.get("best_selection_hard")
    require(type(score) in {int, float} and math.isfinite(score), "Missing finite source-selection score")
    selection_rows = [_json(line) for line in files[attestation["selection_evidence"]].splitlines() if line.strip()]
    require(selection_rows and all(type(row) is dict and row for row in selection_rows),
            "Source-selection execution records are empty or malformed")
    skill_text = files["best_skill.md"]
    require(skill_text == files[attestation["selected_checkpoint"]], "Source checkpoint differs from selected best")
    evidence = [{"role": "source_file", "ref": relative, "sha256": sha}
                for relative, sha in sorted(attestation["file_hashes"].items())]
    seed = _record(history_id, "source_trained", skill_text, evidence=evidence,
                   selection_basis="host_reviewed_best_on_source_validation", attestation=attestation,
                   provenance_status="host_reviewed_attestation_not_automatically_authenticated")
    return validate_seed(seed)


def validate_seed(seed):
    """Validate the frozen seed schema without rereading mutable upstream files."""
    seed = verify(seed)
    require(set(seed) == _FIELDS and seed["version"] == VERSION, "Unexpected seed fields/version")
    RuleSkill(seed["history_id"], ())
    require(seed["mode"] in {"cold", "legacy_diagnostic", "source_trained"}, "Unsupported initialization mode")
    text(seed["skill_text"], maximum=MAX_SKILL_BYTES, empty=seed["mode"] == "cold")
    require(_sha(seed["skill_text"]) == seed["skill_text_hash"], "Seed text/hash mismatch")
    require(seed["deployment_authorized"] is False and seed["skill_admission_authorized"] is False,
            "Seed records cannot authorize Skill use or deployment")
    require(seed["limitations"] == _LIMITATIONS, "Seed provenance limitations must remain explicit")
    if seed["mode"] == "cold":
        require(seed["skill_text"] == "" and seed["structured_skill"] == RuleSkill(seed["history_id"], ()).to_dict()
                and seed["source_evidence"] == [] and seed["source_attestation"] is None
                and seed["selection_basis"] == "empty_initialization"
                and seed["provenance_status"] == "explicit_empty_seed", "Cold must be an empty RuleSkill")
    else:
        require(seed["structured_skill"] is None, "Imported prose cannot inherit verified structured rules")
        if seed["mode"] == "legacy_diagnostic":
            refs = seed["source_evidence"]
            require(type(refs) is list and len(refs) == 1 and type(refs[0]) is dict
                    and set(refs[0]) == {"role", "ref", "sha256"}
                    and refs[0]["role"] == "legacy_text" and refs[0]["sha256"] == seed["skill_text_hash"]
                    and seed["source_attestation"] is None
                    and seed["selection_basis"] == "retained_weak_seed_not_performance_selected"
                    and seed["provenance_status"] == "host_declared_legacy_reference_not_authenticated",
                    "Legacy text must remain a weak diagnostic seed")
            text(refs[0]["ref"], maximum=1000)
        else:
            attestation = _selection_attestation(seed["source_attestation"])
            refs = [{"role": "source_file", "ref": relative, "sha256": sha}
                    for relative, sha in sorted(attestation["file_hashes"].items())]
            require(seed["source_evidence"] == refs and attestation["selected_skill_hash"] == seed["skill_text_hash"]
                    and seed["selection_basis"] == "host_reviewed_best_on_source_validation"
                    and seed["provenance_status"] == "host_reviewed_attestation_not_automatically_authenticated",
                    "Source-trained seed requires the frozen host-reviewed source evidence")
    return seed


def seed_model_text(seed):
    """The only seed model projection: text, never source/config/selection data."""
    return validate_seed(seed)["skill_text"]
