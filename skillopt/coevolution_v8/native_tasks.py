"""Fresh V8 development-only native feedback tasks.

Two variants share one structural family, never independent sample identities.
Literal spot checks and separately written arithmetic/Boolean host oracles check
the reference formulas/rules. Neither references nor hidden cases are exported
by NativeAdapter.public_task(). No historical task or model artifact is loaded.
"""

from __future__ import annotations

from copy import deepcopy

from skillopt.coevolution_v6.native import NativeAdapter

VERSION = "v8-new-native-development-feedback-tasks-v1"
SHEET_FAMILIES = ("marginal-energy-waiver", "emergency-reserve-waterfall")
RULE_FAMILIES = ("specimen-release-shared-dependencies", "review-quorum-layered-permissions")


def _base(family, variant, domain, prompt, obligations):
    return {"id": f"v8-{family}-v{variant}", "domain": domain, "split": "development",
            "cluster_id": f"v8-structural-{family}", "family": family,
            "prompt": prompt, "contract": {"change_scope": "partial_update",
                "preserve_obligations": obligations, "supersedes_old_policy": False},
            "metadata": {"version": VERSION, "structural_family": family, "variant": variant,
                "group": "public_error_feedback_diagnostic", "evaluation_group": "public_error_feedback_diagnostic",
                "origin": "independently_authored_v8_development_not_historical_final",
                "historical_task_or_model_artifacts_used": False,
                "initial_task_is_public_repair_fixture_not_model_generated_failure": True,
                "oracle": "independent_host_arithmetic_or_boolean_contract_with_literal_tests",
                "independence_unit": "structural_family_not_variant_or_repeat"}}


def spreadsheet_oracle(family, inputs):
    """Independent host arithmetic, not an evaluation of reference formulas."""
    a = inputs
    if family == SHEET_FAMILIES[0]:
        remaining, widths = a["A1"], (a["A2"], a["A3"] - a["A2"], a["A1"])
        units = []
        for width in widths:
            assigned = width if remaining > width else remaining
            units.append(assigned)
            remaining -= assigned
        energy = sum(units[i] * a[f"A{i + 4}"] for i in range(3))
        waiver = 0
        if a["A8"] == 1:
            waiver = a["A9"] if a["A9"] < energy else energy
        total = a["A7"] + energy - waiver
        return {"B1": units[0], "B2": units[1], "B3": units[2], "B4": energy,
                "B5": waiver, "B6": total, "C1": 3 * total + a["A7"]}
    if family != SHEET_FAMILIES[1]:
        raise ValueError("Unknown V8 spreadsheet family")
    wanted_reserve = a["A2"] + (a["A7"] if a["A6"] == 1 else 0)
    reserve = a["A1"] if wanted_reserve > a["A1"] else wanted_reserve
    usable = a["A1"] - reserve
    remaining, assignments = usable, []
    for name in ("A3", "A4", "A5"):
        given = remaining if a[name] > remaining else a[name]
        assignments.append(given)
        remaining -= given
    return {"B1": reserve, "B2": usable, "B3": assignments[0], "B4": assignments[1],
            "B5": assignments[2], "B6": remaining,
            "B7": sum(a[k] for k in ("A3", "A4", "A5")) - sum(assignments),
            "C1": reserve + sum(assignments) + remaining}


def _sheet_cases(task, overrides):
    rows = [{"id": f"{task['id']}-{'public' if i < 2 else 'hidden'}-{i}", "overrides": deepcopy(value),
             "expected": spreadsheet_oracle(task["family"], {**task["inputs"], **value})}
            for i, value in enumerate(overrides)]
    task["public_cases"], task["hidden_cases"] = rows[:2], rows[2:]
    return NativeAdapter(task)


def _energy(variant):
    task = _base(SHEET_FAMILIES[0], variant, "spreadsheet",
        "Repair the marginal-energy workbook, not by replacing its protected downstream formulas. "
        "A1 is nonnegative workload; 0<A2<A3 are cumulative tier boundaries. Rates A4/A5/A6 and base "
        "charge A7 are nonnegative. B1/B2/B3 must partition workload into the first A2 units, the next "
        "A3-A2 units, and all excess, respectively. B4 is their rate-weighted energy, not a flat rate on "
        "all workload. A8 is exactly 0 or 1. When A8=1, B5 waives up to A9 units of ENERGY charge, "
        "capped at B4; A9 is nonnegative. When A8=0, B5 is zero. The base charge must never be waived. "
        "B6 is the total and C1 is an existing reconciliation signal. Only B1,B2,B3,B5 are editable. "
        "Preserve all other cell formulas and make the same corrected workbook valid after every legal input substitution.",
        ["Keep the protected weighted-energy and reconciliation formulas unchanged.",
         "Base charge remains payable even when all energy charge is waived."])
    t1, t2, rates, base = ((10, 30, (2, 4, 7), 5) if variant == 0 else (8, 20, (3, 6, 9), 11))
    task.update(inputs={"A1": t1 + 3, "A2": t1, "A3": t2, "A4": rates[0], "A5": rates[1],
                        "A6": rates[2], "A7": base, "A8": 0, "A9": 17},
        formulas={"B1": "=A1", "B2": "=MAX(0,A1-A2)", "B3": "=MAX(0,A1-A3)",
                  "B4": "=B1*A4+B2*A5+B3*A6", "B5": "=IF(A8==1,MIN(A9,B4+A7),0)",
                  "B6": "=A7+B4-B5", "C1": "=3*B6+A7"},
        editable_cells=["B1", "B2", "B3", "B5"], answer_cell="B6",
        reference_artifact={"formulas": {"B1": "=MIN(A1,A2)", "B2": "=MIN(MAX(0,A1-A2),A3-A2)",
                                        "B3": "=MAX(0,A1-A3)", "B5": "=IF(A8==1,MIN(A9,B4),0)"}})
    return _sheet_cases(task, [{}, {"A1": 1, "A8": 1, "A9": 1000},
        {"A1": 0, "A8": 1, "A9": 1000}, {"A1": t1}, {"A1": t1 + 1}, {"A1": t2},
        {"A1": t2 + 2}, {"A1": t2 + 9, "A8": 1, "A9": 12},
        {"A1": t2 + 1, "A8": 1, "A9": 0}, {"A1": 2, "A8": 0, "A9": 10000},
        {"A1": 9, "A2": 3, "A3": 7, "A4": 0, "A5": 2, "A6": 5, "A7": 13, "A8": 1, "A9": 100}])


def _waterfall(variant):
    task = _base(SHEET_FAMILIES[1], variant, "spreadsheet",
        "Repair a shortage-safe resource allocation workbook. All quantities are nonnegative; A6 is 0 or 1. "
        "A1 is available inventory, A2 is the normal reserve, and A7 is EXTRA reserve when emergency flag A6=1. "
        "B1 must actually withhold min(inventory, requested reserve); inventory can be below the reserve target. "
        "Protected B2 is inventory left after reserving. Allocate it in STRICT priority order: A3 demand first "
        "into B3, then A4 into B4, then A5 into B5. Every allocation is capped by both that demand and the "
        "still unallocated inventory. Do not allocate independently from the original total. B6 is leftover, "
        "B7 is total unmet demand, and C1 is the mass-balance signal. Only B1,B3,B4,B5 may change; keep "
        "all downstream formulas, including B2, unchanged. Zero demand and shortage are normal inputs.",
        ["Strict priority, nonnegative allocations, and reserve protection must hold together.",
         "Keep existing leftover, unmet-demand, and mass-balance formula bytes unchanged."])
    reserve, extra = (4, 3) if variant == 0 else (7, 5)
    task.update(inputs={"A1": 20, "A2": reserve, "A3": 8, "A4": 6, "A5": 5, "A6": 0, "A7": extra},
        formulas={"B1": "=A2", "B2": "=MAX(0,A1-B1)", "B3": "=A3", "B4": "=MIN(A4,B2)",
                  "B5": "=MIN(A5,B2)", "B6": "=MAX(0,B2-B3-B4-B5)",
                  "B7": "=A3+A4+A5-B3-B4-B5", "C1": "=B1+B3+B4+B5+B6"},
        editable_cells=["B1", "B3", "B4", "B5"], answer_cell="B7",
        reference_artifact={"formulas": {"B1": "=MIN(A1,A2+IF(A6==1,A7,0))", "B3": "=MIN(A3,B2)",
            "B4": "=MIN(A4,MAX(0,B2-B3))", "B5": "=MIN(A5,MAX(0,B2-B3-B4))"}})
    return _sheet_cases(task, [{}, {"A1": 3, "A6": 1}, {"A1": 0}, {"A1": reserve},
        {"A1": reserve + 3}, {"A1": reserve + 8}, {"A1": reserve + 12}, {"A1": 100, "A6": 1},
        {"A1": 20, "A3": 0, "A4": 0}, {"A1": 10, "A3": 0, "A4": 9, "A5": 9, "A6": 1},
        {"A1": 7, "A2": 0, "A3": 0, "A4": 0, "A5": 0, "A6": 0}])


def _vocabulary(family, variant):
    if family == RULE_FAMILIES[0]:
        primitives = ("identity_ok", "intact", "chain_logged", "screen_clear", "review_signed",
                      "urgent_waiver", "destination_ok", "storage_ok")
        derived = ("checked", "chain_ready", "reviewed", "release_ready", "dispatch_allowed", "audit_required", "archive_allowed")
    elif family == RULE_FAMILIES[1]:
        primitives = ("vote_a", "vote_b", "vote_c", "identity_ok", "policy_ok", "sealed",
                      "export_scope", "local_scope", "audit_signed")
        derived = ("quorum", "cleared", "verified", "export_allowed", "local_allowed", "trace_ready")
    else:
        raise ValueError("Unknown V8 rule family")
    suffix = "" if variant == 0 else "_x"
    return primitives, derived, {name: name + suffix for name in primitives + derived}


def rule_oracle(family, variant, facts):
    """Independent Boolean contract, not rule interpretation or closure."""
    _, _, names = _vocabulary(family, variant)
    known = set(facts)
    has = lambda key: names[key] in known  # noqa: E731
    if family == RULE_FAMILIES[0]:
        checked = has("identity_ok") and has("intact")
        chain = checked and has("chain_logged") and has("screen_clear")
        reviewed = checked and has("review_signed")
        release = chain and (reviewed or has("urgent_waiver"))
        values = {"checked": checked, "chain_ready": chain, "reviewed": reviewed, "release_ready": release,
                  "dispatch_allowed": release and has("destination_ok"),
                  "audit_required": checked and has("chain_logged"), "archive_allowed": reviewed and has("storage_ok")}
    else:
        quorum = sum(has(key) for key in ("vote_a", "vote_b", "vote_c")) >= 2
        cleared = has("identity_ok") and has("policy_ok")
        verified = quorum and cleared and has("sealed")
        values = {"quorum": quorum, "cleared": cleared, "verified": verified,
                  "export_allowed": verified and has("export_scope") and has("audit_signed"),
                  "local_allowed": quorum and cleared and has("local_scope"),
                  "trace_ready": has("identity_ok") and has("audit_signed")}
    return sorted(names[key] for key, value in values.items() if value)


def _rule_task(family, variant):
    primitives, derived, names = _vocabulary(family, variant)
    def rule(identifier, premises, conclusion):
        return {"id": identifier, "if": [names[p] for p in premises], "then": names[conclusion]}
    if family == RULE_FAMILIES[0]:
        declarations = [
            ("check_identity", ["identity_ok", "intact"], "checked"),
            ("prepare_chain", ["checked", "chain_logged", "screen_clear"], "chain_ready"),
            ("accept_review", ["checked", "review_signed"], "reviewed"),
            ("standard_path", ["chain_ready", "reviewed"], "release_ready"),
            ("urgent_path", ["chain_ready", "urgent_waiver"], "release_ready"),
            ("dispatch", ["release_ready", "destination_ok"], "dispatch_allowed"),
            ("audit", ["checked", "chain_logged"], "audit_required"),
            ("archive", ["reviewed", "storage_ok"], "archive_allowed")]
        edits = {"prepare_chain": ["checked", "chain_logged"], "standard_path": ["chain_ready"],
                 "urgent_path": ["urgent_waiver"]}
        rows = [list(primitives), ["urgent_waiver", "destination_ok"], [],
                ["identity_ok", "intact", "chain_logged", "review_signed", "destination_ok"],
                ["identity_ok", "intact", "chain_logged", "screen_clear", "destination_ok"],
                ["identity_ok", "intact", "chain_logged", "screen_clear", "urgent_waiver", "destination_ok"],
                ["identity_ok", "intact", "review_signed", "storage_ok"],
                ["identity_ok", "intact", "chain_logged"],
                ["identity_ok", "intact", "chain_logged", "screen_clear", "review_signed"],
                ["identity_ok", "chain_logged", "screen_clear", "urgent_waiver", "destination_ok"],
                ["intact", "chain_logged", "screen_clear", "review_signed", "storage_ok"]]
        meaning = ("A checked specimen requires identity_ok AND intact. chain_ready additionally requires both "
            "chain_logged AND screen_clear. reviewed requires checked AND review_signed. release_ready has TWO "
            "alternative paths: chain_ready AND reviewed, OR chain_ready AND urgent_waiver. A waiver replaces "
            "only the review requirement, never identity, intactness, chain logging or screen clearance. "
            "dispatch_allowed requires release_ready AND destination_ok. Independently, audit_required needs "
            "checked AND chain_logged (even if the screen is not clear), and archive_allowed needs reviewed "
            "AND storage_ok (no shipment/chain/screen requirement).")
    else:
        declarations = [
            ("pair_ab", ["vote_a", "vote_b"], "quorum"), ("pair_ac", ["vote_a", "vote_c"], "quorum"),
            ("pair_bc", ["vote_b", "vote_c"], "quorum"), ("clear", ["identity_ok", "policy_ok"], "cleared"),
            ("verify", ["quorum", "cleared", "sealed"], "verified"),
            ("export", ["verified", "export_scope", "audit_signed"], "export_allowed"),
            ("local", ["quorum", "cleared", "local_scope"], "local_allowed"),
            ("trace", ["identity_ok", "audit_signed"], "trace_ready")]
        edits = {"pair_bc": ["vote_b"], "verify": ["quorum", "sealed"], "export": ["verified", "export_scope"]}
        rows = [list(primitives), ["vote_b", "sealed", "export_scope"], [],
                ["vote_a", "vote_b", "sealed", "export_scope", "audit_signed"],
                ["vote_a", "vote_c", "identity_ok", "policy_ok", "sealed", "export_scope"],
                ["vote_b", "vote_c", "identity_ok", "policy_ok", "local_scope"],
                ["vote_a", "vote_b", "identity_ok", "policy_ok", "sealed", "export_scope", "audit_signed"],
                ["identity_ok", "audit_signed"], ["vote_c", "identity_ok", "policy_ok", "local_scope"],
                ["vote_b", "vote_c", "identity_ok", "sealed", "export_scope", "audit_signed"],
                ["vote_a", "vote_c", "identity_ok", "policy_ok", "local_scope"]]
        meaning = ("quorum requires ANY TWO DISTINCT votes among vote_a, vote_b and vote_c; one vote never "
            "suffices. cleared requires identity_ok AND policy_ok. verified requires quorum AND cleared AND "
            "sealed. export_allowed additionally needs export_scope AND audit_signed. Independent local_allowed "
            "requires quorum AND cleared AND local_scope; do NOT require sealed/export_scope/audit_signed for "
            "local use. trace_ready requires identity_ok AND audit_signed even when no quorum or policy clearance exists.")
    if variant:
        meaning += " Every symbolic name in this description denotes its suffixed '_x' version in the actual vocabulary and rules."
    prompt = ("Repair this positive-rule policy to the following exact contract. " + meaning
        + " Initial facts are subsets of the declared primitive facts only: " + ", ".join(names[p] for p in primitives)
        + ". Evaluate to a fixed point; no negative rules, priorities, implicit rules, or code. Return ALL original rule IDs. "
        "Only the listed editable_rule_ids may change; protected rules and their premise ordering must remain byte-equivalent. "
        "All requested intermediate as well as terminal facts in answer_facts are checked.")
    task = _base(family, variant, "rule_reasoning", prompt,
        ["Preserve independent secondary outputs when tightening the main policy.",
         "Keep protected rule IDs, premises, and conclusions unchanged."])
    reference = [rule(*row) for row in declarations]
    initial = [rule(identifier, edits.get(identifier, premises), conclusion) for identifier, premises, conclusion in declarations]
    task.update(rules=initial, editable_rule_ids=list(edits), vocabulary=[names[x] for x in primitives + derived],
        initial_facts=[names[p] for p in rows[0]], answer_facts=[names[p] for p in derived],
        reference_artifact={"rules": reference})
    cases = [{"id": f"{task['id']}-{'public' if i < 2 else 'hidden'}-{i}", "facts": [names[p] for p in row],
              "expected": rule_oracle(family, variant, [names[p] for p in row])} for i, row in enumerate(rows)]
    task["public_cases"], task["hidden_cases"] = cases[:2], cases[2:]
    return NativeAdapter(task)


def development_native_tasks() -> list[NativeAdapter]:
    """Eight fresh development instances in exactly four structural families."""
    return [builder(variant) for builder in (_energy, _waterfall) for variant in range(2)] + [
        _rule_task(family, variant) for family in RULE_FAMILIES for variant in range(2)]
