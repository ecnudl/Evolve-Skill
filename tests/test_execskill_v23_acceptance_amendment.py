"""Amendment 1 all-arm equivalence classes and exact-zero acceptance statistics; synthetic offline evidence only."""
from __future__ import annotations

from collections import Counter

import pytest

from skillopt.execskill import acceptance, protocol, reuse
from tests.test_execskill_acceptance import N, fast_statistics, make_cells, seal  # noqa: F401


def identity(label, *, fault=False):
    return {"request_sha256": label, "post_call": [],
            "faults": [{"procedure": N.id, "hook": "before_call", "kind": "output_shape"}] if fault else []}


def amend(old, label):
    signatures = {}
    for jobs in acceptance.schedule(old, logical=True).values():
        for job in jobs:
            signatures.setdefault(job["set"], {}).setdefault(job["item"], {})[job["arm"]] = identity(label(job))
    return acceptance.with_reuse(old, reuse.from_signatures(old, signatures))


def physical(sealed):
    return [job for jobs in acceptance.schedule(sealed).values() for job in jobs]


def test_all_identical_items_have_no_cells_but_keep_all_statistics_and_denominators(tmp_path):
    sealed = amend(seal(tmp_path, rule=protocol.PRACTICAL_RULE), lambda job: "same")
    astar = sealed["plan"]["astar"]
    assert set(sealed["reuse"]["identical_all"]["real"]) == set(astar)
    assert physical(sealed) == acceptance.expanded_cells([], sealed) == []
    decided = acceptance.decide([], sealed)
    assert decided["analysed"] == len(astar) and decided["shared_unanswered"] == []
    assert decided["A"] == len(sealed["A"]) and decided["provenance"] == {}
    for name, contrast in decided["contrasts"].items():
        assert contrast["n"] == len(astar) and contrast["mean"] == contrast["whole_batch"] == 0
        assert contrast["tie"] == len(astar) and contrast["up"] == contrast["down"] == 0
    assert decided["guards"]["J4_items"]["compared_items"] == 0
    assert decided["guards"]["J5"]["ok"] and decided["guards"]["J5"]["infra"] == {}
    assert decided["guards"]["J5"]["reasoning"] == 0
    assert decided["request_reuse"]["identical_all_real_astar_items"] == len(astar)
    assert set(decided["request_reuse"]["dispatched_by_arm"].values()) == {0}
    assert decided["decision"] == "reject" and acceptance.reproduce([], sealed, decided)


def test_full_classes_share_placebos_and_twins_with_c_not_only_with_parent(tmp_path):
    sealed = amend(seal(tmp_path, kind="delete", rule=protocol.PRACTICAL_RULE),
                   lambda job: "parent" if job["arm"] == "S" else "candidate" if job["arm"] == "S'" else "card")
    jobs = physical(sealed)
    assert {job["arm"] for job in jobs} == {"S", "S'", "C"}
    for item, arms in sealed["reuse"]["reused"]["real"].items():
        assert arms["P_y"] == arms["P_i"] == "C"
        assert all(source == "C" for arm, source in arms.items() if arm.startswith(("withhold:", "restore:")))
    cells = make_cells(sealed)
    table = acceptance.table(acceptance.expanded_cells(cells, sealed))
    assert set(acceptance.differences(table, "P_y", "P_i", sealed["plan"]["astar"])) == {0}
    decision = acceptance.decide(cells, sealed)
    assert set(decision["guards"]["J5"]["infra"]) == {"S", "S'", "C"}


@pytest.mark.parametrize("differing", [10, 35])
def test_c_sample_prefers_already_dispatched_s_and_adds_s_only_for_supplements(tmp_path, differing):
    old = seal(tmp_path, kind="empty", rule=protocol.PRACTICAL_RULE)
    kept = set(old["plan"]["astar"][:differing])
    sealed = amend(old, lambda job: "different" if job["arm"] == "S'" and job["item"] in kept else "same")
    sample = sealed["reuse"]["card_sample"]
    assert len(sample["items"]) == 30 and set(sample["preferred_items"]) <= kept
    assert len(sample["preferred_items"]) == min(differing, 30)
    assert len(sample["supplemental_items"]) == max(0, 30 - differing)
    assert not set(sample["supplemental_items"]) & kept
    rows = physical(sealed)
    assert {j["item"] for j in rows if j["arm"] == "S"} == kept | set(sample["supplemental_items"])
    assert {j["item"] for j in rows if j["arm"] == "C"} == set(sample["items"])
    assert len(rows) == (2 * differing + len(sample["supplemental_items"]) + 30) * sealed["runs"]
    expected_skipped = set(old["plan"]["astar"]) - kept - set(sample["items"])
    assert set(sealed["reuse"]["identical_all"].get("real", [])) == expected_skipped
    assert reuse.from_signatures(old, sealed["reuse"]["signatures"]) == sealed["reuse"]


def test_instruments_remain_independent_when_every_request_is_identical(tmp_path):
    old = seal(tmp_path, kind="empty", dup=True, rule=protocol.PRACTICAL_RULE)
    sealed = amend(old, lambda job: "same")
    counts = Counter(job["arm"] for job in physical(sealed))
    assert counts == {"S": len(old["plan"]["astar"]) * old["runs"],
                      "S_dup": len(old["plan"]["astar"]) * old["runs"], "C": 30 * old["runs"]}
    assert sealed["reuse"]["identical_all"] == {}
    cells = make_cells(sealed, token=lambda job: "fail" if job["arm"] == "S" else "pass")
    decided = acceptance.decide(cells, sealed)
    assert decided["contrasts"]["S'-S"]["whole_batch"] == 0
    assert decided["contrasts"]["S-C"]["mean"] == -1
    assert all(row["p_two_sided"] == 0 for row in decided["guards"]["J6_dup"]["pairs"])
    assert decided["decision"] == "undetermined"


def test_j4_excludes_interchangeable_parent_candidate_but_keeps_original_margin(tmp_path):
    sealed = amend(seal(tmp_path, rule=protocol.PRACTICAL_RULE),
                   lambda job: "different" if job["arm"] == "P_y" else "same")
    cells = make_cells(sealed, violation=lambda job: job["arm"] == "S")
    j4 = acceptance.decide(cells, sealed)["guards"]["J4_items"]
    assert j4["S'"] == j4["S"] == j4["compared_items"] == 0
    assert j4["margin"] == protocol.format_margin(len(sealed["plan"]["astar"]))
    assert j4["interchangeable_items"] == len(sealed["plan"]["astar"]) and j4["ok"]


def test_j5_uses_only_actual_representative_cells_not_logical_copies(tmp_path):
    sealed = amend(seal(tmp_path, rule=protocol.PRACTICAL_RULE),
                   lambda job: "different" if job["arm"] == "P_y" else "same")
    cells = make_cells(sealed)
    one = next(cell for cell in cells if cell["arm"] == "S")
    one["judge"]["flags"] = ["reasoning_mismatch"]
    one["judge"]["v2"]["token"] = "unknown"
    j5 = acceptance.decide(cells, sealed)["guards"]["J5"]
    assert set(j5["infra"]) == {"S", "P_y"}
    assert j5["infra"]["S"] == 1 / (len(sealed["plan"]["astar"]) * sealed["runs"])
    assert j5["reasoning"] == 1 / len(cells)
    assert j5["balance"]["ok"] and j5["block_gap"]["ok"]


def test_shared_unanswered_uses_dispatched_cells_and_never_excludes_identical_all(tmp_path):
    old = seal(tmp_path, rule=protocol.PRACTICAL_RULE)
    sent = set(old["plan"]["astar"][:4])
    sealed = amend(old, lambda job: "different" if job["item"] in sent and job["arm"] != "S" else "same")
    cells = make_cells(sealed, token=lambda job: "unknown")
    for cell in cells:
        cell["sends"] = [{"receipt": None}]
    decided = acceptance.decide(cells, sealed)
    assert set(decided["shared_unanswered"]) == sent
    assert decided["analysed"] == len(old["plan"]["astar"]) - len(sent)
    assert decided["contrasts"]["S'-S"]["tie"] == decided["analysed"]
    assert decided["request_reuse"]["identical_all_real_astar_items"] == decided["analysed"]


def test_faulting_or_missing_identity_is_never_an_identical_all_item(tmp_path):
    old = seal(tmp_path, rule=protocol.PRACTICAL_RULE)
    sealed = amend(old, lambda job: "same")
    signatures = sealed["reuse"]["signatures"]
    first, second = old["plan"]["astar"][:2]
    signatures["real"][first]["S'"] = identity("same", fault=True)
    del signatures["real"][second]["S'"]
    sealed = acceptance.with_reuse(old, reuse.from_signatures(old, signatures))
    assert {j["item"] for j in physical(sealed)} == {first, second}
    assert {j["arm"] for j in physical(sealed)} == {"S", "S'"}
    assert acceptance.decide(make_cells(sealed), sealed)["guards"]["J3"]["items"] == [first]


def test_skipped_probe_has_zero_gain_without_a_logical_cell():
    assert acceptance._probe([], identical=["p1", "p2"]) == {"n": 2, "gain": 0, "p_t": 1, "ok": True}


def test_dispatch_counts_exist_on_small_and_early_undetermined_rounds(tmp_path):
    small = seal(tmp_path / "small", kind="empty", fires_n=lambda n: n < 3, reuse={}, rule=protocol.PRACTICAL_RULE)
    decision = acceptance.decide([], small)
    assert decision["decision"] == acceptance.SMALL and decision["reuse"]["physical_cells"] == 0
    assert decision["reuse"]["dispatched_by_arm"] == {}
    sealed = amend(seal(tmp_path / "unknown", kind="empty", rule=protocol.PRACTICAL_RULE), lambda job: job["arm"])
    cells = make_cells(sealed, token=lambda job: "unknown")
    for cell in cells:
        cell["sends"] = [{"receipt": None}]
    decision = acceptance.decide(cells, sealed)
    assert decision["decision"] == "undetermined" and "guards" not in decision
    assert decision["reuse"]["physical_cells"] == len(cells)
    assert decision["reuse"]["dispatched_by_arm"] == dict(Counter(c["arm"] for c in cells))


def test_generated_only_dispatch_balances_without_inventing_real_cells(tmp_path):
    old = seal(tmp_path, rule=protocol.PRACTICAL_RULE,
               generate=lambda views: [{"id": "g-%02d" % n, "source_item": item}
                                       for n, item in enumerate(list(views)[:4])])
    sealed = amend(old, lambda job: "same" if job["set"] == "real" else job["arm"])
    cells = make_cells(sealed)
    assert cells and all(cell["set"] == "G_acc" for cell in cells)
    decision = acceptance.decide(cells, sealed)
    assert decision["analysed"] == len(old["plan"]["astar"])
    assert decision["guards"]["J5"]["infra"] == {} and decision["guards"]["J5"]["reasoning"] == 0
    assert decision["guards"]["J5"]["balance"]["ok"] and decision["guards"]["J5"]["block_gap"]["ok"]
