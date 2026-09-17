"""Calibrate one independently repaired Research candidate, never activate by syntax."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v8.calibration_study import run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=4)
    args = parser.parse_args()
    row = run(REPO, args.diagnostic_root, args.output, blocks=args.blocks)
    print(json.dumps({k: row[k] for k in ("record_hash", "complete", "status", "decision", "ledger") if k in row},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
