"""Synthetic MockHTTP plumbing fixtures, never model or benchmark efficacy evidence."""

import hashlib
import json
import shutil
import threading
from pathlib import Path

import httpx
import pytest

from scripts import audit_coevolution_v7 as audit
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import experiment as e
from skillopt.coevolution_v7 import research, transport
from skillopt.coevolution_v7.tasks import calibration_tasks, development_tasks, final_coding_tasks, final_native_tasks
from skillopt.validator_pilot.api import digest


class Clock:
    def __init__(self):
        self.value, self.lock = 0.0, threading.Lock()

    def monotonic(self):
        with self.lock:
            return self.value

    def wall(self):
        with self.lock:
            return 1700000000 + self.value

    def sleep(self, seconds):
        with self.lock:
            self.value += seconds


def fake_reply(system, p, tasks):
    if "parent_candidate" in p:
        return ("Preserve the current task contract, check dependencies before local edits, test affected and unaffected "
                "constraints, and use a base fallback if evidence is incomplete. Do not impose source delivery syntax "
                "on other task domains. Offline fixture candidate " + digest(p)[:12] + ".")
    if isinstance(p.get("development_evidence"), dict):
        ref = next(iter(p["development_evidence"]["evidence_catalog"].values()))["reference"]
        if '"explanations"' in system:
            return {"explanations": [
                {"hypothesis": "Legal boundary coverage might be incomplete.", "check": "Try allowed boundaries.", "evidence_refs": [ref]},
                {"hypothesis": "Current behavior may already be correct.", "check": "Inspect actual evidence.", "evidence_refs": [ref]}],
                "questions": [{"topic": "semantics", "question": "What does sorted preserve?"}],
                "urls": ["https://docs.python.org/3/library/functions.html#sorted"] if "one to three distinct" in system else []}
        if '"findings"' in system:
            return {"findings": [{"finding_id": "f1", "check_id": "coding_probe", "kind": "coverage_hypothesis",
                "hypothesis": "Legal boundary tests could reveal missing coverage, not a confirmed failure.",
                "proposedtest": "Test legal boundaries and an unaffected control.", "uncertainty": "Finite synthetic evidence only.",
                "evidence_refs": [ref], "evidenceurls": [], "evidencequotes": []}],
                "limits": ["A fake API fixture is not an observed research finding."]}
        return {"changes": [{"check_id": "coding_probe", "search": "Try legal boundaries and unaffected controls.",
                    "when": "Only within the active public contract.", "limits": "Finite tests do not prove safety.",
                    "finding_ids": ["f1"]}], "rationale": "Offline schema fixture, no discovered model effect.", "source_refs": []}
    adapter = tasks[p["task"]["id"]]
    if "current_code" in p:
        return {"inputs": [adapter.task.public_cases[0]["input"]]}
    if p.get("stage") == "revision" or "initial_artifact" in p:
        return "KEEP"
    if isinstance(adapter, audit.CodingAdapter):
        files = adapter.task.reference_files if p["skill"] else adapter.task.files
        return "\n".join("<<<FILE " + name + ">>>\n" + files[name] + "\n<<<END FILE>>>"
                         for name in adapter.task.editable_paths)
    return adapter.task["reference_artifact"]


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        repo = tmp_path_factory.mktemp("v7-paced-audit-offline")
        (repo / ".env").write_text("PJLAB_BASE_URL=https://token.pjlab.org.cn/v1\nPJLAB_MODEL=glm-5.3\n"
                                   "PJLAB_API_KEY=OFFLINE-NOT-A-REAL-KEY\n")
        sentinel = repo / "frozen_fixture.txt"
        sentinel.write_text("Offline source identity sentinel, not a production protocol.")
        mp.setattr(e.Study, "_sources", lambda _: {sentinel.name: hashlib.sha256(sentinel.read_bytes()).hexdigest()})
        def unavailable(*args, **kwargs):
            raise OSError("Offline fixture never fetches documents")
        mp.setattr(research, "fetch_sources", unavailable)
        natives = final_native_tasks()
        native_domains = sorted({a.domain for a in natives})
        panel = {"development": development_tasks(), "calibration": calibration_tasks(),
                 "final": final_coding_tasks()[:1] + [next(a for a in natives if a.domain == d) for d in native_domains]}
        tasks = {e.identifier(a): a for rows in panel.values() for a in rows}
        requests = []
        def handler(request):
            body = json.loads(request.content)
            system, user = [m["content"] for m in body["messages"]]
            reply = fake_reply(system, json.loads(user), tasks)
            requests.append(digest(body))
            response = json.dumps(reply) if not isinstance(reply, str) else reply
            return httpx.Response(200, json={"model": "glm-5.3", "choices": [
                {"message": {"content": response}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}})
        def factory(repo, root, max_calls, workers):
            client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False)
            return transport.make_budgeted_api(repo, root, max_calls=max_calls, workers=workers,
                                              http_client=client, clock=Clock(), stream=False)
        study = e.Study(repo, repo / "outputs/coevolution_v7/offline", histories=1, blocks=1, panel=panel)
        result = study.run(api_factory=factory)
        assert result["research"]["proposed_rubric"] is not None, "Fake fixtures must cover all three Research stages"
        yield repo, study.root, result, requests


def mutate(path, callback, *, sealed=True, field="record_hash"):
    value = json.loads(path.read_text())
    callback(value)
    if sealed:
        value.pop(field, None)
        value = core.seal(value, field)
    path.write_text(json.dumps(value, ensure_ascii=False))


@pytest.fixture
def copy_run(completed, tmp_path):
    repo, run, _, _ = completed
    shutil.copytree(repo, tmp_path / "repo")
    return tmp_path / "repo", tmp_path / "repo" / run.relative_to(repo)


def test_complete_actual_paced_receipts_research_calibration_and_native(completed):
    repo, run, result, requests = completed
    report = audit.audit(run, repo)
    assert report["complete"] and report["approved_deployment_scope"] == []
    assert report["api"]["ledger"]["cached_logical_calls"] == len(requests)
    assert report["pacing"] == result["pacing"]
    assert report["pacing"]["http_attempt_admissions"] == len(requests)
    assert report["old_a_exactly_shared"]
    assert report["unique_final_trajectories"] == 9
    assert report["logical_final_rows"] == 15
    assert not report["validator_activation"]["activate_next_round"]


def test_auditor_never_constructs_api_executes_oracle_or_writes(completed, monkeypatch):
    repo, run, _, requests = completed
    before = len(requests)
    def forbidden(*args, **kwargs):
        raise AssertionError("Audit must be read-only, offline and without artifact reexecution")
    monkeypatch.setattr(transport, "make_budgeted_api", forbidden)
    monkeypatch.setattr(transport.PacedCachedAPI, "__init__", forbidden)
    monkeypatch.setattr(audit.CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(audit.prior.NativeAdapter, "evaluate", forbidden)
    monkeypatch.setattr(audit.coding.executor, "evaluate", forbidden)
    monkeypatch.setattr(audit.coding.executor, "execute_inputs", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    original_read = Path.read_text
    def read_without_credentials(path, *args, **kwargs):
        assert not path.name.startswith(".env"), "Audit must never read credentials"
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_without_credentials)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    assert audit.audit(run, repo)["complete"]
    assert len(requests) == before


def test_partial_snapshot_requires_explicit_opt_in(copy_run):
    repo, run = copy_run
    (run / "results.json").unlink()
    with pytest.raises(ValueError, match="Completed V7"):
        audit.audit(run, repo)
    result = audit.audit(run, repo, require_complete=False)
    assert not result["complete"] and result["verdict"] == "partial_snapshot_only"


@pytest.mark.parametrize("relative", ["private_preflight.json", "private_final_preflight.json", "research_selection.json",
                                    "final_frozen.json", "calibration_rows.json", "source_next/h0.json"])
def test_complete_missing_stage_fails_closed(copy_run, relative):
    repo, run = copy_run
    (run / relative).unlink()
    with pytest.raises((ValueError, OSError)):
        audit.audit(run, repo)


@pytest.mark.parametrize("directory", ["api/calls", "api/budget_reservations", "api/pacing/admissions", "api/pacing/attempts",
                                     "targets", "feedback_probes", "calibration_calls"])
def test_missing_actual_execution_or_http_receipt_never_regenerated(copy_run, directory):
    repo, run = copy_run
    next((run / directory).glob("*.json")).unlink()
    with pytest.raises((ValueError, KeyError, OSError)):
        audit.audit(run, repo)


def test_source_drift_detected(copy_run):
    repo, run = copy_run
    (repo / "frozen_fixture.txt").write_text("drift")
    with pytest.raises(ValueError, match="source changed"):
        audit.audit(run, repo)


@pytest.mark.parametrize("relative,callback", [
    ("calibration_manifest.json", lambda v: v["artifacts"][0].update(truth="bad")),
    ("calibration_rows.json", lambda v: v["rows"][0].update(outcome="unknown")),
    ("calibration_rows.json", lambda v: v["rows"].pop()),
    ("validator_activation.json", lambda v: v.update(activate_next_round=True)),
    ("final_frozen.json", lambda v: v["interventions"][0]["skills"].update(gated_validator_routed="unapproved")),
    ("final_rows.json", lambda v: v["rows"][0].update(skill_hash=digest("wrong"))),
    ("final_rows.json", lambda v: v["rows"][0].update(all_solver_stages_api_ok=False)),
    ("final_rows.json", lambda v: v["rows"].pop()),
    ("research_selection.json", lambda v: v["packet_hashes"].reverse()),
    ("skill_proposals/h0-fixed.json", lambda v: v["feedback_hashes"].pop()),
    ("results.json", lambda v: v.update(protocol_hash=digest("wrong"))),
])
def test_resealed_logical_tampering_rejected(copy_run, relative, callback):
    repo, run = copy_run
    mutate(run / relative, callback)
    with pytest.raises((ValueError, KeyError)):
        audit.audit(run, repo)


def test_audit_detects_resealed_spacing_violation(copy_run):
    repo, run = copy_run
    paths = sorted((run / "api/pacing/admissions").glob("*.json"))
    first = json.loads(paths[0].read_text())
    mutate(paths[1], lambda v: v.update(admitted_monotonic=first["admitted_monotonic"], admitted_wall=first["admitted_wall"]))
    with pytest.raises(ValueError):
        audit.audit(run, repo)


@pytest.mark.parametrize("kind", ["v5_coding_generate", "v6_native_generate", "v7_rubric_patch", "v5_validator_probe"])
def test_actual_response_tamper_cannot_hide_behind_unchanged_request_hash(copy_run, kind):
    repo, run = copy_run
    path = next(p for p in (run / "api/calls").glob("*.json") if json.loads(p.read_text())["request"]["kind"] == kind)
    mutate(path, lambda v: v.update(response="not the actually delivered response"), sealed=False)
    with pytest.raises(ValueError):
        audit.audit(run, repo)


def test_control_receipt_phase_cannot_be_resealed_as_development(copy_run):
    repo, run = copy_run
    path = next((run / "calibration_calls").glob("*.json"))
    def corrupt(value):
        row = value["result"]["assessments"][0]
        row["phase"] = "development"
        row.pop("receipt_hash")
        value["result"]["assessments"][0] = core.seal(row, "receipt_hash")
    mutate(path, corrupt)
    with pytest.raises(ValueError, match="promotion|Calibration"):
        audit.audit(run, repo)
