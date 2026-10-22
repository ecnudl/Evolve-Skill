"""The registrar's engineering fixtures of the route-B smoke (protocol ``fivebench-execskill-v1``; registration §10:
"OfficeQA、LiveMath、SpreadsheetBench 用登记员写的工程夹具题各 20 道", the S0 sandbox, measurement and determinism rows,
the S2 fixture package X and its placebo P; §2.1-§2.6; implementation plan §7 "Fixture items", §10 step 3
``make-fixtures``). Everything here is synthetic registrar content -- never copied from a benchmark item -- labelled
``engineering_fixture`` and never evidence.

- ``make_fixtures``: 20 OfficeQA, 20 LiveMath and 20 SpreadsheetBench items in the pool shape of ``coevo5.data.pool``
  (``benchmark, task_id, family_id, part, public, private``) with the frozen public and private field sets of
  ``continual_eval.datasets`` (checked by the frozen ``validate_panel``), truth computed by program: OfficeQA numeric
  answers from a synthetic table and its note (exact fractions), LiveMath five-option items whose key is computed with
  exact integer and fraction arithmetic (every fourth offers the frozen meta option, never as the key), SpreadsheetBench
  input and reference workbooks written by openpyxl whose answer cells hold formulas WITH their cached values (so the
  v7 recalculating scorer can compare the reference cache with its recalculation), byte-deterministic (fixed zip
  times, fixed document times). With ``p99_workbook_bytes`` (the S0-measured p99 public view, §10 S0 measurement row)
  the last SpreadsheetBench fixture carries a second sheet padded to at least that size. One sealed record of kind
  ``fixtures`` holds each item's content sha256 (workbook paths taken relative to the fixture root, the workbook bytes
  through ``asset_sha256``), its truth, the per-bench and overall set sha256 and the registered fx-crash subset;
  ``verify`` recomputes every hash.
- ``fixture_package``: package X of §10 S2 -- ``fx-note`` (a note), ``fx-bindings`` (bindings: the exact-compute round
  trip of §2.4 on OfficeQA, the one bench whose shell runs it on a table), ``fx-print`` (prints to standard output),
  ``fx-crash`` (raises on the registered subset ``FX_CRASH_SUBSET`` only), ``fx-sheet-repair`` (``sheet_feedback``
  and one repair request, §2.5) and ``fx-alf-tracker`` (the D3 hand tracker as an ``alf_before_step`` /
  ``alf_after_step`` recorder plus one discouraged command). Each has its predicate, description and replay tests on
  ``replay_trajectories``.
- ``fixture_placebo``: P, the irrelevant-text placebo of X (``placebo.irrelevant_text``/``chunks``, the P_i rule of
  §6.1): the yoked P_y needs a donor corpus of sealed run-slice trajectories that only a real run has.
- ``sandbox_suite``: the S0 sandbox procedures with their expected outcome class; ``determinism_hashes``: the
  two-seed, two-order determinism check's run over package X.
- ``add_arguments`` / ``make_fixtures_cli``: the ``make-fixtures`` subcommand.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from fractions import Fraction
from pathlib import Path

import openpyxl

from skillopt.coevo5.data import item_hash
from skillopt.coevo5.protocol import STRONGER_OPTION
from skillopt.continual_eval import datasets
from skillopt.continual_eval.backends import SHEET_PREVIEW_VERSION
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import placebo as placebos
from . import precheck
from .generators.families import Entry, bundle
from .package import FIXTURE, NOTE_HOOKS, Package, Procedure
from .protocol import RECORD_HASH, SANDBOX_TIMEOUTS, SEED, record, verified
from .solver import routing_view

COUNT = 20
BENCHES = ("officeqa", "livemath", "spreadsheetbench")
TAG = "execskill-v1:fixtures"
PART = FIXTURE  # the pool item's ``part``: every fixture item says what it is
RECORD_FILE = "fixtures.json"
SHEET_DIR = "spreadsheetbench"
SHEET_NAME = "Sheet1"
PADDING_SHEET = "Padding"
PADDED = COUNT - 1  # the SpreadsheetBench fixture padded to the S0 p99 size
DOCUMENT_TIME = b"2026-10-21T00:00:00Z"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SHEET_RUNTIME = {"spreadsheet_preview_version": SHEET_PREVIEW_VERSION}  # the smoke's registered sheet preview
CRASH_PER_BENCH = 2
PLACEBO_FACTS = 1  # one irrelevant-text fact per shammed hook: within every X procedure's declared note cap
STEP = "smoke/fixture-x"


def _draw(tag, number, low, high):
    """A seeded integer in [low, high]: sha256 of (SEED, TAG, tag, number), independent of Python's random module."""
    key = hashlib.sha256(json.dumps([SEED, TAG, tag, number]).encode()).hexdigest()
    return low + int(key, 16) % (high - low + 1)


def _item(bench, number, public, private):
    task_id = "fx-%s-%02d" % (bench, number)
    return {"benchmark": bench, "task_id": task_id, "family_id": "%s:%s" % (bench, task_id), "part": PART,
            "public": public, "private": private}


def _decimal(value):
    """An exact value as text: an integer as it is, any other value rounded half away from zero to two decimals."""
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    cents = (200 * abs(value.numerator) + value.denominator) // (2 * value.denominator)
    return "%s%d.%02d" % (sign, cents // 100, cents % 100)


# ---------------------------------------------------------------------------------------------------- OfficeQA
OQ_COLUMNS = ("Customs", "Excise", "Estate", "Misc")
OQ_KINDS = ("difference", "ratio", "percent_change", "sum", "net_of_note")


def officeqa_items():
    """[(item, truth)]: one synthetic receipts table per item, rendered as a parsed page, and one question whose answer
    is computed exactly from the table (and, for ``net_of_note``, the note under it)."""
    out = []
    for n in range(COUNT):
        years = [2011 + n % 7 + k for k in range(4)]
        table = {y: {c: _draw("officeqa:%s:%d" % (c, y), n, 120, 9800) for c in OQ_COLUMNS} for y in years}
        refund = _draw("officeqa:refund", n, 11, 99)
        first, last = years[0], years[-1]
        column = OQ_COLUMNS[n % len(OQ_COLUMNS)]
        other = OQ_COLUMNS[(n + 1) % len(OQ_COLUMNS)]
        kind = OQ_KINDS[n % len(OQ_KINDS)]
        a, b = table[first][column], table[last][column]
        if kind == "difference":
            question = "By how much did %s receipts change from fiscal year %d to fiscal year %d?" % (
                column.lower(), first, last)
            value, operands = Fraction(b - a), {"from": a, "to": b}
        elif kind == "ratio":
            question = ("What is the ratio of %s receipts to %s receipts in fiscal year %d? Give the value to two "
                        "decimal places." % (column.lower(), other.lower(), last))
            value, operands = Fraction(b, table[last][other]), {"numerator": b, "denominator": table[last][other]}
        elif kind == "percent_change":
            question = ("What was the percent change in %s receipts from fiscal year %d to fiscal year %d? Give the "
                        "value to two decimal places." % (column.lower(), first, last))
            value, operands = Fraction(100 * (b - a), a), {"from": a, "to": b}
        elif kind == "sum":
            question = "What is the sum of all four receipt columns in fiscal year %d?" % years[1]
            value, operands = Fraction(sum(table[years[1]].values())), dict(table[years[1]])
        else:
            question = ("What were the %s receipts of fiscal year %d net of the refunds stated in the note under "
                        "the table?" % (column.lower(), years[2]))
            value, operands = Fraction(table[years[2]][column] - refund), {"gross": table[years[2]][column],
                                                                            "refund": refund}
        rows = ["| Fiscal year | %s |" % " | ".join(OQ_COLUMNS), "| --- | --- | --- | --- | --- |"]
        rows += ["| %d | %s |" % (y, " | ".join(str(table[y][c]) for c in OQ_COLUMNS)) for y in years]
        context = ("Fixture page FX-OQ-%02d (synthetic engineering fixture; not taken from any publication)\n\n"
                   "Table %d. Receipts by source, fiscal years %d-%d (in millions of dollars)\n\n%s\n\n"
                   "Note: refunds of %d million dollars of %s receipts were paid in fiscal year %d; the table shows "
                   "gross receipts.\n" % (n, 1 + n % 9, first, last, "\n".join(rows), refund, column.lower(),
                                          years[2]))
        answer = _decimal(value)
        out.append((_item("officeqa", n, {"question": question, "context": context}, {"answer": answer}),
                    {"kind": kind, "operands": operands, "exact": str(value), "answer": answer}))
    return out


# ---------------------------------------------------------------------------------------------------- LiveMath
LM_KINDS = ("series", "gcd", "polynomial", "power_mod", "fraction_sum")


def _livemath_question(kind, n):
    """(question, truth as Fraction, distractor offsets) of one LiveMath fixture."""
    if kind == "series":
        low, high = _draw("lm:low", n, 3, 40), _draw("lm:high", n, 60, 400)
        return ("What is the sum of all integers from %d to %d inclusive?" % (low, high),
                Fraction((low + high) * (high - low + 1), 2), (1, -1, high, -high))
    if kind == "gcd":
        g, p, q = _draw("lm:g", n, 6, 48), _draw("lm:p", n, 5, 30), _draw("lm:q", n, 31, 60)
        while _gcd(p, q) != 1:
            q += 1
        return ("What is the greatest common divisor of %d and %d?" % (g * p, g * q), Fraction(g),
                (1, -1, g, 2 * g))
    if kind == "polynomial":
        c2, c1, c0, x = (_draw("lm:c2", n, 2, 9), _draw("lm:c1", n, -15, 15), _draw("lm:c0", n, -40, 40),
                         _draw("lm:x", n, 2, 12))
        return ("Let f(x) = %dx^2 %s %dx %s %d. What is f(%d)?" % (c2, "+" if c1 >= 0 else "-", abs(c1),
                                                                "+" if c0 >= 0 else "-", abs(c0), x),
                Fraction(c2 * x * x + c1 * x + c0), (1, -1, 2 * x, -2 * x))
    if kind == "power_mod":
        base, power, modulus = _draw("lm:b", n, 3, 19), _draw("lm:e", n, 20, 200), _draw("lm:m", n, 7, 97)
        truth = pow(base, power, modulus)
        return ("What is the remainder when %d^%d is divided by %d?" % (base, power, modulus), Fraction(truth),
                tuple(d if 0 <= truth + d < modulus else d - modulus for d in (1, 2, 3, 4)))
    a, b, c, d = _draw("lm:a", n, 1, 9), _draw("lm:b2", n, 2, 12), _draw("lm:c", n, 1, 9), _draw("lm:d", n, 2, 12)
    return ("What is %d/%d + %d/%d in lowest terms?" % (a, b, c, d), Fraction(a, b) + Fraction(c, d),
            (Fraction(1, b * d), Fraction(-1, b * d), Fraction(1), Fraction(a + c, b + d) - Fraction(a, b)
             - Fraction(c, d)))


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def _option(value):
    return str(value.numerator) if value.denominator == 1 else "%d/%d" % (value.numerator, value.denominator)


def livemath_items():
    """[(item, truth)]: five options "A. ..." to "E. ..." separated by blank lines (the frozen rendering); the key is
    the letter of the exactly computed value. Items 3, 7, 11, 15, 19 offer the frozen meta option as E (never the
    key, the true option is among A-D)."""
    out = []
    for n in range(COUNT):
        kind = LM_KINDS[n % len(LM_KINDS)]
        question, truth, offsets = _livemath_question(kind, n)
        wrong = []
        for offset in offsets:
            candidate = truth + offset
            if candidate != truth and candidate not in wrong:
                wrong.append(candidate)
        extra = 5
        while len(wrong) < 4:
            if truth + extra not in wrong:
                wrong.append(truth + extra)
            extra += 1
        meta = n % 4 == 3
        texts = [_option(v) for v in wrong[:3 if meta else 4]]
        position = _draw("lm:key", n, 0, 3 if meta else 4)
        texts.insert(position, _option(truth))
        if meta:
            texts.append(STRONGER_OPTION)
        choices = "\n\n".join("%s. %s" % (label, text) for label, text in zip("ABCDE", texts))
        letter = "ABCDE"[position]
        out.append((_item("livemath", n, {"question": question, "choices": choices}, {"answer": letter}),
                    {"kind": kind, "value": _option(truth), "answer": letter, "meta_option": meta}))
    return out


# ------------------------------------------------------------------------------------------------ SpreadsheetBench
SB_KINDS = ("sum", "row_product", "average", "count_above", "maximum")
SB_HEADER = ("Item", "Quantity", "Price")
COUNT_THRESHOLD = 25


def _sheet_task(n):
    """The data rows, the instruction, the answer position and the answer cells {coordinate: (formula, value)} of
    SpreadsheetBench fixture ``n``; the values are computed here, independently of any spreadsheet engine."""
    kind, rows = SB_KINDS[n % len(SB_KINDS)], 5 + n
    last = rows + 1
    data = [("Item %02d" % (r + 1), _draw("sb:q:%d" % r, n, 1, 50), _draw("sb:p:%d" % r, n, 2, 99))
            for r in range(rows)]
    quantities = [q for _, q, _ in data]
    if kind == "average":  # the last quantity makes the mean an integer, so the cached value is exact
        name, q, price = data[-1]
        q += (-sum(quantities)) % rows
        data[-1] = (name, q, price)
        quantities[-1] = q
    span = "B2:B%d" % last
    if kind == "sum":
        instruction = "In %s, put a formula in D2 that totals the Quantity column (%s)." % (SHEET_NAME, span)
        cells = {"D2": ("=SUM(%s)" % span, sum(quantities))}
    elif kind == "row_product":
        instruction = ("In %s, fill D2:D%d with formulas giving each row's Quantity multiplied by its Price."
                       % (SHEET_NAME, last))
        cells = {"D%d" % (r + 2): ("=B%d*C%d" % (r + 2, r + 2), data[r][1] * data[r][2]) for r in range(rows)}
    elif kind == "average":
        instruction = "In %s, put a formula in D2 that gives the average Quantity of %s." % (SHEET_NAME, span)
        cells = {"D2": ("=AVERAGE(%s)" % span, sum(quantities) // rows)}
    elif kind == "count_above":
        instruction = ("In %s, put a formula in D2 that counts the rows of %s whose Quantity is greater than %d."
                       % (SHEET_NAME, span, COUNT_THRESHOLD))
        cells = {"D2": ('=COUNTIF(%s,">%d")' % (span, COUNT_THRESHOLD),
                        sum(1 for q in quantities if q > COUNT_THRESHOLD))}
    else:
        instruction = "In %s, put a formula in D2 that gives the highest Price in C2:C%d." % (SHEET_NAME, last)
        cells = {"D2": ("=MAX(C2:C%d)" % last, max(p for _, _, p in data))}
    position = "D2" if len(cells) == 1 else "D2:D%d" % last
    return kind, data, instruction, position, cells


def _padding(count):
    """``count`` incompressible-looking 1,024-character texts (sha256 chains): the p99 padding cells."""
    out, block = [], hashlib.sha256(json.dumps([SEED, TAG, "padding"]).encode()).hexdigest()
    for _ in range(count):
        parts = []
        for _ in range(16):
            block = hashlib.sha256(block.encode()).hexdigest()
            parts.append(block)
        out.append("".join(parts))
    return out


def _book(data, cells, padding):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = SHEET_NAME
    sheet.append(list(SB_HEADER))
    for row in data:
        sheet.append(list(row))
    for coordinate, (formula, _) in cells.items():
        sheet[coordinate] = formula
    if padding:
        extra = book.create_sheet(PADDING_SHEET)
        for text in padding:
            extra.append([text])
    return book


def xlsx_bytes(data, cells, padding=()):
    """The deterministic bytes of one fixture workbook: openpyxl's package with every answer formula given its cached
    value (``<v>``; the v7 scorer compares the reference cache with its recalculation), fixed document times and
    fixed zip entry times. ``cells``: {coordinate: (formula, value)}; empty for an input workbook."""
    buffer = io.BytesIO()
    _book(data, cells, padding).save(buffer)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                payload = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:)",
                                 rb"\g<1>" + DOCUMENT_TIME + rb"\g<2>", payload)
            elif info.filename == "xl/worksheets/sheet1.xml":
                for coordinate, (_, value) in cells.items():
                    pattern = re.compile(rb'(<c r="%s"[^>]*><f>[^<]*</f>)<v */>' % coordinate.encode())
                    payload, found = pattern.subn(rb"\g<1><v>" + str(value).encode() + b"</v>", payload)
                    require(found == 1, "A fixture formula cell without its cache slot: " + coordinate)
            entry = zipfile.ZipInfo(info.filename, ZIP_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(entry, payload)
    return out.getvalue()


def _padded(data, cells, target):
    """``(input bytes, answer bytes, padding rows)`` with a padding sheet making the input at least ``target``
    bytes (the reference carries the same padding, so the program's untouched content still matches it)."""
    rows = max(1, target // 600)
    while True:
        padding = _padding(rows)
        raw = xlsx_bytes(data, {}, padding)
        if len(raw) >= target:
            return raw, xlsx_bytes(data, cells, padding), rows
        rows = rows * target // len(raw) + rows // 20 + 1


def _write_once(path, payload):
    """Write ``payload`` to a new file; an existing file must hold the same bytes (write-once, identical rewrite)."""
    path = Path(path)
    if path.exists():
        require(path.read_bytes() == payload, "A fixture file differs from its earlier write: %s" % path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def spreadsheetbench_items(root, *, p99_workbook_bytes=None):
    """[(item, truth)] with the input and reference workbooks written under ``<root>/spreadsheetbench/<task id>/``
    as ``1_<task id>_input.xlsx`` / ``1_<task id>_answer.xlsx`` (the frozen loader's pair naming, datasets.py
    ``import_spreadsheetbench``); ``private.asset_sha256`` binds both files' bytes."""
    require(p99_workbook_bytes is None or (type(p99_workbook_bytes) is int and p99_workbook_bytes > 0),
            "The p99 workbook size is a positive byte count")
    root = safe_path(root)
    out = []
    for n in range(COUNT):
        kind, data, instruction, position, cells = _sheet_task(n)
        task_id = "fx-spreadsheetbench-%02d" % n
        padding_rows = 0
        if n == PADDED and p99_workbook_bytes is not None:
            raw_input, raw_answer, padding_rows = _padded(data, cells, p99_workbook_bytes)
        else:
            raw_input, raw_answer = xlsx_bytes(data, {}), xlsx_bytes(data, cells)
        folder = root / SHEET_DIR / task_id
        paths = {"input": folder / ("1_%s_input.xlsx" % task_id), "answer": folder / ("1_%s_answer.xlsx" % task_id)}
        _write_once(paths["input"], raw_input)
        _write_once(paths["answer"], raw_answer)
        files = {name: str(path.resolve()) for name, path in paths.items()}
        public = {"instruction": instruction, "input_files": [files["input"]], "answer_position": position}
        private = {"test_files": [files["answer"]], "answer_position": position,
                   "asset_sha256": {files["input"]: hashlib.sha256(raw_input).hexdigest(),
                                    files["answer"]: hashlib.sha256(raw_answer).hexdigest()}}
        truth = {"kind": kind, "sheet": SHEET_NAME, "answer_position": position,
                 "expected": {"%s!%s" % (SHEET_NAME, c): v for c, (_, v) in sorted(cells.items())},
                 "formulas": {"%s!%s" % (SHEET_NAME, c): f for c, (f, _) in sorted(cells.items())},
                 "input_bytes": len(raw_input), "answer_bytes": len(raw_answer), "padding_rows": padding_rows}
        out.append((_item("spreadsheetbench", n, public, private), truth))
    return out


# ------------------------------------------------------------------------------------------- hashes and the record
def portable(item, root):
    """The item with every workbook path taken relative to the fixture root ``root`` (its location-free form)."""
    if item["benchmark"] != "spreadsheetbench":
        return item
    root = str(safe_path(root).resolve()) + "/"

    def rel(path):
        require(path.startswith(root), "A fixture workbook outside the fixture root")
        return path[len(root):]

    public, private = item["public"], item["private"]
    return {**item, "public": {**public, "input_files": [rel(p) for p in public["input_files"]]},
            "private": {**private, "test_files": [rel(p) for p in private["test_files"]],
                        "asset_sha256": {rel(p): h for p, h in private["asset_sha256"].items()}}}


def item_sha256(item, root):
    """An item's content hash: the frozen ``data.item_hash`` of its location-free form (workbook bytes included through
    ``asset_sha256``), equal wherever the fixtures are written."""
    return item_hash(portable(item, root))


def _validated(bench, items):
    """The frozen panel validator over the items (``continual_eval.datasets.validate_panel``)."""
    tasks = [{"task_id": i["task_id"], "family_id": i["family_id"], "project_id": "", "partition": "development",
              "public": i["public"], "private": i["private"]} for i in items]
    datasets.validate_panel({"version": datasets.VERSION, "benchmark": bench, "provenance": "fixture",
                             "dataset_revision": "execskill-v1-engineering-fixtures", "tasks": tasks})


def _ranked_ids(bench, tag):
    return sorted(("fx-%s-%02d" % (bench, n) for n in range(COUNT)),
                  key=lambda task_id: hashlib.sha256(json.dumps([SEED, TAG, tag, task_id]).encode()).hexdigest())


def crash_subset():
    """The registered fx-crash subset (§10 S2): per fixture bench the ``CRASH_PER_BENCH`` task ids first in the seeded
    sha256 order of (SEED, TAG, "fx-crash", task id) -- the ``data.ranked`` rule."""
    return {bench: tuple(sorted(_ranked_ids(bench, "fx-crash")[:CRASH_PER_BENCH])) for bench in BENCHES}


FX_CRASH_SUBSET = crash_subset()


def make_fixtures(out_dir, *, p99_workbook_bytes=None):
    """Write the fixtures under ``out_dir`` (``<bench>.json`` item lists, the workbooks, ``fixtures.json``) and return
    the sealed ``fivebench-execskill-v1-fixtures`` record. Deterministic: a second call on the same directory rewrites
    identical bytes (accepted), a call elsewhere gives the same record."""
    root = safe_path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    built = {"officeqa": officeqa_items(), "livemath": livemath_items(),
             "spreadsheetbench": spreadsheetbench_items(root, p99_workbook_bytes=p99_workbook_bytes)}
    benches = {}
    for bench in BENCHES:
        items = [item for item, _ in built[bench]]
        _validated(bench, items)
        write_json(root / ("%s.json" % bench), items)
        listed = [{"task_id": item["task_id"], "sha256": item_sha256(item, root), "truth": truth}
                  for item, truth in built[bench]]
        benches[bench] = {"file": "%s.json" % bench, "count": len(items), "items": listed,
                          "set_sha256": digest([entry["sha256"] for entry in listed])}
    padded = built["spreadsheetbench"][PADDED][1]
    fields = {"registration": "fivebench-execskill-v1 §10 engineering fixtures; never evidence", "seed": SEED,
              "tag": TAG, "benches": benches, "set_sha256": digest({b: benches[b]["set_sha256"] for b in BENCHES}),
              "p99": None if p99_workbook_bytes is None else {
                  "requested_bytes": p99_workbook_bytes, "task_id": "fx-spreadsheetbench-%02d" % PADDED,
                  "input_bytes": padded["input_bytes"], "answer_bytes": padded["answer_bytes"]},
              "crash_subset": {bench: list(ids) for bench, ids in FX_CRASH_SUBSET.items()}}
    found = record("fixtures", FIXTURE, fields)
    write_json(root / RECORD_FILE, found)
    return found


def load_items(out_dir, bench):
    """The fixture items of ``bench`` as written by ``make_fixtures``."""
    require(bench in BENCHES, "A fixture bench")
    return read_json(safe_path(out_dir) / ("%s.json" % bench))


def verify(out_dir):
    """The sealed fixtures record of ``out_dir`` after recomputing every item hash, every workbook hash and the set
    hashes; ValueError on any difference."""
    root = safe_path(out_dir)
    found = verified(read_json(root / RECORD_FILE), "fixtures")
    for bench in BENCHES:
        items, listed = load_items(root, bench), found["benches"][bench]["items"]
        require([i["task_id"] for i in items] == [e["task_id"] for e in listed]
                and [item_sha256(i, root) for i in items] == [e["sha256"] for e in listed],
                "A %s fixture item differs from its sealed hash" % bench)
        for item in items:
            for path, sha in item["private"].get("asset_sha256", {}).items():
                require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, "A fixture workbook changed")
        require(digest([e["sha256"] for e in listed]) == found["benches"][bench]["set_sha256"], "Set hash mismatch")
    require(digest({b: found["benches"][b]["set_sha256"] for b in BENCHES}) == found["set_sha256"], "Set hash mismatch")
    return found


# -------------------------------------------------------------------------------------- the fixture package X (§10 S2)
FX_NOTE = '''"""Engineering fixture fx-note: lists the numbers the task text quotes."""
import re


def _text(view):
    for key in ("question", "instruction"):
        if isinstance(view.get(key), str):
            return view[key]
    return ""


def applies(view):
    return re.search(r"[0-9]", _text(view)) is not None


def before_call(view, state):
    numbers = re.findall(r"[0-9]+(?:[.][0-9]+)?", _text(view))
    if not numbers:
        return None
    line = "Numbers quoted in the task text:"
    for number in numbers:
        if len(line) + len(number) + 2 > 200:
            break
        line += (" " if line.endswith(":") else ", ") + number
    return {"facts": [line]}
'''
FX_BINDINGS = '''"""Engineering fixture fx-bindings: quotes the cells of a fiscal-year table as named values."""
import re

LABEL = "fiscal year"


def _rows(context):
    rows = []
    for line in context.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            rows.append((line, [cell.strip() for cell in line.strip("|").split("|")]))
    return rows


def applies(view):
    context = view.get("context")
    return isinstance(context, str) and any(cells[0].lower() == LABEL for _, cells in _rows(context))


def bindings(view):
    names, found = [], []
    for line, cells in _rows(view["context"]):
        if cells[0].lower() == LABEL:
            names = [re.sub(r"[^a-z0-9]+", "_", cell.lower()).strip("_") for cell in cells[1:]]
        elif names and re.fullmatch(r"[0-9]{4}", cells[0]) and len(line) <= 200:
            for name, value in zip(names, cells[1:]):
                if re.fullmatch(r"[0-9]+", value) and len(found) < 12:
                    found.append({"name": "%s_%s" % (name, cells[0]), "quote": line, "value": value})
    return {"bindings": found} if found else None
'''
FX_PRINT = '''"""Engineering fixture fx-print: draws a calendar on standard output, then counts the task text."""
import calendar


def _text(view):
    for key in ("question", "instruction"):
        if isinstance(view.get(key), str):
            return view[key]
    return None


def applies(view):
    return _text(view) is not None


def before_call(view, state):
    calendar.prmonth(2026, 10)
    return {"facts": ["Characters in the task text: %d" % len(_text(view))]}
'''
FX_CRASH_TEMPLATE = '''"""Engineering fixture fx-crash: raises on the registered fixture subset only."""
import re

REGISTERED = %s


def _text(view):
    for key in ("question", "instruction"):
        if isinstance(view.get(key), str):
            return view[key]
    return ""


def _fingerprint(text):
    value = 2166136261
    for character in text:
        value = ((value ^ ord(character)) * 16777619) %% 4294967296
    return value


def applies(view):
    return re.search(r"[0-9]", _text(view)) is not None


def before_call(view, state):
    if _fingerprint(_text(view)) in REGISTERED:
        raise RuntimeError("fx-crash: a registered fixture item")
    return None
'''
FX_SHEET_REPAIR = '''"""Engineering fixture fx-sheet-repair: describes the public workbook and asks for one repair
when the program fails on the public input."""


def applies(view):
    return isinstance(view.get("required_answer_position"), str)


def sheet_feedback(view, run_report, state):
    first = public_workbook()["sheets"][0]
    formulas = len([cell for cell in first["cells"].values() if cell["formula"]])
    warnings = ["The first sheet %s holds %d filled cells, %d of them formulas." % (
        first["name"][:40], len(first["cells"]), formulas)]
    failed = run_report.get("status") in ("exception", "missing_output")
    if failed and isinstance(run_report.get("exc_type"), str):
        warnings.append("The pre-check run stopped with %s." % run_report["exc_type"][:60])
    return {"fields": {"warnings": warnings}, "request_repair": failed}
'''
FX_ALF_TRACKER = '''"""Engineering fixture fx-alf-tracker: the D3 hand tracker as a step recorder, plus one
discouraged command (going to the place the agent already stands at)."""
import re


def _state(state):
    facts = state.get("facts") if isinstance(state, dict) else None
    if not isinstance(facts, dict):
        return [], [], 0, None
    return (list(facts.get("reached", [])), list(facts.get("carrying", [])), int(facts.get("nothing_happens", 0)),
            state.get("here"))


def _listed(prefix, names):
    line = prefix
    for name in names:
        if len(line) + len(name) + 2 > 200:
            break
        line += (" " if line.endswith(":") else ", ") + name
    return line


def applies(view):
    return isinstance(view.get("task_text"), str) and isinstance(view.get("admissible_commands_at_reset"), list)


def alf_before_step(view, state):
    reached, carrying, rejected, here = _state(state)
    facts = []
    if reached:
        facts.append(_listed("Places reached so far:", reached))
    if carrying:
        facts.append(_listed("Holding:", carrying))
    if rejected:
        facts.append("Commands the environment rejected so far: %d" % rejected)
    commands = view.get("admissible_commands")
    discourage = []
    if here is not None and isinstance(commands, list) and ("go to " + here) in commands:
        discourage.append("go to " + here)
    return {"fields": {"facts": facts}, "discourage": discourage}


def alf_after_step(event, state):
    reached, carrying, rejected, here = _state(state)
    action = str(event.get("action") or "").strip()
    observation = str(event.get("observation") or "").strip()
    moved = re.match(r"go to (.+)$", action)
    opened = re.match(r"open (.+)$", action)
    took = re.match(r"take (.+?) from (.+)$", action)
    placed = re.match(r"move (.+?) to (.+)$", action) or re.match(r"put (.+?) (?:in/on|in|on) (.+)$", action)
    if observation.startswith("Nothing happens"):
        rejected += 1
    elif moved and observation.startswith("You arrive at"):
        here = moved.group(1).strip()
        reached.append(here)
    elif opened and observation.startswith("You open"):
        reached.append(opened.group(1).strip())
    elif took and observation.startswith("You pick up"):
        carrying.append(took.group(1).strip())
    elif placed and observation.startswith(("You move", "You put")):
        thing = placed.group(1).strip()
        carrying = [held for held in carrying if held != thing]
        reached.append(placed.group(2).strip())
    facts = {"reached": sorted(set(reached)), "carrying": sorted(carrying), "nothing_happens": rejected}
    return {"facts": facts, "here": here}
'''


def fingerprint(text):
    """The fx-crash trigger's text fingerprint (32-bit FNV-1a over the characters), computed on the host exactly as the
    procedure computes it in the sandbox (no ``hash()``: PYTHONHASHSEED-free)."""
    value = 2166136261
    for character in text:
        value = ((value ^ ord(character)) * 16777619) % 4294967296
    return value


def _task_text(item):
    public = item["public"]
    return public.get("question") if "question" in public else public["instruction"]


def _registered_items():
    """The pure fixture items (no files: the SpreadsheetBench texts do not depend on the workbooks)."""
    sheets = [_item("spreadsheetbench", n, {"instruction": _sheet_task(n)[2]}, {}) for n in range(COUNT)]
    return {"officeqa": [i for i, _ in officeqa_items()], "livemath": [i for i, _ in livemath_items()],
            "spreadsheetbench": sheets}


def crash_source():
    """fx-crash's source: the fingerprints of the task texts of ``FX_CRASH_SUBSET`` as its constant."""
    items = _registered_items()
    prints = sorted(fingerprint(_task_text(i)) for bench in BENCHES for i in items[bench]
                    if i["task_id"] in FX_CRASH_SUBSET[bench])
    return FX_CRASH_TEMPLATE % json.dumps(prints)


def cell(bench, task_id):
    """The replay-trajectory cell id of one fixture item (``replay_trajectories``)."""
    return "fx/%s/%s" % (bench, task_id)


ALF_FAIL, ALF_PASS = "fx/alfworld/episode-fail", "fx/alfworld/episode-pass"


def _test(test_id, trajectory, hook, prop, *, claims_fix, mutation=None):
    return {"id": test_id, "trajectory": trajectory, "hook": hook, "property": prop, "claims_fix": claims_fix,
            "nonvacuity": {"withheld_expect": False, "mutation": mutation}}


def _first_binding():
    """(name, value) of the first binding fx-bindings quotes on OfficeQA fixture 00 (its first table row)."""
    context = officeqa_items()[0][0]["public"]["context"]
    row = [line for line in context.splitlines() if re.match(r"\| [0-9]{4} \|", line)][0]
    cells = [c.strip() for c in row.strip("|").split("|")]
    return "%s_%s" % (OQ_COLUMNS[0].lower(), cells[0]), cells[1]


def _crash_free_fail_cell():
    """The first even-numbered (token "fail") OfficeQA fixture outside the fx-crash subset."""
    return next(cell("officeqa", "fx-officeqa-%02d" % n) for n in range(0, COUNT, 2)
                if "fx-officeqa-%02d" % n not in FX_CRASH_SUBSET["officeqa"])


def fixture_package():
    """Package X of §10 S2 (``engineering_fixture``, step ``smoke/fixture-x``), in note order: fx-note, fx-bindings,
    fx-print, fx-crash, fx-sheet-repair, fx-alf-tracker."""
    name, value = _first_binding()
    oq0, lm0, sb0 = cell("officeqa", "fx-officeqa-00"), cell("livemath", "fx-livemath-00"), \
        cell("spreadsheetbench", "fx-spreadsheetbench-00")
    procedures = (
        Procedure(id="fx-note", origin="officeqa", evidence=FIXTURE, hooks=("applies", "before_call"),
                  source=FX_NOTE, max_note_chars=600,
                  description="Engineering fixture: on a QA or spreadsheet task whose text quotes a number, lists "
                              "the numbers the question or instruction quotes as one fact (a before_call note).",
                  replay_tests=(_test("rt-note-1", oq0, "before_call",
                                      {"kind": "note_contains", "value": "Numbers quoted in the task text:"},
                                      claims_fix=True),
                                _test("rt-note-2", lm0, "applies", {"kind": "applies_true"}, claims_fix=False,
                                      mutation="strip_digits"))),
        Procedure(id="fx-bindings", origin="officeqa", evidence=FIXTURE, hooks=("applies", "bindings"),
                  source=FX_BINDINGS, max_note_chars=1500, requests_second_call=True,
                  description="Engineering fixture: on a page with a fiscal-year table, quotes up to 12 table cells "
                              "as named values (bindings) so the shell offers the exact <calc> round trip (§2.4).",
                  replay_tests=(_test("rt-bind-1", oq0, "bindings",
                                      {"kind": "binding_equals", "name": name, "value": value}, claims_fix=True),)),
        Procedure(id="fx-print", origin="officeqa", evidence=FIXTURE, hooks=("applies", "before_call"),
                  source=FX_PRINT, max_note_chars=600,
                  description="Engineering fixture: prints a calendar to standard output (which the sandbox discards) "
                              "and notes the length of the task text; it must never fault.",
                  replay_tests=(_test("rt-print-1", oq0, "before_call",
                                      {"kind": "note_contains", "value": "Characters in the task text:"},
                                      claims_fix=True),)),
        Procedure(id="fx-crash", origin="officeqa", evidence=FIXTURE, hooks=("applies", "before_call"),
                  source=crash_source(), max_note_chars=600,
                  description="Engineering fixture: raises inside before_call on the registered subset of fixture "
                              "items (FX_CRASH_SUBSET, chosen by seeded item hash) and shows nothing elsewhere; its "
                              "faults must appear on exactly those items and never pause a unit.",
                  replay_tests=(_test("rt-crash-1", _crash_free_fail_cell(), "applies", {"kind": "applies_true"},
                                      claims_fix=True, mutation="strip_digits"),)),
        Procedure(id="fx-sheet-repair", origin="spreadsheetbench", evidence=FIXTURE,
                  hooks=("applies", "sheet_feedback"), source=FX_SHEET_REPAIR, max_note_chars=600,
                  requests_second_call=True,
                  description="Engineering fixture: after the pre-check, describes the first sheet of the public "
                              "workbook and requests the one repair call when the program failed on the public input.",
                  replay_tests=(_test("rt-sheet-1", sb0, "sheet_feedback", {"kind": "repair_requested", "value": True},
                                      claims_fix=True, mutation="program_ok"),)),
        Procedure(id="fx-alf-tracker", origin="alfworld", evidence=FIXTURE,
                  hooks=("applies", "alf_before_step", "alf_after_step"), source=FX_ALF_TRACKER,
                  max_note_chars=1200, state_bytes=4096,
                  description="Engineering fixture: the D3 hand tracker ported as a recorder (places reached, objects "
                              "held, rejected commands) shown each step, plus one discouraged command: going to the "
                              "place the agent already stands at.",
                  replay_tests=(_test("rt-alf-1", ALF_FAIL, "alf_before_step",
                                      {"kind": "discourage_contains", "value": ALF_EPISODE[1][1], "step": 1},
                                      claims_fix=True),
                                _test("rt-alf-2", ALF_FAIL, "alf_after_step",
                                      {"kind": "state_equals", "key": "facts", "step": 2,
                                       "value": {"reached": ["drawer 1"], "carrying": [], "nothing_happens": 1}},
                                      claims_fix=False))),
    )
    return Package(procedures, STEP, FIXTURE)


def fixture_placebo(items, *, unit, package=None):
    """P of §10 S2 for ``items`` (pool items of any smoke bench): ``{task id: {"procedures": {id: sham}}}``, the shape
    ``placebo.arm`` reads. Every note hook of X shows ``PLACEBO_FACTS`` facts of the item's registered irrelevant text
    (``placebo.irrelevant_text(task id, unit)``, v3's eight control texts); ``alf_before_step`` one such entry with
    one discouraged command drawn at dispatch. The yoked P_y is not built: its donor corpus is the parent's sealed
    run-slice trajectories, which only a real run has."""
    package = package or fixture_package()
    out = {}
    for item in items:
        facts = placebos.chunks(placebos.irrelevant_text(item["task_id"], unit), PLACEBO_FACTS)
        content = {}
        for procedure in package.procedures:
            sham = {hook: {"facts": list(facts)} for hook in procedure.hooks if hook in NOTE_HOOKS
                    and hook != "alf_before_step"}
            if "alf_before_step" in procedure.hooks:
                sham["alf_before_step"] = [{"fields": {"facts": list(facts)}, "discourage": 1}]
            if sham:
                content[procedure.id] = sham
        out[item["task_id"]] = {"procedures": content}
    return out


# ------------------------------------------------------------------------------- replay trajectories of package X
ALF_INITIAL = ("-= Welcome to TextWorld, ALFRED! =-\n\nYou are in the middle of a room. Looking quickly around you, "
               "you see a cabinet 1, a countertop 1, a drawer 1, and a fridge 1.\n\nYour task is to: put a cool "
               "apple in countertop.")
ALF_ADMISSIBLE = ["go to cabinet 1", "go to countertop 1", "go to drawer 1", "go to fridge 1", "open drawer 1",
                  "take apple 1 from drawer 1", "cool apple 1 with fridge 1", "move apple 1 to countertop 1",
                  "inventory", "look"]
ALF_EPISODE = (  # (observation seen, action, observation after): a synthetic engineering-fixture episode
    (ALF_INITIAL, "go to drawer 1", "You arrive at drawer 1. The drawer 1 is closed."),
    ("You arrive at drawer 1. The drawer 1 is closed.", "go to drawer 1", "Nothing happens."),
    ("Nothing happens.", "open drawer 1", "You open the drawer 1. The drawer 1 is open. In it, you see a apple 1."),
    ("You open the drawer 1. The drawer 1 is open. In it, you see a apple 1.", "take apple 1 from drawer 1",
     "You pick up the apple 1 from the drawer 1."),
    ("You pick up the apple 1 from the drawer 1.", "go to fridge 1", "You arrive at fridge 1. The fridge 1 is closed."),
    ("You arrive at fridge 1. The fridge 1 is closed.", "cool apple 1 with fridge 1",
     "You cool the apple 1 using the fridge 1."),
    ("You cool the apple 1 using the fridge 1.", "go to countertop 1",
     "You arrive at countertop 1. On the countertop 1, you see nothing."),
    ("You arrive at countertop 1. On the countertop 1, you see nothing.", "move apple 1 to countertop 1",
     "You move the apple 1 to the countertop 1."),
)


def _trajectory(cell_id, bench, task_id, token, users, *, steps=None, report=None):
    """A sealed engineering-fixture trajectory with the whitelisted keys (``trajectories.TOP``)."""
    purpose = "step" if bench == "alfworld" else "first"
    zero = "0" * 64
    calls = [{"purpose": purpose, "system": "fixture system prompt", "user": json.dumps(user, ensure_ascii=False),
              "request_sha256": zero, "receipt": {"delivery": "delivered"}} for user in users]
    return record("trajectory", FIXTURE, {
        "cell": cell_id, "unit": "smoke/fixture-replay", "arm": "S", "arm_kind": "parent", "bench": bench,
        "task_id": task_id, "run": 1, "package_sha256": zero, "route": None, "calls": calls,
        "replies": [None] * len(calls), "deciding_receipt": None, "worst_delivery": None,
        "logical_calls": len(calls), "shell": {"notes": [], "compute": None, "precheck": report,
                                               "procedure_calls": [], "faults": [], "fallback": None},
        "alfworld_steps": steps, "judge": {"v2": {"token": token}}, "token": token, "dispatch_ts": 0,
        "finish_ts": 0})


def _alf_trajectory(cell_id, token, episode):
    users = [{"initial_observation": ALF_INITIAL, "observation": seen, "admissible_commands": ALF_ADMISSIBLE,
              "recent_history": []} for seen, _, _ in episode]
    steps = [{"i": i, "view_sha256": "0" * 64, "observation": seen, "notes": "", "discouraged": [], "reply": action,
              "action": action, "how": "tag_exact", "post_observation": after, "state_sha256": {}}
             for i, (seen, action, after) in enumerate(episode)]
    return _trajectory(cell_id, "alfworld", cell_id.rsplit("/", 1)[1], token, users, steps=steps)


def replay_trajectories(out_dir):
    """{cell: sealed trajectory} the replay tests of package X name: every fixture item as a first request showing its
    routing view (token "fail" on even, "pass" on odd numbers; SpreadsheetBench with a stored pre-check report, an
    exception on the failed ones), and two synthetic ALFWorld episodes (failed: the fixture episode; passed: the same
    episode without its idle step)."""
    out = {}
    for bench in BENCHES:
        for number, item in enumerate(load_items(out_dir, bench)):
            token = "fail" if number % 2 == 0 else "pass"
            view = routing_view(bench, item["public"], runtime=SHEET_RUNTIME)
            report = None
            if bench == "spreadsheetbench":
                report = (precheck.report("exception", evidence=FIXTURE, exc_type="KeyError",
                                          message="KeyError: 'Total'") if token == "fail"
                          else precheck.report("ok", evidence=FIXTURE))
            identifier = cell(bench, item["task_id"])
            out[identifier] = _trajectory(identifier, bench, item["task_id"], token, [view], report=report)
    out[ALF_FAIL] = _alf_trajectory(ALF_FAIL, "fail", ALF_EPISODE)
    direct = ALF_EPISODE[:1] + ((ALF_EPISODE[0][2],) + ALF_EPISODE[2][1:],) + ALF_EPISODE[3:]
    out[ALF_PASS] = _alf_trajectory(ALF_PASS, "pass", direct)
    return out


def public_input_dirs(out_dir, scratch):
    """{cell: directory} holding each SpreadsheetBench fixture's public workbook alone as ``input.xlsx`` (the
    sandbox's read-only /input mount, ``sandbox.client.Worker.start``), made under ``scratch``."""
    out = {}
    for item in load_items(out_dir, "spreadsheetbench"):
        directory = safe_path(scratch) / item["task_id"]
        directory.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(item["public"]["input_files"][0], directory / "input.xlsx")
        out[cell("spreadsheetbench", item["task_id"])] = directory.resolve()
    return out


# ---------------------------------------------------------------------------------------- the S0 sandbox suite
SUITE_SOURCES = {
    "fx-sbx-crash": ('def before_call(view, state):\n    return {"facts": [str(1 / 0)]}\n', "before_call"),
    "fx-sbx-loop": ("def before_call(view, state):\n    total = 0\n    while True:\n        total += 1\n",
                    "before_call"),
    "fx-sbx-memory": ('def before_call(view, state):\n    block = bytearray(2 << 30)\n'
                      '    return {"facts": [str(len(block))]}\n', "before_call"),
    "fx-sbx-nan": ('def before_call(view, state):\n    return {"facts": [], "x": float("nan")}\n', "before_call"),
    "fx-sbx-oversized": ('def before_call(view, state):\n    return {"facts": ["x" * (2 << 20)]}\n', "before_call"),
    "fx-sbx-print": ('import calendar\n\n\ndef before_call(view, state):\n    calendar.prmonth(2026, 10)\n'
                     '    return {"facts": ["printed"]}\n', "before_call"),
    "fx-sbx-module-loop": ("def _never(count=sum(1 for _ in iter(int, 1))):\n    return count\n\n\n"
                           "def applies(view):\n    return True\n", "applies"),
    "fx-sbx-nested": ("def before_call(view, state):\n    value = []\n    for _ in range(40):\n"
                      "        value = [value]\n    return {\"facts\": [], \"state\": value}\n", "before_call"),
    "fx-sbx-killed-child": ("def before_call(view, state):\n    total = 0\n    while True:\n        total += 1\n",
                            "before_call"),
    "fx-sbx-worker-kill": ("def before_call(view, state):\n    total = 0\n    while True:\n        total += 1\n",
                           "before_call"),
    "fx-sbx-banned": ("import os\n\n\ndef applies(view):\n    return True\n", "applies"),
    "fx-sbx-workbook": ('def before_call(view, state):\n    book = public_workbook()\n'
                        '    return {"facts": ["sheets: %d" % len(book["sheets"]),\n'
                        '                      "cells: %d" % sum(len(s["cells"]) for s in book["sheets"])]}\n',
                        "before_call"),
    "fx-sbx-healthy": ('def applies(view):\n    return True\n', "applies"),
}
# id -> (expected class, worker fault, the external action the driver performs during the call, timeout seconds)
SUITE_EXPECTED = {
    "fx-sbx-crash": ("procedure_fault", "exception", None, 5),
    "fx-sbx-loop": ("procedure_fault", "timeout", None, 2),
    "fx-sbx-memory": ("procedure_fault", "memory", None, 5),
    "fx-sbx-nan": ("procedure_fault", "output", None, 5),
    "fx-sbx-oversized": ("procedure_fault", "over_cap", None, 10),
    "fx-sbx-print": ("no_fault", None, None, 5),
    "fx-sbx-module-loop": ("procedure_fault", "timeout", None, 2),
    "fx-sbx-nested": ("procedure_fault", "over_cap", None, 5),
    "fx-sbx-killed-child": ("procedure_fault", "killed", "kill_child", 60),
    "fx-sbx-worker-kill": ("procedure_fault", "worker", "kill_worker", 60),
    "fx-sbx-banned": ("procedure_fault", "not_loaded", None, 2),
    "fx-sbx-workbook": ("no_fault", None, None, 5),
}
HEALTHY = "fx-sbx-healthy"


def sandbox_suite():
    """The S0 sandbox suite (§10 S0 sandbox row; plan T-SBX): ``(bundle, cases)``. ``bundle`` loads into one cell
    worker (``generators.families.bundle``: the banned procedure is refused at load, as the policy says); each case
    is {id, fn, args, timeout_s, action, inputs, expected: {class, fault}}: ``action`` the driver's external kill
    during the call (``kill_child``: the call's child; ``kill_worker``: the container's processes), ``inputs``
    "p99" for the case reading the p99-padded public workbook (mount ``public_input_dirs`` of the padded fixture).
    After every case the healthy probe ``HEALTHY`` must answer: the cell completes, a fault never pauses. Printing is
    harmless by design (fds 0/1/2 of every call child are /dev/null, plan §4), so its expected class is
    ``no_fault`` with the value intact."""
    entries = [Entry(pid, source, (fn,)) for pid, (source, fn) in SUITE_SOURCES.items()]
    cases = []
    for pid, (expected, fault, action, timeout) in SUITE_EXPECTED.items():
        fn = SUITE_SOURCES[pid][1]
        args = [{"text": "fixture view"}] if fn == "applies" else [{"text": "fixture view"}, None]
        cases.append({"id": pid, "fn": fn, "args": args, "timeout_s": timeout, "action": action,
                      "inputs": "p99" if pid == "fx-sbx-workbook" else None,
                      "expected": {"class": expected, "fault": fault}})
    return bundle(entries), cases


def _outcome(result):
    return result.get("value_sha256") if result.get("ok") is True else "fault:%s" % result.get("fault")


def determinism_hashes(worker, package, views, *, reverse=False):
    """The S0 two-seed determinism check's run (§2.6, §10 S0 determinism row): {"<bench>/<k>/<procedure>/<fn>": value
    sha256 or "fault:<kind>"} of what the shell runs first on each of ``views`` ({bench: [routing view]}) -- every
    predicate, then, where it holds, ``before_call``/``bindings`` (QA, SpreadsheetBench) or ``alf_before_step`` with
    no state (ALFWorld) -- through a started ``worker`` holding ``package``, the views in order or ``reverse``d. Two
    workers (PYTHONHASHSEED 0 and 1) in the two orders must give equal mappings."""
    jobs = [(bench, k, view) for bench, listed in sorted(views.items()) for k, view in enumerate(listed)]
    out = {}
    for bench, k, view in (jobs[::-1] if reverse else jobs):
        hooks = ("alf_before_step",) if bench == "alfworld" else ("before_call", "bindings")
        for procedure in package.for_bench(bench):
            key = "%s/%d/%s/" % (bench, k, procedure.id)
            result = worker.call(procedure.id, "applies", [view], timeout_s=SANDBOX_TIMEOUTS["predicate"])
            out[key + "applies"] = _outcome(result)
            if result.get("ok") is not True or result.get("value") is not True:
                continue
            for hook in (h for h in hooks if h in procedure.hooks):
                args = [view] if hook == "bindings" else [view, None]
                out[key + hook] = _outcome(worker.call(procedure.id, hook, args, timeout_s=SANDBOX_TIMEOUTS["hook"]))
    return out


# ------------------------------------------------------------------------------------------------------------ CLI
def add_arguments(subparsers):
    """The ``make-fixtures`` subcommand of scripts/run_execskill.py."""
    command = subparsers.add_parser("make-fixtures", help="write the registrar's engineering fixtures (§10)")
    command.add_argument("--out", required=True)
    command.add_argument("--p99-workbook-bytes", type=int, default=None)
    return command


def make_fixtures_cli(args):
    """``make-fixtures --out DIR [--p99-workbook-bytes N]``: writes the fixtures and prints counts and hashes."""
    found = make_fixtures(args.out, p99_workbook_bytes=args.p99_workbook_bytes)
    summary = {"record": str(safe_path(args.out) / RECORD_FILE), "record_sha256": found[RECORD_HASH],
               "set_sha256": found["set_sha256"], "counts": {b: found["benches"][b]["count"] for b in BENCHES},
               "p99": found["p99"], "crash_subset": found["crash_subset"],
               "package_sha256": fixture_package().sha256}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0
