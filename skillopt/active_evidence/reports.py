"""Itemized evidence reports for the analysts and the step-level diagnosis summary.

A report lists each check of one row by grade (CONFIRMED VIOLATION / CONFIRMED PRESERVED / PENDING / UNKNOWN /
NOT APPLICABLE / ERROR) with its hypothesis id, what it asserted, the contract quote and the observation; a
passed row may carry PRESERVED items. The summary keeps assertion confirmation (executed checks) apart from
hypothesis inference (consistent / not observed / undecided -- tentative): which violations were confirmed, which
predicted violations did not occur, which behaviors must be preserved, the tentative edit scope, the exceptions and
what remains unproven. The rubric guides the checker only: none of its fields is quoted to the analysts (its
"exceptions" sentence used to be, and came back as a Skill rule). Bounded and label-free."""
from __future__ import annotations

from skillopt.coevolution_v5.core import seal

from . import PROTOCOL
from .updater import TRUNCATION

UNASSIGNED = "u0"  # the pseudo-hypothesis of a representative case no hypothesis references (diagnosis.py)

LABELS = {"confirmed_violation": "CONFIRMED VIOLATION", "confirmed_preserved": "CONFIRMED PRESERVED",
          "pending_explanation": "PENDING", "unknown": "UNKNOWN", "not_applicable": "NOT APPLICABLE",
          "format_or_env_error": "ERROR"}
ORDER = ("confirmed_violation", "confirmed_preserved", "pending_explanation", "not_applicable",
         "format_or_env_error", "unknown")


def _bounded(text, limit):
    return text if len(text) <= limit else text[:limit] + TRUNCATION


JUDGED_KIND = "judged_obligation"
JUDGED_LABELS = {"fail": "JUDGED FAIL", "pass": "JUDGED PASS", "unknown": "JUDGED UNKNOWN"}
JUDGED_ORDER = ("fail", "unknown", "pass")


def judged_verdict(check):
    """The stored verdict of a judged check, else None. A judged pass or fail is a model judgment whose epistemic
    grade stays pending; a judged unknown keeps the grade unknown."""
    if check.get("kind") != JUDGED_KIND or check.get("grade") not in ("pending_explanation", "unknown"):
        return None
    return check["outcome"] if check.get("outcome") in JUDGED_LABELS else "unknown"


def _label(check):
    verdict = judged_verdict(check)
    return LABELS[check["grade"]] if verdict is None else JUDGED_LABELS[verdict]


def _order(check):
    verdict = judged_verdict(check)
    return (ORDER.index(check["grade"]), 0 if verdict is None else JUDGED_ORDER.index(verdict), check["check_id"])


def render_report(checks, limit):
    """The per-row report (checks of one execution evidence, graded). A judged check shows its verdict (JUDGED
    FAIL / PASS / UNKNOWN): a lead from a model judgment, never a confirmed fact."""
    lines = [f"Evidence report: {len(checks)} diagnostic check(s) on this output, graded (limited-blinding review; "
             "no expected answer or hidden test is shown)."]
    for check in sorted(checks, key=_order):
        tag = f"[{check['hypothesis_id']}] " if check.get("hypothesis_id") else ""
        line = f"- {_label(check)} {tag}{check['assertion'][:260]} (contract: \"{check['contract_quote'][:160]}\")"
        if check.get("observation"):
            line += ": " + check["observation"][:300]
        if check.get("note"):
            line += " -- " + check["note"][:160]
        lines.append(line)
    return _bounded("\n".join(lines), limit)


def observations(hypotheses, checks, cases, controls=None):
    """Per hypothesis, a TENTATIVE inference kept apart from assertion confirmation. ``consistent``: an executed check
    bound to it violated as it predicted on a HOST-FAILED case it explains (consistency, not proof of cause).
    ``also_on_controls``: that, and the same hypothesis's executed check was also violated on a passing control case
    -- the hypothesis does not cleanly separate the checked failing and passing outputs; whether the probe's
    expectation, the contract reading or the hidden tests' coverage is at fault is not established. ``not_observed``
    / ``preserved``: EVERY case it explains has at least one check bound to it and every such check was executed and
    preserved (``preserved`` when all those cases are host-pass, i.e. a hypothesis about what succeeds). A case it
    explains without any check (no admissible probe) leaves the inference ``undecided`` with the uncovered count --
    missing coverage is never read as absence of a violation. ``controls`` = the sealed control assignment
    {case_id: [hypothesis ids]} (diagnosis.control_assignment)."""
    status = {c["case_id"]: c["host_status"] for c in cases}
    controls = controls or {}
    result = []
    for hypothesis in hypotheses:
        mine = [c for c in checks if c.get("hypothesis_id") == hypothesis["id"]]
        explaining = [c for c in mine if c["case_id"] in hypothesis["applies_to"]]
        covered = {c["case_id"] for c in explaining}
        uncovered = [case_id for case_id in hypothesis["applies_to"] if case_id not in covered]
        violated = [c["check_id"] for c in explaining if c["grade"] == "confirmed_violation"]
        violated_on_failed = [c["check_id"] for c in explaining if c["grade"] == "confirmed_violation"
                              and status.get(c["case_id"]) == "fail"]
        preserved = [c["check_id"] for c in explaining if c["grade"] == "confirmed_preserved"]
        undecided = [c["check_id"] for c in explaining if c["grade"] not in {"confirmed_violation", "confirmed_preserved"}]
        all_pass = bool(hypothesis["applies_to"]) and all(status.get(c) == "pass" for c in hypothesis["applies_to"])
        assigned = sorted(case_id for case_id, ids in controls.items() if hypothesis["id"] in ids)
        control = [c for c in mine if c["case_id"] in assigned]
        control_violated = sorted({c["case_id"] for c in control if c["grade"] == "confirmed_violation"})
        if violated:
            verdict, basis = "consistent", violated
            if violated_on_failed and control_violated:
                verdict = "also_on_controls"
        elif preserved and not undecided and not uncovered:
            verdict, basis = ("preserved" if all_pass else "not_observed"), preserved
        else:
            verdict, basis = "undecided", []
        result.append({"hypothesis_id": hypothesis["id"], "kind": hypothesis["kind"], "verdict": verdict,
                       "control_cases_assigned": len(assigned),
                       "control_cases_checked": len({c["case_id"] for c in control}),
                       "control_cases_violated": len(control_violated),
                       "from_checks": basis, "checks": len(mine), "explained_cases": len(hypothesis["applies_to"]),
                       "uncovered_cases": len(uncovered),
                       "pending": sum(c["grade"] == "pending_explanation" for c in mine),
                       "unknown": sum(c["grade"] in {"unknown", "format_or_env_error", "not_applicable"} for c in mine),
                       "note": "tentative inference from executed checks; a violation is consistency, not proof of cause; "
                               "uncovered cases keep it undecided"})
    return result


def judged_leads(hypotheses, checks, cases, controls=None):
    """Per hypothesis (and the unassigned bucket), on how many FAILED representative cases a judged check failed,
    and separately on how many of its passing CONTROL cases (the sealed assignment: passed cases the hypothesis does
    not claim). Assigned, judged and judged-unknown controls are counted apart: an assignment does not guarantee the
    judge checked that hypothesis, and '0 of N judged failures' does not mean N judged passes. Other passed cases the
    hypothesis itself references (preserve / applies_to) are counted as ``claimed_pass_cases``, never as controls."""
    status = {c["case_id"]: c["host_status"] for c in cases}
    controls = controls or {}
    result = []
    for hypothesis_id in [h["id"] for h in hypotheses] + [UNASSIGNED]:
        judged = [c for c in checks if c.get("hypothesis_id") == hypothesis_id and judged_verdict(c) is not None]
        if not judged:
            continue
        assigned = {case_id for case_id, ids in controls.items() if hypothesis_id in ids}
        failed = [c for c in judged if status.get(c["case_id"]) == "fail"]
        control = [c for c in judged if c["case_id"] in assigned]
        claimed = [c for c in judged if status.get(c["case_id"]) == "pass" and c["case_id"] not in assigned]
        result.append({
            "hypothesis_id": hypothesis_id, "judged_checks": len(judged),
            "judged_unknown_checks": sum(judged_verdict(c) == "unknown" for c in judged),
            "fail_cases": len({c["case_id"] for c in failed}),
            "fail_cases_with_judged_fail": len({c["case_id"] for c in failed if judged_verdict(c) == "fail"}),
            "control_cases_assigned": len(assigned),
            "control_cases_judged": len({c["case_id"] for c in control}),
            "control_cases_with_judged_fail": len({c["case_id"] for c in control if judged_verdict(c) == "fail"}),
            "control_cases_with_judged_unknown": len({c["case_id"] for c in control if judged_verdict(c) == "unknown"}),
            "claimed_pass_cases": len({c["case_id"] for c in claimed}),
            "claimed_pass_cases_with_judged_fail": len({c["case_id"] for c in claimed if judged_verdict(c) == "fail"})})
    return result


def fact_needs(hypotheses, checks, research_records, *, arm):
    """Per hypothesis that declared a fact it depends on (``needs_fact``): whether on-demand Research was actually
    consulted for it and, when not, why. Research is reached only through a review's fact question on an admissible
    check, so a need can stay unrouted (no admissible check, no review, no question, or an arm without Research); the
    10/9 run r left such a need invisible (`research: []`). An unresolved need is reported as unresolved, never as
    absence of a problem."""
    by_case = {r["evidence_hash"]: r for r in research_records}
    result = []
    for hypothesis in hypotheses:
        question = hypothesis.get("needs_fact")
        if not question:
            continue
        mine = [c for c in checks if c.get("hypothesis_id") == hypothesis["id"]]
        admitted = [c for c in mine if c["grade"] != "not_applicable"]  # a rejected state cue was never admitted
        reviewed = [c for c in admitted if (c.get("input_legality") or {}).get("reviewed")]
        # Research is bound to the CHECK whose own review asked: a per-index resolution, or an open question on a
        # kept check of a case Research was run for (failed/unresolved Research leaves no per-index entry). A case's
        # Research never counts for another hypothesis's checks on the same case.
        consulted = [c for c in reviewed if c.get("research") is not None
                     or (c["input_legality"].get("fact_question") and c["input_legality"].get("keep")
                         and c["evidence_hash"] in by_case)]
        asked_dropped = [c for c in reviewed if c["input_legality"].get("fact_question") and not c["input_legality"].get("keep")]
        statuses = sorted({by_case[c["evidence_hash"]]["status"] for c in consulted if c["evidence_hash"] in by_case})
        if arm != "diagnosis_research":
            status = "not_consulted:arm_without_research"
        elif consulted:
            # several consulted checks may have met different Research outcomes (one case failed retrieval, another
            # was documented): aggregate honestly instead of reporting whichever check comes first
            status = "consulted:" + (statuses[0] if len(statuses) == 1 else "mixed")
        elif not admitted:
            status = "not_consulted:no_admissible_check"
        elif not reviewed:
            status = "not_consulted:no_check_reached_review"
        elif asked_dropped:
            status = "not_consulted:fact_question_only_on_dropped_checks"  # the researcher only takes kept questions
        else:
            status = "not_consulted:review_raised_no_fact_question"
        result.append({"hypothesis_id": hypothesis["id"], "question": question[:400], "status": status,
                       "checks": len(mine), "reviewed_checks": len(reviewed),
                       "consulted_checks": sorted(c["check_id"] for c in consulted), "research_statuses": statuses,
                       # resolved only by a check that keeps its documentary basis: a revision Research rejected,
                       # the second review dropped, or that review questioned again stays unresolved
                       "resolved": any(c.get("expected_basis") == "documentation"
                                       and c["input_legality"].get("revision_admitted") is not False for c in consulted),
                       "research_hashes": sorted({by_case[c["evidence_hash"]]["record_hash"] for c in consulted
                                                  if c["evidence_hash"] in by_case}),
                       "binding": "structural (this hypothesis's own checks); the declared question is not matched semantically"})
    return result


def render_summary(hypotheses, verdicts, checks, rubric, limit, fact_needs=(), leads=(), rows=None):
    """``leads`` = ``judged_leads``; ``rows`` = (rows with a report, rows with an executed check, known step rows)
    for the coverage statement."""
    by_id = {h["id"]: h for h in hypotheses}
    executed = [c for c in checks if c.get("executed")]
    sections = []
    supported = [v for v in verdicts if v["verdict"] == "consistent"]
    excluded = [v for v in verdicts if v["verdict"] == "not_observed"]
    kept = [v for v in verdicts if v["verdict"] == "preserved"]
    undecided = [v for v in verdicts if v["verdict"] == "undecided"]
    violations = [c for c in checks if c["grade"] == "confirmed_violation"]
    sections.append(f"Confirmed violations (executed checks): {len(violations)}" + ("; hypotheses consistent with them: "
                    + "; ".join(f"{v['hypothesis_id']} ({by_id[v['hypothesis_id']]['kind']}): "
                                f"{by_id[v['hypothesis_id']]['statement'][:220]}" for v in supported)
                    + " -- consistency, not proof of cause" if supported else "; no hypothesis is supported by an executed check"))
    sections.append("Predicted violations that did not occur (every explained case checked, every check preserved): "
                    + ("; ".join(f"{v['hypothesis_id']}: {by_id[v['hypothesis_id']]['statement'][:160]}" for v in excluded)
                       if excluded else "none"))
    blunt = [v for v in verdicts if v["verdict"] == "also_on_controls"]
    if blunt:
        sections.append("Also observed on passing control outputs (specificity and cause unresolved -- the probe's "
                        "expectation, the contract reading or the hidden tests' coverage may be at fault): "
                        + "; ".join(f"{v['hypothesis_id']} ({v['control_cases_violated']} of "
                                    f"{v['control_cases_checked']} checked control cases): "
                                    f"{by_id[v['hypothesis_id']]['statement'][:160]}" for v in blunt))
    partial = [v for v in undecided if v["uncovered_cases"]]
    if partial:
        sections.append("Incomplete coverage (explained cases without any admissible check; nothing inferred): "
                        + "; ".join(f"{v['hypothesis_id']} ({v['uncovered_cases']}/{v['explained_cases']} cases unchecked)"
                                    for v in partial))
    preserve = [c for c in checks if c["grade"] == "confirmed_preserved" and c["host_status"] == "pass"]
    sections.append("Behaviors to preserve: " + ("; ".join(
        f"{c['assertion'][:120]} (contract: \"{c['contract_quote'][:80]}\")" for c in preserve[:6])
        if preserve else "no preserved behavior was confirmed by an executed check")
        + ("; hypotheses about passing cases whose checks all held: " + ", ".join(v["hypothesis_id"] for v in kept)
           if kept else ""))
    if leads:
        sections.append("Judged leads (model judgments, nothing executed -- leads, not confirmed facts): " + "; ".join(
            f"{lead['hypothesis_id']}: a judged check failed on {lead['fail_cases_with_judged_fail']} of "
            f"{lead['fail_cases']} failed cases and on {lead['control_cases_with_judged_fail']} of "
            f"{lead['control_cases_judged']} judged passing controls ({lead['control_cases_assigned']} assigned)"
            + (f"; on {lead['claimed_pass_cases_with_judged_fail']} of {lead['claimed_pass_cases']} passed cases it "
               "claims" if lead["claimed_pass_cases"] else "")
            + (f" ({by_id[lead['hypothesis_id']]['mechanism'][:160]})" if lead["hypothesis_id"] in by_id else "")
            for lead in leads))
    coverage = "" if rows is None else (f" Reports cover {rows[0]} of {rows[2]} step rows; executed checks cover "
                                        f"{rows[1]}.")
    if supported:
        scope = "; ".join(by_id[v["hypothesis_id"]]["mechanism"][:200] for v in supported)
    elif violations:
        # a confirmed violation that no named hypothesis explains (an unassigned or preserve-only case): the violated
        # obligation is a fact about that output, the cause is not established
        scope = (f"{len(violations)} executed assertion(s) failed without a hypothesis that explains them: the "
                 "assertion's outcome is established, the correctness of its expectation and its cause are not; a "
                 "general procedure for the obligation may be proposed as tentative")
    elif not executed:
        # nothing could be executed (a judged domain, or no admissible probe): silence is not evidence
        scope = ("no check could be executed here, so the absence of confirmed violations is NOT evidence that nothing "
                 "should change; propose general, testable procedures from the traces and the judged leads (state them "
                 "as procedures, not as confirmed facts); do not add rules for not-applicable items")
    else:
        # executed is not the same as held: an executed check may have ended unknown, in an error, or pending
        held = sum(c["grade"] == "confirmed_preserved" for c in executed)
        scope = (f"no violation was confirmed: {held} executed check(s) held and {len(executed) - held} executed "
                 "check(s) are unresolved (unknown, error or pending -- they confirm nothing either way); they cover "
                 "few rows, so this does not argue against edits the traces themselves support; do not add rules for "
                 "not-applicable items")
    sections.append("Suggested edit scope (tentative): " + scope + coverage)
    not_applicable = [c for c in checks if c["grade"] == "not_applicable"]
    # The rubric's own fields (e.g. its "exceptions": when the CHECKER should abstain) never enter this summary: in
    # every SearchQA stage of 10/10-10/11 that sentence came back as a solver rule "abstain rather than guess" in the
    # Skill (audit of 10/11). Only the checks the contract did not impose are listed.
    if not_applicable:
        sections.append("Not applicable (checks the task's contract did not impose -- do not add rules for them): "
                        + "; ".join(c["assertion"][:100] for c in not_applicable[:4]))
    pending = sum(c["grade"] == "pending_explanation" for c in checks)
    unknown = sum(c["grade"] in {"unknown", "format_or_env_error"} for c in checks)
    unresolved = [f for f in fact_needs if not f["resolved"]]
    tail = (f"Unproven: {pending} pending explanation(s), {unknown} unknown/error check(s); undecided hypotheses: "
            + (", ".join(v["hypothesis_id"] for v in undecided) if undecided else "none")
            + ("; facts a hypothesis needs that Research did not resolve (unresolved -- do not encode them as rules): "
               + "; ".join(f"{f['hypothesis_id']} [{f['status']}]: {f['question'][:160]}" for f in unresolved)
               if unresolved else "")
            + ". Hypotheses are the diagnoser's conjectures; only executed checks are observations.")
    head = "\n".join(sections)
    if len(head) + 1 + len(tail) <= limit:
        return head + "\n" + tail
    # The caveats are never what the bound cuts first: reserve up to a third of the limit for the tail and truncate
    # the statements instead. Whatever the split, the result stays within limit + one marker (the updater's maximum).
    tail_budget = min(len(tail), max(limit // 3, 1))
    tail_part = tail if tail_budget == len(tail) else tail[:tail_budget] + TRUNCATION
    head_budget = limit - 1 - len(tail_part)
    if head_budget <= 0:
        return _bounded(tail, limit)
    head_part = head if len(head) <= head_budget else head[:head_budget] + TRUNCATION
    return head_part + "\n" + tail_part


def seal_report(value, step, token, host_status, checks, feedback):
    return seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step, "evidence_hash": token,
                 "host_status": host_status, "check_ids": [c["check_id"] for c in checks],
                 "grades": sorted(c["grade"] for c in checks), "feedback": feedback})
