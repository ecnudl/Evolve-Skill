"""POSTHOC whitespace-only replay after a repeated Coding study is COMPLETE.

No model calls or candidate execution. This never changes the original study's
scores. Removing blank lines/line-edge whitespace isolates some grammar failures;
it cannot repair spelling, missing evidence, contradictory verdicts or semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VERSION = "posthoc-scale-judge-whitespace-v1"
REQUIRED_SOURCES = (
    "skillopt/validator_scale_rubrics.py",
    "skillopt/validator_pilot/analysis.py",
    "skillopt/validator_pilot/api.py",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _read(path: Path, files: dict[str, str] | None = None) -> Any:
    raw = path.read_bytes()
    if files is not None:
        files[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def normalize_whitespace(text: str) -> str:
    """Only strip each line's edges and remove whitespace-only lines."""
    if not isinstance(text, str):
        raise TypeError("judge response must be text")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _safe_component(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.-]+", value) is None:
        raise ValueError("invalid artifact path component")
    return value


def _hash_text(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("invalid expected hash")
    return value


def _verify_sources(repo: Path, protocol: dict, snapshot: dict, files: dict[str, str]) -> int:
    hashes = protocol.get("source_hashes", {})
    if not isinstance(hashes, dict) or not all(path in hashes for path in REQUIRED_SOURCES):
        raise ValueError("missing frozen parser/analysis/API source hashes")
    if set(hashes) != set(snapshot):
        raise ValueError("frozen source index mismatch")
    for relative, expected in hashes.items():
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("invalid frozen source path")
        path = (repo / relative).resolve()
        if not path.is_relative_to(repo.resolve()):
            raise ValueError("frozen source escapes repository")
        content = snapshot[relative]
        if not isinstance(content, str) or _digest(content) != expected:
            raise ValueError("frozen source snapshot checksum mismatch")
        raw = path.read_bytes()
        files[str(path)] = hashlib.sha256(raw).hexdigest()
        if raw.decode("utf-8") != content:
            raise ValueError("live frozen source changed; do not reinterpret with a different parser")
    return len(hashes)


def _guarded(row: dict, judgment: dict) -> dict:
    """Reuse the original deterministic guard; do not recompute candidate tests."""
    if row["guard_forced"] or not row["target_ok"] or not row["execution_ok"]:
        guarded = row["guarded_judgment"]
    else:
        guarded = judgment
    return {**row, "judgment": guarded, "judge_ok": row["judge_ok"] or row["guard_forced"]}


def _verify_row(root: Path, row: dict, split: str, arm: str, model: str, files: dict[str, str],
                parse_judgment) -> tuple[dict, str | None]:
    if row.get("split") != split or row.get("rubric_arm") != arm:
        raise ValueError("judgment split/validator identity mismatch")
    identifier, skill = _safe_component(row.get("id")), _safe_component(row.get("skill_version"))
    repeat = row.get("judge_repeat")
    if type(repeat) is not int or repeat < 0 or row.get("repeat") != repeat or row.get("target_repeat") != 0:
        raise ValueError("unexpected frozen judge/target repetition identity")
    path = root / "judgments" / _safe_component(arm) / f"{identifier}__{skill}__j{repeat}.json"
    saved = _read(path, files)
    signature = saved.pop("record_sha256", None)
    if signature != _digest(saved) or saved != row:
        raise ValueError("derived judgment record checksum/content mismatch")
    if row.get("judge_attempted") is not row.get("target_ok"):
        raise ValueError("judge attempt attribution mismatch")
    if row["guard_forced"]:
        if (not row["target_ok"] or not row["execution_ok"]
                or row["guarded_judgment"].get("decision") != "fail"
                or row["guarded_judgment"].get("schema_valid") is not True):
            raise ValueError("inconsistent frozen deterministic guard")
    elif row["target_ok"] and row["execution_ok"]:
        if row["guarded_judgment"] != row["judgment"]:
            raise ValueError("unforced available guard changed judgment")
    elif row["guarded_judgment"].get("decision") != "unknown":
        raise ValueError("unavailable execution must not become a guard rejection")
    if not row["judge_attempted"]:
        if row.get("judge_request_hash") is not None or row["judge_ok"]:
            raise ValueError("unattempted judge has a response")
        return deepcopy(row["judgment"]), None
    request_hash = _hash_text(row.get("judge_request_hash"))
    call = _read(root / "api/calls" / f"{request_hash}.json", files)
    request = call.get("request", {})
    if call.get("request_hash") != request_hash or _digest(request) != request_hash:
        raise ValueError("judge API request hash mismatch")
    if (request.get("kind") != "judge_" + arm or request.get("repeat") != repeat
            or request.get("key") != row["request_hash"] or request.get("model") != model):
        raise ValueError("judge API request identity mismatch")
    if call.get("ok") != row["judge_ok"] or row.get("raw_judge_ok") != row["judge_ok"]:
        raise ValueError("judge API status mismatch")
    response = call.get("response")
    if not isinstance(response, str) or row.get("raw_response_sha256") != _digest(response):
        raise ValueError("judge raw response checksum mismatch")
    if not call["ok"]:
        return deepcopy(row["judgment"]), None
    strict = parse_judgment(response)
    if strict != row["judgment"]:
        raise ValueError("frozen strict parser does not reproduce original judgment")
    return parse_judgment(normalize_whitespace(response)), response


def _changes(left: list[dict], right: list[dict]) -> dict:
    details = []
    exposed = {origin: {"newly_exposed_FP": 0, "newly_exposed_FN": 0,
                        "newly_exposed_TP": 0, "newly_exposed_TN": 0} for origin in ("natural", "controlled")}
    for old, new in zip(left, right):
        before, after = old["judgment"], new["judgment"]
        if before == after:
            continue
        kind = None
        if old["target_ok"] and old["execution_ok"] and old["hard"] is not None:
            if before["decision"] == "unknown" and after["decision"] in {"pass", "fail"}:
                kind = ("TP" if old["hard"] else "FP") if after["decision"] == "pass" else ("FN" if old["hard"] else "TN")
                exposed[old["origin"]]["newly_exposed_" + kind] += 1
        details.append({key: old.get(key) for key in ("id", "family", "origin", "skill_version", "repeat", "hard",
                                                      "judge_request_hash", "request_hash")}
                       | {"strict_decision": before["decision"], "normalized_decision": after["decision"],
                          "strict_schema_valid": before["schema_valid"], "normalized_schema_valid": after["schema_valid"],
                          "newly_exposed_outcome": kind, "normalized_evidence": after.get("evidence", [])})
    return {"by_origin": exposed, "changed_rows": details}


def audit(root: Path, repo: Path = REPO) -> dict:
    """Read results barrier FIRST; no partial-run/held-out diagnostic is allowed."""
    root, repo = Path(root).resolve(), Path(repo).resolve()
    files: dict[str, str] = {}
    results_path = root / "results.json"
    if not results_path.exists():
        raise RuntimeError("complete-results barrier not met")
    results = _read(results_path, files)
    if results.get("status") != "complete":
        raise RuntimeError("complete-results barrier not met")
    protocol = _read(root / "protocol.json", files)
    if results.get("protocol_hash") != _digest(protocol):
        raise ValueError("completed result protocol hash mismatch")
    snapshot = _read(root / "source_snapshot.json", files)
    source_count = _verify_sources(repo, protocol, snapshot, files)
    # Only import after exact frozen-source verification. No evaluator or API
    # client is instantiated, and bytecode writes are disabled above.
    from skillopt.validator_pilot.analysis import compare_judges, summarize_rows
    from skillopt.validator_scale_rubrics import parse_judgment

    groups = {}
    raw_calls = whitespace_changed = newly_valid = 0
    for split in ("dev", "holdout"):
        by_arm = _read(root / f"{split}_judgments.json", files)
        groups[split] = {}
        for arm, rows in by_arm.items():
            normalized = []
            for row in rows:
                judgment, raw = _verify_row(root, row, split, arm, protocol["model"], files, parse_judgment)
                normalized.append({**row, "judgment": judgment})
                if raw is not None:
                    raw_calls += 1
                    whitespace_changed += normalize_whitespace(raw) != raw
                    newly_valid += not row["judgment"]["schema_valid"] and judgment["schema_valid"]
            strict_guarded = [_guarded(row, row["judgment"]) for row in rows]
            normalized_guarded = [_guarded(original, revised["judgment"]) for original, revised in zip(rows, normalized)]
            strict_summary = summarize_rows(rows)
            main_result = results["development_raw"] if split == "dev" else results["holdout_raw"][arm]
            if any(main_result.get(key) != value for key, value in strict_summary.items()):
                raise ValueError("raw aggregate differs from completed main result")
            groups[split][arm] = {
                "raw": {"strict": strict_summary, "whitespace_normalized": summarize_rows(normalized),
                        "paired": compare_judges(rows, normalized), "changes": _changes(rows, normalized)},
                "guarded": {"strict": summarize_rows(strict_guarded), "whitespace_normalized": summarize_rows(normalized_guarded),
                            "paired": compare_judges(strict_guarded, normalized_guarded),
                            "changes": _changes(strict_guarded, normalized_guarded)},
                "attempt_accounting": {"actual_judge_calls": sum(row["judge_attempted"] for row in rows),
                                       "actual_judge_api_errors": sum(row["judge_attempted"] and not row["judge_ok"] for row in rows),
                                       "not_attempted_target_unavailable": sum(not row["judge_attempted"] for row in rows)},
            }
    return {"version": VERSION, "status": "complete", "classification": "POSTHOC whitespace-only diagnostic",
            "input_run": str(root), "original_results_edited": False, "model_calls": 0, "candidate_executions": 0,
            "normalization": "strip line-edge whitespace; remove whitespace-only lines; preserve every nonempty line's remaining text/order",
            "successful_cached_judge_responses": raw_calls, "responses_with_whitespace_change": whitespace_changed,
            "newly_schema_valid_responses": newly_valid, "by_split": groups,
            "provenance": {"frozen_source_files_verified": source_count, "file_sha256": files,
                           "diagnostic_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           "response_checksums_and_strict_reparse_verified": True,
                           "hard_labels": "reused frozen labels; candidate execution not repeated",
                           "not_service_signed_attestation": True},
            "limitations": ["Designed after observing DEVELOPMENT formatting failures, and run only after COMPLETE results.",
                            "Same frozen responses, not new independent evidence; original strict scores are unchanged.",
                            "Typos, missing nonempty lines, contradictory decisions and evidence are never repaired.",
                            "Newly readable judgments can expose false rejection or false approval, not only correct detections.",
                            "Unknown remains abstention; repeats and controlled variants are not independent tasks.",
                            "Guard-forced outcomes are reused, not attributed to improved model judgment.",
                            "Whitespace normalization does not prove semantic judgment or algorithmic robustness."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.run.resolve()
    if args.output is not None and args.output.resolve().is_relative_to(root):
        raise ValueError("diagnostic output must be outside the original run")
    result = audit(root)
    if args.output is None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        from skillopt.validator_pilot.api import write_immutable_json
        write_immutable_json(args.output.resolve(), result)
        print(json.dumps({"status": result["status"], "model_calls": 0, "candidate_executions": 0,
                          "newly_schema_valid_responses": result["newly_schema_valid_responses"],
                          "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
