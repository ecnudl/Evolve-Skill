"""Prepare/check a real selected Coding Skill's full S1 evaluation; no API.

Run from ops with PYTHONPATH pointing at the baseline's frozen evaluation tree.
S0 checkpoints are registered by freeze_plan but are never executed or populated
with another run's predictions. SearchQA is raw Coding-Skill transfer.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval.core import (
    freeze_plan,
    load_checkpoint,
    load_plan,
    read_json,
    register_checkpoint,
    require,
    runtime_identity,
    safe_path,
    source_identity,
    write_json,
)
from skillopt.continual_eval.datasets import load_panel, panel_hash
from skillopt.continual_learning.contracts import check_skill
from skillopt.continual_learning.gepa import official_gepa
from skillopt.continual_learning.ledger import Ledger
from skillopt.continual_learning.skillopt import _stage_artifacts
from skillopt.validator_pilot.api import digest

VERSION = "selected-coding-skill-evaluation-preparation-v2"
SHADOW_VERSION = "continual-feedback-policy-ablation-v1"
SHADOW_ARMS = {"generic_summary", "conditional_mechanism"}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


@contextmanager
def _read_lock(root):
    with safe_path(root / ".writer.lock").open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Source evidence has an active writer") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _source(root, hashes, files):
    require(type(hashes) is dict and hashes, "Missing frozen source identity")
    for name, expected in hashes.items():
        path = safe_path(root / "skillopt" / name)
        require(path.is_relative_to(root / "skillopt") and _sha(path) == expected, "Frozen source changed")
        files[str(path)] = expected


def _inputs(learning, learning_source, baseline, eval_source, gepa_source):
    plan = load_plan(baseline)
    require(plan["version"] == "continual-eval-v2" and plan["config"]["partition"] == "development"
            and plan["repeats"] == 2 and plan["config"]["methods"] == ["no_skill"]
            and plan["config"]["histories"] == ["h0"] and plan["order"][0] == "bigcodebench",
            "Expected Coding-first, two-repeat common-budget development baseline")
    require(plan["source_identity"] == source_identity() and plan["host_runtime"] == runtime_identity(),
            "Use the frozen baseline evaluation package/runtime")
    present = [b for b, row in plan["panels"].items() if row["status"] == "present"]
    require(len(present) == 1 and present[0] in {"bigcodebench", "searchqa"}, "Only single-panel Coding or SearchQA supported")
    benchmark = present[0]
    panel_path = safe_path(plan["panels"][benchmark]["path"])
    panel = load_panel(panel_path)
    require(panel_hash(panel) == plan["panels"][benchmark]["panel_hash"] and len(panel["tasks"]) == 400
            and all(t["partition"] == "development" for t in panel["tasks"]), "Full 400-task development panel required")
    result = read_json(learning / "result.json", sealed=True)
    require(result["status"] == "completed", "Pending learning cannot publish S1")
    files = {str(p): _sha(p) for p in (baseline / "plan.json", panel_path, learning / "result.json")}
    branch = "protocol_hash" in result
    envelope_path = learning / ("protocol.json" if branch else "identity.json")
    envelope = read_json(envelope_path, sealed=True)
    require(envelope["record_hash"] == result["protocol_hash" if branch else "identity_hash"], "Learning result binding differs")
    manifest = verify(envelope["manifest"])
    shadow = branch and envelope.get("version") == SHADOW_VERSION
    fixture = manifest["model"]["provider"] == "fixture"
    require(manifest["model"] == plan["config"]["model"] and manifest["model"]["max_tokens"] == 65536
            and manifest["parent_skill"] == "" and manifest["host_runtime"] == plan["host_runtime"],
            "Learning model, empty parent or host identity differs")
    expected_kind = "engineering_fixture" if fixture else "natural_development_learning"
    require(result["evidence_kind"] == manifest["evidence_kind"] == expected_kind, "Learning provenance differs")
    learned_panel_path = learning / "panel.json"
    learned_panel = load_panel(learned_panel_path)
    require(learned_panel["benchmark"] == "bigcodebench" and digest(learned_panel) == manifest["panel_hash"]
            and all(t["partition"] == "development" for t in learned_panel["tasks"]), "Only Coding development learning allowed")
    authorized = {digest(t): "train" if t["family_id"] in manifest["train_families"] else "selection"
                  for t in learned_panel["tasks"]}
    require(authorized == manifest["authorized_tasks"] and not set(manifest["train_families"]) & set(manifest["selection_families"])
            and set(manifest["train_families"]) | set(manifest["selection_families"])
                == {t["family_id"] for t in learned_panel["tasks"]}, "Learning task/family role binding differs")
    if not fixture:
        require(len(learned_panel["tasks"]) == 129 and list(authorized.values()).count("train") == 65
                and list(authorized.values()).count("selection") == 64, "Original 65/64 learning roster required")
    if benchmark == "bigcodebench":
        require(manifest["runtime"] == plan["config"]["runtime"]["bigcodebench"], "Coding native configuration differs")
        require(set(authorized) <= {digest(t) for t in panel["tasks"]}, "Coding evaluation omits source tasks")
    ledger = Ledger(learning, manifest, None)
    costs = ledger.snapshot()
    require(costs == result["new_costs" if branch else "costs"] and costs["usage_complete"]
            and costs["unclosed_calls"] == 0, "Learning costs incomplete or changed")
    expected_artifacts = _stage_artifacts(learning, ledger) if branch else ledger.artifacts()
    if shadow:
        require(read_json(learning / "started.json", sealed=True)["protocol_hash"] == envelope["record_hash"],
                "Shadow start does not bind to its protocol")
        expected_artifacts.update({name: _sha(learning / name) for name in ("started.json", "model_service.json")
                                   if (learning / name).exists()})
    require(result["artifacts"] == expected_artifacts, "Learning artifacts changed")
    service = read_json(learning / "model_service.json", sealed=True)
    require(service == read_json(baseline / "model_service.json", sealed=True), "Actual baseline/learning model service differs")
    service.pop("record_hash")
    for path in (learning / "calls").glob("*.json"):
        row = read_json(path, sealed=True)
        receipt = row["receipt"]
        require(receipt["request"]["service"] == service and receipt["request"]["model"] == manifest["model"]["name"]
                and receipt["request"]["max_tokens"] == manifest["budget"][row["role"] + "_max_tokens"],
                "Actual learning service/model/budget differs")
        if not fixture:
            require(receipt.get("returned_model") == manifest["model"]["name"], "Returned learning model differs")
            cache = learning / "api/calls" / (receipt["request_hash"] + ".json")
            require(read_json(cache) == receipt, "Learning cache/receipt binding differs")
            files[str(cache)] = _sha(cache)
    if branch:
        if shadow:
            require(envelope.get("arm") in SHADOW_ARMS and result.get("arm") == envelope["arm"]
                    and manifest["method"] == "shadow_" + envelope["arm"]
                    and manifest["version"] == SHADOW_VERSION
                    and all(value.get("shadow_only") is True and value.get("research_rubric_method") is False
                            and value.get("compute_matched_baseline") is False for value in (result, envelope))
                    and result["selection_not_closed"] == 0, "Unsupported or mislabeled shadow study")
        else:
            require(envelope["version"] == manifest["version"] == "skillopt-frozen-evidence-reproposal-v1"
                    and manifest["method"] == "skillopt", "Unsupported proposal branch")
        require(envelope["current_sources"] == manifest["source_identity"]
                and result["inherited_costs"] == envelope["inherited_costs"]
                and result["inherited_costs"]["usage_complete"], "Unsupported proposal branch or inherited costs")
        require(result["gate_action"] in {"accept", "accept_new_best"}
                and result["selected_skill"] == result["candidate_skill"]
                and result["selection_closed" if shadow else "selection_completed"] == 64 and result["selection_unknown"] == 0,
                "Branch must actually select a complete nonempty candidate")
        skill = result["selected_skill"]
        _source(learning_source, envelope["native_sources"], files)
        for name, expected in envelope["original_files"].items():
            require(_sha(Path(name)) == expected, "Inherited branch evidence changed")
            files[name] = expected
    else:
        require(manifest["method"] == "gepa" and manifest["version"] == "continual-learning-v2", "Only completed GEPA or reviewed proposal branches supported")
        if not fixture:
            require(gepa_source is not None, "Natural GEPA needs its pinned official source")
            _, official_sources = official_gepa(gepa_source)
            require(official_sources == envelope["official_sources"], "Official GEPA source binding differs")
            for name, expected in official_sources.items():
                files[str(safe_path(gepa_source / "src/gepa" / name))] = expected
        official = result["official_result"]
        candidates, scores = official["candidates"], official["val_aggregate_scores"]
        require(len(candidates) == len(scores) > 0 and all(type(x) in (int, float) and 0 <= x <= 1 for x in scores),
                "Invalid official candidate/score roster")
        # Exactly the pinned GEPAResult.best_idx tie-breaking, no new selection.
        best = max(range(len(scores)), key=lambda i: scores[i])
        skill = candidates[best]["skill"]
        require(skill == result["candidate_skill"], "Reported Skill is not the official selected candidate")
    check_skill(skill)
    require(skill.strip(), "Empty/no-update Skill cannot create new S1 samples")
    if not fixture:
        # Bind the selected text to its complete existing selection evidence,
        # without executing it again or consulting serialized optimizer state.
        selected = {}
        for path in (learning / "evaluations").glob("*.json"):
            row = read_json(path, sealed=True)
            request = row["request"]
            require(path.stem == digest(request)
                    and read_json(learning / "evaluation_intents" / path.name, sealed=True) == seal(request)
                    and request["manifest_hash"] == manifest["record_hash"]
                    and authorized.get(request["task_hash"]) == request["role"]
                    and request["repeat"] == 0, "Learning evaluation identity differs")
            if request["role"] == "selection" and request["candidate_hash"] == digest({"skill": skill}):
                score = row["score"]
                require(score["status"] in {"pass", "fail"} and type(score["score"]) in (int, float)
                        and score["score"] in (0, 1) and request["task_hash"] not in selected,
                        "Selected candidate has unknown or duplicate evidence")
                selected[request["task_hash"]] = score["score"]
        require(set(selected) == {task for task, role in authorized.items() if role == "selection"}
                and len(selected) == 64, "Selected candidate lacks complete frozen selection evidence")
        reported_score = result["candidate_score"] if branch else scores[best]
        require(sum(selected.values()) / 64 == reported_score, "Selected candidate score differs from its evidence")
    _source(learning_source, manifest["source_identity"], files)
    _source(eval_source, plan["source_identity"], files)
    files.update({str(learning / relative): expected for relative, expected in expected_artifacts.items()})
    for path in (envelope_path, learned_panel_path, learning / "model_service.json", baseline / "model_service.json"):
        files[str(path)] = _sha(path)
    return plan, panel, manifest, result, skill, benchmark, files


def prepare(learning_root, learning_source, baseline_root, eval_source, output, *, gepa_source=None):
    learning, learning_source, baseline, eval_source, root = map(safe_path,
        (learning_root, learning_source, baseline_root, eval_source, output))
    gepa_source = safe_path(gepa_source) if gepa_source is not None else None
    require(not root.exists() and not any(root.is_relative_to(p) or p.is_relative_to(root)
        for p in (learning, learning_source, baseline, eval_source)), "Use a new independent evaluation study")
    with _read_lock(learning), _read_lock(baseline):
        plan, panel, manifest, result, skill, benchmark, files = _inputs(learning, learning_source, baseline, eval_source, gepa_source)
        config = deepcopy(plan["config"])
        config["methods"].append(manifest["method"])
        config["panels"][benchmark] = str(root / "data/panel.json")
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "data/panel.json", panel)
        write_json(root / "learning_manifest.json", manifest)
        write_json(root / "config.json", config)
        new_plan = freeze_plan(config, root / "run")
        checkpoint = register_checkpoint(root / "run", manifest["method"], "h0", 1, skill,
            provenance="Completed development-selected Coding Skill; learning result " + result["record_hash"], _plan=new_plan)
        prepared = {str(p): _sha(p) for p in root.rglob("*.json")}
        value = seal({"version": VERSION, "status": "prepared_not_launched", "study_root": str(root),
            "learning_root": str(learning), "learning_source": str(learning_source), "baseline_root": str(baseline),
            "eval_source": str(eval_source), "gepa_source": str(gepa_source) if gepa_source else None,
            "original_files": files, "prepared_files": prepared, "preparer_sha256": _sha(Path(__file__)),
            "baseline_plan_hash": plan["record_hash"], "plan_hash": new_plan["record_hash"],
            "checkpoint_hash": checkpoint["record_hash"], "learning_manifest_hash": manifest["record_hash"],
            "learning_result_hash": result["record_hash"], "skill_hash": checkpoint["skill_hash"],
            "benchmark": benchmark, "method": manifest["method"], "history": "h0", "stage": 1,
            **({"shadow_only": True, "research_rubric_method": False, "compute_matched_baseline": False}
               if manifest["version"] == SHADOW_VERSION else {}),
            "learning_protocol": manifest["version"],
            "tasks": 400, "repeats": 2, "positions": 800, "model_calls": 0,
            "s0_executed": False, "baseline_receipts_imported": False, "old_results_replaced": False,
            "evidence_kind": "engineering_fixture" if manifest["model"]["provider"] == "fixture" else "prepared_development_evaluation",
            "evaluation_mode": "source_domain" if benchmark == "bigcodebench" else "raw_coding_skill_transfer_no_target_learning",
            "deployment_authorized": False, "independent_final_evidence": False})
        write_json(root / "preparation.json", value)
        return value


def check(output):
    root = safe_path(output)
    value = read_json(root / "preparation.json", sealed=True)
    require(value["version"] == VERSION and value["study_root"] == str(root)
            and value["preparer_sha256"] == _sha(Path(__file__)), "Preparation identity/source changed")
    learning, baseline = safe_path(value["learning_root"]), safe_path(value["baseline_root"])
    with _read_lock(learning), _read_lock(baseline):
        for field in ("original_files", "prepared_files"):
            require(all(_sha(Path(p)) == expected for p, expected in value[field].items()), "Frozen input/prepared file changed")
        _, _, manifest, result, skill, benchmark, files = _inputs(learning, safe_path(value["learning_source"]), baseline,
            safe_path(value["eval_source"]), safe_path(value["gepa_source"]) if value["gepa_source"] else None)
        new_plan = load_plan(root / "run")
        cp = load_checkpoint(root / "run", manifest["method"], "h0", 1, new_plan)
        require(files == value["original_files"] and result["record_hash"] == value["learning_result_hash"]
                and new_plan["record_hash"] == value["plan_hash"] and cp["record_hash"] == value["checkpoint_hash"]
                and cp["skill_text"] == skill and benchmark == value["benchmark"], "Prepared S1 binding differs")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check", action="store_true")
    for name in ("learning-root", "learning-source", "baseline-root", "eval-source", "gepa-source"):
        parser.add_argument("--" + name)
    args = vars(parser.parse_args(argv))
    checking = args.pop("check")
    require(checking or all(args[k] for k in ("learning_root", "learning_source", "baseline_root", "eval_source")), "Source paths required")
    value = check(args["output"]) if checking else prepare(**args)
    print(json.dumps({k: value[k] for k in ("record_hash", "plan_hash", "checkpoint_hash", "benchmark", "method", "positions", "model_calls")}
        | {"status": "validated_not_launched" if checking else value["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
