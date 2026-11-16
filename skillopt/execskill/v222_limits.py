"""main-v8's bounded cross-benchmark cells and routed-card read reservations.

This module only extends main-v8 tables. A gate runs each fired parent/candidate
pair once; narrowing is rechecked without dispatch and cannot spend another
pair. ALFWorld's actual harm slice is twenty games; the cap deliberately keeps
the brief's sixty-item bound on all four other benchmarks.
"""
from copy import deepcopy

from .v218_limits import LEARNED

CROSS_ITEMS_CAP = 60
CROSS_OTHER_BENCHES = 4
CROSS_RUNS = 2
MAX_CONFIRM_CANDIDATES_PER_ROUND = 5  # whole, three split children, merged
MAX_ACCEPT_CANDIDATES_PER_ROUND = 1
HARM_CELLS_PER_CANDIDATE = CROSS_OTHER_BENCHES * CROSS_ITEMS_CAP * CROSS_RUNS


def maximum_candidates(p, bench, phase):
    p.require(phase in ('confirm', 'accept'), 'Registered cross-gate phase')
    per_round = (MAX_CONFIRM_CANDIDATES_PER_ROUND if phase == 'confirm'
                 else MAX_ACCEPT_CANDIDATES_PER_ROUND)
    return p.train_rounds(p.MAIN_V8, bench) * per_round


def extra_cells(p):
    return {home: {phase: {bench: (0, CROSS_ITEMS_CAP * CROSS_RUNS
                                 * maximum_candidates(p, home, phase))
                          for bench in p.MAIN_V5_ORDER if bench != home}
                   for phase in ('confirm', 'accept')}
            for home in LEARNED}


def read_unit_caps(p):
    return {bench: p.legacy._round_up(p.MAIN_CAP_FACTOR * (
        p.CELL_ANCHORS[bench][1] * (cards + p.PROCEDURE_ARM_FACTOR[1] * procedures)
        + p.MAIN_RESERVATIONS * p.READ_RESERVATION), p.MILLION)
        for bench, (cards, procedures) in p.TEST_READ_CELLS[p.MAIN_V8].items()}


def extend(p):
    child, parent = p.MAIN_V8, p.MAIN_V7
    p.require(p.MAX_CHANGES == 3, 'Cross-gate candidate reservation follows the three-change split bound')
    for home, phases in extra_cells(p).items():
        for phase, additions in phases.items():
            schedule = p.CONFIG_SCHEDULE_CELLS[child][home][phase]
            for bench, (cards, procedures) in additions.items():
                old_c, old_p = schedule.get(bench, (0, 0))
                schedule[bench] = (old_c + cards, old_p + procedures)
            derived = p.legacy._round_up(p.MAIN_CAP_FACTOR * (
                sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * q)
                    for b, (c, q) in schedule.items())
                + p.MAIN_RESERVATIONS * p.READ_RESERVATION), 100000)
            p.CONFIG_STEP_CAPS[child][home][phase] = max(
                p.CONFIG_STEP_CAPS[parent][home][phase], derived)
    # B and C0 are shell-only cells. C, F and the four possible stage packages
    # carry routed note procedures; no identity or sparse-firing discount.
    p.TEST_READ_CELLS[child] = {b: (2 * n, 6 * n) for b, n in p.MAIN_V5_TEST_ITEMS.items()}
    base_read = p.legacy._round_up(p.MAIN_CAP_FACTOR * (
        sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * q)
            for b, (c, q) in p.TEST_READ_CELLS[child].items())
        + len(p.MAIN_V5_ORDER) * p.MAIN_RESERVATIONS * p.READ_RESERVATION), p.MILLION)
    p.CONFIGURATIONS[child]['test_read_cap'] = base_read + max(read_unit_caps(p).values())
    p.CONFIGURATIONS[child]['redo_reserve'] = max(
        p.CONFIGURATIONS[parent]['redo_reserve'],
        *(cap for row in p.CONFIG_STEP_CAPS[child].values() for cap in row.values()))
    p.CONFIGURATIONS[child]['solver_cap'] = p.legacy._round_up(
        sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[child].values())
        + p.CONFIGURATIONS[child]['test_read_cap'] + p.CONFIGURATIONS[child]['redo_reserve'],
        5 * p.MILLION)


def identity():
    from . import profiles as p
    return {'maximum_confirmation_candidates_per_round': MAX_CONFIRM_CANDIDATES_PER_ROUND,
        'maximum_acceptance_candidates_per_round': MAX_ACCEPT_CANDIDATES_PER_ROUND,
        'maximum_candidates_per_step': {phase: maximum_candidates(p, LEARNED[0], phase)
                                        for phase in ('confirm', 'accept')},
        'harm_cells_per_candidate': HARM_CELLS_PER_CANDIDATE,
        'harm_cells_per_step': HARM_CELLS_PER_CANDIDATE * sum(
            maximum_candidates(p, LEARNED[0], phase) for phase in ('confirm', 'accept')),
        'extra_procedure_cells': deepcopy(extra_cells(p)),
        'formula': 'ceil_100000(3*(sum(high_anchor*(card+1.6*procedure))+16*520192))',
        'narrowing': 'inert recheck only; residual firing requiring another pair rejects',
        'reuse_discount': False,
        'read_retry': {'unit_caps': read_unit_caps(p), 'reserve': max(read_unit_caps(p).values()),
                       'charged_scope': '<chain>:test'},
        'method_cap': 'main-v7 by value; no new role calls',
        'solver': 'ceil_5000000(sum(step caps)+read cap+largest learning redo)'}
