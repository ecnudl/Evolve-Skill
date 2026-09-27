"""One-round, shadow curriculum experiment; no benchmark or deployment claim.

Historical public evidence proposes capability hypotheses. Two new curricula
then start from the SAME empty rule Skill: generic versus history-targeted.
Only new public execution feedback reaches their identical rule updater.
Generated confirmation families are frozen before any learning execution.
No audit answer, Research hypothesis, or uncalibrated check becomes feedback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
from collections import Counter, defaultdict
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import CachedAPI, digest

from .capability_goals import history_view, plan_goals
from .checks import ExecutionCache, pipeline_hash, validate_callable
from .curriculum_tasks import (
    audit_artifact,
    behavior_fingerprint,
    compile_family,
    family_fingerprint,
    generate_messages,
    parse_families,
    screen_family,
)
from .development_feedback import build_development_feedback
from .models import require
from .natural_policy import normalize_json_envelope
from .natural_study import ExecutorPool, _read, _write
from .panel import checked_path
from .research import fixed_rubric
from .rule_learning import propose
from .rule_skill import RuleSkill, render_skill
from .rule_solver import solve_rule_condition
from .single_round import BoundedCalls, _healthy
from .solver_profile import SolverProfile

VERSION = "history-capability-curriculum-shadow-v4"
ARMS = ("generic", "targeted")
GENERATION_TOKEN_CAP = 6144


class CurriculumCalls(BoundedCalls):
    """A larger teacher budget, using the SAME reservations and API receipts.

    Frozen historical BoundedCalls and solver/updater budgets are unchanged.
    GLM's token cap includes reasoning; 2048 can yield no visible task output.
    This extension is restricted to task-spec generation, not an implicit retry.
    """

    def call(self, system, user, kind, *, repeat=0, max_tokens=2048):
        require(type(max_tokens) is int, "Integer output token budget required")
        if max_tokens <= 2048 or kind in self.output_token_limits:
            return super().call(system, user, kind, repeat=repeat, max_tokens=max_tokens)
        require(kind in {"curriculum-spec-generic", "curriculum-spec-targeted"}
                and max_tokens == GENERATION_TOKEN_CAP, "Larger budget is restricted to curriculum generation")
        require(type(repeat) is int and repeat >= 0 and len((system + user).encode()) <= 120000,
                "Bounded teacher request required")
        key = digest({"protocol": self.protocol_hash, "system": system, "user": user,
                      "kind": kind, "repeat": repeat, "max_tokens": max_tokens})
        request = {"model": self.api.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.api.service}
        request_hash = digest(request)
        intent = self.root / "intents" / (request_hash + ".json")
        receipt_path = self.api.root / "calls" / (request_hash + ".json")
        with self.lock:
            lock = self.request_locks.setdefault(request_hash, threading.Lock())
        with lock:
            with self.lock:
                if receipt_path.exists():
                    require(intent.exists() and _read(intent)["request_hash"] == request_hash,
                            "Teacher cache without reservation")
                elif intent.exists():
                    raise ValueError("Interrupted teacher request retained; no automatic resampling")
                else:
                    require(len(list((self.root / "intents").glob("*.json"))) < self.limit,
                            "Frozen logical request budget exhausted")
                    _write(intent, seal({"request_hash": request_hash, "protocol_hash": self.protocol_hash,
                                         "kind": kind, "repeat": repeat}))
            record = self.api.call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            require(record.get("request") == request and record.get("request_hash") == request_hash,
                    "Teacher request binding changed")
            require(receipt_path.is_file() and json.loads(receipt_path.read_text()) == record,
                    "Missing durable teacher receipt")
            return record


def validate_family_pools(pools):
    """One semantic *specification* cannot cross the development boundary.

    Different compositions can still be semantically equivalent. Fingerprints
    establish structural exclusion, not broad independent-task generalization.
    Development-arm overlap is legal and reported, never silently deduplicated.
    """
    require(type(pools) is dict and set(pools) == {"confirmation", *ARMS}, "Three explicit family pools required")
    hashes, behavior_hashes = {}, {}
    for name, specs in pools.items():
        require(type(specs) is list and bool(specs), "A family pool must be nonempty")
        hashes[name] = [family_fingerprint(spec) for spec in specs]
        require(len(set(hashes[name])) == len(hashes[name]), "Duplicate structural family within a pool")
        behavior_hashes[name] = [behavior_fingerprint(spec) for spec in specs]
        require(len(set(behavior_hashes[name])) == len(behavior_hashes[name]), "Finite behavior-equivalent families within a pool")
    for arm in ARMS:
        require(not set(hashes[arm]) & set(hashes["confirmation"]), "Development/confirmation structural family overlap")
        require(not set(behavior_hashes[arm]) & set(behavior_hashes["confirmation"]),
                "Development/confirmation finite behavior overlap")
    return seal({"family_hashes": hashes,
        "development_overlap": sorted(set(hashes["generic"]) & set(hashes["targeted"])),
        "finite_behavior_hashes": behavior_hashes,
        "finite_behavior_development_overlap": sorted(set(behavior_hashes["generic"]) & set(behavior_hashes["targeted"])),
        "structural_and_finite_behavior_disjointness_only": True, "semantic_independence_established": False})


def _direction(base, candidate):
    require(base in {"pass", "fail", "unknown"} and candidate in {"pass", "fail", "unknown"}, "Invalid outcome")
    return "unknown" if "unknown" in (base, candidate) else "tie" if base == candidate else "win" if candidate == "pass" else "loss"


def summarize(rows, *, expected_positions=None):
    """Keep missing/unknown denominators; repeats and role variants are clustered."""
    grouped = defaultdict(dict)
    for row in rows:
        require(row["arm"] in {"no_skill", *ARMS}, "Unknown confirmation arm")
        key = row["family"], row["role"], row["repeat"]
        require(key not in grouped[row["arm"]], "Duplicate confirmation position")
        require(row["status"] in {"pass", "fail", "unknown"}, "Unknown audit outcome")
        grouped[row["arm"]][key] = row
    require(set(grouped) == {"no_skill", *ARMS}, "Missing comparison arm")
    baseline = grouped["no_skill"]
    require(all(set(group) == set(baseline) for group in grouped.values()), "Unpaired confirmation outcomes")
    if expected_positions is not None:
        require(set(baseline) == set(expected_positions), "Missing planned positions; do not silently drop them")
    result = {}
    for arm, group in grouped.items():
        family_net = defaultdict(int)
        family_unknown = Counter()
        comparisons = Counter()
        for key, row in group.items():
            outcome = _direction(baseline[key]["status"], row["status"])
            comparisons[outcome] += 1
            family_net[key[0]] += {"win": 1, "loss": -1}.get(outcome, 0)
            family_unknown[key[0]] += int(outcome == "unknown")
        result[arm] = {
            "positions": len(group), "structural_families": len(family_net),
            "role_tasks": len({(k[0], k[1]) for k in group}),
            "status_counts": {s: sum(r["status"] == s for r in group.values()) for s in ("pass", "fail", "unknown")},
            "paired_vs_no_skill": {s: comparisons[s] for s in ("win", "loss", "tie", "unknown")},
            "family_net_paired_wins": dict(sorted(family_net.items())),
            "family_unknown_positions": {family: family_unknown[family] for family in sorted(family_net)},
            "family_complete_comparison": {family: family_unknown[family] == 0 for family in sorted(family_net)},
            "by_role": {role: dict(Counter(r["status"] for k, r in group.items() if k[1] == role))
                        for role in sorted({k[1] for k in group})},
        }
    return seal({"arms": result, "independent_semantic_family_count_unknown": True,
        "interpretation": "Finite synthetic composition pilot; roles/repeats are not independent tasks. Unknown is not failure.",
        "deployment_authorized": False, "cross_domain_evaluated": False})


def _generate(calls, *, count, condition, goal=None, excluded=()):
    fingerprints = [family_fingerprint(spec) for spec in excluded]
    system, user = generate_messages(goal, fingerprints, count, condition=condition, excluded_specs=excluded)
    receipt = calls.call(system, user, "curriculum-spec-" + condition, max_tokens=GENERATION_TOKEN_CAP)
    request = receipt.get("request") if type(receipt) is dict else None
    require(type(request) is dict and all(request.get(k) == v for k, v in {
        "system": system, "user": user, "kind": "curriculum-spec-" + condition,
        "repeat": 0, "max_tokens": GENERATION_TOKEN_CAP}.items())
        and receipt.get("request_hash") == digest(request) and type(receipt.get("ok")) is bool,
        "Curriculum generation receipt belongs to another request")
    result = {"condition": condition, "count": count, "prompt_hash": digest({"system": system, "user": user}),
              "api_receipt_hash": digest(receipt), "family_origin": "synthetic_generated_spec"}
    if not receipt.get("ok"):
        return seal({**result, "status": "api_failure", "families": []})
    try:
        require(type(receipt.get("response")) is str and len(receipt["response"].encode()) <= 24000,
                "Raw curriculum response exceeds budget")
        specs = parse_families(normalize_json_envelope(receipt["response"]), max_families=16, expected_count=count)
        require(not set(fingerprints) & {family_fingerprint(s) for s in specs}, "Generated family overlaps reserved confirmation")
        return seal({**result, "status": "generated", "families": specs})
    except (ValueError, TypeError, KeyError) as error:
        return seal({**result, "status": "invalid", "families": [], "error": str(error)[:500]})


def _pending(root, stage, reason, calls):
    value = seal({"version": VERSION, "status": "pending", "stage": stage, "reason": reason,
                  "accounting": calls.accounting(), "method_effect_evaluated": False,
                  "deployment_authorized": False})
    _write(root / ("pending_" + stage + ".json"), value)
    return value


def run(repo, output, parent_path, feedback_path, executor, *, workers=4, repeats=2,
        development_families=6, confirmation_families=12, provider="bigmodel", stop_after=None,
        solver_profile="legacy", solver_max_tokens=None):
    profile = SolverProfile.named(solver_profile, solver_max_tokens)
    require(type(repeats) is int and 1 <= repeats <= 3, "Pilot repeats must be 1..3")
    require(type(development_families) is int and 1 <= development_families <= 12, "Development family budget must be 1..12")
    require(type(confirmation_families) is int and 1 <= confirmation_families <= 16, "Confirmation family budget must be 1..16")
    require(stop_after in {None, "prepare", "learn"}, "Unknown stop stage")
    repo, root = checked_path(repo), checked_path(output)
    parent_record, bundle = _read(parent_path), _read(feedback_path)
    history = history_view(parent_record["text"], bundle)
    root.mkdir(parents=True, exist_ok=True)
    ping = executor.run({"ping.py": "def ping():\n    return True\n"}, "ping", "ping", [], {})
    _healthy(ping)
    require(ping.get("status") == "observed" and ping.get("actual") is True, "Isolated executor preflight failed")
    with CachedAPI(repo, root / "api", workers=workers, provider=provider,
                   stream=True, reasoning_effort="low", **profile.api_options()) as api:
        # Two planners, three generators, two updaters; two solver stages per
        # position. Identical cold prompts legitimately share cached responses.
        limit = 7 + 2 * 2 * development_families * 3 * repeats * 2 + 2 * confirmation_families * 3 * repeats * 3
        protocol = seal({"version": VERSION, "history_hash": history["record_hash"],
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(Path(__file__).parent.glob("*.py"))},
            "service": api.service, "executor": executor.identity,
            "transport": executor.transport_identity, "workers": workers, "repeats": repeats,
            "development_families_per_arm": development_families, "confirmation_families": confirmation_families,
            "request_limit": limit, "parent": "shared_empty_RuleSkill", "one_update_per_arm": True,
            "generation_token_cap": GENERATION_TOKEN_CAP,
            **({"solver_profile": profile.to_dict(), "updater_token_cap": 2048} if profile.enabled
               else {"solver_updater_token_cap": 2048}),
            "development_role_variants": ["preserve", "inplace", "unconstrained"],
            "history_is_hypothesis_source_not_evidence_for_new_parent": True,
            "feedback": "registered_public_checks_only_no_hidden_audit",
            "new_feedback_is_shadow_only_no_new_verifier_authorization": True,
            "research_feedback_arm": "pending_independent_calibration_not_run",
            "confirmation_exposure": "raw_same_conditions_no_success_based_routing",
            "generation_order": "both_development_pools_then_confirmation_before_any_solver_execution",
            "confirmation_generator_sees_development_specs_only_for_novelty_not_outcomes": True,
            "development_generators_do_not_see_confirmation_specs": True,
            "freeze_confirmation_before_learning": True, "final_access": False,
            "deployment_authorized": False, "cross_domain_claim": False})
        _write(root / "protocol.json", protocol)
        _write(root / "host_only/history.json", history)
        calls = CurriculumCalls(api, root / "model_budget", protocol["record_hash"], limit,
                                output_token_limits=profile.output_token_limits())
        goals = {}
        for mode in ("history", "outcome_blind"):
            goals[mode] = plan_goals(history, calls=calls, mode=mode)
            _write(root / "goals" / (mode + ".json"), goals[mode])
        if goals["history"]["status"] != "goals":
            return _pending(root, "goals", "Historical planner produced no admissible capability goal; no forced goal substitution.", calls)
        # Predeclared first-goal rule, not a choice based on downstream scores.
        # The full goal record is retained separately, not copied wholesale to
        # every generator or ever to the solver.
        selected = goals["history"]["goals"][0]
        goal_text = json.dumps({key: selected[key] for key in (
            "mechanism", "failure", "competing_hypotheses", "desired_observations", "observation_basis")},
            ensure_ascii=False, sort_keys=True)
        if len(goal_text.encode()) > 6000:
            return _pending(root, "goals", "First-goal generator projection exceeds budget; no silent truncation.", calls)
        _write(root / "selected_goal.json", seal({"selection": "first_model_ordered_goal_before_task_generation",
            "goal_id": selected["goal_id"], "generator_view": json.loads(goal_text),
            "coverage_limit": "List-pipeline adapter covers only a bounded slice of the proposed capability."}))
        generated = {}
        for arm in ARMS:
            generated[arm] = _generate(calls, count=development_families, condition=arm,
                goal=goal_text if arm == "targeted" else None)
            _write(root / "generation" / (arm + ".json"), generated[arm])
        if any(generated[a]["status"] != "generated" for a in ARMS):
            return _pending(root, "generation", "At least one development generator failed; all generations retained.", calls)
        # Only the confirmation generator sees development specifications for
        # exclusion. Development teachers never see confirmation specifications.
        # No solver execution or model outcome exists at this planning stage.
        exclusions = {family_fingerprint(spec): spec for arm in ARMS for spec in generated[arm]["families"]}
        generated["confirmation"] = _generate(calls, count=confirmation_families, condition="generic",
                                               excluded=list(exclusions.values()))
        _write(root / "generation/confirmation.json", generated["confirmation"])
        if generated["confirmation"]["status"] != "generated":
            return _pending(root, "generation", "Confirmation generation failed; no hand-filled replacement.", calls)
        pools = {name: item["families"] for name, item in generated.items()}
        try:
            registry = validate_family_pools(pools)
        except ValueError as error:
            return _pending(root, "partition", str(error), calls)
        _write(root / "family_registry.json", registry)
        unique = {family_fingerprint(spec): spec for specs in pools.values() for spec in specs}
        qualified = api.parallel(list(sorted(unique)), lambda key: screen_family(unique[key], executor, root / "qualification"), "curriculum qualification")
        _write(root / "qualification_summary.json", seal({"results": qualified}))
        if not all(item["status"] == "qualified" and item.get("formal_eligible") for item in qualified):
            return _pending(root, "qualification", "Not all preselected families passed isolated engineering qualification; no selection by solver performance.", calls)
        _write(root / "frozen_tasks.json", seal({"protocol_hash": protocol["record_hash"], "pools": pools,
            "registry_hash": registry["record_hash"], "qualification_hashes": [v["record_hash"] for v in qualified],
            "family_origin": "synthetic_generated_spec", "before_learning": True,
            "not_verifier_calibration": True}))
        print("TASKS_FROZEN", json.dumps({k: len(v) for k, v in pools.items()}), flush=True)
        if stop_after == "prepare":
            return seal({"status": "prepared", "accounting": calls.accounting(), "method_effect_evaluated": False})
        parent = RuleSkill("curriculum-shared-cold", ())
        _write(root / "cold_parent.json", seal({"skill": parent.to_dict(), "text": render_skill(parent)}))
        candidates, update_statuses = {}, {}
        for arm in ARMS:
            task_rows = [row for spec in pools[arm] for row in compile_family(spec, "development")]
            jobs = [(row, repeat, condition) for row in task_rows for repeat in range(repeats)
                    for condition in ("no_skill", "current")]
            def collect(job):
                row, repeat, condition = job
                key = digest([row["task"].content_hash, repeat, condition])
                pos = root / "development" / arm / key
                solved = solve_rule_condition(row, parent, condition, repeat, calls, executor, pos, exposure="raw",
                                              solver_profile=profile)
                cache = ExecutionCache(executor, pos / "feedback_execution", max_executions=16)
                report = validate_callable(row["public_task"], solved["artifact"], fixed_rubric(), cache)
                _write(pos / "feedback_report.json", report)
                return row, solved["artifact"], report, cache
            collected = api.parallel(jobs, collect, arm + " development")
            paired, records, identity = defaultdict(dict), {}, None
            for row, artifact, report, cache in collected:
                identity = cache.identity if identity is None else identity
                require(cache.identity == identity, "Mixed public execution identities")
                records.update(cache.records)
                records.update(cache.missing_records)
                paired[(row["public_task"].content_hash, artifact.repeat)][artifact.condition] = (row, artifact, report)
            entries = []
            for group in paired.values():
                require(set(group) == {"no_skill", "current"}, "Missing new-development pair")
                entries.append({"task": group["current"][0]["public_task"],
                    "artifacts": tuple(group[c][1] for c in ("no_skill", "current")),
                    "reports": tuple(group[c][2] for c in ("no_skill", "current"))})
            feedback = build_development_feedback(entries, parent_skill=render_skill(parent), rubric=fixed_rubric(),
                pipeline_hash=pipeline_hash(fixed_rubric(), collected[0][3]), execution_identity=identity,
                execution_records=tuple(records.values()), detail_limit=6)
            _write(root / "feedback" / (arm + ".json"), feedback)
            proposal = propose(calls, parent, feedback)
            _write(root / "updates" / (arm + ".json"), proposal)
            update = proposal.get("update", proposal)
            update_statuses[arm] = update["status"]
            candidate = RuleSkill.from_dict(update["candidate"]) if update.get("status") == "candidate" else parent
            candidates[arm] = candidate
            print("UPDATE", arm, update["status"], "rules", len(candidate.rules), flush=True)
        text_hashes = {"no_skill": digest(render_skill(parent)), **{a: digest(render_skill(s)) for a, s in candidates.items()}}
        canonical_texts = {}
        aliases = {arm: canonical_texts.setdefault(text_hash, arm) for arm, text_hash in text_hashes.items()}
        freeze = seal({"protocol_hash": protocol["record_hash"], "candidates": {a: s.to_dict() for a, s in candidates.items()},
            "update_statuses": update_statuses, "fallback_to_parent_for_non_candidates": True,
            "solver_text_aliases": aliases,
            "before_confirmation_execution": True, "deployment_authorized": False})
        _write(root / "frozen_candidates.json", freeze)
        if stop_after == "learn":
            return seal({"status": "learned_shadow_candidates", "accounting": calls.accounting(), "freeze_hash": freeze["record_hash"]})
        task_rows = [row for spec in pools["confirmation"] for row in compile_family(spec, "skill_confirmation")]
        skills = {"no_skill": parent, **candidates}
        jobs = [(row, repeat, arm) for row in task_rows for repeat in range(repeats) for arm in ("no_skill", *ARMS)]
        def confirm(job):
            row, repeat, arm = job
            key = digest([row["task"].content_hash, repeat, arm])
            pos = root / "confirmation" / key
            solved = solve_rule_condition(row, skills[arm], "no_skill" if arm == "no_skill" else "candidate",
                                          repeat, calls, executor, pos, exposure="raw", solver_profile=profile)
            audit = audit_artifact(row, solved["artifact"], executor, pos)
            value = seal({"family": row["host_only"]["family_fingerprint"], "role": row["host_only"]["role"],
                "repeat": repeat, "arm": arm, "status": audit["status"], "audit_hash": audit["record_hash"],
                "artifact_hash": solved["artifact"].content_hash, "update_status": update_statuses.get(arm),
                "revision_hash": solved["revision"]["record"]["record_hash"]})
            _write(pos / "result.json", value)
            return value
        rows = api.parallel(jobs, confirm, "shared synthetic confirmation")
        expected = {(family_fingerprint(s), role, r) for s in pools["confirmation"]
                    for role in ("preserve", "inplace", "unconstrained") for r in range(repeats)}
        result = summarize(rows, expected_positions=expected)
        summary = seal({"version": VERSION, "status": "completed_shadow_pilot", "result": result,
            "freeze_hash": freeze["record_hash"], "update_statuses": update_statuses,
            "solver_text_aliases": aliases,
            "accounting": calls.accounting(), "method_effect_evaluated": "descriptive_synthetic_only",
            "research_increment_evaluated": False, "deployment_authorized": False,
            "gaps": ["No independent Verifier Gate for this new task domain; feedback/update are shadow-only.",
                     "Outcome-blind goals are saved but do not form a third solver arm.",
                     "Shared DSL, syntactic family disjointness; not semantic independence or a public benchmark.",
                     "No true cross-domain, full surface-transfer, or unrelated-mechanism task adapter.",
                     "One learning history per arm; repetitions do not supply independent learning histories."]})
        _write(root / "confirmation_rows.json", seal({"rows": rows}))
        _write(root / "summary.json", summary)
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--historical-parent", type=Path, required=True)
    parser.add_argument("--historical-feedback", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--development-families", type=int, default=6)
    parser.add_argument("--confirmation-families", type=int, default=12)
    parser.add_argument("--stop-after", choices=("prepare", "learn"))
    parser.add_argument("--solver-profile", choices=("legacy", "reliable_v1"), default="legacy")
    parser.add_argument("--solver-max-tokens", type=int, help="Uniform public solver cap; reliable_v1 defaults to 4096")
    args = parser.parse_args(argv)
    executor = ExecutorPool(args.remote_repo, workers=min(args.workers, 6))
    try:
        result = run(args.repo, args.output, args.historical_parent, args.historical_feedback, executor,
            workers=args.workers, repeats=args.repeats, development_families=args.development_families,
            confirmation_families=args.confirmation_families, stop_after=args.stop_after,
            solver_profile=args.solver_profile, solver_max_tokens=args.solver_max_tokens)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
