"""coevo5 evaluation (registration §10, §0, §2.1, §13.4): the SpreadsheetBench reference qualification (zero model
calls, two scorings in fresh directories), the owner's recorded consent and the write-once test-panel registry, sealed
evaluation units (counts only, reuse of a byte-identical Skill, a pause on missing infrastructure), the score-free
monitor and the gated unsealing."""
import base64
import ctypes
import errno
import io
import json
import os
import re
import subprocess
import sys
import traceback
import warnings
import zipfile
from copy import deepcopy

import openpyxl
import pytest

from skillopt.coevo5 import data, evaluation, qualify
from skillopt.coevo5.budget import OVERALL, Budget
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.cells import Context, Pause, exclusive
from skillopt.coevo5.outcomes import REFERENCE_DRIFT, preflight
from skillopt.coevo5.protocol import MAX_RESENDS, RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
REPLY = {"ok": True, "response": "<answer>Paris</answer>", "finish_reason": "stop", "error_type": None,
         "usage": USAGE, "attempts": [{"status": 200}]}
TRANSPORT = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "transport",
             "attempts": [{"error": "ReadTimeout"}] * 4}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _xlsx(path, value):
    book = openpyxl.Workbook()
    book.active["A1"] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return str(path)


# ------------------------------------------------------------------------------------- the reference qualification
PASSED = {"status": "pass", "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
          "metrics": {"cases": [{"status": "pass", "reason": "cell_values_match"}]}}


def _unjudged(reason, **extra):
    return {"status": "unknown", "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
            "metrics": {"cases": [{"status": "unknown", "reason": reason}]}, **extra}


def _sheet_tasks(tmp_path, *names):
    return [{"task_id": name, "family_id": "f-" + name, "project_id": "", "partition": "final",
             "public": {"instruction": "Fill A1.", "input_files": [_xlsx(tmp_path / "wb" / (name + "_init.xlsx"), 1)],
                        "answer_position": "A1"},
             "private": {"test_files": [_xlsx(tmp_path / "wb" / (name + "_golden.xlsx"), 2)],
                         "answer_position": "A1"}} for name in names]


def _referee(monkeypatch, verdicts):
    """The frozen scorer, patched: ``verdicts`` {(task_id, scoring): score}, else a pass; every call is recorded."""
    seen = []

    def score(benchmark, public, private, prediction, *, runtime=None):
        context = runtime["_score_context"]
        seen.append((context, prediction))
        request = context["request"]
        return verdicts.get((request["task_id"], request["scoring"]), PASSED)

    monkeypatch.setattr(backends, "score", score)
    return seen


def _native(tmp_path):
    return Slots(tmp_path / "slots", "spreadsheet-native", 2)


def test_reference_failures_are_categorised_by_their_side_and_reason():
    assert qualify.category(REFERENCE_DRIFT) == "reference_cache_mismatch"
    assert qualify.category("reference:recalculation_changed_formula") == "read_view_unverifiable"
    assert qualify.category("reference:general_formula_read_view_unverified") == "read_view_unverifiable"
    assert qualify.category("reference:recalculation_timeout") == "reference_recalculation_failed"
    assert qualify.category("prediction:recalculation_timeout") == "other"


def test_an_item_qualifies_when_both_scorings_of_its_references_pass(tmp_path, monkeypatch):
    tasks = _sheet_tasks(tmp_path, "s1", "s2", "s3")
    seen = _referee(monkeypatch, {("s2", 1): _unjudged("reference:recalculation_timeout"),
                                  ("s3", 0): _unjudged(REFERENCE_DRIFT)})
    root = tmp_path / "qualification"
    record = qualify.qualify(tasks, root, RUNTIME["spreadsheetbench"], side="train", native=_native(tmp_path),
                             workers=2)
    assert record["qualified"] == ["s1"] and record["model_calls"] == 0 and record["scorings_per_item"] == 2
    assert record["excluded"] == {"s2": "reference_recalculation_failed", "s3": "reference_cache_mismatch"}
    assert qualify.summary(record) == {"side": "train", "items": 3, "qualified": 1,
                                       "excluded": {"reference_recalculation_failed": 1, "reference_cache_mismatch": 1}}
    # every scoring in a directory of its own; the answer of every case is its own reference workbook
    positions = {context["position"] for context, _ in seen}
    assert len(seen) == 6 and len(positions) == 6 and len(list((root / "scores").glob("*.json"))) == 6
    assert all(context["artifact_dir"] == str(root / "host_only" / "scorer_artifacts" / context["position"])
               for context, _ in seen)
    reference = open(tasks[0]["private"]["test_files"][0], "rb").read()
    answer = next(p for c, p in seen if c["request"]["task_id"] == "s1")
    assert base64.b64decode(answer["output"]["cases"][0]["output_base64"]) == reference
    assert qualify.load(root / "qualification.json") == record
    with pytest.raises(ValueError):  # written once
        qualify.qualify(tasks, root, RUNTIME["spreadsheetbench"], side="train", native=_native(tmp_path), workers=1)


@pytest.mark.parametrize("score,kind", [
    (_unjudged("native_scoring_input_error:KeyError"), "configuration"),
    (_unjudged("prediction:recalculation_timeout", cleanup_confirmed=False), "cleanup"),
    (_unjudged("reference:container_cleanup_unconfirmed"), "cleanup")])
def test_a_configuration_error_or_an_unconfirmed_cleanup_stops_the_qualification(tmp_path, monkeypatch, score, kind):
    _referee(monkeypatch, {("s1", 0): score})
    root = tmp_path / "qualification"
    with pytest.raises(Pause) as stop:
        qualify.qualify(_sheet_tasks(tmp_path, "s1"), root, RUNTIME["spreadsheetbench"], side="train",
                        native=_native(tmp_path), workers=1)
    assert stop.value.kind == kind and not (root / "qualification.json").exists()


def test_only_the_frozen_v7_scorer_qualifies(tmp_path):
    with pytest.raises(ValueError):
        qualify.qualify(_sheet_tasks(tmp_path, "s1"), tmp_path / "q", {"spreadsheet_scorer": "other"}, side="train",
                        native=_native(tmp_path), workers=1)


# ----------------------------------------------------------------------------------------- consent and registry
def _consent(shared, **change):
    value = {"test_evaluation": True, "sheet_test_qualification": False, "by": "owner", "date": "2026-10-17",
             "note": "fixture", **change}
    _write(shared / "consent.json", value)


def _test_panel(monkeypatch, tasks, panel_hash="panel-hash", units=None):
    def test_panel(pinned, benchmark, *, access):
        assert isinstance(access, data.TestAccess)
        if units is not None:
            units.append(access.unit)
        return deepcopy(tasks), {"panel_hash": panel_hash, "excluded_without_pages": [], "source_files": None}

    monkeypatch.setattr(data, "test_panel", test_panel)


@pytest.mark.parametrize("change", [None, {"by": "assistant"}, {"test_evaluation": False}, {"extra": 1}])
def test_test_sets_are_read_only_with_the_owner_s_recorded_consent(tmp_path, change):
    shared = tmp_path / "shared"
    if change is not None:
        _consent(shared, **change)
    with pytest.raises(ValueError, match="consent"):
        evaluation.consent(shared)
    _consent(shared)
    assert evaluation.consent(shared)["by"] == "owner"


RUN = "manifest-hash-of-this-run"


def _recover(attempt, decision="owner: redo the interrupted attempt"):
    _write(attempt / "recovery.json", {"by": "owner", "date": "2026-10-17", "decision": decision})


def _sheet_test_tasks(tmp_path, shared, tasks, *, workers=2):
    return evaluation.test_tasks(shared, {}, "spreadsheetbench", "E-glm/s0/evaluation/spreadsheetbench", run=RUN,
                                 runtime=RUNTIME["spreadsheetbench"], native=_native(tmp_path), workers=workers)


def test_the_test_side_qualification_needs_its_own_consent_and_runs_once(tmp_path, monkeypatch):
    shared, tasks = tmp_path / "shared", _sheet_tasks(tmp_path, "s1", "s2")
    _consent(shared)
    _test_panel(monkeypatch, tasks)
    seen = _referee(monkeypatch, {("s2", 0): _unjudged("reference:recalculation_timeout")})
    with pytest.raises(ValueError, match="qualify the test references"):
        _sheet_test_tasks(tmp_path, shared, tasks)
    _write(shared / "consent.json", {**read_json(shared / "consent.json"), "sheet_test_qualification": True})
    assert [t["task_id"] for t in _sheet_test_tasks(tmp_path, shared, tasks)] == ["s1"]
    assert [t["task_id"] for t in _sheet_test_tasks(tmp_path, shared, tasks)] == ["s1"] and len(seen) == 4
    record = qualify.load(shared / "test" / "spreadsheetbench-qualification" / "attempt-1" / "qualification.json")
    assert record["side"] == "test" and record["excluded"] == {"s2": "reference_recalculation_failed"}
    changed = deepcopy(tasks)
    changed[0]["public"]["instruction"] = "Fill A1 again."
    _test_panel(monkeypatch, changed)  # same ids and panel hash, other content
    with pytest.raises(ValueError, match="other items"):
        _sheet_test_tasks(tmp_path, shared, changed)


@pytest.mark.parametrize("score", [_unjudged("native_scoring_input_error:KeyError"),
                                   _unjudged("reference:container_cleanup_unconfirmed")])
def test_a_paused_test_qualification_is_redone_only_after_the_owner_s_decision(tmp_path, monkeypatch, score):
    shared, tasks = tmp_path / "shared", _sheet_tasks(tmp_path, "s1", "s2")
    _consent(shared, sheet_test_qualification=True)
    _test_panel(monkeypatch, tasks)
    _referee(monkeypatch, {("s1", 0): score})
    with pytest.raises(Pause):
        _sheet_test_tasks(tmp_path, shared, tasks, workers=1)
    base = shared / "test" / "spreadsheetbench-qualification"
    assert read_json(base / "attempt-1" / "status.json", sealed=True)["status"] == "paused"
    assert not (base / "attempt-1" / "qualification.json").exists()
    assert not (shared / "test" / "spreadsheetbench-qualification.json").exists()
    seen = _referee(monkeypatch, {})
    with pytest.raises(Pause) as stop:  # an evaluation that was waiting for the lock stops; it does not retry
        _sheet_test_tasks(tmp_path, shared, tasks)
    assert (stop.value.kind, stop.value.reason) == ("qualification_paused", "attempt-1") and seen == []
    _recover(base / "attempt-1")
    assert [t["task_id"] for t in _sheet_test_tasks(tmp_path, shared, tasks)] == ["s1", "s2"]
    pointer = read_json(shared / "test" / "spreadsheetbench-qualification.json", sealed=True)
    assert pointer["attempt"] == "attempt-2"
    assert pointer["qualification_hash"] == qualify.load(base / "attempt-2" / "qualification.json")["record_hash"]


def test_an_interrupted_test_qualification_also_waits_for_the_owner_s_decision(tmp_path, monkeypatch):
    shared, tasks = tmp_path / "shared", _sheet_tasks(tmp_path, "s1")
    _consent(shared, sheet_test_qualification=True)
    _test_panel(monkeypatch, tasks)
    seen = _referee(monkeypatch, {})
    base = shared / "test" / "spreadsheetbench-qualification"
    (base / "attempt-1").mkdir(parents=True)  # a process died inside its attempt
    with pytest.raises(Pause, match="qualification_paused"):
        _sheet_test_tasks(tmp_path, shared, tasks)
    _recover(base / "attempt-1")
    assert [t["task_id"] for t in _sheet_test_tasks(tmp_path, shared, tasks)] == ["s1"] and len(seen) == 2


def test_no_qualified_test_item_pauses_the_evaluation(tmp_path, monkeypatch):
    shared, tasks = tmp_path / "shared", _sheet_tasks(tmp_path, "s1")
    _consent(shared, sheet_test_qualification=True)
    _test_panel(monkeypatch, tasks)
    _referee(monkeypatch, {("s1", 1): _unjudged(REFERENCE_DRIFT)})
    with pytest.raises(Pause) as stop:
        _sheet_test_tasks(tmp_path, shared, tasks)
    assert stop.value.kind == "no_qualified_test_items"


# ------------------------------------------------------------------------------------------- evaluation units
SEARCH_TESTS = [{"task_id": "q%d" % n, "family_id": "f%d" % n, "project_id": "", "partition": "final",
                 "public": {"question": "Capital of France?", "context": ["Paris is the capital."]},
                 "private": {"answers": ["Paris" if n % 2 == 0 else "Lyon"]}} for n in range(4)]


class _Client:
    def __init__(self, reply=REPLY):
        self.reply, self.calls = reply, 0

    def call(self, system, user):
        self.calls += 1
        return self.reply


def _context(tmp_path, unit_root, client, attempt=1, budget=None):
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 4),
                        budget=budget, scopes=(OVERALL,) if budget is not None else (), sleep=lambda _: None)
    return Context(store=unit_root / ("attempt-%d" % attempt), endpoint=endpoint, runtime=RUNTIME,
                   native=_native(tmp_path), episodes=Slots(tmp_path / "slots", "alfworld-episode", 2))


def _evaluate(tmp_path, unit_root, client, *, stage=0, skill="skill", attempt=1, previous=None,
              benchmark="searchqa", chain="E-glm", run=RUN, budget=None):
    return evaluation.evaluate(unit_root, run=run, shared=tmp_path / "shared", pinned={}, chain=chain, stage=stage,
                               benchmark=benchmark, skill=skill,
                               context=_context(tmp_path, unit_root, client, attempt, budget), workers=2,
                               previous=previous)


COUNTS = {"cells", "unknown", "unknown_by_kind", "unknown_by_reason", "infrastructure"}


def test_a_unit_records_counts_only_and_test_scores_stay_sealed(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    units = []
    _test_panel(monkeypatch, SEARCH_TESTS, units=units)
    chain, client = tmp_path / "E-glm", _Client()
    unit_root = chain / "s0" / "evaluation" / "searchqa"
    record = _evaluate(tmp_path, unit_root, client)
    assert units == ["E-glm/s0/evaluation/searchqa"] and client.calls == 4
    assert record["status"] == "complete" and set(record["counts"]) == COUNTS and record["counts"]["cells"] == 4
    assert evaluation.monitor([unit_root]) == [{"unit": "E-glm/s0/evaluation/searchqa", "status": "complete",
                                                **record["counts"]}]
    with pytest.raises(ValueError):  # a completed unit is not run again
        _evaluate(tmp_path, unit_root, client, attempt=2)
    with pytest.raises(ValueError, match="sealed"):
        evaluation.unseal(chain, "E-glm", [unit_root], run=RUN)
    (chain / "chain-complete.json").write_text("{}")
    assert evaluation.unseal(chain, "E-glm", [unit_root], run=RUN) == {
        "E-glm/s0/evaluation/searchqa": {"q0": "pass", "q1": "fail", "q2": "pass", "q3": "fail"}}


def test_a_chain_unseals_only_its_own_units(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    other = tmp_path / "I-glm" / "s0" / "evaluation" / "searchqa"
    _evaluate(tmp_path, other, _Client(), chain="I-glm")
    chain = tmp_path / "E-glm"
    (chain / "chain-complete.json").parent.mkdir(parents=True)
    (chain / "chain-complete.json").write_text("{}")
    with pytest.raises(ValueError, match="another chain"):
        evaluation.unseal(chain, "E-glm", [other], run=RUN)
    moved = chain / "s0" / "evaluation" / "searchqa"
    moved.parent.mkdir(parents=True)
    other.rename(moved)
    with pytest.raises(ValueError, match="another chain"):  # inside the directory, but another chain's record
        evaluation.unseal(chain, "E-glm", [moved], run=RUN)


def test_a_byte_identical_skill_reuses_the_previous_stage_s_unit(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    chain, client = tmp_path / "E-glm", _Client()
    first = chain / "s0" / "evaluation" / "searchqa"
    _evaluate(tmp_path, first, client)
    second, third = chain / "s1" / "evaluation" / "searchqa", chain / "s2" / "evaluation" / "searchqa"
    reused = _evaluate(tmp_path, second, client, stage=1, previous=first)
    again = _evaluate(tmp_path, third, client, stage=2, previous=second)
    assert reused["status"] == again["status"] == "reused" and client.calls == 4
    changed = _evaluate(tmp_path, chain / "s3" / "evaluation" / "searchqa", client, stage=3, skill="new skill",
                        previous=third)
    assert changed["status"] == "complete" and client.calls == 8
    (chain / "chain-terminated.json").write_text("{}")
    tokens = evaluation.unseal(chain, "E-glm", [first, third], run=RUN)
    assert tokens["E-glm/s2/evaluation/searchqa"] == tokens["E-glm/s0/evaluation/searchqa"]


def test_a_unit_is_reused_only_from_its_predecessor_and_never_leaves_an_attempt_behind(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    chain, client = tmp_path / "E-glm", _Client()
    first = chain / "s0" / "evaluation" / "searchqa"
    _evaluate(tmp_path, first, client)
    skipped = chain / "s2" / "evaluation" / "searchqa"
    with pytest.raises(ValueError, match="predecessor"):  # stage 0 is not stage 2's predecessor
        _evaluate(tmp_path, skipped, client, stage=2, previous=first)
    other = tmp_path / "I-glm" / "s1" / "evaluation" / "searchqa"
    with pytest.raises(ValueError, match="predecessor"):  # nor is another chain's unit
        _evaluate(tmp_path, other, client, stage=1, previous=first, chain="I-glm")
    assert client.calls == 4 and not list(skipped.glob("attempt-*")) and not list(other.glob("attempt-*"))


def test_a_registered_shared_stage0_evaluation_is_reused_by_its_member_chains_only(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "SHARED_STAGE0", {"stage0-glm": ("E-glm", "SkillOpt-glm", "GEPA-glm")})  # v1's
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    client = _Client()
    shared_unit = tmp_path / "stage0-glm" / "s0" / "evaluation" / "searchqa"
    _evaluate(tmp_path, shared_unit, client, chain="stage0-glm")
    for chain in ("E-glm", "SkillOpt-glm", "GEPA-glm"):
        reused = _evaluate(tmp_path, tmp_path / chain / "s0" / "evaluation" / "searchqa", client, chain=chain,
                           previous=shared_unit)
        assert reused["status"] == "reused" and reused["chain"] == chain
    assert client.calls == 4
    with pytest.raises(ValueError, match="predecessor"):  # I-glm starts from its own Skill
        _evaluate(tmp_path, tmp_path / "I-glm" / "s0" / "evaluation" / "searchqa", client, chain="I-glm",
                  previous=shared_unit)
    with pytest.raises(ValueError, match="predecessor"):  # shared only at stage 0
        _evaluate(tmp_path, tmp_path / "E-glm" / "s1" / "evaluation" / "searchqa", client, chain="E-glm", stage=1,
                  previous=shared_unit)
    (tmp_path / "E-glm" / "chain-complete.json").write_text("{}")
    unit = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    assert evaluation.unseal(tmp_path / "E-glm", "E-glm", [unit], run=RUN) == {
        "E-glm/s0/evaluation/searchqa": {"q0": "pass", "q1": "fail", "q2": "pass", "q3": "fail"}}


def test_v2_shares_no_stage0_evaluation(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    client = _Client()
    shared_unit = tmp_path / "stage0-glm" / "s0" / "evaluation" / "searchqa"
    _evaluate(tmp_path, shared_unit, client, chain="stage0-glm")
    for chain in ("E-glm", "NoSkill-glm", "SkillOpt-glm"):  # v2 §1: E-glm's scaffold is not the empty Skill
        with pytest.raises(ValueError, match="predecessor"):
            _evaluate(tmp_path, tmp_path / chain / "s0" / "evaluation" / "searchqa", client, chain=chain,
                      previous=shared_unit)
    assert client.calls == 4


def test_a_unit_owned_by_another_process_is_not_evaluated(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    client, unit_root = _Client(), tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    with exclusive(unit_root / ".lock"):
        with pytest.raises(ValueError, match="Another process owns"):
            _evaluate(tmp_path, unit_root, client)
    assert client.calls == 0 and not list(unit_root.glob("attempt-*"))


def test_missing_infrastructure_above_a_tenth_of_the_cells_pauses_the_unit(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    client, unit_root = _Client(TRANSPORT), tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    with pytest.raises(Pause) as stop:
        _evaluate(tmp_path, unit_root, client)
    assert stop.value.kind == "infrastructure_incomplete" and client.calls == 4 * (MAX_RESENDS + 1)
    status = read_json(unit_root / "attempt-1" / "status.json", sealed=True)
    assert status["kind"] == "infrastructure_incomplete" and status["counts"]["infrastructure"] == 4
    assert not (unit_root / "unit.json").exists()
    assert evaluation.monitor([unit_root]) == [{"unit_root": str(unit_root), "status": "open", "attempts": 1,
                                                "cells_done": 4}]
    with pytest.raises(ValueError):  # a new attempt runs in a new directory
        _evaluate(tmp_path, unit_root, _Client())
    with pytest.raises(ValueError, match="owner's recorded decision"):  # never retried without the owner
        _evaluate(tmp_path, unit_root, _Client(), attempt=2)
    _recover(unit_root / "attempt-1")
    with pytest.raises(ValueError):  # and only in the next attempt directory
        _evaluate(tmp_path, unit_root, _Client(), attempt=3)
    assert _evaluate(tmp_path, unit_root, _Client(), attempt=2)["attempt"] == "attempt-2"


def test_the_monitor_reads_the_latest_attempt_by_number(tmp_path):
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    for attempt, cells in (("attempt-9", 9), ("attempt-10", 1), ("attempt-x", 5), ("attempt-011", 5),
                           ("attempt-\u00b2", 5), ("attempt-\u0663", 5)):  # a superscript two, an Arabic-Indic three
        (unit_root / attempt / "cells").mkdir(parents=True)
        for n in range(cells):
            (unit_root / attempt / "cells" / ("%d.json" % n)).write_text("{}")
    (unit_root / "attempt-12").write_text("not a directory")
    assert evaluation.monitor([unit_root]) == [{"unit_root": str(unit_root), "status": "open", "attempts": 2,
                                                "cells_done": 1}]
    assert [a.name for a in evaluation.attempts(unit_root)] == ["attempt-9", "attempt-10"]
    assert evaluation._next_attempt(unit_root) is None  # attempt-10 holds no owner decision
    _recover(unit_root / "attempt-10")
    assert evaluation._next_attempt(unit_root) == unit_root / "attempt-11"


def test_a_unit_is_never_reused_or_unsealed_across_runs(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    client = _Client()
    old = tmp_path / "old" / "E-glm" / "s0" / "evaluation" / "searchqa"
    old_shared = tmp_path / "old" / "stage0-glm" / "s0" / "evaluation" / "searchqa"
    _evaluate(tmp_path, old, client, run="an-earlier-run")
    _evaluate(tmp_path, old_shared, client, run="an-earlier-run", chain="stage0-glm")
    calls = client.calls
    new = tmp_path / "new" / "E-glm"
    with pytest.raises(ValueError, match="predecessor"):  # same chain, stage, bench, settings and Skill
        _evaluate(tmp_path, new / "s1" / "evaluation" / "searchqa", client, stage=1, previous=old)
    with pytest.raises(ValueError, match="predecessor"):  # nor an earlier run's shared stage 0
        _evaluate(tmp_path, new / "s0" / "evaluation" / "searchqa", client, previous=old_shared)
    assert client.calls == calls and not list(new.rglob("attempt-*"))
    (tmp_path / "old" / "E-glm" / "chain-complete.json").write_text("{}")
    with pytest.raises(ValueError, match="another run"):
        evaluation.unseal(tmp_path / "old" / "E-glm", "E-glm", [old], run=RUN)
    assert evaluation.unseal(tmp_path / "old" / "E-glm", "E-glm", [old], run="an-earlier-run")


def test_a_test_panel_that_differs_from_the_first_evaluation_s_pauses_the_unit(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    _evaluate(tmp_path, tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa", _Client())
    _test_panel(monkeypatch, SEARCH_TESTS, panel_hash="another-hash")
    unit_root = tmp_path / "I-glm" / "s0" / "evaluation" / "searchqa"
    with pytest.raises(Pause) as stop:
        _evaluate(tmp_path, unit_root, _Client())
    assert stop.value.kind == "configuration"
    assert read_json(unit_root / "attempt-1" / "status.json", sealed=True)["kind"] == "configuration"


def test_alfworld_is_evaluated_only_with_the_frozen_game_data_path(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "alfworld"
    with pytest.raises(Pause) as stop:
        _evaluate(tmp_path, unit_root, _Client(), benchmark="alfworld")
    assert stop.value.kind == "configuration" and "ALFWORLD_DATA" in stop.value.reason


# ----------------------------------------------------------------- nothing of a test set leaves a sealed record (§0)
SENTINEL = "SEALED_TEST_CONTENT"


def _display(message, category, filename, lineno, file=None, line=None):
    """The interpreter's own display of a warning (pytest records them instead): onto sys.stderr, as it is then."""
    (file or sys.stderr).write(warnings.formatwarning(message, category, filename, lineno, line))


def _diagnostics(shared):
    return "".join(p.read_text() for p in (shared / "host_only" / "diagnostics").glob("*.log"))


class _Noisy(_Client):
    """A solver call that also writes what it saw to every channel of the process."""

    def call(self, system, user):
        print(SENTINEL + "-print")
        sys.stderr.write(SENTINEL + "-stderr\n")
        warnings.warn(SENTINEL + "-warning")
        os.write(2, (SENTINEL + "-fd\n").encode())
        subprocess.run([sys.executable, "-c", "import sys; sys.stderr.write('%s-child')" % SENTINEL], check=True)
        return super().call(system, user)


def test_whatever_an_evaluation_writes_to_the_process_output_stays_sealed(tmp_path, monkeypatch, capfd):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.showwarning = _display
        _evaluate(tmp_path, tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa", _Noisy())
        print("after the unit")  # the process output is back
    out, err = capfd.readouterr()
    assert SENTINEL not in out + err and "after the unit" in out
    sealed = _diagnostics(tmp_path / "shared")
    for channel in ("print", "stderr", "warning", "fd", "child"):
        assert SENTINEL + "-" + channel in sealed


def _print_area_workbook(value):
    """A workbook whose print area is a defined name openpyxl cannot read: it warns, quoting the value."""
    book = openpyxl.Workbook()
    book.active["A1"] = 1
    plain = io.BytesIO()
    book.save(plain)
    patched = io.BytesIO()
    with zipfile.ZipFile(plain) as source, zipfile.ZipFile(patched, "w") as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/workbook.xml":  # "<definedNames/>" with lxml, "<definedNames />" without
                content, count = re.subn(rb"<definedNames\s*/>", b'<definedNames><definedName name="_xlnm.Print_Area" '
                                         b'localSheetId="0">' + value.encode() + b"</definedName></definedNames>", content)
                assert count == 1
            target.writestr(item, content)
    return base64.b64encode(patched.getvalue()).decode()


def test_the_workbook_check_s_warning_quoting_a_workbook_stays_sealed(tmp_path, capfd):
    prediction = {"status": "available", "reason": "model_response_available",
                  "output": {"cases": [{"status": "available", "output_base64": _print_area_workbook(SENTINEL)}]}}
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.showwarning = _display
        assert preflight("spreadsheetbench", prediction, [REPLY]) is None  # a valid workbook, still to be scored
        assert SENTINEL in capfd.readouterr().err  # the channel exists outside a unit
        with evaluation.contained(tmp_path / "shared") as path:
            assert preflight("spreadsheetbench", prediction, [REPLY]) is None
    out, err = capfd.readouterr()
    assert SENTINEL not in out + err and SENTINEL in path.read_text()


class _Odd(_Client):
    """The first call: what the frozen client makes of a provider reply whose finish reason quotes test text."""

    def call(self, system, user):
        self.calls += 1
        if self.calls > 1:
            return self.reply
        return {"ok": False, "response": "x", "finish_reason": SENTINEL, "usage": USAGE,
                "error_type": "finish_" + SENTINEL, "attempts": [{"status": 200, "seconds": 0.1}],
                "returned_model": "glm-5.3"}


def test_provider_text_reaches_neither_the_ledger_nor_the_monitor(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")
    tasks = [dict(SEARCH_TESTS[0], task_id="q%d" % n) for n in range(12)]  # one unknown: below a tenth
    _test_panel(monkeypatch, tasks)
    ledger = Budget(tmp_path / "ledger", poll=0)
    ledger.declare({OVERALL: 10 ** 9})
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    record = _evaluate(tmp_path, unit_root, _Odd(), budget=ledger)
    assert record["status"] == "complete"
    assert record["counts"]["unknown_by_reason"] == {"11:unclassified:other": 1}
    public = json.dumps(evaluation.monitor([unit_root])) + (tmp_path / "ledger" / "events.jsonl").read_text()
    assert SENTINEL not in public + (unit_root / "unit.json").read_text()
    settled = [json.loads(line) for line in (tmp_path / "ledger" / "events.jsonl").read_text().splitlines()]
    assert {e["detail"]["error_type"] for e in settled if e["event"] == "settle"} == {None, "other"}
    sealed = "".join(p.read_text() for p in (unit_root / "attempt-1" / "cells").glob("*.json"))
    assert SENTINEL in sealed  # the cell keeps the receipt as received


def test_a_configuration_error_raised_outside_coevo5_is_reported_by_its_type_only(tmp_path, monkeypatch):
    _consent(tmp_path / "shared")

    def test_panel(pinned, benchmark, *, access):
        return int(SENTINEL)  # e.g. a malformed test field

    monkeypatch.setattr(data, "test_panel", test_panel)
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    with pytest.raises(Pause) as stop:
        _evaluate(tmp_path, unit_root, _Client())
    assert (stop.value.kind, stop.value.reason) == ("configuration", "ValueError")
    assert SENTINEL not in (unit_root / "attempt-1" / "status.json").read_text()


def test_an_unexpected_error_pauses_the_unit_by_its_type_and_location_only(tmp_path, monkeypatch, capfd):
    _consent(tmp_path / "shared")

    def test_panel(pinned, benchmark, *, access):
        raise KeyError(SENTINEL)

    monkeypatch.setattr(data, "test_panel", test_panel)
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    with pytest.raises(Pause) as stop:
        _evaluate(tmp_path, unit_root, _Client())
    assert (stop.value.kind, stop.value.reason) == ("exception", "KeyError")
    assert stop.value.__context__ is None and stop.value.__cause__ is None
    status = read_json(unit_root / "attempt-1" / "status.json", sealed=True)
    assert status["stack"][-1].endswith(":test_panel") and SENTINEL not in json.dumps(status)
    out, err = capfd.readouterr()
    assert SENTINEL not in out + err and SENTINEL in _diagnostics(tmp_path / "shared")  # the full traceback


def test_output_still_buffered_when_a_unit_ends_is_sealed_too(tmp_path, capfd):
    cached = open(1, "w", closefd=False)  # a stream on fd 1 kept from before the unit: buffered, not sys.stdout
    try:
        with evaluation.contained(tmp_path / "shared") as path:
            cached.write(SENTINEL + "-cached")
            ctypes.CDLL(None).printf((SENTINEL + "-printf").encode())  # C stdio, no newline: still buffered
        cached.write("after the unit")
        cached.flush()
    finally:
        cached.close()
    out, err = capfd.readouterr()
    assert SENTINEL not in out + err and "after the unit" in out
    assert SENTINEL + "-cached" in path.read_text() and SENTINEL + "-printf" in path.read_text()


def test_a_lazy_proxy_in_the_process_does_not_break_the_containment(tmp_path):
    class Proxy:  # like openai's module client: computing its class runs code that may fail
        @property
        def __class__(self):
            raise RuntimeError("the proxy loaded its client")

    proxy = Proxy()
    with evaluation.contained(tmp_path / "shared") as path:
        print(SENTINEL)
    assert SENTINEL in path.read_text() and proxy is not None


def _full():
    return OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))


@pytest.mark.parametrize("failing", ["status", "diagnostics"])
def test_an_error_that_cannot_be_recorded_still_leaves_the_unit_without_its_content(tmp_path, monkeypatch, capfd,
                                                                                     failing):
    _consent(tmp_path / "shared")

    def test_panel(pinned, benchmark, *, access):
        raise KeyError(SENTINEL)

    monkeypatch.setattr(data, "test_panel", test_panel)
    if failing == "status":
        write_json = evaluation.write_json

        def write(path, value):
            if path.name == "status.json":
                raise _full()
            return write_json(path, value)

        monkeypatch.setattr(evaluation, "write_json", write)
    else:
        def print_exc(*args, **kwargs):
            raise _full()

        monkeypatch.setattr(evaluation.traceback, "print_exc", print_exc)
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    with pytest.raises(Pause) as stop:
        _evaluate(tmp_path, unit_root, _Client())
    assert (stop.value.kind, stop.value.reason) == ("exception", "OSError" if failing == "status" else "KeyError")
    assert stop.value.__context__ is None and stop.value.__cause__ is None
    shown = "".join(traceback.format_exception(stop.value))
    out, err = capfd.readouterr()
    assert SENTINEL not in shown + out + err
    assert (unit_root / "attempt-1" / "status.json").exists() == (failing == "diagnostics")
    assert (SENTINEL in _diagnostics(tmp_path / "shared")) == (failing == "status")


class _Full:
    """A diagnostics file that cannot take what is still buffered (a full disk)."""

    def __init__(self, sink):
        self.sink = sink

    def fileno(self):
        return self.sink.fileno()

    def write(self, text):
        return self.sink.write(text)

    def flush(self):
        raise _full()

    def close(self):
        self.sink.close()


def test_output_that_cannot_all_be_sealed_is_discarded_from_then_on(tmp_path, monkeypatch, capfd):
    sink = evaluation._sink
    monkeypatch.setattr(evaluation, "_sink", lambda path: _Full(sink(path)))
    saved = os.dup(1), os.dup(2), sys.stdout, sys.stderr
    try:
        with pytest.raises(evaluation.ContainmentFailure, match="OSError"):
            with evaluation.contained(tmp_path / "shared"):
                pass
        assert evaluation._CONTAINED == {"depth": 0, "saved": None}
        null = os.stat(os.devnull)
        assert os.path.samestat(os.fstat(1), null) and os.path.samestat(os.fstat(2), null)
        os.write(1, SENTINEL.encode())
        print(SENTINEL, flush=True)
    finally:
        discarded = sys.stdout
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        sys.stdout, sys.stderr = saved[2], saved[3]
        for descriptor in saved[:2]:
            os.close(descriptor)
        if discarded is not saved[2]:
            discarded.close()
    out, err = capfd.readouterr()
    assert SENTINEL not in out + err


def test_a_unit_whose_sealed_output_cannot_be_flushed_is_not_complete(tmp_path, monkeypatch, capfd):
    _consent(tmp_path / "shared")
    _test_panel(monkeypatch, SEARCH_TESTS)
    sink = evaluation._sink
    monkeypatch.setattr(evaluation, "_sink", lambda path: _Full(sink(path)))
    unit_root = tmp_path / "E-glm" / "s0" / "evaluation" / "searchqa"
    saved = os.dup(1), os.dup(2), sys.stdout, sys.stderr
    try:
        with pytest.raises(Exception):
            _evaluate(tmp_path, unit_root, _Client())
    finally:
        discarded = sys.stdout
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        sys.stdout, sys.stderr = saved[2], saved[3]
        for descriptor in saved[:2]:
            os.close(descriptor)
        if discarded is not saved[2]:
            discarded.close()
    assert not (unit_root / "unit.json").exists() and (unit_root / "attempt-1").is_dir()
    assert evaluation._next_attempt(unit_root) is None  # the redo needs the owner's decision
