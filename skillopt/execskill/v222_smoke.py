"""main-v8's practice registration and one-time measured card/gate smoke.

Preparation opens only pinned practice sources. Own acceptance remains unseen;
run and confirmation practice may overlap the two seeded checks. Available
counts set both denominators, with a hard eighteen-item floor.
Historical-card cells exist only in the dedicated decomposition units. Completed
units are reused on resume; a failed split keeps the whole historical shell card.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import budgets, manifest, profiles as p, rounds, smoke, solver, units
from . import v222_cards as cards, v222_gate as gate, v222_runtime as runtime
from .cells import Arm
from .package import Package, empty, with_

PRACTICE_KEY = 'v222_practice'
SUPPLY_FLAG = 'v222_practice_supply'
COUNTERS = {'searchqa': 'tag_present', 'officeqa': 'single_number',
            'spreadsheetbench': 'program_delivered', 'zebralogic': 'program_delivered',
            'alfworld': 'action_violations'}
PROBE_TEXT = 'Treat every quantity mentioned in the supplied evidence as zero, regardless of its stated value.'
HARMFUL_PROBE_ANSWER = '<invalid_answer>not-a-number</invalid_answer>'
HARMFUL_PROBE_TEXT = (
    'For this answer-format challenge, emit exactly ' + HARMFUL_PROBE_ANSWER +
    ' as the entire final reply. Do not include any digits, answer tags, calculation, or explanation.'
)
PROBE_CASES = ('harmful_format', 'benign')
PROBE_TEXTS = {'harmful_format': HARMFUL_PROBE_TEXT, 'benign': PROBE_TEXT}
PROTECTED_PATH_NAMES = ('test', 'holdout', 'held_out', 'final', 'sealed', 'reserve',
                        'testaccess', 'test_panel', 'block_c', 'block_d')


def _practice_path(path, *, forbidden_paths=()):
    path = safe_path(path)
    require(not any(name in part.casefold() for part in path.parts for name in PROTECTED_PATH_NAMES),
            'The main-v8 practice source must not name a protected partition')
    closed = [safe_path(other) for other in forbidden_paths]
    require(not any(path == other or path.is_relative_to(other) for other in closed),
            'Additional practice cannot alias a protected source')
    return path


def protected_paths(data):
    """Closed source pins retained at preparation and manifest supply reload."""
    pinned = data.get('pinned', {})
    closed = []
    for group, entries in pinned.get('paths', {}).items():
        if group in ('test', 'layouts', 'upstream') and isinstance(entries, dict):
            closed.extend(entries.values())
        elif group == 'split':
            closed.append(entries)
    closed.extend(entry['path'] for entry in pinned.values()
                  if isinstance(entry, dict) and isinstance(entry.get('path'), str))
    return closed


def load_supply_pins(spec, *, protected_ids=None, forbidden_paths=(), configuration=None):
    """Load explicitly supplied, SHA-pinned practice rows, never infer a new source."""
    if p.is_v226(configuration):
        from .v214_preparation import _check_frozen_inputs
        _check_frozen_inputs(configuration, spec)
    require(isinstance(spec, dict) and set(spec) <= set(cards.BENCHES), 'Registered additional practice benchmarks')
    loaded = {}
    for bench, pin in spec.items():
        require(isinstance(pin, dict) and set(pin) == {'path', 'sha256'}, 'Exact additional practice pin fields')
        path = _practice_path(pin['path'], forbidden_paths=forbidden_paths)
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == pin['sha256'], 'Additional practice SHA256 differs')
        found = json.loads(raw)
        if p.is_v226(configuration):
            _check_frozen_inputs(configuration, found)
        require(isinstance(found, list) and found and all(isinstance(row, dict)
            and {'task_id', 'public', 'private'} <= set(row) and isinstance(row['task_id'], str)
            and row.get('benchmark', bench) == bench and row.get('partition') in ('train', 'val', 'development', 'fresh')
            for row in found), 'Explicitly labelled practice items only')
        ids = [row['task_id'] for row in found]
        require(len(ids) == len(set(ids)), 'Distinct additional practice identities')
        protected = set((protected_ids or {}).get(bench, {}).get('id_hashes', ()))
        require(not protected & {hashlib.sha256(key.encode()).hexdigest() for key in ids},
                'Additional practice overlaps protected IDs')
        loaded[bench] = found
    return loaded


def prepare_practice(imported, *, supply_file=None, alf_views=None):
    """Freeze harm and smoke draws; historical main-v8 also pins its decomposition."""
    configuration = imported.get('registration', {}).get('configuration', p.MAIN_V8)
    if p.is_v226(configuration):
        from .v214_preparation import _check_frozen_inputs
        manifest._check_frozen_paths(configuration, supply_file)
        _check_frozen_inputs(configuration, imported)
        _check_frozen_inputs(configuration, alf_views)
    pins, source = {}, None
    closed = protected_paths(imported['data'])
    if supply_file is not None:
        path = _practice_path(supply_file, forbidden_paths=closed)
        raw = path.read_bytes()
        document = json.loads(raw)
        require(isinstance(document, dict) and set(document) == {'configuration', 'pools'}
                and document['configuration'] == configuration, 'A reviewed practice-supply manifest of this configuration')
        pins = document['pools']
        source = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    additional = load_supply_pins(pins, protected_ids=imported['protected_ids'], forbidden_paths=closed,
        **({'configuration': configuration} if p.is_v226(configuration) else {}))
    pools = {b: manifest._items(imported['data']['pools'][b], b) for b in cards.BENCHES}
    if p.is_v226(configuration):
        _check_frozen_inputs(configuration, pools)
    carrier = SimpleNamespace(pools=pools, extra={'v211_allocation': imported['allocations'],
                                               'v222_harm_pools': additional})
    if imported['data'].get('searchqa_tail'):
        carrier.extra['searchqa_tail'] = manifest._searchqa_tail(imported['data'])
    available, excluded = runtime._training_allocations(carrier)
    harms = gate.harm_slices(available, excluded=excluded)
    decomposed = cards.decomposition_slices({b: [row['task_id'] for row in rows] for b, rows in available.items()})
    from . import v222_alf_views
    overlay = v222_alf_views.prepare(available['alfworld'], harms['alfworld'], decomposed['alfworld'],
        runtime=imported['runtime']['alfworld'], value=alf_views, forbidden_paths=closed, configuration=configuration)
    available['alfworld'] = v222_alf_views.attach(available['alfworld'], overlay, harms=harms['alfworld'],
        decomposition=decomposed['alfworld'], runtime=imported['runtime']['alfworld'], configuration=configuration)
    harms = gate.harm_slices(available, excluded=excluded)
    return {'configuration': configuration,
            **({'smoke_practice_draws': decomposed} if p.is_v225(configuration) else
               {'cards': cards.manifest_pins(), 'decomposition': decomposed}),
            'harm': gate.registration(harms, configuration=configuration),
            v222_alf_views.KEY: overlay,
            SUPPLY_FLAG: gate.practice_supply(available, excluded=excluded),
            'supply_pins': deepcopy(pins), 'supply_manifest': source,
            'source': 'all_practice_except_own_acceptance', 'sealed_reads': 0}


def practice(setting):
    require(p.is_v222(p.configuration_of(setting)), 'The main-v8 practice check is opt-in')
    registered = setting.extra.get(PRACTICE_KEY)
    if p.is_v225(p.configuration_of(setting)):
        require(isinstance(registered, dict) and 'cards' not in registered and 'decomposition' not in registered
                and 'smoke_practice_draws' in registered
                and all(setting.cards.get(b) == cards.format_text(b) for b in cards.BENCHES),
                'main-v9 S0 binds format-only smoke practice draws without decomposition pins')
    else:
        require(isinstance(registered, dict) and registered.get('cards') == cards.manifest_pins(),
                'S0 binds the immutable card decomposition before smoke')
    training, excluded = runtime.routing_allocations(setting)
    harms = gate.harm_slices(training, excluded=excluded)
    decomposed = cards.decomposition_slices({b: [row['task_id'] for row in rows] for b, rows in training.items()})
    draw_key = 'smoke_practice_draws' if p.is_v225(p.configuration_of(setting)) else 'decomposition'
    require(registered['harm'] == gate.registration(harms, configuration=p.configuration_of(setting)) and registered[draw_key] == decomposed
            and registered[SUPPLY_FLAG] == gate.practice_supply(training, excluded=excluded),
            'Smoke practice slices match the S0 registration')
    selected = {}
    for bench, draw in decomposed.items():
        lookup = {row['task_id']: row for row in training[bench]}
        selected[bench] = [lookup[key] for key in draw['items']]
    return selected, harms, registered


def _endpoint(setting, chain, bench):
    return budgets.endpoint(setting, ('overall', chain + ':solver'), client=setting.clients(p.CHAINS[chain], bench),
        max_tokens_bound=p.ledger_bound(p.CHAINS[chain], bench, branch=setting.branch, longest=setting.longest))


def _workers(local, attempt, endpoint, name, bench, items):
    """The real sandbox worker and native-input mounting used by practice cells."""
    from . import step
    context = units.cell_context(local, attempt, endpoint)
    publics = {row['task_id']: row['public'] for row in items}
    @contextmanager
    def factory(package, key):
        if not package.for_bench(bench):
            yield None
            return
        environment = context.environment(bench, name) if context.environment else nullcontext()
        with environment:
            with step._sheet_inputs(publics[key]) if bench == 'spreadsheetbench' else nullcontext() as inputs:
                worker = context.worker(bench).start(package, kind='cell', inputs_dir=inputs)
                try:
                    yield worker
                finally:
                    worker.close()
    return factory


def _aggregates(bench, cells):
    from . import outcomes_ext, stats_ext, v221_rule
    require(cells and all(isinstance(cell, dict) and v221_rule.token(cell) in outcomes_ext.TOKENS
                          for cell in cells),
            'Decomposition requires completed practice outcome records, never guessed outcomes')
    tokens = [v221_rule.token(cell) for cell in cells]
    key = COUNTERS[bench]
    formats = [(row.get('judge') or {}).get('format', {}) for row in cells]
    field = 'violation' if bench == 'alfworld' else 'grid' if bench == 'zebralogic' else key
    require(all(isinstance(row, dict) and row and (row.get(field) is None or type(row[field]) is bool)
                for row in formats), 'A decomposition format flag is boolean or not applicable')
    applicable = [row[field] for row in formats if row.get(field) is not None]
    scores = stats_ext.item_scores({('card', index): [token] for index, token in enumerate(tokens)},
                                   'card', list(range(len(tokens))), side='H')
    unknown = {token: tokens.count(token) for token in outcomes_ext.TOKENS
               if token.startswith('unknown') and token in tokens}
    return {'items': len(cells), 'passed': int(sum(scores.values())),
            'observed_passed': tokens.count('pass'), 'unknown': sum(unknown.values()),
            'unknown_by_token': unknown, 'scoring_side': 'H',
            'format': {key: sum(applicable)}, 'format_applicable': {key: len(applicable)},
            'format_not_applicable': {key: len(cells) - len(applicable)}}


def _practice_round(local, attempt, endpoint, name, arms, tasks, *, tag):
    """Resume scored cells under an immutable binding; never replay completed history."""
    from . import outcomes_ext, step, v221_rule
    binding = {'unit': name, 'manifest': local.run, 'tag': tag,
               'arms': {label: arm.package.sha256 for label, arm in arms.items()},
               'tasks_sha256': digest(tasks)}
    path = safe_path(attempt).parent / ('v222-' + hashlib.sha256(name.encode()).hexdigest() + '.json')
    if path.exists():
        require(read_json(path) == binding, 'A resumed practice round retains its original request inputs')
    else:
        write_json(path, binding)
    cached = {}
    for previous in sorted(safe_path(attempt).parent.glob('attempt-*/cells/*.json')):
        row = p.verified(read_json(previous), 'cell')
        cell = row['cell']
        if (cell['unit'] == name and cell['arm'] in arms and cell['task_id'] in tasks
                and cell['run'] == 0 and step._confirm_cell_reusable(row, cell['task_id'])
                and v221_rule.token(row) in outcomes_ext.TOKENS):
            cached[(cell['arm'], cell['task_id'])] = [row]
    jobs = {label: [(key, 1) for key in tasks if (label, key) not in cached] for label in arms}
    # Each native/solver route confirms one actual reply before concurrent practice.
    first = next(((label, key) for label, plan in jobs.items() for key, _ in plan), None)
    if first is not None:
        label, key = first
        found = rounds.run_round(replace(local, workers=1), attempt, endpoint, name,
            {label: arms[label]}, {label: [(key, 1)]}, tasks, tag=tag + '-first-response')
        cell = found[(label, key)][0]
        require(cell.get('final') is not None and cell.get('stop') is None,
                'A confirmed actual first reply precedes concurrent practice cells')
        cached.update(found)
        jobs[label] = [entry for entry in jobs[label] if entry[0] != key]
    if any(jobs.values()):
        cached.update(rounds.run_round(local, attempt, endpoint, name, arms, jobs, tasks, tag=tag))
    return cached


def measure_decomposition(bench, items, run_arms, *, initial, identity_pairs=None, registered_count=None):
    """One historical run and one split run on the registered actual count."""
    count = len(items) if registered_count is None else registered_count
    require(type(count) is int and gate.MIN_PRACTICE_ITEMS <= count <= (20 if bench == 'alfworld' else 100)
            and len(items) == count, 'Exact registered actual decomposition denominator')
    if identity_pairs is not None:
        identity = cards.decomposition_identity(bench, identity_pairs, registered_count=count)
        if identity['identity_proven']:
            return {**identity, 'passed': True, 'fallback': False, 'identity_pairs': identity_pairs,
                    'new_model_cells': 0, 'sealed_reads': 0}
    pairs = run_arms(('C_hist', 'C'), initial)
    require(set(pairs) == {'C_hist', 'C'}, 'Both decomposition arms are measured once')
    old, split = _aggregates(bench, pairs['C_hist']), _aggregates(bench, pairs['C'])
    decision = cards.decomposition_decision(bench, old, split, registered_count=count)
    fallback = decision['decision'] == 'whole_card_fallback'
    return {**decision, 'passed': True, 'fallback': fallback, 'new_model_cells': 2 * count,
            'cell_hashes': {arm: [row.get(p.RECORD_HASH) or digest(row) for row in values] for arm, values in pairs.items()},
            'sealed_reads': 0}


def decomposition(setting, chain):
    """Persist each benchmark once; resume never rereads a completed C_hist arm."""
    selected, _, registered = practice(setting)
    initial = cards.initial_package(evidence=setting.evidence, step=chain + '/s0')
    results = {}
    for bench, items in selected.items():
        name = chain + '/v222-smoke/decomposition/' + bench
        local = units.for_unit(setting, chain, bench, name)
        def work(attempt, bench=bench, items=items, local=local, name=name):
            endpoint = _endpoint(local, chain, bench)
            tasks = {rounds.key(bench, row['task_id']): {'public': row['public'], 'private': row['private']} for row in items}
            def run_arms(labels, package):
                arms = {label: Arm('card', empty(step=chain + '/s0', evidence=local.evidence))
                        if label == 'C_hist' else Arm('candidate', package) for label in labels}
                found = _practice_round(local, attempt, endpoint, name, arms, tasks, tag='historical-and-split')
                return {label: [cell for (arm, _), group in found.items() if arm == label for cell in group]
                        for label in labels}
            identity = None
            if bench == 'zebralogic':
                from . import reuse
                worker_factory = _workers(local, attempt, endpoint, name, bench, items)
                identity = {}
                for row in items:
                    view = solver.routing_view(bench, row['public'], runtime=local.runtime[bench])
                    with worker_factory(initial, row['task_id']) as worker:
                        identity[row['task_id']] = {
                            'C_hist': reuse.signature(bench, empty(step=chain + '/s0', evidence=local.evidence), view,
                                None, card_text=cards.historical_text(bench),
                                runtime=cards.historical_runtime(local.runtime[bench]), configuration=p.MAIN_V8),
                            'C': reuse.signature(bench, initial, view, worker, card_text=cards.format_text(bench),
                                runtime=local.runtime[bench], configuration=p.MAIN_V8)}
            result = measure_decomposition(bench, items, run_arms, initial=initial, identity_pairs=identity,
                registered_count=registered[SUPPLY_FLAG]['benches'][bench]['decomposition_items'])
            return {**result, 'cards_sha256': digest(cards.manifest_pins()),
                    'slice_sha256': digest(registered['decomposition'][bench])}
        results[bench] = units.run_unit(safe_path(setting.root) / name, run=setting.run,
            identity={'unit': name}, work=work, evidence=setting.evidence, configuration=p.MAIN_V8,
            drain=units.drainer(local, chain, name))['result']
    value = {'configuration': p.MAIN_V8, 'chain': chain, 'benches': results,
        'fallbacks': [b for b, row in results.items() if row['fallback']],
        'passed': all(row['passed'] for row in results.values()),
        'new_model_cells': sum(row['new_model_cells'] for row in results.values()),
        'cards_sha256': digest(cards.manifest_pins()), 'slices': registered['decomposition'],
        SUPPLY_FLAG: registered[SUPPLY_FLAG],
        'decomposition': {b: row['decision'] for b, row in results.items()}, 'sealed_reads': 0}
    check_decomposition(value)
    return value


def _check_supply(value):
    require(isinstance(value, dict) and value.get('source') == 'all_practice_except_own_acceptance'
            and value.get('minimum_available') == gate.MIN_PRACTICE_ITEMS
            and value.get('decomposition_harm_overlap_allowed') is True
            and set(value.get('benches', {})) == set(cards.BENCHES),
            'The actual practice supply registration covers every benchmark')
    for bench, row in value['benches'].items():
        require(isinstance(row, dict) and type(row.get('available')) is int
                and row['available'] >= gate.MIN_PRACTICE_ITEMS
                and row.get('decomposition_items') == min(20 if bench == 'alfworld' else 100, row['available'])
                and row.get('harm_items') == min(gate.HARM_ITEMS[bench], row['available'])
                and type(row.get('acceptance_excluded')) is int and row['acceptance_excluded'] >= 0,
                'Actual practice counts respect the available floor and registered maxima')
    return value


def check_decomposition(value):
    require(value.get('configuration') == p.MAIN_V8 and set(value.get('benches', {})) == set(cards.BENCHES)
            and value.get('cards_sha256') == digest(cards.manifest_pins()) and value.get('sealed_reads') == 0,
            'Decomposition readiness binds all five pinned cards')
    supplied = _check_supply(value.get(SUPPLY_FLAG))
    for bench, row in value['benches'].items():
        count = supplied['benches'][bench]['decomposition_items']
        draw = value['slices'][bench]
        require(row.get('items') == draw.get('count') == len(draw.get('items', ())) == count
                and len(set(draw['items'])) == count, 'The actual decomposition denominator is pinned')
        require(row.get('cards_sha256') == value['cards_sha256']
                and row.get('slice_sha256') == digest(value['slices'][bench]),
                'Every one-time decomposition result binds its immutable card and practice draw')
        if row.get('identity_proven') is True:
            require(cards.decomposition_identity(bench, row['identity_pairs'], registered_count=count)['identity_proven']
                    and set(row['identity_pairs']) == set(value['slices'][bench]['items'])
                    and row.get('new_model_cells') == 0 and row.get('passed') is True,
                    'Zero-call decomposition requires every exact request identity')
        else:
            expected = cards.decomposition_decision(bench, row['historical'], row['segmented'], registered_count=count)
            require(all(row.get(key) == expected[key] for key in expected), 'Measured decomposition counts recompute')
            fallback = expected['decision'] == 'whole_card_fallback'
            require(row['passed'] is True and row['fallback'] is fallback,
                    'Fallback flags follow the measured checks')
            require(set(row['cell_hashes']) == {'C_hist', 'C'}
                    and all(len(hashes) == row['items'] for hashes in row['cell_hashes'].values())
                    and row['new_model_cells'] == row['items'] * 2,
                    'Decomposition cell counts and receipt hashes are complete')
    require(value['passed'] is all(row['passed'] for row in value['benches'].values())
            and value['fallbacks'] == [b for b, row in value['benches'].items() if row['fallback']]
            and value['new_model_cells'] == sum(row['new_model_cells'] for row in value['benches'].values())
            and value.get('decomposition') == {b: row['decision'] for b, row in value['benches'].items()},
            'The decomposition summary preserves every benchmark decision')
    return value


def probe_segment(case, *, evidence, step=1):
    """Two fixed SearchQA notes with the same public-structure firing predicate."""
    require(case in PROBE_CASES, 'A registered cross-smoke probe case')
    return cards.make_segment('searchqa', PROBE_TEXTS[case], {'kind': 'public_evidence'},
                              evidence=evidence, step=step)


def _cross_probe_case(setting, chain, case, *, parent, slices, registered, fallback):
    """Persist one measured candidate without sharing its cells with the other."""
    configuration = p.configuration_of(setting) if p.is_v225(p.configuration_of(setting)) else p.MAIN_V8
    name = chain + ('/v225-smoke/' if p.is_v225(configuration) else '/v222-smoke/') + 'cross-narrowing/' + case
    segment = probe_segment(case, evidence=setting.evidence)
    candidate = with_(parent, step=chain + '/s1-searchqa', add=[segment])
    def work(attempt):
        def inspect(bench, before, after, items):
            local = units.for_unit(setting, chain, bench, name)
            endpoint = _endpoint(local, chain, bench)
            return gate.inspect(bench, before, after, items, _workers(local, attempt, endpoint, name, bench, items),
                card_text=cards.historical_text(bench) if bench in fallback else cards.format_text(bench),
                runtime=local.runtime[bench], configuration=configuration)
        def pairs(bench, before, after, items):
            local = units.for_unit(setting, chain, bench, name)
            tasks = {rounds.key(bench, row['task_id']): {'public': row['public'], 'private': row['private']} for row in items}
            found = _practice_round(local, attempt, _endpoint(local, chain, bench), name + '/' + bench,
                {'S': Arm('parent', before), "S'": Arm('candidate', after)},
                tasks, tag='cross-narrowing-' + bench)
            return {(arm, key.split('/', 1)[1]): rows for (arm, key), rows in found.items()}
        selected, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
            slices=slices, inspector=inspect, run_pairs=pairs, phase='confirmation', configuration=configuration,
            registered_counts={b: registered['harm']['benches'][b]['items'] for b in gate.BENCHES})
        passed = selected is not None and record['passed'] and record['paired_item_calls'] > 0
        narrowed = passed and selected.sha256 != candidate.sha256
        reason = (None if narrowed else 'no_measured_harm' if passed else
                  'no_fired_pairs' if record['passed'] else 'gate_rejected')
        return {'passed': bool(passed), 'gate': record,
                'probe_source_sha256': hashlib.sha256(segment.source.encode()).hexdigest(),
                'narrowing_exercised': bool(narrowed),
                'reason': reason, 'sealed_reads': 0}
    return units.run_unit(safe_path(setting.root) / name, run=setting.run, identity={'unit': name},
        work=work, evidence=setting.evidence, configuration=configuration,
        drain=units.drainer(setting, chain, name))['result']


def cross_probe(setting, chain, *, fallback=()):
    """Measure an invalid-format challenge and the original note independently.

The challenge requests a response the official OfficeQA scorer rejects. A
solver may ignore either note or already fail the paired parent cell, so actual
harm is never assumed: a correct unchanged accept records no measured harm.
    """
    _, slices, registered = practice(setting)
    parent = cards.initial_package(evidence=setting.evidence, step=chain + '/s0', fallback=fallback)
    if p.is_v225(p.configuration_of(setting)):
        parent = empty(step=chain + '/s0', evidence=setting.evidence)
    cases = {case: _cross_probe_case(setting, chain, case, parent=parent, slices=slices,
                                    registered=registered, fallback=fallback) for case in PROBE_CASES}
    narrowed = any(row['narrowing_exercised'] for row in cases.values())
    passed = all(row['passed'] for row in cases.values())
    return {'passed': passed, 'cases': cases, 'narrowing_exercised': narrowed,
            'reason': (None if narrowed else 'no_measured_harm') if passed else 'probe_case_failed',
            'paired_item_calls': sum(row['gate']['paired_item_calls'] for row in cases.values()),
            'call_bound': len(PROBE_CASES) * gate.MAX_PAIRED_ITEM_CALLS,
            'harm_registration_sha256': registered['harm']['sha256'], 'sealed_reads': 0}


def s2(setting, chain):
    """The new paid checks precede the inherited 76-cell format-price sample."""
    from . import v214_stages, v214_smoke
    decomposed = decomposition(setting, chain)
    require(decomposed['passed'], 'Card decomposition failed; retain receipts and block smoke')
    setting.extra.setdefault('v222_fallbacks', {})[chain] = list(decomposed['fallbacks'])
    probe = cross_probe(setting, chain, fallback=decomposed['fallbacks'])
    require(probe['passed'], 'Measured cross-firing probe cases did not pass the gate')
    pools, results = v214_stages.fixture_pools(setting, chain), {}
    for bench, items in pools.items():
        name = chain + '/v222-smoke/C0/' + bench
        local = units.for_unit(setting, chain, bench, name)
        def work(attempt, bench=bench, items=items, name=name, local=local):
            tasks = {rounds.key(bench, row['task_id']): {'public': row['public'], 'private': row['private']} for row in items}
            found = _practice_round(local, attempt, _endpoint(local, chain, bench), name,
                {'C0': Arm('card', empty(step=chain + '/s0', evidence=local.evidence))},
                tasks, tag='format-price')
            cells = [row for group in found.values() for row in group]
            from . import outcomes_ext, v221_rule
            valid = all(v221_rule.token(row) in outcomes_ext.TOKENS for row in cells)
            parsed = sum(row.get('judge', {}).get('format', {}).get('grid') is True for row in cells) if bench == 'zebralogic' else None
            return {'passed': valid and len(cells) == v214_smoke.S2_ITEMS[bench] and (parsed is None or parsed >= 9),
                'items': len(tasks), 'cells': len(cells), 'arms': ['C0'], 'measurements': smoke.measured_cells(cells),
                'unknown': sum(v221_rule.token(row).startswith('unknown') for row in cells) if valid else None,
                'settled_tokens': sum(send.get('charged', 0) for row in cells for send in row['sends']),
                'parsed': parsed, 'first_response_confirmed': True, 'sealed_reads': 0}
        results[bench] = units.run_unit(safe_path(setting.root) / name, run=setting.run, identity={'unit': name},
            work=work, evidence=setting.evidence, configuration=p.MAIN_V8,
            drain=units.drainer(local, chain, name))['result']
    return {'passed': all(row['passed'] for row in results.values()), 'chain': chain, 'benches': results,
            'cells': sum(row['cells'] for row in results.values()), 'decomposition': decomposed,
            'cross_narrowing': probe, 'sealed_reads': 0}


def structural_smoke(root):
    """Production router over source-pinned authored predicates; zero model calls."""
    from . import router, v221_smoke
    inherited = v221_smoke.structural_smoke(safe_path(root) / 'inherited')
    initial = cards.initial_package(evidence='engineering_fixture')
    views = {'searchqa': {'question': 'Who described this tree?', 'context': 'A public evidence snippet.'},
        'officeqa': {'question': 'What was the total amount in dollars?', 'context': 'Quantity table: 40 dollars.'},
        'zebralogic': {'puzzle': 'A finite ordered-house puzzle.', 'num_houses': 3, 'categories': {}},
        'spreadsheetbench': {'instruction': 'Copy a value.', 'workbook_preview': {'Sheet1': [['x']]}},
        'alfworld': {'initial_observation': 'A room.', 'admissible_commands_at_reset': ['look'], 'task_text': 'move an object'}}
    class PinnedWorker:
        def __init__(self):
            self.functions = {}
            for proc in initial.procedures:
                require(cards.pinned_seed_source(proc.source), 'Only immutable authored seed predicates execute locally')
                namespace = {}
                exec(proc.source, namespace)
                self.functions[proc.id] = namespace
        def call(self, pid, fn, args, *, timeout_s):
            require(fn == 'applies', 'The structural demo invokes only the pinned predicates')
            value = self.functions[pid][fn](*args)
            return {'ok': True, 'value': value, 'value_sha256': digest(value)}
    worker = PinnedWorker()
    rows = {bench: router.route(initial, bench, view, worker) for bench, view in views.items()}
    expected = {bench: [proc.id for proc in cards.own_segments(initial, bench)] for bench in cards.BENCHES}
    segment = {'passed': all(list(row.enabled) == expected[bench] and not row.faults for bench, row in rows.items()),
               'enabled': {bench: list(row.enabled) for bench, row in rows.items()}, 'expected': expected,
               'source_sha256': digest(cards.manifest_pins()), 'model_calls': 0, 'sealed_reads': 0}
    return {'configuration': p.MAIN_V8, 'passed': inherited['passed'] and segment['passed'],
            'inherited': inherited, 'segments': segment, 'model_calls': 0, 'sealed_reads': 0}


def check_structural(value):
    from . import v221_smoke
    require(value.get('configuration') == p.MAIN_V8 and value.get('passed') is True
            and value.get('model_calls') == 0 and value.get('sealed_reads') == 0,
            'main-v8 structural smoke is a zero-model mechanism check')
    v221_smoke.check_result(value['inherited'])
    row = value.get('segments', {})
    initial = cards.initial_package(evidence='engineering_fixture')
    expected = {bench: [proc.id for proc in cards.own_segments(initial, bench)] for bench in cards.BENCHES}
    require(row.get('passed') is True and row.get('enabled') == row.get('expected') == expected
            and row.get('source_sha256') == digest(cards.manifest_pins()), 'Every own seed fires only at its authored home')
    return value


def _check_probe_case(probe, supply, *, configuration=p.MAIN_V8):
    from .outcomes_ext import TOKENS
    require(isinstance(probe, dict), 'Each cross-smoke case is a measured record')
    record = p.verified(probe.get('gate', {}), 'v222-cross-gate')
    require(probe.get('passed') is True and probe.get('sealed_reads') == 0
            and record.get('passed') is True and 0 < record.get('paired_item_calls', 0) <= gate.MAX_PAIRED_ITEM_CALLS
            and record.get('decision') == 'accept' and record.get('call_bound') == gate.MAX_PAIRED_ITEM_CALLS
            and all(isinstance(record.get(key), str) and len(record[key]) == 64
                    for key in ('parent_sha256', 'proposed_sha256', 'candidate_sha256'))
            and record.get('home') == 'searchqa'
            and record.get('configuration') == configuration and record.get('phase') == 'confirmation',
            'Readiness requires a measured cross-firing case accepted by the unchanged gate')
    rows, narrowing = record['benches'], record['narrowing']
    require(set(rows) == set(gate.BENCHES) - {'searchqa'}, 'Cross smoke checks every off-home slice')
    harmful = []
    for bench, row in rows.items():
        require(row.get('items') == supply['benches'][bench]['harm_items']
                and 'fixed' in row and 'broken' in row,
                'Cross smoke requires outcomes, not a routing fault masquerading as harm')
        expected = gate.counts(fired=row['fired'], fixed=row['fixed'], broken=row['broken'], items=row['items'])
        require(all(row.get(key) == value for key, value in expected.items())
                and row.get('paired_item_calls') == row['fired'] * 2,
                'Cross-smoke counts and charged fired pairs recompute')
        if row['fired']:
            unknown, by_token = row.get('unknown'), row.get('unknown_by_token')
            require(row.get('scoring_sides') == {'S': 'L', "S'": 'L'}
                    and isinstance(unknown, dict) and set(unknown) == {'S', "S'"}
                    and isinstance(by_token, dict) and set(by_token) == set(unknown),
                    'Measured cross unknowns retain both method arms on L')
            for arm, count in unknown.items():
                require(type(count) is int and 0 <= count <= row['fired']
                        and isinstance(by_token[arm], dict)
                        and set(by_token[arm]) <= {token for token in TOKENS if token.startswith('unknown')}
                        and all(type(n) is int and n > 0 for n in by_token[arm].values())
                        and sum(by_token[arm].values()) == count,
                        'Cross-smoke unknown counts match their registered tokens')
            require(unknown['S'] <= row['fired'] - row['broken']
                    and unknown["S'"] <= row['fired'] - row['fixed'],
                    'Unknown method outcomes cannot be counted as passes')
        if not expected['passed']:
            harmful.append(bench)
    require(sum(row['paired_item_calls'] for row in rows.values()) == record['paired_item_calls'],
            'Every charged cross-smoke pair is included in the case total')
    if harmful:
        require(isinstance(narrowing, dict) and narrowing.get('benches') == harmful
                and narrowing.get('candidate_sha256') == record['candidate_sha256']
                and record['candidate_sha256'] != record['proposed_sha256']
                and narrowing.get('additional_model_calls') == 0 and narrowing.get('passed') is True
                and set(narrowing.get('rechecked', {})) == set(rows)
                and all(row.get('passed') is True for row in narrowing['rechecked'].values())
                and probe.get('narrowing_exercised') is True and probe.get('reason') is None,
                'Measured harmful cross firing is narrowed and every other bench is rechecked')
    else:
        require(narrowing is None and record['candidate_sha256'] == record['proposed_sha256']
                and probe.get('narrowing_exercised') is False and probe.get('reason') == 'no_measured_harm',
                'A correct no-harm gate accept records that narrowing was not exercised')
    return probe


def check_measured(s2):
    require(s2.get('passed') is True, 'A passing main-v8 S2')
    decomposition_result = check_decomposition(s2['decomposition'])
    require(decomposition_result['passed'], 'The measured decomposition passed')
    probe = s2.get('cross_narrowing', {})
    require(isinstance(probe, dict), 'The cross-smoke summary is a measured record')
    cases = probe.get('cases', {})
    require(probe.get('passed') is True and probe.get('sealed_reads') == 0
            and isinstance(cases, dict) and set(cases) == set(PROBE_CASES),
            'Both fixed cross-smoke candidates must be recorded')
    for case in PROBE_CASES:
        _check_probe_case(cases[case], decomposition_result[SUPPLY_FLAG])
    require(len({row['gate']['parent_sha256'] for row in cases.values()}) == 1
            and len({row['gate']['proposed_sha256'] for row in cases.values()}) == len(PROBE_CASES),
            'Cross-smoke cases independently measure distinct candidates against the same parent')
    narrowed = any(row['narrowing_exercised'] for row in cases.values())
    require(probe.get('narrowing_exercised') is narrowed
            and probe.get('reason') == (None if narrowed else 'no_measured_harm')
            and probe.get('paired_item_calls') == sum(row['gate']['paired_item_calls'] for row in cases.values())
            and probe.get('call_bound') == len(PROBE_CASES) * gate.MAX_PAIRED_ITEM_CALLS,
            'The cross-smoke summary preserves both measured decisions and the aggregate bound')
    return s2


def check_bound_practice(s2, registered):
    """Bind measured slices and the authored cross probe back to the S0 pins."""
    check_measured(s2)
    chain = s2.get('chain')
    require(chain in p.CHAINS, 'The measured practice record names its registered chain')
    expected_sources = {case: hashlib.sha256(probe_segment(case, evidence='engineering_fixture').source.encode()).hexdigest()
                        for case in PROBE_CASES}
    require(s2['decomposition']['slices'] == registered['decomposition']
            and s2['decomposition'][SUPPLY_FLAG] == registered[SUPPLY_FLAG]
            and s2['cross_narrowing']['harm_registration_sha256'] == registered['harm']['sha256']
            and all(s2['cross_narrowing']['cases'][case].get('probe_source_sha256') == expected_sources[case]
                    for case in PROBE_CASES),
            'Measured decomposition and cross-harm smoke bind the fixed S0 practice registration')
    for case in PROBE_CASES:
        record = s2['cross_narrowing']['cases'][case]['gate']
        parent = cards.initial_package(evidence=record['evidence'], step=chain + '/s0',
                                       fallback=s2['decomposition']['fallbacks'])
        candidate = with_(parent, step=chain + '/s1-searchqa',
                          add=[probe_segment(case, evidence=record['evidence'])])
        require(record['parent_sha256'] == parent.sha256 and record['proposed_sha256'] == candidate.sha256,
                'Every cross-smoke gate binds its exact authored candidate and decomposition parent')
    return s2
