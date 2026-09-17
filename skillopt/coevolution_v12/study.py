"""Bounded three-round, equal-data Skill-content experiment.

Final raw candidates are evaluated regardless of the selection diagnostic.
All identical task/text interventions are exact cached aliases across policies
and histories. This experiment makes no public-benchmark or safety claim.
"""

from __future__ import annotations

import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v8.feedback_study import payload, public_task
from skillopt.coevolution_v9.study import OfflineAPI, closed_ledger, stable_api
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import learning, runtime

VERSION = "v12-equal-data-cross-domain-refinement-v1"
SEED = 20260915
POLICIES = ("no_skill", "independent", "contrastive", "selected_independent", "selected_contrastive")


def read(path):
    return verify(json.loads(Path(path).read_text(encoding="utf-8")))


def save(path, value, *, completed=False):
    expected = seal(value)
    if Path(path).exists():
        if read(path) != expected:
            raise ValueError("Frozen study record differs")
    elif completed:
        raise ValueError("Completed study is missing evidence")
    else:
        write_immutable_json(Path(path), expected)
    return expected


def safe_root(repo, output):
    repo, raw = Path(repo).resolve(), Path(output).absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("Symlink experiment paths are forbidden")
    parent = repo / "outputs/coevolution_v12"
    if raw == parent or not raw.is_relative_to(parent):
        raise ValueError("Use a dedicated output beneath outputs/coevolution_v12")
    if raw.exists() and any(p.is_symlink() for p in raw.rglob("*")):
        raise ValueError("Symlink experiment entries are forbidden")
    return raw


def source_hashes(repo):
    paths = set()
    # Freeze all transitive local research/runtime packages, not secret config.
    for name in ("coevolution", "coevolution_v3", "coevolution_v4", "coevolution_v5", "coevolution_v6",
                 "coevolution_v7", "coevolution_v8", "coevolution_v9", "coevolution_v12", "validator_pilot"):
        paths.update((repo / "skillopt" / name).glob("*.py"))
    paths.update(repo / p for p in ("scripts/coevolution_v12.py", "docs/coevolution-v12-protocol.md",
                                   "skillopt/coevolution_evidence_view.py"))
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


class PauseRequested(RuntimeError):
    pass


class Study:
    def __init__(self, repo, root, *, design="formal", panel=None, api_factory=stable_api):
        if design not in {"smoke", "formal"}:
            raise ValueError("Explicit smoke/formal design required")
        self.repo = Path(repo).resolve()
        self.root = safe_root(self.repo, root)
        self.design = design
        self.histories, self.rounds = (1, 1) if design == "smoke" else (3, 3)
        self.max_calls = 96 if design == "smoke" else 1536
        self.api_factory, self.panel = api_factory, panel
        self.production_panel = panel is None
        self.complete = (self.root / "results.json").exists()
        self.event_number = len(list((self.root / "events").glob("*.json")))
        self.api = None
        self.memo = {}

    def _event(self, stage, **details):
        if self.complete:
            return
        self.event_number += 1
        event = {"version": VERSION, "sequence": self.event_number,
                 "time_utc": datetime.now(timezone.utc).isoformat(), "stage": stage, **details}
        save(self.root / "events" / f"{self.event_number:06d}.json", event)
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def _pause(self):
        if not self.complete and (self.root / "PAUSE_REQUESTED").exists():
            self._event("paused_after_closed_chunk")
            raise PauseRequested("Paused after draining the current solver chunk")

    def _check_sources(self):
        if source_hashes(self.repo) != self.protocol["source_hashes"]:
            raise ValueError("Frozen source drift: stop without changing completed evidence")

    def _audit_closure(self, proposals):
        solver_requests = {h for row in self.memo.values() for h in row["request_hashes"]}
        learning_requests = {row["request_hash"] for row in proposals}
        expected = solver_requests | learning_requests
        actual = {p.stem for p in (self.root / "api/calls").glob("*.json")}
        if actual != expected or solver_requests & learning_requests:
            raise ValueError("API ledger has orphan/missing solver or optimizer requests")
        execution_ids = {h for row in self.memo.values() for h in row["execution_ids"]}
        solve_ids = {digest(row["identity"]) for row in self.memo.values()}
        for directory, identifiers in (("request_intents", solver_requests), ("stages", solver_requests),
                ("execution_intents", execution_ids), ("executions", execution_ids), ("solves", solve_ids)):
            found = {p.stem for p in (self.root / "runtime" / directory).glob("*.json")}
            if found != identifiers:
                raise ValueError("Runtime evidence contains orphan/missing or unresolved " + directory)
        keys = {f"h{p['history']}-r{p['round']}-{p['arm']}" for p in proposals}
        for directory in ("learning", "learning_intents", "selection"):
            if {p.stem for p in (self.root / directory).glob("*.json")} != keys:
                raise ValueError("Learning/selection evidence does not close")
        return {"unique_solver_requests": len(solver_requests), "unique_optimizer_requests": len(learning_requests),
                "unique_executions": len(execution_ids), "unique_trajectories": len(solve_ids),
                "all_intents_closed": True, "extra_requests_or_executions": False}

    def prepare(self):
        if self.panel is None:
            from .tasks import build_panel
            self.panel = build_panel(smoke=self.design == "smoke")
        if self.design == "smoke":
            self.panel = {"train": [self.panel["train"][0][:2]],
                          "selection": [self.panel["selection"][0][:2]],
                          "final": self.panel["final"][:2]}
        if len(self.panel["train"]) != self.rounds or len(self.panel["selection"]) != self.rounds:
            raise ValueError("Panel does not have the frozen number of rounds")
        groups = {key: [payload(a) for group in value for a in group] if key != "final"
                  else [payload(a) for a in value] for key, value in self.panel.items()}
        ids = [t["id"] for group in groups.values() for t in group]
        if len(ids) != len(set(ids)):
            raise ValueError("Train/selection/final task IDs overlap")
        if any(t.get("domain", "coding") == "rule_reasoning" for k in ("train", "selection") for t in groups[k]):
            raise ValueError("Held-out domain cannot enter development or selection")
        if self.design == "formal":
            if len(groups["train"]) != 12 or len(groups["selection"]) != 12 or len(groups["final"]) != 36:
                raise ValueError("Formal task counts differ from the preregistration")
            if ({t["cluster_id"] for t in groups["final"]} &
                    {t["cluster_id"] for k in ("train", "selection") for t in groups[k]}):
                raise ValueError("Final structural families overlap development")
        snapshot = {"version": VERSION, "groups": groups,
                    "reference_artifacts_never_model_inputs": True,
                    "selection_and_final_hidden_data_never_model_inputs": True,
                    "development_executed_checks_may_reach_updater": True}
        registered = save(self.root / "private_panel.json", snapshot, completed=self.complete)
        frozen_sources = source_hashes(self.repo)
        preflight_hash = None
        if self.production_panel:
            from .tasks import self_check
            check_path = self.root / "task_preflight.json"
            if check_path.exists():
                checked = read(check_path)
            elif self.complete:
                raise ValueError("Completed production study is missing task calibration")
            else:
                checked = save(check_path, self_check(self.panel, coding=True))
            expected = {t["id"]: digest(t) for group in groups.values() for t in group}
            observed = {r["task_id"]: r["task_hash"] for r in checked["records"]}
            if (not checked.get("all_checked") or not checked.get("coding_checked")
                    or checked.get("model_api_calls") != 0 or expected != observed
                    or len(checked["records"]) != len(expected) or checked.get("checked_tasks") != len(expected)):
                raise ValueError("Task calibration does not match the frozen production panel")
            for row in checked["records"]:
                controls = row["controls"]
                if (not controls["reference"]["passed"] or not controls["reference"]["available"]
                        or any(controls[k]["passed"] for k in ("starter", "semantic_mutant", "preservation_mutant"))
                        or any(not controls[k]["available"] for k in ("starter", "semantic_mutant"))):
                    raise ValueError("Task calibration controls failed")
            preflight_hash = checked["record_hash"]
        if source_hashes(self.repo) != frozen_sources:
            raise ValueError("Source drift during task calibration")
        protocol = {"version": VERSION, "design": self.design, "histories": self.histories,
            "rounds": self.rounds, "max_calls": self.max_calls, "seed": SEED, "policies": list(POLICIES),
            "learning_arms": list(learning.ARMS), "panel_hash": registered["record_hash"],
            "source_hashes": frozen_sources, "model": "glm-5.3", "workers": 4,
            "task_preflight_hash": preflight_hash, "injected_test_panel": not self.production_panel,
            "http_spacing_seconds": 10, "optimizer_token_cap": learning.TOKEN_CAP,
            "solver_token_cap": runtime.TOKENS, "public_benchmark": False,
            "native_skillopt_baseline": False, "research_validator_active": False,
            "final_feedback_allowed": False, "third_domain_development_feedback": False,
            "all_raw_final_candidates_retained": True, "selected_is_diagnostic_not_scope_approval": True}
        self.protocol = save(self.root / "protocol.json", protocol, completed=self.complete)
        return self.protocol

    def _solver_key(self, adapter, text, phase):
        return digest({"task": payload(adapter)["id"], "text": learning.text_hash(text), "phase": phase})

    def _batch(self, requests, label):
        """Deduplicate before parallelism; one completed trajectory per identity."""
        distinct = {}
        for adapter, text, phase in requests:
            key = self._solver_key(adapter, text, phase)
            distinct.setdefault(key, (adapter, text, phase))
        pending = [(k, v) for k, v in distinct.items() if k not in self.memo]
        random.Random(SEED + sum(ord(c) for c in label)).shuffle(pending)
        for offset in range(0, len(pending), 4):
            self._check_sources()
            self._pause()
            chunk = pending[offset:offset + 4]

            def work(item):
                key, (adapter, text, phase) = item
                row = runtime.solve(adapter, self.api, text, key=key, repeat=0,
                                    root=self.root, phase=phase, completed=self.complete)
                return key, row

            if self.complete:
                resolved = [work(item) for item in chunk]
            else:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    resolved = list(pool.map(work, chunk))
            self.memo.update(resolved)
            self._check_sources()
            self._event(label, completed_trajectories=min(offset + 4, len(pending)),
                        total_trajectories=len(pending))
        return [self.memo[self._solver_key(a, s, p)] for a, s, p in requests]

    def _learn(self, history, round_index, arm, parent, tasks, base_rows, current_rows):
        self._check_sources()
        public = []
        for adapter, base, current in zip(tasks, base_rows, current_rows):
            view = public_task(adapter)
            view["id"] = payload(adapter)["id"]
            # Native execution receipts contain actual values but not the input
            # fixture or expected value. Bind up to eight executed developer
            # checks; the two editing arms use this same projection function.
            if adapter.domain != "coding":
                cases = payload(adapter)["public_cases"] + payload(adapter)["hidden_cases"]
                failed = {r["id"] for row in (base, current) for r in row["private_evaluation"].get("case_results", [])
                          if r["passed"] is False}
                ordered = sorted(enumerate(cases), key=lambda x: (x[1]["id"] not in failed, x[0]))
                view["development_executed_test_definitions"] = [deepcopy(c) for _, c in ordered[:8]]
            public.append(view)
        system, user, evidence_hash = learning.messages(parent, public, list(zip(base_rows, current_rows)), arm)
        key = f"h{history}-r{round_index}-{arm}"
        args = {"system": system, "user": user, "kind": "v12_skill_update", "key": key,
                "max_tokens": learning.TOKEN_CAP, "repeat": history}
        request = {**args, "model": self.api.model, "service": self.api.service}
        request_hash = digest(request)
        path = self.root / "learning" / (key + ".json")
        intent_path = self.root / "learning_intents" / (key + ".json")
        intent = {"version": VERSION, "request_hash": request_hash, "evidence_hash": evidence_hash,
                  "parent_hash": learning.text_hash(parent)}
        call_path = self.root / "api/calls" / (request_hash + ".json")
        if call_path.exists():
            save(intent_path, intent, completed=True)
            receipt = json.loads(call_path.read_text())
        else:
            if self.complete or intent_path.exists():
                raise ValueError("Unresolved optimizer request; do not resample")
            self._pause()
            save(intent_path, intent)
            receipt = self.api.call(**args)
        if receipt.get("request") != request or receipt.get("request_hash") != request_hash:
            raise ValueError("Optimizer receipt differs from expected request")
        if not call_path.exists() or json.loads(call_path.read_text()) != receipt:
            raise ValueError("Optimizer did not return its exact durable API receipt")
        self._check_sources()
        parsed = learning.parse_skill(receipt, parent)
        result = {"version": VERSION, "history": history, "round": round_index, "arm": arm,
            "request_hash": request_hash, "api_receipt_hash": digest(receipt), "parent_hash": learning.text_hash(parent),
            "evidence_hash": evidence_hash, **parsed, "skill_hash": learning.text_hash(parsed["skill"]),
            "changed": parsed["skill"] != parent, "selection_feedback_used": False, "final_feedback_used": False}
        return save(path, result, completed=self.complete)

    def run(self):
        self.prepare()
        if self.complete:
            self.api = OfflineAPI(self.root / "api")
        else:
            self._pause()
            self.api = self.api_factory(self.repo, self.root / "api", max_calls=self.max_calls, workers=4)
        try:
            drafts = [{a: "" for a in learning.ARMS} for _ in range(self.histories)]
            selected = deepcopy(drafts)
            proposals, decisions = [], []
            for r in range(self.rounds):
                train, selection = self.panel["train"][r], self.panel["selection"][r]
                for h in range(self.histories):
                    self._event("learning_round", history=h, round=r)
                    base = self._batch([(a, "", "development") for a in train], f"train_base_r{r}")
                    # Alternate update order across histories/rounds. Neither
                    # arm can consume the other's candidate or selection score.
                    for arm in (learning.ARMS if (h + r) % 2 == 0 else learning.ARMS[::-1]):
                        parent = drafts[h][arm]
                        current = self._batch([(a, parent, "development") for a in train], f"train_{h}_{r}_{arm}")
                        proposal = self._learn(h, r, arm, parent, train, base, current)
                        proposals.append(proposal)
                        drafts[h][arm] = proposal["skill"]
                        old, new = selected[h][arm], proposal["skill"]
                        scored = self._batch([(a, text, "selection") for text in (old, new) for a in selection],
                                             f"selection_{h}_{r}_{arm}")
                        decision = learning.choose_selected(old, new, scored[:len(selection)], scored[len(selection):])
                        selected[h][arm] = decision["skill"]
                        decisions.append(save(self.root / "selection" / f"h{h}-r{r}-{arm}.json",
                            {"version": VERSION, "history": h, "round": r, "arm": arm, **decision,
                             "parent_hash": learning.text_hash(old), "candidate_hash": learning.text_hash(new),
                             "selected_hash": learning.text_hash(decision["skill"]),
                             "solver_records": [row["record_hash"] for row in scored]}, completed=self.complete))
            self._check_sources()
            frozen = save(self.root / "final_frozen.json", {"version": VERSION,
                "protocol_hash": self.protocol["record_hash"], "drafts": drafts, "selected": selected,
                "proposal_hashes": [p["record_hash"] for p in proposals],
                "selection_hashes": [d["record_hash"] for d in decisions],
                "third_domain_used_in_learning": False, "research_validator_active": False}, completed=self.complete)
            self._event("all_skills_frozen", frozen_hash=frozen["record_hash"])
            requests, positions = [], []
            for h in range(self.histories):
                texts = {"no_skill": "", **drafts[h], **{"selected_" + a: selected[h][a] for a in learning.ARMS}}
                for policy in POLICIES:
                    for adapter in self.panel["final"]:
                        requests.append((adapter, texts[policy], "final"))
                        positions.append((h, policy))
            results = self._batch(requests, "frozen_final")
            rows = []
            for result, (history, policy) in zip(results, positions):
                rows.append({key: deepcopy(result[key]) for key in (
                    "task_id", "domain", "cluster_id", "skill_hash", "request_hashes", "score")} |
                    {"history": history, "policy": policy, "solver_record_hash": result["record_hash"]})
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
            final = save(self.root / "results.json", {"version": VERSION, "complete": True,
                "design": self.design, "protocol_hash": self.protocol["record_hash"],
                "frozen_hash": frozen["record_hash"], "final_grid_hash": grid["record_hash"],
                "summary": summary, "ledger": ledger, "evidence_closure": closure,
                "learning": {"proposals": len(proposals), "valid": sum(p["valid"] for p in proposals),
                    "text_changes": sum(p["changed"] for p in proposals),
                    "selection_acceptances": sum(d["accept"] for d in decisions)},
                "public_benchmark": False, "research_validator_evolution_measured": False}, completed=self.complete)
            self._event("finished", result_hash=final["record_hash"], calls=ledger["cached_logical_calls"])
            return final
        finally:
            if not self.complete and self.api is not None:
                self.api.close()
