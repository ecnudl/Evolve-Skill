"""The call wrapper (registration §5.4 row 4, §13.2, §13.5): every model call of the protocol goes through it.

``Slots`` bound concurrency across every coevo5 process (one file lock per slot; a process that dies releases its
slots). An ``Endpoint`` is one model behind the rules for one unit attempt: a slot is held while a request is in
flight; a GLM-5.3 request first reserves its bound in the global ledger -- under the halt generation the attempt began
with, so a halt during the attempt refuses its every further call, even after a resume -- and is settled from its
receipt, attempt by attempt; a call that delivered nothing is re-sent identically after the cooldown. A receipt that
reports more than its reservation's bound assumed (§13.2) latches the endpoint, is recorded, and is settled at what it
reported by the ledger event that also halts every process; ``AssumptionBroken`` is raised at once: the endpoint sends
nothing more (no resend, no further step of an episode). Any failure of the ledger itself (a commit that may or may not
have taken effect, a refused operation) latches the endpoint the same way and pauses the cell (``LedgerFailure``),
whatever the frozen solver makes of the exception. A ``Recorder`` holds the calls of one cell: it is the
``call(system, user)`` the frozen solver receives, and it keeps what ``outcomes.classify`` and the cell runner read --
the receipts the solver received, and the wrapper's own flags (a refused call, an invalid receipt, a broken assumption,
a ledger failure).
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import random
import re
import time
from contextlib import contextmanager

from skillopt.continual_eval.core import require, safe_path

from . import ledger
from .budget import rooted
from .outcomes import AssumptionBroken, BudgetStop, LedgerFailure, public_error, undelivered
from .protocol import MAX_RESENDS, RESEND_COOLDOWN_SECONDS

BREACH = "reported_usage_beyond_reservation_bound"
USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")
EXCEPTION_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


class Slots:
    def __init__(self, root, name, count, *, poll=0.5, sleep=time.sleep):
        require(type(count) is int and count > 0 and name.replace("-", "").replace(".", "").isalnum(),
                "Invalid slot pool")
        self.root = safe_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.name, self.count, self.poll, self.sleep = name, count, poll, sleep

    def _path(self, suffix):
        return self.root / ("%s.%s.lock" % (self.name, suffix))

    def _gathering(self):
        """True while a ``hold_many`` gathers its slots: single holders then take no new slot, so a pool that never
        empties cannot starve the gatherer."""
        descriptor = os.open(self._path("gather"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            os.close(descriptor)
        return False

    def _take(self, index):
        """The slot's locked descriptor, or None when another holder has it."""
        descriptor = os.open(self._path(index), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        return descriptor

    @staticmethod
    def _release(descriptor):
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    @contextmanager
    def hold(self):
        while True:
            if not self._gathering():
                for index in random.sample(range(self.count), self.count):
                    descriptor = self._take(index)
                    if descriptor is None:
                        continue
                    try:
                        yield index
                    finally:
                        self._release(descriptor)
                    return
            self.sleep(self.poll)

    @contextmanager
    def hold_many(self, count):
        """``count`` slots held together for the whole block, for a frozen learner whose own workers keep up to
        ``count`` calls or native jobs open (a baseline's learning stage, §13.5). One such holder per pool at a time (a
        gate held throughout). It takes slots as they come free while single holders wait (``_gathering``); once it
        has them all, the single holders share the rest of the pool again."""
        require(type(count) is int and 0 < count <= self.count, "Invalid slot count")
        gate = os.open(self._path("many"), os.O_CREAT | os.O_RDWR, 0o600)
        gather, held = None, {}
        try:
            fcntl.flock(gate, fcntl.LOCK_EX)
            gather = os.open(self._path("gather"), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(gather, fcntl.LOCK_EX)
            while True:
                for index in range(self.count):
                    if index not in held and len(held) < count:
                        descriptor = self._take(index)
                        if descriptor is not None:
                            held[index] = descriptor
                if len(held) == count:
                    break
                self.sleep(self.poll)
            os.close(gather)
            gather = None
            yield sorted(held)
        finally:
            if gather is not None:
                os.close(gather)
            for descriptor in held.values():
                self._release(descriptor)
            os.close(gate)


def _request_hash(system, user):
    return hashlib.sha256((system + "\x00" + user).encode()).hexdigest()


class Endpoint:
    """``client``: an object with ``call(system, user) -> receipt`` (scripts/weak_solver_probe.Client). ``budget`` and
    ``scopes``: the ledger and the scopes a call is charged to -- GLM-5.3's, or (v3 §9) deepseek-v4-flash's own; None:
    uncharged (v1-v2's free deepseek route). An endpoint serves one unit attempt: built when the attempt begins, it
    takes the ledger's halt generation (``AssumptionBroken`` while the ledger is halted); the owner's recovery after a
    halt builds a new one for the new attempt (§13.4)."""

    def __init__(self, client, *, model, max_tokens, slots, budget=None, scopes=(), cooldown=RESEND_COOLDOWN_SECONDS,
                 sleep=time.sleep):
        require(budget is None or rooted(scopes), "A charged endpoint names one overall scope and only its model's")
        self.client, self.model, self.max_tokens = client, model, max_tokens
        self.slots, self.budget, self.scopes = slots, budget, tuple(scopes)
        self.cooldown, self.sleep = cooldown, sleep
        # the first broken assumption / ledger failure this endpoint saw: nothing more is sent
        self.halted = self.failed = None
        # kept across slot waits and resend cooldowns: a halt since the attempt began refuses every reservation
        self.generation = None if budget is None else budget.generation()

    def recorder(self, *, label, on_reply=None):
        return Recorder(self, label, on_reply)

    def send(self, system, user, recorder):
        """One request as sent; its record (with the receipt) is appended to the recorder."""
        size = ledger.request_bytes(system, user)
        entry = {"request_sha256": _request_hash(system, user), "request_bytes": size, "model": self.model,
                 "max_tokens": self.max_tokens, "started": time.time()}
        with self.slots.hold():
            self._latched(entry, recorder)
            rid = None
            if self.budget is not None:
                entry["reserved"] = ledger.reservation(size, self.max_tokens)
                try:
                    rid = self.budget.reserve(self.scopes, entry["reserved"], label=recorder.label,
                                              generation=self.generation)
                except BudgetStop as stop:
                    recorder.refused = True
                    recorder.sends.append({**entry, "refused": str(stop)})
                    raise
                except AssumptionBroken as stop:  # halted now, or since this attempt began (by any process)
                    self.halted = recorder.broken = str(stop)
                    recorder.sends.append({**entry, "halted": str(stop)})
                    raise
                except Exception as error:  # the reservation may or may not be recorded: nothing is sent
                    self._fail(recorder, error)
                    recorder.sends.append({**entry, "ledger_failure": recorder.failed})
                    raise
            receipt = exception = None
            try:
                receipt = self.client.call(system, user)
            except BaseException as exc:  # recorded and charged below, then raised to the solver
                exception = type(exc).__name__
                raise
            finally:
                broken = self._record(entry, receipt, exception, rid, size, recorder)
        if broken:
            raise AssumptionBroken(BREACH)
        return receipt

    def _latched(self, entry, recorder):
        """An endpoint that saw a broken assumption or a ledger failure sends nothing more."""
        if self.failed is not None:
            recorder.failed = self.failed
            recorder.sends.append({**entry, "ledger_failure": self.failed})
            raise LedgerFailure(self.failed)
        if self.halted is not None:
            recorder.broken = self.halted
            recorder.sends.append({**entry, "halted": self.halted})
            raise AssumptionBroken(self.halted)

    def _record(self, entry, receipt, exception, rid, size, recorder):
        """Latch a breach, record the send (with its receipt), then settle it; returns whether the assumption
        broke."""
        entry["seconds"] = round(time.time() - entry["started"], 3)
        if exception is None and not isinstance(receipt, dict):
            recorder.invalid = True  # row 1: a receipt that is not a mapping
        charged, broken = None, False
        if rid is not None:
            try:
                charged, broken = ledger.settle(receipt if isinstance(receipt, dict) else None, size, self.max_tokens)
            except ValueError:  # a receipt without its 1-4 attempts: charge the reservation, then pause
                charged = entry["reserved"]
                recorder.invalid = True
            entry.update(charged=charged, assumption_broken=broken)
        if broken:  # latched before anything is persisted: whatever happens next, nothing more is sent
            recorder.broken = self.halted = BREACH
        recorder.sends.append({**entry, "receipt": receipt, **({"exception": exception} if exception else {})})
        if rid is not None:
            try:
                self.budget.settle(rid, charged, detail=_detail(receipt), breach=BREACH if broken else None)
            except Exception as error:  # the settlement (and a breach's halt) may or may not be recorded
                self._fail(recorder, error)
                raise
        return broken

    def _fail(self, recorder, error):
        """A reservation or settlement failed: this endpoint and the cell are latched (the cell pauses). The ledger
        quarantined the failure under that operation's own lock -- halted, with what the failed change left open
        closed -- when it could still be written. Otherwise it is only halted here, as far as it can be: nothing is
        released (a reservation left open is charged in full once this process ends) and the owner reconciles the
        ledger before any resume (§13.4)."""
        self.failed = recorder.failed = (str(error) if isinstance(error, LedgerFailure)
                                         else "ledger_failure:" + type(error).__name__)
        if not getattr(error, "quarantined", False):
            try:
                self.budget.halt(self.failed, label=recorder.label)
            except Exception:  # noqa: BLE001 -- the ledger cannot be written; the process pauses all the same
                pass


def _detail(receipt):
    """What the shared ledger keeps of a receipt -- fixed categories and numbers only, since a receipt may carry text
    the provider chose (§0): the error type when the decision table names it (else ``other``), the three usage
    counts, and each attempt's HTTP status or transport exception class. The receipt itself stays in the cell's
    record."""
    if not isinstance(receipt, dict):
        return {"error_type": "no_receipt"}
    error = receipt.get("error_type")
    usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
    attempts = receipt.get("attempts") if isinstance(receipt.get("attempts"), list) else []
    return {"error_type": error if error is None or public_error(error) else "other",
            "usage": {field: usage.get(field) if type(usage.get(field)) is int else None for field in USAGE_FIELDS},
            "attempts": [_attempt(a) for a in attempts]}


def _attempt(attempt):
    status = attempt.get("status") if isinstance(attempt, dict) else None
    error = attempt.get("error") if isinstance(attempt, dict) else None
    if type(status) is int:
        return status
    return error if isinstance(error, str) and EXCEPTION_NAME.fullmatch(error) else "other"


class Recorder:
    def __init__(self, endpoint, label, on_reply):
        self.endpoint, self.label, self.on_reply = endpoint, label, on_reply
        self.receipts, self.sends = [], []
        self.refused = self.invalid = False
        self.broken = self.failed = None  # the reason of a broken assumption / a ledger failure

    def __call__(self, system, user):
        receipt = None
        for attempt in range(MAX_RESENDS + 1):
            if attempt:
                self.endpoint.sleep(self.endpoint.cooldown)
            receipt = self.endpoint.send(system, user, self)
            if not undelivered(receipt):
                break
        self.receipts.append(receipt)
        if self.on_reply is not None:
            self.on_reply()
        return receipt
