"""The two baselines (registration §11, §13.2-13.5): SkillOpt v9 and GEPA, the frozen learners of
``skillopt/continual_learning`` run unchanged, one learning unit per stage.

Stage k learns on the k-th bench's historical train part and selects on its historical val part (SpreadsheetBench: the
reference-qualified items only), from the previous stage's Skill (stage 1: the empty Skill), with the frozen learner's
own budget, Skill limit (32,000 bytes), labeled failure feedback and seed + k, as study G ran learning v9. The learner
runs in the chain process with its own 8 workers; meanwhile the unit holds 8 GLM-5.3 slots and every native slot of its
bench, so the machine-wide bounds of §13.5 still hold for every other process.

Accounting (§13.2): the stage's worst case under the frozen ledger's hard rules (93M) is reserved before the learner
starts and settled from its sealed ledger when it ends, however it ends (``ledger.settle_baseline``): reported usage
where known, else every attempt's bound. A reported usage beyond its attempt's bound, a settlement beyond the
reservation or an unreadable ledger -- a folder that cannot be listed, a record that cannot be read, fewer intents than
the learner dispatched -- breaks the reservation's assumption: the global ledger halts.

Halts (§13.4, §20.2): every dispatch of the frozen client (``CachedAPI._perform``, its only path to the provider) must
still find the global ledger at the halt generation the stage began with (``_Guard``). The first violation is latched
outside the learner's own exception handling and refuses every later dispatch; once the learner returns, the stage is
settled and the unit pauses (``assumption``, or ``ledger`` when the ledger could not be read).

Outcome: a completed run gives its Skill (``selected_update``, or ``completed_no_update`` when it kept its parent). A
pending run under one of the learner's own rules -- its call and token budget, its Skill limit, an optimizer reply it
cannot use -- keeps the parent and the chain goes on, as in study F (``pending_carry_parent``). Every other pending
reason is infrastructure (unknown costs or scores, an interruption, a crash): the unit pauses (§13.4) and an authorized
redo runs the learner afresh in the new attempt's directory. Open model or evaluation intents pause it too; an
unconfirmed native cleanup is a cleanup stop.
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import data, ledger
from .budget import OVERALL, chain_scope, step_scope
from .cells import Pause
from .outcomes import AssumptionBroken, LedgerFailure
from .protocol import BASELINE_BUDGET, BASELINE_INFLIGHT, BASELINE_LEARNING_CAP, BASELINE_SKILL_BYTES, ORDER
from .units import CHAINS, run_unit, unit_path

METHODS = {"SkillOpt-glm": "skillopt", "GEPA-glm": "gepa"}
CHECKED = "baselines-checked.json"  # in the run's shared directory: ``check`` passed for this manifest
NATIVE = {"spreadsheetbench": "spreadsheet-native", "alfworld": "alfworld-episode"}
CONFIG = ("model", "service", "repo", "gepa_source")  # the manifest's "baseline" block
# The learner's own stops (continual_learning/ledger.py, gepa.py, skillopt.py): its budget, its Skill limit, and an
# optimizer reply it cannot use (not delivered, cut at its output cap, or not one valid JSON document after its retry --
# the native bridge reports these as an incomplete reflection or optimizer).
OWN_RULES = frozenset({"max_api_calls", "max_reflection_calls", "max_metric_calls", "reported_token_stop_threshold",
                       "invalid_candidate_skill_length", "native_candidate_exceeds_skill_budget",
                       "native_optimizer_response_unknown", "reflection_unavailable", "native_reflection_incomplete",
                       "native_reflection_parse_incomplete", "native_optimizer_incomplete",
                       "earlier_native_optimizer_failure"})
OWN_PREFIXES = ("native_optimizer_json_rejected:", "native_optimizer_json_rejected_after_retry:")
STEP_KEYS = ("step", "gate_action", "wins", "losses", "ties", "net_wins", "parent_score", "candidate_score",
             "leaked_evidence", "first_pass", "confirmation_pass", "pooled_p_value", "accept_alpha_effective", "tries")
GEPA_KEYS = ("official_best_is_parent", "official_best_rejected", "final_margin", "leaked_candidates_refused",
             "parent_unknown_excluded")


def own_rule(reason):
    return reason in OWN_RULES or reason.startswith(OWN_PREFIXES)


def learning_panel(setting, bench):
    """(panel, train families, selection families) of a baseline stage: the bench's historical train part (learning)
    and val part (selection) as the frozen learner reads them, restricted to the bench's pool (SpreadsheetBench: the
    qualified items, §2.1)."""
    pinned, allowed = setting.extra["pinned"], {item["task_id"] for item in setting.pools[bench]}
    panels = {part: data._load(pinned, bench, part) for part in (data.TRAIN, data.VAL)}
    tasks = {part: [deepcopy(t) for t in panel["tasks"] if str(t["task_id"]) in allowed]
             for part, panel in panels.items()}
    require(tasks[data.TRAIN] and tasks[data.VAL],
            "%s: a baseline stage needs historical train and val items (§2.1)" % bench)
    train, selection = (sorted({t["family_id"] for t in tasks[part]}) for part in (data.TRAIN, data.VAL))
    require(not set(train) & set(selection), "Train and val families overlap")
    return {**deepcopy(panels[data.TRAIN]), "tasks": tasks[data.TRAIN] + tasks[data.VAL]}, train, selection


def frozen_manifest(setting, chain, stage, parent):
    """(the frozen learner's manifest, its panel) of a baseline stage."""
    from skillopt.continual_learning.contracts import CONFIRMATION_VERSION, manifest
    from skillopt.continual_learning.feedback import LABELED_PROFILE
    from skillopt.continual_learning.recovery import POLICY_V9

    bench = ORDER[stage - 1]
    panel, train, selection = learning_panel(setting, bench)
    value = manifest(panel, train_families=train, selection_families=selection,
                     model=deepcopy(setting.extra["baseline"]["model"]), budget=deepcopy(BASELINE_BUDGET),
                     runtime=deepcopy(setting.runtime[bench]), parent_skill=parent, seed=setting.seed + stage,
                     method=METHODS[chain], version=CONFIRMATION_VERSION, recovery_policy=deepcopy(POLICY_V9),
                     feedback_profile=LABELED_PROFILE)
    require(value["recovery_policy"]["skill_budget_bytes"] == BASELINE_SKILL_BYTES
            and value["solver_workers"] == BASELINE_INFLIGHT, "The frozen learner's interface differs from §11")
    return value, panel


def _gepa_path(source):
    """The pinned official GEPA sources are imported from their checkout (``gepa.official_gepa`` then requires them to
    be byte-identical to the reviewed commit)."""
    path = str(safe_path(source) / "src")
    if path not in sys.path:
        sys.path.insert(0, path)


def _frozen(setting, chain, value, panel, out):
    """The frozen learner (production), as study G ran it: the client must still build the frozen model service,
    and afterwards every receipt names that service (scripts/continue_fivebench_baselines)."""
    from scripts.continue_fivebench_baselines import check_client_service, verify_service
    from skillopt.continual_learning import gepa, skillopt
    from skillopt.continual_learning.launch import learning_environment
    from skillopt.continual_learning.recovery import client_options

    config = setting.extra["baseline"]
    check_client_service(config["repo"], value["model"], out.parent / "client-check", config["service"],
                         client_options=client_options(value))
    with learning_environment(value):
        if value["method"] == "gepa":
            _gepa_path(config["gepa_source"])
            result = gepa.run_stage(value, panel, out, repo=config["repo"], gepa_source=config["gepa_source"])
        else:
            result = skillopt.run_stage(value, panel, out, repo=config["repo"])
    verify_service(out, config["service"])
    return result


@contextmanager
def _held(setting, chain, bench):
    """The slots of the learner's own workers (§13.5): every native slot of its bench, then 8 GLM-5.3 slots."""
    with ExitStack() as stack:
        if bench in NATIVE:
            pool = setting.slots[NATIVE[bench]]
            stack.enter_context(pool.hold_many(pool.count))
        stack.enter_context(setting.slots[CHAINS[chain]["solver"]].hold_many(BASELINE_INFLIGHT))
        yield


class _Guard:
    """The global ledger's halt generation, checked before each dispatch of the frozen client (§13.4): the first
    violation is latched and refuses every later dispatch, whatever the learner does with the error it gets.
    ``dispatched``: the dispatches let through (the frozen ledger writes an intent before each)."""

    def __init__(self, budget, generation):
        self.budget, self.generation = budget, generation
        self.stop, self.dispatched = None, 0
        self.lock = threading.Lock()

    def check(self):
        with self.lock:
            if self.stop is None:
                try:
                    if self.budget.generation() != self.generation:
                        self.stop = AssumptionBroken("ledger_halted_since_the_attempt_began")
                except AssumptionBroken as error:
                    self.stop = error
                except Exception as error:  # noqa: BLE001 -- the ledger cannot be read: nothing more is sent
                    self.stop = LedgerFailure("ledger_failure:" + type(error).__name__)
            if self.stop is not None:
                raise type(self.stop)(str(self.stop))
            self.dispatched += 1


@contextmanager
def _guarded(guard):
    """Every dispatch of the frozen client passes ``guard`` while the learner runs (a chain process runs one learner
    at a time; evaluations run in their own processes)."""
    from skillopt.validator_pilot.api import CachedAPI

    original = CachedAPI._perform

    def perform(api, request, identifier):
        guard.check()
        return original(api, request, identifier)

    CachedAPI._perform = perform
    try:
        yield
    finally:
        CachedAPI._perform = original


def _listing(folder):
    """The JSON files of one folder of the frozen ledger: none when the folder is missing; a folder that cannot be
    listed raises (``Path.glob`` would pass over it)."""
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return []
    return sorted(folder / name for name in names if name.endswith(".json"))


def _tree(folder):
    """Every JSON file under ``folder`` (none when it is missing); a directory that cannot be read raises."""
    def fail(error):
        if not (isinstance(error, FileNotFoundError) and Path(error.filename) == folder):
            raise error
    return sorted(Path(top) / name for top, _, names in os.walk(folder, onerror=fail) for name in names
                  if name.endswith(".json"))


def _calls(root, dispatched=0):
    """[(intent, receipt or None)] from the frozen learner's sealed ledger, which holds an intent for every dispatch
    the learner made (``dispatched``)."""
    intents = _listing(root / "call_intents")
    require({p.name for p in _listing(root / "calls")} <= {p.name for p in intents}, "A receipt without intent")
    require(len(intents) >= dispatched, "The frozen ledger holds fewer intents than the learner dispatched")
    out = []
    for path in intents:
        receipt = root / "calls" / path.name
        out.append((read_json(path, sealed=True), read_json(receipt, sealed=True)["receipt"] if receipt.exists()
                    else None))
    return out


def _settle(budget, rid, root, dispatched=0):
    """Settle the stage's reservation from the frozen ledger (§13.2); a breach halts the ledger and is raised."""
    try:
        calls = _calls(root, dispatched)
        charged, broken = ledger.settle_baseline(calls)
    except Exception as error:  # noqa: BLE001 -- the ledger cannot be read: its cost is not bounded
        budget.settle(rid, BASELINE_LEARNING_CAP, detail={"unreadable": type(error).__name__},
                      breach="baseline_ledger_unreadable")
        raise AssumptionBroken("baseline_ledger_unreadable") from error
    breach = ("reported_usage_beyond_attempt_bound" if broken else
              "baseline_stage_beyond_its_worst_case" if charged > BASELINE_LEARNING_CAP else None)
    budget.settle(rid, charged, detail={"calls": len(calls)}, breach=breach)
    if breach is not None:
        raise AssumptionBroken(breach)
    return charged


def _handoff(root, result, label):
    """What the run leaves behind (scripts/continue_fivebench_baselines.require_safe_handoff, by kind): an unconfirmed
    native cleanup is a cleanup stop; an open model or evaluation intent pauses the unit."""
    from scripts.continue_fivebench_baselines import _require_cleanup

    try:  # cleanup evidence that cannot be listed or read confirms nothing
        evidence = [read_json(p, sealed=True) for p in _listing(root / "evaluations")]
        evidence += [read_json(p) for p in _tree(root / "host_only" / "scorer_artifacts")]
        _require_cleanup(evidence)
        unconfirmed = "cleanup" in str(result.get("reason"))  # also cleanup evidence the learner could not read
    except Exception:  # noqa: BLE001
        unconfirmed = True
    if unconfirmed:
        raise Pause("cleanup", "baseline_learning_cleanup_unconfirmed", label)
    try:
        intents = {p.name for p in _listing(root / "evaluation_intents")}
        closed = {p.name for p in _listing(root / "evaluations")}
    except OSError:
        raise Pause("infrastructure_incomplete", "baseline_handoff_unreadable", label) from None
    if (result.get("costs") or {}).get("unclosed_calls") != 0 or intents != closed:
        raise Pause("infrastructure_incomplete", "baseline_open_intents", label)


def learn(setting, chain_root, chain, stage, parent, *, frozen=_frozen):
    """The baseline's learning unit of the stage; returns (the stage's Skill text, the unit's record). ``frozen(setting,
    chain, manifest, panel, output)`` runs the frozen learner (tests inject the frozen learner's fixtures)."""
    from scripts.continue_fivebench_baselines import transition

    require(chain in METHODS, "Not a baseline chain")
    bench = ORDER[stage - 1]
    identity = {"unit": "%s/s%d/learning" % (chain, stage), "chain": chain, "stage": stage, "benchmark": bench,
                "parent_sha256": digest(parent)}
    label = identity["unit"]

    def work(attempt):
        generation = setting.budget.generation()
        value, panel = frozen_manifest(setting, chain, stage, parent)
        write_json(attempt / "manifest.json", value)
        out = attempt / "learning"
        with _held(setting, chain, bench):
            rid = setting.budget.reserve((OVERALL, chain_scope(chain), step_scope(chain, stage, "learning")),
                                         BASELINE_LEARNING_CAP, label=label, generation=generation)
            guard = _Guard(setting.budget, generation)
            try:
                with _guarded(guard):
                    result = frozen(setting, chain, value, panel, out)
            except Exception:
                if guard.stop is None:
                    raise
            finally:
                charged = _settle(setting.budget, rid, out, guard.dispatched)
        if guard.stop is not None:  # the learner went on or ended its own way: the halt pauses the unit
            raise guard.stop
        _handoff(out, result, label)
        state = transition(parent, result, BASELINE_SKILL_BYTES)
        if not state["learning_completed"] and not own_rule(result["reason"]):
            raise Pause("infrastructure_incomplete", "baseline_pending:%s" % result["reason"][:200], label)
        return {"skill": state["skill"], "action": state["action"], "status": result["status"],
                "reason": result["reason"], "skill_sha256": hashlib.sha256(state["skill"].encode()).hexdigest(),
                "skill_bytes": len(state["skill"].encode()), "learning_result_hash": result["record_hash"],
                "manifest_hash": value["record_hash"], "charged": charged, "costs": result["costs"],
                "accepted_steps": result.get("accepted_steps"),
                "steps": [{k: s.get(k) for k in STEP_KEYS} for s in result.get("steps", [])],
                **{k: result[k] for k in GEPA_KEYS if k in result},
                "train_tasks": sum(t["family_id"] in value["train_families"] for t in panel["tasks"]),
                "selection_tasks": sum(t["family_id"] in value["selection_families"] for t in panel["tasks"])}

    record = run_unit(unit_path(chain_root, stage, "learning"), run=setting.run, identity=identity, work=work)
    return record["result"]["skill"], record


def check(setting):
    """Zero model calls, before launch: every baseline stage's frozen manifest builds on the pinned data (families,
    roles, assets, runtime), the native runtimes are ready, the client still builds the frozen model service, and the
    pinned GEPA sources are installed as reviewed. Returns {chain: {bench: sizes}}, recorded in the run (``CHECKED``):
    no chain runs before (§2.1, §14)."""
    from scripts.continue_fivebench_baselines import check_client_service
    from skillopt.continual_eval import backends
    from skillopt.continual_learning.gepa import official_gepa
    from skillopt.continual_learning.recovery import client_options

    config = setting.extra["baseline"]
    require(set(config) == set(CONFIG), "The manifest's baseline block")
    _gepa_path(config["gepa_source"])
    official_gepa(config["gepa_source"])
    found = {}
    for chain in METHODS:
        for stage, bench in enumerate(ORDER, 1):
            value, panel = frozen_manifest(setting, chain, stage, "")
            require(backends.readiness(bench, value["runtime"])["status"] == "ready", "%s runtime not ready" % bench)
            found.setdefault(chain, {})[bench] = {"tasks": len(panel["tasks"]),
                                                  "train_families": len(value["train_families"]),
                                                  "selection_families": len(value["selection_families"])}
    probe = safe_path(setting.shared) / "host_only" / "baseline-client-check"
    check_client_service(config["repo"], value["model"], probe, config["service"], client_options=client_options(value))
    path = safe_path(setting.shared) / CHECKED
    if path.exists():
        require(read_json(path, sealed=True)["run"] == setting.run, "A baseline check of another run")
    else:
        write_json(path, seal({"run": setting.run, "found": found}))
    return found


def checked(setting):
    """Whether ``check`` passed for this run."""
    path = safe_path(setting.shared) / CHECKED
    return path.exists() and read_json(path, sealed=True)["run"] == setting.run
