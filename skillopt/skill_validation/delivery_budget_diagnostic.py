"""Post-hoc first-draft delivery diagnosis, not Skill-effect replication.

Freeze A's sole h0/local candidate and all 78 shared tasks; cross two fresh
budgets with No-Skill/local. The original prompt mentions a possible future
revision, but this experiment deliberately stops at the initial answer. No
repair, Research, evolution, outcome-based selection or deployment is allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot import api as api_module
from skillopt.validator_pilot.api import CachedAPI, digest

from . import public_revision
from .mechanism_study import _accounting
from .mechanism_tasks import audit_row, deserialize_row
from .mechanism_transport import ConfiguredExecutorPool
from .models import ArtifactRecord, SourceFile, require
from .natural_study import _read, _write
from .panel import checked_path
from .rule_learning import _json_response
from .rule_skill import RuleSkill, RuleUpdate, apply_update, render_skill
from .single_round import IMAGE, _healthy, parse_code

VERSION = "posthoc-first-draft-delivery-budget-diagnostic-v1"
CAPS, CONDITIONS = (2048, 4096), ("no_skill", "local")
FROZEN_MODULES = ("mechanism_tasks.py", "curriculum_tasks.py", "public_revision.py", "rule_solver.py", "sandbox.py")


def _artifact(value):
    return ArtifactRecord.from_dict({k: v for k, v in verify(value).items() if k != "record_hash"})


def _durable(root, request, namespace):
    key = digest({"protocol": namespace, **{k: request[k] for k in ("system", "user", "kind", "repeat", "max_tokens")}})
    require(request.get("key") == key, "Source request namespace changed")
    request_hash = digest(request)
    path = checked_path(root / "api/calls" / (request_hash + ".json"))
    require(path.is_file() and path.stat().st_size <= 2_000_000, "Missing or oversized durable response")
    receipt = json.loads(path.read_text())
    require(receipt.get("request") == request and receipt.get("request_hash") == request_hash
            and type(receipt.get("ok")) is bool, "Durable response binding changed")
    return receipt


def _source_receipt(source, request, namespace):
    receipt = _durable(source, request, namespace)
    intent = _read(source / "histories/h0/budget/intents" / (receipt["request_hash"] + ".json"))
    require(intent == seal({"request_hash": receipt["request_hash"], "protocol_hash": namespace,
                           "kind": request["kind"], "repeat": request["repeat"]}), "Original A reservation changed")
    return receipt


class _Captured(Exception):
    pass


def _original_prompt(row, skill, condition, repeat):
    """Capture the unchanged old adapter BEFORE any write, API or execution."""
    captured = {}
    def call(system, user, kind, *, repeat, max_tokens):
        captured.update(system=system, user=user, kind=kind, repeat=repeat, max_tokens=max_tokens)
        raise _Captured
    try:
        public_revision.solve_public_initial(row, render_skill(skill), condition, repeat,
                                             SimpleNamespace(call=call), None)
    except _Captured:
        pass
    require(set(captured) == {"system", "user", "kind", "repeat", "max_tokens"}, "Original prompt capture failed")
    return captured


def load_source(source):
    """Read completed registration, frozen candidate and original draft receipts.

    Old audit outcomes never select tasks, calls or artifacts. All 78 tasks and
    both repeats are imported even when an original draft failed to arrive.
    """
    source = checked_path(source)
    protocol, summary = _read(source / "protocol.json"), _read(source / "summary.json")
    require(summary.get("status") == "completed_shadow_pilot" and summary["protocol_hash"] == protocol["record_hash"]
            and protocol.get("repeats") == 2, "Completed A with two registered repetitions required")
    for name in FROZEN_MODULES:
        require(protocol.get("source_hashes", {}).get(name)
                == hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest(),
                "Use A's original frozen task/execution module: " + name)
    panel, frozen_panel = _read(source / "host_only/panel.json"), _read(source / "frozen_panel.json")
    manifest, qualification = verify(panel["manifest"]), _read(source / "qualification_summary.json")
    require(frozen_panel.get("protocol_hash") == protocol["record_hash"]
            and frozen_panel.get("manifest_hash") == protocol.get("manifest_hash") == manifest["record_hash"]
            and frozen_panel.get("before_learning") is True
            and frozen_panel.get("qualification_hash") == qualification["record_hash"]
            and qualification.get("panel_hash") == manifest["record_hash"]
            and qualification.get("status") == "qualified" and qualification.get("formal_eligible") is True,
            "Source registration/qualification is not frozen and bound")
    require([digest(r) for r in panel["confirmation"]] == manifest["row_hashes"]["confirmation"], "Original task rows changed")
    rows = [deserialize_row(row) for row in panel["confirmation"]]
    require(len(rows) == len({r["task"].contract.task_id for r in rows}) == 78
            and all(r["task"].contract.partition == "skill_confirmation" for r in rows),
            "Retain all 78 original tasks, not only old unknown cases")
    freeze = _read(source / "frozen_candidates.json")
    require(freeze["record_hash"] == summary["freeze_hash"] and freeze["protocol_hash"] == protocol["record_hash"]
            and freeze.get("before_any_confirmation") is True, "Candidate was not frozen before A confirmation")
    history = verify(freeze["histories"]["h0"])
    parent, local = (RuleSkill.from_dict(history["skills"][c]) for c in CONDITIONS)
    require(not parent.rules and len(local.rules) == 1 and history["update_statuses"]["local"] == "candidate"
            and history["protocol_hash"] == protocol["record_hash"] and history["history"] == "h0",
            "This post-hoc case is exactly the frozen h0/local candidate")
    proposal = _read(source / "histories/h0/updates/local.json")
    request, update = verify(proposal["request"]), verify(proposal["update"])
    namespace = digest([protocol["record_hash"], "h0"])
    receipt = _source_receipt(source, proposal["api_receipt"]["request"], namespace)
    require(receipt == proposal["api_receipt"] and receipt.get("ok") is True
            and receipt["request"]["service"] == protocol["service"]
            and receipt["request"]["max_tokens"] == 2048 and receipt["request"]["repeat"] == 0
            and receipt["request"]["kind"] == "same-feedback-rule-update"
            and all(receipt["request"][k] == request[k] for k in ("system", "user"))
            and proposal["status"] == update["status"] == "candidate" and proposal["strategy"] == "local"
            and request["parent_hash"] == update["parent_hash"] == parent.content_hash
            and request["feedback_bundle_hash"] == history["feedback_hash"], "Candidate proposal binding changed")
    parsed = RuleUpdate.from_dict(_json_response(receipt["response"]))
    allowed = {e["id"] for e in request["evidence_catalog"]}
    require(all(set(e.evidence_ids) <= allowed and (e.rule is None or set(e.rule.evidence_ids) <= allowed)
                for e in parsed.edits), "Candidate cites an unknown original evidence handle")
    require(apply_update(parent, parsed, max_edits=request["max_edits"]).skill == local
            and update["candidate"] == local.to_dict(), "Frozen candidate is not the original response")
    roster = _read(source / "expected_positions.json")["positions"]
    selected = [p for p in roster if p["history"] == "h0" and p["exposure"] == "raw" and p["condition"] in CONDITIONS]
    lookup = {r["task"].contract.task_id: r for r in rows}
    require(len(selected) == 312 and {(p["task_id"], p["repeat"], p["condition"]) for p in selected}
            == {(t, n, c) for t in lookup for n in range(2) for c in CONDITIONS}, "Incomplete original draft roster")
    prompts, origins = {}, {}
    for position in selected:
        row, condition = lookup[position["task_id"]], position["condition"]
        require(all(position[k] == v for k, v in {"family_id": row["family_id"], "region": row["region"],
                    "domain": row["task"].contract.domain}.items()), "Draft registration metadata changed")
        base = source / "histories/h0/confirmation" / digest(position)
        result = _read(base / "rule_result.json")
        draft_hash = result["initial_artifact_hash"]
        draft = _artifact(_read(base / "artifacts" / (draft_hash + ".json")))
        initial = _read(base / "public_initial" / (draft_hash + ".json"))
        receipt = _source_receipt(source, initial["api_receipt"]["request"], namespace)
        skill = parent if condition == "no_skill" else local
        solver_condition = "no_skill" if condition == "no_skill" else "candidate"
        prompt = _original_prompt(row, skill, solver_condition, position["repeat"])
        require(receipt == initial["api_receipt"] and all(receipt["request"].get(k) == v for k, v in prompt.items())
                and receipt["request"]["service"] == protocol["service"]
                and initial["artifact_record_hash"] == draft.content_hash == draft_hash
                and draft.task_hash == row["task"].contract.content_hash and draft.condition == solver_condition
                and draft.repeat == position["repeat"] and draft.skill_hash == hashlib.sha256(render_skill(skill).encode()).hexdigest()
                and draft.source_hash == digest(receipt) and draft.source_ref.endswith(":" + receipt["request_hash"]),
                "Original prompt, task, Skill, draft or response identity changed")
        expected_availability, expected_files = "api_failure", ()
        if receipt["ok"]:
            try:
                expected_files = (SourceFile("solution.py", parse_code(receipt.get("response"))), SourceFile.from_dict(row["public_wrapper"]))
                expected_availability = "available"
            except (ValueError, TypeError, KeyError):
                expected_availability = "parse_failure"
        require(draft.availability == expected_availability and draft.files == expected_files
                and initial.get("hidden_feedback_used") is False
                and draft.provenance_kind == ("fixture" if protocol["service"].get("fixture") else "model"),
                "Original draft does not match its response/parser/provenance")
        key = (position["task_id"], position["repeat"], condition)
        prompts[key] = {k: prompt[k] for k in ("system", "user")}
        origins[str(digest(key))] = {"initial_record_hash": initial["record_hash"], "request_hash": receipt["request_hash"],
                                  "receipt_hash": digest(receipt), "artifact_hash": draft_hash}
    return {"rows": rows, "skills": {"no_skill": parent, "local": local}, "prompts": prompts,
            "source_protocol": protocol, "source_summary_hash": summary["record_hash"],
            "source_freeze_hash": freeze["record_hash"], "proposal_hash": proposal["record_hash"], "original_drafts": origins}


def make_roster(rows, seed):
    require(type(seed) is int and seed >= 0, "A fixed nonnegative ordering seed is required")
    rng, roster = random.Random(seed), []
    tasks = sorted(rows, key=lambda r: r["task"].contract.task_id)
    rng.shuffle(tasks)
    for row in tasks:
        for repeat in range(2):
            arms = [(cap, condition) for cap in CAPS for condition in CONDITIONS]
            rng.shuffle(arms)
            for cap, condition in arms:
                roster.append({"task_id": row["task"].contract.task_id, "family_id": row["family_id"],
                    "region": row["region"], "repeat": repeat, "condition": condition, "max_tokens": cap})
    return roster


class RegisteredCalls:
    """Only these 624 frozen requests; neither global budget nor old cache changes."""
    def __init__(self, api, root, namespace, requests):
        self.api, self.root, self.protocol_hash = api, root, namespace
        self.requests = {digest(r): r for r in requests}
        self.limit = len(requests)
        require(len(self.requests) == self.limit == 624, "Exactly 624 distinct registered initial requests required")
        require(Counter(r["max_tokens"] for r in requests) == {2048: 312, 4096: 312}
                and all(r["kind"] == "public-initial" for r in requests), "Fixed balanced initial-only budget registration required")

    def validate_existing(self):
        intents = list((self.root / "intents").glob("*.json"))
        terminals = {p.stem for p in (self.api.root / "calls").glob("*.json")}
        require(terminals <= set(self.requests) and terminals <= {p.stem for p in intents},
                "Orphan or unregistered API response cannot be adopted")
        for path in intents:
            intent = _read(path)
            require(path.stem in self.requests and intent == seal({"request_hash": path.stem,
                    "protocol_hash": self.protocol_hash}), "Unknown registered request reservation")
            _durable(self.api.root.parent, self.requests[path.stem], self.protocol_hash)

    def call(self, request):
        key = digest(request)
        require(key in self.requests and self.requests[key] == request and request["max_tokens"] in CAPS,
                "Unregistered diagnostic request or token budget")
        with public_revision._revision_lock(self.root / "locks" / key):
            intent, terminal = self.root / "intents" / (key + ".json"), self.api.root / "calls" / (key + ".json")
            expected = seal({"request_hash": key, "protocol_hash": self.protocol_hash})
            if terminal.exists():
                require(_read(intent) == expected, "Response has no original registered reservation")
                return _durable(self.api.root.parent, request, self.protocol_hash)
            require(not intent.exists(), "Interrupted request retained; never resample automatically")
            _write(intent, expected)
            result = self.api.call(request["system"], request["user"], request["kind"], request["key"],
                                   max_tokens=request["max_tokens"], repeat=request["repeat"])
            require(result == _durable(self.api.root.parent, request, self.protocol_hash), "Missing durable new response")
            return result


def summarize(rows, roster):
    expected = {digest(p): p for p in roster}
    require(len(expected) == len(roster), "Duplicate diagnostic position")
    observed = {}
    for row in rows:
        verify(row)
        key = digest(row["position"])
        require(key in expected and key not in observed and row["status"] in {"pass", "fail", "unknown"},
                "Invalid or duplicate diagnostic result")
        observed[key] = row
    grid = [observed.get(key, {"position": p, "status": "unknown", "availability": "missing",
            "api_error_type": "missing", "execution_reason": "missing"}) for key, p in expected.items()]
    def counts(values):
        usages = [r.get("usage", {}) for r in values]
        known = [u for u in usages if all(type(u.get(k)) is int for k in ("prompt_tokens", "completion_tokens"))]
        passed = sum(r["status"] == "pass" for r in values)
        evaluable = sum(r["status"] in {"pass", "fail"} for r in values)
        return {"positions": len(values), "tasks": len({r["position"]["task_id"] for r in values}),
            "declared_families": len({r["position"]["family_id"] for r in values}),
            "counts": {s: sum(r["status"] == s for r in values) for s in ("pass", "fail", "unknown")},
            "all_attempt_success": {"numerator": passed, "denominator": len(values)},
            "known_coverage": {"numerator": evaluable, "denominator": len(values)},
            "success_among_evaluable": {"numerator": passed, "denominator": evaluable},
            "delivered": sum(r["availability"] == "available" for r in values),
            "availability": dict(Counter(r["availability"] for r in values)),
            "api_errors": dict(Counter(r.get("api_error_type") or "none" for r in values)),
            "execution_reasons": dict(Counter(r.get("execution_reason") or "none" for r in values)),
            "usage_known_positions": len(known), "usage_unknown_positions": len(usages) - len(known),
            "reported_token_sum_known": {k: sum(u[k] for u in known) for k in ("prompt_tokens", "completion_tokens")}}
    arms = {}
    for cap in CAPS:
        for condition in CONDITIONS:
            values = [r for r in grid if r["position"]["max_tokens"] == cap and r["position"]["condition"] == condition]
            arms[f"{cap}/{condition}"] = {**counts(values), "by_region": {
                region: counts([r for r in values if r["position"]["region"] == region])
                for region in sorted({r["position"]["region"] for r in values})}}
    lookup = {(r["position"]["task_id"], r["position"]["repeat"], r["position"]["max_tokens"], r["position"]["condition"]): r for r in grid}
    def paired(before, after):
        pairs = [(lookup[(t, n, *before)], lookup[(t, n, *after)])
                 for t, n in sorted({(p["task_id"], p["repeat"]) for p in roster})]
        directions = Counter("unknown" if "unknown" in (a["status"], b["status"]) else "tie" if a["status"] == b["status"]
                             else "win" if b["status"] == "pass" else "loss" for a, b in pairs)
        return {"positions": len(pairs), **{s: directions[s] for s in ("win", "loss", "tie", "unknown")},
            "transitions": dict(Counter(a["status"] + "->" + b["status"] for a, b in pairs)),
            "availability_transitions": dict(Counter(a["availability"] + "->" + b["availability"] for a, b in pairs))}
    return seal({"arms": arms, "local_vs_base": {str(cap): paired((cap, "no_skill"), (cap, "local")) for cap in CAPS},
        "higher_vs_lower_budget": {c: paired((2048, c), (4096, c)) for c in CONDITIONS},
        "missing_positions": len(roster) - len(observed), "independent_tasks": False,
        "unknown_is_semantic_failure": False, "deployment_authorized": False})


def execution_accounting(rows):
    executions = {}
    for row in rows:
        key = row.get("execution_hash")
        if key is not None:
            value = {k: row.get(k) for k in ("execution_status", "execution_reason", "execution_duration_seconds")}
            require(key not in executions or executions[key] == value, "Same execution hash has inconsistent metadata")
            executions[key] = value
    durations = [r["execution_duration_seconds"] for r in executions.values()]
    known = [v for v in durations if type(v) in (int, float) and v >= 0]
    return {"audit_position_count": len(rows), "positions_with_execution": sum(r.get("execution_hash") is not None for r in rows),
        "unique_execution_receipts": len(executions), "duration_known_count": len(known),
        "reported_duration_seconds_sum_known": sum(known), "duration_unknown_count": len(durations) - len(known),
        "unique_execution_statuses": dict(Counter(r["execution_status"] for r in executions.values())),
        "unique_execution_reasons": dict(Counter(r["execution_reason"] or "none" for r in executions.values())),
        "scope": "new_host_audits_only_excludes_health_ping_and_historical_qualification"}


def run(repo, source, output, executor, *, workers=2, seed=20260927, proxy=None, prepare=False):
    require(type(workers) is int and 1 <= workers <= 4 and type(prepare) is bool, "Bounded workers and explicit prepare flag required")
    repo, source, root = (checked_path(p).resolve() for p in (repo, source, output))
    require(root != source and source not in root.parents and root not in source.parents, "New output must be outside source run")
    with public_revision._revision_lock(root / "run_lock"):
        imported = load_source(source)
        original = imported["source_protocol"]
        require(executor.identity == original["executor"], "Retain A's qualified isolated execution identity")
        service = {**original["service"], "initial_health_policy": "completed_response_v1"}
        roster = make_roster(imported["rows"], seed)
        protocol = seal({"version": VERSION, "source_protocol_hash": original["record_hash"],
            "source_summary_hash": imported["source_summary_hash"], "source_freeze_hash": imported["source_freeze_hash"],
            "proposal_hash": imported["proposal_hash"], "service": service, "executor": executor.identity,
            "transport": getattr(executor, "transport_identity", {}), "seed": seed, "workers": workers,
            "caps": list(CAPS), "conditions": list(CONDITIONS), "task_count": 78, "repeats": 2,
            "roster_hash": digest(roster), "original_drafts_hash": digest(imported["original_drafts"]),
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))},
            "api_source_hash": hashlib.sha256(Path(api_module.__file__).read_bytes()).hexdigest(),
            "candidate_selection": "post_hoc_fixed_A_h0_local_not_replication", "request_limit": 624,
            "prompt_unchanged_mentions_future_revision": True, "first_draft_only": True, "revision_calls": 0,
            "all_budgets_prescheduled_not_failure_retries": True, "old_solver_cache_reused": False,
            "research": False, "evolution": False, "deployment_authorized": False})
        requests = []
        for p in roster:
            prompt = imported["prompts"][p["task_id"], p["repeat"], p["condition"]]
            request = {**prompt, "kind": "public-initial", "repeat": p["repeat"], "max_tokens": p["max_tokens"]}
            require(len((request["system"] + request["user"]).encode()) <= 120000, "Original prompt exceeds bounded diagnostic limit")
            key = digest({"protocol": protocol["record_hash"], **request})
            requests.append({**request, "key": key, "model": service.get("model", "fixture-no-model"), "service": service})
        _write(root / "protocol.json", protocol)
        _write(root / "expected_positions.json", seal({"positions": roster}))
        frozen = seal({"protocol_hash": protocol["record_hash"], "before_any_new_call": True,
            "skills": {c: s.to_dict() for c, s in imported["skills"].items()}, "requests": requests,
            "source_drafts": imported["original_drafts"], "deployment_authorized": False})
        _write(root / "frozen_inputs.json", frozen)
        # Validate every interrupted reservation before credentials, network or model access.
        metadata_api = SimpleNamespace(root=root / "api")
        RegisteredCalls(metadata_api, root / "budget", protocol["record_hash"], requests).validate_existing()
        if (root / "summary.json").exists():
            result = _read(root / "summary.json")
            require(result["protocol_hash"] == protocol["record_hash"], "Diagnostic summary protocol changed")
            return result
        if prepare:
            return seal({"status": "prepared_delivery_diagnostic", "protocol_hash": protocol["record_hash"],
                "positions": len(roster), "new_model_calls": 0, "deployment_authorized": False})
        with CachedAPI(repo, root / "api", workers=workers, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy, initial_health_policy="completed_response_v1") as api:
            require(api.service == service, "Diagnostic service differs from frozen A plus explicit health policy")
            files = {"ping.py": "def ping():\n    return True\n"}
            ping = verify(executor.run(files, "ping", "ping", [], {}))
            _healthy(ping)
            require(ping.get("status") == "observed" and ping.get("actual") is True
                    and ping.get("input_hash") == digest({"files": files, "module": "ping", "function": "ping", "args": [], "kwargs": {}}),
                    "Safe executor unavailable before paid draft calls")
            calls = RegisteredCalls(api, root / "budget", protocol["record_hash"], requests)
            lookup = {r["task"].contract.task_id: r for r in imported["rows"]}
            def draft(job):
                position, request = job
                row, skill = lookup[position["task_id"]], imported["skills"][position["condition"]]
                receipt = calls.call(request)
                availability, files = "api_failure", ()
                if receipt["ok"]:
                    try:
                        files = (SourceFile("solution.py", parse_code(receipt.get("response"))), SourceFile.from_dict(row["public_wrapper"]))
                        availability = "available"
                    except (ValueError, TypeError, KeyError):
                        availability = "parse_failure"
                shash = hashlib.sha256(render_skill(skill).encode()).hexdigest()
                condition = "no_skill" if position["condition"] == "no_skill" else "candidate"
                artifact = ArtifactRecord(row["task"].contract.content_hash, position["repeat"], condition,
                    "none" if condition == "no_skill" else "skill-" + shash[:16], shash, files, availability,
                    "fixture" if service.get("fixture") else "model", True, False,
                    ("bigmodel-request:" if service.get("provider") == "BIGMODEL" else "pjlab-request:") + receipt["request_hash"], digest(receipt))
                value = seal({"position": position, "artifact": artifact.to_dict(), "request_hash": receipt["request_hash"],
                    "receipt_hash": digest(receipt), "availability": availability, "api_error_type": receipt.get("error_type"),
                    "finish_reason": receipt.get("finish_reason"), "http_status": receipt.get("status"),
                    "usage": receipt.get("usage", {}), "http_attempt_count": receipt.get("http_attempt_count", 0)})
                _write(root / "positions" / digest(position) / "draft.json", value)
                return value
            drafts = api.parallel(list(zip(roster, requests)), draft, "all registered first drafts before any audit")
            _write(root / "all_drafts_frozen.json", seal({"protocol_hash": protocol["record_hash"], "drafts": drafts,
                "all_calls_completed_before_audit": True}))
            def audit(value):
                position = value["position"]
                row, artifact = lookup[position["task_id"]], ArtifactRecord.from_dict(value["artifact"])
                result = verify(audit_row(row, artifact, executor, root / "positions" / digest(position)))
                require(result["artifact_hash"] == artifact.content_hash and result["task_hash"] == row["task"].content_hash,
                        "Audit belongs to another draft or task")
                execution = (result.get("receipt") or {}).get("execution")
                _healthy(execution)
                value = seal({**{k: v for k, v in value.items() if k != "record_hash"}, "status": result["status"],
                    "audit_hash": result["record_hash"], "execution_status": execution.get("status") if execution else None,
                    "execution_reason": execution.get("reason") if execution else None,
                    "execution_exception": execution.get("exception") if execution else None,
                    "execution_hash": digest(execution) if execution else None,
                    "execution_duration_seconds": execution.get("duration_seconds") if execution else None,
                    "hidden_feedback_used": False, "deployment_authorized": False})
                _write(root / "positions" / digest(position) / "result.json", value)
                return value
            results = api.parallel(drafts, audit, "frozen first-draft host audit; no feedback")
            _write(root / "diagnostic_rows.json", seal({"rows": results}))
            summary = seal({"version": VERSION, "status": "completed_delivery_diagnostic", "protocol_hash": protocol["record_hash"],
                "freeze_hash": frozen["record_hash"], "metrics": summarize(results, roster), "accounting": _accounting(api, {"all": calls}),
                "execution_accounting": execution_accounting(results),
                "provenance": "engineering_fixture" if service.get("fixture") else "post_hoc_real_model_synthetic_shared_panel",
                "first_draft_only": True, "independent_replication": False, "research": False, "deployment_authorized": False,
                "limitations": ["Candidate and panel chosen after seeing A; not independent method-effect evidence.",
                    "Original prompt mentions a possible later repair; this diagnostic scores only its first answer.",
                    "Both budgets are independent prescheduled interventions, not resampled failed old calls.",
                    "Unknown API, parse and runtime outcomes are not confirmed semantic failures.",
                    "No revision, learning, Research, hidden feedback or deployment; historical A outcomes remain unchanged."]})
            _write(root / "summary.json", summary)
            return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    for name in ("source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE, help="Must match the original A executor image exactly")
    parser.add_argument("--ssh-config", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--proxy")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args(argv)
    executor = ConfiguredExecutorPool(args.remote_repo, workers=args.workers, host=args.host,
        remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.source, args.output, executor, workers=args.workers,
                     seed=args.seed, proxy=args.proxy, prepare=args.prepare)
        print(json.dumps({k: result[k] for k in ("status", "positions", "new_model_calls", "accounting") if k in result}))
    finally:
        executor.close()


if __name__ == "__main__":
    main()
