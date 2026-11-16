"""SearchQA-only preparation and measured smoke on authored pools and scripted calls."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
import hashlib

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, manifest, profiles as p, rounds, smoke, units
from skillopt.execskill import v214_smoke as v, v214_stages as stages, v219_read, v220_import, v220_smoke as child
from skillopt.execskill.sandbox import client as sandbox
from skillopt.validator_pilot.api import digest
from tests.execskill_v220_fakes import main_v6_root, pinned_source
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.fixtures.execskill.items import searchqa_items
from tests.test_execskill_manifest import fake_environment
from tests.test_execskill_v211_manifest import reseal
from tests.test_execskill_v217i_smoke import first_call
from tests.test_execskill_v214_smoke import measured_probe
from tests.test_execskill_v220_read import consent, fixed_worker
from pathlib import Path as _CapturePath
import pytest as _capture_pytest
_PARENT_CAPTURES = [_CapturePath(__file__).parent / f'fixtures/execskill/v{v}_parents_before.json'
                    for v in ('220', '221', '222', '225', '226')]
needs_parent_captures = _capture_pytest.mark.skipif(
    not all(capture.exists() for capture in _PARENT_CAPTURES),
    reason='parent captures not published (they hold ALFWorld game text)')

CHILD = p.SEARCHQA_HP_V6


def authored_preparation(root):
    items = searchqa_items(20)
    for row in items:
        row['part'] = 'train'
    pool = root / 'practice.json'
    write_json(pool, items)
    pool_pin = {'path': str(pool), 'sha256': hashlib.sha256(pool.read_bytes()).hexdigest()}
    protected = {'id_hashes': ['a' * 64]}
    paths = {'split': str(root / 'unopened-split.json'),
        **{group: {'searchqa': str(root / ('unopened-' + group + '.json'))}
           for group in ('test', 'train', 'val')},
        'layouts': {'officeqa': str(root / 'unopened-office-layout.json')},
        'upstream': {'officeqa': str(root / 'unopened-office-upstream')}}
    pins = {path: 'b' * 64 for group in paths.values()
            for path in (group.values() if isinstance(group, dict) else [group])}
    source = p.record('manifest', p.REAL_RUN_EVIDENCE[p.MAIN_V6], {
        'configuration': p.MAIN_V6, 'root': str(root / 'main-v6'),
        'cards': {'searchqa': v219_read.cards()['searchqa']},
        'contracts': {'searchqa': {'text': 'authored contract', 'sha': hashlib.sha256(b'authored contract').hexdigest()}},
        'runtime': {'searchqa': {}},
        'data': {'pinned': {'paths': paths, 'sha256': pins}, 'pools': {'searchqa': pool_pin},
            'protected_ids': {'searchqa': protected}, 'allocations': {'searchqa': {
                'source_pins': {'pool': pool_pin, 'protected_ids': protected},
                'slices': {'smoke': [row['task_id'] for row in items]}}}}})
    path = root / 'parent-manifest.json'
    write_json(path, source)
    main_v6_root(root / 'main-v6', run=source[p.RECORD_HASH])
    return path, source


def setup(root, monkeypatch, chain='G'):
    path, source = authored_preparation(root / 'inputs')
    owner = root / 'owner.json'
    write_json(owner, consent())
    selftest = root / 'sandbox.json'
    write_json(selftest, p.record('sandbox-selftest', 'smoke', {'passed': True,
        'measured': {'vsz_kib': 10000, 'rss_kib': 5000, 'view_bytes_p99': 1000, 'native_peak_rss_kib': None},
        'limits': {key: asdict(value) for key, value in sandbox.LIMITS.items()}}))
    s0 = v.collect_s0(root / 's0', preparation_file=path, root=root / 'real', selftest=selftest,
        main_v6_root=source['root'], checks={'passed': True, 'evidence': 'authored_zero_call_fixture'},
        consent_file=owner, configuration=CHILD)
    provenance = root / 'provenance.json'
    write_json(provenance, {'build_tree': str(manifest.REPO), 'git_head': 'a' * 40,
        'snapshot_root': str(manifest.REPO), 'sha256_list_sha256': s0['snapshot_sha256'], 'env_files_absent': True})
    options = {'root': root / ('smoke-' + chain), 's0_file': root / 's0' / v.S0_FILE,
        'provenance': provenance, 'roles_repo': str(root / 'unopened-roles'),
        'route_b_env': str(root / 'unopened-route'), 'smoke_chain': chain,
        'environment_found': fake_environment(), 'configuration': CHILD}
    made = v.make_manifest(root / 'manifest.json', **options)
    return s0, made, options


@pytest.mark.parametrize('chain', ['G', 'D'])
@needs_parent_captures
def test_preparation_and_manifest_pin_searchqa_only_and_both_completed_sources(tmp_path, monkeypatch, chain):
    checked, made, options = setup(tmp_path, monkeypatch, chain)
    assert checked['configuration'] == made['configuration'] == CHILD
    assert checked['consent'] == consent() == read_json(options['root'] / 'shared/consent.json')
    assert set(made['cards']) == set(made['runtime']) == set(made['data']['pools']) == {'searchqa'}
    assert made['sheet_qualification'] is None and made['sandbox']['measured']['native_peak_rss_kib'] is None
    assert set(made['data'][v220_import.PIN_KEY]['main_v6']) == {'G', 'D'}
    assert made['data'][v220_import.PIN_KEY] == checked[v220_import.PIN_KEY]
    assert made['data']['smoke_schedule']['S2_authored_probes']['items_per_chain'] == 3
    assert manifest.check(made) == made
    assert not {'alfworld_v11_import', 'confirm', 'launch_sheet_runtime'} & set(made['data'])


def test_preparation_opens_only_manifest_and_searchqa_practice_pool(tmp_path, monkeypatch):
    path, source = authored_preparation(tmp_path)
    allowed = {path, Path(source['data']['pools']['searchqa']['path'])}
    original_bytes, original_text = Path.read_bytes, Path.read_text
    reads = []
    def checked_bytes(path, *args, **kwargs):
        assert path in allowed
        reads.append(path)
        return original_bytes(path, *args, **kwargs)
    def checked_text(path, *args, **kwargs):
        assert path in allowed
        reads.append(path)
        return original_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_bytes', checked_bytes)
    monkeypatch.setattr(Path, 'read_text', checked_text)
    found = child.preparation(path)
    assert child.verify_preparation(found) == found
    assert set(reads) == allowed
    assert found['data']['pinned']['paths']['test'] == source['data']['pinned']['paths']['test']
    assert set(found['data']['pinned']['paths']) == {'split', 'test', 'train', 'val'}


@pytest.mark.parametrize('damage', ['root', 'run'])
def test_source_completion_and_preparation_manifest_cannot_be_detached(tmp_path, damage):
    path, source = authored_preparation(tmp_path)
    imported = child.preparation(path)
    pins = v220_import.pins(source['root'])
    if damage == 'root': pins['main_v6_root'] += '-different'
    else: pins['main_v6']['D']['chain_complete']['record']['identity']['run'] = 'f' * 64
    with pytest.raises(ValueError, match='preparation manifest and root'):
        child.check_source_binding(imported, pins)


@pytest.mark.parametrize('damage', ['configuration', 'pool_alias', 'pool_pin', 'smoke_ids', 'contract', 'protected'])
def test_preparation_refuses_wrong_or_mismatched_metadata(tmp_path, damage):
    path, source = authored_preparation(tmp_path)
    if damage == 'configuration': source['configuration'] = p.MAIN_V5
    elif damage == 'pool_alias':
        source['data']['pools']['searchqa']['path'] = source['data']['pinned']['paths']['test']['searchqa']
    elif damage == 'pool_pin': source['data']['pools']['searchqa']['sha256'] = 'f' * 64
    elif damage == 'smoke_ids': source['data']['allocations']['searchqa']['slices']['smoke'] = ['missing'] * 20
    elif damage == 'contract': source['contracts']['searchqa']['text'] += 'changed'
    else: source['data']['protected_ids']['searchqa']['id_hashes'] = []
    changed = tmp_path / 'changed-parent.json'
    write_json(changed, reseal(source))
    with pytest.raises(ValueError): child.preparation(changed)


@pytest.mark.parametrize('mutation', [{'by': 'agent'}, {'sheet_test_qualification': True},
    {'multi_arm_arms': ['F', 'C', 'B']}, {'test_evaluation': False}, {'note': ''}])
def test_preparation_consent_refuses_wrong_shape_before_write(tmp_path, mutation):
    owner = tmp_path / 'owner.json'
    write_json(owner, {**consent(), **mutation})
    with pytest.raises(ValueError, match='consent'):
        v.prepare_consent(tmp_path / 'root', CHILD, consent_file=owner)
    assert not (tmp_path / 'root/shared/consent.json').exists()


def test_selftest_uses_only_searchqa_worker_and_no_native_or_zebra(tmp_path, monkeypatch):
    path, _ = authored_preparation(tmp_path / 'inputs')
    calls = []
    def worker(out, *, item_files, configuration):
        assert configuration == CHILD and len(item_files) == 1
        calls.append(item_files)
        return p.record('sandbox-selftest', 'smoke', {'passed': True,
            'measured': {'vsz_kib': 100, 'rss_kib': 80, 'view_bytes_p99': 20, 'views': 20, 'start_seconds': 0.1},
            'limits': {key: asdict(value) for key, value in sandbox.LIMITS.items()}})
    monkeypatch.setattr(smoke, 'sandbox_selftest', worker)
    from skillopt.execskill import s0, v218_lock
    monkeypatch.setattr(s0, 'native_peak', lambda *a: pytest.fail('No native sheet peak'))
    monkeypatch.setattr(v218_lock, 'preparation', lambda *a: pytest.fail('No environment lock'))
    found = v.selftest(tmp_path / 'measure', preparation_file=path, configuration=CHILD)
    assert len(calls) == 1 and found['passed']
    assert found['measured']['native_peak_rss_kib'] is None
    assert found['measurement_sources']['zebra_worker'] is None


@pytest.mark.parametrize('action', ['snapshot', 'selftest', 's0', 'manifest', 'structural-smoke', 'smoke-run', 'smoke-summary'])
def test_cli_child_choice_preserves_older_default(action):
    from scripts.run_execskill import parser
    commands = parser()._subparsers._group_actions[0].choices
    option = next(row for row in commands['v214-' + action]._actions if row.dest == 'configuration')
    assert CHILD in option.choices and option.default == p.MAIN_V5


@pytest.mark.parametrize('action', ['selftest', 's0', 'manifest'])
def test_cli_environment_flags_optional_only_for_searchqa_child(action):
    from scripts.run_execskill import parser
    flags = ['v214-' + action, '--out', '/tmp/v220-out']
    if action in ('selftest', 's0'): flags += ['--preparation', '/tmp/v220-parent']
    if action == 's0': flags += ['--root', '/tmp/v220-run', '--selftest', '/tmp/v220-sandbox']
    if action == 'manifest':
        flags += [entry for key in ('root', 's0', 'provenance', 'roles-repo', 'route-b-env')
                  for entry in ('--' + key, '/tmp/v220-' + key)]
    command = parser()
    found = command.parse_args(flags + ['--configuration', CHILD])
    assert found.configuration == CHILD and getattr(found, 'sheet_runtime', None) is None
    for older in (p.MAIN_V5, p.IMPLANT_V5, p.MAIN_V6, p.CROSS_V5):
        with pytest.raises(SystemExit): command.parse_args(flags + ['--configuration', older])


def practice_result(tmp_path, monkeypatch, chain):
    from contextlib import contextmanager
    from skillopt.coevo5.calls import Endpoint, Slots
    from skillopt.coevo5.budget import Budget
    from skillopt.execskill import cells
    from tests.execskill_fakes_env import receipt
    source = pinned_source(tmp_path / 'source')
    final = v220_import.final_package(chain, 'engineering_fixture', source)
    class Solver:
        calls = 0
        def call(self, system, user):
            self.calls += 1
            return {**receipt('<answer>authored probe only</answer>'), 'attempts': [{'status': 200}], 'error_type': None}
    fake = Solver()
    budget = Budget(tmp_path / 'ledger')
    budget.declare({'overall': 1000000})
    endpoint = Endpoint(fake, model=p.CHAINS['D'], max_tokens=100,
        slots=Slots(tmp_path / 'slots', 'authored', 2), budget=budget, scopes=('overall',), sleep=lambda _: None)
    attempt = tmp_path / 'attempt'
    context = cells.Context(attempt=attempt, endpoint=endpoint, runtime={'searchqa': {}},
        cards={'searchqa': v219_read.cards()['searchqa']}, native=None, episodes=None,
        worker=lambda _: fixed_worker(final), evidence='engineering_fixture', configuration=CHILD)
    context.searchqa_import = source
    context.environment = lambda *a: pytest.fail('SearchQA never takes the environment lock')
    @contextmanager
    def workers(setting, package, item, **options):
        worker = fixed_worker(final).start(package, kind='cell', **options)
        try: yield worker
        finally: worker.close()
    monkeypatch.setattr(units, 'cell_context', lambda *a: context)
    monkeypatch.setattr(rounds, 'cell_context', lambda *a: context)
    monkeypatch.setattr(child.evaluation, '_route_worker', workers)
    @dataclass
    class Setting:
        extra: dict
        evidence: str = 'engineering_fixture'
        workers: int = 2
    setting = Setting(extra={'configuration': CHILD, v220_import.PIN_KEY: source})
    tasks = {rounds.key('searchqa', row['task_id']): {'public': row['public'], 'private': row['private']}
             for row in searchqa_items(20)}
    result = child.practice(setting, attempt, endpoint, chain + '/v214-smoke/S2/searchqa', tasks, chain)
    return result, fake


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_s2_executes_immutable_candidates_and_persists_firing_and_reuse(tmp_path, monkeypatch, chain):
    result, fake = practice_result(tmp_path, monkeypatch, chain)
    assert result['passed'], (result['searchqa_fired'], result['request_reuse'], result['probe_coverage'])
    assert result['cells'] == 26 and result['dispatched_cells'] == fake.calls == 25
    assert result['inherited_C_cells'] == 20 and result['authored_probe_cells'] == 6
    assert result['request_reuse']['shared_cells'] == 1
    assert all(row['fired_items'] > 0 for row in result['searchqa_fired']['per_procedure'].values())
    assert child.measured_prices(result, chain)['procedure_assumed'] is False
    assert not result['benchmark_effect_evidence']


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_se6_prices_one_read_and_full_retry_and_has_no_method_work(tmp_path, monkeypatch, chain):
    row, _ = practice_result(tmp_path, monkeypatch, chain)
    probe = measured_probe(300) if chain == 'D' else None
    if probe:
        probe.update(bench='searchqa', max_tokens=p.solver_tokens(p.CHAINS['D'], 'searchqa'),
                     ledger_bound=p.ledger_bound(p.CHAINS['D'], 'searchqa', branch='N', longest=300))
    probe = child.solver_probe(first_call(chain), chain, probe)
    bounds = v.solver_bounds(chain, probe, configuration=CHILD)
    s2 = {'passed': True, 'benches': {'searchqa': row}, 'solver_probe': probe}
    result = stages.projection(s2, chain, bounds=bounds, configuration=CHILD)
    assert result['passed'] and result['stage_packages'] == 0
    assert result['solver_scopes'][chain + ':test']['projected'] == 2 * result['read_estimate'] + result['read_reservation']
    assert result['method_cost'] == {'model_calls': 0, 'all_role_caps': 0, 'learning': 'none'}
    assert v.stages_of(CHILD) == ('S0', 'S1', 'S2', 'SE6')
    assert v.schedule(CHILD)['benchmarks'] == ['searchqa']


@pytest.mark.parametrize('damage', ['missing_probe', 'missing_emission', 'source_request', 'cost_count'])
def test_se6_refuses_incomplete_or_misattributed_mechanism_coverage(tmp_path, monkeypatch, damage):
    row, _ = practice_result(tmp_path, monkeypatch, 'G')
    key = next(key for key in row['probe_coverage'] if key.endswith('silent'))
    if damage == 'missing_probe': del row['probe_coverage'][key]
    elif damage == 'missing_emission':
        for entry in row['probe_coverage'].values(): entry['F']['searchqa_fired']['emitted_note_ids'] = []
    elif damage == 'source_request': row['probe_coverage'][key]['C']['request_sha256'] = ['f' * 64]
    else: row['measurements']['per_arm']['searchqa']['C']['cells'] -= 1
    with pytest.raises(ValueError, match='SearchQA|Both SearchQA'):
        child.measured_prices(row, 'G')


def test_structural_smoke_imports_both_steps_without_clients(tmp_path, monkeypatch):
    source = pinned_source(tmp_path / 'source')
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: {
        'configuration': CHILD, p.RECORD_HASH: 'a' * 64, 'data': {v220_import.PIN_KEY: source}})
    monkeypatch.setattr(manifest, 'verify_code', lambda *_: None)
    monkeypatch.setattr(stages, 'sx', lambda *a, **kw: pytest.fail('No SX'))
    result = v.structural_smoke(tmp_path / 'unread', out=tmp_path / 'structural.json', configuration=CHILD)
    assert result['passed'] and not result['measured_readiness']
    assert result['model_calls'] == result['sealed_reads'] == 0


def measured_receipts(tmp_path, monkeypatch, chain, made):
    row, _ = practice_result(tmp_path, monkeypatch, chain)
    probe = measured_probe(300) if chain == 'D' else None
    if probe:
        probe.update(bench='searchqa', max_tokens=p.solver_tokens(p.CHAINS['D'], 'searchqa'),
                     ledger_bound=p.ledger_bound(p.CHAINS['D'], 'searchqa', branch='N', longest=300))
    probe = child.solver_probe(first_call(chain, made[p.RECORD_HASH]), chain, probe)
    bounds = v.solver_bounds(chain, probe, configuration=CHILD)
    s2 = {'passed': True, 'benches': {'searchqa': row}, 'solver_probe': probe, 'solver_bounds': bounds}
    outputs = {'S0': {'passed': True, 'model_calls': 0, 'sealed_reads': 0},
        'S1': {'passed': True, 'solver_probe': probe, 'solver_bounds': bounds,
               'solver_confirmation': probe['first_call'][p.RECORD_HASH], 'sealed_reads': 0},
        'S2': s2, 'SE6': child.projection(s2, chain, bounds=bounds)}
    records = {name: p.record('v214-smoke-stage', 'smoke', {'configuration': CHILD,
        'chain': chain, 'stage': name, 'manifest_sha256': made[p.RECORD_HASH], 'measured': True,
        'schedule_sha256': digest(v.schedule(CHILD)), 'snapshot_sha256': made['data']['snapshot_sha256'],
        's0_sha256': made['data']['s0_sha256'], 'result': output}) for name, output in outputs.items()}
    return p.record('v214-smoke-result', 'smoke', {'configuration': CHILD, 'chain': chain,
        'manifest_sha256': made[p.RECORD_HASH], 'snapshot_sha256': made['data']['snapshot_sha256'],
        's0_sha256': made['data']['s0_sha256'], 'schedule_sha256': digest(v.schedule(CHILD)),
        'stages': {name: row[p.RECORD_HASH] for name, row in records.items()}, 'stage_records': records,
        'passed': True, 'sealed_reads': 0})


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_measured_readiness_recomputes_searchqa_projection_and_probes(tmp_path, monkeypatch, chain):
    made = {p.RECORD_HASH: 'a' * 64, 'data': {'snapshot_sha256': 'b' * 64, 's0_sha256': 'c' * 64}}
    found = measured_receipts(tmp_path, monkeypatch, chain, made)
    checked, projected = v.checked_readiness(found, chain=chain, source_sha256='b' * 64,
        s0_sha256='c' * 64, configuration=CHILD)
    assert checked == found and projected['passed']
    changed = deepcopy(found)
    changed['stage_records']['S2']['result']['solver_bounds']['ledger_bound']['searchqa'] += 1
    changed['stage_records']['S2'] = reseal(changed['stage_records']['S2'])
    changed['stages']['S2'] = changed['stage_records']['S2'][p.RECORD_HASH]
    with pytest.raises(ValueError, match='same confirmed probe'):
        v.checked_readiness(reseal(changed), chain=chain, source_sha256='b' * 64,
                            s0_sha256='c' * 64, configuration=CHILD)


@needs_parent_captures
def test_real_manifest_requires_both_measured_chains_and_never_reopens_source_root(tmp_path, monkeypatch):
    _, made, options = setup(tmp_path / 'setup', monkeypatch)
    options.update(smoke_chain=None, root=tmp_path / 'real')
    monkeypatch.setitem(p.RUN_ROOTS, CHILD, str(options['root']))
    with pytest.raises(ValueError, match='both measured'):
        v.make_manifest(tmp_path / 'refused.json', **options)
    paths = []
    for chain in p.CHAINS:
        receipt = measured_receipts(tmp_path / ('practice-' + chain), monkeypatch, chain, made)
        target = tmp_path / 'measured' / chain
        for name, row in receipt['stage_records'].items(): write_json(target / (name + '.json'), row)
        path = target / v.RESULT
        write_json(path, receipt)
        paths.append(path)
    monkeypatch.setattr(v220_import, 'pins', lambda *a, **kw: pytest.fail('Only pinned source copies after S0'))
    value = v.make_manifest(tmp_path / 'real-manifest.json', measured_smoke=paths, **options)
    assert value['evidence'] == p.REAL_RUN_EVIDENCE[CHILD] and manifest.check(value) == value


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_s1_uses_only_searchqa_first_reply_and_searchqa_length_probe(monkeypatch, chain):
    from skillopt.execskill import chain as chains, v29_route_probe
    seen = []
    monkeypatch.setattr(chains, 'first_call', lambda setting, selected: first_call(selected))
    def measure(setting, *, bench):
        seen.append(bench)
        value = measured_probe(300)
        value.update(bench=bench, max_tokens=p.solver_tokens(p.CHAINS['D'], bench),
                     ledger_bound=p.ledger_bound(p.CHAINS['D'], bench, branch='N', longest=300))
        return value
    monkeypatch.setattr(v29_route_probe, 'measure', measure)
    result = stages.s1(SimpleNamespace(extra={'configuration': CHILD}), chain)
    assert result['passed'] and set(result['solver_bounds']['ledger_bound']) == {'searchqa'}
    assert seen == (['searchqa'] if chain == 'D' else [])
