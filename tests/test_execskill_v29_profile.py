"""v2.9 registration and northgate-only probe; authored offline identities."""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import json

import pytest

from skillopt.execskill import client, policy, profiles as p, routes, v29_limits, v29_route_probe
from skillopt.execskill.package import Procedure
from tests.test_execskill_v29_runtime import procedure
from tests.test_execskill_zpc_pipeline import offline


@pytest.mark.parametrize('config,parent,tag,bench', [
    ('zebra-pc-v7', 'zebra-pc-v6', 'zpc7', 'zebralogic'),
    ('alfworld-v4', 'alfworld-v3', 'alf4', 'alfworld')])
def test_registration_identity_and_inherited_features(config, parent, tag, bench):
    assert p.FEATURE_FAMILIES[config] == 'v2.9'
    assert all(fn(config) for fn in (p.is_v23, p.is_v24, p.is_v25, p.is_v26, p.is_v27, p.is_v28, p.is_v29))
    assert p.active_benches(config) == (bench,) and p.launchable_chains(config) == ('D',)
    assert p.RUN_ROOTS[config] == '/data/execskill-20261027-' + config
    assert p.CHAIN_NAMESPACES[config] == {'G': 'G-' + tag, 'D': 'D-' + tag}
    assert p.POLICY_VERSIONS[config] == policy.POLICY_VERSION_V29
    assert p.ENGINEER_RECORDS[config] == 'engineer-v2-9'
    assert p.ENGINEER_CALL_BUDGETS[config] == 16 and p.TRAIN_ENGINEER_CALL_BUDGETS[config] == 26
    for key in ('SLICES',):
        assert getattr(p, key)[bench]['run'][0] == 60
    for key in ('ACCEPT_RULES', 'ENGINEER_MAX_TOKENS', 'TEST_READ_CELLS', 'STAGE_READ', 'TRIM_PAYLOADS'):
        assert getattr(p, key)[config] == getattr(p, key)[parent]
    assert p.TRAIN_ROUNDS == 6 and p.TRAIN_PATIENCE == 2 and p.TRAIN_FIXES == 3
    for kind in ('engineer', 'manifest', 'procedure'):
        value = p.record(kind + '-v2-9', p.REAL_RUN_EVIDENCE[config], {})
        assert p.verified(value, kind) == value
    assert p.CONFIGURATIONS[config] is not p.CONFIGURATIONS[parent]
    assert p.CONFIG_STEP_CAPS[config][bench]['confirm'] > 0
    assert p.CONFIG_SCHEDULE_CELLS[config][bench]['confirm'] == {bench: (0, 480)}
    assert set(v29_limits.JUDGE_ROLES) <= set(p.CONFIG_ROLE_CAPS[config])


def test_v29_policy_is_canonical_and_sandbox_rules_inherited():
    assert policy.source_limit(policy.POLICY_VERSION_V29) == 24_000
    assert json.loads(policy.POLICY_PATH_V29.read_text()) == policy.POLICY_V29
    assert hashlib.sha256(policy.POLICY_PATH_V29.read_bytes()).hexdigest() == policy.policy_sha256(version=policy.POLICY_VERSION_V29)
    ignored = {'version', 'registration'}
    assert {k: v for k, v in policy.POLICY_V29.items() if k not in ignored} == {
        k: v for k, v in policy.POLICY_V28.items() if k not in ignored}
    source = 'WORDS = frozenset(["alpha", "beta"])\ndef before_call(view, state):\n    return {}\n'
    assert not policy.check(source, version=policy.POLICY_VERSION_V29)
    assert Procedure.from_json(procedure().to_json()) == procedure()


def test_only_two_v29_profiles_and_exact_freshness():
    assert {name for name in p.CONFIGURATIONS if p.is_v29(name) and not p.is_v291(name)} == {'zebra-pc-v7', 'alfworld-v4'}
    assert p.ACCEPT_FRESHNESS[p.ZEBRA_PC_V7] == 'zebra_split_v1_slices_reused_accept_used_four_times_plus_ub_probe'
    assert p.ACCEPT_FRESHNESS[p.ALFWORLD_V4] == 'alfworld_split_v1_slices_reused_acceptance_used_once'
    assert {name: value for name, value in p.CONFIRM_FRESHNESS.items() if not p.is_v291(name)} == {
        p.ZEBRA_PC_V7: 'zebra_split_v1_confirm_spare_probe_smoke_first_use',
        p.ALFWORLD_V4: 'alfworld_split_v1_confirm_spare_rooms_first_use'}
    assert p.ZEBRA_PC_V7_MANIFEST == p.ZEBRA_PC_V7_ROOT + '-manifest.json'
    assert p.ALFWORLD_V4_MANIFEST == p.ALFWORLD_V4_ROOT + '-manifest.json'


@pytest.mark.parametrize('config', ('zebra-pc-v7', 'alfworld-v4'))
def test_northgate_is_the_start_route_and_route_switches_are_not_implicitly_authorized(tmp_path, monkeypatch, config):
    assert routes.current(tmp_path, configuration=config) == client.ROUTE_B
    assert routes.check_bound(tmp_path, 'B', run='fixture', configuration=config) == 'B'
    assert routes.current(tmp_path, configuration='zebra-pc-v6') == client.ROUTE_A
    monkeypatch.setattr(routes, 'history', lambda *args, **kwargs: [{'to': 'A'}])
    with pytest.raises(ValueError, match='new owner decision'):
        routes.current(tmp_path, configuration=config)


@pytest.mark.parametrize('config', ('zebra-pc-v7', 'alfworld-v4'))
def test_cli_accepts_v29_without_changing_old_defaults(config):
    from scripts.run_execskill import parser
    command = 'zpc-smoke' if p.is_zebra(config) else 'alf-smoke'
    args = parser().parse_args([command, '--manifest', 'fixture.json', '--configuration', config,
                               '--chain', 'D', '--stage', 'S1'])
    assert args.configuration == config


@pytest.mark.parametrize('config,capped', [('zebra-pc-v7',False), ('alfworld-v4',True)])
def test_s1_probe_measures_northgate_longest_with_no_route_a_call(tmp_path, monkeypatch, config, capped):
    bench = p.active_benches(config)[0]
    made, requests = SimpleNamespace(route='B'), []
    def clients(model, bench):
        assert model == p.CHAINS['D'] and bench == p.active_benches(config)[0]
        return made
    setting = SimpleNamespace(extra={'configuration': config}, clients=clients, branch='N', longest=256,
                              root=tmp_path, run='fixture', evidence='engineering_fixture')
    class Endpoint:
        def recorder(self, label):
            return SimpleNamespace(sends=[])
        def send(self, system, user, recorder):
            requests.append((system, user))
            recorder.sends.append({'request_sha256': str(len(requests)), 'charged': 50})
            return {'ok': not capped, 'returned_model': client.NORTHGATE_MODEL,
                    'response': 'Authored nonempty probe output', 'finish_reason': 'length' if capped else 'stop',
                    'error_type': 'finish_length' if capped else None, 'reasoning_chars': 0,
                    'usage': {'completion_tokens': len(requests) * 30, 'prompt_tokens': 20}}
    def endpoint(setting, scopes, *, client, max_tokens_bound):
        assert client is made and scopes[-1] == 'D:confirm'
        assert max_tokens_bound == 4 * p.solver_tokens(p.CHAINS['D'], bench)
        return Endpoint()
    monkeypatch.setattr(v29_route_probe.budgets, 'endpoint', endpoint)
    def run_unit(root, *, work, **kwargs):
        attempt = tmp_path / 'attempt'
        attempt.mkdir()
        return {'result': work(attempt)}
    monkeypatch.setattr(v29_route_probe.units, 'run_unit', run_unit)
    result = v29_route_probe.measure(setting)
    assert result['longest'] == 90 and result['calls'] == 3 and result['route'] == 'B'
    assert result['branch'] == 'N' and result['tokens'] == 150
    assert len(requests) == 3 and all(pair == requests[0] for pair in requests)
    assert {row['returned_model'] for row in result['receipts']} == {client.NORTHGATE_MODEL}
    assert all(row['capped_measurement'] is capped for row in result['receipts'])
    assert (tmp_path / 'attempt/probe-2.json').is_file()
