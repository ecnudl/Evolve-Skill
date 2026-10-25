"""v2.5 registration/policy plumbing on synthetic fixtures; no external execution."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import (budgets, engineer, evaluation, manifest, policy, profiles as p,
                               protocol, smoke, step, zebra_smoke, zebralogic as z)
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Package, Procedure
from skillopt.execskill.sandbox import client, worker
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_chain import CONSENT
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment
from tests.test_execskill_v24_profile import padded_source
from tests.test_execskill_zpc_adapter import pool_rows, row
from tests.test_execskill_zpc_orchestration import made
from tests.test_execskill_zpc_profile import procedure

V25 = policy.POLICY_VERSION_V25
CONFIG = p.ZEBRA_PC_V3


def test_v25_family_inherits_v24_and_preserves_every_unchanged_feature_by_value():
    assert p.FEATURE_FAMILIES[CONFIG] == "v2.5"
    assert all(fn(CONFIG) for fn in (p.is_zebra, p.is_v23, p.is_v24, p.is_v25))
    for name in (*protocol.CONFIGURATIONS, p.ZEBRA_PC_V1, p.ZEBRA_PC_V2, None):
        assert not p.is_v25(name)
    assert p.is_v24(p.ZEBRA_PC_V2) and not p.is_v24(p.ZEBRA_PC_V1)
    with pytest.raises(ValueError, match="Unknown run configuration"):
        p.is_v25("unregistered")
    for table in ("CONFIGURATIONS", "LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING",
                  "ACCEPT_RULES", "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
                  "IDENTICAL_REQUEST_REUSE", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "CONFIG_STEP_CAPS",
                  "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP", "CONFIG_CAP_FACTOR", "STAGE_READ",
                  "COST_CHECK_PAUSES", "TEST_READ_CELLS"):
        assert getattr(p, table)[CONFIG] == getattr(p, table)[p.ZEBRA_PC_V2], table
    assert p.ENGINEER_RECORDS[CONFIG] == "engineer-v2-5"
    assert p.POLICY_VERSIONS[CONFIG] == V25
    assert p.CONFIGURATIONS[CONFIG] is not p.CONFIGURATIONS[p.ZEBRA_PC_V2]
    assert p.ACCEPT_RULES[CONFIG] is not p.ACCEPT_RULES[p.ZEBRA_PC_V2]
    assert p.TRAIN_ROUNDS == 6


def test_v3_identity_freshness_slices_and_budget_formulas_are_registered():
    assert p.RUN_ROOTS[CONFIG] == p.ZEBRA_PC_V3_ROOT == "/data/execskill-20261025-zebra-pc-v3"
    assert p.ZEBRA_PC_V3_MANIFEST == p.RUN_ROOTS[CONFIG] + "-manifest.json"
    assert p.REAL_RUN_EVIDENCE[CONFIG] == "zebra_pc_v3_real_run"
    assert p.REAL_RUN_EVIDENCE[CONFIG] in protocol.EVIDENCE
    assert p.ACCEPT_FRESHNESS[CONFIG] == "zebra_split_v1_slices_reused_zpc2_acceptance_used_once"
    assert p.active_benches(CONFIG) == p.read_benches(CONFIG) == (z.BENCH,)
    assert p.stage_arms_max(CONFIG) == 0 and p.read_arms_of(CONFIG) == p.TEST_ARMS
    for chain in p.CHAINS:
        setting = SimpleNamespace(extra={"configuration": CONFIG})
        assert p.namespace_of(setting, chain) == chain + "-zpc3"
        assert budgets.chain_caps(chain, CONFIG) == budgets.chain_caps(chain, p.ZEBRA_PC_V2)
    assert p.read_estimate_terms({z.BENCH: {"card": 5300}}, 1, CONFIG) == {z.BENCH: 7844000}
    pool = [z.normalize(item) for item in pool_rows()]
    cuts = []
    for name in (p.ZEBRA_PC_V1, p.ZEBRA_PC_V2, CONFIG):
        setting = SimpleNamespace(extra={"configuration": name}, pools={z.BENCH: pool})
        cuts.append(step._cut(SimpleNamespace(setting=setting, bench=z.BENCH), frozenset()))
    assert cuts[0] == cuts[1] == cuts[2]


@pytest.mark.parametrize("size", [10000, 10001, 15999, 16000, 16001])
def test_v25_policy_byte_boundary_does_not_expand_older_policies(size):
    source = padded_source(size)
    assert len(source.encode()) == size
    for version, cap in ((policy.POLICY_VERSION, 6000), (policy.POLICY_VERSION_V23, 6000),
                         (policy.POLICY_VERSION_V24, 10000), (V25, 16000)):
        assert bool(policy.check(source, version=version)) is (size > cap)
        assert policy.source_limit(version) == cap
    assert policy.MAX_SOURCE_BYTES == protocol.MAX_PROCEDURE_BYTES == 6000


def test_v25_policy_json_retains_rules_and_has_a_distinct_immutable_identity(tmp_path):
    excluded = {"version", "registration", "max_source_bytes"}
    assert {k: v for k, v in policy.POLICY_V25.items() if k not in excluded} == {
        k: v for k, v in policy.POLICY_V24.items() if k not in excluded}
    raw = policy.POLICY_PATH_V25.read_bytes()
    assert json.loads(raw) == policy.POLICY_V25
    assert hashlib.sha256(raw).hexdigest() == policy.policy_sha256(version=V25) == \
        "7b7b52f7e8caf5bee291e7f223f4391d574244483aaa3e923917f53feb25efd2"
    copy_path = tmp_path / "policy-copy.json"
    policy.write_policy_json(copy_path, version=V25)
    assert copy_path.read_bytes() == raw
    assert policy.policy_sha256(version=policy.POLICY_VERSION_V24) == \
        "a0290490d63820e5f00ff7f09fe5da1e24070230ff1611faf31b80ba516510ca"
    assert policy.check("import re\nRX = re.compile('x')\n" + padded_source(1000), version=V25) == []
    assert policy.check("import os\n" + padded_source(1000), version=V25)
    assert policy.check("VALUE = '" + "x" * 2001 + "'\n" + padded_source(1000), version=V25)
    assert policy.check(padded_source(16000).replace("xxx", "ééé", 1), version=V25)[0].rule == "size"


def test_v25_procedure_and_record_stamps_roundtrip_while_total_package_cap_stays_64000():
    old = procedure(z.BENCH, p.BENCHES)
    modern = replace(old, source=padded_source(16000), policy_version=V25)
    value = modern.to_json()
    assert value["version"] == protocol.kind("procedure-v2-5")
    assert Procedure.from_json(value) == modern and protocol.verified(value, "procedure") == value
    with pytest.raises(PackageInvalid, match="Policy violations"):
        replace(modern, policy_version=policy.POLICY_VERSION_V24)
    four = tuple(replace(modern, id="p-zebralogic-1-%d" % n) for n in range(1, 5))
    assert len(Package(four, "s1", modern.evidence).procedures) == 4
    with pytest.raises(PackageInvalid, match="sources"):
        Package(four + (replace(modern, id="p-zebralogic-1-5"),), "s1", modern.evidence)
    for name in ("engineer", "manifest"):
        value = protocol.record(name + "-v2-5", p.REAL_RUN_EVIDENCE[CONFIG], {})
        assert protocol.verified(value, name) == value
    with pytest.raises(ValueError, match="another kind"):
        protocol.verified(protocol.record("decision-v2-5", p.REAL_RUN_EVIDENCE[CONFIG], {}), "decision")


def test_v25_worker_envelope_loads_mixed_policies_without_promoting_old_entries(monkeypatch):
    base = procedure(z.BENCH, p.BENCHES)
    procedures = tuple(replace(base, id="p-zebralogic-1-%d" % n, policy_version=version,
                               source=padded_source(cap))
                       for n, (version, cap) in enumerate(((policy.POLICY_VERSION, 6000),
                           (policy.POLICY_VERSION_V23, 6000), (policy.POLICY_VERSION_V24, 10000), (V25, 16000)), 1))
    package = Package(procedures, "s1", base.evidence)
    host, requests = client.Worker(), []
    host.package, host.kind, host._entries = package, "cell", client._entries(package)
    def exchange(request, timeout):
        requests.append(request)
        if request["op"] == "ping":
            return {"ok": True, "worker": client.WORKER_PROTOCOL, "worker_sha256": client.worker_sha256(),
                    "hashseed": "0", "policy_sha256": policy.policy_sha256()}
        return worker.handle_load({"seq": 1, **request}, {"loaded": None}, policy)
    monkeypatch.setattr(host, "_exchange", exchange)
    host._handshake()
    request = requests[-1]
    assert not host.rejected and request["policy_version"] == V25
    assert request["policy_sha256"] == policy.policy_sha256(version=V25)
    request["procedures"][2]["source"] = padded_source(10001)
    result = worker.handle_load({"seq": 1, **request}, {"loaded": None}, policy)
    assert result["rejected"] == [{"id": procedures[2].id, "reason": "policy:size"}]
    assert procedures[-1].id in result["loaded"]
    for version in (policy.POLICY_VERSION, policy.POLICY_VERSION_V23, policy.POLICY_VERSION_V24):
        refused = {**request, "seq": 1, "policy_version": version,
                   "policy_sha256": policy.policy_sha256(version=version)}
        assert not worker.handle_load(refused, {"loaded": None}, policy)["ok"]


def v25_manifest(tmp_path, monkeypatch):
    old = made(tmp_path, monkeypatch)
    given = {key: copy.deepcopy(old[key]) for key in manifest.GIVEN}
    return manifest.make(tmp_path / "v25.json", evidence="engineering_fixture", configuration=CONFIG,
                         environment_found=fake_environment(), measured=MEASURED, **given)


def test_manifest_prompts_policy_setting_and_services_follow_v25(tmp_path, monkeypatch):
    value = v25_manifest(tmp_path, monkeypatch)
    assert value["version"] == p.kind("manifest-v2-5")
    assert value["data"]["zebra_pc_features"] == manifest.zebra_features(CONFIG)
    assert value["data"]["zebra_pc_features"]["family"] == "v2.5"
    assert value["sandbox"]["policy_sha256"] == policy.policy_sha256(version=V25)
    assert value["prompt_sha"]["engineer"] == engineer.ENGINEER_PROMPT_SINGLE_ZPC_V25_SHA256
    assert value["prompt_sha"]["v2"]["engineer"] == engineer.ENGINEER_PROMPT_ZPC_V25_SHA256
    assert value["prompt_sha"] != manifest.prompt_sha(p.ZEBRA_PC_V2)
    setting = manifest.setting_of(value, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert p.configuration_of(setting) == CONFIG and p.namespace_of(setting, "D") == "D-zpc3"
    assert set(setting.pools) == set(setting.cards) == set(setting.runtime) == {z.BENCH}
    services = manifest.services_of(value, "D", setting=setting, transport=NO_CALLS)
    assert services.sources is services.engine is services.checker is None
    assert smoke.engineer_request_floor(CONFIG) == p.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
        engineer.ENGINEER_SYSTEM_ZPC_V25, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V25, engineer.ANALYST_SYSTEM))


def test_v3_preparation_requires_its_own_s0_and_smoke_result(tmp_path, monkeypatch):
    listing = "authored v25 snapshot fixture\n"
    sha = hashlib.sha256(listing.encode()).hexdigest()
    monkeypatch.setattr(zebra_smoke.prelaunch, "sha256_list", lambda root: listing)
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "a" * 64})
    provenance = tmp_path / "provenance.json"
    write_json(provenance, {"build_tree": str(tmp_path / "source"), "git_head": "f" * 40,
        "snapshot_root": str(manifest.REPO), "sha256_list_sha256": sha, "env_files_absent": True})
    fields = {"passed": True, "configuration": p.ZEBRA_PC_V2, "registration": z.identity(),
        "snapshot_root": str(manifest.REPO), "snapshot_sha256": sha,
        "pool": {"path": z.POOL_PATH, "sha256": z.POOL_SHA256},
        "split_manifest": {"path": z.SPLIT_MANIFEST_PATH, "sha256": "b" * 64, "field": "output_sha256"},
        "measured": MEASURED, "limits": {k: asdict(v) for k, v in client.LIMITS.items()}}
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
    smoke_result = tmp_path / "smoke-result.json"
    result = {"passed": True, "configuration": p.ZEBRA_PC_V2, "chain": "D", "s0": checked[p.RECORD_HASH],
        "snapshot_sha256": sha, "manifest_path": str(smoke_path), "manifest": prepared[p.RECORD_HASH],
        "read_estimate": 1000}
    write_json(smoke_result, p.record("zebra-smoke-result", "smoke", result))
    with pytest.raises(ValueError, match="passed measured zebra smoke"):
        zebra_smoke.make_manifest(tmp_path / "never.json", root=p.RUN_ROOTS[CONFIG],
                                 smoke_results=[smoke_result], **args)
    result["configuration"] = CONFIG
    smoke_result.write_text(json.dumps(p.record("zebra-smoke-result", "smoke", result)))
    value = zebra_smoke.make_manifest(tmp_path / "real.json", root=p.RUN_ROOTS[CONFIG],
                                     smoke_results=[smoke_result], **args)
    assert value["configuration"] == CONFIG and value["evidence"] == "zebra_pc_v3_real_run"
    assert value["data"]["launchable_chains"] == ["D"]
    assert value["data"]["zebra_pc"] == prepared["data"]["zebra_pc"] == z.identity()
    assert value["root"] == p.ZEBRA_PC_V3_ROOT


def test_v3_canaries_are_consent_gated_and_cannot_reuse_v2_records(tmp_path, monkeypatch):
    value = v25_manifest(tmp_path, monkeypatch)
    root, accesses = Path(value["root"]), []
    tasks = [z.normalize({**row(index=i), "puzzle": row(index=i)["puzzle"]
                          + "A distinct authored v3 panel canary %d." % i}, partition="test") for i in range(6)]
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
        evaluation.load_canaries(root, read=True, configuration=p.ZEBRA_PC_V2)


@pytest.mark.parametrize("name,args", [
    ("snapshot", ["--out", "out", "--git-head", "f" * 40]), ("s0", ["--out", "out"]),
    ("manifest", ["--out", "out", "--root", "root", "--s0", "s0", "--provenance", "prov",
                  "--roles-repo", "roles", "--elucid-env", "env", "--route-b-env", "route"]),
    ("smoke", ["--manifest", "m", "--chain", "D", "--stage", "S1"]),
])
def test_all_zpc_cli_commands_accept_v3_and_keep_v1_default(name, args):
    from scripts.run_execskill import parser
    assert parser().parse_args(["zpc-" + name, *args]).configuration == p.ZEBRA_PC_V1
    assert parser().parse_args(["zpc-" + name, *args, "--configuration", CONFIG]).configuration == CONFIG


@pytest.mark.parametrize("chain", ["G", "D"])
def test_smoke_projection_changes_only_configuration_label(chain):
    s2 = {"tokens_per_cell": 5300, "items": 10, "settled_tokens": 53000,
          "measurements": {"actual": 53000, "request_bytes": {z.BENCH: 1000}}}
    before = zebra_smoke.projection(s2, chain, p.ZEBRA_PC_V2)
    assert zebra_smoke.projection(s2, chain, CONFIG) == {**before, "configuration": CONFIG}
