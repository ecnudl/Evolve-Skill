"""Host-only development-panel diagnostics before an expensive verifier study.

This is not a dataset selector, a statistical power calculation, or a Skill
Gate. Held-out outcomes never influence readiness. No model or artifact runs.
Declared family/project identities still require source-level human review.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import digest, write_immutable_json

from .models import require
from .stage2 import _manifest, _path, import_pool

CONDITIONS = ("no_skill", "current", "candidate")


def checked_path(path):
    path = _path(path)
    require(".." not in path.parts, "Parent traversal in panel paths is unsupported")
    return path


@dataclass(frozen=True)
class PilotRequirements:
    """Planning defaults, NOT sufficient sample sizes for a research claim."""
    min_tasks: int = 64
    min_families: int = 16
    min_projects: int = 4
    min_error_families: int = 4
    min_audit_coverage: float = 0.75

    def __post_init__(self):
        for name in ("min_tasks", "min_families", "min_projects", "min_error_families"):
            require(type(getattr(self, name)) is int and getattr(self, name) > 0,
                    "Positive pilot count required")
        require(type(self.min_audit_coverage) in {int, float}
                and 0 <= self.min_audit_coverage <= 1, "Invalid audit coverage requirement")


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _status(row, artifact):
    # Missing delivery is uncertainty, never a semantic error or a removed row.
    if artifact.availability != "available":
        return "unknown"
    values = list(row["audit"][artifact.content_hash].values())
    if "fail" in values:
        return "fail"
    return "pass" if values and all(v == "pass" for v in values) else "unknown"


def _counts(rows):
    artifacts = [a for row in rows for a in row["artifacts"]]
    contracts = [r["task"].contract for r in rows]
    return {"task_repeat_triplets": len(rows), "artifact_positions": len(artifacts),
            "original_tasks": len({c.original_task_id for c in contracts}),
            "declared_families": len({c.family_id for c in contracts}),
            "declared_projects": len({c.project_id for c in contracts}),
            "unique_task_artifact_contents": len({(a.task_hash, a.artifact_hash) for a in artifacts
                                                   if a.availability == "available"}),
            "declared_source_references": len({(a.source_ref, a.source_hash) for a in artifacts}),
            "availability": dict(sorted(Counter(a.availability for a in artifacts).items()))}


def _development_summary(rows):
    outcomes = {condition: Counter() for condition in CONDITIONS}
    paired = {"candidate_vs_no_skill": Counter(), "candidate_vs_current": Counter()}
    categories, error_families, discordant_families = Counter(), set(), set()
    family_rates = defaultdict(lambda: defaultdict(list))
    pair_families = {name: defaultdict(list) for name in paired}
    same_contents = same_skill = 0
    skill_versions = defaultdict(set)
    for row in rows:
        contract = row["task"].contract
        artifacts = {a.condition: a for a in row["artifacts"]}
        h = {condition: _status(row, artifacts[condition]) for condition in CONDITIONS}
        for condition, value in h.items():
            outcomes[condition][value] += 1
            family_rates[condition][contract.family_id].append(value == "pass")
            skill_versions[(artifacts[condition].repeat, condition)].add(artifacts[condition].skill_hash)
            if value == "fail":
                error_families.add(contract.family_id)
        if all(a.availability == "available" for a in artifacts.values()):
            same_contents += len({a.artifact_hash for a in artifacts.values()}) == 1
        same_skill += artifacts["current"].skill_hash == artifacts["candidate"].skill_hash
        for comparator in ("no_skill", "current"):
            before, after = h[comparator], h["candidate"]
            direction = ("unknown" if "unknown" in (before, after) else
                         "tie" if before == after else "win" if after == "pass" else "loss")
            name = "candidate_vs_" + comparator
            paired[name][direction] += 1
            pair_families[name][contract.family_id].append(direction)
            if direction in {"win", "loss"}:
                discordant_families.add(contract.family_id)
        category = ("uncertain" if "unknown" in h.values() else
                    "skill_related_regression" if h["candidate"] == "fail" and "pass" in (h["no_skill"], h["current"]) else
                    "skill_repair" if h["candidate"] == "pass" and "fail" in (h["no_skill"], h["current"]) else
                    "shared_error" if all(v == "fail" for v in h.values()) else "shared_success")
        categories[category] += 1
    summaries = {}
    for condition, counts in outcomes.items():
        total = sum(counts.values())
        summaries[condition] = {
            "audit_outcomes": {key: counts[key] for key in ("pass", "fail", "unknown")},
            "all_attempt_success": _ratio(counts["pass"], total),
            "audit_coverage": _ratio(counts["pass"] + counts["fail"], total),
            "family_equal_success": (sum(sum(v) / len(v) for v in family_rates[condition].values())
                                     / len(family_rates[condition]) if family_rates[condition] else None),
        }
    return {**_counts(rows), "conditions": summaries,
            "paired_task_repeat_outcomes": {k: {s: v[s] for s in ("win", "loss", "tie", "unknown")}
                                            for k, v in paired.items()},
            "paired_family_outcomes": {k: {family: dict(sorted(Counter(values).items()))
                                           for family, values in sorted(families.items())}
                                       for k, families in pair_families.items()},
            "paired_categories": dict(sorted(categories.items())),
            "audited_error_families": len(error_families),
            "discordant_families": len(discordant_families),
            "same_delivered_content_triplets": same_contents,
            "unchanged_current_candidate_skill_triplets": same_skill,
            "within_repeat_condition_skill_version_counts": [
                {"repeat": repeat, "condition": condition, "versions": len(values)}
                for (repeat, condition), values in sorted(skill_versions.items())]}


def inspect_pool(pool, requirements=None):
    """Summarize development H only; held-out data contribute metadata counts.

    Never export this host report as a model view. Thresholds do not select or
    remove tasks, and cannot authorize tuning on calibration/audit outcomes.
    """
    manifest = _manifest(pool)
    requirements = requirements or PilotRequirements()
    require(type(requirements) is PilotRequirements, "Typed pilot requirements required")
    development = [r for r in pool if r["task"].contract.partition == "development"]
    natural = [r for r in development if all(manifest.get(a.content_hash).formal_eligible for a in r["artifacts"])]
    diagnostic = [r for r in development if r not in natural]
    natural_summary = _development_summary(natural)
    reasons, warnings = [], []
    for metric, threshold in (("original_tasks", requirements.min_tasks),
                              ("declared_families", requirements.min_families),
                              ("declared_projects", requirements.min_projects),
                              ("audited_error_families", requirements.min_error_families)):
        if natural_summary[metric] < threshold:
            reasons.append("insufficient_natural_" + metric)
    for condition in CONDITIONS:
        coverage = natural_summary["conditions"][condition]["audit_coverage"]["value"]
        if coverage is None or coverage < requirements.min_audit_coverage:
            reasons.append("insufficient_audit_coverage_" + condition)
    if not natural_summary["discordant_families"]:
        warnings.append("no_observed_natural_paired_difference_for_skill_decision_study")
    if any(v["versions"] > 1 for v in natural_summary["within_repeat_condition_skill_version_counts"]):
        reasons.append("skill_changes_across_tasks_within_repeat_condition_review_collection_protocol")
    if natural_summary["task_repeat_triplets"] and natural_summary["unchanged_current_candidate_skill_triplets"]:
        warnings.append("some_candidate_skills_equal_current_not_independent_evolution")
    base = natural_summary["conditions"]["no_skill"]["all_attempt_success"]["value"]
    if base is not None and base >= 0.95:
        warnings.append("base_ceiling_signal_use_for_retention_not_only_positive_learning")
    return seal({"version": "development-panel-diagnostics-v1", "purpose": "host_development_diagnostic_only",
        "requirements": asdict(requirements), "requirements_are_power_guarantee": False,
        "source_manifest_hash": manifest.to_dict()["manifest_hash"],
        "development_data_hash": digest(sorted([
            {"task_hash": r["task"].content_hash, "artifacts": sorted(a.content_hash for a in r["artifacts"]),
             "audit": r["audit"], "near_miss": r["near_miss"]} for r in development], key=lambda r: (r["task_hash"], r["artifacts"]))),
        "partition_metadata": {purpose: _counts([r for r in pool if r["task"].contract.partition == purpose])
                               for purpose in sorted({r["task"].contract.partition for r in pool})},
        "development": {"natural_complete_triplets": natural_summary,
                        "diagnostic_only_triplets": _development_summary(diagnostic)},
        "readiness": {"status": "pending" if reasons else "ready_for_pilot_review", "reasons": reasons,
                      "warnings": warnings, "skill_or_verifier_admission_authority": False},
        "limitations": ["Declared families/projects are not independently certified.",
                        "Repeated tasks, shared sources and check inputs are not new independent tasks.",
                        "No selection by scores; no held-out audit labels enter this report.",
                        "Skill-related paired differences are observations, not proof of causal Skill effects.",
                        "Host-provided H may be incomplete; provenance hashes do not authenticate truth.",
                        "Collection budgets/environment/order still require a frozen source protocol review."]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_pool(import_pool(args.pool))
        output = checked_path(args.output)
        # Host-only diagnostics must never be mistaken for development_views.json.
        write_immutable_json(checked_path(output / "host_only" / "panel.json"), report)
        print(json.dumps({"readiness": report["readiness"], "development": report["development"],
                          "report": str(output / "host_only" / "panel.json")}, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        parser.exit(2, f"Panel inspection refused: {type(error).__name__}\n")


if __name__ == "__main__":
    raise SystemExit(main())
