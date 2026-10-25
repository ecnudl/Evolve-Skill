"""v2.7 registration and D-only orchestration on authored offline fixtures."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import (budgets, chain, engineer, evaluation, manifest, policy, profiles as p,
                               protocol, smoke, step, zebra_smoke, zebralogic as z)
from skillopt.execskill.package import Procedure, empty
from skillopt.execskill.sandbox import client
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_chain import CONSENT
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment
from tests.test_execskill_v24_profile import padded_source
from tests.test_execskill_zpc_adapter import pool_rows, row
from tests.test_execskill_zpc_orchestration import made
from tests.test_execskill_zpc_profile import procedure


CONFIG = p.ZEBRA_PC_V5


def test_v27_inherits_v26_without_changing_other_feature_families():
    assert p.FEATURE_FAMILIES[CONFIG] == "v2.7"
    assert all(fn(CONFIG) for fn in (p.is_zebra, p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27))
    assert all(not p.is_v27(name) for name in (*p.CONFIGURATIONS, None) if name not in (CONFIG, p.ALFWORLD_V2))
    assert p.FEATURE_FAMILIES[p.ALFWORLD_V1] == "v2.6" and p.is_v26(p.ALFWORLD_V1)
    assert p.is_v26(p.ZEBRA_PC_V4) and not p.is_v26(p.ZEBRA_PC_V3)
    with pytest.raises(ValueError, match="Unknown run configuration"):
        p.is_v27("unregistered")
    for name in ("CONFIGURATIONS", "LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING",
                 "ACCEPT_RULES", "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
                 "IDENTICAL_REQUEST_REUSE", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "CONFIG_STEP_CAPS",
                 "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP", "CONFIG_CAP_FACTOR", "STAGE_READ",
                 "COST_CHECK_PAUSES", "TEST_READ_CELLS", "POLICY_VERSIONS"):
        assert getattr(p, name)[CONFIG] == getattr(p, name)[p.ZEBRA_PC_V4], name
    assert p.CONFIGURATIONS[CONFIG] is not p.CONFIGURATIONS[p.ZEBRA_PC_V4]
    assert p.ACCEPT_RULES[CONFIG] is not p.ACCEPT_RULES[p.ZEBRA_PC_V4]
    assert p.TRAIN_ROUNDS == 6 and p.TRAIN_PATIENCE == 2


def test_v5_identity_keeps_v4_slices_and_per_chain_caps_but_registers_d_only():
    assert p.RUN_ROOTS[CONFIG] == p.ZEBRA_PC_V5_ROOT == "/data/execskill-20261026-zebra-pc-v5"
    assert p.ZEBRA_PC_V5_MANIFEST == p.RUN_ROOTS[CONFIG] + "-manifest.json"
    assert p.REAL_RUN_EVIDENCE[CONFIG] == "zebra_pc_v5_real_run"
    assert p.REAL_RUN_EVIDENCE[CONFIG] in protocol.EVIDENCE
    assert p.ACCEPT_FRESHNESS[CONFIG] == "zebra_split_v1_slices_reused_zpc4_acceptance_used_twice"
    assert p.active_benches(CONFIG) == p.read_benches(CONFIG) == (z.BENCH,)
    assert p.stage_arms_max(CONFIG) == 0 and p.read_arms_of(CONFIG) == p.TEST_ARMS
    assert p.CONFIGURATIONS[CONFIG] == {"order": (z.BENCH,), "solver_cap": 235000000,
                                      "test_read_cap": 54000000, "redo_reserve": 43300000}
    assert p.CONFIG_GLM_CAP[CONFIG] == 117600000
    assert p.launchable_chains(CONFIG) == ("D",)
    for name in p.CHAINS:
        assert p.namespace_of(SimpleNamespace(extra={"configuration": CONFIG}), name) == name + "-zpc5"
        assert budgets.chain_caps(name, CONFIG) == budgets.chain_caps(name, p.ZEBRA_PC_V4)
    expected = {**budgets.chain_caps("D", CONFIG), **budgets.first_call_caps("D")}
    assert budgets.caps(CONFIG) == expected
    assert not any(scope.startswith("G:") for scope in budgets.caps(CONFIG))
    pool = [z.normalize(item) for item in pool_rows()]
    cuts = [step._cut(SimpleNamespace(setting=SimpleNamespace(extra={"configuration": name},
                     pools={z.BENCH: pool}), bench=z.BENCH), frozenset())
            for name in (p.ZEBRA_PC_V1, p.ZEBRA_PC_V2, p.ZEBRA_PC_V3, p.ZEBRA_PC_V4, CONFIG)]
    assert all(cut == cuts[0] for cut in cuts)


def test_v27_versions_only_engineer_and_manifest_and_reuses_exact_v25_policy():
    assert p.ENGINEER_RECORDS[CONFIG] == "engineer-v2-7"
    version = p.POLICY_VERSIONS[CONFIG]
    assert version == policy.POLICY_VERSION_V25 and policy.source_limit(version) == 16000
    assert policy.policy_sha256(version=version) == \
        "7b7b52f7e8caf5bee291e7f223f4391d574244483aaa3e923917f53feb25efd2"
    value = replace(procedure(z.BENCH, p.BENCHES), source=padded_source(16000), policy_version=version).to_json()
    assert value["version"] == p.kind("procedure-v2-5")
    assert Procedure.from_json(value).to_json() == value
    for name in ("engineer", "manifest"):
        value = p.record(name + "-v2-7", p.REAL_RUN_EVIDENCE[CONFIG], {})
        assert p.verified(value, name) == value
    for name in ("procedure", "decision", "cell"):
        with pytest.raises(ValueError, match="another kind"):
            p.verified(p.record(name + "-v2-7", p.REAL_RUN_EVIDENCE[CONFIG], {}), name)


def v27_manifest(tmp_path, monkeypatch):
    base = made(tmp_path, monkeypatch)
    given = {key: deepcopy(base[key]) for key in manifest.GIVEN}
    given["data"]["launchable_chains"] = ["D"]
    given["data"]["test_read_estimate"] = {"D": 1000}
    given["data"]["test_read_terms"] = {"D": {z.BENCH: "1000"}}
    return manifest.make(tmp_path / "v27.json", evidence="engineering_fixture", configuration=CONFIG,
                         environment_found=fake_environment(), measured=MEASURED, **given)


def test_manifest_and_services_pin_v27_prompts_policy_and_d_eligibility(tmp_path, monkeypatch):
    value = v27_manifest(tmp_path, monkeypatch)
    assert value["version"] == p.kind("manifest-v2-7")
    assert value["data"]["zebra_pc_features"] == manifest.zebra_features(CONFIG)
    assert value["data"]["zebra_pc_features"]["family"] == "v2.7"
    assert value["data"]["zebra_pc_features"]["launchable_chains"] == ["D"]
    assert value["sandbox"]["policy_sha256"] == policy.policy_sha256(version=policy.POLICY_VERSION_V25)
    assert value["prompt_sha"]["engineer"] == engineer.ENGINEER_PROMPT_SINGLE_ZPC_V27_SHA256
    assert value["prompt_sha"]["v2"]["engineer"] == engineer.ENGINEER_PROMPT_ZPC_V27_SHA256
    assert value["prompt_sha"] != manifest.prompt_sha(p.ZEBRA_PC_V4)
    setting = manifest.setting_of(value, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert p.configuration_of(setting) == CONFIG and p.namespace_of(setting, "D") == "D-zpc5"
    assert set(setting.pools) == set(setting.cards) == set(setting.runtime) == {z.BENCH}
    services = manifest.services_of(value, "D", setting=setting, transport=NO_CALLS)
    assert services.sources is services.engine is services.checker is None
    assert smoke.engineer_request_floor(CONFIG) == p.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
        engineer.ENGINEER_SYSTEM_ZPC_V27, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V27, engineer.ANALYST_SYSTEM))
    for launchable in (None, [], ["G"], ["G", "D"]):
        fields = {key: deepcopy(item) for key, item in value.items()
                  if key not in ("version", "evidence", p.RECORD_HASH)}
        fields["data"]["launchable_chains"] = launchable
        with pytest.raises(ValueError, match="chain D only"):
            manifest.check(p.record("manifest-v2-7", "engineering_fixture", fields))


def test_v5_g_rejected_before_manifest_pool_or_worker_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("An unsupported chain accessed a file, client or worker")
    monkeypatch.setattr(manifest, "load", forbidden)
    monkeypatch.setattr(zebra_smoke, "read_json", forbidden)
    monkeypatch.setattr(chain, "chain_root", forbidden)
    with pytest.raises(ValueError, match="chain D only"):
        manifest.setting_of({"configuration": CONFIG}, "G")
    with pytest.raises(ValueError, match="chain D only"):
        chain.run(SimpleNamespace(extra={"configuration": CONFIG}), "G", learn=forbidden, launch=forbidden)
    with pytest.raises(ValueError, match="chain D's single ZebraLogic step"):
        step.run_step(SimpleNamespace(extra={"configuration": CONFIG}), "G", z.BENCH, 1,
                      empty(step="D/s0", evidence="engineering_fixture"), services=None)
    with pytest.raises(ValueError, match="chain D only"):
        zebra_smoke.run_stage(tmp_path / "never.json", "G", "S1", configuration=CONFIG)
    with pytest.raises(ValueError, match="chain D only"):
        zebra_smoke.make_manifest(tmp_path / "never.json", root=tmp_path, s0_file="never",
            provenance="never", roles_repo="never", elucid_env="never", route_b_env="never",
            smoke_chain="G", configuration=CONFIG)
    with pytest.raises(ValueError, match="chain D only"):
        zebra_smoke.projection({}, "G", CONFIG)


def test_v5_preparation_requires_own_s0_and_d_smoke(tmp_path, monkeypatch):
    listing = "authored v27 snapshot fixture\n"
    sha = hashlib.sha256(listing.encode()).hexdigest()
    monkeypatch.setattr(zebra_smoke.prelaunch, "sha256_list", lambda root: listing)
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "a" * 64})
    provenance = tmp_path / "provenance.json"
    write_json(provenance, {"build_tree": str(tmp_path / "source"), "git_head": "f" * 40,
        "snapshot_root": str(manifest.REPO), "sha256_list_sha256": sha, "env_files_absent": True})
    fields = {"passed": True, "configuration": p.ZEBRA_PC_V4, "registration": z.identity(),
        "snapshot_root": str(manifest.REPO), "snapshot_sha256": sha,
        "pool": {"path": z.POOL_PATH, "sha256": z.POOL_SHA256},
        "split_manifest": {"path": z.SPLIT_MANIFEST_PATH, "sha256": "b" * 64, "field": "output_sha256"},
        "measured": MEASURED, "limits": {key: asdict(value) for key, value in client.LIMITS.items()}}
    s0 = tmp_path / "s0.json"
    write_json(s0, p.record("zebra-s0", "smoke", fields))
    args = dict(s0_file=s0, provenance=provenance, roles_repo=tmp_path / "credentials",
        elucid_env=tmp_path / "elucid.env", route_b_env=tmp_path / "route-b.env",
        environment_found=fake_environment(), configuration=CONFIG)
    smoke_path = tmp_path / "smoke-manifest.json"
    with pytest.raises(ValueError, match="S0 belongs"):
        zebra_smoke.make_manifest(smoke_path, root=tmp_path / "smoke", smoke_chain="D", **args)
    fields["configuration"] = CONFIG
    checked = p.record("zebra-s0", "smoke", fields)
    s0.write_text(json.dumps(checked))
    prepared = zebra_smoke.make_manifest(smoke_path, root=tmp_path / "smoke", smoke_chain="D", **args)
    assert prepared["data"]["launchable_chains"] == ["D"]
    assert set(prepared["data"]["test_read_estimate"]) == set(prepared["data"]["test_read_terms"]) == {"D"}
    smoke_result = tmp_path / "smoke-result.json"
    result = {"passed": True, "configuration": p.ZEBRA_PC_V4, "chain": "D", "s0": checked[p.RECORD_HASH],
        "snapshot_sha256": sha, "manifest_path": str(smoke_path), "manifest": prepared[p.RECORD_HASH], "read_estimate": 1000}
    write_json(smoke_result, p.record("zebra-smoke-result", "smoke", result))
    with pytest.raises(ValueError, match="passed measured zebra smoke"):
        zebra_smoke.make_manifest(tmp_path / "never.json", root=p.RUN_ROOTS[CONFIG], smoke_results=[smoke_result], **args)
    result.update(configuration=CONFIG, chain="G")
    smoke_result.write_text(json.dumps(p.record("zebra-smoke-result", "smoke", result)))
    with pytest.raises(ValueError, match="chain D only"):
        zebra_smoke.make_manifest(tmp_path / "never.json", root=p.RUN_ROOTS[CONFIG], smoke_results=[smoke_result], **args)
    result["chain"] = "D"
    smoke_result.write_text(json.dumps(p.record("zebra-smoke-result", "smoke", result)))
    value = zebra_smoke.make_manifest(tmp_path / "real.json", root=p.RUN_ROOTS[CONFIG], smoke_results=[smoke_result], **args)
    assert value["configuration"] == CONFIG and value["evidence"] == "zebra_pc_v5_real_run"
    assert value["data"]["launchable_chains"] == ["D"] and value["root"] == p.ZEBRA_PC_V5_ROOT
    assert value["data"]["zebra_pc"] == prepared["data"]["zebra_pc"] == z.identity()


def test_v5_canary_identity_preserves_consent_and_refuses_v4_reuse(tmp_path, monkeypatch):
    value = v27_manifest(tmp_path, monkeypatch)
    root, accesses = Path(value["root"]), []
    tasks = [z.normalize({**row(index=i), "puzzle": row(index=i)["puzzle"]
                          + "A distinct authored v5 panel canary %d." % i}, partition="test") for i in range(6)]
    def panel(pinned, bench, *, access):
        accesses.append(bench)
        assert bench == z.BENCH
        return tasks, {"panel_hash": "a" * 64}
    args = dict(pools=value["data"]["pools"], run=value[p.RECORD_HASH], evidence=value["evidence"],
                panel=panel, order=(z.BENCH,), configuration=CONFIG)
    with pytest.raises(ValueError, match="consent"):
        evaluation.make_read_canaries(root, value["data"]["pinned"], **args)
    assert accesses == []
    write_json(root / "shared" / "consent.json", CONSENT)
    found = evaluation.make_read_canaries(root, value["data"]["pinned"], **args)
    assert accesses == [z.BENCH] and found["configuration"] == CONFIG
    assert evaluation.load_canaries(root, read=True, configuration=CONFIG) == found["canaries"]
    with pytest.raises(ValueError, match="trusted ZebraLogic"):
        evaluation.load_canaries(root, read=True, configuration=p.ZEBRA_PC_V4)


@pytest.mark.parametrize("name,args", [
    ("snapshot", ["--out", "out", "--git-head", "f" * 40]), ("s0", ["--out", "out"]),
    ("manifest", ["--out", "out", "--root", "root", "--s0", "s0", "--provenance", "prov",
                  "--roles-repo", "roles", "--elucid-env", "env", "--route-b-env", "route"]),
    ("smoke", ["--manifest", "m", "--chain", "D", "--stage", "S1"]),
])
def test_zpc_cli_commands_accept_v5_and_preserve_v1_defaults(name, args):
    from scripts.run_execskill import parser
    assert parser().parse_args(["zpc-" + name, *args]).configuration == p.ZEBRA_PC_V1
    assert parser().parse_args(["zpc-" + name, *args, "--configuration", CONFIG]).configuration == CONFIG


def test_smoke_projection_keeps_v4_d_budget_formulas():
    s2 = {"tokens_per_cell": 5300, "items": 10, "settled_tokens": 53000,
          "measurements": {"actual": 53000, "request_bytes": {z.BENCH: 1000}}}
    before = zebra_smoke.projection(s2, "D", p.ZEBRA_PC_V4)
    assert zebra_smoke.projection(s2, "D", CONFIG) == {
        **before, "configuration": CONFIG, "other_chain": "not_launchable_in_this_configuration"}
