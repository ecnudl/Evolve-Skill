"""main-v8's instruction arms and hash-only off-home delivery accounting."""
from __future__ import annotations

from collections import defaultdict

from skillopt.continual_eval.core import require
from . import profiles as p, v222_cards
from .cells import Arm
from .package import empty

VERSION = 'main-v8-cross-identity-v1'
ARMS = ('B', 'C0', 'C', 'F')


def start_package(setting, chain):
    require(p.is_v222(p.configuration_of(setting)), 'P0 belongs only to main-v8')
    if p.is_v225(p.configuration_of(setting)):
        return empty(step=chain + '/s0', evidence=setting.evidence)
    fallback = setting.extra.get('v222_fallbacks', {}).get(chain, ())
    return v222_cards.initial_package(evidence=setting.evidence, step=chain + '/s0', fallback=fallback)


def arms(final, initial):
    blank = empty(step=initial.step + '/blank', evidence=initial.evidence)
    return {'B': Arm('blank', blank), 'C0': Arm('card', blank),
            'C': Arm('card', initial), 'F': Arm('candidate', final)}


def learned_benches(final, initial):
    """Frozen seed notes and the fixed ALF import are not learned improvements."""
    changed = set()
    for pid in set(initial.order) | set(final.order):
        before = initial.get(pid) if pid in initial.order else None
        after = final.get(pid) if pid in final.order else None
        if (before is None or after is None or before.sha256 != after.sha256
                or initial.narrowed.get(pid, ()) != final.narrowed.get(pid, ())):
            changed.add((after or before).origin)
    return [bench for bench in p.active_benches(p.MAIN_V8) if bench in changed and bench != 'alfworld']


def metadata(bench, package, shells, *, post_call_effects=None):
    """Retain IDs and booleans only, using actual callback effects after dispatch.

    A sheet_feedback note can be assembled without a repair request ever being
    sent. Its assembled text is therefore not evidence of delivery; the v2.21
    post-call accounting verifies the current procedure version and delivery.
    """
    emitted, affected = set(), set()
    for shell in shells:
        for note in shell.get('notes', ()):
            pid = note.get('id')
            if (note.get('hook') != 'sheet_feedback' and pid in package.order
                    and isinstance(note.get('delivered_text'), str) and note['delivered_text'].strip()):
                emitted.add(pid)
    for pid, effect in (post_call_effects or {}).items():
        if pid not in package.order or effect.get('procedure_sha256') != package.get(pid).sha256:
            continue
        if effect.get('note_emitted') is True:
            emitted.add(pid)
        if effect.get('repair_requested') is True:
            affected.add(pid)
    touched = emitted | affected
    return {'version': VERSION, 'non_home': [
        {'id': pid, 'origin': package.get(pid).origin,
         'segment': v222_cards.is_segment(package.get(pid)),
         'note_emitted': pid in emitted, 'request_changed': pid in affected}
        for pid in package.order if pid in touched and package.get(pid).origin != bench]}


def shared_metadata(bench, package, planning, post_call_effects):
    """Own first-request notes plus verified effects of the identical source callback."""
    require(isinstance(planning, dict) and planning.get('version') == VERSION,
            'A shared main-v8 cell retains its own planned delivery metadata')
    rows = {}
    for row in planning['non_home']:
        pid = row['id']
        require(pid in package.order and row['origin'] == package.get(pid).origin != bench,
                'Planned off-home notes belong to the shared cell package')
        rows[pid] = dict(row)
    actual = metadata(bench, package, [], post_call_effects=post_call_effects)
    for row in actual['non_home']:
        current = rows.setdefault(row['id'], dict(row))
        current['note_emitted'] |= row['note_emitted']
        current['request_changed'] |= row['request_changed']
    return {'version': VERSION, 'non_home': [rows[pid] for pid in package.order if pid in rows]}


def cross_identity(units):
    """F-cell touches; F-C outcomes on that subset are descriptive, not attribution."""
    from . import readout as r
    result = {}
    for bench, cells in units.items():
        items = sorted({item for arm, item, _ in cells if arm == 'F'})
        by_origin, by_procedure = defaultdict(set), defaultdict(set)
        touched = set()
        for (arm, item, _), cell in cells.items():
            if arm != 'F':
                continue
            value = cell.get('cross_identity')
            require(isinstance(value, dict) and value.get('version') == VERSION,
                    'Every main-v8 F cell retains its own delivery accounting')
            for row in value['non_home']:
                require(row['origin'] != bench and (row['note_emitted'] or row['request_changed']),
                        'Only actual off-home effects are counted')
                touched.add(item)
                by_origin[row['origin']].add(item)
                by_procedure[row['id']].add(item)
        paired = sorted(touched & set(r._known(cells, r._items(cells, 'F', 'C'), 'F', 'C')))
        differences = r.differences(cells, 'F', 'C', paired) if paired else []
        result[bench] = {'items': len(items), 'touched': len(touched), 'touched_items': sorted(touched),
            'by_origin': {key: sorted(value) for key, value in sorted(by_origin.items())},
            'by_procedure': {key: sorted(value) for key, value in sorted(by_procedure.items())},
            'identity_proven': not touched, 'extra_model_calls': 0,
            'fixed': sum(value > 0 for value in differences), 'broken': sum(value < 0 for value in differences),
            'paired_known': len(paired), 'paired_unknown': len(touched) - len(paired),
            'comparison': 'F-C on off-home-touched items; descriptive, not isolated procedure attribution',
            'separate_cross_read_needed': bool(touched)}
    return result


def readout(units, *, learned, procedures, label, evidence, stages):
    from . import readout as r, v218_read
    require(stages is not None and stages[0] == 'C', 'main-v8 retains stage rows starting at P0')
    contrasts = {}
    for bench, cells in units.items():
        require({arm for arm, _, _ in cells} == {*ARMS, *stages}, 'Exact main-v8 read arms')
        r._clustered(bench, cells)
        contrasts[bench] = {a + '-' + b: r._contrast(cells, a, b, r._items(cells, a, b),
            bootstrap=True, sensitivity=True) for a, b in
            (('C0', 'B'), ('C', 'C0'), ('F', 'C'), ('C', 'B'), ('F', 'B'))}
    return p.record('readout', evidence, {'configuration': p.MAIN_V8, 'evidence_kind': r.EVIDENCE_KIND,
        'read_label': label, 'learned': list(learned), 'imported': ['alfworld'],
        'contrasts': contrasts, 'contrasts_reading': 'descriptive',
        'arms': {bench: r.arm_table(cells) for bench, cells in units.items()},
        'stages': r.stage_table(units, stages, configuration=p.MAIN_V8),
        'stage_questions': r.stage_questions(units, stages, configuration=p.MAIN_V8),
        'identical_request_analysis': v218_read.secondary(units, stages),
        'shared_unanswered': {bench: len(r.unanswered(cells)) for bench, cells in units.items()},
        'cross_identity': cross_identity(units), 'card_decomposition': v222_cards.manifest_pins(),
        'placebo': {'removed': True}, 'code_vs_text': {'removed': True}, 'twins': {'removed': True}})
