"""Prepare or run the bounded Skill / executable-validator co-evolution study."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution.experiment import Study  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    study = Study(REPO, args.output)
    if args.execute:
        study.run()
    else:
        study.prepare()


if __name__ == "__main__":
    main()
