"""The global GLM-5.3 token ledger (registration §13.2-13.4), shared by every coevo5 process on the machine.

A call's reservation R is checked against every scope it belongs to (its step's cap, its chain's cap, the overall
ceiling) and admitted only when settled + every open reservation + R fits all of them. Otherwise it waits while
reservations of live processes are open in an exceeded scope; with none open, the call is refused: a budget stop
(``outcomes.BudgetStop``). A receipt settles its reservation (``ledger.settle``); a reservation whose process ended
without a receipt keeps its whole amount and is settled at it when found. A receipt reporting more than its bound
assumed (a breach) is settled at what it reported (the overrun is recorded) and, by the same journal event, halts the
ledger: no reservation is admitted until the owner's recorded decision (``resume``, §13.4). Every reservation names the
halt generation its unit attempt began with (``generation``) and is refused once any halt happened since -- also while
it waited, and even after a resume: the attempt is redone, never continued.

Durability: one file lock serializes every change. A change is an event appended to ``events.jsonl`` and synced before
``state.json`` -- a cache of the log up to a byte offset -- is replaced, so a crash between the two is repaired by
replaying the log's tail on the next access; a torn last line (a change never acknowledged) is dropped. A reservation or
settlement that fails otherwise than by a budget stop or a halt (a commit that may or may not have taken effect, a
refused operation, an unreadable ledger) is quarantined before its lock is released: one event halts the ledger and
closes what the failed change left open -- a reservation recorded for a call never sent is released, a settlement left
unrecorded is applied -- so nothing is admitted in between and a torn tail keeps both or neither. ``LedgerFailure``
follows; when even that event cannot be written, the owner reconciles the ledger before any resume (§13.4).
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.continual_eval.core import require, safe_path

from .outcomes import AssumptionBroken, BudgetStop, LedgerFailure

OVERALL = "overall"
DEEPSEEK = "deepseek"  # v3 §9: deepseek-v4-flash's own overall scope, apart from GLM-5.3's
INITIAL = {"offset": 0, "caps": {}, "declared": {}, "settled": {}, "open": {}, "halted": None, "halts": 0}
CLOSING = ("settle", "orphan")


def chain_scope(chain):
    return "chain:" + chain


def deepseek_scope(chain=None, step=None, kind=None):
    """v3 §9: deepseek-v4-flash's own scopes -- all of it, one chain's, or one step's of a chain (``kind`` as in
    ``step_scope``) -- apart from every GLM-5.3 scope."""
    if chain is None:
        return DEEPSEEK
    if step is None:
        return DEEPSEEK + ":" + chain
    require(kind in ("learning", "evaluation"), "Unknown step kind")
    return "%s:%s:%s:%s" % (DEEPSEEK, chain, step, kind)


def rooted(scopes):
    """Whether a call's scopes name one overall scope and only scopes of its model: GLM-5.3's (``OVERALL``) or, v3
    §9, deepseek-v4-flash's (``DEEPSEEK``); a call is never charged to both."""
    scopes = set(scopes)
    deepseek = {s for s in scopes if s == DEEPSEEK or s.startswith(DEEPSEEK + ":")}
    return (OVERALL in scopes and not deepseek) or (DEEPSEEK in scopes and deepseek == scopes)


def step_scope(chain, step, kind):
    """``kind``: "learning" or "evaluation"; the shared stage-0 evaluation of E-glm and the two baselines is its own
    step ("stage0-glm")."""
    require(kind in ("learning", "evaluation"), "Unknown step kind")
    return "step:%s:%s:%s" % (chain, step, kind)


def _process(pid):
    """(state, start) of a Linux process from /proc, (None, None) where unavailable. A zombie (Z) or dead (X) process
    has ended; the start time (clock ticks since boot) tells a reused pid from the reserving process."""
    try:
        fields = Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()
        return fields[0], fields[19]
    except (OSError, IndexError):
        return None, None


def _halt(state, reason, label):
    """The first reason is kept; ``halts`` counts every halt (the generation a reservation must still find)."""
    state["halted"] = state["halted"] or {"reason": reason, "label": label}
    state["halts"] += 1


def _close(state, event):
    """Settle an open reservation at the event's charge; a breach (a receipt beyond its bound) also halts."""
    entry = state["open"].pop(event["id"])
    for scope in entry["scopes"]:
        state["settled"][scope] = state["settled"].get(scope, 0) + event["charged"]
    if event.get("breach"):
        _halt(state, event["breach"], entry["label"])


def _apply(state, event):
    kind = event["event"]
    if kind in ("declare", "raise"):
        state["caps"][event["scope"]] = event["cap"]
        if kind == "declare":  # the registered cap; a raise changes the cap in force only
            state["declared"][event["scope"]] = event["cap"]
    elif kind == "reserve":
        state["open"][event["id"]] = {"amount": event["amount"], "scopes": event["scopes"], "label": event["label"],
                                      **event["owner"]}
    elif kind in CLOSING:
        _close(state, event)
    elif kind == "halt":  # a quarantine also closes what a failed change left open: one event, both or neither
        for closing in event.get("close", ()):
            _close(state, closing)
        _halt(state, event["reason"], event["label"])
    elif kind == "resume":
        state["halted"] = None
    else:
        require(kind == "refuse", "Unknown ledger event")


class Budget:
    def __init__(self, root, *, poll=5.0, sleep=time.sleep):
        self.root = safe_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.poll, self.sleep = poll, sleep
        self.owner = {"pid": os.getpid(), "host": socket.gethostname(), "start": _process(os.getpid())[1]}

    # -------------------------------------------------------------------------------------------------- state
    def _load(self):
        path, log = self.root / "state.json", self.root / "events.jsonl"
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(INITIAL)
        size = log.stat().st_size if log.exists() else 0
        require(state["offset"] <= size, "The ledger state is ahead of its event log")
        if size > state["offset"]:  # changes logged but not yet in the state (an interrupted commit)
            with log.open("rb") as handle:
                handle.seek(state["offset"])
                tail = handle.read()
            complete = tail.rfind(b"\n") + 1
            for line in tail[:complete].splitlines():
                _apply(state, json.loads(line))
            state["offset"] += complete
            if complete < len(tail):  # a torn last line: a change that was never acknowledged
                with log.open("r+b") as handle:
                    handle.truncate(state["offset"])
        return state

    def _commit(self, state, events):
        data = "".join(json.dumps(event, sort_keys=True) + "\n" for event in events).encode()
        with (self.root / "events.jsonl").open("ab") as log:
            log.write(data)
            log.flush()
            os.fsync(log.fileno())
        state["offset"] += len(data)
        temporary = self.root / (".state-%s.json" % uuid.uuid4().hex)
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(state, sort_keys=True))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.root / "state.json")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    @contextmanager
    def _state(self, *, guard=None):
        """(state, emit) under the lock; ``emit(event)`` applies a change and logs it. Events are committed when the
        block ends, also when it raises (a refusal records itself, and any orphan it settled, before raising). A failed
        commit raises ``LedgerFailure`` carrying the events. ``guard``: the label of a reservation or settlement, whose
        every failure other than a budget stop or a halt is quarantined under this same lock (``_quarantine``)."""
        with (self.root / ".lock").open("a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            events = []
            try:
                try:
                    state = self._load()

                    def emit(event):
                        event = {"time": time.time(), **event}
                        _apply(state, event)
                        events.append(event)

                    try:
                        yield state, emit
                    finally:
                        if events:
                            try:
                                self._commit(state, events)
                            except Exception as error:  # the log may hold them: uncertain until the next replay
                                raise LedgerFailure("ledger_commit_failed:" + type(error).__name__,
                                                    events) from error
                except (BudgetStop, AssumptionBroken):
                    raise
                except Exception as error:
                    if guard is None:
                        raise
                    raise self._quarantine(error, events, guard) from error
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _quarantine(self, error, events, label):
        """Still under the lock of the reservation or settlement that failed (``events``: its changes, recorded or
        not), one event halts the ledger and closes what the failed change left open: its reservation -- a call that
        is never sent -- is released at 0, its settlement or orphan, when not recorded, is applied. Returns the
        ``LedgerFailure`` to raise, ``quarantined`` when that event was written."""
        reason = str(error) if isinstance(error, LedgerFailure) else "ledger_failure:" + type(error).__name__
        try:
            state = self._load()  # what the failed commit left in the log, replayed (a torn line dropped)
            close = [{"event": "release", "id": event["id"], "charged": 0, "reason": "not_sent_after_ledger_failure"}
                     if event["event"] == "reserve" else event
                     for event in events
                     if event["event"] in ("reserve",) + CLOSING and event["id"] in state["open"]]
            quarantine = {"time": time.time(), "event": "halt", "reason": reason, "label": label, "close": close}
            _apply(state, quarantine)
            self._commit(state, [quarantine])
        except Exception:  # noqa: BLE001 -- the ledger cannot be written: the owner reconciles it (§13.4)
            return LedgerFailure(reason, events)
        return LedgerFailure(reason, events, quarantined=True)

    def declare(self, caps):
        """Register scope caps (tokens). A scope's cap, once declared, can change only by an explicit owner-authorized
        raise (``raise_cap``), recorded as a protocol deviation; declaring the registered caps again (a restarted
        runner) keeps a raised cap in force."""
        require(isinstance(caps, dict) and caps and all(type(v) is int and v > 0 for v in caps.values()),
                "Positive integer caps required")
        with self._state() as (state, emit):
            for scope, cap in caps.items():
                if scope in state["caps"]:
                    require(state["declared"][scope] == cap, "A declared cap differs: " + scope)
                else:
                    emit({"event": "declare", "scope": scope, "cap": cap})

    def raise_cap(self, scope, cap, *, deviation):
        require(type(cap) is int and isinstance(deviation, str) and deviation.strip(), "A raise records its reason")
        with self._state() as (state, emit):
            require(scope in state["caps"] and cap > state["caps"][scope], "Only a declared cap can be raised")
            emit({"event": "raise", "scope": scope, "from": state["caps"][scope], "cap": cap, "deviation": deviation})

    # ------------------------------------------------------------------------------------------- reservations
    @staticmethod
    def _sum(state, scope):
        return state["settled"].get(scope, 0) + sum(r["amount"] for r in state["open"].values() if scope in r["scopes"])

    def _alive(self, entry):
        if entry["host"] != self.owner["host"]:
            return True  # another machine's process cannot be checked: keep waiting for it
        try:
            os.kill(entry["pid"], 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        status, start = _process(entry["pid"])
        if status in ("Z", "X"):
            return False
        return entry["start"] is None or start == entry["start"]

    def _settle_orphans(self, state, emit):
        for rid, entry in list(state["open"].items()):
            if not self._alive(entry):
                emit({"event": "orphan", "id": rid, "charged": entry["amount"], "scopes": entry["scopes"],
                      "label": entry["label"], "reason": "no_receipt_process_ended"})

    def close_orphans(self):
        """Settle every open reservation whose process ended (at its whole amount, as a waiting reservation would);
        returns how many stay open, their processes still running."""
        with self._state() as (state, emit):
            self._settle_orphans(state, emit)
            return len(state["open"])

    def generation(self):
        """The ledger's halt generation, taken by a unit attempt when it begins (``calls.Endpoint``): its every
        reservation must still find it. Raises ``AssumptionBroken`` while the ledger is halted: no attempt begins."""
        with self._state() as (state, _):
            if state["halted"] is not None:
                raise AssumptionBroken("ledger_halted:" + state["halted"]["reason"])
            return state["halts"]

    def reserve(self, scopes, amount, *, label, generation):
        """The reservation's id once it fits every scope. ``generation``: the one its unit attempt began with. Raises
        ``BudgetStop`` when it cannot fit and nothing in an exceeded scope is still open; ``AssumptionBroken`` while
        the ledger is halted or once any halt happened since that generation (also while this call waited, and even
        after a resume); ``LedgerFailure`` when the ledger fails (quarantined, ``_state``)."""
        scopes = sorted(set(scopes))
        require(rooted(scopes) and type(amount) is int and amount > 0 and type(generation) is int,
                "A reservation names one overall scope (v3: GLM-5.3's or deepseek's) and its attempt's halt "
                "generation")
        while True:
            with self._state(guard=label) as (state, emit):
                if state["halted"] is not None or state["halts"] != generation:
                    emit({"event": "refuse", "amount": amount, "scopes": scopes, "label": label, "halted": True})
                    raise AssumptionBroken("ledger_halted:" + state["halted"]["reason"] if state["halted"]
                                           else "ledger_halted_since_the_attempt_began")
                missing = [s for s in scopes if s not in state["caps"]]
                require(not missing, "Undeclared scopes: %s" % missing)
                exceeded = [s for s in scopes if self._sum(state, s) + amount > state["caps"][s]]
                if not exceeded:
                    rid = uuid.uuid4().hex
                    emit({"event": "reserve", "id": rid, "amount": amount, "scopes": scopes, "label": label,
                          "owner": dict(self.owner)})
                    return rid
                self._settle_orphans(state, emit)
                waiting = [r for r in state["open"].values() if set(r["scopes"]) & set(exceeded)]
                if not waiting:
                    exceeded = [s for s in scopes if self._sum(state, s) + amount > state["caps"][s]]
                    if exceeded:
                        emit({"event": "refuse", "amount": amount, "scopes": scopes, "label": label,
                              "exceeded": exceeded})
                        raise BudgetStop("budget_stop:" + ",".join(exceeded))
                    continue  # settling the orphans made room: reserve on the next turn
            self.sleep(self.poll)

    def settle(self, rid, charged, *, detail, breach=None):
        """Close a reservation at ``charged`` tokens: never more than its amount (§13.2), except a receipt that broke
        the reservation's assumption (``breach``: the reason), settled at what it reported; that same event halts the
        ledger. A refused or failed settlement is quarantined (``_state``) and raises ``LedgerFailure``."""
        require(breach is None or (isinstance(breach, str) and breach), "A breach names its reason")
        with self._state(guard="settle:%s" % rid) as (state, emit):
            entry = state["open"].get(rid)
            require(entry is not None, "Unknown or already settled reservation")
            require(type(charged) is int and charged >= 0 and (breach is not None or charged <= entry["amount"]),
                    "A settlement exceeds its reservation")
            emit({"event": "settle", "id": rid, "charged": charged, "reserved": entry["amount"],
                  "overrun": max(0, charged - entry["amount"]), "scopes": entry["scopes"], "label": entry["label"],
                  "detail": detail, **({"breach": breach} if breach else {})})

    def halt(self, reason, *, label):
        """Stop admitting reservations in every process (e.g. after a ledger failure the ledger could not quarantine,
        §13.2): the run pauses."""
        with self._state() as (_, emit):
            emit({"event": "halt", "reason": reason, "label": label})

    def resume(self, *, decision):
        """Admit reservations again after the owner's recorded decision (§13.4 b)."""
        require(isinstance(decision, str) and decision.strip(), "A resume records the owner's decision")
        with self._state() as (state, emit):
            require(state["halted"] is not None, "The ledger is not halted")
            emit({"event": "resume", "decision": decision})

    def snapshot(self):
        """{scope: {"cap", "settled", "open"}} and the halt -- infrastructure information only (monitoring, owner
        decisions)."""
        with self._state() as (state, _):
            scopes = {scope: {"cap": cap, "settled": state["settled"].get(scope, 0),
                              "open": sum(r["amount"] for r in state["open"].values() if scope in r["scopes"])}
                      for scope, cap in sorted(state["caps"].items())}
            return {**scopes, "halted": state["halted"]} if state["halted"] else scopes
