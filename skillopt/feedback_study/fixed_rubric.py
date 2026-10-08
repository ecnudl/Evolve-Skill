"""L1 fixed-rubric study (``fivebench-fixed-rubric-study-v1``; registered 10/8, Codex design round post-S3-2).

A component experiment, not a learning stage: ONE fresh train rollout of the source stage's parent Skill (same
tasks, model, runtime and recovery policy as the source, under this study's own manifest and ledger) is judged by
FROZEN rubric records -- the default KOR rubric and the three rubrics the main method's S3 stage evolved (h0, h1,
h2) -- one judgment per rubric x output cell, in a randomized interleaved schedule. No policy proposal, Research,
analyst, Skill gate, validation or test evaluation happens. The primary contrast (h2 - default detection rate on
the identical eligible host-fail rows, family-level sign-flip test) and the false-rejection safety rule are frozen
here before any call. Host labels only score the verifier; the judge never sees them or a reference answer.

A positive result supports only: "on fresh outputs of these fixed KOR train tasks, the frozen final evolved rubric
detected more host-failed outputs than the default". Not: monotone evolution, reliable policy search, unseen-family
generalization, Research benefit or Skill improvement. An interruption is pending (inconclusive), never resumed.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.feedback import artifacts as learning_artifacts
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY_V10, client_options
from skillopt.continual_learning.verifier import (TERMINAL_DELIVERY, _bounded_response, _public_view,
                                                  default_policy_record)
from skillopt.validator_pilot.api import CachedAPI, digest

from .common import FixedRubricVerifier, bind_rows, run_cells, study_manifest, study_sources, validate_rubric_record

PROTOCOL = "fivebench-fixed-rubric-study-v1"
BENCHMARK = "korbench"
ARMS = ("default", "h0", "h1", "h2")
ROLLOUT = 0
MODULES = ("__init__.py", "common.py", "fixed_rubric.py")  # the study's own code identity (feedback_study/*)
SCHEDULE_SEED = 20261008
BOOTSTRAP_SEED = 20261009
AUDIT_SEED = 20261010
BUDGET = {"max_metric_calls": 120, "max_reflection_calls": 1, "max_api_calls": 1800, "max_reported_tokens": 12_000_000,
          "max_iterations": 1, "minibatch_size": 8, "solver_max_tokens": 65536, "reflection_max_tokens": 8192,
          "max_verifier_calls": 1440, "verifier_max_tokens": 4096}
ANALYSIS = {
    "row_rejection": "at_least_one_valid_fail_check",
    "row_decided": "at_least_one_valid_pass_or_fail_check",
    "abstention": "no_decision_counts_as_no_rejection_and_stays_an_abstention",
    "detection_rate": "rejected_rows / all_eligible_host_fail_rows",
    "false_rejection_rate": "rejected_rows / all_eligible_host_pass_rows",
    "eligibility": "known_host_score_on_the_fresh_rollout_same_rows_for_every_arm",
    "primary": {"treatment": "h2", "control": "default", "endpoint": "detection_rate",
                "test": "family_sign_flip_exact_two_sided", "alpha": 0.05,
                "directional_claim": "difference_positive_and_p_at_most_alpha"},
    "safety": {"endpoint": "false_rejection_rate_difference_h2_minus_default", "margin": 0.05,
               "bound": "family_cluster_bootstrap_percentile_one_sided_95_upper", "resamples": 20000,
               "seed": BOOTSTRAP_SEED, "conditional_frr_cap": 0.25,
               "failing_safety_wording": "higher_detection_with_reported_false_rejection_and_uncertainty_only"},
    "secondary": ["row_level_exact_mcnemar_detection_and_false_rejection", "h0_h1_descriptive_rates",
                  "decided_coverage_by_host_status", "v7_conditional_rates_and_authorization", "per_family_table",
                  "delivery_accounting", "blinded_public_contract_audit_of_h2_default_disagreements"],
    "prohibited": ["policy_proposal", "research", "analyst", "skill_gate", "validation_evaluation", "test_evaluation",
                   "selecting_the_l3_rubric_by_this_result", "resuming_an_interrupted_study"],
    # The frozen v10 ledger rule every learning stage completes under: a blocking usage gap (an open call, a
    # delivered reply without usage, the HTTP attempt limit or the unknown-cost attempt cap exceeded) or an
    # evaluation intent without its receipt makes the study pending; a bounded failed attempt whose usage the
    # provider never reported is a cost-accounting gap, not a judgment gap -- it is reported (usage_complete,
    # unknown_cost_attempts) and does not block.
    "completion": "frozen_v10_ledger_blocking_usage_gap_rule_bounded_unknown_cost_attempts_reported",
}
AUDIT_INSTRUCTIONS = (
    "Blinded public-contract audit (rubric identity and host label hidden). For every item decide whether EACH "
    "claimed violation is (a) supported: the quoted obligation is stated by the public task text and the response "
    "visibly violates it; (b) unsupported: the obligation is not stated, is misread, or the response satisfies it; "
    "(c) undeterminable from the public text and response alone. Do not solve the task or consult any answer key.")


def build_spec(template, rubrics, source):
    """The sealed pre-registration: every choice the result depends on, frozen before any call."""
    spec = seal({"protocol": PROTOCOL, "benchmark": BENCHMARK, "arms": list(ARMS), "rollout": ROLLOUT,
                 "rubrics": {arm: rubrics[arm] for arm in ARMS},
                 "rubric_policy_hashes": {arm: rubrics[arm]["policy_hash"] for arm in ARMS},
                 "template": template, "budget": dict(BUDGET), "schedule_seed": SCHEDULE_SEED,
                 "audit_seed": AUDIT_SEED, "analysis": ANALYSIS, "source": source,
                 "information_origin": "fresh_train_rollout_host_labels_score_the_verifier_only",
                 "deployment_authorized": False})
    validate_spec(spec)
    return spec


def validate_spec(spec):
    verify(spec)
    require(spec["protocol"] == PROTOCOL and spec["benchmark"] == BENCHMARK and spec["arms"] == list(ARMS)
            and spec["rollout"] == ROLLOUT and spec["budget"] == BUDGET and spec["schedule_seed"] == SCHEDULE_SEED
            and spec["audit_seed"] == AUDIT_SEED and spec["analysis"] == ANALYSIS
            and set(spec["rubrics"]) == set(ARMS), "Not this study's registered protocol")
    rubrics = spec["rubrics"]
    for arm in ARMS:
        validate_rubric_record(rubrics[arm], BENCHMARK)
        require(spec["rubric_policy_hashes"][arm] == rubrics[arm]["policy_hash"], "Rubric hash registry differs")
    default = default_policy_record(BENCHMARK)
    require(rubrics["default"] == default, "The default arm is not the frozen default KOR rubric")
    for parent, child in (("default", "h0"), ("h0", "h1"), ("h1", "h2")):
        require(rubrics[child]["status"] == "update" and rubrics[child]["parent_policy_hash"] == rubrics[parent]["policy_hash"],
                "The evolved rubrics are not one recorded evolution chain from the default")
    require(len({rubrics[arm]["policy_hash"] for arm in ARMS}) == len(ARMS), "Arms must be distinct rubrics")
    template = spec["template"]
    require(set(template) == {"panel_hash", "train_families", "selection_families", "model", "runtime", "parent_skill",
                              "seed", "recovery_policy"}
            and template["recovery_policy"] == POLICY_V10, "The template is not a v10 (v7 delivery) source template")
    return spec


def make_schedule(spec, tokens):
    """Randomized, interleaved execution slots: every arm x eligible output once, in a seeded order."""
    cells = [[arm, token] for token in sorted(tokens) for arm in spec["arms"]]
    random.Random(spec["schedule_seed"]).shuffle(cells)
    return seal({"protocol_hash": spec["record_hash"], "rollout": spec["rollout"], "eligible_tokens": sorted(tokens),
                 "cells": cells})


# ----------------------------------------------------------------------------- analysis (pure, zero calls)
def _rejected(record):
    return any(p["outcome"] == "fail" for p in record["probes"])


def _decided(record):
    return any(p["outcome"] in {"pass", "fail"} for p in record["probes"])


def _terminal(record):
    return any(type(t) is dict and (t.get("status") in TERMINAL_DELIVERY or t.get("status") == "prompt_too_large")
               for t in record["trace"])


def _invalid(record):
    return any(type(t) is dict and t.get("status") in {"invalid_checks", "checks_rejected"} for t in record["trace"])


def arm_metrics(meta, records):
    fail = [m["token"] for m in meta if m["host_status"] == "fail"]
    passed = [m["token"] for m in meta if m["host_status"] == "pass"]
    rejected_fail = sum(_rejected(records[t]) for t in fail)
    rejected_pass = sum(_rejected(records[t]) for t in passed)
    decided_fail = sum(_decided(records[t]) for t in fail)
    decided_pass = sum(_decided(records[t]) for t in passed)
    return {"eligible_host_fail_rows": len(fail), "eligible_host_pass_rows": len(passed),
            "rejected_host_fail_rows": rejected_fail, "rejected_host_pass_rows": rejected_pass,
            "detection_rate": rejected_fail / len(fail) if fail else None,
            "false_rejection_rate": rejected_pass / len(passed) if passed else None,
            "decided_host_fail_rows": decided_fail, "decided_host_pass_rows": decided_pass,
            "abstained_host_fail_rows": len(fail) - decided_fail, "abstained_host_pass_rows": len(passed) - decided_pass,
            "decided_coverage": (decided_fail + decided_pass) / len(meta) if meta else None,
            "terminal_delivery_rows": sum(_terminal(records[m["token"]]) for m in meta),
            "rows_with_invalid_or_rejected_checks": sum(_invalid(records[m["token"]]) for m in meta)}


def sign_flip_two_sided(differences):
    """Exact two-sided sign-flip p-value of sum(differences): every family's sign flips independently under the
    null (exchangeable rubric labels within a family); computed by exact convolution, not sampling."""
    require(all(type(d) is int for d in differences), "Integer family differences required")
    informative = [d for d in differences if d != 0]
    observed = sum(informative)
    distribution = {0: 1}
    for d in informative:
        nxt = {}
        for total, count in distribution.items():
            nxt[total + d] = nxt.get(total + d, 0) + count
            nxt[total - d] = nxt.get(total - d, 0) + count
        distribution = nxt
    extreme = sum(count for total, count in distribution.items() if abs(total) >= abs(observed))
    return {"observed_sum": observed, "informative_families": len(informative),
            "p_value": extreme / 2 ** len(informative), "method": "exact_family_sign_flip_convolution"}


def cluster_bootstrap_upper(families, *, seed, resamples, level=0.95):
    """One-sided percentile upper bound of a pooled rate difference, resampling whole families.
    ``families`` = [(sum of row differences, rows)] for families with at least one row."""
    require(families and all(n > 0 for _, n in families), "Families with rows required")
    rng = random.Random(seed)
    stats = []
    for _ in range(resamples):
        picked = [families[rng.randrange(len(families))] for _ in families]
        stats.append(sum(d for d, _ in picked) / sum(n for _, n in picked))
    stats.sort()
    return stats[math.ceil(level * resamples) - 1]


def mcnemar_exact(b, c):
    """Exact two-sided McNemar (binomial on discordant rows); rows treated as independent (secondary only)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def analyze(spec, meta, records, summaries):
    analysis = spec["analysis"]
    treatment, control = analysis["primary"]["treatment"], analysis["primary"]["control"]
    arms = {arm: {**arm_metrics(meta, records[arm]),
                  "policy_hash": spec["rubrics"][arm]["policy_hash"],
                  "v7_conditional": {k: summaries[arm][k] for k in (
                      "detections", "host_fail_rows", "false_rejections", "host_pass_rows", "false_rejection_rate",
                      "authorized", "coverage", "delivery")},
                  "summary_hash": summaries[arm]["record_hash"], "calibration_hash": summaries[arm]["calibration_hash"]}
            for arm in spec["arms"]}
    families = sorted({m["family"] for m in meta})

    def diff(token):
        return int(_rejected(records[treatment][token])) - int(_rejected(records[control][token]))

    per_family = []
    for family in families:
        rows = [m for m in meta if m["family"] == family]
        fail = [m["token"] for m in rows if m["host_status"] == "fail"]
        passed = [m["token"] for m in rows if m["host_status"] == "pass"]
        per_family.append({"family": family, "host_fail_rows": len(fail), "host_pass_rows": len(passed),
                           "rejected_host_fail": {arm: sum(_rejected(records[arm][t]) for t in fail) for arm in spec["arms"]},
                           "rejected_host_pass": {arm: sum(_rejected(records[arm][t]) for t in passed) for arm in spec["arms"]},
                           "detection_difference": sum(diff(t) for t in fail),
                           "false_rejection_difference": sum(diff(t) for t in passed)})
    fail_rows = [m["token"] for m in meta if m["host_status"] == "fail"]
    pass_rows = [m["token"] for m in meta if m["host_status"] == "pass"]
    flip = sign_flip_two_sided([f["detection_difference"] for f in per_family])
    difference = (arms[treatment]["detection_rate"] - arms[control]["detection_rate"]) if fail_rows else None
    primary = {**analysis["primary"], "difference": difference, **flip,
               "supported": bool(difference is not None and difference > 0
                                 and flip["p_value"] <= analysis["primary"]["alpha"])}
    safety_rule = analysis["safety"]
    fr_difference = (arms[treatment]["false_rejection_rate"] - arms[control]["false_rejection_rate"]) if pass_rows else None
    fr_families = [(f["false_rejection_difference"], f["host_pass_rows"]) for f in per_family if f["host_pass_rows"]]
    upper = (cluster_bootstrap_upper(fr_families, seed=safety_rule["seed"], resamples=safety_rule["resamples"])
             if fr_families else None)
    conditional = summaries[treatment]["false_rejection_rate"]
    safety = {**safety_rule, "difference": fr_difference, "upper_bound": upper,
              "treatment_conditional_frr": conditional,
              "noninferior": bool(upper is not None and upper <= safety_rule["margin"]
                                  and conditional is not None and conditional <= safety_rule["conditional_frr_cap"])}
    discordant = {}
    for name, tokens in (("detection", fail_rows), ("false_rejection", pass_rows)):
        b = sum(_rejected(records[treatment][t]) and not _rejected(records[control][t]) for t in tokens)
        c = sum(_rejected(records[control][t]) and not _rejected(records[treatment][t]) for t in tokens)
        discordant[name] = {"treatment_only": b, "control_only": c, "mcnemar_exact_p": mcnemar_exact(b, c)}
    wording = ("improved_verifier_endpoint" if primary["supported"] and safety["noninferior"] else
               "higher_detection_with_reported_false_rejection_and_uncertainty" if primary["supported"] else
               "no_supported_detection_difference")
    return {"arms": arms, "primary": primary, "safety": safety, "secondary_mcnemar": discordant,
            "per_family": per_family, "families": len(families), "registered_wording": wording}


def audit_packet(spec, meta, records, pairs_by_token):
    """Every row where h2 and default disagree on rejection, blinded: task text, bounded response and the
    rejecting rubric's FAIL checks -- no rubric identity, no host label. The key stays host-only."""
    treatment, control = spec["analysis"]["primary"]["treatment"], spec["analysis"]["primary"]["control"]
    items, key = [], {}
    for m in meta:
        a, b = records[treatment][m["token"]], records[control][m["token"]]
        if _rejected(a) == _rejected(b):
            continue
        rejecting = a if _rejected(a) else b
        item, row = pairs_by_token[m["token"]]
        response, truncated = _bounded_response(row["output"]["output"])
        item_id = digest({"audit_seed": spec["audit_seed"], "token": m["token"]})[:16]
        items.append({"item": item_id, "task": _public_view(BENCHMARK, item["task"]["public"], full=True),
                      "response": response, "response_truncated": truncated,
                      "claimed_violations": [{k: p[k] for k in ("obligation", "contract_quote", "evidence")}
                                             for p in rejecting["probes"] if p["outcome"] == "fail"]})
        key[item_id] = {"evidence_hash": m["token"], "rejecting_rubric": treatment if _rejected(a) else control,
                        "host_status": m["host_status"], "family": m["family"]}
    items.sort(key=lambda x: x["item"])
    return (seal({"protocol_hash": spec["record_hash"], "instructions": AUDIT_INSTRUCTIONS, "items": items}),
            seal({"protocol_hash": spec["record_hash"], "key": key}))


# ----------------------------------------------------------------------------- run
def _manifest(spec, panel):
    template = {k: v for k, v in spec["template"].items() if k != "panel_hash"}
    return study_manifest({**template, "panel": panel}, spec["budget"],
                          {"protocol": PROTOCOL, "protocol_hash": spec["record_hash"],
                           "study_sources": study_sources(MODULES)})


def _artifacts(root, ledger):
    """Every governed file: ledger receipts/intents/evaluations, verifier records and host-only calibration (the v10
    inventory) plus the study's own protocol, manifest, panel, markers, service, schedule and audit files."""
    files = ("protocol.json", "study.json", "panel.json", "started.json", "model_service.json", "schedule.json",
             "audit/packet.json", "host_only/audit_key.json")
    return {**learning_artifacts(ledger),
            **{name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files if (root / name).exists()}}


def verify_result(output):
    """Read-only, zero-call check of a finished study (completed or pending), against its OWN sealed protocol and
    manifest -- never a rebuild from current code: the result binds both, and the exact governed artifact inventory
    (every receipt, intent, evaluation, verifier record, calibration, schedule and audit file; a changed, missing or
    extra file fails) still matches."""
    root = safe_path(output)
    saved = read_json(root / "result.json", sealed=True)
    protocol = read_json(root / "protocol.json", sealed=True)
    value = read_json(root / "study.json", sealed=True)
    require(saved["version"] == protocol["protocol"] == PROTOCOL and saved["protocol_hash"] == protocol["record_hash"]
            and saved["study_hash"] == value["record_hash"] and value["study"]["protocol_hash"] == protocol["record_hash"]
            and value["study"]["protocol"] == PROTOCOL and saved["status"] in {"completed", "pending"}
            and saved["artifacts"] == _artifacts(root, Ledger(root, value, None)),
            "The finished study's bindings or evidence inventory changed")
    return saved


def run_study(spec, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    """Run the registered study once into ``output``; returns its sealed result (completed or pending)."""
    validate_spec(spec)
    require(digest(panel) == spec["template"]["panel_hash"], "The panel is not the registered panel")
    root = safe_path(output)
    with output_lock(root):
        if (root / "result.json").exists():
            saved = verify_result(root)
            require(saved["protocol_hash"] == spec["record_hash"], "The finished study belongs to another protocol")
            return saved
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_study_no_automatic_resume", "model_calls_submitted": 0}
        value = _manifest(spec, panel)  # rebuilt from the current (reviewed) code only before a start
        fixture = value["model"]["provider"] == "fixture"
        require(fixture == (fixture_api is not None and fixture_evaluate is not None)
                and (fixture or (fixture_api is None and fixture_evaluate is None)),
                "Fixture hooks belong to a fixture study only")
        write_json(root / "protocol.json", spec)
        write_json(root / "study.json", value)
        write_json(root / "panel.json", panel)
        final = root / "result.json"
        if not fixture:
            require(repo is not None, "A natural study needs the credential repository")
            require(backends.readiness(BENCHMARK, value["runtime"])["status"] == "ready",
                    "KOR-Bench native runtime is not ready")
        started = seal({"protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        write_json(root / "started.json", started)
        api, pending = fixture_api, None
        train = [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in set(value["train_families"])]
        pairs, unknown, records, summaries = [], 0, None, {}
        try:
            if not fixture:
                model = value["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                                reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(value))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, value, api)
            adapter = Adapter(value, root, ledger, fixture_evaluate=fixture_evaluate)
            skill = value["parent_skill"]
            # the first real solver reply is the health barrier before the concurrent rollout
            rows = adapter.evaluate_rows(train[:1], {"skill": skill}, rollout=spec["rollout"])
            rows += adapter.evaluate_rows(train[1:], {"skill": skill}, rollout=spec["rollout"])
            pairs, unknown = bind_rows(ledger, value, train, rows, skill, spec["rollout"])
            by_token = {row["output"]["evidence_hash"]: (item, row) for item, row in pairs}
            schedule = make_schedule(spec, list(by_token))
            write_json(root / "schedule.json", schedule)  # frozen before the first verifier call
            verifiers = {arm: FixedRubricVerifier(value, ledger, root, spec["rollout"], arm, spec["rubrics"][arm])
                         for arm in spec["arms"]}
            records = run_cells([tuple(cell) for cell in schedule["cells"]], verifiers, by_token,
                                value["recovery_policy"]["verifier_workers"])
            for arm in spec["arms"]:
                summaries[arm], _ = verifiers[arm].calibrate([records[arm][row["output"]["evidence_hash"]]
                                                              for _, row in pairs])
        except LearningPending as exc:
            pending = str(exc)
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, value, api)
        costs = ledger.snapshot()
        if pending is None and ledger.usage_blocks_completion(costs):
            pending = "incomplete_usage"
        if pending is None:
            intents = {p.name for p in (root / "evaluation_intents").glob("*.json")}
            if intents != {p.name for p in (root / "evaluations").glob("*.json")}:
                pending = "evaluation_without_receipt"
        outcome = {"version": PROTOCOL, "protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                   "started_at": started["started_at"],
                   "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "train_tasks": len(train), "eligible_rows": len(pairs), "source_unknown_rows": unknown,
                   "costs": costs, "usage_complete": costs["usage_complete"],
                   "unknown_cost_attempts": costs["unknown_cost_attempts"],
                   "completion_rule": spec["analysis"]["completion"], "deployment_authorized": False}
        if pending is not None:
            outcome.update(status="pending", reason=pending, artifacts=_artifacts(root, ledger))
            frozen = seal(outcome)
            write_json(final, frozen)
            return frozen
        meta = [{"token": row["output"]["evidence_hash"], "family": item["task"]["family_id"],
                 "task_id": item["task"]["task_id"], "host_status": "fail" if row["score"] == 0 else "pass"}
                for item, row in pairs]
        analysis = analyze(spec, meta, records, summaries)
        packet, key = audit_packet(spec, meta, records, {m["token"]: by_token[m["token"]] for m in meta})
        write_json(root / "audit" / "packet.json", packet)
        write_json(root / "host_only" / "audit_key.json", key)
        outcome.update(status="completed", **analysis, eligible_host_fail_rows=sum(m["host_status"] == "fail" for m in meta),
                       eligible_host_pass_rows=sum(m["host_status"] == "pass" for m in meta),
                       audit={"items": len(packet["items"]), "packet_hash": packet["record_hash"],
                              "key_hash": key["record_hash"], "status": "awaiting_independent_blinded_audit"},
                       artifacts=_artifacts(root, ledger))
        frozen = seal(outcome)
        write_json(final, frozen)
        return frozen
