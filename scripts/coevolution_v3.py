"""Prepare or run the frozen multi-file local/deployment co-evolution experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v3.experiment import Study  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    study = Study(REPO, args.output)
    result = study.run() if args.execute else study.prepare()
    if args.execute:
        print("Run status:", result["status"], flush=True)


if __name__ == "__main__":
    main()
