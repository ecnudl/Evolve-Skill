"""Prepare/run/report the isolated V5 integration protocol, not benchmark efficacy."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.experiment import Study, read  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--histories", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-calls", type=int, default=512)
    args = parser.parse_args()
    study = Study(REPO, args.output, histories=args.histories, repeats=args.repeats, max_calls=args.max_calls)
    if args.action == "run":
        result = study.run()
    elif args.action == "prepare":
        result = study.prepare()
    else:
        study.verify()
        result = read(study.root / "results.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
