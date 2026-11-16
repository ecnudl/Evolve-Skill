"""Candidate-local failures are loud; invariants and systematic bugs still pause."""
import json
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, require, write_json
from skillopt.execskill import profiles as p, replay, v226_candidates as c
from skillopt.execskill.cells import Pause
from skillopt.execskill.chain import Terminated
from skillopt.execskill.errors import BudgetStop, ConfigurationError, PackageInvalid, SandboxUnavailable
from skillopt.execskill.package import empty, with_
from tests.execskill_v226_fakes import authored_step
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v226_diagnostics import zebra_procedure


def _raise(error):
    raise error


def fixture(root, configuration='main-v10'):
    parent = empty(step='G/s0', evidence='engineering_fixture')
    st = SimpleNamespace(root=root, evidence='engineering_fixture',
                         setting=SimpleNamespace(extra={'configuration': configuration}))
    return st, parent


def reject(event):
    return {'accepted': False, 'fault': event}


def run(st, parent, key, work):
    return c.guard(st, key, parent, work, reject)(None)


def test_isolated_candidate_error_is_rejected_with_safe_durable_event(tmp_path):
    st, parent = fixture(tmp_path)
    result = run(st, parent, 'procedure-r1', lambda _: _raise(KeyError('private-item and exception message')))
    event = {'kind': 'candidate_error', 'exception': 'KeyError',
             'where': __name__ + ':_raise'}
    assert result == reject(event)
    assert c.counts(tmp_path) == {c.signature(event): 1} and c.events(tmp_path) == [event]
    path = sorted((tmp_path/c.FILE).glob('*.json'))[-1]
    state = read_json(path)
    assert 'private-item' not in str(state) and 'exception message' not in str(state)
    assert set(event) == {'kind', 'exception', 'where'}
    assert p.verified(state, c.KIND)


def test_main_v9_rethrows_without_a_containment_record(tmp_path):
    st, parent = fixture(tmp_path, p.MAIN_V9)
    error = RuntimeError('authored')
    with pytest.raises(RuntimeError) as raised:
        run(st, parent, 'procedure-r1', lambda _: _raise(error))
    assert raised.value is error and not (tmp_path/c.FILE).exists()


def test_same_candidate_across_phases_and_resume_is_counted_once(tmp_path):
    st, parent = fixture(tmp_path)
    first = run(st, parent, 'procedure-r1', lambda _: _raise(TypeError('hidden')))
    for _ in range(3):
        assert run(st, parent, 'procedure-r1', lambda _: pytest.fail('rejected candidate reran')) == first
    assert sum(c.counts(tmp_path).values()) == 1 and len(c.events(tmp_path)) == 1


def test_successful_phases_do_not_erase_a_candidate_error_predecessor(tmp_path):
    st, parent = fixture(tmp_path)
    run(st, parent, 'procedure-r1', lambda _: _raise(ValueError('first')))
    assert run(st, parent, 'procedure-r2', lambda _: {'training': 'passed'}) == {'training': 'passed'}
    error = ValueError('second private message')
    with pytest.raises(ValueError) as raised:
        run(st, parent, 'procedure-r2', lambda _: _raise(error))
    assert raised.value is error
    assert sum(c.counts(tmp_path).values()) == 2
    # An owner retry of the same systematic candidate is not a third candidate.
    with pytest.raises(ValueError):
        run(st, parent, 'procedure-r2', lambda _: _raise(ValueError('third attempt')))
    assert sum(c.counts(tmp_path).values()) == 2


def test_successful_intervening_candidate_does_not_erase_error_history(tmp_path):
    st, parent = fixture(tmp_path)
    run(st, parent, 'procedure-r1', lambda _: _raise(KeyError('first')))
    run(st, parent, 'procedure-r2', lambda _: {'accepted': True})
    with pytest.raises(KeyError):
        run(st, parent, 'procedure-r3', lambda _: _raise(KeyError('later')))
    assert sum(c.counts(tmp_path).values()) == 2


def test_distinct_exception_signatures_are_independent_candidate_faults(tmp_path):
    st, parent = fixture(tmp_path)
    run(st, parent, 'procedure-r1', lambda _: _raise(KeyError('first')))
    run(st, parent, 'procedure-r2', lambda _: _raise(TypeError('second')))
    assert len(c.counts(tmp_path)) == 2 and set(c.counts(tmp_path).values()) == {1}


@pytest.mark.parametrize('role', ['parent', 'incumbent', 'S'])
def test_parent_exception_is_never_contained_and_marks_future_same_signature(tmp_path, role):
    st, parent = fixture(tmp_path)
    original = RuntimeError('parent')
    def work(_):
        with c.arm(role): _raise(original)
    with pytest.raises(RuntimeError) as raised:
        run(st, parent, 'procedure-r1', work)
    assert raised.value is original and c.events(tmp_path) == []
    with pytest.raises(RuntimeError):
        run(st, parent, 'procedure-r2', lambda _: _raise(RuntimeError('candidate')))
    assert sum(c.counts(tmp_path).values()) == 1


def test_system_scope_keeps_unexpected_paid_dispatch_errors_uncontained(tmp_path):
    st, parent = fixture(tmp_path)
    error = KeyError('receipt field')
    def work(_):
        with c.arm('system'):
            with c.arm('candidate'): _raise(error)
    with pytest.raises(KeyError) as raised:
        run(st, parent, 'procedure-r1', work)
    assert raised.value is error and c.events(tmp_path) == []


@pytest.mark.parametrize('kind', [OSError, MemoryError, TimeoutError, BudgetStop, ConfigurationError,
                                  PackageInvalid, SandboxUnavailable, Terminated])
def test_machine_budget_policy_and_protocol_stops_are_never_contained(tmp_path, kind):
    st, parent = fixture(tmp_path)
    error = kind('authored')
    with pytest.raises(kind) as raised:
        run(st, parent, 'procedure-r1', lambda _: _raise(error))
    assert raised.value is error and c.counts(tmp_path) == {}


def test_pause_and_require_invariants_remain_hard(tmp_path):
    st, parent = fixture(tmp_path)
    pause = Pause('configuration', 'private detail', 'unit')
    with pytest.raises(Pause) as raised:
        run(st, parent, 'procedure-r1', lambda _: _raise(pause))
    assert raised.value is pause
    with pytest.raises(ValueError, match='sealed invariant'):
        run(st, parent, 'procedure-r2', lambda _: require(False, 'sealed invariant'))
    assert c.counts(tmp_path) == {}


@pytest.mark.parametrize('module', ['skillopt.execskill.policy', 'skillopt.coevolution_v5.core',
                                    'skillopt.execskill.canary', 'authored.leakage'])
def test_invariant_trace_provenance_is_hard_without_reading_exception_text(tmp_path, module):
    st, parent = fixture(tmp_path)
    scope = {'__name__': module}
    exec('def verify_candidate(_):\n    raise RuntimeError("private message")', scope)
    with pytest.raises(RuntimeError):
        run(st, parent, 'procedure-r1', scope['verify_candidate'])
    assert c.events(tmp_path) == []


@pytest.mark.parametrize('solo', [False, True])
def test_package_arm_protects_incumbent_and_inherited_solo_replays(tmp_path, solo):
    st, initial = fixture(tmp_path)
    procedure = zebra_procedure()
    parent = with_(initial, step='G/s3-zebralogic', add=[procedure])
    package = replay.solo(procedure) if solo else parent
    def work(_):
        with c.package_arm(package): _raise(KeyError('inherited host error'))
    with pytest.raises(KeyError):
        run(st, parent, 'procedure-r1', work)
    assert c.events(tmp_path) == []


def test_new_solo_procedure_is_candidate_local(tmp_path):
    st, parent = fixture(tmp_path)
    def work(_):
        with c.package_arm(replay.solo(zebra_procedure())): _raise(KeyError('candidate'))
    assert run(st, parent, 'procedure-r1', work)['fault']['kind'] == 'candidate_error'


def test_systematic_error_keeps_original_unit_configuration_pause_and_status(tmp_path):
    parent = empty(step='G/s0', evidence='engineering_fixture')
    st, _ = authored_step(tmp_path, parent)
    result = st.unit('engineer-r1', c.guard(st, 'procedure-r1', parent,
        lambda _: _raise(ValueError('candidate private text')), reject))
    assert result['fault']['kind'] == 'candidate_error'
    with pytest.raises(Pause) as paused:
        st.unit('engineer-r2', c.guard(st, 'procedure-r2', parent,
            lambda _: _raise(ValueError('systematic private text')), reject))
    assert paused.value.kind == 'configuration' and paused.value.reason == 'ValueError'
    status = read_json(st.root/'engineer-r2'/'attempt-1'/'status.json')
    assert status['status'] == 'paused' and status['kind'] == 'configuration'
    assert sum(c.counts(st.root).values()) == 2
    assert status['candidate_errors'] == c.counts(st.root)


def test_corrupt_error_state_is_a_sealing_failure(tmp_path):
    st, parent = fixture(tmp_path)
    run(st, parent, 'procedure-r1', lambda _: _raise(KeyError('candidate')))
    path = sorted((tmp_path/c.FILE).glob('*.json'))[-1]
    state = read_json(path)
    state['candidate_errors'] = {}
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match='checksum'):
        run(st, parent, 'procedure-r2', lambda _: {})


def test_no_proposal_round_does_not_break_consecutive_candidate_error_sequence(tmp_path):
    st, parent = fixture(tmp_path)
    run(st, parent, 'procedure-r1', lambda _: _raise(KeyError('candidate')))
    assert run(st, parent, 'procedure-r2', lambda _: (None, {'changes': []})) == (None, {'changes': []})
    with pytest.raises(KeyError):
        run(st, parent, 'procedure-r3', lambda _: _raise(KeyError('next actual candidate')))
    assert sum(c.counts(tmp_path).values()) == 2


def test_role_transport_runtime_error_is_not_candidate_local(tmp_path):
    st, parent = fixture(tmp_path)
    scope = {'__name__': 'skillopt.coevo5.calls'}
    exec('def dispatch(_):\n    raise RuntimeError("network")', scope)
    with pytest.raises(RuntimeError):
        run(st, parent, 'procedure-r1', scope['dispatch'])
    assert c.events(tmp_path) == []


@pytest.mark.parametrize('function', ['analyse', 'payload', '_fit_train'])
def test_preproposal_engineer_preparation_error_is_not_candidate_local(tmp_path, function):
    st, parent = fixture(tmp_path)
    scope = {'__name__': 'skillopt.execskill.engineer'}
    exec('def %s(_):\n    raise KeyError("preproposal input")' % function, scope)
    with pytest.raises(KeyError):
        run(st, parent, 'procedure-r1', scope[function])
    assert c.events(tmp_path) == []


@pytest.mark.parametrize('function', ['run_train', 'check'])
def test_engineer_candidate_checks_remain_containable(tmp_path, function):
    st, parent = fixture(tmp_path)
    scope = {'__name__': 'skillopt.execskill.engineer'}
    exec('def %s(_):\n    raise KeyError("candidate input")' % function, scope)
    assert run(st, parent, 'procedure-r1', scope[function])['fault']['kind'] == 'candidate_error'
