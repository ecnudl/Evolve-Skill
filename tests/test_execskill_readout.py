"""T-READ-1 (implementation plan §8.1; registration §8.2; Codex F2, F20, F21): Q1 with Holm over |L|, Q2 descriptive,
Q3 against −5 points under both readings, the code-vs-text interval readings (else "inconclusive") and the label
priority table applied as descriptors. Synthetic unsealed cells only (the shape ``evaluation.unseal`` returns)."""
from __future__ import annotations

import pytest

from skillopt.execskill import readout
from skillopt.execskill.protocol import TIME_WINDOW_SECONDS, verified

N = 40
LEARNED = ("spreadsheetbench", "officeqa")
PROCEDURES = {"p-officeqa-1-1": "officeqa", "p-spreadsheetbench-1-1": "spreadsheetbench",
              "p-officeqa-1-2": "officeqa", "p-spreadsheetbench-1-2": "spreadsheetbench", "p-officeqa-1-3": "officeqa"}
P1, P2, P3, P4, P5 = PROCEDURES


def cell(token, *, enabled=(), block="b1", violation=False, room=None, shared_with=None):
    return {"v2": token, "token": token, "kind": None, "shared_with": shared_with, "answered": token != "unknown",
            "enabled": list(enabled), "block": block, "room": room, "format": {"violation": violation}, "flags": []}


def bench(f, c, t, *, twins=(), enabled=lambda i: (), rooms=None):
    """One bench's unsealed cells: tokens of F, C, T_F per item i; ``twins``: (procedure, items, token(i));
    ``rooms``: room(i) on ALFWorld (the read's clusters)."""
    cells = {}
    for i in range(N):
        item = "item-%02d" % i
        room = None if rooms is None else rooms(i)
        cells[("F", item, 0)] = cell(f(i), enabled=enabled(i), room=room)
        cells[("C", item, 0)] = cell(c(i), room=room)
        cells[("T_F", item, 0)] = cell(t(i), room=room)
        cells[("P_F", item, 0)] = cell(c(i), room=room)
    for procedure, items, token in twins:
        for i in items:
            cells[("withhold:" + procedure, "item-%02d" % i, 0)] = cell(token(i), violation=token(i) == "fail",
                                                                       room=None if rooms is None else rooms(i))
    return cells


def room_of(i):
    return "room-%d" % (i // 4)


def lost(i):  # a twin that loses the procedure fails on three quarters of its items
    return "pass" if i % 4 == 3 else "fail"


def units():
    officeqa = bench(lambda i: "pass", lambda i: "fail" if i % 2 == 0 else "pass",
                     lambda i: "fail" if i % 2 == 0 else "pass",
                     twins=[(P1, range(20), lost), (P3, range(20, 40), lost), (P5, range(10), lambda i: "pass")],
                     enabled=lambda i: [p for p, on in ((P1, i < 20), (P3, i >= 20), (P5, i < 10)) if on])
    sheet = bench(lambda i: "pass", lambda i: "fail" if i % 2 == 0 else "pass", lambda i: "pass",
                  twins=[(P2, range(20), lambda i: "pass"), (P4, range(20, 40), lost)],
                  enabled=lambda i: [P2] if i < 20 else [P4])
    alf_f = {i: ("fail" if i < 20 and i % 4 != 3 else "pass") for i in range(N)}
    alfworld = bench(lambda i: alf_f[i], lambda i: "pass", lambda i: alf_f[i],
                     twins=[(P1, range(20), lambda i: "pass"), (P2, range(20, 40), lambda i: alf_f[i])],
                     enabled=lambda i: [P1] if i < 20 else [P2], rooms=room_of)
    sq_f = {i: ("fail" if 30 <= i < 35 else "pass") for i in range(N)}
    searchqa = bench(lambda i: sq_f[i], lambda i: "pass",
                     lambda i: "pass" if 30 <= i < 35 else ("fail" if i >= 35 else sq_f[i]),
                     twins=[(P2, range(20), lost), (P5, range(20, 30), lambda i: sq_f[i])],
                     enabled=lambda i: [P2] if i < 20 else ([P5] if i < 30 else []))
    return {"officeqa": officeqa, "spreadsheetbench": sheet, "alfworld": alfworld, "searchqa": searchqa}


def test_read1_label_priority_is_a_primary_label_with_every_holding_descriptor():
    found = readout.labels(units(), PROCEDURES)
    assert found[P1]["label"] == "harmful_elsewhere"
    assert found[P1]["descriptors"] == ["harmful_elsewhere", "home_benefit_established"]
    assert found[P2]["label"] == "general" and "harmful_elsewhere" not in found[P2]["descriptors"]
    assert found[P3]["label"] == "home_benefit_established"
    assert found[P3]["descriptors"] == ["home_benefit_established", "cannot_act_elsewhere"]
    assert found[P4]["descriptors"] == ["home_benefit_established", "cannot_act_elsewhere"]
    assert found[P5]["label"] == "no_measurable_effect" and found[P5]["descriptors"] == ["no_measurable_effect"]
    assert found[P1]["tau"]["alfworld"]["tau"] < 0 < found[P1]["tau"]["officeqa"]["tau"]
    assert found[P3]["enable_rate"]["alfworld"] == 0 and found[P2]["enable_rate"]["searchqa"] == 0.5


def test_read1_holm_over_the_family_can_remove_a_marginal_statement():
    cells = units()
    # one weak positive tau on searchqa for P5: d = 1 on 3 of 10 twin items -- alone p < 2.5 %, not after Holm
    for i in range(20, 23):
        cells["searchqa"][("withhold:" + P5, "item-%02d" % i, 0)]["v2"] = "fail"
    alone = readout.labels({"searchqa": cells["searchqa"]}, {P5: "officeqa"})
    together = readout.labels(cells, PROCEDURES)
    assert "general" not in together[P5]["descriptors"]
    assert alone[P5]["tau"]["searchqa"]["tau"] == together[P5]["tau"]["searchqa"]["tau"] == 0.3


def test_read1_q1_q2_q3_and_the_evidence_wording():
    found = verified(readout.readout(units(), learned=LEARNED, procedures=PROCEDURES,
                                     label="interim_read_addendum_before_unseal", evidence="engineering_fixture"),
                     "readout")
    assert found["evidence_kind"] == "generalization" and found["read_label"].startswith("interim")
    q1 = found["q1_home"]
    assert set(q1) == set(LEARNED) and all(q1[b]["established"] and q1[b]["mean"] == 0.5 for b in LEARNED)
    assert q1["officeqa"]["p_holm"] >= q1["officeqa"]["p_t"] and "p_signflip" in q1["officeqa"]["sensitivity"]
    assert found["similar"] == ["searchqa", "livemath"] and found["dissimilar"] == ["alfworld"]
    q2 = found["q2_similar"]
    assert set(q2) == {"searchqa"} and q2["searchqa"]["reading"] == "descriptive"
    assert q2["searchqa"]["tau"][P2]["tau"] == 0.75 and "established" not in q2["searchqa"]
    q3 = found["q3_noninferiority"]
    assert q3["benches"] == ["alfworld"] and q3["reading"] == "noninferiority_not_established"


def test_read1_q3_needs_both_readings_and_reports_cannot_act_by_construction():
    def alf(f, enabled):
        return {"alfworld": bench(f, lambda i: "pass", lambda i: "pass", enabled=enabled, rooms=room_of)}

    unknown = alf(lambda i: "unknown" if i < 6 else "pass", lambda i: ["p"])  # adverse fails, complete case holds
    found = readout.q3_noninferiority(unknown, LEARNED)
    assert found["complete_case"]["lower95_one_sided"] > -0.05 > found["adverse"]["lower95_one_sided"]
    assert found["reading"] == "noninferiority_not_established"
    assert readout.q3_noninferiority(alf(lambda i: "pass", lambda i: ["p"]), LEARNED)["reading"] == \
        "noninferiority_established"
    rare = alf(lambda i: "pass", lambda i: ["p"] if i < 3 else [])  # enabled on 3 of 40 items: < 10 %
    assert readout.q3_noninferiority(rare, LEARNED) == {"benches": ["alfworld"], "enable_rate": 3 / 40,
                                                        "reading": "cannot_act_by_construction"}


def test_read1_code_vs_text_readings_only_from_the_registered_bounds():
    found = readout.code_vs_text(units(), LEARNED)
    assert found["officeqa"]["readings"] == ["code_better"]
    assert found["spreadsheetbench"]["readings"] == ["inconclusive"]  # home: a zero difference reads nothing
    assert found["alfworld"]["readings"] == ["code_transfer_not_worse", "text_transfer_not_worse"]
    assert found["searchqa"]["readings"] == ["inconclusive"] and found["searchqa"]["mean"] == 0
    assert all(v.get("estimand") in (None, "difference_of_the_two_implementations") for v in found.values())


def test_read1_format_withholding_counts_violations_with_and_without():
    found = readout.format_withholding(units(), PROCEDURES)
    assert found[P1]["officeqa"] == {"n": 20, "violations_with": 0, "violations_without": 15}
    assert found[P4] == {"spreadsheetbench": {"n": 20, "violations_with": 0, "violations_without": 15}}


def test_read1_inputs_are_checked():
    with pytest.raises(ValueError):
        readout.q1_home(units(), ("livemath",))


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def shared_bench(n, unknown, *, enabled_items=0, rooms=None):
    """``n`` items; F enables a procedure on the first ``enabled_items`` (its own cells, passing like C) and nothing
    elsewhere, where F, P_F and T_F share C's cell (§8.1); C is unknown (undelivered) on ``unknown`` shared items."""
    cells = {}
    for i in range(n):
        item = "item-%03d" % i
        room = None if rooms is None else rooms(i)
        own = i < enabled_items
        token = "unknown" if not own and i - enabled_items < unknown else "pass"
        cells[("C", item, 0)] = cell(token, room=room)
        for arm in ("F", "P_F", "T_F"):
            cells[(arm, item, 0)] = cell("pass" if own else token, room=room, enabled=["p"] if own and arm == "F"
                                         else (), shared_with=None if own else "C-cell-%03d" % i)
    return cells


def test_statistics_1_a_shared_cell_is_one_outcome_never_scored_on_both_sides():
    # statistics review probe 4: 134 identical items, nothing enabled, 4 shared unknown cells
    units = {"alfworld": shared_bench(134, 4, rooms=lambda i: "room-%d" % (i // 6))}
    found = readout.code_vs_text(units, LEARNED)["alfworld"]
    assert found["mean"] == 0 and found["readings"] == ["cannot_act_by_construction"]
    # F enabled on half, 4 shared unknown cells among the structural zeros: their differences are 0, not -1
    units = {"searchqa": shared_bench(40, 4, enabled_items=20)}
    assert readout.differences(units["searchqa"], "F", "C", ["item-%03d" % i for i in range(40)]) == [0] * 40
    found = readout.code_vs_text(units, LEARNED)["searchqa"]
    assert found["mean"] == 0 and "text_better" not in found["readings"]
    assert readout.placebo_contrast(units)["searchqa"]["mean"] == 0


def test_statistics_1_the_shared_unanswered_mask_leaves_every_contrast():
    cells = bench(lambda i: "pass", lambda i: "pass", lambda i: "pass")
    for arm in ("F", "C", "T_F", "P_F"):  # item-00: no arm got any reply
        cells[(arm, "item-00", 0)] = cell("unknown")
    assert readout.unanswered(cells) == ["item-00"]
    assert readout.q1_home({"officeqa": cells, "spreadsheetbench": cells}, LEARNED)["officeqa"]["n"] == N - 1
    cells[("C", "item-00", 0)]["answered"] = True  # a delivered reply judged unknown is no shared-unanswered item
    assert readout.unanswered(cells) == []


def test_statistics_7_alfworld_contrasts_are_room_clustered():
    units = {"alfworld": bench(lambda i: "pass" if i % 3 else "fail", lambda i: "pass", lambda i: "pass",
                               enabled=lambda i: ["p"], rooms=room_of)}
    found = readout.code_vs_text(units, LEARNED)["alfworld"]
    assert found["rooms"] == N // 4 and found["df"] == N // 4 - 1 and found["n"] == N
    unclustered = bench(lambda i: "pass", lambda i: "pass", lambda i: "pass", enabled=lambda i: ["p"])
    with pytest.raises(ValueError, match="rooms"):
        readout.code_vs_text({"alfworld": unclustered}, LEARNED)


def test_statistics_5_the_arm_table_reports_next_to_every_accuracy():
    cells = bench(lambda i: "pass" if i % 2 else "unknown", lambda i: "pass", lambda i: "pass",
                  enabled=lambda i: ["p"] if i < 10 else [])
    for n, ((arm, item, run), value) in enumerate(sorted(cells.items())):
        value.update(official="pass", final="pass" if value["v2"] == "pass" else "unknown", lenient=True,
                     fault_kinds={"timeout": 1} if arm == "F" and item == "item-01" else {},
                     dispatch_ts=float(n * 60), completion_tokens=[100 + n % 7],
                     flags=["over_nominal"] if value["v2"] == "unknown" else [],
                     format={"violation": False, "tag_present": value["v2"] == "pass"})
    table = readout.arm_table(cells)["F"]
    assert table["period"] == "this_period" and table["cells"] == N and table["v2"] == 0.5
    assert table["official"] == 1 and table["official_completion"] == 0.5 and table["lenient"] == 1
    assert table["unknown"] == {"unknown": N // 2} and table["flags"] == {"over_nominal": N // 2}
    assert table["faults"] == {"timeout": 1} and table["fault_cells"] == 1 and table["enable_rate"] == 0.25
    assert sum(w["cells"] for w in table["windows"]) == N and all(w["mean_completion_tokens"] for w in table["windows"])


# ------------------------------------------------------- ticket fixer-2: the short answer (registrar decision 10/22)
def windowed(rows):
    """One bench's unsealed cells from rows (arm, window, the completion tokens of each logical call[, shared_with]),
    each dispatched inside its 15-minute window counted from the unit's first dispatch (row 0, at 0 s)."""
    cells = {}
    for n, (arm, window, tokens, *shared) in enumerate(rows):
        value = cell("pass", shared_with=shared[0] if shared else None)
        value.update(dispatch_ts=float(window * TIME_WINDOW_SECONDS + n), completion_tokens=tokens,
                     format={"violation": False, "tag_present": True})
        cells[(arm, "item-%03d" % n, 0)] = value
    return cells


def shares(table, arm):
    return [(w["window"], w["short_answer_share"]) for w in table[arm]["windows"]]


def test_fixer_2_a_short_answer_is_below_a_quarter_of_its_arms_first_window_median():
    table = readout.arm_table(windowed(
        [("C", 0, [400]), ("C", 0, [400]), ("C", 0, [380]), ("C", 0, [420]), ("C", 0, [100]),
         ("F", 0, [200]), ("F", 0, [200]), ("F", 0, [180]), ("F", 0, [220]),
         ("C", 1, [12]), ("C", 1, [12]), ("C", 1, [99]), ("C", 1, [400]),
         ("F", 1, [60]), ("F", 1, [49]), ("F", 1, [210])]))
    assert table["C"]["short_answer_reference"] == {"window": 0, "cells": 5, "no_usage": 0, "median": 400.0,
                                                    "status": "defined"}
    assert shares(table, "C") == [(0, 0.0), (1, 0.75)]  # 100 is a quarter of 400, not below it
    assert table["F"]["short_answer_reference"]["median"] == 200.0  # (200 + 200) / 2: each arm its own reference
    assert shares(table, "F") == [(0, 0.0), (1, 1 / 3)]  # 60 is short for C (< 100), not for F (>= 50)
    assert all("answer_tag_share" in w and "mean_completion_tokens" in w for w in table["C"]["windows"])


def test_fixer_2_a_multi_call_cell_counts_its_mean_per_call_so_an_early_alfworld_win_is_no_short_answer():
    table = readout.arm_table(windowed(
        [("C", 0, [50] * 30), ("C", 0, [40] * 20), ("C", 0, [60] * 50),  # episodes: per-call means 50, 40, 60
         ("C", 1, [50] * 5),  # won in 5 steps: mean 50 (its sum, 250, is below a quarter of the median sum 1,500)
         ("C", 1, [5] * 30),  # a terse episode: mean 5 < 12.5
         ("C", 1, [300, 15])]))  # a <calc> first and second call: mean 157.5
    assert table["C"]["short_answer_reference"]["median"] == 50.0
    assert shares(table, "C") == [(0, 0.0), (1, 1 / 3)]


def test_fixer_2_an_arm_without_a_cell_with_usage_in_the_unit_first_window_has_no_share_and_no_stand_in():
    table = readout.arm_table(windowed(
        [("C", 0, [400]), ("C", 1, [12]),
         ("withhold:p", 1, [400]), ("withhold:p", 1, [400]), ("withhold:p", 2, [12]),  # nothing in window 0
         ("P_F", 0, [None]), ("P_F", 0, []), ("P_F", 1, [300]), ("P_F", 1, [10])]))  # window 0 without usage
    assert shares(table, "C") == [(0, 0.0), (1, 1.0)]
    assert table["withhold:p"]["short_answer_reference"] == {"window": 0, "cells": 0, "no_usage": 0, "median": None,
                                                             "status": "no_cell_with_usage"}
    assert shares(table, "withhold:p") == [(1, None), (2, None)]  # window 1 does not stand in: 12 is not "short"
    assert table["P_F"]["short_answer_reference"] == {"window": 0, "cells": 0, "no_usage": 2, "median": None,
                                                      "status": "no_cell_with_usage"}
    assert shares(table, "P_F") == [(0, None), (1, None)]


def test_fixer_2_a_zero_median_marks_no_short_answer_and_reports_none_not_zero():
    table = readout.arm_table(windowed([("C", 0, [0]), ("C", 0, [0]), ("C", 0, [7]), ("C", 1, [0]), ("C", 1, [300])]))
    assert table["C"]["short_answer_reference"] == {"window": 0, "cells": 3, "no_usage": 0, "median": 0.0,
                                                    "status": "zero_median"}
    assert shares(table, "C") == [(0, None), (1, None)]


def test_fixer_2_cells_without_usage_are_excluded_and_counted_and_shared_cells_are_left_out():
    table = readout.arm_table(windowed(
        [("C", 0, [400]), ("C", 0, [400]), ("C", 0, [400]),
         ("C", 0, [None]), ("C", 0, []), ("C", 0, [400, None]),  # no count, no call, one call without a count
         ("C", 1, [10]), ("C", 1, [None, 5]), ("C", 1, [-3]),  # a negative count is no usage either
         ("F", 1, [], "C-cell-006")]))  # a shared cell sent nothing: in no window, not counted as no usage
    assert table["C"]["short_answer_reference"] == {"window": 0, "cells": 3, "no_usage": 3, "median": 400.0,
                                                    "status": "defined"}
    assert [(w["window"], w["cells"], w["no_usage"], w["short_answer_share"]) for w in table["C"]["windows"]] == \
        [(0, 6, 3, 0.0), (1, 3, 2, 1.0)]
    assert table["F"]["windows"] == [] and table["F"]["shared"] == 1
    assert table["F"]["short_answer_reference"]["status"] == "no_cell_with_usage"


def test_p2_a2_1_a_bench_without_an_answer_tag_has_no_answer_tag_share_not_a_false_zero():
    """Ticket P2-A2-1: SpreadsheetBench and ALFWorld formats carry no ``tag_present`` (``judge._format``), so their
    answer-tag share is None in every window; a QA bench keeps its share."""
    sheet = windowed([("C", 0, [400]), ("C", 0, [380]), ("C", 1, [12])])
    for value in sheet.values():
        value["format"] = {"program_delivered": True, "cases": 1, "cases_available": 1, "violation": False}
    alfworld = windowed([("C", 0, [50] * 3), ("C", 1, [40] * 2)])
    for value in alfworld.values():
        value["format"] = {"steps": 3, "admissible_steps": 3, "violation": False}
    qa = windowed([("C", 0, [400]), ("C", 0, [380]), ("C", 1, [12])])
    qa[("C", "item-000", 0)]["format"]["tag_present"] = False
    for cells in (sheet, alfworld):
        assert [w["answer_tag_share"] for w in readout.arm_table(cells)["C"]["windows"]] == [None, None]
    assert [w["answer_tag_share"] for w in readout.arm_table(qa)["C"]["windows"]] == [0.5, 1.0]
    assert readout.windows is readout._windows


def test_fixer_2_the_sealed_readout_carries_the_short_answer_columns():
    cells = units()
    for bench_cells in cells.values():
        for n, value in enumerate(bench_cells.values()):
            value.update(dispatch_ts=float((n % 3) * TIME_WINDOW_SECONDS + n),
                         completion_tokens=[3 if n % 5 == 4 else 200], format={**value["format"], "tag_present": True})
    found = verified(readout.readout(cells, learned=LEARNED, procedures=PROCEDURES, label="confirmatory",
                                     evidence="engineering_fixture"), "readout")
    table = found["arms"]["officeqa"]["C"]
    assert table["short_answer_reference"]["status"] == "defined" and table["short_answer_reference"]["median"] == 200
    assert all(type(w["short_answer_share"]) is float and w["no_usage"] == 0 for w in table["windows"])
    assert sum(round(w["short_answer_share"] * w["cells"]) for w in table["windows"]) == \
        sum(value["completion_tokens"] == [3] for (arm, _, _), value in cells["officeqa"].items() if arm == "C")
