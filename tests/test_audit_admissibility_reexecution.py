"""Offline scripted evidence; neither audit nor fixture executes generated code."""
import json

import pytest

from scripts import audit_admissibility_reexecution as audit
from skillopt.skill_validation import admissibility_study as study
from tests.test_skill_validation_admissibility_study import Executor, fixture_source, provider


def completed(tmp_path, monkeypatch, *, responses=()):
    source = fixture_source(tmp_path, monkeypatch)
    pool = study.load_frozen(None, None)[3]
    for groups in pool.values():
        for group in groups.values():
            for position in group:
                artifact = position["artifact"]
                study._write(tmp_path / "original/artifacts" / (artifact.content_hash + ".json"),
                             audit.seal(artifact.to_dict()))
    root = tmp_path / "outputs/skill_validation/study"
    executor = Executor(responses)
    study.run(tmp_path, source, root, executor)
    return source, root, executor


def reseal(path, modify):
    value = audit.read(path)
    value.pop("record_hash")
    modify(value)
    path.write_text(json.dumps(audit.seal(value)))


def test_complete_identical_comparison_is_read_only(tmp_path, monkeypatch, provider):
    source, root, executor = completed(tmp_path, monkeypatch)
    calls, executions = provider["calls"], len(executor.calls)
    result = audit.audit(source, root)
    assert result["comparison_complete"] and result["requested_mode"] == "complete"
    assert result["totals"]["expected_admitted_records"] == 10
    assert result["totals"]["compared_probe_pairs"] == result["totals"]["identical_probe_pairs"] == 10
    assert result["totals"]["changed_probe_pairs"] == 0 and result["differences"] == []
    assert provider["calls"] == calls and len(executor.calls) == executions
    assert audit.audit(source, root) == result


@pytest.mark.parametrize("change,field", [
    ({"actual": 99}, "call_0.actual"),
    ({"after_args": [[1, 2, 99]]}, "call_0.after_args"),
])
def test_real_observation_difference_detected_without_printing_values(tmp_path, monkeypatch, provider, change, field):
    source, root, _ = completed(tmp_path, monkeypatch, responses=[change])
    result = audit.audit(source, root)
    assert result["totals"]["changed_probe_pairs"] == 1
    assert result["totals"]["identical_probe_pairs"] == 9
    assert field in result["differences"][0]["changed_fields"]
    assert "expected" not in result["differences"][0] and "actual" not in result["differences"][0]


def test_absent_execution_is_not_a_match(tmp_path, monkeypatch, provider):
    provider["decision"] = "abstain"
    source, root, executor = completed(tmp_path, monkeypatch)
    result = audit.audit(source, root)
    assert not executor.calls
    assert result["totals"]["not_executed_records"] == 10
    assert result["totals"]["compared_probe_pairs"] == 0 and result["comparison_complete"]


def test_partial_must_be_explicit_and_reports_missing_records(tmp_path, monkeypatch, provider):
    source, root, _ = completed(tmp_path, monkeypatch)
    (root / "results.json").unlink()  # Temporary fixture, never a real experiment.
    next((root / "admitted_execution/adaptive_research/admitted").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="Completed results"):
        audit.audit(source, root)
    result = audit.audit(source, root, partial=True)
    assert not result["comparison_complete"] and not result["study_terminal_present"]
    assert result["totals"]["pending_admitted_records"] == 1


def test_terminal_with_missing_admitted_record_is_not_complete(tmp_path, monkeypatch, provider):
    source, root, _ = completed(tmp_path, monkeypatch)
    next((root / "admitted_execution/adaptive_research/admitted").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="missing admitted"):
        audit.audit(source, root)
    assert not audit.audit(source, root, partial=True)["comparison_complete"]


def test_resealed_call_tampering_fails_observation_binding(tmp_path, monkeypatch, provider):
    source, root, _ = completed(tmp_path, monkeypatch)
    path = next((root / "admitted_execution/adaptive_no_research/execution/calls").glob("*.json"))
    def patch(value):
        execution = value["execution"]
        execution.pop("record_hash")
        execution["actual"] = 99
        value["execution"] = audit.seal(execution)
    reseal(path, patch)
    with pytest.raises(ValueError, match="Projected observation"):
        audit.audit(source, root)


def test_source_binding_and_plain_checksum_are_enforced(tmp_path, monkeypatch, provider):
    source, root, _ = completed(tmp_path, monkeypatch)
    reseal(root / "protocol.json", lambda record: record.update(source_result_hash="0" * 64))
    with pytest.raises(ValueError, match="source identity"):
        audit.audit(source, root)
    with pytest.raises(ValueError, match="checksum"):
        audit.verify({"value": 1, "record_hash": "0" * 64})


def test_output_is_explicit_immutable_and_replayable(tmp_path, monkeypatch, provider, capsys):
    source, root, _ = completed(tmp_path, monkeypatch)
    capsys.readouterr()
    output = tmp_path / "audit.json"
    args = ["--source", str(source), "--study", str(root), "--output", str(output)]
    audit.main(args)
    result = json.loads(capsys.readouterr().out)
    assert audit.read(output) == result
    audit.main(args)
    assert json.loads(capsys.readouterr().out) == result
