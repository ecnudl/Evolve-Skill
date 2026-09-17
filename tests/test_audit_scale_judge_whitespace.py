"""Entirely fake completed-run fixtures; no live holdout access or APIs."""
import json

import pytest

from scripts.audit_scale_judge_whitespace import (
    REPO,
    REQUIRED_SOURCES,
    _digest,
    audit,
    main,
    normalize_whitespace,
)
from skillopt.validator_pilot.analysis import summarize_rows
from skillopt.validator_scale_rubrics import parse_judgment


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def fake_run(tmp_path, raw="DECISION=FAIL\n\nEVIDENCE=Changed the required behavior.", hard=True, forced=False):
    root = tmp_path / "original"
    snapshot = {name: (REPO / name).read_text(encoding="utf-8") for name in REQUIRED_SOURCES}
    protocol = {"model": "glm-5.3", "source_hashes": {name: _digest(text) for name, text in snapshot.items()}}
    save(root / "source_snapshot.json", snapshot)
    save(root / "protocol.json", protocol)
    request = {"model": "glm-5.3", "kind": "judge_static_v0", "repeat": 1, "key": "target-hash"}
    request_hash = _digest(request)
    call = {"request_hash": request_hash, "request": request, "ok": True, "response": raw}
    save(root / "api/calls" / f"{request_hash}.json", call)
    judgment = parse_judgment(raw)
    guarded = {"decision": "fail", "schema_valid": True, "feedback": ["visible_test_failure"], "errors": []} if forced else judgment
    row = {"id": "task", "family": "family", "cluster_id": "family", "skill_version": "mechanism_skill",
           "split": "dev", "origin": "natural", "repeat": 1, "judge_repeat": 1, "target_repeat": 0,
           "target_ok": True, "execution_ok": True, "hard": hard, "request_hash": "target-hash",
           "rubric_arm": "static_v0", "judgment": judgment, "guarded_judgment": guarded,
           "guard_forced": forced, "judge_ok": True, "raw_judge_ok": True, "judge_attempted": True,
           "judge_request_hash": request_hash, "raw_response_sha256": _digest(raw)}
    save(root / "judgments/static_v0/task__mechanism_skill__j1.json", {**row, "record_sha256": _digest(row)})
    save(root / "dev_judgments.json", {"static_v0": [row]})
    save(root / "holdout_judgments.json", {"static_v0": []})
    save(root / "results.json", {"status": "complete", "protocol_hash": _digest(protocol),
                                "development_raw": summarize_rows([row]),
                                "holdout_raw": {"static_v0": summarize_rows([])}})
    return root, row


def test_only_blank_lines_and_line_edges_are_changed():
    text = " \n  DECISION=FAIL \t\n\n EVIDENCE=Keep  internal  spaces. \n\t\n"
    assert normalize_whitespace(text) == "DECISION=FAIL\nEVIDENCE=Keep  internal  spaces."


def test_spelling_errors_are_not_repaired():
    text = "DECISION=FAIL\n\nEAVIDENCE=wrong label"
    normalized = normalize_whitespace(text)
    assert "EAVIDENCE=" in normalized
    assert not parse_judgment(normalized)["schema_valid"]


def test_contradictory_nonempty_line_is_preserved():
    text = "DECISION=PASS\n\nEVIDENCE=artifact=FAIL\n"
    normalized = normalize_whitespace(text)
    assert normalized == "DECISION=PASS\nEVIDENCE=artifact=FAIL"
    assert not parse_judgment(normalized)["schema_valid"]


def test_complete_barrier_before_any_other_run_read(tmp_path):
    root = tmp_path / "incomplete"
    save(root / "results.json", {"status": "running"})
    save(root / "holdout_judgments.json", {"sensitive": "must not inspect"})
    with pytest.raises(RuntimeError, match="barrier"):
        audit(root)


def test_missing_results_blocks_without_creating_files(tmp_path):
    root = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="barrier"):
        audit(root)
    assert not root.exists()


def test_blank_line_recovery_exposes_false_rejection_not_success(tmp_path):
    root, _ = fake_run(tmp_path, hard=True)
    result = audit(root)
    raw = result["by_split"]["dev"]["static_v0"]["raw"]
    assert raw["strict"]["main"]["unknown_true"] == 1
    assert raw["whitespace_normalized"]["main"]["FN"] == 1
    assert raw["changes"]["by_origin"]["natural"]["newly_exposed_FN"] == 1
    assert result["model_calls"] == result["candidate_executions"] == 0


def test_false_approval_is_also_exposed(tmp_path):
    root, _ = fake_run(tmp_path, raw="DECISION=PASS\n\nEVIDENCE=Claims correctness.", hard=False)
    result = audit(root)["by_split"]["dev"]["static_v0"]
    assert result["raw"]["changes"]["by_origin"]["natural"]["newly_exposed_FP"] == 1


def test_existing_guard_remains_fixed(tmp_path):
    root, _ = fake_run(tmp_path, raw="DECISION=PASS\n\nEVIDENCE=Claims correctness.", hard=False, forced=True)
    result = audit(root)["by_split"]["dev"]["static_v0"]
    assert result["raw"]["whitespace_normalized"]["main"]["FP"] == 1
    assert result["guarded"]["strict"]["main"]["TN"] == 1
    assert result["guarded"]["whitespace_normalized"]["main"]["TN"] == 1
    assert not result["guarded"]["changes"]["changed_rows"]


def test_provenance_checks_cached_response(tmp_path):
    root, row = fake_run(tmp_path)
    path = root / "api/calls" / f"{row['judge_request_hash']}.json"
    value = json.loads(path.read_text())
    value["response"] = "DECISION=PASS\nEVIDENCE=changed"
    save(path, value)
    with pytest.raises(ValueError, match="response checksum"):
        audit(root)


def test_provenance_checks_call_request(tmp_path):
    root, row = fake_run(tmp_path)
    path = root / "api/calls" / f"{row['judge_request_hash']}.json"
    value = json.loads(path.read_text())
    value["request"]["repeat"] = 99
    save(path, value)
    with pytest.raises(ValueError, match="request hash"):
        audit(root)


def test_record_checksum_verified(tmp_path):
    root, _ = fake_run(tmp_path)
    path = root / "judgments/static_v0/task__mechanism_skill__j1.json"
    value = json.loads(path.read_text())
    value["hard"] = False
    save(path, value)
    with pytest.raises(ValueError, match="record checksum"):
        audit(root)


def test_protocol_hash_verified(tmp_path):
    root, _ = fake_run(tmp_path)
    value = json.loads((root / "results.json").read_text())
    value["protocol_hash"] = "wrong"
    save(root / "results.json", value)
    with pytest.raises(ValueError, match="protocol hash"):
        audit(root)


def test_original_run_is_unchanged(tmp_path):
    root, _ = fake_run(tmp_path)
    before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    audit(root)
    after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert after == before


def test_output_cannot_be_inside_original_run(tmp_path):
    root, _ = fake_run(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        main(["--run", str(root), "--output", str(root / "diagnostic.json")])
    assert not (root / "diagnostic.json").exists()


def test_output_outside_run_published_immutably(tmp_path):
    root, _ = fake_run(tmp_path)
    output = tmp_path / "diagnostic.json"
    assert main(["--run", str(root), "--output", str(output)]) == 0
    assert main(["--run", str(root), "--output", str(output)]) == 0
    value = json.loads(output.read_text())
    assert not value["original_results_edited"]
    assert value["provenance"]["frozen_source_files_verified"] == len(REQUIRED_SOURCES)
