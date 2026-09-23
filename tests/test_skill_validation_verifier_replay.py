"""Fixture-only interface regression tests; never evidence of method efficacy."""
import json
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import natural_policy as policy
from skillopt.skill_validation import natural_verifier_replay as replay
from skillopt.validator_pilot.api import digest, write_immutable_json
from tests.test_skill_validation_checks import artifact, task, ScriptedExecutor
from tests.test_skill_validation_natural_policy import FakeCalls, development_view, plan, proposal, public_source


def test_revised_interface_accepts_only_complete_envelope_and_keeps_strict_fields(tmp_path):
    for arm in policy.ARMS[1:]:
        calls = FakeCalls(["```json\n" + plan() + "\n```", "```json\n" + json.dumps(proposal()) + "\n```"])
        result = policy.propose_policy(arm, development_view(), calls, tmp_path, interface_version=policy.REVISED_INTERFACE)
        assert result["status"] == "update"
        assert len(calls.requests) == 2
        first = json.loads(calls.requests[0]["user"])
        assert first["experiment_arm"] == arm
        assert "source_topics" in first if arm == "adaptive_research" else "source_topics" not in first
    bad = proposal()
    bad["policy"]["legal_boundary_instantiation"] = "Do not silently discard this field."
    calls = FakeCalls([plan(), "```json\n" + json.dumps(bad) + "\n```"])
    result = policy.propose_policy("adaptive_research", development_view(), calls, tmp_path / "bad",
                                   interface_version=policy.REVISED_INTERFACE)
    assert result["status"] == "invalid" and "Exact conditional" in result["failure_detail"]
    with pytest.raises(ValueError, match="interface changed"):
        policy.propose_policy("adaptive_research", development_view(), FakeCalls([]), tmp_path)


@pytest.mark.parametrize("raw", [
    'prefix ```json\n{}\n```', '```json\n{}', '```json\n{}\n``` suffix',
    '```json\n{"status":1,"status":2}\n```', '```json\n{"x":NaN}\n```',
])
def test_envelope_normalization_does_not_repair_malformed_json(raw):
    with pytest.raises(ValueError):
        policy._strict_decode(policy.normalize_json_envelope(raw))


def pool_group(part="development"):
    t = task()
    t = replace(t, contract=replace(t.contract, partition=part, prompt=t.contract.prompt + " Fixture: " + part))
    positions = []
    for condition in ("no_skill", "current", "candidate"):
        a = artifact(t, condition=condition)
        positions.append({"task": t, "artifact": a, "report": {}, "host": {
            "task_id": "TASK_ID_SENTINEL", "family_id": "FAMILY_SENTINEL", "repeat": 0,
            "condition": condition, "partition": part, "public_status": "pass",
            "status": "fail" if condition == "current" else "pass", "hidden_tests": "SECRET_H",
            "artifact_hash": a.content_hash, "audit_hash": digest(condition)}})
    return {t.contract.content_hash: positions}


def test_compact_view_removes_identities_and_hidden_bodies_but_attributes_dev_gap():
    groups = pool_group()
    encoded = json.dumps(replay.compact_development(groups))
    for secret in ("SECRET_H", "TASK_ID_SENTINEL", "FAMILY_SENTINEL", '"condition"', '"no_skill"', '"current"'):
        assert secret not in encoded
    assert "development_audit_summary" in encoded and "missed_error" in encoded
    with pytest.raises(ValueError, match="Development only"):
        replay.compact_development(pool_group("skill_confirmation"))


def test_revised_probe_contains_sources_without_host_labels():
    source = public_source()
    frozen = seal({"version": policy.VERSION, "arm": "adaptive_research", **proposal(),
                   "interface_version": policy.REVISED_INTERFACE, "sources": [{**source, "private": "SECRET_H"}]})
    t = task()
    _, user = policy.probe_messages(t, (artifact(t),), frozen)
    assert source["text"] in user and "SECRET_H" not in user
    for url in policy.SOURCE_TOPICS:
        assert policy.approved(url) == url


def test_pair_diagnostics_distinguish_regression_repair_shared_error_and_unknown():
    rows = []
    for repeat, (a, b) in enumerate((("pass", "fail"), ("fail", "pass"), ("fail", "fail"), ("unknown", "pass"))):
        for cond, status in (("no_skill", a), ("candidate", b)):
            rows.append({"task_id": "one", "family_id": "one", "repeat": repeat, "condition": cond,
                         "audit_status": status, "fixed_status": "pass", "new_status": status})
    result = replay.describe(rows)
    assert result["tasks"] == result["families"] == 1 and result["positions"] == 8
    assert result["paired_diagnostics"]["candidate_vs_no_skill"]["audit_vs_verifier"] == {
        "regression/regression": 1, "repair/repair": 1, "shared_error/shared_error": 1, "unknown/unknown": 1}
    assert result["new_detection"] == 4 and result["new_detection_families"] == 1


@pytest.mark.parametrize("interface", [policy.REVISED_INTERFACE, policy.INDEXED_INTERFACE])
def test_replay_end_to_end_preserves_unknown_and_never_grants_authority(tmp_path, monkeypatch, interface):
    pool = {part: pool_group(part) for part in replay.PARTS}
    # Calibration remains paired; confirmation keeps the frozen three conditions.
    for group in pool["verifier_calibration"].values():
        group[:] = [p for p in group if p["host"]["condition"] != "candidate"]
    source_rows = {part: [p["host"] for group in groups.values() for p in group] for part, groups in pool.items()}
    source = tmp_path / "source"
    monkeypatch.setattr(replay, "load_frozen", lambda *args: (
        seal({"fixture": True}), seal({"fixture": True}), seal({"fixture": True}), pool, source_rows))

    class API:
        def __init__(self, repo, root, **kwargs):
            self.root, self.model, self.service = root, "fixture", {"fixture": True}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def parallel(self, jobs, fn, label):
            return [fn(job) for job in jobs]

        def call(self, system, user, kind, key, max_tokens=2048, repeat=0):
            assert "SECRET_H" not in user and "TASK_ID_SENTINEL" not in user
            request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                       "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
            h = digest(request)
            path = self.root / "calls" / (h + ".json")
            if path.exists():
                return json.loads(path.read_text())
            if "policy-plan" in kind:
                response = plan()
            elif "policy-synthesis" in kind:
                response = json.dumps(proposal())
            else:
                assert kind.startswith("natural-replay-probes-")
                probe = {"kind": "expected", "calls": [{"args": [[1, 2]], "kwargs": {}}],
                         "expected": 3, "obligation_id": "returns", "rationale": "Public example."}
                if interface == policy.INDEXED_INTERFACE:
                    probe["contract_span_id"] = "s0"
                else:
                    probe["contract_quote"] = "Return the total for [1, 2]."
                response = json.dumps({"probes": [probe]})
            record = {"request": request, "request_hash": h, "ok": True, "response": response,
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "http_attempt_count": 1}
            write_immutable_json(path, record)
            return record

    monkeypatch.setattr(replay, "CachedAPI", API)
    executor = ScriptedExecutor([{"cleanup_confirmed": True}] * 20)
    executor.failed, executor.transport_identity = threading.Event(), {"fixture": True}
    root = tmp_path / "outputs/skill_validation/test"
    result = replay.run(tmp_path, source, root, executor, interface_version=interface)
    assert all(g["status"] == "pending" and not g["feedback_authorized"] for g in result["verifier_gates"].values())
    assert not result["final_access"] and result["new_solver_calls"] == result["skill_update_calls"] == 0
    assert result["cost"]["terminal_logical_requests"] == 8
    count = len(executor.calls)
    assert replay.run(tmp_path, source, root, executor, interface_version=interface) == result
    assert len(executor.calls) == count


def test_indexed_sources_select_exact_whitespace_without_inventing_evidence(tmp_path, monkeypatch):
    source = public_source()
    source["text"] = "A stable sort preserves\nthe relative order of equal elements."
    monkeypatch.setattr(policy, "fetch_sources", lambda *args: [source])
    selected = proposal(citations=[{"source_id": source["source_id"], "span_id": "s0"}])
    calls = FakeCalls([plan(urls=[source["url"]]), json.dumps(selected)])
    result = policy.propose_policy("adaptive_research", development_view(), calls, tmp_path,
                                   interface_version=policy.INDEXED_INTERFACE)
    assert result["status"] == "update"
    assert result["citations"][0]["quote"] == source["text"]
    assert result["citation_selection"][0]["span_id"] == "s0"
    for selection in [{"source_id": source["source_id"], "span_id": "missing"},
                      {"source_id": "missing", "span_id": "s0"},
                      {"source_id": source["source_id"], "span_id": "s0", "quote": "invented"}]:
        with pytest.raises(ValueError):
            policy.resolve_citation_ids({"citations": [selection]}, [source])


def test_indexed_contract_never_repairs_calls_expectations_or_unrecognized_ids():
    t = task()
    raw = {"probes": [{"kind": "expected", "calls": [{"args": [[1, 2]], "kwargs": {}}],
                       "expected": 12345, "obligation_id": "returns", "contract_span_id": "s0", "rationale": "hypothesis"}]}
    resolved = policy.resolve_probe_ids(raw, t)
    assert resolved["probes"][0]["expected"] == 12345  # A wrong answer remains wrong.
    assert resolved["probes"][0]["contract_quote"] in t.contract.prompt
    assert "contract_quote" not in raw["probes"][0]
    raw["probes"][0]["contract_span_id"] = "missing"
    with pytest.raises(ValueError, match="Unknown contract"):
        policy.resolve_probe_ids(raw, t)
    for span in policy.evidence_spans(("Words with newlines.\n" * 100)):
        assert 20 <= len(span["text"]) <= 400
