"""Container-only SpreadsheetBench pre-check worker; never execute on the host (protocol ``fivebench-execskill-v1``;
registration §2.5; implementation plan §1 precheck.py row, §3 sheet rows).

A copy of the frozen ``skillopt/continual_eval/native_worker.py`` (the container guard, the request file, the stdout
and stderr sink, the one JSON envelope on stdout) with one operation added and the others removed:
``spreadsheet_precheck`` runs the extracted program ONCE on the public input workbook, exactly as the frozen
``spreadsheet_generate`` does (native_worker.py:91-104: a fresh directory, ``input.xlsx`` written from the request,
``exec`` of the program as ``__main__``), and returns a run report instead of the output workbook:
- ``ok``: the program finished and wrote ``output.xlsx``; ``answer_cells`` = the values written at the public answer
  position (at most ``MAX_ANSWER_CELLS`` cells, each shown as at most ``MAX_CELL_CHARS`` characters);
- ``exception``: the program raised; ``exc_type`` and ``message`` = the last line of its traceback (at most 500
  characters), the shell's own error message (§2.5);
- ``missing_output``: the program finished without writing ``output.xlsx``.
The host side (``precheck.precheck``) mounts this file as ``/input/worker.py`` with the frozen ``_native`` argv and
environment byte for byte, so the program meets the container of the frozen case runs.
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import tempfile
import traceback
from pathlib import Path

PROTOCOL = "continual-eval-native-v1"  # the frozen envelope and container marker (native_worker.py:20)
MAX_WORKBOOK = 8 * 1024 * 1024
MAX_MESSAGE_CHARS = 500  # registration §2.5
MAX_ANSWER_CELLS = 2_000
MAX_CELL_CHARS = 200
RANGE = re.compile(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})(?::\$?([A-Za-z]{1,3})\$?(\d{1,7}))?")


def last_line(error):
    """The last line of the traceback of ``error`` ("KeyError: 'Sheet2'"), at most 500 characters."""
    lines = traceback.format_exception_only(type(error), error)
    return (lines[-1].strip() if lines else type(error).__name__)[:MAX_MESSAGE_CHARS]


def _column(letters):
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - 64
    return number


def _parts(position):
    """[(sheet or None, min_col, min_row, max_col, max_row)] of a public answer position such as "B1",
    "A1:C3", "Sheet1!A1:B2" or "'My Sheet'!A1:B2,D4"; ValueError for anything else."""
    parts, sheet = [], None
    for chunk in position.split(","):
        chunk = chunk.strip()
        if "!" in chunk:
            name, _, chunk = chunk.rpartition("!")
            sheet = name.strip().strip("'")
        match = RANGE.fullmatch(chunk.strip())
        if match is None:
            raise ValueError("unsupported answer position")
        first_col, first_row = _column(match.group(1)), int(match.group(2))
        last_col = _column(match.group(3)) if match.group(3) else first_col
        last_row = int(match.group(4)) if match.group(4) else first_row
        parts.append((sheet, min(first_col, last_col), min(first_row, last_row), max(first_col, last_col),
                      max(first_row, last_row)))
    return parts


def answer_cells(path, position):
    """{"<sheet>!<cell>": shown value} of ``output.xlsx`` at the answer position (formulas as written), None when the
    position or the workbook cannot be read."""
    import openpyxl
    from openpyxl.utils import get_column_letter

    try:
        parts = _parts(position)
        book = openpyxl.load_workbook(path, data_only=False)
    except Exception:  # an unreadable position or workbook is reported as unknown cells, not as a program error
        return None
    try:
        cells = {}
        for sheet_name, min_col, min_row, max_col, max_row in parts:
            sheet = book[sheet_name] if sheet_name in book.sheetnames else book.active
            for row in range(min_row, max_row + 1):
                for col in range(min_col, max_col + 1):
                    if len(cells) >= MAX_ANSWER_CELLS:
                        return cells
                    value = sheet.cell(row=row, column=col).value
                    key = "%s!%s%d" % (sheet.title, get_column_letter(col), row)
                    cells[key] = None if value is None else str(value)[:MAX_CELL_CHARS]
        return cells
    finally:
        book.close()


def precheck(request):
    with tempfile.TemporaryDirectory(prefix="sheet-precheck-") as directory:
        os.chdir(directory)
        Path("input.xlsx").write_bytes(base64.b64decode(request["input_base64"], validate=True))
        try:
            exec(compile(request["code"], "generated.py", "exec"), {"__name__": "__main__"})
        except BaseException as error:  # whatever the program raises is its run report, never the worker's failure
            return {"status": "exception", "exc_type": type(error).__name__, "message": last_line(error),
                    "answer_cells": None}
        path = Path("output.xlsx")
        if path.is_symlink() or not path.is_file():
            return {"status": "missing_output", "exc_type": None, "message": "output.xlsx_not_produced",
                    "answer_cells": None}
        if path.stat().st_size > MAX_WORKBOOK:
            return {"status": "unknown", "exc_type": None, "message": "output_workbook_size_limit",
                    "answer_cells": None}
        return {"status": "ok", "exc_type": None, "message": "", "answer_cells": answer_cells(path,
                                                                                            request["answer_position"])}


def perform(request):
    if request["operation"] == "spreadsheet_precheck":
        return precheck(request)
    raise ValueError("Unsupported native operation")


def main():
    # A host caller cannot accidentally run untrusted input through this file.
    if os.environ.get("CONTINUAL_EVAL_CONTAINER") != PROTOCOL or not Path("/.dockerenv").exists():
        raise SystemExit("Container-only worker; use the hardened backend")
    request = json.loads(Path("/input/request.json").read_text())
    # Model code output never becomes an outer protocol frame. /dev/null also
    # avoids retaining arbitrary output in memory inside the container.
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = perform(request)
    except BaseException as exc:
        result = {"status": "unknown", "reason": "native_exception:" + type(exc).__name__}
    print(json.dumps({"protocol": PROTOCOL, "result": result}, allow_nan=False))


if __name__ == "__main__":
    main()
