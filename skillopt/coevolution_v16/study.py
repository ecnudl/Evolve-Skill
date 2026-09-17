"""Four-round, lagged, calibrated evidence/Skill co-evolution pilot.

All arms use one updater, structured feedback and an identical solver. Final
evaluation is forbidden until every history/checkpoint is frozen. This pilot
studies raw Skill content, not routing/scope promotion or public-benchmark SOTA.
"""

from __future__ import annotations

import hashlib
import json
import random
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v8.feedback_study import payload
from skillopt.coevolution_v9.study import OfflineAPI, closed_ledger, stable_api
from skillopt.coevolution_v12.study import read, save
from skillopt.coevolution_v15 import analysis, evidence, learning, runtime, tasks
from skillopt.coevolution_v15.study import source_hashes as previous_sources
from skillopt.validator_pilot.api import digest

from . import research, validator

VERSION = "v16-lagged-calibrated-normalized-evidence-v1"
SEED = 2026091505
POLICIES = ("no_skill", *learning.ARMS)
DESIGNS = {
    "smoke": {"histories": 1, "rounds": 2, "max_calls": 192},
    "pilot": {"histories": 3, "rounds": 4, "max_calls": 1536},
}


class PauseRequested(RuntimeError):
    pass


def safe_root(repo, output):
    repo, raw = Path(repo).resolve(), Path(output).absolute()
    parent = repo / "outputs/coevolution_v16"
    if (any(p.is_symlink() for p in (raw, *raw.parents)) or ".." in raw.parts
            or raw == parent or not raw.is_relative_to(parent)):
        raise ValueError("Use a dedicated nonsymlink output beneath outputs/coevolution_v16")
    if raw.exists() and any(p.is_symlink() for p in raw.rglob("*")):
        raise ValueError("Symlink run evidence is forbidden")
    return raw


def source_hashes(repo):
    repo = Path(repo)
    result = previous_sources(repo)
    paths = list((repo / "skillopt/coevolution_v16").glob("*.py"))
    paths += [repo / "scripts/coevolution_v16.py", repo / "scripts/launch_coevolution_v16.py",
              repo / "scripts/check_coevolution_v16_research.py",
              repo / "skillopt/validator_document_transport.py", repo / "docs/coevolution-v16-protocol.md"]
    result.update({str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})
    return result


class Study:
    def __init__(self, repo, root, *, design="pilot", workers=4, panel=None, api_factory=stable_api):
        if design not in DESIGNS or workers != 4:
            raise ValueError("Use a registered smoke/pilot design and four stable workers")
        self.repo = Path(repo).resolve()
        self.root = safe_root(self.repo, root)
        self.design, self.workers = design, workers
        self.histories, self.rounds, self.max_calls = (DESIGNS[design][k] for k in ("histories", "rounds", "max_calls"))
        self.panel, self.api_factory = panel, api_factory
        self.production_panel = panel is None
        self.complete = (self.root / "results.json").is_file()
        self.memo, self.api = {}, None
        self.event_number = len(list((self.root / "events").glob("*.json")))
        self.searches, self.assessments, self.updates, self.promotions = [], [], [], []
        self.validator_proposals = []

    def _event(self, stage, **details):
        if self.complete:
            return
        self.event_number += 1
        row = {"version": VERSION, "stage": stage, "sequence": self.event_number,
               "time_utc": datetime.now(timezone.utc).isoformat(), **details}
        save(self.root / "events" / f"{self.event_number:06d}.json", row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def _guard(self):
        if source_hashes(self.repo) != self.protocol["source_hashes"]:
            raise ValueError("Frozen source drift; preserve receipts and start a separately registered version")
        if not self.complete and (self.root / "PAUSE").exists():
            self._event("paused_after_draining_inflight")
            raise PauseRequested("Paused with in-flight receipts retained")

    def prepare(self):
        if self.panel is None:
            self.panel = tasks.build_panel(smoke=self.design == "smoke")
        if (set(self.panel) != {"train", "calibration", "final"}
                or len(self.panel["train"]) != self.rounds
                or len(self.panel["calibration"]) != self.rounds - 1):
            raise ValueError("Actual panel differs from the registered round/split design")
        groups = {"train": [[payload(a) for a in batch] for batch in self.panel["train"]],
                  "calibration": [[payload(a) for a in batch] for batch in self.panel["calibration"]],
                  "final": [payload(a) for a in self.panel["final"]]}
        flattened = {k: (v if k == "final" else [t for batch in v for t in batch]) for k, v in groups.items()}
        all_tasks = [t for group in flattened.values() for t in group]
        if len({t["id"] for t in all_tasks}) != len(all_tasks):
            raise ValueError("Task overlap across development/calibration/final partitions")
        clusters = {k: {t["cluster_id"] for t in rows} for k, rows in flattened.items()}
        if any(clusters[a] & clusters[b] for a, b in (("train", "calibration"), ("train", "final"), ("calibration", "final"))):
            raise ValueError("Authored structural families overlap across partitions")
        if any(t.get("domain", "coding") == "rule_reasoning" for k in ("train", "calibration") for t in flattened[k]):
            raise ValueError("The held-out Rule domain cannot reach development or calibration")
        registered = save(self.root / "private_panel.json", {"version": VERSION, "groups": groups,
            "host_only_references": True, "final_gold_never_model_input": True}, completed=self.complete)
        if self.production_panel:
            path = self.root / "task_preflight.json"
            checked = read(path) if path.exists() else save(path, tasks.self_check(self.panel), completed=self.complete)
            if checked.get("all_checked") is not True:
                raise ValueError("Offline task/oracle controls did not pass")
        else:
            checked = {"record_hash": None}
        sources = source_hashes(self.repo)
        # Preserve reconstructable source evidence even if a stopped diagnostic
        # later requires a NEW code version/run; old evidence is never rewritten.
        snapshot = save(self.root / "source_snapshot.json", {"version": VERSION,
            "files": {name: (self.repo / name).read_text(encoding="utf-8") for name in sources}}, completed=self.complete)
        self.protocol = save(self.root / "protocol.json", {"version": VERSION, "design": self.design,
            **DESIGNS[self.design], "workers": 4, "model": "glm-5.3", "seed": SEED,
            "http_min_interval_seconds": 10, "source_hashes": sources,
            "source_snapshot_hash": snapshot["record_hash"], "panel_hash": registered["record_hash"],
            "task_preflight_hash": checked["record_hash"], "policies": list(POLICIES),
            "split_counts": {k: len(v) for k, v in flattened.items()},
            "learning_arms": list(learning.ARMS), "all_arms_structured_feedback": True,
            "shared_skill_updater": learning.VERSION, "max_probes_per_search": 4,
            "one_round_validator_activation_delay": True, "separate_calibration_slices": True,
            "calibration_is_descriptive_not_statistical_safety_certificate": True,
            "research_is_bounded_official_document_retrieval": True,
            "research_presentation_version": research.VERSION,
            "research_fix": "normalize_already_truncated_visible_whitespace_before_prompt",
            "task_panel_and_scientific_thresholds_unchanged_from_v15": True,
            "equal_solver_optimizer_probe_opportunities": True, "equal_total_compute_claimed": False,
            "public_benchmark": False, "native_skillopt_baseline": False,
            "scope_promotion": False, "skill_selection_or_routing": False,
            "raw_valid_skill_updates_retained": True, "final_validator_online_assistance": False,
            "all_checkpoints_frozen_before_any_final": True,
            "identical_interventions_aliased_within_history_only": True,
            "natural_calibration_artifacts_are_no_skill_and_not_learning_feedback": True,
            "checkpoint_panel": "first_two_final_families_each_development_domain",
            "pilot_family_count_not_power_guarantee": True}, completed=self.complete)
        self._guard()
        return self.protocol

    def _key(self, adapter, text, phase, history):
        return digest({"task_hash": digest(payload(adapter)), "skill": learning.text_hash(text),
                       "phase": phase, "history": history})

    def _batch(self, requests, label):
        distinct = {self._key(a, s, p, h): (a, s, p, h) for a, s, p, h in requests}
        pending = [(k, v) for k, v in distinct.items() if k not in self.memo]
        random.Random(SEED + sum(map(ord, label))).shuffle(pending)

        def work(item):
            key, (adapter, text, phase, history) = item
            return key, runtime.solve(adapter, self.api, text, root=self.root, key=key,
                                      repeat=history, phase=phase, completed=self.complete)

        if self.complete:
            self.memo.update(work(item) for item in pending)
        else:
            index, done_count, error, active = 0, 0, None, set()
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                while active or index < len(pending):
                    while index < len(pending) and len(active) < self.workers and error is None:
                        try:
                            self._guard()
                        except Exception as exc:
                            error = exc
                            break
                        active.add(pool.submit(work, pending[index]))
                        index += 1
                    if not active:
                        break
                    done, active = wait(active, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            key, row = future.result()
                            self.memo[key] = row
                            done_count += 1
                            self._guard()
                            self._event(label, closed_trajectories=done_count, admitted_total=len(pending))
                        except Exception as exc:
                            error = error or exc
                if error is not None:
                    raise error
        self._guard()
        return [self.memo[self._key(a, s, p, h)] for a, s, p, h in requests]

    def _project(self, solve):
        hashes = solve["request_hashes"]
        return evidence.project_development_feedback(solve,
            [read(self.root / "runtime/stages" / (h + ".json")) for h in hashes],
            api_receipts=[json.loads((self.root / "api/calls" / (h + ".json")).read_text()) for h in hashes],
            executions={i: read(self.root / "runtime/executions" / (i + ".json")) for i in solve["execution_ids"]})

    def _feedback(self, adapters, base, current, state, history, round_index):
        public, observations, probes = [], [], []
        for adapter, anchor, solved in zip(adapters, base, current):
            task = payload(adapter)
            view = tasks.public_task(adapter)
            view.update(id=task["id"], obligations=tasks.constraints_for(adapter))
            public.append(view)
            search_key = digest({"task": digest(task), "state": state["record_hash"],
                                 "history": history, "round": round_index, "phase": "development"})
            self._guard()
            searched = validator.search(self.api, adapter, state, root=self.root, key=search_key,
                                         repeat=history, completed=self.complete)
            self.searches.append(searched)
            for role, row in (("no_skill", anchor), ("current", solved)):
                observations.append({"role": role, "artifact": deepcopy(row["artifact"]), "feedback": self._project(row)})
                probe_key = digest({"search": searched["record_hash"], "solve": row["record_hash"]})
                self._guard()
                assessed = validator.assess(adapter, row["artifact"], searched,
                    root=self.root, key=probe_key, completed=self.complete)
                self.assessments.append(assessed)
                probes.append(assessed)
        return public, observations, probes

    def _learn(self, history, round_index, arm, parent, public, observations, probes):
        system, user, feedback_hash = learning.messages(parent, public, observations, probes)
        # Equal input interventions share the same real draw ONLY in this history.
        key = digest({"history": history, "round": round_index, "feedback_hash": feedback_hash})
        args = {"system": system, "user": user, "kind": "v15_skill_update", "key": key,
                "max_tokens": learning.TOKEN_CAP, "repeat": history}
        request = {**args, "model": self.api.model, "service": self.api.service}
        request_hash = digest(request)
        path = self.root / "api/calls" / (request_hash + ".json")
        intent_path = self.root / "learning_intents" / (request_hash + ".json")
        intent = {"version": VERSION, "request_hash": request_hash, "feedback_hash": feedback_hash,
                  "parent_hash": digest(parent)}
        if path.exists():
            save(intent_path, intent, completed=True)
            receipt = json.loads(path.read_text())
        else:
            if self.complete or intent_path.exists():
                raise ValueError("Unresolved Skill update; no silent resampling")
            self._guard()
            save(intent_path, intent)
            receipt = self.api.call(**args)
        if receipt.get("request") != request or receipt.get("request_hash") != request_hash or json.loads(path.read_text()) != receipt:
            raise ValueError("Skill update differs from actual durable API receipt")
        parsed = learning.parse_update(receipt, parent)
        result = save(self.root / "learning" / f"h{history}-r{round_index}-{arm}.json", {
            "version": VERSION, "history": history, "round": round_index, "arm": arm,
            "parent_hash": learning.text_hash(parent["skill"]), "feedback_hash": feedback_hash,
            "request_hash": request_hash, "api_receipt_hash": digest(receipt), **parsed,
            "skill_hash": learning.text_hash(parsed["skill"]), "changed": parent["skill"] != parsed["skill"],
            "calibration_or_final_feedback_used": False}, completed=self.complete)
        self.updates.append(result)
        self._guard()
        return result

    def _row(self, solve, history, policy, text, round_index):
        return {"task_id": solve["task_id"], "domain": solve["domain"], "cluster_id": solve["cluster_id"],
            "history": history, "policy": policy, "round": round_index, "phase": "final",
            "passed": bool(solve["score"]["all_attempt_success"]),
            "oracle_available": bool(solve["score"]["oracle_available"]),
            "artifact_valid": bool(solve["score"]["delivery_valid"]),
            "skill_hash": learning.text_hash(text), "skill_nonempty": bool(text.strip()),
            "solver_record_hash": solve["record_hash"], "request_hashes": solve["request_hashes"],
            "chosen_stage": solve["chosen_stage"], "rollback_reason": solve["rollback_reason"]}

    def _closure(self):
        actual = {p.stem for p in (self.root / "api/calls").glob("*.json")}
        expected = {h for r in self.memo.values() for h in r["request_hashes"]}
        expected.update(r["request_hash"] for r in self.updates)
        # Validator's nested sealed receipts are inventoried explicitly; every
        # request_hash must bind a real API receipt, including invalid outputs.
        for directory in ("validator", "research"):
            for path in (self.root / directory).rglob("*.json"):
                if "snapshots" in path.relative_to(self.root / directory).parts:
                    # Transport snapshots are byte-hashed by the research bundle,
                    # not model-call receipts and not all use the seal schema.
                    continue
                record = read(path)
                def collect(value):
                    if isinstance(value, dict):
                        for name, nested in value.items():
                            if name == "request_hash" and isinstance(nested, str):
                                expected.add(nested)
                            elif name == "request_hashes" and isinstance(nested, list):
                                expected.update(x for x in nested if isinstance(x, str))
                            else:
                                collect(nested)
                    elif isinstance(value, list):
                        for nested in value:
                            collect(nested)
                collect(record)
        if actual != expected:
            raise ValueError(f"API closure differs: orphan={len(actual - expected)}, missing={len(expected - actual)}")
        for path in (self.root / "runtime").rglob("execution_intents/*.json"):
            target = path.parent.parent / "executions" / path.name
            if not target.is_file():
                raise ValueError("Unresolved native execution intent")
            read(target)
        return {"all_api_receipts_accounted": True, "unique_api_requests": len(actual),
                "solver_trajectories": len(self.memo), "unresolved_native_intents": 0}

    def run(self):
        self.prepare()
        self.api = OfflineAPI(self.root / "api") if self.complete else self.api_factory(
            self.repo, self.root / "api", max_calls=self.max_calls, workers=self.workers)
        self.api.before_validator_request = self._guard
        try:
            skills = [{a: learning.empty_state() for a in learning.ARMS} for _ in range(self.histories)]
            validators = [{a: validator.initial_state() for a in learning.ARMS} for _ in range(self.histories)]
            checkpoints, natural_cache = [], {}
            for r, adapters in enumerate(self.panel["train"]):
                for h in range(self.histories):
                    self._event("learning_round", history=h, round=r)
                    texts = {"no_skill": "", **{a: skills[h][a]["skill"] for a in learning.ARMS}}
                    positions = [(p, a) for p in POLICIES for a in adapters]
                    solved = self._batch([(a, texts[p], "development", h) for p, a in positions], f"development_h{h}_r{r}")
                    by_policy = {p: solved[i * len(adapters):(i + 1) * len(adapters)] for i, p in enumerate(POLICIES)}
                    new_validators = deepcopy(validators[h])
                    for arm in (learning.ARMS if (h + r) % 2 == 0 else learning.ARMS[::-1]):
                        current_validator = validators[h][arm]
                        public, observations, probes = self._feedback(adapters, by_policy["no_skill"], by_policy[arm], current_validator, h, r)
                        update = self._learn(h, r, arm, skills[h][arm], public, observations, probes)
                        skills[h][arm] = update["state"]
                        self._event("skill_updated", history=h, round=r, arm=arm, valid=update["valid"], changed=update["changed"])
                        if arm == "fixed" or r == self.rounds - 1:
                            continue
                        development = {"phase": "development", "history": h, "round": r,
                            "public_tasks": public, "observations": observations, "probes": probes,
                            "skill_update_hash": update["record_hash"]}
                        self._guard()
                        proposed = validator.propose(self.api, current_validator, [seal(development)], arm=arm,
                            root=self.root, key=f"h{h}-r{r}-{arm}", repeat=h, completed=self.complete)
                        self.validator_proposals.append(proposed)
                        if proposed["valid"]:
                            cal_panel = self.panel["calibration"][r]
                            if (h, r) not in natural_cache:
                                natural_cache[h, r] = self._batch([(a, "", "calibration", h) for a in cal_panel], f"natural_calibration_h{h}_r{r}")
                            naturals = {row["task_id"]: row for row in natural_cache[h, r]}
                            self._guard()
                            calibrated = validator.calibrate(self.api, cal_panel, current_validator, proposed["candidate_state"],
                                root=self.root, key=f"h{h}-r{r}-{arm}", repeat=h, completed=self.complete,
                                natural_artifacts=naturals)
                            self.promotions.append(calibrated)
                            new_validators[arm] = calibrated["accepted_state"]
                            self._event("validator_calibrated", history=h, round=r, arm=arm,
                                accepted=calibrated["accepted"], effective_round=r + 1)
                        else:
                            self._event("validator_proposal_invalid", history=h, round=r, arm=arm)
                    # No new verifier can alter feedback already used this round.
                    validators[h] = new_validators
                checkpoint = save(self.root / "checkpoints" / f"round_{r}.json", {"version": VERSION,
                    "round": r, "skills": deepcopy(skills), "validators_for_next_round": deepcopy(validators),
                    "completed_updates": [u["record_hash"] for u in self.updates]}, completed=self.complete)
                checkpoints.append(checkpoint)
            frozen = save(self.root / "final_frozen.json", {"version": VERSION,
                "protocol_hash": self.protocol["record_hash"], "skills": skills, "validators": validators,
                "checkpoint_hashes": [c["record_hash"] for c in checkpoints],
                "skill_update_hashes": [u["record_hash"] for u in self.updates],
                "validator_proposal_hashes": [p["record_hash"] for p in self.validator_proposals],
                "calibration_hashes": [p["record_hash"] for p in self.promotions]}, completed=self.complete)
            self._event("all_histories_and_checkpoints_frozen", frozen_hash=frozen["record_hash"])
            rows = []
            for h in range(self.histories):
                texts = {"no_skill": "", **{a: skills[h][a]["skill"] for a in learning.ARMS}}
                positions = [(p, a) for p in POLICIES for a in self.panel["final"]]
                solved = self._batch([(a, texts[p], "final", h) for p, a in positions], f"frozen_final_h{h}")
                rows.extend(self._row(row, h, policy, texts[policy], self.rounds - 1) for row, (policy, _) in zip(solved, positions))
            final_grid = save(self.root / "final_rows.json", {"version": VERSION, "frozen_hash": frozen["record_hash"], "rows": rows}, completed=self.complete)
            retained = []
            audit_tasks = [a for domain in ("coding", "spreadsheet") for a in [t for t in self.panel["final"] if t.domain == domain][:2]]
            for checkpoint in checkpoints[:-1]:
                r = checkpoint["round"]
                for h in range(self.histories):
                    texts = {"no_skill": "", **{a: checkpoint["skills"][h][a]["skill"] for a in learning.ARMS}}
                    positions = [(p, a) for p in POLICIES for a in audit_tasks]
                    solved = self._batch([(a, texts[p], "final", h) for p, a in positions], f"frozen_checkpoint_r{r}_h{h}")
                    retained.extend(self._row(row, h, policy, texts[policy], r) for row, (policy, _) in zip(solved, positions))
            retained.extend(row for row in rows if row["task_id"] in {payload(a)["id"] for a in audit_tasks})
            checkpoint_grid = save(self.root / "checkpoint_rows.json", {"version": VERSION,
                "frozen_hash": frozen["record_hash"], "rows": retained,
                "diagnostic_subset_only": True, "feedback_allowed": False}, completed=self.complete)
            expected = {payload(a)["id"]: {"domain": a.domain, "cluster_id": payload(a)["cluster_id"]} for a in self.panel["final"]}
            summary = analysis.summarize(rows, policies=POLICIES, expected_tasks=expected, expected_histories=list(range(self.histories)))
            ledger, closure = closed_ledger(self.root, self.max_calls), self._closure()
            self._guard()
            result = save(self.root / "results.json", {"version": VERSION, "complete": True,
                "design": self.design, "protocol_hash": self.protocol["record_hash"],
                "frozen_hash": frozen["record_hash"], "final_grid_hash": final_grid["record_hash"],
                "checkpoint_grid_hash": checkpoint_grid["record_hash"], "summary": summary,
                "ledger": ledger, "evidence_closure": closure,
                "learning": {"update_positions": len(self.updates), "valid": sum(u["valid"] for u in self.updates),
                    "changed": sum(u["changed"] for u in self.updates),
                    "unique_update_calls": len({u["request_hash"] for u in self.updates})},
                "validator_evolution": {"proposals": len(self.validator_proposals),
                    "valid_proposals": sum(p["valid"] for p in self.validator_proposals),
                    "calibrations": len(self.promotions), "accepted": sum(p["accepted"] for p in self.promotions)},
                "public_benchmark": False, "raw_skill_content_not_routing": True,
                "statistical_safety_certification": False}, completed=self.complete)
            self._event("finished", result_hash=result["record_hash"], calls=ledger["cached_logical_calls"])
            return result
        finally:
            if not self.complete and self.api is not None:
                self.api.close()
