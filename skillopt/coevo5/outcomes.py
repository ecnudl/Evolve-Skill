"""Cell outcomes (registration §5.4): the ordered decision table -- the first row that applies decides -- and the remedy
each row still allows.

Every cell keeps the official result (the frozen scorer's output, unchanged) next to the completion-aware one defined
here. The rule behind the table: an answer that was delivered is never replaced by a new answer.

- Rows 1-3 are not outcomes: a configuration error, a budget refusal and an unconfirmed cleanup stop the run. They are
  read from every record of the cell (the frozen backend can overwrite its own reason, e.g. when an ALFWorld
  environment fails to close), and the budget refusal from the call wrapper's own state.
- Rows 4-5 are read from the last receipt the solver received, before the backend's reason: a reply of another model
  is undelivered, not a truncation; a completed blank reply is a noncompletion even where the backend scores it.
- A request that delivered nothing is re-sent unchanged by the call wrapper before the frozen solver sees its receipt
  (``undelivered``); a reply still missing is an infrastructure unknown.
- The same SpreadsheetBench artifact may be executed again (``reexecute``: the delivered reply is replayed, so the same
  program runs on every case) or scored again (``rescore``: the same workbooks, in a fresh scoring directory).
- An ALFWorld episode is restarted (``restart``) only when its environment failed before any model call (row 7).
- ``preflight`` runs before the official scorer: it raises the stops the prediction, its receipts and the wrapper
  already show, and keeps a SpreadsheetBench answer away from the native scorer when no scoring can change its verdict
  -- a case that already fails (9a, 9b), or no workbook left to judge.

``classify`` returns a ``Verdict``: the outcome now, its kind, reason and table row, the remedy the runner may still
apply, and the outcome and kind to keep once that remedy is used up (``finalize``). A reason may quote what a backend or
the provider reported; only ``public`` -- the row, the kind and a detail from the table's own vocabulary -- leaves a
sealed record (§0).
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass

from skillopt.continual_eval.core import require

from .protocol import MAX_WORKBOOK_BYTES, MAX_WORKBOOK_EXPANDED_BYTES

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"

# kinds
SCORED = "scored"  # the official scorer judged a delivered answer
NONCOMPLETION = "noncompletion"  # truncated, filtered or empty reply
MALFORMED = "malformed"  # no extractable answer form (program, action)
ARTIFACT_DEFECT = "artifact_defect"  # SpreadsheetBench: no, oversized or structurally invalid output workbook
PROGRAM_DEFECT = "program_defect"  # SpreadsheetBench: the program raised, or timed out on every execution
INFRASTRUCTURE = "infrastructure"  # nothing delivered, or the execution / scoring environment failed
ARTIFACT = "artifact"  # a structurally valid workbook the frozen scorer could not judge
UNCLASSIFIED = "unclassified"  # a reason the table does not list; counted as infrastructure

REEXECUTE, RESCORE, RESTART = "reexecute", "rescore", "restart"

# row 1
CONFIGURATION = frozenset({
    "invalid_code_extraction_version", "invalid_spreadsheet_preview_version", "invalid_alfworld_trace_version",
    "invalid_alfworld_step_budget", "invalid_public_contract", "missing_public_workbook", "unknown_benchmark",
    "public_scoring_region_mismatch", "spreadsheet_case_count_mismatch", "original_case_count_mismatch",
    "invalid_qa_score_input", "invalid_answer_tag_score_input", "invalid_model_receipt",
    "digest_pinned_image_required", "native_request_size_limit",
})
CONFIGURATION_PREFIXES = ("public_input_or_runtime_error:", "native_scoring_input_error:")
# row 3: a container (SpreadsheetBench generation or scoring) or an ALFWorld worker that may still be alive
CLEANUP = frozenset({"container_cleanup_unconfirmed", "not_executed_after_cleanup_failure",
                     "alfworld_cleanup_unconfirmed"})
# row 4: provider receipts of a call that delivered no reply (HTTP error statuses too); v3 §9: a reply of the serving
# the request did not ask for (reasoning text although thinking was disabled) is not the requested model's either
UNDELIVERED_ERRORS = frozenset({"transport", "invalid_json", "error_payload", "malformed_choices", "malformed_finish",
                                "model_mismatch", "finish_network_error", "finish_None", "thinking_mismatch"})
# row 5: the solver's own noncompletion, by the last receipt or by the backend's reason
NONCOMPLETION_ERRORS = frozenset({"finish_sensitive", "finish_content_filter", "finish_length", "finish_max_tokens",
                                  "content_missing", "empty_content"})
NONCOMPLETION_REASONS = frozenset({"model_response_truncated", "model_response_filtered",
                                   "empty_or_oversized_model_response"})
UNAVAILABLE_REASONS = frozenset({"model_call_unavailable", "model_delivery_network_error"})
# row 6
MALFORMED_REASONS = frozenset({"invalid_action_format"})
MALFORMED_PREFIXES = ("code_delivery:",)
# rows 7-8
ALFWORLD_ERROR_PREFIX = "alfworld_environment_error:"
ALFWORLD_SIGNAL = "native_won_signal_missing"
# row 9a: SpreadsheetBench generation environment, one container per input case
EXECUTION_ENVIRONMENT = frozenset({
    "native_execution_unavailable", "invalid_native_receipt", "docker_unavailable",
    "pinned_image_or_daemon_unavailable", "pinned_image_unavailable_or_unsafe", "image_inspection_mismatch",
})
# row 9b
WORKBOOK_PARTS = frozenset({"[Content_Types].xml", "xl/workbook.xml"})
# row 9c: scoring-environment failures; with every reference-side failure they are infrastructure, any other unscorable
# candidate workbook is an artifact unknown
SCORER_ENVIRONMENT = frozenset({"linux_docker_unavailable", "pinned_image_or_daemon_unavailable",
                                "pinned_image_unavailable_or_unsafe"})
REFERENCE_DRIFT = "reference_native_cache_drift_or_unavailable"
HTTP_STATUS = re.compile(r"http_[1-5][0-9][0-9]")


class ConfigurationError(RuntimeError):
    """Row 1: a cell failed because of the run's configuration, not the solver or the infrastructure: the run pauses."""


class BudgetStop(Exception):
    """Row 2: raised by the call wrapper instead of sending a request the caps cannot cover (§13.2)."""


class CleanupUnconfirmed(RuntimeError):
    """Row 3: a container or an ALFWorld worker may still be alive: the run pauses until the cleanup is verified."""


class AssumptionBroken(Exception):
    """§13.2: a receipt reported more input or output tokens than the reservation's bound assumed, or the ledger is
    halted because one did: no further call is sent and the run pauses."""


class LedgerFailure(RuntimeError):
    """§13.2: a change of the token ledger may or may not have been committed (its journal or state could not be
    written), or the ledger refused an operation: no further call is sent and the run pauses. ``events``: the changes
    of the failed operation; ``quarantined``: whether the ledger could still record, under that operation's lock, the
    halt that closes what it left open (``budget.Budget``)."""

    def __init__(self, reason, events=(), *, quarantined=False):
        super().__init__(reason)
        self.events, self.quarantined = list(events), quarantined


@dataclass(frozen=True)
class Verdict:
    outcome: str
    kind: str
    reason: str
    row: str  # the deciding row of the table ("4", "9a", ...)
    remedy: str | None = None
    exhausted: tuple | None = None  # (outcome, kind) to keep once the remedy is used up

    @property
    def token(self):
        """The gate's cell token (``stats.OUTCOMES``) of a final verdict."""
        require(self.remedy is None, "Only a final verdict has a token")
        if self.outcome != UNKNOWN:
            return self.outcome
        return "unknown_artifact" if self.kind == ARTIFACT else "unknown"


def public_error(error):
    """True for a provider error type the table names (rows 4-5, an HTTP status); anything else -- e.g. ``finish_``
    and a finish reason the provider chose -- is not repeated outside a sealed record."""
    return isinstance(error, str) and (error in UNDELIVERED_ERRORS or error in NONCOMPLETION_ERRORS
                                       or HTTP_STATUS.fullmatch(error) is not None)


def public(final):
    """``row:kind:detail`` of a final verdict (a ``Verdict`` or its record) for monitoring and unit counts: the detail
    comes from the table's fixed vocabulary, else ``other`` -- never a raw backend or provider string (§0)."""
    final = final if isinstance(final, dict) else final.__dict__
    row, kind, reason, detail = final["row"], final["kind"], _text(final["reason"]), "other"
    if row == "4" and public_error(reason.rpartition(":")[2]):
        detail = reason.rpartition(":")[2]
    elif row in ("7", "8"):
        detail = ALFWORLD_SIGNAL if reason == ALFWORLD_SIGNAL else ALFWORLD_ERROR_PREFIX.rstrip(":")
    elif row == "9a" and reason.partition(":")[2] in EXECUTION_ENVIRONMENT | {"native_timeout"}:
        detail = reason.partition(":")[2]
    elif row == "9c":
        case = reason.partition(":")[2]
        side, _, base = case.partition(":")
        detail = ("reference" if side == "reference" or case == REFERENCE_DRIFT
                  else "scorer_environment" if side == "prediction" and base in SCORER_ENVIRONMENT
                  else "case_missing" if case == "case_missing" else "candidate_unjudged")
    return "%s:%s:%s" % (row, kind, detail)


def finalize(verdict):
    """The verdict to keep when its remedy can no longer be applied."""
    if verdict.remedy is None:
        return verdict
    outcome, kind = verdict.exhausted
    return Verdict(outcome, kind, verdict.reason, verdict.row)


def undelivered(receipt):
    """Row 4: True when a provider receipt carries no reply; the call wrapper then re-sends the identical request. A
    receipt that is not a mapping is not re-sent: the backend reports it as a configuration error (row 1)."""
    if not isinstance(receipt, dict) or receipt.get("ok") is True:
        return False
    error = receipt.get("error_type")
    return isinstance(error, str) and (error in UNDELIVERED_ERRORS or error.startswith("http_"))


def classify(benchmark, prediction, score=None, receipts=(), *, refused=False, spent=frozenset()):
    """``prediction``: ``backends.solve``'s result; ``score``: ``backends.score``'s result (required once the prediction
    is available); ``receipts``: the receipts the solver received, one per model call, in order; ``refused``: the call
    wrapper refused a call of this cell (§13.2); ``spent``: the remedies whose registered number is used up -- a case
    or cell that still asks for one keeps its final verdict, and the next remedy (9d: rescoring after re-execution)
    is still offered."""
    reason = _stops(prediction, score, receipts, refused)
    verdict = _delivery(reason, receipts)
    if verdict is not None:
        return verdict
    if prediction.get("status") != "available":
        verdict = _unavailable(benchmark, prediction, reason, _last_error(receipts))
        return finalize(verdict) if verdict.remedy in spent else verdict
    require(isinstance(score, dict), "An available prediction is scored before it is classified")
    if benchmark == "spreadsheetbench":
        return _spreadsheet(prediction, score, spent)
    status = score.get("status")
    if status in (PASS, FAIL):
        return Verdict(status, SCORED, _text(score.get("reason")), "10")
    return Verdict(UNKNOWN, UNCLASSIFIED, "score:" + _text(score.get("reason")), "11")


def preflight(benchmark, prediction, receipts=(), *, refused=False, spent=frozenset()):
    """Before the official scorer runs: raises the stops (rows 1-3) the prediction, its receipts and the wrapper
    already show. For a delivered SpreadsheetBench answer, returns ``classify``'s verdict where no scoring can change
    it: a case whose generation or workbook fails the task (9a, 9b; one failed case decides it, 9d), or cases that all
    have their verdict before scoring (e.g. every case timed out: the re-execution comes first). Else None: score,
    then ``classify`` -- also while a re-execution is pending, since a scored case that fails decides the task first
    (9d). A task failed here by 9a/9b carries the fail kind of the first case known to fail without scoring (scoring
    could only add an earlier failing case: the outcome and the gate token are the same)."""
    reason = _stops(prediction, None, receipts, refused)
    if benchmark != "spreadsheetbench" or prediction.get("status") != "available":
        return None
    verdict = _delivery(reason, receipts)
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


def _stops(prediction, score, receipts, refused):
    """Rows 1-3 (and the ledger stops of §13.2) over every record of the cell; returns the prediction's reason."""
    require(isinstance(prediction, dict), "A prediction is a mapping")
    reasons = _reasons(prediction, score)
    for reason in reasons:
        _configuration(reason)
    if not all(isinstance(r, dict) for r in receipts):  # the backend's own report of it may have been overwritten
        raise ConfigurationError("invalid_model_receipt")
    reason = _text(prediction.get("reason"))
    if refused or reason == "model_call_exception:" + BudgetStop.__name__:
        raise BudgetStop(reason)
    if reason == "model_call_exception:" + AssumptionBroken.__name__:
        raise AssumptionBroken(reason)
    if reason == "model_call_exception:" + LedgerFailure.__name__:
        raise LedgerFailure(reason)
    if any(_cleanup(r) for r in reasons) or (isinstance(score, dict) and score.get("cleanup_confirmed") is False):
        raise CleanupUnconfirmed(next((r for r in reasons if _cleanup(r)), "score:cleanup_unconfirmed"))
    return reason


def _last_error(receipts):
    last = receipts[-1] if receipts else None
    return _text(last.get("error_type")) if isinstance(last, dict) else "no_receipt"


def _delivery(reason, receipts):
    """Rows 4-5: the last receipt the solver received, read before the backend's reason."""
    last, error = (receipts[-1] if receipts else None), _last_error(receipts)
    if undelivered(last):
        return Verdict(UNKNOWN, INFRASTRUCTURE, reason + ":" + error, "4")
    if isinstance(last, dict) and error in NONCOMPLETION_ERRORS:
        return Verdict(FAIL, NONCOMPLETION, reason + ":" + error, "5")
    return None


def _text(value):
    return value if isinstance(value, str) else "missing"


def _reasons(prediction, score):
    """Every reason in the cell's records: the prediction's, each generated case's, the score's and each scored case's."""
    reasons = [_text(prediction.get("reason"))]
    output = prediction.get("output")
    if isinstance(output, dict) and isinstance(output.get("cases"), list):
        reasons += [_text(c.get("reason")) for c in output["cases"] if isinstance(c, dict) and "reason" in c]
    if isinstance(score, dict):
        reasons.append(_text(score.get("reason")))
        cases = (score.get("metrics") or {}).get("cases")
        if isinstance(cases, list):
            reasons += [_text(c.get("reason")) for c in cases if isinstance(c, dict) and "reason" in c]
    return reasons


def _configuration(reason):
    if reason in CONFIGURATION or reason.startswith(CONFIGURATION_PREFIXES):
        raise ConfigurationError(reason)


def _cleanup(reason):
    return reason in CLEANUP or reason.partition(":")[2] in CLEANUP


def _unavailable(benchmark, prediction, reason, error):
    if reason in NONCOMPLETION_REASONS:
        return Verdict(FAIL, NONCOMPLETION, reason, "5")
    if reason in MALFORMED_REASONS or reason.startswith(MALFORMED_PREFIXES):
        return Verdict(FAIL, MALFORMED, reason, "6")
    if benchmark == "alfworld":
        calls = (prediction.get("costs") or {}).get("calls")
        if reason.startswith(ALFWORLD_ERROR_PREFIX) and calls == 0:
            return Verdict(UNKNOWN, INFRASTRUCTURE, reason, "7", RESTART, (UNKNOWN, INFRASTRUCTURE))
        if reason.startswith(ALFWORLD_ERROR_PREFIX) or reason == ALFWORLD_SIGNAL:
            return Verdict(UNKNOWN, INFRASTRUCTURE, reason, "8")
    return Verdict(UNKNOWN, UNCLASSIFIED, reason + (":" + error if reason in UNAVAILABLE_REASONS else ""), "11")


def _spreadsheet(prediction, score, spent=frozenset()):
    """Row 9. Every input case must pass (the frozen hard-all-cases rule). Per case: the generation result (9a), the
    delivered workbook's structure (9b), then the scorer's case result (9c); 9d combines the cases."""
    scored = (score.get("metrics") or {}).get("cases")
    return _combine([_generation(case) or _workbook(case) or _scored_case(scored, index)
                     for index, case in enumerate(_cases(prediction))], spent)


def _combine(verdicts, spent):
    """9d: the task's verdict from its case verdicts (a spent remedy keeps the case's final verdict)."""
    verdicts = [finalize(v) if v.remedy in spent else v for v in verdicts]
    failed = [v for v in verdicts if v.outcome == FAIL and v.remedy is None]
    if failed:
        return failed[0]
    for remedy in (REEXECUTE, RESCORE):  # 9d: re-execution (which also rescores) before rescoring
        pending = [v for v in verdicts if v.remedy == remedy]
        if pending:
            return Verdict(UNKNOWN, pending[0].kind, pending[0].reason, pending[0].row, remedy,
                           _aggregate([finalize(v) for v in verdicts]))
    outcome, kind = _aggregate(verdicts)
    first = next((v for v in verdicts if v.outcome == outcome), verdicts[0])
    return Verdict(outcome, kind, first.reason, first.row)


def _cases(prediction):
    output = prediction.get("output")
    cases = output.get("cases") if isinstance(output, dict) else None
    require(isinstance(cases, list) and cases and all(isinstance(c, dict) for c in cases),
            "SpreadsheetBench cases required")
    return cases


def _aggregate(verdicts):
    """9d: (outcome, kind) of a task from its final case verdicts."""
    for verdict in verdicts:
        if verdict.outcome == FAIL:
            return FAIL, verdict.kind
    unknown = [v for v in verdicts if v.outcome == UNKNOWN]
    if unknown:
        return UNKNOWN, ARTIFACT if all(v.kind == ARTIFACT for v in unknown) else INFRASTRUCTURE
    return PASS, SCORED


def _generation(case):
    """9a: None for a delivered workbook; else the verdict of a case whose program did not deliver one."""
    status, reason = case.get("status"), _text(case.get("reason"))
    if status == "available":
        return None
    label = "generation:" + reason
    if status == "missing_output" or reason == "output_workbook_size_limit":
        return Verdict(FAIL, ARTIFACT_DEFECT, label, "9a")
    if reason.startswith("native_exception:"):
        return Verdict(FAIL, PROGRAM_DEFECT, label, "9a")
    if reason == "native_timeout":
        return Verdict(UNKNOWN, INFRASTRUCTURE, label, "9a", REEXECUTE, (FAIL, PROGRAM_DEFECT))
    if reason in EXECUTION_ENVIRONMENT:
        return Verdict(UNKNOWN, INFRASTRUCTURE, label, "9a", REEXECUTE, (UNKNOWN, INFRASTRUCTURE))
    return Verdict(UNKNOWN, UNCLASSIFIED, label, "11")


def _workbook(case):
    """9b: a delivered output must be an xlsx package the frozen openpyxl opens (checked before scoring). A structural
    failure means no valid workbook was delivered (fail); what the scorer then cannot judge is unknown (9c)."""
    try:
        raw = base64.b64decode(case.get("output_base64") or "", validate=True)
        require(0 < len(raw) <= MAX_WORKBOOK_BYTES, "Workbook size")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
        require(sum(m.file_size for m in members) <= MAX_WORKBOOK_EXPANDED_BYTES, "Unpacked workbook size")
        require(WORKBOOK_PARTS <= {m.filename for m in members}, "Workbook parts")
        import openpyxl

        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
        try:
            require(len(book.worksheets) > 0, "A worksheet")
        finally:
            book.close()
    except MemoryError:
        raise
    except Exception:  # whatever openpyxl raises on a package it cannot open
        return Verdict(FAIL, ARTIFACT_DEFECT, "workbook:invalid_xlsx", "9b")
    return None


def _scored_case(scored, index):
    """9c."""
    if not isinstance(scored, list) or index >= len(scored) or not isinstance(scored[index], dict):
        return Verdict(UNKNOWN, ARTIFACT, "score:case_missing", "9c", RESCORE, (UNKNOWN, ARTIFACT))
    status, reason = scored[index].get("status"), _text(scored[index].get("reason"))
    if status in (PASS, FAIL):
        return Verdict(status, SCORED, "score:" + reason, "9c")
    side, _, base = reason.partition(":")
    environment = side == "reference" or reason == REFERENCE_DRIFT or (side == "prediction" and base in
                                                                       SCORER_ENVIRONMENT)
    kind = INFRASTRUCTURE if environment else ARTIFACT
    return Verdict(UNKNOWN, kind, "score:" + reason, "9c", RESCORE, (UNKNOWN, kind))
