"""Authored zero-call ALF confirm preparation; all assets live in pytest tmp."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (alf_confirm_views as cv, alf_smoke, confirm, manifest,
                               profiles as p, routes, step, supply)
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.test_execskill_manifest import MEASURED, NO_CALLS, FakeDockerCLI, fake_environment, given, tree


def reseal(value):
    return p.record(cv.KIND, value["evidence"], {
        key: row for key, row in value.items() if key not in ("version", "evidence", p.RECORD_HASH)})


def authored_preparation(root, monkeypatch):
    """A main preparation whose original export leaves every spare game unreset."""
    root.mkdir(parents=True)
    game_root = root / "games"
    game_root.mkdir()
    runtime = {"alfworld_data": str(game_root), "max_steps": 50, "seed": 42}
    games = []
    for room in range(108):
        for number in range(5):
            key = "room-%03d-game-%d" % (room, number)
            file = game_root / (key + ".synthetic-game")
            file.write_text("authored game " + key, encoding="utf-8")
            games.append({"task_id": key, "room": str(room), "task_type": "pick_and_place_simple",
                          "gamefile": file.name, "game_sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
    fresh = supply.supply_record("alfworld-xs", "alfworld", games,
        sources={"data_root": str(game_root), "pool_games_sha256": "a" * 64}, evidence="engineering_fixture")
    original = supply.slices("alfworld", supply.order("alfworld", games), supply.registered_sizes("alfworld"))
    reset = lambda row: ("Authored room.\nYour task is to: inspect " + row["task_id"], ["look"])
    views = supply.views_record(fresh, supply.prereset(games, original, reset=reset), original, runtime=runtime)
    fresh_file, views_file = root / "supply.json", root / "views.json"
    write_json(fresh_file, fresh)
    write_json(views_file, views)
    pool, counts = supply.alfworld_pool(fresh, views, runtime=runtime)
    exported = supply.write_pool_export(root / "pool", {"alfworld": (pool, counts)}, source={"alfworld": {
        "supply": str(fresh_file), "supply_sha256": fresh[p.RECORD_HASH],
        "views": str(views_file), "views_sha256": views[p.RECORD_HASH]}})
    values = given(root)
    test, split = str(root / "unopened-panel.json"), str(root / "unopened-split.json")
    values["data"] = {"pools": supply.pool_pins(exported), "pinned": {
        "paths": {"split": split, "test": {"alfworld": test}}, "sha256": {test: "a" * 64, split: "b" * 64}}}
    values["runtime"]["alfworld"] = runtime
    values["clients"]["solver"] = {name: manifest.solver_block(name, env_path=block["env_path"],
        branch=block["branch"], configuration=p.MAIN_V2_2) for name, block in values["clients"]["solver"].items()}
    values["clients"]["routes"] = {"D": {"B": routes.pin("D", "B", env_path=root / "unread-route.env",
        solver_block=values["clients"]["solver"]["D"], configuration=p.MAIN_V2_2)}}
    card = values["cards"]["alfworld"]
    monkeypatch.setattr(manifest, "ALFWORLD_CARD_IDENTITY", (len(card), hashlib.sha256(card.encode()).hexdigest()))
    monkeypatch.setattr(manifest, "pin_code", lambda: {"authored.py": "c" * 64})
    monkeypatch.setattr(manifest, "loaded_code", lambda: {"authored.py"})
    from skillopt.execskill import protocol
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(root / "slots"))
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(root / "history"))
    preparation = root / "main-preparation.json"
    manifest.make(preparation, evidence="engineering_fixture", configuration=p.MAIN_V2_2,
                  environment_found=fake_environment(), measured=MEASURED, **values)
    calls = []

    class Environment:
        def __init__(self, key):
            self.key = key
        def reset(self):
            calls.append(("reset", self.key))
            return ["Authored confirm room.\nYour task is to: inspect " + self.key], None, [{"admissible_commands": ["look"]}]
        def close(self):
            calls.append(("close", self.key))

    def opened(public, actual_runtime):
        assert actual_runtime == runtime
        return Environment(Path(public["game_file"]).stem)

    monkeypatch.setattr(backends, "_new_alfworld", opened)
    return preparation, game_root, pool, runtime, calls


def prepared(tmp_path, monkeypatch):
    preparation, game_root, pool, runtime, calls = authored_preparation(tmp_path / "source", monkeypatch)
    path = tmp_path / "confirm-views.json"
    value = cv.prepare(path, configuration=p.ALFWORLD_V4, preparation_file=preparation, data_root=game_root)
    return preparation, pool, runtime, calls, path, value


def test_confirm_prereset_uses_exact_40_spare_games_and_original_runtime_once(tmp_path, monkeypatch):
    preparation, game_root, pool, runtime, calls = authored_preparation(tmp_path / "source", monkeypatch)
    selected, pin = confirm.slice_items(p.ALFWORLD_V4, pool)
    assert len(selected) == 40 and all("routing_view" not in row["public"] for row in selected)
    before = {path: path.read_bytes() for path in (tmp_path / "source").rglob("*.json")}
    out = tmp_path / "confirm-views.json"
    result = cv.prepare(out, configuration=p.ALFWORLD_V4, preparation_file=preparation, data_root=game_root)
    assert {key for action, key in calls if action == "reset"} == set(pin["ids"])
    assert len(calls) == 80 and sum(action == "close" for action, _ in calls) == 40
    assert result["ids"] == pin["ids"] and result["confirm_ids_sha256"] == pin["ids_sha256"]
    assert result["runtime_sha256"] == digest(runtime)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert cv.load_for_preparation(out, configuration=p.ALFWORLD_V4,
        imported=alf_smoke.preparation(preparation), items=pool) == result
    with pytest.raises(ValueError, match="written once"):
        cv.prepare(out, configuration=p.ALFWORLD_V4, preparation_file=preparation, data_root=game_root)
    assert len(calls) == 80


@pytest.mark.parametrize("change", ["runtime", "data_root", "game"])
def test_confirm_prereset_refuses_mismatched_runtime_root_or_game_before_reset(tmp_path, monkeypatch, change):
    preparation, game_root, pool, runtime, calls = authored_preparation(tmp_path / "source", monkeypatch)
    if change == "runtime":
        source = read_json(preparation)
        source["runtime"]["alfworld"]["seed"] += 1
        other = tmp_path / "changed-preparation.json"
        write_json(other, p.record("manifest", source["evidence"], {
            key: value for key, value in source.items() if key not in ("version", "evidence", p.RECORD_HASH)}))
        preparation = other
    elif change == "data_root":
        game_root = tmp_path / "other-games"
    else:
        selected, _ = confirm.slice_items(p.ALFWORLD_V4, pool)
        Path(selected[0]["public"]["game_file"]).write_text("changed authored game", encoding="utf-8")
    with pytest.raises(ValueError):
        cv.prepare(tmp_path / "views.json", configuration=p.ALFWORLD_V4,
                   preparation_file=preparation, data_root=game_root)
    assert not calls


@pytest.mark.parametrize("change", ["ids", "view", "runtime", "supply", "id_hash", "missing"])
def test_v29_s0_requires_exact_intact_confirm_record_before_other_work(tmp_path, monkeypatch, change):
    preparation, pool, runtime, calls, path, value = prepared(tmp_path, monkeypatch)
    changed = deepcopy(value)
    if change == "ids":
        changed["ids"].pop()
    elif change == "view":
        changed["views"][changed["ids"][0]]["view"]["task_text"] += " changed"
    elif change == "runtime":
        changed["runtime_sha256"] = "f" * 64
    elif change == "supply":
        changed["source"]["supply_sha256"] = "f" * 64
    elif change == "id_hash":
        changed["confirm_ids_sha256"] = "f" * 64
    mutated = tmp_path / "mutated-views.json"
    write_json(mutated, reseal(changed))
    with pytest.raises(ValueError):
        alf_smoke.collect_s0(tmp_path / "s0", preparation_file=preparation,
            confirm_views=None if change == "missing" else mutated, configuration=p.ALFWORLD_V4,
            selftest=tmp_path / "must-not-open", checks={"passed": True})
    assert not (tmp_path / "s0").exists()
    assert len(calls) == 80


def test_v29_s0_manifest_and_step_pin_and_attach_confirm_views_by_value(tmp_path, monkeypatch):
    preparation, pool, runtime, calls, path, value = prepared(tmp_path, monkeypatch)
    snapshot = tree(tmp_path / "snapshot")
    monkeypatch.setattr(manifest, "REPO", snapshot)
    selftest = tmp_path / "selftest.json"
    write_json(selftest, p.record("sandbox-selftest", "smoke", {"passed": True,
        "measured": dict(MEASURED), "limits": {key: asdict(limits) for key, limits in sandbox.LIMITS.items()}}))
    checked = alf_smoke.collect_s0(tmp_path / "s0", preparation_file=preparation, confirm_views=path,
        configuration=p.ALFWORLD_V4, snapshot_root=snapshot, selftest=selftest, checks={"passed": True})
    assert checked["passed"] and checked["slice_counts"]["confirm"] == 40
    assert checked["alf_confirm_views"] == value and checked["slice_ids"]["confirm"] == value["ids"]
    provenance = tmp_path / "snapshot-provenance.json"
    write_json(provenance, {"build_tree": str(snapshot), "git_head": "e" * 40, "snapshot_root": str(snapshot),
                           "sha256_list_sha256": checked["snapshot_sha256"], "env_files_absent": True})
    # The original new record need not remain at its CLI path once S0 pins its value.
    path.unlink()
    result = alf_smoke.make_manifest(tmp_path / "manifest.json", root=tmp_path / "run",
        s0_file=tmp_path / "s0" / alf_smoke.S0_FILE, provenance=provenance,
        roles_repo=tmp_path / "unread-credentials", elucid_env=tmp_path / "unread-elucid.env",
        route_b_env=tmp_path / "unread-route.env", smoke_chain="D", environment_found=fake_environment(),
        configuration=p.ALFWORLD_V4)
    assert result["data"]["alf_confirm_views"] == value
    for tamper in ("missing", "view"):
        invalid = deepcopy(result)
        if tamper == "missing":
            del invalid["data"]["alf_confirm_views"]
        else:
            invalid["data"]["alf_confirm_views"]["views"][value["ids"][0]]["view"]["task_text"] += " changed"
        invalid = p.record("manifest-v2-9", invalid["evidence"], {
            key: row for key, row in invalid.items() if key not in ("version", "evidence", p.RECORD_HASH)})
        with pytest.raises(ValueError):
            manifest.check(invalid)
    setting = manifest.setting_of(result, "D", docker=FakeDockerCLI(), transport=NO_CALLS)
    assert setting.extra["alf_confirm_views"] == value
    st = SimpleNamespace(bench="alfworld", setting=setting, runtime=lambda: runtime,
                         root=tmp_path / "step", chain="D", k=1, smoke=None)
    cut = step._cut(st, [])
    assert len(cut["confirm"]) == 40 and all(row["views_runtime_sha256"] == digest(runtime) for row in cut["confirm"])
    assert all(row["public"]["routing_view"] == value["views"][row["task_id"]]["view"] for row in cut["confirm"])
    assert all("routing_view" not in row["public"] for row in confirm.slice_items(p.ALFWORLD_V4, pool)[0])
    st.root.mkdir()
    write_json(st.root / step.SLICES_FILE, p.record("step-slices", "engineering_fixture", {
        "chain": "D", "k": 1, "bench": "alfworld",
        "slices": {name: [row["task_id"] for row in rows] for name, rows in cut.items()}}))
    assert step._slices(st) == cut
    assert len(calls) == 80


def test_confirm_views_cli_inputs_and_v29_s0_flag():
    from scripts.run_execskill import HANDLERS, parser
    args = parser().parse_args(["alf-confirm-views", "--configuration", p.ALFWORLD_V4,
        "--preparation", "main.json", "--data-root", "games", "--out", "confirm.json"])
    assert args.command in HANDLERS and args.preparation == "main.json" and args.data_root == "games"
    args = parser().parse_args(["alf-s0", "--configuration", p.ALFWORLD_V4, "--out", "s0",
        "--preparation", "main.json", "--confirm-views", "confirm.json"])
    assert args.confirm_views == "confirm.json"
