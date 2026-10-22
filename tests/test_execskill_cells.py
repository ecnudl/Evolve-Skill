"""T-CELLS-1..4 and T-ID-1 in the copied cell loop (implementation plan §1 cells row, §2.8, §8; registration §2.5,
§4.4 P3/P5, §8.1; Codex F12, F13): one route-B cell through the shell, the frozen call wrapper, the route-B decision
rows and the judge, with its record, trajectory and enable-log line. Offline and deterministic: scripted receipts
behind the frozen Endpoint, FakeSandbox workers, the fake native runs of tests/execskill_fakes_env.py."""
from __future__ import annotations

import base64
import io
from dataclasses import replace

import openpyxl
import pytest

from skillopt.coevo5.budget import OVERALL, Budget
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.code_delivery import extract_python
from skillopt.continual_eval.core import read_json
from skillopt.execskill import router, solver, trajectories
from skillopt.execskill.cells import Arm, Context, Pause, TrainingStore, cell_id, run_cell, run_cells, share_cell
from skillopt.execskill.errors import (BudgetStop, ConsumptionConflict, PackageInvalid, SandboxUnavailable,
                                       stop_kind)
from skillopt.execskill.package import Package, empty
from skillopt.execskill.protocol import BENCHES, NOTES_KEY, kind, verified
from tests.execskill_fakes_env import FakeNative, FakeSandbox, procedure
from tests.fixtures.execskill.items import officeqa_items, searchqa_items, spreadsheetbench_items

EVIDENCE = "engineering_fixture"
CARD = "Read the public material before answering."
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
UNIT = "G/s1-spreadsheetbench/accept"
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": "sha256:" + "0" * 64, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
RUNTIMES = {**RUNTIME, "spreadsheetbench": SHEET_RUNTIME}
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
REPAIRED = PROGRAM.replace("A1:A5", "A1:A6")
ERROR_REPORT = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Sheet2'"}
FACTS = procedure("fx-facts", ("applies", "before_call"))
SHEET = procedure("fx-sheet", ("applies", "sheet_feedback"), origin="spreadsheetbench", requests_second_call=True)
TRANSPORT = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "error_type": "transport",
             "attempts": [{"error": "ReadTimeout"}] * 4}
TIMEOUT = {"status": "unknown", "reason": "native_timeout"}
PASSED = {"status": "pass", "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
          "metrics": {"cases": [{"status": "pass", "reason": "cell_values_match"}]}}


def _workbook_b64():
    book = openpyxl.Workbook()
    book.active["B1"] = 15
    buffer = io.BytesIO()
    book.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode()


DELIVERED = {"status": "available", "output_base64": _workbook_b64(), "reason": "isolated_workbook_generated",
             "cleanup_confirmed": True}


def _reply(text):
    return {"ok": True, "response": text, "finish_reason": "stop", "error_type": None, "usage": dict(USAGE),
            "attempts": [{"status": 200}]}


class _Client:
    def __init__(self, *receipts):
        self.queue, self.requests = list(receipts), []

    def call(self, system, user):
        self.requests.append((system, user))
        return self.queue.pop(0)


def package(*procedures):
    return Package(tuple(procedures), "fixture", EVIDENCE)


def code(reply):
    return extract_python(reply)["code"]


def _context(tmp_path, client, *, worker=None, budget=None, solve=solver.solve):
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(tmp_path / "slots", "glm-5.3", 2),
                        budget=budget, scopes=(OVERALL,) if budget is not None else (), sleep=lambda _: None)
    return Context(attempt=tmp_path / "unit" / "attempt-1", endpoint=endpoint, runtime=RUNTIMES,
                   cards={bench: CARD for bench in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                   episodes=Slots(tmp_path / "slots", "alfworld-episode", 1),
                   worker=worker or (lambda bench: FakeSandbox()), evidence=EVIDENCE, solve=solve)


def _cell(item, arm="S'", run=0, unit=UNIT):
    task = item["benchmark"] + "/" + item["task_id"]
    return {"id": cell_id(unit, arm, task, run), "unit": unit, "arm": arm, "benchmark": item["benchmark"],
            "task_id": task, "run": run}


def _sheet(monkeypatch, generations, scores, report=ERROR_REPORT):
    """The fake pre-check (FakeNative), one scripted result per program execution, one per scoring."""
    fake = FakeNative(report=report).install(monkeypatch)
    executions, scorings, seen = list(generations), list(scores), {"codes": [], "contexts": []}

    def native(request, runtime):
        seen["codes"].append(request["code"])
        return executions.pop(0)

    def score(benchmark, public, private, prediction, *, runtime=None):
        seen["contexts"].append(runtime.get("_score_context"))
        if prediction.get("status") != "available":
            return {"status": "unknown", "reason": prediction.get("reason"), "metrics": {}}
        return scorings.pop(0)

    monkeypatch.setattr(backends, "_native", native)
    monkeypatch.setattr(backends, "score", score)
    return fake, seen


def _sheet_workers(made, notes=("the sheet named in the program is missing",)):
    """A worker factory: a fresh FakeSandbox per cell whose sheet_feedback asks for one repair after an exception;
    the k-th sandbox gives ``notes[k]`` (the last one after that)."""
    def make(bench):
        note = notes[min(len(made), len(notes) - 1)]
        made.append(FakeSandbox({"fx-sheet": {"sheet_feedback": lambda view, report, state: {
            "fields": {"warnings": [note]}, "request_repair": report["status"] == "exception"}}}))
        return made[-1]
    return make


def _artifact(context, attempt):
    return read_json(context.attempt / "artifacts" / (attempt["prediction"]["sha256"] + ".json"))


# ------------------------------------------------------------------------------------------------- T-CELLS-1, 2
def test_t_cells_1_2_a_two_call_cell_re_executes_by_replaying_its_logical_calls_in_order(tmp_path, monkeypatch):
    fake, seen = _sheet(monkeypatch, [TIMEOUT, DELIVERED], [PASSED])
    client, made = _Client(_reply(PROGRAM), _reply(REPAIRED)), []
    context = _context(tmp_path, client, worker=_sheet_workers(made))
    item = spreadsheetbench_items(tmp_path / "items", 1)[0]
    record = run_cell(context, _cell(item), item, Arm("candidate", package(SHEET)), store=TrainingStore(context.attempt))
    # T-CELLS-1: the timed-out repaired program is re-executed from BOTH stored replies, in order; nothing pauses
    assert record["stop"] is None and record["final"]["token"] == "pass" and record["remedies"] == {"reexecute": 1}
    assert [a["step"] for a in record["attempts"]] == ["solve", "reexecute"]
    assert len(client.requests) == 2 and seen["codes"] == [code(REPAIRED), code(REPAIRED)]
    assert [(c["purpose"], c["receipt_index"]) for c in record["logical_calls"]] == [("first", 0), ("repair", 1)]
    assert len(made) == 2 and all(s.closed for s in made)  # the re-execution ran on a fresh worker
    # T-CELLS-2: the pre-check ran once; the re-execution read the stored report back
    first, again = (_artifact(context, a) for a in record["attempts"])
    assert len(fake.prechecks) == 1 and again["shell"]["precheck"] == first["shell"]["precheck"]
    assert first["shell"]["precheck"]["status"] == "exception"
    assert record["deciding_receipt"] == 1 and record["worst_delivery"] == "delivered"
    assert record["judge"]["v2"]["token"] == "pass" and record["official"]["status"] == "pass"


def test_t_cells_1_a_replay_that_presents_another_request_is_p3_and_never_pauses(tmp_path, monkeypatch):
    _, seen = _sheet(monkeypatch, [TIMEOUT, DELIVERED], [])
    client, made = _Client(_reply(PROGRAM), _reply(REPAIRED)), []
    context = _context(tmp_path, client, worker=_sheet_workers(made, notes=("first advice", "other advice")))
    item = spreadsheetbench_items(tmp_path / "items", 1)[0]
    record = run_cell(context, _cell(item), item, Arm("candidate", package(SHEET)), store=TrainingStore(context.attempt))
    assert record["stop"] is None and record["remedies"] == {"reexecute": 1}
    assert (record["final"]["kind"], record["final"]["row"], record["final"]["token"]) == ("fault", "P3",
                                                                                          "unknown_fault")
    assert record["judge"]["v2"]["token"] == "unknown_fault" and len(client.requests) == 2
    assert record["fault_kinds"] == {"replay_request_mismatch": 1}
    assert _artifact(context, record["attempts"][1])["reason"] == "replay_request_mismatch"
    # the re-executed shell got the first reply, its repair request differed: it fell back to the first program;
    # the P3 prediction is scored host-side as unknown and never executed again
    assert seen["codes"] == [code(REPAIRED), code(PROGRAM)] and len(seen["contexts"]) == 1


# ---------------------------------------------------------------------------------------------------- T-CELLS-4
def test_t_cells_4_a_resent_call_and_a_repair_replay_as_two_logical_calls(tmp_path, monkeypatch):
    _sheet(monkeypatch, [TIMEOUT, DELIVERED], [PASSED])
    ledger = Budget(tmp_path / "ledger", poll=0)
    ledger.declare({OVERALL: 10 ** 9})
    client = _Client(TRANSPORT, _reply(PROGRAM), _reply(REPAIRED))
    context = _context(tmp_path, client, worker=_sheet_workers([]), budget=ledger)
    item = spreadsheetbench_items(tmp_path / "items", 1)[0]
    cell = _cell(item)
    record = run_cell(context, cell, item, Arm("candidate", package(SHEET)), store=TrainingStore(context.attempt))
    assert record["final"]["token"] == "pass" and record["remedies"] == {"reexecute": 1}
    # three transport sends, two logical calls: the replay served the program and the repair, never the resent reply
    assert len(client.requests) == 3 and len(record["sends"]) == 3
    assert record["sends"][0]["receipt"]["error_type"] == "transport"
    assert [(c["purpose"], c["receipt_index"], c["send_indices"]) for c in record["logical_calls"]] == [
        ("first", 0, [0, 1]), ("repair", 1, [2])]
    # the ledger still counts every send, the undelivered one included
    assert all("charged" in send for send in record["sends"]) and record["sends"][0]["charged"] > 0
    assert ledger.snapshot()[OVERALL]["settled"] == sum(send["charged"] for send in record["sends"])
    # persisted: the record, and the trajectory with the logical calls and the two replies
    assert verified(read_json(context.attempt / "cells" / (cell["id"] + ".json")), "cell") == record
    trajectory = verified(read_json(context.attempt / "trajectories" / (cell["id"] + ".json")), "trajectory")
    assert trajectory["logical_calls"] == record["logical_calls"] and trajectory["replies"] == [PROGRAM, REPAIRED]
    assert [c["receipt"]["delivery"] for c in trajectory["calls"]] == ["delivered", "delivered"]


# ------------------------------------------------------------------------------------- the record and the store
def test_a_qa_cell_stores_its_record_trajectory_and_enable_line_once(tmp_path):
    item = searchqa_items(1)[0]
    sandbox = FakeSandbox({"fx-facts": {"before_call": lambda view, state: {"facts": ["Fixture note 0 is short"]}}})
    client = _Client(_reply("<answer>Fixtown 0</answer>"))
    context = _context(tmp_path, client, worker=lambda bench: sandbox)
    clock = iter([100.0, 107.5])
    context.clock = lambda: next(clock)
    cell = {**_cell(item, unit="G/s2-officeqa/run"), "set": "real", "block": "b1"}
    store = TrainingStore(context.attempt)
    record = run_cell(context, cell, item, Arm("candidate", package(FACTS)), store=store)
    assert record["version"] == kind("cell") and record["evidence"] == EVIDENCE and verified(record, "cell")
    assert (record["arm"], record["task_id"], record["run"], record["set"], record["block"]) == (
        "S'", cell["task_id"], 0, "real", "b1")
    assert record["package_sha256"] == package(FACTS).sha256 and record["arm_kind"] == "candidate"
    assert record["enabled"] == ["fx-facts"] and record["withheld"] == [] and record["faults"] == []
    assert (record["dispatch_ts"], record["finish_ts"]) == (100.0, 107.5)
    assert record["final"]["token"] == "pass" and record["judge"]["v2"]["token"] == "pass"
    assert record["shared_with"] is None and record["deciding_receipt"] == 0
    assert NOTES_KEY in client.requests[0][1] and sandbox.closed
    found = verified(read_json(context.attempt / "trajectories" / (cell["id"] + ".json")), "trajectory")
    assert found["token"] == "pass" and found["calls"][0]["purpose"] == "first"
    (line,) = trajectories.enable_log(context.attempt)
    assert (line["arm"], line["item"], line["enabled"], line["applies"]) == ("S'", cell["task_id"], ["fx-facts"],
                                                                             {"fx-facts": True})
    assert line["route_sha256"] == found["route"]["record_sha256"]
    with pytest.raises(ValueError):
        run_cell(context, cell, item, Arm("candidate", package(FACTS)), store=store)


class _Closing(FakeSandbox):
    """A worker with one restart whose close confirms one removal (``sandbox.client.Worker`` records both)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.restarts = [{"cause": "gone", "container": "execskill-sbx-" + "a" * 32, "procedure": "fx-facts"}]
        self.cleanups = []

    def close(self):
        super().close()
        self.cleanups.append({"container": "execskill-sbx-" + "b" * 32, "seconds": 1.5})


def test_c5_4_a_cell_record_carries_its_workers_restarts_and_cleanups(tmp_path):
    item = searchqa_items(1)[0]
    sandbox = _Closing({"fx-facts": {"before_call": lambda view, state: {"facts": ["Fixture note 0 is short"]}}})
    context = _context(tmp_path, _Client(_reply("<answer>Fixtown 0</answer>")), worker=lambda bench: sandbox)
    record = run_cell(context, _cell(item), item, Arm("candidate", package(FACTS)), store=TrainingStore(context.attempt))
    assert verified(record, "cell")["sandbox"] == {
        "restarts": [{"cause": "gone", "container": "execskill-sbx-" + "a" * 32, "procedure": "fx-facts",
                      "step": "solve"}],
        "cleanups": [{"container": "execskill-sbx-" + "b" * 32, "seconds": 1.5, "step": "solve"}]}
    assert record["faults"] == [] and record["final"]["token"] == "pass"  # neither is a fault nor a pause
    card = run_cell(context, _cell(item, arm="C"), item, Arm("card", empty(step="s0", evidence=EVIDENCE)),
                    store=TrainingStore(context.attempt))
    assert card["sandbox"] == {"restarts": [], "cleanups": []}  # no procedure for the bench: no worker


def test_run_cells_runs_jobs_on_threads_and_keeps_job_order(tmp_path):
    items = searchqa_items(4)
    client = _Client(*[_reply("<answer>Fixtown %d</answer>" % n) for n in range(4)])
    context = _context(tmp_path, client)
    card = Arm("card", empty(step="s0", evidence=EVIDENCE))
    jobs = [(_cell(item, arm="C"), item, card) for item in items]
    records = run_cells(context, jobs, workers=3, store=TrainingStore(context.attempt))
    assert [r["cell"]["id"] for r in records] == [job[0]["id"] for job in jobs]
    assert all(r["enabled"] == [] and r["arm_kind"] == "card" for r in records)


# ---------------------------------------------------------------------------------------------------- T-CELLS-3
def test_t_cells_3_structural_zero_sharing_links_the_card_cell(tmp_path):
    item = searchqa_items(1)[0]
    context = _context(tmp_path, _Client(_reply("<answer>Fixtown 0</answer>")))
    store = TrainingStore(context.attempt)
    unit = "G/test-read"
    source = run_cell(context, _cell(item, arm="C", unit=unit), item, Arm("card", empty(step="s0", evidence=EVIDENCE)),
                      store=store)
    final = package(FACTS)

    def routed(applies):
        worker = FakeSandbox({"fx-facts": {"applies": lambda view: applies}}).start(final, kind="cell")
        return router.route(final, "searchqa", solver.routing_view("searchqa", item["public"]), worker).to_json()

    shared = share_cell(context, _cell(item, arm="F", unit=unit), item, Arm("candidate", final), source,
                        routed(False), store=store)
    assert shared["shared_with"] == source["cell"]["id"] and shared["sends"] == [] and shared["enabled"] == []
    assert (shared["final"], shared["official"], shared["judge"]) == (source["final"], source["official"],
                                                                      source["judge"])
    assert shared["package_sha256"] == final.sha256 and verified(shared, "cell")
    assert shared["sandbox"] == {"restarts": [], "cleanups": []}
    with pytest.raises(ValueError):  # a package that enables a procedure on the item runs its own cell
        share_cell(context, _cell(item, arm="P_F", unit=unit), item, Arm("placebo_y", final), source, routed(True),
                   store=store)
    with pytest.raises(ValueError):  # the route of another package
        share_cell(context, _cell(item, arm="T_F", unit=unit), item, Arm("text", package(SHEET)), source,
                   routed(False), store=store)
    with pytest.raises(ValueError):  # a shared cell is never itself a source
        share_cell(context, _cell(item, arm="F2", unit=unit), item, Arm("candidate", final), shared, routed(False),
                   store=store)


# ------------------------------------------------------------------------------------ T-ID-1 in the cell loop
@pytest.mark.parametrize("error", [PackageInvalid("bad package"), ConsumptionConflict("item consumed"),
                                   SandboxUnavailable("sandbox_image_missing")])
def test_t_id_1_route_b_stops_from_the_shell_pause_with_their_kind(tmp_path, error):
    def solve(*args, **kwargs):
        raise error

    item = searchqa_items(1)[0]
    context = _context(tmp_path, _Client(), solve=solve)
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell(item), item, Arm("parent", package(FACTS)), store=TrainingStore(context.attempt))
    assert stop.value.kind == stop_kind(error) != "exception"
    record = verified(read_json(context.attempt / "cells" / (_cell(item)["id"] + ".json")), "cell")
    assert record["stop"]["kind"] == stop.value.kind and record["final"] is None and record["judge"] is None
    assert not (context.attempt / "trajectories").exists()


def test_t_id_1_a_real_sandbox_stop_and_a_real_budget_stop(tmp_path):
    item = searchqa_items(1)[0]
    failing = FakeSandbox(raises={("fx-facts", "applies"): SandboxUnavailable("sandbox_slot_timeout")})
    context = _context(tmp_path / "a", _Client(_reply("<answer>x</answer>")), worker=lambda bench: failing)
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell(item), item, Arm("candidate", package(FACTS)), store=TrainingStore(context.attempt))
    assert stop.value.kind == "sandbox" and failing.closed
    ledger = Budget(tmp_path / "ledger", poll=0)
    ledger.declare({OVERALL: 1})
    client = _Client(_reply("<answer>x</answer>"))
    context = _context(tmp_path / "b", client, budget=ledger)
    with pytest.raises(Pause) as stop:
        run_cell(context, _cell(item, arm="C"), item, Arm("card", empty(step="s0", evidence=EVIDENCE)),
                 store=TrainingStore(context.attempt))
    assert stop.value.kind == "budget" == stop_kind(BudgetStop("x")) and client.requests == []
    record = verified(read_json(context.attempt / "cells" / (_cell(item, arm="C")["id"] + ".json")), "cell")
    assert record["refused"] is True and record["stop"]["kind"] == "budget"


def test_arms_are_registered_kinds():
    base = empty(step="s0", evidence=EVIDENCE)
    for name in ("candidate", "card", "withhold:p-officeqa-1-1", "restore:fx-a", "gen:G_acc"):
        assert Arm(name, base).kind == name
    for name in ("", "withhold:", "candidates", "gen"):
        with pytest.raises(ValueError):
            Arm(name, base)
    with pytest.raises(ValueError):
        Arm("candidate", "not a package")


def test_codex4_each_cell_of_a_mixed_unit_is_sent_by_its_own_benchs_endpoint(tmp_path):
    """Codex finding #4 (registration §4.1, §5.5): a unit whose cells run on several benches (a later step's
    self-test) holds one endpoint per bench (``Context.endpoints``); each cell is sent by its own bench's endpoint --
    its client and its bound B -- while a unit with one endpoint sends every cell by it; a cell on a bench without an
    endpoint, an endpoint of another model or of an unknown bench is refused."""
    sq_item, oq_item = searchqa_items(1)[0], officeqa_items(1)[0]
    sq_client = _Client(_reply("<answer>Fixtown 0</answer>"))
    oq_client = _Client(_reply("<answer>%s</answer>" % oq_item["private"]["answer"]))
    context = _context(tmp_path, sq_client)
    slots_ = Slots(tmp_path / "slots", "glm-5.3", 2)
    oq_endpoint = Endpoint(oq_client, model="glm-5.3", max_tokens=200, slots=slots_, sleep=lambda _: None)
    assert context.endpoint_of("officeqa") is context.endpoint  # one endpoint: every cell's
    mixed = replace(context, endpoints={"searchqa": context.endpoint, "officeqa": oq_endpoint})
    assert mixed.endpoint_of("officeqa") is oq_endpoint and mixed.endpoint_of("searchqa") is context.endpoint
    parent, store = Arm("parent", empty(step="G/s0", evidence=EVIDENCE)), TrainingStore(mixed.attempt)
    records = {item["benchmark"]: run_cell(mixed, _cell(item, arm="S"), item, parent, store=store)
               for item in (sq_item, oq_item)}
    assert len(sq_client.requests) == len(oq_client.requests) == 1
    assert [send["max_tokens"] for send in records["searchqa"]["sends"]] == [100]
    assert [send["max_tokens"] for send in records["officeqa"]["sends"]] == [200]
    with pytest.raises(ValueError, match="no endpoint for"):
        mixed.endpoint_of("livemath")
    other = Endpoint(oq_client, model="deepseek-v4.1-flash-1017", max_tokens=200, slots=slots_, sleep=lambda _: None)
    for endpoints in ({"officeqa": other}, {"webshop": oq_endpoint}):
        with pytest.raises(ValueError, match="one solver model"):
            replace(context, endpoints=endpoints)
