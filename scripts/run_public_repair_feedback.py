"""Preflight or propose from frozen PUBLIC development repair trajectories.

Default/preflight performs only local receipt replay: no API, SSH, execution,
Research or confirmation read. --run-proposals is a separate explicit action.
Existing A/B/C outputs remain read-only. Repeat zero is primary; other repeats
measure proposal stability, never best-of-N candidate selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.run_mechanism_case_feedback import load_source
from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation.models import require
from skillopt.skill_validation.natural_study import _read, _write
from skillopt.skill_validation.public_repair_feedback import (
    ARMS,
    PromptBudgetExceeded,
    build_details,
    build_request,
    propose,
)
from skillopt.skill_validation.public_repair_feedback import (
    VERSION as DETAILS_VERSION,
)
from skillopt.skill_validation.public_revision import _revision_lock
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot import api as api_module
from skillopt.validator_pilot.api import CachedAPI, digest

VERSION = "frozen-public-repair-proposal-diagnostic-v1"


def load_sources(source, history, public_rows, feedback):
    """Read exact registered development paths, never enumerate confirmation."""
    source_protocol = _read(source / "protocol.json")
    revision_implementation = source_protocol["source_hashes"]["public_revision.py"]
    lookup = {r["public_task"].content_hash: r for r in public_rows}
    from skillopt.skill_validation.checks import CallableTask
    from skillopt.skill_validation.models import ArtifactRecord
    sources = []
    for entry in feedback["entries"]:
        checker = CallableTask.from_dict(entry["task"])
        require(checker.content_hash in lookup, "Feedback checker missing from frozen public registration")
        row = lookup[checker.content_hash]
        for raw in entry["artifacts"]:
            final = ArtifactRecord.from_dict(raw)
            position = source / "histories" / history / "development" / digest(
                [row["task"].content_hash, final.repeat, final.condition])
            result = _read(position / "rule_result.json")
            draft_hash = result["initial_artifact_hash"]
            revision = _read(position / "public_revision" / draft_hash / "record.json")
            require(revision["request"]["implementation_hash"] == revision_implementation,
                    "Revision source differs from the frozen original implementation")
            sources.append({"public_row": {"task": row["task"].to_dict(),
                "public_task": row["public_task"].to_dict(), "public_wrapper": row["public_wrapper"]},
                "exposure": _read(position / "rule_exposure.json"), "result": result,
                "draft": _read(position / "artifacts" / (draft_hash + ".json")),
                "initial": _read(position / "public_initial" / (draft_hash + ".json")),
                "revision": revision})
    return sources


def run(repo, source, output, *, detail_limit=6, repeats=2, workers=2, proxy=None, run_proposals=False):
    require(type(repeats) is int and 1 <= repeats <= 2, "At most two proposal repeats are allowed")
    require(type(workers) is int and 1 <= workers <= 4, "Workers must be 1..4")
    require(type(run_proposals) is bool, "Explicit proposal-run flag required")
    require(source.resolve() != output.resolve() and source.resolve() not in output.resolve().parents
            and output.resolve() not in source.resolve().parents, "Use an independent output directory")
    with _revision_lock(output / "run_lock"):
        public_rows, histories, source_index = load_source(source)
        expected_service = {**source_index["source_service"], "initial_health_policy": "completed_response_v1"}
        limit = len(histories) * len(ARMS) * repeats
        require(limit <= 12, "Proposal budget must not exceed twelve logical calls")
        configuration = seal({"version": VERSION, "details_version": DETAILS_VERSION,
            "source": source_index, "parents_and_feedback": {
                h: {"parent_hash": p.content_hash, "feedback_hash": f["record_hash"]}
                for h, (p, f) in histories.items()},
            "detail_limit_pairs": detail_limit, "repeats": repeats, "workers": workers,
            "arms": list(ARMS), "max_tokens": 2048, "max_model_calls": limit,
            "primary_repeat": 0, "other_repeats": "proposal_stability_only_no_best_of_n",
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(Path(build_request.__code__.co_filename).parent.glob("*.py"))},
            "script_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_loader_hash": hashlib.sha256(Path(load_source.__code__.co_filename).read_bytes()).hexdigest(),
            "api_source_hash": hashlib.sha256(Path(api_module.__file__).read_bytes()).hexdigest(),
            "initial_health_policy": "completed_response_v1",
            "expected_proposal_service": expected_service,
            "selection_before_any_proposal": True, "hidden_audit_used": False, "research_calls": 0,
            "execution_calls": 0, "deployment_authorized": False})
        _write(output / "protocol.json", configuration)
        details, preflight_rows = {}, []
        for history, (parent, feedback) in histories.items():
            sources = load_sources(source, history, public_rows, feedback)
            details[history] = build_details(parent, feedback, sources, detail_limit=detail_limit)
            base = output / "histories" / history
            _write(base / "source_parent.json", seal({"skill": parent.to_dict()}))
            _write(base / "source_feedback.json", feedback)
            _write(base / "details.json", details[history])
            try:
                requests = {arm: build_request(parent, feedback, details[history], arm=arm) for arm in ARMS}
            except PromptBudgetExceeded as error:
                pending = seal({"version": VERSION, "protocol_hash": configuration["record_hash"],
                    "status": "pending_prompt_budget", "history": history,
                    "actual_bytes": error.actual_bytes, "limit_bytes": error.limit_bytes,
                    "model_calls": 0, "stage": "before_any_model_call", "deployment_authorized": False})
                _write(output / "pending_preflight.json", pending)
                return pending
            left, right = (requests[a] for a in ARMS)
            require(left["system"] == right["system"] and left["evidence_catalog"] == right["evidence_catalog"],
                    "Repair arms must share updater instructions and evidence IDs")
            lu, ru = json.loads(left["user"]), json.loads(right["user"])
            require(lu.pop("public_repair_annex") == [], "Control must not contain draft detail")
            ru.pop("public_repair_annex")
            require(lu == ru, "Only the registered repair annex may differ")
            for arm, request in requests.items():
                _write(base / "requests" / (arm + ".json"), request)
            coverage = details[history]["coverage"]
            preflight_rows.append({"history": history, "details_hash": details[history]["record_hash"],
                "prompt_bytes": {a: r["prompt_bytes"] for a, r in requests.items()},
                "task_count": coverage["task_count"], "position_count": coverage["position_count"],
                "distinct_request_trajectories": coverage["distinct_request_trajectories"],
                "transitions": coverage["deduplicated_transition_counts"],
                "selected_pairs": coverage["selected_pairs"]})
        preflight = seal({"version": VERSION, "protocol_hash": configuration["record_hash"],
            "status": "preflight_complete", "histories": preflight_rows, "model_calls": 0,
            "execution_calls": 0, "research_calls": 0, "hidden_audit_used": False,
            "proposed_call_limit": limit, "method_effect_evaluated": False, "deployment_authorized": False})
        _write(output / "preflight.json", preflight)
        if not run_proposals:
            return preflight
        # No provider construction or credential read is reachable in preflight.
        with CachedAPI(repo, output / "api", workers=workers, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy, initial_health_policy="completed_response_v1") as api:
            require(api.service == expected_service,
                    "Proposal API service must match the frozen source service plus only initial_health_policy")
            protocol = seal({"configuration_hash": configuration["record_hash"], "service": api.service,
                             "preflight_hash": preflight["record_hash"]})
            _write(output / "api_protocol.json", protocol)
            calls = BoundedCalls(api, output / "budget", protocol["record_hash"], limit)
            jobs = [(h, arm, repeat) for h in histories for repeat in range(repeats)
                    for arm in (ARMS if (int(h[1:]) + repeat) % 2 == 0 else tuple(reversed(ARMS)))]
            _write(output / "jobs.json", seal({"jobs": jobs, "primary_repeat": 0}))

            def one(job):
                h, arm, repeat = job
                parent, feedback = histories[h]
                value = propose(calls, parent, feedback, details[h], arm=arm,
                                repeat=int(h[1:]) * repeats + repeat)
                _write(output / "histories" / h / "updates" / f"{arm}-{repeat}.json", value)
                return {"history": h, "arm": arm, "repeat": repeat, "status": value["status"],
                    "record_hash": value["record_hash"], "api_request_hash": value["api_receipt"]["request_hash"],
                    "candidate": None if value["update"] is None else value["update"].get("candidate")}

            rows = api.parallel(jobs, one, "public repair proposal diagnostic")
            result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"],
                "status": "completed_proposal_diagnostic", "rows": rows, "accounting": calls.accounting(),
                "primary_repeat": 0, "best_of_n_selection": False,
                "provenance": "engineering_fixture" if api.service.get("fixture") is True else
                              "real_model_consumed_synthetic_public_development_replay",
                "research_calls": 0, "execution_calls": 0, "hidden_audit_used": False,
                "method_effect_evaluated": False, "deployment_authorized": False,
                "limitations": ["Both arms already know the complete public repair summary.",
                    "Selected detail is purposive and not an independent performance sample.",
                    "A syntactically valid proposal is not a supported, useful or accepted Skill.",
                    "No new solver, calibration, confirmation or cross-domain result is produced.",
                    "Equal output caps do not imply equal input-token or total cost."]})
            _write(output / "summary.json", result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preflight", action="store_true", help="Default: offline replay only")
    modes.add_argument("--run-proposals", action="store_true", help="Explicitly permit up to twelve API proposals")
    parser.add_argument("--detail-limit", type=int, default=6)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--proxy")
    args = parser.parse_args()
    result = run(args.repo, args.source, args.output, detail_limit=args.detail_limit, repeats=args.repeats,
                 workers=args.workers, proxy=args.proxy, run_proposals=args.run_proposals)
    print(json.dumps({k: result[k] for k in ("status", "histories", "model_calls", "accounting") if k in result}))


if __name__ == "__main__":
    main()
