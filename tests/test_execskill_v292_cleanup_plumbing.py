"""Child-only cleanup options and durable lifecycle evidence, entirely offline."""
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import functools
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import (evaluation, manifest, profiles as p, slots, smoke, step, units)
from skillopt.execskill.cells import Pause
from skillopt.execskill.errors import CleanupUnconfirmed
from skillopt.execskill.sandbox import client
from tests.test_execskill_manifest import FakeDockerCLI, PING
from tests.test_execskill_v292_cleanup import Clock, Docker
from tests.execskill_v293_fakes import tmp_path
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


CONFIGS = ['zebra-pc-v9', 'alfworld-v6', 'zebra-pc-v8', 'alfworld-v5']
EVENT = {'container': client.PREFIX + 'a' * 32, 'seconds': 17.0,
         'extra_tries': 1, 'extra_seconds': 15.0}


def setting(tmp_path, configuration, **extra):
    return units.Setting(run='a' * 64, root=tmp_path, shared=tmp_path / 'shared', pools={}, cards={},
        runtime={}, clients=None, budget=None, slots=slots.pools(tmp_path / 'slots'), sandbox={},
        evidence='engineering_fixture', extra={'configuration': configuration,
            'slot_root': str(tmp_path / 'slots'), **extra})


def fake_clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(client.time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(client.time, 'sleep', clock.sleep)
    return clock


def closing_worker(local, docker, name):
    worker = client.Worker(docker=docker, **local.sandbox)
    worker._container = client._Container(name, ExitStack())
    worker.close()
    return worker


def test_only_two_registered_configurations_receive_cleanup_grace_and_new_pin():
    for config in p.CONFIGURATIONS:
        expected = 120 if p.is_v292(config) else 0
        assert p.cleanup_grace_seconds(config) == expected
        pin = manifest.registered(config)['thresholds']
        assert pin.get('sandbox_cleanup_grace_seconds', 0) == expected
        assert ('sandbox_cleanup_grace_seconds' in pin) == bool(expected)


@pytest.mark.parametrize('configuration', CONFIGS)
def test_full_manifest_settings_factories_and_environment_records_round_trip(tmp_path, monkeypatch, configuration):
    from copy import deepcopy
    from tests.test_execskill_v29_manifest_smoke import test_complete_manifest_pins_exact_practice_ids_prompts_and_models
    test_complete_manifest_pins_exact_practice_ids_prompts_and_models(tmp_path, monkeypatch, configuration)
    value = read_json(tmp_path / 'new-manifest.json')
    monkeypatch.setattr(manifest, '_clients', lambda *args: None)
    actual = manifest.setting_of(value, 'D', docker=FakeDockerCLI())
    assert actual.sandbox.get('cleanup_grace_seconds', 0) == p.cleanup_grace_seconds(configuration)
    assert actual.extra['drain'].keywords.get('cleanup_grace_seconds', 0) == p.cleanup_grace_seconds(configuration)
    services = manifest.services_of(value, 'D', setting=actual)
    assert services.workers.keywords.get('cleanup_grace_seconds', 0) == p.cleanup_grace_seconds(configuration)
    changed = deepcopy(value)
    changed['environment']['sandbox'] = {'cleanups': [dict(EVENT)]}
    fields = {key: item for key, item in changed.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    signed = p.record('manifest-v2-9', 'engineering_fixture', fields)
    if p.is_v292(configuration):
        assert manifest.check(signed) == signed
        fields['environment']['sandbox']['cleanups'][0]['extra_tries'] = 0
        with pytest.raises(ValueError, match='confirmed cleanup'):
            manifest.check(p.record('manifest-v2-9', 'engineering_fixture', fields))
    else:
        with pytest.raises(ValueError, match='environment block'):
            manifest.check(signed)


@pytest.mark.parametrize('configuration', CONFIGS)
def test_unit_worker_and_drainer_share_child_options_without_changing_parent_kwargs(tmp_path, configuration):
    received = []
    original = setting(tmp_path, configuration, drain=lambda *args, **kwargs: received.append((args, kwargs)))
    bench = p.active_benches(configuration)[0]
    label = 'D/s1-%s/engineer-r3' % bench
    local = units.for_unit(original, 'D', bench, label)
    drain = units.drainer(original, 'D', label)
    drain()
    assert local.sandbox['tag'] == client.unit_tag('D', label)
    if p.is_v292(configuration):
        assert local.sandbox['cleanup_grace_seconds'] == 120
        assert received[0][1]['cleanup_grace_seconds'] == 120
        assert received[0][1]['cleanups'] is local.sandbox['cleanup_events'] is drain.cleanups
        other = units.for_unit(original, 'D', bench, label + '-other')
        assert other.sandbox['cleanup_events'] is not drain.cleanups
    else:
        assert local.sandbox == {'tag': client.unit_tag('D', label)}
        assert received == [(('D', label), {})]
        assert not hasattr(drain, 'cleanups') and 'sandbox_cleanup_events' not in original.extra


@pytest.mark.parametrize('configuration', CONFIGS)
def test_cells_get_configuration_grace_even_from_authored_unregistered_settings(tmp_path, monkeypatch, configuration):
    received = []
    monkeypatch.setattr(units, 'Worker', lambda **kwargs: received.append(kwargs) or SimpleNamespace())
    context = units.cell_context(setting(tmp_path, configuration), tmp_path / 'attempt',
                                 SimpleNamespace(model=p.CHAINS['G']))
    context.worker(p.active_benches(configuration)[0])
    assert received[0].get('cleanup_grace_seconds', 0) == p.cleanup_grace_seconds(configuration)
    assert ('cleanup_grace_seconds' in received[0]) == p.is_v292(configuration)


@pytest.mark.parametrize('configuration', ['zebra-pc-v9', 'alfworld-v6'])
@pytest.mark.parametrize('failed_work', [False, True])
def test_noncell_worker_extension_is_durable_on_complete_and_paused_unit(tmp_path, monkeypatch, configuration, failed_work):
    clock = fake_clock(monkeypatch)
    bench, label = p.active_benches(configuration)[0], 'D/unit/engineer-r3'
    name = client.PREFIX + client.unit_tag('D', label) + '-' + 'a' * 32
    docker = Docker(clock, names=[name], remove_on={name: 4})
    original = setting(tmp_path, configuration, drain=functools.partial(client.drain_unit, docker=docker))
    local = units.for_unit(original, 'D', bench, label)
    drain = units.drainer(original, 'D', label)
    def work(attempt):
        worker = closing_worker(local, docker, name)
        assert worker.cleanups[0] == drain.cleanups[0]
        if failed_work:
            raise RuntimeError('authored failure after a confirmed cleanup')
        return {'authored': True}
    root = tmp_path / 'unit'
    options = dict(run=original.run, identity={'unit': label}, work=work,
                   evidence=original.evidence, drain=drain, configuration=configuration)
    if failed_work:
        with pytest.raises(Pause):
            units.run_unit(root, **options)
        record = read_json(root / 'attempt-1/status.json')
    else:
        record = units.run_unit(root, **options)
    event = record['sandbox']['cleanups'][0]
    assert event == {'container': name, 'seconds': 17.0, 'extra_tries': 1, 'extra_seconds': 15.0}
    assert read_json(root / 'attempt-1/sandbox-cleanups.json') == {'cleanups': [event]}
    assert not docker.names


def test_drain_prior_confirmation_survives_a_later_unconfirmed_container(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch)
    label = 'D/unit/engineer-r3'
    prefix = client.PREFIX + client.unit_tag('D', label) + '-'
    first, second = prefix + 'a' * 32, prefix + 'b' * 32
    docker = Docker(clock, names=[first, second], remove_on={first: 4})
    original = setting(tmp_path, 'zebra-pc-v9', drain=functools.partial(client.drain_unit, docker=docker))
    drain = units.drainer(original, 'D', label)
    with pytest.raises(Pause):
        units.run_unit(tmp_path / 'unit', run=original.run, identity={'unit': label},
            work=lambda attempt: {}, evidence=original.evidence, drain=drain, configuration='zebra-pc-v9')
    status = read_json(tmp_path / 'unit/attempt-1/status.json')
    assert status['reason'] == 'CleanupUnconfirmed'
    assert [event['container'] for event in status['sandbox']['cleanups']] == [first]
    assert read_json(tmp_path / 'unit/attempt-1/sandbox-cleanups.json')['cleanups'] == drain.cleanups
    assert docker.names == {second}


@pytest.mark.parametrize('configuration', CONFIGS)
def test_step_engineer_factory_forwards_the_same_options_and_collector_its_drain_records(
        tmp_path, monkeypatch, configuration):
    from skillopt.execskill.package import empty
    from skillopt.execskill.registry import Registry
    clock = fake_clock(monkeypatch)
    bench = p.active_benches(configuration)[0]
    label = 'D/s1-%s/engineer-r3' % bench
    name = client.PREFIX + client.unit_tag('D', label) + '-' + 'a' * 32
    docker = Docker(clock, names=[name], remove_on={name: 4 if p.is_v292(configuration) else 1})
    original = setting(tmp_path, configuration, drain=functools.partial(client.drain_unit, docker=docker))
    received = []
    @contextmanager
    def factory(package, *, kind, **options):
        received.append(options)
        worker = client.Worker(docker=docker, **options)
        worker._container = client._Container(name, ExitStack())
        try:
            yield worker
        finally:
            worker.close()
    services = step.Services(registry=Registry(tmp_path / 'registry', evidence=original.evidence),
                             sources=None, workers=factory)
    parent = empty(step='D/s0', evidence=original.evidence)
    st = step._Step(original, services, 'D', bench, 1, parent, tmp_path / 'D')
    monkeypatch.setattr(st, 'verify', lambda: None)
    def work(attempt):
        with st.services.workers(parent, kind='cell'):
            assert st.setting.sandbox['tag'] == client.unit_tag('D', label)
        return {'authored': True}
    assert st.unit('engineer-r3', work) == {'authored': True}
    actual = read_json(st.root / 'engineer-r3/unit.json')
    assert received[0]['tag'] == client.unit_tag('D', label)
    if p.is_v292(configuration):
        assert received[0]['cleanup_grace_seconds'] == 120
        assert actual['sandbox']['cleanups'] == received[0]['cleanup_events']
        assert actual['sandbox']['cleanups'][0]['container'] == name
    else:
        assert received == [{'tag': client.unit_tag('D', label)}]
        assert 'sandbox' not in actual
    assert st.setting is original and st.services is services


@pytest.mark.parametrize('configuration', CONFIGS)
def test_no_extended_confirmation_keeps_unit_record_and_files_unchanged(tmp_path, configuration):
    original = setting(tmp_path, configuration)
    drain = units.drainer(original, 'D', 'D/unit')
    record = units.run_unit(tmp_path / 'unit', run=original.run, identity={'unit': 'D/unit'},
        work=lambda attempt: {'value': 1}, evidence=original.evidence, drain=drain, configuration=configuration)
    assert set(record) == {'version', 'evidence', p.RECORD_HASH, 'run', 'identity', 'status', 'attempt', 'result'}
    assert not (tmp_path / 'unit/attempt-1/sandbox-cleanups.json').exists()


@pytest.mark.parametrize('configuration', CONFIGS)
def test_manifest_probe_options_and_extension_record_are_child_only(monkeypatch, configuration):
    seen = []
    def probe(**kwargs):
        seen.append(kwargs)
        if kwargs:
            kwargs['cleanup_events'].append(dict(EVENT))
        return dict(PING)
    monkeypatch.setattr(manifest, '_ping_empty', probe)
    result = manifest.environment(docker=FakeDockerCLI(), configuration=configuration)
    if p.is_v292(configuration):
        assert seen[0]['cleanup_grace_seconds'] == 120
        assert result['sandbox'] == {'cleanups': [EVENT]}
    else:
        assert seen == [{}] and set(result) == manifest.ENVIRONMENT_FIELDS


def test_manifest_probe_confirmation_survives_later_probe_failure(tmp_path, monkeypatch):
    def probe(**kwargs):
        kwargs['cleanup_events'].append(dict(EVENT))
        raise CleanupUnconfirmed('authored next start cleanup failure')
    monkeypatch.setattr(manifest, 'environment', probe)
    path = tmp_path / 'manifest.json'
    with pytest.raises(CleanupUnconfirmed):
        manifest._environment_for_manifest(path, 'zebra-pc-v9')
    assert read_json(tmp_path / 'manifest.json.sandbox-cleanups.json') == {'cleanups': [EVENT]}


@pytest.mark.parametrize('configuration', CONFIGS)
def test_selftest_worker_escape_and_telemetry_are_child_only(tmp_path, monkeypatch, configuration):
    calls = []
    def escape(docker, scratch, **kwargs):
        calls.append(('escape', kwargs))
        if kwargs:
            kwargs['cleanup_events'].append(dict(EVENT))
        return {}
    def factory(**kwargs):
        calls.append(('worker', kwargs))
        worker = SimpleNamespace(ping=lambda: {'vsz_kib': 1, 'rss_kib': 2}, close=lambda: None)
        worker.start = lambda *args, **kwargs: worker
        return worker
    monkeypatch.setattr(smoke, '_escape_report', escape)
    monkeypatch.setattr(smoke, 'escape_rows', lambda report: {'authored': True})
    monkeypatch.setattr(smoke, 'view_bytes', lambda paths: {'items': 1, 'p99': 3})
    out = tmp_path / 'selftest'
    result = smoke.sandbox_selftest(out, item_files=[], docker=FakeDockerCLI(), worker=factory,
                                   configuration=configuration)
    if p.is_v292(configuration):
        assert all(kwargs['cleanup_grace_seconds'] == 120 for name, kwargs in calls)
        assert calls[0][1]['cleanup_events'] is calls[1][1]['cleanup_events']
        assert result['sandbox'] == read_json(out / 'sandbox-cleanups.json') == {'cleanups': [EVENT]}
    else:
        assert calls == [('escape', {}), ('worker', {})]
        assert 'sandbox' not in result and not (out / 'sandbox-cleanups.json').exists()


def test_selftest_keeps_escape_confirmation_when_a_later_probe_fails(tmp_path, monkeypatch):
    def escape(docker, scratch, **options):
        options['cleanup_events'].append(dict(EVENT))
        raise CleanupUnconfirmed('authored next probe cleanup failure')
    monkeypatch.setattr(smoke, '_escape_report', escape)
    out = tmp_path / 'selftest'
    with pytest.raises(CleanupUnconfirmed):
        smoke.sandbox_selftest(out, item_files=[], docker=FakeDockerCLI(), configuration='alfworld-v6')
    assert read_json(out / 'sandbox-cleanups.json') == {'cleanups': [EVENT]}


@pytest.mark.parametrize('fail_drain', [False, True])
def test_read_unit_drains_persist_prior_worker_events_on_success_or_failure(tmp_path, fail_drain):
    context = SimpleNamespace(attempt=tmp_path, evidence='engineering_fixture')
    def drain():
        if fail_drain:
            raise CleanupUnconfirmed('authored lingering exact name')
    drain.cleanups = [dict(EVENT)]
    if fail_drain:
        with pytest.raises(Pause):
            evaluation._drained(drain, context, 'D/test/zebralogic', configuration='zebra-pc-v9')
    else:
        evaluation._drained(drain, context, 'D/test/zebralogic', configuration='zebra-pc-v9')
    assert read_json(tmp_path / 'sandbox-cleanups.json') == {'cleanups': [EVENT]}


def test_evaluate_preserves_incoming_worker_confirmation_from_planning(tmp_path, monkeypatch):
    @contextmanager
    def contained(shared):
        yield
    monkeypatch.setattr(evaluation, 'contained', contained)
    monkeypatch.setattr(evaluation, '_evaluate', lambda *args, **kwargs: {'authored': True})
    root = tmp_path / 'unit'
    attempt = root / 'attempt-1'
    attempt.mkdir(parents=True)
    drain = lambda: None
    drain.cleanups = [dict(EVENT)]
    result = evaluation.evaluate(root, run='a' * 64, shared=tmp_path / 'shared', pinned=None,
        chain='D', bench='zebralogic', arms={}, context=SimpleNamespace(attempt=attempt, evidence='engineering_fixture'),
        workers=1, route_workers=None, canaries=[], drain=drain, run_configuration='zebra-pc-v9')
    assert result == {'authored': True}
    assert read_json(attempt / 'sandbox-cleanups.json') == {'cleanups': [EVENT]}
