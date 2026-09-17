"""Probe a frozen plan's official URLs using the pinned existing local proxy.

This creates new public-document snapshots only. It does not repair/regrade a
historical run or make any model call, and never edits proxy settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.validator_document_transport import fetch_sources  # noqa: E402
from skillopt.validator_pilot.api import write_immutable_json  # noqa: E402
from skillopt.validator_pilot.research import parse_plan  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="NEW public-document snapshot directory")
    args = parser.parse_args(argv)
    try:
        plan_bytes = args.plan.read_bytes()
        plan = parse_plan(json.loads(plan_bytes))
        if args.output.resolve() == args.plan.resolve() or args.plan.resolve().parent in args.output.resolve().parents:
            raise ValueError("probe output must not be inside the original plan directory")
        write_immutable_json(
            args.output / "probe_input.json",
            {
                "plan_path": str(args.plan.resolve()),
                "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                "urls": plan["urls"],
                "scope": "engineering retrieval probe only; no retrospective rubric/model result",
            },
        )
        sources = fetch_sources(plan["urls"], args.output)
        summary = {
            "status": "complete",
            "requested": len(sources),
            "retrieved": sum(row["ok"] for row in sources),
            "model_calls": 0,
            "original_run_changed": False,
            "proxy_settings_changed": False,
            "not_a_validator_effectiveness_result": True,
            "sources": [
                {
                    key: row.get(key)
                    for key in (
                        "requested_url",
                        "ok",
                        "error_type",
                        "final_url",
                        "html_bytes",
                        "raw_html_sha256",
                        "text_sha256",
                    )
                }
                for row in sources
            ],
        }
        write_immutable_json(args.output / "probe_result.json", summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["retrieved"] == summary["requested"] else 1
    except Exception as exc:
        print(json.dumps({"status": "refused", "error_type": type(exc).__name__, "model_calls": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
