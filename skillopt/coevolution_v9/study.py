"""Frozen one-update SearchQA Skill learning and paired acceptance-gate study.

Native SkillOpt creates ONE candidate per training history. The two policies
choose from the same candidate/parent; this isolates local acceptance, not a
new two-optimizer algorithm or cross-domain efficacy. Completed replay is offline.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v7 import transport
from skillopt.coevolution_v7.transport import PacingPolicy, make_budgeted_api
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import analysis, data, learning

VERSION = "v9-native-searchqa-one-update-gate-study-v1"
PACING = PacingPolicy(min_interval_seconds=10.0, cooldown_seconds=30.0)
DESIGNS = {
    "smoke": {"histories": 1, "train": 4, "confirmation": 8, "final": 4, "seed": 202609131},
    "source": {"histories": 3, "train": 32, "confirmation": 64, "final": 128, "seed": 202609132},
}
SOLVER_TOKENS = 4096


def _read(path):
    return verify(json.loads(Path(path).read_text(encoding="utf-8")))


def _save(path, value, *, completed=False):
    row = seal(value)
    if Path(path).exists():
        if _read(path) != row:
            raise ValueError("Immutable study evidence changed: " + Path(path).name)
    elif completed:
        raise ValueError("Completed run missing immutable evidence: " + Path(path).name)
    else:
        write_immutable_json(path, row)
    return row


def _safe_run(repo, root):
    path = Path(root).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("Symlink experiment paths are not supported")
    path = path.resolve()
    parent = repo / "outputs/coevolution_v9"
    if path == parent or not path.is_relative_to(parent):
        raise ValueError("Use an isolated run beneath outputs/coevolution_v9")
    return path


def source_hashes(repo):
    paths = []
    for relative in ("skillopt/engine", "skillopt/envs/searchqa", "skillopt/gradient",
                     "skillopt/optimizer", "skillopt/evaluation", "skillopt/model", "skillopt/utils",
                     "skillopt/prompts"):
        paths.extend(p for p in (repo / relative).rglob("*") if p.is_file() and p.suffix in {".py", ".md"})
    paths.extend(repo / p for p in (
        "skillopt/coevolution_v9/__init__.py", "skillopt/coevolution_v9/data.py",
        "skillopt/coevolution_v9/learning.py", "skillopt/coevolution_v9/analysis.py",
        "skillopt/coevolution_v9/study.py", "scripts/coevolution_v9.py",
        "docs/coevolution-v9-source-protocol.md", "skillopt/coevolution_v5/core.py",
        "skillopt/coevolution_v7/transport.py", "skillopt/coevolution/budget.py",
        "skillopt/validator_pilot/api.py", "skillopt/scope_evolution_v2/source_data.py",
        "skillopt/config.py", "skillopt/types.py", "skillopt/datasets/base.py",
        "skillopt/envs/base.py", "skillopt/__init__.py", "pyproject.toml",
    ))
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def stable_api(repo, root, *, max_calls, workers):
    return make_budgeted_api(repo, root, max_calls=max_calls, workers=workers, policy=PACING)


def audit_pacing(root, calls, service):
    """Read V7's entire attempt ledger without clients, credentials, or writes."""
    directory = Path(root) / "api/pacing"
    expected = seal({"version": transport.VERSION, "policy": vars(PACING), "service_hash": digest(service),
        "workers": 4, "unit": "http_client_attempt_admission_not_logical_call", "cooldown_statuses": [429],
        "retry_policy": "unchanged_cached_api_max_three_transport_attempts", "semantic_resampling": False,
        "one_process_per_run": True,
        "resume_clock": "persisted_wall_deadline_converted_to_new_monotonic_deadline",
        "wall_clock_assumption": "clock_not_moved_forward_across_process_restart",
        "inflight_attempts_cannot_be_retracted_by_a_later_429": True})
    try:
        if _read(directory / "protocol.json") != expected:
            raise ValueError("Pacing protocol differs from the frozen V9 policy")
        # These existing V7 methods only read their supplied view. Deliberately
        # do not invoke either constructor: constructors acquire live clients
        # and publish pacing metadata, which completed replay must never do.
        pacer = SimpleNamespace(root=directory, policy=PACING, protocol_hash=expected["record_hash"])
        admissions, outcomes, cooldowns = transport._Pacer._existing(pacer)
        if set(admissions) != set(outcomes):
            raise ValueError("Unresolved HTTP pacing admission")
        references = set()
        view = SimpleNamespace(_pacer=pacer)
        for identifier, call in calls.items():
            transport.PacedCachedAPI._verify_cached(view, call)
            request = call["request"]
            payload = {"model": request["model"], "messages": [
                {"role": "system", "content": request["system"]},
                {"role": "user", "content": request["user"]}],
                "temperature": service["temperature"], "max_tokens": request["max_tokens"]}
            if service.get("stream"):
                payload.update(stream=True, stream_options=service["stream_options"])
            if service.get("reasoning_effort") is not None:
                payload["reasoning_effort"] = service["reasoning_effort"]
            endpoint = "https://" + service["host"] + service["path"]
            wire_hash = digest({"method": "POST", "endpoint": endpoint, "body": payload})
            for attempt_index, reference in enumerate(call["pacing"]["attempts"], 1):
                sequence = reference["sequence"]
                admission = admissions[sequence]
                if (sequence in references or admission["request_hash"] != identifier
                        or admission["kind"] != request["kind"] or admission["attempt"] != attempt_index
                        or admission["http_request_hash"] != wire_hash):
                    raise ValueError("HTTP admission is duplicated or differs from the intended wire payload")
                references.add(sequence)
        if references != set(admissions):
            raise ValueError("Unexpected HTTP pacing admission outside the actual call grid")
        previous = None
        for sequence in sorted(admissions):
            current = admissions[sequence]
            finished = outcomes[sequence]["finished_wall"]
            if (type(finished) not in (int, float) or not math.isfinite(finished)
                    or finished < current["admitted_wall"] - 1e-6):
                raise ValueError("HTTP attempt has an invalid completion clock")
            if previous is not None:
                clock = "admitted_monotonic" if previous["process_epoch"] == current["process_epoch"] else "admitted_wall"
                if current[clock] - previous[clock] < PACING.min_interval_seconds - 1e-6:
                    raise ValueError("HTTP admission violates the frozen minimum interval")
            for cooldown in cooldowns.values():
                # Earlier admitted in-flight requests cannot be withdrawn by
                # a later 429. Only admissions after observing it are checked.
                if (cooldown["observed_wall"] < current["admitted_wall"] - 1e-6
                        and current["admitted_wall"] < cooldown["cooldown_until_wall"] - 1e-6):
                    raise ValueError("HTTP admission violates an already observed shared cooldown")
            previous = current
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Missing or malformed immutable HTTP pacing evidence") from exc
    return {"protocol_hash": expected["record_hash"], "http_attempt_admissions": len(admissions),
            "completed_attempt_receipts": len(outcomes), "cooldown_events": len(cooldowns),
            "unresolved_attempts": [], "wire_payload_hashes_verified": True,
            "local_admission_times_not_server_arrival_or_billing": True}


def verify_optimizer_receipts(root, histories):
    """Bind every learning receipt copy to its exact actual transport receipt."""
    root = Path(root)
    expected, seen = set(), set()
    for history in histories:
        planned = history["optimizer_requests"]
        if not isinstance(planned, list) or len(set(planned)) != len(planned):
            raise ValueError("Duplicate optimizer requests in a frozen history")
        expected.update(planned)
        copied = set()
        directory = root / "learning" / f"history_{history['history']}" / "optimizer/calls"
        for path in directory.glob("*.json"):
            record = _read(path)
            receipt = record["receipt"]
            identifier = receipt["request_hash"]
            if identifier in copied or identifier in seen:
                raise ValueError("Optimizer receipts cannot alias distinct histories or intents")
            try:
                actual = json.loads((root / "api/calls" / (identifier + ".json")).read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("Missing actual optimizer API receipt") from exc
            if actual != receipt or digest(actual["request"]) != identifier:
                raise ValueError("Learning optimizer receipt differs from its actual API record")
            copied.add(identifier)
            seen.add(identifier)
        if copied != set(planned):
            raise ValueError("Learning optimizer receipt grid differs from the frozen history")
    if seen != expected:
        raise ValueError("Optimizer receipt grid is incomplete")
    return {"verified_unique_optimizer_receipts": len(seen), "exact_actual_receipt_binding": True}


def closed_ledger(root, maximum):
    """Check every actual request/reservation, including unsuccessful attempts."""
    budget = json.loads((root / "api/budget_protocol.json").read_text())
    if budget["max_logical_calls"] != maximum or budget["model"] != "glm-5.3" or budget["workers"] != 4:
        raise ValueError("Saved transport budget differs from the frozen design")
    service = json.loads((root / "api/service.json").read_text())
    if digest(service) != budget["service_sha256"]:
        raise ValueError("Saved service configuration changed")
    calls = {}
    for path in (root / "api/calls").glob("*.json"):
        row = json.loads(path.read_text())
        request = row["request"]
        if (path.stem != row["request_hash"] or digest(request) != path.stem
                or request["service"] != service or request["model"] != budget["model"]
                or type(row["ok"]) is not bool or type(row["http_attempt_count"]) is not int
                or not 1 <= row["http_attempt_count"] <= 3):
            raise ValueError("Invalid real API receipt identity")
        calls[path.stem] = row
    reservations = {p.stem: json.loads(p.read_text()) for p in (root / "api/budget_reservations").glob("*.json")}
    if set(calls) != set(reservations) or len(calls) > maximum:
        raise ValueError("Unresolved or excessive model request budget")
    for h, call in calls.items():
        if reservations[h] != {"request_hash": h, "kind": call["request"]["kind"]}:
            raise ValueError("Wrong logical reservation binding")
    rows = list(calls.values())
    pacing = audit_pacing(root, calls, service)
    return {"max_logical_calls": maximum, "logical_requests_reserved": len(rows),
        "cached_logical_calls": len(rows), "successful_calls": sum(r["ok"] for r in rows),
        "terminal_errors": sum(not r["ok"] for r in rows), "unresolved_reservations": [],
        "http_attempts_from_cached_records": sum(r["http_attempt_count"] for r in rows),
        "max_planned_http_attempts": maximum * 3,
        "by_kind": dict(sorted(Counter(r["request"]["kind"] for r in rows).items())),
        **{k: sum(r.get("usage", {}).get(k, 0) or 0 for r in rows)
           for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "missing_usage_calls": sum(not r.get("usage") for r in rows), "pacing": pacing,
        "usage_not_invoice": True, "unreturned_or_interrupted_attempt_usage_unknown": True}


class OfflineAPI:
    offline = True

    def __init__(self, root):
        self.root = Path(root)
        self.model = "glm-5.3"
        self.service = json.loads((self.root / "service.json").read_text())

    def call(self, system, user, kind, key, max_tokens=4096, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        h = digest(request)
        path = self.root / "calls" / (h + ".json")
        if not path.is_file():
            raise ValueError("Completed run missing a real call; offline replay cannot repair it")
        row = json.loads(path.read_text())
        if row["request"] != request or row["request_hash"] != h:
            raise ValueError("Offline receipt request differs")
        return row

    @staticmethod
    def parallel(jobs, fn, label):
        return [fn(job) for job in jobs]


class Study:
    def __init__(self, repo, root, *, design="source", cache_paths=None):
        self.repo = Path(repo).resolve()
        self.root = _safe_run(self.repo, root)
        if design not in DESIGNS:
            raise ValueError("Choose a predeclared smoke or source design")
        self.design_name, self.design = design, deepcopy(DESIGNS[design])
        self.cache_paths = cache_paths
        self.completed = (self.root / "results.json").exists()
        self.histories = list(range(self.design["histories"]))
        self.counts = {"final": self.design["final"]}
        for h in self.histories:
            self.counts[f"train_h{h}_r0"] = self.design["train"]
            self.counts[f"confirmation_h{h}_r0"] = self.design["confirmation"]
        self.maximum = (self.design["histories"] * (self.design["train"] + 16 + 3 * self.design["confirmation"])
                        + (self.design["histories"] + 2) * self.design["final"])
        self.initial = (self.repo / "skillopt/envs/searchqa/skills/initial.md").read_text()
        self.used_solves = set()

    def prepare(self):
        if self.completed and any(not (self.root / name).is_file() for name in
                                  ("protocol.json", "data_manifest.json", "exposure_inventory.json", "final_freeze.json")):
            raise ValueError("Completed run metadata is missing; never reconstruct it")
        manifest = data.prepare_manifest(self.repo, self.root, self.counts, self.design["seed"], self.cache_paths)
        protocol = {"version": VERSION, "design_name": self.design_name, "design": self.design,
            "counts": self.counts, "data_manifest_hash": manifest["record_hash"],
            "source_hashes": source_hashes(self.repo), "max_calls": self.maximum,
            "model": "glm-5.3", "workers": 4, "pacing_policy": vars(PACING),
            "solver_max_tokens": SOLVER_TOKENS, "optimizer_max_tokens": learning.TOKEN_CAP,
            "max_optimizer_calls_per_history": 16, "initial_skill_hash": learning.text_hash(self.initial),
            "reflection_minibatch": 8, "edit_budget": 4, "meta": False, "slow": False,
            "one_native_candidate_shared_between_gates": True, "same_text_same_task_exact_request_reuse": True,
            "confirmation_never_optimizer_feedback": True, "final_requires_deployment_freeze": True,
            "ours_gate": {"alpha": 0.10, "minimum_clusters": 64, "candidate_em_not_below_no_skill": True},
            "histories_are_training_draws_not_provider_seeds": True,
            "scope": "searchqa_source_local_only", "cross_domain_effect_measured": False,
            "native_skillopt_controlled_adaptation_not_default_paper_reproduction": True}
        self.manifest = manifest
        self.protocol = _save(self.root / "protocol.json", protocol, completed=self.completed)
        return self.protocol

    def _tasks(self, split, *, authorization=None):
        rows = data.materialize_split(self.repo, self.manifest, split, final_authorization=authorization)
        expected = self._expected(split)
        if len(rows) != len(expected) or {r["key"] for r in rows} != set(expected):
            raise ValueError("Materialized task grid differs from reservation")
        return [{**row, "split": split} for row in rows]

    def _expected(self, split):
        return {r["id"]: {"cluster_id": r["question_sha256"]} for r in self.manifest["splits"][split]}

    def _solve(self, api, item, skill, split):
        system, user = learning.native_qa_messages(skill, data.public_task(item))
        hskill = learning.text_hash(skill)
        key = digest({"protocol_hash": self.protocol["record_hash"], "split": split,
                      "task_id": item["key"], "skill_hash": hskill})
        receipt = api.call(system, user, "v9_searchqa_solve", key, max_tokens=SOLVER_TOKENS, repeat=0)
        request = {"model": api.model, "service": api.service, "system": system, "user": user,
                   "kind": "v9_searchqa_solve", "key": key, "max_tokens": SOLVER_TOKENS, "repeat": 0}
        h = digest(request)
        if receipt["request"] != request or receipt["request_hash"] != h or type(receipt["ok"]) is not bool:
            raise ValueError("Solver receipt is not the intended native request")
        expected_cluster = self._expected(split)[item["key"]]["cluster_id"]
        if data.question_fingerprint(item["question"]) != expected_cluster:
            raise ValueError("Solver question differs from its reserved identity")
        scores = learning.score_qa(receipt["response"], item) if receipt["ok"] else None
        row = {"task_id": item["key"], "cluster_id": expected_cluster, "split": split,
            "skill_hash": hskill, "request_hash": h, "api_receipt_hash": digest(receipt),
            "response_hash": digest(receipt.get("response", "")), "api_ok": receipt["ok"],
            "em": scores["em"] if scores else None, "f1": scores["f1"] if scores else None,
            "sub_em": scores["sub_em"] if scores else None, "error_type": receipt.get("error_type"),
            "native_evaluator": "skillopt.envs.searchqa.evaluator.evaluate",
            "gold_hash": digest(item["answers"]), "optimizer_feedback_allowed": split.startswith("train_")}
        saved = _save(self.root / "solves" / (h + ".json"), row, completed=self.completed)
        self.used_solves.add(h)
        return saved, receipt

    def _grid(self, api, tasks, skills, split):
        unique = {learning.text_hash(text): text for text in skills}
        jobs = [(item, h) for item in tasks for h in sorted(unique)]
        random.Random(self.design["seed"] + int(digest(split)[:8], 16)).shuffle(jobs)
        observed = api.parallel(jobs, lambda pair: ((pair[0]["key"], pair[1]),
            self._solve(api, pair[0], unique[pair[1]], split)), "v9-" + split)
        indexed = dict(observed)
        expected = {(row["key"], h) for row in tasks for h in unique}
        if len(observed) != len(expected) or set(indexed) != expected:
            raise ValueError("Scheduler omitted or duplicated a solver position")
        return indexed

    @staticmethod
    def _analysis_row(solve, history, policy):
        return {k: solve[k] for k in ("task_id", "cluster_id", "skill_hash", "request_hash", "api_ok", "em", "f1")} | {
            "history": history, "policy": policy}

    def _history(self, api, history):
        train_split = f"train_h{history}_r0"
        train = self._tasks(train_split)
        print(json.dumps({"stage": "training", "history": history, "tasks": len(train)}), flush=True)
        grid = self._grid(api, train, [self.initial], train_split)
        hparent = learning.text_hash(self.initial)
        train_rows = [{"item": item, "receipt": grid[item["key"], hparent][1]} for item in train]
        proposal_path = self.root / "learning" / f"history_{history}"
        if self.completed and not (proposal_path / "result.json").is_file():
            raise ValueError("Completed history missing its native proposal")
        print(json.dumps({"stage": "native_skillopt_update", "history": history}), flush=True)
        proposal = learning.propose_candidate(api, self.initial, train_rows, proposal_path,
            round_key=digest({"protocol_hash": self.protocol["record_hash"], "history": history, "round": 0}))
        candidate = proposal["candidate_text"]
        if proposal["parent_text"] != self.initial or proposal["candidate_hash"] != learning.text_hash(candidate):
            raise ValueError("Candidate does not descend from the frozen initial Skill")
        split = f"confirmation_h{history}_r0"
        tasks = self._tasks(split)
        print(json.dumps({"stage": "source_confirmation", "history": history, "tasks": len(tasks),
                          "unique_skills": len({"", self.initial, candidate})}), flush=True)
        confirmation = self._grid(api, tasks, ["", self.initial, candidate], split)
        def rows(text, policy):
            return [self._analysis_row(confirmation[item["key"], learning.text_hash(text)][0], history, policy)
                    for item in tasks]
        gate = analysis.local_gate(rows(self.initial, "parent"), rows(candidate, "candidate"), rows("", "base"),
                                   expected_tasks=self._expected(split))
        selected = {"skillopt": candidate if gate["standard_accept"] else self.initial,
                    "ours": candidate if gate["ours_accept"] else self.initial}
        row = {"history": history, "round": 0, "proposal_hash": proposal["record_hash"],
            "parent_hash": hparent, "candidate_hash": learning.text_hash(candidate), "gate": gate,
            "skills": {policy: {"text": text, "skill_hash": learning.text_hash(text)} for policy, text in selected.items()},
            "training_requests": sorted(grid[k][0]["request_hash"] for k in grid),
            "confirmation_requests": sorted(confirmation[k][0]["request_hash"] for k in confirmation),
            "optimizer_requests": proposal["optimizer_request_hashes"],
            "candidate_changed": candidate != self.initial, "source_local_only": True,
            "confirmation_labels_not_optimizer_feedback": True}
        return _save(self.root / "histories" / f"{history}.json", row, completed=self.completed)

    def _execute(self, api):
        histories = [self._history(api, h) for h in self.histories]
        if source_hashes(self.repo) != self.protocol["source_hashes"]:
            raise ValueError("Code changed during learning; no final access")
        deployment = {str(row["history"]): {"no_skill": {"text": "", "skill_hash": learning.text_hash("")},
            "initial": {"text": self.initial, "skill_hash": learning.text_hash(self.initial)}, **row["skills"]} for row in histories}
        frozen = _save(self.root / "final_freeze.json", {"phase": "final_frozen",
            "protocol_hash": self.protocol["record_hash"], "data_manifest_hash": self.manifest["record_hash"],
            "policies_hash": digest(deployment), "source_hashes": self.protocol["source_hashes"],
            "deployment": deployment, "history_hashes": [r["record_hash"] for r in histories],
            "final_feedback_forbidden": True}, completed=self.completed)
        final = self._tasks("final", authorization=frozen)
        skill_texts = [s["text"] for choices in deployment.values() for s in choices.values()]
        print(json.dumps({"stage": "frozen_final", "tasks": len(final),
                          "unique_skills": len(set(skill_texts)), "no_further_learning": True}), flush=True)
        grid = self._grid(api, final, skill_texts, "final")
        rows = [self._analysis_row(grid[item["key"], deployment[str(h)][policy]["skill_hash"]][0], h, policy)
                for item in final for h in self.histories for policy in analysis.POLICIES]
        aliases = Counter(r["request_hash"] for r in rows)
        for row in rows:
            row.update(shared_request=aliases[row["request_hash"]] > 1,
                       alias_of_request_hash=row["request_hash"] if aliases[row["request_hash"]] > 1 else None)
        _save(self.root / "final_rows.json", {"rows": rows, "final_freeze_hash": frozen["record_hash"],
              "never_optimizer_feedback": True}, completed=self.completed)
        summary = analysis.summarize_final(rows, expected_tasks=self._expected("final"), histories=self.histories)
        ledger = closed_ledger(self.root, self.maximum)
        optimizer_binding = verify_optimizer_receipts(self.root, histories)
        actual_calls = {p.stem for p in (self.root / "api/calls").glob("*.json")}
        expected_calls = self.used_solves | {h for r in histories for h in r["optimizer_requests"]}
        if actual_calls != expected_calls or {p.stem for p in (self.root / "solves").glob("*.json")} != self.used_solves:
            raise ValueError("Unexpected or missing API/solver artifacts outside the declared study")
        if source_hashes(self.repo) != self.protocol["source_hashes"]:
            raise ValueError("Code changed during final evaluation; cannot publish results")
        return _save(self.root / "results.json", {"version": VERSION, "complete": True,
            "protocol_hash": self.protocol["record_hash"], "data_manifest_hash": self.manifest["record_hash"],
            "final_freeze_hash": frozen["record_hash"], "history_hashes": [r["record_hash"] for r in histories],
            "summary": summary, "ledger": ledger, "optimizer_receipt_binding": optimizer_binding, "histories": histories,
            "no_cross_domain_efficacy_claim": True, "smoke_not_effect_evidence": self.design_name == "smoke"},
            completed=self.completed)

    def run(self, *, api_factory=stable_api):
        self.prepare()
        if self.completed:
            return self._execute(OfflineAPI(self.root / "api"))
        with api_factory(self.repo, self.root / "api", max_calls=self.maximum, workers=4) as api:
            if api.model != self.protocol["model"]:
                raise ValueError("Transport model differs from preregistration")
            return self._execute(api)
