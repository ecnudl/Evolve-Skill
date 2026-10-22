"""Route-B slot pools under a simulated clock (implementation plan §8: T-SLOT-1, T-SLOT-2; registration §2.6, §4.4 P4;
plan §4, §5). Real lock files under the test's directory and real threads; only time is simulated, so a run of hours
takes a second. Offline and deterministic in what is asserted."""
from __future__ import annotations

import heapq
import math
import random
import threading
from collections import Counter

import pytest

from skillopt.execskill import protocol, slots
from skillopt.execskill.errors import ConfigurationError, SandboxUnavailable
from skillopt.execskill.slots import CALL, EPISODE, LIVE, NATIVE

DEEPSEEK, GLM = protocol.CHAINS["D"], protocol.CHAINS["G"]
JOIN_SECONDS = 120  # real seconds: a deadlock fails the test instead of hanging it


class VirtualTime:
    """A clock shared by ``workers`` threads: ``sleep`` blocks the calling thread until simulated time reaches its
    wake-up, and time advances only when every unfinished worker sleeps (to the earliest wake-up)."""

    def __init__(self, workers):
        self.now, self.running, self.sequence, self.timers = 0.0, workers, 0, []
        self.condition = threading.Condition()

    def clock(self):
        with self.condition:
            return self.now

    def sleep(self, seconds):
        with self.condition:
            self.sequence += 1
            woken = []
            heapq.heappush(self.timers, (self.now + seconds, self.sequence, woken))
            self.running -= 1
            self._advance()
            while not woken:
                self.condition.wait()

    def finished(self):
        with self.condition:
            self.running -= 1
            self._advance()

    def _advance(self):
        if self.running or not self.timers:
            return
        self.now = max(self.now, self.timers[0][0])
        while self.timers and self.timers[0][0] <= self.now:
            heapq.heappop(self.timers)[2].append(True)
            self.running += 1
        self.condition.notify_all()


class Usage:
    """The most slots each pool (or unit) had in use at once."""

    def __init__(self):
        self.lock, self.now, self.peak = threading.Lock(), Counter(), Counter()

    def enter(self, *names):
        with self.lock:
            for name in names:
                self.now[name] += 1
                self.peak[name] = max(self.peak[name], self.now[name])

    def leave(self, *names):
        with self.lock:
            for name in names:
                self.now[name] -= 1


def _run(clock, workers):
    """Start one daemon thread per worker function, each reporting to ``clock`` when it ends; returns the errors."""
    errors = []

    def body(work):
        try:
            work()
        except BaseException as error:  # noqa: BLE001 -- reported to the test
            errors.append(error)
        finally:
            clock.finished()

    threads = [threading.Thread(target=body, args=(work,), daemon=True) for work in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_SECONDS)
    assert not [thread for thread in threads if thread.is_alive()], "deadlock"
    return errors


# ------------------------------------------------------------------------------------------------- T-SLOT-1
def test_t_slot_1_heavy_tailed_episodes_all_finish_without_p4(tmp_path):
    rng = random.Random(protocol.SEED)
    sigma = math.log(1900 / 300) / 1.2815515655446004  # lognormal: median 300 s, p90 1,900 s
    durations = [[rng.lognormvariate(math.log(300), sigma) for _ in range(4)] for _ in range(16)]
    clock, lines, usage, waits, done = VirtualTime(16), [], Usage(), [], []
    pool = slots.pools(tmp_path, poll=20, sleep=clock.sleep, clock=clock.clock, log=lines.append)

    def worker(index):
        def work():
            for episode, duration in enumerate(durations[index]):
                asked = clock.clock()
                with pool[EPISODE].hold():
                    waits.append(clock.clock() - asked)
                    with pool[LIVE].hold():
                        usage.enter(EPISODE, LIVE)
                        for _ in range(3):  # three steps: a hook call in the sandbox, then the model
                            with pool[CALL].hold_short():
                                usage.enter(CALL)
                                clock.sleep(2)
                                usage.leave(CALL)
                            with pool[DEEPSEEK].hold():
                                usage.enter(DEEPSEEK)
                                clock.sleep(duration / 3)
                                usage.leave(DEEPSEEK)
                        usage.leave(EPISODE, LIVE)
                done.append((index, episode))
        return work

    assert _run(clock, [worker(index) for index in range(16)]) == []
    assert sorted(done) == [(w, e) for w in range(16) for e in range(4)]  # every episode finished, none was P4
    assert usage.peak[EPISODE] == 6 and usage.peak[LIVE] <= 6 and usage.peak[CALL] <= 4 and usage.peak[DEEPSEEK] <= 8
    assert max(waits) > protocol.SHORT_HOLD_SECONDS  # untimed: far longer than the short-hold timeout, still no P4
    assert any(line.startswith("slot_wait pool=alfworld-episode waited_s=") for line in lines)
    assert not [line for line in lines if line.startswith("slot_timeout")]


def test_t_slot_1_a_four_hour_wait_is_only_logged(tmp_path):
    clock, lines = VirtualTime(2), []
    holdings = slots.Holdings()
    pool = slots.OrderedSlots(tmp_path, EPISODE, 1, holdings=holdings, poll=60, sleep=clock.sleep, clock=clock.clock,
                              log=lines.append)
    acquired = []

    def holder():
        with pool.hold():
            clock.sleep(14_410)

    def waiter():
        clock.sleep(1)
        with pool.hold():
            acquired.append(clock.clock())

    assert _run(clock, [holder, waiter]) == []
    assert acquired == [14_461]  # polls at 1, 61, ..., 14,401 failed; the holder left at 14,410
    assert lines == ["slot_wait pool=alfworld-episode waited_s=%d" % (300 * n) for n in range(1, 49)]


# ------------------------------------------------------------------------------------------------- T-SLOT-2
def test_t_slot_2_lock_order(tmp_path):
    pool = slots.pools(tmp_path, poll=0.01)
    assert slots.LOCK_ORDER == ("alfworld-episode", "execskill-sandbox-live", "execskill-sandbox", "model",
                                "spreadsheet-native")
    with pool[EPISODE].hold(), pool[LIVE].hold(), pool[CALL].hold_short(), pool[GLM].hold(), pool[NATIVE].hold():
        assert pool[EPISODE].holdings.held() == (EPISODE, LIVE, CALL, GLM, NATIVE)
    out_of_order = [(DEEPSEEK, EPISODE), (LIVE, LIVE), (GLM, DEEPSEEK), (NATIVE, CALL), (CALL, LIVE), (NATIVE, GLM)]
    for first, second in out_of_order:
        hold = pool[first].hold_short if first == CALL else pool[first].hold
        with hold():
            with pytest.raises(ConfigurationError, match="slot_lock_order"):
                with (pool[second].hold_short if second == CALL else pool[second].hold)():
                    pass
            assert pool[first].holdings.held() == (first,)
        assert pool[first].holdings.held() == ()
    for name in (EPISODE, LIVE, CALL, NATIVE):  # a refused acquisition took no slot
        taken = [pool[name]._take(index) for index in range(pool[name].count)]
        assert None not in taken
        for descriptor in taken:
            pool[name]._release(descriptor)
    with pytest.raises(ValueError):
        pool[CALL].hold()
    with pytest.raises(ValueError):
        pool[LIVE].hold_short()
    with pytest.raises(ValueError):
        slots.pools(tmp_path, sizes={EPISODE: 8})
    assert slots.pools(tmp_path, sizes={CALL: 3, NATIVE: 2})[NATIVE].count == 2


def test_t_slot_2_live_sandboxes_capped_overall_and_per_spreadsheet_unit(tmp_path):
    clock, usage = VirtualTime(14), Usage()
    pool = slots.pools(tmp_path, poll=5, sleep=clock.sleep, clock=clock.clock, log=lambda line: None)
    rng = random.Random(protocol.SEED)
    units = {"sb-1": pool[LIVE].limited(2), "sb-2": pool[LIVE].limited(2)}

    def sheet(unit):
        def work():
            for _ in range(4):
                with units[unit].hold():
                    usage.enter(LIVE, unit)
                    with pool[CALL].hold_short():
                        clock.sleep(1)
                    with pool[DEEPSEEK].hold(), pool[NATIVE].hold():
                        clock.sleep(rng.uniform(30, 300))
                    usage.leave(LIVE, unit)
        return work

    def episode():
        clock.sleep(1)  # the sheet units take their two live sandboxes first (t = 0), the episodes the rest (t = 1)
        for _ in range(3):
            with pool[EPISODE].hold(), pool[LIVE].hold():
                usage.enter(LIVE)
                clock.sleep(rng.uniform(100, 900))
                usage.leave(LIVE)

    errors = _run(clock, [sheet("sb-1")] * 4 + [sheet("sb-2")] * 4 + [episode] * 6)
    assert errors == []
    assert usage.peak[LIVE] == slots.LIVE_SANDBOX_CAP == 6
    assert usage.peak["sb-1"] == usage.peak["sb-2"] == protocol.LIVE_SANDBOX_UNIT_CAP["spreadsheetbench"] == 2
    assert units["sb-1"].in_use == units["sb-2"].in_use == 0


@pytest.mark.parametrize("held_for, outcome, timeouts", [
    (None, 1_201, 1),  # never released: two consecutive 600 s windows -> P4
    (900, 901, 1),  # released during the retry: one logged timeout, then the slot
    (300, 301, 0),  # released within the first window
])
def test_t_slot_2_short_hold_times_out_once_then_stops(tmp_path, held_for, outcome, timeouts):
    clock, lines, result = VirtualTime(2), [], []
    pool = slots.pools(tmp_path, sizes={CALL: 1}, poll=10, sleep=clock.sleep, clock=clock.clock, log=lines.append)

    def holder():
        with pool[CALL].hold_short():
            clock.sleep(5_000 if held_for is None else held_for)

    def caller():
        clock.sleep(1)
        try:
            with pool[CALL].hold_short():
                result.append(("slot", clock.clock()))
        except SandboxUnavailable:
            result.append(("P4", clock.clock()))

    assert _run(clock, [holder, caller]) == []
    assert result == [("P4" if held_for is None else "slot", outcome)]
    assert sum(line.startswith("slot_timeout pool=execskill-sandbox waited_s=600") for line in lines) == timeouts
