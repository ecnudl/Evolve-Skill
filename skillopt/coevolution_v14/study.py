"""Predeclared three-arm constraint-feedback/local-patch experiment.

Every history is a real sampling block, including No-Skill. Equal model-call
opportunities do not mean equal probe-oracle/context budgets. Final evaluation
starts only after ALL histories' Skills are frozen; no candidate selection.
"""

from __future__ import annotations

import hashlib
import json
import random
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v8.feedback_study import payload, public_task
from skillopt.coevolution_v9.study import OfflineAPI, closed_ledger, stable_api
from skillopt.coevolution_v12.study import read, save
from skillopt.coevolution_v12.study import source_hashes as old_source_hashes
from skillopt.validator_pilot.api import digest

from . import evidence, learning, runtime, tasks

VERSION = "v14-constraint-counterexample-local-patch-study-v1"
SEED = 2026091504
POLICIES = ("no_skill", *learning.ARMS)


def safe_root(repo, output):
    repo, raw = Path(repo).resolve(), Path(output).absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("Symlink experiment paths are forbidden")
    parent = repo / "outputs/coevolution_v14"
    if raw == parent or not raw.is_relative_to(parent) or ".." in raw.parts:
        raise ValueError("Use a dedicated output beneath outputs/coevolution_v14")
    if raw.exists() and any(p.is_symlink() for p in raw.rglob("*")):
        raise ValueError("Symlink experiment entries are forbidden")
    return raw


def source_hashes(repo):
    result = old_source_hashes(repo)
    paths = [p for name in ("coevolution_v13", "coevolution_v14")
             for p in (repo / "skillopt" / name).glob("*.py")]
    paths += [repo / "scripts/coevolution_v14.py", repo / "docs/coevolution-v14-protocol.md"]
    result.update({str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})
    return result


class PauseRequested(RuntimeError):
    pass


class Study:
    def __init__(self, repo, root, *, design="formal", max_calls=None, workers=4, panel=None, api_factory=stable_api):
        if design not in {"smoke", "formal"} or workers != 4:
            raise ValueError("Use the frozen smoke/formal design with four workers")
        self.repo, self.design = Path(repo).resolve(), design
        self.root = safe_root(self.repo, root)
        self.histories, self.rounds = (1, 1) if design == "smoke" else (3, 2)
        self.max_calls = 64 if design == "smoke" else 640
        if max_calls is not None and max_calls != self.max_calls:
            raise ValueError("Cannot override the registered logical-call budget")
        self.api_factory, self.panel = api_factory, panel
        self.production_panel = panel is None
        self.complete = (self.root / "results.json").exists()
        self.event_number = len(list((self.root / "events").glob("*.json")))
        self.api = None
        self.memo, self.probes = {}, {}

    def _event(self, stage, **details):
        if self.complete:
            return
        self.event_number += 1
        event = {"version": VERSION, "sequence": self.event_number,
                 "time_utc": datetime.now(timezone.utc).isoformat(), "stage": stage, **details}
        save(self.root / "events" / f"{self.event_number:06d}.json", event)
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def _pause(self):
        if not self.complete and (self.root / "PAUSE").exists():
            self._event("paused_after_draining_inflight")
            raise PauseRequested("Paused with completed in-flight jobs retained")

    def _check_sources(self):
        if source_hashes(self.repo) != self.protocol["source_hashes"]:
            raise ValueError("Frozen source drift; never alter already admitted experiment evidence")

    def prepare(self):
        if self.panel is None:
            self.panel = tasks.build_panel(smoke=self.design == "smoke")
        if len(self.panel["train"]) != self.rounds or set(self.panel) != {"train", "final"}:
            raise ValueError("Panel rounds/splits differ from registration")
        groups = {"train": [payload(a) for group in self.panel["train"] for a in group],
                  "final": [payload(a) for a in self.panel["final"]]}
        ids = [t["id"] for group in groups.values() for t in group]
        if len(ids) != len(set(ids)) or any(t.get("domain", "coding") == "rule_reasoning" for t in groups["train"]):
            raise ValueError("Task overlap or held-out domain in development")
        if self.design == "formal":
            if len(groups["train"]) != 8 or len(groups["final"]) != 24:
                raise ValueError("Formal task counts differ from registration")
            if {t["cluster_id"] for t in groups["train"]} & {t["cluster_id"] for t in groups["final"]}:
                raise ValueError("Formal structural families overlap")
            for domain in ("coding", "spreadsheet", "rule_reasoning"):
                domain_rows = [t for t in groups["final"] if t.get("domain", "coding") == domain]
                if len(domain_rows) != 8 or len({t["cluster_id"] for t in domain_rows}) != 8:
                    raise ValueError("Exactly eight new authored final structures per domain required")
        registered = save(self.root / "private_panel.json", {"version": VERSION, "groups": groups,
            "reference_artifacts_never_model_inputs": True, "final_hidden_data_never_model_inputs": True,
            "development_executed_checks_may_reach_updater": True}, completed=self.complete)
        frozen_sources = source_hashes(self.repo)
        preflight_hash = None
        if self.production_panel:
            path = self.root / "task_preflight.json"
            if path.exists():
                checked = read(path)
            elif self.complete:
                raise ValueError("Completed run missing task preflight")
            else:
                checked = save(path, tasks.self_check(self.panel, coding=True))
            expected = {t["id"]: digest(t) for group in groups.values() for t in group}
            actual = {r["task_id"]: r["task_hash"] for r in checked["records"]}
            if (not checked.get("all_checked") or not checked.get("coding_checked")
                    or checked.get("model_api_calls") != 0 or expected != actual
                    or len(checked["records"]) != len(expected)):
                raise ValueError("Task calibration differs from the frozen production panel")
            for row in checked["records"]:
                controls = row["controls"]
                if (controls["reference"] != {"passed": True, "available": True}
                        or any(controls[k]["passed"] for k in ("starter", "semantic_mutant", "preservation_mutant"))
                        or any(not controls[k]["available"] for k in ("starter", "semantic_mutant"))):
                    raise ValueError("Task reference/starter/mutant calibration failed")
            probe_rows = checked["probe_records"]
            expected_probe_tasks = {t["id"] for t in groups["train"]}
            if ({r["task_id"] for r in probe_rows} != expected_probe_tasks
                    or len(probe_rows) != len(expected_probe_tasks)):
                raise ValueError("Missing development probe calibrations")
            adapters = {payload(a)["id"]: a for batch in self.panel["train"] for a in batch}
            for row in probe_rows:
                adapter = adapters[row["task_id"]]
                intended_checks = [{"obligation_id": p["obligation_id"], "probe_id": p["id"],
                                    "detected": True, "mutant_hash": digest(p["mutant"])}
                                   for p in payload(adapter)["metadata"]["counterexample_probe_pool"]]
                if (row["probe_task_hash"] != digest(payload(tasks.probe_adapter(adapter)))
                        or row.get("reference_passed") is not True or row.get("ordinary_inputs_disjoint") is not True
                        or row["checks"] != intended_checks):
                    raise ValueError("Probe reference or specific-obligation mutant calibration failed")
            preflight_hash = checked["record_hash"]
        if source_hashes(self.repo) != frozen_sources:
            raise ValueError("Source changed during offline task calibration")
        self.protocol = save(self.root / "protocol.json", {"version": VERSION, "design": self.design,
            "histories": self.histories, "rounds": self.rounds, "max_calls": self.max_calls,
            "seed": SEED, "policies": list(POLICIES), "learning_arms": list(learning.ARMS),
            "panel_hash": registered["record_hash"], "source_hashes": frozen_sources,
            "model": "glm-5.3", "workers": 4, "http_spacing_seconds": 10,
            "optimizer_token_cap": learning.TOKEN_CAP, "solver_token_cap": runtime.TOKENS,
            "task_preflight_hash": preflight_hash, "injected_test_panel": not self.production_panel,
            "public_benchmark": False, "native_skillopt_baseline": False,
            "research_validator_active": False, "probe_origin": "fixed_host_authored",
            "third_domain_development_feedback": False, "final_feedback_allowed": False,
            "all_raw_final_candidates_retained": True, "candidate_selection": False,
            "real_base_draw_per_history": True, "within_history_identical_task_text_alias": True,
            "equal_solver_and_optimizer_call_opportunities": True, "equal_oracle_context_budget": False,
            "bundled_intervention": "constraint_probes_plus_evidence_linked_local_patching",
            "common_delivery_guard": True, "semantic_guard": False}, completed=self.complete)
        return self.protocol

    def _solver_key(self, adapter, text, phase, history):
        return digest({"task": payload(adapter)["id"], "text": learning.text_hash(text),
                       "phase": phase, "history": history})

    def _batch(self, requests, label):
        distinct = {}
        for adapter, text, phase, history in requests:
            distinct.setdefault(self._solver_key(adapter, text, phase, history), (adapter, text, phase, history))
        pending = [(k, v) for k, v in distinct.items() if k not in self.memo]
        random.Random(SEED + sum(ord(c) for c in label)).shuffle(pending)

        def work(item):
            key, (adapter, text, phase, history) = item
            return key, runtime.solve(adapter, self.api, text, key=key, repeat=history,
                                      root=self.root, phase=phase, completed=self.complete)

        if self.complete:
            self.memo.update(work(item) for item in pending)
        else:
            # Rolling window prevents one long response from blocking unrelated
            # ready jobs. Stop admission on pause/error; always drain in-flight.
            index, finished, error = 0, 0, None
            active = set()
            with ThreadPoolExecutor(max_workers=4) as pool:
                while active or index < len(pending):
                    while index < len(pending) and len(active) < 4 and error is None:
                        try:
                            self._check_sources()
                            self._pause()
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
                            finished += 1
                            self._check_sources()
                            self._event(label, completed_trajectories=finished, total_trajectories=len(pending))
                        except Exception as exc:
                            error = error or exc
                if error is not None:
                    raise error
        self._check_sources()
        return [self.memo[self._solver_key(a, s, p, h)] for a, s, p, h in requests]

    def _project(self, solve):
        hashes = solve["request_hashes"]
        return evidence.project_development_feedback(solve,
            [read(self.root / "runtime/stages" / (h + ".json")) for h in hashes],
            api_receipts=[json.loads((self.root / "api/calls" / (h + ".json")).read_text()) for h in hashes],
            executions={i: read(self.root / "runtime/executions" / (i + ".json")) for i in solve["execution_ids"]})

    def _probe(self, adapter, solve, role, history, round_index):
        probe_adapter = tasks.probe_adapter(adapter)
        key = digest({"solve_hash": solve["record_hash"], "history": history, "round": round_index,
                      "probe_task_hash": digest(payload(probe_adapter))})
        if key not in self.probes:
            self._check_sources()
            self._pause()
            self.probes[key] = runtime.evaluate_probe(probe_adapter, solve["artifact"], root=self.root,
                                                      key=key, completed=self.complete)
        row = self.probes[key]
        if row["source_task_id"] != solve["task_id"] or row["source_task_hash"] != solve["identity"]["task_hash"]:
            raise ValueError("Probe is not bound to the actual source task")
        check_rows = row["evaluation"].get("case_results", []) if row["score"]["oracle_available"] else []
        cases = payload(probe_adapter)["public_cases"]
        return {"phase": "development", "probe": True, "role": role, "probe_hash": row["record_hash"],
            "source_task_id": row["source_task_id"], "source_solve_hash": solve["record_hash"],
            "artifact": deepcopy(solve["artifact"]), "score": deepcopy(row["score"]),
            "probe_definitions_not_execution_claims": deepcopy(cases),
            "case_obligations": deepcopy(row["case_obligations"]), "executed_checks": deepcopy(check_rows),
            "executed_details": deepcopy(row["evaluation"].get("private_diagnostics", []) +
                                          row["evaluation"].get("public_observations", []))}

    def _learn(self, history, round_index, arm, parent, adapters, base_rows, current_rows):
        public, observations, probes = [], [], []
        for adapter, base, current in zip(adapters, base_rows, current_rows):
            task = payload(adapter)
            view = public_task(adapter)
            view.update(id=task["id"], obligations=tasks.constraints_for(adapter))
            # These are explicitly definitions, not a claim that an unavailable
            # execution happened. No reference artifacts or final data included.
            view["development_check_definitions_not_execution_claims"] = deepcopy(
                task["public_cases"] + task.get("hidden_cases", task.get("private_cases", [])))
            public.append(view)
            for role, solve in (("no_skill", base), ("current", current)):
                observations.append({"role": role, "artifact": deepcopy(solve["artifact"]),
                                     "feedback": self._project(solve)})
                if arm == "constrained":
                    probes.append(self._probe(adapter, solve, role, history, round_index))
        system, user, evidence_hash, supports = learning.messages(parent, public, observations, probes, arm)
        key = f"h{history}-r{round_index}-{arm}"
        args = {"system": system, "user": user, "kind": "v14_skill_update", "key": key,
                "max_tokens": learning.TOKEN_CAP, "repeat": history}
        request = {**args, "model": self.api.model, "service": self.api.service}
        request_hash = digest(request)
        intent_path = self.root / "learning_intents" / (key + ".json")
        intent = {"version": VERSION, "request_hash": request_hash, "evidence_hash": evidence_hash,
                  "parent_state_hash": digest(parent), "probe_hashes": [p["probe_hash"] for p in probes]}
        call_path = self.root / "api/calls" / (request_hash + ".json")
        if call_path.exists():
            save(intent_path, intent, completed=True)
            receipt = json.loads(call_path.read_text())
        else:
            if self.complete or intent_path.exists():
                raise ValueError("Unresolved optimizer request; never resample")
            self._check_sources()
            self._pause()
            save(intent_path, intent)
            receipt = self.api.call(**args)
        if (receipt.get("request") != request or receipt.get("request_hash") != request_hash
                or not call_path.exists() or json.loads(call_path.read_text()) != receipt):
            raise ValueError("Optimizer receipt differs from its exact durable request")
        self._check_sources()
        parsed = learning.parse_update(receipt, parent, arm, supports)
        return save(self.root / "learning" / (key + ".json"), {"version": VERSION,
            "history": history, "round": round_index, "arm": arm, "request_hash": request_hash,
            "api_receipt_hash": digest(receipt), "parent_hash": learning.text_hash(parent["skill"]),
            "evidence_hash": evidence_hash, **parsed, "skill_hash": learning.text_hash(parsed["skill"]),
            "changed": parsed["skill"] != parent["skill"], "probe_hashes": intent["probe_hashes"],
            "final_feedback_used": False, "free_form_entailment_validated": False}, completed=self.complete)

    def _audit_closure(self, proposals):
        solver_requests = {h for row in self.memo.values() for h in row["request_hashes"]}
        learning_requests = {p["request_hash"] for p in proposals}
        actual = {p.stem for p in (self.root / "api/calls").glob("*.json")}
        if actual != solver_requests | learning_requests or solver_requests & learning_requests:
            raise ValueError("API ledger has orphan/missing solver or optimizer requests")
        execution_ids = {i for row in self.memo.values() for i in row["execution_ids"]}
        solves = {digest(row["identity"]) for row in self.memo.values()}
        probe_ids = {p["execution_id"] for p in self.probes.values()}
        probe_solves = {digest(p["identity"]) for p in self.probes.values()}
        for directory, expected in (("request_intents", solver_requests), ("stages", solver_requests),
                ("execution_intents", execution_ids), ("executions", execution_ids), ("solves", solves),
                ("probes/execution_intents", probe_ids), ("probes/executions", probe_ids), ("probes/solves", probe_solves)):
            if {p.stem for p in (self.root / "runtime" / directory).glob("*.json")} != expected:
                raise ValueError("Missing/orphan/unresolved runtime evidence: " + directory)
        keys = {f"h{p['history']}-r{p['round']}-{p['arm']}" for p in proposals}
        for directory in ("learning", "learning_intents"):
            if {p.stem for p in (self.root / directory).glob("*.json")} != keys:
                raise ValueError("Learning evidence does not close")
        return {"unique_solver_requests": len(solver_requests), "unique_optimizer_requests": len(learning_requests),
                "unique_executions": len(execution_ids), "unique_trajectories": len(solves),
                "extra_probe_native_evaluations": len(probe_ids), "all_intents_closed": True,
                "extra_requests_or_executions": False}

    def run(self):
        self.prepare()
        self.api = OfflineAPI(self.root / "api") if self.complete else None
        if not self.complete:
            self._pause()
            self.api = self.api_factory(self.repo, self.root / "api", max_calls=self.max_calls, workers=4)
        try:
            states = [{arm: learning.empty_state() for arm in learning.ARMS} for _ in range(self.histories)]
            proposals = []
            for r, adapters in enumerate(self.panel["train"]):
                for h in range(self.histories):
                    self._event("learning_round", history=h, round=r)
                    texts = ["", *(states[h][arm]["skill"] for arm in learning.ARMS)]
                    resolved = self._batch([(a, text, "development", h) for text in texts for a in adapters],
                                           f"development_h{h}_r{r}")
                    base = resolved[:len(adapters)]
                    current = {arm: resolved[(i+1)*len(adapters):(i+2)*len(adapters)]
                               for i, arm in enumerate(learning.ARMS)}
                    for arm in (learning.ARMS if (h+r) % 2 == 0 else learning.ARMS[::-1]):
                        proposal = self._learn(h, r, arm, states[h][arm], adapters, base, current[arm])
                        states[h][arm] = proposal["state"]
                        proposals.append(proposal)
                        self._event("skill_updated", history=h, round=r, arm=arm,
                                    valid=proposal["valid"], changed=proposal["changed"])
            self._check_sources()
            frozen = save(self.root / "final_frozen.json", {"version": VERSION,
                "protocol_hash": self.protocol["record_hash"], "states": states,
                "proposal_hashes": [p["record_hash"] for p in proposals],
                "third_domain_used_in_learning": False, "research_validator_active": False}, completed=self.complete)
            self._event("all_skills_frozen", frozen_hash=frozen["record_hash"])
            rows = []
            for h in range(self.histories):
                texts = {"no_skill": "", **{a: states[h][a]["skill"] for a in learning.ARMS}}
                positions = [(p, a) for p in POLICIES for a in self.panel["final"]]
                solved = self._batch([(a, texts[p], "final", h) for p, a in positions], f"frozen_final_h{h}")
                for result, (policy, _) in zip(solved, positions):
                    rows.append({k: deepcopy(result[k]) for k in (
                        "task_id", "domain", "cluster_id", "skill_hash", "request_hashes", "score")} |
                        {"history": h, "policy": policy, "solver_record_hash": result["record_hash"],
                         "chosen_stage": result["chosen_stage"], "rollback_reason": result["rollback_reason"]})
            grid = save(self.root / "final_rows.json", {"version": VERSION, "rows": rows,
                        "frozen_hash": frozen["record_hash"]}, completed=self.complete)
            if self.design == "formal":
                from .analysis import summarize
                expected = {payload(a)["id"]: {"domain": a.domain, "cluster_id": payload(a)["cluster_id"]}
                            for a in self.panel["final"]}
                summary = summarize(rows, expected, histories=self.histories, policies=POLICIES)
            else:
                summary = {"smoke_only": True, "positions": len(rows), "scientific_inference": False,
                    "success_by_policy": {p: sum(r["score"]["all_attempt_success"] for r in rows if r["policy"] == p) /
                        sum(r["policy"] == p for r in rows) for p in POLICIES}}
            ledger = closed_ledger(self.root, self.max_calls)
            closure = self._audit_closure(proposals)
            self._check_sources()
            result = save(self.root / "results.json", {"version": VERSION, "complete": True,
                "design": self.design, "protocol_hash": self.protocol["record_hash"], "frozen_hash": frozen["record_hash"],
                "final_grid_hash": grid["record_hash"], "summary": summary, "ledger": ledger,
                "evidence_closure": closure, "learning": {"proposals": len(proposals),
                    "valid": sum(p["valid"] for p in proposals), "text_changes": sum(p["changed"] for p in proposals),
                    "local_operations": sum(len(p["operations"]) for p in proposals),
                    "probe_native_evaluations": len(self.probes)}, "public_benchmark": False,
                "research_validator_evolution_measured": False}, completed=self.complete)
            self._event("finished", result_hash=result["record_hash"], calls=ledger["cached_logical_calls"])
            return result
        finally:
            if not self.complete and self.api is not None:
                self.api.close()
