"""Bounded PJLAB connectivity/concurrency pilot; all real calls require explicit CLI execution."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skillopt.validator_pilot.api import CachedAPI, digest, write_immutable_json  # noqa: E402


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * q) - 1)]


def _job(index: int) -> tuple[str, str]:
    system = "You are a careful Python code reviewer. Return only a short JSON object."
    user = (
        "Review whether this change preserves the empty-input behavior while adding a factor.\n"
        "Original: def total(values): return sum(values)\n"
        "Changed: def total(values, factor=1): return sum(values) * factor\n"
        "Return {\"valid\": true or false, \"reason\": one short sentence, "
        f"\"probe\": {index}}}. Do not write a long explanation."
    )
    return system, user


def _semantic_ok(record: dict, index: int) -> bool:
    if not record.get("ok"):
        return False
    try:
        raw = record["response"].strip()
        fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        result = json.loads(fenced.group(1) if fenced else raw)
        return (isinstance(result, dict) and result.get("valid") is True
                and result.get("probe") == index and isinstance(result.get("reason"), str))
    except (ValueError, TypeError):
        return False


def run(repo: Path, output: Path, *, max_level: int = 12) -> dict:
    levels = [level for level in (1, 4, 8, 12) if level <= max_level]
    if max_level not in (1, 4, 8, 12):
        raise ValueError("max_level must be one of 1, 4, 8, 12")
    output = Path(output)
    protocol = {"version": "pjlab-preflight-v2-fenced-json", "model": "glm-5.3", "levels": levels,
                "waves_per_level": 2, "max_tokens": 2048,
                "stop_on": ["any terminal error", "any retry/attempt error", "invalid review JSON",
                            "p95 > max(45 seconds, 2.5 times concurrency-1 p95)"],
                "recommendation": "one tested stable level below highest stable level, minimum 1",
                "maximum_logical_calls": 1 + 2 * sum(levels),
                "notes": ["Brief JSON review load; not a guarantee for longer research/evolution calls.",
                          "Two waves and small samples cannot establish a production SLA.",
                          "Cached records are immutable; resume is not a fresh load test."]}
    write_immutable_json(output / "protocol.json", protocol)
    summary_path = output / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    summaries, stable_levels, all_records = [], [], []
    stopped = None
    baseline_p95 = None
    with CachedAPI(repo, output, workers=max_level) as api:
        system, user = _job(0)
        health = api.call(system, user, "preflight_health", "health", max_tokens=2048)
        all_records.append(health)
        health_ok = _semantic_ok(health, 0) and all(row["ok"] for row in health["attempts"])
        print(json.dumps({"stage": "connectivity", "ok": health_ok,
                          "wall_seconds": health["wall_seconds"], "status": health["status"],
                          "error_type": health["error_type"]}), flush=True)
        if not health_ok:
            stopped = "connectivity_or_response_validation_failed"
        for level in levels if health_ok else []:
            level_records, wave_summaries, semantic_flags = [], [], []
            for wave in range(2):
                indices = [level * 1000 + wave * 100 + index for index in range(level)]
                def call(index):
                    system, user = _job(index)
                    return api.call(system, user, "preflight_load", f"c{level}-w{wave}-i{index}", max_tokens=2048)
                started = time.monotonic()
                with ThreadPoolExecutor(max_workers=level) as pool:
                    records = list(pool.map(call, indices))
                elapsed = time.monotonic() - started
                flags = [_semantic_ok(record, index) for record, index in zip(records, indices)]
                semantic_flags.extend(flags)
                level_records.extend(records)
                all_records.extend(records)
                wave_summaries.append({"wave": wave, "wall_seconds": elapsed,
                                       "logical_calls": len(records), "response_valid": sum(flags),
                                       "http_attempts": sum(r["http_attempt_count"] for r in records)})
                if not all(flags) or any(not row["ok"] for r in records for row in r["attempts"]):
                    stopped = "request_or_response_error"
                    break
            latencies = [record["wall_seconds"] for record in level_records]
            p95 = _quantile(latencies, .95)
            if level == 1:
                baseline_p95 = p95
            if baseline_p95 is not None and p95 > max(45, 2.5 * baseline_p95):
                stopped = stopped or "tail_latency_growth"
            summary = {"concurrency": level, "logical_calls": len(level_records),
                       "successes": sum(record["ok"] for record in level_records),
                       "valid_responses": sum(semantic_flags), "p50_seconds": _quantile(latencies, .5),
                       "p95_seconds": p95, "max_seconds": max(latencies),
                       "stable": stopped is None, "waves": wave_summaries,
                       "request_hashes": [record["request_hash"] for record in level_records]}
            summaries.append(summary)
            write_immutable_json(output / f"level_{level}.json", summary)
            print(json.dumps({key: value for key, value in summary.items()
                              if key not in ("waves", "request_hashes")}), flush=True)
            if stopped:
                break
            stable_levels.append(level)
            # A short recovery pause between levels; no extreme load search.
            time.sleep(2)
    recommendation = stable_levels[-2] if len(stable_levels) > 1 else stable_levels[0] if stable_levels else None
    result = {"protocol_hash": digest(protocol), "status": "complete" if health_ok else "failed",
              "stable_levels": stable_levels, "recommended_workers": recommendation,
              "stopped_reason": stopped, "levels": summaries,
              "logical_calls": len(all_records),
              "http_attempts": sum(record["http_attempt_count"] for record in all_records),
              "terminal_errors": sum(not record["ok"] for record in all_records),
              "returned_total_tokens": sum(record.get("usage", {}).get("total_tokens", 0) or 0
                                           for record in all_records),
              "health_request_hash": health["request_hash"],
              "limits": protocol["notes"]}
    write_immutable_json(summary_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--max-level", type=int, choices=(1, 4, 8, 12), default=12)
    args = parser.parse_args()
    try:
        result = run(args.repo, args.output, max_level=args.max_level)
    except Exception:
        print(json.dumps({"status": "failed", "error_type": "configuration_or_frozen_artifact_error"}), flush=True)
        return 2
    print(json.dumps({key: result[key] for key in ("status", "stable_levels", "recommended_workers",
                                                  "stopped_reason", "logical_calls", "http_attempts")}), flush=True)
    return 0 if result["recommended_workers"] is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
