"""Cell-value evaluator faithful to the official SpreadsheetBench
`evaluation/evaluation.py` (https://github.com/RUCKBReasoning/SpreadsheetBench).

Key rules (copied from the official `transform_value` / `compare_cell_value`):
  * numeric values (int/float and numeric strings) are compared after
    ``round(float(v), 2)`` — a fixed 2-decimal quantization (NOT a tolerance);
  * ``datetime.time`` is stringified and the trailing microseconds stripped;
  * ``datetime.datetime`` is converted to an Excel serial day and rounded
    to an integer day;
  * an empty string ``""`` and ``None`` are considered equal, but otherwise
    ``type(v1) != type(v2)`` fails the comparison.

Format/style comparison is deliberately NOT performed — the official
reference evaluator also skips it (the relevant lines are commented out
in `cell_level_compare`). soft vs hard is defined at the run_bench level
across a task's multiple test cases, not here.

Repo-local evidence guards reject invalid/empty target specifications and
report missing formula results as unknown. They do not change the value
comparison above, evaluate formulas, or prove cached results are fresh.
"""
from __future__ import annotations

import datetime
import os
import re
from contextlib import ExitStack

import openpyxl

EVALUATOR_VERSION = "spreadsheetbench-cell-values-evidence-guards-v2"


# ---------- value transform / compare (official port) ----------

def _datetime_to_float(dt: datetime.datetime) -> float:
    excel_start_date = datetime.datetime(1899, 12, 30)
    delta = dt - excel_start_date
    return delta.days + delta.seconds / 86400.0


def _transform_value(v):
    if isinstance(v, bool):
        # openpyxl can return Python bool; official code doesn't special-case
        # bools, but round(float(True), 2) == 1.0 which breaks 1 vs True. Keep
        # parity with the official transform by promoting bool -> float.
        return round(float(v), 2)
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    if isinstance(v, datetime.time):
        return str(v)[:-3]
    if isinstance(v, datetime.datetime):
        return round(_datetime_to_float(v), 0)
    if isinstance(v, str):
        try:
            return round(float(v), 2)
        except ValueError:
            return v
    return v


def _compare_cell_value(v1, v2) -> bool:
    v1 = _transform_value(v1)
    v2 = _transform_value(v2)
    if (v1 == "" and v2 is None) or (v1 is None and v2 == ""):
        return True
    if (v1 == "" and v2 == "") or (v1 is None and v2 is None):
        return True
    if type(v1) is not type(v2):
        return False
    return v1 == v2


# ---------- bounded A1 range parsing ----------

_CELL_RE = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})\Z")
_MAX_COLUMN = 16384  # XFD: Excel's worksheet limits, not observed used area.
_MAX_ROW = 1048576


class _InvalidSpec(ValueError):
    """The requested comparison is not a valid nonempty A1 cell range."""


def _col_num2name(n: int) -> str:
    name = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        name = chr(65 + r) + name
    return name


def _col_name2num(name: str) -> int:
    num = 0
    for c in name:
        num = num * 26 + (ord(c) - ord("A") + 1)
    return num


def _parse_cell(cell: str) -> tuple[int, int]:
    match = _CELL_RE.fullmatch(cell.strip())
    if match is None:
        raise _InvalidSpec(f"invalid A1 cell: {cell!r}")
    col, row = _col_name2num(match[1].upper()), int(match[2])
    if col > _MAX_COLUMN or row > _MAX_ROW:
        raise _InvalidSpec(f"cell outside Excel worksheet bounds: {cell!r}")
    return col, row


def _parse_range(range_str: str):
    if not isinstance(range_str, str) or range_str.count(":") != 1:
        raise _InvalidSpec(f"invalid A1 range: {range_str!r}")
    start_cell, end_cell = range_str.split(":")
    start, end = _parse_cell(start_cell), _parse_cell(end_cell)
    if start[0] > end[0] or start[1] > end[1]:
        raise _InvalidSpec(f"reversed A1 range: {range_str!r}")
    return start, end


def _range_bounds(range_str: str):
    if not isinstance(range_str, str):
        raise _InvalidSpec("cell range must be a string")
    if ":" in range_str:
        return _parse_range(range_str)
    cell = _parse_cell(range_str)
    return cell, cell


def _iter_cell_names(range_str: str):
    (sc, sr), (ec, er) = _range_bounds(range_str)
    for col in range(sc, ec + 1):
        name = _col_num2name(col)
        for row in range(sr, er + 1):
            yield f"{name}{row}"


def _generate_cell_names(range_str: str):
    # Retain the list API used by rollout's legacy per-cell report. The scorer
    # itself iterates rather than allocating a list for a large target range.
    return list(_iter_cell_names(range_str))


def _split_unquoted(value: str, delimiter: str) -> list[str]:
    """Split unions/sheet references without splitting quoted sheet names."""
    result, start, quote, index = [], 0, None, 0
    while index < len(value):
        char = value[index]
        if quote:
            if char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in "'\"":
            quote = char
        elif char == delimiter:
            result.append(value[start:index])
            start = index + 1
        index += 1
    if quote:
        raise _InvalidSpec("unterminated quote in answer_position")
    result.append(value[start:])
    return result


def _unquote(value: str) -> str:
    value = value.strip()
    if value.startswith(("'", '"')):
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise _InvalidSpec("invalid quoted reference")
        inner = value[1:-1]
        if quote in inner.replace(quote * 2, ""):
            raise _InvalidSpec("unescaped quote in reference")
        return inner.replace(quote * 2, quote)
    if "'" in value or '"' in value:
        raise _InvalidSpec("unquoted quote in reference")
    return value


def _answer_targets(answer_position: str, default_sheet: str) -> list[tuple[str, str]]:
    if not isinstance(answer_position, str) or not answer_position.strip():
        raise _InvalidSpec("answer_position must contain at least one cell")
    targets = []
    for reference in _split_unquoted(answer_position, ","):
        if not reference.strip():
            raise _InvalidSpec("empty range in answer_position")
        pieces = _split_unquoted(reference, "!")
        if len(pieces) == 1:
            sheet, cell_range = default_sheet, _unquote(pieces[0])
        elif len(pieces) == 2:
            sheet, cell_range = _unquote(pieces[0]), _unquote(pieces[1])
        else:
            raise _InvalidSpec("multiple unquoted sheet separators")
        if not sheet:
            raise _InvalidSpec("empty worksheet name")
        _range_bounds(cell_range)  # Validate every union member before scoring.
        targets.append((sheet, cell_range))
    return targets


def _cell_level_compare(wb_gt, wb_proc, sheet_name: str, cell_range: str):
    try:
        _range_bounds(cell_range)
    except _InvalidSpec as exc:
        return False, f"invalid_spec: {exc}"
    if sheet_name not in wb_gt.sheetnames:
        return False, f"invalid_spec: reference worksheet not found: {sheet_name}"
    if sheet_name not in wb_proc.sheetnames:
        return False, f"missing_output: worksheet not found: {sheet_name}"
    ws_gt = wb_gt[sheet_name]
    ws_proc = wb_proc[sheet_name]
    for cn in _iter_cell_names(cell_range):
        cg = ws_gt[cn]
        cp = ws_proc[cn]
        if not _compare_cell_value(cg.value, cp.value):
            return False, f"value@{sheet_name}!{cn}: gt={cg.value!r} pred={cp.value!r}"
    return True, ""


# ---------- public API ----------

def compare_workbooks(gt_file: str, proc_file: str, answer_position: str) -> tuple[bool, str]:
    """Return (ok, msg), retaining official cell-value semantics.

    ``invalid_spec`` and ``unavailable`` are not confirmed answer errors.
    Missing cached formula values cannot distinguish an uncalculated formula
    from some legitimate empty-string formula results, so fail closed with
    unavailable instead of treating two missing values as verified equality.
    No recalculation or cache-freshness validation is performed here.
    """
    try:
        # Validate even when a workbook is missing, before any scoring occurs.
        _answer_targets(answer_position, "<default>")
    except _InvalidSpec as exc:
        return False, f"invalid_spec: {exc}"
    if not os.path.isfile(gt_file):
        return False, "unavailable: reference file not found"
    if not os.path.exists(proc_file):
        return False, "missing_output: file not found"
    with ExitStack() as stack:
        try:
            workbooks = []
            for path, data_only in ((gt_file, True), (proc_file, True),
                                    (gt_file, False), (proc_file, False)):
                wb = openpyxl.load_workbook(filename=path, data_only=data_only)
                stack.callback(wb.close)
                workbooks.append(wb)
            wb_gt, wb_proc, formula_gt, formula_proc = workbooks
        except Exception as exc:  # noqa: BLE001
            return False, f"unavailable: workbook load error: {exc}"
        if not wb_gt.sheetnames:
            return False, "invalid_spec: reference workbook has no worksheets"
        targets = _answer_targets(answer_position, wb_gt.sheetnames[0])
        for sheet_name, _ in targets:
            if sheet_name not in wb_gt.sheetnames:
                return False, f"invalid_spec: reference worksheet not found: {sheet_name}"
            if sheet_name not in wb_proc.sheetnames:
                return False, f"missing_output: worksheet not found: {sheet_name}"
        # Retain both confirmed mismatches and unavailable observations. One
        # uncalculated formula cannot erase a mismatch in another checked cell;
        # equally, missing caches alone must never be scored as a mismatch.
        first_mismatch = None
        first_unavailable = None
        unavailable_cells = 0
        for sheet_name, cell_range in targets:
            for cn in _iter_cell_names(cell_range):
                unavailable = False
                for label, values, formulas in (("reference", wb_gt, formula_gt),
                                               ("prediction", wb_proc, formula_proc)):
                    if (formulas[sheet_name][cn].data_type == "f"
                            and values[sheet_name][cn].value is None):
                        unavailable = True
                        if first_unavailable is None:
                            first_unavailable = (f"unavailable: formula result missing in {label} "
                                                 f"at {sheet_name}!{cn}; recalculation required "
                                                 "(not performed)")
                if unavailable:
                    unavailable_cells += 1
                    continue
                actual, expected = wb_proc[sheet_name][cn].value, wb_gt[sheet_name][cn].value
                if not _compare_cell_value(expected, actual) and first_mismatch is None:
                    first_mismatch = f"value@{sheet_name}!{cn}: gt={expected!r} pred={actual!r}"
        if first_mismatch is not None:
            if first_unavailable is not None:
                first_mismatch += f"; partial_unavailable_cells={unavailable_cells}; {first_unavailable}"
            return False, first_mismatch
        if first_unavailable is not None:
            return False, first_unavailable
        return True, ""


def evaluate(pred_path: str, gold_path: str,
             instruction_type: str, answer_position: str) -> dict:
    """Single test-case evaluate. soft/hard aggregation happens in run_bench.

    Legacy ``ok`` remains fail-closed: False alone does not mean a confirmed
    semantic failure. New consumers must retain ``status`` and ``reason``.
    """
    ok, msg = compare_workbooks(gold_path, pred_path, answer_position)
    if ok:
        status = "passed"
    elif msg.startswith("invalid_spec:"):
        status = "invalid_spec"
    elif msg.startswith("unavailable:"):
        status = "unknown"
    elif msg.startswith("missing_output:"):
        status = "missing_output"
    else:
        status = "failed"
    return {
        "ok": ok,
        "reason": msg,
        "status": status,
        "evaluator_version": EVALUATOR_VERSION,
        "instruction_type": instruction_type,
    }
