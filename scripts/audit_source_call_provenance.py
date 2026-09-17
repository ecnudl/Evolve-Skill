"""Read-only, post-hoc integrity audit of C/E SearchQA result-to-call provenance.

No API client, dataset materialization write, repair, retry, or secret/payload
printing. Local hashes are integrity checks, not signatures of server execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
E_ARMS = ("without_evidence_section", "without_answer_form_sections")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _manifest_tasks(manifest, split):
    from skillopt.scope_evolution_v2.source_data import materialize_source_split
    # This helper reads the frozen local Arrow cache; it never writes a dataset.
    return materialize_source_split(manifest, split)


def _builders():
    from skillopt.envs.searchqa.evaluator import evaluate
    from skillopt.envs.searchqa.rollout import _build_system, _build_user
    return _build_system, _build_user, evaluate


class _Audit:
    def __init__(self, root, split):
        self.root, self.split = root, split
        self.errors = []
        self.missing = 0
        self.counts = Counter()

    def issue(self, code, path, *, missing=False):
        self.errors.append({"code": code, "path": str(path)})
        self.missing += int(missing)

    def read(self, path):
        if not path.is_file():
            self.issue("MISSING_REQUIRED_FILE", path, missing=True)
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            self.issue("UNREADABLE_OR_INVALID_JSON", path)
            return None

    def check(self, condition, code, path):
        if not condition:
            self.issue(code, path)
        return bool(condition)

    def hash_file(self, path, expected):
        if not path.is_file():
            self.issue("MISSING_REQUIRED_FILE", path, missing=True)
            return False
        try:
            return self.check(isinstance(expected, str) and HEX64.fullmatch(expected)
                              and _file_hash(path) == expected, "FROZEN_FILE_HASH_MISMATCH", path)
        except OSError:
            self.issue("UNREADABLE_REQUIRED_FILE", path)
            return False

    def relative(self, root, name):
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            raise ValueError("invalid relative artifact path")
        path = (root / name).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("artifact escapes its declared root")
        return path

    def result(self, kind=None):
        return {"status": "incomplete" if self.missing else "failed" if self.errors else "complete",
                "run_dir": str(self.root), "split": self.split, "kind": kind,
                "counts": dict(self.counts), "missing_required_files": self.missing,
                "error_counts": dict(Counter(e["code"] for e in self.errors)), "errors": self.errors,
                "read_only": True, "server_authenticity_verified": False,
                "scope": "post-hoc local result/cache/input consistency; not server signatures or complete cryptographic dependency attestation"}


def _validate_source_contract(audit, source, repo):
    protocol_path = source / "source_protocol.json"
    protocol = audit.read(protocol_path)
    manifest = audit.read(source / "source_manifest.json")
    frozen = audit.read(source / "frozen_source_protocol.json")
    if any(value is None for value in (protocol, manifest, frozen)):
        return None
    audit.check(_digest(manifest) == protocol["manifest_hash"] == frozen["manifest_hash"],
                "SOURCE_MANIFEST_DIGEST_MISMATCH", source / "source_manifest.json")
    audit.check(_digest(protocol) == frozen["protocol_hash"], "SOURCE_PROTOCOL_DIGEST_MISMATCH", protocol_path)
    audit.check(protocol["arms"] == frozen["arms"], "SOURCE_FROZEN_ARMS_MISMATCH", protocol_path)
    audit.check(protocol["code_hashes"] == frozen["code_hashes"], "SOURCE_FROZEN_CODE_LIST_MISMATCH", protocol_path)
    audit.check(frozen["execution_mode"] == "real_target_api", "NONREAL_EXECUTION_MODE", source / "frozen_source_protocol.json")
    for relative, expected in protocol["code_hashes"].items():
        audit.hash_file(audit.relative(repo, relative), expected)
    for relative, expected in frozen["calibration_artifact_hashes"].items():
        audit.hash_file(audit.relative(source, relative), expected)
    return protocol, manifest, frozen


def _row_audit(audit, row, task, arm, split, protocol, skill, service, row_path, build_system, build_user, evaluate):
    before = len(audit.errors)
    audit.counts["rows_checked"] += 1
    expected_fields = {"id": task["id"], "arm": arm, "split": split, "env": "searchqa",
                       "question": task["question"], "gold_answers": task["answers"],
                       "question_sha256": hashlib.sha256(re.sub(r"\s+", " ", task["question"]).strip().casefold().encode()).hexdigest(),
                       "skill_sha256": hashlib.sha256(skill.encode()).hexdigest()}
    for field, expected in expected_fields.items():
        audit.check(row.get(field) == expected, "ROW_" + field.upper() + "_MISMATCH", row_path)
    identifier = row.get("request_hash")
    if not isinstance(identifier, str) or not HEX64.fullmatch(identifier):
        audit.issue("INVALID_ROW_REQUEST_HASH", row_path)
        return
    cache_path = audit.root / "calls" / (identifier + ".json")
    cache = audit.read(cache_path)
    if cache is None:
        return
    audit.counts["call_caches_checked"] += 1
    request = cache.get("request")
    if not isinstance(request, dict):
        audit.issue("INVALID_CACHED_REQUEST", cache_path)
        return
    expected_request = {"protocol": protocol["protocol_version"], "model": protocol["model"],
                        "system": build_system(skill), "user": build_user(task["question"], task["context"]),
                        "key": task["id"], "arm": arm, "split": split, "service": service,
                        "max_completion_tokens": protocol["requested_max_completion_tokens"]}
    audit.check(set(request) == set(expected_request), "REQUEST_FIELDS_MISMATCH", cache_path)
    for field, expected in expected_request.items():
        audit.check(request.get(field) == expected, "REQUEST_" + field.upper() + "_MISMATCH", cache_path)
    actual_digest = _digest(request)
    audit.check(cache.get("request_hash") == identifier == actual_digest,
                "CACHE_REQUEST_HASH_MISMATCH", cache_path)
    audit.check(identifier == _digest(expected_request), "RECONSTRUCTED_REQUEST_HASH_MISMATCH", cache_path)
    ok = cache.get("ok")
    valid_status = isinstance(ok, bool) and isinstance(row.get("agent_ok"), bool)
    audit.check(valid_status and row["agent_ok"] == ok, "API_STATUS_MISMATCH", cache_path)
    audit.check(isinstance(cache.get("response"), str) and row.get("response") == cache.get("response"),
                "RESPONSE_MISMATCH", cache_path)
    audit.check(isinstance(cache.get("usage"), dict) and row.get("usage") == cache.get("usage"),
                "USAGE_MISMATCH", cache_path)
    if ok is False:
        audit.counts["api_error_rows"] += 1
        audit.check(all(row.get(key) is None for key in ("hard", "em", "f1", "predicted_answer")),
                    "API_ERROR_HAS_SCORES", row_path)
        audit.check(row.get("response") == cache.get("response") == "", "API_ERROR_HAS_RESPONSE", cache_path)
        audit.check(isinstance(cache.get("error"), str) and row.get("api_error") == cache.get("error"),
                    "API_ERROR_REASON_MISMATCH", cache_path)
    elif ok is True and isinstance(row.get("response"), str):
        audit.counts["api_success_rows"] += 1
        metrics = evaluate(row["response"], task["answers"])
        for key in ("em", "f1", "predicted_answer"):
            audit.check(row.get(key) == metrics[key], "SCORE_" + key.upper() + "_MISMATCH", row_path)
        audit.check(row.get("hard") == metrics["em"], "SCORE_HARD_MISMATCH", row_path)
        audit.check(all(isinstance(row.get(key), (int, float)) and not isinstance(row[key], bool)
                        and math.isfinite(row[key]) and 0 <= row[key] <= 1 for key in ("hard", "em", "f1")),
                    "INVALID_NUMERIC_SCORE", row_path)
    if len(audit.errors) == before:
        audit.counts["rows_passed"] += 1


def audit_run(run_dir, split, *, repo=REPO):
    """Audit explicit completed local artifacts only; never fill missing results."""
    root, repo = Path(run_dir).resolve(), Path(repo).resolve()
    audit = _Audit(root, split)
    if split not in ("calibration", "holdout"):
        audit.issue("UNSUPPORTED_SPLIT", root)
        return audit.result()
    kind = None
    try:
        if (root / "attribution_protocol.json").is_file():
            kind = "attribution"
            if split != "holdout":
                audit.issue("ATTRIBUTION_HAS_NO_CALIBRATION", root)
                return audit.result(kind)
            protocol_path = root / "attribution_protocol.json"
            protocol = audit.read(protocol_path)
            seal = audit.read(root / "attribution_seal.json")
            if protocol is None or seal is None:
                return audit.result(kind)
            audit.hash_file(protocol_path, seal["protocol_sha256"])
            audit.check(protocol["execution_mode"] == "real_target_api", "NONREAL_EXECUTION_MODE", protocol_path)
            if not audit.check(protocol["new_arms"] == list(E_ARMS)
                               and set(protocol["arms"]) == {"base", "full", *E_ARMS},
                               "ATTRIBUTION_NEW_ARMS_MISMATCH", protocol_path):
                return audit.result(kind)
            arms = E_ARMS
            source = Path(protocol["settings"]["source_dir"]).resolve()
            for name, expected in protocol["source_artifacts"].items():
                audit.hash_file(audit.relative(source, name), expected)
            for name, expected in protocol["code_hashes"].items():
                audit.hash_file(audit.relative(repo, name), expected)
            borrowed = audit.read(root / "borrowed_source_holdout_artifacts.json")
            if borrowed is None:
                return audit.result(kind)
            for name, expected in borrowed.items():
                audit.hash_file(audit.relative(source, name), expected)
        elif (root / "source_protocol.json").is_file():
            kind, source = "source", root
            protocol = audit.read(root / "source_protocol.json")
            if protocol is None:
                return audit.result(kind)
            arms = tuple(protocol["arms"])
            if not audit.check(arms in (("base", "full"), ("base", "full", "extractive")),
                               "SOURCE_ARMS_MISMATCH", root / "source_protocol.json"):
                return audit.result(kind)
        else:
            audit.issue("MISSING_RUN_PROTOCOL", root, missing=True)
            return audit.result()
        source_info = _validate_source_contract(audit, source, repo)
        if source_info is None:
            return audit.result(kind)
        source_protocol, manifest, frozen = source_info
        if kind == "attribution":
            audit.check(_digest(manifest) == protocol["source_manifest_digest"], "ATTRIBUTION_MANIFEST_MISMATCH", root / "attribution_protocol.json")
        task_path = root / "datasets" / (split + ".json")
        tasks = audit.read(task_path)
        summary = audit.read(root / (split + "_summary.json"))
        provider = audit.read(root / "source_provider.json")
        source_provider = provider if source == root else audit.read(source / "source_provider.json")
        if any(value is None for value in (tasks, summary, provider, source_provider)):
            return audit.result(kind)
        cache_path = Path(manifest["settings"]["cache_path"])
        if not audit.hash_file(cache_path, manifest["settings"]["cache_sha256"]):
            return audit.result(kind)
        frozen_tasks = _manifest_tasks(manifest, split)
        audit.check(_digest(tasks) == _digest(frozen_tasks), "TASKS_DIFFER_FROM_FROZEN_CACHE", task_path)
        # Requests are reconstructed from the reference cache, not an altered dataset copy.
        tasks = frozen_tasks
        audit.counts["tasks_expected"] = len(tasks)
        audit.counts["arms_expected"] = len(arms)
        audit.counts["rows_expected"] = len(tasks) * len(arms)
        expected_ids = [task["id"] for task in tasks]
        if not audit.check(len(expected_ids) == len(set(expected_ids)), "DUPLICATE_FROZEN_TASK_IDS", task_path):
            return audit.result(kind)
        audit.check(summary.get("split") == split and summary.get("execution_mode") == frozen["execution_mode"],
                    "SUMMARY_SPLIT_OR_MODE_MISMATCH", root / (split + "_summary.json"))
        if kind == "source":
            audit.check(summary.get("protocol_hash") == _digest(protocol), "SUMMARY_PROTOCOL_MISMATCH", root / (split + "_summary.json"))
        else:
            audit.check(summary.get("protocol_sha256") == _file_hash(protocol_path), "SUMMARY_PROTOCOL_MISMATCH", root / (split + "_summary.json"))
        service = source_provider["service"]
        audit.check(provider["service"] == service, "SERVICE_DIFFERS_FROM_FROZEN_SOURCE", root / "source_provider.json")
        audit.check(service["host"] == protocol["required_provider_host"]
                    and service["cap"] == protocol["effective_max_tokens_cap"],
                    "SERVICE_HOST_OR_CAP_MISMATCH", root / "source_provider.json")
        audit.check(provider["provider"]["provider_host"] == protocol["required_provider_host"]
                    and provider["provider"]["model"] == protocol["model"],
                    "PROVIDER_HOST_OR_MODEL_MISMATCH", root / "source_provider.json")
        skills = {}
        for arm, info in protocol["arms"].items():
            path = audit.relative(root, info["snapshot"])
            if audit.hash_file(path, info["sha256"]):
                skills[arm] = path.read_text(encoding="utf-8")
        if not all(arm in skills for arm in arms):
            return audit.result(kind)
        build_system, build_user, evaluate = _builders()
        for arm in arms:
            path = root / "searchqa_rollouts" / split / arm / "results.jsonl"
            if not path.is_file():
                audit.issue("MISSING_REQUIRED_FILE", path, missing=True)
                continue
            try:
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            except (OSError, UnicodeError, ValueError):
                audit.issue("UNREADABLE_OR_INVALID_JSONL", path)
                continue
            audit.check([row.get("id") for row in rows] == expected_ids, "RESULT_IDS_OR_ORDER_MISMATCH", path)
            if len(rows) < len(tasks):
                audit.issue("INCOMPLETE_RESULT_ROWS", path, missing=True)
            for row, task in zip(rows, tasks):
                _row_audit(audit, row, task, arm, split, protocol, skills[arm], service, path,
                           build_system, build_user, evaluate)
        return audit.result(kind)
    except (KeyError, TypeError, ValueError, AttributeError, OSError, UnicodeError, ImportError):
        # Do not reveal exception messages: JSON/input/paths may contain payloads.
        audit.issue("INVALID_OR_UNREADABLE_REQUIRED_ARTIFACT", root)
        return audit.result(kind)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("calibration", "holdout"), required=True)
    args = parser.parse_args(argv)
    # Keep even import-time .pyc creation out of the read-only CLI workflow.
    sys.dont_write_bytecode = True
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    result = audit_run(args.run_dir, args.split)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return {"complete": 0, "incomplete": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
