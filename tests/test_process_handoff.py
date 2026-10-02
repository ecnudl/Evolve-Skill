"""Synthetic process snapshots only: no sleeps, processes, APIs or signals."""
import subprocess

import pytest

from scripts.process_handoff import wait_owned_session_exit

IDENTITY = {"queue_pid": 40, "parent_pane_pid": 39, "process_group": 39, "session_id": 39}


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_exit_marker_may_precede_shell_and_child_exit():
    clock = Clock()
    snapshots = iter([[(39, 39, 39), (40, 39, 39)], [(41, 39, 39)], [(100, 100, 100)]])
    result = wait_owned_session_exit(IDENTITY, observe=lambda _: next(snapshots), clock=clock, sleep=clock.sleep)
    assert result == {"status": "owned_session_absent", "polls": 3, "processes_remaining": 0}
    assert clock.now == 2


@pytest.mark.parametrize("row", [(40, 100, 100), (39, 100, 100), (100, 39, 100), (100, 100, 39)])
def test_any_owner_group_or_session_remaining_times_out_without_actions(row):
    clock = Clock()
    with pytest.raises(ValueError, match="timed out"):
        wait_owned_session_exit(IDENTITY, timeout=3, observe=lambda _: [row], clock=clock, sleep=clock.sleep)
    assert clock.now == 3


@pytest.mark.parametrize("rows", [[], [(1, 2)], [(1, True, 3)], [(1, -1, 3)], [[1, 2, "3"]]])
def test_missing_or_untyped_observation_does_not_authorize_handoff(rows):
    with pytest.raises(ValueError, match="snapshot"):
        wait_owned_session_exit(IDENTITY, observe=lambda _: rows)


def test_process_observation_failure_propagates_without_allowing_handoff():
    def failed(_):
        raise subprocess.TimeoutExpired("ps", 5)
    with pytest.raises(subprocess.TimeoutExpired):
        wait_owned_session_exit(IDENTITY, observe=failed)


@pytest.mark.parametrize("field", IDENTITY)
def test_bool_is_not_a_process_identity(field):
    with pytest.raises(ValueError, match="identity"):
        wait_owned_session_exit({**IDENTITY, field: True})


@pytest.mark.parametrize("timeout", [0, -1, 31, True, float("inf"), float("nan")])
def test_timeout_is_bounded(timeout):
    with pytest.raises(ValueError, match="timeout"):
        wait_owned_session_exit(IDENTITY, timeout=timeout)
