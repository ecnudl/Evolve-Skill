"""Independent Zebra v5 split-smoke checks with real units and authored offline clients/workers."""
from dataclasses import replace
import json
import re

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import engineer, manifest, profiles as p, smoke_roles, step, zebra_smoke as smoke
from skillopt.execskill import zebralogic as z
from tests.execskill_fakes import FakeSolver, engineer_reply
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_pipeline import build, offline


NOTE_SOURCE = '''def applies(view):
    return "question" in view
def before_call(view, state):
    return {"facts": ["The public puzzle provides named columns."]}
'''


def made(tmp_path, monkeypatch, *, response="rejected"):
    setting, services, _, roles = build(tmp_path, monkeypatch)
    setting = replace(setting, extra={**setting.extra, "configuration": p.ZEBRA_PC_V5})
    original = roles.replies
    def role(system, payload):
        if system == p.FIRST_CALL_SYSTEM:
            return "ready"
        if system != engineer.ENGINEER_SYSTEM_ZPC_V27:
            return original(system, payload)
        if response == "unparseable":
            return "This authored reply contains no proposal manifest."
        if response == "empty":
            return engineer_reply({"changes": []}, [])
        if payload["request"] == "fix":
            entry = {key: value for key, value in payload["change"].items() if key != "source"}
        else:
            entry = {"kind": "new", "description": "Records a generic public clue.",
                "hooks": ["before_call", "applies"], "max_note_chars": 4000,
                "excluded_benches": list(p.BENCHES)}
            if response == "rejected":
                entry["replay_tests"] = [{"id": "authored-false-claim",
                    "trajectory": payload["trajectories"][0]["cell"], "hook": "before_call",
                    "property": {"kind": "note_contains", "value": "Absent authored note fragment."},
                    "claims_fix": True, "nonvacuity": {"withheld_expect": False, "mutation": None}}]
        return engineer_reply({"changes": [entry]}, [NOTE_SOURCE])
    roles.replies = role

    def answer(system, user):
        if system == p.FIRST_CALL_SYSTEM:
            return "ready"
        view = z.parse_user(user)
        grid = {}
        for line in view["question"].splitlines():
            if line.startswith("House ") and " | " in line:
                house, *values = line.split(" | ")
                grid[house] = dict(zip(view["columns"], values))
            else:
                found = re.fullmatch(r"House (\d+) has Name (\S+) and Color (\S+)\.", line)
                if found:
                    house, name, color = found.groups()
                    grid["House " + house] = {"Name": name, "Color": color}
        assert grid, "The fake solver accepts only the authored public fixture grammars"
        return json.dumps({"reasoning": "Copied the authored public facts.", "solution": grid})
    solver = FakeSolver(tmp_path / "review-solver", [(None, answer)], max_tokens=16_384, read_timeout=600)
    setting = replace(setting, clients=lambda model, bench: roles.client if bench is None else solver.client)
    return setting, services, solver, roles


def assert_full_checks(value):
    checks = value["proposal"]["checks"]
    assert {row["check"] for row in checks} >= {
        "C1", "C2", "C3", "C4", "C5", "C5b", "C6", "C6b", "C6c", "C7", "C8", "C9"}
    assert all(row["passed"] for row in checks)


@pytest.mark.parametrize("response", ["rejected", "empty", "accepted"])
def test_real_engineer_parsed_reply_passes_s3b_without_candidate_or_gain_requirement(tmp_path, monkeypatch, response):
    setting, services, solver, roles = made(tmp_path, monkeypatch, response=response)
    found = smoke._s3(setting, services)
    assert found["passed"] and found["failed_substages"] == []
    assert found["S3a"]["passed"] and found["S3b"]["passed"] and found["S3b"]["parsed"]
    assert found["fixtures"] == 6 and found["rounds"] == 1
    real = found["S3b"]
    assert all(real["role_measurements"]["engineer"][key] > 0 for key in ("calls", "tokens", "request_bytes"))
    if response == "accepted":
        assert real["candidate_sha256"] is not None and real["training"]["cells"] > 0
        assert real["training"]["adopted"] is False  # the scripted baseline already solves the public fixture
    else:
        assert real["candidate_sha256"] is real["training"] is None
    if response == "rejected":
        change = real["engineer"]["engineer"]["changes"][0]
        assert not change["survived"]
        assert change["attempts"] and all(attempt["failed"] == "C5b" for attempt in change["attempts"])
    calls = len(solver.requests), len(roles.seen)
    assert smoke._s3(setting, services) == found
    assert (len(solver.requests), len(roles.seen)) == calls


def test_authored_s3a_uses_real_parse_normalization_checks_and_training_with_zero_role_calls(tmp_path, monkeypatch):
    setting, services, solver, roles = made(tmp_path, monkeypatch)
    parsed, normalized = [], []
    parse, normalize = engineer.parse, engineer._normalize
    def parsing(reply, **kwargs):
        result = parse(reply, **kwargs)
        parsed.append((reply, result))
        return result
    def normalizing(change, **kwargs):
        result = normalize(change, **kwargs)
        normalized.extend(change.normalized)
        return result
    monkeypatch.setattr(engineer, "parse", parsing)
    monkeypatch.setattr(engineer, "_normalize", normalizing)
    found = smoke._s3a(setting, services)
    assert found["passed"] and roles.seen == [] and solver.requests
    assert found["model_role_calls"] == found["proposal"]["model_calls"] == 0
    assert parsed and all(smoke.AUTHORED_SOURCE in reply for reply, _ in parsed)
    assert any(row.get("field") == "hooks" for row in normalized)
    assert_full_checks(found)
    assert found["training"]["cells"] > 0
    assert any(row.get("field") == "hooks" for change in found["proposal"]["changes"]
               for row in change.get("normalized", []))
    root = setting.root / "D" / "role-smoke" / "S3a"
    trajectories = [p.verified(read_json(path), "trajectory") for path in root.glob("**/trajectories/*.json")]
    candidates = [row for row in trajectories if row["arm_kind"] == "candidate"]
    assert candidates and all(row["bench"] == z.BENCH for row in candidates)
    assert {row["task_id"] for row in candidates} == {z.BENCH + "/" + item["task_id"] for item in smoke.fixture_items()}
    calls = len(solver.requests)
    assert smoke._s3a(setting, services) == found and len(solver.requests) == calls and roles.seen == []


def test_authored_s3a_fails_without_training_cells_even_when_every_proposal_check_passes(tmp_path, monkeypatch):
    setting, services, solver, roles = made(tmp_path, monkeypatch, response="empty")
    monkeypatch.setattr(step, "_train_eval", lambda *args, **kwargs: {"cells": 0, "adopted": False})
    found = smoke._s3(setting, services)
    assert not found["passed"] and found["failed_substages"] == ["S3a"]
    assert found["S3a"]["proposal"]["passed"] and found["S3a"]["training"]["cells"] == 0
    assert_full_checks(found["S3a"])
    assert found["S3b"]["passed"]
    calls = len(solver.requests), len(roles.seen)
    assert smoke._s3(setting, services) == found and (len(solver.requests), len(roles.seen)) == calls


def test_unparseable_reply_fails_only_s3b_and_failed_substages_resume_without_retries(tmp_path, monkeypatch):
    setting, services, solver, roles = made(tmp_path, monkeypatch, response="unparseable")
    found = smoke._s3(setting, services)
    assert not found["passed"] and found["failed_substages"] == ["S3b"]
    assert found["S3a"]["passed"] and not found["S3b"]["parsed"]
    assert found["S3b"]["role_measurements"]["engineer"]["calls"] > 0
    for substage in ("S3a", "S3b"):
        path = setting.root / "D" / "role-smoke" / substage / "result.json"
        recorded = p.verified(read_json(path), "zebra-smoke-substage")
        assert recorded["result"] == found[substage]
    calls = len(solver.requests), len(roles.seen)
    roles.replies = lambda *args: pytest.fail("Completed substage receipts must be reused")
    assert smoke._s3(setting, services) == found
    assert (len(solver.requests), len(roles.seen)) == calls


def stage_setup(tmp_path, monkeypatch, *, response="rejected", configuration=p.ZEBRA_PC_V5):
    setting, services, solver, roles = made(tmp_path, monkeypatch, response=response)
    setting = replace(setting, extra={**setting.extra, "configuration": configuration})
    value = {"configuration": configuration, "evidence": "smoke", p.RECORD_HASH: setting.run,
             "data": {"s0_sha256": "a" * 64, "snapshot_sha256": "b" * 64}}
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: value)
    monkeypatch.setattr(manifest, "setting_of", lambda *args, **kwargs: setting)
    monkeypatch.setattr(manifest, "services_of", lambda *args, **kwargs: services)
    return setting, services, solver, roles, tmp_path / "smoke-manifest.json"


def test_real_s1_to_se6_stage_runner_accepts_rejected_engineer_and_resumes_all_receipts(tmp_path, monkeypatch):
    setting, services, solver, roles, path = stage_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(smoke_roles, "zebra_training", lambda *args, **kwargs: pytest.fail("v5 uses the split S3"))
    values = [smoke.run_stage(path, "D", name, configuration=p.ZEBRA_PC_V5) for name in smoke.STAGES]
    assert all(value["result"]["passed"] for value in values)
    assert values[1]["result"]["parsed"] == values[1]["result"]["items"] == 10
    assert values[2]["result"]["S3b"]["candidate_sha256"] is None
    root = setting.root / "D" / "lean-smoke"
    completed = p.verified(read_json(root / "result.json"), "zebra-smoke-result")
    assert completed["passed"] and completed["sealed_reads"] == 0 and completed["s0"] == "a" * 64
    assert completed["configuration"] == p.ZEBRA_PC_V5 and completed["stages"] == list(smoke.STAGES)
    calls = len(solver.requests), len(roles.seen)
    assert [smoke.run_stage(path, "D", name, configuration=p.ZEBRA_PC_V5) for name in smoke.STAGES] == values
    assert (len(solver.requests), len(roles.seen)) == calls
    assert not list(tmp_path.rglob("consent.json"))


def test_failed_split_stage_blocks_se6_and_keeps_failure_on_resume(tmp_path, monkeypatch):
    setting, services, solver, roles, path = stage_setup(tmp_path, monkeypatch, response="unparseable")
    for name in ("S1", "S2"):
        assert smoke.run_stage(path, "D", name, configuration=p.ZEBRA_PC_V5)["result"]["passed"]
    failed = smoke.run_stage(path, "D", "S3", configuration=p.ZEBRA_PC_V5)
    assert failed["result"]["failed_substages"] == ["S3b"]
    calls = len(solver.requests), len(roles.seen)
    assert smoke.run_stage(path, "D", "S3", configuration=p.ZEBRA_PC_V5) == failed
    with pytest.raises(ValueError, match="preceding smoke"):
        smoke.run_stage(path, "D", "SE6", configuration=p.ZEBRA_PC_V5)
    assert (len(solver.requests), len(roles.seen)) == calls
    assert not (setting.root / "D" / "lean-smoke" / "result.json").exists()


@pytest.mark.parametrize("configuration", [p.ZEBRA_PC_V1, p.ZEBRA_PC_V2, p.ZEBRA_PC_V3, p.ZEBRA_PC_V4])
def test_every_older_zebra_stage_keeps_exact_legacy_training_dispatch(tmp_path, monkeypatch, configuration):
    setting, services, solver, roles, path = stage_setup(tmp_path, monkeypatch, configuration=configuration)
    root = setting.root / "D" / "lean-smoke"
    for stage in ("S1", "S2"):
        write_json(root / (stage + ".json"), p.record("zebra-smoke-stage", "smoke", {
            "configuration": configuration, "chain": "D", "manifest": setting.run,
            "stage": stage, "result": {"passed": True}}))
    sentinel = {"passed": False, "rounds": 1, "legacy_result": "authored unchanged sentinel"}
    calls = []
    def legacy(*args):
        calls.append(args)
        return sentinel
    monkeypatch.setattr(smoke_roles, "zebra_training", legacy)
    monkeypatch.setattr(smoke, "_s3", lambda *args, **kwargs: pytest.fail("Older Zebra configs keep their old S3"))
    found = smoke.run_stage(path, "D", "S3", configuration=configuration)
    assert found["result"] == sentinel
    assert calls == [(setting, services, "D", smoke.fixture_items())]
    assert not solver.requests and not roles.seen
