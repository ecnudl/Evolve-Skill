"""Chain D's solver route (registrar "Owner instructions 2026-10-22 17:0x and 17:3x", row "deepseek route B";
registration §4.1, §21): which of chain D's two providers (``client.ROUTES``) its solver calls, the route-B pin of the
launch manifest, and the operator's ``switch-route``.

- Route state is per chain and lives in the chain root as a write-once-per-switch history: ``route-<n>.json`` (n = 1,
  2, ...), one sealed record ``route-switch`` per switch, each naming the run, the chain, the route it leaves and the
  one it takes, the pause that motivated it (the paused attempt and its ``unit-status`` record hash), the operator's
  reason and the previous switch's record hash. No file: route A, where chain D starts and stays (registrar row).
  ``current`` verifies the whole history on every read (contiguous numbers, chained hashes, this run and chain).
- The chain D client factory reads it at every unit start (``manifest.setting_of`` binds the route a chain process
  runs on: the route's client, ledger-bound branch and longest probe reply; ``manifest._clients`` reads the history
  again at every client build and refuses a route that changed under a running process, ``check_bound``), so a unit
  never switches mid-unit: a switch takes effect only in the next process, at a unit boundary -- the paused unit's
  redo, which runs whole on the new route as the redo rules define.
- ``switch`` is the operator's step after a unit paused with kind ``balance_exhausted`` (``client.balance_signal``): it
  refuses unless the chain is idle -- its runner lock (``chain.RUNNER_LOCK``) is free and held while it writes, and no
  unit lock under the chain root is owned, as ``chain.terminate`` checks (registrar decision on ticket I1-3: the
  operator checks that no chain process is alive before ``recover``; here the code checks it too) -- and unless the
  chain's latest open pause is ``balance_exhausted`` and no earlier switch answered it (one pause, one switch), or an
  explicit reason is given. ``recover`` of the paused attempt and ``run`` follow (the command line prints them).
- ``pin`` is the manifest's ``clients.routes[chain][route]`` block (only route B of chain D exists): the route's
  credential file (by path; never read here), its request model, the gateway, the reasoning setting, per-bench nominal
  M and read timeout, chain D's slot pool, the route's echo set, the client source hash and the ledger bound B of
  branch N (the conservative bound: route B has no probe of its own), with ``longest`` the chain-D solver block's S1
  longest reply on branch N, else ``S1B_CEILING`` (on branch E every S1-b reply stayed within its M <= 256): B =
  max(4M, ceil(1.5 x longest)). ``check_pins`` re-derives every field, B included, and requires the route-B pin in a
  ``main`` manifest (``protocol.MAIN``).
"""
from __future__ import annotations

import datetime
import hashlib
import re
from contextlib import contextmanager
from pathlib import Path

from skillopt.coevo5.cells import exclusive
from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import client, protocol
from .errors import ConfigurationError

ROUTED = {"D": (client.ROUTE_A, client.ROUTE_B)}  # chain -> its routes, the first its registered start
PINNED = {"D": (client.ROUTE_B,)}  # the routes a manifest pins beside the chain's solver block (route A is that block)
KIND = "route-switch"
FILE = re.compile(r"route-([1-9][0-9]*)\.json")
RUNNER_LOCK = ".runner.lock"  # chain.RUNNER_LOCK, restated: chain.py imports this module (asserted equal in the tests)
BALANCE_EXHAUSTED = "balance_exhausted"  # errors.STOP_KINDS[BalanceExhausted]
S1B_CEILING = max(protocol.S1B_TOKENS)  # branch E: every S1-b reply within its M, the largest M being 256
BRANCH = "N"  # route B's ledger-bound branch (registrar row: conservative bound, no probe of its own)
FIELDS = frozenset({"route", "backend", "model", "url_host", "env_path", "proxy", "reasoning_effort", "M", "B",
                    "branch", "longest", "read_timeout", "slots", "response_model_ids", "client_source_sha"})
SWITCH_FIELDS = frozenset({"run", "chain", "n", "from", "to", "model", "reason", "pause", "previous", "by", "date"})


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------- the history
def history(chain_root, *, run=None, chain="D"):
    """The verified switch records of ``chain`` under ``chain_root``, in order (module docstring); raises ValueError
    on a gap, a broken chain of hashes, another run (when ``run`` is given) or another chain."""
    require(chain in ROUTED, "Chain %s has one route" % chain)
    root = safe_path(chain_root)
    found = {}
    for path in root.glob("route-*.json"):
        match = FILE.fullmatch(path.name)
        require(match is not None, "Not a route record: %s" % path.name)
        found[int(match.group(1))] = path
    require(sorted(found) == list(range(1, len(found) + 1)), "The route history of chain %s has a gap" % chain)
    records, now = [], ROUTED[chain][0]
    for n in range(1, len(found) + 1):
        value = protocol.verified(read_json(found[n]), KIND)
        require(set(value) - {"version", "evidence", protocol.RECORD_HASH} == SWITCH_FIELDS,
                "A route record holds the registered fields")
        require(value["chain"] == chain and value["n"] == n and value["from"] == now and value["to"] in ROUTED[chain]
                and value["to"] != now, "Route record %d of chain %s does not follow the history" % (n, chain))
        require(value["previous"] == (records[-1][protocol.RECORD_HASH] if records else None),
                "Route record %d of chain %s does not name the previous switch" % (n, chain))
        require(run is None or value["run"] == run, "A route record of another run")
        records.append(value)
        now = value["to"]
    return records


def current(chain_root, *, run=None, chain="D"):
    """The route ``chain`` runs on now: the last switch's, else the registered start (route A)."""
    records = history(chain_root, run=run, chain=chain)
    return records[-1]["to"] if records else ROUTED[chain][0]


def check_bound(chain_root, bound, *, run, chain="D"):
    """At every client build (a unit start): the chain's route is still the one this process bound (module
    docstring); ConfigurationError otherwise -- the unit pauses instead of switching mid-run."""
    try:
        found = current(chain_root, run=run, chain=chain)
    except ValueError as error:
        raise ConfigurationError("The route history of chain %s: %s" % (chain, error)) from None
    if found != bound:
        raise ConfigurationError("Chain %s's route is %s but this process runs on route %s: a route switch takes "
                                 "effect in a new process only (run the chain again)" % (chain, found, bound))
    return found


# ------------------------------------------------------------------------------------------------ the idle chain
def _owned(lock):
    try:
        with exclusive(lock):
            return False
    except ValueError:
        return True


@contextmanager
def idle(chain_root):
    """Held while the chain is idle (module docstring; ``chain.terminate``): its runner lock is taken for the whole
    block (ValueError while a runner runs) and no unit lock under the chain root is owned."""
    root = safe_path(chain_root)
    require(root.is_dir(), "No chain root at %s" % root)
    with exclusive(root / RUNNER_LOCK):
        locks = [*root.glob("*/.lock"), *root.glob("*/*/.lock"), *root.glob("*/*/*/.lock")]
        busy = sorted(str(lock.parent) for lock in locks if _owned(lock))
        require(not busy, "Units of the chain are still running: %s" % busy[:3])
        yield root


def open_pauses(chain_root):
    """The chain's open pauses, latest first: (attempt directory, its verified ``unit-status`` record) of every
    paused ``status.json`` of an attempt without ``recovery.json`` in a unit without ``unit.json`` (step units, test
    units and root scans), the most recently written first."""
    root = safe_path(chain_root)
    found = []
    for status in [*root.glob("*/attempt-*/status.json"), *root.glob("*/*/attempt-*/status.json")]:
        attempt = status.parent
        if (attempt / "recovery.json").exists() or (attempt.parent / "unit.json").exists():
            continue
        value = protocol.verified(read_json(status), "unit-status")
        if value.get("status") == "paused":
            found.append((status.stat().st_mtime_ns, str(attempt), attempt, value))
    return [entry[2:] for entry in sorted(found, reverse=True)]


def latest_pause(chain_root):
    """The chain's latest open pause (``open_pauses``); None when nothing is paused."""
    found = open_pauses(chain_root)
    return found[0] if found else None


def switch(chain_root, *, to, run, evidence, chain="D", reason=None, now=None):
    """The operator's route switch (module docstring): refused unless the chain is idle, ``to`` is another route of
    the chain, and the chain's latest open pause is ``balance_exhausted`` and named by no earlier switch record, or
    ``reason`` is given (a non-blank text, recorded). Writes ``route-<n+1>.json`` once while holding the runner lock.
    Returns {"record", "path", "pause", "pauses"} (``pause``: the latest open pause's attempt directory or None;
    ``pauses``: [(attempt directory, kind)] of every open pause, latest first -- each needs the owner's ``recover``
    before the chain runs on)."""
    require(chain in ROUTED and to in ROUTED[chain], "Route %s is not a route of chain %s" % (to, chain))
    require(reason is None or (isinstance(reason, str) and reason.strip()), "A reason is a non-blank text")
    with idle(chain_root) as root:
        records = history(root, run=run, chain=chain)
        here = records[-1]["to"] if records else ROUTED[chain][0]
        require(to != here, "Chain %s already runs on route %s" % (chain, to))
        pauses = open_pauses(root)
        paused = pauses[0] if pauses else None
        kind = paused[1]["kind"] if paused is not None else None
        pause = None if paused is None else {
            "attempt": str(paused[0].relative_to(root)), "kind": kind, "status_sha256": paused[1][protocol.RECORD_HASH]}
        spent = pause is not None and any(found["pause"] == pause for found in records)  # one pause, one switch
        require(reason is not None or (kind == BALANCE_EXHAUSTED and not spent), "Chain %s's latest pause is %s, not "
                "a %s pause that no switch answered yet: a switch then needs an explicit --reason" % (
                    chain, (kind or "none") + (" (answered by a route record)" if spent else ""), BALANCE_EXHAUSTED))
        n = len(records) + 1
        value = protocol.record(KIND, evidence, {
            "run": run, "chain": chain, "n": n, "from": here, "to": to, "model": client.ROUTES[to].model,
            "reason": reason, "pause": pause, "previous": records[-1][protocol.RECORD_HASH] if records else None,
            "by": "operator", "date": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()})
        path = root / ("route-%d.json" % n)
        write_json(path, value)
    return {"record": value, "path": path, "pause": None if paused is None else paused[0],
            "pauses": [(attempt, found["kind"]) for attempt, found in pauses]}


# ------------------------------------------------------------------------------------------- the manifest's pin
def pin(chain, route, *, env_path, solver_block):
    """The manifest's ``clients.routes[chain][route]`` block (module docstring). ``env_path``: the route's credential
    file, recorded by path (never read here); ``solver_block``: the manifest's ``clients.solver[chain]`` block, whose
    S1 branch and longest reply give route B's ``longest``."""
    require(chain in PINNED and route in PINNED[chain], "Only route B of chain D is pinned beside a solver block")
    require(isinstance(solver_block, dict) and solver_block.get("model") == protocol.CHAINS[chain],
            "The chain's own solver block")
    found = solver_block.get("longest")
    longest = found if solver_block.get("branch") == "N" else S1B_CEILING
    require(type(longest) is int and longest > 0, "The solver block's S1 longest reply (branch N)")
    model, provider, benches = protocol.CHAINS[chain], client.ROUTES[route], protocol.BENCHES
    return {"route": route, "backend": provider.backend, "model": provider.model, "url_host": provider.host,
            "env_path": str(safe_path(env_path)), "proxy": protocol.GATEWAY,
            "reasoning_effort": protocol.REASONING_EFFORT, "M": {b: protocol.solver_tokens(model, b) for b in benches},
            "B": {b: protocol.ledger_bound(model, b, branch=BRANCH, longest=longest) for b in benches},
            "branch": BRANCH, "longest": longest, "read_timeout": {b: protocol.read_timeout(model, b) for b in benches},
            "slots": protocol.SLOTS[model], "response_model_ids": sorted(provider.response_model_ids),
            "client_source_sha": _sha(client.__file__)}


def check_pins(clients, *, configuration=None):
    """The clients block's optional ``routes`` (module docstring): {chain: {route: block}} for chains the manifest
    runs, each block equal to ``pin`` re-derived from its own env path and the chain's solver block. A ``main``
    manifest must pin route B of chain D (registrar row "deepseek route B"). Raises ValueError."""
    pinned = clients.get("routes")
    if configuration in (protocol.MAIN, protocol.MAIN_V2, protocol.MAIN_V2_1, protocol.MAIN_V2_2):  # main's chains
        require(isinstance(pinned, dict) and isinstance(pinned.get("D"), dict) and client.ROUTE_B in pinned["D"],
                "A main manifest pins chain D's route B (clients.routes.D.B = routes.pin(...); registrar row "
                "\"deepseek route B\")")
    if pinned is None:
        return
    require(isinstance(pinned, dict) and pinned and set(pinned) <= set(PINNED), "Route pins per routed chain")
    for chain, blocks in pinned.items():
        require(chain in clients["solver"], "Chain %s's routes need its solver block" % chain)
        require(isinstance(blocks, dict) and blocks and set(blocks) <= set(PINNED[chain]),
                "Chain %s pins only %s" % (chain, list(PINNED[chain])))
        for route, block in blocks.items():
            require(isinstance(block, dict) and set(block) == FIELDS, "A route block holds the registered fields")
            expected = pin(chain, route, env_path=block["env_path"], solver_block=clients["solver"][chain])
            same = {key for key in FIELDS if block[key] == expected[key]}
            require(same == FIELDS, "Chain %s's route %s block differs from the registration: %s"
                    % (chain, route, sorted(FIELDS - same)))


def block_of(manifest, chain, route):
    """The manifest block that governs ``chain`` on ``route``: route A's is the chain's solver block, another
    route's its pin (ConfigurationError when the manifest pins none)."""
    if route == ROUTED[chain][0]:
        return manifest["clients"]["solver"][chain]
    found = (manifest["clients"].get("routes") or {}).get(chain) or {}
    if route not in found:
        raise ConfigurationError("Chain %s runs on route %s, which the manifest does not pin (clients.routes)"
                                 % (chain, route))
    return found[route]


def config(block, bench):
    """``client.solver_client``'s config of a route block on ``bench`` (route B: ``route`` named)."""
    return {client.ROUTE_KEY: block["route"], "env_path": block["env_path"], "proxy": block["proxy"],
            "max_tokens": block["M"][bench], "read_timeout": block["read_timeout"][bench]}
