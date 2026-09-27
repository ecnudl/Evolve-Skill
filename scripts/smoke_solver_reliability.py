"""Bounded engineering smoke, not Skill learning or method-effect evaluation.

Three synthetic public contracts, one repeat, three condition identities.
Current/Candidate intentionally share the SAME handwritten smoke-only rule;
equal requests share cached receipts. At most 18 logical model requests. No H.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import rule_solver
from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.curriculum_tasks import compile_family
from skillopt.skill_validation.mechanism_transport import ConfiguredExecutorPool
from skillopt.skill_validation.models import require
from skillopt.skill_validation.public_revision import _revision_lock
from skillopt.skill_validation.rule_skill import Rule, RuleSkill
from skillopt.skill_validation.rule_solver import solve_rule_condition
from skillopt.skill_validation.single_round import IMAGE, BoundedCalls, _healthy, _write
from skillopt.skill_validation.solver_profile import SolverProfile
from skillopt.validator_pilot.api import CachedAPI, digest


def run(repo, output, executor, *, proxy=None):
    repo, root = Path(repo).resolve(), Path(output).resolve()
    profile = SolverProfile.named("reliable_v1")
    spec = {"steps": [{"op": "filter", "kind": "nonzero"}, {"op": "reorder", "kind": "ascending"}],
            "aggregate": "weighted_sum"}
    # This is an explicitly labelled host-selected smoke family, not a newly
    # qualified research panel or a benchmark sample. H fields never leave host.
    rows = [{k: row[k] for k in ("task", "public_task", "public_wrapper")}
            for row in compile_family(spec, "development")]
    parent = RuleSkill("engineering-smoke-not-learned", ())
    rule = Rule("check-explicit-contract", "Constraint Preservation",
                ("Implement the declared output and input-state requirement; check public examples.",),
                "The public task explicitly declares these requirements.",
                ("Do not add a requirement to preserve input when mutation is required or unconstrained.",),
                ScopeRule(("requested_behavior",)), ())
    advice = RuleSkill(parent.history_id, (rule,))
    with _revision_lock(root / "smoke_lock"):
        with CachedAPI(repo, root / "api", workers=1, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy, **profile.api_options()) as api:
            protocol = seal({"version": "solver-reliability-engineering-smoke-v2", "solver_profile": profile.to_dict(),
                "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(rule_solver.__file__).resolve().parent.glob("*.py"))},
                "script_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "service": api.service, "executor": executor.identity, "transport": executor.transport_identity,
                "tasks": [row["task"].content_hash for row in rows], "spec": spec,
                "skills": {"no_skill": parent.to_dict(), "current": advice.to_dict(), "candidate": advice.to_dict()},
                "request_limit": 18, "repeats": 1, "conditions": ["no_skill", "current", "candidate"],
                "skill_origin": "handwritten_engineering_control_not_learned", "hidden_audit_access": False,
                "not_independent_tasks": True, "method_effect_evaluated": False, "deployment_authorized": False})
            _write(root / "protocol.json", protocol)
            # Reserve both stages for every position. Cache aliases save calls,
            # but identical code can produce differing public observations.
            calls = BoundedCalls(api, root / "budget", protocol["record_hash"], 18,
                                 output_token_limits=profile.output_token_limits())
            ping_files = {"ping.py": "def ping():\n    return True\n"}
            ping = executor.run(ping_files, "ping", "ping", [], {})
            _healthy(ping)
            require(ping.get("status") == "observed" and ping.get("actual") is True,
                    "Isolated preflight unavailable; no paid requests")
            records = []
            for row in rows:
                for condition in ("no_skill", "current", "candidate"):
                    position = root / "positions" / digest([row["task"].content_hash, condition])
                    solved = solve_rule_condition(row, parent if condition == "no_skill" else advice,
                        condition, 0, calls, executor, position, exposure="raw", solver_profile=profile)
                    record = solved["revision"]["record"]
                    for stage in (record["draft_stage"], record["revised_stage"]):
                        if stage is not None:
                            for execution in stage["execution_records_host_only"]:
                                _healthy(execution["execution"])
                    records.append({"task_hash": row["task"].content_hash, "condition": condition,
                        "initial_availability": solved["initial_artifact"].availability,
                        "public_status": record["public_status"], "revision_status": record["status"],
                        "revision_hash": record["record_hash"], "artifact_hash": solved["artifact"].content_hash,
                        "position": str(position.relative_to(root))})
            summary = seal({"version": protocol["version"], "protocol_hash": protocol["record_hash"],
                "status": "completed_engineering_smoke", "model": api.model,
                "fixture_only": api.service.get("fixture") is True, "positions": len(records),
                "tasks": len(rows), "independent_task_families": 1, "records": records,
                "public_outcomes": dict(Counter(r["public_status"] for r in records)),
                "accounting": calls.accounting(), "hidden_audit_calls": 0,
                "skill_updated": False, "method_effect_evaluated": False, "deployment_authorized": False,
                "limitations": ["Handwritten smoke-only rule; Current and Candidate intentionally identical.",
                                "One synthetic family with three contract variants, no statistical effect estimate.",
                                "Public pass does not establish hidden correctness or generalization."]})
            _write(root / "summary.json", summary)
            return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--ssh-config", type=Path)
    parser.add_argument("--proxy")
    args = parser.parse_args()
    executor = ConfiguredExecutorPool(args.remote_repo, workers=1, host=args.host,
        remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.output, executor, proxy=args.proxy)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
