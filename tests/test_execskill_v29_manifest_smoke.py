"""Offline synthetic v2.9 manifest, budget and complete lean-smoke wiring."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import re
from types import SimpleNamespace

import pytest

from skillopt.execskill import (audit, budgets, client, engineer, engineer_v29, manifest, profiles as p,
                               routes, smoke, units, v29_limits, v29_smoke, zebra_smoke, alf_smoke)
from tests.test_execskill_v28_profile import tmp_path
from tests.test_execskill_zpc_pipeline import offline
from tests.test_execskill_v27_zebra_smoke_review import made as zebra_made
from tests.test_execskill_alf_v1_smoke_review import made as alf_made


class FixtureJudge:
    def __init__(self, flag=False):
        self.calls, self.flag = [], flag

    def plain(self, role, system, user, *, label, max_tokens):
        assert max_tokens == 8192
        self.calls.append({'sends': [{'charged': 100, 'receipt': {'usage': {'prompt_tokens': 80,
                                                                          'completion_tokens': 20}}}]})
        if system == audit.A_SYSTEM:
            rows = []
            for tid, text in re.findall(r'^(T\d+): (.*)$', user, re.M):
                bad = self.flag and text in ('All clues were parsed.',
                                            'All receptacles named in the room description have been visited.')
                rows.append({'t': tid, 'verdict': 'P1' if bad else 'ok', 'reason': 'Authored fixture verdict.',
                             'false_when': 'At reset before any visit or complete parsing.' if bad else ''})
            return json.dumps({'templates': rows, 'other': []})
        rows = []
        for sid, block in re.findall(r'Situation (S\d+) (.*?)(?=\nSituation |\nReturn only JSON:)', user, re.S):
            rows.append({'s': sid, 'notes': [{'n': nid, 'truth': 'unverifiable', 'policy': 'ok',
                                            'evidence': '', 'reason': 'Synthetic reviewer.'}
                                           for nid in re.findall(r'^(N\d+) \[', block, re.M)]})
        return json.dumps({'situations': rows, 'program': {'verdict': 'ok', 'reason': ''}})


@pytest.mark.parametrize('configuration,bench,per_audit,calls', [
    (p.ZEBRA_PC_V7, 'zebralogic', 5, 600), (p.ALFWORLD_V4, 'alfworld', 6, 720)])
def test_caps_and_prompt_pins_cover_every_new_consumer(configuration, bench, per_audit, calls):
    pins = manifest.prompt_sha(configuration)['v29']
    for family in pins.values():
        for pin in family.values():
            if isinstance(pin['text'], str):
                assert pin['sha256'] == hashlib.sha256(pin['text'].encode()).hexdigest()
    features = manifest.outcome_engineer_features(configuration)
    assert features['lexicon'] == 'log_only' and features['applies'] == 'optional_default_true'
    assert features['audit']['judges']['D']['model'] == client.NORTHGATE_MODEL
    assert features['audit']['judges']['D']['response_model_ids'] == sorted(client.NORTHGATE_RESPONSE_MODEL_IDS)
    assert features['audit']['limits']['judge_max_tokens'] == 8192
    assert v29_limits.prompts_per_audit(bench) == per_audit
    assert v29_limits.judge_calls(p, bench) == calls
    roles = smoke.max_role_calls(configuration)
    assert roles['audit_g'] == roles['audit_d'] == calls
    assert roles['engineer'] == 6 * (26 + 4)
    assert roles['leakage'] == 90
    caps = budgets.chain_caps('D', configuration)
    assert all(scope in caps for scope in (budgets.audit_scopes('D', 'G', bench, 1)[-1],
        budgets.audit_scopes('D', 'D', bench, 1)[-1], budgets.solver_scopes('D', bench, 1, 'confirm')[-1]))
    assert p.CONFIG_SCHEDULE_CELLS[configuration][bench]['confirm'] == {bench: (0, 480)}
    measured = {role: {'calls': 1, 'tokens': 100, 'per_call': 100, 'request_bytes': 2000} for role in roles}
    projected = smoke.glm_projection(measured, configuration)
    assert projected[budgets.audit_scopes('D', 'D', bench, 1)[-1]]['settled'] == calls * 100
    scopes = zebra_smoke._scope_cells('D', configuration)
    assert scopes[budgets.solver_scopes('D', bench, 1, 'confirm')[-1]] == [{bench: (0, 480)}]


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V7, p.ALFWORLD_V4])
def test_manifest_solver_config_never_selects_elucid(configuration, tmp_path):
    block = manifest.solver_block('D', env_path=tmp_path / 'not-read.env', branch='N', longest=256,
                                  configuration=configuration)
    assert block['backend'] == 'northgate' and block['url_host'] == client.NORTHGATE_HOST
    pin = routes.pin('D', 'B', env_path=tmp_path / 'not-read.env', solver_block=block, configuration=configuration)
    m = {'configuration': configuration, 'clients': {'solver': {'D': block}, 'routes': {'D': {'B': pin}}}}
    assert manifest.solver_config(m, 'D', p.active_benches(configuration)[0])['route'] == 'B'
    with pytest.raises(ValueError, match='northgate'):
        manifest.solver_config(m, 'D', p.active_benches(configuration)[0], 'A')


@pytest.mark.parametrize('configuration,make,module', [(p.ZEBRA_PC_V7,zebra_made,zebra_smoke),
                                                     (p.ALFWORLD_V4,alf_made,alf_smoke)])
@pytest.mark.parametrize('flag', [False, True])
def test_complete_s3_records_real_audit_agreement_and_unused_confirmation(
        tmp_path, monkeypatch, configuration, make, module, flag):
    setting, services, solver, roles = make(tmp_path, monkeypatch, response='empty')
    setting = replace(setting, extra={**setting.extra, 'configuration': configuration, 'route': 'B'})
    scope = budgets.solver_scopes('D', p.active_benches(configuration)[0], 1, 'confirm')[-1]
    setting.budget.declare({scope: budgets.chain_caps('D', configuration)[scope]})
    judges = {name: FixtureJudge(flag) for name in ('G','D')}
    monkeypatch.setattr(units, 'audit_judges', lambda *args: judges)
    original = roles.replies
    roles.replies = lambda system, payload: ('```json\n{"changes": []}\n```'
        if system == engineer_v29.system(configuration, train=True) else original(system, payload))
    value = module._s3(setting, services)
    assert value['passed'], value['S3a']
    assert value['S3a']['proposal']['audit']['available'] == {'G': True, 'D': True}
    assert value['S3a']['proposal']['false_template_confirmed'] == flag
    assert value['S3a']['confirm']['confirm']['items'] == 2
    assert value['S3a']['confirm']['confirm']['exercise'] is True
    assert value['S3a']['decision_used_for_adoption'] is False
    assert value['S3a']['proposal']['audit']['sampling']['situations']
    assert {'audit_g', 'audit_d'} <= set(value['role_measurements'])
    before = len(solver.requests), sum(len(j.calls) for j in judges.values())
    assert module._s3(setting, services) == value
    assert before == (len(solver.requests), sum(len(j.calls) for j in judges.values()))


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V7, p.ALFWORLD_V4])
def test_complete_manifest_pins_exact_practice_ids_prompts_and_models(tmp_path, monkeypatch, configuration):
    from skillopt.continual_eval.core import write_json
    from skillopt.execskill import confirm
    from tests.test_execskill_alf_v1_profile import alf_manifest
    from tests.test_execskill_zpc_orchestration import made
    from tests.test_execskill_manifest import MEASURED, fake_environment
    from tests.test_execskill_v29_confirm import alf_pool
    alf = p.is_alfworld(configuration)
    before = (alf_manifest if alf else made)(tmp_path, monkeypatch)
    given = {key: deepcopy(before[key]) for key in manifest.GIVEN}
    given['data']['launchable_chains'] = ['D']
    bench = p.active_benches(configuration)[0]
    if alf:
        rows = alf_pool()
        pool = tmp_path / 'new-practice-pool.json'
        write_json(pool, rows)
        pin = {'path': str(pool), 'sha256': hashlib.sha256(pool.read_bytes()).hexdigest()}
        given['data']['pools'][bench] = pin
        old = given['data'].pop('alfworld_v1')
        given['data']['alfworld_v4'] = {**old, 'pool': pin}
        from skillopt.execskill import alf_confirm_views, supply
        from skillopt.validator_pilot.api import digest
        confirm_pin = confirm.identity(configuration, rows)
        runtime_sha = digest(given['runtime'][bench])
        view = supply.routing_view('Authored room.\nYour task is to: inspect the fixture.', ['look'])
        given['data']['alf_confirm_views'] = p.record(alf_confirm_views.KIND, 'engineering_fixture', {
            'configuration': configuration, 'preparation': old['preparation'], 'pool': pin,
            'source': {'supply_sha256': 'a' * 64, 'original_views_sha256': 'b' * 64,
                       'views_runtime_sha256': runtime_sha, 'pool_export_sha256': 'c' * 64},
            'runtime_sha256': runtime_sha, 'confirm': confirm_pin, 'ids': confirm_pin['ids'],
            'confirm_ids_sha256': confirm_pin['ids_sha256'],
            'views': {key: {'view': view, 'view_sha256': digest(view)} for key in confirm_pin['ids']}})
    given['clients']['solver'] = {name: manifest.solver_block(name, env_path=old['env_path'],
        branch='N' if name == 'D' else None, longest=512 if name == 'D' else None,
        configuration=configuration) for name, old in given['clients']['solver'].items()}
    given['clients']['routes'] = {'D': {'B': routes.pin('D', 'B', env_path=tmp_path / 'unused-route.env',
        solver_block=given['clients']['solver']['D'], configuration=configuration)}}
    value = manifest.make(tmp_path / 'new-manifest.json', evidence='engineering_fixture', configuration=configuration,
                          measured=MEASURED, environment_found=fake_environment(), **given)
    assert value['version'] == p.kind('manifest-v2-9')
    assert value['data']['confirm'] == confirm.identity(configuration, manifest._items(
        given['data']['pools'][bench], bench))
    assert len(value['data']['confirm']['ids']) == 40
    assert manifest.check(value) == value
    assert value['prompt_sha'] == manifest.prompt_sha(configuration)
    assert value['caps'] == budgets.caps(configuration)
    value['data']['confirm']['ids'].pop()
    payload = {key: data for key, data in value.items() if key not in ('version','evidence',p.RECORD_HASH)}
    with pytest.raises(ValueError, match='forty'):
        manifest.check(p.record('manifest-v2-9', 'engineering_fixture', payload))


def test_judges_use_separate_scopes_and_fresh_capped_client_copies(monkeypatch):
    clients = {'glm-5.3': SimpleNamespace(model='glm-5.3', max_tokens=16384),
               p.CHAINS['D']: SimpleNamespace(model=p.CHAINS['D'], max_tokens=16384, route='B')}
    calls = []
    setting = SimpleNamespace(extra={'configuration': p.ZEBRA_PC_V7}, clients=lambda model, bench: clients[model])
    def endpoint(setting, scopes, *, client, max_tokens_bound):
        calls.append((scopes, client, max_tokens_bound))
        return SimpleNamespace(client=client)
    monkeypatch.setattr(budgets, 'endpoint', endpoint)
    made = units.audit_judges(setting, 'D', 'zebralogic', 1)
    assert set(made) == {'G','D'}
    assert [row[0][-1] for row in calls] == ['D:xs:zebralogic:1:role:audit_g', 'D:xs:zebralogic:1:role:audit_d']
    assert all(bound == copied.max_tokens == 8192 for _, copied, bound in calls)
    assert all(client.max_tokens == 16384 for client in clients.values())
    clients[p.CHAINS['D']].route = 'A'
    with pytest.raises(ValueError, match='northgate'):
        units.audit_judges(setting, 'D', 'zebralogic', 1)


def test_false_template_information_requires_the_authored_false_statement():
    result = {'confirmed': [{'kind': 'program', 'verdict': 'P6'}], 'sampling': {'situations': []},
              'templates': {'p': {'templates': [{'t': 'T1', 'text': 'All clues were parsed.'},
                                               {'t': 'T2', 'text': 'The public task sentence.'}]}}}
    assert not v29_smoke.false_template_confirmed(result, 'zebralogic')
    result['confirmed'] = [{'kind': 'template', 'procedure': 'p', 't': 'T2'}]
    assert not v29_smoke.false_template_confirmed(result, 'zebralogic')
    result['confirmed'][0]['t'] = 'T1'
    assert v29_smoke.false_template_confirmed(result, 'zebralogic')


def test_smoke_measurements_count_identical_audits_in_separate_units_once_each():
    request = {'prompt_sha256': 'a'*64, 'system': 'system', 'user': 'user', 'reused': False,
               'tokens': {'charged': 100}, 'retries': []}
    pair = {'requests': {'G': request, 'D': request}}
    unit = {'changes': [{'audits': [pair]}], 'audits': [pair]}
    measured = v29_smoke._audit_measurements(unit, deepcopy(unit))
    assert all(row['calls'] == 2 and row['tokens'] == 200 for row in measured.values())
