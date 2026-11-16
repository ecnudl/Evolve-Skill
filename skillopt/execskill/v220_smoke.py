"""SearchQA-only preparation and practice readiness for the rejected-candidate read."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from functools import partial
import hashlib
import math
import sys

from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest
from . import budgets, evaluation, manifest, prelaunch, profiles as p, rounds, routes, smoke, units
from . import v214_smoke as v, v218_read, v220_import
from .cells import Arm, TrainingStore, cell_id, run_cells
from .package import empty
from .sandbox import client as sandbox

BENCH = 'searchqa'
PRACTICE_ITEMS = 20
STAGES = ('S0', 'S1', 'S2', 'SE6')


def probe_items(chain):
    """Public authored mechanism probes, never sampled from a benchmark panel."""
    require(chain in p.CHAINS, 'A SearchQA practice probe belongs to G or D')
    public = ({
        'echo': {'question': 'Which inventor designed the copper clock mechanism?',
                 'context': '[DOC] [TLE] Inventor clock notes [PAR] An inventor designed the copper clock mechanism. | Ada Rowan'},
        'name': {'question': 'Where did Ada Rowan work?', 'context': 'Ada Rowan worked in Cedar Bay. Ada Rowan stayed there.'},
        'silent': {'question': 'Where?', 'context': 'somewhere'},
    } if chain == 'G' else {
        'phrase': {'question': 'Which inventor designed the clock?',
                   'context': '[DOC] Ada Rowan designed a clock. [DOC] Ada Rowan built another clock.'},
        'this': {'question': 'Who built this copper clock?',
                 'context': 'Ada Rowan built a copper clock. The copper clock works.'},
        'silent': {'question': 'Where?', 'context': 'somewhere'},
    })
    return [{'task_id': 'v220-authored-' + chain + '-' + key, 'public': value,
             'private': {'answers': ['authored probe only']}} for key, value in public.items()]


def schedule():
    return {'configuration': p.SEARCHQA_HP_V6, 'chains': ['G', 'D'], 'stages': list(STAGES),
        'benchmarks': [BENCH], 'S1': {'G': 'one first reply; fixed registered GLM bound',
            'D': 'one first reply plus three inherited northgate length probes on SearchQA'},
        'S2': {BENCH: PRACTICE_ITEMS}, 'S2_arms': ['C', 'F'],
        'S2_authored_probes': {'items_per_chain': 3, 'arms': ['C', 'F'],
            'public_sha256': {chain: digest(probe_items(chain)) for chain in p.CHAINS},
            'purpose': 'two candidate note triggers and one silent request-reuse case; no effect estimate'},
        'SE6': {'procedure_cost': 'max(registered factor over measured card, measured procedure)',
            'card_cost': 'maximum dispatched per-arm class mean; shared cells excluded',
            'stage_packages': 0, 'gate': 'one SearchQA read plus one read-unit retry and reservation'},
        'maximum_schedule': manifest._plain(p.searchqa_hp_v6_identity())}


def prompt_pins():
    """No role calls; pin the inherited SearchQA prompt bytes for identity only."""
    old = manifest.prompt_sha(p.MAIN_V6)
    return {'parent': p.MAIN_V6, 'parent_prompt_sha': old,
            'dispatch': {BENCH: p.machinery_configuration(p.MAIN_V6, BENCH)}}


def _selected_preparation(source):
    """Project frozen main-v6 metadata without touching any referenced panel."""
    require(source.get('configuration') == p.MAIN_V6
            and source.get('evidence') == p.REAL_RUN_EVIDENCE[p.MAIN_V6],
            'SearchQA preparation requires the frozen real main-v6 manifest')
    data = source['data']
    pinned = data['pinned']
    paths = {'split': pinned['paths']['split']}
    for group in ('test', 'train', 'val'):
        paths[group] = {BENCH: pinned['paths'][group][BENCH]}
    kept_paths = [paths['split'], *(row[BENCH] for row in paths.values() if isinstance(row, dict))]
    selected_pins = {'paths': paths,
        'sha256': {str(safe_path(path)): pinned['sha256'][str(safe_path(path))] for path in kept_paths}}
    pool = deepcopy(data['pools'][BENCH])
    closed = {safe_path(pinned['paths']['split'])}
    for group in ('test', 'layouts', 'upstream'):
        closed.update(safe_path(path) for path in pinned['paths'].get(group, {}).values())
    require(not any(safe_path(pool['path']) == path or safe_path(pool['path']).is_relative_to(path)
                    for path in closed), 'The SearchQA practice pool must not alias a closed source')
    allocation = deepcopy(data['allocations'][BENCH])
    protected = deepcopy(data['protected_ids'][BENCH])
    require(allocation['source_pins']['pool'] == pool
            and allocation['source_pins']['protected_ids'] == protected,
            'The SearchQA practice allocation retains its main-v6 pool and protected pins')
    smoke_ids = allocation['slices']['smoke'][:PRACTICE_ITEMS]
    require(len(smoke_ids) == len(set(smoke_ids)) == PRACTICE_ITEMS,
            'Twenty distinct inherited SearchQA smoke items are pinned')
    contract = deepcopy(source['contracts'][BENCH])
    require(contract['sha'] == hashlib.sha256(contract['text'].encode()).hexdigest(),
            'The inherited SearchQA contract hash differs')
    return {'data': {'pinned': selected_pins, 'pools': {BENCH: pool}},
        'cards': {BENCH: source['cards'][BENCH]}, 'contracts': {BENCH: contract},
        'runtime': {BENCH: deepcopy(source['runtime'][BENCH])},
        'allocations': {BENCH: allocation}, 'protected_ids': {BENCH: protected},
        'smoke_ids': smoke_ids, 'fixtures': {}, 'sheet_qualification': None}


def preparation(path):
    path = safe_path(path)
    raw = path.read_bytes()
    import json
    source = p.verified(json.loads(raw), 'manifest')
    found = _selected_preparation(source)
    # Only the public practice pool is opened. Its IDs are checked against the
    # source's frozen protected hashes, without reopening the split or panel.
    items = manifest._items(found['data']['pools'][BENCH], BENCH)
    from . import v211_protection
    v211_protection.check_items(BENCH, items, found['protected_ids'][BENCH]['id_hashes'])
    require(set(found['smoke_ids']) <= {row['task_id'] for row in items},
            'The inherited SearchQA smoke IDs exist in the pinned practice pool')
    return {**found, 'registration': {'configuration': p.SEARCHQA_HP_V6,
        'source_main_v6_manifest': {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                                  'record_sha256': source[p.RECORD_HASH]},
        'sealed_reads': 0, 'practice_only': True}, 'source_manifest': source}


def verify_preparation(value):
    source = p.verified(value.get('source_manifest'), 'manifest')
    expected = _selected_preparation(source)
    registration = value.get('registration', {})
    pin = registration.get('source_main_v6_manifest', {})
    require(registration.get('configuration') == p.SEARCHQA_HP_V6
            and registration.get('sealed_reads') == 0 and registration.get('practice_only') is True
            and pin.get('record_sha256') == source[p.RECORD_HASH]
            and isinstance(pin.get('sha256'), str) and len(pin['sha256']) == 64
            and all(value.get(key) == row for key, row in expected.items()),
            'SearchQA preparation differs from its pinned main-v6 metadata')
    return value


def check_source_binding(imported, source_pins):
    require(imported['source_manifest']['root'] == source_pins['main_v6_root']
            and all(row['chain_complete']['record']['identity']['run']
                    == imported['source_manifest'][p.RECORD_HASH] for row in source_pins['main_v6'].values()),
            'The completed main-v6 packages belong to the frozen preparation manifest and root')


def collect_s0(out, *, preparation_file, root, selftest, main_v6_root=p.MAIN_V6_ROOT,
               snapshot_root=None, checks=None, consent_file=None):
    out, root, source = safe_path(out), safe_path(root), safe_path(snapshot_root or manifest.REPO)
    require(not (out / v.S0_FILE).exists() and not out.is_relative_to(manifest.REPO),
            'A new SearchQA S0 outside the checkout')
    imported = preparation(preparation_file)
    source_pins = v220_import.pins(main_v6_root)
    check_source_binding(imported, source_pins)
    tested = p.verified(read_json(selftest), 'sandbox-selftest')
    require(tested.get('passed') is True and set(tested['measured']) == manifest.MEASURED_FIELDS
            and tested['measured']['native_peak_rss_kib'] is None,
            'Passing SearchQA selftest without a native sheet measurement')
    allowed = v.prepare_consent(root, p.SEARCHQA_HP_V6, consent_file=consent_file)
    checked = prelaunch.zero_call_checks(source, python=sys.executable) if checks is None else checks
    fingerprint = source / 'tests/fixtures/execskill/v220_parents_before.json'
    require(fingerprint.is_file(), 'The before-edit parent fingerprint is included in the snapshot')
    value = p.record('v214-s0', 'smoke', {'configuration': p.SEARCHQA_HP_V6, 'root': str(root),
        'preparation': imported, 'preparation_file': str(safe_path(preparation_file)),
        v220_import.PIN_KEY: source_pins, 'consent_sha256': digest(allowed), 'consent': allowed,
        'prompt_pins': prompt_pins(), 'smoke_schedule': schedule(),
        'authored_probe_items': {chain: probe_items(chain) for chain in p.CHAINS},
        'parents_before_sha256': hashlib.sha256(fingerprint.read_bytes()).hexdigest(),
        'sandbox': tested[p.RECORD_HASH], 'limits': tested['limits'], 'measured': tested['measured'],
        'pytest': checked, 'sealed_reads': 0, 'snapshot_root': str(source), 'snapshot_sha256': v._source(source),
        'passed': tested['passed'] is True and checked.get('passed') is True})
    write_json(out / v.S0_FILE, value)
    return value


def selftest(out, *, preparation_file):
    out = safe_path(out)
    require(not (out / smoke.SELFTEST).exists(), 'A selftest is written once')
    imported = preparation(preparation_file)
    target = out / 'training-views' / 'searchqa.json'
    items = manifest._items(imported['data']['pools'][BENCH], BENCH)
    if target.exists():
        require(read_json(target) == items, 'Selftest practice inputs remain unchanged')
    else:
        write_json(target, items)
    worker = smoke.sandbox_selftest(out / 'worker-selftest', item_files=[target], configuration=p.SEARCHQA_HP_V6)
    measured = {key: worker['measured'][key] for key in ('vsz_kib', 'rss_kib', 'view_bytes_p99')}
    value = p.record('sandbox-selftest', worker['evidence'], {
        **{key: row for key, row in worker.items() if key not in ('version', 'evidence', p.RECORD_HASH, 'measured')},
        'measured': {**measured, 'native_peak_rss_kib': None},
        'measurement_sources': {'worker': worker[p.RECORD_HASH], 'benchmarks': [BENCH],
            'native_peak': 'not_applicable_no_environment_work', 'zebra_worker': None}})
    write_json(out / smoke.SELFTEST, value)
    return value


def make_manifest(out, *, root, s0_file, provenance, roles_repo, route_b_env,
                  smoke_chain=None, measured_smoke=(), environment_found=None):
    checked = p.verified(read_json(s0_file), 'v214-s0')
    require(checked.get('passed') is True and checked.get('configuration') == p.SEARCHQA_HP_V6,
            'A passing SearchQA S0')
    root = safe_path(root)
    require(smoke_chain in (None, 'G', 'D'), 'A smoke names one chain')
    require(smoke_chain is not None or str(root) == p.RUN_ROOTS[p.SEARCHQA_HP_V6], 'The registered SearchQA real root')
    require(digest(checked['consent']) == checked['consent_sha256'], 'S0 consent bytes are pinned')
    if not (root / 'shared/consent.json').exists():
        write_json(root / 'shared/consent.json', checked['consent'])
    require(evaluation.consent(root / 'shared', p.SEARCHQA_HP_V6) == checked['consent'],
            'S0 and manifest bind the same owner consent')
    imported = verify_preparation(checked['preparation'])
    require(preparation(checked['preparation_file']) == imported,
            'The source SearchQA preparation and practice pins remain identical to S0')
    source_pins = v220_import.validate_pins(checked[v220_import.PIN_KEY])
    check_source_binding(imported, source_pins)
    proven, source = read_json(provenance), v._source(manifest.REPO)
    require(checked['snapshot_sha256'] == source == proven.get('sha256_list_sha256')
            and safe_path(checked['snapshot_root']) == manifest.REPO
            and safe_path(proven['snapshot_root']) == manifest.REPO,
            'S0 and provenance certify the current source snapshot')
    require(checked['smoke_schedule'] == schedule() and checked['prompt_pins'] == prompt_pins(),
            'The SearchQA smoke schedule and inherited prompts are unchanged')
    readiness, terms = {}, {}
    if smoke_chain is None:
        require(len(measured_smoke) == 2, 'Real SearchQA read requires both measured chain smoke receipts')
        for path in measured_smoke:
            raw = p.verified(read_json(path), 'v214-smoke-result')
            chain = raw.get('chain')
            require(chain in p.CHAINS and chain not in readiness, 'One measured receipt per chain')
            receipt, se6 = v.measured_readiness(path, chain=chain, source_sha256=source,
                s0_sha256=checked[p.RECORD_HASH], configuration=p.SEARCHQA_HP_V6)
            readiness[chain], terms[chain] = receipt, se6['read_terms']
        require(set(readiness) == set(p.CHAINS), 'Both routes have measured SearchQA smoke')
    for chain in p.CHAINS:
        if chain not in terms:
            anchor = {BENCH: {'card': p.CELL_ANCHORS[BENCH][1 if chain == 'G' else 0], 'procedure_assumed': True}}
            terms[chain] = {b: str(n) for b, n in p.read_estimate_terms(anchor, 1, p.SEARCHQA_HP_V6).items()}
    longest = readiness['D']['stage_records']['S1']['result']['solver_bounds']['longest'] if readiness else routes.S1B_CEILING
    blocks = {'G': manifest.solver_block('G', env_path=roles_repo, configuration=p.SEARCHQA_HP_V6),
              'D': manifest.solver_block('D', env_path=route_b_env, branch='N', longest=longest, configuration=p.SEARCHQA_HP_V6)}
    data = {**deepcopy(imported['data']), v220_import.PIN_KEY: source_pins,
        'v214_s0': checked, 'v214_preparation': imported['registration'], 's0_sha256': checked[p.RECORD_HASH],
        'snapshot_sha256': source, 'allocations': imported['allocations'], 'protected_ids': imported['protected_ids'],
        'smoke_schedule': schedule(), 'launchable_chains': [smoke_chain] if smoke_chain else ['G', 'D'],
        'v214_readiness': readiness, 'test_read_terms': terms,
        'test_read_estimate': {c: math.ceil(sum(Fraction(n) for n in row.values())) for c, row in terms.items()}}
    return manifest.make(out, evidence='smoke' if smoke_chain else p.REAL_RUN_EVIDENCE[p.SEARCHQA_HP_V6],
        measured=checked['measured'], limits={k: sandbox.Limits(**row) for k, row in checked['limits'].items()},
        environment_found=environment_found, configuration=p.SEARCHQA_HP_V6, root=str(root), data=data,
        cards=imported['cards'], contracts=imported['contracts'], fixtures=imported['fixtures'],
        runtime=imported['runtime'], sheet_qualification=None, provenance=proven,
        clients={'solver': blocks, 'roles': manifest.role_settings(p.SEARCHQA_HP_V6), 'routes': {'D': {'B':
            routes.pin('D', 'B', env_path=route_b_env, solver_block=blocks['D'], configuration=p.SEARCHQA_HP_V6)}}})


def check_manifest(value):
    data = value['data']
    checked = p.verified(data.get('v214_s0'), 'v214-s0')
    imported = verify_preparation(checked['preparation'])
    require(checked.get('passed') is True and checked.get('configuration') == p.SEARCHQA_HP_V6
            and checked.get('sealed_reads') == 0 and checked.get('pytest', {}).get('passed') is True
            and checked[p.RECORD_HASH] == data.get('s0_sha256')
            and checked.get('snapshot_sha256') == data.get('snapshot_sha256')
            and checked.get('smoke_schedule') == data.get('smoke_schedule') == schedule()
            and checked.get('prompt_pins') == value['prompt_sha'] == prompt_pins()
            and checked.get('authored_probe_items') == {chain: probe_items(chain) for chain in p.CHAINS},
            'A complete source-bound SearchQA S0')
    require(value['sheet_qualification'] is None and value['sandbox']['measured']['native_peak_rss_kib'] is None,
            'SearchQA has no sheet qualification or native memory measurement')
    for key in ('cards', 'contracts', 'runtime', 'fixtures'):
        require(value[key] == imported[key], 'The frozen main-v6 SearchQA ' + key + ' remain unchanged')
    require(all(data.get(key) == imported['data'][key] for key in ('pinned', 'pools'))
            and data.get('allocations') == imported['allocations']
            and data.get('protected_ids') == imported['protected_ids'],
            'SearchQA panel and practice metadata remain identical to S0')
    require(data.get(v220_import.PIN_KEY) == checked[v220_import.PIN_KEY], 'S0 binds every import record copy')
    v220_import.validate_pins(data[v220_import.PIN_KEY])
    check_source_binding(imported, data[v220_import.PIN_KEY])
    require(value['sizes']['v214'] == manifest._plain(p.searchqa_hp_v6_identity()), 'The SearchQA read schedule is pinned')
    require(data.get('launchable_chains') in (['G'], ['D'], ['G', 'D']), 'One smoke chain or both real chains')
    if value['evidence'] == p.REAL_RUN_EVIDENCE[p.SEARCHQA_HP_V6]:
        require(set(data.get('v214_readiness', {})) == set(p.CHAINS), 'Both chain smoke receipts are required')
        for chain, receipt in data['v214_readiness'].items():
            _, projected = v.checked_readiness(receipt, chain=chain, source_sha256=data['snapshot_sha256'],
                s0_sha256=data['s0_sha256'], configuration=p.SEARCHQA_HP_V6)
            require(data['test_read_terms'][chain] == projected['read_terms']
                    and data['test_read_estimate'][chain] == projected['read_estimate'], 'Measured SearchQA estimate is pinned')
            bounds, block = receipt['stage_records']['S1']['result']['solver_bounds'], value['clients']['solver'][chain]
            require(block['branch'] == bounds['branch'] and block['longest'] == bounds['longest']
                    and block['B'] == bounds['ledger_bound'], 'Real SearchQA solver bounds equal S1')
    return value


def checked_s1_probe(probe):
    """The inherited northgate probe on SearchQA, with no Zebra request or worker."""
    from . import client, v29_route_probe
    require(isinstance(probe, dict), 'SearchQA S1 requires its measured northgate probe')
    rows, ceiling = probe.get('receipts', []), probe.get('request_ceiling')
    nominal = p.solver_tokens(p.CHAINS['D'], BENCH)
    require(probe.get('passed') is True and probe.get('route') == client.ROUTE_B
            and probe.get('provider') == client.ROUTES[client.ROUTE_B].backend
            and probe.get('model') == client.NORTHGATE_MODEL and probe.get('branch') == 'N'
            and probe.get('bench') == BENCH and probe.get('max_tokens') == nominal
            and probe.get('prompt') == v29_route_probe.prompt_pins()
            and probe.get('calls') == v29_route_probe.PROBE_CALLS
            and isinstance(rows, list) and len(rows) == v29_route_probe.PROBE_CALLS
            and probe.get('first_response_confirmed') is True
            and probe.get('code_sha256') == digest(manifest.pin_code())
            and type(ceiling) is int and ceiling >= nominal,
            'SearchQA S1 binds three measured northgate receipts, source and frozen prompt')
    counts = []
    for row in rows:
        count, request = (row.get('usage') or {}).get('completion_tokens'), row.get('request_sha256')
        require(row.get('passed') is True and row.get('route') == client.ROUTE_B
                and row.get('returned_model') in client.NORTHGATE_RESPONSE_MODEL_IDS
                and type(count) is int and 0 < count <= ceiling
                and isinstance(request, str) and len(request) == 64 and set(request) <= set('0123456789abcdef')
                and type(row.get('tokens')) is int and row['tokens'] > 0,
                'SearchQA S1 retains accepted replies, positive usage and request hashes')
        counts.append(count)
    require(probe.get('longest') == max(counts)
            and probe.get('ledger_bound') == p.ledger_bound(p.CHAINS['D'], BENCH, branch='N', longest=max(counts))
            and probe.get('tokens') == sum(row['tokens'] for row in rows),
            'SearchQA S1 bound derives from measured receipt completion counts')
    return probe


def solver_probe(first, chain, probe=None):
    from . import client
    first = p.verified(first, 'first-call')
    echo = client.NORTHGATE_RESPONSE_MODEL_IDS if chain == 'D' else {p.CHAINS['G']}
    require(first.get('passed') is True and first.get('identity', {}).get('chain') == chain
            and first.get('model') == p.CHAINS[chain] and first.get('returned_model') in echo
            and first.get('bench') == BENCH and type(first.get('charged')) is int and first['charged'] > 0
            and isinstance(first.get('request_sha256'), str) and len(first['request_sha256']) == 64,
            'SearchQA S1 requires its confirmed first solver response')
    if chain == 'D':
        checked_s1_probe(probe)
        return {**probe, 'first_call': first}
    require(first.get('bound') == first.get('max_tokens') == p.ledger_bound(p.CHAINS['G'], BENCH),
            'SearchQA G uses its fixed inherited solver bound')
    return {'passed': True, 'chain': chain, 'model': p.CHAINS[chain], 'first_call': first}


def check_solver_bounds(chain, stages):
    probe = stages['S1']['result'].get('solver_probe')
    require(isinstance(probe, dict), 'SearchQA stages retain the confirmed solver probe')
    length = {key: row for key, row in probe.items() if key != 'first_call'} if chain == 'D' else None
    require(probe == solver_probe(probe.get('first_call'), chain, length), 'The SearchQA solver probe is unchanged')
    require(probe['first_call']['identity']['run'] == stages['S1']['manifest_sha256']
            and stages['S1']['result'].get('solver_confirmation') == probe['first_call'][p.RECORD_HASH],
            'SearchQA first response belongs to this smoke manifest')
    expected = v.solver_bounds(chain, probe, configuration=p.SEARCHQA_HP_V6)
    for name in ('S1', 'S2', 'SE6'):
        require(stages[name]['result'].get('solver_bounds') == expected
                and stages[name]['result'].get('solver_probe') == probe,
                'SearchQA S1/S2/SE6 share the same confirmed probe and solver bounds')
    return expected


def s1(setting, chain):
    from . import chain as chains, v29_route_probe
    first = chains.first_call(setting, chain)
    probe = v29_route_probe.measure(setting, bench=BENCH) if chain == 'D' else None
    probe = solver_probe(first, chain, probe)
    return {'passed': True, 'solver_confirmation': first[p.RECORD_HASH], 'solver_probe': probe,
            'solver_bounds': v.solver_bounds(chain, probe, configuration=p.SEARCHQA_HP_V6), 'sealed_reads': 0}


def practice(setting, attempt, endpoint, unit, tasks, chain):
    """Twenty reserved C cells plus three authored C/F mechanism pairs."""
    from . import v220_read
    require(len(tasks) == PRACTICE_ITEMS, 'Twenty inherited SearchQA practice items')
    context = units.cell_context(setting, attempt, endpoint)
    card = empty(step=unit, evidence=setting.evidence)
    final = v220_import.final_package(chain, setting.evidence, setting.extra[v220_import.PIN_KEY])
    arms = v220_read.arms(final, card)
    first_key = next(iter(tasks))
    first = rounds.run_round(replace(setting, workers=1), attempt, endpoint, unit, {'C': arms['C']},
        {'C': [(first_key, 1)]}, tasks, tag='first-response')
    first_cell = next(iter(first.values()))[0]
    require(first_cell.get('final') is not None and first_cell.get('stop') is None,
            'A confirmed actual first reply precedes concurrent SearchQA practice cells')
    rest = rounds.run_round(setting, attempt, endpoint, unit, {'C': arms['C']},
        {'C': [(key, 1) for key in tasks if key != first_key]}, tasks, tag='measured')
    inherited = [first_cell, *(row for group in rest.values() for row in group)]
    probes = {rounds.key(BENCH, row['task_id']): {'public': row['public'], 'private': row['private']}
              for row in probe_items(chain)}
    require(not set(probes) & set(tasks), 'Authored probes do not overlap inherited practice IDs')
    planned = v218_read.plan({'tasks': [{'task_id': key, **task} for key, task in probes.items()]}, arms, {},
        bench=BENCH, context=context, workers=partial(evaluation._route_worker, setting))

    class CapturedStore(TrainingStore):
        def __init__(self):
            super().__init__(attempt)
            self.rows = {}

        def save(self, value, trajectory):
            self.rows[value['cell']['id']] = value
            return super().save(value, trajectory)

    captured = CapturedStore()
    store = v218_read.Store(captured, planned)
    jobs, linked = [], []
    for key, task in probes.items():
        for label in ('C', 'F'):
            cell = {'id': cell_id(unit, label, key, 0), 'unit': unit, 'arm': label,
                    'benchmark': BENCH, 'task_id': key, 'run': 0}
            job = cell, task, arms[label]
            source = planned['sources'][label][key]
            (jobs if source is None else linked).append(job if source is None else (job, source))
    ran = run_cells(context, jobs, workers=setting.workers, store=store)
    sources = {(job[0]['arm'], job[0]['task_id'], 0): row for job, row in zip(jobs, ran)}
    fallback = v218_read.linked(context, linked, sources, planned, store=store)
    if fallback:
        run_cells(context, fallback, workers=setting.workers, store=store)
    diagnostic = list(captured.rows.values())
    rows = inherited + diagnostic
    dispatched = [row for row in rows if row.get('shared_with') is None]
    measured = smoke.measured_cells(dispatched)
    costs = {label: smoke.measured_cells([row for row in dispatched if row['cell']['arm'] == label])['per_class'][BENCH]
             for label in ('C', 'F') if any(row['cell']['arm'] == label for row in dispatched)}
    coverage = {key: {label: next(row for row in diagnostic if row['cell']['arm'] == label
                and row['cell']['task_id'] == key) for label in ('C', 'F')} for key in probes}
    public_coverage = {key: {label: {'cell': row['cell']['id'], 'shared_with': row.get('shared_with'),
        'request_sha256': [call['request_sha256'] for call in row.get('logical_calls', [])],
        'request_reuse': row.get('request_reuse'), 'searchqa_fired': row['searchqa_fired']}
        for label, row in labels.items()} for key, labels in coverage.items()}
    fired = v220_read.fired_counts({(row['cell']['arm'], row['cell']['task_id'], 0): row for row in diagnostic},
                                  {proc.id: proc.origin for proc in final.procedures})
    reuse = v218_read.counts(diagnostic, planned)
    valid = all((row.get('final') or {}).get('token') in ('pass', 'fail') for row in rows)
    return {'passed': valid and len(rows) == PRACTICE_ITEMS + 6
            and all(row['fired_items'] > 0 for row in fired['per_procedure'].values())
            and reuse['shared_cells'] >= 1,
        'items': PRACTICE_ITEMS, 'cells': len(rows), 'inherited_C_cells': len(inherited),
        'authored_probe_items': 3, 'authored_probe_cells': len(diagnostic), 'arms': ['F', 'C'],
        'probe_items_sha256': digest(probe_items(chain)), 'probe_coverage': public_coverage,
        'dispatched_cells': len(dispatched), 'measurements': measured, 'cost_by_arm': costs,
        'request_reuse': reuse, 'searchqa_fired': fired,
        'settled_tokens': sum(send.get('charged', 0) for row in dispatched for send in row['sends']),
        'first_response_confirmed': True, 'sealed_reads': 0,
        'source_kind': 'reserved_smoke_plus_explicit_authored_mechanism_probes', 'benchmark_effect_evidence': False}


def s2(setting, chain):
    name = chain + '/v214-smoke/S2/searchqa'
    local = units.for_unit(setting, chain, BENCH, name)
    lookup = {row['task_id']: row for row in setting.pools[BENCH]}
    ids = setting.extra['allocations'][BENCH]['slices']['smoke'][:PRACTICE_ITEMS]
    require(len(ids) == PRACTICE_ITEMS and set(ids) <= set(lookup), 'Pinned SearchQA practice smoke IDs')
    tasks = {rounds.key(BENCH, key): {'public': lookup[key]['public'], 'private': lookup[key]['private']} for key in ids}

    def work(attempt):
        endpoint = budgets.endpoint(local, ('overall', chain + ':solver'), client=local.clients(p.CHAINS[chain], BENCH),
            max_tokens_bound=p.ledger_bound(p.CHAINS[chain], BENCH, branch=local.branch, longest=local.longest))
        return practice(local, attempt, endpoint, name, tasks, chain)

    row = units.run_unit(safe_path(setting.root) / name, run=setting.run, identity={'unit': name},
        work=work, evidence=setting.evidence, configuration=p.SEARCHQA_HP_V6,
        drain=units.drainer(setting, chain, name))['result']
    return {'passed': row['passed'], 'chain': chain, 'benches': {BENCH: row}, 'cells': row['cells'], 'sealed_reads': 0}


def measured_prices(row, chain):
    from . import v220_read
    measured, coverage = row.get('measurements', {}), row.get('probe_coverage', {})
    keys = {rounds.key(BENCH, item['task_id']) for item in probe_items(chain)}
    require(row.get('passed') is True and row.get('arms') == ['F', 'C']
            and row.get('items') == row.get('inherited_C_cells') == PRACTICE_ITEMS
            and row.get('authored_probe_items') == 3 and row.get('authored_probe_cells') == 6
            and row.get('cells') == PRACTICE_ITEMS + 6 and set(coverage) == keys
            and row.get('probe_items_sha256') == digest(probe_items(chain))
            and row.get('sealed_reads') == 0 and row.get('first_response_confirmed') is True,
            'SearchQA SE6 requires reserved practice and every authored C/F probe')
    keyed, shared = {}, 0
    for key, labels in coverage.items():
        require(set(labels) == {'F', 'C'}, 'Every SearchQA probe covers both arms')
        for label, entry in labels.items():
            require(isinstance(entry.get('cell'), str) and entry['cell'], 'SearchQA probe cell identity')
            keyed[(label, key, 0)] = entry
            if entry.get('shared_with') is None:
                require(entry.get('request_sha256'), 'Dispatched SearchQA probe requests are retained')
            else:
                shared += 1
                annotation = entry.get('request_reuse') or {}
                identity = annotation.get('identity')
                require(label == 'F' and entry['shared_with'] == labels['C']['cell']
                        and labels['C'].get('shared_with') is None
                        and annotation.get('version') == v218_read.VERSION
                        and annotation.get('source_arm') == annotation.get('planned_source_arm') == 'C'
                        and isinstance(identity, dict) and identity == annotation.get('source_identity')
                        and identity.get('fault_free') is True
                        and labels['C'].get('request_sha256', [None])[0] == identity.get('request_sha256'),
                        'SearchQA shared probe retains its actual source request identity')
    fired = v220_read.fired_counts(keyed, {pid: BENCH for pid in v220_import.PROCEDURE_IDS[chain]})
    require(fired == row.get('searchqa_fired')
            and all(entry['fired_items'] > 0 for entry in fired['per_procedure'].values())
            and shared >= 1 and row.get('request_reuse', {}).get('shared_cells') == shared,
            'Both SearchQA procedures emit notes and an identical F request shares C')
    per_arm = measured.get('per_arm', {}).get(BENCH, {})
    costs = row.get('cost_by_arm', {})
    require(set(costs) == set(per_arm) == {'C', 'F'}
            and per_arm['C']['cells'] == PRACTICE_ITEMS + 3
            and per_arm['F']['cells'] == 3 - shared
            and row.get('dispatched_cells') == PRACTICE_ITEMS + 6 - shared,
            'SearchQA cost denominators count dispatched cells only')
    prices = {'card': [], 'procedure': []}
    for label, groups in costs.items():
        require(groups and set(groups) <= set(prices)
                and sum(item['cells'] for item in groups.values()) == per_arm[label]['cells']
                and sum(item['tokens'] for item in groups.values()) == per_arm[label]['tokens'],
                'SearchQA per-arm cost classes sum to measured usage')
        for kind, entry in groups.items():
            require(entry['cells'] > 0 and entry['tokens'] > 0, 'Positive measured SearchQA usage')
            prices[kind].append(Fraction(entry['tokens'], entry['cells']))
    require(prices['card'] and prices['procedure'], 'Both SearchQA card and note-bearing package costs are measured')
    card = max(prices['card'])
    procedure = max([card * p.PROCEDURE_ARM_FACTOR[1], *prices['procedure']])
    return {'card': str(card), 'procedure': str(procedure), 'procedure_assumed': False,
            'basis': 'maximum dispatched per-arm class mean; procedure at least registered card factor'}


def projection(s2, chain, *, bounds):
    require(s2.get('passed') is True and set(s2.get('benches', {})) == {BENCH},
            'SearchQA SE6 uses only its measured practice bench')
    row = s2['benches'][BENCH]
    prices = measured_prices(row, chain)
    measured = row['measurements']
    actual, charged = measured['actual'], row['settled_tokens']
    require(actual > 0 and charged > 0, 'Positive measured SearchQA usage and settled charge')
    ratio = Fraction(charged, actual)
    numeric = {BENCH: {**prices, 'card': Fraction(prices['card']), 'procedure': Fraction(prices['procedure'])}}
    terms = p.read_estimate_terms(numeric, ratio, p.SEARCHQA_HP_V6)
    estimate = math.ceil(sum(terms.values()))
    reserved = reservation(measured['request_bytes'][BENCH], bounds['ledger_bound'][BENCH])
    caps = budgets.chain_caps(chain, p.SEARCHQA_HP_V6)
    maximum = math.ceil(2 * sum(terms.values()) + reserved)
    scopes = {scope: {'projected': maximum, 'cap': caps[scope], 'passed': maximum <= caps[scope]}
              for scope in (chain + ':test', chain + ':solver')}
    read_need = max(estimate + reserved, math.ceil(estimate * p.TEST_START_FACTOR))
    read_scopes = {scope: {'projected': read_need, 'cap': caps[scope], 'passed': read_need <= caps[scope]}
                   for scope in scopes}
    return {'passed': all(row['passed'] for row in scopes.values()) and all(row['passed'] for row in read_scopes.values()),
        'configuration': p.SEARCHQA_HP_V6, 'chain': chain, 'per_cell': {BENCH: prices}, 'ratio': str(ratio),
        'read_terms': {b: str(n) for b, n in terms.items()}, 'read_estimate': estimate,
        'read_reservation': reserved, 'read_start_factor': str(p.TEST_START_FACTOR),
        'later_G_cost_factor': 'not_applicable_no_learning_run', 'read_scopes': read_scopes, 'solver_scopes': scopes,
        'stage_packages': 0, 'solver_bounds': deepcopy(bounds), 'solver_probe': deepcopy(s2['solver_probe']),
        'sealed_reads': 0, 'method_cost': {'model_calls': 0, 'all_role_caps': 0, 'learning': 'none'},
        'maximum_schedule': manifest._plain(p.searchqa_hp_v6_identity())}
