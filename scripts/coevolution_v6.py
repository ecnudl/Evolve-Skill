"""Prepare, run or inspect the isolated V6 native-task/validator experiment."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.experiment import read  # noqa: E402
from skillopt.coevolution_v6.experiment import Study  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--histories", type=int, default=3)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--max-calls", type=int, default=900)
    args = parser.parse_args()
    study = Study(REPO, args.output, histories=args.histories, blocks=args.blocks, max_calls=args.max_calls)
    if args.action == "prepare":
        value = study.prepare()
        print(json.dumps({"status": "frozen", "version": value["version"], "histories": value["histories"],
                          "blocks": value["blocks"], "max_calls": value["max_calls"],
                          "source_files": len(value["source_hashes"]), "panel_hash": value["panel_hash"]}, indent=2))
        return
    if args.action == "run":
        result = study.run()
    else:
        study.verify()
        result = read(study.root / "results.json")
    print(json.dumps({"status": result["status"], "ledger": result["ledger"],
                      "calibration_gate": result["calibration"]["primary_gate"],
                      "final": result["final"]["cluster_analysis"]["policy_summary"],
                      "repairs": result["repair_summary"], "human_review": result["human_review"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
