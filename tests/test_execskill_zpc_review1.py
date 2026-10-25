"""Review regressions: trusted canary dispatch and the complete Zebra redo projection."""
import copy
import hashlib
import math
from dataclasses import asdict
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import evaluation, manifest, profiles as p, smoke, zebra_smoke, zebralogic as z
from skillopt.execskill.sandbox import client as sandbox
from tests.test_execskill_evaluation import consent_value, register_canaries, s0_canaries
from tests.test_execskill_manifest import MEASURED, fake_environment
from tests.test_execskill_zpc_readout import completed


def legacy_canaries(root):
    write_json(root / "shared" / "consent.json", consent_value())
    return register_canaries(root)


@pytest.mark.parametrize("configuration", (None, p.MAIN_V2_3))
def test_zebra_record_cannot_select_its_own_branch_in_a_historical_root(tmp_path, monkeypatch, configuration):
    root = tmp_path / "run"
    completed(root, "D")
    seen = []
    original = evaluation.read_json
    monkeypatch.setattr(evaluation, "read_json", lambda path: (seen.append(Path(path)), original(path))[1])
    with pytest.raises(ValueError, match="No registered test canaries"):
        evaluation.load_canaries(root, read=True, configuration=configuration)
    assert seen == []  # Historical S0 presence is checked before any read-canary record is opened.
    s0_canaries(root)
    with pytest.raises(ValueError, match="counted per bench"):
        evaluation.load_canaries(root, read=True, configuration=configuration)
    assert seen == [root / p.CANARIES, root / evaluation.READ_CANARIES]


def test_historical_record_is_refused_by_trusted_zebra_configuration(tmp_path):
    root = tmp_path / "run"
    legacy = legacy_canaries(root)
    assert evaluation.load_canaries(root, read=True, configuration=p.MAIN_V2_3)[-len(legacy["canaries"]):] == \
        legacy["canaries"]
    with pytest.raises(ValueError, match="trusted ZebraLogic"):
        evaluation.load_canaries(root, read=True, configuration=p.ZEBRA_PC_V1)
    # A spoofed label does not turn a legacy extension/panel set into an isolated Zebra record.
    fields = {k: v for k, v in legacy.items() if k not in ("version", "evidence", p.RECORD_HASH)}
    spoofed_root = tmp_path / "spoofed-root"
    write_json(spoofed_root / evaluation.READ_CANARIES, p.record("test-read-canaries", legacy["evidence"],
        {**fields, "configuration": p.ZEBRA_PC_V1}))
    with pytest.raises(ValueError, match="trusted ZebraLogic"):
        evaluation.load_canaries(spoofed_root, read=True, configuration=p.ZEBRA_PC_V1)


def test_historical_s0_cannot_admit_zebra_even_with_a_matching_legacy_extension(tmp_path, monkeypatch):
    source = tmp_path / "legacy-source"
    second = legacy_canaries(source)
    first = read_json(source / p.CANARIES)
    fields = lambda value: {k: v for k, v in value.items() if k not in ("version", "evidence", p.RECORD_HASH)}
    foreign = p.record("test-canaries", first["evidence"],
        {**fields(first), "counts": {p.ZEBRA: len(first["canaries"])}})
    root = tmp_path / "run"
    write_json(root / p.CANARIES, foreign)
    write_json(root / evaluation.READ_CANARIES, p.record("test-read-canaries", second["evidence"],
        {**fields(second), "extends": foreign[p.RECORD_HASH]}))
    seen, original = [], evaluation.read_json
    monkeypatch.setattr(evaluation, "read_json", lambda path: (seen.append(Path(path)), original(path))[1])
    with pytest.raises(ValueError, match="counted per bench"):
        evaluation.load_canaries(root, read=True, configuration=p.MAIN_V2_3)
    assert seen == [root / p.CANARIES]


@pytest.mark.parametrize("configuration", (p.MAIN_V2_3, p.ZEBRA_PC_V1))
def test_unseal_root_scan_uses_trusted_configuration_in_both_directions(tmp_path, configuration):
    root = tmp_path / "run"
    completed(root, "D")
    if configuration == p.ZEBRA_PC_V1:
        source = tmp_path / "legacy-source"
        legacy = legacy_canaries(source)
        (root / evaluation.READ_CANARIES).unlink()  # Simulate the wrong-profile record copied into this root.
        write_json(root / evaluation.READ_CANARIES, legacy)
    else:
        s0_canaries(root)
    with pytest.raises(ValueError, match="trusted ZebraLogic|counted per bench"):
        evaluation.unseal(root, root / "D", "D", [], run="synthetic-single-panel-read",
                          evidence="engineering_fixture", configuration=configuration)
    assert not (root / "D" / evaluation.UNSEALED).exists()
    assert not (root / "D" / evaluation.ROOT_SCAN / "attempt-1" / "scan.json").exists()


def test_make_canaries_cannot_use_zebra_order_to_override_historical_configuration(tmp_path):
    root = tmp_path / "run"
    completed(root, "D")
    write_json(root / "shared" / "consent.json", consent_value())
    with pytest.raises(ValueError, match="No registered test canaries"):
        evaluation.make_read_canaries(root, None, pools={}, run="synthetic-single-panel-read",
            evidence="engineering_fixture", order=(p.ZEBRA,), configuration=p.MAIN_V2_3,
            panel=lambda *a, **k: pytest.fail("Wrong-profile canaries must refuse before panel access"))


def test_split_manifest_rejects_reserved_path_before_stat_or_read(monkeypatch):
    touched = []
    def forbidden(path, *args, **kwargs):
        touched.append(str(path))
        pytest.fail("Reserved split-manifest path reached a stat/read")
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="reserved path"):
        zebra_smoke._split_pins("/data/zpc/SEALED-manifest.json")
    assert touched == []


def test_current_s0_constructs_smoke_and_real_manifest_with_official_registration(tmp_path, monkeypatch):
    listing = "authored snapshot fixture\n"
    snapshot_sha = hashlib.sha256(listing.encode()).hexdigest()
    monkeypatch.setattr(zebra_smoke.prelaunch, "sha256_list", lambda root: listing)
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "a" * 64})
    provenance = tmp_path / "provenance.json"
    write_json(provenance, {"build_tree": str(tmp_path / "source"), "git_head": "f" * 40,
        "snapshot_root": str(manifest.REPO), "sha256_list_sha256": snapshot_sha, "env_files_absent": True})
    s0_path = tmp_path / "s0.json"
    checked = p.record("zebra-s0", "smoke", {"passed": True, "registration": z.identity(),
        "snapshot_root": str(manifest.REPO), "snapshot_sha256": snapshot_sha,
        "pool": {"path": z.POOL_PATH, "sha256": z.POOL_SHA256},
        "split_manifest": {"path": z.SPLIT_MANIFEST_PATH, "sha256": "b" * 64, "field": "output_sha256"},
        "measured": MEASURED, "limits": {k: asdict(v) for k, v in sandbox.LIMITS.items()}})
    write_json(s0_path, checked)
    args = dict(s0_file=s0_path, provenance=provenance, roles_repo=tmp_path / "credentials",
                elucid_env=tmp_path / "elucid.env", route_b_env=tmp_path / "route-b.env",
                environment_found=fake_environment())
    smoke_path = tmp_path / "smoke-manifest.json"
    prepared = zebra_smoke.make_manifest(smoke_path, root=tmp_path / "smoke", smoke_chain="D", **args)
    assert prepared["data"]["zebra_pc"] == z.identity()
    assert prepared["cards"] == {p.ZEBRA: z.CARD_TEXT}
    assert prepared["contracts"] == {p.ZEBRA: {"text": "", "sha": hashlib.sha256(b"").hexdigest()}}
    assert z.CARD_VERSION in prepared["importable_versions"]
    smoke_result = tmp_path / "smoke-result.json"
    write_json(smoke_result, p.record("zebra-smoke-result", "smoke", {
        "passed": True, "configuration": p.ZEBRA_PC_V1, "chain": "D", "s0": checked[p.RECORD_HASH],
        "snapshot_sha256": snapshot_sha, "manifest_path": str(smoke_path),
        "manifest": prepared[p.RECORD_HASH], "read_estimate": 1000}))
    real = zebra_smoke.make_manifest(tmp_path / "real-manifest.json", root=p.ZEBRA_PC_ROOT,
                                    smoke_results=[smoke_result], **args)
    assert real["evidence"] == p.REAL_RUN_EVIDENCE[p.ZEBRA_PC_V1]
    assert real["data"]["launchable_chains"] == ["D"]
    assert real["data"]["zebra_pc"] == prepared["data"]["zebra_pc"]
    assert real["data"]["test_read_estimate"]["D"] == 1000


@pytest.mark.parametrize("chain", ("G", "D"))
def test_se6_prices_training_redo_maximum_and_preserves_historical_scopes(chain):
    historical = {configuration: copy.deepcopy(smoke._scope_cells(chain, configuration))
                  for configuration in p.legacy.CONFIGURATIONS}
    s2 = {"tokens_per_cell": 5300, "items": 10, "settled_tokens": 53000,
          "measurements": {"actual": 53000, "request_bytes": {p.ZEBRA: 1000}}}
    value = zebra_smoke.projection(s2, chain)
    scopes = zebra_smoke._scope_cells(chain)
    assert {p.ZEBRA: (0, 720)} in scopes[chain + ":redo"]
    assert {p.ZEBRA: (400, 2900)} in scopes[chain + ":solver"]
    proc = 5300 * 1.6
    bound = p.ledger_bound(p.CHAINS[chain], p.ZEBRA, branch="E" if chain == "D" else None)
    reserve = reservation(1000, bound)
    assert value["scopes"][chain + ":redo"]["projected"] == math.ceil(720 * proc + reserve)
    assert value["scopes"][chain + ":solver"]["projected"] == math.ceil(400 * 5300 + 2900 * proc + reserve)
    old_redo = 200 * 5300 + 400 * proc
    assert 720 * proc - old_redo == 1_653_600
    assert all(smoke._scope_cells(chain, configuration) == expected
               for configuration, expected in historical.items())
