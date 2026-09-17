"""Bounded real execution for the V8 independent Research calibration bridge.

The source proposal is fixed before the screen; no calibration label is fed
back into proposal repair or Skill learning. Completed replay is offline.
"""

import hashlib
import json
from pathlib import Path

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v5 import core, evaluation
from skillopt.coevolution_v7.tasks import calibration_tasks
from skillopt.coevolution_v7.transport import PacingPolicy, make_budgeted_api
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import research_calibration as bridge

VERSION = "v8-independent-research-screen-driver-v1"
PACING = PacingPolicy(min_interval_seconds=10.0, cooldown_seconds=30.0)


def stable_api(repo, root, *, max_calls, workers):
    return make_budgeted_api(repo, root, max_calls=max_calls, workers=workers, policy=PACING)


def _read(path):
    return core.verify(json.loads(Path(path).read_text()))


def _save(path, row):
    row = core.seal(row)
    write_immutable_json(path, row)
    return row


def _sources(repo):
    paths = [Path(__file__), Path(bridge.__file__), repo / "scripts/coevolution_v8_calibration.py",
             repo / "docs/coevolution-v8-research-screen-protocol.md"]
    for package in ("coevolution_v5", "coevolution_v6", "coevolution_v7"):
        paths.extend((repo / "skillopt" / package).glob("*.py"))
    paths.extend(repo / p for p in ("skillopt/coevolution_v8/patch_diagnostic.py", "skillopt/research_contract_repair.py",
        "skillopt/coevolution_v8/feedback_study.py", "skillopt/coevolution_v8/feedback.py",
        "skillopt/coevolution_v8/coding_tasks.py", "skillopt/coevolution_v8/native_tasks.py",
        "skillopt/validator_pilot/api.py", "skillopt/validator_pilot/tasks.py", "skillopt/coevolution/executor.py",
        "skillopt/coevolution_v3/executor.py", "skillopt/coevolution_v3/tasks.py",
        "skillopt/coevolution_v3/validator.py", "skillopt/coevolution/budget.py"))
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def _preflight(adapters):
    if not executor.sandbox_probe()["ok"]:
        raise RuntimeError("Native sandbox unavailable; no API requests")
    rows = []
    for adapter in adapters:
        task = adapter.task
        for name in ("reference", "equivalent", "semantic_mutant", "preservation_mutant"):
            files = task.reference_files if name == "reference" else task.metadata["controls"][name]
            assessed = adapter.evaluate(files, core.initial_rubric(), phase="promotion", public_only=False)
            row = next(r for r in assessed if r["check_id"] == "coding_contract")
            rows.append({"artifact_id": task.id + ":" + name, "assessment": row})
    return core.seal({"never_model_feedback": True, "calibration": rows})


def run(repo, diagnostic_root, root, *, blocks=4, api_factory=stable_api, adapters=None):
    repo, root = Path(repo).resolve(), bridge._safe_root(root)
    if root == repo / "outputs/coevolution_v8" or not root.is_relative_to(repo / "outputs/coevolution_v8"):
        raise ValueError("Use a distinct run below outputs/coevolution_v8")
    if type(blocks) is not int or not 1 <= blocks <= 6:
        raise ValueError("Predeclare one to six calibration blocks")
    adapters = calibration_tasks() if adapters is None else list(adapters)
    proposal = bridge.load_proposal(repo, diagnostic_root)
    identity = core.seal({"version": VERSION, "diagnostic_result_hash": proposal["diagnostic_result_hash"],
        "diagnostic_root": str(Path(diagnostic_root).resolve()), "blocks": blocks, "round_index": 0,
        "pacing_policy": vars(PACING), "workers": 4,
        "panel_hash": digest([a.task.to_dict() for a in adapters]), "sources": _sources(repo),
        "screen_id": root.name, "registry_root": str(repo / "outputs/coevolution_v8/validator_calibration_registry"),
        "historical_panel": "V7 reserved calibration families, no prior model probe draws in the source V7 run",
        "new_model_draws_required": True, "source_proposal_selected_without_calibration_feedback": True})
    completed = (root / "results.json").exists()
    if completed and not (root / "identity.json").is_file():
        raise ValueError("Completed driver identity is missing")
    write_immutable_json(root / "identity.json", identity)
    if proposal["candidate_rubric"] is None:
        if (any((root / "api").rglob("*.json")) or any((root / "components").rglob("*.json")) or
                (root / "screen.json").exists()):
            raise ValueError("No-candidate result cannot hide prior screen or API artifacts")
        result = core.seal({"version": VERSION, "identity_hash": identity["record_hash"], "complete": True,
            "status": "no_valid_candidate_no_calibration", "calls": 0, "activate_next_round": False})
        if completed and _read(root / "results.json") != result:
            raise ValueError("Completed no-candidate result changed")
        write_immutable_json(root / "results.json", result)
        return result
    screen_path = root / "screen.json"
    if screen_path.exists():
        screen = _read(screen_path)
        if completed and any(not (Path(screen["registry_root"]) / screen["screen_id"] / name).is_file()
                             for name in ("v8_decision.json", "v8_private_calibration.json")):
            raise ValueError("Completed registry evidence missing; never silently rebuild")
        bridge._verify_screen(screen)
        if (screen["proposal"] != proposal or screen["manifest"]["repeats"] != list(range(blocks)) or
                screen["screen_id"] != identity["screen_id"] or
                digest(list(screen["tasks"].values())) != identity["panel_hash"]):
            raise ValueError("Driver and screen identities differ")
    else:
        if completed:
            raise ValueError("Completed screen missing; never reconstruct or send requests")
        screen = bridge.prepare_screen(repo, diagnostic_root, adapters, _preflight(adapters),
            identity["registry_root"], screen_id=identity["screen_id"], round_index=0, blocks=blocks)
        write_immutable_json(screen_path, screen)
    if screen["max_calls"] > 1600:
        raise ValueError("Screen exceeds supported logical budget")

    def job_run(api, job):
        path = root / "components" / (digest(job) + ".json")
        adapter, artifact, rubric, key = bridge._job_parts(screen, job)
        request = bridge.request_for_job(screen, job)
        h = digest(request)
        if path.exists():
            component = _read(path)
            receipt = json.loads((root / "api/calls" / (h + ".json")).read_text())
            if component["job"] != job:
                raise ValueError("Cached component belongs to another job")
            bridge._probe_result(screen, component, receipt)
            bridge._execution_outcome(component, artifact, rubric, component["search"]["inputs"])
            return component
        if api is None:
            raise ValueError("Completed component missing; no online repair")
        search = evaluation.probe(api, adapter, artifact["files"], rubric, key=key, repeat=job["block"])
        assessed = adapter.evaluate(artifact["files"], rubric, phase="promotion", public_only=True,
                                     extra_inputs=search["inputs"])
        return _save(path, {"job": job, "search": search, "assessments": assessed})

    print(json.dumps({"stage": "independent_calibration", "jobs": len(screen["jobs"]),
                      "families": len({a.task.cluster_id for a in adapters}), "completed_replay": completed}), flush=True)
    if completed:
        components = [job_run(None, job) for job in screen["jobs"]]
        ledger = _read(root / "results.json")["ledger"]
    else:
        with api_factory(repo, root / "api", max_calls=screen["max_calls"], workers=4) as api:
            if api.model != proposal["model"] or api.service != proposal["service"]:
                raise ValueError("Screen transport identity differs from Research")
            components = api.parallel(screen["jobs"], lambda job: job_run(api, job), "v8-calibration")
            ledger = api.ledger()
    # Reuse the API-independent closed ledger verifier from the feedback driver.
    from .feedback_study import closed_ledger
    if ledger != closed_ledger(root, screen["max_calls"]):
        raise ValueError("Calibration call ledger does not match persisted receipts")
    receipts = {p.stem: json.loads(p.read_text()) for p in (root / "api/calls").glob("*.json")}
    if len(components) != len(screen["jobs"]) or len(receipts) != screen["max_calls"]:
        raise ValueError("Incomplete or duplicate calibration matrix")
    if {p.stem for p in (root / "components").glob("*.json")} != {digest(j) for j in screen["jobs"]}:
        raise ValueError("Unexpected calibration component artifacts")
    decision = bridge.assess_screen(screen, components, receipts)
    result = core.seal({"version": VERSION, "identity_hash": identity["record_hash"], "complete": True,
        "screen_hash": screen["record_hash"], "decision": decision, "ledger": ledger,
        "components_hash": digest(components), "no_skill_or_benchmark_effect_measured": True})
    if completed and _read(root / "results.json") != result:
        raise ValueError("Completed calibration result changed")
    write_immutable_json(root / "results.json", result)
    return result
