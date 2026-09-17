"""Run the explicitly adapted, development-only verifier-repair pilot on PJLAB."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.validator_pilot.api import write_immutable_json  # noqa: E402
from skillopt.validator_pilot.experiment import Pilot, log  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4, choices=(1, 4, 8))
    parser.add_argument("--repeats", type=int, default=2, choices=(1, 2, 3))
    parser.add_argument("--rounds", type=int, default=3, choices=(0, 1, 2, 3))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--non-stream", action="store_true", help="Diagnostic only: PJLAB long nonstream requests encountered 60s server504s")
    parser.add_argument("--reasoning-effort", choices=("low", "high", "max"), default="low")
    args = parser.parse_args()
    pilot = Pilot(REPO, args.output, workers=args.workers, repeats=args.repeats, rounds=args.rounds,
                  stream=not args.non_stream, reasoning_effort=args.reasoning_effort)
    try:
        if args.prepare_only:
            pilot.prepare()
        else:
            pilot.run()
    except Exception as exc:
        # Exception messages may contain model content or network detail: fixed category only.
        log("stopped", error_type=type(exc).__name__, note="Artifacts preserved; inspect locally before any new run.")
        write_immutable_json(args.output / "run_error.json", {"error_type": type(exc).__name__, "artifacts_preserved": True})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
