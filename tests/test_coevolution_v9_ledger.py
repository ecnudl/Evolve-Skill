"""Offline integrity tests: no credentials, API clients, or network requests."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v7 import transport
from skillopt.coevolution_v9 import study
from skillopt.validator_pilot.api import digest, write_immutable_json


class Clock:
    def __init__(self):
        self.value = 1000.0

    def wall(self):
        return self.value

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def save(path, value):
    Path(path).write_text(json.dumps(value))


def reseal(row):
    return seal({key: value for key, value in row.items() if key != "record_hash"})


def fixture(tmp_path, *, retry=False):
    root, service = tmp_path / "run", {
        "model": "glm-5.3", "host": "token.pjlab.org.cn", "path": "/v1/chat/completions",
        "temperature": 0, "stream": True, "stream_options": {"include_usage": True}, "reasoning_effort": "low"}
    api = root / "api"
    write_immutable_json(api / "service.json", service)
    write_immutable_json(api / "budget_protocol.json", {"max_logical_calls": 10, "model": "glm-5.3",
                                                       "workers": 4, "service_sha256": digest(service)})
    clock = Clock()
    pacer = transport._Pacer(api, study.PACING, service, clock)
    calls = {}
    for index in range(2):
        request = {"model": "glm-5.3", "service": service, "system": "system", "user": f"question {index}",
                   "kind": "v9_native_analyst", "key": f"h{index}", "max_tokens": 4096, "repeat": 0}
        identifier = digest(request)
        payload = {"model": "glm-5.3", "messages": [{"role": "system", "content": "system"},
            {"role": "user", "content": f"question {index}"}], "max_tokens": 4096, "temperature": 0,
            "stream": True, "stream_options": {"include_usage": True}, "reasoning_effort": "low"}
        wire_hash = digest({"method": "POST", "endpoint": "https://token.pjlab.org.cn/v1/chat/completions", "body": payload})
        attempts, references = [], []
        statuses = [429, 200] if retry and index == 0 else [200]
        for number, status in enumerate(statuses, 1):
            admission = pacer.admit(identifier, request["kind"], number, wire_hash)
            clock.value += 1
            cooldown = pacer.observe_response(admission, status, None)
            attempt = {"attempt": number, "ok": status == 200, "status": status,
                       "error_type": "http_status" if status == 429 else None, "wall_seconds": 1.0}
            outcome = pacer.finish(admission, attempt, cooldown)
            attempts.append(attempt)
            references.append({"sequence": admission["sequence"], "admission_hash": admission["record_hash"],
                               "attempt_receipt_hash": outcome["record_hash"]})
        row = {"request": request, "request_hash": identifier, "ok": True, "response": "native patch",
               "http_attempt_count": len(attempts), "attempts": attempts, "error_type": None, "usage": {},
               "pacing": {"protocol_hash": pacer.protocol_hash, "attempts": references}}
        row["transport_diagnostic"] = transport.classify_failure(row)
        write_immutable_json(api / "calls" / (identifier + ".json"), row)
        write_immutable_json(api / "budget_reservations" / (identifier + ".json"),
                             {"request_hash": identifier, "kind": request["kind"]})
        calls[identifier] = row
    return root, service, calls, pacer


def bytes_under(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def relink_admission(root, calls, sequence, **changes):
    """Change a sealed record and all hashes that refer to it, to test semantics."""
    admission_path = root / "api/pacing/admissions" / f"{sequence:08d}.json"
    admission = json.loads(admission_path.read_text())
    admission.update(changes)
    admission = reseal(admission)
    save(admission_path, admission)
    outcome_path = root / "api/pacing/attempts" / f"{sequence:08d}.json"
    outcome = json.loads(outcome_path.read_text())
    outcome["admission_hash"] = admission["record_hash"]
    outcome = reseal(outcome)
    save(outcome_path, outcome)
    call = calls[admission["request_hash"]]
    reference = next(row for row in call["pacing"]["attempts"] if row["sequence"] == sequence)
    reference.update(admission_hash=admission["record_hash"], attempt_receipt_hash=outcome["record_hash"])
    save(root / "api/calls" / (call["request_hash"] + ".json"), call)


@pytest.mark.parametrize("retry", [False, True])
def test_closed_ledger_reuses_native_checks_without_writes_or_client(tmp_path, monkeypatch, retry):
    root, _, _, _ = fixture(tmp_path, retry=retry)
    before = bytes_under(root)

    def forbidden(*_a, **_k):
        pytest.fail("Read-only audit must not instantiate clients or publish anything")

    monkeypatch.setattr(transport._Pacer, "__init__", forbidden)
    monkeypatch.setattr(transport.PacedCachedAPI, "__init__", forbidden)
    monkeypatch.setattr(transport, "write_immutable_json", forbidden)
    monkeypatch.setattr(study, "write_immutable_json", forbidden)
    ledger = study.closed_ledger(root, 10)
    assert ledger["pacing"]["http_attempt_admissions"] == (3 if retry else 2)
    assert ledger["pacing"]["cooldown_events"] == int(retry)
    assert ledger["pacing"]["wire_payload_hashes_verified"]
    assert bytes_under(root) == before


@pytest.mark.parametrize("name", ["protocol.json", "admissions/00000001.json", "attempts/00000001.json"])
def test_missing_pacing_evidence_rejected(tmp_path, name):
    root, _, _, _ = fixture(tmp_path)
    (root / "api/pacing" / name).unlink()
    with pytest.raises(ValueError):
        study.closed_ledger(root, 10)


def test_missing_cooldown_evidence_rejected(tmp_path):
    root, _, _, _ = fixture(tmp_path, retry=True)
    (root / "api/pacing/cooldowns/00000001.json").unlink()
    with pytest.raises(ValueError):
        study.closed_ledger(root, 10)


def test_resealed_wrong_pacing_policy_rejected(tmp_path):
    root, _, _, _ = fixture(tmp_path)
    path = root / "api/pacing/protocol.json"
    row = json.loads(path.read_text())
    row["policy"]["min_interval_seconds"] = 1
    save(path, reseal(row))
    with pytest.raises(ValueError, match="protocol"):
        study.closed_ledger(root, 10)


def test_relinked_wrong_wire_payload_rejected(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    relink_admission(root, calls, 1, http_request_hash="a" * 64)
    with pytest.raises(ValueError, match="wire payload"):
        study.closed_ledger(root, 10)


def test_relinked_wrong_request_kind_rejected(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    relink_admission(root, calls, 1, kind="undeclared")
    with pytest.raises(ValueError, match="wire payload"):
        study.closed_ledger(root, 10)


def test_relinked_minimum_interval_violation_rejected(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    relink_admission(root, calls, 2, admitted_monotonic=1005.0, admitted_wall=1005.0)
    with pytest.raises(ValueError, match="minimum interval"):
        study.closed_ledger(root, 10)


def test_resumed_process_uses_wall_interval_check(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    relink_admission(root, calls, 2, process_epoch="restart", admitted_monotonic=1.0, admitted_wall=1005.0)
    with pytest.raises(ValueError, match="minimum interval"):
        study.closed_ledger(root, 10)


def test_relinked_observed_cooldown_violation_rejected(tmp_path):
    root, _, calls, _ = fixture(tmp_path, retry=True)
    relink_admission(root, calls, 2, admitted_monotonic=1015.0, admitted_wall=1015.0)
    with pytest.raises(ValueError, match="shared cooldown"):
        study.closed_ledger(root, 10)


def test_missing_call_pacing_references_rejected(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    row = next(iter(calls.values()))
    row["pacing"]["attempts"] = []
    save(root / "api/calls" / (row["request_hash"] + ".json"), row)
    with pytest.raises(ValueError):
        study.closed_ledger(root, 10)


def test_extra_completed_http_attempt_outside_calls_rejected(tmp_path):
    root, _, _, pacer = fixture(tmp_path)
    admission = pacer.admit("b" * 64, "unplanned", 1, "c" * 64)
    pacer.finish(admission, {"attempt": 1, "ok": True, "status": 200, "error_type": None}, None)
    with pytest.raises(ValueError, match="outside"):
        study.closed_ledger(root, 10)


def test_unresolved_http_attempt_rejected(tmp_path):
    root, _, _, pacer = fixture(tmp_path)
    pacer.admit("b" * 64, "unplanned", 1, "c" * 64)
    with pytest.raises(ValueError, match="Unresolved"):
        study.closed_ledger(root, 10)


def test_changed_transport_failure_classification_rejected(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    row = next(iter(calls.values()))
    row["transport_diagnostic"]["classification"] = "success"
    save(root / "api/calls" / (row["request_hash"] + ".json"), row)
    with pytest.raises(ValueError, match="classification"):
        study.closed_ledger(root, 10)


def optimizer_fixture(tmp_path):
    root, _, calls, _ = fixture(tmp_path)
    planned = []
    for index, (identifier, receipt) in enumerate(calls.items()):
        write_immutable_json(root / "learning/history_0/optimizer/calls" / f"{index}.json",
                             seal({"receipt": receipt, "intent": {}}))
        planned.append(identifier)
    return root, calls, [{"history": 0, "optimizer_requests": planned}]


def test_optimizer_copy_binding_is_exact_and_readonly(tmp_path):
    root, _, histories = optimizer_fixture(tmp_path)
    before = bytes_under(root)
    assert study.verify_optimizer_receipts(root, histories) == {
        "verified_unique_optimizer_receipts": 2, "exact_actual_receipt_binding": True}
    assert bytes_under(root) == before


@pytest.mark.parametrize("field", ["response", "usage", "ok", "attempts"])
def test_modified_actual_optimizer_receipt_rejected_even_with_same_request(tmp_path, field):
    root, calls, histories = optimizer_fixture(tmp_path)
    row = deepcopy(next(iter(calls.values())))
    row[field] = {"response": "different", "usage": {"total_tokens": 1}, "ok": False, "attempts": []}[field]
    save(root / "api/calls" / (row["request_hash"] + ".json"), row)
    with pytest.raises(ValueError, match="differs"):
        study.verify_optimizer_receipts(root, histories)


@pytest.mark.parametrize("location", ["api", "copy"])
def test_missing_optimizer_receipt_rejected(tmp_path, location):
    root, _, histories = optimizer_fixture(tmp_path)
    directory = root / ("api/calls" if location == "api" else "learning/history_0/optimizer/calls")
    next(directory.glob("*.json")).unlink()
    with pytest.raises(ValueError):
        study.verify_optimizer_receipts(root, histories)


def test_unplanned_optimizer_receipt_rejected(tmp_path):
    root, _, histories = optimizer_fixture(tmp_path)
    histories[0]["optimizer_requests"].pop()
    with pytest.raises(ValueError, match="grid"):
        study.verify_optimizer_receipts(root, histories)


def test_duplicate_optimizer_position_rejected(tmp_path):
    root, _, histories = optimizer_fixture(tmp_path)
    histories[0]["optimizer_requests"].append(histories[0]["optimizer_requests"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        study.verify_optimizer_receipts(root, histories)


def test_zero_optimizer_calls_remain_a_valid_no_change_history(tmp_path):
    assert study.verify_optimizer_receipts(tmp_path, [{"history": 0, "optimizer_requests": []}])[
        "verified_unique_optimizer_receipts"] == 0
