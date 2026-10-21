"""The native Skill updater under itemized evidence.

``propose_native``'s reflect -> merge -> rank -> apply pipeline (same parser, retries, fallback provenance and
admissibility), with this mode's own trace validation and binding: an evidence report may sit on a passed OR a
failed step row, must equal the step's sealed report record for that execution evidence, and every trace must be
this step's fresh rollout of a STEP task (never a challenge task). The analyst systems explain how to read graded
evidence; the rubric is material inside the reports, never a system rule; a bounded step-level diagnosis summary
may be appended."""
from __future__ import annotations

import math
import warnings
from copy import deepcopy

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.continual_learning.contracts import check_skill, skill_budget
from skillopt.continual_learning.feedback import benchmark_for, project, task_description, validate_public
from skillopt.continual_learning.ledger import LearningPending
from skillopt.continual_learning.recovery import DELIVERY_VERSIONS
from skillopt.continual_learning.skillopt import _NativeBridge, _transport, native_sources
from skillopt.continual_learning.transfer import TRANSFER_PREAMBLE, TRANSFER_PREAMBLE_VERSION
from skillopt.validator_pilot.api import digest

from . import PROTOCOL

TRUNCATION = " …[truncated]"
EVIDENCE_PREAMBLE_VERSION = "active-evidence-report-guidance-v2"  # v2: JUDGED lines, no silence-as-evidence
SUMMARY_FORMAT_VERSION = "diagnosis-summary-v3"  # v3 (10/11): judged leads, coverage, no rubric sentence
EVIDENCE_PREAMBLE = (
    "\n\nEVIDENCE REPORTS. Some development rows carry an itemized evidence report from diagnostic checks of the "
    "generated output: executed public-contract checks, or judged obligations where nothing can be executed. Items "
    "are graded. CONFIRMED VIOLATION / CONFIRMED PRESERVED: an executed check whose input legality, contract "
    "obligation and expected value were each justified separately. PENDING: an observation whose explanation is not "
    "verified -- a lead, not a fact. UNKNOWN: undecidable. NOT APPLICABLE: the task's contract does not impose this "
    "obligation -- do not add a rule for it. ERROR: a format, environment or execution error, not a contract "
    "violation. JUDGED FAIL / JUDGED PASS / JUDGED UNKNOWN: where nothing can be executed, a model's judgment of one "
    "obligation of the public task on this output -- a lead that may motivate a general procedure, never a "
    "confirmed fact. No expected answer or hidden test is shown. Use CONFIRMED VIOLATION items to name the procedural "
    "mistake and the reusable check that would have caught it; use PRESERVED items to know what must not change; a "
    "step summary (when present) lists confirmed problems, judged leads with their counts on failed and passed "
    "cases, behaviors to preserve, a tentative edit scope, exceptions and what remains unproven. Reports cover only "
    "a few rows: the absence of a report or of a confirmed violation is never evidence that an output was right or "
    "that nothing should change. Never copy check inputs, expected values, quotes or task-specific entities into "
    "the skill: write the reusable procedure or check."
)
SUMMARY_HEADER = "\n\n## Diagnosis summary (this step)\n"
# Screened update mode only: the analysts' edits are measured before anything is kept, so distinct hypotheses should
# stay separable (appended to both analyst systems; every other mode's package is byte-identical to before).
SCREENED_PREAMBLE_VERSION = "screened-edit-guidance-v1"
SCREENED_PREAMBLE = (
    "\n\nMEASURED EDITS. Before anything is kept, your edits are tested on these development rows with the native "
    "checker: the complete candidate, the candidate without each edit, and each edit alone, against the current skill "
    "re-run as a control. Therefore keep distinct hypotheses SEPARABLE: one edit per distinct procedure or per distinct "
    "hypothesis about what the checker accepts (for example a shorter versus a fuller answer form), each self-contained "
    "and general. A plausible but unproven hypothesis is welcome as its own edit -- the measurement decides; an edit "
    "that only restates the current skill is not."
)
# The failure-message study arm (label feedback on development rows; never the method) replaces the evidence-report
# guidance for its message branch only; every other arm's analyst package stays byte-identical.
LABEL_PREAMBLE_VERSION = "development-failure-message-guidance-v1"
LABEL_PREAMBLE = (
    "\n\nFAILURE-MESSAGE FEEDBACK (study arm). Every FAILED development row carries, in its [verification] turn, the "
    "final exception messages of the hidden tests it failed (test name and message; traceback frames and paths "
    "removed; at most four tests per row). This is label feedback on development tasks: it tells you what the tests "
    "complained about, not how to fix a task. Hidden test code, expected answers and canonical solutions are not "
    "shown. Infer the general, reusable procedure or check that would have avoided each class of complaint (which "
    "documented behaviours implementations tend to miss); do not copy a task's expected value, test name, file name "
    "or literal into the skill as such."
)


# Analyst prompt profiles (prompt-chain experiment of 2026-10-13, docs/handoff/prompt-chain-design-20261013.md).
# "native" is the unchanged package. A profile only APPENDS its addendum to the analysts' system prompt; nothing
# else in the chain changes. Benchmark-agnostic text; it names no dataset, answer or rule.
ANALYST_PROFILES = {
    "native": "",
    "generalize_v1": """

## Generalization requirement (read after the transfer requirement)
The skill is judged on NEW tasks, and a long skill full of narrow rules hurts as often as it helps. Before
proposing edits:
1. Sort the batch into (a) answer-contract problems -- the response does not have the exact form, length, unit or
   wrapper the task asks for, or puts anything around the final answer; (b) procedure problems -- a step of reading,
   reasoning or checking was skipped or done wrongly; (c) one-off problems that share nothing with the others.
   Propose edits only for (a) and (b), never for (c).
2. Write each edit as ONE conditional rule of at most two sentences: "When <a property of the task that can be
   checked from the task text alone>, <what to do>, because <what goes wrong otherwise>". Only rules about the form
   of the final answer may be unconditional.
3. An edit needs the support of at least two trajectories of this batch, or of one trajectory plus a rule already
   in the skill that it sharpens. Say which in "reasoning".
4. Prefer "replace" (sharpen or merge an existing rule) over "append": if the skill already has a rule for the
   pattern, edit that rule instead of adding a second one.
5. Keep the skill short: do not restate the task's own instructions, do not add headings or examples, and do not
   add a rule that only says to be careful or to double-check in general.
""",
}


def analyst_systems(summary=None, *, label=False, screened=False, profile="native"):
    from skillopt.gradient.reflect import load_prompt

    require(profile in ANALYST_PROFILES, "Unknown analyst prompt profile")
    suffix = TRANSFER_PREAMBLE + (LABEL_PREAMBLE if label else EVIDENCE_PREAMBLE) + ANALYST_PROFILES[profile]
    if screened:
        suffix += SCREENED_PREAMBLE
    if summary:
        suffix += SUMMARY_HEADER + summary
    return {"error_system": load_prompt("analyst_error") + suffix,
            "success_system": load_prompt("analyst_success") + suffix}


def validate_traces(traces, benchmark, *, report_chars):
    require(type(traces) is list and traces, "Nonempty authorized development traces required")
    for trace in traces:
        require(type(trace) is dict and set(trace) == {"Inputs", "Generated Outputs", "Feedback", "evidence_hash"},
                "Only explicitly projected feedback fields are allowed")
        validate_public(benchmark, trace["Inputs"])
        require(type(trace["Generated Outputs"]) is str, "Actual output required")
        feedback = trace["Feedback"]
        require(type(feedback) is dict and set(feedback) in ({"status", "score"}, {"status", "score", "evidence"}),
                "Only scalar native feedback plus an itemized evidence report is allowed")
        if "evidence" in feedback:
            require(type(feedback["evidence"]) is str and 0 < len(feedback["evidence"]) <= report_chars + len(TRUNCATION),
                    "Oversized or empty evidence report")
        if feedback["status"] == "unknown":
            raise LearningPending("unknown_is_not_failure_feedback")
        require(feedback["status"] in {"pass", "fail"} and feedback["score"] == int(feedback["status"] == "pass"),
                "Inconsistent native hard feedback")
        token = trace["evidence_hash"]
        require(type(token) is str and len(token) == 64 and all(c in "0123456789abcdef" for c in token),
                "Bound execution evidence required")
    require(len({t["evidence_hash"] for t in traces}) == len(traces), "Duplicate development evidence")


def canonical_report(ledger, step, token):
    """The step's sealed report record of one execution evidence, re-read from the canonical path and verified."""
    path = ledger.root / "diagnosis" / str(step) / "reports" / (token + ".json")
    require(path.is_file(), "Evidence text without a sealed report for this evidence")
    report = read_json(path, sealed=True)
    verify(report)
    require(report["protocol"] == PROTOCOL and report["manifest_hash"] == ledger.manifest["record_hash"]
            and report["step"] == step and report["evidence_hash"] == token, "Report belongs to another step or stage")
    return report


def canonical_summary(ledger, step, text):
    """The step's sealed diagnosis summary, re-read and verified; the text handed to the analysts must be its own."""
    path = ledger.root / "diagnosis" / str(step) / "summary.json"
    require(path.is_file(), "Diagnosis summary without a sealed summary record")
    summary = read_json(path, sealed=True)
    verify(summary)
    require(summary["protocol"] == PROTOCOL and summary["manifest_hash"] == ledger.manifest["record_hash"]
            and summary["step"] == step and summary["status"] == "completed" and summary["summary_text"] == text,
            "Diagnosis summary differs from the sealed record")
    return summary


def bind_traces(traces, ledger, parent_skill, *, step, reports=None):
    """Every trace is this manifest's sealed evaluation of a STEP task (families from the sealed manifest, never
    from the caller) under the parent Skill and this step's rollout key (== step); evidence text equals the sealed
    canonical report of the same execution evidence (re-read from disk and verified, never a caller's dict)."""
    value = ledger.manifest
    panel = read_json(ledger.root / "panel.json")
    require(digest(panel) == value["panel_hash"], "Feedback panel is not authorized")
    tasks = {digest(task): task for task in panel["tasks"]}
    evidence = {}
    for path in sorted((ledger.root / "evaluations").glob("*.json")):
        row = read_json(path, sealed=True)
        evidence[row["record_hash"]] = (path, row)
    families = set(value["active_evidence"]["step_families"])
    scalar = value["active_evidence"]["arms"]["feedback"] == "scalar"
    for trace in traces:
        token = trace["evidence_hash"]
        require(token in evidence, "Feedback has no current learning execution evidence")
        path, row = evidence[token]
        request = row["request"]
        task = tasks.get(request["task_hash"])
        require(task is not None and request["manifest_hash"] == value["record_hash"] and request["role"] == "train"
                and task["partition"] == "development" and value["authorized_tasks"].get(request["task_hash"]) == "train"
                and request["candidate_hash"] == digest({"skill": parent_skill}) and request.get("rollout") == step,
                "Feedback role, task, parent, rollout or authorization mismatch")
        require(task["family_id"] in families, "A challenge-pool task can never enter reflection")
        require(read_json(ledger.root / "evaluation_intents" / path.name, sealed=True) == seal(request),
                "Feedback execution intent mismatch")
        expected = project(value, task["public"], row["prediction"], row["score"], private=task["private"], role="train")
        feedback = dict(trace["Feedback"])
        if "evidence" in feedback:
            require(not scalar, "The scalar arm carries no evidence reports")
            text = feedback.pop("evidence")
            report = canonical_report(ledger, step, token)
            require(reports is not None and reports.get(token) == report and report["feedback"] == text,
                    "Evidence text differs from the sealed report")
        require({**{key: trace[key] for key in expected if key != "Feedback"}, "Feedback": feedback} == expected,
                "Feedback projection differs from actual execution")


def checker_note(feedback, *, label=False):
    """The native 'system' turn of a projected trace: host status plus the itemized evidence report (if any); the
    failure-message branch names its release instead of claiming that no hidden-test information is provided."""
    if label and "evidence" in feedback:
        return ("Development native checker: " + feedback["status"]
                + ". Failure messages of the hidden tests this output failed (label feedback) follow.\n"
                + feedback["evidence"])
    note = ("Development native checker: " + feedback["status"]
            + ". Hidden tests and expected answers are not provided.")
    if "evidence" in feedback:
        note += "\n" + feedback["evidence"]
    return note


def propose_with_evidence(parent_skill, traces, output, ledger, *, step, seed, minibatch_size, edit_budget,
                          reports=None, summary=None, label=False):
    """One native proposal from this step's traces (sealed; a replay returns the identical record). Evidence
    reports and the summary are authenticated against the step's canonical sealed records. ``label`` marks the
    failure-message branch of the study arm (its own preamble and checker note); the matched scalar branch of the
    same arm calls this without reports, summary or label and gets the scalar arm's exact package."""
    from skillopt.engine.trainer import _normalise_patches
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    from skillopt.optimizer.skill import apply_patch_with_report

    value = ledger.manifest
    check_skill(parent_skill, skill_budget(value))
    benchmark = benchmark_for(value)
    limits = value["active_evidence"]["limits"]
    rollout = step
    validate_traces(traces, benchmark, report_chars=limits["report_chars"])
    scalar = value["active_evidence"]["arms"]["feedback"] == "scalar"
    require(not scalar or (reports is None and summary is None), "The scalar arm carries no reports or summary")
    require(type(label) is bool and (not label or value["active_evidence"]["arms"]["feedback"] == "hidden_failure"),
            "The failure-message preamble belongs to the hidden_failure arm only")
    require(not label or (reports is not None and summary is not None),
            "The failure-message branch carries its sealed reports and summary")
    if summary is not None:
        require(type(summary) is str and 0 < len(summary) <= limits["summary_chars"] + len(TRUNCATION),
                "Oversized or empty diagnosis summary")
        canonical_summary(ledger, step, summary)
    bind_traces(traces, ledger, parent_skill, step=step, reports=reports)
    require(type(seed) is int and seed >= 0, "Invalid seed")
    require(type(minibatch_size) is int and 1 <= minibatch_size <= 64, "Invalid native minibatch size")
    require(type(edit_budget) is int and 1 <= edit_budget <= 16, "Invalid native edit budget")
    screened = value["active_evidence"].get("update_mode", "native") == "screened"
    profile = value["active_evidence"].get("analyst_profile", "native")
    systems = analyst_systems(summary, label=label, screened=screened, profile=profile)
    root = safe_path(output)
    identity = seal({"protocol": PROTOCOL, "parent_skill": parent_skill, "traces_hash": digest(traces),
                     "manifest_hash": value["record_hash"], "native_sources": native_sources(),
                     "step": step, "rollout": rollout, "seed": seed, "minibatch_size": minibatch_size,
                     "edit_budget": edit_budget, "meta": False, "slow": False, "skill_aware": False,
                     "acceptance": "post_update_challenge_decision_or_accepted_without_challenge",
                     "analyst_preamble": TRANSFER_PREAMBLE_VERSION,
                     "evidence_preamble": LABEL_PREAMBLE_VERSION if label else EVIDENCE_PREAMBLE_VERSION,
                     "label_feedback": label, "analyst_systems": digest(systems),
                     **({} if profile == "native" else {"analyst_profile": profile}),
                     "summary_format": SUMMARY_FORMAT_VERSION,
                     "screened_preamble": SCREENED_PREAMBLE_VERSION if screened else None,
                     "reports_hash": digest({k: v["record_hash"] for k, v in sorted((reports or {}).items())}),
                     "summary_hash": digest(summary) if summary else None,
                     "evidence_rows": sum("evidence" in t["Feedback"] for t in traces)})
    write_json(root / "identity.json", identity)
    if (root / "result.json").exists():
        result = read_json(root / "result.json", sealed=True)
        require(result["identity_hash"] == identity["record_hash"], "Native proposal identity differs")
        return result
    if (root / "started.json").exists():
        raise LearningPending("native_proposal_interrupted_no_automatic_resume")
    write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
    native_rows = []
    for trace in traces:
        token = trace["evidence_hash"]
        description = task_description(benchmark, trace["Inputs"])
        write_json(root / "predictions" / token / "conversation.json", [
            {"role": "user", "content": description},
            {"role": "assistant", "content": trace["Generated Outputs"]},
            {"role": "system", "content": checker_note(trace["Feedback"], label=label)},
        ])
        native_rows.append({"id": token, "hard": trace["Feedback"]["score"], "n_turns": 1,
                            "task_description": description, "task_type": benchmark,
                            "fail_reason": "Native development check failed"
                            if trace["Feedback"]["status"] == "fail" else ""})
    bridge = _NativeBridge(ledger, f"ae{step}", audit_root=root / "parser_audits")
    with _transport(bridge), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raw = sorted(reflect.run_minibatch_reflect(
            native_rows, parent_skill, str(root / "predictions"), str(root / "patches"),
            workers=1, failure_only=False, minibatch_size=minibatch_size, edit_budget=edit_budget,
            random_seed=seed, error_system=systems["error_system"],
            success_system=systems["success_system"], update_mode="patch",
            step_buffer_context="", meta_skill_context="", skill_aware_reflection=False), key=digest)
        if bridge.failure is not None:
            raise LearningPending("native_reflection_incomplete") from bridge.failure
        expected = sum(math.ceil(sum(row["hard"] == v for row in native_rows) / minibatch_size) for v in (0, 1))
        if len(raw) != expected:
            raise LearningPending("native_reflection_parse_incomplete")
        failure, success = _normalise_patches(deepcopy(raw), update_mode="patch")
        merged = aggregate.merge_patches(parent_skill, failure, success, batch_size=8,
                                         workers=1, verbose=False, update_mode="patch")
        selected = clip.rank_and_select(parent_skill, merged, max_edits=edit_budget, update_mode="patch")
    if bridge.failure is not None:
        raise LearningPending("native_optimizer_incomplete") from bridge.failure
    require(value["version"] in DELIVERY_VERSIONS, "Fallback provenance is a v5+ record")
    fallbacks = sorted({str(w.message) for w in caught if "using fallback" in str(w.message)})
    if "[fallback truncated" in str(selected.get("reasoning", "")):
        fallbacks.append("ranking fallback truncation")
    candidate, application = apply_patch_with_report(parent_skill, selected)
    common = {"protocol": PROTOCOL, "identity_hash": identity["record_hash"], "raw": raw, "merged": merged,
              "selected": selected, "application": application, "optimizer_calls": bridge.calls,
              "native_fallbacks": fallbacks, "deployment_authorized": False}
    try:
        check_skill(candidate, skill_budget(value))
    except ValueError as exc:
        oversized = type(candidate) is str and len(candidate.encode("utf-8")) > skill_budget(value)
        if not oversized:
            raise LearningPending("native_candidate_exceeds_skill_budget") from exc
        result = seal({**common, "candidate_skill": parent_skill, "status": "rejected_inadmissible_over_budget",
                       "rejected_candidate_skill": candidate, "rejected_candidate_hash": digest(candidate),
                       "rejected_candidate_bytes": len(candidate.encode("utf-8"))})
        write_json(root / "result.json", result)
        return result
    result = seal({**common, "candidate_skill": candidate,
                   "status": "candidate_ready" if candidate != parent_skill else "no_update"})
    write_json(root / "result.json", result)
    return result
