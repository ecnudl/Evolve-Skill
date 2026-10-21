"""Connectivity probe log and its quiet-window check for paid queues (no model call, no credential).

``log`` appends one line per probe -- ``<epoch seconds> ok|fail <duration>`` -- using the same probe as the
evaluation tool's connectivity gate (a TCP connection to the credential-free gateway of a prepared stage's frozen
model record plus an HTTP CONNECT to the provider host). ``quiet`` exits 0 only when the last ``--count`` entries
are all ``ok``, their times strictly increase, the newest is fresh and the window is no longer than the probes can
take -- so a dead probe's old successes, duplicated lines or one fresh line after old ones never look quiet.

Usage:
  python scripts/connectivity_probe.py log --manifest <prepared stage>/manifest.json --out <log> [--count 8640]
  python scripts/connectivity_probe.py quiet --log <log> --count 12       # exit 0 quiet, 1 not (yet)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INTERVAL = 10.0
HOST = "open.bigmodel.cn"


def quiet(lines, count, now, *, interval=INTERVAL, slack=60.0):
    """True iff the last ``count`` log entries are all ok, strictly increasing in time, the newest at most ``slack``
    seconds old and the whole window no longer than ``count`` probes can take (each at most a 20 s probe plus the
    interval, plus the slack)."""
    entries = []
    for line in lines[-count:]:
        parts = line.split()
        if len(parts) < 2:
            return False
        try:
            entries.append((float(parts[0]), parts[1]))
        except ValueError:
            return False
    if count < 1 or len(entries) != count or any(status != "ok" for _, status in entries):
        return False
    times = [t for t, _ in entries]
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        return False
    return 0 <= now - times[-1] <= slack and times[-1] - times[0] <= (count - 1) * (interval + 20.0) + slack


def log(manifest, out, *, interval=INTERVAL, count=8640):
    from scripts.run_active_evidence_panel_eval import bounded, tunnel_probe

    proxy = json.loads(Path(manifest).read_text(encoding="utf-8"))["model"].get("proxy")
    with open(out, "a", encoding="utf-8") as handle:
        for _ in range(count):
            start = time.time()
            ok = bounded(lambda: tunnel_probe(proxy, HOST), 20.0)
            handle.write("%d %s %.2f\n" % (start, "ok" if ok else "fail", time.time() - start))
            handle.flush()
            time.sleep(max(0.0, interval - (time.time() - start)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("log")
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=8640)
    p = sub.add_parser("quiet")
    p.add_argument("--log", required=True)
    p.add_argument("--count", type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == "log":
        log(args.manifest, args.out, count=args.count)
        return 0
    path = Path(args.log)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return 0 if quiet(lines, args.count, time.time()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
