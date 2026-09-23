import json

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import probe_review as review
from skillopt.skill_validation.task_probes import parse_probes
from tests.test_skill_validation_checks import task


def proposed(t):
    return parse_probes({"probes": [{"kind": "expected", "calls": [{"args": [[1, 2]], "kwargs": {}}],
        "expected": 12345, "obligation_id": "returns", "contract_quote": "Return the total for [1, 2].",
        "rationale": "Fallible proposed expected value."}]}, t)


def test_review_view_is_public_only_and_does_not_repair_the_expectation():
    t = task()
    policy = seal({"sources": [{"status": "available", "source_id": "source", "text": "public documentation",
                                "private": "HIDDEN_SENTINEL"}], "hidden_audit": "HIDDEN_SENTINEL"})
    system, user = review.messages(t, proposed(t), policy)
    assert "HIDDEN_SENTINEL" not in user and "anonymous_implementations" not in user
    assert json.loads(user)["probes"][0]["expected"] == 12345
    assert "Never repair" in system


@pytest.mark.parametrize("raw", [
    {"checks": []}, {"checks": [{"probe_index": 0, "decision": "replace", "reason": "Change value"}]},
    {"checks": [{"probe_index": 0, "decision": "keep", "reason": "ok", "expected": 3}]},
    {"checks": [{"probe_index": True, "decision": "keep", "reason": "ok"}]},
    {"checks": [{"probe_index": 1, "decision": "keep", "reason": "wrong ID"}]},
])
def test_review_cannot_add_answers_skip_or_change_probe_identity(raw):
    with pytest.raises(ValueError): review.parse_review(json.dumps(raw), 1)


def test_review_exactly_covers_multiple_checks_without_duplicates():
    row = {"probe_index": 0, "decision": "keep", "reason": "A fallible opinion"}
    assert review.parse_review(json.dumps({"checks": [row]}), 1) == [row]
    with pytest.raises(ValueError): review.parse_review(json.dumps({"checks": [row, row]}), 2)


def test_abstention_retains_public_failures_and_reports_unknown_truthfully():
    r = seal({"probes": [{"status": "mismatch"}, {"status": "match"}, {"status": "unknown"}]})
    assert review.reviewed_prediction("pass", r, [0]) == "fail"
    assert review.reviewed_prediction("pass", r, [1]) == "pass"
    assert review.reviewed_prediction("pass", r, [2]) == "unknown"
    assert review.reviewed_prediction("pass", r, []) == "pass"  # Only original V passed.
    assert review.reviewed_prediction("fail", r, []) == "fail"
    assert review.reviewed_prediction("unknown", r, []) == "unknown"
    with pytest.raises(ValueError): review.reviewed_prediction("pass", r, [0, 0])


def test_real_replay_adapter_fixture(tmp_path, monkeypatch):
    from tests.test_skill_validation_verifier_replay import pool_group
    from skillopt.skill_validation.natural_verifier_replay import PARTS
    pool = {p: pool_group(p) for p in PARTS}
    for groups in pool.values():
        for group in groups.values():
            for position in group:
                position["host"]["task_id"] = position["task"].contract.original_task_id
    source = tmp_path / "source"
    protocol = seal({"source_root": str(tmp_path / "original")})
    review._write(source / "protocol.json", protocol)
    review._write(source / "results.json", seal({"protocol_hash": protocol["record_hash"], "final_access": False}))
    review._write(source / "frozen_policies.json", seal({"policies": {a: seal({"sources": []}) for a in review.ARMS[1:]}}))
    monkeypatch.setattr(review, "load_frozen", lambda *args: (None, None, None, pool, None))
    for arm in review.ARMS[1:]:
        for part in ("verifier_calibration", "skill_confirmation"):
            rows = []
            for group in pool[part].values():
                t = group[0]["task"]
                proposal = proposed(t)
                frozen = seal({"proposal": proposal})
                review._write(source / "probes" / arm / (t.contract.content_hash + ".json"), frozen)
                for p in group:
                    report = seal({"task_hash": t.contract.content_hash, "artifact_record_hash": p["artifact"].content_hash,
                        "proposal_hash": proposal["record_hash"], "status": "mismatch",
                        "probes": [{"probe": proposal["probes"][0], "status": "mismatch"}]})
                    review._write(source / "probe_execution" / arm / "reports" / (report["record_hash"] + ".json"), report)
                    h = p["host"]
                    rows.append({"task_id": h["task_id"], "family_id": h["family_id"], "repeat": h["repeat"],
                        "condition": h["condition"], "audit_status": h["status"], "fixed_status": "pass", "new_status": "fail",
                        "artifact_hash": h["artifact_hash"], "report_hash": report["record_hash"],
                        "proposal_hash": frozen["record_hash"]})
            review._write(source / "host_only" / (arm + "_" + part + ".json"), seal({"rows": rows}))
    class API:
        def __init__(self, repo, root, **kw): self.root, self.service = root, {"fixture": True}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def parallel(self, jobs, fn, label): return list(map(fn, jobs))
    class Calls:
        def __init__(self, *a): pass
        def call(self, system, user, kind, **kw):
            assert "HIDDEN_SENTINEL" not in user and "TASK_ID_SENTINEL" not in user
            return {"ok": True, "request_hash": "fixture", "response": json.dumps({"checks": [
                {"probe_index": 0, "decision": "abstain", "reason": "Unsupported expected value"}]})}
        def accounting(self): return {"fixture": True}
    monkeypatch.setattr(review, "CachedAPI", API)
    monkeypatch.setattr(review, "BoundedCalls", Calls)
    result = review.run(tmp_path, source, tmp_path / "outputs/skill_validation/review")
    assert result["deployment_authorized"] is False
    assert result["coverage"]["adaptive_no_research"]["verifier_calibration"]["retained_checks"] == 0
    assert result["metrics"]["adaptive_no_research"]["verifier_calibration"]["new_status"]["false_rejections"] == 0
