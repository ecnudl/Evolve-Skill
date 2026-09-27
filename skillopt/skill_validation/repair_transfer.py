"""Frozen primary repair-feedback Skills on the consumed patch development panel.

This is a Coding-only interference/near-miss diagnostic with fresh baselines,
not independent confirmation, positive-transfer evidence, Research or deployment.
All primary proposals replay before any new solver call. Neither A confirmation
outcomes nor PatchB solver outcomes are read. No candidate is edited or selected
by downstream performance, and failed proposals retain their cold parent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts import run_mechanism_case_feedback as source_loader
from scripts import run_public_repair_feedback as proposal_driver
from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot import api as api_module
from skillopt.validator_pilot.api import CachedAPI, digest

from .mechanism_case_confirmation import _check_reserved_receipts, _ProposalReplay
from .mechanism_metrics import summarize
from .mechanism_study import _accounting, _execution_health
from .mechanism_transport import ConfiguredExecutorPool
from .models import require
from .natural_study import _read, _write
from .panel import checked_path
from .patch_diagnostic import COMPONENTS, _audit, _counts
from .patch_diagnostic import _roster as patch_roster
from .patch_tasks import deserialize_row
from .public_repair_feedback import ARMS, build_details, propose
from .public_revision import _revision_lock
from .rule_skill import RuleSkill, render_skill
from .rule_solver import solve_rule_condition
from .single_round import IMAGE, BoundedCalls, _healthy

VERSION = "frozen-repair-skill-consumed-patch-transfer-v1"
CONDITIONS = ("no_skill", "current", *ARMS)
PATCH_EXECUTION_MODULES = ("patch_tasks.py", "curriculum_tasks.py", "public_revision.py", "rule_solver.py", "sandbox.py")


def _implementation_hashes():
    # Editable installs must not silently supply live scripts to a frozen run.
    code_root = Path(__file__).resolve().parents[2]
    files = {"source_loader": Path(source_loader.__file__).resolve(),
             "proposal_driver": Path(proposal_driver.__file__).resolve(),
             "api": Path(api_module.__file__).resolve()}
    require(all(path.is_relative_to(code_root) for path in files.values()),
            "Frozen code snapshot must include both source/proposal scripts and API implementation")
    return {**{name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
            "skill_validation": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(Path(__file__).parent.glob("*.py"))}}


def load_primary(source, proposals):
    """Replay source-bound F repeat zero, never choose a stability repeat."""
    public_rows, histories, source_index = source_loader.load_source(source)
    config, api_protocol = _read(proposals / "protocol.json"), _read(proposals / "api_protocol.json")
    preflight, summary = _read(proposals / "preflight.json"), _read(proposals / "summary.json")
    for name, path in (("script_hash", Path(proposal_driver.__file__)),
                       ("source_loader_hash", Path(source_loader.__file__)), ("api_source_hash", Path(api_module.__file__))):
        require(config.get(name) == hashlib.sha256(path.read_bytes()).hexdigest(),
                "Retain original F proposal/import/API implementation: " + name)
    require(config.get("source_hashes", {}).get("public_repair_feedback.py")
            == hashlib.sha256(Path(propose.__code__.co_filename).read_bytes()).hexdigest(),
            "Retain original F repair-feedback projection/parser implementation")
    require(config.get("version") == proposal_driver.VERSION and config.get("source") == source_index
            and config.get("arms") == list(ARMS) and config.get("primary_repeat") == 0
            and config.get("other_repeats") == "proposal_stability_only_no_best_of_n"
            and config.get("selection_before_any_proposal") is True
            and config.get("max_tokens") == 2048 and config.get("hidden_audit_used") is False,
            "F source, primary selection or bounded proposal protocol changed")
    repeats = config.get("repeats")
    require(type(repeats) is int and 1 <= repeats <= 2, "Unsupported proposal repetition budget")
    expected_service = {**source_index["source_service"], "initial_health_policy": "completed_response_v1"}
    require(api_protocol.get("configuration_hash") == config["record_hash"]
            and api_protocol.get("preflight_hash") == preflight["record_hash"]
            and preflight.get("protocol_hash") == config["record_hash"] and preflight.get("status") == "preflight_complete"
            and api_protocol.get("service") == config.get("expected_proposal_service") == expected_service
            and summary.get("protocol_hash") == api_protocol["record_hash"]
            and summary.get("status") == "completed_proposal_diagnostic"
            and summary.get("primary_repeat") == 0 and summary.get("best_of_n_selection") is False,
            "Unbound or incomplete F proposal execution")
    bindings = {h: {"parent_hash": p.content_hash, "feedback_hash": b["record_hash"]} for h, (p, b) in histories.items()}
    require(config.get("parents_and_feedback") == bindings, "F parents or original development feedback changed")
    expected_jobs = [[h, arm, repeat] for h in histories for repeat in range(repeats)
                     for arm in (ARMS if (int(h[1:]) + repeat) % 2 == 0 else tuple(reversed(ARMS)))]
    require(_read(proposals / "jobs.json") == seal({"jobs": expected_jobs, "primary_repeat": 0}),
            "F proposal roster or selection changed")
    index = {(r["history"], r["arm"], r["repeat"]): r for r in summary["rows"]}
    require(len(index) == len(summary["rows"]) and set(index) == {tuple(job) for job in expected_jobs},
            "F proposal summary is incomplete or duplicated")
    skills, records, statuses, changed, all_proposals = {}, {}, {}, {}, {}
    for history, (parent, bundle) in histories.items():
        require(not parent.rules, "Transfer baselines require an actually empty source parent")
        base = proposals / "histories" / history
        require(_read(base / "source_parent.json")["skill"] == parent.to_dict()
                and _read(base / "source_feedback.json") == bundle, "F imported parent/feedback differs from source")
        details = _read(base / "details.json")
        original_sources = proposal_driver.load_sources(source, history, public_rows, bundle)
        require(details == build_details(parent, bundle, original_sources, detail_limit=config["detail_limit_pairs"]),
                "F repair evidence differs from original public development receipts")
        skills[history], records[history], statuses[history], changed[history] = {"no_skill": parent, "current": parent}, {}, {}, {}
        all_proposals[history] = {}
        for arm in ARMS:
            all_proposals[history][arm] = []
            for repeat in range(repeats):
                proposal = _read(base / "updates" / f"{arm}-{repeat}.json")
                replay = _ProposalReplay(proposals, api_protocol, proposal["api_receipt"])
                rebuilt = propose(replay, parent, bundle, details, arm=arm, repeat=int(history[1:]) * repeats + repeat)
                expected_row = {"history": history, "arm": arm, "repeat": repeat, "status": proposal["status"],
                    "record_hash": proposal["record_hash"], "api_request_hash": proposal["api_receipt"]["request_hash"],
                    "candidate": None if proposal["update"] is None else proposal["update"].get("candidate")}
                require(proposal == rebuilt and index[(history, arm, repeat)] == expected_row,
                        "Proposal is not the original source-bound response")
                all_proposals[history][arm].append(proposal["record_hash"])
                if repeat == 0:
                    record = proposal
            skill = RuleSkill.from_dict(record["update"]["candidate"]) if record["status"] == "candidate" else parent
            skills[history][arm], records[history][arm] = skill, record
            statuses[history][arm], changed[history][arm] = record["status"], render_skill(skill) != render_skill(parent)
    return {"skills": skills, "records": records, "statuses": statuses, "changed": changed,
        "all_proposal_record_hashes": all_proposals,
        "source": source_index, "configuration_hash": config["record_hash"], "proposal_protocol_hash": api_protocol["record_hash"],
        "proposal_summary_hash": summary["record_hash"], "service": expected_service}


def load_patch(source):
    """Read only PatchB registration/qualification, never solver outcomes."""
    protocol, panel = _read(source / "protocol.json"), _read(source / "host_only/panel.json")
    frozen, qualification = _read(source / "frozen_panel.json"), _read(source / "qualification_summary.json")
    manifest = verify(panel["manifest"])
    require(protocol.get("development_only") is True and protocol.get("condition") == "no_skill"
            and frozen.get("protocol_hash") == protocol["record_hash"]
            and frozen.get("manifest_hash") == protocol.get("manifest_hash") == manifest["record_hash"]
            and frozen.get("qualification_hash") == qualification["record_hash"]
            and frozen.get("before_any_solver") is True
            and qualification.get("panel_hash") == manifest["record_hash"]
            and qualification.get("status") == "qualified" and qualification.get("formal_eligible") is True,
            "Patch source is not a fully bound qualified development panel")
    for name in PATCH_EXECUTION_MODULES:
        require(protocol.get("source_hashes", {}).get(name)
                == hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest(),
                "Retain the original frozen patch execution/solver adapter: " + name)
    require([digest(row) for row in panel["development"]] == manifest["row_hashes"], "Patch rows changed after registration")
    rows = [deserialize_row(row) for row in panel["development"]]
    patch_roster(rows, 2)
    return {"rows": rows, "protocol": protocol, "manifest_hash": manifest["record_hash"],
            "qualification_hash": qualification["record_hash"], "frozen_panel_hash": frozen["record_hash"]}


def _roster(skills, rows, repeats):
    return [{"history": h, "task_id": row["task"].contract.task_id, "family_id": row["family_id"],
        "domain": "coding", "region": "near_miss" if row["family_id"] == "curated-patch-interval_policy" else "unrelated",
        "patch_role": row["region"], "repeat": repeat, "condition": condition, "exposure": "raw"}
        for h in skills for row in rows for repeat in range(repeats) for condition in CONDITIONS]


def component_summary(results, roster, stage):
    require(stage in {"initial", "final"}, "Unknown audit stage")
    fields = ("history", "task_id", "repeat", "condition")
    expected = {tuple(p[k] for k in fields): p for p in roster}
    require(len(expected) == len(roster), "Duplicate component roster position")
    observed = {}
    for record in results:
        row = verify(record[stage])
        key = tuple(row[k] for k in fields)
        require(key in expected and key not in observed and all(row.get(k) == v for k, v in expected[key].items()),
                "Component result differs from registered position")
        values = row["audit_components"]
        require(set(values) == set(COMPONENTS) and all(v in {"pass", "fail", "unknown", "not_applicable"} for v in values.values()),
                "Explicit component statuses required")
        observed[key] = values
    grid = [{**position, "audit_components": observed.get(key, {name:
        "not_applicable" if name == "replaced_status" and position["patch_role"] == "preserve" else "unknown"
        for name in COMPONENTS})} for key, position in expected.items()]

    def group(rows):
        return {"positions": len(rows), "tasks": len({r["task_id"] for r in rows}),
            "declared_source_families": len({r["family_id"] for r in rows}),
            "components": {name: _counts([r["audit_components"][name] for r in rows], applicable=True) for name in COMPONENTS}}

    arms = {}
    for condition in CONDITIONS:
        rows = [r for r in grid if r["condition"] == condition]
        arms[condition] = {"overall": group(rows)}
        for field in ("region", "history", "patch_role"):
            arms[condition]["by_" + field] = {value: group([r for r in rows if r[field] == value])
                                             for value in sorted({r[field] for r in rows})}
    return seal({"stage": stage, "arms": arms, "missing_positions": len(roster) - len(observed),
        "roster_hash": digest(roster), "aggregation_unit": "registered_position_not_independent_sample",
        "family_independence_proven": False, "deployment_authorized": False})


def run(repo, source, proposals, patch_source, output, executor, *, workers=4, repeats=2, proxy=None, stop_after_prepare=False):
    require(type(workers) is int and 1 <= workers <= 4, "Transfer workers must be 1..4")
    require(type(repeats) is int and 1 <= repeats <= 3, "Transfer repetitions must be 1..3")
    require(type(stop_after_prepare) is bool, "Explicit prepare-only flag required")
    repo, source, proposals, patch_source, root = (checked_path(Path(p)).resolve()
                                                 for p in (repo, source, proposals, patch_source, output))
    require(all(root != p and root not in p.parents and p not in root.parents for p in (source, proposals, patch_source)),
            "Use a new transfer output outside all source experiments")
    with _revision_lock(root / "transfer_lock"):
        implementations = _implementation_hashes()
        imported, patch = load_primary(source, proposals), load_patch(patch_source)
        require(executor.identity == patch["protocol"]["executor"], "Patch qualification belongs to another executor")
        require(imported["service"] == patch["protocol"]["service"], "Frozen proposal/patch model services differ")
        roster = _roster(imported["skills"], patch["rows"], repeats)
        summarize([], roster, bootstrap_samples=100, candidate_conditions=ARMS)
        limit = 2 * len(patch["rows"]) * repeats * len(CONDITIONS)
        protocol = seal({"version": VERSION, "implementations": implementations, "service": imported["service"],
            "source": imported["source"], "proposal_configuration_hash": imported["configuration_hash"],
            "proposal_protocol_hash": imported["proposal_protocol_hash"], "proposal_summary_hash": imported["proposal_summary_hash"],
            "patch_protocol_hash": patch["protocol"]["record_hash"], "patch_manifest_hash": patch["manifest_hash"],
            "patch_qualification_hash": patch["qualification_hash"], "executor": executor.identity,
            "transport": getattr(executor, "transport_identity", {}), "workers": workers, "repeats": repeats,
            "histories": len(imported["skills"]), "conditions": list(CONDITIONS), "exposures": ["raw"],
            "solver_token_cap": 2048, "request_limit_per_history": limit, "roster_hash": digest(roster),
            "primary_proposal_repeat": 0, "regions_are_analysis_only_not_routing": True,
            "near_miss": "Task-level label: both interval_policy roles require new adjacency merging; preserve also tests old-rule false/omitted cases. Neither is a positive-transfer target.",
            "unrelated": "Other 22 tasks/11 declared source families; unrelated to the observed interval-repair rule.",
            "fresh_baselines": True, "source_solver_cache_reused": False, "raw_content_only": True,
            "consumed_development_exploration": True, "independent_confirmation": False,
            "positive_transfer_evaluated": False, "research": False, "deployment_authorized": False})
        _write(root / "protocol.json", protocol)
        _write(root / "expected_positions.json", seal({"positions": roster}))
        frozen = seal({"protocol_hash": protocol["record_hash"], "before_any_new_solver": True,
            "patch_manifest_hash": patch["manifest_hash"], "proposal_records": imported["records"],
            "all_proposal_record_hashes": imported["all_proposal_record_hashes"],
            "skills": {h: {c: s.to_dict() for c, s in values.items()} for h, values in imported["skills"].items()},
            "statuses": imported["statuses"], "behavior_changed": imported["changed"],
            "primary_repeat": 0, "noncandidate_retains_parent": True, "deployment_authorized": False})
        _write(root / "frozen_inputs.json", frozen)
        _check_reserved_receipts(root, protocol)
        common = {"version": VERSION, "protocol_hash": protocol["record_hash"], "freeze_hash": frozen["record_hash"],
            "statuses": imported["statuses"], "behavior_changed": imported["changed"],
            "provenance": "engineering_fixture" if imported["service"].get("fixture") is True else "real_model_consumed_synthetic_development",
            "consumed_development_exploration": True, "independent_confirmation": False,
            "positive_transfer_evaluated": False, "research_increment_evaluated": False, "deployment_authorized": False}
        if (root / "summary.json").exists():
            result = _read(root / "summary.json")
            require(result["protocol_hash"] == protocol["record_hash"] and result["freeze_hash"] == frozen["record_hash"],
                    "Transfer summary binding changed")
            return result
        if stop_after_prepare:
            return seal({**common, "status": "prepared_shadow_transfer", "expected_positions": len(roster),
                "new_model_calls": 0, "accounting": {"new_http_attempts": 0}, "method_effect_evaluated": False})
        if not any(v for history in imported["changed"].values() for v in history.values()):
            result = seal({**common, "status": "no_changed_primary_candidates", "metrics": None,
                "accounting": {"http_attempts": 0, "terminal_logical_requests": 0}, "method_effect_evaluated": False})
            _write(root / "summary.json", result)
            return result
        with CachedAPI(repo, root / "api", workers=workers, provider="bigmodel", stream=True,
                       reasoning_effort="low", proxy=proxy, initial_health_policy="completed_response_v1") as api:
            require(api.service == protocol["service"], "Transfer solver service differs from frozen sources")
            calls = {h: BoundedCalls(api, root / "histories" / h / "budget", digest([protocol["record_hash"], h]), limit)
                     for h in imported["skills"]}
            files = {"ping.py": "def ping():\n    return True\n"}
            ping = verify(executor.run(files, "ping", "ping", [], {}))
            _healthy(ping)
            require(ping.get("status") == "observed" and ping.get("actual") is True
                    and ping.get("input_hash") == digest({"files": files, "module": "ping", "function": "ping", "args": [], "kwargs": {}}),
                    "Transfer safe executor unavailable before paid solver calls")
            lookup = {row["task"].contract.task_id: row for row in patch["rows"]}

            def one(position):
                row, skill = lookup[position["task_id"]], imported["skills"][position["history"]][position["condition"]]
                base = root / "positions" / digest(position)
                public = {key: row[key] for key in ("task", "public_task", "public_wrapper")}
                condition = position["condition"] if position["condition"] in {"no_skill", "current"} else "candidate"
                solved = solve_rule_condition(public, skill, condition, position["repeat"], calls[position["history"]],
                                              executor, base, exposure="raw")
                _execution_health(solved)
                phases = {}
                for stage, artifact in (("initial", solved["initial_artifact"]), ("final", solved["artifact"])):
                    audit = _audit(row, artifact, executor, base)
                    revision = solved["revision"]["record"]
                    public_status = (revision["public_status"] if stage == "final" else
                                     revision["draft_stage"]["report"]["status"] if revision["draft_stage"] else "unknown")
                    phases[stage] = seal({**position, "status": audit["status"], "stage": stage,
                        "public_status": public_status, "revision_status": revision["status"],
                        "skill_applied": bool(solved["exposure"]["rendering"]["selected_rule_ids"]),
                        "rule_skill_hash": skill.content_hash, "artifact_hash": artifact.content_hash,
                        "audit_hash": audit["record_hash"], "audit_components": {name: audit[name] for name in
                            ("target_status", "retained_status", "replaced_status", "state_status")},
                        "request_hash": solved["initial_artifact"].source_ref.split(":", 1)[-1],
                        "receipt_hash": artifact.source_hash, "trajectory_hash": digest([solved["initial_artifact"].source_hash, artifact.source_hash]),
                        "revision_hash": solved["revision"]["record"]["record_hash"], "hidden_feedback_used": False,
                        "deployment_authorized": False})
                result = seal({"position": position, **phases})
                _write(base / "result.json", result)
                return result

            results = api.parallel(roster, one, "frozen public-repair skill interference on consumed patch development")
            _write(root / "transfer_rows.json", seal({"rows": results}))
            result = seal({**common, "status": "completed_shadow_transfer_diagnostic",
                "metrics": {stage: summarize([r[stage] for r in results], roster, candidate_conditions=ARMS)
                            for stage in ("initial", "final")}, "accounting": _accounting(api, calls),
                "component_metrics": {stage: component_summary(results, roster, stage) for stage in ("initial", "final")},
                "public_check_metrics": {stage: {condition: _counts([r[stage]["public_status"] for r in results
                    if r["position"]["condition"] == condition]) for condition in CONDITIONS} for stage in ("initial", "final")},
                "revision_outcomes": dict(Counter(r["final"]["revision_status"] for r in results)),
                "expected_positions": len(roster), "observed_positions": len(results),
                "limitations": ["Same consumed synthetic Coding development tasks, not independent confirmation or cross-domain transfer.",
                    "Both interval-policy tasks are Near-Miss; this panel cannot establish positive-transfer gain.",
                    "Fresh No-Skill and cold Current share equal-prompt receipts; empty histories are aliases, not learning.",
                    "Only fixed primary proposals are tested; invalid proposals retain parent with no replacement.",
                    "Host analysis labels never choose rules; all conditions use raw Skill content and one public repair.",
                    "Initial/final audits happen after final selection and never update Skill or authorize deployment."]})
            _write(root / "summary.json", result)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    for name in ("source", "proposals", "patch-source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    parser.add_argument("--host", default="PJ-CL4MIND-DULIN")
    parser.add_argument("--remote-python", default="/root/miniconda3/envs/skill_validation/bin/python")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--ssh-config", type=Path)
    parser.add_argument("--proxy")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args(argv)
    executor = ConfiguredExecutorPool(args.remote_repo, workers=args.workers, host=args.host,
        remote_python=args.remote_python, image=args.image, ssh_config=args.ssh_config)
    try:
        result = run(args.repo, args.source, args.proposals, args.patch_source, args.output, executor,
                     workers=args.workers, repeats=args.repeats, proxy=args.proxy, stop_after_prepare=args.prepare)
        print(json.dumps({"status": result["status"], "accounting": result["accounting"]}), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
