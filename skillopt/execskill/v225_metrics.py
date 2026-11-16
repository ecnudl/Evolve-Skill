"""Pinned CL formulas on opened main-v9 aggregate records; never reads a run."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib.util
import json

from skillopt.continual_eval.core import require

REFERENCE_SHA256 = '587883bf35392fd3d7739fce98407519515c2090fa4eef705d4b5f59bfb0a994'
REFERENCE_PATH = Path(__file__).resolve().parents[2] / 'tests/fixtures/execskill/v225_cl_metrics_reference.py'
VERSION = 'main-v9-cl-metrics-v1'


@lru_cache(maxsize=1)
def reference():
    """Only load the vendored, SHA-pinned source; its CLI/main is never invoked."""
    source = REFERENCE_PATH.read_bytes()
    require(hashlib.sha256(source).hexdigest() == REFERENCE_SHA256, 'Pinned CL reference bytes changed')
    spec = importlib.util.spec_from_file_location('_v225_cl_reference', REFERENCE_PATH)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(REFERENCE_PATH), 'exec'), module.__dict__)
    return module


def reanchor(aggregates, anchor, *, same_side=False):
    """Re-express the measured matrix with another measured row zero, without offsets."""
    found = deepcopy(aggregates)
    for block in found['chains'].values():
        for pb in block['per_bench'].values():
            if same_side:
                pb['acc'] = {arm: (pb['acc_other_side'][arm] if pb['side'][arm] == 'H' else value)
                             for arm, value in pb['acc'].items()}
                pb['pairs'] = deepcopy(pb['same_side_L_pairs'])
            pb['acc']['C'] = pb['acc'][anchor]
            pairs = deepcopy(pb['pairs'])
            for arm in ('S1','S2','S3','S4','S5','F'):
                pb['pairs'][arm+'-C'] = pairs[arm+'-'+anchor]
    return found


def _block(aggregates, chain, similar):
    ref = reference()
    c = ref.chains_from_readout(aggregates, aggregates['configuration'], 'opened-main-v9-aggregates')[chain]
    # Keep the exact reference result (metrics, matrix), field for field. JSON
    # naturally serializes the tuple as a pair, preserving all numeric values.
    return {an: ref.cl_metrics(c, an, similar) for an in ('P','S')}


def _changed(aggregates, chain, anchors, similar):
    ref = reference()
    block = aggregates['chains'][chain]
    changed = block['package_changed']
    c = ref.chains_from_readout(aggregates, aggregates['configuration'], 'opened-main-v9-aggregates')[chain]
    result = {}
    for an,(metrics,R) in anchors.items():
        ts,td = [],[]
        harmed=uncertain=informative=0
        for k,yes in enumerate(changed,1):
            if not yes:
                continue
            for j,bench in enumerate(ref.BENCHES):
                if j == k-1:
                    continue
                delta = ref.diff(R[k][j], R[k-1][j])
                (ts if bench in similar[ref.HOME[k]] else td).append(delta)
                informative += 1
                entry = c['delta'].get('S'+str(k),{}).get(bench)
                if entry is None:
                    uncertain += 1
                elif entry[an]['mean'] is not None and entry[an]['mean'] < -1e-12:
                    if entry[an]['hi'] is None:
                        uncertain += 1
                    elif entry[an]['hi'] < 0:
                        harmed += 1
        ts_mean,ts_n = ref.mean(ts)
        td_mean,td_n = ref.mean(td)
        result[an] = {'TS':ts_mean,'TS_n':ts_n,'TD':td_mean,'TD_n':td_n,
            'off_inf':informative,'harmed':harmed,'uncertain':uncertain,
            'no_harm_inf':None if not informative else 1-harmed/informative,
            'no_harm_all':1-harmed/20,'steps':[k for k,yes in enumerate(changed,1) if yes]}
    return result


def compute(aggregates, chain):
    from . import profiles as p
    require(aggregates['configuration'] == p.MAIN_V9 and chain in aggregates['chains'], 'main-v9 aggregates')
    ref=reference()
    similar={ref.BENCH_OF_KEY[b]:[ref.BENCH_OF_KEY[x] for x in p.MAIN_V5_ORDER
             if x != b and any(set((b,x)) == set(pair) for pair in p.SIMILAR_PAIRS_BY_CONFIGURATION[p.MAIN_V9])]
             for b in p.MAIN_V5_ORDER}
    anchor_C = _block(aggregates,chain,similar)
    anchor_C0 = _block(reanchor(aggregates,'C0'),chain,similar)
    anchor_B = _block(reanchor(aggregates,'B'),chain,similar)
    same_side = _block(reanchor(aggregates,'C',same_side=True),chain,similar)
    block=aggregates['chains'][chain]
    noise=[]
    for k,changed in enumerate(block['package_changed'],1):
        if changed:
            continue
        previous='C0' if k==1 else 'S'+str(k-1)
        noise.append({'step':k,'package_changed':False,'reading':'same_text_noise_not_transfer_or_forgetting',
            'per_bench':{bench:deepcopy(pb['pairs']['S'+str(k)+'-'+previous]) for bench,pb in block['per_bench'].items()}})
    homes = set(block['procedures'].values()) | {bench for bench,card in block['cards'].items()
                                                if card['origin'] == bench}
    first_touch = {}
    for anchor in ('C','C0','B'):
        rows = {bench:deepcopy(pb['first_call_touch'][anchor]) for bench,pb in block['per_bench'].items()}
        first_touch[anchor] = {'per_bench':rows, 'homes':sorted(homes),
            'all':{key:sum(row[key] for row in rows.values()) for key in ('touched','n','unknown')},
            'off_target':{key:sum(row[key] for bench,row in rows.items() if bench not in homes)
                          for key in ('touched','n','unknown')}}
    return {'version':VERSION,'configuration':p.MAIN_V9,'chain':chain,'reference_sha256':REFERENCE_SHA256,
        'analysis_labels':{'P':'registered primary','S':'identical requests contribute zero'},
        'anchor_C':anchor_C,'anchor_C0':anchor_C0,'anchor_B':anchor_B,'same_side_L':same_side,
        'first_call_touch':first_touch,
        'changed_only':_changed(aggregates,chain,anchor_C,similar), 'same_text':noise,
        'drift_control':{bench:deepcopy(pb['pairs']['C_end-C']) for bench,pb in block['per_bench'].items()},
        'drift_reading':'C_end-C is descriptive only; never a learning decision', 'similar':similar}


def markdown(metrics):
    lines=['# main-v9 continual-learning metrics', '',
           'Reference SHA256: `'+metrics['reference_sha256']+'`.', '',
           'P is the registered primary analysis; S counts identical requests as ties. C0 is the real chain start.', '',
           '| anchor | analysis | ACC | dACC | PG | BWT | FWT |',
           '|---|---|---:|---:|---:|---:|---:|']
    def number(value):
        return 'unknown' if value is None else '%.6f'%value
    for anchor in ('anchor_C0','anchor_C','anchor_B','same_side_L'):
        for an,(m,_) in metrics[anchor].items():
            lines.append('| '+anchor+' | '+an+' | '+' | '.join(number(m[k]) for k in ('ACC_F','dACC','PG','BWT','FWT'))+' |')
    lines += ['', 'Unchanged-step contrasts are same-text noise, not transfer or forgetting.', '',
              'All registered metric fields are retained in the adjacent JSON. No selection by result is performed.', '']
    return '\n'.join(lines)
