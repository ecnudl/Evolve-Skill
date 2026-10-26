"""The route-B smoke (registration §10, §9.3, §21 (c); implementation plan §10 and the smoke row of §1): a sealed
specification, one judged record per stage, the S0 sandbox self-test, the S1 probe dispatch, the dispatch-time receipt
classes, the S4 fault switch and ``smoke-result.json``.

``make`` writes the specification once (``<root>/smoke.json``, zero calls): the smoke solver (chain D's elucid model,
owner rule 22:3x (c), the registered default; or, pinned by ``solver_chain`` -- registrar addendum 2026-10-23 02:3x
-- chain G's GLM-5.3 through its frozen client, with no S1, no probe root and no control cells: ``solver_of``), the
smoke and probe ledgers' caps, the bound item files (SearchQA tail and ALFWorld smoke games; the
registrar's engineering fixtures for OfficeQA, LiveMath and SpreadsheetBench), the stage plan of §10, the stages the
smoke passes on (``stages``, default ``SMOKE_STAGES`` = S0, S1, S2, S3 and S-E6: the registrar's trim of 2026-10-22
13:0x on the owner's instruction; S-N1 and S4 stay runnable and never gate unless listed), the control cells (the
enumerated fault-drill cells, Codex F19; default none, addendum 13:4x: the S4 drill, their only source, is dropped),
the S-N1 noise anchor (required only when S-N1 is listed; otherwise null with the reason, ``TRIMMED``), the sealed S0
sandbox self-test (its measurements and the limits registered from them, written before S1, plan §10 step 3), the code
map and the environment.

Each stage function judges what its stage measured and returns ``{"rows": {...}, "passed": bool, ...}``; ``record``
stores it write-once under ``<root>/stages/``.

- ``s0``: every zero-call row of the §10 S0 table passed (pytest on the snapshot, empty-package equivalence, the
  exception classes, ledger, sandbox, escape probe, measurements, determinism, D3 replay, item supply, sheet
  qualification, consumption registry, the Codex-round fixtures, no leftovers).
- ``s1_probe``: rows a-f and the prompt overhead (≤ 512 tokens over the request bytes); S1-b decides branch E (every
  completion within its M) or N (``longest`` recorded); S1-e must be judged ``reasoning_mismatch``.
- ``s2_solver``: the format floor 9/10 for every bench and arm and X, P at most 1/20 below C (coevo5 smoke.py:73-77,
  ``format_check``); the receipt classes of Codex F19 (``receipt_classes``); every hook fired; reservations equal
  settlements; no leftovers (S3 runs beside S2 in its own process, registrar addendum 14:3x: its process, containers
  and open reservations are listed apart, not S2's).
- ``sn1_noise``: the same-text disagreement of two identical card arms against the registered anchor; above 1.25 x the
  anchor the MDE and sizes are re-registered before the pilot (§3.3).
- ``se6_cost``: per scope, measured tokens per cell x the measured ledger/actual ratio x the maximum-schedule cell
  count + one full next reservation within the cap; the ratio at most 1.5 (§9.3). ``glm_projection``: per GLM scope,
  S3's measured tokens per role call x the registered maximum role calls per step + one full next reservation, at
  no less than a full role input, within the cap (registrar addenda 14:3x, 14:4x).
- ``s3_roles``, ``s4_ministep``: the registered role calls and the mini-step's unit, consumption, sealing and redo ran.

Dispatch (the parts of the smoke that send or start something):
- ``sandbox_selftest`` (S0, zero model calls): the escape probe (``escape_probe.py``, fixed registrar code) in one
  container started with the registered argv, judged by ``escape_rows`` -- no network, read-only ``/`` and
  ``/runner``, uid 65534 without capabilities, exactly the 13 registered environment keys (``REGISTERED_ENV_KEYS``),
  no credential, ledger or consent file, pids and memory limits -- plus one ping of an empty-package worker (VSZ/RSS,
  container start latency) and the p99 public-view size of the given item files; one sealed record.
- ``run_probe`` (S1, ≤ 60 calls in all attempts): on the probe's OWN ledger root (cap 0.5M); rows a, b, c and e with
  the ledger bound B_probe = 32,768, sequential; d = 8 concurrent calls with M = B = 64; e through ``ControlClient``,
  the registered client with ``reasoning_effort`` left out of the body; the first single call (a) must be a confirmed
  reply of the registered model before any further call, and every request goes through the explicit PJLAB gateway
  with ``trust_env=False`` (f). Each send goes out once (no resend: S1-e's mismatch is the point of the probe). Only
  counts and classes are kept -- never a reply text or a credential. An attempt that is stopped (first call not
  confirmed, or a ledger stop) is kept as an attempt record and does not judge S1.
- ``classed_sends``: a cell's recorded sends as receipt-class entries at dispatch time (Codex F19): the class is
  stamped when the cell is dispatched and ``receipt_classes`` refuses an entry whose stamp differs from its own
  verdict.
- ``FaultSwitch`` (S4): the registered ``SandboxUnavailable`` drill, available only for units under the smoke root.
- ``run_stage`` (S2, S-N1, S-E6, S3, S4): S2 and S-N1 as the stage's copied units on the Setting of the smoke manifest
  (``manifest.setting_of(m, "smoke")``, the smoke ledger and caps), one unit per item set under
  ``<root>/units/<stage>/<set>``, cells dispatched through ``rounds.run_round`` in one seeded interleaved order per
  unit (§6.2); the single first cell runs alone and must come back as a confirmed reply of the registered model
  before anything concurrent (plan §10 step 4); receipts are classed at dispatch (``classed_sends``); a unit that
  stops keeps its attempt and the stage is reported, never judged; ``fake`` runs the same path on the plan-§7 fakes.
  S-E6 is zero-call (``se6_projection``, after S2 and S3 are recorded: the measured cost of the S2 cells, with the
  ledger ratio over every solver cell the smoke ledger settled, projected onto every solver scope of both chains at
  the registered maximum schedule; S3's measured tokens per role call projected onto every GLM scope of both chains at
  the registered maximum role calls). S3 is ``smoke_roles.run`` (its own run unit, then the six role pieces;
  registrar addendum 14:3x). S4 is the mini-step (``step.run_step`` in its smoke mode,
  ``step.SmokeStep``) with the drill: the fault switch pauses the accept unit's first attempt, the operator writes
  the owner-format ``recovery.json`` labelled smoke (``write_recovery``, CLI ``smoke-recovery``: ``add_arguments``,
  ``recovery_cli``; never automatic) and the same ``run_stage`` call redoes the paused block (§9.3, owner decision
  #15: the drill stops inside block 1, so attempt-2 redoes block 1 whole and runs blocks 2-4; ``s4_judged``).

Receipt classes (Codex F19): CONTROL = S1-e and the enumerated fault-drill cells (listed, excluded); PROBE = S1-a..d
and f (registered body, probe-only M/B; listed, not counted, leak-free); PRODUCTION = S2, S-N1 and S4 receipts sent
with the registered body AND the registered M and B; RESEND = frozen-path resends (counted apart, leak-free). Any
other receipt is UNREGISTERED and fails the stage. A leak is a receipt with subtype ``reasoning_mismatch``. A chain-G
smoke (registrar addendum 2026-10-23 02:3x) has no S1-e and no control cells, and the frozen GLM client's receipts
carry no subtype (its thinking stays enabled, so it never reports ``thinking_mismatch``): its leak counts stay zero.
"""
from __future__ import annotations

import contextlib
import datetime
import fnmatch
import hashlib
import json
import math
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.evaluation import attempts, recovered
from skillopt.coevo5.ledger import reservation
from skillopt.coevo5.outcomes import undelivered
from skillopt.coevo5.protocol import RESEND_COOLDOWN_SECONDS
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import (acceptance, budgets, client, engineer, fixtures, manifest, precheck, prelaunch, rounds, router,
               slots, solver, step, trajectories, units)
from . import profiles as protocol
from . import protocol as historical_protocol
from . import placebo as placebos
from .cells import Arm, Pause, cell_id
from .chain import FIRST_CALL_ECHO
from .errors import AssumptionBroken, BudgetStop, LedgerFailure, SandboxUnavailable
from .package import empty
from .registry import Registry
from .sandbox import client as sandbox

SPEC, RESULT, STAGES_DIR = "smoke.json", "smoke-result.json", "stages"
STAGES = ("S0", "S1", "S2", "SN1", "SE6", "S3", "S4", "SX")  # SX: v2's example (owner decision 2026-10-23 13:3x)
V1_STAGES = tuple(stage for stage in STAGES if stage != "SX")  # Codex review 2026-10-23 #2: a spec that does not
# list SX serializes, defaults and sums up exactly as before v2
SMOKE_STAGES = ("S0", "S1", "S2", "S3", "SE6")  # registrar addendum 2026-10-22 13:0x (owner): the stages that gate
# registrar addendum 2026-10-23 02:3x ("smoke solver chain"): a chain-G smoke has no S1 -- chain D's elucid probe stays
# chain D's launch precondition -- and gates on every other registered smoke stage
G_SMOKE_STAGES = tuple(stage for stage in SMOKE_STAGES if stage != "S1")
NO_S1 = "S1 is chain D's elucid probe; a chain-G smoke has no S1 (registrar addendum 2026-10-23 02:3x)"
TRIMMED = ("registrar addendum 2026-10-22 13:0x (owner instruction): S-N1 is not a stage of this smoke, so no noise "
           "anchor is registered (addendum 13:4x)")
S0_ROWS = ("pytest", "equivalence", "exceptions", "ledger", "sandbox", "escape_probe", "measurements", "determinism",
           "replay", "supply", "sheet", "registry", "codex_fixtures", "leftovers")
S1_ROWS = ("a", "b", "c", "d", "e", "f")
# §1: what a zero-call rehearsal (``probe --fake``, ``smoke-run --fake``) records is an engineering fixture, never smoke
# evidence (registrar addendum 2026-10-22 15:0x: ``probe --fake`` records its evidence as a rehearsal, never as S1); a
# smoke result with any such stage carries the same label, and so does a test-read estimate made from it
REHEARSAL_EVIDENCE = "engineering_fixture"
S3_ROWS = ("engineer", "detector", "generator_research", "leakage", "describer", "glm_cap")  # smoke_roles.ran_rows
S4_ROWS = ("unit", "consumption", "sealing", "redo")
SX_ROWS = ("unit", "training", "acceptance", "consumption", "ledger")  # v2's example (``sx_judged``)
ARMS = ("C", "X", "P")  # §10 S2: card, fixture package, its placebo (plus twin cells)
COMPARED = ("X", "P")
PRODUCTION_STAGES = ("S2", "SN1", "S4")
CONTROL, PROBE, PRODUCTION, RESEND, UNREGISTERED = "control", "probe", "production", "resend", "unregistered"
REGISTERED_BODY = "registered"  # reasoning_effort "none", temperature 0, [system, user]
CONTROL_BODY = "no_reasoning_effort"  # S1-e only
ITEM_SETS = ("searchqa", "alfworld", "officeqa", "livemath", "spreadsheetbench")
PLAN = {  # §10: items x runs x arms per stage (ALFWorld trimmed to 6 games x 1 run x C, X, P in S2)
    "S2": {"searchqa": {"items": 20, "runs": 2, "arms": ["C", "X", "P", "twins"]},
           "officeqa": {"items": 20, "runs": 2, "arms": ["C", "X", "P", "twins"]},
           "livemath": {"items": 20, "runs": 2, "arms": ["C", "X", "P", "twins"]},
           "spreadsheetbench": {"items": 20, "runs": 2, "arms": ["C", "X", "P", "twins"]},
           "alfworld": {"items": 6, "runs": 1, "arms": ["C", "X", "P"]}},
    "SN1": {"searchqa": {"items": 200, "runs": 1, "arms": ["C", "C_dup"]},
            "alfworld": {"items": 6, "runs": 1, "arms": ["C", "C_dup"]}},
    "S4": {"searchqa": {"run": protocol.S4_SLICES["run"], "accept": protocol.S4_SLICES["accept"]}},
    "SX": {"searchqa": {"run": protocol.SX_SLICES["run"], "accept": protocol.SX_SLICES["accept"]}},
}

# ------------------------------------------------------------------------------- the S0 sandbox self-test (§2.6)
SELFTEST = "sandbox-selftest.json"
ESCAPE_PROBE = Path(__file__).with_name("escape_probe.py")
ESCAPE_SECONDS = 180  # the probe ran 1.9 s in the B2 check; its pids row sleeps forked children briefly
# the container's environment (integration note B2, open item 3): the 5 registered --env keys, the 6 keys the pinned
# image defines and the 2 docker sets -- nothing else, no credential
REGISTERED_ENV_KEYS = ("EXECSKILL_SANDBOX", "GPG_KEY", "HOME", "HOSTNAME", "LANG", "MKL_NUM_THREADS", "OMP_NUM_THREADS",
                       "OPENBLAS_NUM_THREADS", "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHON_SHA256",
                       "PYTHON_VERSION")
REGISTERED_ENV = {"PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                  "EXECSKILL_SANDBOX": "execskill-worker-v1"}
ESCAPE_ROWS = ("network", "read_only", "identity", "env_keys", "no_secrets", "limits", "worker_child", "python_flags")
SECRET_NAMES = ("*.env", "consent*", "ledger*")  # the image's own "*key*" files are listed, never a credential
UNSENT = ("connected", "sent", "resolved")

# ------------------------------------------------------------------------------------- the S1 probe (§10 S1)
PROBE_SCOPE = budgets.SMOKE + ":probe"
PROBE_SYSTEM = "You are a connectivity probe. Follow the user's instruction exactly."
PROBE_SHORT = "Reply with the single word: ready"
PROBE_LONG = ("Write a plain-prose essay of about 1,500 words on the history of the printing press, "
              "without headings or lists.")
PROBE_CALLS = 1 + len(protocol.S1B_TOKENS) * protocol.S1B_REPEATS + 1 + protocol.S1_CONCURRENCY + 1  # a, b, c, d, e
PROBE_FIELDS = ("ok", "error_type", "subtype", "returned_model", "finish_reason", "usage", "reasoning_tokens",
                "seconds")


def _fraction(value):
    return "%d/%d" % (value.numerator, value.denominator)


def make(root, *, items, selftest, control_cells=(), noise_anchor=None, stages=None, environment_found=None,
         write=True, probe_root=None, solver_chain="D"):
    """The sealed smoke specification at ``<root>/smoke.json`` (zero calls). ``items``: {set: path} of the item files
    (``ITEM_SETS``); ``selftest``: the path of the sealed, passing S0 sandbox self-test (``sandbox_selftest``), whose
    limits and measurements the spec binds; ``control_cells``: the enumerated fault-drill cell ids (default none,
    registrar addendum 13:4x); ``noise_anchor``: {bench: the registered per-item SD of a same-text paired difference}
    for S-N1, required when S-N1 is one of ``stages``, else optional (None: recorded null with the reason
    ``TRIMMED``); ``stages``: the stages ``summary`` passes on, recorded in the spec (default ``SMOKE_STAGES``, plus
    S-N1 and/or S4 if listed; v2: SX, the example of the train-then-accept step, whose smoke ledger then has the
    example caps ``budgets.smoke_caps(example=True)``); ``write`` False: a dry run that writes nothing; ``probe_root``: the S1 probe's own
    ledger root, apart from the smoke root (default ``historical_protocol.PROBE_ROOT``; a rehearsal names its own, registrar
    addendum 15:0x), where ``run_probe`` writes and S2 reads the probe's receipts; ``solver_chain`` (registrar addendum
    2026-10-23 02:3x, ``protocol.SMOKE_SOLVER_CHAINS``): "D", the registered default, whose specification is
    unchanged, or "G" -- GLM-5.3 through its frozen client with chain G's registered settings (M = B = 65,536 on every
    bench, read timeout 2,400 s, echo glm-5.3), recorded as the solver block's ``chain``, the elucid-only fields
    (``reasoning_effort``, ``b_probe``, ``s1d_tokens``) null; a chain-G smoke has no S1 (``NO_S1``): its stages are
    ``G_SMOKE_STAGES`` (plus S-N1 and/or S4 if listed, never S1), its probe root null and its control cells none (the
    control client is elucid's). Returns the record."""
    require(solver_chain in protocol.SMOKE_SOLVER_CHAINS, "The smoke solver chain is D or G (registrar addendum "
            "2026-10-23 02:3x)")
    chain_g = solver_chain == "G"
    root = safe_path(root)
    probe = None if chain_g else safe_path(historical_protocol.PROBE_ROOT if probe_root is None else probe_root)
    require(not (root / SPEC).exists(), "A smoke runs in a new directory")
    if chain_g:
        require(probe_root is None, "A chain-G smoke names no probe root: " + NO_S1)
        require(not control_cells, "A chain-G smoke has no control cells (the control client is elucid's)")
    else:
        require(probe != root and not probe.is_relative_to(root) and not root.is_relative_to(probe),
                "The S1 probe has its own ledger root, apart from the smoke's")
    require(set(items) == set(ITEM_SETS), "One item file per set: %s" % (ITEM_SETS,))
    stages = tuple((G_SMOKE_STAGES if chain_g else SMOKE_STAGES) if stages is None else stages)
    if chain_g:  # registrar addendum 2026-10-23 02:3x: S0, S2, S3 and S-E6 gate; S1 never
        require(set(G_SMOKE_STAGES) <= set(stages) <= set(STAGES) - {"S1"} and len(set(stages)) == len(stages),
                "A chain-G smoke passes on S0, S2, S3 and S-E6, with S-N1 or S4 optionally; " + NO_S1)
    else:
        require(set(SMOKE_STAGES) <= set(stages) <= set(STAGES) and len(set(stages)) == len(stages),
                "The smoke passes on S0, S1, S2, S3 and S-E6 (registrar addendum 13:0x), with S-N1 or S4 optionally")
    require(isinstance(control_cells, (list, tuple)) and all(type(c) is str and c for c in control_cells)
            and len(set(control_cells)) == len(control_cells), "The control cells are enumerated by id")
    require(noise_anchor is not None or "SN1" not in stages, "A noise anchor per S-N1 bench when S-N1 is a stage")
    require(noise_anchor is None or (isinstance(noise_anchor, dict) and set(noise_anchor) == set(PLAN["SN1"]) and all(
        type(v) is float and v > 0 for v in noise_anchor.values())), "A noise anchor per S-N1 bench")
    tested = protocol.verified(read_json(selftest), "sandbox-selftest")
    require(tested["passed"] is True, "The S0 sandbox self-test did not pass; no smoke")
    bound = {}
    for name, path in sorted(items.items()):
        found = read_json(path)
        require(isinstance(found, list) and found, "An item file holds a list of items")
        bound[name] = {"path": str(safe_path(path)), "sha256": manifest._sha(safe_path(path)), "count": len(found)}
    model = protocol.CHAINS[solver_chain]  # chain D: protocol.SMOKE_SOLVER, the registered default
    elucid_only = ({"reasoning_effort": None, "b_probe": None, "s1d_tokens": None} if chain_g else
                   {"reasoning_effort": protocol.REASONING_EFFORT, "b_probe": protocol.B_PROBE,
                    "s1d_tokens": protocol.S1D_TOKENS})
    fields = {"root": str(root), "probe_root": None if chain_g else str(probe), "solver": {
        **({"chain": "G"} if chain_g else {}),  # a chain D spec stays as registered (no ``chain``: "D")
        "model": model, "M": {b: protocol.solver_tokens(model, b) for b in protocol.BENCHES},
        "read_timeout": {b: protocol.read_timeout(model, b) for b in protocol.BENCHES}, "proxy": protocol.GATEWAY,
        **elucid_only, "response_model_ids": sorted(FIRST_CALL_ECHO[solver_chain])},
        "caps": {"smoke": budgets.smoke_caps(example="SX" in stages), "probe": budgets.probe_caps()}, "items": bound,
        "plan": plan_of(stages),
        "format": {"floor": _fraction(protocol.SMOKE_FORMAT_FLOOR), "margin": _fraction(protocol.SMOKE_FORMAT_MARGIN)},
        "min_production_receipts": protocol.MIN_PRODUCTION_RECEIPTS, "control_cells": sorted(control_cells),
        "stages": list(stages), "noise_anchor": noise_anchor,
        **({"noise_anchor_reason": TRIMMED} if noise_anchor is None else {}), "code": manifest.pin_code(),
        "sandbox": {"selftest": {"path": str(safe_path(selftest)), "record_sha256": tested[protocol.RECORD_HASH]},
                    "limits": tested["limits"], "measured": tested["measured"]},
        "environment": manifest.environment() if environment_found is None else environment_found}
    spec = protocol.record("smoke-spec", "smoke", fields)
    if write:
        root.mkdir(parents=True, exist_ok=True)
        write_json(root / SPEC, spec)
    return spec


def plan_of(stages):
    """The spec's plan: ``PLAN``, without SX's entry unless ``stages`` lists SX (Codex review 2026-10-23 #2)."""
    return {stage: plan for stage, plan in PLAN.items() if stage != "SX" or "SX" in stages}


def load(path):
    """The verified smoke specification at ``path``."""
    return protocol.verified(read_json(path), "smoke-spec")


def solver_of(spec):
    """The smoke's solver (registrar addendum 2026-10-23 02:3x, "smoke solver chain") from a verified specification:
    ``chain`` (the solver block's; "D" when it names none, as every chain D spec), ``model`` (``protocol.CHAINS``) and
    ``echo``, the model ids a confirmed reply may carry (``chain.FIRST_CALL_ECHO``: chain D the registered elucid set,
    chain G glm-5.3). The spec's solver block must say the same, and a chain-G spec never lists S1."""
    block = spec["solver"]
    name = block.get("chain", "D")
    require(name in protocol.SMOKE_SOLVER_CHAINS and block["model"] == protocol.CHAINS[name]
            and block["response_model_ids"] == sorted(FIRST_CALL_ECHO[name])
            and (name == "D" or not _has_s1(spec)),
            "The smoke's solver is chain D's or chain G's, with its echo set (registrar addendum 2026-10-23 02:3x)")
    return SimpleNamespace(chain=name, model=block["model"], echo=FIRST_CALL_ECHO[name])


def _has_s1(spec):
    """S1 is a stage of this smoke (every chain D smoke; never a chain-G one, registrar addendum 2026-10-23 02:3x)."""
    return "S1" in spec.get("stages", V1_STAGES)


def require_s1(spec):
    """S1 runs only in a smoke that lists it: chain D's (``NO_S1``)."""
    require(solver_of(spec).chain == "D" and _has_s1(spec), NO_S1)


def record(spec, stage, result, *, evidence=manifest.SMOKE_EVIDENCE):
    """Stage ``stage``'s judged result, write-once at ``<root>/stages/<stage>.json``; ``evidence``: "smoke", or
    ``REHEARSAL_EVIDENCE`` for what a zero-call rehearsal measured."""
    require(stage in STAGES and isinstance(result, dict) and type(result.get("passed")) is bool,
            "A judged result of a registered stage")
    require(evidence in (manifest.SMOKE_EVIDENCE, REHEARSAL_EVIDENCE), "A smoke stage is smoke evidence or a rehearsal")
    require(stage != "S1" or _has_s1(spec), NO_S1)  # registrar addendum 2026-10-23 02:3x
    value = protocol.record("smoke-stage", evidence, {"stage": stage, "spec": spec[protocol.RECORD_HASH],
                                                      "result": result})
    write_json(safe_path(spec["root"]) / STAGES_DIR / (stage + ".json"), value)
    return value


def _evidence_of(spec, stages):
    """``REHEARSAL_EVIDENCE`` when any recorded stage of ``stages`` is a rehearsal's, else "smoke"."""
    folder = safe_path(spec["root"]) / STAGES_DIR
    found = [protocol.verified(read_json(folder / (stage + ".json")), "smoke-stage") for stage in stages
             if (folder / (stage + ".json")).exists()]
    return REHEARSAL_EVIDENCE if any(v["evidence"] == REHEARSAL_EVIDENCE for v in found) else manifest.SMOKE_EVIDENCE


def rehearsal_roots(spec, *, probe=False):
    """A zero-call rehearsal never writes the registered smoke root (nor, ``probe``, the registered probe root), so its
    records can never stand in for the smoke's (registrar addendum 2026-10-22 15:0x)."""
    require(safe_path(spec["root"]) != safe_path(historical_protocol.SMOKE_ROOT)
            and not (probe and safe_path(spec["probe_root"]) == safe_path(historical_protocol.PROBE_ROOT)),
            "A rehearsal never runs on the registered smoke or probe root (registrar addendum 15:0x)")


def _rows(rows, names):
    require(isinstance(rows, dict) and set(rows) == set(names), "Exactly the registered rows: %s" % (names,))
    return {name: bool(rows[name]) for name in names}


def s0(checks):
    """§10 S0: ``checks`` = {row: passed} for every row of ``S0_ROWS``."""
    rows = _rows(checks, S0_ROWS)
    return {"rows": rows, "passed": all(rows.values())}


def _leak(receipt):
    return receipt.get("subtype") == client.REASONING_MISMATCH


def s1_probe(probes):
    """§10 S1 rows a-f. ``probes``: {"a": receipt, "b": {M: [receipts]}, "c": receipt, "d": [receipts], "e": receipt,
    "f": {"gateway", "trust_env", "first_confirmed"}}; a receipt holds ``ok``, ``model``, ``usage`` (prompt and
    completion tokens), ``request_bytes``, ``seconds`` and ``subtype``."""
    require(isinstance(probes, dict) and set(probes) == set(S1_ROWS), "Probes a-f")
    a, b, c, d, e, f = (probes[name] for name in S1_ROWS)
    usage_ok = _count(a, "prompt_tokens") is not None and _count(a, "completion_tokens") is not None
    lengths = {int(m): [_count(r, "completion_tokens") for r in found] for m, found in b.items()}
    require(sorted(lengths) == sorted(protocol.S1B_TOKENS)
            and all(len(v) == protocol.S1B_REPEATS for v in lengths.values()), "S1-b: ten requests per M")
    counted = [n for found in lengths.values() for n in found if n is not None]
    measured = len(counted) == len(protocol.S1B_TOKENS) * protocol.S1B_REPEATS  # every S1-b reply reports its length
    enforced = measured and all(n <= m for m, found in lengths.items() for n in found)
    longest = max(counted) if counted else None
    every = [a, *[r for found in b.values() for r in found], c, *d]
    overheads = [_count(r, "prompt_tokens") - r["request_bytes"] for r in every
                 if _count(r, "prompt_tokens") is not None]
    overhead = max(overheads) if overheads else None
    rows = {"a": a.get("ok") is True and a.get("model") in client.ELUCID_RESPONSE_MODEL_IDS and usage_ok,
            "b": measured,
            "c": c.get("ok") is True and c["seconds"] <= protocol.read_timeout(protocol.CHAINS["D"], "spreadsheetbench"),
            "d": len(d) == protocol.S1_CONCURRENCY and all(r.get("ok") is True for r in d),
            "e": _leak(e),
            "f": f == {"gateway": protocol.GATEWAY, "trust_env": False, "first_confirmed": True}}
    leaks = sum(_leak(r) for r in every)
    passed = all(rows.values()) and overhead is not None and overhead <= protocol.PROMPT_OVERHEAD_MAX and leaks == 0
    branch = None if not measured else ("E" if enforced else "N")
    return {"rows": rows, "branch": branch, "longest": longest if branch == "N" else None,
            "prompt_overhead_max": overhead, "probe_leaks": leaks, "passed": passed}


def _count(receipt, key):
    """A usage count of a probe receipt, or None when the receipt reports none."""
    usage = receipt.get("usage")
    return usage[key] if isinstance(usage, dict) and type(usage.get(key)) is int else None


def format_check(compliant):
    """The format floor and margin (coevo5 smoke.py:73-77, §10 S2): ``compliant`` = {bench: {arm: [bool per cell]}};
    every arm's share ≥ 9/10 and X, P at most 1/20 below C."""
    shares, failing = {}, []
    for bench, arms in sorted(compliant.items()):
        require(set(ARMS) <= set(arms), "Arms C, X and P on every bench")
        for arm, cells in sorted(arms.items()):
            require(cells and all(type(c) is bool for c in cells), "One verdict per cell")
            share = Fraction(sum(cells), len(cells))
            shares.setdefault(bench, {})[arm] = _fraction(share)
            if share < protocol.SMOKE_FORMAT_FLOOR:
                failing.append({"bench": bench, "arm": arm, "share": _fraction(share), "criterion": "floor"})
        card = Fraction(shares[bench]["C"])
        for arm in COMPARED:
            if Fraction(shares[bench][arm]) < card - protocol.SMOKE_FORMAT_MARGIN:
                failing.append({"bench": bench, "arm": arm, "share": shares[bench][arm], "criterion": "below_card"})
    return {"shares": shares, "failing": failing, "passed": not failing}


def receipt_class(entry, spec, *, ledger_bound):
    """The class of one dispatched receipt (Codex F19). ``entry``: {"stage", "probe" (S1 row or None), "cell",
    "bench", "body", "M", "B", "resend"}; ``ledger_bound``: {bench: the registered B}."""
    if entry.get("probe") == "e" or entry["cell"] in spec["control_cells"]:
        return CONTROL
    if entry["stage"] == "S1":
        return PROBE
    if entry.get("resend"):
        return RESEND
    registered = (entry["body"] == REGISTERED_BODY and entry["M"] == spec["solver"]["M"][entry["bench"]]
                  and entry["B"] == ledger_bound[entry["bench"]])
    return PRODUCTION if entry["stage"] in PRODUCTION_STAGES and registered else UNREGISTERED


def receipt_classes(entries, spec, *, ledger_bound):
    """The receipt criterion (Codex F19, T-SMOKE-1): counts and leaks per class; passes with ≥ 300 production
    receipts, zero leaks in production, probe and resend receipts, no unregistered receipt, and S1-e present and
    judged ``reasoning_mismatch`` when S1 is a stage of the spec (a chain-G smoke has no S1: no S1-e entry at all,
    registrar addendum 2026-10-23 02:3x). An entry stamped at dispatch (``classed_sends``) whose stamp differs from
    this verdict is unregistered."""
    counts = {name: 0 for name in (CONTROL, PROBE, PRODUCTION, RESEND, UNREGISTERED)}
    leaks, control, s1e = dict(counts), [], []
    for entry in entries:
        kind = receipt_class(entry, spec, ledger_bound=ledger_bound)
        if entry.get("class", kind) != kind:
            kind = UNREGISTERED
        counts[kind] += 1
        leaks[kind] += _leak(entry["receipt"])
        if kind == CONTROL:
            control.append(entry["cell"])
        if entry.get("probe") == "e":
            s1e.append(_leak(entry["receipt"]))
    s1e_wanted = [True] if _has_s1(spec) else []  # registrar addendum 2026-10-23 02:3x: a chain-G smoke has no S1-e
    passed = (counts[PRODUCTION] >= spec["min_production_receipts"] and counts[UNREGISTERED] == 0
              and not any(leaks[k] for k in (PRODUCTION, PROBE, RESEND)) and s1e == s1e_wanted)
    return {"counts": counts, "leaks": leaks, "control_cells": sorted(set(control)), "s1e_mismatch": s1e,
            "passed": passed}


def classed_sends(spec, sends, *, stage, cell, bench, body, nominal, ledger_bound):
    """Receipt-class entries of one dispatched cell (Codex F19), stamped at dispatch: ``sends`` are its recorders'
    sends in order (the frozen ``Recorder.sends``: ``max_tokens`` is the Endpoint's ledger bound B); ``body``
    ``REGISTERED_BODY`` for the registered client; ``nominal`` the M its client sends. A send that repeats the
    previous send's request after an undelivered receipt is a frozen-path resend. Entries hold the receipt's error
    type and subtype only (no reply text)."""
    require(stage in PRODUCTION_STAGES and bench in protocol.BENCHES and type(cell) is str and cell,
            "A cell of a production stage")
    out, previous = [], None
    for send in sends:
        receipt = send.get("receipt") if isinstance(send.get("receipt"), dict) else {}
        resend = (previous is not None and previous["request_sha256"] == send["request_sha256"]
                  and undelivered(previous.get("receipt")))
        entry = {"stage": stage, "probe": None, "cell": cell, "bench": bench, "body": body, "M": nominal,
                 "B": send["max_tokens"], "resend": resend,
                 "receipt": {"ok": receipt.get("ok"), "error_type": receipt.get("error_type"),
                             "subtype": receipt.get("subtype")}}
        out.append({**entry, "class": receipt_class(entry, spec, ledger_bound=ledger_bound)})
        previous = send
    return out


def s2_solver(spec, *, compliant, entries, ledger_bound, hooks_fired, ledger, leftover):
    """§10 S2: the format check, the receipt classes, every hook fired at least once (``hooks_fired`` = {hook: n}),
    reservations equal settlements (``ledger`` = {"reserved", "settled"} token totals) and no leftovers
    (``leftover`` = ``prelaunch.leftovers()["verdict"]``; "cannot_judge" is recorded, owner #3)."""
    formats = format_check(compliant)
    receipts = receipt_classes(entries, spec, ledger_bound=ledger_bound)
    rows = {"format": formats["passed"], "receipts": receipts["passed"],
            "hooks": set(hooks_fired) == set(protocol.HOOKS) and all(n >= 1 for n in hooks_fired.values()),
            "ledger": ledger["reserved"] == ledger["settled"],
            "leftovers": leftover in ("clean", "cannot_judge")}
    return {"rows": rows, "format": formats, "receipts": receipts, "leftover": leftover, "passed": all(rows.values())}


def sn1_noise(spec, pairs):
    """§10 S-N1: ``pairs`` = {bench: [(score of run 1, score of run 2)] per item} of two identical card arms. Per
    bench: the discordant share, the SD of the paired difference and its ratio to the registered anchor; above
    ``NOISE_REREGISTER`` the MDE and sizes are re-registered before the pilot (§3.3)."""
    out, anchor = {}, spec.get("noise_anchor")
    for bench, found in sorted(pairs.items()):
        require(bench in PLAN["SN1"] and (anchor is None or bench in anchor) and len(found) >= 2,
                "Paired scores of an S-N1 bench")
        d = [x - y for x, y in found]
        mean = sum(d) / len(d)
        sd = math.sqrt(sum((v - mean) ** 2 for v in d) / (len(d) - 1))
        ratio = None if anchor is None else sd / anchor[bench]  # no anchor (S-N1 not a stage): measured, not judged
        out[bench] = {"items": len(d), "discordant": sum(v != 0 for v in d), "sd": sd, "ratio": ratio,
                      "reregister": None if ratio is None else ratio > protocol.NOISE_REREGISTER}
    return {"benches": out, "reregister": any(v["reregister"] is True for v in out.values()),
            "anchored": anchor is not None, "passed": True}


def se6_cost(scopes, *, ratio):
    """§10 S-E6 (§9.3): ``scopes`` = {scope: {"per_cell", "cells", "reservation", "cap"}} with the measured tokens per
    cell, the maximum-schedule cell count, one full next reservation and the cap; ``ratio`` the measured
    ledger/actual ratio. A scope fits when per_cell x ratio x cells + reservation ≤ cap; ratio ≤ 1.5."""
    rows = {}
    for scope, row in sorted(scopes.items()):
        need = math.ceil(row["per_cell"] * ratio * row["cells"] + row["reservation"])
        rows[scope] = {"needed": need, "cap": row["cap"], "fits": need <= row["cap"]}
    ratio_ok = ratio <= protocol.CAP_FACTOR
    return {"rows": rows, "ratio": ratio, "ratio_ok": ratio_ok,
            "passed": ratio_ok and all(v["fits"] for v in rows.values())}


def s3_roles(ran):
    """§10 S3: each registered role call ran end to end (``ran`` = {row: bool}); its result need not pass."""
    rows = _rows(ran, S3_ROWS)
    return {"rows": rows, "passed": all(rows.values())}


def s4_ministep(ran):
    """§10 S4: the mini-step's unit, consumption registry, sealing and the drilled redo worked (``ran`` = {row:
    bool}); its result is only ``smoke``."""
    rows = _rows(ran, S4_ROWS)
    return {"rows": rows, "passed": all(rows.values())}


def summary(spec):
    """``smoke-result.json`` (zero calls): pass/fail per stage and per registered row of every recorded stage. The
    smoke passes when every stage of the spec's ``stages`` (``SMOKE_STAGES`` by default; a spec without the list: all
    of ``V1_STAGES``) is recorded and passed, else it fails; any fail means no pilot (§10 exit). A stage outside the
    list is ``not_required`` until it is recorded and never gates (registrar addendum 13:0x: S-N1 and S4 may still
    run); SX is reported only by a spec that lists it (Codex review 2026-10-23 #2).
    Written once, when every listed stage is recorded; from then on the written result is returned. Its evidence is
    ``REHEARSAL_EVIDENCE`` when any recorded stage is a rehearsal's (registrar addendum 15:0x), else "smoke"."""
    root = safe_path(spec["root"])
    if (root / RESULT).exists():
        value = protocol.verified(read_json(root / RESULT), "smoke-result")
        require(value["spec"] == spec[protocol.RECORD_HASH], "The result of another smoke")
        return value
    required = tuple(spec.get("stages", V1_STAGES))
    reported = V1_STAGES + (("SX",) if "SX" in required else ())
    found, rows = {}, {}
    for stage in reported:
        path = root / STAGES_DIR / (stage + ".json")
        value = protocol.verified(read_json(path), "smoke-stage") if path.exists() else None
        require(value is None or value["spec"] == spec[protocol.RECORD_HASH], "A stage of another smoke")
        if value is None:
            found[stage] = "missing" if stage in required else "not_required"
        else:
            found[stage] = "pass" if value["result"]["passed"] else "fail"
            rows[stage] = {row: "pass" if ok else "fail" for row, ok in sorted(value["result"]["rows"].items())}
    result = protocol.record("smoke-result", _evidence_of(spec, reported), {  # a rehearsal's stage: a fixture result
        "spec": spec[protocol.RECORD_HASH], "stages": found, "required": list(required), "rows": rows,
        "passed": all(found[stage] == "pass" for stage in required)})
    if all(found[stage] != "missing" for stage in required):  # a smoke still running is reported, not sealed
        write_json(root / RESULT, result)
    return result


# ------------------------------------------------- the owner's smoke waiver (registrar addendum 2026-10-23 05:3x)
WAIVER_KEYS = frozenset({"decision", "smoke_result", "rows", "note"})


def _waiver_pairs(pairs):
    require(len({key for key, _ in pairs}) == len(pairs), "The owner's smoke waiver repeats a key")
    return dict(pairs)


def waiver(root, result):
    """Registrar addendum 2026-10-23 05:3x (zero calls, writes nothing): the owner's smoke waiver of ``result``, the
    sealed ``smoke-result`` of the smoke at ``root``: ``<root>/shared/owner-smoke-waiver.json``
    (``protocol.SMOKE_WAIVER``; for a smoke that requires v2's example SX ``protocol.SMOKE_WAIVER_V2``,
    ``waiver_name``), which only the owner writes. None when the file is absent; else -- fail closed, any
    violation raises -- {"sha256": the sha256 of the file's bytes, "rows": the waived rows}. The file holds exactly
    ``decision`` ("waive"), ``smoke_result`` (``result``'s record hash), ``rows`` (a sorted, unique, non-empty list
    of "STAGE.row" within ``protocol.WAIVABLE_SMOKE_ROWS`` and exactly the failing rows of the result's required
    stages) and a non-empty ``note``; no required stage is missing, every failing required stage fails on waived
    rows only, and S-E6 is required and passed. A waiver beside a passed result is refused (a passed smoke needs
    none). The whole waiver path is checked before anything is read (Codex G2, registrar G2b): a symlink in it or in
    its parents, dangling or not, is refused, never read and never taken as absent; the waiver is a regular file."""
    result = protocol.verified(result, "smoke-result")
    name = waiver_name(result)
    path = safe_path(safe_path(root) / name)  # G2b: no symlink in the waiver path or its parents
    if not os.path.lexists(path):
        return None
    require(path.is_file(), "The owner's smoke waiver is a regular file")
    require(result["passed"] is not True, "A passed smoke needs no waiver: %s beside a passed smoke-result is refused"
            % name)
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_waiver_pairs)
    require(isinstance(value, dict) and set(value) == WAIVER_KEYS,
            "The owner's smoke waiver holds exactly decision, smoke_result, rows and note")
    require(value["decision"] == "waive" and type(value["note"]) is str and value["note"].strip() != "",
            "The owner's smoke waiver decides \"waive\" and gives a non-empty note")
    require(value["smoke_result"] == result[protocol.RECORD_HASH], "The owner's smoke waiver names another "
            "smoke-result")
    rows = value["rows"]
    require(isinstance(rows, list) and rows != [] and all(type(row) is str for row in rows)
            and rows == sorted(set(rows)) and all(row.partition(".")[0] in STAGES and row.partition(".")[2]
                                                  for row in rows),
            "The waived rows are a sorted, unique, non-empty list of \"STAGE.row\"")
    require(set(rows) <= protocol.WAIVABLE_SMOKE_ROWS, "Only %s may be waived (registrar addendum 2026-10-23 05:3x)"
            % ", ".join(sorted(protocol.WAIVABLE_SMOKE_ROWS)))
    required, stages = result["required"], result["stages"]
    require("SE6" in required and stages.get("SE6") == "pass", "A waived smoke's S-E6 is required and passed")
    require(all(stages.get(stage) in ("pass", "fail") for stage in required), "A waived smoke has no missing stage")
    verdicts = {stage: result["rows"].get(stage, {}) for stage in required}
    require(all(verdict in ("pass", "fail") for found in verdicts.values() for verdict in found.values()),
            "Every row of a waived smoke passed or failed")
    failing = sorted("%s.%s" % (stage, row) for stage, found in verdicts.items()
                     for row, verdict in found.items() if verdict == "fail")
    require(rows == failing, "The waived rows are exactly the failing rows of the required stages (%s)"
            % ", ".join(failing))
    require(all(any(row.partition(".")[0] == stage for row in rows) for stage in required if stages[stage] == "fail"),
            "Every failing required stage of a waived smoke fails on a waived row")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "rows": list(rows)}


def waiver_name(result):
    """The owner's waiver file of a smoke result: ``protocol.SMOKE_WAIVER``; for a smoke that requires v2's example SX
    ``protocol.SMOKE_WAIVER_V2`` (a v2 smoke reuses the registered smoke root, where the earlier smoke's waiver
    stays)."""
    return protocol.SMOKE_WAIVER_V2 if "SX" in result["required"] else protocol.SMOKE_WAIVER


# ------------------------------------------------------------------------------- S0: the sandbox self-test
def escape_argv(runner, *, name, docker="docker", limits=None):
    """The registered cell argv (``sandbox.client.docker_command``) with ``/runner/escape_probe.py`` in place of
    ``/runner/worker.py``; no input mount."""
    argv = sandbox.docker_command("cell", limits, {"runner": str(runner), "input": None}, name=name, docker=docker)
    require(argv[-1] == "/runner/worker.py", "The registered argv ends with the worker")
    return argv[:-1] + ["/runner/escape_probe.py"]


def escape_rows(report):
    """The S0 escape-probe row (§10) from the probe's report: {row: bool} over ``ESCAPE_ROWS``."""
    net, writes, status, child = report["network"], report["writes"], report["status"], report["worker_child"]
    caps = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    names = [Path(path).name.lower() for path in report["secret_names"]]
    limits = child["limits"]
    return {
        "network": all(net[key] not in UNSENT for key in net if key != "interfaces") and net["interfaces"] == ["lo"],
        "read_only": all(writes[where] != "writable" and not writes[where].startswith("created")
                         for where in ("/", "/runner", "/input", "/etc", "/usr"))
        and writes["/tmp"] == "writable" and report["tmp"]["exec"].startswith("refused"),
        "identity": report["identity"]["uid"] == report["identity"]["gid"] == 65534
        and all(int(status[cap], 16) == 0 for cap in caps) and status["NoNewPrivs"] == "1" and status["Seccomp"] == "2",
        "env_keys": tuple(report["env_keys"]) == REGISTERED_ENV_KEYS and report["env"] == REGISTERED_ENV,
        "no_secrets": not any(fnmatch.fnmatch(name, pattern) for name in names for pattern in SECRET_NAMES)
        and not any(report["host_paths"].values()) and report["root_listable"] is not True,
        "limits": report["pids"]["stopped_by"] == "EAGAIN" and report["pids"]["forked"] < sandbox.CELL_LIMITS.pids
        and report["memory"] == "killed_by_signal_9",
        "worker_child": child["write_file"]["ok"] is False and child["connect"]["ok"] is False
        and child["allocate"]["ok"] is False and child["oom_score_adj"].get("value") == "1000"
        and limits.get("value", {}).get("RLIMIT_FSIZE") == [0, 0]
        and child["standard_streams"].get("value") == ["/dev/null"] * 3,
        "python_flags": report["python"]["safe_path"] is True and report["python"]["no_user_site"] == 1
        and report["python"]["dont_write_bytecode"] == 1}


def _escape_report(docker, scratch):
    """Run the escape probe once (forced removal of its exact container name afterwards); its parsed report."""
    if docker.binary is None:
        raise SandboxUnavailable("sandbox_unavailable: docker not found on %s" % sandbox.DOCKER_ENV["PATH"])
    runner = Path(scratch) / ("execskill-escape-" + uuid.uuid4().hex)
    runner.mkdir()
    for source in (sandbox.WORKER_FILE, sandbox.POLICY_FILE, ESCAPE_PROBE):
        (runner / source.name).write_bytes(source.read_bytes())
        (runner / source.name).chmod(0o444)
    runner.chmod(0o755)
    name = sandbox.PREFIX + uuid.uuid4().hex
    try:
        done = docker.run(escape_argv(runner, name=name, docker=docker.binary), ESCAPE_SECONDS)
    finally:
        sandbox.cleanup(name, docker=docker)
        for path in runner.iterdir():
            path.chmod(0o644)
            path.unlink()
        runner.rmdir()
    if done.code != 0:
        raise SandboxUnavailable("sandbox_unavailable: the escape probe exited with %s" % done.code)
    return json.loads(done.stdout.decode("utf-8"))


def _p99(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.99 * len(ordered)) - 1)]


def view_bytes(item_files):
    """{"items", "p99"}: the canonical JSON size of every given item's public view (workbook files counted by their
    size on disk, ``public.input_files``)."""
    sizes = []
    for path in item_files:
        for item in read_json(path):
            size = len(json.dumps(item["public"], sort_keys=True, ensure_ascii=False).encode("utf-8"))
            size += sum(safe_path(name).stat().st_size for name in item["public"].get("input_files") or [])
            sizes.append(size)
    require(sizes, "The measured views come from item files")
    return {"items": len(sizes), "p99": _p99(sizes)}


def sandbox_selftest(out, *, item_files, docker=None, worker=None, scratch="/tmp", clock=time.monotonic):
    """The S0 sandbox self-test (§2.6, §10 S0), zero model calls: the escape probe in the real container (judged by
    ``escape_rows``), one ping of an empty-package worker (VSZ/RSS and the container start latency) and the p99
    public-view size of ``item_files``; the sealed record ``<out>/sandbox-selftest.json`` (write-once) with the start
    limits it measured under. ``docker``: a ``sandbox.client.Docker`` (a fake in tests); ``worker``: a callable
    returning an unstarted worker (default ``sandbox.client.Worker``)."""
    out = safe_path(out)
    require(not (out / SELFTEST).exists(), "A self-test is written once")
    docker = docker or sandbox.Docker()
    rows = escape_rows(_escape_report(docker, scratch))
    empty = SimpleNamespace(sha256=digest([]), procedures=())
    started = clock()
    pinged = (worker or sandbox.Worker)().start(empty, kind="cell")
    try:
        ping = pinged.ping()
    finally:
        pinged.close()
    latency = round(clock() - started, 3)
    views = view_bytes(item_files)
    measured = {"vsz_kib": ping["vsz_kib"], "rss_kib": ping["rss_kib"], "view_bytes_p99": views["p99"],
                "start_seconds": latency, "views": views["items"]}
    value = protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": rows, "escape_probe_sha256": manifest._sha(ESCAPE_PROBE),
        "worker_sha256": sandbox.worker_sha256(),
        "image": sandbox.IMAGE, "limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
        "measured": measured, "passed": all(rows.values())})
    write_json(out / SELFTEST, value)
    return value


# ------------------------------------------------------------------------------------------- S1: the probe
class ControlClient(client.ElucidClient):
    """S1-e (§10): the registered elucid client with ``reasoning_effort`` left out of the body -- a CONTROL probe whose
    reply must be judged ``reasoning_mismatch`` (the detection path works); its receipt is never a production one."""

    def body(self, system, user):
        body = super().body(system, user)
        del body["reasoning_effort"]
        return body


def _summary(row, n, send, *, nominal, body):
    """What the probe keeps of one send: counts and classes, never the reply text."""
    receipt = send.get("receipt") if isinstance(send.get("receipt"), dict) else {}
    kept = {key: receipt.get(key) for key in PROBE_FIELDS}
    return {"row": row, "n": n, "M": nominal, "B": send["max_tokens"], "body": body,
            "request_bytes": send["request_bytes"], **kept}


def _judged(sent):
    """The receipts ``s1_probe`` reads, from the kept summaries."""
    def shaped(entry):
        return {"ok": entry["ok"], "model": entry["returned_model"], "usage": entry["usage"] or {},
                "request_bytes": entry["request_bytes"], "seconds": entry["seconds"], "subtype": entry["subtype"]}

    rows = {row: [shaped(e) for e in sent if e["row"] == row] for row in ("a", "b", "c", "d", "e")}
    b = {m: [shaped(e) for e in sent if e["row"] == "b" and e["M"] == m] for m in protocol.S1B_TOKENS}
    return {"a": rows["a"][0], "b": b, "c": rows["c"][0], "d": rows["d"], "e": rows["e"][0]}


def entries_of(probe):
    """The S1 receipt-class entries of a judged probe attempt (S2 ``receipt_classes`` reads them with the others)."""
    return [{"stage": "S1", "probe": e["row"], "cell": "S1/%s/%d" % (e["row"], e["n"]), "bench": "searchqa",
             "body": e["body"], "M": e["M"], "B": e["B"], "resend": False,
             "receipt": {"ok": e["ok"], "error_type": e["error_type"], "subtype": e["subtype"]}}
            for e in probe["sent"]]


def _attempts(probe_root):
    folder = probe_root / "attempts"
    return sorted(folder.glob("attempt-*.json")) if folder.is_dir() else []


def run_probe(spec, *, env_path, probe_root=None, slot_root=protocol.SLOT_ROOT, transport=None,
              evidence=manifest.SMOKE_EVIDENCE):
    """§10 S1 on the probe's own ledger (``<probe_root>/ledger``, cap 0.5M), at most ``S1_MAX_CALLS`` sends over all
    attempts. Each attempt is kept write-once at ``<probe_root>/attempts/attempt-<n>.json``; a complete one is judged
    (``s1_probe``) and recorded as stage S1. ``probe_root``: the spec's (``make``), where S2 reads the probe's receipts
    (default; another root is refused). ``env_path``: the elucid credential file (read by path only); ``transport``:
    an ``httpx`` mock transport in tests and the rehearsal; ``evidence``: "smoke", or ``REHEARSAL_EVIDENCE`` for
    ``probe --fake`` (registrar addendum 15:0x: the attempt and its S1 record are labelled a rehearsal's). Returns the
    attempt record. A chain-G smoke has no S1: refused (``NO_S1``, registrar addendum 2026-10-23 02:3x)."""
    require_s1(spec)
    probe_root = safe_path(spec["probe_root"] if probe_root is None else probe_root)
    require(probe_root != safe_path(spec["root"]) and not probe_root.is_relative_to(safe_path(spec["root"])),
            "The S1 probe has its own ledger root, apart from the smoke's")
    require(probe_root == safe_path(spec["probe_root"]), "The S1 probe runs on the spec's probe root, where S2 reads "
            "its receipts")
    require(evidence in (manifest.SMOKE_EVIDENCE, REHEARSAL_EVIDENCE), "Smoke evidence or a rehearsal")
    previous = [protocol.verified(read_json(path), "smoke-probe") for path in _attempts(probe_root)]
    require(not any(p["complete"] for p in previous), "S1 was already probed to the end")
    spent = sum(len(p["sent"]) for p in previous)
    require(spent + PROBE_CALLS <= protocol.S1_MAX_CALLS, "The S1 probe would exceed %d calls" % protocol.S1_MAX_CALLS)
    ledger = Budget(probe_root / "ledger")
    ledger.declare(budgets.probe_caps())
    model = protocol.CHAINS["D"]  # S1 is chain D's elucid probe (NO_S1)
    slots = Slots(safe_path(slot_root), model, protocol.SLOTS[model])
    made, sent, lock = [], [], threading.Lock()

    def send(row, n, nominal, bound, kind=client.ElucidClient, prompt=PROBE_SHORT):
        solver = kind(env_path, proxy=protocol.GATEWAY, max_tokens=nominal,
                      read_timeout=protocol.read_timeout(model, "spreadsheetbench"), transport=transport)
        made.append(solver)
        endpoint = Endpoint(solver, model=model, max_tokens=bound, slots=slots, budget=ledger,
                            scopes=(budgets.ROOT, PROBE_SCOPE), cooldown=RESEND_COOLDOWN_SECONDS)
        recorder = endpoint.recorder(label="smoke/S1/%s/%d" % (row, n))
        body = CONTROL_BODY if kind is ControlClient else REGISTERED_BODY
        try:
            endpoint.send(PROBE_SYSTEM, prompt, recorder)
        finally:
            kept = [_summary(row, n, s, nominal=nominal, body=body) for s in recorder.sends]
            with lock:
                sent.extend(kept)
        return kept[-1]

    stopped = None
    try:
        first = send("a", 0, protocol.S1D_TOKENS, protocol.B_PROBE)
        confirmed = first["ok"] is True and first["returned_model"] in client.ELUCID_RESPONSE_MODEL_IDS
        if not confirmed:
            stopped = "first_call_not_confirmed"
        else:
            for m in protocol.S1B_TOKENS:
                for n in range(protocol.S1B_REPEATS):
                    send("b", n, m, protocol.B_PROBE, prompt=PROBE_LONG)
            send("c", 0, protocol.S1C_TOKENS, protocol.B_PROBE, prompt=PROBE_LONG)
            with ThreadPoolExecutor(max_workers=protocol.S1_CONCURRENCY) as pool:
                list(pool.map(lambda n: send("d", n, protocol.S1D_TOKENS, protocol.S1D_TOKENS),
                              range(protocol.S1_CONCURRENCY)))
            send("e", 0, protocol.S1D_TOKENS, protocol.B_PROBE, kind=ControlClient)
    except (BudgetStop, AssumptionBroken, LedgerFailure) as stop:
        stopped = "ledger_stop:" + type(stop).__name__
    finally:
        for solver in made:
            solver.http.close()
    gateway = {"gateway": protocol.GATEWAY, "trust_env": any(s.http.trust_env for s in made),
               "first_confirmed": stopped != "first_call_not_confirmed" and bool(sent)}
    sent.sort(key=lambda e: ("abcde".index(e["row"]), e["M"], e["n"]))
    complete = stopped is None
    judged = s1_probe({**_judged(sent), "f": gateway}) if complete else None
    value = protocol.record("smoke-probe", evidence, {
        "spec": spec[protocol.RECORD_HASH], "attempt": len(previous) + 1, "complete": complete, "stopped": stopped,
        "sent": sent, "calls_before": spent, "gateway": gateway, "result": judged})
    write_json(probe_root / "attempts" / ("attempt-%d.json" % (len(previous) + 1)), value)
    if complete:
        record(spec, "S1", judged, evidence=evidence)
    return value


# ------------------------------------------------------------------------------------------ S4: the drill
class FaultSwitch:
    """S4 (§10): the registered ``SandboxUnavailable`` drill. Available only for a unit under the smoke root of a
    verified smoke specification; the ``fail_at``-th sandbox call made through its workers raises
    ``SandboxUnavailable`` (P4: the unit pauses, the operator writes the owner-format ``recovery.json`` labelled
    ``smoke`` and the block is redone with the same sealed inputs)."""

    def __init__(self, spec, unit_root, *, fail_at):
        spec = protocol.verified(spec, "smoke-spec")
        require(safe_path(unit_root).is_relative_to(safe_path(spec["root"])),
                "The S4 fault switch exists only under the smoke root")
        require(type(fail_at) is int and fail_at >= 1, "The drill fails one numbered call")
        self.fail_at, self.calls, self.fired = fail_at, 0, False
        self._lock = threading.Lock()

    def tick(self):
        """Count one sandbox call; the registered one raises."""
        with self._lock:
            self.calls += 1
            if self.calls == self.fail_at:
                self.fired = True
                raise SandboxUnavailable("sandbox_unavailable: the registered S4 drill (smoke root only)")

    def worker(self, **options):
        """An unstarted ``sandbox.client.Worker`` whose calls pass through the switch."""
        return _DrilledWorker(self, **options)


class _DrilledWorker(sandbox.Worker):
    def __init__(self, switch, **options):
        super().__init__(**options)
        self.switch = switch

    def call(self, proc_id, fn, args, *, timeout_s):
        self.switch.tick()
        return super().call(proc_id, fn, args, timeout_s=timeout_s)


# --------------------------------------------------------------------------- the stage runs: S2 and S-N1 (§10)
BUILT_STAGES = ("S2", "SN1", "SE6", "S3", "S4", "SX")  # run_stage (S3: smoke_roles.run, notes/C7d.md; ticket C7d-1)
UNITS_DIR = "units"  # <root>/units/<stage>/<set>: one copied unit per stage and item set
CONFIRM_ARM = "C_confirm"  # the single production cell whose confirmed reply precedes any concurrency (plan §10 step 4)
DUP_ARM = "C_dup"  # S-N1: the second, identical card arm
TWIN_SETS = ("searchqa", "officeqa", "livemath", "spreadsheetbench")  # §10 S2: no twins on ALFWorld


def _slice(stage, name, items):
    """The stage's items of one set (§10): SearchQA's and ALFWorld's smoke items are cut in stage order S2, S-N1, S4
    (``protocol.SMOKE_REAL_ITEMS``: 20 / 200 / 60 and 6 / 6, disjoint); the 20 fixtures of each other set are S2's."""
    sizes = protocol.SMOKE_REAL_ITEMS.get(name)
    require(name != "zebralogic", "Use the profile-specific zebra smoke recipe")
    if sizes is None:
        require(stage == "S2" and len(items) == protocol.SMOKE_FIXTURES, "S2 runs the 20 fixtures of %s" % name)
        return list(items)
    start = sum(n for other, n in sizes.items() if STAGES.index(other) < STAGES.index(stage))
    require(len(items) >= start + sizes[stage], "The %s smoke items hold the %s slice" % (name, stage))
    return list(items[start:start + sizes[stage]])


class _Watched:
    """A smoke unit's solver client with the native-lock watch (§2.5, §10 S2): a model call made while the calling
    thread holds a spreadsheet-native slot is counted in ``held_native``."""

    def __init__(self, solver_client, holdings):
        self.solver_client, self.holdings, self.held_native = solver_client, holdings, 0
        self._lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.solver_client, name)

    def call(self, system, user):
        if slots.NATIVE in self.holdings.held():
            with self._lock:
                self.held_native += 1
        return self.solver_client.call(system, user)


def _endpoint(spec, setting, bench):
    """(endpoint, watched client) of one smoke unit: the smoke solver's model on ``bench`` (``solver_of``: chain D's,
    or glm-5.3 in a chain-G smoke, registrar addendum 2026-10-23 02:3x) with its registered nominal M, charged to
    ``smoke:solver`` with the ledger bound B (§4.1, §9.3)."""
    model = solver_of(spec).model
    watched = _Watched(setting.clients(model, bench), setting.slots[slots.NATIVE].holdings)
    bound = protocol.ledger_bound(model, bench, branch=setting.branch, longest=setting.longest)
    return budgets.endpoint(setting, budgets.solver_scopes(budgets.SMOKE, None, None, "smoke"), client=watched,
                            max_tokens_bound=bound), watched


def _confirmed(found, echo):
    """The first send of a cell came back as an ok reply of the registered model: an echo in ``echo``, the smoke
    solver's (``solver_of``; registrar addendum 2026-10-23 02:3x)."""
    sends = found["sends"]
    receipt = sends[0].get("receipt") if sends and isinstance(sends[0].get("receipt"), dict) else {}
    return receipt.get("ok") is True and receipt.get("returned_model") in echo


def _usage(found):
    total = 0
    for send in found["sends"]:
        usage = send.get("receipt", {}).get("usage") if isinstance(send.get("receipt"), dict) else None
        if isinstance(usage, dict):
            total += sum(usage.get(key) or 0 for key in ("prompt_tokens", "completion_tokens"))
    return total


def _summary_of(spec, attempt, found, *, stage, bench, nominal, bound):
    """What a stage judges of one cell (counts and classes, never a reply text): the format violation, the v2 token,
    the dispatch-classed receipt entries, the procedure faults, the hook kinds that ran without a fault, the
    ALFWorld step forms, the sandbox restarts and cleanups (ticket C5-4) and the reported tokens."""
    cell, judged = found["cell"], found["judge"]
    path = safe_path(attempt) / trajectories.TRAJECTORIES / (cell["id"] + ".json")
    trajectory = read_json(path) if path.exists() else None
    hooks, steps = set(), None
    if trajectory is not None:
        hooks = {e["fn"] for e in trajectory["shell"]["procedure_calls"] if e.get("fault") is None}
        hooks |= {"applies"} if (trajectory["route"] or {}).get("enabled") else set()
        if trajectory["alfworld_steps"] is not None:
            hows = [s["how"] for s in trajectory["alfworld_steps"]]
            steps = {"steps": len(hows), "wrapped": sum(h.startswith("tag") for h in hows),
                     "level1": sum(h.endswith("_level1") for h in hows)}
    box = found.get("sandbox") or {}
    return {"cell": cell["id"], "arm": cell["arm"], "task_id": cell["task_id"], "run": cell["run"],
            "violation": None if judged is None else judged["format"]["violation"],
            "token": None if judged is None else judged["v2"]["token"],
            "entries": classed_sends(spec, found["sends"], stage=stage, cell=cell["id"], bench=bench,
                                     body=REGISTERED_BODY, nominal=nominal, ledger_bound={bench: bound}),
            "faults": [{"procedure": f.get("procedure"), "kind": f.get("kind")} for f in found["faults"]],
            "hooks": sorted(hooks), "alfworld": steps, "tokens": _usage(found),
            "restarts": len(box.get("restarts") or []),
            "cleanups": [c.get("seconds") for c in box.get("cleanups") or [] if isinstance(c, dict)],
            "stop": found.get("stop")}


def _twins(setting, bench, package, tasks, unit):
    """§6.5 on package X (zero calls): X routed on every item in the sandbox, then a seeded half of each procedure's
    firing items gets its withholding twin (``router.draw_twins``, at most two per item)."""
    firing = {p.id: [] for p in package.for_bench(bench)}
    if not firing:
        return {}
    options = {**setting.sandbox, "live": setting.slots[slots.LIVE], "per_call": setting.slots[slots.CALL]}
    with sandbox.with_worker(package, kind="cell", **options) as worker:
        for item, task in sorted(tasks.items()):
            view = solver.routing_view(bench, task["public"], runtime=setting.runtime.get(bench))
            for procedure_id in router.route(package, bench, view, worker).enabled:
                firing[procedure_id].append(item)
    priority = [p for p in firing if len(firing[p]) >= protocol.TWIN_MIN_FIRED]
    twins, _ = router.draw_twins(firing, priority, {p: "withhold" for p in priority}, unit)
    return twins


def _arms(stage, bench, unit, items, package):
    """(arms, schedule extras) of one unit: S2 C, X, P (+ twins outside ALFWorld), S-N1 C and its duplicate."""
    card = empty(step="smoke/" + stage, evidence=manifest.SMOKE_EVIDENCE)
    if stage == "SN1":
        return {"C": Arm("card", card), DUP_ARM: Arm("dup", card)}
    content = fixtures.fixture_placebo(items, unit=unit, package=package)

    def placebo_arm(cell):
        return Arm("placebo_i", package, placebo=placebos.arm(content, cell["task_id"].partition("/")[2],
                                                              seed=protocol.discourage_tag(unit, cell["id"])))

    return {"C": Arm("card", card), "X": Arm("candidate", package), "P": placebo_arm}


def _unit(spec, setting, stage, name, items, *, first):
    """One stage unit on one item set (``units.run_unit`` under ``<root>/units/<stage>/<set>``): with ``first`` the
    single confirmation cell runs alone before the round and a reply that is not a confirmed one of the registered
    model stops the unit; then one seeded interleaved round (§6.2). Returns the unit's record; raises Pause."""
    bench, unit = name, "smoke/%s/%s" % (stage, name)
    tasks = {rounds.key(bench, item["task_id"]): {"public": item["public"], "private": item["private"]}
             for item in items}
    runs = PLAN[stage][name]["runs"]
    package = fixtures.fixture_package()
    local = units.for_unit(setting, budgets.SMOKE, bench, unit)
    ours = solver_of(spec)

    def work(attempt):
        endpoint, watched = _endpoint(spec, local, bench)
        bound, nominal = endpoint.max_tokens, watched.max_tokens
        done = []
        if first:
            item = sorted(tasks)[0]
            card = Arm("card", empty(step="smoke/" + stage, evidence=manifest.SMOKE_EVIDENCE))
            confirm = rounds.run_round(replace(local, workers=1), attempt, endpoint, unit, {CONFIRM_ARM: card},
                                       {CONFIRM_ARM: [(item, 1)]}, tasks, tag="confirm")
            done += [f for found in confirm.values() for f in found]
            if not _confirmed(done[0], ours.echo):
                raise Pause("first_call_not_confirmed", "the single first reply is not a confirmed %s reply"
                            % ours.model, done[0]["cell"]["id"])
        arms = _arms(stage, bench, unit, items, package)
        schedule = {arm: [(item, runs) for item in sorted(tasks)] for arm in arms}
        if stage == "S2" and name in TWIN_SETS:
            for item, held in sorted(_twins(local, bench, package, tasks, unit).items()):
                for twin in held:
                    label = "withhold:" + twin["procedure"]
                    arms[label] = Arm(label, package, withhold=frozenset({twin["procedure"]}))
                    schedule.setdefault(label, []).append((item, runs))
        cells = rounds.run_round(local, attempt, endpoint, unit, arms, schedule, tasks, tag=stage)
        done += [f for _, found in sorted(cells.items()) for f in found]
        return {"set": name, "bench": bench, "items": len(items), "runs": runs, "held_native": watched.held_native,
                "cells": [_summary_of(spec, attempt, f, stage=stage, bench=bench, nominal=nominal, bound=bound)
                          for f in done]}

    identity = {"unit": unit, "stage": stage, "set": name, "spec": spec[protocol.RECORD_HASH]}
    return units.run_unit(safe_path(spec["root"]) / UNITS_DIR / stage / name, run=setting.run, identity=identity,
                          work=work, evidence=setting.evidence, drain=units.drainer(setting, budgets.SMOKE, unit))


def _compliant(results, arms):
    """{bench: {arm: [format compliant per cell]}} of the units' cells (an unknown cell is not compliant)."""
    out = {}
    for result in results:
        for cell in result["cells"]:
            if cell["arm"] in arms:
                out.setdefault(result["bench"], {}).setdefault(cell["arm"], []).append(cell["violation"] is False)
    return out


def _s2_judged(spec, results, *, ledger_bound, ledger, leftover, probe_entries, concurrent=None):
    """§10 S2 from the units' cell summaries (``s2_solver`` plus the registered extra rows); ``ledger_bound``: {bench:
    the registered B}; ``concurrent``: what of the S3 stage running beside S2 the leftover check listed apart."""
    cells = [c for r in results for c in r["cells"]]
    entries = probe_entries + [e for c in cells for e in c["entries"]]
    hooks = {hook: sum(hook in c["hooks"] for c in cells) for hook in protocol.HOOKS}
    crash = {item for name in fixtures.FX_CRASH_SUBSET for item in fixtures.FX_CRASH_SUBSET[name]}
    faulted = [{"task_id": c["task_id"].partition("/")[2], "procedure": f["procedure"], "kind": f["kind"]}
               for c in cells for f in c["faults"]]
    faults_ok = all(f["procedure"] == "fx-crash" and f["task_id"] in crash for f in faulted)
    steps = [c["alfworld"] for c in cells if c["alfworld"]]
    total = sum(s["steps"] for s in steps)
    judged = s2_solver(spec, compliant=_compliant(results, ARMS), entries=entries, ledger_bound=ledger_bound,
                       hooks_fired=hooks, ledger=ledger, leftover=leftover)
    rows = {**judged["rows"], "faults": faults_ok and not any(c["stop"] for c in cells),
            "native_lock": sum(r["held_native"] for r in results) == 0}
    return {**judged, "rows": rows, "passed": all(rows.values()), "hooks_fired": hooks, "procedure_faults": faulted,
            "ledger": ledger, "concurrent_s3": concurrent,
            "alfworld": {"steps": total, "wrapped_share": total and sum(s["wrapped"] for s in steps) / total,
                         "level1_share": total and sum(s["level1"] for s in steps) / total},
            "sandbox": {"restarts": sum(c["restarts"] for c in cells),
                        "cleanup_seconds_max": max([s for c in cells for s in c["cleanups"] if s is not None],
                                                   default=None)},
            "tokens": {r["bench"] + "/" + arm: sum(c["tokens"] for c in r["cells"] if c["arm"] == arm)
                       for r in results for arm in {c["arm"] for c in r["cells"]}}}


def _sn1_judged(spec, results):
    """§10 S-N1: per bench the paired same-text scores of the two identical card arms (``sn1_noise``)."""
    pairs = {}
    for result in results:
        by_item = {}
        for cell in result["cells"]:
            if cell["arm"] in ("C", DUP_ARM):
                by_item.setdefault(cell["task_id"], {})[cell["arm"]] = int(cell["token"] == "pass")
        pairs[result["bench"]] = [(v["C"], v[DUP_ARM]) for _, v in sorted(by_item.items())]
    judged = sn1_noise(spec, pairs)
    rows = {bench: True for bench in judged["benches"]}
    return {**judged, "rows": rows}


def _ledger_rows(setting):
    """The smoke ledger after a stage: every reservation THIS process made on ``smoke:solver`` settled, no halt. S3
    runs beside S2 in its own process (registrar addendum 14:3x) and its run unit charges the same scope, so another
    process's open reservations are listed (``others_open``), not judged here; S-E6 reads the scope only when nothing
    at all is open. One read under the ledger's lock (frozen budget.py:170-203; each open entry carries its owner's
    pid, host and start, :106)."""
    name, owner = budgets.SMOKE + ":solver", setting.budget.owner
    with setting.budget._state() as (state, _):
        settled = state["settled"].get(name, 0)
        found = [entry for entry in state["open"].values() if name in entry["scopes"]]
        halted = state["halted"]
    mine = sum(entry["amount"] for entry in found if all(entry.get(key) == value for key, value in owner.items()))
    return {"reserved": settled + mine + (1 if halted else 0), "settled": settled,
            "others_open": sum(entry["amount"] for entry in found) - mine}


S3_PROCESS = re.compile(r"(?:^|\s)smoke-run(?:\s.*)?\s--stage(?:=|\s+)S3(?:\s|$)")  # S3's process (14:3x)


def _s3_tags(root):
    """The unit tags (``sandbox.unit_tag``) of S3's units under the smoke root: the roles unit, its own run unit
    (label ``smoke/s1-searchqa/run``) and every confirmation unit it made, or makes next."""
    from . import smoke_roles  # imported here: smoke_roles imports this module

    base = safe_path(root) / UNITS_DIR / smoke_roles.STAGE
    made = len(list(base.glob("confirm-*"))) if base.is_dir() else 0
    labels = [smoke_roles._unit_label(smoke_roles.UNIT_NAME),
              "%s/s%d-%s/run" % (budgets.SMOKE, smoke_roles.K, smoke_roles.BENCH)]
    labels += ["%s/%s/confirm-%d" % (budgets.SMOKE, smoke_roles.STAGE, n) for n in range(1, made + 2)]
    return sorted({sandbox.unit_tag(budgets.SMOKE, label) for label in labels})


def _leftover(docker, *, fake, root=None):
    """The S2 leftover row (``prelaunch.leftovers``; owner #3) -> (verdict, concurrent): real, the host's containers
    and processes; the rehearsal judges only its own FakeDocker containers (other processes on the host are not its
    own). S3 runs beside S2 in its own process (registrar addendum 14:3x): its process (a ``smoke-run ... --stage
    S3`` command line), the processes naming its containers and its containers (named for S3's units,
    ``_s3_tags``) are listed apart in ``concurrent`` and are not S2's leftovers; anything else of route B still is."""
    if fake:
        return prelaunch.leftovers(found=[], docker=docker)["verdict"], None
    prefixes = tuple(sandbox.PREFIX + tag + "-" for tag in _s3_tags(root))
    found = prelaunch.processes()
    theirs = [(pid, command) for pid, command in found
              if S3_PROCESS.search(command) or any(prefix in command for prefix in prefixes)]
    judged = prelaunch.leftovers(found=[entry for entry in found if entry not in theirs], docker=docker)
    containers = judged["containers"]
    concurrent = {"processes": [{"pid": pid, "command": command[:200]} for pid, command in theirs],
                  "containers": sorted(name for name in containers or [] if name.startswith(prefixes))}
    if containers is None or set(containers) - set(concurrent["containers"]) or judged["route_b"] \
            or judged["alfworld"]:
        return "leftovers", concurrent
    return ("cannot_judge" if judged["excluded"] else "clean"), concurrent


def _probe_entries(spec):
    """The S1 receipt-class entries of the complete probe attempt (S2's receipt criterion reads them too); none in a
    smoke without S1 (a chain-G smoke has no probe root, registrar addendum 2026-10-23 02:3x)."""
    if not _has_s1(spec):
        return []
    probe_root = safe_path(spec["probe_root"])
    complete = [protocol.verified(read_json(p), "smoke-probe") for p in _attempts(probe_root)]
    complete = [p for p in complete if p["complete"]]
    return entries_of(complete[-1]) if complete else []


@contextlib.contextmanager
def _backends(spec, m, manifest_path, *, fake, env_path, roles_repo, answer=None):
    """(Setting, docker) of the smoke from the verified manifest (``manifest.setting_of(m, "smoke")``: the smoke
    solver's block, ``solver_of``). Real: the smoke solver's credential -- chain D's elucid credential file; in a
    chain-G smoke (registrar addendum 2026-10-23 02:3x) the GLM credential repository, the manifest's chain G
    ``env_path``, so ``env_path`` and ``roles_repo`` name the same repository -- and the roles' credential repository
    must be named explicitly and be the manifest's (so nothing is sent by accident), the code map and image are
    verified. ``fake`` (plan §7): FakeDocker, the scripted gateway of the smoke solver's model (``answer``, default
    ``_rehearsal_reply``; SX's: ``_sx_rehearsal``), FakeAlfEnv and FakeNative from ``tests/`` (imported only here), zero
    network."""
    solvers, ours = m["clients"]["solver"], solver_of(spec)
    if not fake:
        named = "" if ours.chain == "D" else " (a chain-G smoke: chain G's credential repository as both)"
        require(str(safe_path(env_path)) == str(safe_path(solvers[ours.chain]["env_path"]))
                and str(safe_path(roles_repo)) == str(safe_path(solvers["G"]["env_path"])),
                "The named credentials are not the smoke manifest's" + named)
        docker = sandbox.Docker()
        manifest.verify_unit(m, docker=docker)
        yield manifest.setting_of(m, budgets.SMOKE, path=manifest_path, docker=docker), docker
        return
    require(env_path is None and roles_repo is None, "A rehearsal names no credential")
    from tests import execskill_fakes as fakes  # the rehearsal's fakes (plan §7) live with the tests
    from tests import execskill_fakes_docker as fake_docker
    from tests import execskill_fakes_env as fake_env

    root = safe_path(spec["root"])
    docker = fake_docker.FakeDocker(root / "rehearsal-docker")
    provider = fakes.FakeProvider(ours.model, answer or _rehearsal_reply)
    native = fake_env.FakeNative()
    saved = backends._new_alfworld, backends._native, precheck.precheck
    backends._new_alfworld = lambda public, runtime: fake_env.FakeAlfEnv(
        json.loads(Path(public["game_file"]).read_text(encoding="utf-8")))
    backends._native = native.native
    precheck.precheck = native.precheck
    try:
        yield manifest.setting_of(m, budgets.SMOKE, path=manifest_path, docker=docker,
                                  transport=provider.transport), docker
    finally:
        backends._new_alfworld, backends._native, precheck.precheck = saved
        docker.close()


def _rehearsal_reply(system, user):
    """The rehearsal's scripted solver reply: on ALFWorld the last admissible command (the fake game's next plan step),
    on SpreadsheetBench a program, on LiveMath one letter, else one number -- each in its registered carrier."""
    if system.startswith(solver.ALF_SYSTEM):
        return "<action>%s</action>" % json.loads(user)["admissible_commands"][-1]
    if "input.xlsx" in user or "workbook" in system.lower():
        return "```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\nbook.save('output.xlsx')\n```"
    return "<answer>%s</answer>" % ("A" if '"options"' in user or '"choices"' in user else "1")


def run_stage(spec, manifest_path, stage, *, fake=False, env_path=None, roles_repo=None):
    """Run smoke stage ``stage`` (``BUILT_STAGES``) on the smoke Setting of the verified smoke manifest at
    ``manifest_path`` (its ledger ``<root>/shared/ledger``, caps solver 14M / GLM 2M) and record its judged result
    once (``record``). ``spec``: the smoke specification (record or path). A unit that stops (a cap, connectivity,
    the first reply not confirmed, any pause) keeps its attempt and the stage is reported, not judged: {"stage",
    "complete": False, "stopped", "unit"} (S4 adds the ``paused`` attempts awaiting ``write_recovery``). ``fake``:
    the zero-network rehearsal (``_backends``); a real run needs ``env_path`` and ``roles_repo`` (S-E6 makes no call
    and needs neither; a chain-G smoke names chain G's credential repository as both, registrar addendum 2026-10-23
    02:3x). S3 is ``smoke_roles.run``: its own run unit on these backends, then the roles unit (its own fake backends;
    notes/C7d.md, registrar addendum 14:3x). Returns the stage record, or the stopped report."""
    spec = load(spec) if not isinstance(spec, dict) else protocol.verified(spec, "smoke-spec")
    ours = solver_of(spec)
    require(fake or stage == "SE6" or (env_path is not None and roles_repo is not None), "A real smoke stage names "
            "%s and the roles' credential repository explicitly" % (
                "the elucid env path" if ours.chain == "D" else "chain G's credential repository as the env path"))
    require(stage in BUILT_STAGES, "Smoke stage %s is not run by run_stage (built: %s)" % (stage, BUILT_STAGES))
    require(not (safe_path(spec["root"]) / STAGES_DIR / (stage + ".json")).exists(), "Stage %s is recorded" % stage)
    m = manifest.load(manifest_path, verify=False)
    require(not protocol.is_zebra(m["configuration"]), "Use zpc-smoke for the ZebraLogic profile")
    require(not protocol.is_alfworld(m["configuration"]), "Use alf-smoke for the ALFWorld-only profile")
    require(m["evidence"] == manifest.SMOKE_EVIDENCE and m["root"] == spec["root"], "The smoke manifest of this spec")
    if fake:
        rehearsal_roots(spec)  # registrar addendum 15:0x: a rehearsal never records into the registered smoke root
    evidence = REHEARSAL_EVIDENCE if fake else manifest.SMOKE_EVIDENCE
    if stage == "SX":  # v2's example: listed by the spec, after S-E6 (whose ledger ratio it must not move)
        require("SX" in spec["stages"] and (safe_path(spec["root"]) / STAGES_DIR / "SE6.json").exists()
                and protocol.LEARNING[m["configuration"]] == "train",
                "SX runs in a smoke that lists it, after S-E6, on a manifest of a train configuration (main-v2)")
    if stage == "SE6":  # zero calls: a rehearsal's when it reads a rehearsal's S2 or S3
        found = evidence if fake else _evidence_of(spec, SE6_STAGES)
        return record(spec, stage, se6_projection(spec, m), evidence=found)
    if stage == "S3":  # the method roles, on their own backends (notes/C7d.md)
        from . import smoke_roles
        return smoke_roles.run(spec, m, manifest_path, fake=fake, env_path=env_path, roles_repo=roles_repo)
    rehearsal = _sx_rehearsal() if fake and stage == "SX" else None
    with _backends(spec, m, manifest_path, fake=fake, env_path=env_path, roles_repo=roles_repo,
                   answer=rehearsal.script if rehearsal else None) as (setting, docker):
        if stage == "S4":
            return _s4(spec, m, setting, evidence=evidence)
        if stage == "SX":
            return _sx(spec, m, setting, evidence=evidence,
                       transport=rehearsal.wikipedia.transport if rehearsal else None)
        results, confirm = [], True
        try:
            for name in [n for n in ITEM_SETS if n in PLAN[stage]]:
                items = _slice(stage, name, setting.pools[name])
                ran = not (safe_path(spec["root"]) / UNITS_DIR / stage / name / "unit.json").exists()
                results.append(_unit(spec, setting, stage, name, items, first=confirm and ran)["result"])
                confirm = confirm and not ran  # the first unit this process runs confirms the first reply
        except Pause as pause:
            return {"stage": stage, "complete": False, "stopped": pause.kind, "reason": pause.reason,
                    "unit": pause.cell}
        if stage == "SN1":
            return record(spec, stage, _sn1_judged(spec, results), evidence=evidence)
        bound = {bench: protocol.ledger_bound(ours.model, bench, branch=setting.branch, longest=setting.longest)
                 for bench in protocol.BENCHES}
        verdict, concurrent = _leftover(docker, fake=fake, root=spec["root"])
        judged = _s2_judged(spec, results, ledger_bound=bound, ledger=_ledger_rows(setting), leftover=verdict,
                            concurrent=concurrent, probe_entries=_probe_entries(spec))
        return record(spec, stage, judged, evidence=evidence)


# ------------------------------------------------------------------- S-E6: the zero-call cost check (§9.3, §10)
SE6_STAGES = ("S2", "S3")  # registrar addendum 13:0x: S-E6 reads the recorded S2 and S3 stages (not S-N1 or S4)
SE6_CELLS = ("S2",)  # the production stage whose cells S-E6 measures; the ratio's denominator is every charged cell
# §4.1, §9.3: the chain S-E6 prices at the smoke solver's per-cell tokens, a placeholder -- chain G in a chain D smoke,
# chain D in a chain-G smoke (registrar addendum 2026-10-23 02:3x)
SE6_PLACEHOLDER = {"D": {"chain_g": "priced at the elucid per-cell tokens: a placeholder (§4.1, §9.3)"},
                   "G": {"chain_d": "chain D priced at the glm-5.3 per-cell tokens: a placeholder (§4.1, §9.3)"}}
# Registrar addendum 14:4x, implementation-time registrations (§5.4 C4 and §5.7 imply them; the registration lists
# no number), counted as the code allows them per step and bench (R7 decision 2026-10-22 16:1x, R7c): at most one
# leakage judge call per check of a change (``engineer.leak_check``); each of the step's two engineer units
# (``SELFTEST_PASSES``) checks at most MAX_CHANGES proposed changes once, and every further check follows a fix call,
# of which the step's ENGINEER_CALLS (R7a: shared by both units) leave ENGINEER_CALLS - 2 beside the two proposals,
# at most MAX_CHANGES per unit: 2 x 3 + 4 = 10. MAX_CHANGES describer calls (one per new or revised procedure).
ENGINEER_UNITS = protocol.SELFTEST_PASSES  # ``engineer`` and ``engineer-2``
LEAKAGE_CALLS = ENGINEER_UNITS * protocol.MAX_CHANGES + min(protocol.ENGINEER_CALLS - ENGINEER_UNITS,
                                                            ENGINEER_UNITS * protocol.MAX_CHANGES)
DESCRIBER_CALLS = protocol.MAX_CHANGES
# R7c: a full engineer request carries its system prompt beside the fitted role input (roles.fit's limit)
ENGINEER_REQUEST_FLOOR = protocol.ROLE_INPUT_BYTES + len(engineer.ENGINEER_SYSTEM.encode())
# registrar addendum 14:3x: the registered maximum calls per step and bench of each method role (registration
# §9.2-§9.3, calc T11, the protocol constants; 14:4x for leakage and describer); each role charges its step role
# scope (budgets.ROLES)
MAX_ROLE_CALLS = {
    "engineer": protocol.ENGINEER_CALLS,  # the proposals, re-proposals and fixes of both engineer units (§5.4, R7a)
    "leakage": LEAKAGE_CALLS,
    "describer": DESCRIBER_CALLS,
    "examiner": protocol.DETECTOR_CALLS + protocol.POLICY_CALLS + protocol.GENERATOR_CALLS * protocol.BAND_ROUNDS,
    "examiner_research": protocol.MAX_RESEARCH_REQUESTS * protocol.RESEARCH_MAX_CALLS,  # 24 requests x 8 calls
}
CARD, PROCEDURE = "card", "procedure"  # a cell with no procedure enabled is a card cell (§9.1: x1 / x1.25-1.6)


def max_role_calls(configuration=protocol.PILOT):
    """The maximum calls per step and bench of each method role in a run configuration: ``MAX_ROLE_CALLS``; in a
    train configuration (main-v2, owner decision 2026-10-23 13:3x) ``TRAIN_ROUNDS`` engineer units of
    ``TRAIN_ENGINEER_CALLS`` calls and ``TRAIN_ANALYST_CALLS`` analyst calls each, at most one leakage judge call per
    check -- per unit its ``MAX_CHANGES``
    first checks and one after each fix call, all calls but one proposal being fix calls --, the same describer calls,
    and the examiner's v1 calls plus ``TOPUP_ROUNDS`` top-up writes of ``GENERATOR_CALLS`` after each of its
    ``BAND_ROUNDS`` builds."""
    if protocol.LEARNING[configuration] != "train":
        return dict(MAX_ROLE_CALLS)
    train_calls = (protocol.TRAIN_ENGINEER_CALL_BUDGETS[configuration]
                   if protocol.is_v28(configuration) else protocol.TRAIN_ENGINEER_CALLS)
    result = {"engineer": protocol.TRAIN_ROUNDS * (train_calls + protocol.TRAIN_ANALYST_CALLS),
            "leakage": protocol.TRAIN_ROUNDS * (protocol.MAX_CHANGES + protocol.TRAIN_ENGINEER_CALLS - 1),
            "describer": DESCRIBER_CALLS,
            "examiner": MAX_ROLE_CALLS["examiner"]
            + protocol.GENERATOR_CALLS * protocol.BAND_ROUNDS * protocol.TOPUP_ROUNDS,
            "examiner_research": MAX_ROLE_CALLS["examiner_research"]}
    if protocol.is_v29(configuration):
        from . import v29_limits
        bench = protocol.active_benches(configuration)[0]
        result.update({role: v29_limits.judge_calls(protocol, bench) for role in v29_limits.JUDGE_ROLES})
        result["leakage"] += protocol.TRAIN_ROUNDS * protocol.MAX_CHANGES
        if protocol.is_v291(configuration):
            result.update(v29_limits.v291_role_calls(protocol, configuration))
    return result


def engineer_request_floor(configuration=protocol.PILOT):
    """``ENGINEER_REQUEST_FLOOR`` with the configuration's engineer prompt (v2: the longer of ``ENGINEER_SYSTEM_V2``
    and the analysts' ``ANALYST_SYSTEM``, both engineer-role calls). v2.3 also pins its single-mode smoke prompt."""
    if protocol.is_v291(configuration):
        from . import v29_limits
        return protocol.ROLE_INPUT_BYTES + v29_limits.V291_ENGINEER_SYSTEM_BYTES
    if protocol.is_v29(configuration):
        from . import engineer_v29
        bench = protocol.active_benches(configuration)[0]
        return protocol.ROLE_INPUT_BYTES + max(len((engineer_v29.system(configuration, train=train) + suffix).encode())
            for train in (False, True) for suffix in ("", engineer_v29.FIX_SYSTEM,
                engineer_v29.FORMAT_RETRY_SYSTEM, engineer_v29.AUDIT_FIX_SYSTEM))
    if protocol.is_v28(configuration):
        prompts = ((engineer.ENGINEER_SYSTEM_ALF_V3, engineer.ENGINEER_SYSTEM_SINGLE_ALF_V3)
                   if protocol.is_alfworld(configuration) else
                   (engineer.ENGINEER_SYSTEM_ZPC_V28, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V28))
        suffixes = ("", engineer.engineer_v28.FIX_SYSTEM, engineer.engineer_v28.FORMAT_RETRY_SYSTEM)
        candidates = [prompt + suffix for prompt in prompts for suffix in suffixes] + [engineer.ANALYST_SYSTEM]
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in candidates)
    if protocol.is_alfworld_v2(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ALF_V2, engineer.ENGINEER_SYSTEM_SINGLE_ALF_V2, engineer.ANALYST_SYSTEM))
    if protocol.is_alfworld(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ALF_V1, engineer.ENGINEER_SYSTEM_SINGLE_ALF_V1, engineer.ANALYST_SYSTEM))
    if protocol.is_v27(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ZPC_V27, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V27, engineer.ANALYST_SYSTEM))
    if protocol.is_v26(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ZPC_V26, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V26, engineer.ANALYST_SYSTEM))
    if protocol.is_v25(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ZPC_V25, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V25, engineer.ANALYST_SYSTEM))
    if protocol.is_v24(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ZPC_V24, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V24, engineer.ANALYST_SYSTEM))
    if configuration == protocol.ZEBRA_PC_V1:
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_ZPC, engineer.ENGINEER_SYSTEM_SINGLE_ZPC, engineer.ANALYST_SYSTEM))
    if protocol.is_v23(configuration):
        return protocol.ROLE_INPUT_BYTES + max(len(prompt.encode()) for prompt in (
            engineer.ENGINEER_SYSTEM_V23, engineer.ENGINEER_SYSTEM_SINGLE_V23, engineer.ANALYST_SYSTEM))
    if protocol.LEARNING[configuration] != "train":
        return protocol.ROLE_INPUT_BYTES + len(engineer.ENGINEER_SYSTEM.encode())
    return protocol.ROLE_INPUT_BYTES + max(len(engineer.ENGINEER_SYSTEM_V2.encode()),
                                           len(engineer.ANALYST_SYSTEM.encode()))


def _cell_records(root, stage):
    """Every cell record of a stage's units, every attempt (a stopped attempt's sends were charged too); for S3 its
    own run unit's and its confirmation units' (its roles unit makes no solver call; registrar addendum 14:3x)."""
    base = safe_path(root) / UNITS_DIR / stage
    found = (sorted(base.glob("s1-searchqa/run/attempt-*/cells/*.json")) + sorted(base.glob(
        "confirm-*/attempt-*/cells/*.json"))) if stage == "S3" else sorted(base.glob("**/attempt-*/cells/*.json"))
    return [protocol.verified(read_json(path), "cell") for path in found]


def measured_cells(cells):
    """What S-E6 reads of the smoke's cells: per bench and arm, and per bench and class (card / procedure), the cells
    with a verdict and their reported tokens (prompt + completion of every send); the largest request bytes per bench
    over every send; the reported tokens of every cell (a stopped one included), the ledger ratio's denominator."""
    per_arm, per_class, request_bytes, actual = {}, {}, {}, 0
    for cell in cells:
        bench, tokens = cell["cell"]["benchmark"], _usage(cell)
        actual += tokens
        sizes = [send["request_bytes"] for send in cell["sends"] if type(send.get("request_bytes")) is int]
        if sizes:
            request_bytes[bench] = max(request_bytes.get(bench, 0), *sizes)
        if cell["final"] is None:  # stopped before its verdict: charged, not a measured cell
            continue
        kind = PROCEDURE if cell.get("enabled") else CARD
        for table, key in ((per_arm, cell["cell"]["arm"]), (per_class, kind)):
            entry = table.setdefault(bench, {}).setdefault(key, {"cells": 0, "tokens": 0})
            entry["cells"] += 1
            entry["tokens"] += tokens
    return {"per_arm": per_arm, "per_class": per_class, "request_bytes": request_bytes, "actual": actual}


def _per_cell(per_class):
    """{bench: {"card", "procedure", "procedure_assumed"}} tokens per cell; a bench without a measured procedure
    cell prices one at the registered high factor (``PROCEDURE_ARM_FACTOR``) over its measured card cell."""
    out = {}
    for bench in protocol.BENCHES:
        found = per_class.get(bench, {})
        require(found.get(CARD, {}).get("cells"), "S-E6 measures every bench: no card cell of %s" % bench)
        card = found[CARD]["tokens"] / found[CARD]["cells"]
        assumed = not found.get(PROCEDURE, {}).get("cells")
        procedure = (card * float(protocol.PROCEDURE_ARM_FACTOR[1]) if assumed
                     else found[PROCEDURE]["tokens"] / found[PROCEDURE]["cells"])
        out[bench] = {CARD: card, PROCEDURE: procedure, "procedure_assumed": assumed}
    return out


def _bounds(m):
    """{chain: {bench: B}}: chain D's registered ledger bound (§4.1, the smoke manifest's branch), chain G's 65,536."""
    block = m["clients"]["solver"]["D"]
    return {"D": {b: protocol.ledger_bound(protocol.CHAINS["D"], b, branch=block["branch"], longest=block["longest"])
                  for b in protocol.BENCHES},
            "G": {b: protocol.ledger_bound(protocol.CHAINS["G"], b) for b in protocol.BENCHES}}


def _scope_cells(chain, pilot=protocol.PILOT):
    """{scope: [{bench: (card, procedure)} alternatives]} of every solver scope of ``chain`` at the registered maximum
    schedule of the run configuration ``pilot`` (``protocol.CONFIG_SCHEDULE_CELLS``: the pilots'
    ``MAX_SCHEDULE_CELLS``, main's ``MAIN_SCHEDULE_CELLS``; ``TEST_READ_CELLS``; calc T4-T6): each step kind; a redo
    of a step kind, one acceptance block (``SLICES`` blocks) or the whole kind; the test read; the redo reserve, the
    largest single acceptance block of the configuration's steps; the chain's solver total, every step kind, the test
    read and that block. A scope with several alternatives (the redo reserve, the solver total) takes the dearest."""
    plan, schedule, out = protocol.PILOTS[pilot], protocol.CONFIG_SCHEDULE_CELLS[pilot], {}
    blocks, totals = [], {}
    for k, bench in enumerate(plan["order"], 1):
        for kind in budgets.step_kinds(pilot):
            cells = schedule[bench][kind]
            out[budgets.solver_scopes(chain, bench, k, kind)[-1]] = [cells]
            redo = cells
            if kind == "accept":
                share = protocol.SLICES[bench]["blocks"]
                redo = {b: (card / share, proc / share) for b, (card, proc) in cells.items()}
                blocks.append(redo)
            for attempt in range(2, protocol.MAX_REDOS + 2):
                out[budgets.solver_scopes(chain, bench, k, kind, attempt)[-1]] = [redo]
            for b, (card, proc) in cells.items():
                was = totals.get(b, (0, 0))
                totals[b] = (was[0] + card, was[1] + proc)
    test = protocol.TEST_READ_CELLS[pilot]
    out[chain + ":test"] = [test]
    out[chain + ":redo"] = blocks
    for b, (card, proc) in test.items():
        was = totals.get(b, (0, 0))
        totals[b] = (was[0] + card, was[1] + proc)
    solver_total = []
    for block in blocks:
        whole = dict(totals)
        for b, (card, proc) in block.items():
            was = whole.get(b, (0, 0))
            whole[b] = (was[0] + card, was[1] + proc)
        solver_total.append(whole)
    out[chain + ":solver"] = solver_total
    return out


def se6_projection(spec, m):
    """§10 S-E6 (zero calls; registrar addendum 13:0x: after the recorded S2 and S3): from the cell records of S2 and
    the smoke ledger, the measured tokens per cell per bench and arm (and per bench and class) and the ledger/actual
    ratio (``smoke:solver`` settled over the reported tokens of every solver cell it settled: S2's, S3's run unit and
    confirmation cells, and S-N1's and S4's units if they ran); then, for every solver scope cap of both chains
    (``budgets.chain_caps``, the test read and the redo reserve included), measured tokens per cell x ratio x the
    maximum-schedule cells + one full next reservation R = 4 x (the largest measured request bytes + 512 + B)
    (``coevo5.ledger.reservation``; budget.py:283-314), judged by ``se6_cost`` -- any projection over its cap fails
    S-E6: a v1.1 re-registration before the pilot (§9.3). Every projection is of the smoke manifest's run
    configuration (``m["configuration"]``: its order, maximum schedule and caps; registrar 17:0x: the smoke of the
    main experiment projects ``main``), recorded as ``configuration``. The other chain's cells are priced at the
    smoke solver's measurements, a placeholder (``SE6_PLACEHOLDER``, §4.1): chain G's at the elucid ones in a chain D
    smoke (its own check follows its first run unit), chain D's at glm-5.3's in a chain-G smoke (registrar addendum
    2026-10-23 02:3x). Registrar addendum 14:3x: every GLM scope of both
    chains is projected too (``glm_projection``) from S3's measured tokens per role call (its roles unit's record,
    bound by the S3 stage record) at the registered maximum role calls per step (``MAX_ROLE_CALLS``) + one full next
    reservation at no less than a full role input (registrar addendum 14:4x); an excess fails S-E6 as well.
    ``overall`` is the chain's solver cap plus its GLM cap and is covered by those two."""
    root = safe_path(spec["root"])
    recorded = {}
    for stage in SE6_STAGES:
        path = root / STAGES_DIR / (stage + ".json")
        require(path.exists(), "S-E6 reads the recorded stage %s" % stage)
        recorded[stage] = protocol.verified(read_json(path), "smoke-stage")
        require(recorded[stage]["spec"] == spec[protocol.RECORD_HASH], "A stage of another smoke")
    found = measured_cells([cell for stage in SE6_CELLS for cell in _cell_records(root, stage)])
    charged = {stage: _cell_records(root, stage) for stage in PRODUCTION_STAGES + ("S3",)}  # every settled solver cell
    actual = measured_cells([cell for cells in charged.values() for cell in cells])["actual"]
    ledger_path = budgets.ledger_root(root, budgets.SMOKE)
    require(ledger_path.is_dir(), "The smoke ledger exists")
    snapshot = Budget(ledger_path).snapshot()
    scope = snapshot[budgets.SMOKE + ":solver"]
    require(scope["open"] == 0 and found["actual"] > 0, "S-E6 reads a settled smoke ledger and measured cells")
    ratio = scope["settled"] / actual
    per_cell = _per_cell(found["per_class"])
    require(set(found["request_bytes"]) == set(protocol.BENCHES), "S-E6 measures the request bytes of every bench")
    bounds = _bounds(m)
    reserve = {chain: {b: reservation(found["request_bytes"][b], bounds[chain][b]) for b in protocol.BENCHES}
               for chain in protocol.CHAINS}
    scopes, projected, listed = {}, set(), {}
    configuration = m["configuration"]
    require(configuration in protocol.CONFIGURATIONS, "The smoke manifest names its run configuration")
    for chain in sorted(protocol.CHAINS):
        caps = budgets.chain_caps(chain, configuration)
        for name, alternatives in _scope_cells(chain, configuration).items():
            rows = []
            for cells in alternatives:
                tokens = sum(card * per_cell[b][CARD] + proc * per_cell[b][PROCEDURE]
                             for b, (card, proc) in cells.items())
                count = sum(card + proc for card, proc in cells.values())
                rows.append({"per_cell": tokens / count, "cells": count, "cap": caps[name],
                             "reservation": max(reserve[chain][b] for b in cells)})
            scopes[name] = max(rows, key=lambda row: row["per_cell"] * row["cells"] + row["reservation"])
            projected.add(name)
        listed.update({name: "GLM-5.3 method roles or the root: no solver cells" for name in caps
                       if name not in projected})
    require(all(name == budgets.ROOT or name.endswith(":glm") or ":role:" in name for name in listed),
            "Every solver scope of the chains is projected")
    cost = se6_cost(scopes, ratio=ratio)
    measured = role_calls_measured(_s3_calls(spec, recorded["S3"]))
    glm = glm_projection(measured, configuration)
    require(set(glm) == set(listed) - {budgets.ROOT}, "Every GLM scope of the chains is projected")
    listed = {budgets.ROOT: "the chain's solver cap plus its GLM cap: covered by <chain>:solver and <chain>:glm"}
    anchors = {b: {"card_per_cell": per_cell[b][CARD], "anchor_high": protocol.CELL_ANCHORS[b][1],
                   "above_high": per_cell[b][CARD] > float(protocol.NOISE_REREGISTER) * protocol.CELL_ANCHORS[b][1]}
               for b in protocol.BENCHES}
    rows = {**{name: row["fits"] for name, row in cost["rows"].items()}, "ratio": cost["ratio_ok"],
            **{name: row["fits"] for name, row in glm.items()}}
    spent = recorded["S3"]["result"].get("glm") or {}
    return {"rows": rows, "scopes": cost["rows"], "inputs": scopes, "ratio": ratio, "ratio_ok": cost["ratio_ok"],
            "ledger": {"settled": scope["settled"], "actual": actual,
                       "stages": [stage for stage, cells in charged.items() if cells]}, "per_arm": found["per_arm"],
            "glm": {"scopes": glm, "measured": measured, "max_calls": max_role_calls(configuration),
                    "request_bytes_floor": protocol.ROLE_INPUT_BYTES,
                    "ratio": "1: a role call's charge is the ledger's settlement",
                    "s3": {key: spent.get(key) for key in ("spent", "total", "by_role", "sends", "cap", "within_cap")},
                    "smoke_glm": snapshot.get(budgets.SMOKE + ":glm")},
            "per_class": found["per_class"], "per_cell": per_cell, "request_bytes": found["request_bytes"],
            "bounds": bounds, "reservations": reserve, "anchors": anchors, "not_projected": listed,
            "pilot": configuration, "configuration": configuration,
            **SE6_PLACEHOLDER[solver_of(spec).chain],
            "passed": cost["passed"] and all(row["fits"] for row in glm.values())}


def _s3_calls(spec, s3):
    """The compact role calls (``smoke_roles._calls``) of the roles unit the S3 stage record names (its record hash
    checked)."""
    from . import smoke_roles  # imported here: smoke_roles imports this module

    path = smoke_roles.unit_root(spec, s3["result"]["unit"].rsplit("/", 1)[1]) / "unit.json"
    require(path.exists(), "S-E6 reads the roles unit of the recorded S3")
    value = protocol.verified(read_json(path), "unit")
    require(value[protocol.RECORD_HASH] == s3["result"]["unit_sha256"], "The roles unit the S3 record names")
    return value["result"]["calls"]


def role_calls_measured(calls):
    """{role: {"calls", "tokens", "per_call", "request_bytes"}} of S3's role calls: the charge of every send (what the
    ledger settled, so no ledger/actual ratio applies) per call, and the largest request bytes of the role."""
    out = {}
    for call in calls:
        entry = out.setdefault(call["role"], {"calls": 0, "tokens": 0, "request_bytes": 0})
        entry["calls"] += 1
        entry["tokens"] += call["charged"]
        if type(call.get("request_bytes")) is int:
            entry["request_bytes"] = max(entry["request_bytes"], call["request_bytes"])
    for entry in out.values():
        entry["per_call"] = entry["tokens"] / entry["calls"]
    return out


def _glm_fit(settled, reserve, cap):
    needed = math.ceil(settled + reserve)
    return {"settled": math.ceil(settled), "reservation": reserve, "needed": needed, "cap": cap, "fits": needed <= cap}


def glm_projection(measured, pilot=protocol.PILOT):
    """Every GLM scope of both chains at the registered maximum role calls (registrar addendum 14:3x; §9.2-§9.3,
    calc T11), zero calls: a step role scope (``budgets.glm_scopes``; caps ``budgets.role_scope_caps`` of the run
    configuration ``pilot``: main's 5M / 5M / 9.2M, registrar 17:0x) needs the sum
    over the roles it charges (``budgets.ROLES``) of S3's measured tokens per call x ``MAX_ROLE_CALLS`` + one full
    next reservation R = 4 x (request bytes + 512 + ``ROLE_MAX_TOKENS``) (``coevo5.ledger.reservation``), the request
    bytes of each role being the larger of the largest request S3 sent for it and ``protocol.ROLE_INPUT_BYTES``, the
    role-input limit ``roles.fit`` enforces (registrar addendum 14:4x: S3 runs on SearchQA, and a full SpreadsheetBench
    or OfficeQA role request reserves about 0.95M), for the engineer that limit plus its system prompt
    (``ENGINEER_REQUEST_FLOOR``: a full engineer request reserves 968,264; R7 decision 16:1x, R7c); ``<chain>:glm``
    (``protocol.CONFIG_GLM_CAP``) needs every step of the configuration's order at that maximum + the largest R.
    ``measured``:
    ``role_calls_measured``; a role S3 did not measure is priced at the dearest measured role call and the widest
    measured request (``assumed``). Returns {scope: {"settled", "reservation", "needed", "cap", "fits"} (+ "roles",
    "assumed")}; a scope fits when needed <= cap."""
    require(measured and all(entry["calls"] > 0 for entry in measured.values()), "S3 measured role calls")
    plan, calls = protocol.PILOTS[pilot], max_role_calls(pilot)
    roles = tuple(budgets.ROLES) + (("audit_g", "audit_d") if protocol.is_v29(pilot) else ())
    require(set(calls) == set(roles) and set(measured) <= set(roles), "The registered method roles")
    dearest = max(entry["per_call"] for entry in measured.values())
    widest = max(entry["request_bytes"] for entry in measured.values())
    per_call = {role: measured[role]["per_call"] if role in measured else dearest for role in roles}
    size = {role: max(measured[role]["request_bytes"] if role in measured else widest, protocol.ROLE_INPUT_BYTES)
            for role in roles}  # registrar addendum 14:4x: never below a full role input
    size["engineer"] = max(size["engineer"], engineer_request_floor(pilot))  # R7c: with the engineer's system prompt
    assumed = sorted(set(roles) - set(measured))
    out = {}
    for chain in sorted(protocol.CHAINS):
        caps, total, widest_reserve = budgets.chain_caps(chain, pilot), 0, 0
        for k, bench in enumerate(plan["order"], 1):
            charged = {}
            for role in roles:
                scope = (budgets.audit_scopes(chain, role[-1].upper(), bench, k) if role.startswith("audit_")
                         else budgets.glm_scopes(chain, role, bench, k))
                charged.setdefault(scope[-1], []).append(role)
            for name, members in sorted(charged.items()):
                settled = sum(per_call[role] * calls[role] for role in members)
                reserve = max(reservation(size[role], protocol.ENGINEER_MAX_TOKENS[pilot]
                                          if role == "engineer" else 8192 if role.startswith("audit_") else protocol.ROLE_MAX_TOKENS) for role in members)
                out[name] = {**_glm_fit(settled, reserve, caps[name]), "roles": members,
                             "assumed": [role for role in members if role in assumed]}
                total += settled
                widest_reserve = max(widest_reserve, reserve)
        name = budgets.glm_scopes(chain, roles[0], plan["order"][0], 1)[1]
        out[name] = {**_glm_fit(total, widest_reserve, caps[name]), "roles": list(roles), "assumed": assumed}
    return out


# ----------------------------------------------------------------------- S4: the mini-step and its drill (§10)
S4_DIR = "S4"  # <root>/units/S4: the mini-step's chain root (step.run_step, chain "smoke")
DRILL_HISTORY = "history"  # <root>/units/S4/history: the mini-step's consumption registry (smoke namespace)
SMOKE_LABEL = "smoke drill (registration §10 S4)"  # opens the decision text of a drill's recovery.json
RECOVERY_FIELDS = ("by", "date", "decision")  # the owner format (coevo5 evaluation.py:44, :173-178)


def _confirm(spec, setting, stage, bench, item):
    """The single production cell (``CONFIRM_ARM``: the card arm on ``item`` of ``bench``) dispatched alone, in its
    own unit ``<root>/units/<stage>/confirm-<n>`` (one per process run), before anything concurrent (plan §10 step 4);
    a reply that is not a confirmed one of the smoke solver's registered model (``solver_of``) pauses it."""
    base = safe_path(spec["root"]) / UNITS_DIR / stage
    n = 1 + (len(list(base.glob("confirm-*"))) if base.is_dir() else 0)
    unit = "smoke/%s/confirm-%d" % (stage, n)
    local = units.for_unit(setting, budgets.SMOKE, bench, unit)
    key = rounds.key(bench, item["task_id"])
    ours = solver_of(spec)

    def work(attempt):
        endpoint, _ = _endpoint(spec, local, bench)
        card = Arm("card", empty(step="smoke/" + stage, evidence=manifest.SMOKE_EVIDENCE))
        task = {key: {"public": item["public"], "private": item["private"]}}
        found = rounds.run_round(replace(local, workers=1), attempt, endpoint, unit, {CONFIRM_ARM: card},
                                 {CONFIRM_ARM: [(key, 1)]}, task, tag="confirm")
        cell = [f for cells in found.values() for f in cells][0]
        if not _confirmed(cell, ours.echo):
            raise Pause("first_call_not_confirmed", "the single first reply is not a confirmed %s reply"
                        % ours.model, cell["cell"]["id"])
        return {"cell": cell["cell"]["id"], "tokens": _usage(cell)}

    identity = {"unit": unit, "stage": stage, "set": "confirm", "spec": spec[protocol.RECORD_HASH]}
    return units.run_unit(base / ("confirm-%d" % n), run=setting.run, identity=identity, work=work,
                          evidence=setting.evidence, drain=units.drainer(setting, budgets.SMOKE, unit))


def _paused(root):
    """The paused attempts of the mini-step's units under ``root`` (``<root>/units/S4/s1-searchqa``) that wait for the
    operator's recovery (no ``recovery.json``, unit incomplete), as strings. A paused confirmation unit is not listed:
    the next process run confirms in a new one."""
    out = []
    for status in sorted(safe_path(root).glob("**/attempt-*/status.json")):
        attempt = status.parent
        if not (attempt / "recovery.json").exists() and not (attempt.parent / "unit.json").exists():
            out.append(str(attempt))
    return out


def _s4(spec, m, setting, *, evidence=manifest.SMOKE_EVIDENCE):
    """§10 S4: the confirmation cell, then the mini-step (``step.run_step`` with chain "smoke" and a
    ``step.SmokeStep``: the 60 S4 SearchQA smoke items, the fixture package X re-parented on the smoke's empty parent
    as S', the registered fault switch on
    the accept unit's first attempt) on the smoke ledger, its consumption in the smoke namespace of the drill registry
    ``<root>/units/S4/history`` (the 280 SearchQA smoke items stay held by ``smoke/items`` in the history root). A
    pause returns the stopped report with the attempts waiting for ``write_recovery``; the redo is the same call."""
    chain_root = safe_path(spec["root"]) / UNITS_DIR / S4_DIR
    items = _slice("S4", "searchqa", setting.pools["searchqa"])
    registry = Registry(chain_root / DRILL_HISTORY, evidence=setting.evidence)
    services = replace(manifest.services_of(m, budgets.SMOKE, setting=setting), registry=registry)
    accept_root = units.unit_path(chain_root, 1, step.SMOKE_BENCH, "accept")
    parent = empty(step="smoke/s0", evidence=setting.evidence)
    candidate = replace(fixtures.fixture_package(), parent_sha256=parent.sha256)
    mini = step.SmokeStep(items=tuple(items), candidate=candidate, model=solver_of(spec).model,
                          drill=FaultSwitch(spec, accept_root, fail_at=protocol.S4_DRILL_CALL))
    try:
        if not (accept_root.parent / step.STEP_FILE).exists():
            _confirm(spec, setting, "S4", step.SMOKE_BENCH, items[0])
        found = step.run_step(setting, budgets.SMOKE, step.SMOKE_BENCH, 1, parent, services=services,
                              chain_root=chain_root, smoke=mini)
    except Pause as pause:
        return {"stage": "S4", "complete": False, "stopped": pause.kind, "reason": pause.reason, "unit": pause.cell,
                "paused": _paused(accept_root.parent)}
    return record(spec, "S4", s4_judged(chain_root, found.record, registry, items), evidence=evidence)


def _one(path, name):
    return protocol.verified(read_json(path), name) if path.exists() else None


# ------------------------------------------------------------------- SX: v2's example (owner decision 2026-10-23)
SX_DIR = "SX"  # <root>/units/SX: the example's chain root (step.run_step, chain "smoke"); its registry DRILL_HISTORY


def _sx_items(setting):
    """SX's 260 SearchQA smoke items: those after S2's 20, which S-N1 and S4 would take (``protocol.SX_SLICES``: run
    100, acceptance 160; neither stage runs in a v2 smoke, and S3's own run unit keeps its own registry)."""
    start, n = protocol.SMOKE_REAL_ITEMS["searchqa"]["S2"], protocol.SX_SLICES["run"] + protocol.SX_SLICES["accept"]
    items = list(setting.pools["searchqa"])
    require(len(items) >= start + n, "The SearchQA smoke items hold SX's %d" % n)
    return items[start:start + n]


def _sx_rehearsal():
    """SX's zero-network rehearsal (``smoke-run --stage SX --fake``): ``tests/execskill_fakes_sx.py``'s scripted
    method roles of the example step beside the smoke solver's scripted replies (``_rehearsal_reply``), and
    FakeWikipedia for the research sources (imported only here; the rehearsal's fakes live with the tests)."""
    from tests import execskill_fakes_sx as fakes
    return fakes.SXRehearsal(_rehearsal_reply)


def _sx(spec, m, setting, *, evidence=manifest.SMOKE_EVIDENCE, transport=None):
    """v2's example SX (owner decision 2026-10-23 13:3x: "最好真正的跑通了一个示例再开始正式实验"): the confirmation
    cell, then the whole v2 step (``step.run_step`` with chain "smoke" and ``step.SmokeStep(train=True)``: run,
    diagnose, generate, the training rounds, the self-test, accept and freeze) on its 260 SearchQA smoke items with
    the smoke solver and the real GLM-5.3 roles, on the smoke ledger, its consumption in the smoke namespace of its own
    registry ``<root>/units/SX/history``. A pause returns the stopped report; the stage is judged by ``sx_judged``.
    ``transport``: the research sources' Wikipedia transport (a rehearsal's fake; None: the registered gateway)."""
    chain_root = safe_path(spec["root"]) / UNITS_DIR / SX_DIR
    items = _sx_items(setting)
    registry = Registry(chain_root / DRILL_HISTORY, evidence=setting.evidence)
    services = replace(manifest.services_of(m, budgets.SMOKE, setting=setting, transport=transport),
                       registry=registry)
    parent = empty(step="smoke/s0", evidence=setting.evidence)
    example = step.SmokeStep(items=tuple(items), candidate=None, model=solver_of(spec).model, train=True)
    step_root = chain_root / ("s1-" + step.SMOKE_BENCH)
    try:
        if not (step_root / "run" / "unit.json").exists():
            _confirm(spec, setting, "SX", step.SMOKE_BENCH, items[0])
        found = step.run_step(setting, budgets.SMOKE, step.SMOKE_BENCH, 1, parent, services=services,
                              chain_root=chain_root, smoke=example)
    except Pause as pause:
        return {"stage": "SX", "complete": False, "stopped": pause.kind, "reason": pause.reason, "unit": pause.cell}
    return record(spec, "SX", sx_judged(chain_root, found.record, registry, items, setting.budget.snapshot()),
                  evidence=evidence)


def sx_judged(chain_root, value, registry, items, snapshot):
    """SX's rows from the example step's records: ``unit`` -- run, diagnose, generate, engineer-r1, selftest, accept
    and freeze complete and every completed unit named in the sealed step record; ``training`` -- at least one
    ``train-r<r>`` unit evaluated items (its cells > 0); ``acceptance`` -- the accept unit decided accept or reject on
    its sealed round, and the decision is made again from the sealed record and the cells read back by its block ->
    attempt map (``acceptance.round_cells``, ``acceptance.reproduce``); ``consumption`` -- in the example's registry
    every run item decided by the run unit, every dispatched acceptance item decided by the accept unit, every other
    acceptance item released, each registered once; ``ledger`` -- the smoke ledger's solver and GLM scopes hold no
    open reservation and stay within their caps (``snapshot``). An acceptance on the last evaluated candidate because
    no round adopted is recorded as ``exercise``."""
    step_root = safe_path(chain_root) / ("s1-" + step.SMOKE_BENCH)
    records = {name: _one(step_root / name / "unit.json", "unit") for name in step.UNITS_V2}
    ran = {name: rec for name, rec in records.items() if rec is not None}
    needed = ("run", "diagnose", "generate", "engineer-r1", "selftest", "accept", "freeze")
    unit_ok = all(records[name] for name in needed) and value["units"] == {
        name: rec[protocol.RECORD_HASH] for name, rec in ran.items()}
    trains = {name: rec["result"] for name, rec in ran.items() if name.startswith("train-r")}
    accept_root = step_root / "accept"
    sealed = _one(accept_root / "sealed.json", "acceptance-sealed")
    last = accept_root / records["accept"]["attempt"] if records["accept"] else None
    decision = _one(last / "decision" / "decision.json", "decision") if last else None
    decided = decision is not None and decision["decision"] in ("accept", "reject")
    try:
        cells = acceptance.round_cells(accept_root, sealed, decision) if sealed and decided else []
    except (OSError, ValueError):
        cells = None
    accepted_ok = (decided and cells is not None and decision["sealed"]["record"] == sealed[protocol.RECORD_HASH]
                   and value["decision_sha256"] == decision[protocol.RECORD_HASH]
                   and acceptance.reproduce(cells, sealed, decision))
    cut = protocol.SX_SLICES["run"]
    run_ids, accept_ids = [i["task_id"] for i in items[:cut]], [i["task_id"] for i in items[cut:]]
    sent = set(acceptance.dispatched(sealed)) if sealed and decided else set()
    entries = registry.entries(budgets.SMOKE, step.SMOKE_BENCH)

    def state(item, wanted, unit):
        line = entries.get(item)
        return line is not None and line["state"] == wanted and line["unit"] == unit

    path = registry.path(budgets.SMOKE, step.SMOKE_BENCH)
    lines = [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    registered = {}
    for line in lines:
        if line["state"] == "registered":
            registered[line["item_id"]] = registered.get(line["item_id"], 0) + 1
    consumption = (all(state(i, "decided", "smoke/s1-searchqa/run") for i in run_ids)
                   and all(state(i, "decided" if i in sent else "routed_not_dispatched", "smoke/s1-searchqa/accept")
                           for i in accept_ids)
                   and registered == {i: 1 for i in run_ids + accept_ids})
    scopes = {name: snapshot.get(name) or {} for name in (budgets.SMOKE + ":solver", budgets.SMOKE + ":glm")}
    ledger = all(entry.get("open") == 0 and entry.get("settled", 0) <= entry.get("cap", -1)
                 for entry in scopes.values())
    training = value.get("training") or {}
    rows = {"unit": unit_ok, "training": any(result["cells"] > 0 for result in trains.values()),
            "acceptance": bool(accepted_ok), "consumption": consumption, "ledger": ledger}
    return {"rows": rows, "passed": all(rows.values()), "decision": decision and decision["decision"],
            "reason": decision and decision["reason"], "step_reason": value["reason"],
            "exercise": training.get("exercise", False), "rounds": training.get("rounds", []),
            "adopted": training.get("adopted", 0),
            "train_cells": sum(result["cells"] for result in trains.values()),
            "astar": len(sealed["plan"]["astar"]) if sealed else None, "cells": len(cells or []),
            "tokens": sum(_usage(c) for c in cells or []),
            "ledger": {name: {key: entry.get(key) for key in ("settled", "open", "cap")} for name, entry in
                       scopes.items()}, "step_sha256": value[protocol.RECORD_HASH]}


def s4_judged(chain_root, value, registry, items):
    """§10 S4 from the mini-step's records (``s4_ministep``): ``unit`` -- run, accept and freeze complete, each record
    named in the sealed step record; ``consumption`` -- in the drill registry every run item decided by the run unit,
    the A* items decided by the accept unit when the round decided (else released, nothing consumed) and every other
    acceptance item released, each item registered once (the redo reused its registration); ``sealing`` -- the
    decision names ``sealed.json`` and is made again from the sealed record and the cell records read back by the
    decision's block -> attempt map (``acceptance.round_cells``) alone; ``redo`` -- the accept unit's first attempt
    paused on the drill's ``SandboxUnavailable`` (kind ``sandbox``), its owner-format ``recovery.json`` labelled
    smoke, and the second attempt completed the round on the same sealed record redoing ONE block (§9.3, owner
    decision #15, ticket C7c-2): the block of the drill's stopped cell redone whole in attempt-2, every earlier block
    kept from attempt-1, every later block run in attempt-2 -- the unit's ``reused``/``redone`` and the decision's
    provenance say exactly that. The registered drill stops inside block 1 of the 4 SearchQA blocks of the 40-item
    acceptance round (``protocol.S4_DRILL_CALL``), so nothing is kept: block 1 is redone whole and blocks 2-4 run in
    attempt-2. A too-small A* (the round did not run, so the drill cannot fire) is recorded as such."""
    step_root = safe_path(chain_root) / ("s1-" + step.SMOKE_BENCH)
    records = {name: _one(step_root / name / "unit.json", "unit") for name in step.SMOKE_UNITS}
    accept_root = step_root / "accept"
    sealed = _one(accept_root / "sealed.json", "acceptance-sealed")
    tries = attempts(accept_root)
    last = accept_root / records["accept"]["attempt"] if records["accept"] else None
    decision = _one(last / "decision" / "decision.json", "decision") if last else None
    unit_ok = all(records.values()) and value["units"] == {name: rec[protocol.RECORD_HASH]
                                                          for name, rec in records.items()}
    small = decision is not None and decision["decision"] == router.SMALL
    entries = registry.entries(budgets.SMOKE, step.SMOKE_BENCH)
    run_ids = [i["task_id"] for i in items[:protocol.S4_SLICES["run"]]]
    accept_ids = [i["task_id"] for i in items[protocol.S4_SLICES["run"]:]]
    astar = set(sealed["plan"]["astar"]) if sealed and not small else set()
    decided = decision is not None and decision["decision"] in ("accept", "reject")

    def state(item, wanted, unit):
        line = entries.get(item)
        return line is not None and line["state"] == wanted and line["unit"] == unit

    path = registry.path(budgets.SMOKE, step.SMOKE_BENCH)
    lines = [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    registered = {}
    for line in lines:
        if line["state"] == "registered":
            registered[line["item_id"]] = registered.get(line["item_id"], 0) + 1
    consumption = (all(state(i, "decided", "smoke/s1-searchqa/run") for i in run_ids)
                   and all(state(i, "decided" if (i in astar and decided) else "routed_not_dispatched",
                                 "smoke/s1-searchqa/accept") for i in accept_ids)
                   and registered == {i: 1 for i in run_ids + accept_ids})
    try:  # the round's cells by the decision's block -> attempt map (§9.3, owner decision #15)
        cells = acceptance.round_cells(accept_root, sealed, decision) if sealed and decision else []
    except (OSError, ValueError):  # a block's attempt not named, or a named record missing: not reproduced
        cells = None
    sealing = (sealed is not None and decision is not None and cells is not None
               and decision["sealed"]["record"] == sealed[protocol.RECORD_HASH]
               and value["decision_sha256"] == decision[protocol.RECORD_HASH]
               and acceptance.reproduce(cells, sealed, decision))
    cells = cells or []
    first = tries[0] if tries else None
    status = _one(first / "status.json", "unit-status") if first else None
    drilled = read_json(first / "recovery.json") if first and (first / "recovery.json").exists() else None
    plan = acceptance.schedule(sealed) if sealed else {}
    blocks = [str(block) for block in plan]
    paused_block = next((str(block) for block, jobs in plan.items() for job in jobs if status is not None
                         and status["cell"] == cell_id(sealed["unit"], job["arm"], job["item"], job["run"])), None)
    result = records["accept"]["result"] if records["accept"] else {}
    kept = blocks[:blocks.index(paused_block)] if paused_block in blocks else None
    one_block = (kept is not None and len(tries) == 2
                 and result.get("reused") == {block: tries[0].name for block in kept}
                 and result.get("redone") == [paused_block]
                 and result.get("provenance") == {block: tries[0].name if block in kept else tries[1].name
                                                  for block in blocks}
                 and decision is not None
                 and {b: e["attempt"] for b, e in (decision.get("provenance") or {}).items()} == result["provenance"])
    redo = (len(tries) == 2 and status is not None and status["status"] == "paused" and status["kind"] == "sandbox"
            and recovered(first) and drilled["decision"].startswith(SMOKE_LABEL)
            and records["accept"] is not None and records["accept"]["attempt"] == tries[1].name and one_block)
    return {**s4_ministep({"unit": unit_ok, "consumption": consumption, "sealing": bool(sealing), "redo": redo}),
            "decision": decision and decision["decision"], "reason": decision and decision["reason"],
            "astar": len(astar) if sealed else None, "astar_small": small,
            "twins": len(sealed["plan"]["twins"]) if sealed else None, "attempts": [t.name for t in tries],
            "drill": None if status is None else {"attempt": first.name, "kind": status["kind"],
                                                  "cell": status["cell"], "block": paused_block},
            "blocks": blocks, "reused": result.get("reused"), "redone": result.get("redone"),
            "provenance": result.get("provenance"),
            "cells": len(cells), "tokens": sum(_usage(c) for c in cells), "step_sha256": value[protocol.RECORD_HASH]}


def write_recovery(spec, attempt, *, decision, date=None):
    """The operator's drill (§10 S4, §9.4): the owner-format ``recovery.json`` -- exactly {"by": "owner", "date",
    "decision"} (coevo5 evaluation.py:173-178) -- in a paused attempt of a mini-step unit under
    ``<root>/units/S4/s1-searchqa`` (never a confirmation unit), its decision
    text opened by ``SMOKE_LABEL``. Written once; never by ``run_stage`` (the operator's ``smoke-recovery``). Returns
    the value written."""
    spec = protocol.verified(spec, "smoke-spec")
    attempt = safe_path(attempt)
    require(attempt.is_dir() and attempt.is_relative_to(safe_path(spec["root"]) / UNITS_DIR / S4_DIR
                                                        / ("s1-" + step.SMOKE_BENCH))
            and attempt.name.startswith("attempt-") and not (attempt.parent / "unit.json").exists(),
            "A paused attempt of an S4 unit under the smoke root")
    status = _one(attempt / "status.json", "unit-status")
    require(status is not None and status["status"] == "paused", "The attempt paused")
    require(isinstance(decision, str) and decision.strip(), "The drill records the operator's decision")
    value = {"by": "owner", "date": date or datetime.date.today().isoformat(),
             "decision": "%s: %s" % (SMOKE_LABEL, decision.strip())}
    require(tuple(sorted(value)) == RECOVERY_FIELDS, "The owner format")
    write_json(attempt / "recovery.json", value)
    return value


def add_arguments(subparsers):
    """The ``smoke-recovery`` subcommand (the S4 drill's operator step)."""
    command = subparsers.add_parser("smoke-recovery", help="the S4 drill's owner-format recovery.json (§10 S4)")
    command.add_argument("--spec", required=True)
    command.add_argument("--attempt", required=True)
    command.add_argument("--decision", required=True)


def recovery_cli(args):
    """``run_execskill.py smoke-recovery --spec S --attempt A --decision TEXT``: ``write_recovery``; prints where."""
    value = write_recovery(load(args.spec), args.attempt, decision=args.decision)
    print(json.dumps({"recovery": str(safe_path(args.attempt) / "recovery.json"), **value}, sort_keys=True))
    return 0


def zebra_stage(manifest_path, chain, stage, **options):
    """The isolated zebra-pc-v1 lean smoke; no historical smoke stages or panels are implied."""
    from .zebra_smoke import run_stage
    return run_stage(manifest_path, chain, stage, **options)
