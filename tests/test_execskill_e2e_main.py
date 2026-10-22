"""The end-to-end zero-API five-bench main experiment (registrar addendum 2026-10-22, "Owner instructions 17:0x and
17:3x"; integration phase M): configuration ``main`` -- SearchQA -> OfficeQA -> LiveMath -> SpreadsheetBench ->
ALFWorld -- run as chains G and D through ``chain.run`` with the real ``step.learn``, then the five-unit test read under
the owner's consent, the owner's continuation file and the unseal. Offline and deterministic; everything is an
engineering fixture, never method-effect evidence:

- the slices are cut small (``supply.registered_sizes`` patched: SearchQA run 20 + tail acceptance 40, LiveMath run
  8 + 4 / acceptance 30 / J7 probe 8, SpreadsheetBench 12 / 30, ALFWorld 8 / 16 whole-room games; OfficeQA keeps its
  registered 24 / 50); the registered sizes are covered by tests/test_execskill_fivebench_step.py and the pilot e2e;
- the solvers are scripted gateways behind the REAL clients built from a sealed main manifest
  (``manifest.solver_config``): chain G glm-5.3, chain D route A elucid and route B northgate (deepseek-v4-flash);
  the method roles are FakeGLM behind the real ``Roles``; the cells' procedures are FakeSandbox hooks computing what
  the engineer's sources compute (the engineer's checks, detectors and describer run the real sandbox worker through
  FakeDocker); SpreadsheetBench programs run through FakeNative with a fixture verdict; ALFWorld games are FakeAlfEnv
  episodes with their pre-reset routing views made on the pinned runtime;
- SearchQA's acceptance slice comes from a pinned tail supply through its persisted test exclusion; the engineer
  writes one procedure per QA bench and SpreadsheetBench (SearchQA: the context's town; OfficeQA: the pilot's three
  changes of which one survives; LiveMath: f''(1) from the stem, so the J7 options-only probe sees no gain;
  SpreadsheetBench: the pilot's repair feedback) and none on ALFWorld.

Chain G runs first: its cost check after the SearchQA run unit records a breach (12,010 ledger tokens per cell over
3 x 3,400) and never pauses (``COST_CHECK_PAUSES["main"]``); the read gate prices G's part by that factor. Chain D runs
on route A until elucid refuses its first OfficeQA call for exhausted balance (HTTP 402): the run unit pauses with
kind ``balance_exhausted``; the operator's ``switch-route --manifest M --chain D --to B`` writes ``route-1.json`` and
prints the ``recover`` and ``run`` commands; ``recover`` records the owner's decision; the relaunched ``run`` binds
route B (branch N), confirms route B's own first reply (``confirm-route-B.json``), redoes the paused unit whole on
route B (``D:redo``) and continues to the end. The test read is real on OfficeQA; the other four read units are
stand-in records (their test panels need the test qualification or the ALFWorld environment).
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import io
import itertools
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_execskill as cli
from skillopt.coevo5.budget import Budget
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, chain, client, engineer, evaluation, examiner, manifest, protocol, rounds,
                                routes, slots, solver, step, supply, units)
from skillopt.execskill.cells import Arm
from skillopt.execskill.client import ELUCID_MODEL, GLM_SOLVER, NORTHGATE_MODEL
from skillopt.execskill.package import FIXTURE, empty, load
from skillopt.execskill.protocol import (BENCHES, CANARIES, CHAINS, FIRST_CALL_USER, NOTES_KEY, RECORD_HASH,
                                         ledger_bound, record, verified)
from skillopt.execskill.registry import Registry
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.validator_pilot.api import digest
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import FakeGLM, FakeProvider, Reply, engineer_reply, fake_config, tagged, usage
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeAlfEnv, FakeSandbox, alf_sessions
from tests.fixtures.execskill.items import TASK_TYPES, livemath_items, spreadsheetbench_items
from tests.test_execskill_e2e import (CONCEPTS, OQ_ITEMS, SECOND_TABLE, TEST_ITEMS, Answers, Native, canary_panel,
                                      column_a, descriptions, docker_workers, even, filler, panel, pool_pins,
                                      sheet_change, sheet_score)
from tests.test_execskill_e2e import HOOKS as PILOT_HOOKS
from tests.test_execskill_e2e import SHEET as SHEET_SOURCE
from tests.test_execskill_e2e import YEARS_ID
from tests.test_execskill_e2e import roles_answer as pilot_roles
from tests.test_execskill_evaluation import consent_value
from tests.test_execskill_fivebench_step import _persist_exclusion, _searchqa
from tests.test_execskill_integration_b3 import CARD, SHEET_RUNTIME
from tests.test_execskill_integration_b4 import new
from tests.test_execskill_manifest import MEASURED, fake_environment, given
from tests.test_execskill_replay import source, test_case
from tests.test_execskill_routes import northgate_env

SQ, OQ, LM, SB, ALF = BENCHES
SQ_ID, LM_ID, SB_ID = "fx-searchqa-1-1", "fx-livemath-3-1", "fx-spreadsheetbench-4-1"  # (bench, step, change)
G_TOKENS = 12_000  # chain G's reported completion per SearchQA cell: 12,010 ledger tokens > 3 x 3,400 (a breach)
SIZES = {SQ: {"smoke": 10, "run": 20}, OQ: {"run": 24, "accept": 50},
         LM: {"run_absent": 8, "run_present": 4, "accept": 30, "accept_probe": 8},
         SB: {"run": 12, "accept": 30}, ALF: {"smoke": 2, "run": 8, "accept": 16, "select": 10}}
TAIL_SIZE, TAIL_DROPPED = 40, 6  # SearchQA's tail acceptance slice; the tail items its test exclusion drops
DECISION = "redo on route B: owner instruction 2026-10-22 17:3x, second deepseek provider"
TOWN = """
import re

def applies(view):
    return "Fixtown" in str(view.get("context", ""))

def before_call(view, state):
    found = re.search(r"is kept in (Fixtown [0-9]+)", str(view.get("context", "")))
    if not found:
        return None
    return {"facts": ["Kept in " + found.group(1) + " (from the context)."]}
"""
DERIVATIVE = """
def applies(view):
    return "f(x) = x^" in str(view.get("question", ""))

def before_call(view, state):
    question = str(view.get("question", ""))
    if "f(x) = x^" not in question:
        return None
    digits = ""
    for char in question.split("f(x) = x^", 1)[1]:
        if not char.isdigit():
            break
        digits = digits + char
    if not digits:
        return None
    k = int(digits)
    return {"facts": ["f''(1) = " + str(k * (k - 1)) + " for f(x) = x^" + digits + "."]}
"""


def small_sizes(bench, part="pool"):
    """``supply.registered_sizes`` for this fixture: the registered slice names at small counts."""
    return {"accept": TAIL_SIZE} if part == "tail" else dict(SIZES[bench])


def town(context):
    """What the TOWN procedure writes for a SearchQA context (the same text as its source)."""
    found = re.search(r"is kept in (Fixtown [0-9]+)", context)
    return "Kept in %s (from the context)." % found.group(1) if found else None


def derivative(question):
    """What the DERIVATIVE procedure writes for a LiveMath stem (the same text as its source)."""
    found = re.search(r"f\(x\) = x\^([0-9]+)", question)
    if not found:
        return None
    k = int(found.group(1))
    return "f''(1) = %d for f(x) = x^%d." % (k * (k - 1), k)


def note(fact):
    return {"facts": [fact]} if fact else None


HOOKS = {
    SQ_ID: {"applies": lambda view: "Fixtown" in str(view.get("context", "")),
            "before_call": lambda view, state: note(town(str(view.get("context", ""))))},
    YEARS_ID: PILOT_HOOKS[YEARS_ID],
    LM_ID: {"applies": lambda view: "f(x) = x^" in str(view.get("question", "")),
            "before_call": lambda view, state: note(derivative(str(view.get("question", ""))))},
    SB_ID: {"applies": lambda view: "workbook_preview" in view,
            "sheet_feedback": lambda view, report, state: (
                {"fields": {"warnings": [column_a(view)]}, "request_repair": True}
                if report.get("status") == "exception" and report.get("message") else None)}}
SHEET = SHEET_SOURCE.replace(
    'return "workbook_preview" in view or str(view.get("question", "")).startswith("What is the")',
    'return "workbook_preview" in view')


# ------------------------------------------------------------------------------------------------ the fixtures
def alfworld_pool(root, runtime, *, rooms=27, per_room=3):
    """Fresh-supply ALFWorld pool items in the bench's order: ``rooms`` rooms of ``per_room`` short games, each game
    file holding its FakeAlfEnv episode, with its pre-reset routing view and the digest of the runtime it was made
    with (``supply.alfworld_pool``'s shape). 27 rooms give the room groups smoke 1, run 4, acceptance 10."""
    items = []
    for r in range(rooms):
        room = str(401 + r)
        for g in range(per_room):
            n, thing = r * per_room + g, ("apple", "mug", "book")[g]
            task_type = TASK_TYPES[n % len(TASK_TYPES)]
            plan = ["go to countertop 1", "take %s 1 from countertop 1" % thing, "put %s 1 in/on fridge 1" % thing]
            game = {"task_id": "fx-alfworld-%03d" % n, "room": room, "task_type": task_type,
                    "gamefile": "json_2.1.1/train/%s-%s-None-Fridge-%s/trial_T2020%04d_fixture/game.tw-pddl"
                                % (task_type, thing.capitalize(), room, n),
                    "initial_observation": "-= Welcome to TextWorld, ALFRED! =-\n\nYou are in room %s. You see a "
                                           "countertop 1 and a fridge 1.\n\nYour task is to: put a %s in fridge."
                                           % (room, thing),
                    "admissible_commands": ["go to countertop 1", "go to fridge 1", "look", "inventory"],
                    "plan": plan, "won_at": len(plan), "expert_plan": list(plan),
                    "terminal_observation": "You put the %s 1 in/on the fridge 1. You won!" % thing,
                    "extra": {"gamefile": "hidden", "expert_plan": list(plan)}}
            path = Path(root) / game["gamefile"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(game, sort_keys=True), encoding="utf-8")
            observations, _, infos = FakeAlfEnv(game).reset()
            view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
            items.append({"benchmark": ALF, "task_id": game["task_id"], "family_id": game["task_id"], "part": "fresh",
                          "room": room, "task_type": task_type,
                          "public": {"game_file": str(path), "routing_view": view, "routing_view_sha256": digest(view)},
                          "private": {"game_metadata": {"source_split": "train", "task_type": task_type,
                                                        "asset_files": []}},
                          "views_runtime_sha256": digest(runtime)})
    return supply.order(ALF, items)


class MainAnswers(Answers):
    """Every solver of both chains (``answer(system, user)``), the same replies in every arm, run and route: the
    pilot's OfficeQA and SpreadsheetBench rules; SearchQA right when the notes carry the item's own TOWN note, else on
    even keys; LiveMath the keyed letter when the notes carry the stem's own DERIVATIVE note, else on even options (an
    options-only J7 probe cell has no stem: the procedure never fires there); ALFWorld the next plan step (the fake
    game's last admissible command), so every game is won."""

    def __init__(self, items, livemath):
        super().__init__(items)
        self.letters = {item["public"]["choices"]: item["private"]["answer"] for item in livemath}

    def __call__(self, system, user):
        if user == FIRST_CALL_USER:
            return "ready"
        if system.startswith(solver.ALF_SYSTEM):
            return "<action>%s</action>" % json.loads(user)["admissible_commands"][-1]
        view = json.loads(user)
        notes = view.get(NOTES_KEY, "")
        if "choices" in view:
            own, letter = derivative(view.get("question", "")), self.letters[view["choices"]]
            right = (own is not None and own in notes) or even(view["choices"])
            return tagged(letter if right else "ABCDE"[("ABCDE".index(letter) + 1) % 5])
        if "Fixtown" in str(view.get("context", "")):
            context = str(view["context"])
            right = town(context) in notes or even(view["question"] + context)
            return tagged(re.search(r"is kept in (Fixtown [0-9]+)", context).group(1) if right else "Nowhere")
        return super().__call__(system, user)


def is_searchqa(user):
    return user != FIRST_CALL_USER and user.startswith("{") and "Fixtown" in str(json.loads(user).get("context", ""))


def main_roles(system, payload):
    """The pilot's scripted GLM-5.3 roles, plus: LiveMath's policy names a family and requests no research (no
    material, no generated item); the engineer writes TOWN on SearchQA, DERIVATIVE on LiveMath and nothing on
    ALFWorld (the pilot's changes on OfficeQA and SpreadsheetBench)."""
    bench = payload.get("bench") if isinstance(payload, dict) else None
    if system == examiner.POLICY_SYSTEM and bench == LM:
        return {"families": ["livemath.derivative"], "rationale": "Calculus stems.", "requests": []}
    if system == engineer.ENGINEER_SYSTEM and payload["request"] != "fix":
        if bench == ALF:
            return engineer_reply({"changes": []}, [])
        if bench in (SQ, LM, SB):
            failing = next(t["cell"] for t in payload["trajectories"] if t["kind"] == "failures")
            if bench == SB:
                return engineer_reply({"changes": [sheet_change(failing)]}, [source(SHEET)])
            if bench == SQ:
                test = test_case(failing, "before_call", {"kind": "note_contains", "value": "Kept in Fixtown"},
                                 mutation="strip_digits")
                return engineer_reply({"changes": [new("Names the town the context keeps the bell in.", test)]},
                                      [source(TOWN)])
            test = test_case(failing, "before_call", {"kind": "note_contains", "value": "f''(1) = "},
                             mutation="strip_digits")
            return engineer_reply({"changes": [new("States f''(1) for the stem's power function.", test)]},
                                  [source(DERIVATIVE)])
    return pilot_roles(system, payload)


@contextmanager
def item_workers(package, item):
    """The router's and the donors' factory: a started FakeSandbox with the cells' procedures."""
    worker = FakeSandbox(HOOKS).start(package, kind="cell")
    try:
        yield worker
    finally:
        worker.close()


class MainRead:
    """The read children of both chains, in process (``chain.evaluate`` starts all five): the OfficeQA unit for real,
    the other four stand-in records."""

    def __init__(self, pins):
        self.pins, self.launched = pins, []

    def launch(self, setting_, spec):
        unit_root, name = Path(spec["unit_root"]), spec["chain"]
        self.launched.append((name, spec["bench"]))
        if spec["bench"] != OQ:  # a stand-in unit: it names its run, chain and package like a real one
            unit_root.mkdir(parents=True, exist_ok=True)
            write_json(unit_root / "unit.json", record("evaluation", FIXTURE, {
                "run": setting_.run, "chain": name, "bench": spec["bench"],
                "packages": {"F": spec["package_sha256"]}, "stand_in": True}))
            return chain.EXIT_COMPLETE
        chain_root = chain.chain_root(setting_, name)
        final = load(chain_root / "packages" / (spec["package_sha256"] + ".json"))
        model = CHAINS[name]
        bound = ledger_bound(model, OQ, branch=None if name == "G" else setting_.branch,
                             longest=None if name == "G" else setting_.longest)
        endpoint = budgets.endpoint(setting_, budgets.solver_scopes(name, None, None, "test"),
                                    client=setting_.clients(model, OQ), max_tokens_bound=bound)
        context = units.cell_context(setting_, unit_root / "attempt-1", endpoint)

        def placebo(cell, task):
            return Arm("placebo_y", final, placebo={"procedures": {
                YEARS_ID: {"before_call": {"facts": ["Customs receipts by year: a donor's table."]}}},
                "seed": "seed:" + cell["id"]})

        arms = {"F": Arm("candidate", final), "C": Arm("card", empty(step="%s/card" % name, evidence=FIXTURE)),
                "P_F": placebo, "T_F": Arm("text", final, text=descriptions(chain_root))}
        evaluation.make_read_canaries(setting_.root, None, pools=self.pins, run=setting_.run, evidence=FIXTURE,
                                      panel=canary_panel, order=protocol.order_of(setting_))
        evaluation.evaluate(unit_root, run=setting_.run, shared=setting_.shared, pinned=None, chain=name, bench=OQ,
                            arms=arms, context=context, workers=1, route_workers=item_workers,
                            canaries=evaluation.load_canaries(setting_.root, read=True), panel=panel)
        return chain.EXIT_COMPLETE


def searchqa_supply(tmp, root):
    """The SearchQA pool (smoke 10 at the end of its order + run 20 + spare) and the pinned tail supply with its
    persisted test exclusion, which drops the first ``TAIL_DROPPED`` items of the tail order."""
    pool = supply.order(SQ, [_searchqa(n, "train") for n in range(40)])
    tail = [{**_searchqa(n, "tail"), "position": protocol.SEARCHQA_TAIL_START + n} for n in range(60)]
    dropped = [i["task_id"] for i in supply.order(SQ, tail)[:TAIL_DROPPED]]
    path = supply.write_supply(tmp / "history-supply", supply.supply_record(
        "searchqa-tail", SQ, tail, sources={"fixture": True}, evidence="smoke"))
    bound, value = _persist_exclusion(root, tail, dropped)
    pin = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
           "exclusion": {"path": str(bound), "record_sha256": value[RECORD_HASH]}}
    return pool, tail, dropped, pin


def main_manifest(tmp, root):
    """A sealed manifest of configuration ``main`` on ``root`` (zero calls) whose clients block pins chain D's route
    B: the solver configs of the e2e's clients (``manifest.solver_config``) and the run id ``switch-route`` reads."""
    elucid, glm = fake_config(tmp, ELUCID_MODEL), fake_config(tmp, GLM_SOLVER)
    solvers = {"D": manifest.solver_block("D", env_path=elucid["env_path"], branch="E"),
               "G": manifest.solver_block("G", env_path=glm["repo"])}
    clients = {"solver": solvers, "roles": dict(manifest.ROLES),
               "routes": {"D": {"B": routes.pin("D", "B", env_path=northgate_env(tmp), solver_block=solvers["D"])}}}
    path = tmp / "main-manifest.json"
    found = manifest.make(path, evidence=FIXTURE, environment_found=fake_environment(), measured=MEASURED,
                          configuration=protocol.MAIN, **{**given(tmp), "root": str(root), "clients": clients})
    return found, path


def captured(argv):
    """``run_execskill.py`` in process: (exit code, its stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


# --------------------------------------------------------------------------------------------- the main run
@pytest.fixture(scope="module")
def main(tmp_path_factory):
    """Run chain G, then chain D (route A -> balance pause -> switch-route B -> recover -> route B), each through the
    five steps and the five-unit read; then the continuation file and the unseal."""
    tmp = tmp_path_factory.mktemp("e2e-main")
    root, shared = tmp / "root", tmp / "root" / "shared"
    shared.mkdir(parents=True)
    write_json(shared / "consent.json", consent_value())
    found, counts = evaluation.select_canaries({"alfworld": filler("alfworld"), "searchqa": filler("searchqa")})
    write_json(root / CANARIES, record("test-canaries", FIXTURE, {"canaries": found, "counts": counts}))
    m, manifest_path = main_manifest(tmp, root)
    run = m[RECORD_HASH]
    runtime = {**RUNTIME, SB: SHEET_RUNTIME}
    sq_pool, tail, dropped, tail_pin = searchqa_supply(tmp, tmp / "smoke-root")
    lm_items = supply.order(LM, livemath_items(60))
    sb_items = supply.order(SB, spreadsheetbench_items(tmp / "sheets", 42))
    pools = {SQ: sq_pool, OQ: OQ_ITEMS, LM: lm_items, SB: sb_items, ALF: alfworld_pool(tmp / "games", runtime[ALF])}
    pins = pool_pins(tmp / "pools", pools)
    answers = MainAnswers(OQ_ITEMS + TEST_ITEMS, lm_items)

    def g_answer(system, user):  # chain G: a long reported completion on SearchQA (its cost check breaches)
        reply = answers(system, user)
        return Reply(text=reply, usage=usage(G_TOKENS)) if is_searchqa(user) else reply

    exhausted = []

    def route_a(system, user):  # chain D on elucid: the balance runs out at its first OfficeQA call
        if user != FIRST_CALL_USER and "Year |" in user:
            exhausted.append(user)
            return Reply(text=None, usage=None, failure="http_402")
        return answers(system, user)

    providers = {("G", None): FakeProvider(GLM_SOLVER, g_answer), ("D", "A"): FakeProvider(ELUCID_MODEL, route_a),
                 ("D", "B"): FakeProvider(NORTHGATE_MODEL, answers)}
    glms = {name: FakeGLM(tmp / ("glm-" + name), main_roles) for name in CHAINS}
    built = {}

    def clients(name, route=None):
        def client_of(model, bench):
            if bench is None:
                return glms[name].client
            if (name, route, bench) not in built:
                built[(name, route, bench)] = client.solver_client(
                    model, config=manifest.solver_config(m, name, bench, route),
                    transport=providers[(name, route)].transport)
            return built[(name, route, bench)]
        return client_of

    ledgers = {name: Budget(budgets.ledger_root(root, name), sleep=lambda _: None) for name in CHAINS}
    pool_slots = slots.pools(tmp / "slots", poll=0.01, log=lambda line: None)
    ticks, waited = itertools.count(), []

    def clock():  # advanced by the dispatch's wait between OfficeQA's time blocks (§3.3)
        return float(next(ticks)) + sum(waited)

    base = units.Setting(
        run=run, root=root, shared=shared, pools=pools, cards={b: CARD for b in BENCHES}, runtime=runtime,
        clients=None, budget=None, slots=pool_slots, sandbox={}, evidence=FIXTURE, workers=1, cooldown=0,
        extra={"verify": lambda: None, "slot_root": str(tmp / "slots"), "configuration": protocol.MAIN,
               step.TAIL: tail_pin, "test_read_estimate": {"G": 10 ** 6, "D": 10 ** 6}})
    settings = {"G": replace(base, clients=clients("G"), budget=ledgers["G"]),
                "D": replace(base, clients=clients("D", "A"), budget=ledgers["D"], branch="E",
                             extra={**base.extra, "route": "A"})}
    docker = FakeDocker(tmp / "containers")
    registry = Registry(tmp / "history", evidence=FIXTURE)
    research_root = tmp / "research"
    results, switched = {}, {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(fake_research.PAGES, "Public finance", ("Public finance", 1007, SECOND_TABLE, [], False))
        patch.setitem(fake_research.SEARCHES, CONCEPTS[1], ["Public finance"])
        Native().install(patch)
        sessions = alf_sessions(patch)
        patch.setattr(backends, "score", sheet_score(backends.score))
        patch.setattr(supply, "registered_sizes", small_sizes)
        real_context = units.cell_context

        def context(setting_, attempt, endpoint):
            made = real_context(setting_, attempt, endpoint)
            made.worker, made.clock = (lambda bench: FakeSandbox(HOOKS)), clock
            return made

        patch.setattr(units, "cell_context", context)
        patch.setattr(rounds, "cell_context", context)
        made_by = examiner.build

        def known(*args, **kwargs):  # the fake solver learns the generated items' answers
            built_ = made_by(*args, **kwargs)
            answers.add(built_.items)
            return built_

        patch.setattr(examiner, "build", known)
        patch.setattr(examiner, "BAND_PROBE_ITEMS", 4)  # the four-item OQ set's band probe (Codex finding #9)
        services = step.Services(registry=registry, sources=fake_research.sources(research_root)[0],
                                 workers=docker_workers(docker, tmp), item_workers=item_workers, clock=clock,
                                 sleep=waited.append)
        reader = MainRead(pins)
        learn = functools.partial(step.learn, services=services)
        results["G"] = chain.run(settings["G"], "G", learn=learn, launch=reader.launch)
        results["D-route-A"] = chain.run(settings["D"], "D", learn=learn, launch=reader.launch)
        # the operator (main-runbook 8.1): chain D idle after its EXIT 3 -> switch-route -> recover -> run
        code, shown = captured(["switch-route", "--manifest", str(manifest_path), "--chain", "D", "--to", "B"])
        switched = {"code": code, **json.loads(shown)}
        recovered = []
        for command in switched["next"]:
            if " recover " in command:
                attempt = re.search(r"--attempt (\S+)", command).group(1)
                recovered.append((attempt, captured(["recover", "--attempt", attempt, "--decision", DECISION])[0]))
        block = routes.block_of(m, "D", "B")  # what setting_of binds for route B (registrar row "deepseek route B")
        settings["D"] = replace(settings["D"], clients=clients("D", "B"), branch=block["branch"],
                                longest=block["longest"], extra={**settings["D"].extra, "route": "B"})
        results["D"] = chain.run(settings["D"], "D", learn=learn, launch=reader.launch)
    docker.close()

    # the owner's continuation file (an exploratory run: no formal addendum), then the unseal
    write_json(shared / "owner-continuation.json",
               {"by": "owner", "date": "2026-10-22", "decision": "continue", "note": "fixture: the main experiment"})
    opened, labels = {}, {}
    for name in CHAINS:
        labels[name] = evaluation.continuation_check({"root": str(root)}, chain=name,
                                                     clock=lambda: "2026-10-22T23:00:00Z")["label"]
        opened[name] = evaluation.unseal(root, root / name, name, [chain.unit_root(settings[name], name, OQ)],
                                         run=run, evidence=FIXTURE, clock=lambda: "2026-10-22T23:00:00Z")
    return SimpleNamespace(root=root, tmp=tmp, run=run, results=results, switched=switched, recovered=recovered,
                           settings=settings, ledgers=ledgers, providers=providers, exhausted=exhausted,
                           registry=registry, sessions=sessions, reader=reader, labels=labels, opened=opened,
                           tail=tail, dropped=dropped, pools=pools)


def step_record(chain_root, k, bench):
    return verified(read_json(chain_root / ("s%d-%s" % (k, bench)) / step.STEP_FILE), "step")


def unit_result(chain_root, k, bench, name):
    return verified(read_json(units.unit_path(chain_root, k, bench, name) / "unit.json"), "unit")


def cell_records(attempt):
    return [read_json(path) for path in sorted((attempt / "cells").glob("*.json"))]


# ---------------------------------------------------------------------------------------------------- the chains
def test_both_chains_run_mains_five_steps_and_accept_four_procedures(main):
    assert main.results["G"] == main.results["D"] == {"status": "complete"}
    for name in CHAINS:
        chain_root = main.root / name
        started = verified(read_json(chain_root / "chain.json"), "chain")
        assert (started["order"], started["configuration"]) == (list(BENCHES), "main")
        done = verified(read_json(chain_root / "chain-complete.json"), "chain-complete")
        steps = [step_record(chain_root, k, bench) for k, bench in enumerate(BENCHES, 1)]
        assert done["steps"] == [value[RECORD_HASH] for value in steps]
        assert [value["decision"] for value in steps] == ["accept"] * 4 + ["not_run"], [
            (value["decision"], value["reason"]) for value in steps]
        assert steps[-1]["reason"] == "no_surviving_change" and steps[-1]["candidate_sha256"] is None
        final = load(chain_root / "packages" / (done["package_sha256"] + ".json"))
        assert final.order == (SQ_ID, YEARS_ID, LM_ID, SB_ID)
        for k, bench in enumerate(BENCHES, 1):  # every step ran its run, diagnose, generate, engineer and freeze
            assert {"run", "diagnose", "generate", "engineer", "freeze"} <= set(steps[k - 1]["units"])
            assert ("accept" in steps[k - 1]["units"]) == (bench != ALF)


def test_searchqa_runs_on_its_pool_and_accepts_on_the_kept_tail(main):
    for name in CHAINS:
        cut = read_json(main.root / name / "s1-searchqa" / step.SLICES_FILE)["slices"]
        tail = {i["task_id"] for i in main.tail}
        assert len(cut["run"]) == 20 and set(cut["run"]) <= {i["task_id"] for i in main.pools[SQ]}
        assert len(cut["accept"]) == TAIL_SIZE and set(cut["accept"]) <= tail and not set(main.dropped) & set(
            cut["accept"])


def test_livemath_cuts_its_j7_probe_and_runs_it_options_only(main):
    for name in CHAINS:
        cut = read_json(main.root / name / "s3-livemath" / step.SLICES_FILE)["slices"]
        assert {len(ids) for key_, ids in cut.items() if key_ == "accept_probe"} == {8}
        probe = set(cut["accept_probe"])
        stems = {i["task_id"]: i["public"]["question"] for i in main.pools[LM]}
        accepted = unit_result(main.root / name, 3, LM, "accept")
        attempt = units.unit_path(main.root / name, 3, LM, "accept") / accepted["attempt"]
        sent = [c for c in cell_records(attempt) if c["cell"].get("source_item", c["cell"]["task_id"]) in probe
                or c["cell"]["task_id"] in probe]
        assert sent and all(stems[c["cell"]["task_id"]] for c in sent)  # the stems exist in the pool ...
        assert not any(derivative(stems[c["cell"]["task_id"]]) in json.dumps(c) for c in sent)  # ... never noted
        guard = read_json(attempt / "decision" / "decision.json")["guards"]["J7_meta"]  # the probe's 8 items judged
        assert guard["n"] == 8 and guard["ok"] is True and guard["gain"] == 0.0


def test_the_self_tests_of_steps_three_and_four_run_officeqas_set_on_its_own_endpoint(main):
    for name in CHAINS:
        for k, bench in ((3, LM), (4, SB)):
            tested = unit_result(main.root / name, k, bench, "selftest")["result"]
            assert set(tested["sets"]) == {OQ} and tested["cells"] == 2 * tested["sets"][OQ]["items"] > 0
            assert not tested["blocked"]


def test_alfworld_runs_whole_room_slices_of_the_fresh_supply_on_the_pinned_views(main):
    rooms = {i["task_id"]: i["room"] for i in main.pools[ALF]}
    for name in CHAINS:
        cut = read_json(main.root / name / "s5-alfworld" / step.SLICES_FILE)["slices"]
        assert len(cut["run"]) == 8 and len(cut["accept"]) == 16
        assert not {rooms[i] for i in cut["run"]} & {rooms[i] for i in cut["accept"]}
        ran = unit_result(main.root / name, 5, ALF, "run")["result"]
        assert ran["cells"] == 8
    assert main.sessions and all(session.closed for session in main.sessions)


# --------------------------------------------------------------------------------------- chain G's cost check
def test_chain_g_cost_check_records_its_breach_and_never_pauses_and_the_read_gate_applies_the_factor(main):
    check = verified(read_json(main.root / "G" / chain.CAP_CHECK), "cap-check")
    assert (check["ok"], check["pauses"], check["configuration"]) == (False, False, "main")
    assert check["per_cell"] / check["anchor_high"] > protocol.MAIN_CAP_FACTOR
    assert not list((main.root / "G").glob("cap-check-G-*.json"))  # one check, no pause, no owner raise
    read = verified(read_json(main.root / "G" / chain.TEST_READ), "test-read")
    assert read["status"] == "read" and read["gate"]["factor"] == pytest.approx(
        check["per_cell"] / check["anchor_high"])
    assert read["gate"]["used"] > 3 * read["gate"]["estimate"]


# ------------------------------------------------------------------------------------------ chain D's route B
def test_chain_d_pauses_on_balance_exhaustion_switches_to_route_b_and_redoes_the_unit_there(main):
    assert main.results["D-route-A"]["status"] == "paused"
    assert main.results["D-route-A"]["kind"] == "balance_exhausted" == routes.BALANCE_EXHAUSTED
    assert len(main.exhausted) == 1  # never retried, nothing sent after the refusal
    chain_root = main.root / "D"
    paused = units.unit_path(chain_root, 2, OQ, "run") / "attempt-1"
    status = verified(read_json(paused / "status.json"), "unit-status")
    assert status["kind"] == "balance_exhausted" and read_json(paused / "recovery.json")["decision"] == DECISION
    assert main.switched["code"] == 0 and (main.switched["from"], main.switched["to"]) == ("A", "B")
    assert main.switched["paused_attempt"] == str(paused) and main.recovered == [(str(paused), 0)]
    history = verified(read_json(chain_root / "route-1.json"), routes.KIND)
    assert history["pause"]["attempt"] == "s2-officeqa/run/attempt-1" and history["run"] == main.run
    assert routes.current(chain_root, run=main.run) == "B" and not (chain_root / "route-2.json").exists()
    first = verified(read_json(chain_root / chain.CONFIRM), "first-call")
    second = verified(read_json(chain_root / (chain.CONFIRM_ROUTE % "B")), "first-call")
    assert first["passed"] and second["passed"] and second["identity"] == {"run": main.run, "chain": "D",
                                                                            "route": "B"}
    assert second["returned_model"] == NORTHGATE_MODEL
    redone = unit_result(chain_root, 2, OQ, "run")
    assert redone["attempt"] == "attempt-2"
    cells = cell_records(units.unit_path(chain_root, 2, OQ, "run") / "attempt-2")
    assert cells and all(c["solver_route"] == {"route": "B", "model": NORTHGATE_MODEL} for c in cells)
    s1 = cell_records(units.unit_path(chain_root, 1, SQ, "run") / unit_result(chain_root, 1, SQ, "run")["attempt"])
    assert s1 and all(c["solver_route"] == {"route": "A", "model": ELUCID_MODEL} for c in s1)
    redo = main.ledgers["D"].snapshot()[budgets.solver_scopes("D", OQ, 2, "run", 2)[-1]]
    assert redo["settled"] > 0 and redo["open"] == 0
    bodies = main.providers[("D", "B")].requests
    assert bodies and {b["model"] for b in bodies} == {NORTHGATE_MODEL}
    assert not [b for b in main.providers[("D", "A")].requests if "Year |" in json.dumps(b)][1:]


# ------------------------------------------------------------------------------------------------- the test read
def test_both_chains_read_all_five_units_and_the_sealed_cells_keep_the_solver_route(main):
    assert sorted(main.reader.launched) == sorted((name, bench) for name in CHAINS for bench in BENCHES)
    for name, route in (("G", {"route": None, "model": GLM_SOLVER}), ("D", {"route": "B", "model": NORTHGATE_MODEL})):
        read = verified(read_json(main.root / name / chain.TEST_READ), "test-read")
        assert read["status"] == "read" and read["gate"]["units"] == list(BENCHES)
        for bench in BENCHES:
            assert (chain.unit_root(main.settings[name], name, bench) / "unit.json").exists()
        own = verified(read_json(chain.unit_root(main.settings[name], name, OQ) / "unit.json"), "evaluation")
        sealed = [verified(read_json(path), "evaluation-cell") for path in sorted(
            (chain.unit_root(main.settings[name], name, OQ) / own["attempt"] / "cells").glob("*.json"))]
        assert sealed and all(cell["solver_route"] == route for cell in sealed)
        assert main.opened[name]["units"][OQ] and all(
            value["solver_route"] == route for value in main.opened[name]["units"][OQ].values())
        assert main.labels[name] == main.opened[name]["label"]


def test_every_ledger_settled_every_reservation(main):
    for name in CHAINS:
        snapshot = main.ledgers[name].snapshot()
        assert all(entry["open"] == 0 for entry in snapshot.values() if isinstance(entry, dict))
        assert snapshot[name + ":solver"]["cap"] == protocol.PILOTS["main"]["solver_cap"]
