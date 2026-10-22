"""The production engines of the SpreadsheetBench generator family (``skillopt/execskill/engines.py``; registration
§7.2 "SpreadsheetBench 族", §4.4 P4; plan §4-§5 slots and lock order; tickets C6-1, C7b1-3): the frozen v7
``Recalculator`` and its offline revalidation (``sheet_numeric_adapter.qualified_engine``) faked, the slot pools,
``generators.generate`` and the per-item engine qualification ``qualify.qualify`` real (its frozen scorer
``backends.score`` faked). Zero calls, offline."""
from __future__ import annotations

import base64
import functools
import hashlib
import io
import threading
import time
from pathlib import Path

import openpyxl
import pytest

from skillopt.coevo5.outcomes import SCORER_ENVIRONMENT
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require
from skillopt.execskill import engines, errors, research, slots
from skillopt.execskill import generators as gen
from skillopt.execskill import qualify as qualification
from skillopt.execskill.errors import CleanupUnconfirmed, ConfigurationError, SandboxUnavailable
from skillopt.execskill.generators import sheet
from skillopt.execskill.protocol import verified
from tests.fixtures.execskill.items import spreadsheetbench_items

EVIDENCE = "engineering_fixture"
IMAGE = "sha256:" + "f" * 64
IDENTITY = {"version": "spreadsheet-independent-lo-recalculation-v7", "image_id": IMAGE, "timeout_seconds": 120,
            "comparison_view": "original-general-formula-numeric-read-view-v1",
            "sources": {"/snapshot/skillopt/continual_eval/sheet_recalc_v7.py": "a" * 64}}
RUNTIME = {"spreadsheet_scorer": qualification.SCORER, "image": "sha256:" + "0" * 64, "timeout_seconds": 300,
           "recalculation": {"image": IMAGE, "timeout_seconds": 120, "qualification_path": "/q/qualification.json",
                             "qualification_sha256": "1" * 64, "qualification_hash": "2" * 64}}
EDIT = {"edits": [{"cell": "A3", "formula": "=ROUND(A2*2.5,0)"}]}  # A2 = 2: the new A3 is 5, the answer B1 17


class FakeRecalculator:
    """The frozen v7 ``Recalculator``, faked: ``run`` writes ``values`` ({(sheet, cell): value}) over a copy of the
    workbook and returns a sealed receipt of the frozen shape (``status``, ``reason``, ``output_base64``,
    ``output_sha256``, the input's hash, the identity, the cleanup flag, zero model calls); with ``reason`` an
    unavailable one. ``held``: the slots its thread held during each run; ``peak``: the most runs at once."""

    def __init__(self, native, *, values=None, reason=None, cleanup=True, patch=None, inside=None, pause=0.0):
        self.native, self.values, self.reason, self.cleanup = native, dict(values or {}), reason, cleanup
        self.patch, self.inside, self.pause, self.identity = dict(patch or {}), inside, pause, dict(IDENTITY)
        self.held, self.runs, self.active, self.peak = [], 0, 0, 0
        self._lock = threading.Lock()

    def run(self, path):
        with self._lock:
            self.runs, self.active = self.runs + 1, self.active + 1
            self.peak = max(self.peak, self.active)
        try:
            self.held.append(self.native.holdings.held())
            if self.inside is not None:
                self.inside()
            time.sleep(self.pause)
            base = {"input_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "identity": self.identity,
                    "cleanup_confirmed": self.cleanup, "model_api_calls": 0, "container_execution_attempted": True,
                    "duration_seconds": 0.5}
            if self.reason is not None:
                return seal({**base, "status": "unknown", "reason": self.reason, **self.patch})
            book = openpyxl.load_workbook(path)
            for (name, cell), value in self.values.items():
                book[name][cell] = value
            buffer = io.BytesIO()
            book.save(buffer)
            raw = buffer.getvalue()
            return seal({**base, "status": "available", "reason": "independently_recalculated",
                         "output_base64": base64.b64encode(raw).decode(),
                         "output_sha256": hashlib.sha256(raw).hexdigest(), **self.patch})
        finally:
            with self._lock:
                self.active -= 1


def _engine_of(recalculator, calls, *, qualified=None):
    """The frozen ``qualified_engine``, faked: the scorer profile check, then (engine, qualification record)."""
    def engine_of(runtime):
        calls.append(runtime)
        require(runtime.get("spreadsheet_scorer") == qualification.SCORER,
                "Explicit numeric recalculation profile required")
        return recalculator, {"record_hash": "9" * 64, "engine": qualified or recalculator.identity}
    return engine_of


def _pools(root, **sizes):
    return slots.pools(root / "slots", sizes=sizes or None, poll=0.01)


def _book(path, value=1):
    book = openpyxl.Workbook()
    for row in range(1, 4):
        book.active.cell(row=row, column=1, value=value + row)
    book.save(path)
    return path


def _function(name, quote):
    return research.material({"purpose": "function", "status": "found", "subject": name, "conclusion": name,
                              "quotes": [{"page": "P1", "archive": "c" * 64, "title": "Calc " + name, "revid": None,
                                          "text": quote}]})


def _functions():
    return sheet.function_set([_function("ROUND", "Syntax: ROUND(Number [; Count])"),
                               _function("SUM", "Syntax: SUM(Number 1[; Number 2])")])


def _sheet_item(root):
    item = spreadsheetbench_items(root, count=1)[0]  # A1:A5 = 1..5; the reference's B1 becomes =SUM(A1:A5)
    path = item["private"]["test_files"][0]
    book = openpyxl.load_workbook(path)
    book.active["B1"] = "=SUM(A1:A5)"
    book.save(path)
    return item


def _generate(engine, item, out_dir, params=EDIT):
    return gen.generate(sheet.FAMILY, [params], _functions(), generator="g-test-1", set_name="G_self", seed=11,
                        evidence=EVIDENCE, source_items=[item], engine=engine, out_dir=out_dir)


def test_sheet_engines_is_the_family_engine_and_builds_without_revalidating(tmp_path):
    pools, calls = _pools(tmp_path), []
    native = pools[slots.NATIVE]
    engine = engines.sheet_engines(RUNTIME, native=native, evidence=EVIDENCE,
                                   engine_of=_engine_of(FakeRecalculator(native), calls))
    assert isinstance(engine, sheet.Engine) and isinstance(engine.recalc, engines.Recalculation)
    assert isinstance(engine.qualify, functools.partial) and engine.qualify.func is qualification.qualify
    assert engine.qualify.keywords == {"evidence": EVIDENCE} and engine.native is native
    assert engine.runtime == RUNTIME and engine.runtime is not RUNTIME and engine.recalc.runtime is engine.runtime
    assert calls == []  # nothing is revalidated while the Services are built
    bare = engines.sheet_engines({}, native=native, evidence=EVIDENCE, engine_of=_engine_of(None, calls))
    assert calls == [] and bare.runtime == {}  # the manifest tests' empty runtimes still build
    with pytest.raises(ValueError, match="evidence"):
        engines.sheet_engines(RUNTIME, native=native, evidence="pilot")
    with pytest.raises(ValueError, match="hold"):
        engines.sheet_engines(RUNTIME, native=object(), evidence=EVIDENCE)
    assert engines.Recalculation(RUNTIME, native).engine_of is engines.sheet_numeric_adapter.qualified_engine


def test_recalc_revalidates_once_and_holds_one_native_slot_around_the_run_only(tmp_path):
    pools, calls = _pools(tmp_path), []
    native = pools[slots.NATIVE]

    def inside():  # under the recalculation's slot: no model slot and no second native slot (slots.LOCK_ORDER)
        for pool in ("glm-5.3", "deepseek-v4.1-flash-1017", slots.NATIVE):
            with pytest.raises(ConfigurationError, match="slot_lock_order"):
                with pools[pool].hold():
                    pass

    fake = FakeRecalculator(native, values={("Sheet", "A1"): 7}, inside=inside)
    recalc = engines.sheet_engines(RUNTIME, native=native, evidence=EVIDENCE, engine_of=_engine_of(fake, calls)).recalc
    first = recalc(_book(tmp_path / "one.xlsx"))
    second = recalc(_book(tmp_path / "two.xlsx", value=5))
    assert len(calls) == 1 and fake.runs == 2 and fake.held == [(slots.NATIVE,), (slots.NATIVE,)]
    assert native.holdings.held() == () and first["status"] == second["status"] == "available"
    output = openpyxl.load_workbook(io.BytesIO(base64.b64decode(first["output_base64"]))).active
    assert output["A1"].value == 7 and first["input_sha256"] == hashlib.sha256(
        (tmp_path / "one.xlsx").read_bytes()).hexdigest()
    with pools["glm-5.3"].hold():  # a thread between model calls may recalculate: native is the last level
        assert recalc(tmp_path / "one.xlsx")["status"] == "available"
    assert fake.held[-1] == ("glm-5.3", slots.NATIVE)


def test_a_runtime_that_does_not_revalidate_pauses_before_any_slot_or_run(tmp_path):
    pools = _pools(tmp_path)
    native, workbook = pools[slots.NATIVE], _book(tmp_path / "one.xlsx")
    fake = FakeRecalculator(native)

    def stale(runtime):
        assert native.holdings.held() == ()  # the revalidation runs before the slot is taken
        raise ValueError("Engine/source/image changed")  # replay_sheet_v6.py:133 from another checkout

    for engine_of, message in ((stale, "Engine/source/image changed"),
                               (lambda runtime: {}["recalculation"], "KeyError"),
                               (_engine_of(fake, []), "profile required")):
        runtime = {} if message == "profile required" else RUNTIME
        recalc = engines.Recalculation(runtime, native, engine_of=engine_of)
        with pytest.raises(ValueError, match="does not revalidate from this checkout") as refused:
            recalc(workbook)
        assert message in str(refused.value)
    other = engines.Recalculation(RUNTIME, native, engine_of=_engine_of(fake, [], qualified={**IDENTITY,
                                                                                            "image_id": "x"}))
    with pytest.raises(ValueError, match="not the qualified one"):
        other(workbook)
    assert fake.runs == 0 and native.holdings.held() == ()


@pytest.mark.parametrize("patch", [{"input_sha256": "0" * 64}, {"identity": {**IDENTITY, "timeout_seconds": 60}},
                                   {"model_api_calls": 1}])
def test_a_receipt_not_bound_to_its_input_engine_and_zero_calls_is_refused(tmp_path, patch):
    pools = _pools(tmp_path)
    fake = FakeRecalculator(pools[slots.NATIVE], patch=patch)
    recalc = engines.Recalculation(RUNTIME, pools[slots.NATIVE], engine_of=_engine_of(fake, []))
    with pytest.raises(ValueError, match="not bound"):
        recalc(_book(tmp_path / "one.xlsx"))
    assert fake.runs == 1 and pools[slots.NATIVE].holdings.held() == ()


def test_an_unconfirmed_cleanup_and_a_scorer_environment_failure_are_stops(tmp_path):
    pools = _pools(tmp_path)
    native, workbook = pools[slots.NATIVE], _book(tmp_path / "one.xlsx")
    leftover = FakeRecalculator(native, reason="container_cleanup_unconfirmed", cleanup=False)
    with pytest.raises(CleanupUnconfirmed) as stopped:
        engines.Recalculation(RUNTIME, native, engine_of=_engine_of(leftover, []))(workbook)
    assert errors.stop_kind(stopped.value) == "cleanup" and native.holdings.held() == ()
    assert len(SCORER_ENVIRONMENT) == 3
    for reason in sorted(SCORER_ENVIRONMENT):
        fake = FakeRecalculator(native, reason=reason)
        with pytest.raises(SandboxUnavailable, match=reason) as paused:
            engines.Recalculation(RUNTIME, native, engine_of=_engine_of(fake, []))(workbook)
        assert errors.stop_kind(paused.value) == "sandbox" and fake.held == [(slots.NATIVE,)]


def test_other_unavailable_receipts_reach_the_family_as_recalc_failed(tmp_path):
    pools = _pools(tmp_path)
    native = pools[slots.NATIVE]
    for n, reason in enumerate(("recalculation_timeout", "recalculation_execution_error",
                                "general_formula_read_view_unverified", "unsupported_external_link")):
        fake = FakeRecalculator(native, reason=reason)
        engine = engines.sheet_engines(RUNTIME, native=native, evidence=EVIDENCE, engine_of=_engine_of(fake, []))
        receipt = engine.recalc(_book(tmp_path / ("w%d.xlsx" % n)))
        assert receipt["status"] == "unknown" and receipt["reason"] == reason
        made = _generate(engine, _sheet_item(tmp_path / ("items-%d" % n)), tmp_path / ("out-%d" % n))
        assert made["dropped"] == {"recalc_failed": 1} and made["items"] == []
        assert list((tmp_path / ("out-%d" % n)).iterdir()) == []  # the dropped item's folder is removed


def test_the_production_engine_plugs_into_the_sheet_family(tmp_path, monkeypatch):
    pools = _pools(tmp_path)
    native = pools[slots.NATIVE]
    fake = FakeRecalculator(native, values={("Sheet", "A3"): 5, ("Sheet", "B1"): 17})
    scored = []

    def score(benchmark, public, private, prediction, *, runtime=None):  # the frozen v7 scorer, faked
        assert benchmark == "spreadsheetbench" and fake.runs == 3 and set(runtime) == set(RUNTIME) | {"_score_context"}
        scored.append(native.holdings.held())
        return {"status": "pass", "score": 1.0, "reason": "qualified_numeric_recalculation_hard_all_cases",
                "metrics": {"cases": [{"status": "pass", "reason": ""}]}, "cleanup_confirmed": True}

    monkeypatch.setattr(qualification.backends, "score", score)
    engine = engines.sheet_engines(RUNTIME, native=native, evidence=EVIDENCE, engine_of=_engine_of(fake, []))
    made = _generate(engine, _sheet_item(tmp_path / "items"), tmp_path / "generated")
    assert made["status"] == "made" and made["dropped"] == {}
    generated = verified(made["items"][0], "generated-item")
    truth = generated["private"]["truth"]
    assert truth["edited_values"] == {"Sheet!A3": 5} and truth["expected_cells"] == {"Sheet!B1": 17}
    assert generated["private"]["engine_qualification"]["ok"] is True
    assert fake.held == [(slots.NATIVE,)] * 3 and scored == [(slots.NATIVE,), (slots.NATIVE,)]  # one slot each, in turn
    found = list((tmp_path / "generated").glob("*/qualification/qualification.json"))
    record = verified(read_json(found[0]), qualification.KIND)
    assert len(found) == 1 and record["evidence"] == EVIDENCE and record["qualified"] == [generated["id"]]
    assert native.holdings.held() == ()


def test_native_slots_bound_concurrent_recalculations_and_revalidation_runs_once(tmp_path):
    pools, calls = _pools(tmp_path, **{slots.NATIVE: 2}), []
    native = pools[slots.NATIVE]
    fake = FakeRecalculator(native, pause=0.05)
    recalc = engines.Recalculation(RUNTIME, native, engine_of=_engine_of(fake, calls))
    paths = [_book(tmp_path / ("w%d.xlsx" % n), value=n) for n in range(6)]
    receipts = [None] * len(paths)

    def one(n):
        receipts[n] = recalc(paths[n])

    threads = [threading.Thread(target=one, args=(n,)) for n in range(len(paths))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1 and fake.runs == 6 and 1 <= fake.peak <= native.count == 2
    assert fake.held == [(slots.NATIVE,)] * 6 and all(r["status"] == "available" for r in receipts)
