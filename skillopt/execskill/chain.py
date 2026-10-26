"""A route-B chain (protocol ``fivebench-execskill-v1``; registration §5, §8.1, §9.3, §9.4, §11, §21; implementation
plan §1 chain row, §5; T-CHAINS-1): a copy of ``coevo5.chain`` (chain.py:58-314) for the two chains G and D.

Copied: one runner owns a chain while it runs (``.runner.lock``; a second runner fails at once); every terminal marker
(``chain.json``, ``chain-complete.json``, ``chain-terminated.json``) names its run and chain; the pinned files are
verified before the chain starts (a mismatch refuses it and writes nothing) and again before every stage (a mismatch
terminates a started chain, §9.4); nothing resumes by itself -- a pause returns, the owner records ``recovery.json`` or
terminates; an evaluation unit runs in a child process whose stdout and stderr are a sealed file from its first byte
(chain.py:153-166), and a child that ends before its attempt leaves a paused attempt (chain.py:185-192); only an idle
chain can be terminated (chain.py:303-314). What changes:

- the chains are route B's G (solver glm-5.3) and D (deepseek-v4.1-flash-1017), both starting from the empty package
  (§5, §21); each runs on its own ledger (``budgets.ledger_root``: ``<root>/shared/ledger-<chain>``, declaring only
  ``budgets.chain_caps(chain)`` and the first-call scope ``budgets.first_call_caps(chain)``; ticket fixer-5), so a
  halt in one chain never stops the other (§9.3), and has its own
  consumption namespace (``registry``, §3.4); their steps see the same slice items;
- a step is ``learn(setting, chain_root, chain, k, bench, parent) -> (package, step record)`` -- ``step.learn``
  in a run; the pinned files are verified again before every unit of a step (``check_pins``, plan §2.9); the chain
  reads the order of the manifest's run configuration (``protocol.order_of(setting)``; registrar 17:0x: the pilots'
  two benches or main's five) and no stage-0 read (§8.1: the run reads the test sets once, at the end);
- memory (§5, §11 owner #10): machine-wide, a SpreadsheetBench unit holds the ``memory-heavy`` lock exclusively and an
  ALFWorld unit shares it, so two SpreadsheetBench units never run at once and SpreadsheetBench never runs beside
  ALFWorld, in either chain; QA units take no such lock (``heavy``). The lock follows every bench whose cells a unit
  runs, not only its step's: a later step's self-test running an earlier SpreadsheetBench set holds it exclusively
  (``heavy_mode``; Codex finding #5);
- the first-call confirmation (registrar addendum 2026-10-22 14:10, row 7; ``first_call``): before the chain's first
  paid unit, one solver call alone on a registered fixture prompt, charged to ``<c>:confirm``; ``confirm.json`` is
  written once and reused, a failure pauses the chain (``first_call_unconfirmed``) before any unit attempt;
- chain G's cost check (§9.3, owner rule 22:3x (c)): after chain G's first run unit, ``cap_check`` compares the
  measured per-cell cost against every chain-G scope (the caller's zero-call arithmetic); a breach writes
  ``cap-check-G.json`` and pauses chain G only -- in a configuration whose cost check pauses
  (``protocol.COST_CHECK_PAUSES``); in main it records its factor and never pauses (registrar 17:0x), and the read
  gate still applies that factor;
- the one test read (§8.1, §9.3): F = C (nothing accepted) is not read (``test-read.json``: ``not_read``) -- in a
  stage-read configuration (``protocol.STAGE_READ``, main-v2) only when no step passed on a package with a procedure,
  its read units running every step's package as well (``evaluation.stage_rows``); otherwise
  the owner's read consent is checked once for the chain (``read_consent``, registrar addendum 14:10 row 9: missing,
  the chain waits in ``read-waiting.json`` and no read attempt is opened), the remaining chain budget must cover 1.3 x
  the S-E6-corrected test-read estimate of the read units still to run (``TEST_START_FACTOR``; ``read_estimate_record``;
  chain G's corrected by its cost check's factor, row 8; a relaunch prices only the units not yet complete, registrar
  addendum 15:3x, ticket P2C-2), else the chain pauses for the owner; the five units run as children side by side
  under the memory lock;
- the command line's adapters (ticket A13-1): ``run_manifest`` runs a chain from the verified manifest (its Setting and
  Services from ``manifest.setting_of`` / ``services_of``, the step ``step.learn``), ``terminate_manifest`` records
  the owner's termination of an idle chain of the manifest's run root.
"""
from __future__ import annotations

import fcntl
import functools
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.evaluation import _next_attempt, attempts
from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import budgets, prelaunch, routes
from .cells import Pause
from .client import ELUCID_RESPONSE_MODEL_IDS, ROUTE_A, ROUTES
from .errors import AssumptionBroken, BudgetStop, ConfigurationError, LedgerFailure
from .package import empty
from .profiles import (BENCHES, SUPPORTED_BENCHES, read_benches, CHAINS, CONFIGURATIONS, COST_CHECK_PAUSES, FIRST_CALL_SYSTEM, FIRST_CALL_USER, PILOT,
                       PROCEDURE_ARM_FACTOR, RECORD_HASH, SLOT_ROOT, STAGE_READ, TEST_READ_CELLS, TEST_START_FACTOR,
                       configuration_of, estimate_arms, estimate_test_read, fired_share, first_call_bench, is_alfworld, is_zebra, is_v27, is_v29,
                       ledger_bound, order_of, read_estimate_terms, record, verified)

__all__ = ("EXIT_AWAITING", "EXIT_COMPLETE", "EXIT_PAUSED", "RUNNER_LOCK", "Terminated", "cap_check", "chain_root",
           "check_pins", "confirmation", "evaluate", "first_call", "heavy", "latest_cap_check", "launch_child",
           "read_budget", "read_consent", "read_estimate_record", "run", "run_manifest", "terminate",
           "terminate_manifest", "unit_root")

EXIT_COMPLETE, EXIT_PAUSED, EXIT_AWAITING = 0, 3, 5
RUNNER_LOCK = ".runner.lock"
HEAVY_LOCK = "memory-heavy.lock"
HEAVY = {"spreadsheetbench": fcntl.LOCK_EX, "alfworld": fcntl.LOCK_SH}  # §5, §11: memory on 15 GiB
CAP_CHECK = "cap-check-G.json"
TEST_READ = "test-read.json"
CONFIRM = "confirm.json"  # registrar addendum 2026-10-22 14:10, row 7 (``first_call``)
CONFIRM_FAILED = "confirm-failed-%d.json"
READ_WAITING = "read-waiting.json"  # row 9 (``read_consent``)
# the echoed model ids of a confirmed first reply (§4.1): chain G the frozen MODELS entry's (weak_solver_probe.py:77,
# as the manifest's solver block records it), chain D the registered elucid set
FIRST_CALL_ECHO = {"G": frozenset({CHAINS["G"]}), "D": ELUCID_RESPONSE_MODEL_IDS}
# chain D's route B (registrar row "deepseek route B", 2026-10-22 17:3x; M4): its own first call, recorded beside route
# A's ``confirm.json``, its echo set the route's (``client.ROUTES``)
CONFIRM_ROUTE, CONFIRM_ROUTE_FAILED = "confirm-route-%s.json", "confirm-route-%s-failed-%%d.json"


class Terminated(Exception):
    """The protocol terminated the chain (§9.4); its marker is written."""


def chain_root(setting, chain):
    require(chain in CHAINS, "Unknown chain")
    return safe_path(setting.root) / chain


def unit_root(setting, chain, bench):
    """A test-read unit: ``<chain root>/test/<bench>``."""
    require(bench in SUPPORTED_BENCHES, "Unknown bench")
    return chain_root(setting, chain) / "test" / bench


def heavy_mode(benches):
    """The memory lock a unit needs from EVERY bench whose cells it runs (§2.6, §11; Codex finding #5): exclusive when
    any is SpreadsheetBench, shared when any is ALFWorld, else none -- a mixed unit (a self-test running an earlier
    SpreadsheetBench set at a later step, §5.5) takes the spreadsheet lock like a SpreadsheetBench unit."""
    benches = tuple(benches)
    require(benches and all(bench in SUPPORTED_BENCHES for bench in benches), "The benches a unit runs")
    modes = {HEAVY[bench] for bench in benches if bench in HEAVY}
    return fcntl.LOCK_EX if fcntl.LOCK_EX in modes else fcntl.LOCK_SH if modes else None


@contextmanager
def heavy(setting, bench, *more):
    """The machine-wide memory lock of a unit on ``bench`` whose cells also run on ``more`` (``heavy_mode``; module
    docstring); waits its turn, untimed like every route-B slot wait (plan §4)."""
    mode = heavy_mode((bench, *more))
    if mode is None:
        yield
        return
    path = safe_path(setting.extra.get("slot_root", SLOT_ROOT)) / HEAVY_LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, mode)
        yield
    finally:
        os.close(descriptor)


# ------------------------------------------------------------------------------------ the first-call confirmation
def _first_call_fields(chain, entry, receipt, error, checks, bench):
    """What ``confirm.json`` and ``confirm-failed-<n>.json`` keep of the one call (on ``bench``): counts, the model
    names, the latency, hashes and the error classes -- never the reply or a provider's text."""
    usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
    reply = receipt.get("response")
    tried = receipt.get("attempts") if isinstance(receipt.get("attempts"), list) else []
    return {
        "model": CHAINS[chain], "returned_model": receipt.get("returned_model"), "bench": bench,
        "max_tokens": entry.get("model_max_tokens"), "bound": entry.get("max_tokens"),
        "scopes": list(budgets.first_call_scopes(chain)), "request_sha256": entry.get("request_sha256"),
        "request_bytes": entry.get("request_bytes"),
        "reply_sha256": hashlib.sha256(reply.encode("utf-8")).hexdigest() if isinstance(reply, str) else None,
        "reserved": entry.get("reserved"), "charged": entry.get("charged"),
        "usage": {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "reasoning": {"tokens": receipt.get("reasoning_tokens"), "chars": receipt.get("reasoning_chars")},
        "finish_reason": str(receipt["finish_reason"])[:30] if receipt.get("finish_reason") is not None else None,
        "error_type": receipt.get("error_type"),
        "attempts": [a.get("status") if type(a.get("status")) is int else str(a.get("error"))[:40]
                     for a in tried if isinstance(a, dict)],
        "seconds": entry.get("seconds"), "checks": checks, "error": None if error is None else type(error).__name__}


def _confirm_of(run, chain, route):
    """(identity, confirmation file, failed-file pattern, echo set) of the first call of ``chain`` on ``route``
    (registrar row "deepseek route B", 17:3x; M4): chain G and chain D's route A keep ``confirm.json`` and the
    registered echo set; chain D's route B confirms its own first reply (``confirm-route-B.json``, its identity naming
    the route, the route's echo set ``client.ROUTES[route].response_model_ids``)."""
    if route in (None, ROUTE_A):
        return {"run": run, "chain": chain}, CONFIRM, CONFIRM_FAILED, FIRST_CALL_ECHO[chain]
    return ({"run": run, "chain": chain, "route": route}, CONFIRM_ROUTE % route, CONFIRM_ROUTE_FAILED % route,
            ROUTES[route].response_model_ids)


def first_call(setting, chain, *, before=lambda: None):
    """Registrar addendum 2026-10-22 14:10, row 7 (AGENTS.md: confirm the first actual model response before releasing
    a concurrent run; plan §10 step 4): before the chain's first paid unit, ONE solver call alone through the chain's
    own solver client (``setting.clients``) with its registered settings on the bench of that unit
    (``protocol.first_call_bench`` of the Setting's run configuration, its order's first bench: the client's M and read
    timeout, the ledger bound B of ``protocol.ledger_bound``), on the
    registered fixture prompt (``FIRST_CALL_SYSTEM`` / ``FIRST_CALL_USER``: no pool item, nothing consumed), charged to
    ``<c>:solver`` in the sub-scope ``<c>:confirm`` (``budgets.first_call_scopes``). It passes when a reply arrives
    (``ok``), its echoed model is in the registered set (``FIRST_CALL_ECHO``), the ledger settled more than 0 tokens
    for it, and -- chain D -- the reasoning check of its receipt holds (``client.ElucidClient``: no reasoning tokens,
    no reasoning text; chain G's reasoning is registered, §4.1). A pass is written once as ``confirm.json`` (record
    ``first-call``: counts, model, latency and hashes, never the reply) and every relaunch reuses it without a second
    call. Any failure is kept as ``confirm-failed-<n>.json`` (the same fields, like any failed launch) and raises
    ``Pause("first_call_unconfirmed")`` before the first unit: no unit attempt is opened, and the main agent checks
    network and TLS and relaunches ``run`` (no unit spent anything, so no owner decision is needed). ``before``: called
    once just before the call is made (a relaunched chain's pin check). Returns the verified ``confirm.json``.
    Chain D on route B (registrar row "deepseek route B", 17:3x; M4): the route ``manifest.setting_of`` bound
    (``setting.extra["route"]``) confirms its own first reply the same way (``_confirm_of``)."""
    root = chain_root(setting, chain)
    route = ("B" if chain == "D" and is_v29(configuration_of(setting)) else
             setting.extra.get("route") if chain in routes.ROUTED else None)  # M4: the route this process runs on
    identity, confirm, failed_name, echo = _confirm_of(setting.run, chain, route)
    if (root / confirm).exists():
        return confirmation(setting.root, setting.run, chain, route=route)
    before()
    model, glm, entry, receipt, error = CHAINS[chain], chain == "G", {}, None, None
    bench = first_call_bench(configuration_of(setting))  # registrar 17:0x: the configuration's first step bench
    try:
        client = setting.clients(model, bench)
        require(client.model == model, "The chain's solver client")
        bound = ledger_bound(model, bench, branch=None if glm else setting.branch,
                             longest=None if glm else setting.longest)
        endpoint = budgets.endpoint(setting, budgets.first_call_scopes(chain), client=client, max_tokens_bound=bound)
        recorder = endpoint.recorder(label="%s/confirm" % chain)
        try:
            receipt = endpoint.send(FIRST_CALL_SYSTEM, FIRST_CALL_USER, recorder)
        finally:
            entry = {**recorder.sends[-1], "model_max_tokens": client.max_tokens} if recorder.sends else {}
    except Exception as failure:  # noqa: BLE001 -- any failure stops the chain before its first unit
        error = failure
    if not isinstance(receipt, dict):
        receipt = entry.get("receipt") if isinstance(entry.get("receipt"), dict) else {}
    checks = {"reply": receipt.get("ok") is True, "model": receipt.get("returned_model") in echo,
              "settled": type(entry.get("charged")) is int and entry["charged"] > 0,
              "reasoning": None if glm else (receipt.get("reasoning_tokens", "unchecked") in (None, 0)
                                             and receipt.get("reasoning_chars") == 0)}
    passed = error is None and all(ok is not False for ok in checks.values())
    fields = {"identity": identity, **_first_call_fields(chain, entry, receipt, error, checks, bench),
              "passed": passed}
    if passed:
        write_json(root / confirm, record("first-call", setting.evidence, fields))
        return verified(read_json(root / confirm), "first-call")
    n = 1 + len(list(root.glob(failed_name.replace("%d", "*"))))
    write_json(root / (failed_name % n), record("first-call", setting.evidence, fields))
    told = (": " + str(error)[:200]) if isinstance(error, (ValueError, ConfigurationError, BudgetStop,
                                                           AssumptionBroken, LedgerFailure)) else ""
    failed = [name for name, ok in checks.items() if ok is False]
    raise Pause("first_call_unconfirmed", "the first reply of chain %s is not confirmed (%s; %s)" % (
        chain if route in (None, ROUTE_A) else "%s on route %s" % (chain, route), ", ".join(failed)
        or "no check reached", type(error).__name__ + told if error is not None
        else "error_type %s" % receipt.get("error_type")), "%s/confirm" % chain)


def confirmation(root, run, chain, route=None, configuration=None):
    """The verified ``confirm.json`` of chain ``chain`` of run ``run`` under the run root ``root`` (``first_call``):
    it exists, names this run and chain, and passed; ValueError otherwise. ``first_call`` reuses it on every relaunch,
    and ``step.run_unit_spec`` needs it before a paid step unit starts outside ``run`` (registrar addendum 2026-10-22
    15:3x, ticket P2C-1). Chain D (registrar row "deepseek route B", 17:3x; M4): the confirmation of ``route``, by
    default the chain's current route (``routes.current``), so a paid unit after a route switch needs that route's
    own first call (``_confirm_of``)."""
    if route is None and chain in routes.ROUTED:
        route = routes.current(safe_path(root) / chain, run=run, chain=chain, configuration=configuration)
    identity, confirm = _confirm_of(run, chain, route)[:2]
    path = safe_path(root) / chain / confirm
    require(path.exists(), "Chain %s has no confirmed first call (%s): start the chain with run, which makes it "
            "(registrar addendum 14:10 row 7, 15:3x ticket P2C-1)" % (chain, confirm))
    found = verified(read_json(path), "first-call")
    require(found["identity"] == identity and found["passed"] is True,
            "A first-call record of another run")
    return found


# --------------------------------------------------------------------------------------------- chain G's check
def cap_check(setting, chain, k, measured):
    """§9.3: after chain G's first run unit (k = 1), ``measured`` = {"ok": bool, "scopes": {scope: {"cap",
    "projected"}}} -- the zero-call projection of every chain-G scope from the measured per-cell cost. A breach
    pauses chain G only, in a run configuration whose cost check pauses (``protocol.COST_CHECK_PAUSES``); in main
    (registrar 17:0x) the check records its factor with ``pauses`` false and never pauses, and the read gate still
    applies that factor (``read_budget``). Chain D and later steps are never checked here. The check is written once as
    ``cap-check-G.json``; a re-check whose caps an owner's ``raise_cap`` changed is written next to it as
    ``cap-check-G-<n>.json`` (ticket C2-2), and a restart with unchanged caps rewrites the same record."""
    if chain != "G" or k != 1:
        return None
    require(isinstance(measured, dict) and type(measured.get("ok")) is bool and isinstance(measured.get("scopes"), dict)
            and all(s.startswith("G:") or s == budgets.ROOT for s in measured["scopes"]),
            "A chain-G cap check names chain-G scopes")
    configuration = configuration_of(setting)
    pauses = COST_CHECK_PAUSES[configuration]
    value = record("cap-check", setting.evidence, {"run": setting.run, "chain": chain, **measured,
                                                   "configuration": configuration, "pauses": pauses})
    path, n = chain_root(setting, chain) / CAP_CHECK, 1
    while path.exists() and read_json(path).get(RECORD_HASH) != value[RECORD_HASH]:
        n += 1
        path = path.with_name("cap-check-G-%d.json" % n)
    write_json(path, value)
    if not measured["ok"] and pauses:
        raise Pause("cap_check", "chain G's projected cost exceeds a registered cap (§9.3)", "G/s1")
    return verified(read_json(path), "cap-check")


# ------------------------------------------------------------------------------------------- the test read
def _child(setting, arguments, name):
    """Run ``python -B scripts/run_execskill.py <arguments>`` in a child whose stdout and stderr are a sealed file from
    its first byte (chain.py:153-166), in the route-B launch environment (``prelaunch.launch_env``, ticket A13-1);
    returns the exit code."""
    logs = safe_path(setting.shared) / "host_only" / "diagnostics"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / ("child-%s-%d.log" % (name, time.time_ns()))
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_execskill.py"
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        process = subprocess.run([sys.executable, "-B", str(script), *arguments], stdin=subprocess.DEVNULL,
                                 stdout=descriptor, stderr=descriptor, env=prelaunch.launch_env(), check=False)
    finally:
        os.close(descriptor)
    return process.returncode


def launch_child(setting, spec):
    """One test-read unit in a child process (``evaluate-unit``)."""
    name = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
    spec_path = safe_path(setting.shared) / "host_only" / "specs" / (name + ".json")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    if not spec_path.exists():
        write_json(spec_path, spec)
    return _child(setting, ["evaluate-unit", "--manifest", str(setting.extra["manifest"]), "--spec", str(spec_path)],
                  name)


def _status(root, name, code):
    """A Pause for a read unit that did not complete (chain.py:141-150)."""
    found = attempts(root)
    if code == EXIT_AWAITING and found:
        return Pause("awaiting_owner_decision", found[-1].name, name)
    if found and (found[-1] / "status.json").exists():
        status = verified(read_json(found[-1] / "status.json"), "unit-status")
        return Pause(status["kind"], status["reason"], name)
    return Pause("exception", "evaluation_child_ended_without_status", name)


def _failed_start(setting, root, code):
    """A child that ended before its attempt: the parent writes the paused attempt (chain.py:185-192)."""
    attempt = _next_attempt(root)
    if attempt is not None:
        attempt.mkdir(parents=True)
        write_json(attempt / "status.json", record("unit-status", setting.evidence, {
            "status": "paused", "kind": "exception", "reason": "child_failed_before_its_attempt", "cell": None,
            "exit": code}))


def read_estimate_record(smoke_root, configuration=None):
    """Registrar addendum 2026-10-22 14:10, row 8 (§9.3; pilot-runbook §3.4; zero calls): the sealed record
    ``test-read-estimate`` of the S-E6-corrected test-read estimate (``protocol.estimate_test_read``) of the passed
    smoke at ``smoke_root``: its result (``smoke-result.json``: passed -- or failed under the owner's valid smoke
    waiver, ``smoke.waiver``, recorded as ``waiver``, registrar addendum 2026-10-23 05:3x --, S-E6 required and
    passed) and S-E6's stage
    record (``stages/SE6.json``: passed, ``result.per_cell`` and ``result.ratio``), both of the smoke's own
    specification (``smoke.json``), for the run configuration S-E6 projected (``result.configuration``; a record
    without one projected ``protocol.PILOT``); ``configuration``, when given, must be that one (registrar 17:0x: the
    main run's estimate is main's test-read cells and fired shares). Both chains carry its one value in the manifest's
    ``data.test_read_estimate``, and
    its exact per-bench terms (``terms``, {bench: "p/q"}, ``protocol.read_estimate_terms``) in ``data.test_read_terms``
    {chain: terms} (registrar addendum 15:3x, ticket P2C-2); chain G's own measured cost corrects it at the read gate
    (``read_budget``). ``run_execskill.py test-read-estimate`` writes it once."""
    from . import smoke  # imported here: smoke imports step, which imports this module

    root = safe_path(smoke_root)
    spec = smoke.load(root / smoke.SPEC)
    result = verified(read_json(root / smoke.RESULT), "smoke-result")
    waived = smoke.waiver(root, result)  # registrar addendum 2026-10-23 05:3x: None, or the owner's valid smoke waiver
    require(result["spec"] == spec[RECORD_HASH] and (result["passed"] is True or waived is not None)
            and "SE6" in result["required"] and result["stages"].get("SE6") == "pass",
            "The estimate needs a passed smoke (or a failed one under the owner's valid smoke waiver, registrar "
            "addendum 2026-10-23 05:3x) whose S-E6 passed (§10)")
    stage = verified(read_json(root / smoke.STAGES_DIR / "SE6.json"), "smoke-stage")
    require(stage["stage"] == "SE6" and stage["spec"] == spec[RECORD_HASH] and stage["result"].get("passed") is True,
            "S-E6's passed stage record of this smoke")
    se6 = stage["result"]
    roster = read_benches(se6.get("configuration", PILOT))
    require(isinstance(se6.get("per_cell"), dict) and set(se6["per_cell"]) == set(roster),
            "S-E6's per-cell tokens of every bench")
    per_cell = {bench: {key: se6["per_cell"][bench].get(key) for key in ("card", "procedure", "procedure_assumed")}
                for bench in roster}
    projected = se6.get("configuration", PILOT)
    require(projected in CONFIGURATIONS and configuration in (None, projected), "S-E6 projected the run configuration "
            "%r, not %r (registrar 17:0x)" % (projected, configuration))
    value = estimate_test_read(per_cell, se6["ratio"], projected)
    terms = read_estimate_terms(per_cell, se6["ratio"], projected)  # ticket P2C-2: the read gate's per-bench terms
    require(math.ceil(sum(terms.values())) == value, "The estimate is the sum of its per-bench terms")
    return record("test-read-estimate", result["evidence"], {  # a rehearsal smoke's estimate is a fixture (15:0x)
        "smoke": {"root": str(root), "spec": spec[RECORD_HASH], "result": result[RECORD_HASH],
                  "se6": stage[RECORD_HASH]},
        "waiver": waived,  # registrar addendum 2026-10-23 05:3x: None, or {"sha256", "rows"} of the owner's waiver
        "pilot": projected, "formula": "ceil(ratio x sum_b n_b x (card_b + %d x f_b x proc_b)); registrar addendum "
                                        "2026-10-22 14:10, row 8" % estimate_arms(projected),
        "inputs": {"ratio": se6["ratio"], "per_cell": per_cell,
                   "n": {bench: TEST_READ_CELLS[projected][bench][0] for bench in roster},
                   "fired": {bench: str(fired_share(bench, projected)) for bench in roster},
                   "arms": estimate_arms(projected),  # 4; with main-v2's stage arms 8
                   "procedure_factor": str(PROCEDURE_ARM_FACTOR[1])},
        "value": value, "test_read_estimate": {chain: value for chain in sorted(CHAINS)},
        "terms": {bench: "%d/%d" % (term.numerator, term.denominator) for bench, term in terms.items()}})


def latest_cap_check(setting):
    """Chain G's latest cost check (``cap_check``: ``cap-check-G.json``, then ``cap-check-G-<n>.json`` after an owner's
    raise), verified as this run's chain-G record of the Setting's run configuration with its measured tokens per run
    cell and the anchor: passed, or -- in a configuration whose cost check never pauses (main, registrar 17:0x) -- a
    recorded breach, whose factor the read gate applies all the same; -> (path, record)."""
    root = chain_root(setting, "G")
    path, n = root / CAP_CHECK, 1
    require(path.exists(), "Chain G's read gate needs its cost check (%s, §9.3)" % CAP_CHECK)
    while path.with_name("cap-check-G-%d.json" % (n + 1)).exists():
        n += 1
        path = path.with_name("cap-check-G-%d.json" % n)
    found = verified(read_json(path), "cap-check")
    per_cell, anchor = found.get("per_cell"), found.get("anchor_high")
    configuration = configuration_of(setting)
    recorded = found.get("pauses") is False and COST_CHECK_PAUSES[configuration] is False  # main: record-only
    require(found["run"] == setting.run and found["chain"] == "G" and found.get("configuration") == configuration
            and (found["ok"] is True or recorded)
            and type(per_cell) in (int, float) and math.isfinite(per_cell) and per_cell >= 0
            and type(anchor) is int and anchor > 0, "Chain G's passed cost check of this run")
    return path, found


def read_budget(setting, chain):
    """§9.3: the test read starts only when the chain's remaining solver budget and its test-read scope both cover
    1.3 x the S-E6-corrected test-read estimate (``setting.extra["test_read_estimate"][chain]``, tokens;
    ``read_estimate_record``) of the read units still to run: on a first start all five, so the whole estimate; on a
    relaunch after some units completed (a ``unit.json``), ceil of the sum of the remaining units' per-bench terms
    (``setting.extra["test_read_terms"][chain]``, the manifest's ``data.test_read_terms``; registrar addendum 2026-10-22
    15:3x, ticket P2C-2: units already read are not charged again). Chain G's part is corrected by its own measured
    cost, since the smoke never prices GLM-5.3 solving (registrar addendum 14:10, row 8): ceil(part x max(1,
    factor_G)), factor_G = the per-cell factor of its latest cost check (``latest_cap_check``: ledger tokens per run
    cell / the bench's high anchor, as ``step.cost_projection`` measured it); chain D's is the part. The need is
    ceil(1.3 x used) (15:3x). Returns the gate {"estimate", "units" (the read units still to run), "part", "factor",
    "cap_check", "used", "need"}; ``test-read.json`` records the gate of the launch that completed the read."""
    estimate = setting.extra["test_read_estimate"][chain]
    require(type(estimate) is int and estimate > 0, "The S-E6-corrected test-read estimate, in tokens")
    roster = read_benches(configuration_of(setting))
    units = [bench for bench in roster if not (unit_root(setting, chain, bench) / "unit.json").exists()]
    part = estimate
    if len(units) < len(roster):  # ticket P2C-2: a relaunch prices only the read units still to run
        terms = (setting.extra.get("test_read_terms") or {}).get(chain)
        require(isinstance(terms, dict) and set(terms) == set(roster), "The per-bench terms of the test-read "
                "estimate (data.test_read_terms; registrar addendum 15:3x, ticket P2C-2)")
        part = math.ceil(sum((Fraction(terms[bench]) for bench in units), Fraction(0)))
    factor, check, used = None, None, part
    if chain == "G":
        path, found = latest_cap_check(setting)
        factor = Fraction(found["per_cell"]) / found["anchor_high"]
        used = math.ceil(part * max(Fraction(1), factor))
        check = {"file": path.name, "record_sha256": found[RECORD_HASH]}
    snapshot = setting.budget.snapshot()
    need = math.ceil(used * TEST_START_FACTOR)
    for scope in (chain + ":solver", chain + ":test"):
        entry = snapshot[scope]
        if entry["cap"] - entry["settled"] - entry["open"] < need:
            raise Pause("test_read_budget", "%s leaves less than 1.3 x the estimate %d of the read units %s (§9.3)"
                        % (scope, used, ", ".join(units)), "%s/test" % chain)
    return {"estimate": estimate, "units": units, "part": part, "factor": None if factor is None else float(factor),
            "cap_check": check, "used": used, "need": need}


def read_consent(setting, chain):
    """Registrar addendum 2026-10-22 14:10, row 9 (§8.1): the chain-level check of the owner's read consent
    (``evaluation.consent`` on the run root's ``shared/consent.json``) before any read child starts. Missing or invalid:
    no read attempt is opened; ``read-waiting.json`` (kind ``consent_missing``, counts only; rewritten only with the
    same content) is written and the chain pauses, so ``run`` exits 3. Once the owner has written the consent the main
    agent relaunches ``run`` -- a waiting chain, not a paused attempt: no ``recovery.json``. The check inside each read
    child (``evaluation.run_unit_spec``) stays as the second guard."""
    from . import evaluation  # imported here: evaluation imports this module

    try:
        evaluation.consent(setting.shared, configuration_of(setting))  # a stage read's consent names its stage arms
    except ValueError:
        roots = [unit_root(setting, chain, bench) for bench in read_benches(configuration_of(setting))]
        write_json(chain_root(setting, chain) / READ_WAITING, record("read-waiting", setting.evidence, {
            "identity": {"run": setting.run, "chain": chain}, "kind": "consent_missing", "read_units": len(roots),
            "read_attempts": sum(len(attempts(path)) for path in roots),
            "units_complete": sum((path / "unit.json").exists() for path in roots)}))
        raise Pause("consent_missing", "no valid owner consent to the test read (shared/consent.json, §8.1); no read "
                    "attempt was opened", "%s/test" % chain) from None


def evaluate(setting, chain, package, *, launch=launch_child):
    """The chain's one test read (§8.1): five units side by side, each a child under the memory lock. Returns {bench:
    unit root}; raises the first ``Pause`` once every child has ended."""
    roster = read_benches(configuration_of(setting))
    roots = {b: unit_root(setting, chain, b) for b in roster}

    def one(bench):
        root = roots[bench]
        name = "%s/test/%s" % (chain, bench)
        if not (root / "unit.json").exists():
            spec = {"chain": chain, "bench": bench, "package_sha256": package.sha256, "unit_root": str(root)}
            before = len(attempts(root))
            with heavy(setting, bench):
                code = launch(setting, spec)
            if not (root / "unit.json").exists():
                if code != EXIT_AWAITING and len(attempts(root)) == before:
                    _failed_start(setting, root, code)
                return _status(root, name, code)
        found = verified(read_json(root / "unit.json"), "evaluation")
        require(found["run"] == setting.run and found["chain"] == chain and found["packages"]["F"] == package.sha256,
                "A read unit of another run, chain or package")
        return None

    with ThreadPoolExecutor(max_workers=len(roster)) as pool:
        results = list(pool.map(one, roster))
    for pause in results:
        if pause is not None:
            raise pause
    return roots


# ---------------------------------------------------------------------------------------------- the runner
def _terminal(root, identity):
    """"complete" or "terminated" when the chain of this run has ended, else None (chain.py:240-248)."""
    if (root / "chain.json").exists():
        require(verified(read_json(root / "chain.json"), "chain")["identity"] == identity, "A chain of another run")
    for marker, kind_, status in (("chain-terminated.json", "chain-terminated", "terminated"),
                                  ("chain-complete.json", "chain-complete", "complete")):
        if (root / marker).exists():
            require(verified(read_json(root / marker), kind_)["identity"] == identity,
                    "A terminal marker of another run")
            return status
    return None


def _verified(setting, root, identity, verify):
    """The pinned files still match the manifest; otherwise the started chain is terminated (chain.py:251-258). Route
    B's check (``manifest.verify_unit``, plan §2.9, ticket A13-1 item 3) raises ConfigurationError, the frozen one
    ValueError: either terminates."""
    try:
        verify()
    except (ValueError, ConfigurationError) as error:
        write_json(root / "chain-terminated.json", record("chain-terminated", setting.evidence, {
            "identity": identity, "by": "protocol", "decision": "manifest_mismatch: %s" % str(error)[:300]}))
        raise Terminated("manifest_mismatch") from None


def check_pins(setting, chain):
    """Before every unit (plan §2.9, ticket A13-1 item 3): the pinned files still match the manifest
    (``setting.extra["verify"]``, none in fixtures); a mismatch writes ``chain-terminated.json`` and raises
    ``Terminated``."""
    _verified(setting, chain_root(setting, chain), {"run": setting.run, "chain": chain},
              setting.extra.get("verify", lambda: None))


def run(setting, chain, *, learn, launch=launch_child):
    """Run the chain until it completes, pauses or is terminated (chain.py:261-292). Returns {"status": "complete" |
    "paused" | "terminated", ...}. ``learn``: one step (``step.learn`` in a run). ``setting.budget`` is the chain's own
    ledger (``budgets.own_ledger``). The steps follow the order of the Setting's run configuration
    (``protocol.order_of``; registrar 17:0x), whose caps the ledger declares."""
    if is_alfworld(configuration_of(setting)):
        require(chain == "D", configuration_of(setting) + " launches chain D only")
    if is_zebra(configuration_of(setting)) and is_v27(configuration_of(setting)):
        require(chain == "D", "zebra-pc-v5 launches chain D only")
    root = chain_root(setting, chain)
    root.mkdir(parents=True, exist_ok=True)
    identity = {"run": setting.run, "chain": chain}
    configuration = configuration_of(setting)
    order = order_of(setting)
    with exclusive(root / RUNNER_LOCK):
        ended = _terminal(root, identity)
        if ended is not None:
            return {"status": ended}
        verify = setting.extra.get("verify", lambda: None)
        started = (root / "chain.json").exists()
        if not started:
            verify()  # before the chain starts, a mismatch refuses the run and writes nothing
            write_json(root / "chain.json", record("chain", setting.evidence, {
                "identity": identity, "solver": CHAINS[chain], "order": list(order), "configuration": configuration}))
        budgets.own_ledger(setting, chain).declare({**budgets.chain_caps(chain, configuration),
                                                    **budgets.first_call_caps(chain)})
        start = empty(step="%s/s0" % chain, evidence=setting.evidence)
        package, steps, passed = start, [], []
        try:
            # registrar addendum 14:10, row 7: one confirmed reply before the first unit (a relaunch checks its pins)
            first_call(setting, chain, before=functools.partial(_verified, setting, root, identity, verify)
                       if started else (lambda: None))
            for k, bench in enumerate(order, 1):
                _verified(setting, root, identity, verify)
                package, step_record = learn(setting, root, chain, k, bench, package)
                steps.append(step_record["record_sha256"])
                passed.append(package)
            _verified(setting, root, identity, verify)
            if STAGE_READ[configuration] and not any(found.order for found in passed):
                write_json(root / TEST_READ, record("test-read", setting.evidence, {
                    "identity": identity, "status": "not_read", "reason": "Every step's package is C: nothing was "
                    "accepted (§8.1; v2 stage reads)"}))
            elif not STAGE_READ[configuration] and (package.sha256 == start.sha256 or not package.order):
                write_json(root / TEST_READ, record("test-read", setting.evidence, {
                    "identity": identity, "status": "not_read", "reason": "F = C: nothing was accepted (§8.1)"}))
            else:
                read_consent(setting, chain)  # registrar addendum 14:10, row 9: before any read child starts
                gate = read_budget(setting, chain)
                evaluate(setting, chain, package, launch=launch)
                write_json(root / TEST_READ, record("test-read", setting.evidence, {
                    "identity": identity, "status": "read", "package_sha256": package.sha256, "gate": gate}))
        except Pause as pause:
            return {"status": "paused", "kind": pause.kind, "reason": pause.reason, "unit": pause.cell}
        except Terminated as ended_:
            return {"status": "terminated", "reason": str(ended_)}
        write_json(root / "chain-complete.json", record("chain-complete", setting.evidence, {
            "identity": identity, "package_sha256": package.sha256, "steps": steps}))
        return {"status": "complete"}


def _owned(lock):
    try:
        with exclusive(lock):
            return False
    except ValueError:
        return True


def terminate(setting, chain, *, decision):
    """§9.4: the owner ends the chain; its sealed scores may then be read (``evaluation.unseal``, which also needs the
    owner's continuation file). Only an idle chain can be terminated: no runner, no running read child."""
    require(isinstance(decision, str) and decision.strip(), "A termination records the owner's decision")
    root = chain_root(setting, chain)
    root.mkdir(parents=True, exist_ok=True)
    identity = {"run": setting.run, "chain": chain}
    with exclusive(root / RUNNER_LOCK):  # fails while the chain's runner runs
        require(_terminal(root, identity) is None, "The chain has ended")
        busy = [str(lock.parent) for lock in sorted(root.glob("test/*/.lock")) if _owned(lock)]
        require(not busy, "Test-read units are still running: %s" % busy[:3])
        write_json(root / "chain-terminated.json", record("chain-terminated", setting.evidence, {
            "identity": identity, "by": "owner", "decision": decision}))


# ------------------------------------------------------------------------------- the manifest adapters (A13-1)
def run_manifest(manifest, *, chain, path, docker=None, transport=None):
    """``run_execskill.py run --manifest M --chain G|D`` (ticket A13-1, C2-1 §1): ``run`` on the verified manifest's
    Setting of ``chain`` with ``step.learn`` bound to its Services; ``path``: the manifest file, which the read
    children are started with. ``docker`` / ``transport``: fakes in tests. Returns ``run``'s status."""
    require(chain in CHAINS, "Chain G or D")
    from . import manifest as manifests, step  # imported here: step imports this module

    require(manifest["evidence"] != "smoke", "A smoke manifest runs through its registered smoke command")
    setting = manifests.setting_of(manifest, chain, path=path, docker=docker, transport=transport)
    services = manifests.services_of(manifest, chain, setting=setting, transport=transport)
    return run(setting, chain, learn=functools.partial(step.learn, services=services))


def terminate_manifest(manifest, *, chain, decision):
    """``run_execskill.py terminate --manifest M --chain C --decision TEXT`` (§9.4, ticket A13-1): ``terminate`` on
    the manifest's run root, run and evidence -- all a termination reads -- without building a Setting (no ledger, slot
    or client is touched). Returns the termination's identity."""
    require(chain in CHAINS, "Chain G or D")
    found = SimpleNamespace(root=safe_path(manifest["root"]), run=manifest[RECORD_HASH], evidence=manifest["evidence"])
    terminate(found, chain, decision=decision)
    return {"status": "terminated", "chain": chain, "run": found.run}
