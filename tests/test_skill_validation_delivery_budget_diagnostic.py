"""All API/qualification/execution records are fabricated fixtures, no real A reads."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import delivery_budget_diagnostic as driver
from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.mechanism_tasks import build_panel, serialize_row
from skillopt.skill_validation.public_revision import solve_public_initial
from skillopt.skill_validation.rule_skill import Rule, RuleSkill, RuleUpdate, apply_update
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest
from tests.test_run_mechanism_case_feedback import FixtureAPI, reseal, write
from tests.test_skill_validation_public_revision import FixtureExecutor

SECRET = "HOST_AUDIT_SENTINEL_NEVER_IN_MODEL"


class DraftAPI(FixtureAPI):
    failures = False

    def __init__(self, *args, initial_health_policy="legacy_success_only", **kwargs):
        super().__init__(*args, **kwargs)
        self.service["model"] = self.model
        if initial_health_policy != "legacy_success_only":
            self.service["initial_health_policy"] = initial_health_policy

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        result = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if self.failures and kind == "public-initial":
            payload = json.loads(user)
            if max_tokens == 2048 and not payload["optional_skill"]:
                result = {**result, "ok": False, "response": "", "error_type": "truncated_content",
                    "finish_reason": "length", "status": 200,
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2048,
                              "completion_tokens_details": {"reasoning_tokens": 2048}}}
                write(self.root / "calls" / (result["request_hash"] + ".json"), result)
        return result


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(DraftAPI, "instances", [])
    monkeypatch.setattr(DraftAPI, "failures", False)
    monkeypatch.setattr(driver, "CachedAPI", DraftAPI)
    source, output = tmp_path / "source-A", tmp_path / "new-budget"
    executor = FixtureExecutor()
    rows = build_panel(20260925, 1, 24)["confirmation"]
    raw = [serialize_row(r) for r in rows]
    manifest = seal({"row_hashes": {"confirmation": [digest(r) for r in raw]}})
    api = DraftAPI(tmp_path, source / "api")
    protocol = seal({"service": api.service, "repeats": 2, "manifest_hash": manifest["record_hash"],
        "executor": executor.identity, "source_hashes": {name: hashlib.sha256(
            (Path(driver.__file__).parent / name).read_bytes()).hexdigest() for name in driver.FROZEN_MODULES}})
    namespace = digest([protocol["record_hash"], "h0"])
    calls = BoundedCalls(api, source / "histories/h0/budget", namespace, 313)
    parent = RuleSkill("fixture-h0", ())
    rule = Rule("fixture-local", "Fixture constraint", ("Check the stated public requirement.",),
                "When explicitly required.", (), ScopeRule(("requested_behavior",)), ("fixture-evidence",))
    raw_update = {"parent_hash": parent.content_hash, "edits": [{"operation": "add", "rule_id": rule.id,
        "rule": rule.to_dict(), "evidence_ids": ["fixture-evidence"], "reason": "Fixture only, not learned evidence."}]}
    local = apply_update(parent, RuleUpdate.from_dict(raw_update)).skill
    feedback_hash = digest("fixture-public-feedback")
    request = seal({"system": "Fixture proposal, no real model", "user": "Fixture public feedback",
        "parent_hash": parent.content_hash, "feedback_bundle_hash": feedback_hash,
        "evidence_catalog": [{"id": "fixture-evidence"}], "max_edits": 2})
    api.proposal_response = json.dumps(raw_update)
    receipt = calls.call(request["system"], request["user"], "same-feedback-rule-update")
    proposal = seal({"request": request, "api_receipt": receipt, "strategy": "local", "status": "candidate",
        "update": seal({"status": "candidate", "parent_hash": parent.content_hash, "candidate": local.to_dict()})})
    write(source / "histories/h0/updates/local.json", proposal)
    frozen = seal({"protocol_hash": protocol["record_hash"], "before_any_confirmation": True, "histories": {
        "h0": seal({"protocol_hash": protocol["record_hash"], "history": "h0", "feedback_hash": feedback_hash,
                    "update_statuses": {"local": "candidate"}, "skills": {"no_skill": parent.to_dict(), "local": local.to_dict()}})}})
    qualification = seal({"status": "qualified", "formal_eligible": True, "fixture_only": True,
                          "panel_hash": manifest["record_hash"]})
    write(source / "protocol.json", protocol)
    write(source / "summary.json", seal({"status": "completed_shadow_pilot", "protocol_hash": protocol["record_hash"],
                                        "freeze_hash": frozen["record_hash"]}))
    write(source / "frozen_candidates.json", frozen)
    write(source / "host_only/panel.json", seal({"manifest": manifest, "confirmation": raw, "unused_private": SECRET}))
    write(source / "qualification_summary.json", qualification)
    write(source / "frozen_panel.json", seal({"protocol_hash": protocol["record_hash"], "manifest_hash": manifest["record_hash"],
        "before_learning": True, "qualification_hash": qualification["record_hash"]}))
    roster = []
    for row in rows:
        for repeat in range(2):
            for condition, skill in (("no_skill", parent), ("local", local)):
                position = {"history": "h0", "task_id": row["task"].contract.task_id, "family_id": row["family_id"],
                    "region": row["region"], "domain": "coding", "repeat": repeat, "condition": condition, "exposure": "raw"}
                roster.append(position)
                base = source / "histories/h0/confirmation" / digest(position)
                artifact = solve_public_initial(row, driver.render_skill(skill), "no_skill" if condition == "no_skill" else "candidate",
                                                repeat, calls, base)
                write(base / "rule_result.json", seal({"initial_artifact_hash": artifact.content_hash}))
    write(source / "expected_positions.json", seal({"positions": roster}))
    write(source / "confirmation_rows.json", {"must_not_read_old_outcomes": SECRET})
    def audit(row, artifact, executor, root):
        # Every fresh call finishes before any hidden audit.
        assert (output / "all_drafts_frozen.json").exists()
        assert len(DraftAPI.instances[-1].fresh_requests) == 624
        timeout = artifact.availability == "available" and artifact.repeat == 0 and artifact.condition == "no_skill"
        status = "unknown" if timeout or artifact.availability != "available" else "pass"
        execution = ({"status": "execution_error", "reason": "execution_timeout", "cleanup_confirmed": True} if timeout else None)
        return seal({"status": status, "task_hash": row["task"].content_hash, "artifact_hash": artifact.content_hash,
                     "receipt": {"execution": execution} if execution else None, "fixture_only": True})
    monkeypatch.setattr(driver, "audit_row", audit)
    return source, output, executor


def test_prepare_complete_panel_zero_api_and_only_cap_changes(setup, tmp_path):
    source, output, executor = setup
    instances, executions = len(DraftAPI.instances), len(executor.calls)
    result = driver.run(tmp_path, source, output, executor, prepare=True)
    assert result["positions"] == 624 and result["new_model_calls"] == 0
    assert len(DraftAPI.instances) == instances and len(executor.calls) == executions
    frozen = driver._read(output / "frozen_inputs.json")
    roster = driver._read(output / "expected_positions.json")["positions"]
    assert len({p["task_id"] for p in roster}) == 78 and len({r["key"] for r in frozen["requests"]}) == 624
    grouped = {}
    for position, request in zip(roster, frozen["requests"]):
        assert SECRET not in request["system"] + request["user"]
        assert set(json.loads(request["user"])) == {"task", "optional_skill"}
        assert "later revision opportunity" in request["system"]
        grouped.setdefault((position["task_id"], position["repeat"], position["condition"]), []).append(request)
    for pair in grouped.values():
        assert {r["max_tokens"] for r in pair} == {2048, 4096}
        assert {k: v for k, v in pair[0].items() if k not in {"key", "max_tokens"}} == {
            k: v for k, v in pair[1].items() if k not in {"key", "max_tokens"}}
    for index in range(0, 624, 4):
        assert len({(p["task_id"], p["repeat"]) for p in roster[index:index + 4]}) == 1
        assert {(p["max_tokens"], p["condition"]) for p in roster[index:index + 4]} == {
            (cap, condition) for cap in driver.CAPS for condition in driver.CONDITIONS}
    assert not (output / "summary.json").exists()
    assert driver.run(tmp_path, source, output, executor, prepare=True) == result


def test_full_fixture_run_no_revisions_length_and_execution_timeout_separate(setup, tmp_path, monkeypatch):
    source, output, executor = setup
    monkeypatch.setattr(DraftAPI, "failures", True)
    result = driver.run(tmp_path, source, output, executor)
    assert result["status"] == "completed_delivery_diagnostic" and result["first_draft_only"]
    assert not result["independent_replication"] and not result["deployment_authorized"]
    assert result["accounting"]["terminal_logical_requests"] == 624
    assert result["accounting"]["by_kind"] == {"public-initial": 624}
    metrics = result["metrics"]
    assert metrics["missing_positions"] == 0
    assert metrics["arms"]["2048/no_skill"]["api_errors"] == {"truncated_content": 156}
    assert metrics["arms"]["4096/no_skill"]["execution_reasons"]["execution_timeout"] == 78
    assert metrics["arms"]["4096/no_skill"]["counts"] == {"pass": 78, "fail": 0, "unknown": 78}
    assert metrics["local_vs_base"]["2048"]["win"] == 0  # Unknown is not semantic failure.
    assert metrics["local_vs_base"]["2048"]["unknown"] == 156
    api = DraftAPI.instances[-1]
    assert all(r["max_tokens"] in driver.CAPS and r["kind"] == "public-initial" for r in api.requests)
    assert not {p.stem for p in (source / "api/calls").glob("*.json")} & {p.stem for p in (output / "api/calls").glob("*.json")}
    before = len(DraftAPI.instances), len(executor.calls)
    assert driver.run(tmp_path, source, output, executor) == result
    assert before == (len(DraftAPI.instances), len(executor.calls))


@pytest.mark.parametrize("tamper", ["candidate", "source_cap", "source_receipt", "source_intent", "missing_task", "source_checker", "incomplete"])
def test_source_changes_fail_before_new_api(setup, tmp_path, tamper):
    source, output, executor = setup
    if tamper in {"source_cap", "source_receipt", "source_intent"}:
        path = next((source / "histories/h0/confirmation").glob("*/public_initial/*.json"))
        initial = driver._read(path)
        key = initial["api_receipt"]["request_hash"]
        if tamper == "source_cap":
            initial["api_receipt"]["request"]["max_tokens"] = 4096
            write(path, reseal(initial))
        else:
            path = source / ("api/calls" if tamper == "source_receipt" else "histories/h0/budget/intents") / (key + ".json")
            path.unlink()
    else:
        path = source / {"candidate": "frozen_candidates.json", "missing_task": "expected_positions.json",
                         "source_checker": "protocol.json", "incomplete": "summary.json"}[tamper]
        value = driver._read(path)
        if tamper == "candidate":
            value["histories"]["h0"]["skills"]["local"]["rules"] = []
        elif tamper == "missing_task":
            value["positions"].pop()
        elif tamper == "source_checker":
            value["source_hashes"]["curriculum_tasks.py"] = "0" * 64
        else:
            value["status"] = "running"
        write(path, reseal(value))
    before = len(DraftAPI.instances)
    with pytest.raises((ValueError, FileNotFoundError)):
        driver.run(tmp_path, source, output, executor, prepare=True)
    assert len(DraftAPI.instances) == before


def test_interrupted_registered_request_not_retried_or_rescued_at_other_cap(setup, tmp_path):
    source, output, executor = setup
    driver.run(tmp_path, source, output, executor, prepare=True)
    protocol, frozen = driver._read(output / "protocol.json"), driver._read(output / "frozen_inputs.json")
    request = frozen["requests"][0]
    write(output / "budget/intents" / (digest(request) + ".json"),
          seal({"request_hash": digest(request), "protocol_hash": protocol["record_hash"]}))
    before = len(DraftAPI.instances)
    with pytest.raises(ValueError, match="Missing or oversized"):
        driver.run(tmp_path, source, output, executor)
    assert len(DraftAPI.instances) == before


def test_roster_and_metrics_retain_missing_unknown_not_success_or_failure(setup):
    source, _, _ = setup
    imported = driver.load_source(source)
    roster = driver.make_roster(imported["rows"], 42)
    assert roster == driver.make_roster(imported["rows"], 42)
    assert roster != driver.make_roster(imported["rows"], 43)
    result = driver.summarize([], roster)
    assert result["missing_positions"] == 624
    assert all(r["counts"] == {"pass": 0, "fail": 0, "unknown": 156} for r in result["arms"].values())


def test_original_global_2048_limit_is_unchanged(tmp_path):
    api = DraftAPI(tmp_path, tmp_path / "api")
    calls = BoundedCalls(api, tmp_path / "budget", digest("old"), 1)
    with pytest.raises(ValueError, match="output budget"):
        calls.call("system", "user", "public-initial", max_tokens=4096)


def _registered_fixture(tmp_path):
    api = DraftAPI(tmp_path, tmp_path / "api", initial_health_policy="completed_response_v1")
    namespace, requests = digest("registered-fixture"), []
    for index in range(312):
        for cap in driver.CAPS:
            prompt = {"system": "Fixture, no model", "user": json.dumps({"task": str(index), "optional_skill": ""}),
                      "kind": "public-initial", "repeat": 0, "max_tokens": cap}
            requests.append({**prompt, "key": digest({"protocol": namespace, **prompt}), "model": api.model, "service": api.service})
    return api, driver.RegisteredCalls(api, tmp_path / "budget", namespace, requests), requests


def test_terminal_failure_and_concurrent_calls_never_resample(tmp_path, monkeypatch):
    api, calls, requests = _registered_fixture(tmp_path)
    monkeypatch.setattr(DraftAPI, "failures", True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: calls.call(requests[0]), range(3)))
    assert all(r == results[0] and r["ok"] is False for r in results)
    assert len(api.fresh_requests) == len(api.requests) == 1
    calls.validate_existing()
    assert calls.call(requests[0]) == results[0] and len(api.requests) == 1
    (api.root / "calls" / (results[0]["request_hash"] + ".json")).unlink()
    with pytest.raises(ValueError, match="Missing or oversized"):
        calls.validate_existing()
    with pytest.raises(ValueError, match="Interrupted"):
        calls.call(requests[0])
    assert len(api.requests) == 1


def test_orphan_terminal_and_unregistered_caps_cannot_expand_run(tmp_path):
    api, calls, requests = _registered_fixture(tmp_path)
    request = requests[0]
    api.call(request["system"], request["user"], request["kind"], request["key"], max_tokens=2048, repeat=0)
    with pytest.raises(ValueError, match="Orphan"):
        calls.validate_existing()
    with pytest.raises(ValueError, match="Unregistered"):
        calls.call({**request, "max_tokens": 8192})
    assert len(api.requests) == 1


def test_execution_cost_counts_unique_receipts_not_positions():
    observed = {"execution_hash": digest("single-fixture-execution"), "execution_status": "execution_error",
                "execution_reason": "execution_timeout", "execution_duration_seconds": 10.0}
    result = driver.execution_accounting([observed, observed, {"execution_hash": None}])
    assert result["audit_position_count"] == 3 and result["positions_with_execution"] == 2
    assert result["unique_execution_receipts"] == 1 and result["reported_duration_seconds_sum_known"] == 10
    assert result["unique_execution_reasons"] == {"execution_timeout": 1}
