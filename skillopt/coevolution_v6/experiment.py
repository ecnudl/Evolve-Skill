"""Two predeclared V6 studies; neither overwrites nor re-scores a frozen run.

A: repeated, equal-budget verifier portfolios on new Coding projects.
B: source-evolved candidates, forced versus explicit-contract routing, on
unseen native task instances. Candidate evaluation is not deployment approval.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v4.experiment import require_cached_calls
from skillopt.coevolution_v5 import core, governance, research
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v5.evaluation import probe, repair_feedback_comparison, summarize_final
from skillopt.coevolution_v5.experiment import bind, read, save, text
from skillopt.validator_pilot.api import digest

VERSION = "v6-prospective-portfolio-native-routing-v1"
SEED = 20260911


def identifier(adapter):
    return adapter.task.id if isinstance(adapter, CodingAdapter) else adapter.task["id"]


def project(adapter):
    return adapter.task.cluster_id if isinstance(adapter, CodingAdapter) else adapter.task["cluster_id"]


def task_payload(adapter):
    return adapter.task.to_dict() if isinstance(adapter, CodingAdapter) else deepcopy(adapter.task)


def code_artifact(adapter, row):
    return row["files"] if isinstance(adapter, CodingAdapter) else row["artifact"]


def contract(adapter):
    if isinstance(adapter, CodingAdapter):
        return deepcopy(adapter.task.metadata["public_contract"])
    return deepcopy(adapter.public_task()["contract"])


def group(adapter):
    task = task_payload(adapter)
    metadata = task.get("metadata", {})
    return metadata.get("evaluation_group", metadata.get("group", task.get("evaluation_group")))


def event(stage, **values):
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False), flush=True)


def outcome(rows):
    checks = [r for r in rows if r["check_id"] in {"coding_contract", "coding_probe"}]
    if any(r["verified"] and r["status"] == "fail" for r in checks):
        return "detected"
    if len(checks) == 2 and all(r["verified"] and r["status"] == "pass" for r in checks):
        return "not_detected"
    return "unknown"


def portfolio_outcome(components):
    """Retain confirmed failures; do not manufacture passes from missing probes."""
    values = [outcome(component["assessments"]) for component in components]
    return "detected" if "detected" in values else "not_detected" if all(
        v == "not_detected" for v in values) else "unknown"


def selected_feedback(packets, *, maximum=6, char_limit=110000):
    chosen, used = [], 0
    for packet in sorted({p["record_hash"]: p for p in packets}.values(),
                         key=lambda p: (not any(r["status"] == "fail" for r in p["observations"]), p["record_hash"])):
        core.verify(packet)
        core.development_only(packet)
        size = len(json.dumps(packet, ensure_ascii=False))
        if len(chosen) < maximum and used + size <= char_limit:
            chosen.append(packet)
            used += size
    if packets and not chosen:
        raise ValueError("No complete development feedback fits the frozen context budget")
    return chosen


class Study:
    def __init__(self, repo, root, *, histories=3, blocks=4, max_calls=900, panel=None):
        self.repo, self.root = Path(repo).resolve(), Path(root).resolve()
        parent = self.repo / "outputs/coevolution_v6"
        if self.root == parent or not self.root.is_relative_to(parent):
            raise ValueError("Use a separate run below outputs/coevolution_v6")
        if type(histories) is not int or not 1 <= histories <= 3:
            raise ValueError("One to three explicitly recorded learning histories required")
        if type(blocks) is not int or not 1 <= blocks <= 6:
            raise ValueError("One to six explicitly recorded probe blocks required")
        if type(max_calls) is not int or not 1 <= max_calls <= 1600:
            raise ValueError("Logical-call cap must be in [1,1600]")
        self.histories, self.blocks, self.max_calls = histories, blocks, max_calls
        if panel is None:
            from .native import final_native_tasks
            from .tasks import calibration_tasks, development_tasks, final_coding_tasks
            panel = {"development": development_tasks(), "calibration": calibration_tasks(),
                     "final": final_coding_tasks() + final_native_tasks()}
        self.panel = panel
        self.memory = {}

    def _sources(self):
        paths = []
        for directory in ("skillopt/coevolution_v6", "skillopt/coevolution_v5"):
            paths.extend(sorted((self.repo / directory).glob("*.py")))
        paths.extend(self.repo / relative for relative in (
            "scripts/coevolution_v6.py", "docs/coevolution-v6-protocol.md",
            "skillopt/coevolution/budget.py", "skillopt/coevolution/executor.py",
            "skillopt/coevolution_v3/executor.py", "skillopt/coevolution_v3/validator.py",
            "skillopt/coevolution_v3/tasks.py", "skillopt/coevolution_v4/experiment.py",
            "skillopt/coevolution_v4/tasks.py", "skillopt/validator_pilot/tasks.py",
            "skillopt/validator_pilot/api.py", "skillopt/validator_pilot/research.py",
            "skillopt/validator_document_transport.py", "skillopt/envs/searchqa/evaluator.py"))
        return {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def _panel(self):
        return {phase: [{"domain": a.domain, "task": task_payload(a)} for a in adapters]
                for phase, adapters in self.panel.items()}

    def _legacy_rubric(self):
        directory = self.repo / "outputs/coevolution_v5/glm53_integration_20260911_v1/research/h0-research"
        paths = list(directory.rglob("proposal.json"))
        if len(paths) != 1:
            raise ValueError("The explicit frozen V5 fallback proposal is unavailable")
        value = json.loads(paths[0].read_text())
        core.verify(value)
        rubric = core.validate_rubric(value["proposed_rubric"])
        return {"rubric": rubric, "source": str(paths[0].relative_to(self.repo)),
                "source_sha256": hashlib.sha256(paths[0].read_bytes()).hexdigest()}

    def prepare(self):
        phases = {phase: {project(a) for a in adapters} for phase, adapters in self.panel.items()}
        if any(phases[a] & phases[b] for a in phases for b in phases if a < b):
            raise ValueError("Development, calibration and final structural families must be disjoint")
        if len({identifier(a) for values in self.panel.values() for a in values}) != sum(map(len, self.panel.values())):
            raise ValueError("Task IDs must be unique across the complete frozen panel")
        for adapter in self.panel["final"]:
            if isinstance(adapter, CodingAdapter) and json.dumps(
                    contract(adapter), sort_keys=True, ensure_ascii=False) not in adapter.task.prompt:
                raise ValueError("Coding routing contract must be visibly declared in the task prompt")
        self.controls = []
        for adapter in self.panel["calibration"]:
            task = adapter.task
            for name, files, truth in (("reference", task.reference_files, "good"),
                    ("equivalent", task.metadata["controls"]["equivalent"], "good"),
                    ("semantic_mutant", task.metadata["controls"]["semantic_mutant"], "bad"),
                    ("preservation_mutant", task.metadata["controls"]["preservation_mutant"], "bad")):
                self.controls.append({"artifact_id": task.id + ":" + name, "task_id": task.id,
                                      "cluster_id": task.cluster_id, "artifact_hash": digest(files),
                                      "files": files, "truth": truth})
        governance._artifacts({"artifacts": self.controls})
        fallback = self._legacy_rubric()
        protocol = {"version": VERSION, "seed": SEED, "model": "glm-5.3", "workers": 4,
                    "histories": self.histories, "blocks": self.blocks, "max_calls": self.max_calls,
                    "source_rounds": 2, "source_hashes": self._sources(), "panel_hash": digest(self._panel()),
                    "fallback_proposal": fallback, "historical_template_reuse": False,
                    "public_benchmark": False, "synthetic_native_task_diagnostic": True,
                    "primary_validator_comparison": "old_a+old_b versus old_a+new; equal two-call budgets",
                    "validator_draw_channels": ["old_a", "old_b", "new"], "max_inputs_per_call": 4,
                    "candidate_only_is_secondary": True, "validator_screen_never_auto_activates": True,
                    "source_skill_evolution_rubric": core.initial_rubric()["rubric_hash"],
                    "final_policies": ["no_skill", "always_candidate", "mechanism_routed_candidate"],
                    "final_candidate_selection": "last syntactically valid proposal per history; no final selection",
                    "unapproved_candidate_counterfactual_not_production_deployment": True,
                    "routing": "explicit_public_contract_only_not_natural_language_classifier_or_gold",
                    "skill_mechanism": "constraint_preservation_hypothesis_not_certified_by_router",
                    "final_feedback_forbidden": True, "calibration_feedback_forbidden": True,
                    "repair_diagnostic": "all predeclared initial buggy development artifacts, paired per history",
                    "human_review": "external_review_pending_no_synthetic_reviewers", "semantic_retries": 0}
        save(self.root / "protocol.json", protocol)
        save(self.root / "panel.json", self._panel())
        save(self.root / "calibration_manifest.json", {"artifacts": self.controls,
             "blocks": list(range(self.blocks)), "source_task_families_disjoint": True})
        self.verify()
        return protocol

    def verify(self):
        protocol = read(self.root / "protocol.json")
        if protocol["source_hashes"] != self._sources() or protocol["panel_hash"] != digest(self._panel()):
            raise ValueError("Frozen V6 sources or task panel changed")
        if protocol["fallback_proposal"] != self._legacy_rubric():
            raise ValueError("Frozen predecessor proposal changed")

    def _cached(self, api, namespace, identity, compute):
        key = digest({"namespace": namespace, "identity": identity})
        path = self.root / namespace / (key + ".json")
        if key in self.memory:
            return self.memory[key]
        if path.exists():
            value = read(path)
            if value["identity"] != identity:
                raise ValueError("Cached identity mismatch")
            result = value["result"]
            require_cached_calls(api, result)
        else:
            result = compute(key)
            save(path, {"identity": identity, "result": result})
        self.memory[key] = result
        return result

    def _solve(self, api, adapter, skill, history, phase):
        identity = {"kind": "solve", "task": digest(adapter.public_task()), "skill": text(skill),
                    "history": history, "phase": phase}
        return self._cached(api, "targets", identity,
            lambda key: adapter.solve(api, text(skill), key=key, repeat=history))

    def _warm(self, api, jobs, label):
        jobs = list({(identifier(a), text(s), h, p): (a, s, h, p) for a, s, h, p in jobs}.values())
        random.Random(SEED + int(digest(label)[:8], 16)).shuffle(jobs)
        api.parallel(jobs, lambda args: self._solve(api, *args), label)

    def _preflight(self):
        if executor.sandbox_probe().get("ok") is not True:
            raise RuntimeError("The native Coding OS sandbox is unavailable")
        indexed = {identifier(a): a for a in self.panel["calibration"]}
        records = []
        for row in self.controls:
            assessment = next(r for r in indexed[row["task_id"]].evaluate(row["files"], core.initial_rubric(),
                phase="promotion", public_only=False) if r["check_id"] == "coding_contract")
            if assessment["status"] != ("pass" if row["truth"] == "good" else "fail") or not assessment["verified"]:
                raise ValueError("Frozen calibration control failed independent native truth preflight")
            records.append({"artifact_id": row["artifact_id"], "assessment": assessment})
        for adapter in self.panel["development"]:
            assessment = next(r for r in adapter.evaluate(adapter.task.files, core.initial_rubric(),
                phase="development") if r["check_id"] == "coding_contract")
            if assessment["status"] != "fail" or not assessment["verified"]:
                raise ValueError("The predeclared repair artifact must have a reproducible development defect")
        save(self.root / "private_preflight.json", {"calibration": records, "never_model_feedback": True})

    def _packet(self, adapter, solver, assessments, *, audit=False, pair=None):
        comparisons = [] if pair is None else [{"repeat": pair["repeat"], "arms": {
            arm: [{k: r[k] for k in ("check_id", "status", "receipt_hash", "artifact_hash")}
                  for r in pair[arm] if r["check_id"] == "coding_contract"]
            for arm in ("baseline", "current", "candidate")}, "interpretation": "paired_observation_not_causation"}]
        return core.feedback_packet(task_id=identifier(adapter), cluster_id=project(adapter), domain="coding",
            assessments=assessments, artifact=solver["files"], contract=adapter.task.prompt,
            task_context=adapter.public_task(), comparisons=comparisons,
            research_context={"audit": {"preselected": audit, "selection": "pre_execution_random"}})

    def _learn(self, api):
        rubric, tasks = core.initial_rubric(), self.panel["development"]
        histories = [{"state": governance.initial_skill_state(), "feedback": [], "candidate": None}
                     for _ in range(self.histories)]
        all_feedback, decisions = [], []
        audited = identifier(random.Random(SEED).choice(tasks))
        for round_index in range(2):
            for history, branch in enumerate(histories):
                event("source_evolution", history=history, round=round_index)
                state = branch["state"]
                self._warm(api, [(a, s, history, "development") for a in tasks
                           for s in ("", state["working"])], f"dev-before-{history}-{round_index}")
                before = []
                for adapter in tasks:
                    row = self._solve(api, adapter, state["working"], history, "development")
                    assessments = bind(adapter.evaluate(row["files"], rubric, phase="development"), row)
                    before.append(self._packet(adapter, row, assessments, audit=identifier(adapter) == audited))
                packets = selected_feedback(before + branch["feedback"])
                system, user = core.optimizer_messages(text(state["working"]), state["repair_parent"], packets)
                system += (
                    " This experiment targets the hypothesis of reusable Constraint Preservation. "
                    "Preserve only obligations the current task explicitly keeps active; do not retain "
                    "a superseded policy or impose a source-domain output format on another task. "
                    "Express the hypothesized mechanism and counterconditions, not a self-certified scope."
                )
                proposal = api.call(system, user, kind="v6_skill", key=digest({"history": history,
                    "round": round_index, "messages": [system, user]}), max_tokens=2400)
                content = proposal.get("response", "").strip()
                valid = proposal.get("ok") is True and 100 <= len(content) <= 5000 and not content.startswith("```")
                candidate = {"content": content, "valid": valid, "request_hash": proposal["request_hash"]}
                if not valid:
                    decisions.append({"history": history, "round": round_index, "action": "Restrict",
                                      "reason": "invalid_skill_delivery"})
                    branch["feedback"] = before
                    all_feedback.extend(before)
                    continue
                branch["candidate"] = candidate
                self._warm(api, [(a, candidate, history, "development") for a in tasks],
                           f"dev-candidate-{history}-{round_index}")
                pairs, feedback = [], []
                for adapter in tasks:
                    rows = {arm: self._solve(api, adapter, skill, history, "development")
                            for arm, skill in (("baseline", ""), ("current", state["working"]), ("candidate", candidate))}
                    probe_identity = {"kind": "development_probe", "task": identifier(adapter),
                        "artifact_hash": rows["candidate"]["artifact_hash"], "history": history, "round": round_index,
                        "rubric_hash": rubric["rubric_hash"]}
                    proposed = self._cached(api, "probes", probe_identity,
                        lambda key: probe(api, adapter, rows["candidate"]["files"], rubric, key=key, repeat=history))
                    pair = {"task_id": identifier(adapter), "cluster_id": project(adapter), "domain": "coding",
                            "repeat": history, "rubric_hash": rubric["rubric_hash"],
                            "required_check_ids": ["coding_contract"],
                            "skill_hashes": {arm: row["skill_hash"] for arm, row in rows.items()},
                            **{arm: bind(adapter.evaluate(row["files"], rubric, phase="development",
                                extra_inputs=proposed["inputs"]), row) for arm, row in rows.items()}}
                    pairs.append(pair)
                    feedback.append(self._packet(adapter, rows["candidate"], pair["candidate"],
                        audit=identifier(adapter) == audited, pair=pair))
                branch["state"] = governance.transition_skill(state, candidate, {"source": pairs, "replay": []}, [], round_index)
                branch["feedback"] = feedback
                all_feedback.extend(feedback)
                decisions.append({"history": history, "round": round_index, **branch["state"]["last_transition"]})
                save(self.root / "source_decisions" / f"h{history}-r{round_index}.json", {
                    "before": state, "candidate": candidate, "pairs": pairs, "after": branch["state"]})
            save(self.root / "source_states" / f"r{round_index}.json", {"histories": histories})
        save(self.root / "skills_frozen.json", {"histories": histories, "decisions": decisions,
             "selection": "last valid candidate; source approvals reported separately; final feedback unavailable"})
        return histories, decisions, all_feedback

    def _research(self, api, feedback, protocol):
        chosen = selected_feedback(feedback)
        save(self.root / "research_selection.json", {"model_visible": [p["record_hash"] for p in chosen],
             "all_feedback": sorted({p["record_hash"] for p in feedback}), "complete_packets_only": True})
        result = research.evolve(api, core.initial_rubric(), chosen, self.root / "research",
                                 "v6-fresh-development", True, 0)
        candidate = result.get("proposed_rubric")
        reason = "fresh_development_research"
        if candidate is not None:
            for left, right in zip(core.initial_rubric()["checks"], candidate["checks"]):
                if left != right and set(left["domains"]) - {"coding"}:
                    candidate = None
                    reason = "unsupported_qa_patch_fallback_to_frozen_predecessor"
                    break
        if candidate is None:
            candidate = protocol["fallback_proposal"]["rubric"]
            if reason == "fresh_development_research":
                reason = "invalid_fresh_proposal_fallback_to_frozen_predecessor"
        record = {"rubric": candidate, "selection_reason": reason,
                  "proposal_hash": result["record_hash"], "no_calibration_labels_seen": True}
        save(self.root / "validator_candidate_frozen.json", record)
        return candidate, result, record

    def _calibrate(self, api, candidate):
        from .statistics import summarize_validator
        indexed = {identifier(a): a for a in self.panel["calibration"]}
        jobs = [(row, block, channel) for row in self.controls for block in range(self.blocks)
                for channel in ("old_a", "old_b", "new")]
        random.Random(SEED).shuffle(jobs)
        save(self.root / "calibration_schedule.json", {"jobs": [[r["artifact_id"], b, c] for r, b, c in jobs]})

        def execute(job):
            row, block, channel = job
            rubric = candidate if channel == "new" else core.initial_rubric()
            adapter = indexed[row["task_id"]]
            identity = {"kind": "calibration", "artifact_id": row["artifact_id"],
                "artifact_hash": row["artifact_hash"], "rubric_hash": rubric["rubric_hash"],
                "block": block, "channel": channel}

            def compute(key):
                search = probe(api, adapter, row["files"], rubric, key=key, repeat=block)
                if not search.get("request_hash"):
                    raise ValueError("Every preflighted calibration artifact requires one real reserved probe request")
                assessed = adapter.evaluate(row["files"], rubric, phase="promotion",
                                            extra_inputs=search["inputs"], public_only=True)
                if any(r["artifact_hash"] != row["artifact_hash"] for r in assessed):
                    raise ValueError("Calibration execution artifact mismatch")
                return {"search": search, "assessments": assessed}

            return (row["artifact_id"], block, channel), self._cached(api, "calibration_calls", identity, compute)

        event("validator_calibration", jobs=len(jobs), projects=len(indexed), blocks=self.blocks)
        completed = api.parallel(jobs, execute, "v6-equal-budget-calibration")
        components = dict(completed)
        if len(components) != len(jobs):
            raise ValueError("Calibration scheduler dropped or duplicated a position")
        rows = []
        policies = {"old_single": ["old_a"], "new_single": ["new"],
                    "old_double": ["old_a", "old_b"], "portfolio": ["old_a", "new"]}
        for artifact in self.controls:
            for block in range(self.blocks):
                for policy, channels in policies.items():
                    parts = [components[artifact["artifact_id"], block, c] for c in channels]
                    inputs = {digest(i) for part in parts for i in part["search"]["inputs"]}
                    rows.append({k: artifact[k] for k in ("artifact_id", "artifact_hash", "task_id", "cluster_id", "truth")}
                        | {"block": block, "policy": policy, "outcome": portfolio_outcome(parts),
                           "input_count": len(inputs), "probe_request_hashes": [p["search"]["request_hash"] for p in parts],
                           "component_hashes": [digest(p) for p in parts], "public_only": True})
        save(self.root / "calibration_rows.json", {"rows": rows, "labels_never_optimizer_feedback": True})
        summary = summarize_validator(rows, expected_artifacts={r["artifact_id"]: {
            "cluster_id": r["cluster_id"], "truth": r["truth"]} for r in self.controls},
            expected_blocks=list(range(self.blocks)))
        save(self.root / "calibration_summary.json", summary)
        return summary

    def _repair(self, api):
        results = []
        for history in range(self.histories):
            for adapter in self.panel["development"]:
                rubric = core.initial_rubric()
                assessed = adapter.evaluate(adapter.task.files, rubric, phase="development")
                packet = core.feedback_packet(task_id=identifier(adapter), cluster_id=project(adapter), domain="coding",
                    assessments=assessed, artifact=adapter.task.files, contract=adapter.task.prompt,
                    task_context=adapter.public_task())
                result = repair_feedback_comparison(api, adapter, adapter.task.files, packet, rubric,
                    self.root / "feedback_utility", key=digest({"task": identifier(adapter), "history": history,
                                                               "packet": packet["record_hash"]}))
                results.append({"task_id": identifier(adapter), "cluster_id": project(adapter), "history": history,
                                "artifact_origin": "predeclared_buggy_task_fixture_not_agent_generated_failure", "result": result})
        save(self.root / "repair_results.json", {"rows": results, "no_update": True})
        return results

    def _final(self, api, histories):
        from .routing import route
        routes, jobs = {}, []
        for history, branch in enumerate(histories):
            candidate = text(branch["candidate"]) if branch["candidate"] else ""
            for adapter in self.panel["final"]:
                routes[history, identifier(adapter)] = route(contract(adapter), candidate)
                jobs.extend((adapter, skill, history, "final") for skill in ("", candidate))
        save(self.root / "final_frozen.json", {"histories": histories,
             "routes": [{"history": h, "task_id": t, "decision": d} for (h, t), d in routes.items()],
             "candidate_counterfactual_not_approved_deployment": True})
        event("final_native_evaluation", tasks=len(self.panel["final"]), histories=self.histories)
        self._warm(api, jobs, "v6-final-frozen-interventions")
        rows = []
        for history, branch in enumerate(histories):
            candidate = text(branch["candidate"]) if branch["candidate"] else ""
            for adapter in self.panel["final"]:
                routed = routes[history, identifier(adapter)]
                for policy, skill in (("no_skill", ""), ("always_candidate", candidate),
                                      ("mechanism_routed_candidate", candidate if routed["apply"] else "")):
                    result = self._solve(api, adapter, skill, history, "final")
                    artifact = code_artifact(adapter, result)
                    if isinstance(adapter, CodingAdapter):
                        assessed = bind(adapter.evaluate(artifact, core.initial_rubric(), phase="final"), result)
                        native = next(r for r in assessed if r["check_id"] == "coding_contract")
                        score = float(native["status"] == "pass") if native["status"] in {"pass", "fail"} else None
                        cases = native["details"].get("case_results", [])
                        error = native["details"].get("reason") if score is None else None
                    else:
                        native = adapter.evaluate(artifact, public_only=False)
                        core.verify(native)
                        score, cases = native["score"], native["case_results"]
                        error = native.get("error", native.get("reason")) if score is None else None
                        if result.get("target_ok") is False and score is None:
                            error = "transport_unavailable"
                    rows.append({"history": history, "repeat": 0, "policy": policy, "task_id": identifier(adapter),
                        "cluster_id": project(adapter), "domain": adapter.domain, "evaluation_group": group(adapter),
                        "score": score, "error": error, "case_results": cases, "fallback": not bool(skill),
                        "skill_hash": result["skill_hash"], "artifact_hash": result["artifact_hash"],
                        "request_hashes": result["request_hashes"], "route": routed})
        expected = {(identifier(a), h, p) for a in self.panel["final"] for h in range(self.histories)
                    for p in ("no_skill", "always_candidate", "mechanism_routed_candidate")}
        if len(rows) != len(expected) or {(r["task_id"], r["history"], r["policy"]) for r in rows} != expected:
            raise ValueError("Final observation grid differs from the preregistered panel")
        save(self.root / "final_rows.json", {"rows": rows, "final_feedback_used": False})
        from .analysis import summarize_transfer
        return {"native": summarize_final(rows), "cluster_analysis": summarize_transfer(rows)}

    def run(self, *, api_factory=BudgetedAPI):
        protocol = self.prepare()
        if (self.root / "results.json").exists():
            return read(self.root / "results.json")
        self._preflight()
        event("preflight_complete", calibration_artifacts=len(self.controls))
        with api_factory(self.repo, self.root / "api", max_calls=self.max_calls, workers=4) as api:
            histories, decisions, feedback = self._learn(api)
            candidate, proposal, selection = self._research(api, feedback, protocol)
            calibration = self._calibrate(api, candidate)
            # Both source Skill learning and research proposals precede access
            # to calibration labels; the screen is advisory, never a retrofit.
            repair = self._repair(api)
            final = self._final(api, histories)
            unique_feedback = {p["record_hash"]: p for p in feedback}
            review_rows = [{"feedback_id": p["record_hash"], "domain": p["domain"],
                           "disputed": any(r["status"] == "unknown" for r in p["observations"]),
                           **{k: p[k] for k in ("artifact", "contract", "facts", "hypotheses", "repair_guidance")}}
                           for p in unique_feedback.values()]
            if review_rows:
                governance.export_review_queue(self.root / "human_review/queue.json", review_rows, seed=SEED)
            ledger = api.ledger()
            if ledger["unresolved_reservations"]:
                raise ValueError("Unresolved requests cannot be reported complete")
        self.verify()
        returned = Counter(json.loads(p.read_text()).get("returned_model", "unreported")
                           for p in (self.root / "api/calls").glob("*.json"))
        from .analysis import summarize_repairs
        result = {"version": VERSION, "status": "complete", "protocol_hash": digest(protocol),
                  "decisions": decisions, "validator_selection": selection, "research_proposal_hash": proposal["record_hash"],
                  "calibration": calibration, "final": final, "repair": repair,
                  "repair_summary": summarize_repairs(repair), "ledger": ledger,
                  "returned_models": dict(returned), "unique_feedback": len(unique_feedback),
                  "human_review": "pending_external_human" if review_rows else "no_feedback_to_review",
                  "engineering_only": True, "public_benchmark_efficacy_established": False,
                  "final_feedback_used": False, "calibration_feedback_used": False}
        save(self.root / "results.json", result)
        event("complete", logical_calls=ledger["cached_logical_calls"])
        return result
