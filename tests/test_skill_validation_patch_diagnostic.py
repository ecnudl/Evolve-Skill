"""Engineering-only orchestration fixtures: no model, Docker, SSH or task execution."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import patch_diagnostic as driver
from skillopt.skill_validation import patch_tasks
from skillopt.skill_validation.public_revision import solve_public_initial
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest
from tests.test_run_mechanism_case_feedback import FixtureAPI, write
from tests.test_skill_validation_public_revision import CODE, SECRET, FixtureExecutor, fixture_row


def fixture_panel(seed=20260926):
    rows = []
    source = fixture_row()
    for family in range(12):
        for role in driver.ROLES:
            contract = replace(source["task"].contract,
                task_id=f"fixture-patch-{family}-{role}", original_task_id=f"fixture-source-{family}",
                family_id=f"fixture-family-{family}", project_id=f"fixture-project-{family}",
                prompt=source["task"].contract.prompt + f"\nFixture {family}, {role}.\nStarter:\n" + CODE)
            rows.append({"task": replace(source["task"], contract=contract),
                "public_task": replace(source["public_task"], contract=contract),
                "public_wrapper": source["public_wrapper"], "family_id": contract.family_id,
                "region": role, "host_only": {"private": SECRET}, "task_kind": "engineering_fixture"})
    return {"development": rows, "manifest": seal({"seed": seed, "fixture_only": True,
        "tasks": [row["task"].content_hash for row in rows]})}


class DiagnosticAPI(FixtureAPI):
    qualification_ready = False
    initial_fail = False
    parameters = []

    def __init__(self, *args, **kwargs):
        type(self).parameters.append(kwargs)
        super().__init__(*args, **kwargs)

    def call(self, *args, **kwargs):
        assert self.qualification_ready, "Paid request before full qualification"
        value = super().call(*args, **kwargs)
        if self.initial_fail and value["request"]["kind"] == "public-initial":
            value = {**value, "ok": False, "response": "", "error_type": "truncated_content"}
            write(self.root / "calls" / (value["request_hash"] + ".json"), value)
        return value


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(DiagnosticAPI, "instances", [])
    monkeypatch.setattr(DiagnosticAPI, "parameters", [])
    monkeypatch.setattr(DiagnosticAPI, "initial_fail", False)
    monkeypatch.setattr(DiagnosticAPI, "qualification_ready", False)
    monkeypatch.setattr(driver, "CachedAPI", DiagnosticAPI)
    monkeypatch.setattr(driver, "build_development_panel", fixture_panel)
    monkeypatch.setattr(driver, "serialize_row", lambda row: {
        **row, "task": row["task"].to_dict(), "public_task": row["public_task"].to_dict()})
    qualifications, audits = [], []
    def qualify(panel, executor, root):
        assert not any(api.requests for api in DiagnosticAPI.instances)
        qualifications.append(panel)
        DiagnosticAPI.qualification_ready = True
        return seal({"status": "qualified", "formal_eligible": True,
                     "fixture_override_only": True, "source_families": 12,
                     "panel_hash": panel["manifest"]["record_hash"]})
    monkeypatch.setattr(driver, "qualify_panel", qualify)
    def audit(row, artifact, executor, root):
        frozen = driver._read(tmp_path / "output/frozen_panel.json")
        assert frozen["before_any_solver"]
        assert (root / "rule_result.json").exists(), "Hidden audit before public-only final selection"
        audits.append(artifact)
        status = "pass" if artifact.availability == "available" else "unknown"
        return seal({"status": status, "target_status": status, "state_status": status,
            "retained_status": status,
            "replaced_status": status if row["region"] == "replace" else "not_applicable",
            "receipt": None, "fixture_only": True, "private_diagnostic": SECRET})
    monkeypatch.setattr(driver, "audit_row", audit)
    return tmp_path, tmp_path / "output", FixtureExecutor(), qualifications, audits


def test_fixed_24_tasks_two_roles_two_repeats_and_cold_solver_protocol(setup):
    repo, output, executor, qualifications, audits = setup
    result = driver.run(repo, output, executor)
    assert result["status"] == "completed_development_diagnostic"
    assert result["provenance"] == "engineering_fixture"
    assert not result["skill_evolution_evaluated"] and not result["generalization_evaluated"]
    metrics = result["metrics"]
    assert metrics["overall"]["tasks"] == 24 and metrics["overall"]["source_families"] == 12
    assert metrics["expected_positions"] == metrics["observed_positions"] == 48
    assert metrics["missing_positions"] == 0 and len(qualifications) == 1 and len(audits) == 96
    assert result["accounting"]["terminal_logical_requests"] == 96
    api = DiagnosticAPI.instances[-1]
    for request in api.requests:
        assert request["max_tokens"] == 2048 and request["kind"] in {"public-initial", "public-revision"}
        assert SECRET not in request["system"] + request["user"]
        assert '"optional_skill": ""' in request["user"]
        if request["kind"] == "public-initial":
            assert "Starter:" in request["user"]
    assert DiagnosticAPI.parameters[-1]["initial_health_policy"] == "completed_response_v1"
    for role in ("preserve", "replace"):
        part = metrics["by_role"][role]
        assert part["tasks"] == 12 and part["source_families"] == 12 and part["positions"] == 24
        assert part["components"]["final"]["retained_status"]["counts"]["pass"] == 24
    inapplicable = metrics["by_role"]["preserve"]["components"]["final"]["replaced_status"]
    assert inapplicable["counts"]["not_applicable"] == 24 and inapplicable["all_attempt_success"]["denominator"] == 0


def test_prepare_only_and_replay_do_not_resample(setup):
    repo, output, executor, _, _ = setup
    prepared = driver.run(repo, output, executor, stop_after="prepare")
    assert prepared["status"] == "prepared_diagnostic"
    assert prepared["accounting"]["http_attempts"] == 0
    assert not DiagnosticAPI.instances[-1].requests
    result = driver.run(repo, output, executor)
    executions = len(executor.calls)
    assert driver.run(repo, output, executor) == result
    assert len(executor.calls) == executions and DiagnosticAPI.instances[-1].fresh_requests == []


def test_qualification_failure_leaves_full_registration_and_zero_paid_calls(setup, monkeypatch):
    repo, output, executor, _, _ = setup
    monkeypatch.setattr(driver, "qualify_panel", lambda panel, *args: seal({"status": "pending", "formal_eligible": False,
                        "panel_hash": panel["manifest"]["record_hash"]}))
    result = driver.run(repo, output, executor)
    assert result["status"] == "pending_qualification" and result["accounting"]["http_attempts"] == 0
    assert len(driver._read(output / "expected_positions.json")["positions"]) == 48
    assert not (output / "frozen_panel.json").exists()
    assert not DiagnosticAPI.instances[-1].requests


def test_safe_executor_failure_cannot_fall_back_to_host_or_paid_solver(setup):
    repo, output, _, _, _ = setup
    executor = FixtureExecutor({"status": "unsupported", "actual": None})
    with pytest.raises(ValueError, match="infrastructure unavailable"):
        driver.run(repo, output, executor)
    assert not DiagnosticAPI.instances[-1].requests


def test_qualification_receipt_must_bind_the_registered_panel_before_paid_calls(setup, monkeypatch):
    repo, output, executor, _, _ = setup
    monkeypatch.setattr(driver, "qualify_panel", lambda *args: seal({"status": "qualified", "formal_eligible": True,
                        "panel_hash": digest("different-panel")}))
    with pytest.raises(ValueError, match="another frozen panel"):
        driver.run(repo, output, executor)
    assert not DiagnosticAPI.instances[-1].requests


def test_failed_initial_calls_remain_unknown_without_hidden_repair(setup, monkeypatch):
    repo, output, executor, _, _ = setup
    monkeypatch.setattr(DiagnosticAPI, "initial_fail", True)
    result = driver.run(repo, output, executor)
    assert result["accounting"]["terminal_failures"] == 48
    assert result["accounting"]["by_kind"] == {"public-initial": 48}
    overall = result["metrics"]["overall"]
    assert overall["final"]["counts"]["unknown"] == 48 and overall["final"]["counts"]["fail"] == 0
    assert overall["final"]["all_attempt_success"]["denominator"] == 48
    assert overall["unknown_pairs"] == 48


def test_missing_reserved_receipt_rejects_resume_even_with_summary(setup):
    repo, output, executor, _, _ = setup
    driver.run(repo, output, executor)
    next((output / "api/calls").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="Interrupted API request"):
        driver.run(repo, output, executor)
    assert DiagnosticAPI.instances[-1].fresh_requests == []


@pytest.mark.parametrize("change", [{"workers": 3}, {"repeats": 1}, {"seed": 7}])
def test_protocol_changes_cannot_reuse_output(setup, change):
    repo, output, executor, _, _ = setup
    driver.run(repo, output, executor, stop_after="prepare")
    with pytest.raises(ValueError):
        driver.run(repo, output, executor, **change)
    assert not any(api.requests for api in DiagnosticAPI.instances)


@pytest.mark.parametrize("change", ["drop_task", "duplicate_role", "duplicate_id", "confirmation"])
def test_task_roster_cannot_shrink_or_masquerade_as_independent_families(change):
    panel = fixture_panel()
    rows = panel["development"]
    if change == "drop_task":
        rows.pop()
    elif change == "duplicate_role":
        rows[1]["region"] = rows[0]["region"]
    elif change == "duplicate_id":
        rows[1]["task"] = rows[0]["task"]
    else:
        rows[0]["task"] = replace(rows[0]["task"], contract=replace(rows[0]["task"].contract, partition="skill_confirmation"))
    with pytest.raises(ValueError):
        driver._roster(rows, 2)


def test_summary_keeps_missing_denominator_and_distinguishes_NA():
    roster = driver._roster(fixture_panel()["development"], 2)
    position = roster[0]
    components = {"target_status": "pass", "retained_status": "fail", "replaced_status": "not_applicable", "state_status": "pass"}
    row = seal({**position, "initial_status": "fail", "final_status": "pass",
        "initial_components": components, "final_components": {**components, "retained_status": "pass"}})
    summary = driver.summarize([row], roster)
    assert summary["expected_positions"] == 48 and summary["missing_positions"] == 47
    assert summary["overall"]["final"]["all_attempt_success"] == {"numerator": 1, "denominator": 48, "value": 1 / 48}
    assert summary["overall"]["audit_confirmed_after_public_revision_repairs"] == 1
    assert summary["overall"]["unknown_pairs"] == 47
    replaced = summary["by_role"]["preserve"]["components"]["final"]["replaced_status"]
    assert replaced["counts"]["not_applicable"] == 24 and replaced["counts"]["unknown"] == 0
    assert replaced["all_attempt_success"]["denominator"] == 0
    with pytest.raises(ValueError, match="mismatched"):
        driver.summarize([row, row], roster)
    changed = deepcopy(row)
    changed["family_id"] = "incorrect-family"
    changed = seal({k: v for k, v in changed.items() if k != "record_hash"})
    with pytest.raises(ValueError):
        driver.summarize([changed], roster)


def test_cli_transparent_executor_transport_and_prepare(monkeypatch, tmp_path, capsys):
    seen = {}
    class Executor:
        def __init__(self, remote, **kwargs): seen.update(remote=remote, transport=kwargs)
        def close(self): seen["closed"] = True
    def run(repo, output, executor, **kwargs):
        seen["run"] = kwargs
        return seal({"status": "fixture", "accounting": {}})
    monkeypatch.setattr(driver, "ConfiguredExecutorPool", Executor)
    monkeypatch.setattr(driver, "run", run)
    driver.main(["--output", str(tmp_path / "out"), "--remote-repo", "/fixture/repo",
        "--host", "fixture-host", "--ssh-config", str(tmp_path / "ssh"), "--proxy", "http://127.0.0.1:7890",
        "--stop-after", "prepare"])
    assert seen["closed"] and seen["run"]["stop_after"] == "prepare"
    assert seen["run"]["workers"] == 2 and seen["run"]["repeats"] == 2
    assert seen["transport"]["ssh_config"] == tmp_path / "ssh"
    assert '"status": "fixture"' in capsys.readouterr().out


def test_actual_catalog_starter_enters_unchanged_solver_request_without_host_oracle(tmp_path):
    """Only build strings and fake receipts; no reference/candidate execution."""
    panel = patch_tasks.build_development_panel()
    assert len(driver._roster(panel["development"], 2)) == 48
    api = FixtureAPI(tmp_path, tmp_path / "api")
    calls = BoundedCalls(api, tmp_path / "budget", digest("public-starter-fixture"), 24)
    for index, row in enumerate(panel["development"]):
        public = {key: row[key] for key in ("task", "public_task", "public_wrapper")}
        solve_public_initial(public, "", "no_skill", 0, calls, tmp_path / "positions" / str(index))
        request = api.requests[-1]
        payload = json.loads(request["user"])
        assert row["host_only"]["starter"] in payload["task"]
        assert row["host_only"]["reference"] not in payload["task"]
        assert "host_only" not in payload and "audit_runner" not in payload
        assert payload == {"task": row["task"].contract.prompt, "optional_skill": ""}
