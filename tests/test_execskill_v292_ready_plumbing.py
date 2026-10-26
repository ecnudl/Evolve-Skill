"""Child-only slow-start options and durable lifecycle evidence, offline fixtures."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import evaluation, manifest, profiles as p, smoke, step, units
from skillopt.execskill.cells import Pause
from skillopt.execskill.errors import CleanupUnconfirmed
from skillopt.execskill.sandbox import client
from tests.test_execskill_manifest import FakeDockerCLI, PING
from tests.test_execskill_v292_cleanup_plumbing import setting, EVENT as CLEANUP
from tests.test_execskill_v28_profile import tmp_path
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CONFIGS = ('zebra-pc-v9', 'alfworld-v6', 'zebra-pc-v8', 'alfworld-v5')
START = {'container': client.PREFIX + 'a' * 32, 'seconds': 30.0,
         'ready_timeout_seconds': 90, 'ready': True}


def test_ready_timeout_and_manifest_pin_only_change_the_two_children():
    for config in p.CONFIGURATIONS:
        child = config in ('zebra-pc-v9', 'alfworld-v6')
        assert p.ready_timeout_seconds(config) == (90 if child else 20)
        pins = manifest.registered(config)['thresholds']
        assert ('sandbox_ready_timeout_seconds' in pins) is child
        assert pins.get('sandbox_ready_timeout_seconds', 20) == (90 if child else 20)
    assert p.ready_timeout_seconds(None) == p.SANDBOX_READY_SECONDS == 20


@pytest.mark.parametrize('configuration', CONFIGS)
def test_manifest_factories_and_start_records_round_trip(tmp_path, monkeypatch, configuration):
    from tests.test_execskill_v29_manifest_smoke import test_complete_manifest_pins_exact_practice_ids_prompts_and_models
    test_complete_manifest_pins_exact_practice_ids_prompts_and_models(tmp_path, monkeypatch, configuration)
    value = read_json(tmp_path / 'new-manifest.json')
    monkeypatch.setattr(manifest, '_clients', lambda *args: None)
    actual = manifest.setting_of(value, 'D', docker=FakeDockerCLI())
    services = manifest.services_of(value, 'D', setting=actual)
    for options in (actual.sandbox, services.workers.keywords):
        assert options.get('ready_timeout_seconds', 20) == p.ready_timeout_seconds(configuration)
        assert ('ready_timeout_seconds' in options) is p.is_v292(configuration)
    assert 'ready_timeout_seconds' not in actual.extra['drain'].keywords
    value['environment']['sandbox'] = {'starts': [dict(START)]}
    fields = {key: item for key, item in value.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    signed = p.record('manifest-v2-9', 'engineering_fixture', fields)
    if p.is_v292(configuration):
        assert manifest.check(signed) == signed
        fields['environment']['sandbox']['cleanups'] = [dict(CLEANUP)]
        assert manifest.check(p.record('manifest-v2-9', 'engineering_fixture', fields))
    else:
        with pytest.raises(ValueError, match='environment block'):
            manifest.check(signed)


@pytest.mark.parametrize('key,value', [('seconds', -1), ('seconds', float('inf')), ('seconds', True),
                                       ('ready', 1), ('ready_timeout_seconds', 20),
                                       ('ready_timeout_seconds', True), ('container', 'not-a-container')])
def test_manifest_rejects_invalid_start_record(tmp_path, monkeypatch, key, value):
    from tests.test_execskill_v29_manifest_smoke import test_complete_manifest_pins_exact_practice_ids_prompts_and_models
    test_complete_manifest_pins_exact_practice_ids_prompts_and_models(tmp_path, monkeypatch, 'zebra-pc-v9')
    source = read_json(tmp_path / 'new-manifest.json')
    source['environment']['sandbox'] = {'starts': [{**START, key: value}]}
    fields = {key: item for key, item in source.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    with pytest.raises(ValueError, match='JSON compliant' if value == float('inf') else 'ready-ping start records'):
        manifest.check(p.record('manifest-v2-9', 'engineering_fixture', fields))


@pytest.mark.parametrize('configuration', CONFIGS)
def test_cell_service_and_drain_collectors_are_shared_only_in_children(tmp_path, monkeypatch, configuration):
    original = setting(tmp_path, configuration)
    bench, label = p.active_benches(configuration)[0], 'D/unit'
    local = units.for_unit(original, 'D', bench, label)
    drain = units.drainer(original, 'D', label)
    seen = []
    monkeypatch.setattr(units, 'Worker', lambda **options: seen.append(options))
    context = units.cell_context(local, tmp_path / 'attempt', SimpleNamespace(model=p.CHAINS['G']))
    context.worker(bench)
    if p.is_v292(configuration):
        assert seen[0]['ready_timeout_seconds'] == 90
        assert local.sandbox['start_events'] is seen[0]['start_events'] is drain.starts
        other = units.for_unit(original, 'D', bench, label + '-other')
        assert other.sandbox['start_events'] is not drain.starts
    else:
        assert 'ready_timeout_seconds' not in seen[0] and 'start_events' not in seen[0]
        assert not hasattr(drain, 'starts') and 'sandbox_start_events' not in original.extra


@pytest.mark.parametrize('configuration', CONFIGS)
def test_direct_cell_context_enforces_ready_limit(tmp_path, monkeypatch, configuration):
    seen = []
    monkeypatch.setattr(units, 'Worker', lambda **options: seen.append(options))
    context = units.cell_context(setting(tmp_path, configuration), tmp_path / 'attempt',
                                 SimpleNamespace(model=p.CHAINS['G']))
    context.worker(p.active_benches(configuration)[0])
    assert seen[0].get('ready_timeout_seconds', 20) == p.ready_timeout_seconds(configuration)


@pytest.mark.parametrize('configuration', ('zebra-pc-v9', 'alfworld-v6'))
@pytest.mark.parametrize('failure', ('none', 'work', 'drain'))
def test_unit_persists_start_records_even_after_later_failure(tmp_path, configuration, failure):
    def finish(*args, **kwargs):
        if failure == 'drain':
            raise CleanupUnconfirmed('authored lingering container')
    original = setting(tmp_path, configuration, drain=finish)
    local = units.for_unit(original, 'D', p.active_benches(configuration)[0], 'D/unit')
    drain = units.drainer(original, 'D', 'D/unit')
    local.sandbox['start_events'].append({'stale': True})
    def work(attempt):
        assert not local.sandbox['start_events']
        local.sandbox['start_events'].append(dict(START))
        if failure == 'work':
            raise RuntimeError('authored later failure')
        return {'authored': True}
    root = tmp_path / 'unit'
    options = dict(run=original.run, identity={'unit': 'D/unit'}, work=work, evidence=original.evidence,
                   drain=drain, configuration=configuration)
    if failure == 'none':
        record = units.run_unit(root, **options)
    else:
        with pytest.raises(Pause):
            units.run_unit(root, **options)
        record = read_json(root / 'attempt-1/status.json')
    assert record['sandbox'] == {'starts': [START]}
    assert read_json(root / 'attempt-1/sandbox-starts.json') == {'starts': [START]}
    assert not (root / 'attempt-1/sandbox-cleanups.json').exists()


@pytest.mark.parametrize('configuration', CONFIGS)
def test_step_services_forward_start_collector_and_parent_kwargs_stay_exact(tmp_path, monkeypatch, configuration):
    from skillopt.execskill.package import empty
    from skillopt.execskill.registry import Registry
    original = setting(tmp_path, configuration)
    bench = p.active_benches(configuration)[0]
    received = []
    @contextmanager
    def workers(package, *, kind, **options):
        received.append(options)
        if 'start_events' in options:
            options['start_events'].append(dict(START))
        yield SimpleNamespace()
    services = step.Services(registry=Registry(tmp_path / 'registry', evidence=original.evidence),
                             sources=None, workers=workers)
    parent = empty(step='D/s0', evidence=original.evidence)
    st = step._Step(original, services, 'D', bench, 1, parent, tmp_path / 'D')
    monkeypatch.setattr(st, 'verify', lambda: None)
    def work(attempt):
        with st.services.workers(parent, kind='cell'):
            pass
        return {'authored': True}
    st.unit('engineer-r3', work)
    actual = read_json(st.root / 'engineer-r3/unit.json')
    if p.is_v292(configuration):
        assert received[0]['ready_timeout_seconds'] == 90
        assert received[0]['start_events'] == actual['sandbox']['starts'] == [START]
    else:
        assert received == [{'tag': client.unit_tag('D', st.label('engineer-r3'))}]
        assert 'sandbox' not in actual


@pytest.mark.parametrize('configuration', CONFIGS)
def test_environment_probe_ready_options_and_start_records_are_child_only(monkeypatch, configuration):
    received = []
    def ping(**options):
        received.append(options)
        if 'start_events' in options:
            options['start_events'].append(dict(START))
        return dict(PING)
    monkeypatch.setattr(manifest, '_ping_empty', ping)
    value = manifest.environment(docker=FakeDockerCLI(), configuration=configuration)
    if p.is_v292(configuration):
        assert received[0]['ready_timeout_seconds'] == 90
        assert value['sandbox'] == {'starts': [START]}
    else:
        assert received == [{}] and set(value) == manifest.ENVIRONMENT_FIELDS


def test_empty_probe_forwards_worker_start_options(monkeypatch):
    received, starts = [], []
    @contextmanager
    def worker(package, *, kind, **options):
        received.append(options)
        yield SimpleNamespace(ping=lambda: dict(PING))
    monkeypatch.setattr(manifest.sandbox, 'with_worker', worker)
    manifest._ping_empty()
    manifest._ping_empty(ready_timeout_seconds=90, start_events=starts)
    assert received == [{}, {'ready_timeout_seconds': 90, 'start_events': starts}]
    assert received[1]['start_events'] is starts


def test_environment_start_sidecar_survives_a_later_failure(tmp_path, monkeypatch):
    def environment(**options):
        options['start_events'].append(dict(START))
        raise RuntimeError('authored later environment query fails')
    monkeypatch.setattr(manifest, 'environment', environment)
    with pytest.raises(RuntimeError):
        manifest._environment_for_manifest(tmp_path / 'manifest.json', 'alfworld-v6')
    assert read_json(tmp_path / 'manifest.json.sandbox-starts.json') == {'starts': [START]}


@pytest.mark.parametrize('configuration', CONFIGS)
@pytest.mark.parametrize('fail', (False, True))
def test_s0_worker_records_starts_but_escape_cleanup_receives_no_start_options(tmp_path, monkeypatch, configuration, fail):
    received = []
    def escape(docker, scratch, **options):
        received.append(('escape', options))
        assert 'ready_timeout_seconds' not in options and 'start_events' not in options
        return {}
    def worker(**options):
        received.append(('worker', options))
        def ping():
            if 'start_events' in options:
                options['start_events'].append(dict(START))
            if fail:
                raise RuntimeError('authored failure after start')
            return {'vsz_kib': 1, 'rss_kib': 2}
        result = SimpleNamespace(ping=ping, close=lambda: None)
        result.start = lambda *args, **kwargs: result
        return result
    monkeypatch.setattr(smoke, '_escape_report', escape)
    monkeypatch.setattr(smoke, 'escape_rows', lambda value: {'authored': True})
    monkeypatch.setattr(smoke, 'view_bytes', lambda paths: {'items': 1, 'p99': 3})
    out = tmp_path / 's0'
    args = dict(item_files=[], docker=FakeDockerCLI(), worker=worker, configuration=configuration)
    if fail:
        with pytest.raises(RuntimeError):
            smoke.sandbox_selftest(out, **args)
    else:
        value = smoke.sandbox_selftest(out, **args)
        assert value.get('sandbox') == ({'starts': [START]} if p.is_v292(configuration) else None)
    if p.is_v292(configuration):
        assert received[1][1]['ready_timeout_seconds'] == 90
        assert read_json(out / 'sandbox-starts.json') == {'starts': [START]}
    else:
        assert received == [('escape', {}), ('worker', {})]
        assert not (out / 'sandbox-starts.json').exists()


@pytest.mark.parametrize('fail', (False, True))
def test_read_drain_preserves_start_evidence_on_success_or_failure(tmp_path, fail):
    def drain():
        if fail:
            raise CleanupUnconfirmed('authored lingering container')
    drain.starts = [dict(START)]
    context = SimpleNamespace(attempt=tmp_path, evidence='engineering_fixture')
    if fail:
        with pytest.raises(Pause):
            evaluation._drained(drain, context, 'D/test/zebralogic', configuration='zebra-pc-v9')
    else:
        evaluation._drained(drain, context, 'D/test/zebralogic', configuration='zebra-pc-v9')
    assert read_json(tmp_path / 'sandbox-starts.json') == {'starts': [START]}


def test_evaluate_preserves_incoming_start_evidence(tmp_path, monkeypatch):
    @contextmanager
    def contained(shared):
        yield
    monkeypatch.setattr(evaluation, 'contained', contained)
    monkeypatch.setattr(evaluation, '_evaluate', lambda *args, **kwargs: {'authored': True})
    root, attempt = tmp_path / 'unit', tmp_path / 'unit/attempt-1'
    attempt.mkdir(parents=True)
    drain = lambda: None
    drain.starts = [dict(START)]
    evaluation.evaluate(root, run='a' * 64, shared=tmp_path / 'shared', pinned=None,
        chain='D', bench='zebralogic', arms={}, context=SimpleNamespace(attempt=attempt, evidence='engineering_fixture'),
        workers=1, route_workers=None, canaries=[], drain=drain, run_configuration='zebra-pc-v9')
    assert read_json(attempt / 'sandbox-starts.json') == {'starts': [START]}


def test_smoke_cell_summary_keeps_full_start_record_without_altering_older_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, 'classed_sends', lambda *args, **kwargs: [])
    found = {'cell': {'id': 'authored', 'arm': 'F', 'task_id': 'authored', 'run': 'run'}, 'judge': None,
             'faults': [], 'sends': [], 'sandbox': {'restarts': [], 'cleanups': []}}
    args = dict(stage='S2', bench='zebralogic', nominal=None, bound=1)
    old = smoke._summary_of({}, tmp_path, found, **args)
    assert 'starts' not in old
    found['sandbox']['starts'] = [{**START, 'step': 2}]
    new = smoke._summary_of({}, tmp_path, found, **args)
    assert new.pop('starts') == [{**START, 'step': 2}]
    assert new == old


def test_s2_aggregate_preserves_start_records_and_old_shape(monkeypatch):
    monkeypatch.setattr(smoke, 's2_solver', lambda *args, **kwargs: {'rows': {'authored': True}})
    monkeypatch.setattr(smoke, '_compliant', lambda *args: {})
    cell = {'entries': [], 'hooks': [], 'faults': [], 'stop': None, 'alfworld': None,
            'restarts': 0, 'cleanups': [], 'tokens': 0, 'arm': 'F'}
    results = [{'cells': [cell], 'bench': 'zebralogic', 'held_native': 0}]
    options = dict(ledger={}, leftover=[], concurrent=[], probe_entries=[], ledger_bound={})
    old = smoke._s2_judged({}, results, **options)
    assert 'starts' not in old['sandbox']
    cell['starts'] = [{**START, 'step': 2}]
    new = smoke._s2_judged({}, results, **options)
    assert new['sandbox'].pop('starts') == [{**START, 'step': 2}]
    assert new == old
