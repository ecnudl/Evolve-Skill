"""One new proposal branch over explicitly frozen development evidence.

This is not optimizer resume or semantics-preserving JSON repair. Seven valid
analyst responses are replayed; two malformed responses get one fresh proposal
each under their original prompts. Native merge/rank/apply and a full selection
panel follow, subject to the remaining original budget. Historical data stays
read-only and unknown remains Pending.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import warnings
from contextlib import contextmanager
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, runtime_identity, safe_path, write_json
from skillopt.continual_eval.runner import _valid_prediction, _valid_score
from skillopt.validator_pilot.api import CachedAPI, digest

from .contracts import sources
from .gepa import Adapter
from .ledger import LearningPending, Ledger
from .skillopt import _stage_artifacts, native_sources, propose_native

VERSION = "skillopt-frozen-evidence-reproposal-v1"


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


@contextmanager
def _parent_lock(root):
    import fcntl

    path = safe_path(root / ".writer.lock")
    require(path.is_file(), "Parent lock missing")
    with path.open("rb") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Parent learner still has an active writer") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _parse(response):
    from skillopt.utils.json_utils import extract_json

    with warnings.catch_warnings(record=True):
        value = extract_json(response)
    if value is None:
        return None
    require(type(value) is dict and type(value.get("patch")) is dict
            and type(value["patch"].get("edits")) is list, "Unsupported analyst schema; not this recovery protocol")
    return value


def _collect(parent, source):
    """Validate original execution/proposal identity without importing outcomes."""
    from skillopt.optimizer.update_modes import truncate_payload

    identity = read_json(parent / "identity.json", sealed=True)
    result = read_json(parent / "result.json", sealed=True)
    old = identity["manifest"]
    panel = read_json(parent / "panel.json")
    fixture = old["model"]["provider"] == "fixture"
    require(old["version"] == "continual-learning-v2" and old["method"] == "skillopt"
            and old["parent_skill"] == "" and old["panel_hash"] == digest(panel), "Unsupported original learner/parent")
    require(result["identity_hash"] == identity["record_hash"] and result["status"] == "pending"
            and result["reason"] == "native_reflection_parse_incomplete" and result["steps"] == []
            and result["candidate_skill"] == old["parent_skill"], "Only pre-candidate parse-incomplete parents are supported")
    require(old["host_runtime"] == runtime_identity() and identity["native_sources"] == native_sources(),
            "Original runtime or native algorithm changed")
    ledger = Ledger(parent, old, None)
    costs = ledger.snapshot()
    require(costs == result["costs"] and costs["usage_complete"] and costs["unclosed_calls"] == 0,
            "Parent calls/costs incomplete")
    artifacts = _stage_artifacts(parent, ledger)
    require(result["artifacts"] == artifacts, "Parent evidence changed")
    files = {str(parent / relative): expected for relative, expected in artifacts.items()}
    for name in ("identity.json", "result.json", "panel.json", "model_service.json"):
        files[str(parent / name)] = _sha(parent / name)
    for relative, expected in {**old["source_identity"], **identity["native_sources"]}.items():
        path = safe_path(source / "skillopt" / relative)
        require(path.is_relative_to(source / "skillopt") and _sha(path) == expected, "Original frozen source changed")
        files[str(path)] = expected
    require(_sha(source / "skillopt/continual_eval/backends.py") == _sha(Path(backends.__file__)),
            "Solver/scorer implementation changed; not an identical-prompt branch")
    require(len(panel["tasks"]) == 129 and all(t["partition"] == "development" for t in panel["tasks"]),
            "This bounded branch requires the original 129 development tasks")
    service = read_json(parent / "model_service.json", sealed=True)
    service.pop("record_hash")
    calls, cache_paths = {}, set()
    for path in sorted((parent / "calls").glob("*.json")):
        row = read_json(path, sealed=True)
        intent = read_json(parent / "call_intents" / path.name, sealed=True)
        receipt = row["receipt"]
        require(receipt["ok"] is True and receipt["finish_reason"] == "stop"
                and receipt["request"]["service"] == service
                and receipt["request"]["model"] == old["model"]["name"], "Parent delivery or service differs")
        if not fixture:
            require(receipt.get("returned_model") == old["model"]["name"], "Parent returned model differs")
            cache = parent / "api/calls" / (receipt["request_hash"] + ".json")
            require(read_json(cache) == receipt, "Parent API cache differs from receipt")
            files[str(cache)] = _sha(cache)
            cache_paths.add(str(cache))
        key = (row["role"], intent["logical_id"])
        require(key not in calls, "Duplicate parent logical call")
        calls[key] = {"receipt": receipt, "intent": intent}
    if not fixture:
        require({str(p) for p in (parent / "api/calls").glob("*")} == cache_paths, "Unbound parent API artifacts")
    evaluations = {}
    for path in (parent / "evaluations").glob("*.json"):
        row = read_json(path, sealed=True)
        request = row["request"]
        require(path.stem == digest(request)
                and read_json(parent / "evaluation_intents" / path.name, sealed=True) == seal(request)
                and request["manifest_hash"] == old["record_hash"]
                and request["candidate_hash"] == digest({"skill": old["parent_skill"]}) and request["repeat"] == 0
                and old["authorized_tasks"].get(request["task_hash"]) == request["role"], "Parent task/Skill/role mismatch")
        _valid_prediction(row["prediction"])
        _valid_score(row["score"])
        require(row["prediction"]["status"] == "available" and row["score"]["status"] in {"pass", "fail"},
                "Parent semantic evidence is incomplete")
        require(request["task_hash"] not in evaluations, "Duplicate parent task evidence")
        if not fixture:
            call = calls.get(("solver", path.stem))
            require(call is not None and call["intent"]["max_tokens"] == old["budget"]["solver_max_tokens"]
                    and backends._code(call["receipt"]["response"]) == row["prediction"]["output"],
                    "Parent prediction is not bound to its Solver call")
        evaluations[request["task_hash"]] = row
    require(set(evaluations) == {digest(t) for t in panel["tasks"]}
            and len(list((parent / "evaluation_intents").glob("*.json"))) == 129, "Parent panel not fully evaluated")
    train = [t for t in panel["tasks"] if old["authorized_tasks"][digest(t)] == "train"]
    selection = [t for t in panel["tasks"] if old["authorized_tasks"][digest(t)] == "selection"]
    require(len(train) == 65 and len(selection) == 64 and len({t["family_id"] for t in train}) == 64
            and len({t["family_id"] for t in selection}) == 64, "Frozen task/family roster changed")
    traces = [{"Inputs": t["public"], "Generated Outputs": evaluations[digest(t)]["prediction"]["output"],
               "Feedback": {k: evaluations[digest(t)]["score"][k] for k in ("status", "score")},
               "evidence_hash": evaluations[digest(t)]["record_hash"]} for t in train]
    proposal_identity = read_json(parent / "native/0/identity.json", sealed=True)
    require(not (parent / "native/0/result.json").exists()
            and proposal_identity["manifest_hash"] == old["record_hash"]
            and proposal_identity["traces_hash"] == digest(traces)
            and proposal_identity["parent_skill"] == old["parent_skill"]
            and proposal_identity["seed"] == old["seed"] and proposal_identity["step"] == 0
            and proposal_identity["minibatch_size"] == old["budget"]["minibatch_size"]
            and proposal_identity["edit_budget"] == 4 and proposal_identity["native_sources"] == native_sources(),
            "Parent proposal/trace identity differs")
    failures = sum(t["Feedback"]["status"] == "fail" for t in traces)
    failure_batches = math.ceil(failures / old["budget"]["minibatch_size"])
    expected = failure_batches + math.ceil((len(traces) - failures) / old["budget"]["minibatch_size"])
    reflection = {logical: row for (role, logical), row in calls.items() if role == "reflection"}
    require(expected == len(reflection) == 9 and costs["reflection_calls"] == 9
            and (fixture or costs["solver_calls"] == 129), "Original call roster is not the bounded first proposal")
    reusable, malformed, patch_files = [], [], set()
    for index in range(9):
        logical = f"skillopt:0:analyst:{index}"
        require(logical in reflection, "Parent reflection stage/index mismatch")
        call = reflection[logical]
        require(call["intent"]["max_tokens"] == old["budget"]["reflection_max_tokens"], "Parent reflection budget differs")
        parsed = _parse(call["receipt"]["response"])
        failure = index < failure_batches
        path = parent / "native/0/patches" / (f"minibatch_fail_{index:03d}.json" if failure
                                               else f"minibatch_succ_{index-failure_batches:03d}.json")
        if parsed is None:
            require(not path.exists(), "Malformed response has an unexplained saved patch")
            malformed.append(logical)
        else:
            parsed["source_type"] = "failure" if failure else "success"
            truncate_payload(parsed["patch"], 4, "patch")
            require(read_json(path) == parsed, "Saved patch differs from actual analyst response")
            reusable.append(logical)
            patch_files.add(path.name)
    require(len(reusable) == 7 and len(malformed) == 2
            and {p.name for p in (parent / "native/0/patches").glob("*")} == patch_files,
            "Expected exactly seven reusable and two malformed responses")
    return {"manifest": old, "panel": panel, "traces": traces, "selection": selection, "reflection": reflection,
            "reusable": reusable, "malformed": malformed, "costs": costs, "files": files, "service": service,
            "parent_score": sum(evaluations[digest(t)]["score"]["score"] for t in selection) / len(selection),
            "selection_rows": {digest(t): evaluations[digest(t)] for t in selection}, "result_hash": result["record_hash"]}


def _manifest(inherited):
    old, costs = inherited["manifest"], inherited["costs"]
    budget = {**old["budget"], "max_iterations": 1}
    for field, consumed in (("max_metric_calls", 129), ("max_api_calls", costs["logical_calls"]),
                            ("max_reflection_calls", costs["reflection_calls"]),
                            ("max_reported_tokens", costs["reported_tokens_known_subtotal"])):
        budget[field] -= consumed
        require(budget[field] > 0, "Inherited evidence exhausted the original budget")
    require(budget["max_metric_calls"] >= 64 and budget["max_reflection_calls"] >= 2,
            "Insufficient remaining selection/reproposal budget")
    return seal({**{k: v for k, v in old.items() if k != "record_hash"}, "version": VERSION,
                 "budget": budget, "source_identity": sources(),
                 "feedback_authorization": "explicit_frozen_development_evidence_reuse",
                 "parent_manifest_hash": old["record_hash"], "parent_result_hash": inherited["result_hash"]})


def prepare(parent_output, parent_source_root, output):
    parent, source, root = safe_path(parent_output), safe_path(parent_source_root), safe_path(output)
    require(not root.exists() and not root.is_relative_to(parent) and not root.is_relative_to(source),
            "Use a new independent proposal directory")
    with _parent_lock(parent):
        inherited = _collect(parent, source)
        old, costs = inherited["manifest"], inherited["costs"]
        new_manifest = _manifest(inherited)
        protocol = seal({"version": VERSION, "parent_root": str(parent), "parent_source_root": str(source),
                         "parent_result_hash": inherited["result_hash"], "parent_manifest_hash": old["record_hash"],
                         "original_files": inherited["files"], "current_sources": sources(), "host_runtime": runtime_identity(),
                         "native_sources": native_sources(), "manifest": new_manifest, "reusable": inherited["reusable"],
                         "malformed": inherited["malformed"], "inherited_costs": costs, "original_budget": old["budget"],
                         "max_new_analyst_calls": 2, "retries_per_malformed_logical_call": 1,
                         "semantics_preserving_repair": False, "optimizer_resumed": False,
                         "old_scores_replaced": False, "deployment_authorized": False,
                         "evidence_kind": old["evidence_kind"]})
        root.mkdir(parents=True, mode=0o700)
        write_json(root / "protocol.json", protocol)
        write_json(root / "panel.json", inherited["panel"])
    return {"status": "prepared_not_launched", "protocol_hash": protocol["record_hash"], "model_calls": 0,
            "reused_solver_evaluations": 129, "reused_analyst_responses": 7, "new_analyst_call_limit": 2}


def _load(root):
    value = read_json(root / "protocol.json", sealed=True)
    require(value["version"] == VERSION and value["current_sources"] == sources()
            and value["native_sources"] == native_sources() and value["host_runtime"] == runtime_identity(),
            "New proposal source/runtime changed")
    require(all(_sha(Path(p)) == h for p, h in value["original_files"].items()), "Inherited evidence/source changed")
    inherited = _collect(safe_path(value["parent_root"]), safe_path(value["parent_source_root"]))
    require(inherited["result_hash"] == value["parent_result_hash"]
            and inherited["files"] == value["original_files"]
            and inherited["reusable"] == value["reusable"] and inherited["malformed"] == value["malformed"]
            and read_json(root / "panel.json") == inherited["panel"], "Branch lineage changed")
    require(value["manifest"] == _manifest(inherited) and value["inherited_costs"] == inherited["costs"]
            and value["original_budget"] == inherited["manifest"]["budget"]
            and value["max_new_analyst_calls"] == 2 and value["retries_per_malformed_logical_call"] == 1,
            "Branch budget or authorization changed")
    return value, inherited


class _EvidenceView:
    """Read-only old trace binding; all new calls go to the new Ledger."""

    def __init__(self, parent, inherited, ledger):
        self.root, self.manifest = parent, inherited["manifest"]
        self.inherited, self.ledger, self.served = inherited, ledger, set()

    def call(self, role, logical, system, user, max_tokens):
        require(role == "reflection", "Only native optimizer calls use the evidence view")
        if logical in self.inherited["reflection"]:
            require(logical not in self.served, "A reflection cannot be sampled twice")
            prior = self.inherited["reflection"][logical]
            require(all(prior["intent"][k] == v for k, v in
                        (("system", system), ("user", user), ("max_tokens", max_tokens))),
                    "Reconstructed analyst prompt/budget differs from the original")
            self.served.add(logical)
            if logical in self.inherited["reusable"]:
                return prior["receipt"]
            require(logical in self.inherited["malformed"], "Unapproved analyst retry")
            return self.ledger.call(role, "new-proposal:" + logical, system, user, max_tokens)
        require(self.served == set(self.inherited["reflection"])
                and re.fullmatch(r"skillopt:0:(merge|ranking):\d+", logical), "Unexpected optimizer stage")
        return self.ledger.call(role, "native:" + logical, system, user, max_tokens)


def run(output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    from skillopt.evaluation.gate import evaluate_gate

    root = safe_path(output)
    value = read_json(root / "protocol.json", sealed=True)
    with output_lock(root), _parent_lock(safe_path(value["parent_root"])):
        value, inherited = _load(root)
        new = value["manifest"]
        fixture = new["model"]["provider"] == "fixture"
        require(fixture == (fixture_api is not None and fixture_evaluate is not None)
                and (fixture or (fixture_api is None and fixture_evaluate is None)), "Fixture callback boundary")
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            require(result["protocol_hash"] == value["record_hash"]
                    and result["artifacts"] == _stage_artifacts(root, Ledger(root, new, None)), "Branch evidence changed")
            return result
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_branch_no_automatic_resume", "model_calls_submitted": 0}
        if not fixture:
            require(repo is not None and backends.readiness("bigcodebench", new["runtime"])["status"] == "ready",
                    "Native runtime and credential repository required")
        write_json(root / "started.json", seal({"protocol_hash": value["record_hash"]}))
        api = fixture_api
        try:
            if not fixture:
                model = new["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                                reasoning_effort=model["reasoning_effort"], **model["transport"],
                                **({"proxy": model["proxy"]} if "proxy" in model else {}))
            require(api.service == inherited["service"], "Branch must retain the original model service")
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, new, api)
            view = _EvidenceView(safe_path(value["parent_root"]), inherited, ledger)
            proposal = propose_native(inherited["manifest"]["parent_skill"], inherited["traces"], root / "native/0", view,
                                      step=0, seed=new["seed"], minibatch_size=new["budget"]["minibatch_size"], edit_budget=4)
            require(view.served == set(inherited["reflection"]), "Not all frozen batches were incorporated")
            candidate = proposal["candidate_skill"]
            parent_skill, parent_score = inherited["manifest"]["parent_skill"], inherited["parent_score"]
            if proposal["status"] == "no_update" or candidate == parent_skill:
                # An identical Skill is not a new candidate. Resampling it could
                # turn execution randomness into a spurious learning improvement.
                require(candidate == parent_skill, "No-update proposal changed the Skill")
                payload = {"status": "completed", "reason": "no_update", "candidate_skill": parent_skill,
                           "selected_skill": parent_skill, "parent_score": parent_score, "candidate_score": parent_score,
                           "candidate_score_source": "inherited_parent_no_new_evaluation", "gate_action": "no_update",
                           "paired_to_parent": None, "selection_completed": 0, "selection_planned": 0}
            else:
                adapter = Adapter(new, root, ledger, fixture_evaluate=fixture_evaluate)
                selected = adapter.evaluate_rows([{"role": "selection", "task": t} for t in inherited["selection"]],
                                                 {"skill": candidate})
                score = sum(r["score"] for r in selected) / len(selected)
                gate = evaluate_gate(candidate, score, parent_skill, parent_score, parent_skill, parent_score, 0, 1, metric="hard")
                pairs = {"wins": 0, "losses": 0, "ties": 0}
                for task, row in zip(inherited["selection"], selected):
                    old_score = inherited["selection_rows"][digest(task)]["score"]["score"]
                    pairs["wins" if row["score"] > old_score else "losses" if row["score"] < old_score else "ties"] += 1
                payload = {"status": "completed", "reason": "new_proposal_native_development_selection",
                           "candidate_skill": candidate, "selected_skill": gate.current_skill, "parent_score": parent_score,
                           "candidate_score": score, "candidate_score_source": "new_full_selection",
                           "gate_action": gate.action, "paired_to_parent": pairs,
                           "selection_completed": len(selected), "selection_planned": 64}
        except Exception as exc:
            payload = {"status": "pending", "reason": str(exc) if isinstance(exc, LearningPending) else type(exc).__name__,
                       "selected_skill": inherited["manifest"]["parent_skill"], "selection_planned": 64}
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, new, api)
        costs = ledger.snapshot()
        selection_records = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
        selection_closed = len(selection_records)
        selection_unknown = sum(r["score"]["status"] == "unknown" for r in selection_records)
        if not costs["usage_complete"] and payload["status"] == "completed":
            payload.update(status="pending", reason="incomplete_usage", selected_skill=inherited["manifest"]["parent_skill"])
        result = seal({"version": VERSION, "protocol_hash": value["record_hash"], **payload,
                       "new_costs": costs, "inherited_costs": value["inherited_costs"],
                       "total_logical_calls": costs["logical_calls"] + value["inherited_costs"]["logical_calls"],
                       "reported_tokens_known_subtotal": costs["reported_tokens_known_subtotal"]
                            + value["inherited_costs"]["reported_tokens_known_subtotal"],
                       "reused_solver_evaluations": 129, "reused_analyst_responses": 7,
                       "selection_panel_size": 64, "selection_closed": selection_closed,
                       "selection_unknown": selection_unknown,
                       "selection_not_closed": payload["selection_planned"] - selection_closed,
                       "evidence_kind": value["evidence_kind"], "artifacts": _stage_artifacts(root, ledger),
                       "semantics_preserving_repair": False, "optimizer_resumed": False,
                       "old_scores_replaced": False, "deployment_authorized": False, "resume_supported": False})
        write_json(terminal, result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "check"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--parent")
    parser.add_argument("--parent-source")
    parser.add_argument("--repo")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        require(args.parent is not None and args.parent_source is not None, "Parent run and source required")
        result = prepare(args.parent, args.parent_source, args.output)
    elif args.command == "run":
        result = run(args.output, repo=args.repo)
    else:
        root = safe_path(args.output)
        value = read_json(root / "protocol.json", sealed=True)
        with _parent_lock(safe_path(value["parent_root"])):
            value, _ = _load(root)
        result = {"status": "validated_not_launched", "protocol_hash": value["record_hash"], "model_calls": 0}
    print(json.dumps({k: result[k] for k in ("status", "reason", "protocol_hash", "model_calls", "new_costs",
        "inherited_costs", "parent_score", "candidate_score", "gate_action", "selection_completed") if k in result},
        ensure_ascii=False))
    return 0 if result["status"] != "pending" else 3


if __name__ == "__main__":
    raise SystemExit(main())
