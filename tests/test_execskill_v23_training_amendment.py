"""Amendment 1 T2: skipped requests remain unchanged evaluated items. Synthetic cells/hooks only; zero calls."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from skillopt.execskill import protocol, step
from skillopt.execskill.package import FIXTURE, empty, with_
from tests.execskill_fakes_env import FakeSandbox, procedure


def cell(arm, item, token, run=0, *, faults=(), violation=False):
    return {"cell": {"arm": arm, "task_id": item, "id": "%s/%s/%s" % (arm, item, run), "run": run},
            "judge": {"v2": {"token": token}, "format": {"violation": violation}}, "faults": list(faults),
            "final": {"outcome": token, "kind": "answer"}}


def fixed_items(ids, runs=2):
    return {(arm, item): [cell(arm, item, token, n) for n in range(runs)] for item in ids
            for arm, token in (("S'", "pass"), ("S", "fail"))}


def test_identical_items_keep_adoption_threshold_and_fault_cell_denominator():
    same = ["same-%d" % n for n in range(99)]
    cells = fixed_items(["fixed"])
    cells[("S'", "fixed")][0]["faults"] = [{"procedure": "new"}]
    verdict = step.train_verdict(cells, ["fixed", *same], [], {"new"}, predicate_faults=0, routed=100,
                                 sign=False, identical=same, runs=protocol.SLICES["officeqa"]["run"][1])
    assert verdict["items"] == 100 and verdict["need"] == 2
    assert verdict["fixed"] == ["fixed"] and verdict["broken"] == [] and verdict["net"] == "1/1"
    assert verdict["candidate_cells"] == 2 and verdict["skipped_candidate_cells"] == 198
    assert verdict["candidate_cells_denominator"] == 200 and verdict["guards"]["own_faults"]
    assert verdict["format_margin"] == 4 and verdict["reason"] == "gain:net" and not verdict["adopted"]


def test_identical_items_keep_format_margin_at_registered_runs():
    same = ["same-%d" % n for n in range(98)]
    cells = fixed_items(["a", "b"])
    for c in cells[("S'", "a")] + cells[("S'", "b")][:1]:
        c["judge"]["format"]["violation"] = True
    verdict = step.train_verdict(cells, ["a", "b", *same], [], set(), predicate_faults=0, routed=100,
                                 sign=False, identical=same, runs=2)
    assert verdict["format_cells"] == {"S'": 3, "S": 0}
    assert verdict["format_margin"] == 4 and verdict["candidate_cells_denominator"] == 200
    assert verdict["adopted"] and verdict["need"] == 2 and verdict["net"] == "2/1"


def test_generated_identical_items_count_once_and_all_identical_items_never_gain():
    items, generated = ["r1", "r2"], ["g1", "g2", "g3"]
    verdict = step.train_verdict({}, items, generated, set(), predicate_faults=0, routed=5,
                                 sign=False, identical=items + generated, runs=2)
    assert verdict["items"] == 2 and verdict["generated"] == 3
    assert verdict["candidate_cells"] == 0 and verdict["candidate_cells_denominator"] == 7
    assert verdict["skipped_candidate_cells"] == 7 and verdict["net"] == "0/1"
    assert verdict["fixed"] == verdict["broken"] == [] and not verdict["adopted"]
    assert verdict["guards"] == {"own_faults": True, "predicate_faults": True, "format": True}


@pytest.mark.parametrize("options", [
    {"identical": ["absent"]}, {"identical": ["same", "same"]}, {"identical": ["same"], "runs": 0},
    {"identical": ["same"], "request_faults": ["same"]},
])
def test_skip_declaration_cannot_invent_items_or_drop_a_fault(options):
    with pytest.raises(ValueError, match="Identical training items"):
        step.train_verdict({}, ["same"], [], set(), predicate_faults=0, routed=1, **options)


def test_legacy_verdict_omits_amendment_fields_and_keeps_its_exact_shape():
    cells = fixed_items(["one"])
    verdict = step.train_verdict(cells, ["one"], [], set(), predicate_faults=0, routed=1, sign=False)
    assert verdict == {
        "adopted": True, "reason": None, "items": 1, "generated": 0, "fixed": ["one"], "broken": [],
        "net": "1/1", "need": 1, "p_sign": 0.5,
        "guards": {"own_faults": True, "predicate_faults": True, "format": True},
        "gain": {"fixed_over_broken": True, "net": True}, "own_fault_cells": 0, "candidate_cells": 2,
        "predicate_faults": 0, "routed": 1, "format_cells": {"S": 0, "S'": 0}, "format_margin": 2,
        "sign_required": False,
    }


def make_step(tmp_path, monkeypatch, configuration=protocol.MAIN_V2_3):
    parent = empty(step="s0", evidence=FIXTURE)
    note = procedure("fx-amendment", ("applies", "before_call"))
    candidate = with_(parent, step="s1", add=[note])
    table = {note.id: {"applies": lambda view: True,
                       "before_call": lambda view, state: {"facts": ["A public fact."]}
                       if view["question"] == "different" else None}}

    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(table).start(package, kind="cell")
        try:
            yield worker
        finally:
            worker.close()

    setting = SimpleNamespace(extra={"configuration": configuration}, evidence=FIXTURE,
                              cards={}, runtime={"officeqa": {}})
    st = step._Step(setting, SimpleNamespace(item_workers=workers), "G", "officeqa", 1, parent, tmp_path)

    def unit(name, work, **kwargs):
        attempt = tmp_path / name / "attempt-1"
        attempt.mkdir(parents=True, exist_ok=True)
        return work(attempt)

    seen = []

    def cells(st, attempt, endpoints, unit, jobs, **kwargs):
        seen.extend(jobs)
        return [cell(arm, item, "pass" if arm == "S'" else "fail", run)
                for arm, package, item, run, task in jobs]

    monkeypatch.setattr(st, "unit", unit)
    monkeypatch.setattr(st, "solver", lambda *args, **kwargs: object())
    monkeypatch.setattr(step, "_cells", cells)
    return st, candidate, seen


def item(task_id, question):
    return {"task_id": task_id, "public": {"question": question, "context": "A public fact."}, "private": {}}


def generated(task_id, question):
    value = item(task_id, question)
    return protocol.record("generated-item", FIXTURE, {"id": task_id, "benchmark": "officeqa",
                                                       "public": value["public"], "private": {}})


def test_training_dispatches_differences_but_evaluates_both_item_sources(tmp_path, monkeypatch):
    st, candidate, seen = make_step(tmp_path, monkeypatch)
    cut = {"run": [item("different", "different"), item("same", "same")]}
    g_self = [generated("g-different", "different"), generated("g-same", "same")]
    result = step._train_eval(st, cut, 1, st.parent, candidate,
                              {"generator": {"status": "admitted"}, "g_self": g_self})
    assert {(arm, key, run) for arm, package, key, run, task in seen} == {
        (arm, key, run) for arm in ("S'", "S") for key, runs in (("officeqa/different", 2), ("g-different", 1))
        for run in range(runs)}
    assert result["identical"] == ["officeqa/same", "g-same"] and result["cells"] == 6
    verdict = result["verdict"]
    assert verdict["items"] == verdict["generated"] == 2
    assert verdict["candidate_cells"] == verdict["skipped_candidate_cells"] == 3
    assert verdict["candidate_cells_denominator"] == 6 and verdict["net"] == "2/1"
    assert result["feedback"]["procedures"][0]["enabled_items"] == 2


def test_training_all_identical_creates_no_endpoint_and_keeps_evaluated_items(tmp_path, monkeypatch):
    st, candidate, seen = make_step(tmp_path, monkeypatch)
    monkeypatch.setattr(st, "solver", lambda *args, **kwargs: pytest.fail("No endpoint for identical requests"))
    result = step._train_eval(st, {"run": [item("same", "same")]}, 1, st.parent, candidate, {})
    assert not seen and result["cells"] == 0 and result["verdict"]["items"] == 1
    assert result["verdict"]["candidate_cells_denominator"] == 2 and not result["adopted"]


def test_legacy_training_still_dispatches_enabled_list_differences(tmp_path, monkeypatch):
    st, candidate, seen = make_step(tmp_path, monkeypatch, protocol.MAIN_V2_2)
    result = step._train_eval(st, {"run": [item("same", "same")]}, 1, st.parent, candidate, {})
    assert len(seen) == result["cells"] == 4 and result["verdict"]["items"] == 1
    assert "identical" not in result and "candidate_cells_denominator" not in result["verdict"]


def test_selftest_has_the_same_unchanged_item_denominators():
    same = ["same-%d" % n for n in range(196)]
    different = ["different-%d" % n for n in range(4)]
    cells = [cell(arm, key, "pass", faults=({"procedure": "new"},) if arm == "S'" and n == 0 else (),
                  violation=arm == "S'") for n, key in enumerate(different) for arm in ("S'", "S")]
    verdict = step.selftest_verdict(cells, {"officeqa": different + same}, {"new"}, identical={"officeqa": same})
    assert verdict["candidate_cells"] == 4 and verdict["fault_items_denominator"] == 200
    assert verdict["fault_share"] == 0.005 and verdict["sets"]["officeqa"]["format_gap"] == 0.02
    assert verdict["sets"]["officeqa"]["accuracy_items"] == 4 and not verdict["blocked"]


def test_selftest_all_identical_is_unchanged_without_cells():
    verdict = step.selftest_verdict([], {"officeqa": ["same"]}, set(), identical={"officeqa": ["same"]})
    assert verdict["fault_items_denominator"] == 1 and verdict["skipped_items"] == 1
    assert verdict["sets"]["officeqa"]["format_gap"] == 0 and not verdict["blocked"]
    assert verdict["sets"]["officeqa"]["accuracy"] == {"S'": None, "S": None}
