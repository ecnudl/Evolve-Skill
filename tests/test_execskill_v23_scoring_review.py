"""Codex review findings 2 and 5: conservative shared scores and predictive validity, with offline synthetic cells."""
from __future__ import annotations

from fractions import Fraction

import pytest

from skillopt.execskill import acceptance, protocol, stats_ext, validity
from tests.test_execskill_acceptance import fast_statistics, make_cells, seal  # noqa: F401
from tests.test_execskill_v23_acceptance_amendment import amend
from tests.test_execskill_validity import generated


def cell(arm, token, *, item="i", run=0, origin=None, cell_set="real"):
    return {"arm": arm, "task_id": item, "run": run, "set": cell_set, "judge": {"v2": {"token": token}},
            **({"reused_from": origin} if origin is not None else {})}


def origin(arm="S", *, item="i", run=0, cell_set="real"):
    return {"arm": arm, "task_id": item, "run": run, "set": cell_set}


@pytest.mark.parametrize("unknown", ["unknown_artifact", "unknown", "unknown_fault"])
def test_shared_candidate_keeps_l_bound_against_different_controls(unknown):
    table = acceptance.table([cell("S", unknown), cell("S'", unknown, origin=origin()),
                              cell("P_y", "fail"), cell("C", "pass")])
    assert acceptance.differences(table, "S'", "P_y", ["i"]) == [0]  # the reviewer's +1 regression
    assert acceptance.differences(table, "S'", "C", ["i"]) == [-1]
    assert acceptance.differences(table, "S'", "S", ["i"]) == [0]  # same-origin exception only
    assert acceptance.differences(table, "S", "P_y", ["i"]) == [1]


def test_shared_control_keeps_h_bound_against_a_different_parent():
    table = acceptance.table([cell("S'", "unknown_artifact"),
                              cell("P_y", "unknown_artifact", origin=origin("S'")), cell("S", "fail")])
    assert acceptance.differences(table, "P_y", "S", ["i"]) == [1]
    assert acceptance.differences(table, "S'", "S", ["i"]) == [0]
    assert acceptance.differences(table, "S'", "P_y", ["i"]) == [0]


def test_zeroing_is_per_shared_run_not_per_item():
    table = acceptance.table([cell("S", "unknown_artifact", run=0),
                              cell("S'", "unknown_artifact", run=0, origin=origin(run=0)),
                              cell("S", "fail", run=1), cell("S'", "pass", run=1)])
    assert acceptance.differences(table, "S'", "S", ["i"]) == [Fraction(1, 2)]
    assert acceptance.differences(table, "S", "S'", ["i"]) == [Fraction(-1, 2)]


@pytest.mark.parametrize("different", [{"item": "other"}, {"run": 1}, {"cell_set": "G_acc"}])
def test_an_origin_from_another_item_run_or_set_does_not_zero_a_comparison(different):
    foreign = origin(**different)
    table = acceptance.table([cell("S'", "unknown_artifact", origin=foreign),
                              cell("P_y", "unknown_artifact", origin=foreign)])
    assert acceptance.differences(table, "S'", "P_y", ["i"]) == [-1]


def test_decision_contrasts_labels_and_tau_preserve_each_arms_registered_bound(tmp_path):
    old = seal(tmp_path, kind="delete", rule=protocol.PRACTICAL_RULE)

    def label(job):
        if job["arm"] in ("S", "S'"):
            return "shared-parent"
        return "twins" if job["arm"].startswith(("withhold:", "restore:")) else job["arm"]

    sealed = amend(old, label)
    cells = make_cells(sealed, token=lambda job: "unknown_artifact" if job["arm"] == "S"
                       else "pass" if job["arm"] in ("C", "P_i") else "fail",
                       violation=lambda job: job["arm"] == "S")
    decided = acceptance.decide(cells, sealed)
    whole = len(sealed["plan"]["astar"]) / len(sealed["A"])
    expected = {"S'-S": 0, "S'-P_y": 0, "S'-C": -whole, "S-C": 0, "P_y-S": -whole, "P_i-S": 0}
    assert {name: value["whole_batch"] for name, value in decided["contrasts"].items()} == expected
    assert not decided["guards"]["J1"]["ok"] and decided["guards"]["J2"]["label"] == "form"
    assert decided["twins"] and all(twin["tau"] == 0 for twin in decided["twins"].values())
    assert decided["guards"]["J4_items"]["S'"] == decided["guards"]["J4_items"]["S"] == 0
    assert decided["guards"]["J4_items"]["compared_items"] == 0


@pytest.mark.parametrize("zero_set", ["real", "G_acc"])
def test_validity_keeps_identical_all_real_and_generated_items_and_denominators(tmp_path, zero_set):
    sealed = amend(seal(tmp_path, generate=generated, rule=protocol.PRACTICAL_RULE),
                   lambda job: "same" if job["set"] == zero_set else job["arm"])
    cells = make_cells(sealed, token=lambda job: "pass" if job["arm"] == "S'" else "fail")
    assert not any(c["set"] == zero_set for c in cells)
    expected = {"d_gen": 0.0 if zero_set == "G_acc" else 1.0,
                "d_real": 0.0 if zero_set == "real" else 1.0,
                "se_gen": 0.0, "se_real": 0.0, "cov": 0.0, "n_gen": 45, "n_real": 45}
    assert validity.round_pair(cells, sealed) == expected
    assert validity.round_pair(acceptance.expanded_cells(cells, sealed), sealed) == expected


def test_validity_expands_shared_cells_and_retains_partial_zero_generated_items(tmp_path):
    old = seal(tmp_path, generate=generated, rule=protocol.PRACTICAL_RULE)
    unchanged = {g["id"] for g in old["g_acc"][:10]}

    def label(job):
        if job["set"] == "G_acc":
            return "same" if job["item"] in unchanged else job["arm"]
        return "other" if job["arm"] == "P_y" else "shared"

    sealed = amend(old, label)
    cells = make_cells(sealed, token=lambda job: "pass" if job["arm"] == "S'" else "fail")
    assert all(c["arm"] != "S'" for c in cells if c["set"] == "real")
    pair = validity.round_pair(cells, sealed)
    assert pair["n_gen"] == pair["n_real"] == 45
    assert pair["d_gen"] == 35 / 45 and pair["d_real"] == pair["cov"] == 0
    assert pair["se_gen"] > 0 and pair["se_real"] == 0


def test_validity_duplicate_control_includes_zero_generated_and_real_items(tmp_path):
    sealed = amend(seal(tmp_path, kind="empty", generate=generated, rule=protocol.PRACTICAL_RULE),
                   lambda job: "same")
    cells = make_cells(sealed, token=lambda job: "pass" if job["arm"] == "C" else "fail")
    assert all(c["set"] == "real" for c in cells)
    sample = set(sealed["reuse"]["card_sample"]["items"])
    expected = {"pair": "C-S", "gen_ci95": [0.0, 0.0], "real_ci95": list(stats_ext.bootstrap_ci(
        [Fraction(int(item in sample)) for item in sorted(sealed["plan"]["astar"])]))}
    assert validity.dup_control(cells, sealed) == expected
    assert validity.dup_control(acceptance.expanded_cells(cells, sealed), sealed) == expected


def test_identical_all_stays_exact_zero_without_any_cell_or_bound():
    table = acceptance.table([], identical=["i"])
    for first in ("S", "S'", "C", "P_y", "withhold:p"):
        for second in ("S", "S'", "C", "P_y", "withhold:p"):
            assert acceptance.differences(table, first, second, ["i"]) == [Fraction(0)]
