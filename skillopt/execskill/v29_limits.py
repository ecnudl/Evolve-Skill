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
    return {"judge_max_tokens": JUDGE_MAX_TOKENS, "format_retries": FORMAT_RETRIES,
            "audit1_passes": AUDIT1_PASSES, "templates": TEMPLATE_LIMIT,
            "prompts_per_audit": prompts_per_audit(bench), "calls_per_judge": judge_calls(p, bench),
            "confirm_items": CONFIRM_ITEMS, "confirm_cells": p.TRAIN_ROUNDS * 2 * CONFIRM_ITEMS,
            "request_bytes_allowance": p.ROLE_INPUT_BYTES,
            "judge_reservation": reservation(p.ROLE_INPUT_BYTES, JUDGE_MAX_TOKENS)}
