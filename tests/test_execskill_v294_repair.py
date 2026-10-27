"""v2.9.4 inert repairs through the actual offline engineer loop and wire prompts."""
from dataclasses import replace
import json

import pytest

from skillopt.execskill import audit, engineer as e, engineer_v28, engineer_v294, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v291_engineer import (ALF_GOOD, CRASH, GOOD, SYNTAX, encoded, proposal, run)
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

NO_HOOK = 'def applies(view):\n    return True\ndef _run(view):\n    return {"facts": ["Public clue read."]}\n'
NEVER = 'def applies(view):\n    return False\ndef before_call(view, state):\n    return {"facts": ["Public clue read."]}\n'
EMPTY = 'def before_call(view, state):\n    return None\n'
ALF_NO_HOOK = NO_HOOK
ALF_NEVER = NEVER.replace('before_call', 'alf_before_step').replace(
    'return {"facts": ["Public clue read."]}', 'return {"fields": {"facts": ["Public clue read."]}}')
ALF_EMPTY = EMPTY.replace('before_call', 'alf_before_step')
CHILDREN = [('zebra-pc-v11', GOOD), ('alfworld-v8', ALF_GOOD)]


def repair_row(record):
    return record['changes'][0]['inert_repair']


@pytest.mark.parametrize('configuration,bad,good,cause', [
    ('zebra-pc-v11', NO_HOOK, GOOD, 'no_effect_hook'),
    ('zebra-pc-v11', NEVER, GOOD, 'never_fires'),
    ('zebra-pc-v11', EMPTY, GOOD, 'empty_notes'),
    ('alfworld-v8', ALF_NO_HOOK, ALF_GOOD, 'no_effect_hook'),
    ('alfworld-v8', ALF_NEVER, ALF_GOOD, 'never_fires'),
    ('alfworld-v8', ALF_EMPTY, ALF_GOOD, 'empty_notes'),
])
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_repairable_inert_change_becomes_candidate_before_audit(configuration, bad, good, cause, mode):
    ctx, package, record = run(bad, good, configuration=configuration, mode=mode)
    row, repaired = record['changes'][0], repair_row(record)
    assert package is not None and package.procedures[0].source.strip() == good.strip()
    assert cause in row['attempts'][0]['inert_causes'] and row['attempts'][0]['inert']
    assert not row['inert'] and not row['deferred'] and 'inert_causes' not in row
    assert row['kept_attempt'] == 1 and row['fix_calls'] == row['audit_fix_calls'] == 0
    assert repaired['causes'] == row['attempts'][0]['inert_causes']
    assert repaired['kept_index'] == 1 and repaired['stop_reason'] == 'fixed'
    assert record['inert_repair_calls'] == 1 and record['fault_repair_calls'] == 0
    event = repaired['calls'][0]
    assert all(event[key] for key in ('call', 'parsed', 'checked', 'passed_fatal_checks', 'kept'))
    assert not event['inert_after'] and not event['deferred']
    assert event['request']['evidence'] == row['attempts'][0]['inert_evidence']
    expected = engineer_v294.inert_repair_instruction(configuration, repaired['causes'])
    assert event['request']['instruction'] == expected
    assert len(row['audits']) == 1
    wires = [wire for wire in ctx.roles.wire if '/inert-repair/' in wire['label']]
    assert len(wires) == 1 and wires[0]['label'].endswith('inert-repair/1/1')
    assert wires[0]['system'] == engineer_v294.system(configuration, train=mode == 'train') + expected
    assert json.loads(wires[0]['user']) == event['request']
    assert record['prompt_sha256'] == audit.text_sha256(engineer_v294.system(configuration, train=mode == 'train'))
    assert record['version'] == p.kind('engineer-v2-9-4')
    if mode == 'train':
        assert record['lint'][0] == row['attempts'][1]['lint']
        assert e.payload(replace(ctx, round=2, lint=record['lint']))['lint'] == record['lint']


@pytest.mark.parametrize('replacement,reason,parsed,checked', [
    (EMPTY, 'still_inert', True, True),
    (SYNTAX, 'failed_checks', True, True),
    (None, 'unparseable', False, False),
])
def test_unsuccessful_inert_repair_retains_original_report_and_attempt(replacement, reason, parsed, checked):
    sources = (NO_HOOK, replacement, None) if replacement is None else (NO_HOOK, replacement)
    _, package, record = run(*sources, configuration='zebra-pc-v11')
    row, repaired = record['changes'][0], repair_row(record)
    assert package is None and row['inert'] and row['survived'] and row['kept_attempt'] == 0
    assert row['inert_causes'] == row['attempts'][0]['inert_causes'] == ['no_effect_hook']
    assert repaired['kept_index'] == 0 and repaired['stop_reason'] == reason
    assert len(repaired['calls']) == record['inert_repair_calls'] == 1
    event = repaired['calls'][0]
    assert event['parsed'] == parsed and event['checked'] == checked and not event['kept']
    assert len(row['attempts']) == 1 + int(checked)
    assert record['lint'][0] == row['attempts'][0]['lint'] and row['fix_calls'] == 0
    if replacement is None:
        assert len(record['format_retries']) == 1 and record['calls'] == 3
    else:
        assert len(record['format_retries']) == 0


def test_inert_repair_cannot_spend_a_second_behavior_repair():
    ctx, package, record = run(NO_HOOK, EMPTY, GOOD, configuration='zebra-pc-v11')
    assert package is None and repair_row(record)['stop_reason'] == 'still_inert'
    assert record['calls'] == 2 and len(ctx.roles.replies) == 1
    assert record['inert_repair_calls'] == 1 and p.INERT_REPAIRS == engineer_v294.INERT_REPAIRS == 1


def test_no_calls_left_keeps_original_and_no_attempted_call():
    _, package, record = run(NO_HOOK, configuration='zebra-pc-v11', mode='single',
                             spent=p.ENGINEER_CALL_BUDGETS['zebra-pc-v11'] - 1)
    assert package is None and repair_row(record)['stop_reason'] == 'no_calls_left'
    assert repair_row(record)['calls'] == [] and record['inert_repair_calls'] == 0
    assert len(record['changes'][0]['attempts']) == 1


@pytest.mark.parametrize('configuration,good', CHILDREN)
def test_active_change_is_not_triggered_and_gets_no_inert_call(configuration, good):
    _, package, record = run(good, configuration=configuration)
    assert package is not None and repair_row(record) == {
        'causes': [], 'calls': [], 'kept_index': 0, 'stop_reason': 'not_triggered'}
    assert record['inert_repair_calls'] == 0 and record['calls'] == 1


def test_fatal_fix_then_fault_repair_then_inert_repair_then_audit_order():
    ctx, package, record = run(SYNTAX, CRASH, NO_HOOK, GOOD, configuration='zebra-pc-v11')
    row = record['changes'][0]
    assert package is not None and row['fix_calls'] == 1 and row['kept_attempt'] == 3
    assert record['fault_repair_calls'] == record['inert_repair_calls'] == 1
    assert len(row['audits']) == 1 and [attempt['failed'] for attempt in row['attempts']] == ['C2', None, None, None]
    assert [wire['label'].rsplit('/engineer-r1/', 1)[-1] for wire in ctx.roles.wire
            if wire['label'].startswith('engineer/')] == ['propose', 'fix/1/1', 'fault-repair/1/1', 'inert-repair/1/1']
    assert row['inert_repair']['causes'] == ['no_effect_hook']


@pytest.mark.parametrize('blocked', ['crashed', 'excluded_bench'])
@pytest.mark.parametrize('repairable', ['no_effect_hook', 'never_fires', 'empty_notes'])
def test_disallowed_cause_blocks_repair_even_with_repairable_cause(monkeypatch, blocked, repairable):
    ctx, _ = context(configuration='zebra-pc-v11')
    change = proposal(ctx, NO_HOOK)
    report = {'passed': True, 'checks': [], 'inert': True, 'inert_causes': [repairable, blocked],
              'inert_evidence': {repairable: {}, blocked: {}}}
    monkeypatch.setattr(e, '_ask', lambda *a, **k: pytest.fail('No repair allowed'))
    best, current, checked, record = engineer_v294.repair(ctx, change, report)
    assert best is change and current is report and checked == []
    assert record == {'causes': [repairable, blocked], 'calls': [], 'kept_index': 0, 'stop_reason': 'not_triggered'}


def test_actual_crashed_change_uses_fault_repair_only_and_never_inert_repair():
    ctx, package, record = run(CRASH, CRASH, GOOD, configuration='zebra-pc-v11')
    assert package is None and record['fault_repair_calls'] == 1
    assert record['inert_repair_calls'] == 0 and repair_row(record)['stop_reason'] == 'not_triggered'
    assert 'crashed' in record['changes'][0]['inert_causes']
    assert record['calls'] == 2 and len(ctx.roles.replies) == 1


def test_actual_excluded_change_makes_no_repair_call():
    ctx, _ = context(configuration='zebra-pc-v11', mode='single')
    change = proposal(ctx, GOOD)
    change.entry['excluded_benches'].append('zebralogic')
    ctx.roles = WireRoles([engineer_reply({'changes': [change.entry]}, [change.source])])
    package, record = e.run(ctx)
    assert package is None and record['calls'] == 1
    assert record['inert_repair_calls'] == record['fault_repair_calls'] == 0
    assert 'excluded_bench' in repair_row(record)['causes']
    assert repair_row(record)['stop_reason'] == 'not_triggered'


@pytest.mark.parametrize('field,value', [('passed', False), ('deferred', True), ('inert', False)])
def test_failed_deferred_or_active_report_is_ineligible(monkeypatch, field, value):
    ctx, _ = context(configuration='zebra-pc-v11')
    change = proposal(ctx, NO_HOOK)
    report = {'passed': True, 'checks': [], 'inert': True, 'inert_causes': ['no_effect_hook']}
    report[field] = value
    monkeypatch.setattr(e, '_ask', lambda *a, **k: pytest.fail('No repair allowed'))
    best, current, checked, record = engineer_v294.repair(ctx, change, report)
    assert best is change and current is report and checked == [] and record['stop_reason'] == 'not_triggered'


def test_deferred_repair_is_rejected_and_original_replay_cache_restored(monkeypatch):
    ctx, _ = context(configuration='zebra-pc-v11')
    change = proposal(ctx, NO_HOOK)
    report = e.check(change, ctx)
    original_replays = dict(ctx.sheet['audit_replays'])
    ctx.roles = WireRoles([encoded(ctx, GOOD)])
    actual = e.check
    def deferred(candidate, context, taken):
        checked = actual(candidate, context, taken)
        checked['deferred'] = True
        return checked
    monkeypatch.setattr(e, 'check', deferred)
    best, current, checked, record = engineer_v294.repair(ctx, change, report)
    assert best is change and current is report and len(checked) == 1
    assert record['stop_reason'] == 'failed_checks' and record['calls'][0]['passed_fatal_checks']
    assert record['calls'][0]['deferred'] and not record['calls'][0]['kept']
    assert ctx.sheet['audit_replays'] == original_replays


def test_fatal_check_boolean_cannot_mask_failed_fatal_row(monkeypatch):
    ctx, _ = context(configuration='zebra-pc-v11')
    change = proposal(ctx, NO_HOOK)
    report = e.check(change, ctx)
    ctx.roles = WireRoles([encoded(ctx, GOOD)])
    monkeypatch.setattr(e, 'check', lambda *a, **k: {
        'passed': True, 'checks': [{'check': 'C2', 'passed': False}], 'inert': False})
    best, current, checked, record = engineer_v294.repair(ctx, change, report)
    assert best is change and current is report and len(checked) == 1
    assert record['stop_reason'] == 'failed_checks' and not record['calls'][0]['passed_fatal_checks']


def test_bad_format_can_be_fixed_once_using_selected_change_retry():
    ctx, package, record = run(NO_HOOK, None, GOOD, configuration='zebra-pc-v11')
    repaired = repair_row(record)
    assert package is not None and repaired['calls'][0]['kept'] and record['inert_repair_calls'] == 1
    event = record['format_retries'][0]
    assert event['purpose'] == 'inert-repair/1/1' and event['parsed']
    assert record['changes'][0]['fix_calls'] == 0 and record['calls'] == 3
    retry = next(json.loads(wire['user']) for wire in ctx.roles.wire if '/format-retry/' in wire['label'])
    assert retry['change_index'] == 1 and retry['change']['source'].strip() == NO_HOOK.strip()


@pytest.mark.parametrize('configuration', ['zebra-pc-v7', 'zebra-pc-v8', 'zebra-pc-v9', 'zebra-pc-v10',
                                           'alfworld-v4', 'alfworld-v5', 'alfworld-v6', 'alfworld-v7'])
def test_older_configurations_keep_inert_outcomes_without_any_new_calls_or_fields(configuration):
    _, package, record = run(NO_HOOK, configuration=configuration)
    assert package is None and record['calls'] == 1 and record['changes'][0]['inert']
    assert 'inert_repair_calls' not in record and 'inert_repair' not in record['changes'][0]
    assert 'inert_causes' not in record['changes'][0]
    assert all('inert_causes' not in report and 'inert_evidence' not in report
               for report in record['changes'][0]['attempts'])
