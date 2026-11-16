"""Authored hooks through real engineer checks and serialized repair requests."""
from dataclasses import replace
import json

import pytest

from skillopt.execskill import (diagnostics_feedback as diagnostics, engineer, engineer_v216, engineer_v294,
                               inert_feedback, profiles as p, v221_rule, v222_cards, zebralogic)
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_replay import trajectory
from tests.test_execskill_v24_engineer import context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_v291_engineer import proposal, views
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


ADVICE = (
    "Coverage does not outrank a complete solution: when an item's whole answer can be computed and verified "
    "from its public input, propose that program first and keep repairing it across rounds, even at low coverage. "
    "A note that does not settle the answer leaves the answering model to re-solve, so its fixed and broken "
    "counts may only measure re-run noise; do not treat a near miss from such a note as progress."
)
DIAGNOSTIC = 'An authored public clue remains unparsed.'
CONFIGURATIONS = (p.MAIN_V7, p.MAIN_V8, p.MAIN_V9)


def authored_context(configuration, *, mode='train'):
    ctx, workers = context(configuration=p.ZEBRA_PC_V15, views=views(4), mode=mode)
    ctx = replace(ctx, configuration=configuration, card=zebralogic.CARD_TEXT,
                  current=list(ctx.trajectories) if mode == 'train' else [])
    return ctx, workers


def source(notes, *, fires=True):
    return ('def applies(view):\n'
            '    return %s\n'
            'def before_call(view, state):\n'
            '    index = int(view["question"].splitlines()[-1].split()[-1])\n'
            '    result = {"diagnostics": [%r]}\n'
            '    if index < %d:\n'
            '        result["facts"] = ["The public question was read."]\n'
            '    return result\n') % (fires, DIAGNOSTIC, notes)


def checked(configuration, notes, *, fires=True):
    ctx, workers = authored_context(configuration)
    change = proposal(ctx, source(notes, fires=fires))
    report = engineer.check(change, ctx)
    assert report['passed'] and report['failed'] is None
    assert detail(report, 'C6b')['fires_on'] == (4 if fires else 0)
    assert detail(report, 'C6c')['fired'] == (4 if fires else 0)
    assert detail(report, 'C6c')['nonempty'] == (notes if fires else 0)
    assert workers.calls  # The authored hook source really executed.
    return ctx, change, report


def expected_coverage(configuration, pid, touched):
    row = {'touched': touched, 'batch': 4, 'share': touched / 4}
    value = {'candidate': dict(row), 'procedures': {pid: dict(row)},
             'instruction': v221_rule.COVERAGE_SENTENCE,
             'repair': 'fires on almost nothing: %d / 4 items touched' % touched if touched < 3 else None}
    if configuration != p.MAIN_V7:
        value['segments'] = {}
    return value


def expected_empty_evidence(ctx, change, report, notes):
    examples = [{'task_id': key, 'view': view} for key, view in ctx.routing_items[notes:notes + 2]]
    return {'empty_notes': {
        'counts': {'fired': 4, 'empty': 4 - notes, 'exceptions': 0, 'nonempty': notes},
        'task_ids': [row['task_id'] for row in examples], 'examples': examples},
        diagnostics.KEY: diagnostics.from_checks(ctx, change.procedure, report,
            examples=[row['task_id'] for row in examples])}


def repair_request(ctx, change, report):
    ctx.roles = WireRoles([engineer_reply({'changes': []}, [])])
    if p.uses_v216(ctx.configuration, ctx.bench):
        _, _, _, fields = engineer_v216.repair_cycle(ctx, change, report, attempts=[report])
        assert fields['repair_cycle']['inert_repairs'] > 0
    else:
        engineer_v294.repair(ctx, change, report)
    request = next(wire for wire in ctx.roles.wire if '/inert-repair/' in wire['label'])
    return json.loads(request['user'])


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
@pytest.mark.parametrize('mode', ['single', 'train'])
@pytest.mark.parametrize('purpose', ['propose', 'inert_repair'])
def test_complete_solution_sentence_reaches_only_main_v9_rendered_engineer_prompt(configuration, mode, purpose):
    ctx, _ = authored_context(configuration, mode=mode)
    ctx.roles = WireRoles()
    engineer._ask(ctx, {'request': purpose, 'evidence': {}}, purpose)
    assert len(ctx.roles.wire) == 1
    rendered = ctx.roles.wire[0]['system']
    assert rendered.count(ADVICE) == (1 if configuration == p.MAIN_V9 else 0)


@pytest.mark.parametrize('notes', [0, 1, 2])
def test_main_v9_fired_procedure_keeps_empty_note_diagnostics_and_coverage_in_repair(notes):
    ctx, change, report = checked(p.MAIN_V9, notes)
    coverage = expected_coverage(p.MAIN_V9, change.procedure.id, notes)
    assert report['inert'] is True and report['coverage'] == coverage
    assert report['inert_causes'] == ['empty_notes']
    evidence = {**expected_empty_evidence(ctx, change, report, notes), 'coverage': coverage}
    assert report['inert_evidence'] == evidence
    extra = evidence[diagnostics.KEY]
    assert extra['items_count'] == 4 and extra['aggregate'][0]['items'] == 4
    assert extra['texts'][extra['aggregate'][0]['text_index']]['text'] == DIAGNOSTIC
    assert all('fired' in row['labels'] and 'never_fires' not in row['labels'] for row in extra['items'])
    request = repair_request(ctx, change, report)
    assert request['request'] == 'inert_repair' and request['evidence'] == evidence
    assert 'empty_notes' in request['instruction'] and 'never_fires' not in request['instruction']


@pytest.mark.parametrize('configuration', [p.MAIN_V7, p.MAIN_V8])
@pytest.mark.parametrize('notes', [0, 1, 2])
def test_main_v7_and_main_v8_keep_exact_existing_inert_labels_and_evidence(configuration, notes):
    ctx, change, report = checked(configuration, notes)
    coverage = expected_coverage(configuration, change.procedure.id, notes)
    assert report['inert'] is True and report['coverage'] == coverage
    assert report['inert_causes'] == (['never_fires', 'empty_notes'] if notes == 0 else ['never_fires'])
    expected = {**(expected_empty_evidence(ctx, change, report, notes) if notes == 0 else {}),
                'coverage': coverage}
    assert report['inert_evidence'] == expected
    request = repair_request(ctx, change, report)
    assert request['evidence'] == expected and 'never_fires' in request['instruction']
    assert (diagnostics.KEY in request['evidence']) is (notes == 0)


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_truly_never_firing_procedure_retains_existing_never_fires_evidence(configuration):
    ctx, change, report = checked(configuration, 0, fires=False)
    assert report['inert'] is True and report['inert_causes'] == ['never_fires']
    examples = [{'task_id': key, 'view': view} for key, view in ctx.routing_items[:2]]
    evidence = {'never_fires': {
        'counts': {'fires_on': 0, 'items': 4, 'predicate_faults': 0}, 'examples': examples},
        diagnostics.KEY: diagnostics.from_checks(ctx, change.procedure, report,
            examples=[row['task_id'] for row in examples]),
        'coverage': expected_coverage(configuration, change.procedure.id, 0)}
    assert report['inert_evidence'] == evidence
    assert repair_request(ctx, change, report)['evidence'] == evidence


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_three_notes_keep_existing_non_inert_boundary_without_repair(configuration):
    ctx, change, report = checked(configuration, 3)
    assert report['inert'] is False
    assert report['coverage'] == expected_coverage(configuration, change.procedure.id, 3)
    assert 'inert_causes' not in report and 'inert_evidence' not in report
    assert engineer_v294.repair(ctx, change, report)[3]['stop_reason'] == 'not_triggered'
    assert not ctx.roles.calls


def test_inert_cause_names_and_repairable_set_stay_frozen():
    assert inert_feedback.CAUSES == ('no_effect_hook', 'never_fires', 'empty_notes', 'crashed', 'excluded_bench')
    assert engineer_v294.REPAIRABLE_CAUSES == frozenset({'no_effect_hook', 'never_fires', 'empty_notes'})


def train_scripted(ctx, *changes):
    """Keep checks, repair dispatch and audit real; only roles/workers are authored."""
    ctx.audit_judges = {key: Judge() for key in ('G', 'D')}
    ctx.roles = WireRoles([engineer_reply({'findings': []}, [])] + [
        engineer_reply({'changes': [change.entry]}, [change.source]) for change in changes])
    return engineer.run_train(ctx)


def search_context(configuration):
    ctx, workers = authored_context(configuration)
    public = [{'question': 'Public fixture index %d' % i, 'context': 'Authored public evidence.'}
              for i in range(3)]
    stored = [trajectory('cell-%d' % i, 'searchqa', 'searchqa/run-%d' % i, 'fail', [view])
              for i, view in enumerate(public[:2])]
    # This is the exact routing boundary after admission: two stored run items
    # and one generated item, which has no stored replay or disclosed example.
    routing = [(row['task_id'], view) for row, view in zip(stored, public)]
    routing.append(('searchqa/generated-0', public[2]))
    return replace(ctx, bench='searchqa', step='D/s1-searchqa', label='D/s1-searchqa/engineer-r1',
                   card=v222_cards.historical_text('searchqa'), trajectories=stored, current=list(stored),
                   routing_items=routing), workers


def search_change(ctx, *, crashes):
    body = ('def applies(view):\n    return True\n'
            'def before_call(view, state):\n'
            '    index = int(view["question"].split()[-1])\n')
    if crashes:
        body += '    if index < 2:\n        raise ValueError("Authored stored-input failure")\n'
    body += '    return {"facts": ["The public question was read."]}\n'
    change = proposal(ctx, body)
    change.entry['excluded_benches'] = []
    return change


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_coverage_only_stored_crashes_do_not_block_inert_repair_in_run_train(configuration):
    ctx, workers = search_context(configuration)
    bad, good = search_change(ctx, crashes=True), search_change(ctx, crashes=False)
    package, record = train_scripted(ctx, bad, bad, good)
    row = record['changes'][0]
    initial = row['attempts'][0]
    assert initial['passed'] and initial['inert']
    assert detail(initial, 'C6c')['exceptions'] == 2
    assert detail(initial, 'C6c')['nonempty'] == 1
    assert initial['coverage']['candidate']['touched'] == 1
    causes = ['empty_notes'] if configuration == p.MAIN_V9 else ['never_fires']
    assert initial['inert_causes'] == causes
    assert row['fault_repair']['stop_reason'] == 'no_improvement'
    assert record['fault_repair_calls'] == 1
    assert row['inert_repair']['causes'] == causes
    assert record['inert_repair_calls'] == 1 and row['inert_repair']['stop_reason'] == 'fixed'
    assert row['survived'] and package is not None
    assert package.procedures[0].source.strip() == good.source.strip()
    assert [json.loads(wire['user']).get('request') for wire in ctx.roles.wire] == [
        'analyse', 'propose', 'fault_repair', 'inert_repair']
    evidence = row['inert_repair']['calls'][0]['request']['evidence']
    assert evidence == initial['inert_evidence'] and 'crashed' not in evidence
    if configuration == p.MAIN_V9:
        assert evidence['empty_notes']['counts'] == {
            'fired': 3, 'empty': 2, 'exceptions': 2, 'nonempty': 1, 'missing_precheck': 0}
        assert evidence['empty_notes']['examples'] == []
    else:
        assert evidence == {'coverage': initial['coverage']}
    assert workers.calls


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_original_all_crashed_inert_classification_is_preserved(configuration):
    ctx, _ = search_context(configuration)
    ctx = replace(ctx, routing_items=ctx.routing_items[:2])
    change = search_change(ctx, crashes=True)
    report = engineer.check(change, ctx)
    assert report['passed'] and report['inert']
    assert detail(report, 'C6c')['nonempty'] == 0
    assert 'crashed' in report['inert_causes'] and 'crashed' in report['inert_evidence']
    assert engineer_v294.repair(ctx, change, report)[3]['stop_reason'] == 'not_triggered'
    assert not ctx.roles.calls


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
@pytest.mark.parametrize('touched', [1, 2])
def test_low_revision_coverage_keeps_truthful_four_nonempty_note_evidence(configuration, touched):
    ctx, original, report = checked(configuration, 4)
    assert not report['inert']
    parent = engineer.candidate(ctx.parent, [original], step=ctx.step)
    ctx = replace(ctx, parent=parent, base=parent, round=2)
    changed = source(4).replace('    return result\n',
        '    if index < %d:\n'
        '        result["facts"] = ["The public question was read again."]\n'
        '    return result\n' % touched)
    revision = engineer.Change(1, 'revision', {**original.entry, 'kind': 'revision',
        'revises': original.procedure.id}, changed, 'b' * 64)
    report = engineer.check(revision, ctx)
    assert report['passed'] and report['inert']
    assert detail(report, 'C6b')['fires_on'] == detail(report, 'C6c')['nonempty'] == 4
    assert report['coverage']['candidate']['touched'] == touched
    if configuration == p.MAIN_V9:
        assert report['inert_causes'] == ['empty_notes']
        expected = {**expected_empty_evidence(ctx, revision, report, 4), 'coverage': report['coverage']}
        assert expected['empty_notes'] == {'counts': {
            'fired': 4, 'empty': 0, 'exceptions': 0, 'nonempty': 4}, 'task_ids': [], 'examples': []}
    else:
        assert report['inert_causes'] == ['never_fires']
        expected = {'coverage': report['coverage']}
    assert report['inert_evidence'] == expected
    assert repair_request(ctx, revision, report)['evidence'] == expected


def test_main_v9_run_train_dispatches_zebra_to_real_v216_repair_cycle():
    ctx, _ = authored_context(p.MAIN_V9)
    package, record = train_scripted(ctx, proposal(ctx, source(1)), proposal(ctx, source(4)))
    row = record['changes'][0]
    assert package is not None and row['survived']
    assert row['repair_cycle']['stop_reason'] == 'survived'
    assert row['repair_cycle']['inert_repairs'] == row['repair_cycle']['audits'] == 1
    assert row['inert_repair']['causes'] == ['empty_notes']
    assert row['inert_repair']['stop_reason'] == 'fixed'
    assert row['inert_repair']['calls'][0]['request']['evidence'] == row['attempts'][0]['inert_evidence']
    assert record['inert_repair_calls'] == 1 and record['fault_repair_calls'] == 0
    assert row['kept_attempt'] == 1
