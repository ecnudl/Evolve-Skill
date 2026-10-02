"""Single bounded parameter-acceptance probe, never a benchmark score.

A short answer with max_tokens=131072 proves only request acceptance, not that
the endpoint will actually produce more than 65536 tokens on a long task.
No retry, key, raw upstream error, or reasoning text is persisted.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.validator_pilot import api as api_module
from skillopt.validator_pilot.api import PJLAB_HTTP_PROXY_HOST, CachedAPI


def run(repo, output):
    root = safe_path(output)
    with output_lock(root):
        if (root / "result.json").exists():
            return read_json(root / "result.json", sealed=True)
        require(not (root / "intent.json").exists(), "Unclosed probe; inspect before any new request")
        api = CachedAPI(Path(repo), root / "api", provider="bigmodel", model="glm-5.3",
                        workers=1, reasoning_effort="low", stream=True,
                        read_timeout_seconds=300, stream_wall_seconds=3600,
                        initial_health_policy="completed_response_v1",
                        proxy=f"http://{PJLAB_HTTP_PROXY_HOST}:3128")
        payload = {"model": "glm-5.3", "temperature": 0, "max_tokens": 131072,
                   "stream": True, "stream_options": {"include_usage": True},
                   "thinking": {"type": "enabled"}, "reasoning_effort": "low",
                   "messages": [{"role": "system", "content": "Reply with exactly OK and no other text."},
                                {"role": "user", "content": "Reply OK."}]}
        intent = seal({"kind": "bigmodel-output-budget-parameter-acceptance-v1",
                       "payload": payload, "service": api.service,
                       "effective_whole_probe_deadline_seconds": 90, "max_http_attempts": 1,
                       "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "api_sha256": hashlib.sha256(Path(api_module.__file__).read_bytes()).hexdigest(),
                       "is_benchmark": False})
        write_json(root / "intent.json", intent)
        started = time.monotonic()
        diagnostic, status, body, error = {}, None, None, None

        async def once():
            # Intentionally bypass CachedAPI.call's old client-side cap only
            # for this explicit, source-bound endpoint capability probe.
            return await asyncio.wait_for(api._long_stream_request(payload, diagnostic), timeout=90)

        try:
            status, _, body = asyncio.run(once())
        except Exception as exc:
            error = type(exc).__name__  # never exception text, headers, or keys
        finally:
            api.close()
        body = body or {}
        choices = body.get("choices") or [{}]
        choice = choices[0]
        answer = (choice.get("message") or {}).get("content") or ""
        accepted = (status == 200 and body.get("model") == "glm-5.3"
                    and body.get("_stream_complete") is True
                    and choice.get("finish_reason") == "stop" and answer.strip() == "OK")
        result = seal({"intent_hash": intent["record_hash"], "max_tokens": 131072,
                       "status": status or diagnostic.get("status"), "error_category": error,
                       "parameter_accepted_and_short_answer_completed": accepted,
                       "effective_long_output_limit_verified": False,
                       "returned_model": body.get("model"), "finish_reason": choice.get("finish_reason"),
                       "stream_complete": body.get("_stream_complete", False),
                       "response_characters": len(answer), "usage": body.get("usage", {}),
                       "http_attempt_count": 1, "wall_seconds": time.monotonic() - started,
                       "benchmark_tasks_submitted": 0})
        write_json(root / "result.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.repo, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
