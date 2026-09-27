"""Pre-execution review replay on consumed, frozen natural artifacts.

Historical Research/no-Research generators are input strata, not a new causal
Research comparison. Both reviewers receive no documents. No Solver, Skill
update, final access, or feedback/deployment authorization is implemented.
"""
from __future__ import annotations

import argparse
import json
import threading
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import CachedAPI, digest

from .admissibility import execute_admitted, inventory, review_proposal
from .models import require
from .natural_policy import ARMS
from .natural_study import ExecutorPool, _read, _write, probe_prediction
from .natural_verifier_replay import describe, load_frozen
from .panel import checked_path
from .single_round import BoundedCalls
from .task_probes import _bindings, _check_execution, _observe
from .verifier_readiness import diagnose_readiness

VERSION = "pre-execution-admissibility-study-v1"
PARTS = ("verifier_calibration", "skill_confirmation")


def _position(row):
    return row["task_id"], row["repeat"], row["condition"]


def _report(task, artifact, proposal, report, source, arm, identity, read):
    """Read and reconstruct every original call receipt without executing/writing."""
    request = report["request"]
    require(request["task_hash"] == task.contract.content_hash
            and request["callable_task_hash"] == task.content_hash
            and request["artifact_record_hash"] == artifact.content_hash
            and request["proposal_hash"] == proposal["record_hash"]
            and request["pipeline_hash"] == proposal["pipeline_hash"]
            and request["executor_identity"] == identity, "Original execution request changed")
    require(report["task_hash"] == task.contract.content_hash and report["artifact_record_hash"] == artifact.content_hash
            and report["proposal_hash"] == proposal["record_hash"]
            and report["pipeline_hash"] == proposal["pipeline_hash"]
            and len(report["probes"]) == len(proposal["probes"]), "Original report identity changed")
    files, outcomes = {f.path: f.content for f in artifact.files}, []
    for index, (probe, row) in enumerate(zip(proposal["probes"], report["probes"])):
        observations, refs = [], []
        for call_index, call in enumerate(probe["calls"]):
            call_request = {**request, "probe_index": index, "call_index": call_index, "call": call}
            key = digest(call_request)
            base = source / "probe_execution" / arm
            terminal, intent = read(base / "calls" / (key + ".json")), read(base / "intents" / (key + ".json"))
            require(terminal["request"] == call_request and intent == seal({"request": call_request})
                    and type(terminal["execution_performed"]) is bool, "Original call/intent binding changed")
            execution = _check_execution(terminal["execution"], _bindings(task, files, call, identity))
            public, state, reason = _observe(execution, call)
            refs.append(terminal["record_hash"])
            observations.append({"call_index": call_index, "status": state, "reason": reason,
                "execution_performed": terminal["execution_performed"], "execution_ref": execution["record_hash"],
                "receipt_ref": terminal["record_hash"], "public_observation": public})
        status = "unknown"
        if all(o["status"] == "observed" for o in observations):
            expected = probe["expected"] if probe["kind"] == "expected" else observations[1]["public_observation"]["actual"]
            status = "match" if digest(observations[0]["public_observation"]["actual"]) == digest(expected) else "mismatch"
        require(row["probe_index"] == index and row["probe"] == probe and row["observations"] == observations
                and row["evidence_refs"] == refs and row["status"] == status, "Original observation reconstruction changed")
        outcomes.append(status)
    aggregate = "mismatch" if "mismatch" in outcomes else "unknown" if not outcomes or "unknown" in outcomes else "match"
    require(report["status"] == aggregate, "Original report aggregation changed")


def load_source(repo, source):
    """Complete structural/receipt validation precedes the first paid request."""
    bindings = {}
    def read(path):
        value = _read(path)
        bindings[str(path.relative_to(source))] = value["record_hash"]
        return value
    parent, protocol = read(source / "results.json"), read(source / "protocol.json")
    require(parent["protocol_hash"] == protocol["record_hash"] and parent["final_access"] is False
            and protocol["final_access"] is False and protocol["previously_consumed_panel"] is True,
            "Completed consumed no-final replay required")
    natural = checked_path(Path(protocol["source_root"]))
    manifest, old_protocol, freeze, pool, old_rows = load_frozen(repo, natural)
    require(protocol["manifest_hash"] == manifest["record_hash"]
            and protocol["source_protocol_hash"] == old_protocol["record_hash"]
            and protocol["candidate_freeze_hash"] == freeze["record_hash"]
            and protocol["source_rows_hash"] == digest(old_rows), "Original natural freeze mismatch")
    policies = read(source / "frozen_policies.json")["policies"]
    jobs, originals = [], {}
    for arm in ARMS[1:]:
        verify(policies[arm])
        require(policies[arm]["arm"] == arm, "Frozen generator arm changed")
        reports = {read(p)["record_hash"]: read(p) for p in sorted((source / "probe_execution" / arm / "reports").glob("*.json"))}
        originals[arm] = {}
        for part in PARTS:
            rows = read(source / "host_only" / (arm + "_" + part + ".json"))["rows"]
            indexed = {_position(r): r for r in rows}
            expected = {_position(p["host"]) for g in pool[part].values() for p in g}
            require(len(indexed) == len(rows) and set(indexed) == expected, "Missing/duplicate original positions")
            require(describe(rows) == parent["metrics"][arm][part], "Original summary differs from rows")
            originals[arm][part] = rows
            for key in sorted(pool[part]):
                group, selected = pool[part][key], []
                task = group[0]["task"]
                frozen = read(source / "probes" / arm / (task.contract.content_hash + ".json"))
                require(frozen["pipeline_hash"] == digest({"policy": policies[arm], "protocol": protocol["record_hash"]}),
                        "Original generator pipeline changed")
                proposal = frozen["proposal"]
                inventory(task, proposal)
                for position in group:
                    host, artifact = position["host"], position["artifact"]
                    row = indexed[_position(host)]
                    require(row["partition"] == part and row["family_id"] == host["family_id"]
                            and row["audit_status"] == host["status"] and row["audit_hash"] == host["audit_hash"]
                            and row["fixed_status"] == host["public_status"] and row["artifact_hash"] == host["artifact_hash"]
                            and row["proposal_hash"] == frozen["record_hash"]
                            and row["probe_count"] == len(proposal["probes"]), "Original host/proposal binding changed")
                    report = reports.get(row["report_hash"])
                    if artifact is not None and proposal["probes"]:
                        require(report is not None, "Missing original execution report")
                        _report(task, artifact, proposal, report, source, arm, protocol["executor"], read)
                        require(probe_prediction(row["fixed_status"], report) == row["new_status"], "Original prediction changed")
                    else:
                        require(report is None and row["report_hash"] == frozen["record_hash"]
                                and row["new_status"] == row["fixed_status"], "Unexpected absent-execution prediction")
                    selected.append((position, row))
                jobs.append({"arm": arm, "part": part, "task": task, "proposal": proposal, "positions": selected})
    return parent, protocol, natural, seal({"records": bindings}), jobs, originals


class _FailClosedExecutor:
    def __init__(self, executor):
        self.base, self.identity, self.failed = executor, executor.identity, threading.Event()

    def run(self, *args, **kwargs):
        require(not self.failed.is_set(), "Execution infrastructure already stopped")
        try:
            result = self.base.run(*args, **kwargs)
            require(result.get("status") == "observed" and result.get("cleanup_confirmed") is True,
                    "Execution infrastructure unavailable or cleanup unconfirmed")
            return result
        except Exception:
            self.failed.set()
            raise


def run(repo, source, root, executor, *, workers=6, api_proxy=None):
    repo, source, root = (checked_path(p).absolute() for p in (repo, source, root))
    require(type(workers) is int and 1 <= workers <= 6, "Bounded reviewer concurrency required")
    require(root.is_relative_to(repo / "outputs/skill_validation")
            and not root.is_relative_to(source) and not source.is_relative_to(root), "Separate non-overlapping study output required")
    parent, old_protocol, natural, bindings, jobs, originals = load_source(repo, source)
    require(not root.is_relative_to(natural) and not natural.is_relative_to(root), "Output overlaps original natural run")
    package = Path(__file__).resolve().parents[1]
    code = {str(p.relative_to(package.parent)): p.read_text() for p in sorted(package.rglob("*.py"))}
    snapshot = seal({"files": code})
    guarded = _FailClosedExecutor(executor)
    with CachedAPI(repo, root / "api", workers=workers, stream=True, reasoning_effort="low", provider="bigmodel", proxy=api_proxy) as api:
        protocol = seal({"version": VERSION, "source_root": str(source), "source_result_hash": parent["record_hash"],
            "source_protocol_hash": old_protocol["record_hash"], "input_manifest_hash": bindings["record_hash"],
            "source_snapshot_hash": snapshot["record_hash"], "service": api.service, "executor": executor.identity,
            "transport": executor.transport_identity, "workers": workers, "request_cap": 120, "output_token_cap": 2048,
            "selection": "all frozen probes from both historical generators; calibration and confirmation only",
            "review_sources": [], "gap_research": False, "consumed_panels": list(PARTS),
            "final_access": False, "new_solver_calls": 0, "skill_update_calls": 0,
            "feedback_authorized": False, "deployment_authorized": False})
        _write(root / "protocol.json", protocol)
        _write(root / "source_snapshot.json", snapshot)
        _write(root / "host_only/input_manifest.json", bindings)
        calls = BoundedCalls(api, root / "model_budget", protocol["record_hash"], 120)
        metrics, coverage, readiness = {}, {}, {}
        for arm in ARMS[1:]:
            metrics[arm], coverage[arm], readiness[arm] = {}, {}, {}
            pipeline = digest({"protocol": protocol["record_hash"], "historical_generator": arm})
            for part in PARTS:
                selected = [j for j in jobs if j["arm"] == arm and j["part"] == part]
                rows, reviews = [], []
                def review_job(job):
                    require(not guarded.failed.is_set(), "Execution failure blocks further paid phases")
                    return job, review_proposal(job["task"], job["proposal"], calls, root / "reviews" / arm,
                                                pipeline_hash=pipeline, sources=())
                def execute_job(item):
                    job, review = item
                    output = []
                    for position, old in job["positions"]:
                        artifact, admitted = position["artifact"], None
                        if artifact is not None:
                            admitted = execute_admitted(job["task"], artifact, job["proposal"], review, guarded,
                                root / "admitted_execution" / arm, pipeline_hash=pipeline)
                            report = admitted["execution_report"]
                            reasons = [o["reason"] for p in (report or {}).get("probes", []) for o in p["observations"]]
                            require(not guarded.failed.is_set() and not any(r.startswith("executor_exception_")
                                    or r == "interrupted_call_no_resampling" for r in reasons),
                                    "Execution infrastructure failed; stop paid phases, retain receipts")
                        report = admitted["execution_report"] if admitted else None
                        output.append({**old, "unreviewed_status": old["new_status"],
                            "new_status": probe_prediction(old["fixed_status"], report) if report else old["fixed_status"],
                            "review_hash": review["record_hash"], "review_status": review["status"],
                            "admitted_report_hash": admitted["record_hash"] if admitted else None,
                            "new_execution_report_hash": report["record_hash"] if report else None,
                            "new_probe_status": admitted["probe_status"] if admitted else "artifact_absent",
                            "retained_probes": sum(d["decision"] == "keep" for d in review["decisions"])})
                    return output
                for start in range(0, len(selected), workers):
                    batch = api.parallel(selected[start:start + workers], review_job, "pre-execution-review")
                    reviews.extend(r for _, r in batch)
                    for output in api.parallel(batch, execute_job, "admitted-execution"):
                        rows.extend(output)
                    print(json.dumps({"arm": arm, "part": part, "tasks": min(start + workers, len(selected))}), flush=True)
                rows.sort(key=_position)
                _write(root / "host_only" / (arm + "_" + part + ".json"), seal({"rows": rows}))
                metrics[arm][part] = {"unreviewed": describe(originals[arm][part]), "preexecution_reviewed": describe(rows)}
                coverage[arm][part] = {"tasks": len(reviews), "review_statuses": dict(Counter(r["status"] for r in reviews)),
                    "original_checks": sum(r["inventory"]["original_checks"] for r in reviews),
                    "unique_checks": sum(r["inventory"]["unique_checks"] for r in reviews),
                    "decisions": dict(Counter(d["decision"] for r in reviews for d in r["decisions"])),
                    "reason_codes": dict(Counter(d["reason_code"] for r in reviews for d in r["decisions"])),
                    "position_probe_statuses": dict(Counter(r["new_probe_status"] for r in rows)),
                    "review_information_origin": "public_contract_and_frozen_check_only_no_new_research"}
                readiness[arm][part] = diagnose_readiness(rows, protocol_hash=protocol["record_hash"], consumed_panels=list(PARTS))
        executions = [_read(p) for p in sorted((root / "admitted_execution").glob("*/execution/calls/*.json"))]
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "metrics": metrics,
            "coverage": coverage, "readiness": readiness, "cost": calls.accounting(), "final_access": False,
            "execution_cost": {"terminal_call_receipts": len(executions),
                "executions_performed_over_run_lifetime": sum(r["execution_performed"] for r in executions),
                "observed_call_receipts": sum(r["execution"]["status"] == "observed" for r in executions)},
            "new_solver_calls": 0, "skill_update_calls": 0, "feedback_authorized": False, "deployment_authorized": False,
            "gate": "pending_consumed_panel_new_uncalibrated_pipeline",
            "effect_claim": "consumed_panel_preexecution_filter_diagnostic_not_research_causal_or_skill_efficacy"})
        _write(root / "results.json", result)
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
    args = parser.parse_args(argv)
    executor = ExecutorPool(args.remote_repo, args.execution_workers)
    try:
        run(args.repo, args.source, args.output, executor, workers=args.workers, api_proxy=args.api_proxy)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
