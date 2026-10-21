"""Generate OfficeQA validation tasks from a stage's TRAINING tasks, to serve as the selection set of the
validation-gated learners (learning v9 / v10) in place of the 24-item validation part of the paper's split
(docs/handoff/officeqa-generated-validation-design-20261014.md).

Label-free and train-only: the writer sees one training task's PUBLIC fields (its question and the parsed pages that
came with it) and writes up to ``--per-task`` new questions over the same pages. It never states an answer. It names
the printed figures the answer is computed from (each with its value as printed and a verbatim quote of the place),
an arithmetic expression over them and the number of decimal places the question asks for; the reference answer is
COMPUTED here, exactly (rational arithmetic, + - * / abs min max only -- the expression is parsed against a closed
grammar and never executed as code). No reference answer of a training task, no validation / test item and no solver
outcome enters a prompt. A candidate survives when

1. deterministic filters hold (every quote is verbatim in the pages and its figure is the whole content of a table
   cell of the pages there, with its sign; the expression is inside the grammar and the answer depends on every
   figure; the rounding is not a tie and leaves no trailing zero; the question states none of its figures nor the
   answer in digits; lengths are bounded; it differs from the source question and from every other generated or
   training question), and
2. an independent reviewer call judges the figures grounded, the computation the one asked for, the reading unique,
   the unit and rounding stated, the question distinct from the source question, and the question answerable only
   from the pages (no stated or hinted answer).

No filter uses a solver's answer, so the pool is not conditioned on being solved. The generated task keeps the source
task's pages as its context and the computed number as its reference; it is scored by the frozen OfficeQA exact-match
scorer like any OfficeQA task. The run lifecycle (locks, sealed records, no resume) is the SearchQA generator's.

Usage:
  python scripts/generate_officeqa_tasks.py prepare --study <extension study> --split <its split> \\
      --repo <credential repo> --seed <stage seed> --output <new dir>
  python scripts/generate_officeqa_tasks.py run --output <prepared dir>   # writes items.json, records.json
  python scripts/generate_officeqa_tasks.py check --output <dir>          # exit 0 only for a completed generation
"""
from __future__ import annotations

import ast
import bisect
import hashlib
import re
import sys
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_searchqa_tasks as base  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "generated-officeqa-tasks-v1"
BENCHMARK = "officeqa"
PER_TASK = 4
MAX_FIGURES, MAX_QUOTE, MAX_EXPRESSION, MAX_DECIMALS, MAX_DEPTH = 6, 400, 200, 4, 12
MAX_VALUE = 24  # characters of a printed figure
MAX_CELL = 64  # characters searched for a cell bar on either side of a figure
WRITER = (
    "You write evaluation questions for a document question-answering task over U.S. Treasury Bulletin pages. You "
    "are given ONE source item: a question and the parsed page(s) it was asked about. Write up to {count} NEW "
    "questions over the SAME pages in the style of the source question (a precise, self-contained request for one "
    "number that names the table or series, the period and the unit as needed), each about DIFFERENT figures than "
    "the source question and than each other.\n"
    "Do NOT state an answer. For each question give instead:\n"
    "- \"figures\": the one to {figures} printed figures the answer is computed from. For each figure: a short "
    "lower-case \"name\" (a, b, c, ...), its \"value\" exactly as printed (digits with their commas, decimal point "
    "and minus sign, for example \"1,513\" or \"-18\" or \"4.73\"), and a \"quote\": a verbatim excerpt of the pages "
    "(at most 300 characters; for a table the row with its label) that contains this value;\n"
    "- \"expression\": an arithmetic expression over the figure names that computes the answer, using only + - * / "
    "parentheses, plain numbers, abs(), min() and max() -- for example \"(b - a) / a * 100\", \"(a + b + c) / 3\" "
    "or \"a / 1000\";\n"
    "- \"decimals\": the number of decimal places the answer is rounded to (0 to {decimals}).\n"
    "Requirements:\n"
    "- the pages alone are enough to answer, and only one reading of the question fits them;\n"
    "- the question says exactly which unit the answer is in and how it is rounded, asks for a plain number, and "
    "never states any of the figures it needs;\n"
    "- at least half of your questions combine two or more figures (a difference, sum, ratio, share, percent "
    "change or average, possibly with a unit conversion); prefer questions that need care in choosing the right "
    "row, column, period, unit or footnote;\n"
    "- use only figures that are legible and unambiguous in the pages (nothing read off a chart, nothing "
    "estimated), and only figures that stand alone in a table cell: the cell holds just the number, possibly with "
    "a currency or percent sign or a footnote mark -- no numbers from running text, no dates, no fractions, no "
    "cells with letters or several numbers.\n"
    "If the pages do not support such a question (a chart, a page without numeric tables), return fewer questions "
    "or none.\n"
    "Return one JSON object and nothing else: {{\"tasks\": [{{\"question\": \"...\", \"figures\": [{{\"name\": "
    "\"a\", \"value\": \"...\", \"quote\": \"...\"}}], \"expression\": \"...\", \"decimals\": 0}}]}}")
REVIEWER = (
    "You check an evaluation question against parsed U.S. Treasury Bulletin pages. You are given the pages, the "
    "source question they came with, a new question, the figures its answer is computed from (each with its printed "
    "value and a quote of the pages), the arithmetic expression over those figures, the number of decimal places "
    "and the answer computed from them. Decide six things:\n"
    "- grounded: is every figure the value the pages print for exactly the thing the question refers to (the right "
    "table, row, column, period and unit)?\n"
    "- computation: does the expression compute exactly what the question asks for, including any unit conversion, "
    "and does the question ask for this rounding?\n"
    "- unique: do the pages support only this reading and this answer (no other table, revision or footnote that "
    "fits the question equally well)?\n"
    "- format: does the question state the unit and the rounding, so that the computed answer written as a plain "
    "number is the only correctly formatted answer?\n"
    "- distinct: does the question ask for something else than the source question does (not a paraphrase of it "
    "and not the same figure)?\n"
    "- needs_pages: can the question be answered only by reading the pages -- it neither states nor hints at its "
    "answer or at any of its figures (in digits, in words or in any other notation), and its answer does not follow "
    "from the wording of the question alone?\n"
    "Return one JSON object and nothing else: {\"grounded\": true|false, \"computation\": true|false, \"unique\": "
    "true|false, \"format\": true|false, \"distinct\": true|false, \"needs_pages\": true|false, \"reason\": "
    "\"at most 200 characters\"}")
VERDICTS = ("grounded", "computation", "unique", "format", "distinct", "needs_pages")
FILTERS = ("every field bounded in length before it is parsed; question 60-700 chars; one to six figures with "
           "distinct names [a-z][a-z0-9_]*; each value a printed number of at most 24 chars (optional ASCII minus, "
           "$ and %, thousands commas, decimal point); each quote 1-400 chars, inside the pages (case ignored, "
           "whitespace collapsed), and its value the whole content of a table cell OF THE PAGES at a place the "
           "quote stands, read in the pages beyond the quote's ends: the text between the two cell bars around "
           "the value, on one line of the pages, is the value itself, at most with a currency sign in front, a "
           "percent sign behind and footnote marks like '10/' after it -- a cell holding anything else is no "
           "figure, nor is a number in running text or on a line of its own; " "expression at most 200 ASCII chars inside the grammar {+ - "
           "* / unary minus, parentheses, the figure names, abs/min/max, constants spelled as plain decimal "
           "digits with at most 15 digits on either side of the point -- read from their spelling, never as "
           "floats}, naming every figure, evaluated exactly over the rationals, no division by zero, magnitude "
           "below 1e15; decimals an integer 0-4; the exact value is not a rounding tie and the rounded text has no "
           "trailing zero after the decimal point; for every figure some other value gives a different answer "
           "that is itself a valid reference by these rules; no number token of the question (digits, with or without "
           "separators, a leading-dot decimal part, an exponent) has the value of a figure or of the answer "
           "(sign ignored; numbers in words or as powers are left to the reviewer); the question differs, after "
           "the scorer's normalization, from the source question, from every training question and from every "
           "earlier accepted question (exact identity, not semantic deduplication -- paraphrases of the source "
           "question are left to the reviewer)")
_FIGURE = re.compile(r"(-?)\$?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)%?")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,15}")
_LITERAL = re.compile(r"\d{1,15}(?:\.\d{1,15})?")  # a constant of an expression: plain decimal digits only
_MARKS = re.compile(r"(?: \d{1,2}/){1,4}")  # footnote marks behind a figure in its cell: "1,006 10/", "507 1/ 2/"
_OPERATORS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
              ast.Div: lambda a, b: a / b}
_FUNCTIONS = {"abs": abs, "min": min, "max": max}


def tool_sha256():
    """The generator's identity: this file and the shared lifecycle it runs in."""
    return hashlib.sha256((base._sha(Path(__file__)) + base.tool_sha256()).encode()).hexdigest()


def question_key(text):
    from skillopt.envs.officeqa.evaluator import normalize_answer

    return normalize_answer(text)


def figure(text):
    """The exact value of a number as a table prints it (optional minus, $ and %, thousands commas, a decimal
    point), or None."""
    match = _FIGURE.fullmatch(text) if len(text) <= MAX_VALUE else None
    return None if match is None else Fraction(match.group(1) + match.group(2).replace(",", ""))


def lines(text):
    """(the text with whitespace collapsed -- exactly ``_squash`` of it --, the offsets in it at which the lines of
    the original begin): what ``printed`` reads a table cell in."""
    kept = [line for line in map(base._squash, text.splitlines()) if line]
    starts, offset = [], 0
    for line in kept:
        starts.append(offset)
        offset += len(line) + 1
    return " ".join(kept), starts


def printed(value, quote, pages, starts):
    """Is the figure the whole content of a table cell of the PAGES at a place the quote stands? A whitelist, read
    in the pages and not in the quote (a quote cropped around a part of a number or behind its sign proves
    nothing): the text between the two cell bars around the value, ON ONE LINE of the pages, must BE the value --
    at most with a currency sign in front (after the minus, if any), a percent sign behind and footnote marks of
    the form ``10/`` after it. A cell that holds anything else (a second sign, a parenthesis, more digits, a
    separator, a letter, a fraction, a revision mark, a label, another number) is not a figure, and neither is a
    number in running text or on a line of its own between two tables. ``pages, starts`` come from ``lines``."""
    digits = value[1:] if value.startswith("-") else value
    sign = "-" if value.startswith("-") else ""
    bare = digits.lstrip("$").rstrip("%")
    forms = {sign + money + bare + percent for money in ("", "$") for percent in ("", "%")
             if (money or not digits.startswith("$")) and (percent or not digits.endswith("%"))}
    for place in re.finditer(re.escape(quote), pages, flags=re.IGNORECASE):
        for match in re.finditer(re.escape(value), pages[place.start():place.end()]):
            at, end = place.start() + match.start(), place.start() + match.end()
            # a cell of this kind is short: bars farther away than the window mean a cell with more in it
            low, high = pages.rfind("|", max(0, at - MAX_CELL), at), pages.find("|", end, end + MAX_CELL)
            if low < 0 or high < 0 or bisect.bisect_right(starts, low) != bisect.bisect_right(starts, high):
                continue
            cell = pages[low + 1:high].strip()
            if any(cell == form or (cell.startswith(form) and _MARKS.fullmatch(cell[len(form):])) for form in forms):
                return True
    return False


def evaluate(expression, values):
    """The exact value of an arithmetic expression over the named figures, or None when the text is outside the
    closed grammar, leaves a figure unused or divides by zero. The text is only parsed and walked: never compiled or
    executed."""
    if not expression.isascii() or "\n" in expression or "\r" in expression:
        return None
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    used = set()

    def walk(node, depth):
        require(depth <= MAX_DEPTH, "Expression too deep")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            # the constant's own spelling, exactly: never the float Python read it as (1e-400, 9007199254740993.0)
            spelling = expression[node.col_offset:node.end_col_offset]
            require(_LITERAL.fullmatch(spelling) is not None, "Constant outside the grammar")
            return Fraction(spelling)
        if isinstance(node, ast.Name) and node.id in values:
            used.add(node.id)
            return values[node.id]
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.USub, ast.UAdd):
            value = walk(node.operand, depth + 1)
            return -value if type(node.op) is ast.USub else value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](walk(node.left, depth + 1), walk(node.right, depth + 1))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS
                and not node.keywords and (len(node.args) == 1 if node.func.id == "abs" else 2 <= len(node.args) <= 8)):
            return _FUNCTIONS[node.func.id](*(walk(a, depth + 1) for a in node.args))
        raise ValueError("Outside the expression grammar")

    try:
        value = walk(tree.body, 0)
    except (ValueError, ZeroDivisionError, OverflowError, RecursionError):
        return None
    return value if used == set(values) and abs(value) < 10 ** 15 else None


def depends(expression, values, decimals):
    """Does the ANSWER change with every figure? For each figure some other value must give a different answer that
    is itself a valid reference (evaluable, no rounding tie, no trailing zero -- the rules of ``rounded``); a
    substitution that yields no valid reference proves nothing. (``a - a``, ``a / a``, ``min(abs(a - 18), 0.5)``
    or ``5 + a / (abs(a) + 1) / 100`` at no decimals name a figure without the answer resting on it.)"""
    def answer(given):
        value = evaluate(expression, given)
        return None if value is None else rounded(value, decimals)

    reference = answer(values)
    if reference is None:
        return False
    for name, value in values.items():
        others = [v for other, v in values.items() if other != name]
        trials = [value + 1, value - 1, 2 * value + 1, value + 3, value + 10 ** 6, value - 10 ** 6]
        trials += [v + shift for v in others for shift in (1, -1)]
        if not any(answer({**values, name: trial}) not in (None, reference) for trial in trials):
            return False
    return True


def rounded(value, decimals):
    """The value at ``decimals`` places as plain text, or None for a tie (the answer would depend on the rounding
    convention) or a trailing zero after the decimal point (it would depend on whether zeros are written)."""
    scaled = value * 10 ** decimals
    whole = scaled.numerator // scaled.denominator
    rest = scaled - whole
    if rest == Fraction(1, 2):
        return None
    whole += rest > Fraction(1, 2)
    digits = str(abs(whole)).rjust(decimals + 1, "0")
    text = digits[:-decimals] + "." + digits[-decimals:] if decimals else digits
    if decimals and text.endswith("0"):
        return None
    return ("-" if whole < 0 else "") + text


def _scaled(digits, shift):
    """A decimal number as (integer without trailing zeros, power of ten): the same pair for every spelling of one
    value, without ever raising ten to the exponent."""
    number = int(digits)
    if number == 0:
        return 0, 0
    while number % 10 == 0:
        number, shift = number // 10, shift + 1
    return number, shift


def _decimal(value):
    """The pair of ``_scaled`` for the magnitude of an exact value with a finite decimal expansion, else None."""
    numerator, denominator, places = abs(value.numerator), value.denominator, 0
    while denominator % 10 == 0:
        denominator, places = denominator // 10, places + 1
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator, numerator, places = denominator // prime, numerator * (10 // prime), places + 1
    return _scaled(numerator, -places) if denominator == 1 else None


def _numbers(text):
    """The values of the number tokens of a text, each as the pair of ``_scaled``: digits with thousands separators,
    a decimal part with or without leading digits, an exponent of any length and padding ("2.0", "02", ".2e1" and
    "0.2e0000000001" are the value 2). A token with an exponent counts with and without it. Numbers written in
    words or as products of powers are not recognized here: they are left to the reviewer."""
    found = set()
    for whole, part, exponent in re.findall(r"(\d[\d,]*)?(?:\.(\d+))?(?:[eE]([-+]?\d+))?", text):
        if not whole and not part:
            continue
        digits = whole.replace(",", "") + part
        found.add(_scaled(digits, -len(part)))
        if exponent:
            found.add(_scaled(digits, int(exponent) - len(part)))
    return found


def admit(candidate, source, seen_questions):
    """(None, the fields of the candidate's record incl. its computed answer) for a survivor of the deterministic
    filters, else (the first reason it fails, None)."""
    if (type(candidate) is not dict or type(candidate.get("question")) is not str
            or type(candidate.get("expression")) is not str or type(candidate.get("decimals")) is not int
            or type(candidate.get("figures")) is not list or not 1 <= len(candidate["figures"]) <= MAX_FIGURES
            or any(type(f) is not dict or any(type(f.get(k)) is not str for k in ("name", "value", "quote"))
                   for f in candidate["figures"])):
        return "malformed", None
    # every length is bounded BEFORE anything is parsed or converted: one hostile candidate costs only itself
    if (not 60 <= len(candidate["question"]) <= 2000 or len(candidate["expression"]) > 2 * MAX_EXPRESSION
            or any(len(f["name"]) > 16 or len(f["value"]) > 2 * MAX_VALUE or len(f["quote"]) > 4 * MAX_QUOTE
                   for f in candidate["figures"])):
        return "field_length", None
    question, expression = base._squash(candidate["question"]), base._squash(candidate["expression"])
    figures = [{k: base._squash(f[k]) for k in ("name", "value", "quote")} for f in candidate["figures"]]
    if not 60 <= len(question) <= 700:
        return "question_length", None
    if len({f["name"] for f in figures}) != len(figures) or any(_NAME.fullmatch(f["name"]) is None for f in figures):
        return "figure_names", None
    (pages, starts), values = lines(source["context"]), {}
    for item in figures:
        value = figure(item["value"])
        if value is None:
            return "figure_not_a_number", None
        if not 1 <= len(item["quote"]) <= MAX_QUOTE or not printed(item["value"], item["quote"], pages, starts):
            return "quote_not_verbatim_or_without_figure", None
        values[item["name"]] = value
    if len(expression) > MAX_EXPRESSION or not 0 <= candidate["decimals"] <= MAX_DECIMALS:
        return "expression_or_decimals_out_of_bounds", None
    value = evaluate(expression, values)
    if value is None:
        return "expression_outside_grammar_or_figure_unused", None
    answer = rounded(value, candidate["decimals"])
    if answer is None:
        return "rounding_tie_or_trailing_zero", None
    if not depends(expression, values, candidate["decimals"]):
        return "expression_outside_grammar_or_figure_unused", None
    # compared as VALUES: "2.0", "02" or "0.2e1" in the question states the figure 2 as much as "2" does
    if _numbers(question) & {_decimal(v) for v in (*values.values(), Fraction(answer))}:
        return "figure_or_answer_in_question", None
    key = question_key(question)
    if key == question_key(source["question"]) or key in seen_questions:
        return "duplicate_question", None
    return None, {"question": question, "figures": figures, "expression": expression,
                  "decimals": candidate["decimals"], "answer": answer}


def write_payload(public):
    return {"source_question": public["question"], "pages": public["context"]}


def review_payload(public, item):
    return {"pages": public["context"], "source_question": public["question"], "question": item["question"],
            "figures": item["figures"], "expression": item["expression"], "decimals": item["decimals"],
            "computed_answer": item["answer"]}


def task_item(public, item):
    return {"id": item["id"], "question": item["question"], "context": public["context"], "answer": item["answer"]}


def prepare(study, split_path, output, repo, *, seed, per_task=PER_TASK):
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    version, policy, budget = tool._protocol("v11")
    require(type(per_task) is int and 1 <= per_task <= 4, "One to four questions per training task")
    root, protocol = tool._study(study)
    out = safe_path(output)
    tool._outside(out, root, protocol, [split_path])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    tool.check_split(split, protocol, BENCHMARK)
    dev_path = tool.dev_panel_path(protocol, BENCHMARK)
    dev_panel = read_json(dev_path)
    # exactly the training rows a learning stage of this seed draws (the stage tool's own outcome-blind draw)
    train, families = tool.train_tasks(dev_panel, split, BENCHMARK, seed)
    require(all(type(t["public"]["context"]) is str for t in train), "A training task's pages are one text")
    panel = {**deepcopy(dev_panel), "tasks": deepcopy(train)}
    value = ae.manifest(panel, step_families=sorted(families), challenge_families=[],
                        model=deepcopy(protocol["model"]), budget=budget,
                        runtime=protocol["roles"][BENCHMARK]["runtime"], parent_skill="", seed=seed, arms=base.ARMS,
                        limits=ae.effective_limits(base.ARMS, 0))
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split_hash": split["record_hash"], "benchmark": BENCHMARK, "repo": str(safe_path(repo)),
                   "seed": seed, "per_task": per_task, "source_tasks": len(train),
                   "source_task_hashes": sorted(digest(t) for t in train), "source_families": sorted(families),
                   "writer_system": WRITER.format(count=per_task, figures=MAX_FIGURES, decimals=MAX_DECIMALS),
                   "reviewer_system": REVIEWER, "filters": FILTERS,
                   "development_questions_hash": digest(sorted(question_key(t["public"]["question"])
                                                               for t in dev_panel["tasks"])),
                   "information": "public fields (question, parsed pages) of this seed's training tasks only; no "
                                  "reference answer, no validation / test item, no solver outcome; the reference "
                                  "of a generated task is computed from figures quoted from those pages",
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "native_lock": protocol["config"]["native_lock"], "dev_panel": str(safe_path(dev_path)),
                   "manifest_hash": value["record_hash"], "panel_sha256": base._sha(out / "panel.json"),
                   "tool_sha256": tool_sha256()})
    write_json(out / "generation.json", record)
    return record


def run(output, *, fixture_api=None, fixture_gate=None):
    return base.run(output, fixture_api=fixture_api, fixture_gate=fixture_gate, kind=sys.modules[__name__])


def check(output):
    return base.check(output, sys.modules[__name__])


def family_map(output):
    return base.family_map(output, sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(base.main(kind=sys.modules[__name__]))
