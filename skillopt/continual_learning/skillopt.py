"""Bounded native SkillOpt patch proposal for explicitly authorized development.

Reuse the repository's real reflection/merge/ranking/application code, not a
replacement optimizer prompt. This module does not authorize deployment.
"""
from __future__ import annotations

import hashlib
import math
import threading
import warnings
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import CachedAPI, digest

from .contracts import (
    CONFIRMATION_VERSIONS,
    GENERALIZATION_VERSIONS,
    VERIFIER_METHOD,
    check_skill,
    skill_budget,
    validate_manifest,
)
from .execution_evidence import render as render_evidence
from .feedback import (
    EXPECTED_CHARS,
    artifacts,
    benchmark_for,
    evidence_enabled,
    labeled_enabled,
    project,
    task_description,
    validate_public,
    verifier_enabled,
)
from .ledger import LearningPending, Ledger
from .recovery import DELIVERY_VERSIONS, client_options
from .recovery import VERSIONS as RECOVERY_VERSIONS
from .reflection_json import POLICIES as PARSER_POLICIES
from .reflection_json import NativeJSONError, prepare_native_json, strict_native_object

_NATIVE_LOCK = threading.RLock()

from .transfer import TRANSFER_PREAMBLE, TRANSFER_PREAMBLE_VERSION  # noqa: E402
from .verifier import MAX_REPORT_CHARS, Verifier  # noqa: E402
from .verifier import VERSION as VERIFIER_IMPLEMENTATION  # noqa: E402
from .verifier import default_policy_record, native_probe_executor, policy_record_for_next_stage  # noqa: E402

# V10: what the analysts are told about verifier reports (appended after the transfer requirement).
VERIFIER_PREAMBLE_VERSION = "verifier-report-guidance-v2"
VERIFIER_PREAMBLE = (
    "\n\nVERIFIER REPORTS. Some failed development rows include a report from a reusable, label-free "
    "verification rubric: public contract checks executed on the generated output (or judged against the "
    "task text), calibrated against the development checker. No expected answer or hidden test is shown. "
    "Use a report to name the contract obligation that was violated and the procedural mistake that led "
    "to it; a passed check tells you what was NOT the problem. An ERROR line means the call raised: it is a "
    "hint to check input handling and robustness, not a verified contract violation (the input may have been "
    "illegal). Never copy probe inputs, expected values, "
    "quotes or task-specific entities into the skill: write the reusable procedure or check that would "
    "have caught the mistake. Current rubric -- mechanism: {mechanism} applicability: {applicability} "
    "exceptions: {exceptions}"
)


def native_sources():
    root = Path(__file__).resolve().parents[1]
    names = ["engine/trainer.py", "gradient/reflect.py", "gradient/aggregate.py",
             "optimizer/clip.py", "optimizer/skill.py", "optimizer/update_modes.py",
             "optimizer/meta_skill.py", "optimizer/skill_aware.py", "evaluation/gate.py",
             "utils/json_utils.py", "prompts/analyst_error.md", "prompts/analyst_success.md",
             "prompts/merge_failure.md", "prompts/merge_success.md", "prompts/merge_final.md",
             "prompts/ranking.md"]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


class _NativeBridge:
    def __init__(self, ledger, step, *, audit_root=None):
        self.ledger, self.step = ledger, step
        self.calls = 0
        self.failure = None
        self.strict_parser = ledger.manifest["version"] in RECOVERY_VERSIONS
        self.audit_root = safe_path(audit_root) if audit_root is not None else None
        self.json_retries = 0
        if self.strict_parser:
            policy = ledger.manifest.get("recovery_policy", {})
            self.parser_policy = policy.get("reflection_parser")
            require(self.parser_policy in PARSER_POLICIES, "Native parser recovery policy differs")
            require(self.audit_root is not None, "Native parser audit output required")
            self.json_retries = policy.get("reflection_json_retries", 0)
            require(self.json_retries in {0, 1}, "Unsupported native JSON retry policy")

    def chat(self, system, user, max_completion_tokens=16384, retries=3, stage="optimizer", **kwargs):
        if self.failure is not None:
            raise LearningPending("earlier_native_optimizer_failure")
        try:
            require(stage in {"analyst", "merge", "ranking"} and not kwargs,
                    "Unsupported native optimizer transport options")
            require(type(max_completion_tokens) is int and max_completion_tokens > 0,
                    "Invalid native optimizer token budget")
            cap = min(max_completion_tokens, self.ledger.manifest["budget"]["reflection_max_tokens"])
            index = self.calls
            self.calls += 1
            logical = f"skillopt:{self.step}:{stage}:{index}"
            receipt = self.ledger.call("reflection", logical, system, user, cap)
            if not receipt.get("ok") or receipt.get("finish_reason") != "stop":
                raise LearningPending("native_optimizer_response_unknown")
            require(type(receipt.get("response")) is str, "Missing optimizer response")
            response = receipt["response"]
            if self.strict_parser:
                binding = {"manifest_hash": self.ledger.manifest["record_hash"], "step": self.step,
                           "stage": stage, "call_index": index, "receipt_hash": digest(receipt),
                           "request_hash": receipt["request_hash"],
                           "call_intent_hash": receipt["request"]["key"]}
                try:
                    response, audit = prepare_native_json(response, self.parser_policy)
                except NativeJSONError as exc:
                    write_json(self.audit_root / f"{index}.json", seal({**binding, **exc.audit}))
                    if not self.json_retries:
                        raise LearningPending("native_optimizer_json_rejected:" + exc.reason) from exc
                    # V9: one bounded format retry. The same request is re-issued with a format
                    # reminder appended (a fresh model sample); the first reply stays in its receipt
                    # and audit. A second invalid document leaves the stage pending as before.
                    retry_user = (user + "\n\nYour previous reply could not be parsed as one JSON document ("
                                  + exc.reason + "). Reply again with ONLY a single valid JSON object: no prose, "
                                  "no code fences, commas between all elements, every string properly escaped.")
                    retry = self.ledger.call("reflection", logical + ":json-retry:1", system, retry_user, cap)
                    if not retry.get("ok") or retry.get("finish_reason") != "stop":
                        raise LearningPending("native_optimizer_response_unknown") from exc
                    require(type(retry.get("response")) is str, "Missing optimizer response")
                    retry_binding = {**binding, "json_retry": 1, "receipt_hash": digest(retry),
                                     "request_hash": retry["request_hash"], "call_intent_hash": retry["request"]["key"],
                                     "first_reply_reason": exc.reason}
                    try:
                        response, audit = prepare_native_json(retry["response"], self.parser_policy)
                    except NativeJSONError as again:
                        write_json(self.audit_root / f"{index}-retry1.json", seal({**retry_binding, **again.audit}))
                        raise LearningPending("native_optimizer_json_rejected_after_retry:" + again.reason) from again
                    write_json(self.audit_root / f"{index}-retry1.json", seal({**retry_binding, **audit}))
                    usage = deepcopy(retry.get("usage", {}))
                    return response, usage
                write_json(self.audit_root / f"{index}.json", seal({**binding, **audit}))
            return response, deepcopy(receipt.get("usage", {}))
        except Exception as exc:
            # Upstream has fallbacks that catch exceptions; do not let a
            # transport failure become an apparently complete learned candidate.
            self.failure = exc
            raise


@contextmanager
def _transport(bridge):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip

    with _NATIVE_LOCK:
        modules = (reflect, aggregate, clip)
        originals = [module.chat_optimizer for module in modules]
        parsers = [module.extract_json for module in modules]
        try:
            for module in modules:
                module.chat_optimizer = bridge.chat
                if bridge.strict_parser:
                    module.extract_json = strict_native_object
            yield
        finally:
            for module, original, parser in zip(modules, originals, parsers):
                module.chat_optimizer = original
                if bridge.strict_parser:
                    module.extract_json = parser


def _validate_traces(traces, benchmark="bigcodebench", *, evidence=False, labeled=False, verifier=False):
    require(type(traces) is list and traces, "Nonempty authorized development traces required")
    for trace in traces:
        require(type(trace) is dict and set(trace) == {"Inputs", "Generated Outputs", "Feedback", "evidence_hash"},
                "Only explicitly projected feedback fields are allowed")
        public, feedback = trace["Inputs"], trace["Feedback"]
        validate_public(benchmark, public)
        require(type(trace["Generated Outputs"]) is str, "Actual output required")
        allowed = [{"status", "score"}]
        if verifier and type(feedback) is dict and feedback.get("status") == "fail":
            # V10: a failed train row may carry the sealed verifier report text (never a label).
            allowed.append({"status", "score", "verifier"})
            if "verifier" in feedback:
                require(type(feedback["verifier"]) is str
                        and 0 < len(feedback["verifier"]) <= MAX_REPORT_CHARS + len(" …[truncated]"),
                        "Oversized or empty verifier report")
        if evidence and type(feedback) is dict and feedback.get("status") == "fail":
            # The v7 BigCodeBench ablation adds only sanitized structural evidence.
            allowed.append({"status", "score", "execution_evidence"})
        if labeled and type(feedback) is dict and feedback.get("status") == "fail":
            # V8: failed train rows carry the expected answer (KOR/QA) or BCB evidence.
            allowed.append({"status", "score", "execution_evidence"} if benchmark == "bigcodebench"
                           else {"status", "score", "expected"})
            if type(feedback.get("expected")) is str:
                require(len(feedback["expected"]) <= 2000 + len(" …[truncated]"), "Oversized label text")
        require(type(feedback) is dict and set(feedback) in allowed, "Only scalar native feedback allowed")
        if feedback["status"] == "unknown":
            raise LearningPending("unknown_is_not_failure_feedback")
        require(feedback["status"] in {"pass", "fail"}
                and feedback["score"] == int(feedback["status"] == "pass"), "Inconsistent native hard feedback")
        token = trace["evidence_hash"]
        require(type(token) is str and len(token) == 64 and all(c in "0123456789abcdef" for c in token),
                "Bound execution evidence required")
    require(len({t["evidence_hash"] for t in traces}) == len(traces), "Duplicate development evidence")


def _bind_traces(traces, ledger, parent_skill, verifier_reports=None, step=None, policy_record=None):
    """Resolve projections to this learner's actual authorized train evidence.

    V10: a trace's verifier text must be exactly the sealed, authorized report of the same
    execution evidence (``verifier/<step>/reports/<evidence hash>.json`` re-read here, bound to this
    manifest, step and the step's authorized policy), never free text or a caller-supplied dict.
    """
    panel = read_json(ledger.root / "panel.json")
    require(digest(panel) == ledger.manifest["panel_hash"], "Feedback panel is not authorized")
    tasks = {digest(task): task for task in panel["tasks"]}
    evidence = {}
    for path in sorted((ledger.root / "evaluations").glob("*.json")):
        row = read_json(path, sealed=True)
        evidence[row["record_hash"]] = (path, row)
    for trace in traces:
        require(trace["evidence_hash"] in evidence, "Feedback has no current learning execution evidence")
        path, row = evidence[trace["evidence_hash"]]
        request = row["request"]
        task = tasks.get(request["task_hash"])
        require(task is not None and request["manifest_hash"] == ledger.manifest["record_hash"]
                and request["role"] == "train" and task["partition"] == "development"
                and ledger.manifest["authorized_tasks"].get(request["task_hash"]) == "train"
                and request["candidate_hash"] == digest({"skill": parent_skill}),
                "Feedback role, task, parent or authorization mismatch")
        require(read_json(ledger.root / "evaluation_intents" / path.name, sealed=True) == seal(request),
                "Feedback execution intent mismatch")
        if verifier_enabled(ledger.manifest):
            require(step is not None and request.get("rollout") == step, "V10 traces must be this step's fresh train rollout")
        expected = project(ledger.manifest, task["public"], row["prediction"], row["score"],
                           private=task["private"], role="train")
        feedback = dict(trace["Feedback"])
        if "verifier" in feedback:
            require(verifier_reports is not None and trace["evidence_hash"] in verifier_reports
                    and type(step) is int and type(policy_record) is dict,
                    "Verifier feedback without a sealed report for this evidence")
            report_path = ledger.root / "verifier" / str(step) / "reports" / (trace["evidence_hash"] + ".json")
            require(report_path.is_file(), "Verifier feedback differs from the sealed report (no report for this step)")
            report = read_json(report_path, sealed=True)
            require(report == verifier_reports[trace["evidence_hash"]]
                    and report["manifest_hash"] == ledger.manifest["record_hash"] and report["step"] == step
                    and report["policy_hash"] == policy_record["policy_hash"]
                    and report["authorized"] is True and report["feedback"] == feedback.pop("verifier")
                    and report["evidence_hash"] == trace["evidence_hash"], "Verifier feedback differs from the sealed report")
        require({**{key: trace[key] for key in expected if key != "Feedback"}, "Feedback": feedback} == expected,
                "Feedback projection differs from actual execution")


def _authenticate_policy(ledger, step, policy_record):
    """V10: the policy text the analysts see must be the step's canonical sealed policy, whose
    verifier summary (same manifest and step) says the step was authorized."""
    require(type(step) is int and type(policy_record) is dict, "Verifier policy needs its step")
    root = ledger.root / "verifier" / str(step)
    require((root / "policy.json").is_file() and (root / "summary.json").is_file(),
            "Verifier policy without the step's sealed policy and summary")
    canonical = read_json(root / "policy.json", sealed=True)
    summary = read_json(root / "summary.json", sealed=True)
    require(policy_record == canonical and digest(canonical["policy"]) == canonical["policy_hash"]
            and canonical["manifest_hash"] == ledger.manifest["record_hash"] and canonical["step"] == step
            and summary["manifest_hash"] == ledger.manifest["record_hash"] and summary["step"] == step
            and summary["policy_hash"] == canonical["policy_hash"] and summary["authorized"] is True,
            "Verifier policy is not the step's authorized sealed policy")
    return canonical


def _checker_note(feedback):
    """The native 'system' turn of a projected trace: status plus v7 evidence / v8 label."""
    note = ("Development native checker: " + feedback["status"]
            + ". Hidden tests and expected answers are not provided.")
    if "expected" in feedback:
        note = ("Development native checker: " + feedback["status"]
                + ". The checker expected exactly this answer (do not copy it into the skill; "
                "explain the procedural mistake that led away from it): " + feedback["expected"])
    if "execution_evidence" in feedback:
        note += " " + render_evidence(feedback["execution_evidence"])
    if "verifier" in feedback:
        note += "\n" + feedback["verifier"]
    return note


def _analyst_systems(manifest, policy_record=None):
    """V8 appends the transfer requirement to the repository's own analyst prompts; v10 adds the
    verifier-report guidance with the step's current rubric policy."""
    if manifest["version"] not in GENERALIZATION_VERSIONS:
        return {}
    from skillopt.gradient.reflect import load_prompt

    require(manifest["recovery_policy"]["reflection_preamble"] == TRANSFER_PREAMBLE_VERSION,
            "Unsupported reflection preamble")
    suffix = TRANSFER_PREAMBLE
    if verifier_enabled(manifest):
        # The rubric text reaches the analysts only in a step whose verifier passed calibration (the
        # same condition under which its reports do); an unauthorized step gets the v9 prompts.
        if policy_record is not None:
            policy = policy_record["policy"]
            suffix += VERIFIER_PREAMBLE.format(mechanism=policy["mechanism"], applicability=policy["applicability"],
                                               exceptions=policy["exceptions"])
    else:
        require(policy_record is None, "Verifier policies are a v10 concept")
    return {"error_system": load_prompt("analyst_error") + suffix,
            "success_system": load_prompt("analyst_success") + suffix}


def propose_native(parent_skill, traces, output, ledger, *, step=0, seed=0, minibatch_size=8, edit_budget=4,
                   verifier_reports=None, policy_record=None):
    """One real reflect -> aggregate -> clip -> patch pass; no selection gate.

    ``traces`` must come from the new learner's authorized execution adapter,
    never from reinterpreting a frozen no-feedback evaluation artifact. V10 passes the step's
    sealed verifier reports and rubric policy; the traces may quote only those reports.
    """
    from skillopt.engine.trainer import _normalise_patches
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    from skillopt.optimizer.skill import apply_patch_with_report

    check_skill(parent_skill, skill_budget(ledger.manifest))
    benchmark = benchmark_for(ledger.manifest)
    evidence = evidence_enabled(ledger.manifest)
    labeled = labeled_enabled(ledger.manifest)
    verifier = verifier_enabled(ledger.manifest)
    _validate_traces(traces, benchmark, evidence=evidence, labeled=labeled, verifier=verifier)
    require(ledger.manifest.get("method") == ("skillopt" if not verifier else VERIFIER_METHOD),
            "SkillOpt learning authorization required")
    require(verifier or (verifier_reports is None and policy_record is None), "Verifier inputs are a v10 concept")
    require(not verifier or policy_record is not None or not any("verifier" in t["Feedback"] for t in traces),
            "Verifier reports need the step's authorized policy")
    if verifier and policy_record is not None:
        policy_record = _authenticate_policy(ledger, step, policy_record)
    _bind_traces(traces, ledger, parent_skill, verifier_reports, step, policy_record)
    require(type(step) is int and step >= 0 and type(seed) is int and seed >= 0, "Invalid step or seed")
    require(type(minibatch_size) is int and 1 <= minibatch_size <= 64, "Invalid native minibatch size")
    require(type(edit_budget) is int and 1 <= edit_budget <= 16, "Invalid native edit budget")
    systems = _analyst_systems(ledger.manifest, policy_record if verifier else None)
    root = safe_path(output)
    identity = seal({"parent_skill": parent_skill, "traces_hash": digest(traces),
                     "manifest_hash": ledger.manifest["record_hash"], "native_sources": native_sources(),
                     "step": step, "seed": seed, "minibatch_size": minibatch_size,
                     "edit_budget": edit_budget, "meta": False, "slow": False, "skill_aware": False,
                     "native_generic_prompts": not systems, "acceptance": "external_development_selection",
                     **({"analyst_preamble": TRANSFER_PREAMBLE_VERSION, "analyst_systems": digest(systems)}
                        if systems else {}),
                     **({"verifier": VERIFIER_IMPLEMENTATION, "verifier_preamble": VERIFIER_PREAMBLE_VERSION,
                         "verifier_authorized": policy_record is not None,
                         "verifier_policy_hash": policy_record["policy_hash"] if policy_record else None,
                         "verifier_reports_hash": digest({k: v["record_hash"] for k, v in sorted((verifier_reports or {}).items())})}
                        if verifier else {})})
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
            {"role": "system", "content": _checker_note(trace["Feedback"])},
        ])
        native_rows.append({"id": token, "hard": trace["Feedback"]["score"], "n_turns": 1,
                            "task_description": description, "task_type": "coding" if benchmark == "bigcodebench" else benchmark,
                            "fail_reason": ("Native development tests failed" if benchmark == "bigcodebench"
                                            else "Native development check failed")
                            if trace["Feedback"]["status"] == "fail" else ""})
    bridge = _NativeBridge(ledger, step, audit_root=root / "parser_audits")
    with _transport(bridge), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raw = sorted(reflect.run_minibatch_reflect(
            native_rows, parent_skill, str(root / "predictions"), str(root / "patches"),
            workers=1, failure_only=False, minibatch_size=minibatch_size, edit_budget=edit_budget,
            random_seed=seed, error_system=systems.get("error_system"),
            success_system=systems.get("success_system"), update_mode="patch",
            step_buffer_context="", meta_skill_context="", skill_aware_reflection=False), key=digest)
        if bridge.failure is not None:
            raise LearningPending("native_reflection_incomplete") from bridge.failure
        expected = sum(math.ceil(sum(row["hard"] == value for row in native_rows) / minibatch_size)
                       for value in (0, 1))
        if len(raw) != expected:
            raise LearningPending("native_reflection_parse_incomplete")
        failure, success = _normalise_patches(deepcopy(raw), update_mode="patch")
        merged = aggregate.merge_patches(parent_skill, failure, success, batch_size=8,
                                         workers=1, verbose=False, update_mode="patch")
        selected = clip.rank_and_select(parent_skill, merged, max_edits=edit_budget, update_mode="patch")
    if bridge.failure is not None:
        raise LearningPending("native_optimizer_incomplete") from bridge.failure
    provenance = {}
    if ledger.manifest["version"] in DELIVERY_VERSIONS:
        # Upstream merge/rank silently fall back on unusable optimizer output.
        # Record it, so a completed stage cannot pass for a native merge/rank result.
        fallbacks = sorted({str(w.message) for w in caught if "using fallback" in str(w.message)})
        if "[fallback truncated" in str(selected.get("reasoning", "")):
            fallbacks.append("ranking fallback truncation")
        provenance = {"native_fallbacks": fallbacks}
    candidate, application = apply_patch_with_report(parent_skill, selected)
    try:
        check_skill(candidate, skill_budget(ledger.manifest))
    except ValueError as exc:
        oversized = type(candidate) is str and len(candidate.encode("utf-8")) > skill_budget(ledger.manifest)
        if not oversized or ledger.manifest["version"] not in DELIVERY_VERSIONS:
            raise LearningPending("native_candidate_exceeds_skill_budget") from exc
        # V5: a complete native proposal outside the frozen Skill interface is
        # inadmissible. Keep the parent, retain the rejected text for audit, and
        # never truncate, compress or evaluate it.
        result = seal({"identity_hash": identity["record_hash"], "candidate_skill": parent_skill,
                       "status": "rejected_inadmissible_over_budget",
                       "rejected_candidate_skill": candidate, "rejected_candidate_hash": digest(candidate),
                       "rejected_candidate_bytes": len(candidate.encode("utf-8")),
                       "raw": raw, "merged": merged, "selected": selected, "application": application,
                       "optimizer_calls": bridge.calls, **provenance, "deployment_authorized": False})
        write_json(root / "result.json", result)
        return result
    result = seal({"identity_hash": identity["record_hash"], "candidate_skill": candidate,
                   "status": "candidate_ready" if candidate != parent_skill else "no_update",
                   "raw": raw, "merged": merged, "selected": selected, "application": application,
                   "optimizer_calls": bridge.calls, **provenance, "deployment_authorized": False})
    write_json(root / "result.json", result)
    return result


def _known_mean(rows, policy, reason):
    """V5: mean over known positions; too few known positions cannot justify a comparison."""
    known = [r["score"] for r in rows if r["score"] is not None]
    if not known or len(known) < policy["min_known_fraction"] * len(rows):
        raise LearningPending(reason)
    return sum(known) / len(known)


def _paired_selection(parent_rows, candidate_rows, policy):
    """V5 paired comparison on jointly known selection positions; unknown is never zero.

    Net newly unknown positions beyond a frozen tolerance are inadmissible.
    This historical criterion does not guarantee regression safety: recovering
    unknowns elsewhere can offset loss of known positions. V6 preserves that
    selection policy; changing it requires a separate research protocol.
    """
    require(len(parent_rows) == len(candidate_rows), "Selection rows differ")
    pairs = [(p["score"], c["score"]) for p, c in zip(parent_rows, candidate_rows)]
    joint = [(p, c) for p, c in pairs if p is not None and c is not None]
    new_unknown = sum(p is not None and c is None for p, c in pairs)
    resolved = sum(p is None and c is not None for p, c in pairs)
    tolerance = max(policy["unknown_shift_tolerance_min"],
                    math.ceil(policy["unknown_shift_tolerance_fraction"] * len(pairs)))
    record = {"selection_positions": len(pairs), "jointly_known": len(joint),
              "candidate_new_unknown": new_unknown, "candidate_resolved_unknown": resolved,
              "unknown_shift_tolerance": tolerance,
              "paired_admissible": bool(joint) and len(joint) >= policy["min_known_fraction"] * len(pairs)
              and new_unknown - resolved <= tolerance}
    if joint:
        record.update(parent_score=sum(p for p, _ in joint) / len(joint),
                      candidate_score=sum(c for _, c in joint) / len(joint))
    return record


def _margin_selection(parent_rows, candidate_rows, items, policy):
    """V8 gate: paired net wins over a fixed denominator, no unknown compensation.

    Every authorized selection position counts. A win is a parent failure the
    candidate confirms as a pass; a loss is a parent pass the candidate fails
    OR cannot score (a new unknown is charged as a loss, never averaged away);
    a position the parent itself could not score is neither. Acceptance needs
    net wins of at least max(min_net_wins, ceil(net_wins_fraction * positions))
    and more families improving than regressing (KOR rules, ALF scenarios ...).
    """
    require(len(parent_rows) == len(candidate_rows) == len(items), "Selection rows differ")
    wins = losses = new_unknown = parent_unknown = ties = 0
    families = {}
    for parent, candidate, item in zip(parent_rows, candidate_rows, items):
        p, c = parent["score"], candidate["score"]
        family = item["task"]["family_id"]
        if p is None:
            parent_unknown += 1
            continue
        if c is None:
            new_unknown += 1
            losses += 1
            families[family] = families.get(family, 0) - 1
        elif c > p:
            wins += 1
            families[family] = families.get(family, 0) + 1
        elif c < p:
            losses += 1
            families[family] = families.get(family, 0) - 1
        else:
            ties += 1
            families.setdefault(family, 0)
    positions = len(items)
    margin = max(policy["min_net_wins"], math.ceil(policy["net_wins_fraction"] * positions))
    improving = sum(v > 0 for v in families.values())
    regressing = sum(v < 0 for v in families.values())
    known = positions - parent_unknown
    candidate_known = sum(c["score"] is not None for c in candidate_rows)
    record = {"selection_positions": positions, "parent_known": known, "parent_unknown": parent_unknown,
              "candidate_known": candidate_known,
              "candidate_new_unknown": new_unknown, "wins": wins, "losses": losses, "ties": ties,
              "net_wins": wins - losses, "required_net_wins": margin,
              "families_improving": improving, "families_regressing": regressing,
              # Both Skills must score the frozen coverage floor; an accepted candidate becomes
              # the next parent, whose known rows the following comparison needs.
              "coverage_admissible": bool(known >= policy["min_known_fraction"] * positions
                                          and candidate_known >= policy["min_known_fraction"] * positions),
              "selection_gate": policy["selection_gate"]}
    record["accepted"] = bool(record["coverage_admissible"] and wins - losses >= margin and improving > regressing)
    if known:
        record["parent_score"] = sum(r["score"] for r in parent_rows if r["score"] is not None) / known
        record["candidate_score"] = sum((c["score"] if c["score"] is not None else 0.0)
                                        for p, c in zip(parent_rows, candidate_rows) if p["score"] is not None) / known
    return record


def sign_test_p(wins, losses):
    """Exact one-sided sign test: P(X >= wins) for X ~ Binomial(wins + losses, 1/2)."""
    require(type(wins) is int and type(losses) is int and wins >= 0 and losses >= 0, "Invalid sign-test counts")
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n


def _paired_counts(parent_rows, candidate_rows, items):
    """Paired outcomes over every authorized position, summarized per family.

    A candidate's new unknown is a loss; a position the parent could not score is neither.
    The unit of inference is the FAMILY (a KOR-Bench rule, an ALFWorld scenario, a single task
    elsewhere): tasks of one family share the Skill's effect, so each family contributes one
    sign -- that of its summed paired differences -- to the exact sign test.
    """
    require(len(parent_rows) == len(candidate_rows) == len(items), "Selection rows differ")
    wins = losses = new_unknown = parent_unknown = jointly_known = 0
    families = {}
    for parent, candidate, item in zip(parent_rows, candidate_rows, items):
        p, c = parent["score"], candidate["score"]
        family = item["task"]["family_id"]
        if p is None:
            parent_unknown += 1
            continue
        delta = 0
        if c is None:
            new_unknown += 1
            delta = -1
        else:
            jointly_known += 1
            delta = (c > p) - (c < p)
        wins += delta == 1
        losses += delta == -1
        families[family] = families.get(family, 0) + delta
    improving, regressing = sum(v > 0 for v in families.values()), sum(v < 0 for v in families.values())
    return {"positions": len(items), "wins": wins, "losses": losses, "net_wins": wins - losses,
            "candidate_new_unknown": new_unknown, "parent_unknown": parent_unknown, "jointly_known": jointly_known,
            "families": len(families), "families_improving": improving, "families_regressing": regressing,
            "family_p_value": sign_test_p(improving, regressing)}


def confirm_selection(adapter, items, parent_skill, candidate_skill, parent_rows, candidate_rows, policy, *,
                      tries, rollout):
    """V9 gate: screen on the first val pass, then decide on a fresh pass of BOTH Skills alone.

    ``parent_rows``/``candidate_rows`` are the first pass; the parent's is shared by every
    candidate of the stage and the candidate was chosen for confirmation because of it, so the
    first pass only SCREENS (family-level exact sign test at ``screen_alpha``, positive net).
    A screened candidate and its parent are then both re-evaluated on fresh samples
    (``rollout``), and acceptance is decided on that confirmation pass ALONE: enough jointly
    known positions, and a family-level exact one-sided sign test (one sign per family, never
    one per repeated task) at ``accept_alpha / tries`` (Bonferroni over the candidates the stage
    may try). Nothing from the first pass enters the accepted p-value, so neither a lucky
    candidate draw nor an unlucky shared parent draw can carry an acceptance.
    """
    require(type(tries) is int and tries >= 1 and type(rollout) is int and rollout >= 1, "Invalid confirmation plan")
    floor = policy["min_known_fraction"] * len(items)
    first = _paired_counts(parent_rows, candidate_rows, items)
    record = {"selection_gate": policy["selection_gate"], "selection_positions": len(items),
              "first_pass": first, "screen_alpha": policy["screen_alpha"],
              "accept_alpha_effective": policy["accept_alpha"] / tries, "tries": tries,
              "wins": first["wins"], "losses": first["losses"], "net_wins": first["net_wins"],
              "families_improving": first["families_improving"], "families_regressing": first["families_regressing"]}
    if not (first["jointly_known"] >= floor and first["net_wins"] > 0
            and first["family_p_value"] <= policy["screen_alpha"]):
        return {**record, "gate_action": "reject_screen", "accepted": False}
    parent_again = adapter.evaluate_rows(items, {"skill": parent_skill}, rollout=rollout)
    candidate_again = adapter.evaluate_rows(items, {"skill": candidate_skill}, rollout=rollout)
    second = _paired_counts(parent_again, candidate_again, items)
    accepted = bool(second["jointly_known"] >= floor and second["net_wins"] > 0
                    and second["family_p_value"] <= policy["accept_alpha"] / tries)
    return {**record, "confirmation_rollout": rollout, "confirmation_pass": second,
            "wins": second["wins"], "losses": second["losses"], "net_wins": second["net_wins"],
            "families_improving": second["families_improving"], "families_regressing": second["families_regressing"],
            "confirmation_p_value": second["family_p_value"],
            "gate_action": "accept_confirmed" if accepted else "reject_confirmation", "accepted": accepted}


def _train_labels(benchmark, items, rows):
    """V8: the individual expected answers of the failed train rows (never joined display text)."""
    labels = []
    for item, row in zip(items, rows):
        if row["score"] is None or row["score"] != 0:
            continue
        private = item["task"]["private"]
        if benchmark == "korbench":
            values = [private["answer"]]
        elif benchmark == "searchqa":
            values = list(private["answers"])
        else:
            values = []
        labels.extend((row["output"]["evidence_hash"], str(v)) for v in values)
    return labels


def _label_leak(candidate, parent, labels, policy):
    """V8: a candidate that newly contains a long expected answer of a failed train row is rejected."""
    minimum = policy["label_leakage_min_chars"]
    leaks = []
    for evidence_hash, label in labels:
        # The analyst saw at most EXPECTED_CHARS of a label, so match that prefix (a copied
        # full label contains it too). Labels shorter than the frozen minimum are not checked.
        text = label.strip()[:EXPECTED_CHARS]
        if len(text) >= minimum and text in candidate and text not in parent:
            leaks.append(evidence_hash)
    return sorted(set(leaks))


def _evaluations_closed(root):
    """Every evaluation intent has its sealed evaluation, and no execution reports unconfirmed cleanup."""
    from .gepa import _cleanup_unconfirmed

    intents = {p.name for p in (root / "evaluation_intents").glob("*.json")}
    closed = {p.name for p in (root / "evaluations").glob("*.json")}
    if intents != closed:
        return False
    for path in (root / "evaluations").glob("*.json"):
        if _cleanup_unconfirmed(read_json(path, sealed=True)):
            return False
    for path in (root / "host_only/scorer_artifacts").rglob("*.json"):
        try:
            if _cleanup_unconfirmed(read_json(path)):
                return False
        except (OSError, ValueError, TypeError):
            return False
    # V10: every probe execution the verifier began must have a receipt with confirmed cleanup.
    for intent in (root / "verifier").glob("*/executions/*.intent.json"):
        receipt = intent.with_name(intent.name[: -len(".intent.json")] + ".json")
        if not receipt.exists():
            return False
        try:
            if _cleanup_unconfirmed(read_json(receipt, sealed=True)["execution"]):
                return False
        except (OSError, ValueError, TypeError, KeyError):
            return False
    return True


def _stage_artifacts(root, ledger):
    return {**artifacts(ledger), **{
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("native", "steps") for p in sorted((root / folder).rglob("*.json"))}}


def run_stage(manifest, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None,
              fixture_probe_executor=None, fixture_fetcher=None):
    """Native source-only gate; repeated stages inherit the caller's parent Skill.

    Fixed full train passes and source selection; no meta/slow update, adaptive
    learning rate, history replay, routing or independent final evaluation.
    V10 (method ``rubric_research``) runs the Rubric -> probe -> Research verifier on each
    step's train rows before the native analysts see them; the updater and gate are v9's.
    """
    from skillopt.continual_eval import backends
    from skillopt.evaluation.gate import evaluate_gate

    from .gepa import Adapter  # evaluate_rows itself has no GEPA dependency.

    validate_manifest(manifest, panel)
    verifier = verifier_enabled(manifest)
    require(manifest["method"] == ("skillopt" if not verifier else VERIFIER_METHOD),
            "SkillOpt cannot run another method's manifest")
    fixture = manifest["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None and fixture_evaluate is not None), "Invalid fixture callbacks")
    require(fixture or (fixture_api is None and fixture_evaluate is None), "Natural run cannot inject fixtures")
    require((fixture and verifier) or (fixture_probe_executor is None and fixture_fetcher is None),
            "Verifier fixtures belong to a v10 fixture run only")
    require(not (fixture and verifier) or fixture_probe_executor is not None, "V10 fixture run needs a probe executor")
    root = safe_path(output)
    g = manifest["version"] in GENERALIZATION_VERSIONS
    v9 = manifest["version"] in CONFIRMATION_VERSIONS
    with output_lock(root):
        identity = seal({"manifest": manifest, "native_sources": native_sources(),
                         "edit_budget": 4,
                         "gate": ("v9_family_sign_test_screen_then_fresh_confirmation_on_val" if v9 else "v8_paired_net_wins_margin_on_val")
                         if g else "native_hard_strict_improvement",
                         "training_schedule": "full_train_pass_per_update",
                         "meta": False, "slow": False, "skill_aware": False,
                         **({"analyst_preamble": TRANSFER_PREAMBLE_VERSION,
                             "accepted_prefix": "kept_when_a_later_iteration_stops"} if g else {}),
                         **({"verifier": VERIFIER_IMPLEMENTATION, "verifier_preamble": VERIFIER_PREAMBLE_VERSION,
                             "feedback": "label_free_verifier_reports_on_failed_train_rows"} if verifier else {})})
        write_json(root / "identity.json", identity)
        write_json(root / "panel.json", panel)
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            ledger = Ledger(root, manifest, None)
            require(result["identity_hash"] == identity["record_hash"]
                    and result["artifacts"] == _stage_artifacts(root, ledger), "Learning evidence changed")
            ledger.snapshot()
            return result
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_stage_no_automatic_optimizer_resume",
                    "deployment_authorized": False, "model_calls_submitted": 0}
        if not fixture:
            require(repo is not None, "Natural run needs credential repository")
            require(backends.readiness(benchmark_for(manifest), manifest["runtime"])["status"] == "ready",
                    "Benchmark native runtime is not ready")
        write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
        api = fixture_api
        steps = []
        accepted_prefix = []  # v8: accepted candidates in order; the last one survives a later stop
        initial_score = None
        policy = manifest.get("recovery_policy")
        policy_record = authorized_policy = None
        verifier_steps = []
        previous_calibration = None
        if verifier:
            # The co-evolving rubric: this domain's entry of the parent mapping, else the frozen default.
            # ``policy_record`` is what the proposer continues from; ``authorized_policy`` is the last
            # rubric that passed calibration (what analysts see and the next stage starts from).
            policy_record = authorized_policy = (manifest.get("parent_verifier_policy") or {}).get(manifest["benchmark"]) \
                or default_policy_record(manifest["benchmark"])
        try:
            if not fixture:
                model = manifest["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"],
                                workers=1, reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}),
                                **client_options(manifest))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, manifest, api)
            adapter = Adapter(manifest, root, ledger, fixture_evaluate=fixture_evaluate)
            train, selection = [], []
            for task in panel["tasks"]:
                role = "train" if task["family_id"] in manifest["train_families"] else "selection"
                (train if role == "train" else selection).append({"role": role, "task": task})
            v5 = manifest["version"] in DELIVERY_VERSIONS
            current = manifest["parent_skill"]
            selected = adapter.evaluate_rows(selection, {"skill": current})
            if v5:
                current_score = _known_mean(selected, policy, "insufficient_known_selection")
            else:
                current_score = sum(r["score"] for r in selected) / len(selected)
            initial_score = current_score
            for step in range(manifest["budget"]["max_iterations"]):
                rows = adapter.evaluate_rows(train, {"skill": current}, **({"rollout": step} if v5 else {}))
                labels = list(adapter.train_labels) if g else []  # every label any analyst call has seen so far
                pairs = list(zip(train, rows))  # task/row pairing is kept through the unknown-row filter below
                if v5:
                    _known_mean(rows, policy, "insufficient_known_train")
                    pairs = [(item, r) for item, r in pairs if r["score"] is not None]
                    rows = [r for _, r in pairs]
                traces = [{**r["trajectory"], "evidence_hash": r["output"]["evidence_hash"]} for r in rows
                          if r["trajectory"] is not None]
                require(len(traces) == len(rows), "Native reflection needs executed train rows only")
                reports = step_policy = None
                if verifier:
                    # V10: Rubric -> probe -> Research on this step's executed train rows; the analysts
                    # receive the authorized, sealed reports of failed rows and nothing else.
                    executor = fixture_probe_executor if fixture else native_probe_executor(manifest["runtime"])
                    runner = Verifier(manifest, ledger, root, step, executor=executor, fetcher=fixture_fetcher)
                    summary, reports = runner.run([item for item, _ in pairs], rows, policy_record, previous_calibration,
                                                  skill=current)
                    policy_record = read_json(root / "verifier" / str(step) / "policy.json", sealed=True)
                    previous_calibration = {k: summary[k] for k in ("authorized", "detections", "false_rejections",
                                                                    "false_rejection_rate", "host_pass_rows", "host_fail_rows")}
                    verifier_steps.append(summary)
                    if summary["authorized"]:
                        authorized_policy = step_policy = policy_record
                        for trace in traces:
                            report = reports.get(trace["evidence_hash"])
                            if (trace["Feedback"]["status"] == "fail" and report is not None and report["authorized"]
                                    and report["feedback"] is not None):
                                trace["Feedback"] = {**trace["Feedback"], "verifier": report["feedback"]}
                proposal = propose_native(current, traces, root / "native" / str(step), ledger,
                                          step=step, seed=manifest["seed"] + step,
                                          minibatch_size=manifest["budget"]["minibatch_size"], edit_budget=4,
                                          **({"verifier_reports": reports, "policy_record": step_policy} if verifier else {}))
                if g and proposal["status"] == "candidate_ready":
                    leaks = _label_leak(proposal["candidate_skill"], current, labels, policy)
                    if leaks:
                        # A copied train label is memorization, not a procedure: rejected unevaluated.
                        step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                            "proposal_hash": proposal["record_hash"],
                                            "candidate_skill_hash": digest(proposal["candidate_skill"]),
                                            "native_fallbacks": proposal["native_fallbacks"],
                                            "gate_action": "reject_label_leakage", "leaked_evidence": leaks,
                                            "train_tasks": len(train), "selection_tasks": len(selection),
                                            "deployment_authorized": False})
                        write_json(root / "steps" / f"{step}.json", step_record)
                        steps.append(step_record)
                        continue
                if proposal["status"] == "rejected_inadmissible_over_budget":
                    step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                        "proposal_hash": proposal["record_hash"],
                                        "candidate_skill_hash": proposal["rejected_candidate_hash"],
                                        "native_fallbacks": proposal["native_fallbacks"],
                                        "rejected_candidate_bytes": proposal["rejected_candidate_bytes"],
                                        "parent_score": current_score, "candidate_score": None,
                                        "gate_action": "reject_inadmissible_over_budget",
                                        "train_tasks": len(train), "selection_tasks": len(selection),
                                        "deployment_authorized": False})
                    write_json(root / "steps" / f"{step}.json", step_record)
                    steps.append(step_record)
                    continue
                candidate = proposal["candidate_skill"]
                if g and proposal["status"] == "no_update":
                    step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                        "proposal_hash": proposal["record_hash"],
                                        "candidate_skill_hash": digest(candidate),
                                        "native_fallbacks": proposal["native_fallbacks"],
                                        "gate_action": "no_update_proposed", "train_tasks": len(train),
                                        "selection_tasks": len(selection), "deployment_authorized": False})
                    write_json(root / "steps" / f"{step}.json", step_record)
                    steps.append(step_record)
                    continue
                scores = adapter.evaluate_rows(selection, {"skill": candidate})
                parent_score, paired = current_score, {}
                if v9:
                    verdict = confirm_selection(adapter, selection, current, candidate, selected, scores, policy,
                                                tries=manifest["budget"]["max_iterations"], rollout=step + 1)
                    step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                        "proposal_hash": proposal["record_hash"],
                                        "native_fallbacks": proposal["native_fallbacks"],
                                        "candidate_skill_hash": digest(candidate),
                                        "train_tasks": len(train), "selection_tasks": len(selection),
                                        "deployment_authorized": False, **verdict})
                    write_json(root / "steps" / f"{step}.json", step_record)
                    steps.append(step_record)
                    if verdict["accepted"]:
                        current, selected = candidate, scores
                        current_score = _known_mean(selected, policy, "insufficient_known_selection")
                        accepted_prefix.append(current)
                    continue
                if g:
                    margin = _margin_selection(selected, scores, selection, policy)
                    step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                        "proposal_hash": proposal["record_hash"],
                                        "native_fallbacks": proposal["native_fallbacks"],
                                        "candidate_skill_hash": digest(candidate),
                                        "gate_action": "accept_margin" if margin["accepted"] else "reject_margin",
                                        "train_tasks": len(train), "selection_tasks": len(selection),
                                        "deployment_authorized": False, **margin})
                    write_json(root / "steps" / f"{step}.json", step_record)
                    steps.append(step_record)
                    if margin["accepted"]:
                        current, selected = candidate, scores
                        current_score = _known_mean(selected, policy, "insufficient_known_selection")
                        accepted_prefix.append(current)
                    continue
                if v5:
                    paired = _paired_selection(selected, scores, policy)
                    if not paired["paired_admissible"]:
                        step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                            "proposal_hash": proposal["record_hash"],
                                            "native_fallbacks": proposal["native_fallbacks"],
                                            "candidate_skill_hash": digest(candidate),
                                            "gate_action": "reject_unknown_shift_or_coverage",
                                            "train_tasks": len(train), "selection_tasks": len(selection),
                                            "deployment_authorized": False, **paired})
                        write_json(root / "steps" / f"{step}.json", step_record)
                        steps.append(step_record)
                        continue
                    parent_score, candidate_score = paired.pop("parent_score"), paired.pop("candidate_score")
                else:
                    candidate_score = sum(r["score"] for r in scores) / len(scores)
                gate = evaluate_gate(candidate, candidate_score, current, parent_score,
                                     current, parent_score, step, step + 1, metric="hard")
                step_record = seal({"step": step, "parent_skill_hash": digest(current),
                                    "proposal_hash": proposal["record_hash"],
                                    **({"native_fallbacks": proposal["native_fallbacks"]} if v5 else {}),
                                    "candidate_skill_hash": digest(candidate), "parent_score": parent_score,
                                    "candidate_score": candidate_score, "gate_action": gate.action,
                                    "train_tasks": len(train), "selection_tasks": len(selection),
                                    "deployment_authorized": False, **paired})
                write_json(root / "steps" / f"{step}.json", step_record)
                steps.append(step_record)
                if not v5:
                    current, current_score = gate.current_skill, gate.current_score
                elif gate.action != "reject":
                    # The accepted candidate's own known positions are the next parent rows.
                    current, selected = candidate, scores
                    current_score = _known_mean(selected, policy, "insufficient_known_selection")
            payload = {"status": "completed", "candidate_skill": check_skill(current, skill_budget(manifest)),
                       "initial_selection_score": initial_score, "selected_score": current_score,
                       "reason": "native_skillopt_development_selection" if not verifier
                       else "rubric_research_verifier_feedback_native_updater_development_selection",
                       **({"unknown_policy": policy["unknown_score"]} if v5 else {}),
                       **({"accepted_steps": len(accepted_prefix), "iterations_completed": True,
                           "leaked_candidates_refused": len(adapter.leaked_candidates)} if g else {})}
        except Exception as exc:
            reason = str(exc) if isinstance(exc, LearningPending) else type(exc).__name__
            payload = {"status": "pending", "candidate_skill": manifest["parent_skill"], "reason": reason}
            if g and accepted_prefix and isinstance(exc, LearningPending) and _evaluations_closed(root):
                # V8: a stop in a later iteration does not discard an already verified
                # acceptance (F's S2 lost one) -- provided every evaluation this stage began is
                # closed with confirmed cleanup (other rows of a concurrent batch included). The
                # usage check below can still turn this into Pending if any cost or receipt is unknown.
                payload = {"status": "completed", "candidate_skill": accepted_prefix[-1],
                           "initial_selection_score": initial_score,
                           "reason": "accepted_prefix_kept_after_stop:" + reason,
                           "accepted_steps": len(accepted_prefix), "iterations_completed": False,
                           "unknown_policy": policy["unknown_score"]}
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, manifest, api)
        costs = ledger.snapshot()
        if ledger.usage_blocks_completion(costs) and payload["status"] == "completed":
            payload.update(status="pending", candidate_skill=manifest["parent_skill"], reason="incomplete_usage")
        if verifier:
            # The rubric this stage ends with (its domain's entry of the mapping it started from) is what
            # a chained stage starts from; a pending stage hands on what it started with.
            mapping = dict(manifest.get("parent_verifier_policy") or {})
            if payload["status"] == "completed" and authorized_policy is not None:
                mapping[manifest["benchmark"]] = policy_record_for_next_stage(authorized_policy)
            payload.update(verifier_steps=verifier_steps, verifier_policy=mapping)
        record = seal({"version": manifest["version"], "identity_hash": identity["record_hash"], **payload,
                       "steps": steps, "evidence_kind": manifest["evidence_kind"], "costs": costs,
                       "artifacts": _stage_artifacts(root, ledger), "deployment_authorized": False,
                       "scope_expansion_authorized": False, "resume_supported": False})
        write_json(terminal, record)
        return record
