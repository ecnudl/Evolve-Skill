"""Freeze, run/resume, or report the isolated evidence-grounded V7 study."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.experiment import read  # noqa: E402
from skillopt.coevolution_v7.experiment import Study  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--histories", type=int, default=2)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--max-calls", type=int, default=700)
    args = parser.parse_args()
    study = Study(REPO, args.output, histories=args.histories, blocks=args.blocks, max_calls=args.max_calls)
    if args.action == "prepare":
        p = study.prepare()
        result = {"status": "frozen", "version": p["version"], "panel_hash": p["panel_hash"], "max_calls": p["max_calls"]}
    else:
        if args.action == "run":
            result = study.run()
        else:
            study.verify()
            result = read(study.root / "results.json")
        result = {"status": result["status"], "ledger": result["ledger"],
                  "validator_activation": result["validator_activation"],
                  "source_decisions": result["source_decisions"], "final": result["final"]["native"]["macro"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
