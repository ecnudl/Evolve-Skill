"""Real-model, frozen-panel conditional Skill study (Coding only).

Contract-only and public-evidence updates are exploratory candidates. New
model-hypothesis feedback is used only after its full policy passes held-out
calibration. This study never grants cross-domain or deployment authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import queue
import threading
from collections import Counter, defaultdict
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import CachedAPI, digest, write_immutable_json

from .checks import ExecutionCache, pipeline_hash, validate_callable
from .conditional_feedback import deterministic_select, messages
from .models import ArtifactRecord, SourceFile, require
from .natural_policy import ARMS, probe_messages, propose_policy
from .panel import checked_path
from .research import fixed_rubric
from .single_round import IMAGE, BoundedCalls, _healthy, parse_code
from .single_round_feedback import build_feedback_bundle, parse_update
from .task_probes import execute_probes, parse_probes

VERSION = "natural-conditional-skill-study-v1"
UPDATE_ARMS = ("contract_only", "fixed", "adaptive_no_research", "adaptive_research")


def _write(path, value):
    write_immutable_json(checked_path(path), value)


def _read(path):
    return verify(json.loads(checked_path(path).read_text()))


class ExecutorPool:
    """Several serial, fail-closed SSH workers; no local code execution."""
    def __init__(self, remote_repo, workers=4):
        from .remote_executor import SSHExecutor
        require(1 <= workers <= 6, "Bounded execution concurrency")
        self.workers = [SSHExecutor(IMAGE, remote_repo=remote_repo) for _ in range(workers)]
        self.available = queue.Queue()
        for worker in self.workers:
            self.available.put(worker)
        self.identity = self.workers[0].identity
        self.transport_identity = {**self.workers[0].transport_identity, "parallel_ssh_workers": workers}
        self.failed = threading.Event()

    def run(self, *args, **kwargs):
        require(not self.failed.is_set(), "Execution pool stopped after infrastructure failure")
        worker = self.available.get()
        try:
            result = worker.run(*args, **kwargs)
            _healthy(result)
            return result
        except Exception:
            self.failed.set()
            raise
        finally:
            self.available.put(worker)

    def close(self):
        for worker in self.workers:
            worker.close()


def solve(row, skill, condition, repeat, calls, root):
    task = row["task"]
    system = (
        "Solve the public Python programming task. Return ONLY a valid JSON object mapping exactly "
        "'solution.py' to the complete Python source string, including needed standard-library imports. "
        "Escape newlines/quotes within the JSON string. Implement the requested function signature. "
        "No Markdown fences or file-section wrappers. Task and output contract override optional fallible Skill advice. "
        "No shell, network, files, benchmark detection, test tampering or evaluator access. "
        "No hidden feedback or repair round is available. Do not add unstated task requirements."
    )
    user = json.dumps({"task": task.contract.prompt, "optional_skill": skill}, ensure_ascii=False, sort_keys=True)
    receipt = calls.call(system, user, "natural-solver", repeat=repeat, max_tokens=2048)
    availability, files = "api_failure", ()
    if receipt.get("ok"):
        try:
            files = (SourceFile("solution.py", parse_code(receipt["response"])),
                     SourceFile.from_dict(row["public_wrapper"]))
            availability = "available"
        except (ValueError, TypeError, KeyError):
            availability = "parse_failure"
    shash = hashlib.sha256(skill.encode()).hexdigest()
    artifact = ArtifactRecord(task.contract.content_hash, repeat, condition,
        "none" if condition == "no_skill" else "skill-" + shash[:16], shash, files, availability,
        "fixture" if calls.api.service.get("fixture") else "model", True, False,
        "pjlab-request:" + receipt["request_hash"], digest(receipt))
    _write(root / "artifacts" / (artifact.content_hash + ".json"), artifact.sealed())
    return artifact


def audit(row, artifact, executor, root, *, reference=False):
    from .natural_data import build_audit_files
    task = row["task"]
    code = None if reference else next((f.content for f in artifact.files if f.path == "solution.py"), None)
    files = build_audit_files(row, code, reference=reference) if reference or code is not None else {}
    request = {"task_hash": task.content_hash, "artifact_hash": None if reference else artifact.content_hash,
               "files_hash": digest(files), "executor": executor.identity, "reference": reference}
    key = digest(request)
    terminal, intent = root / "host_only/audits" / (key + ".json"), root / "host_only/audit_intents" / (key + ".json")
    if terminal.exists():
        result = _read(terminal)
        require(result["request"] == request, "Audit request changed")
        if result["execution"] is not None:
            _healthy(result["execution"])
        return result
    require(not intent.exists(), "Interrupted audit cannot be resampled")
    _write(intent, seal({"request": request}))
    execution, values, status, native = None, None, "unknown", "unknown"
    if files:
        execution = executor.run(files, "hidden_audit", "audit", [], {})
        verify(execution)
        invocation = {"module": "hidden_audit", "function": "audit", "args": [], "kwargs": {}}
        require(execution["input_hash"] == digest({"files": files, **invocation}), "Wrong audit execution binding")
        _healthy(execution)
        values = execution.get("actual")
        if execution.get("status") == "observed" and execution.get("exception") is None and type(values) is dict:
            require(set(values) >= {"base_pass", "plus_pass", "base_count", "plus_count"}, "Malformed audit output")
            require(all(values[k] is None or type(values[k]) is bool for k in ("base_pass", "plus_pass")),
                    "Audit booleans or explicit unknown required")
            native = "unknown" if values["base_pass"] is None else "pass" if values["base_pass"] else "fail"
            status = ("fail" if any(values[k] is False for k in ("base_pass", "plus_pass")) else
                      "unknown" if any(values[k] is None for k in ("base_pass", "plus_pass")) else "pass")
            require(values.get("status", status) == status, "Audit aggregation disagrees with observed partitions")
        elif execution.get("status") == "observed" and execution.get("exception") not in {None, "MemoryError", "TimeoutError"}:
            status = native = "fail"
    result = seal({"request": request, "status": status, "native_status": native,
                   "execution": execution, "information_origin": "host_only_executed_audit"})
    _write(terminal, result)
    return result


def probe_prediction(fixed_status, report):
    require(fixed_status in {"pass", "fail", "unknown"}, "Public status required")
    verify(report)
    if fixed_status == "fail" or report["status"] == "mismatch":
        return "fail"
    if fixed_status == "unknown" or report["status"] == "unknown":
        return "unknown"
    return "pass"


def project_probe_feedback(task, artifacts, reports, authority, policy_hash, proposal_record):
    """Qualified, fallible probe evidence; never project any audit labels."""
    verify(authority)
    require(authority["status"] == "accepted" and authority["policy_hash"] == policy_hash
            and authority["qualified_development_feedback_authorized"] is True,
            "Uncalibrated hypotheses cannot update a Skill")
    require(authority.get("purpose") == "finite_verifier_policy_calibration"
            and authority.get("scope", {}).get("adapter_domain") == "coding"
            and authority.get("scope", {}).get("obligation_kinds") == ["requested_behavior"]
            and authority.get("scope", {}).get("allowed_partition") == "development",
            "Calibration scope does not authorize this kind of feedback")
    require(task.contract.partition == "development", "Only development feedback")
    require(len(artifacts) == len(reports) == 2 and {a.condition for a in artifacts} == {"no_skill", "current"}
            and len({a.repeat for a in artifacts}) == 1, "Complete paired feedback required")
    verify(proposal_record)
    verify(proposal_record["proposal"])
    require(proposal_record["policy_hash"] == policy_hash, "Probe generator is not the authorized policy")
    roles = {}
    for artifact, report in zip(artifacts, reports):
        verify(report)
        require(report["request"]["artifact_record_hash"] == artifact.content_hash
                and report["request"]["task_hash"] == task.contract.content_hash
                and report["request"]["proposal_hash"] == proposal_record["proposal"]["record_hash"],
                "Probe/feedback artifact mismatch")
        checks = []
        for row in report["probes"]:
            probe = row["probe"]
            checks.append({"hypothesis": {k: probe[k] for k in
                ("kind", "calls", "expected", "obligation_id", "contract_quote", "rationale")},
                "information_origin": "model_hypothesis_not_ground_truth", "comparison": row["status"],
                "execution": [{"status": o["status"], "observation": o["public_observation"],
                               "information_origin": "recorded_public_execution"} for o in row["observations"]]})
        roles[artifact.condition] = checks
    return {"public_task": task.contract.prompt, "roles": roles,
            "qualification": "Finite independently calibrated generator, not certified task answers; ambiguity remains."}


def amend_panel(repo, root, prior_root):
    """Explicit adapter repair on the SAME panel, never a new independent split."""
    from . import natural_data
    repo, root, prior_root = checked_path(repo), checked_path(root), checked_path(prior_root)
    require(root != prior_root and root.is_relative_to(repo / "outputs/skill_validation"), "New pilot output required")
    previous = _read(prior_root / "data_manifest.json")
    protocol = _read(prior_root / "protocol.json")
    parent = _read(prior_root / "parent_skill.json")
    require(protocol["manifest_hash"] == previous["record_hash"]
            and protocol["parent_hash"] == parent["record_hash"], "Prior experiment identity mismatch")
    manifest = {k: v for k, v in previous.items() if k != "record_hash"}
    manifest["settings"] = {**manifest["settings"], "implementation_hash":
                            hashlib.sha256(Path(natural_data.__file__).read_bytes()).hexdigest()}
    manifest.update(run_path=str(root.relative_to(repo)),
        amendment={"previous_manifest_hash": previous["record_hash"], "previous_protocol_hash": protocol["record_hash"],
                   "reason": "Public example extractor must distinguish function examples from mathematical definitions.",
                   "same_panel_not_new_independent_sample": True,
                   "development_model_artifacts_preexist": True,
                   "selection_based_on_model_outcomes": False})
    frozen = seal(manifest)
    for name in ("source_snapshot.json", "exposure_inventory.json", "eligibility_manifest.json", "parent_skill.json"):
        _write(root / name, _read(prior_root / name))
    _write(root / "data_manifest.json", frozen)
    return frozen


def run(repo, root, executor, *, workers=6, repeats=2, update_repeats=2, stop_after=None, reuse_from=None,
        public_preflight=None):
    from .natural_data import load_tasks
    from .natural_metrics import calibrate_policy, summarize
    repo, root = checked_path(repo), checked_path(root)
    manifest, parent_record = _read(root / "data_manifest.json"), _read(root / "parent_skill.json")
    parent = parent_record["text"]
    incompatible, compatibility = {}, None
    if public_preflight is not None:
        compatibility = _read(public_preflight)
        require(compatibility["manifest_hash"] == manifest["record_hash"]
                and compatibility["model_calls"] == 0 and compatibility["hidden_audit_executed"] is False,
                "Public compatibility must precede model evaluation and match this panel")
        declared = {(r["task_id"], part) for part, rows in manifest["splits"].items() for r in rows}
        observed = {(r["task_id"], r["partition"]) for r in compatibility["rows"]}
        require(declared == observed and len(observed) == len(compatibility["rows"]), "Complete unique public preflight required")
        for item in compatibility["rows"]:
            if item["status"] != "pass":
                require(item["partition"] in {"skill_confirmation", "final"},
                        "An incompatible development/calibration task blocks feedback experiments")
                incompatible[item["task_id"]] = item["record_hash"]
        _write(root / "public_compatibility.json", compatibility)
    require(1 <= repeats <= 3 and 1 <= update_repeats <= 3, "Bounded repeat budget")
    reference_locks, artifact_locks, lock_guard = {}, {}, threading.Lock()
    with CachedAPI(repo, root / "api", workers=workers, stream=True, reasoning_effort="low") as api:
        source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in Path(__file__).parent.glob("*.py")}
        inherited = None
        if reuse_from is not None:
            reuse_from = checked_path(reuse_from)
            prior_manifest, prior_protocol = _read(reuse_from / "data_manifest.json"), _read(reuse_from / "protocol.json")
            require(manifest.get("amendment", {}).get("previous_manifest_hash") == prior_manifest["record_hash"]
                    and manifest["amendment"]["previous_protocol_hash"] == prior_protocol["record_hash"]
                    and manifest["splits"] == prior_manifest["splits"]
                    and manifest["source_snapshot"] == prior_manifest["source_snapshot"]
                    and parent_record == _read(reuse_from / "parent_skill.json"), "Receipt reuse requires an explicit same-panel amendment")
            inherited = {"root": str(reuse_from), "manifest_hash": prior_manifest["record_hash"],
                         "protocol_hash": prior_protocol["record_hash"], "same_prompt_terminal_solver_receipts_only": True}
        protocol = seal({"version": VERSION, "manifest_hash": manifest["record_hash"],
            "parent_hash": parent_record["record_hash"], "source_hashes": source_hashes,
            "service": api.service, "executor": executor.identity, "transport": executor.transport_identity,
            "workers": workers, "repeats": repeats, "update_repeats": update_repeats,
            "max_logical_requests": 2400, "max_output_tokens": 2048, "feedback_tasks": 8,
            "qualified_probe_feedback_tasks": 4,
            "feedback_selection": "first repeat, ascending task hash, no outcome filtering",
            "max_probes_per_task_arm": 2, "probe_policy_calibration_scope": "coding_requested_behavior_feedback_only",
            "calibration_thresholds": {"min_independent_families": 8, "min_natural_errors": 4,
                "min_natural_correct": 12, "min_coverage": .9, "max_false_rejection_increase": 0., "min_net_new_detection": 1},
            "arms": list(UPDATE_ARMS), "equal_adaptive_budget_caps_not_equal_realized_cost": True,
            "research_model_excerpt_chars": 6000, "inherited_solver_receipts": inherited,
            "public_compatibility_hash": compatibility["record_hash"] if compatibility else None,
            "unsupported_public_tasks": incompatible, "unsupported_tasks_remain_unknown_in_common_denominator": True,
            "single_parent_multiple_update_samples_not_independent_learning_histories": True,
            "deployment_authorized": False, "cross_domain_evidence": False,
            "final_never_updates_skills_rubrics_or_thresholds": True})
        _write(root / "protocol.json", protocol)
        preflight = executor.run({"probe.py": "def ping():\n    return True\n"}, "probe", "ping", [], {})
        require(preflight.get("actual") is True and preflight["status"] == "observed", "Sandbox unavailable")
        calls = BoundedCalls(api, root / "model_budget", protocol["record_hash"], protocol["max_logical_requests"])
        if reuse_from is not None:
            from .reused_calls import ReusedSolverCalls
            calls = ReusedSolverCalls(calls, reuse_from)
        cache_records, cache_identity = {}, None

        def reference_for(row):
            key = row["task"].content_hash
            with lock_guard:
                lock = reference_locks.setdefault(key, threading.Lock())
            with lock:
                result = audit(row, None, executor, root, reference=True)
            return result

        def position(job):
            row, arm, repeat, skill = job
            condition = "no_skill" if arm == "no_skill" else "current" if arm == "current" else "candidate"
            contract = row["task"].contract
            if contract.original_task_id in incompatible:
                return {"record": {"task_id": contract.original_task_id, "family_id": contract.family_id,
                    "partition": contract.partition, "repeat": repeat, "arm": arm, "condition": condition,
                    "status": "unknown", "native_status": "unknown", "public_status": "unknown",
                    "availability": "not_run_public_contract_or_adapter_incompatible",
                    "compatibility_receipt": incompatible[contract.original_task_id], "artifact_hash": None,
                    "audit_hash": None, "reference_hash": None, "request_ref": None}}
            artifact = solve(row, skill, condition, repeat, calls, root)
            with lock_guard:
                artifact_lock = artifact_locks.setdefault(artifact.content_hash, threading.Lock())
            with artifact_lock:
                reference = reference_for(row)
                audited = audit(row, artifact, executor, root)
                cache = ExecutionCache(executor, root / "public_execution" / artifact.content_hash, max_executions=192)
                report = validate_callable(row["public_task"], artifact, fixed_rubric(), cache)
                for receipt in cache.records.values():
                    _healthy(receipt["execution"])
                _write(root / "public_reports" / (report["record_hash"] + ".json"), report)
            record = {"task_id": row["task"].contract.original_task_id, "family_id": row["task"].contract.family_id,
                "partition": row["task"].contract.partition, "repeat": repeat, "arm": arm, "condition": condition,
                "status": audited["status"] if reference["status"] == "pass" else "unknown",
                "native_status": audited["native_status"] if reference["status"] == "pass" else "unknown",
                "public_status": report["status"], "availability": artifact.availability,
                "artifact_hash": artifact.content_hash, "audit_hash": audited["record_hash"],
                "reference_hash": reference["record_hash"], "request_ref": artifact.source_ref}
            with lock_guard:
                cache_records.update(cache.records)
                cache_records.update(cache.missing_records)
            return {"row": row, "artifact": artifact, "report": report, "record": record,
                    "cache_identity": cache.identity}

        def phase(partition, skills, count_repeats=repeats):
            rows = load_tasks(repo, manifest, partition)
            jobs = [(row, arm, repeat, skills[arm]) for repeat in range(count_repeats) for row in rows
                    for arm in sorted(skills, key=lambda a: digest([row["task"].content_hash, repeat, a]))]
            positions = []
            print(json.dumps({"phase": partition, "tasks": len(rows), "positions": len(jobs)}), flush=True)
            # Batches bound spending if execution or API infrastructure stops.
            for start in range(0, len(jobs), 12):
                positions.extend(api.parallel(jobs[start:start + 12], position, "natural-" + partition))
                print(json.dumps({"phase": partition, "completed": len(positions), "total": len(jobs)}), flush=True)
            _write(root / "host_only" / (partition + "_rows.json"), seal({"rows": [p["record"] for p in positions]}))
            return positions

        development = phase("development", {"no_skill": "", "current": parent})
        dev_metrics = summarize([p["record"] for p in development], partition="development", protocolseed=20260920)
        _write(root / "host_only/development_diagnostic.json", dev_metrics)
        if stop_after == "development":
            result = seal({"phase": "development_complete", "metrics": dev_metrics, "cost": calls.accounting()})
            _write(root / "development_summary.json", result)
            return result
        by_task = defaultdict(dict)
        for p in development:
            if p["artifact"].repeat == 0:
                by_task[p["artifact"].task_hash][p["artifact"].condition] = p
        entries = [{"task": group["no_skill"]["row"]["public_task"],
                    "artifacts": tuple(group[c]["artifact"] for c in ("no_skill", "current")),
                    "reports": tuple(group[c]["report"] for c in ("no_skill", "current"))}
                   for group in by_task.values()]
        selected = deterministic_select(entries, limit=8)
        cache_identity = development[0]["cache_identity"]
        replay_cache = ExecutionCache(executor, max_executions=192)
        bundle = build_feedback_bundle(selected, parent_skill=parent, rubric=fixed_rubric(),
            pipeline_hash=pipeline_hash(fixed_rubric(), replay_cache), execution_identity=cache_identity,
            execution_records=tuple(cache_records.values()))
        _write(root / "public_feedback.json", bundle)
        # Host audit summaries are explicitly attributed; no private input/answer is projected.
        visible = json.loads(messages(parent, bundle, "evidence")[1])["feedback"]
        gap_summary = []
        selected_hashes = {e["task"].contract.content_hash for e in selected}
        for p in development:
            if p["artifact"].task_hash in selected_hashes and p["artifact"].repeat == 0:
                gap_summary.append({"public_status": p["report"]["status"], "audited_status": p["record"]["status"],
                                    "information_origin": "development_audit_summary"})
        policy_view = {"public_feedback": visible, "unlinked_development_gap_counts":
                      dict(Counter(p["public_status"] + "/" + p["audited_status"] for p in gap_summary)),
                      "gap_origin": "development_audit_summary_not_research_discovery"}
        policies = {arm: propose_policy(arm, policy_view, calls, root / "policies") for arm in ARMS}
        policy_ids = {arm: digest({"policy": p["record_hash"], "protocol": protocol["record_hash"],
                                  "generator": "natural_policy.probe_messages", "executor": executor.identity})
                      for arm, p in policies.items()}
        _write(root / "frozen_policies.json", seal({"policies": policies, "pipeline_hashes": policy_ids}))
        print(json.dumps({"phase": "policies_frozen", "status": {a: p["status"] for a, p in policies.items()}}), flush=True)
        calibration = phase("verifier_calibration", {"no_skill": "", "current": parent})

        def probe_phase(positions, arm, *, only_hashes=None):
            grouped = defaultdict(list)
            for p in positions:
                if only_hashes is None or p["artifact"].task_hash in only_hashes:
                    grouped[p["artifact"].task_hash].append(p)

            def one(group):
                task = group[0]["row"]["task"]
                path = root / "probes" / arm / (task.contract.content_hash + ".json")
                if path.exists():
                    proposal_record = _read(path)
                    require(proposal_record["policy_hash"] == policy_ids[arm], "Probe used changed generation policy")
                    proposal = proposal_record["proposal"]
                else:
                    system, user = probe_messages(task, tuple(p["artifact"] for p in group), policies[arm])
                    receipt = calls.call(system, user, "natural-probes-" + arm, max_tokens=2048)
                    try:
                        require(receipt.get("ok"), "Probe API failure")
                        proposal = parse_probes(receipt["response"], task)
                        status = proposal["status"]
                    except (ValueError, TypeError, KeyError):
                        proposal, status = parse_probes({"probes": []}, task), "invalid"
                    proposal_record = seal({"policy_hash": policy_ids[arm], "proposal": proposal,
                                            "status": status, "request_hash": receipt["request_hash"]})
                    _write(path, proposal_record)
                results = []
                for p in group:
                    report = execute_probes(task, p["artifact"], proposal, executor, root / "probe_execution" / arm)
                    require(not getattr(executor, "failed", threading.Event()).is_set(),
                            "Probe infrastructure failed; stop before further paid calls")
                    if not proposal["probes"]:
                        prediction = p["report"]["status"]
                    else:
                        prediction = probe_prediction(p["report"]["status"], report)
                    results.append((p, report, prediction, proposal_record["status"]))
                return results

            output = []
            groups = [grouped[k] for k in sorted(grouped)]
            for start in range(0, len(groups), 6):
                for rows in api.parallel(groups[start:start + 6], one, "natural-probe-evidence-" + arm):
                    output.extend(rows)
                print(json.dumps({"phase": "probe_evidence", "arm": arm, "tasks": min(start + 6, len(groups)),
                                  "total_tasks": len(groups)}), flush=True)
            return output

        authorities, calibration_evidence = {}, {}
        for arm in ARMS[1:]:
            if policies[arm]["status"] != "update":
                authorities[arm] = seal({"status": "pending", "reason": "no_valid_policy",
                    "policy_hash": policy_ids[arm], "qualified_development_feedback_authorized": False,
                    "deployment_authorized": False})
                continue
            evidence = probe_phase(calibration, arm)
            calibration_evidence[arm] = evidence
            records = [{"task_id": p["record"]["task_id"], "family_id": p["record"]["family_id"],
                "repeat": p["artifact"].repeat, "condition": p["artifact"].condition,
                "audit_status": p["record"]["status"], "fixed_status": p["report"]["status"],
                "new_status": prediction, "artifact_hash": p["artifact"].content_hash,
                "report_hash": report["record_hash"], "audit_hash": p["record"]["audit_hash"],
                "partition": "verifier_calibration"} for p, report, prediction, _ in evidence]
            authorities[arm] = calibrate_policy(records, policy_hash=policy_ids[arm],
                protocol_hash=protocol["record_hash"], manifest_hash=manifest["record_hash"],
                config=protocol["calibration_thresholds"])
            _write(root / "host_only" / (arm + "_calibration_records.json"), seal({"records": records}))
        _write(root / "verifier_authorities.json", seal({"authorities": authorities}))
        print(json.dumps({"phase": "verifier_gate", "status": {a: v["status"] for a, v in authorities.items()}}), flush=True)
        extra_feedback = {}
        for arm in ARMS[1:]:
            if authorities[arm]["status"] != "accepted":
                continue  # Never feed uncalibrated hypothesis mismatches to updater.
            subset = [p for p in development if p["artifact"].repeat == 0]
            evidence = probe_phase(subset, arm, only_hashes=set(sorted(selected_hashes)[:4]))
            groups = defaultdict(list)
            for p, report, _, _ in evidence:
                groups[p["artifact"].task_hash].append((p, report))
            extra_feedback[arm] = [project_probe_feedback(rows[0][0]["row"]["task"],
                tuple(p["artifact"] for p, _ in rows), tuple(r for _, r in rows), authorities[arm], policy_ids[arm],
                _read(root / "probes" / arm / (task_hash + ".json")))
                for task_hash, rows in sorted(groups.items())]
        candidates, skills = {}, {"no_skill": "", "current": parent}
        for sample in range(update_repeats):
            for arm in UPDATE_ARMS:
                mode = "contract_only" if arm == "contract_only" else "evidence"
                system, user, _ = messages(parent, bundle, mode)
                if arm in extra_feedback:
                    payload = json.loads(user)
                    payload["qualified_probe_feedback"] = extra_feedback[arm]
                    system += (" Additional probe feedback comes from a finitely calibrated generator. Its expected "
                               "values and relations remain hypotheses, not hidden or public ground truth. Only "
                               "actual calls are observations. Treat unsupported interpretations as uncertainty; "
                               "revise a rule only if the public contract and evidence support the change.")
                    user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                prompt_hash = digest({"system": system, "user": user})
                receipt = calls.call(system, user, "natural-skill-update", repeat=sample, max_tokens=2048)
                update = parse_update(receipt.get("response") if receipt.get("ok") else None, parent)
                skill = update["candidate_skill"] if update["status"] == "candidate" else parent
                name = arm + "_u" + str(sample)
                skills[name] = skill
                candidates[name] = {"update": update, "skill": skill, "prompt_hash": prompt_hash,
                    "request_ref": receipt["request_hash"], "extra_probe_feedback_used": arm in extra_feedback,
                    "fallback_feedback": arm in ARMS[1:] and arm not in extra_feedback,
                    "deployment_authorized": False}
        freeze = seal({"protocol_hash": protocol["record_hash"], "candidates": candidates,
                       "skills": skills, "all_frozen_before_confirmation_and_final": True})
        _write(root / "frozen_candidates.json", freeze)
        confirmation = phase("skill_confirmation", skills)
        confirm_summary = summarize([p["record"] for p in confirmation], partition="skill_confirmation", protocolseed=20260920)
        _write(root / "host_only/confirmation_summary.json", confirm_summary)
        # No selection, threshold tuning, or feedback from confirmation changes
        # a candidate. Skill scope/deployment are intentionally NOT authorized
        # by this raw-content pilot; independent final evaluates every candidate.
        _write(root / "skill_decision.json", seal({"action": "Pending", "deployment_authorized": False,
            "reason": "Raw-content pilot lacks retention/Near-Miss deployment panel and scope authorization.",
            "frozen_candidate_hash": freeze["record_hash"], "confirmation_hash": confirm_summary["record_hash"]}))
        final = phase("final", skills)
        final_summary = summarize([p["record"] for p in final], protocolseed=20260920)
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
            "manifest_hash": manifest["record_hash"], "candidate_freeze_hash": freeze["record_hash"],
            "development": dev_metrics, "confirmation": confirm_summary, "final": final_summary,
            "policy_status": {a: p["status"] for a, p in policies.items()},
            "verifier_gate": {a: v["status"] for a, v in authorities.items()},
            "unique_update_requests": len({v["request_ref"] for v in candidates.values()}),
            "unique_candidate_texts": len({v["skill"] for v in candidates.values()}),
            "cost": calls.accounting(), "deployment_authorized": False, "cross_domain_evidence": False,
            "effect_claim": "descriptive_real_model_Coding_single_parent_content_pilot_not_generalization_proof"})
        _write(root / "results.json", result)
        print(json.dumps({"phase": "completed", "cost": result["cost"],
                          "verifier_gate": result["verifier_gate"]}), flush=True)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "amend", "run"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", default="/root/Evolve-Skill-validation")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--execution-workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--update-repeats", type=int, default=2)
    parser.add_argument("--stop-after", choices=("development",))
    parser.add_argument("--reuse-from", type=Path)
    parser.add_argument("--public-preflight", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        from .natural_data import prepare
        from .single_round_data import freeze_parent
        manifest = prepare(args.repo, args.output)
        parent = freeze_parent(args.repo, args.output)
        print(json.dumps({"manifest_hash": manifest["record_hash"], "parent_hash": parent["record_hash"]}))
    elif args.command == "amend":
        require(args.reuse_from is not None, "Amend requires explicit prior output")
        print(json.dumps({"manifest_hash": amend_panel(args.repo, args.output, args.reuse_from)["record_hash"]}))
    else:
        executor = ExecutorPool(args.remote_repo, args.execution_workers)
        try:
            run(args.repo, args.output, executor, workers=args.workers, repeats=args.repeats,
                update_repeats=args.update_repeats, stop_after=args.stop_after, reuse_from=args.reuse_from,
                public_preflight=args.public_preflight)
        finally:
            executor.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "stopped", "error_type": type(error).__name__,
                          "recovery": "Inspect saved receipts; do not overwrite or resample."}), flush=True)
        raise SystemExit(2)
