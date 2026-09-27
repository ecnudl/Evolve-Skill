"""Posthoc development diagnosis: full public feedback and one public repair.

This is deliberately NOT a new benchmark score or admission gate. The source
development outcomes have already been inspected. Frozen candidate texts are
replayed, and optional new proposals consume only public development evidence.
No confirmation/final task, hidden answer, or audit result enters a model prompt.
Historical outputs and the frozen historical driver remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from skillopt.coevolution_v5.core import seal
from skillopt.validator_pilot.api import CachedAPI, digest

from .checks import ExecutionCache, pipeline_hash, validate_callable
from .models import ArtifactRecord, require
from .natural_data import build_audit_files, load_tasks
from .natural_study import ExecutorPool, _read, _write, audit
from .panel import checked_path
from .research import fixed_rubric
from .single_round import BoundedCalls, _healthy
from .single_round_feedback import parse_update

VERSION = "posthoc-development-feedback-and-public-repair-v1"
PREFERRED_ARMS = ("no_skill", "current", "contract_only_u0", "contract_only_u1", "fixed_u0", "fixed_u1")
# Host-only annotations from the completed qualitative review. They do not
# change scores, remove tasks, generate answers, or reach a solver/updater.
CONTRACT_FLAGS = {
    "HumanEval/76": "Zero-exponent/zero-base convention deserves explicit review.",
    "HumanEval/116": "Published negative-number example conflicts with the frozen reference.",
    "HumanEval/151": "Whether bool counts as an integer is not explicit in the prose contract.",
}


def unique_skills(skills):
    """Deduplicate actual texts, not named arms or allegedly independent runs."""
    require(type(skills) is dict and skills.get("no_skill") == "" and "current" in skills,
            "An explicit empty baseline and parent are required")
    result, aliases, by_hash = {}, {}, {}
    for arm in sorted(skills, key=lambda a: (PREFERRED_ARMS.index(a) if a in PREFERRED_ARMS else 99, a)):
        value = skills[arm]
        require(type(value) is str and len(value.encode()) <= 6000, "Bounded frozen Skill text required")
        key = hashlib.sha256(value.encode()).hexdigest()
        canonical = by_hash.setdefault(key, arm)
        result.setdefault(canonical, value)
        aliases[arm] = canonical
    return result, aliases


def regression_tasks(rows):
    """Select an explicitly posthoc diagnostic set, using DEVELOPMENT H only."""
    pairs = defaultdict(dict)
    for row in rows:
        require(row["partition"] == "development", "Diagnostic selection must not access held-out rows")
        require(row["condition"] in {"no_skill", "current"}, "Source development must be two-condition")
        key = row["task_id"], row["repeat"]
        require(row["condition"] not in pairs[key], "Duplicate source position")
        pairs[key][row["condition"]] = row
    losses = []
    for (task_id, repeat), pair in sorted(pairs.items()):
        require(set(pair) == {"no_skill", "current"}, "Incomplete source pair")
        if pair["no_skill"]["status"] == "pass" and pair["current"]["status"] == "fail":
            losses.append({"task_id": task_id, "repeat": repeat})
    return sorted({r["task_id"] for r in losses}), losses


def load_development(repo, source):
    """Read/replay every source development position; never read final files.

    Loading audits here authenticates the *host-side* diagnostic selection.
    Feedback entries contain only typed public tasks/artifacts/replayed V.
    """
    repo, source = checked_path(repo), checked_path(source)
    manifest, protocol = _read(source / "data_manifest.json"), _read(source / "protocol.json")
    parent, freeze = _read(source / "parent_skill.json"), _read(source / "frozen_candidates.json")
    require(protocol["manifest_hash"] == manifest["record_hash"]
            and protocol["parent_hash"] == parent["record_hash"]
            and freeze["protocol_hash"] == protocol["record_hash"]
            and freeze["all_frozen_before_confirmation_and_final"] is True
            and freeze["skills"]["current"] == parent["text"], "Changed source lineage")
    task_rows = load_tasks(repo, manifest, "development")
    tasks = {r["task"].contract.original_task_id: r for r in task_rows}
    require(bool(tasks) and len(tasks) == len(task_rows), "Distinct nonempty development tasks required")
    rows = _read(source / "host_only/development_rows.json")["rows"]
    expected = {(t, r, c) for t in tasks for r in range(protocol["repeats"])
                for c in ("no_skill", "current")}
    actual = {(r["task_id"], r["repeat"], r["condition"]) for r in rows}
    require(actual == expected and len(rows) == len(expected), "Incomplete/duplicate development panel")
    executor = SimpleNamespace(identity=protocol["executor"])
    records, groups, audits, cache_identity = {}, defaultdict(dict), {}, None

    def bound_audit(row, artifact, reference=False):
        code = next((f.content for f in artifact.files if f.path == "solution.py"), None)
        files = build_audit_files(row, code, reference=reference) if reference or code is not None else {}
        request = {"task_hash": row["task"].content_hash,
                   "artifact_hash": None if reference else artifact.content_hash,
                   "files_hash": digest(files), "executor": protocol["executor"], "reference": reference}
        key = digest(request)
        if key not in audits:
            result = _read(source / "host_only/audits" / (key + ".json"))
            require(result["request"] == request, "Changed source audit")
            audits[key] = result
        return audits[key]

    for record in rows:
        row = tasks[record["task_id"]]
        require(record["partition"] == "development" and record["arm"] == record["condition"]
                and record["family_id"] == row["task"].contract.family_id, "Source task/condition mismatch")
        raw = _read(source / "artifacts" / (record["artifact_hash"] + ".json"))
        artifact = ArtifactRecord.from_dict({k: v for k, v in raw.items() if k != "record_hash"})
        text = freeze["skills"][record["condition"]]
        require(artifact.content_hash == record["artifact_hash"]
                and artifact.task_hash == row["task"].contract.content_hash
                and artifact.repeat == record["repeat"] and artifact.condition == record["condition"]
                and artifact.skill_hash == hashlib.sha256(text.encode()).hexdigest()
                and artifact.source_ref == record["request_ref"] and artifact.provenance_complete
                and artifact.provenance_kind == "model" and not artifact.historical_only,
                "Source artifact identity/provenance mismatch")
        request_hash = artifact.source_ref.split(":", 1)[1]
        receipt_path = next((source / p / (request_hash + ".json") for p in
            ("api/calls", "reused_solver_receipts/receipts") if (source / p / (request_hash + ".json")).is_file()), None)
        require(receipt_path is not None, "Missing original model receipt")
        receipt = json.loads(checked_path(receipt_path).read_text())
        require(digest(receipt) == artifact.source_hash and receipt["request_hash"] == request_hash,
                "Changed source model receipt")
        cache = ExecutionCache(executor, source / "public_execution" / artifact.content_hash,
                               max_executions=192, read_only=True)
        report = validate_callable(row["public_task"], artifact, fixed_rubric(), cache)
        require(not cache.missing_records and report == _read(source / "public_reports" / (report["record_hash"] + ".json"))
                and report["status"] == record["public_status"], "Source public receipt mismatch")
        audited, reference = bound_audit(row, artifact), bound_audit(row, artifact, True)
        require(audited["record_hash"] == record["audit_hash"]
                and reference["record_hash"] == record["reference_hash"]
                and record["status"] == (audited["status"] if reference["status"] == "pass" else "unknown"),
                "Source audit labels do not match receipts")
        cache_identity = cache.identity if cache_identity is None else cache_identity
        require(cache.identity == cache_identity, "Mixed source execution policies")
        records.update(cache.records)
        groups[(record["task_id"], artifact.repeat)][artifact.condition] = (artifact, report)
    entries = [{"task": tasks[t]["public_task"],
                "artifacts": tuple(pair[c][0] for c in ("no_skill", "current")),
                "reports": tuple(pair[c][1] for c in ("no_skill", "current"))}
               for (t, _), pair in sorted(groups.items())]
    return {"manifest": manifest, "protocol": protocol, "parent": parent, "freeze": freeze,
            "tasks": tasks, "rows": rows, "entries": entries,
            "feedback_options": {"parent_skill": parent["text"], "rubric": fixed_rubric(),
                "pipeline_hash": pipeline_hash(fixed_rubric(), cache), "execution_identity": cache_identity,
                "execution_records": tuple(records.values())}}


def prepare(repo, source, output, *, repeats=2, detail_limit=12, include_updates=True, task_ids=None):
    from .development_feedback import build_development_feedback, messages
    source, output = checked_path(source), checked_path(output)
    require(output != source and not output.is_relative_to(source) and not source.is_relative_to(output),
            "Use a separate, non-overlapping output directory")
    require(type(repeats) is int and 1 <= repeats <= 20, "Freeze a repeat budget from 1 to 20")
    require(type(include_updates) is bool, "Explicit update choice required")
    data = load_development(repo, source)
    selected, losses = regression_tasks(data["rows"])
    if task_ids is not None:
        require(type(task_ids) is list and task_ids and len(set(task_ids)) == len(task_ids)
                and set(task_ids) <= set(data["tasks"]), "Requested tasks must be distinct source development tasks")
        selected = sorted(task_ids)
    require(bool(selected), "No diagnostic tasks selected")
    coverage = build_development_feedback(data["entries"], detail_limit=detail_limit, **data["feedback_options"])
    prompt_records = {}
    for mode in ("contract_only", "evidence"):
        system, user, prompt_hash = messages(data["parent"]["text"], coverage, mode)
        require(len((system + user).encode()) <= 120000, "Feedback exceeds the frozen API prompt budget")
        prompt_records[mode] = seal({"system": system, "user": user, "prompt_hash": prompt_hash})
    skills, aliases = unique_skills(data["freeze"]["skills"])
    prepared = seal({"version": VERSION, "source": str(source),
        "source_manifest_hash": data["manifest"]["record_hash"],
        "source_protocol_hash": data["protocol"]["record_hash"],
        "source_freeze_hash": data["freeze"]["record_hash"],
        "coverage_hash": coverage["record_hash"],
        "prompt_hashes": {m: p["record_hash"] for m, p in prompt_records.items()},
        "selected_task_ids": selected, "source_regression_positions": losses,
        "selection": "posthoc DEVELOPMENT diagnostic, not representative or independent generalization",
        "partition": "development", "repeats": repeats, "detail_limit": detail_limit,
        "include_updates": include_updates, "skills": skills, "aliases": aliases,
        "contract_review_flags": {t: CONTRACT_FLAGS[t] for t in selected if t in CONTRACT_FLAGS},
        "old_scores_unchanged": True, "final_access": False, "deployment_authorized": False})
    _write(output / "coverage.json", coverage)
    for mode, value in prompt_records.items():
        _write(output / "update_prompts" / (mode + ".json"), value)
    _write(output / "prepared.json", prepared)
    return prepared, data


def direction(before, after):
    require(before in {"pass", "fail", "unknown"} and after in {"pass", "fail", "unknown"}, "Invalid status")
    return "unknown" if "unknown" in (before, after) else "tie" if before == after else "win" if after == "pass" else "loss"


def summarize_rows(rows):
    grouped = defaultdict(list)
    for row in rows:
        require(row["partition"] == "development", "No held-out outcomes in development diagnostic")
        grouped[row["arm"]].append(row)
    baseline = {(r["task_id"], r["repeat"]): r for r in grouped.get("no_skill", [])}
    result = {}
    for arm, items in sorted(grouped.items()):
        require(len({(r["task_id"], r["repeat"]) for r in items}) == len(items), "Duplicate diagnostic position")
        require({(r["task_id"], r["repeat"]) for r in items} == set(baseline), "Incomplete paired diagnostic")
        result[arm] = {
            "positions": len(items), "independent_tasks": len({r["task_id"] for r in items}),
            "draft": dict(Counter(r["draft_status"] for r in items)),
            "after_public_revision": dict(Counter(r["revised_status"] for r in items)),
            "revision_effect": dict(Counter(direction(r["draft_status"], r["revised_status"]) for r in items)),
            "revision_actions": dict(Counter(r["revision_status"] for r in items)),
            "completed_revision_opportunities": sum(r.get("revision_opportunity_completed", False) for r in items),
            "draft_vs_no_skill": dict(Counter(direction(baseline[(r["task_id"], r["repeat"])]["draft_status"],
                                                               r["draft_status"]) for r in items)),
            "revised_vs_no_skill": dict(Counter(direction(baseline[(r["task_id"], r["repeat"])]["revised_status"],
                                                                 r["revised_status"]) for r in items)),
            "contract_flagged_positions": sum(r["contract_review_required"] for r in items),
        }
    return result


def run(repo, source, output, executor, *, workers=4, repeats=2, detail_limit=12,
        include_updates=True, task_ids=None, provider="bigmodel", api_proxy=None, reasoning_effort="low"):
    from .public_revision import revise_public, solve_public_initial
    output = checked_path(output)
    prepared, data = prepare(repo, source, output, repeats=repeats, detail_limit=detail_limit,
                             include_updates=include_updates, task_ids=task_ids)
    preflight = executor.run({"ping.py": "def ping():\n    return True\n"}, "ping", "ping", [], {})
    _healthy(preflight)
    require(preflight.get("actual") is True and preflight.get("status") == "observed", "Sandbox preflight failed")
    with CachedAPI(checked_path(repo), output / "api", workers=workers, provider=provider, stream=True,
                   reasoning_effort=reasoning_effort, proxy=api_proxy) as api:
        n_conditions = len(prepared["skills"]) + (2 if include_updates else 0)
        limit = 2 * len(prepared["selected_task_ids"]) * repeats * n_conditions + (2 if include_updates else 0)
        protocol = seal({"version": VERSION, "prepared_hash": prepared["record_hash"],
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")},
            "service": api.service, "executor": executor.identity, "transport": executor.transport_identity,
            "workers": workers, "request_limit": limit, "max_output_tokens": 2048,
            "same_public_revision_policy_all_conditions": True,
            "reference_audit_after_freeze_never_model_feedback": True,
            "not_official_evalplus_evaluator": True, "posthoc_only": True, "final_access": False,
            "research_effect_claim": False, "deployment_authorized": False})
        _write(output / "protocol.json", protocol)
        calls = BoundedCalls(api, output / "model_budget", protocol["record_hash"], limit)
        skills, updates = dict(prepared["skills"]), {}
        if include_updates:
            for mode in ("contract_only", "evidence"):
                prompt = _read(output / "update_prompts" / (mode + ".json"))
                receipt = calls.call(prompt["system"], prompt["user"], "development-coverage-update", repeat=0)
                update = parse_update(receipt.get("response") if receipt.get("ok") else None, data["parent"]["text"])
                arm = "coverage_" + mode + "_u0"
                skills[arm] = update["candidate_skill"] if update["status"] == "candidate" else data["parent"]["text"]
                updates[arm] = {"update": update, "request_hash": receipt["request_hash"],
                                "api_ok": receipt.get("ok") is True}
        skills, aliases = unique_skills(skills)
        freeze = seal({"protocol_hash": protocol["record_hash"], "skills": skills, "aliases": aliases,
                       "updates": updates, "all_frozen_before_new_solver_calls": True})
        _write(output / "frozen_candidates.json", freeze)
        references = {t: audit(data["tasks"][t], None, executor, output, reference=True)
                      for t in prepared["selected_task_ids"]}

        def position(job):
            task_id, repeat, arm = job
            row, skill = data["tasks"][task_id], skills[arm]
            condition = "no_skill" if arm == "no_skill" else "current" if arm == "current" else "candidate"
            root = output / "positions" / digest({"task": task_id, "repeat": repeat, "arm": arm})
            initial = solve_public_initial(row, skill, condition, repeat, calls, root)
            revision = revise_public(row, initial, skill, calls, executor, root)
            selected = revision["artifact"]
            # Hidden scoring happens only AFTER repair; no H feedback goes back.
            first = audit(row, initial, executor, root)
            last = audit(row, selected, executor, root)
            reference_ok = references[task_id]["status"] == "pass"
            record = seal({"task_id": task_id, "family_id": row["task"].contract.family_id,
                "partition": "development", "repeat": repeat, "arm": arm,
                "draft_status": first["status"] if reference_ok else "unknown",
                "revised_status": last["status"] if reference_ok else "unknown",
                "draft_artifact_hash": initial.content_hash, "selected_artifact_hash": selected.content_hash,
                "draft_audit_hash": first["record_hash"], "revised_audit_hash": last["record_hash"],
                "reference_hash": references[task_id]["record_hash"],
                "revision_hash": revision["record"]["record_hash"], "revision_status": revision["record"]["status"],
                "revision_opportunity_completed": revision["record"].get("revision_opportunity_completed", False),
                "contract_review_required": task_id in prepared["contract_review_flags"],
                "contract_review_note": prepared["contract_review_flags"].get(task_id),
                "scores_relative_to_frozen_H_not_absolute_truth": True})
            _write(root / "result.json", record)
            return record

        jobs = [(t, r, arm) for t in prepared["selected_task_ids"] for r in range(repeats) for arm in skills]
        jobs.sort(key=lambda job: digest({"protocol": protocol["record_hash"], "job": job}))
        results = []
        for start in range(0, len(jobs), workers):
            results.extend(api.parallel(jobs[start:start + workers], position, "development-repair"))
            print(json.dumps({"phase": "development_repair", "completed": len(results), "total": len(jobs)}), flush=True)
        cost = calls.accounting()
        require(cost["reserved_logical_requests"] == cost["terminal_logical_requests"],
                "Unresolved model intents require explicit recovery; no completed experiment report")
        result = seal({"version": VERSION, "protocol_hash": protocol["record_hash"], "freeze_hash": freeze["record_hash"],
            "rows": results, "summary": summarize_rows(results), "cost": cost,
            "effect_claim": "posthoc_development_diagnostic_not_independent_generalization",
            "fixture_only": api.service.get("fixture") is True,
            "source_scores_unchanged": True, "final_access": False, "deployment_authorized": False})
        _write(output / "results.json", result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--detail-limit", type=int, default=12)
    parser.add_argument("--no-updates", action="store_true")
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--execution-workers", type=int, default=2)
    parser.add_argument("--remote-repo", default="/root/skillval-bigmodel-20260922.xTA5fM")
    parser.add_argument("--provider", choices=("bigmodel", "pjlab"), default="bigmodel")
    parser.add_argument("--api-proxy")
    parser.add_argument("--reasoning-effort", choices=("low", "high", "max"), default="low")
    args = parser.parse_args(argv)
    common = dict(repeats=args.repeats, detail_limit=args.detail_limit,
                  include_updates=not args.no_updates, task_ids=args.task_ids)
    if args.command == "prepare":
        prepared, _ = prepare(args.repo, args.source, args.output, **common)
        print(json.dumps({"selected_task_ids": prepared["selected_task_ids"],
                          "frozen_unique_conditions": len(prepared["skills"]), "new_model_calls": 0}))
    else:
        executor = ExecutorPool(args.remote_repo, args.execution_workers)
        try:
            result = run(args.repo, args.source, args.output, executor, workers=args.workers,
                         provider=args.provider, api_proxy=args.api_proxy, reasoning_effort=args.reasoning_effort, **common)
            print(json.dumps({"summary": result["summary"], "cost": result["cost"]}))
        finally:
            executor.close()


if __name__ == "__main__":
    main()
