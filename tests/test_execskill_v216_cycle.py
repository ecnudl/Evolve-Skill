"""v2.16 bounded cycles over authored public inputs, fake roles, and in-process hooks."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.coevo5.outcomes import BudgetStop
from skillopt.execskill import (audit, diagnostics_feedback, engineer as e, engineer_v28,
                               engineer_v216 as cycle, engineer_v294, profiles as p)
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v291_engineer import GOOD, SYNTAX, encoded, proposal
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILD = 'zebra-pc-v15'
EMPTY = 'def before_call(view,state):\n    return {"diagnostics": ["Unparsed clue zero."]}\n'
EMPTY1 = EMPTY.replace('zero', 'one')
EMPTY2 = EMPTY.replace('zero', 'two')
EMPTY3 = EMPTY.replace('zero', 'three')
GOOD1 = GOOD.replace('was read', 'was read once')
GOOD2 = GOOD.replace('was read', 'was read twice')
WITH_DIAGNOSTIC = GOOD.replace(']}', '], "diagnostics": ["A remaining public ambiguity."]}')


def prepared(source=EMPTY, *, mode='train', configuration=CHILD):
    ctx, _ = context(configuration=configuration, mode=mode)
    ctx.current = list(ctx.trajectories) if mode == 'train' else []
    ctx.audit_judges = {'G': Judge(), 'D': Judge()}
    change = proposal(ctx, source)
    report = e.check(change, ctx)
    return ctx, change, report


def run_cycle(monkeypatch, source=EMPTY, replies=(), *, confirmed=(False,), report_edit=None):
    ctx, change, report = prepared(source)
    if report_edit:
        report_edit(report)
    ctx.roles = WireRoles([encoded(ctx, reply) for reply in replies])
    audits, original = [], audit.audit1
    def scripted(ctx, candidate, checked):
        flag = confirmed[min(len(audits), len(confirmed) - 1)]
        ctx.audit_judges = {name: Judge(template='P1' if flag else None) for name in ('G', 'D')}
        audits.append((candidate.source, deepcopy(ctx.sheet['audit_replays'])))
        return original(ctx, candidate, checked)
    monkeypatch.setattr(audit, 'audit1', scripted)
    attempts = [report]
    final, current, survived, fields = cycle.repair_cycle(ctx, change, report, attempts=attempts)
    return ctx, final, current, survived, fields, attempts, audits


def requests(ctx, purpose):
    return [json.loads(wire['user']) for wire in ctx.roles.wire
            if json.loads(wire['user']).get('request') == purpose]


def test_three_still_inert_repairs_advance_source_evidence_and_final_replay_cache(monkeypatch):
    ctx, final, current, survived, fields, attempts, audits = run_cycle(
        monkeypatch, replies=(EMPTY1, EMPTY2, GOOD))
    assert survived and final.source.strip() == GOOD.strip() and current is attempts[3]
    rec = fields['repair_cycle']
    assert (rec['inert_repairs'], rec['audit_fixes'], rec['audits'], rec['stop_reason']) == (3, 0, 1, 'survived')
    assert [row['became_current'] for row in rec['steps']] == [True, True, True, False]
    assert [row['attempt_index'] for row in rec['steps']] == [1, 2, 3, 3]
    assert [request['change']['source'].strip() for request in requests(ctx, 'inert_repair')] == [
        EMPTY.strip(), EMPTY1.strip(), EMPTY2.strip()]
    shown = [str(request['evidence'][diagnostics_feedback.KEY]) for request in requests(ctx, 'inert_repair')]
    assert all(word in text for word, text in zip(('zero', 'one', 'two'), shown))
    assert audits[-1][0].strip() == GOOD.strip()
    assert fields['inert_repair']['kept_index'] == 3
    entries, outcomes = ctx.sheet['audit_replays'][final.procedure.id]
    assert entries and all(outcome.notes for outcome in outcomes.values())


@pytest.mark.parametrize('replies,accepted', [((EMPTY1, EMPTY2, EMPTY3), True), ((SYNTAX, SYNTAX, SYNTAX), False)])
def test_inert_limit_is_three_and_every_checked_attempt_is_retained(monkeypatch, replies, accepted):
    ctx, final, current, survived, fields, attempts, audits = run_cycle(monkeypatch, replies=replies)
    rec = fields['repair_cycle']
    assert not survived and rec['stop_reason'] == 'inert' and rec['inert_repairs'] == 3
    assert len(attempts) == 4 and not audits and len(requests(ctx, 'inert_repair')) == 3
    assert current is attempts[3 if accepted else 0]
    assert all(row['became_current'] == accepted for row in rec['steps'])
    assert fields['inert_repair']['stop_reason'] == ('still_inert' if accepted else 'failed_checks')


def test_rejected_inert_reply_restores_replays_and_next_request_uses_previous_source(monkeypatch):
    ctx, change, report = prepared()
    saved = dict(ctx.sheet['audit_replays'])
    original_check, before = e.check, []
    def checked(candidate, context, taken=()):
        before.append(dict(context.sheet['audit_replays']))
        result = original_check(candidate, context, taken)
        if candidate.source.strip() == SYNTAX.strip():
            context.sheet['audit_replays'][change.procedure.id] = ('rejected poison', {})
        return result
    monkeypatch.setattr(e, 'check', checked)
    ctx.roles = WireRoles([encoded(ctx, SYNTAX), encoded(ctx, GOOD)])
    attempts = [report]
    final, current, survived, fields = cycle.repair_cycle(ctx, change, report, attempts=attempts)
    assert survived and before == [saved, saved]
    assert [request['change']['source'].strip() for request in requests(ctx, 'inert_repair')] == [EMPTY.strip()] * 2
    assert [row['became_current'] for row in fields['repair_cycle']['steps']] == [False, True, False]
    assert current is attempts[2]


def test_unparseable_inert_reply_is_recorded_then_cycle_continues_from_current(monkeypatch):
    ctx, final, current, survived, fields, attempts, _ = run_cycle(monkeypatch, replies=(None, None, GOOD))
    assert survived and len(attempts) == 2
    assert fields['repair_cycle']['inert_repairs'] == 2
    assert [row['parsed'] for row in fields['inert_repair']['calls']] == [False, True]
    assert len(ctx.sheet['format_retries']) == 1
    assert fields['repair_cycle']['steps'][0]['attempt_index'] == 0


def test_two_audit_fixes_and_three_audits_are_the_hard_bounds(monkeypatch):
    ctx, final, current, survived, fields, attempts, _ = run_cycle(
        monkeypatch, source=GOOD, replies=(GOOD1, GOOD2), confirmed=(True, True, True))
    rec = fields['repair_cycle']
    assert not survived and rec['stop_reason'] == fields['reason'] == 'audit_confirmed'
    assert (rec['inert_repairs'], rec['audit_fixes'], rec['audits']) == (0, 2, 3)
    assert [row['kind'] for row in rec['steps']] == ['audit', 'audit_fix', 'audit', 'audit_fix', 'audit']
    assert current is attempts[2] and len(requests(ctx, 'audit_fix')) == fields['audit_fix_calls'] == 2
    assert len(fields['audits']) == len(ctx.sheet['audits']) == 3
    assert all(set(row['call']) == {'G', 'D'} for row in rec['steps'] if row['kind'] == 'audit')


def test_inert_budget_is_shared_across_both_audit_fixes_and_can_reach_all_three_bounds(monkeypatch):
    ctx, final, current, survived, fields, attempts, _ = run_cycle(monkeypatch,
        replies=(GOOD, GOOD1, EMPTY1, EMPTY2, GOOD2), confirmed=(True, True, False))
    rec = fields['repair_cycle']
    assert survived and (rec['inert_repairs'], rec['audit_fixes'], rec['audits']) == (3, 2, 3)
    assert len(attempts) == 6 and current is attempts[5]
    assert fields['inert_repair']['kept_index'] == 5
    assert [row['change']['source'].strip() for row in requests(ctx, 'inert_repair')] == [
        EMPTY.strip(), EMPTY1.strip(), EMPTY2.strip()]


@pytest.mark.parametrize('reply', [SYNTAX, None])
def test_failed_audit_fix_is_dropped_and_preserves_previous_current_cache(monkeypatch, reply):
    ctx, final, current, survived, fields, attempts, audits = run_cycle(
        monkeypatch, source=GOOD, replies=(reply, None) if reply is None else (reply,), confirmed=(True,))
    assert not survived and fields['repair_cycle']['stop_reason'] == 'audit_fix_failed_checks'
    assert fields['reason'] == 'audit_fix_failed_checks' and current is attempts[0]
    assert ctx.sheet['audit_replays'] == audits[0][1]
    assert final.source.strip() == GOOD.strip()
    assert len(attempts) == (1 if reply is None else 2)
    assert fields['repair_cycle']['steps'][-1]['became_current'] is False


@pytest.mark.parametrize('state', ['failed_checks', 'masked_failure', 'deferred', 'excluded', 'crashed'])
def test_initial_stop_conditions_make_no_repair_or_audit_call(monkeypatch, state):
    def edit(report):
        if state == 'failed_checks':
            report['passed'] = False
        elif state == 'masked_failure':
            report['checks'].append({'check': 'authored_fatal_failure', 'passed': False})
        elif state == 'deferred':
            report['deferred'] = True
        else:
            report['inert_causes'].append('excluded_bench' if state == 'excluded' else 'crashed')
    ctx, final, current, survived, fields, attempts, audits = run_cycle(monkeypatch, report_edit=edit)
    assert not survived and not ctx.roles.wire and not audits and len(attempts) == 1
    assert fields['repair_cycle']['stop_reason'] == (
        'failed_checks' if state == 'masked_failure' else state if state in ('failed_checks', 'deferred') else 'inert')


def test_passing_but_deferred_inert_reply_is_rejected_while_audit_fix_becomes_current(monkeypatch):
    original = e.check
    def deferred(candidate, ctx, taken=()):
        result = original(candidate, ctx, taken)
        if candidate.source.strip() == GOOD1.strip():
            result['deferred'] = True
        return result
    monkeypatch.setattr(e, 'check', deferred)
    _, _, current, survived, fields, attempts, _ = run_cycle(monkeypatch, replies=(GOOD1, GOOD))
    assert survived and current is attempts[2]
    assert not fields['repair_cycle']['steps'][0]['became_current']
    # Keep the same real audit wrapper from the first run, avoiding nested scripted wrappers.
    monkeypatch.undo()
    monkeypatch.setattr(e, 'check', deferred)
    _, final, current, survived, fields, attempts, _ = run_cycle(
        monkeypatch, source=GOOD, replies=(GOOD1,), confirmed=(True,))
    assert not survived and current is attempts[1] and current['deferred']
    assert fields['repair_cycle']['stop_reason'] == 'deferred'
    assert fields['repair_cycle']['steps'][-1]['became_current']


@pytest.mark.parametrize('source,purpose', [(EMPTY, 'inert_repair'), (GOOD, 'audit_fix')])
def test_engineer_call_budget_refusal_stops_without_spending_repair(monkeypatch, source, purpose):
    ctx, change, report = prepared(source)
    ctx.spent = ctx.calls_cap  # The cycle consumes the same inherited per-unit budget.
    ctx.audit_judges = {'G': Judge(template='P1'), 'D': Judge(template='P1')}
    final, current, survived, fields = cycle.repair_cycle(ctx, change, report, attempts=[report])
    assert not survived and fields['repair_cycle']['stop_reason'] == 'no_calls_left'
    assert fields['repair_cycle']['steps'][-1]['kind'] == purpose
    assert fields['repair_cycle']['steps'][-1]['call'] is None
    assert fields['repair_cycle']['inert_repairs'] == fields['repair_cycle']['audit_fixes'] == 0


@pytest.mark.parametrize('purpose', ['inert', 'audit'])
def test_refused_format_retry_is_no_calls_left_not_parse_failure(monkeypatch, purpose):
    ctx, change, report = prepared(EMPTY if purpose == 'inert' else GOOD)
    ctx.spent = ctx.calls_cap - 1
    ctx.roles = WireRoles(['unusable'])
    ctx.audit_judges = {'G': Judge(template='P1'), 'D': Judge(template='P1')}
    _, _, survived, fields = cycle.repair_cycle(ctx, change, report, attempts=[report])
    assert not survived and fields['repair_cycle']['stop_reason'] == 'no_calls_left'
    assert ctx.sheet['format_retries'][-1]['call'] is None


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V14, CHILD])
@pytest.mark.parametrize('source,purpose', [(EMPTY, 'inert_repair'), (GOOD, 'audit_fix')])
@pytest.mark.parametrize('after_dispatch', [False, True])
def test_engineer_ledger_refusal_propagates_out_of_unit(monkeypatch, configuration, source, purpose, after_dispatch):
    ctx, _, _ = prepared(source, configuration=configuration)
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, source), encoded(ctx, GOOD1)])
    ctx.audit_judges = {'G': Judge(template='P1'), 'D': Judge(template='P1')}
    original, refused = ctx.roles.plain, []
    stop = BudgetStop('authored engineer reservation refusal')
    def plain(role, system, user, *, label, **options):
        if json.loads(user).get('request') == purpose:
            refused.append(label)
            if after_dispatch:
                # Model a charged first send followed by a refused transport resend.
                original(role, system, user, label=label, **options)
                ctx.roles.calls[-1]['sends'] = [{'charged': 13}]
            raise stop
        return original(role, system, user, label=label, **options)
    monkeypatch.setattr(ctx.roles, 'plain', plain)

    with pytest.raises(BudgetStop) as raised:
        engineer_v28.run(ctx)

    assert raised.value is stop and len(refused) == 1
    dispatched = [call for call in ctx.roles.calls if call['label'] == refused[0]]
    assert len(dispatched) == int(after_dispatch)
    if after_dispatch:
        assert dispatched[0]['sends'] == [{'charged': 13}]


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V14, CHILD])
@pytest.mark.parametrize('source,purpose', [(EMPTY, 'inert_repair'), (GOOD, 'audit_fix')])
def test_repair_format_retry_budget_refusal_propagates_out_of_unit(monkeypatch, configuration, source, purpose):
    ctx, _, _ = prepared(source, configuration=configuration)
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, source), 'unusable'])
    ctx.audit_judges = {'G': Judge(template='P1'), 'D': Judge(template='P1')}
    original, refused = ctx.roles.plain, []
    stop = BudgetStop('authored format retry reservation refusal')
    def plain(role, system, user, *, label, **options):
        if json.loads(user).get('request') == 'format_retry':
            refused.append(label)
            raise stop
        return original(role, system, user, label=label, **options)
    monkeypatch.setattr(ctx.roles, 'plain', plain)

    with pytest.raises(BudgetStop) as raised:
        engineer_v28.run(ctx)

    assert raised.value is stop and len(refused) == 1
    assert '/format-retry/' + purpose.replace('_', '-') + '/' in refused[0]
    assert len(requests(ctx, purpose)) == 1


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V14, CHILD])
@pytest.mark.parametrize('source,purpose', [(EMPTY, 'inert_repair'), (GOOD, 'audit_fix')])
def test_repair_check_budget_refusal_propagates_out_of_unit(monkeypatch, configuration, source, purpose):
    ctx, _, _ = prepared(source, configuration=configuration)
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, source), encoded(ctx, GOOD1)])
    ctx.audit_judges = {'G': Judge(template='P1'), 'D': Judge(template='P1')}
    original, checked_sources = e.check, []
    stop = BudgetStop('authored leakage reservation refusal')
    def checked(candidate, context, taken=()):
        checked_sources.append(candidate.source.strip())
        if candidate.source.strip() == GOOD1.strip():
            raise stop
        return original(candidate, context, taken)
    monkeypatch.setattr(e, 'check', checked)

    with pytest.raises(BudgetStop) as raised:
        engineer_v28.run(ctx)

    assert raised.value is stop
    assert checked_sources == [source.strip(), GOOD1.strip()]
    assert len(requests(ctx, purpose)) == 1


class BudgetJudge(Judge):
    def __init__(self, shared, refuse_at, *, after_dispatch=False, **kwargs):
        super().__init__(**kwargs)
        self.shared, self.refuse_at, self.after_dispatch = shared, refuse_at, after_dispatch
        self.refusal = BudgetStop('authored judge budget refusal')

    def plain(self, *args, **kwargs):
        self.shared.append(kwargs['label'])
        if len(self.shared) == self.refuse_at:
            if self.after_dispatch:
                super().plain(*args, **kwargs)
            raise self.refusal
        return super().plain(*args, **kwargs)


@pytest.mark.parametrize('configuration', [p.ZEBRA_PC_V14, CHILD])
@pytest.mark.parametrize('refuse_at,invalid,after_dispatch', [(1, 0, False), (2, 0, False),
                                                           (2, 1, False), (1, 0, True)])
def test_audit_judge_budget_refusal_propagates_out_of_unit(configuration, refuse_at, invalid, after_dispatch):
    ctx, _, _ = prepared(GOOD, configuration=configuration)
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, GOOD)])
    sent = []
    ctx.audit_judges = {name: BudgetJudge(sent, refuse_at, invalid=invalid, after_dispatch=after_dispatch)
                       for name in ('G', 'D')}

    with pytest.raises(BudgetStop) as raised:
        engineer_v28.run(ctx)

    assert any(raised.value is judge.refusal for judge in ctx.audit_judges.values())
    assert len(sent) == refuse_at and not ctx.sheet.get('audits')
    charged = sum(send['charged'] for judge in ctx.audit_judges.values()
                  for call in judge.calls for send in call['sends'])
    assert charged == 13 * (refuse_at - 1 + int(after_dispatch))
    if invalid:
        assert sent[-1].endswith('/format-retry')


def test_ordinary_nonbudget_incomplete_audit_keeps_existing_not_confirmed_rule():
    ctx, change, report = prepared(GOOD)
    ctx.audit_judges = {}
    _, _, survived, fields = cycle.repair_cycle(ctx, change, report, attempts=[report])
    assert survived and fields['repair_cycle']['stop_reason'] == 'survived'
    assert fields['audits'][0]['audit_incomplete'] and not fields['audits'][0].get('budget_refused')


def test_audit_fix_request_uses_current_run_counts_diagnostics_and_exact_added_paragraph(monkeypatch):
    ctx, final, current, survived, fields, attempts, _ = run_cycle(
        monkeypatch, source=WITH_DIAGNOSTIC, replies=(GOOD,), confirmed=(True, False))
    assert survived
    request = requests(ctx, 'audit_fix')[0]
    assert request['evidence']['notes'] == {'fired': 1, 'nonempty': 1, 'empty': 0, 'exceptions': 0}
    assert 'A remaining public ambiguity.' in str(request['evidence'][diagnostics_feedback.KEY])
    assert request['instruction'].count(cycle.AUDIT_FIX_PARAGRAPH) == 1
    assert request['instruction'].endswith('\n\n' + cycle.AUDIT_FIX_PARAGRAPH)
    assert cycle.prompt_pins()['audit_fix_paragraph']['text'] == cycle.AUDIT_FIX_PARAGRAPH
    wire = next(wire for wire in ctx.roles.wire if json.loads(wire['user']).get('request') == 'audit_fix')
    parent = replace(ctx, configuration=p.ZEBRA_PC_V14)
    assert wire['system'] == e._legacy_system(parent, request)


def test_audit_evidence_counts_each_verified_run_item_once_and_excludes_foreign(monkeypatch):
    ctx, change, report = prepared(WITH_DIAGNOSTIC)
    entries, outcomes = ctx.sheet['audit_replays'][change.procedure.id]
    first = entries[0]
    duplicate = {**first, 'cell': 'duplicate'}
    foreign = {**first, 'cell': 'generated', 'item': 'generated'}
    ctx.sheet['audit_replays'][change.procedure.id] = ([first, duplicate, foreign], {
        first['cell']: outcomes[first['cell']], 'duplicate': outcomes[first['cell']],
        'generated': outcomes[first['cell']]})
    original = e._verified_run_cells
    monkeypatch.setattr(e, '_verified_run_cells', lambda context: {**original(context), 'duplicate': ctx.trajectories[0]})
    evidence = cycle.audit_fix_evidence(ctx, change, report)
    assert evidence['notes'] == {'fired': 1, 'nonempty': 1, 'empty': 0, 'exceptions': 0}
    assert evidence[diagnostics_feedback.KEY]['items_count'] == 1


def test_audit_fix_diagnostic_failure_is_nonfatal_and_preserves_note_counts(monkeypatch):
    ctx, change, report = prepared(GOOD)
    monkeypatch.setattr(diagnostics_feedback, 'from_checks', lambda *a, **kw: (_ for _ in ()).throw(ValueError('fixture')))
    evidence = cycle.audit_fix_evidence(ctx, change, report)
    assert evidence == {'notes': {'fired': 1, 'nonempty': 1, 'empty': 0, 'exceptions': 0}}
    assert ctx.sheet['diagnostics_omissions']['stages'] == {'audit_fix_evidence': 1}


def test_parent_inert_request_and_record_shape_remain_the_original_single_repair():
    ctx, change, report = prepared(configuration=p.ZEBRA_PC_V14)
    ctx.roles = WireRoles([encoded(ctx, EMPTY1), encoded(ctx, GOOD)])
    final, current, checked, rec = engineer_v294.repair(ctx, change, report)
    assert final is change and current is report and len(checked) == 1 and rec['stop_reason'] == 'still_inert'
    assert set(rec) == {'causes', 'calls', 'kept_index', 'stop_reason'} and len(ctx.roles.wire) == 1
    assert cycle.AUDIT_FIX_PARAGRAPH not in json.dumps(ctx.roles.wire)


def test_full_engineer_unit_keeps_preexisting_fix_and_fault_repair_before_cycle(monkeypatch):
    from tests.test_execskill_v291_engineer import CRASH, run
    ctx, package, unit = run(SYNTAX, CRASH, EMPTY, GOOD, configuration=CHILD)
    assert package is not None
    row = unit['changes'][0]
    assert row['fix_calls'] == row['fault_repair']['kept_index'] == 1
    assert row['repair_cycle']['stop_reason'] == 'survived'
    assert row['repair_cycle']['inert_repairs'] == row['repair_cycle']['audits'] == 1
    assert row['kept_attempt'] == 3 and len(row['attempts']) == 4
    assert unit['inert_repair_calls'] == unit['fault_repair_calls'] == 1
    assert unit['audit_fix_calls'] == 0
    assert [json.loads(wire['user']).get('request') for wire in ctx.roles.wire
            if json.loads(wire['user']).get('request')] == ['analyse', 'propose', 'fix', 'fault_repair', 'inert_repair']
