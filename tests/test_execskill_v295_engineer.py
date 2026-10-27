"""v2.9.5 pinned abstention prompts on the actual offline engineer call path."""
import json

import pytest

from skillopt.execskill import (audit, engineer as e, engineer_v29, engineer_v291,
                               engineer_v293, engineer_v294, engineer_v295, profiles as p)
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v291_engineer import ALF_GOOD, GOOD, run
from tests.test_execskill_v294_repair import NO_HOOK
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


SENTENCE = ('When a program cannot verify its result on an item, it should return no note for that item: '
            'unverified warnings or partial results tend to turn correct answers wrong, and training counts '
            'every answer they break.')
CHILDREN = [('zebra-pc-v12', 'zebra-pc-v11', GOOD, 10, 8),
            ('alfworld-v9', 'alfworld-v8', ALF_GOOD, 6, 4)]


@pytest.mark.parametrize('configuration,parent,good,rounds,patience', CHILDREN)
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_prompt_has_exact_abstention_rule_and_configured_round_limits(configuration, parent, good,
                                                                        rounds, patience, mode):
    prompt = engineer_v295.system(configuration, train=mode == 'train')
    assert prompt.endswith(SENTENCE + '\n') and prompt.count(SENTENCE) == 1
    assert '(v2.9.5)' in prompt and '(v2.9.4)' not in prompt
    assert ('Up to %d training rounds, patience %d;' % (rounds, patience) if mode == 'train' else
            'Training, when used, has patience %d over at most %d rounds.' % (patience, rounds)) in prompt
    parent_prompt = engineer_v294.system(parent, train=mode == 'train')
    assert SENTENCE not in parent_prompt and '(v2.9.4)' in parent_prompt
    assert engineer_v295.prompt_pins()[configuration + '/' + mode] == {
        'text': prompt, 'sha256': audit.text_sha256(prompt)}


@pytest.mark.parametrize('configuration,parent,good,rounds,patience', CHILDREN)
@pytest.mark.parametrize('mode', ['single', 'train'])
@pytest.mark.parametrize('request_kind', ['propose', 'fix', 'format_retry', 'audit_fix', 'fault_repair', 'inert_repair'])
def test_every_request_uses_child_system_with_inherited_suffix(configuration, parent, good,
                                                               rounds, patience, mode, request_kind):
    ctx, _ = context(configuration=configuration, bench=p.active_benches(configuration)[0], mode=mode)
    ctx.roles = WireRoles(['authored reply'])
    user = {'request': request_kind, 'evidence': {'no_effect_hook': {'effect_hooks': ['before_call']}}}
    reply, call = e._ask(ctx, user, 'wire/' + request_kind)
    assert reply == 'authored reply' and call
    suffix = {'propose': '', 'fix': engineer_v29.FIX_SYSTEM,
              'format_retry': engineer_v293.FORMAT_RETRY_SYSTEM, 'audit_fix': engineer_v29.AUDIT_FIX_SYSTEM,
              'fault_repair': engineer_v291.FAULT_REPAIR_INSTRUCTION,
              'inert_repair': engineer_v294.inert_repair_instruction(configuration, ['no_effect_hook'])}[request_kind]
    assert ctx.roles.wire[0]['system'] == engineer_v295.system(configuration, train=mode == 'train') + suffix
    assert json.loads(ctx.roles.wire[0]['user']) == user


@pytest.mark.parametrize('configuration,parent,good,rounds,patience', CHILDREN)
@pytest.mark.parametrize('mode', ['single', 'train'])
def test_inherited_inert_repair_reaches_audit_with_new_record_and_prompt_pins(configuration, parent, good,
                                                                           rounds, patience, mode):
    ctx, package, record = run(NO_HOOK, good, configuration=configuration, mode=mode)
    assert package is not None and record['inert_repair_calls'] == 1
    assert record['changes'][0]['inert_repair']['stop_reason'] == 'fixed'
    assert not record['changes'][0]['inert'] and len(record['changes'][0]['audits']) == 1
    assert record['version'] == p.kind('engineer-v2-9-5')
    assert record['prompt_sha256'] == audit.text_sha256(engineer_v295.system(configuration, train=mode == 'train'))
    assert record['calls'] == 2 and ctx.calls_cap == (41 if mode == 'train' else 31)
    if mode == 'train':
        proposal = next(json.loads(wire['user']) for wire in ctx.roles.wire if wire['label'].endswith('/propose'))
        assert proposal['rounds'] == rounds
