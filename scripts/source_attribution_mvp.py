"""Explicit, paced entry for preregistered source section-lesion attribution."""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("prepare", "test", "report"))
    parser.add_argument("--out", type=Path, default=Path("outputs/scope_evolution_v2/source_attribution_gpt55_20260908"))
    parser.add_argument("--source-dir", type=Path, default=Path("outputs/scope_evolution_v2/source_retention_gpt55_20260908_sessionfix"))
    parser.add_argument("--routing-dir", type=Path, default=Path("outputs/scope_evolution_v2/retention_routing_gpt55_20260908_paced"))
    parser.add_argument("--workers", type=int, default=6, choices=(6,))
    parser.add_argument("--seed", type=int, default=20260908)
    args = parser.parse_args(argv)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    root = (REPO / args.out).resolve()
    if REPO / "outputs" not in root.parents:
        raise ValueError("Use a dedicated attribution directory below repository outputs")
    # Must happen before any SkillOpt/model import; never create/persist a session.
    launcher = importlib.import_module("scripts.source_retention_session_mvp")
    expected = launcher.preload_session_environment(REPO)
    if args.phase == "test" and expected is None:
        raise ValueError("An existing target/shared session is required before attribution target calls")
    backend = importlib.import_module("skillopt.model.openai_compatible_backend")
    if args.phase == "test" and backend.TARGET_CONFIG.session_id != expected:
        raise ValueError("Backend session does not match preloaded configuration; use a fresh process")
    runner = importlib.import_module("skillopt.scope_evolution_v2.source_attribution")
    pacing = importlib.import_module("scripts.paced_scope_mvp")
    with pacing.paced_backend(backend, 2.0):
        result = runner.run_phase(REPO, root, REPO / args.source_dir, REPO / args.routing_dir,
                                  args.phase, workers=args.workers, seed=args.seed)
    if args.phase == "prepare":
        print({"phase": "prepare", "arms": list(result["arms"]), "holdout_n": result["holdout_n"],
               "new_calls": result["max_new_logical_target_calls"], "holdout_materialized": False})
    else:
        print({"phase": args.phase, "common_n": len(result["common_ids"]), "arms": result["arms"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
