"""S3c exercises the real check/repair/cache path with authored offline replies."""
from dataclasses import replace
import json

import pytest

from skillopt.execskill import (alf_smoke, budgets, engineer, engineer_v291, profiles as p,
                               units, v29_smoke, zebra_smoke)
from tests.test_execskill_zpc_pipeline import offline
from tests.test_execskill_v28_execution import SeedWorkers
from tests.test_execskill_v29_manifest_smoke import FixtureJudge
from tests.test_execskill_v27_zebra_smoke_review import made as zebra_made
from tests.test_execskill_alf_v1_smoke_review import made as alf_made

PROFILES = [(p.ZEBRA_PC_V8, zebra_made, zebra_smoke), (p.ALFWORLD_V5, alf_made, alf_smoke)]


def prepare(tmp_path, monkeypatch, configuration, make, response):
    setting, services, solver, roles = make(tmp_path, monkeypatch, response='empty')
    setting = replace(setting, extra={**setting.extra, 'configuration': configuration, 'route': 'B'})
    seeded = SeedWorkers()
    def workers(package, **options):
        options.pop("tag", None)
        return seeded(package, **options)
    services = replace(services, workers=workers)
    original = roles.replies
    def authored(system, payload):
        if payload.get('request') == 'fault_repair':
            if response == 'unparseable':
                return 'Authored malformed reply without a change.'
            entry = dict(payload['change'])
            source = entry.pop('source')
            if response == 'fixed':
                source = ('def alf_before_step(view, state):\n'
                          '    return {"fields": {"facts": [view["initial_observation"]]}, "discourage": []}\n'
                          if p.is_alfworld(configuration) else
                          'def before_call(view, state):\n'
                          '    return {"facts": ["The public puzzle lists named columns."]}\n')
            return '```json\n' + json.dumps({'changes': [entry]}) + '\n```\n```python\n' + source + '```'
        if payload.get('request') == 'propose':
            return '```json\n{"changes": []}\n```'
        return original(system, payload)
    roles.replies = authored
    return setting, services, solver, roles


@pytest.mark.parametrize('configuration,make,module', PROFILES)
@pytest.mark.parametrize('response', ['unchanged', 'fixed', 'unparseable'])
def test_s3c_one_real_endpoint_call_evidence_check_and_cached_result(
        tmp_path, monkeypatch, configuration, make, module, response):
    setting, services, solver, roles = prepare(tmp_path, monkeypatch, configuration, make, response)
    result = v29_smoke._s3c(setting, services)
    proposal = result['proposal']
    repair = proposal['fault_repair']
    assert repair['triggered'] and repair['faulted'] == repair['fired'] > 0
    assert len(repair['calls']) == 1 and result['role_measurements']['engineer']['calls'] == 1
    sent = repair['calls'][0]
    evidence = sent['request']['evidence']
    signature = evidence['signatures'][0]
    assert signature['line'] == 2 and signature['source_line']
    assert signature['exc_type'] == ('AttributeError' if p.is_alfworld(configuration) else 'IndexError')
    assert signature['message'] and signature['source_line'] == sent['request']['change']['source'].splitlines()[1]
    assert evidence['example_call']['arguments']['state'] is None
    assert evidence['example_call']['arguments']['view']
    if p.is_alfworld(configuration):
        assert evidence['example_call']['step'] == 0
    assert result['passed'] is (response != 'unparseable')
    assert sent['parsed'] is sent['checked'] is (response != 'unparseable')
    if response == 'unchanged':
        assert result['passed'] and result['faulted_after'] == repair['faulted']
        assert sent['kept'] is False  # a quality failure is not the S3c pass gate
    elif response == 'fixed':
        assert result['faulted_after'] == 0 and sent['kept']
    before = len(solver.requests), len(roles.seen)
    assert v29_smoke._s3c(setting, services) == result
    assert (len(solver.requests), len(roles.seen)) == before


@pytest.mark.parametrize('configuration,make,module', PROFILES)
@pytest.mark.parametrize('response', ['unchanged', 'unparseable'])
def test_complete_s3_includes_s3c_gate_and_aggregates_its_engineer_measurements(
        tmp_path, monkeypatch, configuration, make, module, response):
    setting, services, solver, roles = prepare(tmp_path, monkeypatch, configuration, make, response)
    bench = p.active_benches(configuration)[0]
    scope = budgets.solver_scopes('D', bench, 1, 'confirm')[-1]
    setting.budget.declare({scope: budgets.chain_caps('D', configuration)[scope]})
    judges = {name: FixtureJudge() for name in ('G', 'D')}
    monkeypatch.setattr(units, 'audit_judges', lambda *args: judges)
    result = module._s3(setting, services)
    assert result['S3a']['passed'] and result['S3b']['passed']
    assert result['passed'] is (response == 'unchanged')
    assert result['failed_substages'] == ([] if response == 'unchanged' else ['S3c'])
    assert result['role_measurements']['engineer']['calls'] == (
        result['S3b']['role_measurements']['engineer']['calls'] + 1)
    assert result['role_measurements']['engineer']['tokens'] == (
        result['S3b']['role_measurements']['engineer']['tokens'] +
        result['S3c']['role_measurements']['engineer']['tokens'])
    before = len(solver.requests), len(roles.seen), sum(len(judge.calls) for judge in judges.values())
    assert module._s3(setting, services) == result
    assert (len(solver.requests), len(roles.seen), sum(len(judge.calls) for judge in judges.values())) == before


@pytest.mark.parametrize('missing', ['exc_type', 'message', 'line', 'source_line', 'source_context'])
def test_s3c_does_not_pass_incomplete_exception_evidence(missing):
    evidence = {'fired': 1, 'faulted': 1, 'triggered': True,
        'signatures': [{'exc_type': 'IndexError', 'message': 'list index out of range', 'line': 2,
                        'source_line': '    view["question"].splitlines()[999]',
                        'source_context': [{'line': 2, 'text': 'Authored line.'}]}],
        'example_call': {'hook': 'before_call', 'step': None, 'arguments': {'view': {}, 'state': None}}}
    assert v29_smoke._fault_evidence_ok(evidence, 'zebralogic')
    evidence['signatures'][0].pop(missing)
    assert not v29_smoke._fault_evidence_ok(evidence, 'zebralogic')
