"""Public own-synthetic excerpts: consistency checks, never execute model code."""
import ast
import hashlib
import json
import socket
import subprocess
from pathlib import Path

import pytest

from scripts.replay_research_demo import digest, inspect_package

ROOT = Path(__file__).resolve().parents[1] / "examples/research_evidence"
PATH = ROOT / "20260925_repair_chain.json"


def read_demo():
    value = json.loads(PATH.read_text())
    assert value["excerpt_sha256"] == digest({k: v for k, v in value.items() if k != "excerpt_sha256"})
    return value


def test_own_synthetic_chain_keeps_real_repair_and_frozen_rule_binding():
    data = read_demo()
    source, proposal = data["source_repair"], data["skill_proposal"]
    assert source["task_id"] == "synthetic-unrelated-interval_union"
    assert source["before"]["solution_py"].replace("lo <= out[-1][1] + 1", "lo <= out[-1][1]") == source["after"]["solution_py"]
    assert source["before"]["public_check"]["status"] == "fail"
    assert source["after"]["public_check"]["status"] == "pass"
    assert [x["actual"] for x in source["before"]["public_check"]["observations"]] == [False]
    assert [x["actual"] for x in source["after"]["public_check"]["observations"]] == [True]
    assert proposal["repeat"] == 0 and proposal["arm"] == "trajectory"
    assert proposal["rule_skill_hash"] == digest(proposal["candidate"])
    rule = proposal["candidate"]["rules"][0]
    assert rule["evidence_ids"] == [source["evidence_id_used_by_F"]]
    assert rule["evidence_ids"][0] == "ev_" + source["original_supporting_public_detail_hash"][:24]
    assert not proposal["semantic_support_automatically_certified"]
    codes = [source[stage] for stage in ("before", "after")] + data["reverse_policy_execution"]["examples"]
    for item in codes:
        assert hashlib.sha256(item["solution_py"].encode()).hexdigest() == item["solution_sha256"]
        ast.parse(item["solution_py"])  # Parsing, never exec/eval.


def test_reverse_policy_keeps_no_skill_control_and_no_positive_transfer_claim():
    data = read_demo()
    transfer = data["reverse_policy_execution"]
    assert transfer["exposure"] == "raw"
    examples = {e["role"]: e for e in transfer["examples"]}
    assert set(examples) == {"preserve", "replace"}
    assert "use_new_policy and lo == prev[1] + 1" in examples["preserve"]["solution_py"]
    assert "lo <= result[-1][1] + 1" in examples["replace"]["solution_py"]
    for e in examples.values():
        assert e["source"]["rule_skill_hash"] == data["skill_proposal"]["rule_skill_hash"]
        assert e["public_check"]["status"] == "pass" and e["H_summary"]["status"] == "pass"
        assert "not_model_visible" in e["H_summary"]["information_origin"]
    rows = transfer["all_h0_interval_no_skill_and_trajectory_positions"]
    assert len(rows) == 8
    assert {(r["role"], r["repeat"], r["condition"]) for r in rows} == {
        (role, repeat, condition) for role in ("preserve", "replace") for repeat in (0, 1)
        for condition in ("no_skill", "trajectory")}
    assert all(r["public_final_status"] == r["H_final_status"] == "pass" for r in rows)
    for field in ("research_credit", "positive_transfer_established", "independent_certification", "deployment_authorized",
                  "future_independent_evaluation_eligible", "artifact_code_execution_performed_for_export"):
        assert data[field] is False


def test_failed_proposal_and_two_unknowns_are_not_repaired_or_semantic_wins():
    data = read_demo()
    failed = data["retained_negative_examples"]["F_invalid"]
    assert failed["repeat"] == 1 and not failed["used_as_primary_candidate"]
    assert failed["status"] == "invalid" and failed["finish_reason"] == "stop"
    assert failed["response"].startswith("NO_UPDATE\n\n")
    assert hashlib.sha256(failed["response"].encode()).hexdigest() == failed["response_sha256"]
    with pytest.raises(json.JSONDecodeError):
        json.loads(failed["response"])
    unknowns = data["retained_negative_examples"]["T_format_unknowns"]
    assert len(unknowns) == len({r["request_hash"] for r in unknowns}) == 2
    assert sum(r["nominal_positions"] for r in unknowns) == 6
    for row in unknowns:
        assert row["availability"] == "parse_failure" and row["api_response_ok"] is True
        assert row["finish_reason"] == "stop" and row["parse_error"].startswith("JSONDecodeError:")
        assert row["public_check_status"] == row["H_summary_status"] == "unknown"
        assert row["no_executable_artifact_or_semantic_failure_claimed"] is True
        assert set(row["aliased_conditions"]) == {"no_skill", "current", "summary_only"}
    full = data["full_T_context"]
    assert full["nominal_positions"] == 24 * 3 * 2 * 4 == 576
    assert full["H_final_counts"]["raw/trajectory"] == {"pass": 144, "fail": 0, "unknown": 0}
    for condition in ("no_skill", "current", "summary_only"):
        assert full["H_final_counts"]["raw/" + condition] == {"pass": 142, "fail": 0, "unknown": 2}


def test_excerpt_sanitization_and_read_only_no_network_or_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No model code, subprocess or network is allowed")
    before = PATH.read_bytes()
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    data = read_demo()
    forbidden_keys = {"api_key", "apikey", "authorization", "service", "api_receipt", "reasoning_content",
                      "host_only", "audit_inputs", "audit_cases", "reference_code", "audit_runner", "url"}
    def walk(value):
        if isinstance(value, dict):
            assert not set(value) & forbidden_keys
            for key, item in value.items():
                if key == "local_source":
                    assert item.startswith("outputs/skill_validation/") and ".." not in Path(item).parts
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            assert not any(marker in value for marker in ("https://", "http://", "/Users/", "/root/", "Bearer "))
    walk(data)
    result = inspect_package()
    assert result["model_calls"] == 0 and not result["executed_artifact_code"]
    assert result["final_positions"] == 96  # Historical benchmark table is unchanged.
    assert PATH.read_bytes() == before
