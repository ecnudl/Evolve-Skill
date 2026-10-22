"""Route-B rows P1-P7 in front of the frozen decision table, and the frozen preflight read on the deciding receipt
(docs/handoff/execskill-registration-v1-20261021.md §4.4 rows P1-P7, §2.4 item 4, §2.5; Codex F12 in §20;
implementation plan §1 outcomes_ext row, §8.1 T-OUT-1..5).

The frozen table (skillopt/coevo5/outcomes.py) is imported unchanged. Route B puts rows in front of it and reads its
delivery rows on another receipt:

- P1 (a procedure fault: crash, timeout, memory, format, cap, banned name, lexicon hit, worker death) and P2 (an
  ``applies`` fault): the shell goes on without the procedure. The fault is counted (J3); the cell is classified like
  any other and nothing pauses, so no row here changes a verdict for them.
- P3 (a re-execution that presents another request than the stored one): the replayed prediction carries the reason
  ``REPLAY_MISMATCH`` and the cell's token is ``unknown_fault`` (kind ``FAULT``): wrong for the candidate arm, right for
  the controls (``stats_ext``), outside the infrastructure share (the frozen guard counts the kinds infrastructure and
  unclassified only, step.py:128-130), counted as a fault, no pause.
- P4 (sandbox unavailable) is a stop: ``errors.SandboxUnavailable`` propagates from the sandbox. A call exception of any
  stop class of the one exception set that the frozen ``_response`` turned into a reason
  (``model_call_exception:<class>``, backends.py:91-94) is raised again here.
- P5 (a second or repair call undelivered or truncated): the shell falls back to the first reply. The cell is decided
  on the DECIDING receipt -- the one whose reply the prediction carries -- while the mandatory stops are read from
  every receipt and every record. The worst delivery state over all receipts is recorded (``worst_delivery``) and
  never decides. The frozen preflight reads ``receipts[-1]`` (``_delivery``, outcomes.py:256-263, :258), which turns a
  valid first reply into an infrastructure unknown when the second call fails (Codex F12); it is copied here with the
  deciding receipt as a parameter, and ``classify`` hands the frozen table only the deciding receipt.
- P6 (reasoning although disabled): the client marks the receipt ``thinking_mismatch`` (an undelivered error,
  outcomes.py:66-67), the call wrapper re-sends it, and the frozen row 4 applies on the deciding receipt; a reply
  beyond the ledger bound B stops the ledger (``AssumptionBroken``) before any resend.
- P7 (M < reply <= B): scored as usual; the judge counts the receipt's ``over_nominal``.

Route-B code reads a final verdict's token through ``token``: the frozen ``Verdict.token`` knows no fault kind.
"""
from __future__ import annotations

from skillopt.coevo5 import outcomes
from skillopt.coevo5.outcomes import (
    FAIL,
    INFRASTRUCTURE,
    NONCOMPLETION,
    NONCOMPLETION_ERRORS,
    UNKNOWN,
    Verdict,
    _cases,
    _combine,
    _generation,
    _stops,
    _text,
    _workbook,
    finalize,
    public_error,
    undelivered,
)
from skillopt.coevo5.stats import OUTCOMES
from skillopt.continual_eval.core import require

from .errors import STOP_KINDS
from .protocol import BENCHES

FAULT = "fault"  # P3's kind
UNKNOWN_FAULT = "unknown_fault"  # P3's token
TOKENS = OUTCOMES + (UNKNOWN_FAULT,)  # the cell tokens of route B (frozen stats.py:16 plus P3's)
REPLAY_MISMATCH = "replay_request_mismatch"  # P3: the reason of a re-execution that presented another request
CALL_EXCEPTION = "model_call_exception:"  # the frozen _response's reason for a call that raised (backends.py:93-94)
STOPS_BY_NAME = {cls.__name__: cls for cls in STOP_KINDS}  # the one exception set (errors.py)
TRUNCATED_ERRORS = frozenset({"finish_length", "finish_max_tokens"})
DELIVERED, TRUNCATED, NO_CALL = "delivered", "truncated", "no_call"


def token(verdict):
    """The cell token of a final verdict: the frozen ``Verdict.token`` (outcomes.py:132-138), or ``unknown_fault`` for
    P3."""
    require(isinstance(verdict, Verdict) and verdict.remedy is None, "Only a final verdict has a token")
    return UNKNOWN_FAULT if verdict.kind == FAULT else verdict.token


def deciding_receipt(prediction, receipts):
    """The index of the receipt that decides the cell: the shell's ``deciding_receipt`` for a route-B prediction (plan
    §3: the receipt whose reply the prediction carries), else the last receipt -- a frozen-shape prediction has one
    call, or one per ALFWorld step, and the frozen table reads the last. None for a cell without receipts."""
    require(isinstance(prediction, dict), "A prediction is a mapping")
    receipts = list(receipts)
    shell = prediction.get("shell")
    if shell is None:
        index = len(receipts) - 1 if receipts else None
    else:
        require(isinstance(shell, dict) and "deciding_receipt" in shell, "A shell names its deciding receipt")
        index = shell["deciding_receipt"]
    check_deciding(receipts, index)
    return index


def preflight(bench, prediction, receipts=(), *, deciding, refused=False, spent=frozenset()):
    """Copy of the frozen ``preflight`` (outcomes.py:207-228) with two changes (Codex F12): the stops are read from
    every record of the cell and from every receipt (``_all_stops``), and rows 4-5 read the deciding receipt instead of
    ``receipts[-1]`` (outcomes.py:258). For a delivered SpreadsheetBench answer it returns the verdict no scoring can
    change (9a, 9b, 9d); else None: score, then ``classify``."""
    require(bench in BENCHES, "Unknown benchmark")
    receipts = list(receipts)
    check_deciding(receipts, deciding)
    reason = _all_stops(prediction, None, receipts, refused)
    if bench != "spreadsheetbench" or prediction.get("status") != "available":
        return None
    verdict = _delivery(reason, receipts, deciding)
    if verdict is not None:
        return verdict
    verdicts = [_generation(case) or _workbook(case) for case in _cases(prediction)]
    failed = [finalize(v) for v in verdicts if v is not None and (v.remedy is None or v.remedy in spent)
              and finalize(v).outcome == FAIL]
    if failed:
        return failed[0]
    if any(v is None for v in verdicts):
        return None  # a workbook still to be judged
    return _combine(verdicts, spent)


def classify(bench, prediction, score=None, receipts=(), *, deciding, refused=False, spent=frozenset()):
    """The cell's verdict: the stops over every record and every receipt, then P3, then the frozen ``classify``
    (outcomes.py:185-204) on the deciding receipt alone, so its rows 4-5 and its unavailable rows read that receipt.
    Arguments as the frozen ``classify``, plus ``deciding`` (``deciding_receipt``)."""
    require(bench in BENCHES, "Unknown benchmark")
    receipts = list(receipts)
    check_deciding(receipts, deciding)
    _all_stops(prediction, score, receipts, refused)
    if prediction.get("reason") == REPLAY_MISMATCH:
        return Verdict(UNKNOWN, FAULT, REPLAY_MISMATCH, "P3")
    return outcomes.classify(bench, prediction, score, [receipts[deciding]] if receipts else [], refused=refused,
                             spent=spent)


def delivery(receipt):
    """One receipt's delivery state: ``delivered``, ``truncated``, ``noncompletion:<error>`` (filtered, empty or
    missing content) or ``undelivered:<error>`` (no usable reply); a provider error type the table does not name is
    written ``other`` (outcomes.public_error)."""
    if not isinstance(receipt, dict):
        return "undelivered:no_receipt"
    if receipt.get("ok") is True:
        return DELIVERED
    error = receipt.get("error_type")
    if error in TRUNCATED_ERRORS:
        return TRUNCATED
    detail = error if public_error(error) else "other"
    return ("noncompletion:" if error in NONCOMPLETION_ERRORS else "undelivered:") + detail


def worst_delivery(receipts):
    """P5: the worst delivery state over all receipts of the cell (undelivered, then truncated or another
    noncompletion, then delivered; the first of equally bad ones), ``no_call`` without receipts. Recorded per cell and
    reported per arm; it never decides the cell."""
    states = [delivery(r) for r in receipts]
    if not states:
        return NO_CALL
    return max(states, key=_badness)


def _badness(state):
    return 2 if state.startswith("undelivered:") else 0 if state == DELIVERED else 1


def check_deciding(receipts, deciding):
    """``deciding`` indexes one of ``receipts``; without receipts it is None."""
    if receipts:
        require(type(deciding) is int and 0 <= deciding < len(receipts),
                "The deciding receipt is one of the cell's receipts")
    else:
        require(deciding is None, "A cell without receipts has no deciding receipt")


def _all_stops(prediction, score, receipts, refused):
    """The frozen rows 1-3 and ledger stops over every record and every receipt (outcomes.py:231-248), then every
    recorded call exception of a stop class of the one exception set (the frozen ``_stops`` names only BudgetStop,
    AssumptionBroken and LedgerFailure, for the prediction's own reason). Returns the prediction's reason."""
    reason = _stops(prediction, score, receipts, refused)
    for found in _reasons(prediction, score):
        name = found[len(CALL_EXCEPTION):] if found.startswith(CALL_EXCEPTION) else None
        if name in STOPS_BY_NAME:
            raise STOPS_BY_NAME[name](found)
    return reason


def _reasons(prediction, score):
    """Every reason of the cell's records (outcomes.py:270-281) and the reason the shell recorded for each of its
    logical calls (``shell.calls[i].reason``, when the shell records one)."""
    shell = prediction.get("shell")
    calls = shell.get("calls") if isinstance(shell, dict) else None
    extra = [_text(c.get("reason")) for c in calls or () if isinstance(c, dict) and "reason" in c]
    return outcomes._reasons(prediction, score) + extra


def _delivery(reason, receipts, deciding):
    """Rows 4-5 on the deciding receipt: a copy of outcomes.py:256-263 with ``_last_error`` (:251-253), both of which
    read ``receipts[-1]`` (:252, :258)."""
    receipt = receipts[deciding] if receipts else None
    error = _text(receipt.get("error_type")) if isinstance(receipt, dict) else "no_receipt"
    if undelivered(receipt):
        return Verdict(UNKNOWN, INFRASTRUCTURE, reason + ":" + error, "4")
    if isinstance(receipt, dict) and error in NONCOMPLETION_ERRORS:
        return Verdict(FAIL, NONCOMPLETION, reason + ":" + error, "5")
    return None
