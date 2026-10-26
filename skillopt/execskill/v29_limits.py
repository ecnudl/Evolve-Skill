"""Audited-note reservation formulas, used only by the two v2.9 profiles.

Caps bound ledger tokens, not dollars. They deliberately assume no request reuse.
"""
from __future__ import annotations

import math

from skillopt.coevo5.ledger import reservation

JUDGE_MAX_TOKENS = 8_192
CONFIRM_ITEMS = 40
FORMAT_RETRIES = 1
AUDIT1_PASSES = 2
EXTRA_SITUATIONS = 4
TEMPLATE_LIMIT = 60
JUDGE_ROLES = ("audit_g", "audit_d")


def prompts_per_audit(bench):
    situations, batch = (12, 4) if bench == "zebralogic" else (8 * 3, 6)
    return 1 + math.ceil((situations + EXTRA_SITUATIONS) / batch)


def judge_calls(p, bench):
    # Every proposed change can be checked before and after its one audit fix;
    # every final procedure can receive an independent audit 2.
    audits = p.TRAIN_ROUNDS * p.MAX_CHANGES * AUDIT1_PASSES + p.MAX_PROCEDURES
    return audits * prompts_per_audit(bench) * (1 + FORMAT_RETRIES)


def extend_profiles(p):
    """Mutate only freshly copied v2.9 entries, leaving all parent tables intact."""
    for config in (p.ZEBRA_PC_V7, p.ALFWORLD_V4):
        bench = p.CONFIGURATIONS[config]["order"][0]
        calls = judge_calls(p, bench)
        # Full frozen role-input allowance; actual wider prompts remain subject
        # to the normal ledger reservation guard and S-E6 measurements.
        per_call = reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)
        judge_cap = (calls + 1) * per_call
        roles = p.CONFIG_ROLE_CAPS[config]
        old_total = p.CONFIG_GLM_CAP[config]
        audit_fix_reserve = p.TRAIN_ROUNDS * p.MAX_CHANGES * (
            reservation(p.ROLE_INPUT_BYTES, p.ENGINEER_MAX_TOKENS[config])
            + reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS))
        roles["engineer"] += audit_fix_reserve
        roles.update({role: judge_cap for role in JUDGE_ROLES})
        p.CONFIG_GLM_CAP[config] = old_total + sum(roles[role] for role in JUDGE_ROLES) + (
            audit_fix_reserve)
        count = p.TRAIN_ROUNDS * 2 * CONFIRM_ITEMS
        p.CONFIG_SCHEDULE_CELLS[config][bench]["confirm"] = {bench: (0, count)}
        amount = math.ceil(p.MAIN_CAP_FACTOR * (count * p.CELL_ANCHORS[bench][1]
                          * p.PROCEDURE_ARM_FACTOR[1] + p.MAIN_RESERVATIONS * p.READ_RESERVATION))
        cap = math.ceil(amount / 100_000) * 100_000
        p.CONFIG_STEP_CAPS[config][bench]["confirm"] = cap
        plan = p.CONFIGURATIONS[config]
        previous_redo = plan["redo_reserve"]
        plan["redo_reserve"] = max(previous_redo, cap)
        plan["solver_cap"] += cap + plan["redo_reserve"] - previous_redo


def identity(p, config):
    bench = p.CONFIGURATIONS[config]["order"][0]
    out = {"judge_max_tokens": JUDGE_MAX_TOKENS, "format_retries": FORMAT_RETRIES,
            "audit1_passes": AUDIT1_PASSES, "templates": TEMPLATE_LIMIT,
            "prompts_per_audit": prompts_per_audit(bench), "calls_per_judge": judge_calls(p, bench),
            "confirm_items": CONFIRM_ITEMS, "confirm_cells": p.TRAIN_ROUNDS * 2 * CONFIRM_ITEMS,
            "request_bytes_allowance": p.ROLE_INPUT_BYTES,
            "judge_reservation": reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)}
    if p.is_v291(config):
        out["fault_feedback"] = {"fault_repairs": p.FAULT_REPAIRS, "patience": p.train_patience(config),
            "single_call_budget": p.ENGINEER_CALL_BUDGETS[config],
            "train_call_budget": p.TRAIN_ENGINEER_CALL_BUDGETS[config],
            "role_calls": v291_role_calls(p, config), "engineer_system_bytes_allowance": V291_ENGINEER_SYSTEM_BYTES,
            "engineer_cap": v291_engineer_cap(p, config),
            "selftest_cells": p.CONFIG_SCHEDULE_CELLS[config][bench]["selftest"][bench][1]}
    return out


# Includes the full proposal/fix system text in addition to the payload ceiling.
# Asserted against the actual v2.9.1 prompts in the offline profile tests.
V291_ENGINEER_SYSTEM_BYTES = 16_000


def v291_role_calls(p, config):
    """Six rounds at the full proposal/fix/format budgets, without request reuse."""
    return {
        "engineer": p.TRAIN_ROUNDS * (p.TRAIN_ENGINEER_CALL_BUDGETS[config] + p.TRAIN_ANALYST_CALLS),
        "leakage": p.TRAIN_ROUNDS * p.MAX_CHANGES * (1 + p.TRAIN_FIXES + p.FAULT_REPAIRS + 1),
        "describer": min(p.MAX_PROCEDURES, p.TRAIN_ROUNDS * p.MAX_CHANGES),
    }


def v291_engineer_cap(p, config):
    calls = v291_role_calls(p, config)
    engineer = reservation(p.ROLE_INPUT_BYTES + V291_ENGINEER_SYSTEM_BYTES, p.ENGINEER_MAX_TOKENS[config])
    ordinary = reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS)
    return calls["engineer"] * engineer + (calls["leakage"] + calls["describer"]) * ordinary + engineer


def extend_v291_profiles(p):
    """Reserve six full rounds on child profiles; inherited parent bytes stay fixed."""
    for config in (p.ZEBRA_PC_V8, p.ALFWORLD_V5):
        bench = p.CONFIGURATIONS[config]["order"][0]
        old_role = p.CONFIG_ROLE_CAPS[config]["engineer"]
        p.CONFIG_ROLE_CAPS[config]["engineer"] = max(old_role, v291_engineer_cap(p, config))
        p.CONFIG_GLM_CAP[config] += p.CONFIG_ROLE_CAPS[config]["engineer"] - old_role
        # ALF's selected forty games may appear in every train round, followed by
        # the two conservative final self-test passes. Zebra has no generated set.
        selected = p.ALFWORLD_SELECTED_MAX if p.is_alfworld(config) else 0
        count = (p.TRAIN_ROUNDS * 2 * (p.SLICES[bench]["run"][0] * p.SLICES[bench]["run"][1] + selected)
                 + p.SELFTEST_PASSES * 2 * selected)
        cells = p.CONFIG_SCHEDULE_CELLS[config][bench]["selftest"]
        cards, inherited = cells.get(bench, (0, 0))
        cells[bench] = (cards, max(inherited, count))
        reserve = p.ALFWORLD_V1_RESERVATION if p.is_alfworld(config) else p.READ_RESERVATION
        amount = math.ceil(p.MAIN_CAP_FACTOR * (
            sum(p.CELL_ANCHORS[b][1] * (card + p.PROCEDURE_ARM_FACTOR[1] * proc)
                for b, (card, proc) in cells.items()) + p.MAIN_RESERVATIONS * reserve))
        cap = math.ceil(amount / 100_000) * 100_000
        previous = p.CONFIG_STEP_CAPS[config][bench]["selftest"]
        p.CONFIG_STEP_CAPS[config][bench]["selftest"] = max(previous, cap)
        plan = p.CONFIGURATIONS[config]
        old_redo = plan["redo_reserve"]
        plan["redo_reserve"] = max(old_redo, p.CONFIG_STEP_CAPS[config][bench]["selftest"])
        plan["solver_cap"] += max(previous, cap) - previous + plan["redo_reserve"] - old_redo
