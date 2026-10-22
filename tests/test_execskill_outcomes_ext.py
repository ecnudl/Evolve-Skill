"""T-OUT-1..5 (implementation plan §8.1): the route-B rows P1-P7 in front of the frozen decision table, the copied
preflight read on the deciding receipt (Codex F12), ``unknown_fault`` outside the infrastructure share, and the
worst delivery state that is recorded but never decides (registration §2.4, §4.4).

Offline and deterministic: synthetic receipts in the frozen client shape, and for T-OUT-5 the real elucid client
behind the scripted gateway of tests/execskill_fakes.py. No model call, no test-pool data.
"""
from __future__ import annotations

import pytest

from skillopt.coevo5 import outcomes
from skillopt.coevo5.outcomes import (
    FAIL,
    INFRASTRUCTURE,
    MALFORMED,
    NONCOMPLETION,
    PASS,
    PROGRAM_DEFECT,
    SCORED,
    UNKNOWN,
    AssumptionBroken,
    BudgetStop,
    CleanupUnconfirmed,
    ConfigurationError,
    LedgerFailure,
)
from skillopt.coevo5.step import _infrastructure
from skillopt.continual_eval import backends
from skillopt.execskill import judge, outcomes_ext, stats_ext
from skillopt.execskill.errors import ConsumptionConflict, PackageInvalid, SandboxUnavailable
from tests.execskill_fakes import FakeSolver, tagged, truncated, undelivered

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
PUBLIC = {"question": "What is the capital of France?", "context": ["Paris is the capital of France."]}
PRIVATE = {"answers": ["Paris"]}


def receipt(text="<answer>Paris</answer>", *, finish="stop", ok=True, error=None, **extra):
    """A receipt in the frozen client shape (weak_solver_probe.py:268-303)."""
    found = {"status": 200, "attempts": [{"status": 200, "seconds": 0.1}], "seconds": 0.1, "response": text,
             "finish_reason": finish, "usage": dict(USAGE), "usage_valid": True,
             "returned_model": "deepseek-v4.1-flash-1017", "reasoning_chars": 0, "ok": ok}
    if error is not None:
        found["error_type"] = error
    return {**found, **extra}


def gone(error="http_400"):
    return {"ok": False, "response": None, "finish_reason": None, "usage": {}, "status": 400,
            "attempts": [{"status": 400, "seconds": 0.1}], "error_type": error, "error_code": "x", "seconds": 0.1}


def available(reply="<answer>Paris</answer>", **shell):
    prediction = {"status": "available", "output": reply, "costs": {"calls": 1, "usage": USAGE},
                  "reason": "model_response_available"}
    return {**prediction, "shell": shell} if shell else prediction


def unknown(reason, **shell):
    prediction = {"status": "unknown", "output": None, "costs": {"calls": 1}, "reason": reason}
    return {**prediction, "shell": shell} if shell else prediction


def scored(prediction):
    return backends.score("searchqa", PUBLIC, PRIVATE, prediction, runtime={})


def sheet(case_reason):
    """A delivered SpreadsheetBench program whose only case failed in generation (row 9a, decided before scoring)."""
    return {"status": "available", "output": {"code": "print(1)", "cases": [{"status": "unknown", "reason": case_reason}]},
            "costs": {"calls": 2}, "reason": "generated_once_executed_per_public_case",
            "shell": {"deciding_receipt": 0, "calls": [], "fallback": "second_call_fallback"}}


# ------------------------------------------------------------------------------------------------- T-OUT-1: P1-P7
def test_t_out_1_p1_p2_faults_never_change_the_verdict():
    plain = available()
    faulted = available(deciding_receipt=0, faults=[{"procedure": "p-searchqa-1-1", "hook": "before_call",
                                                     "kind": "timeout"}, {"procedure": "p-searchqa-1-2",
                                                                          "hook": "applies", "kind": "crash"}])
    for prediction in (plain, faulted):
        verdict = outcomes_ext.classify("searchqa", prediction, scored(prediction), [receipt()], deciding=0)
        assert (verdict.outcome, verdict.kind, verdict.row) == (PASS, SCORED, "10")
        assert outcomes_ext.token(verdict) == "pass"


def test_t_out_1_p3_replay_mismatch_is_an_unknown_fault():
    prediction = unknown(outcomes_ext.REPLAY_MISMATCH)
    verdict = outcomes_ext.classify("spreadsheetbench", prediction, backends.score(
        "spreadsheetbench", {}, {}, prediction), [receipt("```python\nprint(1)\n```")], deciding=0)
    assert (verdict.outcome, verdict.kind, verdict.row, verdict.remedy) == (UNKNOWN, outcomes_ext.FAULT, "P3", None)
    assert outcomes_ext.token(verdict) == outcomes_ext.UNKNOWN_FAULT
    assert verdict.token == "unknown"  # the frozen property knows no fault kind: route B reads outcomes_ext.token
    assert outcomes.public(verdict) == "P3:fault:other"


@pytest.mark.parametrize("stop", [SandboxUnavailable, PackageInvalid, ConsumptionConflict, ConfigurationError,
                                  CleanupUnconfirmed, BudgetStop, AssumptionBroken, LedgerFailure])
def test_t_out_1_p4_a_recorded_call_exception_of_a_stop_class_stops(stop):
    prediction = unknown("model_call_exception:" + stop.__name__, deciding_receipt=None, calls=[])
    with pytest.raises(stop):
        outcomes_ext.preflight("searchqa", prediction, [], deciding=None)
    # the frozen table only knows three of them, and only as the prediction's own reason
    frozen_stops = (BudgetStop, AssumptionBroken, LedgerFailure)
    if stop not in frozen_stops:
        verdict = outcomes.classify("searchqa", prediction, scored(prediction), [])
        assert (verdict.outcome, verdict.row) == (UNKNOWN, "11")


def test_t_out_1_p4_a_stop_of_a_non_deciding_call_recorded_by_the_shell_stops():
    calls = [{"purpose": "first", "receipt_index": 0, "reason": "model_response_available"},
             {"purpose": "second", "receipt_index": None, "reason": "model_call_exception:SandboxUnavailable"}]
    prediction = available(deciding_receipt=0, calls=calls, fallback="second_call_fallback")
    with pytest.raises(SandboxUnavailable):
        outcomes_ext.classify("searchqa", prediction, scored(prediction), [receipt()], deciding=0)


def test_t_out_1_p6_reasoning_mismatch_on_the_deciding_receipt_is_row_4_and_elsewhere_is_counted_only():
    mismatch = receipt("<answer>Paris</answer>", ok=False, error="thinking_mismatch", subtype="reasoning_mismatch",
                       reasoning_tokens=12)
    prediction = unknown("model_call_unavailable")
    verdict = outcomes_ext.classify("searchqa", prediction, scored(prediction), [mismatch], deciding=0)
    assert (verdict.outcome, verdict.kind, verdict.row) == (UNKNOWN, INFRASTRUCTURE, "4")
    # the same mismatch on a second call the shell fell back from: the first reply decides
    fallback = available(deciding_receipt=0, fallback="second_call_fallback")
    verdict = outcomes_ext.classify("searchqa", fallback, scored(fallback), [receipt(), mismatch], deciding=0)
    assert (verdict.outcome, verdict.row) == (PASS, "10")
    found = judge.judge("searchqa", PUBLIC, PRIVATE, fallback, [receipt(), mismatch], runtime={})
    assert "reasoning_mismatch" in found["flags"] and found["v2"]["token"] == "pass"


def test_t_out_1_p7_over_nominal_is_scored_as_usual_and_counted():
    over = receipt(over_nominal=True, visible_completion_tokens=9000, reasoning_tokens=0)
    prediction = available()
    verdict = outcomes_ext.classify("searchqa", prediction, scored(prediction), [over], deciding=0)
    assert (verdict.outcome, verdict.row) == (PASS, "10")
    found = judge.judge("searchqa", PUBLIC, PRIVATE, prediction, [over], runtime={})
    assert found["flags"] == ["over_nominal"] and found["v2"]["token"] == "pass"


# ----------------------------------------------------------------------- T-OUT-2: unknown_fault is not infrastructure
def test_t_out_2_unknown_fault_is_outside_the_infrastructure_share():
    fault = outcomes_ext.classify("spreadsheetbench", unknown(outcomes_ext.REPLAY_MISMATCH), {"status": "unknown"},
                                  [receipt()], deciding=0)
    record = {"final": {"outcome": fault.outcome, "kind": fault.kind, "token": outcomes_ext.token(fault)}}
    assert _infrastructure([record]) == 0  # the frozen guard (step.py:128-130) counts infrastructure kinds only
    cells = {("S'", "a"): ["unknown_fault", "pass"], ("S'", "b"): ["unknown", "fail"]}
    assert stats_ext.infrastructure_share(cells, "S'", ["a", "b"]) == stats_ext.Fraction(1, 4)
    assert stats_ext.item_scores(cells, "S'", ["a", "b"], side="L") == {"a": stats_ext.Fraction(1, 2),
                                                                         "b": stats_ext.Fraction(0)}
    assert stats_ext.item_scores(cells, "S'", ["a", "b"], side="H") == {"a": stats_ext.Fraction(1),
                                                                         "b": stats_ext.Fraction(1, 2)}


# ------------------------------------------------- T-OUT-3: the deciding receipt decides, worst_delivery is recorded
def test_t_out_3_delivery_rows_read_the_deciding_receipt_and_worst_delivery_never_decides():
    prediction = available(deciding_receipt=0, fallback="second_call_fallback")
    receipts = [receipt(), gone()]
    verdict = outcomes_ext.classify("searchqa", prediction, scored(prediction), receipts, deciding=0)
    assert (verdict.outcome, verdict.row) == (PASS, "10")
    assert outcomes_ext.worst_delivery(receipts) == "undelivered:http_400"
    # the frozen table reads receipts[-1] (outcomes.py:258): the valid first reply would be an infrastructure unknown
    frozen = outcomes.classify("searchqa", prediction, scored(prediction), receipts)
    assert (frozen.outcome, frozen.kind, frozen.row) == (UNKNOWN, INFRASTRUCTURE, "4")
    # a deciding receipt that is itself truncated decides, whatever a later receipt says
    cut = receipt("<answer>Par", finish="length", ok=False, error="finish_length")
    verdict = outcomes_ext.classify("searchqa", unknown("model_response_truncated", deciding_receipt=0),
                                    {"status": "unknown"}, [cut, receipt()], deciding=0)
    assert (verdict.outcome, verdict.kind, verdict.row) == (FAIL, NONCOMPLETION, "5")


def test_t_out_3_worst_delivery_order_and_vocabulary():
    cut = receipt("x", finish="length", ok=False, error="finish_length")
    filtered = receipt("x", finish="content_filter", ok=False, error="finish_content_filter")
    weird = receipt("x", finish="provider says hello", ok=False, error="finish_provider says hello")
    assert outcomes_ext.worst_delivery([]) == outcomes_ext.NO_CALL
    assert outcomes_ext.worst_delivery([receipt()]) == "delivered"
    assert outcomes_ext.worst_delivery([receipt(), cut]) == "truncated"
    assert outcomes_ext.worst_delivery([filtered, cut]) == "noncompletion:finish_content_filter"
    assert outcomes_ext.worst_delivery([cut, gone("transport"), gone()]) == "undelivered:transport"
    assert outcomes_ext.worst_delivery([weird]) == "undelivered:other"  # provider text never leaves the table
    assert outcomes_ext.worst_delivery(["not a receipt"]) == "undelivered:no_receipt"


def test_t_out_3_the_deciding_receipt_comes_from_the_shell_and_is_checked():
    assert outcomes_ext.deciding_receipt(available(), [receipt(), receipt()]) == 1  # frozen shape: the last
    assert outcomes_ext.deciding_receipt(unknown("model_call_unavailable"), []) is None
    assert outcomes_ext.deciding_receipt(available(deciding_receipt=0), [receipt(), gone()]) == 0
    with pytest.raises(ValueError):
        outcomes_ext.deciding_receipt(available(deciding_receipt=2), [receipt(), gone()])
    with pytest.raises(ValueError):
        outcomes_ext.deciding_receipt(available(calls=[]), [receipt()])  # a shell must name it
    with pytest.raises(ValueError):
        outcomes_ext.classify("searchqa", available(), scored(available()), [receipt()], deciding=None)


# --------------------------------------------------------------------------------- T-OUT-4: the copied preflight
def test_t_out_4_a_stop_in_any_receipt_or_record_halts():
    first_invalid = ["not a receipt", receipt()]
    with pytest.raises(ConfigurationError):  # a non-deciding first receipt is scanned too
        outcomes_ext.preflight("searchqa", available(deciding_receipt=1), first_invalid, deciding=1)
    with pytest.raises(BudgetStop):
        outcomes_ext.preflight("searchqa", available(deciding_receipt=0), [receipt(), receipt()], deciding=0,
                               refused=True)
    for stop in (AssumptionBroken, LedgerFailure):
        with pytest.raises(stop):
            outcomes_ext.preflight("searchqa", unknown("model_call_exception:" + stop.__name__, deciding_receipt=0),
                                   [receipt()], deciding=0)
    with pytest.raises(CleanupUnconfirmed):
        outcomes_ext.preflight("spreadsheetbench", sheet("container_cleanup_unconfirmed"), [receipt(), gone()],
                               deciding=0)


def test_t_out_4_delivery_checks_read_the_deciding_receipt_never_the_last():
    prediction = sheet("native_exception:KeyError")
    receipts = [receipt("```python\nprint(1)\n```"), gone()]  # the repair call was not delivered
    verdict = outcomes_ext.preflight("spreadsheetbench", prediction, receipts, deciding=0)
    assert (verdict.outcome, verdict.kind, verdict.row) == (FAIL, PROGRAM_DEFECT, "9a")
    frozen = outcomes.preflight("spreadsheetbench", prediction, receipts)  # reads receipts[-1]
    assert (frozen.outcome, frozen.kind, frozen.row) == (UNKNOWN, INFRASTRUCTURE, "4")
    # with the deciding receipt undelivered the copied rows apply as the frozen ones do
    verdict = outcomes_ext.preflight("spreadsheetbench", prediction, [gone(), receipt()], deciding=0)
    assert (verdict.outcome, verdict.row) == (UNKNOWN, "4")
    # QA benches: the preflight only raises stops (outcomes.py:216-217)
    assert outcomes_ext.preflight("searchqa", available(deciding_receipt=0), [receipt(), gone()], deciding=0) is None


def test_t_out_4_without_receipts_there_is_no_deciding_receipt():
    prediction = unknown("alfworld_environment_error:RuntimeError")
    prediction["costs"] = {"calls": 0}
    verdict = outcomes_ext.classify("alfworld", prediction, {"status": "unknown"}, [], deciding=None)
    assert (verdict.outcome, verdict.row, verdict.remedy) == (UNKNOWN, "7", "restart")
    with pytest.raises(ValueError):
        outcomes_ext.classify("alfworld", prediction, {"status": "unknown"}, [], deciding=0)


# ------------------------------------------------------- T-OUT-5: through actual scoring with the real elucid client
def _two_calls(tmp_path, second):
    solver = FakeSolver(tmp_path, [("first question", tagged("Paris")), ("second question", second)])
    return [solver.call("system", "first question"), solver.call("system", "second question")]


def test_t_out_5_valid_first_and_undelivered_second_scores_the_first(tmp_path):
    receipts = _two_calls(tmp_path, undelivered("http_400"))
    assert receipts[0]["ok"] is True and receipts[1]["error_type"] == "http_400"
    prediction = available(receipts[0]["response"], deciding_receipt=0, fallback="second_call_fallback")
    found = judge.judge("searchqa", PUBLIC, PRIVATE, prediction, receipts, runtime={})
    assert found["official"]["status"] == "pass"
    assert found["final"]["token"] == "pass" and found["final"]["row"] == "10"
    assert found["v2"]["token"] == "pass" and "second_call_fallback" in found["flags"]
    assert outcomes_ext.worst_delivery(receipts) == "undelivered:http_400"
    frozen = outcomes.classify("searchqa", prediction, scored(prediction), receipts)
    assert frozen.kind == INFRASTRUCTURE  # what Codex F12 found


def test_t_out_5_valid_first_and_truncated_second_scores_the_first(tmp_path):
    receipts = _two_calls(tmp_path, truncated("<answer>Lyo"))
    assert receipts[1]["error_type"] == "finish_length"
    prediction = available(receipts[0]["response"], deciding_receipt=0, fallback="second_call_fallback")
    found = judge.judge("searchqa", PUBLIC, PRIVATE, prediction, receipts, runtime={})
    assert (found["final"]["token"], found["v2"]["token"]) == ("pass", "pass")
    assert "truncated" not in found["flags"]  # the deciding reply was complete
    assert outcomes_ext.worst_delivery(receipts) == "truncated"
    frozen = outcomes.classify("searchqa", prediction, scored(prediction), receipts)
    assert (frozen.outcome, frozen.kind) == (FAIL, NONCOMPLETION)


def test_t_out_5_a_delivered_second_reply_decides_and_is_scored(tmp_path):
    receipts = _two_calls(tmp_path, tagged("Lyon"))
    prediction = available(receipts[1]["response"], deciding_receipt=1)
    found = judge.judge("searchqa", PUBLIC, PRIVATE, prediction, receipts, runtime={})
    assert (found["official"]["status"], found["final"]["token"], found["v2"]["token"]) == ("fail", "fail", "fail")
    assert found["final"]["kind"] == SCORED and outcomes_ext.worst_delivery(receipts) == "delivered"
    malformed = outcomes_ext.classify("alfworld", unknown("invalid_action_format"), {"status": "unknown"},
                                      [receipt("")], deciding=0)
    assert (malformed.outcome, malformed.kind) == (FAIL, MALFORMED)
