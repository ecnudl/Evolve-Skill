"""T-GEN-1..6: the registrar-defined transformation families (registration §7.2 after Codex F8, §21 owner rule (b);
plan generators row) with fixed reference functions, the fixed LiveMath checker faked in process (sympy exists only
in the pinned image) and once through the real sandbox client and worker (FakeDocker), the recalculation engine and
the engine qualification faked (zero calls, offline). The fake recalculation keeps every formula and writes its value
as the formula's cache, as Calc's export does (``recalculated``; ticket PR-C61-2, whose regression tests run the real
frozen scorer path: tests/test_execskill_sheet_generated.py)."""
from __future__ import annotations

import ast
import base64
import hashlib
import io
import math
import operator
import re
import zipfile
from contextlib import contextmanager
from decimal import Decimal, localcontext
from fractions import Fraction

import openpyxl
import pytest

from skillopt.execskill import compute, policy, research
from skillopt.execskill import generators as gen
from skillopt.execskill.generators import alfworld_select, livemath, officeqa, sheet
from skillopt.execskill.generators.families import Drop, check
from skillopt.execskill.protocol import MAX_ITEMS_PER_FINDING, verified
from skillopt.execskill.sandbox.client import KINDS, Limits, Worker
from tests.execskill_fakes_docker import FakeDocker
from tests.fixtures.execskill.items import alfworld_games, spreadsheetbench_items

EVIDENCE = "engineering_fixture"
ROWS = [["Year", "Income tax", "Customs", "Total"], ["2019", "1,718", "71", "1,789"],
        ["2020", "1,609", "68", "1,677"], ["2021", "2,044", "80", "2,124"]]
LIMITS = {kind: Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
          for kind in KINDS}  # the host-side fixture limits of the other sandbox tests
QUOTE = ("In mathematics, the derivative is a fundamental tool that quantifies the sensitivity to change of a "
         "function's output with respect to its input.")


def _table():
    return research.material({"purpose": "table", "status": "found", "source": {"title": "Government revenue",
                                                                                 "revid": 1001},
                              "table": {"page": "P1", "archive": "a" * 64, "index": 0,
                                        "caption": "Receipts by year (billions)", "rows": ROWS}})


def _definition(quote=QUOTE, title="Derivative"):
    return research.material({"purpose": "definition", "status": "found", "quote": quote, "page": "P1",
                              "archive": "b" * 64, "source": {"title": title, "revid": 7}})


def _function(name, quote):
    return research.material({"purpose": "function", "status": "found", "subject": name, "conclusion": name,
                              "quotes": [{"page": "P1", "archive": "c" * 64, "title": "Calc " + name, "revid": None,
                                          "text": quote}]})


def _generate(family, params, material, **context):
    return gen.generate(family, params, material, generator="g-test-1", set_name="G_self", seed=11,
                        evidence=EVIDENCE, **context)


# --------------------------------------------------------------------------------------------------- T-GEN-1
def test_gen1_officeqa_answers_recomputed_from_the_perturbed_cells():
    family = gen.family("officeqa.percent_change")
    params = {"cells": [[1, 1], [3, 1]], "decimals": 2, "perturb": [{"cell": [3, 1], "percent": 10}]}
    made = _generate(family, [params], _table())
    item = verified(made["items"][0], "generated-item")
    truth = item["private"]["truth"]
    assert item["public"]["context"].count("2,248") == 1 and "2,044" not in item["public"]["context"]
    assert item["private"]["answer"] == compute.rounded(Fraction(100 * (2248 - 1718), 1718), 2) == "30.85"
    assert truth["original"] == compute.render(Fraction(100 * (2044 - 1718), 1718))  # reproduced first
    assert truth["kind"] == "family_reference" and truth["perturbed"] == {"3,1": 10}
    assert 'row "2019", column "Income tax"' in item["public"]["question"] and item["source_item"] is None
    difference = _generate(gen.family("officeqa.difference"), [{"cells": [[1, 1], [2, 1]], "decimals": 0}], _table())
    assert difference["items"][0]["private"]["answer"] == "-109"


def test_gen1_officeqa_drops_by_reason_and_rejects_an_answer_field():
    sets = [{"cells": [[1, 1], [1, 2]], "decimals": 0},  # 1,718 + 71 = 1,789: the Total cell holds the answer
            {"cells": [[1, 1], [1, 2]], "decimals": 0, "answer": "1789"},  # the examiner may not give an answer
            {"cells": [[0, 1], [1, 1]], "decimals": 0},  # a header cell
            {"cells": [[1, 0], [1, 1]], "decimals": 0},  # a label cell
            {"cells": [[1, 1], [2, 1]], "decimals": 5}]  # rounding outside 0-4
    made = _generate(gen.family("officeqa.sum"), sets, _table())
    assert made["items"] == [] and made["dropped"] == {"answer_in_context": 1, "format": 4}
    with pytest.raises(Drop, match="perturbed cell"):
        officeqa.apply(gen.family("officeqa.ratio"), {"cells": [[1, 1], [2, 1]], "decimals": 2,
                                                      "perturb": [{"cell": [3, 2], "percent": 5}]}, _table())


# --------------------------------------------------------------------------------------------------- T-GEN-2
def _poly(expression):
    """{power: coefficient} of a ``livemath.polynomial`` text (the fake checker's own parse)."""
    terms, sign = {}, 1
    for token in expression.split():
        if token in "+-":
            sign = -1 if token == "-" else 1
            continue
        if token.startswith("-"):
            sign, token = -1, token[1:]
        if "x" in token:
            size, _, power = token.partition("x")
            coefficient, exponent = int(size.rstrip("*") or 1), int(power[1:]) if power else 1
        else:
            coefficient, exponent = int(token), 0
        terms[exponent] = sign * coefficient
        sign = 1
    return terms


def _digits(value):
    with localcontext() as context:
        context.prec = 50
        return str(Decimal(value.numerator) / Decimal(value.denominator))


class FakeChecker:
    """The fixed checker's contract, solved exactly in process: ``override`` replaces the next Result."""

    def __init__(self, override=None):
        self.specs, self.override = [], override

    def solve(self, spec):
        self.specs.append(spec)
        if self.override is not None:
            return self.override
        if spec["op"] == "derivative":
            k, at = int(spec["order"]), Fraction(spec["at"])
            value = sum(c * math.perm(p, k) * at ** (p - k) for p, c in _poly(spec["expression"]).items() if p >= k)
        elif spec["op"] == "integral":
            a, b = Fraction(spec["lower"]), Fraction(spec["upper"])
            value = sum(Fraction(c, p + 1) * (b ** (p + 1) - a ** (p + 1)) for p, c in _poly(spec["expression"]).items())
        elif spec["op"] == "binomial":
            value = Fraction(math.comb(int(spec["n"]), int(spec["k"])))
        else:
            value = sum(int(spec["first"]) * Fraction(spec["ratio"]) ** i for i in range(int(spec["terms"])))
        value = Fraction(value)
        exact = str(value.numerator) if value.denominator == 1 else "%d/%d" % (value.numerator, value.denominator)
        return {"ok": True, "value": {"exact": exact, "digits": _digits(value)}}


def test_gen2_livemath_fixed_checker_single_matching_option_and_key_rotation():
    family = gen.family("livemath.derivative")
    assert livemath.polynomial([3, 0, -1]) == "3*x^2 - 1" and livemath.polynomial([-1, 2, 0]) == "-x^2 + 2*x"
    checker = FakeChecker()
    sets = [{"coefficients": [3, 0, -1], "at": n % 5 - 2, "order": 1} for n in range(10)]
    made = _generate(family, sets, _definition(), checker=checker)
    letters = []
    for n, item in enumerate(made["items"]):
        options = item["public"]["choices"].split("\n\n")
        truth = Fraction(item["private"]["truth"]["exact"])
        assert truth == 6 * (n % 5 - 2) and item["private"]["truth"]["spec"]["expression"] == "3*x^2 - 1"
        assert sum(1 for o in options if Fraction(o[3:]) == truth) == 1 and len(set(options)) == 5
        assert item["private"]["answer"] == "ABCDE"[n % 5] and item["public"]["question"].startswith("Background")
        letters.append(item["private"]["answer"])
    assert {letter: letters.count(letter) for letter in "ABCDE"} == dict.fromkeys("ABCDE", 2)
    integral = _generate(gen.family("livemath.integral"), [{"coefficients": [1, 0], "lower": 0, "upper": 3}],
                         _definition("The integral of a function is the signed area under its graph."),
                         checker=FakeChecker())
    assert integral["items"][0]["private"]["truth"]["exact"] == "9/2"


def test_gen2_livemath_drops_meta_option_mismatch_and_unsolved_instances():
    family, sets = gen.family("livemath.derivative"), [{"coefficients": [1, 1], "at": 1, "order": 1}]
    meta = _definition(QUOTE + " One of the remaining options is correct, but a stronger result can be proven.")
    assert _generate(family, sets, meta, checker=FakeChecker())["dropped"] == {"meta_option": 1}
    assert _generate(gen.family("livemath.binomial"), [{"n": 5, "k": 2}], _definition(),
                     checker=FakeChecker())["dropped"] == {"material_mismatch": 1}
    faults = [{"ok": False, "fault": "exception", "exc_type": "RuntimeError", "message": "no sympy", "line": 9},
              {"ok": True, "value": {"exact": None, "digits": "1.4142135623730950488016887242096980785696718753769"}},
              {"ok": True, "value": {"exact": "3", "digits": "3.5"}}]
    for fault in faults:
        assert _generate(family, sets, _definition(), checker=FakeChecker(fault))["dropped"] == {
            "reference_fn_failed": 1}
    wrong = [{"coefficients": [1, 1], "at": 1, "order": 1, "answer": "B"}, {"n": 3, "k": 5}]
    assert _generate(family, wrong[:1], _definition(), checker=FakeChecker())["dropped"] == {"format": 1}
    binomial = _definition("The binomial coefficient counts the ways to choose k elements of a set of n.")
    assert _generate(gen.family("livemath.binomial"), wrong[1:], binomial,
                     checker=FakeChecker())["dropped"] == {"format": 1}


def test_gen2_the_real_checker_passes_the_policy_and_runs_through_the_sandbox(tmp_path):
    assert policy.check(livemath.CHECKER_SOURCE) == []
    docker = FakeDocker(tmp_path / "containers")
    worker = Worker(docker=docker, limits=LIMITS, scratch=tmp_path)
    try:
        checker = livemath.SandboxChecker(worker)
        result = checker.solve({"op": "binomial", "n": "5", "k": "2"})
        # the host has no sympy: the checker's import fails, which is the call's fault, never a crash of the run
        assert result["ok"] is False and result["fault"] == "exception"
        assert result["exc_type"] in ("ModuleNotFoundError", "ImportError")
        made = _generate(gen.family("livemath.binomial"), [{"n": 5, "k": 2}],
                         _definition("The binomial coefficient counts subsets."), checker=checker)
        assert made["dropped"] == {"reference_fn_failed": 1} and made["items"] == []
    finally:
        worker.close()
        docker.close()


# --------------------------------------------------------------------------------------------------- T-GEN-3
def _evaluate(formula, cells):
    """A test-only evaluator of the fixture formulas: SUM over a range, ROUND, + - * / and cell references."""
    def literal(number):
        number = Fraction(number)
        return "(%d/%d)" % (number.numerator, number.denominator)

    def cell_range(match):
        low, high = match.group(1), match.group(2)
        column, first, last = low[0], int(low[1:]), int(high[1:])
        return literal(sum(cells[column + str(row)] for row in range(first, last + 1)))
    text = re.sub(r"SUM\(([A-Z]\d+):([A-Z]\d+)\)", cell_range, formula[1:])
    text = re.sub(r"\b([A-Z]\d+)\b", lambda m: literal(cells[m.group(1)]), text).replace("ROUND", "rnd")
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def value(node):
        if isinstance(node, ast.Expression):
            return value(node.body)
        if isinstance(node, ast.Constant):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -value(node.operand)
        if isinstance(node, ast.BinOp):
            return operators[type(node.op)](value(node.left), value(node.right))
        if isinstance(node, ast.Call):  # rnd(x, places): half away from zero
            x, places = value(node.args[0]), int(value(node.args[1]))
            return Fraction(compute.rounded(x, places))
        raise AssertionError("unsupported fixture formula")
    return value(ast.parse(text, mode="eval"))


def recalculated(path, *, caches=True):
    """A test-only recalculation of a fixture workbook (its first sheet, ``_evaluate``): the workbook's bytes with every
    formula kept and its value written as the formula's cache (``<v>``), as Calc's export does -- the frozen v7 scorer
    compares a reference's caches with its own recalculation; ``caches=False``: the formulas without caches, as
    openpyxl's save leaves them. None when a formula cannot be evaluated."""
    book = openpyxl.load_workbook(path)
    sheet_ = book[book.sheetnames[0]]
    cells = {c.coordinate: c.value for row in sheet_.iter_rows() for c in row if c.value is not None}
    pending = {k: v for k, v in cells.items() if isinstance(v, str) and v.startswith("=")}
    formulas = sorted(pending)
    while pending:
        progress = False
        for coordinate, formula in list(pending.items()):
            try:
                cells[coordinate] = _evaluate(formula, {k: v for k, v in cells.items() if k not in pending})
            except KeyError:
                continue
            del pending[coordinate]
            progress = True
        if not progress:
            return None
    buffer = io.BytesIO()
    book.save(buffer)  # every formula keeps an empty cache slot: <c r=".."><f>..</f><v /></c>
    if not caches:
        return buffer.getvalue()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                for coordinate in formulas:
                    value = cells[coordinate]
                    text = repr(int(value) if value.denominator == 1 else float(value)).encode()
                    payload, found = re.subn(rb'(<c r="%s"[^>]*><f>[^<]*</f>)<v */>' % coordinate.encode(),
                                             rb"\g<1><v>" + text + b"</v>", payload)
                    assert found == 1, coordinate
            target.writestr(info, payload)
    return out.getvalue()


class FakeEngine:
    """The recalculation engine and the engine qualification of the sheet family, faked; ``log`` keeps their order,
    ``sent`` the names of the workbooks recalculated. A recalculation is ``recalculated`` in a receipt bound to the
    bytes sent and to its output; ``fail_at``: the recalculations (counted from 0) that come back unavailable;
    ``patch``: receipt fields overwritten."""

    def __init__(self, *, recalc_status="available", qualified=True, fail_at=(), patch=None):
        self.recalc_status, self.qualified, self.log, self.held = recalc_status, qualified, [], 0
        self.fail_at, self.patch, self.sent = set(fail_at), dict(patch or {}), []

    @contextmanager
    def hold(self):  # the native slot the frozen qualification holds around each scoring
        self.held += 1
        yield

    def recalc(self, path):
        self.log.append("recalc")
        self.sent.append(path.name)
        failing = self.recalc_status != "available" or len(self.sent) - 1 in self.fail_at
        raw = None if failing else recalculated(path)
        if raw is None:
            return {"status": "unknown", "reason": "recalculation_execution_error"}
        return {"status": "available", "reason": "independently_recalculated",
                "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "output_base64": base64.b64encode(raw).decode(), "output_sha256": hashlib.sha256(raw).hexdigest(),
                **self.patch}

    def qualify(self, tasks, root, runtime, *, side, native, workers):
        self.log.append("qualify")
        assert side == "train" and workers == 1 and runtime == {"spreadsheet_scorer": "qualified_lo_recalc_v7_v1"}
        for _ in range(2):  # two scorings, each under the native slot (coevo5/qualify.py:97-111)
            with native.hold():
                pass
        return {"qualified": [t["task_id"] for t in tasks] if self.qualified else [], "scorings_per_item": 2}

    def engine(self):
        return sheet.Engine(recalc=self.recalc, qualify=self.qualify,
                            runtime={"spreadsheet_scorer": "qualified_lo_recalc_v7_v1"}, native=self)


def _sheet_item(root, formula_answer=True):
    item = spreadsheetbench_items(root, count=1)[0]
    if formula_answer:  # the reference's answer cell becomes the formula the instruction describes
        path = item["private"]["test_files"][0]
        book = openpyxl.load_workbook(path)
        book.active["B1"] = "=SUM(A1:A5)"
        book.save(path)
    return item


def _functions():
    return sheet.function_set([_function("ROUND", "Syntax: ROUND(Number [; Count])"),
                               _function("SUM", "Syntax: SUM(Number 1[; Number 2])")])


def test_gen3_sheet_truth_by_recalculation_then_a_separate_engine_qualification(tmp_path):
    fake, item = FakeEngine(), _sheet_item(tmp_path / "items")
    edits = {"edits": [{"cell": "A3", "formula": "=ROUND(A2*2.5,0)"}]}  # A2 = 2: the new A3 is 5
    made = _generate(sheet.FAMILY, [edits], _functions(), source_items=[item], engine=fake.engine(),
                     out_dir=tmp_path / "generated")
    generated = verified(made["items"][0], "generated-item")
    truth = generated["private"]["truth"]
    assert truth["kind"] == "recalc_formula" and truth["edited_values"] == {"Sheet!A3": 5}
    assert truth["expected_cells"] == {"Sheet!B1": 17} and fake.log == ["recalc"] * 3 + ["qualify"] and fake.held == 2
    # the edited reference (truth), then the generated input and reference (their caches; ticket PR-C61-2)
    assert fake.sent == ["edited-reference.xlsx", "literal-input.xlsx", "literal-answer.xlsx"]
    assert generated["private"]["engine_qualification"]["ok"] is True and generated["source_item"] == item["task_id"]
    given = openpyxl.load_workbook(generated["public"]["input_files"][0]).active
    reference = openpyxl.load_workbook(generated["private"]["test_files"][0]).active
    assert given["A3"].value == 5 and reference["A3"].value == 5 and reference["B1"].value == "=SUM(A1:A5)"
    assert set(generated["private"]["asset_sha256"]) == {generated["public"]["input_files"][0],
                                                         generated["private"]["test_files"][0]}
    assert generated["private"]["answer_position"] == "B1" and "answer" not in generated["private"]


def test_gen3_sheet_drops_by_reason(tmp_path):
    cases = [
        ({"edits": [{"cell": "A3", "formula": "=A2*3"}]}, "function_not_researched"),
        ({"edits": [{"cell": "A3", "formula": "=ROUND(RAND()*9,0)"}]}, "forbidden_function"),
        ({"edits": [{"cell": "B1", "formula": "=ROUND(A2*3,0)"}]}, "edit_target_invalid"),
        ({"edits": [{"cell": "A3", "formula": "=ROUND(A3*3,0)"}]}, "edit_target_invalid"),
        ({"edits": [{"cell": "A3", "formula": "=ROUND(A2*1.5,0)"}]}, "perturbation_noop"),
        ({"edits": [{"cell": "A3", "formula": "=ROUND(A2*3,0)"}], "answer": 17}, "format"),
    ]
    for n, (edits, reason) in enumerate(cases):
        item = _sheet_item(tmp_path / ("items-%d" % n))
        made = _generate(sheet.FAMILY, [edits], _functions(), source_items=[item], engine=FakeEngine().engine(),
                         out_dir=tmp_path / ("out-%d" % n))
        assert made["dropped"] == {reason: 1}, (edits, made["dropped"])
    literal = _sheet_item(tmp_path / "literal", formula_answer=False)  # the fixture's B1 holds a literal sum
    made = _generate(sheet.FAMILY, [{"edits": [{"cell": "A3", "formula": "=ROUND(A2*3,0)"}]}], _functions(),
                     source_items=[literal], engine=FakeEngine().engine(), out_dir=tmp_path / "out-literal")
    assert made["dropped"] == {"literal_answer": 1}
    for fake, reason in ((FakeEngine(recalc_status="unknown"), "recalc_failed"),
                         (FakeEngine(qualified=False), "engine_qualification_failed")):
        made = _generate(sheet.FAMILY, [{"edits": [{"cell": "A3", "formula": "=ROUND(A2*3,0)"}]}], _functions(),
                         source_items=[_sheet_item(tmp_path / reason)], engine=fake.engine(),
                         out_dir=tmp_path / ("out-" + reason))
        assert made["dropped"] == {reason: 1}


def test_gen3_a_dropped_sheet_item_leaves_no_folder_for_the_next_parameter_set(tmp_path):
    """Integration C4: ``generate`` gives the parameter set after a drop the dropped item's number, so the dropped
    item's folder must be gone (before, the second set raised FileExistsError and the generate unit crashed)."""
    item = _sheet_item(tmp_path / "items")
    params = [{"edits": [{"cell": "B1", "formula": "=ROUND(A2*3,0)"}]},  # edit_target_invalid, after its folder
              {"edits": [{"cell": "A3", "formula": "=ROUND(A2*2.5,0)"}]}]
    made = _generate(sheet.FAMILY, params, _functions(), source_items=[item, item], engine=FakeEngine().engine(),
                     out_dir=tmp_path / "generated")
    assert made["dropped"] == {"edit_target_invalid": 1} and [i["id"] for i in made["items"]] == ["gen:g-test-1:0"]
    assert len(list((tmp_path / "generated").iterdir())) == 1


# --------------------------------------------------------------------------------------------------- T-GEN-4
def _pool():
    return {game["task_id"]: {"initial_observation": game["initial_observation"],
                              "admissible_commands_at_reset": game["admissible_commands"],
                              "task_text": game["initial_observation"].rsplit("Your task is to: ", 1)[1]}
            for game in alfworld_games()}


def test_gen4_alfworld_selection_and_its_null_selector():
    pool = _pool()
    finding = {"kind": "selection", "id": "f" * 64}
    spec = alfworld_select.check_spec({"task_kinds": ["place"], "min_receptacles": 4, "min_openable": 3,
                                       "target": "openable", "finding": "f" * 64}, [finding])
    chosen = alfworld_select.select(spec, pool, n=4, seed_tag="execskill-v1:select:u")
    null = alfworld_select.null_select(pool, len(chosen), seed_tag="execskill-v1:select:u")
    assert len(chosen) == 4 and len(null) == 4 and set(null) <= set(pool)
    assert null == alfworld_select.null_select(pool, 4, seed_tag="execskill-v1:select:u")
    assert alfworld_select.features(pool[chosen[0]]) == {"task_kind": "place", "receptacles": 4, "openable": 3}
    report = alfworld_select.shift(chosen, null, pool, "openable")
    assert report["shift"] == report["selected_mean"] - report["null_mean"]
    with pytest.raises(Drop, match="no_material"):
        alfworld_select.check_spec({**spec, "finding": "0" * 64}, [finding])
    with pytest.raises(Drop, match="format"):
        alfworld_select.check_spec({**spec, "target": "won"}, [finding])


# --------------------------------------------------------------------------------------------------- T-GEN-5
def test_gen5_benches_without_a_family_are_selection_only():
    assert gen.mode("searchqa") == gen.mode("alfworld") == "selection_only"
    assert {gen.mode(b) for b in ("officeqa", "livemath", "spreadsheetbench")} == {"families"}
    assert gen.FAMILIES["searchqa"] == gen.FAMILIES["alfworld"] == {}
    with pytest.raises(ValueError):
        gen.family("searchqa.paraphrase")


# --------------------------------------------------------------------------------------------------- T-GEN-6
def test_gen6_items_only_from_qualified_findings_and_at_most_ten_per_finding():
    family = gen.family("officeqa.difference")
    assert _generate(family, [{"cells": [[1, 1], [2, 1]], "decimals": 0}], None) == {
        "status": "no_material", "items": [], "made": 0, "dropped": {}}
    assert research.material({"purpose": "table", "status": "none"}) is None
    sets = [{"cells": [[1, 1], [2, 1]], "decimals": d % 5} for d in range(MAX_ITEMS_PER_FINDING + 2)]
    made = _generate(family, sets, _table())
    assert len(made["items"]) == MAX_ITEMS_PER_FINDING and made["dropped"] == {"finding_exhausted": 2}
    assert [i["id"] for i in made["items"]][:2] == ["gen:g-test-1:0", "gen:g-test-1:1"]
    with pytest.raises(ValueError):
        _generate(family, sets[:1], _definition())  # a family consumes only its own material kind


def test_gen6_truth_by_the_reference_function_even_when_a_finding_states_a_number():
    stated = _definition("The derivative of f(x) = x^2 + x at x = 1 is 7, a fact about the derivative.")
    made = _generate(gen.family("livemath.derivative"), [{"coefficients": [1, 1, 0], "at": 1, "order": 1}], stated,
                     checker=FakeChecker())
    assert made["items"][0]["private"]["truth"]["exact"] == "3"  # 2x + 1 at 1, not the stated 7
    family = gen.family("officeqa.ratio")
    assert family.in_range("decimals", Fraction(3)) and not family.in_range("decimals", Fraction(7))
    with pytest.raises(Drop):
        check(family, {"cells": [[1, 1]], "decimals": 1})
