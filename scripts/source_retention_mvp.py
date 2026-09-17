"""Prepare, screen, then explicitly test fresh local SearchQA source questions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skillopt.scope_evolution_v2.source_data import DEFAULT_CACHE  # noqa: E402
from skillopt.scope_evolution_v2.source_retention import DEFAULT_ARMS, run_phase  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "pilot", "test"), required=True)
    parser.add_argument("--out", type=Path, default=Path("outputs/scope_evolution_v2/source_retention_gpt55_20260908"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--calibration-n", type=int, default=128)
    parser.add_argument("--holdout-n", type=int, default=256)
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--without-extractive", action="store_true", help="Preregister only base/full; cannot change after prepare")
    args = parser.parse_args(argv)
    root = (REPO / args.out).resolve()
    outputs = (REPO / "outputs").resolve()
    if outputs not in root.parents:
        raise ValueError("Use a dedicated new directory under repository outputs")
    result = run_phase(REPO, root, args.phase,
                       arms=("base", "full") if args.without_extractive else DEFAULT_ARMS,
                       workers=args.workers, seed=args.seed, calibration_n=args.calibration_n,
                       holdout_n=args.holdout_n, cache_path=args.cache_path)
    # Never print task payloads, gold labels, per-item answers or API credentials.
    shown = result if args.phase == "prepare" else {key: result[key] for key in ("phase", "split", "arms", "vs_base")}
    print(json.dumps(shown, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
