"""Run, pause, explicitly resume, or offline-replay one bounded V14 study."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from contextlib import ExitStack, contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def study_module():
    from skillopt.coevolution_v14 import study
    return study


def tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def forbidden(*args, **kwargs):
    raise ValueError("Completed V14 replay attempted model access or native execution")


def configuration(protocol=None, *, design=None, max_calls=None, workers=None):
    if protocol:
        saved = {key: protocol[key] for key in ("design", "max_calls", "workers")}
        requested = {"design": design, "max_calls": max_calls, "workers": workers}
        if any(value is not None and value != saved[key] for key, value in requested.items()):
            raise ValueError("Cannot change the frozen design, request budget or worker count")
        return saved
    design = design or "smoke"
    max_calls = max_calls if max_calls is not None else 64 if design == "smoke" else 640
    workers = workers if workers is not None else 4
    if (design not in {"smoke", "formal"} or type(max_calls) is not int
            or max_calls != (64 if design == "smoke" else 640)):
        raise ValueError("Frozen budgets are exactly smoke=64 and formal=640 logical calls")
    if type(workers) is not int or workers != 4:
        raise ValueError("Frozen worker count is exactly 4")
    return {"design": design, "max_calls": max_calls, "workers": workers}


@contextmanager
def completed_replay(repo, output):
    """Hold a shared run lock through offline replay and the caller's readout."""
    module = study_module()
    repo = Path(repo).resolve()
    root = module.safe_root(repo, output)
    if not (root / "results.json").is_file() or not (root / ".run.lock").is_file():
        raise ValueError("Completed results and their pre-existing run lock are required")
    with (root / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        before = tree(root)
        protocol, result = module.read(root / "protocol.json"), module.read(root / "results.json")
        if result.get("complete") is not True or result.get("protocol_hash") != protocol["record_hash"]:
            raise ValueError("Completed result/protocol binding differs")
        runner = module.Study(repo, root, **configuration(protocol), api_factory=forbidden)
        if not runner.complete:
            raise ValueError("Completed replay cannot start or resume an experiment")
        from skillopt.coevolution_v14 import runtime
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime.legacy, "evaluate", forbidden))
            stack.enter_context(patch.object(module.OfflineAPI, "call", forbidden))
            stack.enter_context(redirect_stdout(StringIO()))
            replayed = runner.run()
        if replayed != result or module.read(root / "results.json") != result or tree(root) != before:
            raise ValueError("Completed replay disagrees or changed experiment evidence")
        if module.source_hashes(repo) != protocol["source_hashes"]:
            raise ValueError("Frozen source drift during completed replay")
        yield {"root": root, "protocol": protocol, "result": result, "before": before}
        if module.source_hashes(repo) != protocol["source_hashes"] or tree(root) != before:
            raise ValueError("Completed readout changed frozen sources or experiment files")


def _brief(result, *, replay=False):
    return {"complete": result["complete"], "result_hash": result["record_hash"],
            "learning": result.get("learning"), "summary": result.get("summary"), "ledger": result.get("ledger"),
            "replay_files_unchanged": replay, "replay_model_api_calls": 0 if replay else None,
            "replay_native_executions": 0 if replay else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=("smoke", "formal"), default=None)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--replay-only", action="store_true")
    actions.add_argument("--request-pause", action="store_true")
    actions.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    module = study_module()
    root = module.safe_root(REPO, args.output)
    protocol = module.read(root / "protocol.json") if (root / "protocol.json").is_file() else None
    config = configuration(protocol, design=args.design, max_calls=args.max_calls, workers=args.workers)
    complete = (root / "results.json").is_file()
    if args.request_pause:
        if protocol is None or complete:
            parser.error("Pause requires a prepared, unfinished run")
        if not (root / "PAUSE").exists():
            (root / "PAUSE").touch(exist_ok=False)
        print('{"pause_requested":true,"drain_current_chunk":true}')
        return 0
    if args.resume and (protocol is None or complete):
        parser.error("Explicit resume requires a prepared, unfinished run")
    if args.replay_only or complete:
        with completed_replay(REPO, root) as audited:
            output = _brief(audited["result"], replay=True)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".run.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            # Only this exact marker in a validated, source-identical run is consumed.
            current = module.read(root / "protocol.json")
            if current != protocol or module.source_hashes(REPO) != current["source_hashes"]:
                raise ValueError("Cannot resume changed protocol or frozen sources")
            if (root / "PAUSE").exists():
                (root / "PAUSE").unlink()
        try:
            result = module.Study(REPO, root, **config).run()
        except module.PauseRequested:
            print('{"complete":false,"paused":true,"evidence_preserved":true}')
            return 75
        print(json.dumps(_brief(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
