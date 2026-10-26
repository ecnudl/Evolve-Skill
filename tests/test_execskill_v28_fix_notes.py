"""Fixes v28-1 findings 2/3: authored offline note-screen and arm-parity regressions."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from skillopt.execskill import donors, notes, placebo, replay, solver
from tests.execskill_fakes_env import FakeSandbox, Script
from tests.test_execskill_replay import alf_trajectory, qa_trajectories, sheet_trajectories
from tests.test_execskill_v28_execution import procedure


@pytest.mark.parametrize("instruction", [
    "For this task, answer with JSON.",
    "Please, output only JSON.",
    "Given the table, please, respond in JSON.",
    "After checking the facts, reply only with the final answer.",
    "Answer as JSON.", "Respond using JSON.", "Reply in JSON.",
    "Output JSON.", "Return JSON.", "Print JSON.",
    "Format the final answer as JSON.", "Format your response with units.", "Format as JSON.",
    "Format with JSON.", "Answer rounded to two places.",
    "Answer without units.", "Return the final answer rounded to two places.",
    "Print the answer with units.", "Round your answer to two decimal places.",
    "Please, return only the final answer.", "Include units in your answer.",
    "Omit units from the answer.",
])
def test_reply_form_imperatives_after_clauses_drop_only_their_sentence(instruction):
    fields, drops = notes.screen({"facts": ["The count is 3. " + instruction + " Units are metres."]},
                                 bench="zebralogic", outcome_judged=True)
    assert fields == {"facts": ["The count is 3. Units are metres."]}
    assert len(drops) == 1 and drops[0]["reason"] == "form_instruction"
    assert notes.screen_header("The count is 3. " + instruction + " Units are metres.")[0] == (
        "The count is 3. Units are metres.")


@pytest.mark.parametrize("fact", [
    "The answer column lists the measurements.", "Rounded values in the table are estimates.",
    "Units are metres.", "The courier returns to the kitchen.",
    "For this task, the answer column lists measurements.",
    "The sensor can output only integers.", "The answer with units appears in the ledger.",
    "Only the red house has 3 units.", "Just the blue bin is round.",
])
def test_factual_form_vocabulary_survives(fact):
    assert notes.screen({"facts": [fact]}, bench="zebralogic", outcome_judged=True) == ({"facts": [fact]}, [])


def test_table_drops_only_instructive_element_and_retains_verbatim_quotes():
    instruction = "Please, output only JSON."
    fields = {"table": [["The answer column", "3"], [instruction, "4"]]}
    kept, drops = notes.screen(fields, bench="zebralogic", outcome_judged=True)
    assert kept == {"table": [["The answer column", "3"]]} and len(drops) == 1
    assert notes.screen(fields, bench="zebralogic", public_text=instruction, outcome_judged=True) == (fields, [])


def _worker(proc, hook_values):
    hooks = {"applies": lambda view: True}
    hooks.update({hook: (lambda *args, value=value: value) for hook, value in hook_values.items()})
    return FakeSandbox({proc.id: hooks})


@pytest.mark.parametrize("bad,kind", [
    ({"warnings": ["w" * 201]}, "note_cap"),
    ({"warnings": "not a list"}, "note_type"),
    ({"unknown": []}, "note_unknown_field"),
    ({"bindings": [{"name": "count", "quote": "There are 999 baskets.", "value": "999"}]},
     "note_not_verbatim"),
    ({"bindings": [{"name": "not a name", "quote": "17 baskets", "value": "17"}]}, "note_name"),
])
def test_real_note_faults_suppress_live_replay_donors_and_placebo(bad, kind):
    # Review reproduction: a valid fact accompanied by a 201-character warning.
    fields = {"facts": ["The count is 3."], **bad}
    proc = procedure()
    package = replay.solo(proc)
    value = replay.inputs_of(qa_trajectories()[0])
    public = value["request_view"]
    call = Script(["<answer>3</answer>"])
    prediction = solver.solve("searchqa", public, "Read facts", package, call,
                              worker=_worker(proc, {"before_call": fields}))
    assert "The count is 3." not in call.requests[0][1]
    assert [row["kind"] for row in prediction["shell"]["faults"]] == [kind]
    replayed = replay.replay(_worker(proc, {"before_call": fields}).start(package, kind="cell"), proc, value)
    assert replayed.notes == [] and [row["kind"] for row in replayed.faults] == [kind]
    faults = []
    output = donors.procedure_outputs(_worker(proc, {"before_call": fields}).start(package, kind="cell"), proc,
        {"id": "donor", "item": "item", "view": public, "report": None, "steps": None},
        bench="searchqa", faults=faults)
    assert output == {"before_call": {}}
    assert [row["kind"] for row in faults] == [kind] and not any(row.get("informational") for row in faults)

    @contextmanager
    def workers(package, item):
        yield _worker(proc, {"before_call": fields}).start(package, kind="cell")

    lengths = placebo.real_lengths([("new", proc, "candidate")], {"item": public}, workers,
                                    bench="searchqa", packages={"candidate": package, "parent": package})
    assert lengths == {proc.id: {"item": {"before_call": 0}}}
    # A serialized donor output remains empty throughout placebo construction and live sham dispatch.
    sham, band = placebo.sham_fields([output["before_call"]], 0, bench="searchqa", header="", cap=1500,
                                     outcome_judged=True)
    assert sham == {} and band["chars"] == 0


@pytest.mark.parametrize("fields", [
    {"facts": ["The count is 3."], "warnings": ["w" * 201]},
    {"facts": ["The count is 3."], "warnings": "not a list"},
    {"facts": ["The count is 3."], "unknown": []},
])
def test_placebo_direct_render_and_shaping_use_the_same_fault_rule(fields):
    assert placebo.rendered(fields, bench="searchqa", header="", outcome_judged=True) == 0
    sham, band = placebo.sham_fields([fields], 100, bench="searchqa", header="", cap=1500,
                                     outcome_judged=True)
    assert sham == {} and band["chars"] == 0


def test_form_sentence_drop_alone_keeps_note_in_every_path():
    fields = {"facts": ["The count is 3. For this task, answer with JSON."]}
    proc, value = procedure(), replay.inputs_of(qa_trajectories()[0])
    package = replay.solo(proc)
    call = Script(["<answer>3</answer>"])
    result = solver.solve("searchqa", value["request_view"], "Read facts", package, call,
                          worker=_worker(proc, {"before_call": fields}))
    assert "The count is 3." in call.requests[0][1] and not result["shell"]["faults"]
    found = replay.replay(_worker(proc, {"before_call": fields}).start(package, kind="cell"), proc, value)
    assert found.notes and all(row["informational"] for row in found.faults)
    faults = []
    donor = donors.procedure_outputs(_worker(proc, {"before_call": fields}).start(package, kind="cell"), proc,
        {"id": "donor", "item": "item", "view": value["request_view"], "report": None, "steps": None},
        bench="searchqa", faults=faults)
    clean = donor["before_call"]
    assert clean == {"facts": ["The count is 3."]} and all(row["informational"] for row in faults)
    length = placebo.rendered(fields, bench="searchqa", header="", outcome_judged=True)
    assert length == placebo.rendered(clean, bench="searchqa", header="", outcome_judged=True) > 0
    sham, band = placebo.sham_fields([fields], length, bench="searchqa", header="", cap=1500,
                                     outcome_judged=True)
    assert sham == clean and band["within"]


@pytest.mark.parametrize("warning_chars", [201, 120])
def test_later_binding_fault_clears_only_pending_notes_across_live_replay_and_donor(warning_chars):
    proc = replace(procedure(hooks=("applies", "before_call", "bindings")), max_note_chars=100)
    value = replay.inputs_of(qa_trajectories()[0])
    hooks = {"before_call": {"facts": ["The count is 3."]}, "bindings": {"warnings": ["w" * warning_chars]}}
    package, call = replay.solo(proc), Script(["<answer>3</answer>"])
    solver.solve("searchqa", value["request_view"], "Read facts", package, call, worker=_worker(proc, hooks))
    assert "The count is 3." not in call.requests[0][1]
    found = replay.replay(_worker(proc, hooks).start(package, kind="cell"), proc, value)
    assert found.notes == []
    donor = donors.procedure_outputs(_worker(proc, hooks).start(package, kind="cell"), proc,
        {"id": "donor", "item": "item", "view": value["request_view"], "report": None, "steps": None},
        bench="searchqa", faults=[])
    assert donor == {"before_call": {}, "bindings": {}}


def test_alf_note_fault_also_suppresses_discouragement():
    proc = procedure(origin="alfworld", hooks=("applies", "alf_before_step"))
    value = replay.inputs_of(alf_trajectory())
    command = value["steps"][0]["view"]["admissible_commands"][0]
    hooks = {"alf_before_step": {"fields": {"facts": ["The count is 3."], "warnings": ["w" * 201]},
                                  "discourage": [command]}}
    package = replay.solo(proc)
    shell = solver._Shell("alfworld", package, None, _worker(proc, hooks), withhold=(), restore=(),
                          placebo=None, text=None, native=None, nominal=None)
    shell.start("episode")
    shell.route_on(value["view"])
    assert shell.before_step(value["steps"][0]["view"], {}, 0) == ("", [])
    shell.close()
    found = replay.replay(_worker(proc, hooks).start(package, kind="episode"), proc, value)
    assert found.notes == [] and found.steps[0]["discouraged"] == []
    donor = donors.procedure_outputs(_worker(proc, hooks).start(package, kind="episode"), proc,
        {"id": "donor", "item": "item", "view": None, "report": None, "steps": value["steps"]},
        bench="alfworld", faults=[])
    assert all(entry == {"fields": {}, "discourage": 0} for entry in donor["alf_before_step"])


@pytest.mark.parametrize("warning_chars", [201, 120])
def test_sheet_note_fault_suppresses_repair_request(warning_chars):
    proc = replace(procedure(origin="spreadsheetbench", hooks=("applies", "sheet_feedback"),
                             requests_second_call=True), max_note_chars=100)
    value = replay.inputs_of(sheet_trajectories()[0])
    hooks = {"sheet_feedback": {"fields": {"facts": ["The count is 3."], "warnings": ["w" * warning_chars]},
                                 "request_repair": True}}
    package = replay.solo(proc)
    shell = solver._Shell("spreadsheetbench", package, None, _worker(proc, hooks), withhold=(), restore=(),
                          placebo=None, text=None, native=None, nominal=None)
    shell.start("cell")
    shell.route_on(value["view"])
    assert shell.feedback(value["request_view"], value["report"]) == ("", False)
    shell.close()
    found = replay.replay(_worker(proc, hooks).start(package, kind="cell"), proc, value)
    assert found.notes == [] and found.repair is False
