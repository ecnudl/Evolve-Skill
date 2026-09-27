"""Fixture-only confirmation integration: no API, SSH, or original A results."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_mechanism_case_feedback as proposal_driver
from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import mechanism_case_confirmation as driver
from skillopt.skill_validation.mechanism_case_feedback import CALL_KIND
from skillopt.skill_validation.mechanism_study import _collect_development
from skillopt.skill_validation.mechanism_tasks import build_panel, serialize_row
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest
from tests.test_run_mechanism_case_feedback import FixtureAPI, reseal, write
from tests.test_skill_validation_public_revision import FixtureExecutor


class ConfirmationAPI(FixtureAPI):
    proposal_modes = {}
    fail_solver = False

    def __init__(self, *args, initial_health_policy="legacy_success_only", **kwargs):
        super().__init__(*args, **kwargs)
        if initial_health_policy != "legacy_success_only":
            self.service["initial_health_policy"] = initial_health_policy

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        if kind == CALL_KIND:
            mode = self.proposal_modes.get(repeat, "candidate")
            payload = json.loads(user)
            if mode == "candidate":
                evidence = payload["evidence_catalog"][0]["id"]
                rule = {"id": "public-preservation", "mechanism": "Constraint Preservation",
                    "procedure": ["Check explicitly preserved inputs before and after the change."],
                    "when": "The public contract explicitly preserves input.",
                    "exceptions": ["Do not preserve input when in-place replacement is required."],
                    "scope": {"required_obligation_kinds": ["input_preservation"], "forbidden_obligation_kinds": []},
                    "evidence_ids": [evidence]}
                response = json.dumps({"parent_hash": payload["parent_hash"], "edits": [
                    {"operation": "add", "rule_id": rule["id"], "rule": rule,
                     "evidence_ids": [evidence], "reason": "Fixture only, not semantic evidence support."}]})
            else:
                response = mode
            self.proposal_response, self.proposal_ok = response, mode != "api_failure"
        value = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if self.fail_solver and kind == "public-initial":
            value = {**value, "ok": False, "response": ""}
            write(self.root / "calls" / (value["request_hash"] + ".json"), value)
        return value


def source_fixture(tmp_path, *, histories=1):
    """Small valid registrations with fixture receipts and explicitly fake qualification."""
    source, executor = tmp_path / "A", FixtureExecutor()
    panel = build_panel(20260925, 1, 1)
    rows = {p: panel[p][:3] for p in ("development", "confirmation")}
    raw = {p: [serialize_row(r) for r in values] for p, values in rows.items()}
    manifest = seal({"version": "fixture", "row_hashes": {p: [digest(r) for r in values]
                                                          for p, values in raw.items()}})
    api = ConfirmationAPI(tmp_path, source / "api")
    protocol = seal({"version": "fixture-source", "manifest_hash": manifest["record_hash"],
        "histories": histories, "repeats": 1, "seed": 20260925, "service": api.service,
        "source_hashes": {name: hashlib.sha256((Path(driver.__file__).parent / name).read_bytes()).hexdigest()
                          for name in driver.FROZEN_EXECUTION_MODULES},
        "executor": executor.identity, "parent": "same_empty_RuleSkill_per_history",
        "one_public_revision_all_conditions": True, "solver_updater_token_cap": 2048})
    qualification = seal({"status": "qualified", "formal_eligible": True, "fixture_override_only": True,
                          "panel_hash": manifest["record_hash"]})
    write(source / "protocol.json", protocol)
    write(source / "host_only/panel.json", seal({"manifest": manifest, **raw}))
    write(source / "qualification_summary.json", qualification)
    write(source / "frozen_panel.json", seal({"protocol_hash": protocol["record_hash"],
        "manifest_hash": manifest["record_hash"], "qualification_hash": qualification["record_hash"],
        "before_learning": True}))
    for index in range(histories):
        history = f"h{index}"
        parent = RuleSkill("fixture-cold-" + history, ())
        base = source / "histories" / history
        calls = BoundedCalls(api, base / "budget", digest(["fixture", history]), 24)
        bundle = _collect_development(rows["development"], parent, calls, executor, base / "development", api, 1)
        write(base / "parent.json", seal({"skill": parent.to_dict()}))
        write(base / "feedback.json", bundle)
    # Invalid sentinels would fail immediately if any A results were read.
    write(source / "summary.json", {"FORBIDDEN_A_OUTCOMES": True})
    write(source / "confirmation_rows.json", {"FORBIDDEN_A_OUTCOMES": True})
    return source, executor


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(ConfirmationAPI, "instances", [])
    monkeypatch.setattr(ConfirmationAPI, "proposal_modes", {})
    monkeypatch.setattr(ConfirmationAPI, "fail_solver", False)
    monkeypatch.setattr(proposal_driver, "CachedAPI", ConfirmationAPI)
    monkeypatch.setattr(driver, "CachedAPI", ConfirmationAPI)
    monkeypatch.setattr(driver, "audit_row", lambda *a: seal({"status": "pass", "receipt": None, "fixture_only": True}))

    def build(*, modes=None, histories=1, proposal_repeats=2):
        source, executor = source_fixture(tmp_path, histories=histories)
        ConfirmationAPI.proposal_modes = modes or {}
        proposals, output = tmp_path / "B", tmp_path / "C"
        proposal_driver.run(tmp_path, source, proposals, executor, workers=1, repeats=proposal_repeats)
        return source, proposals, output, executor
    return build


def test_primary_repeat_only_freezes_before_all_execution_and_reuses_no_A_calls(setup, tmp_path, monkeypatch):
    source, proposals, output, executor = setup(histories=2)
    original_calls = executor.run
    def guarded(*args, **kwargs):
        frozen = verify(json.loads((output / "frozen_candidates.json").read_text()))
        assert frozen["before_any_confirmation"] and set(frozen["skills"]) == {"h0", "h1"}
        return original_calls(*args, **kwargs)
    monkeypatch.setattr(executor, "run", guarded)
    result = driver.run(tmp_path, source, proposals, output, executor, workers=1)
    assert result["status"] == "completed_shadow_confirmation"
    assert result["provenance"] == "engineering_fixture"
    assert result["shared_holdout_exploratory_extension"] and not result["independent_replication"]
    assert not result["deployment_authorized"] and not result["research_increment_evaluated"]
    protocol = driver._read(output / "protocol.json")
    assert protocol["version"] == driver.VERSION and protocol["original_solver_payload_unchanged"]
    assert protocol["api_source_hash"] == hashlib.sha256(Path(driver.api_module.__file__).read_bytes()).hexdigest()
    assert protocol["service"] == {**driver._read(source / "protocol.json")["service"],
                                   "initial_health_policy": "completed_response_v1"}
    assert "initial_health_policy" not in driver._read(proposals / "protocol.json")["service"]
    rows = driver._read(output / "confirmation_rows.json")["rows"]
    assert len(rows) == 2 * 3 * 4 * 2
    api = ConfirmationAPI.instances[-1]
    assert api.root == output / "api" and api.fresh_requests
    assert all(r["kind"] in {"public-initial", "public-revision"} and r["max_tokens"] == 2048 for r in api.requests)
    initial = [r for r in api.fresh_requests if r["kind"] == "public-initial"]
    assert len(initial) == 2 * 3 * 2  # empty and actual learned text, separately per history
    assert all(not r["skill_applied"] for r in rows if r["condition"] in {"no_skill", "current"})
    assert result["accounting"]["terminal_logical_requests"] == len(api.fresh_requests)
    source_requests = {p.stem for p in (source / "api/calls").glob("*.json")}
    assert not source_requests & {p.stem for p in (output / "api/calls").glob("*.json")}
    assert all(not r["predeclared_near_duplicate"] for r in rows)
    calls_before, api_before = len(executor.calls), len(ConfirmationAPI.instances)
    assert driver.run(tmp_path, source, proposals, output, executor, workers=1) == result
    assert len(executor.calls) == calls_before and len(ConfirmationAPI.instances) == api_before


@pytest.mark.parametrize("mode,status", [("NO_UPDATE", "no_update"), ("{broken", "invalid"), ("api_failure", "api_failure")])
def test_no_primary_change_stops_even_when_stability_repeat_is_candidate(setup, tmp_path, mode, status):
    source, proposals, output, executor = setup(modes={0: mode, 1: "candidate"})
    executions, instances = len(executor.calls), len(ConfirmationAPI.instances)
    result = driver.run(tmp_path, source, proposals, output, executor)
    assert result["status"] == "no_changed_primary_candidates"
    assert result["update_statuses"] == {"h0": {arm: status for arm in driver.ARMS}}
    assert result["executed_positions"] == 0 and result["metrics"] is None
    assert not result["method_effect_evaluated"] and not result["new_behavioral_learning"]
    assert result["accounting"]["http_attempts"] == 0
    assert len(executor.calls) == executions and len(ConfirmationAPI.instances) == instances
    assert not (output / "api").exists()
    frozen = driver._read(output / "frozen_candidates.json")
    assert all(not s["rules"] for s in frozen["skills"]["h0"].values())


def test_unknown_retained_and_failed_solver_receipts_accounted(setup, tmp_path, monkeypatch):
    source, proposals, output, executor = setup()
    monkeypatch.setattr(ConfirmationAPI, "fail_solver", True)
    monkeypatch.setattr(driver, "audit_row", lambda *a: seal({"status": "unknown", "receipt": None}))
    result = driver.run(tmp_path, source, proposals, output, executor, workers=1)
    assert result["accounting"]["terminal_failures"] > 0
    assert result["metrics"]["missing_positions"] == 0
    for arm in result["metrics"]["arms"].values():
        assert arm["counts"]["unknown"] == 3
        assert arm["all_attempt_success"]["denominator"] == 3


def test_missing_interrupted_solver_receipt_is_not_resampled(setup, tmp_path):
    source, proposals, output, executor = setup()
    driver.run(tmp_path, source, proposals, output, executor, workers=1)
    # Simulate interruption before terminal summary with a reserved missing call.
    (output / "summary.json").unlink()
    receipt = next((output / "api/calls").glob("*.json"))
    receipt.unlink()
    instances = len(ConfirmationAPI.instances)
    with pytest.raises(ValueError, match="Interrupted API request"):
        driver.run(tmp_path, source, proposals, output, executor, workers=1)
    assert len(ConfirmationAPI.instances) == instances  # Fails even before reopening the API context.


@pytest.mark.parametrize("tamper", ["missing_receipt", "missing_intent", "feedback", "parent", "proposal_record",
                                     "manifest_row", "unfrozen", "unqualified", "summary_selection", "details"])
def test_broken_source_or_proposal_binding_fails_before_spending(setup, tmp_path, tamper):
    source, proposals, output, executor = setup()
    selected = proposals / "histories/h0/updates/boolean-0.json"
    record = driver._read(selected)
    if tamper in {"missing_receipt", "missing_intent"}:
        subpath = "api/calls" if tamper == "missing_receipt" else "budget/intents"
        (proposals / subpath / (record["api_receipt"]["request_hash"] + ".json")).unlink()
    else:
        path = {"feedback": proposals / "histories/h0/source_feedback.json",
                "parent": proposals / "histories/h0/source_parent.json", "proposal_record": selected,
                "manifest_row": source / "host_only/panel.json", "unfrozen": source / "frozen_panel.json",
                "unqualified": source / "qualification_summary.json", "summary_selection": proposals / "summary.json",
                "details": proposals / "histories/h0/details.json"}[tamper]
        value = driver._read(path)
        if tamper == "feedback":
            value["fake"] = True
        elif tamper == "parent":
            value["skill"]["history_id"] = "foreign-parent"
        elif tamper == "proposal_record":
            value["status"] = "no_update"
        elif tamper == "manifest_row":
            value["confirmation"][0]["region"] = "unrelated"
        elif tamper == "unfrozen":
            value["before_learning"] = False
        elif tamper == "unqualified":
            value["status"] = "pending"
        elif tamper == "summary_selection":
            value["rows"][0]["record_hash"] = digest("different")
        elif tamper == "details":
            value["parent_hash"] = digest("different")
        write(path, reseal(value))
    executions, instances = len(executor.calls), len(ConfirmationAPI.instances)
    with pytest.raises((ValueError, FileNotFoundError)):
        driver.run(tmp_path, source, proposals, output, executor, workers=1)
    assert len(executor.calls) == executions and len(ConfirmationAPI.instances) == instances


def test_source_reader_never_opens_A_outcomes_and_prompts_never_contain_host_labels(setup, tmp_path, monkeypatch):
    source, proposals, output, executor = setup()
    read, accessed = driver._read, []
    def guard(path):
        if path.is_relative_to(source):
            relative = str(path.relative_to(source))
            assert relative in {"protocol.json", "host_only/panel.json", "frozen_panel.json", "qualification_summary.json",
                                "histories/h0/parent.json", "histories/h0/feedback.json"}
            accessed.append(relative)
        return read(path)
    monkeypatch.setattr(driver, "_read", guard)
    monkeypatch.setattr(proposal_driver, "_read", guard)
    driver.run(tmp_path, source, proposals, output, executor, workers=1)
    assert "host_only/panel.json" in accessed
    for request in ConfirmationAPI.instances[-1].requests:
        prompt = request["system"] + request["user"]
        for forbidden in ("host_only", "audit_runner", "target_related", "boundary_control", "FORBIDDEN_A_OUTCOMES"):
            assert forbidden not in prompt


@pytest.mark.parametrize("name", ["A", "B"])
def test_output_cannot_overwrite_or_nest_in_old_runs(setup, tmp_path, name):
    source, proposals, _, executor = setup()
    for output in (tmp_path / name, tmp_path / name / "new", tmp_path):
        with pytest.raises(ValueError, match="outside"):
            driver.run(tmp_path, source, proposals, output, executor)


def test_changed_runtime_protocol_cannot_resume(setup, tmp_path):
    source, proposals, output, executor = setup(modes={0: "NO_UPDATE"})
    driver.run(tmp_path, source, proposals, output, executor, workers=1)
    with pytest.raises(ValueError):
        driver.run(tmp_path, source, proposals, output, executor, workers=2)


def test_predeclared_near_duplicates_are_bound_not_removed(tmp_path):
    tasks = {f"task-{n}" for n in range(78)}
    excluded = sorted(tasks)[:4]
    plan = {"kind": "analysis_plan_not_experimental_result", "primary_confirmation_tasks": 78,
            "additional_sensitivity_excluded_task_ids": excluded}
    write(tmp_path / driver.SENSITIVITY, plan)
    frozen = driver._sensitivity(tmp_path, {"service": {"fixture": False}}, tasks)
    assert frozen["additional_sensitivity_excluded_task_ids"] == excluded
    assert not frozen["main_panel_filtered"] and len(tasks) == 78
    assert frozen["plan_sha256"] == hashlib.sha256((tmp_path / driver.SENSITIVITY).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="four-task"):
        driver._sensitivity(tmp_path, {"service": {}}, tasks - {excluded[0]})


@pytest.mark.parametrize("name", driver.FROZEN_EXECUTION_MODULES)
def test_original_adapter_and_solver_sources_must_match_even_for_fixtures(setup, tmp_path, name):
    source, proposals, output, executor = setup()
    protocol = driver._read(source / "protocol.json")
    protocol["source_hashes"][name] = digest("another-protocol-implementation")
    protocol = reseal(protocol)
    write(source / "protocol.json", protocol)
    frozen = driver._read(source / "frozen_panel.json")
    frozen["protocol_hash"] = protocol["record_hash"]
    write(source / "frozen_panel.json", reseal(frozen))
    executions, instances = len(executor.calls), len(ConfirmationAPI.instances)
    with pytest.raises(ValueError, match="original frozen execution/solver adapter"):
        driver.run(tmp_path, source, proposals, output, executor)
    assert len(executor.calls) == executions and len(ConfirmationAPI.instances) == instances


def test_cli_forwards_dedicated_transport_and_proxy(tmp_path, monkeypatch):
    seen = {}
    class Transport:
        def __init__(self, remote, **kwargs): seen.update(remote=remote, transport=kwargs)
        def close(self): seen["closed"] = True
    def fake_run(repo, source, proposals, output, executor, **kwargs):
        seen["run"] = kwargs
        return {"status": "fixture", "accounting": {}}
    monkeypatch.setattr(driver, "ConfiguredExecutorPool", Transport)
    monkeypatch.setattr(driver, "run", fake_run)
    driver.main(["--source", str(tmp_path / "A"), "--proposals", str(tmp_path / "B"),
        "--output", str(tmp_path / "C"), "--remote-repo", "/fixture/repo", "--host", "fixture-host",
        "--ssh-config", str(tmp_path / "ssh"), "--image", "sha256:fixture",
        "--proxy", "http://127.0.0.1:7890"])
    assert seen["transport"]["workers"] == seen["run"]["workers"] == 2
    assert seen["transport"]["host"] == "fixture-host" and seen["closed"]
    assert seen["run"]["proxy"] == "http://127.0.0.1:7890"
