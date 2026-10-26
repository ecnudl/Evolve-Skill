"""The ZebraLogic profile preparation and lean smoke, independent of frozen five-bench recipes.

Only S1/S2/S3 send requests. S0 and manifest preparation never open a sealed panel.
The manifest names all registration values and the smoke records are restartable.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import budgets, chain as chains, engineer, manifest, prelaunch, profiles as p, routes, smoke, smoke_roles, solver, step, units
from . import zebralogic as z
from .cells import Arm, TrainingStore, cell_id, run_cells
from .package import empty
from .registry import Registry
from .sandbox import client as sandbox

STAGES = ("S1", "S2", "S3", "SE6")
S0_FILE = "zebra-s0.json"
RUNTIME = {"prompt_layout": "contract-first-v2"}
AUTHORED_SOURCE = '''def applies(view):
    return isinstance(view.get("question"), str) and isinstance(view.get("columns"), list)
def before_call(view, state):
    return {"facts": [view["question"].splitlines()[0]]}
'''


def authored_reply():
    """A wiring fixture: repeat the visible house-count sentence, with no puzzle-solving logic."""
    change = {"kind": "new", "description": "Keeps the public house-count sentence visible.",
              "hooks": ["before_call", "applies"], "state_bytes": 0, "max_note_chars": 4000,
              "excluded_benches": list(p.BENCHES), "replay_tests": []}
    return "```json\n" + json.dumps({"changes": [change]}, sort_keys=True) + "\n```\n```python\n" + AUTHORED_SOURCE + "```"


def fixture_items():
    """Synthetic public facts, never a real puzzle or a fixture of a different benchmark."""
    found = []
    for index in range(6):
        rows = [[str(house), "Person%d_%d" % (index, house), "Color%d_%d" % (index, house)]
                for house in range(1, 6)]
        question = "There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street.\n" + "\n".join(
            "House %s has Name %s and Color %s." % tuple(row) for row in rows)
        found.append(z.normalize({"id": "zpc-fixture-%02d" % index, "bench": z.BENCH, "task": "5*2", "size": "5*2",
                                  "puzzle": question, "solution": {"header": ["House", "Name", "Color"],
                                                                    "rows": rows}}))
    return found


def snapshot(out, *, source, git_head, configuration=p.ZEBRA_PC_V1):
    """Copy the registered code/test trees only, rejecting links and private file names."""
    require(p.is_zebra(configuration), "A registered ZebraLogic configuration")
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


def _split_pins(path):
    """Validate output_sha256 values in the split manifest, without statting either panel."""
    raw = z.guard_pool_path(path).read_bytes()
    found = json.loads(raw)
    expected = {"zebralogic/pool.json": z.POOL_SHA256,
                "zebralogic/sealed-holdout.json": z.SEALED_SHA256}
    require(isinstance(found, dict) and isinstance(found.get("output_sha256"), dict)
            and all(found["output_sha256"].get(key) == value for key, value in expected.items()),
            "The split manifest output_sha256 must register both exact ZebraLogic paths and identities")
    return {"path": str(safe_path(path)), "sha256": hashlib.sha256(raw).hexdigest(), "field": "output_sha256"}


def collect_s0(out, *, pool=z.POOL_PATH, split_manifest=z.SPLIT_MANIFEST_PATH, snapshot_root=manifest.REPO,
               selftest=None, checks=None, configuration=p.ZEBRA_PC_V1):
    """Zero-call import, slice/card/panel-pin checks and actual sandbox selftest on Linux."""
    require(p.is_zebra(configuration), "A registered ZebraLogic configuration")
    out = safe_path(out)
    require(not (out / S0_FILE).exists(), "S0 is written once")
    tasks = z.load_pool(pool)
    slices = z.slices(tasks)
    pinned = _split_pins(split_manifest)
    require(not out.is_relative_to(manifest.REPO), "Preparation artifacts live outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    fixtures = out / "synthetic-fixtures.json"
    write_json(fixtures, fixture_items())
    tested = (smoke.sandbox_selftest(out / "sandbox", item_files=[str(fixtures)]) if selftest is None
              else p.verified(read_json(selftest), "sandbox-selftest"))
    checked = checks or prelaunch.zero_call_checks(snapshot_root, python=sys.executable)
    measured = {key: tested["measured"][key] for key in ("vsz_kib", "rss_kib", "view_bytes_p99")}
    measured["view_bytes_p99"] = max(measured["view_bytes_p99"], max(
        len(json.dumps(z.public_view(t["public"]), ensure_ascii=False).encode()) for t in tasks))
    measured["native_peak_rss_kib"] = 1  # no native sheet scorer in this profile
    value = p.record("zebra-s0", "smoke", {"configuration": configuration, "registration": z.identity(),
        "pool": {"path": str(safe_path(pool)), "sha256": z.POOL_SHA256}, "split_manifest": pinned,
        "slice_ids": {key: [t["task_id"] for t in value] for key, value in slices.items()},
        "slice_counts": {key: len(value) for key, value in slices.items()}, "fixtures_sha256": digest(fixture_items()),
        "card_sha256": z.CARD_SHA256, "sandbox": tested[p.RECORD_HASH], "limits": tested["limits"],
        "measured": measured, "pytest": checked, "sealed_reads": 0,
        "snapshot_root": str(safe_path(snapshot_root)),
        "snapshot_sha256": hashlib.sha256(prelaunch.sha256_list(snapshot_root).encode()).hexdigest(),
        "passed": tested["passed"] is True and checked["passed"] is True})
    write_json(out / S0_FILE, value)
    return value


def make_manifest(out, *, root, s0_file, provenance, roles_repo, elucid_env, route_b_env, smoke_chain=None,
                  smoke_results=(), environment_found=None, configuration=p.ZEBRA_PC_V1):
    """Build an isolated smoke or run manifest; real runs require measured, passing chain smokes."""
    require(p.is_zebra(configuration), "A registered ZebraLogic configuration")
    if p.is_v27(configuration):
        require(smoke_chain is None or smoke_chain in p.launchable_chains(configuration),
                "zebra-pc-v5 launches chain D only")
    checked = p.verified(read_json(s0_file), "zebra-s0")
    require(checked["passed"] and checked["registration"] == z.identity(), "Passing S0 of this registration")
    provenance_value = read_json(provenance)
    current_sha = hashlib.sha256(prelaunch.sha256_list(manifest.REPO).encode()).hexdigest()
    require(checked.get("snapshot_sha256") == current_sha == provenance_value.get("sha256_list_sha256")
            and safe_path(checked["snapshot_root"]) == manifest.REPO
            and safe_path(provenance_value["snapshot_root"]) == manifest.REPO,
            "S0 and snapshot provenance must certify the current code/test snapshot")
    require(checked.get("configuration", p.ZEBRA_PC_V1) == configuration, "S0 belongs to this configuration")
    require(smoke_chain is None or smoke_chain in p.CHAINS, "A registered smoke chain")
    root = safe_path(root)
    require(smoke_chain is not None or str(root) == p.RUN_ROOTS[configuration], "The registered real run root")
    estimates, terms, smoke_pins = {}, {}, {}
    for result_path in smoke_results:
        result = p.verified(read_json(result_path), "zebra-smoke-result")
        require(result["passed"] and result["configuration"] == configuration, "A passed measured zebra smoke")
        chain = result["chain"]
        if p.is_v27(configuration):
            require(chain in p.launchable_chains(configuration), "zebra-pc-v5 launches chain D only")
        require(chain in p.CHAINS and chain not in smoke_pins and result.get("s0") == checked[p.RECORD_HASH]
                and result.get("snapshot_sha256") == current_sha, "The smoke result belongs to this S0 and snapshot")
        smoked = manifest.load(result["manifest_path"], verify=False)
        require(smoked[p.RECORD_HASH] == result["manifest"] and smoked["configuration"] == configuration
                and smoked["evidence"] == "smoke" and smoked["data"]["s0_sha256"] == checked[p.RECORD_HASH]
                and smoked["code"] == manifest.pin_code() and chain in smoked["data"]["launchable_chains"],
                "The measured smoke used this code, registration, S0 and chain")
        estimates[chain] = result["read_estimate"]
        terms[chain] = {z.BENCH: str(result["read_estimate"])}
        smoke_pins[chain] = {"path": str(safe_path(result_path)), "record_sha256": result[p.RECORD_HASH]}
    require(smoke_chain is not None or estimates, "A real run needs a passed smoke for each launchable chain")
    launchable = [smoke_chain] if smoke_chain else sorted(estimates)
    for chain in p.launchable_chains(configuration):
        if chain not in estimates:
            # A preparation anchor, never labelled measured; the unmeasured chain cannot launch.
            anchor = 5_300 if chain == "G" else 3_400
            estimates[chain] = math.ceil(anchor * (200 + 1_000 * float(p.PROCEDURE_ARM_FACTOR[1])))
            terms[chain] = {z.BENCH: str(estimates[chain])}
    blocks = {"G": manifest.solver_block("G", env_path=roles_repo, configuration=configuration),
              "D": manifest.solver_block("D", env_path=elucid_env, branch="E", configuration=configuration)}
    route = routes.pin("D", "B", env_path=route_b_env, solver_block=blocks["D"], configuration=configuration)
    kwargs = {"root": str(root), "data": {"pools": {z.BENCH: checked["pool"]}, "pinned": z.identity()["sealed"],
        "zebra_pc": z.identity(), "split_manifest": checked["split_manifest"], "s0_sha256": checked[p.RECORD_HASH],
        "test_read_estimate": estimates, "test_read_terms": terms, "launchable_chains": launchable,
        "snapshot_sha256": current_sha,
        "smoke_results": smoke_pins}, "sheet_qualification": None, "cards": {z.BENCH: z.CARD_TEXT},
        "contracts": {z.BENCH: {"text": z.CONTRACT, "sha": hashlib.sha256(z.CONTRACT.encode()).hexdigest()}},
        "runtime": {z.BENCH: dict(RUNTIME)}, "clients": {"solver": blocks, "roles": manifest.role_settings(configuration),
        "routes": {"D": {"B": route}}}, "fixtures": {"sha256": digest(fixture_items())},
        "provenance": provenance_value}
    return manifest.make(out, evidence="smoke" if smoke_chain else p.REAL_RUN_EVIDENCE[configuration],
                         measured=checked["measured"], limits={k: sandbox.Limits(**v) for k, v in checked["limits"].items()},
                         configuration=configuration, environment_found=environment_found, **kwargs)


def _s1(setting, chain):
    configuration = p.configuration_of(setting)
    first = chains.first_call(setting, chain)
    roles = {}
    for role in ("engineer", "examiner", "describer", "leakage"):
        name = "%s/zebra-smoke/S1/%s" % (chain, role)
        def work(attempt, role=role, name=name):
            endpoint = units.role_endpoint(setting, chain, role, z.BENCH, 1)
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
        done = units.run_unit(safe_path(setting.root) / chain / "lean-smoke" / "S1-roles" / role,
                              run=setting.run, identity={"unit": name}, work=work, evidence=setting.evidence,
                              configuration=configuration)
        roles[role] = done["result"]
    return {"passed": first["passed"] and all(row["passed"] for row in roles.values()), "roles": roles,
            "solver_confirmation": first[p.RECORD_HASH]}


def _s2(setting, chain):
    configuration = p.configuration_of(setting)
    tasks = z.slices(setting.pools[z.BENCH])["smoke"]
    name = "%s/zebra-smoke/S2" % chain
    base = safe_path(setting.root) / chain / "lean-smoke" / "S2"
    def work(attempt):
        endpoint = units.solver_endpoint(setting, chain, z.BENCH, 1, "run", attempt)
        context = units.cell_context(setting, attempt, endpoint)
        arm = Arm("card", empty(step=name, evidence=setting.evidence))
        jobs = []
        for task in tasks:
            item = task["task_id"]
            cell = {"id": cell_id(name, "C", item, 0), "unit": name, "arm": "C", "benchmark": z.BENCH,
                    "task_id": item, "run": 0}
            jobs.append((cell, {"public": task["public"], "private": task["private"]}, arm))
        cells = run_cells(context, jobs, workers=setting.workers, store=TrainingStore(attempt))
        measured = smoke.measured_cells(cells)
        parsed = sum(((c.get("judge") or {}).get("format") or {}).get("grid") is True
                     and (c.get("final") or {}).get("token") in ("pass", "fail") for c in cells)
        complete = sum((c.get("final") or {}).get("token") in ("pass", "fail") for c in cells)
        return {"passed": complete == 10 and parsed >= 9, "items": 10, "parsed": parsed,
                "parse_rate": parsed / 10, "measurements": measured,
                "tokens_per_cell": measured["actual"] / 10,
                "settled_tokens": sum(s.get("charged", 0) for c in cells for s in c["sends"])}
    return units.run_unit(base, run=setting.run, identity={"unit": name}, work=work, evidence=setting.evidence,
                          configuration=configuration, drain=units.drainer(setting, chain, name))["result"]


def _scope_cells(chain, configuration=p.ZEBRA_PC_V1):
    """The Zebra schedule prices every redo kind, including all six paired training rounds."""
    scopes = smoke._scope_cells(chain, configuration)
    redo, totals = [], {}
    for k, bench in enumerate(p.PILOTS[configuration]["order"], 1):
        for kind in budgets.STEP_KINDS:
            redo.extend(cells for cells in scopes[budgets.solver_scopes(chain, bench, k, kind, 2)[-1]] if cells)
            for b, (card, proc) in p.CONFIG_SCHEDULE_CELLS[configuration][bench][kind].items():
                was = totals.get(b, (0, 0))
                totals[b] = (was[0] + card, was[1] + proc)
    for b, (card, proc) in p.TEST_READ_CELLS[configuration].items():
        was = totals.get(b, (0, 0))
        totals[b] = (was[0] + card, was[1] + proc)
    scopes[chain + ":redo"] = redo
    scopes[chain + ":solver"] = [{b: (card + extra.get(b, (0, 0))[0], proc + extra.get(b, (0, 0))[1])
                                   for b, (card, proc) in totals.items()} for extra in redo]
    return scopes


def projection(s2, chain, configuration=p.ZEBRA_PC_V1, *, s3=None):
    """Measured solver costs and, for v2.8, role costs at the registered call caps."""
    require(p.is_zebra(configuration), "A registered ZebraLogic configuration")
    if p.is_v27(configuration):
        require(chain in p.launchable_chains(configuration), "zebra-pc-v5 launches chain D only")
    card = s2["tokens_per_cell"]
    require(card > 0 and s2["items"] == 10, "S-E6 needs ten measured cells")
    ratio = s2["settled_tokens"] / s2["measurements"]["actual"]
    proc = card * float(p.PROCEDURE_ARM_FACTOR[1])
    size = s2["measurements"]["request_bytes"][z.BENCH]
    reserve = reservation(size, p.ledger_bound(p.CHAINS[chain], z.BENCH, branch="E" if chain == "D" else None))
    caps = budgets.chain_caps(chain, configuration)
    scopes = {}
    for scope, alternatives in _scope_cells(chain, configuration).items():
        estimate = max((sum(card * c + proc * q for c, q in cells.values()) for cells in alternatives), default=0)
        need = math.ceil(estimate * ratio + reserve)
        scopes[scope] = {"projected": need, "cap": caps[scope], "passed": need <= caps[scope]}
    roles = None
    if p.is_v28(configuration):
        require(isinstance(s3, dict) and s3.get("role_measurements"), "S-E6 needs S3 measured role calls")
        roles = {name: row for name, row in smoke.glm_projection(s3["role_measurements"], configuration).items()
                 if name.startswith(chain + ":")}
    return {"passed": all(v["passed"] for v in scopes.values())
            and (roles is None or all(row["fits"] for row in roles.values())), "configuration": configuration,
            "chain": chain, "per_cell": {z.BENCH: {"card": card, "procedure": proc, "procedure_assumed": True}},
            "ratio": ratio, "scopes": scopes, "read_estimate": math.ceil(ratio * (200 * card + 1_000 * proc)),
            **({"roles": roles} if roles is not None else {}),
            "other_chain": ("not_launchable_in_this_configuration" if p.is_v27(configuration)
                            else "not_projected; requires its own smoke")}


def _fixture_step(setting, services, chain, substage):
    configuration = p.configuration_of(setting)
    require(p.is_zebra(configuration) and p.is_v27(configuration) and chain == "D",
            "Zebra v5/v6 role smoke on chain D")
    root = safe_path(setting.root) / chain / "role-smoke" / substage
    items = fixture_items()
    services = replace(services, registry=Registry(root / "fixture-history", evidence=setting.evidence))
    setting = replace(setting, pools={z.BENCH: items})
    parent = empty(step="%s/s0" % chain, evidence=setting.evidence)
    st = step._Step(setting, services, chain, z.BENCH, 1, parent, root, None)
    return st, {"run": items, "accept": []}


def _substage_identity(st, cut, substage):
    return {"run": st.setting.run, "configuration": p.configuration_of(st.setting), "chain": st.chain,
            "substage": substage, "recipe": "zebra-v27-s3-v1", "fixtures_sha256": digest(cut["run"]),
            **({"proposal_sha256": digest(authored_reply())} if substage == "S3a" else {})}


def _cached_substage(st, identity):
    path = st.chain_root / "result.json"
    if not path.exists():
        return None
    value = p.verified(read_json(path), "zebra-smoke-substage")
    require(all(value.get(key) == expected for key, expected in identity.items()),
            "A Zebra smoke substage belongs to this run, configuration, chain and authored fixtures")
    return value["result"]


def _save_substage(st, identity, result):
    write_json(st.chain_root / "result.json", p.record("zebra-smoke-substage", st.evidence,
               {**identity, "result": result}))
    return result


class _NoRoleCalls:
    calls = ()

    def plain(self, *args, **kwargs):
        raise RuntimeError("An authored S3a proposal must not request a model role")


def _authored_proposal(st, cut):
    """Use the real proposal parser, normalizer, checks and package builder; no role endpoint."""
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
        _, _, publics = step._training_publics(cut, None, z.BENCH)
        ctx = engineer.Context(bench=z.BENCH, k=1, step=st.name, evidence=st.evidence, parent=st.parent,
            trajectories=step._run_trajectories(st), current=step._current(st, []), corpora=step._corpora(st, cut),
            workers=st.services.workers, roles=_NoRoleCalls(), label=st.label("engineer-r1"),
            card=st.setting.cards.get(z.BENCH, ""), mode="train", round=1, base=st.parent,
            configuration=p.configuration_of(st.setting), echo=p.FIX_ECHO[p.configuration_of(st.setting)],
            counterfactual=p.META_COUNTERFACTUAL[p.configuration_of(st.setting)],
            routing_items=[(key, solver.routing_view(z.BENCH, public, runtime=st.runtime()))
                           for key, public in publics.items()],
            routing_workers=step._item_workers(st, publics),
            routing_shared_worker=st.services.item_workers is None)
        checked = engineer.check(changes[0], ctx)
        candidate, kept = engineer._combined_train(ctx, changes) if checked["passed"] else (None, [])
        if candidate is not None:
            step.save(st.chain_root, candidate)
        return {"parsed": True, "passed": bool(checked["passed"] and candidate is not None and kept),
                "checks": checked["checks"], "failed": checked["failed"],
                "changes": [change.to_json() for change in changes],
                "candidate_sha256": candidate.sha256 if candidate is not None else None, "model_calls": 0}
    return st.unit("engineer-r1", work)


def _s3a(setting, services, chain="D"):
    """Authored C1-C9 plus measured solver training, independent of the real engineer's choices."""
    st, cut = _fixture_step(setting, services, chain, "S3a")
    identity = _substage_identity(st, cut, "S3a")
    cached = _cached_substage(st, identity)
    if cached is not None:
        return cached
    step._run(st, cut)
    proposed = _authored_proposal(st, cut)
    candidate = step._package(st, proposed["candidate_sha256"]) if proposed["candidate_sha256"] else None
    evaluated = step._train_eval(st, cut, 1, st.parent, candidate, None) if candidate is not None else None
    return _save_substage(st, identity, {"passed": bool(proposed["passed"] and evaluated is not None
        and evaluated["cells"] > 0), "proposal": proposed, "training": evaluated, "model_role_calls": 0})


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


def _s3b(setting, services, chain="D"):
    """One ordinary engineer round; parsing and role measurements are required, admission is optional."""
    st, cut = _fixture_step(setting, services, chain, "S3b")
    identity = _substage_identity(st, cut, "S3b")
    cached = _cached_substage(st, identity)
    if cached is not None:
        return cached
    measurement_path = _measured_roles(st)
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


def _s3(setting, services, chain="D"):
    authored, real = _s3a(setting, services, chain), _s3b(setting, services, chain)
    failed = [name for name, value in (("S3a", authored), ("S3b", real)) if not value["passed"]]
    return {"passed": not failed, "S3a": authored, "S3b": real, "failed_substages": failed,
            "rounds": 1, "fixtures": len(fixture_items()), "role_measurements": real["role_measurements"],
            "generator": "selection", "research": "not_applicable"}


def run_stage(manifest_path, chain, stage, *, docker=None, transport=None, configuration=p.ZEBRA_PC_V1):
    """S1 first calls; S2 ten card cells; S3 one fixture training round; SE6 measured projection."""
    require(stage in STAGES and chain in p.CHAINS, "A lean smoke stage and chain")
    if p.is_v27(configuration):
        require(p.is_zebra(configuration), "A registered ZebraLogic configuration")
        require(chain in p.launchable_chains(configuration), "zebra-pc-v5 launches chain D only")
    m = manifest.load(manifest_path, docker=docker)
    require(p.is_zebra(configuration) and m["configuration"] == configuration and m["evidence"] == "smoke", "An isolated zebra smoke manifest")
    setting = manifest.setting_of(m, chain, path=manifest_path, docker=docker, transport=transport)
    setting.budget.declare({**budgets.chain_caps(chain, configuration), **budgets.first_call_caps(chain)})
    root = safe_path(setting.root) / chain / "lean-smoke"
    with exclusive(root / ".stage-lock"):
        path = root / (stage + ".json")
        if path.exists():
            return _checked_stage(path, m, chain, stage)
        previous = {}
        for prior in STAGES[:STAGES.index(stage)]:
            previous[prior] = _checked_stage(root / (prior + ".json"), m, chain, prior)["result"]
            require(previous[prior]["passed"], "Every preceding smoke stage must pass")
        if stage == "S1":
            value = _s1(setting, chain)
        elif stage == "S2":
            value = _s2(setting, chain)
        elif stage == "S3":
            services = manifest.services_of(m, chain, setting=setting, transport=transport)
            value = (_s3(setting, services, chain) if p.is_v27(configuration) else
                     smoke_roles.zebra_training(setting, services, chain, fixture_items()))
        else:
            value = projection(previous["S2"], chain, configuration,
                               **({"s3": previous["S3"]} if p.is_v28(configuration) else {}))
        written = p.record("zebra-smoke-stage", "smoke", {"configuration": configuration, "chain": chain,
                            "manifest": m[p.RECORD_HASH], "stage": stage, "result": value})
        write_json(path, written)
        if stage == "SE6":
            write_json(root / "result.json", p.record("zebra-smoke-result", "smoke", {
                "configuration": configuration, "chain": chain, "manifest": m[p.RECORD_HASH],
                "stages": list(STAGES), "passed": value["passed"], "read_estimate": value["read_estimate"],
                "s0": m["data"]["s0_sha256"], "manifest_path": str(safe_path(manifest_path)),
                "snapshot_sha256": m["data"]["snapshot_sha256"], "sealed_reads": 0}))
        return written


def _checked_stage(path, m, chain, stage):
    value = p.verified(read_json(path), "zebra-smoke-stage")
    require(value.get("configuration") == m.get("configuration", p.ZEBRA_PC_V1) and value.get("manifest") == m[p.RECORD_HASH]
            and value.get("chain") == chain and value.get("stage") == stage,
            "A smoke stage belongs to this manifest, chain, configuration and stage")
    return value
