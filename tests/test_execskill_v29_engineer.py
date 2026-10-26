"""Offline actual engineer orchestration: one audit fix, fresh checks, and disclosure isolation."""
import json
from dataclasses import replace

import pytest

from skillopt.execskill import audit, engineer as e, engineer_v29, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import GOOD, change
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v26_references import fixture
from tests.test_execskill_v29_audit import Judge
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CONFIG='zebra-pc-v7'
FIXED=GOOD + '\n# AUDIT_FIXED\n'
SYNTAX='def before_call(view, state):\n    return {\n'


def encoded(proposed):
    return engineer_reply({'changes':[proposed.entry]},[proposed.source])


class FixAwareJudge(Judge):
    def plain(self,role,system,user,**kwargs):
        self.template='P2' if system==audit.A_SYSTEM and 'AUDIT_FIXED' not in user else None
        return super().plain(role,system,user,**kwargs)


def run(*sources, judges=None, mode='train'):
    ctx,_=fixture(configuration=CONFIG,mode=mode)
    ctx.audit_judges=judges or {'G':Judge(),'D':Judge()}
    replies=[encoded(change(ctx,source)) if source is not None else 'unusable' for source in sources]
    ctx.roles=WireRoles(([engineer_reply({'findings':[]},[])] if mode=='train' else [])+replies)
    package,record=(e.run_train(ctx) if mode=='train' else e.run(ctx))
    return ctx,package,record


def test_audit_pass_keeps_change_and_next_round_lint_carries_decision():
    ctx,package,record=run(GOOD)
    assert package is not None and len(record['audits'])==1
    assert record['audit_fix_calls']==0 and record['audit_incomplete']==0
    assert record['lint'][0]['audit']['decision']=='pass'
    subsequent=replace(ctx,round=2,lint=record['lint'])
    assert e.payload(subsequent)['lint'][0]['audit']['decision']=='pass'
    assert all(c['max_tokens']==8192 for result in record['audits'] for pair in result['requests'] for c in pair['requests'].values())


@pytest.mark.parametrize('mode',['single','train'])
def test_confirmed_once_fix_then_pass_not_a_train_behavior_fix(mode):
    judges={'G':FixAwareJudge(),'D':FixAwareJudge()}
    ctx,package,record=run(GOOD,FIXED,judges=judges,mode=mode)
    row=record['changes'][0]
    assert package is not None and package.procedures[0].source.strip()==FIXED.strip()
    assert row['fix_calls']==0 and row['audit_fix_calls']==1 and record['calls']==2
    assert len(row['audits'])==2 and row['audits'][0]['confirmed'] and not row['audits'][1]['confirmed']
    payloads=[json.loads(w['user']) for w in ctx.roles.wire]
    assert sum(w.get('request')=='audit_fix' for w in payloads)==1
    assert not any(w.get('request')=='fix' for w in payloads)
    assert all(len(w['instruction'])>0 for w in payloads if w.get('request')=='audit_fix')


def test_still_confirmed_after_audit_fix_is_removed():
    ctx,package,record=run(GOOD,FIXED,judges={'G':Judge(template='P2'),'D':Judge(template='P2')})
    assert package is None
    row=record['changes'][0]
    assert row['reason']=='audit_confirmed' and not row['survived']
    assert row['fix_calls']==0 and row['audit_fix_calls']==1 and len(row['audits'])==2


def test_audit_fix_fatal_check_drops_without_restarting_behavior_fix_loop():
    ctx,package,record=run(GOOD,SYNTAX,judges={'G':Judge(template='P2'),'D':Judge(template='P2')})
    assert package is None
    row=record['changes'][0]
    assert row['reason']=='audit_fix_failed_checks' and row['attempts'][-1]['failed']=='C2'
    assert row['fix_calls']==0 and row['audit_fix_calls']==1
    assert len(record['audits'])==1 and record['calls']==2


def test_audit_fix_uses_generic_format_retry_not_train_fixes():
    ctx,package,record=run(GOOD,None,FIXED,judges={'G':FixAwareJudge(),'D':FixAwareJudge()})
    assert package is not None and record['calls']==3
    assert record['changes'][0]['fix_calls']==0 and record['audit_fix_calls']==1
    assert record['format_retries'][0]['purpose']=='audit-fix/1'
    assert record['format_retries'][0]['parsed']


def test_unavailable_judge_continues_with_explicit_incomplete_and_advisory():
    _,package,record=run(GOOD,judges={'G':Judge(invalid=100),'D':Judge(template='P2')})
    assert package is not None and record['audit_incomplete']==1
    assert record['audits'][0]['advisory'] and not record['audits'][0]['confirmed']


def test_inert_and_metadata_changes_never_get_audit_calls():
    ctx,package,record=run('def applies(view):\n    return False\ndef before_call(view,state):\n    return {}\n')
    assert package is None and record['changes'][0]['inert']
    assert record['audits']==[] and all(not judge.calls for judge in ctx.audit_judges.values())
    ctx,_=fixture(configuration=CONFIG)
    ctx.audit_judges={'G':Judge(),'D':Judge()}
    ctx.roles=WireRoles([engineer_reply({'findings':[]},[]),engineer_reply({'changes':[{'kind':'deletion','id':'fx-absent'}]},[])])
    _,record=e.run_train(ctx)
    assert record['audits']==[]


def test_audit1_only_run_c6_public_input_and_never_solver_replies_or_reference():
    ctx,_=fixture(configuration=CONFIG)
    proposed=change(ctx,GOOD)
    report=e.check(proposed,ctx)
    assert report['passed']
    entries,outcomes=ctx.sheet['audit_replays'][proposed.procedure.id]
    original=entries[0]
    injected={**original,'cell':'confirm-cell','item':'CONFIRM_ID_SENTINEL',
              'request_view':{'question':'CONFIRM_CONTENT_SENTINEL','columns':['Name']}}
    ctx.sheet['audit_replays'][proposed.procedure.id]=(entries+[injected],{**outcomes,'confirm-cell':next(iter(outcomes.values()))})
    ctx.audit_judges={'G':Judge(),'D':Judge()}
    result=audit.audit1(ctx,proposed,report)
    serialized=json.dumps(result)
    assert 'CONFIRM_CONTENT_SENTINEL' not in serialized and 'CONFIRM_ID_SENTINEL' not in serialized
    own={t['task_id'] for t in ctx.trajectories}
    assert all(s['item'] in own for s in result['sampling']['situations'])
    for pair in result['requests']:
        user=pair['requests']['G']['user']
        assert 'current_reply' not in user and 'candidate_reply' not in user and 'reference_answer' not in user


def test_new_prompts_and_pins_state_optional_applies_policy_audits_and_confirmation():
    for config in ('zebra-pc-v7','alfworld-v4'):
        for train in (False,True):
            text=engineer_v29.system(config,train=train)
            assert 'applies(view) -> bool is optional; without it the procedure runs on every item' in text
            assert 'you may restate requirements the task input itself states' in text
            assert 'two independent reviewers' in text and 'fixed > broken' in text
            assert 'are removed and recorded' not in text and '(v2.9)' in text
    for pin in engineer_v29.prompt_pins().values():
        assert audit.text_sha256(pin['text'])==pin['sha256']
    assert p.ENGINEER_CALL_BUDGETS[CONFIG]==16 and p.TRAIN_ENGINEER_CALL_BUDGETS[CONFIG]==26
