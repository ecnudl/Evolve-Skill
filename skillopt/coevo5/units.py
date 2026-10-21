"""Learning units (registration §13.4) and what every unit attempt is given.

A chain is a fixed sequence of units; a unit writes its record once, when an attempt completes. The attempt rules are
the evaluation units' (``evaluation``): one process owns a unit while it runs, attempts are numbered directories, and an
attempt after a pause or an interruption runs only once the owner's decision is recorded in the earlier attempt
(``recovery.json``); a completed unit is never run again, and its record must name the same run and identity. A pause
writes the attempt's status and is raised; any other error (a configuration check, a crash) pauses the unit the same
way, its traceback kept in the attempt's diagnostics -- a learning unit holds training data only, never a test item.

``Setting`` holds what a chain process needs from the launch manifest; ``endpoints`` builds a unit attempt's two
endpoints -- the solver's and the method roles' -- charged to the unit's scopes (§13.2): v3 §9: a deepseek solver to its
own allowance (never a GLM-5.3 scope); every method role is GLM-5.3, charged to the chain's learning step.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from .budget import OVERALL, chain_scope, step_scope
from .calls import Endpoint
from .cells import STOP_KINDS, Context, Pause, exclusive
from .evaluation import _next_attempt, attempts
from .protocol import (
    READ_TIMEOUT_SECONDS,
    RESEND_COOLDOWN_SECONDS,
    ROLE_MAX_TOKENS,
    ROLE_MODEL,
    ROLE_READ_TIMEOUT_SECONDS,
    SOLVER_MAX_TOKENS,
    VERSION,
)

CHAINS = {  # §1: the method's chains and the two baselines (§11: frozen learners, ``baseline``)
    "E-glm": {"solver": "glm-5.3", "start": "scaffold", "caps": "E"},  # v2 §2: the scaffold, not the empty Skill
    "I-glm": {"solver": "glm-5.3", "start": "instructions", "caps": "I"},
    "E-ds": {"solver": "deepseek-v4-flash", "start": "scaffold", "caps": "ds"},
    "I-ds": {"solver": "deepseek-v4-flash", "start": "instructions", "caps": "ds"},
    "SkillOpt-glm": {"solver": "glm-5.3", "start": "empty", "caps": "baseline"},  # v2 §1: defined, not run
    "GEPA-glm": {"solver": "glm-5.3", "start": "empty", "caps": "baseline"},
    "NoSkill-glm": {"solver": "glm-5.3", "start": "empty", "caps": "N"},  # v2 §1: stage 0 only, the empty Skill
    "NoSkill-ds": {"solver": "deepseek-v4-flash", "start": "empty", "caps": "N"},  # v3 §1: deepseek's reference
}


@dataclass
class Setting:
    """``pools``: each bench's training pool (SpreadsheetBench: its qualified part); ``regression``: {bench: {"items":
    [task ids], "tolerance": t_b}} (empty items: no panel); ``tolerance``: t_k per bench; ``cards``: the public task
    cards; ``rubrics``: the six initial rubrics; ``instructions``: the five task-card instructions (chain I's start);
    ``clients(model, max_tokens, read_timeout)``: a client with ``call(system, user)``; ``slots``: {name:
    calls.Slots} for the two models and the native pools; ``sources(store)``: the research sources archiving under
    ``store`` (``research.Sources``)."""

    run: str
    root: Path
    shared: Path
    pools: dict
    regression: dict
    tolerance: dict
    cards: dict
    rubrics: dict
    instructions: dict
    runtime: dict
    clients: object
    budget: object
    slots: dict
    sources: object
    workers: int = 16
    seed: int = 20261017
    cooldown: int = RESEND_COOLDOWN_SECONDS
    extra: dict = field(default_factory=dict)


def scopes(chain, stage, kind):
    return (OVERALL, chain_scope(chain), step_scope(chain, stage, kind))


def endpoints(setting, chain, stage, kind="learning"):
    """(solver endpoint, role endpoint) of one unit attempt, built when the attempt begins (the ledger's halt
    generation is taken then)."""
    from .chain import deepseek_scopes

    solver = CHAINS[chain]["solver"]
    charged = scopes(chain, stage, kind)
    glm = solver == ROLE_MODEL
    solve = solver_endpoint(setting, solver, charged if glm else deepseek_scopes(chain, stage, kind))
    role = Endpoint(setting.clients(ROLE_MODEL, ROLE_MAX_TOKENS, ROLE_READ_TIMEOUT_SECONDS), model=ROLE_MODEL,
                    max_tokens=ROLE_MAX_TOKENS, slots=setting.slots[ROLE_MODEL], budget=setting.budget,
                    scopes=charged, cooldown=setting.cooldown)
    return solve, role


def solver_endpoint(setting, solver, charged):
    """A solver's endpoint; ``charged``: its scopes (v3: a deepseek solver's own), or None: uncharged (v1-v2's free
    deepseek route)."""
    return Endpoint(setting.clients(solver, SOLVER_MAX_TOKENS[solver], READ_TIMEOUT_SECONDS), model=solver,
                    max_tokens=SOLVER_MAX_TOKENS[solver], slots=setting.slots[solver],
                    budget=None if charged is None else setting.budget, scopes=charged or (),
                    cooldown=setting.cooldown)


def cell_context(setting, attempt, endpoint):
    return Context(store=attempt, endpoint=endpoint, runtime=setting.runtime,
                   native=setting.slots["spreadsheet-native"], episodes=setting.slots["alfworld-episode"])


def unit_path(chain_root, stage, name):
    return safe_path(chain_root) / ("s%d" % stage) / name


def complete(unit_root, *, run, identity):
    """The unit's record when it is complete (same run and identity), else None."""
    path = safe_path(unit_root) / "unit.json"
    if not path.exists():
        return None
    record = read_json(path, sealed=True)
    require(record["run"] == run and record["identity"] == identity,
            "A completed unit of another run or with another identity: " + str(unit_root))
    return record


def run_unit(unit_root, *, run, identity, work):
    """Run ``work(attempt)`` -> result (a JSON-safe dict) in the unit's next attempt, unless the unit is complete.
    Returns the unit's record; raises ``Pause`` after writing the attempt's status."""
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
        attempt.mkdir()
        write_json(attempt / "started.json", seal({"run": run, "identity": identity}))
        try:
            result = work(attempt)
        except Pause as pause:
            write_json(attempt / "status.json", seal({"status": "paused", "kind": pause.kind, "reason": pause.reason,
                                                      "cell": pause.cell}))
            raise
        except Exception as error:  # a stop of the run, a configuration check or a crash: the unit pauses
            (attempt / "diagnostics.log").write_text(traceback.format_exc(), encoding="utf-8")
            kind = next((k for cls, k in STOP_KINDS.items() if isinstance(error, cls)),
                        "configuration" if isinstance(error, ValueError) else "exception")
            write_json(attempt / "status.json", seal({"status": "paused", "kind": kind,
                                                      "reason": type(error).__name__}))
            raise Pause(kind, type(error).__name__, name) from error
        record = seal({"version": VERSION + "-unit", "run": run, "identity": identity, "status": "complete",
                       "attempt": attempt.name, "result": result})
        write_json(unit_root / "unit.json", record)
        return record
