"""Run the separate V8 prospective feedback ablation; no legacy run mutations."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v8.feedback_study import FeedbackStudy  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=4)
    args = parser.parse_args()
    study = FeedbackStudy(REPO, args.output, blocks=args.blocks)
    result = study.prepare() if args.action == "prepare" else study.run()
    print(json.dumps({key: result[key] for key in ("record_hash", "complete", "summary", "ledger", "max_calls")
                     if key in result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
