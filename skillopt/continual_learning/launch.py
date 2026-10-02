"""Explicit, bounded process environment for a frozen ALFWorld learner launch.

Use this at a serial launcher boundary, never inside concurrent episode workers.
The backend deliberately does not mutate global ``ALFWORLD_DATA`` per episode.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager

from skillopt.continual_eval.core import require, safe_path


@contextmanager
def learning_environment(manifest):
    """Bind a natural ALFWorld launch to its declared root and restore on exit.

    An existing conflicting environment is an operator/configuration error, not
    permission to overwrite it. Fixtures and other benchmarks are untouched.
    This only checks deterministic launch prerequisites; it does not claim a
    native episode or a model call has succeeded.
    """
    if (manifest.get("benchmark") != "alfworld"
            or manifest["model"]["provider"] == "fixture"):
        yield
        return
    require(threading.current_thread() is threading.main_thread(),
            "ALFWorld launch environment must be bound on the main thread")
    runtime = manifest["runtime"]
    root = runtime.get("alfworld_data")
    require(type(root) is str and root and os.path.isabs(root),
            "ALFWorld learning needs an explicit absolute frozen data root")
    path = safe_path(root)
    require(path.is_dir() and (path / "logic/alfred.pddl").is_file()
            and (path / "logic/alfred.twl2").is_file(),
            "ALFWorld frozen data root or native logic files are unavailable")
    previous = os.environ.get("ALFWORLD_DATA")
    require(previous is None or previous == root,
            "Existing ALFWORLD_DATA differs from the frozen learning runtime")
    if previous is None:
        os.environ["ALFWORLD_DATA"] = root
    try:
        yield
    finally:
        # These launchers own a serial process scope; do not leave a root behind
        # for an unrelated later run, including on Pending/exception paths.
        if previous is None:
            os.environ.pop("ALFWORLD_DATA", None)
        else:
            os.environ["ALFWORLD_DATA"] = previous
