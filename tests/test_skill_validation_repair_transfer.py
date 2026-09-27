"""Offline transfer integration with fabricated model/qualification receipts only."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_public_repair_feedback as proposals
from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import patch_tasks
from skillopt.skill_validation import repair_transfer as driver
from skillopt.skill_validation.public_repair_feedback import CALL_KIND
from skillopt.validator_pilot.api import digest
from tests.test_run_mechanism_case_feedback import FixtureAPI, reseal, write
from tests.test_skill_validation_mechanism_case_confirmation import source_fixture


class RepairAPI(FixtureAPI):
    all_empty = False
    primary_invalid = False
    solver_unknown = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = {**self.service, "initial_health_policy": "completed_response_v1"}

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        if kind == CALL_KIND:
            payload = json.loads(user)
            arm = "trajectory" if payload["public_repair_annex"] else "summary_only"
            if self.all_empty or repeat >= 4:
                response = "NO_UPDATE"
            elif self.primary_invalid and repeat % 2 == 0:
                response = "INVALID_JSON"
            else:
                evidence = payload["evidence_catalog"][0]["id"]
                rule = {"id": f"fixture-{arm}-{repeat}", "mechanism": "Constraint Preservation",
                    "procedure": ["Check preserved behavior against the explicit changed contract."],
                    "when": "The public task requires retained behavior.", "exceptions": ["Do not retain explicitly replaced rules."],
                    "scope": {"required_obligation_kinds": ["requested_behavior"], "forbidden_obligation_kinds": []},
                    "evidence_ids": [evidence]}
                response = json.dumps({"parent_hash": payload["parent_hash"], "edits": [{"operation": "add",
                    "rule_id": rule["id"], "rule": rule, "evidence_ids": [evidence], "reason": "Fixture, not semantic evidence."}]})
            self.proposal_response, self.proposal_ok = response, True
        value = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if self.solver_unknown and kind == "public-initial":
            value = {**value, "ok": False, "response": "", "error_type": "truncated_content"}
            write(self.root / "calls" / (value["request_hash"] + ".json"), value)
        return value


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(RepairAPI, "instances", [])
    for name in ("all_empty", "primary_invalid", "solver_unknown"):
        monkeypatch.setattr(RepairAPI, name, False)
    monkeypatch.setattr(proposals, "CachedAPI", RepairAPI)
    monkeypatch.setattr(driver, "CachedAPI", RepairAPI)
    def build(*, all_empty=False, primary_invalid=False):
        source, executor = source_fixture(tmp_path, histories=3)
        RepairAPI.all_empty, RepairAPI.primary_invalid = all_empty, primary_invalid
        proposed, patch, output = tmp_path / "F", tmp_path / "Patch", tmp_path / "Transfer"
        proposals.run(tmp_path, source, proposed, repeats=2, workers=1, run_proposals=True)
        panel = patch_tasks.build_development_panel()
        protocol = seal({"version": "fixture-patch-diagnostic", "development_only": True, "condition": "no_skill",
            "manifest_hash": panel["manifest"]["record_hash"], "service": RepairAPI.instances[-1].service,
            "executor": executor.identity, "source_hashes": {name: hashlib.sha256(
                (Path(driver.__file__).parent / name).read_bytes()).hexdigest() for name in driver.PATCH_EXECUTION_MODULES}})
        qualification = seal({"status": "qualified", "formal_eligible": True, "fixture_override_only": True,
                              "panel_hash": panel["manifest"]["record_hash"]})
        write(patch / "protocol.json", protocol)
        write(patch / "host_only/panel.json", seal({"manifest": panel["manifest"],
            "development": [patch_tasks.serialize_row(row) for row in panel["development"]]}))
        write(patch / "qualification_summary.json", qualification)
        write(patch / "frozen_panel.json", seal({"protocol_hash": protocol["record_hash"],
            "manifest_hash": panel["manifest"]["record_hash"], "qualification_hash": qualification["record_hash"],
            "before_any_solver": True}))
        # Any read would violate the source-outcome isolation contract.
        write(patch / "summary.json", {"FORBIDDEN_PATCH_RESULTS": True})
        write(patch / "diagnostic_rows.json", {"FORBIDDEN_PATCH_RESULTS": True})
        def audit(row, artifact, executor, root):
            frozen = driver._read(output / "frozen_inputs.json")
            assert frozen["before_any_new_solver"] and len(frozen["skills"]) == 3
            assert (root / "rule_result.json").exists()
            status = "pass" if artifact.availability == "available" else "unknown"
            return seal({"status": status, "target_status": status, "retained_status": status,
                "replaced_status": status if row["region"] == "replace" else "not_applicable",
                "state_status": status, "receipt": None, "fixture_only": True})
        monkeypatch.setattr(driver, "_audit", audit)
        return source, proposed, patch, output, executor
    return build


def test_primary_full_receipt_replay_prepare_zero_calls_and_576_grid(setup, tmp_path):
    source, proposed, patch, output, executor = setup()
    before = len(RepairAPI.instances)
    result = driver.run(tmp_path, source, proposed, patch, output, executor, stop_after_prepare=True)
    assert result["status"] == "prepared_shadow_transfer" and result["expected_positions"] == 576
    assert result["new_model_calls"] == 0 and len(RepairAPI.instances) == before
    frozen = driver._read(output / "frozen_inputs.json")
    assert sum(len(hashes) for hist in frozen["all_proposal_record_hashes"].values() for hashes in hist.values()) == 12
    for history in ("h0", "h1"):
        for arm in driver.ARMS:
            rules = frozen["skills"][history][arm]["rules"]
            assert len(rules) == 1 and rules[0]["id"].endswith("0" if history == "h0" else "2")
    assert all(not skill["rules"] for skill in frozen["skills"]["h2"].values())
    roster = driver._read(output / "expected_positions.json")["positions"]
    assert {row["exposure"] for row in roster} == {"raw"}
    assert {row["region"] for row in roster} == {"near_miss", "unrelated"}
    near = [row for row in roster if row["region"] == "near_miss"]
    assert len(near) == 48 and {row["patch_role"] for row in near} == {"preserve", "replace"}
    assert {row["family_id"] for row in near} == {"curated-patch-interval_policy"}
    assert not (output / "summary.json").exists()


def test_full_fixture_run_new_baselines_empty_history_aliases_unknown_and_resume(setup, tmp_path, monkeypatch):
    source, proposed, patch, output, executor = setup()
    monkeypatch.setattr(RepairAPI, "solver_unknown", True)
    result = driver.run(tmp_path, source, proposed, patch, output, executor)
    assert result["status"] == "completed_shadow_transfer_diagnostic"
    assert result["observed_positions"] == result["expected_positions"] == 576
    assert not result["independent_confirmation"] and not result["positive_transfer_evaluated"]
    assert result["accounting"]["terminal_failures"] > 0
    for phase in ("initial", "final"):
        metrics = result["metrics"][phase]
        assert metrics["missing_positions"] == 0
        assert set(metrics["arms"]) == {"raw/" + condition for condition in driver.CONDITIONS}
        for arm in metrics["arms"].values():
            assert arm["all_attempt_success"]["denominator"] == 144
            assert arm["counts"]["unknown"] == 144
        assert not metrics["arms"]["raw/trajectory"]["by_history"]["h2"]["skill_application_coverage"]["numerator"]
    api = RepairAPI.instances[-1]
    assert api.root == output / "api"
    assert len(api.fresh_requests) == 336  # h0/h1 three effective prompts, h2 only the clean base.
    public_prompts = {row["task"].contract.prompt for row in patch_tasks.build_development_panel()["development"]}
    for request in api.requests:
        assert request["kind"] == "public-initial" and request["max_tokens"] == 2048
        payload = json.loads(request["user"])
        assert set(payload) == {"task", "optional_skill"}  # Public prose may legitimately contain "unrelated keys".
        assert payload["task"] in public_prompts
        assert "FORBIDDEN_PATCH_RESULTS" not in request["user"]
    previous = len(executor.calls)
    assert driver.run(tmp_path, source, proposed, patch, output, executor) == result
    assert len(executor.calls) == previous


@pytest.mark.parametrize("kwargs,status", [({"all_empty": True}, "no_update"), ({"primary_invalid": True}, "invalid")])
def test_invalid_or_empty_primary_never_promotes_stability_candidate(setup, tmp_path, kwargs, status):
    source, proposed, patch, output, executor = setup(**kwargs)
    before = len(RepairAPI.instances)
    result = driver.run(tmp_path, source, proposed, patch, output, executor)
    assert result["status"] == "no_changed_primary_candidates"
    assert result["metrics"] is None and not result["method_effect_evaluated"]
    assert len(RepairAPI.instances) == before
    assert all(s == status for s in result["statuses"]["h0"].values())


@pytest.mark.parametrize("repeat,part", [(0, "receipt"), (1, "receipt"), (0, "intent"), (1, "intent")])
def test_all_twelve_original_receipts_and_reservations_are_required(setup, tmp_path, repeat, part):
    source, proposed, patch, output, executor = setup()
    record = driver._read(proposed / "histories/h0/updates" / f"summary_only-{repeat}.json")
    path = proposed / ("api/calls" if part == "receipt" else "budget/intents") / (record["api_receipt"]["request_hash"] + ".json")
    path.unlink()
    before = len(RepairAPI.instances)
    with pytest.raises((ValueError, FileNotFoundError)):
        driver.run(tmp_path, source, proposed, patch, output, executor, stop_after_prepare=True)
    assert len(RepairAPI.instances) == before


@pytest.mark.parametrize("tamper", ["candidate", "feedback", "selection", "jobs", "patch_rows", "patch_adapter", "qualification"])
def test_bound_source_metadata_cannot_change_under_same_experiment(setup, tmp_path, tamper):
    source, proposed, patch, output, executor = setup()
    path = {"candidate": proposed / "histories/h0/updates/trajectory-0.json",
        "feedback": proposed / "histories/h0/source_feedback.json", "selection": proposed / "protocol.json",
        "jobs": proposed / "jobs.json", "patch_rows": patch / "host_only/panel.json",
        "patch_adapter": patch / "protocol.json", "qualification": patch / "qualification_summary.json"}[tamper]
    value = driver._read(path)
    if tamper == "candidate":
        value["update"]["candidate"]["rules"] = []
    elif tamper == "feedback":
        value["altered"] = True
    elif tamper == "selection":
        value["primary_repeat"] = 1
    elif tamper == "jobs":
        value["jobs"].reverse()
    elif tamper == "patch_rows":
        value["development"][0]["region"] = "unrelated"
    elif tamper == "patch_adapter":
        value["source_hashes"]["patch_tasks.py"] = digest("foreign")
    else:
        value["status"] = "pending"
    write(path, reseal(value))
    with pytest.raises(ValueError):
        driver.run(tmp_path, source, proposed, patch, output, executor, stop_after_prepare=True)


def test_patch_source_never_opens_solver_results_and_freeze_precedes_new_calls(setup, tmp_path, monkeypatch):
    source, proposed, patch, output, executor = setup()
    reader = driver._read
    def guarded(path):
        if path.is_relative_to(patch):
            assert str(path.relative_to(patch)) in {"protocol.json", "host_only/panel.json", "frozen_panel.json", "qualification_summary.json"}
        return reader(path)
    monkeypatch.setattr(driver, "_read", guarded)
    api_call = RepairAPI.call
    def guarded_call(self, *args, **kwargs):
        if self.root == output / "api":
            freeze = reader(output / "frozen_inputs.json")
            assert freeze["before_any_new_solver"] and len(freeze["skills"]) == 3
        return api_call(self, *args, **kwargs)
    monkeypatch.setattr(RepairAPI, "call", guarded_call)
    result = driver.run(tmp_path, source, proposed, patch, output, executor, repeats=1)
    assert result["observed_positions"] == 288
    assert result["metrics"]["final"]["arms"]["raw/no_skill"]["counts"]["pass"] == 72


def test_snapshot_rejects_live_fallback_script_import(monkeypatch, tmp_path):
    monkeypatch.setattr(driver.proposal_driver, "__file__", str(tmp_path / "outside.py"))
    with pytest.raises(ValueError, match="Frozen code snapshot"):
        driver._implementation_hashes()


def test_output_overlap_and_worker_limits_before_loading_sources(tmp_path):
    source, proposals_root, patch, output = (tmp_path / name for name in ("A", "F", "Patch", "New"))
    for target in (source, source / "nested", tmp_path):
        with pytest.raises(ValueError, match="outside"):
            driver.run(tmp_path, source, proposals_root, patch, target, None)
    with pytest.raises(ValueError, match="workers"):
        driver.run(tmp_path, source, proposals_root, patch, output, None, workers=5)


def test_component_tables_keep_NA_unknown_and_registered_missing_denominators():
    positions = [{"history": "h0", "task_id": role, "family_id": "one-declared-family", "domain": "coding",
        "region": "near_miss", "patch_role": role, "repeat": 0, "condition": "trajectory", "exposure": "raw"}
        for role in ("preserve", "replace")]
    components = {"target_status": "fail", "retained_status": "pass", "replaced_status": "not_applicable", "state_status": "unknown"}
    record = {"initial": seal({**positions[0], "audit_components": components})}
    result = driver.component_summary([record], positions, "initial")
    assert result["missing_positions"] == 1 and not result["family_independence_proven"]
    overall = result["arms"]["trajectory"]["overall"]
    assert overall["positions"] == 2 and overall["declared_source_families"] == 1
    assert overall["components"]["target_status"]["counts"] == {"pass": 0, "fail": 1, "unknown": 1, "not_applicable": 0}
    assert overall["components"]["replaced_status"]["counts"] == {"pass": 0, "fail": 0, "unknown": 1, "not_applicable": 1}
    assert overall["components"]["replaced_status"]["all_attempt_success"]["denominator"] == 1
    empty = driver.component_summary([], positions, "initial")
    preserve = empty["arms"]["trajectory"]["by_patch_role"]["preserve"]["components"]["replaced_status"]
    assert preserve["counts"]["not_applicable"] == 1 and preserve["all_attempt_success"]["denominator"] == 0
