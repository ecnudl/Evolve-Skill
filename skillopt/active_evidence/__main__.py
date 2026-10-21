"""Offline smoke of the active-evidence mode: ``python -m skillopt.active_evidence smoke --output <dir>``.

A fixture provider answers every model role with canned replies, a fixture evaluator decides pass/fail, and a
fixture container fails exactly the probes run on the wrong output. The smoke PROVES THE CONTROL FLOW ONLY -- a
round without a canonical validation split (a reserved development challenge pool serves the post-update selection),
diagnosis with graded evidence, the post-update challenge and the frozen decision --
and says nothing about the method's effect. No network, no credentials, no Docker."""
from __future__ import annotations

import argparse
import json
import sys
import threading
from copy import deepcopy
from pathlib import Path

from skillopt.continual_learning.recovery import POLICY_V10  # noqa: F401  (the base policy the manifest embeds)
from skillopt.continual_learning import verifier as vf
from skillopt.validator_pilot.api import digest

from . import protocol as ae
from .stage import run_stage

PROMPT = "Return one. The input list is not modified."
STEP = [str(i) for i in range(8)]
POOL = [f"c{i}" for i in range(12)]
PASSING = {"0", "1", "2", "3", "4"}
PATCH = {"batch_size": 2, "patch": {"reasoning": "fixture", "edits": [{"op": "append", "content": "Use the requested constant result."}]}}


def panel():
    task = {"public": {"prompt": PROMPT, "entry_point": "f"}, "private": {"test": "fixture hidden test"},
            "project_id": "", "partition": "development"}
    tasks = [{**deepcopy(task), "task_id": i, "family_id": i} for i in STEP + POOL]
    return {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "fixture-smoke-v1",
            "provenance": "fixture", "tasks": tasks}


def evaluate(task, skill):
    ok = task["task_id"] in PASSING if task["task_id"] in STEP else "requested constant" in skill
    # a failed row carries the fixture's per-test traceback (host-only for every arm but the failure-message study)
    details = {} if ok else {"test_smoke": ("Traceback (most recent call last):\n  File \"__test__.py\", line 9, in "
                                            "test_smoke\n    self.assertEqual(f(), 1)\nAssertionError: 0 != 1\n")}
    return ({"status": "available", "output": "one" if ok else "zero", "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture",
             "metrics": {"native_result": "pass" if ok else "fail", "details": details}})


def executor(public, output, probes):
    details = {}
    if output == "zero":
        details["test_probe_0"] = ("Traceback (most recent call last):\n  File \"__test__.py\", line 9\n"
                                   f"AssertionError: {vf.probe_mark(probes)} got 0 expected 1")
    return {"status": "fail" if details else "pass", "score": 0.0 if details else 1.0,
            "reason": "official_bigcodebench_untrusted_check",
            "metrics": {"native_result": "fail" if details else "pass", "details": details},
            "cleanup_confirmed": True, "execution_costs": {"container_calls": 1}}


def fetcher(urls, root):
    text = "The builtin returns the documented constant one for an empty boundary call; documented behavior."
    return [{"source_id": digest([u, "smoke"])[:16], "url": u, "status": "available", "text": text,
             "text_sha256": digest(text), "retrieved_text_sha256": digest(text), "retrieved_utc": "fixture",
             "source_version": "Python 3.11", "information_origin": "research_document"} for u in urls]


class SmokeAPI:
    service = {"fixture": "active-evidence-smoke", "delivery_retry_policy": "closed_delivery_error_v3", "max_retries": 2}
    model = "fixture"

    def __init__(self):
        self.calls = {"solver": 0, "reflection": 0, "verifier": 0}
        self.lock = threading.Lock()

    def close(self):
        pass

    def _verifier(self, payload):
        if "batch_summary" in payload:
            cases = payload["cases"]
            fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
            passes = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
            return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate",
                                    "statement": "The documented boundary return value is produced wrongly.",
                                    "mechanism": "Check the documented return value on a legal boundary input.",
                                    "applies_to": fails or [cases[0]["case_id"]],
                                    "discriminating_observation": {"supports": "the boundary call returns another value",
                                                                   "excludes": "the boundary call returns the documented value"},
                                    "needs_fact": "Is the boundary return documented?", "preserve": passes}]}
        if "diagnostic_focus" in payload and "anonymous_implementation" in payload:
            return {"probes": [{"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1,
                                "obligation_id": "requested_behavior", "contract_quote": "Return one.",
                                "rationale": "The contract fixes the return value.", "hypothesis_id": "h1"}]}
        if "fact_questions" in payload:
            return {"urls": ["https://docs.python.org/3.11/library/functions.html"]}
        if "reviews" in payload and "sources" in payload:
            return {"resolutions": [{"index": 0, "keep": True, "revised_expected": None,
                                     "citation": {"source_id": payload["sources"][0]["source_id"],
                                                  "quote": "returns the documented constant one for an empty boundary call"},
                                     "reason": "documented"}]}
        if "probes" in payload:
            return {"reviews": [{"index": 0, "keep": True, "reason": "legal input",
                                 "fact_question": "Is the boundary return documented?"}]}
        raise AssertionError("unknown verifier payload")

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        role = kind.rsplit("-", 1)[-1]
        with self.lock:
            self.calls[role] += 1
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        if role == "verifier":
            response = json.dumps(self._verifier(json.loads(user)))
        elif role == "reflection":
            response = json.dumps(PATCH)
        else:
            response = "```python\ndef f():\n    return 1\n```"
        return {"request": request, "request_hash": digest(request), "response": response, "ok": True,
                "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 20},
                "http_attempt_count": 1, "attempts": [{"usage": {"prompt_tokens": 20, "completion_tokens": 20}}]}


def smoke(output, arms, update_mode="native"):
    value = ae.manifest(panel(), step_families=list(STEP), challenge_families=list(POOL),
                        model={"provider": "fixture", "name": "fixture", "max_tokens": 100, "reasoning_effort": "low",
                               "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                                             "initial_health_policy": "completed_response_v1"}},
                        budget={"max_metric_calls": 400, "max_reflection_calls": 40, "max_api_calls": 600,
                                "max_reported_tokens": 1_000_000, "max_iterations": 1, "minibatch_size": 2,
                                "solver_max_tokens": 100, "reflection_max_tokens": 100, "max_verifier_calls": 200,
                                "verifier_max_tokens": 100},
                        runtime={}, parent_skill="", seed=7, arms=arms,
                        limits={**ae.DEFAULT_LIMITS, "fresh_tasks": 8, "min_paired_known": 8,
                                # the matched-branch study has no replay/local-fix sets (fixture pool: 12 tasks)
                                **({"replay_rows": 0, "local_fix_rows": 0}
                                   if arms["post_update"] in ae.STUDY_ARMS else
                                   {"replay_rows": 4, "local_fix_rows": 2})}, update_mode=update_mode)
    api = SmokeAPI()
    result = run_stage(value, panel(), Path(output) / "learning", fixture_api=api, fixture_evaluate=evaluate,
                       fixture_probe_executor=executor, fixture_fetcher=fetcher)
    return {"status": result["status"], "reason": result["reason"], "decisions": result["decisions"],
            "arms": result["arms"], "candidate_changed": result["candidate_skill"] != "",
            "steps": [{k: s[k] for k in ("diagnosis_status", "rows_with_evidence", "proposal_status", "challenge_status",
                                         "decision")} for s in result["steps"]],
            "model_calls": api.calls, "evidence_kind": result["evidence_kind"],
            "note": "fixture smoke: proves the control flow only, never the method's effect"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke",))
    parser.add_argument("--output", required=True)
    parser.add_argument("--arm-feedback", choices=ae.FEEDBACK_ARMS, default="diagnosis_research")
    parser.add_argument("--arm-post-update", choices=ae.POST_UPDATE_ARMS, default="challenge_replay")
    parser.add_argument("--arm-update", choices=ae.UPDATE_MODES, default="native")
    args = parser.parse_args(argv)
    summary = smoke(args.output, {"feedback": args.arm_feedback, "post_update": args.arm_post_update}, args.arm_update)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["status"] == "completed" else 3


if __name__ == "__main__":
    sys.exit(main())
