"""Deterministic, bounded writer payloads using authored practice traces only."""
import json
from pathlib import Path

import pytest

from skillopt.execskill import profiles as p, v225_cards as c, v225_writer as w
from skillopt.execskill.package import empty
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def row(n, token='fail', **kw):
    return {'unit': 'G/s1-searchqa/run', 'bench': 'searchqa', 'task_id': f'practice-{n}', 'run': 0,
            'arm': 'S', 'token': token, 'view': f'Public authored question {n}', 'reply': 'A bounded response.',
            'evidence': 'engineering_fixture', **kw}


def select(rows, **kw):
    return w.select_examples(rows, **{'chain': 'G', 'bench': 'searchqa', 'k': 1, 'c': 1,
        'references': {r['task_id']: 'Authored reference' for r in rows if r['token'] == 'fail'},
        'allowed_ids': [r['task_id'] for r in rows], **kw})


def test_example_caps_order_and_first_registered_run_are_deterministic():
    rows = [row(i) for i in range(20)] + [row(i + 20, 'pass') for i in range(10)]
    expected = select(rows)
    assert select(list(reversed(rows))) == expected
    assert sum(e['outcome'] == 'fail' for e in expected) == 12
    assert sum(e['outcome'] == 'pass' for e in expected) == 6
    assert all(('reference' in e) == (e['outcome'] == 'fail') for e in expected)
    assert select([row(0, run=1, reply='Later run'), row(0, reply='First run')])[0]['reply'] == 'First run'


def test_revision_prioritizes_broken_then_fixed_items():
    rows = [row(i, unit='G/s1-searchqa/card-train-c1', arm="S'", card_broken=i == 19) for i in range(20)]
    rows += [row(i + 20, 'pass', unit='G/s1-searchqa/card-train-c1', arm="S'", card_fixed=i == 9) for i in range(10)]
    selected = select(rows, c=2)
    assert selected[0]['view'] == 'Public authored question 19'
    assert selected[12]['view'] == 'Public authored question 29'


@pytest.mark.parametrize('unit', ['G/s1-searchqa/accept', 'G/s1-searchqa/confirm-r1',
    'G/s1-searchqa/card-accept-c1', 'G/s1-searchqa/card-confirm-c1', 'G/s1-searchqa/card-cross-officeqa',
    'G/test/s1/searchqa', 'G/s1-searchqa/harm', 'D/s1-searchqa/run', 'G/s2-searchqa/run'])
def test_writer_refuses_any_acceptance_confirmation_harm_or_test_row(unit):
    with pytest.raises(ValueError, match='practice run/card-train'):
        select([row(0, unit=unit)])


def test_unregistered_item_unsealed_row_and_future_training_are_refused():
    with pytest.raises(ValueError, match='run-slice'):
        select([row(0)], allowed_ids=[] , references={})
    with pytest.raises(ValueError, match='authored'):
        select([row(0, evidence='main_v9_real_run')])
    with pytest.raises(ValueError, match='immediately preceding'):
        select([row(0, unit='G/s1-searchqa/card-train-c2', arm="S'")], c=2)


def test_truncation_preserves_registered_head_tail_and_references():
    got = select([row(0, view='a' * 3500 + 'z' * 1000, reply='h' * 500 + 't' * 1500)],
                 references={'practice-0': 'r' * 700})[0]
    assert len(got['view']) == 3000 and got['view'].startswith('a' * 100) and got['view'].endswith('z' * 1000)
    assert got['reply'] == 'h' * 300 + w.TRUNCATION_MARK + 't' * 1200
    assert got['reference'] == 'r' * 300


def test_request_fitting_drops_successes_before_failures_and_bounds_both_calls():
    examples = [{'view': 'x' * 9000, 'reply': 'y' * 9000, 'outcome': 'fail'} for _ in range(12)]
    examples += [{'view': 's' * 9000, 'reply': 'u' * 9000, 'outcome': 'pass'} for _ in range(6)]
    request, dropped = w.build_request(bench='searchqa', runtime={}, current_card='', examples=examples, c=1)
    assert dropped['successes'] == 6 and dropped['failures'] > 0
    assert len(json.dumps(request, ensure_ascii=False, sort_keys=True)) <= 120000
    assert set(request) == {'request', 'task_card', 'format_block', 'current_card', 'card_rules', 'examples', 'evidence'}


class FakeRoles:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
    def plain(self, role, system, user, *, label, max_tokens):
        assert role == 'card_writer' and max_tokens == 32768
        self.calls.append({'role': role, 'system': system, 'user': user, 'label': label, 'max_tokens': max_tokens})
        return next(self.replies)


def write(roles, **kw):
    return w.write(roles, **{'chain': 'G', 'bench': 'searchqa', 'k': 1, 'c': 1,
        'incumbent': empty(step='G/s0', evidence='engineering_fixture'), 'rows': [row(0)],
        'references': {'practice-0': 'Verdant Mountain'}, 'allowed_ids': ['practice-0'], 'corpus': {},
        'practice_ids': ['practice-0'], **kw})


def test_same_inputs_fake_reply_produce_byte_identical_requests_and_card():
    first, second = FakeRoles(['Weigh the supplied evidence.']), FakeRoles(['Weigh the supplied evidence.'])
    assert write(first) == write(second)
    assert first.calls == second.calls
    payload = json.loads(first.calls[0]['user'])
    assert payload['current_card'] == '' and payload['evidence'] == 'practice_only'


def test_retry_once_then_second_static_failure_ends_round():
    roles = FakeRoles(['<answer>bad</answer>', 'Still <answer>bad</answer>', 'unreachable'])
    result = write(roles)
    assert result['calls'] == 2 and len(roles.calls) == 2 and result['text'] is None
    assert result['decision'] == 'card_rejected_static' and result['static'] == 'format_markers'
    assert c.CARD_RETRY.format(reason=c.RETRY_REASONS['format_markers']) in roles.calls[1]['user']
    assert 'bad</answer>' not in roles.calls[1]['user']


def test_wrapping_fence_reader_and_successful_retry():
    roles = FakeRoles(['', '```markdown\nCompare the supplied sources carefully.\n```'])
    result = write(roles)
    assert result['calls'] == 2 and result['text'] == 'Compare the supplied sources carefully.\n'
    assert result['static'] is None


def test_revise_feedback_is_count_only_and_no_frozen_card_is_disclosed():
    req, _ = w.build_request(bench='searchqa', runtime={}, current_card='Current learned guidance.',
        examples=[], c=2, previous_card='Earlier learned guidance.', result={'stage': 'training',
            'decision': 'reject', 'clause': 'gain_floor', 'fixed': 2, 'broken': 0,
            'secret_rows': [{'answer': 'not exposed'}]})
    assert set(req['result']) == set(w.RESULT_FIELDS)
    assert 'secret_rows' not in json.dumps(req)
    assert req['request'] == 'revise'
    assert req['current_card'] == 'Current learned guidance.'


def test_prompt_and_zebra_pins_match_independent_fixture_bytes():
    root = Path(__file__).parent / 'fixtures/execskill/v225_cards'
    pins = json.loads((root / 'pins.json').read_text())
    for name, pin in c.prompt_pins().items():
        filename = 'zebralogic-task-card.txt' if name == 'ZEBRA_TASK_CARD' else name.lower() + '.txt'
        assert (root / filename).read_text() == pin['text']
        assert c.sha256((root / filename).read_text()) == pins['prompts'][name] == pin['sha256']


def test_writer_count_bound_and_zebra_public_card():
    assert c.CARD_ROUNDS * 2 * 4 == 24
    assert '5 or 6 houses, 2 to 6 characteristics' in w.task_card('zebralogic', {})
    assert 'every cell matches' in w.task_card('zebralogic', {})


def test_second_reply_survives_failure_before_unit_completion(tmp_path, monkeypatch):
    state = tmp_path/'G'/'card-writer'
    roles = FakeRoles(['<answer>bad</answer>', 'Compare the supplied evidence carefully.'])
    original = c.card_violation
    screened = []
    def interrupt_after_second_reply(*args, **kwargs):
        screened.append(args[0])
        if len(screened) == 2:
            raise RuntimeError('authored interruption before unit completion')
        return original(*args, **kwargs)
    monkeypatch.setattr(c,'card_violation',interrupt_after_second_reply)
    with pytest.raises(RuntimeError,match='before unit completion'):
        write(roles,state_root=state)
    assert len(roles.calls) == 2 and len(list((state/'dispatches').glob('*.json'))) == 2
    assert len(list((state/'replies').glob('*.json'))) == 2
    monkeypatch.setattr(c,'card_violation',original)
    resumed_roles = FakeRoles([])
    resumed = write(resumed_roles,state_root=state)
    assert resumed_roles.calls == [] and resumed['calls'] == 2
    assert resumed['text'] == 'Compare the supplied evidence carefully.\n'
    assert resumed['call_record']['calls'] == roles.calls
    assert write(FakeRoles([]),state_root=state) == resumed


def test_reservation_is_durable_before_transport_and_lost_reply_is_not_resent(tmp_path):
    from skillopt.execskill.errors import BudgetStop
    state = tmp_path/'G'/'card-writer'
    class Interrupted(FakeRoles):
        def plain(self, *args, **kwargs):
            assert len(list((state/'dispatches').glob('*.json'))) == 1
            raise RuntimeError('authored uncertain transport')
    with pytest.raises(RuntimeError,match='uncertain transport'):
        write(Interrupted([]),state_root=state)
    resumed = FakeRoles(['A reply that must never be requested.'])
    with pytest.raises(BudgetStop,match='reserved without a persisted reply'):
        write(resumed,state_root=state)
    assert resumed.calls == []


def test_twenty_four_calls_are_enforced_across_all_rounds_and_attempts(tmp_path):
    from skillopt.execskill.errors import BudgetStop
    state = tmp_path/'G'/'card-writer'
    for k,bench in enumerate(c.BENCHES[:-1],1):
        for number in (1,2,3):
            trace = row(0, bench=bench, unit=f'G/s{k}-{bench}/'+('run' if number==1 else f'card-train-c{number-1}'),
                        arm='S' if number==1 else "S'")
            kwargs = {'bench':bench,'k':k,'c':number,'rows':[trace],
                'state_root':state,'previous_card':'Previous guidance.',
                'result':{'stage':'training','decision':'reject','clause':'gain_floor'}}
            result = write(FakeRoles(['<answer>bad</answer>']*2),**kwargs)
            assert result['calls'] == 2
            resumed = FakeRoles([])
            assert write(resumed,**kwargs) == result and resumed.calls == []
    assert len(list((state/'dispatches').glob('*.json'))) == 24
    refused = FakeRoles(['Never dispatched.'])
    with pytest.raises(BudgetStop,match='twenty-four per chain'):
        write(refused,state_root=state,k=5,rows=[row(0,unit='G/s5-searchqa/run')])
    assert refused.calls == [] and len(list((state/'dispatches').glob('*.json'))) == 24
    with pytest.raises(ValueError,match='two writer dispatches'):
        w._durable_reply(refused,state_root=state,binding={},system='system',sent='user',
                         label='third',ordinal=3,evidence='engineering_fixture')


def test_durable_round_refuses_changed_request_and_production_without_state(tmp_path):
    state = tmp_path/'G'/'card-writer'
    write(FakeRoles(['Compare the supplied evidence carefully.']),state_root=state)
    with pytest.raises(ValueError,match='Immutable artifact differs'):
        write(FakeRoles([]),state_root=state,rows=[row(0,view='Different public practice view')])
    with pytest.raises(ValueError,match='durable per-chain'):
        write(FakeRoles([]),incumbent=empty(step='G/s0',evidence='main_v9_real_run'))


def test_six_call_bench_cap_cannot_be_reset_by_changing_step_identity(tmp_path):
    from skillopt.execskill.errors import BudgetStop
    state = tmp_path/'G'/'card-writer'
    for number in (1,2,3):
        trace = row(0,unit='G/s1-searchqa/'+('run' if number==1 else f'card-train-c{number-1}'),
                    arm='S' if number==1 else "S'")
        write(FakeRoles(['<answer>bad</answer>']*2),state_root=state,c=number,rows=[trace],
            previous_card='Previous guidance.',result={'stage':'training','decision':'reject','clause':'gain_floor'})
    refused = FakeRoles(['Never dispatched.'])
    with pytest.raises(BudgetStop,match='six per bench'):
        write(refused,state_root=state,k=2,rows=[row(0,unit='G/s2-searchqa/run')])
    assert refused.calls == [] and len(list((state/'dispatches').glob('*.json'))) == 6


def smoke_row(evidence):
    return p.record('trajectory',evidence,{'unit':'G/v225-smoke/price/searchqa/C0',
        'arm':'C0','bench':'searchqa','task_id':'practice-0','run':0,'token':'pass',
        'calls':[{'purpose':'first','user':'Authored public practice information'}],
        'replies':['Authored practice reply'],'deciding_receipt':0})


@pytest.mark.parametrize('incumbent_evidence,row_evidence', [
    ('main_v9_real_run','engineering_fixture'),('engineering_fixture','main_v9_real_run'),
    ('smoke','main_v9_real_run'),('main_v9_real_run','main_v9_real_run')])
def test_smoke_writer_rejects_production_incumbent_or_offered_rows_before_dispatch(
        tmp_path, incumbent_evidence, row_evidence):
    roles = FakeRoles(['Never dispatched.'])
    with pytest.raises(ValueError,match='smoke or fixture evidence'):
        write(roles,smoke=True,state_root=tmp_path/'writer',
            incumbent=empty(step='G/s0',evidence=incumbent_evidence),rows=[smoke_row(row_evidence)])
    assert roles.calls == [] and not list(tmp_path.rglob('dispatches/*.json'))


@pytest.mark.parametrize('evidence',['smoke','engineering_fixture'])
def test_smoke_writer_accepts_only_explicit_smoke_or_fixture_provenance(tmp_path,evidence):
    result = write(FakeRoles(['Compare the supplied evidence carefully.']),smoke=True,
        state_root=tmp_path/'writer',incumbent=empty(step='G/s0',evidence=evidence),rows=[smoke_row(evidence)])
    assert result['text'] == 'Compare the supplied evidence carefully.\n'
    with pytest.raises(ValueError,match='incumbent requires smoke or fixture evidence'):
        select([smoke_row(evidence)],smoke=True)
