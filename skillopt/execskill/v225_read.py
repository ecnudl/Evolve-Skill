"""main-v9: fresh, sealed read events, isolated from the overlapping learner.

The chain process handles package hashes and completion receipts only. Test data
and cells are opened exclusively by evaluate-unit children; aggregates are made
only after the inherited two-chain unseal gate has passed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import copy
from fractions import Fraction
from pathlib import Path
import functools
import math
from functools import lru_cache

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest
from . import profiles as p
from .cells import Arm, Pause
from .package import empty, load, save

VERSION = 'main-v9-fresh-stage-reads-v1'
ARMS = ('B', 'C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5', 'I', 'C_end')
EVENTS = ('anchor', 's1', 's2', 's3', 's4', 's5', 'i', 'c_end')
STAGE_ROWS = ['C', 'S1', 'S2', 'S3', 'S4', 'S5']
SPEC_FIELDS = frozenset({'chain', 'bench', 'label', 'package_sha256', 'unit_root'})
LEARNING_UNIT_NAMES = frozenset({'selftest', 'selftest-1', 'selftest-2', 'audit-final', 'sandbox-selftest'})
PROTECTED = ('test', 'holdout', 'held_out', 'final', 'sealed', 'reserve', 'testaccess', 'test_panel', 'block_c', 'block_d')


def assert_learning_path(path):
    """Fail before a learner opens a protected component (including test children)."""
    require(not any(token in part.lower() for part in Path(path).parts if part not in LEARNING_UNIT_NAMES for token in PROTECTED),
            'main-v9 learner cannot open protected data or read-unit directories')
    return Path(path)


def labels(event):
    require(event in EVENTS, 'A registered main-v9 read event')
    return ('B', 'C0', 'C') if event == 'anchor' else (event.upper() if event != 'c_end' else 'C_end',)


def unit_root(setting, chain, label, bench):
    require(chain in p.CHAINS and bench in p.MAIN_V5_ORDER and label in EVENTS,
            'A registered main-v9 read unit')
    return safe_path(setting.root) / chain / 'test' / label / bench


def status_path(setting, chain, label, bench):
    # A status receipt outside test lets orchestration avoid opening sealed units.
    return safe_path(setting.root) / chain / 'read-status' / (label + '-' + bench + '.json')


def status(setting, chain, label, bench):
    path = status_path(setting, chain, label, bench)
    if not path.exists():
        pauses = sorted(path.parent.glob(path.stem + '-paused-*.json'),
                        key=lambda value: int(value.stem.rsplit('-', 1)[1]))
        if not pauses:
            return None
        path = pauses[-1]
    value = p.verified(read_json(path), 'read-status')
    require(value['run'] == setting.run and value['chain'] == chain
            and value['label'] == label and value['bench'] == bench,
            'The read status belongs to its run, chain, event and bench')
    return value


def plan_events():
    return [{'label': label, 'bench': bench, 'arms': list(labels(label))}
            for label in EVENTS for bench in p.MAIN_V5_ORDER]


def cards_only(package):
    from .v225_cards import is_card
    from dataclasses import replace
    cards = tuple(proc for proc in package.procedures if is_card(proc))
    ids = {proc.id for proc in cards}
    return replace(package, procedures=cards, narrowed={i: v for i, v in package.narrowed.items() if i in ids},
                   describer={i: v for i, v in package.describer.items() if i in ids})


def arms(package, event, *, chain, evidence):
    blank = empty(step=chain + '/s0', evidence=evidence)
    if event == 'anchor':
        return {'B': Arm('blank', blank), 'C0': Arm('card', blank), 'C': Arm('card', blank)}
    if event == 'c_end':
        return {'C_end': Arm('card', blank)}
    return {labels(event)[0]: Arm('candidate', cards_only(package) if event == 'i' else package)}


def context_for(context, bench, label):
    """The original historical C request, including Zebra's absent card, is pinned."""
    from . import v222_cards
    own = copy(context)
    own.cards = dict(context.cards)
    own.runtime = dict(context.runtime)
    if label in ('C', 'C_end'):
        own.cards[bench] = v222_cards.historical_text(bench)
        own.runtime[bench] = (v222_cards.historical_runtime(context.runtime[bench])
                              if bench == 'zebralogic' else context.runtime[bench])
    else:
        own.cards[bench] = '' if label == 'B' else v222_cards.format_text(bench)
    return own


def fresh_plan(base, chosen, packages, *, bench, context, workers):
    """Request identities are retained for analysis, never used to share a cell."""
    from . import evaluation, notes, reuse, solver, v218_read
    from contextlib import nullcontext
    require(not packages, 'main-v9 reads each frozen stage in a separate unit')
    tasks = {task['task_id']: task for task in base['tasks']}
    workers = evaluation.mounting(workers, evaluation.public_inputs(bench, tasks))
    identities, routes, metadata = ({label: {} for label in chosen} for _ in range(3))
    for item, task in sorted(tasks.items()):
        for label, arm in chosen.items():
            own = context_for(context, bench, label)
            view = solver.routing_view(bench, task['public'], runtime=own.runtime[bench])
            captured = []
            def observe(shell, text):
                captured.append(shell.route)
            factory = workers(arm.package, item) if arm.package.for_bench(bench) else nullcontext(None)
            with factory as worker:
                identities[label][item] = reuse.signature(bench, arm.package, view, worker,
                    card_text=own.cards.get(bench, ''), runtime=own.runtime[bench],
                    configuration=context.configuration, note_observer=observe)
            routes[label][item] = captured[0]
            metadata[label][item] = {}
    sources = {label: {item: None for item in tasks} for label in chosen}
    summary = {'version': VERSION, 'sources': sources, 'planning_metadata': metadata,
        'identities': {label: {item: v218_read.public_identity(identity) for item, identity in rows.items()}
                       for label, rows in identities.items()}}
    return {**summary, 'identities': identities, 'routes': routes, 'arms': chosen, 'sha256': digest(summary),
            'staged': {'routes': {}, 'sources': {}, 'derived': {}, 'sha256': digest(summary)}}


def read_terms(setting, chain):
    """Per-unit SE6 terms, including the C_end drift arm; never a reuse discount."""
    raw = (setting.extra.get('test_read_terms') or {}).get(chain, {})
    expected = {row['label'] + '/' + row['bench'] for row in plan_events()}
    if set(raw) == expected:
        return {key: Fraction(value) for key, value in raw.items()}
    require(False, 'main-v9 requires per-unit SE6 terms for all 40 registered units')


def estimate_unit_terms(measurements, ratio):
    ratio = Fraction(str(ratio))
    terms = {}
    for row in plan_events():
        event, bench = row['label'], row['bench']
        measured = measurements[bench]
        card = Fraction(measured['card'])
        procedure = (Fraction(8, 5) * card if measured.get('procedure_assumed')
                     else Fraction(measured['procedure']))
        unit = 3 * card if event == 'anchor' else card if event == 'c_end' else procedure
        terms[event + '/' + bench] = ratio * p.MAIN_V5_TEST_ITEMS[bench] * unit
    return terms


def read_budget(setting, chain):
    from . import chain as c
    pending = [row for row in plan_events() if not (status(setting, chain, row['label'], row['bench']) or {}).get('status') == 'complete']
    terms = read_terms(setting, chain)
    part = math.ceil(sum((terms[row['label'] + '/' + row['bench']] for row in pending), Fraction(0)))
    factor, check = Fraction(1), None
    # The anchor necessarily precedes the first learning cost check. SE6 is its
    # measured basis; all later events also use the current chain-G correction.
    if chain == 'G' and (safe_path(setting.root) / 'G' / c.CAP_CHECK).exists():
        path, found = c.latest_cap_check(setting)
        factor = max(Fraction(1), Fraction(found['per_cell']) / found['anchor_high'])
        check = {'file': path.name, 'record_sha256': found[p.RECORD_HASH]}
    used = math.ceil(part * factor)
    need = math.ceil(used * p.TEST_START_FACTOR)
    snapshot = setting.budget.snapshot()
    for scope in (chain + ':solver', chain + ':test'):
        row = snapshot[scope]
        if row['cap'] - row['settled'] - row['open'] < need:
            raise Pause('test_read_budget', 'main-v9 remaining read-unit estimate exceeds scope', chain + '/test')
    return {'estimate': setting.extra['test_read_estimate'][chain], 'units': [r['label']+'/'+r['bench'] for r in pending],
            'part': part, 'factor': float(factor), 'cap_check': check, 'used': used, 'need': need}


def evaluate_event(setting, chain, package, *, label, launch):
    from . import chain as c
    require(label in EVENTS, 'A registered read event')
    save(c.chain_root(setting, chain), package)
    def one(bench):
        previous = status(setting, chain, label, bench)
        if previous and previous['status'] == 'complete':
            require(previous['package_sha256'] == package.sha256, 'Frozen event package changed')
            return
        root = unit_root(setting, chain, label, bench)
        spec = {'chain': chain, 'bench': bench, 'label': label,
                'package_sha256': package.sha256, 'unit_root': str(root)}
        name = chain + '/test/' + label + '/' + bench
        code = launch(setting, spec)
        receipt = status(setting, chain, label, bench)
        if receipt and receipt['status'] == 'complete':
            require(receipt['package_sha256'] == package.sha256, 'Frozen event package changed')
            return
        if receipt and receipt['status'] == 'paused':
            raise Pause(receipt['kind'], receipt['reason'], name)
        raise Pause('exception', 'read_child_missing_status_receipt', name)

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(one, p.MAIN_V5_ORDER))
    return {bench: unit_root(setting, chain, label, bench) for bench in p.MAIN_V5_ORDER}


def run(setting, chain, *, learn, launch):
    """Anchor first, then stage read k overlaps learning k+1; all reads survive a learning pause."""
    from . import budgets, chain as c, evaluation, v222_runtime, v221_recovery
    from skillopt.coevo5.cells import exclusive
    configuration = p.MAIN_V9
    if p.is_v226(p.configuration_of(setting)):
        configuration = p.configuration_of(setting)
    root = c.chain_root(setting, chain)
    root.mkdir(parents=True, exist_ok=True)
    identity = {'run': setting.run, 'chain': chain}
    with exclusive(root / c.RUNNER_LOCK):
        ended = c._terminal(root, identity)
        if ended is not None:
            return {'status': ended}
        verify = setting.extra.get('verify', lambda: None)
        verify()
        if not (root / 'chain.json').exists():
            write_json(root / 'chain.json', p.record('chain', setting.evidence, {
                'identity': identity, 'solver': p.CHAINS[chain], 'order': list(p.MAIN_V5_ORDER), 'configuration': configuration}))
        budgets.own_ledger(setting, chain).declare({**budgets.chain_caps(chain, configuration), **budgets.first_call_caps(chain)})
        start = empty(step=chain + '/s0', evidence=setting.evidence)
        save(root, start)
        package, steps, pending, gates = start, [], [], []
        outcome = None
        pool = ThreadPoolExecutor(max_workers=len(EVENTS))
        try:
            v222_runtime.preflight(setting)
            c.read_consent(setting, chain)
            c.first_call(setting, chain, before=lambda: c._verified(setting, root, identity, verify))
            gates.append(read_budget(setting, chain))
            # Qualification opens a panel only in a child (run_unit_spec), before
            # its first anchor arm; the existing shared qualification lock serializes it.
            evaluate_event(setting, chain, start, label='anchor', launch=launch)
            for k, bench in enumerate(p.MAIN_V5_ORDER, 1):
                for job in pending:
                    if job.done():
                        job.result()
                c._verified(setting, root, identity, verify)
                package, receipt = learn(setting, root, chain, k, bench, package)
                steps.append(receipt[p.RECORD_HASH])
                gates.append(read_budget(setting, chain))
                # Always submit, including byte-identical packages after rejection.
                pending.append(pool.submit(evaluate_event, setting, chain, package, label='s'+str(k), launch=launch))
            for job in pending:
                job.result()
            for event in ('i', 'c_end'):
                gates.append(read_budget(setting, chain))
                evaluate_event(setting, chain, package, label=event, launch=launch)
            write_json(root / c.TEST_READ, p.record('test-read', setting.evidence, {
                'identity': identity, 'status': 'read', 'configuration': configuration,
                'arms': list(ARMS), 'events': list(EVENTS), 'package_sha256': package.sha256,
                'gates': gates, 'request_reuse': False, 'stage_timing': 'overlap_next_learning_step'}))
        except Pause as pause:
            outcome = {'status': 'paused', 'kind': pause.kind, 'reason': pause.reason, 'unit': pause.cell}
        except c.Terminated as error:
            outcome = {'status': 'terminated', 'reason': str(error)}
        finally:
            # Do not cancel launched reads when learning pauses. Await their
            # sealed completion before this process exits, without opening results.
            pool.shutdown(wait=True, cancel_futures=False)
            if c.complete_deferred_termination(setting, root, identity):
                outcome = {'status': 'terminated', 'reason': 'manifest_mismatch'}
        if outcome is not None:
            return outcome
        write_json(root / 'chain-complete.json', p.record('chain-complete', setting.evidence, {
            'identity': identity, 'package_sha256': package.sha256, 'steps': steps,
            'automatic_retries': [entry for k, bench in enumerate(p.MAIN_V5_ORDER, 1)
                for entry in v221_recovery.records(root / ('s%d-%s' % (k, bench)))]}))
        return {'status': 'complete'}


def evaluate_unit(root, *, event, run, shared, pinned, chain, bench, chosen, context,
                  workers, canaries, panel, reset=None, drain=None):
    """A single sealed unit. Every arm/item/run goes through run_cells afresh."""
    from . import evaluation as e, v221_recovery
    from .cells import cell_id, run_cells
    from skillopt.coevo5.cells import exclusive
    configuration = p.MAIN_V9
    if p.is_v226(getattr(context, 'configuration', None)):
        configuration = context.configuration
    unit = chain + '/test/' + event + '/' + bench
    require(tuple(chosen) == labels(event), 'Exact event arm labels and order')
    e.consent(shared, configuration)
    root = safe_path(root)
    root.mkdir(parents=True, exist_ok=True)
    with exclusive(root / '.lock'):
        require(not (root / 'unit.json').exists(), 'This read unit already completed')
        require(context.attempt == v221_recovery.next_attempt(root), 'Next authorized read attempt')
        cleaned = e._leftovers(root, context.evidence)
        before = e._scanned(root, shared, canaries, configuration=configuration)
        require(not before['hits'], 'No canary hit before a main-v9 read')
        attempt = context.attempt
        attempt.mkdir()
        write_json(attempt / 'started.json', p.record('unit-started', context.evidence, {
            'run': run, 'identity': {'unit': unit, 'chain': chain}}))
        store = e.EvaluationStore(attempt, evidence=context.evidence)
        with e.contained(shared):
            try:
                tasks = e.test_tasks(shared, pinned, bench, unit, run=run,
                    runtime=context.runtime[bench], native=context.native, workers=workers,
                    evidence=context.evidence, panel=panel, configuration=configuration)
                if bench == 'alfworld':
                    if reset is None:
                        reset = e.alfworld_reset(context.runtime[bench], context.episodes)
                    if p.is_v225(context.configuration) and context.environment is not None:
                        preparation_reset = reset

                        def reset(public):
                            # Match cells: environment first, then the reset's
                            # episode slot; release both after each session closes.
                            with context.environment('alfworld', unit):
                                return preparation_reset(public)
                tasks = e._with_views(tasks, bench, reset)
                by_id = {task['task_id']: {'public': task['public'], 'private': task['private']} for task in tasks}
                block_unit = chain + '/test/' + bench if p.is_v226(context.configuration) else unit
                blocks = e._blocks(sorted(by_id), bench, block_unit)
                rooms = ({item: e.task_folder(task['public']['game_file'])[0] for item, task in by_id.items()}
                         if bench == 'alfworld' else {})
                expected_count = len(chosen) * len(by_id) * e.TEST_RUNS
                for label, arm in chosen.items():
                    own = context_for(context, bench, label)
                    jobs = []
                    for item in sorted(by_id):
                        for index in range(e.TEST_RUNS):
                            cell = {'id': cell_id(unit, label, item, index), 'unit': unit, 'arm': label,
                                'benchmark': bench, 'task_id': item, 'run': index, 'block': blocks[item],
                                **({'room': rooms[item]} if rooms else {})}
                            jobs.append((cell, by_id[item], arm))
                    for block in sorted(set(blocks.values())):
                        members = [job for job in jobs if job[0]['block'] == block]
                        run_cells(own, members, workers=workers, store=store)
                deleted = e._closed(store, context.evidence)
                e._drained(drain, context, unit, configuration=configuration)
            except BaseException as error:
                if not (attempt / 'transient-deleted.json').exists():
                    e._closed(store, context.evidence)
                recovery = v221_recovery.exception_pause(error)
                kind = (recovery or {}).get('kind', error.kind if isinstance(error, Pause) else
                    'configuration' if isinstance(error, ValueError) else 'exception')
                reason = (recovery or {}).get('reason', error.reason if isinstance(error, Pause) else type(error).__name__)
                e._paused(attempt, context.evidence, kind, reason,
                          auto_retry_eligible=recovery is not None)
                # The inherited drain is mandatory even on an incomplete attempt.
                e._drained(drain, context, unit, configuration=configuration)
                raise Pause(kind, reason, unit) from None
        sealed = [p.verified(read_json(path), 'evaluation-cell') for path in sorted((attempt / 'cells').glob('*.json'))]
        require(len(sealed) == expected_count and all(cell['shared_with'] is None for cell in sealed),
                'Every main-v9 arm/item/run is a fresh independently dispatched cell')
        after = e._scanned(root, shared, canaries, configuration=configuration)
        counts = e._counts(sealed)
        if after['hits'] or counts['infrastructure'] > e.INFRA_UNKNOWN_MAX * counts['cells']:
            kind = 'canary_hit' if after['hits'] else 'infrastructure_incomplete'
            e._paused(attempt, context.evidence, kind, kind, scan=after)
            raise Pause(kind, kind, unit)
        scan = p.record('canary-scan', context.evidence, {'artifacts_scanned': after['artifacts_scanned'],
            'hits': 0, 'canaries': len(canaries), 'canaries_sha256': digest(canaries), 'cleaned_attempts': cleaned})
        write_json(attempt / 'canary_scan.json', scan)
        value = p.record('evaluation', context.evidence, {'run': run, 'unit': unit, 'chain': chain, 'bench': bench,
            'label': event, 'configuration': configuration, 'status': 'complete', 'attempt': attempt.name,
            'packages': {label: arm.package.sha256 for label, arm in chosen.items()},
            'cells': sorted(cell['cell']['id'] for cell in sealed), 'counts': counts,
            'request_reuse': {'shared_cells': 0, 'dispatched_cells': expected_count}, 'structural_zero': 0,
            'transient_deleted_sha256': deleted['manifest_sha256'], 'canary_scan_sha256': scan[p.RECORD_HASH]})
        write_json(root / 'unit.json', value)
        return value


def bind_event_package(setting, chain, event, package):
    """Each read independently verifies the immutable learning-step snapshot."""
    if event == 'anchor':
        require(package.sha256 == empty(step=chain + '/s0', evidence=setting.evidence).sha256,
                'Anchor reads the exact empty chain start')
        return
    k = int(event[1:]) if event.startswith('s') else 5
    bench = p.MAIN_V5_ORDER[k - 1]
    path = safe_path(setting.root) / chain / ('s%d-%s' % (k, bench)) / 'step.json'
    value = p.verified(read_json(path), 'step')
    require(value['chain'] == chain and value['k'] == k and value['bench'] == bench
            and value['package_sha256'] == package.sha256,
            'The stage read package matches its immutable completed step')


def _run_unit_attempt(manifest, *, spec, docker=None, transport=None, panel=None, reset=None):
    from . import evaluation as e, budgets, units, v221_recovery
    from . import chain as c
    if panel is None:
        panel = e.data.test_panel
    found = read_json(spec)
    require(isinstance(found, dict) and set(found) == SPEC_FIELDS, 'Exact main-v9 read-unit spec')
    chain, bench, event = found['chain'], found['bench'], found['label']
    setting = e.setting_of(manifest, chain, docker=docker, transport=transport)
    require(p.is_v225(p.configuration_of(setting)), 'main-v9 read-child configuration')
    configuration = p.MAIN_V9
    if p.is_v226(p.configuration_of(setting)):
        configuration = p.configuration_of(setting)
    root = unit_root(setting, chain, event, bench)
    require(root == safe_path(found['unit_root']), 'Registered main-v9 unit directory')
    e.consent(setting.shared, configuration)
    c.confirmation(setting.root, setting.run, chain, route='B' if chain == 'D' else None, configuration=configuration)
    package = load(safe_path(setting.root) / chain / 'packages' / (found['package_sha256'] + '.json'))
    require(package.sha256 == found['package_sha256'], 'The immutable event package')
    bind_event_package(setting, chain, event, package)
    unit = chain + '/test/' + event + '/' + bench
    if not (root / 'unit.json').exists():
        try:
            e.prepare_test_qualification(setting, chain, panel=panel, pinned=manifest['data'].get('pinned'))
            v221_recovery.wait_pending(root, run=setting.run, identity={'unit': unit, 'chain': chain})
            attempt = v221_recovery.next_attempt(root)
            if attempt is None:
                return c.EXIT_AWAITING
            own = units.for_unit(setting, chain, bench, unit)
            own.sandbox['cleanup_events'].clear()
            own.sandbox['start_events'].clear()
            model = p.CHAINS[chain]
            endpoint = budgets.endpoint(own, budgets.solver_scopes(chain, None, None, 'test'),
                client=own.clients(model, bench), max_tokens_bound=p.ledger_bound(model, bench,
                    branch=None if chain == 'G' else own.branch, longest=None if chain == 'G' else own.longest))
            e.make_read_canaries(setting.root, manifest['data'].get('pinned'), pools=manifest['data'].get('pools'),
                run=setting.run, evidence=setting.evidence, panel=panel, order=p.MAIN_V5_ORDER, configuration=configuration)
            evaluate_unit(root, event=event, run=setting.run, shared=setting.shared,
                pinned=manifest['data'].get('pinned'), chain=chain, bench=bench,
                chosen=arms(package, event, chain=chain, evidence=setting.evidence),
                context=units.cell_context(own, attempt, endpoint), workers=own.workers,
                canaries=e.load_canaries(setting.root, read=True, configuration=configuration),
                panel=panel, reset=reset, drain=units.drainer(setting, chain, unit))
        except Pause as pause:
            return c.EXIT_AWAITING if pause.kind == 'awaiting_owner_decision' else c.EXIT_PAUSED
    value = p.verified(read_json(root / 'unit.json'), 'evaluation')
    require(value['run'] == setting.run and value['unit'] == unit and value['status'] == 'complete',
            'The completed child read matches this run')
    require(value['packages'] == {key: arm.package.sha256 for key, arm in
            arms(package, event, chain=chain, evidence=setting.evidence).items()}, 'Completed arm packages match')
    write_json(status_path(setting, chain, event, bench), p.record('read-status', setting.evidence, {
        'run': setting.run, 'chain': chain, 'bench': bench, 'label': event, 'status': 'complete',
        'package_sha256': package.sha256, 'unit_sha256': value[p.RECORD_HASH]}))
    return c.EXIT_COMPLETE


def run_unit_spec(manifest, *, spec, docker=None, transport=None, panel=None, reset=None):
    """Recovery stays wholly inside the read child; parent sees a status mirror."""
    from . import evaluation as e, chain as c, v221_recovery
    found = read_json(spec)
    require(isinstance(found, dict) and set(found) == SPEC_FIELDS, 'Exact main-v9 read-unit spec')
    chain, bench, event = found['chain'], found['bench'], found['label']
    setting = e.setting_of(manifest, chain, docker=docker, transport=transport)
    root = unit_root(setting, chain, event, bench)
    require(safe_path(found['unit_root']) == root, 'Registered main-v9 read-unit root')
    unit = chain + '/test/' + event + '/' + bench
    def execute(root, **identity):
        before = len(e.attempts(root))
        code = _run_unit_attempt(manifest, spec=spec, docker=docker, transport=transport, panel=panel, reset=reset)
        if code == c.EXIT_COMPLETE:
            return
        if code != c.EXIT_AWAITING and len(e.attempts(root)) == before:
            c._failed_start(setting, root, code)
        raise c._status(root, unit, code)
    try:
        v221_recovery.run_unit(root, execute=execute, run=setting.run, identity={'unit':unit,'chain':chain})
    except Pause as pause:
        mirror = status_path(setting, chain, event, bench)
        index = len(list(mirror.parent.glob(mirror.stem + '-paused-*.json'))) + 1
        mirror = mirror.with_name(mirror.stem + '-paused-' + str(index) + '.json')
        write_json(mirror, p.record('read-status', setting.evidence, {
            'run': setting.run, 'chain':chain, 'bench':bench, 'label':event, 'status':'paused',
            'kind':pause.kind, 'reason':pause.reason, 'package_sha256':found['package_sha256']}))
        return c.EXIT_AWAITING if pause.kind == 'awaiting_owner_decision' else c.EXIT_PAUSED
    return c.EXIT_COMPLETE


def side(arm):
    from . import readout as r
    return 'L' if arm == 'I' else r.side(arm)


def differences(cells, first, second, items, *, on=None, secondary=False):
    from . import readout as r, v218_read
    values = []
    for item in items:
        runs = r._runs(cells, first, item)
        require(runs and runs == r._runs(cells, second, item), 'The paired arms have equal runs')
        tied = secondary and v218_read.identical_item(cells, first, second, item)
        values.append(Fraction(0) if tied else sum((r._score(cells[first,item,k]['v2'], on or side(first)) -
            r._score(cells[second,item,k]['v2'], on or side(second)) for k in runs), Fraction(0)) / len(runs))
    return values


def registered_pairs():
    pairs = []
    for k in range(1, 6):
        pairs.extend([('S'+str(k), anchor) for anchor in ('C', 'B', 'C0')])
        pairs.append(('S'+str(k), 'C0' if k == 1 else 'S'+str(k-1)))
    pairs.extend([('F','C'), ('F','B'), ('F','C0'), ('C','B'), ('C0','B'), ('C','C0'),
                  ('I','C'), ('I','C0'), ('F','I'), ('C_end','C')])
    return list(dict.fromkeys(pairs))


def with_alias(units):
    result = {}
    for bench, rows in units.items():
        result[bench] = dict(rows)
        for (arm, item, run), value in rows.items():
            if arm == 'S5':
                result[bench]['F', item, run] = value
    return result


def pair(cells, first, second, *, on=None):
    from . import readout as r, v218_read
    items = r._items(cells, first, second)
    tied = sum(v218_read.identical_item(cells, first, second, item) for item in items)
    out = {'n': len(items), 'items_reading_one_cell': 0, 'items_tied_by_identical_requests': tied}
    for name, secondary in (('primary', False), ('secondary', True)):
        values = differences(cells, first, second, items, on=on, secondary=secondary)
        out[name] = {'better': sum(v > 0 for v in values), 'worse': sum(v < 0 for v in values),
                     'tied': sum(v == 0 for v in values),
                     'estimate': r.estimate(values, design=r._design(cells, items), bootstrap=True, sensitivity=True)}
    return out


def readout(units, *, learned, procedures, label, evidence, stages=None, configuration=p.MAIN_V9,
            candidate_errors=None):
    from . import readout as r
    units = with_alias(units)
    require(set(units) == set(p.MAIN_V5_ORDER), 'Every main-v9 panel is reported')
    for bench, cells in units.items():
        require({key[0] for key in cells} == set(ARMS) | {'F'}, 'All ten read arms and the F alias')
        r._clustered(bench, cells)
        if p.is_v226(configuration):
            by_item = {}
            for (_, item, _), row in cells.items():
                by_item.setdefault(item, set()).add(row.get('block'))
            require(all(len(blocks) == 1 for blocks in by_item.values()),
                    'main-v10 readout block mismatch across arms: ' + bench)
    contrasts = {bench: {a+'-'+b: pair(cells, a, b)['primary']['estimate']
                        for a,b in registered_pairs()} for bench,cells in units.items()}
    return p.record('readout', evidence, {'configuration': configuration, 'evidence_kind': r.EVIDENCE_KIND,
        'read_label': label, 'learned': list(learned), 'imported': ['alfworld'], 'contrasts': contrasts,
        'contrasts_reading': 'descriptive', 'arms': {bench:r.arm_table(cells, configuration=configuration) for bench,cells in units.items()},
        'stages': r.stage_table(units, STAGE_ROWS, configuration=configuration),
        'stage_questions': r.stage_questions(units, STAGE_ROWS, configuration=configuration),
        'request_reuse': False, 'drift_control': {'contrast':'C_end-C','reading':'descriptive_only'},
        'placebo': {'removed':True}, 'code_vs_text': {'removed':True}, 'twins': {'removed':True},
        **({'candidate_errors': candidate_error_counts(candidate_errors),
            'candidate_error_count': sum(candidate_error_counts(candidate_errors).values())}
           if p.is_v226(configuration) else {})})



def candidate_error_counts(value):
    """Readout exposes signature counts only, never exception messages or items."""
    value = {} if value is None else value
    require(isinstance(value, dict) and all(isinstance(key, str) and key
            and type(count) is int and count >= 0 for key, count in value.items()),
            'Candidate errors are a mapping of signatures to nonnegative counts')
    return dict(sorted(value.items()))

def first_call_touch(cells, first, second, items):
    """Actual first-request touch; separate from reference whole-sequence ties."""
    from . import readout as r
    touched = unknown = 0
    for item in items:
        runs = r._runs(cells, first, item)
        require(runs == r._runs(cells, second, item), 'Touch arms have equal runs')
        pairs = [(cells[first,item,k].get('request_sha256') or [],
                  cells[second,item,k].get('request_sha256') or []) for k in runs]
        if any(not left or not right or not left[0] or not right[0] for left,right in pairs):
            unknown += 1
        else:
            touched += any(left[0] != right[0] for left,right in pairs)
    return {'touched':touched, 'n':len(items), 'unknown':unknown}


def aggregates(units, *, chain, run, run_root, label, evidence, final, package_changed, units_present=None,
               configuration=p.MAIN_V9, candidate_errors=None):
    from . import readout as r, v225_cards
    require(len(package_changed) == 5 and all(type(v) is bool for v in package_changed), 'Five package-change flags')
    units = with_alias(units)
    cards = {}
    for bench in p.MAIN_V5_ORDER:
        card = final.card_for(bench)
        if card is not None:
            meta = v225_cards.card_metadata(card)
            cards[bench] = {'id':card.id, 'sha256':card.sha256, 'chars':len(meta['text']),
                            'origin':card.origin, 'route':bench}
    procedures = {proc.id:proc.origin for proc in final.procedures if not v225_cards.is_card(proc)}
    learned = [bench for bench in p.MAIN_V5_ORDER[:-1] if bench in procedures.values() or
               (bench in cards and cards[bench]['origin'] == bench)]
    value = readout(units, learned=learned, procedures=procedures, label=label, evidence=evidence,
                    **({'configuration': configuration, 'candidate_errors': candidate_errors}
                       if p.is_v226(configuration) else {}))
    per_bench = {}
    for bench, cells in units.items():
        items = r._items(cells, *ARMS)
        per_bench[bench] = {'arms':list(ARMS)+['F'], 'items_all_arms':len(items),
            'acc':{arm:r._accuracy(cells,arm,items,side(arm)) for arm in (*ARMS,'F')},
            'acc_other_side':{arm:r._accuracy(cells,arm,items,'H' if side(arm)=='L' else 'L') for arm in (*ARMS,'F')},
            'side':{arm:side(arm) for arm in (*ARMS,'F')},
            'first_call_touch':{anchor:first_call_touch(cells,'F',anchor,items) for anchor in ('C','C0','B')},
            'solver_models':sorted({str((v.get('solver_route') or {}).get('model')) for v in cells.values()}),
            'pairs':{a+'-'+b:pair(cells,a,b) for a,b in registered_pairs()},
            'same_side_L_pairs':{a+'-'+b:pair(cells,a,b,on='L') for a,b in registered_pairs()}}
    present = units_present if units_present is not None else [r['label']+'/'+r['bench'] for r in plan_events()]
    block = {'test_read':True, 'procedures':procedures, 'cards':cards, 'learned':learned,
        'units_present':present, 'units_missing':[], 'stage_rows':STAGE_ROWS,
        'stage_row_kinds':['anchor']+['measured']*5, 'package_changed':list(package_changed),
        'readout':value, 'per_bench':per_bench,
        **({'candidate_errors': candidate_error_counts(candidate_errors),
            'candidate_error_count': sum(candidate_error_counts(candidate_errors).values())}
           if p.is_v226(configuration) else {})}
    return {'run_root':str(run_root), 'run':run, 'configuration':configuration, 'label':label,
        'evidence_kind':r.EVIDENCE_KIND, 'secondary_rule':'items with byte-identical solver request sequences count as ties',
        'arm_map':{'S5':final.sha256,'F':'alias of S5'}, 'chains':{chain:block}}


def report(manifest, *, out):
    from . import evaluation as e, v225_metrics
    configuration = p.MAIN_V9
    if p.is_v226(manifest.get('configuration')):
        configuration = manifest['configuration']
        from . import v226_metrics as metrics_module
    else:
        metrics_module = v225_metrics
    out = safe_path(out)
    require(not out.exists(), 'The main-v9 report goes to a new directory')
    root, run, evidence = safe_path(manifest['root']), manifest[p.RECORD_HASH], manifest['evidence']
    prepared = {}
    for chain in p.CHAINS:
        cr = root/chain
        receipt = p.verified(read_json(cr/'test-read.json'), 'test-read')
        require(receipt['status'] == 'read' and receipt['arms'] == list(ARMS), 'All registered reads completed')
        roots = [cr/'test'/event/bench for event in EVENTS for bench in p.MAIN_V5_ORDER]
        opened = e.unseal(root, cr, chain, roots, run=run, evidence=evidence, configuration=configuration)
        final = load(cr/'packages'/(receipt['package_sha256']+'.json'))
        previous = empty(step=chain+'/s0',evidence=evidence).sha256
        changed, candidate_errors = [], {}
        for k,bench in enumerate(p.MAIN_V5_ORDER,1):
            step = p.verified(read_json(cr/('s%d-%s'%(k,bench))/'step.json'),'step')
            current = step['package_sha256']
            changed.append(current != previous)
            previous = current
            if p.is_v226(configuration):
                for signature, count in candidate_error_counts(step.get('candidate_errors')).items():
                    candidate_errors[signature] = candidate_errors.get(signature, 0) + count
        agg = aggregates(opened['units'], chain=chain, run=run, run_root=root, label=opened['label'],
                         evidence=evidence, final=final, package_changed=changed,
                         **({'configuration': configuration, 'candidate_errors': candidate_errors}
                            if p.is_v226(configuration) else {}))
        prepared[chain] = (agg, metrics_module.compute(agg, chain))
    out.mkdir(parents=True)
    for chain,(agg,metrics) in prepared.items():
        write_json(out/('readout-'+chain+'.json'), agg['chains'][chain]['readout'])
        write_json(out/('readout-aggregates-'+chain+'.json'), agg)
        write_json(out/('cl-metrics-'+chain+'.json'), metrics)
        (out/('cl-metrics-'+chain+'.md')).write_text(metrics_module.markdown(metrics), encoding='utf-8')
    return {chain:agg['chains'][chain]['readout'][p.RECORD_HASH] for chain,(agg,_) in prepared.items()}


@lru_cache(maxsize=1)
def structural_readout_demo(configuration=p.MAIN_V9):
    """Production readout/aggregate/CL paths on authored outcomes, never a panel."""
    if p.is_v226(configuration):
        from . import v226_metrics as v225_metrics
    else:
        from . import v225_metrics
    units = {}
    for bench in p.MAIN_V5_ORDER:
        values = {}
        for arm_index, arm in enumerate(ARMS):
            for item in range(6):
                token = 'pass' if item < arm_index % 7 else 'fail'
                values[arm, str(item), 0] = {'v2':token,'token':token,'kind':None,
                    'shared_with':None,'answered':True,'enabled':[], 'block':'authored',
                    'room':'authored-room-'+str(item % 3), 'format':{},'flags':[],
                    'request_sha256':['authored-'+('C0' if arm=='S1' else arm)+'-'+str(item)]}
        units[bench] = values
    aggregate = aggregates(units, chain='G', run='authored-main-v9', run_root='/authored',
        label='engineering_fixture', evidence='engineering_fixture',
        final=empty(step='G/s5',evidence='engineering_fixture'), package_changed=[False,True,False,True,False],
        **({'configuration': configuration} if p.is_v226(configuration) else {}))
    metrics = v225_metrics.compute(aggregate, 'G')
    if p.is_v226(configuration):
        from .v225_metrics import reference
        ref = reference()
    else:
        ref = v225_metrics.reference()
    parsed = ref.chains_from_readout(aggregate,configuration,'authored-main-v9')['G']
    require(all(metrics['anchor_C'][an] == ref.cl_metrics(parsed,an,metrics['similar']) for an in ('P','S')),
            'Authored anchor_C metrics exactly equal the pinned independent implementation')
    require([row['step'] for row in metrics['same_text']] == [1,3,5],
            'Unchanged steps are reported only as same-text noise')
    return {'passed':True,'evidence':'engineering_fixture','model_calls':0,'sealed_reads':0,
        'panels':5,'arms':10,'authored_cells':300,'pairs_per_bench':len(registered_pairs()),
        'aggregate_sha256':digest(aggregate),'metrics_sha256':digest(metrics),
        'reference_sha256':v225_metrics.REFERENCE_SHA256,'anchor_C_equal':True,
        'same_text_steps':[1,3,5],'C_end':'descriptive_only'}
