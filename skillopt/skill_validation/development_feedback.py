"""Complete public-development coverage with bounded, stratified detail.

Every supplied pair is replayed through the frozen feedback boundary. The host
bundle retains replay inputs so loading a bundle rechecks summaries, identities
and selection; only ``messages`` may project it to a model. No code is executed,
and hashes establish consistency, not execution authenticity.

Evidence detail uses a fixed public-V stratification policy. The contract-only
control independently selects at most 16 unique tasks by task hash, never by
outcomes, submitted source, or the evidence-detail selection.
"""
from __future__ import annotations

import json
from collections import deque
from copy import deepcopy

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from .checks import CallableTask
from .conditional_feedback import MODES, PUBLIC_CONTEXT, public_role_summary
from .conditional_feedback import messages as conditional_messages
from .models import ArtifactRecord, RubricVersion, require, text
from .single_round_feedback import MAX_CONTEXT_BYTES, ROLES, _ReceiptReplay
from .single_round_feedback import build_feedback_bundle, skill_hash
from .single_round_feedback import messages as validated_messages

VERSION = "complete-development-public-feedback-v1"
MAX_PAIRS = 128
MAX_DETAILS = 16
MAX_PROMPT_BYTES = 120000
STRATA = ("loss", "shared_fail", "win", "unknown", "both_pass")
SELECTION_POLICY = (
    "Fixed round-robin across loss, shared_fail, win, unknown, both_pass; within each stratum, "
    "round-robin across repeat indices and then task-hash order. Unknown pairs with a confirmed "
    "public failure precede other unknown pairs. Skip details that exceed the 120000-byte system-plus-user budget. "
    "Only replay-validated public V statuses determine strata; no hidden audit is read."
)
INTERPRETATION = (
    "Only public V is summarized. Distinct task identities are the task denominator; repeat positions "
    "are repeated measures, not additional independent tasks. These paired observations are not causal "
    "Skill effects. Unknown is not a confirmed failure. Shared failures are not Skill-specific failures. "
    "Public passes do not establish full correctness. Selected detail is a stratified illustration, "
    "not the denominator for the complete-development counts."
)
_BUNDLE_FIELDS = {
    "version", "parent_skill_hash", "rubric", "pipeline_hash", "execution_identity", "execution_records",
    "entries", "detail_limit", "coverage", "selected_source_bindings", "selected_bundle", "contract_only",
    "shadow_only", "deployment_authorized", "record_hash",
}


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


class _PromptBudgetExceeded(ValueError):
    """Only the final API-size limit, never a receipt-validation failure."""


def _limit(value):
    require(type(value) is int and 1 <= value <= MAX_DETAILS, "Detail limit must be an integer from 1 to 16")


def _stratum(pair):
    baseline, current = (pair["roles"][role]["status"] for role in ROLES)
    if "unknown" in (baseline, current):
        return "unknown"
    if baseline == current:
        return "both_pass" if current == "pass" else "shared_fail"
    return "win" if current == "pass" else "loss"


def _ordered_detail_keys(pairs):
    queues = {}
    for stratum in STRATA:
        # An unknown/fail pair retains its known failure, without relabeling the
        # unknown side as failed. Within each priority group cover all repeats.
        groups = (True, False) if stratum == "unknown" else (False,)
        ordered = []
        for failure_first in groups:
            by_repeat = {}
            for key, pair in sorted(pairs.items()):
                known_failure = any(pair["roles"][role]["status"] == "fail" for role in ROLES)
                if _stratum(pair) != stratum or (stratum == "unknown" and known_failure != failure_first):
                    continue
                by_repeat.setdefault(key[1], deque()).append(key)
            while any(by_repeat.values()):
                for repeat in sorted(by_repeat):
                    if by_repeat[repeat]:
                        ordered.append(by_repeat[repeat].popleft())
        queues[stratum] = deque(ordered)
    result = []
    while any(queues.values()):
        for stratum in STRATA:
            if queues[stratum]:
                result.append(queues[stratum].popleft())
    return result


def _coverage(pairs, selected, detail_limit):
    task_hashes = sorted({key[0] for key in pairs})
    slots = {task_hash: f"task_{index:03d}" for index, task_hash in enumerate(task_hashes)}
    rows, denominators = [], []
    for key, pair in sorted(pairs.items()):
        kinds = {obligation["id"]: obligation["kind"] for obligation in pair["task"]["obligations"]}
        failures = {}
        for role in ROLES:
            checks = {(check["method"], kinds[check["obligation_id"]])
                      for check in pair["roles"][role]["checks"] if check["status"] == "fail"}
            failures[role] = [{"method": method, "obligation_kind": kind} for method, kind in sorted(checks)]
        rows.append({"task_slot": slots[key[0]], "repeat": key[1], "stratum": _stratum(pair),
                     "statuses": {role: pair["roles"][role]["status"] for role in ROLES},
                     "availability": {role: pair["roles"][role]["artifact"]["availability"] for role in ROLES},
                     "failed_checks": failures})
    for repeat in sorted({key[1] for key in pairs}):
        keys = [key for key in pairs if key[1] == repeat]
        denominators.append({"repeat": repeat, "pair_count": len(keys), "task_count": len({k[0] for k in keys})})
    return {
        "information_origin": "replay_validated_public_V_only",
        "independent_task_count": len(task_hashes), "paired_repeat_count": len(pairs),
        "repeat_denominators": denominators,
        "role_counts": {role: {status: sum(pair["roles"][role]["status"] == status for pair in pairs.values())
                               for status in ("pass", "fail", "unknown")} for role in ROLES},
        "stratum_counts": {stratum: sum(_stratum(pair) == stratum for pair in pairs.values()) for stratum in STRATA},
        "pair_summaries": rows,
        # This order matches conditional_messages' ordering of selected details.
        "detailed_pairs": [{"task_slot": slots[key[0]], "repeat": key[1]} for key in sorted(selected)],
        "detail_limit": detail_limit, "detailed_pair_count": len(selected),
        "selection_policy": SELECTION_POLICY, "interpretation": INTERPRETATION,
    }


def _merge(singletons, selected):
    """Compose only legacy-validated singleton bundles, retaining its schema."""
    combined = [(singletons[key]["model_view"]["paired_development"][0],
                 singletons[key]["source_bindings"][0]) for key in selected]
    combined.sort(key=lambda item: digest(item[0]))
    prototype = singletons[selected[0]]
    view = {**deepcopy(prototype["model_view"]), "paired_development": [deepcopy(pair) for pair, _ in combined]}
    return seal({**{key: deepcopy(value) for key, value in prototype.items()
                   if key not in {"record_hash", "model_view", "model_view_hash", "source_bindings", "execution_receipts"}},
                 "source_bindings": [deepcopy(binding) for _, binding in combined],
                 "execution_receipts": sorted({receipt for key in selected
                                               for receipt in singletons[key]["execution_receipts"]}),
                 "model_view": view, "model_view_hash": digest(view)})


def _contracts(pairs, parent_skill, system):
    unique = {}
    for (task_hash, _), pair in sorted(pairs.items()):
        declaration = {"task": {key: deepcopy(pair["task"][key]) for key in
                                 ("information_origin", "domain", "prompt", "obligations")},
                       "public_cases": deepcopy(pair["public_cases"])}
        require(task_hash not in unique or unique[task_hash] == declaration,
                "Repeated task identity has inconsistent public declarations")
        unique[task_hash] = declaration
    control = {"purpose": "public_contract_conditioning_candidate_only", "development_contracts": []}
    # Independent of all submitted artifacts and outcomes, including selection
    # failures caused by large evidence detail. Content size here is public only.
    for task_hash in sorted(unique)[:MAX_DETAILS]:
        trial = {**control, "development_contracts": control["development_contracts"] + [unique[task_hash]]}
        trial_bytes = len(system.encode("utf-8")) + _size(
            {"parent_skill": parent_skill, "public_context": PUBLIC_CONTEXT, "feedback": trial})
        if trial_bytes <= MAX_PROMPT_BYTES:
            control = trial
    require(bool(control["development_contracts"]), "No public contract fits the bounded control context")
    return control


def _render(parent_skill, selected_bundle, coverage, control, mode, all_summary):
    system, original_user, _ = conditional_messages(parent_skill, selected_bundle, mode)
    payload = json.loads(original_user)
    if mode == "evidence":
        payload["feedback"]["coverage"] = deepcopy(coverage)
        payload["feedback"]["public_role_summary"] = deepcopy(all_summary)
        system += (
            " The coverage section summarizes every supplied development task/repeat pair. Its paired-repeat "
            "count is the denominator for public outcome counts; independent_task_count counts distinct tasks. "
            "Detailed examples are selected by the declared public-status strata and are not a representative "
            "performance sample. Match them to coverage.detailed_pairs in order. Use the complete pair "
            "summaries to notice failures omitted from detailed examples."
        )
    else:
        payload["feedback"] = deepcopy(control)
    user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    text(user, maximum=MAX_CONTEXT_BYTES)
    if len(system.encode("utf-8")) + len(user.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise _PromptBudgetExceeded("Development feedback exceeds frozen API prompt budget")
    return system, user, digest({"system": system, "user": user})


def build_development_feedback(entries, *, parent_skill, rubric, pipeline_hash,
                               execution_identity, execution_records, detail_limit=16):
    """Return a JSON-serializable, sealed HOST bundle for 1..128 matched pairs.

    ``entries`` has exactly the legacy ``build_feedback_bundle`` input schema.
    All pairs, including every repeat, pass that receipt-replay/whitelist
    boundary separately before selection. ``coverage`` is a public-only compact
    summary; ``selected_source_bindings`` identifies the detailed examples for
    host bookkeeping. ``entries``, ``rubric``, ``execution_*`` and bindings must
    never be passed to a model directly. ``messages`` replays these retained host
    inputs to verify a reused/loaded bundle, including any stored derived data.

    ``detail_limit`` is a maximum, not a promise: large details are skipped to
    keep the complete system-plus-user prompt within the API's 120,000-byte
    bound (as well as the legacy user-context limit). The
    control always independently hash-selects up to 16 distinct public tasks.
    """
    _limit(detail_limit)
    parent_hash = skill_hash(parent_skill)
    require(type(rubric) is RubricVersion, "Typed Rubric required")
    replay = _ReceiptReplay(execution_identity, execution_records)
    receipt_index = {}
    for receipt in replay.records.values():
        request = receipt["request"]
        key = request["callable_task_hash"], request["artifact_record_hash"]
        receipt_index.setdefault(key, []).append(receipt)
    singletons, pairs, raw_entries, seen_task_ids, task_identities = {}, {}, {}, set(), {}
    for index, entry in enumerate(entries):
        require(index < MAX_PAIRS, "Too many development pairs")
        require(type(entry) is dict and set(entry) == {"task", "artifacts", "reports"},
                "Feedback entry contains unexpected/private fields")
        task, artifacts = entry["task"], entry["artifacts"]
        require(type(task) is CallableTask and type(artifacts) is tuple
                and len(artifacts) == 2 and all(type(a) is ArtifactRecord for a in artifacts),
                "Typed development task and two ArtifactRecord values required")
        receipts = tuple(record for artifact in artifacts
                         for record in receipt_index.get((task.content_hash, artifact.content_hash), ()))
        singleton = build_feedback_bundle([entry], parent_skill=parent_skill, rubric=rubric,
                                          pipeline_hash=pipeline_hash, execution_identity=execution_identity,
                                          execution_records=receipts)
        # Even the unselected pairs pass the legacy loaded-bundle projection.
        _, projected, _ = validated_messages(parent_skill, singleton)
        pair = json.loads(projected)["feedback"]["paired_development"][0]
        key = task.contract.content_hash, artifacts[0].repeat
        identity_key = task.contract.task_id, artifacts[0].repeat
        require(key not in pairs and identity_key not in seen_task_ids, "Duplicate development task/repeat pair")
        require(task.contract.task_id not in task_identities
                or task_identities[task.contract.task_id] == task.content_hash,
                "Repeated task identity must retain the same callable contract")
        task_identities[task.contract.task_id] = task.content_hash
        seen_task_ids.add(identity_key)
        pairs[key], singletons[key] = pair, singleton
        aligned = sorted(zip(entry["artifacts"], entry["reports"]), key=lambda item: item[0].condition)
        raw_entries[key] = {"task": task.to_dict(), "artifacts": [artifact.to_dict() for artifact, _ in aligned],
                            "reports": [deepcopy(report) for _, report in aligned]}
    require(bool(pairs), "At least one development pair required")
    # The control system instruction is fixed across outcomes. Obtain it from
    # an already validated singleton before the result-dependent detail choice.
    control_system = conditional_messages(parent_skill, singletons[min(singletons)], "contract_only")[0]
    control = _contracts(pairs, parent_skill, control_system)
    selected = []
    all_summary = public_role_summary(list(pairs.values()))
    for key in _ordered_detail_keys(pairs):
        trial = selected + [key]
        coverage = _coverage(pairs, trial, detail_limit)
        # Reserve conservative space for the legacy view/policy JSON wrappers;
        # no text or artifact is truncated to make a detail fit.
        trial_bytes = (_size({"parent_skill": parent_skill, "public_context": PUBLIC_CONTEXT,
                              "coverage": coverage, "public_role_summary": all_summary})
                       + sum(_size(pairs[item]) for item in trial) + 4096)
        if trial_bytes > MAX_PROMPT_BYTES:
            continue
        # Count the exact final system plus user bytes before retaining a
        # detail; coverage rows and source strings are never truncated.
        try:
            _render(parent_skill, _merge(singletons, trial), coverage, control, "evidence", all_summary)
        except _PromptBudgetExceeded:
            continue
        selected = trial
        if len(selected) == detail_limit:
            break
    require(bool(selected), "No complete development detail fits beside full coverage")
    selected_bundle = _merge(singletons, selected)
    coverage = _coverage(pairs, selected, detail_limit)
    # Check the actual final contexts as well as the conservative size bound.
    for mode in MODES:
        _render(parent_skill, selected_bundle, coverage, control, mode, all_summary)
    return seal({
        "version": VERSION, "parent_skill_hash": parent_hash, "rubric": rubric.to_dict(),
        "pipeline_hash": pipeline_hash, "execution_identity": deepcopy(execution_identity),
        "execution_records": [deepcopy(record) for record in sorted(execution_records, key=lambda record: record["record_hash"])],
        "entries": [raw_entries[key] for key in sorted(raw_entries)], "detail_limit": detail_limit,
        "coverage": coverage, "selected_source_bindings": deepcopy(selected_bundle["source_bindings"]),
        "selected_bundle": selected_bundle, "contract_only": control,
        "shadow_only": True, "deployment_authorized": False,
    })


def messages(parent_skill, coverage_bundle, mode="evidence"):
    """Return ``(system, user, prompt_hash)`` after full offline receipt replay.

    Recompute every derived field instead of trusting resealed coverage counts,
    source bindings, model views, or contract-control projections. This does
    not authenticate the host's receipts or the completeness of its input set.
    """
    require(mode in MODES, "Unknown development-feedback mode")
    verify(coverage_bundle)
    require(set(coverage_bundle) == _BUNDLE_FIELDS, "Unexpected development-feedback bundle fields")
    require(coverage_bundle["version"] == VERSION
            and coverage_bundle["parent_skill_hash"] == skill_hash(parent_skill)
            and coverage_bundle["shadow_only"] is True and coverage_bundle["deployment_authorized"] is False,
            "Changed parent, feedback, or exploratory authority")
    require(type(coverage_bundle["entries"]) is list and 0 < len(coverage_bundle["entries"]) <= MAX_PAIRS,
            "Bounded serialized development entries required")
    require(type(coverage_bundle["execution_records"]) is list, "Serialized execution records require an array")
    entries = []
    for entry in coverage_bundle["entries"]:
        require(type(entry) is dict and set(entry) == {"task", "artifacts", "reports"},
                "Feedback entry contains unexpected/private fields")
        require(type(entry["artifacts"]) is list and type(entry["reports"]) is list,
                "Serialized artifact/report arrays required")
        entries.append({"task": CallableTask.from_dict(entry["task"]),
                        "artifacts": tuple(ArtifactRecord.from_dict(value) for value in entry["artifacts"]),
                        "reports": tuple(deepcopy(entry["reports"]))})
    rebuilt = build_development_feedback(
        entries, parent_skill=parent_skill, rubric=RubricVersion.from_dict(coverage_bundle["rubric"]),
        pipeline_hash=coverage_bundle["pipeline_hash"], execution_identity=coverage_bundle["execution_identity"],
        execution_records=tuple(coverage_bundle["execution_records"]), detail_limit=coverage_bundle["detail_limit"],
    )
    require(coverage_bundle == rebuilt, "Coverage bundle differs from source-bound receipt replay")
    summary = public_role_summary([
        {"roles": {role: {"status": row["statuses"][role]} for role in ROLES}}
        for row in rebuilt["coverage"]["pair_summaries"]
    ])
    return _render(parent_skill, rebuilt["selected_bundle"], rebuilt["coverage"], rebuilt["contract_only"], mode, summary)
