"""Run, pause, resume, or verify the bounded Coding transfer study."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import io
import json
import sys
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5 import core  # noqa: E402


def _study_module():
    # Parsing --help and checking a completed result never constructs an API
    # client or reads credentials. Actual study construction remains explicit.
    return importlib.import_module("skillopt.coevolution_v10.study")


def _read(path):
    return core.verify(json.loads(Path(path).read_text(encoding="utf-8")))


def safe_root(output, repo=REPO):
    repo = Path(repo).resolve()
    raw = Path(output).absolute()
    if any(part.is_symlink() for part in (raw, *raw.parents)):
        raise ValueError("Experiment paths may not contain symlinks")
    root = raw.resolve()
    registry = repo / "outputs/coevolution_v10"
    if root == registry or not root.is_relative_to(registry):
        raise ValueError("Use a separate output beneath outputs/coevolution_v10")
    return root


def tree_hashes(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Run artifacts may not be symlinks")
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def forbidden_api(*args, **kwargs):
    raise RuntimeError("Model API construction is forbidden during completed replay")


@contextmanager
def _run_lock(root, *, readonly=False):
    path = root / ".run.lock"
    if path.is_symlink():
        raise ValueError("Run lock may not be a symlink")
    if readonly and not path.exists():
        # Legacy/offline fixture runs may have no CLI lock. Do not create one
        # in a mode whose explicit contract is zero writes.
        yield
        return
    if not readonly:
        root.mkdir(parents=True, exist_ok=True)
    with path.open("rb" if readonly else "a+") as lock:
        try:
            fcntl.flock(lock.fileno(), (fcntl.LOCK_SH if readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another process is actively running this experiment") from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def completed_replay(output, repo=REPO):
    """Verify an already complete run without resuming or writing any artifact."""
    repo = Path(repo).resolve()
    root = safe_root(output, repo)
    with _run_lock(root, readonly=True):
        return _completed_replay(root, repo)


def _completed_replay(root, repo):
    if not (root / "results.json").is_file() or not (root / "protocol.json").is_file():
        raise ValueError("Completed replay requires existing results and protocol")
    result, protocol = _read(root / "results.json"), _read(root / "protocol.json")
    if result.get("complete") is not True:
        raise ValueError("Active or incomplete runs cannot be reported/replayed as complete")
    if (protocol.get("design_name") not in {"smoke", "formal"}
            or result.get("protocol_hash") != protocol["record_hash"]):
        raise ValueError("Completed result is not bound to its frozen protocol")
    before = tree_hashes(root)
    # A supervisor may redirect stdout to a log inside the run. Replaying its
    # progress messages would then alter the very artifact tree being audited.
    with redirect_stdout(io.StringIO()):
        replayed = _study_module().Study(repo, root, design=protocol["design_name"], api_factory=forbidden_api).run()
    core.verify(replayed)
    if replayed != result:
        raise ValueError("Completed replay differs from the frozen result")
    if tree_hashes(root) != before:
        raise ValueError("Completed replay changed run artifacts")
    audit = core.seal({"version": "v10-completed-cli-replay-v1", "result_hash": result["record_hash"],
                       "protocol_hash": protocol["record_hash"], "complete_integrity_audit": True,
                       "run_files_unchanged": True, "verified_run_files": len(before), "model_api_calls": 0})
    return {"protocol": protocol, "result": result, "audit": audit}


def _design(root, requested):
    path = root / "protocol.json"
    existing = _read(path).get("design_name") if path.exists() else None
    if existing is not None and existing not in {"smoke", "formal"}:
        raise ValueError("Existing protocol has an unknown design")
    if requested is not None and existing is not None and requested != existing:
        raise ValueError("Requested design differs from the frozen protocol")
    return requested or existing or "smoke"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=("smoke", "formal"), default=None,
                        help="Infer an existing frozen design; new runs default to smoke")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--replay-only", action="store_true", help="Require a complete run; forbid API construction")
    group.add_argument("--request-pause", action="store_true", help="Request a checkpointed pause; do not launch the study")
    group.add_argument("--resume", action="store_true", help="Clear the checkpointed pause and continue the frozen run")
    args = parser.parse_args(argv)
    root = safe_root(args.output, REPO)
    design = _design(root, args.design)
    if args.replay_only:
        replay = completed_replay(root, REPO)
        result = {**replay["result"], "replay_audit": replay["audit"]}
    elif args.request_pause:
        result = _study_module().request_pause(root)
    else:
        module = _study_module()
        with _run_lock(root):
            if args.resume:
                module.resume(root)
            try:
                result = module.Study(REPO, root, design=design).run()
            except Exception as exc:
                if not isinstance(exc, getattr(module, "PauseRequested", ())):
                    raise
                print(json.dumps({"complete": False, "paused": True, "status": "paused_after_draining"}))
                return 75
    # Never dump task payloads, reference code, private assertions or Skill text.
    public_keys = ("record_hash", "complete", "paused", "status", "phase", "action", "sequence",
                   "ledger", "summary", "replay_audit")
    print(json.dumps({key: result[key] for key in public_keys if key in result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
