"""Authored pause metadata only; no client, Docker, network or protected data."""
from datetime import datetime, timezone
import errno
import json

import httpx
import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, units, v221_recovery as recovery
from skillopt.execskill.cells import Pause
from skillopt.execskill.errors import BudgetStop, CleanupUnconfirmed, PackageInvalid, SandboxUnavailable
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

IDENTITY = {'unit': 'G/s1-searchqa/train-r1', 'chain': 'G', 'k': 1}


@pytest.fixture
def clock(monkeypatch):
    state = {'now': 1000.0, 'slept': []}
    def sleep(seconds):
        state['slept'].append(seconds)
        state['now'] += seconds
    monkeypatch.setattr(recovery.time, 'time', lambda: state['now'])
    monkeypatch.setattr(recovery.time, 'sleep', sleep)
    return state


def run(root, work, **kwargs):
    return units.run_unit(root, run='authored-run', identity=IDENTITY, work=work,
                          evidence='engineering_fixture', configuration=p.MAIN_V7, **kwargs)


@pytest.mark.parametrize('error,kind', [
    (CleanupUnconfirmed('authored cleanup'), 'container_cleanup_unconfirmed'),
    (OSError(errno.ENOSPC, 'authored full disk'), 'storage_exhausted'),
    (SandboxUnavailable('sandbox_start_failed: authored'), 'docker_start_failure'),
    (Pause('container_cleanup_unconfirmed', 'authored', 'cell'), 'container_cleanup_unconfirmed'),
    (Pause('enospc', 'authored', 'cell'), 'storage_exhausted'),
    (Pause('inode_exhausted', 'authored', 'cell'), 'storage_exhausted'),
    (Pause('client_pool_timeout_zero_sockets', 'authored', 'cell'), 'client_pool_timeout_zero_sockets'),
])
def test_only_explicit_pure_infrastructure_is_normalized(error, kind):
    assert recovery.exception_pause(error) == {'kind': kind, 'reason': recovery.REASONS[kind]}


@pytest.mark.parametrize('error', [
    BudgetStop('authored cap'), PackageInvalid('authored policy'),
    ValueError('authored data'), OSError(errno.EACCES, 'authored permission'),
    SandboxUnavailable('sandbox_unavailable: docker not found'),
    SandboxUnavailable('authored image missing'),
    httpx.PoolTimeout('authored timeout'),
    Pause('infrastructure_incomplete', 'aggregate J5', 'unit'),
    Pause('acceptance_undetermined', 'J6', 'unit'),
    Pause('balance_exhausted', 'authored balance', 'unit'),
    Pause('policy', 'authored policy', 'unit'),
    Pause('data', 'authored data', 'unit'),
    Pause('exception', 'OSError', 'unit'),
])
def test_ambiguous_and_non_infrastructure_pauses_require_owner(error):
    assert recovery.exception_pause(error) is None


def test_pool_timeout_requires_an_explicit_zero_socket_observation():
    error = httpx.PoolTimeout('authored timeout')
    error.socket_count = 1
    assert recovery.exception_pause(error) is None
    error.socket_count = 0
    assert recovery.exception_pause(error)['kind'] == 'client_pool_timeout_zero_sockets'


def test_one_retry_waits_sixty_seconds_and_records_unit_step_and_chain_metadata(tmp_path, clock):
    root = tmp_path / IDENTITY['unit']
    calls = []
    def work(attempt):
        calls.append((attempt.name, clock['now']))
        if len(calls) == 1:
            raise OSError(errno.ENOSPC, 'authored')
        return {'success': True}
    done = run(root, work)
    auto = read_json(root / 'attempt-1' / recovery.FILE)
    assert set(auto) == recovery.FIELDS and auto['by'] == 'system'
    assert auto['attempt'] == 'attempt-1' and auto['kind'] == 'storage_exhausted'
    assert datetime.fromisoformat(auto['at']).tzinfo is not None
    assert clock['slept'] == [60.0]
    assert calls == [('attempt-1', 1000.0), ('attempt-2', 1060.0)]
    assert done['attempt'] == 'attempt-2' and done['result'] == {'success': True}
    assert len(done['automatic_retries']) == 1
    assert len(recovery.records(root.parent)) == 1
    assert not (root / 'attempt-1' / 'recovery.json').exists()
    log = (tmp_path / 'G' / 'auto-recovery.jsonl').read_text().splitlines()
    assert len(log) == 1 and json.loads(log[0])['unit'] == IDENTITY['unit']
    assert run(root, work) == done and len(calls) == 2


def test_second_pure_pause_of_same_unit_still_pauses_even_when_kind_changes(tmp_path, clock):
    root = tmp_path / IDENTITY['unit']; calls = []
    def work(attempt):
        calls.append(attempt.name)
        if len(calls) == 1:
            raise OSError(errno.ENOSPC, 'authored')
        raise SandboxUnavailable('sandbox_start_failed: authored')
    with pytest.raises(Pause):
        run(root, work)
    assert calls == ['attempt-1', 'attempt-2'] and clock['slept'] == [60.0]
    assert (root / 'attempt-1' / recovery.FILE).exists()
    assert not (root / 'attempt-2' / recovery.FILE).exists()
    with pytest.raises(Pause, match='awaiting_owner_decision'):
        run(root, work)
    assert calls == ['attempt-1', 'attempt-2']


def test_a_cleanup_failure_after_completion_commits_without_repeating_work(tmp_path, clock):
    calls, drains = [], []
    def work(attempt):
        calls.append(attempt.name)
        return {'paid_cells': 3}
    def drain():
        drains.append(1)
        if len(drains) == 1:
            raise CleanupUnconfirmed('authored cleanup')
    done = run(tmp_path / IDENTITY['unit'], work, drain=drain)
    assert calls == ['attempt-1'] and len(drains) == 2
    assert done['attempt'] == 'attempt-1' and done['committed_in'] == 'attempt-2'
    assert done['result'] == {'paid_cells': 3} and clock['slept'] == [60.0]


def test_infrastructure_drain_cannot_hide_a_non_infrastructure_stop(tmp_path, clock):
    root = tmp_path / IDENTITY['unit']
    def work(attempt):
        raise BudgetStop('authored exhausted budget')
    def drain():
        raise CleanupUnconfirmed('authored cleanup')
    with pytest.raises(Pause):
        run(root, work, drain=drain)
    status = read_json(root / 'attempt-1' / 'status.json')
    assert status['auto_retry_eligible'] is False
    assert clock['slept'] == [] and not (root / 'attempt-1' / recovery.FILE).exists()


@pytest.mark.parametrize('kind', ['balance_exhausted', 'acceptance_undetermined', 'policy', 'data'])
def test_owner_pauses_are_never_automatically_retried(tmp_path, clock, kind):
    root = tmp_path / IDENTITY['unit']; calls = []
    def work(attempt):
        calls.append(attempt.name)
        raise Pause(kind, 'authored owner pause', IDENTITY['unit'])
    with pytest.raises(Pause):
        run(root, work)
    assert calls == ['attempt-1'] and not clock['slept']
    assert not (root / 'attempt-1' / recovery.FILE).exists()


def test_a_restart_waits_only_the_remaining_registered_delay(tmp_path, clock, monkeypatch):
    root = tmp_path / IDENTITY['unit']
    class Interrupted(BaseException):
        pass
    def interrupted(seconds):
        clock['now'] += 17
        raise Interrupted()
    monkeypatch.setattr(recovery.time, 'sleep', interrupted)
    def fail(attempt):
        raise OSError(errno.ENOSPC, 'authored')
    with pytest.raises(Interrupted):
        run(root, fail)
    assert (root / 'attempt-1' / recovery.FILE).exists()
    waits = []
    def sleep(seconds):
        waits.append(seconds); clock['now'] += seconds
    monkeypatch.setattr(recovery.time, 'sleep', sleep)
    done = run(root, lambda _: {'resumed': True})
    assert waits == [43.0] and done['attempt'] == 'attempt-2'


def test_parent_configuration_still_requires_owner_after_cleanup_pause(tmp_path, clock):
    root = tmp_path / IDENTITY['unit']
    def work(_):
        raise CleanupUnconfirmed('authored cleanup')
    with pytest.raises(Pause):
        units.run_unit(root, run='authored-run', identity=IDENTITY, work=work,
                       evidence='engineering_fixture', configuration=p.MAIN_V6)
    assert not clock['slept'] and not (root / 'attempt-1' / recovery.FILE).exists()
    assert 'auto_retry_eligible' not in read_json(root / 'attempt-1' / 'status.json')


def test_auto_record_cannot_authorize_another_run_or_a_non_infra_status(tmp_path, clock):
    root = tmp_path / IDENTITY['unit']
    attempt = root / 'attempt-1'; attempt.mkdir(parents=True)
    write_json(attempt / 'started.json', p.record('unit-started', 'engineering_fixture',
        {'run': 'another-run', 'identity': IDENTITY}))
    write_json(attempt / 'status.json', p.record('unit-status', 'engineering_fixture',
        {'status': 'paused', 'kind': 'enospc', 'reason': 'authored'}))
    with pytest.raises(ValueError, match='same unit and run'):
        recovery.authorize(root, run='authored-run', identity=IDENTITY)
    assert not (attempt / recovery.FILE).exists()


def test_read_child_retries_the_same_unit_once_and_logs_it(tmp_path, clock, monkeypatch):
    from skillopt.execskill import chain, evaluation
    from tests.test_execskill_chain import setting
    from skillopt.execskill.package import empty
    st = setting(tmp_path, chain_='G', consent=False)
    st.extra['configuration'] = p.MAIN_V7
    package = empty(step='G/s0', evidence='engineering_fixture')
    monkeypatch.setattr(chain, 'read_benches', lambda _: ('searchqa',))
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', lambda *a, **kw: None)
    calls = []
    def launch(_, spec):
        root = chain.unit_root(st, 'G', 'searchqa')
        attempt = recovery.next_attempt(root); attempt.mkdir(parents=True)
        calls.append(attempt.name)
        write_json(attempt / 'started.json', p.record('unit-started', st.evidence, {
            'run': st.run, 'identity': {'unit': 'G/test/searchqa', 'chain': 'G'}}))
        if len(calls) == 1:
            write_json(attempt / 'status.json', p.record('unit-status', st.evidence, {
                'status': 'paused', 'kind': 'docker_start_failure', 'reason': recovery.REASONS['docker_start_failure'],
                'auto_retry_eligible': True}))
            return chain.EXIT_PAUSED
        write_json(root / 'unit.json', p.record('evaluation', st.evidence, {
            'run': st.run, 'chain': 'G', 'packages': {'F': package.sha256}}))
        return chain.EXIT_COMPLETE
    roots = chain.evaluate(st, 'G', package, launch=launch)
    assert calls == ['attempt-1', 'attempt-2'] and clock['slept'] == [60.0]
    assert (roots['searchqa'] / 'attempt-1' / recovery.FILE).exists()
    assert (chain.chain_root(st, 'G') / 'auto-recovery.jsonl').exists()


def test_shared_qualification_keeps_retry_metadata_and_cleans_authored_artifacts(tmp_path, clock, monkeypatch):
    from skillopt.execskill import evaluation, qualify
    calls = []
    def qualify_fake(tasks, root, runtime, **kwargs):
        root.parent.mkdir(parents=True, exist_ok=True)
        root.mkdir()
        calls.append(root.name)
        (root / 'authored-transient.txt').write_text('authored scratch')
        if len(calls) == 1:
            raise OSError(errno.ENOSPC, 'authored')
        result = p.record('sheet-qualification', 'engineering_fixture', {'authored': True})
        write_json(root / 'qualification.json', result)
        return result
    monkeypatch.setattr(qualify, 'qualify', qualify_fake)
    monkeypatch.setattr(qualify, 'load', read_json)
    monkeypatch.setattr(qualify, 'record_digest', lambda value: value[p.RECORD_HASH])
    shared = tmp_path / 'shared'
    found = evaluation._sheet_qualification(shared, [{'task_id': 'authored'}], {},
        allowed={'sheet_test_qualification': True}, native=None, workers=1, evidence='engineering_fixture',
        configuration=p.MAIN_V7, run='authored-run', unit='G/test/spreadsheetbench')
    root = shared / 'test' / evaluation.SHEET_QUALIFICATION
    assert found['authored'] is True and calls == ['attempt-1', 'attempt-2']
    assert clock['slept'] == [60.0]
    assert not list(root.glob('attempt-*/authored-transient.txt'))
    assert (root / 'attempt-1' / recovery.FILE).exists()
    assert (root / 'attempt-1' / 'started.json').exists()
    assert (tmp_path / 'G' / 'auto-recovery.jsonl').exists()


def test_shared_qualification_g_authorizes_d_resumes_remaining_wait(tmp_path, clock, monkeypatch):
    from skillopt.execskill import evaluation, qualify
    calls = []
    def qualify_fake(tasks, root, runtime, **kwargs):
        root.mkdir(parents=True)
        calls.append((root.name, clock['now']))
        if len(calls) == 1:
            raise OSError(errno.ENOSPC, 'authored')
        result = p.record('sheet-qualification', 'engineering_fixture', {'authored': True})
        write_json(root / 'qualification.json', result)
        return result
    monkeypatch.setattr(qualify, 'qualify', qualify_fake)
    monkeypatch.setattr(qualify, 'load', read_json)
    monkeypatch.setattr(qualify, 'record_digest', lambda value: value[p.RECORD_HASH])
    class Interrupted(BaseException):
        pass
    def interrupted(seconds):
        assert seconds == 60.0
        clock['now'] += 17
        raise Interrupted()
    monkeypatch.setattr(recovery.time, 'sleep', interrupted)
    shared = tmp_path / 'shared'
    def qualification(chain):
        return evaluation._sheet_qualification(shared, [{'task_id': 'authored'}], {},
            allowed={'sheet_test_qualification': True}, native=None, workers=1,
            evidence='engineering_fixture', configuration=p.MAIN_V7,
            run='authored-run', unit=chain + '/test/spreadsheetbench')
    with pytest.raises(Interrupted):
        qualification('G')
    root = shared / 'test' / evaluation.SHEET_QUALIFICATION
    first = root / 'attempt-1'
    identity = {'unit': 'shared/test/' + evaluation.SHEET_QUALIFICATION}
    started = p.verified(read_json(first / 'started.json'), 'unit-started')
    assert started['identity'] == identity and started['initiating_chain'] == 'G'
    auto_bytes = (first / recovery.FILE).read_bytes()
    assert set(read_json(first / recovery.FILE)) == recovery.FIELDS
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        clock['now'] += seconds
    monkeypatch.setattr(recovery.time, 'sleep', sleep)
    assert qualification('D')['authored'] is True
    assert waits == [43.0] and calls == [('attempt-1', 1000.0), ('attempt-2', 1060.0)]
    assert (first / recovery.FILE).read_bytes() == auto_bytes
    assert p.verified(read_json(first / 'started.json'), 'unit-started') == started
    resumed = p.verified(read_json(root / 'attempt-2' / 'started.json'), 'unit-started')
    assert resumed['identity'] == identity and resumed['initiating_chain'] == 'D'
    rows = (tmp_path / 'G' / 'auto-recovery.jsonl').read_text().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])['initiating_chain'] == 'G'
    assert json.loads(rows[0])['unit'] == identity['unit']
    assert not (tmp_path / 'D' / 'auto-recovery.jsonl').exists()


def test_persisted_auto_recovery_cannot_resume_a_different_run(tmp_path, clock, monkeypatch):
    root = tmp_path / IDENTITY['unit']
    class Interrupted(BaseException):
        pass
    monkeypatch.setattr(recovery.time, 'sleep', lambda _: (_ for _ in ()).throw(Interrupted()))
    def fail(_):
        raise OSError(errno.ENOSPC, 'authored')
    with pytest.raises(Interrupted):
        run(root, fail)
    with pytest.raises(ValueError, match='same unit and run'):
        units.run_unit(root, run='different-run', identity=IDENTITY, work=lambda _: {},
                       evidence='engineering_fixture', configuration=p.MAIN_V7)


POOL_TIMEOUT = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {},
                'error_type': 'transport', 'attempts': [{'error': 'PoolTimeout'}] * 4}


def test_real_endpoint_receipt_settles_before_zero_socket_pause_and_unit_retry(tmp_path, clock, monkeypatch):
    from types import SimpleNamespace
    from skillopt.coevo5.budget import Budget
    from skillopt.coevo5.calls import Slots
    from skillopt.execskill import budgets
    from tests.test_execskill_cells import _Client, _reply
    client = _Client(POOL_TIMEOUT, _reply('authored answer'))
    client.model, client.max_tokens = p.CHAINS['G'], 100
    budget = Budget(tmp_path / 'ledger')
    budget.declare({'overall': 1000000, 'G:solver': 1000000})
    st = SimpleNamespace(extra={'configuration': p.MAIN_V7}, budget=budget, cooldown=0,
                         slots={client.model: Slots(tmp_path / 'slots', client.model, 1)})
    monkeypatch.setattr(recovery, 'process_socket_count', lambda: 0)
    sends = []
    def work(attempt):
        endpoint = budgets.endpoint(st, ('overall', 'G:solver'), client=client, max_tokens_bound=100)
        assert isinstance(endpoint, recovery.Endpoint)
        recorder = endpoint.recorder(label=IDENTITY['unit'])
        try:
            return {'ok': recorder('authored system', 'authored user')['ok']}
        finally:
            sends.extend(recorder.sends)
    done = run(tmp_path / IDENTITY['unit'], work)
    assert done['result'] == {'ok': True} and len(client.requests) == 2
    assert sends[0]['receipt'] == POOL_TIMEOUT and sends[0]['charged'] == 0
    assert sends[0]['infrastructure_observation'] == {
        'kind': 'client_pool_timeout', 'socket_count': 0, 'zero_sockets_confirmed': True}
    assert budget.snapshot()['overall']['settled'] == 15
    assert done['automatic_retries'][0]['kind'] == 'client_pool_timeout_zero_sockets'
    assert clock['slept'] == [60.0]


@pytest.mark.parametrize('sockets', [None, 1])
def test_pool_timeout_without_zero_socket_proof_remains_an_ordinary_receipt(tmp_path, monkeypatch, sockets):
    from skillopt.coevo5.calls import Slots
    from tests.test_execskill_cells import _Client
    monkeypatch.setattr(recovery, 'process_socket_count', lambda: sockets)
    endpoint = recovery.Endpoint(_Client(POOL_TIMEOUT), model=p.CHAINS['G'], max_tokens=100,
                                  slots=Slots(tmp_path / 'slots', p.CHAINS['G'], 1))
    recorder = endpoint.recorder(label='authored')
    assert endpoint.send('authored system', 'authored user', recorder) == POOL_TIMEOUT
    assert recorder.sends[-1]['infrastructure_observation']['zero_sockets_confirmed'] is False


def test_mixed_transport_failure_never_observes_sockets_or_becomes_a_pure_pause(tmp_path, monkeypatch):
    from skillopt.coevo5.calls import Slots
    from tests.test_execskill_cells import _Client
    receipt = {**POOL_TIMEOUT, 'attempts': [{'error': 'ConnectError'}, {'error': 'PoolTimeout'}]}
    monkeypatch.setattr(recovery, 'process_socket_count', lambda: pytest.fail('Mixed receipt is not pure'))
    endpoint = recovery.Endpoint(_Client(receipt), model=p.CHAINS['G'], max_tokens=100,
                                  slots=Slots(tmp_path / 'slots', p.CHAINS['G'], 1))
    recorder = endpoint.recorder(label='authored')
    assert endpoint.send('authored system', 'authored user', recorder) == receipt
    assert 'infrastructure_observation' not in recorder.sends[-1]


def test_solver_shell_cannot_swallow_the_proven_pool_timeout_pause(tmp_path, monkeypatch):
    from dataclasses import replace
    from skillopt.execskill.cells import Arm, TrainingStore, run_cell
    from skillopt.execskill.package import empty
    from tests.test_execskill_cells import _Client, _context, _cell
    from tests.fixtures.execskill.items import searchqa_items
    ctx = _context(tmp_path, _Client(POOL_TIMEOUT))
    from skillopt.execskill.instruction_start import pins
    ctx = replace(ctx, configuration=p.MAIN_V7, cards={b: row['text'] for b, row in pins().items()},
        endpoint=recovery.Endpoint(ctx.endpoint.client,
        model=ctx.endpoint.model, max_tokens=ctx.endpoint.max_tokens, slots=ctx.endpoint.slots))
    monkeypatch.setattr(recovery, 'process_socket_count', lambda: 0)
    item = searchqa_items(1)[0]; cell = _cell(item, unit=IDENTITY['unit'])
    store = TrainingStore(ctx.attempt)
    with pytest.raises(Pause) as stopped:
        run_cell(ctx, cell, {'public': item['public'], 'private': item['private']},
                 Arm('card', empty(step='authored', evidence='engineering_fixture')), store=store)
    assert stopped.value.kind == 'client_pool_timeout_zero_sockets'
    found = read_json(ctx.attempt / 'cells' / (cell['id'] + '.json'))
    assert found['stop']['auto_retry_eligible'] is True and found['sends'][0]['receipt'] == POOL_TIMEOUT
    assert found['logical_calls'][0]['exception'] == 'Pause'
