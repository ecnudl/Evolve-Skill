"""Evidence -> Research -> independent screen -> next-round feedback -> Skill.

The rejected-proposal shadow branch is an explicit intervention, never approval.
All final scoring and calibration labels remain outside optimizer feedback.
V5/V6 modules are reused without changing their frozen source bytes.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_evidence_view import research_evidence_view
from skillopt.coevolution_v5 import core, governance
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v5.evaluation import probe
from skillopt.coevolution_v5.experiment import bind, read, save, text
from skillopt.coevolution_v6.experiment import (
    Study as PreviousStudy,
)
from skillopt.coevolution_v6.experiment import (
    code_artifact,
    contract,
    event,
    group,
    identifier,
    project,
)
from skillopt.coevolution_v6.routing import route
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import analysis, research

VERSION = "v7-grounded-next-round-coevolution-v1"
SEED = 20260911
MAX_FEEDBACK_CHARS = 160000


class DeliveryAPI:
    """Identical predeclared reminders for every solver arm; no output repair."""

    def __init__(self, api):
        self.api = api

    def call(self, system, user, kind, key, **kwargs):
        if kind.startswith("v5_coding_"):
            system += (" DELIVERY REMINDER: output must start with an exact <<<FILE filename.py>>> header, "
                       "with no explanation or markdown before it. For revision ONLY, the exact word KEEP "
                       "is also allowed if initial_artifact_valid is true. Do not output a JSON file list.")
        elif kind.startswith("v6_native_"):
            system += (" DELIVERY REMINDER: return only the requested JSON object. For the revision request ONLY, "
                       "the exact word KEEP is permitted only when initial_artifact_valid is true. "
                       "Never return KEEP at generation. No prose or markdown fences.")
        return self.api.call(system, user, kind, key, **kwargs)


def validator_activation(summary, proposal):
    """One prospective screen authorizes next-round development use only."""
    reasons = []
    if proposal is None:
        reasons.append("no_valid_fresh_research_proposal")
    if summary is None:
        reasons.append("independent_screen_unavailable")
    else:
        gate = summary["primary_gate"]
        reasons.extend(gate["reasons"])
        if gate["action"] != "Support":
            reasons.append("independent_screen_did_not_support")
        primary = summary["comparisons"]["portfolio_vs_old_double"]["metrics"]["bad_detection"]
        p = primary["sign_flip"]["p_two_sided"]
        if p is None or p > 0.05:
            reasons.append("exact_cluster_comparison_not_supported_at_05")
    return core.seal({"activate_next_round": not reasons, "reasons": sorted(set(reasons)),
                      "scope": "next_round_development_feedback_only", "deployment_approval": False,
                      "calibration_summary_hash": summary["summary_hash"] if summary else None,
                      "candidate_rubric_hash": proposal["rubric_hash"] if proposal else None,
                      "feedback_contains_calibration_labels": False})


def optimizer_payload(parent, working, packets):
    """Use complete grounded views in BOTH arms, not raw ambiguous starter code."""
    views = [research_evidence_view(p, max_chars=MAX_FEEDBACK_CHARS) for p in packets]
    if len(json.dumps(views, ensure_ascii=False)) > MAX_FEEDBACK_CHARS:
        raise ValueError("Complete paired feedback exceeds frozen context budget; no silent selection")
    system = (
        "Improve a procedural Skill from host-grounded DEVELOPMENT evidence. Return 100-450 words of "
        "plain text, no fences. Task contracts outrank Skills. Learn a reusable constraint-preservation "
        "mechanism with explicit applicability, supersession counterconditions and fallback. Do not memorize "
        "task IDs, constants, answers, filenames or source-domain delivery grammar. The parent candidate "
        "may be UNAPPROVED: it is a repair hypothesis, not a successful global rule. Only verified failing "
        "execution receipts establish observed failures. Original task fixtures are NOT Base executions. "
        "Pass and unknown do not establish bugs, causal attribution or safety. Research hypotheses and "
        "repair advice require reexecution. Never change evaluation requirements or authorize yourself. "
        "If no semantic defect is demonstrated, state a cautious procedure without inventing discoveries."
    )
    user = {"working": text(working), "parent_candidate": text(parent),
            "parent_deployment_approved": False, "development_evidence": views,
            "feedback_packet_hashes": [p["record_hash"] for p in packets],
            "calibration_or_final_labels_available": False,
            "context_policy": "all_complete_paired_views_no_truncation"}
    return system, json.dumps(user, ensure_ascii=False, sort_keys=True)


class Study(PreviousStudy):
    def __init__(self, repo, root, *, histories=2, blocks=4, max_calls=700, panel=None):
        self.repo, self.root = Path(repo).resolve(), Path(root).resolve()
        parent = self.repo / "outputs/coevolution_v7"
        if self.root == parent or not self.root.is_relative_to(parent):
            raise ValueError("Use a separate run below outputs/coevolution_v7")
        if type(histories) is not int or not 1 <= histories <= 3:
            raise ValueError("One to three learning histories required")
        if type(blocks) is not int or not 1 <= blocks <= 6:
            raise ValueError("One to six explicitly frozen calibration blocks required")
        if type(max_calls) is not int or not 1 <= max_calls <= 1600:
            raise ValueError("Bounded logical call budget required")
        if panel is None:
            from .tasks import calibration_tasks, development_tasks, final_coding_tasks, final_native_tasks
            panel = {"development": development_tasks(), "calibration": calibration_tasks(),
                     "final": final_coding_tasks() + final_native_tasks()}
        self.panel, self.memory = panel, {}
        self.histories, self.blocks, self.max_calls = histories, blocks, max_calls

    def _sources(self):
        previous = super()._sources()
        paths = list((self.repo / "skillopt/coevolution_v7").glob("*.py"))
        paths.extend(self.repo / p for p in ("skillopt/coevolution_evidence_view.py",
                                            "scripts/coevolution_v7.py", "docs/coevolution-v7-protocol.md"))
        return {**previous, **{str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(paths)}}

    def prepare(self):
        if set(self.panel) != {"development", "calibration", "final"} or any(not p for p in self.panel.values()):
            raise ValueError("Three nonempty disjoint phases required")
        phases = {p: {project(a) for a in tasks} for p, tasks in self.panel.items()}
        if any(phases[a] & phases[b] for a in phases for b in phases if a < b):
            raise ValueError("Development/calibration/final structural families must be disjoint")
        all_tasks = [a for tasks in self.panel.values() for a in tasks]
        if len({identifier(a) for a in all_tasks}) != len(all_tasks):
            raise ValueError("Task IDs must be globally unique")
        for adapter in self.panel["final"]:
            if isinstance(adapter, CodingAdapter) and json.dumps(
                    contract(adapter), sort_keys=True, ensure_ascii=False) not in adapter.task.prompt:
                raise ValueError("The routing contract must be public in the Coding prompt")
        self.controls = []
        for adapter in self.panel["calibration"]:
            task = adapter.task
            for name, files, truth in (("reference", task.reference_files, "good"),
                    ("equivalent", task.metadata["controls"]["equivalent"], "good"),
                    ("semantic_mutant", task.metadata["controls"]["semantic_mutant"], "bad"),
                    ("preservation_mutant", task.metadata["controls"]["preservation_mutant"], "bad")):
                self.controls.append({"artifact_id": task.id + ":" + name, "task_id": task.id,
                    "cluster_id": task.cluster_id, "artifact_hash": digest(files), "files": files, "truth": truth})
        governance._artifacts({"artifacts": self.controls})
        d, c, f = (len(self.panel[p]) for p in ("development", "calibration", "final"))
        upper_bound = 11 * d * self.histories + 3 * self.histories + 3 + 12 * c * self.blocks + 6 * f * self.histories
        if upper_bound > self.max_calls:
            raise ValueError("The complete predeclared design exceeds the logical call cap")
        from .transport import PacingPolicy
        protocol = {"version": VERSION, "seed": SEED, "histories": self.histories, "blocks": self.blocks,
                    "max_calls": self.max_calls, "logical_call_upper_bound": upper_bound, "workers": 4, "model": "glm-5.3",
                    "source_hashes": self._sources(), "panel_hash": digest(self._panel()),
                    "pacing_policy": vars(PacingPolicy()), "source_rounds": 2,
                    "primary_feedback_comparison": "shared old_a+old_b versus shared old_a+fresh_new",
                    "primary_final_comparison": "research_candidate_shadow versus fixed_validator_candidate",
                    "fresh_research_only_no_historical_fallback": True,
                    "research_input": "complete_identity_grounded_development_evidence_views",
                    "research_fixture_origin": "predeclared_host_bug_fixture_not_model_generated_failure",
                    "validator_activation": "V6 Support AND exact two-sided cluster p<=.05; next round only",
                    "rejected_research_policy": "retain old active; isolated shadow feedback branch permitted",
                    "invalid_research_policy": "no calibration or fake new arm; exact old branch alias",
                    "development_labels_may_train": True, "calibration_labels_never_model_feedback": True,
                    "final_feedback_forbidden": True, "final_policies": list(analysis.POLICIES),
                    "final_candidate_selection": "last valid proposal else common parent, never by final score",
                    "final_candidate_counterfactual_not_approved_deployment": True,
                    "solver_delivery_policy": "same format reminders all arms; strict old parsers; no output repair",
                    "semantic_retries": 0, "final_solver_calls": 2, "public_benchmark": False,
                    "harder_tasks_are_design_intent_not_measured_difficulty": True}
        save(self.root / "protocol.json", protocol)
        save(self.root / "panel.json", self._panel())
        save(self.root / "calibration_manifest.json", {"artifacts": self.controls,
             "blocks": list(range(self.blocks)), "source_task_families_disjoint": True})
        self.verify()
        return protocol

    def verify(self):
        protocol = read(self.root / "protocol.json")
        if protocol["source_hashes"] != self._sources() or protocol["panel_hash"] != digest(self._panel()):
            raise ValueError("Frozen V7 sources or task panel changed")

    def _preflight(self):
        super()._preflight()
        records = []
        for adapter in self.panel["final"]:
            if isinstance(adapter, CodingAdapter):
                value = next(r for r in adapter.evaluate(adapter.task.reference_files, core.initial_rubric(), phase="final")
                             if r["check_id"] == "coding_contract")
                correct = value["verified"] and value["status"] == "pass"
            else:
                value = adapter.evaluate(adapter.task["reference_artifact"], public_only=False)
                correct = value["score"] == 1.0
            if not correct:
                raise ValueError("A frozen final reference failed host oracle preflight")
            records.append({"task_id": identifier(adapter), "assessment": value})
        save(self.root / "private_final_preflight.json", {"records": records, "never_model_feedback": True})

    def _solve(self, api, adapter, skill, history, phase):
        identity = {"kind": "v7_solve", "task": digest(adapter.public_task()), "skill": text(skill),
                    "history": history, "phase": phase, "delivery_reminder": VERSION}
        return self._cached(api, "targets", identity,
            lambda key: adapter.solve(DeliveryAPI(api), text(skill), key=key, repeat=history))

    def _packet(self, adapter, solver, assessments, **kwargs):
        return super()._packet(adapter, solver, assessments, **kwargs)

    def _bind(self, api, rows, solver):
        from .transport import classify_failure
        bound = bind(rows, solver)
        if solver.get("target_ok") is not False:
            return bound
        terminal = json.loads((api.root / "calls" / (solver["request_hashes"][-1] + ".json")).read_text())
        if classify_failure(terminal)["classification"] == "transport_failure":
            return bound
        return [core.make_assessment(**{k: v for k, v in row.items() if k not in {"receipt_hash", "details"}},
                    details={**row["details"], "reason": "response_unavailable", "category": "delivery"})
                if row["status"] == "unknown" else row for row in bound]

    def _propose(self, api, parent, working, packets, history, stage):
        system, user = optimizer_payload(parent, working, packets)
        identity = {"history": history, "stage": stage, "messages": [system, user]}
        response = api.call(system, user, kind="v7_skill", key=digest(identity), max_tokens=2400, repeat=history)
        content = response.get("response", "").strip()
        valid = response.get("ok") is True and 100 <= len(content) <= 5000 and not content.startswith("```")
        proposal = {"content": content, "valid": valid, "request_hash": response["request_hash"]}
        save(self.root / "skill_proposals" / f"h{history}-{stage}.json", {
            "proposal": proposal, "parent_hash": digest(text(parent)), "feedback_hashes": [p["record_hash"] for p in packets]})
        return proposal

    def _source_gate(self, api, state, candidate, history, round_index):
        if not candidate or not candidate["valid"]:
            return {"state": state, "decision": {"action": "Restrict", "reason": "invalid_skill_delivery"}, "pairs": []}
        pairs = []
        for adapter in self.panel["development"]:
            rows = {arm: self._solve(api, adapter, skill, history, "development")
                    for arm, skill in (("baseline", ""), ("current", state["working"]), ("candidate", candidate))}
            rubric = core.initial_rubric()
            pairs.append({"task_id": identifier(adapter), "cluster_id": project(adapter), "domain": "coding",
                "repeat": history, "rubric_hash": rubric["rubric_hash"], "required_check_ids": ["coding_contract"],
                "skill_hashes": {arm: row["skill_hash"] for arm, row in rows.items()},
                **{arm: self._bind(api, adapter.evaluate(row["files"], rubric, phase="development"), row) for arm, row in rows.items()}})
        after = governance.transition_skill(state, candidate, {"source": pairs, "replay": []}, [], round_index)
        return {"state": after, "decision": after["last_transition"], "pairs": pairs}

    def _initial(self, api):
        rubric, branches, packets = core.initial_rubric(), [], []
        self._warm(api, [(a, "", h, "development") for h in range(self.histories)
                        for a in self.panel["development"]], "v7-common-base")
        for history in range(self.histories):
            feedback = []
            for adapter in self.panel["development"]:
                row = self._solve(api, adapter, "", history, "development")
                packet = self._packet(adapter, row, self._bind(api, adapter.evaluate(row["files"], rubric, phase="development"), row), audit=True)
                feedback.append(packet)
            candidate = self._propose(api, "", "", feedback, history, "common-parent")
            selected = candidate if candidate["valid"] else ""
            self._warm(api, [(a, selected, history, "development") for a in self.panel["development"]], f"v7-parent-{history}")
            gate = self._source_gate(api, governance.initial_skill_state(), candidate, history, 0)
            current_packets = []
            for adapter in self.panel["development"]:
                row = self._solve(api, adapter, selected, history, "development")
                current_packets.append(self._packet(adapter, row,
                    self._bind(api, adapter.evaluate(row["files"], rubric, phase="development"), row), audit=True))
            packets.extend(current_packets)
            branches.append({"parent": selected, "state": gate["state"], "initial_gate": gate,
                             "parent_feedback": current_packets})
            save(self.root / "source_initial" / f"h{history}.json", branches[-1])
        fixture_packets = []
        for adapter in self.panel["development"]:
            fixture_packets.append(core.feedback_packet(task_id=identifier(adapter), cluster_id=project(adapter), domain="coding",
                artifact=adapter.task.files, assessments=adapter.evaluate(adapter.task.files, rubric, phase="development"),
                contract=adapter.task.prompt, task_context=adapter.public_task(),
                research_context={"artifact_origin": "predeclared_host_bug_fixture_not_agent_generated",
                                  "audit": {"preselected": True, "selection": "pre_execution_random"}}))
        # Both origin types are explicit. No synthetic artifact is called a model failure.
        save(self.root / "research_inputs.json", {"actual_solver_packets": packets, "host_fixture_packets": fixture_packets})
        # Fixed before outcomes: h0's actual parent trajectories and all three
        # explicitly host-authored fixtures. h1 does not expand Research context.
        return branches, branches[0]["parent_feedback"] + fixture_packets

    def _research_and_screen(self, api, packets):
        # Select whole task/history packets prospectively, not by final or calibration performance.
        views, selected, chars = [], [], 0
        for packet in packets:
            view = research_evidence_view(packet, max_chars=110000)
            size = len(json.dumps(view, ensure_ascii=False))
            if chars + size > 180000:
                raise ValueError("The frozen complete research panel exceeds context capacity")
            views.append(view)
            selected.append(packet)
            chars += size
        save(self.root / "research_selection.json", {"packet_hashes": [p["record_hash"] for p in selected],
             "complete_views": views, "no_calibration_or_final_feedback": True})
        proposal = research.evolve(api, core.initial_rubric(), selected, self.root / "research",
                                   "v7-grounded-fresh-development", True, 0)
        candidate = proposal.get("proposed_rubric")
        if candidate is not None:
            candidate = core.validate_rubric(candidate)
            for before, after in zip(core.initial_rubric()["checks"], candidate["checks"]):
                if before != after and set(before["domains"]) - {"coding"}:
                    raise ValueError("Coding-only study cannot activate a QA patch")
        save(self.root / "validator_candidate_frozen.json", {"rubric": candidate,
             "research_record_hash": proposal["record_hash"], "historical_fallback_used": False})
        calibration = self._calibrate(api, candidate) if candidate else None
        activation = validator_activation(calibration, candidate)
        write_immutable_json(self.root / "validator_activation.json", activation)
        event("next_round_validator_decision", activate=activation["activate_next_round"], reasons=activation["reasons"])
        return candidate, proposal, calibration, activation

    def _feedback_forks(self, api, branches, new_rubric, activation):
        old = core.initial_rubric()
        for history, branch in enumerate(branches):
            channels = ("old_a", "old_b", "new") if new_rubric else ("old_a", "old_b")
            feedback = {channel: [] for channel in channels}
            jobs = [(adapter, channel) for adapter in self.panel["development"] for channel in channels]

            def assess(job):
                adapter, channel = job
                rubric = new_rubric if channel == "new" else old
                solver = self._solve(api, adapter, branch["parent"], history, "development")
                identity = {"task_id": identifier(adapter), "history": history, "channel": channel,
                    "artifact_hash": solver["artifact_hash"], "rubric_hash": rubric["rubric_hash"]}

                def compute(key):
                    search = probe(api, adapter, solver["files"], rubric, key=key, repeat=history)
                    rows = self._bind(api, adapter.evaluate(solver["files"], rubric, phase="development", extra_inputs=search["inputs"]), solver)
                    return {"search": search, "packet": self._packet(adapter, solver, rows)}

                return identifier(adapter), channel, self._cached(api, "feedback_probes", identity, compute)

            evaluated = api.parallel(jobs, assess, f"v7-shared-parent-feedback-{history}")
            if len(evaluated) != len(jobs) or len({(t, c) for t, c, _ in evaluated}) != len(jobs):
                raise ValueError("Feedback scheduler dropped or duplicated a paired position")
            for _, channel, value in sorted(evaluated, key=lambda v: (v[0], v[1])):
                feedback[channel].append(value["packet"])
            arms = {"fixed": feedback["old_a"] + feedback["old_b"]}
            if new_rubric:
                arms["research_shadow"] = feedback["old_a"] + feedback["new"]
            proposals = {}
            for name, packets in arms.items():
                proposals[name] = self._propose(api, branch["parent"], branch["state"]["working"], packets, history, name)
            if not new_rubric:
                proposals["research_shadow"] = proposals["fixed"]
            candidates = {name: p if p["valid"] else branch["parent"] for name, p in proposals.items()}
            self._warm(api, [(a, skill, history, "development") for a in self.panel["development"]
                            for skill in candidates.values()], f"v7-next-source-{history}")
            gates = {name: self._source_gate(api, branch["state"], proposals[name], history, 1) for name in proposals}
            branch.update(candidates=candidates, proposals=proposals, feedback=feedback, gates=gates,
                          selected_arm="research_shadow" if activation["activate_next_round"] else "fixed",
                          shadow_is_counterfactual=not activation["activate_next_round"],
                          fresh_research_available=new_rubric is not None)
            save(self.root / "source_next" / f"h{history}.json", branch)
        save(self.root / "skills_frozen.json", {"histories": branches,
             "all_selection_before_final": True, "approved_deployment_scope": [],
             "approval_not_inferred_from_final_counterfactuals": True})
        return branches

    def _final_v7(self, api, branches):
        frozen, jobs = [], []
        for history, branch in enumerate(branches):
            chosen = branch["candidates"][branch["selected_arm"]]
            for adapter in self.panel["final"]:
                routing = route(contract(adapter), text(chosen))
                policies = {"no_skill": "", "fixed_validator_candidate": branch["candidates"]["fixed"],
                    "research_candidate_shadow": branch["candidates"]["research_shadow"],
                    "gated_validator_candidate": chosen, "gated_validator_routed": chosen if routing["apply"] else ""}
                frozen.append({"history": history, "task_id": identifier(adapter), "routing": routing,
                               "skills": {p: text(s) for p, s in policies.items()}})
                jobs.extend((adapter, s, history, "final") for s in policies.values())
        save(self.root / "final_frozen.json", {"interventions": frozen, "validator_gate_known": True,
             "final_results_known": False, "candidate_evaluation_not_approved_deployment": True})
        event("final_native_evaluation", tasks=len(self.panel["final"]), histories=self.histories)
        self._warm(api, jobs, "v7-final-frozen-interventions")
        indexed = {identifier(a): a for a in self.panel["final"]}
        rows = []
        for intervention in frozen:
            adapter, history = indexed[intervention["task_id"]], intervention["history"]
            for policy, skill in intervention["skills"].items():
                result = self._solve(api, adapter, skill, history, "final")
                artifact = code_artifact(adapter, result)
                if isinstance(adapter, CodingAdapter):
                    native = next(r for r in self._bind(api, adapter.evaluate(artifact, core.initial_rubric(), phase="final"), result)
                                  if r["check_id"] == "coding_contract")
                    score = float(native["status"] == "pass") if native["status"] in {"pass", "fail"} else None
                    cases, error = native["details"].get("case_results", []), native["details"].get("reason") if score is None else None
                else:
                    native = adapter.evaluate(artifact, public_only=False)
                    core.verify(native)
                    score, cases = native["score"], native["case_results"]
                    error = native.get("error", native.get("reason")) if score is None else None
                records = [json.loads((api.root / "calls" / (h + ".json")).read_text()) for h in result["request_hashes"]]
                if score is not None:
                    category = "correct" if score == 1.0 else "semantic_failure"
                elif result.get("target_ok") is False:
                    from .transport import classify_failure
                    terminal = classify_failure(records[-1])["classification"]
                    category = "transport_unavailable" if terminal == "transport_failure" else "response_unavailable"
                    error = category
                elif artifact is None:
                    category = "delivery_unavailable"
                else:
                    category = "native_oracle_unavailable"
                rows.append({"history": history, "repeat": 0, "policy": policy, "task_id": identifier(adapter),
                    "cluster_id": project(adapter), "domain": adapter.domain, "evaluation_group": group(adapter),
                    "score": score, "error": error, "case_results": cases, "outcome_category": category,
                    "fallback": not bool(skill), "skill_hash": result["skill_hash"], "artifact_hash": result["artifact_hash"],
                    "request_hashes": result["request_hashes"], "route": intervention["routing"],
                    "all_solver_stages_api_ok": all(r["ok"] is True for r in records),
                    "any_solver_stage_retried": any(r["http_attempt_count"] > 1 for r in records)})
        expected = {(identifier(a), h, p) for a in self.panel["final"] for h in range(self.histories) for p in analysis.POLICIES}
        summary = analysis.summarize(rows, expected=expected)
        save(self.root / "final_rows.json", {"rows": rows, "final_feedback_used": False})
        write_immutable_json(self.root / "final_summary.json", summary)
        return summary

    def run(self, *, api_factory=None):
        protocol = self.prepare()
        if (self.root / "results.json").exists():
            return read(self.root / "results.json")
        self._preflight()
        event("preflight_complete", calibration_artifacts=len(self.controls))
        if api_factory is None:
            from .transport import make_budgeted_api
            api_factory = make_budgeted_api
        with api_factory(self.repo, self.root / "api", max_calls=self.max_calls, workers=4) as api:
            branches, packets = self._initial(api)
            candidate, proposal, calibration, activation = self._research_and_screen(api, packets)
            branches = self._feedback_forks(api, branches, candidate, activation)
            final = self._final_v7(api, branches)
            ledger = api.ledger()
            pacing_fn = getattr(getattr(api, "api", None), "pacing_audit", None)
            pacing = pacing_fn() if callable(pacing_fn) else {"available": False, "reason": "offline_test_backend"}
            if ledger["unresolved_reservations"]:
                raise ValueError("Unresolved requests cannot be reported complete")
        self.verify()
        returned = Counter(json.loads(p.read_text()).get("returned_model") or "unreported"
                           for p in (self.root / "api/calls").glob("*.json"))
        result = {"status": "complete", "version": VERSION, "protocol_hash": digest(protocol),
                  "ledger": ledger, "pacing": pacing, "returned_models": dict(sorted(returned.items())),
                  "research": proposal, "calibration": calibration, "validator_activation": activation, "final": final,
                  "source_decisions": [{"history": h, "initial": b["initial_gate"]["decision"],
                      "next": {n: g["decision"] for n, g in b["gates"].items()}} for h, b in enumerate(branches)],
                  "calibration_labels_in_optimizer_feedback": False, "final_feedback_used": False,
                  "approved_deployment_scope": [], "engineering_only": True,
                  "public_benchmark_efficacy_established": False}
        save(self.root / "results.json", result)
        return result
