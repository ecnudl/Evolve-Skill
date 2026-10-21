"""coevo5 v3 (registration delta §2, §4-§6), offline: the contract-first prompt layout, the role inputs' byte bound, the
analyst's rule-by-rule validation and limits, the reviser's check library with parameters, the spreadsheet views (the
solver's workbook preview; the compared answer-range cells bound to the scored artifacts) and the expected cell values
the leakage adjudicator sees."""
import base64
import hashlib
import io
import json

import openpyxl
import pytest

from skillopt.coevo5 import analyst, examiner, leakage, sheetview, smoke
from skillopt.coevo5.protocol import SHEET_PREVIEW_CHARS
from skillopt.coevo5.roles import fit, message_bytes
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import write_json
from skillopt.validator_pilot.api import digest
from tests.coevo5_fakes import reply, roles

LAYOUT = {"prompt_layout": "contract-first-v1"}
BASE = "Solve the supplied task using only the supplied public information."
GUIDANCE = "\n\nFrozen skill guidance (use only where applicable):\n"


# ------------------------------------------------------------------------------------------- §2: the layout
def test_the_contract_first_layout_states_the_answer_form_before_the_skill():
    seen = []

    def call(system, user):
        seen.append(system)
        return reply("<answer>x</answer>")
    public, skill = {"question": "Q?", "context": "C"}, "## SearchQA\nApplies when: x"
    for runtime in (LAYOUT, None):
        backends.solve("searchqa", public, "", call, runtime=runtime)
    contract = "\nReturn the concise final answer inside <answer>...</answer>."
    assert seen == [BASE + contract] * 2  # the empty Skill's prompt is byte-identical in both layouts
    backends.solve("searchqa", public, skill, call, runtime=LAYOUT)
    backends.solve("searchqa", public, skill, call)  # callers without the option keep the historical order
    assert seen[2:] == [BASE + contract + GUIDANCE + skill, BASE + GUIDANCE + skill + contract]
    backends.solve("livemath", {"question": "Q?", "choices": "A. 1\n\nB. 2"}, skill, call, runtime=LAYOUT)
    assert seen[-1] == BASE + backends.LIVEMATH_CONTRACT + GUIDANCE + skill
    # an unknown layout, or the layout on ALFWorld (whose contract already comes first), is refused
    assert backends.readiness("alfworld", LAYOUT) == {"status": "unsupported", "reason": "invalid_prompt_layout"}
    assert backends.readiness("searchqa", {"prompt_layout": "other"})["reason"] == "invalid_prompt_layout"
    found = backends.solve("searchqa", public, skill, call, runtime={"prompt_layout": "other"})
    assert (found["status"], found["reason"]) == ("unknown", "invalid_prompt_layout") and len(seen) == 5


def test_v2_states_the_spreadsheet_deliverable_for_every_skill_and_leaves_the_other_prompts_as_v1(tmp_path):
    """After the format check (the owner, 2026-10-19): SpreadsheetBench's contract names the program, its output and
    the fence's own line; nothing else changes."""
    seen = []

    def call(system, user):
        seen.append(system)
        return reply("```python\nprint(1)\n```")
    book = tmp_path / "input.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active["A1"] = 1
    workbook.save(book)
    public = {"instruction": "Sum column A.", "input_files": [str(book)], "answer_position": "Sheet!B1"}
    v2 = {"prompt_layout": "contract-first-v2"}
    skill = "## SpreadsheetBench\nApplies when: x"
    old = "\nReturn one complete Python program in a ```python code block."
    for skill_text in ("", skill):
        for runtime in (v2, LAYOUT, None):
            backends.solve("spreadsheetbench", public, skill_text, call, runtime=runtime)
    guided = GUIDANCE + skill
    assert seen == [BASE + backends.SHEET_CONTRACT_V2, BASE + old, BASE + old,
                    BASE + backends.SHEET_CONTRACT_V2 + guided, BASE + old + guided, BASE + guided + old]
    assert "formula alone is not an answer" in backends.SHEET_CONTRACT_V2 and "own line" in backends.SHEET_CONTRACT_V2
    for bench, view in (("searchqa", {"question": "Q?", "context": "C"}), ("officeqa", {"question": "Q?", "context": "C"}),
                        ("livemath", {"question": "Q?", "choices": "A. 1\n\nB. 2"})):
        for skill_text in ("", skill):
            backends.solve(bench, view, skill_text, call, runtime=v2)
            backends.solve(bench, view, skill_text, call, runtime=LAYOUT)
            assert seen[-1] == seen[-2]  # v2 is v1 outside SpreadsheetBench
    assert backends.readiness("alfworld", v2)["reason"] == "invalid_prompt_layout"
    from skillopt.coevo5.protocol import RUNTIME
    assert {RUNTIME[b]["prompt_layout"] for b in ("searchqa", "officeqa", "livemath", "spreadsheetbench")} == \
        {"contract-first-v2"} and "prompt_layout" not in RUNTIME["alfworld"]


def test_v2_role_cards_quote_the_contract_the_solver_receives():
    """The analyst and the self-test's revision read the cards a run's Setting holds: under v2 the SpreadsheetBench
    card quotes v2's contract; the registered cards (archive, texts record, manifest) keep v1's."""
    from skillopt.coevo5 import texts
    from skillopt.coevo5.protocol import RUNTIME

    cards = texts.solver_cards(texts.CARDS, RUNTIME)
    assert '"%s"' % backends.SHEET_CONTRACT_V2.strip() in cards["spreadsheetbench"]
    assert texts.SHEET_CONTRACT_QUOTE not in cards["spreadsheetbench"]
    assert {b: c for b, c in cards.items() if b != "spreadsheetbench"} == \
        {b: c for b, c in texts.CARDS.items() if b != "spreadsheetbench"}
    assert texts.CARDS["spreadsheetbench"].count(texts.SHEET_CONTRACT_QUOTE) == 1  # the registered card is unchanged
    for runtime in ({}, {"spreadsheetbench": {"prompt_layout": "contract-first-v1"}}):
        assert texts.solver_cards(texts.CARDS, runtime) == texts.CARDS


# ---------------------------------------------------------------------------------------- §6: input bounds
def test_a_role_input_leaves_out_its_last_shown_entries_until_it_fits():
    user = {"section": "S", "examples": [{"task_id": "t%d" % n, "text": "y" * 100} for n in range(10)]}
    found = fit(json.loads(json.dumps(user)), "examples", 700)
    kept = len(found["examples"])
    assert message_bytes(found) <= 700 and 0 < kept < 10 and found["examples_omitted"] == 10 - kept
    assert found["examples"] == user["examples"][:kept]  # the shown order: the last ones go first
    assert fit(json.loads(json.dumps(user)), "examples", 10 ** 6)["examples_omitted"] == 0


# ----------------------------------------------------------------------------- §4: the analyst's rows
ROW = {"text": "Copy the exact answer.", "placement": "local", "codes": ["R1"], "evidence": ["t1", "t2"],
       "covered": "", "adds": "an exact copy", "rationale": "fix", "questions": []}


@pytest.mark.parametrize("broken", [{"rationale": "r" * 501}, {"covered": "c" * 201}, {"adds": "a" * 301},
                                    {"questions": ["q" * 301]}, {"text": "t" * 601}, {"placement": "elsewhere"},
                                    {"codes": ["R9"]}, {"text": 7}])
def test_an_invalid_rule_row_is_dropped_on_its_own(broken):
    check = analyst._check("searchqa", {"R1"}, {"t1": {"R1"}, "t2": {"R1"}})
    found = check({"rules": [ROW, {**ROW, **broken}], "transfer": {"none": "a fix of this kind only"}})
    first, second = found["rules"]
    assert (first["row_status"], first["evidence_status"]) == ("ok", "ok")
    assert second["row_status"] != "ok" and second["evidence_status"] == "not_checked" and second["codes"] == []
    with pytest.raises(ValueError, match="no valid rule"):  # every row invalid: the reply is invalid
        check({"rules": [{**ROW, **broken}], "transfer": {"none": "a fix of this kind only"}})


def test_the_smoke_paths_take_the_first_proposal_whose_row_is_valid():
    rules = [{"text": None, "row_status": "fields"}, {"text": "t" * 700, "row_status": "text"},
             {"id": "r3", "text": "Copy it.", "row_status": "ok"}, {"id": "r4", "text": "Old record."}]
    assert [r["id"] for r in smoke.valid_proposals(rules)] == ["r3", "r4"]


def test_a_role_input_whose_fixed_fields_exceed_the_bound_is_never_sent():
    user = {"section": "S" * 800, "examples": [{"text": "y" * 100}]}
    with pytest.raises(ValueError, match="no example left"):
        fit(user, "examples", 700)


def test_the_analyst_is_told_every_limit_and_to_condition_only_on_what_the_solver_sees():
    for limit in ("text 600", "covered 200", "adds 300", "rationale 500", "each question 300",
                  "the transfer reason 300"):
        assert limit in analyst.ANALYST_SYSTEM
    assert "the solver sees while solving" in analyst.ANALYST_SYSTEM
    assert "something the solver cannot see while solving" in leakage.ADJUDICATE_SYSTEM


# ------------------------------------------------------------------------------------- §5: the reviser
def test_the_reviser_sees_every_check_with_its_parameters():
    found = examiner.library()
    assert found["answer_pure_number"] == {"allow_percent": "true or false"}
    assert found["answer_max_words"] == {"n": "integer 1-50"} and found["answer_tag_present"] == {}
    assert "exactly the parameters listed for it" in examiner.REVISE_SYSTEM


# ------------------------------------------------------------------------------- §6: spreadsheet views
def _workbook(path, cells):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    for coordinate, value in cells.items():
        sheet[coordinate] = value
    if path is None:
        buffer = io.BytesIO()
        book.save(buffer)
        return buffer.getvalue()
    book.save(path)
    return path.read_bytes()


def test_the_task_view_shows_the_solvers_workbook_preview(tmp_path):
    path = tmp_path / "input.xlsx"
    _workbook(path, {"A1": "Region", "B1": "Sales", "A2": "North", "B2": 12})
    view = examiner.task_view("spreadsheetbench", {"instruction": "Sum B.", "answer_position": "C1",
                                                   "input_files": [str(path)]})
    assert isinstance(view["workbook_preview"], str) and len(view["workbook_preview"]) <= SHEET_PREVIEW_CHARS
    assert "North" in view["workbook_preview"] and view["answer_position"] == "C1"
    assert examiner.task_view("spreadsheetbench", {"instruction": "x", "answer_position": "C1",
                                                   "input_files": [str(tmp_path / "missing.xlsx")]}
                              )["workbook_preview"] is None


def _receipt(directory, name, source, output):
    record = seal({"status": "available", "input_sha256": hashlib.sha256(source).hexdigest(),
                   "output_sha256": hashlib.sha256(output).hexdigest(),
                   "output_base64": base64.b64encode(output).decode()})
    write_json(directory / "recalculations" / (name + ".json"), record)
    return record["record_hash"]


def test_the_compared_cells_are_read_from_the_scored_artifacts(tmp_path):
    store = tmp_path / "attempt"
    reference = _workbook(tmp_path / "reference.xlsx", {"A1": "Total", "B1": 1, "B2": 2})
    written = _workbook(None, {"A1": "Total", "B1": "=1+0", "B2": 5})
    recalculated = _workbook(None, {"A1": "Total", "B1": 1, "B2": 5})
    record = {"cell": {"unit": "I-ds/s4/train", "id": "c1"}, "attempts": [{"score": {"sha256": "s" * 64}}]}
    directory = store / "host_only" / "scorer_artifacts" / digest(
        {"benchmark": "spreadsheetbench", "unit": "I-ds/s4/train", "cell": "c1", "scoring": 0})
    receipts = {"reference": _receipt(directory, "r", reference, reference),
                "prediction": _receipt(directory, "p", written, recalculated)}
    write_json(store / "artifacts" / ("s" * 64 + ".json"), {"metrics": {"cases": [
        {"reason": "value@Sheet1!B2: mismatch", "receipts": receipts}]}})
    prediction = {"status": "available", "output": {"code": "x", "cases": [
        {"status": "available", "output_base64": base64.b64encode(written).decode()}]}}
    private = {"test_files": [str(tmp_path / "reference.xlsx")], "answer_position": "Sheet1!B1:B2"}
    found = sheetview.cells(store, record, prediction, private)
    assert found == {"case": 0, "cells_in_range": 2, "first_mismatch": "Sheet1!B2",
                     "expected_source": "recalculated_reference", "recalculated": "available", "written": "available",
                     "shown": [{"cell": "Sheet1!B1", "expected": 1, "recalculated": 1, "written": "=1+0"},
                               {"cell": "Sheet1!B2", "expected": 2, "recalculated": 5, "written": 5}]}
    # a receipt bound to another input is never used: the reference's own cached values, said so
    (directory / "recalculations" / "r.json").unlink()
    _receipt(directory, "r", b"another workbook", reference)
    write_json(store / "artifacts" / ("t" * 64 + ".json"), {"metrics": {"cases": [{"reason": "", "receipts": {}}]}})
    record["attempts"].append({"score": {"sha256": "t" * 64}})  # a later scoring: its own directory, no receipts
    later = sheetview.cells(store, record, prediction, private)
    assert (later["expected_source"], later["recalculated"], later["first_mismatch"]) == (
        "reference_cache", "unavailable", None)
    assert [c["recalculated"] for c in later["shown"]] == [None, None]
    assert sheetview.cells(store, record, prediction, {**private, "answer_position": "Nowhere!A1"}) is None


def test_the_adjudicator_sees_the_expected_cell_values_of_the_shown_failures(tmp_path):
    answers = [{"sheet_cells": {"shown": [{"expected": 3.5}, {"expected": None}, {"expected": "  "},
                                          {"expected": True}, {"expected": "Total"}]}},
               {"sheet_cells": None}, {"sheet_cells": {"shown": [{"expected": 3.5}, {"expected": 7}]}}]
    assert leakage.answer_values(answers) == ["3.5", "Total", "7"]
    assert leakage.answer_values(answers, limit=2) == ["3.5", "Total"]
    adjudicator, script = roles(tmp_path, [{"verdict": "yes", "reason": "copies an expected cell value"}])
    assert leakage.adjudicate(adjudicator, "Write 3.5 in B2.", label="leak", values=["3.5", "Total"]) is False
    assert script.seen[0][1] == {"rule": "Write 3.5 in B2.", "answer_values": ["3.5", "Total"]}
