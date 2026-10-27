"""ALFWorld-only preparation and lean smoke; test panels remain consent gated.

Preparation imports existing main-v2-2 metadata by value. S2 alone uses registered
smoke games; S3 uses authored toy episodes and never a real game or expert plan.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import shutil
import sys
from copy import deepcopy
from dataclasses import replace

from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import budgets, chain, engineer, manifest, prelaunch, profiles as p, routes, smoke, solver, step, supply, units
from .cells import Arm, TrainingStore, cell_id, run_cells
from .package import empty
from .registry import Registry
from .sandbox import client as sandbox

BENCH = "alfworld"
STAGES = ("S1", "S2", "S3", "SE6")
S0_FILE = "alfworld-s0.json"
S2_ITEMS = 3
FIXTURE_INITIAL = ("You are in the middle of a room. Looking quickly around you, you see a table 1, and a shelf 1.\n\n"
                   "Your task is to: put a mug in shelf 1.")
FIXTURE_EPISODE = (
    ("go to table 1", "You arrive at table 1. On the table 1, you see a mug 1."),
    ("take mug 1 from table 1", "You pick up the mug 1 from the table 1."),
    ("go to shelf 1", "You arrive at shelf 1. On the shelf 1, you see nothing."),
    ("put mug 1 in/on shelf 1", "You put the mug 1 in/on the shelf 1."),
)
AUTHORED_SOURCE = '''import re
def applies(view):
    return "task_text" in view and "initial_observation" in view
def alf_before_step(view, state):
    reached = state["facts"]["reached"] if state else []
    discourage = [action for action in view["admissible_commands"]
                  if action.startswith("go to ") and action[6:] in reached]
    return {"fields": {"facts": [view["initial_observation"]]}, "discourage": discourage}
def alf_after_step(event, state):
    old = state["facts"] if state else {"reached": [], "carrying": [], "nothing_happens": 0}
    reached = list(old["reached"])
    carrying = list(old["carrying"])
    rejected = old["nothing_happens"]
    action = event["action"].strip()
    observation = (event["observation"] or "").strip()
    if observation.startswith("Nothing happens"):
        rejected += 1
    else:
        visit = re.match(r"(?:go to|open) (.+)$", action)
        take = re.match(r"take (.+?) from (.+)$", action)
        put = re.match(r"(?:move (.+?) to|put (.+?) (?:in/on|in|on)) (.+)$", action)
        if visit and observation.startswith(("You arrive at", "You open")):
            reached = sorted(set(reached + [visit.group(1).strip()]))
        elif take and observation.startswith("You pick up"):
            carrying.append(take.group(1).strip())
        elif put and observation.startswith(("You move", "You put")):
            obj = (put.group(1) or put.group(2)).strip()
            carrying = [value for value in carrying if value != obj]
            reached = sorted(set(reached + [put.group(3).strip()]))
    return {"counter": (state["counter"] if state else 0) + 1,
            "facts": {"reached": reached, "carrying": sorted(carrying), "nothing_happens": rejected}}
'''


def authored_reply():
    """A fixed proposal, parsed by the same parser and checked by the same registrar as real proposals."""
    change = {"kind": "new", "description": "Tracks visited receptacles and carried objects from public transitions.",
              "hooks": ["alf_after_step", "applies", "alf_before_step"], "state_bytes": 4000,
              "max_note_chars": 4000, "excluded_benches": [bench for bench in p.BENCHES if bench != BENCH],
              "replay_tests": []}
    return "```json\n" + json.dumps({"changes": [change]}, sort_keys=True) + "\n```\n```python\n" + AUTHORED_SOURCE + "```"


def _profile(configuration):
    require(p.is_alfworld(configuration), "The registered ALFWorld-only configuration")


def snapshot(out, *, source, git_head, configuration=p.ALFWORLD_V1):
    _profile(configuration)
    source, out = safe_path(source), safe_path(out)
    require(not out.exists() and not out.is_relative_to(source), "A snapshot is a new directory outside the checkout")
    paths = prelaunch._files(source)
    forbidden = (".env", "sealed-holdout", "private-api", "api-cache")
    require(all(not path.is_symlink() and not any(term in path.name.lower() for term in forbidden)
                for path in paths), "Snapshot source contains a private file or link")
    for path in paths:
        target = out / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    listing = out / "sha256-list.txt"
    listing.write_text(prelaunch.sha256_list(source), encoding="utf-8")
    value = prelaunch.verify_snapshot(listing, root=out, build_tree=source, git_head=git_head)
    write_json(out / "snapshot-provenance.json", value)
    return value


def preparation(path):
    """Project a verified main manifest onto ALF metadata, without opening any pinned data file."""
    path = safe_path(path)
    source = manifest.load(path, verify=False)
    require(source["configuration"] == p.MAIN_V2_2, "ALFWorld inherits the main-v2-2 preparation")
    card = source["cards"][BENCH]
    card_sha = hashlib.sha256(card.encode()).hexdigest()
    require(len(card) == manifest.ALFWORLD_CARD_IDENTITY[0]
            and card_sha.startswith(manifest.ALFWORLD_CARD_IDENTITY[1]),
            "The registered frozen ALFWorld task card")
    pool = deepcopy(source["data"]["pools"][BENCH])
    pinned = source["data"]["pinned"]
    split_path, test_path = pinned["paths"]["split"], pinned["paths"]["test"][BENCH]
    test = {"path": test_path, "sha256": pinned["sha256"][test_path]}
    split = {"path": split_path, "sha256": pinned["sha256"][split_path]}
    require(len({str(safe_path(entry["path"])) for entry in (pool, test, split)}) == 3,
            "The ALFWorld pool is separate from the split and test panel")
    for entry in (pool, test, split):
        require(set(entry) == {"path", "sha256"} and type(entry["path"]) is str
                and type(entry["sha256"]) is str and len(entry["sha256"]) == 64
                and set(entry["sha256"]) <= set("0123456789abcdef"), "A pinned ALFWorld data identity")
    runtime, contract = deepcopy(source["runtime"][BENCH]), deepcopy(source["contracts"][BENCH])
    require(contract["sha"] == hashlib.sha256(contract["text"].encode()).hexdigest(), "The inherited contract pin")
    registration = {"preparation": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "record_sha256": source[p.RECORD_HASH]},
                    "card_sha256": card_sha, "contract_sha256": contract["sha"],
                    "runtime_sha256": digest(runtime), "pool": pool, "test": test, "split": split}
    return {"registration": registration, "pool": pool, "cards": {BENCH: card},
            "runtime": {BENCH: runtime}, "contracts": {BENCH: contract},
            "pinned": {"paths": {"split": split_path, "test": {BENCH: test_path}},
                       "sha256": {split_path: split["sha256"], test_path: test["sha256"]}}}


def _slices(items, runtime):
    from .alfworld_format import environment_runtime
    runtime = environment_runtime(runtime)
    require(all(item.get("benchmark") == BENCH and item.get("part") == supply.FRESH_PART for item in items),
            "The registered fresh ALFWorld supply only")
    cut = supply.slices(BENCH, supply.order(BENCH, items), supply.registered_sizes(BENCH))
    for item in (item for values in cut.values() for item in values):
        public = item["public"]
        require(item.get("views_runtime_sha256") == digest(runtime)
                and public.get("routing_view_sha256") == digest(public.get("routing_view"))
                and set(public["routing_view"]) == set(p.ALFWORLD_ROUTING_VIEW),
                "ALFWorld slices use pre-reset views from the inherited runtime")
    return cut


def fixture_items(runtime):
    """Two authored stateful episodes; paths are labels consumed only by _FixtureEnv."""
    from .alfworld_format import environment_runtime
    runtime = environment_runtime(runtime)
    rows = []
    for number in range(2):
        view = solver.alfworld_routing_view(FIXTURE_INITIAL, ["look", "inventory", FIXTURE_EPISODE[0][0]])
        key = "alfworld/alf-smoke-fixture-%d" % number
        rows.append({"benchmark": BENCH, "task_id": key, "family_id": key, "part": "fixture",
                     "room": "fixture-%d" % number, "task_type": "pick_and_place_simple",
                     "public": {"game_file": "alf-smoke-fixture://%d" % number, "routing_view": view,
                                "routing_view_sha256": digest(view)}, "private": {"game_metadata": {}},
                     "views_runtime_sha256": digest(runtime)})
    return rows


class _FixtureEnv:
    """Authored ALF-shaped transitions, with no filesystem access or hidden plan in the public infos."""
    def __init__(self, public):
        self.initial = public["routing_view"]["initial_observation"]
        self.position = 0

    def _info(self):
        commands = ["look", "inventory"]
        if self.position < len(FIXTURE_EPISODE):
            commands.append(FIXTURE_EPISODE[self.position][0])
        return [{"admissible_commands": commands, "won": self.position == len(FIXTURE_EPISODE)}]

    def reset(self):
        self.position = 0
        return [self.initial], None, self._info()

    def step(self, actions):
        if self.position < len(FIXTURE_EPISODE) and actions[0] == FIXTURE_EPISODE[self.position][0]:
            observation = FIXTURE_EPISODE[self.position][1]
            self.position += 1
        elif actions[0] == "look":
            observation = self.initial if self.position == 0 else FIXTURE_EPISODE[self.position - 1][1]
        elif actions[0] == "inventory":
            observation = "You are carrying a mug 1." if self.position in (2, 3) else "You are carrying nothing."
        else:
            observation = "Nothing happens."
        won = self.position == len(FIXTURE_EPISODE)
        return [observation], None, [float(won)], [won], self._info()

    def close(self):
        pass


@contextlib.contextmanager
def _fixture_environment(items):
    allowed = {item["public"]["game_file"]: item["public"] for item in items}
    original = backends._new_alfworld
    def opened(public, runtime):
        require(public.get("game_file") in allowed, "Only authored S3 fixture games use the fixture environment")
        return _FixtureEnv(allowed[public["game_file"]])
    backends._new_alfworld = opened
    try:
        yield
    finally:
        backends._new_alfworld = original


def collect_s0(out, *, preparation_file, snapshot_root=manifest.REPO, selftest=None, checks=None,
               configuration=p.ALFWORLD_V1, confirm_views=None):
    _profile(configuration)
    out = safe_path(out)
    require(not (out / S0_FILE).exists(), "S0 is written once")
    require(not out.is_relative_to(manifest.REPO), "Preparation artifacts live outside the repository")
    imported = preparation(preparation_file)
    items = manifest._items(imported["pool"], BENCH)
    cut = _slices(items, imported["runtime"][BENCH])
    additional = {}
    if p.is_v296(configuration):
        from .alfworld_format import bind
        additional["judge_runtime"] = bind(imported["runtime"][BENCH], configuration)
    if p.is_v29(configuration):
        from . import alf_confirm_views, confirm
        viewed = alf_confirm_views.load_for_preparation(confirm_views, configuration=configuration,
                                                        imported=imported, items=items)
        selected, pin = confirm.slice_items(configuration, items)
        cut["confirm"] = alf_confirm_views.attach(selected, viewed, configuration=configuration,
                                                runtime=imported["runtime"][BENCH], confirm_pin=pin)
        additional["alf_confirm_views"] = viewed
    out.mkdir(parents=True, exist_ok=True)
    fixtures = fixture_items(imported["runtime"][BENCH])
    fixture_file = out / "synthetic-fixtures.json"
    write_json(fixture_file, fixtures)
    tested = (smoke.sandbox_selftest(out / "sandbox", item_files=[str(fixture_file)],
                  **({"configuration": configuration} if p.is_v292(configuration) else {})) if selftest is None
              else p.verified(read_json(selftest), "sandbox-selftest"))
    checked = checks or prelaunch.zero_call_checks(snapshot_root, python=sys.executable)
    measured = {key: tested["measured"][key] for key in ("vsz_kib", "rss_kib", "view_bytes_p99")}
    measured["view_bytes_p99"] = max(measured["view_bytes_p99"], max(
        len(json.dumps(item["public"]["routing_view"], ensure_ascii=False).encode())
        for values in cut.values() for item in values))
    measured["native_peak_rss_kib"] = 1  # no native spreadsheet scorer in this profile
    value = p.record("alfworld-s0", "smoke", {"configuration": configuration, **imported, **additional,
        "slice_ids": {key: [item["task_id"] for item in rows] for key, rows in cut.items()},
        "slice_counts": {key: len(rows) for key, rows in cut.items()}, "fixtures_sha256": digest(fixtures),
        "sandbox": tested[p.RECORD_HASH], "limits": tested["limits"], "measured": measured,
        "pytest": checked, "sealed_reads": 0, "snapshot_root": str(safe_path(snapshot_root)),
        "snapshot_sha256": hashlib.sha256(prelaunch.sha256_list(snapshot_root).encode()).hexdigest(),
        "passed": tested["passed"] is True and checked["passed"] is True})
    write_json(out / S0_FILE, value)
    return value


def make_manifest(out, *, root, s0_file, provenance, roles_repo, elucid_env, route_b_env, smoke_chain=None,
                  smoke_results=(), environment_found=None, configuration=p.ALFWORLD_V1):
    _profile(configuration)
    checked = p.verified(read_json(s0_file), "alfworld-s0")
    require(checked["passed"] and checked["configuration"] == configuration, "A passing ALFWorld S0")
    imported = preparation(checked["registration"]["preparation"]["path"])
    require(all(checked[key] == value for key, value in imported.items()), "The preparation still matches S0")
    if p.is_v296(configuration):
        from .alfworld_format import bind
        require(checked.get("judge_runtime") == bind(imported["runtime"][BENCH], configuration),
                "S0 pins the configured ALFWorld format runtime")
    additional = {}
    if p.is_v29(configuration):
        from . import alf_confirm_views, confirm
        items = manifest._items(imported["pool"], BENCH)
        _, source = alf_confirm_views.preparation_sources(imported, items)
        viewed = alf_confirm_views.validate(checked.get("alf_confirm_views"), configuration=configuration,
            runtime=imported["runtime"][BENCH], confirm_pin=confirm.identity(configuration, items),
            preparation=imported["registration"]["preparation"], pool=imported["pool"], source=source)
        additional = {"alf_confirm_views": deepcopy(viewed)}
    provenance_value = read_json(provenance)
    current_sha = hashlib.sha256(prelaunch.sha256_list(manifest.REPO).encode()).hexdigest()
    require(checked.get("snapshot_sha256") == current_sha == provenance_value.get("sha256_list_sha256")
            and safe_path(checked["snapshot_root"]) == manifest.REPO
            and safe_path(provenance_value["snapshot_root"]) == manifest.REPO,
            "S0 and snapshot provenance must certify the current code/test snapshot")
    require(smoke_chain in (None, "D"), "Only chain D is launchable")
    root = safe_path(root)
    require(smoke_chain is not None or str(root) == p.RUN_ROOTS[configuration], "The registered real run root")
    require(len(smoke_results) <= 1, "One measured chain-D smoke result")
    read_card, read_proc = p.TEST_READ_CELLS[configuration][BENCH]
    estimate = math.ceil(p.CELL_ANCHORS[BENCH][1] * (read_card + read_proc * float(p.PROCEDURE_ARM_FACTOR[1])))
    pins = {}
    probe_longest = routes.S1B_CEILING
    for result_path in smoke_results:
        result = p.verified(read_json(result_path), "alfworld-smoke-result")
        require(result["passed"] and result["configuration"] == configuration and result["chain"] == "D"
                and result.get("s0") == checked[p.RECORD_HASH] and result.get("snapshot_sha256") == current_sha,
                "A passed measured ALFWorld smoke for this S0 and snapshot")
        if p.is_v29(configuration):
            probe = result["solver_probe"]
            require(probe["passed"] and probe["route"] == "B" and probe["longest"] > 0,
                    "The real-run ledger bound comes from northgate S1")
            probe_longest = probe["longest"]
        smoked = manifest.load(result["manifest_path"], verify=False)
        require(smoked[p.RECORD_HASH] == result["manifest"] and smoked["configuration"] == configuration
                and smoked["evidence"] == "smoke" and smoked["data"]["s0_sha256"] == checked[p.RECORD_HASH]
                and smoked["code"] == manifest.pin_code() and smoked["data"]["launchable_chains"] == ["D"],
                "The measured smoke used this code, registration, S0 and chain")
        estimate = result["read_estimate"]
        pins["D"] = {"path": str(safe_path(result_path)), "record_sha256": result[p.RECORD_HASH]}
    require(smoke_chain is not None or pins, "A real run needs a passed measured chain-D smoke")
    blocks = {"G": manifest.solver_block("G", env_path=roles_repo, configuration=configuration),
              "D": manifest.solver_block("D", env_path=route_b_env if p.is_v29(configuration) else elucid_env,
                  branch="N" if p.is_v29(configuration) else "E",
                  longest=probe_longest if p.is_v29(configuration) else None, configuration=configuration)}
    route = routes.pin("D", "B", env_path=route_b_env, solver_block=blocks["D"], configuration=configuration)
    given = {"root": str(root), "data": {"pools": {BENCH: imported["pool"]}, "pinned": imported["pinned"],
        manifest.alfworld_registration_key(configuration): imported["registration"], "s0_sha256": checked[p.RECORD_HASH],
        "test_read_estimate": {"D": estimate}, "test_read_terms": {"D": {BENCH: str(estimate)}},
        "launchable_chains": ["D"], "snapshot_sha256": current_sha, "smoke_results": pins, **additional},
        "cards": imported["cards"], "contracts": imported["contracts"], "runtime": imported["runtime"],
        "sheet_qualification": None, "fixtures": {"sha256": checked["fixtures_sha256"]},
        "clients": {"solver": blocks, "roles": manifest.role_settings(configuration), "routes": {"D": {"B": route}}},
        "provenance": provenance_value}
    return manifest.make(out, evidence="smoke" if smoke_chain else p.REAL_RUN_EVIDENCE[configuration],
        measured=checked["measured"], limits={key: sandbox.Limits(**value) for key, value in checked["limits"].items()},
        configuration=configuration, environment_found=environment_found, **given)


def _s1(setting):
    configuration = p.configuration_of(setting)
    first, roles = chain.first_call(setting, "D"), {}
    for role in ("engineer", "examiner", "describer", "leakage"):
        name = "D/alfworld-smoke/S1/" + role
        def work(attempt, role=role, name=name):
            endpoint = units.role_endpoint(setting, "D", role, BENCH, 1)
            if role == "engineer":
                endpoint = units._bounded_endpoint(endpoint, p.ENGINEER_MAX_TOKENS[configuration])
            recorder = endpoint.recorder(label=name)
            receipt = endpoint.send(p.FIRST_CALL_SYSTEM, p.FIRST_CALL_USER, recorder)
            result = {"passed": receipt.get("ok") is True and receipt.get("returned_model") == p.ROLE_MODEL,
                      "calls": len(recorder.sends), "tokens": sum(s.get("charged", 0) for s in recorder.sends),
                      "request_sha256": recorder.sends[0]["request_sha256"] if recorder.sends else None}
            write_json(attempt / "first-call.json", result)
            require(result["passed"], "First %s role response was not confirmed" % role)
            return result
        done = units.run_unit(safe_path(setting.root) / "D" / "lean-smoke" / "S1-roles" / role,
            run=setting.run, identity={"unit": name}, work=work, evidence=setting.evidence, configuration=configuration)
        roles[role] = done["result"]
    extra = {}
    if p.is_v29(configuration):
        from . import v29_route_probe
        extra["solver_probe"] = v29_route_probe.measure(setting)
    return {"passed": first["passed"] and all(row["passed"] for row in roles.values()), "roles": roles,
            "solver_confirmation": first[p.RECORD_HASH], **extra}


def _s2(setting):
    tasks = _slices(setting.pools[BENCH], setting.runtime[BENCH])["smoke"][:S2_ITEMS]
    name = "D/alfworld-smoke/S2"
    local = units.for_unit(setting, "D", BENCH, name) if p.is_v292(p.configuration_of(setting)) else setting
    def work(attempt):
        endpoint = units.solver_endpoint(setting, "D", BENCH, 1, "run", attempt)
        context = units.cell_context(local, attempt, endpoint)
        arm = Arm("card", empty(step=name, evidence=setting.evidence))
        jobs = [({"id": cell_id(name, "C", task["task_id"], 0), "unit": name, "arm": "C", "benchmark": BENCH,
                  "task_id": task["task_id"], "run": 0}, {"public": task["public"], "private": task["private"]}, arm)
                for task in tasks]
        cells = run_cells(context, jobs, workers=setting.workers, store=TrainingStore(attempt))
        measured = smoke.measured_cells(cells)
        complete = sum((cell.get("final") or {}).get("token") in ("pass", "fail") for cell in cells)
        return {"passed": len(tasks) == complete == S2_ITEMS and measured["actual"] > 0,
                "items": len(tasks), "completed": complete, "wins": sum(
                    (cell.get("final") or {}).get("token") == "pass" for cell in cells),
                "measurements": measured, "tokens_per_cell": measured["actual"] / len(tasks),
                "settled_tokens": sum(send.get("charged", 0) for cell in cells for send in cell["sends"]),
                "solver_bounds": {"branch": setting.branch, "longest": setting.longest,
                    "ledger_bound": p.ledger_bound(p.CHAINS["D"], BENCH, branch=setting.branch,
                                                    longest=setting.longest)}}
    return units.run_unit(safe_path(setting.root) / "D" / "lean-smoke" / "S2", run=setting.run,
        identity={"unit": name}, work=work, evidence=setting.evidence, configuration=p.configuration_of(setting),
        drain=units.drainer(setting, "D", name))["result"]


def _fixture_step(setting, services, substage):
    root = safe_path(setting.root) / "D" / "role-smoke" / substage
    items = fixture_items(setting.runtime[BENCH])
    services = replace(services, registry=Registry(root / "fixture-history", evidence=setting.evidence))
    setting = replace(setting, pools={BENCH: items})
    parent = empty(step="D/s0", evidence=setting.evidence)
    st = step._Step(setting, services, "D", BENCH, 1, parent, root, None)
    return st, {"run": items, "accept": []}


def _substage_identity(st, cut, substage):
    return {"run": st.setting.run, "configuration": p.configuration_of(st.setting), "substage": substage,
            "fixtures_sha256": digest(cut["run"]), "episode_sha256": digest(FIXTURE_EPISODE),
            **({"proposal_sha256": digest(authored_reply())} if substage == "S3a" else {})}


def _cached_substage(st, identity):
    path = st.chain_root / "result.json"
    if not path.exists():
        return None
    value = p.verified(read_json(path), "alfworld-smoke-substage")
    require(all(value.get(key) == expected for key, expected in identity.items()),
            "An ALF smoke substage belongs to this run, configuration and authored fixtures")
    return value["result"]


def _save_substage(st, identity, result):
    write_json(st.chain_root / "result.json", p.record("alfworld-smoke-substage", st.evidence,
               {**identity, "result": result}))
    return result


class _NoRoleCalls:
    """The authored proposal must require no model role, including adjudication or fixes."""
    calls = ()

    def plain(self, *args, **kwargs):
        raise RuntimeError("An authored S3a proposal must not request a model role")


def _authored_proposal(st, cut):
    def work(attempt):
        reply = authored_reply()
        try:
            entries, sources = engineer.parse(reply)
        except engineer.Unparseable as error:
            return {"parsed": False, "passed": False, "reason": str(error), "checks": [],
                    "candidate_sha256": None, "model_calls": 0}
        changes = engineer.changes_of(entries, sources, digest(reply))
        if len(changes) != 1:
            return {"parsed": True, "passed": False, "reason": "one_authored_change", "checks": [],
                    "candidate_sha256": None, "model_calls": 0}
        stored = step._run_trajectories(st)
        _, _, publics = step._training_publics(cut, None, BENCH)
        ctx = engineer.Context(bench=BENCH, k=1, step=st.name, evidence=st.evidence, parent=st.parent,
            trajectories=stored, current=step._current(st, []), corpora=step._corpora(st, cut),
            workers=st.services.workers, roles=_NoRoleCalls(), label=st.label("engineer-r1"),
            card=st.setting.cards.get(BENCH, ""), mode="train", round=1, base=st.parent,
            configuration=p.configuration_of(st.setting), echo=p.FIX_ECHO[p.configuration_of(st.setting)],
            counterfactual=p.META_COUNTERFACTUAL[p.configuration_of(st.setting)],
            routing_items=[(key, solver.routing_view(BENCH, public, runtime=st.runtime()))
                           for key, public in publics.items()],
            routing_workers=step._item_workers(st, publics),
            routing_shared_worker=st.services.item_workers is None)
        checked = engineer.check(changes[0], ctx)
        candidate, kept = engineer._combined_train(ctx, changes) if checked["passed"] else (None, [])
        if candidate is not None:
            step.save(st.chain_root, candidate)
        return {"parsed": True, "passed": bool(checked["passed"] and candidate is not None and kept),
                "checks": checked["checks"], "failed": checked["failed"],
                "candidate_sha256": candidate.sha256 if candidate is not None else None,
                "model_calls": 0}
    return st.unit("engineer-r1", work)


def _state_changes(st, cut, candidate, evaluated):
    """Check only this completed training unit's candidate-arm hashes, once for every fixture game."""
    wanted = step._run_keys(st, cut)
    result = {"games": len(wanted), "checked": 0, "changed": 0, "passed": False}
    if candidate is None or evaluated is None or evaluated["cells"] <= 0:
        return result
    procedures = [proc.id for proc in candidate.for_bench(BENCH)
                  if "alf_before_step" in proc.hooks and "alf_after_step" in proc.hooks]
    if len(procedures) != 1 or evaluated["candidate_sha256"] != candidate.sha256:
        return result
    found = [row for row in step._unit_trajectories(st, "train-r1")
             if row["unit"] == st.label("train-r1") and row["arm"] == "S'" and row["arm_kind"] == "candidate"
             and row["bench"] == BENCH and row["package_sha256"] == candidate.sha256]
    for key in sorted(wanted):
        games = [row for row in found if row["task_id"] == key]
        if len(games) != 1 or games[0]["run"] != 0:
            continue
        result["checked"] += 1
        hashes = [row["state_sha256"].get(procedures[0]) for row in games[0].get("alfworld_steps") or []]
        valid = len(hashes) >= 2 and all(type(value) is str and len(value) == 64
                                       and set(value) <= set("0123456789abcdef") for value in hashes)
        if valid and all(a != b for a, b in zip(hashes, hashes[1:])):
            result["changed"] += 1
    result["passed"] = result["games"] == result["checked"] == result["changed"] and len(found) == len(wanted)
    return result


def _s3a(setting, services):
    """Authored parse/normalization/C1-C9 and real solver training, without any model role call."""
    st, cut = _fixture_step(setting, services, "S3a")
    identity = _substage_identity(st, cut, "S3a")
    cached = _cached_substage(st, identity)
    if cached is not None:
        return cached
    with _fixture_environment(cut["run"]):
        step._run(st, cut)
        proposed = _authored_proposal(st, cut)
        candidate = step._package(st, proposed["candidate_sha256"]) if proposed["candidate_sha256"] else None
        evaluated = step._train_eval(st, cut, 1, st.parent, candidate, None) if candidate is not None else None
    changing = _state_changes(st, cut, candidate, evaluated)
    return _save_substage(st, identity, {"passed": bool(proposed["passed"] and changing["passed"]),
        "proposal": proposed, "training": evaluated, "state_changes": changing, "model_role_calls": 0})


def _measured_roles(st):
    roles, measurement_path = st.roles, st.chain_root / "role-measurements.jsonl"
    def measured_roles(role):
        made = roles(role)
        plain = made.plain
        def measured(*args, **kwargs):
            before = len(made.calls)
            try:
                return plain(*args, **kwargs)
            finally:
                rows = []
                for call in made.calls[before:]:
                    sends = call.get("sends") or []
                    rows.append({"role": role, "charged": sum(send.get("charged", 0) for send in sends),
                                 "request_bytes": max([send.get("request_bytes", 0) for send in sends], default=0)})
                if rows:
                    measurement_path.parent.mkdir(parents=True, exist_ok=True)
                    with measurement_path.open("a", encoding="utf-8") as handle:
                        handle.write("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        made.plain = measured
        return made
    st.roles = measured_roles
    return measurement_path


def _s3b(setting, services):
    """One ordinary real engineer round: parsed proposal and measurements, with no candidate or gain gate."""
    st, cut = _fixture_step(setting, services, "S3b")
    identity = _substage_identity(st, cut, "S3b")
    cached = _cached_substage(st, identity)
    if cached is not None:
        return cached
    measurement_path = _measured_roles(st)
    with _fixture_environment(cut["run"]):
        step._run(st, cut)
        step._diagnose(st, cut)
        generated = step._generate(st, cut)
        engineered = step._engineer_train(st, cut, 1, st.parent, done=[], fed=None, history=[], training=None,
            lint=[], reserved=frozenset(), analysed=frozenset(), disclosed=frozenset(), generated=generated)
        candidate = step._package(st, engineered["candidate_sha256"]) if engineered["candidate_sha256"] else None
        evaluated = step._train_eval(st, cut, 1, st.parent, candidate, generated) if candidate is not None else None
    measurements = smoke.role_calls_measured([json.loads(line) for line in measurement_path.read_text().splitlines()]
                                             if measurement_path.exists() else [])
    parsed = any(row["parsed"] for row in engineered["engineer"]["proposals"])
    measured = measurements.get("engineer") or {}
    return _save_substage(st, identity, {"passed": bool(parsed and measured.get("calls", 0) > 0
            and measured.get("tokens", 0) > 0 and measured.get("request_bytes", 0) > 0),
        "parsed": parsed, "engineer": engineered, "training": evaluated,
        "candidate_sha256": engineered["candidate_sha256"], "role_measurements": measurements})


def _s3(setting, services):
    if p.is_v29(p.configuration_of(setting)):
        from . import v29_smoke
        return v29_smoke.s3(setting, services)

    authored, real = _s3a(setting, services), _s3b(setting, services)
    failed = [name for name, value in (("S3a", authored), ("S3b", real)) if not value["passed"]]
    return {"passed": not failed, "S3a": authored, "S3b": real, "failed_substages": failed,
            "rounds": 1, "fixtures": 2, "role_measurements": real["role_measurements"],
            "generator": "selection", "research": "not_applicable", "environment": "authored_local_fixture"}


def projection(s2, s3, configuration=p.ALFWORLD_V1):
    _profile(configuration)
    card = s2["tokens_per_cell"]
    require(card > 0 and s2["items"] == S2_ITEMS and s2["measurements"]["actual"] > 0,
            "S-E6 needs three measured ALFWorld games")
    ratio, proc = s2["settled_tokens"] / s2["measurements"]["actual"], card * float(p.PROCEDURE_ARM_FACTOR[1])
    if p.is_v29(configuration):
        measured_confirm = s3["confirm_measurements"]
        require(measured_confirm["cells"] > 0, "S3 confirmation ran fixture cells")
        proc = max(proc, measured_confirm["settled_tokens"] / measured_confirm["cells"] / ratio)
    bound = s2["solver_bounds"]
    require(ratio > 0 and bound["ledger_bound"] == p.ledger_bound(p.CHAINS["D"], BENCH,
        branch=bound["branch"], longest=bound["longest"]), "The measured solver bound and positive ledger ratio")
    reserve = reservation(s2["measurements"]["request_bytes"][BENCH], bound["ledger_bound"])
    caps, scopes = budgets.chain_caps("D", configuration), {}
    # Reuse the registered schedule, including every permitted kind of redo.
    from .zebra_smoke import _scope_cells
    for name, alternatives in _scope_cells("D", configuration).items():
        estimate = max((sum(card * c + proc * q for c, q in cells.values()) for cells in alternatives), default=0)
        need = math.ceil(estimate * ratio + reserve)
        scopes[name] = {"projected": need, "cap": caps[name], "passed": need <= caps[name]}
    roles = {name: row for name, row in smoke.glm_projection(s3["role_measurements"], configuration).items()
             if name.startswith("D:")}
    read_card, read_proc = p.TEST_READ_CELLS[configuration][BENCH]
    return {"passed": all(row["passed"] for row in scopes.values()) and all(row["fits"] for row in roles.values()),
            "configuration": configuration, "chain": "D", "scopes": scopes, "roles": roles,
            "solver_bounds": dict(bound),
            "per_cell": {BENCH: {"card": card, "procedure": proc, "procedure_assumed": True}}, "ratio": ratio,
            "read_estimate": math.ceil(ratio * (read_card * card + read_proc * proc))}


def _checked_stage(path, m, stage):
    value = p.verified(read_json(path), "alfworld-smoke-stage")
    require(value.get("configuration") == m["configuration"] and value.get("manifest") == m[p.RECORD_HASH]
            and value.get("chain") == "D" and value.get("stage") == stage,
            "A smoke stage belongs to this manifest, chain, configuration and stage")
    return value


def run_stage(manifest_path, stage, *, chain_id="D", docker=None, transport=None, configuration=p.ALFWORLD_V1):
    _profile(configuration)
    require(stage in STAGES and chain_id == "D", "An ALFWorld smoke stage on chain D")
    m = manifest.load(manifest_path, docker=docker)
    require(m["configuration"] == configuration and m["evidence"] == "smoke", "An isolated ALFWorld smoke manifest")
    setting = manifest.setting_of(m, "D", path=manifest_path, docker=docker, transport=transport)
    setting.budget.declare({**budgets.chain_caps("D", configuration), **budgets.first_call_caps("D")})
    root = safe_path(setting.root) / "D" / "lean-smoke"
    with exclusive(root / ".stage-lock"):
        path = root / (stage + ".json")
        if path.exists():
            return _checked_stage(path, m, stage)
        previous = {}
        for prior in STAGES[:STAGES.index(stage)]:
            previous[prior] = _checked_stage(root / (prior + ".json"), m, prior)["result"]
            require(previous[prior]["passed"], "Every preceding smoke stage must pass")
        if p.is_v29(configuration) and stage != "S1":
            probe = previous["S1"]["solver_probe"]
            require(probe["passed"] and probe["route"] == "B", "The measured northgate bound")
            setting = replace(setting, branch="N", longest=probe["longest"])
        if stage == "S1":
            value = _s1(setting)
        elif stage == "S2":
            value = _s2(setting)
        elif stage == "S3":
            value = _s3(setting, manifest.services_of(m, "D", setting=setting, transport=transport))
        else:
            value = projection(previous["S2"], previous["S3"], configuration)
        written = p.record("alfworld-smoke-stage", "smoke", {"configuration": configuration, "chain": "D",
                            "manifest": m[p.RECORD_HASH], "stage": stage, "result": value})
        write_json(path, written)
        if stage == "SE6":
            write_json(root / "result.json", p.record("alfworld-smoke-result", "smoke", {
                "configuration": configuration, "chain": "D", "manifest": m[p.RECORD_HASH],
                "stages": list(STAGES), "passed": value["passed"], "read_estimate": value["read_estimate"],
                "s0": m["data"]["s0_sha256"], "manifest_path": str(safe_path(manifest_path)),
                "snapshot_sha256": m["data"]["snapshot_sha256"], "sealed_reads": 0,
                **({"solver_probe": previous["S1"]["solver_probe"]} if p.is_v29(configuration) else {})}))
        return written
