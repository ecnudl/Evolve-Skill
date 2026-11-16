"""Production engines of the SpreadsheetBench generator family (protocol ``fivebench-execskill-v1``; registration
§7.2 "SpreadsheetBench 族" (Codex F8, [SF F24]), §4.4 P4 row, §10 S0; implementation plan §1 generators row, §4
"Slots and lock order", §5; tickets C6-1, C7b1-3; registrar decisions 2026-10-22, addendum 13:0x: the pilot-readiness
row).

``sheet_engines(runtime, *, native, evidence)`` is the ``generators.sheet.Engine`` a run binds as
``step.Services.engine`` (``manifest.services_of``, ticket PR-C61-1). Zero model calls throughout:
- ``recalc`` (``Recalculation``): ``recalc(path) -> receipt``, the frozen v7 recalculation receipt of one workbook
  (``sheet_recalc_v7.Recalculator.run``: ``status``, ``reason``, ``output_base64``, ``output_sha256``, ..., sealed
  with ``record_hash``), run by the engine the frozen offline ``sheet_numeric_adapter.qualified_engine(runtime)``
  returns: the runtime's v7 engine qualification revalidated from this checkout (the file and its hash, its protocol,
  every control receipt and judgment, and the engine identity -- image, timeout, limits, the scorer sources by
  absolute path and hash; Calc is not run). The revalidation runs once, at the first recalculation
  (``Recalculation.engine``), so building the Services stays cheap and a QA step never pays for it; ``make-manifest``
  and S0 revalidate the same runtime before launch (``qualify.engine_runtime``, ticket C7b1-3). A runtime that does
  not revalidate raises ValueError: the generate unit pauses as "configuration".
- ``qualify``: the separate per-item engine qualification, ``qualify.qualify`` (the generated reference judged against
  itself twice by the frozen v7 scorer, each scoring under one native slot), with the run's ``evidence`` bound;
- ``runtime``: the SpreadsheetBench runtime (the manifest's ``runtime["spreadsheetbench"]``, copied);
- ``native``: the ``spreadsheet-native`` slot pool (``setting.slots[slots.NATIVE]``).

The native slot (plan §4-§5; registration §4.4): a recalculation holds ONE ``spreadsheet-native`` slot around the
frozen container run only -- taken when ``run`` starts, released as soon as it returns, before the receipt is checked
or read. No model call happens under it: ``spreadsheet-native`` is the last level of ``slots.LOCK_ORDER``, so a
thread holding it cannot take a model slot, and ``assert_order`` refuses a second native slot. The wait is the
untimed, logged native wait, never P4.

The receipt, checked after the slot is released (the frozen stop rows of ``coevo5.outcomes``):
- its container's removal is not confirmed (``cleanup_confirmed`` is not True): ``CleanupUnconfirmed``, a stop, as
  the frozen qualification stops on it (``coevo5.qualify._check``; outcomes row 3);
- it is not bound to the input's bytes, to the qualified engine's identity and to zero model calls: ValueError (the
  frozen ``DurableEngine.run`` check, scripts/replay_sheet_v6.py:110-111);
- a scorer-environment failure (``coevo5.outcomes.SCORER_ENVIRONMENT``, row 9c: no Linux docker, the pinned image or
  the daemon unavailable, an unsafe image): ``SandboxUnavailable`` (P4: the image is missing or docker does not
  start), so an infrastructure failure pauses the unit instead of dropping every parameter set as ``recalc_failed``;
- otherwise it is returned unchanged: ``generators.sheet`` reads an available one and drops the parameter set as
  ``recalc_failed`` on any other (a workbook the frozen screen refuses, a timeout, an execution error, an unverified
  read view).
"""
from __future__ import annotations

import functools
import hashlib
import threading
from copy import deepcopy

from skillopt.coevo5.outcomes import SCORER_ENVIRONMENT
from skillopt.continual_eval import sheet_numeric_adapter
from skillopt.continual_eval.core import require, safe_path

from . import qualify as qualification
from .errors import CleanupUnconfirmed, SandboxUnavailable
from .generators import sheet
from .protocol import EVIDENCE

__all__ = ("Recalculation", "sheet_engines")

REVALIDATION_ERRORS = (OSError, ValueError, KeyError, TypeError)  # sheet_numeric_adapter.readiness, :82


class Recalculation:
    """``Engine.recalc`` (module docstring). ``runtime``: the SpreadsheetBench runtime; ``native``: the
    ``spreadsheet-native`` pool (its ``hold()``); ``engine_of(runtime) -> (engine, qualification record)``: the frozen
    ``sheet_numeric_adapter.qualified_engine`` (a fake in tests)."""

    def __init__(self, runtime, native, *, engine_of=None):
        require(isinstance(runtime, dict), "A SpreadsheetBench runtime")
        require(hasattr(native, "hold"), "The native slot pool has hold()")
        self.runtime, self.native = runtime, native
        self.engine_of = engine_of or sheet_numeric_adapter.qualified_engine
        self._engine, self._identity, self._lock = None, None, threading.Lock()

    def engine(self):
        """The frozen v7 ``Recalculator`` of the runtime's engine qualification, revalidated from this checkout at the
        first use and kept with the qualified identity; ValueError naming the frozen refusal otherwise."""
        with self._lock:
            if self._engine is None:
                try:
                    engine, qualified = self.engine_of(self.runtime)
                except REVALIDATION_ERRORS as error:
                    raise ValueError("The SpreadsheetBench engine qualification does not revalidate from this "
                                     "checkout (tickets C6-1, C7b1-3): %s: %s"
                                     % (type(error).__name__, error)) from None
                require(qualified.get("engine") == engine.identity, "The recalculation engine is not the qualified one")
                self._engine, self._identity = engine, qualified["engine"]
            return self._engine

    def __call__(self, path):
        """The frozen v7 receipt of the workbook at ``path``, run under one native slot (module docstring)."""
        path = safe_path(path)
        engine = self.engine()
        expected = {"input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "identity": self._identity,
                    "model_api_calls": 0}
        with self.native.hold():
            receipt = engine.run(path)
        require(isinstance(receipt, dict), "A recalculation receipt")
        if receipt.get("cleanup_confirmed") is not True:
            raise CleanupUnconfirmed("sheet_recalc_cleanup_unconfirmed: %s" % (receipt.get("reason"),))
        require(all(receipt.get(key) == value for key, value in expected.items()),
                "The recalculation receipt is not bound to its input, the qualified engine and zero model calls")
        if receipt.get("reason") in SCORER_ENVIRONMENT:
            raise SandboxUnavailable("sheet_recalc_environment: %s" % receipt["reason"])
        return receipt


def sheet_engines(runtime, *, native, evidence, engine_of=None):
    """The ``generators.sheet.Engine`` of a run (module docstring). ``runtime``: the SpreadsheetBench runtime whose
    ``recalculation`` names a v7 engine qualification made from this checkout (``qualify.engine_runtime``);
    ``native``: the ``spreadsheet-native`` pool; ``evidence``: the run's label, stamped on every per-item engine
    qualification record; ``engine_of``: as ``Recalculation``. Nothing is revalidated here."""
    require(evidence in EVIDENCE or evidence in ('main_v9_real_run', 'main_v10_real_run'), "Unknown evidence label")
    runtime = deepcopy(runtime)
    return sheet.Engine(recalc=Recalculation(runtime, native, engine_of=engine_of),
                        qualify=functools.partial(qualification.qualify, evidence=evidence), runtime=runtime,
                        native=native)
