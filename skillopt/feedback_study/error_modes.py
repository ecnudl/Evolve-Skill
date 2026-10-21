"""Host-executed, truth-aware diagnosis of a wrong answer on a GENERATED OfficeQA item (2026-10-15; design
docs/handoff/generalization-architecture-20261015.md section 2.4).

A generated item carries its derivation: the figures (each a printed value with a verbatim quote of the pages), a
closed-grammar expression over them, the rounding and the answer the host computed exactly. When the solver's answer
is wrong, the host recomputes simple VARIANTS of that derivation and reports the first one that reproduces the
solver's number -- another rounding or truncation, the value times a power of ten, the opposite sign, two figures
swapped, or one figure replaced by a neighbouring cell of the SAME table row or column as the figure's quoted place
(described by its position and value only: no other line of the page is quoted).
A matching variant reproduces the number; it is not a proof of the solver's reasoning, and the wording says so.
Nothing here calls a model; the derivation is the generator's own computation from public pages of TRAINING tasks,
never a dataset label of a validation or test item. The report is feedback for the analyst on a generated training
item only. Every input is bounded before it is parsed: a hostile answer costs only itself.
"""
from __future__ import annotations

import itertools
import re
from fractions import Fraction

from scripts import generate_officeqa_tasks as v1

MAX_SUBSTITUTES = 40   # candidate neighbour cells per figure
MAX_WALK = 40          # lines walked up and down a column from the quoted row
MAX_ANSWER_CHARS = 40  # an answer tag longer than this is not one plain number
MAX_DIGITS = 30
SCALES = (-6, -3, -2, -1, 1, 2, 3, 6)
_ANSWER = re.compile(r"<answer>(.*?)</answer>", re.S | re.I)
_PLAIN = re.compile(r"^\s*(-?)\s*\$?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?|\.\d+)\s*%?\s*$")
_CELL_NUMBER = re.compile(r"^\s*(-?)\$?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)%?(?:\s+\d{1,2}/)*\s*$")


def final_answer(output):
    """(the solver's final answer as an exact number, the decimals it was written with), or (None, None) when the
    last answer tag does not hold one plain number of bounded size."""
    if type(output) is not str:
        return None, None
    tags = _ANSWER.findall(output[-200_000:])
    if not tags or len(tags[-1]) > MAX_ANSWER_CHARS:
        return None, None
    match = _PLAIN.match(tags[-1])
    if match is None:
        return None, None
    digits = match.group(2)
    if sum(ch.isdigit() for ch in digits) > MAX_DIGITS:
        return None, None
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    return Fraction(match.group(1) + digits.replace(",", "")), decimals


def _round(value, decimals):
    """Half away from zero at ``decimals`` places, exactly (ties are excluded by the generator)."""
    scale = Fraction(10) ** decimals
    scaled = abs(value) * scale
    whole = int(scaled)
    if scaled - whole >= Fraction(1, 2):
        whole += 1
    return Fraction(whole, 1) / scale * (1 if value >= 0 else -1)


def _truncate(value, decimals):
    """Toward zero at ``decimals`` places, exactly."""
    scale = Fraction(10) ** decimals
    return Fraction(int(abs(value) * scale), 1) / scale * (1 if value >= 0 else -1)


def _same(variant, answer, decimals):
    """Does the variant, written with the solver's own number of decimals, give the solver's number?"""
    return variant is not None and _round(variant, decimals) == answer


def _number(cell):
    """A table cell's number, or None; a cell longer than an answer may be is never parsed."""
    if len(cell) > MAX_ANSWER_CHARS + 20:
        return None
    m = _CELL_NUMBER.match(cell)
    if m is None or sum(ch.isdigit() for ch in m.group(2)) > MAX_DIGITS:
        return None
    return Fraction(m.group(1) + m.group(2).replace(",", ""))


def _anchor(pages, figure):
    """(line index, cell index) of the ONE table cell that holds the figure's printed value on a line that contains
    the figure's quote (whitespace collapsed), or None when there is no such cell or more than one."""
    quote = " ".join(figure["quote"].split())
    value = figure["value"].replace("$", "").replace("%", "").strip()
    found = []
    for index, line in enumerate(pages.splitlines()):
        if "|" not in line or quote not in " ".join(line.split()) and " ".join(line.split()) not in quote:
            continue
        for position, cell in enumerate(line.split("|")):
            if len(cell) > MAX_ANSWER_CHARS + 20:
                continue
            m = _CELL_NUMBER.match(cell)
            if m is not None and m.group(1) + m.group(2) == value:
                found.append((index, position))
    return found[0] if len(found) == 1 else None


def _neighbours(pages, figure):
    """Numbers printed in the anchored cell's row and column: [(value, description)], at most MAX_SUBSTITUTES,
    collected while walking (no unbounded scan)."""
    anchor = _anchor(pages, figure)
    if anchor is None:
        return []
    lines = pages.splitlines()
    row_index, position = anchor
    cells = lines[row_index].split("|")
    found, seen = [], set()

    def add(value, where):
        if value is not None and value not in seen and len(found) < MAX_SUBSTITUTES:
            seen.add(value)
            found.append((value, where))

    for other, text in enumerate(cells):
        if len(found) >= MAX_SUBSTITUTES:
            break
        if other != position:
            add(_number(text), "another cell of the same row, %d cell(s) to the %s" % (abs(other - position),
                                                                                    "right" if other > position else "left"))
    for step in (-1, 1):
        j, walked = row_index + step, 0
        while 0 <= j < len(lines) and "|" in lines[j] and walked < MAX_WALK and len(found) < MAX_SUBSTITUTES:
            row = lines[j].split("|")
            if len(row) == len(cells):
                add(_number(row[position]), "the same column, %d table line(s) %s" % (walked + 1, "below" if step > 0 else "above"))
            j += step
            walked += 1
    return found


def _text(value):
    if value.denominator == 1 and abs(value) < 10 ** MAX_DIGITS:
        return str(int(value))
    try:
        return "%.6g" % float(value)
    except OverflowError:
        return "a very large number"


def diagnose(derivation, pages, output):
    """{"mode", "detail", "expected", "answer"} for a solver output on a generated item whose host score is FAIL.
    ``mode`` names the first variant that reproduces the solver's number, or ``unexplained``."""
    values = {f["name"]: v1.figure(f["value"]) for f in derivation["figures"]}
    exact = v1.evaluate(derivation["expression"], values) if None not in values.values() else None
    decimals = derivation["decimals"]
    answer, places = final_answer(output)
    base = {"expected": derivation["answer"], "answer": None if answer is None else _text(answer) if places == 0
            else ("%." + str(places) + "f") % float(answer) if abs(answer) < 10 ** 15 else _text(answer)}
    if exact is None:
        return {**base, "mode": "derivation_unavailable", "detail": "the host could not re-evaluate the derivation"}
    if answer is None:
        return {**base, "mode": "not_one_number", "detail": "the last answer tag does not hold one plain number"}
    if places != decimals and _same(exact, answer, places):
        return {**base, "mode": "rounding",
                "detail": "your number is the expected value written with %d decimal place(s); the question asks for %d"
                          % (places, decimals)}
    if places == decimals and _truncate(exact, decimals) == answer and _round(exact, decimals) != answer:
        return {**base, "mode": "truncation",
                "detail": "your number is the expected value cut (not rounded) at %d decimal place(s)" % decimals}
    if answer != 0:
        for k in SCALES:
            if _same(exact * Fraction(10) ** k, answer, places):
                return {**base, "mode": "power_of_ten",
                        "detail": "your number equals the expected value times 10^%d (a variant that matches a ratio vs "
                                  "percent or a unit/scale difference)" % k}
    if answer != 0 and _same(-exact, answer, places):
        return {**base, "mode": "sign", "detail": "your number equals the expected value with the opposite sign"}
    names = list(values)
    for a, b in itertools.combinations(names, 2):
        swapped = dict(values)
        swapped[a], swapped[b] = values[b], values[a]
        variant = v1.evaluate(derivation["expression"], swapped)
        if variant is not None and variant != exact and _same(variant, answer, places):
            return {**base, "mode": "operand_order",
                    "detail": "your number equals the computation with %s and %s swapped" % (a, b)}
    for f in derivation["figures"]:
        for value, where in _neighbours(pages, f):
            if value == values[f["name"]]:
                continue
            variant = v1.evaluate(derivation["expression"], {**values, f["name"]: value})
            if _same(variant, answer, places):
                return {**base, "mode": "neighbour_cell",
                        "detail": "your number equals the computation with %s = %s taken from %s of the quoted table, "
                                  "instead of %s" % (f["name"], _text(value), where, f["value"])}
    try:
        relative = "; it differs from the expected value by %.2f%%" % float(abs(answer - exact) / abs(exact) * 100) if exact else ""
    except OverflowError:
        relative = ""
    return {**base, "mode": "unexplained",
            "detail": "no simple variant (rounding, truncation, a power of ten, sign, swapped figures, a neighbouring "
                      "cell of the quoted table) reproduces your number" + relative}


def canonical(expression):
    """The expression's arithmetic text exactly as spelled (no float conversion): anything from a comment sign on is
    dropped and whitespace collapsed; when the dropped part would change the text the parser evaluates -- or the text is
    not plain arithmetic -- a placeholder is shown instead."""
    text = " ".join(expression.split("#", 1)[0].split())[:400]
    plain = re.fullmatch(r"[a-z0-9_+\-*/()., ]+", text) is not None
    return text if plain and text else "(the derivation's expression)"


def render(derivation, diagnosis, limit):
    """The analyst-facing note, most essential first (the expected answer, the solver's number, the matching variant,
    the expression), the figure quotes last; bounded to ``limit`` characters."""
    head = ("Verifier (host-executed derivation check on a GENERATED training item whose answer the host computed "
            "exactly from quoted table cells): expected %s; your answer %s. Diagnosis (%s): %s. Derivation: %s, rounded "
            "to %d decimal place(s), with " % (diagnosis["expected"],
                                               diagnosis["answer"] if diagnosis["answer"] is not None else "no single number",
                                               diagnosis["mode"], diagnosis["detail"], canonical(derivation["expression"]),
                                               derivation["decimals"]))
    figures = "; ".join('%s = %s ("%s")' % (f["name"], f["value"], " ".join(f["quote"].split())[:110])
                        for f in derivation["figures"])
    text = head + figures + "."
    return text if len(text) <= limit else text[:limit] + " …[truncated]"
