"""Validate a frozen development learning protocol; --execute explicitly runs it.

Usage: python -m scripts.run_continual_learning --manifest ... --panel ...
Add --execute --output NEW_DIR [--gepa-source PINNED_REPO] to run one method.
Authored --fixture controls never execute generated code or contact an API.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skillopt.continual_eval.core import read_json
from skillopt.continual_learning.contracts import validate_manifest
from skillopt.validator_pilot.api import digest


class _FixtureAPI:
    model = "fixture"
    service = {"provider": "fixture", "transport": "offline", "model": "fixture"}

    def __init__(self, method, version=None):
        self.method = method
        if version in {"continual-learning-v6", "continual-learning-v7"}:
            self.service = {**self.service, "delivery_retry_policy": "closed_delivery_error_v3", "max_retries": 2}

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        text = "Handle empty inputs."
        response = ("```\n" + text + "\n```") if self.method == "gepa" else json.dumps({
            "batch_size": 2, "patch": {"reasoning": "Authored engineering fixture", "edits": [
                {"op": "append", "content": text}]}})
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        result = {"request": request, "request_hash": digest(request), "ok": True, "response": response,
                "finish_reason": "stop", "status": 200, "http_attempt_count": 1,
                "usage": {"prompt_tokens": 20, "completion_tokens": 20}}
        if self.service.get("delivery_retry_policy") == "closed_delivery_error_v3":
            result["attempts"] = [{"usage": dict(result["usage"])}]
        return result


def _fixture_evaluate(task, skill):
    success = "Handle empty inputs." in skill
    return ({"status": "available", "output": "authored-fixture-output", "reason": "fixture_no_execution"},
            {"status": "pass" if success else "fail", "score": float(success), "metrics": {},
             "reason": "authored_fixture_not_method_effect"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--method", choices=("gepa", "skillopt"), help="Optional assertion matching the manifest")
    parser.add_argument("--output", help="New private output directory; completed results replay without calls")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]), help="Credential repository")
    parser.add_argument("--gepa-source", help="Reviewed official GEPA source at the pinned commit")
    parser.add_argument("--execute", action="store_true", help="Explicitly authorize this already frozen run")
    parser.add_argument("--fixture", action="store_true", help="Authored offline controls, fixture protocols only")
    args = parser.parse_args(argv)
    value = read_json(args.manifest, sealed=True)
    panel = read_json(args.panel)
    validate_manifest(value, panel)
    method = value["method"]
    if args.method and method != args.method:
        parser.error("--method does not match the frozen learning manifest")
    fixture = value["model"]["provider"] == "fixture"
    if args.fixture and not fixture:
        parser.error("--fixture cannot override natural data/model provenance")
    if not args.execute:
        print(json.dumps({"status": "validated_not_executed", "manifest_hash": value["record_hash"],
                          "method": method, "benchmark": panel["benchmark"], "tasks": len(panel["tasks"]),
                          "train_families": len(value["train_families"]),
                          "selection_families": len(value["selection_families"]),
                          "evidence_kind": value["evidence_kind"], "model_calls_submitted": 0}, indent=2))
        return 0
    if not args.output:
        parser.error("--execute requires --output")
    if fixture and not args.fixture:
        parser.error("Fixture protocols require explicit --fixture execution")
    if method == "gepa" and not args.gepa_source:
        parser.error("GEPA execution requires --gepa-source")
    kwargs = {"repo": args.repo}
    if fixture:
        kwargs.update(fixture_api=_FixtureAPI(method, value["version"]), fixture_evaluate=_fixture_evaluate)
    if method == "gepa":
        from skillopt.continual_learning.gepa import run_stage
        kwargs["gepa_source"] = args.gepa_source
    else:
        from skillopt.continual_learning.skillopt import run_stage
    from skillopt.continual_learning.launch import learning_environment

    with learning_environment(value):
        result = run_stage(value, panel, args.output, **kwargs)
    summary = {k: result[k] for k in ("status", "reason", "record_hash", "evidence_kind", "costs",
                                    "deployment_authorized", "model_calls_submitted") if k in result}
    summary.update(method=method, output=str(Path(args.output).absolute()),
                   learned_improvement_claimed=False)
    if fixture:
        summary["paid_calls"] = 0
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] == "completed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
