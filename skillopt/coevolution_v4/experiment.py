"""Frozen three-arm V4 engineering study; one owner per run directory.

All model calls use the existing bounded PJLAB transport. Development diagnostics
may train skills; calibration labels only select validators, and sealed final
labels never flow back. Reused project identities are explicitly not unseen data.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v3.executor import evaluate, execute_inputs, sandbox_probe
from skillopt.validator_pilot.api import digest, write_immutable_json
from skillopt.validator_pilot.tasks import _same

from . import gates, runtime, validator

VERSION = "coevolution-v4-engineering-v1"
POLICIES = ("fixed", "feedback", "research")
STREAMS = (0, 1)
ROUNDS = (0, 1, 2)
TRAIN_REPEATS = (0, 1)
FINAL_REPEATS = (0, 1, 2)
MAX_CALLS = 1600
CLAIM_TOKENS = 4500
SKILL_TOKENS = 3000
SEED = 20260909
PROTOCOL_DOC = "docs/coevolution-v4-protocol-20260909.md"
REUSED = (
    "skillopt/coevolution/budget.py", "skillopt/coevolution/executor.py",
    "skillopt/coevolution_v3/executor.py", "skillopt/coevolution_v3/state.py",
    "skillopt/coevolution_v3/validator.py", "skillopt/coevolution/validator.py",
    "skillopt/validator_pilot/api.py", "skillopt/validator_pilot/tasks.py",
    "skillopt/validator_pilot/research.py", "skillopt/validator_document_transport.py",
    "scripts/coevolution_v4.py", PROTOCOL_DOC,
)


def log(event, **values):
    print(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": event, **values},
                     ensure_ascii=False), flush=True)


def save(path, value):
    write_immutable_json(path, {"record": value, "record_hash": digest(value)})


def read(path):
    value = json.loads(path.read_text())
    if set(value) != {"record", "record_hash"} or value["record_hash"] != digest(value["record"]):
        raise ValueError(f"Immutable record integrity mismatch: {path.name}")
    return value["record"]


def require_cached_calls(api, value):
    """Cached outer stages cannot hide missing or corrupted transport receipts."""
    hashes = set()
    def visit(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if key in {"request_hash", "initial_request_hash"} and child is not None:
                    hashes.add(child)
                elif key == "request_hashes":
                    hashes.update(v for v in child if v is not None)
                else:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    for identifier in hashes:
        if not isinstance(identifier, str) or len(identifier) != 64:
            raise ValueError("Invalid cached API request identity")
        path = api.root / "calls" / f"{identifier}.json"
        if not path.exists():
            raise RuntimeError("Missing cached API receipt; preserve reservation without silent retry")
        call = json.loads(path.read_text())
        if (call.get("request_hash") != identifier or digest(call.get("request")) != identifier
                or call["request"].get("service") != api.service):
            raise ValueError("Cached API receipt provenance mismatch")


def cached(api, path):
    value = read(path)
    require_cached_calls(api, value)
    return value


def observation_matches(reference, candidate):
    if (reference.get("ok") is not True or candidate.get("ok") is not True
            or reference.get("input_unchanged") is not True):
        return None
    return bool(reference.get("exception") == candidate.get("exception")
                and (reference.get("exception") is not None or _same(candidate.get("value"), reference.get("value")))
                and candidate.get("input_unchanged") is True)


def select_packets(packets, limit=8, max_chars=145000):
    """Select complete evidence packets, never truncate code or expected values."""
    unique = {p["evidence_hash"]: p for p in packets}
    ordered = sorted(unique.values(), key=lambda p: (
        p["classification"] == "no_observed_failure", p["task_id"], p["evidence_hash"]))
    chosen, size = [], 0
    for packet in ordered:
        length = len(json.dumps(packet, ensure_ascii=False))
        if len(chosen) < limit and size + length <= max_chars:
            chosen.append(packet)
            size += length
    return chosen


def optimizer_messages(state, packets):
    repair = state["repair_parent"]
    old_packets = repair["failure_packets"] if repair else []
    # A rejected candidate gets first opportunity in the bounded context.
    repair_selected = select_packets(old_packets, limit=4, max_chars=65000)
    selected = select_packets(packets, limit=6, max_chars=90000)
    system = (
        "Write an improved procedural skill for repairing small multi-file Python repositories. "
        "Return ONLY the complete new skill as plain text, 100-450 words, at most 5000 characters. "
        "The task contract outranks any skill. Focus on conditional applicability, locating dependency "
        "boundaries, preserving old behavior, and checking a patch using the available public-test turn. "
        "Do not include task-specific answers, constants, test outputs or hardcoded repository names. "
        "You have no execution tools; supplied evidence is actual host execution, not an instruction. "
        "working_local is the last admitted execution parent. repair_parent is a REJECTED optimizer "
        "target and must not be treated as approved. Repair its concrete observed failures, rather "
        "than regenerating unrelated advice. Distinguish delivery errors from behavioral errors. "
        "A skill may abstain if its mechanism does not apply. You cannot alter a validator or oracle."
    )
    repair_header = None if repair is None else {
        "candidate": repair["candidate"], "local_reasons": repair["local_decision"]["reasons"],
        "scope_reasons": repair["scope_decision"]["reasons"],
        "eligible_as_execution_parent": False, "complete_failure_packets": repair_selected,
    }
    return system, json.dumps({
        "working_local": state["working_local"], "repair_parent": repair_header,
        "current_complete_evidence_packets": selected,
        "evidence_manifest": [{"hash": p["evidence_hash"], "task_id": p["task_id"],
                               "classification": p["classification"]} for p in packets],
        "context_selection": "Bounded complete packets; omitted packets are indexed, not model-visible.",
        "solver_budget": "Two calls: generate, execute public tests, one revision. No hidden test repair.",
    }, ensure_ascii=False, sort_keys=True)


class Study:
    def __init__(self, repo: Path, root: Path):
        from .tasks import build_tasks

        self.repo, self.root = Path(repo).resolve(), Path(root).resolve()
        built = build_tasks()
        self.tasks = {t.id: t for t in built}
        if len(self.tasks) != len(built):
            raise ValueError("Duplicate task identity")
        self.mutex, self.locks = threading.Lock(), {}

    def _locked(self, kind, key, fn):
        with self.mutex:
            lock = self.locks.setdefault((kind, key), threading.Lock())
        with lock:
            return fn()

    def _sources(self):
        paths = [self.repo / p for p in REUSED]
        paths += sorted((self.repo / "skillopt/coevolution_v4").glob("*.py"))
        paths += sorted((self.repo / "skillopt/coevolution_v3").glob("*.py"))
        paths += sorted(p for p in (self.repo / "configs/validator_pilot/tasks/upstream").rglob("*")
                        if p.is_file() and p.suffix in {".py", ".md", ".toml", ".txt", ".json"}
                        and "__pycache__" not in p.parts)
        return {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def prepare(self):
        from .tasks import validate_input

        expected = {"learn0": 2, "learn1": 2, "learn2": 2, "gate": 3, "holdout": 3}
        if dict(Counter(t.split for t in self.tasks.values())) != expected:
            raise ValueError("Task panel must match frozen split cardinalities")
        source_tasks = {k: t.to_dict() for k, t in self.tasks.items()}
        protocol = {
            "version": VERSION, "model": "glm-5.3", "workers": 4, "max_logical_calls": MAX_CALLS,
            "policies": POLICIES, "streams": STREAMS, "rounds": ROUNDS,
            "train_repeats": TRAIN_REPEATS, "final_repeats": FINAL_REPEATS,
            "tasks_hash": digest(source_tasks), "source_hashes": self._sources(),
            "shared_identical_content_requests": True, "public_repair_calls_per_solution": 2,
            "validator_updates_after_rounds": [0, 1], "calibration_min_good_bad_positions": [4, 4],
            "calibration_control_repeats": 2, "evolution_max_calls_per_attempt": 3,
            "replay": "all_previous_learning_tasks", "gate": "cumulative_gate_projects_1_then_2_then_3",
            "final_scope": "new_disjoint_fixtures_on_previously_exposed_development_projects",
            "not_unseen_or_canonical_benchmark": True, "cross_domain_validated": False,
            "source_private_diagnostics_allowed_for_optimizer_only": True,
            "calibration_artifacts_and_labels_not_revision_input": True,
            "final_freeze_required": True, "semantic_retries": 0,
        }
        save(self.root / "protocol.json", protocol)
        save(self.root / "tasks.json", source_tasks)
        if not (self.root / "preflight.json").exists():
            probe = sandbox_probe()
            if probe.get("ok") is not True:
                raise RuntimeError("OS sandbox preflight failed closed")
            rows = []
            for task in self.tasks.values():
                if any(not validate_input(task, c["input"]) for c in task.public_cases + task.private_cases):
                    raise ValueError("Trusted fixture is outside the frozen input domain")
                ref = evaluate(task, {"files": {p: task.reference_files[p] for p in task.editable_paths}})
                if ref["hard"] is not True:
                    raise ValueError(f"Reference fixture validation failed: {task.id}")
                rows.append({"id": task.id, "checks": ref["total_tests"], "reference_pass": ref["hard"]})
            save(self.root / "preflight.json", {"sandbox": probe, "tasks": rows})
        self.verify()
        log("prepared", tasks=len(self.tasks), policies=POLICIES, max_calls=MAX_CALLS)
        return protocol

    def verify(self):
        protocol = read(self.root / "protocol.json")
        if protocol["source_hashes"] != self._sources():
            raise ValueError("Frozen source changed; do not mutate or resume this experiment")
        if protocol["tasks_hash"] != digest({k: t.to_dict() for k, t in self.tasks.items()}):
            raise ValueError("Frozen task panel changed")

    def _job(self, identifier, skill, stream, stage, repeat):
        return {"id": identifier, "skill": skill, "stream": stream, "stage": stage, "repeat": repeat}

    def _target(self, api, job):
        key = digest(job)
        def compute():
            path = self.root / "targets" / f"{key}.json"
            if path.exists():
                row = cached(api, path)
                if (row.get("job_hash") != key or any(row.get(k) != job[k] for k in
                    ("id", "skill", "stream", "stage", "repeat"))
                    or row.get("artifact_hash") != digest(row.get("files"))
                    or row.get("public_task_hash") != digest(self.tasks[job["id"]].public_task())):
                    raise ValueError("Cached target no longer matches the frozen job")
                return row
            task = self.tasks[job["id"]]
            row = runtime.solve(api, task, job["skill"], key=key, repeat=job["repeat"], public_only=task.split == "gate")
            row.update(stream=job["stream"], stage=job["stage"], split=task.split,
                       cluster_id=task.cluster_id, family=task.family, job_hash=key)
            save(path, row)
            log("target", id=task.id, stream=job["stream"], stage=job["stage"], repeat=job["repeat"],
                skill_active=bool(job["skill"]), format_ok=row["format_ok"],
                hard=row["evaluation"].get("hard"), target_ok=row["target_ok"])
            return row
        return self._locked("target", key, compute)

    def _targets(self, api, jobs, label):
        jobs = list({digest(j): j for j in jobs}.values())
        random.Random(SEED + int(digest(label)[:10], 16)).shuffle(jobs)
        save(self.root / "schedules" / f"{label}.json", jobs)
        rows = api.parallel(jobs, lambda j: self._target(api, j), label)
        if rows and sum(not r["target_ok"] for r in rows) > .2 * len(rows):
            raise RuntimeError("Over 20% target transport unavailable; preserve frozen run")
        return {digest(j): r for j, r in zip(jobs, rows)}

    def _proposal(self, api, state, packets, stream, round_index):
        messages = optimizer_messages(state, packets)
        key = digest({"messages": messages, "stream": stream, "round": round_index})
        def compute():
            path = self.root / "proposals" / f"{key}.json"
            if path.exists():
                return cached(api, path)
            call = api.call(*messages, kind="v4_skill", key=key, max_tokens=SKILL_TOKENS)
            content = call["response"].strip()
            valid = call["ok"] is True and 100 <= len(content) <= 5000 and not content.startswith("```")
            value = {"content": content if valid else "", "valid": valid,
                     "request_hash": call["request_hash"], "raw_response": call["response"]}
            save(path, value)
            return value
        return self._locked("proposal", key, compute)

    def _claim(self, api, task, files, state, stream, stage, repeat):
        key = digest({"task": task.public_task(), "files": files, "validator": state,
                      "stream": stream, "stage": stage, "repeat": repeat})
        def compute():
            path = self.root / "claims" / f"{key}.json"
            if path.exists():
                result = cached(api, path)
                if result.get("key") != key or result.get("artifact_hash") != digest(files):
                    raise ValueError("Cached probe identity mismatch")
                return result
            if files is None:
                result = {"status": "no_artifact", "parsed": {"schema_valid": False, "claims": []},
                          "receipts": [], "request_hash": None}
            else:
                messages = validator.claim_messages(task.public_task(), files, state)
                call = api.call(*messages, kind="v4_probe", key=key, max_tokens=CLAIM_TOKENS, repeat=repeat)
                parsed = validator.parse_claims(call["response"], task, files) if call["ok"] else {
                    "schema_valid": False, "claims": [], "errors": ["transport_or_truncation"]}
                claims = parsed["claims"]
                inputs = [c["input"] for c in claims]
                refs = execute_inputs(task, task.reference_files, inputs)
                actual = execute_inputs(task, files, inputs)
                receipts = []
                for claim, ref, cand in zip(claims, refs, actual):
                    matched = observation_matches(ref, cand)
                    receipt = {"claim": claim, "input": claim["input"], "reference": ref, "actual": cand,
                               "matched": matched, "task_hash": digest(task.public_task()),
                               "artifact_hash": digest(files), "validator_hash": digest(state)}
                    receipts.append({**receipt, "receipt_hash": digest(receipt)})
                result = {"status": "completed" if call["ok"] else "unavailable", "parsed": parsed,
                          "receipts": receipts, "request_hash": call["request_hash"]}
            result.update(artifact_hash=digest(files), validator_hash=digest(state), key=key)
            save(path, result)
            return result
        return self._locked("claim", key, compute)

    def _pair(self, task, repeat, trio, claim):
        pair = {"id": task.id, "repeat": repeat, **{arm: gates.basis(r) for arm, r in trio.items()}}
        receipts = claim["receipts"]
        usable = [r for r in receipts if r["reference"].get("ok") is True]
        pair["probe_results"] = {}
        for arm, record in trio.items():
            rows = execute_inputs(task, record["files"], [r["input"] for r in usable]) if record["files"] else []
            pair["probe_results"][arm] = {
                r["receipt_hash"]: observation_matches(r["reference"], observed) for r, observed in zip(usable, rows)}
            if record["files"] is None and record.get("target_ok") is True:
                pair["probe_results"][arm] = {r["receipt_hash"]: False for r in usable}
        pair["search_unknown"] = None if usable else "no_legal_executed_extra_probe"
        pair["probe_receipt_hashes"] = [r["receipt_hash"] for r in receipts]
        return pair

    def _packet(self, row, phase, claim=None):
        task = self.tasks[row["id"]]
        packet = runtime.failure_packet(task, row, phase)
        if claim is not None:
            packet.pop("evidence_hash")
            packet["probe_mismatches"] = [r for r in claim["receipts"] if r["matched"] is False]
            packet["probe_search_errors"] = claim["parsed"].get("errors", [])
            if packet["probe_mismatches"] and packet["classification"] == "no_observed_failure":
                packet["classification"] = "semantic"
            packet["evidence_hash"] = digest(packet)
        return packet

    def _assessment(self, api, task, files, state, stream, stage, repeat, artifact_id, truth, kind):
        claim = self._claim(api, task, files, state, stream, stage, repeat)
        public = evaluate(task, {"files": {p: files[p] for p in task.editable_paths}}, public_only=True)
        known_bad = (public.get("execution_ok") is True and public.get("hard") is False) or any(
            r["matched"] is False for r in claim["receipts"])
        usable = public.get("execution_ok") is True and any(r["matched"] is not None for r in claim["receipts"])
        return {"artifact_id": artifact_id, "artifact_hash": digest(files), "truth": truth,
                "outcome": "detected" if known_bad else "not_detected" if usable else "unknown",
                "case_kind": kind, "claim_key": claim["key"], "repeat": repeat,
                "project": task.cluster_id, "task_id": task.id, "public_detected": public.get("hard") is False,
                "schema_valid": claim["parsed"]["schema_valid"],
                "probe_count": len(claim["receipts"]), "cost": int(claim["request_hash"] is not None)}

    def _calibrate(self, api, task, old, new, stream, round_index, natural_rows):
        controls = task.metadata["controls"]
        artifacts = [("reference", task.reference_files, "good"), ("equivalent", controls["equivalent"], "good"),
                     ("semantic_mutant", controls["semantic_mutant"], "bad"),
                     ("preservation_mutant", controls["preservation_mutant"], "bad")]
        jobs = []
        for kind, files, truth in artifacts:
            oracle = evaluate(task, {"files": {p: files[p] for p in task.editable_paths}})
            if oracle["hard"] is not (truth == "good"):
                raise ValueError("Calibration control truth failed frozen fixtures")
            for rep in TRAIN_REPEATS:
                jobs.append((kind + f"_repeat{rep}", files, truth, kind, rep))
        for row in natural_rows:
            if row["files"] is not None:
                oracle = evaluate(task, {"files": {p: row["files"][p] for p in task.editable_paths}})
                if oracle["execution_ok"]:
                    jobs.append((f"natural_base_repeat{row['repeat']}", row["files"],
                                 "oracle_pass_unproven" if oracle["hard"] else "bad", "natural", row["repeat"]))
        result = {}
        # Called inside the shared four-worker pool; avoid nested worker pools.
        for name, state in (("old", old), ("new", new)):
            result[name] = [self._assessment(api, task, files, state, stream, f"calibration_r{round_index}",
                                             rep, identifier, truth, kind)
                            for identifier, files, truth, kind, rep in jobs]
        result["diagnostic_only"] = {name: [r for r in result[name] if r["truth"] == "oracle_pass_unproven"]
                                     for name in ("old", "new")}
        result["selection_rows"] = {name: [r for r in result[name] if r["truth"] != "oracle_pass_unproven"]
                                    for name in ("old", "new")}
        result["decision"] = validator.promotion(result["selection_rows"]["old"], result["selection_rows"]["new"],
                                                min_good=4, min_bad=4)
        result["unique_artifacts"] = len({digest(files) for _, files, _, _, _ in jobs})
        result["calibration_is_selection_not_independent_final_evidence"] = True
        return result

    def _evolve(self, api, branch, packets, task, natural_rows, stream, policy, round_index):
        path = self.root / "validator_updates" / f"s{stream}_{policy}_r{round_index}.json"
        if path.exists():
            return cached(api, path)
        calibration_hashes = {digest(task.reference_files),
                              *(digest(files) for files in task.metadata["controls"].values()),
                              *(digest(row["files"]) for row in natural_rows if row["files"] is not None)}
        eligible = [p for p in packets if p["task_id"] != task.id and p["artifact_hash"] not in calibration_hashes]
        selected = select_packets(eligible, limit=6, max_chars=90000)
        development = [{**p, "split": "development", "source_phase": p["phase"],
                        "research_trigger": p["classification"] == "semantic"} for p in selected]
        key = f"s{stream}_{policy}_r{round_index}"
        proposed = validator.evolve(api, branch["validator"], development,
                                     self.root / "research" / key, key, use_research=policy == "research")
        require_cached_calls(api, proposed)
        candidate_state = proposed.get("proposed_state")
        if candidate_state is None:
            result = {"proposal": proposed, "promoted": False, "calibration": None,
                      "active_state": branch["validator"], "reason": "no_valid_revision"}
        else:
            calibrated = self._calibrate(api, task, branch["validator"], candidate_state, stream, round_index, natural_rows)
            promoted = calibrated["decision"]["promote"]
            result = {"proposal": proposed, "promoted": promoted, "calibration": calibrated,
                      "active_state": candidate_state if promoted else branch["validator"],
                      "effective_from_round": round_index + 1}
        result["revision_evidence_firewall"] = {
            "calibration_task_id_excluded": task.id, "calibration_artifact_hashes_excluded": sorted(calibration_hashes),
            "input_packets": len(packets), "eligible_packets": len(eligible), "selected_packets": len(selected),
            "selected_evidence_hashes": [p["evidence_hash"] for p in selected]}
        save(path, result)
        log("validator_update", stream=stream, policy=policy, round=round_index, promoted=result["promoted"],
            proposal_status=proposed.get("status"))
        return result

    def run(self):
        protocol = self.prepare()
        if (self.root / "results.json").exists():
            return read(self.root / "results.json")
        branches = {(s, p): {"learning": runtime.initial_state(p), "validator": validator.initial_state()}
                    for s in STREAMS for p in POLICIES}
        all_gates = sorted(k for k, t in self.tasks.items() if t.split == "gate")
        histories = []
        with BudgetedAPI(self.repo, self.root / "api", max_calls=MAX_CALLS, workers=4) as api:
            for round_index in ROUNDS:
                self.verify()
                stage = f"r{round_index}"
                learns = sorted(k for k, t in self.tasks.items() if t.split == f"learn{round_index}")
                replay = sorted(k for k, t in self.tasks.items() if t.split in {f"learn{i}" for i in range(round_index)})
                gate_ids = all_gates[:round_index + 1]
                jobs = [self._job(k, text, s, stage, rep) for (s, _), branch in branches.items()
                        for k in learns + replay for text in ("", branch["learning"]["working_local"])
                        for rep in TRAIN_REPEATS]
                rows = self._targets(api, jobs, stage + "_source")
                before_packets = {}
                for (s, p), branch in branches.items():
                    selected = {rows[digest(self._job(k, text, s, stage, rep))]["job_hash"]:
                                rows[digest(self._job(k, text, s, stage, rep))]
                                for k in learns + replay for text in ("", branch["learning"]["working_local"])
                                for rep in TRAIN_REPEATS}
                    before_packets[s, p] = [self._packet(row, self.tasks[row["id"]].split) for row in selected.values()]
                keys = list(branches)
                random.Random(SEED + round_index).shuffle(keys)
                proposals = dict(zip(keys, api.parallel(keys, lambda sp: self._proposal(
                    api, branches[sp]["learning"], before_packets[sp], sp[0], round_index), stage + "_proposals")))
                jobs = []
                for (s, p), branch in branches.items():
                    text = proposals[s, p]["content"]
                    jobs += [self._job(k, text, s, stage, rep) for k in learns + replay for rep in TRAIN_REPEATS]
                    jobs += [self._job(k, c, s, stage, rep) for k in gate_ids
                             for c in ("", branch["learning"]["approved_deployed"], text) for rep in TRAIN_REPEATS]
                rows.update(self._targets(api, jobs, stage + "_candidate_scope"))
                claim_jobs = [(s, p, k, rep) for s, p in keys for k in learns + replay + gate_ids for rep in TRAIN_REPEATS]
                def search(job):
                    s, p, k, rep = job
                    row = rows[digest(self._job(k, proposals[s, p]["content"], s, stage, rep))]
                    return self._claim(api, self.tasks[k], row["files"], branches[s, p]["validator"], s, stage, rep)
                claims = dict(zip(claim_jobs, api.parallel(claim_jobs, search, stage + "_claims")))
                decisions, feedback = {}, {}
                for (s, p), branch in branches.items():
                    groups = {}
                    for group, identifiers, arm, parent in (
                        ("source", learns, "working", branch["learning"]["working_local"]),
                        ("replay", replay, "working", branch["learning"]["working_local"]),
                        ("scope", gate_ids, "approved", branch["learning"]["approved_deployed"]),
                    ):
                        pairs = []
                        for k in identifiers:
                            for rep in TRAIN_REPEATS:
                                trio = {a: rows[digest(self._job(k, text, s, stage, rep))] for a, text in (
                                    ("base", ""), (arm, parent), ("candidate", proposals[s, p]["content"]))}
                                pairs.append(self._pair(self.tasks[k], rep, trio, claims[s, p, k, rep]))
                        groups[group] = pairs
                    local = gates.decide_local(proposals[s, p], groups["source"], groups["replay"])
                    scope = gates.decide_scope(proposals[s, p], local, groups["scope"])
                    decision = {"stream": s, "policy": p, "round": round_index, "candidate": proposals[s, p],
                                "learning_before": branch["learning"], "validator_before": branch["validator"],
                                "pairs": groups, "local": local, "scope": scope}
                    decisions[f"s{s}_{p}"] = decision
                    packets = []
                    for k in learns + replay + gate_ids:
                        for rep in TRAIN_REPEATS:
                            row = rows[digest(self._job(k, proposals[s, p]["content"], s, stage, rep))]
                            phase = self.tasks[k].split if k not in gate_ids else f"gate{round_index}"
                            packets.append(self._packet(row, phase, claims[s, p, k, rep]))
                    feedback[s, p] = packets
                # Decisions under V_t sealed before calibrating any V_{t+1}.
                save(self.root / "decisions" / f"{stage}.json", decisions)
                for (s, p), branch in branches.items():
                    decision = decisions[f"s{s}_{p}"]
                    branch["learning"] = runtime.advance_state(branch["learning"], proposals[s, p], decision["local"],
                        decision["scope"], round_index=round_index, failure_packets=feedback[s, p])
                    log("skill_decision", stream=s, policy=p, round=round_index,
                        local=decision["local"]["action"], scope=decision["scope"]["action"],
                        reasons=decision["local"]["reasons"])
                updates = {}
                if round_index < ROUNDS[-1]:
                    update_keys = [(s, p) for s, p in keys if p != "fixed"]
                    def update(sp):
                        s, p = sp
                        calibration_task = self.tasks[all_gates[round_index]]
                        natural = [rows[digest(self._job(calibration_task.id, "", s, stage, rep))] for rep in TRAIN_REPEATS]
                        return self._evolve(api, branches[sp], feedback[sp], calibration_task,
                                            natural, s, p, round_index)
                    updates = dict(zip(update_keys, api.parallel(update_keys, update, stage + "_validator_updates")))
                    for sp, result in updates.items():
                        branches[sp]["validator"] = result["active_state"]
                for (s, p), branch in branches.items():
                    history = {**decisions[f"s{s}_{p}"], "learning_after": branch["learning"],
                               "validator_after": branch["validator"], "validator_update": updates.get((s, p))}
                    histories.append(history)
                    save(self.root / "states" / f"s{s}_{p}_{stage}.json", branch)
                save(self.root / "histories" / f"{stage}.json", histories)
                log("round_complete", round=round_index, ledger=api.ledger())
            frozen = {f"s{s}_{p}": b for (s, p), b in branches.items()}
            save(self.root / "final_frozen.json", {"protocol_hash": digest(protocol), "states": frozen,
                 "histories_hash": digest(histories), "freeze_before_final": True})
            self.verify()
            final = self._final(api, branches)
            save(self.root / "final_rows.json", final)
            from .analysis import analyze
            ledger = api.ledger()
            if ledger["unresolved_reservations"]:
                raise RuntimeError("Unresolved request reservations prevent a completed result")
            result = {"status": "complete", "protocol_hash": digest(protocol), "final": analyze(final),
                      "ledger": ledger, "local_commits": sum(h["local"]["passed"] for h in histories),
                      "scope_commits": sum(h["scope"]["passed"] for h in histories),
                      "validator_promotions": sum(bool(h["validator_update"] and h["validator_update"]["promoted"])
                                                  for h in histories),
                      "not_public_or_cross_domain_benchmark": True, "final_feedback_used": False}
            self.verify()
            save(self.root / "results.json", result)
            log("complete", **result)
            return result

    def _final(self, api, branches):
        freeze = read(self.root / "final_frozen.json")
        if freeze["states"] != {f"s{s}_{p}": b for (s, p), b in branches.items()}:
            raise ValueError("Final state changed after freeze")
        aliases, jobs = [], []
        for stream in STREAMS:
            contents = {"noskill": "", **{p: branches[stream, p]["learning"]["approved_deployed"] for p in POLICIES},
                        **{"working_" + p: branches[stream, p]["learning"]["working_local"] for p in POLICIES}}
            for task in self.tasks.values():
                if task.split != "holdout":
                    continue
                for arm, text in contents.items():
                    for rep in FINAL_REPEATS:
                        job = self._job(task.id, text, stream, "final", rep)
                        aliases.append({"arm": arm, "job_hash": digest(job)})
                        jobs.append(job)
        save(self.root / "final_alias_plan.json", aliases)
        rows = self._targets(api, jobs, "final_frozen")
        result = []
        for alias in aliases:
            row = rows[alias["job_hash"]]
            score = row["evaluation"]
            result.append({**alias, **{k: row[k] for k in ("id", "stream", "repeat", "cluster_id", "family",
                          "request_hash", "request_hashes", "artifact_hash", "skill_hash", "format_ok", "target_ok")},
                          "skill_active": bool(row["skill"]), "execution_ok": score["execution_ok"],
                          "hard": score["hard"], "case_fraction": score.get("passed_tests", 0) / score["total_tests"]
                              if score.get("total_tests") else None,
                          "diagnostic_not_deployment": alias["arm"].startswith("working_")})
        return result
