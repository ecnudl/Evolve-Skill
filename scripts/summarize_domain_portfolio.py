"""Describe normalized domain score portfolios; never run or regrade a benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.cross_domain.portfolio_metrics import summarize_portfolio  # noqa: E402
from skillopt.validator_pilot.api import digest, write_immutable_json  # noqa: E402


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not allowed")
        result[key] = value
    return result


def summarize_file(source):
    payload = json.loads(Path(source).read_text(encoding="utf-8"), object_pairs_hook=_unique)
    allowed = {"scores", "source_domains", "weights", "metadata"}
    if not isinstance(payload, dict) or not {"scores", "metadata"} <= set(payload) or set(payload) - allowed:
        raise ValueError("Input must have scores and metadata, plus optional source_domains and weights")
    metadata = payload["metadata"]
    if not isinstance(metadata, dict) or metadata.get("kind") not in {"illustrative_example", "observed_scores"}:
        raise ValueError("Explicit metadata.kind must be illustrative_example or observed_scores")
    return {
        "version": "domain-portfolio-descriptive-report-v1",
        "source_sha256": digest(payload),
        "metadata": metadata,
        "model_calls": 0,
        "descriptive_only": True,
        "benchmark_reexecution": False,
        "original_benchmark_scores_changed": False,
        "illustration_is_not_experimental_evidence": metadata["kind"] == "illustrative_example",
        "input_provenance_not_independently_verified": True,
        "metrics": summarize_portfolio(
            payload["scores"], source_domains=payload.get("source_domains", ()), weights=payload.get("weights")
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve() or args.output.exists():
        parser.error("Output must be a new file, distinct from the input")
    try:
        report = summarize_file(args.input)
        write_immutable_json(args.output, report)
    except (ValueError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"report": str(args.output), "kind": report["metadata"]["kind"], "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
