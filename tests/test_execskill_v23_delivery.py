"""Offline E1/E5 integration and configuration controls for the v2.3 delivery rules."""
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.code_delivery import extract_python as old_extract
from skillopt.execskill import code_delivery, judge, manifest, policy, protocol, smoke, solver, units
from tests.execskill_fakes import glm_roles

V23 = protocol.MAIN_V2_3


def test_v23_configuration_extends_every_table_without_changing_caps():
    tables = (protocol.CONFIG_STEP_CAPS, protocol.CONFIG_SCHEDULE_CELLS, protocol.CONFIG_ROLE_CAPS,
              protocol.CONFIG_GLM_CAP, protocol.CONFIG_CAP_FACTOR, protocol.COST_CHECK_PAUSES,
              protocol.PILOTS, protocol.TEST_READ_CELLS, protocol.STAGE_READ)
    for table in tables:
        assert table[V23] == table[protocol.MAIN_V2_2]
    assert protocol.RUN_ROOTS[V23] == '/data/execskill-20261025-main-v2-3'
    assert protocol.MAIN_V2_3_MANIFEST == '/data/execskill-20261025-main-v2-3-manifest.json'
    assert protocol.REAL_RUN_EVIDENCE[V23] == 'main_v2_3_real_run'
    assert [protocol.namespace_of(SimpleNamespace(extra={'configuration': V23}), c) for c in ('G', 'D')] == [
        'G-v2-3', 'D-v2-3']
    for table in (protocol.ENGINEER_MAX_TOKENS, protocol.TRIM_PAYLOADS, protocol.NORMALIZE_STRUCTURE,
                  protocol.IDENTICAL_REQUEST_REUSE, protocol.POLICY_VERSIONS, protocol.CODE_EXTRACTION,
                  protocol.MULTIPLE_PYTHON_BLOCKS, protocol.CHECK_NON_FIRING, protocol.ENGINEER_RECORDS):
        assert set(table) == set(protocol.CONFIGURATIONS)
    assert protocol.POLICY_VERSIONS[V23] == policy.POLICY_VERSION_V23
    for config in set(protocol.CONFIGURATIONS) - {V23}:
        assert protocol.ENGINEER_MAX_TOKENS[config] == 16384
        assert protocol.POLICY_VERSIONS[config] == policy.POLICY_VERSION
        assert protocol.CODE_EXTRACTION[config] == 'explicit-python-fences-v1'
        assert not protocol.IDENTICAL_REQUEST_REUSE[config]
        assert not protocol.CHECK_NON_FIRING[config]
        assert protocol.ENGINEER_RECORDS[config] == 'engineer'
    assert protocol.CHECK_NON_FIRING[V23]
    assert protocol.ENGINEER_RECORDS[V23] == 'engineer-v2-3-a2'
    assert set(protocol.MULTIPLE_PYTHON_BLOCKS.values()) == {'refuse'}
    assert manifest.prompt_sha(V23)['v2']['engineer'] != manifest.prompt_sha(protocol.MAIN_V2_2)['v2']['engineer']
    assert manifest.role_settings(V23)['engineer_propose_max_tokens'] == 32768


@pytest.mark.parametrize('reply,kind', [
    ("Let's produce the code.```PyThOn\nprint(1)\n```", 'prose_prefixed_opening_fence'),
    ('```python\nprint(1)\n```\n```\n\n', 'trailing_fence_only_lines'),
])
def test_e5_new_cases_have_unchanged_source_spans_and_separate_kinds(reply, kind):
    old = old_extract(reply)
    new = code_delivery.extract_python(reply)
    assert old['status'] == 'unknown' and old['reason'] == 'unclosed_fence'
    assert new['status'] == 'available' and kind in new['kinds']
    assert new['code'] == reply[slice(*new['span'])] == 'print(1)\n'
    assert new['source_sha256'] == old['source_sha256']
    assert old_extract(reply) == old  # v1 never changes on the same inputs
    assert solver._extract(reply, 'explicit-python-fences-v1')[0] is None
    assert solver._extract(reply, code_delivery.VERSION)[0] == 'print(1)\n'
    assert judge.select_answer('spreadsheetbench', reply)[1] == 'none'
    assert judge.select_answer('spreadsheetbench', reply, configuration=V23) == ('print(1)\n', 'official')


def test_e5_multiple_blocks_refuse_by_default_last_is_explicit():
    reply = '```python\nx=1\n```\n```PY\nx=2\n```'
    for extract in (old_extract, code_delivery.extract_python):
        assert extract(reply)['reason'] == 'multiple_python_blocks'
    last = code_delivery.extract_python(reply, multiple='last')
    assert last['code'] == 'x=2\n' and last['candidate_kind'] == 'last_explicit_python'
    assert last['kinds'] == ['last_explicit_python_block']
    assert solver._extract(reply, code_delivery.VERSION, multiple='last')[0] == 'x=2\n'
    with pytest.raises(ValueError):
        code_delivery.extract_python(reply, multiple='best')


def test_e5_inline_fences_in_prose_never_start_or_close_blocks():
    reply = 'A prose ``` fragment.\n```python\ns = "literal ``` text"\n```\nA prose ``` fragment.'
    assert code_delivery.extract_python(reply)['code'] == 's = "literal ``` text"\n'
    assert code_delivery.extract_python(reply)['kinds'] == []
    assert code_delivery.extract_python('Use `x`.```PY\nx=1\n```')['code'] == 'x=1\n'
    assert old_extract(reply)['code'] == code_delivery.extract_python(reply)['code']
    assert code_delivery.extract_python('```python\nx=1\n```\n```\ntrailing text')['reason'] == 'unclosed_fence'


def test_e1_nominal_and_reservation_bounds_are_per_call(tmp_path):
    frozen, script = glm_roles(tmp_path, ['proposal', 'fix', 'analysis'])
    frozen.endpoint.client = script.client
    roles = units.roles(frozen.endpoint, configuration=V23)
    for label, bound in [('propose', 32768), ('fix', 16384), ('analyst', 16384)]:
        roles.plain('engineer', 'system', '{}', label=label, max_tokens=bound)
        assert roles.calls[-1]['max_tokens'] == bound
        assert roles.calls[-1]['sends'][0]['max_tokens'] == bound
        assert script.provider.requests[-1]['max_tokens'] == bound
    assert frozen.endpoint.max_tokens == frozen.endpoint.client.max_tokens == 16384
    assert type(units.roles(frozen.endpoint, configuration=protocol.MAIN_V2_2)) is type(frozen)


def test_e1_smoke_projection_prices_new_prompt_and_output_reservation():
    measured = {'engineer': {'calls': 1, 'per_call': 100, 'request_bytes': 100}}
    old = smoke.glm_projection(measured, protocol.MAIN_V2_2)
    new = smoke.glm_projection(measured, V23)
    scopes = [key for key in old if key.endswith(':role:engineer')]
    assert scopes
    assert all(new[key]['reservation'] > old[key]['reservation'] for key in scopes)


def test_v23_manifest_seals_prompt_policy_output_bound_and_extraction(tmp_path, monkeypatch):
    from skillopt.execskill import routes
    from tests.test_execskill_manifest import MEASURED, fake_environment, given
    from skillopt.validator_pilot.api import digest

    # Route pins are a separate fixture family; this fixture constructs no client or sandbox.
    monkeypatch.setattr(routes, 'check_pins', lambda *a, **k: None)
    values = given(tmp_path)
    made = manifest.make(tmp_path / 'manifest.json', evidence='engineering_fixture', configuration=V23,
                         environment_found=fake_environment(), measured=MEASURED, **values)
    assert made['version'] == protocol.kind('manifest-v2-3')
    assert made['clients']['roles']['engineer_propose_max_tokens'] == 32768
    assert made['sandbox']['policy_sha256'] == policy.policy_sha256(version=policy.POLICY_VERSION_V23)
    assert made['runtime']['spreadsheetbench']['code_extraction_version'] == code_delivery.VERSION
    assert made['runtime']['spreadsheetbench']['multiple_python_blocks'] == 'refuse'
    altered = {**made, 'runtime': {**made['runtime'], 'spreadsheetbench': {
        **made['runtime']['spreadsheetbench'], 'multiple_python_blocks': 'last'}}}
    altered[protocol.RECORD_HASH] = digest({k: v for k, v in altered.items() if k != protocol.RECORD_HASH})
    with pytest.raises(ValueError, match='multiple-block'):
        manifest.check(altered)
    assert values['clients']['roles'] == manifest.ROLES and values['runtime']['spreadsheetbench'] == {}


def test_e5_solver_delivery_reaches_native_only_for_the_new_configuration(tmp_path, monkeypatch):
    from tests.test_execskill_solver import PROGRAM, SHEET_RUNTIME, CARD, EMPTY
    from tests.execskill_fakes_env import FakeNative, Script
    from tests.fixtures.execskill.items import spreadsheetbench_items

    native = FakeNative().install(monkeypatch)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    reply = 'Here is the code.' + PROGRAM + '\n```'
    before = solver.solve('spreadsheetbench', item['public'], CARD, EMPTY, Script([reply]), runtime=SHEET_RUNTIME)
    assert before['status'] == 'unknown' and not native.prechecks and not native.cases
    after = solver.solve('spreadsheetbench', item['public'], CARD, EMPTY, Script([reply]), runtime={
        **SHEET_RUNTIME, 'code_extraction_version': protocol.CODE_EXTRACTION[V23], 'multiple_python_blocks': 'refuse'})
    assert after['status'] == 'available' and len(native.prechecks) == 1 and native.cases
    assert after['code_delivery']['version'] == code_delivery.VERSION
    assert set(after['code_delivery']['kinds']) == {'prose_prefixed_opening_fence', 'trailing_fence_only_lines'}
