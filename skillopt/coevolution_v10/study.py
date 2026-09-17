"""Frozen SearchQA-to-Coding transfer, paired scope gate, and offline replay.

This is a compatibility-bounded transfer experiment, not a new optimizer or a
canonical MBPP reproduction. Confirmation/final outcomes never train Skills.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import platform
import random
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v9 import learning
from skillopt.coevolution_v9.study import PACING, OfflineAPI, _read, _save, closed_ledger, stable_api
from skillopt.coevolution_v9.study import source_hashes as parent_source_hashes
from skillopt.validator_pilot.api import digest

from . import analysis, data, execution, executor

VERSION = "v10-frozen-searchqa-coding-transfer-v1"
DESIGNS = {
    "smoke": {"confirmation": 2, "final": 4, "seed": 202609141},
    "formal": {"confirmation": 64, "final": 128, "seed": 202609142},
}
PARENT = "outputs/coevolution_v9/glm53_native_searchqa_source_20260913_v1"
PARENT_RESULT_HASH = "43b94ba693d582ab3b49a677b1705844a1a36c312016222b7d0d4900019e81f1"


def source_hashes(repo):
    result = parent_source_hashes(repo)
    paths = list((repo / "skillopt/coevolution_v10").glob("*.py"))
    paths.extend(repo / name for name in (
        "scripts/coevolution_v10.py", "scripts/report_coevolution_v10.py", "scripts/launch_coevolution_v10.py",
        "scripts/audit_coevolution_v9.py", "docs/coevolution-v10-protocol.md",
        "skillopt/validator_artifact_sensitivity.py", "skillopt/validator_pilot/tasks.py",
        "skillopt/coevolution/executor.py",
    ))
    for path in paths:
        result[str(path.relative_to(repo))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(result.items()))


def _safe_run(repo, root):
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("Symlink experiment paths are unsupported")
    root = root.resolve()
    parent = repo / "outputs/coevolution_v10"
    if root == parent or not root.is_relative_to(parent):
        raise ValueError("Use an isolated run beneath outputs/coevolution_v10")
    return root


def load_source(repo):
    from scripts.audit_coevolution_v9 import audit

    parent = repo / PARENT
    verified = audit(parent, repo=repo, require_complete=True)
    if verified["result_hash"] != PARENT_RESULT_HASH or not verified["complete_integrity_audit"]:
        raise ValueError("Expected the exact completed, offline-audited V9 source run")
    freeze = _read(parent / "final_freeze.json")
    deployment = freeze["deployment"]
    if set(deployment) != {"0", "1", "2"} or digest(deployment) != freeze["policies_hash"]:
        raise ValueError("Unexpected frozen parent deployment")
    initial = (repo / "skillopt/envs/searchqa/skills/initial.md").read_text()
    skills = {}
    for h, choices in deployment.items():
        if choices["initial"]["text"] != initial or choices["ours"] != choices["skillopt"]:
            raise ValueError("Parent gates must share their actual selected source Skill")
        chosen = choices["skillopt"]
        if learning.text_hash(chosen["text"]) != chosen["skill_hash"]:
            raise ValueError("Parent Skill bytes do not match the frozen digest")
        skills[h] = {**chosen, "learned": chosen["text"] != initial}
    return {"parent_run": PARENT, "parent_result_hash": verified["result_hash"],
        "parent_freeze_hash": freeze["record_hash"], "parent_audit_hash": verified["record_hash"],
        "source_domain": "searchqa", "initial_text": initial, "skills": skills,
        "no_new_learning_or_research_in_this_run": True}


class PauseRequested(RuntimeError):
    """The current four-request chunk drained; no new work is admitted."""


def _controls(root):
    if any(p.is_symlink() for p in (root / "controls").rglob("*")) or (root / "controls").is_symlink():
        raise ValueError("Control paths cannot contain symlinks")
    requests = {p.stem: _read(p) for p in (root / "controls/requests").glob("*.json")}
    resumed = {p.stem: _read(p) for p in (root / "controls/resumes").glob("*.json")}
    for key, row in requests.items():
        if not key.isdigit() or len(key) != 6 or row.get("sequence") != key or row.get("action") != "pause_after_current_chunk":
            raise ValueError("Malformed immutable pause request")
    for key, row in resumed.items():
        if key not in requests or row.get("request_hash") != requests[key]["record_hash"]:
            raise ValueError("Pause acknowledgement does not match an actual request")
    return requests, resumed


def _control(root, action):
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Control paths cannot contain symlinks")
    root = root.resolve()
    if not (root / "protocol.json").is_file() or (root / "results.json").exists():
        raise ValueError("Pause/resume requires an existing incomplete run")
    directory = root / "controls"
    _controls(root)
    directory.mkdir(exist_ok=True)
    with (directory / ".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        requests, resumed = _controls(root)
        pending = sorted(set(requests) - set(resumed))
        if action == "pause":
            if pending:
                return requests[pending[0]]
            number = f"{len(requests) + 1:06d}"
            return _save(directory / "requests" / (number + ".json"),
                         {"action": "pause_after_current_chunk", "sequence": number})
        if len(pending) != 1:
            raise ValueError("Resume requires exactly one pending pause request")
        number = pending[0]
        return _save(directory / "resumes" / (number + ".json"),
                     {"action": "resume", "request_hash": requests[number]["record_hash"]})


def request_pause(root):
    return _control(root, "pause")


def resume(root):
    return _control(root, "resume")


class Study:
    def __init__(self, repo, root, *, design="smoke", api_factory=None):
        self.repo = Path(repo).resolve()
        self.root = _safe_run(self.repo, root)
        if design not in DESIGNS:
            raise ValueError("Choose the fixed smoke or formal design")
        self.design_name, self.design = design, deepcopy(DESIGNS[design])
        self.counts = {k: self.design[k] for k in ("confirmation", "final")}
        self.histories = [0, 1, 2]
        self.completed = (self.root / "results.json").exists()
        self.api_factory = api_factory or stable_api
        self.used_solves = set()

    def prepare(self):
        if self.completed and any(not (self.root / name).is_file() for name in (
                "protocol.json", "source_anchor.json", "data_manifest.json", "exposure_inventory.json",
                "eligibility_manifest.json", "sandbox_probe.json", "gate.json", "final_freeze.json")):
            raise ValueError("Completed metadata is missing; never reconstruct it")
        anchor = _save(self.root / "source_anchor.json", load_source(self.repo), completed=self.completed)
        self.anchor, self.initial = anchor, anchor["initial_text"]
        self.skills = {int(h): row for h, row in anchor["skills"].items()}
        self.texts = sorted({"", self.initial, *(r["text"] for r in self.skills.values())})
        self.maximum = sum(self.counts.values()) * len(self.texts)
        manifest = data.prepare_manifest(self.repo, self.root, self.counts, self.design["seed"])
        self.manifest = manifest
        self.protocol = _save(self.root / "protocol.json", {
            "version": VERSION, "design_name": self.design_name, "design": self.design,
            "counts": self.counts, "histories": self.histories, "source_anchor_hash": anchor["record_hash"],
            "data_manifest_hash": manifest["record_hash"], "source_hashes": source_hashes(self.repo),
            "max_calls": self.maximum, "unique_skill_texts": len(self.texts), "model": "glm-5.3",
            "workers": 4, "pacing_policy": vars(PACING), "solver_max_tokens": 4096,
            "python_version": sys.version, "python_executable": str(Path(sys.executable).resolve()),
            "operating_system": platform.platform(),
            "gate": {"minimum_clusters": 64, "alpha": 0.10, "maximum_observed_loss_rate": 0.02},
            "confirmation_shared_across_histories": True, "identical_text_task_exact_request_reuse": True,
            "reference_failure_policy": "retain_position_mark_oracle_unknown_no_replacement",
            "candidate_state": "fresh_globals_per_case_pure_function_compatibility_adaptation",
            "model_sees_test_examples": False, "model_sees_reference_or_expected": False,
            "artifact_parser": "frozen_extract_artifact_no_repair_or_resampling",
            "frozen_source_skill_raw_transfer_not_original_skillopt_cross_domain_claim": True,
            "scope_gated_rejection": "empty_no_skill_exact_alias",
            "confirmation_or_final_feedback_to_optimizer": False, "research_validator_active": False,
            "canonical_mbpp_reproduction": False, "scope_population": "predeclared_mbpp_compatible_subset",
            "safety_certificate": False, "old_searchqa_not_fresh_multidomain_final": True,
            "pause": "drain_four_request_chunk_then_checkpoint_exit_75",
        }, completed=self.completed)
        probe_path = self.root / "sandbox_probe.json"
        if probe_path.exists():
            probe = _read(probe_path)
        elif self.completed:
            raise ValueError("Completed isolation probe is missing")
        else:
            probe = _save(probe_path, executor.sandbox_probe())
        if not probe.get("ok") or probe.get("runner_sha256") != executor.RUNNER_SHA256:
            raise ValueError("Native Coding sandbox failed isolation; no candidate execution")
        self.probe = probe
        return self.protocol

    def _check_sources(self):
        if source_hashes(self.repo) != self.protocol["source_hashes"]:
            raise ValueError("Frozen implementation changed; no continuation or final release")

    def _pause_check(self):
        if self.completed:
            return
        requests, resumed = _controls(self.root)
        if set(requests) - set(resumed):
            raise PauseRequested("Paused after draining the current request chunk")

    def _expected(self, split):
        return {str(r["task_id"]): {"cluster_id": r["question_sha256"]}
                for r in self.manifest["splits"][split]}

    def _tasks(self, split, authorization=None):
        rows = data.materialize_split(self.repo, self.manifest, split, final_authorization=authorization)
        expected = self._expected(split)
        if len(rows) != len(expected) or any(expected.get(str(r["task_id"])) !=
                {"cluster_id": r["question_sha256"]} for r in rows):
            raise ValueError("Materialized Coding panel differs from reserved identities")
        return rows

    def _grid(self, api, tasks, split):
        references = {}
        for task in tasks:
            self._pause_check()
            references[str(task["task_id"])] = execution.reference(task, self.root, completed=self.completed)
        jobs = [(task, text) for task in tasks for text in self.texts]
        random.Random(self.design["seed"] + int(digest(split)[:8], 16)).shuffle(jobs)
        indexed = {}

        def solve(pair):
            task, text = pair
            row = execution.solve(api, task, text, split, self.root, self.protocol["record_hash"],
                                  references[str(task["task_id"])], completed=self.completed)
            return (str(task["task_id"]), learning.text_hash(text)), row

        for offset in range(0, len(jobs), 4):
            self._pause_check()
            observed = api.parallel(jobs[offset:offset + 4], solve, "v10-" + split)
            for key, row in observed:
                if key in indexed:
                    raise ValueError("Duplicate solver position")
                indexed[key] = row
                self.used_solves.add(row["request_hash"])
            print(json.dumps({"stage": split, "positions_cached": len(indexed), "planned": len(jobs)}), flush=True)
        if set(indexed) != {(str(t["task_id"]), learning.text_hash(s)) for t in tasks for s in self.texts}:
            raise ValueError("Incomplete actual request grid")
        return indexed, references

    @staticmethod
    def _row(solve, history, policy):
        keys = ("task_id", "cluster_id", "skill_hash", "request_hash", "api_ok", "hard", "soft")
        return {k: solve[k] for k in keys} | {"history": history, "policy": policy}

    def _execute(self, api):
        self._pause_check()
        confirmation = self._tasks("confirmation")
        grid, confirmation_refs = self._grid(api, confirmation, "confirmation")
        raw = {str(h): {"no_skill": "", "initial": self.initial, "raw_transfer": self.skills[h]["text"]}
               for h in self.histories}
        confirmation_rows = [self._row(grid[str(t["task_id"]), learning.text_hash(text)], h, policy)
            for t in confirmation for h in self.histories for policy, text in raw[str(h)].items()]
        _save(self.root / "confirmation_rows.json", {"rows": confirmation_rows,
            "never_optimizer_feedback": True}, completed=self.completed)
        gate = analysis.portfolio_gate(confirmation_rows, expected_tasks=self._expected("confirmation"),
            source_skills={h: {k: self.skills[h][k] for k in ("skill_hash", "learned")} for h in self.histories},
            **self.protocol["gate"])
        _save(self.root / "gate.json", {k: v for k, v in gate.items() if k != "record_hash"}, completed=self.completed)
        deployment = {}
        for h in self.histories:
            choices = {**raw[str(h)], "scope_gated": self.skills[h]["text"] if gate["decisions"][str(h)]["approve"] else ""}
            deployment[str(h)] = {p: {"text": t, "skill_hash": learning.text_hash(t)} for p, t in choices.items()}
        self._pause_check()
        self._check_sources()
        frozen = _save(self.root / "final_freeze.json", {"phase": "final_frozen",
            "protocol_hash": self.protocol["record_hash"], "data_manifest_hash": self.manifest["record_hash"],
            "source_hashes": self.protocol["source_hashes"], "policies_hash": digest(deployment),
            "deployment": deployment, "gate_hash": gate["record_hash"], "final_feedback_forbidden": True},
            completed=self.completed)
        final = self._tasks("final", frozen)
        grid, final_refs = self._grid(api, final, "final")
        rows = [self._row(grid[str(t["task_id"]), deployment[str(h)][p]["skill_hash"]], h, p)
                for t in final for h in self.histories for p in analysis.POLICIES]
        _save(self.root / "final_rows.json", {"rows": rows, "final_freeze_hash": frozen["record_hash"],
              "never_optimizer_feedback": True}, completed=self.completed)
        summary = analysis.summarize_final(rows, expected_tasks=self._expected("final"), histories=self.histories)
        learned = {s["skill_hash"] for s in self.skills.values() if s["learned"]}
        summary["actual_learned_usage"] = {p: sum(r["policy"] == p and r["skill_hash"] in learned for r in rows)
                                             for p in analysis.POLICIES}
        summary["scope_fallback_positions"] = sum(r["policy"] == "scope_gated" and
            r["skill_hash"] == learning.text_hash("") for r in rows)
        learned_histories = [h for h in self.histories if self.skills[h]["learned"]]
        summary["learned_history_only_diagnostic"] = {
            "histories": learned_histories, "not_an_additional_confirmatory_test": True,
            "policy_task_success": {p: sum((r["hard"] or 0) for r in rows
                if r["policy"] == p and r["history"] in learned_histories) / (len(final) * len(learned_histories))
                if learned_histories else None for p in analysis.POLICIES}}
        ledger = closed_ledger(self.root, self.maximum)
        for directory in ("api/calls", "solves"):
            if {p.stem for p in (self.root / directory).glob("*.json")} != self.used_solves:
                raise ValueError("Unexpected or missing actual solver evidence")
        solves = [_read(p) for p in (self.root / "solves").glob("*.json")]
        references = {**{f"confirmation_{k}": v for k, v in confirmation_refs.items()},
                      **{f"final_{k}": v for k, v in final_refs.items()}}
        if {p.stem for p in (self.root / "references").glob("*.json")} != set(references):
            raise ValueError("Unexpected or missing reference evidence")
        execution_ids = {r["execution_id"] for r in references.values()}
        execution_ids.update(r["execution_id"] for r in solves if r["execution_id"] is not None)
        for directory in ("execution_intents", "executions"):
            if {p.stem for p in (self.root / directory).glob("*.json")} != execution_ids:
                raise ValueError("Unclosed or unexpected native execution evidence")
        reference_summary = {}
        for split, refs in (("confirmation", confirmation_refs), ("final", final_refs)):
            reference_summary[split] = {"total": len(refs),
                "valid": sum(r["oracle_valid"] for r in refs.values()),
                "unknown": sum(not r["oracle_valid"] for r in refs.values())}
        categories = Counter(r["outcome_category"] for r in solves)
        self._check_sources()
        return _save(self.root / "results.json", {"version": VERSION, "complete": True,
            "protocol_hash": self.protocol["record_hash"], "source_anchor_hash": self.anchor["record_hash"],
            "data_manifest_hash": self.manifest["record_hash"], "final_freeze_hash": frozen["record_hash"],
            "gate": gate, "summary": summary, "ledger": ledger, "reference_summary": reference_summary,
            "outcome_categories": dict(sorted(categories.items())), "no_new_skill_learning": True,
            "no_research_validator_activation": True, "canonical_mbpp_reproduction": False,
            "smoke_not_effect_evidence": self.design_name == "smoke"}, completed=self.completed)

    def run(self, *, api_factory=None):
        self.prepare()
        if self.completed:
            return self._execute(OfflineAPI(self.root / "api"))
        self._pause_check()
        factory = api_factory or self.api_factory
        try:
            with factory(self.repo, self.root / "api", max_calls=self.maximum, workers=4) as api:
                if api.model != self.protocol["model"]:
                    raise ValueError("Live model differs from preregistration")
                return self._execute(api)
        except PauseRequested:
            ledger = closed_ledger(self.root, self.maximum)
            requests, resumed = _controls(self.root)
            number = sorted(set(requests) - set(resumed))[0]
            _save(self.root / "checkpoints" / ("pause_" + number + ".json"),
                  {"state": "paused_drained", "request_hash": requests[number]["record_hash"],
                   "ledger": ledger, "source_hashes": source_hashes(self.repo)})
            raise
