"""Practice-only learned-card controller; v2.25 overlay's five-percent rule.

Cards are judged on full batches. Procedure confirmation alone has a main-v9
small-slice gain floor. Full-touch decision selections are immutable and consumed even when
rejected; public identity screening alone does not consume them. Only training
trajectories can return to the writer.
"""
from __future__ import annotations

from dataclasses import replace
from contextlib import nullcontext
from fractions import Fraction
import hashlib
import math

from skillopt.continual_eval.core import read_json, require, write_json
from . import profiles as p, v221_rule

CARD_ROUNDS = 3
CARD_GAIN_SHARE = Fraction(1, 20)
CARD_CONFIRM_ITEMS = 40
CARD_ACCEPT_ITEMS = {'searchqa': 60, 'officeqa': 32, 'zebralogic': 40, 'spreadsheetbench': 36}
CONFIRMATION_SMALL_SLICE_BELOW_ITEMS = 30
CONFIRMATION_SMALL_SLICE_GAIN_FLOOR = 1


def procedure_confirmation(rule, *, configuration, items):
    """Relax only main-v9's small procedure confirmation gain floor."""
    if not p.is_v225(configuration) or items >= CONFIRMATION_SMALL_SLICE_BELOW_ITEMS:
        return rule
    passed = (rule['net'] >= CONFIRMATION_SMALL_SLICE_GAIN_FLOOR
              and rule['broken'] <= p.HARM_RATIO * rule['fixed']
              and Fraction(str(rule['whole_batch'])) >= p.WHOLE_BATCH_FLOOR)
    return {**rule, 'gain_floor': CONFIRMATION_SMALL_SLICE_GAIN_FLOOR,
            'decision': 'accept' if passed else 'reject', 'small_slice_clause': True}


def counts(*, touched, fixed, broken, batch, whole_batch=None):
    """Full-touch card rule, separate from the frozen procedure rule."""
    old = v221_rule.counts(touched=touched, fixed=fixed, broken=broken,
                           batch=batch, whole_batch=whole_batch)
    require(touched == batch, 'A card comparison touches the full registered batch')
    floor = max(p.GAIN_MIN_ITEMS, math.ceil(CARD_GAIN_SHARE * touched))
    whole = Fraction(str(old['whole_batch']))
    passed = old['net'] >= floor and broken <= p.HARM_RATIO * fixed and whole >= p.WHOLE_BATCH_FLOOR
    clause = ('gain_floor' if old['net'] < floor else 'harm_ratio' if broken > p.HARM_RATIO * fixed
              else 'whole_batch' if whole < p.WHOLE_BATCH_FLOOR else None)
    return {**old, 'gain_floor': floor, 'decision': 'accept' if passed else 'reject',
            'clause': clause, 'constants': {**old['constants'], 'GAIN_MIN_SHARE': float(CARD_GAIN_SHARE)}}


def request_changed(signatures):
    """Only a different, fault-free rendered request establishes a card touch."""
    return [key for key, pair in signatures.items()
            if all(isinstance(pair.get(arm), dict) and pair[arm].get('faults') == []
                   and isinstance(pair[arm].get('request_sha256'), str)
                   and len(pair[arm]['request_sha256']) == 64 for arm in ('S', "S'"))
            and pair['S']['request_sha256'] != pair["S'"]['request_sha256']]



def require_card_identity(st, incumbent, candidate, signatures):
    """Changed composed guidance cannot produce an entirely unchanged batch."""
    if not p.is_v226(p.configuration_of(st.setting)) or not signatures:
        return
    from . import v225_cards as cards
    from .cells import Pause
    shell = st.setting.cards.get(st.bench, '')
    if (cards.compose(st.bench, shell, incumbent) != cards.compose(st.bench, shell, candidate)
            and all(pair['S']['request_sha256'] == pair["S'"]['request_sha256']
                    for pair in signatures.values())):
        raise Pause('configuration', 'card_request_identity_defect:' + st.bench, st.name)

def no_change_rule(batch, touched=0):
    """A rejected card cannot receive credit for stochastic rerun differences."""
    rule = v221_rule.counts(touched=touched, fixed=0, broken=0, batch=batch)
    return {**rule, 'gain_floor': max(p.GAIN_MIN_ITEMS, math.ceil(CARD_GAIN_SHARE * touched)),
            'decision': 'reject', 'clause': 'gain_floor', 'reason': 'not_full_touch',
            'fixed_items': [], 'broken_items': [],
            'constants': {**rule['constants'], 'GAIN_MIN_SHARE': float(CARD_GAIN_SHARE)}}


def decide(cells, keys, *, signatures):
    require(set(signatures) == set(keys), 'Every card item has a request comparison')
    touched = request_changed(signatures)
    if len(touched) != len(keys):
        return no_change_rule(len(keys), len(touched))
    changes = v221_rule.item_changes(cells, keys, touched=keys)
    rule = counts(touched=len(keys), fixed=len(changes['fixed']), broken=len(changes['broken']),
                  batch=len(keys), whole_batch=sum(changes['deltas'].values(), Fraction(0)) / len(keys))
    return {**rule, 'fixed_items': changes['fixed'], 'broken_items': changes['broken']}


def count_feedback(result, stage):
    rule = result.get('rule', result)
    return {'stage': stage, **{k: rule.get(k) for k in ('touched', 'fixed', 'broken', 'net',
            'gain_floor', 'harm_cap', 'whole_batch', 'decision', 'clause')}}


def units():
    return tuple(name for c in range(1, CARD_ROUNDS + 1) for name in
        ('card-write-c%d' % c, 'card-train-c%d' % c, 'card-confirm-c%d' % c, 'card-accept-c%d' % c)) + tuple(
            'card-cross-' + b for b in CARD_ACCEPT_ITEMS)


def _read_record(st, path, kind):
    if p.is_v226(p.configuration_of(st.setting)):
        from .v226_candidates import read_record
        from .cells import Pause
        from .errors import ConfigurationError
        try:
            return read_record(path, kind)
        except (ValueError, OSError, TypeError, KeyError, AttributeError, ConfigurationError) as error:
            raise Pause('configuration', 'sealed_record_invalid', str(path)) from error
    return p.verified(read_json(path), kind)


def used_acceptance(st):
    """Only practice selection receipts; never scan the chain's read directory."""
    found = set()
    for kind in ('confirm', 'accept'):
        for c in range(1, CARD_ROUNDS + 1):
            path = st.root / ('card-%s-selection-c%d.json' % (kind, c))
            if path.exists():
                if p.is_v226(p.configuration_of(st.setting)):
                    found.update(_read_record(st, path, 'v225-card-selection')['examined'])
                else:
                    found.update(p.verified(read_json(path), 'v225-card-selection')['examined'])
    return found



def _system_context(st):
    if p.is_v226(p.configuration_of(st.setting)):
        from . import v226_candidates
        return v226_candidates.arm('system')
    return nullcontext()

def select(st, cut, c, kind, incumbent, candidate):
    # Preserve the frozen selector's reads, identities and call order.
    if p.is_v226(p.configuration_of(st.setting)):
        return _select_v226(st, cut, c, kind, incumbent, candidate)
    from . import step, v221_learning
    n = CARD_CONFIRM_ITEMS if kind == 'confirm' else CARD_ACCEPT_ITEMS[st.bench]
    path = st.root / ('card-%s-selection-c%d.json' % (kind, c))
    pool = list(cut['accept'])
    by_id = {item['task_id']: item for item in pool}
    if path.exists():
        row = p.verified(read_json(path), 'v225-card-selection')
        require(row['parent_sha256'] == incumbent.sha256 and row['candidate_sha256'] == candidate.sha256
                and row['pool_ids'] == list(by_id) and row['requested'] == n,
                'Card selection resumes its original packages and practice pool')
        return [by_id[key] for key in row.get('screened', row['examined'])], row
    used = used_acceptance(st)
    def signature(item):
        from . import solver
        key = item['task_id']
        views = [(key, solver.routing_view(st.bench, item['public'], runtime=st.runtime()))]
        return step._pair_signatures(st, candidate, incumbent, {key: item['public']}, views)[key]
    sampled = v221_learning.select_acceptance(pool, signature, used=used, maximum=n, target=n)
    selected = sampled.pop('selected')
    require(set(sampled['request_signatures']) == {item['task_id'] for item in selected},
            'Card selection identities cover exactly its screened practice items')
    sampled['touched'] = request_changed(sampled['request_signatures'])
    if len(sampled['touched']) != len(selected):
        # Identity screening is public-only. An invalid full-touch comparison
        # must not consume the scarce OfficeQA/SpreadsheetBench decision read.
        sampled['screened'], sampled['examined'] = sampled['examined'], []
    row = p.record('v225-card-selection', st.evidence, {**sampled, 'configuration': p.MAIN_V9,
        'parent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256,
        'pool_ids': list(by_id), 'requested': n, 'round': c, 'kind': kind,
        'previously_examined': sorted(used)})
    write_json(path, row)
    return selected, row



def _select_v226(st, cut, c, kind, incumbent, candidate):
    from skillopt.validator_pilot.api import digest
    from . import step, v221_learning
    n = CARD_CONFIRM_ITEMS if kind == 'confirm' else CARD_ACCEPT_ITEMS[st.bench]
    path = st.root / ('card-%s-selection-c%d.json' % (kind, c))
    pool = list(cut['accept'])
    by_id = {item['task_id']: item for item in pool}
    core = None
    if p.is_v226(p.configuration_of(st.setting)):
        from . import solver
        from .v226_bindings import workbook_digests
        core = {'workbook_sha256': workbook_digests(st.bench, {key: item['public'] for key, item in by_id.items()}),
                'configuration': p.configuration_of(st.setting), 'bench': st.bench, 'round': c, 'kind': kind,
                'pool_ids': list(by_id), 'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
                'views_sha256': digest([(key, solver.routing_view(st.bench, item['public'], runtime=st.runtime()))
                                       for key, item in by_id.items()]),
                'runtime_sha256': digest(st.runtime()), 'card_sha256': digest(st.setting.cards.get(st.bench, ''))}
    if path.exists():
        with _system_context(st):
            row = _read_record(st, path, 'v225-card-selection')
            if core is not None:
                require(row['core'] == core, 'A resumed card selection keeps its deterministic request core')
            require(row['parent_sha256'] == incumbent.sha256 and row['candidate_sha256'] == candidate.sha256
                    and row['pool_ids'] == list(by_id) and row['requested'] == n,
                    'Card selection resumes its original packages and practice pool')
            return [by_id[key] for key in row.get('screened', row['examined'])], row
    with _system_context(st):
        used = used_acceptance(st)
    def signature(item):
        from . import solver
        key = item['task_id']
        views = [(key, solver.routing_view(st.bench, item['public'], runtime=st.runtime()))]
        return step._pair_signatures(st, candidate, incumbent, {key: item['public']}, views)[key]
    sampled = v221_learning.select_acceptance(pool, signature, used=used, maximum=n, target=n)
    selected = sampled.pop('selected')
    require(set(sampled['request_signatures']) == {item['task_id'] for item in selected},
            'Card selection identities cover exactly its screened practice items')
    require_card_identity(st, incumbent, candidate, sampled['request_signatures'])
    sampled['touched'] = request_changed(sampled['request_signatures'])
    if len(sampled['touched']) != len(selected):
        # Identity screening is public-only. An invalid full-touch comparison
        # must not consume the scarce OfficeQA/SpreadsheetBench decision read.
        sampled['screened'], sampled['examined'] = sampled['examined'], []
    with _system_context(st):
        row = p.record('v225-card-selection', st.evidence, {**sampled, 'configuration': p.configuration_of(st.setting),
            'parent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256,
            'pool_ids': list(by_id), 'requested': n, 'round': c, 'kind': kind,
            'previously_examined': sorted(used), **({'core': core} if core is not None else {})})
        write_json(path, row)
    return selected, row


def measure(st, items, incumbent, candidate, *, name, kind, runs, cached=None, consume=False, cross=False,
            selection=None):
    """Fresh candidate cells; exact fault-free incumbent reuse in training only."""
    # The v2.26 core/containment work must never run on the frozen path.
    if p.is_v226(p.configuration_of(st.setting)):
        return _measure_v226(st, items, incumbent, candidate, name=name, kind=kind, runs=runs, cached=cached,
                             consume=consume, cross=cross, selection=selection)
    from . import step, rounds, solver, units as u, v222_runtime
    from .cells import Arm
    keys = {rounds.key(st.bench, row['task_id']) if kind == 'selftest' else row['task_id']: row for row in items}
    publics = {key: row['public'] for key, row in keys.items()}
    views = [(key, solver.routing_view(st.bench, public, runtime=st.runtime())) for key, public in publics.items()]
    signatures = step._pair_signatures(st, candidate, incumbent, publics, views)
    require(set(signatures) == set(keys), 'Card dispatch identities cover exactly the registered batch')
    def work(attempt):
        gate = None
        changed = request_changed(signatures)
        if len(changed) != len(keys):
            rule = no_change_rule(len(keys), len(changed))
            return {'rule': rule, 'decision': 'reject', 'reason': 'not_full_touch',
                'cells': 0, 'reused_cells': 0, 'request_signatures': signatures,
                'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
                'parent_cells': {}, 'candidate_cells': {}, 'cross_gate': None}
        if cross:
            chosen, gate = v222_runtime.cross_gate(st, attempt, unit=name, phase='acceptance',
                                                   parent=incumbent, candidate=candidate)
            require(chosen is not None and chosen.sha256 == candidate.sha256 and gate['passed'],
                    'Own card acceptance proves off-home request identity')
        if consume:
            st.services.registry.register(st.namespace, st.bench, items, unit=st.label(name),
                purpose=st.purpose('accept'), run_root=str(st.setting.root), attempt=u.attempt_number(attempt))
            st.services.registry.dispatch(st.namespace, st.bench, items, unit=st.label(name),
                run_root=str(st.setting.root), attempt=u.attempt_number(attempt))
        jobs, parent_rows = [], {}
        for key, item in keys.items():
            old = (cached or {}).get('parent_cells', {}).get(key, [])
            reuse = (kind == 'selftest' and len(old) == runs
                and (cached or {}).get('request_signatures', {}).get(key, {}).get('S') == signatures[key]['S']
                and all(step._confirm_cell_reusable(row, key) for row in old))
            if reuse:
                parent_rows[key] = old
            task = {'benchmark': st.bench, 'public': item['public'], 'private': item['private']}
            for run in range(runs):
                if not reuse:
                    jobs.append(('S', Arm('parent', incumbent), key, run, task))
                jobs.append(("S'", Arm('candidate', candidate), key, run, task))
        found = step._cells(st, attempt, st.solver(kind, attempt), st.label(name), jobs, tag='v225-card')
        pairs = {('S', key): rows for key, rows in parent_rows.items()}
        for row in found:
            pairs.setdefault((row['cell']['arm'], row['cell']['task_id']), []).append(row)
        require(set(pairs) == {(arm, key) for key in keys for arm in ('S', "S'")}
                and all(len(rows) == runs for rows in pairs.values()), 'Complete registered card pairs')
        rule = decide(pairs, list(keys), signatures=signatures)
        decision = p.record('v225-card-decision', st.evidence, {'unit': st.label(name), 'rule': rule,
            'parent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256})
        write_json(attempt / 'card-decision.json', decision)
        return {'rule': rule, 'decision': rule['decision'], 'reason': rule['clause'],
            'decision_sha256': decision[p.RECORD_HASH], 'sealed_sha256': None,
            'cells': len(found), 'reused_cells': sum(map(len, parent_rows.values())),
            'fault_items': [], 'violating_items': [], 'dup': False, 'g_acc': 0,
            'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
            'request_signatures': signatures, 'cross_gate': gate,
            'parent_cells': {key: pairs[('S', key)] for key in keys},
            'candidate_cells': {key: pairs[("S'", key)] for key in keys}}
    def settle(attempt, result):
        if consume and result.get('reason') != 'not_full_touch':
            st.services.registry.decide(st.namespace, st.bench, items, unit=st.label(name),
                run_root=str(st.setting.root), attempt=u.attempt_number(attempt))
    return st.unit(name, work, settle=settle if consume else None)



def _measure_v226(st, items, incumbent, candidate, *, name, kind, runs, cached=None, consume=False, cross=False,
            selection=None):
    """Fresh candidate cells; exact fault-free incumbent reuse in training only."""
    from skillopt.validator_pilot.api import digest
    from . import step, rounds, solver, units as u, v222_runtime
    from .cells import Arm
    current = p.is_v226(p.configuration_of(st.setting))
    if current:
        from . import v226_candidates as candidate_guard
    def system():
        return candidate_guard.arm('system') if current else nullcontext()
    evaluation = {'registered': False, 'selected_ids': [], 'signatures': {}, 'gate': None, 'cells': 0}
    def identities(chosen, attempt=None):
        keys = {rounds.key(st.bench, row['task_id']) if kind == 'selftest' else row['task_id']: row
                for row in chosen}
        publics = {key: row['public'] for key, row in keys.items()}
        views = [(key, solver.routing_view(st.bench, public, runtime=st.runtime())) for key, public in publics.items()]
        core = {'configuration': p.configuration_of(st.setting), 'bench': st.bench, 'unit': name,
                'kind': kind, 'runs': runs, 'slice_ids': list(keys), 'candidate_sha256': candidate.sha256,
                'incumbent_sha256': incumbent.sha256, 'views_sha256': digest(views),
                'runtime_sha256': digest(st.runtime()), 'card_sha256': digest(st.setting.cards.get(st.bench, ''))}
        if current:
            from .v226_bindings import workbook_digests
            core['workbook_sha256'] = workbook_digests(st.bench, publics)
        path = attempt.parent / 'card-request-plan.json' if current else None
        if path is not None and path.exists():
            with system():
                sealed = _read_record(st, path, 'v226-card-requests')
                require(sealed['core'] == core, 'A resumed card unit keeps its deterministic request core')
                signatures = sealed['request_signatures']
        else:
            signatures = step._pair_signatures(st, candidate, incumbent, publics, views)
            if path is not None:
                with system():
                    write_json(path, p.record('v226-card-requests', st.evidence,
                        {'core': core, 'request_signatures': signatures}))
        require(set(signatures) == set(keys), 'Card dispatch identities cover exactly the registered batch')
        require_card_identity(st, incumbent, candidate, signatures)
        return keys, signatures
    # Frozen main-v9 retains its original timing. main-v10 performs every sandbox
    # identity inside work, after _Step.unit binds tags, locks and diagnostics.
    original = None if current else identities(items)
    def work(attempt):
        chosen_items, selected = items, None
        gate = None
        # Harm slices are fixed and independent of the scarce home selection.
        # Reject before writing a selection receipt or consuming that pool.
        if current and cross:
            chosen, gate = v222_runtime.cross_gate(st, attempt, unit=name, phase='acceptance',
                                                   parent=incumbent, candidate=candidate)
            evaluation['gate'] = gate
            if chosen is None or chosen.sha256 != candidate.sha256 or not gate['passed']:
                rule = {**no_change_rule(len(items)), 'reason': 'cross_bench_harm', 'clause': 'cross_bench_harm'}
                return {'rule': rule, 'decision': 'reject', 'reason': 'cross_bench_harm',
                    'cells': 0, 'reused_cells': 0, 'request_signatures': {},
                    'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
                    'parent_cells': {}, 'candidate_cells': {}, 'cross_gate': gate,
                    'selected_ids': [], 'selection': None, 'registered': False}
        if selection is not None:
            require(current, 'Unit-bound card selection belongs to main-v10')
            cut, c, select_kind = selection
            chosen_items, selected = select(st, cut, c, select_kind, incumbent, candidate)
        keys, signatures = identities(chosen_items, attempt) if current else original
        evaluation.update(selected_ids=[row['task_id'] for row in chosen_items], signatures=signatures)
        changed = request_changed(signatures)
        extra = ({'selected_ids': [row['task_id'] for row in chosen_items], 'selection': selected,
                  'registered': False} if current else {})
        def rejected(reason):
            rule = no_change_rule(len(keys), len(changed))
            if reason != 'not_full_touch':
                rule = {**rule, 'reason': reason, 'clause': reason}
            return {'rule': rule, 'decision': 'reject', 'reason': reason,
                'cells': 0, 'reused_cells': 0, 'request_signatures': signatures,
                'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
                'parent_cells': {}, 'candidate_cells': {}, 'cross_gate': gate, **extra}
        if selected is not None and len(chosen_items) != selected['requested']:
            return rejected('supply_exhausted')
        if len(changed) != len(keys):
            return rejected('not_full_touch')
        if cross and not current:
            chosen, gate = v222_runtime.cross_gate(st, attempt, unit=name, phase='acceptance',
                                                   parent=incumbent, candidate=candidate)
            evaluation['gate'] = gate
            if current and (chosen is None or chosen.sha256 != candidate.sha256 or not gate['passed']):
                return rejected('cross_bench_harm')
            require(chosen is not None and chosen.sha256 == candidate.sha256 and gate['passed'],
                    'Own card acceptance proves off-home request identity')
        # Once a paid/registered evaluation begins, preserve the unit's ordinary
        # stop semantics; containment cannot discard consumption or partial cells.
        with system():
            if consume:
                st.services.registry.register(st.namespace, st.bench, chosen_items, unit=st.label(name),
                    purpose=st.purpose('accept'), run_root=str(st.setting.root), attempt=u.attempt_number(attempt))
                st.services.registry.dispatch(st.namespace, st.bench, chosen_items, unit=st.label(name),
                    run_root=str(st.setting.root), attempt=u.attempt_number(attempt))
                if current:
                    extra['registered'] = evaluation['registered'] = True
            jobs, parent_rows = [], {}
            for key, item in keys.items():
                old = (cached or {}).get('parent_cells', {}).get(key, [])
                reuse = (kind == 'selftest' and len(old) == runs
                    and (cached or {}).get('request_signatures', {}).get(key, {}).get('S') == signatures[key]['S']
                    and all(step._confirm_cell_reusable(row, key) for row in old))
                if reuse:
                    parent_rows[key] = old
                task = {'benchmark': st.bench, 'public': item['public'], 'private': item['private']}
                for run in range(runs):
                    if not reuse:
                        jobs.append(('S', Arm('parent', incumbent), key, run, task))
                    jobs.append(("S'", Arm('candidate', candidate), key, run, task))
            found = step._cells(st, attempt, st.solver(kind, attempt), st.label(name), jobs, tag='v225-card')
            evaluation['cells'] = len(found)
            pairs = {('S', key): rows for key, rows in parent_rows.items()}
            for row in found:
                pairs.setdefault((row['cell']['arm'], row['cell']['task_id']), []).append(row)
            require(set(pairs) == {(arm, key) for key in keys for arm in ('S', "S'")}
                    and all(len(rows) == runs for rows in pairs.values()), 'Complete registered card pairs')
            rule = decide(pairs, list(keys), signatures=signatures)
            decision = p.record('v225-card-decision', st.evidence, {'unit': st.label(name), 'rule': rule,
                'parent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256})
            write_json(attempt / 'card-decision.json', decision)
            return {'rule': rule, 'decision': rule['decision'], 'reason': rule['clause'],
                'decision_sha256': decision[p.RECORD_HASH], 'sealed_sha256': None,
                'cells': len(found), 'reused_cells': sum(map(len, parent_rows.values())),
                'fault_items': [], 'violating_items': [], 'dup': False, 'g_acc': 0,
                'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
                'request_signatures': signatures, 'cross_gate': gate,
                'parent_cells': {key: pairs[('S', key)] for key in keys},
                'candidate_cells': {key: pairs[("S'", key)] for key in keys}, **extra}
    def settle(attempt, result):
        if consume and (result.get('registered') if current else result.get('reason') != 'not_full_touch'):
            chosen_items = ([row for row in items if row['task_id'] in set(result['selected_ids'])]
                            if current else items)
            st.services.registry.decide(st.namespace, st.bench, chosen_items, unit=st.label(name),
                run_root=str(st.setting.root), attempt=u.attempt_number(attempt))
    if current:
        key = 'card-c' + name.rsplit('-c', 1)[1] if '-c' in name else name
        def candidate_rejected(event):
            rule = {**no_change_rule(len(evaluation['selected_ids']) or len(items)),
                    'reason': 'candidate_error', 'clause': 'candidate_error'}
            return {'rule': rule, 'decision': 'reject', 'reason': 'candidate_error', 'candidate_error': event,
                'faults': [event], 'cells': evaluation['cells'], 'reused_cells': 0,
                'request_signatures': evaluation['signatures'], 'candidate_sha256': candidate.sha256,
                'incumbent_sha256': incumbent.sha256, 'parent_cells': {}, 'candidate_cells': {},
                'cross_gate': evaluation['gate'], 'selected_ids': evaluation['selected_ids'],
                'registered': evaluation['registered'], 'selection': None}
        work = candidate_guard.guard(st, key, incumbent, work, candidate_rejected)
    return st.unit(name, work, settle=settle if consume else None)


def acceptance(st, cut, candidate, *, unit, incumbent):
    return measure(st, cut['accept'], incumbent, candidate, name=unit, kind='accept',
                   runs=p.slice_spec(p.configuration_of(st.setting) if p.is_v226(p.configuration_of(st.setting))
                                     else p.MAIN_V9, st.bench)['accept'][1], consume=True, cross=True)


def place_card(parent, card, *, step):
    from .package import with_, withhold
    from . import v225_cards as cards
    route = cards.metadata(card)['route']
    old = parent.card_for(route)
    base = withhold(parent, [old.id]) if old is not None else parent
    return with_(base, step=step, add=(card,))


def admit_cross(parent, candidate, target, gate):
    """A failed or occupied-slot cross copy can never alter the package."""
    require(parent.card_for(target) is None, 'Cross cards require an empty target card slot')
    return candidate if gate['passed'] else parent


def cross_cards(st, incumbent, card):
    from . import v225_cards as cards, v222_runtime
    from .package import save, load
    meta = cards.metadata(card)
    require(meta['home'] == meta['route'] == st.bench, 'Never re-export a cross card')
    records = []
    targets = [b for pair in p.SIMILAR_PAIRS_BY_CONFIGURATION[
        p.configuration_of(st.setting) if p.is_v226(p.configuration_of(st.setting)) else p.MAIN_V9] if st.bench in pair
               for b in pair if b != st.bench]
    for j, target in enumerate(targets):
        if incumbent.card_for(target) is not None:
            records.append({'target': target, 'decision': 'occupied_slot', 'calls': 0})
            continue
        copied = cards.make_card(st.bench, meta['text'], route=target, k=st.k, ordinal=110+j,
            evidence=st.evidence, writer_sha256=card.lineage['engineer_call'])
        candidate = place_card(incumbent, copied, step=st.name)
        before = incumbent
        name = 'card-cross-' + target
        def work(attempt):
            chosen, gate = v222_runtime.cross_gate(st, attempt, unit=name, phase='cross_card',
                                                    parent=before, candidate=candidate)
            if p.is_v226(p.configuration_of(st.setting)):
                with _system_context(st):
                    selected = admit_cross(before, candidate, target, gate)
                    require(gate['parent_sha256'] == before.sha256 and gate['proposed_sha256'] == candidate.sha256
                            and (chosen.sha256 if chosen is not None else None) ==
                                (candidate.sha256 if gate['passed'] else None),
                            'Cross cards bind the exact parent and candidate and cannot be narrowed')
                    save(st.chain_root, selected)
                    write_json(attempt / 'v225-cross-card.json', gate)
            else:
                selected = admit_cross(before, candidate, target, gate)
                require(gate['parent_sha256'] == before.sha256 and gate['proposed_sha256'] == candidate.sha256
                        and (chosen.sha256 if chosen is not None else None) ==
                            (candidate.sha256 if gate['passed'] else None),
                        'Cross cards bind the exact parent and candidate and cannot be narrowed')
                save(st.chain_root, selected)
                write_json(attempt / 'v225-cross-card.json', gate)
            return {'target': target, 'gate': gate, 'package_sha256': selected.sha256}
        if p.is_v226(p.configuration_of(st.setting)):
            from . import v226_candidates
            def reject_cross(event):
                return {'target': target, 'decision': 'reject', 'reason': 'candidate_error',
                    'candidate_error': event, 'package_sha256': before.sha256,
                    'parent_sha256': before.sha256, 'proposed_sha256': candidate.sha256}
            work = v226_candidates.guard(st, 'cross-card-' + target, before, work, reject_cross)
        record = st.unit(name, work, benches=(target,))
        if p.is_v226(p.configuration_of(st.setting)) and record.get('candidate_error'):
            require(record['target'] == target and record['package_sha256'] == before.sha256
                    and record['parent_sha256'] == before.sha256 and record['proposed_sha256'] == candidate.sha256,
                    'A rejected cross card retains its exact incumbent')
            records.append(record)
            continue
        require(record['target'] == target and record['gate']['parent_sha256'] == before.sha256
                and record['gate']['proposed_sha256'] == candidate.sha256
                and record['package_sha256'] == (candidate.sha256 if record['gate']['passed'] else before.sha256),
                'A resumed cross card binds its exact pre-rebase packages')
        incumbent = load(st.chain_root / 'packages' / (record['package_sha256'] + '.json'))
        records.append(record)
    return incumbent, records


def cross_bindings(records, *, configuration=p.MAIN_V9):
    bindings = []
    for row in records:
        if 'gate' not in row:
            continue
        gate = p.verified(row['gate'], 'v222-cross-gate')
        require(gate['configuration'] == configuration and gate['phase'] == 'cross_card'
                and row['package_sha256'] == (gate['candidate_sha256'] if gate['passed'] else gate['parent_sha256']),
                'Card handoff binds the selected cross-gate candidate')
        bindings.append({'target': row['target'], 'gate_sha256': gate[p.RECORD_HASH],
            'parent_sha256': gate['parent_sha256'], 'proposed_sha256': gate['proposed_sha256'],
            'selected_package_sha256': row['package_sha256']})
    return bindings


def card_phase(st, cut):
    from . import step, rounds, v225_cards as cards, v225_writer as writer
    from .package import load, save, validate
    require(p.is_v225(p.configuration_of(st.setting)) and st.bench in CARD_ACCEPT_ITEMS,
            'Only the four learned benches have a main-v9 card phase')
    path = st.root / 'card-phase.json'
    if path.exists():
        record = (_read_record(st, path, 'v225-card-phase') if p.is_v226(p.configuration_of(st.setting))
                  else p.verified(read_json(path), 'v225-card-phase'))
        require(record['parent_sha256'] == st.parent.sha256, 'Card phase resumes the same step parent')
        st.card_phase_record = record
        st.card_incumbent = load(st.chain_root / 'packages' / (record['package_sha256'] + '.json'))
        selected = load(st.chain_root / 'packages' / (record['handoff']['selected_package_sha256'] + '.json'))
        rebased = selected if selected.sha256 == st.parent.sha256 else replace(selected, parent_sha256=st.parent.sha256)
        require(record['handoff']['step_parent_sha256'] == st.parent.sha256
                and record['handoff']['package_sha256'] == rebased.sha256 == st.card_incumbent.sha256
                and record['handoff']['cross_gate_bindings'] == cross_bindings(record['cross_cards'], **({'configuration': p.configuration_of(st.setting)}
                    if p.is_v226(p.configuration_of(st.setting)) else {})),
                'Card handoff retains the gated package contents')
        if rebased.sha256 != st.parent.sha256:
            validate(rebased, st.parent)
        return st.card_incumbent, record
    incumbent, previous, feedback, cached = st.parent, None, None, None
    run_rows = step._run_trajectories(st, parent_only=True)
    rows = run_rows
    allowed = {rounds.key(st.bench, row['task_id']) for row in cut['run']}
    record = {'parent_sha256': st.parent.sha256, 'rounds': [], 'final_card': None,
              'accepted_training_unit': None, 'cross_cards': [], 'procedure_phase': 'pending',
              'configuration': p.configuration_of(st.setting) if p.is_v226(p.configuration_of(st.setting)) else p.MAIN_V9}
    for c in range(1, CARD_ROUNDS + 1):
        references = step._references(st, cut, rows)
        def write(attempt):
            result = writer.write(st.roles('card_writer'), chain=st.chain, bench=st.bench, k=st.k, c=c,
                incumbent=incumbent, rows=rows, references=references, allowed_ids=allowed,
                corpus=step._corpora(st, cut), practice_ids=[row['task_id'] for row in st.setting.pools[st.bench]],
                runtime=st.setting.runtime, previous_card=previous, result=feedback, label=st.label('card-write-c%d' % c),
                state_root=st.chain_root / 'card-writer',
                **({'configuration': p.configuration_of(st.setting)}
                   if p.is_v226(p.configuration_of(st.setting)) else {}))
            call_path = attempt / 'card-writer.json'
            write_json(call_path, result['call_record'])
            # The lineage is the exact sealed call-record file, not a display text.
            result['writer_sha256'] = hashlib.sha256(call_path.read_bytes()).hexdigest()
            return result
        proposed = st.unit('card-write-c%d' % c, write)
        line = {'round': c, 'writer_sha256': proposed['writer_sha256'], 'static': proposed['static']}
        record['rounds'].append(line)
        text = proposed.get('text')
        if not text:
            previous = proposed.get('call_record', {}).get('card') or previous or ''
            feedback = {'stage': 'static', 'decision': 'reject', 'clause': proposed['static']}
            line['decision'] = 'card_rejected_static'
            # No preceding candidate cells exist after a static rejection.
            rows = run_rows
            continue
        previous = text
        card = cards.make_card(st.bench, text, k=st.k, round=c, evidence=st.evidence,
                               writer_sha256=proposed['writer_sha256'])
        candidate = place_card(incumbent, card, step=st.name)
        candidate = replace(candidate, parent_sha256=st.parent.sha256)
        shell = st.setting.cards[st.bench]
        if cards.compose(st.bench, shell, candidate) == cards.compose(st.bench, shell, incumbent):
            line.update(decision='card_unchanged', reason='unchanged_composed_guidance',
                        training=count_feedback(no_change_rule(len(cut['run'])), 'training'))
            feedback, rows = line['training'], run_rows
            continue
        save(st.chain_root, candidate)
        trained = measure(st, cut['run'], incumbent, candidate, name='card-train-c%d' % c,
            kind='selftest', runs=p.slice_spec(p.configuration_of(st.setting) if p.is_v226(p.configuration_of(st.setting))
                                             else p.MAIN_V9, st.bench)['run'][1], cached=cached)
        cached = trained
        line['training'] = count_feedback(trained, 'training')
        if p.is_v226(p.configuration_of(st.setting)) and trained.get('candidate_error'):
            line.update(decision='reject', reason='candidate_error', candidate_error=trained['candidate_error'])
            feedback, rows = line['training'], run_rows
            continue
        if trained.get('reason') == 'not_full_touch':
            line.update(decision='card_not_full_touch', reason='unchanged_rendered_requests')
            feedback, rows = line['training'], run_rows
            continue
        rows = [row for row in step._unit_trajectories(st, 'card-train-c%d' % c) if row['arm'] == "S'"]
        for row in rows:
            row['card_fixed'] = row['task_id'] in trained['rule']['fixed_items']
            row['card_broken'] = row['task_id'] in trained['rule']['broken_items']
        if trained['decision'] != 'accept':
            feedback = line['training']
            continue
        if st.bench == 'searchqa':
            if p.is_v226(p.configuration_of(st.setting)):
                confirmed = measure(st, cut['accept'], incumbent, candidate, name='card-confirm-c%d' % c,
                    kind='confirm', runs=1, consume=True, selection=(cut, c, 'confirm'))
                if confirmed['reason'] == 'supply_exhausted':
                    line['decision'] = 'card_supply_exhausted'
                    break
                if confirmed['reason'] == 'not_full_touch':
                    line['decision'] = 'card_not_full_touch'
                    feedback = count_feedback(confirmed, 'confirmation')
                    continue
            else:
                selected, selection = select(st, cut, c, 'confirm', incumbent, candidate)
                if len(selected) != CARD_CONFIRM_ITEMS:
                    line['decision'] = 'card_supply_exhausted'
                    break
                if len(selection['touched']) != CARD_CONFIRM_ITEMS:
                    line['decision'] = 'card_not_full_touch'
                    feedback = count_feedback(no_change_rule(len(selected), len(selection['touched'])), 'confirmation')
                    continue
                confirmed = measure(st, selected, incumbent, candidate, name='card-confirm-c%d' % c,
                                    kind='confirm', runs=1, consume=True)
            line['confirmation'] = count_feedback(confirmed, 'confirmation')
            if p.is_v226(p.configuration_of(st.setting)) and confirmed.get('candidate_error'):
                line.update(decision='reject', reason='candidate_error', candidate_error=confirmed['candidate_error'])
                feedback, rows = line['confirmation'], run_rows
                continue
            if confirmed['decision'] != 'accept':
                feedback = line['confirmation']
                continue
        else:
            line['confirmation'] = 'not_applicable_supply'
        if p.is_v226(p.configuration_of(st.setting)):
            accepted = measure(st, cut['accept'], incumbent, candidate, name='card-accept-c%d' % c,
                kind='accept', runs=p.slice_spec(p.configuration_of(st.setting), st.bench)['accept'][1],
                consume=True, cross=True, selection=(cut, c, 'accept'))
            if accepted['reason'] == 'supply_exhausted':
                line['decision'] = 'card_supply_exhausted'
                break
            if accepted['reason'] == 'not_full_touch':
                line['decision'] = 'card_not_full_touch'
                feedback = count_feedback(accepted, 'acceptance')
                continue
        else:
            selected, selection = select(st, cut, c, 'accept', incumbent, candidate)
            if len(selected) != CARD_ACCEPT_ITEMS[st.bench]:
                line['decision'] = 'card_supply_exhausted'
                break
            if len(selection['touched']) != CARD_ACCEPT_ITEMS[st.bench]:
                line['decision'] = 'card_not_full_touch'
                feedback = count_feedback(no_change_rule(len(selected), len(selection['touched'])), 'acceptance')
                continue
            accepted = step._accept(st, {**cut, 'accept': selected, 'accept_probe': []}, candidate, None,
                                    unit='card-accept-c%d' % c, incumbent=incumbent)
        line['acceptance'] = count_feedback(accepted, 'acceptance')
        if p.is_v226(p.configuration_of(st.setting)) and accepted.get('candidate_error'):
            line.update(decision='reject', reason='candidate_error', candidate_error=accepted['candidate_error'])
            feedback, rows = line['acceptance'], run_rows
            continue
        if accepted['decision'] == 'accept':
            incumbent, cross = cross_cards(st, candidate, card)
            record.update(final_card={'id': card.id, 'sha256': card.sha256},
                accepted_training_unit='card-train-c%d' % c, acceptance_unit='card-accept-c%d' % c,
                cross_cards=cross)
            line['decision'] = 'accept'
            break
        feedback = line['acceptance']
        if p.is_v226(p.configuration_of(st.setting)) and accepted['reason'] == 'cross_bench_harm':
            line.update(decision='reject', reason='cross_bench_harm', cross_gate=accepted['cross_gate'])
            continue
        if st.bench != 'searchqa':
            line['decision'] = 'card_supply_exhausted'
            break
    used = used_acceptance(st)
    exhausted = all(item['task_id'] in used for item in cut['accept'])
    selected_sha256 = incumbent.sha256
    if incumbent.sha256 != st.parent.sha256:
        incumbent = replace(incumbent, parent_sha256=st.parent.sha256)
        validate(incumbent, st.parent)
    record.update(package_sha256=incumbent.sha256, consumed_acceptance=sorted(used),
        handoff={'step_parent_sha256': st.parent.sha256, 'selected_package_sha256': selected_sha256,
            'package_sha256': incumbent.sha256,
            'cross_gate_bindings': cross_bindings(record['cross_cards'], **({'configuration': p.configuration_of(st.setting)}
                    if p.is_v226(p.configuration_of(st.setting)) else {}))},
        procedure_phase='skipped_pool_exhausted' if exhausted else 'run')
    record = p.record('v225-card-phase', st.evidence, record)
    save(st.chain_root, incumbent)
    write_json(path, record)
    st.card_phase_record, st.card_incumbent = record, incumbent
    return incumbent, record


def authored_phase_smoke(root, *, bench='searchqa', scenario='accept', configuration=p.MAIN_V9):
    """Exercise the real controller and handoff with authored cells, zero services.

    The injected boundaries are the writer transport, cell dispatch and external
    cross-gate runtime. Selection, static screening, decisions, package writes,
    the cross-gain rule and the procedure controller are production functions.
    This fixture is engineering evidence, never an estimated method effect.
    """
    from contextlib import ExitStack, nullcontext
    from copy import copy
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    from skillopt.validator_pilot.api import digest
    from . import step, rounds, v225_cards as cards, v222_cards, v222_gate, v222_runtime
    from .package import empty, save, with_

    require(bench in CARD_ACCEPT_ITEMS and scenario in ('accept', 'static', 'training', 'confirmation',
        'acceptance', 'all_training', 'cross_reject', 'replacement', 'exhausted'), 'An authored card scenario')
    require(scenario != 'confirmation' or bench == 'searchqa', 'Only SearchQA confirms cards')

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    def pool(bench, n, prefix):
        if not p.is_v226(configuration):
            return [{'task_id': '%s-%03d' % (prefix, i), 'benchmark': bench, 'partition': 'practice',
                     'public': {'question': 'Authored public question.', 'context': ['Authored public evidence.']},
                     'private': {'answer': 'authored'}} for i in range(n)]
        public = {'question': 'Authored public question.', 'context': ['Authored public evidence.']}
        if p.is_v226(configuration):
            if bench == p.ZEBRA:
                public = {'question': 'There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. Compare the clues.',
                          'columns': ['Name', 'Color']}
            elif bench == 'spreadsheetbench':
                from openpyxl import Workbook
                workbook = root / 'authored-input.xlsx'
                if not workbook.exists():
                    book = Workbook()
                    book.active['A1'] = 'Authored value'
                    book.save(workbook)
                public = {'instruction': 'Copy A1 to B1.', 'input_files': [str(workbook)], 'answer_position': 'B1'}
            elif bench == 'alfworld':
                view = step.solver.alfworld_routing_view('You are in a room.', ['look'])
                public = {'game_file': '/authored/game.tw-pddl', 'routing_view': view,
                          'routing_view_sha256': digest(view)}
        return [{'task_id': '%s-%03d' % (prefix, i), 'benchmark': bench, 'partition': 'practice',
                 'public': public, 'private': {'answer': 'authored'}} for i in range(n)]
    spec = p.slice_spec(configuration, bench)
    cut = {'run': pool(bench, spec['run'][0], 'practice'), 'accept': pool(bench, spec['accept'][0], 'decision'),
           'accept_probe': []}
    if scenario == 'exhausted':
        cut['accept'] = cut['accept'][:2]
    setting = SimpleNamespace(root=root, runtime={b:{} for b in p.MAIN_V5_ORDER}, pools={bench: cut['run'] + cut['accept']},
        cards={b:v222_cards.format_text(b) for b in p.MAIN_V5_ORDER},
        extra={'configuration': configuration}, evidence='engineering_fixture')
    registry = SimpleNamespace(**{name: lambda *a, **kw: None for name in ('register', 'dispatch', 'decide')})
    parent = empty(step='G/s0', evidence='engineering_fixture')
    if scenario == 'replacement':
        other = 'officeqa' if bench == 'searchqa' else 'searchqa' if bench == 'officeqa' else (
            'spreadsheetbench' if bench == 'zebralogic' else 'zebralogic')
        parent = with_(parent, step='G/s0', add=[cards.make_card(other,
            'An inherited cross card checks the supplied evidence.', route=bench, evidence='engineering_fixture')])
    services = (step.Services(registry=registry, sources=None, workers=lambda *a, **kw: nullcontext(None))
                if p.is_v226(configuration) else SimpleNamespace(registry=registry))
    st = step._Step(setting, services, 'G', bench, p.MAIN_V5_ORDER.index(bench)+1,
                    parent, root / 'G')
    st.root.mkdir(parents=True, exist_ok=True)
    save(st.chain_root, st.parent)
    completed, traces, dispatched, procedure_current = {}, {}, [], []
    class Roles:
        def __init__(self): self.calls = []
        def plain(self, role, system, user, *, label, max_tokens):
            self.calls.append({'role': role, 'label': label, 'request_sha256': digest([system,user]),
                               'max_tokens': max_tokens, 'evidence': 'engineering_fixture'})
            return 'x'*3001 if scenario == 'static' and 'card-write-c1' in label else (
                'Compare corroborating evidence and check what the question asks.')
    role = Roles()
    st.roles = lambda name: role
    st.solver = lambda *a, **kw: None
    st.runtime = lambda: {}
    def unit(name, work, *, benches=(), settle=None):
        require(name in st.units, 'Authored smoke uses registered production units')
        if name not in completed:
            attempt = st.root / name / 'attempt-1'
            attempt.mkdir(parents=True, exist_ok=True)
            result = work(attempt)
            write_json(attempt.parent / 'unit.json', p.record('unit', st.evidence, {'result': result}))
            completed[name] = result
            if settle: settle(attempt, result)
        return completed[name]
    st.unit = unit
    run_rows = [{'task_id': rounds.key(st.bench, item['task_id']), 'bench': st.bench,
        'unit': st.label('run'), 'arm': 'S', 'token': 'fail', 'run': 0,
        'view': 'Authored public evidence.', 'reply': 'An authored attempt.', 'evidence': st.evidence}
        for item in cut['run']]
    def signature(bench, package, key):
        return {'request_sha256': digest([key, cards.compose(bench, 'Fixed format.', package)]),
                'post_call': [], 'faults': []}
    def pair_signatures(_st, candidate, incumbent, publics, views, **kw):
        return {key: {'S': signature(st.bench, incumbent, key), "S'": signature(st.bench, candidate, key)}
                for key in publics}
    def cells(_st, attempt, endpoint, label, jobs, **kw):
        name = label.rsplit('/', 1)[-1]
        keys = list(dict.fromkeys(key for _,_,key,_,_ in jobs))
        floor = max(3, math.ceil(CARD_GAIN_SHARE * len(keys)))
        rejected = (scenario == 'training' and name == 'card-train-c1'
            or scenario == 'confirmation' and name == 'card-confirm-c1'
            or scenario == 'acceptance' and name == 'card-accept-c1'
            or scenario == 'all_training' and name.startswith('card-train'))
        if rejected:
            floor -= 1
        results, traces[name] = [], []
        for arm, package_arm, key, run, task in jobs:
            token = 'pass' if arm == "S'" and keys.index(key) < floor else 'fail'
            cell = {'cell': {'id': digest([label,arm,key,run]), 'arm': arm, 'task_id': key, 'run': run},
                'judge': {'v2': {'token': token}}, 'final': {'outcome': token, 'kind': 'score', 'remedy': None},
                'faults': [], 'stop': None}
            results.append(cell)
            traces[name].append({'task_id': key, 'bench': st.bench, 'unit': label, 'arm': arm,
                'run': run, 'token': token, 'cell': cell['cell']['id'], 'view': 'Authored public evidence.',
                'reply': 'An authored attempt.', 'evidence': st.evidence})
        dispatched.append({'unit': name, 'cells': len(results)})
        return results
    harms = {bench: pool(bench, n, 'harm') for bench,n in (
        ('searchqa',60),('officeqa',42),('zebralogic',60),('spreadsheetbench',55),('alfworld',20))}
    def inspector(bench,parent,candidate,items):
        if p.is_v226(configuration):
            other = copy(st)
            other.bench = bench
            return v222_gate.inspect(bench, parent, candidate, items,
                step._item_workers(other, {item['task_id']: item['public'] for item in items}),
                card_text=st.setting.cards[bench], runtime=st.runtime(), configuration=configuration)
        pairs = {item['task_id']: {'S': signature(bench,parent,item['task_id']),
                                   "S'": signature(bench,candidate,item['task_id'])} for item in items}
        fired = [key for key,pair in pairs.items() if not v221_rule.same_request(pair['S'],pair["S'"])]
        return {'bench':bench,'slice_ids':list(pairs),'fired':len(fired),'fired_items':fired,
            'signatures':pairs,'faults':[],'identity_proven':not fired,
            'parent_sha256':parent.sha256,'candidate_sha256':candidate.sha256}
    def cross(_st,attempt,*,unit,phase,parent,candidate):
        def pairs(bench,before,after,items):
            dispatched.append({'unit':unit,'bench':bench,'cells':2*len(items)})
            return {(arm,item['task_id']): [{'judge':{'v2':{'token':
                'pass' if arm == "S'" and index < (0 if scenario == 'cross_reject' else 3) else 'fail'}}}]
                for index,item in enumerate(items) for arm in ('S',"S'")}
        return v222_gate.check(home=st.bench,parent=parent,candidate=candidate,slices=harms,
            inspector=inspector,run_pairs=pairs,phase=phase,configuration=configuration)
    def engineer(_st,_cut,r,incumbent,**kwargs):
        from .engineer import Context, TRAIN
        current = step._current(st, kwargs['done'])
        accepted_unit = st.card_phase_record['accepted_training_unit']
        require(current and all(row['unit'] == st.label(accepted_unit) and row['arm'] == "S'"
                                for row in current), 'Procedure rounds receive accepted card S-prime cells')
        require(incumbent.card_for(st.bench) is not None, 'Procedure incumbent contains accepted card')
        def sealed(row):
            return p.record('trajectory', st.evidence, {key:value for key,value in row.items() if key != 'evidence'})
        # This is the real procedure-context boundary, including the candidate
        # parent check that catches an intermediate cross-card parent link.
        Context(bench=st.bench,k=st.k,step=st.name,evidence=st.evidence,parent=incumbent,
            trajectories=[sealed(row) for row in run_rows],corpora={},workers=None,roles=None,
            label=st.label('engineer-r%d'%r),card=st.setting.cards[st.bench],mode=TRAIN,round=r,
            base=st.parent,current=[sealed(row) for row in current],configuration=configuration)
        procedure_current.append({'round':r,'items':len(current),'source':accepted_unit})
        return {'candidate_sha256':None,'engineer':{'changes':[], 'analysis':{'items':[]},
                                                  'disclosed':[], 'lint':[]}}
    with ExitStack() as stack:
        for module,name,replacement in ((step,'_run_trajectories',lambda *a,**kw: run_rows),
            (step,'_unit_trajectories',lambda _st,name: traces.get(name,[])),
            (step,'_references',lambda *a:{}),(step,'_corpora',lambda *a:[]),
            (step.solver,'routing_view',lambda bench,public,**kw:public),
            (step,'_pair_signatures',pair_signatures),(step,'_cells',cells),
            (v222_runtime,'cross_gate',cross),(step,'_engineer_train',engineer)):
            if p.is_v226(configuration) and name in ('routing_view', '_pair_signatures'):
                continue
            stack.enter_context(patch.object(module,name,replacement))
        package,record = card_phase(st,cut)
        if record['final_card'] or record['procedure_phase'] == 'skipped_pool_exhausted':
            inherited,procedure_rounds,_ = step._train(st,cut,None)
            require(package.sha256 == inherited.sha256, 'Procedure rounds retain accepted cards')
        else:
            procedure_rounds = []
    if scenario == 'accept':
        require(len(record['rounds']) == 1 and record['final_card'] is not None and len(role.calls) == 1,
                'Authored controller exercises first acceptance and gated cross transfer')
    if scenario == 'exhausted':
        require(record['rounds'][-1]['decision'] == 'card_supply_exhausted'
                and record['procedure_phase'] == 'skipped_pool_exhausted' and not procedure_rounds,
                'An exhausted practice pool stops before procedure rounds')
    if scenario == 'replacement':
        require(cards.metadata(package.card_for(bench))['home'] == bench
                and parent.card_for(bench).id != package.card_for(bench).id,
                'An accepted own-bench card replaces the inherited cross card')
    result = p.record('v225-authored-phase-smoke','engineering_fixture',{
        'passed':True,'configuration':configuration,'real_calls':0,'writer_calls_authored':len(role.calls),
        'card_phase_sha256':record[p.RECORD_HASH],'package_sha256':package.sha256,
        'scenario':scenario,'bench':bench,'rounds':record['rounds'],
        'procedure_phase':record['procedure_phase'],'accepted_training_unit':record['accepted_training_unit'],
        'units':list(completed),'dispatches':dispatched,'consumed_acceptance':len(record['consumed_acceptance']),
        'cross_cards':record['cross_cards'],'procedure_rounds':procedure_current,
        'procedure_round_count':len(procedure_rounds),'patience':p.train_patience(configuration)})
    write_json(root/'v225-authored-phase.json',result)
    return result
