"""Offline bridge from a repaired Research proposal to independent calibration.

No function sends model requests or executes candidate/reference code. The
caller executes the frozen jobs with the existing sandboxed Coding adapter.
Only receipt-grounded, equal-budget calibration can authorize next-round
DEVELOPMENT feedback. This does not approve a Skill or claim cross-domain safety.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path

from skillopt import research_contract_repair
from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v5 import core, evaluation, governance
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v6 import statistics
from skillopt.coevolution_v7.experiment import validator_activation
from skillopt.coevolution_v8 import patch_diagnostic
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v8-independent-research-calibration-bridge-v1"
CHANNELS = ("old_a", "old_b", "new")
POLICIES = {"old_single": ("old_a",), "new_single": ("new",),
            "old_double": ("old_a", "old_b"), "portfolio": ("old_a", "new")}
UNAVAILABLE = {"delivery", "transport", "infrastructure", "format", "schema", "transport_unavailable",
               "infrastructure_or_resource_failure", "reference_dispute_or_unavailable",
               "probe_reference_dispute_or_execution_unknown", "target_unavailable"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    return core.verify(json.loads(Path(path).read_text()))


def _dependencies():
    files = [Path(__file__), *(Path(module.__file__) for module in
                              (research_contract_repair, patch_diagnostic, core, evaluation, governance, statistics))]
    files.extend([Path(executor.__file__), Path(__file__).parents[1] / "coevolution_v7/experiment.py",
                  Path(__file__).parents[1] / "coevolution_v5/adapters.py"])
    return {str(p.relative_to(Path(__file__).parents[2])): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def _safe_root(root):
    path = Path(root).absolute()
    _require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink registry path rejected")
    research_contract_repair._reject_symlink_tree(path)
    return path.resolve()


def load_proposal(repo, diagnostic_root):
    """Read and re-validate a COMPLETED diagnostic, never repair missing output.

    The diagnostic's own completed-resume path verifies all prompts, receipts,
    source snapshots and frozen development views without writes or API clients.
    No final/calibration result is read. Local hashes are not host authentication.
    """
    repo, diagnostic_root = Path(repo).resolve(), _safe_root(diagnostic_root)
    _require((diagnostic_root / "result.json").is_file(), "A completed isolated diagnostic is required")
    identity = _read(diagnostic_root / "identity.json")
    if identity.get("version") == research_contract_repair.VERSION:
        result = research_contract_repair.run(repo, identity["source_run"], diagnostic_root)
        source_type = "completed_plan_contract_diagnostic"
    elif identity.get("version") == patch_diagnostic.VERSION:
        result = patch_diagnostic.run(repo, identity["source_diagnostic"], diagnostic_root)
        source_type = "completed_separate_patch_diagnostic_with_verified_failed_predecessor"
    else:
        raise ValueError("Unknown Research diagnostic source type")
    _require(result["diagnostic_only"] is True and result["activation"] == "never"
             and result["original_result_replacement"] is False and result["historical_fallback_used"] is False,
             "Only a fresh, isolated, nonactivated diagnostic may enter this bridge")
    evidence = _read(diagnostic_root / "evidence_view.json")
    hashes, clusters, tasks = set(), set(), set()
    for view in evidence["views"]:
        core.verify(view)
        tasks.add(view["task_id"])
        clusters.add(view["cluster_id"])
        for field in ("initial_task_fixture", "evaluated_artifact"):
            record = view[field]
            if record["available"]:
                hashes.add(digest(record["artifact"]))
        hashes.update(view["supplied_solver_artifact_registry"])
    candidate = result["proposed_rubric"]
    old = core.initial_rubric()
    if candidate is not None:
        core.validate_rubric(candidate)
        _require(core.apply_rubric_patch(old, result["revision_patch"]) == candidate,
                 "Diagnostic Rubric does not derive from its verified patch")
        _require(all(before == after for before, after in zip(old["checks"], candidate["checks"])
                     if before["id"] not in {"coding_contract", "coding_probe"}), "Coding bridge cannot import QA changes")
    return core.seal({"version": VERSION, "repo": str(repo), "diagnostic_root": str(diagnostic_root), "source_type": source_type,
        "diagnostic_result_hash": result["record_hash"], "diagnostic_identity_hash": identity["record_hash"],
        "evidence_view_hash": evidence["record_hash"], "development_task_ids": sorted(tasks),
        "development_cluster_ids": sorted(clusters), "development_artifact_hashes": sorted(hashes),
        "old_rubric": old, "candidate_rubric": candidate, "model": identity["model"], "service": identity["service"],
        "proposal_only": True, "semantic_claims_verified": False, "source_support_not_semantic_truth": True})


def _controls(adapters):
    _require(isinstance(adapters, (list, tuple)) and bool(adapters), "Independent Coding calibration adapters required")
    tasks, artifacts = {}, []
    for adapter in adapters:
        _require(isinstance(adapter, CodingAdapter) and adapter.task.split in {"calibration", "promotion"},
                 "No development, final, QA or relabeled assessment inputs may enter calibration")
        task = adapter.task
        _require(task.id not in tasks, "Duplicate calibration task ID")
        tasks[task.id] = task.to_dict()
        variants = task.metadata["controls"]
        for name, files, truth in (("reference", task.reference_files, "good"),
                ("equivalent", variants["equivalent"], "good"),
                ("semantic_mutant", variants["semantic_mutant"], "bad"),
                ("preservation_mutant", variants["preservation_mutant"], "bad")):
            evaluation._validate_files(task, files)
            artifacts.append({"artifact_id": task.id + ":" + name, "artifact_hash": digest(files), "files": deepcopy(files),
                              "task_id": task.id, "cluster_id": task.cluster_id, "truth": truth})
    governance._artifacts({"artifacts": artifacts})
    return tasks, artifacts


def _unavailable(details):
    if isinstance(details, dict):
        # Task inputs/outputs and exception messages are DATA, not host status.
        return any((k in {"reason", "category", "error_category"} and isinstance(v, str) and v in UNAVAILABLE)
                   or _unavailable(v) for k, v in details.items()
                   if k not in {"input", "value", "expected", "message"}
                   and not (k == "actual" and (not isinstance(v, dict) or type(v.get("ok")) is not bool)))
    return isinstance(details, list) and any(_unavailable(v) for v in details)


def _preflight(value, artifacts, rubric):
    core.verify(value)
    _require(value.get("never_model_feedback") is True and isinstance(value.get("calibration"), list),
             "Private independent host preflight required, never model-generated truth")
    rows = {r["artifact_id"]: r["assessment"] for r in value["calibration"]}
    _require(len(rows) == len(value["calibration"]) == len(artifacts)
             and set(rows) == {a["artifact_id"] for a in artifacts}, "Complete private oracle preflight grid required")
    for artifact in artifacts:
        row = core.verify(rows[artifact["artifact_id"]], "receipt_hash")
        _require(row["task_id"] == artifact["task_id"] and row["artifact_hash"] == artifact["artifact_hash"]
                 and row["rubric_hash"] == rubric["rubric_hash"] and row["phase"] == "promotion"
                 and row["domain"] == "coding" and row["check_id"] == "coding_contract"
                 and row["evidence_kind"] == "execution" and row["verified"] is True and row["gate_eligible"] is True
                 and row["status"] == ("pass" if artifact["truth"] == "good" else "fail")
                 and row["details"].get("task_split") in {"promotion", "calibration"}
                 and row["details"].get("requested_phase") == "promotion"
                 and row["details"].get("public_only") is False and not _unavailable(row["details"]),
                 "Private calibration truth unavailable, wrongly attributed, or from a different task/Rubric/split")


def prepare_screen(repo, diagnostic_root, adapters, private_preflight, registry_root, *, screen_id, round_index, blocks=4):
    """Reserve one independent shard before judgments; no model/native execution.

    Reusing an identical reservation is resume; any new candidate/screen using
    an already reserved cluster or artifact fails. The caller must keep one
    canonical registry across rounds; independence labels are host declarations.
    """
    proposal = load_proposal(repo, diagnostic_root)
    root = _safe_root(registry_root)
    _require(type(round_index) is int and round_index >= 0 and type(blocks) is int and 1 <= blocks <= 16,
             "Explicit bounded round and repeated-block design required")
    if proposal["candidate_rubric"] is None:
        return core.seal({"version": VERSION, "status": "no_valid_candidate_keep_old", "proposal": proposal,
                          "active_rubric": proposal["old_rubric"], "jobs": [], "activate_next_round": False})
    allowed = Path(repo).resolve() / "outputs/coevolution_v8"
    _require(root.is_relative_to(allowed) and root != allowed, "Use a new isolated outputs/coevolution_v8 registry")
    tasks, artifacts = _controls(adapters)
    _require(not set(tasks).intersection(proposal["development_task_ids"]), "Calibration task overlaps Research development")
    _preflight(private_preflight, artifacts, proposal["old_rubric"])
    manifest = {"phase": "promotion", "artifacts": artifacts, "repeats": list(range(blocks)),
                "current_rubric_hash": proposal["old_rubric"]["rubric_hash"]}
    registry = governance.CalibrationRegistry(root)
    reservation = registry.reserve(screen_id, manifest, proposal["development_cluster_ids"],
        proposal["development_artifact_hashes"], [], proposal["candidate_rubric"]["rubric_hash"], round_index)
    jobs = [{"artifact_id": a["artifact_id"], "block": b, "channel": c}
            for a in artifacts for b in range(blocks) for c in CHANNELS]
    random.Random(20260913).shuffle(jobs)
    screen = core.seal({"version": VERSION, "status": "reserved_not_activated", "registry_root": str(root),
        "screen_id": screen_id, "round_index": round_index, "proposal": proposal, "tasks": tasks,
        "manifest": manifest, "private_preflight_hash": private_preflight["record_hash"], "reservation": reservation,
        "jobs": jobs, "dependencies": _dependencies(), "max_calls": len(jobs), "max_tokens_each": evaluation.PROBE_TOKENS,
        "comparison": "shared_old_a_plus_old_b_vs_shared_old_a_plus_new", "next_round_only": True,
        "private_labels_never_model_feedback": True, "final_results_read": False,
        "independence_verified_against": "research_development_ids_clusters_content_and_this_one_use_registry",
        "independence_of_host_cluster_labels_is_assumed": True})
    write_immutable_json(root / screen_id / "v8_private_preflight.json", private_preflight)
    write_immutable_json(root / screen_id / "v8_screen.json", screen)
    return screen


def _verify_screen(screen):
    core.verify(screen)
    _require(screen.get("version") == VERSION and screen.get("status") == "reserved_not_activated",
             "A reserved V8 calibration screen is required")
    root = _safe_root(screen["registry_root"])
    registry = governance.CalibrationRegistry(root)
    path = registry._path(screen["screen_id"], "v8_screen.json")
    _require(_read(path) == screen and screen["dependencies"] == _dependencies(), "Frozen calibration screen changed")
    proposal = load_proposal(screen["proposal"]["repo"], screen["proposal"]["diagnostic_root"])
    _require(proposal == screen["proposal"], "Imported Research provenance changed after reservation")
    reservation = json.loads(registry._path(screen["screen_id"], "reservation.json").read_text())
    governance._verify(reservation, "reservation_hash")
    _require(reservation == screen["reservation"], "Independent shard reservation changed")
    _require(json.loads(registry._path(screen["screen_id"], "private_manifest.json").read_text()) == screen["manifest"],
             "Private calibration manifest changed")
    preflight = _read(registry._path(screen["screen_id"], "v8_private_preflight.json"))
    _require(preflight["record_hash"] == screen["private_preflight_hash"], "Private preflight changed")
    _preflight(preflight, screen["manifest"]["artifacts"], proposal["old_rubric"])
    return root / screen["screen_id"]


class _CapturedRequest(Exception):
    def __init__(self, request):
        self.request = request


class _RequestCapture:
    """Pure prompt capture: abort before any real API or receipt-file operation."""
    def __init__(self, model, service):
        self.model, self.service = model, service

    def call(self, system, user, *, kind, key, max_tokens, repeat=0):
        raise _CapturedRequest({"model": self.model, "service": self.service, "system": system, "user": user,
                                "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat})


def _job_parts(screen, job):
    _require(isinstance(job, dict) and set(job) == {"artifact_id", "block", "channel"}
             and job in screen["jobs"], "Job must be one of the complete predeclared calibration positions")
    artifact = next(a for a in screen["manifest"]["artifacts"] if a["artifact_id"] == job["artifact_id"])
    adapter = CodingAdapter(executor.RepoTask.from_dict(screen["tasks"][artifact["task_id"]]))
    rubric = screen["proposal"]["candidate_rubric" if job["channel"] == "new" else "old_rubric"]
    key = digest({"screen_hash": screen["record_hash"], "job": job})
    return adapter, artifact, rubric, key


def request_for_job(screen, job):
    """Return the exact old public-only probe request; never send it.

    The opaque request identity binds the private job without putting its truth,
    variant name, reference implementation, or hidden tests into the prompt.
    """
    core.verify(screen)
    adapter, artifact, rubric, key = _job_parts(screen, job)
    capture = _RequestCapture(screen["proposal"]["model"], screen["proposal"]["service"])
    try:
        evaluation.probe(capture, adapter, artifact["files"], rubric, key=key, repeat=job["block"])
    except _CapturedRequest as result:
        return result.request
    raise ValueError("Preflighted calibration artifact unexpectedly has no legal probe request")


def _probe_result(screen, component, receipt):
    job, search = component["job"], component["search"]
    core.verify(search)
    adapter, artifact, rubric, key = _job_parts(screen, job)
    request = request_for_job(screen, job)
    expected_identity = {"version": evaluation.VERSION, "task_hash": digest(adapter.public_task()),
        "artifact_hash": artifact["artifact_hash"], "rubric_hash": rubric["rubric_hash"], "key": key, "repeat": job["block"]}
    _require(search["identity"] == expected_identity and receipt["request"] == request
             and search["request_hash"] == receipt["request_hash"] == digest(request)
             and search["api_receipt_hash"] == digest(receipt) and type(receipt["ok"]) is bool,
             "Probe/API receipt does not match the frozen public-only job or Rubric")
    _require(search["model_calls"] == 1 and all(search.get(k) == receipt.get(k, {} if k == "usage" else None)
             for k in ("http_attempt_count", "usage", "finish_reason"))
             and search["transport_ok"] == receipt["ok"], "Probe execution metadata changed")
    inputs, error = [], None
    if not receipt["ok"]:
        error = "terminal_api_result"
    else:
        try:
            parsed = core.strict_object(receipt.get("response", ""))
            _require(set(parsed) == {"inputs"} and isinstance(parsed["inputs"], list) and 1 <= len(parsed["inputs"]) <= 4,
                     "Invalid probe schema")
            seen = set()
            for value in parsed["inputs"]:
                evaluation._bounded_input(value)
                _require(isinstance(value, dict) and adapter._input_valid(value) is True and digest(value) not in seen,
                         "Illegal/duplicate proposed probe")
                seen.add(digest(value))
            inputs = parsed["inputs"]
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            error = "invalid_probe_schema_or_input"
    _require(search["inputs"] == inputs and search["error"] == error and search["schema_valid"] == (error is None),
             "Proposed probe inputs were altered after the actual model response")
    return artifact, rubric, inputs


def _execution_outcome(component, artifact, rubric, inputs):
    outcome = governance._promotion_assessments(component, artifact, rubric["rubric_hash"])
    unknown = []
    for row in component["assessments"]:
        if row["check_id"] not in {"coding_contract", "coding_probe"}:
            _require(row["status"] == "not_applicable" and not row["verified"], "QA checks cannot decide Coding calibration")
            continue
        details = row["details"]
        hard = row["verified"] and row["gate_eligible"] and row["status"] in {"pass", "fail"}
        _require(not hard or not _unavailable(details), "Execution unavailability cannot masquerade as verified behavior")
        if not hard:
            unknown.append(details.get("reason", "missing_verified_execution"))
            continue
        if row["check_id"] == "coding_contract":
            cases = details.get("case_results")
            _require(details.get("public_only") is True and details.get("facts", {}).get("execution_ok") is True
                     and isinstance(cases, list) and bool(cases) and all(c.get("public") is True for c in cases)
                     and not details["facts"].get("private_diagnostics"), "Public contract checks cannot consume private truth")
            _require(all(type(c.get("passed")) is bool for c in cases)
                     and (row["status"] == "pass") == all(c["passed"] for c in cases),
                     "Contract outcome differs from sealed executed cases")
        else:
            receipts = details.get("receipts")
            _require(bool(inputs) and isinstance(receipts, list) and [r["input"] for r in receipts] == inputs,
                     "A probe verdict requires execution of those exact model-proposed inputs")
            for pair in receipts:
                ref, got = pair["reference"], pair["actual"]
                _require(ref.get("ok") is True and got.get("ok") is True and ref.get("input_unchanged") is True
                         and not ref.get("error_category") and not _unavailable(got),
                         "Unavailable/disputed reference or candidate execution cannot detect a semantic defect")
                passed = (got.get("input_unchanged") is True and got.get("exception") == ref.get("exception")
                          and executor.pilot._same(got.get("value"), ref.get("value")))
                _require(type(pair["passed"]) is bool and pair["passed"] == passed, "Differential verdict does not match recorded execution")
            _require((row["status"] == "pass") == all(p["passed"] for p in receipts), "Probe aggregate changed")
    return outcome, unknown


def _api_category(receipt, search):
    if receipt.get("finish_reason") == "length":
        return "output_budget_exhausted_not_semantic_defect"
    if not receipt["ok"]:
        return "transport_failure" if receipt.get("error_type") in {"http_status", "timeout", "transport_error"} else "response_failure"
    return "valid_input_proposal" if search["schema_valid"] else "invalid_probe_schema_or_input"


def assess_screen(screen, components, api_receipts):
    """Consume one complete actual calibration grid, never rerun missing cells.

    Components are sealed {job, search, assessments}; api_receipts maps hash to
    the persisted raw API records. A caller must obtain these from its immutable
    cache. Hash agreement does not authenticate a malicious or invented host.
    Raw calibration labels/inputs are stored privately; the returned decision
    contains only aggregate authority and hashes, not optimizer repair feedback.
    """
    directory = _verify_screen(screen)
    _require(isinstance(components, (list, tuple)) and isinstance(api_receipts, dict), "Explicit executed components and API receipts required")
    jobs = {digest(job): job for job in screen["jobs"]}
    indexed, outcomes, failures, api_kinds = {}, {}, [], Counter()
    for component in components:
        core.verify(component)
        _require(set(component) == {"job", "search", "assessments", "record_hash"}, "Unexpected calibration component fields")
        position = digest(component["job"])
        _require(position in jobs and position not in indexed, "Unknown or duplicate calibration position")
        h = component["search"].get("request_hash")
        _require(h in api_receipts, "Calibration component lacks its actual API receipt")
        receipt = api_receipts[h]
        artifact, rubric, inputs = _probe_result(screen, component, receipt)
        outcome, unknown = _execution_outcome(component, artifact, rubric, inputs)
        indexed[position], outcomes[position] = component, outcome
        api_kinds[_api_category(receipt, component["search"])] += 1
        failures.extend(unknown)
    request_hashes = [c["search"]["request_hash"] for c in components]
    _require(len(set(request_hashes)) == len(request_hashes) and set(api_receipts) == set(request_hashes),
             "Extra, reused or unresolved model receipts cannot be hidden in a calibration grid")
    rows, summary = [], None
    complete = set(indexed) == set(jobs)
    if complete:
        for artifact in screen["manifest"]["artifacts"]:
            for block in screen["manifest"]["repeats"]:
                for policy, channels in POLICIES.items():
                    keys = [digest({"artifact_id": artifact["artifact_id"], "block": block, "channel": c}) for c in channels]
                    parts = [indexed[k] for k in keys]
                    values = [outcomes[k] for k in keys]
                    union = "detected" if "detected" in values else "not_detected" if all(v == "not_detected" for v in values) else "unknown"
                    rows.append({k: artifact[k] for k in ("artifact_id", "artifact_hash", "task_id", "cluster_id", "truth")}
                        | {"block": block, "policy": policy, "outcome": union,
                           "input_count": len({digest(i) for p in parts for i in p["search"]["inputs"]}),
                           "probe_request_hashes": [p["search"]["request_hash"] for p in parts],
                           "component_hashes": [p["record_hash"] for p in parts], "public_only": True})
        summary = statistics.summarize_validator(rows, expected_artifacts={a["artifact_id"]: {
            "cluster_id": a["cluster_id"], "truth": a["truth"]} for a in screen["manifest"]["artifacts"]},
            expected_blocks=screen["manifest"]["repeats"])
    candidate = screen["proposal"]["candidate_rubric"]
    gate = validator_activation(summary, candidate)
    active = candidate if gate["activate_next_round"] else screen["proposal"]["old_rubric"]
    decision = core.seal({"version": VERSION, "screen_hash": screen["record_hash"],
        "diagnostic_result_hash": screen["proposal"]["diagnostic_result_hash"], "gate": gate,
        "activate_next_round": gate["activate_next_round"], "active_rubric": active,
        "active_from_round": screen["round_index"] + 1 if gate["activate_next_round"] else None,
        "old_retained": not gate["activate_next_round"], "complete_calibration_grid": complete,
        "expected_components": len(jobs), "observed_components": len(components),
        "api_diagnostic_counts": dict(api_kinds), "execution_unknown_counts": dict(Counter(failures)),
        "summary_hash": summary["summary_hash"] if summary else None,
        "deployment_approval": False, "scope": "next_round_development_feedback_only",
        "raw_calibration_labels_returned": False, "no_skill_or_cross_domain_efficacy_claim": True})
    evidence = core.seal({"screen_hash": screen["record_hash"], "components": list(components), "api_receipts": api_receipts,
                          "rows": rows, "summary": summary, "private_calibration_never_optimizer_feedback": True})
    registry = governance.CalibrationRegistry(screen["registry_root"])
    with registry._lock():
        write_immutable_json(directory / "v8_private_calibration.json", evidence)
        write_immutable_json(directory / "v8_decision.json", decision)
    return decision
