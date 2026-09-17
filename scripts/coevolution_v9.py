"""Run the prospective native SearchQA Skill learning/gate study."""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v9.study import Study  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=("smoke", "source"), default="source")
    parser.add_argument("--prepare-only", action="store_true", help="Reserve blinded identities and freeze protocol; no API")
    args = parser.parse_args()
    study = Study(REPO, args.output, design=args.design)
    result = study.prepare() if args.prepare_only else study.run()
    print(json.dumps({k: result[k] for k in ("record_hash", "complete", "ledger", "summary") if k in result},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
