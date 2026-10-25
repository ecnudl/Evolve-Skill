"""Frozen Zebra v2 bytes captured from /tmp/zpc-v25-before, before the v2.5 changes.

All inputs are authored fixtures. Ambient code/worker pins and temporary paths are
fixed for the manifest comparison; all configuration-dependent identity fields are real.
The thirteen pre-existing legacy/v1 groups remain in test_execskill_zpc_regression.py.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_regression import FEATURES, byte_sha


def zebra_v2_snapshot(root, monkeypatch):
    root = root.resolve()
    from skillopt.execskill import budgets, engineer, manifest, policy, profiles as p, protocol, zebralogic as z
    from skillopt.execskill.package import Procedure
    from skillopt.execskill.sandbox import client
    from tests.test_execskill_manifest import MEASURED, fake_environment
    from tests.test_execskill_v24_engineer import GOOD, change, context
    from tests.test_execskill_zpc_orchestration import made

    name = p.ZEBRA_PC_V2
    prompts = {key: getattr(engineer, key) for key in (
        "ENGINEER_SYSTEM_V24", "ENGINEER_SYSTEM_SINGLE_V24", "ENGINEER_SYSTEM_ZPC_V24",
        "ENGINEER_SYSTEM_SINGLE_ZPC_V24", "ENGINEER_PROMPT_V24_SHA256", "ENGINEER_PROMPT_SINGLE_V24_SHA256",
        "ENGINEER_PROMPT_ZPC_V24_SHA256", "ENGINEER_PROMPT_SINGLE_ZPC_V24_SHA256")}
    records = {}
    for mode in ("train", "single"):
        ctx, _ = context(configuration=name)
        if mode == "single":
            ctx = replace(ctx, mode=mode, round=0, base=None, label="D/s1-zebralogic/engineer")
        _, result = (engineer.run_train if mode == "train" else engineer.run)(ctx)
        records[mode] = {"record": result, "requests": ctx.roles.seen}
    ctx, _ = context(configuration=name)
    candidate = change(ctx, GOOD)
    engineer._build(candidate, ctx)
    proc = candidate.procedure.to_json()
    assert Procedure.from_json(proc) == candidate.procedure
    records["procedure"] = proc
    records["kinds"] = {kind: protocol.record(kind + "-v2-4", "zebra_pc_v2_real_run", {"synthetic": True})
                        for kind in ("engineer", "procedure", "manifest")}
    registration = manifest._plain({
        "features": {key: getattr(p, key).get(name, {"unregistered": True}) for key in FEATURES},
        "family": p.FEATURE_FAMILIES[name], "namespaces": p.CHAIN_NAMESPACES[name],
        "manifest_path": p.ZEBRA_PC_V2_MANIFEST, "registered": manifest.registered(name),
        "prompts": manifest.prompt_sha(name), "roles": manifest.role_settings(name),
        "zebra_features": manifest.zebra_features(name), "data": z.identity(),
        "budgets": {chain: budgets.chain_caps(chain, name) for chain in p.CHAINS}})

    # A complete manifest with constant ambient build/environment pins, so code
    # additions and a different test directory cannot hide identity regressions.
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored-fixture.py": "a" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored-fixture.py"})
    monkeypatch.setattr(client, "worker_sha256", lambda: "b" * 64)
    old = made(root, monkeypatch)
    given = {key: deepcopy(old[key]) for key in manifest.GIVEN}
    environment = fake_environment()
    environment.update(python="3.11.13", openpyxl="3.1.5")
    full = manifest.make(root / "v2-frozen.json", evidence="engineering_fixture", configuration=name,
                         environment_found=environment, measured=MEASURED, **given)

    def normalized(value):
        if isinstance(value, dict):
            return {key: normalized(child) for key, child in value.items() if key != p.RECORD_HASH}
        if isinstance(value, list):
            return [normalized(child) for child in value]
        return value.replace(str(root.resolve()), "<fixture-root>") if isinstance(value, str) else value

    return {"prompts": prompts, "policy": {"raw": policy.POLICY_PATH_V24.read_text(),
                "sha256": policy.policy_sha256(version=policy.POLICY_VERSION_V24)},
            "records_and_requests": records, "registration": registration,
            "manifest_identity": normalized(full)}


# Populated by running this exact helper against the untouched pre-v2.5 snapshot.
ZEBRA_V2_SHA256 = {
    "prompts": "338b2a12c7325c83085e9dc41f35507dca3ae327c0abd9b11a0f344f5422af45",
    "policy": "a5650a06a456ab072123a9ff815e17de6535fe2d985202c439841b09d1aaae1d",
    "records_and_requests": "8c45bacecd4d39ee95d10852e3ad9954c7e0aaf49a0c7ccf9b2bbf1c42525e1d",
    "registration": "0057ec51d050eaca834796ee67a9ec42708c0eb0219d6d685c6925db2812e21b",
    "manifest_identity": "24c4a418ed65f63bbb418c54e404bd78d83a439c61225ad9a1511cf13142b567",
}


@pytest.fixture(scope="module")
def zebra_v2_bytes(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        snapshot = zebra_v2_snapshot(tmp_path_factory.mktemp("zpc-v2-frozen"), patch)
    return {key: byte_sha(value) for key, value in snapshot.items()}


@pytest.mark.parametrize("name", tuple(ZEBRA_V2_SHA256))
def test_zebra_v2_keeps_its_pre_v25_bytes(name, zebra_v2_bytes):
    assert zebra_v2_bytes[name] == ZEBRA_V2_SHA256[name]
