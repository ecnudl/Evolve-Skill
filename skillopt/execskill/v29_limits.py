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


def judge_calls(p, bench, configuration=None):
    # Every proposed change can be checked before and after its one audit fix;
    # every final procedure can receive an independent audit 2.
    audits = p.train_rounds(configuration) * p.MAX_CHANGES * AUDIT1_PASSES + p.MAX_PROCEDURES
    return audits * prompts_per_audit(bench) * (1 + FORMAT_RETRIES)


def extend_profiles(p):
    """Mutate only freshly copied v2.9 entries, leaving all parent tables intact."""
    for config in (p.ZEBRA_PC_V7, p.ALFWORLD_V4):
        bench = p.CONFIGURATIONS[config]["order"][0]
        calls = judge_calls(p, bench, config)
        # Full frozen role-input allowance; actual wider prompts remain subject
        # to the normal ledger reservation guard and S-E6 measurements.
        per_call = reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)
        judge_cap = (calls + 1) * per_call
        roles = p.CONFIG_ROLE_CAPS[config]
        old_total = p.CONFIG_GLM_CAP[config]
        audit_fix_reserve = p.train_rounds(config) * p.MAX_CHANGES * (
            reservation(p.ROLE_INPUT_BYTES, p.ENGINEER_MAX_TOKENS[config])
            + reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS))
        roles["engineer"] += audit_fix_reserve
        roles.update({role: judge_cap for role in JUDGE_ROLES})
        p.CONFIG_GLM_CAP[config] = old_total + sum(roles[role] for role in JUDGE_ROLES) + (
            audit_fix_reserve)
        count = p.train_rounds(config) * 2 * CONFIRM_ITEMS
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
            "prompts_per_audit": prompts_per_audit(bench), "calls_per_judge": judge_calls(p, bench, config),
            "confirm_items": CONFIRM_ITEMS, "confirm_cells": p.train_rounds(config) * 2 * CONFIRM_ITEMS,
            "request_bytes_allowance": p.ROLE_INPUT_BYTES,
            "judge_reservation": reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)}
    if p.is_v291(config):
        out["fault_feedback"] = {"fault_repairs": p.FAULT_REPAIRS, "patience": p.train_patience(config),
            "single_call_budget": p.ENGINEER_CALL_BUDGETS[config],
            "train_call_budget": p.TRAIN_ENGINEER_CALL_BUDGETS[config],
            "role_calls": v291_role_calls(p, config), "engineer_system_bytes_allowance": V291_ENGINEER_SYSTEM_BYTES,
            "engineer_cap": v291_engineer_cap(p, config),
            "selftest_cells": p.CONFIG_SCHEDULE_CELLS[config][bench]["selftest"][bench][1]}
    if p.is_v215(config):
        out['fault_feedback']['engineer_payload_bytes_allowance'] = engineer_input_bytes(p, config)
        out['fault_feedback']['diagnostics_bytes_allowance'] = engineer_input_bytes(p, config) - p.ROLE_INPUT_BYTES
    return out


# Includes the full proposal/fix system text in addition to the payload ceiling.
# Asserted against the actual v2.9.1 prompts in the offline profile tests.
V291_ENGINEER_SYSTEM_BYTES = 16_000


def v291_role_calls(p, config):
    """Configured rounds at the full per-round budgets, without request reuse."""
    return {
        "engineer": p.train_rounds(config) * (p.TRAIN_ENGINEER_CALL_BUDGETS[config] + p.TRAIN_ANALYST_CALLS),
        "leakage": p.train_rounds(config) * p.MAX_CHANGES * (1 + p.TRAIN_FIXES + p.FAULT_REPAIRS + 1),
        "describer": min(p.MAX_PROCEDURES, p.train_rounds(config) * p.MAX_CHANGES),
    }


def engineer_input_bytes(p, config):
    """Preserve the complete legacy payload; only v2.15 adds a bounded envelope."""
    if p.is_v215(config):
        from .diagnostics import INPUT_BYTES
        return p.ROLE_INPUT_BYTES + INPUT_BYTES
    return p.ROLE_INPUT_BYTES


def v291_engineer_cap(p, config):
    calls = v291_role_calls(p, config)
    engineer = reservation(engineer_input_bytes(p, config) + V291_ENGINEER_SYSTEM_BYTES, p.ENGINEER_MAX_TOKENS[config])
    ordinary = reservation(p.ROLE_INPUT_BYTES, p.ROLE_MAX_TOKENS)
    return calls["engineer"] * engineer + (calls["leakage"] + calls["describer"]) * ordinary + engineer


def extend_v291_profiles(p, configurations=None):
    """Reserve full configured rounds on children; inherited parent bytes stay fixed."""
    for config in ((p.ZEBRA_PC_V8, p.ALFWORLD_V5) if configurations is None else configurations):
        bench = p.CONFIGURATIONS[config]["order"][0]
        old_role = p.CONFIG_ROLE_CAPS[config]["engineer"]
        p.CONFIG_ROLE_CAPS[config]["engineer"] = max(old_role, v291_engineer_cap(p, config))
        p.CONFIG_GLM_CAP[config] += p.CONFIG_ROLE_CAPS[config]["engineer"] - old_role
        # ALF's selected forty games may appear in every train round, followed by
        # the two conservative final self-test passes. Zebra has no generated set.
        selected = p.ALFWORLD_SELECTED_MAX if p.is_alfworld(config) else 0
        count = (p.train_rounds(config) * 2 * (p.SLICES[bench]["run"][0] * p.SLICES[bench]["run"][1] + selected)
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


def extend_v295_profiles(p):
    """Recompute the Zebra v12 round-dependent terms using the inherited formulas.

    Per-round limits, read/accept/examiner scopes and all parent objects stay
    unchanged. The ALF child remains its exact six-round parent budget.
    """
    config = p.ZEBRA_PC_V12
    bench = p.CONFIGURATIONS[config]["order"][0]
    extend_v291_profiles(p, (config,))
    roles = p.CONFIG_ROLE_CAPS[config]
    judge_cap = (judge_calls(p, bench, config) + 1) * reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)
    for role in JUDGE_ROLES:
        p.CONFIG_GLM_CAP[config] += judge_cap - roles[role]
        roles[role] = judge_cap
    count = p.train_rounds(config) * 2 * CONFIRM_ITEMS
    p.CONFIG_SCHEDULE_CELLS[config][bench]["confirm"] = {bench: (0, count)}
    amount = math.ceil(p.MAIN_CAP_FACTOR * (count * p.CELL_ANCHORS[bench][1]
                      * p.PROCEDURE_ARM_FACTOR[1] + p.MAIN_RESERVATIONS * p.READ_RESERVATION))
    cap = math.ceil(amount / 100_000) * 100_000
    previous = p.CONFIG_STEP_CAPS[config][bench]["confirm"]
    p.CONFIG_STEP_CAPS[config][bench]["confirm"] = cap
    plan = p.CONFIGURATIONS[config]
    old_redo = plan["redo_reserve"]
    plan["redo_reserve"] = max(old_redo, cap)
    plan["solver_cap"] += cap - previous + plan["redo_reserve"] - old_redo


def extend_v212_profiles(p):
    """Reprice the v12 child at six rounds, independent S/C and F/C-only read.

    Use v12's delta accounting (including its inherited solver headroom),
    but recompute shrinking terms instead of its expansion-only maxima.
    """
    config, bench = p.ZEBRA_PC_V13, p.ZEBRA
    roles = p.CONFIG_ROLE_CAPS[config]
    before_roles = sum(roles.values())
    roles['engineer'] = v291_engineer_cap(p, config)
    for role in JUDGE_ROLES:
        roles[role] = (judge_calls(p, bench, config) + 1) * reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)
    p.CONFIG_GLM_CAP[config] += sum(roles.values()) - before_roles
    schedule = p.CONFIG_SCHEDULE_CELLS[config][bench]
    n, runs = p.SLICES[bench]['run']
    schedule['selftest'] = {bench: (0, p.train_rounds(config) * 2 * n * runs)}
    schedule['confirm'] = {bench: (0, p.train_rounds(config) * 2 * CONFIRM_ITEMS)}
    card, proc = schedule['accept'][bench]
    n, runs = p.SLICES[bench]['accept']
    schedule['accept'][bench] = (card, proc - n * runs)  # remove P_y; retain both acceptance twins
    caps = p.CONFIG_STEP_CAPS[config][bench]
    previous_steps = sum(caps.values())

    def cap(cells, rounding):
        return p.legacy._round_up(p.MAIN_CAP_FACTOR * (
            sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * q)
                for b, (c, q) in cells.items())
            + p.MAIN_RESERVATIONS * p.READ_RESERVATION), rounding)

    for kind in ('selftest', 'confirm', 'accept'):
        caps[kind] = cap(schedule[kind], 100_000)
    plan = p.CONFIGURATIONS[config]
    before_read, before_redo = plan['test_read_cap'], plan['redo_reserve']
    plan['test_read_cap'] = cap(p.TEST_READ_CELLS[config], p.MILLION)
    plan['redo_reserve'] = max(caps.values())  # Zebra acceptance is one block.
    plan['solver_cap'] += (sum(caps.values()) - previous_steps
                           + plan['test_read_cap'] - before_read + plan['redo_reserve'] - before_redo)
