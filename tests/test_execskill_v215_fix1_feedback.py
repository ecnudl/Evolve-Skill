"""Informational display fitting/fallback regressions over authored inputs only."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from skillopt.coevo5.roles import message_bytes
from skillopt.execskill import audit, diagnostics, diagnostics_feedback as d, engineer, profiles as p, step
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import PUBLIC, context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v291_engineer import GOOD, run
from tests.test_execskill_v215_feedback import CHILD, record
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def envelope(task='run'):
    return d.build([{'task_id': task, 'records': [record('Unparsed public clue.')],
                     'labels': ['fired'], 'source': 'replay'}])


def fail(*args, **kwargs):
    raise RuntimeError('DIAGNOSTIC_EXCEPTION_TEXT_MUST_NOT_ENTER_REQUEST_OR_RECORD')


def test_exact_review_sixty_by_five_answerable_cut_is_screened_and_valid():
    items = []
    for item in range(60):
        texts = [('%03d ' % (item * 5 + n)) + 'x' * 21 + ' answerable ' + 'z' * 204 for n in range(5)]
        assert all(not audit.marked(text, 'zebralogic') and audit.marked(text[:32], 'zebralogic')
                   for text in texts)
        report = diagnostics.extract({'diagnostics': texts}, configuration=CHILD,
                                     procedure='authored', source_sha256='a' * 64)[1]
        items.append({'task_id': 'item-%02d' % item, 'records': [report],
                      'labels': ['fired'], 'source': 'candidate'})
    value = d.build(items)
    assert value['items_count'] == 60 and value['distinct_strings'] == 300
    assert value['display_screened'] == 292
    assert all(row['text'] == diagnostics.SCREENED_MARKER and row['screened']
               and row['truncated'] and row['chars'] == 240 for row in value['texts'][8:])
    assert d.valid(value, own={item['task_id'] for item in items})
    d.check_request({'request': 'propose', d.KEY: value})
    assert message_bytes(value) <= d.ENVELOPE_BYTES


@pytest.mark.parametrize('word,cut', [(word, cut) for word in (
    'answerable', 'formattingly', 'outputtingly', 'respondent') for cut in range(1, len(word) + 1)])
def test_every_cut_position_rescreens_the_exact_display(word, cut):
    assert not audit.marked(word, 'zebralogic')
    entry = d._display(word, limit=cut)
    marked = audit.marked(word[:cut], 'zebralogic')
    assert entry['screened'] == marked
    assert entry['text'] == (diagnostics.SCREENED_MARKER if marked else word[:cut])
    assert entry['full_text_sha256'] == diagnostics.sha256(word) and entry['chars'] == len(word)
    value = envelope()
    value['texts'] = [entry]
    value['display_screened'] = int(marked)
    value['display_truncated'] = entry['truncated']
    value = d._seal({key: child for key, child in value.items() if key != 'sha256'})
    assert d.valid(value, own={'run'})
    d.check_request({'request': 'propose', d.KEY: value})


@pytest.mark.parametrize('failure', ['builder', 'validator', 'hash', 'screen', 'bounds'])
def test_attachment_failure_omits_whole_envelope_and_records_only_fixed_reason(monkeypatch, failure):
    value, sink, base = envelope(), {}, {'existing': ['all evidence remains']}
    if failure == 'builder':
        builder = fail
    else:
        builder = lambda: value
        if failure == 'validator':
            monkeypatch.setattr(d, 'valid', fail)
        elif failure == 'hash':
            value['sha256'] = '0' * 64
        elif failure == 'screen':
            value['texts'][0]['text'] = 'answer'
            value = d._seal({key: child for key, child in value.items() if key != 'sha256'})
        else:
            value['items_count'] = 61
    assert d.attach(deepcopy(base), builder, sink=sink, stage='authored_test') == base
    assert sink['diagnostics_omissions'] == {'count': 1, 'reasons': {
        'build_failed' if failure == 'builder' else 'validation_failed': 1}, 'stages': {'authored_test': 1}}
    assert 'DIAGNOSTIC_EXCEPTION' not in json.dumps(sink)


@pytest.mark.parametrize('purpose', ['propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair'])
@pytest.mark.parametrize('failure', ['invalid', 'validator_exception'])
def test_all_actual_request_purposes_fall_back_to_identical_disabled_wire(monkeypatch, purpose, failure):
    base = {'request': purpose, 'bench': 'zebralogic', 'evidence': {'empty_notes': {'count': 1}}}
    ctx, _ = context(configuration=CHILD)
    ctx.roles = WireRoles()
    engineer._ask(ctx, deepcopy(base), purpose)
    expected = ctx.roles.wire[0]
    ctx.roles = WireRoles()
    user = deepcopy(base)
    user['evidence'][d.KEY] = envelope()
    if failure == 'invalid':
        user['evidence'][d.KEY]['sha256'] = '0' * 64
    else:
        monkeypatch.setattr(d, 'check_request', fail)
    engineer._ask(ctx, user, purpose)
    assert ctx.roles.wire[0] == expected and user == base
    assert ctx.sheet['diagnostics_omissions']['count'] == 1
    assert 'diagnostics_omissions' not in ctx.roles.wire[0]['user']


@pytest.mark.parametrize('failure', ['builder', 'validator'])
@pytest.mark.parametrize('source,purpose', [
    ('def before_call(view,state):\n    return {"diagnostics": ["Unparsed public clue."]}\n', 'inert_repair'),
    ('def before_call(view,state):\n    return {"facts": "bad shape", "diagnostics": ["Unparsed public clue."]}\n',
     'fault_repair')])
def test_actual_inert_and_fault_repair_units_persist_omissions_and_keep_legacy_wire(monkeypatch, failure, source, purpose):
    # Establish the diagnostics-disabled wire with the same child prompts and hook code.
    original = d.attach
    monkeypatch.setattr(d, 'attach', lambda container, *args, **kwargs: container)
    disabled, old_package, _ = run(source, GOOD, configuration=CHILD)
    monkeypatch.setattr(d, 'attach', original)
    monkeypatch.setattr(d, 'from_checks' if failure == 'builder' else 'valid', fail)
    ctx, package, unit = run(source, GOOD, configuration=CHILD)
    assert package is not None and package.sha256 == old_package.sha256
    assert ctx.roles.wire == disabled.roles.wire
    assert unit['diagnostics_omissions']['count'] >= 1
    assert unit['diagnostics_omissions'] == ctx.sheet['diagnostics_omissions']
    assert any(json.loads(wire['user']).get('request') == purpose for wire in ctx.roles.wire)
    assert 'DIAGNOSTIC_EXCEPTION' not in json.dumps(unit)
    assert all(d.KEY not in wire['user'] for wire in ctx.roles.wire)


def training_result(monkeypatch, tmp_path):
    ctx, _ = context(configuration=CHILD)
    task = ctx.trajectories[0]['task_id']
    st = SimpleNamespace(bench='zebralogic', parent=ctx.parent, chain_root=tmp_path,
        setting=SimpleNamespace(extra={'configuration': CHILD}, cards={}),
        label=lambda unit: 'D/s1-zebralogic/' + unit, runtime=lambda: {},
        unit=lambda unit, work: work(tmp_path), services=SimpleNamespace(item_workers=None))
    cut = {'run': [{'task_id': task.split('/', 1)[1], 'public': PUBLIC}]}
    monkeypatch.setattr(step, '_references', lambda *args, **kwargs: {})
    monkeypatch.setattr(step, '_run_keys', lambda *args: {task})
    monkeypatch.setattr(step, '_attempt_trajectories', lambda *args: {})
    result = step._train_eval(st, cut, 1, ctx.parent, ctx.parent, {}, current=ctx.trajectories)
    return ctx, result


def test_actual_training_builder_failure_persists_in_train_unit_and_next_context_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(d, 'training', fail)
    ctx, result = training_result(monkeypatch, tmp_path)
    assert d.KEY not in result['feedback']
    assert result['diagnostics_omissions'] == {'count': 1, 'reasons': {'build_failed': 1},
                                              'stages': {'training_feedback': 1}}
    child = replace(ctx, round=2, current=ctx.trajectories, training=result['feedback'])
    assert d.KEY not in engineer.payload(child)
    _, unit = engineer.run_train(child)
    assert unit['calls'] == 1


@pytest.mark.parametrize('failure', ['hash', 'foreign', 'bounds', 'validator_exception'])
def test_context_omits_invalid_channel_but_preserves_strict_legacy_isolation(monkeypatch, tmp_path, failure):
    ctx, result = training_result(monkeypatch, tmp_path)
    valid_training = result['feedback']
    base = {key: value for key, value in valid_training.items() if key != d.KEY}
    broken = deepcopy(valid_training)
    if failure == 'hash':
        broken[d.KEY]['sha256'] = '0' * 64
    elif failure == 'foreign':
        broken[d.KEY] = envelope('foreign-run')
    elif failure == 'bounds':
        broken[d.KEY]['items_count'] = 61
    else:
        monkeypatch.setattr(d, 'valid', fail)
    child = replace(ctx, round=2, current=ctx.trajectories, training=broken)
    disabled = replace(ctx, round=2, current=ctx.trajectories, training=base)
    assert child.training == base and engineer.payload(child) == engineer.payload(disabled)
    _, unit = engineer.run_train(child)
    assert unit['diagnostics_omissions']['count'] == 1
    bad_legacy = {**broken, 'unfixed_examples': [{'task_id': 'foreign-run', 'reference': 'private sentinel'}]}
    with pytest.raises(ValueError, match='training feedback'):
        replace(ctx, round=2, current=ctx.trajectories, training=bad_legacy)
    with pytest.raises(ValueError, match='References only'):
        replace(ctx, references={'foreign-run': 'private sentinel'})


def test_payload_validation_failure_preserves_full_legacy_220k_and_unit_telemetry(monkeypatch, tmp_path):
    ctx, result = training_result(monkeypatch, tmp_path)
    child = replace(ctx, round=2, current=ctx.trajectories, training=result['feedback'])
    base = {key: value for key, value in result['feedback'].items() if key != d.KEY}
    disabled = replace(child, training=base)
    padding = 220_000 - message_bytes(engineer.payload(disabled))
    disabled = replace(disabled, card=disabled.card + 'x' * padding)
    child = replace(child, card=disabled.card)
    expected = engineer.payload(disabled)
    assert message_bytes(expected) == 220_000
    monkeypatch.setattr(d, 'check_request', fail)
    assert engineer.payload(child) == expected
    assert child.sheet['diagnostics_omissions']['stages'] == {'proposal_payload': 1}
    _, unit = engineer.run_train(child)
    assert unit['diagnostics_omissions']['count'] == 2
    assert unit['diagnostics_omissions']['stages'] == {'proposal_payload': 2}


def test_later_validation_failure_cannot_turn_context_validation_into_a_unit_failure(monkeypatch, tmp_path):
    ctx, result = training_result(monkeypatch, tmp_path)
    original, calls = d.valid, []
    def once(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs) if len(calls) == 1 else fail()
    monkeypatch.setattr(d, 'valid', once)
    child = replace(ctx, round=2, current=ctx.trajectories, training=result['feedback'])
    assert len(calls) == 1 and d.KEY in child.training
    assert d.KEY not in engineer.payload(child)
    assert child.sheet['diagnostics_omissions']['stages'] == {'proposal_payload': 1}
