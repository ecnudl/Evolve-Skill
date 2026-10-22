"""OfficeQA transformation families (protocol ``fivebench-execskill-v1``; registration §7.2 "OfficeQA 族", Codex F8,
§21 owner rule (b); implementation plan §1 generators row; T-GEN-1, T-GEN-6).

The table comes from research: one qualified ``family_material`` finding, an eligible English Wikipedia numeric table
(research.py ``eligible``). The examiner's generator only picks the template's cells, the rounding and an optional
perturbation of at most two of the chosen cells (``percent``: -20..20, never 0); fixed code does the rest:

1. reproduce the original reference first: the template's reference function on the UNPERTURBED cells must evaluate
   exactly (``compute.exact``), else the set is dropped (``reference_fn_failed``);
2. apply the perturbation: a chosen cell's value times (1 + percent/100), rounded half away from zero to the cell's
   own decimals and written back into the table in the cell's style (a perturbation that changes nothing is
   ``perturbation_noop``);
3. recompute the answer exactly from the (perturbed) cells and round it as the question states (``compute.rounded``);
4. every perturbed literal must appear verbatim in the rendered context (``literal_not_in_context``) and the answer's
   value may not appear among the numbers of the question or the context (``answer_in_context``; D6 wrote 2 of 7
   answers into the question, [FP F30]).

Templates (the fixed reference functions): ``difference`` b - a, ``ratio`` b / a, ``percent_change``
100 (b - a) / a, ``sum`` of 2-6 named cells. A cell is [row, column] of the table's data rows (row 0 is the header,
column 0 the row label), named in the question by its row label and column header, which must be unambiguous.
"""
from __future__ import annotations

import math
import re
from fractions import Fraction

from .. import compute
from ..research import NUMBER, numeric
from .families import Drop, Family, Param, check

CHECKED_BY = "execskill.generators.officeqa"
TEMPLATES = ("difference", "ratio", "percent_change", "sum")
PERTURB_PERCENT = (-20, 20)
MAX_PERTURBED = 2
CURRENCY = "$€£¥"
QUESTIONS = {
    "difference": "Using the table, what is the value in {b} minus the value in {a}?",
    "ratio": "Using the table, what is the ratio of the value in {b} to the value in {a}?",
    "percent_change": "Using the table, what is the percent change from the value in {a} to the value in {b}?",
    "sum": "Using the table, what is the sum of the values in {cells}?",
}
ROUNDING = {0: " Give the answer rounded to a whole number.",
            **{d: " Give the answer rounded to %d decimal place%s." % (d, "" if d == 1 else "s") for d in (1, 2, 3, 4)}}


def _family(template):
    cells = Param("cells", count=(2, 6) if template == "sum" else (2, 2))
    return Family(name="officeqa." + template, bench="officeqa", material="table", reference=template,
                  params={"cells": cells, "decimals": Param("int", 0, 4),
                          "perturb": Param("edits", *PERTURB_PERCENT, count=(0, MAX_PERTURBED), optional=True)})


FAMILIES = {"officeqa." + template: _family(template) for template in TEMPLATES}


def reference(template, values):
    """The fixed reference function of a template over the cells' exact values (in the chosen order)."""
    if template == "sum":
        return sum(values, Fraction(0))
    a, b = values
    if template == "difference":
        return b - a
    if a == 0:
        raise Drop("reference_fn_failed", "division by zero")
    return b / a if template == "ratio" else 100 * (b - a) / a


def cell_value(text):
    """The exact number a numeric table cell holds (thousands separators, a currency sign, a trailing % and a U+2212
    minus allowed); Drop("reference_fn_failed") for any other cell."""
    if not numeric(text):
        raise Drop("reference_fn_failed", "a chosen cell is not a number: %r" % text[:40])
    return Fraction(text.strip().lstrip(CURRENCY).rstrip("%").strip().replace(",", "").replace("−", "-"))


def _written(value, like):
    """``value`` written in the style of the cell text ``like``: its decimals, separators, sign and affixes."""
    core = like.strip().lstrip(CURRENCY).rstrip("%").strip()
    decimals = len(core.split(".")[1]) if "." in core else 0
    scaled = abs(value) * 10 ** decimals
    whole = math.floor(scaled + Fraction(1, 2))
    digits = str(whole).rjust(decimals + 1, "0")
    body = digits[:-decimals] + "." + digits[-decimals:] if decimals else digits
    if "," in core:
        head, _, tail = body.partition(".")
        body = "{:,}".format(int(head)) + ("." + tail if tail else "")
    sign = ("−" if "−" in core else "-") if value < 0 and whole else ""
    prefix = like.strip()[:len(like.strip()) - len(like.strip().lstrip(CURRENCY))]
    return prefix + sign + body + ("%" if like.strip().endswith("%") else "")


def _labels(rows, cell):
    row, column = cell
    if not (1 <= row < len(rows) and 1 <= column < len(rows[row]) and column < len(rows[0])):
        raise Drop("format", "cell %s outside the data cells" % (list(cell),))
    return rows[row][0].strip(), rows[0][column].strip()


def _name(rows, cell):
    row_label, column_label = _labels(rows, cell)
    if not row_label or not column_label:
        raise Drop("format", "a chosen cell has no row label or column header")
    if [r[0].strip() for r in rows[1:]].count(row_label) != 1 or [c.strip() for c in rows[0]].count(column_label) != 1:
        raise Drop("format", "a chosen cell's label is ambiguous")
    return 'row "%s", column "%s"' % (row_label, column_label)


def _perturbations(entries, cells):
    found = {}
    for entry in entries:
        if (type(entry) is not dict or set(entry) != {"cell", "percent"} or type(entry["percent"]) is not int
                or not PERTURB_PERCENT[0] <= entry["percent"] <= PERTURB_PERCENT[1] or entry["percent"] == 0):
            raise Drop("format", "a perturbation is {cell, percent} with percent in -20..20, not 0")
        cell = tuple(entry["cell"]) if type(entry["cell"]) is list else None
        if cell not in cells or cell in found:
            raise Drop("format", "a perturbed cell is one of the chosen cells, once")
        found[cell] = entry["percent"]
    return found


def context_text(material, rows):
    """The item's context: the table's caption, its source and the rows joined by " | " (research.render_table)."""
    source = material["source"]
    head = ["Table: " + material["caption"]] if material["caption"] else []
    head.append('Source: English Wikipedia, "%s" (revision %s)' % (source["title"], source["revid"]))
    return "\n".join(head + [" | ".join(row) for row in rows])


def _numbers(text):
    return {Fraction(m.group().replace(",", "").replace("−", "-").lstrip("+")) for m in NUMBER.finditer(text)}


def apply(family, params, material):
    """One OfficeQA item from one parameter set: {"public": {question, context}, "answer", "truth"}; Drop on any
    failure (module docstring)."""
    if material.get("kind") != "table":
        raise Drop("material_mismatch", "an OfficeQA family consumes a researched table")
    params = check(family, params)
    template, cells, decimals = family.reference, params["cells"], params["decimals"]
    if len(set(cells)) != len(cells):
        raise Drop("format", "the chosen cells are distinct")
    rows = [list(row) for row in material["rows"]]
    names = [_name(rows, cell) for cell in cells]
    original = reference(template, [cell_value(rows[r][c]) for r, c in cells])  # 1. the original reference
    perturbed = _perturbations(params.get("perturb", ()), cells)
    literals = []
    for (r, c), percent in sorted(perturbed.items()):  # 2. the perturbation, written into the table
        new = _written(cell_value(rows[r][c]) * (100 + percent) / 100, rows[r][c])
        if cell_value(new) == cell_value(rows[r][c]):
            raise Drop("perturbation_noop", "cell %s" % [r, c])
        rows[r][c] = new
        literals.append(new)
    exact = reference(template, [cell_value(rows[r][c]) for r, c in cells])  # 3. recomputed exactly
    answer = compute.rounded(exact, decimals)
    if template == "sum":
        question = QUESTIONS["sum"].format(cells=", ".join(names[:-1]) + " and " + names[-1])
    else:
        question = QUESTIONS[template].format(a=names[0], b=names[1])
    question += ROUNDING[decimals]
    context = context_text(material, rows)
    if not all(re.search(r"(?<![\w.,])%s(?![\w])" % re.escape(literal), context) for literal in literals):
        raise Drop("literal_not_in_context")  # 4. the checks
    if Fraction(answer) in _numbers(question) | _numbers(context):
        raise Drop("answer_in_context")
    truth = {"kind": "family_reference", "family": family.name, "checked_by": CHECKED_BY, "template": template,
             "cells": [list(cell) for cell in cells], "original": compute.render(original),
             "perturbed": {"%d,%d" % cell: percent for cell, percent in sorted(perturbed.items())},
             "exact": compute.render(exact), "decimals": decimals}
    return {"public": {"question": question, "context": context}, "answer": answer, "truth": truth}
