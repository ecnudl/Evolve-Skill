"""End-to-end Stage-1 entry points: generated fixtures are never real runs."""
import json
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.__main__ import main
from skillopt.skill_validation.fixtures import smoke_cases
from skillopt.skill_validation.replay import case_record, read_case, run_case
from skillopt.validator_pilot.api import write_immutable_json


def test_smoke_and_replay_idempotent(tmp_path, capsys):
    root = tmp_path.resolve() / "smoke"
    assert main(["smoke", "--output", str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert {k: v["status"] for k, v in result.items()} == {
        "preserved": "pass", "changed": "fail", "unavailable": "unknown", "in_place": "pass"}
    files = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")}
    assert main(["smoke", "--output", str(root)]) == 0
    capsys.readouterr()
    assert files == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")}
    for name in result:
        assert main(["replay", "--input", str(root / name / "case.json"), "--output", str(root / name)]) == 0
        replayed = json.loads(capsys.readouterr().out)
        assert replayed == result[name]
        assert replayed["metrics"]["model_calls"] == replayed["metrics"]["new_executions"] == 0
        assert replayed["verifier_gate"]["status"] == replayed["skill_gate"]["status"] == "pending"


def _write_case(tmp_path, payload):
    path = tmp_path.resolve() / "case.json"
    write_immutable_json(path, seal(payload))
    return path


@pytest.mark.parametrize("attack", ["hidden", "manifest", "task", "artifact", "evidence"])
def test_case_read_rejects_mismatches_and_audit_input(tmp_path, attack):
    _, task, artifact, evidence = next(smoke_cases())
    payload = case_record(task, artifact, evidence)
    payload.pop("record_hash")
    if attack == "hidden":
        payload["host_only_audit"] = {"answer": "HIDDEN"}
    elif attack == "manifest":
        payload["partition_manifest"]["entries"][0]["partition"] = "final"
    elif attack == "task":
        payload["task"]["partition"] = "final"
    elif attack == "artifact":
        payload["artifact"]["files"][0]["content"] += "# changed"
    else:
        payload["evidence"][0]["visibility"] = "private"
    with pytest.raises(ValueError):
        read_case(_write_case(tmp_path, payload))


def test_invalid_json_or_missing_input_is_visible_cli_failure(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        main(["replay", "--input", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out")])
    assert error.value.code == 2
    assert "refused" in capsys.readouterr().err


def test_changed_report_not_silently_overwritten(tmp_path):
    _, task, artifact, evidence = next(smoke_cases())
    output = tmp_path.resolve() / "out"
    run_case(task, artifact, evidence, output=output)
    changed = replace(artifact, repeat=1)
    with pytest.raises(ValueError, match="Immutable"):
        run_case(task, changed, (), output=output)


def test_unsupported_preserved_as_unknown(tmp_path):
    name, task, artifact, evidence = list(smoke_cases())[2]
    summary = run_case(task, artifact, evidence, output=tmp_path.resolve() / name)
    assert summary["metrics"]["unknown"] == 2
    assert summary["metrics"]["fail"] == 0
    assert "unsupported" in json.dumps(json.loads((tmp_path / name / "report.json").read_text()))


def test_historical_normalization_and_replay_optional(tmp_path):
    from pathlib import Path

    from skillopt.skill_validation.importers import normalize_v15
    from skillopt.skill_validation.legacy import load_v15_development

    root = Path(__file__).resolve().parents[1] / "outputs/coevolution_v16/pilot_20260915_a_clean_resume_20260916"
    if not root.exists():
        pytest.skip("Optional closed historical cache is not distributed with the repository")
    source = load_v15_development(root, "11abc4a5491a01588134af3faa138f9c0d0a3d9ecdc3f86002f423cef9ba33aa", source_kind="model")
    task, artifact, evidence, audit = normalize_v15(source)
    summary = run_case(task, artifact, evidence, output=tmp_path.resolve() / "real")
    assert summary["source_kind"] == "model" and summary["historical_only"] is True
    assert summary["provenance_complete"] is True
    assert summary["metrics"]["pass"] == 2
    assert "historical_private_evaluation" in audit
    visible = (tmp_path / "real/verifier_view.json").read_text()
    for key in ("historical_private_evaluation", "skill_hash", "condition", "task_id", "cluster_id", "family_id"):
        assert key not in visible


def test_legacy_normalization_separates_behavior_from_mutation(tmp_path, monkeypatch):
    from skillopt.skill_validation.engine import validate
    from skillopt.skill_validation.importers import normalize_v15
    from tests.test_skill_validation_legacy import closed_fixture, load

    _, identifier = closed_fixture(tmp_path, monkeypatch, mutates_input=True)
    task, artifact, evidence, _ = normalize_v15(load(tmp_path, identifier))
    report = validate(task, artifact, evidence)
    assert dict(report.obligation_results) == {"requested": "pass", "preserve_input": "fail"}


def test_missing_public_observation_retains_unknown(tmp_path, monkeypatch):
    from skillopt.skill_validation.engine import validate
    from skillopt.skill_validation.importers import normalize_v15
    from tests import test_skill_validation_legacy as fixture

    original = fixture._fixture_evaluation

    def missing(*args, **kwargs):
        result = original(*args, **kwargs)
        result["public_observations"] = []
        return result

    monkeypatch.setattr(fixture, "_fixture_evaluation", missing)
    _, identifier = fixture.closed_fixture(tmp_path, monkeypatch)
    task, artifact, evidence, _ = normalize_v15(fixture.load(tmp_path, identifier))
    report = validate(task, artifact, evidence)
    assert dict(report.obligation_results) == {"requested": "unknown", "preserve_input": "unknown"}
    assert len(evidence[0].observations) == 2


def test_modified_import_is_not_used_by_normalizer(tmp_path, monkeypatch):
    from skillopt.skill_validation.importers import normalize_v15
    from tests.test_skill_validation_legacy import closed_fixture, load

    _, identifier = closed_fixture(tmp_path, monkeypatch)
    source = load(tmp_path, identifier)
    source.public_observations[0]["behavior_passed"] = False
    with pytest.raises(ValueError, match="changed"):
        normalize_v15(source)
