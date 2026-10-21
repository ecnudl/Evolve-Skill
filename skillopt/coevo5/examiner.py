"""The examiner (registration §6): rubrics, judging, revision and diagnosis.

A rubric is a bench's list of items -- an id, a text, an optional host check from the fixed library (``checks``) and the
item's basis -- plus one general rubric that never changes. Judging never sees a reference: the host checks run first
(any violated check fails the answer with that item); otherwise GLM-5.3 judges the text items. A revision (at the
bench's own stage only, never on ALFWorld) proposes at most three edits from the proposal half's disagreements with the
official scorer, each backed by proposal-half evidence, and is accepted only when it raises the balanced accuracy on a
selection panel of the check half, fixed before any judging, by >= 0.05 with >= 2 more correct verdicts; an invalid
verdict counts as wrong under either rubric. The revised rubric serves this stage's diagnosis only. Diagnosis codes
every failed answer of both halves: the decision table's own kind for a failure without an answer (``noncompletion``,
``malformed``), else the first violated fixed format check, else the first violated rubric check, else GLM-5.3 (shown
the reference) picks a text item or ``other``; an invalid reply is ``other``.

The selection panel is selection material: a revision accepted on it is better there by construction, so it is no
independent evidence that the examiner improved (§6, §12.7).

v2 (registration delta §3, §6): a rubric item's text and basis may have up to 450 characters (the reviser is still
asked for 300); a revision's edits are validated one by one -- an invalid edit is dropped and recorded, the valid ones
are applied in order, and the result must still be a valid rubric -- and the reply is invalid only when its envelope is
malformed or no edit is valid; an edit or removal of an item an earlier edit removed is skipped and recorded. The
diagnosis (after the decision table and the fixed format checks) no longer lets a rubric host check pre-empt the
model -- the v1 audit found such checks mislabelling answers whose reference has another form -- and asks GLM-5.3 for
the bench's frozen failure type (``TAXONOMY``), which takes precedence, else a rubric text item, else ``other``;
LiveMath's two meta-option types are assigned by table (``TABLE_CODES``) from the reference and the chosen letter; the
OfficeQA diagnosis sees up to ``DIAGNOSE_CONTEXT_CHARS`` characters of the pages.

v3 (registration delta §5, §6): the reviser sees each library check with its parameters (names, types, bounds), as the
initial rubric writer does, and its message is bounded (``ROLE_INPUT_BYTES``: shown disagreements beyond it are left out
from the end). A SpreadsheetBench task view adds the solver's own workbook preview (clipped); its reference view (never
the judge's) adds up to ``SHEET_CELLS`` answer-range cells with the values the scorer compared (``sheetview``).
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from copy import deepcopy
from fractions import Fraction
from functools import lru_cache

from skillopt.continual_eval.core import require

from . import checks
from .cells import run_parallel
from .protocol import (
    DIAGNOSE_CONTEXT_CHARS,
    RUNTIME,
    EXAMINER_BENCHES,
    ORDER,
    REQUIRED_FORMAT,
    RUBRIC_MAX_DISAGREEMENTS,
    RUBRIC_MAX_EDITS,
    RUBRIC_MIN_BA_GAIN,
    RUBRIC_MIN_MINORITY,
    RUBRIC_MIN_NET,
    RUBRIC_ITEM_CHARS,
    RUBRIC_PANEL_PER_CLASS,
    ROLE_INPUT_BYTES,
    SHEET_PREVIEW_CHARS,
    STRONGER_OPTION,
    TABLE_CODES,
    TAXONOMY,
)
from .roles import Invalid, fields, fit, items, text

GENERAL = "general"
MAX_ITEMS = 12
MAX_ITEM_CHARS = RUBRIC_ITEM_CHARS  # v2 §6 (v1: 300, which the reviser's prompt still asks for)
ITEM_ID = {GENERAL: re.compile(r"G[1-9][0-9]?"), "bench": re.compile(r"R[1-9][0-9]?")}
OTHER, NONCOMPLETION, MALFORMED = "other", "noncompletion", "malformed"
NO_ANSWER_KINDS = {"noncompletion": NONCOMPLETION, "malformed": MALFORMED}  # decision-table kinds (outcomes.py)
VIEW_CHARS = {"question": 2000, "context": 6000, "choices": 3000, "instruction": 3000, "answer": 4000}
TRACE_STEPS, TRACE_CHARS = 30, 300
CLIP_MARK = " [...]"

JUDGE_SYSTEM = (
    "You are an examiner. You receive a task as the solver saw it, the solver's answer, and the text items of a "
    "rubric. You do not know the correct answer and must not guess it. Decide whether the answer satisfies every text "
    "item. Reply with one JSON object only: {\"verdict\": \"pass\" or \"fail\", \"violated\": [ids of the violated "
    "items; empty exactly when the verdict is pass]}.")
DIAGNOSE_SYSTEM = (
    "You diagnose why a solver's answer was scored wrong. You receive the task as the solver saw it, the solver's "
    "answer, the reference (the correct answer, or for an interactive episode the task and its trajectory) and a list "
    "of failure codes, each with its description: error types (codes D1, D2, ...: what went wrong, judged only from "
    "what is visible in the task, the answer and the reference) and rubric criteria (codes R and G: what an answer of "
    "this kind should satisfy). Choose the single code that best explains the failure: an error type whenever one "
    "fits (error types take precedence), a rubric criterion only when no error type fits, and \"other\" when none "
    "fits. Reply with one JSON object only: {\"code\": \"<one of the listed codes or other>\"}.")
REVISE_SYSTEM = (
    "You revise the rubric an examiner uses to judge answers to one kind of task without seeing the correct answer. "
    "You receive the current rubric and answers on which the examiner's verdict disagreed with the official score, "
    "each with its task, the answer, the reference, the official result and the examiner's verdict. Propose at most "
    "three edits that would make the examiner agree with the official score more often on answers of this kind. Each "
    "edit is {\"op\": \"add\" | \"edit\" | \"remove\", \"id\": the item id (edit and remove only), \"text\": the item "
    "text (add and edit; at most 300 characters; a general criterion, never a fact about one task), \"check\": null or "
    "a host check {\"name\", \"params\"} from the listed library with exactly the parameters listed for it (add and "
    "edit), \"basis\": why (at most 300 characters), \"evidence\": [ids of the shown answers' tasks that motivate "
    "it]}. Reply with one JSON object only: {\"edits\": [...]}.")


# ----------------------------------------------------------------------------------------------------- rubrics
def validate_rubric(value, bench):
    """A rubric of ``bench`` (one of the five) or the general rubric: 1-12 items {"id", "text", "check", "basis"} with
    the scope's id form, distinct ids, texts of at most ``MAX_ITEM_CHARS`` characters (v2 §6: 450) and checks from the
    fixed library."""
    require(bench == GENERAL or bench in ORDER, "Unknown rubric scope")
    require(type(value) is dict and set(value) == {"bench", "items"} and value["bench"] == bench
            and type(value["items"]) is list and 1 <= len(value["items"]) <= MAX_ITEMS, "Malformed rubric")
    form = ITEM_ID[GENERAL if bench == GENERAL else "bench"]
    out = []
    for item in value["items"]:
        require(type(item) is dict and set(item) == {"id", "text", "check", "basis"}, "Malformed rubric item")
        require(type(item["id"]) is str and form.fullmatch(item["id"]) is not None, "Invalid rubric item id")
        for key in ("text", "basis"):
            require(type(item[key]) is str and item[key].strip() and len(item[key]) <= MAX_ITEM_CHARS,
                    "Rubric item text is 1-%d characters" % MAX_ITEM_CHARS)
        check = None if item["check"] is None else checks.validate(item["check"])
        out.append({"id": item["id"], "text": item["text"], "check": check, "basis": item["basis"]})
    require(len({i["id"] for i in out}) == len(out), "Duplicate rubric item id")
    return {"bench": bench, "items": out}


def _all(rubric, general):
    return list(rubric["items"]) + list(general["items"])


def _first_violation(rubric, general, output):
    for item in _all(rubric, general):
        if item["check"] is not None and checks.run(item["check"], output) is False:
            return item["id"]
    return None


def _text_items(rubric, general):
    return [{"id": i["id"], "text": i["text"]} for i in _all(rubric, general) if i["check"] is None]


# ------------------------------------------------------------------------------------------------------ views
def _clip(value, limit):
    """``value`` within ``limit`` characters, its truncation mark included."""
    if len(value) <= limit:
        return value
    return value[:limit - len(CLIP_MARK)] + CLIP_MARK if limit >= len(CLIP_MARK) else value[:limit]


def _trace_step(step):
    """One ALFWorld trajectory step within TRACE_CHARS characters in all: the action, then its observation."""
    action = step.get("action")
    action = _clip(action, TRACE_CHARS) if isinstance(action, str) else None
    observation = _clip(str(step.get("post_observation") or ""), TRACE_CHARS - len(action or ""))
    return {"action": action, "observation": observation}


@lru_cache(maxsize=1024)
def _preview(path):
    """v3 §6: the solver's own preview of the first input workbook (the frozen function and version of the run's
    runtime), as compact JSON clipped to ``SHEET_PREVIEW_CHARS``; None when it cannot be read."""
    from skillopt.continual_eval import backends

    try:
        value = backends._sheet_preview(path, version=RUNTIME["spreadsheetbench"]["spreadsheet_preview_version"])
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        return None
    return _clip(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str), SHEET_PREVIEW_CHARS)


def task_view(benchmark, public, *, trace=None, context_chars=None):
    """The task as the solver saw it, clipped (a role's input bound): never a reference. ``context_chars``: a wider
    bound of a QA context (v2 §3: the OfficeQA diagnosis; v3: the OfficeQA analyst)."""
    if benchmark == "alfworld":
        first = trace[0]["observation"] if trace else ""
        return {"initial_observation": _clip(str(first), VIEW_CHARS["context"])}
    if benchmark == "spreadsheetbench":
        files = public.get("input_files") or []
        return {"instruction": _clip(public["instruction"], VIEW_CHARS["instruction"]),
                "answer_position": public["answer_position"],
                "workbook_preview": _preview(str(files[0])) if files else None}
    view = {"question": _clip(public["question"], VIEW_CHARS["question"])}
    if benchmark == "livemath":
        view["choices"] = _clip(public["choices"], VIEW_CHARS["choices"])
    else:
        context = public["context"]
        joined = "\n".join(context) if isinstance(context, list) else context
        view["context"] = _clip(joined, context_chars or VIEW_CHARS["context"])
    return view


def answer_text(benchmark, output):
    """The answer a role reads: a QA reply's text, a SpreadsheetBench program, an ALFWorld episode's end."""
    if benchmark == "spreadsheetbench":
        code = output.get("code") if isinstance(output, dict) else None
        return _clip(code, VIEW_CHARS["answer"]) if isinstance(code, str) else None
    if benchmark == "alfworld":
        return json.dumps(output, sort_keys=True) if isinstance(output, dict) else None
    return _clip(output, VIEW_CHARS["answer"]) if isinstance(output, str) else None


def reference(benchmark, answer):
    """What a diagnosis or a revision may see besides the task (§6): the reference answer; SpreadsheetBench the answer
    position and the official per-case results; ALFWorld the episode's trajectory."""
    private = answer["private"]
    if benchmark == "searchqa":
        return {"answers": list(private["answers"])}
    if benchmark == "officeqa":
        return {"answer": private["answer"]}
    if benchmark == "livemath":
        from skillopt.continual_eval.datasets import livemath_options

        options = livemath_options(answer["public"]["choices"]) or []
        index = "ABCDE".find(private["answer"])
        return {"answer": private["answer"], "option": options[index] if 0 <= index < len(options) else None}
    if benchmark == "spreadsheetbench":  # v3 §6: the compared answer-range cells, when they could be read
        return {"answer_position": private["answer_position"], "official_cases": answer.get("cases") or [],
                "cells": answer.get("sheet_cells")}
    steps = answer.get("trace") or []
    return {"trajectory": [_trace_step(s) for s in steps[-TRACE_STEPS:]]}


# --------------------------------------------------------------------------------------------------- judging
def _judgment(rubric, general):
    ids = {i["id"] for i in _text_items(rubric, general)}

    def check(value):
        fields(value, ["verdict", "violated"])
        violated = items(value["violated"], limit=MAX_ITEMS * 2)
        if value["verdict"] not in ("pass", "fail") or any(type(v) is not str or v not in ids for v in violated):
            raise Invalid("verdict")
        if (value["verdict"] == "pass") != (not violated) or len(set(violated)) != len(violated):
            raise Invalid("verdict")
        return {"verdict": value["verdict"], "violated": sorted(violated)}
    return check


def judge(roles, benchmark, rubric, general, answer, *, label):
    """{"verdict": "pass" | "fail" | "invalid", "item", "by": "check" | "model"} for one answer (never its
    reference)."""
    item = _first_violation(rubric, general, answer["output"])
    if item is not None:
        return {"verdict": "fail", "item": item, "by": "check"}
    payload = {"task": task_view(benchmark, answer["public"], trace=answer.get("trace")),
               "answer": answer_text(benchmark, answer["output"]), "items": _text_items(rubric, general)}
    value = roles.ask("judge", JUDGE_SYSTEM, payload, label=label, check=_judgment(rubric, general))
    if value is None:
        return {"verdict": "invalid", "item": None, "by": "model"}
    return {"verdict": value["verdict"], "item": (value["violated"] or [None])[0], "by": "model"}


def judge_all(roles, benchmark, rubric, general, answers, *, label, workers):
    keys = [a["key"] for a in answers]
    results = run_parallel(lambda a: judge(roles, benchmark, rubric, general, a, label="%s/%s" % (label, a["key"])),
                           answers, workers=workers)
    return dict(zip(keys, results))


def judgeable(answer):
    """An answer the examiner can judge: a delivered answer with a known official result."""
    return answer["official"] in ("pass", "fail") and answer_text(answer["benchmark"], answer["output"]) is not None


# -------------------------------------------------------------------------------------------------- revision
def _order(values, seed, tag):
    key = lambda v: hashlib.sha256(json.dumps([seed, tag, v]).encode()).hexdigest()  # noqa: E731
    return sorted(values, key=key)


def selection_panel(answers, *, seed, tag):
    """§6 step 3, fixed before any judging: one judgeable answer per check-half item (seeded), then at most 20
    officially passed and 20 officially failed answers (seeded). None when the minority class has fewer than 8."""
    by_item = {}
    for answer in answers:
        if answer["half"] == "check" and judgeable(answer):
            by_item.setdefault(answer["item"], []).append(answer)
    chosen = [_pick(group, seed, tag) for _, group in sorted(by_item.items())]
    classes = {c: _order([a["key"] for a in chosen if a["official"] == c], seed, tag + ":" + c)[:RUBRIC_PANEL_PER_CLASS]
               for c in ("pass", "fail")}
    if min(len(v) for v in classes.values()) < RUBRIC_MIN_MINORITY:
        return None
    return classes["pass"] + classes["fail"]


def _pick(group, seed, tag):
    keys = _order([a["key"] for a in group], seed, tag + ":item:" + group[0]["item"])
    return next(a for a in group if a["key"] == keys[0])


def disagreements(answers, judgments, *, seed, tag):
    """§6 step 2: proposal-half answers judged validly against the official result, at most 10 of each kind (the
    examiner passed an officially failed answer; it failed an officially passed one), seeded."""
    half = RUBRIC_MAX_DISAGREEMENTS // 2
    out = []
    for official, verdict in (("fail", "pass"), ("pass", "fail")):
        keys = [a["key"] for a in answers if a["half"] == "proposal" and judgeable(a) and a["official"] == official
                and judgments[a["key"]]["verdict"] == verdict]
        out += _order(keys, seed, tag + ":" + official)[:half]
    return out


def balanced_accuracy(panel, answers, judgments):
    """(balanced accuracy, correct verdicts) on the panel; an invalid verdict is wrong under either rubric."""
    by_key = {a["key"]: a for a in answers}
    correct = {"pass": 0, "fail": 0}
    total = {"pass": 0, "fail": 0}
    for key in panel:
        official = by_key[key]["official"]
        total[official] += 1
        correct[official] += judgments[key]["verdict"] == official
    rate = sum(Fraction(correct[c], total[c]) for c in total) / 2
    return rate, correct["pass"] + correct["fail"]


def _edit(edit, ids, shown):
    """One edit of a revision, validated on its own (v2 §6); raises ``Invalid`` (or ``ValueError`` from a check's
    parameters, ``TypeError`` from a value of the wrong type) when it cannot be used."""
    if type(edit) is not dict or edit.get("op") not in ("add", "edit", "remove"):
        raise Invalid("edit")
    keys = {"op", "evidence", "basis"} | ({"id"} if edit["op"] != "add" else set()) | (
        {"text", "check"} if edit["op"] != "remove" else set())
    # a key the prompt gives only to other ops (an add's id, a remove's text and check) is dropped, not refused: the
    # GLM-5.3 smoke's add carried the id it expected (registration §25); apply_edits numbers adds
    fields(edit, keys, {"id", "text", "check"} - keys)
    edit = {k: v for k, v in edit.items() if k in keys}
    if edit["op"] != "add" and (type(edit["id"]) is not str or edit["id"] not in ids):
        raise Invalid("edit id")
    text(edit["basis"], limit=MAX_ITEM_CHARS)
    if edit["op"] != "remove":
        text(edit["text"], limit=MAX_ITEM_CHARS)
        if edit["check"] is not None:
            edit["check"] = checks.validate(edit["check"])
    evidence = items(edit["evidence"], limit=RUBRIC_MAX_DISAGREEMENTS)
    return {**edit, "evidence": [e for e in evidence if type(e) is str and e in shown]}


def _edits(rubric, shown, dropped=None):
    """The reply's edits validated one by one (v2 §6): an invalid edit is appended to ``dropped`` as {"index",
    "reason"} and left out; the reply is invalid when its envelope is malformed or no edit is valid."""
    ids = {i["id"] for i in rubric["items"]}
    dropped = [] if dropped is None else dropped

    def check(value):
        fields(value, ["edits"])
        out, del_ = [], []
        for index, edit in enumerate(items(value["edits"], limit=RUBRIC_MAX_EDITS)):
            try:
                out.append(_edit(edit, ids, shown))
            except (ValueError, TypeError) as error:  # Invalid is a ValueError; a wrong type is the edit's own fault
                del_.append({"index": index, "reason": str(error)[:80] or type(error).__name__})
        dropped[:] = del_
        if not out:
            raise Invalid("no valid edit")
        return out
    return check


def apply_edits(rubric, edits):
    """(the edits applied, the rubric after them): the edits that carry proposal-half evidence (others are dropped, §6
    step 2), in the reply's order; v2 §6: an edit or removal of an item an earlier edit removed is skipped. The rubric
    is None when the result is not a valid rubric -- then nothing is revised."""
    items_, used = deepcopy(rubric["items"]), []
    numbers = [int(i["id"][1:]) for i in items_]
    for edit in edits:
        if not edit["evidence"]:
            continue
        if edit["op"] == "add":
            numbers.append(max(numbers or [0]) + 1)
            items_.append({"id": "R%d" % numbers[-1], "text": edit["text"], "check": edit["check"],
                           "basis": edit["basis"]})
            used.append(edit)
            continue
        index = next((k for k, i in enumerate(items_) if i["id"] == edit["id"]), None)
        if index is None:  # removed by an earlier edit
            continue
        if edit["op"] == "remove":
            del items_[index]
        else:
            items_[index] = {"id": edit["id"], "text": edit["text"], "check": edit["check"], "basis": edit["basis"]}
        used.append(edit)
    try:
        return used, validate_rubric({"bench": rubric["bench"], "items": items_}, rubric["bench"])
    except ValueError:
        return used, None


def revise(roles, benchmark, rubric, general, answers, *, seed, tag, label, workers):
    """§6 for one stage: judge every judgeable answer with the current rubric, propose edits from the proposal half's
    disagreements, and accept them only by the selection rule. Returns the record, with "rubric" the one diagnosis
    uses (the revised one only when accepted) and "judgments" the current rubric's verdicts."""
    if benchmark not in EXAMINER_BENCHES:
        return {"status": "not_revised", "rubric": rubric}
    panel = selection_panel(answers, seed=seed, tag=tag + ":panel")
    pool = [a for a in answers if judgeable(a)]
    judgments = judge_all(roles, benchmark, rubric, general, pool, label=label + "/judge", workers=workers)
    record = {"panel": panel, "judgments": judgments, "rubric": rubric}
    if panel is None:
        return {**record, "status": "insufficient_panel"}
    shown = disagreements(pool, judgments, seed=seed, tag=tag + ":disagreements")
    if not shown:
        return {**record, "status": "no_disagreements"}
    by_key = {a["key"]: a for a in pool}
    payload = fit({"rubric": rubric, "library": library(),
                   "disagreements": [{"task_id": by_key[k]["item"],
                                      "task": task_view(benchmark, by_key[k]["public"], trace=by_key[k].get("trace")),
                                      "answer": answer_text(benchmark, by_key[k]["output"]),
                                      "reference": reference(benchmark, by_key[k]), "official": by_key[k]["official"],
                                      "examiner": judgments[k]} for k in shown]}, "disagreements", ROLE_INPUT_BYTES)
    shown = shown[:len(payload["disagreements"])]  # v3 §6: only the disagreements actually shown back an edit
    dropped = []
    edits = roles.ask("revise", REVISE_SYSTEM, payload, label=label + "/revise",
                      check=_edits(rubric, {by_key[k]["item"] for k in shown}, dropped))
    if edits is None:
        return {**record, "status": "invalid_reply", "shown": shown, "dropped_edits": dropped}
    record["dropped_edits"] = dropped
    used, revised = apply_edits(rubric, edits)
    record["skipped_edits"] = [n for n, edit in enumerate(edits) if not any(edit is u for u in used)]
    if revised is None or not used:
        return {**record, "status": "no_valid_edits", "shown": shown, "edits": edits}
    old = balanced_accuracy(panel, pool, judgments)
    new_judgments = judge_all(roles, benchmark, revised, general, [by_key[k] for k in panel],
                              label=label + "/judge-revised", workers=workers)
    new = balanced_accuracy(panel, pool, new_judgments)
    accepted = new[0] - old[0] >= RUBRIC_MIN_BA_GAIN and new[1] - old[1] >= RUBRIC_MIN_NET
    return {**record, "status": "accepted" if accepted else "rejected", "shown": shown, "edits": edits,
            "candidate": revised, "candidate_judgments": new_judgments, "rubric": revised if accepted else rubric,
            "balanced_accuracy": {"old": str(old[0]), "new": str(new[0])}, "correct": {"old": old[1], "new": new[1]},
            "invalid": {"old": sum(judgments[k]["verdict"] == "invalid" for k in panel),
                        "new": sum(new_judgments[k]["verdict"] == "invalid" for k in panel)}}


def library():
    """v3 §5: the host-check library as the reviser sees it -- every check with its parameters (type and bounds), the
    schema ``checks.validate`` enforces."""
    def described(rule):
        return "true or false" if rule[0] is bool else "integer %d-%d" % (rule[1], rule[2])
    return {name: {key: described(rule) for key, rule in schema.items()}
            for name, (_, schema) in sorted(checks.CHECKS.items())}


# ------------------------------------------------------------------------------------------------- diagnosis
def taxonomy(benchmark, *, model=False):
    """v2 §3: the bench's frozen failure types as listed codes [{"id", "text"}]; ``model``: only those the model may
    choose (not the table's)."""
    table = TABLE_CODES.get(benchmark, ()) if model else ()
    return [{"id": code, "text": meaning} for code, meaning in TAXONOMY[benchmark] if code not in table]


OPTION = re.compile(r"(?m)^([A-E])\. (.*)$")
LETTER = re.compile(r"(?<![A-Za-z])([A-Ea-e])(?![A-Za-z])")


def stronger_option_code(answer):
    """v2 §3: LiveMath's meta-option types by table -- D1 when the item offers the option that a stronger result can
    be proven, it is the reference and the answer's single letter picked another option; D2 when the answer picked it
    and the reference is another; else None (the model diagnoses)."""
    meta = [letter for letter, line in OPTION.findall(answer["public"].get("choices") or "")
            if line.strip() == STRONGER_OPTION]
    tag = checks.last_answer(answer["output"]) if isinstance(answer["output"], str) else None
    letters = LETTER.findall(tag or "")
    correct = answer["private"].get("answer")
    if len(meta) != 1 or len(letters) != 1 or type(correct) is not str:
        return None
    chosen, correct = letters[0].upper(), correct.strip().upper()
    if chosen != correct and correct == meta[0]:
        return TABLE_CODES["livemath"][0]
    if chosen != correct and chosen == meta[0]:
        return TABLE_CODES["livemath"][1]
    return None


def _code(rubric, general):
    allowed = ({i["id"] for i in _text_items(rubric, general)} | {OTHER}
               | {c["id"] for c in taxonomy(rubric["bench"], model=True)})

    def check(value):
        fields(value, ["code"])
        if value["code"] not in allowed:
            raise Invalid("code")
        return value["code"]
    return check


def diagnose_one(roles, benchmark, rubric, general, answer, *, label):
    """{"code", "by"} for one failed answer (§6; v2 §3: no rubric check pre-empts the model, LiveMath's table codes)."""
    if answer["kind"] in NO_ANSWER_KINDS:
        return {"code": NO_ANSWER_KINDS[answer["kind"]], "by": "table"}
    for name in REQUIRED_FORMAT[benchmark]:
        if checks.run({"name": name, "params": {}}, answer["output"]) is False:
            return {"code": name, "by": "format"}
    if benchmark == "livemath":
        code = stronger_option_code(answer)
        if code is not None:
            return {"code": code, "by": "table"}
    payload = {"task": task_view(benchmark, answer["public"], trace=answer.get("trace"),
                                 context_chars=DIAGNOSE_CONTEXT_CHARS.get(benchmark)),
               "answer": answer_text(benchmark, answer["output"]), "reference": reference(benchmark, answer),
               "codes": taxonomy(benchmark, model=True) + _text_items(rubric, general)
               + [{"id": OTHER, "text": "None of the listed codes fits."}]}
    code = roles.ask("diagnose", DIAGNOSE_SYSTEM, payload, label=label, check=_code(rubric, general))
    return {"code": OTHER if code is None else code, "by": "model" if code is not None else "invalid"}


def diagnose(roles, benchmark, rubric, general, failures, *, label, workers):
    """{answer key: {"code", "by"}} for every failed answer of both halves."""
    results = run_parallel(lambda a: diagnose_one(roles, benchmark, rubric, general, a,
                                                  label="%s/%s" % (label, a["key"])), failures, workers=workers)
    return {a["key"]: r for a, r in zip(failures, results)}


def code_meanings(benchmark, rubric, general):
    """What each diagnosis code means, for the analyst."""
    fixed = {NONCOMPLETION: "The solver did not complete a reply (truncated, filtered or empty).",
             MALFORMED: "The reply had no extractable answer form (no program, an invalid action).",
             OTHER: "None of the rubric's codes fits."}
    fixed.update({name: "The answer fails the fixed format check %s." % name for name in REQUIRED_FORMAT[benchmark]})
    fixed.update({c["id"]: c["text"] for c in taxonomy(benchmark)})
    fixed.update({i["id"]: i["text"] for i in _all(rubric, general)})
    return fixed
