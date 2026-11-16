"""main-v7's one count rule and zero-call touched-item accounting.

This module receives already selected practice records. It never opens a pool,
starts a worker or calls a model. A request identity is a content identity;
fault flags still prohibit reuse but do not manufacture a changed request.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math

from skillopt.continual_eval.core import require

from . import profiles as p, reuse

NAME = 'gain-and-no-harm-v2-21'
COVERAGE_SENTENCE = (
    'A program must touch at least 30% of the items of its bench to be worth its cost, '
    'unless it is a solver of a sub-type; then state the sub-type share.'
)


def constants():
    return {'GAIN_MIN_ITEMS': p.GAIN_MIN_ITEMS, 'GAIN_MIN_SHARE': float(p.GAIN_MIN_SHARE),
            'HARM_RATIO': str(p.HARM_RATIO), 'WHOLE_BATCH_FLOOR': float(p.WHOLE_BATCH_FLOOR)}


def counts(*, touched, fixed, broken, batch, whole_batch=None):
    """The same serializable decision record at training, confirmation and acceptance."""
    require(all(type(n) is int and n >= 0 for n in (touched, fixed, broken, batch))
            and fixed + broken <= touched <= batch, 'Valid touched-item decision counts')
    net = fixed - broken
    whole = Fraction(net, batch) if whole_batch is None and batch else Fraction(0)
    if whole_batch is not None:
        require(type(whole_batch) in (int, float, Fraction) and math.isfinite(whole_batch),
                'A finite whole-batch contrast')
        whole = Fraction(str(whole_batch)) if type(whole_batch) is float else Fraction(whole_batch)
    require(-1 <= whole <= 1, 'Whole-batch contrast lies between -1 and 1')
    floor = max(p.GAIN_MIN_ITEMS, math.ceil(p.GAIN_MIN_SHARE * touched))
    cap = p.HARM_RATIO * fixed
    accepted = net >= floor and broken <= cap and whole >= p.WHOLE_BATCH_FLOOR
    return {'touched': touched, 'fixed': fixed, 'broken': broken, 'net': net,
            'gain_floor': floor, 'harm_cap': float(cap), 'whole_batch': float(whole),
            'decision': 'accept' if accepted else 'reject', 'constants': constants(),
            **({'reason': 'no_touched_items'} if touched == 0 else {})}


def same_request(first, second):
    """Compare rendered requests; a registered sheet callback is not an effect.

    The unchanged reuse planner still includes callback identities, since it
    must dispatch them before their effects are known. They cannot establish a
    touched item for the main-v7 decision on their own.
    """
    require(all(isinstance(row, dict) and isinstance(row.get('request_sha256'), str)
                and len(row['request_sha256']) == 64 and isinstance(row.get('post_call'), list)
                for row in (first, second)), 'Both complete request identities are required')
    def request_content(row):
        return row['request_sha256'], [entry for entry in row['post_call'] if entry.get('hook') != 'sheet_feedback']
    return request_content(first) == request_content(second)


def post_call_effects(shell, calls=(), *, package=None, practice_replay=False):
    """Count actual sheet callback effects, keeping silent callbacks explicit.

    Notes count only in a delivered repair request. A permitted request for a
    repair is itself an effect, even if that later call fails. The engineer may
    separately inspect callbacks on verified practice reports without a solver;
    ``practice_replay`` permits the assembled notes of that requested repair.
    """
    from .outcomes_ext import delivery
    versions = {proc.id: (proc.sha256, hashlib.sha256(proc.source.encode()).hexdigest())
                for proc in package.procedures if 'sheet_feedback' in proc.hooks} if package is not None else {}
    enabled = (shell.get('route') or {}).get('enabled', ())
    found = {pid: {'procedure_sha256': versions[pid][0], 'note_emitted': False, 'repair_requested': False}
             for pid in enabled if pid in versions}
    def entry(pid, version=None):
        if not isinstance(pid, str) or not pid:
            return None
        if pid in versions:
            version = versions[pid][0]
        return found.setdefault(pid, {'procedure_sha256': version,
                                     'note_emitted': False, 'repair_requested': False})
    for effect in shell.get('effects', ()):
        pid = effect.get('procedure')
        if effect.get('hook') != 'sheet_feedback' or effect.get('kind') != 'request_repair':
            continue
        row = entry(pid)
        if row is not None and effect.get('permitted') is True and (
                pid not in versions or effect.get('source_sha256') == versions[pid][1]):
            row['repair_requested'] = True
    delivered = []
    for call in calls:
        receipt = call.get('receipt')
        state = (receipt or {}).get('delivery') or delivery(receipt)
        if call.get('purpose') != 'repair' or state not in ('delivered', 'truncated'):
            continue
        try:
            request = json.loads(call.get('user', ''))
        except (TypeError, ValueError):
            continue
        if isinstance(request, dict) and isinstance(request.get('repair_notes'), str):
            delivered.append(request['repair_notes'])
    requested = any(row['repair_requested'] for row in found.values())
    for note in shell.get('notes', ()):
        if note.get('hook') != 'sheet_feedback':
            continue
        pid, text = note.get('id'), note.get('delivered_text')
        row = entry(pid, note.get('procedure_sha256'))
        if row is None:
            continue
        if row['procedure_sha256'] is None:
            row['procedure_sha256'] = note.get('procedure_sha256')
        matching = pid not in versions or (note.get('procedure_sha256') == versions[pid][0]
                                           and note.get('source_sha256') == versions[pid][1])
        row['note_emitted'] |= bool(matching and isinstance(text, str) and text
                                    and (any(text in shown for shown in delivered) or practice_replay and requested))
    return found


def identity_report(signatures, *, bench, trajectories=()):
    require(bench in reuse.BENCHES, 'This bench has a zero-call request identity')
    changed = [key for key, pair in signatures.items() if not same_request(pair.get("S'"), pair.get('S'))]
    callbacks = {key: {arm: {row['procedure']: row for row in pair[arm]['post_call']
                            if row.get('hook') == 'sheet_feedback' and isinstance(row.get('procedure'), str)}
                       for arm in ('S', "S'")} for key, pair in signatures.items()}
    touched = set(changed)
    for trace in trajectories:
        cell = trace.get('cell') if isinstance(trace.get('cell'), dict) else {}
        key, arm = trace.get('task_id', cell.get('task_id')), trace.get('arm', cell.get('arm'))
        if key not in callbacks or arm not in ('S', "S'"):
            continue
        effects = trace.get('post_call_effects')
        if effects is None:
            effects = post_call_effects(trace.get('shell') or {}, trace.get('calls') or ())
        other = 'S' if arm == "S'" else "S'"
        for pid, effect in effects.items():
            active = callbacks[key][arm].get(pid)
            if (active is not None and active != callbacks[key][other].get(pid)
                    and (effect.get('procedure_sha256') is None or effect['procedure_sha256'] == active.get('version'))
                    and (effect.get('note_emitted') is True or effect.get('repair_requested') is True)):
                touched.add(key)
    return {'touched': [key for key in signatures if key in touched],
            'untouched': [key for key in signatures if key not in touched],
            'request_changed': changed,
            'callback_active': {key: {arm: list(rows) for arm, rows in pair.items()}
                                for key, pair in callbacks.items()}}


def identity_touched(signatures, *, bench, trajectories=()):
    return identity_report(signatures, bench=bench, trajectories=trajectories)['touched']


def alfworld_touched(trajectories, changed):
    """Changed-procedure note emission, not enabled predicates or blank/dropped notes."""
    changed = set(changed)
    touched = []
    for row in trajectories:
        if row.get('bench', row.get('benchmark')) != 'alfworld':
            continue
        cell = row.get('cell') if isinstance(row.get('cell'), dict) else {}
        if row.get('arm', cell.get('arm', row.get('arm_kind'))) not in ("S'", 'candidate', 'S', 'parent'):
            continue
        key = row.get('task_id', cell.get('task_id'))
        emitted = any(note.get('id', note.get('procedure')) in changed
                      and isinstance(note.get('delivered_text'), str) and bool(note['delivered_text'].strip())
                      for note in (row.get('shell') or {}).get('notes', ()))
        if emitted and key not in touched:
            require(isinstance(key, str) and key, 'An emitted-note episode has an item identity')
            touched.append(key)
    return touched


def token(cell):
    if isinstance(cell, str):
        return cell
    return ((cell.get('judge') or {}).get('v2') or {}).get('token', (cell.get('final') or {}).get('token'))


def item_changes(cells, evaluated, *, touched):
    """Pass-rate changes per item; repeated runs remain within their item denominator."""
    evaluated, touched = list(evaluated), set(touched)
    require(len(evaluated) == len(set(evaluated)) and touched <= set(evaluated),
            'Touched items belong to one distinct evaluated batch')
    fixed, broken, deltas = [], [], {}
    for key in evaluated:
        if key not in touched:
            deltas[key] = Fraction(0)
            continue
        first, second = cells.get(("S'", key)), cells.get(('S', key))
        require(first and second and len(first) == len(second), 'Every touched item has paired equal-run cells')
        require(all(token(cell) is not None for cell in list(first) + list(second)),
                'Every compared cell has an outcome token')
        delta = Fraction(sum(token(cell) == 'pass' for cell in first)
                         - sum(token(cell) == 'pass' for cell in second), len(first))
        deltas[key] = delta
        if delta > 0:
            fixed.append(key)
        elif delta < 0:
            broken.append(key)
    return {'fixed': fixed, 'broken': broken, 'deltas': deltas,
            'untouched': [key for key in evaluated if key not in touched]}


def decide(cells, evaluated, *, touched, whole_batch=None):
    evaluated, touched = list(evaluated), list(touched)
    require(len(touched) == len(set(touched)), 'Touched items are distinct')
    changes = item_changes(cells, evaluated, touched=touched)
    if whole_batch is None:
        whole_batch = sum(changes['deltas'].values(), Fraction(0)) / len(evaluated) if evaluated else Fraction(0)
    return counts(touched=len(touched), fixed=len(changes['fixed']), broken=len(changes['broken']),
                  batch=len(evaluated), whole_batch=whole_batch)


def coverage(batch, touched, per_procedure):
    """Count-only feedback; no confirmation/acceptance task content enters the engineer."""
    require(type(batch) is int and batch >= 0, 'A nonnegative coverage batch')
    def row(items):
        n = len(set(items))
        require(n <= batch, 'Touched coverage cannot exceed its batch')
        return {'touched': n, 'batch': batch, 'share': n / batch if batch else 0.0}
    candidate = row(touched)
    return {'candidate': candidate, 'procedures': {pid: row(items) for pid, items in per_procedure.items()},
            'instruction': COVERAGE_SENTENCE,
            'repair': ('fires on almost nothing: %d / %d items touched' % (candidate['touched'], batch)
                       if candidate['touched'] < p.GAIN_MIN_ITEMS else None)}


def coverage_ok(value):
    if not isinstance(value, dict) or set(value) != {'candidate', 'procedures', 'instruction', 'repair'}:
        return False
    if value['instruction'] != COVERAGE_SENTENCE or not isinstance(value['procedures'], dict):
        return False
    for row in [value['candidate'], *value['procedures'].values()]:
        if not (isinstance(row, dict) and set(row) == {'touched', 'batch', 'share'}
                and type(row['touched']) is int and type(row['batch']) is int
                and 0 <= row['touched'] <= row['batch']
                and row['share'] == (row['touched'] / row['batch'] if row['batch'] else 0.0)):
            return False
    row = value['candidate']
    expected = ('fires on almost nothing: %d / %d items touched' % (row['touched'], row['batch'])
                if row['touched'] < p.GAIN_MIN_ITEMS else None)
    return value['repair'] == expected


def rule_ok(value):
    fields = {'touched', 'fixed', 'broken', 'net', 'gain_floor', 'harm_cap', 'whole_batch', 'decision', 'constants'}
    if not isinstance(value, dict) or set(value) != fields | ({'reason'} if value.get('touched') == 0 else set()):
        return False
    try:
        expected = counts(touched=value['touched'], fixed=value['fixed'], broken=value['broken'],
                          batch=value['touched'], whole_batch=value['whole_batch'])
    except (ValueError, TypeError):
        return False
    return value == expected
