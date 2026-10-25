"""v2.4 profile/policy registration and real in-process sandbox loader; no container or external calls."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import budgets, policy, profiles as p, protocol, zebralogic as z
from skillopt.execskill.package import Package, Procedure
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.sandbox import client, worker
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_adapter import pool_rows
from tests.test_execskill_zpc_profile import SOURCE, procedure

V24 = policy.POLICY_VERSION_V24


def padded_source(size):
    return SOURCE + "#" + "x" * (size - len(SOURCE.encode()) - 2) + "\n"


def test_feature_families_are_explicit_and_v24_includes_every_v23_feature():
    assert p.is_zebra(p.ZEBRA_PC_V1) and p.is_zebra(p.ZEBRA_PC_V2)
    assert not p.is_zebra(None) and not p.is_v23(None) and not p.is_v24(None)
    assert p.is_v23(p.ZEBRA_PC_V1) and p.is_v23(p.MAIN_V2_3) and p.is_v23(p.ZEBRA_PC_V2)
    assert p.is_v24(p.ZEBRA_PC_V2) and not p.is_v24(p.ZEBRA_PC_V1) and not p.is_v24(p.MAIN_V2_3)
    assert p.FEATURE_FAMILIES[p.ZEBRA_PC_V2] == "v2.4"
    for fn in (p.is_zebra, p.is_v23, p.is_v24):
        with pytest.raises(ValueError, match="Unknown run configuration"):
            fn("unregistered")
    for name in ("CONFIGURATIONS", "LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING",
                 "ACCEPT_RULES", "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
                 "IDENTICAL_REQUEST_REUSE", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS", "CONFIG_STEP_CAPS",
                 "CONFIG_SCHEDULE_CELLS", "CONFIG_ROLE_CAPS", "CONFIG_GLM_CAP", "CONFIG_CAP_FACTOR", "STAGE_READ",
                 "COST_CHECK_PAUSES", "TEST_READ_CELLS"):
        assert getattr(p, name)[p.ZEBRA_PC_V2] == getattr(p, name)[p.ZEBRA_PC_V1], name
    assert p.ENGINEER_RECORDS[p.ZEBRA_PC_V2] == "engineer-v2-4"
    assert p.POLICY_VERSIONS[p.ZEBRA_PC_V2] == V24
    assert p.POLICY_VERSIONS[p.ZEBRA_PC_V1] == policy.POLICY_VERSION_V23
    assert p.CONFIGURATIONS[p.ZEBRA_PC_V2] is not p.CONFIGURATIONS[p.ZEBRA_PC_V1]
    assert p.ACCEPT_RULES[p.ZEBRA_PC_V2] is not p.ACCEPT_RULES[p.ZEBRA_PC_V1]


def test_v2_registration_changes_identity_and_freshness_but_keeps_slices_and_budgets():
    name = p.ZEBRA_PC_V2
    assert p.RUN_ROOTS[name] == p.ZEBRA_PC_V2_ROOT == "/data/execskill-20261025-zebra-pc-v2"
    assert p.ZEBRA_PC_V2_MANIFEST == p.RUN_ROOTS[name] + "-manifest.json"
    assert p.REAL_RUN_EVIDENCE[name] == "zebra_pc_v2_real_run"
    assert p.REAL_RUN_EVIDENCE[name] in protocol.EVIDENCE
    assert p.CHAIN_NAMESPACES[name] == {"G": "G-zpc2", "D": "D-zpc2"}
    assert p.ACCEPT_FRESHNESS[name] == "zebra_split_v1_slices_reused_zpc1_acceptance_unused"
    assert p.active_benches(name) == p.read_benches(name) == (z.BENCH,)
    assert p.stage_arms_max(name) == 0 and p.read_arms_of(name) == p.TEST_ARMS
    for chain in p.CHAINS:
        setting = SimpleNamespace(extra={"configuration": name})
        assert p.namespace_of(setting, chain) == chain + "-zpc2"
        assert budgets.chain_caps(chain, name) == budgets.chain_caps(chain, p.ZEBRA_PC_V1)
    assert p.read_estimate_terms({z.BENCH: {"card": 5300}}, 1, name) == {z.BENCH: 7844000}
    assert p.fired_share(z.BENCH, name) == 1
    pool = [z.normalize(item) for item in pool_rows()]
    # Configuration never participates in the adapter's registered split seed or item identity.
    from skillopt.execskill import step
    cuts = []
    for configuration in (p.ZEBRA_PC_V1, name):
        setting = SimpleNamespace(extra={"configuration": configuration}, pools={z.BENCH: pool})
        cuts.append(step._cut(SimpleNamespace(setting=setting, bench=z.BENCH), frozenset()))
    assert cuts[0] == cuts[1]
    assert {key: [item["task_id"] for item in value] for key, value in cuts[0].items()} == {
        key: [item["task_id"] for item in value] for key, value in z.slices(pool).items() if key in cuts[0]}
    assert p.SLICES[p.CONFIGURATIONS[name]["order"][0]] == p.SLICES[p.CONFIGURATIONS[p.ZEBRA_PC_V1]["order"][0]]


@pytest.mark.parametrize("size", [6000, 6001, 9999, 10000, 10001])
def test_policy_byte_boundary_is_selected_by_version(size):
    source = padded_source(size)
    assert len(source.encode()) == size
    assert bool(policy.check(source, version=V24)) is (size > 10000)
    for old in (policy.POLICY_VERSION, policy.POLICY_VERSION_V23):
        assert bool(policy.check(source, version=old)) is (size > 6000)
    assert policy.MAX_SOURCE_BYTES == protocol.MAX_PROCEDURE_BYTES == 6000
    assert policy.source_limit(V24) == 10000 and policy.source_limit() == 6000


def test_v24_policy_retains_v23_rules_and_immutable_canonical_files(tmp_path):
    assert {k: v for k, v in policy.POLICY_V24.items() if k not in ("version", "registration", "max_source_bytes")} == {
        k: v for k, v in policy.POLICY_V23.items() if k not in ("version", "registration", "max_source_bytes")}
    for version, path in ((policy.POLICY_VERSION, policy.POLICY_PATH),
                          (policy.POLICY_VERSION_V23, policy.POLICY_PATH_V23), (V24, policy.POLICY_PATH_V24)):
        raw = path.read_bytes()
        assert json.loads(raw) == policy.POLICIES[version]
        assert hashlib.sha256(raw).hexdigest() == policy.policy_sha256(version=version)
        copy = tmp_path / path.name
        policy.write_policy_json(copy, version=version)
        assert copy.read_bytes() == raw
    assert policy.policy_sha256(version=V24) == "a0290490d63820e5f00ff7f09fe5da1e24070230ff1611faf31b80ba516510ca"
    assert policy.check("import re\nRX = re.compile('x')\n" + SOURCE, version=V24) == []
    assert policy.check("import os\n" + SOURCE, version=V24)
    assert policy.check("A = '" + "x" * 2001 + "'\n" + SOURCE, version=V24)
    with pytest.raises(ValueError, match="Unknown policy version"):
        policy.source_limit("unregistered")
    # UTF-8 bytes, not characters: replacing ASCII with a two-byte code point crosses the limit.
    source = padded_source(10000).replace("xxx", "ééé", 1)
    assert len(source) == 10000 and policy.check(source, version=V24)[0].rule == "size"


def test_v24_procedure_roundtrip_stamps_and_total_package_cap_stay_explicit():
    old = procedure(z.BENCH, p.BENCHES)
    modern = replace(old, source=padded_source(10000), policy_version=V24)
    sealed = modern.to_json()
    assert sealed["version"] == protocol.kind("procedure-v2-4")
    assert Procedure.from_json(sealed) == modern
    assert protocol.verified(sealed, "procedure") == sealed
    with pytest.raises(PackageInvalid, match="Policy violations"):
        replace(old, source=padded_source(6001))
    six = tuple(replace(modern, id="p-zebralogic-1-%d" % n) for n in range(1, 7))
    assert len(Package(six, "s1", modern.evidence).procedures) == 6
    with pytest.raises(PackageInvalid, match="64,000|64000|64k|sources"):
        Package(six + (replace(modern, id="p-zebralogic-1-7"),), "s1", modern.evidence)
    for name in ("engineer", "manifest"):
        value = protocol.record(name + "-v2-4", "zebra_pc_v2_real_run", {})
        assert protocol.verified(value, name) == value
    with pytest.raises(ValueError, match="another kind"):
        protocol.verified(protocol.record("decision-v2-4", "zebra_pc_v2_real_run", {}), "decision")


def test_v24_sandbox_handshake_and_loader_preserve_each_procedures_policy(monkeypatch):
    old = procedure(z.BENCH, p.BENCHES)
    modern = replace(old, id="p-zebralogic-1-2", source=padded_source(10000), policy_version=V24)
    package = Package((old, modern), "s1", old.evidence)
    host = client.Worker()
    host.package, host.kind, host._entries = package, "cell", client._entries(package)
    requests = []
    def exchange(request, timeout):
        requests.append(request)
        if request["op"] == "ping":
            return {"ok": True, "worker": client.WORKER_PROTOCOL, "worker_sha256": client.worker_sha256(),
                    "hashseed": "0", "policy_sha256": policy.policy_sha256()}
        return worker.handle_load({"seq": 1, **request}, {"loaded": None}, policy)
    monkeypatch.setattr(host, "_exchange", exchange)
    host._handshake()
    assert not host.rejected
    request = requests[-1]
    assert request["policy_version"] == V24 and request["policy_sha256"] == policy.policy_sha256(version=V24)
    # The v24 envelope cannot promote a v23 entry to its larger cap.
    request["procedures"][0]["source"] = padded_source(6001)
    result = worker.handle_load({"seq": 1, **request}, {"loaded": None}, policy)
    assert result["loaded"] == [modern.id]
    assert result["rejected"] == [{"id": old.id, "reason": "policy:size"}]
    request["policy_version"] = policy.POLICY_VERSION_V23
    request["policy_sha256"] = policy.policy_sha256(version=policy.POLICY_VERSION_V23)
    assert not worker.handle_load({"seq": 1, **request}, {"loaded": None}, policy)["ok"]
