"""Run, explicitly resume, or read-only replay one preregistered V17 study."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import json
import socket
import subprocess
import sys
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _study():
    return importlib.import_module("skillopt.coevolution_v17.study")


def forbidden(*args, **kwargs):
    raise RuntimeError("Completed verification forbids API/network/native execution")


def tree(root):
    """Hash every file, including operational logs; never follow evidence links."""
    root = Path(root)
    paths = sorted(root.rglob("*"))
    if any(path.is_symlink() for path in (root, *root.parents, *paths)):
        raise ValueError("Symlink run evidence is forbidden")
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.is_file()}


def completed_replay(repo, root):
    from skillopt.coevolution_v9.study import OfflineAPI
    from skillopt.coevolution_v15 import runtime
    from skillopt.validator_pilot import api

    study = _study()
    root = study.safe_root(repo, root)
    required = ("results.json", "protocol.json", ".run.lock", ".audit.lock")
    if not all((root / name).is_file() for name in required):
        raise ValueError("Completed run and its original locks required")
    with (root / ".run.lock").open("rb") as handle, (root / ".audit.lock").open("rb") as audit_lock:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(audit_lock, fcntl.LOCK_EX)
        before = tree(root)
        original, protocol = study.read(root / "results.json"), study.read(root / "protocol.json")
        if original.get("complete") is not True or original.get("protocol_hash") != protocol["record_hash"]:
            raise ValueError("Result/protocol mismatch")
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, "_configuration", forbidden))
            stack.enter_context(patch.object(api.CachedAPI, "call", forbidden))
            stack.enter_context(patch.object(OfflineAPI, "call", forbidden))
            stack.enter_context(patch.object(runtime.legacy, "evaluate", forbidden))
            stack.enter_context(patch.object(socket, "create_connection", forbidden))
            stack.enter_context(patch.object(socket.socket, "connect", forbidden))
            stack.enter_context(patch.object(socket.socket, "connect_ex", forbidden))
            stack.enter_context(patch.object(subprocess, "Popen", forbidden))
            stack.enter_context(redirect_stdout(StringIO()))
            replayed = study.Study(repo, root, design=protocol["design"],
                                   workers=protocol.get("workers", 4), api_factory=forbidden).run()
        if replayed != original or tree(root) != before:
            raise ValueError("Offline replay changed evidence or disagreed with completed result")
        return original


def status(root):
    from skillopt.coevolution_v12.study import read

    root = Path(root)
    if not (root / "protocol.json").exists():
        return {"prepared": False, "output": str(root)}
    protocol = read(root / "protocol.json")
    calls = [json.loads(path.read_text()) for path in (root / "api/calls").glob("*.json")]
    events = sorted((root / "events").glob("*.json"))
    result = read(root / "results.json") if (root / "results.json").is_file() else None
    return {"prepared": True, "design": protocol["design"],
            "complete": result is not None and result.get("complete") is True,
            "result_status": result.get("status") if result else None,
            "pause_requested": (root / "PAUSE").exists(), "logical_calls": len(calls),
            "terminal_api_failures": sum(call.get("ok") is not True for call in calls),
            "max_calls": protocol.get("max_calls"), "model": protocol.get("model"),
            "last_event": read(events[-1]) if events else None, "output": str(root)}


def report_path(repo, target):
    path = Path(target).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents)) or ".." in path.parts
            or path.suffix != ".md" or not path.is_relative_to(Path(repo).resolve() / "docs")
            or path.name.endswith("-protocol.md")):
        raise ValueError("Derived report must be a nonsource Markdown file beneath docs")
    return path


def write_report(root, target):
    from skillopt.coevolution_v17.reporting import render

    path = report_path(REPO, target)
    content = render(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def main(argv=None):
    study = _study()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--design", choices=tuple(study.DESIGNS))
    parser.add_argument("--report", type=Path)
    actions = parser.add_mutually_exclusive_group()
    for action in ("prepare-only", "status", "request-pause", "resume", "replay-only"):
        actions.add_argument("--" + action, action="store_true")
    args = parser.parse_args(argv)
    root = study.safe_root(REPO, args.output)
    if args.report:
        report_path(REPO, args.report)
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
                          "status": result.get("status"), "result_hash": result["record_hash"],
                          "report": report}, ensure_ascii=False))
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
        runner = study.Study(REPO, root, design=design, workers=4)
        try:
            if args.prepare_only:
                result = runner.prepare()
                print(json.dumps({"prepared": True, "protocol_hash": result["record_hash"],
                                  "model_api_calls": 0}))
                return 0
            result = runner.run()
        except study.PauseRequested:
            print('{"complete":false,"paused":true,"evidence_preserved":true}')
            return 75
    completed_replay(REPO, root)
    report = write_report(root, args.report) if args.report else None
    print(json.dumps({"complete": True, "offline_verified": True, "status": result.get("status"),
                      "result_hash": result["record_hash"], "report": report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
