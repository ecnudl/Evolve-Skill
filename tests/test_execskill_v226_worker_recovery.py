"""The first diagnostic exchange shares the registered call-slot loss policy."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from skillopt.execskill import diagnostics, profiles as p, replay
from skillopt.execskill.errors import ConfigurationError
from skillopt.execskill.sandbox import client
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v226_diagnostics import VIEW, zebra_procedure


def worker(tmp_path, monkeypatch, *, configuration='main-v10', losses=1, cause='gone', corrupt=False):
    procedure = zebra_procedure(expression='{"facts": ["Clue 6 compares positions."]}')
    made = client.Worker(scratch=tmp_path, diagnostics_configuration=p.ZEBRA_PC_V15,
                         instruction_configuration=configuration)
    made.start(replay.solo(procedure), kind='cell')
    calls, slots, starts = [], {'held': False}, []
    @contextmanager
    def slot():
        assert not slots['held']
        slots['held'] = True
        try: yield
        finally: slots['held'] = False
    monkeypatch.setattr(made, '_call_slot', slot)
    def ensure():
        if made._container is None:
            starts.append(len(starts)+1)
            made._container = SimpleNamespace(name='authored-%d' % len(starts))
    monkeypatch.setattr(made, '_ensure', ensure)
    monkeypatch.setattr(made, '_cause', lambda _: cause)
    monkeypatch.setattr(made, '_discard', lambda: setattr(made, '_container', None))
    def exchange(request, timeout):
        calls.append((request['op'], made._container.name, slots['held']))
        if request['op'] == 'diagnostics-v215':
            if sum(op == 'diagnostics-v215' for op, _, _ in calls) <= losses:
                raise client._Lost('authored lost first diagnostics exchange')
            return {'ok': True, 'diagnostics_v215': 'bad-pin' if corrupt else digest(request['screen'])}
        value = {'facts': ['Clue 6 compares positions.']}
        return {'ok': True, 'op': 'call', 'proc': request['proc'], 'fn': request['fn'],
                'args_sha256': digest(request['args']), 'value': value, 'value_sha256': digest(value),
                'cpu_ms': 0, 'rss_kib': 1}
    monkeypatch.setattr(made, '_exchange', exchange)
    return made, procedure, calls, starts


@pytest.mark.parametrize('cause', ['gone', 'oom'])
def test_first_diagnostics_exchange_loss_retries_once_inside_call_slot(tmp_path, monkeypatch, cause):
    made, procedure, calls, starts = worker(tmp_path, monkeypatch, cause=cause)
    result = made.call_diagnostics(procedure.id, 'before_call', [VIEW, None], timeout_s=1)
    assert result['ok'] and result['value_sha256'] == digest(result['value'])
    assert [op for op, _, _ in calls] == ['diagnostics-v215', 'diagnostics-v215', 'call']
    assert all(held for _, _, held in calls) and starts == [1, 2]
    assert len(made.restarts) == 1 and made.restarts[0]['cause'] == cause
    assert made.dropped == []
    made.close()


@pytest.mark.parametrize('cause,losses,expected_starts', [('worker', 1, 1), ('gone', 2, 2)])
def test_unrecoverable_diagnostics_loss_maps_to_registered_worker_fault(tmp_path, monkeypatch, cause, losses, expected_starts):
    made, procedure, calls, starts = worker(tmp_path, monkeypatch, cause=cause, losses=losses)
    result = made.call_diagnostics(procedure.id, 'before_call', [VIEW, None], timeout_s=1)
    assert result['ok'] is False and result['fault'] == 'worker'
    assert made.dropped == [procedure.id] and len(starts) == expected_starts
    assert all(held for _, _, held in calls)
    made.close()


def test_diagnostics_configuration_error_still_propagates_without_retry(tmp_path, monkeypatch):
    made, procedure, calls, starts = worker(tmp_path, monkeypatch, losses=0, corrupt=True)
    with pytest.raises(ConfigurationError, match='screen differs'):
        made.call_diagnostics(procedure.id, 'before_call', [VIEW, None], timeout_s=1)
    assert len(starts) == 1 and made.restarts == made.dropped == []
    assert calls[0][-1] is True
    made.close()


def test_main_v9_keeps_original_unhandled_first_diagnostics_loss(tmp_path, monkeypatch):
    made, procedure, calls, starts = worker(tmp_path, monkeypatch, configuration=p.MAIN_V9)
    with pytest.raises(client._Lost):
        made.call_diagnostics(procedure.id, 'before_call', [VIEW, None], timeout_s=1)
    assert calls == [('diagnostics-v215', 'authored-1', False)] and made.restarts == []
    made.close()
