"""Run/resume or verify one fixed public-task V18 pilot; no implicit resampling."""

from __future__ import annotations

import argparse
import fcntl
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
    from skillopt.coevolution_v18 import study
    return study


def forbidden(*args, **kwargs):
    raise RuntimeError("Completed replay forbids models, network, execution and credentials")


def completed_replay(repo, root):
    from scripts.coevolution_v17 import tree
    from skillopt.coevolution_v11 import executor
    from skillopt.validator_pilot import api
    study = _study()
    root = study.safe_root(repo, root)
    if not all((root / p).is_file() for p in ("results.json", "protocol.json", ".run.lock", ".audit.lock")):
        raise ValueError("Completed original evidence and locks are required")
    with (root / ".run.lock").open("rb") as lock, (root / ".audit.lock").open("rb") as audit:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(audit, fcntl.LOCK_EX)
        before, original = tree(root), study.read(root / "results.json")
        with ExitStack() as stack:
            for owner, name in ((api, "_configuration"), (api.CachedAPI, "call"),
                                (study.OfflineAPI, "call"), (executor, "run_cases"),
                                (executor, "sandbox_probe"), (socket, "create_connection"),
                                (socket.socket, "connect"), (socket.socket, "connect_ex"), (subprocess, "Popen")):
                stack.enter_context(patch.object(owner, name, forbidden))
            stack.enter_context(redirect_stdout(StringIO()))
            result = study.Study(repo, root, api_factory=forbidden).run()
        if result != original or tree(root) != before:
            raise ValueError("Completed replay changed evidence or disagreed with sealed result")
        return result


def status(root):
    study = _study()
    if not (root / "protocol.json").is_file():
        return {"prepared": False}
    calls = [json.loads(p.read_text()) for p in (root / "api/calls").glob("*.json")]
    events = sorted((root / "events").glob("*.json"))
    return {"prepared": True, "complete": (root / "results.json").is_file(),
            "pause_requested": (root / "PAUSE").exists(), "logical_calls": len(calls),
            "terminal_api_errors": sum(r.get("ok") is not True for r in calls),
            "last_event": study.read(events[-1]) if events else None}


def write_report(root, target):
    from scripts.coevolution_v17 import report_path
    from skillopt.coevolution_v18.reporting import render
    path = report_path(REPO, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(root), encoding="utf-8")
    return str(path)


def main(argv=None):
    study = _study()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    group = parser.add_mutually_exclusive_group()
    for option in ("prepare-only", "status", "request-pause", "resume", "replay-only"):
        group.add_argument("--" + option, action="store_true")
    args = parser.parse_args(argv)
    root = study.safe_root(REPO, args.output)
    if args.report:
        from scripts.coevolution_v17 import report_path
        report_path(REPO, args.report)
    if args.status:
        print(json.dumps(status(root), ensure_ascii=False))
        return 0
    if args.request_pause:
        if not (root / "protocol.json").is_file() or (root / "results.json").exists():
            parser.error("Pause requires an unfinished registered run")
        (root / "PAUSE").touch(exist_ok=True)
        return 0
    if args.replay_only or (root / "results.json").exists():
        result = completed_replay(REPO, root)
    else:
        if args.resume and not (root / "protocol.json").is_file():
            parser.error("Explicit resume requires a prior protocol")
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".audit.lock").open("a"):
            pass
        with (root / ".run.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.resume:
                if study.source_hashes(REPO) != study.read(root / "protocol.json")["source_hashes"]:
                    raise ValueError("Cannot resume changed frozen sources")
                (root / "PAUSE").unlink(missing_ok=True)
            runner = study.Study(REPO, root)
            if args.prepare_only:
                result = runner.prepare()
                print(json.dumps({"prepared": True, "protocol_hash": result["record_hash"], "api_calls": 0}))
                return 0
            try:
                runner.run()
            except study.PauseRequested:
                print('{"paused":true,"inflight_preserved":true}')
                return 75
        result = completed_replay(REPO, root)
    report = write_report(root, args.report) if args.report else None
    print(json.dumps({"complete": True, "offline_verified": True,
                      "result_hash": result["record_hash"], "report": report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
