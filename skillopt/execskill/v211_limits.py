"""main-v4 maximum-schedule reservations; token ceilings, never spend forecasts."""
from fractions import Fraction
from math import ceil

from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval.core import require

LEARNED = ('searchqa', 'officeqa', 'livemath', 'spreadsheetbench')
ROUNDS, PATIENCE = 6, 4
RE = reservation(236000, 32768)
RO = reservation(220000, 16384)
RJ = reservation(220000, 8192)
ENGINEER = 271 * RE + (144 + 18) * RO
JUDGE_CALLS = {b: 840 if b == 'spreadsheetbench' else 600 for b in LEARNED}
CONFIRM_CELLS = {b: 480 if b == 'searchqa' else 48 for b in LEARNED}
METHOD_CAP = 470400000 + 4 * (ENGINEER - 20000000) + 2 * sum((n + 1) * RJ for n in JUDGE_CALLS.values())
SOLVER_CAP = 1250000000


def role_caps(bench):
    require(bench in LEARNED, 'A learned benchmark is required for method scopes')
    return {'engineer': ENGINEER, 'examiner': 10000000, 'examiner_research': 9200000,
            'audit_g': (JUDGE_CALLS[bench] + 1) * RJ, 'audit_d': (JUDGE_CALLS[bench] + 1) * RJ}


def role_calls(bench):
    require(bench in LEARNED, 'A learned benchmark is required for method calls')
    from . import smoke, profiles as p
    return {'engineer': 270, 'leakage': 144, 'describer': 18,
            'examiner': smoke.MAX_ROLE_CALLS['examiner'] + p.GENERATOR_CALLS * p.BAND_ROUNDS * p.TOPUP_ROUNDS,
            'examiner_research': smoke.MAX_ROLE_CALLS['examiner_research'],
            'audit_g': JUDGE_CALLS[bench], 'audit_d': JUDGE_CALLS[bench]}


def extend(p):
    c = p.MAIN_V4
    # A compatibility summary uses the largest scope; execution always supplies a benchmark.
    p.CONFIG_ROLE_CAPS[c] = role_caps('spreadsheetbench')
    for bench in LEARNED:
        n = CONFIRM_CELLS[bench]
        p.CONFIG_SCHEDULE_CELLS[c][bench]['confirm'] = {bench: (0, n)}
        amount = 3 * (n * p.CELL_ANCHORS[bench][1] * Fraction(8, 5) + 16 * 520192)
        p.CONFIG_STEP_CAPS[c][bench]['confirm'] = p.legacy._round_up(amount, 100000)
    p.CONFIG_GLM_CAP[c] = METHOD_CAP
    p.CONFIGURATIONS[c].update(solver_cap=SOLVER_CAP, test_read_cap=238000000, redo_reserve=87000000)


def identity():
    from . import profiles as p
    return {'configuration': p.MAIN_V4, 'rounds': ROUNDS, 'patience': PATIENCE,
            'reservations': {'engineer': RE, 'ordinary': RO, 'judge': RJ},
            'single_call_budget': 31, 'train_call_budget': 41,
            'roles': {b: role_caps(b) for b in LEARNED},
            'calls': {b: role_calls(b) for b in LEARNED},
            'prompts_per_audit': {b: 7 if b == 'spreadsheetbench' else 5 for b in LEARNED},
            'solver_scopes': p.CONFIG_STEP_CAPS[p.MAIN_V4],
            'schedule': p.CONFIG_SCHEDULE_CELLS[p.MAIN_V4],
            'confirm_cells': CONFIRM_CELLS, 'confirm_total': sum(CONFIRM_CELLS.values()),
            'judge_calls_per_chain': 2 * sum(JUDGE_CALLS.values()),
            'method_cap': METHOD_CAP, 'solver_cap': SOLVER_CAP, 'overall_cap': METHOD_CAP + SOLVER_CAP,
            'acceptance_sp_s_c': {'searchqa': 3000, 'officeqa': 384, 'livemath': 600, 'spreadsheetbench': 216},
            'independent_c': {'searchqa': 1000, 'officeqa': 128, 'livemath': 200, 'spreadsheetbench': 72},
            'test_items': 1110, 'test_logical_cells_per_chain': 3330,
            'test_logical_cells_both_chains': 6660, 'import_learning_cells': 0}


def method_projection(measured):
    """Per-benchmark costs from measured smoke, including both auditor providers.

    Require actual role measurements on every learned benchmark. Missing data is
    not a readiness waiver. The caller must separately prove the smoke stages.
    """
    from . import profiles as p, budgets, smoke
    require(set(measured) == set(LEARNED), 'Measured method costs for every learned benchmark')
    out = {}
    for chain in p.CHAINS:
        caps = budgets.chain_caps(chain, p.MAIN_V4)
        total, reserve_max = 0, 0
        for k, bench in enumerate(LEARNED, 1):
            calls, entries = role_calls(bench), measured[bench]
            require(set(entries) == set(calls) and all(e['calls'] > 0 for e in entries.values()),
                    'Measured roles include both auditors, repairs and research on each benchmark')
            groups = {}
            for role in calls:
                scope = (budgets.audit_scopes(chain, role[-1].upper(), bench, k) if role.startswith('audit_')
                         else budgets.glm_scopes(chain, role, bench, k))[-1]
                groups.setdefault(scope, []).append(role)
            for scope, roles in groups.items():
                settled = sum(Fraction(str(entries[r]['per_call'])) * calls[r] for r in roles)
                reserve = max(reservation(max(entries[r]['request_bytes'],236000 if r == 'engineer' else 220000),
                    32768 if r == 'engineer' else 8192 if r.startswith('audit_') else 16384) for r in roles)
                out[scope] = {**smoke._glm_fit(settled,reserve,caps[scope]),'roles':roles,'bench':bench,'assumed':[]}
                total += settled
                reserve_max = max(reserve_max,reserve)
        out[chain+':glm'] = {**smoke._glm_fit(total,reserve_max,caps[chain+':glm']), 'assumed':[]}
    return out


def smoke_identity():
    """Finite authored/measured smoke ceilings, independently derived from stage work.

    Solver allowances use the unchanged high-anchor ×1.6 procedure projection,
    threefold headroom and sixteen full next reservations per benchmark/stage.
    Method ceilings use full-input reservations directly, without another ×3.
    These are launch ceilings; measured SE6 may require a new amendment.
    """
    from . import profiles as p
    solver_cells = {'S2': {b: (6, 6) if b == 'alfworld' else (20, 20) for b in p.BENCHES},
                    'S3': {}, 'SX': {}}
    for b in LEARNED:
        runs = p.slice_spec(p.MAIN_V4, b)['run'][1]
        # Two baseline units, one two-arm train unit, two-arm authored confirm;
        # retain the complete inherited examiner and two final self-test passes.
        cards, procs = 2 * 4, 2 * 4 * runs + 2 * 4 * runs + 2 * 2 + 2 * 2 * p.G_SELF_MAX
        for on, (c, n) in p.CONFIG_SCHEDULE_CELLS[p.MAIN_V4][b]['examiner'].items():
            require(on == b, 'Smoke examiner work is benchmark-local')
            cards += c
            procs += n
        solver_cells['S3'][b] = (cards, procs)
    # 100 run items; six training rounds including up to 60 generated items;
    # two final self-tests; 160 acceptance items with full C and two twins;
    # conservatively allow an independent S_dup for every acceptance item.
    solver_cells['SX']['searchqa'] = (
        100 + 2 * 160 + 160 + 150,
        100 + 6 * 2 * (100 + p.G_SELF_MAX) + 2 * 2 * p.G_SELF_MAX + 3 * 160 + 6 * 2 * 2)
    method_calls = {'S2': {}, 'S3': {}, 'SX': {'searchqa': role_calls('searchqa')}}
    for b in LEARNED:
        maximum = role_calls(b)
        prompts = 7 if b == 'spreadsheetbench' else 5
        method_calls['S3'][b] = {
            # Both engineer contexts are bounded by41; analysts4; one bounded role-cost probe.
            'engineer': 2 * 41 + 4 + 1,
            'leakage': 2 * 24 + 1 + 1, 'describer': 24 + 1,
            'examiner': maximum['examiner'] + 1,
            'examiner_research': maximum['examiner_research'] + 1,
            # Two sets of three changes × two passes, plus up to24 final procedures.
            'audit_g': (2 * 3 * 2 + 24) * prompts * 2 + 1,
            'audit_d': (2 * 3 * 2 + 24) * prompts * 2 + 1}
    stages = {}
    for stage in ('S2', 'S3', 'SX'):
        solver_by_bench = {b: p.legacy._round_up(3 * (
            p.CELL_ANCHORS[b][1] * (cards + Fraction(8, 5) * procs) + 16 * 520192), 100000)
            for b, (cards, procs) in solver_cells[stage].items()}
        method_by_bench = {}
        audit_caps = {}
        for b, calls in method_calls[stage].items():
            charges = {role: (count + 1) * (RE if role == 'engineer' else RJ if role.startswith('audit_') else RO)
                       for role, count in calls.items()}
            method_by_bench[b] = sum(charges.values())
            audit_caps[b] = {role: charges[role] for role in ('audit_g', 'audit_d')}
        stages[stage] = {'solver': sum(solver_by_bench.values()), 'method': sum(method_by_bench.values()),
            'solver_by_bench': solver_by_bench, 'method_by_bench': method_by_bench,
            'audit_caps': audit_caps, 'solver_cells': {b: list(v) for b, v in solver_cells[stage].items()},
            'method_calls': method_calls[stage]}
        stages[stage]['overall'] = stages[stage]['solver'] + stages[stage]['method']
    return {'version': 'main-v4-smoke-caps-1', 'stages': stages,
            'solver': sum(row['solver'] for row in stages.values()),
            'method': sum(row['method'] for row in stages.values()),
            'overall': sum(row['overall'] for row in stages.values()),
            'solver_formula': 'ceil_100000(3*(high_anchor*(card+1.6*procedure)+16*520192)) per bench/stage',
            'method_formula': 'sum((maximum_calls+1)*full_input_reservation) per role/bench/stage',
            'scope': 'engineering smoke; no formal scarce supplies; no test reads',
            'repairs': 'QA calculator and sheet optional second calls retain the inherited1.6 envelope; SE6 verifies measured costs',
            'S0_SE6_model_calls': 0, 'D_probes': 'separate D readiness ledger,15 sequential calls'}


def smoke_caps(stage):
    require(stage in ('S2', 'S3', 'SX'), 'A metered smoke stage')
    return smoke_identity()['stages'][stage]
