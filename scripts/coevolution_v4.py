"""Prepare or execute V4 without changing credentials, proxy routes, or old runs."""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v4.experiment import Study  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    study = Study(REPO, args.output)
    result = study.run() if args.execute else study.prepare()
    print("Status:", result.get("status", "prepared"), flush=True)


if __name__ == "__main__":
    main()
