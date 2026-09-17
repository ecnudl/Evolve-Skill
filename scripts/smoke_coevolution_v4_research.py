"""Separate six-call research-chain smoke on one pinned historical DEV failure.

This is not a continuation, repair, rerun, or efficacy result of the primary V4
study. No candidate code is executed, no validator is promoted, and no final or
calibration artifact is consumed. `prepare` is offline; `run` makes at most six
logical PJLAB calls using the existing configuration without modifying it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib import metadata
from pathlib import Path

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v4 import validator
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "coevolution-v4-secondary-research-chain-smoke-v1"
SOURCE_RUN = "outputs/coevolution_v3/glm53_multifile_20260909_v1"
SOURCE_CLAIM = "claims/2cff374d25c86c2184d9a2d009d31237eef5a3e5512ec69d0c1249b14e57a45d.json"
SOURCE_TARGET = "targets/a1a0986ee572574403e84f60cf879e01db04043dd4728cdd8209d00098ed280c.json"
SOURCE_API = "api/calls/b0791e8e57f65d9f65cf7b2c9f8a6e31a2e09a62a5b0fb0a837875cf0a776df3.json"
EXPECTED_TASK = "repo-v3-incremental_build_graph-local-update"
EXPECTED_RECEIPT = "8a34daa82f35bf46e706fcf9cf00d6f5e6df308297e4953bea7f926ee7f3b933"
EXPECTED_CANDIDATE = "b958e9664e64eb43a08eddd34c2faec6f8e5e143db61e39ccc682846a6b2b4b9"
EXPECTED_CONTRACT = "bb403edb39cde04c1af1ad2666175e8fbe4fb7830f75a2b74e0bc80d49c2dfdd"
EXPECTED_INPUT = {"action": "apply", "changed": ["d"],
                  "graph": {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []},
                  "targets": ["b", "c", "a"]}
ARMS = ("feedback", "research")
MAX_CALLS = 6
MAX_TOKENS_EACH = 6000
PROTOCOL_DOC = "docs/coevolution-v4-research-smoke-protocol.md"
SOURCES = (
    "scripts/smoke_coevolution_v4_research.py", PROTOCOL_DOC,
    "skillopt/coevolution_v4/validator.py", "skillopt/coevolution_v3/validator.py",
    "skillopt/coevolution/validator.py", "skillopt/coevolution/budget.py",
    "skillopt/validator_pilot/api.py", "skillopt/validator_pilot/tasks.py",
    "skillopt/validator_pilot/research.py", "skillopt/validator_document_transport.py",
)
LIMITS = [
    "Secondary engineering feature smoke, separate from the primary V4 three-arm experiment.",
    "One deliberately selected, previously reported natural DEVELOPMENT failure; not a representative sample.",
    "No main-study final result, calibration artifact, hidden benchmark, or reference implementation is used as feedback.",
    "The historical executable differential is an observation under an assumed reference, not universal correctness proof.",
    "Official-document provenance and successful schema delivery are not evidence that research improves validation.",
    "No new probe execution, independent calibration, Skill update, validator promotion, or deployment occurs.",
    "Both arms have three calls capped at 6000 tokens; actual provider usage is recorded, not equalized retrospectively.",
    "Transport has at most three HTTP attempts per logical call; malformed content is terminal and never rerolled.",
    "If research planning, fetching, quotation, or revision fails, report that failure without changing this protocol.",
]


def _read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate source JSON key")
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError("Nonfinite source JSON")
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)


def _file(repo, relative):
    root, path = Path(repo).resolve(), Path(repo).resolve() / relative
    if not path.resolve().is_relative_to(root) or any(parent.is_symlink() for parent in (path, *path.parents)
                                                    if parent != root and root in parent.parents):
        raise ValueError("Source path escaped repository or used a symlink")
    return path


def _v3_record(path):
    record = _read(path)
    if not isinstance(record, dict):
        raise ValueError("Expected V3 object record")
    payload = {key: value for key, value in record.items() if key != "record_sha256"}
    if record.get("record_sha256") != digest(payload):
        raise ValueError("Historical V3 record checksum mismatch")
    return payload


def load_development_packet(repo):
    """Read only three pinned DEV files; never open tasks_private or final data."""
    repo = Path(repo).resolve()
    paths = {"claim": _file(repo, SOURCE_RUN + "/" + SOURCE_CLAIM),
             "target": _file(repo, SOURCE_RUN + "/" + SOURCE_TARGET),
             "api": _file(repo, SOURCE_RUN + "/" + SOURCE_API)}
    claim, target, call = _v3_record(paths["claim"]), _v3_record(paths["target"]), _read(paths["api"])
    if (target.get("id") != EXPECTED_TASK or target.get("phase") != "learn1" or target.get("stage") != "r1"
            or target.get("stream") != 0 or target.get("repeat") != 0 or target.get("target_ok") is not True):
        raise ValueError("Pinned historical target is not the intended natural learning artifact")
    files = target.get("files")
    if not isinstance(files, dict) or digest(files) != EXPECTED_CANDIDATE or claim.get("artifact_hash") != EXPECTED_CANDIDATE:
        raise ValueError("Historical candidate files do not match the pinned artifact")
    request = call.get("request")
    if (not isinstance(request, dict) or digest(request) != paths["api"].stem
            or call.get("request_hash") != paths["api"].stem or target.get("request_hash") != paths["api"].stem
            or request.get("key") != paths["target"].stem or request.get("kind") != "repo_target"
            or request.get("model") != "glm-5.3" or call.get("ok") is not True
            or target.get("response") != call.get("response")):
        raise ValueError("Historical target is not bound to its actual successful model call")
    source_user = json.loads(request["user"])
    public = source_user.get("task")
    allowed = {"id", "prompt", "files", "editable_paths", "input_domain", "public_cases", "entry_module", "entry_function"}
    if (not isinstance(public, dict) or set(public) != allowed or public["id"] != EXPECTED_TASK
            or digest(public["prompt"]) != EXPECTED_CONTRACT):
        raise ValueError("Historical source call lacks the exact public-only task contract")
    matches = [row for row in claim.get("receipts", []) if row.get("receipt_hash") == EXPECTED_RECEIPT]
    if len(matches) != 1:
        raise ValueError("Expected exactly one pinned natural differential receipt")
    receipt = matches[0]
    payload = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if digest(payload) != EXPECTED_RECEIPT:
        raise ValueError("Historical differential receipt checksum mismatch")
    if (receipt.get("phase") != "learn1" or receipt.get("task_id") != EXPECTED_TASK
            or receipt.get("candidate_hash") != EXPECTED_CANDIDATE or receipt.get("contract_hash") != EXPECTED_CONTRACT
            or receipt.get("status") != "verified_mismatch" or receipt.get("reason") != "return_value_difference"
            or receipt.get("input") != EXPECTED_INPUT or receipt.get("input_preserved") is not True):
        raise ValueError("Pinned receipt is not the declared development behavioral mismatch")
    path, quote, clause = receipt.get("candidate_path"), receipt.get("candidate_quote"), receipt.get("clause_quote")
    if (path not in files or not isinstance(quote, str) or quote not in files[path]
            or not isinstance(clause, str) or clause not in public["prompt"]):
        raise ValueError("Natural failure is not grounded in its delivered files and task contract")
    ref, actual = receipt.get("reference_observation", {}), receipt.get("candidate_observation", {})
    expected_values = ({"result": ["d", "b", "c", "a"], "api_version": 1},
                       {"result": ["d", "b", "a"], "api_version": 1})
    for observation, expected in zip((ref, actual), expected_values):
        if (observation.get("ok") is not True or observation.get("exception") is not None
                or observation.get("input_unchanged") is not True or observation.get("value") != expected):
            raise ValueError("Historical observed differential changed")
    packet = {"split": "development", "source_phase": "learn1", "classification": "semantic",
              "failure_kind": "behavior", "research_trigger": True, "task_id": EXPECTED_TASK,
              "contract": public["prompt"], "contract_hash": EXPECTED_CONTRACT,
              "input_domain": public["input_domain"], "files": files, "artifact_hash": EXPECTED_CANDIDATE,
              "failed_cases": [{"input": receipt["input"], "expected": ref["value"], "actual": actual["value"],
                                "clause": clause, "candidate_path": path, "candidate_quote": quote}],
              "historical_receipt_hash": EXPECTED_RECEIPT,
              "observed_gap": "In the shared-prerequisite diamond, an already visited dependency returns None instead of its cached dirtiness; node c is omitted.",
              "research_question": "Which language return-value or graph-traversal assumptions explain the missing propagation, and how should a legal counterexample search distinguish shared traversal state from task-specific output policy?",
              "reference_is_assumption": True, "differential_evidence_not_contract_proof": True,
              "task_contract_has_priority_over_generic_documentation": True,
              "source_selected_from_previously_reported_v3_development_not_main_v4_final": True}
    packet["evidence_hash"] = digest(packet)
    provenance = {"source_files": {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in paths.values()},
                  "receipt_hash": EXPECTED_RECEIPT, "candidate_hash": EXPECTED_CANDIDATE,
                  "contract_hash": EXPECTED_CONTRACT, "source_request_hash": call["request_hash"],
                  "source_phase": "learn1", "reference_implementation_read": False,
                  "tasks_private_or_final_artifacts_read": False}
    return packet, provenance


def source_hashes(repo):
    return {relative: hashlib.sha256(_file(repo, relative).read_bytes()).hexdigest() for relative in SOURCES}


def _output_root(repo, root):
    repo, root = Path(repo).resolve(), Path(root).resolve()
    parent = repo / "outputs/coevolution_v4_research_smoke"
    if root == parent or not root.is_relative_to(parent):
        raise ValueError("Smoke output must be its own run beneath outputs/coevolution_v4_research_smoke")
    return root


def prepare(repo, root):
    repo, root = Path(repo).resolve(), _output_root(repo, root)
    packet, provenance = load_development_packet(repo)
    initial = validator.initial_state()
    if validator.MAX_EVOLUTION_CALLS != 3 or validator.MAX_STAGE_TOKENS != MAX_TOKENS_EACH:
        raise ValueError("Imported validator no longer matches the six-call smoke cap")
    if not validator.research_trigger([packet])["triggered"]:
        raise ValueError("Pinned behavioral receipt no longer triggers bounded research")
    protocol = {"version": VERSION, "purpose": "secondary_engineering_feature_smoke_not_efficacy",
                "arms": list(ARMS), "arm_order": list(ARMS), "model": "glm-5.3", "workers": 4,
                "execution": "sequential_arms_after_main_run", "max_logical_calls": MAX_CALLS,
                "max_calls_per_arm": 3, "max_tokens_per_call": MAX_TOKENS_EACH,
                "max_http_attempts_per_logical_call": 3, "max_http_attempts": 18,
                "packet_hash": digest(packet), "provenance": provenance, "initial_state_hash": digest(initial),
                "source_hashes": source_hashes(repo), "python_version": platform.python_version(),
                "httpx_version": metadata.version("httpx"), "new_candidate_executions": 0,
                "independent_calibration": False, "validator_activation": False,
                "main_study_outputs_modified": False, "main_final_feedback_used": False,
                "semantic_retries": 0, "limits": LIMITS}
    # Every immutable protocol/evidence record is published before opening a
    # model client; prepare needs neither credentials nor network access.
    write_immutable_json(root / "protocol.json", protocol)
    write_immutable_json(root / "development_packet.json", packet)
    write_immutable_json(root / "initial_state.json", initial)
    verify(repo, root)
    return protocol


def verify(repo, root):
    root = _output_root(repo, root)
    protocol = _read(root / "protocol.json")
    packet, provenance = load_development_packet(repo)
    if (protocol.get("version") != VERSION or protocol.get("source_hashes") != source_hashes(repo)
            or protocol.get("provenance") != provenance or protocol.get("packet_hash") != digest(packet)
            or _read(root / "development_packet.json") != packet
            or protocol.get("initial_state_hash") != digest(validator.initial_state())
            or _read(root / "initial_state.json") != validator.initial_state()
            or protocol.get("max_logical_calls") != MAX_CALLS or protocol.get("max_tokens_per_call") != MAX_TOKENS_EACH
            or protocol.get("arms") != list(ARMS) or protocol.get("validator_activation") is not False):
        raise ValueError("Frozen research smoke protocol, source, or evidence changed")
    return protocol


def _summary(arm, proposal):
    research = proposal["research"]
    findings = (research.get("findings") or {}).get("findings", [])
    source_backed = [row for row in findings if row.get("evidencequotes")]
    return {"arm": arm, "proposal_status": proposal["status"], "proposed_validator_schema_valid": proposal.get("proposed_state") is not None,
            "research_requested": research["requested"], "research_executed": research["executed"],
            "fetch_status": research["fetch_status"], "sources_requested": research["sources_requested"],
            "sources_available": research["sources_available"], "source_snapshots": research["source_snapshots"],
            "parsed_findings": len(findings), "source_backed_findings": len(source_backed),
            "verified_exact_quotes": sum(len(row["evidencequotes"]) for row in source_backed),
            "stages": proposal["stages"], "calls_used": proposal["calls_used"],
            "activation": "none_no_calibration", "provenance_is_not_entailment_or_efficacy": True}


def run(repo, root, *, api_factory=None):
    protocol = prepare(repo, root)
    root = _output_root(repo, root)
    if (root / "results.json").exists():
        return report(repo, root)
    factory = BudgetedAPI if api_factory is None else api_factory
    packet, initial = _read(root / "development_packet.json"), _read(root / "initial_state.json")
    summaries = []
    with factory(Path(repo), root / "api", max_calls=MAX_CALLS, workers=4) as api:
        for arm in ARMS:
            verify(repo, root)
            proposal = validator.evolve(api, initial, [packet], root / "arms" / arm,
                                         key="secondary-natural-v3-dev-smoke-" + arm,
                                         use_research=arm == "research")
            summary = _summary(arm, proposal)
            write_immutable_json(root / (arm + "_summary.json"), summary)
            summaries.append(summary)
        ledger = api.ledger()
    if sum(row["calls_used"] for row in summaries) != MAX_CALLS or ledger["cached_logical_calls"] != MAX_CALLS:
        raise ValueError("Smoke did not complete exactly the predeclared six logical calls")
    verify(repo, root)
    result = {"version": VERSION, "status": "complete", "protocol_hash": digest(protocol),
              "purpose": "secondary_research_chain_engineering_not_primary_efficacy_result",
              "arms": summaries, "ledger": ledger, "no_validator_promoted": True,
              "main_final_feedback_used": False, "main_results_modified": False,
              "candidate_executions": 0, "interpretation": LIMITS}
    result["result_hash"] = digest(result)
    write_immutable_json(root / "results.json", result)
    return result


def report(repo, root):
    protocol = verify(repo, root)
    result = _read(Path(root) / "results.json")
    core = {key: value for key, value in result.items() if key != "result_hash"}
    if (result.get("result_hash") != digest(core) or result.get("protocol_hash") != digest(protocol)
            or result.get("no_validator_promoted") is not True or result.get("main_final_feedback_used") is not False):
        raise ValueError("Frozen smoke result integrity mismatch")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = {"prepare": prepare, "run": run, "report": report}[args.action](args.repo, args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
