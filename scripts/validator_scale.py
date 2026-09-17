"""Prepare or explicitly execute the frozen repeated Coding diagnostic study."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.validator_pilot.api import write_immutable_json  # noqa: E402
from skillopt.validator_pilot.experiment import log  # noqa: E402
from skillopt.validator_scale_experiment import ScaleStudy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true", help="Explicitly allow up to900logicalPJLABcalls")
    args = parser.parse_args()
    study = ScaleStudy(REPO, args.output)
    try:
        if args.execute:
            study.run()
        else:
            study.prepare()
    except Exception as exc:
        log("stopped", error_type=type(exc).__name__, artifacts_preserved=True)
        write_immutable_json(args.output / "run_error.json", {"error_type": type(exc).__name__,
                                                              "artifacts_preserved": True})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
