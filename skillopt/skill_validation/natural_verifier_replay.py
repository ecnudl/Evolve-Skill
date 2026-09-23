"""Explore verifier changes on frozen natural artifacts, without new solver calls.

The source panel has already been consumed. Calibration is diagnostic only and
cannot authorize feedback, Skill admission, or deployment. No final data enters
this replay. Existing calls, probes, execution isolation and metrics are reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import CachedAPI, digest

from .models import ArtifactRecord, require
from .natural_data import build_audit_files, load_tasks
from .checks import ExecutionCache, validate_callable
from .research import fixed_rubric
from .natural_metrics import DEFAULT_CONFIG, calibrate_policy
from .natural_documents import SSHDocumentFetcher
from .natural_policy import (ARMS, REVISED_INTERFACE, INDEXED_INTERFACE, _strict_decode,
                             normalize_json_envelope, probe_messages, propose_policy, resolve_probe_ids)
from .natural_study import ExecutorPool, _read, _write, probe_prediction
from .panel import checked_path
from .single_round import BoundedCalls
from .task_probes import execute_probes, parse_probes

VERSION = "frozen-natural-verifier-replay-v1"
PARTS = ("development", "verifier_calibration", "skill_confirmation")
CANDIDATE = "fixed_u0"  # A declared index, never chosen by verifier/score.


def load_frozen(repo, source):
    """Validate source identities; retain the original host audit in host rows."""
    source = checked_path(source)
    manifest = _read(source / "data_manifest.json")
    protocol = _read(source / "protocol.json")
    freeze = _read(source / "frozen_candidates.json")
    require(protocol["manifest_hash"] == manifest["record_hash"]
            and freeze["protocol_hash"] == protocol["record_hash"], "Source freeze mismatch")
    replay_executor = SimpleNamespace(identity=protocol["executor"])

    def audit_record(task_row, artifact, *, reference=False):
        code = None if reference else next((f.content for f in artifact.files if f.path == "solution.py"), None)
        files = build_audit_files(task_row, code, reference=reference) if reference or code is not None else {}
        request = {"task_hash": task_row["task"].content_hash,
                   "artifact_hash": None if reference else artifact.content_hash,
                   "files_hash": digest(files), "executor": protocol["executor"], "reference": reference}
        result = _read(source / "host_only/audits" / (digest(request) + ".json"))
        require(result["request"] == request, "Changed audit request")
        return result
    pool, records = {}, {}
    for part in PARTS:
        task_rows = load_tasks(repo, manifest, part)
        row_map = {r["task"].contract.original_task_id: r for r in task_rows}
        tasks = {r["task"].contract.original_task_id: r["task"] for r in task_rows}
        identities = {r["task_id"]: r for r in manifest["splits"][part]}
        allowed = ("no_skill", "current", CANDIDATE) if part == "skill_confirmation" else ("no_skill", "current")
        rows = [r for r in _read(source / "host_only" / (part + "_rows.json"))["rows"] if r["arm"] in allowed]
        expected = {(task, repeat, arm) for task in tasks for repeat in range(protocol["repeats"]) for arm in allowed}
        actual = {(r["task_id"], r["repeat"], r["arm"]) for r in rows}
        require(actual == expected and len(rows) == len(expected), "Incomplete/duplicate frozen panel")
        groups = defaultdict(list)
        for row in rows:
            require(row["partition"] == part and row["family_id"] == identities[row["task_id"]]["family_id"],
                    "Source task partition/family mismatch")
            task = tasks[row["task_id"]]
            artifact, report = None, None
            if row["artifact_hash"] is not None:
                raw = _read(source / "artifacts" / (row["artifact_hash"] + ".json"))
                artifact = ArtifactRecord.from_dict({k: v for k, v in raw.items() if k != "record_hash"})
                expected_condition = row["arm"] if row["arm"] != CANDIDATE else "candidate"
                skill = freeze["skills"][row["arm"]]
                require(artifact.content_hash == row["artifact_hash"] and artifact.task_hash == task.contract.content_hash
                        and artifact.repeat == row["repeat"] and artifact.condition == expected_condition
                        and artifact.skill_hash == hashlib.sha256(skill.encode()).hexdigest()
                        and artifact.source_ref == row["request_ref"], "Frozen artifact identity mismatch")
                require(artifact.provenance_kind == "model" and artifact.provenance_complete
                        and not artifact.historical_only, "Real complete model artifacts required")
                request_hash = artifact.source_ref.split(":", 1)[1]
                paths = [source / "api/calls" / (request_hash + ".json"),
                         source / "reused_solver_receipts/receipts" / (request_hash + ".json")]
                receipt_path = next((p for p in paths if p.exists()), None)
                require(receipt_path is not None, "Missing original model receipt")
                receipt = json.loads(checked_path(receipt_path).read_text())
                require(digest(receipt) == artifact.source_hash and receipt["request_hash"] == request_hash,
                        "Changed original model receipt")
                public_cache = ExecutionCache(replay_executor, source / "public_execution" / artifact.content_hash,
                                              max_executions=192, read_only=True)
                report = validate_callable(row_map[row["task_id"]]["public_task"], artifact, fixed_rubric(), public_cache)
                require(not public_cache.missing_records and report == _read(source / "public_reports" / (report["record_hash"] + ".json")),
                        "Public execution replay differs from source report")
                require(report["task_hash"] == artifact.task_hash and report["status"] == row["public_status"],
                        "Public report differs from artifact/row")
                audit = audit_record(row_map[row["task_id"]], artifact)
                reference = audit_record(row_map[row["task_id"]], artifact, reference=True)
                require(audit["record_hash"] == row["audit_hash"] and reference["record_hash"] == row["reference_hash"],
                        "Audit receipt differs from frozen source row")
                require(audit["request"]["artifact_hash"] == artifact.content_hash
                        and audit["request"]["task_hash"] == task.content_hash
                        and reference["request"]["reference"] is True
                        and reference["request"]["task_hash"] == task.content_hash,
                        "Host audit binding mismatch")
                require(row["status"] == (audit["status"] if reference["status"] == "pass" else "unknown"),
                        "Host audit label mismatch")
            else:
                require(row["status"] == row["public_status"] == "unknown"
                        and row["availability"] == "not_run_public_contract_or_adapter_incompatible",
                        "Missing source artifact cannot be silently dropped")
            groups[task.contract.content_hash].append({"task": task, "artifact": artifact, "report": report, "host": row})
        pool[part], records[part] = dict(groups), rows
    return manifest, protocol, freeze, pool, records


def compact_development(groups, *, limit=8):
    """Whitelist projection: only development gets an attributed H category."""
    cases = []
    for task_hash in sorted(groups)[:limit]:
        group = groups[task_hash]
        require(all(p["task"].contract.partition == "development" for p in group), "Development only")
        programs = []
        for position in group:
            artifact = position["artifact"]
            if position["host"]["repeat"] != 0:
                continue
            public, audit = position["host"]["public_status"], position["host"]["status"]
            gap = ("uncertain" if "unknown" in (public, audit) else
                   "missed_error" if public == "pass" and audit == "fail" else
                   "false_rejection" if public == "fail" and audit == "pass" else "no_observed_gap")
            programs.append({"code": next((f.content for f in artifact.files if f.path == "solution.py"), "")
                             if artifact else "", "public_check_status": public,
                             "code_origin": "submitted_artifact", "status_origin": "recorded_public_execution",
                             "development_gap": {"category": gap, "information_origin": "development_audit_summary"}})
        programs.sort(key=lambda p: digest(p["code"]))
        cases.append({"task": group[0]["task"].contract.prompt, "task_origin": "public_contract",
                      "anonymous_implementations": programs})
    return {"cases": cases, "selection": "first eight ascending task hash; first repeat; no outcome filtering",
            "gap_origin": "development_audit_summary_not_research_discovery",
            "limits": "H categories are imperfect host diagnostics. No H inputs, answers, reference code, or task identities supplied."}


def direction(before, after):
    if "unknown" in (before, after):
        return "unknown"
    return ("shared_correct" if before == after == "pass" else "shared_error" if before == after else
            "repair" if after == "pass" else "regression")


def describe(rows):
    errors = [r for r in rows if r["audit_status"] == "fail"]
    correct = [r for r in rows if r["audit_status"] == "pass"]
    metrics = {"positions": len(rows), "tasks": len({r["task_id"] for r in rows}),
               "families": len({r["family_id"] for r in rows}),
               "audit_unknown": sum(r["audit_status"] == "unknown" for r in rows),
               "errors": len(errors), "correct": len(correct)}
    for field in ("fixed_status", "new_status"):
        metrics[field] = {"statuses": dict(Counter(r[field] for r in rows)),
                          "detected_errors": sum(r[field] == "fail" for r in errors),
                          "false_rejections": sum(r[field] == "fail" for r in correct)}
    new_errors = [r for r in errors if r["fixed_status"] != "fail" and r["new_status"] == "fail"]
    metrics["new_detection"] = len(new_errors)
    metrics["new_detection_families"] = len({r["family_id"] for r in new_errors})
    missed = [r for r in errors if r["fixed_status"] != "fail"]
    metrics["fixed_missed_subset"] = {"size": len(missed), "full_panel_size": len(rows),
                                       "new_detected": len(new_errors)}
    proposals = {r["task_id"]: (r.get("proposal_status", "not_recorded"), r.get("probe_count", 0)) for r in rows}
    metrics["probe_proposals"] = {"task_statuses": dict(Counter(state for state, _ in proposals.values())),
                                  "tasks_with_checks": sum(count > 0 for _, count in proposals.values()),
                                  "tasks": len(proposals)}
    pairs = {}
    indexed = {(r["task_id"], r["repeat"], r["condition"]): r for r in rows}
    for target, baseline in (("current", "no_skill"), ("candidate", "no_skill"), ("candidate", "current")):
        table, fixed_table = Counter(), Counter()
        for (task, repeat, condition), row in indexed.items():
            other = indexed.get((task, repeat, baseline))
            if condition != target or other is None:
                continue
            h = direction(other["audit_status"], row["audit_status"])
            table[h + "/" + direction(other["new_status"], row["new_status"])] += 1
            fixed_table[h + "/" + direction(other["fixed_status"], row["fixed_status"])] += 1
        if table:
            pairs[target + "_vs_" + baseline] = {"audit_vs_verifier": dict(table), "audit_vs_fixed": dict(fixed_table)}
    metrics["paired_diagnostics"] = pairs
    return metrics


def run(repo, source, root, executor, *, workers=6, api_proxy=None, source_fetcher=None,
        interface_version=REVISED_INTERFACE):
    repo, source, root = checked_path(repo), checked_path(source), checked_path(root)
    require(root != source and root.is_relative_to(repo / "outputs/skill_validation"), "Separate replay output required")
    manifest, source_protocol, freeze, pool, source_rows = load_frozen(repo, source)
    view = compact_development(pool["development"])
    with CachedAPI(repo, root / "api", workers=workers, stream=True, reasoning_effort="low",
                   provider="bigmodel", proxy=api_proxy) as api:
        protocol = seal({"version": VERSION, "interface_version": interface_version,
            "source_root": str(source), "source_protocol_hash": source_protocol["record_hash"],
            "manifest_hash": manifest["record_hash"], "candidate_freeze_hash": freeze["record_hash"],
            "source_rows_hash": digest(source_rows), "development_view_hash": digest(view),
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")},
            "service": api.service, "executor": executor.identity, "transport": executor.transport_identity,
            "workers": workers, "max_logical_requests": 110, "max_output_tokens": 2048,
            "document_transport": source_fetcher.identity if source_fetcher else {"kind": "local_direct"},
            "candidate_selection": CANDIDATE, "max_probes_per_task": 2, "thresholds": DEFAULT_CONFIG,
            "evaluation_partitions": ["verifier_calibration", "skill_confirmation"],
            "previously_consumed_panel": True, "final_access": False, "deployment_authorized": False,
            "feedback_authorized": False, "same_panel_reanalysis_not_independent_confirmation": True})
        _write(root / "protocol.json", protocol)
        _write(root / "development_view.json", seal(view))
        _write(root / "host_only/source_rows.json", seal(source_rows))
        calls = BoundedCalls(api, root / "model_budget", protocol["record_hash"], protocol["max_logical_requests"])
        policies = {arm: propose_policy(arm, view, calls, root / "policies", interface_version=interface_version,
                                       source_fetcher=source_fetcher)
                    for arm in ARMS}
        _write(root / "frozen_policies.json", seal({"policies": policies}))
        print(json.dumps({"phase": "policies_frozen", "status": {a: p["status"] for a, p in policies.items()}}), flush=True)
        all_results, gates = {}, {}
        for arm in ARMS[1:]:
            policy = policies[arm]
            pipeline = digest({"policy": policy, "protocol": protocol["record_hash"]})
            arm_results = {}

            def one(group):
                task = group[0]["task"]
                path = root / "probes" / arm / (task.contract.content_hash + ".json")
                if path.exists():
                    proposed = _read(path)
                    require(proposed["pipeline_hash"] == pipeline, "Changed replay policy")
                else:
                    artifacts = tuple(p["artifact"] for p in group if p["artifact"] is not None)
                    state, reason, ref, raw = "abstained", "policy_did_not_update_or_no_artifacts", None, {"probes": []}
                    if policy["status"] == "update" and artifacts:
                        system, user = probe_messages(task, artifacts, policy)
                        receipt = calls.call(system, user, "natural-replay-probes-" + arm, max_tokens=2048)
                        ref = receipt["request_hash"]
                        try:
                            require(receipt["ok"], "Probe API failure")
                            raw = _strict_decode(normalize_json_envelope(receipt["response"]))
                            if interface_version == INDEXED_INTERFACE:
                                raw = resolve_probe_ids(raw, task)
                            parsed = parse_probes(raw, task)
                            state, reason = parsed["status"], "parsed_without_semantic_repair"
                        except (ValueError, TypeError, KeyError) as error:
                            raw, state, reason = {"probes": []}, "invalid", type(error).__name__ + ": " + str(error)[:200]
                    proposed = seal({"proposal": parse_probes(raw, task), "status": state, "reason": reason,
                                     "pipeline_hash": pipeline, "request_hash": ref})
                    _write(path, proposed)
                results = []
                for position in group:
                    row, artifact = position["host"], position["artifact"]
                    report = None
                    prediction = row["public_status"]
                    if artifact is not None and proposed["proposal"]["probes"]:
                        report = execute_probes(task, artifact, proposed["proposal"], executor, root / "probe_execution" / arm)
                        require(not executor.failed.is_set(), "Replay execution infrastructure failed")
                        prediction = probe_prediction(prediction, report)
                    results.append({"task_id": row["task_id"], "family_id": row["family_id"], "repeat": row["repeat"],
                        "condition": row["condition"], "audit_status": row["status"], "fixed_status": row["public_status"],
                        "new_status": prediction, "artifact_hash": row["artifact_hash"],
                        "audit_hash": row["audit_hash"], "report_hash": report["record_hash"] if report else proposed["record_hash"],
                        "partition": row["partition"], "proposal_status": proposed["status"],
                        "proposal_hash": proposed["record_hash"], "probe_count": len(proposed["proposal"]["probes"])})
                return results

            for part in protocol["evaluation_partitions"]:
                groups = [pool[part][k] for k in sorted(pool[part])]
                rows = []
                for start in range(0, len(groups), 6):
                    for result in api.parallel(groups[start:start + 6], one, "replay-" + arm):
                        rows.extend(result)
                    print(json.dumps({"phase": part, "arm": arm, "tasks": min(start + 6, len(groups)), "total": len(groups)}), flush=True)
                _write(root / "host_only" / (arm + "_" + part + ".json"), seal({"rows": rows}))
                arm_results[part] = describe(rows)
                if part == "verifier_calibration":
                    clean = [{k: v for k, v in r.items() if k not in {"proposal_status", "proposal_hash", "probe_count"}} for r in rows]
                    decision = calibrate_policy(clean, policy_hash=pipeline, protocol_hash=protocol["record_hash"],
                                                manifest_hash=manifest["record_hash"], config=DEFAULT_CONFIG)
                    # This consumed panel can diagnose a threshold, never grant authority.
                    gates[arm] = {"status": "pending", "reason": "previously_consumed_panel_requires_fresh_confirmation",
                                  "diagnostic_threshold_status": decision["status"],
                                  "diagnostic_reasons": decision["reasons"], "feedback_authorized": False,
                                  "deployment_authorized": False}
                    _write(root / "host_only" / (arm + "_diagnostic_gate.json"), seal({
                        "metrics": {k: decision[k] for k in ("counts", "fixed", "new", "new_detection_count", "false_rejection_increase")},
                        "gate": gates[arm]}))
            all_results[arm] = arm_results
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
            "source_manifest_hash": manifest["record_hash"], "policy_status": {a: p["status"] for a, p in policies.items()},
            "sources": {a: [{k: s[k] for k in ("source_id", "url", "status")} for s in p["sources"]] for a, p in policies.items()},
            "metrics": all_results, "verifier_gates": gates, "cost": calls.accounting(),
            "effect_claim": "exploratory_fixed_artifact_replay_on_previously_consumed_panel",
            "new_solver_calls": 0, "skill_update_calls": 0, "final_access": False,
            "deployment_authorized": False, "cross_domain_evidence": False})
        _write(root / "results.json", result)
        print(json.dumps({"phase": "completed", "cost": result["cost"], "gates": gates}), flush=True)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--execution-workers", type=int, default=4)
    parser.add_argument("--api-proxy")
    parser.add_argument("--interface-version", choices=[REVISED_INTERFACE, INDEXED_INTERFACE], default=REVISED_INTERFACE)
    args = parser.parse_args(argv)
    executor = ExecutorPool(args.remote_repo, args.execution_workers)
    try:
        run(args.repo, args.source, args.output, executor, workers=args.workers, api_proxy=args.api_proxy,
            source_fetcher=SSHDocumentFetcher(args.remote_repo), interface_version=args.interface_version)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
