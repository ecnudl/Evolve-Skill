"""Row C7b-1: the S0 driver ``skillopt.execskill.s0`` (registration §10 S0 rows, §2.6; implementation plan §10 step 3,
§11; registrar decisions 2026-10-22 A5-1 and C5-3). Every row in fake mode (FakeDocker, a fake pytest result,
synthetic items), the A5-1 limits rule with its memory guard, the fixer-9 escape rows, the D3 replay conversion and the
``checks.json`` that ``smoke --stage S0`` reads. Integrator I1: the sheet row of ticket C7b1-3 (this snapshot's engine
qualification, the same engine sources as v3's, every fixture qualified) and the exported SearchQA pool that
``smoke_items`` reads (C7b1-2). Offline and deterministic: no docker, no network, no test-pool file."""
from __future__ import annotations

import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import fixtures, protocol, qualify, s0, smoke, supply
from skillopt.execskill.errors import ConsumptionConflict
from skillopt.execskill.registry import Registry
from skillopt.execskill.sandbox import client
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeAlfEnv
from tests.fixtures.execskill.items import alfworld_games, alfworld_items, searchqa_items
from tests.test_execskill_qualify import engine_record, identity, v3_sheet_runtime

GIB_KIB = 1 << 20
SMALL = {"vsz_kib": 600_000, "view_bytes_max": 300_000, "native_peak_rss_kib": 900_000, "worker_rss_kib": 120_000,
         "call_rss_kib": 50_000}
TRACES = [{"chain": "E-ds", "cell": "c%d" % n, "item": "alfworld/val:%04d" % n, "token": "pass" if n else "fail",
           "initial": "-= Welcome to TextWorld, ALFRED! =-\n\nYou are in the middle of a room. Looking quickly around "
                      "you, you see a cabinet 1, a countertop 1, and a fridge 1.\n\nYour task is to: put a mug in "
                      "fridge.",
           "steps": [["go to countertop 1", "You arrive at countertop 1. On the countertop 1, you see a mug 1."],
                     ["take mug 1 from countertop 1", "You pick up the mug 1 from the countertop 1."],
                     ["open drawer 9", "Nothing happens."],
                     ["go to fridge 1", "You arrive at fridge 1. The fridge 1 is closed."]][:3 + n]}
          for n in range(2)]


# --------------------------------------------------------------------------------------- A5-1: measurements -> limits
def test_limits_are_the_floors_when_the_measurements_are_small():
    found = s0.limits(SMALL, mem_available_kib=12 * GIB_KIB)
    assert set(found["limits"]) == set(client.KINDS)
    for kind, value in found["limits"].items():
        start = asdict(client.LIMITS[kind])
        assert value == {**start, "address_space_mb": 2048, "frame_bytes": 1 << 20}
        client.Limits(**value)  # within the sandbox's registered ranges
    assert found["slots"] == {"execskill-sandbox-live": 6, "execskill-sandbox": 4, "spreadsheet-native": 3}
    assert found["guard"]["steps"] == [] and found["guard"]["ok"] is True
    assert found["guard"]["budget_kib"] == int(0.7 * 12 * GIB_KIB)


@pytest.mark.parametrize("vsz_kib, address_mb", [(1 << 20, 2048), ((1 << 20) + 1, 2304), (1_600_000, 3328)])
def test_rlimit_as_is_twice_the_largest_vsz_rounded_up_to_256_mib(vsz_kib, address_mb):
    found = s0.limits({**SMALL, "vsz_kib": vsz_kib}, mem_available_kib=12 * GIB_KIB)
    assert {v["address_space_mb"] for v in found["limits"].values()} == {address_mb}


@pytest.mark.parametrize("view_bytes, frame", [(1 << 19, 1 << 20), ((1 << 19) + 1, 2 << 20), (700_000, 2 << 20),
                                               (3 << 20, 6 << 20)])
def test_frame_cap_is_twice_the_largest_public_view_rounded_up_to_1_mib(view_bytes, frame):
    found = s0.limits({**SMALL, "view_bytes_max": view_bytes}, mem_available_kib=12 * GIB_KIB)
    assert {v["frame_bytes"] for v in found["limits"].values()} == {frame}


def test_native_slots_drop_to_two_above_a_two_gib_native_peak():
    at = s0.limits({**SMALL, "native_peak_rss_kib": 2 * GIB_KIB}, mem_available_kib=12 * GIB_KIB)
    above = s0.limits({**SMALL, "native_peak_rss_kib": 2 * GIB_KIB + 1}, mem_available_kib=12 * GIB_KIB)
    assert at["slots"]["spreadsheet-native"] == 3 and above["slots"]["spreadsheet-native"] == 2


@pytest.mark.parametrize("budget_kib, steps, ok", [
    (13_000_000, [], True),  # 6 + 4 + 3 = 13 units of 1 GB fit exactly
    (12_000_000, [{"execskill-sandbox": 2}], True),  # 6 + 2 + 3 = 11
    (9_500_000, [{"execskill-sandbox": 2}, {"execskill-sandbox-live": 4}], True),  # 4 + 2 + 3 = 9
    (5_000_000, [{"execskill-sandbox": 2}, {"execskill-sandbox-live": 4}], False)])  # no registered step is left
def test_memory_guard_cuts_per_call_slots_then_live_slots(budget_kib, steps, ok):
    measured = {**SMALL, "worker_rss_kib": 1_000_000, "call_rss_kib": 1_000_000, "native_peak_rss_kib": 1_000_000}
    found = s0.limits(measured, mem_available_kib=budget_kib * 10 // 7 + 1)
    assert found["guard"]["budget_kib"] == budget_kib
    assert found["guard"]["steps"] == steps and found["guard"]["ok"] is ok
    live = 4 if len(steps) == 2 else 6
    per_call = 2 if steps else 4
    assert found["slots"] == {"execskill-sandbox-live": live, "execskill-sandbox": per_call, "spreadsheet-native": 3}
    assert found["guard"]["sum_kib"] == 1_000_000 * (live + per_call + 3)


# ------------------------------------------------------------------------------- escape rows (fixer-9 item 2, C5-3)
def test_the_fake_report_passes_both_row_sets_and_each_fixer9_row_can_fail():
    report = s0.fake_escape_report()
    assert all(smoke.escape_rows(report).values())
    assert s0.fixer9_rows(report) == {row: True for row in s0.FIXER9_ROWS}
    broken = {"dumpable": ("worker", "dumpable", 1), "sigint": ("worker", "after_sigint", "lost"),
              "process_group": ("group", "child_pgid", 1)}
    for row, (where, key, value) in broken.items():
        report = s0.fake_escape_report()
        (report["worker"] if where == "worker" else report["worker"]["group"])[key] = value
        assert s0.fixer9_rows(report)[row] is False
    report = s0.fake_escape_report()
    report["worker"]["group"]["descendant"] = "alive"
    assert s0.fixer9_rows(report)["process_group"] is False
    report = s0.fake_escape_report()
    report["worker"]["group"]["child_dumpable"] = 1
    assert s0.fixer9_rows(report)["dumpable"] is False


# ----------------------------------------------------------------------------------------- named pytest selections
@pytest.mark.parametrize("returncode, output, passed", [(0, b"..\n3 passed in 0.12s\n", True),
                                                        (1, b"F.\n1 failed, 2 passed in 0.2s\n", False),
                                                        (5, b"\n2 deselected, no tests ran in 0.1s\n", False)])
def test_named_tests_run_the_registered_selection_and_read_its_summary(tmp_path, returncode, output, passed):
    seen = {}

    def run(command, **options):
        seen.update(command=command, **options)
        return SimpleNamespace(returncode=returncode, stdout=output)

    files, keyword = s0.NAMED["exceptions"]
    found = s0.named_tests(tmp_path, files, keyword, run=run)
    assert found["passed"] is passed and found["summary"] == output.decode().strip().splitlines()[-1]
    assert seen["command"][-2:] == ["-k", "t_id_1"] and "-p" in seen["command"] and "no:cacheprovider" in seen["command"]
    assert seen["cwd"] == str(tmp_path) and "OPENAI_API_KEY" not in seen["env"]


# ----------------------------------------------------------------------------------------------------- D3 replay
def test_equivalence_ignores_only_the_measured_wall_time_of_a_native_run():
    """Real S0 run 2026-10-22: frozen and routed SpreadsheetBench predictions differed only in
    ``execution_costs.wall_seconds``; every other field still counts."""
    case = {"status": "unknown", "reason": "native_exception:SyntaxError",
            "execution_costs": {"container_calls": 1, "wall_seconds": 1.2, "includes_cleanup": True}}
    first = {"output": {"code": "x", "cases": [case]}, "costs": {"tokens": 3}}
    second = {"output": {"code": "x", "cases": [{**case, "execution_costs": {**case["execution_costs"],
                                                                         "wall_seconds": 1.4}}]},
              "costs": {"tokens": 3}}
    assert first != second and s0._steady(first) == s0._steady(second)
    assert s0._steady(first) != s0._steady({**second, "costs": {"tokens": 4}})
    assert "wall_seconds" not in json.dumps(s0._steady(second))


def test_d3_traces_become_hook_inputs_with_an_event_after_every_step():
    entries = s0.d3_entries(TRACES)
    assert [len(e["steps"]) for e in entries] == [3, 4]
    first = entries[0]
    assert first["bench"] == "alfworld" and first["cell"] == "d3/E-ds/c0" and first["item"] == "alfworld/val:0000"
    assert first["view"] == alf_routing_view(TRACES[0]["initial"], [])
    assert [s["event"]["action"] for s in first["steps"]] == [a for a, _ in TRACES[0]["steps"]]
    assert first["steps"][1]["view"]["observation"] == TRACES[0]["steps"][0][1]  # the view before step 2
    assert all(s["event"]["step"] == i for i, s in enumerate(first["steps"]))


def test_the_replay_row_runs_the_fixture_recorder_in_two_workers_and_checks_the_registered_counts(tmp_path):
    docker = FakeDocker(tmp_path / "containers")
    try:
        workers = s0._workers(s0.Deps(docker=docker), str(tmp_path))
        passed, found = s0.replay_row(TRACES, workers, expected=(2, 7))
        assert passed is True, found
        assert found["zero_crash"]["fault_count"] == 0 and found["reference_steps"] == 7
        assert found["agreement"][1] > 0
        registered, _ = s0.replay_row(TRACES, workers)  # 2 trajectories are not the registered 228 / 7,524
        assert registered is False
    finally:
        docker.close()


# ---------------------------------------------------------------------------------------------- collect (fake)
def _selftest(path):
    value = protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": client.worker_sha256(), "image": client.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted(client.LIMITS.items())},
        "measured": {"vsz_kib": 1_000, "rss_kib": 1_000, "view_bytes_p99": 2_000, "start_seconds": 0.5, "views": 3},
        "passed": True})
    write_json(path, value)
    return path


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("s0-inputs")
    fixtures.make_fixtures(root / "fx")
    items = {bench: root / "fx" / ("%s.json" % bench) for bench in fixtures.BENCHES}
    items["searchqa"] = root / "searchqa.json"
    write_json(items["searchqa"], searchqa_items(4))
    alfworld = []
    for item, game in list(zip(alfworld_items(root / "games"), alfworld_games()))[:3]:
        observations, _, infos = FakeAlfEnv(game).reset()
        view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
        alfworld.append({**item, "public": {**item["public"], "routing_view": view,
                                            "routing_view_sha256": digest(view)}})
    items["alfworld"] = root / "alfworld.json"
    write_json(items["alfworld"], alfworld)
    (root / "snapshot" / "tests").mkdir(parents=True)
    (root / "snapshot" / "tests" / "test_execskill_example.py").write_text("def test_example():\n    pass\n")
    write_json(root / "traces.json", TRACES)
    return SimpleNamespace(root=root, items={k: str(v) for k, v in items.items()}, selftest=_selftest(
        root / "selftest.json"))


def _collect(made, tmp_path, **changes):
    deps = s0.fake_deps(str(tmp_path))
    deps.extra["d3_expected"] = (2, 7)
    for key, value in changes.items():
        setattr(deps, key, value)
    try:
        found = s0.collect(tmp_path / "smoke", snapshot=made.root / "snapshot", items=made.items,
                           fixtures_dir=made.root / "fx", pins_out=tmp_path / "pins.json", selftest=made.selftest,
                           traces=made.root / "traces.json", deps=deps, scratch=str(tmp_path))
    finally:
        deps.docker.close()
        deps.extra["missing_docker"].close()
    return found


def test_collect_in_fake_mode_runs_every_row_and_writes_checks_that_smoke_s0_accepts(made, tmp_path):
    found = _collect(made, tmp_path)
    folder = tmp_path / "smoke" / s0.DIR
    records = {row: protocol.verified(read_json(folder / ("s0-%s.json" % row)), s0.ROW_KIND) for row in smoke.S0_ROWS}
    assert found["passed"] is True, {row: r["result"] for row, r in records.items() if not r["passed"]}
    checks = read_json(folder / s0.CHECKS)
    assert checks == {"checks": {row: True for row in smoke.S0_ROWS}}
    assert smoke.s0(checks["checks"]) == {"rows": {row: True for row in smoke.S0_ROWS}, "passed": True}
    assert all(r["version"] == "fivebench-execskill-v1-s0-row" and r["evidence"] == "smoke" for r in records.values())
    equivalence = records["equivalence"]["result"]["benches"]
    assert set(equivalence) == set(smoke.ITEM_SETS)
    assert all(v["different"] == 0 and v["compared"] > 0 for v in equivalence.values())
    sandbox = records["sandbox"]["result"]
    assert sandbox["image_missing_is_unavailable"] is True and sandbox["drained"] is True
    assert set(sandbox["cases"]) == {c["id"] for c in fixtures.sandbox_suite()[1]}
    assert records["escape_probe"]["result"]["dumpable"] == 0
    measured = records["measurements"]["result"]
    assert measured["dumpable"] == 0 and measured["spec_limits_equal_derived"] is True
    pins = read_json(tmp_path / "pins.json")
    assert set(pins) == {"limits", "measured"} and pins["limits"] == measured["derived"]["limits"]
    assert set(pins["measured"]) == {"vsz_kib", "rss_kib", "view_bytes_p99", "native_peak_rss_kib"}
    assert pins["measured"]["native_peak_rss_kib"] == 400_000 and pins["measured"]["vsz_kib"] == 1_000
    limits = protocol.verified(read_json(folder / s0.LIMITS_FILE), s0.LIMITS_KIND)
    assert limits["p99_workbook_bytes"] == 9_000
    determinism = records["determinism"]["result"]
    assert determinism["equal"] is True and determinism["seeds"] == ["0", "1"] and len(set(determinism["draws"])) == 1
    with pytest.raises(ValueError, match="once"):
        _collect(made, tmp_path)


def test_a_failing_row_is_recorded_and_no_limits_are_pinned_without_a_passing_measurement(made, tmp_path):
    leftovers = {"verdict": "leftovers", "containers": ["execskill-sbx-0"]}
    found = _collect(made, tmp_path, leftovers=lambda: leftovers, mem_available_kib=lambda: 1_000)
    assert found["passed"] is False
    assert found["checks"]["leftovers"] is False and found["checks"]["measurements"] is False
    assert found["checks"]["pytest"] is True and found["checks"]["sandbox"] is True
    folder = tmp_path / "smoke" / s0.DIR
    assert read_json(folder / "s0-leftovers.json")["result"] == leftovers
    assert read_json(folder / "s0-measurements.json")["result"]["derived"]["guard"]["ok"] is False
    assert not (tmp_path / "pins.json").exists() and not (folder / s0.LIMITS_FILE).exists()
    assert smoke.s0(read_json(folder / s0.CHECKS)["checks"])["passed"] is False


# ------------------------------------------------------------------------------------------- smoke item files (§10)
def _alfworld_supply(tmp_path):
    """A synthetic supply of 108 rooms x 3 games with its pre-reset views (the shape ``make-items`` writes)."""
    items = []
    for room in range(108):
        for game in range(3):
            relative = "json_2.1.1/train/pick_and_place_simple-Obj%d-None-Shelf-%d/trial_T%03d_%d/game.tw-pddl" % (
                game, 200 + room, room, game)
            items.append({"benchmark": "alfworld", "task_id": supply.xs_id(relative), "gamefile": relative,
                          "room": str(200 + room), "task_type": "pick_and_place_simple", "game_sha256": "0" * 64})
    value = supply.supply_record("alfworld-xs", "alfworld", items, sources={}, evidence="smoke")
    views = {}
    for item in items:
        view = alf_routing_view("You are in room %s.\n\nYour task is to: put a mug in shelf." % item["room"],
                                ["look", "inventory"])
        views[item["task_id"]] = {"view": view, "view_sha256": digest(view)}
    write_json(tmp_path / "supply" / "alfworld-xs.json", value)
    write_json(tmp_path / "supply" / "alfworld-xs-views.json", protocol.record("alfworld-views", "smoke", {
        "supply_sha256": value[protocol.RECORD_HASH], "views": views, "slices": {}}))
    return value


def _searchqa_export(folder, count=600):
    """``export-pools``' SearchQA file for a synthetic pool (400 train + the rest val), in supply order."""
    pool = [{**item, "part": "train" if n < 400 else "val"} for n, item in enumerate(searchqa_items(count))]
    supply.write_pool_export(folder, {"searchqa": (supply.order("searchqa", pool), {"pool": count, "items": count})},
                             source={"synthetic": True})
    return pool, folder / "searchqa.json"


def test_smoke_items_cut_registered_sets_and_feed_smoke_make(made, tmp_path, monkeypatch):
    pool, exported = _searchqa_export(tmp_path / "pools")
    alfworld = _alfworld_supply(tmp_path)
    options = dict(searchqa_pool=exported, alfworld_supply=tmp_path / "supply" / "alfworld-xs.json",
                   alfworld_views=tmp_path / "supply" / "alfworld-xs-views.json", data_root=tmp_path / "data",
                   fixtures_dir=made.root / "fx", run_root=tmp_path / "pre" / "smoke",
                   history_root=tmp_path / "history")
    value = s0.smoke_items(tmp_path / "items", **options)
    assert value["version"] == "fivebench-execskill-v1-smoke-items" and value["evidence"] == "smoke"
    searchqa, games = read_json(value["items"]["searchqa"]), read_json(value["items"]["alfworld"])
    ordered = supply.order("searchqa", pool)
    assert [i["task_id"] for i in searchqa] == [i["task_id"] for i in ordered[-280:]]  # the tail of the pool order
    assert {stage: len(ids) for stage, ids in value["stages"]["searchqa"].items()} == {"S2": 20, "SN1": 200, "S4": 60}
    assert {stage: len(ids) for stage, ids in value["stages"]["alfworld"].items()} == {"S2": 6, "SN1": 6}
    smoke_rooms = supply.room_groups(supply.room_order(alfworld["items"]))["smoke"]
    assert len(games) == 12 and {g["room"] for g in games} == set(smoke_rooms) == set(value["rooms"])
    assert all(g["public"]["game_file"].startswith(str(tmp_path / "data")) and
               digest(g["public"]["routing_view"]) == g["public"]["routing_view_sha256"] for g in games)
    assert value["items"]["officeqa"] == str(made.root / "fx" / "officeqa.json")
    registry = Registry(tmp_path / "history", evidence="smoke")
    assert registry.consumed("smoke", "searchqa") == {i["task_id"] for i in searchqa}
    assert registry.consumed("smoke", "alfworld") == {g["task_id"] for g in games}
    assert {e["purpose"] for e in registry.entries("smoke", "searchqa").values()} == {"smoke"}
    assert s0.smoke_items(tmp_path / "items", **options) == value  # a repeat reuses its own registration
    with pytest.raises(ConsumptionConflict):
        registry.register("smoke", "searchqa", searchqa[:1], unit="smoke/other", purpose="smoke", run_root="r")
    monkeypatch.setattr(smoke.manifest, "environment", lambda **_: {})
    spec = smoke.make(tmp_path / "smoke", items=value["items"], control_cells=["S2/searchqa/X/fx-crash/q1/1"],
                      noise_anchor={"searchqa": 0.3, "alfworld": 0.45}, selftest=made.selftest, write=False)
    assert {name: entry["count"] for name, entry in spec["items"].items()} == {
        "searchqa": 280, "alfworld": 12, "officeqa": 20, "livemath": 20, "spreadsheetbench": 20}


def test_smoke_items_read_only_the_exported_600_item_searchqa_pool(made, tmp_path):
    """Ticket C7b1-2: ``--searchqa-pool`` is ``export-pools``' file, checked against its sealed record; a plain list,
    a changed file or a pool of another size is refused before anything is registered or written."""
    _alfworld_supply(tmp_path)
    options = dict(alfworld_supply=tmp_path / "supply" / "alfworld-xs.json",
                   alfworld_views=tmp_path / "supply" / "alfworld-xs-views.json", data_root=tmp_path / "data",
                   fixtures_dir=made.root / "fx", run_root=tmp_path / "pre" / "smoke",
                   history_root=tmp_path / "history")
    pool, exported = _searchqa_export(tmp_path / "pools")
    write_json(tmp_path / "plain" / "searchqa.json", supply.order("searchqa", pool))  # the same items, no export
    with pytest.raises(ValueError, match="Not an exported pool"):
        s0.smoke_items(tmp_path / "a", searchqa_pool=tmp_path / "plain" / "searchqa.json", **options)
    _, short = _searchqa_export(tmp_path / "short", count=580)  # an export, but not the registered pool
    with pytest.raises(ValueError, match="registered 600"):
        s0.smoke_items(tmp_path / "b", searchqa_pool=short, **options)
    exported.write_text(exported.read_text().replace("Fixtown 7\"", "Fixtown 8\""))
    with pytest.raises(ValueError, match="not the exported file"):
        s0.smoke_items(tmp_path / "c", searchqa_pool=exported, **options)
    assert not (tmp_path / "history").exists() and not any((tmp_path / name).exists() for name in "abc")


# --------------------------------------------------------------------------------- the sheet row (ticket C7b1-3)
def _sheet_deps(tmp_path, **changes):
    deps = s0.fake_deps(str(tmp_path))
    deps.docker.close()
    deps.extra["missing_docker"].close()
    for key, value in changes.items():
        setattr(deps, key, value)
    return deps


def _sheet(made, tmp_path, deps, **options):
    return s0.sheet_row(deps, source="v3.json", sha256="0" * 64, base_runtime=options.get("base"),
                        engine_qualification=options.get("engine"), fixtures_dir=made.root / "fx",
                        target=tmp_path / "sheet-fixture-qualification")


def test_the_sheet_row_passes_only_with_the_import_every_fixture_qualified_and_the_same_engine(made, tmp_path):
    passed, found = _sheet(made, tmp_path, _sheet_deps(tmp_path), engine="/q23/qualification.json")
    assert passed is True and found["fixtures"]["all_qualified"] is True and found["fixtures"]["qualified"] == 20
    engine = found["engine"]
    assert engine["qualification_path"] == "/q23/qualification.json" and engine["same_sources_as_v3_training"]["same"]
    assert set(engine) == {"qualification_path", "qualification_sha256", "qualification_hash",
                           "same_sources_as_v3_training"}
    seen = []

    def other(new, old):
        seen.append((new, old))
        return {**s0._fake_same_sources(new, old), "same": False}

    passed, found = _sheet(made, tmp_path, _sheet_deps(tmp_path, same_sources=other),
                           engine="/q23/qualification.json")
    assert passed is False and found["engine"]["same_sources_as_v3_training"]["same"] is False
    assert seen == [("/q23/qualification.json", "/fake/v3-q23/qualification.json")]  # new vs the v3 training's engine

    def one_excluded(tasks, target, runtime):
        return {**s0._fake_qualification(tasks, target, runtime), "excluded": {tasks[0]["task_id"]: "other"}}

    passed, found = _sheet(made, tmp_path, _sheet_deps(tmp_path, qualify_fixtures=one_excluded), engine="/q")
    assert passed is False and found["fixtures"]["all_qualified"] is False

    def not_imported(source, sha256):
        raise ValueError("The qualification record is not the pinned one")

    with pytest.raises(ValueError, match="pinned"):  # collect records a raised row as that row's failure
        _sheet(made, tmp_path, _sheet_deps(tmp_path, sheet_import=not_imported), engine="/q")


def test_the_real_sheet_row_runs_on_the_snapshots_engine_runtime_and_compares_the_sources(made, tmp_path,
                                                                                          monkeypatch):
    """The real ``engine_runtime`` and ``same_engine_sources`` on synthetic sealed qualifications; only the frozen
    offline revalidation (``qualify.revalidate``) and the fixture scoring are replaced."""
    old = tmp_path / "v3-q23-f" / "qualification.json"
    engine_record(old, identity("/data/coevo5-20261019-v3-source-f"))
    new = tmp_path / "q23" / "qualification.json"
    record = engine_record(new, identity("/data/execskill-20261021-source"))
    checked, scored = [], []
    monkeypatch.setattr(qualify, "revalidate", checked.append)

    def imported(source, sha256):
        return {"version": "fivebench-coevolution-v3-sheet-qualification", "summary": {"qualified": 91},
                "recalculation": {"qualification_path": str(old)}}

    def scoring(tasks, target, runtime):
        scored.append(runtime)
        return s0._fake_qualification(tasks, target, runtime)

    deps = _sheet_deps(tmp_path, engine_runtime=None, same_sources=None, sheet_import=imported,
                       qualify_fixtures=scoring)
    passed, found = _sheet(made, tmp_path, deps, base=v3_sheet_runtime(), engine=str(new))
    assert passed is True and checked == scored and len(scored) == 1
    assert scored[0]["recalculation"]["qualification_hash"] == record["record_hash"] == \
        found["engine"]["qualification_hash"]
    assert {k: v for k, v in scored[0].items() if k != "recalculation"} == \
        {k: v for k, v in v3_sheet_runtime().items() if k != "recalculation"}
    assert found["engine"]["same_sources_as_v3_training"]["sources"] == {"new": 7, "old": 7, "equal": 7,
                                                                         "differing": []}
    changed = identity("/data/execskill-20261021-source")
    changed["sources"]["/data/execskill-20261021-source/skillopt/continual_eval/sheet_recalc_v7.py"] = "f" * 64
    engine_record(tmp_path / "q23-changed" / "qualification.json", changed)
    passed, found = _sheet(made, tmp_path, deps, base=v3_sheet_runtime(),
                           engine=str(tmp_path / "q23-changed" / "qualification.json"))
    assert passed is False
    assert found["engine"]["same_sources_as_v3_training"]["sources"]["differing"] == [
        "skillopt/continual_eval/sheet_recalc_v7.py"]


def test_collect_on_the_real_path_needs_the_engine_qualification_before_any_row(made, tmp_path):
    options = dict(snapshot=made.root / "snapshot", items=made.items, fixtures_dir=made.root / "fx",
                   pins_out=tmp_path / "pins.json", selftest=made.selftest, manifest_path=tmp_path / "v3.json",
                   sheet_source="v3-train.json", sheet_sha256="0" * 64, deps=s0.Deps(docker=object()))
    with pytest.raises(ValueError, match="engine qualification"):
        s0.collect(tmp_path / "smoke", **options)
    assert not (tmp_path / "smoke").exists()  # S0 is collected once: nothing ran, nothing was written


def test_m1_s0_equivalence_runs_on_the_cards_and_runtimes_and_marks_an_unexecuted_frozen_run_invalid(made):
    """Codex #13 (MINOR): the equivalence row runs on the imported cards and the pinned runtimes and records both by
    hash; an item whose frozen run's backend did not execute validly (a native case not "available") is "invalid",
    never "same", and fails the row -- identical infrastructure failures prove nothing."""
    import hashlib

    from tests.execskill_fakes_env import FakeNative
    sheet, fake = {"spreadsheetbench": made.items["spreadsheetbench"]}, FakeNative()
    cards = {"spreadsheetbench": s0.REHEARSAL_CARDS["spreadsheetbench"]}
    runtimes = {"spreadsheetbench": s0.REHEARSAL_RUNTIMES["spreadsheetbench"]}
    n = len(read_json(made.items["spreadsheetbench"]))
    passed, found = s0.equivalence(sheet, cards=cards, runtimes=runtimes, native=fake.native, precheck=fake.precheck)
    assert passed is True and fake.cases
    assert found["benches"]["spreadsheetbench"] == {"same": n, "different": 0, "excluded": 0, "invalid": 0,
                                                    "compared": n}
    assert found["cards_sha256"] == {"spreadsheetbench": hashlib.sha256(cards["spreadsheetbench"].encode()).hexdigest()}
    assert found["runtimes_sha256"] == {"spreadsheetbench": digest(runtimes["spreadsheetbench"])}

    def failed(request, runtime):
        return {"status": "unknown", "reason": "native_exception:SyntaxError", "cleanup_confirmed": True}
    passed, found = s0.equivalence(sheet, cards=cards, runtimes=runtimes, native=failed, precheck=fake.precheck)
    assert passed is False
    assert found["benches"]["spreadsheetbench"] == {"same": 0, "different": 0, "excluded": 0, "invalid": n,
                                                    "compared": 0}
    for bad in ({}, {"spreadsheetbench": "  "}):
        with pytest.raises(ValueError, match="imported cards"):
            s0.equivalence(sheet, cards=bad, runtimes=runtimes, native=fake.native, precheck=fake.precheck)
    with pytest.raises(ValueError, match="pinned runtime"):
        s0.equivalence(sheet, cards=cards, runtimes={}, native=fake.native, precheck=fake.precheck)
