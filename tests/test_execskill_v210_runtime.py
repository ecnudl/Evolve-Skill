"""The imported v29 code and learned v23 code coexist only under the new explicit worker opt-in."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import chain, policy, profiles as p, smoke, v210_import
from skillopt.execskill.package import Package, Procedure
from skillopt.execskill.sandbox import client, worker
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

MARKER = 'main-v3-alfworld-v11'
LIMITS = {'address_space_mb': 2048, 'frame_bytes': 1 << 20}


def package():
    learner = Procedure('p-searchqa-1-1', 'searchqa', 'Counts public words.', ('applies', 'before_call'),
        'def applies(view):\n    return True\ndef before_call(view, state):\n    return {"facts": ["word count 2"]}\n',
        'engineering_fixture', max_note_chars=100, policy_version=policy.POLICY_VERSION_V23)
    imported = tuple(replace(Procedure.from_json(row['record']), evidence='engineering_fixture')
                     for row in v210_import.pins()['procedures'])
    return Package((learner,) + imported, 'G/s5-alfworld', 'engineering_fixture')


@pytest.mark.parametrize('version', [policy.POLICY_VERSION, policy.POLICY_VERSION_V23, policy.POLICY_VERSION_V24,
                                   policy.POLICY_VERSION_V25, policy.POLICY_VERSION_V28, policy.POLICY_VERSION_V29])
def test_historical_load_request_envelopes_are_exact_and_never_gain_marker(version):
    entries = [{'id': 'x', 'source': 'def applies(view):\n    return True\n', 'hooks': ['applies'],
                **({'policy_version': version} if version != policy.POLICY_VERSION else {})}]
    expected = {'op': 'load', 'package_sha256': 'a' * 64, 'policy_sha256': policy.policy_sha256(version=version),
                **({'policy_version': version} if version != policy.POLICY_VERSION else {}),
                'limits': LIMITS, 'procedures': entries}
    assert client._load_request(SimpleNamespace(sha256='a' * 64), entries, LIMITS) == expected
    assert client._load_request(SimpleNamespace(sha256='a' * 64), entries, LIMITS,
                                mixed_policy_bundle=MARKER) == expected


def test_v23_v29_union_loads_original_sources_only_with_explicit_marker():
    combined = package()
    entries = client._entries(combined)
    old = client._load_request(combined, entries, LIMITS)
    denied = worker.handle_load({**old, 'seq': 1}, {'loaded': None}, policy)
    assert denied == {'seq': 1, 'ok': False, 'error': 'malformed load request'}
    enabled = client._load_request(combined, entries, LIMITS, mixed_policy_bundle=MARKER)
    assert enabled == {**old, 'mixed_policy_bundle': MARKER}
    state = {'loaded': None}
    result = worker.handle_load({**enabled, 'seq': 1}, state, policy)
    assert result['ok'] and not result['rejected'] and result['loaded'] == list(combined.order)
    # Execute the compiled, original imported loop guard on authored public events.
    scope = {}
    exec(state['loaded']['p-alfworld-1-15'][0], scope)
    status = None
    for index in range(20):
        status = scope['alf_after_step']({'action': 'look', 'observation': 'Nothing happens'}, status)
    note = scope['alf_before_step']({}, status)
    assert 'look' in note['discourage']
    assert 'Steps used so far: 20 of 50.' in note['fields']['warnings']


def test_union_keeps_each_procedures_own_policy_instead_of_promoting_v23():
    combined = package()
    entries = client._entries(combined)
    entries[0]['source'] += '\n# ' + 'x' * 7000
    request = client._load_request(combined, entries, LIMITS, mixed_policy_bundle=MARKER)
    result = worker.handle_load({**request, 'seq': 1}, {'loaded': None}, policy)
    assert result['ok'] and combined.procedures[0].id not in result['loaded']
    assert len(result['rejected']) == 1 and result['rejected'][0]['id'] == combined.procedures[0].id
    assert result['rejected'][0]['reason'].startswith('policy:')
    assert set(result['loaded']) == set(combined.order[1:])


@pytest.mark.parametrize('other', [policy.POLICY_VERSION_V24, policy.POLICY_VERSION_V25, policy.POLICY_VERSION_V28])
def test_import_marker_does_not_port_other_feature_policy_families(other):
    combined = package()
    entries = client._entries(combined)
    entries[0]['policy_version'] = other
    request = {**client._load_request(combined, entries, LIMITS), 'mixed_policy_bundle': MARKER, 'seq': 1}
    assert worker.handle_load(request, {'loaded': None}, policy)['error'] == 'malformed load request'


def test_worker_option_is_explicit_and_validated_without_docker():
    fake = SimpleNamespace(binary=None)
    assert client.Worker(docker=fake).mixed_policy_bundle is None
    assert client.Worker(docker=fake, mixed_policy_bundle=MARKER).mixed_policy_bundle == MARKER
    with pytest.raises(ValueError, match='Unknown mixed-policy'):
        client.Worker(docker=fake, mixed_policy_bundle='all-policies')


@pytest.mark.parametrize('configuration,arms', [(p.BASELINE_V210, 0), (p.MAIN_V3, 1)])
def test_read_estimate_receipt_names_actual_item_count_and_card_procedure_arithmetic(tmp_path, monkeypatch,
                                                                                   configuration, arms):
    spec = {p.RECORD_HASH: 'a' * 64}
    monkeypatch.setattr(smoke, 'load', lambda path: spec)
    monkeypatch.setattr(smoke, 'waiver', lambda *args: None)
    per_cell = {bench: {'card': 100, 'procedure': 150, 'procedure_assumed': False} for bench in p.BENCHES}
    write_json(tmp_path / smoke.RESULT, p.record('smoke-result', 'smoke', {
        'spec': spec[p.RECORD_HASH], 'passed': True, 'required': ['SE6'], 'stages': {'SE6': 'pass'}}))
    write_json(tmp_path / smoke.STAGES_DIR / 'SE6.json', p.record('smoke-stage', 'smoke', {
        'stage': 'SE6', 'spec': spec[p.RECORD_HASH], 'result': {
            'passed': True, 'configuration': configuration, 'per_cell': per_cell, 'ratio': 1}}))
    found = chain.read_estimate_record(tmp_path, configuration)
    assert found['inputs']['n'] == {b: p.read_items(configuration, b) for b in p.BENCHES}
    assert found['inputs']['card_arms'] == 2 and found['inputs']['procedure_arms'] == arms
    assert found['inputs']['fired'] == {bench: '1' for bench in p.BENCHES}
    assert '2 x card_b + %d x proc_b' % arms in found['formula']
    assert found['value'] == sum(found['inputs']['n'].values()) * (200 + arms * 150)
