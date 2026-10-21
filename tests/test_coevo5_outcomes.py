"""coevo5 cell outcomes (registration §5.4): the ordered decision table, row by row, its remedies (which never replace
a delivered answer), and cells where several rows apply at once -- through the frozen backend with mocked
environments."""
import base64
import io
import zipfile

import openpyxl
import pytest

from skillopt.coevo5 import outcomes
from skillopt.coevo5.outcomes import (
    ARTIFACT,
    ARTIFACT_DEFECT,
    FAIL,
    INFRASTRUCTURE,
    MALFORMED,
    NONCOMPLETION,
    PASS,
    PROGRAM_DEFECT,
    REEXECUTE,
    RESCORE,
    RESTART,
    SCORED,
    UNCLASSIFIED,
    UNKNOWN,
    AssumptionBroken,
    BudgetStop,
    CleanupUnconfirmed,
    ConfigurationError,
    classify,
    finalize,
    preflight,
    undelivered,
)
from skillopt.continual_eval import backends


def _unknown(reason, **extra):
    return {"status": "unknown", "reason": reason, **extra}


def _workbook():
    book = openpyxl.Workbook()
    book.active["A1"] = 1
    buffer = io.BytesIO()
    book.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode()


WORKBOOK = _workbook()
OK = {"ok": True, "error_type": None}


def _package(**members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return base64.b64encode(buffer.getvalue()).decode()


def _sheet(*cases):
    return {"status": "available", "output": {"code": "x", "cases": list(cases)}}


def _delivered(output=WORKBOOK):
    return {"status": "available", "output_base64": output, "reason": "isolated_workbook_generated"}


def _score(*cases, cleanup=True):
    status = "fail" if any(c["status"] == "fail" for c in cases) else (
        "unknown" if any(c["status"] == "unknown" for c in cases) or not cleanup else "pass")
    return {"status": status, "reason": "qualified_numeric_recalculation_hard_all_cases" if cleanup
            else "container_cleanup_unconfirmed", "cleanup_confirmed": cleanup, "metrics": {"cases": list(cases)}}


def _row(verdict):
    return verdict.outcome, verdict.kind, verdict.remedy, verdict.row


# row 1
@pytest.mark.parametrize("reason", ["invalid_public_contract", "invalid_alfworld_trace_version", "unknown_benchmark",
                                    "public_input_or_runtime_error:OSError", "invalid_model_receipt"])
def test_row1_configuration_errors_stop_the_run(reason):
    with pytest.raises(ConfigurationError):
        classify("searchqa", _unknown(reason))


def test_row1_reads_every_record_of_the_cell():
    with pytest.raises(ConfigurationError):
        classify("searchqa", {"status": "available"}, _unknown("native_scoring_input_error:KeyError"))
    with pytest.raises(ConfigurationError):
        classify("spreadsheetbench", _sheet(_delivered()), _unknown("native_scoring_input_error:ValueError"))
    # the frozen numeric adapter reports a case-count mismatch as its only case; a failed generation does not hide it
    mismatch = _score(_unknown("spreadsheet_case_count_mismatch"))
    with pytest.raises(ConfigurationError):
        classify("spreadsheetbench", _sheet({"status": "missing_output", "reason": "output.xlsx_not_produced"},
                                            _delivered()), mismatch)
    with pytest.raises(ConfigurationError):
        classify("spreadsheetbench", _sheet(_delivered()), _score(_unknown("public_scoring_region_mismatch")))


# row 2
def test_row2_a_budget_refusal_is_a_stop_whatever_the_backend_reports():
    with pytest.raises(BudgetStop):
        classify("searchqa", _unknown("model_call_exception:BudgetStop"))
    with pytest.raises(BudgetStop):  # the wrapper's own state, e.g. under an overwritten ALFWorld reason
        classify("alfworld", _unknown("alfworld_cleanup_unconfirmed", costs={"calls": 2}), receipts=[OK], refused=True)
    assert classify("searchqa", _unknown("model_call_exception:ValueError")).row == "11"


# row 3
@pytest.mark.parametrize("prediction,score", [
    (_sheet(_unknown("container_cleanup_unconfirmed"), _delivered()), _score({"status": "pass"}, {"status": "pass"})),
    (_sheet(_delivered(), _unknown("not_executed_after_cleanup_failure")), _score({"status": "pass"})),
    (_sheet(_delivered()), _score({"status": "pass"}, cleanup=False)),
    (_sheet(_delivered()), _score(_unknown("prediction:container_cleanup_unconfirmed"))),
    (_sheet(_delivered()), _score(_unknown("reference:container_cleanup_unconfirmed")))])
def test_row3_an_unconfirmed_spreadsheet_cleanup_pauses_the_run(prediction, score):
    with pytest.raises(CleanupUnconfirmed):
        classify("spreadsheetbench", prediction, score)


def test_row3_an_alfworld_worker_that_did_not_close_pauses_the_run():
    with pytest.raises(CleanupUnconfirmed):
        classify("alfworld", _unknown("alfworld_cleanup_unconfirmed", costs={"calls": 0}))


# row 4
@pytest.mark.parametrize("error", ["transport", "http_429", "http_500", "invalid_json", "error_payload",
                                   "malformed_choices", "model_mismatch", "finish_network_error", "finish_None",
                                   "thinking_mismatch"])
def test_row4_a_call_that_delivered_nothing_is_an_infrastructure_unknown(error):
    verdict = classify("searchqa", _unknown("model_call_unavailable"), receipts=[OK, {"ok": False, "error_type": error}])
    # the call wrapper re-sent the identical request before the solver saw this receipt: nothing is left to redo
    assert _row(verdict) == (UNKNOWN, INFRASTRUCTURE, None, "4")


def test_undelivered_receipts_are_the_ones_the_wrapper_resends():
    assert undelivered({"ok": False, "error_type": "http_503"}) and undelivered({"ok": False, "error_type": "transport"})
    assert undelivered({"ok": False, "error_type": "model_mismatch", "finish_reason": "length"})
    assert undelivered({"ok": False, "error_type": "thinking_mismatch", "finish_reason": "stop"})  # v3 §9
    assert not undelivered(None)  # not a receipt: the backend reports a configuration error (row 1)
    assert not undelivered({"ok": True, "error_type": None})
    assert not undelivered({"ok": False, "error_type": "finish_length"})
    assert not undelivered({"ok": False, "error_type": "empty_content"})


# row 5
@pytest.mark.parametrize("reason", ["model_response_truncated", "model_response_filtered",
                                    "empty_or_oversized_model_response"])
def test_row5_the_solver_s_own_noncompletion_is_a_fail_and_is_never_redone(reason):
    assert _row(classify("searchqa", _unknown(reason), receipts=[OK])) == (FAIL, NONCOMPLETION, None, "5")


@pytest.mark.parametrize("error", ["finish_length", "finish_sensitive", "finish_content_filter", "content_missing",
                                   "empty_content"])
def test_row5_reads_the_last_receipt(error):
    verdict = classify("searchqa", _unknown("model_call_unavailable"), receipts=[{"ok": False, "error_type": error}])
    assert _row(verdict) == (FAIL, NONCOMPLETION, None, "5")


# row 6
@pytest.mark.parametrize("benchmark,reason", [("alfworld", "invalid_action_format"),
                                              ("spreadsheetbench", "code_delivery:no_python_block")])
def test_row6_no_extractable_answer_form_is_a_fail(benchmark, reason):
    verdict = classify(benchmark, _unknown(reason, costs={"calls": 2}), receipts=[OK, OK])
    assert _row(verdict) == (FAIL, MALFORMED, None, "6")


# rows 7-8
def test_rows7_8_alfworld_restarts_only_an_episode_that_never_called_the_model():
    early = classify("alfworld", _unknown("alfworld_environment_error:RuntimeError", costs={"calls": 0}))
    assert _row(early) == (UNKNOWN, INFRASTRUCTURE, RESTART, "7") and finalize(early).outcome == UNKNOWN
    late = classify("alfworld", _unknown("alfworld_environment_error:RuntimeError", costs={"calls": 3}),
                    receipts=[OK] * 3)
    assert _row(late) == (UNKNOWN, INFRASTRUCTURE, None, "8")
    lost = classify("alfworld", _unknown("native_won_signal_missing", costs={"calls": 1}), receipts=[OK])
    assert _row(lost) == (UNKNOWN, INFRASTRUCTURE, None, "8")


# row 9a
@pytest.mark.parametrize("case,kind", [
    ({"status": "missing_output", "reason": "output.xlsx_not_produced"}, ARTIFACT_DEFECT),
    (_unknown("output_workbook_size_limit"), ARTIFACT_DEFECT),
    (_unknown("native_exception:KeyError"), PROGRAM_DEFECT),
    (_unknown("native_exception:SystemExit"), PROGRAM_DEFECT)])
def test_row9a_program_defects_fail_without_a_new_answer(case, kind):
    # the frozen scorer reports such a case as unknown; one failed case decides the task
    score = _score({"status": "pass"}, _unknown("output.xlsx_not_produced"))
    verdict = classify("spreadsheetbench", _sheet(_delivered(), case), score)
    assert _row(verdict) == (FAIL, kind, None, "9a")


def test_row9a_timeouts_and_sandbox_failures_reexecute_the_same_program():
    timed_out = classify("spreadsheetbench", _sheet(_delivered(), _unknown("native_timeout")),
                         _score({"status": "pass"}, _unknown("native_timeout")))
    assert timed_out.remedy == REEXECUTE and finalize(timed_out).outcome == FAIL
    assert finalize(timed_out).kind == PROGRAM_DEFECT
    for reason in ("native_execution_unavailable", "invalid_native_receipt", "image_inspection_mismatch"):
        crashed = classify("spreadsheetbench", _sheet(_unknown(reason), _delivered()),
                           _score(_unknown(reason), {"status": "pass"}))
        assert crashed.remedy == REEXECUTE and finalize(crashed).kind == INFRASTRUCTURE
        assert finalize(crashed).token == "unknown"


# row 9b
@pytest.mark.parametrize("output", [
    base64.b64encode(b"a,b\n1,2").decode(),  # a CSV posing as xlsx
    _package(**{"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<workbook/>"}),  # the parts, unreadable
    _package(**{"xl/workbook.xml": "<workbook/>"}),
    "", "not base64!"])
def test_row9b_a_structurally_invalid_workbook_is_a_fail(output):
    verdict = classify("spreadsheetbench", _sheet(_delivered(output)), _score(_unknown("prediction:unreadable")))
    assert _row(verdict) == (FAIL, ARTIFACT_DEFECT, None, "9b")


def test_row9b_bounds_the_unpacked_size(monkeypatch):
    assert classify("spreadsheetbench", _sheet(_delivered()), _score({"status": "pass"})).outcome == PASS
    monkeypatch.setattr(outcomes, "MAX_WORKBOOK_EXPANDED_BYTES", 1000)
    assert classify("spreadsheetbench", _sheet(_delivered()), _score({"status": "pass"})).row == "9b"


# row 9c
@pytest.mark.parametrize("reason,kind", [
    ("reference:recalculation_timeout", INFRASTRUCTURE),
    ("reference:numeric_literal_manifest_unavailable", INFRASTRUCTURE),
    ("reference_native_cache_drift_or_unavailable", INFRASTRUCTURE),
    ("prediction:linux_docker_unavailable", INFRASTRUCTURE),
    ("prediction:pinned_image_unavailable_or_unsafe", INFRASTRUCTURE),
    ("prediction:recalculation_timeout", ARTIFACT), ("prediction:recalculation_execution_error", ARTIFACT),
    ("prediction:numeric_literal_manifest_unavailable", ARTIFACT),
    ("prediction:unsupported_external_relationship", ARTIFACT), ("recalculation_input_or_evidence_error", ARTIFACT),
    ("read_view_unverifiable", ARTIFACT)])
def test_row9c_scorer_failures_rescore_the_same_workbook(reason, kind):
    verdict = classify("spreadsheetbench", _sheet(_delivered()), _score(_unknown(reason)))
    assert (verdict.remedy, verdict.row) == (RESCORE, "9c")
    assert finalize(verdict).kind == kind
    assert finalize(verdict).token == ("unknown_artifact" if kind == ARTIFACT else "unknown")


# row 9d
def test_row9d_tasks_pass_only_when_every_case_passes():
    assert classify("spreadsheetbench", _sheet(_delivered(), _delivered()),
                    _score({"status": "pass"}, {"status": "pass"})).outcome == PASS
    failed = classify("spreadsheetbench", _sheet(_delivered(), _unknown("native_timeout")),
                      _score({"status": "fail", "reason": "value_mismatch"}, _unknown("native_timeout")))
    assert _row(failed) == (FAIL, SCORED, None, "9c")


def test_row9d_reexecution_comes_before_rescoring_and_mixed_unknowns_are_infrastructure():
    verdict = classify("spreadsheetbench", _sheet(_delivered(), _unknown("native_timeout")),
                       _score(_unknown("prediction:recalculation_timeout"), _unknown("native_timeout")))
    assert verdict.remedy == REEXECUTE and finalize(verdict).outcome == FAIL
    mixed = classify("spreadsheetbench", _sheet(_delivered(), _delivered()),
                     _score(_unknown("prediction:recalculation_timeout"), _unknown("reference:recalculation_timeout")))
    assert finalize(mixed).kind == INFRASTRUCTURE
    artifacts = classify("spreadsheetbench", _sheet(_delivered(), _delivered()),
                         _score(_unknown("prediction:recalculation_timeout"), {"status": "pass"}))
    assert finalize(artifacts).kind == ARTIFACT


# preflight: before the official scorer
def test_preflight_raises_the_stops_already_visible():
    with pytest.raises(CleanupUnconfirmed):
        preflight("spreadsheetbench", _sheet(_delivered(), _unknown("container_cleanup_unconfirmed")))
    with pytest.raises(BudgetStop):
        preflight("searchqa", _unknown("model_call_exception:BudgetStop"))
    with pytest.raises(AssumptionBroken):
        preflight("alfworld", _unknown("model_call_exception:AssumptionBroken"))
    with pytest.raises(ConfigurationError):
        preflight("searchqa", {"status": "available"}, receipts=["not a mapping"])
    assert preflight("searchqa", {"status": "available"}, receipts=[OK]) is None  # the other benches: scored


def test_preflight_decides_only_what_no_scoring_can_change():
    # a structurally invalid workbook fails the task whatever the other case scores
    assert _row(preflight("spreadsheetbench", _sheet(_delivered(), _delivered("not base64!")))) == \
        (FAIL, ARTIFACT_DEFECT, None, "9b")
    # every case timed out: nothing to judge, the re-execution comes first; used up, a program defect
    timed_out = _sheet(_unknown("native_timeout"), _unknown("native_timeout"))
    assert preflight("spreadsheetbench", timed_out).remedy == REEXECUTE
    assert _row(preflight("spreadsheetbench", timed_out, spent=frozenset({REEXECUTE}))) == \
        (FAIL, PROGRAM_DEFECT, None, "9a")
    # a workbook to judge next to a timeout is scored first: a failing case decides the task before re-execution
    assert preflight("spreadsheetbench", _sheet(_delivered(), _unknown("native_timeout"))) is None
    assert preflight("spreadsheetbench", _sheet(_delivered())) is None


@pytest.mark.parametrize("cases", [
    (_unknown("native_timeout"),), (_unknown("native_execution_unavailable"), _unknown("native_timeout")),
    (_delivered("not base64!"),), (_unknown("native_exception:KeyError"), _delivered()),
    (_delivered(), _unknown("native_exception:KeyError")), (_unknown("odd_reason"),)])
@pytest.mark.parametrize("spent", [frozenset(), frozenset({REEXECUTE})])
def test_what_preflight_decides_classify_decides_whatever_the_score(cases, spent):
    early = preflight("spreadsheetbench", _sheet(*cases), spent=spent)
    for scored in ({"status": "pass"}, {"status": "fail", "reason": "value_mismatch"},
                   _unknown("prediction:recalculation_timeout")):
        late = classify("spreadsheetbench", _sheet(*cases), _score(*[scored] * len(cases)), spent=spent)
        assert (early.outcome, early.remedy, finalize(early).outcome) == (
            late.outcome, late.remedy, finalize(late).outcome)


# rows 10-11
def test_rows10_11_official_scores_pass_through_and_the_rest_is_unclassified():
    for benchmark in ("searchqa", "officeqa", "livemath", "alfworld"):
        assert classify(benchmark, {"status": "available"}, {"status": "pass", "reason": "r"}, receipts=[OK]) == \
            outcomes.Verdict(PASS, SCORED, "r", "10")
        assert classify(benchmark, {"status": "available"}, {"status": "fail", "reason": "r"}).outcome == FAIL
    with pytest.raises(ValueError):  # an available answer is always scored first, so the official result exists
        classify("searchqa", {"status": "available"})
    odd = classify("searchqa", _unknown("model_call_unavailable"), receipts=[{"ok": False,
                                                                               "error_type": "finish_tool_calls"}])
    assert _row(odd) == (UNKNOWN, UNCLASSIFIED, None, "11") and odd.token == "unknown"


def test_only_final_verdicts_have_gate_tokens():
    verdict = classify("spreadsheetbench", _sheet(_delivered()), _score(_unknown("prediction:recalculation_timeout")))
    with pytest.raises(ValueError):
        verdict.token
    assert classify("searchqa", _unknown("model_response_truncated")).token == "fail"


# several rows at once, through the frozen backend
class _Episode:
    """A mocked ALFWorld environment: one admissible action, never won; ``close`` may fail."""

    def __init__(self, close_fails):
        self.close_fails = close_fails

    def reset(self):
        return ["You are in a room."], None, [{"admissible_commands": ["look"]}]

    def step(self, actions):
        return ["Nothing happens."], None, [0], [False], [{"admissible_commands": ["look"], "won": False}]

    def close(self):
        if self.close_fails:
            raise RuntimeError("ALFWorld worker cleanup unconfirmed")


def _calls(*replies):
    """A solver call that returns the given receipts in turn (an exception class is raised) and records them."""
    received, queue = [], list(replies)

    def call(system, user):
        reply = queue.pop(0)
        if isinstance(reply, type):
            raise reply("refused")
        received.append(reply)
        return reply
    return call, received


def _reply(text):
    return {"ok": True, "response": text, "finish_reason": "stop", "error_type": None,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


TRUNCATED = {"ok": False, "response": "<action>lo", "finish_reason": "length", "error_type": "finish_length",
             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
WRONG_MODEL = {"ok": False, "response": None, "finish_reason": "length", "error_type": "model_mismatch", "usage": {}}


def _alfworld(monkeypatch, close_fails, *replies):
    monkeypatch.setattr(backends, "_new_alfworld", lambda public, runtime: _Episode(close_fails))
    call, received = _calls(*replies)
    prediction = backends.solve("alfworld", {"game_file": "game.tw-pddl"}, "", call, runtime={"max_steps": 3})
    return prediction, received


def test_a_budget_refusal_under_an_alfworld_cleanup_failure_still_stops(monkeypatch):
    prediction, received = _alfworld(monkeypatch, True, _reply("<action>look</action>"), BudgetStop)
    assert prediction["reason"] == "alfworld_cleanup_unconfirmed"  # the backend overwrote the refusal
    with pytest.raises(BudgetStop):
        classify("alfworld", prediction, receipts=received, refused=True)
    with pytest.raises(CleanupUnconfirmed):
        classify("alfworld", prediction, receipts=received)


def test_a_receipt_that_is_not_a_mapping_under_an_alfworld_cleanup_failure_is_a_configuration_error(monkeypatch):
    prediction, received = _alfworld(monkeypatch, True, _reply("<action>look</action>"), None)
    assert prediction["reason"] == "alfworld_cleanup_unconfirmed"  # the backend overwrote invalid_model_receipt
    with pytest.raises(ConfigurationError):
        classify("alfworld", prediction, receipts=received)


def test_a_truncation_under_an_alfworld_cleanup_failure_pauses_and_without_it_fails(monkeypatch):
    prediction, received = _alfworld(monkeypatch, True, _reply("<action>look</action>"), TRUNCATED)
    with pytest.raises(CleanupUnconfirmed):
        classify("alfworld", prediction, receipts=received)
    prediction, received = _alfworld(monkeypatch, False, _reply("<action>look</action>"), TRUNCATED)
    assert _row(classify("alfworld", prediction, receipts=received)) == (FAIL, NONCOMPLETION, None, "5")


def test_alfworld_wrong_model_and_malformed_actions_through_the_frozen_backend(monkeypatch):
    prediction, received = _alfworld(monkeypatch, False, _reply("<action>look</action>"), WRONG_MODEL)
    assert prediction["reason"] == "model_response_truncated"  # the backend reads finish_reason first
    assert _row(classify("alfworld", prediction, receipts=received)) == (UNKNOWN, INFRASTRUCTURE, None, "4")
    prediction, received = _alfworld(monkeypatch, False, _reply("<action></action>"))
    assert _row(classify("alfworld", prediction, receipts=received)) == (FAIL, MALFORMED, None, "6")
    prediction, received = _alfworld(monkeypatch, False, *[_reply("<action>look</action>")] * 3)
    score = backends.score("alfworld", {"game_file": "game.tw-pddl"}, {}, prediction)
    assert _row(classify("alfworld", prediction, score, received)) == (FAIL, SCORED, None, "10")


def test_a_completed_blank_answer_tag_reply_is_a_noncompletion_though_the_backend_scores_it():
    blank = {"ok": False, "response": "", "finish_reason": "stop", "error_type": "empty_content", "status": 200,
             "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10}}
    call, received = _calls(blank)
    public = {"question": "What?", "context": "page"}
    prediction = backends.solve("officeqa", public, "", call)
    score = backends.score("officeqa", public, {"answer": "42"}, prediction)
    assert (prediction["status"], score["status"]) == ("available", "fail")
    assert _row(classify("officeqa", prediction, score, received)) == (FAIL, NONCOMPLETION, None, "5")


def test_a_wrong_model_truncation_is_undelivered_through_the_frozen_backend():
    call, received = _calls(WRONG_MODEL)
    prediction = backends.solve("searchqa", {"question": "Q", "context": ["c"]}, "", call)
    assert prediction["reason"] == "model_response_truncated"
    assert _row(classify("searchqa", prediction, receipts=received)) == (UNKNOWN, INFRASTRUCTURE, None, "4")


def test_a_spent_remedy_keeps_the_final_verdict_and_the_next_remedy_is_still_offered():
    early = _unknown("alfworld_environment_error:RuntimeError", costs={"calls": 0})
    assert _row(classify("alfworld", early, spent=frozenset({RESTART}))) == (UNKNOWN, INFRASTRUCTURE, None, "7")
    timed_out = _sheet(_delivered(), _unknown("native_timeout"))
    score = _score(_unknown("prediction:recalculation_timeout"), _unknown("native_timeout"))
    assert classify("spreadsheetbench", timed_out, score).remedy == REEXECUTE
    # re-executions used up: the timed-out case is a program defect, and one failed case decides the task
    assert _row(classify("spreadsheetbench", timed_out, score, spent=frozenset({REEXECUTE}))) == \
        (FAIL, PROGRAM_DEFECT, None, "9a")
    # a sandbox failure stays unknown once re-executions are used up; the unjudged workbook is still rescored
    crashed = _sheet(_unknown("native_execution_unavailable"), _delivered())
    score = _score(_unknown("native_execution_unavailable"), _unknown("prediction:recalculation_timeout"))
    after = classify("spreadsheetbench", crashed, score, spent=frozenset({REEXECUTE}))
    assert (after.remedy, after.row) == (RESCORE, "9c") and finalize(after).kind == INFRASTRUCTURE
    final = classify("spreadsheetbench", crashed, score, spent=frozenset({REEXECUTE, RESCORE}))
    assert _row(final) == (UNKNOWN, INFRASTRUCTURE, None, "9a") and final.token == "unknown"


@pytest.mark.parametrize("final, category", [
    ({"row": "4", "kind": "infrastructure", "reason": "model_call_unavailable:transport"}, "4:infrastructure:transport"),
    ({"row": "4", "kind": "infrastructure", "reason": "model_call_unavailable:http_502"}, "4:infrastructure:http_502"),
    ({"row": "4", "kind": "infrastructure", "reason": "x:finish_SEALED"}, "4:infrastructure:other"),
    ({"row": "11", "kind": "unclassified", "reason": "model_call_unavailable:finish_SEALED"},
     "11:unclassified:other"),
    ({"row": "8", "kind": "infrastructure", "reason": "alfworld_environment_error:SEALED"},
     "8:infrastructure:alfworld_environment_error"),
    ({"row": "9a", "kind": "infrastructure", "reason": "generation:docker_unavailable"},
     "9a:infrastructure:docker_unavailable"),
    ({"row": "9a", "kind": "unclassified", "reason": "generation:SEALED"}, "9a:unclassified:other"),
    ({"row": "9c", "kind": "infrastructure", "reason": "score:reference:SEALED"}, "9c:infrastructure:reference"),
    ({"row": "9c", "kind": "artifact", "reason": "score:prediction:SEALED"}, "9c:artifact:candidate_unjudged"),
])
def test_only_the_table_s_vocabulary_leaves_a_sealed_record(final, category):
    assert outcomes.public(final) == category
