"""Forward panels of a similar candidate (registration §8, version 6).

A rule proposed for the similar placement is checked on each forward target of its stage -- a similar bench not yet
learned that has a generated style (§1.1): OfficeQA style, a question on a real data table taken verbatim from a
Wikipedia page and answered by an exact calculation; LiveMath style, a five-option question on a real Wikipedia
definition or theorem whose correct option a formula computes. The research step supplies the material (§7: one
material request per round, made by the caller, ``material``). Per round, one generation call asks for three items;
each item that passes the program's checks gets exactly one independent consistency-check call -- at most 5 rounds,
so at most 5 generation and 15 check calls per (rule, target), besides the material requests.

Validity is decided by exact rational arithmetic (``evaluate``), never by a model alone: an OfficeQA-style formula uses
only numbers copied from cells of the table, and its value, rounded as the question states, is the reference answer;
a LiveMath-style formula's value is exactly one of five distinct options, the answer's. An item's identity is the hash
of the normalised material and question (``identity``); within a panel an item whose identity repeats a kept item's is
dropped as a duplicate (counted, no check call), and the first 12 distinct valid items are kept, in order. Item ids are
namespaced by rule and target, so the same question in two panels is two items. A panel of fewer than 8 items is
"short": the rule is tested at its own placement only (§4 step 8). Forward items are selection material for the
placement, never evidence of transfer (§12.8).
"""
from __future__ import annotations

import ast
import hashlib
import math
import re
import unicodedata
from collections import Counter
from fractions import Fraction

from skillopt.continual_eval.core import require

from .protocol import FORWARD_ATTEMPTS, FORWARD_PANEL, FORWARD_PER_CALL, FORWARD_STYLES
from .roles import Invalid, fields, items, text

MAX_FORMULA_CHARS = 300
MAX_FORMULA_NODES = 100
MAX_EXPONENT = 10
MAX_FACTORIAL = 100
MAX_COMBINATORIAL = 1000  # comb / perm: n at most this
MAX_BITS = 4096  # every intermediate value's numerator and denominator
MAX_DECIMALS = 4
MAX_QUESTION_CHARS = 600
MAX_ANSWER_CHARS = 40
OPTIONS = "ABCDE"

LITERAL = re.compile(r"\d+(?:\.\d+)?")  # decimal digits, one optional fraction part: no exponent, sign or separator
PLAIN_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")
OPTION_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\d+/\d+)")
SIGNS = ("-", "+", "−")  # a cell's sign: the formula writes it as an operator
FUNCTIONS = ("abs", "min", "max", "floor", "ceil", "factorial", "comb", "perm", "gcd", "lcm")
OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
# why a generated item is not in the panel (``build_panel`` counts); duplicates are counted apart
DROPS = ("format", "formula", "literal_not_in_table", "answer_mismatch", "options", "check_invalid",
         "check_literal_not_in_table", "check_mismatch", "check_rejected", "panel_full")

FORMULA_RULES = ("operators + - * / ** and parentheses; functions abs, min, max, floor, ceil, factorial, comb, perm, "
                 "gcd, lcm; numbers written with digits and at most one decimal point (no thousands separators, "
                 "currency signs, percent signs, exponents or variables)")
GENERATE_SYSTEM = {
    "officeqa": (
        "You write practice questions about a real data table. You receive a guidance rule (\"topic\"), the source of "
        "the table and the table itself (\"material\"), copied verbatim from a Wikipedia page. Write as many distinct "
        "questions as \"count\" asks. Every question must be answerable from this table alone, by reading the right "
        "cells and computing with them, and must exercise the situation the guidance rule addresses. Do not mention "
        "any benchmark, dataset or test, and do not refer to the rule.\n\n"
        "For each question give:\n"
        "- \"question\": at most 600 characters; do not say how to round (the rounding instruction is added from "
        "\"decimals\");\n"
        "- \"formula\": one arithmetic expression that computes the exact answer, in which every number is copied "
        "exactly from a cell of the table (a cell's minus sign is written as an operator; no other constant, such as "
        "100 for a percentage); " + FORMULA_RULES + ";\n"
        "- \"decimals\": an integer from 0 to 4, the number of decimal places the answer is rounded to;\n"
        "- \"answer\": the formula's value rounded half away from zero to exactly that many decimal places, written "
        "with digits only, a decimal point when \"decimals\" is not 0, and a leading minus sign when negative.\n\n"
        "Reply with one JSON object {\"items\": [...]} and nothing else."),
    "livemath": (
        "You write multiple-choice mathematics questions about a real definition or theorem. You receive a guidance "
        "rule (\"topic\"), the source of the passage and the passage itself (\"material\"), quoted verbatim from a "
        "Wikipedia page. Write as many distinct questions as \"count\" asks. Every question must be about this "
        "passage and must exercise the situation the guidance rule addresses. The solver sees only the question and "
        "the five options, never the passage: state in the question every definition and value it needs. Do not "
        "mention any benchmark, dataset or test, and do not refer to the rule.\n\n"
        "For each question give:\n"
        "- \"question\": at most 600 characters;\n"
        "- \"options\": five distinct exact numbers (integers, decimals or fractions p/q, optionally signed), exactly "
        "one of them correct;\n"
        "- \"answer\": the letter, A to E, of the correct option in the order given;\n"
        "- \"formula\": one arithmetic expression whose value is exactly the correct option; " + FORMULA_RULES + ".\n\n"
        "Reply with one JSON object {\"items\": [...]} and nothing else."),
}
CHECK_SYSTEM = {
    "officeqa": (
        "You receive a data table and a question about it. Write one arithmetic expression that computes the exact, "
        "unrounded answer to the question from the table: every number copied exactly from a cell of the table (a "
        "cell's minus sign written as an operator); " + FORMULA_RULES + ". Reply with one JSON object "
        "{\"formula\": \"...\"} and nothing else."),
    "livemath": (
        "You receive a passage quoted from Wikipedia, a multiple-choice question and an arithmetic expression. Decide "
        "whether the expression computes exactly the quantity the question asks for, given the passage. Reply with "
        "one JSON object {\"verdict\": \"yes\"} or {\"verdict\": \"no\"} and nothing else."),
}


# --------------------------------------------------------------------------------------------- exact arithmetic
def _tree(formula):
    if type(formula) is not str or not formula.strip() or len(formula) > MAX_FORMULA_CHARS:
        raise Invalid("formula_text")
    source = formula.strip()
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        raise Invalid("formula_syntax") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_FORMULA_NODES:
        raise Invalid("formula_size")
    return source, tree


def _literal(source, node):
    """A number literal exactly as written (never through a float)."""
    written = ast.get_source_segment(source, node)
    if type(node.value) not in (int, float) or written is None or LITERAL.fullmatch(written) is None:
        raise Invalid("formula_literal")
    return written


def _bounded(value):
    if value.numerator.bit_length() > MAX_BITS or value.denominator.bit_length() > MAX_BITS:
        raise Invalid("formula_magnitude")
    return value


def _integer(value):
    if value.denominator != 1:
        raise Invalid("formula_integer_argument")
    return value.numerator


def _binary(op, left, right):
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        if right == 0:
            raise Invalid("formula_division_by_zero")
        return left / right
    exponent = _integer(right)
    if abs(exponent) > MAX_EXPONENT or (exponent < 0 and left == 0):
        raise Invalid("formula_exponent")
    if max(left.numerator.bit_length(), left.denominator.bit_length()) * abs(exponent) > MAX_BITS:
        raise Invalid("formula_magnitude")
    return left ** exponent


def _call(name, args):
    if name == "abs" and len(args) == 1:
        return abs(args[0])
    if name in ("min", "max") and len(args) >= 2:
        return min(args) if name == "min" else max(args)
    if name in ("floor", "ceil") and len(args) == 1:
        return Fraction(math.floor(args[0]) if name == "floor" else math.ceil(args[0]))
    if name == "factorial" and len(args) == 1:
        n = _integer(args[0])
        if not 0 <= n <= MAX_FACTORIAL:
            raise Invalid("formula_argument_range")
        return Fraction(math.factorial(n))
    if name in ("comb", "perm") and len(args) == 2:
        n, k = _integer(args[0]), _integer(args[1])
        if not (0 <= n <= MAX_COMBINATORIAL and 0 <= k):
            raise Invalid("formula_argument_range")
        return Fraction(math.comb(n, k) if name == "comb" else math.perm(n, k))
    if name in ("gcd", "lcm") and len(args) >= 2:
        ints = [_integer(a) for a in args]
        return Fraction(math.gcd(*ints) if name == "gcd" else math.lcm(*ints))
    raise Invalid("formula_arguments")


def _value(source, node):
    if isinstance(node, ast.Expression):
        return _value(source, node.body)
    if isinstance(node, ast.Constant):
        return Fraction(_literal(source, node))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _value(source, node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, OPERATORS):
        return _bounded(_binary(node.op, _value(source, node.left), _value(source, node.right)))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS
            and not node.keywords):
        return _bounded(_call(node.func.id, [_value(source, a) for a in node.args]))
    raise Invalid("formula_element")


def evaluate(formula):
    """The exact value (``Fraction``) of an arithmetic formula: number literals as written (decimal digits with at most
    one decimal point), unary + and -, + - * /, ** with an integer exponent of at most 10 in size (negative only for
    a nonzero base), parentheses and the functions abs, min and max (two or more arguments), floor, ceil, factorial
    (n <= 100), comb and perm (n <= 1000), gcd and lcm (integer arguments). Anything else, a division by zero, more
    than 300 characters, 100 syntax nodes or 4096-bit values: ``roles.Invalid``."""
    source, tree = _tree(formula)
    return _value(source, tree)


def literals(formula):
    """The formula's number literals as written, in order of appearance."""
    source, tree = _tree(formula)
    found = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Constant)), key=lambda n: (n.lineno, n.col_offset))
    return [_literal(source, node) for node in found]


def rounded(value, decimals):
    """``value`` rounded half away from zero to exactly ``decimals`` (0-4) digits after the point, no separators."""
    require(type(decimals) is int and 0 <= decimals <= MAX_DECIMALS, "Rounding to 0-4 decimal places")
    value = Fraction(value)
    whole = math.floor(abs(value) * 10 ** decimals + Fraction(1, 2))
    digits = str(whole).rjust(decimals + 1, "0")
    body = digits[:-decimals] + "." + digits[-decimals:] if decimals else digits
    return ("-" if value < 0 and whole else "") + body


def _normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def identity(material_text, question):
    """An item's identity (§8): the hash of the normalised (NFKC, lower case, collapsed whitespace) material and
    question."""
    require(type(material_text) is str and type(question) is str, "Identity of text")
    return hashlib.sha256((_normalize(material_text) + "\x00" + _normalize(question)).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------------- items
def _cell(value):
    """A table cell as a formula may write it: stripped, without "," separators, one leading "$", one trailing "%"
    and one leading sign (written as an operator)."""
    cleaned = value.strip().replace(",", "")
    cleaned = cleaned[1:] if cleaned.startswith("$") else cleaned
    cleaned = cleaned[:-1] if cleaned.endswith("%") else cleaned
    cleaned = cleaned.strip()
    return cleaned[1:].strip() if cleaned[:1] in SIGNS else cleaned


def _rounding(decimals):
    if decimals == 0:
        return "Round your answer to the nearest whole number."
    return "Round your answer to %d decimal place%s." % (decimals, "" if decimals == 1 else "s")


def _source_line(material):
    return "Source: Wikipedia, %s (revision %d)" % (material["source"]["title"], material["source"]["revid"])


def _material(material, style):
    """The material of one round, as the research step supplies it (§7); a malformed one is a fault of the run."""
    needed = {"style", "source", "page", "text"} | ({"table"} if style == "officeqa" else {"quote"})
    require(isinstance(material, dict) and needed <= set(material) and material["style"] == style,
            "Forward material of the target's style")
    source = material["source"]
    require(isinstance(source, dict) and type(source.get("title")) is str and source["title"].strip()
            and type(source.get("revid")) is int, "Forward material names its Wikipedia page and revision")
    require(type(material["text"]) is str and material["text"].strip(), "Forward material has text")
    if style == "officeqa":
        table = material["table"]
        require(isinstance(table, dict) and type(table.get("rows")) is list and table["rows"]
                and all(type(row) is list and all(type(c) is str for c in row) for row in table["rows"]),
                "An OfficeQA-style material holds a table of text cells")
    else:
        require(type(material["quote"]) is str and material["quote"].strip(), "A LiveMath-style material quotes")
    return material


def _cells(material):
    return {_cell(c) for row in material["table"]["rows"] for c in row}


def _office(raw, material):
    """(drop reason or None, prepared item) of a generated OfficeQA-style item, before its check call."""
    try:
        fields(raw, ["question", "answer", "formula", "decimals"])
        question = text(raw["question"], limit=MAX_QUESTION_CHARS).strip()
        answer = text(raw["answer"], limit=MAX_ANSWER_CHARS).strip()
        text(raw["formula"], limit=MAX_FORMULA_CHARS)
        decimals = raw["decimals"]
        if type(decimals) is not int or not 0 <= decimals <= MAX_DECIMALS:
            raise Invalid("decimals")
    except Invalid:
        return "format", None
    try:
        value, written = evaluate(raw["formula"]), literals(raw["formula"])
    except Invalid:
        return "formula", None
    if not set(written) <= _cells(material):
        return "literal_not_in_table", None
    reference = rounded(value, decimals)
    if PLAIN_NUMBER.fullmatch(answer) is None or Fraction(answer) != Fraction(reference):
        return "answer_mismatch", None
    public = {"question": question + " " + _rounding(decimals),
              "context": _source_line(material) + "\n" + material["text"]}
    return None, {"public": public, "private": {"answer": reference}, "formula": raw["formula"],
                  "decimals": decimals}


def _options(values):
    """The five options' exact values, or None unless they are five distinct exact numbers."""
    if type(values) is not list or len(values) != len(OPTIONS):
        return None
    exact = []
    for value in values:
        if type(value) is not str or len(value) > MAX_ANSWER_CHARS or OPTION_NUMBER.fullmatch(value.strip()) is None:
            return None
        written = value.strip()
        if "/" in written and int(written.split("/")[1]) == 0:
            return None
        exact.append(Fraction(written))
    return exact if len(set(exact)) == len(exact) else None


def _live(raw, material):
    """(drop reason or None, prepared item) of a generated LiveMath-style item, before its check call."""
    try:
        fields(raw, ["question", "options", "answer", "formula"])
        question = text(raw["question"], limit=MAX_QUESTION_CHARS).strip()
        text(raw["formula"], limit=MAX_FORMULA_CHARS)
        if type(raw["answer"]) is not str or len(raw["answer"]) != 1 or raw["answer"] not in OPTIONS:
            raise Invalid("answer")
    except Invalid:
        return "format", None
    exact = _options(raw["options"])
    if exact is None:
        return "options", None
    try:
        value = evaluate(raw["formula"])
    except Invalid:
        return "formula", None
    matches = [OPTIONS[i] for i, option in enumerate(exact) if option == value]
    if matches != [raw["answer"]]:
        return "answer_mismatch", None
    choices = "\n\n".join("%s. %s" % (OPTIONS[i], o.strip()) for i, o in enumerate(raw["options"]))
    return None, {"public": {"question": question, "choices": choices}, "private": {"answer": raw["answer"]},
                  "formula": raw["formula"]}


def _generated(value):
    fields(value, ["items"])
    return items(value["items"], limit=FORWARD_PER_CALL)


def _checked_formula(value):
    fields(value, ["formula"])
    formula = text(value["formula"], limit=MAX_FORMULA_CHARS)
    return evaluate(formula), literals(formula)


def _checked_verdict(value):
    fields(value, ["verdict"])
    if value["verdict"] not in ("yes", "no"):
        raise Invalid("verdict")
    return value["verdict"]


def _check(roles, target, material, prepared, *, label):
    """The independent consistency check of one item (§8): None when it holds, else the drop reason."""
    if target == "officeqa":
        payload = {"table": material["text"], "question": prepared["public"]["question"]}
        checked = roles.ask("forward_check", CHECK_SYSTEM[target], payload, label=label, check=_checked_formula)
        if checked is None:
            return "check_invalid"
        value, written = checked
        if not set(written) <= _cells(material):  # the independent formula too takes every number from a cell
            return "check_literal_not_in_table"
        same = rounded(value, prepared["decimals"]) == prepared["private"]["answer"]
        return None if same else "check_mismatch"
    payload = {"passage": material["quote"], "question": prepared["public"]["question"],
               "formula": prepared["formula"]}
    verdict = roles.ask("forward_check", CHECK_SYSTEM[target], payload, label=label, check=_checked_verdict)
    if verdict is None:
        return "check_invalid"
    return None if verdict == "yes" else "check_rejected"


# ------------------------------------------------------------------------------------------------------ panels
def build_panel(roles, *, rule_id, rule_text, target, material, label):
    """The forward panel of one (rule, forward target) (§8). ``roles``: the attempt's ``roles.Roles``;
    ``material(round)``: the research step's material request of that round (§7) -- a material record of the target's
    style, or None when it found none (the round then yields nothing). Stops of the run raised by a call propagate.

    Returns {"status": "ok" (8-12 items) | "short", "items": [{"id", "benchmark", "public", "private", "identity",
    "source", "formula", "round"}], "counts": {"rounds", "generated", "valid", "duplicates", "dropped": {reason: n}},
    "rounds": [per-round record]}; ``generated`` = ``valid`` + ``duplicates`` + every dropped item."""
    require(target in FORWARD_STYLES, "A forward target has a generated style")
    require(type(rule_id) is str and rule_id and type(rule_text) is str and rule_text.strip(), "A rule's panel")
    require(callable(material) and type(label) is str and label, "A panel needs its material request and label")
    prepare = _office if target == "officeqa" else _live
    kept, rounds, dropped, seen = [], [], Counter(), set()
    counts = {"rounds": 0, "generated": 0, "valid": 0, "duplicates": 0}
    for number in range(1, FORWARD_ATTEMPTS + 1):
        if len(kept) >= FORWARD_PANEL[1]:
            break
        counts["rounds"] += 1
        found = material(number)
        record = {"round": number, "source": None, "reply": "no_material", "items": []}
        rounds.append(record)
        if found is None:
            continue
        found = _material(found, target)
        record["source"] = dict(found["source"])
        payload = {"topic": rule_text, "source": found["source"], "material": found["text"],
                   "count": FORWARD_PER_CALL}
        raws = roles.ask("forward_generate", GENERATE_SYSTEM[target], payload,
                         label="%s/r%d/generate" % (label, number), check=_generated)
        record["reply"] = "invalid" if raws is None else "ok"
        for position, raw in enumerate(raws or [], start=1):
            counts["generated"] += 1
            row = {"position": position}
            record["items"].append(row)
            if len(kept) >= FORWARD_PANEL[1]:
                row["outcome"] = "panel_full"
                dropped["panel_full"] += 1
                continue
            reason, prepared = prepare(raw, found)
            if reason is None:
                row["identity"] = key = identity(found["text"], prepared["public"]["question"])
                if key in seen:  # the first occurrence decides, checked or not, kept or not
                    row["outcome"] = "duplicate"
                    counts["duplicates"] += 1
                    continue
                seen.add(key)
                reason = _check(roles, target, found, prepared, label="%s/r%d/check%d" % (label, number, position))
            if reason is not None:
                row["outcome"] = reason
                dropped[reason] += 1
                continue
            item_id = "fwd:%s:%s:%d" % (rule_id, target, len(kept) + 1)
            kept.append({"id": item_id, "benchmark": target, "public": prepared["public"],
                         "private": prepared["private"], "identity": key, "source": dict(found["source"]),
                         "formula": prepared["formula"], "round": number})
            row.update(outcome="kept", id=item_id)
    counts["valid"] = len(kept)
    counts["dropped"] = dict(sorted(dropped.items()))
    return {"status": "ok" if len(kept) >= FORWARD_PANEL[0] else "short", "items": kept, "counts": counts,
            "rounds": rounds}
