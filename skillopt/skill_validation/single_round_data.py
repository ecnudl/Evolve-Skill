"""Outcome-blind MBPP subset and a real, predetermined historical Skill.

Only static source parsing happens on the host. Benchmark assertions execute
only inside the caller's isolated executor. The first original assertion is
public to BOTH solver and verifier; all remaining assertions stay host-side.
This is a disclosed compatibility protocol, not canonical MBPP evaluation.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v11 import data as mbpp
from skillopt.validator_pilot.api import digest, write_immutable_json

from .checks import CallableTask, PublicCase
from .models import Obligation, SourceFile, TaskContract, require

VERSION = "skill-validation-single-round-mbpp-data-v1"
COUNTS = {"development": 8, "verifier_calibration": 4, "final": 16}
SEED = 20260918
PARENT_RUN = "outputs/coevolution_v16/pilot_20260915_a_clean_resume_20260916"


def _read(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink source unsupported")
    return verify(json.loads(path.read_text(encoding="utf-8")))


def _write(path, value):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink destination unsupported")
    write_immutable_json(path, value)


def _fingerprints(rows):
    """Conservative lexical components; NOT certified semantic family labels."""
    identifiers = sorted(row["task_id"] for row in rows)
    prompts = {row["task_id"]: " ".join(re.findall(r"\w+", row["prompt"].casefold())) for row in rows}
    parents = {identifier: identifier for identifier in identifiers}

    def root(identifier):
        while parents[identifier] != identifier:
            identifier = parents[identifier]
        return identifier

    for i, left in enumerate(identifiers):
        for right in identifiers[i + 1:]:
            a, b = prompts[left], prompts[right]
            # Length bound cheaply rejects impossible >=.90 SequenceMatcher pairs.
            if 2 * min(len(a), len(b)) / max(1, len(a) + len(b)) < .90:
                continue
            if SequenceMatcher(None, a, b, autojunk=False).ratio() >= .90:
                ra, rb = root(left), root(right)
                parents[max(ra, rb)] = min(ra, rb)
    return {identifier: f"mbpp-lexical-{root(identifier)}" for identifier in identifiers}


def select_identities(records, inventory, families, *, counts=None, seed=SEED):
    """Pure static selection, including historical exposure family closure."""
    counts = COUNTS if counts is None else counts
    require(set(counts) == set(COUNTS) and all(type(n) is int and n > 0 for n in counts.values()),
            "Explicit positive development/calibration/final counts required")
    require(type(seed) is int and 0 <= seed < 2**64, "Invalid reservation seed")
    excluded_ids = set(inventory["excluded_ids"])
    excluded_questions = set(inventory["excluded_question_sha256"])
    exposed_families = {families[r["task_id"]] for r in records
                        if r["task_id"] in excluded_ids or r["question_sha256"] in excluded_questions}
    pools, reasons = {p: [] for p in COUNTS}, Counter()
    for record in records:
        phase = {"train": "development", "validation": "verifier_calibration", "test": "final"}.get(record["source_split"])
        if phase is None:
            continue
        if not record["eligible"]:
            reasons[phase + ":static_incompatible"] += 1
        elif families[record["task_id"]] in exposed_families:
            reasons[phase + ":historical_exposure_or_near_duplicate"] += 1
        else:
            pools[phase].append(record)
    selected, used_families, used_questions = {}, set(), set()
    # Holdout has priority, as in the previous public-data reservation protocol.
    for phase in ("final", "verifier_calibration", "development"):
        chosen = []
        ranked = sorted(pools[phase], key=lambda r: hashlib.sha256(
            f"{VERSION}|{seed}|{phase}|{r['task_id']}".encode()).hexdigest())
        reasons[phase + ":available_before_cross_phase_dedup"] = len(ranked)
        for row in ranked:
            family = families[row["task_id"]]
            if family in used_families or row["question_sha256"] in used_questions:
                continue
            chosen.append({"task_id": row["task_id"], "original_task_id": f"mbpp:{row['task_id']}",
                           "partition": phase, "source_split": row["source_split"],
                           "question_sha256": row["question_sha256"], "family_id": family,
                           "source_row_hash": row["source_row_hash"], "compiled_hash": row["compiled_hash"]})
            used_families.add(family)
            used_questions.add(row["question_sha256"])
            if len(chosen) == counts[phase]:
                break
        require(len(chosen) == counts[phase],
                f"Insufficient unexposed lexical-family-disjoint {phase} tasks; do not lower counts silently")
        selected[phase] = chosen
    return selected, dict(sorted(reasons.items()))


def freeze_manifest(repo, output, *, dev_count=8, calib_count=4, final_count=16, seed=SEED):
    """Freeze identities before model calls; no answer/reference in the manifest."""
    repo, output = Path(repo).resolve(), Path(output).absolute()
    require(".." not in output.parts, "Parent traversal in output is unsupported")
    require(output.is_relative_to(repo / "outputs/skill_validation")
            and output != repo / "outputs/skill_validation", "Use a dedicated new-mainline output directory")
    require(not any(p.is_symlink() for p in (output, *output.parents)), "Symlink output unsupported")
    counts = {"development": dev_count, "verifier_calibration": calib_count, "final": final_count}
    snapshot = mbpp.load_snapshot(repo)
    settings = {"counts": counts, "seed": seed, "source_snapshot_hash": snapshot["record_hash"],
                "implementation_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest_path = output / "data_manifest.json"
    if manifest_path.exists():
        previous = _read(manifest_path)
        require(previous.get("version") == VERSION and previous["settings"] == settings,
                "Frozen reservation changed")
        inventory = _read(output / "exposure_inventory.json")
        require(inventory["record_hash"] == previous["exposure_inventory_hash"], "Exposure inventory changed")
        # Check the frozen files, rather than rediscovering subsequent experiment outputs as prior exposure.
        for item in inventory["files"]:
            path = repo / item["path"]
            require(not path.is_symlink() and path.is_file()
                    and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"],
                    "Historical exposure source changed")
        return previous
    rows = mbpp._source_rows(repo, snapshot)
    eligibility = mbpp.inspect_compatibility(repo)
    inventory = mbpp._history(repo, output, eligibility["records"])
    families = _fingerprints(rows)
    selected, counts_diagnostic = select_identities(eligibility["records"], inventory, families,
                                                   counts=counts, seed=seed)
    manifest = seal({"version": VERSION, "dataset": mbpp.DATASET,
                     "run_path": str(output.relative_to(repo)), "settings": settings,
                     "splits": selected, "pool_counts": counts_diagnostic,
                     "exposure_inventory_hash": inventory["record_hash"],
                     "source_snapshot_path": str(mbpp.DIRECTORY / "source_snapshot.json"),
                     "public_assertion_index": 0, "native_assertions_retained_in_H": True,
                     "lexical_grouping": "casefold-word-normalized SequenceMatcher>=0.90 connected components",
                     "structural_family_independence_certified": False,
                     "project_disjoint": False, "canonical_mbpp": False,
                     "extra_nonmutation_or_repeat_obligations": False})
    _write(output / "exposure_inventory.json", inventory)
    _write(manifest_path, manifest)
    return manifest


def _wrapper(assertions, entry_point, *, audit):
    """Build trusted test text, never execute it. Native tuple/set/bool semantics stay Python's."""
    require(bool(assertions), "No zero-check wrapper")
    functions = []
    for index, assertion in enumerate(assertions):
        body = "\n".join("        " + line for line in assertion.splitlines())
        success = "{'passed': True, 'exception': None}" if audit else "True"
        failure = "{'passed': False, 'exception': type(error).__name__}" if audit else "False"
        functions.append(f"def _case_{index}():\n    try:\n        from solution import {entry_point}\n"
                         + body + f"\n        return {success}\n    except MemoryError:\n        raise\n"
                         + f"    except Exception as error:\n        return {failure}\n")
    if audit:
        return "\n".join(functions) + "\ndef audit():\n    return [" + ", ".join(
            f"_case_{i}()" for i in range(len(assertions))) + "]\n"
    require(len(assertions) == 1, "Public wrapper gets exactly the first assertion")
    return "\n".join(functions) + "\ndef check():\n    return _case_0()\n"


def materialize_row(row, identity):
    require(digest(row) == identity["source_row_hash"], "Selected source row changed")
    compatible = mbpp._compatibility(row)
    require(compatible["eligible"] and digest(compatible["compiled"]) == identity["compiled_hash"],
            "Selected assertion compatibility changed")
    compiled = compatible["compiled"]
    public_assertion = row["test_list"][0]
    prompt = (row["prompt"] + "\n\nImplement the named Python function in solution.py.\n"
              + "Public native example (original assertion 0; Python assertion semantics):\n"
              + public_assertion)
    contract = TaskContract(identity["original_task_id"], identity["original_task_id"],
                            identity["family_id"], "mbpp-single-function-not-repository", identity["partition"],
                            "coding", "task_contract_conformance_not_assumed_nonmutation", prompt,
                            (Obligation("requested_behavior", "requested_behavior", row["prompt"], row["prompt"]),))
    case = PublicCase("original-assertion-0", '{"args":[],"kwargs":{}}', public_assertion,
                      ("requested_behavior",), expected_json="true")
    task = CallableTask(contract, "public_runner", "check", (case,))
    public_wrapper = SourceFile("public_runner.py", _wrapper([public_assertion], compiled["entry_point"], audit=False))
    hidden_wrapper = SourceFile("hidden_audit.py", _wrapper(row["test_list"], compiled["entry_point"], audit=True))
    return {"identity": identity, "task": task, "public_wrapper": public_wrapper.to_dict(),
            "host_audit": {"reference_code": row["code"], "compiled": compiled,
                           "native_assertions": list(row["test_list"]), "wrapper": hidden_wrapper.to_dict(),
                           "original_assertion_count": len(row["test_list"]),
                           "public_assertion_index": 0}}


def materialize_tasks(repo, manifest, partition, *, final_authorization=None):
    """Host-only payload; final requires the caller's already-frozen candidate identities."""
    repo = Path(repo).resolve()
    verify(manifest)
    require(manifest.get("version") == VERSION and partition in COUNTS, "Unknown data manifest or phase")
    root = repo / manifest["run_path"]
    require(".." not in root.parts, "Parent traversal in manifest is unsupported")
    require(root.is_relative_to(repo / "outputs/skill_validation") and _read(root / "data_manifest.json") == manifest,
            "Actual frozen manifest required")
    if partition == "final":
        require(type(final_authorization) is dict, "Final tasks require candidate freeze")
        verify(final_authorization)
        require(final_authorization.get("data_manifest_hash") == manifest["record_hash"]
                and type(final_authorization.get("candidate_skill_hashes")) is dict
                and set(final_authorization["candidate_skill_hashes"]) == {
                    "fixed", "adaptive_no_research", "adaptive_research"}
                and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
                        for value in final_authorization["candidate_skill_hashes"].values()),
                "Final authorization must bind all three frozen candidate Skills")
    snapshot = mbpp.load_snapshot(repo)
    require(snapshot["record_hash"] == manifest["settings"]["source_snapshot_hash"], "Source snapshot changed")
    rows = {row["task_id"]: row for row in mbpp._source_rows(repo, snapshot)}
    return [materialize_row(rows[item["task_id"]], item) for item in manifest["splits"][partition]]


def build_artifact_files(row, model_code, *, audit=False):
    require(type(model_code) is str and bool(model_code.strip()), "Actual nonempty model code required")
    wrapper = row["host_audit"]["wrapper"] if audit else row["public_wrapper"]
    return (SourceFile("solution.py", model_code), SourceFile.from_dict(wrapper))


def freeze_parent(repo, output):
    """First fixed-validator Coding update, h0/r0, chosen without new outcomes."""
    repo, output = Path(repo).resolve(), Path(output).absolute()
    source = repo / PARENT_RUN
    checkpoint = _read(source / "checkpoints/round_0.json")
    update = _read(source / "learning/h0-r0-fixed.json")
    frozen = _read(source / "final_frozen.json")
    receipt_path = source / "api/calls" / (update["request_hash"] + ".json")
    receipt = json.loads(receipt_path.read_text())
    skill = checkpoint["skills"][0]["fixed"]["skill"]
    skill_hash = hashlib.sha256(skill.encode()).hexdigest()
    require(checkpoint["record_hash"] in frozen["checkpoint_hashes"]
            and update["record_hash"] in frozen["skill_update_hashes"]
            and update["record_hash"] in checkpoint["completed_updates"]
            and update["history"] == update["round"] == 0 and update["arm"] == "fixed"
            and update["valid"] and update["changed"] and update["skill_hash"] == skill_hash
            and update["state"]["skill"] == skill and update["api_receipt_hash"] == digest(receipt)
            and receipt["ok"] and receipt["request_hash"] == update["request_hash"]
            and digest(receipt["request"]) == update["request_hash"],
            "Parent does not bind the actual recorded first Coding update")
    record = seal({"version": VERSION + "-parent", "text": skill, "skill_hash": skill_hash,
                   "source_run": PARENT_RUN, "history": 0, "round": 0, "arm": "fixed",
                   "checkpoint_hash": checkpoint["record_hash"], "update_hash": update["record_hash"],
                   "api_receipt_hash": update["api_receipt_hash"], "source_final_freeze_hash": frozen["record_hash"],
                   "selection_rule": "first fixed-validator update of first historical learning history",
                   "source_is_synthetic_coding": True, "new_outcomes_used_for_parent_selection": False,
                   "historical_content_not_authorized_contract_or_deployment": True})
    _write(output / "parent_skill.json", record)
    return record
