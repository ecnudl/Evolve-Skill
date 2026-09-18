"""python -m skillopt.skill_validation: credential-free offline Stage 1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    smoke = commands.add_parser("smoke", help="Four explicitly synthetic fixed-artifact cases")
    smoke.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser("replay", help="Replay a typed case without models, Research or code execution")
    replay.add_argument("--input", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    legacy = commands.add_parser("import-v15", help="Import one closed historical Coding development solve")
    legacy.add_argument("--run-root", type=Path, required=True)
    legacy.add_argument("--solve-id", required=True)
    legacy.add_argument("--source-kind", choices=("model", "fixture", "mutant"), required=True)
    legacy.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from .replay import read_case, run_case, save_host_audit
    try:
        if args.command == "smoke":
            from .fixtures import smoke_cases
            from .partitions import PartitionManifest
            manifest = PartitionManifest()
            result = {name: run_case(task, artifact, evidence, output=args.output / name, manifest=manifest)
                      for name, task, artifact, evidence in smoke_cases()}
        elif args.command == "replay":
            task, artifact, evidence, manifest = read_case(args.input)
            result = run_case(task, artifact, evidence, output=args.output, manifest=manifest)
        else:
            from .importers import normalize_v15
            from .legacy import load_v15_development
            imported = load_v15_development(args.run_root, args.solve_id, source_kind=args.source_kind)
            task, artifact, evidence, audit = normalize_v15(imported)
            result = run_case(task, artifact, evidence, output=args.output)
            save_host_audit(args.output, audit)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        # Do not print source bundles, upstream responses, or credentials.
        parser.exit(2, f"Offline validation refused: {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
