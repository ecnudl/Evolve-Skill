"""Tiny live-API Research smoke on disclosed, handwritten engineering fixtures.

The two external-fact questions are DECLARED BY THE CALLER, not discovered by
the model. There is no natural-task efficacy experiment, solver, hidden oracle,
Skill update, or Research-generation ablation. At most six model calls are
reserved. Generated test code is never executed locally; fixture programs run
only through the existing isolated Linux executor.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import CachedAPI, digest
from skillopt.skill_validation.admissibility import execute_admitted, review_proposal
from skillopt.skill_validation.admissibility_study import _FailClosedExecutor
from skillopt.skill_validation.checks import CallableTask, PublicCase
from skillopt.skill_validation.models import ArtifactRecord, Obligation, SourceFile, TaskContract, require
from skillopt.skill_validation.natural_documents import SSHDocumentFetcher
from skillopt.skill_validation.natural_study import ExecutorPool, _write
from skillopt.skill_validation.panel import checked_path
from skillopt.skill_validation.probe_fact_research import resolve_gap
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.skill_validation.task_probes import parse_probes

VERSION = "caller-declared-fact-fixture-smoke-v1"
REQUEST_LIMIT = 6


def fixtures():
    """The same overgeneralized check meets two different public contracts."""
    cases = []
    for name, explicit in (("whitespace_api", False), ("literal_space_near_miss", True)):
        api = "str.split(' ') with the explicit separator U+0020" if explicit else "str.split(None) with no explicit separator"
        contract_quote = "Return exactly the Python 3.11 " + api + " result for the supplied text."
        prompt = ("Implement split_tokens(text: str) -> list[str]. " + contract_quote
                  + " Public example: split_tokens('a b') returns ['a', 'b']. Do not impose other normalization.")
        contract = TaskContract("fixture-" + name, "fixture-" + name, "fixture-api-splitting",
            "handwritten-engineering-fixtures", "development", "coding", "explicit_api_contract", prompt,
            (Obligation("result", "requested_behavior", "Follow the stated API semantics", contract_quote),))
        public = PublicCase("ordinary-space", json.dumps({"args": ["a b"], "kwargs": {}}),
            "Public example: split_tokens('a b') returns ['a', 'b'].", ("result",), expected_json='["a", "b"]')
        task = CallableTask(contract, "solution", "split_tokens", (public,))
        # This remains a hypothesis. It is deliberately inapplicable to the
        # explicit-separator near miss; Research may not fix its expected value.
        proposal = parse_probes({"probes": [{"kind": "expected", "calls": [{"args": ["a\u00a0b"], "kwargs": {}}],
            "expected": ["a", "b"], "obligation_id": "result", "contract_quote": contract_quote,
            "rationale": "Hypothesis: U+00A0 separates these tokens under the API explicitly required by the task."}]}, task, max_probes=1)
        question = ("Under Python 3.11 " + ("str.split(' ')" if explicit else "str.split(None)")
            + ", is U+00A0 NO-BREAK SPACE a delimiter, or is it preserved inside a token? "
              "Resolve only this documented API fact; do not alter the proposed check.")
        artifacts = []
        for label, use_literal in (("intended_conforming", explicit), ("intended_counterexample", not explicit)):
            source = "def split_tokens(text):\n    return text.split(" + ("' '" if use_literal else "None") + ")\n"
            artifact = ArtifactRecord(contract.content_hash, 0, "unassigned", "fixture-no-learned-skill",
                hashlib.sha256(b"").hexdigest(), (SourceFile("solution.py", source),), "available", "fixture",
                True, False, "handwritten-fixture:" + name + ":" + label, digest(source))
            artifacts.append((label, artifact))
        cases.append({"name": name, "task": task, "proposal": proposal, "question": question,
            "artifacts": artifacts, "host_fixture_expectation": "abstain" if explicit else "keep"})
    return cases


def run(repo, output, executor, document_fetcher, *, api_proxy=None):
    repo, output = checked_path(repo), checked_path(output)
    require(output.is_relative_to(repo / "outputs/skill_validation")
            and output != repo / "outputs/skill_validation", "Dedicated skill_validation output required")
    require(type(document_fetcher.identity) is dict and document_fetcher.identity,
            "Explicit document transport identity required")
    require("question_origin" in inspect.signature(resolve_gap).parameters,
            "This smoke requires resolve_gap's explicit caller_declared_fixture_gap provenance interface")
    cases = fixtures()
    manifest = seal({"version": VERSION, "provenance": "handwritten_engineering_fixture",
        "question_origin": "caller_declared_not_model_discovered", "cases": [{
            "name": case["name"], "task": case["task"].to_dict(), "proposal": case["proposal"],
            "question": case["question"], "host_fixture_expectation": case["host_fixture_expectation"],
            "artifacts": [{"label": label, "artifact": artifact.to_dict()} for label, artifact in case["artifacts"]]}
            for case in cases], "hidden_oracle_available": False})
    paths = [Path(__file__).resolve(), *sorted((ROOT / "skillopt").rglob("*.py"))]
    snapshot = seal({"files": {str(path.relative_to(ROOT)): path.read_text(encoding="utf-8") for path in paths}})
    guarded = _FailClosedExecutor(executor)
    with CachedAPI(repo, output / "api", workers=1, stream=True, reasoning_effort="low",
                   provider="bigmodel", proxy=api_proxy) as api:
        protocol = seal({"version": VERSION, "manifest_hash": manifest["record_hash"],
            "source_snapshot_hash": snapshot["record_hash"], "service": api.service,
            "executor": executor.identity, "executor_transport": executor.transport_identity,
            "document_transport": document_fetcher.identity, "request_limit": REQUEST_LIMIT,
            "output_token_limit_per_request": 2048, "question_origin": "caller_declared_not_model_discovered",
            "research_role": "fact_assisted_review_of_fixed_checks_not_generation_ablation",
            "review_after_no_evidence": "public_contract_only_fallback_separately_reported",
            "provenance": "handwritten_engineering_fixture", "new_solver_calls": 0,
            "hidden_oracle_access": False, "skill_update_calls": 0, "deployment_authorized": False,
            "feedback_authorized": False, "final_access": False})
        # Immutable configuration and source are bound BEFORE the first request.
        _write(output / "protocol.json", protocol)
        _write(output / "source_snapshot.json", snapshot)
        _write(output / "fixture_manifest.json", manifest)
        calls = BoundedCalls(api, output / "model_budget", protocol["record_hash"], REQUEST_LIMIT)
        records = []
        for case in cases:
            pipeline = digest({"protocol": protocol["record_hash"], "case": case["name"]})
            root = output / "cases" / case["name"]
            task, proposal = case["task"], case["proposal"]
            fact = resolve_gap(task, proposal["probes"][0], case["question"], calls, root / "research",
                pipeline_hash=pipeline, source_fetcher=document_fetcher, question_origin="caller_declared_fixture_gap")
            require(fact["question_origin"] == "caller_declared_fixture_gap"
                    and fact["binding"]["question_origin"] == "caller_declared_fixture_gap",
                    "Research receipt must bind the declared, non-model-discovered question origin")
            sources = fact["sources"] if fact["status"] == "evidence_selected" else []
            review = review_proposal(task, proposal, calls, root / "review", pipeline_hash=pipeline, sources=sources)
            executions = []
            for label, artifact in case["artifacts"]:
                admitted = execute_admitted(task, artifact, proposal, review, guarded, root / "execution",
                    pipeline_hash=pipeline)
                reasons = [o["reason"] for p in (admitted["execution_report"] or {}).get("probes", [])
                           for o in p["observations"]]
                require(not guarded.failed.is_set() and not any(reason.startswith("executor_exception_")
                        or reason == "interrupted_call_no_resampling" for reason in reasons),
                        "Execution infrastructure failed; stop further model requests, retain receipts")
                executions.append({"host_fixture_label": label, "artifact_hash": artifact.content_hash,
                    "admitted_report_hash": admitted["record_hash"], "probe_status": admitted["probe_status"],
                    "retained_checks": admitted["retained_checks"]})
            record = seal({"name": case["name"], "task_hash": task.content_hash,
                "proposal_hash": proposal["record_hash"], "pipeline_hash": pipeline,
                "fact_result_hash": fact["record_hash"], "fact_status": fact["status"],
                "selected_source_count": len(sources), "question_origin": "caller_declared_not_model_discovered",
                "review_hash": review["record_hash"], "review_status": review["status"],
                "review_decisions": review["decisions"], "review_had_research_evidence": bool(sources),
                "host_fixture_expectation": case["host_fixture_expectation"], "executions": executions,
                "natural_method_efficacy": False, "research_incremental_effect_established": False})
            _write(root / "result.json", record)
            records.append(record)
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "cases": records,
            "cost": calls.accounting(), "provenance": "handwritten_engineering_fixture",
            "question_origin": "caller_declared_not_model_discovered", "natural_method_efficacy": False,
            "research_incremental_effect_established": False, "new_solver_calls": 0, "skill_update_calls": 0,
            "hidden_oracle_access": False, "final_access": False, "deployment_authorized": False,
            "feedback_authorized": False, "gate": "not_applicable_fixture_only",
            "limitations": ["Human-declared gaps and fixture intentions are not independently discovered errors.",
                "Two related fixture tasks provide no statistical or cross-domain effectiveness evidence.",
                "No documents, abstention and unsuccessful checks are valid outcomes, not retried for success.",
                "Without selected evidence the reviewer is a public-contract-only fallback, not a Research success."]})
        _write(output / "results.json", result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--api-proxy")
    args = parser.parse_args(argv)
    executor = ExecutorPool(args.remote_repo, workers=1)
    try:
        result = run(args.repo, args.output, executor, SSHDocumentFetcher(args.remote_repo), api_proxy=args.api_proxy)
    finally:
        executor.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
