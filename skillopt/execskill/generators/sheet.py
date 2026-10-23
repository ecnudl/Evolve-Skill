"""SpreadsheetBench transformation family (protocol ``fivebench-execskill-v1``; registration §7.2 "SpreadsheetBench
族", Codex F8, §21 owner rule (b); implementation plan §1 generators row; T-GEN-3, T-GEN-6).

``spreadsheetbench.formula_edit``: formula-defined cell edits of a source item. The examiner's generator gives 1-5
edits ``{"cell", "formula"[, "sheet"]}``; every edit formula calls at least one function and every function it calls
has a qualified research finding -- a verbatim quote of the pinned LibreOffice Calc help archive
(``research.Researcher.family_material`` on SpreadsheetBench; ``function_set``) -- else ``function_not_researched``;
the frozen recalculation's forbidden functions (continual_eval/sheet_recalc.py ``FORBIDDEN_FUNCTIONS``: volatile,
link and indirect functions) are refused (``forbidden_function``).

Fixed code, in order:
1. every answer cell of the source's reference workbook must hold a formula: a literal answer cannot follow an edit
   without a reference transformation, so such items are refused (``literal_answer``; [SF R5]);
2. every edit target is a numeric literal cell inside the worksheet (A1:XFD1048576), equal in the input and the
   reference workbook, outside the answer range, not referenced by its own formula (``edit_target_invalid``); a
   formula holding a character a worksheet cannot store is ``format`` (both checked before any file is written; v2.1,
   Codex review 2026-10-24 #2);
3. semantic truth: the edit formulas are written into a copy of the reference workbook, which the recalculation engine
   recalculates (``Engine.recalc``: in a run ``engines.Recalculation``, the frozen ``sheet_recalc_v7.Recalculator.run``
   of the qualified engine; a fake in tests); the recalculated values of the edited cells become the new literals of
   the generated input and reference workbooks, and the recalculated answer cells are the expected values
   (``truth.expected_cells``, the engine's values); an unavailable recalculation or a non-numeric edited value is
   ``recalc_failed``, an edit that changes nothing ``perturbation_noop``;
4. the generated workbooks (ticket PR-C61-2; registrar decisions 2026-10-22, addendum 14:1x; [SF F24]): the family
   edits BOTH source workbooks (step 2 makes every target the same numeric literal of the input and the reference, and
   step 3 changes at least one), so neither keeps its source bytes: each is saved with the new literals and then
   recalculated by the same engine, and the generated input and reference are the two receipts' output bytes. The
   reference thus carries the qualified engine's formula caches, which the frozen v7 scorer's drift guard compares with
   its own recalculation (continual_eval/sheet_recalc.py:610-612; openpyxl's save drops every cache, and a formula
   without one is "formula cache not established", spreadsheet_compat.py:246-260); the input carries the caches its
   formulas have after the edit. The private fields bind both written files (``asset_sha256``: {absolute path: sha256
   of the bytes on disk}, the pool items' shape, fixtures.py:360-361), hashed after they are written and before step
   5: the frozen scorer re-checks every reference against it before it scores
   (continual_eval/sheet_numeric_adapter.py:93-94), and without it every scoring pauses the unit as "configuration"
   (``native_scoring_input_error:ValueError``, coevo5/qualify.py:63-64). An unavailable recalculation is
   ``recalc_failed``;
5. THEN, separately, the engine qualification: the generated reference judged against itself twice by the frozen v7
   scorer (``Engine.qualify``, the signature of ``coevo5.qualify.qualify``; a run passes ``execskill.qualify.qualify``,
   which stamps this protocol's version -- Codex F15, ticket A11-1); an item it does not qualify is dropped
   (``engine_qualification_failed``). Zero model calls throughout.

Every receipt (steps 3-4) must be bound to the workbook sent and to its own output bytes (``input_sha256``,
``output_sha256``; the frozen ``evaluate_pair`` binding, continual_eval/sheet_recalc.py:595-602), else ValueError; a
run's ``engines.Recalculation`` has already stopped on an unconfirmed cleanup or a scorer-environment failure and
refused a receipt not bound to the qualified engine and to zero model calls. Each recalculation is one container run
under one ``spreadsheet-native`` slot (engines.py), three for a parameter set that reaches step 4.
"""
from __future__ import annotations

import base64
import hashlib
import re
import shutil
from dataclasses import dataclass
from typing import Callable

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils.cell import column_index_from_string, range_boundaries

from skillopt.continual_eval import spreadsheet_compat
from skillopt.continual_eval.core import require, safe_path
from skillopt.continual_eval.sheet_recalc import FORBIDDEN_FUNCTIONS
from skillopt.validator_pilot.api import digest

from .families import Drop, Family, Param, check

CHECKED_BY = "execskill.generators.sheet"
MAX_EDITS = 5
MAX_FORMULA_CHARS = 200
FUNCTION_CALL = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*)\s*\(")
CELL_REFERENCE = re.compile(r"(?<![A-Za-z0-9_])\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})(?![A-Za-z0-9_(])")
COORDINATE = re.compile(r"[A-Z]{1,3}[1-9][0-9]{0,6}")
MAX_ROW, MAX_COLUMN = 1048576, 16384  # the worksheet's bounds (openpyxl raises ValueError past the last row)
FAMILY = Family("spreadsheetbench.formula_edit", "spreadsheetbench", "function", reference="recalc_formula",
                params={"edits": Param("edits", count=(1, MAX_EDITS))})
FAMILIES = {FAMILY.name: FAMILY}


@dataclass(frozen=True)
class Engine:
    """The zero-call engines of the family: ``recalc(path) -> receipt`` (frozen v7 recalculation receipt shape:
    ``status``, ``input_sha256``, ``output_base64``, ``output_sha256``; in a run ``engines.Recalculation``),
    ``qualify(tasks, root, runtime, *, side, native, workers) -> record`` with ``qualified`` task ids, the frozen
    SpreadsheetBench runtime and the native slot pool (``hold()``)."""
    recalc: Callable
    qualify: Callable
    runtime: dict
    native: object


def functions(formula):
    """The function names a formula calls, upper case."""
    return {name.upper() for name in FUNCTION_CALL.findall(formula)}


def function_set(materials):
    """The family's material from qualified function findings (``research.material`` of kind ``function``): one per
    function name, the first finding of a name kept; ``id`` is the digest of the set."""
    found = {}
    for material in materials:
        require(material.get("kind") == "function", "A function set holds function findings")
        found.setdefault(material["name"].upper(), material)
    require(found, "A function set holds at least one finding")
    return {"kind": "functions", "functions": found, "id": digest(sorted(m["id"] for m in found.values()))}


def _edits(entries, researched):
    out = []
    for entry in entries:
        if (type(entry) is not dict or not {"cell", "formula"} <= set(entry) <= {"cell", "formula", "sheet"}
                or type(entry["cell"]) is not str or COORDINATE.fullmatch(entry["cell"]) is None
                or type(entry["formula"]) is not str or not entry["formula"].startswith("=")
                or len(entry["formula"]) > MAX_FORMULA_CHARS
                or ("sheet" in entry and type(entry["sheet"]) is not str)):
            raise Drop("format", "an edit is {cell, formula[, sheet]} with a formula of at most 200 characters")
        if ILLEGAL_CHARACTERS_RE.search(entry["formula"]):  # v2.1 (Codex review 2026-10-24 #2): openpyxl refuses it
            raise Drop("format", "a formula holds a character a worksheet cannot store")
        letters = entry["cell"].rstrip("0123456789")
        if column_index_from_string(letters) > MAX_COLUMN or int(entry["cell"][len(letters):]) > MAX_ROW:
            raise Drop("edit_target_invalid", "%s is outside the worksheet" % entry["cell"])
        if FORBIDDEN_FUNCTIONS.search(entry["formula"]):
            raise Drop("forbidden_function", entry["formula"][:60])
        called = functions(entry["formula"])
        if not called or not called <= set(researched):
            raise Drop("function_not_researched", ", ".join(sorted(called - set(researched))) or "no function")
        referenced = {(c.upper() + r) for c, r in CELL_REFERENCE.findall(entry["formula"])}
        if entry["cell"] in referenced:
            raise Drop("edit_target_invalid", "%s refers to itself" % entry["cell"])
        out.append(entry)
    if len({(e.get("sheet"), e["cell"]) for e in out}) != len(out):
        raise Drop("format", "each cell is edited once")
    return out


def _answer_cells(book, answer_position):
    try:
        targets = spreadsheet_compat.resolve_targets(answer_position, book.sheetnames)["targets"]
    except (spreadsheet_compat.CompatibilityError, ValueError):
        raise Drop("format", "unreadable answer position") from None
    cells = []
    for sheet, region in targets:
        low_col, low_row, high_col, high_row = range_boundaries(region)
        cells += [(sheet, book[sheet].cell(row=r, column=c).coordinate)
                  for r in range(low_row, high_row + 1) for c in range(low_col, high_col + 1)]
    return cells


def _number(value):
    return type(value) in (int, float) and value == value and abs(value) != float("inf")


def _recalculated(engine, path, target):
    """The engine's receipt for the workbook at ``path``, its output bytes written to ``target`` (module docstring:
    ``recalc_failed`` unless available; bound to the bytes sent and to its output bytes, else ValueError)."""
    sent = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = engine.recalc(path)
    if not isinstance(receipt, dict) or receipt.get("status") != "available":
        raise Drop("recalc_failed", str(receipt.get("reason") if isinstance(receipt, dict) else receipt)[:80])
    output = receipt.get("output_base64")
    raw = base64.b64decode(output, validate=True) if type(output) is str else None
    require(raw is not None and receipt.get("input_sha256") == sent
            and receipt.get("output_sha256") == hashlib.sha256(raw).hexdigest(),
            "The recalculation receipt is not bound to the workbook sent and to its output bytes")
    target.write_bytes(raw)
    return receipt


def apply(family, params, material, *, engine, source_item, out_dir, item_id):
    """One SpreadsheetBench item from one parameter set on ``source_item`` (a pool item: public ``input_files`` and
    ``answer_position``, private ``test_files``): {"public", "private_fields", "truth", "engine_qualification",
    "findings"}; Drop on any failure (module docstring). Files go under ``out_dir/<item_id>``. A dropped item's folder
    is removed again: ``generate`` gives the next parameter set the dropped item's number, hence its folder
    (integration C4)."""
    if material.get("kind") != "functions":
        raise Drop("material_mismatch", "the sheet family consumes researched functions")
    edits = _edits(check(family, params)["edits"], material["functions"])
    folder = safe_path(out_dir) / hashlib.sha256(item_id.encode()).hexdigest()[:16]
    folder.mkdir(parents=True, exist_ok=False)
    try:
        return _made(family, edits, material, engine=engine, source_item=source_item, folder=folder, item_id=item_id)
    except Drop:
        shutil.rmtree(folder)
        raise


def _made(family, edits, material, *, engine, source_item, folder, item_id):
    """Steps 1-5 of the module docstring for one item, its files in the fresh ``folder``."""
    public, private = source_item["public"], source_item["private"]
    reference = openpyxl.load_workbook(private["test_files"][0])
    source_input = openpyxl.load_workbook(public["input_files"][0])
    answers = _answer_cells(reference, private["answer_position"])
    if not all(isinstance(reference[s][c].value, str) and reference[s][c].value.startswith("=") for s, c in answers):
        raise Drop("literal_answer")
    targets = []
    for edit in edits:  # 2. the targets
        sheet = edit.get("sheet", reference.sheetnames[0])
        if (sheet not in reference.sheetnames or sheet not in source_input.sheetnames or (sheet, edit["cell"]) in
                answers):
            raise Drop("edit_target_invalid", "%s!%s" % (sheet, edit["cell"]))
        before = reference[sheet][edit["cell"]].value
        if not _number(before) or isinstance(before, bool) or source_input[sheet][edit["cell"]].value != before:
            raise Drop("edit_target_invalid", "%s!%s is not the same numeric literal" % (sheet, edit["cell"]))
        targets.append((sheet, edit["cell"], before))
        reference[sheet][edit["cell"]] = edit["formula"]
    edited = folder / "edited-reference.xlsx"
    reference.save(edited)
    recalculated = folder / "recalculated-reference.xlsx"
    receipt = _recalculated(engine, edited, recalculated)  # 3. semantic truth
    values = openpyxl.load_workbook(recalculated, data_only=True)
    new = {(s, c): values[s][c].value for s, c, _ in targets}
    if not all(_number(v) and not isinstance(v, bool) for v in new.values()):
        raise Drop("recalc_failed", "an edited cell has no numeric value")
    if all(new[(s, c)] == before for s, c, before in targets):
        raise Drop("perturbation_noop")
    expected = {"%s!%s" % cell: values[cell[0]][cell[1]].value for cell in answers}
    paths = {}
    for name, original in (("input", public["input_files"][0]), ("answer", private["test_files"][0])):
        book = openpyxl.load_workbook(original)  # 4. both workbooks are edited, then recalculated
        for (sheet, cell), value in new.items():
            book[sheet][cell] = value
        literal = folder / ("literal-%s.xlsx" % name)
        book.save(literal)
        paths[name] = folder / ("%s.xlsx" % name)
        _recalculated(engine, literal, paths[name])
    public_view = {**public, "input_files": [str(paths["input"])]}
    private_fields = {"test_files": [str(paths["answer"])], "answer_position": private["answer_position"],
                      "asset_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in (paths["input"], paths["answer"])}}
    task = {"task_id": item_id, "public": public_view, "private": private_fields}
    qualification = engine.qualify([task], folder / "qualification", engine.runtime, side="train",
                                   native=engine.native, workers=1)  # 5. the separate engine check
    qualified = item_id in qualification.get("qualified", [])
    if not qualified:
        raise Drop("engine_qualification_failed")
    used = sorted({name for edit in edits for name in functions(edit["formula"])})
    return {"public": public_view, "private_fields": private_fields,
            "truth": {"kind": "recalc_formula", "family": family.name, "checked_by": CHECKED_BY,
                      "edits": [dict(edit) for edit in edits],
                      "edited_values": {"%s!%s" % cell: value for cell, value in sorted(new.items())},
                      "expected_cells": expected, "recalc_output_sha256": receipt.get("output_sha256")},
            "engine_qualification": {"ok": True, "passes": qualification.get("scorings_per_item"),
                                     "record_sha256": digest(qualification)},
            "findings": [material["functions"][name]["id"] for name in used]}
