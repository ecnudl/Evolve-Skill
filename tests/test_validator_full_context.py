from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "validator_full_context", Path(__file__).resolve().parents[1] / "scripts/validator_full_context.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def cases():
    return [{"id": f"dev{i}", "split": "dev",
             "task": {"prompt": "preserve full contract " * 30, "starter_code": "def f(): pass",
                      "public_cases": [{"inputs": [1], "expected": 1}], "reference_code": "secret"},
             "candidate_code": "def f():\n    return " + repr("full code " * 200),
             "public_test_log": {"tests": [{"passed": True, "evidence": "full visible " * 20}]},
             "old_judgment": {"decision": "unknown", "evidence": ["prior evidence " * 20]},
             "development_hard": False, "development_failed_checks": ["private diagnostic " * 30]}
            for i in range(12)]


def pack():
    return {"sources": [{"id": "S1", "url": "https://docs.python.org/3/library/copy.html",
                         "text": "copy source text", "ok": True}]}


def test_complete_evidence_mapping():
    original = cases()
    full = module.full_cases(original)
    for old, new in zip(original, full):
        assert new["candidate_code"] == old["candidate_code"]
        assert new["public_evidence"] == old["public_test_log"]
        assert new["development_failed_checks"] == old["development_failed_checks"]
        assert new["old_judgment"] == old["old_judgment"]
        assert new["task"]["prompt"] == old["task"]["prompt"]
        assert "reference_code" not in new["task"]


def test_six_repair_requests_share_complete_cases():
    full = module.full_cases(cases())
    for stage, research in (("gap_analysis", None), ("critique", None), ("final", None),
                            ("gap_analysis", None), ("research_synthesis", pack()), ("final", pack())):
        system, user = module.full_messages(stage, full, "Previous unverified proposal.", research)
        payload = json.loads(user)
        assert payload["development_cases"] == full
        assert payload["selection"]["fixed_context_hash"] == module.digest(full)
        assert payload["selection"]["truncated"] is False
        assert module.BOUNDARY in system


def test_oversized_request_stops_without_clipping():
    original = cases()
    for case in original:
        case["candidate_code"] = "x" * 20000
    with pytest.raises(ValueError, match="180000"):
        module.full_messages("gap_analysis", module.full_cases(original))


def test_no_nondev_repair_input():
    original = cases()
    original[0]["split"] = "holdout"
    with pytest.raises(ValueError, match="development only"):
        module.full_cases(original)


def test_normalization_preserves_all_nonempty_content():
    raw = " \n 1. First semantic check. \n \t\n 2. EAVIDENCE typo is not repaired. \n"
    assert module.normalize_final(raw) == "1. First semantic check.\n2. EAVIDENCE typo is not repaired."
    assert module.normalize_final("1. a\n3. b") == "1. a\n3. b"
    assert module.normalize_final("DECISION=PASS\nDECISION=FAIL") == "DECISION=PASS\nDECISION=FAIL"


def test_barrier_does_not_read_source_before_own_freeze(tmp_path):
    source, output = tmp_path / "source", tmp_path / "supplement"
    source.mkdir()
    output.mkdir()
    (source / "results.json").write_text("not even valid JSON")
    with pytest.raises(RuntimeError, match="own verified rubric freeze"):
        module.evaluation_barrier(source, output)


def write_freeze(output):
    output.mkdir()
    (output / "revisions").mkdir()
    payloads = {"rubrics_frozen.json": {}, "protocol.json": {}, "full_development_cases.json": []}
    for name, payload in payloads.items():
        (output / name).write_text(json.dumps(payload))
    manifest = {"rubrics_hash": module.digest({}), "protocol_hash": module.digest({}),
                "full_context_hash": module.digest([]), "revisions_hash": module.digest({}),
                "source_holdout_read": False}
    (output / "rubrics_freeze_manifest.json").write_text(json.dumps(manifest))


def test_barrier_requires_source_complete(tmp_path):
    source, output = tmp_path / "source", tmp_path / "supplement"
    source.mkdir()
    write_freeze(output)
    with pytest.raises(RuntimeError, match="source run must be complete"):
        module.evaluation_barrier(source, output)
    (source / "results.json").write_text(json.dumps({"status": "running"}))
    with pytest.raises(RuntimeError, match="not complete"):
        module.evaluation_barrier(source, output)
    (source / "results.json").write_text(json.dumps({"status": "complete"}))
    assert module.evaluation_barrier(source, output)["status"] == "complete"


def test_output_is_new_sibling(tmp_path):
    module.validate_output(tmp_path / "source", tmp_path / "supplement")
    with pytest.raises(ValueError):
        module.validate_output(tmp_path / "source", tmp_path / "source/child")
    with pytest.raises(ValueError):
        module.validate_output(tmp_path / "source", tmp_path.parent / "different")


def test_tampered_freeze_stops_before_source_read(tmp_path):
    source, output = tmp_path / "source", tmp_path / "supplement"
    source.mkdir()
    write_freeze(output)
    (source / "results.json").write_text("must not be opened")
    (output / "rubrics_frozen.json").write_text(json.dumps({"tampered": "new rules"}))
    with pytest.raises(ValueError, match="freeze integrity"):
        module.evaluation_barrier(source, output)


@pytest.mark.parametrize("first_unavailable", [False, True])
def test_rehydrate_exact_public_input_without_execution(monkeypatch, tmp_path, first_unavailable):
    from skillopt import validator_scale_experiment as experiment
    from skillopt.validator_pilot import tasks as task_module
    from skillopt.validator_pilot.experiment import public_evidence
    from skillopt.validator_scale_rubrics import baseline_rubric, judge_messages, parse_judgment

    def forbidden_execution(*args, **kwargs):
        raise AssertionError("rehydration must not execute candidates")

    monkeypatch.setattr(task_module, "evaluate", forbidden_execution)
    monkeypatch.setattr(experiment, "evaluate", forbidden_execution)
    source = tmp_path / "source"
    signed, ordinary, baseline, tasks = {}, {}, [], {}
    for index in range(56):
        identifier = f"task{index}"
        unavailable = first_unavailable and index == 0
        task = {"id": identifier, "prompt": "Return its input unchanged.",
                "starter_code": "def identity(x): return None", "public_cases": [],
                "private_cases": [{"hidden": "never transmitted"}]}
        tasks[identifier] = task
        evaluation = {"execution_ok": not unavailable, "hard": None if unavailable else True,
                      "public_observations": [{"passed": True}],
                      "error_category": "target_unavailable" if unavailable else None}
        artifact = {
            "id": identifier, "skill_version": "noskill", "arm": "noskill",
            "origin": "natural" if index < 48 else "controlled", "family": "toy",
            "cluster_id": "toy", "split": "holdout", "repeat": 0,
            "target_ok": not unavailable, "execution_ok": not unavailable,
            "hard": evaluation["hard"], "request_hash": module.digest({"target": index}),
            "code": None if unavailable else "def identity(x): return x",
            "response": "" if unavailable else "def identity(x): return x",
            "guard_reason": None, "evaluation": evaluation,
        }
        signed[source / "targets" / f"{identifier}__noskill__0.json"] = artifact
        for repeat in range(2):
            raw = "DECISION=PASS\nEVIDENCE=The function returns its input unchanged."
            judgment = parse_judgment(raw) if not unavailable else {
                "decision": "unknown", "schema_valid": False, "errors": ["target_unavailable"],
                "feedback": []}
            system, user = judge_messages(experiment.visible(task), artifact["code"] or "",
                                          public_evidence(evaluation), baseline_rubric())
            request = {"model": "glm-5.3", "system": system, "user": user,
                       "kind": "judge_static_v0", "key": artifact["request_hash"],
                       "max_tokens": 2000, "repeat": repeat, "service": {}}
            call_hash = module.digest(request)
            ordinary[source / "api/calls" / (call_hash + ".json")] = {
                "request": request, "request_hash": call_hash, "ok": True, "response": raw}
            row = {key: artifact[key] for key in (
                "id", "skill_version", "origin", "family", "cluster_id", "split",
                "target_ok", "execution_ok", "hard", "request_hash")}
            row.update(target_repeat=0, judge_repeat=repeat, repeat=repeat,
                       artifact_sha256=module.digest(artifact), guard_forced=False,
                       guarded_judgment=judgment, judgment=judgment, judge_ok=not unavailable,
                       judge_request_hash=None if unavailable else call_hash,
                       raw_response_sha256=None if unavailable else module.digest(raw))
            baseline.append(row)
            signed[source / "judgments/static_v0" / f"{identifier}__noskill__j{repeat}.json"] = row
    monkeypatch.setattr(experiment, "read_record", lambda path: signed[path])
    monkeypatch.setattr(module, "read", lambda path: ordinary[path])
    reconstructed = module.rehydrate(source, baseline, tasks)
    assert len(reconstructed) == 56
    assert sum(row["target_ok"] for row in reconstructed) == 56 - int(first_unavailable)
    for row in reconstructed:
        assert row["request_hash"] == module.digest({"target": int(row["id"][4:])})
        assert "private_cases" not in row["evaluation"]
