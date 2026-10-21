"""The per-step diagnosis: triage -> representative cases -> hypotheses -> hypothesis-bound checks (deterministic
admissibility, limited-blinding review, [Research + a second review of revised expectations], execution) -> graded
check records -> per-row reports and the step summary. Every model call is a ledger ``verifier`` call under the v7
delivery rule (a closed length truncation gets one length recovery; a still truncated/empty/filtered reply is that
unit's own result; one bounded format retry that itself follows the delivery rule); every record is sealed under
``diagnosis/<step>``. The challenge pool never appears here. Diagnosis stops admitting cases when the step's
protected challenge capacity would be touched."""
from __future__ import annotations

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, write_json
from skillopt.continual_learning import verifier as vf
from skillopt.continual_learning.ledger import LearningPending
from skillopt.continual_learning.reflection_json import NativeJSONError
from skillopt.validator_pilot.api import digest

from . import PROTOCOL
from .checks import (
    STATE_KIND,
    NOT_APPLICABLE,
    blind_review_messages,
    check_messages,
    describe,
    deterministic_admissibility,
    grade,
    judge_focus_messages,
    normalize_probe,
    parse_check_probes,
    parse_judged_checks,
    repair_messages,
)
from .diagnoser import clip_hypothesis_texts, fitted_case_views, hypothesis_messages, parse_hypotheses
from .profiles import profile_text
from .reports import UNASSIGNED, fact_needs, judged_leads, observations, render_report, render_summary, seal_report
from .triage import triage_record

TERMINAL = ("truncated_or_empty", "filtered", "prompt_too_large")
# WORST-CASE ledger requests one case may need: every unit (BCB: check, repair, review, research plan, resolution,
# revision review; text domains: judge) can take 4 requests (call, length recovery, format retry, its recovery)
UNIT_REQUESTS = 4
CASE_CALL_ESTIMATE = {"bigcodebench": 6 * UNIT_REQUESTS, "searchqa": UNIT_REQUESTS, "korbench": UNIT_REQUESTS}


# ----------------------------------------------------------------------------- calls
def _intent(ledger, logical, system, user, cap):
    return digest({"manifest_hash": ledger.manifest["record_hash"], "role": "verifier", "logical_id": logical,
                   "system": system, "user": user, "max_tokens": cap})


def _deliver(ledger, logical, system, user, trace):
    """One verifier request under the v7 delivery rule -> (ok receipt or None, status). A closed length truncation
    gets exactly one length recovery bound to the original intent; a still truncated, empty or filtered reply is a
    terminal unit result; any other undelivered reply stops the stage."""
    policy = ledger.manifest["recovery_policy"]
    cap = ledger.budget["verifier_max_tokens"]
    receipt = ledger.call("verifier", logical, system, user, cap)
    trace.append(vf._call_record(logical, receipt))
    if receipt.get("ok"):
        return receipt, "ok"
    if vf._closed_length(receipt):
        recovery = logical + ":length-recovery:1"
        receipt = ledger.call("verifier", recovery, system, user, policy["length_max_tokens"],
                              recovery_of=_intent(ledger, logical, system, user, cap))
        trace.append(vf._call_record(recovery, receipt))
        if receipt.get("ok"):
            return receipt, "ok_after_recovery"
        if vf._closed_length(receipt) or vf._closed_empty(receipt) or vf._closed_filter(receipt):
            trace.append({"stage": recovery, "status": "truncated_or_empty"})
            return None, "truncated_or_empty"
        raise LearningPending("verifier_call_undelivered")
    if vf._closed_empty(receipt):
        trace.append({"stage": logical, "status": "truncated_or_empty"})
        return None, "truncated_or_empty"
    if vf._closed_filter(receipt):
        trace.append({"stage": logical, "status": "filtered"})
        return None, "filtered"
    raise LearningPending("verifier_call_undelivered")


def call_json(ledger, logical, system, user, trace):
    """One verifier-role call -> (JSON object or None, status): delivery rule, then one bounded format retry that
    follows the same delivery rule."""
    policy = ledger.manifest["recovery_policy"]
    if len((system + user).encode()) > vf.MAX_PROMPT_BYTES:
        trace.append({"stage": logical, "status": "prompt_too_large"})
        return None, "prompt_too_large"
    receipt, status = _deliver(ledger, logical, system, user, trace)
    if receipt is None:
        return None, status
    try:
        return vf._decode(receipt["response"], policy["reflection_parser"]), status
    except (ValueError, TypeError, KeyError, NativeJSONError) as exc:
        reason = vf._json_reason(exc, receipt.get("response"))
        retry = logical + ":format-retry:1"
        again, status = _deliver(ledger, retry, system, user + vf.JSON_RETRY_NOTE.format(reason=reason), trace)
        trace.append({"stage": retry, "retry_of": reason[:200]})
        if again is None:
            return None, status
        try:
            return vf._decode(again["response"], policy["reflection_parser"]), "ok_after_retry"
        except (ValueError, TypeError, KeyError, NativeJSONError):
            trace.append({"stage": retry, "status": "invalid_json_after_retry"})
            return None, "invalid_json_after_retry"


def _terminal(trace):
    return any(type(t) is dict and t.get("status") in TERMINAL for t in trace)


# ----------------------------------------------------------------------------- hypotheses
def propose_hypotheses(ledger, value, step, folder, summary, views, rubric, limits, view_fit=None):
    path = folder / "hypotheses.json"
    if path.exists():
        record = read_json(path, sealed=True)
        require(record["manifest_hash"] == value["record_hash"] and record["step"] == step, "Hypotheses replay changed")
        return record
    benchmark = value["benchmark"]
    trace, hypotheses, status, clipped = [], [], "invalid", []
    case_ids = [v["case_id"] for v in views]
    text = profile_text(benchmark)
    system, user = hypothesis_messages(benchmark, text, rubric["policy"], summary, views, limits)
    reply, delivery = call_json(ledger, f"ae:{step}:diagnoser", system, user, trace)
    if reply is None:
        status = delivery
    else:
        try:
            hypotheses, status = parse_hypotheses(reply, case_ids, limits), "ok"
            clipped = clip_hypothesis_texts(reply)[1]
        except (ValueError, TypeError, KeyError) as error:
            if limits["max_diagnoser_calls_per_step"] < 2:
                status = "invalid_hypotheses_no_repair_budget:" + str(error)[:120]
            else:
                repair = {"previous_reply": reply, "validation_error": f"{type(error).__name__}: {str(error)[:500]}"}
                system, user = hypothesis_messages(benchmark, text, rubric["policy"], summary, views, limits, repair=repair)
                reply, delivery = call_json(ledger, f"ae:{step}:diagnoser:repair", system, user, trace)
                if reply is None:
                    status = delivery
                else:
                    try:
                        hypotheses, status = parse_hypotheses(reply, case_ids, limits), "ok_after_repair"
                        clipped = clip_hypothesis_texts(reply)[1]
                    except (ValueError, TypeError, KeyError) as again:
                        status = "invalid_hypotheses:" + str(again)[:120]
    record = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step, "status": status,
                   "hypotheses": hypotheses, "cases": case_ids, "rubric_hash": rubric["policy_hash"],
                   "profile_hash": digest(text), "summary_hash": digest(summary), "trace": trace,
                   # what the diagnoser saw of each case's public task (original lengths, truncated fields)
                   "case_task_text": {v["case_id"]: {"chars": v["task_text_chars"], "truncated": v["task_text_truncated"],
                                                     "output_truncated": v["generated_output_truncated"]}
                                      for v in views},
                   "view_fit": view_fit,  # the byte fit of the serialized diagnoser prompt (scale, size, target)
                   "clipped_text_fields": clipped,  # over-long hypothesis texts clipped to their bounds
                   "hypotheses_are_not_task_truth": True})
    write_json(path, record)
    return record


# ----------------------------------------------------------------------------- checks per case
def _execute(ledger, folder, token, group, executor, public, output, probes):
    """One container run of a probe group with a durable intent (an open intent is never re-run)."""
    intent_path = folder / "executions" / f"{token}-{group}.intent.json"
    receipt_path = folder / "executions" / f"{token}-{group}.json"
    if receipt_path.exists():
        receipt = read_json(receipt_path, sealed=True)
        require(receipt["evidence_hash"] == token and receipt["group"] == group, "Execution replay changed")
        return receipt["execution"]
    if intent_path.exists():
        raise LearningPending("interrupted_probe_execution")
    write_json(intent_path, seal({"protocol": PROTOCOL, "manifest_hash": ledger.manifest["record_hash"],
                                  "evidence_hash": token, "group": group, "probes": probes}))
    execution = executor(public, output, probes)
    write_json(receipt_path, seal({"protocol": PROTOCOL, "manifest_hash": ledger.manifest["record_hash"],
                                   "evidence_hash": token, "group": group,
                                   "execution": {k: v for k, v in execution.items() if k != "metrics"},
                                   "details": {k: vf._trace_message(v) for k, v in
                                               ((execution.get("metrics") or {}).get("details") or {}).items()}}))
    return execution


def _check_record(token, case, index, probe, *, review, executed, outcome, evidence, grade_value, basis, note=None):
    return {"check_id": f"{token[:12]}/{index}", "hypothesis_id": probe.get("hypothesis_id"), "case_id": case["case_id"],
            "evidence_hash": token, "host_status": case["host_status"], "kind": probe["kind"],
            "assertion": describe(probe), "contract_quote": probe["contract_quote"],
            "input_legality": None if review is None else {"reviewed": True, "keep": review["keep"],
                                                            "reason": review["reason"][:300],
                                                            "fact_question": review.get("fact_question"),
                                                            "revision_review": review.get("revision_review"),
                                                            "revision_fact_question": review.get("revision_fact_question"),
                                                            "revision_admitted": review.get("revision_admitted")},
            "expected_basis": basis, "executed": executed, "outcome": outcome, "observation": evidence,
            "grade": grade_value, "note": note,
            "uncertainty": "model-derived expectation; limited-blinding review; execution decides the assertion, "
                           "not the explanation"}


def _review(ledger, step, token, public, probes, rubric, trace, *, revision=False):
    """The limited-blinding review of a probe list; None when unavailable."""
    system, user = blind_review_messages(public, probes, rubric["policy"], revision=revision)
    suffix = ":revision" if revision else ""
    reply, _ = call_json(ledger, f"ae:{step}:review{suffix}:{token[:16]}", system, user, trace)
    if reply is None:
        return None
    try:
        return vf.parse_reviews(reply, len(probes))
    except (ValueError, TypeError, KeyError) as exc:
        trace.append({"stage": "review" + suffix, "status": "invalid_reviews", "error": type(exc).__name__})
        return None


ERROR_KINDS = ("task_error_candidate", "coverage_gap", "delivery", "environment")  # hypotheses about why outputs FAIL
CONTROL_VERSION = "passed-case-controls-v1"


def control_assignment(hypotheses, cases, per_case):
    """Controls for the error hypotheses: a hypothesis that explains failed outputs predicts that its violation is
    ABSENT from passing ones, and until now nothing looked (10/11 audit: leads such as 'failed on 4 of 4 failed and 0
    of 0 passed cases'). Each PASSED representative case gets up to ``per_case`` error hypotheses that do not already
    reference it, assigned round-robin over the passed cases in case order (deterministic). Returns
    {case_id: [hypothesis ids]}."""
    errors = [h for h in hypotheses if h["kind"] in ERROR_KINDS]
    assigned, cursor = {}, 0
    for case in cases:
        if case["host_status"] != "pass" or not errors:
            continue
        own = {h["id"] for h in hypotheses if case["case_id"] in h["applies_to"] or case["case_id"] in h["preserve"]}
        # one cursor over the STABLE hypothesis order, skipping the hypotheses that already reference this case (a
        # cursor over per-case filtered lists starved some hypotheses); this spreads controls fairly but cannot
        # guarantee one for every hypothesis under every exclusion pattern -- the sealed counts say what was assigned
        picked, steps = [], 0
        while len(picked) < per_case and steps < len(errors):
            hypothesis = errors[(cursor + steps) % len(errors)]
            steps += 1
            if hypothesis["id"] not in own:
                picked.append(hypothesis["id"])
                advance = steps
        if picked:
            assigned[case["case_id"]] = picked
            cursor = (cursor + advance) % len(errors)
    return assigned


def check_case(ledger, value, step, folder, case, pair, rubric, hypotheses, limits, executor, state_executor, researcher,
               controls=()):
    """All checks of one representative case (sealed record under diagnosis/<step>/checks). ``controls`` names the
    focus hypotheses this PASSED case serves as a control for."""
    token = case["token"]
    path = folder / "checks" / (token + ".json")
    if path.exists():
        record = read_json(path, sealed=True)
        require(record["manifest_hash"] == value["record_hash"] and record["step"] == step, "Check replay changed")
        return record
    benchmark = value["benchmark"]
    public, output = pair["item"]["task"]["public"], pair["row"]["output"]["output"]
    text = vf.task_text(benchmark, public)
    focus = [{"hypothesis_id": h["id"], "kind": h["kind"], "statement": h["statement"], "mechanism": h["mechanism"],
              "supports": h["discriminating_observation"]["supports"],
              "excludes": h["discriminating_observation"]["excludes"], "needs_fact": h["needs_fact"],
              # a control entry is given the NEUTRAL role "probe": the per-case prompt is not told that this output
              # passed the host audit (the control status stays host-side, in the sealed record)
              "role": ("probe" if h["id"] in controls else
                       "explains" if case["case_id"] in h["applies_to"] else "preserves")} for h in hypotheses]
    ids = {h["id"] for h in hypotheses}
    trace, records, rejected_all, research_summary = [], [], {}, None
    if benchmark == "bigcodebench":
        system, user = check_messages(public, output, rubric["policy"], focus)
        reply, status = call_json(ledger, f"ae:{step}:checks:{token[:16]}", system, user, trace)
        probes, rejected = [], {}
        if reply is not None:
            try:
                probes, rejected = parse_check_probes(reply, text, ids, limits["max_checks_per_case"])
            except (ValueError, TypeError, KeyError) as exc:
                rejected = {"envelope": str(exc)[:200]}
                trace.append({"stage": "checks", "status": "invalid_probes", "error": type(exc).__name__,
                              "detail": str(exc)[:200]})
            rejected_all["parse"] = rejected
            if rejected and not any(r.startswith(NOT_APPLICABLE) for r in rejected.values()) and not probes:
                # 10/9 run: 4 of 16 cases lost every probe to field-level strictness; one repair with the exact errors
                system2, user2 = repair_messages(system, user, rejected, reply)
                again, status = call_json(ledger, f"ae:{step}:checks:{token[:16]}:repair", system2, user2, trace)
                if again is not None:
                    try:
                        probes, rejected_again = parse_check_probes(again, text, ids, limits["max_checks_per_case"])
                        rejected_all["repair"] = rejected_again
                        # the repaired reply is the effective response: its own rejections decide what follows
                        reply, rejected = again, rejected_again
                    except (ValueError, TypeError, KeyError) as exc:
                        rejected_all["repair"] = {"envelope": str(exc)[:200]}
        effective = rejected  # the rejection map of the response the records are built from (attempt history above)
        probes, duplicates = deterministic_admissibility(probes)
        rejected_all["deterministic"] = duplicates
        reviews = _review(ledger, step, token, public, probes, rubric, trace) if probes else None
        research, unresolved_revisions = None, set()
        if probes and reviews is not None and researcher is not None:
            research = researcher(public, probes, reviews, token, trace)
            if research is not None:
                reviews, probes = research["reviews"], research["probes"]
                if research["revised"]:
                    # a revised expectation is a new assertion: it needs its own limited-blinding review. It executes
                    # only with ALL of: Research approval with documentary provenance (keep + citation), the second
                    # review's keep, and no fact question raised by that review. The second review can never re-admit
                    # a revision Research rejected, and a question it raises leaves the check unresolved.
                    revised = [probes[i] for i in research["revised"]]
                    second = _review(ledger, step, token, public, revised, rubric, trace, revision=True)
                    for position, index in enumerate(research["revised"]):
                        verdict = None if second is None else second[position]
                        approved = bool(reviews[index]["keep"]) and research["per_index"][str(index)]["keep"]
                        question = None if verdict is None else verdict.get("fact_question")
                        reviews[index]["revision_review"] = None if verdict is None else verdict["reason"][:300]
                        reviews[index]["revision_fact_question"] = question
                        reviews[index]["revision_admitted"] = bool(approved and verdict is not None and verdict["keep"]
                                                                   and not question)
                        if reviews[index]["revision_admitted"]:
                            continue
                        unresolved_revisions.add(index)  # its documentary basis no longer stands for an executed check
                        if not approved:
                            reviews[index]["keep"] = False
                            reviews[index]["reason"] = ("revised expectation rejected by Research (a second review "
                                                        "cannot re-admit it): " + reviews[index]["reason"])[:800]
                        elif verdict is None or not verdict["keep"]:
                            reviews[index]["keep"] = False
                            reviews[index]["reason"] = ("revised expectation not kept by its second review: "
                                                        + (reviews[index]["reason"] if verdict is None else verdict["reason"]))[:800]
                        else:
                            # kept, but the second review asks a new fact question: unresolved, never executed
                            reviews[index]["keep"], reviews[index]["fact_question"] = True, question
                research_summary = {"record_hash": research["record_hash"], "status": research["status"],
                                    "documented": research["documented"], "revised": research["revised"],
                                    "new_information": research["new_information"]}
        documented = (set(research["documented"]) if research is not None else set()) - unresolved_revisions
        bases = {i: ("documentation" if i in documented else "contract") for i in range(len(probes))}
        groups = {"standard": [], "state": []}
        for index, probe in enumerate(probes):
            review = None if reviews is None else reviews[index]
            if review is not None and review["keep"] and not review["fact_question"]:
                groups["state" if probe["kind"] == STATE_KIND else "standard"].append((index, probe))
        if _terminal(trace):
            # v7 rule: a row any of whose verifier replies was a terminal unit result gets no executed verdict
            trace.append({"stage": "row", "status": "no_verdict_after_terminal_delivery"})
            groups = {"standard": [], "state": []}
        outcomes = {}
        for group, runner in (("standard", executor), ("state", state_executor)):
            members = groups[group]
            if not members:
                continue
            execution = _execute(ledger, folder, token, group, runner, public, output, [p for _, p in members])
            for (index, _), outcome in zip(members, vf.probe_outcomes(execution, [p for _, p in members])):
                outcomes[index] = outcome
        for index, probe in enumerate(probes):
            review = None if reviews is None else reviews[index]
            outcome = outcomes.get(index)
            executed = outcome is not None
            value_grade = grade(executed=executed, outcome=None if outcome is None else outcome["outcome"],
                                review=review, basis=bases[index], probe=probe)
            note = None
            if not executed:
                note = ("review unavailable" if review is None else
                        "unresolved fact question: not executed" if review["fact_question"] and review["keep"] else
                        "dropped by the limited-blinding review: " + review["reason"][:120] if not review["keep"] else
                        "not executed")
            elif probe["kind"] == STATE_KIND and probe["expected"]["relation"] == "changed" and outcome["outcome"] == "fail":
                note = "ambiguous: the input may already be in its final state"
            records.append({**_check_record(token, case, index, probe, review=review, executed=executed,
                                            outcome=None if outcome is None else outcome["outcome"],
                                            evidence=None if outcome is None else outcome["evidence"],
                                            grade_value=value_grade, basis=bases[index], note=note),
                            "research": None if research is None else research["per_index"].get(str(index))})
        # a probe the contract does not impose (the state cue) is evidence too: NOT APPLICABLE, never hard feedback
        for position, reason in sorted(effective.items()):
            if reason.startswith(NOT_APPLICABLE) and reply is not None:
                raw = reply["probes"][int(position)] if type(reply.get("probes")) is list and int(position) < len(reply["probes"]) else {}
                # the probe as the parser read it: the same surface repairs (bound hypothesis id, a quote relocated to
                # its verbatim task line), else such a record lost its hypothesis or vanished (review of 10/11)
                raw = normalize_probe(raw, ids, text)
                quote = raw.get("contract_quote") if type(raw) is dict and type(raw.get("contract_quote")) is str else ""
                if vf.quote_in(quote or "", text):
                    records.append({"check_id": f"{token[:12]}/r{position}", "hypothesis_id": raw.get("hypothesis_id") if raw.get("hypothesis_id") in ids else None,
                                    "case_id": case["case_id"], "evidence_hash": token, "host_status": case["host_status"],
                                    "kind": str(raw.get("kind"))[:20], "assertion": "state check the contract does not impose",
                                    "contract_quote": quote[:600], "input_legality": None, "expected_basis": "contract",
                                    "executed": False, "outcome": None, "observation": None, "grade": "not_applicable",
                                    "note": reason[len(NOT_APPLICABLE):].strip()[:160], "research": None,
                                    "uncertainty": "deterministic cue check on the contract quote"})
    else:
        system, user = judge_focus_messages(benchmark, public, output, rubric["policy"], focus)
        reply, status = call_json(ledger, f"ae:{step}:judge:{token[:16]}", system, user, trace)
        effective = {}
        if reply is not None:
            try:
                checks, effective = parse_judged_checks(reply, text, ids)
                rejected_all["parse"] = effective
            except (ValueError, TypeError, KeyError) as exc:
                checks, effective = [], {"envelope": str(exc)[:200]}
                rejected_all["parse"] = effective
                trace.append({"stage": "judge", "status": "invalid_checks", "error": type(exc).__name__})
            for index, check in enumerate(checks):
                probe = {"kind": "judged_obligation", "contract_quote": check["contract_quote"],
                         "hypothesis_id": check["hypothesis_id"], "obligation": check["obligation"]}
                records.append({**_check_record(token, case, index, probe, review=None, executed=False,
                                                outcome=check["verdict"], evidence=check["evidence"],
                                                grade_value=grade(executed=False, outcome=check["verdict"], review=None,
                                                                  basis="model_judgment", judged=True),
                                                basis="model_judgment", note="model judgment, not an executed check"),
                                "assertion": "judged: " + check["obligation"][:240], "research": None})
    record = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step, "evidence_hash": token,
                   "case_id": case["case_id"], "host_status": case["host_status"], "rubric_hash": rubric["policy_hash"],
                   "focus": focus, "controls": sorted(controls), "checks": records, "rejected": rejected_all,
                   "research": research_summary,
                   "delivery": case_delivery(records, reply, effective), "trace": trace})
    write_json(path, record)
    return record


def unassigned_focus(case_id):
    """The pseudo-hypothesis of a representative case that no hypothesis references."""
    return {"id": UNASSIGNED, "kind": "unexplained",
            "statement": "No hypothesis was assigned to this case. Check the main obligations of the public contract on "
                         "this output.",
            "mechanism": "unassigned case: a generic check of the public contract's main obligations",
            "discriminating_observation": {"supports": "a main obligation of the public contract is violated by the output",
                                           "excludes": "the main obligations of the public contract hold on the output"},
            "needs_fact": None, "applies_to": [case_id], "preserve": []}


def case_delivery(records, reply, effective):
    """How one case's check request ended, judged on the EFFECTIVE response (the repaired reply when a repair parsed,
    else the first reply) and its own rejection map: ``checks`` (at least one graded check record, whatever its grade
    -- a pending or not-applicable item is a legitimate result), ``format_failure`` (no record because the reply was
    undelivered or undecodable, or a proposed item failed validation) or ``no_checks`` (a valid reply that proposed
    nothing, or only checks the contract does not impose). A format failure is a delivery problem, never evidence
    about the task."""
    if records:
        return "checks"
    failed = reply is None or any(not str(r).startswith(NOT_APPLICABLE) for r in effective.values())
    return "format_failure" if failed else "no_checks"


# ----------------------------------------------------------------------------- the step
def run_diagnosis(ledger, value, root, step, pairs, unknown, *, rubric, executor, state_executor, researcher=None,
                  reserve_calls=0):
    """Diagnose one step's bound rows. ``reserve_calls`` is the protected ledger capacity of the post-update
    challenge (and the updater): diagnosis admits a case only while its estimated calls fit before that reserve.
    Returns the material the stage needs: sealed report records by evidence hash, the bounded summary text and the
    chain fields."""
    extension = value["active_evidence"]
    arms, limits = extension["arms"], extension["limits"]
    folder = root / "diagnosis" / str(step)
    saved = {p["token"]: p["saved"] for p in pairs}
    triage, host_only = triage_record(value, step, pairs, saved, unknown, limits)
    if not (folder / "triage.json").exists():
        write_json(folder / "triage.json", triage)
        write_json(root / "host_only" / "triage" / (str(step) + ".json"), host_only)
    else:
        require(read_json(folder / "triage.json", sealed=True) == triage, "Triage replay changed")
    pairs_by_token = {p["token"]: p for p in pairs}
    cases = triage["cases"]
    def prompt_bytes(candidate_views):
        system, user = hypothesis_messages(value["benchmark"], profile_text(value["benchmark"]), rubric["policy"],
                                           triage["summary"], candidate_views, limits)
        return len((system + user).encode())

    views, view_fit = fitted_case_views(value["benchmark"], pairs_by_token, cases, limits, prompt_bytes)
    budget = value["budget"]
    per_case = CASE_CALL_ESTIMATE[value["benchmark"]]

    def room(extra):
        costs = ledger.snapshot()
        return (costs["logical_calls"] + extra + reserve_calls <= budget["max_api_calls"]
                and costs.get("verifier_calls", 0) + extra <= budget["max_verifier_calls"])

    base = {"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step, "arm": arms["feedback"],
            "triage_hash": triage["record_hash"], "cases": [c["case_id"] for c in cases], "reserve_calls": reserve_calls}
    if not room(limits["max_diagnoser_calls_per_step"] * UNIT_REQUESTS + per_case):
        summary = seal({**base, "status": "skipped_budget_reserve", "hypotheses": [], "checks": [], "observations": [],
                        "report_hashes": {}, "summary_text": None, "research": [], "research_new_information": False,
                        "research_consulted": False, "fact_needs": []})
        write_json(folder / "summary.json", summary)
        return _result(summary, {}, None)
    hypotheses = propose_hypotheses(ledger, value, step, folder, triage["summary"], views, rubric, limits,
                                    view_fit=view_fit)
    if not hypotheses["hypotheses"]:
        summary = seal({**base, "status": "no_hypotheses:" + hypotheses["status"], "hypotheses_hash": hypotheses["record_hash"],
                        "hypotheses": [], "checks": [], "observations": [], "report_hashes": {}, "summary_text": None,
                        "research": [], "research_new_information": False, "research_consulted": False, "fact_needs": []})
        write_json(folder / "summary.json", summary)
        return _result(summary, {}, None)
    checks, research_records, skipped, deliveries, unassigned = [], [], [], [], []
    by_id = {h["id"]: h for h in hypotheses["hypotheses"]}
    control_map = control_assignment(hypotheses["hypotheses"], cases, limits["max_checks_per_case"])
    for case in cases:
        mine = [h for h in hypotheses["hypotheses"] if case["case_id"] in h["applies_to"] or case["case_id"] in h["preserve"]]
        controls = control_map.get(case["case_id"], [])
        # a passed case first serves as a control for error hypotheses (listed first: at most two checks per case)
        mine = [by_id[i] for i in controls] + mine
        if not mine:
            # every representative case has a disposition: a case no hypothesis references gets a generic check
            # attempt under the pseudo-hypothesis u0 (it is never silently skipped)
            unassigned.append(case["case_id"])
            mine = [unassigned_focus(case["case_id"])]
        if not (folder / "checks" / (case["token"] + ".json")).exists() and not room(per_case):
            skipped.append(case["case_id"])  # the protected challenge/updater capacity comes first
            continue
        record = check_case(ledger, value, step, folder, case, pairs_by_token[case["token"]], rubric, mine, limits,
                            executor, state_executor, researcher, controls=controls)
        checks.extend(record["checks"])
        deliveries.append(record["delivery"])
        if record.get("research"):
            research_records.append({"evidence_hash": case["token"], **record["research"]})
    verdicts = observations(hypotheses["hypotheses"], checks, cases, controls=control_map)
    needs = fact_needs(hypotheses["hypotheses"], checks, research_records, arm=arms["feedback"])
    leads = judged_leads(hypotheses["hypotheses"], checks, cases, controls=control_map)
    reports = {}
    for case in cases:
        mine = [c for c in checks if c["evidence_hash"] == case["token"]]
        if not mine:
            continue
        text = render_report(mine, limits["report_chars"])
        report = seal_report(value, step, case["token"], case["host_status"], mine, text)
        write_json(folder / "reports" / (case["token"] + ".json"), report)
        reports[case["token"]] = report
    # an unrouted fact need is itself evidence the analysts must see (as unresolved), even when no check was admitted
    summary_text = render_summary(hypotheses["hypotheses"], verdicts, checks, rubric["policy"], limits["summary_chars"],
                                  fact_needs=needs, leads=leads,
                                  rows=(len(reports), len({c["evidence_hash"] for c in checks if c["executed"]}),
                                        len(pairs))) if checks or needs else None
    summary = seal({**base, "status": "completed", "hypotheses_hash": hypotheses["record_hash"],
                    "cases_skipped_for_reserve": skipped,
                    "hypotheses": [{"id": h["id"], "kind": h["kind"], "needs_fact": h["needs_fact"]} for h in hypotheses["hypotheses"]],
                    "checks": [{"check_id": c["check_id"], "hypothesis_id": c["hypothesis_id"], "evidence_hash": c["evidence_hash"],
                                "grade": c["grade"], "executed": c["executed"]} for c in checks],
                    "grades": {g: sum(c["grade"] == g for c in checks) for g in sorted({c["grade"] for c in checks})},
                    "observations": verdicts, "report_hashes": {t: r["record_hash"] for t, r in sorted(reports.items())},
                    "summary_text": summary_text, "research": research_records,
                    "research_new_information": any(r["new_information"] for r in research_records),
                    "research_consulted": bool(research_records), "fact_needs": needs,
                    "judged_leads": leads, "unassigned_cases": unassigned,
                    "controls": {"version": CONTROL_VERSION, "assignment": control_map},
                    # what actually reached the analysts' package (a format failure is not evidence about a task)
                    "delivery": {"cases": len(cases), "cases_attempted": len(deliveries),
                                 "cases_with_checks": deliveries.count("checks"),
                                 "cases_format_failed": deliveries.count("format_failure"),
                                 "cases_without_checks": deliveries.count("no_checks"),
                                 "cases_skipped_for_reserve": len(skipped), "cases_unassigned": len(unassigned),
                                 "rows_with_reports": len(reports),
                                 "summary_present": summary_text is not None}})
    write_json(folder / "summary.json", summary)
    return _result(summary, reports, summary_text)


def _result(summary, reports, summary_text):
    return {"status": summary["status"], "reports": reports, "summary": summary_text, "summary_hash": summary["record_hash"],
            "rows_with_evidence": len(reports), "hypotheses": summary["hypotheses"], "checks": summary["checks"],
            "observations": summary["observations"], "research": summary.get("research", []),
            "research_new_information": summary.get("research_new_information", False),
            "research_consulted": summary.get("research_consulted", False), "fact_needs": summary.get("fact_needs", []),
            "triage_hash": summary["triage_hash"], "delivery": summary.get("delivery")}
