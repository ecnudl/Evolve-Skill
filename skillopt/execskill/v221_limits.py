"""main-v7's extra immediate acceptance and merged-split solver bounds."""
from copy import deepcopy

from .v218_limits import LEARNED, GENERATED_MAX


def extra_cells(p):
    """Keep the frozen first-read allowance and price five additional full reads.

    Sampling and exact-request reuse receive no discount. A merged split is
    priced as both package arms on all training/confirmation items each round.
    """
    result = {}
    for bench in LEARNED:
        rounds = p.train_rounds(p.MAIN_V7, bench)
        size, runs = p.slice_spec(p.MAIN_V7, bench)['accept']
        result[bench] = {
            'accept': ((rounds - 1) * size * runs, 2 * (rounds - 1) * size * runs),
            'selftest': (0, 2 * rounds * (p.slice_spec(p.MAIN_V7, bench)['run'][0]
                                        + GENERATED_MAX[bench])),
            'confirm': (0, 2 * rounds * p.confirm_spec(p.MAIN_V7, bench, 1)['items']),
        }
    return result


def extend(p):
    child, parent = p.MAIN_V7, p.MAIN_V6
    for bench, kinds in extra_cells(p).items():
        for kind, (cards, procedures) in kinds.items():
            schedule = p.CONFIG_SCHEDULE_CELLS[child][bench][kind]
            old_c, old_p = schedule[bench]
            schedule[bench] = (old_c + cards, old_p + procedures)
            derived = p.legacy._round_up(p.MAIN_CAP_FACTOR * (
                sum(p.CELL_ANCHORS[b][1] * (c + p.PROCEDURE_ARM_FACTOR[1] * q)
                    for b, (c, q) in schedule.items())
                + p.MAIN_RESERVATIONS * p.READ_RESERVATION), 100000)
            p.CONFIG_STEP_CAPS[child][bench][kind] = max(
                p.CONFIG_STEP_CAPS[parent][bench][kind], derived)
    p.CONFIGURATIONS[child]['redo_reserve'] = max(
        p.CONFIGURATIONS[parent]['redo_reserve'],
        *(cap for row in p.CONFIG_STEP_CAPS[child].values() for cap in row.values()))
    p.CONFIGURATIONS[child]['solver_cap'] = p.legacy._round_up(
        sum(sum(row.values()) for row in p.CONFIG_STEP_CAPS[child].values())
        + p.CONFIGURATIONS[child]['test_read_cap'] + p.CONFIGURATIONS[child]['redo_reserve'],
        5 * p.MILLION)


def identity():
    from . import profiles as p
    return {'extra_cells': deepcopy(extra_cells(p)),
        'acceptance': 'frozen first-read allowance + (rounds-1)*A*runs*(one C + two package arms)',
        'merged_split': 'two package arms * rounds * items; one run per item',
        'formula': 'ceil_100000(3*(sum(high_anchor*(card+1.6*procedure))+16*520192))',
        'reuse_discount': False, 'fresh_pool_discount': False,
        'method_cap': 'main-v6 by value; no added model-role calls',
        'read_cap': 'main-v6 by value, including its charged test retry',
        'solver': 'ceil_5000000(sum(step caps)+read cap+largest learning redo)'}
