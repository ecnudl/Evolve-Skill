"""Fixed paired comparisons for the synthetic MVP, with no API/model imports.

Default: read artifacts and print JSON only. ``--report`` additionally writes
``cross_domain_analysis.json`` in the explicitly selected experiment directory.
No coverage level or policy is selected using test outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from numbers import Real
from pathlib import Path

import numpy as np

DEFAULT_OUT = Path("outputs/cross_domain/scope_mvp_gpt55_20260907")
COVERAGES = (10, 25, 50, 75)
COMPARISONS = (
    ("H1_safe_vs_unconditional", "H1", "safe_mechanism", "unconditional"),
    ("H1_safe_vs_source_gate", "H1", "safe_mechanism", "source_gate"),
    *((f"H2_matched_{coverage}_vs_{other}", "H2", f"matched_{coverage}_mechanism", f"matched_{coverage}_{other}")
      for coverage in COVERAGES for other in ("domain", "shuffled")),
)
STRATA = {
    "overall": None,
    "non_source": ("spreadsheet", "rule_reasoning"),
    "spreadsheet": ("spreadsheet",),
    "rule_reasoning": ("rule_reasoning",),
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _indexed_repeats(repeats, label):
    indexes = []
    domains = {}
    for repeat_i, rows in enumerate(repeats):
        index = {}
        for row in rows:
            task_id, domain = row.get("id"), row.get("domain")
            if not isinstance(task_id, str) or not task_id or not isinstance(domain, str) or not domain:
                raise ValueError(f"{label} repeat {repeat_i}: each row needs nonempty id and domain")
            if task_id in index:
                raise ValueError(f"{label} repeat {repeat_i}: duplicate task id {task_id}")
            if task_id in domains and domains[task_id] != domain:
                raise ValueError(f"Domain changed across repeats for {task_id}")
            for field in ("candidate", "applied"):
                value = row.get(field)
                if not isinstance(value, Real) or not math.isfinite(value) or value not in (0, 1):
                    raise ValueError(f"{label} repeat {repeat_i}: {field} must be finite binary data")
            domains[task_id] = domain
            index[task_id] = row
        indexes.append(index)
    return indexes, domains


def compare_policies(left_repeats, right_repeats, *, domains=None, resamples=4000, seed=42):
    """Compare LEFT minus RIGHT on the common IDs of every policy and repeat.

    First average each original task's paired difference across generation
    repeats; then bootstrap those task means. Repeats are never independent
    samples. Coverage uses the same complete-case population as accuracy.
    """
    if not left_repeats or len(left_repeats) != len(right_repeats):
        raise ValueError("Policies must have the same positive number of aligned repeats")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ValueError("resamples must be a positive integer")
    left, left_domains = _indexed_repeats(left_repeats, "left")
    right, right_domains = _indexed_repeats(right_repeats, "right")
    for task_id in left_domains.keys() & right_domains.keys():
        if left_domains[task_id] != right_domains[task_id]:
            raise ValueError(f"Domain differs between policies for {task_id}")
    for left_index, right_index in zip(left, right):
        for task_id in left_index.keys() & right_index.keys():
            for field in ("baseline", "current"):
                if field in left_index[task_id] and field in right_index[task_id]:
                    if left_index[task_id][field] != right_index[task_id][field]:
                        raise ValueError(f"Policies do not share the same {field} draw for {task_id}")
    all_domains = {**left_domains, **right_domains}
    permitted = set(domains) if domains is not None else None
    observed = {task_id for task_id, domain in all_domains.items() if permitted is None or domain in permitted}
    common = set.intersection(*(set(index) for index in left + right)) & observed
    ids = sorted(common)
    n_repeats = len(left)
    result = {
        "n_unique_tasks": len(ids), "n_generation_repeats": n_repeats,
        "n_paired_task_repeat_observations": len(ids) * n_repeats,
        "n_observed_in_any_policy_repeat": len(observed),
        "n_excluded_from_observed_union": len(observed - common),
        "left_em": None, "right_em": None, "difference_pp": None,
        "difference_ci95_pp": [None, None],
        "policy_coverage": {"left": None, "right": None},
    }
    if not ids:
        return result
    values = {}
    coverage = {}
    for label, indexes in (("left", left), ("right", right)):
        values[label] = np.array([[index[task_id]["candidate"] for index in indexes] for task_id in ids], dtype=float)
        coverage[label] = float(np.mean([[index[task_id]["applied"] for index in indexes] for task_id in ids]))
    task_differences = (values["left"] - values["right"]).mean(axis=1)
    rng = np.random.default_rng(seed)
    bootstrap = np.empty(resamples)
    for start in range(0, resamples, 256):
        count = min(256, resamples - start)
        sampled_ids = rng.integers(0, len(ids), size=(count, len(ids)))
        bootstrap[start:start + count] = task_differences[sampled_ids].mean(axis=1)
    result.update({
        "left_em": float(values["left"].mean()), "right_em": float(values["right"].mean()),
        "difference_pp": 100 * float(task_differences.mean()),
        "difference_ci95_pp": [100 * float(value) for value in np.quantile(bootstrap, [0.025, 0.975])],
        "policy_coverage": coverage,
    })
    return result


def analyze_run(out: Path) -> dict:
    """Read only frozen-policy, summary, and per-policy paired outcome artifacts."""
    out = Path(out).resolve()
    summary = _read_json(out / "summary.json")
    frozen = _read_json(out / "frozen_policies.json")
    protocol = summary["protocol"]
    if frozen.get("protocol_hash") != _digest(protocol):
        raise ValueError("Summary protocol does not match the frozen experiment")
    if set(summary["tracks"]) != set(frozen["tracks"]):
        raise ValueError("Summary and frozen policy tracks do not match")
    n_repeats = protocol["test_repeats"]
    if isinstance(n_repeats, bool) or not isinstance(n_repeats, int) or n_repeats < 1:
        raise ValueError("Protocol test_repeats must be a positive integer")
    policy_names = sorted({policy for _, _, left, right in COMPARISONS for policy in (left, right)})
    tracks = {}
    for skill_id in sorted(frozen["tracks"]):
        if not isinstance(skill_id, str) or not skill_id or Path(skill_id).name != skill_id or skill_id in {".", ".."} or "\\" in skill_id:
            raise ValueError("Unsafe skill identifier in frozen artifact")
        skill = frozen["tracks"][skill_id]["skill"]
        if skill["source_domain"] != "coding":
            raise ValueError("This fixed analysis preregisters coding as source; do not relabel test domains")
        missing = set(policy_names) - summary["tracks"][skill_id].keys()
        if missing:
            raise ValueError(f"Missing preregistered policies in summary: {sorted(missing)}")
        outcomes = {
            name: [_read_json(out / "policy_outcomes" / skill_id / f"{name}_r{repeat}.json")
                   for repeat in range(n_repeats)]
            for name in policy_names
        }
        comparisons = {}
        for comparison_id, hypothesis, left, right in COMPARISONS:
            comparisons[comparison_id] = {
                "hypothesis": hypothesis, "left_policy": left, "right_policy": right,
                "strata": {name: compare_policies(outcomes[left], outcomes[right], domains=domains)
                           for name, domains in STRATA.items()},
            }
        tracks[skill_id] = {"source_domain": skill["source_domain"], "mechanism": skill["mechanism"],
                            "comparisons": comparisons}
    return {
        "analysis_version": "cross-domain-mvp-paired-v1", "out_directory": str(out),
        "protocol_hash": frozen["protocol_hash"], "candidates_hash": frozen.get("candidates_hash"),
        "frozen_code_hashes": frozen.get("code_hashes"),
        "evaluation_type": summary.get("evaluation_type"),
        "comparison_direction": "left minus right; positive difference favors left",
        "bootstrap": {"resamples": 4000, "seed": 42, "interval": "95% percentile",
                      "cluster": "original task after averaging aligned generation repeats"},
        "fixed_coverage_percentages": list(COVERAGES),
        "comparison_plan": [{"id": cid, "hypothesis": hypothesis, "left_policy": left, "right_policy": right}
                            for cid, hypothesis, left, right in COMPARISONS],
        "tracks": tracks,
        "limitations": [
            "Shared-draw offline policy replay, not independent online policy trials.",
            "All listed comparisons and coverage fractions are fixed in code; none is selected using test outcomes.",
            "Per-task bootstrap intervals do not include training-seed or fitted-policy uncertainty.",
            "Intervals are not adjusted for multiple comparisons; report every preregistered comparison.",
            "Coverage is empirical on the common complete-case subset; missing calls can alter matched-coverage counts.",
            "Observed-union exclusion counts cannot count tasks absent from every policy/repeat; consult original summary API/missing counts.",
            "Synthetic task diagnostics are not public-benchmark or deployment-safety evidence.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Experiment directory; relative paths are repository-relative")
    parser.add_argument("--report", action="store_true", help="Also write OUT/cross_domain_analysis.json; otherwise stdout only")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    out = args.out if args.out.is_absolute() else repo / args.out
    result = analyze_run(out)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.report:
        (out / "cross_domain_analysis.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
