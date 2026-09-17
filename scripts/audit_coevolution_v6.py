"""Read-only V6 receipt audit; no API calls, generated-code execution, or writes.

Hashes detect inconsistent local records, not a malicious host. Recorded native
outcomes are not re-executed. The report is an integrity/analysis audit, never an
independent benchmark, human review, or authorization to activate a Skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v3.executor import RepoTask  # noqa: E402
from skillopt.coevolution_v3.validator import _bounded_input  # noqa: E402
from skillopt.coevolution_v5 import core, governance, research  # noqa: E402
from skillopt.coevolution_v5.adapters import CodingAdapter  # noqa: E402
from skillopt.coevolution_v5.evaluation import _check_metrics, summarize_final  # noqa: E402
from skillopt.coevolution_v5.experiment import text  # noqa: E402
from skillopt.coevolution_v6.analysis import summarize_repairs, summarize_transfer  # noqa: E402
from skillopt.coevolution_v6.experiment import VERSION, contract  # noqa: E402
from skillopt.coevolution_v6.native import NativeAdapter  # noqa: E402
from skillopt.coevolution_v6.routing import route  # noqa: E402
from skillopt.coevolution_v6.statistics import summarize_validator  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

POLICIES = {"old_single": ["old_a"], "new_single": ["new"],
            "old_double": ["old_a", "old_b"], "portfolio": ["old_a", "new"]}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            _require(key not in value, "Duplicate JSON key in audit input")
            value[key] = item
        return value
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite audit input")))


def _read(path):
    record = _json(path)
    core.verify(record)
    return {key: value for key, value in record.items() if key != "record_hash"}


def _safe(repo, relative):
    _require(isinstance(relative, str) and not Path(relative).is_absolute(), "Relative source path required")
    path = (repo / relative).resolve()
    _require(path.is_relative_to(repo) and path.is_file()
             and not any(part == ".git" or part.startswith(".env") for part in path.parts),
             "Frozen source unavailable, credential path, or outside repository")
    return path


def _returned_model(receipt):
    value = receipt.get("returned_model")
    _require(value is None or isinstance(value, str), "Returned model must be a string or unreported")
    return value or "unreported"


def _receipts(run, protocol, complete):
    budget_path = run / "api/budget_protocol.json"
    if not budget_path.exists():
        _require(not complete, "Complete run lacks API budget protocol")
        return {}, {"available": False}
    budget = _json(budget_path)
    _require(budget["model"] == protocol["model"] and budget["workers"] == protocol["workers"]
             and budget["max_logical_calls"] == protocol["max_calls"], "API budget differs from protocol")
    reservations = {}
    for path in sorted((run / "api/budget_reservations").glob("*.json")):
        item = _json(path)
        _require(item.get("request_hash") == path.stem, "Reservation filename/hash mismatch")
        reservations[path.stem] = item
    calls = {}
    for path in sorted((run / "api/calls").glob("*.json")):
        item = _json(path)
        request = item.get("request", {})
        _require(item.get("request_hash") == path.stem == digest(request), "API request hash mismatch")
        _require(path.stem in reservations and reservations[path.stem].get("kind") == request.get("kind"),
                 "API request lacks its matching prior reservation")
        _require(request.get("model") == protocol["model"]
                 and digest(request.get("service")) == budget["service_sha256"], "API service/model mismatch")
        _require(type(item.get("ok")) is bool and type(item.get("http_attempt_count")) is int
                 and 1 <= item["http_attempt_count"] <= 3, "Invalid transport receipt accounting")
        calls[path.stem] = item
    unresolved = sorted(set(reservations) - set(calls))
    _require(len(reservations) <= protocol["max_calls"], "Logical budget exceeded")
    _require(not complete or not unresolved, "Complete run has unresolved API reservations")
    rows = list(calls.values())
    ledger = {"max_logical_calls": protocol["max_calls"], "logical_requests_reserved": len(reservations),
              "cached_logical_calls": len(calls), "successful_calls": sum(row["ok"] for row in rows),
              "terminal_errors": sum(not row["ok"] for row in rows), "unresolved_reservations": unresolved,
              "http_attempts_from_cached_records": sum(row["http_attempt_count"] for row in rows),
              "max_planned_http_attempts": protocol["max_calls"] * 3,
              "by_kind": dict(sorted(Counter(row["request"]["kind"] for row in rows).items())),
              **{key: sum(row.get("usage", {}).get(key, 0) or 0 for row in rows)
                 for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
              "missing_usage_calls": sum(not row.get("usage") for row in rows),
              "usage_not_invoice": True, "unreturned_or_interrupted_attempt_usage_unknown": True}
    return calls, {"available": True, "ledger": ledger,
                   "returned_models": dict(Counter(_returned_model(row) for row in rows))}


def _metadata(value, calls):
    record = calls.get(value.get("request_hash"))
    _require(record is not None, "Evidence lacks a persisted API receipt")
    if "api_receipt_hash" in value:
        _require(value["api_receipt_hash"] == digest(record), "API receipt content hash mismatch")
    for key in ("usage", "http_attempt_count", "finish_reason"):
        if key in value:
            _require(value[key] == record.get(key, {} if key == "usage" else None), "API metadata mismatch")
    return record


def _cached(run, namespace):
    found = {}
    for path in sorted((run / namespace).glob("*.json")):
        row = _read(path)
        _require(path.stem == digest({"namespace": namespace, "identity": row["identity"]}),
                 "Cached evidence identity/hash mismatch")
        found[path.stem] = row
    return found


def _targets(run, calls, adapters):
    indexed = {}
    by_public = {digest(a.public_task()): a for a in adapters.values()}
    for key, wrapped in _cached(run, "targets").items():
        identity, result = wrapped["identity"], wrapped["result"]
        if "record_hash" in result:
            core.verify(result)
        adapter = by_public.get(identity.get("task"))
        _require(adapter is not None and identity.get("kind") == "solve", "Solver public-task identity mismatch")
        task_id = adapter.task.id if isinstance(adapter, CodingAdapter) else adapter.task["id"]
        artifact = result.get("files") if isinstance(adapter, CodingAdapter) else result.get("artifact")
        _require(result.get("artifact_hash") == digest(artifact)
                 and result.get("skill_hash") == digest(identity.get("skill")), "Solver artifact/Skill hash mismatch")
        _require(result.get("public_task_hash") == identity["task"] and result.get("repeat") == identity["history"],
                 "Solver public task or history mismatch")
        hashes = result.get("request_hashes")
        _require(isinstance(hashes, list) and len(hashes) == 2 and len(set(hashes)) == 2, "Solver requires two distinct receipts")
        for number, request_hash in enumerate(hashes):
            _require(request_hash in calls, "Solver API request missing")
            request = calls[request_hash]["request"]
            visible = json.loads(request["user"])
            _require(visible.get("task") == adapter.public_task() and visible.get("skill") == identity["skill"]
                     and request["repeat"] == identity["history"], "Solver request intervention/task mismatch")
            expected = ("v5_coding_" if isinstance(adapter, CodingAdapter) else "v6_native_") + (
                "generate" if number == 0 else "revision")
            _require(request["kind"] == expected, "Solver request stage mismatch")
        position = (task_id, identity["history"], identity["phase"], result["skill_hash"])
        _require(position not in indexed, "Duplicate solver intervention")
        indexed[position] = result
    return indexed


def _skill_audit(run, protocol, calls, targets, panel, complete):
    rounds, count = protocol["source_rounds"], protocol["histories"]
    states = [governance.initial_skill_state() for _ in range(count)]
    decisions, valid, packets, unique_working = [], [], {}, set()
    candidates, latest_histories = [None] * count, None
    proposals = {}
    for receipt in calls.values():
        request = receipt["request"]
        if request["kind"] != "v6_skill":
            continue
        matching = [(h, r) for h in range(count) for r in range(rounds)
                    if request["key"] == digest({"history": h, "round": r,
                                                 "messages": [request["system"], request["user"]]})]
        _require(len(matching) == 1 and matching[0] not in proposals, "Optimizer history/round request identity mismatch")
        proposals[matching[0]] = receipt
    development = {r["task"]["id"]: r for r in panel["development"]}
    for round_index in range(rounds):
        state_path = run / "source_states" / f"r{round_index}.json"
        if not state_path.exists():
            _require(not complete, "Complete run lacks source round state")
            continue
        histories = _read(state_path)["histories"]
        latest_histories = histories
        _require(len(histories) == count, "Source history count mismatch")
        for history, branch in enumerate(histories):
            core.verify(branch["state"], "state_hash")
            proposal = proposals.get((history, round_index))
            _require(proposal is not None, "Source state lacks its optimizer API receipt")
            content = proposal.get("response", "").strip()
            delivery_valid = proposal["ok"] and 100 <= len(content) <= 5000 and not content.startswith("```")
            path = run / "source_decisions" / f"h{history}-r{round_index}.json"
            _require(path.exists() == bool(delivery_valid), "Source decision presence differs from actual proposal validity")
            if path.exists():
                decision = _read(path)
                candidate, pairs = decision["candidate"], decision["pairs"]
                proposal = calls.get(candidate.get("request_hash"))
                _require(proposal is not None and proposal["request"]["kind"] == "v6_skill"
                         and proposal["ok"] and proposal["response"].strip() == text(candidate), "Skill proposal API binding mismatch")
                _require(proposal == proposals[history, round_index], "Skill proposal belongs to another source round")
                _require(candidate.get("valid") is True and 100 <= len(text(candidate)) <= 5000
                         and not text(candidate).startswith("```"), "Candidate validity differs from frozen rule")
                _require(decision["before"] == states[history], "Skill evolution state chain changed")
                _require(len(pairs) == len(development) and {p["task_id"] for p in pairs} == set(development),
                         "Source comparison omits a frozen development task")
                for pair in pairs:
                    for arm in ("baseline", "current", "candidate"):
                        solver = targets.get((pair["task_id"], history, "development", pair["skill_hashes"][arm]))
                        _require(solver is not None, "Source comparison lacks actual solver artifact")
                        for assessment in pair[arm]:
                            _require(assessment["artifact_hash"] == solver["artifact_hash"]
                                     and assessment["details"].get("solver_request_hashes") == solver["request_hashes"],
                                     "Source assessment not bound to its actual solver")
                after = governance.transition_skill(states[history], candidate, {"source": pairs, "replay": []}, [], round_index)
                _require(after == decision["after"] == branch["state"], "Recomputed Skill decision differs")
                decisions.append({"history": history, "round": round_index, **after["last_transition"]})
                valid.append((history, round_index, digest(text(candidate))))
                candidates[history] = candidate
                if after["working"] != states[history]["working"]:
                    unique_working.add(digest(text(after["working"])))
            else:
                _require(branch["state"] == states[history], "Invalid delivery silently changed Skill state")
                decisions.append({"history": history, "round": round_index, "action": "Restrict",
                                  "reason": "invalid_skill_delivery"})
            states[history] = branch["state"]
            _require(branch["candidate"] == candidates[history], "Selected candidate is not the last valid source proposal")
            for packet in branch["feedback"]:
                core.verify(packet)
                core.development_only(packet)
                _require(packet["task_id"] in development and packet["artifact_hash"] == digest(packet["artifact"]),
                         "Feedback artifact or development panel mismatch")
                for assessment in packet["observations"]:
                    core.verify(assessment, "receipt_hash")
                    _require(all(assessment[k] == packet[k] for k in
                             ("task_id", "domain", "phase", "artifact_hash", "rubric_hash")), "Feedback observation binding mismatch")
                packets[packet["record_hash"]] = packet
    freeze = _read(run / "skills_frozen.json") if (run / "skills_frozen.json").exists() else None
    if freeze:
        _require(freeze["decisions"] == decisions and freeze["histories"] == latest_histories,
                 "Frozen Skills differ from source history/decisions")
    _require(not complete or freeze is not None, "Complete run lacks frozen Skills")
    return {"histories": count, "valid_proposals": len(valid), "unique_valid_skill_contents": len({v[2] for v in valid}),
            "working_commit_events": sum(d.get("local_passed", False) for d in decisions),
            "unique_changed_working_contents": len(unique_working),
            "approved_nonempty_histories": sum(bool(text(state["approved"])) for state in states),
            "decision_actions": dict(Counter(d["action"] for d in decisions)),
            "unique_retained_feedback": len(packets)}, freeze, decisions, packets


def _research_audit(run, protocol, calls, packets, complete):
    selection_path = run / "research_selection.json"
    if not selection_path.exists():
        _require(not complete, "Complete run lacks research selection")
        return {"available": False}
    selection = _read(selection_path)
    _require(set(selection["all_feedback"]) == set(packets)
             and set(selection["model_visible"]) <= set(packets)
             and len(set(selection["model_visible"])) == len(selection["model_visible"]),
             "Research selection differs from retained development evidence")
    paths = list((run / "research").rglob("proposal.json"))
    if not paths:
        _require(not complete, "Complete run lacks research proposal")
        return {"available": True, "complete": False}
    _require(len(paths) == 1, "V6 expects exactly one pre-calibration research proposal")
    path, proposal = paths[0], _read(paths[0])
    identity = proposal["identity"]
    _require(path.parent.name == digest(identity) and _json(path.parent / "identity.json") == identity,
             "Research proposal identity mismatch")
    _require(identity["packets_hash"] == digest([packets[h] for h in selection["model_visible"]])
             and identity["rubric_hash"] == core.initial_rubric()["rubric_hash"], "Research input feedback/Rubric mismatch")
    for stage in proposal["stages"]:
        sealed = _json(path.parent / (stage["stage"] + ".json"))
        core.verify(sealed)
        receipt = calls.get(stage["request_hash"])
        _require(receipt is not None and sealed["api_receipt"] == receipt
                 and stage["receipt_hash"] == digest(receipt) and stage["stage_hash"] == sealed["record_hash"]
                 and sealed["identity_hash"] == digest(identity), "Research stage API/source seal mismatch")
    source = _read(path.parent / "source_receipt.json")
    _require(source["sources"] == proposal["research"]["sources"] and source["identity_hash"] == digest(identity),
             "Research source receipt differs from proposal")
    research._verify_sources(source["sources"], path.parent)  # Snapshot bytes only; no fetch.
    proposed = core.apply_rubric_patch(core.initial_rubric(), proposal["revision_patch"]) if proposal["revision_patch"] is not None else None
    _require(proposed == proposal["proposed_rubric"], "Research patch does not reconstruct proposed Rubric")
    reason = "fresh_development_research"
    if proposed is not None and any(a != b and set(a["domains"]) - {"coding"}
                                   for a, b in zip(core.initial_rubric()["checks"], proposed["checks"])):
        proposed = None
        reason = "unsupported_qa_patch_fallback_to_frozen_predecessor"
    if proposed is None:
        proposed = protocol["fallback_proposal"]["rubric"]
        if reason == "fresh_development_research":
            reason = "invalid_fresh_proposal_fallback_to_frozen_predecessor"
    candidate_path = run / "validator_candidate_frozen.json"
    if candidate_path.exists():
        _require(_read(candidate_path) == {"rubric": proposed, "selection_reason": reason,
                  "proposal_hash": digest(proposal), "no_calibration_labels_seen": True},
                 "Frozen validator differs from predeclared research/fallback selection")
    else:
        _require(not complete, "Complete research lacks validator freeze")
    return {"available": True, "complete": candidate_path.exists(), "selection_reason": reason,
            "proposal_hash": digest(proposal), "model_visible_packets": len(selection["model_visible"]),
            "external_documents_verified": sum(bool(s.get("ok")) for s in source["sources"]),
            "recorded_provenance_quotes": len(proposal["research"]["quotes"]),
            "semantic_support": "pending_not_established_by_byte_provenance"}


def _calibration(run, protocol, manifest, calls, adapters, complete):
    controls = governance._artifacts(manifest)
    indexed = {r["artifact_id"]: r for r in controls}
    _require(manifest["blocks"] == list(range(protocol["blocks"])), "Calibration blocks differ from protocol")
    for row in controls:
        task = adapters[row["task_id"]].task
        _require(row["artifact_hash"] == digest(row["files"]) and row["cluster_id"] == task.cluster_id,
                 "Calibration manifest artifact/project mismatch")
        name = row["artifact_id"].removeprefix(task.id + ":")
        expected = task.reference_files if name == "reference" else task.metadata["controls"].get(name)
        _require(row["files"] == expected and row["truth"] == ("good" if name in {"reference", "equivalent"} else "bad"),
                 "Calibration oracle label/control differs from frozen task")
    expected_ids = {a.task.id + ":" + name for a in adapters.values() if isinstance(a, CodingAdapter)
                    and a.task.split in {"calibration", "promotion"}
                    for name in ("reference", "equivalent", "semantic_mutant", "preservation_mutant")}
    _require(set(indexed) == expected_ids, "Calibration manifest omits a frozen artifact")
    preflight_path = run / "private_preflight.json"
    if preflight_path.exists():
        preflight = _read(preflight_path)
        _require(preflight.get("never_model_feedback") is True and len(preflight["calibration"]) == len(controls),
                 "Private preflight incomplete or feedback declaration changed")
        seen = set()
        for row in preflight["calibration"]:
            artifact, assessment = indexed[row["artifact_id"]], row["assessment"]
            core.verify(assessment, "receipt_hash")
            _require(row["artifact_id"] not in seen and assessment["artifact_hash"] == artifact["artifact_hash"]
                     and assessment["status"] == ("pass" if artifact["truth"] == "good" else "fail")
                     and assessment["verified"], "Private native truth receipt mismatch")
            seen.add(row["artifact_id"])
    else:
        _require(not complete, "Complete run lacks private oracle preflight")
    candidate_path = run / "validator_candidate_frozen.json"
    if not candidate_path.exists():
        _require(not complete, "Complete run lacks frozen validator")
        return {"available": False}
    selection = _read(candidate_path)
    candidate = core.validate_rubric(selection["rubric"])
    _require(selection["no_calibration_labels_seen"] is True, "Validator selection feedback declaration changed")
    expected = {(r["artifact_id"], block, c) for r in controls for block in manifest["blocks"]
                for c in ("old_a", "old_b", "new")}
    schedule_path = run / "calibration_schedule.json"
    if schedule_path.exists():
        jobs = _read(schedule_path)["jobs"]
        _require(len(jobs) == len(expected) and {tuple(j) for j in jobs} == expected, "Calibration schedule grid mismatch")
    elif complete:
        raise ValueError("Complete run lacks calibration schedule")
    components, derived = {}, {}
    for key, wrapper in _cached(run, "calibration_calls").items():
        identity, component = wrapper["identity"], wrapper["result"]
        position = (identity["artifact_id"], identity["block"], identity["channel"])
        _require(position in expected and position not in components, "Calibration component grid mismatch")
        artifact = indexed[identity["artifact_id"]]
        rubric = candidate if identity["channel"] == "new" else core.initial_rubric()
        _require(identity["artifact_hash"] == artifact["artifact_hash"] and identity["rubric_hash"] == rubric["rubric_hash"],
                 "Calibration component artifact/Rubric mismatch")
        search = component["search"]
        core.verify(search)
        request = _metadata(search, calls)["request"]
        probe_identity = search["identity"]
        adapter = adapters[artifact["task_id"]]
        _require(probe_identity["artifact_hash"] == artifact["artifact_hash"]
                 and probe_identity["rubric_hash"] == rubric["rubric_hash"] and probe_identity["key"] == key
                 and probe_identity["repeat"] == identity["block"]
                 and probe_identity["task_hash"] == digest(adapter.public_task()), "Probe frozen identity mismatch")
        visible = json.loads(request["user"])
        expected_public = adapter.public_task()
        expected_public["files"] = artifact["files"]
        _require(request["kind"] == "v5_validator_probe" and request["repeat"] == identity["block"]
                 and request["key"] == digest(probe_identity) and visible == {
                     "task": expected_public, "current_code": artifact["files"], "rubric": rubric},
                 "Calibration probe prompt differs from public artifact/Rubric")
        actual = calls[search["request_hash"]]
        parsed_inputs, parse_error = [], None
        if not actual["ok"]:
            parse_error = "terminal_api_result"
        else:
            try:
                parsed = core.strict_object(actual.get("response", ""))
                _require(set(parsed) == {"inputs"} and isinstance(parsed["inputs"], list)
                         and 1 <= len(parsed["inputs"]) <= 4, "Invalid returned probe input count")
                seen = set()
                for value in parsed["inputs"]:
                    _bounded_input(value)
                    _require(isinstance(value, dict) and adapter._input_valid(value) is True
                             and digest(value) not in seen, "Invalid or duplicate returned probe input")
                    seen.add(digest(value))
                parsed_inputs = parsed["inputs"]
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                parse_error = "invalid_probe_schema_or_input"
        _require(search["inputs"] == parsed_inputs and search["error"] == parse_error
                 and search["schema_valid"] == (parse_error is None), "Probe execution inputs differ from actual model response")
        derived[position] = governance._promotion_assessments(component, artifact, rubric["rubric_hash"])
        probe_row = next(r for r in component["assessments"] if r["check_id"] == "coding_probe")
        receipts = probe_row["details"].get("receipts", [])
        if probe_row["verified"]:
            _require([r["input"] for r in receipts] == search["inputs"], "Probe inputs differ from executed receipts")
        components[position] = component
    rows_path = run / "calibration_rows.json"
    if not rows_path.exists():
        _require(not complete, "Complete run lacks calibration rows")
        return {"available": True, "complete": False, "component_calls": len(components), "expected_component_calls": len(expected)}
    _require(set(components) == expected, "Calibration rows exist without full component grid")
    record = _read(rows_path)
    _require(record["labels_never_optimizer_feedback"] is True, "Calibration feedback declaration changed")
    recomputed = []
    for artifact in controls:
        for block in manifest["blocks"]:
            for policy, channels in POLICIES.items():
                positions = [(artifact["artifact_id"], block, c) for c in channels]
                parts = [components[p] for p in positions]
                outcomes = [derived[p] for p in positions]
                outcome = "detected" if "detected" in outcomes else (
                    "not_detected" if all(v == "not_detected" for v in outcomes) else "unknown")
                recomputed.append({k: artifact[k] for k in ("artifact_id", "artifact_hash", "task_id", "cluster_id", "truth")}
                    | {"block": block, "policy": policy, "outcome": outcome,
                       "input_count": len({digest(i) for p in parts for i in p["search"]["inputs"]}),
                       "probe_request_hashes": [p["search"]["request_hash"] for p in parts],
                       "component_hashes": [digest(p) for p in parts], "public_only": True})
    _require(record["rows"] == recomputed, "Calibration rows differ from recomputed sealed component outcomes")
    summary = summarize_validator(recomputed, expected_artifacts={r["artifact_id"]: {
        "cluster_id": r["cluster_id"], "truth": r["truth"]} for r in controls}, expected_blocks=manifest["blocks"])
    _require(summary == _read(run / "calibration_summary.json"), "Calibration statistics differ from recomputation")
    costs = {}
    for policy in POLICIES:
        hashes = {h for r in recomputed if r["policy"] == policy for h in r["probe_request_hashes"]}
        receipts = [calls[h] for h in hashes]
        costs[policy] = {"unique_logical_calls": len(hashes),
            "http_attempts": sum(r["http_attempt_count"] for r in receipts),
            **{k: sum(r.get("usage", {}).get(k, 0) or 0 for r in receipts)
               for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "missing_usage_calls": sum(not r.get("usage") for r in receipts),
            "returned_models": dict(Counter(_returned_model(r) for r in receipts))}
    return {"available": True, "complete": True, "summary": summary, "costs_per_policy": costs,
            "primary_equal_logical_calls": costs["old_double"]["unique_logical_calls"] == costs["portfolio"]["unique_logical_calls"],
            "primary_equal_tokens": costs["old_double"]["total_tokens"] == costs["portfolio"]["total_tokens"],
            "costs_overlap_shared_old_a_not_additive": True, "usage_not_invoice": True}


def _final(run, protocol, panel, adapters, freeze, targets, complete):
    path = run / "final_frozen.json"
    if not path.exists():
        _require(not complete, "Complete run lacks final freeze")
        return {"available": False}
    final_freeze = _read(path)
    _require(freeze is not None and final_freeze["histories"] == freeze["histories"], "Final Skill freeze changed")
    routes = {(r["history"], r["task_id"]): r["decision"] for r in final_freeze["routes"]}
    expected = {(h, r["task"]["id"]) for h in range(protocol["histories"]) for r in panel["final"]}
    _require(len(routes) == len(final_freeze["routes"]) == len(expected) and set(routes) == expected,
             "Final route grid differs from frozen panel")
    for (history, task_id), value in routes.items():
        _require(value == route(contract(adapters[task_id]), text(freeze["histories"][history]["candidate"])),
                 "Final route differs from explicit public contract")
    row_path = run / "final_rows.json"
    if not row_path.exists():
        _require(not complete, "Complete run lacks final rows")
        return {"available": True, "complete": False}
    record = _read(row_path)
    rows = record["rows"]
    expected_rows = {(h, t, p) for h, t in expected for p in protocol["final_policies"]}
    _require(len(rows) == len(expected_rows) and {(r["history"], r["task_id"], r["policy"]) for r in rows} == expected_rows,
             "Final observation grid differs from frozen panel")
    _require(record["final_feedback_used"] is False, "Final feedback declaration changed")
    for row in rows:
        history, task_id = row["history"], row["task_id"]
        adapter = adapters[task_id]
        task = adapter.task.to_dict() if isinstance(adapter, CodingAdapter) else adapter.task
        metadata = task.get("metadata", {})
        _require(row["domain"] == adapter.domain and row["cluster_id"] == task["cluster_id"]
                 and row["evaluation_group"] == metadata.get("evaluation_group", metadata.get("group")),
                 "Final task/domain/cluster identity mismatch")
        candidate = text(freeze["histories"][history]["candidate"])
        chosen = candidate if row["policy"] == "always_candidate" or (
            row["policy"] == "mechanism_routed_candidate" and routes[history, task_id]["apply"]) else ""
        solver = targets.get((task_id, history, "final", digest(chosen)))
        _require(solver is not None and row["route"] == routes[history, task_id]
                 and row["fallback"] == (not bool(chosen)) and row["skill_hash"] == digest(chosen)
                 and all(row[k] == solver[k] for k in ("artifact_hash", "request_hashes")),
                 "Final intervention lacks exact frozen solver/route receipt")
    summary = {"native": summarize_final(rows), "cluster_analysis": summarize_transfer(rows)}
    return {"available": True, "complete": True, "summary": summary,
            "task_instances": len(panel["final"]), "project_clusters": len({r["task"]["cluster_id"] for r in panel["final"]}),
            "learning_histories": protocol["histories"], "logical_rows": len(rows),
            "unique_trajectory_receipts": len({tuple(r["request_hashes"]) for r in rows}),
            "routed_candidate_positions": sum(value["apply"] for value in routes.values()),
            "route_positions": len(routes), "approved_deployment_positions": 0,
            "counterfactual_not_approved_deployment": True}


def _repairs(run, protocol, panel, calls, complete):
    path = run / "repair_results.json"
    if not path.exists():
        _require(not complete, "Complete run lacks repair comparison")
        return {"available": False}
    record = _read(path)
    rows = record["rows"]
    tasks = {r["task"]["id"]: r["task"] for r in panel["development"]}
    expected = {(t, h) for t in tasks for h in range(protocol["histories"])}
    _require(record["no_update"] is True and len(rows) == len(expected)
             and {(r["task_id"], r["history"]) for r in rows} == expected, "Repair grid/no-update declaration changed")
    for row in rows:
        result, task = row["result"], tasks[row["task_id"]]
        core.verify(result)
        identity = result["identity"]
        _require(identity["artifact_hash"] == digest(task["files"]) and identity["task_hash"] == digest(task)
                 and row["cluster_id"] == task["cluster_id"]
                 and row["artifact_origin"] == "predeclared_buggy_task_fixture_not_agent_generated_failure",
                 "Repair fixture provenance mismatch")
        checked = [(result["initial_assessments"], identity["artifact_hash"], result["initial_metrics"])]
        for arm in ("score_only", "structured_evidence"):
            value = result["arms"][arm]
            request = _metadata(value, calls)["request"]
            _require(request["kind"] == "v5_feedback_repair" and request["key"] == digest({**identity, "arm": arm}),
                     "Repair API arm identity mismatch")
            _require(value["artifact_hash"] == digest(value["files"]), "Repair artifact hash mismatch")
            checked.append((value["assessments"], value["artifact_hash"], value["metrics"]))
            before, after = result["initial_metrics"]["checks"], value["metrics"]["checks"]
            passed = {k for k, v in before.items() if v is True}
            _require(value["new_passing_check_losses"] == sorted(k for k in passed if after.get(k) is False)
                     and value["unavailable_preservation_checks"] == sorted(k for k in passed if k not in after),
                     "Repair regression accounting mismatch")
        for assessments, artifact_hash, metrics in checked:
            for assessment in assessments:
                core.verify(assessment, "receipt_hash")
                _require(assessment["artifact_hash"] == artifact_hash and assessment["task_id"] == row["task_id"]
                         and assessment["phase"] == "development" and assessment["rubric_hash"] == identity["rubric_hash"],
                         "Repair assessment identity/phase mismatch")
            _require(metrics == _check_metrics(assessments, probe_required=identity["check_inputs_hash"] != digest([])),
                     "Repair metrics differ from sealed assessments")
    return {"available": True, "summary": summarize_repairs(rows), "rows": rows}


def _verify_recovery(result, run, repo, calls):
    _require(not (run / "results.json").exists(), "Recovery requires absence of original runtime results")
    recovery = result.get("reporting_recovery")
    _require(isinstance(recovery, dict), "Recovered index requires explicit reporting recovery provenance")
    required = {"version": "v6-reporting-index-recovery-v1", "reason": "null_returned_model_counter_serialization",
                "original_results_present": False, "original_runtime_completed": False,
                "runtime_completion_success": False, "source_results_file": "recovered_results.json",
                "no_api_calls": True, "no_rescoring": True, "original_evidence_unchanged": True}
    _require(all((recovery.get(k) is v if type(v) is bool else recovery.get(k) == v) for k, v in required.items()),
             "Recovery provenance declarations mismatch")
    _require(recovery.get("runtime_failure_confirmation") == {"kind": "operator_attestation", "confirmed": True,
             "independently_verified_process_exit": False}, "Recovery lacks explicit, honestly scoped failure attestation")
    for name, relative in (("exporter", "scripts/finalize_coevolution_v6.py"),
                           ("auditor", "scripts/audit_coevolution_v6.py")):
        _require(recovery.get(name + "_source") == relative
                 and hashlib.sha256(_safe(repo, relative).read_bytes()).hexdigest() == recovery.get(name + "_source_sha256"),
                 "Recovery exporter/auditor source provenance mismatch")
    records = list(calls.values())
    _require(any("returned_model" in row and row["returned_model"] is None and not row["ok"] for row in records)
             and any(isinstance(row.get("returned_model"), str) and row["returned_model"] for row in records),
             "This recovery requires actual mixed null/string returned-model receipts")
    roots = ("protocol.json", "panel.json", "skills_frozen.json", "validator_candidate_frozen.json",
             "research_selection.json", "calibration_manifest.json", "calibration_schedule.json",
             "calibration_rows.json", "calibration_summary.json", "private_preflight.json",
             "repair_results.json", "final_frozen.json", "final_rows.json", "api/budget_protocol.json")
    paths = {run / relative for relative in roots}
    for relative in ("api/calls", "api/budget_reservations", "source_states", "source_decisions", "targets",
                     "probes", "calibration_calls", "research", "feedback_utility", "human_review"):
        directory = run / relative
        _require(not directory.is_symlink(), "Symlink evidence directory forbidden")
        children = directory.glob("*.json") if relative.startswith("api/") else directory.rglob("*")
        paths.update(p for p in children if (p.is_file() or p.is_symlink()) and not p.name.endswith(".lock"))
    _require(all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(run)
                 and not p.name.startswith(".pending-")
                 and not any(q.is_symlink() for q in p.parents if q != run and q.is_relative_to(run)) for p in paths),
             "Recovery source evidence is unavailable or symlinked")
    expected = {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    _require(recovery.get("source_evidence_manifest") == expected, "Recovery source evidence manifest incomplete or changed")


def audit(run, repo=REPO, require_complete=True, *, require_evidence_complete=False):
    """Validate retained evidence and recompute summaries, without changing it.

    A complete evidence set can be checked before a reporting index exists via
    require_complete=False, require_evidence_complete=True. This never claims
    that the original runtime successfully serialized its final report.
    """
    run, repo = Path(run).resolve(), Path(repo).resolve()
    _require(run.is_dir() and run.is_relative_to(repo), "Existing run inside repository required")
    protocol, panel = _read(run / "protocol.json"), _read(run / "panel.json")
    _require(protocol.get("version") == VERSION and protocol["panel_hash"] == digest(panel), "Protocol/panel identity mismatch")
    _require(bool(protocol.get("source_hashes")), "Frozen source manifest required")
    for relative, expected in protocol["source_hashes"].items():
        _require(hashlib.sha256(_safe(repo, relative).read_bytes()).hexdigest() == expected, "Frozen source hash drift")
    fallback = protocol["fallback_proposal"]
    fallback_path = _safe(repo, fallback["source"])
    _require(hashlib.sha256(fallback_path.read_bytes()).hexdigest() == fallback["source_sha256"], "Frozen predecessor hash drift")
    _require(core.validate_rubric(_read(fallback_path)["proposed_rubric"]) == fallback["rubric"], "Predecessor Rubric mismatch")
    completion_source = "results.json" if (run / "results.json").exists() else (
        "recovered_results.json" if (run / "recovered_results.json").exists() else None)
    result = _read(run / completion_source) if completion_source else None
    complete = result is not None and result.get("status") == "complete"
    complete_checks = complete or require_evidence_complete
    _require(not require_complete or complete, "Completed results required; explicitly allow an incomplete snapshot")
    adapters, phase_clusters = {}, {}
    for phase, items in panel.items():
        phase_clusters[phase] = set()
        for item in items:
            task = item["task"]
            _require(task["id"] not in adapters, "Frozen panel has duplicate task IDs")
            adapter = CodingAdapter(RepoTask.from_dict(task)) if item["domain"] == "coding" else NativeAdapter(task)
            adapters[task["id"]] = adapter
            phase_clusters[phase].add(task["cluster_id"])
    _require(not any(phase_clusters[a] & phase_clusters[b] for a in phase_clusters for b in phase_clusters if a < b),
             "Frozen development/calibration/final families overlap")
    calls, api = _receipts(run, protocol, complete_checks)
    targets = _targets(run, calls, adapters)
    skill, freeze, decisions, packets = _skill_audit(run, protocol, calls, targets, panel, complete_checks)
    # Audit model-visible payloads in memory; never print raw prompts, responses, or labels.
    forbidden_ids = [r["task"]["id"] for phase in ("calibration", "final") for r in panel[phase]]
    for value in calls.values():
        request = value["request"]
        if request["kind"] == "v6_skill" or request["kind"].startswith("v5_rubric_"):
            _require(all(t not in request["user"] for t in forbidden_ids)
                     and '"truth":' not in request["user"], "Future task/label exposed to learning or research")
    calibration = _calibration(run, protocol, _read(run / "calibration_manifest.json"), calls, adapters, complete_checks)
    final = _final(run, protocol, panel, adapters, freeze, targets, complete_checks)
    repairs = _repairs(run, protocol, panel, calls, complete_checks)
    research_report = _research_audit(run, protocol, calls, packets, complete_checks)
    human_review = {"review_performed": False, "status": "not_exported_yet"}
    queue_path = run / "human_review/queue.json"
    if queue_path.exists():
        queue = _json(queue_path)
        core.verify(queue, "queue_hash")
        private = _json(queue_path.with_suffix(".json.private.json"))
        _require(private["queue_hash"] == queue["queue_hash"] and queue["review_performed"] is False,
                 "Human assignment queue identity/performed status changed")
        sources = {s["review_id"]: s for s in private["sources"]}
        _require(len(sources) == len(queue["entries"]), "Human review source mapping incomplete")
        for entry in queue["entries"]:
            source = sources[entry["review_id"]]
            packet = packets[source["feedback_id"]]
            evidence = {k: packet[k] for k in ("artifact", "contract", "facts", "hypotheses", "repair_guidance")}
            row = {"feedback_id": packet["record_hash"], "domain": packet["domain"],
                   "disputed": any(r["status"] == "unknown" for r in packet["observations"]), **evidence}
            _require(source["source_hash"] == digest(row) and entry["evidence"] == governance._blind(evidence),
                     "Human queue evidence not bound to retained development packet")
        human_review = {"review_performed": False, "status": "pending_external_human",
                        "queued": len(queue["entries"]), "queue_hash": queue["queue_hash"]}
    if complete_checks:
        _require(not packets or queue_path.exists(), "Complete run lacks its declared human assignment queue")
    if complete:
        _require(result["protocol_hash"] == digest(protocol) and result["decisions"] == decisions,
                 "Completed result protocol/Skill decision mismatch")
        _require(result["calibration"] == calibration["summary"] and result["final"] == final["summary"]
                 and result["repair_summary"] == repairs["summary"] and result["repair"] == repairs["rows"],
                 "Completed summary differs from independently recomputed analysis")
        _require(result["ledger"] == api["ledger"] and result["returned_models"] == api["returned_models"],
                 "Completed API ledger/model counts differ from actual receipts")
        _require(result["unique_feedback"] == len(packets) and result["final_feedback_used"] is False
                 and result["calibration_feedback_used"] is False, "Completed feedback declaration mismatch")
        _require(result["validator_selection"] == _read(run / "validator_candidate_frozen.json")
                 and result["research_proposal_hash"] == research_report["proposal_hash"], "Completed research selection mismatch")
    if completion_source == "recovered_results.json":
        _verify_recovery(result, run, repo, calls)
    elif result is not None:
        _require("reporting_recovery" not in result, "Recovery provenance must not masquerade as original results")
    evidence_complete = bool(api.get("available") and not api["ledger"]["unresolved_reservations"] and freeze
        and calibration.get("complete") and final.get("complete") and repairs.get("available")
        and research_report.get("complete") and (not packets or queue_path.exists()))
    if require_evidence_complete:
        _require(evidence_complete, "Full evidence completion required")
    recovered = completion_source == "recovered_results.json"
    repairs.pop("rows", None)  # No raw model artifacts or task labels in the audit report.
    return core.seal({"version": "coevolution-v6-read-only-audit-v1", "complete": complete,
        "evidence_complete": evidence_complete, "completion_source": completion_source,
        "original_runtime_completed": bool(complete and not recovered),
        "verdict": ("recovered_reporting_index_and_evidence_consistent" if recovered and complete else
                    "completed_receipts_and_analysis_consistent" if complete else
                    "complete_evidence_without_runtime_result" if evidence_complete else "partial_snapshot_only"),
        "protocol_hash": digest(protocol), "results_hash": digest(result) if result is not None else None,
        "verified_source_files": len(protocol["source_hashes"]), "api": api,
        "source_skills": skill, "research": research_report, "calibration": calibration,
        "final": final, "repair": repairs, "human_review": human_review,
        "limitations": ["Local hashes are integrity checks, not authenticated proof of an honest host.",
            "Generated code/native scores were not re-executed; host outcome receipts are the retained evidence.",
            "No API calls, label feedback, runtime edits, output writes, or Skill/validator activation.",
            "Repeated histories and parameter variants are not independent structural task families.",
            "Equal call counts are not guaranteed equal tokens, invoices, or effective independent probes.",
            "This synthetic diagnostic does not establish public benchmark efficacy or cross-domain safety.",
            "No completed human review is inferred from an exported review queue.",
            "A recovered reporting index is not successful completion of the original runtime; null model receipts remain unreported."]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(args.run, repo=args.repo, require_complete=not args.allow_incomplete)
    except (ValueError, KeyError, TypeError, OSError):
        # Do not echo potentially model-controlled input or credentials from an exception.
        print(json.dumps({"audit_valid": False, "error": "input_integrity_or_completeness_check_failed"}))
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
