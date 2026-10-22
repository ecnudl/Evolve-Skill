"""Consumption registry (registration §3.4, §3.1 "never used"; plan §2.7, T-REG-1..6).

One append-only file per namespace and benchmark, ``<history root>/consumption/<chain>/<bench>.jsonl``. The history
root (``/data/execskill-history``) is shared by the smoke, pilot and formal roots, so the registry does not depend on
any run root. Namespaces (owner rule 22:3x (c)): chain ``G``, chain ``D`` and ``smoke``. Both chains cut the same
slices from the same fixed order (§3.2), so the same item is consumed once in EACH chain -- a replication on the same
items, disclosed in every table, never two independent pieces of evidence -- and never twice within one namespace.

Every line records one state change of one item; the reader folds the lines in file order. States move forward only:
``registered`` -> ``dispatched`` (written and flushed before the first cell is sent) -> ``decided`` (after the
decision is written). A registered item the router did not send is ``routed_not_dispatched`` and returns to the
supply: it may be registered again later. A redo of a unit reuses its own registration -- the same items with the same
purpose, nothing new is written -- while another unit of the same namespace touching an item it does not hold raises
``ConsumptionConflict`` (the run pauses). A unit is its label AND its run root (Codex finding #7, §3.1-§3.4): labels
such as ``G/s1-searchqa/run`` repeat in every run root, so an item registered by the same label under another root is
another unit's (a conflict), never a redo's own registration; the run root is the canonical absolute path
(``run_identity``) the registration names, and the later moves name it too -- through a registry bound to the run root
(``bound``; every step unit's, ``step._Step.unit``) or the ``run_root`` keyword. A move that names no run root (an
unbound registry's caller: fixtures) is matched by its label alone. Deciding an item the unit already decided writes
nothing, so a unit's settlement is idempotent (Codex finding #8: ``units.run_unit`` settles once the unit's completion
evidence is persisted, and settles again when a recovery finishes that commit). A call that fails on any of its items
writes nothing. Writers hold an exclusive ``fcntl`` lock on the file's ``.lock`` sibling while they fold, check and
append; readers hold it shared.

Every line is a protocol record (``protocol.record``: ``version`` ``fivebench-execskill-v1-consumption``,
``evidence``, ``record_sha256``); a line that fails ``protocol.verified``, or a folded sequence that is not a legal
forward move, stops the reader (a hand-edited registry is never trusted).
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from skillopt.coevo5.data import item_hash
from skillopt.continual_eval.core import require, safe_path

from .errors import ConsumptionConflict
from .protocol import BENCHES, EVIDENCE, HISTORY_ROOT, NAMESPACES, record, verified

RECORD_KIND = "consumption"  # version fivebench-execskill-v1-consumption
PURPOSES = ("smoke", "run", "accept", "accept_probe", "examiner", "detector_holdout")  # plan §2.7
REGISTERED, DISPATCHED, DECIDED, RELEASED = "registered", "dispatched", "decided", "routed_not_dispatched"
STATES = (REGISTERED, DISPATCHED, DECIDED, RELEASED)
HELD = frozenset({REGISTERED, DISPATCHED, DECIDED})  # not available to the supply
FIELDS = frozenset({"version", "chain", "bench", "item_id", "item_hash", "state", "purpose", "unit", "run_root",
                    "attempt", "ts", "evidence", "record_sha256"})
_RANK = {REGISTERED: 0, DISPATCHED: 1, DECIDED: 2}
WRITE, REUSE = "write", "reuse"


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_identity(run_root):
    """The canonical run root of a registration (Codex finding #7): its absolute path (``safe_path``: no parent
    traversal, no symlink), the immutable identity a unit label is qualified by."""
    require(isinstance(run_root, (str, os.PathLike)) and str(run_root), "A run root is a path")
    return str(safe_path(run_root))


def _owns(held, unit, run_root):
    """Whether the unit moving an item is the one holding it: the same label and -- when the move names it -- the same
    run root (Codex finding #7)."""
    return held["unit"] == unit and (run_root is None or held["run_root"] == run_root)


def _move(target, held, unit, purpose, run_root=None):
    """The verdict on moving one item to ``target`` for ``unit`` of ``run_root`` (None: a move that names no run root,
    matched by its label alone): ``WRITE`` (a forward move), ``REUSE`` (the unit's own state already, nothing to
    write), ``("conflict", text)`` or ``("invalid", text)``. ``held`` is the item's folded last line (None: never
    registered in this namespace)."""
    if held is not None and held["state"] == RELEASED:
        if target == REGISTERED:
            return WRITE
        if target == RELEASED and _owns(held, unit, run_root):
            return REUSE
        return ("invalid", "a released item is back in the supply; register it first")
    if held is not None and not _owns(held, unit, run_root):
        return ("conflict", "%s by unit %s of run root %s" % (held["state"], held["unit"], held["run_root"]))
    if target == REGISTERED:
        if held is None:
            return WRITE
        if held["state"] == DECIDED:
            return ("invalid", "a decided item is consumed; it cannot be registered again")
        if held["purpose"] != purpose:
            return ("invalid", "registered by this unit for purpose %s" % held["purpose"])
        return REUSE
    if held is None:
        return ("invalid", "not registered")
    if target == RELEASED:
        if held["state"] == REGISTERED:
            return WRITE
        return ("invalid", "a %s item was sent; it cannot be released" % held["state"])
    step = _RANK[target] - _RANK[held["state"]]
    if step < 0:
        return ("invalid", "states move forward only (%s -> %s)" % (held["state"], target))
    if step > 1:
        return ("invalid", "%s before %s" % (target, DISPATCHED))
    return WRITE if step == 1 else REUSE


class Registry:
    """The consumption registry under ``root`` (tests pass a temporary directory; runs use ``HISTORY_ROOT``).
    ``evidence`` labels every line this instance writes (registration §1). ``run_root``: the run root every move of
    this instance names (``bound``; Codex finding #7), None for an unbound registry."""

    def __init__(self, root=HISTORY_ROOT, *, evidence, clock=_utc_now, run_root=None):
        require(evidence in EVIDENCE, "Unknown evidence label")
        self.root = safe_path(root)
        self.evidence = evidence
        self.clock = clock
        self.run_root = None if run_root is None else run_identity(run_root)

    def bound(self, run_root):
        """This registry with every move naming ``run_root`` (canonical, ``run_identity``): the registry of one run
        root's units (``step._Step.unit``; Codex finding #7)."""
        return Registry(self.root, evidence=self.evidence, clock=self.clock, run_root=run_root)

    def _run_root(self, run_root):
        """The run root a move names: the keyword's, else the bound one (None when neither: matched by label)."""
        if run_root is None:
            return self.run_root
        run_root = run_identity(run_root)
        require(self.run_root is None or run_root == self.run_root,
                "A move of another run root through a bound registry")
        return run_root

    def path(self, chain, bench):
        require(chain in NAMESPACES, "Unknown consumption namespace")
        require(bench in BENCHES, "Unknown benchmark")
        return self.root / "consumption" / chain / (bench + ".jsonl")

    @contextmanager
    def _locked(self, chain, bench, mode):
        path = self.path(chain, bench)
        path.parent.mkdir(parents=True, exist_ok=True)
        with safe_path(path.with_name(bench + ".lock")).open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), mode)
            try:
                yield path
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _fold(self, path, chain, bench):
        """{item_id: last line} of a registry file, every line checked and every move re-validated."""
        held = {}
        if not path.exists():
            return held
        for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            invalid = "Consumption registry line %d of %s is not a valid record" % (number, path)
            try:
                line = verified(json.loads(text), RECORD_KIND)
            except ValueError as error:
                raise ValueError(invalid) from error
            require(set(line) == FIELDS and line["chain"] == chain and line["bench"] == bench
                    and line["state"] in STATES, invalid)
            previous = held.get(line["item_id"])
            require(_move(line["state"], previous, line["unit"], line["purpose"], line["run_root"]) == WRITE
                    and (previous is None or previous["state"] == RELEASED
                         or previous["item_hash"] == line["item_hash"]),
                    "Consumption registry line %d of %s is not a forward move" % (number, path))
            held[line["item_id"]] = line
        return held

    def entries(self, chain, bench):
        """{item_id: folded last line} of a namespace and benchmark."""
        with self._locked(chain, bench, fcntl.LOCK_SH) as path:
            return self._fold(path, chain, bench)

    def consumed(self, chain, bench):
        """The ids of the items a namespace holds or used (registered, dispatched or decided); released items are
        back in the supply."""
        return frozenset(i for i, line in self.entries(chain, bench).items() if line["state"] in HELD)

    def _apply(self, target, chain, bench, items, *, unit, purpose=None, run_root=None, attempt):
        require(type(unit) is str and unit, "A unit name is required")
        require(type(attempt) is int and attempt >= 1, "Attempts are numbered from 1")
        require(target != REGISTERED or purpose in PURPOSES, "Unknown purpose")
        require(target != REGISTERED or (purpose == "smoke") == (chain == "smoke"),
                "Purpose 'smoke' is the smoke namespace's only purpose")
        require(target != REGISTERED or run_root is not None or self.run_root is not None,
                "A registration names its run root")
        run_root = self._run_root(run_root)
        ids = [str(item["task_id"]) for item in items]
        require(len(set(ids)) == len(ids), "An item is listed twice")
        with self._locked(chain, bench, fcntl.LOCK_EX) as path:
            held = self._fold(path, chain, bench)
            lines = []
            for item, item_id in zip(items, ids):
                previous = held.get(item_id)
                verdict = _move(target, previous, unit, purpose, run_root)
                if type(verdict) is tuple:
                    kind, text = verdict
                    message = "%s/%s item %s: %s" % (chain, bench, item_id, text)
                    if kind == "conflict":
                        raise ConsumptionConflict(message)
                    raise ValueError(message)
                hashed = item_hash(item)
                require(previous is None or previous["state"] == RELEASED or previous["item_hash"] == hashed,
                        "%s/%s item %s changed since it was registered" % (chain, bench, item_id))
                if verdict == REUSE:
                    continue
                source = previous if target != REGISTERED else None
                line = record(RECORD_KIND, self.evidence, {
                    "chain": chain, "bench": bench, "item_id": item_id, "item_hash": hashed, "state": target,
                    "purpose": source["purpose"] if source else purpose, "unit": unit,
                    "run_root": source["run_root"] if source else run_root, "attempt": attempt, "ts": self.clock()})
                lines.append(json.dumps(line, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
            if lines:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("".join(lines))
                    handle.flush()
                    os.fsync(handle.fileno())
            return len(lines)

    def register(self, chain, bench, items, *, unit, purpose, run_root=None, attempt=1):
        """Register items for one unit of ``run_root`` (before any routing or dispatch; a bound registry's run root
        when None); returns the number of lines written (0 when a redo reuses its own registration)."""
        return self._apply(REGISTERED, chain, bench, items, unit=unit, purpose=purpose, run_root=run_root,
                           attempt=attempt)

    def dispatch(self, chain, bench, items, *, unit, attempt=1, run_root=None):
        """Mark registered items dispatched -- called, and flushed, before the first cell of the items is sent."""
        return self._apply(DISPATCHED, chain, bench, items, unit=unit, attempt=attempt, run_root=run_root)

    def decide(self, chain, bench, items, *, unit, attempt=1, run_root=None):
        """Mark dispatched items decided, after the unit's decision record is written; deciding them again writes
        nothing (idempotent settlement, Codex finding #8)."""
        return self._apply(DECIDED, chain, bench, items, unit=unit, attempt=attempt, run_root=run_root)

    def release(self, chain, bench, items, *, unit, attempt=1, run_root=None):
        """Return registered, never dispatched items to the supply (``routed_not_dispatched``: routed outside A*, or
        a round not run because A* was too small)."""
        return self._apply(RELEASED, chain, bench, items, unit=unit, attempt=attempt, run_root=run_root)
