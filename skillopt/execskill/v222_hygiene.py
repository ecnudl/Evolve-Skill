"""main-v8's measured own-card deletion proposals inside ordinary training rounds.

Parent pass-minus-fail counts choose a candidate; they are not an estimate of
that segment's causal benefit. Only the existing paired train/confirm/accept
rules and cross-bench gates can adopt the measured deletion.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import json

from skillopt.continual_eval.core import require

from . import profiles as p, v211_effects, v222_cards
from .package import with_

MODE = 'measured_candidates'
MIN_TOUCHED = 3


def propose(parent, *, bench, own_segments, parent_cells, whole_card=False, configuration='main-v8'):
    """Return at most one deletion, chosen from actual delivered own-segment notes.

Repeated scored parent cells are averaged within each distinct item, so they
cannot inflate the three-item trigger. Unknown outcomes and undelivered notes
do not establish either touched support or a negative parent-outcome net.
Equal nets use frozen P0 order. An unsuccessful deletion may be tried in a
later ordinary round; the unchanged round/patience limits remain decisive.
    """
    require(p.is_v222(configuration), 'Card hygiene belongs only to main-v8')
    if p.is_v225(configuration):
        return None, {'hygiene_mode': 'off_no_p0'}
    require(len(own_segments) == len(set(own_segments)), 'Distinct original card segment identities')
    record = {'hygiene_mode': MODE, 'bench': bench, 'selected': None, 'segments': [],
              'minimum_touched': MIN_TOUCHED, 'selection': 'lowest_parent_outcome_net_then_P0_order',
              'net_definition': 'sum_over_items(mean_parent_pass_minus_fail); proposal_heuristic_not_deletion_gain',
              'candidate_slot': 'ordinary_round_candidate', 'confirmation_candidates': 0}
    if bench == 'alfworld' or whole_card:
        record['reason'] = 'import_only' if bench == 'alfworld' else 'whole_card_fallback'
        return None, record
    own = [pid for pid in own_segments if pid in parent.order and parent.get(pid).origin == bench
           and v222_cards.is_segment(parent.get(pid))
           and v222_cards.segment_metadata(parent.get(pid))['seeded']]
    outcomes = {pid: defaultdict(list) for pid in own}
    seen = set()
    for trace in parent_cells:
        token = trace.get('token')
        if trace.get('bench') != bench or token not in ('pass', 'fail'):
            continue
        # _current() supplies the incumbent for this round, which may be a
        # previous round's accepted S' trajectory on an unchanged item.
        key = trace.get('task_id')
        require(isinstance(key, str) and key, 'A scored parent trajectory has its item identity')
        cell = trace.get('cell')
        if cell is not None:
            require(isinstance(cell, str), 'A stored parent trajectory has a cell ID')
            if cell in seen:
                continue
            seen.add(cell)
        shown = set()
        for call in trace.get('calls', ()):
            if call.get('purpose') != 'first' or not v211_effects.delivered(call):
                continue
            request = json.loads(call['user'])
            text = str(request.get(p.NOTES_KEY) or '')
            shown.update(v211_effects.shown_fields(bench, parent,
                (trace.get('shell') or {}).get('notes', ()), request, text, hook='before_call'))
        for pid in shown & set(own):
            outcomes[pid][key].append(token)
    ranked = []
    for position, pid in enumerate(own):
        items = outcomes[pid]
        passed = sum((Fraction(sum(t == 'pass' for t in values), len(values))
                      for values in items.values()), Fraction(0))
        failed = Fraction(len(items)) - passed
        net = passed - failed
        record['segments'].append({'segment': pid, 'touched': len(items),
                                   'passed': str(passed), 'failed': str(failed), 'net': str(net)})
        if len(items) >= MIN_TOUCHED and net < 0:
            ranked.append((net, position, pid))
    if not ranked:
        record['reason'] = 'no_negative_supported_segment'
        return None, record
    _, _, pid = min(ranked)
    candidate = with_(parent, step=parent.step, remove=[pid])
    record.update(selected=pid, candidate_sha256=candidate.sha256, confirmation_candidates=1,
                  reason='measured_deletion_proposed')
    return candidate, record
