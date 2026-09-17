"""One NEW patch-contract diagnostic after a completed failed plan-repair run.

Never reopens the original result, changes findings, fetches new sources, or
uses calibration/final evidence. Host feedback describes syntax/field structure
only; the model, not the host, must supply a valid patch. No activation occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from skillopt import research_contract_repair as previous
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import research as frozen
from skillopt.coevolution_v7.transport import make_budgeted_api
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v8-one-shot-patch-contract-diagnostic-v1"
MAX_TOKENS = 6000


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    return core.verify(json.loads(Path(path).read_text()))


def _dependencies():
    return {**previous._dependencies(), "skillopt/coevolution_v8/patch_diagnostic.py":
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def structural_feedback(raw):
    """Report the parser location and schema; never append braces or move fields."""
    _require(isinstance(raw, str) and 0 < len(raw) <= 60000, "Bounded actual patch response required")
    try:
        frozen.legacy._decode(raw)
    except json.JSONDecodeError as error:
        failure = {"kind": "json_syntax_error", "message": error.msg, "line": error.lineno,
                   "column": error.colno, "character_offset": error.pos}
    else:
        raise ValueError("This diagnostic is only for the observed syntactically invalid patch, not semantic resampling")
    return {"syntax_error": failure,
        "required_top_level_fields": ["changes", "rationale", "source_refs"],
        "allowed_change_fields": ["check_id", "search", "when", "limits", "finding_ids"],
        "structural_requirements": ["Each change object must close before its containing changes array closes.",
            "rationale is a required top-level field, not a field inside an individual change.",
            "One or two changes; each check_id occurs once; finding_ids must refer to existing same-check findings."],
        "host_repaired_response": False, "host_supplied_research_content": False}


def inspect_source(repo, source_diagnostic):
    root = Path(source_diagnostic).absolute()
    _require(not any(p.is_symlink() for p in (root, *root.parents)), "Symlink source diagnostic rejected")
    previous._reject_symlink_tree(root)
    _require((root / "result.json").is_file(), "Completed source diagnostic required; no continuation permitted")
    identity = _read(root / "identity.json")
    result = previous.run(repo, identity["source_run"], root)
    _require(result["status"] == "diagnostic_no_valid_proposal" and result["calls_used"] == 3
             and result["proposed_rubric"] is None and result["activation"] == "never"
             and [s["stage"] for s in result["stages"]] == ["plan_repair", "synthesis", "patch"]
             and [s["schema_valid"] for s in result["stages"]] == [True, True, False],
             "Only a completed source with valid plan/findings and one invalid patch is eligible")
    stage = _read(root / "patch.json")
    receipt = stage["api_receipt"]
    _require(receipt["ok"] is True and receipt.get("finish_reason") == "stop",
             "Source patch must be transport-successful with provider finish=stop, not length/transport failure")
    errors = structural_feedback(receipt["response"])
    evidence = _read(root / "evidence_view.json")
    _require(bool(result["research"]["findings"]["findings"]), "Validated source findings required")
    return {"source_diagnostic": str(root.resolve()), "source_identity": identity, "source_result": result,
            "source_patch": stage, "source_receipt": receipt, "evidence": evidence,
            "findings": result["research"]["findings"], "structural_feedback": errors}


def _messages(context):
    original = context["source_receipt"]["request"]
    payload = json.loads(original["user"])
    payload["patch_contract_diagnostic"] = {
        "original_invalid_response": context["source_receipt"]["response"],
        "host_structural_feedback": context["structural_feedback"],
        "instruction": "This is a separate one-call structural diagnostic, not a semantic-performance retry. "
            "Retain the intended existing proposal and its substantive limitations; make it conform to the "
            "original JSON schema. Use only the supplied unchanged findings/evidence. The host provides no "
            "replacement rationale, search text, hypotheses, citations, expected task answers or verdicts. "
            "Do not claim original failure was a success. Return only the original patch schema. "
            "No calibration or final feedback is available; valid output is still an unapproved proposal.",
    }
    user = frozen._encoded(payload)
    _require(len(user) <= frozen.MAX_PROMPT_CHARS, "Complete original patch context exceeds the bound; no truncation")
    return original["system"], user


def _root(repo, source, root):
    root = Path(root).absolute()
    _require(not any(p.is_symlink() for p in (root, *root.parents)), "Symlink output rejected")
    allowed = Path(repo).resolve() / "outputs/research_patch_diagnostic"
    root = root.resolve()
    _require(root.is_relative_to(allowed) and root != allowed and not root.is_relative_to(source)
             and not Path(source).is_relative_to(root), "Use a distinct outputs/research_patch_diagnostic/<run> directory")
    previous._reject_symlink_tree(root)
    return root


def run(repo, source_diagnostic, root, *, api_factory=None, source_run_stopped=False):
    """At most one new 6000-token patch call; completed resume is strictly offline."""
    repo, source = Path(repo).resolve(), Path(source_diagnostic).resolve()
    root = _root(repo, source, root)
    context = inspect_source(repo, source)
    original = context["source_receipt"]["request"]
    identity = core.seal({"version": VERSION, "source_diagnostic": str(source),
        "source_diagnostic_result_hash": context["source_result"]["record_hash"],
        "source_identity_hash": context["source_identity"]["record_hash"],
        "source_patch_hash": context["source_patch"]["record_hash"],
        "source_patch_request_hash": context["source_receipt"]["request_hash"],
        "source_patch_receipt_hash": digest(context["source_receipt"]),
        "source_run": context["source_identity"]["source_run"],
        "evidence_view_hash": context["evidence"]["record_hash"], "findings_hash": digest(context["findings"]),
        "model": original["model"], "service": original["service"], "max_calls": 1, "max_tokens_each": MAX_TOKENS,
        "dependencies": _dependencies(), "diagnostic_only": True, "original_result_replacement": False,
        "activation": "never", "new_sources_or_changed_findings": False})
    completed = (root / "result.json").exists()
    _require(completed or source_run_stopped is True, "Explicit stopped-source operator attestation required before a new call")
    if completed:
        _read(root / "result.json")
    for name, value in (("identity.json", identity), ("evidence_view.json", context["evidence"]),
            ("structural_feedback.json", core.seal(context["structural_feedback"]))):
        previous._persist_or_verify(root / name, value, completed=completed)
    system, user = _messages(context)
    kind, key = "v8_patch_contract_diagnostic", identity["record_hash"] + ":patch_repair"
    request = {"model": original["model"], "service": original["service"], "system": system, "user": user,
               "kind": kind, "key": key, "max_tokens": MAX_TOKENS, "repeat": 0}
    h = digest(request)
    api_root = root / "api"
    cache, stage_path, intent = api_root / "calls" / (h + ".json"), root / "patch_repair.json", root / "call_intent.json"
    intent_value = core.seal({"identity_hash": identity["record_hash"], "request_hash": h})
    if stage_path.exists():
        receipt = _read(stage_path)["api_receipt"]
    elif cache.exists():
        _require(not completed and intent.is_file(), "Unexpected orphan cache or missing completed stage")
        receipt = json.loads(cache.read_text())
    else:
        _require(not completed and not intent.exists(), "Missing completed or unresolved request; do not silently retry")
        with (api_factory or make_budgeted_api)(repo, api_root, max_calls=1, workers=4) as api:
            _require(api.model == original["model"] and api.service == original["service"]
                     and Path(api.root).resolve() == api_root.resolve(), "New diagnostic API identity differs")
            write_immutable_json(intent, intent_value)
            receipt = api.call(system, user, kind=kind, key=key, max_tokens=MAX_TOKENS)
    _require(intent.is_file() and _read(intent) == intent_value, "Missing or inconsistent one-call intent")
    frozen.legacy._verify_receipt(receipt, system, user, kind, key,
                                 SimpleNamespace(root=api_root, model=original["model"], service=original["service"]))
    patch, error = None, None
    if receipt["ok"] and receipt.get("finish_reason") == "stop":
        try:
            patch = frozen._patch(receipt.get("response", ""), core.initial_rubric(), context["findings"])
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            error = "invalid_patch_schema_or_evidence_attribution"
    else:
        error = "terminal_api_or_output_completion_failure"
    stage = core.seal({"identity_hash": identity["record_hash"], "api_receipt": receipt,
                       "parsed": patch, "schema_valid": patch is not None, "error": error})
    previous._persist_or_verify(stage_path, stage, completed=completed)
    _require({p.stem for p in (api_root / "calls").glob("*.json")} == {h}, "Unexpected extra model calls")
    reservations = api_root / "budget_reservations"
    _require(not reservations.exists() or {p.stem for p in reservations.glob("*.json")} == {h}, "Unresolved extra reservations")
    revision = None if patch is None else {"changes": [{k: row[k] for k in ("check_id", "search", "when", "limits")}
        for row in patch["changes"]], "rationale": patch["rationale"], "source_refs": patch["source_refs"]}
    candidate = core.apply_rubric_patch(core.initial_rubric(), revision) if revision else None
    result = core.seal({"version": VERSION, "identity_hash": identity["record_hash"],
        "status": "diagnostic_proposal_ready" if candidate else "diagnostic_no_valid_proposal", "calls_used": 1,
        "max_calls": 1, "diagnostic_only": True, "activation": "never", "original_result_replacement": False,
        "historical_fallback_used": False, "proposed_rubric": candidate, "revision_patch": revision, "revision_evidence": patch,
        "source_chain": [{"kind": "original_v7_plan", "request_hash": context["source_identity"]["source_request_hash"]},
                         {"kind": "separate_plan_contract_diagnostic", "root": str(source),
                          "record_hash": context["source_result"]["record_hash"], "calls_used": 3}],
        "stages": [{"stage": "patch_repair", "stage_hash": stage["record_hash"], "request_hash": h,
                    "receipt_hash": digest(receipt), "schema_valid": patch is not None, "error": error}],
        "research": context["source_result"]["research"], "findings_unchanged": True,
        "new_document_fetches": 0, "source_calls_not_new_independent_evidence": True,
        "semantic_edit_preservation_verified": False, "no_calibration_or_final_feedback": True,
        "ledger": {"logical_calls": 1, "source_diagnostic_calls": 3, "original_v7_plan_calls": 1,
                   "http_attempts": receipt.get("http_attempt_count"), "usage": receipt.get("usage", {}),
                   "returned_model": receipt.get("returned_model") or "unreported", "usage_not_invoice": True}})
    previous._persist_or_verify(root / "result.json", result, completed=completed)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "run"), nargs="?", default="inspect")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--source-diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-run-stopped", action="store_true")
    args = parser.parse_args()
    if args.action == "inspect":
        context = inspect_source(args.repo, args.source_diagnostic)
        result = {"status": "eligible_not_run", "source_patch_hash": context["source_patch"]["record_hash"],
                  "structural_feedback": context["structural_feedback"], "new_api_calls": 0}
    else:
        if args.output is None:
            parser.error("run requires an isolated --output")
        record = run(args.repo, args.source_diagnostic, args.output, source_run_stopped=args.source_run_stopped)
        result = {k: record[k] for k in ("status", "calls_used", "activation", "record_hash")}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
