"""Explicit phases for fixed-full-Skill retention/routing diagnostics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True,
                        choices=("prepare", "route-calibration", "control-calibration", "freeze", "route-test", "control-test", "report"))
    parser.add_argument("--out", type=Path, default=Path("outputs/scope_evolution_v2/retention_routing_gpt55_20260908"))
    parser.add_argument("--source-dir", type=Path, default=Path("outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--n-per-group", type=int, default=16)
    args = parser.parse_args(argv)
    # Must run before importing SkillOpt/QA/model code, including controls.
    from scripts.source_retention_session_mvp import preload_session_environment
    expected = preload_session_environment(REPO)
    real_call_phase = args.phase.startswith("route-") or args.phase.startswith("control-")
    if real_call_phase and expected is None:
        raise ValueError("No preexisting gateway session ID; no API call started")
    from skillopt.scope_evolution_v2.retention_routing import run_phase
    root = (REPO / args.out).resolve()
    if (REPO / "outputs").resolve() not in root.parents:
        raise ValueError("Use a separate routing directory under repository outputs")
    result = run_phase(REPO, root, (REPO / args.source_dir).resolve(), args.phase,
                       workers=args.workers, seed=args.seed, n_per_group=args.n_per_group)
    if "routes" in result:
        shown = {"phase": args.phase, "route_n": len(result["routes"]),
                 "routing_errors": sum(not r["route_ok"] for r in result["routes"]),
                 "enabled_n": {k: len(v) for k, v in result["deployment"].items()}}
    elif "splits" in result:
        shown = {"phase": args.phase, "report_splits": list(result["splits"]), "commit_authorized": False}
    else:
        shown = result
    print(json.dumps(shown, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
