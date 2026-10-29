"""Manifest/S0 paths with the real frozen instruction cards and authored unopened data pins."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (evaluation, exclusion, instruction_start, manifest, prelaunch,
                               profiles as p, protocol, routes, v210_import, v210_smoke as v)
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401
from tests.test_execskill_manifest import given, fake_environment, MEASURED, tree

CONFIGS = (p.BASELINE_V210, p.MAIN_V3)


def consent(root, configuration):
    value = {"by": "owner", "date": "2026-10-29", "note": "Authored consent for local tests",
             "test_evaluation": True, "sheet_test_qualification": True,
             "multi_arm_arms": list(p.read_arms_of(configuration))}
    write_json(root / "shared/consent.json", value)
    return value


def preparation(root, monkeypatch):
    root.mkdir(parents=True, exist_ok=True)
    args = given(root)
    args["cards"] = {bench: row["text"] for bench, row in instruction_start.pins().items()}
    records = {
        exclusion.SEARCHQA_RUN: p.record(exclusion.RECORD_KIND, "engineering_fixture", {
            "run": exclusion.SEARCHQA_RUN, "dropped": [], "exclusion_sha256": digest([]), "consent_sha256": "a" * 64}),
        exclusion.ALFWORLD_RUN: p.record(exclusion.RECORD_KIND, "engineering_fixture", {
            "run": exclusion.ALFWORLD_RUN, "disjoint": True, "consent_sha256": "a" * 64}),
        "test_canaries": p.record("test-canaries", "engineering_fixture", {
            "consent_sha256": "a" * 64, "canaries": {}})}
    exclusions = {}
    for name, value in records.items():
        path = root / (name + ".json")
        write_json(path, value)
        exclusions[name] = {"path": str(path), "record_sha256": value[p.RECORD_HASH]}
    split = str(root / "unopened-split.json")
    tests = {bench: str(root / (bench + "-unopened-test.json")) for bench in p.BENCHES}
    args["data"] = {"pools": {bench: {"path": str(root / (bench + "-unopened-pool.json")),
                                    "sha256": "b" * 64} for bench in p.BENCHES},
        "pinned": {"paths": {"split": split, "test": tests},
                   "sha256": {path: "c" * 64 for path in (split, *tests.values())}},
        "exclusion": exclusions, "searchqa_tail": {"path": str(root / "unopened-tail.json"), "sha256": "d" * 64}}
    args["clients"]["solver"] = {c: manifest.solver_block(c, env_path=b["env_path"], branch=b["branch"],
        configuration=p.MAIN_V2_2) for c, b in args["clients"]["solver"].items()}
    args["clients"]["routes"] = {"D": {"B": routes.pin("D", "B", env_path=root / "route.env",
        solver_block=args["clients"]["solver"]["D"], configuration=p.MAIN_V2_2)}}
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "e" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored.py"})
    path = root / "preparation.json"
    value = manifest.make(path, evidence="engineering_fixture", configuration=p.MAIN_V2_2,
                          environment_found=fake_environment(), measured=MEASURED, **args)
    return path, value, records


def setup(root, monkeypatch, configuration):
    source, old, records = preparation(root / "source", monkeypatch)
    snapshot = tree(root / "snapshot")
    monkeypatch.setattr(manifest, "REPO", snapshot)
    run = root / "run"
    consent(run, configuration)
    selftest = None
    if configuration == p.MAIN_V3:
        selftest = root / "sandbox-selftest.json"
        write_json(selftest, p.record("sandbox-selftest", "smoke", {"passed": True,
            "measured": MEASURED, "limits": {k: asdict(l) for k, l in sandbox.LIMITS.items()}}))
    checked = v.collect_s0(root / "s0", preparation_file=source, root=run, configuration=configuration,
        snapshot_root=snapshot, selftest=selftest, checks={"passed": True, "summary": "authored checks"})
    provenance = root / "provenance.json"
    write_json(provenance, {"build_tree": str(snapshot), "git_head": "f" * 40,
        "snapshot_root": str(snapshot), "sha256_list_sha256": checked["snapshot_sha256"], "env_files_absent": True})
    options = {"root": run, "s0_file": root / "s0" / v.S0_FILE, "provenance": provenance,
        "roles_repo": root / "roles", "route_b_env": root / "route.env", "configuration": configuration,
        "smoke_chain": "D", "environment_found": fake_environment() if configuration == p.MAIN_V3 else None}
    return checked, options, old, records


def reseal(value):
    return p.record("manifest-v2-3", value["evidence"], {
        k: v for k, v in value.items() if k not in ("version", "evidence", p.RECORD_HASH)})


@pytest.mark.parametrize("configuration", CONFIGS)
def test_s0_imports_supply_exclusion_and_instruction_pins_without_opening_panels(tmp_path, monkeypatch, configuration):
    checked, _, old, records = setup(tmp_path, monkeypatch, configuration)
    assert checked["instructions"] == instruction_start.pins()
    assert checked["cards"] == old["cards"]
    assert checked["active_cards"] == checked["cards"] == {b: e["text"] for b, e in instruction_start.pins().items()}
    assert checked["instruction_start"] == "historical_card_is_the_instruction"
    assert checked["blank_arm"] == {"card": "", "kind": "blank"}
    assert checked["data"]["pools"] == old["data"]["pools"]
    assert checked["exclusion_records"] == records
    assert checked["sealed_reads"] == 0 and checked["passed"]
    assert checked["sandbox_required"] == (configuration == p.MAIN_V3)
    if configuration == p.BASELINE_V210:
        assert checked["training_units"] == [] and checked["sandbox"] is None
        assert all(value is None for value in checked["measured"].values())
    else:
        assert checked["alfworld_v11_import"] == v210_import.pins()
    assert not list(tmp_path.rglob("*-unopened-*.json"))


@pytest.mark.parametrize("configuration", CONFIGS)
def test_manifest_build_pins_cards_and_source_and_routes_both_chains(tmp_path, monkeypatch, configuration):
    checked, options, old, records = setup(tmp_path, monkeypatch, configuration)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    assert made["data"]["instructions"] == checked["instructions"]
    assert made["cards"] == checked["active_cards"]
    assert made["data"]["original_cards"] == old["cards"]
    assert made["data"]["instruction_start"] == checked["instruction_start"]
    assert made["data"]["blank_arm"] == checked["blank_arm"] == {"card": "", "kind": "blank"}
    assert made["data"]["card_sha256"] == {b: e["sha256"] for b, e in instruction_start.pins().items()}
    for name, pin in made["data"]["exclusion"].items():
        assert read_json(pin["path"]) == records[name]
        assert str(options["root"]) in pin["path"]
    assert set(made["clients"]["solver"]) == {"G", "D"}
    assert made["clients"]["solver"]["D"]["backend"] == "northgate"
    assert manifest.solver_config(made, "D", "officeqa")["route"] == "B"
    assert made["data"]["readiness"]["measured"] is False
    if configuration == p.BASELINE_V210:
        assert made["environment"]["docker"] == "not-required-no-procedures"
        assert made["sandbox"]["image_id"] is None
        assert all(value is None for value in made["sandbox"]["measured"].values())
    assert manifest.check(made) == made


@pytest.mark.parametrize("configuration", CONFIGS)
@pytest.mark.parametrize("change", ["instruction_text", "instruction_hash", "card", "card_hash", "prompt",
                                    "instruction_start", "blank_card", "blank_kind", "blank_extra"])
def test_manifest_refuses_resealed_pin_drift(tmp_path, monkeypatch, configuration, change):
    _, options, _, _ = setup(tmp_path, monkeypatch, configuration)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    if change == "instruction_text":
        made["data"]["instructions"]["searchqa"]["text"] += "different"
    elif change == "instruction_hash":
        made["data"]["instructions"]["searchqa"]["sha256"] = "0" * 64
    elif change == "card":
        made["cards"]["searchqa"] += "different"
    elif change == "card_hash":
        made["data"]["card_sha256"]["searchqa"] = "0" * 64
    elif change == "prompt":
        made["prompt_sha"]["engineer"] = "0" * 64
    elif change == "instruction_start":
        made["data"]["instruction_start"] = "append_instruction"
    elif change == "blank_card":
        made["data"]["blank_arm"]["card"] = "Public task card"
    elif change == "blank_kind":
        made["data"]["blank_arm"]["kind"] = "card"
    else:
        made["data"]["blank_arm"]["extra"] = True
    with pytest.raises(ValueError, match="[Ii]nstruction|card|prompt|blank"):
        manifest.check(reseal(made))


@pytest.mark.parametrize("configuration", CONFIGS)
@pytest.mark.parametrize("change", ["instruction_start", "blank_card", "blank_kind", "card_hash", "active_card"])
def test_manifest_preparation_refuses_resealed_s0_definition_drift(tmp_path, monkeypatch, configuration, change):
    checked, options, _, _ = setup(tmp_path, monkeypatch, configuration)
    if change == "instruction_start":
        checked["instruction_start"] = "concatenate"
    elif change == "blank_card":
        checked["blank_arm"]["card"] = checked["cards"]["searchqa"]
    elif change == "blank_kind":
        checked["blank_arm"]["kind"] = "card"
    elif change == "card_hash":
        checked["card_sha256"]["searchqa"] = "0" * 64
    else:
        checked["active_cards"]["searchqa"] += " changed"
    altered = tmp_path / "altered-s0.json"
    write_json(altered, p.record("v210-s0", checked["evidence"], {
        key: value for key, value in checked.items() if key not in ("version", "evidence", p.RECORD_HASH)}))
    options["s0_file"] = altered
    out = tmp_path / "must-not-exist.json"
    with pytest.raises(ValueError, match="instruction|card|blank"):
        v.make_manifest(out, **options)
    assert not out.exists()


@pytest.mark.parametrize("configuration", CONFIGS)
def test_s0_refuses_wrong_arm_consent_before_preparation(tmp_path, monkeypatch, configuration):
    run = tmp_path / "run"
    consent(run, p.MAIN_V3 if configuration == p.BASELINE_V210 else p.BASELINE_V210)
    with pytest.raises(ValueError, match="consent"):
        v.collect_s0(tmp_path / "s0", preparation_file=tmp_path / "must-not-open.json", root=run,
                     configuration=configuration, checks={"passed": True})
    assert not (tmp_path / "s0").exists()


@pytest.mark.parametrize("configuration", CONFIGS)
def test_real_registered_card_identity_passes_s0_and_manifest_unchanged(tmp_path, monkeypatch, configuration):
    from scripts.run_execskill import CARD_IDENTITY
    checked, options, old, _ = setup(tmp_path, monkeypatch, configuration)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    for cards in (old["cards"], checked["cards"], checked["active_cards"], made["cards"]):
        assert {bench: (len(text), hashlib.sha256(text.encode()).hexdigest()[:8])
                for bench, text in cards.items()} == CARD_IDENTITY
        assert cards == old["cards"] == {b: e["text"] for b, e in instruction_start.pins().items()}


@pytest.mark.parametrize("configuration", CONFIGS)
@pytest.mark.parametrize("change", ["modified", "doubled", "public_task_card"])
def test_s0_refuses_nonhistorical_cards_before_checks_or_writes(tmp_path, monkeypatch, configuration, change):
    from skillopt.coevo5.texts import CARDS
    _, old, _ = preparation(tmp_path / "source", monkeypatch)
    old["cards"]["searchqa"] = (old["cards"]["searchqa"] + "changed" if change == "modified" else
                                old["cards"]["searchqa"] * 2 if change == "doubled" else CARDS["searchqa"])
    source = tmp_path / "invalid-card-preparation.json"
    write_json(source, reseal(old))
    run = tmp_path / "run"
    consent(run, configuration)
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid historical cards must be refused before prelaunch or sandbox work")
    monkeypatch.setattr(prelaunch, "zero_call_checks", forbidden)
    with pytest.raises(ValueError, match="[Ii]nstruction|historical"):
        v.collect_s0(tmp_path / "s0", preparation_file=source, root=run, configuration=configuration,
                     selftest=tmp_path / "must-not-open.json" if configuration == p.MAIN_V3 else None)
    assert not (tmp_path / "s0").exists()


@pytest.mark.parametrize("configuration", CONFIGS)
def test_resealed_manifest_cannot_silently_double_inherited_instructions(tmp_path, monkeypatch, configuration):
    _, options, _, _ = setup(tmp_path, monkeypatch, configuration)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    original = {bench: row["text"] for bench, row in instruction_start.pins().items()}
    made["data"]["original_cards"] = original
    made["data"]["card_sha256"] = {bench: hashlib.sha256(text.encode()).hexdigest()
                                    for bench, text in original.items()}
    made["cards"] = {bench: text + "\n\n" + text for bench, text in original.items()}
    with pytest.raises(ValueError, match="[Ii]nstruction|historical"):
        manifest.check(reseal(made))


def test_baseline_setting_and_verify_never_construct_or_inspect_docker_or_training_pools(tmp_path, monkeypatch):
    _, options, _, _ = setup(tmp_path, monkeypatch, p.BASELINE_V210)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    monkeypatch.setattr(manifest, "verify_code", lambda *a, **k: None)
    def forbidden(*a, **k):
        pytest.fail("Baseline touched a procedure sandbox or training pool")
    monkeypatch.setattr(sandbox, "Docker", forbidden)
    monkeypatch.setattr(manifest, "image_id", forbidden)
    monkeypatch.setattr(manifest, "_items", forbidden)
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))
    made["slot_root"] = str(tmp_path / "slots")
    manifest.verify_unit(made)
    setting = manifest.setting_of(made, "D")
    assert setting.pools == {} and setting.sandbox == {}
    assert setting.extra["drain"]() is None
    assert setting.extra["route"] == "B"
    assert setting.extra["blank_arm"] == {"card": "", "kind": "blank"}
    assert setting.cards == {b: e["text"] for b, e in instruction_start.pins().items()}
    assert "searchqa_tail" not in setting.extra


def test_main_import_drift_refused_by_manifest(tmp_path, monkeypatch):
    _, options, _, _ = setup(tmp_path, monkeypatch, p.MAIN_V3)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    made["data"]["alfworld_v11_import"]["procedures"][0]["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="imported ALFWorld"):
        manifest.check(reseal(made))


def test_real_baseline_manifest_needs_no_sandbox_or_measured_smoke(tmp_path, monkeypatch):
    _, options, _, _ = setup(tmp_path, monkeypatch, p.BASELINE_V210)
    monkeypatch.setitem(p.RUN_ROOTS, p.BASELINE_V210, str(options["root"]))
    options["smoke_chain"] = None
    def forbidden(*args, **kwargs):
        pytest.fail("Baseline must not inspect a sandbox or measured procedure smoke")
    monkeypatch.setattr(manifest, "environment", forbidden)
    monkeypatch.setattr(v.chain, "read_estimate_record", forbidden)
    value = v.make_manifest(tmp_path / "real-baseline.json", **options)
    assert value["evidence"] == p.REAL_RUN_EVIDENCE[p.BASELINE_V210]
    assert value["data"]["launchable_chains"] == ["G", "D"]
    assert all(item is None for item in value["sandbox"]["measured"].values())


def test_real_main_refuses_structural_only_readiness_then_binds_measured_terms(tmp_path, monkeypatch):
    _, options, _, _ = setup(tmp_path, monkeypatch, p.MAIN_V3)
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V3, str(options["root"]))
    options["smoke_chain"] = None
    output = tmp_path / "real-main.json"
    with pytest.raises(ValueError, match="measured smoke"):
        v.make_manifest(output, **options)
    assert not output.exists()
    measured = p.record("test-read-estimate", "smoke", {
        "terms": {bench: "1000/1" for bench in p.BENCHES}, "value": 5000})
    monkeypatch.setattr(v.chain, "read_estimate_record", lambda root, configuration: deepcopy(measured))
    value = v.make_manifest(output, measured_smoke=tmp_path / "authored-measured-smoke", **options)
    assert value["data"]["readiness"]["measured"] is True
    assert value["data"]["test_read_estimate"] == {"G": 5000, "D": 5000}
    assert value["evidence"] == p.REAL_RUN_EVIDENCE[p.MAIN_V3]


def test_main_setting_passes_only_registered_mixed_policy_bundle(tmp_path, monkeypatch):
    _, options, _, _ = setup(tmp_path, monkeypatch, p.MAIN_V3)
    made = v.make_manifest(tmp_path / "manifest.json", **options)
    made["slot_root"] = str(tmp_path / "slots")
    monkeypatch.setattr(manifest, "_pools", lambda *args: {})
    setting = manifest.setting_of(made, "D")
    assert setting.sandbox["mixed_policy_bundle"] == "main-v3-alfworld-v11"
    assert setting.extra["alfworld_v11_import"] == v210_import.pins()


@pytest.mark.parametrize("configuration", CONFIGS)
def test_structural_smoke_is_explicitly_zero_call_not_measured_readiness(tmp_path, monkeypatch, configuration):
    _, options, _, _ = setup(tmp_path, monkeypatch, configuration)
    path = tmp_path / "manifest.json"
    made = v.make_manifest(path, **options)
    monkeypatch.setattr(manifest, "verify_code", lambda value: None)
    found = v.structural_smoke(path, out=tmp_path / "smoke.json", configuration=configuration)
    assert found["manifest"] == made[p.RECORD_HASH]
    assert found["model_calls"] == found["sealed_reads"] == 0
    assert found["read_arms"] == list(p.read_arms_of(configuration))
    assert found["measured_readiness"] is False and found["passed"]
    assert found["evidence"] == "engineering_fixture"


def test_snapshot_carries_frozen_instruction_file_as_well_as_code_and_procedure_fixtures(tmp_path):
    source = tree(tmp_path / "source")
    target = source / "docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(instruction_start.FIXTURE.read_bytes())
    fixture = source / "tests/fixtures/execskill/authored.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}")
    copied = tmp_path / "snapshot"
    found = v.snapshot(copied, source=source, git_head="a" * 40, configuration=p.BASELINE_V210)
    assert found["env_files_absent"]
    assert (copied / target.relative_to(source)).read_bytes() == target.read_bytes()
    assert (copied / fixture.relative_to(source)).read_bytes() == fixture.read_bytes()


@pytest.mark.parametrize("name", ["snapshot", "s0", "manifest", "smoke"])
def test_cli_offers_both_new_configuration_choices(name):
    from scripts.run_execskill import parser, HANDLERS
    commands = parser()._subparsers._group_actions[0].choices
    action = next(a for a in commands["v210-" + name]._actions if a.dest == "configuration")
    assert set(action.choices) == set(CONFIGS) and action.required
    assert "v210-" + name in HANDLERS
