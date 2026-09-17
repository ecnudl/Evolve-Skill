"""Inspect or run a NEW isolated development Research contract-repair diagnostic."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.research_contract_repair import inspect_source, run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "run"), nargs="?", default="inspect")
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--original-run-stopped", action="store_true",
                        help="Operator attestation: original API process has stopped; not independently verified")
    args = parser.parse_args()
    if args.action == "inspect":
        context = inspect_source(REPO, args.source_run)
        result = {"status": "eligible_new_diagnostic_not_run", "source_plan_hash": context["source_plan_hash"],
                  "packet_count": len(context["evidence"]["packet_hashes"]),
                  "structural_errors": context["structural_errors"], "api_calls": 0}
    else:
        if args.output is None:
            parser.error("run requires --output under outputs/research_contract_repair/<run>")
        record = run(REPO, args.source_run, args.output, original_run_stopped=args.original_run_stopped)
        result = {k: record[k] for k in ("status", "calls_used", "activation", "diagnostic_only", "record_hash")}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
