"""Frozen within-run allocation, with historical exposure explicitly disclosed.

Only already pinned preparations enter this module. It never reads source data,
opens sealed content, qualifies new material, or fetches additional supplies.
"""
from copy import deepcopy

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest
from . import profiles as p, supply, v211_protection

LEARNED = p.BENCHES[:-1]
PROVENANCE = {'historical_exposure': 'unknown', 'route_history_fresh': 'unknown',
              'within_run_disjoint': True, 'decision_uses_per_slice': 1}


def freshness(value=None):
    out = deepcopy(PROVENANCE if value is None else value)
    require(set(out) == set(PROVENANCE), 'Freshness has all four structured provenance fields')
    require(out['historical_exposure'] == 'unknown' or isinstance(out['historical_exposure'], list),
            'Historical exposure is a verified list or unknown')
    require(type(out['route_history_fresh']) is bool or out['route_history_fresh'] == 'unknown',
            'Route history freshness is true, false or unknown')
    require(out['within_run_disjoint'] is True and type(out['decision_uses_per_slice']) is int
            and out['decision_uses_per_slice'] == 1, 'One decision per disjoint slice')
    return out


def allocate(bench, pool, *, tail=(), kept=None, excluded=(), protected_hashes=(), source_pins=None, provenance=None):
    """Return flat, round-assigned cuts and a content-bound, public ID identity.

    Input order is normalized by the unchanged registered ordering function.
    Protected IDs cause refusal, never an adaptive recut. Spare supplies remain
    closed; callers may not recycle unused confirmation rounds.
    """
    require(bench in LEARNED, 'Only four learned benchmarks allocate child slices')
    rows = list(pool)
    require(all(i.get('benchmark') == bench for i in rows), 'One benchmark per allocation')
    protected = set(protected_hashes) | {v211_protection.id_hash(v) for v in excluded}
    v211_protection.check_items(bench, rows, protected)
    require(len({i['task_id'] for i in rows}) == len(rows), 'Distinct supply IDs')
    expected = {'searchqa': 600, 'officeqa': 74, 'livemath': 283, 'spreadsheetbench': 91}[bench]
    require(len(rows) == expected, 'Pinned qualified pool has its registered size')
    rows = supply.order(bench, rows)
    spec = p.slice_spec(p.MAIN_V4, bench)
    cut = {}
    if bench == 'searchqa':
        tail = list(tail)
        v211_protection.check_items(bench, tail, protected)
        require(len(tail) >= 1240, 'SearchQA requires at least 1,240 qualified tail items')
        require(all(i.get('benchmark') == bench and i.get('part') == 'tail' for i in tail),
                'SearchQA confirmation uses the qualified tail only')
        require(len({i['task_id'] for i in tail}) == len(tail), 'Distinct tail IDs')
        require(not {i['task_id'] for i in rows} & {i['task_id'] for i in tail}, 'Pool and tail are disjoint')
        # This preserves the existing persisted exclusion validation, including its sealed digest.
        supply.slices(bench, tail, {'accept': 1240}, kept=kept)
        ordered_tail = supply.order(bench, tail)
        cut.update(run=rows[:300], smoke=rows[-280:], spare=rows[300:320], accept=ordered_tail[:1000])
        confirmations = ordered_tail[1000:1240]
    elif bench == 'livemath':
        absent = [i for i in rows if not supply.meta_present(i)]
        present = [i for i in rows if supply.meta_present(i)]
        require((len(absent), len(present)) == (154, 129), 'LiveMath has 154 absent and 129 present items')
        chosen = {i['task_id'] for i in absent[:30] + present[:65]}
        cut.update(run=[i for i in rows if i['task_id'] in chosen], accept=absent[30:130],
                   accept_probe=present[65:])
        confirmations = absent[130:]
    else:
        n, a = spec['run'][0], spec['accept'][0]
        cut.update(run=rows[:n], accept=rows[n:n+a])
        confirmations = rows[n+a:]
    count = p.confirm_spec(p.MAIN_V4, bench, 1)['items']
    require(len(confirmations) == 6 * count, 'Exactly six round-assigned confirmation slices')
    for r in range(1, 7):
        cut['confirm-r%d' % r] = confirmations[(r-1)*count:r*count]
    identities = {name: [i['task_id'] for i in items] for name, items in cut.items()}
    used = [key for ids in identities.values() for key in ids]
    require(len(set(used)) == len(used), 'Pairwise disjoint run/accept/confirm/smoke/probe/spare slices')
    require(not protected & {v211_protection.id_hash(v) for v in used},
            'Allocation overlaps protected or already consumed IDs')
    origin = freshness(provenance)
    identity = {'configuration': p.MAIN_V4, 'bench': bench, 'slices': identities,
                'slice_sha256': {name: digest(ids) for name, ids in identities.items()},
                'source_items_sha256': digest(pool), 'source_pins': deepcopy(source_pins or {}),
                'tail_items_sha256': digest(tail) if bench == 'searchqa' else None,
                'exclusion_record_sha256': kept[p.RECORD_HASH] if bench == 'searchqa' else None,
                'protected_ids_sha256': digest(sorted(protected)), 'provenance': origin,
                'accept_freshness': p.ACCEPT_FRESHNESS[p.MAIN_V4],
                'confirm_freshness': p.CONFIRM_FRESHNESS[p.MAIN_V4],
                'confirm_rule': 'fixed > broken plus registered format guard',
                'selection_check': 'preregistered', 'rounds': 6, 'recycle_unused': False,
                'cross_round_incumbent_cache': False}
    identity['allocation_sha256'] = digest(identity)
    return cut, identity
