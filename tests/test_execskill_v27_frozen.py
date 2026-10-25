"""Frozen ALF v1 bytes captured from the untouched pre-v2.7 snapshot.

Authored offline fixtures execute real train/single proposal, reproposal, fix,
malformed-claim, advisory-lint and C6 mismatch paths. Only ambient build pins,
host environment versions, and temporary manifest paths are normalized. The
existing legacy and Zebra v1/v2/v3/v4 fingerprint modules remain unchanged.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from tests.test_execskill_zpc_regression import FEATURES, byte_sha
from tests.test_execskill_zpc_pipeline import offline


def alf_v1_snapshot(root, monkeypatch):
    root = root.resolve()
    from skillopt.execskill import budgets, engineer, manifest, policy, profiles as p, protocol
    from skillopt.execskill.package import Procedure
    from skillopt.execskill.sandbox import client
    from skillopt.validator_pilot.api import digest
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_alf_v1_profile import alf_manifest
    from tests.test_execskill_manifest import MEASURED, fake_environment
    from tests.test_execskill_v24_engineer import context, detail
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v24_routing_review import tracker_change
    from tests.test_execskill_v25_engineer import replies

    name = p.ALFWORLD_V1
    prompts = {key: getattr(engineer, key) for key in (
        "ENGINEER_SYSTEM_ALF_V1", "ENGINEER_SYSTEM_SINGLE_ALF_V1",
        "ENGINEER_PROMPT_ALF_V1_SHA256", "ENGINEER_PROMPT_SINGLE_ALF_V1_SHA256",
        "RENDER_SAMPLE_FIELDS_V25", "RENDER_SAMPLE_HEADER_V25", "RENDER_SAMPLE_V25")}

    def shown(mode="train"):
        ctx, workers = context(configuration=name, bench="alfworld", mode=mode)
        return (replace(ctx, current=list(ctx.trajectories)) if mode == "train" else ctx), workers

    def captured(ctx, package, record, *, allow_empty=False):
        assert allow_empty or package is not None
        for procedure in package.procedures if package is not None else ():
            assert Procedure.from_json(procedure.to_json()) == procedure
        return {"package": package.to_json() if package is not None else None, "record": record,
                "requests": ctx.roles.seen, "wire": ctx.roles.wire}

    records = {}
    for mode in ("train", "single"):
        ctx, _ = shown(mode)
        incorrect, corrected = tracker_change(ctx), tracker_change(ctx)
        incorrect.entry["replay_tests"][0]["property"]["value"] = "Authored absent note fragment"
        prefix = [engineer_reply({"findings": []}, [])] if mode == "train" else []
        ctx.roles = WireRoles(prefix + ["An authored malformed proposal"] + [
            engineer_reply({"changes": [candidate.entry]}, [candidate.source])
            for candidate in (incorrect, corrected)])
        package, result = (engineer.run_train if mode == "train" else engineer.run)(ctx)
        assert [row["parsed"] for row in result["proposals"]] == [False, True]
        assert [row["failed"] for row in result["changes"][0]["attempts"]] == ["C5b", None]
        assert "rendered_note" in detail(result["changes"][0]["attempts"][0], "C5b")["failed"][0]
        records["proposal_reproposal_fix_" + mode] = captured(ctx, package, result)

    # The new v2.7 validation explanations must not alter ALF's existing failed
    # claim or persisted advisory feedback, even for the same malformed shapes.
    ctx, _ = shown()
    malformed, corrected = tracker_change(ctx), tracker_change(ctx)
    malformed.entry["replay_tests"][0]["property"] = {
        "kind": "note_matches", "value": ["authored"] * 10, "step": 1}
    ctx.roles = WireRoles(replies(ctx, malformed, corrected))
    package, result = engineer.run_train(ctx)
    assert [row["failed"] for row in result["changes"][0]["attempts"]] == ["C5b", None]
    failed = detail(result["changes"][0]["attempts"][0], "C5b")["failed"][0]
    assert failed["reason"] == "value"
    records["malformed_claim"] = captured(ctx, package, result)

    ctx, _ = shown()
    advisory = tracker_change(ctx)
    advisory.entry["replay_tests"][0].update(id="authored bad id", claims_fix=False)
    ctx.roles = WireRoles(replies(ctx, advisory))
    package, result = engineer.run_train(ctx)
    assert result["changes"][0]["attempts"][0]["passed"]
    assert any(row["reason"] == "invalid_test" for entry in result["lint"] for row in entry["problems"])
    records["advisory_lint"] = captured(ctx, package, result)
    resumed = replace(ctx, round=2, label="D/s1-alfworld/engineer-r2",
                      lint=json.loads(json.dumps(result["lint"])), roles=WireRoles())
    next_package, next_record = engineer.run_train(resumed)
    records["resumed_lint"] = captured(resumed, next_package, next_record, allow_empty=True)

    # Vary the existing second replay worker, keeping real ALF state progression
    # and all C6 diagnostics. There are no new worker kinds or hook executions.
    ctx, workers = shown()
    mismatching, corrected = tracker_change(ctx, claims=False), tracker_change(ctx)
    mismatching.source += "\n# Authored ALF worker-order mismatch fixture.\n"
    @contextmanager
    def by_seed(package, *, kind="cell", hashseed=0, inputs_dir=None):
        with workers(package, kind=kind, hashseed=hashseed, inputs_dir=inputs_dir) as worker:
            for procedure in package.procedures:
                if procedure.source == mismatching.source and hashseed == 1:
                    worker.hooks[procedure.id]["alf_before_step"] = lambda view, state: {
                        "fields": {"facts": ["The second authored replay returns a different public note."]},
                        "discourage": []}
            yield worker
    ctx.workers = by_seed
    ctx.roles = WireRoles(replies(ctx, mismatching, corrected))
    package, result = engineer.run_train(ctx)
    assert [row["failed"] for row in result["changes"][0]["attempts"]] == ["C6", None]
    mismatch = detail(result["changes"][0]["attempts"][0], "C6")
    assert mismatch["fault_count"] == 0 and mismatch["mismatched_total"] == 1
    assert mismatch["mismatched_task_ids"] == [ctx.trajectories[0]["task_id"]]
    assert mismatch["mismatch_example"]["hook"] == "alf_before_step"
    assert mismatch["mismatch_example"]["step"] == 0
    records["c6_mismatch"] = captured(ctx, package, result)

    ctx, _ = shown()
    candidate = tracker_change(ctx)
    engineer._build(candidate, ctx)
    records["procedure"] = candidate.procedure.to_json()
    records["kinds"] = {kind: protocol.record(stamp, "alfworld_v1_real_run", {"synthetic": True})
        for kind, stamp in (("engineer", "engineer-alf-v1"), ("manifest", "manifest-alf-v1"),
                            ("procedure", "procedure-v2-5"))}
    registration = manifest._plain({
        "features": {key: getattr(p, key).get(name, {"unregistered": True}) for key in FEATURES},
        "family": p.FEATURE_FAMILIES[name], "namespaces": p.CHAIN_NAMESPACES[name],
        "manifest_path": p.ALFWORLD_V1_MANIFEST, "registered": manifest.registered(name),
        "prompts": manifest.prompt_sha(name), "roles": manifest.role_settings(name),
        "alfworld_features": manifest.alfworld_features(name),
        "active_benches": p.active_benches(name), "read_benches": p.read_benches(name),
        "launchable_chains": p.launchable_chains(name), "stage_arms_max": p.stage_arms_max(name),
        "read_arms": p.read_arms_of(name),
        "budgets": {chain: budgets.chain_caps(chain, name) for chain in p.CHAINS}})

    monkeypatch.setattr(client, "worker_sha256", lambda: "b" * 64)
    old = alf_manifest(root, monkeypatch)
    given = {key: deepcopy(old[key]) for key in manifest.GIVEN}
    # This runtime is identity metadata only. A fixed authored path avoids a
    # temporary directory entering the registered runtime's own content hash.
    given["runtime"]["alfworld"]["alfworld_data"] = "/authored/alfworld-data"
    given["data"]["alfworld_v1"]["runtime_sha256"] = digest(given["runtime"]["alfworld"])
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored-fixture.py": "a" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored-fixture.py"})
    environment = fake_environment()
    environment.update(python="3.11.13", openpyxl="3.1.5")
    full = manifest.make(root / "alf-frozen.json", evidence="engineering_fixture", configuration=name,
                         environment_found=environment, measured=MEASURED, **given)

    def normalized(value):
        if isinstance(value, dict):
            return {normalized(key): normalized(child) for key, child in value.items() if key != p.RECORD_HASH}
        if isinstance(value, list):
            return [normalized(child) for child in value]
        return value.replace(str(root), "<fixture-root>") if isinstance(value, str) else value

    return {"prompts": prompts, "policy": {"raw": policy.POLICY_PATH_V25.read_text(),
                "sha256": policy.policy_sha256(version=policy.POLICY_VERSION_V25)},
            "records_and_requests": records, "registration": registration,
            "manifest_identity": normalized(full)}


# Captured by this helper on /tmp/zpc-v27-before before comparison to the writer tree.
ALF_V1_SHA256 = {
    "prompts": "8e93db1a77bf8a2476a3455332ed5ef781ca89dc663ed9c8f5a65a71e0ff1e40",
    "policy": "b0644d9d5771eb2f129278e2f92810515495616ea1f9801b4ff605ba7992093e",
    "records_and_requests": "761a6f32e30d4fc4fc738d5875b1b998d997117aa677e96f654ab9cf5c6e7e3e",
    "registration": "94f8224569cdae4c3e3519fc5bf254fc25dfb429b345701f7248dfd37ac83ef5",
    "manifest_identity": "90e7cff6995182e92c5f135b1f6d6d2201794f60e52e41041606810460f2d796",
}


@pytest.fixture(scope="module")
def alf_v1_bytes(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        snapshot = alf_v1_snapshot(tmp_path_factory.mktemp("alf-v1-frozen"), patch)
    return {key: byte_sha(value) for key, value in snapshot.items()}


@pytest.mark.parametrize("name", tuple(ALF_V1_SHA256))
def test_alf_v1_keeps_its_pre_v27_bytes(name, alf_v1_bytes):
    assert alf_v1_bytes[name] == ALF_V1_SHA256[name]
