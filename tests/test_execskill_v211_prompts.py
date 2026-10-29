"""main-v4 frozen prompt dispatch and request identities; all replies are authored."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest

from skillopt.execskill import (audit, engineer, engineer_v28, engineer_v29, engineer_v291,
    engineer_v292, engineer_v293, engineer_v294, engineer_v295, engineer_v211 as v,
    instruction_start, manifest, profiles as p)
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

EXPECTED = {
    'searchqa': (6184, '547b6cbff515517556debde17e8e3ce4e367340189c168be509eed9e31c089dd', 6178, 'f197407b4f553586c5f7d63cafda41d2c9055ff641cfdf6cfa772c1f0c8e857d'),
    'officeqa': (6184, 'a0f3ff888215f903d7637123dc00a21022f87dc0f8b76f049ae2420434743b6d', 6178, '2e6421d7e1c1aa45537c53d7ad1130b5788037dd02754a738b4baa060b948518'),
    'livemath': (6226, '97c463e5eb9cb5dc1adb5a02b9591ebcaedef3b57c475ffd446fa66e123b75f1', 6220, '061a9c116ab6bb8edf92ade20882af63d6c8051540e977ea6e3802fc0e48aab4'),
    'spreadsheetbench': (6517, 'a2694d46fc981df4814cfdf0c46ddb8f44d7d7eaac0ff6ac4cbb2246f85ca592', 6511, '832c41a3e59e74948a29ad7f9aa25a5b56ec50e11612fd568dc57f8957c9d7d1'),
}


def refuse_legacy_maps(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError('main-v4 invoked a legacy system selector')
    for module in (engineer_v28, engineer_v29, engineer_v291, engineer_v292,
                   engineer_v293, engineer_v294, engineer_v295):
        monkeypatch.setattr(module, 'system', refused)
    monkeypatch.setattr(instruction_start, 'engineer_system', refused)


def authored(bench, train):
    ctx, _ = context(configuration=p.MAIN_V2_3, bench='officeqa', mode='train' if train else 'single')
    ctx = replace(ctx, configuration=p.MAIN_V4, bench=bench, routing_shared_worker=False,
                  card=instruction_start.pins()[bench]['text'])
    ctx.roles = WireRoles(['authored reply'])
    return ctx


@pytest.mark.parametrize('bench', v.BENCHES)
@pytest.mark.parametrize('train', [False, True])
def test_all_eight_literal_bytes_and_manifest_pins(bench, train):
    count, sha = EXPECTED[bench][2 if train else 0:4 if train else 2]
    text = v.system(bench, train=train)
    assert len(text.encode()) == count
    assert hashlib.sha256(text.encode()).hexdigest() == sha
    registered = manifest.prompt_sha(p.MAIN_V4)
    assert (registered['v2']['engineer'] if train else registered['engineer'])[bench] == sha
    assert text.count(instruction_start.ENGINEER_SENTENCE) == 1
    assert v.HOOKS[bench] in text


@pytest.mark.parametrize('bench', v.BENCHES)
@pytest.mark.parametrize('train', [False, True])
@pytest.mark.parametrize('purpose', v.PURPOSES)
def test_actual_wire_dispatch_never_calls_parent_maps_and_pins_rendered_requests(bench, train, purpose, monkeypatch):
    ctx = authored(bench, train)
    ctx.sheet['v211_prompt_pins'] = json.loads(json.dumps(manifest.prompt_sha(p.MAIN_V4)['v211']))
    refuse_legacy_maps(monkeypatch)
    user = {'request': purpose, 'bench': bench,
            'evidence': {'never_fires': {'count': 2}, 'empty_notes': {'count': 3}}}
    reply, call = engineer._ask(ctx, user, 'wire/' + purpose)
    assert reply == 'authored reply' and call
    wire = ctx.roles.wire[0]
    expected = v.system(bench, train=train, purpose=purpose, causes=user['evidence'])
    assert wire['system'] == expected
    if purpose == 'inert_repair':
        assert 'empty_notes, never_fires' in expected
        assert ', '.join(v.HOOK_NAMES[bench]) in expected
    record = ctx.sheet['v211_requests'][0]
    assert record['system_sha256'] == hashlib.sha256(wire['system'].encode()).hexdigest()
    assert record['user_sha256'] == hashlib.sha256(wire['user'].encode()).hexdigest()
    assert record['request_sha256'] == digest({'system': wire['system'], 'user': wire['user']})


@pytest.mark.parametrize('bench', v.BENCHES)
@pytest.mark.parametrize('train', [False, True])
def test_sealed_record_uses_actual_current_bench_prompt_without_legacy_maps(bench, train, monkeypatch):
    ctx = authored(bench, train)
    ctx.roles = WireRoles(([engineer_reply({'findings': []}, [])] if train else [])
        + [engineer_reply({'changes': []}, [])])
    refuse_legacy_maps(monkeypatch)
    _, record = engineer.run_train(ctx) if train else engineer.run(ctx)
    assert record['prompt_sha256'] == v.text_sha(v.system(bench, train=train))
    assert len(record['prompt_requests']) == 1
    assert record['prompt_requests'][0]['system_sha256'] == record['prompt_sha256']


@pytest.mark.parametrize('name,sha', [
    ('fix', 'f432eb1abe7a7e2a8bd5051e545fd783036a44dbb8909930c2d8c0da4ed1c0ec'),
    ('format_retry', '1c282c66f19d7f56a1c4423c4386ed6f0a5ba8e2fe72ca53371d84a9aed545da'),
    ('audit_fix', '5625daf483652dfb8f7848041a79c94f4564c40c844378865468aa6069318ef5'),
    ('fault_repair', '528deae528dcdfbc2b9e2f8766c065d63b15dd6efb95970d9c81137bf5ad0c1c'),
    ('inert_repair', '7421db461499aadc6dbae48e1dcac4665c34e65654e42c7aa23a1e298c54d9c1'),
    ('audit_policy', '5e86651b3421993bbfaeb10cfbfb57eaa3c6424096bf48095482fd320ee2b697'),
    ('audit_schema_A', '799803e96ea1b7506f1604e19938cc6c100da4f58f9eb5288f19c3da5e1d3b4b'),
    ('audit_schema_B', '731d90b8ca6ce850e10dc115d746f02d200261e610fbfd3402a29fbe23789157'),
    ('audit_schema_final', 'b7657ff23349e21c7ba8134cf3d34b86a6c18a575bb3f9c5f8f8ffb4a1c02283'),
    ('audit_format_retry', '6c97bda2c0aac1852cef204bee0b87a150e454a4ed7ec3c68ee77a0a525bd08b'),
])
def test_exact_repair_and_audit_material_hashes(name, sha):
    pin = v.pins()['materials'][name]
    assert pin['sha256'] == v.text_sha(pin['text']) == sha


def test_exact_audit_system_hashes_and_canonical_maps():
    pins = v.pins()
    expected = {'A': 'd93b82a7f7af8be02694dae503a7378958dbf0f49be0f04baa653a1cf7a5edd8',
                'B': 'f0125878bd1176261919f6d6be24db3e08103d6f0d24bc1b7b46a3026b2cc3fc',
                'final': '2522de54ae625d2fc55bdc57629dafe9e0d9d1bd520c843bac6546b9c116a694'}
    for bench in v.BENCHES:
        assert {key: row['sha256'] for key, row in pins['audit'][bench].items()} == expected
        assert all(audit.EPISODE_HISTORY_RULE not in row['text'] for row in pins['audit'][bench].values())
    for row in pins['maps'].values():
        assert row['sha256'] == digest(row['value'])
    assert pins['alfworld_audit'] == audit.prompt_pins(p.ALFWORLD_V11)
    assert 'example' in pins['maps']['format_retry_schema']['value']


def test_manifest_drift_refused_before_dispatch_and_call_budget_stops_without_pinning():
    ctx = authored('officeqa', True)
    ctx.sheet['v211_prompt_pins'] = deepcopy(v.pins())
    ctx.sheet['v211_prompt_pins']['systems']['officeqa']['train']['propose']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='sealed manifest'):
        engineer._ask(ctx, {}, 'propose')
    assert not ctx.roles.wire and not ctx.sheet.get('v211_requests')
    ctx.roles.calls = [{'label': 'engineer/' + ctx.label + '/spent'} for _ in range(ctx.calls_cap)]
    assert engineer._ask(ctx, {}, 'propose') == (None, None)
    assert not ctx.roles.wire and not ctx.sheet.get('v211_requests')


def test_inherited_nonengineer_pins_unchanged():
    child, parent = manifest.prompt_sha(p.MAIN_V4), manifest.prompt_sha(p.MAIN_V3)
    assert {key: value for key, value in child.items() if key not in ('engineer', 'v2', 'v211')} == {
        key: value for key, value in parent.items() if key not in ('engineer', 'v2')}
    assert {key: value for key, value in child['v2'].items() if key != 'engineer'} == {
        key: value for key, value in parent['v2'].items() if key != 'engineer'}


def test_complete_dispatch_and_inherited_text_maps_have_independent_canonical_pins():
    from skillopt.coevo5 import leakage
    from skillopt.execskill import research
    pins = v.pins()
    assert set(pins['map_sha256']) == set(pins) - {'map_sha256'}
    assert all(digest(pins[key]) == sha for key, sha in pins['map_sha256'].items())
    for row in pins['inherited'].values():
        assert row['sha256'] == v.text_sha(row['text'])
        assert row['canonical_text_sha256'] == digest(row['text'])
    assert pins['inherited']['analyst']['canonical_text_sha256'] == engineer.ANALYST_PROMPT_SHA256
    assert pins['inherited']['leakage']['text'] == leakage.ADJUDICATE_SYSTEM
    assert pins['inherited']['research/query']['text'] == research.QUERY_SYSTEM
    assert pins['inherited']['research/pick']['text'] == research.PICK_SYSTEM
    for purpose, text in research.CONCLUDE_SYSTEM.items():
        assert pins['inherited']['research/conclude/' + purpose]['text'] == text
    assert pins['materials']['format_retry_example']['text'] == pins['maps']['format_retry_schema']['value']['example']
    assert pins['maps']['workbook_preview']['value']['max_rows'] == 5
    assert json.loads(json.dumps(pins)) == pins


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS if not p.is_v211(name)])
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_prompt_accessor_keeps_historical_actual_dispatch_and_purpose_suffixes(configuration, mode):
    from types import SimpleNamespace
    bench = p.active_benches(configuration)[0]
    for purpose in v.PURPOSES:
        ctx = SimpleNamespace(configuration=configuration, bench=bench, mode=mode, spent=0,
            roles=WireRoles(['authored reply']), label='D/accessor', calls_cap=1, sheet={})
        engineer._ask(ctx, {'request': purpose}, 'wire/' + purpose)
        assert p.engineer_prompt(configuration, bench, mode, purpose) == ctx.roles.wire[0]['system']


@pytest.mark.parametrize('bench', v.BENCHES)
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_child_accessor_resolves_current_benchmark_and_every_purpose(bench, mode):
    for purpose in v.PURPOSES:
        assert p.engineer_prompt(p.MAIN_V4, bench, mode, purpose) == v.system(bench, train=mode == 'train', purpose=purpose)
    with pytest.raises(ValueError, match='Registered engineer mode'):
        p.engineer_prompt(p.MAIN_V4, bench, 'unknown')
