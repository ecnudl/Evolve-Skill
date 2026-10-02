"""Frozen token-budget retries, never a revised baseline or optimizer resume.

All inputs/outputs are private. Original runs are read-only. ALFWorld recovers
only the frozen failed model call: no environment is recreated or episode scored.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import signal
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
from functools import lru_cache
from pathlib import Path
from threading import Event, Lock, current_thread, main_thread

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import CachedAPI, digest

from . import backends
from .core import load_checkpoint, output_lock, panel_tasks, read_json, require, runtime_identity, safe_path, write_json
from .runner import _costs, _stored_calls, _valid_prediction, _valid_score

VERSION = "truncation-recovery-v2"
TOKEN_CAP = 8192
BUDGET_VERSION = "truncation-recovery-v3"
BUDGET_CAP = 32768
ENVIRONMENT_VERSION = "truncation-recovery-v4"
ENVIRONMENT_CAPS = {"length": 65536, "timeout": 32768}
CEILING_VERSION = "truncation-recovery-v5"
CEILING_CAP = 131072


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _sources():
    package = Path(__file__).parent
    names = [Path(__file__), package / "backends.py", package / "native_worker.py",
             package / "spreadsheet_compat.py", package / "runner.py", package / "core.py",
             package / "datasets.py", package.parent / "validator_pilot/api.py",
             package.parent / "skill_validation/sandbox.py",
             package.parent / "envs/spreadsheetbench/evaluator.py"]
    return {str(p): _sha(p) for p in names}


@lru_cache(maxsize=8)
def _backend(source_root):
    path = safe_path(Path(source_root) / "skillopt/continual_eval/backends.py")
    name = "skillopt.continual_eval._recovery_original_" + _sha(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect(spec):
    require(type(spec) is dict and set(spec) == {"version", "runs"}
            and spec["version"] == "truncation-recovery-spec-v1", "Invalid recovery specification")
    require(type(spec["runs"]) is list and spec["runs"], "Explicit original runs required")
    files, slots, seen, old_calls, counts = {}, [], set(), set(), Counter()

    def read(path, sealed=False):
        path = safe_path(path)
        value = read_json(path, sealed=sealed)
        files[str(path)] = _sha(path)
        return value

    def bind_sources(source_root, declared):
        require(type(declared) is dict and declared, "Original source identity is missing")
        for relative, expected in declared.items():
            path = safe_path(source_root / "skillopt" / relative)
            require(path.is_relative_to(source_root / "skillopt") and _sha(path) == expected,
                    "Original frozen source changed")
            files[str(path)] = expected

    def add(task, benchmark, skill, runtime, model, prediction, receipt, provenance, service, source):
        require(prediction["status"] == "unknown" and prediction["reason"] == "model_response_truncated",
                "Only confirmed truncated predictions can be retried")
        old = receipt["request"]
        require(receipt.get("request_hash") == digest(old) and receipt.get("finish_reason") == "length"
                and receipt.get("status") == 200 and receipt.get("ok") is False
                and receipt.get("error_type") == "truncated_content",
                "Truncation must bind to an HTTP 200 finish_reason=length receipt")
        require(receipt["request_hash"] not in old_calls, "Duplicate original logical model call")
        old_calls.add(receipt["request_hash"])
        require(old["max_tokens"] == model["max_tokens"] and 0 < old["max_tokens"] < TOKEN_CAP,
                "Recovery must increase the original frozen token cap")
        require(old["model"] == model["name"] and task["partition"] == "development",
                "Only authorized development calls are supported")
        require(old["service"] == service and service["model"] == model["name"], "Original model service mismatch")
        if model["provider"] != "fixture":
            require(receipt.get("returned_model") == model["name"]
                    and service["provider"].lower() == model["provider"]
                    and service.get("reasoning_effort") == model["reasoning_effort"]
                    and service.get("proxy") == model.get("proxy"), "Original provider/model/settings mismatch")
        require(type(skill) is str and len(skill.encode()) <= 6000, "Invalid original Skill")
        slot = {"benchmark": benchmark, "task": task, "skill_text": skill, "runtime": runtime,
                "model": model, "old_request": old, "old_receipt": receipt, "provenance": provenance,
                "source_root": str(source),
                "mode": "exact_call_only_no_episode_score" if benchmark == "alfworld" else "solver_and_score"}
        slot["id"] = digest(slot)
        require(slot["id"] not in seen, "Duplicate recovery position")
        seen.add(slot["id"])
        slots.append(slot)
        counts[benchmark] += 1

    roots = set()
    for entry in spec["runs"]:
        require(type(entry) is dict and set(entry) == {"kind", "root", "source_root"}
                and entry["kind"] in {"eval", "learning"}, "Invalid original run specification")
        root, source = safe_path(entry["root"]), safe_path(entry["source_root"])
        require(str(root) not in roots, "Duplicate original run")
        roots.add(str(root))
        service_record = read(root / "model_service.json", sealed=True)
        service = {k: v for k, v in service_record.items() if k != "record_hash"}
        if entry["kind"] == "eval":
            plan = read(root / "plan.json", sealed=True)
            bind_sources(source, plan["source_identity"])
            model = plan["config"]["model"]
            checkpoints, tasks = {}, {}
            for declaration in plan["checkpoints"]:
                path = root / "checkpoints" / declaration["method"] / declaration["history"] / f"s{declaration['stage']}.json"
                if path.is_file():
                    cp = load_checkpoint(root, declaration["method"], declaration["history"], declaration["stage"], plan)
                    read(path, sealed=True)
                    checkpoints[cp["record_hash"]] = cp
            for benchmark, info in plan["panels"].items():
                if info["status"] == "present":
                    read(info["path"])
                    tasks.update({digest(t): (benchmark, t) for t in panel_tasks(plan, benchmark)})
            for path in sorted((root / "predictions").glob("*/prediction.json")):
                record = read(path, sealed=True)
                prediction = record["prediction"]
                if prediction.get("status") != "unknown" or prediction.get("reason") != "model_response_truncated":
                    continue
                position = record["request"]
                require(path.parent.name == digest(position) and position["plan_hash"] == plan["record_hash"],
                        "Original position binding mismatch")
                require(read(path.parent / "intent.json", sealed=True) == seal(position), "Original position intent mismatch")
                benchmark, task = tasks[position["task_hash"]]
                cp = checkpoints[position["checkpoint_hash"]]
                require(cp["method"] == "no_skill" and cp["skill_text"] == ""
                        and benchmark in {"korbench", "spreadsheetbench", "alfworld"},
                        "This eval recovery supports only No-Skill KOR/Sheet/ALF")
                require(benchmark == position["benchmark"] and type(position["repeat"]) is int
                        and 0 <= position["repeat"] < plan["repeats"], "Original task/repeat mismatch")
                receipts = _stored_calls(path.parent)
                matching = []
                turns = []
                for call_path in sorted((path.parent / "calls").glob("*.json")):
                    call = read(call_path, sealed=True)
                    read(path.parent / "call_intents" / call_path.name, sealed=True)
                    require(call["request"]["position"] == position, "Call belongs to another original position")
                    turns.append(call["request"]["turn"])
                    if call["receipt"].get("finish_reason") == "length":
                        matching.append(call)
                require(len(matching) == 1 and matching[0]["request"]["turn"] == max(turns)
                        and sorted(turns) == list(range(len(turns))), "Missing or ambiguous truncated call")
                require(len(receipts) == (1 if benchmark != "alfworld" else len(turns)), "Unexpected solver call count")
                add(task, benchmark, cp["skill_text"], plan["config"]["runtime"].get(benchmark, {}), model,
                    prediction, matching[0]["receipt"], {"kind": "eval", "root": str(root),
                    "prediction_hash": record["record_hash"], "position": position,
                    "call_hash": matching[0]["record_hash"], "turn": matching[0]["request"]["turn"]}, service, source)
        else:
            identity = read(root / "identity.json", sealed=True)
            manifest = identity["manifest"]
            require(seal({k: v for k, v in manifest.items() if k != "record_hash"}) == manifest,
                    "Original learning manifest is not sealed")
            bind_sources(source, manifest["source_identity"])
            if "native_sources" in identity:
                bind_sources(source, identity["native_sources"])
            panel = read(root / "panel.json")
            require(digest(panel) == manifest["panel_hash"], "Original learning panel changed")
            tasks = {digest(t): t for t in panel["tasks"]}
            skills = [manifest["parent_skill"]]
            for path in sorted((root / "native").glob("*/result.json")):
                proposal = read(path, sealed=True)
                proposal_identity = read(path.parent / "identity.json", sealed=True)
                require(proposal["identity_hash"] == proposal_identity["record_hash"]
                        and proposal_identity["manifest_hash"] == manifest["record_hash"],
                        "Candidate proposal provenance differs from original learning manifest")
                skills.append(proposal["candidate_skill"])
            skill_map = {digest({"skill": text}): text for text in skills}
            calls = {}
            for path in sorted((root / "calls").glob("*.json")):
                row = read(path, sealed=True)
                intent = read(root / "call_intents" / path.name, sealed=True)
                require(row["intent_hash"] == intent["record_hash"] and path.stem == intent["record_hash"]
                        and intent["manifest_hash"] == manifest["record_hash"], "Learning call intent mismatch")
                inner = row["receipt"]["request"]
                require(inner.get("key") == path.stem and inner.get("repeat") == 0
                        and inner.get("kind") == "continual-learning-" + row["role"]
                        and row["role"] == intent["role"]
                        and all(inner.get(k) == intent[k] for k in ("system", "user", "max_tokens")),
                        "Learning nested request mismatch")
                if row["role"] == "solver":
                    require(intent["logical_id"] not in calls, "Duplicate learning solver identity")
                    calls[intent["logical_id"]] = row
            for path in sorted((root / "evaluations").glob("*.json")):
                row = read(path, sealed=True)
                prediction = row["prediction"]
                if prediction.get("status") != "unknown" or prediction.get("reason") != "model_response_truncated":
                    continue
                request = row["request"]
                require(path.stem == digest(request) and request["manifest_hash"] == manifest["record_hash"]
                        and read(root / "evaluation_intents" / path.name, sealed=True) == seal(request),
                        "Learning evaluation intent mismatch")
                require(request["repeat"] == 0 and manifest["authorized_tasks"].get(request["task_hash"]) == request["role"],
                        "Original learning task/role not authorized")
                require(request["candidate_hash"] in skill_map, "Original candidate Skill cannot be established")
                call = calls[path.stem]
                add(tasks[request["task_hash"]], "bigcodebench", skill_map[request["candidate_hash"]],
                    manifest["runtime"], manifest["model"], prediction, call["receipt"],
                    {"kind": "learning", "root": str(root), "evaluation_hash": row["record_hash"],
                     "evaluation_request": request, "call_hash": call["record_hash"]}, service, source)
    require(slots, "No proven truncated development positions found")
    for slot in slots:
        for path, expected in slot["task"]["private"].get("asset_sha256", {}).items():
            require(_sha(path) == expected, "Original task asset changed")
            files[str(safe_path(path))] = expected
    return slots, files, dict(counts)


def prepare(spec, output):
    root = safe_path(output)
    require(not root.exists(), "Use a new recovery directory")
    slots, files, counts = _collect(spec)
    require(all(not root.is_relative_to(safe_path(e[k])) for e in spec["runs"] for k in ("root", "source_root")),
            "Recovery output must not be inside an original run/source")
    services = {digest(s["old_request"]["service"]) for s in slots}
    require(len(services) == 1 and len({digest(s["model"]) for s in slots}) == 1,
            "One recovery batch requires identical original model service/settings")
    value = seal({"version": VERSION, "max_tokens": TOKEN_CAP, "max_logical_calls": len(slots),
                  "spec": spec, "positions": slots, "counts": counts, "original_files": files,
                  "recovery_sources": _sources(), "host_runtime": runtime_identity(),
                  "evidence_kind": "engineering_fixture" if slots[0]["model"]["provider"] == "fixture"
                    else "selected_truncation_retry_diagnostic", "feedback_allowed": False,
                  "optimizer_resume_allowed": False, "old_scores_replaced": False})
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "protocol.json", value)
    return {"status": "prepared", "positions": len(slots), "counts": counts, "record_hash": value["record_hash"]}


def _verify_frozen(value, *, current):
    version = value["version"]
    expected_cap = (CEILING_CAP if version == CEILING_VERSION else
                    ENVIRONMENT_CAPS.get(value.get("selection_reason")) if version == ENVIRONMENT_VERSION
                    else BUDGET_CAP if version == BUDGET_VERSION else TOKEN_CAP)
    require(version in {"truncation-recovery-v1", VERSION, BUDGET_VERSION, ENVIRONMENT_VERSION, CEILING_VERSION}
            and type(value["max_tokens"]) is int
            and value["max_tokens"] == expected_cap
            and value["max_logical_calls"] == len(value["positions"]), "Recovery budget/protocol changed")
    require((not current or value["recovery_sources"] == _sources()) and value["host_runtime"] == runtime_identity(),
            "Recovery source/runtime changed")
    override = value.get("transport_override")
    if override is not None:
        keys = ({"read_timeout_seconds", "stream_wall_seconds"}
                if version in {ENVIRONMENT_VERSION, CEILING_VERSION} else {"read_timeout_seconds"})
        require(type(override) is dict and set(override) == keys, "Invalid transport override")
    if version == CEILING_VERSION:
        require(value.get("selection_reason") == "length"
                and override == {"read_timeout_seconds": 300, "stream_wall_seconds": 3600},
                "Ceiling diagnostic requires fixed length selection and long transport")
        require(all(s["model"]["provider"] in {"bigmodel", "fixture"}
                    and s["model"]["name"] == ("fixture" if s["model"]["provider"] == "fixture" else "glm-5.3")
                    for s in value["positions"]), "Ceiling diagnostic supports BigModel GLM-5.3 only")
    for slot in value["positions"]:
        require(_expected(slot)["max_tokens"] == value["max_tokens"], "Recovery slot budget changed")
        if version in {ENVIRONMENT_VERSION, CEILING_VERSION}:
            expected_service = _environment_service(slot["environment_retry"]["receipt"]["request"]["service"], **override)
        else:
            expected_service = (_with_read_timeout(slot["old_request"]["service"], override["read_timeout_seconds"])
                                if override is not None else slot["old_request"]["service"])
        require(slot.get("recovery_service", slot["old_request"]["service"]) == expected_service,
                "Recovery service differs from the declared transport override")
    for path, expected in value["recovery_sources"].items():
        require(_sha(path) == expected, "Recovery frozen source changed")
    for path, expected in value["original_files"].items():
        require(_sha(path) == expected, "Original evidence/source changed")
    inherited = value.get("inherited")
    if inherited:
        require(_evidence_paths(Path(inherited["parent_root"])) == inherited["evidence_paths"],
                "Parent recovery evidence roster changed")
    if version == BUDGET_VERSION:
        require(value.get("budget_parent") is not None, "Budget recovery parent missing")
        parent = value["budget_parent"]
        previous = read_json(Path(parent["parent_root"]) / "protocol.json", sealed=True)
        require(previous["record_hash"] == parent["protocol_hash"] and previous["max_tokens"] == TOKEN_CAP,
                "Budget parent protocol changed")
        old_slots = {s["id"]: s for s in previous["positions"]}
        selected_ids = {s["position_id"] for s in parent["selected_positions"]}
        require(len(selected_ids) == len(parent["selected_positions"])
                and len(parent["selected_positions"]) + len(parent["excluded_positions"]) == len(old_slots)
                and selected_ids.isdisjoint(s["position_id"] for s in parent["excluded_positions"])
                and selected_ids | {s["position_id"] for s in parent["excluded_positions"]} == set(old_slots),
                "Budget parent denominator changed")
        for slot in value["positions"]:
            lineage = slot["parent_retry"]
            require(lineage["position_id"] in selected_ids and slot["id"] == digest({k: v for k, v in slot.items() if k != "id"}),
                    "Budget recovery position lineage changed")
            old = old_slots[lineage["position_id"]]
            row = _result(Path(parent["parent_root"]), previous, old)
            receipt = read_json(Path(parent["parent_root"]) / "positions" / old["id"] / "call.json", sealed=True)["receipt"]
            require(row is not None and row["record_hash"] == lineage["result_hash"]
                    and row["call_hash"] == lineage["call_hash"] and receipt == lineage["receipt"]
                    and receipt["request_hash"] == lineage["request_hash"]
                    and lineage["protocol_hash"] == parent["protocol_hash"]
                    and lineage["parent_root"] == parent["parent_root"]
                    and {k: v for k, v in slot.items() if k not in {"id", "parent_retry", "recovery_max_tokens", "recovery_service"}}
                    == {k: v for k, v in old.items() if k not in {"id", "recovery_service"}},
                    "Budget recovery changed the original task, Skill, prompt or parent receipt")
        for ancestor in _ancestors(value):
            require(_evidence_paths(Path(ancestor["parent_root"])) == ancestor["evidence_paths"],
                    "Parent recovery evidence roster changed")
    if version in {ENVIRONMENT_VERSION, CEILING_VERSION}:
        _verify_environment(value)


def _load(root):
    value = read_json(root / "protocol.json", sealed=True)
    _verify_frozen(value, current=True)
    return value


def _expected(slot):
    return {**slot["old_request"], "max_tokens": slot.get("recovery_max_tokens", TOKEN_CAP),
            "service": slot.get("recovery_service", slot["old_request"]["service"]),
            "kind": "truncation-recovery-solver", "key": slot["id"]}


def _with_read_timeout(service, seconds):
    require(type(seconds) is int and 120 <= seconds <= 600, "Read timeout must be an integer in [120, 600]")
    require(type(service.get("timeout_seconds")) is dict and "read" in service["timeout_seconds"],
            "Original service lacks a frozen read timeout")
    return {**service, "timeout_seconds": {**service["timeout_seconds"], "read": seconds}}


def _evidence_paths(root):
    # Include temporary/partial artifacts: their presence is not proof that a
    # model call was never submitted. Logs and the advisory lock are excluded.
    return sorted(str(safe_path(p)) for folder in (root / "positions", root / "api/calls")
                  for p in folder.rglob("*") if p.is_file())


@contextmanager
def _readonly_parent_lock(root):
    import fcntl

    path = safe_path(root / ".writer.lock")
    require(path.is_file(), "Parent writer-lock file missing; cannot establish quiescence")
    with path.open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Parent recovery still has an active writer") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ancestors(value):
    def chain(item):
        while item:
            yield item
            item = item.get("prior_inherited")
    yield from chain(value.get("inherited"))
    yield from chain(value.get("budget_parent"))
    if value.get("environment_parent"):
        yield value["environment_parent"]
        yield from value["environment_ancestors"]


@contextmanager
def _parent_locks(root, *, all_versions=False):
    value = read_json(root / "protocol.json", sealed=True)
    with ExitStack() as stack:
        if all_versions or value["version"] in {BUDGET_VERSION, ENVIRONMENT_VERSION, CEILING_VERSION}:
            for path in sorted({a["parent_root"] for a in _ancestors(value)}):
                stack.enter_context(_readonly_parent_lock(safe_path(path)))
        yield


def prepare_budget(parent_output, output, *, max_tokens, read_timeout_seconds=None):
    """Select completed 8192 HTTP-200/length calls for one explicit 32768 retry."""
    require(type(max_tokens) is int and max_tokens == BUDGET_CAP, "Budget recovery requires max_tokens=32768")
    parent, root = safe_path(parent_output), safe_path(output)
    require(not root.exists() and not root.is_relative_to(parent), "Use a new independent recovery directory")
    with _readonly_parent_lock(parent), _parent_locks(parent, all_versions=True):
        previous = read_json(parent / "protocol.json", sealed=True)
        _verify_frozen(previous, current=False)
        require(previous["version"] in {"truncation-recovery-v1", VERSION}
                and previous["max_tokens"] == TOKEN_CAP, "Budget recovery requires an 8192 parent; no repeated escalation")
        require(all(not root.is_relative_to(safe_path(e[k])) for e in previous["spec"]["runs"]
                    for k in ("root", "source_root")), "Recovery output must not be inside an original run/source")
        paths = _evidence_paths(parent)
        files = {**previous["original_files"], **previous["recovery_sources"],
                 str(parent / "protocol.json"): _sha(parent / "protocol.json")}
        files.update({p: _sha(p) for p in paths})
        slots, selected, excluded, receipts, counts = [], [], [], [], Counter()
        allowed, seen_requests = set(), set()
        override = previous.get("transport_override")
        if read_timeout_seconds is not None:
            override = {"read_timeout_seconds": read_timeout_seconds}
        for slot in previous["positions"]:
            base = parent / "positions" / slot["id"]
            row = _result(parent, previous, slot)
            require(row is not None, "Budget parent must be completed with no open or unsubmitted positions")
            _valid_prediction(row["prediction"])
            _valid_score(row["score"])
            allowed.update(str(safe_path(base / name)) for name in ("intent.json", "result.json"))
            receipt = None
            if row["call_hash"] is not None:
                receipt = read_json(base / "call.json", sealed=True)["receipt"]
                expected = _expected(slot)
                identifier = digest(expected)
                require(identifier not in seen_requests, "Duplicate parent retry call identity")
                seen_requests.add(identifier)
                cache = parent / "api/calls" / (identifier + ".json")
                require(cache.is_file() and read_json(cache) == receipt, "Parent API and position receipts differ or cache missing")
                allowed.update(str(safe_path(p)) for p in (base / "call.json", base / "call_intent.json", cache))
            prediction = row["prediction"]
            is_truncated = prediction["status"] == "unknown" and prediction.get("reason") == "model_response_truncated"
            evidence = {"position_id": slot["id"], "benchmark": slot["benchmark"],
                        "result_hash": row["record_hash"], "call_hash": row["call_hash"],
                        "prediction_status": prediction["status"], "prediction_reason": prediction.get("reason"),
                        "score_status": row["score"]["status"]}
            if not is_truncated:
                excluded.append(evidence)
                continue
            require(receipt is not None and receipt.get("status") == 200
                    and receipt.get("finish_reason") == "length" and receipt.get("ok") is False
                    and receipt.get("error_type") == "truncated_content"
                    and receipt.get("returned_model") == slot["model"]["name"]
                    and (not receipt["request"]["service"].get("stream") or receipt.get("stream_complete") is True),
                    "Budget selection requires a complete HTTP 200 finish_reason=length receipt")
            require(slot["task"]["partition"] == "development", "Only authorized development calls are supported")
            service = (_with_read_timeout(slot["old_request"]["service"], override["read_timeout_seconds"])
                       if override is not None else slot["old_request"]["service"])
            parent_retry = {"parent_root": str(parent), "protocol_hash": previous["record_hash"],
                            **evidence, "request_hash": receipt["request_hash"], "receipt": receipt}
            new = {**{k: v for k, v in slot.items() if k != "id"}, "recovery_max_tokens": max_tokens,
                   "recovery_service": service, "parent_retry": parent_retry}
            new["id"] = digest(new)
            slots.append(new)
            selected.append(evidence)
            receipts.append(receipt)
            counts[slot["benchmark"]] += 1
        require(set(paths) == allowed, "Unbound or partial parent recovery evidence; operator review required")
        require(slots, "No completed proven truncations remain in parent")
        require(len({digest(_expected(s)["service"]) for s in slots}) == 1
                and len({digest(s["model"]) for s in slots}) == 1, "Budget recovery requires one frozen model service")
        transport_changed = any(_expected(s)["service"] != s["parent_retry"]["receipt"]["request"]["service"] for s in slots)
        budget_parent = {"parent_root": str(parent), "protocol_hash": previous["record_hash"],
                         "eligible_positions": len(previous["positions"]), "selected_positions": selected,
                         "excluded_positions": excluded, "evidence_paths": paths,
                         "selected_retry_costs": _costs(receipts), "summary": _report(parent, previous),
                         "prior_inherited": previous.get("inherited")}
        value = seal({"version": BUDGET_VERSION, "max_tokens": max_tokens, "max_logical_calls": len(slots),
                      "spec": previous["spec"], "positions": slots, "counts": dict(counts),
                      "original_files": files, "recovery_sources": _sources(), "host_runtime": runtime_identity(),
                      "budget_parent": budget_parent, "evidence_kind": previous["evidence_kind"],
                      "budget_change": {"from": TOKEN_CAP, "to": max_tokens},
                      "transport_changed_from_parent": transport_changed, "pure_token_comparison": False,
                      "feedback_allowed": False, "optimizer_resume_allowed": False, "old_scores_replaced": False,
                      **({"transport_override": override} if override is not None else {})})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
    return {"status": "prepared", "positions": len(slots), "counts": dict(counts),
            "parent_positions": len(previous["positions"]), "excluded_positions": len(excluded),
            "record_hash": value["record_hash"]}


def _environment_service(service, *, read_timeout_seconds, stream_wall_seconds):
    from skillopt.validator_pilot.api import long_stream_service

    return long_stream_service(service, read_timeout_seconds=read_timeout_seconds,
                               stream_wall_seconds=stream_wall_seconds)


def _environment_eligible(row, receipt, reason, slot):
    if row["prediction"]["status"] != "unknown" or row["score"]["status"] != "unknown" or not receipt:
        return False
    if reason == "length":
        return (row["prediction"].get("reason") == "model_response_truncated"
                and receipt.get("status") == 200 and receipt.get("finish_reason") == "length"
                and receipt.get("ok") is False and receipt.get("error_type") == "truncated_content"
                and receipt.get("returned_model") == slot["model"]["name"]
                and (not receipt["request"]["service"].get("stream") or receipt.get("stream_complete") is True))
    return (reason == "timeout" and row["prediction"].get("reason") == "model_call_unavailable"
            and receipt.get("ok") is False and receipt.get("error_type") == "timeout"
            and receipt.get("finish_reason") is None and not receipt.get("response")
            and type(receipt.get("http_attempt_count")) is int and receipt["http_attempt_count"] > 0)


def _verify_environment(value):
    parent = value["environment_parent"]
    root = Path(parent["parent_root"])
    previous = read_json(root / "protocol.json", sealed=True)
    ceiling = value["version"] == CEILING_VERSION
    valid_parent = (previous["version"] == ENVIRONMENT_VERSION
                    and previous["max_tokens"] in ENVIRONMENT_CAPS.values()) if ceiling else (
                        previous["version"] == BUDGET_VERSION and previous["max_tokens"] == BUDGET_CAP)
    require(valid_parent
            and previous["record_hash"] == parent["protocol_hash"], "Environment parent changed")
    require(value["environment_ancestors"] == list(_ancestors(previous)), "Environment ancestor chain changed")
    old_slots = {s["id"]: s for s in previous["positions"]}
    selected = {s["position_id"] for s in parent["selected_positions"]}
    excluded = {s["position_id"] for s in parent["excluded_positions"]}
    require(len(selected) == len(parent["selected_positions"]) == len(value["positions"])
            and len(excluded) == len(parent["excluded_positions"])
            and selected.isdisjoint(excluded) and selected | excluded == set(old_slots),
            "Environment parent denominator changed")
    require(selected == {s["environment_retry"]["position_id"] for s in value["positions"]},
            "Environment selection changed")
    for slot in value["positions"]:
        lineage = slot["environment_retry"]
        old = old_slots[lineage["position_id"]]
        row = _result(root, previous, old)
        receipt = read_json(root / "positions" / old["id"] / "call.json", sealed=True)["receipt"]
        require(row is not None and row["record_hash"] == lineage["result_hash"]
                and row["call_hash"] == lineage["call_hash"] and receipt == lineage["receipt"]
                and receipt["request_hash"] == lineage["request_hash"]
                and lineage["protocol_hash"] == parent["protocol_hash"]
                and lineage["parent_root"] == parent["parent_root"]
                and lineage["reason"] == value["selection_reason"]
                and slot["id"] == digest({k: v for k, v in slot.items() if k != "id"})
                and _environment_eligible(row, receipt, value["selection_reason"], old),
                "Environment retry eligibility or receipt changed")
        ignored = {"id", "environment_retry", "recovery_max_tokens", "recovery_service"}
        require({k: v for k, v in slot.items() if k not in ignored}
                == {k: v for k, v in old.items() if k not in ignored},
                "Environment retry changed original task, Skill, prompt or prior lineage")
    for ancestor in _ancestors(value):
        require(_evidence_paths(Path(ancestor["parent_root"])) == ancestor["evidence_paths"],
                "Parent recovery evidence roster changed")


def prepare_environment(parent_output, output, *, reason, read_timeout_seconds, stream_wall_seconds):
    """One explicit new transport trial, split by terminal failure mechanism.

    Length uses 65536; closed transport timeouts retain 32768. Complete wrong
    answers, unsubmitted tasks, and ambiguous/open calls are never resampled.
    """
    return _prepare_environment(parent_output, output, reason=reason, read_timeout_seconds=read_timeout_seconds,
                                stream_wall_seconds=stream_wall_seconds, ceiling=False)


def prepare_ceiling(parent_output, output):
    """One final explicit 131072 diagnostic of completed v4 length calls.

    Never recursively increase the ceiling, retry complete wrong answers, or
    replace a frozen baseline. The longer per-HTTP deadline is not a pure token
    intervention. Normal evaluation and learning retain their separate limits.
    """
    return _prepare_environment(parent_output, output, reason="length", read_timeout_seconds=300,
                                stream_wall_seconds=3600, ceiling=True)


def _prepare_environment(parent_output, output, *, reason, read_timeout_seconds, stream_wall_seconds, ceiling):
    require(reason in ENVIRONMENT_CAPS, "Environment reason must be length or timeout")
    cap = CEILING_CAP if ceiling else ENVIRONMENT_CAPS[reason]
    parent, root = safe_path(parent_output), safe_path(output)
    require(not root.exists() and not root.is_relative_to(parent), "Use a new independent recovery directory")
    with _readonly_parent_lock(parent), _parent_locks(parent, all_versions=True):
        previous = read_json(parent / "protocol.json", sealed=True)
        _verify_frozen(previous, current=False)
        if ceiling:
            require(previous["version"] == ENVIRONMENT_VERSION
                    and previous["max_tokens"] in ENVIRONMENT_CAPS.values(),
                    "Ceiling recovery requires completed v4 parent; no repeated escalation")
        else:
            require(previous["version"] == BUDGET_VERSION and previous["max_tokens"] == BUDGET_CAP,
                    "Environment recovery requires completed v3 32768 parent; no automatic escalation")
        require(all(not root.is_relative_to(safe_path(e[k])) for e in previous["spec"]["runs"]
                    for k in ("root", "source_root")), "Recovery output must not be inside an original run/source")
        paths = _evidence_paths(parent)
        files = {**previous["original_files"], **previous["recovery_sources"],
                 str(parent / "protocol.json"): _sha(parent / "protocol.json"), **{p: _sha(p) for p in paths}}
        override = {"read_timeout_seconds": read_timeout_seconds, "stream_wall_seconds": stream_wall_seconds}
        slots, selected, excluded, receipts, counts = [], [], [], [], Counter()
        allowed, seen_requests = set(), set()
        for old in previous["positions"]:
            base = parent / "positions" / old["id"]
            row = _result(parent, previous, old)
            require(row is not None, "Environment parent must be completed; no open or unsubmitted positions")
            _valid_prediction(row["prediction"])
            _valid_score(row["score"])
            allowed.update(str(safe_path(base / name)) for name in ("intent.json", "result.json"))
            receipt = None
            if row["call_hash"] is not None:
                receipt = read_json(base / "call.json", sealed=True)["receipt"]
                identifier = digest(_expected(old))
                require(identifier not in seen_requests, "Duplicate parent retry call identity")
                seen_requests.add(identifier)
                cache = parent / "api/calls" / (identifier + ".json")
                require(cache.is_file() and read_json(cache) == receipt, "Parent API and position receipts differ or cache missing")
                allowed.update(str(safe_path(p)) for p in (base / "call.json", base / "call_intent.json", cache))
            evidence = {"position_id": old["id"], "benchmark": old["benchmark"], "result_hash": row["record_hash"],
                        "call_hash": row["call_hash"], "prediction_status": row["prediction"]["status"],
                        "prediction_reason": row["prediction"].get("reason"), "score_status": row["score"]["status"]}
            if not _environment_eligible(row, receipt, reason, old):
                excluded.append(evidence)
                continue
            require(old["task"]["partition"] == "development", "Only authorized development calls are supported")
            if ceiling:
                require(old["model"]["provider"] in {"bigmodel", "fixture"}
                        and old["model"]["name"] == ("fixture" if old["model"]["provider"] == "fixture" else "glm-5.3"),
                        "Ceiling diagnostic supports BigModel GLM-5.3 only")
            service = _environment_service(receipt["request"]["service"], **override)
            lineage = {"parent_root": str(parent), "protocol_hash": previous["record_hash"], **evidence,
                       "reason": reason, "request_hash": receipt["request_hash"], "receipt": receipt}
            new = {**{k: v for k, v in old.items() if k != "id"}, "environment_retry": lineage,
                   "recovery_max_tokens": cap, "recovery_service": service}
            new["id"] = digest(new)
            slots.append(new)
            selected.append(evidence)
            receipts.append(receipt)
            counts[old["benchmark"]] += 1
        require(set(paths) == allowed, "Unbound or partial parent recovery evidence; operator review required")
        require(slots, "No terminal calls qualify for the selected environment reason")
        require(len({digest(_expected(s)["service"]) for s in slots}) == 1
                and len({digest(s["model"]) for s in slots}) == 1, "Environment recovery requires one model service")
        parent_record = {"parent_root": str(parent), "protocol_hash": previous["record_hash"],
                         "eligible_positions": len(previous["positions"]), "selected_positions": selected,
                         "excluded_positions": excluded, "evidence_paths": paths,
                         "selected_retry_costs": _costs(receipts), "summary": _report(parent, previous)}
        value = seal({"version": CEILING_VERSION if ceiling else ENVIRONMENT_VERSION, "max_tokens": cap,
                      "max_logical_calls": len(slots), "selection_reason": reason, "transport_override": override,
                      "spec": previous["spec"], "positions": slots, "counts": dict(counts),
                      "original_files": files, "recovery_sources": _sources(), "host_runtime": runtime_identity(),
                      "environment_parent": parent_record, "environment_ancestors": list(_ancestors(previous)),
                      "evidence_kind": previous["evidence_kind"], "feedback_allowed": False,
                      "optimizer_resume_allowed": False, "old_scores_replaced": False})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
    return {"status": "prepared", "positions": len(slots), "counts": dict(counts), "selection_reason": reason,
            "max_tokens": cap, "parent_positions": len(previous["positions"]),
            "excluded_positions": len(excluded), "record_hash": value["record_hash"]}


def prepare_resume(parent_output, output, *, read_timeout_seconds=None):
    """Freeze only never-started calls; ambiguous calls are not sampled again."""
    parent, root = safe_path(parent_output), safe_path(output)
    require(not root.exists() and not root.is_relative_to(parent), "Use a new independent recovery directory")
    with _readonly_parent_lock(parent), _parent_locks(parent):
        previous = read_json(parent / "protocol.json", sealed=True)
        _verify_frozen(previous, current=False)
        require(previous["version"] not in {ENVIRONMENT_VERSION, CEILING_VERSION},
                "Environment recovery resumes in the same directory; new fork needs operator review")
        require(all(not root.is_relative_to(safe_path(e[k])) for e in previous["spec"]["runs"]
                    for k in ("root", "source_root")), "Recovery output must not be inside an original run/source")
        paths = _evidence_paths(parent)
        files = {**previous["original_files"], **previous["recovery_sources"],
                 str(parent / "protocol.json"): _sha(parent / "protocol.json")}
        files.update({p: _sha(p) for p in paths})
        by_request = {digest(_expected(s)): s for s in previous["positions"]}
        require(len(by_request) == len(previous["positions"]), "Duplicate parent retry call identity")
        cached = {}
        for path in (parent / "api/calls").glob("*"):
            if not path.is_file():
                continue
            receipt = read_json(path)
            identifier = receipt.get("request_hash")
            require(identifier in by_request and receipt.get("request") == _expected(by_request[identifier]),
                    "Unbound or partial parent API cache; operator review required")
            require(path.name == identifier + ".json", "Nonterminal parent API cache; operator review required")
            require(identifier not in cached, "Duplicate parent API receipt")
            cached[identifier] = receipt
        slots, excluded, counts, inherited_counts, receipts = [], [], Counter(), {}, {}
        unclosed = 0
        for slot in previous["positions"]:
            base = parent / "positions" / slot["id"]
            expected = _expected(slot)
            cached_receipt = cached.get(digest(expected))
            row = _result(parent, previous, slot)
            touched = base.exists() or cached_receipt is not None
            if not touched:
                slots.append(slot)
                counts[slot["benchmark"]] += 1
                continue
            group = inherited_counts.setdefault(slot["benchmark"], Counter())
            group["excluded_positions"] += 1
            state = "completed" if row is not None else "interrupted_unknown"
            group[state] += 1
            if row:
                group["score_" + row["score"]["status"]] += 1
            if (base / "intent.json").exists():
                require(read_json(base / "intent.json", sealed=True) == seal({"protocol_hash": previous["record_hash"],
                        "position_id": slot["id"]}), "Parent recovery position intent mismatch")
            if (base / "call_intent.json").exists():
                require(read_json(base / "call_intent.json", sealed=True) == seal(expected),
                        "Parent recovery call intent mismatch")
            receipt = cached_receipt
            if (base / "call.json").exists():
                receipt = read_json(base / "call.json", sealed=True)["receipt"]
                require(receipt.get("request") == expected and receipt.get("request_hash") == digest(expected),
                        "Parent recovery receipt mismatch")
                require(cached_receipt is None or cached_receipt == receipt, "Parent API and position receipts differ")
            if receipt:
                receipts[digest(expected)] = receipt
            elif row is None:
                # Even a position-only intent may have preceded a lost write.
                # Do not report missing receipts as zero-cost semantic failures.
                unclosed += 1
            excluded.append({"position_id": slot["id"], "benchmark": slot["benchmark"], "status": state,
                             "result_hash": row["record_hash"] if row else None,
                             "terminal_receipt_available": receipt is not None})
        require(slots, "No never-started recovery positions remain")
        override = previous.get("transport_override")
        if read_timeout_seconds is not None:
            override = {"read_timeout_seconds": read_timeout_seconds}
            # Change only the transport wait bound, after classifying parent
            # evidence using its own original request/service identities.
            slots = [{**s, "recovery_service": _with_read_timeout(s["old_request"]["service"], read_timeout_seconds)}
                     for s in slots]
            if previous["version"] == BUDGET_VERSION:
                slots = [{**s, "id": digest({k: v for k, v in s.items() if k != "id"})} for s in slots]
        inherited = {"parent_root": str(parent), "protocol_hash": previous["record_hash"],
                     "eligible_positions": len(previous["positions"]), "excluded_positions": excluded,
                     "counts": {k: dict(v) for k, v in inherited_counts.items()},
                     "retry_costs": _costs(list(receipts.values()), unclosed=unclosed),
                     "evidence_paths": paths, "prior_inherited": previous.get("inherited"),
                     "interrupted_positions_are_model_errors": False}
        value = seal({**{k: v for k, v in previous.items() if k not in {"record_hash", "inherited"}},
                      "version": BUDGET_VERSION if previous["version"] == BUDGET_VERSION else VERSION,
                      "positions": slots, "counts": dict(counts),
                      "max_logical_calls": len(slots), "original_files": files, "recovery_sources": _sources(),
                      "host_runtime": runtime_identity(), "inherited": inherited,
                      **({"transport_changed_from_parent": any(_expected(s)["service"] !=
                           s["parent_retry"]["receipt"]["request"]["service"] for s in slots)}
                         if previous["version"] == BUDGET_VERSION else {}),
                      **({"transport_override": override} if override is not None else {})})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", value)
    return {"status": "prepared", "positions": len(slots), "counts": dict(counts),
            "inherited_excluded_positions": len(excluded), "record_hash": value["record_hash"]}


def request_pause(output):
    root = safe_path(output)
    require((root / "protocol.json").is_file(), "Recovery protocol missing")
    write_json(root / "PAUSE", {"pause_requested": True})
    return {"status": "pause_requested", "inflight_behavior": "drain_without_new_dispatch",
            "resume": "Explicitly remove PAUSE, then run the same directory; do not suspend the process"}


@contextmanager
def _pause_signals(root):
    stopped, previous = Event(), {}
    def handler(signum, frame):
        stopped.set()
    if current_thread() is main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, handler)
    try:
        yield lambda: stopped.is_set() or (root / "PAUSE").exists()
    finally:
        try:
            if stopped.is_set():
                request_pause(root)
        finally:
            for sig, old in previous.items():
                signal.signal(sig, old)


def _result(root, value, slot):
    base = root / "positions" / slot["id"]
    if not (base / "result.json").exists():
        return None
    row = read_json(base / "result.json", sealed=True)
    require(row["protocol_hash"] == value["record_hash"] and row["position_id"] == slot["id"],
            "Recovery result identity mismatch")
    require(read_json(base / "intent.json", sealed=True) == seal({"protocol_hash": value["record_hash"],
            "position_id": slot["id"]}), "Recovery position intent mismatch")
    if row["call_hash"] is not None:
        call = read_json(base / "call.json", sealed=True)
        request = call["receipt"]["request"]
        expected = _expected(slot)
        require(request == expected and call["receipt"]["request_hash"] == digest(expected)
                and call["record_hash"] == row["call_hash"]
                and read_json(base / "call_intent.json", sealed=True) == seal(expected), "Recovery call binding mismatch")
    else:
        require(not (base / "call.json").exists() and not (base / "call_intent.json").exists(),
                "Unaccounted recovery call")
    return row


def run(output, *, repo=None, workers=1, fixture_api=None, fixture_solve=None, fixture_score=None):
    require(type(workers) is int and 1 <= workers <= 10, "Workers must be 1..10")
    root = safe_path(output)
    with output_lock(root), _pause_signals(root) as stopping, _parent_locks(root):
        value = _load(root)
        fixture = value["evidence_kind"] == "engineering_fixture"
        require(fixture == (fixture_api is not None and fixture_solve is not None and fixture_score is not None),
                "Fixture callbacks require a fixture protocol")
        require(fixture or all(x is None for x in (fixture_api, fixture_solve, fixture_score)), "Natural callback injection")
        pending = []
        for slot in value["positions"]:
            if _result(root, value, slot) is None:
                require(not (root / "positions" / slot["id"]).exists()
                        and not (root / "api/calls" / (digest(_expected(slot)) + ".json")).exists(),
                        "Interrupted recovery position; no automatic resampling")
                pending.append(slot)
        if not pending:
            return report(root)
        if stopping():
            request_pause(root)
            return report(root)
        api = fixture_api
        if not fixture:
            require(repo is not None, "Credential repository required")
            for source, benchmark, runtime in {(s["source_root"], s["benchmark"], json.dumps(s["runtime"], sort_keys=True)) for s in pending
                                       if s["benchmark"] != "alfworld"}:
                require(_backend(source).readiness(benchmark, json.loads(runtime))["status"] == "ready", "Native runtime unavailable")
            model, service = pending[0]["model"], _expected(pending[0])["service"]
            api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=workers,
                reasoning_effort=model["reasoning_effort"], stream=service.get("stream", False),
                initial_health_policy=service.get("initial_health_policy", "legacy_success_only"),
                read_timeout_seconds=service["timeout_seconds"]["read"],
                **({"stream_wall_seconds": service["stream_max_wall_seconds"]} if "stream_transport" in service else {}),
                **({"proxy": service["proxy"]} if "proxy" in service else {}))
        try:
            require(api.service == _expected(pending[0])["service"] and api.model == pending[0]["old_request"]["model"],
                    "Model service differs from original request")
            dispatch_lock = Lock()

            def one(slot):
                base = root / "positions" / slot["id"]
                with dispatch_lock:
                    if stopping():
                        return None
                    write_json(base / "intent.json", seal({"protocol_hash": value["record_hash"], "position_id": slot["id"]}))
                # Once reserved, finish this call and score even if pause arrives.
                call_record, guard_error = None, None

                def callback(system, user):
                    nonlocal call_record, guard_error
                    old = slot["old_request"]
                    if system != old["system"] or user != old["user"]:
                        guard_error = "original_prompt_mismatch"
                        raise ValueError(guard_error)
                    require(call_record is None and not (base / "call_intent.json").exists(), "Only one new logical call allowed")
                    expected = _expected(slot)
                    write_json(base / "call_intent.json", seal(expected))
                    receipt = api.call(system, user, expected["kind"], expected["key"],
                                       max_tokens=value["max_tokens"], repeat=old["repeat"])
                    require(receipt.get("request") == expected and receipt.get("request_hash") == digest(expected),
                            "New model receipt belongs to another request")
                    call_record = seal({"receipt": receipt})
                    write_json(base / "call.json", call_record)
                    return receipt

                try:
                    if slot["mode"] == "exact_call_only_no_episode_score":
                        response, costs, reason = backends._response(callback, slot["old_request"]["system"], slot["old_request"]["user"])
                        prediction = {"status": "available" if response is not None else "unknown", "output": response,
                                      "costs": costs, "reason": reason}
                        score = {"status": "unknown", "score": None, "metrics": {}, "reason": "unsupported_full_episode_resume"}
                    else:
                        original = _backend(slot["source_root"]) if not fixture else None
                        solver, scorer = (fixture_solve, fixture_score) if fixture else (original.solve, original.score)
                        prediction = _valid_prediction(solver(slot["benchmark"], slot["task"]["public"], slot["skill_text"],
                                                             callback, runtime=slot["runtime"]))
                        score = _valid_score(scorer(slot["benchmark"], slot["task"]["public"], slot["task"]["private"],
                                                   prediction, runtime=slot["runtime"]))
                    if guard_error:
                        score = {"status": "unknown", "score": None, "metrics": {}, "reason": guard_error}
                except Exception as exc:
                    prediction = {"status": "unknown", "output": None, "reason": "recovery_exception:" + type(exc).__name__}
                    score = {"status": "unknown", "score": None, "metrics": {}, "reason": guard_error or prediction["reason"]}
                # An API intent without receipt is ambiguous: preserve it and do
                # not write a misleading closed result that later permits retry.
                require(call_record is not None or not (base / "call_intent.json").exists(),
                        "Recovery call interrupted or receipt invalid; retained open intent")
                row = seal({"protocol_hash": value["record_hash"], "position_id": slot["id"],
                            "call_hash": call_record["record_hash"] if call_record else None,
                            "prediction": prediction, "score": score, "mode": slot["mode"],
                            "feedback_allowed": False, "old_scores_replaced": False})
                write_json(base / "result.json", row)
                return row

            first = one(pending[0])
            if first is not None:
                require(first["call_hash"] is not None, "First recovery prompt/call unavailable; remaining positions not submitted")
                first_call = read_json(root / "positions" / pending[0]["id"] / "call.json", sealed=True)["receipt"]
                require(api._initial_ready(first_call), "First real recovery response unavailable; remaining positions not submitted")
                # Never queue the entire panel. At most `workers` submitted
                # futures exist; a pause or exception stops all replenishment.
                remaining = iter(pending[1:])
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    active, exhausted = set(), False
                    while active or not exhausted:
                        while not exhausted and len(active) < workers and not stopping():
                            slot = next(remaining, None)
                            if slot is None:
                                exhausted = True
                            else:
                                active.add(pool.submit(one, slot))
                        if not active:
                            break
                        done, active = wait(active, timeout=0.25, return_when=FIRST_COMPLETED)
                        for future in done:
                            future.result()  # Includes KeyboardInterrupt: drain then propagate, never swallow.
        finally:
            if api is not None and not fixture:
                api.close()
    return report(root)


def _inherited_summary(value):
    if value is None:
        return None
    return {k: value[k] for k in ("parent_root", "protocol_hash", "eligible_positions", "counts", "retry_costs",
                                 "interrupted_positions_are_model_errors")} | {
        "excluded_positions": len(value["excluded_positions"]),
        "prior_inherited": _inherited_summary(value["prior_inherited"])}


def report(output):
    root = safe_path(output)
    with _parent_locks(root):
        return _report(root, _load(root))


def _report(root, value):
    counts, completed, receipts, open_calls = {}, 0, [], 0
    for slot in value["positions"]:
        group = counts.setdefault(slot["benchmark"], Counter())
        group["eligible"] += 1
        row = _result(root, value, slot)
        base = root / "positions" / slot["id"]
        if (base / "call.json").exists():
            receipts.append(read_json(base / "call.json", sealed=True)["receipt"])
        elif (base / "call_intent.json").exists():
            open_calls += 1
        if row is None:
            group["pending"] += 1
            continue
        completed += 1
        group["response_" + row["prediction"]["status"]] += 1
        group["score_" + row["score"]["status"]] += 1
    status = "completed" if completed == len(value["positions"]) else "paused" if (root / "PAUSE").exists() else "pending"
    result = {"version": value["version"], "status": status,
            "protocol_hash": value["record_hash"], "eligible_positions": len(value["positions"]),
            "completed_positions": completed, "counts": {k: dict(v) for k, v in counts.items()},
            "new_costs": _costs(receipts, unclosed=open_calls),
            "inherited": _inherited_summary(value.get("inherited")),
            "transport_override": value.get("transport_override"),
            "old_selected_call_costs": _costs([s["old_receipt"] for s in value["positions"]]),
            "evidence_kind": value["evidence_kind"], "selection": "only_prior_confirmed_truncations",
            "whole_benchmark_accuracy_claimed": False, "causal_token_effect_claimed": False,
            "old_scores_replaced": False, "optimizer_resumed": False, "alfworld_episode_scores_recovered": 0}
    if value["version"] == BUDGET_VERSION:
        parent = value["budget_parent"]
        result.update(max_tokens=value["max_tokens"], budget_change=value["budget_change"],
                      transport_changed_from_parent=value["transport_changed_from_parent"], pure_token_comparison=False,
                      parent_selected_retry_costs=parent["selected_retry_costs"],
                      budget_parent={k: parent[k] for k in ("parent_root", "protocol_hash", "eligible_positions", "summary")}
                      | {"selected_positions": len(parent["selected_positions"]), "excluded_positions": len(parent["excluded_positions"])})
    if value["version"] in {ENVIRONMENT_VERSION, CEILING_VERSION}:
        parent = value["environment_parent"]
        result.update(max_tokens=value["max_tokens"], selection="prior_terminal_" + value["selection_reason"],
                      budget_change={"from": (parent["summary"]["max_tokens"]
                                              if value["version"] == CEILING_VERSION else BUDGET_CAP),
                                     "to": value["max_tokens"]},
                      transport_changed_from_parent=True, pure_token_comparison=False,
                      parent_selected_retry_costs=parent["selected_retry_costs"],
                      environment_parent={k: parent[k] for k in ("parent_root", "protocol_hash", "eligible_positions", "summary")}
                      | {"selected_positions": len(parent["selected_positions"]), "excluded_positions": len(parent["excluded_positions"])})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "prepare-resume", "prepare-budget", "prepare-environment", "prepare-ceiling", "pause", "run", "report"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--spec")
    parser.add_argument("--parent")
    parser.add_argument("--read-timeout", type=int, help="Explicit read timeout for a new prepare-resume/prepare-budget protocol")
    parser.add_argument("--max-tokens", type=int, help="32768, for a new prepare-budget protocol only")
    parser.add_argument("--reason", choices=("length", "timeout"), help="Explicit terminal failure stratum for prepare-environment")
    parser.add_argument("--stream-wall", type=int, help="Whole-attempt stream deadline for prepare-environment")
    parser.add_argument("--repo")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    require(args.read_timeout is None or args.command in {"prepare-resume", "prepare-budget", "prepare-environment"},
            "Read timeout changes require prepare-resume, prepare-budget or prepare-environment")
    require(args.max_tokens is None or args.command == "prepare-budget", "Token budget changes require prepare-budget")
    require((args.reason is None and args.stream_wall is None) or args.command == "prepare-environment",
            "Environment changes require prepare-environment")
    if args.command == "prepare":
        require(args.spec is not None, "prepare requires --spec")
        result = prepare(read_json(args.spec), args.output)
    elif args.command == "prepare-budget":
        require(args.parent is not None and args.max_tokens is not None, "prepare-budget requires --parent and --max-tokens")
        result = prepare_budget(args.parent, args.output, max_tokens=args.max_tokens, read_timeout_seconds=args.read_timeout)
    elif args.command == "prepare-environment":
        require(args.parent is not None and args.reason is not None and args.read_timeout is not None
                and args.stream_wall is not None, "prepare-environment requires parent, reason, read-timeout and stream-wall")
        result = prepare_environment(args.parent, args.output, reason=args.reason,
                                     read_timeout_seconds=args.read_timeout, stream_wall_seconds=args.stream_wall)
    elif args.command == "prepare-ceiling":
        require(args.parent is not None, "prepare-ceiling requires --parent")
        result = prepare_ceiling(args.parent, args.output)
    elif args.command == "prepare-resume":
        require(args.parent is not None, "prepare-resume requires --parent")
        result = prepare_resume(args.parent, args.output, read_timeout_seconds=args.read_timeout)
    elif args.command == "pause":
        result = request_pause(args.output)
    elif args.command == "run":
        result = run(args.output, repo=args.repo, workers=args.workers)
    else:
        result = report(args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"prepared", "completed", "pause_requested"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
