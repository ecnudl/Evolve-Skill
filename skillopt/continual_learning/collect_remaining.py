"""Finish unsubmitted selection positions, diagnostically, without reopening a learner.

Closed unknowns are immutable evidence, not invitations to resample. This new
collection has no updater, gate or selected Skill and cannot authorize S1.
"""
from __future__ import annotations

import argparse
import copy
import json
from contextlib import contextmanager
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_eval.runner import _valid_prediction, _valid_score
from skillopt.validator_pilot.api import CachedAPI, digest

from . import feedback_ablation as ablation
from . import reproposal
from .contracts import sources
from .ledger import LearningPending, Ledger

VERSION = "continual-frozen-selection-collection-v1"


@contextmanager
def _locks(parent):
    with reproposal._parent_lock(parent):
        value = read_json(parent / "protocol.json", sealed=True)
        with reproposal._parent_lock(safe_path(value["parent_root"])):
            yield


def _rows(root, manifest, candidate, authorized, service, *, require_closed=True):
    """Validate positions, actual call identity, and typed scores; never print content."""
    fixture = manifest["model"]["provider"] == "fixture"
    calls, files, cache_paths = {}, {}, set()
    for path in sorted((root / "calls").glob("*.json")):
        row = read_json(path, sealed=True)
        intent = read_json(root / "call_intents" / path.name, sealed=True)
        receipt = row["receipt"]
        require(receipt["request"]["service"] == service
                and receipt["request"]["model"] == manifest["model"]["name"]
                and intent["max_tokens"] == manifest["budget"][row["role"] + "_max_tokens"],
                "Frozen model/service/output budget changed")
        key = (row["role"], intent["logical_id"])
        require(key not in calls, "Duplicate logical call")
        calls[key] = {"receipt": receipt, "intent": intent}
        if not fixture:
            require(not receipt["ok"] or receipt.get("returned_model") == manifest["model"]["name"],
                    "Returned model differs")
            cache = root / "api/calls" / (receipt["request_hash"] + ".json")
            require(read_json(cache) == receipt, "API cache differs")
            files[str(cache)] = reproposal._sha(cache)
            cache_paths.add(str(cache))
    if not fixture:
        require({str(p) for p in (root / "api/calls").glob("*")} == cache_paths, "Unbound API artifacts")
    rows, closed = {}, set()
    for path in (root / "evaluations").glob("*.json"):
        row = read_json(path, sealed=True)
        request = row["request"]
        expected = {"manifest_hash": manifest["record_hash"], "candidate_hash": digest({"skill": candidate}),
                    "task_hash": request["task_hash"], "role": "selection", "repeat": 0}
        require(request == expected and path.stem == digest(request)
                and read_json(root / "evaluation_intents" / path.name, sealed=True) == seal(request)
                and request["task_hash"] in authorized and request["task_hash"] not in rows,
                "Selection task/Skill/intent mismatch")
        _valid_prediction(row["prediction"])
        _valid_score(row["score"])
        if not fixture:
            call = calls.get(("solver", path.stem))
            require(call is not None, "Selection has no Solver receipt")
            if row["prediction"]["status"] == "available":
                require(call["receipt"]["ok"] and call["receipt"]["finish_reason"] == "stop"
                        and backends._code(call["receipt"]["response"]) == row["prediction"]["output"],
                        "Prediction not bound to its actual Solver response")
        rows[request["task_hash"]] = row
        closed.add(path.name)
    intent_paths = {p.name for p in (root / "evaluation_intents").glob("*.json")}
    require(closed <= intent_paths, "Missing evaluation intent")
    if require_closed:
        require(closed == intent_paths, "Started-but-unclosed selection position")
    return rows, calls, files


def _collect(parent, source):
    value, result = (read_json(parent / name, sealed=True) for name in ("protocol.json", "result.json"))
    old = value["manifest"]
    require(value["version"] == ablation.VERSION and value["arm"] in ablation.POLICIES
            and result["version"] == ablation.VERSION and result["protocol_hash"] == value["record_hash"]
            and result["status"] == "pending" and result["reason"] == "evaluation_unknown"
            and result["selected_skill"] == "" and "gate_action" not in result
            and "candidate_score" not in result and result["selection_planned"] == 64,
            "Only terminal unknown-interrupted shadow selection is supported")
    candidate = ablation.parse_skill(result["candidate_skill"])
    require(candidate != "", "No nonempty frozen candidate")
    inherited = reproposal._collect(safe_path(value["parent_root"]), safe_path(value["parent_source_root"]))
    # Reconstruct the original protocol, substituting ONLY its frozen source
    # identities; adding this independent collector must not rewrite the parent.
    expected = ablation._protocol(safe_path(value["parent_root"]), safe_path(value["parent_source_root"]),
                                 inherited, value["arm"])
    expected.pop("record_hash")
    expected["current_sources"] = value["current_sources"]
    expected["manifest"].pop("record_hash")
    expected["manifest"]["source_identity"] = value["current_sources"]
    expected["manifest"] = seal(expected["manifest"])
    require(value == seal(expected), "Original shadow protocol changed")
    files = dict(inherited["files"])
    for relative, expected_hash in {**value["current_sources"], **value["native_sources"]}.items():
        path = safe_path(source / "skillopt" / relative)
        require(path.is_relative_to(source / "skillopt") and reproposal._sha(path) == expected_hash,
                "Frozen shadow source changed")
        files[str(path)] = expected_hash
    current = sources()
    # Deploy the original frozen source plus this new module. In particular the
    # dynamically loaded native worker and score validation must not drift.
    require(all(current.get(name) == h for name, h in value["current_sources"].items()),
            "Execution or inheritance code changed")
    require(read_json(parent / "panel.json") == inherited["panel"], "Frozen panel changed")
    ledger = Ledger(parent, old, None)
    costs = ledger.snapshot()
    require(costs == result["new_costs"] and costs["usage_complete"] and costs["unclosed_calls"] == 0
            and costs["reflection_calls"] == 1 and result["artifacts"] == ablation._artifacts(parent, ledger),
            "Parent calls, costs or artifacts incomplete")
    require(read_json(parent / "started.json", sealed=True) == seal({"protocol_hash": value["record_hash"]})
            and read_json(parent / "model_service.json", sealed=True) == seal(inherited["service"]),
            "Parent start/service identity differs")
    roster = [digest(t) for t in inherited["selection"]]
    rows, calls, cache_files = _rows(parent, old, candidate, roster, inherited["service"])
    require(0 < len(rows) < 64 and set(rows) == set(roster[:len(rows)])
            and rows[roster[len(rows) - 1]]["score"]["status"] == "unknown"
            and all(rows[h]["score"]["status"] != "unknown" for h in roster[:len(rows) - 1])
            and result["selection_closed"] == len(rows) and result["selection_unknown"] == 1
            and result["selection_not_closed"] == 64 - len(rows), "Not an intact first-unknown selection prefix")
    reflection = calls.get(("reflection", "shadow-proposal:" + value["arm"]))
    require(reflection is not None and reflection["receipt"]["ok"]
            and reflection["receipt"]["finish_reason"] == "stop"
            and ablation.parse_skill(reflection["receipt"]["response"]) == candidate
            and digest({k: reflection["intent"][k] for k in ("system", "user")}) == value["prompt_hash"],
            "Candidate not bound to the actual frozen proposal")
    require(read_json(parent / "steps/proposal.json", sealed=True) == seal({"protocol_hash": value["record_hash"],
            "request_hash": reflection["receipt"]["request_hash"], "candidate_skill": candidate}),
            "Frozen proposal artifact changed")
    require(old["model"]["provider"] == "fixture" or costs["solver_calls"] == len(rows),
            "Unbound or missing Solver calls")
    files.update(cache_files)
    files.update({str(parent / name): h for name, h in result["artifacts"].items()})
    for name in ("protocol.json", "result.json", "panel.json"):
        files[str(parent / name)] = reproposal._sha(parent / name)
    return {"inherited": inherited, "protocol": value, "result": result, "rows": rows, "candidate": candidate,
            "files": files, "costs": costs, "remaining": inherited["selection"][len(rows):]}


def _protocol(parent, source, prior):
    old = prior["protocol"]["manifest"]
    new = copy.deepcopy({k: v for k, v in old.items() if k != "record_hash"})
    count = len(prior["remaining"])
    new.update(version=VERSION, method="diagnostic_remaining_" + prior["protocol"]["arm"],
               source_identity=sources(), authorized_tasks={digest(t): "selection" for t in prior["remaining"]},
               feedback_authorization="diagnostic_only_no_skill_update")
    budget = new["budget"]
    budget.update(max_reflection_calls=0, max_api_calls=count, max_metric_calls=count, max_iterations=0)
    budget["max_reported_tokens"] -= prior["costs"]["reported_tokens_known_subtotal"]
    require(budget["max_reported_tokens"] > 0 and old["budget"]["max_api_calls"]
            - prior["costs"]["logical_calls"] >= count, "No remaining original collection budget")
    return seal({"version": VERSION, "parent_root": str(parent), "parent_source_root": str(source),
                 "parent_protocol_hash": prior["protocol"]["record_hash"],
                 "parent_result_hash": prior["result"]["record_hash"], "original_files": prior["files"],
                 "manifest": seal(new), "candidate_skill": prior["candidate"],
                 "candidate_hash": digest({"skill": prior["candidate"]}),
                 "remaining_task_hashes": [digest(t) for t in prior["remaining"]],
                 "closed_prefix_hash": digest(prior["rows"]), "original_gate_status": "pending",
                 "diagnostic_only": True, "deployment_authorized": False, "scope_authorized": False,
                 "s1_authorized": False, "optimizer_resumed": False, "resume_supported": False})


def prepare(parent_output, parent_source_root, output):
    parent, source, root = map(safe_path, (parent_output, parent_source_root, output))
    require(not root.exists() and not root.is_relative_to(parent) and not root.is_relative_to(source),
            "Use a new independent collection directory")
    with _locks(parent):
        prior = _collect(parent, source)
        value = _protocol(parent, source, prior)
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
        write_json(root / "panel.json", prior["inherited"]["panel"])
    return {"status": "prepared_not_launched", "protocol_hash": value["record_hash"],
            "remaining_positions": len(prior["remaining"]), "model_calls": 0, "s1_authorized": False}


def _load(root):
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION, "Unsupported collection version")
    prior = _collect(safe_path(value["parent_root"]), safe_path(value["parent_source_root"]))
    require(value == _protocol(safe_path(value["parent_root"]), safe_path(value["parent_source_root"]), prior)
            and read_json(root / "panel.json") == prior["inherited"]["panel"], "Collection identity changed")
    return value, prior


def _summary(prior, rows):
    combined = {**prior["rows"], **rows}
    counts = {"pass": 0, "fail": 0, "unknown": 0, "missing": 0}
    pairs = {"wins": 0, "losses": 0, "ties": 0, "unknown": 0, "missing": 0}
    for task in prior["inherited"]["selection"]:
        h = digest(task)
        score = combined[h]["score"] if h in combined else {"status": "missing"}
        status = score["status"]
        counts[status] += 1
        if status in {"unknown", "missing"}:
            pairs[status] += 1
        else:
            base = prior["inherited"]["selection_rows"][h]["score"]["score"]
            pairs["wins" if score["score"] > base else "losses" if score["score"] < base else "ties"] += 1
    return {"selection_planned": 64, "selection_closed": len(combined), "selection_counts": counts,
            "known_denominator": counts["pass"] + counts["fail"], "paired_to_same_parent": pairs,
            "accuracy_bounds": {"lower": counts["pass"] / 64,
                                "upper": (counts["pass"] + counts["unknown"] + counts["missing"]) / 64},
            "evidence_references": {h: {"record_hash": row["record_hash"],
                                       "source": "original_arm" if h in prior["rows"] else "new_collection"}
                                    for h, row in combined.items()}}


def _execute(root, manifest, ledger, task, candidate, *, fixture_evaluate=None):
    """Exactly one never-submitted authorized position, with existing Solver/scorer."""
    require(task["partition"] == "development"
            and manifest["authorized_tasks"].get(digest(task)) == "selection", "Unauthorized diagnostic task")
    require(ledger.snapshot()["usage_complete"], "Cannot continue after incomplete usage")
    request = {"manifest_hash": manifest["record_hash"], "candidate_hash": digest({"skill": candidate}),
               "task_hash": digest(task), "role": "selection", "repeat": 0}
    key = digest(request)
    intent = root / "evaluation_intents" / (key + ".json")
    require(not intent.exists(), "Never resample a started position")
    write_json(intent, seal(request))
    if fixture_evaluate is not None:
        require(manifest["model"]["provider"] == "fixture", "Natural collection cannot inject evaluations")
        prediction, score = fixture_evaluate(task, candidate)
    else:
        call = lambda system, user: ledger.call(  # noqa: E731
            "solver", key, system, user, manifest["budget"]["solver_max_tokens"])
        prediction = backends.solve("bigcodebench", task["public"], candidate, call, runtime=manifest["runtime"])
        score = backends.score("bigcodebench", task["public"], task["private"], prediction, runtime=manifest["runtime"])
    write_json(root / "evaluations" / (key + ".json"),
               seal({"request": request, "prediction": _valid_prediction(prediction), "score": _valid_score(score)}))


def _audit_collection(root, manifest, candidate, authorized, service):
    """Failure-path audit never adopts orphan caches or invents zero cost.

    A malformed/unbound receipt can follow a paid request. Preserve the files
    and a Pending terminal even when strict validation cannot establish totals.
    Invalid new position evidence is conservatively uncounted, not semantic fail.
    """
    issues, rows, costs = {}, {}, None
    try:
        costs = Ledger(root, manifest, None).snapshot()
    except Exception as exc:
        issues["cost_validation_error"] = type(exc).__name__
    try:
        rows, _, _ = _rows(root, manifest, candidate, authorized, service, require_closed=False)
    except Exception as exc:
        issues["position_validation_error"] = type(exc).__name__
    return costs, rows, issues


def _artifacts(root, ledger):
    # Also bind orphan/malformed API caches: they remain evidence of a possibly
    # paid request even when no valid Ledger receipt can adopt them.
    return {**ablation._artifacts(root, ledger),
            **{str(p.relative_to(root)): reproposal._sha(p) for p in sorted((root / "api/calls").glob("*"))
               if p.is_file()}}


def run(output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    root = safe_path(output)
    initial = read_json(root / "protocol.json", sealed=True)
    with output_lock(root), _locks(safe_path(initial["parent_root"])):
        value, prior = _load(root)
        manifest, service = value["manifest"], prior["inherited"]["service"]
        fixture = manifest["model"]["provider"] == "fixture"
        require(fixture == (fixture_api is not None and fixture_evaluate is not None)
                and (fixture or (fixture_api is None and fixture_evaluate is None)), "Fixture callback boundary")
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            ledger = Ledger(root, manifest, None)
            costs, rows, issues = _audit_collection(root, manifest, prior["candidate"],
                                                    value["remaining_task_hashes"], service)
            require(result["protocol_hash"] == value["record_hash"] and result["collection_costs"] == costs
                    and result["evidence_validation_issues"] == issues
                    and all(result[k] == v for k, v in _summary(prior, rows).items())
                    and result["artifacts"] == _artifacts(root, ledger), "Collection evidence changed")
            return result
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_collection_no_automatic_resume",
                    "model_calls_submitted": 0, "s1_authorized": False, "original_gate_status": "pending"}
        if not fixture:
            require(repo is not None and backends.readiness("bigcodebench", manifest["runtime"])["status"] == "ready",
                    "Native runtime and credential repository required")
        write_json(root / "started.json", seal({"protocol_hash": value["record_hash"]}))
        api, reason = fixture_api, "all_original_unsubmitted_positions_collected"
        try:
            if not fixture:
                model = manifest["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                                reasoning_effort=model["reasoning_effort"], **model["transport"],
                                **({"proxy": model["proxy"]} if "proxy" in model else {}))
            require(api.service == service, "Collection model service changed")
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, manifest, api)
            for task in prior["remaining"]:
                _execute(root, manifest, ledger, task, prior["candidate"], fixture_evaluate=fixture_evaluate)
                # A closed unknown is retained; it does not abort diagnostic coverage.
        except Exception as exc:
            reason = str(exc) if isinstance(exc, LearningPending) else type(exc).__name__
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, manifest, None)
        costs, rows, issues = _audit_collection(root, manifest, prior["candidate"],
                                                value["remaining_task_hashes"], service)
        complete = len(rows) == len(prior["remaining"]) and costs is not None and costs["usage_complete"] and not issues
        result = seal({"version": VERSION, "protocol_hash": value["record_hash"],
                       "status": "completed" if complete else "pending", "reason": reason,
                       "candidate_hash": value["candidate_hash"], **_summary(prior, rows),
                       "evidence_validation_issues": issues,
                       "collection_call_intents_on_disk": len(list((root / "call_intents").glob("*.json"))),
                       "collection_evaluation_intents_on_disk": len(list((root / "evaluation_intents").glob("*.json"))),
                       "collection_costs": costs, "original_arm_costs": prior["costs"],
                       "collection_total_cost_known": costs is not None and costs["usage_complete"]
                           and costs["retry_inclusive_usage_known"] and not issues,
                       "collection_cost_scope": "validated_ledger_only_orphan_or_unclosed_costs_may_be_unknown",
                       "shared_base_costs": prior["inherited"]["costs"],
                       "shared_base_costs_count_once_across_arms": True,
                       "evidence_kind": prior["protocol"]["evidence_kind"],
                       "feedback_source": "existing_host_development_audit_not_new_research",
                       "artifacts": _artifacts(root, ledger), "original_gate_status": "pending",
                       "diagnostic_only": True, "deployment_authorized": False, "scope_authorized": False,
                       "s1_authorized": False, "optimizer_resumed": False, "resume_supported": False})
        write_json(terminal, result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check", "run"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--parent-output")
    parser.add_argument("--parent-source-root")
    parser.add_argument("--repo")
    args = parser.parse_args()
    if args.command == "prepare":
        require(args.parent_output and args.parent_source_root, "Parent output and frozen source required")
        result = prepare(args.parent_output, args.parent_source_root, args.output)
    elif args.command == "check":
        root = safe_path(args.output)
        initial = read_json(root / "protocol.json", sealed=True)
        with output_lock(root), _locks(safe_path(initial["parent_root"])):
            value, prior = _load(root)
        result = {"status": "ready_not_launched", "protocol_hash": value["record_hash"],
                  "remaining_positions": len(prior["remaining"]), "model_calls": 0}
    else:
        record = run(args.output, repo=args.repo)
        result = {k: record[k] for k in ("status", "reason", "s1_authorized")}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
