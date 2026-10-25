"""ALF-only registration and manifest identities, using authored metadata and pools."""
from copy import deepcopy
from fractions import Fraction
import hashlib
from pathlib import Path

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import budgets, engineer, manifest, policy, profiles as p, protocol, routes
from skillopt.validator_pilot.api import digest
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, given

CONFIG = p.ALFWORLD_V1


def alf_manifest(tmp_path, monkeypatch):
    """No real data or credential file is opened; the sealed panel does not exist."""
    args = given(tmp_path)
    pool = tmp_path / "authored-pool.json"
    write_json(pool, [{"task_id": "authored-alf-1", "room": "1", "public": {
        "initial_observation": "Authored room.", "admissible_commands_at_reset": ["look"],
        "task_text": "Put a fixture mug on a fixture table."}, "private": {}}])
    args["cards"] = {"alfworld": args["cards"]["alfworld"]}
    args["contracts"] = {"alfworld": args["contracts"]["alfworld"]}
    args["runtime"] = {"alfworld": {"alfworld_data": str(tmp_path / "authored-games"),
                                       "max_steps": 50, "seed": 42}}
    pool_pin = {"path": str(pool), "sha256": hashlib.sha256(pool.read_bytes()).hexdigest()}
    split_pin = {"path": str(tmp_path / "unopened-split.json"), "sha256": "a" * 64}
    test_pin = {"path": str(tmp_path / "unopened-sealed-panel.json"), "sha256": "b" * 64}
    registration = {"preparation": {"path": str(tmp_path / "authored-preparation.json"),
        "sha256": "c" * 64, "record_sha256": "d" * 64}, "pool": pool_pin, "test": test_pin, "split": split_pin,
        "card_sha256": hashlib.sha256(args["cards"]["alfworld"].encode()).hexdigest(),
        "contract_sha256": args["contracts"]["alfworld"]["sha"],
        "runtime_sha256": digest(args["runtime"]["alfworld"])}
    args["data"] = {"pools": {"alfworld": pool_pin}, "pinned": {
        "paths": {"split": split_pin["path"], "test": {"alfworld": test_pin["path"]}},
        "sha256": {split_pin["path"]: split_pin["sha256"], test_pin["path"]: test_pin["sha256"]}},
        "alfworld_v1": registration, "launchable_chains": ["D"], "test_read_estimate": {"D": 1000},
        "test_read_terms": {"D": {"alfworld": "1000/1"}}}
    args["clients"]["solver"] = {chain: manifest.solver_block(chain,
        env_path=block["env_path"], branch=block["branch"], configuration=CONFIG)
        for chain, block in args["clients"]["solver"].items()}
    args["clients"]["routes"] = {"D": {"B": routes.pin("D", "B", env_path=tmp_path / "route.env",
        solver_block=args["clients"]["solver"]["D"], configuration=CONFIG)}}
    args["sheet_qualification"] = None
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "e" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored.py"})
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(tmp_path / "history"))
    return manifest.make(tmp_path / "alf-manifest.json", evidence="engineering_fixture", configuration=CONFIG,
        environment_found=fake_environment(), measured=MEASURED, **args)


def reseal(value):
    return protocol.record("manifest-alf-v1", value["evidence"], {
        key: item for key, item in value.items() if key not in ("version", "evidence", p.RECORD_HASH)})


def test_alf_v1_identity_family_and_features_are_distinct_from_all_older_configs():
    assert p.CONFIGURATIONS[CONFIG]["order"] == ("alfworld",)
    assert p.RUN_ROOTS[CONFIG] == p.ALFWORLD_V1_ROOT == "/data/execskill-20261026-alfworld-v1"
    assert p.ALFWORLD_V1_MANIFEST == p.ALFWORLD_V1_ROOT + "-manifest.json"
    assert p.CHAIN_NAMESPACES[CONFIG] == {"G": "G-alf1", "D": "D-alf1"}
    assert p.REAL_RUN_EVIDENCE[CONFIG] == "alfworld_v1_real_run"
    assert p.REAL_RUN_EVIDENCE[CONFIG] in protocol.EVIDENCE
    assert p.ACCEPT_FRESHNESS[CONFIG] == "alfworld_main_accept_slice_first_use"
    assert p.FEATURE_FAMILIES[CONFIG] == "v2.6"
    assert all(fn(CONFIG) for fn in (p.is_alfworld, p.is_v23, p.is_v24, p.is_v25, p.is_v26))
    assert not p.is_zebra(CONFIG) and not p.is_alfworld(None)
    assert all(not p.is_alfworld(name) for name in p.CONFIGURATIONS if name not in (CONFIG, p.ALFWORLD_V2))
    for table in ("LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
                  "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
                  "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS"):
        assert getattr(p, table)[CONFIG] == getattr(p, table)[p.ZEBRA_PC_V4], table
    assert p.ENGINEER_RECORDS[CONFIG] == "engineer-alf-v1"
    assert p.POLICY_VERSIONS[CONFIG] == policy.POLICY_VERSION_V25
    assert policy.source_limit(p.POLICY_VERSIONS[CONFIG]) == 16_000
    assert p.active_benches(CONFIG) == p.read_benches(CONFIG) == ("alfworld",)
    assert p.launchable_chains(CONFIG) == ("D",)
    assert p.stage_arms_max(CONFIG) == 0 and p.read_arms_of(CONFIG) == p.TEST_ARMS
    assert p.TRAIN_ROUNDS == 6 and p.TRAIN_CELLS["alfworld"] == 720


def test_caps_recompute_registered_alf_schedule_training_and_whole_scope_redo():
    schedule = p.CONFIG_SCHEDULE_CELLS[CONFIG]
    assert schedule == {"alfworld": {"run": {"alfworld": (0, 120)}, "examiner": {"alfworld": (0, 90)},
        "selftest": {"alfworld": (0, 880)}, "accept": {"alfworld": (150, 750)}}}
    assert all(set(cells) == {"alfworld"} for cells in schedule["alfworld"].values())
    reserve = 16 * 4 * (32_000 + 512 + 65_536)
    cost = lambda card, proc: 45_000 * (card + Fraction(8, 5) * proc)
    up = lambda value, quantum: -(-value // quantum) * quantum
    expected = {name: up(3 * (cost(*cells["alfworld"]) + reserve), 100_000)
                for name, cells in schedule["alfworld"].items()}
    assert expected == p.CONFIG_STEP_CAPS[CONFIG]["alfworld"] == {
        "run": 44_800_000, "examiner": 38_300_000, "selftest": 209_000_000, "accept": 201_100_000}
    read = up(3 * (cost(134, 670) + reserve), 1_000_000)
    redo = max(*(expected[name] for name in ("run", "examiner", "selftest")),
               up(3 * (cost(Fraction(150, 4), Fraction(750, 4)) + reserve), 100_000))
    assert read == 182_000_000 and redo == 209_000_000
    assert p.CONFIGURATIONS[CONFIG] == {"order": ("alfworld",), "solver_cap": 885_000_000,
        "test_read_cap": read, "redo_reserve": redo}
    assert up(sum(expected.values()) + read + redo, 5_000_000) == 885_000_000
    assert cost(150, 750) >= cost(300, 600)  # registered conservative bound for the empty-parent arms
    assert p.CONFIG_GLM_CAP[CONFIG] == 3 * sum(p.CONFIG_ROLE_CAPS[CONFIG].values()) == 117_600_000
    scopes = budgets.caps(CONFIG)
    assert scopes["overall"] == 1_002_600_000
    assert all(key == "overall" or key.startswith("D:") for key in scopes)
    assert scopes["D:xs:alfworld:1:selftest:attempt-2"] == redo


def test_read_projection_and_solver_bounds_only_allow_alfworld():
    per_cell = {"alfworld": {"card": 45_000, "procedure_assumed": True}}
    assert p.TEST_READ_CELLS[CONFIG] == {"alfworld": (134, 670)}
    assert p.read_estimate_terms(per_cell, 3, CONFIG) == {"alfworld": Fraction(3 * 134 * (45_000 + 4 * 72_000))}
    assert p.estimate_test_read(per_cell, 3, CONFIG) == 133_866_000
    assert p.fired_share("alfworld", CONFIG) == 1
    with pytest.raises(ValueError, match="ALFWorld per-cell"):
        p.read_estimate_terms({**per_cell, "searchqa": {"card": 10}}, 3, CONFIG)
    with pytest.raises(ValueError, match="ALFWorld panel"):
        p.fired_share("searchqa", CONFIG)
    assert p.solver_tokens(p.CHAINS["D"], "alfworld") == 1024
    assert p.read_timeout(p.CHAINS["D"], "alfworld") == 180
    assert p.ALFWORLD_MAX_STEPS == 50


def test_manifest_records_prompts_only_alf_pins_and_selection_services(tmp_path, monkeypatch):
    value = alf_manifest(tmp_path, monkeypatch)
    assert value["version"] == p.kind("manifest-alf-v1")
    assert manifest.check(value) == value
    assert value["prompt_sha"]["engineer"] == engineer.ENGINEER_PROMPT_SINGLE_ALF_V1_SHA256
    assert value["prompt_sha"]["v2"]["engineer"] == engineer.ENGINEER_PROMPT_ALF_V1_SHA256
    assert value["data"]["alfworld_features"] == manifest.alfworld_features()
    assert value["data"]["alfworld_features"]["notes_coverage"] is False
    assert value["data"]["alfworld_features"]["slices"] == {"run": [60, 1], "accept": [150, 1], "blocks": 4}
    setting = manifest.setting_of(value, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert set(setting.pools) == set(setting.cards) == set(setting.runtime) == {"alfworld"}
    assert p.namespace_of(setting, "D") == "D-alf1" and setting.branch == "E"
    services = manifest.services_of(value, "D", setting=setting, transport=NO_CALLS)
    assert services.sources is services.engine is services.checker is None
    with pytest.raises(ValueError, match="only chain D"):
        manifest.setting_of(value, "G", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert not (Path(value["root"]) / "G").exists()
    assert not Path(value["data"]["alfworld_v1"]["test"]["path"]).exists()
    assert not Path(value["data"]["alfworld_v1"]["split"]["path"]).exists()


@pytest.mark.parametrize("mutation", ["pool", "test", "runtime", "card", "contract", "other_pool", "research", "launch", "sheet"])
def test_manifest_refuses_changed_or_unrelated_profile_identities(tmp_path, monkeypatch, mutation):
    value = deepcopy(alf_manifest(tmp_path, monkeypatch))
    if mutation == "pool":
        value["data"]["pools"]["alfworld"] = {**value["data"]["pools"]["alfworld"], "sha256": "f" * 64}
    elif mutation == "test":
        value["data"]["pinned"]["paths"]["test"]["searchqa"] = "/never-open-searchqa"
    elif mutation == "runtime":
        value["runtime"]["alfworld"]["seed"] = 13
    elif mutation == "card":
        value["cards"]["alfworld"] += " changed"
    elif mutation == "contract":
        value["contracts"]["alfworld"]["text"] += " changed"
    elif mutation == "other_pool":
        value["data"]["pools"]["searchqa"] = {"path": "/never-open-searchqa", "sha256": "a" * 64}
    elif mutation == "research":
        value["data"]["research"] = {}
    elif mutation == "launch":
        value["data"]["launchable_chains"] = ["G", "D"]
    elif mutation == "sheet":
        value["sheet_qualification"] = {"path": "/unrelated-sheet", "record_hash": "f" * 64}
    with pytest.raises(ValueError):
        manifest.check(reseal(value))


def test_alf_engineer_stamp_does_not_change_procedure_kind():
    for name in ("manifest", "engineer"):
        value = p.record(name + "-alf-v1", p.REAL_RUN_EVIDENCE[CONFIG], {})
        assert p.verified(value, name) == value
    for name in ("procedure", "decision", "cell"):
        with pytest.raises(ValueError, match="another kind"):
            p.verified(p.record(name + "-alf-v1", p.REAL_RUN_EVIDENCE[CONFIG], {}), name)
