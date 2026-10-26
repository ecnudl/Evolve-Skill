"""Opt-in sandbox cleanup grace, exercised with a clock and CLI fake only."""
from contextlib import ExitStack
from types import SimpleNamespace
import re

import pytest

from skillopt.execskill.errors import CleanupUnconfirmed
from skillopt.execskill.sandbox import client


UNIT = 'D/s1-zebralogic/engineer-r3'
TAG = client.unit_tag('D', UNIT)
PREFIX = client.PREFIX + TAG + '-'
NAME = PREFIX + 'a' * 32
OTHER = client.PREFIX + client.unit_tag('D', 'D/s1-zebralogic/another-unit') + '-' + 'b' * 32
CHAIN = client.PREFIX + client.unit_tag('G', UNIT) + '-' + 'c' * 32


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(seconds)
        self.now += seconds


class Docker:
    binary = 'authored-docker'

    def __init__(self, clock, *, names=(NAME,), remove_on=None, duration=0, foreign=False, failed_ps=False):
        self.clock, self.names = clock, set(names)
        self.remove_on = remove_on or {}
        self.duration, self.foreign, self.failed_ps = duration, foreign, failed_ps
        self.calls, self.removed = [], {}

    def run(self, argv, timeout):
        assert 0 < timeout <= client.CLEANUP_SECONDS
        self.calls.append({'argv': list(argv), 'timeout': timeout, 'at': self.clock.now})
        self.clock.now += min(self.duration, timeout)
        if self.duration > timeout:
            return client.Completed(None, b'')
        if argv[1] == 'rm':
            name = argv[-1]
            self.removed[name] = self.removed.get(name, 0) + 1
            if self.removed[name] >= self.remove_on.get(name, 10**6):
                self.names.discard(name)
            return client.Completed(0, b'')
        assert argv[1] == 'ps'
        if self.failed_ps:
            return client.Completed(None, b'')
        pattern = argv[argv.index('--filter') + 1].removeprefix('name=')
        names = self.names if self.foreign else {name for name in self.names if re.search(pattern, '/' + name)}
        return client.Completed(0, ('\n'.join(sorted(names)) + '\n').encode())


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(client.time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(client.time, 'sleep', clock.sleep)
    return clock


def operations(docker):
    return [row['argv'][1] for row in docker.calls]


@pytest.mark.parametrize('explicit', [False, True])
def test_zero_grace_preserves_three_attempts_timing_exception_and_none_return(clock, explicit):
    docker = Docker(clock)
    kwargs = {'cleanup_grace_seconds': 0} if explicit else {}
    with pytest.raises(CleanupUnconfirmed) as failure:
        client.cleanup(NAME, docker=docker, **kwargs)
    assert str(failure.value) == 'sandbox cleanup unconfirmed (%s): still listed after 3 tries in 2.0 s' % NAME
    assert operations(docker) == ['rm', 'ps'] * 3
    assert [row['timeout'] for row in docker.calls] == [10] * 6
    assert clock.sleeps == [1, 1] and clock.now == 2
    docker = Docker(clock, remove_on={NAME: 1})
    assert client.cleanup(NAME, docker=docker, **kwargs) is None


def test_positive_grace_does_not_change_a_standard_confirmation(clock):
    docker = Docker(clock, remove_on={NAME: 3})
    assert client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120) is None
    assert operations(docker) == ['rm', 'ps'] * 3 and clock.sleeps == [1, 1]


@pytest.mark.parametrize('tries,seconds', [(4, 15), (5, 30), (10, 105)])
def test_later_exact_confirmation_records_extra_tries_and_grace_seconds(clock, tries, seconds):
    docker = Docker(clock, names=(NAME, OTHER, CHAIN), remove_on={NAME: tries})
    result = client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120)
    assert result == {'container': NAME, 'extra_tries': tries - 3, 'extra_seconds': seconds}
    assert clock.now == 2 + seconds and clock.sleeps == [1, 1] + [15] * (tries - 3)
    assert docker.names == {OTHER, CHAIN} and set(docker.removed) == {NAME}
    assert all(row['argv'][4] == 'name=^/%s$' % NAME for row in docker.calls if row['argv'][1] == 'ps')


def test_unconfirmed_name_uses_up_bounded_grace_then_stops(clock):
    docker = Docker(clock)
    with pytest.raises(CleanupUnconfirmed, match='still listed after 10 tries in 122.0 s'):
        client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120)
    assert docker.removed[NAME] == 10 and clock.now == 122
    assert clock.sleeps == [1, 1] + [15] * 8
    assert [row['at'] for row in docker.calls if row['argv'][1] == 'rm'] == [0, 1, 2, 17, 32, 47, 62, 77, 92, 107]


def test_missing_list_reply_never_counts_as_confirmed_removal(clock):
    docker = Docker(clock, remove_on={NAME: 4}, failed_ps=True)
    with pytest.raises(CleanupUnconfirmed, match='docker ps failed'):
        client.cleanup(NAME, docker=docker, cleanup_grace_seconds=31)
    assert not docker.names and clock.now == 33


def test_deadline_caps_rm_and_does_not_start_listing_after_budget_is_used(clock):
    docker = Docker(clock, duration=10)
    with pytest.raises(CleanupUnconfirmed, match='docker ps failed'):
        client.cleanup(NAME, docker=docker, cleanup_grace_seconds=18)
    # Original 3 pairs cost 60s plus 2 pauses. The extra rm has only 3s left.
    assert clock.now == 80 and len(docker.calls) == 7
    assert docker.calls[-1] == {'argv': [docker.binary, 'rm', '--force', NAME], 'timeout': 3, 'at': 77}


def test_deadline_caps_exact_listing_and_counts_confirmation_at_deadline(clock):
    docker = Docker(clock, duration=5, remove_on={NAME: 4})
    result = client.cleanup(NAME, docker=docker, cleanup_grace_seconds=25)
    assert result == {'container': NAME, 'extra_tries': 1, 'extra_seconds': 25}
    assert clock.now == 57 and docker.calls[-1]['timeout'] == 5


def test_long_commands_do_not_overlap_or_add_unbounded_sleep(clock):
    docker = Docker(clock, duration=10, remove_on={NAME: 5})
    result = client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120)
    extra = [row['at'] for row in docker.calls if row['argv'][1] == 'rm'][3:]
    assert extra == [77, 97] and result['extra_seconds'] == 55
    assert clock.sleeps == [1, 1, 15]


def test_oversleep_keeps_extended_starts_at_least_fifteen_seconds_apart(clock, monkeypatch):
    original_sleep = clock.sleep
    def oversleep(seconds):
        original_sleep(seconds)
        if seconds == 15:
            clock.now += 2
    monkeypatch.setattr(client.time, 'sleep', oversleep)
    docker = Docker(clock, duration=2, remove_on={NAME: 5})
    client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120)
    assert [row['at'] for row in docker.calls if row['argv'][1] == 'rm'][3:] == [31, 46]


def test_delayed_successful_listing_after_deadline_is_not_a_confirmation(clock):
    class LateDocker(Docker):
        def run(self, argv, timeout):
            result = super().run(argv, timeout)
            if argv[1] == 'ps' and self.removed.get(NAME) == 4:
                clock.now += 120
            return result
    docker = LateDocker(clock, remove_on={NAME: 4})
    with pytest.raises(CleanupUnconfirmed):
        client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120)
    assert docker.removed[NAME] == 4 and not docker.names


@pytest.mark.parametrize('grace', [1, 14, 15])
def test_no_extra_command_starts_when_first_poll_reaches_deadline(clock, grace):
    docker = Docker(clock)
    with pytest.raises(CleanupUnconfirmed):
        client.cleanup(NAME, docker=docker, cleanup_grace_seconds=grace)
    assert len(docker.calls) == 6 and clock.now == 2 + grace


def test_exact_name_confirmation_ignores_unrelated_names_even_if_cli_filter_is_wrong(clock):
    docker = Docker(clock, names=(NAME, OTHER, CHAIN), remove_on={NAME: 4}, foreign=True)
    assert client.cleanup(NAME, docker=docker, cleanup_grace_seconds=120)['extra_tries'] == 1
    assert docker.names == {OTHER, CHAIN} and set(docker.removed) == {NAME}


def test_zero_grace_drain_keeps_immediate_finding_and_never_removes(clock):
    docker = Docker(clock)
    with pytest.raises(CleanupUnconfirmed) as failure:
        client.drain_unit('D', UNIT, docker=docker)
    assert str(failure.value) == 'sandbox containers remain (%s*): %s' % (PREFIX, NAME)
    assert operations(docker) == ['ps'] and not clock.sleeps
    docker.names.clear()
    assert client.drain_unit('D', UNIT, docker=docker) is None


def test_grace_drain_confirms_only_its_exact_names_and_records_extension(clock):
    docker = Docker(clock, names=(NAME, OTHER, CHAIN), remove_on={NAME: 5}, foreign=True)
    events = []
    assert client.drain_unit('D', UNIT, docker=docker, cleanup_grace_seconds=120, cleanups=events) is events
    assert events == [{'container': NAME, 'seconds': 32, 'extra_tries': 2, 'extra_seconds': 30}]
    assert docker.names == {OTHER, CHAIN} and set(docker.removed) == {NAME}


def test_drain_keeps_prior_extended_confirmation_when_later_name_never_disappears(clock):
    second = PREFIX + 'b' * 32
    docker = Docker(clock, names=(NAME, second), remove_on={NAME: 4})
    events = []
    with pytest.raises(CleanupUnconfirmed):
        client.drain_check(PREFIX, docker=docker, cleanup_grace_seconds=30, cleanups=events)
    assert events == [{'container': NAME, 'seconds': 17, 'extra_tries': 1, 'extra_seconds': 15}]
    assert docker.names == {second}


def test_drain_reports_newly_appearing_name_without_expanding_removal_snapshot(clock):
    late = PREFIX + 'd' * 32
    class AppearingDocker(Docker):
        def run(self, argv, timeout):
            result = super().run(argv, timeout)
            if argv[1] == 'rm' and NAME not in self.names:
                self.names.add(late)
            return result
    docker = AppearingDocker(clock, remove_on={NAME: 4})
    events = []
    with pytest.raises(CleanupUnconfirmed, match=late):
        client.drain_unit('D', UNIT, docker=docker, cleanup_grace_seconds=120, cleanups=events)
    assert docker.names == {late} and set(docker.removed) == {NAME}
    assert events == [{'container': NAME, 'seconds': 17, 'extra_tries': 1, 'extra_seconds': 15}]


@pytest.mark.parametrize('prefix', [client.PREFIX, client.PREFIX + 'd-', client.PREFIX + TAG])
def test_grace_never_turns_machine_or_chain_drain_into_removal(clock, prefix):
    docker = Docker(clock)
    with pytest.raises(ValueError, match='exact sandbox unit prefix'):
        client.drain_check(prefix, docker=docker, cleanup_grace_seconds=120)
    assert docker.calls == []


def test_malformed_name_under_unit_prefix_is_a_finding_never_a_removal(clock):
    docker = Docker(clock, names=(PREFIX + 'not-a-container',))
    with pytest.raises(CleanupUnconfirmed):
        client.drain_check(PREFIX, docker=docker, cleanup_grace_seconds=120)
    assert operations(docker) == ['ps']


def test_positive_drain_without_lingering_names_has_no_event(clock):
    docker = Docker(clock, names=(OTHER, CHAIN), foreign=True)
    assert client.drain_unit('D', UNIT, docker=docker, cleanup_grace_seconds=120) == []
    assert operations(docker) == ['ps']


@pytest.mark.parametrize('invalid', [-1, float('inf'), float('nan'), True, False, '120', None])
def test_invalid_grace_rejected_without_cli_work(clock, invalid):
    docker = Docker(clock)
    for call in (lambda: client.cleanup(NAME, docker=docker, cleanup_grace_seconds=invalid),
                 lambda: client.drain_unit('D', UNIT, docker=docker, cleanup_grace_seconds=invalid),
                 lambda: client.Worker(docker=docker, cleanup_grace_seconds=invalid)):
        with pytest.raises(ValueError):
            call()
    assert docker.calls == []


def attached_worker(docker, *, grace=0, events=None):
    worker = client.Worker(docker=docker, cleanup_grace_seconds=grace, cleanup_events=events)
    released = []
    stack = ExitStack()
    stack.callback(released.append, NAME)
    worker._container = client._Container(NAME, stack)
    return worker, released


@pytest.mark.parametrize('grace', [0, 120])
def test_standard_worker_cleanup_record_remains_exact_without_extension(clock, grace):
    docker = Docker(clock, remove_on={NAME: 3})
    events = []
    worker, released = attached_worker(docker, grace=grace, events=events)
    worker.close()
    assert worker.cleanups == [{'container': NAME, 'seconds': 2}]
    assert worker.restarts == events == [] and released == [NAME]


def test_worker_extended_confirmation_is_recorded_and_releases_its_live_slot(clock):
    docker = Docker(clock, remove_on={NAME: 4})
    events = []
    worker, released = attached_worker(docker, grace=120, events=events)
    worker.close()
    assert worker.cleanups == events == [{'container': NAME, 'seconds': 17, 'extra_tries': 1, 'extra_seconds': 15}]
    assert worker.unconfirmed == [] and released == [NAME]


def test_unconfirmed_worker_keeps_live_slot_and_does_not_claim_a_cleanup(clock):
    docker = Docker(clock)
    events = []
    worker, released = attached_worker(docker, grace=30, events=events)
    with pytest.raises(CleanupUnconfirmed):
        worker.close()
    assert not released and worker.unconfirmed[0].name == NAME
    assert worker.cleanups == events == []


def test_extended_confirmation_survives_a_later_local_process_reap_failure(clock, monkeypatch):
    docker = Docker(clock, remove_on={NAME: 4})
    events = []
    worker, _ = attached_worker(docker, grace=120, events=events)
    worker._container.process = SimpleNamespace(stdin=SimpleNamespace(close=lambda: None))
    def broken_reap(process):
        raise CleanupUnconfirmed('authored local process failure')
    monkeypatch.setattr(client, '_reap', broken_reap)
    with pytest.raises(CleanupUnconfirmed, match='local process'):
        worker.close()
    assert events == [{'container': NAME, 'seconds': 17, 'extra_tries': 1, 'extra_seconds': 15}]


@pytest.mark.parametrize('grace', [0, 120])
def test_failed_ready_ping_resumes_existing_start_retry_only_after_grace_confirmation(clock, monkeypatch, grace):
    docker = Docker(clock, remove_on={NAME: 4})
    events = []
    worker = client.Worker(docker=docker, cleanup_grace_seconds=grace, cleanup_events=events)
    starts, released = [], []
    def start():
        starts.append(len(starts) + 1)
        worker._container = client._Container(NAME if len(starts) == 1 else OTHER, ExitStack())
        worker._container.stack.callback(released.append, worker._container.name)
        if len(starts) == 1:
            raise client._Lost('no reply in time')
    monkeypatch.setattr(worker, '_start', start)
    monkeypatch.setattr(worker, '_missing', lambda: None)
    if not grace:
        with pytest.raises(CleanupUnconfirmed):
            worker._ensure()
        assert starts == [1] and docker.removed[NAME] == 3
        assert not released and worker.unconfirmed[0].name == NAME
        assert worker.restarts == worker.cleanups == events == []
        return
    worker._ensure()
    assert starts == [1, 2] and client.START_TRIES == 2
    assert released == [NAME] and worker._container.name == OTHER
    assert worker.restarts == [{'cause': 'start_failed', 'container': NAME, 'procedure': None}]
    assert worker.cleanups == events == [{'container': NAME, 'seconds': 17, 'extra_tries': 1, 'extra_seconds': 15}]
