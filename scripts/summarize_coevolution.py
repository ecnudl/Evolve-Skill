"""Summarize a COMPLETE co-evolution run without requests, rescoring, or edits.

Never reads .env or api/calls. Original contrasts are copied, not recomputed.
Only an immutable posthoc_summary.json in a separate output directory is written.
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

from scripts.audit_completed_scale import archive_audit  # noqa: E402

TRIO = ("noskill", "current", "candidate")
CONTRASTS = {"evolving_validator_vs_fixed_validator", "evolving_validator_vs_noskill"}
PROTOCOL_STATUS = {
    "coding-skill-executable-validator-loop-v1": "harness_confounded_retained_only",
    "coding-skill-executable-validator-loop-v2-divmod-runtime": "divmod_runtime_corrected_rerun",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _counts(values):
    values = list(values)
    if any(value is not None and type(value) not in (bool, int) for value in values):
        raise ValueError("Outcome must be binary or missing")
    if any(value is not None and value not in (0, 1) for value in values):
        raise ValueError("Nonbinary outcome")
    known = [int(value) for value in values if value is not None]
    return {"expected": len(values), "observable": len(known), "passes": sum(known),
            "failures": len(known) - sum(known), "unknown": len(values) - len(known),
            "pass_rate": sum(known) / len(known) if known else None}


def _pairs(rows):
    return {"n_task_repeat_pairs": len(rows), "n_distinct_tasks": len({row["id"] for row in rows}),
            "conditions": {arm: _counts(row[arm] for row in rows) for arm in TRIO},
            "by_mode": {mode: {arm: _counts(row[arm] for row in rows if row["mode"] == mode) for arm in TRIO}
                        for mode in sorted({row["mode"] for row in rows})}}


def _memory(state):
    core = dict(state)
    checksum = core.pop("state_hash", None)
    if checksum != digest(core):
        raise ValueError("Validator memory integrity mismatch")
    entries = [*core["memory"], *core["calibration_notes"]]
    if any(row.get("source_phase") not in {"learn0", "learn1", "gate0", "gate1"} for row in entries):
        raise ValueError("Validator memory contains nondevelopment evidence")
    return {"version": core["version"], "revision": core["revision"], "state_hash": checksum,
            "verified_mismatch_memories": len(core["memory"]),
            "not_reproduced_notes": len(core["calibration_notes"]), "stored_entries": len(entries),
            "source_phase_counts": dict(sorted(Counter(row["source_phase"] for row in entries).items())),
            "source_receipt_hashes": sorted(row["source_receipt_hash"] for row in entries)}


def _probe_summary(records):
    receipts = [receipt for record in records for receipt in record["receipts"]]
    statuses = Counter(receipt["status"] for receipt in receipts)
    for receipt in receipts:
        core = dict(receipt)
        checksum = core.pop("receipt_hash", None)
        if checksum != digest(core):
            raise ValueError("Probe receipt integrity mismatch")
    return {"planned_search_jobs": len(records),
            "actual_logical_search_calls": sum(record.get("request_hash") is not None for record in records),
            "distinct_request_hashes": len({record["request_hash"] for record in records if record.get("request_hash")}),
            "search_status_counts": dict(sorted(Counter(record["status"] for record in records).items())),
            "schema_valid_responses": sum(record.get("parsed", {}).get("schema_valid") is True for record in records),
            "receipt_count": len(receipts), "receipt_status_counts": dict(sorted(statuses.items())),
            "comparable_executed_receipts": statuses["verified_mismatch"] + statuses["not_reproduced"],
            "invalid_or_unavailable_receipts": len(receipts) - statuses["verified_mismatch"] - statuses["not_reproduced"],
            "counts_are_search_receipts_not_independent_tasks": True}


def _final_counts(rows, streams, arms, repeats):
    def outcome(row):
        return row["hard"] if row["target_ok"] and row["execution_ok"] else None

    return {arm: {"all": _counts(outcome(row) for row in rows if row["arm"] == arm),
                  "skill_active_rows": sum(row["skill_active"] for row in rows if row["arm"] == arm),
                  "per_stream": {str(stream): {
                      "all": _counts(outcome(row) for row in rows if row["arm"] == arm and row["stream"] == stream),
                      "per_repeat": {str(repeat): _counts(outcome(row) for row in rows
                          if row["arm"] == arm and row["stream"] == stream and row["repeat"] == repeat)
                                     for repeat in repeats}} for stream in streams},
                  "per_repeat_combined_streams": {str(repeat): _counts(outcome(row) for row in rows
                      if row["arm"] == arm and row["repeat"] == repeat) for repeat in repeats}}
            for arm in arms}


def summarize(run: Path):
    run, hashes = Path(run), {}

    def read(relative, *, checked_record=False):
        # Internal callers supply only known derived-artifact paths, never a
        # provider-call cache or arbitrary user-supplied relative path.
        if relative == ".env" or relative.startswith("api/"):
            raise ValueError("Credential and provider-request reads are forbidden")
        payload = (run / relative).read_bytes()
        hashes[relative] = hashlib.sha256(payload).hexdigest()
        row = json.loads(payload)
        if checked_record:
            checksum = row.pop("record_sha256", None)
            if checksum != digest(row):
                raise ValueError("Derived target integrity mismatch")
        return row

    results = read("results.json")
    if results.get("status") != "complete":
        raise ValueError("Completion barrier not met; other artifacts remain unread")
    protocol = read("protocol.json")
    if protocol.get("version") not in PROTOCOL_STATUS or results.get("protocol_hash") != digest(protocol):
        raise ValueError("Completed results and supported frozen protocol disagree")
    streams, policies, rounds = protocol["streams"], protocol["policies"], protocol["rounds"]
    if streams != [0, 1] or rounds != [0, 1] or policies != ["fixed_validator", "evolving_validator"]:
        raise ValueError("Summary requires the frozen two-stream/two-policy/two-round design")
    final_seal = read("final_frozen.json")
    histories = read(f"histories/r{rounds[-1]}.json")
    if (final_seal.get("freeze_before_holdout") is not True or final_seal.get("protocol_hash") != digest(protocol)
            or final_seal.get("histories_hash") != digest(histories)
            or results.get("final_state_hash") != digest(final_seal["states"])):
        raise ValueError("Final lineage/history seal mismatch")
    expected = {(stream, policy, round_index) for stream in streams for policy in policies for round_index in rounds}
    if len(histories) != len(expected) or {(h["stream"], h["policy"], h["round"]) for h in histories} != expected:
        raise ValueError("Expected exactly eight unique proposal/decision histories")
    decision_files = {round_index: read(f"decisions/r{round_index}.json") for round_index in rounds}
    lineage_rows, proposals, searches = [], [], []
    for history in sorted(histories, key=lambda row: (row["stream"], row["policy"], row["round"])):
        stream, policy, round_index = history["stream"], history["policy"], history["round"]
        identity = f"s{stream}_{policy}"
        sealed = decision_files[round_index][identity]
        if any(history.get(key) != value for key, value in sealed.items()):
            raise ValueError("History differs from its pre-audit decision seal")
        proposal = read(f"proposals/{identity}_r{round_index}.json")
        if proposal != history["candidate"] or proposal["content_hash"] != digest(proposal["content"]):
            raise ValueError("Proposal differs from frozen decision")
        state = read(f"states/{identity}_r{round_index}.json")
        expected_skill = proposal["content"] if history["decision"]["action"] == "Commit" else history["current_skill"]
        if state["skill"] != expected_skill or state["last_candidate"] != proposal["content"]:
            raise ValueError("Stored state does not follow the recorded decision")
        if round_index == rounds[-1] and state != final_seal["states"][identity]:
            raise ValueError("Final state differs from its last round")
        proposal_summary = {"stream": stream, "policy": policy, "round": round_index,
                            "valid": proposal["valid"], "reason": proposal["reason"],
                            "request_hash": proposal["request_hash"], "content_hash": proposal["content_hash"],
                            "content_characters": len(proposal["content"]), "raw_characters": len(proposal.get("raw", ""))}
        proposals.append(proposal_summary)
        planned = [(row["id"], 0) for row in history["source_pairs"] if row["repeat"] == 0]
        planned += [(row["id"], row["repeat"]) for row in history["gate_pairs"]]
        if len(set(planned)) != len(planned):
            raise ValueError("Duplicate planned probe job in one lineage/round")
        local_searches = []
        for task_id, repeat in planned:
            job = {"id": task_id, "skill": proposal["content"], "stream": stream,
                   "stage": f"r{round_index}", "repeat": repeat, "arm": "shared_content"}
            artifact = read(f"targets/{digest(job)}.json", checked_record=True)
            if any(artifact.get(key) != value for key, value in {
                    "id": task_id, "stream": stream, "repeat": repeat, "stage": f"r{round_index}",
                    "arm": "shared_content", "skill_hash": digest(proposal["content"])}.items()):
                raise ValueError("Claim source artifact does not match its lineage/round")
            claim_key = digest({"artifact": artifact, "state": history["validator_before"],
                                "stream": stream, "policy": policy, "round": round_index})
            claim = read(f"claims/{claim_key}.json")
            if claim.get("request_hash") is not None and (
                    claim.get("artifact_hash") != digest(artifact)
                    or claim.get("validator_hash") != digest(history["validator_before"])):
                raise ValueError("Claim artifact or validator provenance mismatch")
            local_searches.append(claim)
            searches.append({"stream": stream, "policy": policy, "round": round_index, "record": claim})
        lineage_rows.append({"stream": stream, "policy": policy, "round": round_index,
                             "decision": history["decision"], "proposal_valid": proposal["valid"],
                             "source_full_oracle": _pairs(history["source_pairs"]),
                             "visible_gate_scoped_checks": _pairs(history["gate_pairs"]),
                             "postdecision_private_gate": _pairs(history["gate_private_audit_pairs"]),
                             "private_gate_observed_losses": history["gate_private_observed_losses"],
                             "committed_with_hidden_gate_loss": history["committed_with_hidden_gate_loss"],
                             "validator_before": _memory(history["validator_before"]),
                             "validator_after": _memory(state["validator"]),
                             "deployed_skill_hash": digest(state["skill"]), "deployed_skill_active": bool(state["skill"]),
                             "last_candidate_hash": digest(state["last_candidate"]), "probe_search": _probe_summary(local_searches)})
    final_rows = read("final_rows.json")
    analysis = results["final_analysis"]
    if set(analysis["contrasts"]) != CONTRASTS:
        raise ValueError("Expected exactly the two prespecified frozen contrasts")
    if len(final_rows) != analysis["design"]["n_expected_rows"]:
        raise ValueError("Completed final matrix has the wrong row count")
    identities = {(row["id"], row["stream"], row["arm"], row["repeat"]) for row in final_rows}
    final_ids = {row["id"] for row in final_rows}
    expected_final = {(identity, stream, arm, repeat) for identity in final_ids for stream in streams
                      for arm in protocol["final_arms"] for repeat in protocol["final_repeats"]}
    if len(identities) != len(final_rows) or identities != expected_final or len(final_ids) != analysis["design"]["n_expected_tasks"]:
        raise ValueError("Final stream/task/arm/repeat identities are incomplete or duplicated")
    if any(row.get("phase") != "holdout" or row.get("stage") != "final" for row in final_rows):
        raise ValueError("Final rows contain development or unfrozen deployment rows")
    final_counts = _final_counts(final_rows, streams, protocol["final_arms"], protocol["final_repeats"])
    for arm, counts in final_counts.items():
        if (counts["all"]["passes"] != analysis["arms"][arm]["hard_passes"]
                or counts["all"]["observable"] != analysis["arms"][arm]["n_observable"]):
            raise ValueError("Final count summary disagrees with frozen analysis")
    return {"version": "coevolution-posthoc-summary-v1", "status": "complete_source_summarized",
            "source_run": str(run.resolve()), "completion_barrier_checked": True,
            "source_protocol_version": protocol["version"],
            "source_run_interpretation": PROTOCOL_STATUS[protocol["version"]],
            "cross_run_statistics_pooled": False,
            "input_sha256": hashes, "summary_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "proposal_count": len(proposals), "valid_proposals": sum(p["valid"] for p in proposals),
            "proposals": proposals, "decision_counts": dict(sorted(Counter(h["decision"]["action"] for h in histories).items())),
            "lineage_rounds": lineage_rows,
            "probe_search": {"all": _probe_summary([row["record"] for row in searches]),
                             "by_policy_round": {f"{policy}/r{round_index}": _probe_summary(
                                 [row["record"] for row in searches if row["policy"] == policy and row["round"] == round_index])
                                 for policy in policies for round_index in rounds}},
            "final_five_arms": final_counts,
            "frozen_contrasts": {name: {"source_json_pointer": f"/final_analysis/contrasts/{name}",
                                         "copied_without_recomputation": True, "result": value}
                                 for name, value in analysis["contrasts"].items()},
            "new_inferential_tests": False, "new_thresholds": False,
            "limitations": [
                            ("The v1 run is retained as harness-confounded: missing divmod in the executor could penalize valid code and contaminate later optimizer context."
                             if protocol["version"] == "coding-skill-executable-validator-loop-v1" else
                             "The v2 run is a separate full rerun after the divmod executor correction; this label does not certify absence of other limitations."),
                            "Different protocol runs must be archived separately and are not pooled as additional observations.",
                            "Development shared-content requests may be reused across roles/policies; these are not extra independent responses.",
                            "Visible gate checked-pass is not full correctness; its private audit occurs only after the decision seal.",
                            "Two streams and repeated outputs are not independent additional task families.",
                            "Last-candidate arms diagnose terminal candidate deployment, not fully ungated training branches.",
                            "Only the two prespecified contrast results are copied; no Fixed-minus-NoSkill inferential contrast is added."]}


def compact(summary):
    return {"source_protocol_version": summary["source_protocol_version"],
            "source_run_interpretation": summary["source_run_interpretation"],
            "cross_run_statistics_pooled": summary["cross_run_statistics_pooled"],
            "proposal_count": summary["proposal_count"], "valid_proposals": summary["valid_proposals"],
            "decision_counts": summary["decision_counts"],
            "lineage_rounds": [{key: row[key] for key in ("stream", "policy", "round", "decision", "proposal_valid",
                                                         "deployed_skill_active", "private_gate_observed_losses")}
                               for row in summary["lineage_rounds"]],
            "final_five_arms": summary["final_five_arms"],
            "frozen_contrasts": {name: {"estimate": value["result"]["primary_macro_cluster_delta"],
                                        "ci95": value["result"]["family_cluster_bootstrap"]["ci95"]}
                                 for name, value in summary["frozen_contrasts"].items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--stdout", action="store_true", help="Print a compact summary in addition to archive provenance")
    args = parser.parse_args()
    try:
        summary = summarize(args.run)
        archive = archive_audit(summary, args.output_dir / "posthoc_summary.json", args.run)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "original_run_unchanged": True,
                          "no_api_calls": True}))
        return 1
    print(json.dumps({"ok": True, "archive": archive, **({"summary": compact(summary)} if args.stdout else {})},
                     ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
