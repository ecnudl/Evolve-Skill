"""Authored ALF episodes exercise every consumer of the configuration-bound judge.

The 60-pair example reproduces counts in the brief, not the original games or
an independent effect experiment. No environment, model, Docker or network runs.
"""
from copy import deepcopy
from contextlib import contextmanager
from fractions import Fraction
import functools
import json

import pytest

from skillopt.coevo5.outcomes import Verdict
from skillopt.execskill import (acceptance, alfworld_format, detectors, evaluation, judge,
                               profiles as p, readout, smoke, stats_ext, step, confirm)
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


CONFIGURATIONS = ("alfworld-v9", "alfworld-v10")
EXPECTED = {"alfworld-v9": {"S": 10, "S'": 20}, "alfworld-v10": {"S": 0, "S'": 0}}


def episode(configuration, admissible, *, won=True, steps=8, invalid=False):
    prediction = {"status": "unavailable" if invalid else "available",
                  "output": None if invalid else {"won": won, "steps": steps},
                  "reason": "invalid_action_format" if invalid else "fresh_native_episode_completed",
                  "costs": {"calls": steps},
                  "shell": {"deciding_receipt": None, "alfworld_steps": [
                      {"how": "tag_exact" if n < admissible else "unchanged"} for n in range(steps)]}}
    runtime = alfworld_format.bind({}, configuration)
    token = "pass" if won and not invalid else "fail"
    scored = {"status": token, "reason": "authored_episode"}
    verdict = (Verdict(token, "malformed", "invalid_action_format", "6") if invalid else
               Verdict(token, "scored", "authored_episode", "10"))
    judged = judge.judge("alfworld", {"game_file": "authored-in-memory"}, {}, prediction,
                         runtime=runtime, score=scored, verdict=verdict)
    return judged, prediction, runtime, scored, verdict


def cell(configuration, arm, index, admissible, won):
    judged, prediction, runtime, scored, verdict = episode(configuration, admissible, won=won)
    key = "episode-%02d" % index
    return {"cell": {"id": arm + "/" + key, "arm": arm, "task_id": key, "run": 0},
            "judge": judged, "final": {**verdict.__dict__, "token": verdict.token},
            "prediction": prediction, "runtime": runtime, "score": scored,
            "faults": [], "sends": [], "stop": None}


def training_case(configuration, *, count=60):
    """S: three severe + seven mild; S': one severe + nineteen mild.

    Old violating sets are nested, so the self-test also has ten worsening
    pairs. Wins are independent of action admissibility: exactly 11 fixes and
    two breaks. Confirmation uses the first 40 pairs with these same counts.
    """
    cells = {}
    for index in range(count):
        for arm in ("S", "S'"):
            severe, bad = (3, 10) if arm == "S" else (1, 20)
            admissible = 3 if index < severe else 7 if index < bad else 8
            won = index >= 11 if arm == "S" else (index < 11 or index >= 13)
            row = cell(configuration, arm, index, admissible, won)
            cells[(arm, row["cell"]["task_id"])] = [row]
    ids = sorted({key for _, key in cells})
    return cells, ids


def acceptance_case(configuration):
    """150 authored pairs match the final v7 acceptance counts, never its data."""
    ids = ["episode-%02d" % index for index in range(150)]
    wins = {"S": set(range(86)), "C": set(range(86)), "P_y": set(range(88)),
            "S'": (set(range(86)) - set(range(8))) | set(range(86, 98))}
    counts = {"S": (19, 18, 1), "C": (18, 22, 6), "P_y": (19, 27, 8), "S'": (19, 25, 5)}
    cells = {}
    for arm, won in wins.items():
        won_bad, lost_bad, severe_count = counts[arm]
        bad = set(sorted(won)[:won_bad]) | set(sorted(set(range(150)) - won)[:lost_bad])
        severe = set(sorted(bad)[:severe_count])
        for index, key in enumerate(ids):
            admissible = 3 if index in severe else 7 if index in bad else 8
            cells[(arm, key)] = [cell(configuration, arm, index, admissible, index in won)]
    return cells, ids


def train(cells, ids, configuration):
    return step.train_verdict(cells, ids, [], set(), predicate_faults=0,
                              routed=len(ids), sign=False, configuration=configuration)


def flat(cells):
    return [row for rows in cells.values() for row in rows]


def traces(cells):
    return {row["cell"]["id"]: {"cell": row["cell"]["id"], "task_id": row["cell"]["task_id"],
            "bench": "alfworld", "arm_kind": "candidate" if row["cell"]["arm"] == "S'" else "parent",
            "alfworld_steps": [{"notes": "Authored public note."}], "replies": ["<action>look</action>"]}
            for row in flat(cells)}


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_training_replayed_counts_adopt_only_with_readable_action_rule(configuration):
    cells, ids = training_case(configuration)
    found = train(cells, ids, configuration)
    assert len(found["fixed"]) == 11 and len(found["broken"]) == 2 and found["net"] == "9/1"
    assert found["format_cells"] == EXPECTED[configuration]
    if configuration == "alfworld-v10":
        assert {arm: sum(row["judge"]["format"]["violation_at_9_10"]
                        for (side, _), rows in cells.items() if side == arm for row in rows)
                for arm in ("S", "S'")} == {"S": 10, "S'": 20}
        assert {arm: sum(row["judge"]["format"]["violation_below_half"]
                        for (side, _), rows in cells.items() if side == arm for row in rows)
                for arm in ("S", "S'")} == {"S": 3, "S'": 1}
    assert found["format_margin"] == 2 and all(found["gain"].values())
    assert found["adopted"] is (configuration == "alfworld-v10")
    assert found["reason"] == (None if configuration == "alfworld-v10" else "guard:format")


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_confirmation_equivalent_uses_same_judge_counts_and_unchanged_margin(configuration):
    cells, ids = training_case(configuration, count=40)
    found = confirm.verdict(cells, ids)
    assert found["items"] == found["evaluated"] == 40
    assert (found["fixed"], found["broken"], found["net"]) == (11, 2, 9)
    assert found["format_cells"] == EXPECTED[configuration] and found["format_margin"] == 2
    assert found["passed"] is (configuration == "alfworld-v10")
    assert found["reason"] == (None if configuration == "alfworld-v10" else "guard:format")


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_selftest_equivalent_keeps_exact_sign_test_and_format_margin(configuration):
    cells, ids = training_case(configuration)
    found = step.selftest_verdict(flat(cells), {"alfworld": ids}, set(), configuration=configuration)
    row = found["sets"]["alfworld"]
    assert found["fault_cells"] == 0 and not found["fault_blocks"]
    if configuration == "alfworld-v10":
        assert (row["worse"], row["better"], row["format_gap"]) == (0, 0, 0)
        assert not row["blocks"] and not found["blocked"]
    else:
        assert (row["worse"], row["better"], row["format_gap"]) == (10, 0, 10 / 60)
        assert row["p_sign"] == 1 / 1024 and row["blocks"] and found["blocked"]
    assert p.SELFTEST_FORMAT_MARGIN == Fraction(1, 20) and p.SELFTEST_ALPHA == .05


def smoke_case(cells, tmp_path):
    rows = [smoke._summary_of({}, tmp_path, row, stage="S2", bench="alfworld", nominal=1, bound=1)
            for row in flat(cells)]
    compliant = {arm: [not row["violation"] for row in rows if row["arm"] == source]
                 for arm, source in (("C", "S"), ("X", "S'"), ("P", "S'"))}
    return smoke.format_check({"alfworld": compliant}), rows


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_smoke_stage_summary_and_format_shares_use_the_same_judgment(configuration, tmp_path):
    cells, _ = training_case(configuration)
    found, summaries = smoke_case(cells, tmp_path)
    assert len(summaries) == 120
    assert {arm: sum(row["violation"] for row in summaries if row["arm"] == arm)
            for arm in ("S", "S'")} == EXPECTED[configuration]
    assert found["shares"]["alfworld"] == ({"C": "1/1", "X": "1/1", "P": "1/1"}
        if configuration == "alfworld-v10" else {"C": "5/6", "X": "2/3", "P": "2/3"})
    assert found["passed"] is (configuration == "alfworld-v10")
    assert p.SMOKE_FORMAT_FLOOR == Fraction(9, 10) and p.SMOKE_FORMAT_MARGIN == Fraction(1, 20)


def j4(cells, ids):
    records = [{**row, **row["cell"], "set": "real"} for row in flat(cells)]
    counts = {arm: len(acceptance._violating(records, arm, ids)) for arm in ("S", "S'")}
    margin = p.format_margin(len(ids))
    return {**counts, "margin": margin, "ok": counts["S'"] <= counts["S"] + margin}


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_j4_equivalent_counts_items_from_judge_and_preserves_its_margin(configuration):
    cells, ids = training_case(configuration)
    found = j4(cells, ids)
    assert found == {**EXPECTED[configuration], "margin": 2, "ok": configuration == "alfworld-v10"}
    # Multiple logged runs never turn J4 into a cell-count guard.
    duplicated = {key: rows + deepcopy(rows) for key, rows in cells.items()}
    assert j4(duplicated, ids) == found
    assert p.FORMAT_MARGIN_MIN == 2 and p.FORMAT_MARGIN_SHARE == Fraction(1, 50)


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_full_alf_acceptance_decision_j4_uses_configuration_bound_judges(configuration, tmp_path, monkeypatch):
    from skillopt.execskill.package import empty, with_
    from tests.execskill_fakes_env import FakeSandbox, procedure
    # This authored plan exercises the production ALF room-clustered decision,
    # with in-process workers and fewer descriptive resamples for test speed.
    monkeypatch.setattr(stats_ext, "signflip", functools.partial(stats_ext.signflip, n=200))
    monkeypatch.setattr(stats_ext, "bootstrap_ci", functools.partial(stats_ext.bootstrap_ci, resamples=50))
    parent = empty(step="D/s0", evidence="engineering_fixture")
    proc = procedure("fx-alf-format", ("applies", "alf_before_step"), origin="alfworld")
    candidate = with_(parent, step="D/s1-alfworld", add=[proc])
    hooks = {proc.id: {"applies": lambda view: True,
                       "alf_before_step": lambda view, state: {"fields": {"facts": ["Authored public note."]},
                                                                "discourage": []}}}
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind="cell")
        try:
            yield worker
        finally:
            worker.close()
    paired, ids = acceptance_case(configuration)
    passed = lambda arm, key: paired[(arm, key)][0]["judge"]["v2"]["token"] == "pass"
    assert sum(passed("S'", key) and not passed("S", key) for key in ids) == 12
    assert sum(passed("S", key) and not passed("S'", key) for key in ids) == 8
    views = {key: {"task_text": "Inspect the authored room.", "initial_observation": "Authored room.",
                   "admissible_commands_at_reset": ["look"]} for key in ids}
    rooms = {key: "room-%02d" % (index % 40) for index, key in enumerate(ids)}
    blocks = {key: "block-%d" % ((index % 40) // 10) for index, key in enumerate(ids)}
    trajectories = [{"bench": "alfworld", "arm_kind": "parent", "cell": "donor-%02d" % index,
                     "task_id": "donor-%02d" % index,
                     "calls": [{"purpose": "step", "user": json.dumps({"step": 0,
                         "initial_observation": "Authored room.", "observation": "Authored room.",
                         "admissible_commands": ["look"]})}],
                     "alfworld_steps": [{"action": "look"}], "shell": {}}
                    for index in range(12)]
    sealed = acceptance.prepare(tmp_path / "acceptance", chain="D", bench="alfworld", step="D/s1-alfworld",
        unit="D/s1-alfworld/accept", candidate=candidate, parent=parent, views=views, blocks=blocks,
        rooms=rooms, workers=workers, trajectories=trajectories, configuration=configuration,
        freshness=p.ACCEPT_FRESHNESS[configuration], rule=p.ACCEPT_RULES[configuration])
    assert len(sealed["plan"]["astar"]) == 150 and sealed["plan"]["astar_rooms"] == 40
    records = []
    for block in acceptance.schedule(sealed).values():
        for job in block:
            source = job["arm"] if job["arm"] in ("S'", "S", "C", "P_y") else "S"
            judged = deepcopy(paired[(source, job["item"])][0]["judge"])
            records.append({"arm": job["arm"], "task_id": job["item"], "run": job["run"], "set": job["set"],
                "judge": judged, "faults": [], "logical_calls": [{"purpose": "first"}],
                "worst_delivery": "delivered", "sends": [{"receipt": {"ok": True}}],
                "dispatch_ts": float(len(records)), "finish_ts": float(len(records)) + .5})
    found = acceptance.decide(records, sealed)
    assert found["bench"] == "alfworld" and found["configuration"] == configuration
    assert found["guards"]["J4_items"] == {"S": 0 if configuration == "alfworld-v10" else 37,
        "S'": 0 if configuration == "alfworld-v10" else 44, "margin": 3, "ok": configuration == "alfworld-v10"}
    assert found["contrasts"]["S'-S"]["whole_batch"] == pytest.approx(4 / 150)
    assert p.ACCEPT_RULES[configuration]["gain_points"] == 5
    assert not found["guards"]["J1"]["ok"]
    assert found["decision"] == "reject" and "J1" in found["reason"]
    if configuration == "alfworld-v9":
        assert "J4" in found["reason"]
    else:
        assert "J4" not in found["reason"]
        for arm, old, half, won, won_bad in (("S", 37, 1, 86, 19), ("C", 40, 6, 86, 18),
                                           ("P_y", 46, 8, 88, 19), ("S'", 44, 5, 90, 19)):
            rows = [paired[(arm, key)][0]["judge"] for key in ids]
            assert sum(row["v2"]["token"] == "pass" for row in rows) == won
            assert sum(row["format"]["violation_at_9_10"] for row in rows) == old
            assert sum(row["format"]["violation_below_half"] for row in rows) == half
            assert sum(row["format"]["violation_at_9_10"] and row["v2"]["token"] == "pass"
                       for row in rows) == won_bad
    for row in records:
        if "violation_at_9_10" in row["judge"]["format"]:
            row["judge"]["format"]["violation_at_9_10"] = not row["judge"]["format"]["violation_at_9_10"]
            row["judge"]["format"]["violation_below_half"] = not row["judge"]["format"]["violation_below_half"]
    assert acceptance.decide(records, sealed)["guards"] == found["guards"]


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_format_feedback_lists_only_new_violations_under_its_run_rule(configuration):
    cells, ids = training_case(configuration)
    verdict = train(cells, ids, configuration)
    feedback = step._format_feedback(cells, traces(cells), set(ids), verdict, "v296-authored")
    assert {key: feedback[key] for key in ("S", "S'")} == EXPECTED[configuration]
    assert feedback["margin"] == 2 and feedback["blocked"] is (configuration == "alfworld-v9")
    if configuration == "alfworld-v10":
        assert feedback["examples"] == []
    else:
        assert len(feedback["examples"]) == 2
        assert all(row["task_id"] in ids[10:20] for row in feedback["examples"])
        assert all(row["notes"] == "Authored public note." for row in feedback["examples"])


@pytest.mark.parametrize("admissible,invalid,expected", [(0, False, False), (3, False, False),
                                                      (4, False, False), (7, False, False), (8, True, True)])
def test_new_feedback_rule_lists_only_unreadable_action_examples(admissible, invalid, expected):
    cells = {(arm, "episode-00"): [cell("alfworld-v10", arm, 0, 8 if arm == "S" else admissible, True)]
             for arm in ("S", "S'")}
    if invalid:
        cells[("S'", "episode-00")][0]["judge"] = episode("alfworld-v10", admissible, invalid=True)[0]
    ids = ["episode-00"]
    feedback = step._format_feedback(cells, traces(cells), set(ids), train(cells, ids, "alfworld-v10"), "case")
    assert bool(feedback["examples"]) is expected
    if expected:
        assert feedback["examples"][0]["task_id"] == ids[0]
        assert json.loads(feedback["examples"][0]["detail"])["violation"] is True


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_stage_and_test_tables_report_deciding_and_historical_fields_separately(configuration):
    cells, _ = training_case(configuration)
    values = {(arm, key, 0): {"v2": row["judge"]["v2"]["token"],
              "format": row["judge"]["format"], "shared_with": None, "enabled": [], "flags": []}
              for (arm, key), (row,) in cells.items()}
    table = readout.arm_table(values)
    for arm in ("S", "S'"):
        assert table[arm]["format"].get("violation", 0) == EXPECTED[configuration][arm]
        if configuration == "alfworld-v10":
            assert table[arm]["format"]["violation_at_9_10"] == EXPECTED["alfworld-v9"][arm]
            assert table[arm]["format"]["violation_below_half"] == {"S": 3, "S'": 1}[arm]
        else:
            assert "violation_at_9_10" not in table[arm]["format"]


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_sealed_evaluation_carries_the_actual_judge_format_without_reinterpreting(configuration):
    row = cell(configuration, "F", 0, 7, True)
    full = p.record("cell", "engineering_fixture", {**row, "configuration": configuration,
        "arm_kind": "candidate", "package_sha256": "a" * 64, "enabled": [], "withheld": [], "restored": [],
        "logical_calls": [], "deciding_receipt": None, "worst_delivery": "no_call", "fault_kinds": {},
        "shared_with": None, "dispatch_ts": 1., "finish_ts": 2., "keyword_hits": [], "applies": [],
        "returned_model": None, "returned_models": []})
    sealed = evaluation.sealed_cell(full)
    assert sealed["configuration"] == configuration
    assert sealed["judge"]["format"] == row["judge"]["format"]
    assert sealed["judge"]["format"]["violation"] is (configuration == "alfworld-v9")


def test_historical_verdict_is_reporting_only_for_all_decisions(tmp_path):
    cells, ids = training_case("alfworld-v10")
    def decisions(rows):
        verdict = train(rows, ids, "alfworld-v10")
        return (verdict, confirm.verdict(rows, ids, items=60),
                step.selftest_verdict(flat(rows), {"alfworld": ids}, set(), configuration="alfworld-v10"),
                j4(rows, ids), smoke_case(rows, tmp_path)[0],
                step._format_feedback(rows, traces(rows), set(ids), verdict, "reporting-only"))
    expected = decisions(cells)
    for row in flat(cells):
        row["judge"]["format"]["violation_at_9_10"] = not row["judge"]["format"]["violation_at_9_10"]
        row["judge"]["format"]["violation_below_half"] = not row["judge"]["format"]["violation_below_half"]
    assert decisions(cells) == expected
    for row in flat(cells):
        del row["judge"]["format"]["violation_at_9_10"]
        del row["judge"]["format"]["violation_below_half"]
    assert decisions(cells) == expected


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_offline_rejudging_json_roundtripped_records_reuses_the_pinned_runtime(configuration, tmp_path):
    judged, prediction, runtime, scored, verdict = episode(configuration, 7)
    path = tmp_path / "stored-authored-episode.json"
    path.write_text(json.dumps({"prediction": prediction, "runtime": runtime, "score": scored,
                               "verdict": verdict.__dict__, "judge": judged}))
    stored = json.loads(path.read_text())
    found = judge.judge("alfworld", {"game_file": "authored-in-memory"}, {}, stored["prediction"],
                        runtime=stored["runtime"], score=stored["score"], verdict=Verdict(**stored["verdict"]))
    assert found == stored["judge"]
    assert found["format"]["violation"] is (configuration == "alfworld-v9")


@pytest.mark.parametrize("invalid_count", [3, 6, 7])
def test_readable_action_rule_keeps_format_guards_and_their_original_thresholds(tmp_path, invalid_count):
    cells, ids = training_case("alfworld-v10")
    # Keep positive gains but add malformed replies, including exactly 3/60.
    for index in range(20, 20 + invalid_count):
        cells[("S'", ids[index])][0]["judge"] = episode("alfworld-v10", 8, invalid=True)[0]
    trained = train(cells, ids, "alfworld-v10")
    assert trained["format_cells"] == {"S": 0, "S'": invalid_count}
    assert all(trained["gain"].values()) and trained["reason"] == "guard:format"
    assert confirm.verdict(cells, ids, items=60)["reason"] == "guard:format"
    found = step.selftest_verdict(flat(cells), {"alfworld": ids}, set(), configuration="alfworld-v10")
    assert found["sets"]["alfworld"]["p_sign"] == 1 / 2 ** invalid_count
    assert found["blocked"] is (invalid_count >= 6)
    assert not j4(cells, ids)["ok"]
    assert smoke_case(cells, tmp_path)[0]["passed"] is (invalid_count == 3)
    feedback = step._format_feedback(cells, traces(cells), set(ids), trained, "malformed-only")
    assert feedback["blocked"] and len(feedback["examples"]) == 2
    assert all(row["task_id"] in ids[20:20 + invalid_count] for row in feedback["examples"])


@pytest.mark.parametrize("admissible,diagnosed,violation", [(8, False, False), (7, True, False),
                                                         (5, True, False), (4, True, False)])
def test_diagnosis_keeps_its_independent_strict_one_fifth_threshold(admissible, diagnosed, violation):
    judged, prediction, *_ = episode("alfworld-v10", admissible, steps=10)
    trajectory = {"alfworld_steps": prediction["shell"]["alfworld_steps"]}
    assert detectors.MECHANICAL["alfworld"]["inadmissible_share>0.2"](trajectory) is diagnosed
    assert judged["format"]["violation"] is violation
