"""Same-response parser sensitivity tests; no network or model calls."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import audit_coevolution_v4_delivery as audit
from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v4 import runtime
from skillopt.validator_pilot.api import digest, write_immutable_json


def task_for():
    files = {"api.py": "import calculation\ndef solve(data):\n    return calculation.double(data['x'])\n",
             "calculation.py": "import helper\ndef double(value):\n    return helper.compute(value)\n",
             "helper.py": "def compute(value):\n    return value\n"}
    reference = {**files, "helper.py": "def compute(value):\n    return value * 2\n"}
    public = {"label": "public", "input": {"x": 2}, "expected": 4, "exception": None,
              "dimension": "requested_behavior", "public": True}
    private = {**public, "label": "private", "input": {"x": 7}, "expected": 14, "public": False}
    return RepoTask("audit_unit", "learn0", "unit", "unit", "Return twice x without mutation.",
                    files, reference, ["calculation.py", "helper.py"], {}, [public], [private], {})


def good_delivery(task=None):
    task = task or task_for()
    return runtime.serialize_delivery({p: task.reference_files[p] for p in task.editable_paths})


def missing_intermediate_end(task=None):
    return good_delivery(task).replace("<<<END FILE>>>\n", "", 1)


class FakeAPI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.rows = []

    def call(self, system, user, **kwargs):
        response = self.responses.pop(0)
        request = {"system": system, "user": user, **kwargs}
        row = {"request": request, "request_hash": digest(request), "ok": True, "response": response}
        if isinstance(response, dict):
            row.update(response)
        self.rows.append(row)
        return row


def solve(first, second, task=None):
    task = task or task_for()
    job = {"id": task.id, "skill": "", "stream": 0, "stage": "r0", "repeat": 0}
    api = FakeAPI([first, second])
    row = runtime.solve(api, task, "", key=digest(job), repeat=0)
    row.update(stream=0, stage="r0", split=task.split, job_hash=digest(job))
    return row, api


def test_strict_valid_delivery_preserves_identical_source():
    task = task_for()
    result = audit.recover_delivery(task, good_delivery(task))
    assert result["mode"] == "strict_unchanged"
    assert result["implicit_boundaries"] == []
    assert result["files"] == task.reference_files


def test_missing_intermediate_end_is_only_boundary_change():
    task = task_for()
    raw = missing_intermediate_end(task)
    result = audit.recover_delivery(task, raw)
    assert result["files"] == task.reference_files
    assert result["mode"] == "missing_end_marker_only"
    assert result["implicit_boundaries"][0]["boundary"] == "next_file_header"
    assert result["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.parametrize("ending", ["", "\n"])
def test_eof_recovery_preserves_exact_source_bytes(ending):
    code = "def compute(value):\n    return value * 2" + ending
    raw = "<<<FILE helper.py>>>\n" + code
    result = audit.recover_delivery(task_for(), raw)
    assert result["files"]["helper.py"] == code
    assert result["implicit_boundaries"] == [{"path": "helper.py", "boundary": "end_of_response", "line": 4}]


def test_all_missing_end_markers_recovered_without_rewriting():
    task = task_for()
    raw = good_delivery(task).replace("<<<END FILE>>>\n", "")
    result = audit.recover_delivery(task, raw)
    assert result["files"] == task.reference_files
    assert len(result["implicit_boundaries"]) == 2


@pytest.mark.parametrize("raw", [
    "", "KEEP", "Some prose\n" + missing_intermediate_end(),
    missing_intermediate_end() + "Trailing explanation", "```python\n" + missing_intermediate_end() + "```",
    "<<<FILE helper.py>>>\n```python\ndef compute(v): return v\n```\n",
    "<<<FILE api.py>>>\ndef solve(data): return 1\n",
    "<<<FILE missing.py>>>\na=1\n", "<<<FILE ../helper.py>>>\na=1\n",
    "<<<FILE /helper.py>>>\na=1\n", "<<<FILE helper.py>>>\n\n",
    "<<<FILE helper.py>>>\ndef broken(:\n",
    "<<<FILE helper.py>>>\nimport os\n",
    "<<<FILE helper.py>>>\ndef compute(v): return open('/etc/passwd').read()\n",
    "<<<FILE helper.py>>>\ndef compute(v): return v.__class__\n",
    "<<<END FILE>>>\n" + missing_intermediate_end(),
    "<<<FILE helper.py>>>\na=1\n<<<FILE helper.py>>>\na=2\n",
    "<<<FILE helper.py>>\na=1\n",
    "<<<FILE helper.py>>>\r\ndef compute(v): return v\r\n",
    "<<<FILE helper.py>>>\n<<<OTHER>>>\ndef compute(v): return v\n",
])
def test_recovery_rejects_adversarial_or_ambiguous_text(raw):
    with pytest.raises((ValueError, SyntaxError)):
        audit.recover_delivery(task_for(), raw)


def test_recovery_rejects_oversize_without_execution(monkeypatch):
    monkeypatch.setattr(audit.executor, "run_payload", lambda _: pytest.fail("oversized code executed"))
    with pytest.raises(ValueError):
        audit.recover_delivery(task_for(), "x" * (audit.executor.MAX_ARTIFACT_CHARS + 20001))


def test_valid_finished_response_is_not_reexecuted(monkeypatch):
    row, _ = solve(good_delivery(), "KEEP")
    monkeypatch.setattr(audit.executor, "run_payload", lambda _: pytest.fail("unchanged code reexecuted"))
    result = audit.audit_target(task_for(), row, True, True)
    assert result["same_prompt_base_sensitivity"]["mode"] == "strict_keep_unchanged"
    assert result["same_prompt_base_sensitivity"]["score"]["hard"] is True


def test_original_failure_stays_original_while_same_text_recovers_in_sandbox():
    task = task_for()
    row, _ = solve(good_delivery(task), missing_intermediate_end(task), task)
    original_hash = digest(row)
    result = audit.audit_target(task, row, True, True)
    assert result["original"]["score"]["hard"] is False
    assert result["same_prompt_base_sensitivity"]["score"]["hard"] is True
    assert result["same_prompt_base_sensitivity"]["artifact_hash"] == digest(task.reference_files)
    assert result["same_prompt_base_sensitivity"]["base_interpretation"] == "same_revision_prompt_strict_initial_files"
    assert digest(row) == original_hash
    assert result["new_model_calls"] == 0 and result["primary_score_or_state_changed"] is False


def test_invalid_initial_recovery_is_separately_labelled_counterfactual():
    task = task_for()
    revision = "<<<FILE calculation.py>>>\n" + task.files["calculation.py"]
    row, _ = solve(missing_intermediate_end(task), revision, task)
    result = audit.audit_target(task, row, True, True)
    assert result["initial_public_only_sensitivity"]["score"]["hard"] is True
    assert result["same_prompt_base_sensitivity"]["score"]["hard"] is False
    assert result["counterfactual_recovered_initial_base"]["score"]["hard"] is True
    assert result["counterfactual_recovered_initial_base"]["base_interpretation"].startswith("counterfactual_")
    assert result["counterfactual_recovered_initial_base"]["revision_and_feedback_not_regenerated"] is True


def test_keep_after_invalid_initial_cannot_invent_a_valid_artifact():
    row, _ = solve(missing_intermediate_end(), "KEEP")
    result = audit.audit_target(task_for(), row, True, True)
    assert result["same_prompt_base_sensitivity"]["mode"] == "keep_after_invalid_initial_excluded"
    assert result["same_prompt_base_sensitivity"]["format_ok"] is False
    assert result["counterfactual_recovered_initial_base"] is None


def test_truncated_return_is_excluded_even_if_text_is_valid():
    row, _ = solve(good_delivery(), {"ok": False, "response": good_delivery()})
    result = audit.audit_target(task_for(), row, True, False)
    assert result["same_prompt_base_sensitivity"]["mode"] == "api_unavailable_excluded"
    assert result["same_prompt_base_sensitivity"]["score"]["hard"] is None


def test_initial_unavailable_does_not_become_counterfactual_reference():
    row, _ = solve({"ok": False, "response": missing_intermediate_end()}, missing_intermediate_end())
    result = audit.audit_target(task_for(), row, False, True)
    assert result["initial_public_only_sensitivity"]["mode"] == "api_unavailable_excluded"
    assert result["counterfactual_recovered_initial_base"] is None
    assert result["same_prompt_base_sensitivity"]["score"]["hard"] is True


def test_public_only_original_gate_never_silently_uses_private_tests():
    task = task_for()
    job = {"id": task.id, "skill": "", "stream": 0, "stage": "r0", "repeat": 0}
    api = FakeAPI([good_delivery(), missing_intermediate_end()])
    row = runtime.solve(api, task, "", key=digest(job), repeat=0, public_only=True)
    row.update(stream=0, stage="r0", split=task.split, job_hash=digest(job))
    result = audit.audit_target(task, row, True, True)
    assert result["same_prompt_base_sensitivity"]["score"]["total_tests"] == 2


def put(root, name, value):
    write_immutable_json(root / name, {"record": value, "record_hash": digest(value)})


def fixture_run(root):
    repo = Path(audit.__file__).resolve().parents[1]
    task = task_for()
    row, api = solve(good_delivery(), missing_intermediate_end())
    protocol = {"version": "coevolution-v4-engineering-v1", "rounds": [],
                "tasks_hash": digest({task.id: task.to_dict()}),
                "source_hashes": {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in audit.EXECUTOR_SOURCES}}
    put(root, "results.json", {"status": "complete", "protocol_hash": digest(protocol)})
    put(root, "protocol.json", protocol)
    put(root, "tasks.json", {task.id: task.to_dict()})
    put(root, "final_frozen.json", {"protocol_hash": digest(protocol), "freeze_before_final": True})
    put(root, "final_alias_plan.json", [])
    put(root, f"targets/{row['job_hash']}.json", row)
    for call in api.rows:
        write_immutable_json(root / "api" / "calls" / f"{call['request_hash']}.json", call)
    return row


def test_completed_run_audit_reads_frozen_tasks_and_never_modifies_run(tmp_path):
    root = tmp_path / "run"
    fixture_run(root)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")}
    result = audit.audit(root)
    assert result["summary"]["missing_terminator_recovered_jobs"] == 1
    assert result["summary"]["recovered_hard_pass_jobs"] == 1
    assert result["primary_scores_states_or_protocol_changed"] is False
    assert {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")} == before
    path = tmp_path / "audit" / "result.json"
    audit.publish(result, path)
    assert json.loads(path.read_text())["audit_sha256"] == result["audit_sha256"]


def test_no_read_or_execution_before_completion_barrier(tmp_path, monkeypatch):
    root = tmp_path / "run"
    put(root, "results.json", {"status": "running"})
    monkeypatch.setattr(audit.executor, "sandbox_probe", lambda: pytest.fail("incomplete run probed"))
    with pytest.raises(ValueError, match="completed"):
        audit.audit(root)
    reader = audit.Reader(root)
    with pytest.raises(ValueError, match="completion"):
        reader.read("tasks.json")


def test_output_inside_frozen_run_forbidden(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        audit.publish({"run": str(tmp_path / "run")}, tmp_path / "run" / "audit.json")


def test_symlink_and_source_changes_fail_closed(tmp_path):
    root = tmp_path / "run"
    fixture_run(root)
    protocol = root / "protocol.json"
    outside = tmp_path / "copied.json"
    outside.write_bytes(protocol.read_bytes())
    protocol.unlink()
    protocol.symlink_to(outside)
    with pytest.raises(ValueError, match="Symlinked"):
        audit.audit(root)


def test_wrong_api_response_or_receipt_prevents_audit(tmp_path):
    root = tmp_path / "run"
    row = fixture_run(root)
    path = root / "api" / "calls" / f"{row['request_hashes'][1]}.json"
    call = json.loads(path.read_text())
    call["response"] = "different returned text"
    path.write_text(json.dumps(call))
    with pytest.raises(ValueError, match="returned API text"):
        audit.audit(root)


def test_reader_detects_modified_inputs(tmp_path):
    root = tmp_path / "run"
    put(root, "results.json", {"status": "complete"})
    reader = audit.Reader(root)
    reader.read("results.json")
    (root / "results.json").write_text("modified")
    with pytest.raises(ValueError, match="changed"):
        reader.verify_unchanged()


def test_conditional_pairing_excludes_counterfactual_initial_base():
    task = task_for()
    left, _ = solve(good_delivery(), "KEEP")
    right, _ = solve(good_delivery(), missing_intermediate_end())
    records = {"base": audit.audit_target(task, left, True, True), "candidate": audit.audit_target(task, right, True, True)}
    result = audit.pair_accounting([{"reference_job": "base", "candidate_job": "candidate"}], records)
    assert result["original_both_strict_valid"]["eligible_pairs"] == 0
    assert result["same_prompt_base_both_recovered_valid"]["eligible_pairs"] == 1
    assert result["same_prompt_base_both_recovered_valid"]["hard_gain_sum"] == 0
    assert result["counterfactual_recovered_initial_base_excluded"] is True


def test_task_identity_mismatch_rejected():
    row, _ = solve(good_delivery(), "KEEP")
    with pytest.raises(ValueError, match="provenance"):
        audit.audit_target(replace(task_for(), prompt="other contract"), row, True, True)
