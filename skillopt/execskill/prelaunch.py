"""Before a route-B launch (registration §1, §10 S0, §14 #3; implementation plan §10 steps 1-3 and the prelaunch row
of §1): the snapshot check, the zero-call checks and the leftover check. Zero model calls.

- ``launch_env``: the environment of every route-B launch and child process (plan §6): ``OPENAI_API_KEY`` and
  ``OPENAI_BASE_URL`` removed, ``PYTHONDONTWRITEBYTECODE=1``.
- ``sha256_list`` / ``verify_snapshot``: plan §10 step 1 -- the sha256 list of ``skillopt/ scripts/ tests/`` (the
  format of ``sha256sum``, sorted by path, caches excluded) recomputed on the snapshot and compared line for line;
  no ``.env*`` file anywhere under the snapshot. Returns the manifest's provenance values.
- ``zero_call_checks``: the S0 pytest row on the snapshot with the registered interpreter and flags
  (``python -B -m pytest tests/test_execskill_*.py tests/test_weak_solver_probe.py -p no:cacheprovider``).
- ``leftovers``: after a stage, no route-B container (``execskill-sbx-*``) and no route-B or ALFWorld process may remain.
  The owner's rule #3 (22:3x): the D3/D14 feasibility workers left on the machine are not touched; processes whose
  command line matches ``EXCLUDED`` are listed apart and the ALFWorld-process check records ``cannot_judge`` while
  any of them runs.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from skillopt.continual_eval.core import require, safe_path

from . import protocol
from .sandbox import client as sandbox

UNSET = ("OPENAI_API_KEY", "OPENAI_BASE_URL")
SNAPSHOT_DIRS = ("skillopt", "scripts", "tests")
TEST_FILES = ("tests/test_execskill_*.py", "tests/test_weak_solver_probe.py")
# owner #3 (§14): the D3/D14 feasibility workers' command lines (their trace roots are /data/feasibility/D3 and D14)
EXCLUDED = re.compile(r"/feasibility/(D3|D14)(/|\s|$)")
ROUTE_B = re.compile(r"run_execskill\.py|skillopt[./]execskill|execskill-sbx-")
ALFWORLD = re.compile(r"alfworld", re.IGNORECASE)
SUMMARY = re.compile(r"^=*\s*(\d+ passed.*|.*\b(failed|error|errors|no tests ran)\b.*?)\s*=*$")
PYTEST_SECONDS = 3_600


def launch_env(base=None):
    """The environment of a route-B process: ``base`` (default ``os.environ``) without ``UNSET``, with
    ``PYTHONDONTWRITEBYTECODE=1``."""
    env = {key: value for key, value in (os.environ if base is None else base).items() if key not in UNSET}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _files(root):
    return [path for name in SNAPSHOT_DIRS for path in sorted((root / name).rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]


def sha256_list(root):
    """The sha256 list of the tree at ``root`` (``sha256sum`` lines "<hex>  <path>", sorted by path)."""
    root = safe_path(root)
    lines = sorted("%s  %s" % (hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(root).as_posix())
                   for p in _files(root))
    return "".join(line + "\n" for line in lines)


def env_files(root):
    """Every ``.env*`` file under ``root`` (plan §10 step 1: must be none)."""
    return sorted(p.relative_to(root).as_posix() for p in safe_path(root).rglob(".env*"))


def verify_snapshot(list_path, *, root=protocol.SNAPSHOT_ROOT, build_tree=protocol.BUILD_TREE, git_head):
    """Plan §10 step 1: the snapshot at ``root`` matches the sha256 list written on the build tree, line for line,
    and holds no ``.env*`` file. Returns the manifest's ``provenance`` block; ValueError otherwise."""
    root, list_path = safe_path(root), safe_path(list_path)
    listed = list_path.read_text(encoding="utf-8")
    found = sha256_list(root)
    if found != listed:
        missing = sorted(set(listed.splitlines()) ^ set(found.splitlines()))
        raise ValueError("The snapshot differs from its sha256 list: %s" % [line[66:] for line in missing[:5]])
    require(not env_files(root), "The snapshot holds .env files")
    require(type(git_head) is str and re.fullmatch(r"[0-9a-f]{40}", git_head), "The build tree's git HEAD")
    return {"build_tree": str(build_tree), "git_head": git_head, "snapshot_root": str(root),
            "sha256_list_sha256": hashlib.sha256(listed.encode("utf-8")).hexdigest(), "env_files_absent": True}


def zero_call_checks(root=protocol.SNAPSHOT_ROOT, *, python=protocol.INTERPRETER, run=subprocess.run):
    """The S0 pytest row on the snapshot: the registered command, the launch environment, no bytecode. Returns
    {"command", "returncode", "summary", "passed"}; ``run``: ``subprocess.run`` (tests pass a fake)."""
    root = safe_path(root)
    tests = sorted(p.relative_to(root).as_posix() for pattern in TEST_FILES for p in root.glob(pattern))
    require(tests, "No route-B tests under the snapshot")
    command = [str(python), "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests]
    done = run(command, cwd=str(root), env=launch_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
               timeout=PYTEST_SECONDS, check=False)
    output = done.stdout.decode("utf-8", "replace") if isinstance(done.stdout, bytes) else str(done.stdout)
    lines = [line for line in output.splitlines() if SUMMARY.match(line.strip())]
    summary = lines[-1].strip() if lines else ""
    return {"command": command, "returncode": done.returncode, "summary": summary,
            "passed": done.returncode == 0 and " passed" in summary and "failed" not in summary}


def processes():
    """[(pid, command line)] of every process, read from /proc (empty where /proc is unavailable)."""
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if raw:
            found.append((int(entry.name), raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()))
    return sorted(found)


def _containers(docker):
    if docker.binary is None:
        return None
    listed = docker.run([docker.binary, "ps", "-a", "--filter", "name=^/" + sandbox.PREFIX, "--format",
                         "{{.Names}}"], protocol.CLEANUP_SECONDS)
    return sorted(listed.stdout.decode("utf-8", "replace").split()) if listed.code == 0 else None


def leftovers(*, found=None, docker=None, own=None):
    """What remains after a stage (§10 S2 row; owner #3): route-B containers, route-B processes, ALFWorld processes.
    ``found``: [(pid, command line)] (default ``processes()``); ``own``: pids to ignore (default this process).
    ``verdict``: "clean", "leftovers" (anything of route B or an unexcluded ALFWorld process remains, or the
    container list cannot be read) or "cannot_judge" (only excluded D3/D14 workers remain)."""
    found = processes() if found is None else found
    own = {os.getpid(), os.getppid()} if own is None else set(own)
    excluded, route_b, alfworld = [], [], []
    for pid, command in found:
        if pid in own:
            continue
        if EXCLUDED.search(command):
            excluded.append({"pid": pid, "command": command[:200], "verdict": "cannot_judge"})
        elif ROUTE_B.search(command):
            route_b.append({"pid": pid, "command": command[:200]})
        elif ALFWORLD.search(command):
            alfworld.append({"pid": pid, "command": command[:200]})
    containers = _containers(docker or sandbox.Docker())
    if containers is None or containers or route_b or alfworld:
        verdict = "leftovers"
    else:
        verdict = "cannot_judge" if excluded else "clean"
    return {"containers": containers, "route_b": route_b, "alfworld": alfworld, "excluded": excluded,
            "verdict": verdict}
