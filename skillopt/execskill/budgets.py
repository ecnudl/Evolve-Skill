"""Ledger scopes of route B (docs/handoff/execskill-registration-v1-20261021.md §4.1, §9.3; implementation plan §1,
budgets row, and §5) on the frozen ledger: ``skillopt.coevo5.budget.Budget`` and ``calls.Endpoint``, imported unchanged.

Each chain of a run root has its OWN ledger, ``<root>/shared/ledger-<chain>`` (``ledger_root``; registrar decision on
safety review finding 1, ticket fixer-5): the frozen ledger's halt is global to one ledger (budget.py:276-297), so a
completion above B, a leaked reasoning reply or a quarantine in chain G refuses only chain G's open attempts and never
chain D's, and vice versa (§9.3: each chain pauses on its own). A chain's ledger declares only its own caps
(``chain_caps``), whose ``overall`` is that chain's solver cap plus its role cap; a scope of the other chain is not
declared there, so ``endpoint`` refuses it before anything is sent. The smoke keeps one ledger
(``<root>/shared/ledger``) and the S1 probe its own root (§9.3). The frozen ledger admits a reservation only when its
scopes are rooted (budget.py:59-64): they name the root ``overall`` and no ``deepseek`` scope, or ``deepseek`` and
nothing else. Route-B scope names begin with their chain (``G:`` / ``D:``, §9.3), so every route-B call -- either chain,
solver or method role -- also names ``ROOT`` = ``overall``, whose cap is that chain's solver cap plus its role cap and
never binds first. A call is charged to exactly one total: its chain's solver tokens (``<c>:solver``; chain G's GLM-5.3
solver tokens included, §9.3) or its chain's method-role tokens (``<c>:glm``), or the smoke's or the probe's.

Scopes, per chain c in {G, D}; b is the step's bench and k its position in the chain (SB step 1, OQ step 2):
- solver: ``overall``, ``c:solver`` and the registered cap of the work: ``c:xs:b:k:<kind>`` for the step kinds run,
  examiner (incl. G_acc), selftest and accept; ``c:test`` for the one test read. A redo (attempt N >= 2, §9.3) is
  charged instead to ``c:redo`` -- the chain's redo reserve: one redo is pre-funded, a second needs the owner's
  recorded cap decision (``Budget.raise_cap``) -- and to its own sub-scope ``c:xs:b:k:<kind>:attempt-N``. In an
  acceptance round a redo charges these for the ONE block it redoes (§9.3 "a pause redoes only one block"; owner
  decision #15: the block an earlier attempt started and did not complete, redone whole); the blocks no attempt
  started are the round's first run of them and go to ``c:xs:b:k:accept`` in any attempt
  (``units.solver_endpoint(..., first_run=True)``; ticket C7c-2). So the sub-scope never holds more than one block,
  which is what its cap -- min(kind cap, redo reserve = the largest single acceptance block cap), calc T6 -- and the
  S-E6 projection (``smoke._scope_cells``: the kind's maximum-schedule cells / the bench's blocks) assume. The round's
  G_acc cells are the examiner's (§3.3 "它的做题费用记在考官作用域里（9.2、9.3）", §9.2; T6 and
  ``protocol.MAX_SCHEDULE_CELLS`` count them in "examiner"): they go to ``c:xs:b:k:examiner`` in every attempt of the
  accept unit (``units.solver_endpoint(..., g_acc=True)``; registrar decision on ticket C7e-1), so ``...:accept``,
  its attempt sub-scopes and ``c:redo`` hold acceptance cells only, as T6 and S-E6 price them.
- method roles: ``overall``, ``c:glm`` and ``c:xs:b:k:role:<role>`` -- engineer 2.5M, examiner 3.0M, examiner research
  4.6M per step and bench (§9.3; calc T11 registered 1.5M / 2.5M / 4.6M; registrar addendum 2026-10-22, R7 decision
  16:1x, R7b). The describer (at freeze) and the leakage adjudication call (§5.4) are charged to the engineer's scope,
  so the per-step role ceiling of 10.1M holds (20.2M for the two pilot steps, within ``c:glm`` 30M).
- smoke (its own ledger): ``overall`` with ``smoke:solver`` (14M) or ``smoke:glm`` (2M); the S1 probe (its own ledger
  root): ``overall`` with ``smoke:probe`` (0.5M).
- the first-call confirmation of a chain (registrar addendum 2026-10-22 14:10, row 7; ``chain.first_call``):
  ``overall``, ``c:solver`` and ``c:confirm`` (``first_call_scopes``), capped at ``FIRST_CALL_CAP`` and declared by
  ``chain.run`` beside ``chain_caps`` (``first_call_caps``). It is not in ``chain_caps``: S-E6 projects every solver
  scope there at the maximum schedule (``smoke.se6_projection``), and the one confirmation call has no such cells.

``endpoint`` builds the frozen Endpoint with ``max_tokens`` = the ledger bound B (§4.1): a reservation is 4 x (request
bytes + 512 + B) (ledger.py:26-36) and only a completion above B breaks the assumption (ledger.py:67), never one
between the nominal M the request names and B.
"""
from __future__ import annotations

import time
from pathlib import Path

from skillopt.coevo5.budget import OVERALL
from skillopt.coevo5.calls import Endpoint
from skillopt.continual_eval.core import require, safe_path

from .errors import ConfigurationError
from .profiles import (SUPPORTED_BENCHES, BENCHES, CHAINS, CONFIG_GLM_CAP, CONFIG_ROLE_CAPS, CONFIG_STEP_CAPS, FIRST_CALL_CAP, LEDGER,
                       MAX_REDOS, PILOT, PILOTS, PROBE_CAP, ROLE_CAPS, SMOKE_CAPS, SMOKE_SX_CAPS,
                       launchable_chains)

ROOT = OVERALL
SMOKE = "smoke"  # the smoke's namespace and scope prefix (registry.NAMESPACES)
STEP_KINDS = ("run", "examiner", "selftest", "accept")
KINDS = STEP_KINDS + ("test", "smoke", "probe", "confirm")
# method role -> its per-step scope; the describer and the leakage adjudication are the engineer's
ROLES = {"engineer": "engineer", "describer": "engineer", "leakage": "engineer", "examiner": "examiner",
         "examiner_research": "examiner:research"}
ROLE_SCOPE_CAPS = {"engineer": ROLE_CAPS["engineer"], "examiner": ROLE_CAPS["examiner"],
                   "examiner:research": ROLE_CAPS["examiner_research"]}  # the default configuration's (role_scope_caps)
TOTALS = frozenset({chain + ":" + kind for chain in CHAINS for kind in ("solver", "glm")}
                   | {SMOKE + ":solver", SMOKE + ":glm", SMOKE + ":probe"})
CONFIRM = "confirm"  # the first-call confirmation's sub-scope ``<c>:confirm`` (registrar addendum 14:10, row 7)


def ledger_root(root, chain):
    """The ledger root of ``chain`` under the run root ``root``: ``<root>/shared/ledger-<chain>`` for G and D (one
    ledger per chain, module docstring); the smoke's one ledger ``<root>/shared/ledger``."""
    require(chain in CHAINS or chain == SMOKE, "Unknown chain")
    shared = safe_path(root) / LEDGER
    return shared if chain == SMOKE else shared.with_name("ledger-" + chain)


def own_ledger(setting, chain):
    """ConfigurationError unless ``setting.budget`` is ``chain``'s own ledger (``ledger_root``): a chain never runs on
    a ledger another chain shares."""
    found = getattr(setting.budget, "root", None)
    if found is None or Path(found) != ledger_root(setting.root, chain):
        raise ConfigurationError("Chain %s runs on its own ledger %s, not %s" % (
            chain, ledger_root(setting.root, chain), found))
    return setting.budget


def _step(chain, bench, k):
    require(chain in CHAINS and bench in SUPPORTED_BENCHES and type(k) is int and k >= 1, "Unknown chain, bench or step")
    return "%s:xs:%s:%d" % (chain, bench, k)


def solver_scopes(chain, bench, k, kind, attempt=None):
    """The scopes of a solver call (module docstring). ``kind`` "test": one scope per chain (``bench`` and ``k``
    None); "smoke" and "probe": ``chain`` is the smoke namespace "smoke". ``attempt``: None or 1 for a first attempt,
    2 .. MAX_REDOS + 1 for a redo of a step kind."""
    require(kind in KINDS, "Unknown solver scope kind")
    require(attempt is None or (type(attempt) is int and 1 <= attempt <= MAX_REDOS + 1), "Invalid attempt")
    if kind in ("smoke", "probe"):
        require(chain == SMOKE and bench is None and k is None and attempt is None, "The smoke's scopes are its own")
        return ROOT, "%s:%s" % (SMOKE, "solver" if kind == "smoke" else "probe")
    if kind == "test":
        require(chain in CHAINS and bench is None and k is None and attempt is None, "One test-read scope per chain")
        return ROOT, chain + ":solver", chain + ":test"
    scope = _step(chain, bench, k) + ":" + kind
    if attempt is None or attempt == 1:
        return ROOT, chain + ":solver", scope
    return ROOT, chain + ":solver", chain + ":redo", "%s:attempt-%d" % (scope, attempt)


def glm_scopes(chain, role, bench, k):
    """The scopes of a method-role call (GLM-5.3, §4.2-4.3; module docstring); in the smoke, ``chain`` "smoke" with
    ``bench`` and ``k`` None."""
    require(role in ROLES, "Unknown method role")
    if chain == SMOKE:
        require(bench is None and k is None, "The smoke's role scope is its own")
        return ROOT, SMOKE + ":glm"
    return ROOT, chain + ":glm", "%s:role:%s" % (_step(chain, bench, k), ROLES[role])


def role_scope_caps(pilot=PILOT, bench=None):
    """{role scope: cap} per step of the run configuration ``pilot`` (§9.3; R7b for the pilots; main: engineer 5M,
    examiner 5M, examiner research 9.2M, registrar 17:0x)."""
    require(pilot in PILOTS, "Unknown run configuration")
    from . import profiles
    if profiles.is_implant_v5(pilot):
        caps = CONFIG_ROLE_CAPS[pilot]
    elif profiles.is_v214(pilot) and bench == profiles.ZEBRA:
        caps = CONFIG_ROLE_CAPS[profiles.machinery_configuration(pilot, bench)]
    elif profiles.is_v211(pilot):
        from . import v211_limits
        caps = v211_limits.role_caps(bench or 'spreadsheetbench')
    else:
        caps = CONFIG_ROLE_CAPS[pilot]
    out = {"engineer": caps["engineer"], "examiner": caps["examiner"], "examiner:research": caps["examiner_research"]}
    from . import profiles
    if profiles.is_v29(pilot):
        out.update({role: caps[role] for role in ("audit_g", "audit_d")})
    return out


def step_kinds(configuration):
    from . import profiles
    return STEP_KINDS + (("confirm",) if profiles.is_v29(configuration) else ())


def audit_scopes(chain, judge, bench, k):
    """Separate judge subscopes, charged to the method total on both providers."""
    require(judge in ("G", "D"), "A registered audit judge")
    return ROOT, chain + ":glm", "%s:role:audit_%s" % (_step(chain, bench, k), judge.lower())


def chain_caps(chain, pilot=PILOT):
    """The registered caps of ``chain``'s own ledger in the run configuration ``pilot`` (the manifest's
    ``configuration``; §9.3; calc T6, T11; main: registrar 17:0x, ``protocol.MAIN_STEP_CAPS``): its solver cap, test
    read, redo reserve and role cap, and per step of the configuration's order the four step scopes, their redo
    attempts (each capped at the smaller of its step's cap and the redo reserve) and the three role scopes;
    ``overall`` is its solver cap plus its role cap."""
    require(pilot in PILOTS and chain in CHAINS, "Unknown pilot or chain")
    plan, step_caps, glm = PILOTS[pilot], CONFIG_STEP_CAPS[pilot], CONFIG_GLM_CAP[pilot]
    out = {ROOT: plan["solver_cap"] + glm, chain + ":solver": plan["solver_cap"],
           chain + ":test": plan["test_read_cap"], chain + ":redo": plan["redo_reserve"], chain + ":glm": glm}
    from . import profiles
    if profiles.is_v219(pilot):
        # The registered redo is a read-unit reserve, not an uncharged learning scope.
        out[chain + ":test"] += out.pop(chain + ":redo")
    out = {scope: cap for scope, cap in out.items() if cap > 0}
    for k, bench in enumerate(plan["order"], 1):
        if bench not in step_caps:
            continue  # v2.10: baseline has no learning; ALFWorld is a zero-call import.
        for kind in step_kinds(pilot):
            cap = step_caps[bench][kind]
            out[solver_scopes(chain, bench, k, kind)[-1]] = cap
            for attempt in range(2, MAX_REDOS + 2):
                out[solver_scopes(chain, bench, k, kind, attempt)[-1]] = min(cap, plan["redo_reserve"])
        for role, cap in role_scope_caps(pilot, bench).items():
            out["%s:role:%s" % (_step(chain, bench, k), role)] = cap
    return out


def first_call_scopes(chain):
    """The scopes of ``chain``'s first-call confirmation (registrar addendum 2026-10-22 14:10, row 7; module
    docstring): ``overall``, ``<c>:solver`` and ``<c>:confirm``."""
    require(chain in CHAINS, "Unknown chain")
    return ROOT, chain + ":solver", chain + ":" + CONFIRM


def first_call_caps(chain):
    """The confirmation's sub-scope and its registered cap (``FIRST_CALL_CAP``), which ``chain.run`` declares on the
    chain's own ledger beside ``chain_caps``."""
    require(chain in CHAINS, "Unknown chain")
    return {chain + ":" + CONFIRM: FIRST_CALL_CAP}


def caps(pilot=PILOT):
    """Every registered cap of both chains of a run root of configuration ``pilot`` in one listing (the manifest's
    ``caps`` and the S-E6 comparison of §10): ``chain_caps`` of G and D and their first-call confirmation caps
    (``first_call_caps``), with ``overall`` the sum of the two chains' totals. A run never declares this on one ledger;
    each chain's ledger declares its own ``chain_caps`` and ``first_call_caps``."""
    require(pilot in PILOTS, "Unknown pilot")
    out = {}
    for chain in launchable_chains(pilot):
        out.update({scope: cap for scope, cap in chain_caps(chain, pilot).items() if scope != ROOT})
        out.update(first_call_caps(chain))
    out[ROOT] = sum(chain_caps(chain, pilot)[ROOT] for chain in launchable_chains(pilot))
    return out


def smoke_caps(example=False):
    """The smoke ledger's caps (§9.3; calc T7): solver 14M, GLM 2M; with ``example`` (a v2 smoke that lists the
    example stage SX, ``protocol.SX_SLICES``) solver 80M, GLM 40M (``protocol.SMOKE_SX_CAPS``)."""
    caps = SMOKE_SX_CAPS if example else SMOKE_CAPS
    return {ROOT: caps["solver"] + caps["glm"], SMOKE + ":solver": caps["solver"], SMOKE + ":glm": caps["glm"]}


def probe_caps():
    """The S1 probe ledger's caps (§9.3, §10): 0.5M."""
    return {ROOT: PROBE_CAP, SMOKE + ":probe": PROBE_CAP}


def endpoint(setting, scopes, *, client, max_tokens_bound, sleep=time.sleep):
    """The frozen ``calls.Endpoint`` of one unit attempt and role (§4.1): ``client``'s model and its slot pool
    (``setting.slots[client.model]``), charged to ``scopes`` in ``setting.budget`` with ``max_tokens`` = the ledger
    bound B (``protocol.ledger_bound`` for a solver; ``ROLE_MAX_TOKENS`` for a role, M = B), ``setting.cooldown``
    between resends. ConfigurationError, before anything is sent, when the scopes do not start with the root and name
    exactly one total, when one of them is not declared in the ledger (the frozen ledger would quarantine itself,
    budget.py:299, :198-201, :205-222), when B is below the nominal M the client sends, or when the model has no slot
    pool."""
    scopes = tuple(scopes)
    if not scopes or scopes[0] != ROOT or len(set(scopes)) != len(scopes) or len(TOTALS.intersection(scopes)) != 1:
        raise ConfigurationError("Not a route-B scope set: %s" % (scopes,))
    if type(max_tokens_bound) is not int or max_tokens_bound < client.max_tokens:
        raise ConfigurationError("The ledger bound B must be at least the nominal M the request names")
    if client.model not in setting.slots:
        raise ConfigurationError("No slot pool for %s" % client.model)
    missing = sorted(set(scopes) - set(setting.budget.snapshot()))
    if missing:
        raise ConfigurationError("Undeclared ledger scopes: %s" % missing)
    return Endpoint(client, model=client.model, max_tokens=max_tokens_bound, slots=setting.slots[client.model],
                    budget=setting.budget, scopes=scopes, cooldown=setting.cooldown, sleep=sleep)
