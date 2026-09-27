"""Offline public draft/revision evidence for a bounded proposal diagnostic.

This adapter replays recorded public execution; it never runs a solver, check,
Research, or hidden audit. Both proposal arms see the same selected final
artifacts, citation catalog and complete public transition summary. Only the
trajectory arm also sees the original draft and its public execution. Thus the
contrast is detailed repair evidence ABOVE a shared repair summary, not whether
the updater knows that a repair happened. No proposal grants any authority.
"""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from . import mechanism_learning, public_revision
from .checks import CallableTask
from .models import ArtifactRecord, RubricVersion, SourceFile, require
from .rule_learning import MAX_PROMPT_BYTES, build_update_request, candidate_from_response
from .rule_skill import render_skill
from .single_round_feedback import build_feedback_bundle, skill_hash

VERSION = "public-repair-trajectory-feedback-v1"
ARMS = ("summary_only", "trajectory")
CALL_KIND = "public-repair-evidence-update"
STRATA = ("deteriorated", "repaired", "unresolved", "stable", "unknown")
SELECTION = (
    "Round-robin deteriorated, repaired, unresolved, stable, unknown using only public checks. "
    "After the first stratum round, reserve at most one remaining detail for a stable repeat of the "
    "EXACT same task as a selected deteriorated/unresolved case, if such evidence exists. "
    "Prefer a not-yet-selected task globally before additional repeats; within a stratum prefer "
    "a new structural family, then repeat index, then task hash. At most the frozen detail_limit "
    "task/repeat PAIRS are selected. No method output or hidden audit affects this selection."
)
POLICY = (
    " Both arms receive complete public draft-to-selected transition summaries and the SAME selected "
    "final-artifact pairs. The optional public_repair_annex adds source-bound draft and revision "
    "observations for those same pairs. Cite their existing evidence_id, not receipt hashes or case IDs. "
    "A within-run repair or deterioration is NOT a No-Skill versus Current effect or a Skill-induced "
    "regression. The same optional Skill was used before and after revision. Public wrapper results "
    "can jointly check return values and state: a false boolean does NOT identify which component "
    "failed, and a wrapper's own empty arguments do not prove input preservation. Component attribution "
    "remains unknown without a separate applicable observation. API/parse failures and unavailable "
    "execution are unknown, not semantic failures. KEEP and identical-source revisions are not learned "
    "repairs. Public passes are bounded evidence, not complete correctness. The summary covers every "
    "registered development position; detail is purposive, not a representative performance sample. "
    "Repeated requests and aliases do not add independent tasks. No Research or hidden audit is supplied. "
)
_SOURCE_KEYS = {"public_row", "exposure", "result", "draft", "initial", "revision"}


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class PromptBudgetExceeded(ValueError):
    def __init__(self, actual_bytes):
        self.actual_bytes, self.limit_bytes = actual_bytes, MAX_PROMPT_BYTES
        super().__init__(f"Repair prompt {actual_bytes} bytes exceeds {MAX_PROMPT_BYTES}; no truncation allowed")


class UnsupportedRepairEvidence(ValueError):
    """Abort a legacy unhealthy replay, without rewriting or dropping records."""


def _require_supported_execution(records):
    for receipt in records:
        verify(receipt)
        execution = verify(receipt["execution"])
        if execution.get("exception") in {"MemoryError", "TimeoutError"}:
            raise UnsupportedRepairEvidence(
                "Unsupported legacy resource exception; preserve the original report, "
                "do not infer semantic repair or call the updater")
        if execution.get("status") == "observed" and execution.get("cleanup_confirmed") is not True:
            raise UnsupportedRepairEvidence(
                "Unsupported observed execution without confirmed cleanup; preserve the original report, "
                "do not infer semantic repair or call the updater")
        # Unobserved placeholders remain unknown through receipt replay. Their
        # absent cleanup assertion cannot establish that execution occurred.


class _ReplayExecutor:
    def __init__(self, identity):
        self.identity = deepcopy(identity)

    def run(self, *args, **kwargs):
        raise AssertionError("Public repair feedback must never execute code")


def _artifact(value):
    verify(value)
    return ArtifactRecord.from_dict({k: v for k, v in value.items() if k != "record_hash"})


def _output_options(record):
    """Replay explicitly declared controls, never infer a budget from a receipt."""
    max_tokens, format_policy = record.get("max_tokens", 2048), record.get("format_policy")
    options = public_revision._output_options(max_tokens=max_tokens, format_policy=format_policy)
    require({key: record[key] for key in ("max_tokens", "format_policy") if key in record} == options,
            "Noncanonical public generation options")
    return max_tokens, format_policy, options


def _initial(initial, draft, task, wrapper, text):
    verify(initial)
    receipt = initial["api_receipt"]
    request = receipt["request"]
    max_tokens, format_policy, _ = _output_options(initial)
    system, user = public_revision._initial_messages(task, text, format_policy=format_policy)
    require(initial["version"] == public_revision.VERSION and initial["stage"] == "draft"
            and initial["artifact_record_hash"] == draft.content_hash
            and initial["artifact_hash"] == draft.artifact_hash
            and initial["hidden_feedback_used"] is False,
            "Initial generation does not bind the registered draft")
    public_revision._receipt(receipt, system, user, "public-initial", draft.repeat, max_tokens=max_tokens)
    prefix = "bigmodel-request:" if request["service"].get("provider") == "BIGMODEL" else "pjlab-request:"
    require(draft.source_ref == prefix + receipt["request_hash"] and draft.source_hash == digest(receipt),
            "Draft source is not bound to its initial API receipt")
    files, availability = (), "api_failure"
    if receipt["ok"]:
        try:
            files = (SourceFile("solution.py", public_revision._parse(receipt.get("response"))), wrapper)
            availability = "available"
        except (ValueError, TypeError, KeyError):
            availability = "parse_failure"
    fixture = request["service"].get("fixture") is True
    require(draft.files == files and draft.availability == availability
            and draft.provenance_complete and not draft.historical_only
            and draft.provenance_kind == ("fixture" if fixture else "model")
            and initial["fixture_only"] is fixture,
            "Draft content/availability/provenance differs from API evidence")
    return receipt


def _transition(before, after):
    if "unknown" in (before, after):
        return "unknown"
    return {("pass", "fail"): "deteriorated", ("fail", "pass"): "repaired",
            ("fail", "fail"): "unresolved", ("pass", "pass"): "stable"}[(before, after)]


def _stage_view(stage, task, public_task, artifact, text, *, clean_timeout_policy=None, format_policy=None):
    if stage is None:
        return {"status": "unknown", "observations": [], "component_attribution": "unknown"}
    # _result already replayed the report, input/source hashes and every receipt.
    clean_timeout = (clean_timeout_policy == public_revision.CLEAN_TIMEOUT_POLICY
                     and public_revision._clean_timeout_stage(stage))
    _, user = public_revision._messages(task, public_task, artifact, text, stage,
                                       clean_timeout=clean_timeout, format_policy=format_policy)
    execution = json.loads(user)["public_execution"]
    return {"status": stage["report"]["status"], "observations": execution["observations"],
            "checker": execution["callable"],
            "scope": "registered_public_check_only_not_component_attribution",
            "component_attribution": "unknown"}


def _source(value, parent, final_entries, executor_identity):
    require(type(value) is dict and set(value) == _SOURCE_KEYS, "Unexpected repair-source fields")
    raw = value["public_row"]
    require(type(raw) is dict and set(raw) == {"task", "public_task", "public_wrapper"},
            "Only whitelisted public registrations are allowed")
    task = CallableTask.from_dict(raw["task"])
    public_task = CallableTask.from_dict(raw["public_task"])
    wrapper = SourceFile.from_dict(raw["public_wrapper"])
    public_revision._parts({"task": task, "public_task": public_task, "public_wrapper": wrapper.to_dict()})
    require(task.contract.partition == "development", "Only development repair evidence is allowed")
    draft = _artifact(value["draft"])
    key = task.contract.content_hash, draft.repeat
    role = draft.condition
    require(role in {"no_skill", "current"} and key in final_entries,
            "Repair source is outside the registered development roster")
    entry = final_entries[key]
    require(entry["task"] == public_task and draft.task_hash == key[0], "Repair public task differs from feedback")
    text = "" if role == "no_skill" else render_skill(parent)
    require(draft.skill_hash == skill_hash(text), "Repair source uses another parent Skill")
    initial = _initial(value["initial"], draft, task, wrapper, text)
    exposure, result, record = (verify(value[k]) for k in ("exposure", "result", "revision"))
    for name in ("draft_stage", "revised_stage"):
        if record[name] is not None:
            _require_supported_execution(record[name]["execution_records_host_only"])
    require(exposure["task_hash"] == key[0] and exposure["callable_task_hash"] == task.content_hash
            and exposure["public_task_hash"] == public_task.content_hash
            and exposure["public_wrapper_hash"] == wrapper.content_hash
            and exposure["condition"] == role and exposure["repeat"] == draft.repeat
            and exposure["exposure_mode"] == "raw" and exposure["rendering"]["text"] == text
            and exposure["effective_skill_text_hash"] == draft.skill_hash
            and exposure["hidden_feedback_used"] is False
            and exposure["executor"] == executor_identity
            and exposure["model"] == initial["request"]["model"]
            and exposure["service"] == initial["request"]["service"], "Draft exposure binding changed")
    if role == "current":
        require(exposure["rule_skill_hash"] == parent.content_hash, "Current exposure uses another RuleSkill")
    require(result["exposure_hash"] == exposure["record_hash"]
            and result["initial_artifact_hash"] == draft.content_hash
            and result["revision_hash"] == record["record_hash"], "Repair result points to another source")
    request = record["request"]
    expected = {"version": public_revision.VERSION, "draft_artifact_hash": draft.content_hash,
        "implementation_hash": request["implementation_hash"], "task_hash": key[0],
        "public_task_hash": public_task.content_hash, "declared_public_task_hash": task.content_hash,
        "repeat": draft.repeat, "skill_hash": draft.skill_hash, "executor": executor_identity,
        "model": exposure["model"], "service": exposure["service"], "protocol_hash": exposure["protocol_hash"]}
    if "clean_timeout_revision_policy" in request:
        require(request["clean_timeout_revision_policy"] == public_revision.CLEAN_TIMEOUT_POLICY,
                "Unsupported public timeout revision policy")
        expected["clean_timeout_revision_policy"] = request["clean_timeout_revision_policy"]
    if "public_selection_policy" in request:
        require(request["public_selection_policy"] == public_revision.PUBLIC_NONREGRESSION_POLICY,
                "Unsupported public selection policy")
        expected["public_selection_policy"] = request["public_selection_policy"]
    _, format_policy, options = _output_options(request)
    expected.update(options)
    if "solver_profile" in exposure:
        from .solver_profile import SolverProfile
        declared = exposure["solver_profile"]
        require(type(declared) is dict, "Declared solver profile must be a canonical record")
        profile = SolverProfile.named(declared.get("name"), declared.get("initial_max_tokens"))
        require(profile.enabled and declared == profile.to_dict(), "Declared solver profile changed")
        initial_tokens, initial_format, _ = _output_options(value["initial"])
        require(initial_tokens == request.get("max_tokens", 2048) == profile.max_tokens
                and initial_format == format_policy == declared["format_policy"]
                and request.get("clean_timeout_revision_policy") == public_revision.CLEAN_TIMEOUT_POLICY
                and request.get("public_selection_policy") == declared["public_selection_policy"]
                and exposure["service"].get("initial_health_policy") == declared["initial_health_policy"],
                "Initial/revision controls differ from the registered solver profile")
    replayed = public_revision._result(record, expected, draft, task, public_task, text,
                                       _ReplayExecutor(executor_identity))
    selected = replayed["artifact"]
    final = entry["artifacts"][role]
    require(selected == final and result["artifact_hash"] == final.content_hash
            and record["hidden_feedback_used"] is False and record["retry_authorized"] is False
            and record["fixture_only"] == (draft.provenance_kind == "fixture"),
            "Selected repair artifact differs from the final feedback source")
    receipt = record["api_receipt"]
    before = "unknown" if record["draft_stage"] is None else record["draft_stage"]["report"]["status"]
    after = record["public_status"]
    # The feedback was re-executed in the original study. Retain disagreement
    # explicitly rather than overriding either observed public status.
    feedback_status = entry["reports"][role]["status"]
    status, reason = record["status"], record["reason"]
    expected_reason = {"revised": "single_revision_selected", "kept": "explicit_keep"}
    if status == "retained":
        # _result has already replayed both checks and recomputed the decision.
        require(request.get("public_selection_policy") == public_revision.PUBLIC_NONREGRESSION_POLICY,
                "Retained attempted revision requires explicit public policy")
        expected_reason["retained"] = "public_nonregression_revised_" + record["revised_stage"]["report"]["status"]
    if status in expected_reason:
        require(reason == expected_reason[status], "Revision decision/reason mismatch")
    elif status == "fallback":
        require(receipt is not None and reason in {"api_failure_no_retry", "parse_failure_no_retry"},
                "Fallback requires a recorded delivery failure")
        if reason == "api_failure_no_retry":
            require(receipt["ok"] is False, "API failure is not an observed semantic outcome")
        else:
            require(receipt["ok"] is True, "Parse failure requires a successful API response")
            try:
                public_revision._parse(receipt.get("response"))
            except (ValueError, TypeError, KeyError):
                pass
            else:
                raise ValueError("Parse-failure fallback has parseable revision code")
    else:
        require(receipt is None and reason in {"artifact_unavailable", "conflicting_public_assertions_abstain",
                                              "public_execution_unknown_or_unsupported"},
                "Skipped revision has an unexpected source or reason")
        if reason == "artifact_unavailable":
            require(draft.availability != "available", "Available draft cannot claim missing artifact")
        elif reason == "conflicting_public_assertions_abstain":
            require(public_revision._conflicts(task) or public_revision._conflicts(public_task),
                    "Conflict abstention needs registered conflicting public assertions")
        else:
            stage = record["draft_stage"]
            require(stage is not None, "Execution-unknown skip requires a recorded public stage")
            require(not public_revision._revision_eligible(stage, request.get("clean_timeout_revision_policy")),
                    "Observed public execution cannot be mislabeled unsupported")
    require(record["revision_opportunity_completed"] == (status in {"revised", "kept", "retained"}),
            "Revision opportunity marker changed")
    if draft.availability != "available":
        require(status == "skipped" and reason == "artifact_unavailable" and record["draft_stage"] is None,
                "Unavailable draft cannot claim an executed repair")
    final_stage = record["revised_stage"] if status == "revised" else record["draft_stage"]
    # Only the recorded opt-in may enrich a replay-verified clean timeout. A
    # legacy/ordinary unknown never acquires an observed-return interpretation
    # or a semantic repair label; default F feedback remains byte-identical.
    timeout_policy = request.get("clean_timeout_revision_policy")
    visible = {"draft": {"availability": draft.availability,
        "solution.py": next((f.content for f in draft.files if f.path == "solution.py"), None),
        "public_check": _stage_view(record["draft_stage"], task, public_task, draft, text,
                                    clean_timeout_policy=timeout_policy, format_policy=format_policy)},
        "selected_public_check": _stage_view(final_stage, task, public_task, selected, text,
                                             clean_timeout_policy=timeout_policy, format_policy=format_policy),
        "revision_decision": status, "revision_reason": reason,
        "source_changed": draft.artifact_hash != selected.artifact_hash,
        "selected_final_feedback_status": feedback_status,
        "public_recheck_disagreement": after != feedback_status}
    row = {"draft_status": before, "selected_status": after, "final_feedback_status": feedback_status,
        "transition": _transition(before, after), "draft_availability": draft.availability,
        "revision_decision": status, "revision_reason": reason, "source_changed": visible["source_changed"],
        "public_recheck_disagreement": after != feedback_status}
    if request.get("public_selection_policy") == public_revision.PUBLIC_NONREGRESSION_POLICY:
        attempt = record["revised_artifact"]
        attempt_stage = record["revised_stage"]
        attempt_status = attempt_stage["report"]["status"] if attempt_stage is not None else "not_attempted"
        attempt_transition = _transition(before, attempt_status) if attempt_stage is not None else "not_attempted"
        visible.update(public_selection_policy=public_revision.PUBLIC_NONREGRESSION_POLICY,
                       attempt_transition=attempt_transition, attempted_revision=None)
        if attempt is not None:
            attempted = _artifact(attempt)
            visible["attempted_revision"] = {
                "solution.py": next(f.content for f in attempted.files if f.path == "solution.py"),
                "public_check": _stage_view(attempt_stage, task, public_task, attempted, text,
                                            clean_timeout_policy=timeout_policy, format_policy=format_policy),
                "selected": status == "revised",
                "source_changed_from_draft": attempted.artifact_hash != draft.artifact_hash}
        row.update(public_selection_policy=public_revision.PUBLIC_NONREGRESSION_POLICY,
                   attempt_status=attempt_status, attempt_transition=attempt_transition,
                   attempt_selected=status == "revised", attempt_retained_for_feedback=attempt is not None)
    alias = (key, initial["request_hash"], None if receipt is None else receipt["request_hash"])
    return key, role, row, visible, alias, task.contract.family_id


def _select(pairs, families, limit):
    require(type(limit) is int and 1 <= limit <= 8, "Repair detail limit must be 1..8 PAIRS")
    priority = {name: i for i, name in enumerate(STRATA)}
    strata = {key: min((transition for r in pair.values()
                       for transition in (r["transition"], r.get("attempt_transition")) if transition in priority),
                      key=priority.get) for key, pair in pairs.items()}
    remaining, selected, tasks, seen_families = set(pairs), [], set(), set()
    first_round = True
    while remaining and len(selected) < limit:
        for stratum in STRATA:
            fresh = any(key[0] not in tasks for key in remaining)
            options = [key for key in remaining if strata[key] == stratum and (not fresh or key[0] not in tasks)]
            if not options:
                continue
            key = min(options, key=lambda k: (families[k] in seen_families, k[1], k[0]))
            selected.append(key)
            tasks.add(key[0])
            seen_families.add(families[key])
            remaining.remove(key)
            if len(selected) == limit:
                break
        if first_round and len(selected) < limit:
            anchors = [key for key in selected if strata[key] in {"deteriorated", "unresolved"}]
            alternatives = [key for key in remaining if strata[key] == "stable"
                            and all(r["final_feedback_status"] == "pass" and not r["public_recheck_disagreement"]
                                    for r in pairs[key].values())
                            and any(key[0] == anchor[0] for anchor in anchors)]
            if alternatives:
                key = min(alternatives, key=lambda k: (k[1], k[0]))
                selected.append(key)
                tasks.add(key[0])
                seen_families.add(families[key])
                remaining.remove(key)
        first_round = False
    return selected


def build_details(parent, bundle, sources, *, detail_limit=6):
    """Replay ALL public positions, then build a small shared final-only bundle.

    ``sources`` are serialized, source-bound public records, not paths. They
    must exactly cover the complete final-feedback roster. This is offline;
    missing or mismatched evidence is an integrity error, never a retry.
    """
    build_update_request(parent, bundle)  # Existing full coverage receipt replay.
    _require_supported_execution(bundle["execution_records"])
    require(type(sources) in (tuple, list) and len(sources) <= 256, "Bounded complete source list required")
    finals = {}
    for e in bundle["entries"]:
        task = CallableTask.from_dict(e["task"])
        artifacts = tuple(map(ArtifactRecord.from_dict, e["artifacts"]))
        key = task.contract.content_hash, artifacts[0].repeat
        finals[key] = {"task": task, "artifacts": {a.condition: a for a in artifacts},
                      "reports": {a.condition: r for a, r in zip(artifacts, e["reports"])}}
    pairs, views, families, aliases, source_map = {}, {}, {}, {}, {}
    alias_observations, api_receipts = {}, {}
    initial_requests, revision_requests = set(), set()
    identity = bundle["execution_identity"]["executor"]
    for source in sources:
        key, role, row, view, alias, family = _source(source, parent, finals, identity)
        require((key, role) not in source_map, "Duplicate repair position")
        source_map[key, role] = deepcopy(source)
        pairs.setdefault(key, {})[role] = row
        views.setdefault(key, {})[role] = view
        families[key] = family
        # A cached response may be executed more than once. If public execution
        # varies, preserve both observations; identical API keys do not prove
        # identical runtime behavior or justify discarding an unfavorable row.
        alias_observations.setdefault(alias, set()).add(digest(row))
        aliases[alias, digest(row)] = row
        for receipt in (source["initial"]["api_receipt"], source["revision"]["api_receipt"]):
            if receipt is not None:
                request_hash, receipt_hash = receipt["request_hash"], digest(receipt)
                require(request_hash not in api_receipts or api_receipts[request_hash] == receipt_hash,
                        "Same cached API request is bound to different response receipts")
                api_receipts[request_hash] = receipt_hash
        initial_requests.add(alias[1])
        if alias[2] is not None:
            revision_requests.add(alias[2])
    require(set(pairs) == set(finals) and all(set(p) == {"no_skill", "current"} for p in pairs.values()),
            "Repair evidence must cover every registered task/repeat/role, including unknowns")
    selected = _select(pairs, families, detail_limit)
    subset = [{"task": finals[k]["task"],
               "artifacts": tuple(finals[k]["artifacts"][r] for r in ("no_skill", "current")),
               "reports": tuple(finals[k]["reports"][r] for r in ("no_skill", "current"))} for k in selected]
    final_bundle = build_feedback_bundle(subset, parent_skill=render_skill(parent),
        rubric=RubricVersion.from_dict(bundle["rubric"]), pipeline_hash=bundle["pipeline_hash"],
        execution_identity=bundle["execution_identity"], execution_records=tuple(bundle["execution_records"]))
    task_slots = {key: f"task_{i:03d}" for i, key in enumerate(sorted({k[0] for k in pairs}))}
    positions = [row for pair in pairs.values() for row in pair.values()]
    def counts(rows):
        return {name: {status: sum(r[name] == status for r in rows) for status in ("pass", "fail", "unknown")}
                for name in ("draft_status", "selected_status", "final_feedback_status")}
    coverage = {"task_count": len(task_slots), "structural_family_count": len(set(families.values())),
        "pair_count": len(pairs), "position_count": len(positions), "distinct_request_trajectories": len(aliases),
        "unique_request_pairs": len(alias_observations),
        "same_request_observation_disagreements": sum(len(v) > 1 for v in alias_observations.values()),
        "unique_initial_requests": len(initial_requests), "unique_revision_requests": len(revision_requests),
        "position_status_counts": counts(positions), "deduplicated_status_counts": counts(list(aliases.values())),
        "position_transition_counts": dict(Counter(r["transition"] for r in positions)),
        "deduplicated_transition_counts": dict(Counter(r["transition"] for r in aliases.values())),
        "positions": [{"task_slot": task_slots[key[0]], "repeat": key[1], "roles": pairs[key]} for key in sorted(pairs)],
        "selection_policy": SELECTION, "detail_limit_pairs": detail_limit,
        "selected_pairs": [{"task_slot": task_slots[k[0]], "repeat": k[1]} for k in selected],
        "limits": ["Within-run repair is not a causal Skill effect.",
                   "Repeated positions/request aliases are not new independent tasks.",
                   "Structural family labels do not establish independent semantic families.",
                   "A public pass is not a hidden audit or complete correctness result."]}
    if any("attempt_transition" in row for row in positions):
        coverage["selection_policy"] += (" For the explicit public nonregression policy only, an attempted "
            "revision's transition also contributes to stratum priority; rejected deterioration is not hidden as stable.")
        coverage["position_attempt_transition_counts"] = dict(Counter(
            r.get("attempt_transition", "legacy_unreported") for r in positions))
        coverage["deduplicated_attempt_transition_counts"] = dict(Counter(
            r.get("attempt_transition", "legacy_unreported") for r in aliases.values()))
    annex = []
    for binding, pair in zip(final_bundle["source_bindings"], final_bundle["model_view"]["paired_development"]):
        key = binding["task_hash"], binding["repeat"]
        role_views = views[key]
        item = {"evidence_id": "ev_" + digest(pair)[:24], "task_slot": task_slots[key[0]], "repeat": key[1]}
        if _encode(role_views["no_skill"]) == _encode(role_views["current"]):
            item.update(shared_trajectory=role_views["no_skill"],
                        roles={r: {"trajectory_ref": "shared_trajectory"} for r in ("no_skill", "current")})
        else:
            item["roles"] = role_views
        annex.append(item)
    return seal({"version": VERSION, "parent_hash": parent.content_hash,
        "feedback_bundle_hash": bundle["record_hash"], "detail_limit": detail_limit,
        "sources": [source_map[k] for k in sorted(source_map)], "coverage": coverage,
        "selected_final_bundle": final_bundle, "annex": annex,
        "information_origin": "replayed_registered_public_generation_and_execution",
        "hidden_audit_used": False, "research_increment": False,
        "learning_authorized": False, "deployment_authorized": False})


def _validate(parent, bundle, details):
    verify(details)
    require(details["version"] == VERSION, "Unknown repair details version")
    rebuilt = build_details(parent, bundle, details["sources"], detail_limit=details["detail_limit"])
    require(details == rebuilt, "Repair projection differs from source replay")
    return rebuilt


def build_request(parent, bundle, details, *, arm, max_tokens=2048):
    require(arm in ARMS, "Unknown repair-feedback arm")
    details = _validate(parent, bundle, details)
    base = mechanism_learning.build_request(parent, details["selected_final_bundle"],
                                             strategy="mechanism", max_tokens=max_tokens)
    payload = json.loads(base["user"])
    payload["public_repair_coverage"] = deepcopy(details["coverage"])
    payload["public_repair_annex"] = deepcopy(details["annex"]) if arm == "trajectory" else []
    system, user = base["system"] + POLICY, _encode(payload)
    nbytes = len((system + user).encode("utf-8"))
    if nbytes > MAX_PROMPT_BYTES:
        raise PromptBudgetExceeded(nbytes)
    return seal({**{k: v for k, v in base.items() if k != "record_hash"},
        "version": VERSION, "arm": arm, "details_record_hash": details["record_hash"],
        "source_feedback_hash": bundle["record_hash"], "base_request_hash": base["record_hash"],
        "system": system, "user": user, "prompt_hash": digest({"system": system, "user": user}),
        "prompt_bytes": nbytes, "call_kind": CALL_KIND, "research_increment": False,
        "learning_authorized": False, "deployment_authorized": False})


def propose(calls, parent, bundle, details, *, arm, repeat=0, max_tokens=2048):
    require(type(repeat) is int and repeat >= 0, "Nonnegative proposal repeat required")
    request = build_request(parent, bundle, details, arm=arm, max_tokens=max_tokens)
    receipt = calls.call(request["system"], request["user"], CALL_KIND, repeat=repeat, max_tokens=max_tokens)
    sent = receipt.get("request")
    require(type(receipt.get("ok")) is bool and type(sent) is dict and receipt["request_hash"] == digest(sent)
            and all(sent.get(k) == v for k, v in {"system": request["system"], "user": request["user"],
                "kind": CALL_KIND, "repeat": repeat, "max_tokens": max_tokens}.items()),
            "Repair updater response belongs to another request")
    parsed = candidate_from_response(receipt.get("response"), parent, details["selected_final_bundle"],
        update_mode="rule_patch", feedback_mode="evidence", max_edits=2) if receipt["ok"] else None
    if parsed is not None:
        require(parsed["request_hash"] == request["parser_request_hash"], "Repair parser source changed")
    return seal({"version": VERSION, "status": parsed["status"] if parsed else "api_failure",
        "arm": arm, "request": request, "api_receipt": receipt, "api_receipt_hash": digest(receipt),
        "update": parsed, "details_record_hash": details["record_hash"],
        "semantic_support_verified": False, "confirmation_required": True,
        "research_increment": False, "hidden_audit_used": False, "retry_authorized": False,
        "learning_authorized": False, "deployment_authorized": False,
        "fixture_only": sent.get("service", {}).get("fixture") is True})
