"""ALFWorld v2 registration, isolated dispatch and actual authored lean smoke."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (alf_smoke as a, budgets, chain, engineer, evaluation, manifest, policy,
                               profiles as p, protocol, smoke, step, zebra_smoke)
from skillopt.execskill.package import empty
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import FakeSolver
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_alf_v1_pipeline import BENCH, build
from tests.test_execskill_alf_v1_profile import alf_manifest
from tests.test_execskill_alf_v1_smoke import source_preparation
from tests.test_execskill_chain import CONSENT
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, tree
from tests.test_execskill_zpc_pipeline import offline


CONFIG = p.ALFWORLD_V2


def test_alf_v2_is_the_second_v27_profile_and_inherits_alf_v1_by_value():
    assert p.FEATURE_FAMILIES[CONFIG] == "v2.7"
    assert all(fn(CONFIG) for fn in (p.is_alfworld, p.is_alfworld_v2, p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27))
    assert not p.is_zebra(CONFIG)
    assert p.is_alfworld(p.ALFWORLD_V1) and not p.is_alfworld_v2(p.ALFWORLD_V1)
    assert p.FEATURE_FAMILIES[p.ALFWORLD_V1] == "v2.6" and not p.is_v27(p.ALFWORLD_V1)
    assert {name for name in p.CONFIGURATIONS if p.is_v27(name)} == {p.ZEBRA_PC_V5, CONFIG}
    assert {name for name in p.CONFIGURATIONS if p.is_alfworld(name)} == {p.ALFWORLD_V1, CONFIG}
    assert not p.is_alfworld(None) and not p.is_alfworld_v2(None)
    for name in ("CONFIGURATIONS", "LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING",
                 "ACCEPT_RULES", "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
                 "IDENTICAL_REQUEST_REUSE", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "CONFIG_STEP_CAPS",
                 "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP", "CONFIG_CAP_FACTOR", "STAGE_READ",
                 "COST_CHECK_PAUSES", "TEST_READ_CELLS", "POLICY_VERSIONS"):
        assert getattr(p, name)[CONFIG] == getattr(p, name)[p.ALFWORLD_V1], name
    assert p.CONFIGURATIONS[CONFIG] is not p.CONFIGURATIONS[p.ALFWORLD_V1]
    assert p.ACCEPT_RULES[CONFIG] is not p.ACCEPT_RULES[p.ALFWORLD_V1]
    assert p.TRAIN_ROUNDS == 6 and p.TRAIN_PATIENCE == 2
    assert p.active_benches(CONFIG) == p.read_benches(CONFIG) == (BENCH,)
    assert p.launchable_chains(CONFIG) == ("D",)
    assert p.read_arms_of(CONFIG) == p.TEST_ARMS and p.stage_arms_max(CONFIG) == 0


def test_alf_v2_identity_caps_and_policy_are_registered_independently():
    assert p.RUN_ROOTS[CONFIG] == p.ALFWORLD_V2_ROOT == "/data/execskill-20261026-alfworld-v2"
    assert p.ALFWORLD_V2_MANIFEST == p.ALFWORLD_V2_ROOT + "-manifest.json"
    assert p.CHAIN_NAMESPACES[CONFIG] == {"G": "G-alf2", "D": "D-alf2"}
    assert p.REAL_RUN_EVIDENCE[CONFIG] == "alfworld_v2_real_run"
    assert p.REAL_RUN_EVIDENCE[CONFIG] in protocol.EVIDENCE
    assert p.ACCEPT_FRESHNESS[CONFIG] == p.ALFWORLD_V2_FRESHNESS
    assert p.ALFWORLD_V2_FRESHNESS == "alfworld_split_v1_slices_reused_alf1_acceptance_unused"
    assert p.ENGINEER_RECORDS[CONFIG] == "engineer-alf-v2"
    assert p.POLICY_VERSIONS[CONFIG] == policy.POLICY_VERSION_V25
    assert policy.source_limit(p.POLICY_VERSIONS[CONFIG]) == 16000
    assert budgets.caps(CONFIG) == budgets.caps(p.ALFWORLD_V1)
    assert budgets.caps(CONFIG)["overall"] == 1_002_600_000
    assert p.CONFIGURATIONS[CONFIG] == {"order": (BENCH,), "solver_cap": 885_000_000,
        "test_read_cap": 182_000_000, "redo_reserve": 209_000_000}
    assert p.TEST_READ_CELLS[CONFIG] == {BENCH: (134, 670)}
    per_cell = {BENCH: {"card": 45000, "procedure_assumed": True}}
    assert p.read_estimate_terms(per_cell, 3, CONFIG) == p.read_estimate_terms(per_cell, 3, p.ALFWORLD_V1)
    for kind in ("engineer", "manifest"):
        value = p.record(kind + "-alf-v2", p.REAL_RUN_EVIDENCE[CONFIG], {})
        assert p.verified(value, kind) == value
    for kind in ("procedure", "cell", "decision"):
        with pytest.raises(ValueError, match="another kind"):
            p.verified(p.record(kind + "-alf-v2", p.REAL_RUN_EVIDENCE[CONFIG], {}), kind)


def v2_manifest(tmp_path, monkeypatch):
    before = alf_manifest(tmp_path, monkeypatch)
    fields = {key: deepcopy(before[key]) for key in manifest.GIVEN}
    fields["data"]["alfworld_v2"] = fields["data"].pop("alfworld_v1")
    found = manifest.make(tmp_path / "alf-v2.json", evidence="engineering_fixture", configuration=CONFIG,
        measured=MEASURED, environment_found=fake_environment(), **fields)
    return found, before


def test_manifest_pins_alf_v2_prompts_and_only_inherited_alf_metadata(tmp_path, monkeypatch):
    found, before = v2_manifest(tmp_path, monkeypatch)
    assert found["version"] == p.kind("manifest-alf-v2") and manifest.check(found) == found
    assert found["prompt_sha"]["engineer"] == engineer.ENGINEER_PROMPT_SINGLE_ALF_V2_SHA256
    assert found["prompt_sha"]["v2"]["engineer"] == engineer.ENGINEER_PROMPT_ALF_V2_SHA256
    assert found["prompt_sha"] != before["prompt_sha"]
    assert found["data"]["alfworld_features"] == manifest.alfworld_features(CONFIG)
    assert found["data"]["alfworld_v2"] == before["data"]["alfworld_v1"]
    assert "alfworld_v1" not in found["data"] and "zebra_pc" not in found["data"]
    assert found["cards"] == before["cards"] and found["runtime"] == before["runtime"]
    assert found["sandbox"]["policy_sha256"] == before["sandbox"]["policy_sha256"]
    assert found["clients"] == before["clients"] and found["caps"] == before["caps"]
    setting = manifest.setting_of(found, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert p.namespace_of(setting, "D") == "D-alf2"
    assert set(setting.pools) == set(setting.cards) == set(setting.runtime) == {BENCH}
    services = manifest.services_of(found, "D", setting=setting, transport=NO_CALLS)
    assert services.sources is services.engine is services.checker is None
    assert smoke.engineer_request_floor(CONFIG) == p.ROLE_INPUT_BYTES + max(len(value.encode()) for value in (
        engineer.ENGINEER_SYSTEM_ALF_V2, engineer.ENGINEER_SYSTEM_SINGLE_ALF_V2, engineer.ANALYST_SYSTEM))
    assert not Path(found["data"]["alfworld_v2"]["test"]["path"]).exists()
    assert not Path(found["data"]["alfworld_v2"]["split"]["path"]).exists()


@pytest.mark.parametrize("configuration,bench", [(CONFIG, BENCH), (p.ZEBRA_PC_V5, "zebralogic")])
def test_v27_guards_keep_each_profile_on_its_own_d_step_before_work(tmp_path, monkeypatch, configuration, bench):
    def reached(*args, **kwargs):
        raise RuntimeError("reached the allowed step")
    monkeypatch.setattr(step, "_Step", reached)
    setting = SimpleNamespace(root=tmp_path, extra={"configuration": configuration})
    parent = empty(step="D/s0", evidence="engineering_fixture")
    for chain_id, wrong_bench in (("G", bench), ("D", "zebralogic" if bench == BENCH else BENCH)):
        with pytest.raises(ValueError, match="single .* step"):
            step.run_step(setting, chain_id, wrong_bench, 1, parent, services=None)
    with pytest.raises(RuntimeError, match="reached the allowed step"):
        step.run_step(setting, "D", bench, 1, parent, services=None)
    with pytest.raises(ValueError, match="chain D only"):
        chain.run(setting, "G", learn=reached, launch=reached)
    with pytest.raises(ValueError, match="only chain D|chain D only"):
        manifest.setting_of({"configuration": configuration}, "G")


def test_smoke_families_refuse_each_others_profiles_before_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: pytest.fail("Wrong smoke loaded a manifest"))
    with pytest.raises(ValueError, match="ZebraLogic configuration"):
        zebra_smoke.run_stage("unopened", "D", "S1", configuration=CONFIG)
    with pytest.raises(ValueError, match="ALFWorld-only configuration"):
        a.run_stage("unopened", "S1", configuration=p.ZEBRA_PC_V5)
    with pytest.raises(ValueError, match="chain D"):
        a.run_stage("unopened", "S1", chain_id="G", configuration=CONFIG)


def s0_files(root, monkeypatch):
    source, old, _ = source_preparation(root / "source", monkeypatch)
    snapshot = tree(root / "snapshot")
    monkeypatch.setattr(manifest, "REPO", snapshot)
    selftest = root / "selftest.json"
    write_json(selftest, p.record("sandbox-selftest", "smoke", {"passed": True,
        "measured": dict(MEASURED), "limits": {key: asdict(value) for key, value in sandbox.LIMITS.items()}}))
    options = dict(preparation_file=source, snapshot_root=snapshot, selftest=selftest,
                   checks={"passed": True, "summary": "authored checks"})
    before = a.collect_s0(root / "s0-v1", **options)
    checked = a.collect_s0(root / "s0-v2", configuration=CONFIG, **options)
    assert {key: value for key, value in checked.items() if key not in ("configuration", p.RECORD_HASH)} == {
        key: value for key, value in before.items() if key not in ("configuration", p.RECORD_HASH)}
    provenance = root / "snapshot-provenance.json"
    write_json(provenance, {"build_tree": str(snapshot), "git_head": "e" * 40, "snapshot_root": str(snapshot),
        "sha256_list_sha256": checked["snapshot_sha256"], "env_files_absent": True})
    return checked, before, {"root": root / "smoke", "s0_file": root / "s0-v2" / a.S0_FILE,
        "provenance": provenance, "roles_repo": root / "credentials", "elucid_env": root / "elucid.env",
        "route_b_env": root / "route.env", "environment_found": fake_environment(), "smoke_chain": "D",
        "configuration": CONFIG}


def test_s0_slices_pins_and_manifest_receipts_are_profile_bound(tmp_path, monkeypatch):
    checked, before, options = s0_files(tmp_path, monkeypatch)
    assert checked["configuration"] == CONFIG and before["configuration"] == p.ALFWORLD_V1
    assert checked["sealed_reads"] == 0 and checked["slice_counts"] == {
        "smoke": 12, "run": 60, "accept": 150, "select": 100}
    path = tmp_path / "smoke.json"
    with pytest.raises(ValueError, match="passing ALFWorld S0"):
        a.make_manifest(path, **{**options, "s0_file": tmp_path / "s0-v1" / a.S0_FILE})
    made = a.make_manifest(path, **options)
    assert made["configuration"] == CONFIG and made["data"]["alfworld_v2"] == checked["registration"]
    assert made["data"]["launchable_chains"] == ["D"]
    result = {"passed": True, "configuration": p.ALFWORLD_V1, "chain": "D", "s0": checked[p.RECORD_HASH],
        "snapshot_sha256": checked["snapshot_sha256"], "manifest_path": str(path), "manifest": made[p.RECORD_HASH],
        "read_estimate": 12345}
    result_path = tmp_path / "result.json"
    write_json(result_path, p.record("alfworld-smoke-result", "smoke", result))
    options.update(root=p.RUN_ROOTS[CONFIG], smoke_chain=None, smoke_results=[result_path])
    with pytest.raises(ValueError, match="passed measured ALFWorld smoke"):
        a.make_manifest(tmp_path / "real.json", **options)
    result["configuration"] = CONFIG
    result_path.write_text(json.dumps(p.record("alfworld-smoke-result", "smoke", result)))
    real = a.make_manifest(tmp_path / "real.json", **options)
    assert real["evidence"] == p.REAL_RUN_EVIDENCE[CONFIG] and real["root"] == p.ALFWORLD_V2_ROOT
    assert real["data"]["test_read_estimate"] == {"D": 12345}
    assert not list(tmp_path.rglob("consent.json"))
    assert not Path(checked["registration"]["test"]["path"]).exists()


@pytest.mark.parametrize("name,args", [
    ("snapshot", ["--out", "out", "--git-head", "f" * 40]),
    ("s0", ["--out", "out", "--preparation", "main"]),
    ("manifest", ["--out", "out", "--root", "root", "--s0", "s0", "--provenance", "prov",
                  "--roles-repo", "roles", "--elucid-env", "env", "--route-b-env", "route"]),
    ("smoke", ["--manifest", "m", "--stage", "S1"]),
])
def test_alf_cli_commands_dispatch_v2_and_preserve_v1_defaults(monkeypatch, name, args):
    from scripts.run_execskill import HANDLERS, parser
    commands = parser()
    assert commands.parse_args(["alf-" + name, *args]).configuration == p.ALFWORLD_V1
    parsed = commands.parse_args(["alf-" + name, *args, "--configuration", CONFIG])
    calls = []
    result = {"passed": True, "slice_counts": {}, "sealed_reads": 0, p.RECORD_HASH: "a" * 64,
              "root": "fixture", "data": {"launchable_chains": ["D"]}, "result": {"passed": True}}
    def fake(*positional, **kwargs):
        calls.append(kwargs)
        return result
    method = {"snapshot": "snapshot", "s0": "collect_s0", "manifest": "make_manifest", "smoke": "run_stage"}[name]
    monkeypatch.setattr(a, method, fake)
    HANDLERS["alf-" + name](parsed)
    assert len(calls) == 1 and calls[0]["configuration"] == CONFIG


def test_real_alf_v2_lean_smoke_runs_all_stages_and_resumes(tmp_path, monkeypatch):
    setting, services, _, glm, _ = build(tmp_path, monkeypatch)
    inherited_reply = glm.replies
    glm.replies = lambda system, payload: inherited_reply(
        engineer.ENGINEER_SYSTEM_ALF_V1 if system == engineer.ENGINEER_SYSTEM_ALF_V2 else system, payload)
    def answer(system, user):
        return "ready" if system == p.FIRST_CALL_SYSTEM else "<action>" + json.loads(user)["admissible_commands"][-1] + "</action>"
    fake = FakeSolver(tmp_path / "stage-solver", [(None, answer)], max_tokens=p.ELUCID_MAX_TOKENS[BENCH],
                      read_timeout=p.ELUCID_READ_TIMEOUT[BENCH])
    setting = replace(setting, clients=lambda model, bench: glm.client if bench is None else fake.client,
                      extra={**setting.extra, "configuration": CONFIG})
    m = {"configuration": CONFIG, "evidence": "smoke", p.RECORD_HASH: setting.run,
         "data": {"s0_sha256": "a" * 64, "snapshot_sha256": "b" * 64}}
    monkeypatch.setattr(manifest, "load", lambda *args, **kwargs: m)
    monkeypatch.setattr(manifest, "setting_of", lambda *args, **kwargs: setting)
    monkeypatch.setattr(manifest, "services_of", lambda *args, **kwargs: services)
    path = tmp_path / "smoke.json"
    values = [a.run_stage(path, name, configuration=CONFIG) for name in a.STAGES]
    assert all(value["result"]["passed"] for value in values)
    third = values[2]["result"]
    assert third["S3a"]["passed"] and third["S3a"]["model_role_calls"] == 0 and third["S3b"]["passed"]
    assert third["S3b"]["engineer"]["engineer"]["version"] == p.kind("engineer-alf-v2")
    assert any(system == engineer.ENGINEER_SYSTEM_ALF_V2 for system, payload in glm.seen)
    result = p.verified(read_json(setting.root / "D" / "lean-smoke" / "result.json"), "alfworld-smoke-result")
    assert result["configuration"] == CONFIG and result["passed"] and result["sealed_reads"] == 0
    calls = len(fake.requests), len(glm.seen)
    assert [a.run_stage(path, name, configuration=CONFIG) for name in a.STAGES] == values
    assert calls == (len(fake.requests), len(glm.seen)) and not list(tmp_path.rglob("consent.json"))


def test_alf_v2_canaries_require_consent_and_refuse_v1_reuse(tmp_path):
    pool = tmp_path / "pool.json"
    write_json(pool, [{"task_id": "training", "public": {"game_file":
        "/synthetic/json_2.1.1/train/pick_and_place_simple-Mug-None-Desk-1/trial_TRAIN/game.tw-pddl"}}])
    pools = {BENCH: {"path": str(pool), "sha256": hashlib.sha256(pool.read_bytes()).hexdigest()}}
    panel_rows = [{"task_id": "sealed-%d" % n, "public": {"game_file":
        "/synthetic/json_2.1.1/valid_unseen/pick_and_place_simple-Mug-None-Desk-%d/trial_UNSEEN/game.tw-pddl" % n}}
        for n in range(6)]
    accesses = []
    def panel(pinned, bench, *, access):
        accesses.append(bench)
        assert bench == BENCH
        return panel_rows, {"panel_hash": digest(panel_rows)}
    args = dict(pools=pools, run="authored-alf-v2", evidence="engineering_fixture", panel=panel,
                order=(BENCH,), configuration=CONFIG)
    root = tmp_path / "root"
    with pytest.raises(ValueError, match="consent"):
        evaluation.make_read_canaries(root, {}, **args)
    assert accesses == [] and not root.exists()
    write_json(root / "shared" / "consent.json", CONSENT)
    found = evaluation.make_read_canaries(root, {}, **args)
    assert accesses == [BENCH] and found["configuration"] == CONFIG
    assert evaluation.load_canaries(root, read=True, configuration=CONFIG) == found["canaries"]
    with pytest.raises(ValueError, match="trusted ALFWorld"):
        evaluation.load_canaries(root, read=True, configuration=p.ALFWORLD_V1)
