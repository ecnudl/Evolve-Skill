"""Bounded read-only wait for a previously identified owned process session.

This is operational resource handoff, not experiment scoring or a retry policy.
The caller binds the identity to its sealed observation, boot and launcher.
"""
import subprocess
import time


def _snapshot(remaining):
    value = subprocess.run(["ps", "-eo", "pid=,pgid=,sid="], capture_output=True, text=True,
                           timeout=min(5.0, remaining), check=True)
    return [tuple(map(int, line.split())) for line in value.stdout.splitlines()]


def wait_owned_session_exit(identity, *, timeout=30.0, observe=_snapshot,
                            clock=time.monotonic, sleep=time.sleep):
    fields = ("queue_pid", "parent_pane_pid", "process_group", "session_id")
    if any(type(identity.get(key)) is not int or identity[key] < 1 for key in fields):
        raise ValueError("Invalid owned process identity")
    if type(timeout) not in (int, float) or not 0 < timeout <= 30:
        raise ValueError("Invalid bounded handoff timeout")
    deadline, polls = clock() + timeout, 0
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            raise ValueError("Owned process handoff timed out; no process was stopped")
        rows = observe(remaining)
        polls += 1
        if (not rows or any(type(row) not in (list, tuple) or len(row) != 3
                           or any(type(v) is not int or v < 0 for v in row) for row in rows)):
            raise ValueError("Process snapshot unavailable or invalid")
        live = any(row[0] in (identity["queue_pid"], identity["parent_pane_pid"])
                   or row[1] == identity["process_group"] or row[2] == identity["session_id"] for row in rows)
        if not live:
            return {"status": "owned_session_absent", "polls": polls, "processes_remaining": 0}
        sleep(max(0, min(1.0, deadline - clock())))
