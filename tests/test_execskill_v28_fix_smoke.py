"""Fix v28-1 smoke dispatch and measured-role budget regressions; authored offline fixtures."""
from dataclasses import replace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import alf_smoke, budgets, engineer, manifest, profiles as p, smoke, smoke_roles, zebra_smoke
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_alf_v1_smoke_review import made as alf_made
from tests.test_execskill_v27_zebra_smoke_review import made as zebra_made
from tests.test_execskill_v28_profile import tmp_path
from tests.test_execskill_zpc_pipeline import offline


def s2_measurement(configuration):
    bench = p.active_benches(configuration)[0]
    count = 10 if p.is_zebra(configuration) else alf_smoke.S2_ITEMS
    value = {"passed": True, "items": count, "tokens_per_cell": 1000, "settled_tokens": 1000 * count,
             "measurements": {"actual": 1000 * count, "request_bytes": {bench: 1000}}}
    if p.is_alfworld(configuration):
        value["solver_bounds"] = {"branch": "E", "longest": None,
            "ledger_bound": p.ledger_bound(p.CHAINS["D"], bench, branch="E")}
    return value


def projected(configuration, s3):
    s2 = s2_measurement(configuration)
    return (zebra_smoke.projection(s2, "D", configuration, s3=s3) if p.is_zebra(configuration)
            else alf_smoke.projection(s2, s3, configuration))


@pytest.mark.parametrize("configuration", (p.ZEBRA_PC_V6, p.ALFWORLD_V3))
@pytest.mark.parametrize("response", ("empty", "inert", "deferred"))
def test_candidate_free_parsed_proposals_pass_split_smoke_and_measured_projection(
        tmp_path, monkeypatch, configuration, response):
    module = zebra_smoke if p.is_zebra(configuration) else alf_smoke
    make = zebra_made if p.is_zebra(configuration) else alf_made
    setting, services, solver, roles = make(tmp_path, monkeypatch, response="empty")
    setting = replace(setting, extra={**setting.extra, "configuration": configuration})
    original = roles.replies
    hook = "before_call" if p.is_zebra(configuration) else "alf_before_step"
    source = "def applies(view):\n    return False\ndef %s(view, state):\n    return None\n" % hook

    def role(system, payload):
        if system != engineer.engineer_v28.system(configuration, train=True):
            return original(system, payload)
        if response == "empty":
            return engineer_reply({"changes": []}, [])
        if response == "deferred":
            return engineer_reply({"changes": [{"kind": "deletion", "id": "fx-absent"}]}, [])
        return engineer_reply({"changes": [{"kind": "new", "description": "An inert authored helper."}]}, [source])

    roles.replies = role
    value = {"configuration": configuration, "evidence": "smoke", p.RECORD_HASH: setting.run,
             "data": {"s0_sha256": "a" * 64, "snapshot_sha256": "b" * 64}}
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: value)
    monkeypatch.setattr(manifest, "setting_of", lambda *args, **kwargs: setting)
    monkeypatch.setattr(manifest, "services_of", lambda *args, **kwargs: services)
    monkeypatch.setattr(smoke_roles, "zebra_training", lambda *args, **kwargs: pytest.fail("v6 uses split S3"))
    root = setting.root / "D" / "lean-smoke"
    kind = "zebra" if p.is_zebra(configuration) else "alfworld"
    for stage, result in (("S1", {"passed": True}), ("S2", s2_measurement(configuration))):
        write_json(root / (stage + ".json"), p.record(kind + "-smoke-stage", "smoke", {
            "configuration": configuration, "chain": "D", "manifest": setting.run,
            "stage": stage, "result": result}))

    def run(stage):
        args = (tmp_path / "manifest.json", "D", stage) if p.is_zebra(configuration) else (
            tmp_path / "manifest.json", stage)
        return module.run_stage(*args, configuration=configuration)

    s3 = run("S3")["result"]
    assert s3["passed"] and s3["failed_substages"] == []
    assert s3["S3a"]["passed"] and s3["S3b"]["parsed"]
    real = s3["S3b"]
    assert real["candidate_sha256"] is real["training"] is None
    if response != "empty":
        assert real["engineer"]["engineer"]["changes"][0][response]
    assert all(real["role_measurements"]["engineer"][key] > 0 for key in ("calls", "tokens", "request_bytes"))
    result = run("SE6")["result"]
    assert result["passed"] and result["roles"]
    assert result["roles"] == {key: row for key, row in smoke.glm_projection(
        s3["role_measurements"], configuration).items() if key.startswith("D:")}
    assert p.verified(read_json(root / "result.json"), kind + "-smoke-result")["passed"]
    calls = len(solver.requests), len(roles.seen)
    assert run("S3")["result"] == s3 and run("SE6")["result"] == result
    assert (len(solver.requests), len(roles.seen)) == calls


@pytest.mark.parametrize("configuration,parent", ((p.ZEBRA_PC_V6, p.ZEBRA_PC_V5),
                                                   (p.ALFWORLD_V3, p.ALFWORLD_V2)))
def test_se6_rejects_role_costs_that_exceed_enlarged_engineer_call_budget(configuration, parent):
    measured = {role: {"calls": 1, "tokens": 150000 if role == "engineer" else 1000,
                      "per_call": 150000 if role == "engineer" else 1000, "request_bytes": 1000}
                for role in budgets.ROLES}
    old = smoke.glm_projection(measured, parent)
    assert all(row["fits"] for name, row in old.items() if name.startswith("D:"))
    found = projected(configuration, {"role_measurements": measured})
    assert all(row["passed"] for row in found["scopes"].values())
    assert not found["passed"]
    name = next(name for name in found["roles"] if name.endswith(":role:engineer"))
    row = found["roles"][name]
    assert not row["fits"] and row["needed"] > row["cap"]
    assert row["settled"] == 6 * (23 + 4) * 150000 + (72 + 3) * 1000
    assert all(name.startswith("D:") for name in found["roles"])


def test_zebra_v6_projection_requires_measured_roles_and_v5_keeps_frozen_output():
    with pytest.raises(ValueError, match="S3 measured role calls"):
        zebra_smoke.projection(s2_measurement(p.ZEBRA_PC_V6), "D", p.ZEBRA_PC_V6)
    before = zebra_smoke.projection(s2_measurement(p.ZEBRA_PC_V5), "D", p.ZEBRA_PC_V5)
    assert before["passed"] and "roles" not in before
