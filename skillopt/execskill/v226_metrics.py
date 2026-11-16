"""main-v10 CL metrics anchored to the actual start and registered step pairs."""
from copy import deepcopy

from skillopt.continual_eval.core import require

from . import profiles as p, v225_metrics as frozen

VERSION = 'main-v10-cl-metrics-v1'
REFERENCE_SHA256 = frozen.REFERENCE_SHA256


def _incremental(aggregates, chain, similar):
    """Use measured S_k-S_{k-1} pairs, including their secondary tie rule."""
    ref = frozen.reference()
    block = aggregates['chains'][chain]
    steps = [k for k, changed in enumerate(block['package_changed'], 1) if changed]
    result = {}
    for analysis, side in (('P', 'primary'), ('S', 'secondary')):
        ts, td, rows = [], [], []
        harmed = uncertain = informative = 0
        for k in steps:
            previous = 'C0' if k == 1 else 'S' + str(k - 1)
            contrast = 'S%d-%s' % (k, previous)
            benches = {}
            for bench, values in block['per_bench'].items():
                if bench == p.MAIN_V5_ORDER[k - 1]:
                    continue
                informative += 1
                pair = values['pairs'].get(contrast)
                estimate = None if pair is None else pair[side]['estimate']
                mean = None if estimate is None else estimate['mean']
                hi = None if estimate is None else (estimate.get('ci95') or [None, None])[1]
                # Exactly the reference harmed/uncertain rule; crossing zero
                # does not establish harm, and a missing upper bound is unknown.
                unknown = pair is None or mean is not None and mean < -1e-12 and hi is None
                harm = mean is not None and mean < -1e-12 and hi is not None and hi < 0
                uncertain += int(unknown)
                harmed += int(harm)
                target = ts if ref.BENCH_OF_KEY[bench] in similar[ref.HOME[k]] else td
                target.append(mean)
                benches[bench] = {'contrast': contrast, 'estimate': deepcopy(estimate),
                                  'harmed': harm, 'uncertain': unknown}
            rows.append({'step': k, 'contrast': contrast, 'per_bench': benches})
        ts_mean, ts_n = ref.mean(ts)
        td_mean, td_n = ref.mean(td)
        result[analysis] = {'TS': ts_mean, 'TS_n': ts_n, 'TD': td_mean, 'TD_n': td_n,
            'off_inf': informative, 'harmed': harmed, 'uncertain': uncertain,
            'no_harm_inf': None if not informative else 1 - harmed / informative,
            'no_harm_all': 1 - harmed / 20, 'steps': steps, 'per_step': rows}
    return result


def compute(aggregates, chain):
    require(p.is_v226(aggregates['configuration']) and chain in aggregates['chains'], 'main-v10 aggregates')
    # Reuse the frozen descriptive calculations on a detached value. The
    # original module and the caller's aggregate remain byte-for-byte intact.
    descriptive = deepcopy(aggregates)
    descriptive['configuration'] = p.MAIN_V9
    result = frozen.compute(descriptive, chain)
    reanchored = frozen.reanchor(aggregates, 'C0')
    changed = frozen._changed(reanchored, chain, result['anchor_C0'], result['similar'])
    incremental = _incremental(aggregates, chain, result['similar'])
    for analysis in ('P', 'S'):
        # Secondary pairwise ties need not telescope across different anchors.
        # TS/TD therefore come directly from registered incremental pairs.
        changed[analysis].update({key: incremental[analysis][key] for key in ('TS', 'TS_n', 'TD', 'TD_n')})
    result.update(version=VERSION, configuration=p.MAIN_V10,
        changed_only=changed, incremental_changed=incremental,
        changed_only_reading='cumulative harm relative to C0 at changed steps; TS/TD from incremental registered pairs',
        incremental_reading='S1-C0 at step 1; S_k-S_{k-1} thereafter; changed steps only',
        anchor_readings={'anchor_C0': 'actual chain start',
                         'anchor_C': 'descriptive historical comparison only',
                         'anchor_B': 'descriptive no-guidance comparison',
                         'same_side_L': 'descriptive historical comparison with both arms on L'})
    return result


def markdown(metrics):
    text = frozen.markdown(metrics).replace('# main-v9 continual-learning metrics',
                                           '# main-v10 continual-learning metrics', 1)
    return text + ('\nChanged-step cumulative harm is relative to C0. Incremental harm and TS/TD use the registered '
                   'S1-C0 and S_k-S_{k-1} pairs. Anchor C is a descriptive historical comparison only.\n')
