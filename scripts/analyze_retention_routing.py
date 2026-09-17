"""Fixed paired analysis for the mature-Skill routing diagnostic; no API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

POPULATIONS = ("source", "cross_domain_positive", "source_appearance_near_miss", "cross_domain_near_miss", "unrelated", "overall_diagnostic")
DEPLOY_PAIRS = (("unconditional", "base"), ("mechanism", "base"), ("domain", "base"),
                ("mechanism", "unconditional"), ("mechanism", "domain"))
MATCHED_PAIRS = (("mechanism_topk", "domain_topk"), ("mechanism_topk", "hash_random_topk"))
BOOTSTRAP_N = 5000
SEED = 20260908


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _population(rows, name):
    if name == "source":
        return [r for r in rows if r["origin"] == "source"]
    if name == "cross_domain_positive":
        return [r for r in rows if r["origin"] == "control" and r["group"] == "positive"]
    if name in {"source_appearance_near_miss", "cross_domain_near_miss"}:
        return [r for r in rows if r["origin"] == "control" and r["group"] == "near_miss"
                and (r["domain"] == "searchqa") == (name == "source_appearance_near_miss")]
    if name == "unrelated":
        return [r for r in rows if r["origin"] == "control" and r["group"] == "unrelated"]
    if name == "overall_diagnostic":
        return rows
    raise ValueError("Unknown preregistered population")


def paired_comparison(rows, left_mask, right_mask, *, bootstrap_n=BOOTSTRAP_N, seed=SEED):
    """Whole-task pairing; filtering cannot differ across the two methods."""
    if bootstrap_n < 1:
        raise ValueError("Positive bootstrap count required")
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Repeated IDs are not independent tasks")
    left, right = set(left_mask), set(right_mask)
    good = []
    for row in rows:
        if not isinstance(row["base_ok"], bool) or not isinstance(row["full_ok"], bool):
            raise ValueError("Explicit API success booleans required")
        if row["base_ok"] and row["full_ok"]:
            if any(isinstance(row[k], bool) or not isinstance(row[k], (int, float))
                   or not math.isfinite(row[k]) or row[k] not in (0, 1) for k in ("base", "full")):
                raise ValueError("Successful target scores must be finite binary numbers")
            good.append(row)
    left_scores = np.array([r["full"] if r["id"] in left else r["base"] for r in good], dtype=float)
    right_scores = np.array([r["full"] if r["id"] in right else r["base"] for r in good], dtype=float)
    delta = left_scores - right_scores
    if good:
        rng = np.random.default_rng(seed)
        samples = np.array([delta[rng.integers(0, len(good), len(good))].mean() for _ in range(bootstrap_n)])
        ci = np.quantile(samples, [.025, .975]).tolist()
    else:
        ci = [None, None]
    return {
        "n_expected": len(rows), "n_independent_common_tasks": len(good),
        "excluded_api_ids": [r["id"] for r in rows if not (r["base_ok"] and r["full_ok"])],
        "left_enabled_common": sum(r["id"] in left for r in good),
        "right_enabled_common": sum(r["id"] in right for r in good),
        "left_em": float(left_scores.mean()) if good else None,
        "right_em": float(right_scores.mean()) if good else None,
        "delta_em_left_minus_right": float(delta.mean()) if good else None,
        "paired_bootstrap95": ci,
        "left_better_ids": [r["id"] for r, d in zip(good, delta) if d > 0],
        "left_worse_ids": [r["id"] for r, d in zip(good, delta) if d < 0],
        "identical_observed_policy_masks": all((r["id"] in left) == (r["id"] in right) for r in good) if good else None,
    }


def _plan(root):
    protocol = _read(root / "routing_protocol.json")
    return {
        "analysis_version": "fixed-retention-paired-v1",
        "analysis_script_sha256": _hash(Path(__file__).resolve()),
        "routing_protocol_sha256": _hash(root / "routing_protocol.json"),
        "source_protocol_sha256": protocol["source_protocol_sha256"],
        "populations": list(POPULATIONS), "deployment_pairs_left_minus_right": list(map(list, DEPLOY_PAIRS)),
        "matched_pairs_left_minus_right": list(map(list, MATCHED_PAIRS)),
        "matched_scope": "Every input-only matched mask in the frozen protocol, never a selected winner",
        "bootstrap": {"resamples": BOOTSTRAP_N, "seed": SEED, "unit": "independent original task", "confidence": .95},
        "notes": [
            "Source observations are the SAME observations as experiment C, not an independent replication.",
            "Do not pool public-source QA and synthetic controls as the main success claim; overall is diagnostic only.",
            "All methods share the same complete Base/full API-success intersection in each population.",
            "Equal matched coverage is assigned before outcomes; API exclusion may unbalance observed coverage.",
            "Matched K is equal over the full preregistered population, not necessarily within source/domain/group subsets even with no API exclusions.",
            "Source net-gain retention is a point ratio in the routing report, undefined if full net gain is nonpositive.",
            "Intervals have no multiple-comparison, model-seed or service-drift adjustment, and certify no safety.",
            "A zero interval for identical masks describes identical replay policies, not unknown-task safety.",
        ],
    }


def freeze_plan(root):
    from skillopt.scope_evolution_v2.source_data import write_immutable_json

    path = root / "paired_analysis_plan_before_holdout.json"
    value = _plan(root)
    if path.exists():
        if _read(path) != value:
            raise ValueError("Analysis plan/code changed")
        return value
    protocol = _read(root / "routing_protocol.json")
    source = Path(protocol["settings"]["source_dir"])
    if (root / "routes/holdout.json").exists() or (root / "datasets/source_holdout.json").exists():
        raise ValueError("Freeze the analysis before routing/materializing holdout")
    if (source / "datasets/holdout.json").exists():
        raise ValueError("Source holdout has already been opened")
    if any((source / f"searchqa_rollouts/holdout/{a}/results.jsonl").exists()
           or (root / f"controls/holdout/{a}.json").exists() for a in ("base", "full")):
        raise ValueError("Held-out outcomes already exist")
    write_immutable_json(path, value)
    return value


def analyze(root, split="holdout"):
    from skillopt.scope_evolution_v2 import retention_routing as routing

    if split not in {"calibration", "holdout"}:
        raise ValueError("Unsupported split")
    plan = _read(root / "paired_analysis_plan_before_holdout.json")
    if plan != _plan(root):
        raise ValueError("Analysis script or frozen protocol differs from the pre-holdout plan")
    protocol = _read(root / "routing_protocol.json")
    routing._validate(REPO, root, protocol)
    routing._verify_source_freeze(REPO, protocol)
    if split == "holdout" or (root / "routing_frozen.json").exists():
        routing._verify_freeze(REPO, root, protocol)
    seals = routing._load_route(REPO, root, protocol, split)
    rows = routing._paired_rows(REPO, root, protocol, split)
    if {r["id"] for r in rows} != {r["id"] for r in seals["routes"]}:
        raise ValueError("Routes and target IDs differ")
    result = {"analysis_plan": plan, "split": split, "execution_mode": protocol["settings"]["execution_mode"],
              "deployment": {}, "matched_coverage_diagnostic": []}
    for name in POPULATIONS:
        selected = _population(rows, name)
        result["deployment"][name] = {
            f"{left}_minus_{right}": paired_comparison(selected, seals["deployment"][left], seals["deployment"][right])
            for left, right in DEPLOY_PAIRS
        }
    for item in seals["matched_coverage_diagnostic"]:
        lengths = {len(mask) for mask in item["enabled"].values()}
        if lengths != {item["k"]}:
            raise ValueError("Assigned matched masks do not have equal coverage")
        result["matched_coverage_diagnostic"].append({
            "mechanism_score_threshold": item["mechanism_score_threshold"], "assigned_k": item["k"], "assigned_n": item["n"],
            "populations": {name: {
                f"{left}_minus_{right}": paired_comparison(_population(rows, name), item["enabled"][left], item["enabled"][right])
                for left, right in MATCHED_PAIRS
            } for name in POPULATIONS},
        })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=Path("outputs/scope_evolution_v2/retention_routing_gpt55_20260908"))
    parser.add_argument("--split", choices=("calibration", "holdout"), default="holdout")
    parser.add_argument("--freeze-plan", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = (REPO / args.run_dir).resolve()
    if (REPO / "outputs").resolve() not in root.parents:
        raise ValueError("Expected an experiment output directory")
    if args.freeze_plan:
        result = freeze_plan(root)
    else:
        result = analyze(root, args.split)
        if args.write:
            from skillopt.scope_evolution_v2.source_data import write_immutable_json
            write_immutable_json(root / f"paired_{args.split}_analysis.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
