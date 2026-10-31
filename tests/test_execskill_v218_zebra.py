"""main-v6's Zebra step runs v15's real diagnostics/repair code on authored fixtures."""
from dataclasses import replace
import json

import pytest

from skillopt.coevo5.outcomes import BudgetStop
from skillopt.execskill import (audit, diagnostics, diagnostics_feedback, engineer, engineer_v216,
                               instruction_start, profiles as p, zebralogic)
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_v291_engineer import encoded
from tests.test_execskill_v216_cycle import EMPTY, EMPTY1, EMPTY2, GOOD, GOOD1, GOOD2, WITH_DIAGNOSTIC
from tests.test_execskill_v215_diagnostics_runtime import FIELDS, run as run_shell
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def zebra_context():
    ctx, _ = context(configuration=p.ZEBRA_PC_V15)
    ctx = replace(ctx, configuration=p.MAIN_V6, card=zebralogic.CARD_TEXT)
    ctx.current = list(ctx.trajectories)
    ctx.audit_judges = {'G': Judge(), 'D': Judge()}
    return ctx


def payloads(ctx, request):
    return [json.loads(row['user']) for row in ctx.roles.wire if json.loads(row['user']).get('request') == request]


def test_full_main_v6_zebra_engineer_reaches_all_three_v15_bounds(monkeypatch):
    ctx = zebra_context()
    ctx.roles = WireRoles([engineer_reply({'findings': []}, [])] +
                         [encoded(ctx, source) for source in (EMPTY, GOOD, GOOD1, EMPTY1, EMPTY2, GOOD2)])
    original, audits = audit.audit1, []

    def audit_current(context, candidate, checked):
        confirmed = len(audits) < 2
        context.audit_judges = {name: Judge(template='P1' if confirmed else None) for name in ('G', 'D')}
        audits.append(candidate.source)
        return original(context, candidate, checked)

    monkeypatch.setattr(audit, 'audit1', audit_current)
    package, result = engineer.run_train(ctx)
    assert package is not None and package.procedures[0].source.strip() == GOOD2.strip()
    cycle = result['changes'][0]['repair_cycle']
    assert (cycle['inert_repairs'], cycle['audit_fixes'], cycle['audits'], cycle['stop_reason']) == (3, 2, 3, 'survived')
    assert len(audits) == 3 and len(result['changes'][0]['attempts']) == 6
    repairs = payloads(ctx, 'inert_repair')
    assert [row['change']['source'].strip() for row in repairs] == [EMPTY.strip(), EMPTY1.strip(), EMPTY2.strip()]
    assert all(word in str(row['evidence'][diagnostics_feedback.KEY])
               for row, word in zip(repairs, ('zero', 'one', 'two')))
    assert ctx.calls_cap == p.TRAIN_ENGINEER_CALL_BUDGETS[p.ZEBRA_PC_V15]


def test_main_v6_audit_fix_carries_current_note_counts_diagnostics_and_pinned_paragraph(monkeypatch):
    ctx = zebra_context()
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, WITH_DIAGNOSTIC), encoded(ctx, GOOD)])
    original, calls = audit.audit1, []

    def first_confirmed(context, candidate, checked):
        context.audit_judges = {name: Judge(template='P1' if not calls else None) for name in ('G', 'D')}
        calls.append(candidate.source)
        return original(context, candidate, checked)

    monkeypatch.setattr(audit, 'audit1', first_confirmed)
    package, result = engineer.run_train(ctx)
    assert package is not None and result['changes'][0]['repair_cycle']['audit_fixes'] == 1
    request = payloads(ctx, 'audit_fix')[0]
    assert request['evidence']['notes'] == {'fired': 1, 'nonempty': 1, 'empty': 0, 'exceptions': 0}
    assert 'A remaining public ambiguity.' in str(request['evidence'][diagnostics_feedback.KEY])
    assert request['instruction'].count(engineer_v216.AUDIT_FIX_PARAGRAPH) == 1
    assert request['instruction'].endswith('\n\n' + engineer_v216.AUDIT_FIX_PARAGRAPH)


@pytest.mark.parametrize('purpose,source', [('inert_repair', EMPTY), ('audit_fix', GOOD)])
def test_main_v6_repair_reservation_refusal_propagates(purpose, source, monkeypatch):
    ctx = zebra_context()
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, source)])
    ctx.audit_judges = {name: Judge(template='P1') for name in ('G', 'D')}
    original = ctx.roles.plain
    stop = BudgetStop('Authored main-v6 budget refusal')

    def refuse(role, system, user, **kwargs):
        if json.loads(user).get('request') == purpose:
            raise stop
        return original(role, system, user, **kwargs)

    monkeypatch.setattr(ctx.roles, 'plain', refuse)
    with pytest.raises(BudgetStop) as raised:
        engineer.run_train(ctx)
    assert raised.value is stop


@pytest.mark.parametrize('arm', ['F', 'C', 'B', 'S', "S'"])
def test_main_v6_zebra_diagnostics_remain_engineer_only_in_every_arm(arm):
    baseline, before, _ = run_shell(FIELDS, configuration=p.ZEBRA_PC_V15, arm=arm)
    found, after, _ = run_shell({**FIELDS, 'diagnostics': ['Clue 6 remains unparsed.']},
                              configuration=p.MAIN_V6, arm=arm)
    assert before == after
    assert found['shell']['notes_chars'] == baseline['shell']['notes_chars']
    assert found['shell']['faults'] == baseline['shell']['faults']
    assert 'Clue 6 remains unparsed.' not in json.dumps(after)


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'spreadsheetbench'])
def test_other_engineer_benches_keep_main_v4_prompt_and_budget(bench):
    old, _ = context(configuration=p.MAIN_V2_3, bench='officeqa')
    old = replace(old, configuration=p.MAIN_V5, bench=bench, routing_shared_worker=False,
                  card=instruction_start.pins()[bench]['text'])
    child = replace(old, configuration=p.MAIN_V6)
    assert child.calls_cap == old.calls_cap
    assert not p.uses_v215(p.MAIN_V6, bench) and not p.uses_v216(p.MAIN_V6, bench)
    assert not diagnostics.enabled(p.MAIN_V6, bench)
    assert p.engineer_prompt(p.MAIN_V6, bench, 'train') == p.engineer_prompt(p.MAIN_V5, bench, 'train')
    assert p.machinery_configuration(p.MAIN_V6, bench) == p.MAIN_V4


def test_main_v6_zebra_card_and_machinery_remain_explicit():
    ctx = zebra_context()
    assert ctx.card == zebralogic.CARD_TEXT
    assert p.machinery_configuration(p.MAIN_V6, 'zebralogic') == p.ZEBRA_PC_V15
    assert p.uses_v215(p.MAIN_V6, 'zebralogic') and p.uses_v216(p.MAIN_V6, 'zebralogic')
    assert not p.uses_v215(p.MAIN_V5, 'zebralogic') and not p.uses_v216(p.MAIN_V5, 'zebralogic')
