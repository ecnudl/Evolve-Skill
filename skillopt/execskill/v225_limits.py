"""main-v9 reservations: learned cards, fresh stage reads and C_end drift control.

No reuse, rejected-round, exhausted-pool or overlap discount is taken. The
operator overlay adds one shell-only C_end read to the brief's nine arms.
"""
from copy import deepcopy

from skillopt.coevo5.ledger import reservation
from .v218_limits import LEARNED

CARD_ROUNDS = 3
CARD_WRITER_INPUT_CHARS = 120_000
CARD_WRITER_OUTPUT_TOKENS = 32_768
CARD_ACCEPT_ITEMS = {'searchqa': 60, 'officeqa': 32, 'zebralogic': 40,
                     'spreadsheetbench': 36}
CARD_CONFIRM_ITEMS = 40
WRITER_CALLS_PER_BENCH = CARD_ROUNDS * 2
WRITER_CALLS_PER_CHAIN = len(LEARNED) * WRITER_CALLS_PER_BENCH
WRITER_RESERVATION = reservation(CARD_WRITER_INPUT_CHARS, CARD_WRITER_OUTPUT_TOKENS)
READ_LABELS = ('anchor', 's1', 's2', 's3', 's4', 's5', 'i', 'c_end')
READ_ARMS = ('B', 'C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5', 'I', 'C_end')
SMOKE_SOLVER_TOKENS = 1_000_000
SMOKE_METHOD_TOKENS = 3 * WRITER_RESERVATION


def extra_cells(p):
    """Added (home, scope, target) procedure cells, priced at 1.6 high anchor."""
    result = {}
    for home in LEARNED:
        size, runs = p.slice_spec(p.MAIN_V8, home)['run']
        acceptance_runs = p.slice_spec(p.MAIN_V8, home)['accept'][1]
        attempts = CARD_ROUNDS if home == 'searchqa' else 1
        result[home] = {
            'selftest': {home: (0, 2 * size * runs * CARD_ROUNDS)},
            'accept': {home: (0, 2 * CARD_ACCEPT_ITEMS[home] * acceptance_runs * attempts)},
            'confirm': ({home: (0, 2 * CARD_CONFIRM_ITEMS * CARD_ROUNDS)}
                        if home == 'searchqa' else {}),
        }
    # At most one accepted home card; only the registered empty target slots.
    # Both QA directions are reserved even though a concrete chain may omit one.
    for home, targets in {'searchqa': ('officeqa',),
                           'officeqa': ('searchqa', 'spreadsheetbench'),
                           'spreadsheetbench': ('officeqa',)}.items():
        for target in targets:
            result[home]['confirm'][target] = (0, 120)
    return result


def unit_cells(p, label, bench):
    p.require(label in READ_LABELS and bench in p.MAIN_V5_ORDER,
              'Registered main-v9 read unit')
    count = p.MAIN_V5_TEST_ITEMS[bench]
    return (3 * count, 0) if label == 'anchor' else ((count, 0)
        if label == 'c_end' else (0, count))


def read_unit_caps(p):
    return {label: {bench: p.legacy._round_up(p.MAIN_CAP_FACTOR * (
        p.CELL_ANCHORS[bench][1] * (cards + p.PROCEDURE_ARM_FACTOR[1] * procedures)
        + p.MAIN_RESERVATIONS * p.READ_RESERVATION), p.MILLION)
        for bench in p.MAIN_V5_ORDER
        for cards, procedures in (unit_cells(p, label, bench),)}
        for label in READ_LABELS}


def base_read_cap(p):
    return p.legacy._round_up(p.MAIN_CAP_FACTOR * (
        sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * q)
            for b, (c, q) in p.TEST_READ_CELLS[p.MAIN_V9].items())
        + len(p.MAIN_V5_ORDER) * p.MAIN_RESERVATIONS * p.READ_RESERVATION), p.MILLION)


def extend(p):
    child, parent = p.MAIN_V9, p.MAIN_V8
    for home, phases in extra_cells(p).items():
        for phase, additions in phases.items():
            schedule = p.CONFIG_SCHEDULE_CELLS[child][home][phase]
            for bench, (cards, procedures) in additions.items():
                old_c, old_p = schedule.get(bench, (0, 0))
                schedule[bench] = (old_c + cards, old_p + procedures)
            derived = p.legacy._round_up(p.MAIN_CAP_FACTOR * (
                sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * q)
                    for b, (c, q) in schedule.items())
                + p.MAIN_RESERVATIONS * p.READ_RESERVATION), 100_000)
            p.CONFIG_STEP_CAPS[child][home][phase] = max(
                p.CONFIG_STEP_CAPS[parent][home][phase], derived)
    p.TEST_READ_CELLS[child] = {b: (4 * n, 6 * n) for b, n in p.MAIN_V5_TEST_ITEMS.items()}
    retry = max(cap for row in read_unit_caps(p).values() for cap in row.values())
    p.CONFIGURATIONS[child]['test_read_cap'] = max(
        p.CONFIGURATIONS[parent]['test_read_cap'], base_read_cap(p) + retry)
    p.CONFIGURATIONS[child]['redo_reserve'] = max(
        p.CONFIGURATIONS[parent]['redo_reserve'],
        *(cap for row in p.CONFIG_STEP_CAPS[child].values() for cap in row.values()))
    p.CONFIGURATIONS[child]['solver_cap'] = p.legacy._round_up(
        sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[child].values())
        + p.CONFIGURATIONS[child]['test_read_cap'] + p.CONFIGURATIONS[child]['redo_reserve'],
        5 * p.MILLION)
    p.CONFIG_ROLE_CAPS[child]['card_writer'] = WRITER_CALLS_PER_BENCH * WRITER_RESERVATION
    p.CONFIG_GLM_CAP[child] = p.CONFIG_GLM_CAP[parent] + WRITER_CALLS_PER_CHAIN * WRITER_RESERVATION


def identity():
    from . import profiles as p
    unit_caps = read_unit_caps(p)
    retry = max(cap for row in unit_caps.values() for cap in row.values())
    return {'extra_procedure_cells': deepcopy(extra_cells(p)),
        'formula': 'ceil_100000(3*(sum(high_anchor*(card+1.6*procedure))+16*520192))',
        'reuse_discount': False, 'fresh_pool_discount': False, 'overlap_discount': False,
        'step_caps_sum': sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[p.MAIN_V9].values()),
        'read_arms': list(READ_ARMS), 'read_units': len(READ_LABELS) * len(p.MAIN_V5_ORDER),
        'read_formula': 'ceil_1M(3*(sum(high_anchor*(4*n+1.6*6*n))+5*16*520192))',
        'read_retry': {'base_read_cap': base_read_cap(p), 'unit_caps': unit_caps,
                       'reserve': retry, 'derived_read_cap': base_read_cap(p) + retry,
                       'registered_read_cap': p.CONFIGURATIONS[p.MAIN_V9]['test_read_cap'],
                       'charged_scope': '<chain>:test'},
        'writer': {'calls_per_bench': WRITER_CALLS_PER_BENCH,
                   'calls_per_chain': WRITER_CALLS_PER_CHAIN,
                   'reservation': WRITER_RESERVATION,
                   'additional_method_cap': WRITER_CALLS_PER_CHAIN * WRITER_RESERVATION},
        'smoke_additions': {'writer_calls': 3, 'solver_cells': 60,
                           'solver_tokens': SMOKE_SOLVER_TOKENS,
                           'method_tokens': SMOKE_METHOD_TOKENS},
        'solver': 'ceil_5000000(sum(step caps)+read cap+largest learning redo)'}
