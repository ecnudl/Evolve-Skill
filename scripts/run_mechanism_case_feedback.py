"""Compare feedback granularity on frozen real development artifacts only.

Both arms use the same mechanism updater and inline evidence IDs. The enriched
arm adds actual executions of already registered public examples. No hidden
audit, confirmation result, Research, deployment decision, or new solver run is
read or produced. This is a proposal diagnostic, not a generalization result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.checks import CallableTask
from skillopt.skill_validation.mechanism_case_feedback import (
    PromptBudgetExceeded,
    build_request,
    collect_details,
    propose,
)
from skillopt.skill_validation.mechanism_transport import ConfiguredExecutorPool
from skillopt.skill_validation.models import SourceFile, require
from skillopt.skill_validation.natural_study import _read, _write
from skillopt.skill_validation.public_revision import _revision_lock
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.single_round import IMAGE, BoundedCalls
from skillopt.validator_pilot.api import CachedAPI, digest

VERSION = "frozen-real-development-case-feedback-comparison-v1"
ARMS = ("boolean", "case_details")


def load_source(source):
    """Only development registration/feedback; do not enumerate run contents."""
    protocol = _read(source / "protocol.json")
    frozen = _read(source / "frozen_panel.json")
    panel = _read(source / "host_only" / "panel.json")
    manifest = verify(panel["manifest"])
    require(frozen["protocol_hash"] == protocol["record_hash"]
            and frozen["manifest_hash"] == manifest["record_hash"]
            and protocol["manifest_hash"] == manifest["record_hash"]
            and frozen["before_learning"] is True, "Unbound or unfrozen source panel")
    require([digest(row) for row in panel["development"]] == manifest["row_hashes"]["development"],
            "Development registrations differ from the frozen manifest")
    rows = []
    for raw in panel["development"]:
        task = CallableTask.from_dict(raw["task"])
        public_task = CallableTask.from_dict(raw["public_task"])
        wrapper = SourceFile.from_dict(raw["public_wrapper"])
        require(task.contract.partition == "development" and task.contract == public_task.contract,
                "Only matching registered development tasks are allowed")
        rows.append({"task": task, "public_task": public_task, "public_wrapper": wrapper.to_dict()})
    require(len({r["task"].contract.task_id for r in rows}) == len(rows), "Duplicate development task")
    histories = {}
    require(type(protocol["histories"]) is int and 1 <= protocol["histories"] <= 3,
            "Expected one to three frozen histories")
    for index in range(protocol["histories"]):
        name = f"h{index}"
        parent = _read(source / "histories" / name / "parent.json")
        feedback = _read(source / "histories" / name / "feedback.json")
        histories[name] = (RuleSkill.from_dict(parent["skill"]), feedback)
    return rows, histories, {
        "source_protocol_hash": protocol["record_hash"], "source_panel_hash": panel["record_hash"],
        "source_manifest_hash": panel["manifest"]["record_hash"],
        "source_frozen_panel_hash": frozen["record_hash"],
        "development_task_count": len(rows),
        "confirmation_outputs_read": False, "hidden_audit_used": False,
        "source_service": protocol["service"],
    }


def run(repo, source, output, executor, *, repeats=2, workers=2, proxy=None):
    require(type(repeats) is int and 1 <= repeats <= 3, "Proposal repeats must be 1..3")
    require(type(workers) is int and 1 <= workers <= 4, "Workers must be 1..4")
    require(source.resolve() != output.resolve() and source.resolve() not in output.resolve().parents
            and output.resolve() not in source.resolve().parents,
            "Use a new output directory outside the source experiment")
    with _revision_lock(output / "lock"):
        public_rows, histories, source_index = load_source(source)
        with CachedAPI(repo, output / "api", workers=workers, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy) as api:
            protocol = seal({"version": VERSION, "source": source_index,
                "parent_and_feedback": {h: {"parent_hash": p.content_hash, "feedback_hash": f["record_hash"]}
                                        for h, (p, f) in histories.items()},
                "repeats": repeats, "arms": list(ARMS), "workers": workers,
                "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(Path(build_request.__code__.co_filename).parent.glob("*.py"))},
                "script_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "service": api.service, "executor": executor.identity,
                "transport": getattr(executor, "transport_identity", {}),
                "same_final_artifacts_same_selected_details": True,
                "confirmation_candidate_selection": "repeat_0_only_no_best_of_n_selection",
                "additional_proposal_repeats": "stability_diagnostics_not_candidate_selection",
                "not_a_solver_or_skill_confirmation_experiment": True,
                "no_research_increment": True, "deployment_authorized": False})
            _write(output / "protocol.json", protocol)
            calls = BoundedCalls(api, output / "budget", protocol["record_hash"], len(histories) * 2 * repeats)
            details = {}
            for history, (parent, feedback) in histories.items():
                base = output / "histories" / history
                _write(base / "source_feedback.json", feedback)
                _write(base / "source_parent.json", seal({"skill": parent.to_dict()}))
                details[history] = collect_details(parent, feedback, public_rows, executor, base / "public_cases")
                _write(base / "details.json", details[history])
                try:
                    left = build_request(parent, feedback, details[history], arm="boolean")
                    right = build_request(parent, feedback, details[history], arm="case_details")
                except PromptBudgetExceeded as error:
                    result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
                        "status": "pending_prompt_budget", "stage": "before_any_model_call",
                        "history": history, "actual_bytes": error.actual_bytes,
                        "limit_bytes": error.limit_bytes, "accounting": calls.accounting(),
                        "skill_effect_evaluated": False, "deployment_authorized": False})
                    _write(output / "pending_prompt_budget.json", result)
                    return result
                require(left["system"] == right["system"], "Feedback arms need identical updater instructions")
                luser, ruser = json.loads(left["user"]), json.loads(right["user"])
                luser.pop("public_case_annex")
                ruser.pop("public_case_annex")
                require(luser == ruser, "Only the registered-case annex may differ between arms")
                print("DETAILS_READY", history, flush=True)

            # Build every request and check size/identity before any model call.
            jobs = [(h, arm, repeat) for h in histories for repeat in range(repeats) for arm in ARMS]

            def one(job):
                history, arm, repeat = job
                parent, feedback = histories[history]
                # Namespace repetitions by history even if visible text happens
                # to match; repeated generations are not independent tasks.
                request_repeat = int(history[1:]) * repeats + repeat
                record = propose(calls, parent, feedback, details[history], arm=arm, repeat=request_repeat)
                _write(output / "histories" / history / "updates" / f"{arm}-{repeat}.json", record)
                print("PROPOSAL", history, arm, repeat, record["status"], flush=True)
                return {"history": history, "arm": arm, "repeat": repeat,
                        "status": record["status"], "record_hash": record["record_hash"],
                        "api_request_hash": record["api_receipt"]["request_hash"],
                        "candidate": record["update"].get("candidate"),
                        "semantic_support_verified": False}

            rows = api.parallel(jobs, one, "same-artifact public feedback comparison")
            result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
                "status": "completed_proposal_diagnostic", "rows": rows,
                "accounting": calls.accounting(),
                "information_increment": "Registered public examples re-executed, not Research or H",
                "provenance": ("engineering_fixture" if api.service.get("fixture") is True else
                               "real_model_frozen_synthetic_development_replay"),
                "skill_effect_evaluated": False, "cross_domain_evaluated": False,
                "deployment_authorized": False,
                "limitations": ["Same consumed development data, not independent method evaluation.",
                    "A candidate is syntax-valid, not semantically supported or accepted.",
                    "No-update frequency is not a learning-quality measure.",
                    "Same output cap does not equal identical token cost.",
                    "No initial-to-revision trajectory or independent confirmation is evaluated."]})
            _write(output / "summary.json", result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--ssh-config", type=Path)
    parser.add_argument("--proxy")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    executor = ConfiguredExecutorPool(args.remote_repo, workers=args.workers, host=args.host,
        remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.source, args.output, executor,
                     repeats=args.repeats, workers=args.workers, proxy=args.proxy)
        print(json.dumps({"status": result["status"], "accounting": result["accounting"]}), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
