"""Read-only V7 evidence audit; no API construction or artifact re-execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import audit_coevolution_v6 as prior  # noqa: E402
from skillopt.coevolution_evidence_view import research_evidence_view  # noqa: E402
from skillopt.coevolution_v5 import adapters as coding  # noqa: E402
from skillopt.coevolution_v5 import core, governance  # noqa: E402
from skillopt.coevolution_v5.adapters import CodingAdapter  # noqa: E402
from skillopt.coevolution_v5.experiment import text  # noqa: E402
from skillopt.coevolution_v6 import native  # noqa: E402
from skillopt.coevolution_v6.experiment import contract, portfolio_outcome  # noqa: E402
from skillopt.coevolution_v6.routing import route  # noqa: E402
from skillopt.coevolution_v6.statistics import summarize_validator  # noqa: E402
from skillopt.coevolution_v7 import analysis, experiment, research, transport  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

_require, _read, _json = prior._require, prior._read, prior._json


def _pacing(run, protocol, calls, *, require_complete=True):
    root = run / "api/pacing"
    policy = transport.PacingPolicy(**protocol["pacing_policy"])
    sealed = transport._read(root / "protocol.json")
    _require(sealed["policy"] == vars(policy) and sealed["service_hash"] == _json(run / "api/budget_protocol.json")["service_sha256"],
             "Global pacing policy/service mismatch")
    # Invoke a pure reader, not an API/pacer constructor (which would write).
    pacer = SimpleNamespace(root=root, policy=policy, protocol_hash=sealed["record_hash"])
    admissions, receipts, cooldowns = transport._Pacer._existing(pacer)
    _require(not require_complete or set(admissions) == set(receipts), "Unresolved HTTP attempt cannot be audited complete")
    backend = SimpleNamespace(_pacer=pacer)
    referenced = []
    for record in calls.values():
        transport.PacedCachedAPI._verify_cached(backend, record)
        referenced.extend(r["sequence"] for r in record["pacing"]["attempts"])
    _require(len(referenced) == len(set(referenced)) and set(referenced) <= set(admissions)
             and (not require_complete or set(referenced) == set(admissions)),
             "Actual API attempt grid differs from pacing admissions")
    ordered = [admissions[k] for k in sorted(admissions)]
    for left, right in zip(ordered, ordered[1:]):
        field = "admitted_monotonic" if left["process_epoch"] == right["process_epoch"] else "admitted_wall"
        _require(right[field] - left[field] >= policy.min_interval_seconds - 1e-6, "Global HTTP admissions violated minimum spacing")
    for cooldown in cooldowns.values():
        for admission in ordered:
            if admission["admitted_wall"] > cooldown["observed_wall"] + 1e-6:
                _require(admission["admitted_wall"] >= cooldown["cooldown_until_wall"] - 1e-6,
                         "An HTTP admission ignored an already observed global cooldown")
    return {"protocol_hash": sealed["record_hash"], "http_attempt_admissions": len(admissions),
            "completed_attempt_receipts": len(receipts), "unresolved_attempts": sorted(set(admissions) - set(receipts)),
            "cooldown_events": len(cooldowns),
            "attempt_statuses": dict(Counter(str(r["api_attempt"].get("status")) for r in receipts.values())),
            "server_arrival_or_billing_proven": False}


def _targets(run, calls, adapters):
    result = {}
    public = {digest(a.public_task()): a for a in adapters.values()}
    for key, wrapped in prior._cached(run, "targets").items():
        identity, solver = wrapped["identity"], wrapped["result"]
        adapter = public.get(identity.get("task"))
        _require(adapter is not None and identity.get("kind") == "v7_solve"
                 and identity.get("delivery_reminder") == experiment.VERSION, "Unknown frozen solver identity")
        if "record_hash" in solver:
            core.verify(solver)
        task_id = experiment.identifier(adapter)
        artifact = solver["files"] if isinstance(adapter, CodingAdapter) else solver["artifact"]
        _require(solver["id"] == task_id and solver["artifact_hash"] == digest(artifact)
                 and solver["skill_hash"] == digest(identity["skill"]) and solver["public_task_hash"] == identity["task"]
                 and solver["repeat"] == identity["history"], "Solver artifact/task/Skill/history binding mismatch")
        hashes = solver["request_hashes"]
        _require(len(hashes) == len(set(hashes)) == 2, "Every solver requires distinct generation and revision receipts")
        for index, request_hash in enumerate(hashes):
            _require(request_hash in calls, "Frozen solver lost a real API receipt")
            request = calls[request_hash]["request"]
            visible = json.loads(request["user"])
            prefix = "v5_coding_" if isinstance(adapter, CodingAdapter) else "v6_native_"
            _require(request["kind"] == prefix + ("generate" if index == 0 else "revision")
                     and request["repeat"] == identity["history"] and visible["task"] == adapter.public_task()
                     and visible["skill"] == identity["skill"] and "DELIVERY REMINDER:" in request["system"],
                     "Solver intervention or delivery request binding mismatch")
        _require(calls[hashes[0]]["request"]["system"] == calls[hashes[1]]["request"]["system"],
                 "Generation/revision format policy differs")
        first, second = (calls[h] for h in hashes)
        _require(solver["target_ok"] == second["ok"] and solver["solver_calls"] == 2,
                 "Solver delivery availability differs from the terminal API receipt")
        revision_payload = json.loads(second["request"]["user"])
        if isinstance(adapter, CodingAdapter):
            solver_identity = {"version": coding.VERSION, "key": key, "task": identity["task"],
                               "skill": solver["skill_hash"], "repeat": identity["history"]}
            expected_keys = [digest({**solver_identity, "stage": "generate"}),
                             digest({**solver_identity, "stage": "revision", "initial_request": hashes[0]})]
            def parse(task, receipt):
                if receipt["ok"] is not True:
                    return None
                try:
                    return coding.parse_delivery(task, receipt.get("response", ""))
                except (ValueError, TypeError, SyntaxError, RecursionError):
                    return None
            initial = parse(adapter.task, first)
            revision_task = replace(adapter.task, files=initial) if initial is not None else adapter.task
            kept = second["ok"] is True and second.get("response", "").strip() == "KEEP" and initial is not None
            parsed = initial if kept else parse(revision_task, second)
            _require(solver["initial_response"] == first.get("response", "")
                     and solver["response"] == solver["revision_response"] == second.get("response", "")
                     and solver["initial_evaluation"].get("files") == initial
                     and revision_payload["initial_response"] == first.get("response", "")
                     and revision_payload["current_files"] == revision_task.files,
                     "Coding artifacts/revision do not derive from the actual HTTP responses")
        else:
            solver_identity = {"version": native.VERSION, "key": key, "task_hash": identity["task"],
                               "skill_hash": solver["skill_hash"], "repeat": identity["history"]}
            expected_keys = [digest({**solver_identity, "stage": "generate", "initial_request": None}),
                             digest({**solver_identity, "stage": "revision", "initial_request": hashes[0]})]
            initial, _ = adapter._parse_response(first)
            kept = second["ok"] is True and str(second.get("response", "")).strip() == "KEEP" and initial is not None
            parsed = initial if kept else adapter._parse_response(second, previous=initial)[0]
            _require(solver["initial_artifact"] == initial == revision_payload["initial_artifact"],
                     "Native revision does not derive from actual generation response")
        _require([r["request"]["key"] for r in (first, second)] == expected_keys and artifact == parsed
                 and solver["revision_kept"] == kept and solver["format_ok"] == (parsed is not None)
                 and revision_payload["initial_artifact_valid"] == (initial is not None),
                 "Solver receipt stage identities or strict parsed final artifact changed")
        position = task_id, identity["history"], identity["phase"], solver["skill_hash"]
        _require(position not in result, "Duplicate solver intervention")
        result[position] = solver
    # Same representation uses the exact same format policy in every arm.
    systems = {}
    for solver in result.values():
        system = calls[solver["request_hashes"][0]]["request"]["system"]
        _require(systems.setdefault(solver["domain"], system) == system, "Unequal solver delivery instructions across arms")
    return result


def _packet(packet, adapter, *, solver=None, rubric=None):
    core.verify(packet)
    core.development_only(packet)
    _require(packet["task_id"] == experiment.identifier(adapter) and packet["cluster_id"] == experiment.project(adapter)
             and packet["domain"] == adapter.domain and packet["artifact_hash"] == digest(packet["artifact"]),
             "Development packet provenance mismatch")
    if rubric is not None:
        _require(packet["rubric_hash"] == rubric["rubric_hash"], "Feedback Rubric differs from frozen intervention")
    if solver is not None:
        _require(packet["artifact_hash"] == solver["artifact_hash"], "Feedback does not evaluate actual parent solver")
    for row in packet["observations"]:
        core.verify(row, "receipt_hash")
        _require(all(row[k] == packet[k] for k in ("task_id", "domain", "phase", "artifact_hash", "rubric_hash")),
                 "Packet observation binding mismatch")
        if solver is not None:
            _require(row["details"].get("solver_request_hashes") == solver["request_hashes"]
                     and row["details"].get("solver_skill_hash") == solver["skill_hash"], "Feedback solver receipt mismatch")
    research_evidence_view(packet)  # Validate identity-grounded complete view without scoring.


def _probe(search, calls, *, adapter, artifact, rubric, key, repeat):
    core.verify(search)
    identity = search["identity"]
    _require(identity["artifact_hash"] == digest(artifact) and identity["rubric_hash"] == rubric["rubric_hash"]
             and identity["key"] == key and identity["repeat"] == repeat
             and identity["task_hash"] == digest(adapter.public_task()), "Probe identity differs from frozen artifact/Rubric")
    if search.get("request_hash") is None:
        _require(search.get("error") == "delivery" and search["inputs"] == [] and search["model_calls"] == 0,
                 "Missing probe call must be an explicit invalid-artifact delivery result")
        return
    record = prior._metadata(search, calls)
    request = record["request"]
    public = adapter.public_task()
    public["files"] = artifact
    _require(request["kind"] == "v5_validator_probe" and request["key"] == digest(identity)
             and request["repeat"] == repeat and json.loads(request["user"]) == {
                 "task": public, "current_code": artifact, "rubric": rubric}, "Probe API payload/identity mismatch")
    parsed, error = [], None
    if not record["ok"]:
        error = "terminal_api_result"
    else:
        try:
            value = core.strict_object(record["response"])
            _require(set(value) == {"inputs"} and isinstance(value["inputs"], list) and 1 <= len(value["inputs"]) <= 4,
                     "Invalid probe response")
            seen = set()
            for item in value["inputs"]:
                prior._bounded_input(item)
                _require(isinstance(item, dict) and adapter._input_valid(item) is True and digest(item) not in seen,
                         "Illegal or duplicated probe input")
                seen.add(digest(item))
            parsed = value["inputs"]
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
            error = "invalid_probe_schema_or_input"
    _require(search["inputs"] == parsed and search["error"] == error and search["schema_valid"] == (error is None),
             "Executed probe inputs differ from actual model response")


def _probe_assessments(search, rows):
    for row in rows:
        core.verify(row, "receipt_hash")
        if row["check_id"] == "coding_probe" and row["verified"]:
            receipts = row["details"].get("receipts", [])
            _require([r["input"] for r in receipts] == search["inputs"] and bool(receipts),
                     "Verified differential receipts did not execute the exact model-proposed inputs")
            _require(row["status"] == ("pass" if all(r["passed"] for r in receipts) else "fail"),
                     "Probe aggregate differs from sealed input-level observations")


def _preflights(run, panel, adapters):
    """Bind private host labels to predeclared controls, without executing an oracle."""
    expected = []
    for item in panel["calibration"]:
        task = adapters[item["task"]["id"]].task
        controls = task.metadata["controls"]
        for name, files, truth in (("reference", task.reference_files, "good"),
                ("equivalent", controls["equivalent"], "good"),
                ("semantic_mutant", controls["semantic_mutant"], "bad"),
                ("preservation_mutant", controls["preservation_mutant"], "bad")):
            expected.append({"artifact_id": task.id + ":" + name, "task_id": task.id,
                "cluster_id": task.cluster_id, "artifact_hash": digest(files), "files": files, "truth": truth})
    manifest = _read(run / "calibration_manifest.json")
    _require(manifest["artifacts"] == expected, "Calibration labels/artifacts changed from the frozen task panel")
    governance._artifacts(manifest)
    preflight = _read(run / "private_preflight.json")
    _require(preflight["never_model_feedback"] is True and len(preflight["calibration"]) == len(expected),
             "Private calibration preflight grid missing")
    for record, artifact in zip(preflight["calibration"], expected):
        row = record["assessment"]
        core.verify(row, "receipt_hash")
        _require(record["artifact_id"] == artifact["artifact_id"] and row["task_id"] == artifact["task_id"]
                 and row["artifact_hash"] == artifact["artifact_hash"] and row["phase"] == "promotion"
                 and row["rubric_hash"] == core.initial_rubric()["rubric_hash"]
                 and row["check_id"] == "coding_contract" and row["evidence_kind"] == "execution"
                 and row["verified"] is True and row["status"] == ("pass" if artifact["truth"] == "good" else "fail")
                 and row["details"]["public_only"] is False, "Private oracle label/artifact binding mismatch")
    final = _read(run / "private_final_preflight.json")
    expected_ids = [i["task"]["id"] for i in panel["final"]]
    _require(final["never_model_feedback"] is True and [r["task_id"] for r in final["records"]] == expected_ids,
             "Final private reference preflight grid missing")
    for record in final["records"]:
        adapter, row = adapters[record["task_id"]], record["assessment"]
        if isinstance(adapter, CodingAdapter):
            core.verify(row, "receipt_hash")
            _require(row["check_id"] == "coding_contract" and row["task_id"] == adapter.task.id
                     and row["artifact_hash"] == digest(adapter.task.reference_files)
                     and row["verified"] is True and row["status"] == "pass" and row["phase"] == "final",
                     "Final Coding reference receipt binding mismatch")
        else:
            core.verify(row)
            _require(row["score"] == 1.0 and row["artifact_hash"] == digest(adapter.task["reference_artifact"]),
                     "Final native reference receipt binding mismatch")


def _calibration(run, protocol, calls, adapters, candidate):
    if candidate is None:
        _require(not list((run / "calibration_calls").glob("*.json")) and not (run / "calibration_rows.json").exists(),
                 "Invalid Research cannot generate a historical or fabricated calibration arm")
        return None
    manifest = _read(run / "calibration_manifest.json")
    artifacts = governance._artifacts(manifest)
    _require(manifest["blocks"] == list(range(protocol["blocks"])), "Calibration block grid changed")
    indexed = {r["artifact_id"]: r for r in artifacts}
    expected = {(r["artifact_id"], b, c) for r in artifacts for b in manifest["blocks"] for c in ("old_a", "old_b", "new")}
    jobs = _read(run / "calibration_schedule.json")["jobs"]
    _require(len(jobs) == len(expected) and {tuple(j) for j in jobs} == expected, "Calibration schedule incomplete")
    components = {}
    for key, wrapped in prior._cached(run, "calibration_calls").items():
        identity, component = wrapped["identity"], wrapped["result"]
        position = identity["artifact_id"], identity["block"], identity["channel"]
        _require(position in expected and position not in components, "Calibration component grid mismatch")
        artifact = indexed[identity["artifact_id"]]
        rubric = candidate if identity["channel"] == "new" else core.initial_rubric()
        _require(identity["artifact_hash"] == artifact["artifact_hash"] and identity["rubric_hash"] == rubric["rubric_hash"],
                 "Calibration component artifact/Rubric mismatch")
        _probe(component["search"], calls, adapter=adapters[artifact["task_id"]], artifact=artifact["files"],
               rubric=rubric, key=key, repeat=identity["block"])
        governance._promotion_assessments(component, artifact, rubric["rubric_hash"])
        _probe_assessments(component["search"], component["assessments"])
        components[position] = component
    _require(set(components) == expected, "Calibration lost an actual HTTP component")
    rows = []
    for artifact in artifacts:
        for block in manifest["blocks"]:
            for policy, channels in prior.POLICIES.items():
                parts = [components[artifact["artifact_id"], block, channel] for channel in channels]
                rows.append({k: artifact[k] for k in ("artifact_id", "artifact_hash", "task_id", "cluster_id", "truth")}
                    | {"block": block, "policy": policy, "outcome": portfolio_outcome(parts),
                       "input_count": len({digest(v) for p in parts for v in p["search"]["inputs"]}),
                       "probe_request_hashes": [p["search"]["request_hash"] for p in parts],
                       "component_hashes": [digest(p) for p in parts], "public_only": True})
    stored = _read(run / "calibration_rows.json")
    _require(stored["rows"] == rows and stored["labels_never_optimizer_feedback"] is True,
             "Calibration policy outcomes differ from sealed execution receipts")
    summary = summarize_validator(rows, expected_artifacts={r["artifact_id"]: {
        "cluster_id": r["cluster_id"], "truth": r["truth"]} for r in artifacts}, expected_blocks=manifest["blocks"])
    _require(summary == _read(run / "calibration_summary.json"), "Calibration statistics changed")
    return summary


def _proposal(run, calls, history, stage, *, parent, working, packets=None):
    stored = _read(run / "skill_proposals" / f"h{history}-{stage}.json")
    proposal = stored["proposal"]
    receipt = calls.get(proposal["request_hash"])
    _require(receipt is not None, "Skill proposal API receipt missing")
    request = receipt["request"]
    _require(request["kind"] == "v7_skill" and request["repeat"] == history
             and request["key"] == digest({"history": history, "stage": stage,
                                           "messages": [request["system"], request["user"]]}), "Skill history/stage binding mismatch")
    content = receipt.get("response", "").strip()
    valid = receipt["ok"] is True and 100 <= len(content) <= 5000 and not content.startswith("```")
    _require(proposal == {"content": content, "valid": valid, "request_hash": receipt["request_hash"]}
             and stored["parent_hash"] == digest(text(parent)), "Skill content/validity/parent mismatch")
    if packets is not None:
        system, user = experiment.optimizer_payload(parent, working, packets)
        _require(request["system"] == system and request["user"] == user
                 and stored["feedback_hashes"] == [p["record_hash"] for p in packets],
                 "Optimizer did not receive the exact shared-oldA paired feedback")
    return proposal


def _base_packets(run, calls, history, development, targets):
    proposal = _read(run / "skill_proposals" / f"h{history}-common-parent.json")["proposal"]
    payload = json.loads(calls[proposal["request_hash"]]["request"]["user"])
    views = payload["development_evidence"]
    _require([v["task_id"] for v in views] == list(development), "Common-parent Base feedback grid changed")
    packets = []
    for view in views:
        adapter = development[view["task_id"]]
        solver = targets[view["task_id"], history, "development", digest("")]
        packet = core.feedback_packet(task_id=view["task_id"], cluster_id=experiment.project(adapter), domain="coding",
            assessments=view["observations"], artifact=solver["files"], contract=adapter.task.prompt,
            task_context=adapter.public_task(), comparisons=[],
            research_context={"audit": {"preselected": True, "selection": "pre_execution_random"}})
        _packet(packet, adapter, solver=solver, rubric=core.initial_rubric())
        _require(research_evidence_view(packet, max_chars=experiment.MAX_FEEDBACK_CHARS) == view,
                 "Initial optimizer feedback is not the complete actual Base artifact evidence")
        packets.append(packet)
    return packets


def _gate(gate, before, candidate, history, round_index, tasks, targets):
    if not candidate or not candidate["valid"]:
        _require(gate == {"state": before, "decision": {"action": "Restrict", "reason": "invalid_skill_delivery"}, "pairs": []},
                 "Invalid candidate changed source Skill state")
        return
    pairs = gate["pairs"]
    _require(len(pairs) == len(tasks) and {p["task_id"] for p in pairs} == set(tasks), "Source gate omitted a frozen task")
    for pair in pairs:
        for arm in ("baseline", "current", "candidate"):
            solver = targets.get((pair["task_id"], history, "development", pair["skill_hashes"][arm]))
            _require(solver is not None, "Source gate lacks actual solver intervention")
            for row in pair[arm]:
                _require(row["artifact_hash"] == solver["artifact_hash"]
                         and row["details"].get("solver_request_hashes") == solver["request_hashes"], "Source gate solver provenance mismatch")
    state = governance.transition_skill(before, candidate, {"source": pairs, "replay": []}, [], round_index)
    _require(state == gate["state"] and gate["decision"] == state["last_transition"] and not text(state["approved"]),
             "Source gate recomputation or Approved scope differs")


def _skills(run, protocol, calls, adapters, targets, candidate, activation):
    frozen = _read(run / "skills_frozen.json")
    branches = frozen["histories"]
    _require(len(branches) == protocol["histories"] and frozen["approved_deployment_scope"] == [], "Skill histories/approval scope changed")
    development = {k: a for k, a in adapters.items() if isinstance(a, CodingAdapter) and a.task.split in {"development", "dev"}}
    probes = prior._cached(run, "feedback_probes")
    expected = {(h, t, c) for h in range(protocol["histories"]) for t in development
                for c in (("old_a", "old_b", "new") if candidate else ("old_a", "old_b"))}
    actual, packets_by_key = set(), {}
    for key, wrapper in probes.items():
        identity, result = wrapper["identity"], wrapper["result"]
        position = identity["history"], identity["task_id"], identity["channel"]
        _require(position in expected and position not in actual, "Development feedback fork grid mismatch")
        actual.add(position)
        parent = branches[identity["history"]]["parent"]
        solver = targets[position[1], position[0], "development", digest(text(parent))]
        rubric = candidate if identity["channel"] == "new" else core.initial_rubric()
        _require(identity["artifact_hash"] == solver["artifact_hash"] and identity["rubric_hash"] == rubric["rubric_hash"],
                 "Feedback fork changed shared parent artifact/Rubric")
        _probe(result["search"], calls, adapter=development[position[1]], artifact=solver["files"],
               rubric=rubric, key=key, repeat=position[0])
        _packet(result["packet"], development[position[1]], solver=solver, rubric=rubric)
        _probe_assessments(result["search"], result["packet"]["observations"])
        packets_by_key[position] = result["packet"]
    _require(actual == expected, "Feedback fork lost an expected position")
    decisions = []
    for history, branch in enumerate(branches):
        initial = _read(run / "source_initial" / f"h{history}.json")
        _require(_read(run / "source_next" / f"h{history}.json") == branch
                 and all(branch[k] == value for k, value in initial.items()), "Frozen source branch state chain changed")
        parent = _proposal(run, calls, history, "common-parent", parent="", working="",
                           packets=_base_packets(run, calls, history, development, targets))
        _require(branch["parent"] == (parent if parent["valid"] else ""), "Common parent selection changed")
        _gate(initial["initial_gate"], governance.initial_skill_state(), parent, history, 0, development, targets)
        feedback = {c: [packets_by_key[history, task, c] for task in sorted(development)]
                    for c in (("old_a", "old_b", "new") if candidate else ("old_a", "old_b"))}
        _require(branch["feedback"] == feedback, "Source branch feedback does not match actual probes")
        fixed = feedback["old_a"] + feedback["old_b"]
        shadow = feedback["old_a"] + feedback["new"] if candidate else fixed
        proposals = {"fixed": _proposal(run, calls, history, "fixed", parent=branch["parent"], working=branch["state"]["working"], packets=fixed)}
        proposals["research_shadow"] = (_proposal(run, calls, history, "research_shadow", parent=branch["parent"],
            working=branch["state"]["working"], packets=shadow) if candidate else proposals["fixed"])
        selected = {name: p if p["valid"] else branch["parent"] for name, p in proposals.items()}
        _require(branch["proposals"] == proposals and branch["candidates"] == selected
                 and branch["selected_arm"] == ("research_shadow" if activation["activate_next_round"] else "fixed")
                 and branch["shadow_is_counterfactual"] is (not activation["activate_next_round"]),
                 "Shadow branch or candidate selection masquerades as activation")
        for name, proposal in proposals.items():
            _gate(branch["gates"][name], branch["state"], proposal, history, 1, development, targets)
        decisions.append({"history": history, "initial": branch["initial_gate"]["decision"],
                          "next": {n: g["decision"] for n, g in branch["gates"].items()}})
    return branches, decisions, len(expected)


def _research(run, protocol, calls, adapters, targets, proposal):
    inputs = _read(run / "research_inputs.json")
    development = [i["task"]["id"] for i in _read(run / "panel.json")["development"]]
    parent_packets = []
    for history in range(protocol["histories"]):
        initial = _read(run / "source_initial" / f"h{history}.json")
        packets = initial["parent_feedback"]
        _require([p["task_id"] for p in packets] == development, "Parent research feedback grid changed")
        for packet in packets:
            solver = targets[packet["task_id"], history, "development", digest(text(initial["parent"]))]
            _packet(packet, adapters[packet["task_id"]], solver=solver, rubric=core.initial_rubric())
        parent_packets.extend(packets)
    _require(inputs["actual_solver_packets"] == parent_packets, "Research parent inputs changed after solver execution")
    fixtures = inputs["host_fixture_packets"]
    _require([p["task_id"] for p in fixtures] == development, "Host fixture Research grid changed")
    for packet in fixtures:
        adapter = adapters[packet["task_id"]]
        _packet(packet, adapter, rubric=core.initial_rubric())
        _require(packet["artifact"] == adapter.task.files
                 and packet["research_context"]["artifact_origin"] == "predeclared_host_bug_fixture_not_agent_generated",
                 "Host fixture has been mislabeled as an actual agent-generated artifact")
    selected = parent_packets[:len(development)] + fixtures
    selection = _read(run / "research_selection.json")
    _require(selection == {"packet_hashes": [p["record_hash"] for p in selected],
        "complete_views": [research_evidence_view(p, max_chars=110000) for p in selected],
        "no_calibration_or_final_feedback": True}, "Research selection is not the predeclared complete h0 plus fixture set")
    evidence = research.prepare_evidence(selected)
    paths = list((run / "research").rglob("proposal.json"))
    _require(len(paths) == 1 and _json(paths[0]) == proposal, "Actual frozen research proposal missing")
    directory, identity = paths[0].parent, proposal["identity"]
    _require(directory.name == digest(identity) and _json(directory / "identity.json") == identity
             and _json(directory / "evidence_view.json") == evidence
             and identity == {"version": research.VERSION, "key": "v7-grounded-fresh-development",
                 "round_index": 0, "use_research": True, "rubric_hash": core.initial_rubric()["rubric_hash"],
                 "packets_hash": digest(selected), "evidence_view_hash": evidence["record_hash"],
                 "dependencies": research._dependency_hashes(), "max_calls": research.MAX_CALLS,
                 "max_tokens_each": research.MAX_STAGE_TOKENS, "historical_fallback_available": False},
             "Research evidence/identity/dependency binding mismatch")
    trigger = research.legacy.research_trigger(selected)
    external = trigger["triggered"]
    sources = proposal["research"]["sources"]
    research.legacy._verify_sources(sources, directory)
    plan, findings, patch = None, None, None
    expected_stages = ["plan"]
    for index, stage in enumerate(proposal["stages"]):
        _require(index < len(expected_stages) and stage["stage"] == expected_stages[index],
                 "Research stage continued after a malformed response")
        name = stage["stage"]
        row = _json(directory / (name + ".json"))
        core.verify(row)
        receipt = calls[stage["request_hash"]]
        visible_sources = [] if name == "plan" else sources
        messages = research._messages(name, core.initial_rubric(), evidence, external=external,
            plan=plan, findings=findings, sources=visible_sources)
        request = receipt["request"]
        _require(row["api_receipt"] == receipt and row["record_hash"] == stage["stage_hash"]
                 and stage["receipt_hash"] == digest(receipt) and row["identity_hash"] == digest(identity)
                 and request["system"] == messages[0] and request["user"] == messages[1]
                 and request["kind"] == "v7_rubric_" + name
                 and request["key"] == f"{identity['key']}:{digest(identity)}:{name}"
                 and request["max_tokens"] == research.MAX_STAGE_TOKENS,
                 "Research stage differs from the identity-bound actual API request")
        parsed, error = None, None
        if not receipt["ok"]:
            error = "terminal_api_result"
        else:
            try:
                if name == "plan":
                    parsed = research._plan(receipt["response"], external, evidence)
                elif name == "synthesis":
                    parsed = research._findings(receipt["response"], sources, evidence)
                else:
                    parsed = research._patch(receipt["response"], core.initial_rubric(), findings)
            except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
                error = "invalid_stage_schema_or_evidence_attribution"
        _require(row["parsed"] == parsed and row["error"] == error and row["schema_valid"] == (parsed is not None),
                 "Research parsed claims differ from actual model response")
        if name == "plan":
            plan = parsed
            if plan is not None:
                expected_stages.append("synthesis")
                source_record = _read(directory / "source_receipt.json")
                _require(source_record["identity_hash"] == digest(identity) and source_record["sources"] == sources
                         and source_record["status"] == proposal["research"]["status"], "Research document provenance changed")
                _require(not sources or [s["requested_url"] for s in sources] == (plan["urls"] if external else []),
                         "Research document URLs do not match the frozen plan")
        elif name == "synthesis":
            findings = parsed
            if findings is not None and findings["findings"]:
                expected_stages.append("patch")
        else:
            patch = parsed
    _require(len(proposal["stages"]) == len(expected_stages) == proposal["calls_used"], "Research call grid incomplete")
    revision = None if patch is None else {"changes": [{k: c[k] for k in ("check_id", "search", "when", "limits")}
        for c in patch["changes"]], "rationale": patch["rationale"], "source_refs": patch["source_refs"]}
    candidate = core.apply_rubric_patch(core.initial_rubric(), revision) if revision else None
    _require(proposal["revision_evidence"] == patch and proposal["revision_patch"] == revision
             and proposal["proposed_rubric"] == candidate and proposal["research"]["plan"] == plan
             and proposal["research"]["findings"] == findings and proposal["research"]["triggers"] == trigger
             and proposal["historical_fallback_used"] is False
             and proposal["activation"] == "none_requires_independent_calibration_next_round",
             "Research proposal/patch does not follow actual grounded stages")


def _final(run, protocol, branches, adapters, targets, calls):
    panel = _read(run / "panel.json")
    final_ids = {p["task"]["id"] for p in panel["final"]}
    frozen = _read(run / "final_frozen.json")
    interventions = {(r["history"], r["task_id"]): r for r in frozen["interventions"]}
    expected = {(h, t) for h in range(protocol["histories"]) for t in final_ids}
    _require(len(frozen["interventions"]) == len(expected) and set(interventions) == expected, "Final freeze grid mismatch")
    for (history, task_id), intervention in interventions.items():
        branch = branches[history]
        selected = text(branch["candidates"][branch["selected_arm"]])
        routing = route(contract(adapters[task_id]), selected)
        skills = {"no_skill": "", "fixed_validator_candidate": text(branch["candidates"]["fixed"]),
                  "research_candidate_shadow": text(branch["candidates"]["research_shadow"]),
                  "gated_validator_candidate": selected, "gated_validator_routed": selected if routing["apply"] else ""}
        _require(intervention["skills"] == skills and intervention["routing"] == routing, "Frozen final aliases/route selection changed")
    record = _read(run / "final_rows.json")
    _require(record["final_feedback_used"] is False, "Final labels cannot re-enter learning")
    rows = record["rows"]
    for row in rows:
        intervention = interventions[row["history"], row["task_id"]]
        skill = intervention["skills"][row["policy"]]
        solver = targets[row["task_id"], row["history"], "final", digest(skill)]
        adapter = adapters[row["task_id"]]
        _require(row["cluster_id"] == experiment.project(adapter) and row["domain"] == adapter.domain
                 and row["evaluation_group"] == experiment.group(adapter)
                 and row["fallback"] == (not bool(skill)) and row["route"] == intervention["routing"]
                 and all(row[k] == solver[k] for k in ("artifact_hash", "skill_hash", "request_hashes")),
                 "Final row task/intervention/solver receipt binding mismatch")
        receipts = [calls[h] for h in solver["request_hashes"]]
        _require(row["all_solver_stages_api_ok"] == all(r["ok"] for r in receipts)
                 and row["any_solver_stage_retried"] == any(r["http_attempt_count"] > 1 for r in receipts),
                 "Final API missingness classification mismatch")
        artifact = solver["files"] if isinstance(adapter, CodingAdapter) else solver["artifact"]
        if row["score"] is not None:
            category = "correct" if row["score"] == 1 else "semantic_failure"
        elif solver["target_ok"] is False:
            category = "transport_unavailable" if transport.classify_failure(receipts[-1])["transport_failure"] else "response_unavailable"
        else:
            category = "delivery_unavailable" if artifact is None else "native_oracle_unavailable"
        _require(row["outcome_category"] == category, "Transport/delivery/native/semantic error categories differ")
    for history, task_id in expected:
        related = {r["policy"]: r for r in rows if r["history"] == history and r["task_id"] == task_id}
        for left in analysis.POLICIES:
            for right in analysis.POLICIES:
                if interventions[history, task_id]["skills"][left] == interventions[history, task_id]["skills"][right]:
                    _require(all(related[left][k] == related[right][k] for k in (
                        "score", "case_results", "error", "artifact_hash", "request_hashes", "skill_hash", "outcome_category")),
                        "A routed/gated alias was independently sampled or differently scored")
    summary = analysis.summarize(rows, expected={(t, h, p) for h, t in expected for p in analysis.POLICIES})
    _require(summary == _json(run / "final_summary.json"), "Final statistics differ from frozen rows")
    return summary, rows


def _call_coverage(run, calls, targets, proposal, candidate):
    references = [h for solver in targets.values() for h in solver["request_hashes"]]
    references += [s["request_hash"] for s in proposal["stages"]]
    references += [_read(p)["proposal"]["request_hash"] for p in (run / "skill_proposals").glob("*.json")]
    for name in ("feedback_probes", "calibration_calls"):
        references += [r["result"]["search"]["request_hash"] for r in prior._cached(run, name).values()
                       if r["result"]["search"].get("request_hash")]
    _require(set(references) == set(calls) and len(references) == len(set(references)),
             "API ledger contains an unexplained call or reused execution receipt")
    policies = {}
    if candidate:
        components = prior._cached(run, "calibration_calls").values()
        for policy, channels in prior.POLICIES.items():
            hashes = [r["result"]["search"]["request_hash"] for r in components if r["identity"]["channel"] in channels]
            receipts = [calls[h] for h in hashes]
            policies[policy] = {"logical_calls": len(hashes), "http_attempts": sum(r["http_attempt_count"] for r in receipts),
                "reported_tokens": {key: sum(r.get("usage", {}).get(key, 0) or 0 for r in receipts)
                                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
                "missing_usage_calls": sum(not r.get("usage") for r in receipts)}
    return {"all_logical_calls_explained": True, "calibration_policy_costs": policies,
            "actual_http_attempt_outcomes": dict(Counter(
                f"status={a.get('status')};ok={a.get('ok')};error_type={a.get('error_type')}"
                for r in calls.values() for a in r["attempts"])),
            "primary_policies_share_old_a_cost": True, "equal_calls_do_not_imply_equal_tokens_or_invoices": True}


def audit(run, repo=REPO, require_complete=True):
    """Require complete original results and all real cached evidence; never fill gaps."""
    run, repo = Path(run).resolve(), Path(repo).resolve()
    _require(run.is_dir() and run.is_relative_to(repo), "Existing repository run required")
    protocol, panel = (_read(run / name) for name in ("protocol.json", "panel.json"))
    _require(protocol["version"] == experiment.VERSION and protocol["panel_hash"] == digest(panel),
             "Frozen V7 source/panel protocol binding required")
    for relative, expected in protocol["source_hashes"].items():
        _require(hashlib.sha256(prior._safe(repo, relative).read_bytes()).hexdigest() == expected, "Frozen V7 source changed")
    if not (run / "results.json").exists():
        _require(not require_complete, "Completed V7 results required; incomplete snapshot needs explicit opt-in")
        calls, api = prior._receipts(run, protocol, False)
        pacing = _pacing(run, protocol, calls, require_complete=False) if (run / "api/pacing/protocol.json").exists() else {"available": False}
        return core.seal({"version": "v7-read-only-complete-audit-v1", "complete": False,
                          "verdict": "partial_snapshot_only", "protocol_hash": digest(protocol),
                          "verified_source_files": len(protocol["source_hashes"]), "api": api, "pacing": pacing,
                          "limitation": "Only available source/API/attempt receipts checked; no complete experiment claim."})
    result = _read(run / "results.json")
    _require(result["status"] == "complete" and result["protocol_hash"] == digest(protocol),
             "Complete V7 result/protocol identity mismatch")
    adapters, phase_ids = {}, {}
    for phase, items in panel.items():
        phase_ids[phase] = set()
        for item in items:
            task = item["task"]
            adapter = CodingAdapter(prior.RepoTask.from_dict(task)) if item["domain"] == "coding" else prior.NativeAdapter(task)
            _require(task["id"] not in adapters, "Duplicate frozen task identity")
            adapters[task["id"]] = adapter
            phase_ids[phase].add(task["cluster_id"])
    _require(not any(phase_ids[a] & phase_ids[b] for a in phase_ids for b in phase_ids if a < b), "Project-family leakage across phases")
    _preflights(run, panel, adapters)
    calls, api = prior._receipts(run, protocol, True)
    pacing = _pacing(run, protocol, calls)
    _require(result["ledger"] == api["ledger"] and result["returned_models"] == api["returned_models"]
             and result["pacing"] == pacing, "Result API/pacing ledger differs from actual receipts")
    targets = _targets(run, calls, adapters)
    proposal = result["research"]
    core.verify(proposal)
    candidate = proposal["proposed_rubric"]
    if candidate:
        core.validate_rubric(candidate)
    _require(_read(run / "validator_candidate_frozen.json") == {"rubric": candidate,
        "research_record_hash": proposal["record_hash"], "historical_fallback_used": False}, "Research candidate/fallback binding mismatch")
    _research(run, protocol, calls, adapters, targets, proposal)
    forbidden = [i["task"]["id"] for phase in ("calibration", "final") for i in panel[phase]]
    for value in calls.values():
        request = value["request"]
        if request["kind"] == "v7_skill" or request["kind"].startswith("v7_rubric_"):
            _require(all(t not in request["user"] for t in forbidden) and '"truth":' not in request["user"],
                     "Calibration/final task identity or labels exposed to learning")
    calibration = _calibration(run, protocol, calls, adapters, candidate)
    _require(result["calibration"] == calibration, "Final calibration summary differs")
    activation = experiment.validator_activation(calibration, candidate)
    _require(activation == result["validator_activation"] == _json(run / "validator_activation.json"),
             "Activation differs from independent gate and exact-p criterion")
    branches, decisions, fork_positions = _skills(run, protocol, calls, adapters, targets, candidate, activation)
    _require(result["source_decisions"] == decisions, "Reported source decisions differ from host evidence")
    final, rows = _final(run, protocol, branches, adapters, targets, calls)
    costs = _call_coverage(run, calls, targets, proposal, candidate)
    d, c, f = (len(panel[p]) for p in ("development", "calibration", "final"))
    upper_bound = 11 * d * protocol["histories"] + 3 * protocol["histories"] + 3 + 12 * c * protocol["blocks"] + 6 * f * protocol["histories"]
    _require(protocol["logical_call_upper_bound"] == upper_bound and len(calls) <= upper_bound <= protocol["max_calls"],
             "Real API calls exceed the predeclared complete-design budget")
    _require(result["final"] == final and result["approved_deployment_scope"] == []
             and result["final_feedback_used"] is False and result["calibration_labels_in_optimizer_feedback"] is False,
             "Result final scores or deployment/feedback declarations differ")
    return core.seal({"version": "v7-read-only-complete-audit-v1", "complete": True,
        "verdict": "original_completed_receipts_and_analysis_consistent", "protocol_hash": digest(protocol),
        "results_hash": digest(result), "verified_source_files": len(protocol["source_hashes"]),
        "api": api, "pacing": pacing, "costs": costs, "calibration_summary": calibration,
        "histories": len(branches), "feedback_fork_positions": fork_positions,
        "old_a_exactly_shared": True, "validator_activation": activation, "final_summary": final,
        "logical_final_rows": len(rows), "unique_final_trajectories": len({tuple(r["request_hashes"]) for r in rows}),
        "approved_deployment_scope": [], "limitations": [
            "Local integrity checks trust the sealed host observations; native artifacts were not re-executed.",
            "No API calls, missing-cache regeneration, score changes, output writes, or deployment activation.",
            "Client admission and wall-clock continuity do not prove provider arrival, invoices, or random missingness.",
            "Shadow candidates remain experimental counterfactuals; synthetic tasks do not establish public benchmark efficacy."]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(args.run, repo=args.repo, require_complete=not args.allow_incomplete)
    except (ValueError, KeyError, TypeError, OSError):
        print(json.dumps({"audit_valid": False, "error": "incomplete_or_inconsistent_frozen_evidence"}))
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
