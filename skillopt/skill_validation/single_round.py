"""One exploratory shared-parent Skill update on newly reserved public tasks.

All candidate Skills are evaluated raw, including unapproved/invalid-update
fallbacks. This driver does not deploy a Skill, expand scope, or certify transfer.
Model credentials remain local; generated code runs only in the Linux sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
from collections import Counter, defaultdict
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import CachedAPI, digest, write_immutable_json

from .calibration import CalibrationRow, FreezeDeclaration, GateConfig, calibrate, register_freeze
from .checks import ExecutionCache, pipeline_hash, validate_callable
from .models import ArtifactRecord, EvidenceRecord, Observation, require
from .panel import checked_path
from .partitions import PartitionManifest
from .replay import partition_entry
from .research import BoundedResearch, ModelReply, ResearchBudget, fixed_rubric
from .stage2 import _proposal
from .views import DevelopmentGap, research_development_view

VERSION = "shared-parent-single-round-shadow-v1"
ARMS = ("fixed", "adaptive_no_research", "adaptive_research")
IMAGE = "sha256:b8fe4ce3655e95f7f22c2a87d8e03a2f1f0cedc488a8e9adf18cc5a18cfdf401"


def _healthy(execution):
    if execution is not None:
        require(execution.get("status") != "unsupported"
                and not str(execution.get("reason", "")).startswith("ssh_")
                and execution.get("cleanup_confirmed", True) is not False,
                "Execution infrastructure unavailable; retained receipts, stop paid phases")


def _write(path, value):
    write_immutable_json(checked_path(path), value)


def _read(path):
    path = checked_path(path)
    require(path.stat().st_size <= 32_000_000, "Oversized pilot record")
    return verify(json.loads(path.read_text(encoding="utf-8")))


class BoundedCalls:
    """Paid requests are content addressed; interrupted calls are not retried.

    Equal prompts/repeats share one real response, including updater prompts.
    Different repeat numbers remain independent requests, not independent tasks.
    """
    def __init__(self, api, root, protocol_hash, limit):
        self.api, self.root, self.protocol_hash, self.limit = api, checked_path(root), protocol_hash, limit
        self.lock = threading.Lock()
        self.request_locks = {}

    def call(self, system, user, kind, *, repeat=0, max_tokens=2048):
        require(len((system + user).encode()) <= 120000, "Pilot prompt byte budget exceeded")
        require(1 <= max_tokens <= 2048, "Pilot output budget exceeded")
        key = digest({"protocol": self.protocol_hash, "system": system, "user": user,
                      "kind": kind, "repeat": repeat, "max_tokens": max_tokens})
        request = {"model": self.api.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.api.service}
        request_hash = digest(request)
        intent = self.root / "intents" / (request_hash + ".json")
        receipt_path = self.api.root / "calls" / (request_hash + ".json")
        with self.lock:
            request_lock = self.request_locks.setdefault(request_hash, threading.Lock())
        with request_lock:
            with self.lock:
                if receipt_path.exists():
                    require(intent.exists() and _read(intent)["request_hash"] == request_hash,
                            "API cache without pilot reservation")
                elif intent.exists():
                    raise ValueError("Interrupted API request retained; explicit recovery required")
                else:
                    require(len(list((self.root / "intents").glob("*.json"))) < self.limit,
                            "Frozen logical request budget exhausted")
                    _write(intent, seal({"request_hash": request_hash, "protocol_hash": self.protocol_hash,
                                         "kind": kind, "repeat": repeat}))
            record = self.api.call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            require(record.get("request") == request and record.get("request_hash") == request_hash,
                    "Provider request binding changed")
            require(receipt_path.is_file() and json.loads(receipt_path.read_text()) == record,
                    "Missing durable model receipt")
            return record

    def research_model(self, system, user, cap):
        record = self.call(system, user, "single-round-verifier-proposal", max_tokens=cap)
        require(record.get("ok") is True, "Proposal API failure")
        usage = record.get("usage") or {}
        return ModelReply(record["response"], usage.get("prompt_tokens"), usage.get("completion_tokens"))

    def accounting(self):
        records = [json.loads(p.read_text()) for p in sorted((self.api.root / "calls").glob("*.json"))]
        usage_complete = all(type(r.get("usage", {}).get(k)) is int for r in records
                             for k in ("prompt_tokens", "completion_tokens"))
        return {"reserved_logical_requests": len(list((self.root / "intents").glob("*.json"))),
                "terminal_logical_requests": len(records),
                "http_attempts": sum(r.get("http_attempt_count", 0) for r in records),
                "terminal_failures": sum(r.get("ok") is not True for r in records),
                "terminal_reported_tokens": sum(sum(r["usage"][k] for k in ("prompt_tokens", "completion_tokens"))
                                                for r in records) if usage_complete else None,
                "retry_inclusive_token_usage_known": usage_complete and all(r.get("http_attempt_count") == 1 for r in records),
                "request_limit": self.limit, "temperature": 0, "generation_seed_sent": False}


def solver_messages(row, skill):
    task = row["task"].contract
    system = ("Solve the given Python programming task. Return ONLY a JSON object mapping 'solution.py' "
              "to its complete Python source string. Implement the requested function names. Standard library only. "
              "No shell, network, files, benchmark detection, test tampering or reading evaluator internals. "
              "The supplied public example is visible to all conditions. Do not add requirements absent from the "
              "task. The optional Skill is fallible advice; the task and output contract take precedence. "
              "Do not output the public test wrapper. No repair round or hidden feedback is available.")
    user = json.dumps({"task": task.prompt, "public_files": [f.to_dict() for f in task.public_files],
                       "optional_skill": skill}, sort_keys=True, ensure_ascii=False)
    return system, user


def parse_code(response):
    require(type(response) is str and len(response.encode()) <= 60000, "Missing/oversized code response")
    value = response.strip()
    if value.startswith("```json\n") and value.endswith("\n```"):
        value = value[8:-4]
    def pairs(items):
        output = {}
        for key, item in items:
            require(key not in output, "Duplicate source file")
            output[key] = item
        return output
    payload = json.loads(value, object_pairs_hook=pairs)
    require(type(payload) is dict and set(payload) == {"solution.py"}, "Exactly solution.py is required")
    code = payload["solution.py"]
    require(type(code) is str and bool(code.strip()) and len(code.encode()) <= 50000, "Invalid code text")
    return code


def solve(row, skill, condition, repeat, calls, root):
    from .single_round_data import build_artifact_files
    system, user = solver_messages(row, skill)
    receipt = calls.call(system, user, "single-round-solver", repeat=repeat)
    availability, files = "api_failure", ()
    if receipt.get("ok") is True:
        try:
            files = build_artifact_files(row, parse_code(receipt["response"]))
            availability = "available"
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            availability = "parse_failure"
    skill_hash = hashlib.sha256(skill.encode()).hexdigest()
    provenance = "fixture" if calls.api.service.get("fixture") is True else "model"
    artifact = ArtifactRecord(row["task"].contract.content_hash, repeat, condition,
        "none" if condition == "no_skill" else "frozen-" + skill_hash[:16], skill_hash,
        files, availability, provenance, True, False, "pjlab-request:" + receipt["request_hash"], digest(receipt))
    _write(root / "artifacts" / (artifact.content_hash + ".json"), artifact.sealed())
    return artifact


def audit_artifact(row, artifact, executor, root, *, reference=False):
    """Original native assertions in an isolated host-only wrapper, never V."""
    from .single_round_data import build_artifact_files
    files = (build_artifact_files(row, row["host_audit"]["reference_code"] if reference else
                                 next(f.content for f in artifact.files if f.path == "solution.py"), audit=True)
             if reference or artifact.availability == "available" else ())
    request = {"task": row["task"].content_hash, "artifact": None if reference else artifact.content_hash,
               "files_hash": digest([f.to_dict() for f in files]), "executor": executor.identity,
               "reference": reference}
    key = digest(request)
    path, intent = root / "host_only" / "audits" / (key + ".json"), root / "host_only" / "audit_intents" / (key + ".json")
    if path.exists():
        record = _read(path)
        require(record["request"] == request, "Audit replay binding changed")
        _healthy(record["execution"])
        return record
    require(not intent.exists(), "Interrupted private audit retained; no automatic rerun")
    _write(intent, seal({"request": request}))
    if not reference and artifact.availability != "available":
        execution, status = None, "unknown"
    else:
        execution = executor.run({f.path: f.content for f in files}, "hidden_audit", "audit", [], {})
        verify(execution)
        require(execution["input_hash"] == digest({"files": {f.path: f.content for f in files},
                "module": "hidden_audit", "function": "audit", "args": [], "kwargs": {}}), "Audit execution mismatch")
        values = execution.get("actual")
        if execution["status"] != "observed":
            status = "unknown"
        elif execution.get("exception") is not None:
            status = "unknown" if execution["exception"] in {"MemoryError", "TimeoutError"} else "fail"
        elif (type(values) is not list or len(values) != row["host_audit"]["original_assertion_count"]
              or not all(type(v) is dict and type(v.get("passed")) is bool for v in values)):
            status = "unknown"
        else:
            status = "pass" if all(v["passed"] for v in values) else "fail"
    record = seal({"request": request, "status": status, "execution": execution})
    _write(path, record)
    _healthy(execution)
    return record


def _research_views(entries, audits):
    views = []
    for entry in entries:
        task = entry["task"].contract
        for artifact, report in zip(entry["artifacts"], entry["reports"]):
            observations = tuple(Observation("public-" + o.id, o.id, "public_test",
                                            passed=report["obligations"][o.id] == "pass")
                                 for o in task.obligations if report["obligations"][o.id] in {"pass", "fail"})
            evidence = EvidenceRecord(task.content_hash, artifact.artifact_hash, artifact.content_hash,
                artifact.repeat, "public", "observed" if observations else "unsupported", observations,
                "bound-public-report:" + report["record_hash"], report["record_hash"], artifact.provenance_kind)
            h = audits[artifact.content_hash]["status"]
            category = ("uncertainty" if report["status"] == "unknown" or h == "unknown" else
                        "missed_error" if report["status"] == "pass" and h == "fail" else
                        "false_rejection" if report["status"] == "fail" and h == "pass" else None)
            gaps = tuple(DevelopmentGap(task.content_hash, artifact.artifact_hash, o.id, category,
                                       audits[artifact.content_hash]["record_hash"])
                         for o in task.obligations) if category else ()
            view = research_development_view(task, artifact, (evidence,), gaps=gaps)
            view["anonymous_id"] = "item-" + digest(artifact.content_hash)[:24]
            views.append(view)
    return sorted(views, key=lambda v: v["anonymous_id"])


def _phase(rows, parent, calls, executor, root, api):
    jobs = [(row, skill, condition) for row in rows for skill, condition in (("", "no_skill"), (parent, "current"))]
    artifacts = api.parallel(jobs, lambda j: solve(j[0], j[1], j[2], 0, calls, root), "single-round-paired-solves")
    entries, audits = [], {}
    cache = ExecutionCache(executor, root / "public_execution", max_executions=192)
    for index, row in enumerate(rows):
        pair = tuple(artifacts[2 * index:2 * index + 2])
        reference = audit_artifact(row, None, executor, root, reference=True)
        reports = tuple(validate_callable(row["task"], a, fixed_rubric(), cache) for a in pair)
        for record in cache.records.values():
            _healthy(record["execution"])
        for artifact in pair:
            result = audit_artifact(row, artifact, executor, root)
            audits[artifact.content_hash] = seal({"status": result["status"] if reference["status"] == "pass" else "unknown",
                "artifact_audit_hash": result["record_hash"], "reference_audit_hash": reference["record_hash"],
                "reference_available": reference["status"] == "pass"})
        entries.append({"task": row["task"], "artifacts": pair, "reports": reports})
    return entries, audits, cache


def _calibration(entries, audits, dev_entries, rubrics, proposals, executor, root, protocol):
    config = GateConfig(4, 4, 4, 2, 0.75, 0.0, 0.0, 1)
    manifest = PartitionManifest([partition_entry(entry["task"].contract, a)
                                 for entry in (*dev_entries, *entries) for a in entry["artifacts"]])
    dev = PartitionManifest([e for e in manifest.entries if e.partition == "development"])
    cache = ExecutionCache(executor, root / "calibration_public", max_executions=192)
    pipelines = {arm: pipeline_hash(rubric, cache) for arm, rubric in rubrics.items()}
    changed = tuple(sorted({value for value in pipelines.values() if value != pipelines["fixed"]}))
    freezes = {}
    for arm in ARMS[1:]:
        if pipelines[arm] != pipelines["fixed"]:
            # Equivalent pipelines share an explicitly bound proposal set; they
            # cannot overwrite one another's single content-addressed freeze.
            proposal_set_hash = digest(sorted(p.content_hash for name, p in proposals.items()
                                              if pipelines[name] == pipelines[arm]))
            freeze = FreezeDeclaration(proposal_set_hash, pipelines[arm], pipelines["fixed"], changed,
                protocol["record_hash"], config.content_hash, dev.to_dict()["manifest_hash"],
                digest([a.content_hash for e in dev_entries for a in e["artifacts"]]),
                tuple(sorted({e.original_task_id for e in dev.entries})),
                tuple(sorted({e.near_duplicate_family for e in dev.entries})))
            register_freeze(freeze, development_manifest=dev, ledger_dir=root / "verifier_gate")
            freezes[arm] = freeze
    data = {arm: [] for arm in ARMS}
    for entry in entries:
        task = entry["task"].contract
        for artifact in entry["artifacts"]:
            for arm in ARMS:
                report = validate_callable(entry["task"], artifact, rubrics[arm], cache)
                for obligation in task.obligations:
                    data[arm].append(CalibrationRow(task.task_id, task.original_task_id, task.family_id,
                        task.project_id, task.partition, task.content_hash, artifact.content_hash, artifact.repeat,
                        artifact.condition, obligation.id, report["obligations"][obligation.id],
                        audits[artifact.content_hash]["status"], True, False, artifact.provenance_kind,
                        artifact.provenance_complete, artifact.historical_only,
                        pipelines[arm], report["record_hash"], audits[artifact.content_hash]["record_hash"]))
    results = {}
    for arm in ARMS[1:]:
        if arm in freezes:
            decision, comparison = calibrate(data["fixed"], data[arm], manifest=manifest, freeze=freezes[arm],
                                            config=config, ledger_dir=root / "verifier_gate")
            results[arm] = {"decision": decision.to_dict(), "comparison": comparison}
        else:
            results[arm] = {"decision": {"status": "pending", "reason": "no_new_verifier"}}
    record = seal({"results": results, "config": config.to_dict(), "scope": "coding_native_example_only",
                   "near_miss_data_available": False, "skill_admission_authority": False})
    _write(root / "host_only" / "calibration.json", record)
    return record


def summarize_final(records):
    grouped = defaultdict(list)
    by_task = defaultdict(dict)
    for row in records:
        grouped[row["arm"]].append(row)
        key = row["task_id"], row["repeat"]
        require(row["arm"] not in by_task[key], "Duplicate final position")
        by_task[key][row["arm"]] = row["status"]
    rates = {}
    for arm, rows in sorted(grouped.items()):
        counts = Counter(r["status"] for r in rows)
        rates[arm] = {"pass": counts["pass"], "fail": counts["fail"], "unknown": counts["unknown"],
                      "positions": len(rows), "independent_task_ids": len({r["task_id"] for r in rows}),
                      "all_attempt_success": counts["pass"] / len(rows),
                      "unique_model_requests": len({r["request_ref"] for r in rows})}
    pairs = {}
    for arm in ARMS:
        for anchor in ("no_skill", "parent"):
            counts = Counter()
            task_effects = defaultdict(list)
            for (task, _), values in by_task.items():
                before, after = values.get(anchor, "unknown"), values.get(arm, "unknown")
                category = ("unknown" if "unknown" in (before, after) else "tie" if before == after
                            else "win" if after == "pass" else "loss")
                counts[category] += 1
                task_effects[task].append(int(after == "pass") - int(before == "pass"))
            pairs[arm + "_vs_" + anchor] = {"positions": dict(sorted(counts.items())),
                "task_mean_all_attempt_delta": sum(sum(v) / len(v) for v in task_effects.values()) / len(task_effects)
                                               if task_effects else None,
                "distinct_task_count": len(task_effects), "per_task_repeat_deltas": dict(sorted(task_effects.items()))}
    return {"rates": rates, "paired": pairs, "unique_final_model_requests": len({r["request_ref"] for r in records})}


def run(repo, root, executor, *, workers=4):
    from .single_round_data import materialize_tasks
    from .single_round_feedback import build_feedback_bundle, candidate_from_response, messages
    repo, root = checked_path(repo), checked_path(root)
    manifest, parent_record = _read(root / "data_manifest.json"), _read(root / "parent_skill.json")
    parent = parent_record["text"]
    with CachedAPI(repo, root / "api", workers=workers, stream=True, reasoning_effort="low") as api:
        source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
        protocol = seal({"version": VERSION, "manifest_hash": manifest["record_hash"],
            "parent_hash": parent_record["record_hash"], "source_hashes": source_hashes,
            "executor": executor.identity, "transport": executor.transport_identity,
            "service": api.service, "workers": workers,
            "repeats_final": 2, "one_learning_history": True, "one_update_per_arm": True,
            "arms": list(ARMS), "max_logical_requests": 191, "max_output_tokens": 2048,
            "shadow_only": True, "skill_gate_or_scope_expansion": False,
            "unapproved_verifiers_may_generate_exploratory_candidates_only": True,
            "same_effective_feedback_uses_same_updater_request": True,
            "research_novel_check_capability": "not_identifiable_with_current_recipes_and_MBPP_contracts",
            "calibration_pending_by_design": True,
            "first_native_assertion_public_remaining_native_tests_host_only": True,
            "limitations": ["Coding-only, not cross-domain generalization or repository engineering.",
                            "One history and sixteen final task IDs do not establish statistical superiority.",
                            "No extra input-preservation or repeat-invariance task requirements.",
                            "Current recipes cannot introduce a new effective MBPP check; this is not a Research efficacy test."]})
        _write(root / "protocol.json", protocol)
        preflight = executor.run({"probe.py": "def ping():\n    return True\n"}, "probe", "ping", [], {})
        verify(preflight)
        _write(root / "runtime_probes" / (preflight["record_hash"] + ".json"), preflight)
        _healthy(preflight)
        require(preflight["status"] == "observed" and preflight.get("actual") is True,
                "Harmless sandbox preflight failed; no model requests sent")
        calls = BoundedCalls(api, root / "model_budget", protocol["record_hash"], 191)
        require(manifest["settings"]["counts"] == {"development": 8, "verifier_calibration": 4, "final": 16},
                "This pilot has frozen 8/4/16 task counts")
        development = materialize_tasks(repo, manifest, "development")
        require(len(development) == 8, "Missing reserved development tasks")
        print(json.dumps({"phase": "development", "tasks": len(development)}), flush=True)
        entries, dev_audits, cache = _phase(development, parent, calls, executor, root / "development", api)
        views = _research_views(entries, dev_audits)
        _write(root / "development_views.json", seal({"views": views}))
        research = BoundedResearch(model=calls.research_model, cache_root=root / "research_docs",
                                   budget=ResearchBudget(max_output_tokens=2048))
        proposals = {arm: _proposal(research, arm, views, root, protocol["record_hash"]) for arm in ARMS}
        rubrics = {arm: value.rubric or fixed_rubric() for arm, value in proposals.items()}
        # Freeze proposals first, before even generating calibration artifacts.
        print(json.dumps({"phase": "verifier_calibration", "proposal_status": {a: p.status for a, p in proposals.items()}}), flush=True)
        calibration_tasks = materialize_tasks(repo, manifest, "verifier_calibration")
        require(len(calibration_tasks) == 4, "Missing reserved calibration tasks")
        calibration_entries, calibration_audits, _ = _phase(calibration_tasks, parent, calls, executor,
                                                            root / "calibration", api)
        calibration = _calibration(calibration_entries, calibration_audits, entries, rubrics, proposals,
                                   executor, root, protocol)
        candidates, bundles = {}, {}
        for arm in ARMS:
            arm_entries = [{"task": entry["task"], "artifacts": entry["artifacts"],
                            "reports": tuple(validate_callable(entry["task"], a, rubrics[arm], cache)
                                             for a in entry["artifacts"])} for entry in entries]
            bundle = build_feedback_bundle(arm_entries, parent_skill=parent, rubric=rubrics[arm],
                pipeline_hash=pipeline_hash(rubrics[arm], cache), execution_identity=cache.identity,
                execution_records=tuple((*cache.records.values(), *cache.missing_records.values())))
            bundles[arm] = bundle
            _write(root / "feedback" / (arm + ".json"), bundle)
            system, user, _ = messages(parent, bundle)
            receipt = calls.call(system, user, "single-round-skill-update")
            candidate = candidate_from_response(receipt.get("response") if receipt.get("ok") else None, parent, bundle)
            proposed = candidate["update"]
            candidates[arm] = {"update": proposed, "binding": candidate,
                "evaluated_skill": proposed["candidate_skill"] if proposed["status"] == "candidate" else parent,
                "parent_fallback": proposed["status"] != "candidate",
                "request_ref": "pjlab-request:" + receipt["request_hash"]}
        candidate_freeze = seal({"candidates": candidates, "protocol_hash": protocol["record_hash"],
                                 "data_manifest_hash": manifest["record_hash"],
                                 "candidate_skill_hashes": {arm: hashlib.sha256(value["evaluated_skill"].encode()).hexdigest()
                                                            for arm, value in candidates.items()},
                                 "calibration_hash": calibration["record_hash"], "no_deployment": True})
        _write(root / "frozen_candidates.json", candidate_freeze)
        # No final task is materialized for solving until all candidate texts freeze.
        final_tasks = materialize_tasks(repo, manifest, "final", final_authorization=candidate_freeze)
        require(len(final_tasks) == 16, "Missing reserved final tasks")
        skills = {"no_skill": "", "parent": parent,
                  **{arm: value["evaluated_skill"] for arm, value in candidates.items()}}
        jobs = [(row, arm, repeat) for repeat in range(2) for row in final_tasks
                for arm in sorted(skills, key=lambda a: digest([row["task"].content_hash, repeat, a]))]
        print(json.dumps({"phase": "final", "tasks": len(final_tasks), "positions": len(jobs),
                          "distinct_skill_texts": len(set(skills.values()))}), flush=True)
        records = []
        # Small bounded batches let terminal execution failure stop subsequent
        # spending; unknown task-specific outcomes remain in the denominator.
        for start in range(0, len(jobs), 8):
            batch = jobs[start:start + 8]
            artifacts = api.parallel(batch, lambda j: solve(j[0], skills[j[1]], "no_skill" if j[1] == "no_skill" else
                "current" if j[1] == "parent" else "candidate", j[2], calls, root / "final"), "single-round-final-solves")
            for (row, arm, repeat), artifact in zip(batch, artifacts):
                reference = audit_artifact(row, None, executor, root / "final", reference=True)
                audited = audit_artifact(row, artifact, executor, root / "final")
                records.append({"task_id": row["task"].contract.original_task_id, "repeat": repeat, "arm": arm,
                    "artifact_hash": artifact.content_hash, "request_ref": artifact.source_ref,
                    "status": audited["status"] if reference["status"] == "pass" else "unknown",
                    "audit_hash": audited["record_hash"], "reference_audit_hash": reference["record_hash"],
                    "reference_available": reference["status"] == "pass"})
            print(json.dumps({"phase": "final_audit", "completed_positions": len(records), "total": len(jobs)}), flush=True)
        _write(root / "host_only/final_rows.json", seal({"rows": records, "candidate_freeze_hash": candidate_freeze["record_hash"]}))
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
            "candidate_freeze_hash": candidate_freeze["record_hash"], "final": summarize_final(records),
            "proposal_status": {arm: p.status for arm, p in proposals.items()},
            "calibration_status": {arm: r["decision"]["status"] for arm, r in calibration["results"].items()},
            "calibration_pending_by_design": True,
            "candidate_status": {arm: value["update"]["status"] for arm, value in candidates.items()},
            "unique_updater_requests": len({value["request_ref"] for value in candidates.values()}),
            "unique_feedback_prompts": len({messages(parent, bundle)[2] for bundle in bundles.values()}),
            "collapsed_intervention": len({messages(parent, bundle)[2] for bundle in bundles.values()}) == 1,
            "cost": calls.accounting(), "cross_domain_evidence": False, "deployment_authorized": False,
            "effect_claim": "descriptive_single_history_raw_skill_pilot_not_confirmatory",
            "limitations": protocol["limitations"]})
        _write(root / "results.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", default="/root/Evolve-Skill-validation")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        from .single_round_data import freeze_manifest, freeze_parent
        manifest = freeze_manifest(args.repo, args.output, dev_count=8, calib_count=4, final_count=16, seed=20260918)
        parent = freeze_parent(args.repo, args.output)
        print(json.dumps({"manifest_hash": manifest["record_hash"], "parent_hash": parent["record_hash"]}))
    else:
        from .remote_executor import SSHExecutor
        with SSHExecutor(IMAGE, remote_repo=args.remote_repo) as executor:
            run(args.repo, args.output, executor, workers=args.workers)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No provider error bodies, key-containing configuration or response dumps.
        print(json.dumps({"status": "stopped", "error_type": type(error).__name__,
                          "recovery": "inspect_saved_receipts_no_automatic_rerun_or_budget_expansion"}), flush=True)
        raise SystemExit(2)
