"""A chain (registration §1, §10, §11, §13): stage 0's evaluation, then for each bench in the fixed order its learning
units (the method's ``step.learn``; a baseline's one frozen-learner unit, ``baseline.learn``) and the evaluation of the
stage's Skill on the five test sets.

Every evaluation unit runs in a child process whose stdout and stderr are a sealed diagnostics file from its first byte
(§0, §20.2: an in-process redirection cannot reach a descriptor someone else duplicated); the parent never reads that
file and learns only the unit's record or its paused attempt's status. The five units of a stage run side by side (the
global slots bound their calls); a stage whose evaluations do not all complete pauses the chain. E-glm's stage 0 is the
shared evaluation of the empty Skill on GLM-5.3 (``stage0-glm``), run once for E-glm and the two baselines; each
member's own stage-0 unit then reuses it. Before any stage-0 call, a child process runs the SpreadsheetBench test-side
qualification (§2.1; once for the run): no qualified test item stops the chain before stage 0.

One runner owns a chain while it runs (``.runner.lock``); the owner's termination needs the chain idle -- no runner and
no running evaluation child -- so a terminated chain issues no further work and only then can be unsealed. Every
terminal marker names its run. Nothing resumes by itself: after a pause the owner records a decision in the paused
attempt (``recovery.json``) or terminates the chain (``chain-terminated.json``); a restarted runner passes every
completed unit and redoes only the authorized one. An evaluation child that fails before it begins its attempt leaves
a paused attempt written by the parent, so its redo too needs the owner's decision. A launch manifest whose pinned
files changed refuses a chain that has not started and terminates one that has (§13.4: an interruption outside the
registered units).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import baseline, step
from .budget import OVERALL, chain_scope, deepseek_scope, step_scope
from .cells import Pause, exclusive
from .evaluation import _next_attempt, attempts
from .protocol import (
    BASELINE_LEARNING_CAP,
    CHAIN_CAP,
    DEEPSEEK_CEILING,
    DEEPSEEK_CHAIN_CAP,
    EVALUATION_CAP,
    LEARNING_CAP,
    ORDER,
    OVERALL_CEILING,
    SHARED_STAGE0,
    STAGE0_EVALUATION_CAP,
    VERSION,
)
from .skill import Skill
from .units import CHAINS

SHARED = "stage0-glm"
EXIT_COMPLETE, EXIT_PAUSED, EXIT_NO_QUALIFIED, EXIT_AWAITING = 0, 3, 4, 5
RUNNER_LOCK = ".runner.lock"
QUALIFICATION = "spreadsheetbench-qualification"
QUALIFICATION_PAUSES = {EXIT_NO_QUALIFIED: "no_qualified_test_items", EXIT_AWAITING: "awaiting_owner_decision",
                        EXIT_PAUSED: "qualification_paused"}


class Terminated(Exception):
    """The protocol terminated the chain (§13.4); its marker is written."""


def chain_root(setting, chain):
    return safe_path(setting.root) / chain


def start(setting, chain):
    """§1: the five task-card instructions together (each at the top of its section); v2 §2: chain E's scaffold (every
    section's heading and applicability line); the NoSkill-glm reference's empty Skill; a baseline's Skill is its frozen
    learner's text (§11), empty at the start."""
    if CHAINS[chain]["caps"] == "baseline":
        return ""
    kind = CHAINS[chain]["start"]
    if kind == "instructions":
        return Skill.seeded(setting.instructions)
    return Skill(scaffold=True) if kind == "scaffold" else Skill()


def learns(chain):
    """v2 §1: every chain but the references (NoSkill-glm; v3: NoSkill-ds) learns after its stage 0."""
    return CHAINS[chain]["caps"] != "N"


def text(skill):
    """The Skill text a solver receives: a method Skill rendered, a baseline's text as it is."""
    return skill if isinstance(skill, str) else skill.render()


def caps(chain, overall=OVERALL_CEILING):
    """The scopes a chain's calls are charged to, with their caps (§13.3); declared when the chain starts.
    ``overall``: what remains of the overall cap after the GLM-5.3 tokens spent before the run (the manifest's)."""
    kind = CHAINS[chain]["caps"]
    out = {OVERALL: overall, chain_scope(chain): CHAIN_CAP[chain]}
    if CHAINS[chain]["solver"] == "deepseek-v4-flash":  # v3 §9: the solver's own allowance, counted per step
        steps = [(0, "evaluation")] + ([] if kind == "N" else [(k, t) for k in range(1, len(ORDER) + 1)
                                                                for t in ("learning", "evaluation")])
        out.update({deepseek_scope(): DEEPSEEK_CEILING, deepseek_scope(chain): DEEPSEEK_CHAIN_CAP[chain],
                    **{deepseek_scope(chain, k, t): DEEPSEEK_CHAIN_CAP[chain] for k, t in steps}})
    if kind == "N":  # v2 §1: the reference evaluates stage 0 only
        if CHAINS[chain]["solver"] == "glm-5.3":
            out[step_scope(chain, 0, "evaluation")] = STAGE0_EVALUATION_CAP[kind]
        return out
    out.update({step_scope(chain, k, "learning"): BASELINE_LEARNING_CAP if kind == "baseline" else LEARNING_CAP[kind][b]
                for k, b in enumerate(ORDER, 1)})
    if CHAINS[chain]["solver"] == "glm-5.3":
        out.update({step_scope(chain, k, "evaluation"): EVALUATION_CAP[kind] for k in range(1, len(ORDER) + 1)})
        if chain in SHARED_STAGE0.get(SHARED, ()):  # E-glm's unit, charged to E-glm's chain scope: whoever runs it
            out[step_scope(SHARED, 0, "evaluation")] = STAGE0_EVALUATION_CAP["E"]
            out[chain_scope("E-glm")] = CHAIN_CAP["E-glm"]
        else:
            out[step_scope(chain, 0, "evaluation")] = STAGE0_EVALUATION_CAP[kind]
    return out


def evaluation_scopes(chain, stage):
    """The scopes of an evaluation unit's solver calls; v3 §9: a deepseek solver's own allowance (never a GLM-5.3
    scope)."""
    if chain == SHARED:
        return (OVERALL, chain_scope("E-glm"), step_scope(SHARED, 0, "evaluation"))
    if CHAINS[chain]["solver"] != "glm-5.3":
        return deepseek_scopes(chain, stage, "evaluation")
    return (OVERALL, chain_scope(chain), step_scope(chain, stage, "evaluation"))


def deepseek_scopes(chain, stage=None, kind=None):
    """v3 §9: the scopes of a deepseek chain's solver calls -- with a step's own count, or (the smoke's format check)
    without one."""
    return (deepseek_scope(), deepseek_scope(chain)) + (() if stage is None else (deepseek_scope(chain, stage, kind),))


def unit_root(setting, chain, stage, benchmark):
    return safe_path(setting.root) / chain / ("s%d" % stage) / "evaluation" / benchmark


def _status(root, name, code):
    """A Pause for an evaluation unit that did not complete: the child found the last attempt still awaiting the
    owner's decision, or the attempt it ran ended with a status."""
    found = attempts(root)
    if code == EXIT_AWAITING and found:
        return Pause("awaiting_owner_decision", found[-1].name, name)
    if found and (found[-1] / "status.json").exists():
        status = read_json(found[-1] / "status.json", sealed=True)
        return Pause(status.get("kind", "exception"), status.get("reason", "unknown"), name)
    return Pause("exception", "evaluation_child_ended_without_status", name)


def _child(setting, arguments, name):
    """Run ``scripts/run_coevo5.py <arguments>`` in a child process whose stdout and stderr are a sealed file from its
    first byte; returns the exit code."""
    logs = safe_path(setting.shared) / "host_only" / "diagnostics"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / ("child-%s-%d.log" % (name, time.time_ns()))
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_coevo5.py"
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        process = subprocess.run([sys.executable, str(script), *arguments], stdin=subprocess.DEVNULL,
                                 stdout=descriptor, stderr=descriptor, check=False)
    finally:
        os.close(descriptor)
    return process.returncode


def launch_child(setting, spec):
    """One evaluation unit in a child process (``evaluate-unit``)."""
    name = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
    spec_path = safe_path(setting.shared) / "host_only" / "specs" / (name + ".json")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    if not spec_path.exists():
        write_json(spec_path, spec)
    return _child(setting, ["evaluate-unit", "--manifest", str(setting.extra["manifest"]), "--spec", str(spec_path)],
                  name)


def qualify_child(setting):
    """The SpreadsheetBench test-side qualification (``qualify-test-sheet``, zero model calls) in a child process."""
    return _child(setting, ["qualify-test-sheet", "--manifest", str(setting.extra["manifest"])], "qualification")


def _failed_start(root, code):
    """§13.4 for a child that ended before it began its attempt: the parent writes the paused attempt, so the redo
    needs the owner's decision like any other."""
    attempt = _next_attempt(root)
    if attempt is not None:
        attempt.mkdir(parents=True)
        write_json(attempt / "status.json", seal({"status": "paused", "kind": "exception",
                                                  "reason": "child_failed_before_its_attempt", "exit": code}))


def evaluate(setting, chain, stage, skill, previous, *, launch=launch_child):
    """The stage's five evaluation units (children, side by side) of the Skill text ``skill``. Returns {bench: unit
    root}; raises the first ``Pause`` once every child has ended. A unit is complete once its record exists (it is
    written only after the child's sealed output was flushed)."""
    roots = {b: unit_root(setting, chain, stage, b) for b in ORDER}

    def one(bench):
        root = roots[bench]
        name = "%s/s%d/evaluation/%s" % (chain, stage, bench)
        if not (root / "unit.json").exists():
            spec = {"chain": chain, "stage": stage, "benchmark": bench, "skill": skill,
                    "unit_root": str(root), "previous": None if previous is None else str(previous[bench])}
            before = len(attempts(root))
            code = launch(setting, spec)
            if not (root / "unit.json").exists():
                if code != EXIT_AWAITING and len(attempts(root)) == before:
                    _failed_start(root, code)
                return code, _status(root, name, code)
        record = read_json(root / "unit.json", sealed=True)
        require(record["run"] == setting.run and record["chain"] == chain and record["stage"] == stage
                and record["skill_sha256"] == digest(skill), "An evaluation unit of another run or Skill")
        return 0, None

    with ThreadPoolExecutor(max_workers=len(ORDER)) as pool:
        results = list(pool.map(one, ORDER))
    for _, pause in results:
        if pause is not None:
            raise pause
    return roots


def _stage0(setting, chain, skill, *, launch, qualify):
    """Stage 0: the SpreadsheetBench test-side qualification first (no stage-0 call before it found a qualified item),
    then the shared units (one member runs them; the others wait, then reuse them) and the chain's own."""
    if not all((unit_root(setting, chain, 0, b) / "unit.json").exists() for b in ORDER):
        code = qualify(setting)
        if code != EXIT_COMPLETE:
            raise Pause(QUALIFICATION_PAUSES.get(code, "qualification_failed"), "exit %d" % code, QUALIFICATION)
    if chain in SHARED_STAGE0.get(SHARED, ()):
        with exclusive(safe_path(setting.root) / SHARED / RUNNER_LOCK, wait=True):
            shared = evaluate(setting, SHARED, 0, text(skill), None, launch=launch)
        return evaluate(setting, chain, 0, text(skill), shared, launch=launch)
    return evaluate(setting, chain, 0, text(skill), None, launch=launch)


def _terminal(root, identity):
    """"complete" or "terminated" when the chain of this run has ended, else None; a marker of another run stops."""
    if (root / "chain.json").exists():
        require(read_json(root / "chain.json", sealed=True)["identity"] == identity, "A chain of another run")
    for marker, status in (("chain-terminated.json", "terminated"), ("chain-complete.json", "complete")):
        if (root / marker).exists():
            require(read_json(root / marker, sealed=True)["identity"] == identity, "A terminal marker of another run")
            return status
    return None


def _verified(root, identity, verify):
    """The pinned files still match the manifest; otherwise the started chain is terminated (§13.4)."""
    try:
        verify()
    except ValueError as error:
        write_json(root / "chain-terminated.json", seal({"identity": identity, "by": "protocol",
                                                        "decision": "manifest_mismatch: %s" % str(error)[:300]}))
        raise Terminated("manifest_mismatch") from None


def run(setting, chain, *, launch=launch_child, qualify=qualify_child):
    """Run the chain until it completes, pauses or is terminated. Returns {"status": "complete" | "paused" |
    "terminated", ...}. One runner per chain: a second one fails at once."""
    require(chain in CHAINS, "Unknown chain")
    root = chain_root(setting, chain)
    root.mkdir(parents=True, exist_ok=True)
    identity = {"run": setting.run, "chain": chain}
    with exclusive(root / RUNNER_LOCK):
        ended = _terminal(root, identity)
        if ended is not None:
            return {"status": ended}
        verify = setting.extra.get("verify", lambda: None)
        if not (root / "chain.json").exists():
            verify()  # before the chain starts, a mismatch refuses the run and writes nothing
            write_json(root / "chain.json", seal({"version": VERSION + "-chain", "identity": identity}))
        setting.budget.declare(caps(chain, setting.extra.get("overall", OVERALL_CEILING)))
        skill = start(setting, chain)
        try:
            _verified(root, identity, verify)
            previous = _stage0(setting, chain, skill, launch=launch, qualify=qualify)
            learn = baseline.learn if CHAINS[chain]["caps"] == "baseline" else step.learn
            for stage in range(1, len(ORDER) + 1 if learns(chain) else 1):
                _verified(root, identity, verify)
                skill, _ = learn(setting, root, chain, stage, skill)
                previous = evaluate(setting, chain, stage, text(skill), previous, launch=launch)
        except Pause as pause:
            return {"status": "paused", "kind": pause.kind, "reason": pause.reason, "unit": pause.cell}
        except Terminated as ended:
            return {"status": "terminated", "reason": str(ended)}
        write_json(root / "chain-complete.json", seal({"identity": identity, "skill_sha256": digest(text(skill)),
                                                       "skill": skill if isinstance(skill, str) else skill.to_json()}))
        return {"status": "complete"}


def _owned(lock):
    try:
        with exclusive(lock):
            return False
    except ValueError:
        return True


def terminate(setting, chain, *, decision):
    """§13.4 (a): the owner ends the chain; its sealed scores may then be read (``evaluation.unseal``). Only an idle
    chain can be terminated: no runner, no running evaluation child."""
    require(isinstance(decision, str) and decision.strip(), "A termination records the owner's decision")
    root = chain_root(setting, chain)
    root.mkdir(parents=True, exist_ok=True)
    identity = {"run": setting.run, "chain": chain}
    with exclusive(root / RUNNER_LOCK):  # fails while the chain's runner runs
        require(_terminal(root, identity) is None, "The chain has ended")
        busy = [str(lock.parent) for lock in sorted(root.glob("s*/evaluation/*/.lock")) if _owned(lock)]
        require(not busy, "Evaluation units are still running: %s" % busy[:3])
        write_json(root / "chain-terminated.json", seal({"identity": identity, "by": "owner", "decision": decision}))
