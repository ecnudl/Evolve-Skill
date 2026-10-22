"""Ticket PR-C61-2 (registrar decisions 2026-10-22, addendum 14:1x; registration §7.2 "SpreadsheetBench 族",
[SF F24]; plan §1 generators row, T-GEN-3): a generated SpreadsheetBench item binds both written workbooks by sha256
(``asset_sha256``, the pool items' shape) and its reference is the qualified engine's recalculation of the edited
workbook, so it carries formula caches and the frozen v7 engine qualification keeps it.

Real: ``generators.generate``, ``engines.sheet_engines`` (its receipt checks and its one native slot per container run),
``qualify.qualify``, the slot pools and the frozen scorer path -- ``backends.score``, ``sheet_numeric_adapter.score``
(the asset check, sheet_numeric_adapter.py:93-94) and ``sheet_recalc.evaluate_pair`` (the receipt binding, the content
guard, the reference-cache drift guard, the comparison). Faked: the container (the frozen v7 ``Recalculator``, here
``Calc``) and the offline revalidation ``sheet_numeric_adapter.qualified_engine``. Zero calls, offline."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
from pathlib import Path

import openpyxl
import pytest

from skillopt.coevo5.cells import Pause
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import sheet_numeric_adapter
from skillopt.continual_eval.core import read_json
from skillopt.execskill import engines, slots
from skillopt.execskill import generators as gen
from skillopt.execskill import qualify as qualification
from skillopt.execskill.generators import sheet
from skillopt.execskill.protocol import verified
from tests.test_execskill_generators import FakeEngine, _functions, _sheet_item, recalculated

EVIDENCE = "engineering_fixture"
IMAGE = "sha256:" + "f" * 64
IDENTITY = {"version": "spreadsheet-independent-lo-recalculation-v7", "image_id": IMAGE, "timeout_seconds": 120,
            "comparison_view": "original-general-formula-numeric-read-view-v1",
            "sources": {"/snapshot/skillopt/continual_eval/sheet_recalc_v7.py": "a" * 64}}
RUNTIME = {"spreadsheet_scorer": qualification.SCORER, "image": "sha256:" + "0" * 64, "timeout_seconds": 300,
           "recalculation": {"image": IMAGE, "timeout_seconds": 120, "qualification_path": "/q/qualification.json",
                             "qualification_sha256": "1" * 64, "qualification_hash": "2" * 64}}
EDIT = {"edits": [{"cell": "A3", "formula": "=ROUND(A2*2.5,0)"}]}  # A2 = 2: the new A3 is 5, the answer B1 17
RECALCULATED = ["edited-reference.xlsx", "literal-input.xlsx", "literal-answer.xlsx"]  # truth, then the two caches


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Calc:
    """The frozen v7 ``Recalculator`` without its container: ``run`` returns a sealed receipt of the frozen shape
    (sheet_recalc.py:410-497) whose output is ``recalculated`` -- every formula kept, its value written as its cache;
    ``caches(name)`` False: no caches, as openpyxl's save leaves them. ``held``: the slots its thread held during each
    run; ``sent``: the names of the workbooks run; ``outputs``: name -> output bytes."""
    image = IMAGE

    def __init__(self, native, *, caches=lambda name: True):
        self.native, self.caches, self.held, self.sent, self.outputs = native, caches, [], [], {}

    @property
    def identity(self):
        return dict(IDENTITY)

    def run(self, path):
        path = Path(path)
        self.held.append(self.native.holdings.held())
        self.sent.append(path.name)
        raw = self.outputs[path.name] = recalculated(path, caches=self.caches(path.name))
        return seal({"input_sha256": _sha(path), "identity": self.identity, "cleanup_confirmed": True,
                     "model_api_calls": 0, "container_execution_attempted": True, "duration_seconds": 0.5,
                     "status": "available", "reason": "independently_recalculated",
                     "output_base64": base64.b64encode(raw).decode(), "output_sha256": hashlib.sha256(raw).hexdigest()})


def _engine(tmp_path, monkeypatch, **options):
    """(the production ``sheet.Engine`` over ``Calc``, the ``Calc``, the native pool); the frozen offline revalidation
    is faked for ``engines.Recalculation`` and for the frozen scorer alike -- nothing else of the scorer is."""
    native = slots.pools(tmp_path / "slots", poll=0.01)[slots.NATIVE]
    calc = Calc(native, **options)

    def qualified_engine(runtime):
        assert runtime["spreadsheet_scorer"] == qualification.SCORER
        return calc, {"record_hash": "9" * 64, "engine": calc.identity}

    monkeypatch.setattr(sheet_numeric_adapter, "qualified_engine", qualified_engine)
    return engines.sheet_engines(RUNTIME, native=native, evidence=EVIDENCE, engine_of=qualified_engine), calc, native


def _generate(engine, item, out_dir, params=EDIT):
    return gen.generate(sheet.FAMILY, [params], _functions(), generator="g-test-1", set_name="G_self", seed=11,
                        evidence=EVIDENCE, source_items=[item], engine=engine, out_dir=out_dir)


def _capturing(engine, records, strip=()):
    """``engine`` whose qualification is the real one, its records kept in ``records``; the private ``strip`` keys are
    removed from the task first (a generated item without them)."""
    def qualify(tasks, root, runtime, **options):
        tasks = [{**t, "private": {k: v for k, v in t["private"].items() if k not in strip}} for t in tasks]
        records.append(engine.qualify(tasks, root, runtime, **options))
        return records[-1]
    return dataclasses.replace(engine, qualify=qualify)


def test_a_generated_item_binds_both_files_and_passes_the_real_frozen_engine_qualification(tmp_path, monkeypatch):
    """Both fixes on the real scorer path, as PR-C61's zero-call check on dl: the frozen asset check finds the reference
    bound, the drift guard finds its caches equal to the engine's recalculation, both scorings pass every case."""
    engine, calc, native = _engine(tmp_path, monkeypatch)
    made = _generate(engine, _sheet_item(tmp_path / "items"), tmp_path / "generated")
    assert made["status"] == "made" and made["dropped"] == {}
    generated = verified(made["items"][0], "generated-item")
    private = generated["private"]
    given, answer = generated["public"]["input_files"][0], private["test_files"][0]
    assert private["asset_sha256"] == {given: _sha(given), answer: _sha(answer)}  # {absolute path: sha256}, both files
    assert Path(given).is_absolute() and [Path(given).name, Path(answer).name] == ["input.xlsx", "answer.xlsx"]
    found = list((tmp_path / "generated").glob("*/qualification/qualification.json"))
    record = verified(read_json(found[0]), qualification.KIND)
    assert len(found) == 1 and record["qualified"] == [generated["id"]] and record["excluded"] == {}
    assert record["task_hashes"] == {generated["id"]: record["task_hashes"][generated["id"]]}
    scores = [read_json(path)["score"] for path in sorted(found[0].parent.glob("scores/*.json"))]
    assert [s["status"] for s in scores] == ["pass", "pass"]
    assert all(s["metrics"]["case_passed"] == 1 and s["metrics"]["model_api_calls"] == 0 for s in scores)
    # three recalculations, then one container run per scoring (the prediction is the reference: its receipt is reused)
    assert calc.sent == RECALCULATED + ["answer.xlsx", "answer.xlsx"]
    assert calc.held == [(slots.NATIVE,)] * 5 and native.holdings.held() == ()  # one native slot per container run


def test_the_saved_reference_carries_the_engines_caches_on_its_answer_cells(tmp_path, monkeypatch):
    """The generated reference and input are the engine's output for the workbooks with the new literals, byte for byte
    (the family edits both): the answer cell keeps its formula and carries the engine's value as its cache."""
    engine, calc, _ = _engine(tmp_path, monkeypatch)
    item = _sheet_item(tmp_path / "items")
    made = _generate(engine, item, tmp_path / "generated")
    generated = verified(made["items"][0], "generated-item")
    given, answer = generated["public"]["input_files"][0], generated["private"]["test_files"][0]
    cached, formulas = openpyxl.load_workbook(answer, data_only=True).active, openpyxl.load_workbook(answer).active
    assert cached["B1"].value == 17 == generated["private"]["truth"]["expected_cells"]["Sheet!B1"]
    assert formulas["B1"].value == "=SUM(A1:A5)" and formulas["A3"].value == cached["A3"].value == 5
    assert Path(answer).read_bytes() == calc.outputs["literal-answer.xlsx"]
    assert Path(given).read_bytes() == calc.outputs["literal-input.xlsx"]
    assert openpyxl.load_workbook(given).active["A3"].value == 5
    assert openpyxl.load_workbook(item["public"]["input_files"][0]).active["A3"].value == 3  # the source is unchanged


def test_without_asset_sha256_the_real_frozen_check_pauses_the_qualification(tmp_path, monkeypatch):
    """Defect 1: the frozen v7 scorer re-checks every reference against ``asset_sha256`` before it scores
    (sheet_numeric_adapter.py:93-94); without the binding the scoring is ``native_scoring_input_error:ValueError``
    (backends.py:566) and the frozen check pauses on it as "configuration" (coevo5/qualify.py:63-64)."""
    engine, calc, native = _engine(tmp_path, monkeypatch)
    with pytest.raises(Pause) as paused:
        _generate(_capturing(engine, [], strip=("asset_sha256",)), _sheet_item(tmp_path / "items"),
                  tmp_path / "generated")
    assert paused.value.kind == "configuration" and paused.value.reason == "native_scoring_input_error:ValueError"
    assert calc.sent == RECALCULATED and native.holdings.held() == ()  # refused before any container run of a scoring


def test_a_reference_without_caches_is_excluded_by_the_real_drift_guard(tmp_path, monkeypatch):
    """Defect 2: a reference whose formulas have no caches (openpyxl's save) leaves the frozen drift guard nothing to
    compare (spreadsheet_compat.py:246-260; sheet_recalc.py:610-612): both scorings unknown, the item excluded as
    ``reference_cache_mismatch``, the parameter set dropped -- so the harness above does see the caches."""
    engine, calc, _ = _engine(tmp_path, monkeypatch, caches=lambda name: name != "literal-answer.xlsx")
    records = []
    made = _generate(_capturing(engine, records), _sheet_item(tmp_path / "items"), tmp_path / "generated")
    assert made["dropped"] == {"engine_qualification_failed": 1} and made["items"] == []
    assert records[0]["qualified"] == [] and records[0]["excluded"] == {"gen:g-test-1:0": "reference_cache_mismatch"}
    assert list((tmp_path / "generated").iterdir()) == []


@pytest.mark.parametrize("patch", [{"input_sha256": "0" * 64}, {"output_sha256": "0" * 64}, {"output_base64": None}])
def test_a_receipt_not_bound_to_the_workbook_sent_and_its_output_is_refused(tmp_path, patch):
    fake = FakeEngine(patch=patch)
    with pytest.raises(ValueError, match="not bound to the workbook sent"):
        _generate(fake.engine(), _sheet_item(tmp_path / "items"), tmp_path / "generated")
    assert fake.log == ["recalc"]


@pytest.mark.parametrize("failing", [1, 2])
def test_an_unavailable_recalculation_of_a_generated_workbook_drops_the_set(tmp_path, failing):
    fake = FakeEngine(fail_at={failing})  # 1: the generated input, 2: the generated reference
    made = _generate(fake.engine(), _sheet_item(tmp_path / "items"), tmp_path / "generated")
    assert made["dropped"] == {"recalc_failed": 1} and fake.log == ["recalc"] * (failing + 1)
    assert fake.sent == RECALCULATED[:failing + 1] and list((tmp_path / "generated").iterdir()) == []
