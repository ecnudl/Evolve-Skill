"""Bounded two-round integration study; historical panels are engineering only.

This driver does not overwrite the default SkillOpt trainer or any frozen study.
Fresh benchmark efficacy requires a separate, prospectively disjoint task panel.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v4.tasks import build_tasks
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import core, governance, research
from .adapters import CodingAdapter, QAAdapter

VERSION = "coevolution-v5-integration-study-v1"
POLICIES = ("fixed", "feedback", "research")
SEED = 20260910


def text(skill):
    return skill if isinstance(skill, str) else skill.get("content", "")


def save(path, value):
    write_immutable_json(Path(path), core.seal(value))


def read(path):
    value = json.loads(Path(path).read_text())
    core.verify(value)
    return {k: v for k, v in value.items() if k != "record_hash"}


def task_id(adapter):
    return adapter.task.id if adapter.domain == "coding" else adapter.task["id"]


def cluster(adapter):
    return adapter.task.cluster_id if adapter.domain == "coding" else adapter.task["cluster_id"]


def artifact(adapter, row):
    return row["files"] if adapter.domain == "coding" else row["answer"]


def bind(rows, solver):
    """Host binds evaluation to the exact returned solver intervention."""
    if any(row["artifact_hash"] != solver["artifact_hash"] for row in rows):
        raise ValueError("Evaluation is not of the actual returned solver artifact")
    bound = []
    for row in rows:
        details = {**row["details"], "solver_skill_hash": solver["skill_hash"],
                   "solver_request_hashes": solver["request_hashes"],
                   "solver_delivery_status": solver.get("delivery_status"),
                   "solver_target_ok": solver.get("target_ok")}
        if row["status"] == "unknown" and solver.get("target_ok") is False:
            details.update(reason="transport_unavailable", category="transport")
        bound.append(core.make_assessment(
            **{k: v for k, v in row.items() if k not in {"receipt_hash", "details"}}, details=details))
    return bound


def engineering_panel(repo):
    """Only known development material; never mislabel this as unseen data."""
    tasks = build_tasks()
    source = [[CodingAdapter(t) for t in tasks if t.split == f"learn{r}"] for r in (0, 1)]
    # Eligibility depends only on content identity, never model outcomes. One
    # historical gate project has a byte-identical "equivalent" and reference.
    promotion = [CodingAdapter(replace(t, split="promotion")) for t in tasks if t.split == "gate"
                 and digest(t.reference_files) != digest(t.metadata["controls"]["equivalent"])][:2]
    final = [CodingAdapter(replace(t, split="final")) for t in tasks if t.split == "learn2"]
    data = json.loads((Path(repo) / "data/searchqa_split/train/items.json").read_text())
    selected = random.Random(SEED).sample(data, 6)
    qa = []
    for index, item in enumerate(selected):
        qa.append(QAAdapter({"id": "v5-searchqa-" + item["id"], "cluster_id": "searchqa-" + item["id"],
                             "question": item["question"], "contexts": [item["context"]], "answers": item["answers"],
                             "split": "development" if index < 4 else "final"}))
    return {"source": source, "scope": [qa[:2], qa[:4]], "promotion": promotion, "final": final + qa[4:]}


class Study:
    def __init__(self, repo, root, *, histories=1, repeats=1, max_calls=512, panel=None):
        self.repo, self.root = Path(repo).resolve(), Path(root).resolve()
        parent = self.repo / "outputs/coevolution_v5"
        if self.root == parent or not self.root.is_relative_to(parent):
            raise ValueError("A separate V5 run beneath outputs/coevolution_v5 is required")
        if type(histories) is not int or not 1 <= histories <= 3 or type(repeats) is not int or not 1 <= repeats <= 3:
            raise ValueError("Bounded histories/repeats required")
        if type(max_calls) is not int or not 1 <= max_calls <= 1600:
            raise ValueError("max_calls must be an integer in [1,1600]")
        self.histories, self.repeats, self.max_calls = histories, repeats, max_calls
        self.panel = panel or engineering_panel(self.repo)
        self.memory = {}

    def _sources(self):
        paths = sorted((self.repo / "skillopt/coevolution_v5").glob("*.py"))
        paths += [self.repo / p for p in (
            "scripts/coevolution_v5.py", "docs/coevolution-v5-protocol.md", "skillopt/coevolution/budget.py",
            "skillopt/coevolution/executor.py", "skillopt/coevolution_v3/executor.py",
            "skillopt/coevolution_v3/validator.py",
            "skillopt/coevolution_v3/tasks.py", "skillopt/coevolution_v4/tasks.py", "skillopt/validator_pilot/tasks.py",
            "skillopt/coevolution_v4/experiment.py",
            "skillopt/validator_pilot/api.py", "skillopt/validator_document_transport.py",
            "skillopt/validator_pilot/research.py", "skillopt/envs/searchqa/evaluator.py")]
        return {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def _panel(self):
        def encode(adapter):
            return {"domain": adapter.domain, "task": adapter.task.to_dict() if adapter.domain == "coding" else adapter.task}
        return {key: [[encode(a) for a in group] for group in groups] if key in {"source", "scope"}
                else [encode(a) for a in groups] for key, groups in self.panel.items()}

    def _audit_tasks(self):
        return [task_id(random.Random(SEED + index).choice(group))
                for index, group in enumerate(self.panel["source"])]

    def prepare(self):
        if len(self.panel["source"]) != 2 or len(self.panel["scope"]) != 2:
            raise ValueError("Integration protocol has two rounds")
        dev = [a for groups in (self.panel["source"], self.panel["scope"]) for group in groups for a in group]
        dev_clusters, final_clusters = {cluster(a) for a in dev}, {cluster(a) for a in self.panel["final"]}
        promotion_clusters = {cluster(a) for a in self.panel["promotion"]}
        if dev_clusters & final_clusters or promotion_clusters & (dev_clusters | final_clusters):
            raise ValueError("Development/promotion/final project overlap inside this run")
        controls = []
        for adapter in self.panel["promotion"]:
            task = adapter.task
            for name, files, truth in (("reference", task.reference_files, "good"),
                                      ("equivalent", task.metadata["controls"]["equivalent"], "good"),
                                      ("semantic_mutant", task.metadata["controls"]["semantic_mutant"], "bad"),
                                      ("preservation_mutant", task.metadata["controls"]["preservation_mutant"], "bad")):
                controls.append({"artifact_id": task.id + ":" + name, "task_id": task.id, "cluster_id": task.cluster_id,
                                 "artifact_hash": digest(files), "files": files, "truth": truth})
        self.controls = controls
        governance._artifacts({"artifacts": controls})
        protocol = {"version": VERSION, "policies": list(POLICIES), "histories": self.histories,
                    "repeats": self.repeats, "rounds": 2, "model": "glm-5.3", "workers": 4,
                    "max_calls": self.max_calls, "panel_hash": digest(self._panel()), "source_hashes": self._sources(),
                    "historical_exposure": True, "purpose": "engineering_integration_not_benchmark_efficacy",
                    "original_skillopt_baseline_included": False, "final_is_not_unseen_public_benchmark": True,
                    "human_review_status": "pending_external_human", "calibration_repeats": [0, 1],
                    "calibration_shared_across_frozen_arms_not_reused_within_arm": True,
                    "preselected_pass_audit": self._audit_tasks(),
                    "final_feedback_forbidden": True, "semantic_retries": 0}
        save(self.root / "protocol.json", protocol)
        save(self.root / "panel.json", self._panel())
        save(self.root / "calibration_manifest.json", {"artifacts": controls, "repeats": [0, 1]})
        self.verify()
        return protocol

    def verify(self):
        protocol = read(self.root / "protocol.json")
        if protocol["source_hashes"] != self._sources() or protocol["panel_hash"] != digest(self._panel()):
            raise ValueError("Frozen V5 sources or panel changed")

    def _preflight_controls(self):
        """Confirm frozen labels with the private oracle before any model calls.

        This is host-only data integrity checking, never validator feedback.
        """
        indexed = {task_id(a): a for a in self.panel["promotion"]}
        records = []
        for control in self.controls:
            rows = indexed[control["task_id"]].evaluate(
                control["files"], core.initial_rubric(), phase="promotion", public_only=False)
            native = next(r for r in rows if r["check_id"] == "coding_contract")
            expected = "pass" if control["truth"] == "good" else "fail"
            if native["status"] != expected or native["verified"] is not True:
                raise ValueError("Frozen calibration control truth is not confirmed by the private executable oracle")
            records.append({"artifact_id": control["artifact_id"], "assessment": native})
        save(self.root / "private_control_preflight.json", {"records": records, "never_model_feedback": True})

    def _cached(self, api, namespace, identity, compute):
        key = digest(identity)
        path = self.root / namespace / (key + ".json")
        if key in self.memory:
            return self.memory[key]
        if path.exists():
            wrapped = read(path)
            if wrapped["identity"] != identity:
                raise ValueError("Cached record identity mismatch")
            row = wrapped["result"]
            from skillopt.coevolution_v4.experiment import require_cached_calls
            require_cached_calls(api, row)
        else:
            row = compute(key)
            save(path, {"identity": identity, "result": row})
        self.memory[key] = row
        return row

    def _solve(self, api, adapter, skill, history, stage, repeat):
        identity = {"kind": "solve", "task": digest(adapter.public_task()), "skill": text(skill),
                    "history": history, "stage": stage, "repeat": repeat}
        return self._cached(api, "targets", identity,
                            lambda key: adapter.solve(api, text(skill), key=key, repeat=repeat))

    def _warm_solutions(self, api, jobs, label):
        unique = {(task_id(a), text(s), h, stage, rep): (a, s, h, stage, rep)
                  for a, s, h, stage, rep in jobs}
        scheduled = list(unique.values())
        random.Random(SEED + int(digest(label)[:8], 16)).shuffle(scheduled)
        api.parallel(scheduled, lambda args: self._solve(api, *args), label)

    def _probe(self, api, adapter, row, rubric, history, stage, repeat):
        from .evaluation import probe
        if adapter.domain != "coding" or artifact(adapter, row) is None:
            return {"inputs": [], "schema_valid": False, "error": "no_code_artifact"}
        identity = {"kind": "probe", "task": digest(adapter.public_task()), "artifact": row["artifact_hash"],
                    "rubric": rubric["rubric_hash"], "history": history, "stage": stage, "repeat": repeat}
        return self._cached(api, "probes", identity,
                            lambda key: probe(api, adapter, artifact(adapter, row), rubric, key=key, repeat=repeat))

    def _assess(self, adapter, row, rubric, inputs, phase="development"):
        assessed = adapter.evaluate(artifact(adapter, row), rubric, phase=phase, extra_inputs=inputs)
        return bind(assessed, row)

    def _packet(self, adapter, row, rubric, assessed, preselected=False, pair=None):
        comparisons = []
        if pair is not None:
            comparisons = [{"check_id": check_id, "repeat": pair["repeat"],
                            "arms": {arm: {k: check[k] for k in (
                                "status", "artifact_hash", "receipt_hash", "gate_eligible", "verified")}
                                | {"skill_hash": pair["skill_hashes"][arm]}
                                for arm in ("baseline", "current", "candidate")
                                for check in pair[arm] if check["check_id"] == check_id},
                            "interpretation": "paired_observation_not_proven_causation"}
                           for check_id in pair["required_check_ids"]]
        return core.feedback_packet(task_id=task_id(adapter), cluster_id=cluster(adapter), domain=adapter.domain,
                                    assessments=assessed, artifact=artifact(adapter, row),
                                    contract=adapter.task.prompt if adapter.domain == "coding" else adapter.task["question"],
                                    task_context=adapter.public_task(), comparisons=comparisons,
                                    research_context={"audit": {"preselected": preselected,
                                                                 "selection": "pre_execution_random"}})

    def _pair(self, adapter, rows, rubric, inputs, repeat):
        return {"task_id": task_id(adapter), "cluster_id": cluster(adapter), "domain": adapter.domain, "repeat": repeat,
                "rubric_hash": rubric["rubric_hash"],
                "required_check_ids": ["coding_contract" if adapter.domain == "coding" else "qa_answer"],
                "skill_hashes": {arm: row["skill_hash"] for arm, row in rows.items()},
                **{arm: self._assess(adapter, row, rubric, inputs) for arm, row in rows.items()}}

    def run(self, *, api_factory=BudgetedAPI):
        from .evaluation import compare_validators, repair_feedback_comparison, summarize_final
        protocol = self.prepare()
        if (self.root / "results.json").exists():
            return read(self.root / "results.json")
        if executor.sandbox_probe().get("ok") is not True:
            raise RuntimeError("OS isolation unavailable; no candidate execution")
        self._preflight_controls()
        branches = {(h, p): {"skill": governance.initial_skill_state(), "rubric": core.initial_rubric(), "feedback": []}
                    for h in range(self.histories) for p in POLICIES}
        rubrics = {core.initial_rubric()["rubric_hash"]: core.initial_rubric()}
        decisions, feedback_all, repair_comparisons = [], [], []
        with api_factory(self.repo, self.root / "api", max_calls=self.max_calls, workers=4) as api:
            for round_index in range(2):
                self.verify()
                source = self.panel["source"][round_index]
                replay = [a for group in self.panel["source"][:round_index] for a in group]
                scopes = self.panel["scope"][round_index]
                pending_updates = {}
                for (history, policy), branch in branches.items():
                    rubric, state = branch["rubric"], branch["skill"]
                    stage = f"h{history}-r{round_index}"
                    self._warm_solutions(api, [(a, parent, history, stage, repeat) for a in source + replay
                        for repeat in range(self.repeats) for parent in sorted({text(state["working"]), ""})], stage + "-before")
                    before = []
                    for adapter in source + replay:
                        for repeat in range(self.repeats):
                            for parent in sorted({text(state["working"]), ""}):
                                row = self._solve(api, adapter, parent, history, stage, repeat)
                                assessed = self._assess(adapter, row, rubric, [])
                                before.append(self._packet(adapter, row, rubric, assessed))
                    # Retain bounded complete previous failed-candidate evidence; no calibration records.
                    packets = before[:8] + branch["feedback"][:4]
                    system, user = core.optimizer_messages(text(state["working"]), state["repair_parent"], packets)
                    proposal = api.call(system, user, kind="v5_skill", key=digest({"history": history, "round": round_index,
                                        "messages": [system, user]}), max_tokens=2200)
                    content = proposal.get("response", "").strip()
                    valid = proposal.get("ok") is True and 100 <= len(content) <= 5000 and not content.startswith("```")
                    candidate = {"content": content if valid else "", "valid": valid, "request_hash": proposal["request_hash"]}
                    if not valid:
                        invalid = {k: deepcopy(v) for k, v in state.items() if k != "state_hash"}
                        invalid.update(last_round=round_index, repair_parent={"candidate": candidate,
                                       "usage": "optimizer_repair_only", "reason": "invalid_skill_delivery"})
                        branch["skill"] = core.seal(invalid, "state_hash")
                        decisions.append({"history": history, "policy": policy, "round": round_index,
                                          "action": "Restrict", "reason": "invalid_skill_delivery"})
                        branch["feedback"] = before[:8]
                        feedback_all.extend(before)
                    else:
                        jobs = []
                        for group, adapters in (("source", source), ("replay", replay), ("scope", scopes)):
                            parent = state["approved"] if group == "scope" else state["working"]
                            jobs.extend((a, s, history, stage, r) for a in adapters for r in range(self.repeats)
                                        for s in ("", parent, candidate))
                        self._warm_solutions(api, jobs, stage + "-candidate")
                        grouped = {"source": [], "replay": [], "scope": []}
                        candidate_packets = []
                        for group, adapters in (("source", source), ("replay", replay), ("scope", scopes)):
                            parent = state["approved"] if group == "scope" else state["working"]
                            for adapter in adapters:
                                for repeat in range(self.repeats):
                                    rows = {arm: self._solve(api, adapter, skill, history, stage, repeat) for arm, skill in (
                                        ("baseline", ""), ("current", parent), ("candidate", candidate))}
                                    probe = self._probe(api, adapter, rows["candidate"], rubric, history, stage, repeat)
                                    pair = self._pair(adapter, rows, rubric, probe["inputs"], repeat)
                                    grouped[group].append(pair)
                                    packet = self._packet(adapter, rows["candidate"], rubric, pair["candidate"],
                                                          task_id(adapter) in self._audit_tasks(), pair=pair)
                                    candidate_packets.append(packet)
                        # Replay the old Approved intervention itself, not the new
                        # proposal, before retaining any existing domain scope.
                        pre_revalidation_state = state
                        if state["approved"]:
                            for domain in sorted({p["domain"] for p in grouped["scope"]}):
                                if domain not in {r["domain"] for r in state["approved_scope"]}:
                                    continue
                                old_pairs = [{**p, "current": p["baseline"], "candidate": p["current"],
                                              "skill_hashes": {"baseline": p["skill_hashes"]["baseline"],
                                                               "current": p["skill_hashes"]["baseline"],
                                                               "candidate": p["skill_hashes"]["current"]}}
                                             for p in grouped["scope"] if p["domain"] == domain]
                                old_decision = governance.evaluate_pairs(old_pairs, False)
                                if old_decision["harms"]:
                                    state = governance.revoke_scope(state, domain, old_decision,
                                        "Confirmed development replay regression of the existing Approved Skill")
                        branch["skill"] = governance.transition_skill(state, candidate,
                            {"source": grouped["source"], "replay": grouped["replay"]}, grouped["scope"], round_index)
                        decisions.append({"history": history, "policy": policy, "round": round_index,
                                          **branch["skill"]["last_transition"]})
                        save(self.root / "decisions" / f"h{history}-{policy}-r{round_index}.json",
                             {"before": pre_revalidation_state, "after_scope_revalidation": state,
                              "candidate": candidate, "pairs": grouped, "after": branch["skill"]})
                        branch["feedback"] = candidate_packets
                        feedback_all.extend(candidate_packets)
                    if round_index == 0 and policy != "fixed":
                        pending_updates[history, policy] = research.evolve(api, rubric, branch["feedback"][:8],
                            self.root / "research" / f"h{history}-{policy}", f"h{history}-{policy}-r0", policy == "research", 0)
                # All validator proposals sealed before ANY promotion judgments can be inspected.
                save(self.root / "validator_candidates" / f"r{round_index}.json", {
                    f"h{h}-{p}": value for (h, p), value in pending_updates.items()})
                for (history, policy), proposal in pending_updates.items():
                    branch = branches[history, policy]
                    proposed = proposal.get("proposed_rubric")
                    if proposed is None:
                        continue
                    changed_domains = {d for a, b in zip(branch["rubric"]["checks"], proposed["checks"])
                                       if a != b for d in a["domains"]}
                    if changed_domains - {"coding"}:
                        save(self.root / "promotions" / f"h{history}-{policy}.json",
                             {"promoted": False, "reason": "qa_changes_require_qa_calibration", "next_round_only": True})
                        continue
                    registry = governance.CalibrationRegistry(self.root / "calibration" / f"h{history}-{policy}")
                    manifest = {"artifacts": self.controls, "repeats": [0, 1],
                                "current_rubric_hash": branch["rubric"]["rubric_hash"]}
                    dev_clusters = [cluster(a) for groups in (self.panel["source"], self.panel["scope"]) for group in groups for a in group]
                    registry.reserve("r0", manifest, dev_clusters, [p["artifact_hash"] for p in branch["feedback"]],
                                     [cluster(a) for a in self.panel["final"]], proposed["rubric_hash"], 0)
                    compared = compare_validators(api, self.panel["promotion"], self.controls,
                        {"old": branch["rubric"], "new": proposed}, self.root / "validator_comparisons" / f"h{history}-{policy}",
                        key=f"h{history}-{policy}-r0", repeat=2)
                    outcome = registry.consume("r0", compared["rows"]["old"], compared["rows"]["new"],
                                               proposal_hash=proposed["rubric_hash"], round_index=0)
                    save(self.root / "promotions" / f"h{history}-{policy}.json", outcome)
                    if outcome["decision"]["promote"]:
                        branch["rubric"] = proposed
                        rubrics[proposed["rubric_hash"]] = proposed
                save(self.root / "states" / f"r{round_index}.json", {f"h{h}-{p}": b for (h, p), b in branches.items()})
            # Feedback utility is a separate diagnostic; never use it to alter sealed branches.
            all_dev_adapters = {task_id(a): a for group in self.panel["source"] for a in group}
            for packet in feedback_all:
                if packet["domain"] == "coding" and packet["artifact"] is not None and any(
                    r["status"] == "fail" and r["gate_eligible"] for r in packet["observations"]):
                    adapter = all_dev_adapters.get(packet["task_id"])
                    if adapter:
                        repair_comparisons.append(repair_feedback_comparison(api, adapter, packet["artifact"], packet,
                            rubrics[packet["rubric_hash"]], self.root / "feedback_utility", key=packet["record_hash"]))
                        break
            save(self.root / "final_frozen.json", {"protocol_hash": digest(protocol), "states": {
                f"h{h}-{p}": b for (h, p), b in branches.items()}, "decisions_hash": digest(decisions)})
            final = []
            for history in range(self.histories):
                for adapter in self.panel["final"]:
                    interventions = {"no_skill": ("", True)}
                    for policy in POLICIES:
                        branch = branches[history, policy]
                        deployment = governance.eligible_skill(branch["skill"], adapter.domain,
                                                                task_id=task_id(adapter), cluster_id=cluster(adapter))
                        interventions[policy] = (text(deployment["skill"]), deployment["fallback"])
                        interventions["working_" + policy] = (text(branch["skill"]["working"]), False)
                    for policy, (skill, fallback) in interventions.items():
                        for repeat in range(self.repeats):
                            row = self._solve(api, adapter, skill, history, "final", repeat)
                            assessed = self._assess(adapter, row, core.initial_rubric(), [], phase="final")
                            check = next(r for r in assessed if r["check_id"] == (
                                "coding_contract" if adapter.domain == "coding" else "qa_answer"))
                            score = float(check["status"] == "pass") if check["status"] in {"pass", "fail"} else None
                            final.append({"policy": policy, "domain": adapter.domain, "task_id": task_id(adapter),
                                          "cluster_id": cluster(adapter), "history": history, "repeat": repeat,
                                          "score": score, "request_hashes": row["request_hashes"], "fallback": fallback,
                                          "error": check["details"].get("reason") if score is None else None,
                                          "skill_hash": row["skill_hash"], "artifact_hash": row["artifact_hash"]})
            save(self.root / "final_rows.json", {"rows": final})
            review_rows = [{"feedback_id": p["record_hash"], "domain": p["domain"], "packet": p,
                            "disputed": any(r["status"] == "unknown" for r in p["observations"])}
                           for p in {p["record_hash"]: p for p in feedback_all}.values()]
            if review_rows:
                governance.export_review_queue(self.root / "human_review/queue.json", review_rows, seed=SEED)
            ledger = api.ledger()
            returned_models = Counter(json.loads(p.read_text()).get("returned_model", "unreported")
                                      for p in (self.root / "api/calls").glob("*.json"))
            if ledger["unresolved_reservations"]:
                raise ValueError("Unresolved transport reservations cannot be reported complete")
        self.verify()
        result = {"version": VERSION, "status": "complete", "protocol_hash": digest(protocol),
                  "decisions": decisions, "final": summarize_final(final), "ledger": ledger,
                  "returned_models": dict(returned_models),
                  "feedback": core.feedback_summary(feedback_all), "feedback_utility": repair_comparisons,
                  "human_review": "queue_exported_not_yet_performed" if review_rows else "no_feedback_to_review",
                  "engineering_only": True,
                  "cross_domain_efficacy_established": False, "final_feedback_used": False}
        save(self.root / "results.json", result)
        return result
