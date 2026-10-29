"""Instruction-start preparation and structural smoke, without sealed-panel reads.

The structural smoke is a zero-call prelaunch receipt, not a measured model smoke.
Main-v3 real manifests still require the inherited measured smoke/read-cost receipt.
The baseline has no procedure sandbox or method-role smoke: its chain confirms its
solver, then reads C/B once and writes the usual chain/read/per-bench unit records.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction
import hashlib
import math
import shutil
import sys

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import budgets, chain, evaluation, exclusion, instruction_start, manifest, prelaunch, profiles as p, routes, step
from .sandbox import client as sandbox

S0_FILE = "v210-s0.json"
PREPARATION = "/data/execskill-20261024-main-v2-2-manifest.json"


def _profile(configuration):
    require(p.is_v210(configuration), "A registered instruction-start configuration")


def snapshot(out, *, source, git_head, configuration):
    _profile(configuration)
    source, out = safe_path(source), safe_path(out)
    require(not out.exists() and not out.is_relative_to(source), "A new snapshot outside the checkout")
    paths = prelaunch._files(source)
    instruction_file = source / "docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json"
    paths.append(instruction_file)
    require(all(not path.is_symlink() and not any(term in path.name.lower() for term in
                (".env", "sealed-holdout", "private-api", "api-cache")) for path in paths),
            "Snapshot source contains a private file or link")
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
    """Copy main-v2-2 metadata by value; never open its pinned files or upstream directories."""
    path = safe_path(path)
    source = manifest.load(path, verify=False)
    require(source["configuration"] == p.MAIN_V2_2, "v2.10 inherits the main-v2-2 preparation")
    data = deepcopy(source["data"])
    require({"exclusion", "pinned", "pools", "research", "searchqa_tail", "test_read_estimate",
             "test_read_terms"} <= set(data), "Preparation carries the main-v2-2 data fields")
    require(all(isinstance(data[key], dict) and set(data[key]) == set(p.CHAINS)
                for key in ("test_read_estimate", "test_read_terms"))
            and all(type(value) is int for value in data["test_read_estimate"].values()),
            "Preparation carries both chains' read estimates and terms")
    require(set(data.get("pools", {})) == set(p.BENCHES), "Preparation pins all five supplies")
    pinned = data["pinned"]
    require(set(pinned) == {"paths", "sha256"}, "Preparation carries paths and hashes")
    paths = pinned["paths"]
    groups = {"test": {"alfworld", "searchqa", "spreadsheetbench"},
              "layouts": {"livemath", "officeqa"}, "upstream": {"livemath", "officeqa"},
              "train": set(p.BENCHES), "val": set(p.BENCHES)}
    require(set(paths) == set(groups) | {"split", "alfworld_data"},
            "Preparation pins the main-v2-2 data paths")
    for group, benches in groups.items():
        require(isinstance(paths[group], dict) and set(paths[group]) == benches,
                "Preparation pins the main-v2-2 " + group + " paths")
    require(all(type(value) is str and value for value in
                [paths["split"], paths["alfworld_data"],
                 *(value for group in groups for value in paths[group].values())]),
            "Preparation data paths are nonempty strings")

    def sha256(value):
        return type(value) is str and len(value) == 64 and set(value) <= set("0123456789abcdef")

    # coevo5.data.pin hashes files; upstream and alfworld_data are directories.
    files = [paths["split"], *(value for group in ("test", "layouts", "train", "val")
                             for value in paths[group].values())]
    require(isinstance(pinned["sha256"], dict)
            and all(sha256(pinned["sha256"].get(str(safe_path(value)))) for value in files),
            "Preparation carries the pinned file hashes")
    sealed = {safe_path(value) for value in [paths["split"],
              *(value for group in ("test", "layouts", "upstream") for value in paths[group].values())]}
    supplies = [*data["pools"].values(), data["searchqa_tail"]]
    require(all(isinstance(entry, dict) and set(entry) == {"path", "sha256"}
                and type(entry["path"]) is str and entry["path"] and sha256(entry["sha256"])
                for entry in supplies), "Preparation pins supply paths and hashes")
    require(all(safe_path(entry["path"]) not in sealed for entry in supplies),
            "Supplies are separate from the sealed test panels")
    require(exclusion.SEARCHQA_RUN == "searchqa_test_exclusion"
            and exclusion.ALFWORLD_RUN == "alfworld_test_identity_check",
            "The inherited exclusion run names are unchanged")
    require(set(data["exclusion"]) == {exclusion.SEARCHQA_RUN, exclusion.ALFWORLD_RUN, "test_canaries"},
            "Preparation carries exclusion records and canaries by value")
    records = {}
    for name, pin in data["exclusion"].items():
        require(isinstance(pin, dict) and set(pin) == {"path", "record_sha256"}
                and type(pin["path"]) is str and pin["path"] and sha256(pin["record_sha256"])
                and safe_path(pin["path"]) not in sealed, "Preparation pins an exclusion record")
        # verified expands test-canaries to fivebench-execskill-v1-test-canaries.
        value = p.verified(read_json(pin["path"]), "test-canaries" if name == "test_canaries" else exclusion.RECORD_KIND)
        require(value[p.RECORD_HASH] == pin["record_sha256"], "The exclusion record differs from its pin")
        records[name] = value
    searchqa, alfworld = records[exclusion.SEARCHQA_RUN], records[exclusion.ALFWORLD_RUN]
    require(searchqa["run"] == exclusion.SEARCHQA_RUN and searchqa["exclusion_sha256"] == digest(searchqa["dropped"])
            and alfworld["run"] == exclusion.ALFWORLD_RUN and alfworld["disjoint"] is True
            and len({value["consent_sha256"] for value in records.values()}) == 1,
            "The imported exclusions are one consented, passing preparation")
    require(set(source["contracts"]) == set(source["runtime"]) == set(p.BENCHES)
            and isinstance(source["fixtures"], dict)
            and set(source["sheet_qualification"]) == {"path", "record_hash"},
            "Preparation carries five-bench contracts, runtime, qualification and fixtures")
    for bench, contract in source["contracts"].items():
        require(contract["sha"] == hashlib.sha256(contract["text"].encode()).hexdigest(),
                "The inherited contract pin")
    return {"registration": {"preparation": {"path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "record_sha256": source[p.RECORD_HASH]},
                "supplies_sha256": digest(data["pools"]), "exclusion_sha256": digest(records)},
            "data": data, "exclusion_records": records, "cards": deepcopy(source["cards"]),
            "contracts": deepcopy(source["contracts"]), "runtime": deepcopy(source["runtime"]),
            "sheet_qualification": deepcopy(source["sheet_qualification"]),
            "fixtures": deepcopy(source["fixtures"])}


def collect_s0(out, *, preparation_file, root, configuration, snapshot_root=None, selftest=None,
               sheet_runtime=None, checks=None):
    _profile(configuration)
    out, root = safe_path(out), safe_path(root)
    require(not (out / S0_FILE).exists(), "S0 is written once")
    require(not out.is_relative_to(manifest.REPO), "Preparation artifacts live outside the repository")
    allowed = evaluation.consent(root / "shared", configuration)
    imported = preparation(preparation_file)
    original = imported["cards"]
    active = instruction_start.active_cards(original, configuration)
    baseline = configuration == p.BASELINE_V210
    if baseline:
        require(selftest is None, "The baseline does not need a procedure sandbox selftest")
        tested = None
        measured = {key: None for key in manifest.MEASURED_FIELDS}
        limits = {key: asdict(value) for key, value in sandbox.LIMITS.items()}
    else:
        require(selftest is not None, "main-v3 requires the inherited passing sandbox selftest")
        tested = p.verified(read_json(selftest), "sandbox-selftest")
        require(tested.get("passed") is True, "A passing procedure sandbox selftest")
        measured, limits = deepcopy(tested["measured"]), deepcopy(tested["limits"])
        require(set(measured) == manifest.MEASURED_FIELDS, "Complete S0 measurements")
    snapshot_root = safe_path(snapshot_root or manifest.REPO)
    from . import sheet_runtime as launch_sheet
    sheet = launch_sheet.read(sheet_runtime, snapshot_root=snapshot_root) if sheet_runtime is not None else None
    checked = prelaunch.zero_call_checks(snapshot_root, python=sys.executable) if checks is None else checks
    imports = {}
    if not baseline:
        from . import v210_import
        imports["alfworld_v11_import"] = v210_import.pins()
    value = p.record("v210-s0", "smoke", {"configuration": configuration, "root": str(root),
        **imported, "instructions": instruction_start.pins(),
        "launch_sheet_runtime": sheet,
        "instruction_start": instruction_start.START, "blank_arm": instruction_start.blank_definition(),
        "card_sha256": {bench: hashlib.sha256(text.encode()).hexdigest() for bench, text in original.items()},
        "active_cards": active,
        "consent": deepcopy(allowed), "consent_sha256": digest(allowed), **imports,
        "sandbox_required": not baseline, "sandbox": tested[p.RECORD_HASH] if tested else None,
        "limits": limits, "measured": measured,
        "measured_basis": "not applicable; no procedure sandbox" if baseline else "passing sandbox selftest",
        "pytest": checked, "sealed_reads": 0,
        "training_units": [] if baseline else list(step.training_units(configuration)),
        "snapshot_root": str(snapshot_root),
        "snapshot_sha256": hashlib.sha256(prelaunch.sha256_list(snapshot_root).encode()).hexdigest(),
        "passed": checked.get("passed") is True})
    write_json(out / S0_FILE, value)
    return value


def _bind_exclusion(root, imported):
    bound = {}
    for name, value in imported["exclusion_records"].items():
        target = root / (p.CANARIES if name == "test_canaries" else exclusion.EXCLUSION_DIR + "/" + name + ".json")
        if target.exists():
            require(read_json(target) == value, "An imported exclusion record changed")
        else:
            write_json(target, value)
        bound[name] = {"path": str(target), "record_sha256": value[p.RECORD_HASH]}
    return bound


def make_manifest(out, *, root, s0_file, provenance, roles_repo, route_b_env, configuration, sheet_runtime,
                  smoke_chain=None, measured_smoke=None, environment_found=None):
    _profile(configuration)
    checked = p.verified(read_json(s0_file), "v210-s0")
    require(checked["passed"] and checked["configuration"] == configuration, "A passing configured v2.10 S0")
    root = safe_path(root)
    require(smoke_chain in (None, "G", "D"), "The two registered solver chains")
    require(smoke_chain is not None or str(root) == p.RUN_ROOTS[configuration], "The registered real run root")
    allowed = evaluation.consent(root / "shared", configuration)
    require(digest(allowed) == checked["consent_sha256"], "S0 and manifest bind the same exact consent")
    imported = preparation(checked["registration"]["preparation"]["path"])
    require(all(checked[key] == value for key, value in imported.items()), "The preparation still matches S0")
    from . import sheet_runtime as launch_sheet
    sheet = launch_sheet.for_manifest(sheet_runtime, checked, snapshot_root=manifest.REPO)
    require(checked["active_cards"] == instruction_start.active_cards(imported["cards"], configuration),
            "S0 pins the historical instruction cards unchanged")
    require(checked["instructions"] == instruction_start.pins(), "Instruction pins differ from the frozen fixture")
    require(checked.get("instruction_start") == instruction_start.START,
            "S0 records the historical instruction-card definition")
    require(checked.get("blank_arm") == instruction_start.blank_definition(), "S0 pins a blank arm without guidance")
    require(checked.get("card_sha256") == {bench: row["sha256"] for bench, row in instruction_start.pins().items()},
            "S0 card hashes equal the frozen instruction hashes")
    if configuration == p.MAIN_V3:
        from . import v210_import
        require(checked.get("alfworld_v11_import") == v210_import.pins(), "The import differs from S0")
    provenance_value = read_json(provenance)
    current_sha = hashlib.sha256(prelaunch.sha256_list(manifest.REPO).encode()).hexdigest()
    require(checked["snapshot_sha256"] == current_sha == provenance_value.get("sha256_list_sha256")
            and safe_path(checked["snapshot_root"]) == manifest.REPO
            and safe_path(provenance_value["snapshot_root"]) == manifest.REPO,
            "S0 and provenance certify the current snapshot")
    per_cell = {bench: {"card": p.CELL_ANCHORS[bench][1], "procedure_assumed": True} for bench in p.BENCHES}
    terms = p.read_estimate_terms(per_cell, 1, configuration)
    estimate = math.ceil(sum(terms.values()))
    readiness = {"measured": False, "basis": "registered anchors; first actual response gates the chain"}
    if measured_smoke is not None:
        measured = chain.read_estimate_record(measured_smoke, configuration)
        require(measured["evidence"] == "smoke", "Measured readiness requires real smoke evidence")
        terms = {bench: Fraction(value) for bench, value in measured["terms"].items()}
        estimate = measured["value"]
        readiness = {"measured": True, "receipt": measured}
    require(configuration == p.BASELINE_V210 or smoke_chain is not None or readiness["measured"],
            "main-v3 requires its measured smoke; structural smoke is not measured readiness")
    blocks = {"G": manifest.solver_block("G", env_path=roles_repo, configuration=configuration),
              "D": manifest.solver_block("D", env_path=route_b_env, branch="N", longest=routes.S1B_CEILING,
                                         configuration=configuration)}
    data = {**imported["data"], "exclusion": _bind_exclusion(root, imported),
        "launch_sheet_runtime": sheet, "inherited_sheet_runtime": launch_sheet.inherited(imported),
        "v210_preparation": imported["registration"], "s0_sha256": checked[p.RECORD_HASH],
        "snapshot_sha256": current_sha, "launchable_chains": [smoke_chain] if smoke_chain else ["G", "D"],
        "readiness": readiness, "test_read_estimate": {c: estimate for c in p.CHAINS},
        "test_read_terms": {c: {b: str(v) for b, v in terms.items()} for c in p.CHAINS}}
    return manifest.make(out, evidence="smoke" if smoke_chain else p.REAL_RUN_EVIDENCE[configuration],
        measured=checked["measured"], limits={key: sandbox.Limits(**value) for key, value in checked["limits"].items()},
        environment_found=environment_found, configuration=configuration, root=str(root), data=data,
        cards=imported["cards"], contracts=imported["contracts"],
        runtime={**imported["runtime"], "spreadsheetbench": sheet["runtime"]},
        sheet_qualification=sheet["qualification"], fixtures=imported["fixtures"], provenance=provenance_value,
        clients={"solver": blocks, "roles": manifest.role_settings(configuration), "routes": {"D": {"B":
            routes.pin("D", "B", env_path=route_b_env, solver_block=blocks["D"], configuration=configuration)}}})


def structural_smoke(manifest_path, *, out, configuration):
    """Zero-call smoke: identity, consent, cards, imports and registered caps only."""
    _profile(configuration)
    value = manifest.load(manifest_path, verify=False)
    require(value["configuration"] == configuration, "The configured smoke manifest")
    manifest.verify_code(value)
    allowed = evaluation.consent(safe_path(value["root"]) / "shared", configuration)
    result = p.record("v210-structural-smoke", "engineering_fixture", {"configuration": configuration,
        "manifest": value[p.RECORD_HASH], "passed": True, "model_calls": 0, "sealed_reads": 0,
        "instruction_start": instruction_start.START, "blank_arm": instruction_start.blank_definition(),
        "measured_readiness": False, "read_arms": list(p.read_arms_of(configuration)),
        "consent_sha256": digest(allowed), "caps_sha256": digest(budgets.caps(configuration)),
        "sandbox_required": configuration != p.BASELINE_V210})
    require(not safe_path(out).exists(), "A structural smoke receipt is written once")
    write_json(out, result)
    return result
