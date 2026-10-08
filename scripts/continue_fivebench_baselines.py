"""Finite sequential baseline attempts; historical evaluation is explicitly reused.

The ``worker`` command deliberately runs under each original evaluation source
and Python environment. No historical source, prediction or score is rewritten.
This is development orchestration, not a new independent final experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, read_json, require, runtime_identity, safe_path, write_json
from skillopt.validator_pilot.api import digest

VERSION = "fivebench-sequential-attempts-v1"
RECOVERY_SEQUENCE = "fivebench-sequential-attempts-v2"
# V3 runs the same SkillOpt-only queue with learning v5 closed-delivery fixes.
DELIVERY_SEQUENCE = "fivebench-sequential-attempts-v3"
# V4 runs SkillOpt and GEPA with learning v7 (raised Skill interface). New
# policies are evaluated in a derived source that differs from the frozen
# No-Skill source only in the checkpoint Skill-budget literal.
BUDGET_SEQUENCE = "fivebench-sequential-attempts-v4"
RECOVERY_SEQUENCES = {RECOVERY_SEQUENCE, DELIVERY_SEQUENCE, BUDGET_SEQUENCE}
LAUNCHERS = {RECOVERY_SEQUENCE: "run_skillopt_generalization_linux.sh",
             DELIVERY_SEQUENCE: "run_skillopt_generalization_e_linux.sh",
             BUDGET_SEQUENCE: "run_fivebench_f_linux.sh"}
BUDGET_SOURCE_EDITS = {"skillopt/continual_eval/core.py": "len(skill_text.encode()) <= 6000",
                       "skillopt/continual_eval/truncation_recovery.py": "len(skill.encode()) <= 6000"}


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def split_panel(panel, train_count, selection_count, seed):
    """Outcome-blind family selection; never select successful old positions."""
    from skillopt.continual_eval.datasets import validate_panel

    validate_panel(panel)
    require(all(t["partition"] == "development" for t in panel["tasks"]), "Development only")
    require(type(train_count) is int and type(selection_count) is int
            and min(train_count, selection_count) > 0, "Positive family counts required")
    families = sorted({t["family_id"] for t in panel["tasks"]},
                      key=lambda f: digest([seed, panel["benchmark"], f]))
    require(len(families) >= train_count + selection_count, "Insufficient independent families")
    train = families[:train_count]
    selection = families[train_count:train_count + selection_count]
    roles = dict.fromkeys(train, "train") | dict.fromkeys(selection, "selection")
    project_roles = {}
    tasks = [t for t in panel["tasks"] if t["family_id"] in roles]
    for task in tasks:
        if task["project_id"]:
            require(project_roles.setdefault(task["project_id"], roles[task["family_id"]])
                    == roles[task["family_id"]], "Project crosses roles; provide a reviewed grouped panel")
    return {**deepcopy(panel), "tasks": deepcopy(tasks)}, train, selection


def transition(parent, result, limit=6000):
    """An unsuccessful attempt may advance the queue, not the completion claim."""
    from skillopt.continual_learning.contracts import check_skill

    require(result["status"] in {"completed", "pending"}, "Unknown learning terminal state")
    check_skill(parent, limit)
    candidate = check_skill(result["candidate_skill"], limit)
    if result["status"] == "pending":
        require(candidate == parent, "Pending learner must retain its authorized parent")
        return {"skill": parent, "action": "pending_carry_parent", "learning_completed": False}
    return {"skill": candidate, "action": "selected_update" if candidate != parent else "completed_no_update",
            "learning_completed": True}


def policy_key(baseline, skill, version=None):
    value = {"baseline_plan": baseline["plan_hash"], "skill": skill,
             "reuse": "same_frozen_solver_runtime_budget_panel_existing_samples"}
    if version in {DELIVERY_SEQUENCE, BUDGET_SEQUENCE}:
        # V3 also binds the target domain and frozen report: two domains frozen
        # from one identical plan can never share a reused evaluation cell.
        value.update(baseline_benchmark=baseline["benchmark"], baseline_report=baseline["report_hash"])
    return digest(value)


def verify_service(root, expected=None):
    service = read_json(safe_path(root) / "model_service.json", sealed=True)
    if expected is not None:
        require(service == expected, "Actual model services differ")
    public = {k: v for k, v in service.items() if k != "record_hash"}
    for path in (safe_path(root) / "api/calls").glob("*.json"):
        receipt = read_json(path)
        require(receipt["request_hash"] == digest(receipt["request"])
                and receipt["request"]["service"] == public
                and receipt["request"]["model"] == "glm-5.3", "API cache/service mismatch")
        if receipt.get("ok") or receipt.get("returned_model") is not None:
            require(receipt.get("returned_model") == "glm-5.3", "Returned model mismatch")
    return service


def check_client_service(repo, model, cache, expected, *, client_options=None):
    from skillopt.validator_pilot.api import CachedAPI

    api = CachedAPI(Path(repo), Path(cache), provider=model["provider"], model=model["name"],
                    workers=1, reasoning_effort=model["reasoning_effort"], **model["transport"],
                    **(client_options or {}),
                    **({"proxy": model["proxy"]} if "proxy" in model else {}))
    try:
        require(seal(api.service) == expected, "Current client differs from frozen model service")
    finally:
        api.close()


def _require_cleanup(value):
    if isinstance(value, dict):
        for key, item in value.items():
            require(not (key in {"cleanup_confirmed", "cleaned_up"} and item is False),
                    "Native cleanup unconfirmed; stop the queue for review")
            require(not (key in {"reason", "status", "error_type"} and isinstance(item, str)
                         and "cleanup_unconfirmed" in item),
                    "Native cleanup unconfirmed; stop the queue for review")
            _require_cleanup(item)
    elif isinstance(value, list):
        for item in value:
            _require_cleanup(item)


def require_safe_handoff(learning_root, result):
    """A terminal learning label alone is not a native-resource handoff."""
    require(result["costs"]["unclosed_calls"] == 0, "Open model intents require operator review")
    root = safe_path(learning_root)
    intents = {p.name for p in (root / "evaluation_intents").glob("*.json")}
    closed = {p.name for p in (root / "evaluations").glob("*.json")}
    require(intents == closed, "Open evaluation intents require operator review")

    for path in (root / "evaluations").glob("*.json"):
        _require_cleanup(read_json(path, sealed=True))
    # Recalculation receipts can fail before the high-level score has evidence.
    for path in (root / "host_only/scorer_artifacts").rglob("*.json"):
        _require_cleanup(read_json(path))
    # Learning v10: probe executions the verifier began need a receipt with confirmed cleanup too.
    for intent in (root / "verifier").glob("*/executions/*.intent.json"):
        receipt = intent.with_name(intent.name[: -len(".intent.json")] + ".json")
        require(receipt.exists(), "Open probe execution intents require operator review")
        _require_cleanup(read_json(receipt, sealed=True)["execution"])


def require_eval_handoff(root):
    root = safe_path(root)
    for pattern in ("predictions/*/prediction.json", "host_only/scores/*.json", "host_only/scorer_artifacts/**/*.json"):
        for path in root.glob(pattern):
            _require_cleanup(read_json(path))


def _invoke(reference, operation, request, output, *, log):
    # PYTHONPATH and cwd must both point at the old source; do not import current
    # scorers while claiming to replay historical evaluation semantics. V4 only
    # evaluates new policies in its verified budget-derived copy of that source.
    source = reference["source"]
    if operation in {"evaluate", "verify-evaluation"} and "evaluation_source" in reference:
        source = reference["evaluation_source"]
    env = dict(os.environ, PYTHONPATH=str(safe_path(source)))
    command = [reference["python"], str(Path(__file__).absolute()), "worker", "--operation", operation,
               "--request", str(request), "--output", str(output)]
    with safe_path(log).open("ab") as handle:
        code = subprocess.run(command, cwd=source, env=env, stdout=handle, stderr=handle).returncode
    require(code == 0 and Path(output).is_file(), "Frozen evaluation worker failed; inspect private log, do not retry")
    return read_json(output, sealed=True)


def _reference_identity(ref):
    return {k: ref[k] for k in ("root", "source", "python", "evaluation_source") if k in ref}


def _skill_limit(protocol):
    if protocol["version"] == BUDGET_SEQUENCE:
        return protocol["config"]["learning_recovery_policy"]["skill_budget_bytes"]
    return 6000


def _check_budget_source(source, derived, budget):
    """The derived evaluation source equals the frozen one except the Skill-budget literal."""
    source, derived = safe_path(source), safe_path(derived)

    def tree(root):
        return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                and not {"__pycache__", ".pytest_cache"} & set(p.relative_to(root).parts)}

    require(source != derived and tree(source) == tree(derived), "Derived evaluation source file set differs")
    changed = {}
    for name in sorted(tree(source)):
        original, copy = (source / name).read_bytes(), (derived / name).read_bytes()
        if name in BUDGET_SOURCE_EDITS:
            literal = BUDGET_SOURCE_EDITS[name]
            text = original.decode()
            require(text.count(literal) == 1, "Frozen Skill-budget literal not found exactly once")
            require(copy.decode() == text.replace(literal, literal.replace("6000", str(budget))),
                    "Derived evaluation source changes more than the Skill budget")
            changed[name] = {"original": hashlib.sha256(original).hexdigest(),
                             "derived": hashlib.sha256(copy).hexdigest()}
        else:
            require(original == copy, "Derived evaluation source differs outside the Skill budget")
    require(set(changed) == set(BUDGET_SOURCE_EDITS), "Derived evaluation source lacks the budget edit")
    return changed


def _source_files():
    from skillopt.continual_learning.contracts import sources
    from skillopt.continual_learning.skillopt import native_sources

    root = Path(__file__).resolve().parents[1]
    files = {str(root / "skillopt" / name): value for name, value in {**sources(), **native_sources()}.items()}
    files[str(Path(__file__).absolute())] = sha(__file__)
    files[str(root / "scripts/run_continual_learning.py")] = sha(root / "scripts/run_continual_learning.py")
    return files


def prepare(config_path, output):
    config, root = read_json(config_path), safe_path(output)
    recovery = config.get("version") in RECOVERY_SEQUENCES
    fields = {"version", "references", "families", "budget", "seed", "native_lock", "workers",
              "learning_sheet_qualification"}
    if recovery:
        fields |= {"learning_recovery_policy", "learning_sheet_scorer"}
    if config.get("version") == BUDGET_SEQUENCE:
        fields |= {"evaluation_qualifications"}
    require(set(config) == fields and config["version"] in {VERSION, *RECOVERY_SEQUENCES},
            "Invalid sequential configuration")
    if recovery:
        require(config["learning_sheet_scorer"] == "qualified_lo_recalc_v7_v1"
                and type(config["learning_sheet_qualification"]) is str,
                "V2 requires a newly qualified v7 learning scorer")
    require(set(config["references"]) == set(BENCHMARKS)
            and set(config["families"]) == set(BENCHMARKS), "All five domains required")
    require(type(config["workers"]) is int and 1 <= config["workers"] <= 10, "Invalid evaluation concurrency")
    require(type(config["seed"]) is int and 0 <= config["seed"] < 2**32 - 5, "Invalid five-stage seed")
    require(not root.exists(), "A new output directory is required")
    root.mkdir(parents=True, mode=0o700)
    refs, roles, files, models = {}, {}, {}, []
    for benchmark in BENCHMARKS:
        reference = config["references"][benchmark]
        require(set(reference) == {"root", "source", "python"} | (
            {"evaluation_source"} if config["version"] == BUDGET_SEQUENCE else set()), "Invalid frozen reference")
        request = root / f"requests/baseline-{benchmark}.json"
        write_json(request, seal({"reference": reference, "benchmark": benchmark}))
        result = _invoke(reference, "inspect", request, root / f"baselines/{benchmark}.json",
                         log=root / f"baseline-{benchmark}.log")
        refs[benchmark] = {**reference, **result}
        plan = read_json(Path(reference["root"]) / "plan.json", sealed=True)
        require(plan["order"] == list(BENCHMARKS), "Domain order mismatch")
        models.append(plan["config"]["model"])
        panel_path = plan["config"]["panels"][benchmark]
        panel = read_json(panel_path)
        counts = config["families"][benchmark]
        require(set(counts) == {"train", "selection"}, "Explicit train/selection family counts required")
        learning, train, selection = split_panel(panel, counts["train"], counts["selection"], config["seed"])
        path = root / f"panels/{benchmark}.json"
        write_json(path, learning)
        files[str(path)] = sha(path)
        files[str(safe_path(panel_path))] = sha(panel_path)
        roles[benchmark] = {"path": str(path), "train": train, "selection": selection,
                            "train_tasks": sum(t["family_id"] in train for t in learning["tasks"]),
                            "selection_tasks": sum(t["family_id"] in selection for t in learning["tasks"]),
                            "evaluation_overlap_tasks": len(learning["tasks"]),
                            "runtime": plan["config"]["runtime"].get(benchmark, {})}
    # The scorer algorithm/image stays fixed, but its authorization includes
    # absolute source paths. Requalify this new learning tree; never transfer an
    # old source's authority or silently replace the evaluation reference.
    if config["learning_sheet_qualification"] is not None:
        qpath = safe_path(config["learning_sheet_qualification"])
        q = read_json(qpath, sealed=True)
        runtime = roles["spreadsheetbench"]["runtime"]
        if recovery:
            runtime["spreadsheet_scorer"] = config["learning_sheet_scorer"]
        runtime["recalculation"] = {**runtime["recalculation"], "qualification_path": str(qpath),
                                    "qualification_sha256": sha(qpath), "qualification_hash": q["record_hash"]}
        files[str(qpath)] = sha(qpath)
        if recovery:
            from skillopt.continual_eval.sheet_numeric_adapter import readiness

            require(readiness(runtime)["status"] == "ready", "New learning workbook scorer is not qualified/ready")
    require(all(m == models[0] for m in models), "Historical solver models/budgets differ")
    require(all(r["model_service"] == refs[BENCHMARKS[0]]["model_service"] for r in refs.values()),
            "Actual historical services differ")
    from skillopt.continual_learning.contracts import (
        BUDGET_VERSION,
        DELIVERY_VERSION,
        MULTI_BENCHMARK_VERSION,
        RECOVERY_VERSION,
        manifest,
    )
    from skillopt.continual_learning.recovery import RETRY_POLICIES, validate_policy

    learning_version = {DELIVERY_SEQUENCE: DELIVERY_VERSION,
                        BUDGET_SEQUENCE: BUDGET_VERSION}.get(config["version"], RECOVERY_VERSION)
    methods = ["skillopt", "gepa"] if config["version"] in {VERSION, BUDGET_SEQUENCE} else ["skillopt"]
    if config["version"] == BUDGET_SEQUENCE:
        budget = config["learning_recovery_policy"]["skill_budget_bytes"]
        derived = {}
        for reference in config["references"].values():
            derived.setdefault((reference["source"], reference["evaluation_source"]), None)
        for (source, evaluation_source) in sorted(derived):
            for name, value in _check_budget_source(source, evaluation_source, budget).items():
                files[str(safe_path(evaluation_source) / name)] = value["derived"]

    learning_model = deepcopy(models[0])
    extra = {}
    extension = {}
    if recovery:
        from skillopt.validator_pilot.api import long_stream_service

        learning_model["transport"]["stream_wall_seconds"] = 3600
        validate_policy(config["learning_recovery_policy"], learning_model, learning_version)
        extra = {"recovery_policy": config["learning_recovery_policy"]}
        base_service = {k: v for k, v in refs[BENCHMARKS[0]]["model_service"].items() if k != "record_hash"}
        service = long_stream_service(base_service, read_timeout_seconds=300, stream_wall_seconds=3600)
        service["delivery_retry_policy"] = RETRY_POLICIES[learning_version]
        extension = {"learning_version": learning_version, "learning_model_service": seal(service),
                     "learning_client_options": {"delivery_retry_policy": RETRY_POLICIES[learning_version]},
                     "evaluation_policy": "unchanged_original_frozen_budget_source_scorer_all_methods"}
        if config["version"] == BUDGET_SEQUENCE:
            # A source-path-bound scorer qualification must be redone in the derived
            # source (same image/controls). Only those three binding fields change.
            overrides = {}
            for target, qpath in sorted(config["evaluation_qualifications"].items()):
                derived_root = str(safe_path(config["references"][target]["evaluation_source"])) + "/"
                q = read_json(qpath, sealed=True)
                reference_plan = read_json(safe_path(config["references"][target]["root"]) / "plan.json", sealed=True)
                original = reference_plan["config"]["runtime"][target]["recalculation"]
                require(q["status"] == "qualified" and q["model_api_calls"] == 0
                        and q["engine"]["image_id"] == original["image"]
                        and q["engine"]["timeout_seconds"] == original["timeout_seconds"]
                        and q["engine"]["sources"] and all(path.startswith(derived_root) for path in q["engine"]["sources"]),
                        "Evaluation qualification must bind the derived source with the original engine")
                overrides[target] = {"recalculation": {"qualification_path": str(safe_path(qpath)),
                                                       "qualification_sha256": sha(qpath),
                                                       "qualification_hash": q["record_hash"]}}
                files[str(safe_path(qpath))] = sha(qpath)
            extension.update(evaluation_policy="original_frozen_semantics_budget_derived_source_requalified_scorer",
                             evaluation_runtime_overrides=overrides)
        launcher = Path(__file__).with_name(LAUNCHERS[config["version"]])
        files[str(launcher.absolute())] = sha(launcher)
    # Validate every domain/role/runtime before any paid work is authorized.
    for stage, benchmark in enumerate(BENCHMARKS, 1):
        role = roles[benchmark]
        for method in methods if recovery else ["skillopt"]:
            manifest(read_json(role["path"]), train_families=role["train"], selection_families=role["selection"],
                     model=learning_model, budget=config["budget"], runtime=role["runtime"],
                     seed=config["seed"] + stage, version=learning_version if recovery else MULTI_BENCHMARK_VERSION,
                     method=method, **extra)
    protocol = seal({"version": config["version"], "root": str(root), "config": config, "references": refs,
                     **extension, "roles": roles, "model": learning_model, "files": files, "source_files": _source_files(),
                     "learning_host_runtime": runtime_identity(),
                     "order": list(BENCHMARKS), "methods": methods,
                     "pending_policy": "carry_parent_continue_attempts_never_claim_completed_learning",
                     "reuse_policy": "link_identical_policy_existing_samples_no_new_independent_observations",
                     "data_scope": "previously_exposed_development_with_explicit_learning_overlap_not_final",
                     "evaluation_feedback_to_learner": False, "deployment_authorized": False})
    write_json(root / "protocol.json", protocol)
    return protocol


def check(root):
    root = safe_path(root)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] in {VERSION, *RECOVERY_SEQUENCES} and protocol["root"] == str(root),
            "Protocol binding mismatch")
    check_frozen_files(protocol)
    for benchmark, reference in protocol["references"].items():
        _invoke(reference, "inspect", root / f"requests/baseline-{benchmark}.json",
                root / f"baselines/{benchmark}.json", log=root / f"baseline-{benchmark}.log")
    return protocol


def check_frozen_files(protocol):
    """Recheck after queue waits and between stages, before any paid work."""
    require(protocol["source_files"] == _source_files(), "Current learning sources changed")
    require(protocol["learning_host_runtime"] == runtime_identity(), "Frozen learning runtime changed")
    for path, expected in (protocol["files"] | protocol["source_files"]).items():
        require(sha(path) == expected, "Frozen input changed")


def worker(operation, request_path, output):
    """Runs only inside the requested historical evaluation environment."""
    from skillopt.continual_eval.core import freeze_plan, load_checkpoint, load_plan, register_checkpoint
    from skillopt.continual_eval.runner import generate, report, score_checkpoint

    request = read_json(request_path, sealed=True)
    reference, benchmark = request["reference"], request["benchmark"]
    root = safe_path(reference["root"])
    # A V4 budget-derived source cannot rebuild the frozen No-Skill plan; inspect
    # already verified that plan and report under the frozen source itself.
    derived = operation in {"evaluate", "verify-evaluation"} and "evaluation_source" in reference
    require(Path(__import__("skillopt.continual_eval.core", fromlist=["__file__"]).__file__).resolve().parents[2]
            == safe_path(reference["evaluation_source" if derived else "source"]),
            "Worker imported the wrong evaluation source")
    plan = read_json(root / "plan.json", sealed=True) if derived else load_plan(root)
    require(plan["config"]["methods"] == ["no_skill"] and plan["config"]["partition"] == "development",
            "Expected frozen development No-Skill reference")
    expected = len([t for t in plan["tasks"] if t["benchmark"] == benchmark]) * plan["repeats"]
    if not derived:
        baseline = report(root)
        require(expected > 0 and all(baseline["run_accounting"][k] == expected for k in
                ("reserved_positions", "terminal_predictions", "scored_positions"))
                and baseline["run_accounting"]["unclosed_calls"] == 0, "Baseline incomplete")
        require(load_checkpoint(root, "no_skill", "h0", 0, plan)["skill_text"] == "", "Baseline not empty")
    service = verify_service(root)
    if operation in {"evaluate", "verify-evaluation"}:
        require(plan["record_hash"] == request["baseline_plan_hash"]
                and (derived or baseline["record_hash"] == request["baseline_report_hash"]),
                "Historical baseline changed")
        new = safe_path(request["run"])
        config = deepcopy(plan["config"])
        config["methods"] = ["no_skill", request["method"]]
        if "evaluation_runtime" in request:
            require(derived and set(request["evaluation_runtime"]) == {"recalculation"}
                    and set(request["evaluation_runtime"]["recalculation"])
                    == {"qualification_path", "qualification_sha256", "qualification_hash"},
                    "Only a derived source may rebind its re-qualified scorer")
            runtime = config["runtime"][benchmark]
            runtime["recalculation"] = {**runtime["recalculation"], **request["evaluation_runtime"]["recalculation"]}
        chain = request["chain"]
        require(1 <= len(chain) <= 5, "Invalid attempt stage")
        if operation == "evaluate":
            require(not new.exists(), "Never silently retry a begun evaluation")
            freeze_plan(config, new)
            check_client_service(request["repo"], config["model"], new / "api", service)
            for stage, skill in enumerate(chain, 1):
                register_checkpoint(new, request["method"], "h0", stage, skill,
                                    provenance="sequential_attempts_not_all_successful_learning:" + request["stage_hash"])
            generate(new, method=request["method"], history="h0", stage=len(chain), benchmark=benchmark,
                     repo=request["repo"], workers=request["workers"])
            require_eval_handoff(new)
            score_checkpoint(new, method=request["method"], history="h0", stage=len(chain), benchmark=benchmark)
        require(load_plan(new)["config"] == config, "Evaluation configuration changed")
        for stage, skill in enumerate(chain, 1):
            cp = load_checkpoint(new, request["method"], "h0", stage, load_plan(new))
            require(cp["skill_text"] == skill and cp["provenance"] ==
                    "sequential_attempts_not_all_successful_learning:" + request["stage_hash"],
                    "Selected policy/checkpoint chain changed")
        verify_service(new, service)
        require_eval_handoff(new)
        root, plan, baseline = new, load_plan(new), report(new)
    rows = [read_json(p, sealed=True) for p in sorted((root / "host_only/scores").glob("*.json"))]
    require(len(rows) == expected and baseline["run_accounting"]["unclosed_calls"] == 0,
            "Incomplete evaluation cannot authorize the next stage")
    counts = dict(Counter(r["status"] for r in rows))
    result = seal({"root": str(root), "plan_hash": plan["record_hash"], "report_hash": baseline["record_hash"],
                   "benchmark": benchmark, "positions": expected, "counts": counts,
                   "model_service": service,
                   "costs": baseline["run_accounting"], "rows": [
                       {k: r[k] for k in ("task_id", "family_id", "repeat", "status", "record_hash")} for r in rows],
                   "score_semantics": "original_frozen_primary_not_unknown_repair_shadow"})
    write_json(output, result)
    return result


def run(root, method, *, repo, gepa_source):
    import fcntl

    from skillopt.continual_eval.core import output_lock
    from skillopt.continual_learning.contracts import MULTI_BENCHMARK_VERSION, manifest
    from skillopt.continual_learning.launch import learning_environment

    protocol, root = check(root), safe_path(root)
    learning_service = protocol.get("learning_model_service", protocol["references"][BENCHMARKS[0]]["model_service"])
    require(method in protocol["methods"], "Unsupported method")
    run_root = root / method
    with output_lock(run_root), safe_path(protocol["config"]["native_lock"]).open("a") as resource, ExitStack() as launch:
        # Both learning and original evaluation can launch native containers.
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        check_frozen_files(protocol)
        # Validate/bind this serial process before any earlier domain can incur
        # paid calls. The immutable root is shared with the ALF evaluation
        # reference; restored after this method, including exception paths.
        launch.enter_context(learning_environment({"benchmark": "alfworld", "model": protocol["model"],
                                                   "runtime": protocol["roles"]["alfworld"]["runtime"]}))
        check_client_service(repo, protocol["model"], run_root / "client-check",
                             learning_service, client_options=protocol.get("learning_client_options"))
        previous, chain, results = "", [], []
        parent_stage_hash = None
        cache = {policy_key(ref, "", protocol["version"]): {"result": ref, "kind": "historical_empty_policy", "source_stage": 0}
                 for ref in protocol["references"].values()}

        def verify_cell(cell, expected_skill, expected_target):
            require(cell["result"]["benchmark"] == expected_target, "Evaluation cell domain mismatch")
            if cell["kind"] == "historical_empty_policy":
                require(expected_skill == "" and cell["result"] == protocol["references"][expected_target],
                        "Historical policy reference changed")
            else:
                ref = protocol["references"][expected_target]
                req = read_json(cell["request_path"], sealed=True)
                require(req["benchmark"] == expected_target and req["chain"][-1] == expected_skill
                        and req["baseline_plan_hash"] == ref["plan_hash"]
                        and req["baseline_report_hash"] == ref["report_hash"]
                        and req["reference"] == _reference_identity(ref),
                        "Reused evaluation does not belong to this policy/domain")
                verified = _invoke(ref, "verify-evaluation", cell["request_path"], cell["output_path"],
                                   log=run_root / "verify-evaluations.log")
                require(verified == cell["result"], "Reused evaluation changed")

        # Shared immutable registry: references, not duplicated observations.
        for path in sorted((root / "evaluated_policies").glob("*.json")):
            entry = read_json(path, sealed=True)
            ref = protocol["references"][entry["cell"]["result"]["benchmark"]]
            require(entry["protocol_hash"] == protocol["record_hash"]
                    and path.stem == policy_key(ref, entry["skill"], protocol["version"]),
                    "Policy registry binding mismatch")
            verify_cell(entry["cell"], entry["skill"], ref["benchmark"])
            cache[path.stem] = entry["cell"]
        for stage, benchmark in enumerate(protocol["order"], 1):
            check_frozen_files(protocol)
            directory = run_root / f"s{stage}-{benchmark}"
            completed = directory / "stage.json"
            if completed.exists():
                # Only a completed orchestration record (including all five
                # evaluation cells) is replayable; an intent alone is not.
                record = read_json(completed, sealed=True)
                require(record["protocol_hash"] == protocol["record_hash"]
                        and record["parent_skill"] == previous and record["method"] == method
                        and record["parent_stage_hash"] == parent_stage_hash
                        and record["stage"] == stage and record["benchmark"] == benchmark,
                        "Stage chain binding mismatch")
                decision = read_json(directory / "decision.json", sealed=True)
                require(decision["record_hash"] == record["decision_hash"]
                        and all(record[k] == v for k, v in decision.items() if k != "record_hash"),
                        "Stage decision changed")
                value = read_json(directory / "manifest.json", sealed=True)
                require(value["record_hash"] == record["manifest_hash"] and value["parent_skill"] == previous,
                        "Stage manifest changed")
                panel = read_json(protocol["roles"][benchmark]["path"])
                require((directory / "learning/result.json").is_file(), "Completed learning evidence missing")
                if method == "gepa":
                    from skillopt.continual_learning.gepa import run_stage
                    replay = run_stage(value, panel, directory / "learning", repo=repo, gepa_source=gepa_source)
                else:
                    from skillopt.continual_learning.skillopt import run_stage
                    replay = run_stage(value, panel, directory / "learning", repo=repo)
                require(replay["record_hash"] == record["learning_result_hash"]
                        and transition(previous, replay, _skill_limit(protocol))["skill"] == record["skill"],
                        "Learning result changed")
                require_safe_handoff(directory / "learning", replay)
                verify_service(directory / "learning", learning_service)
                require(set(record["cells"]) == set(BENCHMARKS), "Incomplete stage evaluation matrix")
                for target, cell in record["cells"].items():
                    verify_cell(cell, record["skill"], target)
            else:
                require(not directory.exists(), "Interrupted stage requires explicit review, not automatic paid resume")
                directory.mkdir(parents=True, mode=0o700)
                role = protocol["roles"][benchmark]
                panel = read_json(role["path"])
                value = manifest(panel, train_families=role["train"], selection_families=role["selection"],
                    model=protocol["model"], budget=protocol["config"]["budget"], runtime=role["runtime"],
                    parent_skill=previous, seed=protocol["config"]["seed"] + stage,
                    method=method, version=protocol.get("learning_version", MULTI_BENCHMARK_VERSION),
                    **({"recovery_policy": protocol["config"]["learning_recovery_policy"]}
                       if protocol["version"] in RECOVERY_SEQUENCES else {}))
                write_json(directory / "manifest.json", value)
                if method == "gepa":
                    from skillopt.continual_learning.gepa import run_stage
                    result = run_stage(value, panel, directory / "learning", repo=repo, gepa_source=gepa_source)
                else:
                    from skillopt.continual_learning.skillopt import run_stage
                    result = run_stage(value, panel, directory / "learning", repo=repo)
                verify_service(directory / "learning", learning_service)
                require_safe_handoff(directory / "learning", result)
                state = transition(previous, result, _skill_limit(protocol))
                decision = seal({"protocol_hash": protocol["record_hash"], "method": method, "stage": stage,
                                 "benchmark": benchmark, "parent_skill": previous, "manifest_hash": value["record_hash"],
                                 "parent_stage_hash": parent_stage_hash, "parent_skill_hash": digest(previous),
                                 "learning_result_hash": result["record_hash"], "learning_reason": result["reason"],
                                 "learning_costs": result["costs"], **state})
                write_json(directory / "decision.json", decision)
                cells = {}
                for target in protocol["order"]:
                    ref = protocol["references"][target]
                    key = policy_key(ref, state["skill"], protocol["version"])
                    if key in cache:
                        require(cache[key]["result"]["benchmark"] == target,
                                "Reused evaluation belongs to another domain")
                        cells[target] = {**cache[key], "reused": True, "new_model_calls": 0,
                                         "independent_new_observation": False}
                    else:
                        req_path = directory / f"requests/{target}.json"
                        write_json(req_path, seal({"reference": _reference_identity(ref),
                            "benchmark": target, "baseline_plan_hash": ref["plan_hash"],
                            "baseline_report_hash": ref["report_hash"], "run": str(directory / f"evaluations/{target}"),
                            "method": method, "chain": chain + [state["skill"]], "stage_hash": decision["record_hash"],
                            "repo": str(safe_path(repo)), "workers": protocol["config"]["workers"],
                            **({"evaluation_runtime": protocol["evaluation_runtime_overrides"][target]}
                               if target in protocol.get("evaluation_runtime_overrides", {}) else {})}))
                        evaluated = _invoke(ref, "evaluate", req_path, directory / f"evaluation-{target}.json",
                                            log=directory / f"evaluation-{target}.log")
                        cells[target] = {"result": evaluated, "kind": "new_frozen_policy_evaluation", "source_stage": stage,
                                         "request_path": str(req_path), "output_path": str(directory / f"evaluation-{target}.json"),
                                         "reused": False, "independent_new_observation": True,
                                         "new_model_calls": evaluated["costs"]["logical_calls"]}
                        write_json(root / "evaluated_policies" / f"{key}.json",
                                   seal({"protocol_hash": protocol["record_hash"], "skill": state["skill"],
                                         "cell": cells[target]}))
                record = seal({**{k: v for k, v in decision.items() if k != "record_hash"},
                               "decision_hash": decision["record_hash"], "cells": cells,
                               "learning_scores_used_from_evaluation": False,
                               "deployment_authorized": False})
                write_json(completed, record)
            for target, cell in record["cells"].items():
                cache[policy_key(protocol["references"][target], record["skill"], protocol["version"])] = cell
            previous = record["skill"]
            parent_stage_hash = record["record_hash"]
            chain.append(previous)
            results.append(record)
        summary = seal({"version": protocol["version"], "protocol_hash": protocol["record_hash"], "method": method,
                        "attempted_stages": len(results), "completed_learning_stages": sum(r["learning_completed"] for r in results),
                        "status": "completed" if all(r["learning_completed"] for r in results) else "attempts_finished_with_pending",
                        "stage_hashes": [r["record_hash"] for r in results], "final_skill": previous,
                        "independent_final": False, "deployment_authorized": False})
        write_json(run_root / "final.json", summary)
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "run", "worker"))
    parser.add_argument("--config")
    parser.add_argument("--output", required=True)
    parser.add_argument("--method", choices=("skillopt", "gepa"))
    parser.add_argument("--repo")
    parser.add_argument("--gepa-source")
    parser.add_argument("--operation", choices=("inspect", "evaluate", "verify-evaluation"))
    parser.add_argument("--request")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.config, args.output)
    elif args.command == "check":
        result = check(args.output)
    elif args.command == "worker":
        result = worker(args.operation, args.request, args.output)
    else:
        result = run(args.output, args.method, repo=args.repo, gepa_source=args.gepa_source)
    print({k: result[k] for k in ("version", "status", "record_hash", "attempted_stages", "completed_learning_stages") if k in result})


if __name__ == "__main__":
    main()
