"""Pace logical requests without changing frozen source/routing experiments.

Usage: paced_scope_mvp.py --entry source|routing --min-interval 2 [--] ORIGINAL_ARGS

Each process admits logical backend calls at least min-interval seconds apart;
the original worker count still bounds concurrent in-flight requests. Original
model, prompts, token settings, scoring, retries and backoff are unchanged.
Internal retries are NOT separately paced, so this is not a wire-request rate
guarantee and does not guarantee avoidance of HTTP 429. This ordinary transport
throttle does not bypass provider limits. Other processes are not coordinated.

The launcher preloads only existing session configuration, creates no session,
and writes no experiment artifacts or amendments. Preserve failed-run caches;
use the preregistered new output directory and record the transport amendment
separately. The temporary backend wrapper is restored even on exceptional exit.
"""

from __future__ import annotations

import argparse
import importlib
import math
import sys
import threading
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _interval(value) -> float:
    if isinstance(value, bool):
        raise ValueError("Minimum interval must be a positive finite number of seconds")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Minimum interval must be a positive finite number of seconds")
    return number


class StartPacer:
    """One lock and a monotonic deadline; no queue and no accumulated burst credit."""

    def __init__(self, min_interval=2.0, *, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = _interval(min_interval)
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next_start = None

    def wait(self) -> float:
        with self._lock:
            now = self._clock()
            while self._next_start is not None and now < self._next_start:
                self._sleep(self._next_start - now)
                now = self._clock()
            self._next_start = now + self.min_interval
            return now


@contextmanager
def paced_backend(backend, min_interval=2.0, *, clock=time.monotonic, sleep=time.sleep):
    """Change dispatch timing only; release the pacing lock before backend I/O."""
    pacer = StartPacer(min_interval, clock=clock, sleep=sleep)
    original = backend._chat_messages_impl

    @wraps(original)
    def paced(*args, **kwargs):
        pacer.wait()
        return original(*args, **kwargs)

    backend._chat_messages_impl = paced
    try:
        yield
    finally:
        backend._chat_messages_impl = original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument("--entry", required=True, choices=("source", "routing"))
    parser.add_argument("--min-interval", type=_interval, default=2.0,
                        help="Minimum seconds between logical backend starts in this process (default: 2)")
    args, remaining = parser.parse_known_args(argv)
    if remaining and remaining[0] == "--":
        remaining = remaining[1:]
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    # Keep every SkillOpt/model import below the existing session preloader.
    session_launcher = importlib.import_module("scripts.source_retention_session_mvp")
    session_launcher.preload_session_environment(REPO)
    backend = importlib.import_module("skillopt.model.openai_compatible_backend")
    delegate = (session_launcher if args.entry == "source"
                else importlib.import_module("scripts.retention_routing_mvp"))
    with paced_backend(backend, args.min_interval):
        return delegate.main(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
