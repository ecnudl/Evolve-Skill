"""Bounded PJLAB proposal transport; fixture connectivity is not method efficacy.

Four logical calls at most, one worker, 2048 output tokens per call. CachedAPI
may make up to three HTTP attempts per logical call. It retains token usage only
for the terminal attempt, so retry-inclusive token cost is explicitly unknown.
No candidate code, hidden audit, calibration, Skill update or deployment runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import CachedAPI, digest, write_immutable_json

from .fixtures import smoke_cases
from .models import require, text
from .research import BoundedResearch, ModelReply, ResearchBudget, fetch_documents, fixed_rubric
from .views import DevelopmentGap, research_development_view

VERSION = "skill-validation-proposal-transport-v1"
MAX_LOGICAL_CALLS = 4
MAX_OUTPUT_TOKENS = 2048


class ProposalTransportError(RuntimeError):
    """Only a fixed category is exposed; never copy provider exception text."""


def _path(path):
    result = Path(path).absolute()
    require(not any(p.is_symlink() for p in (result, *result.parents)), "Symlink proposal cache unsupported")
    return result


def _read(path):
    path = _path(path)
    require(path.is_file() and path.stat().st_size <= 8_000_000, "Missing or oversized proposal receipt")
    return verify(json.loads(path.read_text(encoding="utf-8")))


def _usage(value):
    return value if type(value) is int and value >= 0 else None


class ProposalTransport:
    def __init__(self, api, root):
        require(api.model == "glm-5.3" and api.workers == 1, "Proposal pilot requires glm-5.3 and one worker")
        require(type(api.service) is dict and type(api.service.get("max_retries")) is int
                and 0 <= api.service["max_retries"] <= 2, "At most two bounded upstream retries allowed")
        self.api, self.root = api, _path(root)
        self.api_root = _path(api.root)
        self.events = []
        write_immutable_json(_path(self.root / "transport.json"), seal({"version": VERSION, "model": api.model,
            "service_hash": digest(api.service), "workers": 1, "max_logical_calls": MAX_LOGICAL_CALLS,
            "max_output_tokens": MAX_OUTPUT_TOKENS, "max_http_attempts_per_logical_call": api.service["max_retries"] + 1,
            "cached_failure_is_terminal": True, "interrupted_intent_requires_manual_review": True}))

    def __call__(self, system, user, max_output_tokens):
        text(system, maximum=120000)
        text(user, maximum=120000)
        require(len((system + user).encode("utf-8")) <= 120000, "Proposal prompt exceeds byte budget")
        require(type(max_output_tokens) is int and 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS,
                "Proposal output exceeds fixed 2048-token cap")
        request = {"version": VERSION, "system_hash": digest(system), "user_hash": digest(user),
                   "model": self.api.model, "service_hash": digest(self.api.service), "max_output_tokens": max_output_tokens}
        key = digest(request)
        upstream_request = {"model": self.api.model, "system": system, "user": user,
                            "kind": "stage2-rubric-proposal", "key": key, "max_tokens": max_output_tokens,
                            "repeat": 0, "service": self.api.service}
        upstream_hash = digest(upstream_request)
        upstream_path = _path(self.api_root / "calls" / (upstream_hash + ".json"))
        terminal = _path(self.root / "terminal" / (key + ".json"))
        intent = _path(self.root / "intents" / (key + ".json"))
        if terminal.exists():
            record = _read(terminal)
            require(record["request"] == request and intent.is_file() and _read(intent)["request"] == request,
                    "Proposal terminal/intent identity mismatch")
            self._verify_upstream(record, upstream_request, upstream_path)
            self.events.append({"key": key, "cached": True, "new_http_attempts": 0})
            return self._reply(record, cached=True)
        if intent.exists():
            require(_read(intent)["request"] == request, "Interrupted proposal request changed")
            self.events.append({"key": key, "cached": False, "new_http_attempts": None,
                                "error": "interrupted_transport_intent"})
            raise ProposalTransportError("interrupted_transport_intent")
        require(len(list(_path(self.root / "intents").glob("*.json"))) < MAX_LOGICAL_CALLS,
                "Four-logical-call proposal budget exhausted")
        write_immutable_json(intent, seal({"request": request, "upstream_request_hash": upstream_hash}))
        cached_before = upstream_path.exists()
        base = {"version": VERSION, "request": request, "upstream_request_hash": upstream_hash,
                "upstream_cache_ref": "calls/" + upstream_hash + ".json", "upstream_record_hash": None,
                "status": "transport_failure", "error": "api_call_exception", "response": None,
                "input_tokens_terminal_attempt": None, "output_tokens_terminal_attempt": None,
                "upstream_http_attempt_count": None, "http_attempts": [],
                "new_http_attempt_count": None, "upstream_cached_before_call": cached_before,
                "all_attempt_token_usage_complete": False}
        try:
            upstream = self.api.call(system, user, "stage2-rubric-proposal", key, max_tokens=max_output_tokens, repeat=0)
            require(type(upstream) is dict and upstream.get("request_hash") == upstream_hash
                    and upstream.get("request") == upstream_request, "Upstream request cache mismatch")
            require(upstream_path.is_file() and json.loads(upstream_path.read_text(encoding="utf-8")) == upstream,
                    "Upstream call must have its durable terminal receipt")
            attempts = upstream.get("attempts")
            count = upstream.get("http_attempt_count")
            require(type(attempts) is list and type(count) is int and 1 <= count <= self.api.service["max_retries"] + 1
                    and len(attempts) == count, "Malformed upstream HTTP attempt accounting")
            clean_attempts = []
            for index, attempt in enumerate(attempts):
                require(type(attempt) is dict and attempt.get("attempt") == index + 1 and type(attempt.get("ok")) is bool,
                        "Malformed upstream attempt sequence")
                status = attempt.get("status")
                clean_attempts.append({"attempt": index + 1, "ok": attempt["ok"],
                                       "http_status": status if type(status) is int and 100 <= status <= 599 else None,
                                       "error": None if attempt["ok"] else "upstream_attempt_failed"})
            usage = upstream.get("usage") if type(upstream.get("usage")) is dict else {}
            input_tokens, output_tokens = _usage(usage.get("prompt_tokens")), _usage(usage.get("completion_tokens"))
            response = upstream.get("response")
            ok = upstream.get("ok") is True and type(response) is str and bool(response.strip())
            if ok and output_tokens is not None:
                require(output_tokens <= max_output_tokens, "Upstream violated output token budget")
            base.update(status="completed" if ok else "api_failure", error=None if ok else "upstream_terminal_failure",
                        response=response if ok else None, upstream_record_hash=digest(upstream),
                        input_tokens_terminal_attempt=input_tokens, output_tokens_terminal_attempt=output_tokens,
                        upstream_http_attempt_count=count, http_attempts=clean_attempts,
                        new_http_attempt_count=0 if cached_before else count,
                        all_attempt_token_usage_complete=count == 1 and input_tokens is not None and output_tokens is not None)
        except Exception:
            # Do not log str(exc), headers, API credentials, or arbitrary response
            # errors. Missing durable upstream accounting stays unknown, not zero.
            base["error"] = "api_call_or_receipt_validation_failed"
        record = seal(base)
        write_immutable_json(terminal, record)
        self.events.append({"key": key, "cached": cached_before, "new_http_attempts": record["new_http_attempt_count"]})
        return self._reply(record, cached=cached_before)

    def _verify_upstream(self, record, request, path):
        if record["upstream_record_hash"] is None:
            return
        require(path.is_file() and path.stat().st_size <= 8_000_000, "Missing upstream receipt on proposal replay")
        upstream = json.loads(path.read_text(encoding="utf-8"))
        require(digest(upstream) == record["upstream_record_hash"] and upstream.get("request") == request
                and upstream.get("request_hash") == digest(request), "Upstream terminal receipt changed")

    @staticmethod
    def _reply(record, *, cached):
        if record["status"] != "completed":
            raise ProposalTransportError(record["error"])
        return ModelReply(record["response"], record["input_tokens_terminal_attempt"],
                          record["output_tokens_terminal_attempt"], cached=cached)

    def accounting(self):
        records = [_read(p) for p in sorted(_path(self.root / "terminal").glob("*.json"))]
        intents = list(_path(self.root / "intents").glob("*.json"))
        complete = bool(records) and len(records) == len(intents) and all(r["all_attempt_token_usage_complete"] for r in records)
        attempts_known = len(records) == len(intents) and all(r["upstream_http_attempt_count"] is not None for r in records)
        return {"logical_requests_reserved": len(intents), "terminal_logical_receipts": len(records),
                "interrupted_without_terminal": len(intents) - len(records),
                "terminal_status_counts": {status: sum(r["status"] == status for r in records)
                                           for status in ("completed", "api_failure", "transport_failure")},
                "retained_upstream_http_attempts": sum(r["upstream_http_attempt_count"] for r in records) if attempts_known else None,
                "new_http_attempts_this_invocation": sum(e["new_http_attempts"] for e in self.events)
                    if all(e["new_http_attempts"] is not None for e in self.events) else None,
                "all_attempt_token_usage_complete": complete,
                "input_tokens_all_attempts": sum(r["input_tokens_terminal_attempt"] for r in records) if complete else None,
                "output_tokens_all_attempts": sum(r["output_tokens_terminal_attempt"] for r in records) if complete else None,
                "terminal_attempt_usage": [{"request_hash": r["upstream_request_hash"],
                    "input_tokens": r["input_tokens_terminal_attempt"], "output_tokens": r["output_tokens_terminal_attempt"]} for r in records],
                "note": "Logical calls are not HTTP attempts. Earlier retry token usage is not retained by CachedAPI."}


def fixture_development_views():
    views = []
    for name, task, artifact, _discard_fixture_execution in smoke_cases():
        if name not in {"changed", "in_place"}:
            continue
        gaps = tuple(DevelopmentGap(task.content_hash, artifact.artifact_hash, o.id, "hypothesis", "fixture:hypothesis-not-audit")
                     for o in task.obligations)
        view = research_development_view(task, artifact, (), gaps=gaps)
        view["anonymous_id"] = "item-" + digest(["fixture-presentation", artifact.content_hash])[:24]
        views.append(view)
    return sorted(views, key=lambda v: v["anonymous_id"])


def run_fixture_proposals(api, output, *, fetcher=fetch_documents):
    root = _path(output)
    views = fixture_development_views()
    context = [{"path": "FIXTURE_CONTEXT.md", "information_origin": "shared_public_project_context",
                "content": "These are synthetic engineering artifacts, not natural model runs. No code was executed. "
                           "All supplied development gap labels are unconfirmed fixture hypotheses, not independent audit findings."}]
    budget = ResearchBudget(max_output_tokens=MAX_OUTPUT_TOKENS)
    transport = ProposalTransport(api, root / "transport")
    protocol = seal({"version": VERSION, "budget_per_adaptive_arm": budget.to_dict(),
                     "global_max_logical_calls": MAX_LOGICAL_CALLS, "source_kind": "fixture",
                     "service_hash": digest(api.service), "shared_views_hash": digest(views),
                     "shared_context_hash": digest(context), "rubric_hash": fixed_rubric().content_hash,
                     "source_hashes": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                       for name in ("research.py", "stage2_transport.py")},
                     "no_calibration_or_audit": True, "no_candidate_execution": True, "no_deployment_authority": True})
    write_immutable_json(_path(root / "protocol.json"), protocol)
    write_immutable_json(_path(root / "shared_development_views.json"), seal({"views": views, "context": context}))
    research = BoundedResearch(model=transport, fetcher=fetcher, cache_root=_path(root / "research_docs"), budget=budget)
    results = {}
    for arm in ("adaptive_no_research", "adaptive_research"):
        path = _path(root / "proposals" / (arm + ".json"))
        intent = _path(path.with_suffix(".intent.json"))
        request = {"arm": arm, "protocol_hash": protocol["record_hash"]}
        if path.exists():
            terminal = _read(path)
            require(terminal["request"] == request, "Frozen proposal inputs changed")
            results[arm] = terminal["result"]
            continue
        if intent.exists():
            raise ProposalTransportError("interrupted_arm_proposal_requires_manual_review")
        write_immutable_json(intent, seal({"request": request}))
        result = research.propose(arm, fixed_rubric(), views, project_context=context)
        results[arm] = result.to_dict()
        write_immutable_json(path, seal({"request": request, "result": result.to_dict()}))
    report = {"version": VERSION, "source_kind": "fixture", "proposal_statuses": {a: r["status"] for a, r in results.items()},
              "transport_accounting": transport.accounting(), "candidate_executions": 0, "calibration_calls": 0,
              "formal_effect_estimate": False, "deployment_authority": False,
              "limitations": ["Live model proposals on synthetic development views test integration, not efficacy.",
                              "Fixture hypotheses and optional official documentation are not independent calibration evidence."]}
    # Invocation accounting can change on replay; terminal proposals/receipts do
    # not. A separate content-addressed report preserves each invocation honestly.
    write_immutable_json(_path(root / "reports" / (digest(report) + ".json")), seal(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    root = _path(args.output)
    try:
        api_root = _path(root / "api_cache")
        _path(api_root / "calls")
        _path(api_root / "service.json")
        with CachedAPI(Path(args.repo), api_root, workers=1, stream=True, reasoning_effort="low") as api:
            report = run_fixture_proposals(api, root)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        failures = report["transport_accounting"]["terminal_status_counts"]
        return 1 if failures["api_failure"] or failures["transport_failure"] else 0
    except Exception:
        # Setup errors can contain credential paths/headers; fixed category only.
        print(json.dumps({"status": "failed", "error": "configuration_transport_or_frozen_state_error",
                          "new_experiment_effect_claim": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
