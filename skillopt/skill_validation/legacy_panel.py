"""Inventory checked historical Coding development records, without new runs.

Compatibility diagnostics only: old Skill-bearing records remain unassigned,
not relabelled Current/Candidate. No historical data become fresh calibration.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import write_immutable_json

from .importers import normalize_v15
from .legacy import _read, _safe_path, load_v15_development
from .models import require
from .panel import checked_path
from .replay import run_case, save_host_audit


def inventory_legacy(run_root, output, *, source_kind, limit=64):
    require(type(limit) is int and limit > 0, "Positive diagnostic record limit required")
    require(source_kind in {"model", "fixture", "mutant"}, "Explicit source kind required")
    root, output = checked_path(run_root), checked_path(output)
    require(root != output and root not in output.parents and output not in root.parents,
            "Inventory output must be separate from historical run")
    directory = _safe_path(root, "runtime/solves")
    require(directory.is_dir(), "Missing historical solver directory")
    eligible, exclusions = [], []
    for path in sorted(directory.glob("*.json")):
        try:
            record = _read(root, str(path.relative_to(root)))
            # Only metadata select development; no final outcome is used.
            if record.get("domain") != "coding" or record.get("phase") != "development":
                exclusions.append({"solve_id": path.stem, "reason": "outside_coding_development"})
                continue
            eligible.append({"solve_id": path.stem, "record_hash": record["record_hash"]})
        except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
            exclusions.append({"solve_id": path.stem, "reason": "invalid_metadata", "error_type": type(error).__name__})
    selected = eligible[:limit]
    selection = seal({"version": "legacy-development-inventory-v1", "source_kind": source_kind,
                      "limit": limit, "selection": "sorted_solve_id_not_outcome", "selected": selected,
                      "excluded": exclusions, "unselected_due_to_limit": eligible[limit:]})
    write_immutable_json(checked_path(output / "host_only" / "selection.json"), selection)
    records, refused = [], []
    for entry in selected:
        identifier = entry["solve_id"]
        try:
            imported = load_v15_development(root, identifier, source_kind=source_kind)
            task, artifact, evidence, audit = normalize_v15(imported)
        except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
            refused.append({"solve_id": identifier, "error_type": type(error).__name__,
                            "reason": "closed_import_refused_not_regenerated"})
            continue
        # Output errors, including changed resume inputs, must fail closed.
        case_root = output / "cases" / identifier
        summary = run_case(task, artifact, evidence, output=case_root)
        save_host_audit(case_root, audit)
        records.append({"solve_id": identifier, "source_hash": artifact.source_hash,
                        "task_id": task.original_task_id, "family_id": task.family_id,
                        "project_id": task.project_id, "repeat": artifact.repeat,
                        "condition": artifact.condition, "artifact_hash": artifact.artifact_hash,
                        "availability": artifact.availability, "provenance_kind": artifact.provenance_kind,
                        "provenance_complete": artifact.provenance_complete,
                        "historical_only": artifact.historical_only, "formal_eligible": False,
                        "public_replay_status": summary["status"], "case_hash": summary["case_hash"],
                        "report_hash": summary["report_hash"]})
    report = seal({"version": "legacy-development-inventory-v1", "selection_hash": selection["record_hash"],
        "purpose": "host_only_historical_compatibility_diagnostic", "selected_records": len(selected),
        "imported_records": len(records), "refused_records": refused, "records": records,
        "original_tasks": len({r["task_id"] for r in records}),
        "declared_families": len({r["family_id"] for r in records}),
        "declared_projects": len({r["project_id"] for r in records}),
        "unique_task_artifact_contents": len({(r["task_id"], r["artifact_hash"]) for r in records
                                               if r["availability"] == "available"}),
        "conditions": dict(sorted(Counter(r["condition"] for r in records).items())),
        "public_replay_statuses": dict(sorted(Counter(r["public_replay_status"] for r in records).items())),
        "availability": dict(sorted(Counter(r["availability"] for r in records).items())),
        "natural_formal_eligible_records": 0, "certified_current_candidate_triplets": 0,
        "new_model_calls": 0, "new_artifact_executions": 0,
        "limitations": ["All imported historical records remain development-only diagnostics.",
                        "Public replay status is not full-task accuracy or stronger independent audit.",
                        "Skill-bearing records are unassigned: no invented parent/candidate pairing.",
                        "Sorted solve-ID sampling is a bounded inventory, not a representative task study.",
                        "Counts do not authenticate provenance or establish generalization."]})
    write_immutable_json(checked_path(output / "host_only" / "inventory.json"), report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-kind", choices=("model", "fixture", "mutant"), required=True)
    parser.add_argument("--limit", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        result = inventory_legacy(args.run_root, args.output, source_kind=args.source_kind, limit=args.limit)
        print(json.dumps({k: v for k, v in result.items() if k != "records"}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        parser.exit(2, f"Legacy inventory refused: {type(error).__name__}\n")


if __name__ == "__main__":
    raise SystemExit(main())
