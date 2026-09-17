"""Post-completion summaries use synthetic artifacts only, never model calls."""

import copy
import json
import sys
from pathlib import Path

import pytest

from scripts import summarize_coevolution as summary

POLICIES = ["fixed_validator", "evolving_validator"]
ARMS = ["noskill", *POLICIES, "latest_fixed_candidate", "latest_evolving_candidate"]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def memory(revision=0):
    core = {"version": f"validator-memory-v{revision}", "revision": revision,
            "memory": ([{"source_phase": "learn0", "source_receipt_hash": "receipt-a"}]
                       if revision else []),
            "calibration_notes": ([{"source_phase": "gate1", "source_receipt_hash": "receipt-b"}]
                                  if revision > 1 else []), "local_tests_only": True}
    return {**core, "state_hash": summary.digest(core)}


@pytest.fixture
def complete_run(tmp_path):
    run = tmp_path / "run"
    protocol = {"version": "coding-skill-executable-validator-loop-v1", "streams": [0, 1],
                "rounds": [0, 1], "policies": POLICIES, "final_arms": ARMS,
                "final_repeats": [0, 1, 2]}
    write(run / "protocol.json", protocol)
    histories, final_states = [], {}
    previous = {f"s{s}_{p}": {"skill": "", "validator": memory()} for s in [0, 1] for p in POLICIES}
    for round_index in [0, 1]:
        decisions = {}
        for stream in [0, 1]:
            for policy in POLICIES:
                identity = f"s{stream}_{policy}"
                candidate = f"synthetic skill {identity} round {round_index}"
                proposal = {"content": candidate, "content_hash": summary.digest(candidate),
                            "valid": True, "raw": candidate, "reason": "valid",
                            "request_hash": f"proposal-{identity}-{round_index}"}
                write(run / "proposals" / f"{identity}_r{round_index}.json", proposal)
                source_pairs = [{"id": f"learn{round_index}", "repeat": repeat,
                                 "mode": "local-update", "noskill": False, "current": False,
                                 "candidate": True} for repeat in [0, 1]]
                gate_pairs = [{"id": f"gate{round_index}", "repeat": repeat,
                               "mode": "full-policy-replacement", "noskill": 1,
                               "current": 1, "candidate": 1} for repeat in [0, 1]]
                action = "Reject" if round_index else "Commit"
                record = {"stream": stream, "policy": policy, "round": round_index,
                          "candidate": proposal, "current_skill": previous[identity]["skill"],
                          "validator_before": previous[identity]["validator"],
                          "source_pairs": source_pairs, "gate_pairs": gate_pairs,
                          "decision": {"action": action, "reason": "synthetic recorded decision"}}
                decisions[identity] = copy.deepcopy(record)
                audit_pairs = [{**pair, "noskill": True, "current": True,
                                "candidate": bool(pair["repeat"])} for pair in gate_pairs]
                histories.append({**record, "gate_private_audit_pairs": audit_pairs,
                                  "gate_private_observed_losses": 1,
                                  "committed_with_hidden_gate_loss": action == "Commit"})
                state = {"skill": candidate if action == "Commit" else previous[identity]["skill"],
                         "validator": memory(round_index + 1) if policy == "evolving_validator" else memory(),
                         "last_candidate": candidate}
                write(run / "states" / f"{identity}_r{round_index}.json", state)
                previous[identity] = state
                if round_index == 1:
                    final_states[identity] = state
                for task_id, repeat in [(f"learn{round_index}", 0), (f"gate{round_index}", 0), (f"gate{round_index}", 1)]:
                    job = {"id": task_id, "skill": candidate, "stream": stream,
                           "stage": f"r{round_index}", "repeat": repeat, "arm": "shared_content"}
                    artifact = {key: value for key, value in job.items() if key != "skill"}
                    artifact.update(skill_hash=summary.digest(candidate), target_ok=True, code="synthetic",
                                    request_hash=f"target-{summary.digest(job)}")
                    write(run / "targets" / f"{summary.digest(job)}.json",
                          {**artifact, "record_sha256": summary.digest(artifact)})
                    claim_key = summary.digest({"artifact": artifact, "state": record["validator_before"],
                                                "stream": stream, "policy": policy, "round": round_index})
                    receipt = {"status": "not_reproduced", "task_id": task_id,
                               "phase": task_id, "input": {"synthetic": True}}
                    claim = {"receipts": [{**receipt, "receipt_hash": summary.digest(receipt)}],
                             "status": "completed", "request_hash": f"claim-{claim_key}",
                             "artifact_hash": summary.digest(artifact),
                             "validator_hash": summary.digest(record["validator_before"]),
                             "parsed": {"schema_valid": True}}
                    write(run / "claims" / f"{claim_key}.json", claim)
        write(run / "decisions" / f"r{round_index}.json", decisions)
        write(run / "histories" / f"r{round_index}.json", histories)
    final_rows = []
    for arm in ARMS:
        for stream in [0, 1]:
            for repeat in [0, 1, 2]:
                hard = not (arm == "fixed_validator" and repeat == 0)
                if arm == "evolving_validator" and stream == 0 and repeat == 0:
                    hard = False
                if arm == "noskill" and stream == 0:
                    hard = None if repeat == 0 else repeat != 1
                final_rows.append({"id": "heldout-task", "stream": stream, "arm": arm, "repeat": repeat,
                                   "phase": "holdout", "stage": "final", "hard": hard,
                                   "target_ok": hard is not None, "execution_ok": hard is not None,
                                   "skill_active": arm != "noskill"})
    contrasts = {name: {"primary_macro_cluster_delta": 0.123, "family_cluster_bootstrap": {"ci95": [-0.2, 0.4]},
                       "sentinel_original_methodology": "copied, never recomputed"} for name in summary.CONTRASTS}
    analysis = {"design": {"n_expected_rows": 30, "n_expected_tasks": 1}, "contrasts": contrasts,
                "arms": {arm: {"hard_passes": sum(row["hard"] is True for row in final_rows if row["arm"] == arm),
                               "n_observable": sum(row["hard"] is not None for row in final_rows if row["arm"] == arm)}
                         for arm in ARMS}}
    write(run / "final_rows.json", final_rows)
    write(run / "final_frozen.json", {"protocol_hash": summary.digest(protocol), "states": final_states,
                                      "histories_hash": summary.digest(histories), "freeze_before_holdout": True})
    write(run / "results.json", {"status": "complete", "protocol_hash": summary.digest(protocol),
                                 "final_state_hash": summary.digest(final_states), "final_analysis": analysis})
    write(run / "api" / "calls" / "never-read.json", {"private": "synthetic request sentinel"})
    write(run / ".env", {"private": "synthetic credential sentinel"})
    return run


def test_completion_barrier_reads_nothing_beyond_results(tmp_path, monkeypatch):
    reads = []

    def read(path):
        reads.append(path.name)
        assert path.name == "results.json"
        return b'{"status":"running"}'

    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(ValueError, match="Completion barrier"):
        summary.summarize(tmp_path)
    assert reads == ["results.json"]


def test_complete_summary_counts_and_copies_without_request_reads(complete_run, monkeypatch):
    original_read = Path.read_bytes
    reads = []

    def safe_read(path):
        assert path.name != ".env" and "api" not in path.parts
        reads.append(path)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", safe_read)
    result = summary.summarize(complete_run)
    assert result["proposal_count"] == result["valid_proposals"] == 8
    assert result["decision_counts"] == {"Commit": 4, "Reject": 4}
    assert result["probe_search"]["all"]["actual_logical_search_calls"] == 24
    assert result["probe_search"]["all"]["receipt_status_counts"] == {"not_reproduced": 24}
    assert all(group["planned_search_jobs"] == 6 for group in result["probe_search"]["by_policy_round"].values())
    for row in result["lineage_rounds"]:
        assert row["source_full_oracle"]["conditions"]["candidate"]["passes"] == 2
        assert row["visible_gate_scoped_checks"]["conditions"]["candidate"]["passes"] == 2
        assert row["postdecision_private_gate"]["conditions"]["candidate"]["passes"] == 1
        assert row["probe_search"]["planned_search_jobs"] == 3  # learn repeat 0, both gate repeats
        expected_memories = int(row["policy"] == "evolving_validator")
        assert row["validator_after"]["verified_mismatch_memories"] == expected_memories
    base = result["final_five_arms"]["noskill"]
    assert base["all"] == {"expected": 6, "observable": 5, "passes": 4, "failures": 1, "unknown": 1, "pass_rate": 0.8}
    assert base["per_stream"]["0"]["per_repeat"]["0"]["unknown"] == 1
    assert base["per_repeat_combined_streams"]["0"]["passes"] == 1
    originals = json.loads((complete_run / "results.json").read_text())["final_analysis"]["contrasts"]
    assert set(result["frozen_contrasts"]) == summary.CONTRASTS
    for name, record in result["frozen_contrasts"].items():
        assert record["result"] == originals[name]
        assert record["copied_without_recomputation"] is True
    assert result["new_inferential_tests"] is result["new_thresholds"] is False
    assert "synthetic skill" not in json.dumps(result)
    assert "synthetic request sentinel" not in json.dumps(result)
    assert "results.json" in result["input_sha256"]
    assert reads[0] == complete_run / "results.json"


@pytest.mark.parametrize("relative,error", [("protocol.json", "frozen protocol"),
                                           ("final_frozen.json", "seal mismatch")])
def test_rejects_mismatched_protocol_or_seal(complete_run, relative, error):
    path = complete_run / relative
    value = json.loads(path.read_text())
    value["protocol_hash" if relative == "final_frozen.json" else "version"] = "corrupted"
    write(path, value)
    with pytest.raises(ValueError, match=error):
        summary.summarize(complete_run)


@pytest.mark.parametrize("version,interpretation", [
    ("coding-skill-executable-validator-loop-v1", "harness_confounded_retained_only"),
    ("coding-skill-executable-validator-loop-v2-divmod-runtime", "divmod_runtime_corrected_rerun"),
])
def test_versions_explicitly_labeled_and_never_pooled(complete_run, version, interpretation):
    protocol = json.loads((complete_run / "protocol.json").read_text())
    protocol["version"] = version
    write(complete_run / "protocol.json", protocol)
    for filename in ["results.json", "final_frozen.json"]:
        value = json.loads((complete_run / filename).read_text())
        value["protocol_hash"] = summary.digest(protocol)
        write(complete_run / filename, value)
    result = summary.summarize(complete_run)
    assert result["source_protocol_version"] == version
    assert result["source_run_interpretation"] == interpretation
    assert result["cross_run_statistics_pooled"] is False
    assert summary.compact(result)["source_protocol_version"] == version
    assert "harness-confounded" in result["limitations"][0] if version.endswith("v1") else "separate full rerun" in result["limitations"][0]


def test_target_record_checksum_required(complete_run):
    path = next((complete_run / "targets").glob("*.json"))
    target = json.loads(path.read_text())
    target["code"] = "changed derived code"
    write(path, target)
    with pytest.raises(ValueError, match="Derived target integrity"):
        summary.summarize(complete_run)


def test_receipt_checksum_required(complete_run):
    path = next((complete_run / "claims").glob("*.json"))
    claim = json.loads(path.read_text())
    claim["receipts"][0]["status"] = "verified_mismatch"
    write(path, claim)
    with pytest.raises(ValueError, match="Probe receipt integrity"):
        summary.summarize(complete_run)


def test_missing_claim_is_not_silently_dropped(complete_run):
    next((complete_run / "claims").glob("*.json")).unlink()
    with pytest.raises(FileNotFoundError):
        summary.summarize(complete_run)


def test_unavailable_probe_search_and_invalid_receipts_are_explicit():
    receipt = {"status": "invalid_input"}
    report = summary._probe_summary([
        {"request_hash": None, "status": "target_unavailable", "receipts": []},
        {"request_hash": "attempt", "status": "claim_unavailable", "receipts": []},
        {"request_hash": "valid", "status": "completed", "parsed": {"schema_valid": True},
         "receipts": [{**receipt, "receipt_hash": summary.digest(receipt)}]},
    ])
    assert report["planned_search_jobs"] == 3
    assert report["actual_logical_search_calls"] == 2
    assert report["schema_valid_responses"] == 1
    assert report["invalid_or_unavailable_receipts"] == 1
    assert report["comparable_executed_receipts"] == 0


def test_holdout_memory_rejected_even_with_valid_checksum():
    state = memory(1)
    state.pop("state_hash")
    state["memory"][0]["source_phase"] = "holdout"
    state["state_hash"] = summary.digest(state)
    with pytest.raises(ValueError, match="nondevelopment evidence"):
        summary._memory(state)


def test_final_incomplete_matrix_and_new_contrast_are_rejected(complete_run):
    path = complete_run / "final_rows.json"
    rows = json.loads(path.read_text())
    write(path, rows[:-1])
    with pytest.raises(ValueError, match="wrong row count"):
        summary.summarize(complete_run)
    write(path, rows)
    results = json.loads((complete_run / "results.json").read_text())
    results["final_analysis"]["contrasts"]["fixed_validator_vs_noskill"] = {}
    write(complete_run / "results.json", results)
    with pytest.raises(ValueError, match="two prespecified"):
        summary.summarize(complete_run)


def test_cli_archives_immutably_outside_source_and_prints_summary(complete_run, tmp_path, monkeypatch, capsys):
    before = {path.relative_to(complete_run): path.read_bytes() for path in complete_run.rglob("*") if path.is_file()}
    output = tmp_path / "independent-audit"
    monkeypatch.setattr(sys, "argv", ["summary", "--run", str(complete_run), "--output-dir", str(output), "--stdout"])
    assert summary.main() == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True and printed["archive"]["immutable"] is True
    assert printed["summary"]["proposal_count"] == 8
    archived = (output / "posthoc_summary.json").read_bytes()
    assert summary.main() == 0
    capsys.readouterr()
    assert (output / "posthoc_summary.json").read_bytes() == archived
    after = {path.relative_to(complete_run): path.read_bytes() for path in complete_run.rglob("*") if path.is_file()}
    assert before == after
    monkeypatch.setattr(sys, "argv", ["summary", "--run", str(complete_run), "--output-dir", str(complete_run / "audit")])
    assert summary.main() == 1
    assert json.loads(capsys.readouterr().out)["error_type"] == "ValueError"
    assert not (complete_run / "audit").exists()
