"""Child ready-ping grace and start latency with fake Docker, containers and time."""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import policy
from skillopt.execskill.errors import CleanupUnconfirmed, ConfigurationError, SandboxUnavailable
from skillopt.execskill.sandbox import client
from tests.test_execskill_v292_cleanup import Clock


PACKAGE = SimpleNamespace(sha256='a' * 64, procedures=[SimpleNamespace(
    id='p', source='def before_call(view, state):\n    return {}\n', hooks=['before_call'])])


class Docker:
    binary = 'authored-ready-docker'

    def __init__(self, clock, delays=(30,), *, spawn_seconds=0, load_seconds=0, ping_seconds=0,
                 bad_identity=False, fail_cleanup=False, fail_spawn=False, lost_call=False):
        self.clock, self.delays = clock, delays
        self.spawn_seconds, self.load_seconds, self.ping_seconds = spawn_seconds, load_seconds, ping_seconds
        self.bad_identity, self.fail_cleanup = bad_identity, fail_cleanup
        self.fail_spawn, self.lost_call = fail_spawn, lost_call
        self.names, self.requests, self.commands = [], [], []

    def spawn(self, argv):
        name = argv[argv.index('--name') + 1]
        index = len(self.names)
        self.names.append(name)
        created = self.clock.now
        self.clock.now += self.spawn_seconds
        if self.fail_spawn:
            raise OSError('authored spawn failure')
        return SimpleNamespace(name=name, created=created, first_ping=True,
            ready_at=created + self.delays[min(index, len(self.delays) - 1)],
            stdin=SimpleNamespace(close=lambda: None), stdout=SimpleNamespace(close=lambda: None),
            wait=lambda **kwargs: 0)

    def run(self, argv, timeout):
        self.commands.append((argv, timeout))
        if argv[1] == 'inspect':
            return client.Completed(1, b'')  # a lost call's container vanished
        if argv[1] == 'ps' and self.fail_cleanup:
            return client.Completed(0, ('\n'.join(self.names) + '\n').encode())
        return client.Completed(0, b'')

    def send(self, container, data, deadline):
        if container.process is None:
            raise client._Lost('docker did not start')
        container.request = json.loads(data[client.HEADER.size:])
        self.requests.append((container.name, container.request['op'], deadline - self.clock.now))

    def receive(self, container, deadline, cap):
        process, request = container.process, container.request
        op = request['op']
        at = self.clock.now
        if op == 'ping' and process.first_ping:
            process.first_ping = False
            at = max(at, process.ready_at)
        elif op == 'ping':
            at += self.ping_seconds
        elif op == 'load':
            at += self.load_seconds
        elif op == 'call' and self.lost_call:
            self.lost_call = False
            raise client._Lost('authored vanished worker')
        if at > deadline:
            self.clock.now = deadline
            raise client._Lost('no reply in time')
        self.clock.now = at
        reply = {'ok': True, 'seq': request['seq']}
        if op == 'ping':
            reply.update(worker='wrong' if self.bad_identity else client.WORKER_PROTOCOL,
                         worker_sha256=client.worker_sha256(), hashseed='0', policy_sha256=policy.policy_sha256())
        elif op == 'load':
            reply.update(package_sha256=request['package_sha256'], loaded=['p'], rejected=[])
        else:
            reply.update(op='call', proc=request['proc'], fn=request['fn'], args_sha256=client.sha256(request['args']),
                         value={}, value_sha256=client.sha256({}), cpu_ms=1, rss_kib=1)
        return reply


@pytest.fixture
def factory(monkeypatch, tmp_path):
    clock = Clock()
    monkeypatch.setattr(client.time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(client.time, 'sleep', clock.sleep)
    def make(*, docker_options=None, **worker_options):
        docker = Docker(clock, **(docker_options or {}))
        monkeypatch.setattr(client._Container, 'send', lambda container, data, deadline: docker.send(container, data, deadline))
        monkeypatch.setattr(client._Container, 'receive', lambda container, deadline, cap: docker.receive(container, deadline, cap))
        worker = client.Worker(docker=docker, scratch=tmp_path, **worker_options).start(PACKAGE, kind='cell')
        monkeypatch.setattr(worker, '_runner_dir', lambda: tmp_path)
        return worker, docker, clock
    return make


@pytest.mark.parametrize('explicit', [False, True])
def test_thirty_second_start_fails_default_twenty_and_keeps_historical_records(factory, explicit):
    worker, docker, clock = factory(**({'ready_timeout_seconds': 20} if explicit else {}))
    with pytest.raises(SandboxUnavailable, match='sandbox_start_failed: no reply in time'):
        worker._ensure()
    assert clock.now == 40
    assert [row[1:] for row in docker.requests] == [('ping', 20), ('ping', 20)]
    assert len(worker.names) == 2 and len(worker.restarts) == 1 and len(worker.cleanups) == 2
    assert worker.starts == [] and worker.ready_timeout_seconds == 20
    assert all(set(row) == {'container', 'seconds'} for row in worker.cleanups)
    assert all(set(row) == {'cause', 'container', 'procedure'} for row in worker.restarts)
    worker.close()


def test_thirty_second_start_succeeds_with_ninety_and_only_first_ping_changes(factory):
    events = []
    worker, docker, clock = factory(ready_timeout_seconds=90, start_events=events)
    worker.ping()
    assert [row[1:] for row in docker.requests] == [('ping', 90), ('load', 20), ('ping', 20)]
    assert worker.starts == events == [{'container': docker.names[0], 'seconds': 30,
                                        'ready_timeout_seconds': 90, 'ready': True}]
    worker.call('p', 'before_call', [{}, None], timeout_s=2)
    assert docker.requests[-1][1:] == ('call', 12)
    assert len(worker.starts) == 1 and worker.restarts == []
    worker.close()


def test_existing_start_retry_uses_ninety_and_records_both_attempts_before_cleanup(factory):
    events = []
    worker, docker, clock = factory(ready_timeout_seconds=90, start_events=events,
                                    docker_options={'delays': (100, 30)})
    worker._ensure()
    assert [row[1:] for row in docker.requests] == [('ping', 90), ('ping', 90), ('load', 20)]
    assert [row['seconds'] for row in events] == [90, 30]
    assert [row['ready'] for row in events] == [False, True]
    assert [row['container'] for row in events] == docker.names
    assert len(worker.restarts) == len(worker.cleanups) == 1 and clock.now == 120
    worker.close()


def test_second_failed_start_keeps_two_failed_latency_records(factory):
    events = []
    worker, docker, clock = factory(ready_timeout_seconds=90, start_events=events,
                                    docker_options={'delays': (100,)})
    with pytest.raises(SandboxUnavailable):
        worker._ensure()
    assert clock.now == 180 and len(events) == 2
    assert all(row['ready'] is False and row['seconds'] == 90 for row in events)
    assert len(worker.restarts) == 1 and len(worker.cleanups) == 2


def test_explicit_sink_can_observe_twenty_without_changing_timeout(factory):
    events = []
    worker, docker, clock = factory(start_events=events)
    with pytest.raises(SandboxUnavailable):
        worker._ensure()
    assert [row['seconds'] for row in events] == [20, 20]
    assert all(row['ready_timeout_seconds'] == 20 and row['ready'] is False for row in events)


def test_start_latency_includes_spawn_but_excludes_slot_wait_load_later_ping_and_cleanup(factory):
    events, slots = [], []
    holder = {}
    @contextmanager
    def hold():
        holder['clock'].now += 12
        slots.append('held')
        yield
        slots.append('released')
    worker, docker, clock = factory(ready_timeout_seconds=90, start_events=events,
        live=SimpleNamespace(hold=hold), docker_options={'spawn_seconds': 7, 'load_seconds': 8, 'ping_seconds': 4})
    holder['clock'] = clock
    worker.ping()
    assert clock.now == 54  # 12 slot +30 create-to-ready +8 load +4 later ping
    assert events[0]['seconds'] == 30 and slots == ['held']
    worker.close()
    assert events[0]['seconds'] == 30 and slots == ['held', 'released']


def test_bad_ready_identity_records_failed_response_without_retry(factory):
    worker, docker, clock = factory(ready_timeout_seconds=90, docker_options={'bad_identity': True})
    with pytest.raises(ConfigurationError, match='identity mismatch'):
        worker._ensure()
    assert len(worker.starts) == 1 and worker.starts[0]['ready'] is False
    assert worker.starts[0]['seconds'] == 30 and len(worker.cleanups) == 1 and worker.restarts == []


def test_load_timeout_stays_twenty_and_does_not_extend_recorded_ready_latency(factory):
    worker, docker, clock = factory(ready_timeout_seconds=90, docker_options={'load_seconds': 30})
    with pytest.raises(SandboxUnavailable):
        worker._ensure()
    assert [row[1:] for row in docker.requests] == [('ping', 90), ('load', 20)] * 2
    assert [row['seconds'] for row in worker.starts] == [30, 30]
    assert all(row['ready'] for row in worker.starts) and clock.now == 100


def test_later_ping_timeout_stays_twenty_without_another_start_record(factory):
    worker, docker, clock = factory(ready_timeout_seconds=90, docker_options={'ping_seconds': 30})
    with pytest.raises(SandboxUnavailable, match='lost on ping'):
        worker.ping()
    assert clock.now == 50 and len(worker.starts) == 1 and worker.starts[0]['ready'] is True
    assert docker.requests[-1][1:] == ('ping', 20) and len(worker.names) == 1


def test_start_latency_survives_unconfirmed_cleanup_and_slot_stays_held(factory):
    events, slots = [], []
    @contextmanager
    def hold():
        slots.append('held')
        yield
        slots.append('released')
    worker, docker, clock = factory(ready_timeout_seconds=90, start_events=events,
        live=SimpleNamespace(hold=hold), docker_options={'delays': (100,), 'fail_cleanup': True})
    with pytest.raises(CleanupUnconfirmed):
        worker._ensure()
    assert slots == ['held'] and len(worker.unconfirmed) == 1 and len(docker.names) == 1
    assert events == [{'container': docker.names[0], 'seconds': 90, 'ready_timeout_seconds': 90, 'ready': False}]
    assert worker.restarts == worker.cleanups == [] and clock.now == 92


def test_spawn_failure_records_each_attempt_and_keeps_existing_retry_count(factory):
    worker, docker, clock = factory(ready_timeout_seconds=90,
        docker_options={'fail_spawn': True, 'spawn_seconds': 3})
    with pytest.raises(SandboxUnavailable, match='docker did not start'):
        worker._ensure()
    assert [row['seconds'] for row in worker.starts] == [3, 3]
    assert all(row['ready'] is False for row in worker.starts) and len(docker.names) == 2


def test_replacement_after_lost_call_also_uses_ninety_and_keeps_call_deadline(factory):
    worker, docker, clock = factory(ready_timeout_seconds=90,
        docker_options={'delays': (1, 30), 'lost_call': True})
    assert worker.call('p', 'before_call', [{}, None], timeout_s=2)['ok'] is True
    assert [row[1:] for row in docker.requests] == [('ping', 90), ('load', 20), ('call', 12)] * 2
    assert [row['seconds'] for row in worker.starts] == [1, 30]
    assert [row['cause'] for row in worker.restarts] == ['gone'] and worker.dropped == []
    worker.close()


@pytest.mark.parametrize('value', [0, -1, True, None, '90', float('nan'), float('inf'), 10**1000])
def test_invalid_ready_timeout_is_rejected(value):
    with pytest.raises(ValueError, match='ready timeout'):
        client.Worker(ready_timeout_seconds=value)


def test_invalid_start_sink_is_rejected():
    with pytest.raises(ValueError, match='ready timeout'):
        client.Worker(start_events={})
