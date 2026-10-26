"""Authored offline v2.9.1 fault repair through the actual engineer loop."""
from dataclasses import replace
import json

import pytest

from skillopt.execskill import audit, engineer as e, engineer_v291, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import PUBLIC, change, context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CRASH = 'def before_call(view, state):\n    return {"facts": [view["question"].splitlines()[999]]}\n'
GOOD = 'def before_call(view, state):\n    return {"facts": ["The public question was read."]}\n'
ALF_CRASH = 'def alf_before_step(view, state):\n    return {"fields": {"facts": [state.get("seen", "No prior state.")]}}\n'
ALF_GOOD = 'def alf_before_step(view, state):\n    return {"fields": {"facts": ["The initial observation is visible."]}}\n'
SYNTAX = 'def before_call(view, state):\n    return {\n'


def proposal(ctx, source):
    result = change(ctx, source)
    if ctx.bench == 'alfworld':
        result.entry['excluded_benches'] = []
    return result


def encoded(ctx, source):
    if source is None:
        return 'unusable'
    result = proposal(ctx, source)
    return engineer_reply({'changes': [result.entry]}, [result.source])


def run(*sources, configuration='zebra-pc-v8', mode='train', views=None, spent=0):
    bench = p.active_benches(configuration)[0]
    ctx, _ = context(configuration=configuration, bench=bench, mode=mode, views=views)
    if mode == 'train':
        ctx = replace(ctx, current=list(ctx.trajectories))
    ctx.spent = spent
    ctx.audit_judges = {'G': Judge(), 'D': Judge()}
    analysts = min(p.TRAIN_ANALYST_CALLS, (len(ctx.current) + p.TRAIN_ANALYST_BATCH - 1) // p.TRAIN_ANALYST_BATCH)
    ctx.roles = WireRoles(([engineer_reply({'findings': []}, [])] * analysts if mode == 'train' else [])
                          + [encoded(ctx, source) for source in sources])
    package, record = e.run_train(ctx) if mode == 'train' else e.run(ctx)
    return ctx, package, record


def repair_row(record):
    return record['changes'][0]['fault_repair']


@pytest.mark.parametrize('configuration,bad,good', [('zebra-pc-v8', CRASH, GOOD),
                                                   ('alfworld-v5', ALF_CRASH, ALF_GOOD)])
@pytest.mark.parametrize('mode', ['train', 'single'])
def test_inert_faulting_change_is_repaired_before_audit_and_becomes_candidate(configuration, bad, good, mode):
    ctx, package, record = run(bad, good, configuration=configuration, mode=mode)
    row, repaired = record['changes'][0], repair_row(record)
    assert package is not None and package.procedures[0].source.strip() == good.strip()
    assert row['attempts'][0]['inert'] and not row['inert'] and not row['deferred']
    assert row['kept_attempt'] == 1 and row['fix_calls'] == 0 and row['audit_fix_calls'] == 0
    assert repaired['fired'] == repaired['faulted'] == repaired['threshold'] == 1
    assert repaired['triggered'] and repaired['kept_index'] == 1 and repaired['stop_reason'] == 'fixed'
    assert repaired['final']['faulted'] == 0 and record['fault_repair_calls'] == 1
    call = repaired['calls'][0]
    assert call['call'] and call['parsed'] and call['checked'] and call['passed_fatal_checks'] and call['kept']
    assert call['faulted_after'] == 0
    assert call['request']['change']['source'].strip() == bad.strip()
    assert call['request']['instruction'] == engineer_v291.FAULT_REPAIR_INSTRUCTION
    assert len(row['audits']) == 1 and all('splitlines()[999]' not in pair['requests']['G']['user']
                                        for pair in row['audits'][0]['requests'])
    fault_calls = [wire for wire in ctx.roles.wire if '/fault-repair/' in wire['label']]
    assert len(fault_calls) == 1 and fault_calls[0]['label'].endswith('fault-repair/1/1')
    if mode == 'train':
        next_ctx = replace(ctx, round=2, lint=record['lint'])
        assert e.payload(next_ctx)['lint'] == record['lint']
        c6 = next(info for info in record['lint'][0]['information'] if info['check'] == 'C6')
        assert c6['fired_items'] == 1 and c6['faulted_items'] == 0 and c6['signatures'] == []
    assert record['version'] == p.kind('engineer-v2-9-1')


@pytest.mark.parametrize('configuration,good', [('zebra-pc-v8', GOOD), ('alfworld-v5', ALF_GOOD)])
def test_no_fault_has_explicit_not_triggered_record_and_no_repair(configuration, good):
    _, package, record = run(good, configuration=configuration)
    repaired = repair_row(record)
    assert package is not None and repaired['stop_reason'] == 'not_triggered'
    assert repaired['faulted'] == 0 and not repaired['triggered'] and repaired['calls'] == []
    assert repaired['kept_index'] == 0 and record['fault_repair_calls'] == 0


def partial_source(faulted, label='The public question was read.'):
    return ('def before_call(view, state):\n'
            '    index = int(view["question"].splitlines()[-1].split()[-1])\n'
            '    if index < %d:\n        raise ValueError("Authored failure")\n'
            '    return {"facts": [%r]}\n') % (faulted, label)


def views(number):
    return [{**PUBLIC, 'question': PUBLIC['question'] + '\nFixture index %d' % index} for index in range(number)]


@pytest.mark.parametrize('counts,reason,kept', [((20, 15, 10), 'limit', 2),
                                              ((6, 4, 2), 'fixed', 2),
                                              ((6, 4, 5), 'no_improvement', 1)])
def test_two_call_limit_and_strict_best_attempt_retention(counts, reason, kept):
    sources = [partial_source(count) for count in counts]
    ctx, package, record = run(*sources, views=views(30))
    repaired, row = repair_row(record), record['changes'][0]
    assert record['fault_repair_calls'] == 2 and len(repaired['calls']) == 2
    assert repaired['stop_reason'] == reason and repaired['kept_index'] == kept and row['kept_attempt'] == kept
    assert repaired['final']['faulted'] == counts[kept]
    assert package.procedures[0].source.strip() == sources[kept].strip()
    assert [event['kept'] for event in repaired['calls']] == [True, kept == 2]
    c6 = next(info for info in record['lint'][0]['information'] if info['check'] == 'C6')
    assert c6['faulted_items'] == counts[kept]
    replace(ctx, round=2, lint=record['lint'])


@pytest.mark.parametrize('replacement,reason,parsed', [(SYNTAX, 'failed_checks', True),
                                                     (CRASH, 'no_improvement', True),
                                                     (None, 'unparseable', False)])
def test_failed_or_unparseable_repair_keeps_original_attempt_and_lint(replacement, reason, parsed):
    sources = (CRASH, replacement, None) if replacement is None else (CRASH, replacement)
    ctx, package, record = run(*sources)
    repaired, row = repair_row(record), record['changes'][0]
    assert package is None and row['inert'] and row['survived'] and row['kept_attempt'] == 0
    assert repaired['calls'][0]['request']['change']['source'].strip() == CRASH.strip()
    assert repaired['stop_reason'] == reason and repaired['kept_index'] == 0
    assert repaired['calls'][0]['parsed'] == parsed and not repaired['calls'][0]['kept']
    assert repaired['final']['faulted'] == 1 and record['fault_repair_calls'] == 1
    assert record['lint'][0] == row['attempts'][0]['lint'] and row['fix_calls'] == 0
    if replacement is None:
        assert len(record['format_retries']) == 1 and record['calls'] == 3


def test_worse_repair_cannot_replace_best_replay_cache_before_audit():
    original = partial_source(1, 'Original public note.')
    rejected = partial_source(2, 'Rejected changed note.')
    _, package, record = run(original, rejected, views=views(3))
    row = record['changes'][0]
    assert package is not None and package.procedures[0].source.strip() == original.strip()
    assert repair_row(record)['stop_reason'] == 'no_improvement' and row['kept_attempt'] == 0
    for pair in row['audits'][0]['requests']:
        for request in pair['requests'].values():
            assert 'Rejected changed note.' not in request['user']
    assert any('Original public note.' in pair['requests']['G']['user'] for pair in row['audits'][0]['requests'])


def test_fatal_check_loop_precedes_fault_repair_and_allowances_are_separate():
    _, package, record = run(SYNTAX, CRASH, GOOD)
    row = record['changes'][0]
    assert package is not None and row['fix_calls'] == 1 and record['fault_repair_calls'] == 1
    assert [report['failed'] for report in row['attempts']] == ['C2', None, None]
    assert row['kept_attempt'] == 2


def test_no_calls_left_does_not_discard_the_original_change():
    _, package, record = run(CRASH, mode='single', spent=p.ENGINEER_CALL_BUDGETS['zebra-pc-v8'] - 1)
    assert package is None and repair_row(record)['stop_reason'] == 'no_calls_left'
    assert repair_row(record)['calls'] == [] and record['fault_repair_calls'] == 0


def test_repair_reply_gets_only_one_format_retry_without_using_behavior_fixes():
    _, package, record = run(CRASH, None, GOOD)
    assert package is not None and record['fault_repair_calls'] == 1
    assert record['changes'][0]['fix_calls'] == 0 and len(record['format_retries']) == 1
    assert record['format_retries'][0]['purpose'] == 'fault-repair/1/1'
    assert record['format_retries'][0]['parsed'] and repair_row(record)['calls'][0]['kept']


def test_deferred_repair_is_not_kept_even_with_fewer_reported_faults(monkeypatch):
    ctx, _ = context(configuration='zebra-pc-v8')
    proposed = proposal(ctx, CRASH)
    original = e.check(proposed, ctx)
    ctx.roles = WireRoles([encoded(ctx, GOOD)])
    actual = e.check
    def deferred(change, ctx, taken):
        report = actual(change, ctx, taken)
        report['deferred'] = True
        return report
    monkeypatch.setattr(e, 'check', deferred)
    best, report, checked, record = engineer_v291.repair(ctx, proposed, original)
    assert best is proposed and report is original and len(checked) == 1
    assert record['stop_reason'] == 'failed_checks' and not record['calls'][0]['kept']
    assert record['calls'][0]['passed_fatal_checks'] and record['calls'][0]['faulted_after'] == 0


@pytest.mark.parametrize('configuration,bad', [('zebra-pc-v7', CRASH), ('alfworld-v4', ALF_CRASH)])
def test_parent_configs_keep_faults_informational_without_new_prompt_or_record_fields(configuration, bad):
    ctx, package, record = run(bad, configuration=configuration)
    assert package is None and record['changes'][0]['inert'] and record['calls'] == 1
    assert 'fault_repair_calls' not in record and 'fault_repair' not in record['changes'][0]
    assert 'kept_attempt' not in record['changes'][0]
    assert all('fault-repair calls' not in request['system'] for request in ctx.roles.wire)
    c6 = next(info for info in record['lint'][0]['information'] if info['check'] == 'C6')
    assert set(c6) == {'check', 'passed', 'counts'}


@pytest.mark.parametrize('configuration', ['zebra-pc-v8', 'alfworld-v5'])
@pytest.mark.parametrize('train', [False, True])
def test_new_prompt_contains_exact_fault_rule_and_configuration_patience(configuration, train):
    text = engineer_v291.system(configuration, train=train)
    assert engineer_v291.FAULT_RULE in text and 'patience 4' in text and '(v2.9.1)' in text
    assert (engineer_v291.ALF_STATE_RULE in text) == (configuration == 'alfworld-v5')
    for pin in engineer_v291.prompt_pins().values():
        assert audit.text_sha256(pin['text']) == pin['sha256']
