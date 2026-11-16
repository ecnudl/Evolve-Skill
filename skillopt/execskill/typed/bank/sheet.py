"""SpreadsheetBench made items: fixed code around reference programs (no model call; reads training-side workbooks).

A sheet practice item is an instruction, an input workbook, an answer position and an expected workbook. Its CODE
RUBRIC is a reference program: a Python program that turns ``input.xlsx`` into an ``output.xlsx`` whose answer
cells equal the expected workbook's under the benchmark's own scorer (the anchor: "reproduce the reference first").
An anchored program is what allows a changed copy of the workbook (a data twin) or a new instruction on the same
workbook to get an expected output computed by code instead of stated by a model.

This module holds what needs no sandbox:

- ``workbook_view``: what a program writer is shown of a training workbook -- more than the solver's five-row
  preview (the writer must see how far the data go), never more than fixed limits;
- ``answer_cells``: the expected values at the answer position (cached values of the expected workbook);
- ``screen_program``: a reference program may not carry the expected answers as constants (a program that writes
  its answers down would pass the anchor and compute nothing on changed data);
- ``scale_workbook``: the data change of a twin -- every numeric constant cell outside protected cells multiplied
  by ONE factor, so sums, order, equal keys and signs keep their relations;
- ``label_output``: the rubric's name for a wrong output workbook (missing output or sheet, nothing written, right
  values in the wrong rows or columns, texts that differ only in case or blanks, numbers that are close, a text
  where a number or date was due, part of the cells right).

The benchmark's scorer alone decides right and wrong; the answer position grammar and the cell comparison are the
scorer's own functions (``continual_eval.spreadsheet_compat``, ``envs/spreadsheetbench/evaluator.py``).
"""
from __future__ import annotations

import ast
import datetime
import re
from fractions import Fraction

VIEW_ROWS, VIEW_COLUMNS, VIEW_TAIL_ROWS, VIEW_SHEETS, VIEW_CELL_CHARS = 12, 20, 3, 8, 80
EXPECTED_SHOWN = 60               # expected answer cells shown to a program writer
MIN_CONSTANT_CHARS = 3            # a constant shorter than this is never called a copied answer
SCALE_FACTORS = (Fraction(13, 10), Fraction(7, 10), Fraction(21, 10))   # the factor of a parent's first, second, third twin
LABELS = ('missing_output', 'missing_sheet', 'nothing_written', 'shifted_rows', 'shifted_columns', 'text_form',
          'number_close', 'type_mismatch', 'partly_right', 'all_wrong')


class Drop(Exception):
    def __init__(self, reason, detail=''):
        super().__init__(reason + (': ' + str(detail) if detail else ''))
        self.reason, self.detail = reason, str(detail)


def _tools():
    """The scorer's own grammar and comparison, loaded where they are needed (the bound machinery snapshot)."""
    from skillopt.continual_eval import spreadsheet_compat
    return spreadsheet_compat.resolve_targets, spreadsheet_compat._legacy()


def targets(answer_position, sheetnames):
    """[(sheet, [cell coordinates])] of an answer position, by the scorer's own parser."""
    resolve, legacy = _tools()
    return [(sheet, list(legacy._iter_cell_names(region)))
            for sheet, region in resolve(answer_position, list(sheetnames))['targets']]


def targets_in(answer_position, sheetnames):
    """``targets`` for a workbook that may lack the answer sheet (a task that creates a new sheet): the targets on
    sheets the workbook has, and whether some answer sheet is missing in it."""
    from skillopt.continual_eval.spreadsheet_compat import CompatibilityError
    try:
        return targets(answer_position, sheetnames), False
    except CompatibilityError:
        return [], True


def shown(value):
    """A cell value as a writer sees it: text cut to VIEW_CELL_CHARS, dates in ISO form, None as None."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return str(value)[:VIEW_CELL_CHARS]


def workbook_view(path, answer_position):
    """{sheets: [{sheet, rows, columns, first_rows, last_rows}], answer_cells_in_input}: formulas as text (as the
    solver's preview shows them), at most VIEW_SHEETS sheets, VIEW_ROWS first and VIEW_TAIL_ROWS last rows of
    VIEW_COLUMNS columns, and the current content of the answer cells."""
    import openpyxl
    book = openpyxl.load_workbook(path, data_only=False)
    try:
        sheets = []
        for sheet in book.worksheets[:VIEW_SHEETS]:
            rows, columns = sheet.max_row or 0, sheet.max_column or 0
            grid = lambda first, last: [[shown(sheet.cell(row=r, column=c).value) for c in range(1, min(columns, VIEW_COLUMNS) + 1)]
                                        for r in range(first, last + 1)]
            head = min(rows, VIEW_ROWS)
            tail_start = max(head + 1, rows - VIEW_TAIL_ROWS + 1)
            sheets.append({'sheet': sheet.title, 'rows': rows, 'columns': columns, 'first_rows': grid(1, head),
                           'last_rows': {'from_row': tail_start, 'rows': grid(tail_start, rows)} if rows > head else None})
        inside, missing = [], False
        found, missing = targets_in(answer_position, book.sheetnames)
        for name, cells in found:
            inside += [{'sheet': name, 'cell': cell, 'value': shown(book[name][cell].value)} for cell in cells]
        view = {'sheets': sheets, 'answer_cells_in_input': inside[:EXPECTED_SHOWN], 'answer_cells': len(inside)}
        if missing:
            view['answer_sheet_missing_in_input'] = True   # the task creates the sheet (or the name differs)
        return view
    finally:
        book.close()


def answer_cells(path, answer_position):
    """[(sheet, cell, cached value)] of a workbook at the answer position (openpyxl ``data_only``)."""
    import openpyxl
    book = openpyxl.load_workbook(path, data_only=True)
    try:
        return [(name, cell, book[name][cell].value) for name, cells in targets(answer_position, book.sheetnames)
                for cell in cells]
    finally:
        book.close()


def workbook_values(path):
    """The set of every cell value of a workbook as text (constants and formula texts): what a program may name
    without having copied it from the expected workbook."""
    import openpyxl
    book = openpyxl.load_workbook(path, data_only=False)
    try:
        return {_text(cell.value) for sheet in book.worksheets for row in sheet.iter_rows() for cell in row
                if cell.value is not None}
    finally:
        book.close()


def _text(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return str(value).strip()


def program_constants(source):
    """The string and number constants of a program, as text; ``Drop('syntax')`` when it does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        raise Drop('syntax') from None
    return {_text(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)) and not isinstance(node.value, bool)}


def screen_program(source, instruction, expected, input_values):
    """Refuse a reference program that carries expected answers as constants. ``expected``: the expected values of
    the answer cells; ``input_values``: ``workbook_values`` of the input. A constant counts as a copied answer when
    it equals an expected value of at least MIN_CONSTANT_CHARS characters that is neither a cell value of the
    input nor written in the instruction (a category word such as "Pass" that the instruction itself names is never
    one). ONE copied answer refuses the program, however many answer cells there are."""
    constants = program_constants(source)
    answers = {_text(value) for value in expected if value is not None}
    copied = sorted(value for value in constants & answers
                    if len(value) >= MIN_CONSTANT_CHARS and value not in input_values and value not in instruction)
    if copied:   # any one (review 2026-11-13: a program that computes one answer and writes the other down passed)
        raise Drop('copied_answers', ', '.join(copied[:5]))
    if 'input.xlsx' not in source or 'output.xlsx' not in source:
        raise Drop('contract', 'the program must read input.xlsx and write output.xlsx')
    return len(constants)


def compare_cells(first_path, second_path, answer_position):
    """'same', 'different' or 'unknown' for the answer cells of two workbooks by their CACHED values and the scorer's
    cell rule (no recalculation: both files must hold values, not uncached formulas, in the answer cells)."""
    from skillopt.continual_eval import spreadsheet_compat
    status = spreadsheet_compat.evaluate(str(first_path), str(second_path), None, answer_position)['status']
    return {'passed': 'same', 'failed': 'different'}.get(status, 'unknown')


def blank_answer(path, answer_position):
    """Whether EVERY answer cell of a workbook is empty (None or blank text): a reference that fills nothing."""
    return all(value is None or (isinstance(value, str) and not value.strip())
               for _, _, value in answer_cells(path, answer_position))


# ---- data twins ----------------------------------------------------------------------------------------------------
def looks_like_year(value):
    return isinstance(value, int) and 1800 <= value <= 2100


def scale_workbook(source_path, target_path, factor, answer_position, instruction):
    """A copy of a workbook with every numeric constant cell multiplied by ``factor`` (a Fraction or int ratio),
    integers staying integers (rounded half up) and decimals keeping their number of decimals. NOT changed: formula
    cells, the answer cells, booleans, dates, year-like integers, integers below 10 in absolute value, and any
    number written in the instruction. Returns the number of cells changed; ``Drop('nothing_to_change')`` below 3."""
    import openpyxl
    factor = Fraction(factor)
    named = set(re.findall(r'\d+(?:\.\d+)?', instruction))
    book = openpyxl.load_workbook(source_path, data_only=False)
    try:
        protected = {(name, cell) for name, cells in targets_in(answer_position, book.sheetnames)[0] for cell in cells}
        changed = 0
        for sheet in book.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    value = cell.value
                    if (isinstance(value, bool) or not isinstance(value, (int, float)) or cell.is_date
                            or (sheet.title, cell.coordinate) in protected or looks_like_year(value)
                            or (isinstance(value, int) and abs(value) < 10) or _text(value) in named or value == 0):
                        continue
                    if isinstance(value, int) or float(value).is_integer():
                        scaled = _half_up(Fraction(int(value)) * factor, 0)
                        new = int(scaled) if isinstance(value, int) else float(scaled)
                    else:
                        places = min(6, len(repr(float(value)).partition('.')[2]))
                        new = float(_half_up(Fraction(repr(float(value))) * factor, places))
                    if new != value:
                        cell.value = new
                        changed += 1
        if changed < 3:
            raise Drop('nothing_to_change', changed)
        book.save(target_path)
        return changed
    finally:
        book.close()


def _half_up(value, places):
    """``value`` (a Fraction) rounded half away from zero to ``places`` decimals, exactly."""
    scaled = abs(value) * 10 ** places
    whole = int(scaled + Fraction(1, 2))
    return Fraction(whole, 10 ** places) * (-1 if value < 0 else 1)


# ---- the rubric's label of a wrong output ----------------------------------------------------------------------------
def label_output(output_path, expected_path, answer_position):
    """The label of an output workbook the scorer counted wrong, from the expected workbook: one of ``LABELS``.
    Cached values are compared with the scorer's own cell rule (numbers at two decimals, numeric texts as numbers,
    dates by day, other texts exactly). ``shifted_rows`` / ``shifted_columns``: every expected value stands one row
    or column away. When all wrong cells fail the same way: ``text_form`` (equal but for case or blanks),
    ``number_close`` (within one percent), ``type_mismatch`` (a text where a number or date was due, or the
    reverse). Else ``partly_right`` or ``all_wrong``."""
    import openpyxl
    _, legacy = _tools()
    same = legacy._compare_cell_value
    if output_path is None:
        return 'missing_output'
    expected_book = openpyxl.load_workbook(expected_path, data_only=True)
    try:
        output_book = openpyxl.load_workbook(output_path, data_only=True)
    except Exception:
        expected_book.close()
        return 'missing_output'
    try:
        cells = [(name, cell) for name, group in targets(answer_position, expected_book.sheetnames) for cell in group]
        if any(name not in output_book.sheetnames for name, _ in cells):
            return 'missing_sheet'
        want = [expected_book[name][cell].value for name, cell in cells]
        got = [output_book[name][cell].value for name, cell in cells]
        wrong = [(a, b) for a, b in zip(got, want) if not same(a, b)]
        if not wrong:
            return 'partly_right'  # the scorer saw a difference these cached values do not show (a recalculation)
        def moved(rows, columns):
            hits, filled = 0, 0
            for (name, cell), value in zip(cells, want):
                if value is None:
                    continue
                filled += 1
                place = output_book[name][cell]
                if place.row + rows >= 1 and place.column + columns >= 1:
                    hits += same(place.offset(row=rows, column=columns).value, value)
            return filled >= 2 and hits == filled
        if moved(1, 0) or moved(-1, 0):
            return 'shifted_rows'
        if moved(0, 1) or moved(0, -1):
            return 'shifted_columns'
        if all(value is None for value in got) and any(value is not None for value in want):
            return 'nothing_written'
        kinds = {_difference(a, b) for a, b in wrong}
        if len(kinds) == 1 and kinds != {'other'}:
            return kinds.pop()
        return 'partly_right' if len(wrong) < len(cells) else 'all_wrong'
    finally:
        expected_book.close()
        output_book.close()


def _difference(got, want):
    """How one wrong cell differs from the expected one: text_form, number_close, type_mismatch or other."""
    number = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(got, str) and isinstance(want, str):
        if _number(got) is None and ' '.join(got.split()).casefold() == ' '.join(want.split()).casefold():
            return 'text_form'
        a, b = _number(got), _number(want)
    else:
        a = got if number(got) else _number(got) if isinstance(got, str) else None
        b = want if number(want) else _number(want) if isinstance(want, str) else None
    if a is not None and b is not None:
        return 'number_close' if abs(a - b) <= 0.01 * max(abs(a), abs(b), 1e-9) else 'other'
    if got is not None and want is not None and (isinstance(got, str) != isinstance(want, str)):
        return 'type_mismatch'
    return 'other'


def _number(text):
    try:
        return float(text.replace(',', '').strip())
    except ValueError:
        return None
