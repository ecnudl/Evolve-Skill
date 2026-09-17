"""Read-only calibration audit: pending snapshots never produce performance/gates.

No API/pacer constructor, oracle execution, registry reservation/decision write,
or output-file option is provided. Existing diagnostic provenance is verified
through its completed-only reader; missing artifacts are never reconstructed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import audit_coevolution_v6 as prior  # noqa: E402
from scripts.audit_coevolution_v7 import _pacing  # noqa: E402
from skillopt.coevolution_v5 import core  # noqa: E402
from skillopt.coevolution_v6 import statistics  # noqa: E402
from skillopt.coevolution_v7.experiment import validator_activation  # noqa: E402
from skillopt.coevolution_v8 import calibration_study as driver  # noqa: E402
from skillopt.coevolution_v8 import research_calibration as bridge  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "v8-read-only-calibration-audit-v1"
_require, _json = prior._require, prior._json
LIMITS = [
    "Checks host receipt consistency, not authenticity against a malicious host.",
    "Does not reexecute candidate/reference code or independently establish oracle truth.",
    "Structural-family independence is a host declaration, not proved by hashes.",
    "Finite calibration performance is not Skill efficacy, public-benchmark gain, or deployment safety.",
    "Usage is provider-reported, not an invoice; failed attempts can have unreported usage.",
    "Pacing measures HTTP attempt admission/start, including retries, not completion or server arrival.",
]


def _read(path):
    return core.verify(_json(path))


def _paths(directory):
    # Atomic publication's temporary files are not committed evidence.
    return sorted(p for p in Path(directory).glob("*.json") if not p.name.startswith("."))


def _api_snapshot(run, screen, identity, *, complete):
    budget = _json(run / "api/budget_protocol.json")
    proposal = screen["proposal"]
    _require(budget["model"] == proposal["model"] == "glm-5.3" and budget["workers"] == identity["workers"] == 4
             and budget["max_logical_calls"] == screen["max_calls"]
             and budget["service_sha256"] == digest(proposal["service"]), "API budget/profile differs from frozen screen")
    _require(_json(run / "api/service.json") == proposal["service"], "API profile differs from Research source")
    # Read call paths before reservations: every published call had a prior reservation.
    calls = {p.stem: _json(p) for p in _paths(run / "api/calls")}
    reservations = {p.stem: _json(p) for p in _paths(run / "api/budget_reservations")}
    _require(len(reservations) <= screen["max_calls"], "Logical budget exceeded")
    expected = {digest(bridge.request_for_job(screen, job)): job for job in screen["jobs"]}
    _require(len(expected) == len(screen["jobs"]), "Distinct jobs unexpectedly share an API request")
    _require(set(calls) <= set(reservations) <= set(expected), "Unexpected or unreserved calibration API request")
    for h, reservation in reservations.items():
        _require(reservation == {"request_hash": h, "kind": "v5_validator_probe"}, "Reservation identity mismatch")
    for h, record in calls.items():
        request = record.get("request")
        _require(record.get("request_hash") == h == digest(request)
                 and request == bridge.request_for_job(screen, expected[h]), "API payload differs from declared public-only request")
        _require(type(record.get("ok")) is bool and type(record.get("http_attempt_count")) is int
                 and 1 <= record["http_attempt_count"] <= 3, "Invalid API outcome/attempt accounting")
    unresolved = sorted(set(reservations) - set(calls))
    _require(not complete or set(calls) == set(reservations) == set(expected), "Complete result has an incomplete request grid")
    records = list(calls.values())
    ledger = {"max_logical_calls": screen["max_calls"], "logical_requests_reserved": len(reservations),
        "cached_logical_calls": len(calls), "successful_calls": sum(r["ok"] for r in records),
        "terminal_errors": sum(not r["ok"] for r in records), "unresolved_reservations": unresolved,
        "http_attempts_from_cached_records": sum(r["http_attempt_count"] for r in records),
        "max_planned_http_attempts": screen["max_calls"] * 3,
        "by_kind": dict(sorted(Counter(r["request"]["kind"] for r in records).items())),
        **{k: sum(r.get("usage", {}).get(k, 0) or 0 for r in records)
           for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "missing_usage_calls": sum(not r.get("usage") for r in records), "usage_not_invoice": True,
        "unreturned_or_interrupted_attempt_usage_unknown": True}
    pacing = _pacing(run, {"pacing_policy": identity["pacing_policy"]}, calls, require_complete=complete)
    return calls, ledger, pacing


def _reconstruct(screen, components, calls):
    """Pure counterpart of screen aggregation, without registry.consume/writes."""
    indexed, outcomes, unknowns, api_kinds = {}, {}, [], Counter()
    for component in components:
        artifact, rubric, inputs = bridge._probe_result(screen, component, calls[component["search"]["request_hash"]])
        outcome, missing = bridge._execution_outcome(component, artifact, rubric, inputs)
        key = digest(component["job"])
        _require(key not in indexed, "Duplicate calibration component")
        indexed[key], outcomes[key] = component, outcome
        unknowns.extend(missing)
        api_kinds[bridge._api_category(calls[component["search"]["request_hash"]], component["search"])] += 1
    _require(set(indexed) == {digest(j) for j in screen["jobs"]}, "Metrics require the complete frozen component grid")
    rows = []
    for artifact in screen["manifest"]["artifacts"]:
        for block in screen["manifest"]["repeats"]:
            for policy, channels in bridge.POLICIES.items():
                keys = [digest({"artifact_id": artifact["artifact_id"], "block": block, "channel": c}) for c in channels]
                parts, values = [indexed[k] for k in keys], [outcomes[k] for k in keys]
                outcome = "detected" if "detected" in values else "not_detected" if all(v == "not_detected" for v in values) else "unknown"
                rows.append({k: artifact[k] for k in ("artifact_id", "artifact_hash", "task_id", "cluster_id", "truth")}
                    | {"block": block, "policy": policy, "outcome": outcome,
                       "input_count": len({digest(i) for p in parts for i in p["search"]["inputs"]}),
                       "probe_request_hashes": [p["search"]["request_hash"] for p in parts],
                       "component_hashes": [p["record_hash"] for p in parts], "public_only": True})
    summary = statistics.summarize_validator(rows, expected_artifacts={a["artifact_id"]: {
        "cluster_id": a["cluster_id"], "truth": a["truth"]} for a in screen["manifest"]["artifacts"]},
        expected_blocks=screen["manifest"]["repeats"])
    candidate = screen["proposal"]["candidate_rubric"]
    gate = validator_activation(summary, candidate)
    decision = core.seal({"version": bridge.VERSION, "screen_hash": screen["record_hash"],
        "diagnostic_result_hash": screen["proposal"]["diagnostic_result_hash"], "gate": gate,
        "activate_next_round": gate["activate_next_round"],
        "active_rubric": candidate if gate["activate_next_round"] else screen["proposal"]["old_rubric"],
        "active_from_round": screen["round_index"] + 1 if gate["activate_next_round"] else None,
        "old_retained": not gate["activate_next_round"], "complete_calibration_grid": True,
        "expected_components": len(screen["jobs"]), "observed_components": len(components),
        "api_diagnostic_counts": dict(api_kinds), "execution_unknown_counts": dict(Counter(unknowns)),
        "summary_hash": summary["summary_hash"], "deployment_approval": False,
        "scope": "next_round_development_feedback_only", "raw_calibration_labels_returned": False,
        "no_skill_or_cross_domain_efficacy_claim": True})
    return rows, summary, decision


def _cost_by_channel(screen, components, calls):
    result = {}
    for channel in bridge.CHANNELS:
        records = [calls[c["search"]["request_hash"]] for c in components if c["job"]["channel"] == channel]
        result[channel] = {"calls": len(records), "http_attempts": sum(r["http_attempt_count"] for r in records),
            **{k: sum(r.get("usage", {}).get(k, 0) or 0 for r in records)
               for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "missing_usage_calls": sum(not r.get("usage") for r in records)}
    return {"channels": result, "policy_calls": {p: sum(result[c]["calls"] for c in channels)
                for p, channels in bridge.POLICIES.items()}, "max_tokens_each": screen["max_tokens_each"],
            "old_a_is_shared_not_independently_rerun": True, "equal_call_caps_not_equal_tokens_or_invoice": True}


def audit(run, repo=REPO, require_complete=False):
    repo, run = Path(repo).resolve(), bridge._safe_root(run)
    _require(run.is_dir() and run.is_relative_to(repo / "outputs/coevolution_v8"), "Existing V8 repository run required")
    identity = _read(run / "identity.json")
    _require(identity["version"] == driver.VERSION and identity["sources"] == driver._sources(repo), "Frozen source identities changed")
    _require(identity["pacing_policy"] == vars(driver.PACING) and identity["workers"] == 4,
             "Frozen attempt pacing/workers changed")
    complete = (run / "results.json").is_file()
    _require(not require_complete or complete, "Pending: completed results are required")
    if not (run / "screen.json").is_file():
        _require(not complete, "Complete calibration result requires its frozen screen")
        return core.seal({"version": VERSION, "status": "pending", "complete": False,
                          "stage": "screen_not_published", "metrics_computed": False, "gate_computed": False,
                          "identity_hash": identity["record_hash"], "limitations": LIMITS})
    screen = _read(run / "screen.json")
    # This helper verifies existing registry/diagnostic artifacts only. It does
    # not reserve, consume, call assess_screen, or execute native code.
    registry = bridge._verify_screen(screen)
    _require(screen["screen_id"] == run.name == identity["screen_id"]
             and screen["registry_root"] == identity["registry_root"]
             and screen["proposal"]["diagnostic_root"] == identity["diagnostic_root"]
             and screen["proposal"]["diagnostic_result_hash"] == identity["diagnostic_result_hash"]
             and screen["round_index"] == identity["round_index"]
             and screen["manifest"]["repeats"] == list(range(identity["blocks"]))
             and digest(list(screen["tasks"].values())) == identity["panel_hash"], "Driver/screen/proposal identities differ")
    jobs = {(a["artifact_id"], b, c) for a in screen["manifest"]["artifacts"]
            for b in screen["manifest"]["repeats"] for c in bridge.CHANNELS}
    _require(len(screen["jobs"]) == len(jobs) == screen["max_calls"]
             and {(j["artifact_id"], j["block"], j["channel"]) for j in screen["jobs"]} == jobs,
             "Calibration matrix differs from manifest Cartesian product")
    if not (run / "api/budget_protocol.json").is_file():
        _require(not complete, "Complete run missing API protocol")
        return core.seal({"version": VERSION, "status": "pending", "complete": False,
                          "expected_calls": len(jobs), "stage": "api_not_started", "metrics_computed": False,
                          "gate_computed": False, "identity_hash": identity["record_hash"], "limitations": LIMITS})
    # Capture components before calls: a committed component must already have
    # its committed API receipt, even while the live run publishes new jobs.
    paths = _paths(run / "components")
    calls, ledger, pacing = _api_snapshot(run, screen, identity, complete=complete)
    expected_components = {digest(j): j for j in screen["jobs"]}
    components = {}
    for path in paths:
        component = _read(path)
        _require(path.stem in expected_components and component["job"] == expected_components[path.stem]
                 and set(component) == {"job", "search", "assessments", "record_hash"}, "Unexpected or misbound component")
        h = component["search"]["request_hash"]
        _require(h in calls, "Component has no actual API receipt")
        artifact, rubric, inputs = bridge._probe_result(screen, component, calls[h])
        bridge._execution_outcome(component, artifact, rubric, inputs)
        components[path.stem] = component
    _require(not complete or set(components) == set(expected_components), "Complete result has missing components")
    common = {"version": VERSION, "status": "verified_complete" if complete else "pending", "complete": complete,
        "identity_hash": identity["record_hash"], "screen_hash": screen["record_hash"],
        "expected_calls": len(jobs), "verified_components": len(components), "verified_source_files": len(identity["sources"]),
        "ledger": ledger, "pacing": pacing, "read_only": True, "native_code_reexecuted": False,
        "new_api_calls": 0, "limitations": LIMITS}
    if not complete:
        return core.seal({**common, "metrics_computed": False, "gate_computed": False,
                          "snapshot_not_transactional": True, "live_inflight_evidence_may_be_unpublished": True})
    ordered = [components[digest(j)] for j in screen["jobs"]]
    rows, summary, decision = _reconstruct(screen, ordered, calls)
    private = core.seal({"screen_hash": screen["record_hash"], "components": ordered, "api_receipts": calls,
        "rows": rows, "summary": summary, "private_calibration_never_optimizer_feedback": True})
    _require(_read(registry / "v8_private_calibration.json") == private, "Stored private calibration differs from reconstructed evidence")
    _require(_read(registry / "v8_decision.json") == decision, "Stored gate differs from independent offline reconstruction")
    expected_result = core.seal({"version": driver.VERSION, "identity_hash": identity["record_hash"], "complete": True,
        "screen_hash": screen["record_hash"], "decision": decision, "ledger": ledger,
        "components_hash": digest(ordered), "no_skill_or_benchmark_effect_measured": True})
    _require(_read(run / "results.json") == expected_result, "Complete driver result differs from reconstructed grid/ledger/gate")
    metrics = {policy: {m: summary["policy_summary"][policy]["metrics"][m]["cluster_mean"]
                       for m in ("bad_detection", "good_false_rejection", "unknown", "unknown_good", "unknown_bad")}
               for policy in bridge.POLICIES}
    return core.seal({**common, "metrics_computed": True, "gate_computed": True, "policy_metrics_cluster_equal_weight": metrics,
        "comparison_summary": summary["comparisons"], "summary_hash": summary["summary_hash"],
        "gate": decision["gate"], "decision_hash": decision["record_hash"], "result_hash": expected_result["record_hash"],
        "cost": _cost_by_channel(screen, ordered, calls), "returned_models": dict(Counter(prior._returned_model(r) for r in calls.values())),
        "api_diagnostic_counts": decision["api_diagnostic_counts"], "execution_unknown_counts": decision["execution_unknown_counts"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Existing run to READ; no files will be written")
    parser.add_argument("--require-complete", action="store_true", help="Reject pending runs instead of printing a pending snapshot")
    args = parser.parse_args()
    try:
        result = audit(args.output, require_complete=args.require_complete)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"version": VERSION, "status": "audit_failed", "error_type": type(exc).__name__,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
