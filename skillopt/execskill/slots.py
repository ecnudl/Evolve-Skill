"""Route-B slot pools (docs/handoff/execskill-registration-v1-20261021.md §2.6, §4.1, §4.4 P4, §11 owner #10;
implementation plan §1, slots row, §4 and §5): the machine-wide concurrency bounds, their lock order and their waits.

Pools (``POOL_SIZES``; lock files under ``protocol.SLOT_ROOT``, shared by every route-B process):
- ``alfworld-episode`` (6): one per live ALFWorld episode, held for the whole episode (minutes to hours);
- ``execskill-sandbox-live`` (6, O12): one per live sandbox container, held as long as the container lives (an
  ALFWorld episode's container, a SpreadsheetBench unit's containers -- at most 2 per such unit, ``limited``);
- ``execskill-sandbox`` (4 until S0 registers its value): the per-call sandbox slot, held for seconds;
- the model pools ``glm-5.3`` (10) and ``deepseek-v4.1-flash-1017`` (8), held by the frozen Endpoint while a request
  is in flight (``with self.slots.hold():``, calls.py:155);
- ``spreadsheet-native`` (3; 2 when the S0 native peak RSS exceeds 2 GiB).

Lock order (``LOCK_ORDER``): a thread that holds slots takes a new one only from a later level -- episode, live
sandbox, sandbox call, model, native -- so no cycle of waits can form. ``assert_order`` refuses an acquisition that
breaks it (ConfigurationError) before any wait; one ``Holdings`` per process tracks each thread's held pools.

Waits: every pool but the per-call sandbox keeps the frozen untimed poll of ``calls.Slots.hold`` (calls.py:77-90) and
adds a log line every 300 s of waiting; such a wait never maps to P4 (§4.4: queueing for an episode or native lock does
not count). The per-call sandbox pool, whose holds last seconds, waits at most 600 s: the first timeout is logged and
the wait retried once; a second consecutive timeout raises ``SandboxUnavailable`` (P4).
"""
from __future__ import annotations

import random
import sys
import threading
import time
from contextlib import contextmanager

from skillopt.coevo5.calls import Slots
from skillopt.continual_eval.core import require

from .errors import ConfigurationError, SandboxUnavailable
from .protocol import (NATIVE_SLOTS_LOW_MEMORY, SANDBOX_SLOTS, SHORT_HOLD_SECONDS, SLOTS, SOLVERS,
                       WAIT_LOG_SECONDS)

EPISODE, LIVE, CALL, NATIVE = "alfworld-episode", "execskill-sandbox-live", "execskill-sandbox", "spreadsheet-native"
MODEL = "model"  # the level every model pool (protocol.SOLVERS) shares
LOCK_ORDER = (EPISODE, LIVE, CALL, MODEL, NATIVE)
LIVE_SANDBOX_CAP = SANDBOX_SLOTS[LIVE]
POOL_SIZES = {EPISODE: SLOTS[EPISODE], LIVE: LIVE_SANDBOX_CAP, CALL: SANDBOX_SLOTS[CALL],
              **{model: SLOTS[model] for model in SOLVERS}, NATIVE: SLOTS[NATIVE]}


def level(pool):
    """A pool's place in ``LOCK_ORDER``."""
    require(pool in POOL_SIZES, "Unknown slot pool: %s" % pool)
    return LOCK_ORDER.index(MODEL if pool in SOLVERS else pool)


def assert_order(held, pool):
    """Refuse (ConfigurationError) a slot of ``pool`` for a thread holding slots of the pools ``held`` unless ``pool``
    comes later in ``LOCK_ORDER`` than each of them."""
    for name in held:
        if level(name) >= level(pool):
            raise ConfigurationError("slot_lock_order: %s requested while holding %s" % (pool, name))


def _stderr(line):
    print(line, file=sys.stderr, flush=True)


class Holdings:
    """The pools whose slots each thread of a process holds, in acquisition order; shared by the process's pools."""

    def __init__(self):
        self._local = threading.local()

    def held(self):
        return getattr(self._local, "held", ())

    @contextmanager
    def holding(self, pool):
        held = self.held()
        self._local.held = held + (pool,)
        try:
            yield
        finally:
            self._local.held = held


class OrderedSlots(Slots):
    """``calls.Slots`` (one lock file per slot under ``root``; a process that dies releases its slots) with the
    route-B rules: the lock order, wait logging and the single short-hold timeout. ``clock`` and ``sleep``: the time
    source and the poll's sleep (a simulated clock in tests); ``log``: receives every wait and timeout line (default:
    stderr, the unit's sealed diagnostics file)."""

    def __init__(self, root, name, count, *, holdings, poll=0.5, sleep=time.sleep, clock=time.monotonic, log=_stderr):
        super().__init__(root, name, count, poll=poll, sleep=sleep)
        require(name in POOL_SIZES and isinstance(holdings, Holdings), "A registered pool, with its process's Holdings")
        self.holdings, self.clock, self.log = holdings, clock, log

    def hold(self, *, log_every_s=WAIT_LOG_SECONDS):
        """A slot for the block, waited for without a time limit (a log line every ``log_every_s`` seconds): never
        P4. The per-call sandbox pool is held with ``hold_short``."""
        require(self.name != CALL, "The per-call sandbox pool is held with hold_short")
        return self._slot(log_every_s=log_every_s)

    def hold_short(self, *, timeout_s=SHORT_HOLD_SECONDS, log_every_s=WAIT_LOG_SECONDS):
        """A per-call sandbox slot (§4.4 P4): a wait of ``timeout_s`` seconds without a slot is logged and retried
        once; a second consecutive one raises SandboxUnavailable."""
        require(self.name == CALL and timeout_s > 0, "Only the per-call sandbox pool waits with a timeout")
        return self._slot(log_every_s=log_every_s, timeout_s=timeout_s)

    def limited(self, cap):
        """One unit's view of this pool, holding at most ``cap`` of its slots at once (§2.6: a SpreadsheetBench unit
        keeps at most 2 live sandboxes)."""
        return UnitCap(self, cap)

    @contextmanager
    def _slot(self, *, log_every_s, timeout_s=None, unit=None):
        assert_order(self.holdings.held(), self.name)
        taken = self._wait(log_every_s, timeout_s, unit)
        if taken is None:  # only with a timeout
            self.log("slot_timeout pool=%s waited_s=%d retry=1" % (self.name, timeout_s))
            taken = self._wait(log_every_s, timeout_s, unit)
            if taken is None:
                raise SandboxUnavailable("sandbox_slot_timeout: %s busy for 2 x %d s" % (self.name, timeout_s))
        index, descriptor = taken
        try:
            with self.holdings.holding(self.name):
                yield index
        finally:
            self._release(descriptor)
            if unit is not None:
                unit.leave()

    def _wait(self, log_every_s, timeout_s, unit):
        """A free slot's (index, locked descriptor) -- after the unit's turn, when ``unit`` caps it -- polling as the
        frozen ``hold`` does; a log line each ``log_every_s`` seconds of waiting; None once ``timeout_s`` passed."""
        require(log_every_s > 0, "Invalid wait-log interval")
        start, logged = self.clock(), 0
        while True:
            if unit is None or unit.enter():
                taken = None
                try:
                    taken = self._try()
                finally:
                    if taken is None and unit is not None:
                        unit.leave()
                if taken is not None:
                    return taken
            waited = self.clock() - start
            if timeout_s is not None and waited >= timeout_s:
                return None
            while waited >= (logged + 1) * log_every_s:
                logged += 1
                self.log("slot_wait pool=%s waited_s=%d" % (self.name, logged * log_every_s))
            self.sleep(self.poll)

    def _try(self):
        """One pass of the frozen ``hold`` (calls.py:80-84): a free slot's (index, locked descriptor), or None."""
        if self._gathering():
            return None
        for index in random.sample(range(self.count), self.count):
            descriptor = self._take(index)
            if descriptor is not None:
                return index, descriptor
        return None


class UnitCap:
    """One unit's share of a pool: its threads hold at most ``cap`` of the pool's slots at once, waiting for their
    turn the same untimed, logged way."""

    def __init__(self, pool, cap):
        require(isinstance(pool, OrderedSlots) and pool.name != CALL and type(cap) is int and 0 < cap <= pool.count,
                "Invalid unit cap")
        self.pool, self.cap, self.in_use = pool, cap, 0
        self._lock = threading.Lock()

    def hold(self, *, log_every_s=WAIT_LOG_SECONDS):
        return self.pool._slot(log_every_s=log_every_s, unit=self)

    def enter(self):
        with self._lock:
            if self.in_use == self.cap:
                return False
            self.in_use += 1
            return True

    def leave(self):
        with self._lock:
            self.in_use -= 1


def pools(root, *, sizes=None, poll=0.5, sleep=time.sleep, clock=time.monotonic, log=_stderr):
    """Every route-B pool under ``root`` (``protocol.SLOT_ROOT`` in a run), sharing one ``Holdings``. ``sizes``: only
    the registered changes -- the per-call sandbox pool's S0 value, the native pool 3 -> 2 (plan §5)."""
    sizes = {**POOL_SIZES, **(sizes or {})}
    require(set(sizes) == set(POOL_SIZES) and type(sizes[CALL]) is int and sizes[CALL] > 0
            and sizes[NATIVE] in (POOL_SIZES[NATIVE], NATIVE_SLOTS_LOW_MEMORY)
            and all(sizes[name] == POOL_SIZES[name] for name in POOL_SIZES if name not in (CALL, NATIVE)),
            "Only the per-call sandbox and native pool sizes may change")
    holdings = Holdings()
    return {name: OrderedSlots(root, name, count, holdings=holdings, poll=poll, sleep=sleep, clock=clock, log=log)
            for name, count in sizes.items()}
