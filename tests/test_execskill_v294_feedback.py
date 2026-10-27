"""Inert diagnostics, bounded public evidence and next-round history; offline."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import (engineer as e, engineer_v28, fault_feedback, inert_feedback,
                               profiles as p, step)
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import PUBLIC, context, detail
from tests.test_execskill_v291_engineer import ALF_CRASH, CRASH, proposal, run
from tests.test_execskill_v294_repair import (ALF_EMPTY, ALF_NEVER, EMPTY, NEVER, NO_HOOK)
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def checked(configuration, source, *, views=None, hooks=('before_call',)):
    ctx, _ = context(configuration=configuration, bench=p.active_benches(configuration)[0], views=views)
    change = proposal(ctx, source)
    if hooks is None:
        change.entry.pop('hooks', None)
    else:
        change.entry['hooks'] = list(hooks)
    return ctx, change, e.check(change, ctx)


@pytest.mark.parametrize('configuration,effects', [
    ('zebra-pc-v11', ['before_call']), ('alfworld-v8', ['alf_before_step', 'alf_after_step'])])
def test_no_effect_hook_evidence_is_declared_not_derived_and_only_top_level(configuration, effects):
    source = NO_HOOK + '\ndef outer():\n    def before_call(view, state):\n        return None\n    return None\n'
    _, change, report = checked(configuration, source)
    assert report['passed'] and report['inert_causes'] == ['no_effect_hook']
    evidence = report['inert_evidence']['no_effect_hook']
    assert evidence == {'declared_hooks': ['before_call'],
                        'defined_functions': ['applies', '_run', 'outer'], 'effect_hooks': effects}
    assert change.entry['hooks'] == ['applies']


@pytest.mark.parametrize('configuration', ['zebra-pc-v11', 'alfworld-v8'])
def test_absent_written_hooks_stay_absent_in_read_call_and_direct_check(configuration):
    ctx, change, report = checked(configuration, NO_HOOK, hooks=None)
    assert 'declared_hooks' not in report['inert_evidence']['no_effect_hook']
    entry = dict(change.entry)
    entry.pop('hooks')
    changes, failures = engineer_v28.read_call(ctx, engineer_reply({'changes': [entry]}, [NO_HOOK]),
                                               'a' * 64, 'propose')
    assert not failures
    assert 'declared_hooks' not in e.check(changes[0], ctx)['inert_evidence']['no_effect_hook']


@pytest.mark.parametrize('configuration,source', [('zebra-pc-v11', NEVER), ('alfworld-v8', ALF_NEVER)])
def test_never_fires_has_counts_and_run_examples_without_vacuous_crashed(configuration, source):
    ctx, _, report = checked(configuration, source)
    assert report['passed'] and report['inert_causes'] == ['never_fires']
    evidence = report['inert_evidence']['never_fires']
    assert evidence['counts'] == {'items': 1, 'fires_on': 0, 'predicate_faults': 0}
    assert evidence['examples'][0]['task_id'] == ctx.trajectories[0]['task_id']
    assert evidence['examples'][0]['view'] == dict(ctx.routing_items)[ctx.trajectories[0]['task_id']]


@pytest.mark.parametrize('configuration,source', [('zebra-pc-v11', EMPTY), ('alfworld-v8', ALF_EMPTY)])
def test_empty_notes_reports_counts_and_ids_that_actually_returned_nothing(configuration, source):
    ctx, _, report = checked(configuration, source)
    assert report['passed'] and report['inert_causes'] == ['empty_notes']
    evidence = report['inert_evidence']['empty_notes']
    assert evidence['counts'] == {'fired': 1, 'empty': 1, 'exceptions': 0, 'nonempty': 0}
    assert evidence['task_ids'] == [ctx.trajectories[0]['task_id']]
    assert evidence['examples'][0]['task_id'] == evidence['task_ids'][0]


@pytest.mark.parametrize('configuration,source', [('zebra-pc-v11', CRASH), ('alfworld-v8', ALF_CRASH)])
def test_crashed_evidence_uses_existing_signatures_and_order(configuration, source):
    ctx, change, report = checked(configuration, source)
    assert report['passed'] and report['inert_causes'] == ['empty_notes', 'crashed']
    summary = fault_feedback.summarize(change.procedure, report, limit=3, example=False,
                                       configuration=configuration)
    assert report['inert_evidence']['crashed']['signatures'] == summary['signatures']
    assert summary['signatures']
    assert report['inert_evidence']['empty_notes']['task_ids'] == []


def test_excluded_bench_evidence_and_no_repair_call():
    ctx, _ = context(configuration='zebra-pc-v11')
    change = proposal(ctx, NO_HOOK)
    change.entry['excluded_benches'].append(ctx.bench)
    report = e.check(change, ctx)
    assert report['passed'] and report['inert_causes'] == ['no_effect_hook', 'never_fires', 'excluded_bench']
    assert report['inert_evidence']['excluded_bench'] == {'bench': ctx.bench}
    from skillopt.execskill import engineer_v294
    assert engineer_v294.repair(ctx, change, report)[3]['stop_reason'] == 'not_triggered'
    assert not ctx.roles.calls


def test_alf_after_step_counts_as_effect_hook_in_existing_check_tuple():
    ctx, _ = context(configuration='alfworld-v8', bench='alfworld')
    change = proposal(ctx, 'def alf_after_step(event, state):\n    return {"seen": True}\n')
    change.entry['state_bytes'] = 100
    report = e.check(change, ctx)
    assert report['passed'] and not report['inert']
    assert 'inert_causes' not in report and 'inert_evidence' not in report


@pytest.mark.parametrize('source,cause', [(EMPTY, 'empty_notes'), (NEVER, 'never_fires')])
def test_examples_are_bounded_two_verified_run_items_and_never_generated(source, cause):
    views = [{**PUBLIC, 'question': PUBLIC['question'] + '\n' + '界' * 20_000} for _ in range(5)]
    ctx, _ = context(configuration='zebra-pc-v11', views=views)
    # C6b may route generated items; they must never be disclosed as examples.
    ctx.routing_items.insert(0, ('generated-private', {'question': 'SEALED SENTINEL'}))
    change = proposal(ctx, source)
    report = e.check(change, ctx)
    evidence = report['inert_evidence']
    examples = evidence[cause]['examples']
    assert len(examples) == 2
    assert {row['task_id'] for row in examples} <= {row['task_id'] for row in ctx.trajectories}
    assert all(len(fault_feedback._json(row['view'])) <= fault_feedback.VIEW_CHARS for row in examples)
    assert fault_feedback.serialized_bytes(evidence) <= fault_feedback.EVIDENCE_BYTES
    assert 'SEALED SENTINEL' not in str(evidence) and 'generated-private' not in str(evidence)
    assert evidence[cause]['counts']['fired' if cause == 'empty_notes' else 'items'] == 6


def test_all_causes_are_ordered_and_metadata_and_views_fit_byte_budget():
    ctx, _ = context(configuration='zebra-pc-v11', views=[{**PUBLIC, 'question': PUBLIC['question'] + '界' * 20_000}] * 3)
    source = '\n'.join('def f%d_%s():\n    return None\n' % (n, '界' * 150) for n in range(50))
    change = proposal(ctx, source)
    change.procedure = SimpleNamespace(hooks=(), excluded_benches=(ctx.bench,), id='inert', source=source)
    inert_feedback.remember_declaration(change, {'hooks': ['界' * 20_000]})
    tasks = [row['task_id'] for row in ctx.trajectories]
    report = {'checks': [{'check': 'C6b', 'detail': {'fires_on': 0, 'items': 60, 'predicate_faults': 0,
        'captures': [{'task_id': task, 'applies': False} for task in tasks]}},
        {'check': 'C6c', 'detail': {'fired': 60, 'empty': 60, 'nonempty': 0, 'exceptions': 0,
                                  'empty_task_ids': tasks}}]}
    causes, evidence = inert_feedback.describe(change, ctx, report, effect_hooks=('before_call',),
        from_replay=True, from_routing=True, outcomes={'cell': SimpleNamespace(applies=True)})
    assert causes == list(inert_feedback.CAUSES) == list(evidence)
    assert len(evidence['no_effect_hook']['defined_functions']) <= inert_feedback.FUNCTIONS
    assert all(len(name) <= inert_feedback.FUNCTION_CHARS for name in evidence['no_effect_hook']['defined_functions'])
    assert fault_feedback.serialized_bytes(evidence['no_effect_hook']['declared_hooks']) <= 1000
    assert evidence['no_effect_hook']['truncated']
    assert fault_feedback.serialized_bytes(evidence) <= fault_feedback.EVIDENCE_BYTES
    assert evidence['never_fires']['counts']['items'] == evidence['empty_notes']['counts']['fired'] == 60


def test_oversized_task_ids_are_omitted_without_inventing_shortened_ids(monkeypatch):
    task = 'task-' + '界' * 1000
    ctx = SimpleNamespace(routing_items=[(task, {'question': 'public'})])
    monkeypatch.setattr(e, '_run_entries', lambda ctx: [{'item': task, 'view': {'question': 'public'}}])
    assert inert_feedback._examples(ctx, [task]) == []


@pytest.mark.parametrize('configuration', ['zebra-pc-v11', 'alfworld-v8'])
def test_history_contains_only_names_and_is_accepted_in_next_round(configuration):
    ctx, package, record = run(NO_HOOK, NO_HOOK, configuration=configuration)
    assert package is None
    line = step._line(1, {'candidate_sha256': None, 'engineer': record}, None, configuration=configuration)
    line['patience_counted'] = False
    row = line['proposals'][0]
    assert row['fate'] == 'inert' and row['inert_causes'] == ['no_effect_hook']
    assert set(row) == e.PROPOSAL_FIELDS | {'inert_causes'}
    assert e._history_line(line, 2, v24=True, v28=True, v29=True, v291=True, v294=True)
    assert not e._history_line(line, 2, v24=True, v28=True, v29=True, v291=True)
    next_ctx = replace(ctx, round=2, history=[line], lint=record['lint'])
    assert e.payload(next_ctx)['history'] == [line]


@pytest.mark.parametrize('bad', [['invented'], ['empty_notes', 'no_effect_hook'],
                                 ['no_effect_hook', 'no_effect_hook'], None, 'no_effect_hook'])
def test_history_rejects_invalid_or_unordered_causes(bad):
    _, _, record = run(NO_HOOK, NO_HOOK, configuration='zebra-pc-v11')
    line = step._line(1, {'candidate_sha256': None, 'engineer': record}, None, configuration='zebra-pc-v11')
    line['patience_counted'] = False
    line['proposals'][0]['inert_causes'] = bad
    assert not e._history_line(line, 2, v24=True, v28=True, v29=True, v291=True, v294=True)


def test_unobserved_routing_does_not_invent_crashes_or_break_next_round_history():
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v291_engineer import encoded
    ctx, _ = context(configuration='zebra-pc-v11')
    ctx.routing_items = []
    ctx.roles = WireRoles([encoded(ctx, NEVER)])
    # No current failures means no analyst request; the run replays still exist.
    package, record = e.run_train(ctx)
    assert package is None and record['changes'][0]['inert']
    assert record['changes'][0]['inert_causes'] == []
    assert record['inert_repair_calls'] == record['fault_repair_calls'] == 0
    line = step._line(1, {'candidate_sha256': None, 'engineer': record}, None, configuration=ctx.configuration)
    line['patience_counted'] = False
    next_ctx = replace(ctx, round=2, history=[line], lint=record['lint'])
    assert e.payload(next_ctx)['history'][0]['proposals'][0]['inert_causes'] == []


@pytest.mark.parametrize('configuration', ['zebra-pc-v9', 'zebra-pc-v10', 'alfworld-v6', 'alfworld-v7'])
def test_parent_history_and_checks_have_no_new_fields(configuration):
    _, _, record = run(NO_HOOK, configuration=configuration)
    line = step._line(1, {'candidate_sha256': None, 'engineer': record}, None, configuration=configuration)
    line['patience_counted'] = False
    assert line['proposals'][0]['fate'] == 'inert' and set(line['proposals'][0]) == e.PROPOSAL_FIELDS
    assert e._history_line(line, 2, v24=True, v28=True, v29=True, v291=True)
    assert all('empty_task_ids' not in detail(attempt, 'C6c') for attempt in record['changes'][0]['attempts'])
