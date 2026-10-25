"""The zebra-pc-v1 preparation and lean smoke, independent of frozen five-bench recipes.

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

from . import budgets, chain as chains, manifest, prelaunch, profiles as p, routes, smoke, smoke_roles, solver, units
from . import zebralogic as z
from .cells import Arm, TrainingStore, cell_id, run_cells
from .package import empty
from .sandbox import client as sandbox

STAGES = ("S1", "S2", "S3", "SE6")
S0_FILE = "zebra-s0.json"
RUNTIME = {"prompt_layout": "contract-first-v2"}


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


def snapshot(out, *, source, git_head):
    """Copy the registered code/test trees only, rejecting links and private file names."""
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
               selftest=None, checks=None):
    """Zero-call import, slice/card/panel-pin checks and actual sandbox selftest on Linux."""
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
    value = p.record("zebra-s0", "smoke", {"configuration": p.ZEBRA_PC_V1, "registration": z.identity(),
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
                  smoke_results=(), environment_found=None):
    """Build an isolated smoke or run manifest; real runs require measured, passing chain smokes."""
    checked = p.verified(read_json(s0_file), "zebra-s0")
    require(checked["passed"] and checked["registration"] == z.identity(), "Passing S0 of this registration")
    provenance_value = read_json(provenance)
    current_sha = hashlib.sha256(prelaunch.sha256_list(manifest.REPO).encode()).hexdigest()
    require(checked.get("snapshot_sha256") == current_sha == provenance_value.get("sha256_list_sha256")
            and safe_path(checked["snapshot_root"]) == manifest.REPO
            and safe_path(provenance_value["snapshot_root"]) == manifest.REPO,
            "S0 and snapshot provenance must certify the current code/test snapshot")
    require(smoke_chain is None or smoke_chain in p.CHAINS, "A registered smoke chain")
    root = safe_path(root)
    require(smoke_chain is not None or str(root) == p.ZEBRA_PC_ROOT, "The registered real run root")
    estimates, terms, smoke_pins = {}, {}, {}
    for result_path in smoke_results:
        result = p.verified(read_json(result_path), "zebra-smoke-result")
        require(result["passed"] and result["configuration"] == p.ZEBRA_PC_V1, "A passed measured zebra smoke")
        chain = result["chain"]
        require(chain in p.CHAINS and chain not in smoke_pins and result.get("s0") == checked[p.RECORD_HASH]
                and result.get("snapshot_sha256") == current_sha, "The smoke result belongs to this S0 and snapshot")
        smoked = manifest.load(result["manifest_path"], verify=False)
        require(smoked[p.RECORD_HASH] == result["manifest"] and smoked["configuration"] == p.ZEBRA_PC_V1
                and smoked["evidence"] == "smoke" and smoked["data"]["s0_sha256"] == checked[p.RECORD_HASH]
                and smoked["code"] == manifest.pin_code() and chain in smoked["data"]["launchable_chains"],
                "The measured smoke used this code, registration, S0 and chain")
        estimates[chain] = result["read_estimate"]
        terms[chain] = {z.BENCH: str(result["read_estimate"])}
        smoke_pins[chain] = {"path": str(safe_path(result_path)), "record_sha256": result[p.RECORD_HASH]}
    require(smoke_chain is not None or estimates, "A real run needs a passed smoke for each launchable chain")
    launchable = [smoke_chain] if smoke_chain else sorted(estimates)
    for chain in p.CHAINS:
        if chain not in estimates:
            # A preparation anchor, never labelled measured; the unmeasured chain cannot launch.
            anchor = 5_300 if chain == "G" else 3_400
            estimates[chain] = math.ceil(anchor * (200 + 1_000 * float(p.PROCEDURE_ARM_FACTOR[1])))
            terms[chain] = {z.BENCH: str(estimates[chain])}
    blocks = {"G": manifest.solver_block("G", env_path=roles_repo, configuration=p.ZEBRA_PC_V1),
              "D": manifest.solver_block("D", env_path=elucid_env, branch="E", configuration=p.ZEBRA_PC_V1)}
    route = routes.pin("D", "B", env_path=route_b_env, solver_block=blocks["D"], configuration=p.ZEBRA_PC_V1)
    kwargs = {"root": str(root), "data": {"pools": {z.BENCH: checked["pool"]}, "pinned": z.identity()["sealed"],
        "zebra_pc": z.identity(), "split_manifest": checked["split_manifest"], "s0_sha256": checked[p.RECORD_HASH],
        "test_read_estimate": estimates, "test_read_terms": terms, "launchable_chains": launchable,
        "snapshot_sha256": current_sha,
        "smoke_results": smoke_pins}, "sheet_qualification": None, "cards": {z.BENCH: z.CARD_TEXT},
        "contracts": {z.BENCH: {"text": z.CONTRACT, "sha": hashlib.sha256(z.CONTRACT.encode()).hexdigest()}},
        "runtime": {z.BENCH: dict(RUNTIME)}, "clients": {"solver": blocks, "roles": manifest.role_settings(p.ZEBRA_PC_V1),
        "routes": {"D": {"B": route}}}, "fixtures": {"sha256": digest(fixture_items())},
        "provenance": provenance_value}
    return manifest.make(out, evidence="smoke" if smoke_chain else p.REAL_RUN_EVIDENCE[p.ZEBRA_PC_V1],
                         measured=checked["measured"], limits={k: sandbox.Limits(**v) for k, v in checked["limits"].items()},
                         configuration=p.ZEBRA_PC_V1, environment_found=environment_found, **kwargs)


def _s1(setting, chain):
    first = chains.first_call(setting, chain)
    roles = {}
    for role in ("engineer", "examiner", "describer", "leakage"):
        name = "%s/zebra-smoke/S1/%s" % (chain, role)
        def work(attempt, role=role, name=name):
            endpoint = units.role_endpoint(setting, chain, role, z.BENCH, 1)
            if role == "engineer":
                endpoint = units._bounded_endpoint(endpoint, p.ENGINEER_MAX_TOKENS[p.ZEBRA_PC_V1])
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
                              configuration=p.ZEBRA_PC_V1)
        roles[role] = done["result"]
    return {"passed": first["passed"] and all(row["passed"] for row in roles.values()), "roles": roles,
            "solver_confirmation": first[p.RECORD_HASH]}


def _s2(setting, chain):
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
                          configuration=p.ZEBRA_PC_V1, drain=units.drainer(setting, chain, name))["result"]


def _scope_cells(chain):
    """The Zebra schedule prices every redo kind, including all six paired training rounds."""
    scopes = smoke._scope_cells(chain, p.ZEBRA_PC_V1)
    redo, totals = [], {}
    for k, bench in enumerate(p.PILOTS[p.ZEBRA_PC_V1]["order"], 1):
        for kind in budgets.STEP_KINDS:
            redo.extend(cells for cells in scopes[budgets.solver_scopes(chain, bench, k, kind, 2)[-1]] if cells)
            for b, (card, proc) in p.CONFIG_SCHEDULE_CELLS[p.ZEBRA_PC_V1][bench][kind].items():
                was = totals.get(b, (0, 0))
                totals[b] = (was[0] + card, was[1] + proc)
    for b, (card, proc) in p.TEST_READ_CELLS[p.ZEBRA_PC_V1].items():
        was = totals.get(b, (0, 0))
        totals[b] = (was[0] + card, was[1] + proc)
    scopes[chain + ":redo"] = redo
    scopes[chain + ":solver"] = [{b: (card + extra.get(b, (0, 0))[0], proc + extra.get(b, (0, 0))[1])
                                   for b, (card, proc) in totals.items()} for extra in redo]
    return scopes


def projection(s2, chain):
    """Measured card-cell costs; procedure costs remain explicitly assumed at the registered high factor."""
    card = s2["tokens_per_cell"]
    require(card > 0 and s2["items"] == 10, "S-E6 needs ten measured cells")
    ratio = s2["settled_tokens"] / s2["measurements"]["actual"]
    proc = card * float(p.PROCEDURE_ARM_FACTOR[1])
    size = s2["measurements"]["request_bytes"][z.BENCH]
    reserve = reservation(size, p.ledger_bound(p.CHAINS[chain], z.BENCH, branch="E" if chain == "D" else None))
    caps = budgets.chain_caps(chain, p.ZEBRA_PC_V1)
    scopes = {}
    for scope, alternatives in _scope_cells(chain).items():
        estimate = max((sum(card * c + proc * q for c, q in cells.values()) for cells in alternatives), default=0)
        need = math.ceil(estimate * ratio + reserve)
        scopes[scope] = {"projected": need, "cap": caps[scope], "passed": need <= caps[scope]}
    return {"passed": all(v["passed"] for v in scopes.values()), "configuration": p.ZEBRA_PC_V1,
            "chain": chain, "per_cell": {z.BENCH: {"card": card, "procedure": proc, "procedure_assumed": True}},
            "ratio": ratio, "scopes": scopes, "read_estimate": math.ceil(ratio * (200 * card + 1_000 * proc)),
            "other_chain": "not_projected; requires its own smoke"}


def run_stage(manifest_path, chain, stage, *, docker=None, transport=None):
    """S1 first calls; S2 ten card cells; S3 one fixture training round; SE6 measured projection."""
    require(stage in STAGES and chain in p.CHAINS, "A lean smoke stage and chain")
    m = manifest.load(manifest_path, docker=docker)
    require(m["configuration"] == p.ZEBRA_PC_V1 and m["evidence"] == "smoke", "An isolated zebra smoke manifest")
    setting = manifest.setting_of(m, chain, path=manifest_path, docker=docker, transport=transport)
    setting.budget.declare({**budgets.chain_caps(chain, p.ZEBRA_PC_V1), **budgets.first_call_caps(chain)})
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
            value = smoke_roles.zebra_training(setting, services, chain, fixture_items())
        else:
            value = projection(previous["S2"], chain)
        written = p.record("zebra-smoke-stage", "smoke", {"configuration": p.ZEBRA_PC_V1, "chain": chain,
                            "manifest": m[p.RECORD_HASH], "stage": stage, "result": value})
        write_json(path, written)
        if stage == "SE6":
            write_json(root / "result.json", p.record("zebra-smoke-result", "smoke", {
                "configuration": p.ZEBRA_PC_V1, "chain": chain, "manifest": m[p.RECORD_HASH],
                "stages": list(STAGES), "passed": value["passed"], "read_estimate": value["read_estimate"],
                "s0": m["data"]["s0_sha256"], "manifest_path": str(safe_path(manifest_path)),
                "snapshot_sha256": m["data"]["snapshot_sha256"], "sealed_reads": 0}))
        return written


def _checked_stage(path, m, chain, stage):
    value = p.verified(read_json(path), "zebra-smoke-stage")
    require(value.get("configuration") == p.ZEBRA_PC_V1 and value.get("manifest") == m[p.RECORD_HASH]
            and value.get("chain") == chain and value.get("stage") == stage,
            "A smoke stage belongs to this manifest, chain, configuration and stage")
    return value
