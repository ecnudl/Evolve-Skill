"""Frozen Zebra v4 bytes captured from /tmp/alf-v1-before, before ALF v1 changes.

Authored fixtures exercise real proposal/fix flows, including C5b and C6. Only
ambient build pins and temporary manifest paths are normalized. Historical
legacy/v1/v2/v3 fingerprints remain in their existing test modules unchanged.
"""
from contextlib import contextmanager
from copy import deepcopy

import pytest

from tests.test_execskill_zpc_regression import FEATURES, byte_sha
from tests.test_execskill_zpc_pipeline import offline


def zebra_v4_snapshot(root, monkeypatch):
    root = root.resolve()
    from skillopt.execskill import budgets, engineer, manifest, policy, profiles as p, protocol, zebralogic as z
    from skillopt.execskill.package import Procedure
    from skillopt.execskill.sandbox import client
    from tests.test_execskill_manifest import MEASURED, fake_environment
    from tests.test_execskill_v24_engineer import GOOD, change
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v25_engineer import TABLE, matches, replies, shown_context
    from tests.test_execskill_zpc_orchestration import made

    name = p.ZEBRA_PC_V4
    prompts = {key: getattr(engineer, key) for key in (
        "ENGINEER_SYSTEM_ZPC_V26", "ENGINEER_SYSTEM_SINGLE_ZPC_V26",
        "ENGINEER_PROMPT_ZPC_V26_SHA256", "ENGINEER_PROMPT_SINGLE_ZPC_V26_SHA256",
        "RENDER_SAMPLE_FIELDS_V25", "RENDER_SAMPLE_HEADER_V25", "RENDER_SAMPLE_V25")}
    records = {}
    for mode in ("train", "single"):
        ctx, _ = shown_context(configuration=name, mode=mode)
        incorrect = change(ctx, TABLE, tests=[matches(ctx)])
        corrected = change(ctx, TABLE, tests=[matches(ctx, good=True)])
        ctx.roles = WireRoles(replies(ctx, incorrect, corrected))
        package, result = (engineer.run_train if mode == "train" else engineer.run)(ctx)
        assert package is not None
        assert [attempt["failed"] for attempt in result["changes"][0]["attempts"]] == ["C5b", None]
        records["c5b_" + mode] = {"package": package.to_json(), "record": result,
                                 "requests": ctx.roles.seen, "wire": ctx.roles.wire}

    # The second existing C6 worker returns another authored value. No randomness,
    # new worker kind, subprocess or model is needed to freeze mismatch feedback.
    ctx, workers = shown_context(configuration=name)
    mismatch_source = GOOD + "\n# Authored deterministic worker-order fixture.\n"
    @contextmanager
    def by_seed(package, *, kind="cell", hashseed=0, inputs_dir=None):
        with workers(package, kind=kind, hashseed=hashseed, inputs_dir=inputs_dir) as worker:
            for procedure in package.procedures:
                if procedure.source == mismatch_source and hashseed == 1:
                    worker.hooks[procedure.id]["before_call"] = lambda view, state: {
                        "facts": ["The second authored replay returns a different public note."]}
            yield worker
    ctx.workers = by_seed
    ctx.roles = WireRoles(replies(ctx, change(ctx, mismatch_source), change(ctx, GOOD)))
    package, result = engineer.run_train(ctx)
    assert package is not None
    assert [attempt["failed"] for attempt in result["changes"][0]["attempts"]] == ["C6", None]
    failed = next(check["detail"] for check in result["changes"][0]["attempts"][0]["checks"]
                  if check["check"] == "C6")
    assert failed["fault_count"] == 0 and failed["mismatched"]
    assert isinstance(failed["mismatched_task_ids"], list) and failed["mismatched_total"] == 1
    assert failed["mismatch_example"]["hook"] == "before_call"
    records["c6_mismatch"] = {"package": package.to_json(), "record": result,
                              "requests": ctx.roles.seen, "wire": ctx.roles.wire}

    ctx, _ = shown_context(configuration=name)
    candidate = change(ctx, GOOD)
    engineer._build(candidate, ctx)
    proc = candidate.procedure.to_json()
    assert Procedure.from_json(proc) == candidate.procedure
    records["procedure"] = proc
    records["kinds"] = {kind: protocol.record(kind + "-v2-6", "zebra_pc_v4_real_run", {"synthetic": True})
                        for kind in ("engineer", "procedure", "manifest")}
    registration = manifest._plain({
        "features": {key: getattr(p, key).get(name, {"unregistered": True}) for key in FEATURES},
        "family": p.FEATURE_FAMILIES[name], "namespaces": p.CHAIN_NAMESPACES[name],
        "manifest_path": p.ZEBRA_PC_V4_MANIFEST, "registered": manifest.registered(name),
        "prompts": manifest.prompt_sha(name), "roles": manifest.role_settings(name),
        "zebra_features": manifest.zebra_features(name), "data": z.identity(),
        "budgets": {chain: budgets.chain_caps(chain, name) for chain in p.CHAINS}})

    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored-fixture.py": "a" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored-fixture.py"})
    monkeypatch.setattr(client, "worker_sha256", lambda: "b" * 64)
    old = made(root, monkeypatch)
    given = {key: deepcopy(old[key]) for key in manifest.GIVEN}
    environment = fake_environment()
    environment.update(python="3.11.13", openpyxl="3.1.5")
    full = manifest.make(root / "v4-frozen.json", evidence="engineering_fixture", configuration=name,
                         environment_found=environment, measured=MEASURED, **given)

    def normalized(value):
        if isinstance(value, dict):
            return {key: normalized(child) for key, child in value.items() if key != p.RECORD_HASH}
        if isinstance(value, list):
            return [normalized(child) for child in value]
        return value.replace(str(root.resolve()), "<fixture-root>") if isinstance(value, str) else value

    return {"prompts": prompts, "policy": {"raw": policy.POLICY_PATH_V25.read_text(),
                "sha256": policy.policy_sha256(version=policy.POLICY_VERSION_V25)},
            "records_and_requests": records, "registration": registration,
            "manifest_identity": normalized(full)}


# Captured by running this exact helper on the untouched pre-ALF-v1 snapshot before comparisons.
ZEBRA_V4_SHA256 = {
    "prompts": "a96d21903728616ea0f461cca13fd1a7b770d34d794a1948a5299e85182daf93",
    "policy": "b0644d9d5771eb2f129278e2f92810515495616ea1f9801b4ff605ba7992093e",
    "records_and_requests": "336e796f04805e62913e0ee399b0ecd1f1cc9fdad4ed104a512f617117837e37",
    "registration": "c2c8af2f6bcd8f51b82a700dbd81848621f24874e1a6950517718ee2c998bd8f",
    "manifest_identity": "37cdb8d292c0a7c4ffdb56673f21c4d6ba2c61679bd77a621cec098ce488ed43",
}


@pytest.fixture(scope="module")
def zebra_v4_bytes(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        snapshot = zebra_v4_snapshot(tmp_path_factory.mktemp("zpc-v4-frozen"), patch)
    return {key: byte_sha(value) for key, value in snapshot.items()}


@pytest.mark.parametrize("name", tuple(ZEBRA_V4_SHA256))
def test_zebra_v4_keeps_its_pre_alf_v1_bytes(name, zebra_v4_bytes):
    assert zebra_v4_bytes[name] == ZEBRA_V4_SHA256[name]
