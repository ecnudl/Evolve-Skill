"""coevo5 cells (registration §5.4): one arm solves one task once through the frozen backends and the call wrapper;
the decision table's remedies are applied without replacing a delivered answer (re-execution replays the stored reply,
rescoring uses a fresh scoring directory, an episode that never called the model restarts); records are written once
and a stop of the run is recorded, then raised."""
import base64
import io
import json

import openpyxl
import pytest

from skillopt.coevo5 import budget as budget_module
from skillopt.coevo5 import cells
from skillopt.coevo5.budget import OVERALL, Budget
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.cells import Context, Pause, cell_id, run_cell, run_cells
from skillopt.coevo5.protocol import MAX_REEXECUTIONS, MAX_RESCORES, RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _Client:
    def __init__(self, *receipts):
        self.queue, self.requests = list(receipts), []

    def call(self, system, user):
        self.requests.append((system, user))
        return self.queue.pop(0)


def _reply(text):
    return {"ok": True, "response": text, "finish_reason": "stop", "error_type": None, "usage": USAGE,
            "attempts": [{"status": 200}]}


TRANSPORT = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "transport",
             "attempts": [{"error": "ReadTimeout"}] * 4}


def _context(tmp_path, client, runtime=None, budget=None):
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 2),
                        budget=budget, scopes=(OVERALL,) if budget is not None else (), sleep=lambda _: None)
    return Context(store=tmp_path / "unit" / "attempt-1", endpoint=endpoint, runtime=runtime or RUNTIME,
                   native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                   episodes=Slots(tmp_path / "slots", "alfworld-episode", 1))


def _cell(benchmark, task_id="t1", arm="parent", run=0):
    unit = "E-glm/s1/round-1"
    return {"id": cell_id(unit, arm, task_id, run), "unit": unit, "arm": arm, "benchmark": benchmark,
            "task_id": task_id, "run": run}


SEARCH = {"public": {"question": "Capital of France?", "context": ["Paris is the capital."]},
          "private": {"answers": ["Paris"]}}


def test_a_scored_cell_keeps_the_official_result_and_writes_its_record_once(tmp_path):
    context = _context(tmp_path, _Client(_reply("<answer>Paris</answer>")))
    record = run_cell(context, _cell("searchqa"), SEARCH, "skill text")
    assert record["final"]["token"] == "pass" and record["final"]["row"] == "10"
    assert record["official"] == {"status": "pass", "reason": "repository_searchqa_native_em"}
    assert len(record["sends"]) == 1 and record["stop"] is None
    path = context.store / "cells" / (_cell("searchqa")["id"] + ".json")
    assert read_json(path, sealed=True) == record
    with pytest.raises(ValueError):
        run_cell(context, _cell("searchqa"), SEARCH, "skill text")


def test_a_call_that_never_delivered_is_an_infrastructure_unknown_after_the_resends(tmp_path):
    client = _Client(TRANSPORT, TRANSPORT, TRANSPORT)
    record = run_cell(_context(tmp_path, client), _cell("searchqa"), SEARCH, "")
    assert (record["final"]["outcome"], record["final"]["kind"], record["final"]["row"]) == (
        "unknown", "infrastructure", "4")
    assert len(client.requests) == 3 and len(set(client.requests)) == 1


def test_a_stop_is_recorded_then_raised_as_a_pause(tmp_path):
    context = _context(tmp_path, _Client(["not a mapping"]))
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell("searchqa"), SEARCH, "")
    assert stop.value.kind == "configuration"
    record = read_json(context.store / "cells" / (_cell("searchqa")["id"] + ".json"), sealed=True)
    assert record["final"] is None and record["stop"]["kind"] == "configuration"
    assert record["attempts"][0]["verdict"] is None  # the attempt is kept, without a verdict


def test_an_unexpected_error_interrupts_the_unit_without_a_score(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "score", lambda *args, **kwargs: 1 / 0)
    with pytest.raises(Pause) as stop:
        run_cell(_context(tmp_path, _Client(_reply("<answer>Paris</answer>"))), _cell("searchqa"), SEARCH, "")
    assert (stop.value.kind, stop.value.reason) == ("exception", "ZeroDivisionError")


def test_a_claimed_cell_never_runs_again_whichever_process_tries(tmp_path):
    client = _Client(_reply("<answer>Paris</answer>"))
    context = _context(tmp_path, client)
    (context.store / "cells").mkdir(parents=True)
    (context.store / "cells" / (_cell("searchqa")["id"] + ".claim")).touch()
    with pytest.raises(ValueError):
        run_cell(context, _cell("searchqa"), SEARCH, "")
    assert client.requests == []


# --------------------------------------------------------------------------------------------- SpreadsheetBench
def _xlsx(tmp_path, name):
    book = openpyxl.Workbook()
    book.active["A1"] = 1
    path = tmp_path / name
    book.save(path)
    return str(path)


def _workbook_b64():
    book = openpyxl.Workbook()
    book.active["A1"] = 2
    buffer = io.BytesIO()
    book.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode()


SHEET_RUNTIME = {**RUNTIME, "spreadsheetbench": {key: RUNTIME["spreadsheetbench"][key] for key in (
    "code_extraction_version", "spreadsheet_preview_version", "_stop_on_cleanup_failure")}}
PROGRAM = "```python\nimport openpyxl\n```"


def _sheet_task(tmp_path):
    return {"public": {"instruction": "Put 2 in A1.", "input_files": [_xlsx(tmp_path, "1_init.xlsx")],
                       "answer_position": "A1"},
            "private": {"test_files": [_xlsx(tmp_path, "1_golden.xlsx")], "answer_position": "A1"}}


def _sheet(monkeypatch, generations, scores):
    """Patch the frozen sandbox (one result per execution) and the frozen scorer (one result per scoring)."""
    executions, scorings = list(generations), list(scores)
    seen = {"executions": 0, "contexts": []}

    def native(request, runtime):
        assert request["operation"] == "spreadsheet_generate"
        seen["executions"] += 1
        return executions.pop(0)

    def score(benchmark, public, private, prediction, *, runtime=None):
        seen["contexts"].append(runtime.get("_score_context"))
        if prediction.get("status") != "available":
            return {"status": "unknown", "reason": prediction.get("reason"), "metrics": {}}
        return scorings.pop(0)

    monkeypatch.setattr(backends, "_native", native)
    monkeypatch.setattr(backends, "score", score)
    return seen


DELIVERED = {"status": "available", "output_base64": _workbook_b64(), "reason": "isolated_workbook_generated",
             "cleanup_confirmed": True}
TIMEOUT = {"status": "unknown", "reason": "native_timeout"}


def _scored(*statuses):
    cases = [{"status": status, "reason": reason} for status, reason in statuses]
    status = "fail" if any(c["status"] == "fail" for c in cases) else (
        "unknown" if any(c["status"] == "unknown" for c in cases) else "pass")
    return {"status": status, "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
            "metrics": {"cases": cases}}


def test_a_timed_out_program_is_re_executed_from_its_stored_reply_without_a_model_call(tmp_path, monkeypatch):
    seen = _sheet(monkeypatch, [TIMEOUT, DELIVERED], [_scored(("pass", "cell_values_match"))])
    client = _Client(_reply(PROGRAM))
    record = run_cell(_context(tmp_path, client, SHEET_RUNTIME), _cell("spreadsheetbench"), _sheet_task(tmp_path), "")
    assert record["final"]["token"] == "pass" and record["remedies"] == {"reexecute": 1}
    assert len(client.requests) == 1 and seen["executions"] == 2 and len(record["sends"]) == 1
    assert [a["step"] for a in record["attempts"]] == ["solve", "reexecute"]
    assert record["attempts"][0]["score"] is None  # the generation already asked for a re-execution: not scored
    (scoring,) = seen["contexts"]
    assert scoring["artifact_dir"].endswith(scoring["position"])


def test_a_program_that_keeps_timing_out_is_a_program_defect_never_scored(tmp_path, monkeypatch):
    seen = _sheet(monkeypatch, [TIMEOUT] * (MAX_REEXECUTIONS + 1), [])
    record = run_cell(_context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME), _cell("spreadsheetbench"),
                      _sheet_task(tmp_path), "")
    assert (record["final"]["outcome"], record["final"]["kind"]) == ("fail", "program_defect")
    assert record["remedies"] == {"reexecute": MAX_REEXECUTIONS} and record["spent"] == ["reexecute"]
    assert seen["contexts"] == []
    assert record["official"] == {"status": None, "reason": "not_scored:decided_before_scoring"}


def test_an_invalid_workbook_fails_before_the_native_scorer(tmp_path, monkeypatch):
    invalid = {**DELIVERED, "output_base64": base64.b64encode(b"not a workbook").decode()}
    seen = _sheet(monkeypatch, [invalid], [])
    record = run_cell(_context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME), _cell("spreadsheetbench"),
                      _sheet_task(tmp_path), "")
    assert (record["final"]["token"], record["final"]["row"]) == ("fail", "9b") and seen["contexts"] == []
    assert record["official"]["reason"] == "not_scored:decided_before_scoring"


def test_a_cleanup_failure_of_the_generation_pauses_before_the_native_scorer(tmp_path, monkeypatch):
    unconfirmed = {"status": "unknown", "reason": "container_cleanup_unconfirmed", "cleanup_confirmed": False}
    seen = _sheet(monkeypatch, [unconfirmed], [])
    context = _context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME)
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell("spreadsheetbench"), _sheet_task(tmp_path), "")
    assert stop.value.kind == "cleanup" and seen["contexts"] == []
    record = read_json(context.store / "cells" / (_cell("spreadsheetbench")["id"] + ".json"), sealed=True)
    assert record["attempts"][0]["score"] is None and record["final"] is None


def test_answers_and_scores_are_stored_once_by_content_and_referenced_by_hash(tmp_path, monkeypatch):
    unjudged = _scored(("unknown", "prediction:recalculation_timeout"))
    _sheet(monkeypatch, [DELIVERED], [unjudged, _scored(("pass", "cell_values_match"))])
    context = _context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME)
    record = run_cell(context, _cell("spreadsheetbench"), _sheet_task(tmp_path), "")
    first, second = record["attempts"]
    assert second["step"] == "rescore" and first["prediction"] == second["prediction"]
    assert DELIVERED["output_base64"] not in json.dumps(record)
    stored = read_json(context.store / "artifacts" / (first["prediction"]["sha256"] + ".json"))
    assert stored["output"]["cases"][0]["output_base64"] == DELIVERED["output_base64"]
    assert first["score"]["cases"] == [{"status": "unknown", "reason": "prediction:recalculation_timeout"}]
    assert len(list((context.store / "artifacts").glob("*.json"))) == 3  # one answer, two scores


def test_unjudgeable_workbooks_are_rescored_in_fresh_directories_then_kept_unknown(tmp_path, monkeypatch):
    unjudged = _scored(("unknown", "prediction:recalculation_timeout"))
    seen = _sheet(monkeypatch, [DELIVERED], [unjudged] * (MAX_RESCORES + 1))
    record = run_cell(_context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME), _cell("spreadsheetbench"),
                      _sheet_task(tmp_path), "")
    assert record["final"]["token"] == "unknown_artifact" and record["remedies"] == {"rescore": MAX_RESCORES}
    assert seen["executions"] == 1 and len({c["position"] for c in seen["contexts"]}) == MAX_RESCORES + 1


def test_rescoring_still_happens_after_re_executions_run_out(tmp_path, monkeypatch):
    two_cases = _sheet_task(tmp_path)
    two_cases["public"]["input_files"].append(_xlsx(tmp_path, "2_init.xlsx"))
    two_cases["private"]["test_files"].append(_xlsx(tmp_path, "2_golden.xlsx"))
    unavailable = {"status": "unknown", "reason": "docker_unavailable"}
    executions = [unavailable, DELIVERED] * (MAX_REEXECUTIONS + 1)
    scores = [_scored(("unknown", "docker_unavailable"), ("unknown", "prediction:recalculation_timeout"))] * (
        MAX_REEXECUTIONS + 1) + [_scored(("unknown", "docker_unavailable"), ("fail", "cell_values_differ"))]
    seen = _sheet(monkeypatch, executions, scores)
    record = run_cell(_context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME), _cell("spreadsheetbench"),
                      two_cases, "")
    assert record["remedies"] == {"reexecute": MAX_REEXECUTIONS, "rescore": 1}
    # every execution with a workbook to judge is scored (a failing case would decide the task before re-execution)
    assert all(a["score"] is not None for a in record["attempts"]) and len(seen["contexts"]) == MAX_REEXECUTIONS + 2
    assert record["final"]["token"] == "fail"  # the rescored second case failed: the task fails (9d)


def test_a_failing_case_decides_the_task_before_a_pending_re_execution(tmp_path, monkeypatch):
    seen = _sheet(monkeypatch, [DELIVERED, TIMEOUT], [_scored(("fail", "cell_values_differ"),
                                                               ("unknown", "native_timeout"))])
    two_cases = _sheet_task(tmp_path)
    two_cases["public"]["input_files"].append(_xlsx(tmp_path, "2_init.xlsx"))
    two_cases["private"]["test_files"].append(_xlsx(tmp_path, "2_golden.xlsx"))
    record = run_cell(_context(tmp_path, _Client(_reply(PROGRAM)), SHEET_RUNTIME), _cell("spreadsheetbench"),
                      two_cases, "")
    assert (record["final"]["token"], record["final"]["row"]) == ("fail", "9c") and record["remedies"] == {}
    assert seen["executions"] == 2 and len(seen["contexts"]) == 1


# ------------------------------------------------------------------------------------------------------- ALFWorld
class _Won:
    def reset(self):
        return ["You are in a room. Your task is to look."], None, [{"admissible_commands": ["look"]}]

    def step(self, actions):
        return ["Done."], None, [1], [True], [{"admissible_commands": ["look"], "won": True}]

    def close(self):
        pass


def test_an_episode_that_failed_before_any_model_call_restarts(tmp_path, monkeypatch):
    starts = []

    def new(public, runtime):
        starts.append(1)
        if len(starts) == 1:
            raise RuntimeError("worker failed to start")
        return _Won()

    monkeypatch.setattr(backends, "_new_alfworld", new)
    runtime = {**RUNTIME, "alfworld": {**RUNTIME["alfworld"], "max_steps": 3}}
    client = _Client(_reply("<action>look</action>"))
    record = run_cell(_context(tmp_path, client, runtime), _cell("alfworld"),
                      {"public": {"game_file": "game.tw-pddl"}, "private": {}}, "")
    assert record["final"]["token"] == "pass" and record["remedies"] == {"restart": 1}
    assert [a["step"] for a in record["attempts"]] == ["solve", "restart"] and len(record["sends"]) == 1


class _Unfinished(_Won):
    def step(self, actions):
        return ["Nothing happens."], None, [0], [False], [{"admissible_commands": ["look"], "won": False}]


def test_a_receipt_beyond_the_bound_ends_the_episode_halts_the_ledger_and_pauses(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_new_alfworld", lambda public, runtime: _Unfinished())
    ledger = _ledger(tmp_path)
    over = {**_reply("<action>look</action>"), "usage": {"prompt_tokens": 10, "completion_tokens": 101,
                                                          "total_tokens": 111}}
    client = _Client(over, _reply("<action>look</action>"), _reply("<action>look</action>"))
    runtime = {**RUNTIME, "alfworld": {**RUNTIME["alfworld"], "max_steps": 3}}
    context = _context(tmp_path, client, runtime, budget=ledger)
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell("alfworld"), {"public": {"game_file": "game.tw-pddl"}, "private": {}}, "")
    assert stop.value.kind == "assumption" and len(client.requests) == 1
    assert ledger.snapshot()["halted"]["reason"] == "reported_usage_beyond_reservation_bound"
    record = read_json(context.store / "cells" / (_cell("alfworld")["id"] + ".json"), sealed=True)
    assert record["sends"][0]["assumption_broken"] is True and record["final"] is None


def _ledger(tmp_path):
    ledger = Budget(tmp_path / "ledger", poll=0)
    ledger.declare({OVERALL: 10 ** 9})
    return ledger


def test_a_reservation_the_ledger_could_not_record_pauses_the_cell_before_any_call(tmp_path, monkeypatch):
    ledger, real, failures = _ledger(tmp_path), budget_module.os.replace, []

    def once(*args):
        if not failures:
            failures.append(1)
            raise OSError("state not replaced")
        return real(*args)

    monkeypatch.setattr(budget_module.os, "replace", once)
    client = _Client(_reply("<answer>Paris</answer>"))
    context = _context(tmp_path, client, budget=ledger)
    with pytest.raises(Pause) as stop:  # the frozen solver swallowed the exception; the wrapper's flag did not
        run_cell(context, _cell("searchqa"), SEARCH, "")
    assert stop.value.kind == "ledger" and client.requests == []
    record = read_json(context.store / "cells" / (_cell("searchqa")["id"] + ".json"), sealed=True)
    assert record["final"] is None and record["sends"][0]["ledger_failure"] == "ledger_commit_failed:OSError"
    view = ledger.snapshot()
    assert view[OVERALL]["open"] == 0 and view["halted"]["reason"] == "ledger_commit_failed:OSError"


def test_a_settlement_the_ledger_could_not_record_pauses_the_cell_keeping_the_receipt(tmp_path, monkeypatch):
    ledger = _ledger(tmp_path)

    def unwritable(self, *args, **kwargs):
        raise OSError("disk")

    monkeypatch.setattr(Budget, "settle", unwritable)
    client = _Client(_reply("<answer>Paris</answer>"), _reply("<answer>Paris</answer>"))
    context = _context(tmp_path, client, budget=ledger)
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell("searchqa"), SEARCH, "")
    assert stop.value.kind == "ledger" and len(client.requests) == 1
    record = read_json(context.store / "cells" / (_cell("searchqa")["id"] + ".json"), sealed=True)
    assert record["sends"][0]["receipt"]["response"] == "<answer>Paris</answer>" and record["final"] is None
    with pytest.raises(Pause):  # the endpoint is latched: the next cell sends nothing
        run_cell(context, _cell("searchqa", "t2"), SEARCH, "")
    assert len(client.requests) == 1 and ledger.snapshot()["halted"]["reason"] == "ledger_failure:OSError"


# --------------------------------------------------------------------------------------------------------- units
def test_a_pause_stops_dispatching_further_cells(tmp_path):
    context = _context(tmp_path, _Client(["not a mapping"], _reply("<answer>Paris</answer>")))
    jobs = [(_cell("searchqa", "t%d" % k), SEARCH, "") for k in range(3)]
    with pytest.raises(Pause):
        run_cells(context, jobs, workers=1)
    assert len(list((context.store / "cells").glob("*.json"))) == 1


def test_any_error_stops_dispatching_further_jobs():
    started = []

    def function(job):
        started.append(job)
        raise ValueError("Another process owns this cell")

    with pytest.raises(ValueError):
        cells.run_parallel(function, [1, 2, 3], workers=1)
    assert started == [1]


def test_units_return_records_in_job_order(tmp_path):
    replies = [_reply("<answer>Paris</answer>"), _reply("<answer>Rome</answer>")]
    context = _context(tmp_path, _Client(*replies))
    jobs = [(_cell("searchqa", "t%d" % k), SEARCH, "") for k in range(2)]
    records = run_cells(context, jobs, workers=1)
    assert [r["cell"]["task_id"] for r in records] == ["t0", "t1"]
    assert [r["final"]["token"] for r in records] == ["pass", "fail"]


def test_cell_ids_are_stable_and_distinct():
    assert cells.cell_id("u", "arm", "t", 0) == cells.cell_id("u", "arm", "t", 0) != cells.cell_id("u", "arm", "t", 1)
