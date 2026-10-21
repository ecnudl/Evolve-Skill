"""One v11 stage: the per-step loop and its sealed records.

Per step: fresh train rollout of the step subset under the Current -> bound rows (never a challenge task) ->
capacity reserve for the post-update challenge (before any update expenditure) -> [diagnosis arms: triage,
hypotheses, checks, graded reports, summary] -> native proposal under authenticated evidence -> [challenge arm:
sealed draw after the candidate is frozen, both Skills re-solve fresh/replay/local-fix positions] -> frozen
decision -> evidence chain. A completed stage replays to the identical record with zero calls; an interruption is a
complete sealed pending record carrying the parent (never resumed); a revert or park completes carrying the
parent. No canonical validation split is read or authorized; the post-update decision uses a fresh panel sampled
from the stage's fixed reserved development challenge pool (a selection function), held out from diagnosis,
reflection and Research."""
from __future__ import annotations

import hashlib
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.contracts import check_skill, skill_budget
from skillopt.continual_learning.feedback import artifacts as learning_artifacts
from skillopt.continual_learning.feedback import benchmark_for
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending, Ledger
from skillopt.continual_learning.recovery import client_options
from skillopt.continual_learning.skillopt import native_sources
from skillopt.continual_learning.verifier import default_policy_record, native_probe_executor
from skillopt.validator_pilot.api import CachedAPI, digest

from . import METHOD, PROTOCOL
from .challenge import draw as draw_challenge
from .challenge import run as run_challenge
from .challenge import run_references
from .checks import state_probe_executor
from .decision import ADVANCING, decide
from .diagnosis import call_json, run_diagnosis
from .label_feedback import run_label_feedback
from .matched import comparator_traces, matched_record, selection_record, treatment_delivery_problem
from .protocol import CHALLENGE_ARMS, STUDY_ARMS, challenge_items, step_items, validate_manifest
from .screen import chain_summary as screen_summary
from .screen import max_positions as screen_positions
from .screen import run_screen
from .research import make_researcher, natural_fetcher
from .updater import propose_with_evidence

CHAIN_VERSION = "active-evidence-chain-v5"  # v5: the composition-aware screen and the selection study (v4: decision v2)
RECORD_FOLDERS = ("native", "native_matched", "steps", "chain", "challenge", "diagnosis", "host_only/triage", "screen")
MERGE_BATCH = 8  # skillopt.gradient.aggregate.merge_patches batch size (per-group merges, then one final merge)
TOP_FILES = ("identity.json", "panel.json", "started.json")


def stage_artifacts(root, ledger):
    """The governed inventory: receipts, intents, evaluations, scorer artifacts, the stage's top-level markers and
    every record this mode seals."""
    result = {**learning_artifacts(ledger), **{
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in TOP_FILES if (root / name).exists()}}
    result.update({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in RECORD_FOLDERS for p in sorted((root / folder).rglob("*")) if p.is_file()})
    return result


def rollout_rows(adapter, items, skill, rollout):
    """The first row alone (the first real reply is the health barrier), then the rest concurrently."""
    rows = adapter.evaluate_rows(items[:1], {"skill": skill}, rollout=rollout)
    if len(items) > 1:
        rows += adapter.evaluate_rows(items[1:], {"skill": skill}, rollout=rollout)
    return rows


def bind_step_rows(ledger, value, items, rows, skill, rollout):
    """Every known row re-derived from its sealed evaluation and intent (never looked up by the row's own claim);
    a row of a non-step family is refused. Each pair keeps its saved evaluation for host-only triage."""
    require(len(items) == len(rows), "Items and rows must be given pairwise")
    families = set(value["active_evidence"]["step_families"])
    pairs, unknown = [], 0
    for item, row in zip(items, rows):
        task = item["task"]
        require(task["family_id"] in families, "A challenge-pool task can never be a step row")
        request = {"manifest_hash": value["record_hash"], "candidate_hash": digest({"skill": skill}),
                   "task_hash": digest(task), "role": "train", "repeat": 0, "benchmark": value["benchmark"],
                   "rollout": rollout}
        key = digest(request)
        saved = read_json(ledger.root / "evaluations" / (key + ".json"), sealed=True)
        require(item["role"] == "train" and value["authorized_tasks"].get(digest(task)) == "train"
                and saved["request"] == request
                and read_json(ledger.root / "evaluation_intents" / (key + ".json"), sealed=True) == seal(request),
                "A step row is not this rollout's sealed evaluation of its task")
        if row["score"] is None:
            require(saved["score"]["status"] == "unknown" and row["trajectory"] is None, "Unknown row mismatch")
            unknown += 1
            continue
        require(row["output"]["evidence_hash"] == saved["record_hash"]
                and row["output"]["output"] == saved["prediction"]["output"]
                and row["score"] == saved["score"]["score"] and saved["score"]["status"] in {"pass", "fail"},
                "A step row differs from its sealed evaluation")
        pairs.append({"item": item, "row": row, "token": saved["record_hash"], "saved": saved,
                      "host_status": "pass" if row["score"] == 1 else "fail"})
    return pairs, unknown


def reserve_capacity(ledger, value, panel, pairs, used):
    """Before any update expenditure: the post-update challenge must keep its solver capacity (two Skills, each
    solver call allowed one length recovery) and its metric positions; otherwise the stage stops pending."""
    limits = value["active_evidence"]["limits"]
    pool = {digest(t) for t in panel["tasks"] if t["family_id"] in set(value["active_evidence"]["challenge_families"])}
    fresh = min(limits["fresh_tasks"], len(pool - set(used)))
    # without an eligible fresh task the challenge does not run at all (no replay or local-fix comparison either)
    positions = 0 if fresh == 0 else (
        fresh + min(limits["replay_rows"], sum(p["host_status"] == "pass" for p in pairs))
        + min(limits["local_fix_rows"], sum(p["host_status"] == "fail" for p in pairs))
        # the optional in-sample panel: an upper bound (positions shared with replay / local-fix are solved once)
        + min(limits.get("train_panel_rows", 0),
              sum(t["family_id"] in set(value["active_evidence"]["step_families"]) for t in panel["tasks"])))
    post_update = value["active_evidence"]["arms"]["post_update"]
    matched = post_update == "matched_scalar_branch"
    # a matched study also solves the fresh holdout once per reference Skill (the parent plus the sealed ones)
    references = 1 + len(value["active_evidence"]["reference_skills"]) if post_update in STUDY_ARMS else 0
    # the composition-aware screen re-solves the step rows under two controls, the candidate and one variant per edit
    screen = (screen_positions(len(pairs), limits["edit_budget"])
              if value["active_evidence"].get("update_mode") == "screened" else 0)
    needed_metric = 2 * positions + references * fresh + screen
    needed_calls = 2 * needed_metric
    # the native updater's own ledger requests: failure and success rows are reflected in separate minibatches
    # (one analyst call each), the patches are merged per group in batches of MERGE_BATCH plus one final merge, then
    # ranked once; every call may take one JSON retry. The matched-branch study runs two updater branches.
    minibatch = value["budget"]["minibatch_size"]
    failures = sum(p["host_status"] == "fail" for p in pairs)
    fail_groups, pass_groups = -(-failures // minibatch), -(-(len(pairs) - failures) // minibatch)
    groups = fail_groups + pass_groups
    merges = _merge_calls(fail_groups) + _merge_calls(pass_groups) + 1  # per-group merge levels, then the final merge
    branches = 2 if matched else 1
    updater_calls = branches * 2 * (groups + merges + 1)
    budget = value["budget"]
    costs = ledger.snapshot()
    intents = len(list((ledger.root / "evaluation_intents").glob("*.json")))
    logical = costs["logical_calls"]
    if (intents + needed_metric > budget["max_metric_calls"]
            or logical + needed_calls + updater_calls > budget["max_api_calls"]
            or costs.get("reflection_calls", 0) + updater_calls > budget["max_reflection_calls"]):
        raise BudgetExhausted("challenge_budget_reserve_unavailable")
    return {"positions": positions, "reference_evaluations": references * fresh, "screen_positions": screen,
            "challenge_metric_calls": 2 * positions + references * fresh, "metric_calls": needed_metric,
            "solver_calls_with_recovery": needed_calls,
            "updater_calls": updater_calls, "protected_calls": needed_calls + updater_calls,
            "metric_calls_used": intents, "api_calls_used": logical}


def _merge_calls(patches):
    """Merge calls the native merger makes for one group: batches of MERGE_BATCH, repeated until one patch remains."""
    calls = 0
    while patches > 1:
        patches = -(-patches // MERGE_BATCH)
        calls += patches
    return calls


def _edit_count(proposal):
    selected = proposal.get("selected")
    if type(selected) is dict and type(selected.get("edits")) is list:
        return len(selected["edits"])
    return None


def _chain(value, panel, step, rollout, pairs, unknown, items, proposal, candidate, draw, outcome, decision, diagnosis,
           reserve, matched=None, screen=None, native_candidate=None, parent=None):
    arms = value["active_evidence"]["arms"]
    fresh = outcome["summary"]["fresh"] if outcome is not None and outcome["status"] == "completed" else None
    replay = outcome["summary"]["replay"] if fresh is not None else None
    return seal({
        "chain_version": CHAIN_VERSION, "protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": step,
        "arms": arms,
        "rollout": {"kind": "fresh", "rollout": rollout, "rows": len(items), "known": len(pairs), "unknown": unknown,
                    "outputs_new": True, "tasks_reused_across_steps": step > 0},
        "problem": {"host_fail": sorted(p["token"] for p in pairs if p["host_status"] == "fail"),
                    "host_pass": sorted(p["token"] for p in pairs if p["host_status"] == "pass"),
                    "triage_hash": diagnosis.get("triage_hash")},
        "diagnosis_status": diagnosis["status"], "diagnosis_delivery": diagnosis.get("delivery"),
        "hypotheses": diagnosis.get("hypotheses", []), "research": diagnosis.get("research", []),
        "fact_needs": diagnosis.get("fact_needs", []),  # declared fact needs and whether Research was reached for them
        # the failure-message study arm: what was released to the message-branch analysts, and its sealed audit
        "information_release": diagnosis.get("information_release"),
        "release_audit_hash": diagnosis.get("release_audit_hash"),
        "checks": diagnosis.get("checks", []), "observations": diagnosis.get("observations", []),
        "reports": {"rows_with_evidence": diagnosis.get("rows_with_evidence", 0),
                    "summary_hash": diagnosis.get("summary_hash")},
        "edits": {"proposal_hash": proposal["record_hash"], "status": proposal["status"],
                  "candidate_hash": digest(candidate) if candidate is not None else None,
                  "edit_count": _edit_count(proposal), "native_fallbacks": proposal["native_fallbacks"]},
        "reserve": reserve,
        "challenge": None if draw is None else {"draw_hash": draw["record_hash"], "outcome_hash": outcome["record_hash"],
                                                "status": outcome["status"],
                                                "summary": outcome.get("summary"), "reason": outcome.get("reason")},
        "decision": {"record_hash": decision["record_hash"], "action": decision["action"], "reason": decision["reason"]},
        "matched": matched,  # the matched-branch study record (both branches, holdout pairs, prespecified outcome class)
        # the composition-aware screen (update_mode "screened"): which exact text this step put forward
        "update_mode": value["active_evidence"].get("update_mode", "native"), "screen": screen,
        "native_candidate_hash": digest(native_candidate) if native_candidate is not None else None,
        # observable participation of each link, never a causal benefit claim
        "intervened": {"research_consulted": bool(diagnosis.get("research_consulted", False)),
                       "label_feedback": arms["feedback"] == "hidden_failure",
                       "research_new_information": bool(diagnosis.get("research_new_information", False)),
                       "feedback_differs_from_scalar": bool(diagnosis.get("rows_with_evidence", 0))
                       or diagnosis.get("summary") is not None,
                       "skill_changed": candidate is not None and candidate != parent,
                       "screen_changed_selection": bool(screen is not None and screen["selection"]["id"] != "candidate"),
                       "challenge_delta": bool(fresh is not None and (fresh["net_wins"] != 0 or replay["regressions"])),
                       "decision": decision["action"]},
        # the solver necessarily sees a challenge task it solves; diagnosis, reflection and Research never do
        "never_shown_to_diagnosis_or_reflection": {
            "challenge_task_hashes": sorted(digest(i["task"]) for i in challenge_items(value, panel))},
    })


def _pending_record(root, manifest, identity, reason, *, steps=(), accepted=0):
    """A complete sealed pending result (parent carried, existing accounting and inventory, no resume)."""
    ledger = Ledger(root, manifest, None)
    costs = ledger.snapshot()
    return seal({"version": manifest["version"], "protocol": PROTOCOL, "method": METHOD,
                 "identity_hash": identity["record_hash"], "status": "pending",
                 "candidate_skill": manifest["parent_skill"], "reason": reason, "accepted_steps": accepted,
                 "iterations_completed": False, "steps": list(steps), "arms": manifest["active_evidence"]["arms"],
                 "decisions": [s["decision"] for s in steps], "evidence_chain_hashes": [s["chain_hash"] for s in steps],
                 "evidence_kind": manifest["evidence_kind"], "costs": costs, "artifacts": stage_artifacts(root, ledger),
                 "model_calls_submitted": costs["logical_calls"], "deployment_authorized": False,
                 "scope_expansion_authorized": False, "resume_supported": False})


def run_stage(manifest, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None,
              fixture_probe_executor=None, fixture_fetcher=None):
    """Run (or replay) one sealed v11 stage into ``output``; returns the sealed result."""
    validate_manifest(manifest, panel)
    extension = manifest["active_evidence"]
    arms, limits = extension["arms"], extension["limits"]
    fixture = manifest["model"]["provider"] == "fixture"
    diagnosis_arm = arms["feedback"] != "scalar"
    executor_arm = arms["feedback"] in ("diagnosis", "diagnosis_research")  # the label arm executes nothing
    matched_study = arms["post_update"] == "matched_scalar_branch"
    selection_study = arms["post_update"] == "matched_selection_branch"
    screened = extension.get("update_mode", "native") == "screened"
    require(fixture == (fixture_api is not None and fixture_evaluate is not None), "Invalid fixture callbacks")
    require(fixture or (fixture_api is None and fixture_evaluate is None), "Natural run cannot inject fixtures")
    require(fixture or (fixture_probe_executor is None and fixture_fetcher is None),
            "Diagnosis fixtures belong to a fixture run only")
    require(not (fixture and executor_arm) or fixture_probe_executor is not None,
            "A diagnosis fixture run needs a probe executor")
    root = safe_path(output)
    with output_lock(root):
        identity = seal({"protocol": PROTOCOL, "method": METHOD, "manifest": manifest,
                         "native_sources": native_sources(), "edit_budget": limits["edit_budget"], "arms": arms,
                         "gate": ("post_update_challenge_replay_family_sign_test_decision_v2"
                                  if arms["post_update"] == "challenge_replay"
                                  else "matched_scalar_branch_study_with_holdout_references_nothing_deployed_v2"
                                  if arms["post_update"] == "matched_scalar_branch"
                                  else "matched_selection_branch_study_screen_vs_native_nothing_deployed_v3"
                                  if arms["post_update"] == "matched_selection_branch"
                                  else "none_accepted_without_challenge"),
                         "update_mode": extension.get("update_mode", "native"),
                         "training_schedule": "full_step_pass_per_update",
                         "validation_role": "no_canonical_validation_split__reserved_development_challenge_pool_selects",
                         "rubric": "frozen_default_this_round",
                         "meta": False, "slow": False, "skill_aware": False, "chain": CHAIN_VERSION})
        write_json(root / "identity.json", identity)
        write_json(root / "panel.json", panel)
        terminal = root / "result.json"
        if terminal.exists():
            result = read_json(terminal, sealed=True)
            ledger = Ledger(root, manifest, None)
            require(result["identity_hash"] == identity["record_hash"]
                    and result["artifacts"] == stage_artifacts(root, ledger), "Learning evidence changed")
            ledger.snapshot()
            return result
        if (root / "started.json").exists():
            # an interrupted stage becomes a durable terminal pending record (parent carried, accounting kept)
            record = _pending_record(root, manifest, identity, "interrupted_stage_no_automatic_resume")
            write_json(terminal, record)
            return record
        if not fixture:
            require(repo is not None, "Natural run needs credential repository")
            require(backends.readiness(benchmark_for(manifest), manifest["runtime"])["status"] == "ready",
                    "Benchmark native runtime is not ready")
        write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
        api = fixture_api
        steps, accepted, used = [], [], set()
        current = manifest["parent_skill"]
        rubric = default_policy_record(manifest["benchmark"])  # frozen this round (policy_lifecycle: frozen)
        try:
            if not fixture:
                model = manifest["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"],
                                workers=1, reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}),
                                **client_options(manifest))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, manifest, api)
            adapter = Adapter(manifest, root, ledger, fixture_evaluate=fixture_evaluate)
            executor = fixture_probe_executor if fixture else native_probe_executor(manifest["runtime"])
            state_executor = fixture_probe_executor if fixture else state_probe_executor(manifest["runtime"])
            items = step_items(manifest, panel)
            require(extension["rollout_source"] is None, "Rollout import arrives with a later increment")
            for step in range(manifest["budget"]["max_iterations"]):
                rollout = step
                rows = rollout_rows(adapter, items, current, rollout)
                pairs, unknown = bind_step_rows(ledger, manifest, items, rows, current, rollout)
                if not pairs or len(pairs) < manifest["recovery_policy"]["min_known_fraction"] * len(items):
                    raise LearningPending("insufficient_known_train")
                reserve = (reserve_capacity(ledger, manifest, panel, pairs, used)
                           if arms["post_update"] in CHALLENGE_ARMS or screened else None)
                traces = [{**p["row"]["trajectory"], "evidence_hash": p["token"]} for p in pairs]
                diagnosis = {"status": "scalar_arm_no_diagnosis", "rows_with_evidence": 0, "summary_hash": None}
                reports = summary = None
                if diagnosis_arm and arms["feedback"] == "hidden_failure":
                    # the failure-message study arm: zero-call, audited release of bounded hidden-test messages
                    diagnosis = run_label_feedback(ledger, manifest, root, step, pairs, unknown)
                    if diagnosis["status"] != "completed":  # release below the minimum: no updater call at all
                        raise LearningPending("label_feedback_" + diagnosis["status"])
                elif diagnosis_arm:
                    researcher = None
                    if arms["feedback"] == "diagnosis_research":
                        fetcher = fixture_fetcher if fixture else natural_fetcher(manifest)
                        require(fetcher is not None, "A research fixture run needs a fetcher")
                        researcher = make_researcher(ledger, manifest, root / "diagnosis" / str(step), step, fetcher,
                                                     call_json)
                    diagnosis = run_diagnosis(ledger, manifest, root, step, pairs, unknown, rubric=rubric,
                                              executor=executor, state_executor=state_executor, researcher=researcher,
                                              reserve_calls=0 if reserve is None else reserve["protected_calls"])
                if matched_study:
                    # the study never spends two updater branches and a holdout on an undelivered treatment package
                    problem = treatment_delivery_problem(diagnosis)
                    if problem is not None:
                        raise LearningPending("treatment_package_not_delivered:" + problem)
                if diagnosis_arm:
                    reports, summary = diagnosis["reports"], diagnosis["summary"]
                    for trace in traces:
                        report = reports.get(trace["evidence_hash"])
                        if report is not None and report["feedback"]:
                            trace["Feedback"] = {**trace["Feedback"], "evidence": report["feedback"]}
                proposal = propose_with_evidence(current, traces, root / "native" / str(step), ledger, step=step,
                                                 seed=manifest["seed"] + step,
                                                 minibatch_size=manifest["budget"]["minibatch_size"],
                                                 edit_budget=limits["edit_budget"], reports=reports, summary=summary,
                                                 label=arms["feedback"] == "hidden_failure")
                candidate = proposal["candidate_skill"] if proposal["status"] == "candidate_ready" else None
                draw = outcome = matched = references = screen = None
                comparator_skill = current
                native_candidate = candidate
                if screened and candidate is not None:
                    # which exact text does this step put forward: the native candidate, a leave-one-edit-out variant,
                    # or nothing (abstention)? Measured on the step rows with interleaved parent controls.
                    screen = run_screen(adapter, ledger, manifest, root, step, current, proposal, pairs,
                                        protected_calls=2 * reserve["challenge_metric_calls"],
                                        protected_metric=reserve["challenge_metric_calls"])
                    candidate = screen["selected_skill"]
                if selection_study:
                    # comparator = the native candidate; treatment = the screen's selection (the parent on abstention)
                    if native_candidate is not None:
                        comparator_skill = native_candidate
                        candidate = candidate if candidate is not None else current
                    else:
                        candidate = None  # nothing to select: no holdout
                if matched_study:
                    # the matched scalar branch: the same traces without any evidence, the scalar arm's exact package
                    comparator = propose_with_evidence(current, comparator_traces(traces),
                                                       root / "native_matched" / str(step), ledger, step=step,
                                                       seed=manifest["seed"] + step,
                                                       minibatch_size=manifest["budget"]["minibatch_size"],
                                                       edit_budget=limits["edit_budget"])
                    if comparator["status"] == "candidate_ready":
                        comparator_skill = comparator["candidate_skill"]
                if candidate is not None and arms["post_update"] in CHALLENGE_ARMS:
                    draw = draw_challenge(manifest, panel, step, step_rows=pairs, candidate_hash=digest(candidate),
                                          root=root, exclude=used)
                    used.update(e["task_hash"] for e in draw["fresh"])
                    outcome = run_challenge(adapter, ledger, manifest, panel, step, draw, comparator_skill, candidate,
                                            root)
                    if matched_study or selection_study:
                        # evaluation-only references on the same drawn holdout: the parent, then the sealed Skills
                        references = run_references(
                            adapter, ledger, manifest, panel, step, draw, outcome,
                            [("parent", current)] + [(r["name"], r["skill"]) for r in extension["reference_skills"]],
                            root)
                decision = decide(outcome, limits, parent=comparator_skill, candidate=candidate, step=step)
                write_json(root / "challenge" / str(step) / "decision.json", decision)
                if matched_study:
                    matched = matched_record(comparator, comparator_skill, current, proposal, candidate, outcome,
                                             diagnosis, limits, references=references)
                elif selection_study:
                    matched = selection_record(proposal, native_candidate, current, candidate, screen, outcome, limits,
                                               references=references, diagnosis=diagnosis)
                chain = _chain(manifest, panel, step, rollout, pairs, unknown, items, proposal, candidate, draw,
                               outcome, decision, diagnosis, reserve, matched=matched, screen=screen_summary(screen),
                               native_candidate=native_candidate, parent=current)
                write_json(root / "chain" / (str(step) + ".json"), chain)
                record = seal({"step": step, "rollout": rollout, "rows": len(items), "known": len(pairs),
                               "unknown": unknown, "diagnosis_status": diagnosis["status"],
                               "rows_with_evidence": diagnosis.get("rows_with_evidence", 0),
                               "proposal_hash": proposal["record_hash"], "proposal_status": proposal["status"],
                               "candidate_hash": digest(candidate) if candidate is not None else None,
                               "draw_hash": None if draw is None else draw["record_hash"],
                               "outcome_hash": None if outcome is None else outcome["record_hash"],
                               "challenge_status": None if outcome is None else outcome["status"],
                               "challenge_summary": None if outcome is None else outcome.get("summary"),
                               "decision": decision["action"], "decision_reason": decision["reason"],
                               "decision_hash": decision["record_hash"], "chain_hash": chain["record_hash"],
                               "matched_outcome": None if matched is None else matched["outcome"]["outcome"],
                               "matched_reason": None if matched is None else matched["outcome"]["reason"]})
                write_json(root / "steps" / (str(step) + ".json"), record)
                steps.append(record)
                if decision["action"] in ADVANCING and arms["post_update"] not in STUDY_ARMS:  # a study deploys nothing
                    current = candidate
                    accepted.append(candidate)
            payload = {"status": "completed", "candidate_skill": check_skill(current, skill_budget(manifest)),
                       "reason": f"active_evidence_{arms['feedback']}_{arms['post_update']}_frozen_decision",
                       "accepted_steps": len(accepted), "iterations_completed": True}
        except Exception as exc:
            reason = str(exc) if isinstance(exc, LearningPending) else type(exc).__name__
            payload = {"status": "pending", "candidate_skill": manifest["parent_skill"], "reason": reason,
                       # an unexpected exception keeps its message (bounded) so the operator can review the stop
                       "reason_detail": None if isinstance(exc, LearningPending) else str(exc)[:500],
                       "accepted_steps": len(accepted), "iterations_completed": False}
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, manifest, api)
        costs = ledger.snapshot()
        if ledger.usage_blocks_completion(costs) and payload["status"] == "completed":
            payload.update(status="pending", candidate_skill=manifest["parent_skill"], reason="incomplete_usage")
        record = seal({"version": manifest["version"], "protocol": PROTOCOL, "method": METHOD,
                       "identity_hash": identity["record_hash"], **payload, "steps": steps, "arms": arms,
                       "decisions": [s["decision"] for s in steps],
                       "evidence_chain_hashes": [s["chain_hash"] for s in steps],
                       "evidence_kind": manifest["evidence_kind"], "costs": costs,
                       "model_calls_submitted": costs["logical_calls"],
                       "artifacts": stage_artifacts(root, ledger), "deployment_authorized": False,
                       "scope_expansion_authorized": False, "resume_supported": False})
        write_json(terminal, record)
        return record
