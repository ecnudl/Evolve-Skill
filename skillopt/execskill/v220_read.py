"""SearchQA-only, post-hoc F/C read; request reuse is main-v6's unchanged algorithm."""
from __future__ import annotations

from skillopt.continual_eval.core import read_json, require, write_json
from skillopt.validator_pilot.api import digest

from . import profiles as p, v218_read, v220_import
from .cells import Arm

EVIDENCE_KIND = 'post_hoc_selected_upper_bound'


def arms(final, card):
    require(final.procedures and final.sha256 != card.sha256 and not card.procedures,
            'F = C: the SearchQA import read requires its nonempty treatment and empty card package')
    return {'F': Arm('candidate', final), 'C': Arm('card', card)}


def check_cell(context, cell):
    """No other bench, arm or learning-unit dispatch exists in this configuration."""
    require(p.is_v220(context.configuration) and cell['benchmark'] == 'searchqa'
            and cell['arm'] in ('F', 'C') and cell['unit'] in {
                chain + scope + 'searchqa' for chain in p.CHAINS
                for scope in ('/test/', '/v214-smoke/S2/')},
            'SearchQA import read refuses arm %s in unit %s' % (cell['arm'], cell['unit']))


def fired_notes(shell_notes, procedure_ids):
    """Only a nonempty note actually delivered to the shell counts as an emission."""
    ids = set(procedure_ids)
    return sorted({row['id'] for row in shell_notes
                   if row.get('id') in ids and row.get('delivered_text')})


def fired_metadata(chain, route, shell_notes):
    ids = v220_import.PROCEDURE_IDS[chain]
    return {'procedure_ids': list(ids),
            'enabled': [pid for pid in ids if pid in (route or {}).get('enabled', [])],
            'emitted_note_ids': fired_notes(shell_notes, ids)}


def fired_counts(cells, procedures):
    """Count unique F items, not stochastic runs; distinguish enabled from emitted."""
    candidates = set().union(*map(set, v220_import.PROCEDURE_IDS.values()))
    ids = sorted(pid for pid in procedures if pid in candidates)
    require(any(set(ids) == set(pair) for pair in v220_import.PROCEDURE_IDS.values()),
            'The SearchQA readout names one chain\'s two fixed rejected procedures')
    rows = [(item, value) for (arm, item, _), value in cells.items() if arm == 'F']
    for _, row in rows:
        found = row.get('searchqa_fired')
        require(isinstance(found, dict) and set(found.get('procedure_ids', [])) == set(ids)
                and set(found.get('enabled', [])) <= set(ids)
                and set(found.get('emitted_note_ids', [])) <= set(found.get('enabled', [])),
                'Every SearchQA F cell retains its hash-only procedure firing metadata')
    return {'definition': 'fired means a nonempty note delivered to the solver; enabled predicates are separate',
            'items': len({item for item, _ in rows}),
            'fired_items': len({item for item, row in rows if row['searchqa_fired']['emitted_note_ids']}),
            'enabled_items': len({item for item, row in rows if row['searchqa_fired']['enabled']}),
            'per_procedure': {pid: {
                'fired_items': len({item for item, row in rows if pid in row['searchqa_fired']['emitted_note_ids']}),
                'enabled_items': len({item for item, row in rows if pid in row['searchqa_fired']['enabled']})}
                for pid in ids}}


def secondary(units):
    from . import readout as r
    return {'rule': 'items with byte-identical solver request sequences count as ties',
            'conclusions_follow': 'primary',
            'contrasts': {bench: {'F-C': v218_read.contrast(cells, 'F', 'C', r._items(cells, 'F', 'C'),
                bootstrap=True, sensitivity=True)} for bench, cells in units.items()}}


def readout(units, *, learned, procedures, label, evidence, stages):
    from . import readout as r
    require(set(units) == {'searchqa'} and stages is None,
            'The SearchQA import readout contains only SearchQA and no stage rows')
    require(not learned, 'A post-hoc SearchQA import has no newly learned benchmarks')
    cells = units['searchqa']
    require({arm for arm, _, _ in cells} == {'F', 'C'}, 'The SearchQA import readout arms must match F/C')
    r._clustered('searchqa', cells)
    primary = r._contrast(cells, 'F', 'C', r._items(cells, 'F', 'C'), bootstrap=True, sensitivity=True)
    return p.record('readout', evidence, {
        'configuration': p.SEARCHQA_HP_V6, 'evidence_kind': EVIDENCE_KIND, 'read_label': label,
        'learned': [], 'imported': [bench for bench in p.SUPPORTED_BENCHES if bench in set(procedures.values())],
        'contrasts': {'searchqa': {'F-C': primary}}, 'contrasts_reading': 'descriptive',
        'identical_request_analysis': secondary(units),
        'searchqa_fired': fired_counts(cells, procedures),
        'q1_home': None, 'q2_similar': None, 'q3_noninferiority': None,
        'shared_unanswered': {'searchqa': len(r.unanswered(cells))},
        'arms': {'searchqa': r.arm_table(cells)},
        'placebo': {'removed': True}, 'code_vs_text': {'removed': True}, 'twins': {'removed': True},
        'honesty': {
            'acceptance': 'Both candidates were rejected: failed J1 under practical-v2-11-pooled.',
            'interpretation': 'Owner-requested post-hoc upper-bound description, never method evidence.',
            'panel_exposure': 'Fifth or sixth SearchQA read after main-v4, main-v5, baseline-v210, implant-v5 and cross-v5.',
            'same_text_noise': 'Primary paired estimate governs conclusions; dispatched same-text reruns may differ.'}})


def make_canaries(root, pinned, *, pools, run, evidence, panel, configuration):
    """One SearchQA panel, only after consent; S0 never opens a test dataset."""
    from . import evaluation as e
    allowed = e.consent(root / 'shared', configuration)
    require(set(pools or {}) == {'searchqa'}, 'Only the SearchQA practice pool is visible')
    path = root / e.READ_CANARIES
    with e.exclusive(root / 'shared' / 'test-read-canaries.lock', wait=True):
        if not path.exists():
            training, pins = e._training_side(pools, ('searchqa',), configuration=configuration)
            tasks, report = panel(pinned, 'searchqa', access=e.data.TestAccess(e.READ_CANARY_UNIT))
            texts = {'searchqa': [task['public']['question'] for task in tasks]}
            skip = e.training_duplicates(texts, training)
            found, counts = e.select_canaries(texts, skip=skip)
            write_json(path, p.record('test-read-canaries', evidence, {
                'configuration': configuration, 'canaries': found, 'counts': counts,
                'per_bench': e.CANARIES_PER_BENCH, 'seed_tag': e.CANARY_TAG,
                'sources': {'searchqa': 'the public question'},
                'skipped': {'searchqa': len(skip['searchqa'])}, 'training_pools': pins,
                'unit': e.READ_CANARY_UNIT, 'run': run, 'panels': {'searchqa': report['panel_hash']},
                'consent_sha256': digest(allowed), 'extends': None}))
        value, second = e._canary_records(root, read=True, configuration=configuration)
    require(second is None and value.get('run') == run and value.get('consent_sha256') == digest(allowed),
            'The isolated SearchQA read canaries belong to this run and consent')
    return value
