"""Isolated, development-only diagnostic of one failed V7 plan contract.

This is an explicitly NEW experiment, not an original-run retry or replacement.
Only structural feedback is host-authored. A repaired plan and any later Rubric
remain unverified proposals: this module never calibrates, evaluates or activates.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import research as frozen
from skillopt.coevolution_v7.transport import make_budgeted_api
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "research-plan-contract-repair-diagnostic-v1"
MAX_CALLS = 3
MAX_TOKENS = 6000


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path, *, sealed=True):
    value = frozen.legacy._decode(Path(path).read_text()) if not sealed else json.loads(Path(path).read_text())
    return core.verify(value) if sealed else value


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _reject_symlink_tree(root):
    """Inspect existing entries without following links, before writes or IO clients.

    As with the frozen run transport, one process must own this directory. This
    preflight is not a defense against another process racing to replace entries.
    """
    pending = [Path(root)]
    while pending:
        path = pending.pop()
        _require(not path.is_symlink(), "Symlink inside diagnostic output tree is not supported")
        if path.is_dir():
            pending.extend(path.iterdir())


def _persist_or_verify(path, value, *, completed):
    if completed:
        _require(path.is_file(), "Completed diagnostic metadata/stage missing; no offline reconstruction")
        _require(_read(path) == value, "Completed diagnostic evidence changed")
    else:
        write_immutable_json(path, value)


def _dependencies():
    package = Path(__file__).resolve().parent
    paths = [Path(__file__), package.parent / "scripts/repair_research_contract.py",
             package / "coevolution_v7/transport.py", package / "coevolution/budget.py",
             package / "validator_pilot/api.py"]
    return {**frozen._dependency_hashes(), **{str(p.relative_to(package.parent)): _sha(p) for p in paths}}


def structure_errors(raw, evidence):
    """Describe only the observed contract errors, never supply research content.

    Other failure kinds are outside this narrow diagnostic and fail closed.
    The caller separately establishes full transport completion and invalidity.
    """
    value = frozen.legacy._decode(raw)
    _require(set(value) <= {"explanations", "questions", "urls"}, "Unexpected original plan fields")
    errors = [{"path": name, "error": "missing_required_field"}
              for name in ("questions", "urls") if name not in value]
    rows = value.get("explanations")
    _require(isinstance(rows, list) and 1 <= len(rows) <= 30, "Unsupported original explanation structure")
    if not 2 <= len(rows) <= 4:
        errors.append({"path": "explanations", "error": "count_outside_contract",
                       "observed": len(rows), "minimum": 2, "maximum": 4})
    for i, row in enumerate(rows):
        _require(isinstance(row, dict) and set(row) == {"hypothesis", "check", "evidence_refs"}
                 and all(frozen._text(row[k], 1200) for k in ("hypothesis", "check")),
                 "Unsupported original hypothesis schema")
        refs = row["evidence_refs"]
        _require(isinstance(refs, list) and 1 <= len(refs) <= 6, "Unsupported original reference count")
        for j, ref in enumerate(refs):
            if not isinstance(ref, dict) or set(ref) != frozen.REF_FIELDS:
                errors.append({"path": f"explanations[{i}].evidence_refs[{j}]",
                    "error": "reference_must_be_five_field_object", "required_fields": sorted(frozen.REF_FIELDS),
                    "observed_type": type(ref).__name__})
            else:
                frozen._references([ref], evidence)
    # Existing question/URL content is not repaired by host feedback in this diagnostic.
    if "questions" in value or "urls" in value:
        _require("questions" in value and "urls" in value, "Unsupported partial original research content")
        frozen.documents.parse_plan({"questions": value["questions"], "urls": value["urls"]})
    _require(bool(errors), "No eligible structural errors; do not resample a valid or different failure")
    return errors


def inspect_source(repo, source_run):
    """Read only the original development selection and failed Research evidence.

    No results, calibration, final trajectories, credentials or executors are read.
    Hashes establish local consistency, not independent execution authentication.
    """
    source_path = Path(source_run).absolute()
    _require(not any(p.is_symlink() for p in (source_path, *source_path.parents)), "Symlink source run is not supported")
    repo, source_run = Path(repo).resolve(), source_path.resolve()
    candidates = sorted((source_run / "research/research_evolution").glob("*/identity.json"))
    _require(len(candidates) == 1, "Exactly one original frozen Research identity required")
    directory = candidates[0].parent
    identity = _read(directory / "identity.json", sealed=False)
    _require(directory.name == digest(identity) and identity.get("version") == frozen.VERSION,
             "Original research identity changed")
    _require(identity.get("dependencies") == frozen._dependency_hashes(), "Frozen research dependencies changed")
    _require(identity.get("max_calls") == 3 and identity.get("max_tokens_each") == 6000
             and identity.get("use_research") is True and identity.get("round_index") == 0,
             "Only the original bounded first-round external Research is in scope")
    selection = _read(source_run / "research_selection.json")
    inputs = _read(source_run / "research_inputs.json")
    packets = inputs["actual_solver_packets"] + inputs["host_fixture_packets"]
    by_hash = {p["record_hash"]: p for p in packets}
    selected = selection["packet_hashes"]
    _require(len(selected) == 6 and len(set(selected)) == 6 and all(h in by_hash for h in selected),
             "The exact six original development packets are required")
    selected_packets = [by_hash[h] for h in selected]
    evidence = frozen.prepare_evidence(selected_packets)
    _require(selection.get("no_calibration_or_final_feedback") is True
             and selection["complete_views"] == evidence["views"], "Original complete selection mismatch")
    _require(_read(directory / "evidence_view.json") == evidence
             and identity["evidence_view_hash"] == evidence["record_hash"]
             and identity["packets_hash"] == digest(selected_packets), "Original evidence identity mismatch")
    rubric = core.initial_rubric()
    _require(identity["rubric_hash"] == rubric["rubric_hash"]
             and all(p["rubric_hash"] == rubric["rubric_hash"] for p in selected_packets),
             "Original Rubric provenance mismatch")
    trigger = frozen.legacy.research_trigger(selected_packets)
    _require(trigger["triggered"], "Original Research must have been authorized by development triggers")
    system, user = frozen._messages("plan", rubric, evidence, external=True)
    stage = _read(directory / "plan.json")
    receipt = stage["api_receipt"]
    request = receipt["request"]
    offline = SimpleNamespace(root=source_run / "api", model=request["model"], service=request["service"])
    frozen.legacy._verify_receipt(receipt, system, user, "v7_rubric_plan",
                                 f"{identity['key']}:{digest(identity)}:plan", offline)
    _require(receipt["ok"] is True and receipt.get("finish_reason") == "stop",
             "Original plan must be transport-successful and fully stopped, not truncated")
    _require(stage["stage"] == "plan" and stage["identity_hash"] == digest(identity)
             and stage["parsed"] is None and stage["schema_valid"] is False
             and stage["error"] == "invalid_stage_schema_or_evidence_attribution", "Not the eligible failed plan stage")
    try:
        frozen._plan(receipt["response"], True, evidence)
    except (ValueError, TypeError, KeyError):
        pass
    else:
        raise ValueError("The original plan is valid; a contract repair cannot resample it")
    errors = structure_errors(receipt["response"], evidence)
    proposal = _read(directory / "proposal.json")
    _require(proposal["identity"] == identity and proposal["status"] == "no_valid_fresh_proposal"
             and proposal["proposed_rubric"] is None and proposal["calls_used"] == 1
             and proposal["historical_fallback_used"] is False
             and proposal["stages"][0]["stage_hash"] == stage["record_hash"]
             and proposal["research"]["status"] == "not_attempted_invalid_plan",
             "Original terminal proposal does not match the one failed plan")
    _require(not any((directory / name).exists() for name in ("synthesis.json", "patch.json", "source_receipt.json")),
             "Original later stages unexpectedly exist")
    paths = [source_run / "research_inputs.json", source_run / "research_selection.json",
             *(directory / name for name in ("identity.json", "evidence_view.json", "plan.json", "proposal.json")),
             source_run / "api/calls" / f"{receipt['request_hash']}.json"]
    for path in paths:
        _require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink source evidence is not supported")
    return {"source_run": str(source_run), "source_manifest": {str(p.relative_to(source_run)): _sha(p) for p in paths},
            "source_identity": identity, "source_plan_hash": stage["record_hash"],
            "source_proposal_hash": proposal["record_hash"], "source_receipt": receipt,
            "evidence": evidence, "rubric": rubric, "original_system": system, "original_user": user,
            "structural_errors": errors, "trigger": trigger}


def _messages(stage, context, *, plan=None, findings=None, sources=()):
    if stage != "plan_repair":
        return frozen._messages(stage, context["rubric"], context["evidence"], external=True,
                                plan=plan, findings=findings, sources=sources)
    payload = json.loads(context["original_user"])
    payload["contract_repair_diagnostic"] = {
        "original_invalid_response": context["source_receipt"]["response"],
        "host_structural_errors": context["structural_errors"],
        "instruction": "One separate diagnostic contract repair, not a semantic-score retry. Organize two to four "
            "of your original competing hypotheses; supply your own required questions and official URLs. "
            "Use exact five-field objects from the existing evidence catalog. The host supplies no hypotheses, "
            "questions, URLs, diagnoses or reference choices. Do not invent execution evidence. "
            "Return the original schema only. This output never replaces or activates the original V7 result.",
    }
    user = frozen._encoded(payload)
    _require(len(user) <= frozen.MAX_PROMPT_CHARS, "Full repair context exceeds budget; no truncation authorized")
    return context["original_system"], user


def _output_root(repo, source_run, root):
    root = Path(root).absolute()
    _require(not any(p.is_symlink() for p in (root, *root.parents)), "Symlink output root is not supported")
    root = root.resolve()
    allowed = Path(repo).resolve() / "outputs/research_contract_repair"
    _require(root.is_relative_to(allowed) and root != allowed, "Use an isolated outputs/research_contract_repair/<run> directory")
    _require(not root.is_relative_to(source_run) and not Path(source_run).is_relative_to(root),
             "Diagnostic output may not overlap original frozen evidence")
    _reject_symlink_tree(root)
    return root


def run(repo, source_run, root, *, api_factory=None, original_run_stopped=False):
    """At most one repair + one synthesis + one patch; completed resume is offline.

    ``original_run_stopped`` is an operator attestation, not independent process
    verification. It is required before ANY new network operation. No activation,
    semantic evaluation, calibration or original-run result mutation is possible.
    """
    repo, source_run = Path(repo).resolve(), Path(source_run).resolve()
    root = _output_root(repo, source_run, root)
    context = inspect_source(repo, source_run)
    original = context["source_receipt"]["request"]
    identity = core.seal({"version": VERSION, "source_run": str(source_run),
        "source_manifest": context["source_manifest"], "source_plan_hash": context["source_plan_hash"],
        "source_request_hash": context["source_receipt"]["request_hash"],
        "source_receipt_hash": digest(context["source_receipt"]),
        "packet_hashes": context["evidence"]["packet_hashes"], "evidence_view_hash": context["evidence"]["record_hash"],
        "dependencies": _dependencies(),
        "model": original["model"], "service": original["service"], "max_calls": MAX_CALLS,
        "max_tokens_each": MAX_TOKENS, "diagnostic_only": True, "no_activation": True,
        "original_result_replacement": False, "historical_fallback_available": False,
        "operator_attestation_scope": "original_run_stopped_not_independently_verified"})
    completed = (root / "result.json").exists()
    if not completed:
        _require(original_run_stopped is True, "Explicit operator attestation original_run_stopped required")
    else:
        _read(root / "result.json")
    metadata = {"identity.json": identity, "evidence_view.json": context["evidence"],
                "structural_feedback.json": core.seal({"source_plan_hash": context["source_plan_hash"],
                    "errors": context["structural_errors"], "semantic_feedback_supplied": False})}
    for name, value in metadata.items():
        _persist_or_verify(root / name, value, completed=completed)
    offline = SimpleNamespace(root=root / "api", model=identity["model"], service=identity["service"])
    stages, sources, plan, findings, patch = [], [], None, None, None
    status, api = "not_attempted", None
    with ExitStack() as stack:
        def call(name, parser):
            nonlocal api
            system, user = _messages(name, context, plan=plan, findings=findings, sources=sources)
            kind, key = "research_contract_diagnostic_" + name, f"{identity['record_hash']}:{name}"
            request = {"model": offline.model, "service": offline.service, "system": system, "user": user,
                       "kind": kind, "key": key, "max_tokens": MAX_TOKENS, "repeat": 0}
            request_hash = digest(request)
            path, cache = root / f"{name}.json", offline.root / "calls" / f"{request_hash}.json"
            intent = root / "call_intents" / f"{request_hash}.json"
            if path.exists():
                receipt = _read(path)["api_receipt"]
            elif cache.exists():
                _require(not completed and intent.exists(), "Unexpected cache without diagnostic intent")
                receipt = json.loads(cache.read_text())
            else:
                _require(not completed, "Completed diagnostic stage/cache missing; offline resume cannot repair it")
                _require(not intent.exists(), "Unresolved diagnostic call; do not silently repeat a request")
                if api is None:
                    api = stack.enter_context((api_factory or make_budgeted_api)(repo, offline.root, max_calls=3, workers=4))
                    _require(api.model == offline.model and api.service == offline.service
                             and Path(api.root).resolve() == offline.root.resolve(), "Diagnostic API identity changed")
                write_immutable_json(intent, core.seal({"identity_hash": identity["record_hash"], "request_hash": request_hash}))
                receipt = api.call(system, user, kind=kind, key=key, max_tokens=MAX_TOKENS)
            frozen.legacy._verify_receipt(receipt, system, user, kind, key, offline)
            _require(intent.exists() and _read(intent) == core.seal({"identity_hash": identity["record_hash"],
                     "request_hash": request_hash}), "Missing or changed diagnostic intent")
            parsed, error = None, None
            if receipt["ok"] and receipt.get("finish_reason") == "stop":
                try:
                    parsed = parser(receipt["response"])
                except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                    error = "invalid_stage_schema_or_evidence_attribution"
            else:
                error = "terminal_api_or_output_completion_failure"
            stage = core.seal({"stage": name, "identity_hash": identity["record_hash"], "api_receipt": receipt,
                               "parsed": parsed, "schema_valid": parsed is not None, "error": error})
            _persist_or_verify(path, stage, completed=completed)
            stages.append({"stage": name, "stage_hash": stage["record_hash"], "request_hash": request_hash,
                           "receipt_hash": digest(receipt), "schema_valid": parsed is not None, "error": error})
            return parsed

        plan = call("plan_repair", lambda raw: frozen._plan(raw, True, context["evidence"]))
        if plan is not None:
            source_path = root / "source_receipt.json"
            if source_path.exists():
                source_record = _read(source_path)
            else:
                _require(not completed, "Completed diagnostic source receipt missing; no network repair")
                try:
                    sources = frozen.fetch_sources(plan["urls"], root / "research_sources")
                    status = "complete" if sources and all(s.get("ok") for s in sources) else "partial_or_failed"
                except (OSError, ValueError):
                    sources, status = [], "trusted_transport_unavailable"
                source_record = core.seal({"identity_hash": identity["record_hash"], "sources": sources, "status": status})
                write_immutable_json(source_path, source_record)
            _require(source_record["identity_hash"] == identity["record_hash"], "Source receipt identity mismatch")
            sources, status = source_record["sources"], source_record["status"]
            _require(not sources or [s.get("requested_url") for s in sources] == plan["urls"], "Research URLs mismatch")
            frozen.legacy._verify_sources(sources, root)
            findings = call("synthesis", lambda raw: frozen._findings(raw, sources, context["evidence"]))
            if findings is not None and findings["findings"]:
                patch = call("patch", lambda raw: frozen._patch(raw, context["rubric"], findings))
        else:
            status = "not_attempted_invalid_repaired_plan"
    expected = {s["request_hash"] for s in stages}
    for directory in (root / "call_intents", offline.root / "calls"):
        _require({p.stem for p in directory.glob("*.json")} == expected, "Unexpected or unresolved diagnostic requests")
    reservations = offline.root / "budget_reservations"
    if reservations.exists():
        _require({p.stem for p in reservations.glob("*.json")} == expected, "Unresolved API budget reservations")
    _require({p.name for p in root.glob("*.json") if p.stem in {"plan_repair", "synthesis", "patch"}}
             == {s["stage"] + ".json" for s in stages}, "Unexpected diagnostic later stages")
    receipts = [json.loads((offline.root / "calls" / f"{s['request_hash']}.json").read_text()) for s in stages]
    ledger = {"logical_calls": len(receipts), "max_logical_calls": MAX_CALLS,
        "successful_calls": sum(r["ok"] for r in receipts), "terminal_errors": sum(not r["ok"] for r in receipts),
        "http_attempts": sum(r.get("http_attempt_count", 0) for r in receipts),
        "returned_models": dict(Counter(r.get("returned_model") or "unreported" for r in receipts)),
        "usage": {k: sum(r.get("usage", {}).get(k, 0) or 0 for r in receipts)
                  for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "usage_not_invoice": True, "unresolved_requests": []}
    revision = None if patch is None else {"changes": [{k: c[k] for k in ("check_id", "search", "when", "limits")}
        for c in patch["changes"]], "rationale": patch["rationale"], "source_refs": patch["source_refs"]}
    proposed = core.apply_rubric_patch(context["rubric"], revision) if revision else None
    result = core.seal({"version": VERSION, "identity_hash": identity["record_hash"],
        "status": "diagnostic_proposal_ready" if proposed else "diagnostic_no_valid_proposal",
        "diagnostic_only": True, "activation": "never", "original_result_replacement": False,
        "historical_fallback_used": False, "calls_used": len(stages), "max_calls": MAX_CALLS, "ledger": ledger,
        "stages": stages, "proposed_rubric": proposed, "revision_patch": revision, "revision_evidence": patch,
        "research": {"status": status, "plan": plan, "findings": findings, "sources": sources,
            "quotes": [{**q, "source_support": "verified_provenance_only", "semantic_support": "pending"}
                       for f in (findings or {}).get("findings", []) for q in f["evidencequotes"]],
            "semantic_support": "pending", "free_text_claims_verified": False},
        "interpretation": "Contract-delivery diagnostic only; no calibration, Skill effect or cross-domain efficacy measured."})
    _persist_or_verify(root / "result.json", result, completed=completed)
    return result
