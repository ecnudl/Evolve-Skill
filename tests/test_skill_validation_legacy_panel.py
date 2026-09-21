"""Synthetic closed-receipt inventory tests; no models or code execution."""
import json

import pytest

from skillopt.skill_validation.legacy_panel import inventory_legacy
from tests.test_skill_validation_legacy import closed_fixture


def test_actual_closed_record_replays_without_inventing_fresh_evidence(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "output"
    _, identifier = closed_fixture(source, monkeypatch)
    report = inventory_legacy(source, output, source_kind="fixture")
    assert report["selected_records"] == report["imported_records"] == 1
    assert report["natural_formal_eligible_records"] == 0
    assert report["certified_current_candidate_triplets"] == 0
    assert report["conditions"] == {"no_skill": 1}
    assert report["public_replay_statuses"] == {"pass": 1}
    assert report["new_model_calls"] == report["new_artifact_executions"] == 0
    assert report["records"][0]["historical_only"] is True
    case = output / "cases" / identifier
    assert (case / "case.json").is_file()
    assert "PRIVATE" not in json.dumps(report)
    assert "PRIVATE" in (case / "host_only/audit.json").read_text()
    before = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*.json")}
    assert inventory_legacy(source, output, source_kind="fixture") == report
    assert before == {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*.json")}


def test_incomplete_import_is_retained_and_not_recreated(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "output"
    _, identifier = closed_fixture(source, monkeypatch)
    next((source / "runtime/executions").glob("*.json")).unlink()
    result = inventory_legacy(source, output, source_kind="fixture")
    assert result["selected_records"] == 1 and result["imported_records"] == 0
    assert result["refused_records"] == [{"solve_id": identifier, "error_type": "ValueError",
                                          "reason": "closed_import_refused_not_regenerated"}]


def test_final_is_excluded_and_synthetic_cannot_be_called_model(tmp_path, monkeypatch):
    source = tmp_path / "source"
    closed_fixture(source, monkeypatch, phase="final")
    report = inventory_legacy(source, tmp_path / "final_inventory", source_kind="fixture")
    assert report["selected_records"] == 0
    source = tmp_path / "another_source"
    closed_fixture(source, monkeypatch)
    report = inventory_legacy(source, tmp_path / "model_inventory", source_kind="model")
    assert report["imported_records"] == 0 and len(report["refused_records"]) == 1


def test_output_cannot_overwrite_source_and_changed_resume_refuses(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "output"
    closed_fixture(source, monkeypatch)
    with pytest.raises(ValueError, match="separate"):
        inventory_legacy(source, source / "inventory", source_kind="fixture")
    inventory_legacy(source, output, source_kind="fixture", limit=1)
    with pytest.raises((ValueError, RuntimeError)):
        inventory_legacy(source, output, source_kind="fixture", limit=2)


def test_invalid_metadata_is_recorded_without_source_text(tmp_path):
    source = tmp_path / "source"
    (source / "runtime/solves").mkdir(parents=True)
    (source / "runtime/solves/bad.json").write_text('SECRET_INVALID_CONTENT')
    output = tmp_path / "output"
    result = inventory_legacy(source, output, source_kind="fixture")
    selection = json.loads((output / "host_only/selection.json").read_text())
    assert selection["excluded"][0]["reason"] == "invalid_metadata"
    assert "SECRET" not in json.dumps(result) + json.dumps(selection)


def test_traversal_and_child_symlink_cannot_write_into_history(tmp_path, monkeypatch):
    source = tmp_path / "source"
    closed_fixture(source, monkeypatch)
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    with pytest.raises(ValueError, match="traversal"):
        inventory_legacy(source, sibling / ".." / "source" / "new", source_kind="fixture")
    output = tmp_path / "output"
    output.mkdir()
    (output / "host_only").symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        inventory_legacy(source, output, source_kind="fixture")
    assert not (source / "selection.json").exists()
