"""Read-only post-hoc V12 process diagnostics after complete offline replay.

Prints score/metadata projections only. Never generates a Skill, selects a new
deployment, executes artifacts, publishes a file, or performs a new hypothesis
test. Initial/revision transitions refer ONLY to their public evaluations.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from collections import Counter, defaultdict
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.report_coevolution_v12 import _forbidden, _tree  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.coevolution_v12 import runtime, study  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

SCORE_KEYS = ("all_attempt_success", "oracle_available", "delivery_valid", "semantic_success")
KINDS = ("v12_skill_update", "v12_solve_generation", "v12_solve_revision")
EMPTY_SKILL_HASH = hashlib.sha256(b"").hexdigest()


def _score(raw):
    value = {k: raw[k] for k in SCORE_KEYS}
    if (type(value["all_attempt_success"]) is not int or value["all_attempt_success"] not in (0, 1)
            or type(value["oracle_available"]) is not bool or type(value["delivery_valid"]) is not bool):
        raise ValueError("Explicit binary/evaluability score metadata required")
    semantic = value["semantic_success"]
    if value["oracle_available"]:
        if (not value["delivery_valid"] or type(semantic) is not int or semantic not in (0, 1)
                or semantic != value["all_attempt_success"]):
            raise ValueError("Available score disagrees with semantic result")
    elif semantic is not None or value["all_attempt_success"] != 0:
        raise ValueError("Unavailable score cannot be labeled a semantic result")
    return value


def _mean(values):
    values = list(values)
    if not values:
        raise ValueError("Cannot summarize an empty task slice")
    return sum(values) / len(values)


def _slice_scores(rows):
    """Small paired development/selection slice: equal tasks then equal domains."""
    domains = sorted({r["domain"] for r in rows})
    by_domain = {d: _mean(r["score"]["all_attempt_success"] for r in rows if r["domain"] == d)
                 for d in domains}
    return {"macro": _mean(by_domain.values()), "by_domain": by_domain, "positions": len(rows),
            "unknown": sum(not r["score"]["oracle_available"] for r in rows),
            "unique_trajectories": len({tuple(r["request_hashes"]) for r in rows})}


def _solve_index(root):
    indexed, requests = {}, {}
    for path in sorted((root / "runtime/solves").glob("*.json")):
        raw = study.read(path)
        row = {k: raw[k] for k in ("task_id", "domain", "cluster_id", "phase", "skill_hash",
                                   "request_hashes", "stage_api_ok")}
        row["score"] = _score(raw["score"])
        row["record_hash"] = raw["record_hash"]
        if (len(row["request_hashes"]) != 2 or len(set(row["request_hashes"])) != 2
                or len(row["stage_api_ok"]) != 2 or any(type(v) is not bool for v in row["stage_api_ok"])):
            raise ValueError("Each trajectory must have two distinct ordered actual requests")
        key = tuple(row["request_hashes"])
        if raw["record_hash"] in indexed or key in requests:
            raise ValueError("Duplicate solve evidence cannot add process observations")
        indexed[raw["record_hash"]] = row
        requests[key] = row
    if not indexed:
        raise ValueError("Completed experiment has no solve evidence")
    return indexed, requests


def _paired_slice(left, right):
    if len(left) != len(right) or not left:
        raise ValueError("Nonempty complete paired slice required")
    if any((a["task_id"], a["domain"]) != (b["task_id"], b["domain"]) for a, b in zip(left, right)):
        raise ValueError("Paired task identities differ")
    before, after = _slice_scores(left), _slice_scores(right)
    return {"before": before, "after": after, "macro_delta": after["macro"] - before["macro"],
        "domain_deltas": {d: after["by_domain"][d] - before["by_domain"][d] for d in before["by_domain"]},
        "identical_paired_trajectories": sum(a["request_hashes"] == b["request_hashes"] for a, b in zip(left, right)),
        "paired_unknown": sum(not (a["score"]["oracle_available"] and b["score"]["oracle_available"])
                              for a, b in zip(left, right))}


def _learning_process(root, protocol, indexed, by_requests):
    expected = {f"h{h}-r{r}-{a}" for h in range(protocol["histories"])
                for r in range(protocol["rounds"]) for a in protocol["learning_arms"]}
    for directory in ("learning", "selection"):
        if {p.stem for p in (root / directory).glob("*.json")} != expected:
            raise ValueError("Learning/selection record grid is incomplete or orphaned")
    output, optimizer_requests = [], set()
    for key in sorted(expected):
        proposal = study.read(root / "learning" / (key + ".json"))
        selection = study.read(root / "selection" / (key + ".json"))
        identity = {k: proposal[k] for k in ("history", "round", "arm")}
        if (key != f"h{identity['history']}-r{identity['round']}-{identity['arm']}"
                or any(selection[k] != v for k, v in identity.items())):
            raise ValueError("Learning process identity mismatch")
        request_hash = proposal["request_hash"]
        receipt = json.loads((root / "api/calls" / (request_hash + ".json")).read_text())
        if (receipt["request_hash"] != request_hash or digest(receipt) != proposal["api_receipt_hash"]
                or receipt["request"]["kind"] != "v12_skill_update"):
            raise ValueError("Optimizer process receipt binding differs")
        observed = json.loads(receipt["request"]["user"])["observed_records"]
        if digest(observed) != proposal["evidence_hash"]:
            raise ValueError("Optimizer observed evidence digest differs")
        optimizer_requests.add(request_hash)
        grouped = {role: [] for role in ("no_skill", "current")}
        for record in observed:
            role = record["role"]
            if role not in grouped:
                raise ValueError("Unknown optimizer evidence role")
            solve = by_requests[tuple(record["request_hashes"])]
            skill = EMPTY_SKILL_HASH if role == "no_skill" else proposal["parent_hash"]
            if (solve["phase"] != "development" or solve["skill_hash"] != skill
                    or any(solve[k] != record[k] for k in ("task_id", "domain"))
                    or solve["score"] != _score(record["score"])):
                raise ValueError("Optimizer process data is not its development parent evidence")
            grouped[role].append(solve)
        training = _paired_slice(grouped["no_skill"], grouped["current"])
        selection_rows = [indexed[h] for h in selection["solver_records"]]
        if len(selection_rows) % 2:
            raise ValueError("Selection evidence must have two equal arms")
        mid = len(selection_rows) // 2
        old, new = selection_rows[:mid], selection_rows[mid:]
        if any(r["phase"] != "selection" or r["skill_hash"] != skill
               for rows, skill in ((old, selection["parent_hash"]), (new, selection["candidate_hash"])) for r in rows):
            raise ValueError("Selection records do not belong to their declared Skill")
        paired = _paired_slice(old, new)
        if (abs(paired["macro_delta"] - selection["macro_delta"]) > 1e-12
                or any(abs(v - selection["domain_differences"][d]) > 1e-12 for d, v in paired["domain_deltas"].items())):
            raise ValueError("Selection descriptive scores disagree with frozen decision")
        output.append({**identity, "valid": proposal["valid"], "changed": proposal["changed"],
            "skill_chars": len(proposal["skill"]), "proposal_status": proposal["reason"],
            "parent_current_training_vs_base": training,
            "selection_old_to_candidate": {**paired, "accepted": selection["accept"]},
            "training_is_parent_before_update_not_candidate_after_update": True})
    return output, optimizer_requests


def _hierarchy(rows):
    task_values = defaultdict(list)
    for row in rows:
        task_values[row["domain"], row["cluster_id"], row["task_id"]].append(row["score"]["all_attempt_success"])
    clusters = defaultdict(list)
    for (domain, cluster, _), values in task_values.items():
        clusters[domain, cluster].append(_mean(values))
    domains = defaultdict(list)
    for (domain, _), values in clusters.items():
        domains[domain].append(_mean(values))
    by_domain = {d: _mean(values) for d, values in sorted(domains.items())}
    return {"macro": _mean(by_domain.values()), "by_domain": by_domain}


def _failure_class(row):
    score = row["score"]
    if score["all_attempt_success"]:
        return "success"
    if not score["delivery_valid"]:
        return "delivery_api_unavailable" if not row["stage_api_ok"][1] else "delivery_invalid"
    if not score["oracle_available"]:
        return "delivered_oracle_unknown"
    return "oracle_evaluated_failure_not_pure_reasoning_attribution"


def _final(root, protocol, result, indexed):
    grid = study.read(root / "final_rows.json")
    if grid["record_hash"] != result["final_grid_hash"]:
        raise ValueError("Final diagnostic grid differs from the completed result")
    rows, positions = [], set()
    for raw in grid["rows"]:
        solve = indexed[raw["solver_record_hash"]]
        row = {k: raw[k] for k in ("task_id", "domain", "cluster_id", "history", "policy", "skill_hash")}
        row["score"] = _score(raw["score"])
        row["stage_api_ok"] = solve["stage_api_ok"]
        key = (row["task_id"], row["history"], row["policy"])
        if (key in positions or solve["phase"] != "final" or row["score"] != solve["score"]
                or raw["request_hashes"] != solve["request_hashes"]
                or any(row[k] != solve[k] for k in ("task_id", "domain", "cluster_id", "skill_hash"))):
            raise ValueError("Final row is not its unique actual final trajectory")
        positions.add(key)
        rows.append(row)
    base = {(r["task_id"], r["history"]): r for r in rows if r["policy"] == "no_skill"}
    policies = protocol["policies"]
    if not base or positions != {(t, h, p) for t, h in base for p in policies}:
        raise ValueError("Final policy comparison requires the complete shared task grid")
    base_summary = _hierarchy(list(base.values()))
    summaries, losses = {}, []
    for policy in policies:
        selected = [r for r in rows if r["policy"] == policy]
        hierarchy = _hierarchy(selected)
        deltas = {d: value - base_summary["by_domain"][d] for d, value in hierarchy["by_domain"].items()}
        counts = Counter()
        for row in selected:
            reference = base[row["task_id"], row["history"]]
            difference = row["score"]["all_attempt_success"] - reference["score"]["all_attempt_success"]
            counts["wins" if difference > 0 else "losses" if difference < 0 else "ties"] += 1
            counts["paired_unknown"] += not (row["score"]["oracle_available"] and reference["score"]["oracle_available"])
            if difference < 0:
                losses.append({"history": row["history"], "policy": policy, "task_id": row["task_id"],
                    "domain": row["domain"], "failure_class": _failure_class(row)})
        summaries[policy] = {**hierarchy, "worst_domain_success": min(hierarchy["by_domain"].values()),
            "macro_delta_vs_base": hierarchy["macro"] - base_summary["macro"], "domain_deltas_vs_base": deltas,
            "worst_domain_delta_vs_base": min(deltas.values()), "maximum_domain_drop_vs_base": max(0, -min(deltas.values())),
            "paired_counts": {k: counts[k] for k in ("wins", "losses", "ties", "paired_unknown")},
            "failure_classes": dict(sorted(Counter(_failure_class(r) for r in selected).items())),
            "selected_diagnostic_only": policy.startswith("selected_")}
        if protocol["design"] == "formal":
            primary = result["summary"]["policy_summary"][policy]
            if (abs(hierarchy["macro"] - primary["macro_all_attempt_success"]) > 1e-12
                    or any(abs(v - primary["by_domain"][d]["cluster_equal_all_attempt_success"]) > 1e-12
                           for d, v in hierarchy["by_domain"].items())):
                raise ValueError("Descriptive hierarchy differs from the frozen primary summary")
    return {"policies": summaries, "loss_positions_vs_no_skill": losses,
            "loss_positions_not_independent_trials": True,
            "loss_details_limited_to_ids_domain_and_score_failure_class": True}


def _public_state(score):
    return "unavailable" if not score["oracle_available"] else "pass" if score["semantic_success"] else "fail"


def _public_transitions(root, indexed):
    groups = defaultdict(Counter)
    for solve in indexed.values():
        scores = []
        for stage, request_hash in zip(("generation", "revision"), solve["request_hashes"]):
            row = study.read(root / "runtime/stages" / (request_hash + ".json"))
            if row["stage"] != stage or row["receipt"]["request_hash"] != request_hash:
                raise ValueError("Public stage ordering or receipt differs")
            scores.append(_score(row["public_score"]))
        transition = _public_state(scores[0]) + "_to_" + _public_state(scores[1])
        binary = f"{scores[0]['all_attempt_success']}_to_{scores[1]['all_attempt_success']}"
        for group in ("all", solve["phase"], solve["phase"] + "/" + solve["domain"]):
            groups[group]["trajectories"] += 1
            groups[group][transition] += 1
            groups[group]["all_attempt_" + binary] += 1
    return {"unique_trajectories": len(indexed), "by_phase_and_domain": {k: dict(sorted(v.items())) for k, v in sorted(groups.items())},
            "both_scores_public_only": True, "not_initial_to_final_hidden_gain": True,
            "skill_causal_contribution_identified": False,
            "identical_receipt_aliases_counted_once": True}


def _api_costs(root, result, expected_requests):
    paths = sorted((root / "api/calls").glob("*.json"))
    if {p.stem for p in paths} != expected_requests:
        raise ValueError("Diagnostic API accounting has orphan/missing requests")
    costs = {kind: Counter() for kind in KINDS}
    for path in paths:
        row = json.loads(path.read_text())
        kind = row["request"]["kind"]
        if kind not in costs or row["request_hash"] != path.stem:
            raise ValueError("Unknown request kind or filename binding")
        count = costs[kind]
        count["unique_logical_calls"] += 1
        count["successful_calls"] += row["ok"]
        count["terminal_errors"] += not row["ok"]
        count["http_attempts"] += row["http_attempt_count"]
        count["missing_usage_calls"] += not row.get("usage")
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = row.get("usage", {}).get(key, 0) or 0
            if type(value) is not int or value < 0:
                raise ValueError("Usage must be nonnegative recorded integer counters")
            count[key] += value
    fields = ("unique_logical_calls", "successful_calls", "terminal_errors", "http_attempts",
              "prompt_tokens", "completion_tokens", "total_tokens", "missing_usage_calls")
    totals = {key: sum(count[key] for count in costs.values()) for key in fields}
    ledger_names = {"unique_logical_calls": "cached_logical_calls", "http_attempts": "http_attempts_from_cached_records"}
    if any(totals[key] != result["ledger"][ledger_names.get(key, key)] for key in fields):
        raise ValueError("Unique API cost totals disagree with the closed ledger")
    return {"by_kind": {kind: {key: count[key] for key in fields} for kind, count in costs.items()},
            "totals": totals, "shared_policy_and_history_requests_counted_once": True,
            "usage_is_not_an_invoice": True, "unreturned_attempt_usage_unknown": True}


def diagnose(output, *, repo=REPO):
    repo = Path(repo).resolve()
    root = study.safe_root(repo, output)
    if not (root / "results.json").is_file() or not (root / ".run.lock").is_file():
        raise ValueError("Diagnostics require completed evidence and its pre-existing run lock")
    with (root / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        before = _tree(root)
        protocol, result = study.read(root / "protocol.json"), study.read(root / "results.json")
        if result.get("complete") is not True or result.get("protocol_hash") != protocol["record_hash"]:
            raise ValueError("Completed result/protocol binding is required")
        replay = study.Study(repo, root, design=protocol["design"], api_factory=_forbidden)
        if not replay.complete:
            raise ValueError("Diagnostics cannot resume an incomplete experiment")
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime.legacy, "evaluate", _forbidden))
            stack.enter_context(patch.object(study.OfflineAPI, "call", _forbidden))
            stack.enter_context(redirect_stdout(StringIO()))
            replayed = replay.run()
        if replayed != result or study.read(root / "results.json") != result or _tree(root) != before:
            raise ValueError("Completed diagnostic replay differs or changed evidence")
        indexed, by_requests = _solve_index(root)
        process, optimizer_requests = _learning_process(root, protocol, indexed, by_requests)
        aggregate = {"proposals": len(process), "valid": sum(p["valid"] for p in process),
                     "text_changes": sum(p["changed"] for p in process),
                     "selection_acceptances": sum(p["selection_old_to_candidate"]["accepted"] for p in process)}
        if aggregate != result["learning"]:
            raise ValueError("Process proposal summary disagrees with the completed experiment")
        solver_requests = {h for row in indexed.values() for h in row["request_hashes"]}
        if solver_requests & optimizer_requests:
            raise ValueError("Optimizer and solver requests cannot alias")
        diagnostic = {"version": "v12-completed-posthoc-process-diagnostics-v1", "design": protocol["design"],
            "posthoc_descriptive_only": True, "new_primary_tests": 0, "new_selection_decisions": 0,
            "smoke_not_scientific_inference": protocol["design"] == "smoke",
            "result_hash": result["record_hash"], "protocol_hash": protocol["record_hash"],
            "learning_process": process, "learning_aggregate": aggregate,
            "final": _final(root, protocol, result, indexed),
            "public_revision_transitions": _public_transitions(root, indexed),
            "api_costs": _api_costs(root, result, solver_requests | optimizer_requests),
            "interpretation": ["训练得分是更新前父 Skill 的表现，不是刚生成候选的训练提升。",
                "selection 是冻结的同开发域小样本诊断，不能替代 raw 主比较或跨域安全认证。",
                "生成到修订的变化仅来自 PUBLIC 评分，不是隐藏最终题的因果提升。",
                "已可评的失败可能含运行异常；API/交付/不可评损失不直接证明 Skill 推理有害。",
                "各历史、策略与变体可能共享实际请求；消耗和公开修订统计按唯一实际轨迹去重。"],
            "audit": {"verified_run_files": len(before), "model_api_calls": 0, "native_executions": 0,
                      "files_written": 0, "run_files_unchanged": True}}
        if study.source_hashes(repo) != protocol["source_hashes"] or _tree(root) != before:
            raise ValueError("Frozen sources/evidence changed during diagnostics")
        return seal(diagnostic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(diagnose(args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
