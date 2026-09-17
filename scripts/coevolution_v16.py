"""Run, explicitly resume, or read-only replay one preregistered V16 study."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def forbidden(*args, **kwargs):
    raise RuntimeError("Completed verification forbids API/network/native execution")


def tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def completed_replay(repo, root):
    from skillopt.coevolution_v15 import runtime
    from skillopt.coevolution_v16 import research, study
    root = study.safe_root(repo, root)
    if not all((root / name).is_file() for name in ("results.json", ".run.lock", ".audit.lock")):
        raise ValueError("Completed run and its original lock required")
    with (root / ".run.lock").open("rb") as handle, (root / ".audit.lock").open("rb") as audit_lock:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        # Exclude operational heartbeat writes during the whole-tree snapshot.
        fcntl.flock(audit_lock, fcntl.LOCK_EX)
        before = tree(root)
        original, protocol = study.read(root / "results.json"), study.read(root / "protocol.json")
        if original["complete"] is not True or original["protocol_hash"] != protocol["record_hash"]:
            raise ValueError("Result/protocol mismatch")
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime.legacy, "evaluate", forbidden))
            stack.enter_context(patch.object(research, "fetch_sources", forbidden))
            stack.enter_context(patch.object(study.OfflineAPI, "call", forbidden))
            stack.enter_context(redirect_stdout(StringIO()))
            replayed = study.Study(repo, root, design=protocol["design"], api_factory=forbidden).run()
        if replayed != original or tree(root) != before:
            raise ValueError("Offline replay changed evidence or disagreed with completed result")
        return original


def status(root):
    from skillopt.coevolution_v12.study import read
    protocol_path = root / "protocol.json"
    if not protocol_path.exists():
        return {"prepared": False, "output": str(root)}
    protocol = read(protocol_path)
    calls = [json.loads(p.read_text()) for p in (root / "api/calls").glob("*.json")]
    events = sorted((root / "events").glob("*.json"))
    return {"prepared": True, "design": protocol["design"], "complete": (root / "results.json").is_file(),
        "pause_requested": (root / "PAUSE").exists(), "logical_calls": len(calls),
        "terminal_api_failures": sum(c.get("ok") is not True for c in calls),
        "max_calls": protocol["max_calls"], "last_event": read(events[-1]) if events else None,
        "model": protocol["model"], "output": str(root)}


def write_report(root, target):
    from skillopt.coevolution_v16.reporting import render
    path = Path(target).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents)) or path.suffix != ".md"
            or not path.is_relative_to(REPO / "docs") or path.name.endswith("-protocol.md")):
        raise ValueError("Derived report must be a nonsource Markdown file beneath docs")
    content = render(root)
    path.write_text(content, encoding="utf-8")
    return str(path)


def main(argv=None):
    from skillopt.coevolution_v16 import study
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--design", choices=tuple(study.DESIGNS))
    parser.add_argument("--report", type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--prepare-only", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--request-pause", action="store_true")
    actions.add_argument("--resume", action="store_true")
    actions.add_argument("--replay-only", action="store_true")
    args = parser.parse_args(argv)
    root = study.safe_root(REPO, args.output)
    if args.status:
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    previous = study.read(root / "protocol.json") if (root / "protocol.json").exists() else None
    design = args.design or (previous["design"] if previous else None)
    if design is None or (previous is not None and design != previous["design"]):
        parser.error("Explicit initial design required; existing design cannot change")
    if args.request_pause:
        if previous is None or (root / "results.json").exists():
            parser.error("Pause requires a prepared unfinished run")
        (root / "PAUSE").touch(exist_ok=True)
        print('{"pause_requested":true,"inflight_drained_before_stop":true}')
        return 0
    if args.replay_only or (root / "results.json").exists():
        result = completed_replay(REPO, root)
        report = write_report(root, args.report) if args.report else None
        print(json.dumps({"complete": True, "offline_verified": True, "api_calls": 0,
                          "result_hash": result["record_hash"], "report": report}, ensure_ascii=False))
        return 0
    if args.resume and previous is None:
        parser.error("Resume requires an existing registered run")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".audit.lock").open("a"):
        pass
    with (root / ".run.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            if study.source_hashes(REPO) != previous["source_hashes"]:
                raise ValueError("Cannot resume after frozen source drift")
            if (root / "PAUSE").exists():
                (root / "PAUSE").unlink()
        runner = study.Study(REPO, root, design=design)
        try:
            if args.prepare_only:
                result = runner.prepare()
                print(json.dumps({"prepared": True, "protocol_hash": result["record_hash"], "model_api_calls": 0}))
                return 0
            result = runner.run()
        except study.PauseRequested:
            print('{"complete":false,"paused":true,"evidence_preserved":true}')
            return 75
    # Verification itself reopens the original lock read-only.
    completed_replay(REPO, root)
    report = write_report(root, args.report) if args.report else None
    print(json.dumps({"complete": True, "offline_verified": True, "result_hash": result["record_hash"],
                      "validator_evolution": result["validator_evolution"], "report": report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
