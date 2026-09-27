"""Fixed development-only patch diagnostic, not Skill learning or confirmation.

All 12 source families and both contract roles are registered before execution.
Reference/control qualification precedes any paid model call. A cold No-Skill
solver gets the existing single public-check repair opportunity; independent
host audits of its draft and final answer are never fed back to that solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot import api as api_module
from skillopt.validator_pilot.api import CachedAPI, digest

from .mechanism_case_confirmation import _check_reserved_receipts
from .mechanism_study import _accounting, _execution_health
from .mechanism_transport import ConfiguredExecutorPool
from .models import require
from .natural_study import _read, _write
from .panel import checked_path
from .patch_tasks import audit_row, build_development_panel, qualify_panel, serialize_row
from .public_revision import _revision_lock
from .rule_skill import RuleSkill
from .rule_solver import solve_rule_condition
from .single_round import IMAGE, BoundedCalls, _healthy

VERSION = "fixed-source-patch-development-diagnostic-v1"
ROLES = ("preserve", "replace")
COMPONENTS = ("target_status", "retained_status", "replaced_status", "state_status")
STATUSES = ("pass", "fail", "unknown", "not_applicable")


def _roster(rows, repeats):
    require(len(rows) == 24, "Exactly 24 preregistered patch tasks required; no outcome-dependent subsets")
    families = {}
    for row in rows:
        task = row["task"].contract
        require(task.partition == "development" and task.domain == "coding" and row["region"] in ROLES
                and task.family_id == row["family_id"],
                "Only the fixed Coding development roles are eligible")
        families.setdefault(row["family_id"], []).append(row["region"])
    require(len(families) == 12 and all(sorted(roles) == sorted(ROLES) for roles in families.values()),
            "Each of 12 source families must retain both contract roles")
    require(len({row["task"].contract.task_id for row in rows}) == 24, "Duplicate diagnostic task")
    return [{"task_id": row["task"].contract.task_id, "family_id": row["family_id"],
        "role": row["region"], "repeat": repeat, "condition": "no_skill"}
        for row in rows for repeat in range(repeats)]


def _counts(values, *, applicable=False):
    counts = Counter(values)
    denominator = len(values)
    observed = counts["pass"] + counts["fail"]
    applicable_denominator = denominator - counts["not_applicable"]
    return {"positions": denominator, "counts": {s: counts[s] for s in STATUSES},
        "known_coverage": {"numerator": observed, "denominator": applicable_denominator,
                           "value": observed / applicable_denominator if applicable_denominator else None},
        "all_attempt_success": {"numerator": counts["pass"],
            "denominator": applicable_denominator if applicable else denominator,
            "value": counts["pass"] / (applicable_denominator if applicable else denominator)
                     if (applicable_denominator if applicable else denominator) else None}}


def summarize(rows, roster):
    """All registered tasks remain in denominators; repetitions are not families."""
    expected = {(row["task_id"], row["repeat"]): row for row in roster}
    require(len(expected) == len(roster), "Duplicate expected diagnostic position")
    observed = {}
    for row in rows:
        verify(row)
        key = row["task_id"], row["repeat"]
        require(key in expected and key not in observed
                and all(row.get(k) == v for k, v in expected[key].items()), "Unknown or mismatched diagnostic position")
        require(all(row.get(stage + "_status") in STATUSES[:3] for stage in ("initial", "final")),
                "Explicit draft/final status required")
        require(all(set(row[stage + "_components"]) == set(COMPONENTS)
                    and all(v in STATUSES for v in row[stage + "_components"].values())
                    for stage in ("initial", "final")), "Explicit component statuses required")
        observed[key] = row
    grid = [observed.get(key, {**position, "initial_status": "unknown", "final_status": "unknown",
             **{stage + "_components": {name: ("not_applicable" if name == "replaced_status" and position["role"] == "preserve"
                                               else "unknown") for name in COMPONENTS}
                for stage in ("initial", "final")}})
            for key, position in expected.items()]

    def group(values):
        transitions = Counter(row["initial_status"] + "->" + row["final_status"] for row in values)
        by_family = {}
        for family in sorted({row["family_id"] for row in values}):
            family_rows = [row for row in values if row["family_id"] == family]
            by_family[family] = sum(row["final_status"] == "pass" for row in family_rows) / len(family_rows)
        return {"positions": len(values), "tasks": len({row["task_id"] for row in values}),
            "source_families": len(by_family), "family_equal_final_success":
                sum(by_family.values()) / len(by_family) if by_family else None,
            "initial": _counts([row["initial_status"] for row in values]),
            "final": _counts([row["final_status"] for row in values]),
            "transitions": dict(sorted(transitions.items())),
            "audit_confirmed_after_public_revision_repairs": transitions["fail->pass"],
            "audit_confirmed_after_public_revision_regressions": transitions["pass->fail"],
            "unknown_pairs": sum("unknown" in (row["initial_status"], row["final_status"]) for row in values),
            "components": {stage: {name: _counts([row[stage + "_components"][name] for row in values], applicable=True)
                                    for name in COMPONENTS} for stage in ("initial", "final")}}
    references = {}
    for field in ("initial_request_hash", "initial_artifact_hash", "final_artifact_hash"):
        values = [row[field] for row in rows if field in row]
        references[field] = {"positions_with_reference": len(values), "unique_references": len(set(values)),
                             "aliased_positions": len(values) - len(set(values))}
    return seal({"version": VERSION, "expected_positions": len(roster), "observed_positions": len(rows),
        "missing_positions": len(roster) - len(rows), "overall": group(grid),
        "by_role": {role: group([row for row in grid if row["role"] == role]) for role in ROLES},
        "by_family": {family: group([row for row in grid if row["family_id"] == family])
                      for family in sorted({row["family_id"] for row in grid})},
        "reference_reuse": references, "records_hash": digest(rows), "roster_hash": digest(roster),
        "method_effect_evaluated": False, "generalization_evaluated": False,
        "aggregation_unit": "declared_source_family_cluster", "family_independence_proven": False,
        "deployment_authorized": False})


def _audit(row, artifact, executor, root):
    result = verify(audit_row(row, artifact, executor, root))
    require(result.get("status") in STATUSES[:3]
            and all(result.get(name) in STATUSES for name in COMPONENTS), "Missing diagnostic audit components")
    if result.get("receipt"):
        _healthy(result["receipt"].get("execution"))
    return result


def run(repo, output, executor, *, seed=20260926, repeats=2, workers=2, proxy=None, stop_after=None):
    require(type(seed) is int and seed >= 0, "Nonnegative fixed seed required")
    require(type(repeats) is int and 1 <= repeats <= 3, "Diagnostic repeats must be 1..3")
    require(type(workers) is int and 1 <= workers <= 4, "Diagnostic workers must be 1..4")
    require(stop_after in (None, "prepare"), "Only prepare is an optional diagnostic stopping point")
    repo, root = checked_path(Path(repo)).resolve(), checked_path(Path(output)).resolve()
    require(root != repo and root not in repo.parents, "Use a separate diagnostic output directory")
    with _revision_lock(root / "diagnostic_lock"):
        panel = build_development_panel(seed=seed)
        verify(panel["manifest"])
        rows, parent = panel["development"], RuleSkill("patch-diagnostic-cold", ())
        roster = _roster(rows, repeats)
        summarize([], roster)
        _write(root / "host_only/panel.json", seal({"manifest": panel["manifest"],
            "development": [serialize_row(row) for row in rows]}))
        _write(root / "expected_positions.json", seal({"positions": roster}))
        with CachedAPI(repo, root / "api", workers=workers, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy, initial_health_policy="completed_response_v1") as api:
            limit = 2 * len(roster)
            protocol = seal({"version": VERSION, "seed": seed, "repeats": repeats, "workers": workers,
                "manifest_hash": panel["manifest"]["record_hash"], "roster_hash": digest(roster),
                "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(__file__).parent.glob("*.py"))},
                "api_source_hash": hashlib.sha256(Path(api_module.__file__).read_bytes()).hexdigest(),
                "service": api.service, "executor": executor.identity,
                "transport": getattr(executor, "transport_identity", {}), "request_limit": limit,
                "histories": 1, "history_label_is_cache_namespace_not_learning": True,
                "condition": "no_skill", "parent": parent.to_dict(), "solver_token_cap": 2048,
                "one_public_revision": True, "qualification_before_any_paid_request": True,
                "development_only": True, "skill_update": False, "research": False,
                "confirmation_selection": False, "deployment_authorized": False})
            _write(root / "protocol.json", protocol)
            _check_reserved_receipts(root, protocol)
            if (root / "summary.json").exists():
                result = _read(root / "summary.json")
                require(result["protocol_hash"] == protocol["record_hash"], "Diagnostic summary protocol changed")
                return result
            calls = BoundedCalls(api, root / "histories/h0/budget", digest([protocol["record_hash"], "h0"]), limit)
            def accounting():
                return _accounting(api, {"h0": calls})
            ping_files = {"ping.py": "def ping():\n    return True\n"}
            ping = verify(executor.run(ping_files, "ping", "ping", [], {}))
            _healthy(ping)
            require(ping.get("input_hash") == digest({"files": ping_files, "module": "ping", "function": "ping",
                                                     "args": [], "kwargs": {}})
                    and ping.get("status") == "observed" and ping.get("actual") is True,
                    "Safe executor health failed before model calls")
            qualification = verify(qualify_panel(panel, executor, root / "qualification"))
            require(qualification.get("panel_hash") == panel["manifest"]["record_hash"],
                    "Qualification receipt belongs to another frozen panel")
            _write(root / "qualification_summary.json", qualification)
            common = {"version": VERSION, "protocol_hash": protocol["record_hash"],
                "provenance": "engineering_fixture" if api.service.get("fixture") is True else "real_model_synthetic_development",
                "method_effect_evaluated": False, "skill_evolution_evaluated": False,
                "generalization_evaluated": False, "deployment_authorized": False}
            if qualification.get("status") != "qualified" or qualification.get("formal_eligible") is not True:
                result = seal({**common, "status": "pending_qualification", "qualification_hash": qualification["record_hash"],
                    "accounting": accounting(), "reason": "All fixed tasks must qualify; no replacement or paid solver calls."})
                _write(root / "pending_qualification.json", result)
                return result
            frozen = seal({"protocol_hash": protocol["record_hash"], "manifest_hash": panel["manifest"]["record_hash"],
                "qualification_hash": qualification["record_hash"], "parent": parent.to_dict(),
                "before_any_solver": True, "development_only": True})
            _write(root / "frozen_panel.json", frozen)
            if stop_after == "prepare":
                return seal({**common, "status": "prepared_diagnostic", "freeze_hash": frozen["record_hash"],
                             "accounting": accounting()})
            lookup = {row["task"].contract.task_id: row for row in rows}

            def one(position):
                row, base = lookup[position["task_id"]], root / "positions" / digest(position)
                public = {name: row[name] for name in ("task", "public_task", "public_wrapper")}
                solved = solve_rule_condition(public, parent, "no_skill", position["repeat"], calls, executor, base,
                                              exposure="raw")
                _execution_health(solved)
                # Both hidden audits occur only after the final public-only
                # revision has been selected. Neither can affect the revision.
                initial = _audit(row, solved["initial_artifact"], executor, base)
                final = _audit(row, solved["artifact"], executor, base)
                value = seal({**position, "initial_status": initial["status"], "final_status": final["status"],
                    "initial_components": {k: initial[k] for k in COMPONENTS},
                    "final_components": {k: final[k] for k in COMPONENTS},
                    "initial_audit_hash": initial["record_hash"], "final_audit_hash": final["record_hash"],
                    "initial_artifact_hash": solved["initial_artifact"].content_hash,
                    "final_artifact_hash": solved["artifact"].content_hash,
                    "initial_request_hash": solved["initial_artifact"].source_ref.split(":", 1)[-1],
                    "revision_hash": solved["revision"]["record"]["record_hash"],
                    "revision_status": solved["revision"]["record"]["status"], "rule_skill_hash": parent.content_hash,
                    "hidden_feedback_used": False, "deployment_authorized": False})
                _write(base / "result.json", value)
                return value

            results = api.parallel(roster, one, "fixed development-only patch diagnostic")
            _write(root / "diagnostic_rows.json", seal({"rows": results}))
            result = seal({**common, "status": "completed_development_diagnostic", "freeze_hash": frozen["record_hash"],
                "metrics": summarize(results, roster), "accounting": accounting(),
                "limitations": ["12 declared, same-author curated Coding source families, not proven independent natural projects or a public benchmark.",
                    "Both roles and all repeats remain registered, including failed and unknown calls.",
                    "Draft/final comparisons diagnose one public repair, not Skill benefit or generalization.",
                    "Host audits are bounded task checks, not an unrestricted semantic-correctness guarantee.",
                    "No Skill update, Research calibration, confirmation-set selection or deployment occurred."]})
            _write(root / "summary.json", result)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--ssh-config", type=Path)
    parser.add_argument("--proxy")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260926)
    parser.add_argument("--stop-after", choices=("prepare",))
    args = parser.parse_args(argv)
    executor = ConfiguredExecutorPool(args.remote_repo, workers=args.workers, host=args.host,
        remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.output, executor, workers=args.workers, repeats=args.repeats,
                     seed=args.seed, proxy=args.proxy, stop_after=args.stop_after)
        print(json.dumps({"status": result["status"], "accounting": result["accounting"]}), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
