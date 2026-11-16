"""Authored route-B bodies, receipts and ledger guards; mock transport only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import weak_solver_probe as frozen
from skillopt.coevo5.budget import Budget, DEEPSEEK
from skillopt.coevo5.calls import BREACH, Endpoint, Slots, _request_hash
from skillopt.coevo5.outcomes import AssumptionBroken
from skillopt.coevo5.protocol import RESEND_COOLDOWN_SECONDS
from skillopt.continual_eval.core import write_json
from skillopt.execskill import budgets, client, manifest, profiles as p, routes, units, v214_stages, v225_client
from skillopt.execskill.errors import ConfigurationError
from tests.execskill_fakes import fake_config, usage
from tests.test_execskill_routes import Gateway, completion, northgate_env
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]
BEFORE = json.loads((ROOT / 'tests/fixtures/execskill/v225_route_thinking_legacy.json').read_text())


def registered(tmp_path, configuration=p.MAIN_V9):
    env = northgate_env(tmp_path)
    glm = fake_config(tmp_path, client.GLM_SOLVER)['repo']
    blocks = {chain: manifest.solver_block(chain, env_path=env if chain == 'D' else glm,
        branch='N' if chain == 'D' else None, longest=256 if chain == 'D' else None,
        configuration=configuration) for chain in ('G', 'D')}
    return {'configuration': configuration, 'root': str(tmp_path / 'run'), p.RECORD_HASH: 'a' * 64,
        'clients': {'solver': blocks, 'roles': manifest.role_settings(configuration),
                    'routes': {'D': {'B': routes.pin('D', 'B', env_path=env,
                        solver_block=blocks['D'], configuration=configuration)}}}}


def make(tmp_path, gateway, configuration=p.MAIN_V9, bench='searchqa'):
    value = registered(tmp_path, configuration)
    factory = manifest._clients(value, 'D', gateway.transport, route='B')
    return factory(p.CHAINS['D'], bench), value


@pytest.mark.parametrize('bench', p.active_benches(p.MAIN_V9))
def test_registered_main_v9_client_sends_both_fields_and_nothing_else_changes(tmp_path, bench):
    gateway = Gateway(completion())
    new, value = make(tmp_path, gateway, bench=bench)
    old = manifest.make_solver(registered(tmp_path, p.MAIN_V8), 'D', bench, transport=gateway.transport)
    assert new.body('sys', 'user') == {**old.body('sys', 'user'), 'thinking': {'type': 'disabled'}}
    assert new.thinking == 'disabled' and new.effort == 'none'
    assert new.call('sys', 'user')['ok']
    assert gateway.bodies == [new.body('sys', 'user')]
    assert value['clients']['solver']['D']['thinking'] == value['clients']['routes']['D']['B']['thinking'] == {
        'type': 'disabled'}
    assert manifest.solver_config(value, 'D', bench)['thinking'] == {'type': 'disabled'}
    new.http.close(); old.http.close()


@pytest.mark.parametrize('configuration', sorted(BEFORE['configurations']))
def test_every_older_solver_block_and_route_pin_stays_exact(configuration):
    blocks = {chain: manifest.solver_block(chain, env_path=ROOT / 'tests/authored.env',
        branch='N' if chain == 'D' else None, longest=256 if chain == 'D' else None,
        configuration=configuration) for chain in ('G', 'D')}
    pin = routes.pin('D', 'B', env_path=ROOT / 'tests/authored.env', solver_block=blocks['D'],
                     configuration=configuration)
    manifest.check_clients({'solver': blocks, 'roles': manifest.role_settings(configuration),
                            'routes': {'D': {'B': pin}}}, configuration=configuration)
    for block in [*blocks.values(), pin]:
        block['env_path'] = 'authored.env'
    assert {'solver': blocks, 'route_B': pin} == BEFORE['configurations'][configuration]
    assert hashlib.sha256(Path(client.__file__).read_bytes()).hexdigest() == BEFORE['client_source_sha256']


def test_legacy_route_b_body_and_config_keys_remain_exact(tmp_path):
    made, value = make(tmp_path, Gateway(completion()), configuration=p.MAIN_V8)
    assert type(made) is client.NorthgateClient
    assert made.body('sys', 'user') == {'model': client.NORTHGATE_MODEL,
        'messages': [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'user'}],
        'max_tokens': p.solver_tokens(p.CHAINS['D'], 'searchqa'), 'temperature': 0, 'reasoning_effort': 'none'}
    assert client.CONFIG_KEYS == {client.GLM_SOLVER: frozenset({'repo', 'proxy'}),
        client.ELUCID_MODEL: frozenset({'env_path', 'proxy', 'max_tokens', 'read_timeout'})}
    assert set(value['clients']['solver']['D']) == manifest.SOLVER_FIELDS
    assert set(value['clients']['routes']['D']['B']) == routes.FIELDS
    made.http.close()


@pytest.mark.parametrize('configuration', [p.MAIN_V7, p.MAIN_V8, p.MAIN_V9])
@pytest.mark.parametrize('target', ['solver', 'route'])
@pytest.mark.parametrize('damage', ['missing', 'enabled', 'extra_key'])
def test_solver_and_route_identity_refuse_wrong_thinking_in_both_directions(tmp_path, configuration, target, damage):
    value = registered(tmp_path, configuration)
    manifest.check_clients(value['clients'], configuration=configuration)
    block = (value['clients']['solver']['D'] if target == 'solver' else value['clients']['routes']['D']['B'])
    if configuration != p.MAIN_V9:
        block['thinking'] = {'type': 'disabled'}
    elif damage == 'missing':
        del block['thinking']
    elif damage == 'enabled':
        block['thinking'] = {'type': 'enabled'}
    else:
        block['thinking']['extra'] = True
    with pytest.raises(ValueError):
        manifest.check_clients(value['clients'], configuration=configuration)
    if configuration == p.MAIN_V9:
        with pytest.raises(ValueError):
            manifest.make_solver(value, 'D', 'searchqa', transport=Gateway(completion()).transport)


def test_adapter_refuses_missing_option_wrong_route_or_other_configuration(tmp_path):
    value = registered(tmp_path)
    config = manifest.solver_config(value, 'D', 'searchqa')
    for configuration, changed in [(p.MAIN_V8, config),
            (p.MAIN_V9, {key: val for key, val in config.items() if key != 'thinking'}),
            (p.MAIN_V9, {**config, 'route': 'A'}),
            (p.MAIN_V9, {**config, 'thinking': {'type': 'enabled'}})]:
        with pytest.raises(ConfigurationError):
            v225_client.solver_client(client.ELUCID_MODEL, configuration=configuration, config=changed,
                                      transport=Gateway(completion()).transport)


def test_s1e_control_uses_registered_route_b_and_drops_both_fields(tmp_path):
    gateway = Gateway(completion(reasoning='control reasoning', tokens=2))
    registered_client, _ = make(tmp_path, gateway)
    control = v225_client.control_client(registered_client)
    assert control.body('sys', 'user') == {key: value for key, value in registered_client.body('sys', 'user').items()
                                          if key not in ('thinking', 'reasoning_effort')}
    receipt = control.call('sys', 'user')
    assert (receipt['error_type'], receipt['subtype'], receipt['route'], receipt['route_model']) == (
        'thinking_mismatch', 'reasoning_mismatch', 'B', client.NORTHGATE_MODEL)
    assert 'thinking' not in gateway.bodies[0] and 'reasoning_effort' not in gateway.bodies[0]
    assert registered_client.body('sys', 'user')['thinking'] == {'type': 'disabled'}
    assert registered_client.effort == 'none'
    registered_client.http.close()


def test_actual_main_v9_s1_first_call_and_length_probe_use_registered_body(tmp_path):
    gateway = Gateway(completion())
    value = registered(tmp_path)
    ledger = Budget(tmp_path / 'ledger', poll=0)
    ledger.declare({scope: 10 ** 9 for scope in budgets.first_call_scopes('D')})
    factory = manifest._clients(value, 'D', gateway.transport, route='B')
    setting = SimpleNamespace(root=Path(value['root']), run=value[p.RECORD_HASH], evidence='engineering_fixture',
        extra={'configuration': p.MAIN_V9, 'route': 'B'}, clients=factory, branch='N', longest=256,
        budget=ledger, slots={client.ELUCID_MODEL: Slots(tmp_path / 'slots', client.ELUCID_MODEL, 2)}, cooldown=0)
    result = v214_stages.s1(setting, 'D')
    assert result['passed'] and result['solver_probe']['calls'] == 3
    assert len(gateway.requests) == 4  # First-call confirmation, then the three length probes.
    assert all(body['thinking'] == {'type': 'disabled'} and body['reasoning_effort'] == 'none'
               and body['model'] == client.NORTHGATE_MODEL for body in gateway.bodies)
    factory(client.ELUCID_MODEL, 'searchqa').http.close()
    factory(client.ELUCID_MODEL, 'zebralogic').http.close()


@pytest.mark.parametrize('finish', ['stop', 'length'])
@pytest.mark.parametrize('reasoning,tokens', [(None, None), ('', 0), ('reasoning', 3),
    ('reasoning', None), (None, 3), (' ', 0), (['reasoning'], 0), (None, 'invalid')])
def test_disabled_frozen_receipt_branch_composes_without_changing_any_route_b_field(
        tmp_path, monkeypatch, finish, reasoning, tokens):
    monkeypatch.setattr(frozen.time, 'time', lambda: 1234.0)
    status, body = completion(reasoning=reasoning, tokens=tokens)
    body['choices'][0]['finish_reason'] = finish
    old, _ = make(tmp_path, Gateway((status, deepcopy(body))), configuration=p.MAIN_V8)
    new, _ = make(tmp_path, Gateway((status, deepcopy(body))))
    before, after = old.call('sys', 'user'), new.call('sys', 'user')
    assert before == after  # Includes usage, reasoning_chars/tokens, visible tokens and subtype.
    if reasoning not in (None, '') or tokens not in (None, 0):
        assert (after['ok'], after['error_type'], after['subtype']) == (
            False, 'thinking_mismatch', 'reasoning_mismatch')
    old.http.close(); new.http.close()


def endpoint(tmp_path, made, *, ledger=None, sleep=lambda _: None):
    return Endpoint(made, model=client.ELUCID_MODEL, max_tokens=32768,
        slots=Slots(tmp_path / 'slots', client.ELUCID_MODEL, 2), budget=ledger,
        scopes=(DEEPSEEK,) if ledger is not None else (), sleep=sleep)


def test_new_shape_reasoning_reply_still_resends_identically(tmp_path):
    gateway = Gateway(completion(reasoning='reasoning', tokens=2), completion())
    made, _ = make(tmp_path, gateway)
    slept = []
    recorder = endpoint(tmp_path, made, sleep=slept.append).recorder(label='authored-cell')
    result = recorder('sys', 'user')
    assert result['ok'] and len(recorder.sends) == 2
    assert recorder.sends[0]['receipt']['subtype'] == 'reasoning_mismatch'
    assert gateway.requests[0].content == gateway.requests[1].content
    assert gateway.bodies[0]['thinking'] == {'type': 'disabled'}
    assert slept == [RESEND_COOLDOWN_SECONDS]
    made.http.close()


@pytest.mark.parametrize('reasoning', [None, 'reasoning'])
def test_reply_above_bound_still_halts_ledger_before_resend(tmp_path, reasoning):
    status, body = completion(reasoning=reasoning, tokens=30000 if reasoning else 0)
    body['usage'] = usage(32769)
    if reasoning:
        body['usage']['completion_tokens_details'] = {'reasoning_tokens': 30000}
    gateway = Gateway((status, body), completion())
    made, _ = make(tmp_path, gateway)
    ledger = Budget(tmp_path / 'ledger', poll=0)
    ledger.declare({DEEPSEEK: 10 ** 9})
    recorder = endpoint(tmp_path, made, ledger=ledger).recorder(label='authored-cell')
    with pytest.raises(AssumptionBroken):
        recorder('sys', 'user')
    assert len(gateway.requests) == 1 and recorder.broken == BREACH and recorder.receipts == []
    assert ledger.snapshot()['halted'] == {'reason': BREACH, 'label': 'authored-cell'}
    if reasoning:
        assert recorder.sends[0]['receipt']['subtype'] == 'reasoning_mismatch'
    made.http.close()


def test_chain_g_and_glm_role_clients_stay_identical(tmp_path, monkeypatch):
    monkeypatch.setattr(frozen.time, 'time', lambda: 1234.0)
    made = []
    for configuration in (p.MAIN_V8, p.MAIN_V9):
        value = registered(tmp_path, configuration)
        factory = manifest._clients(value, 'G', Gateway(completion(model=client.GLM_SOLVER)).transport)
        made.append((value['clients']['solver']['G'], factory(client.GLM_SOLVER, 'searchqa'),
                     factory(client.GLM_SOLVER, None)))
    assert made[0][0] == made[1][0]
    for index in (1, 2):
        old, new = made[0][index], made[1][index]
        assert type(old) is type(new) is frozen.Client
        assert old.body('sys', 'user') == new.body('sys', 'user')
        assert old.call('sys', 'user') == new.call('sys', 'user')
        old.http.close(); new.http.close()


def test_prompt_hash_is_not_a_cross_run_reply_cache_and_completed_units_refuse_old_run(tmp_path):
    gateway = Gateway(completion())
    old, _ = make(tmp_path, gateway, configuration=p.MAIN_V8)
    new, value = make(tmp_path, gateway)
    for made in (old, new):
        recorder = endpoint(tmp_path, made).recorder(label='authored-cell')
        assert recorder('sys', 'user')['ok']
        assert recorder.sends[0]['request_sha256'] == _request_hash('sys', 'user')
    assert len(gateway.requests) == 2
    assert 'thinking' not in gateway.bodies[0] and gateway.bodies[1]['thinking'] == {'type': 'disabled'}
    unit = tmp_path / 'completed'
    identity = {'unit': 'D/authored-unit'}
    write_json(unit / 'unit.json', p.record('unit', 'engineering_fixture', {
        'run': 'older-run-and-snapshot', 'identity': identity, 'status': 'complete', 'result': {}}))
    with pytest.raises(ValueError, match='another run'):
        units.complete(unit, run=value[p.RECORD_HASH], identity=identity)
    old.http.close(); new.http.close()
