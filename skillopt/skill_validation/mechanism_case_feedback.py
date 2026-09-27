"""Public case details appended to the SAME frozen boolean-feedback examples.

This independent diagnostic does not alter historical experiments. Both arms
use the mechanism-learning v3 policy, inline original evidence IDs, RuleUpdate
schema and budget. Only the public-case annex differs. Original wrapper results
remain intact, including joint/in-place checks the direct examples cannot prove.
The caller must load public rows from its frozen source panel and retain that
panel's provenance: the old feedback bundle does not itself store direct cases.
"""
from __future__ import annotations

import json
from copy import deepcopy

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

from . import mechanism_learning, public_case_feedback
from .checks import CallableTask
from .development_feedback import VERSION as COVERAGE_VERSION
from .models import ArtifactRecord, require
from .panel import checked_path
from .public_revision import _parts, _read, _revision_lock, _write
from .rule_learning import MAX_PROMPT_BYTES, build_update_request, candidate_from_response

VERSION = "same-feedback-public-case-annex-v2"
ARMS = ("boolean", "case_details")
CALL_KIND = "mechanism-public-case-annex-update"
ANNEX_POLICY = (
    " An optional public_case_annex expands only the already selected final-artifact examples. "
    "It never replaces the original wrapper outcomes, which can check additional joint or in-place "
    "requirements. A direct return match therefore does not overturn a wrapper failure. "
    "Treat differences as evidence of a remaining verification gap, not proof that the old check is wrong. "
    "Annex entries attach to the existing pair evidence_id; cite only original ev_ catalog IDs in edits "
    "and rules, never case IDs or record hashes. References prove identity, not semantic support. "
    "The annex contains no draft-to-revision trajectory, hidden audit, new task, Research finding, "
    "or inferred in-place target. Missing observations and unregistered postconditions remain unknown. "
    "Within one pair only, completely identical cases and counts are stored once as shared_observations; "
    "each role then has observations_ref='shared_observations' and its own public_case_record_hash. "
    "Read that same observation object for each referenced role. Different observations remain in each "
    "role in full. Sharing text neither merges the two real receipts nor adds independent evidence. "
)
_DETAIL_FIELDS = {"version", "parent_hash", "feedback_bundle_hash", "parser_request_hash",
    "feedback_view_hash", "sources", "execution_identity", "entries", "information_origins",
    "registration_provenance", "original_wrapper_feedback_retained", "research_increment",
    "learning_authorized", "deployment_authorized", "record_hash"}
_CASE_FIELDS = ("id", "public_input", "expected", "expected_is_provided", "expected_exception",
    "observation", "return_check", "input_state_changed", "preservation_check",
    "other_state_requirements", "obligation_ids")


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class PromptBudgetExceeded(ValueError):
    """Only final prompt size, never a source binding or evidence error."""

    def __init__(self, actual_bytes, limit_bytes):
        self.actual_bytes, self.limit_bytes = actual_bytes, limit_bytes
        super().__init__(f"Public-case annex prompt is {actual_bytes} bytes, limit {limit_bytes}; "
                         "do not truncate cases or original feedback")


def _share_pair_observations(role_views):
    """Lossless within-pair text sharing after both receipts were validated."""
    observed = {role: {key: role_views[role][key] for key in ("cases", "counts")}
                for role in ("no_skill", "current")}
    # JSON equivalence is deliberately type-sensitive (True is not integer 1),
    # preserves array order, and ignores only the separately retained receipts.
    if _encode(observed["no_skill"]) != _encode(observed["current"]):
        return {"roles": deepcopy(role_views)}
    return {"roles": {role: {"public_case_record_hash": role_views[role]["public_case_record_hash"],
                             "observations_ref": "shared_observations"}
                      for role in ("no_skill", "current")},
            "shared_observations": deepcopy(observed["no_skill"])}


def _sources(parent, bundle):
    require(type(bundle) is dict and bundle.get("version") == COVERAGE_VERSION,
            "Complete development coverage bundle required; legacy summaries lack bound artifacts")
    request = build_update_request(parent, bundle, update_mode="rule_patch", feedback_mode="evidence", max_edits=2)
    visible_pairs = json.loads(request["user"])["feedback"]["paired_development"]
    # selected_bundle aligns its raw pairs with bindings; the existing feedback
    # projection orders details by (task hash, repeat), not raw digest order.
    selected = bundle["selected_bundle"]
    bound = sorted(zip(selected["source_bindings"], selected["model_view"]["paired_development"]),
                   key=lambda item: (item[0]["task_hash"], item[0]["repeat"]))
    require(len(bound) == len(visible_pairs) <= 16, "Selected detail set changed")
    allowed_ids = {e["id"] for e in request["evidence_catalog"] if e["kind"] == "public_paired_detail"}
    entries = {}
    for entry in bundle["entries"]:
        task = CallableTask.from_dict(entry["task"])
        artifacts = {a.condition: a for a in map(ArtifactRecord.from_dict, entry["artifacts"])}
        key = (task.contract.content_hash, artifacts["current"].repeat)
        require(key not in entries, "Duplicate original feedback pair")
        entries[key] = (task, artifacts)
    sources, artifacts_by_pair = [], []
    for index, ((binding, raw_pair), pair) in enumerate(zip(bound, visible_pairs)):
        require(raw_pair == pair, "Original selected details changed order or contents")
        evidence_id = "ev_" + digest(pair)[:24]
        require(evidence_id in allowed_ids, "Original detail has no catalog evidence ID")
        key = binding["task_hash"], binding["repeat"]
        require(key in entries, "Selected detail has no original task/artifact pair")
        task, artifacts = entries[key]
        require(task.content_hash == binding["callable_task_hash"], "Original public checker identity changed")
        for role in ("no_skill", "current"):
            report = next(r for r in binding["reports"] if r["role"] == role)
            require(artifacts[role].content_hash == report["artifact_record_hash"]
                    and artifacts[role].artifact_hash == report["artifact_hash"]
                    and artifacts[role].repeat == binding["repeat"], "Original artifact/repeat binding changed")
        sources.append({"pair_index": index, "evidence_id": evidence_id,
            "task_hash": task.contract.content_hash, "public_task_hash": task.content_hash,
            "repeat": binding["repeat"], "artifacts": {r: a.content_hash for r, a in artifacts.items()}})
        artifacts_by_pair.append((task, artifacts))
    return request, sources, artifacts_by_pair


def _assemble(parent, bundle, entries):
    request, sources, artifacts_by_pair = _sources(parent, bundle)
    require(type(entries) is list and len(entries) == len(sources), "One annex entry per original detail required")
    views, identity = [], None
    for source, (public_task, artifacts), entry in zip(sources, artifacts_by_pair, entries):
        require(type(entry) is dict and set(entry) == {"source", "roles"} and entry["source"] == source,
                "Annex entry belongs to another selected pair")
        require(type(entry["roles"]) is dict and set(entry["roles"]) == {"no_skill", "current"},
                "Both original roles must remain in every annex entry")
        role_views = {}
        for role, artifact in artifacts.items():
            record = entry["roles"][role]
            view = public_case_feedback.model_view(record)  # Full typed + receipt replay, never trust a sealed view.
            require(record["artifact"] == artifact.to_dict() and record["public_task"] == public_task.to_dict(),
                    "Annex observation is not from the original final artifact/public checker")
            require(record["execution_identity"]["executor"] == bundle["execution_identity"]["executor"],
                    "Annex executor policy differs from the original feedback")
            identity = record["execution_identity"] if identity is None else identity
            require(record["execution_identity"] == identity, "Mixed annex execution identities")
            role_views[role] = {"public_case_record_hash": record["record_hash"],
                "cases": [{k: deepcopy(case[k]) for k in _CASE_FIELDS} for case in view["cases"]],
                "counts": deepcopy(view["counts"])}
        views.append({"pair_index": source["pair_index"], "evidence_id": source["evidence_id"],
                      **_share_pair_observations(role_views)})
    record = seal({"version": VERSION, "parent_hash": parent.content_hash,
        "feedback_bundle_hash": bundle["record_hash"], "parser_request_hash": request["record_hash"],
        "feedback_view_hash": request["feedback_view_hash"], "sources": sources,
        "execution_identity": identity, "entries": deepcopy(entries),
        "information_origins": list(public_case_feedback.ORIGINS),
        "registration_provenance": "caller_supplied_frozen_public_rows; original panel provenance is caller responsibility",
        "original_wrapper_feedback_retained": True, "research_increment": False,
        "learning_authorized": False, "deployment_authorized": False})
    return record, views


def collect_details(parent, bundle, panel_public_rows, executor, root):
    """Execute direct public cases only for the bundle's already selected finals.

    Read exactly task/public_task/public_wrapper from supplied rows. The driver
    must supply them from its frozen original panel, not regenerate test cases.
    No caller row's host_only, region, private cases, or reference code is read.
    """
    request, sources, artifacts_by_pair = _sources(parent, bundle)
    require(type(panel_public_rows) in (list, tuple) and len(panel_public_rows) <= 1024,
            "Bounded list of frozen public rows required")
    require(executor.identity == bundle["execution_identity"]["executor"],
            "Annex executor policy differs from the original feedback")
    lookup = {}
    for row in panel_public_rows:
        task, public_task, wrapper = _parts(row)
        require(public_task.content_hash not in lookup, "Duplicate public panel row")
        lookup[public_task.content_hash] = {"task": task, "public_task": public_task,
                                          "public_wrapper": wrapper.to_dict()}
    require(all(s["public_task_hash"] in lookup for s in sources), "Original selected detail missing from public panel")
    base = checked_path(root)
    with _revision_lock(base):
        binding = seal({"version": VERSION, "parent_hash": parent.content_hash,
            "feedback_bundle_hash": bundle["record_hash"], "parser_request_hash": request["record_hash"],
            "sources": sources, "executor": executor.identity,
            "public_registrations": {key: digest({"task": lookup[key]["task"].to_dict(),
                "public_task": lookup[key]["public_task"].to_dict(), "public_wrapper": lookup[key]["public_wrapper"]})
                for key in sorted({s["public_task_hash"] for s in sources})}})
        _write(base / "binding.json", binding)
        path = base / "details.json"
        if path.exists():
            details = _read(path)
            _validate(parent, bundle, details)
            return details
        entries = []
        for source, (_, artifacts) in zip(sources, artifacts_by_pair):
            row = lookup[source["public_task_hash"]]
            roles = {role: public_case_feedback.collect(row, artifacts[role], executor,
                        base / "cases" / digest([source, role])) for role in ("no_skill", "current")}
            entries.append({"source": source, "roles": roles})
        details, _ = _assemble(parent, bundle, entries)
        _write(path, details)
        return details


def _validate(parent, bundle, details):
    verify(details)
    require(set(details) == _DETAIL_FIELDS and details["version"] == VERSION, "Unexpected annex fields/version")
    rebuilt, views = _assemble(parent, bundle, details["entries"])
    require(details == rebuilt, "Annex parent/source/observations changed")
    return views


def build_request(parent, bundle, details, *, arm, max_tokens=2048):
    require(type(arm) is str and arm in ARMS, "Unknown public-feedback arm")
    views = _validate(parent, bundle, details)
    base = mechanism_learning.build_request(parent, bundle, strategy="mechanism", max_tokens=max_tokens)
    require(base["parser_request_hash"] == details["parser_request_hash"], "Annex and updater source differ")
    payload = json.loads(base["user"])
    annex = views if arm == "case_details" else []
    payload["public_case_annex"] = annex
    system, user = base["system"] + ANNEX_POLICY, _encode(payload)
    prompt_bytes = len((system + user).encode("utf-8"))
    if prompt_bytes > MAX_PROMPT_BYTES:
        raise PromptBudgetExceeded(prompt_bytes, MAX_PROMPT_BYTES)
    return seal({**{k: v for k, v in base.items() if k != "record_hash"},
        "version": VERSION, "arm": arm, "base_mechanism_request_hash": base["record_hash"],
        "base_user_hash": digest(base["user"]),
        "evidence_annotation_scope": "original_base_user_before_public_case_annex",
        "details_record_hash": details["record_hash"], "annex_hash": digest(annex),
        "system": system, "user": user, "prompt_hash": digest({"system": system, "user": user}),
        "call_kind": CALL_KIND, "original_wrapper_feedback_retained": True,
        "research_increment": False, "learning_authorized": False})


def propose(calls, parent, bundle, details, *, arm, repeat=0, max_tokens=2048):
    require(type(repeat) is int and repeat >= 0, "Nonnegative integer repeat required")
    request = build_request(parent, bundle, details, arm=arm, max_tokens=max_tokens)
    receipt = calls.call(request["system"], request["user"], CALL_KIND, repeat=repeat, max_tokens=max_tokens)
    require(type(receipt) is dict and type(receipt.get("ok")) is bool, "Explicit API outcome and receipt required")
    sent = receipt.get("request")
    require(type(sent) is dict and receipt.get("request_hash") == digest(sent)
            and all(sent.get(k) == v for k, v in {"system": request["system"], "user": request["user"],
                "kind": CALL_KIND, "repeat": repeat, "max_tokens": max_tokens}.items()),
            "Annex updater receipt belongs to another request or is incomplete")
    parser_result = None
    if receipt["ok"]:
        parser_result = candidate_from_response(receipt.get("response"), parent, bundle,
                                                update_mode="rule_patch", feedback_mode="evidence", max_edits=2)
        require(parser_result["request_hash"] == request["parser_request_hash"],
                "Original feedback changed after the updater request")
        parsed = {k: v for k, v in parser_result.items() if k not in {"record_hash", "request_hash"}}
    else:
        parsed = {"status": "api_failure", "parent_hash": parent.content_hash,
            "candidate": None, "candidate_text": None, "evidence_catalog": request["evidence_catalog"],
            "scope_expansion_requests": [], "scope_status": "unconfirmed_proposal_only"}
    common = {"version": VERSION, "request_hash": request["record_hash"],
        "actual_update_request_hash": request["record_hash"], "parser_request_hash": request["parser_request_hash"],
        "details_record_hash": request["details_record_hash"], "annex_hash": request["annex_hash"],
        "feedback_view_hash": request["feedback_view_hash"], "semantic_support_verified": False,
        "confirmation_required": True, "learning_authorized": False, "deployment_authorized": False,
        "research_increment": False, "retry_authorized": False}
    update = seal({**parsed, **common,
        "parser_result_hash": parser_result["record_hash"] if parser_result else None,
        "feedback_use": "shadow_diagnostic_only"})
    service = sent.get("service")
    fixture = receipt.get("fixture_only") is True or (type(service) is dict and service.get("fixture") is True)
    return seal({**common, "arm": arm, "strategy": "mechanism", "status": update["status"],
        "request": request, "api_receipt": receipt, "api_receipt_hash": digest(receipt),
        "fixture_only": fixture, "update": update})
