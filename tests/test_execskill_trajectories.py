"""T-TRAJ-1 and the trajectory views (implementation plan §1 trajectories row, §2.3, §8; registration §7.1 after
Codex F10): trajectories written by real route-B cells over the fake ALFWorld games and fixture QA/sheet items, the
landmark view, the masked detector and examiner views, the whitelist and the unit loader. Offline and deterministic."""
from __future__ import annotations

import json

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json
from skillopt.execskill import trajectories
from skillopt.execskill.cells import Arm, Context, TrainingStore, cell_id, run_cell
from skillopt.execskill.package import Package, empty
from skillopt.execskill.protocol import BENCHES, LANDMARK_STEPS, record
from skillopt.execskill.trajectories import Excluded, landmark_view, mask_answers, masked_view, whitelisted
from skillopt.execskill.units import run_unit
from tests.execskill_fakes_env import FakeNative, FakeSandbox, alf_sessions, procedure
from tests.fixtures.execskill.items import (alfworld_games, alfworld_items, officeqa_items, searchqa_items,
                                            spreadsheetbench_items)

EVIDENCE = "engineering_fixture"
CARD = "Read the public material before answering."
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
EMPTY = empty(step="s0", evidence=EVIDENCE)
BASE = set(alfworld_games()[0]["admissible_commands"])
TRANSPORT = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "transport",
             "attempts": [{"error": "ReadTimeout"}] * 4}
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": "sha256:" + "0" * 64, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
SHEET = procedure("fx-sheet", ("applies", "sheet_feedback"), origin="spreadsheetbench", requests_second_call=True)


def _reply(text):
    return {"ok": True, "response": text, "finish_reason": "stop", "error_type": None, "usage": dict(USAGE),
            "attempts": [{"status": 200}]}


class _Client:
    """Replies by a function of the request; ``censor_after``: every call after that many delivered replies gets an
    undelivered receipt (the Recorder resends it, then gives up)."""

    def __init__(self, answer, *, censor_after=None):
        self.answer, self.censor_after, self.delivered, self.requests = answer, censor_after, 0, []

    def call(self, system, user):
        self.requests.append((system, user))
        if self.censor_after is not None and self.delivered >= self.censor_after:
            return dict(TRANSPORT)
        self.delivered += 1
        return _reply(self.answer(json.loads(user)))


def follow(view):
    """The fake games' winning policy: the plan step the game offers, else the first place of the plan."""
    extra = [c for c in view["admissible_commands"] if c not in BASE]
    if extra:
        return "<action>%s</action>" % extra[0]
    return "<action>go to %s</action>" % ("cabinet 1" if "a mug" in view["initial_observation"] else "countertop 1")


def stall(view):
    return "<action>look</action>"


def _context(root, client, runtime=None, worker=None):
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(root / "slots", "glm-5.3", 2),
                        sleep=lambda _: None)
    return Context(attempt=root / "unit" / "attempt-1", endpoint=endpoint, runtime=runtime or {
        **RUNTIME, "spreadsheetbench": SHEET_RUNTIME}, cards={bench: CARD for bench in BENCHES},
        native=Slots(root / "slots", "spreadsheet-native", 1), episodes=Slots(root / "slots", "alfworld-episode", 1),
        worker=worker or (lambda bench: FakeSandbox()), evidence=EVIDENCE)


def _run(root, item, client, *, arm=None, runtime=None, worker=None, unit="G/s2-alfworld/run"):
    context = _context(root, client, runtime, worker)
    task = item["benchmark"] + "/" + item["task_id"]
    cell = {"id": cell_id(unit, "S", task, 0), "unit": unit, "arm": "S", "benchmark": item["benchmark"],
            "task_id": task, "run": 0}
    found = run_cell(context, cell, item, arm or Arm("parent", EMPTY), store=TrainingStore(context.attempt))
    return found, read_json(context.attempt / "trajectories" / (cell["id"] + ".json"))


# ----------------------------------------------------------------------------------------------------- T-TRAJ-1
def test_t_traj_1_the_landmark_view_keeps_ten_nonterminal_steps_of_long_episodes_only(tmp_path, monkeypatch):
    sessions = alf_sessions(monkeypatch)
    items = alfworld_items(tmp_path / "games")
    short_win, long_win = _run(tmp_path / "c0", items[0], _Client(follow)), _run(tmp_path / "c6", items[6],
                                                                                   _Client(follow))
    long_fail = _run(tmp_path / "c7", items[7], _Client(stall))  # 50 steps, never won
    censored_late = _run(tmp_path / "c8", items[8], _Client(follow, censor_after=12))
    censored_early = _run(tmp_path / "c9", items[9], _Client(follow, censor_after=3))
    short_runtime = {**RUNTIME, "alfworld": {**RUNTIME["alfworld"], "max_steps": 5}}
    short_fail = _run(tmp_path / "c10", items[10], _Client(stall), runtime=short_runtime)
    assert [r["final"]["token"] for r, _ in (short_win, long_win, long_fail, censored_late, censored_early,
                                             short_fail)] == ["pass", "pass", "fail", "unknown", "unknown", "fail"]
    assert len(short_win[1]["alfworld_steps"]) == 3 and len(long_win[1]["alfworld_steps"]) == 18
    assert len(long_fail[1]["alfworld_steps"]) == 50 and len(censored_late[1]["alfworld_steps"]) == 12
    # excluded: ended within 10 steps (by outcome), or censored by infrastructure
    assert landmark_view(short_win[1]) == Excluded("ended_by_step_10:won")
    assert landmark_view(short_fail[1]) == Excluded("ended_by_step_10:done")
    assert landmark_view(censored_early[1]) == Excluded("ended_by_step_10:infrastructure")
    assert landmark_view(censored_late[1]) == Excluded("censored:infrastructure")
    # included: exactly the first 10 (observation, action) pairs, nothing terminal and no length
    won, failed = landmark_view(long_win[1]), landmark_view(long_fail[1])
    for view, trajectory in ((won, long_win[1]), (failed, long_fail[1])):
        assert set(view) == {"bench", "steps"} and len(view["steps"]) == LANDMARK_STEPS
        assert all(set(step) == {"observation", "action"} for step in view["steps"])
        assert [s["action"] for s in view["steps"]] == [s["action"] for s in trajectory["alfworld_steps"][:10]]
        text = json.dumps(view)
        assert "You won" not in text and "won" not in view and "done" not in view
    assert won["steps"][0]["observation"].startswith("-= Welcome to TextWorld")
    assert won != failed and json.dumps(won).count("observation") == json.dumps(failed).count("observation")
    # the views of a 18-step win and a 50-step failure have the same shape: no step budget to read
    assert masked_view(long_win[1], bench="alfworld", purpose="detector") == won
    assert masked_view(long_win[1], bench="alfworld", purpose="examiner") == {**won, "passed": True}
    assert masked_view(short_win[1], bench="alfworld", purpose="examiner") == Excluded("ended_by_step_10:won")
    assert all(session.closed for session in sessions)


def test_alfworld_trajectories_carry_the_steps_but_never_the_environment_extras(tmp_path, monkeypatch):
    alf_sessions(monkeypatch)
    item = alfworld_items(tmp_path / "games")[6]
    found, trajectory = _run(tmp_path / "c", item, _Client(follow))
    steps = trajectory["alfworld_steps"]
    assert [s["i"] for s in steps] == list(range(18)) and steps[0]["reply"].startswith("<action>")
    assert steps[-1]["post_observation"].endswith("You won!") and steps[0]["observation"] == json.loads(
        trajectory["calls"][0]["user"])["observation"]
    text = json.dumps(trajectory)
    assert "expert_plan" not in text and "game.tw-pddl" not in text and "extra." not in text
    assert set(whitelisted(trajectory)) == set(trajectories.TOP)
    assert found["judge"]["format"]["steps"] == 18 and "judge" not in whitelisted(trajectory)
    leaked = json.loads(trajectory["calls"][0]["user"])
    leaked["extra.gamefile"] = "hidden"
    fields = {k: v for k, v in trajectory.items() if k not in ("version", "evidence", "record_sha256")}
    fields["calls"] = [{**trajectory["calls"][0], "user": json.dumps(leaked)}] + trajectory["calls"][1:]
    with pytest.raises(ValueError, match="hidden_environment_data"):
        whitelisted(record("trajectory", EVIDENCE, fields))
    with pytest.raises(ValueError):  # a trajectory changed after sealing
        whitelisted({**trajectory, "token": "fail"})


# --------------------------------------------------------------------------------------------- masked views
def test_qa_masked_views_hide_every_answer_carrier(tmp_path):
    item = searchqa_items(1)[0]
    _, trajectory = _run(tmp_path / "a", item, _Client(lambda view: "Clue read.\n<answer>Fixtown 0</answer>"),
                         unit="G/s1-searchqa/run")
    view = masked_view(trajectory, bench="searchqa", purpose="detector")
    assert view == {"bench": "searchqa", "task": json.loads(trajectory["calls"][0]["user"]), "notes": None,
                    "replies": ["Clue read.\n<answer>[masked]</answer>"]}
    assert masked_view(trajectory, bench="searchqa", purpose="examiner") == {**view, "passed": True}
    assert mask_answers("searchqa", "I think\nFixtown 0\n") == "I think\n[masked]\n"
    assert mask_answers("officeqa", 'Result {"answer": "200"} <answer>2') == 'Result {"answer": "[masked]"} <answer>[masked]'
    assert mask_answers("livemath", '{"answer": 12.5}') == '{"answer": "[masked]"}'
    assert mask_answers("officeqa", "No carrier here") == "No carrier here" and mask_answers("searchqa", None) is None
    item = officeqa_items(1)[0]
    _, trajectory = _run(tmp_path / "b", item, _Client(lambda view: '{"answer": "200"}'), unit="G/s2-officeqa/run")
    assert "200" not in json.dumps(masked_view(trajectory, bench="officeqa", purpose="detector")["replies"])


def test_sheet_masked_view_hides_the_run_status_and_the_repair(tmp_path, monkeypatch):
    FakeNative(report={"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Sheet2'"}).install(
        monkeypatch)
    monkeypatch.setattr(backends, "score", lambda *args, **kwargs: {
        "status": "fail", "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
        "metrics": {"cases": [{"status": "fail", "reason": "cell_values_differ"}]}})
    worker = lambda bench: FakeSandbox({"fx-sheet": {"sheet_feedback": lambda view, report, state: {  # noqa: E731
        "fields": {"warnings": ["a sheet is missing"]}, "request_repair": report["status"] == "exception"}}})
    item = spreadsheetbench_items(tmp_path / "items", 1)[0]
    replies = iter([PROGRAM, PROGRAM.replace("A1:A5", "A1:A6")])
    found, trajectory = _run(tmp_path / "s", item, _Client(lambda view: next(replies)),
                             arm=Arm("candidate", Package((SHEET,), "fixture", EVIDENCE)), worker=worker,
                             unit="G/s1-spreadsheetbench/run")
    assert [c["purpose"] for c in trajectory["calls"]] == ["first", "repair"]
    assert trajectory["shell"]["precheck"]["status"] == "exception"
    view = masked_view(trajectory, bench="spreadsheetbench", purpose="detector")
    assert view["replies"] == [PROGRAM] and view["notes"] is None and set(view) == {"bench", "task", "notes",
                                                                                     "replies"}
    text = json.dumps(view)
    assert "KeyError" not in text and "run_report" not in text and "exception" not in text and "A1:A6" not in text


# ------------------------------------------------------------------------------------------------ unit loader
def test_load_run_reads_a_completed_units_trajectories_in_order(tmp_path):
    items = searchqa_items(3)
    unit_root = tmp_path / "chain" / "s1-searchqa" / "run"
    identity = {"unit": "G/s1-searchqa/run"}

    def work(attempt):
        endpoint = Endpoint(_Client(lambda view: "<answer>Fixtown 1</answer>"), model="glm-5.3", max_tokens=100,
                            slots=Slots(tmp_path / "slots", "glm-5.3", 2), sleep=lambda _: None)
        context = Context(attempt=attempt, endpoint=endpoint, runtime=RUNTIME, cards={b: CARD for b in BENCHES},
                          native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                          episodes=Slots(tmp_path / "slots", "alfworld-episode", 1),
                          worker=lambda bench: FakeSandbox(), evidence=EVIDENCE)
        for item in reversed(items):
            task = "searchqa/" + item["task_id"]
            cell = {"id": cell_id(identity["unit"], "S", task, 0), "unit": identity["unit"], "arm": "S",
                    "benchmark": "searchqa", "task_id": task, "run": 0}
            run_cell(context, cell, item, Arm("parent", EMPTY), store=TrainingStore(attempt))
        return {"cells": len(items)}

    with pytest.raises(FileNotFoundError):
        trajectories.load_run(unit_root)
    run_unit(unit_root, run="fixture-run", identity=identity, work=work, evidence=EVIDENCE)
    loaded = trajectories.load_run(unit_root)
    assert [t["task_id"] for t in loaded] == ["searchqa/" + i["task_id"] for i in items]
    assert [t["token"] for t in loaded] == ["fail", "pass", "fail"]
    assert len(trajectories.enable_log(unit_root / "attempt-1")) == 3


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_7_a_restated_answer_is_masked_with_the_carrier():
    reply = "The orchard is Gravenstein  orchard, so the answer is gravenstein orchard.\n<answer>Gravenstein Orchard</answer>"
    masked = mask_answers("searchqa", reply)
    assert "gravenstein" not in masked.lower() and masked.count("[masked]") == 3
    number = mask_answers("officeqa", "Receipts were 1,718 then; total 1718.0. <answer>1718</answer> (not 17180)")
    assert "1,718" not in number and "1718.0" not in number and "17180" in number
    choices = "A. 12 apples\n\nB. 30 apples\n\nC. 42 apples\n\nD. 7 apples\n\nE. None of the above"
    option = mask_answers("livemath", "Counting gives 42 apples, which is option C.\n(C)\n<answer>C</answer>",
                          choices=choices)
    assert "42 apples" not in option and "option C" not in option and "(C)" not in option
    assert "12 apples" not in option or True  # other options' text is public and may stay
    assert mask_answers("searchqa", "No carrier, last line\nOkavango River") == "No carrier, last line\n[masked]"
