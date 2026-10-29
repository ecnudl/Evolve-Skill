"""Route-B learning units and what every unit attempt is given (protocol ``fivebench-execskill-v1``; registration
§3.4, §4.1, §9.3, §21; implementation plan §1 units row): a copy of ``coevo5.units`` (units.py:1-157).

Copied: a chain is a fixed sequence of units and a unit writes its record once, when an attempt completes; one
process owns a unit while it runs (``exclusive``); attempts are numbered directories and an attempt after a pause or an
interruption runs only once the owner's decision is recorded in the earlier attempt (``recovery.json``; ``attempts``
and ``_next_attempt`` imported from coevo5.evaluation, as units.py:26 does); a completed unit is never run again and
its record must name the same run and identity; a pause writes the attempt's status and is raised; any other error
pauses the unit the same way, its traceback kept in the attempt's diagnostics. What changes:

- the records are this protocol's: ``unit-started``, ``unit-status`` and ``unit`` (``protocol.record``);
- stop kinds are looked up subclass-aware (``errors.stop_kind``; units.py:149-150 maps PackageInvalid to
  "configuration" and the other route-B stops to "exception", B1 open item 2);
- §3.4: at most ``MAX_REDOS`` redos of a unit -- an attempt beyond ``1 + MAX_REDOS`` is refused (``redo_limit``)
  before it starts; whether a second redo is funded is the owner's recorded cap decision on the ledger (``budgets``);
- the chains are route B's two (§21): G (glm-5.3) and D (deepseek-v4.1-flash-1017), both starting from the empty
  package (§5); every method role is GLM-5.3 (§4.2-§4.3);
- endpoints are ``budgets.endpoint``'s with the ledger bound B (``protocol.ledger_bound``, §4.1), charged to
  ``budgets.solver_scopes`` (an attempt N >= 2 to the chain's redo reserve and its own sub-scope -- except, in an
  acceptance round, the blocks no earlier attempt started: their first run stays on the kind's own scope, §9.3,
  ticket C7c-2; and the round's G_acc cells, which go to the examiner's own scope in every attempt, §3.3, §9.2,
  ticket C7e-1) or ``budgets.glm_scopes``; they are built when the attempt begins (the ledger's halt generation is
  taken then). A solver endpoint's client, nominal M, read timeout and bound B are those of the bench its cells run
  on, which a self-test's earlier generated sets make another bench than the step's; its scopes stay the step's
  (``solver_endpoint(..., cell_bench=)``; Codex finding #4);
- ``cell_context`` gives the cells one unstarted ``sandbox.client.Worker`` per cell or episode (the live pool capped
  per SpreadsheetBench unit, §2.6), the route-B slot pools (``slots.pools``) and chain D's nominal M per bench (§4.1:
  the margin rule; chain G has none);
- a unit's own Setting (``for_unit``; registrar decision on safety review 3, ticket C5-1): every sandbox worker it
  makes carries ``sandbox.client.unit_tag(chain, unit)`` and an ALFWorld unit runs at most ``ALFWORLD_WORKERS`` cells
  at once (plan §5: one per episode slot); ``run_unit`` drains the unit (``drainer``: none of its containers may
  remain) once its work has ended, completed or paused, before the attempt's status or the unit's record is written;
- the commit is idempotent (Codex finding #8; §3.4, §9.4): an attempt whose work completed writes its completion
  evidence (``completed.json``: the work's result) BEFORE the unit's consumption settlement (``settle``), the drain
  and ``unit.json``. A stop after that evidence -- in the settlement, the drain or before ``unit.json`` -- pauses the
  unit as usual; once the owner's decision is recorded, the next attempt is a commit attempt: it settles again
  (deciding an item twice writes nothing, ``registry``), drains and writes ``unit.json`` naming the attempt whose work
  completed, and never runs the work (no paid cell repeated). A commit attempt spends nothing and is not a redo.
"""
from __future__ import annotations

import functools
import re
import traceback
from copy import copy
from dataclasses import dataclass, field, replace
from pathlib import Path

from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.evaluation import _next_attempt, attempts
from skillopt.coevo5.protocol import RESEND_COOLDOWN_SECONDS
from skillopt.coevo5.roles import Roles
from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import budgets, profiles as protocol, solver
from .cells import Context, Pause
from .errors import stop_kind
from .profiles import (SUPPORTED_BENCHES, BENCHES, LIVE_SANDBOX_UNIT_CAP, MAX_REDOS, ROLE_MAX_TOKENS, ROLE_MODEL, SLOTS, ledger_bound,
                       record, solver_tokens, verified)
from .sandbox.client import Worker, unit_tag
from .slots import CALL, EPISODE, LIVE, NATIVE

CHAINS = {chain: {"solver": model, "start": "empty"} for chain, model in protocol.CHAINS.items()}  # §21, §5
ATTEMPT = re.compile(r"attempt-([1-9][0-9]*)")
COMPLETED = "completed.json"  # Codex finding #8: an attempt's completion evidence (``run_unit``)
ALFWORLD_WORKERS = SLOTS[EPISODE]  # plan §5: an ALFWorld unit runs with workers = the 6 episode slots


@dataclass
class Setting:
    """What a chain process needs from the launch manifest (units.py:49-75 with the route-B parts). ``pools``: {bench:
    [items with task_id, public, private]}; ``cards``: {bench: the active card text} (§2.2); ``runtime``: the frozen
    runtime per bench; ``clients(model, bench)``: the solver client of ``model`` for ``bench`` (``bench`` None: the
    method-role client), with ``model``, ``max_tokens`` and ``call``; ``budget``: the chain's own ledger
    (``coevo5.budget.Budget`` at ``budgets.ledger_root``); ``slots``: every route-B pool (``slots.pools``); ``sandbox``:
    the ``Worker`` keywords (docker, limits, scratch, image; a unit's own Setting adds its ``tag``, ``for_unit``);
    ``evidence``: the run's records' label; ``branch`` / ``longest``: chain D's ledger-bound branch and longest probe
    completion (§4.1, S1-b); ``extra``: the run's hooks -- ``verify`` (the manifest check before every unit), ``drain``
    (``drain(chain, unit)``, the unit drain), ``manifest``, ``slot_root``, ``test_read_estimate`` -- fixtures leave
    out what they do not exercise."""

    run: str
    root: Path
    shared: Path
    pools: dict
    cards: dict
    runtime: dict
    clients: object
    budget: object
    slots: dict
    sandbox: dict
    evidence: str
    branch: str | None = None
    longest: int | None = None
    workers: int = 16
    cooldown: int = RESEND_COOLDOWN_SECONDS
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        from .instruction_start import active_cards
        if protocol.is_v210(protocol.configuration_of(self)):
            self.cards = active_cards(self.cards, protocol.configuration_of(self))


def attempt_number(attempt):
    """N of an ``attempt-N`` directory."""
    match = ATTEMPT.fullmatch(safe_path(attempt).name)
    require(match is not None, "Not an attempt directory: %s" % attempt)
    return int(match.group(1))


def solver_endpoint(setting, chain, bench, k, kind, attempt, *, first_run=False, g_acc=False, cell_bench=None):
    """The solver endpoint of one unit attempt of step ``k`` (§4.1, §9.3): the chain's solver client for ``bench``,
    charged to ``budgets.solver_scopes`` of the step ``kind`` (run, examiner, selftest, accept) and the attempt, with
    the ledger bound B as its ``max_tokens``. ``first_run`` (``kind`` "accept" only): the endpoint of the acceptance
    blocks that no earlier attempt started -- a pause redoes ONE block on the redo's sub-scope (§9.3; owner decision
    #15), the rest of the round is its first run and is charged to the kind's own scope in any attempt (ticket
    C7c-2). ``g_acc`` (``kind`` "examiner" only): the endpoint of an acceptance round's G_acc cells, run in an attempt
    of the accept unit -- the registration puts their solver cost in the examiner scope (§3.3 "它的做题费用记在考官作用域
    里（9.2、9.3）", §9.2; calc T6 and ``protocol.MAX_SCHEDULE_CELLS`` count G_acc in "examiner"; registrar decision
    2026-10-22 on ticket C7e-1), so they are charged to the examiner's own scope ``...:examiner`` in any attempt,
    never to an ``...:accept`` scope or the redo reserve, which T6 and S-E6 (``smoke._scope_cells``) price for the
    acceptance cells alone. ``cell_bench``: the bench the endpoint's cells run on when it is not the step's -- an
    earlier bench's generated items in a self-test (§5.5; Codex finding #4): the client (its nominal M and read
    timeout) and the ledger bound B are that bench's (§4.1, §5.5), the scopes stay the step's ``bench``, ``k``,
    ``kind`` and attempt (§9.3: the self-test is charged to the step that runs it)."""
    require(not first_run or kind == "accept", "Only an acceptance round has blocks of a first run in a redo")
    require(not g_acc or kind == "examiner", "Only the examiner scope holds an acceptance round's G_acc cells")
    on = bench if cell_bench is None else cell_bench
    require(on in SUPPORTED_BENCHES, "A cell bench")
    model = CHAINS[chain]["solver"]
    client = setting.clients(model, on)
    require(client.model == model, "The chain's solver client")
    glm = model == protocol.CHAINS["G"]
    bound = ledger_bound(model, on, branch=None if glm else setting.branch,
                         longest=None if glm else setting.longest)
    number = attempt_number(attempt)  # an attempt directory in either case
    scopes = budgets.solver_scopes(chain, bench, k, kind, None if first_run or g_acc else number)
    return budgets.endpoint(setting, scopes, client=client, max_tokens_bound=bound)


def role_endpoint(setting, chain, role, bench, k):
    """A method role's endpoint (§4.2-§4.3): GLM-5.3 with M = B = ``ROLE_MAX_TOKENS``, charged to
    ``budgets.glm_scopes``."""
    client = setting.clients(ROLE_MODEL, None)
    require(client.model == ROLE_MODEL, "Every method role is GLM-5.3")
    return budgets.endpoint(setting, budgets.glm_scopes(chain, role, bench, k), client=client,
                            max_tokens_bound=ROLE_MAX_TOKENS)



def _bounded_endpoint(endpoint, bound):
    """A v2.3 call-local nominal M and reservation B; preserve the original pool and halt generation."""
    made = copy(endpoint)
    made.max_tokens = bound
    if hasattr(endpoint, "client"):
        made.client = copy(endpoint.client)
        made.client.max_tokens = bound
    else:  # smoke_roles.Metered: both the guard and the underlying reservation see the actual bound
        made.endpoint = _bounded_endpoint(endpoint.endpoint, bound)
    return made


def _carry_halts(original, made):
    if hasattr(original, "endpoint"):
        _carry_halts(original.endpoint, made.endpoint)
    else:
        original.halted, original.failed = made.halted, made.failed


class BoundedRoles(Roles):
    """v2.3 proposal calls may reserve/send 32K; every other role call keeps the frozen 16K bound (E1)."""

    def plain(self, role, system, user, *, label, max_tokens=None):
        bound = ROLE_MAX_TOKENS if max_tokens is None else max_tokens
        require(bound in (ROLE_MAX_TOKENS, protocol.ENGINEER_MAX_TOKENS[protocol.MAIN_V2_3]),
                "A registered role output bound")
        original = self.endpoint
        self.endpoint = _bounded_endpoint(original, bound)
        before = len(self.calls)
        try:
            return super().plain(role, system, user, label=label)
        finally:
            if len(self.calls) > before:
                self.calls[-1]["max_tokens"] = bound
            _carry_halts(original, self.endpoint)
            self.endpoint = original


def roles(endpoint, *, configuration=protocol.PILOT):
    return BoundedRoles(endpoint) if protocol.is_v23(configuration) else Roles(endpoint)


class AuditRoles(Roles):
    """One fresh, stateless 8K reviewer request; no engineer conversation."""
    def plain(self, role, system, user, *, label, max_tokens=8192):
        require(max_tokens == 8192, "The pinned audit response cap")
        return super().plain(role, system, user, label=label)


def audit_judges(setting, chain, bench, k):
    from .v29_limits import JUDGE_MAX_TOKENS
    require(protocol.is_v29(protocol.configuration_of(setting)), "Judges belong to v2.9")
    out = {}
    for judge in ("G", "D"):
        model = ROLE_MODEL if judge == "G" else protocol.CHAINS["D"]
        made = copy(setting.clients(model, None if judge == "G" else bench))
        if judge == "D":
            from . import client
            require(getattr(made, "route", None) == client.ROUTE_B,
                    "J-D uses the pinned northgate route")
        made.max_tokens = JUDGE_MAX_TOKENS
        scopes = (("overall", "smoke:glm", "smoke:role:audit_" + judge.lower())
                  if chain == budgets.SMOKE and protocol.is_v211(protocol.configuration_of(setting))
                  else budgets.audit_scopes(chain, judge, bench, k))
        endpoint = budgets.endpoint(setting, scopes, client=made, max_tokens_bound=JUDGE_MAX_TOKENS)
        out[judge] = AuditRoles(endpoint)
    return out


def cell_context(setting, attempt, endpoint, *, solve=solver.solve):
    """The cells' ``Context`` of one unit attempt (module docstring); ``solve``: the shell."""
    pools = setting.slots
    capped = {bench: pools[LIVE].limited(cap) for bench, cap in LIVE_SANDBOX_UNIT_CAP.items()}

    def worker(bench):
        options = dict(setting.sandbox)
        if protocol.is_v292(protocol.configuration_of(setting)):
            options["cleanup_grace_seconds"] = protocol.cleanup_grace_seconds(protocol.configuration_of(setting))
            options["ready_timeout_seconds"] = protocol.ready_timeout_seconds(protocol.configuration_of(setting))
        return Worker(**options, live=capped.get(bench, pools[LIVE]), per_call=pools[CALL])

    nominal = ({bench: solver_tokens(endpoint.model, bench) for bench in protocol.active_benches(protocol.configuration_of(setting))}
               if endpoint.model == protocol.CHAINS["D"] else {})
    from .instruction_start import active_cards
    cards = active_cards(setting.cards, protocol.configuration_of(setting))
    return Context(attempt=attempt, endpoint=endpoint, runtime=setting.runtime, cards=cards,
                   native=pools[NATIVE], episodes=pools[EPISODE], worker=worker, evidence=setting.evidence,
                   nominal=nominal, solve=solve, configuration=protocol.configuration_of(setting))


def for_unit(setting, chain, bench, unit):
    """The Setting of one unit of ``chain`` on ``bench`` (module docstring; ticket C5-1): ``setting`` with the sandbox
    keyword ``tag`` = ``unit_tag(chain, unit)``, so every container the unit's workers start is named for the unit and
    ``drain_unit(chain, unit)`` finds exactly those, and on ALFWorld at most ``ALFWORLD_WORKERS`` cells at once."""
    require(bench in SUPPORTED_BENCHES and type(unit) is str and unit, "A unit of a known bench")
    workers = min(setting.workers, ALFWORLD_WORKERS) if bench == "alfworld" else setting.workers
    options = {**setting.sandbox, "tag": unit_tag(chain, unit)}
    if protocol.is_v292(protocol.configuration_of(setting)):
        options.update(cleanup_grace_seconds=protocol.cleanup_grace_seconds(protocol.configuration_of(setting)),
                       cleanup_events=_cleanup_events(setting, chain, unit),
                       ready_timeout_seconds=protocol.ready_timeout_seconds(protocol.configuration_of(setting)),
                       start_events=_start_events(setting, chain, unit))
    return replace(setting, sandbox=options, workers=workers)


def _cleanup_events(setting, chain, unit):
    """One child-only collector shared by unit workers and their exact-name drain."""
    return setting.extra.setdefault("sandbox_cleanup_events", {}).setdefault((chain, unit), [])


def _start_events(setting, chain, unit):
    """One child-only start collector shared by service and cell workers."""
    return setting.extra.setdefault("sandbox_start_events", {}).setdefault((chain, unit), [])


def drainer(setting, chain, unit):
    """``run_unit``'s drain of one unit (§2.6, ticket C5-1): ``setting.extra["drain"](chain, unit)`` -- in a run
    ``sandbox.client.drain_unit`` on the run's docker (``manifest.setting_of``) -- or None for a setting without one
    (fixtures whose cells start no container)."""
    drain = setting.extra.get("drain")
    if protocol.is_v292(protocol.configuration_of(setting)):
        cleanups = _cleanup_events(setting, chain, unit)
        def finish():
            if drain is not None:
                return drain(chain, unit,
                             cleanup_grace_seconds=protocol.cleanup_grace_seconds(protocol.configuration_of(setting)),
                             cleanups=cleanups)
        finish.cleanups = cleanups
        finish.starts = _start_events(setting, chain, unit)
        return finish
    return None if drain is None else functools.partial(drain, chain, unit)


def unit_path(chain_root, k, bench, name):
    """``<chain root>/s<k>-<bench>/<name>``."""
    require(type(k) is int and k >= 1 and bench in SUPPORTED_BENCHES, "A step position and a known bench")
    return safe_path(chain_root) / ("s%d-%s" % (k, bench)) / name


def complete(unit_root, *, run, identity):
    """The unit's record when it is complete (same run and identity), else None."""
    path = safe_path(unit_root) / "unit.json"
    if not path.exists():
        return None
    value = verified(read_json(path), "unit")
    require(value["run"] == run and value["identity"] == identity,
            "A completed unit of another run or with another identity: " + str(unit_root))
    return value


def completed(unit_root, *, run, identity):
    """``(attempt, result)`` of the unit's completion evidence that no ``unit.json`` follows yet -- the latest attempt
    whose work completed (``COMPLETED``; Codex finding #8) -- else None. Evidence of another run, identity or attempt
    raises."""
    for attempt in reversed(attempts(unit_root)):
        path = attempt / COMPLETED
        if path.exists():
            value = verified(read_json(path), "unit-completed")
            require(value["run"] == run and value["identity"] == identity and value["attempt"] == attempt.name,
                    "The completion evidence of another run, identity or attempt: " + str(path))
            return attempt, value["result"]
    return None


def run_unit(unit_root, *, run, identity, work, evidence, drain=None, settle=None, configuration=protocol.PILOT):
    """Run ``work(attempt)`` -> result (a JSON-safe dict) in the unit's next attempt, unless the unit is complete.
    The commit (module docstring; Codex finding #8): the result is persisted as the attempt's completion evidence
    (``COMPLETED``) before ``settle(attempt, result)`` -- the unit's consumption settlement, idempotent -- runs; when an
    earlier attempt holds that evidence, the next attempt (after the owner's recorded decision) is a commit attempt
    that settles again, drains and writes ``unit.json`` naming the attempt whose work completed, without running
    ``work``. ``drain`` (``drainer``): called once the work (and the settlement) has ended, completed or paused, before
    the attempt's status or the unit's record is written; its CleanupUnconfirmed pauses the unit as a stop, so a unit
    whose containers remain is never complete. Returns the unit's record; raises ``Pause`` after writing the attempt's
    status."""
    suffix = "-v2-3" if protocol.is_v23(configuration) else ""
    unit_root = safe_path(unit_root)
    unit_root.mkdir(parents=True, exist_ok=True)
    name = identity["unit"]
    with exclusive(unit_root / ".lock"):
        done = complete(unit_root, run=run, identity=identity)
        if done is not None:
            return done
        attempt = _next_attempt(unit_root)
        if attempt is None:
            raise Pause("awaiting_owner_decision", attempts(unit_root)[-1].name, name)
        finished = completed(unit_root, run=run, identity=identity)  # a commit attempt spends nothing: no redo limit
        if finished is None and attempt_number(attempt) > 1 + MAX_REDOS:
            raise Pause("redo_limit", "%s: at most %d redos of a unit (§3.4)" % (attempt.name, MAX_REDOS), name)
        attempt.mkdir()
        cleanup_events = getattr(drain, "cleanups", None) if protocol.is_v292(configuration) else None
        start_events = getattr(drain, "starts", None) if protocol.is_v292(configuration) else None
        if cleanup_events is not None:
            cleanup_events.clear()
        if start_events is not None:
            start_events.clear()
        def lifecycle():
            events = {key: rows for key, rows in (("cleanups", cleanup_events), ("starts", start_events)) if rows}
            return {"sandbox": events} if events else {}
        write_json(attempt / "started.json", record("unit-started" + suffix, evidence, {
            "run": run, "identity": identity, **({"commit_of": finished[0].name} if finished else {})}))
        try:
            try:
                if finished is None:
                    result = work(attempt)
                    write_json(attempt / COMPLETED, record("unit-completed" + suffix, evidence, {
                        "run": run, "identity": identity, "attempt": attempt.name, "result": result}))
                    worked = attempt
                else:
                    worked, result = finished
                if settle is not None:
                    settle(worked, result)
            finally:
                try:
                    if drain is not None:
                        drain()
                finally:
                    if cleanup_events:
                        write_json(attempt / "sandbox-cleanups.json", {"cleanups": cleanup_events})
                    if start_events:
                        write_json(attempt / "sandbox-starts.json", {"starts": start_events})
        except Pause as pause:
            write_json(attempt / "status.json", record("unit-status" + suffix, evidence, {
                "status": "paused", "kind": pause.kind, "reason": pause.reason, "cell": pause.cell,
                **lifecycle()}))
            raise
        except Exception as error:  # a stop of the run, a configuration check or a crash: the unit pauses
            (attempt / "diagnostics.log").write_text(traceback.format_exc(), encoding="utf-8")
            kind = stop_kind(error) or ("configuration" if isinstance(error, ValueError) else "exception")
            write_json(attempt / "status.json", record("unit-status" + suffix, evidence, {
                "status": "paused", "kind": kind, "reason": type(error).__name__, "cell": None,
                **lifecycle()}))
            raise Pause(kind, type(error).__name__, name) from error
        value = record("unit" + suffix, evidence, {"run": run, "identity": identity, "status": "complete",
                                          "attempt": worked.name, "result": result,
                                          **lifecycle(),
                                          **({"committed_in": attempt.name} if finished else {})})
        write_json(unit_root / "unit.json", value)
        return value
