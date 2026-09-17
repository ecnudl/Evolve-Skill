"""Selected TRAIN JSON-failure regression probe, separate from frozen pilot results.

Default mode only freezes inputs; credentials/network are used solely with
--execute. No semantic scoring, hidden evaluation access, or old-run writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skillopt.validator_pilot.api import (  # noqa: E402
    MODEL,
    PROVIDER_HOST,
    _configuration,
    _stream_body,
    _StreamResponseError,
    digest,
    write_immutable_json,
)
from skillopt.validator_pilot.rubrics import parse_judgment  # noqa: E402

LIMITS = [
    "Selected previously invalid TRAIN judgments only; this is a regression diagnostic, not a random reliability estimate.",
    "Fresh default-format and JSON-mode calls are paired with alternating order; original failures are selection triggers, not controls.",
    "Only up to four selected prompt pairs and one draw per arm; no significance or general reliability claim.",
    "JSON-object output does not guarantee Rubric schema consistency or semantic correctness.",
    "No hidden outcome is scored, no validator promoted, and no frozen pilot result is replaced.",
    "Model-official JSON mode support does not prove PJLAB parameter enforcement.",
]
REFERENCES = ["https://docs.z.ai/guides/llm/glm-5.3",
              "https://docs.z.ai/api-reference/llm/chat-completion",
              "https://docs.z.ai/guides/capabilities/struct-output"]


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _leading_split(path: Path) -> str:
    """Read only the leading split metadata; never parse a non-TRAIN body."""
    with path.open(encoding="utf-8") as handle:
        for _ in range(12):
            line = handle.readline(4096)
            if not line:
                break
            matched = re.fullmatch(r'  "split": "([a-z_]+)",?\s*', line)
            if matched:
                return matched.group(1)
            if '"response"' in line or '"evaluation"' in line or len(line) >= 4096:
                break
    raise ValueError("Cannot establish split from bounded leading judgment metadata")


def select_cases(source: Path, limit: int = 4) -> list[dict[str, Any]]:
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError("Select one to four TRAIN regression cases")
    source = Path(source).resolve()
    eligible = []
    for path in sorted((source / "judgments").glob("*.json")):
        if _leading_split(path) != "train":
            continue
        row = _read(path)
        if row.get("split") != "train":
            raise ValueError("TRAIN metadata mismatch")
        if row.get("judgment", {}).get("schema_valid") is not False:
            continue
        call_hash = row.get("judge_request_hash", "")
        if not isinstance(call_hash, str) or re.fullmatch(r"[0-9a-f]{64}", call_hash) is None:
            raise ValueError("Invalid TRAIN judge cache identity")
        cache = source / "api/calls" / (call_hash + ".json")
        record = _read(cache)
        request = record["request"]
        if (record.get("request_hash") != call_hash or digest(request) != call_hash
                or request.get("kind") != "judge_static_v0"
                or request.get("key") != row.get("request_hash")
                or request.get("repeat") != row.get("repeat")
                or record.get("ok") is not True or record.get("finish_reason") != "stop"):
            raise ValueError("Source TRAIN call provenance mismatch")
        service = request.get("service", {})
        if (request.get("model") != MODEL or request.get("max_tokens") != 8000
                or service.get("host") != PROVIDER_HOST or service.get("temperature") != 0
                or service.get("stream") is not True or service.get("reasoning_effort") != "low"):
            raise ValueError("Source TRAIN call does not match fixed GLM low-stream settings")
        user = json.loads(request["user"])
        if user.get("task", {}).get("id") != row["id"] or not isinstance(user.get("rubric"), dict):
            raise ValueError("Source judge prompt identity mismatch")
        parsed = parse_judgment(record["response"], user["rubric"])
        if parsed.schema_valid or "invalid JSON response" not in parsed.errors:
            continue
        eligible.append({"id": row["id"], "repeat": row["repeat"], "skill_version": row["skill_version"],
                         "split": "train", "source_judge_hash": call_hash,
                         "source_judgment_path": str(path), "source_judgment_sha256": _sha(path),
                         "source_cache_path": str(cache), "source_cache_sha256": _sha(cache),
                         "old_response_sha256": hashlib.sha256(record["response"].encode()).hexdigest(),
                         "old_schema_valid": parsed.schema_valid, "old_schema_errors": list(parsed.errors),
                         "system": request["system"], "user": request["user"], "rubric": user["rubric"]})
    eligible.sort(key=lambda item: (item["id"], item["repeat"], item["skill_version"], item["source_judge_hash"]))
    return eligible[:limit]


def _request(case: dict[str, Any], arm: str) -> dict[str, Any]:
    if arm not in {"default_format", "json_object"}:
        raise ValueError("Unknown JSON regression arm")
    request = {"protocol": "selected-train-json-mode-regression-v1", "source_judge_hash": case["source_judge_hash"],
            "arm": arm,
            "service": {"provider": "PJLAB", "host": PROVIDER_HOST, "path": "/v1/chat/completions",
                        "trust_env": False, "follow_redirects": False, "max_retries": 0,
                        "timeout_seconds": {"connect": 20, "read": 120, "write": 30, "pool": 20}},
            "body": {"model": MODEL, "messages": [{"role": "system", "content": case["system"]},
                                                        {"role": "user", "content": case["user"]}],
                     "temperature": 0, "max_tokens": 8000, "stream": True,
                     "stream_options": {"include_usage": True}, "reasoning_effort": "low"}}
    if arm == "json_object":
        request["body"]["response_format"] = {"type": "json_object"}
    return request


def _jobs(cases: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
    result = []
    for index, case in enumerate(cases):
        arms = ("default_format", "json_object") if index % 2 == 0 else ("json_object", "default_format")
        result.extend((case, arm) for arm in arms)
    return result


def prepare(repo: Path, source: Path, output: Path, limit: int = 4) -> dict[str, Any]:
    repo, source, output = Path(repo).resolve(), Path(source).resolve(), Path(output).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Regression output must be a separate directory outside the original run")
    code_paths = [repo / "scripts/validator_json_mode_probe.py", repo / "skillopt/validator_pilot/api.py",
                  repo / "skillopt/validator_pilot/rubrics.py"]
    code_hashes = {str(path.relative_to(repo)): _sha(path) for path in code_paths}
    protocol_path = output / "protocol.json"
    if protocol_path.exists():
        protocol = _read(protocol_path)
        if (protocol["source_root"] != str(source) or protocol["limit"] != limit
                or protocol["code_hashes"] != code_hashes):
            raise ValueError("Frozen regression configuration changed")
        if _sha(source / "protocol.json") != protocol["source_protocol_sha256"]:
            raise ValueError("Original pilot protocol changed")
        for case in protocol["cases"]:
            for kind in ("judgment", "cache"):
                if _sha(Path(case[f"source_{kind}_path"])) != case[f"source_{kind}_sha256"]:
                    raise ValueError("Original selected TRAIN evidence changed")
        return protocol
    cases = select_cases(source, limit)
    protocol = {"version": "selected-train-json-mode-regression-v1", "source_root": str(source),
                "source_protocol_sha256": _sha(source / "protocol.json"), "code_hashes": code_hashes,
                "limit": limit, "cases": cases,
                "request_hashes": [digest(_request(case, arm)) for case, arm in _jobs(cases)],
                "selection": "TRAIN only, cache finish=stop and parser invalid JSON; sort id/repeat/version/hash",
                "max_logical_calls": 2 * len(cases), "workers": 1, "max_retries": 0,
                "arms": ["default_format", "json_object"],
                "order": [{"source_judge_hash": case["source_judge_hash"], "arm": arm} for case, arm in _jobs(cases)],
                "source_scan": "Leading split metadata only for non-TRAIN files; never parse their bodies",
                "references": REFERENCES, "limits": LIMITS}
    write_immutable_json(protocol_path, protocol)
    return protocol


def _call(client: httpx.Client, endpoint: str, case: dict[str, Any], arm: str, output: Path) -> dict[str, Any]:
    request = _request(case, arm)
    identifier = digest(request)
    path = output / "calls" / (identifier + ".json")
    if path.exists():
        record = _read(path)
        if record.get("request_hash") != identifier or record.get("request") != request:
            raise ValueError("Regression request cache mismatch")
        return record
    started = time.monotonic()
    record: dict[str, Any] = {"request_hash": identifier, "request": request, "ok": False,
                              "response": "", "usage": {}, "status": None, "finish_reason": None,
                              "error_type": None, "http_attempt_count": 1}
    try:
        with client.stream("POST", endpoint, json=request["body"]) as response:
            record["status"] = response.status_code
            if response.status_code != 200:
                record["error_type"] = "http_status"
            else:
                body = _stream_body(response)
                choice = body["choices"][0]
                record.update(response=choice["message"]["content"], usage=body["usage"],
                              finish_reason=choice["finish_reason"], returned_model=body["model"],
                              stream_complete=body["_stream_complete"],
                              stream_event_count=body["_stream_event_count"])
                if not body["_stream_complete"]:
                    record["error_type"] = "incomplete_stream"
                elif record["finish_reason"] == "length":
                    record["error_type"] = "truncated_content"
                elif record["finish_reason"] != "stop":
                    record["error_type"] = "unexpected_finish_reason"
                elif not record["response"].strip():
                    record["error_type"] = "empty_content"
                else:
                    record["ok"] = True
    except httpx.TimeoutException:
        record["error_type"] = "timeout"
    except httpx.TransportError:
        record["error_type"] = "transport_error"
    except _StreamResponseError as error:
        record["error_type"] = error.category
    except Exception:
        record["error_type"] = "response_or_client_error"
    record["wall_seconds"] = time.monotonic() - started
    parsed = parse_judgment(record["response"] if record["ok"] else "", case["rubric"])
    record.update(schema_valid=bool(record["ok"] and parsed.schema_valid), schema_errors=list(parsed.errors))
    write_immutable_json(path, record)
    return record


def run(repo: Path, source: Path, output: Path, *, execute: bool = False, limit: int = 4) -> dict[str, Any]:
    protocol = prepare(repo, source, output, limit)
    output = Path(output).resolve()
    if not execute:
        return {"status": "prepared", "selected_train_failures": len(protocol["cases"]),
                "network_requests": 0, "credentials_loaded": False, "limits": LIMITS}
    summary_path = output / "summary.json"
    if summary_path.exists():
        return _read(summary_path)
    if not protocol["cases"]:
        summary = {"status": "no_eligible_train_cases", "logical_calls": 0, "limits": LIMITS}
        write_immutable_json(summary_path, summary)
        return summary
    # Deliberately the first point where credentials are read.
    endpoint, api_key = _configuration(Path(repo), MODEL)
    records = []
    with httpx.Client(trust_env=False, follow_redirects=False,
                      timeout=httpx.Timeout(120, connect=20, write=30, pool=20),
                      headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}) as client:
        for case, arm in _jobs(protocol["cases"]):
            record = _call(client, endpoint, case, arm, output)
            records.append(record)
            print(json.dumps({"stage": "selected_train_json_regression", "id": case["id"],
                              "repeat": case["repeat"], "arm": arm, "transport_ok": record["ok"],
                              "schema_valid": record["schema_valid"], "wall_seconds": record["wall_seconds"],
                              "status": record["status"], "error_type": record["error_type"]}), flush=True)
            if not record["ok"]:
                break
    by_arm = {arm: [r for r in records if r["request"]["arm"] == arm] for arm in ("default_format", "json_object")}
    by_case: dict[str, dict[str, Any]] = {}
    for record in records:
        by_case.setdefault(record["request"]["source_judge_hash"], {})[record["request"]["arm"]] = record
    completed_pairs = [pair for pair in by_case.values()
                       if set(pair) == {"default_format", "json_object"} and all(r["ok"] for r in pair.values())]
    json_gains = sum(not pair["default_format"]["schema_valid"] and pair["json_object"]["schema_valid"]
                     for pair in completed_pairs)
    json_losses = sum(pair["default_format"]["schema_valid"] and not pair["json_object"]["schema_valid"]
                      for pair in completed_pairs)
    summary = {"status": "complete" if len(records) == 2 * len(protocol["cases"]) and all(r["ok"] for r in records)
               else "stopped_transport_failure", "selected_train_failures": len(protocol["cases"]),
               "logical_calls": len(records), "http_attempts": sum(r["http_attempt_count"] for r in records),
               "old_schema_valid": 0, "new_schema_valid": sum(r["schema_valid"] for r in records),
               "transport_successes": sum(r["ok"] for r in records),
               "by_arm": {arm: {"calls": len(rows), "transport_successes": sum(r["ok"] for r in rows),
                                "schema_valid": sum(r["schema_valid"] for r in rows),
                                "api_errors": sum(not r["ok"] for r in rows)} for arm, rows in by_arm.items()},
               "fresh_pairs": {"complete_transport_successful_pairs": len(completed_pairs),
                               "json_only_schema_valid": json_gains, "default_only_schema_valid": json_losses,
                               "both_schema_valid": sum(all(r["schema_valid"] for r in pair.values()) for pair in completed_pairs),
                               "neither_schema_valid": sum(not any(r["schema_valid"] for r in pair.values()) for pair in completed_pairs)},
               "total_tokens": sum(r["usage"].get("total_tokens", 0) or 0 for r in records),
               "prompt_tokens": sum(r["usage"].get("prompt_tokens", 0) or 0 for r in records),
               "completion_tokens": sum(r["usage"].get("completion_tokens", 0) or 0 for r in records),
               "cases": [{"id": case["id"], "repeat": case["repeat"], "skill_version": case["skill_version"], "arm": arm,
                          "source_judge_hash": case["source_judge_hash"], "new_request_hash": record["request_hash"],
                          "old_schema_valid": case["old_schema_valid"], "new_schema_valid": record["schema_valid"],
                          "transport_ok": record["ok"], "wall_seconds": record["wall_seconds"]}
                         for (case, arm), record in zip(_jobs(protocol["cases"]), records)],
               "protocol_hash": digest(protocol), "limits": LIMITS, "references": REFERENCES}
    write_immutable_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--limit", type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument("--execute", action="store_true", help="Explicitly enable at most eight serial real API calls")
    args = parser.parse_args()
    try:
        result = run(args.repo, args.source, args.output, execute=args.execute, limit=args.limit)
    except Exception:
        print(json.dumps({"status": "stopped", "error_type": "configuration_or_provenance_error"}), flush=True)
        return 2
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] in {"prepared", "complete", "no_eligible_train_cases"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
