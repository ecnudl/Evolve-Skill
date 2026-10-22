"""The engineer's step: proposal, the fixed checks C1-C9, one fix, the candidate (implementation plan §1 engineer.py,
B4, §8; registration §4.2, §5.4). The engineer and the leakage adjudicator are FakeGLM (scripted GLM-5.3 replies
behind the real client and ``Roles``); every procedure runs in the real worker through FakeDocker; every procedure
and trajectory is a synthetic engineering fixture (fx-note, fx-crash, fx-lexicon, fx-meta, fx-literal, ...)."""
from __future__ import annotations

import dataclasses
import json

import pytest

from skillopt.coevo5.leakage import Corpus
from skillopt.execskill import engineer
from skillopt.execskill.package import FIXTURE, Package, edits, empty
from skillopt.execskill.protocol import ENGINEER_CALLS, verified
from tests.execskill_fakes import engineer_reply, glm_roles
from tests.test_execskill_replay import (CRASH, LEXICON, LITERAL, META, NOTE, QA, fake, fixture,  # noqa: F401
                                         qa_items, qa_trajectories, source, test_case, workers)

CARD = "Use the supplied context to settle each question."
NOTE_TEST = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "17"}, mutation="strip_digits")
WORDS = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": ["The question has %d words." % len(view["question"].split())]}
"""
QUOTE = """
import re

def applies(view):
    return "context" in view

def before_call(view, state):
    found = re.findall(r"The ([A-Z][a-z]+ [A-Z][a-z]+) ", " ".join(view["context"]))
    return {"candidates": found} if found else None
"""
COMPOSER = """
def applies(view):
    return "sonata" in view["question"]

def before_call(view, state):
    return {"candidates": ["Ludwig Beethoven"]}
"""
COMPOSER_FIXED = """
def applies(view):
    return "sonata" in view["question"]

def before_call(view, state):
    return {"facts": ["The question asks about the composer of a sonata."]}
"""


def new(description, tests, **fields):
    return {"kind": "new", "description": description, "hooks": ["applies", "before_call"], "max_note_chars": 1000,
            "replay_tests": tests, **fields}


def context(tmp_path, workers, replies, *, parent=None):
    roles, glm = glm_roles(tmp_path / "glm", replies)
    ctx = engineer.Context(
        bench="searchqa", k=1, step="s1", evidence=FIXTURE, parent=parent or empty(step="s0", evidence=FIXTURE),
        trajectories=qa_trajectories(), corpora={"searchqa": Corpus("searchqa", qa_items())}, workers=workers,
        roles=roles, label="D/s1-searchqa/engineer", card=CARD,
        references={item: answers for item, (_, answers, token) in QA.items() if token == "fail"})
    return ctx, glm


def checks(attempt):
    return [c["check"] for c in attempt["checks"]]


def test_reply_parsing_takes_one_manifest_and_one_code_block_per_coded_change():
    reply = engineer_reply({"changes": [new("Lists numbers.", [NOTE_TEST]), {"kind": "deletion", "id": "fx-old"}]},
                           [NOTE])
    changes, sources = engineer.parse(reply)
    assert [c["kind"] for c in changes] == ["new", "deletion"] and sources == [NOTE]
    for bad, reason in (("no blocks here", "manifest_blocks:0"), ("```json\n{\"changes\": [\n```", "manifest_json"),
                        (engineer_reply({"changes": [{"kind": "new"}] * 4}, [NOTE] * 4), "manifest_shape"),
                        (engineer_reply({"changes": [new("x", [])]}, []), "code_blocks"), (None, "no_reply")):
        with pytest.raises(engineer.Unparseable, match=reason):
            engineer.parse(bad)


def test_the_pipeline_runs_c1_to_c9_and_gives_one_fix_per_failed_change(tmp_path, workers):
    fixed_test = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "words."})
    lexicon_test = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "names a place"})
    proposal = engineer_reply({"changes": [new("Lists the numbers of the question.", [NOTE_TEST]),
                                           new("Divides by zero.", [fixed_test]),
                                           new("Tells the solver how to reply.", [lexicon_test])]},
                              [source(NOTE), source(CRASH), source(LEXICON)])
    crash_fix = engineer_reply({"changes": [new("Counts the question's words.", [fixed_test])]}, [source(WORDS)])
    lexicon_fix = engineer_reply({"changes": [new("Tells the solver how to reply.", [lexicon_test])]},
                                 [source(LEXICON)])
    ctx, glm = context(tmp_path, workers, [proposal, crash_fix, lexicon_fix])
    package, sealed = engineer.run(ctx)
    sealed = verified(sealed, "engineer")
    note, crash, lexicon = sealed["changes"]
    assert checks(note["attempts"][0]) == ["C1", "C2", "C4", "C3", "C5", "C6", "C4", "C7", "C8", "C9"]
    assert note["survived"] and len(note["attempts"]) == 1
    assert crash["attempts"][0]["failed"] == "C6" and crash["attempts"][1]["passed"] and crash["survived"]
    assert [a["failed"] for a in lexicon["attempts"]] == ["C9", "C9"] and not lexicon["survived"]
    assert lexicon["attempts"][0]["checks"][-1]["detail"][0]["kind"] == "note_lexicon"
    assert package.order == ("fx-searchqa-1-1", "fx-searchqa-1-2") and sealed["kept"] == [1, 2]
    assert sealed["candidate_sha256"] == package.sha256 and package.parent_sha256 == ctx.parent.sha256
    calls = [c["request_sha256"] for c in ctx.roles.calls]
    assert [p.lineage["engineer_call"] for p in package.procedures] == calls[:2]
    assert sealed["calls"] == 3 and sealed["prompt_sha256"] == engineer.ENGINEER_PROMPT_SHA256
    assert [e.kind for e in edits(ctx.parent, package)] == ["new", "new"]
    shown = glm.seen[0][1]
    assert shown["request"] == "propose" and shown["card"] == CARD and shown["trajectories_omitted"] == 0
    assert {t["cell"]: "reference" in t for t in shown["trajectories"]} == {"c-q1": True, "c-q3": True,
                                                                           "c-q2": False}
    assert all("system" not in call for t in shown["trajectories"] for call in t["calls"])
    assert glm.seen[1][1]["request"] == "fix" and glm.seen[1][1]["failed"]["check"] == "C6"


def test_static_bans_c1_and_an_unparseable_reply(tmp_path, workers):
    meta_test = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "option"})
    literal_test = test_case("c-q1", "alf_before_step", {"kind": "note_contains", "value": "first", "step": 0})
    meta = new("Prefers a meta option.", [meta_test])
    literal = {**new("Looks in one drawer.", [literal_test]), "hooks": ["applies", "alf_before_step"]}
    missing = {"kind": "deletion", "id": "fx-missing"}
    proposal = engineer_reply({"changes": [meta, literal, missing]}, [source(META), source(LITERAL)])
    replies = ["I would add a procedure.", proposal, engineer_reply({"changes": [meta]}, [source(META)]),
               engineer_reply({"changes": [literal]}, [source(LITERAL)]), engineer_reply({"changes": [missing]}, [])]
    ctx, glm = context(tmp_path, workers, replies)
    package, sealed = engineer.run(ctx)
    assert package is None and sealed["candidate_sha256"] is None and sealed["procedures"] == []
    assert sealed["proposals"][0] == {"call": ctx.roles.calls[0]["request_sha256"], "parsed": False,
                                      "reason": "manifest_blocks:0"}
    assert glm.seen[1][1]["unparseable"] == "manifest_blocks:0"
    first, second, third = sealed["changes"]
    for change, rule in ((first, "meta_option"), (second, "receptacle_literal")):
        assert [checks(a) for a in change["attempts"]] == [["C1", "C2", "C4"]] * 2
        assert change["attempts"][0]["checks"][-1]["detail"]["static_bans"][0]["rule"] == rule
    assert [a["checks"] for a in third["attempts"]] == [[{"check": "C1", "passed": False,
                                                         "detail": "target_not_in_parent"}]] * 2
    assert sealed["calls"] == 5 <= ENGINEER_CALLS


def test_r3_a_bindings_hook_whose_declared_scope_reaches_a_bench_without_calc_fails_c1(tmp_path, workers):
    """Registration §2.4, §3: ``bindings`` is QA-only (registrar addendum 2026-10-22 15:5x R3). A new or revised
    procedure declaring it must list spreadsheetbench and alfworld in excluded_benches; C1 says so, for the fix call."""
    bind_test = test_case("c-q1", "bindings", {"kind": "binding_equals", "name": "n", "value": "17"},
                          mutation="strip_digits")
    entry = {**new("Names the numbers of the question.", [bind_test]), "hooks": ["applies", "bindings"]}
    ctx, glm = context(tmp_path, workers, [])
    assert engineer.NO_CALC_BENCHES == ("spreadsheetbench", "alfworld")
    for excluded in ([], ["spreadsheetbench"], ["alfworld", "livemath"]):
        change = engineer.Change(1, "new", {**entry, "excluded_benches": excluded}, source(NOTE), "call")
        report = engineer.check(change, ctx)
        assert report["failed"] == "C1" and report["checks"] == [{"check": "C1", "passed": False,
                                                                  "detail": engineer.BINDINGS_SCOPE}]
    assert "spreadsheetbench and alfworld in excluded_benches" in engineer.BINDINGS_SCOPE
    scoped = engineer.Change(1, "new", {**entry, "excluded_benches": ["alfworld", "spreadsheetbench"]}, source(NOTE),
                             "call")
    assert engineer._structure(scoped, ctx.parent, ()) is None  # QA-only: well formed
    notes_only = engineer.Change(1, "new", new("Lists numbers.", [NOTE_TEST]), source(NOTE), "call")
    assert engineer._structure(notes_only, ctx.parent, ()) is None  # other hooks keep every bench
    assert glm.seen == []


def test_r7a_engineer_calls_are_counted_per_step_across_both_engineer_units(tmp_path, workers):
    """Registrar addendum 2026-10-22, R7 decision 16:1x (R7a): ``ENGINEER_CALLS`` = 6 per step, one count shared by
    the step's engineer units; ``engineer-2`` (``Context.spent`` = the first unit's calls) gets the calls left."""
    words = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "words."})
    proposal = engineer_reply({"changes": [new("Divides by zero.", [words])]}, [source(CRASH)])
    fixed = engineer_reply({"changes": [new("Counts the question's words.", [words])]}, [source(WORDS)])
    ctx, glm = context(tmp_path / "one-left", workers, [proposal, fixed])
    ctx.spent = ENGINEER_CALLS - 1  # one call left: the proposal; its change fails C6 and gets no fix call
    package, sealed = engineer.run(ctx)
    change = sealed["changes"][0]
    assert package is None and len(glm.seen) == 1 and (sealed["calls"], sealed["earlier_calls"]) == (1, 5)
    assert [a["failed"] for a in change["attempts"]] == ["C6"] and not change["survived"]
    ctx, glm = context(tmp_path / "two-left", workers, [proposal, fixed])
    ctx.spent = ENGINEER_CALLS - 2  # two left: the proposal and its fix
    package, sealed = engineer.run(ctx)
    assert package is not None and len(glm.seen) == 2 and sealed["calls"] == 2 and sealed["changes"][0]["survived"]
    ctx, glm = context(tmp_path / "none-left", workers, [proposal])
    ctx.spent = ENGINEER_CALLS  # the first unit used them all: no call at all
    package, sealed = engineer.run(ctx)
    assert package is None and glm.seen == [] and sealed["calls"] == 0
    assert [p["parsed"] for p in sealed["proposals"]] == [False, False]
    with pytest.raises(ValueError, match="engineer calls so far"):
        dataclasses.replace(ctx, spent=ENGINEER_CALLS + 1)


def test_leakage_counts_only_content_absent_from_the_items_public_view(tmp_path, workers):
    corpus = Corpus("searchqa", qa_items())
    own = QA["q1"][0]
    quoting = "Candidates listed by a helper program (may be incomplete):\n- Gravenstein Orchard"
    public = engineer.public_text(own)
    assert engineer.absent_findings(quoting, corpus, public) == {}
    assert engineer.absent_findings(quoting, corpus, "") == {"answer_text": True}
    quote_test = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "Gravenstein Orchard"})
    composer_test = test_case("c-q3", "before_call", {"kind": "note_contains", "value": "composer"})
    leaky_test = test_case("c-q3", "before_call", {"kind": "note_contains", "value": "Beethoven"})
    proposal = engineer_reply({"changes": [new("Lists the named places of the context.", [quote_test]),
                                           new("Suggests a composer.", [leaky_test])]},
                              [source(QUOTE), source(COMPOSER)])
    veto = {"verdict": "yes", "reason": "It names one task's reference answer."}
    fix = engineer_reply({"changes": [new("Notes that the question asks about a composer.", [composer_test])]},
                         [source(COMPOSER_FIXED)])
    ctx, glm = context(tmp_path, workers, [proposal, veto, fix])
    package, sealed = engineer.run(ctx)
    quote, composer = sealed["changes"]
    assert quote["survived"] and quote["attempts"][0]["passed"]
    leak = composer["attempts"][0]["checks"][-1]
    assert leak["check"] == "C4" and not leak["passed"] and leak["detail"]["adjudicated"] is True
    assert {h["where"] for h in leak["detail"]["hits"]} == {"literal", "note:c-q3"}
    assert composer["attempts"][1]["passed"] and composer["survived"] and len(package.procedures) == 2
    assert ctx.roles.count("leak/") == 1 and "Ludwig Beethoven" in glm.seen[1][1]["rule"]
    assert [c["role"] for c in ctx.roles.calls] == ["engineer", "leak_adjudicate", "engineer"]


def test_revision_deletion_and_narrowing_build_the_candidate(tmp_path, workers):
    old_note = fixture("fx-old-note", source(NOTE), ("applies", "before_call"), tests=[NOTE_TEST])
    old_quote = fixture("fx-old-quote", source(QUOTE), ("applies", "before_call"))
    old_words = fixture("fx-old-words", source(WORDS), ("applies", "before_call"))
    parent = Package((old_note, old_quote, old_words), "s0", FIXTURE)
    revised = {**new("Lists the numbers of the question, revised.", [NOTE_TEST]), "kind": "revision",
               "revises": "fx-old-note", "header": "Numbers"}
    proposal = engineer_reply({"changes": [revised, {"kind": "deletion", "id": "fx-old-words"},
                                           {"kind": "narrowing", "id": "fx-old-quote", "benches": ["alfworld"]}]},
                              [source(NOTE)])
    ctx, _ = context(tmp_path, workers, [proposal], parent=parent)
    package, sealed = engineer.run(ctx)
    assert [c["survived"] for c in sealed["changes"]] == [True, True, True]
    assert [checks(c["attempts"][0]) for c in sealed["changes"][1:]] == [["C1", "C3"]] * 2
    assert package.order == ("fx-searchqa-1-1", "fx-old-quote") and package.narrowed == {"fx-old-quote": ("alfworld",)}
    revision = package.get("fx-searchqa-1-1")
    assert revision.lineage == {"parent": old_note.sha256, "revises": "fx-old-note",
                                "engineer_call": ctx.roles.calls[0]["request_sha256"]}
    assert [e.kind for e in edits(parent, package)] == ["revision", "deletion", "narrowing"]
    assert [p["id"] for p in engineer.payload(ctx)["package"]] == list(parent.order)


def test_the_engineer_calls_stop_at_the_step_ceiling(tmp_path, workers):
    ctx, _ = context(tmp_path, workers, ["no manifest"] * ENGINEER_CALLS)
    for n in range(ENGINEER_CALLS):
        assert engineer._ask(ctx, {"request": "propose", "n": n}, "propose")[0] == "no manifest"
    assert engineer._ask(ctx, {"request": "propose"}, "propose") == (None, None)
    assert ctx.roles.count("engineer/D/s1-searchqa/engineer/") == ENGINEER_CALLS


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_5_the_engineer_context_refuses_inputs_of_the_wrong_provenance(tmp_path):
    import dataclasses

    from skillopt.execskill.protocol import record
    from tests.test_execskill_replay import alf_trajectory

    ctx, _ = context(tmp_path, None, [])

    def refused(match, **changes):
        with pytest.raises(ValueError, match=match):
            dataclasses.replace(ctx, **changes)

    accepted_unit = dict(ctx.trajectories[0])
    accepted_unit.pop("record_sha256")
    accepted_unit = record("trajectory", FIXTURE, {**{k: v for k, v in accepted_unit.items()
                                                       if k not in ("version", "evidence")},
                                                    "unit": "D/s1-searchqa/accept-r1"})
    refused("run-slice", trajectories=[*ctx.trajectories, accepted_unit])  # an acceptance cell, even "parent"
    refused("run-slice", label="G/s1-searchqa/engineer")  # another chain's run slice
    refused("run-slice", k=0)  # a later step's run slice
    refused("References", references={"q2": ["Okavango River"]})  # a passing item
    refused("References", references={"q1": {"expert_plan": ["go to fridge 1"], "gamefile": "json_2.1.1/x"}})
    refused("ALFWorld", bench="alfworld", trajectories=[alf_trajectory()], references={"alf-1": "x"})
    refused("counts", detectors={"failing": {"c-q1": ["no_answer_tag"]}})
    refused("previous", previous={"acceptance_item_scores": {"acc-01": 1}})
    refused("previous", previous={"decision": "accepted", "faults": {"timeout": 1}, "format": {"items": "3"}})
    fine = dataclasses.replace(ctx, detectors={"cells": 3, "failed": 2, "categories": {"no_answer_tag": {"cells": 1}}},
                               previous={"decision": "not_accepted", "faults": {"timeout": 1}, "format": {"items": 3}})
    assert engineer.payload(fine)["previous"]["decision"] == "not_accepted"


# ---------------------------------------------------------------------- M round (Codex review 2026-10-22, #2)
# SpreadsheetBench references (registrar addendum 2026-10-22 15:5x R1) reach the engineer as answer-cell values; the
# frozen corpus indexes none of them, so C4 checks the disclosed values itself (registration §4.2, §5.4 C4).
SHEET_REFERENCE = {"Sheet1!C2": 4242.5, "Sheet1!C3": 1250, "Sheet1!C4": "Northwind Traders",
                   "Sheet1!C5": "Contoso Pharmaceuticals", "Sheet1!C6": 7, "Sheet1!C7": "TRUE", "Sheet1!C8": "",
                   "Sheet1!C9": "N/A", "Sheet1!D2": "Total"}
FAILED_ROWS = [["Q1", "Q2", "Total", "Target"], [1000, 250, None, 1250]] + [[k, k + 1] for k in range(37)] + [
    ["Northwind Traders"]]  # beyond the five preview rows: public only through the whole workbook
PASSED_ROWS = [["Q1", "Q2", "Total"], [3, 4, 7], ["Contoso Pharmaceuticals"]]
COPIED_LITERAL = """
TARGET = 4242.5

def applies(view):
    return "instruction" in view

def before_call(view, state):
    return {"facts": ["The instruction has %d words." % len(view["instruction"].split())]} if TARGET else None
"""
COPIED_NOTE = """
def applies(view):
    return "instruction" in view

def before_call(view, state):
    return {"facts": ["The expected total is %s." % (8485 / 2)]}
"""
PUBLIC_QUOTES = """
def applies(view):
    return "instruction" in view

def before_call(view, state):
    names = sorted(cell["value"] for sheet in public_workbook()["sheets"] for cell in sheet["cells"].values()
                   if isinstance(cell["value"], str) and " " in cell["value"])
    return {"facts": ["Target 1250 over 7 rows, flags TRUE or N/A, in the Total column.", "Names: " + "; ".join(names)]}
"""
COLUMNS = """
def applies(view):
    return "instruction" in view

def before_call(view, state):
    return {"facts": ["The instruction names %d columns." % len(view["instruction"].split(" and "))]}
"""


def _workbook(directory, rows):
    from openpyxl import Workbook

    book = Workbook()
    book.active.title = "Sheet1"
    for row in rows:
        book.active.append(row)
    directory.mkdir(parents=True)
    book.save(directory / "input.xlsx")
    return directory


def sheet_context(tmp_path, workers, replies):
    from tests.test_execskill_replay import SHEET_VIEW, sheet_trajectories

    roles, glm = glm_roles(tmp_path / "glm", replies)
    items = [{"benchmark": "spreadsheetbench", "task_id": task, "public": {"instruction": SHEET_VIEW["instruction"]},
              "private": {}} for task in ("s1", "s2")]
    ctx = engineer.Context(
        bench="spreadsheetbench", k=1, step="s1", evidence=FIXTURE, parent=empty(step="s0", evidence=FIXTURE),
        trajectories=sheet_trajectories(), corpora={"spreadsheetbench": Corpus("spreadsheetbench", items)},
        workers=workers, roles=roles, label="D/s1-spreadsheetbench/engineer", card=CARD,
        references={"s1": dict(SHEET_REFERENCE)},
        inputs_dirs={"c-sheet-fail": _workbook(tmp_path / "in-fail", FAILED_ROWS),
                     "c-sheet-pass": _workbook(tmp_path / "in-pass", PASSED_ROWS)})
    return ctx, glm


def sheet_change(description, code, value):
    test = test_case("c-sheet-fail", "before_call", {"kind": "note_contains", "value": value})
    return engineer.Change(1, "new", new(description, [test]), source(code), "0" * 64)  # a request hash


def test_codex_2_the_disclosed_values_trivial_and_public_ones_left_out(tmp_path, workers, monkeypatch):
    """Exactly the payload's disclosed values count: trivial ones (blank, boolean, < 3 significant digits, < 5 word
    characters) and those public in their own item (instruction, request view, the WHOLE public workbook) do not."""
    from fractions import Fraction

    from skillopt.coevo5 import leakage

    key = engineer.sheet_key
    assert [key(v) for v in (None, True, "", "  ", "TRUE", "false", 7, 99, 42.0, 0.5, 2.5, -42, "N/A", "Yes", "Q1",
                             "1-2", "45%")] == [None] * 17
    assert key(100) == ("number", Fraction(100)) and key(4242.5) == ("number", Fraction(8485, 2))
    assert key("$1,234.50") == ("number", Fraction(2469, 2)) and key(-1234) == ("number", Fraction(1234))
    assert key(2019) == ("number", Fraction(2019)) and engineer._numbers("in 2019") == {Fraction(2019)}
    assert set(leakage._numbers("in 2019")) == set()  # the frozen rule check skips years; this one does not
    assert key("Total") == ("text", ("total",)) and key("New York") == ("text", ("new", "york"))
    assert key("2023-01-15T00:00:00") == key("2023-01-15") == ("text", ("2023", "01", "15"))
    assert engineer._Seen(["Due 2023-01-15T00:00:00 or 1,234.5"]).has(key("2023-01-15"))
    assert engineer._Seen(["Due 2023-01-15T00:00:00 or 1,234.5"]).has(key(1234.5))
    ctx, glm = sheet_context(tmp_path, workers, [])
    assert engineer.payload(ctx)["trajectories"][0]["reference"] == SHEET_REFERENCE  # disclosed to the engineer
    assert engineer.disclosed(ctx) == {("number", Fraction(8485, 2)): "4242.5",
                                       ("text", ("contoso", "pharmaceuticals")): "Contoso Pharmaceuticals"}
    monkeypatch.setattr(engineer, "ENGINEER_SHOWN", {"failures": 0, "successes": 6})
    hidden, _ = sheet_context(tmp_path / "hidden", workers, [])
    assert "reference" not in json.dumps(engineer.payload(hidden)) and engineer.disclosed(hidden) == {}
    assert glm.seen == []


def test_codex_2_a_copied_reference_in_a_source_literal_is_adjudicated_with_the_values(tmp_path, workers):
    """A literal holding a disclosed value (rendered nowhere) is a finding; the ONE adjudication is shown the
    disclosed values (matched first) and the procedure's code; its veto drops the change and the fix survives."""
    literal = new("Counts the instruction's words.", [test_case("c-sheet-fail", "before_call",
                                                                {"kind": "note_contains", "value": "words."})])
    columns = new("Counts the instruction's columns.", [test_case("c-sheet-fail", "before_call",
                                                                  {"kind": "note_contains", "value": "columns."})])
    proposal = engineer_reply({"changes": [literal]}, [source(COPIED_LITERAL)])
    veto = {"verdict": "yes", "reason": "It copies an expected answer-cell value."}
    fixed = engineer_reply({"changes": [columns]}, [source(COLUMNS)])
    ctx, glm = sheet_context(tmp_path, workers, [proposal, veto, fixed])
    package, sealed = engineer.run(ctx)
    change = verified(sealed, "engineer")["changes"][0]
    leak = change["attempts"][0]["checks"][-1]
    assert leak["check"] == "C4" and not leak["passed"] and leak["detail"]["kept"] is False
    assert leak["detail"]["hits"] == [{"where": "literal", "bench": "spreadsheetbench",
                                       "reasons": [engineer.SHEET_REASON]}]
    assert leak["detail"]["sheet_values"] == 2
    assert change["attempts"][1]["passed"] and change["survived"] and len(package.procedures) == 1
    assert [c["role"] for c in ctx.roles.calls] == ["engineer", "leak_adjudicate", "engineer"]
    judged = glm.seen[1][1]
    assert judged["answer_values"] == ["4242.5", "Contoso Pharmaceuticals"] and "colliding_items" not in judged
    rule = judged["rule"]
    assert "- 4242.5" in rule and "Procedure code:\n" in rule and "TARGET = 4242.5" in rule
    assert ctx.sheet["shown"] == [("c-sheet-fail", SHEET_REFERENCE)]  # what the proposal call disclosed


def test_codex_2_a_copied_reference_in_a_rendered_note_is_adjudicated_not_dropped_mechanically(tmp_path, workers):
    """A value the code builds (no literal holds it) and writes into a note is a finding on every note showing it;
    the adjudicator decides: "yes" drops the change, "no" keeps it (a value computed on the public workbook may be
    legitimate)."""
    change = sheet_change("States the expected total.", COPIED_NOTE, "expected total")
    vetoed, glm = sheet_context(tmp_path / "veto", workers, [{"verdict": "yes", "reason": "Copies a value."}])
    report = engineer.check(change, vetoed)
    leak = report["checks"][-1]
    assert report["failed"] == "C4" and {h["where"] for h in leak["detail"]["hits"]} == {"note:c-sheet-fail",
                                                                                         "note:c-sheet-pass"}
    assert {h["bench"] for h in leak["detail"]["hits"]} == {"spreadsheetbench"}
    assert glm.seen[0][1]["answer_values"][0] == "4242.5" and "The expected total is 4242.5." in glm.seen[0][1]["rule"]
    kept, glm = sheet_context(tmp_path / "kept", workers, [{"verdict": "no", "reason": "Computed, not copied."}])
    report = engineer.check(change, kept)
    assert report["passed"] and [c["check"] for c in report["checks"]][-4:] == ["C4", "C7", "C8", "C9"]
    assert len(glm.seen) == 1


def test_codex_2_public_and_trivial_values_need_no_adjudication(tmp_path, workers):
    """Notes and literals quoting values public in their own item (the instruction, the whole public workbook, here a
    name beyond the preview rows), a note quoting its own item's workbook, and trivial values: no finding, no call."""
    ctx, glm = sheet_context(tmp_path, workers, [])
    report = engineer.check(sheet_change("Quotes the workbook's names.", PUBLIC_QUOTES, "Northwind Traders"), ctx)
    assert report["passed"] and glm.seen == [] and ctx.roles.calls == []
    assert [c["check"] for c in report["checks"]] == ["C1", "C2", "C4", "C3", "C5", "C6", "C4", "C7", "C8", "C9"]
