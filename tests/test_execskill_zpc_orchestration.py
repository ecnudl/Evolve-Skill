"""Zero-call profile isolation and lean smoke checks using synthetic grids and scripted clients."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, chain, evaluation, manifest, profiles as p, protocol, routes,
                               smoke, units, zebra_smoke, zebralogic as z)
from skillopt.execskill.cells import Pause
from skillopt.execskill.package import empty
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import FakeSolver, fake_config
from tests.test_execskill_chain import CONSENT, Launch, Learn, setting as chain_setting
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, given
from tests.test_execskill_zpc_adapter import answer, materialize, pool_rows, row


def made(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(tmp_path / "history"))
    value = given(tmp_path)
    source = tmp_path / "fake-pool.json"
    sha = materialize(source, pool_rows())
    configs = {name: fake_config(tmp_path / name, p.CHAINS[name]) for name in p.CHAINS}
    blocks = {"G": manifest.solver_block("G", env_path=configs["G"]["repo"], configuration=p.ZEBRA_PC_V1),
              "D": manifest.solver_block("D", env_path=configs["D"]["env_path"], branch="E", configuration=p.ZEBRA_PC_V1)}
    value.update(cards={z.BENCH: z.CARD_TEXT}, runtime={z.BENCH: dict(zebra_smoke.RUNTIME)}, sheet_qualification=None,
        clients={"solver": blocks, "roles": manifest.role_settings(p.ZEBRA_PC_V1), "routes": {"D": {"B": routes.pin(
            "D", "B", env_path=tmp_path / "route-b.env", solver_block=blocks["D"], configuration=p.ZEBRA_PC_V1)}}},
        data={"pools": {z.BENCH: {"path": str(source), "sha256": sha}}, "pinned": z.identity()["sealed"],
              "zebra_pc": z.identity(), "test_read_estimate": {"G": 1000, "D": 1000},
              "test_read_terms": {"G": {z.BENCH: "1000"}, "D": {z.BENCH: "1000"}}})
    return manifest.make(tmp_path / "zpc.json", evidence="engineering_fixture", configuration=p.ZEBRA_PC_V1,
                         environment_found=fake_environment(), measured=MEASURED, **value)


def test_manifest_isolated_bounds_cards_identity_optional_services(tmp_path, monkeypatch):
    m = made(tmp_path, monkeypatch)
    assert m["configuration"] == p.ZEBRA_PC_V1
    assert m["clients"]["solver"]["G"]["M"] == {z.BENCH: 65536}
    assert m["clients"]["solver"]["D"]["M"] == {z.BENCH: 16384}
    assert m["clients"]["solver"]["D"]["read_timeout"] == {z.BENCH: 600}
    assert m["clients"]["solver"]["D"]["backend"] == "elucid"
    assert set(m["clients"]["routes"]["D"]["B"]["M"]) == {z.BENCH}
    assert m["cards"] == {z.BENCH: z.CARD_TEXT}
    assert m["data"]["zebra_pc"] == z.identity()
    assert protocol.TEXTS_IMPORT not in m["importable_versions"]
    setting = manifest.setting_of(m, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert set(setting.pools) == set(setting.runtime) == set(setting.cards) == {z.BENCH}
    setting.budget.declare(budgets.chain_caps("D", p.ZEBRA_PC_V1))
    services = manifest.services_of(m, "D", setting=setting, transport=NO_CALLS)
    assert services.sources is services.engine is services.checker is None
    assert set(units.cell_context(setting, tmp_path / "attempt", units.solver_endpoint(
        setting, "D", z.BENCH, 1, "run", tmp_path / "attempt-1")).nominal) == {z.BENCH}


def test_manifest_rejects_different_registration_and_unrelated_card(tmp_path, monkeypatch):
    m = made(tmp_path, monkeypatch)
    for change in (lambda v: v["data"]["zebra_pc"].update(excluded_ids=[]),
                   lambda v: v["cards"].update(searchqa="wrong"),
                   lambda v: v["clients"]["solver"]["D"]["M"].update(searchqa=16384)):
        value = copy.deepcopy(m)
        change(value)
        value = p.record("manifest-v2-3", "engineering_fixture", {
            k: v for k, v in value.items() if k not in ("version", "evidence", p.RECORD_HASH)})
        with pytest.raises(ValueError):
            manifest.check(value)


def test_end_read_isolation_before_consent_and_only_zebra_after(tmp_path, monkeypatch):
    m = made(tmp_path, monkeypatch)
    root = Path(m["root"])
    accesses = []
    fake_rows = [z.normalize({**row(index=i), "puzzle": ("There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. "
                                                   "Unique synthetic canary puzzle number %d.") % i},
                             partition="test") for i in range(6)]
    def panel(pinned, bench, *, access):
        accesses.append((bench, access.unit))
        assert bench == z.BENCH
        return fake_rows, {"panel_hash": digest(fake_rows), "excluded_without_pages": [], "source_files": None}
    args = dict(pools=m["data"]["pools"], run=m[p.RECORD_HASH], evidence=m["evidence"], panel=panel,
                order=(z.BENCH,), configuration=p.ZEBRA_PC_V1)
    with pytest.raises(ValueError, match="consent"):
        evaluation.make_read_canaries(root, m["data"]["pinned"], **args)
    assert accesses == [] and not (root / protocol.CANARIES).exists()
    write_json(root / "shared" / "consent.json", CONSENT)
    value = evaluation.make_read_canaries(root, m["data"]["pinned"], **args)
    assert accesses == [(z.BENCH, evaluation.READ_CANARY_UNIT)]
    assert value["counts"] == {z.BENCH: 5} and value["extends"] is None
    assert evaluation.load_canaries(root, read=True, configuration=p.ZEBRA_PC_V1) == value["canaries"]
    assert not (root / protocol.CANARIES).exists()
    evaluation.make_read_canaries(root, m["data"]["pinned"], **args)
    assert len(accesses) == 1
    assert evaluation.test_tasks(root / "shared", m["data"]["pinned"], z.BENCH, "D/test/zebralogic",
        run=m[p.RECORD_HASH], runtime={}, native=None, workers=None, evidence=m["evidence"], panel=panel) == fake_rows
    assert [bench for bench, _ in accesses] == [z.BENCH, z.BENCH]


def test_chain_single_read_resume_and_empty_not_read(tmp_path):
    for accepted in (False, True):
        directory = tmp_path / str(accepted)
        setting = chain_setting(directory, chain_="D")
        setting.extra.update(configuration=p.ZEBRA_PC_V1,
                             test_read_terms={"D": {z.BENCH: "1000"}})
        learn, launched = Learn(accept=accepted), Launch(directory)
        assert chain.run(setting, "D", learn=learn, launch=launched) == {"status": "complete"}
        assert [(k, bench) for _, k, bench, _ in learn.calls] == [(1, z.BENCH)]
        assert [spec["bench"] for spec in launched.specs] == ([z.BENCH] if accepted else [])
        result = p.verified(read_json(setting.root / "D" / chain.TEST_READ), "test-read")
        assert result["status"] == ("read" if accepted else "not_read")
        assert chain.run(setting, "D", learn=learn, launch=launched) == {"status": "complete"}
        assert len(learn.calls) == 1


@pytest.mark.parametrize("chain_id", ("G", "D"))
def test_single_launchable_chain_can_report_without_other_chain(tmp_path, chain_id):
    from skillopt.execskill import readout
    root = tmp_path / "run"
    write_json(root / chain_id / "test-read.json", p.record("test-read", "engineering_fixture", {
        "status": "not_read"}))
    value = {"root": str(root), p.RECORD_HASH: "a" * 64, "evidence": "engineering_fixture",
             "configuration": p.ZEBRA_PC_V1, "data": {"launchable_chains": [chain_id]}}
    assert readout.report(value, out=tmp_path / "report") == {chain_id: "not_read"}
    assert sorted(path.name for path in root.iterdir()) == [chain_id]
    # Historical profiles continue requiring both chains, even if given this extra key.
    value["configuration"] = p.MAIN_V2_3
    with pytest.raises(ValueError, match="neither read nor ended"):
        readout.report(value, out=tmp_path / "legacy-report")
    assert not (tmp_path / "legacy-report").exists()


def test_missing_consent_records_only_one_waiting_unit(tmp_path):
    setting = chain_setting(tmp_path, chain_="D", consent=False)
    setting.extra["configuration"] = p.ZEBRA_PC_V1
    with pytest.raises(Pause, match="consent"):
        chain.read_consent(setting, "D")
    value = p.verified(read_json(setting.root / "D" / chain.READ_WAITING), "read-waiting")
    assert value["read_units"] == 1 and value["read_attempts"] == 0


def test_s2_real_solver_scorer_flow_and_projection_are_zebra_only(tmp_path, monkeypatch):
    m = made(tmp_path, monkeypatch)
    setting = manifest.setting_of(m, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    source = {json.dumps(task["public"], sort_keys=True): task for task in setting.pools[z.BENCH]}
    fake = FakeSolver(tmp_path / "solver", [(None, lambda system, user: answer(source[json.dumps(z.parse_user(user), sort_keys=True)]))],
                      max_tokens=16384, read_timeout=600)
    setting = replace(setting, clients=lambda model, bench: fake.client, cooldown=0, workers=1)
    setting.budget.declare(budgets.chain_caps("D", p.ZEBRA_PC_V1))
    result = zebra_smoke._s2(setting, "D")
    assert result["passed"] and result["parsed"] == result["items"] == 10 and len(fake.requests) == 10
    assert set(result["measurements"]["per_class"]) == {z.BENCH}
    projected = zebra_smoke.projection(result, "D")
    assert projected["passed"] and set(projected["per_cell"]) == {z.BENCH}
    assert projected["per_cell"][z.BENCH]["procedure_assumed"] is True
    assert projected["other_chain"].startswith("not_projected")
    assert zebra_smoke._s2(setting, "D") == result and len(fake.requests) == 10


def test_new_cli_commands_and_old_default_recipe():
    from scripts.run_execskill import parser
    parsed = parser().parse_args(["zpc-smoke", "--manifest", "m", "--chain", "G", "--stage", "S1"])
    assert parsed.chain == "G" and parsed.stage == "S1"
    assert smoke.ITEM_SETS == ("searchqa", "alfworld", "officeqa", "livemath", "spreadsheetbench")
    assert protocol.CONFIGURATIONS.get(p.ZEBRA_PC_V1) is None
    assert manifest.registered() == manifest.registered(protocol.MAIN_V2_3)
    assert p.STAGE_READ[p.ZEBRA_PC_V1] is False


def test_s1_confirms_each_role_and_resumes_without_calls(tmp_path, monkeypatch):
    from tests.execskill_fakes import FakeGLM
    m = made(tmp_path, monkeypatch)
    setting = manifest.setting_of(m, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    solver = FakeSolver(tmp_path / "solver-first", [(None, "ready")], max_tokens=16384, read_timeout=600)
    roles = FakeGLM(tmp_path / "roles-first", lambda system, payload: "ready")
    setting = replace(setting, clients=lambda model, bench: roles.client if bench is None else solver.client,
                      cooldown=0)
    setting.budget.declare({**budgets.chain_caps("D", p.ZEBRA_PC_V1), **budgets.first_call_caps("D")})
    result = zebra_smoke._s1(setting, "D")
    assert result["passed"] and len(solver.requests) == 1 and len(roles.seen) == 4
    assert set(result["roles"]) == {"engineer", "examiner", "describer", "leakage"}
    assert zebra_smoke._s1(setting, "D") == result
    assert len(solver.requests) == 1 and len(roles.seen) == 4


def test_s2_unknown_outcomes_never_count_as_parsed(tmp_path, monkeypatch):
    m = made(tmp_path, monkeypatch)
    setting = manifest.setting_of(m, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    setting.budget.declare(budgets.chain_caps("D", p.ZEBRA_PC_V1))
    def unknown(context, jobs, **kwargs):
        return [{"cell": cell, "final": {"token": "unknown"}, "judge": {"format": {"violation": None}},
                 "enabled": [], "sends": []} for cell, task, arm in jobs]
    monkeypatch.setattr(zebra_smoke, "run_cells", unknown)
    result = zebra_smoke._s2(setting, "D")
    assert result["passed"] is False and result["parsed"] == 0


def test_split_manifest_pins_are_bound_to_exact_zebra_paths(tmp_path):
    path = tmp_path / "split-manifest.json"
    write_json(path, {"output_sha256": {"other/pool.json": z.POOL_SHA256,
                                       "other/sealed-holdout.json": z.SEALED_SHA256}})
    with pytest.raises(ValueError, match="exact ZebraLogic paths"):
        zebra_smoke._split_pins(path)
    path.write_text(json.dumps({"output_sha256": {"zebralogic/pool.json": z.POOL_SHA256,
                                       "zebralogic/sealed-holdout.json": z.SEALED_SHA256}}))
    assert zebra_smoke._split_pins(path)["field"] == "output_sha256"


def test_stage_reuse_requires_same_manifest_chain_and_stage(tmp_path):
    path = tmp_path / "S1.json"
    fields = {"configuration": p.ZEBRA_PC_V1, "chain": "G", "stage": "S1", "manifest": "a" * 64,
              "result": {"passed": True}}
    write_json(path, p.record("zebra-smoke-stage", "smoke", fields))
    assert zebra_smoke._checked_stage(path, {p.RECORD_HASH: "a" * 64}, "G", "S1")["result"]["passed"]
    for manifest_sha, chain_id, stage in (("b" * 64, "G", "S1"), ("a" * 64, "D", "S1"),
                                           ("a" * 64, "G", "S2")):
        with pytest.raises(ValueError, match="belongs to this manifest"):
            zebra_smoke._checked_stage(path, {p.RECORD_HASH: manifest_sha}, chain_id, stage)


def test_stale_s0_or_smoke_cannot_certify_current_manifest(tmp_path, monkeypatch):
    import hashlib
    snapshot_sha = hashlib.sha256(b"synthetic snapshot\n").hexdigest()
    monkeypatch.setattr(zebra_smoke.prelaunch, "sha256_list", lambda root: "synthetic snapshot\n")
    provenance = tmp_path / "provenance.json"
    write_json(provenance, {"snapshot_root": str(manifest.REPO), "sha256_list_sha256": snapshot_sha})
    s0_path, smoke_path = tmp_path / "s0.json", tmp_path / "smoke-result.json"
    fields = {"passed": True, "registration": z.identity(), "snapshot_root": str(manifest.REPO),
              "snapshot_sha256": "0" * 64}
    write_json(s0_path, p.record("zebra-s0", "smoke", fields))
    args = dict(root=p.ZEBRA_PC_ROOT, s0_file=s0_path, provenance=provenance, roles_repo=tmp_path,
                elucid_env=tmp_path / "elucid.env", route_b_env=tmp_path / "route-b.env")
    with pytest.raises(ValueError, match="current code/test snapshot"):
        zebra_smoke.make_manifest(tmp_path / "never.json", **args)
    fields["snapshot_sha256"] = snapshot_sha
    checked = p.record("zebra-s0", "smoke", fields)
    s0_path.write_text(json.dumps(checked))
    write_json(smoke_path, p.record("zebra-smoke-result", "smoke", {
        "passed": True, "configuration": p.ZEBRA_PC_V1, "chain": "D", "s0": "stale",
        "snapshot_sha256": snapshot_sha}))
    with pytest.raises(ValueError, match="belongs to this S0"):
        zebra_smoke.make_manifest(tmp_path / "never.json", smoke_results=[smoke_path], **args)
    assert not (tmp_path / "never.json").exists()


def test_s3_executes_one_actual_fixture_training_round_and_reuses_units(tmp_path, monkeypatch):
    from skillopt.execskill import smoke_roles
    from tests.test_execskill_zpc_pipeline import build
    setting, services, fake_solver, glm = build(tmp_path, monkeypatch)
    items = setting.pools[z.BENCH][:6]
    result = smoke_roles.zebra_training(setting, services, "D", items)
    assert result["passed"] and result["rounds"] == 1 and result["fixtures"] == 6
    assert result["training"]["cells"] == 12
    assert result["research"] == "not_applicable" and result["generator"] == "selection"
    calls = len(fake_solver.requests), len(glm.seen)
    assert smoke_roles.zebra_training(setting, services, "D", items) == result
    assert (len(fake_solver.requests), len(glm.seen)) == calls
