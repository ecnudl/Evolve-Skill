"""Shadow confirmation of preregistered public-case feedback candidates.

This reuses A's frozen task registration, NOT A's solver calls or outcomes.
The shared holdout is an exploratory extension, not independent replication.
Only proposal repeat_0 is eligible; other proposal repeats cannot rescue an
invalid update. Public evidence and original receipts are replayed before every
candidate is frozen. No Research or deployment authorization is introduced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.run_mechanism_case_feedback import VERSION as PROPOSAL_VERSION
from scripts.run_mechanism_case_feedback import load_source
from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot import api as api_module
from skillopt.validator_pilot.api import CachedAPI, digest

from .mechanism_case_feedback import ARMS, propose
from .mechanism_metrics import summarize
from .mechanism_study import EXPOSURES, _accounting, _execution_health
from .mechanism_tasks import audit_row, deserialize_row
from .mechanism_transport import ConfiguredExecutorPool
from .models import require
from .natural_study import _read, _write
from .panel import checked_path
from .public_revision import _revision_lock
from .rule_skill import RuleSkill, render_skill
from .rule_solver import solve_rule_condition
from .single_round import IMAGE, BoundedCalls, _healthy

VERSION = "shared-holdout-public-case-feedback-confirmation-v2"
INITIAL_HEALTH_POLICY = "completed_response_v1"
CONDITIONS = ("no_skill", "current", *ARMS)
SENSITIVITY = "docs/results/skill-validation-mechanism-sensitivity-plan-20260925.json"
FROZEN_EXECUTION_MODULES = ("mechanism_tasks.py", "curriculum_tasks.py", "public_revision.py",
                            "rule_solver.py", "sandbox.py")


class _ProposalReplay:
    """Return exactly one durable, reserved original response; never call a model."""

    def __init__(self, root, protocol, receipt):
        self.root, self.protocol, self.receipt = root, protocol, receipt
        self.count = 0

    def call(self, system, user, kind, *, repeat=0, max_tokens=2048):
        require(self.count == 0, "Unexpected second proposal replay")
        self.count += 1
        request = self.receipt.get("request")
        key = digest({"protocol": self.protocol["record_hash"], "system": system, "user": user,
                      "kind": kind, "repeat": repeat, "max_tokens": max_tokens})
        require(type(request) is dict and all(request.get(k) == v for k, v in {
            "system": system, "user": user, "kind": kind, "repeat": repeat,
            "max_tokens": max_tokens, "key": key, "service": self.protocol["service"]}.items()),
            "Original proposal request or protocol binding changed")
        require(self.protocol["service"].get("fixture") is True
                or request.get("model") == self.protocol["service"].get("model"),
                "Original model differs from frozen service")
        request_hash = digest(request)
        require(self.receipt.get("request_hash") == request_hash, "Invalid original proposal request hash")
        path = checked_path(self.root / "api/calls" / (request_hash + ".json"))
        require(path.is_file() and path.stat().st_size <= 2_000_000
                and json.loads(path.read_text()) == self.receipt, "Missing or changed durable proposal receipt")
        intent = _read(self.root / "budget/intents" / (request_hash + ".json"))
        require(intent == seal({"request_hash": request_hash, "protocol_hash": self.protocol["record_hash"],
                               "kind": kind, "repeat": repeat}), "Original proposal reservation changed")
        return self.receipt


def _sensitivity(repo, source_protocol, task_ids):
    if source_protocol["service"].get("fixture") is True:
        return seal({"fixture_only": True, "additional_sensitivity_excluded_task_ids": [],
                     "main_panel_filtered": False})
    path = checked_path(repo / SENSITIVITY)
    value = json.loads(path.read_text())
    excluded = value.get("additional_sensitivity_excluded_task_ids")
    require(value.get("kind") == "analysis_plan_not_experimental_result"
            and value.get("primary_confirmation_tasks") == len(task_ids) == 78
            and type(excluded) is list and len(excluded) == len(set(excluded)) == 4
            and set(excluded) <= task_ids, "Original four-task sensitivity plan does not match frozen panel")
    return seal({"plan": value, "plan_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "additional_sensitivity_excluded_task_ids": excluded, "main_panel_filtered": False})


def load_candidates(repo, source, proposals):
    """Read registration/development plus B proposals, never A confirmation results."""
    development, histories, source_index = load_source(source)
    public_registrations = {row["public_task"].content_hash: row for row in development}
    original = _read(source / "protocol.json")
    # The old panel's unrelated provenance fingerprint includes its adapter
    # version. Do not silently rewrite it to today's catalog or wash row hashes.
    # A confirmation snapshot must retain that source adapter unchanged.
    for name in FROZEN_EXECUTION_MODULES:
        require(original.get("source_hashes", {}).get(name)
                == hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest(),
                "Use the original frozen execution/solver adapter " + name + "; do not rebuild A with live code")
    panel = _read(source / "host_only/panel.json")
    frozen = _read(source / "frozen_panel.json")
    qualification = _read(source / "qualification_summary.json")
    require(frozen.get("qualification_hash") == qualification["record_hash"]
            and qualification.get("panel_hash") == panel["manifest"]["record_hash"]
            and qualification.get("status") == "qualified" and qualification.get("formal_eligible") is True,
            "Source panel has no bound successful qualification")
    raw = panel["confirmation"]
    require([digest(row) for row in raw] == panel["manifest"]["row_hashes"]["confirmation"],
            "Confirmation registrations differ from frozen manifest")
    rows = [deserialize_row(row) for row in raw]
    task_ids = {row["task"].contract.task_id for row in rows}
    require(bool(rows) and len(task_ids) == len(rows)
            and all(row["task"].contract.partition == "skill_confirmation" for row in rows),
            "Unique registered confirmation tasks required")
    repeats = original["repeats"]
    require(type(repeats) is int and 1 <= repeats <= 3
            and original.get("parent") == "same_empty_RuleSkill_per_history"
            and original.get("one_public_revision_all_conditions") is True
            and original.get("solver_updater_token_cap") == 2048,
            "Expected original cold-parent, bounded public-revision solver protocol")
    proposal_protocol, summary = _read(proposals / "protocol.json"), _read(proposals / "summary.json")
    require(proposal_protocol.get("version") == PROPOSAL_VERSION
            and proposal_protocol.get("source") == source_index
            and proposal_protocol.get("arms") == list(ARMS)
            and proposal_protocol.get("confirmation_candidate_selection") == "repeat_0_only_no_best_of_n_selection"
            and proposal_protocol.get("service") == original["service"]
            and summary.get("protocol_hash") == proposal_protocol["record_hash"]
            and summary.get("status") == "completed_proposal_diagnostic",
            "Proposal experiment is not bound to this source/selection protocol")
    proposal_repeats = proposal_protocol["repeats"]
    require(type(proposal_repeats) is int and 1 <= proposal_repeats <= 3, "Invalid proposal repeat budget")
    index = {(r["history"], r["arm"], r["repeat"]): r for r in summary["rows"]}
    require(len(index) == len(summary["rows"]) and set(index) == {
        (h, arm, repeat) for h in histories for arm in ARMS for repeat in range(proposal_repeats)},
        "Incomplete or duplicate proposal roster; no replacement candidate allowed")
    learned, records, statuses, changed = {}, {}, {}, {}
    expected_bindings = {h: {"parent_hash": p.content_hash, "feedback_hash": b["record_hash"]}
                         for h, (p, b) in histories.items()}
    require(proposal_protocol.get("parent_and_feedback") == expected_bindings, "Parent/feedback bindings changed")
    for history, (parent, bundle) in histories.items():
        require(not parent.rules, "Source No-Skill parent must actually be empty")
        base = proposals / "histories" / history
        require(_read(base / "source_parent.json")["skill"] == parent.to_dict()
                and _read(base / "source_feedback.json") == bundle, "Imported parent or feedback differs from A")
        details = _read(base / "details.json")
        for entry in details["entries"]:
            registered = public_registrations.get(entry["source"]["public_task_hash"])
            require(registered is not None, "Annex has no source-panel registration")
            for record in entry["roles"].values():
                require(record["task"] == registered["task"].to_dict()
                        and record["public_task"] == registered["public_task"].to_dict()
                        and record["public_wrapper"] == registered["public_wrapper"],
                        "Annex public cases differ from source-panel registration")
        learned[history] = {"no_skill": parent, "current": parent}
        records[history], statuses[history], changed[history] = {}, {}, {}
        for arm in ARMS:
            record = _read(base / "updates" / (arm + "-0.json"))
            replay = _ProposalReplay(proposals, proposal_protocol, record["api_receipt"])
            rebuilt = propose(replay, parent, bundle, details, arm=arm,
                              repeat=int(history[1:]) * proposal_repeats)
            require(record.get("fixture_only") is (original["service"].get("fixture") is True),
                    "Fixture proposal cannot be imported as a real-model candidate")
            expected_row = {"history": history, "arm": arm, "repeat": 0, "status": record["status"],
                "record_hash": record["record_hash"], "api_request_hash": record["api_receipt"]["request_hash"],
                "candidate": record["update"].get("candidate"), "semantic_support_verified": False}
            require(record == rebuilt and index[(history, arm, 0)] == expected_row,
                    "Selected proposal/summary differs from replayed original receipt")
            status = record["status"]
            candidate = RuleSkill.from_dict(record["update"]["candidate"]) if status == "candidate" else parent
            learned[history][arm], records[history][arm] = candidate, record
            statuses[history][arm] = status
            changed[history][arm] = render_skill(candidate) != render_skill(parent)
    sensitivity = _sensitivity(repo, original, task_ids)
    return {"source_index": source_index, "source_protocol": original, "rows": rows,
            "proposal_protocol": proposal_protocol, "proposal_summary_hash": summary["record_hash"],
            "skills": learned, "proposal_records": records, "update_statuses": statuses,
            "behavior_changed": changed, "sensitivity": sensitivity,
            "qualification_hash": qualification["record_hash"]}


def _roster(imported):
    return [{"history": history, "task_id": row["task"].contract.task_id, "family_id": row["family_id"],
             "domain": row["task"].contract.domain, "region": row["region"], "repeat": repeat,
             "condition": condition, "exposure": exposure}
            for history in imported["skills"] for row in imported["rows"]
            for repeat in range(imported["source_protocol"]["repeats"])
            for exposure in EXPOSURES for condition in CONDITIONS]


def _check_reserved_receipts(root, protocol):
    """Completed artifact caches must not hide missing underlying paid receipts."""
    for index in range(protocol["histories"]):
        history = f"h{index}"
        namespace = digest([protocol["record_hash"], history])
        for path in sorted((root / "histories" / history / "budget/intents").glob("*.json")):
            intent = _read(path)
            require(intent.get("request_hash") == path.stem and intent.get("protocol_hash") == namespace,
                    "Confirmation reservation belongs to another history/protocol")
            receipt_path = checked_path(root / "api/calls" / (path.stem + ".json"))
            require(receipt_path.is_file(), "Interrupted API request retained; explicit recovery required")
            require(receipt_path.stat().st_size <= 2_000_000, "Oversized solver receipt")
            receipt = json.loads(receipt_path.read_text())
            request = receipt.get("request")
            require(type(request) is dict and digest(request) == path.stem
                    and receipt.get("request_hash") == path.stem and type(receipt.get("ok")) is bool
                    and request.get("service") == protocol["service"]
                    and request.get("kind") == intent.get("kind")
                    and request.get("repeat") == intent.get("repeat"), "Changed durable solver receipt")
            key = digest({"protocol": namespace, **{k: request[k] for k in
                         ("system", "user", "kind", "repeat", "max_tokens")}})
            require(request.get("key") == key, "Solver receipt belongs to another history namespace")


def run(repo, source, proposals, output, executor, *, workers=2, proxy=None):
    require(type(workers) is int and 1 <= workers <= 4, "Confirmation workers must be 1..4")
    repo, source, proposals, root = (checked_path(Path(p)).resolve() for p in (repo, source, proposals, output))
    require(all(root != p and root not in p.parents and p not in root.parents for p in (source, proposals)),
            "New output must be outside both source experiments")
    with _revision_lock(root / "study_lock"):
        imported = load_candidates(repo, source, proposals)
        original = imported["source_protocol"]
        require(executor.identity == original["executor"] == imported["proposal_protocol"]["executor"],
                "Confirmation executor differs from frozen source/proposal execution identity")
        seed, roster = original["seed"], _roster(imported)
        summarize([], roster, bootstrap_seed=seed, bootstrap_samples=100, candidate_conditions=ARMS)
        limit = 16 * len(imported["rows"]) * original["repeats"]
        protocol = seal({"version": VERSION, "source": imported["source_index"],
            "proposal_protocol_hash": imported["proposal_protocol"]["record_hash"],
            "proposal_summary_hash": imported["proposal_summary_hash"],
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(Path(__file__).parent.glob("*.py"))},
            "api_source_hash": hashlib.sha256(Path(api_module.__file__).read_bytes()).hexdigest(),
            "proposal_importer_source_hash": hashlib.sha256(Path(load_source.__code__.co_filename).read_bytes()).hexdigest(),
            "service": {**original["service"], "initial_health_policy": INITIAL_HEALTH_POLICY},
            "initial_health_change": "Complete matching-model HTTP length/empty failures remain unknown, not network outage",
            "original_solver_payload_unchanged": True, "executor": executor.identity,
            "transport": getattr(executor, "transport_identity", {}), "workers": workers,
            "histories": len(imported["skills"]), "repeats": original["repeats"], "seed": seed,
            "conditions": list(CONDITIONS), "exposures": list(EXPOSURES), "solver_token_cap": 2048,
            "request_limit_per_history": limit, "expected_positions_hash": digest(roster),
            "selection": "repeat_0_only_no_best_of_n_selection", "no_A_solver_cache_reuse": True,
            "all_candidates_frozen_before_any_confirmation": True,
            "shared_holdout_exploratory_extension": True, "independent_replication": False,
            "source_qualification_hash": imported["qualification_hash"],
            "sensitivity_hash": imported["sensitivity"]["record_hash"],
            "research_increment_evaluated": False, "deployment_authorized": False})
        _write(root / "protocol.json", protocol)
        _write(root / "expected_positions.json", seal({"positions": roster}))
        _write(root / "sensitivity_plan.json", imported["sensitivity"])
        frozen = seal({"protocol_hash": protocol["record_hash"], "before_any_confirmation": True,
            "selected_proposal_repeat": 0, "proposal_records": imported["proposal_records"],
            "skills": {h: {c: s.to_dict() for c, s in skills.items()} for h, skills in imported["skills"].items()},
            "update_statuses": imported["update_statuses"], "behavior_changed": imported["behavior_changed"],
            "noncandidate_retains_parent": True, "deployment_authorized": False})
        _write(root / "frozen_candidates.json", frozen)
        common = {"version": VERSION, "protocol_hash": protocol["record_hash"], "freeze_hash": frozen["record_hash"],
            "update_statuses": imported["update_statuses"], "behavior_changed": imported["behavior_changed"],
            "provenance": "engineering_fixture" if original["service"].get("fixture") is True else "real_model_synthetic_tasks",
            "shared_holdout_exploratory_extension": True, "independent_replication": False,
            "research_increment_evaluated": False, "cross_domain_evaluated": False, "deployment_authorized": False}
        _check_reserved_receipts(root, protocol)
        if (root / "summary.json").exists():
            result = _read(root / "summary.json")
            require(result["protocol_hash"] == protocol["record_hash"] and result["freeze_hash"] == frozen["record_hash"],
                    "Summary bound to another protocol or candidate freeze")
            return result
        if not any(v for values in imported["behavior_changed"].values() for v in values.values()):
            result = seal({**common, "status": "no_changed_primary_candidates", "method_effect_evaluated": False,
                "new_behavioral_learning": False, "metrics": None,
                "accounting": {"reserved_logical_requests": 0, "terminal_logical_requests": 0,
                    "http_attempts": 0, "terminal_failures": 0, "terminal_reported_tokens": 0},
                "expected_positions": len(roster), "executed_positions": 0,
                "reason": "Every preregistered primary candidate retains the empty parent; no solver calls needed."})
            _write(root / "summary.json", result)
            return result
        with CachedAPI(repo, root / "api", workers=workers, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy, initial_health_policy=INITIAL_HEALTH_POLICY) as api:
            require(api.service == protocol["service"], "New solver service differs beyond declared health policy")
            calls = {h: BoundedCalls(api, root / "histories" / h / "budget",
                                    digest([protocol["record_hash"], h]), limit) for h in imported["skills"]}
            ping_files = {"ping.py": "def ping():\n    return True\n"}
            ping = executor.run(ping_files, "ping", "ping", [], {})
            verify(ping)
            _healthy(ping)
            require(ping.get("input_hash") == digest({"files": ping_files, "module": "ping", "function": "ping",
                                                     "args": [], "kwargs": {}})
                    and ping.get("status") == "observed" and ping.get("actual") is True,
                    "Isolated executor preflight failed")
            lookup = {row["task"].contract.task_id: row for row in imported["rows"]}

            def confirm(position):
                history, condition, exposure = (position[k] for k in ("history", "condition", "exposure"))
                row, skill = lookup[position["task_id"]], imported["skills"][history][condition]
                pos = root / "histories" / history / "confirmation" / digest(position)
                solver_condition = condition if condition in {"no_skill", "current"} else "candidate"
                solved = solve_rule_condition(row, skill, solver_condition, position["repeat"], calls[history],
                                              executor, pos, exposure=exposure)
                _execution_health(solved)
                audit = audit_row(row, solved["artifact"], executor, pos)
                if audit.get("receipt"):
                    _healthy(audit["receipt"].get("execution"))
                value = seal({**position, "status": audit["status"],
                    "skill_applied": bool(solved["exposure"]["rendering"]["selected_rule_ids"]),
                    "audit_hash": audit["record_hash"], "artifact_hash": solved["artifact"].content_hash,
                    "trajectory_hash": digest([solved["initial_artifact"].source_hash, solved["artifact"].source_hash]),
                    "request_hash": solved["initial_artifact"].source_ref.split(":", 1)[-1],
                    "receipt_hash": solved["artifact"].source_hash, "rule_skill_hash": skill.content_hash,
                    "revision_hash": solved["revision"]["record"]["record_hash"],
                    "update_status": imported["update_statuses"][history].get(condition),
                    "predeclared_near_duplicate": position["task_id"] in imported["sensitivity"]["additional_sensitivity_excluded_task_ids"],
                    "deployment_authorized": False})
                _write(pos / "result.json", value)
                return value

            rows = api.parallel(roster, confirm, "shared-holdout public-case feedback confirmation")
            _write(root / "confirmation_rows.json", seal({"rows": rows}))
            result = seal({**common, "status": "completed_shadow_confirmation",
                "method_effect_evaluated": original["service"].get("fixture") is not True,
                "confirmation_flow_exercised": True,
                "metrics": summarize(rows, roster, bootstrap_seed=seed, candidate_conditions=ARMS),
                "accounting": _accounting(api, calls), "expected_positions": len(roster), "executed_positions": len(rows),
                "limitations": ["Shared original holdout; exploratory extension, not independent replication.",
                    "Raw content utility and conditional abstention are separate, not interchangeable effects.",
                    "No-Skill/Current are cold-parent aliases; repeated receipts are not independent samples.",
                    "All primary failures retain parent; stability repeats never select a better candidate.",
                    "Public-case information is not Research evidence; shadow feedback grants no authority."]})
            _write(root / "summary.json", result)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--ssh-config", type=Path)
    parser.add_argument("--proxy")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(argv)
    executor = ConfiguredExecutorPool(args.remote_repo, workers=args.workers, host=args.host,
        remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.source, args.proposals, args.output, executor, workers=args.workers, proxy=args.proxy)
        print(json.dumps({"status": result["status"], "accounting": result["accounting"]}), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
