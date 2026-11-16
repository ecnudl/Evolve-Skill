"""main-v8 gate orchestration on the existing charged practice units.

No source supply is opened here: Setting already holds pinned practice records.
Only the registered home acceptance allocation is excluded from harm data.
"""
from __future__ import annotations

from copy import copy
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import profiles as p, supply, units, v222_gate
from .cells import Arm
from .package import load, save


def _read_record(configuration, path, kind=None):
    if p.is_v226(configuration):
        from .v226_candidates import read_record
        return read_record(path, kind)
    found = read_json(path)
    return p.verified(found, kind) if kind is not None else found


def _system(configuration):
    if p.is_v226(configuration):
        from .v226_candidates import arm
        return arm('system')
    return nullcontext()


def initial_package(st):
    from . import v222_read
    return v222_read.start_package(st.setting, st.chain)


def _training_allocations(setting):
    """D1: all pinned practice rows, except each bench's own acceptance IDs."""
    from . import step, zebralogic
    pools, excluded = {}, {}
    extra = setting.extra.get('v222_harm_pools', {})
    require(isinstance(extra, dict) and set(extra) <= set(v222_gate.BENCHES),
            'Additional harm supplies name registered benchmarks only')
    allocation = setting.extra.get('v211_allocation', {})
    for bench in v222_gate.BENCHES:
        rows = list(setting.pools.get(bench, ()))
        if bench in allocation:
            names = allocation[bench]['slices']
            excluded[bench] = list(names['accept'])
            if bench == 'searchqa' and setting.extra.get('searchqa_tail'):
                # The registered SearchQA confirmations live in the qualified
                # tail, alongside the acceptance allocation excluded below.
                from types import SimpleNamespace
                tail, _ = step._tail(SimpleNamespace(setting=setting))
                rows += list(tail)
        elif bench == 'zebralogic':
            cut = zebralogic.slices(rows)
            excluded[bench] = [row['task_id'] for row in cut['accept']]
        elif bench == 'alfworld':
            sizes = supply.registered_sizes(bench)
            cut = supply.slices(bench, rows, {name: sizes[name] for name in ('run', 'accept')})
            excluded[bench] = [row['task_id'] for row in cut['accept']]
        else:
            require(False, 'main-v8 requires the registered acceptance allocation for ' + bench)
        require(len(excluded[bench]) == len(set(excluded[bench])), 'Distinct registered acceptance IDs')
        by_id = {}
        for row in rows + list(extra.get(bench, ())):
            key = row['task_id']
            require(key not in by_id or by_id[key] == row, 'Repeated practice IDs must have identical records')
            by_id[key] = row
        protected = set(excluded[bench])
        pools[bench] = [by_id[key] for key in sorted(by_id) if key not in protected]
    return pools, excluded


def routing_allocations(setting):
    """Overlay selected ALF routing views while preserving D1's raw allocation."""
    from . import v222_alf_views, v222_cards
    require(p.is_v222(p.configuration_of(setting)), 'The routing overlay is main-v8 only')
    pools, excluded = _training_allocations(setting)
    harms = v222_gate.harm_slices(pools, excluded=excluded)
    decomposition = v222_cards.decomposition_slices({bench: [row['task_id'] for row in rows]
                                                    for bench, rows in pools.items()})
    overlay = setting.extra.get('v222_practice', {}).get(v222_alf_views.KEY)
    pools['alfworld'] = v222_alf_views.attach(pools['alfworld'], overlay, harms=harms['alfworld'],
        decomposition=decomposition['alfworld'], runtime=setting.runtime['alfworld'],
        configuration=p.configuration_of(setting))
    return pools, excluded


def preflight(setting):
    """Require and pin all fixed practice harm slices before any solver call."""
    from skillopt.coevo5.cells import exclusive
    require(p.is_v222(p.configuration_of(setting)), 'main-v8 harm preflight is opt-in')
    pools, excluded = routing_allocations(setting)
    counts = v222_gate.practice_supply(pools, excluded=excluded)
    expected = setting.extra.get('v222_practice', {}).get('v222_practice_supply')
    if expected is not None:
        require(counts == expected, 'The registered actual main-v8 practice counts changed')
    slices = v222_gate.harm_slices(pools, excluded=excluded)
    registered = v222_gate.registration(slices, configuration=p.configuration_of(setting))
    expected_harm = setting.extra.get('v222_practice', {}).get('harm')
    if expected_harm is not None:
        require(registered == expected_harm, 'The main-v8 harm slices differ from S0 registration')
    path = safe_path(setting.shared) / 'v222-harm-slices.json'
    with exclusive(path.with_suffix('.lock'), wait=True):
        if path.exists():
            if p.is_v226(p.configuration_of(setting)):
                require(_read_record(p.configuration_of(setting), path) == registered,
                        'The fixed main-v8 harm slices changed after registration')
            else:
                require(read_json(path) == registered, 'The fixed main-v8 harm slices changed after registration')
        else:
            write_json(path, registered)
    return slices, registered


def _resume_pairs(st, attempt, *, unit, binding):
    """Reuse completed scored practice cells only under the exact request binding."""
    from . import step
    root = Path(attempt).parent
    pin = root / ('v222-cross-' + binding['bench'] + '.json')
    if pin.exists():
        if p.is_v226(p.configuration_of(st.setting)):
            require(_read_record(p.configuration_of(st.setting), pin) == binding,
                    'A cross-gate retry keeps its original packages and slice')
        else:
            require(read_json(pin) == binding, 'A cross-gate retry keeps its original packages and slice')
    else:
        write_json(pin, binding)
    found = {}
    for path in sorted(root.glob('attempt-*/cells/*.json')):
        row = (_read_record(p.configuration_of(st.setting), path, 'cell')
               if p.is_v226(p.configuration_of(st.setting)) else p.verified(read_json(path), 'cell'))
        cell = row['cell']
        if (cell['unit'] == unit and cell['task_id'] in binding['items']
                and cell['arm'] in ('S', "S'") and cell.get('run') == 0
                and step._confirm_cell_reusable(row, cell['task_id'])):
            found[(cell['arm'], cell['task_id'])] = [row]
    return found


def cross_gate(st, attempt, *, unit, phase, parent, candidate):
    """Execute one bounded gate inside its confirmation/acceptance unit attempt."""
    from . import step, v222_limits
    require(p.is_v222(p.configuration_of(st.setting)), 'Cross-gate orchestration is opt-in')
    configuration = p.configuration_of(st.setting)
    cross_card = p.is_v225(configuration) and phase == 'cross_card'
    require(phase in ('confirmation', 'acceptance') or cross_card, 'A charged home decision phase')
    slices, registered = preflight(st.setting)
    kind = 'confirm' if phase == 'confirmation' or cross_card else 'accept'
    roots = list(st.root.glob(kind + '-r*/v222-cross-completed.json'))
    limit = v222_limits.maximum_candidates(p, st.bench, kind)
    current = Path(attempt).parent / 'v222-cross-completed.json'
    if current.exists():
        recorded = (_read_record(configuration, current, 'v222-cross-gate') if p.is_v226(configuration)
                    else p.verified(read_json(current), 'v222-cross-gate'))
        require(recorded['phase'] == phase and recorded['parent_sha256'] == parent.sha256
                and recorded['proposed_sha256'] == candidate.sha256
                and recorded['configuration'] == configuration and recorded['home'] == st.bench
                and recorded['unit'] == st.label(unit)
                and recorded['harm_registration_sha256'] == registered['sha256'],
                'A completed cross gate binds its original candidate, parent and harm slices')
        if p.is_v226(configuration):
            with _system(configuration):
                selected = (load(st.chain_root / 'packages' / (recorded['candidate_sha256'] + '.json'))
                            if recorded['candidate_sha256'] is not None else None)
        else:
            selected = (load(st.chain_root / 'packages' / (recorded['candidate_sha256'] + '.json'))
                        if recorded['candidate_sha256'] is not None else None)
        write_json(Path(attempt) / 'v222-cross-gate.json', recorded)
        return selected, recorded
    if cross_card:
        roots = list(st.root.glob('card-cross-*/v222-cross-completed.json'))
        limit = len([b for pair in p.SIMILAR_PAIRS_BY_CONFIGURATION[configuration] if st.bench in pair
                     for b in pair if b != st.bench])
    elif p.is_v225(configuration) and unit.startswith('card-accept-'):
        roots = list(st.root.glob('card-accept-*/v222-cross-completed.json'))
        from .v225_phase import CARD_ROUNDS
        limit = CARD_ROUNDS
    require(len({path.parent.name for path in roots} | {current.parent.name}) <= limit,
            'The registered maximum number of cross-gated candidates is exhausted')
    new_calls, reused_calls = 0, 0

    def inspect(bench, before, after, items):
        other = copy(st)
        other.bench = bench
        publics = {row['task_id']: row['public'] for row in items}
        if p.is_v226(configuration):
            from skillopt.validator_pilot.api import digest
            from . import solver, v226_bindings
            views = {key: solver.routing_view(bench, public, runtime=st.runtime(bench))
                     for key, public in publics.items()}
            core = {'configuration': configuration, 'phase': phase, 'home': st.bench, 'bench': bench,
                'unit': st.label(unit), 'parent_sha256': before.sha256, 'candidate_sha256': after.sha256,
                'proposed_sha256': candidate.sha256, 'slice_ids': [row['task_id'] for row in items],
                'harm_registration_sha256': registered['sha256'], 'routing_views_sha256': digest(views),
                'card_sha256': digest(st.setting.cards.get(bench, '')), 'runtime_sha256': digest(st.runtime(bench)),
                'workbook_sha256': v226_bindings.workbook_digests(bench, publics)}
            suffix = bench if after.sha256 == candidate.sha256 else 'narrowed-' + bench
            pin = Path(attempt).parent / ('v226-cross-inspection-' + suffix + '.json')
            if pin.exists():
                saved = _read_record(configuration, pin, 'v226-cross-inspection')
                require(saved['core'] == core, 'A redo keeps its deterministic cross inspection inputs')
                return saved['inspection']
        if not p.is_v226(configuration):
            return v222_gate.inspect(bench, before, after, items, step._item_workers(other, publics),
                card_text=st.setting.cards.get(bench, ''), runtime=st.runtime(bench),
                configuration=p.configuration_of(st.setting))
        found = v222_gate.inspect(bench, before, after, items, step._item_workers(other, publics),
            card_text=st.setting.cards.get(bench, ''), runtime=st.runtime(bench),
            configuration=configuration, **({'views': views} if p.is_v226(configuration) else {}))
        if p.is_v226(configuration):
            with _system(configuration):
                saved = p.record('v226-cross-inspection', st.evidence, {'core': core, 'inspection': found})
                write_json(pin, saved)
        return found

    def run_pairs(bench, before, after, items):
        nonlocal new_calls, reused_calls
        name = st.label(unit) + '/cross-' + bench
        binding = {'configuration': configuration, 'phase': phase, 'bench': bench,
            'parent_sha256': before.sha256, 'candidate_sha256': after.sha256,
            'items': [row['task_id'] for row in items], 'harm_registration_sha256': registered['sha256']}
        cached = _resume_pairs(st, attempt, unit=name, binding=binding)
        jobs = []
        for row in items:
            key = row['task_id']
            task = {'benchmark': bench, 'public': row['public'], 'private': row['private']}
            for arm, arm_kind, package in (('S', 'parent', before), ("S'", 'candidate', after)):
                if (arm, key) not in cached:
                    jobs.append((arm, Arm(arm_kind, package), key, 0, task))
        endpoint = st.solver(kind, attempt, cell_bench=bench)
        if p.is_v226(configuration):
            found = step._system_cells(st, attempt, {bench: endpoint}, name, jobs, tag='v222-cross') if jobs else []
        else:
            found = step._cells(st, attempt, {bench: endpoint}, name, jobs, tag='v222-cross') if jobs else []
        reused_calls += len(cached)
        new_calls += len(found)
        for row in found:
            cached[(row['cell']['arm'], row['cell']['task_id'])] = [row]
        return cached

    selected, record = v222_gate.check(home=st.bench, parent=parent, candidate=candidate,
        slices=slices, inspector=inspect, run_pairs=run_pairs, phase=phase,
        configuration=p.configuration_of(st.setting),
        registered_counts={bench: row['items'] for bench, row in registered['benches'].items()})
    if selected is not None:
        save(st.chain_root, selected)
    fields = {key: value for key, value in record.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    record = p.record('v222-cross-gate', st.evidence, {**fields,
        'harm_registration_sha256': registered['sha256'], 'new_model_cells': new_calls,
        'reused_model_cells': reused_calls, 'unit': st.label(unit)})
    write_json(Path(attempt) / 'v222-cross-gate.json', record)
    write_json(current, record)
    return selected, record


def confirmation(st, attempt, *, unit, parent, candidate, result):
    """Attach a mandatory cross decision and retain the home decision's meaning."""
    selected, gate = cross_gate(st, attempt, unit=unit, phase='confirmation', parent=parent, candidate=candidate)
    home = dict(result['confirm'])
    if not gate['passed']:
        home.update(passed=False, reason='cross_bench_harm')
    return {**result, 'confirm': home, 'cross_gate': gate,
            'accepted_candidate_sha256': selected.sha256 if selected is not None else None}


def confirmed_candidate(st, candidate, result):
    """Use only the package named by the completed cross-gate result."""
    gate = result.get('cross_gate')
    require(isinstance(gate, dict) and gate['proposed_sha256'] == candidate.sha256,
            'main-v8 confirmation requires its own candidate-bound cross gate')
    if not gate['passed']:
        return candidate
    sha = result['accepted_candidate_sha256']
    if p.is_v226(p.configuration_of(st.setting)):
        with _system(p.configuration_of(st.setting)):
            selected = load(st.chain_root / 'packages' / (sha + '.json'))
    else:
        selected = load(st.chain_root / 'packages' / (sha + '.json'))
    require(selected.sha256 == gate['candidate_sha256'], 'The narrowed package matches the cross gate')
    return selected


def bind_training(result, candidate, confirmation):
    """Narrowing off-home preserves measured home requests, with explicit provenance."""
    gate = confirmation.get('cross_gate')
    require(gate is not None, 'A main-v8 confirmation carries its cross gate')
    return {**result, 'home_measured_candidate_sha256': result['candidate_sha256'],
            'candidate_sha256': candidate.sha256, 'cross_gate': gate,
            'feedback': {**result['feedback'], 'cross_gate': {
                'passed': gate['passed'], 'benches': {bench: {key: row[key] for key in
                    ('fired', 'passed', 'fixed', 'broken', 'net') if key in row}
                    for bench, row in gate['benches'].items()}}}}


def hygiene_candidate(st, cut, r, incumbent, current):
    """One controller proposal occupies this round's ordinary candidate slot."""
    if p.is_v225(p.configuration_of(st.setting)):
        return None, {'hygiene_mode': 'off_no_p0'}
    from . import engineer, rounds, v222_cards, v222_hygiene
    from .errors import PackageInvalid
    require(p.is_v222(p.configuration_of(st.setting)), 'Only main-v8 has card hygiene')
    original = initial_package(st)
    own = [proc.id for proc in v222_cards.own_segments(original, st.bench)]
    allowed = {rounds.key(st.bench, row['task_id']) for row in cut['run']}
    whole = st.bench in st.setting.extra.get('v222_fallbacks', {}).get(st.chain, ())
    candidate, record = v222_hygiene.propose(incumbent, bench=st.bench, own_segments=own,
        parent_cells=[row for row in current if row.get('task_id') in allowed], whole_card=whole)
    record.update(round=r, incumbent_sha256=incumbent.sha256)
    if candidate is not None:
        try:
            candidate = engineer.rebase(candidate, st.parent, incumbent, step=st.name)
        except PackageInvalid:
            record.update(reason='existing_step_edit_budget', selected=None, confirmation_candidates=0)
            record.pop('candidate_sha256', None)
            return None, record
        record['candidate_sha256'] = candidate.sha256
    return candidate, record


def hygiene_engineered(st, r, incumbent, candidate, record):
    """Honest registrar-authored deletion metadata; no fabricated role/audit call."""
    from types import SimpleNamespace
    from . import engineer, step, v222_hygiene
    pid = record['selected']
    require(pid in incumbent.order and pid not in candidate.order,
            'The ordinary hygiene candidate removes its selected own segment')
    save(st.chain_root, candidate)
    sealed = p.record('engineer', st.evidence, {
        'bench': st.bench, 'k': st.k, 'step': st.name, 'label': st.label('engineer-r%d' % r),
        'parent_sha256': incumbent.sha256, 'base_sha256': st.parent.sha256,
        'mode': step.TRAIN, 'round': r, 'source': 'card_hygiene_controller',
        'hygiene_mode': v222_hygiene.MODE, 'hygiene': record,
        'budget': engineer.budget(SimpleNamespace(base=st.parent, parent=incumbent)),
        'changes': [{'n': 1, 'kind': 'deletion', 'id': None, 'target': pid,
                     'procedure_sha256': None, 'engineer_call': None, 'survived': True,
                     'attempts': [], 'summary': 'Measured deletion of an own P0 segment.', 'fix_calls': 0}],
        'analysis': {'items': [], 'calls': []}, 'disclosed': [], 'lint': [], 'dropped': [],
        'kept': [1], 'audits': [], 'calls': 0, 'proposals': [],
        'package_checks': ['unchanged_package_validation', 'unchanged_step_edit_budget']})
    return {'engineer': sealed, 'candidate_sha256': candidate.sha256,
            'learning': step.TRAIN, 'round': r, 'hygiene': record}
