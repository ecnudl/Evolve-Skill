"""Pure V17 evidence views, an empirical scope gate, and clustered analysis.

No model, filesystem, execution, or benchmark access occurs here. Upstream
callers must authenticate/close the receipts before supplying normalized facts.
This module checks schema and partition boundaries, not receipt authenticity.
The gate is a finite-panel heuristic, NEVER a statistical safety certificate.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from statistics import mean

VERSION = "v17-cross-domain-feedback-core-v1"
BOOTSTRAP_SEED = 2026091701
BOOTSTRAP_SAMPLES = 1000
CELLS = {"same_mechanism", "near_miss"}
GATE_ARMS = {"no_skill", "parent", "candidate"}
HOST_ONLY = {"mechanism_cell", "mechanism_label", "structural_family", "cluster_id"}


def _json_copy(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return json.loads(encoded)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("Only finite, serializable JSON facts are supported") from error


def _text(value):
    return type(value) is str and bool(value.strip())


def feedback_views(records, mode):
    """Project the SAME closed development facts as raw or grouped JSON.

    Each input record must contain phase='development', task_id, domain and
    role (no_skill/current). Other JSON facts are retained without invention.
    Top-level mechanism_cell/mechanism_label/structural_family/cluster_id and
    cell are host-only labels and removed in BOTH conditions. Explicit public
    contracts and executed diagnostics are retained verbatim. Callers must not
    insert reference code, hidden test bodies, or final observations as facts.

    Raw result: {mode, records}; structured: {mode, groups:[{domain, tasks:
    [{task_id, roles:[{role, records:[{position, fact}]}]}]}]}. Positions make
    flatten_feedback() an exact inverse, even for interleaved histories.
    Grouping supplies no new facts, suggested repair, mechanism label or gold.
    """
    if mode not in {"raw", "structured"}:
        raise ValueError("Feedback mode must be raw or structured")
    if type(records) is not list or not records:
        raise ValueError("A nonempty list of closed development records is required")
    facts = _json_copy(records)
    for record in facts:
        if (type(record) is not dict or record.get("phase") != "development"
                or not _text(record.get("task_id")) or not _text(record.get("domain"))
                or record.get("role") not in {"no_skill", "current"}):
            raise ValueError("Only identified, paired-role development facts may reach learning")
        for name in HOST_ONLY | {"cell"}:
            record.pop(name, None)
    if mode == "raw":
        return {"mode": mode, "records": facts}
    indexed = {}
    for position, record in enumerate(facts):
        tasks = indexed.setdefault(record["domain"], {})
        roles = tasks.setdefault(record["task_id"], {})
        roles.setdefault(record["role"], []).append({"position": position, "fact": record})
    groups = [{"domain": domain, "tasks": [
        {"task_id": task, "roles": [{"role": role, "records": values}
                                     for role, values in roles.items()]}
        for task, roles in tasks.items()]} for domain, tasks in indexed.items()]
    return {"mode": mode, "groups": groups}


def flatten_feedback(view):
    """Recover original-order projected facts; reject inconsistent grouping."""
    view = _json_copy(view)
    if type(view) is not dict:
        raise ValueError("Feedback view must be an object")
    if view.get("mode") == "raw" and set(view) == {"mode", "records"}:
        return feedback_views(view["records"], "raw")["records"]
    if view.get("mode") != "structured" or set(view) != {"mode", "groups"}:
        raise ValueError("Unrecognized feedback view")
    positions = {}
    try:
        for group in view["groups"]:
            for task in group["tasks"]:
                for role in task["roles"]:
                    for item in role["records"]:
                        position, fact = item["position"], item["fact"]
                        if (type(position) is not int or position < 0 or position in positions
                                or fact["domain"] != group["domain"]
                                or fact["task_id"] != task["task_id"]
                                or fact["role"] != role["role"]):
                            raise ValueError("Group identity or original position does not match its fact")
                        positions[position] = fact
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed structured feedback") from error
    if set(positions) != set(range(len(positions))):
        raise ValueError("Feedback positions are incomplete")
    return feedback_views([positions[i] for i in range(len(positions))], "raw")["records"]


def _grid(rows, phase, *, fixed_arms=None, require_family=False,
          expected_tasks=None, expected_arms=None, expected_histories=None):
    if type(rows) is not list or not rows:
        raise ValueError("A nonempty materialized observation list is required")
    values = _json_copy(rows)
    indexed, metadata = {}, {}
    for row in values:
        if (type(row) is not dict or row.get("phase") != phase
                or not all(_text(row.get(k)) for k in ("task_id", "domain", "arm"))
                or row.get("cell") not in CELLS
                or type(row.get("history")) is not int or row["history"] < 0
                or type(row.get("oracle_available")) is not bool
                or (row.get("artifact_valid") is not None and type(row["artifact_valid"]) is not bool)
                or (row.get("passed") is not None and type(row["passed"]) is not bool)
                or not {"artifact_valid", "passed"}.issubset(row)):
            raise ValueError("Unsupported task/history/arm or typed outcome schema")
        if row["passed"] is True and not (row["oracle_available"] and row["artifact_valid"] is True):
            raise ValueError("Success requires an available oracle and valid delivered artifact")
        if row["oracle_available"] and row["artifact_valid"] is True and row["passed"] is None:
            raise ValueError("An executed valid artifact requires its actual boolean outcome")
        if require_family and not _text(row.get("structural_family")):
            raise ValueError("Final analysis requires explicit structural-family identities")
        fields = ("domain", "cell", "structural_family") if require_family else ("domain", "cell")
        identity = {name: row[name] for name in fields}
        if metadata.setdefault(row["task_id"], identity) != identity:
            raise ValueError("Task metadata changed across arms or histories")
        key = row["task_id"], row["history"], row["arm"]
        if key in indexed:
            raise ValueError("Duplicate task/history/arm observation")
        indexed[key] = row
    tasks = set(metadata)
    arms = {key[2] for key in indexed}
    histories = {key[1] for key in indexed}
    if fixed_arms is not None and arms != set(fixed_arms):
        raise ValueError("Gate needs exactly no_skill, parent and candidate observations")
    if "no_skill" not in arms:
        raise ValueError("No-Skill anchor is mandatory")
    if expected_tasks is not None:
        if type(expected_tasks) not in (list, tuple) or len(expected_tasks) != len(set(expected_tasks)):
            raise ValueError("Frozen task manifest must contain unique identifiers")
        if tasks != set(expected_tasks):
            raise ValueError("Observed tasks differ from frozen task manifest")
    if expected_arms is not None and arms != set(expected_arms):
        raise ValueError("Observed arms differ from frozen intervention manifest")
    if expected_histories is not None and histories != set(expected_histories):
        raise ValueError("Observed histories differ from frozen history manifest")
    if set(indexed) != {(task, history, arm) for task in tasks for history in histories for arm in arms}:
        raise ValueError("Incomplete task x history x arm grid; retain explicit unknown attempts")
    return values, indexed, metadata, sorted(histories), sorted(arms)


def _paired(rows, indexed, arm, reference):
    wins = losses = ties = unknown = anchor_successes = 0
    for row in rows:
        if row["arm"] != arm:
            continue
        anchor = indexed[row["task_id"], row["history"], reference]
        lhs, rhs = int(row["passed"] is True), int(anchor["passed"] is True)
        wins += lhs > rhs
        losses += lhs < rhs
        ties += lhs == rhs
        anchor_successes += rhs
        unknown += not row["oracle_available"] or not anchor["oracle_available"]
    total = wins + losses + ties
    return {"wins": wins, "losses": losses, "ties": ties, "total": total,
            "unknown_pairs": unknown, "delta": (wins - losses) / total if total else None,
            "loss_rate": losses / total if total else None, "anchor_successes": anchor_successes,
            "loss_rate_given_anchor_success": losses / anchor_successes if anchor_successes else None}


def empirical_gate(rows, *, expected_tasks=None, expected_histories=None):
    """Gate ONE history's candidate on independent phase='calibration' rows.

    Required fields: phase, task_id, history (one history only), domain, cell
    ('same_mechanism'/'near_miss'), arm (no_skill/parent/candidate),
    artifact_valid (bool/None), oracle_available (bool), passed (bool/None).
    All four Coding/Spreadsheet x mechanism/near-miss cells are required.
    Repeated history evidence must never approve a different history's Skill.

    Cross-domain commit: no observed candidate losses against EITHER parent or
    base anywhere, plus >=1 Spreadsheet same-mechanism win against EACH.
    Local commit: no losses on Coding against either anchor, with >=1 source
    same-mechanism win against EACH; use candidate on the entire Coding domain.
    Otherwise retain parent only as learning lineage (restrict_parent), but
    deploy base, never assume the parent is safe. Observed harm without a local
    commit or any unknown outcome rejects. Malformed/incomplete panels raise.
    Near-miss cells constrain admission but NEVER route individual tasks. The
    trusted environment's domain selects candidate/base. A cross-domain commit
    covers only Coding and Spreadsheet, not unseen Rule. These finite-panel
    rules do not establish population non-inferiority.
    """
    values, indexed, metadata, histories, _ = _grid(
        rows, "calibration", fixed_arms=GATE_ARMS, expected_tasks=expected_tasks,
        expected_histories=expected_histories)
    if len(histories) != 1:
        raise ValueError("Gate each frozen history candidate separately, never pool different Skills")
    cells = {(row["domain"], row["cell"]) for row in values}
    required = {(domain, cell) for domain in ("coding", "spreadsheet") for cell in CELLS}
    if cells != required:
        raise ValueError("Gate requires all and only Coding/Spreadsheet mechanism and near-miss cells")
    support = {}
    for domain, cell in sorted(cells):
        selected = [row for row in values if row["domain"] == domain and row["cell"] == cell]
        support.setdefault(domain, {})[cell] = {
            anchor: _paired(selected, indexed, "candidate", anchor)
            for anchor in ("no_skill", "parent")}
    unknown = any(not row["oracle_available"] or row["artifact_valid"] is None
                  or row["passed"] is None for row in values)
    all_counts = [item for cells_ in support.values() for anchors in cells_.values() for item in anchors.values()]
    code_counts = [item for anchors in support["coding"].values() for item in anchors.values()]
    transfer = support["spreadsheet"]["same_mechanism"]
    source = support["coding"]["same_mechanism"]
    cross_ok = not unknown and all(row["losses"] == 0 for row in all_counts) and all(
        row["wins"] > 0 for row in transfer.values())
    local_ok = not unknown and all(row["losses"] == 0 for row in code_counts) and all(
        row["wins"] > 0 for row in source.values())
    if cross_ok:
        decision, scope, reason = "cross_domain_commit", "cross_domain", "paired_transfer_gain_without_observed_cell_losses"
    elif local_ok:
        decision, scope, reason = "local_commit", "local", "source_gain_only_or_cross_domain_conditions_not_met"
    elif unknown:
        decision, scope, reason = "reject", "no_skill", "unknown_evidence_cannot_approve_scope"
    elif any(row["losses"] > 0 for row in all_counts):
        decision, scope, reason = "reject", "no_skill", "observed_losses_without_supported_local_gain"
    else:
        decision, scope, reason = "restrict_parent", "no_skill", "insufficient_positive_transfer_evidence"
    deployed_domains = (["coding", "spreadsheet"] if scope == "cross_domain" else
                        ["coding"] if scope == "local" else [])
    deployment = {domain: "candidate" if domain in deployed_domains else "no_skill"
                  for domain in ("coding", "spreadsheet", "rule_reasoning")}
    return {"version": VERSION, "decision": decision, "scope": scope, "reason": reason,
            "history": histories[0], "support": support, "unique_tasks": len(metadata),
            "unknown_evidence": unknown, "deployment_mapping": deployment,
            "deployment_domains": deployed_domains,
            "unseen_domain_default": "no_skill", "parent_retained_as_learning_lineage": decision == "restrict_parent",
            "statistical_safety_claim": False,
            "routing": "trusted_environment_domain_only_no_mechanism_cell_routing"}


def _counts(rows):
    success = semantic = delivery = delivery_unknown = execution_unknown = 0
    for row in rows:
        if row["passed"] is True:
            success += 1
        elif row["artifact_valid"] is False:
            delivery += 1
        elif row["artifact_valid"] is None:
            delivery_unknown += 1
        elif not row["oracle_available"]:
            execution_unknown += 1
        else:
            semantic += 1
    return {"attempts": len(rows), "successes": success, "all_attempt_success_rate": success / len(rows),
            "semantic_failures": semantic, "delivery_failures": delivery,
            "delivery_unknown": delivery_unknown, "execution_unknown": execution_unknown}


def _interval(values):
    ordered = sorted(values)
    def quantile(p):
        position = (len(ordered) - 1) * p
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])
    return [quantile(0.025), quantile(0.975)]


def analyze(rows, *, expected_tasks=None, expected_arms=None, expected_histories=None):
    """Analyze complete phase='final' raw-Skill records, with fixed 1000 draws.

    Same schema as empirical_gate plus nonempty structural_family. Any named
    arms are allowed provided no_skill exists. Unknown/delivery failures remain
    in the all-attempt denominator. Paired wins/losses are descriptive positions,
    not independent trials. Average histories within task, tasks within family,
    families within domain, then equal-weight domains. Bootstrap families within
    each domain, retaining ALL their tasks/histories together. No history is
    counted as a new family. Conditional CIs do not capture new training-history
    uncertainty. Optional frozen manifests detect an entirely omitted task/arm/
    history; without them only completeness of the observed Cartesian grid can
    be checked. No data selection, filtering of failed attempts or p-values.
    """
    values, indexed, metadata, histories, arms = _grid(
        rows, "final", require_family=True, expected_tasks=expected_tasks,
        expected_arms=expected_arms, expected_histories=expected_histories)
    family_tasks = defaultdict(lambda: defaultdict(list))
    for task, info in metadata.items():
        family_tasks[info["domain"]][info["structural_family"]].append(task)
    domains = sorted(family_tasks)
    family_values = {}
    for arm in arms:
        family_values[arm] = {domain: {family: mean([
            mean([int(indexed[task, h, arm]["passed"] is True) for h in histories]) for task in tasks])
            for family, tasks in sorted(family_tasks[domain].items())} for domain in domains}
    by_arm = {}
    for arm in arms:
        domain_summary = {}
        for domain in domains:
            selected = [row for row in values if row["arm"] == arm and row["domain"] == domain]
            domain_summary[domain] = {**_counts(selected),
                "family_weighted_success_rate": mean(family_values[arm][domain].values()),
                "unique_tasks": sum(len(tasks) for tasks in family_tasks[domain].values()),
                "structural_families": len(family_tasks[domain]),
                "vs_no_skill": _paired(selected, indexed, arm, "no_skill")}
        rates = [item["family_weighted_success_rate"] for item in domain_summary.values()]
        by_arm[arm] = {**_counts([row for row in values if row["arm"] == arm]),
            "by_domain": domain_summary, "macro_success_rate": mean(rates),
            "worst_domain_success_rate": min(rates)}
    rng = random.Random(BOOTSTRAP_SEED)
    plan = [{domain: [rng.choice(sorted(family_tasks[domain])) for _ in family_tasks[domain]]
             for domain in domains} for _ in range(BOOTSTRAP_SAMPLES)]
    comparisons = {}
    contrasts = [(arm, "no_skill") for arm in arms if arm != "no_skill"]
    if "parent" in arms:
        contrasts += [(arm, "parent") for arm in arms if arm not in {"parent", "no_skill"}]
    for contrast in (("cross_raw_feedback", "local_feedback"),
                     ("cross_structured_feedback", "cross_raw_feedback")):
        if all(arm in arms for arm in contrast):
            contrasts.append(contrast)
    for arm, reference in contrasts:
        observed = {domain: mean(family_values[arm][domain].values())
                    - mean(family_values[reference][domain].values()) for domain in domains}
        draws = [{domain: mean([family_values[arm][domain][family]
                               - family_values[reference][domain][family]
                               for family in draw[domain]]) for domain in domains} for draw in plan]
        comparisons[arm + "_vs_" + reference] = {
            "by_domain": {domain: {"delta": observed[domain],
                "ci95": _interval([draw[domain] for draw in draws])} for domain in domains},
            "macro_delta": mean(observed.values()),
            "macro_delta_ci95": _interval([mean(draw.values()) for draw in draws]),
            "worst_domain_delta": min(observed.values()),
            "worst_domain_delta_ci95": _interval([min(draw.values()) for draw in draws]),
            "paired": _paired(values, indexed, arm, reference)}
    return {"version": VERSION, "phase": "final", "arms": by_arm, "comparisons": comparisons,
            "unique_tasks": len(metadata), "histories": histories,
            "complete_grid_positions": len(values), "domains": domains,
            "bootstrap": {"samples": BOOTSTRAP_SAMPLES, "seed": BOOTSTRAP_SEED,
                "unit": "structural_family_with_all_tasks_and_histories",
                "stratified_by_domain": True, "histories_resampled_as_independent_tasks": False,
                "conditional_on_observed_histories": True, "multiple_comparison_adjustment": False},
            "manifest_checked": all(x is not None for x in (expected_tasks, expected_arms, expected_histories)),
            "statistical_safety_claim": False}
