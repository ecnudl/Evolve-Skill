"""Same-curriculum local versus mechanism learning, in shadow mode.

This Coding-only study separates learned content (raw exposure) from contract
filtering (conditional exposure). It does not calibrate a Research verifier,
authorize deployment, or establish cross-domain noninferiority. All histories
share one frozen panel; repeats/histories are not new independent tasks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import CachedAPI, digest

from .checks import ExecutionCache, pipeline_hash, validate_callable
from .development_feedback import build_development_feedback
from .mechanism_learning import STRATEGIES, propose
from .mechanism_metrics import summarize
from .mechanism_tasks import audit_row, build_panel, qualify_panel, serialize_row
from .mechanism_transport import ConfiguredExecutorPool
from .models import require
from .natural_study import _read, _write
from .panel import checked_path
from .public_revision import _revision_lock
from .research import fixed_rubric
from .rule_skill import RuleSkill, render_skill
from .rule_solver import solve_rule_condition
from .single_round import IMAGE, BoundedCalls, _healthy
from .solver_profile import SolverProfile

VERSION = "same-curriculum-mechanism-shadow-v1"
CONDITIONS = ("no_skill", "current", *STRATEGIES)
EXPOSURES = ("raw", "conditional")


def expected_roster(panel, histories, repeats):
    """Freeze ALL positions before results; no result-driven denominator."""
    return [{"history": f"h{h}", "task_id": row["task"].contract.task_id,
             "family_id": row["family_id"], "domain": row["task"].contract.domain,
             "region": row["region"], "repeat": repeat, "condition": condition,
             "exposure": exposure}
            for h in range(histories) for row in panel["confirmation"]
            for repeat in range(repeats) for exposure in EXPOSURES for condition in CONDITIONS]


def _accounting(api, calls_by_history):
    # BoundedCalls.accounting() counts its entire API root. Histories share
    # that root, so summing those old per-caller counters would multiply cost.
    records = [json.loads(p.read_text()) for p in sorted((api.root / "calls").glob("*.json"))]
    complete = all(type(r.get("usage", {}).get(k)) is int for r in records
                   for k in ("prompt_tokens", "completion_tokens"))
    return {"reserved_logical_requests": sum(len(list((c.root / "intents").glob("*.json")))
                                               for c in calls_by_history.values()),
            "terminal_logical_requests": len(records),
            "http_attempts": sum(r.get("http_attempt_count", 0) for r in records),
            "terminal_failures": sum(r.get("ok") is not True for r in records),
            "terminal_reported_tokens": sum(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"]
                                              for r in records) if complete else None,
            "retry_inclusive_token_usage_known": complete and all(r.get("http_attempt_count") == 1 for r in records),
            "by_kind": dict(Counter(r["request"]["kind"] for r in records)),
            "request_limit": sum(c.limit for c in calls_by_history.values()),
            "temperature": 0, "generation_seed_sent": False,
            "failed_attempt_token_usage_may_be_missing": True}


def _execution_health(solved):
    for key in ("draft_stage", "revised_stage"):
        stage = solved["revision"]["record"][key]
        if stage:
            for receipt in stage["execution_records_host_only"]:
                _healthy(receipt["execution"])


def _collect_development(rows, parent, calls, executor, root, api, repeats, solver_profile=None):
    jobs = [(row, repeat, condition) for row in rows for repeat in range(repeats)
            for condition in ("no_skill", "current")]

    def collect(job):
        row, repeat, condition = job
        pos = root / digest([row["task"].content_hash, repeat, condition])
        solved = solve_rule_condition(row, parent, condition, repeat, calls, executor, pos, exposure="raw",
                                      solver_profile=solver_profile)
        _execution_health(solved)
        cache = ExecutionCache(executor, pos / "feedback_execution", max_executions=16)
        report = validate_callable(row["public_task"], solved["artifact"], fixed_rubric(), cache)
        for record in (*cache.records.values(), *cache.missing_records.values()):
            _healthy(record["execution"])
        _write(pos / "feedback_report.json", report)
        return row, solved["artifact"], report, cache

    collected = api.parallel(jobs, collect, "shared development " + parent.history_id)
    paired, records, identity = defaultdict(dict), {}, None
    for row, artifact, report, cache in collected:
        identity = cache.identity if identity is None else identity
        require(identity == cache.identity, "Mixed public execution identities")
        for key, value in {**cache.records, **cache.missing_records}.items():
            require(key not in records or records[key] == value, "Conflicting execution receipts")
            records[key] = value
        paired[(row["public_task"].content_hash, artifact.repeat)][artifact.condition] = (row, artifact, report)
    entries = []
    for group in paired.values():
        require(set(group) == {"no_skill", "current"}, "Missing development pair")
        entries.append({"task": group["current"][0]["public_task"],
                        "artifacts": tuple(group[c][1] for c in ("no_skill", "current")),
                        "reports": tuple(group[c][2] for c in ("no_skill", "current"))})
    require(bool(collected), "Empty development panel")
    return build_development_feedback(entries, parent_skill=render_skill(parent), rubric=fixed_rubric(),
        pipeline_hash=pipeline_hash(fixed_rubric(), collected[0][3]), execution_identity=identity,
        execution_records=tuple(records.values()), detail_limit=10)


def _validate_options(workers, histories, repeats, development_families, confirmation_families, stop_after):
    for value, lower, upper, name in ((workers, 1, 8, "workers"), (histories, 1, 3, "histories"),
            (repeats, 1, 3, "repeats"), (development_families, 1, 12, "development_families"),
            (confirmation_families, 1, 32, "confirmation_families")):
        require(type(value) is int and lower <= value <= upper, f"Invalid bounded {name}")
    require(stop_after in {None, "prepare", "learn"}, "Unknown stop stage")


def run(repo, output, executor, *, workers=4, histories=3, repeats=2, seed=20260925,
        development_families=8, confirmation_families=24, provider="bigmodel", proxy=None, stop_after=None,
        solver_profile="legacy", solver_max_tokens=None):
    """Resumable complete panel, no hidden feedback or cherry-picked positions.

    Terminal failures are retained. Interrupted calls require explicit recovery;
    this entry never silently samples a replacement. The output-directory lock
    prevents concurrent drivers from corrupting a logical experiment.
    """
    _validate_options(workers, histories, repeats, development_families, confirmation_families, stop_after)
    require(type(seed) is int and seed >= 0, "Nonnegative panel seed required")
    profile = SolverProfile.named(solver_profile, solver_max_tokens)
    root = checked_path(output)
    with _revision_lock(root / "study_lock"):
        return _run(checked_path(repo), root, executor, workers=workers, histories=histories, repeats=repeats,
                    seed=seed, development_families=development_families,
                    confirmation_families=confirmation_families, provider=provider, proxy=proxy,
                    stop_after=stop_after, profile=profile)


def _run(repo, root, executor, *, workers, histories, repeats, seed, development_families,
         confirmation_families, provider, proxy, stop_after, profile):
    panel = build_panel(seed, development_families=development_families,
                        confirmation_families=confirmation_families)
    roster = expected_roster(panel, histories, repeats)
    # Check the whole schema/grid before spending any tokens. Missing positions
    # are an explicit unknown here, not a dummy success or an observed failure.
    summarize([], roster, bootstrap_seed=seed, bootstrap_samples=100)
    _write(root / "host_only/panel.json", seal({"version": VERSION, "manifest": panel["manifest"],
        **{part: [serialize_row(r) for r in panel[part]] for part in ("development", "confirmation")}}))
    _write(root / "expected_positions.json", seal({"positions": roster}))
    with CachedAPI(repo, root / "api", workers=workers, provider=provider, stream=True,
                   reasoning_effort="low", proxy=proxy, **profile.api_options()) as api:
        # Upper bound, not a promise to consume calls: identical effective
        # prompts share receipts WITHIN a history. Histories never share calls.
        limit = 2 + 4 * len(panel["development"]) * repeats + 16 * len(panel["confirmation"]) * repeats
        protocol = seal({"version": VERSION, "manifest_hash": panel["manifest"]["record_hash"],
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(Path(__file__).parent.glob("*.py"))},
            "service": api.service, "executor": executor.identity,
            "transport": getattr(executor, "transport_identity", {"kind": "direct_isolated_executor"}),
            "workers": workers, "histories": histories, "repeats": repeats, "seed": seed,
            "conditions": list(CONDITIONS), "exposures": list(EXPOSURES),
            "request_limit_per_history": limit,
            **({"solver_profile": profile.to_dict(), "updater_token_cap": 2048} if profile.enabled
               else {"solver_updater_token_cap": 2048}),
            "parent": "same_empty_RuleSkill_per_history", "current_equals_no_skill_at_cold_start": True,
            "same_feedback_same_schema_same_max_two_edits": True,
            "only_learning_strategy_varies": True, "shared_panel_across_histories": True,
            "histories_are_independent_requests_not_independent_task_datasets": True,
            "feedback": "registered_public_execution_only_no_H_no_Research",
            "feedback_and_updates_shadow_only": True, "one_public_revision_all_conditions": True,
            "conditional_filter": "public_obligation_kinds_before_execution_not_hidden_region_labels",
            "all_candidates_frozen_before_any_confirmation": True,
            "final_access": False, "deployment_authorized": False, "cross_domain_evaluated": False,
            "noninferiority": {"delta": .02, "min_declared_families": 20, "min_histories": 3,
                                "diagnostic_only_never_authorizes": True},
            "bootstrap_seed": seed, "bootstrap_samples": 2000})
        _write(root / "protocol.json", protocol)
        if (root / "summary.json").exists():
            result = _read(root / "summary.json")
            require(result["protocol_hash"] == protocol["record_hash"], "Summary has another protocol")
            return result
        calls = {f"h{h}": BoundedCalls(api, root / "histories" / f"h{h}" / "budget",
                                      digest([protocol["record_hash"], f"h{h}"]), limit,
                                      output_token_limits=profile.output_token_limits())
                 for h in range(histories)}
        ping_files = {"ping.py": "def ping():\n    return True\n"}
        ping = executor.run(ping_files, "ping", "ping", [], {})
        verify(ping)
        _healthy(ping)
        require(ping.get("input_hash") == digest({"files": ping_files, "module": "ping", "function": "ping",
                                                   "args": [], "kwargs": {}})
                and ping.get("status") == "observed" and ping.get("actual") is True,
                "Isolated executor preflight failed")
        qualification = qualify_panel(panel, executor, root / "qualification")
        _write(root / "qualification_summary.json", qualification)
        if qualification["status"] != "qualified" or qualification.get("formal_eligible") is not True:
            result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "status": "pending",
                "stage": "qualification", "reason": "Preselected panel did not fully qualify; no replacement tasks.",
                "qualification_hash": qualification["record_hash"], "accounting": _accounting(api, calls),
                "method_effect_evaluated": False, "deployment_authorized": False})
            _write(root / "pending_qualification.json", result)
            return result
        _write(root / "frozen_panel.json", seal({"protocol_hash": protocol["record_hash"],
            "manifest_hash": panel["manifest"]["record_hash"], "qualification_hash": qualification["record_hash"],
            "before_learning": True, "not_verifier_calibration": True}))
        print("PANEL_FROZEN", json.dumps({p: len(panel[p]) for p in ("development", "confirmation")}), flush=True)
        if stop_after == "prepare":
            return seal({"status": "prepared", "protocol_hash": protocol["record_hash"], "accounting": _accounting(api, calls)})
        learned, statuses, freezes = {}, {}, {}
        for history, bounded in calls.items():
            base = root / "histories" / history
            parent = RuleSkill("shared-cold-" + history, ())
            _write(base / "parent.json", seal({"skill": parent.to_dict(), "text": render_skill(parent),
                                              "origin": "cold_start_not_hand_written_parent"}))
            feedback = _collect_development(panel["development"], parent, bounded, executor,
                                            base / "development", api, repeats, profile)
            _write(base / "feedback.json", feedback)
            learned[history] = {"no_skill": parent, "current": parent}
            statuses[history], requests = {}, {}
            for strategy in STRATEGIES:
                proposal = propose(bounded, parent, feedback, strategy=strategy)
                _write(base / "updates" / (strategy + ".json"), proposal)
                requests[strategy] = proposal["request"]
                update = proposal["update"]
                statuses[history][strategy] = update["status"]
                candidate = RuleSkill.from_dict(update["candidate"]) if update["status"] == "candidate" else parent
                learned[history][strategy] = candidate
                print("UPDATE", history, strategy, update["status"], "rules", len(candidate.rules), flush=True)
            require(requests["local"]["user"] == requests["mechanism"]["user"], "Learning arms received different evidence")
            freezes[history] = seal({"protocol_hash": protocol["record_hash"], "history": history,
                "feedback_hash": feedback["record_hash"], "update_statuses": statuses[history],
                "skills": {c: s.to_dict() for c, s in learned[history].items()},
                "noncandidate_retains_parent": True, "deployment_authorized": False})
            _write(base / "frozen_candidates.json", freezes[history])
        freeze = seal({"protocol_hash": protocol["record_hash"], "histories": freezes,
                       "before_any_confirmation": True})
        _write(root / "frozen_candidates.json", freeze)
        if stop_after == "learn":
            return seal({"status": "learned_shadow_candidates", "protocol_hash": protocol["record_hash"],
                         "freeze_hash": freeze["record_hash"], "accounting": _accounting(api, calls)})
        task_lookup = {r["task"].contract.task_id: r for r in panel["confirmation"]}

        def confirm(position):
            history, condition, exposure = (position[k] for k in ("history", "condition", "exposure"))
            row = task_lookup[position["task_id"]]
            pos = root / "histories" / history / "confirmation" / digest(position)
            solver_condition = condition if condition in {"no_skill", "current"} else "candidate"
            solved = solve_rule_condition(row, learned[history][condition], solver_condition,
                position["repeat"], calls[history], executor, pos, exposure=exposure, solver_profile=profile)
            _execution_health(solved)
            audit = audit_row(row, solved["artifact"], executor, pos)
            receipt = audit.get("receipt")
            if receipt:
                _healthy(receipt.get("execution"))
            value = seal({**position, "status": audit["status"],
                "skill_applied": bool(solved["exposure"]["rendering"]["selected_rule_ids"]),
                "audit_hash": audit["record_hash"], "artifact_hash": solved["artifact"].content_hash,
                "trajectory_hash": digest([solved["initial_artifact"].source_hash, solved["artifact"].source_hash]),
                "request_hash": solved["initial_artifact"].source_ref.split(":", 1)[-1],
                "receipt_hash": solved["artifact"].source_hash,
                "rule_skill_hash": learned[history][condition].content_hash,
                "revision_hash": solved["revision"]["record"]["record_hash"],
                "update_status": statuses[history].get(condition), "deployment_authorized": False})
            _write(pos / "result.json", value)
            return value

        # Order is frozen independent of outcomes; interleave methods within
        # a task/repeat to reduce gross temporal provider confounding.
        rows = api.parallel(roster, confirm, "paired raw and conditional confirmation")
        _write(root / "confirmation_rows.json", seal({"rows": rows}))
        metrics = summarize(rows, roster, bootstrap_seed=seed)
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
            "status": "completed_shadow_pilot", "metrics": metrics,
            "freeze_hash": freeze["record_hash"], "update_statuses": statuses,
            "accounting": _accounting(api, calls),
            "provenance": "engineering_fixture" if api.service.get("fixture") is True else "real_model_synthetic_tasks",
            "research_increment_evaluated": False, "cross_domain_evaluated": False,
            "deployment_authorized": False,
            "limitations": ["One shared Coding synthetic panel; not an independent public benchmark.",
                "Histories vary model requests, not the development task distribution.",
                "Cold Current is a No-Skill alias, not a learned incumbent.",
                "Public-only feedback is shadow evidence, not newly calibrated verifier authority.",
                "Conditional filtering measures abstention separately from raw learned-content utility.",
                "No amount of fixture success or zero observed regressions establishes broad safety."]})
        _write(root / "summary.json", result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE, help="Existing digest-pinned Docker image on the Linux executor")
    parser.add_argument("--ssh-config", type=Path, help="Optional dedicated frozen SSH config, strict host-key checking")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--histories", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--development-families", type=int, default=8)
    parser.add_argument("--confirmation-families", type=int, default=24)
    parser.add_argument("--proxy", help="Optional existing credential-free loopback HTTP proxy; no route changes")
    parser.add_argument("--stop-after", choices=("prepare", "learn"))
    parser.add_argument("--solver-profile", choices=("legacy", "reliable_v1"), default="legacy")
    parser.add_argument("--solver-max-tokens", type=int, help="Predeclare a uniform solver cap; reliable_v1 defaults to 4096")
    args = parser.parse_args(argv)
    executor = ConfiguredExecutorPool(args.remote_repo, workers=min(args.workers, 6),
        host=args.host, remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.output, executor, workers=args.workers, histories=args.histories,
            repeats=args.repeats, seed=args.seed, development_families=args.development_families,
            confirmation_families=args.confirmation_families, proxy=args.proxy, stop_after=args.stop_after,
            solver_profile=args.solver_profile, solver_max_tokens=args.solver_max_tokens)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
