"""The zero-call smoke rehearsal (registration §10; implementation plan §7, §10 steps 5-8; registrar addenda 2026-10-22
13:0x and 14:3x): ``smoke.run_stage`` with ``fake=True`` runs S2, S3 (its own run unit, then the six role pieces on
``S3Rehearsal``; ticket C7d-1), S-N1 and S4 (the drill's pause, the operator's ``write_recovery`` and the redo) --
the last two no longer gate but keep their code -- and then S-E6 end to end on the plan-§7 fakes (the scripted elucid
gateway behind the real client, FakeDocker running the real sandbox worker, FakeAlfEnv, FakeNative) on a temporary
smoke root with zero network; S0 and S1 are synthesized as passing stage records; ``smoke.summary`` reads every
stage and passes on the spec's stages (S0, S1, S2, S3, S-E6). Engineering fixtures only."""
from __future__ import annotations

import math
from dataclasses import asdict

import pytest

from skillopt.coevo5.evaluation import recovered
from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, fixtures, manifest, protocol, research, smoke
from skillopt.execskill.registry import Registry
from skillopt.execskill.sandbox import client as sandbox
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.validator_pilot.api import digest
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import fake_config
from tests.execskill_fakes_env import FakeAlfEnv
from tests.fixtures.execskill.items import alfworld_games, alfworld_items, searchqa_items
from tests.test_execskill_manifest import MEASURED, fake_environment, given


def _alfworld(root):
    """The 12 fake games with their registered pre-reset routing views (S2 6, S-N1 6)."""
    out = []
    for game, item in zip(alfworld_games(), alfworld_items(root)):
        observations, _, infos = FakeAlfEnv(game).reset()
        view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
        out.append({**item, "room": game["room"],
                    "public": {**item["public"], "routing_view": view, "routing_view_sha256": digest(view)}})
    return out


def _write(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, items)
    return str(path)


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rehearsal")
    patch = pytest.MonkeyPatch()
    patch.setattr(protocol, "SLOT_ROOT", str(tmp / "slots"))
    patch.setattr(protocol, "HISTORY_ROOT", str(tmp / "history"))
    root = tmp / "smoke"
    fixtures.make_fixtures(tmp / "fixtures")
    sets = {bench: str(tmp / "fixtures" / (bench + ".json")) for bench in ("officeqa", "livemath",
                                                                           "spreadsheetbench")}
    sets["searchqa"] = _write(tmp / "items" / "searchqa.json", searchqa_items(280))
    sets["alfworld"] = _write(tmp / "items" / "alfworld.json", _alfworld(tmp / "games"))
    tested = tmp / "s0" / smoke.SELFTEST
    write_json(tested, protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
        "measured": {**{k: MEASURED[k] for k in ("vsz_kib", "rss_kib", "view_bytes_p99")}, "start_seconds": 2.6,
                     "views": 15}, "passed": True}))
    spec = smoke.make(root, items=sets, control_cells=["fx-drill-1"], noise_anchor={"searchqa": 0.21, "alfworld": 0.3},
                      selftest=str(tested), environment_found=fake_environment(),
                      probe_root=tmp / "probe")  # its own probe root: S2 never reads the registered one
    elucid, glm = fake_config(tmp, protocol.CHAINS["D"]), fake_config(tmp, protocol.CHAINS["G"])
    archive = fake_research.archive_fixture(tmp / "archive")
    values = {**given(tmp), "root": str(root),
              "clients": {"solver": {"D": manifest.solver_block("D", env_path=elucid["env_path"], branch="E"),
                                     "G": manifest.solver_block("G", env_path=glm["repo"])},
                          "roles": dict(manifest.ROLES)},
              "data": {"research": {"archive": str(archive), "index_sha256": research.Archive(archive).index_sha256}}}
    path = tmp / "smoke-manifest.json"
    manifest.make(path, evidence=manifest.SMOKE_EVIDENCE, environment_found=fake_environment(), measured=MEASURED,
                  **values)
    smoke.record(spec, "S0", smoke.s0({row: True for row in smoke.S0_ROWS}))
    smoke.record(spec, "S1", {"rows": {row: True for row in smoke.S1_ROWS}, "passed": True, "synthesized": True})
    stages = {stage: smoke.run_stage(root / smoke.SPEC, path, stage, fake=True) for stage in ("S2", "S3", "SN1")}
    stopped = smoke.run_stage(root / smoke.SPEC, path, "S4", fake=True)
    drill = [smoke.write_recovery(spec, attempt, decision="redo the round with the same sealed inputs")
             for attempt in stopped.get("paused", [])]
    stages["S4"] = smoke.run_stage(root / smoke.SPEC, path, "S4", fake=True)
    stages["SE6"] = smoke.run_stage(root / smoke.SPEC, path, "SE6", fake=True)
    yield {"spec": spec, "root": root, "path": path, "stages": stages, "tmp": tmp, "stopped": stopped, "drill": drill}
    patch.undo()


def test_every_built_stage_is_recorded_and_judged(rehearsal):
    # ticket C7d-1: S3 is built and rehearsed; v2's example SX is rehearsed with a main-v2 smoke
    # (tests/test_execskill_sx_rehearsal.py)
    assert set(rehearsal["stages"]) == set(smoke.BUILT_STAGES) - {"SX"} and "SX" in smoke.BUILT_STAGES
    for stage, value in rehearsal["stages"].items():
        assert value["stage"] == stage and type(value["result"]["passed"]) is bool
        stored = read_json(rehearsal["root"] / smoke.STAGES_DIR / (stage + ".json"))
        assert stored[protocol.RECORD_HASH] == value[protocol.RECORD_HASH]
        assert stored["evidence"] == smoke.REHEARSAL_EVIDENCE  # registrar addendum 15:0x: a fixture, never smoke
    found = smoke.summary(rehearsal["spec"])
    assert found["evidence"] == smoke.REHEARSAL_EVIDENCE  # any rehearsal stage labels the result
    assert found["stages"]["S0"] == found["stages"]["S1"] == "pass" and found["required"] == list(smoke.SMOKE_STAGES)
    assert {found["stages"][s] for s in set(smoke.BUILT_STAGES) - {"SX"}} <= {"pass", "fail"} and "SX" not in found["stages"]
    assert found["stages"]["S3"] == "pass"  # every role ran through on the S3 rehearsal
    assert found["stages"]["S2"] == "fail" and found["passed"] is False  # S1 synthesized: S2's receipt row fails
    assert read_json(rehearsal["root"] / smoke.RESULT) == found


def test_s2_classes_production_receipts_and_settles_every_reservation(rehearsal):
    result = rehearsal["stages"]["S2"]["result"]
    counts = result["receipts"]["counts"]
    assert counts["production"] >= protocol.MIN_PRODUCTION_RECEIPTS and counts["unregistered"] == 0
    assert result["receipts"]["leaks"]["production"] == 0
    assert result["receipts"]["s1e_mismatch"] == []  # S1 synthesized: no probe attempt, so the receipt row fails
    assert result["rows"]["receipts"] is False and result["passed"] is False
    assert result["rows"]["ledger"] is True and result["rows"]["native_lock"] is True
    assert result["rows"]["leftovers"] is True
    assert set(result["format"]["shares"]) == {"searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld"}
    assert result["hooks_fired"]["applies"] >= 1 and result["alfworld"]["steps"] > 0
    crash = {item for items in fixtures.FX_CRASH_SUBSET.values() for item in items}
    assert result["procedure_faults"] and all(f["procedure"] == "fx-crash" and f["task_id"] in crash
                                              for f in result["procedure_faults"])
    assert result["rows"]["faults"] is True and result["rows"]["format"] is True


def test_s2_units_ran_the_registered_arms_and_the_confirmation_cell_first(rehearsal):
    units_root = rehearsal["root"] / smoke.UNITS_DIR / "S2"
    seen = {}
    for name in smoke.ITEM_SETS:
        unit = read_json(units_root / name / "unit.json")
        seen[name] = {cell["arm"] for cell in unit["result"]["cells"]}
    assert smoke.CONFIRM_ARM in seen["searchqa"]
    assert all({"C", "X", "P"} <= arms for arms in seen.values())
    assert any(arm.startswith("withhold:") for arm in seen["searchqa"] | seen["officeqa"])
    assert not any(arm.startswith("withhold:") for arm in seen["alfworld"])


def test_sn1_pairs_two_identical_card_arms(rehearsal):
    result = rehearsal["stages"]["SN1"]["result"]
    assert result["benches"]["searchqa"]["items"] == 200 and result["benches"]["alfworld"]["items"] == 6
    assert result["benches"]["searchqa"]["discordant"] == 0  # the same scripted reply twice


def test_a_real_stage_needs_both_credentials_named_and_a_recorded_stage_is_not_rerun(rehearsal):
    with pytest.raises(ValueError, match="names the elucid env path"):
        smoke.run_stage(rehearsal["root"] / smoke.SPEC, rehearsal["path"], "S2")
    with pytest.raises(ValueError, match="recorded"):
        smoke.run_stage(rehearsal["root"] / smoke.SPEC, rehearsal["path"], "SN1", fake=True)
    with pytest.raises(ValueError, match="not run by run_stage"):
        smoke.run_stage(rehearsal["root"] / smoke.SPEC, rehearsal["path"], "S0", fake=True)


def test_s4_pauses_on_the_drill_and_the_operator_recovery_redoes_the_round(rehearsal):
    stopped, root = rehearsal["stopped"], rehearsal["root"] / smoke.UNITS_DIR / smoke.S4_DIR
    accept = root / "s1-searchqa" / "accept"
    assert stopped["complete"] is False and stopped["stopped"] == "sandbox"
    assert "registered S4 drill" in stopped["reason"]
    assert stopped["paused"] == [str(accept / "attempt-1")]
    assert rehearsal["drill"][0]["by"] == "owner" and rehearsal["drill"][0]["decision"].startswith(smoke.SMOKE_LABEL)
    assert set(read_json(accept / "attempt-1" / "recovery.json")) == {"by", "date", "decision"}
    assert recovered(accept / "attempt-1")
    result = rehearsal["stages"]["S4"]["result"]
    assert result["rows"] == {row: True for row in smoke.S4_ROWS} and result["passed"] is True
    assert result["attempts"] == ["attempt-1", "attempt-2"] and result["drill"]["kind"] == "sandbox"
    # ticket C7c-2 (§9.3, owner decision #15): the drill stops inside block 1 of the round's 4 SearchQA blocks, so the
    # redo keeps nothing, redoes block 1 whole and runs blocks 2-4 in attempt-2; no attempt-1 cell is decided on
    blocks = ["b1", "b2", "b3", "b4"]
    assert result["blocks"] == blocks and result["drill"]["block"] == "b1"
    assert result["reused"] == {} and result["redone"] == ["b1"]
    assert result["provenance"] == {block: "attempt-2" for block in blocks}
    decision = read_json(accept / "attempt-2" / "decision" / "decision.json")
    assert {block: entry["attempt"] for block, entry in decision["provenance"].items()} == result["provenance"]
    assert sum(entry["cells"] for entry in decision["provenance"].values()) == result["cells"]
    assert result["astar"] == protocol.S4_SLICES["accept"] and result["twins"] > 0 and result["astar_small"] is False
    assert result["decision"] in ("accept", "reject")
    assert sorted(p.name for p in root.glob("confirm-*")) == ["confirm-1", "confirm-2"]  # one per process run
    entries = Registry(root / smoke.DRILL_HISTORY, evidence="smoke").entries(budgets.SMOKE, "searchqa")
    assert len(entries) == protocol.S4_SLICES["run"] + protocol.S4_SLICES["accept"]
    assert {line["purpose"] for line in entries.values()} == {"smoke"}
    history = Registry(rehearsal["tmp"] / "history", evidence="smoke")
    assert not history.consumed(budgets.SMOKE, "searchqa")  # the drill registry is the mini-step's own
    step = read_json(root / "s1-searchqa" / "step.json")
    assert step["chain"] == "smoke" and step["evidence"] == "smoke"
    assert set(step["units"]) == {"run", "accept", "freeze"}


def test_the_drill_recovery_is_written_only_into_a_paused_s4_attempt(rehearsal, tmp_path):
    spec, root = rehearsal["spec"], rehearsal["root"]
    with pytest.raises(ValueError, match="paused attempt of an S4 unit"):
        smoke.write_recovery(spec, root / smoke.UNITS_DIR / "S2" / "searchqa" / "attempt-1", decision="redo")
    with pytest.raises(ValueError, match="paused attempt of an S4 unit"):  # the unit completed
        smoke.write_recovery(spec, root / smoke.UNITS_DIR / smoke.S4_DIR / "s1-searchqa" / "accept" / "attempt-2",
                             decision="redo")
    with pytest.raises(ValueError):  # written once
        smoke.write_recovery(spec, rehearsal["stopped"]["paused"][0], decision="again")


def test_se6_projects_every_solver_scope_of_both_chains_at_the_maximum_schedule(rehearsal):
    result = rehearsal["stages"]["SE6"]["result"]
    caps = {**budgets.chain_caps("G"), **budgets.chain_caps("D")}
    solver = {name for name in caps if name != budgets.ROOT and not name.endswith(":glm") and ":role:" not in name}
    glm = {name for name in caps if name.endswith(":glm") or ":role:" in name}
    assert set(result["scopes"]) == solver and set(result["rows"]) == solver | glm | {"ratio"}
    assert set(result["not_projected"]) == {budgets.ROOT}
    # the ratio's denominator is every cell smoke:solver settled: S2's, S3's run unit and confirmation, S-N1's, S4's
    assert result["ledger"]["stages"] == ["S2", "SN1", "S4", "S3"]
    assert result["ratio"] == pytest.approx(1.0) and result["ratio_ok"] is True  # one attempt per fake send
    assert set(result["per_arm"]) == set(protocol.BENCHES) and set(result["request_bytes"]) == set(protocol.BENCHES)
    assert {"C", "X", "P"} <= set(result["per_arm"]["searchqa"])  # measured on S2's cells (SE6_CELLS)
    row = result["inputs"]["D:xs:officeqa:2:accept"]
    cells = protocol.MAX_SCHEDULE_CELLS["officeqa"]["accept"]["officeqa"]
    per = result["per_cell"]["officeqa"]
    assert row["cells"] == sum(cells) and row["per_cell"] * row["cells"] == pytest.approx(
        cells[0] * per["card"] + cells[1] * per["procedure"])
    assert row["reservation"] == 4 * (result["request_bytes"]["officeqa"] + 512 + result["bounds"]["D"]["officeqa"])
    assert result["inputs"]["G:test"]["reservation"] > result["inputs"]["D:test"]["reservation"] - 1  # B 65,536
    assert result["passed"] is all(result["rows"].values())


def test_se6_projects_every_glm_scope_from_s3s_measured_role_calls(rehearsal):
    """Registrar addendum 14:3x: S3's measured tokens per role call x the registered maximum role calls per step +
    one full next reservation (never below a full role input, 14:4x; on the engineer row, plus its system prompt,
    R7c), against every GLM scope of both chains; an excess fails S-E6."""
    result = rehearsal["stages"]["SE6"]["result"]
    s3 = rehearsal["stages"]["S3"]["result"]
    projected, measured = result["glm"]["scopes"], result["glm"]["measured"]
    assert set(measured) == set(budgets.ROLES) and result["glm"]["max_calls"] == smoke.MAX_ROLE_CALLS
    assert sum(entry["tokens"] for entry in measured.values()) == s3["glm"]["spent"]
    engineer = projected["D:xs:spreadsheetbench:1:role:engineer"]
    roles = ("engineer", "leakage", "describer")
    assert sorted(engineer["roles"]) == sorted(roles) and engineer["cap"] == protocol.ROLE_CAPS["engineer"]
    assert engineer["settled"] == math.ceil(sum(measured[r]["per_call"] * smoke.MAX_ROLE_CALLS[r] for r in roles))
    widest = max([measured[r]["request_bytes"] for r in roles] + [protocol.ROLE_INPUT_BYTES])  # 14:4x floor
    widest = max(widest, smoke.ENGINEER_REQUEST_FLOOR)  # R7 decision 16:1x (R7c): with the engineer's system prompt
    assert engineer["reservation"] == 4 * (widest + 512 + protocol.ROLE_MAX_TOKENS) >= 968_264
    assert result["glm"]["request_bytes_floor"] == protocol.ROLE_INPUT_BYTES
    research_ = projected["G:xs:officeqa:2:role:examiner:research"]
    assert research_["roles"] == ["examiner_research"] and research_["cap"] == protocol.ROLE_CAPS["examiner_research"]
    total = projected["G:glm"]
    steps = [entry for name, entry in projected.items() if name.startswith("G:xs:")]
    assert len(steps) == 3 * len(protocol.PILOTS[protocol.PILOT]["order"]) and total["cap"] == protocol.GLM_CAP
    assert total["settled"] == pytest.approx(sum(entry["settled"] for entry in steps), abs=len(steps))
    assert all(result["rows"][name] is entry["fits"] for name, entry in projected.items())


def test_m1_se6_projects_the_smoke_manifests_configuration_main_on_the_same_recorded_stages(rehearsal):
    """Registrar "Owner instructions 2026-10-22 17:0x and 17:3x": the smoke of the main experiment projects ``main``
    -- its five steps, its caps (3 x the need), its test read and its GLM scopes -- from the same S2 cells and S3 role
    calls (zero calls: S-E6 reads the recorded stages); the result names the configuration it projected."""
    m = manifest.load(rehearsal["path"], verify=False)
    default = smoke.se6_projection(rehearsal["spec"], m)
    found = smoke.se6_projection(rehearsal["spec"], {**m, "configuration": protocol.MAIN})
    assert (default["configuration"], default["pilot"]) == ("default", "default")
    assert (found["configuration"], found["pilot"]) == ("main", "main")
    assert found["ratio"] == default["ratio"] and found["per_cell"] == default["per_cell"]
    solver = {name for chain in protocol.CHAINS for name in budgets.chain_caps(chain, "main")
              if name != budgets.ROOT and not name.endswith(":glm") and ":role:" not in name}
    assert set(found["scopes"]) == solver and set(found["not_projected"]) == {budgets.ROOT}
    for k, bench in enumerate(protocol.BENCHES, 1):
        accept = budgets.solver_scopes("G", bench, k, "accept")[-1]
        cells = protocol.MAIN_SCHEDULE_CELLS[bench]["accept"][bench]
        assert found["inputs"][accept]["cap"] == protocol.MAIN_STEP_CAPS[bench]["accept"]
        assert found["inputs"][accept]["cells"] == sum(cells)
    assert found["inputs"]["D:test"]["cells"] == sum(card + proc for card, proc in protocol.TEST_READ_CELLS[
        "main"].values())
    assert found["inputs"]["G:solver"]["cap"] == protocol.PILOTS["main"]["solver_cap"]
    for chain in protocol.CHAINS:  # M2a #4: step 5's self-test runs the earlier sets, each cell priced by its bench
        cells = protocol.MAIN_SCHEDULE_CELLS["alfworld"]["selftest"]
        row = found["inputs"][budgets.solver_scopes(chain, "alfworld", 5, "selftest")[-1]]
        tokens = sum(card * found["per_cell"][b]["card"] + proc * found["per_cell"][b]["procedure"]
                     for b, (card, proc) in cells.items())
        assert sorted(cells) == sorted(protocol.BENCHES[1:]) and row["per_cell"] * row["cells"] == pytest.approx(tokens)
        assert row["reservation"] == max(reservation(found["request_bytes"][b], found["bounds"][chain][b])
                                         for b in cells)
    block = m["clients"]["solver"]["D"]  # chain D's own B per bench (its branch), chain G's 65,536
    assert found["bounds"]["D"] == {b: protocol.ledger_bound(protocol.CHAINS["D"], b, branch=block["branch"],
                                                             longest=block["longest"]) for b in protocol.BENCHES}
    glm = found["glm"]["scopes"]
    steps = [entry for name, entry in glm.items() if name.startswith("G:xs:")]
    assert len(steps) == 3 * len(protocol.BENCHES) and glm["G:glm"]["cap"] == protocol.MAIN_GLM_CAP
    assert glm["D:xs:alfworld:5:role:examiner:research"]["cap"] == 9_200_000
    assert glm["G:xs:searchqa:1:role:engineer"]["cap"] == glm["G:xs:searchqa:1:role:examiner"]["cap"] == 5_000_000
    assert found["passed"] is all(found["rows"].values())
    with pytest.raises(ValueError, match="run configuration"):
        smoke.se6_projection(rehearsal["spec"], {**m, "configuration": "pilot"})
