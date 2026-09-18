"""Synthetic receipt import tests; no model service or candidate execution."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v15 import runtime
from skillopt.skill_validation.legacy import load_v15_development
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v12_runtime import FakeAPI, coding, put, tree


def _fixture_evaluation(adapter, artifact, *, public_only, mutates_input=False):
    """Explicit fabricated unit-test observations, NOT an executable oracle."""
    if artifact is None:
        return {"files": None, "hard": None, "correct": False, "execution_ok": False,
                "artifact_execution_ok": False, "case_results": [], "public_observations": [],
                "private_diagnostics": [], "passed_tests": 0, "total_tests": 0, "public_pass": None}
    cases = adapter.task.public_cases + ([] if public_only else adapter.task.private_cases)
    observations = [{"label": case["label"], "input": case["input"], "actual": case["expected"],
        "passed": not mutates_input, "exception": None, "input_unchanged": not mutates_input,
        "input_before_fingerprint": digest(case["input"]),
        "input_after_fingerprint": digest({"mutated": True}) if mutates_input else digest(case["input"]),
        "host_private_metadata": {"reference": "NESTED_PRIVATE_SENTINEL"}} for case in cases]
    rows = [{"id": case["label"] + ":" + suffix, "label": case["label"],
             "passed": not mutates_input or suffix == "behavior",
             "public": case["public"], "dimension": case["dimension"]}
            for case in cases for suffix in ("behavior", "input_unchanged")]
    return {"files": artifact, "hard": not mutates_input, "correct": not mutates_input, "execution_ok": True,
        "artifact_execution_ok": True, "case_results": rows,
        "public_observations": [row for row in observations if row["label"] == "public-code"],
        "private_diagnostics": [row for row in observations if row["label"] != "public-code"],
        "passed_tests": sum(row["passed"] for row in rows), "total_tests": len(rows),
        "public_pass": not mutates_input}


def closed_fixture(tmp_path, monkeypatch, *, manifests=True, bad_first=False, bad_revision=False,
                   phase="development", mutates_input=False):
    monkeypatch.setattr(runtime.legacy, "evaluate", lambda *args, **kwargs:
        _fixture_evaluation(*args, **kwargs, mutates_input=mutates_input))
    adapter = coding()
    adapter = type(adapter)(replace(adapter.task, split=phase))
    state = {"calls": 0, "receipts": [], "bad_first": bad_first, "bad_revision": bad_revision}
    solved = runtime.solve(adapter, FakeAPI(tmp_path, state), "", root=tmp_path, key="fixture-only", phase=phase)
    if manifests:
        files = {name: "# Explicit synthetic source fixture, not historical production code.\n" for name in (
            "skillopt/coevolution_v15/runtime.py", "skillopt/coevolution_v15/evidence.py")}
        snapshot = seal({"files": files})
        panel = seal({"groups": {"train": [[runtime.legacy.payload(adapter)]]}})
        put(tmp_path / "source_snapshot.json", snapshot)
        put(tmp_path / "private_panel.json", panel)
        put(tmp_path / "protocol.json", seal({"source_hashes": {
            name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
            "source_snapshot_hash": snapshot["record_hash"], "panel_hash": panel["record_hash"]}))
    return solved, digest(solved["identity"])


def load(root, identifier):
    return load_v15_development(root, identifier, source_kind="fixture")


def reseal(value):
    return seal({k: v for k, v in value.items() if k != "record_hash"})


def test_public_projection_has_actual_artifact_but_not_private_projection(tmp_path, monkeypatch):
    solved, identifier = closed_fixture(tmp_path, monkeypatch)
    imported = load(tmp_path, identifier)
    assert imported.artifact == solved["artifact"]
    assert imported.identity["artifact_hash"] == digest(solved["artifact"])
    assert imported.identity["condition"] == "no_skill"
    assert imported.provenance["source_closure_complete"]
    assert imported.provenance["integrity_checked"]
    assert not imported.provenance["execution_authenticated"]
    assert not imported.provenance["formal_eligible"]
    assert imported.source_kind == "fixture"
    safe = json.dumps([imported.public_task, imported.public_observations])
    assert "PRIVATE" not in safe
    assert "runtime-coding" not in safe
    assert "public_case_0" in safe
    assert "PRIVATE_CODE_SENTINEL" in json.dumps(imported.host_only)
    assert "NESTED_PRIVATE_SENTINEL" in json.dumps(imported.host_only)
    assert imported.public_observations[0]["expected"] == {"answer": 2}
    assert imported.public_observations[0]["input_unchanged"] is True
    exported = imported.to_dict()
    exported["artifact"]["helper.py"] = "changed"
    assert exported["artifact"] != imported.artifact


def test_import_never_calls_executes_or_writes_and_replays_identically(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch)
    before = tree(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("Import attempted model call, execution or write")
    monkeypatch.setattr(FakeAPI, "call", forbidden)
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    first = load(tmp_path, identifier)
    assert first.to_dict() == load(tmp_path, identifier).to_dict()
    assert first.provenance["api_calls"] == first.provenance["native_executions"] == 0
    assert before == tree(tmp_path)


@pytest.mark.parametrize("target", ["public_observation", "public_task", "host_only"])
def test_nested_import_mutation_invalidates_verified_snapshot(tmp_path, monkeypatch, target):
    _, identifier = closed_fixture(tmp_path, monkeypatch)
    imported = load(tmp_path, identifier)
    imported.verify_integrity()
    if target == "public_observation":
        imported.public_observations[0]["behavior_passed"] = False
    elif target == "public_task":
        imported.public_task["public_cases"][0]["expected"] = {"answer": 999}
    else:
        imported.host_only["solve"]["private_evaluation"]["hard"] = False
    with pytest.raises(ValueError, match="changed after receipt verification"):
        imported.verify_integrity()
    with pytest.raises(ValueError, match="changed after receipt verification"):
        imported.to_dict()


@pytest.mark.parametrize("directory", ["runtime/stages", "runtime/request_intents", "runtime/execution_intents",
                                       "runtime/executions", "api/calls"])
def test_missing_durable_dependency_fails_without_rebuilding(tmp_path, monkeypatch, directory):
    _, identifier = closed_fixture(tmp_path, monkeypatch)
    next((tmp_path / directory).glob("*.json")).unlink()
    before = tree(tmp_path)
    with pytest.raises(ValueError, match="missing"):
        load(tmp_path, identifier)
    assert tree(tmp_path) == before


def test_missing_source_manifest_keeps_record_diagnostic(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch, manifests=False)
    imported = load(tmp_path, identifier)
    assert not imported.provenance["source_closure_complete"]
    assert "protocol.json" in imported.provenance["missing_dependencies"]
    assert not imported.provenance["formal_eligible"]


@pytest.mark.parametrize("change", ["source", "panel", "execution", "artifact", "intent"])
def test_resealed_dependency_mismatch_is_not_accepted(tmp_path, monkeypatch, change):
    solved, identifier = closed_fixture(tmp_path, monkeypatch)
    if change in {"source", "panel"}:
        path = tmp_path / ("source_snapshot.json" if change == "source" else "private_panel.json")
        value = json.loads(path.read_text())
        if change == "source":
            value["files"]["skillopt/coevolution_v15/runtime.py"] += "tamper"
        else:
            value["groups"]["train"][0][0]["prompt"] = "Another task"
        put(path, reseal(value))
    elif change == "execution":
        path = tmp_path / "runtime/executions" / (solved["execution_ids"][0] + ".json")
        value = json.loads(path.read_text())
        value["native_evaluation"]["public_observations"][0]["actual"] = {"answer": 999}
        put(path, reseal(value))
    elif change == "artifact":
        path = tmp_path / "runtime/solves" / (identifier + ".json")
        value = json.loads(path.read_text())
        value["artifact"]["helper.py"] = "def compute(x): return 999\n"
        put(path, reseal(value))
    else:
        path = tmp_path / "runtime/request_intents" / (solved["request_hashes"][0] + ".json")
        value = json.loads(path.read_text())
        value["stage"] = "revision"
        put(path, reseal(value))
    with pytest.raises(ValueError):
        load(tmp_path, identifier)


def test_synthetic_transport_cannot_be_labeled_natural(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Synthetic"):
        load_v15_development(tmp_path, identifier, source_kind="model")


def test_final_cannot_be_relabeled_as_development(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch, phase="final")
    with pytest.raises(ValueError, match="development"):
        load(tmp_path, identifier)


def test_rollback_uses_only_chosen_artifact_public_receipt(tmp_path, monkeypatch):
    solved, identifier = closed_fixture(tmp_path, monkeypatch, bad_revision=True)
    imported = load(tmp_path, identifier)
    assert imported.artifact == solved["artifact"]
    assert imported.provenance["chosen_stage"] == "generation"
    assert imported.public_observations[0]["execution_id"] == solved["execution_ids"][0]
    assert imported.host_only["projection"]["stages"][1]["delivery_status"] == "fail"


def test_missing_artifact_does_not_import_starter_files_as_answer(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch, bad_first=True, bad_revision=True)
    imported = load(tmp_path, identifier)
    assert imported.artifact is None
    assert imported.public_task["files"]
    assert imported.public_observations == []


def test_correct_return_with_input_mutation_keeps_distinct_obligations(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch, mutates_input=True)
    imported = load(tmp_path, identifier)
    observation = imported.public_observations[0]
    assert observation["actual"] == observation["expected"]
    assert observation["passed"] is False  # Historical combined result.
    assert observation["behavior_passed"] is True  # Actual return-value receipt.
    assert observation["input_unchanged"] is False
    assert observation["input_before_fingerprint"] != observation["input_after_fingerprint"]


def test_missing_behavior_check_is_unknown_not_inferred_from_combined_result(tmp_path, monkeypatch):
    from skillopt.skill_validation.legacy import _public_projection

    _, identifier = closed_fixture(tmp_path, monkeypatch)
    imported = load(tmp_path, identifier)
    task = json.loads(imported.host_only["api_receipts"][0]["request"]["user"])["task"]
    chosen = imported.host_only["stages"][1]
    chosen["public_evaluation"]["case_results"] = []
    _, observations = _public_projection(task, chosen)
    assert observations[0]["passed"] is True
    assert observations[0]["behavior_passed"] is None


@pytest.mark.parametrize("change", ["private", "nonboolean", "duplicate", "label"])
def test_behavior_receipt_requires_unambiguous_public_boolean_match(tmp_path, monkeypatch, change):
    from skillopt.skill_validation.legacy import _public_projection

    _, identifier = closed_fixture(tmp_path, monkeypatch)
    imported = load(tmp_path, identifier)
    task = json.loads(imported.host_only["api_receipts"][0]["request"]["user"])["task"]
    chosen = imported.host_only["stages"][1]
    row = chosen["public_evaluation"]["case_results"][0]
    if change == "private":
        row["public"] = False
    elif change == "nonboolean":
        row["passed"] = 1
    elif change == "label":
        row["label"] = "other"
    else:
        chosen["public_evaluation"]["case_results"].append(dict(row))
    with pytest.raises(ValueError, match="behavior|Behavior"):
        _public_projection(task, chosen)


def test_symlink_evidence_and_path_traversal_are_refused(tmp_path, monkeypatch):
    _, identifier = closed_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="SHA256"):
        load(tmp_path, "../" + identifier)
    path = tmp_path / "protocol.json"
    moved = tmp_path / "actual_protocol.json"
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(ValueError, match="Symlink"):
        load(tmp_path, identifier)


@pytest.mark.parametrize("duplicate", [True, False])
def test_ambiguous_or_nonfinite_json_is_not_reinterpreted(tmp_path, monkeypatch, duplicate):
    _, identifier = closed_fixture(tmp_path, monkeypatch)
    path = tmp_path / "protocol.json"
    if duplicate:
        path.write_text('{"record_hash":"first", "record_hash":"second"}')
    else:
        path.write_text('{"unexpected":NaN}')
    with pytest.raises(ValueError, match="Duplicate|Nonfinite"):
        load(tmp_path, identifier)


def test_optional_closed_real_local_record():
    """Read-only integration evidence; skipped in clean clones without outputs."""
    root = Path(__file__).resolve().parents[1] / "outputs/coevolution_v16/pilot_20260915_a_clean_resume_20260916"
    if not root.exists():
        pytest.skip("Local historical outputs are deliberately not distributed with the repository")
    imported = load_v15_development(root,
        "11abc4a5491a01588134af3faa138f9c0d0a3d9ecdc3f86002f423cef9ba33aa", source_kind="model")
    assert imported.provenance["source_closure_complete"]
    assert imported.provenance["source_file_count"] > 0
    assert imported.artifact is not None
    assert len(imported.public_observations) == 2
    assert imported.provenance["api_calls"] == imported.provenance["native_executions"] == 0
