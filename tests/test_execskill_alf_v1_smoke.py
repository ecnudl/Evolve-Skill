"""ALF-only smoke commands and actual synthetic stateful training, all offline."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_pipeline import offline
from tests.test_execskill_alf_v1_pipeline import BENCH, RUNTIME, build, fixture_pool
from tests.test_execskill_manifest import MEASURED, fake_environment, given, tree
from tests.execskill_fakes import FakeSolver
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import alf_smoke as a, budgets, engineer, manifest, prelaunch, profiles as p, routes, smoke
from skillopt.execskill.sandbox import client as sandbox


def source_preparation(root, monkeypatch):
    root.mkdir(parents=True, exist_ok=True)
    values = given(root)
    pool, _ = fixture_pool(root / "authored-games")
    pool_file = root / "pool.json"
    write_json(pool_file, pool)
    pool_pin = {"path": str(pool_file), "sha256": hashlib.sha256(pool_file.read_bytes()).hexdigest()}
    test, split = str(root / "unopened-test-panel.json"), str(root / "unopened-split.json")
    values["data"] = {"pools": {BENCH: pool_pin}, "pinned": {
        "paths": {"split": split, "test": {BENCH: test, "searchqa": "unrelated-must-not-open"}},
        "sha256": {test: "a" * 64, split: "b" * 64}}}
    values["runtime"][BENCH] = dict(RUNTIME)
    values["clients"]["solver"] = {chain: manifest.solver_block(chain, env_path=block["env_path"],
        branch=block["branch"], configuration=p.MAIN_V2_2) for chain, block in values["clients"]["solver"].items()}
    values["clients"]["routes"] = {"D": {"B": routes.pin("D", "B", env_path=root / "route.env",
        solver_block=values["clients"]["solver"]["D"], configuration=p.MAIN_V2_2)}}
    card = values["cards"][BENCH]
    monkeypatch.setattr(manifest, "ALFWORLD_CARD_IDENTITY", (len(card), hashlib.sha256(card.encode()).hexdigest()))
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "c" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored.py"})
    source = root / "main-preparation.json"
    value = manifest.make(source, evidence="engineering_fixture", configuration=p.MAIN_V2_2,
                          environment_found=fake_environment(), measured=MEASURED, **values)
    return source, value, pool


def s0_files(root, monkeypatch):
    source, old, pool = source_preparation(root / "source", monkeypatch)
    snapshot = tree(root / "snapshot")
    monkeypatch.setattr(manifest, "REPO", snapshot)
    sandbox_record = p.record("sandbox-selftest", "smoke", {"passed": True,
        "measured": dict(MEASURED), "limits": {key: asdict(value) for key, value in sandbox.LIMITS.items()}})
    selftest = root / "selftest.json"
    write_json(selftest, sandbox_record)
    checked = a.collect_s0(root / "s0", preparation_file=source, snapshot_root=snapshot, selftest=selftest,
                           checks={"passed": True, "summary": "authored checks"})
    provenance = root / "snapshot-provenance.json"
    write_json(provenance, {"build_tree": str(snapshot), "git_head": "e" * 40, "snapshot_root": str(snapshot),
                           "sha256_list_sha256": checked["snapshot_sha256"], "env_files_absent": True})
    options = {"root": root / "smoke", "s0_file": root / "s0" / a.S0_FILE, "provenance": provenance,
               "roles_repo": root / "role-credentials", "elucid_env": root / "elucid.env",
               "route_b_env": root / "route.env", "environment_found": fake_environment(), "smoke_chain": "D"}
    return checked, options, old, pool


def test_snapshot_and_existing_verifier_copy_only_registered_source(tmp_path):
    original = tree(tmp_path / "source")
    (original / "tests").mkdir()
    (original / "tests" / "test_authored.py").write_text("pass\n")
    value = a.snapshot(tmp_path / "snapshot", source=original, git_head="f" * 40)
    assert value["sha256_list_sha256"] == hashlib.sha256(prelaunch.sha256_list(original).encode()).hexdigest()
    assert prelaunch.verify_snapshot(tmp_path / "snapshot" / "sha256-list.txt", root=tmp_path / "snapshot",
                                    build_tree=original, git_head="f" * 40) == value
    assert not (tmp_path / "snapshot" / "shared" / "consent.json").exists()


def test_s0_imports_only_alf_metadata_and_registered_slices_without_test_access(tmp_path, monkeypatch):
    checked, _, old, _ = s0_files(tmp_path, monkeypatch)
    assert checked["passed"] and checked["sealed_reads"] == 0
    assert checked["slice_counts"] == {"smoke": 12, "run": 60, "accept": 150, "select": 100}
    assert checked["cards"] == {BENCH: old["cards"][BENCH]}
    assert checked["pinned"]["paths"]["test"] == {BENCH: old["data"]["pinned"]["paths"]["test"][BENCH]}
    assert set(checked["registration"]) == {"preparation", "pool", "test", "split", "card_sha256",
                                             "contract_sha256", "runtime_sha256"}
    assert checked["registration"]["preparation"]["record_sha256"] == old[p.RECORD_HASH]
    assert not Path(checked["registration"]["test"]["path"]).exists()
    assert not Path(checked["registration"]["split"]["path"]).exists()
    assert not list(tmp_path.rglob("consent.json"))


@pytest.mark.parametrize("change,reason", [("card", "task card"), ("views", "pre-reset"),
                                          ("pool_pin", "differs from its pin"), ("alias", "separate")])
def test_s0_refuses_bad_card_pin_view_or_sealed_alias(tmp_path, monkeypatch, change, reason):
    source, old, pool = source_preparation(tmp_path / "source", monkeypatch)
    if change == "views":
        a._slices(pool, RUNTIME)["run"][0]["views_runtime_sha256"] = "wrong"
        path = tmp_path / "modified-pool.json"
        write_json(path, pool)
        old["data"]["pools"][BENCH] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    elif change == "pool_pin":
        old["data"]["pools"][BENCH]["sha256"] = "0" * 64
    elif change == "alias":
        old["data"]["pools"][BENCH] = {"path": old["data"]["pinned"]["paths"]["test"][BENCH], "sha256": "a" * 64}
    else:
        old["cards"][BENCH] += " changed"
    source = tmp_path / "modified-preparation.json"
    write_json(source, p.record("manifest", old["evidence"], {
        key: value for key, value in old.items() if key not in ("version", "evidence", p.RECORD_HASH)}))
    with pytest.raises(ValueError, match=reason):
        a.collect_s0(tmp_path / "s0", preparation_file=source, selftest="must-not-read", checks={"passed": True})
    assert not (tmp_path / "s0" / a.S0_FILE).exists()


def test_manifest_preparation_constructs_isolated_smoke_then_real_identity(tmp_path, monkeypatch):
    checked, options, _, _ = s0_files(tmp_path, monkeypatch)
    path = tmp_path / "smoke.json"
    made = a.make_manifest(path, **options)
    assert made["configuration"] == p.ALFWORLD_V1 and made["data"]["launchable_chains"] == ["D"]
    assert made["evidence"] == "smoke" and made["data"]["alfworld_v1"] == checked["registration"]
    assert set(made["cards"]) == set(made["runtime"]) == set(made["data"]["pools"]) == {BENCH}
    result_path = tmp_path / "smoke-result.json"
    write_json(result_path, p.record("alfworld-smoke-result", "smoke", {
        "passed": True, "configuration": p.ALFWORLD_V1, "chain": "D", "s0": checked[p.RECORD_HASH],
        "snapshot_sha256": checked["snapshot_sha256"], "manifest_path": str(path), "manifest": made[p.RECORD_HASH],
        "read_estimate": 12345}))
    options.update(root=p.RUN_ROOTS[p.ALFWORLD_V1], smoke_chain=None, smoke_results=[result_path])
    real = a.make_manifest(tmp_path / "real.json", **options)
    assert real["evidence"] == p.REAL_RUN_EVIDENCE[p.ALFWORLD_V1]
    assert real["data"]["test_read_estimate"] == {"D": 12345}
    assert not list(tmp_path.rglob("consent.json"))


@pytest.mark.parametrize("changed", ["snapshot", "smoke_configuration", "smoke_s0"])
def test_manifest_rejects_stale_snapshot_or_other_profile_receipts(tmp_path, monkeypatch, changed):
    checked, options, _, _ = s0_files(tmp_path, monkeypatch)
    if changed == "snapshot":
        (manifest.REPO / "scripts" / "run_execskill.py").write_text("print('changed')\n")
    else:
        result = {"passed": True, "configuration": p.ALFWORLD_V1, "chain": "D", "s0": checked[p.RECORD_HASH],
                  "snapshot_sha256": checked["snapshot_sha256"]}
        result["configuration" if changed == "smoke_configuration" else "s0"] = "wrong"
        result_path = tmp_path / "stale-result.json"
        write_json(result_path, p.record("alfworld-smoke-result", "smoke", result))
        options["smoke_results"] = [result_path]
    with pytest.raises(ValueError, match="snapshot|ALFWorld smoke"):
        a.make_manifest(tmp_path / "must-not-exist.json", **options)
    assert not (tmp_path / "must-not-exist.json").exists()


def test_s1_first_responses_use_alf_bounds_and_resume(tmp_path, monkeypatch):
    setting, _, fake, glm, _ = build(tmp_path, monkeypatch)
    # The scripted role can return any delivered first-call response.
    setting.budget.declare(budgets.first_call_caps("D"))
    found = a._s1(setting)
    assert found["passed"] and set(found["roles"]) == {"engineer", "examiner", "describer", "leakage"}
    assert len(fake.requests) == 1 and fake.requests[0]["max_tokens"] == p.ELUCID_MAX_TOKENS[BENCH]
    calls = len(fake.requests), len(glm.seen)
    assert a._s1(setting) == found and (len(fake.requests), len(glm.seen)) == calls


def test_s2_runs_three_smoke_games_on_real_shell_and_reuses_units(tmp_path, monkeypatch):
    setting, _, fake, _, sessions = build(tmp_path, monkeypatch)
    result = a._s2(setting)
    assert result["passed"] and result["items"] == result["completed"] == 3
    assert result["wins"] == 0 and len(sessions) == 3 and all(session.closed for session in sessions)
    assert set(result["measurements"]["per_class"]) == {BENCH}
    calls = len(fake.requests)
    assert a._s2(setting) == result and len(fake.requests) == calls


def test_s2_unknown_cells_do_not_pass(tmp_path, monkeypatch):
    setting, _, _, _, _ = build(tmp_path, monkeypatch)
    def unknown(context, jobs, **kwargs):
        return [{"cell": cell, "enabled": [], "final": {"token": "unknown"}, "sends": []}
                for cell, task, arm in jobs]
    monkeypatch.setattr(a, "run_cells", unknown)
    assert not a._s2(setting)["passed"]


def test_s3_real_stateful_fixture_training_c1_c9_and_resumption(tmp_path, monkeypatch):
    setting, services, _, glm, _ = build(tmp_path, monkeypatch)
    def answer(system, user):
        view = json.loads(user)
        return "<action>" + view["admissible_commands"][-1] + "</action>"
    fake = FakeSolver(tmp_path / "fixture-solver", [(None, answer)], max_tokens=p.ELUCID_MAX_TOKENS[BENCH],
                      read_timeout=p.ELUCID_READ_TIMEOUT[BENCH])
    setting = replace(setting, clients=lambda model, bench: glm.client if bench is None else fake.client)
    found = a._s3(setting, services)
    assert found["passed"] and found["rounds"] == 1 and found["fixtures"] == 2, found["failed_substages"]
    checks = found["S3a"]["proposal"]["checks"]
    assert {row["check"] for row in checks} >= {"C1", "C2", "C3", "C4", "C5", "C5b", "C6", "C6b", "C6c", "C7", "C8", "C9"}
    assert all(row["passed"] for row in checks)
    assert found["S3a"]["training"]["cells"] > 0 and found["role_measurements"]["engineer"]["tokens"] > 0
    assert found["S3a"]["state_changes"] == {"games": 2, "checked": 2, "changed": 2, "passed": True}
    assert found["S3b"]["parsed"] and found["S3b"]["training"] is not None
    assert all(len(json.loads(body["messages"][1]["content"])["recent_history"]) <= 3 for body in fake.requests)
    trajectories = [p.verified(read_json(path), "trajectory") for path in
                    (setting.root / "D" / "role-smoke" / "S3a").glob("**/trajectories/*.json")]
    stateful = [row["alfworld_steps"] for row in trajectories
                if row["arm_kind"] == "candidate"]
    assert stateful and all(steps[0]["state_sha256"] != steps[1]["state_sha256"] for steps in stateful)
    calls = len(fake.requests), len(glm.seen)
    assert a._s3(setting, services) == found and (len(fake.requests), len(glm.seen)) == calls


def _fixture_solver(setting, roles, path):
    fake = FakeSolver(path, [(None, lambda system, user:
        "<action>" + json.loads(user)["admissible_commands"][-1] + "</action>")],
        max_tokens=p.ELUCID_MAX_TOKENS[BENCH], read_timeout=p.ELUCID_READ_TIMEOUT[BENCH])
    return replace(setting, clients=lambda model, bench: roles.client if bench is None else fake.client), fake


@pytest.mark.parametrize("reply,parsed,failed", [("unparseable", False, None),
    ('```json\n{"changes":[{"kind":"new","description":"Invalid proposal."}]}\n```\n```python\nx=1\n```',
     True, "C1")])
def test_s3a_records_authored_parse_and_check_failure_without_role_calls(tmp_path, monkeypatch, reply, parsed, failed):
    setting, services, _, roles, _ = build(tmp_path, monkeypatch)
    setting, fake = _fixture_solver(setting, roles, tmp_path / "failure-solver")
    monkeypatch.setattr(a, "authored_reply", lambda: reply)
    result = a._s3a(setting, services)
    assert not result["passed"] and result["proposal"]["parsed"] is parsed
    assert result["proposal"].get("failed") == failed
    assert result["training"] is None and result["state_changes"]["checked"] == 0
    assert roles.seen == []
    calls = len(fake.requests)
    assert a._s3a(setting, services) == result and len(fake.requests) == calls


def test_s3_resume_after_authored_checkpoint_does_not_repeat_authored_solver_calls(tmp_path, monkeypatch):
    setting, services, _, roles, _ = build(tmp_path, monkeypatch)
    setting, fake = _fixture_solver(setting, roles, tmp_path / "interrupted-solver")
    ordinary = a._s3b
    def interrupted(*args):
        raise RuntimeError("fixture interruption before S3b")
    monkeypatch.setattr(a, "_s3b", interrupted)
    with pytest.raises(RuntimeError, match="fixture interruption"):
        a._s3(setting, services)
    authored = p.verified(read_json(setting.root / "D" / "role-smoke" / "S3a" / "result.json"),
                          "alfworld-smoke-substage")["result"]
    assert authored["passed"] and roles.seen == []
    previous = deepcopy(fake.requests)
    monkeypatch.setattr(a, "_s3b", ordinary)
    run = a.step._run
    def only_ordinary(st, cut):
        assert st.chain_root.name == "S3b", "Completed S3a must resume from its own checkpoint"
        return run(st, cut)
    monkeypatch.setattr(a.step, "_run", only_ordinary)
    result = a._s3(setting, services)
    assert result["passed"] and result["S3a"] == authored and fake.requests[:len(previous)] == previous


@pytest.mark.parametrize("defect", ["no_candidate", "wrong_arm", "missing_game", "wrong_package", "wrong_unit",
                                    "constant", "missing_hash", "no_cells"])
def test_state_guard_uses_every_actual_candidate_game_only(tmp_path, monkeypatch, defect):
    setting, services, _, roles, _ = build(tmp_path, monkeypatch)
    setting, fake = _fixture_solver(setting, roles, tmp_path / "state-solver")
    result = a._s3a(setting, services)
    assert result["passed"]
    st, cut = a._fixture_step(setting, services, "S3a")
    candidate = a.step._package(st, result["proposal"]["candidate_sha256"])
    evaluated = deepcopy(result["training"])
    rows = deepcopy(a.step._unit_trajectories(st, "train-r1"))
    actual = [row for row in rows if row["arm_kind"] == "candidate"]
    if defect == "no_candidate":
        rows = [row for row in rows if row not in actual]
    elif defect == "wrong_arm":
        actual[0]["arm"] = "S"
    elif defect == "missing_game":
        rows.remove(actual[0])
    elif defect == "wrong_package":
        actual[0]["package_sha256"] = "b" * 64
    elif defect == "wrong_unit":
        actual[0]["unit"] = "D/s1-alfworld/run"
    elif defect == "constant":
        for entry in actual[0]["alfworld_steps"]:
            entry["state_sha256"] = actual[0]["alfworld_steps"][0]["state_sha256"]
    elif defect == "missing_hash":
        actual[0]["alfworld_steps"][1]["state_sha256"] = {}
    else:
        evaluated["cells"] = 0
    monkeypatch.setattr(a.step, "_unit_trajectories", lambda *args: rows)
    assert not a._state_changes(st, cut, candidate, evaluated)["passed"]


def test_projection_prices_measured_games_all_redos_and_roles_without_other_chain():
    s2 = {"items": 3, "tokens_per_cell": 26000, "settled_tokens": 78000,
          "measurements": {"actual": 78000, "request_bytes": {BENCH: 1000}},
          "solver_bounds": {"branch": "E", "longest": None,
                            "ledger_bound": p.ledger_bound(p.CHAINS["D"], BENCH, branch="E")}}
    s3 = {"role_measurements": {"engineer": {"calls": 1, "tokens": 3000, "per_call": 3000, "request_bytes": 1000}}}
    found = a.projection(s2, s3)
    assert found["passed"] and set(found["per_cell"]) == {BENCH}
    assert all(name.startswith("D:") for name in {*found["scopes"], *found["roles"]})
    assert found["read_estimate"] == 26000 * (134 + 670 * float(p.PROCEDURE_ARM_FACTOR[1]))
    reserve = found["scopes"]["D:redo"]["projected"] - 26000 * 1.6 * 880
    assert reserve > 0 and found["scopes"]["D:redo"]["cap"] == p.CONFIGURATIONS[p.ALFWORLD_V1]["redo_reserve"]
    expensive = deepcopy(s2)
    expensive["tokens_per_cell"] *= 1000
    assert not a.projection(expensive, s3)["passed"]
    switched = deepcopy(s2)
    switched["solver_bounds"] = {"branch": "N", "longest": 256,
        "ledger_bound": p.ledger_bound(p.CHAINS["D"], BENCH, branch="N", longest=256)}
    alternative = a.projection(switched, s3)
    assert alternative["solver_bounds"] == switched["solver_bounds"]
    assert alternative["scopes"]["D:redo"]["projected"] - found["scopes"]["D:redo"]["projected"] == 4 * (
        switched["solver_bounds"]["ledger_bound"] - s2["solver_bounds"]["ledger_bound"])
    assert smoke.engineer_request_floor(p.ALFWORLD_V1) == p.ROLE_INPUT_BYTES + max(
        len(value.encode()) for value in (engineer.ENGINEER_SYSTEM_ALF_V1,
                                          engineer.ENGINEER_SYSTEM_SINGLE_ALF_V1, engineer.ANALYST_SYSTEM))


@pytest.mark.parametrize("change", ["configuration", "manifest", "chain", "stage"])
def test_stage_reuse_refuses_other_identity(tmp_path, change):
    value = {"configuration": p.ALFWORLD_V1, "manifest": "a" * 64, "chain": "D", "stage": "S1",
             "result": {"passed": True}}
    value[change] = "wrong"
    path = tmp_path / "S1.json"
    write_json(path, p.record("alfworld-smoke-stage", "smoke", value))
    with pytest.raises(ValueError, match="belongs"):
        a._checked_stage(path, {"configuration": p.ALFWORLD_V1, p.RECORD_HASH: "a" * 64}, "S1")


def test_cli_additions_preserve_old_defaults_and_restrict_alf_to_d():
    from scripts.run_execskill import HANDLERS, parser
    commands = parser()
    assert commands.parse_args(["alf-smoke", "--manifest", "m", "--stage", "S1"]).chain == "D"
    assert commands.parse_args(["alf-s0", "--out", "o", "--preparation", "m"]).preparation == "m"
    assert commands.parse_args(["zpc-smoke", "--manifest", "m", "--chain", "G", "--stage", "S1"]).configuration == p.ZEBRA_PC_V1
    assert {"alf-snapshot", "alf-s0", "alf-manifest", "alf-smoke"} <= HANDLERS.keys()
    with pytest.raises(SystemExit):
        commands.parse_args(["alf-smoke", "--manifest", "m", "--chain", "G", "--stage", "S1"])


def test_generic_manifest_command_refuses_alf_before_historical_exclusions(tmp_path):
    from types import SimpleNamespace
    from scripts.run_execskill import make_manifest
    path = tmp_path / "pins.json"
    write_json(path, {"configuration": p.ALFWORLD_V1, "evidence": "smoke", "root": str(tmp_path / "run"),
                      "data": {}, "limits": {}, "measured": {}})
    with pytest.raises(ValueError, match="Use alf-manifest"):
        make_manifest(SimpleNamespace(pins=path, s0_pins=None))
    assert not (tmp_path / "run").exists()


def test_real_stage_runner_persists_all_four_stages_and_resumes_without_calls(tmp_path, monkeypatch):
    setting, services, _, glm, _ = build(tmp_path, monkeypatch)
    def answer(system, user):
        if system == p.FIRST_CALL_SYSTEM:
            return "ready"
        return "<action>" + json.loads(user)["admissible_commands"][-1] + "</action>"
    fake = FakeSolver(tmp_path / "stage-solver", [(None, answer)], max_tokens=p.ELUCID_MAX_TOKENS[BENCH],
                      read_timeout=p.ELUCID_READ_TIMEOUT[BENCH])
    setting = replace(setting, clients=lambda model, bench: glm.client if bench is None else fake.client)
    m = {"configuration": p.ALFWORLD_V1, "evidence": "smoke", p.RECORD_HASH: setting.run,
         "data": {"s0_sha256": "a" * 64, "snapshot_sha256": "b" * 64}}
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: m)
    monkeypatch.setattr(manifest, "setting_of", lambda *args, **kwargs: setting)
    monkeypatch.setattr(manifest, "services_of", lambda *args, **kwargs: services)
    path = tmp_path / "smoke.json"
    values = [a.run_stage(path, name) for name in a.STAGES]
    assert all(value["result"]["passed"] for value in values)
    result = p.verified(read_json(setting.root / "D" / "lean-smoke" / "result.json"), "alfworld-smoke-result")
    assert result["passed"] and result["sealed_reads"] == 0 and result["s0"] == "a" * 64
    calls = len(fake.requests), len(glm.seen)
    assert [a.run_stage(path, name) for name in a.STAGES] == values
    assert (len(fake.requests), len(glm.seen)) == calls
    assert not list(tmp_path.rglob("consent.json"))
