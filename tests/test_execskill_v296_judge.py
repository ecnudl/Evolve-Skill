"""The v2.9.6 ALFWorld format rule and runtime identity, without services."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

import pytest

from skillopt.coevo5.outcomes import Verdict
from skillopt.execskill import alfworld_format as rule, judge, profiles as p


BEFORE = json.loads((Path(__file__).parent / 'fixtures/execskill/v296_parents_before.json').read_text())
EPISODES = BEFORE['k1_episodes']
EXPECTED = {
    '0_of_8': False, '3_of_8': False, '4_of_8': False, '7_of_8': False,
    '9_of_10': False, '10_of_10': False, 'no_steps': None, 'no_shell': None,
    'unknown': None, 'invalid_action_format': True, 'invalid_no_steps': None,
}
BELOW_HALF = {
    **EXPECTED, '0_of_8': True, '3_of_8': True, 'invalid_no_steps': True,
}


def run_episode(label, runtime, *, case=None):
    case = EPISODES[label] if case is None else case
    return judge.judge('alfworld', {'game_file': 'authored'}, {}, case['prediction'],
                       runtime=runtime, score=case['score'], verdict=Verdict(**case['verdict']))


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


@pytest.mark.parametrize('label', sorted(EPISODES))
def test_k1_child_judge_uses_readable_action_and_keeps_both_diagnostics(label):
    found = run_episode(label, rule.bind({}, p.ALFWORLD_V10))
    older = BEFORE['configurations'][p.ALFWORLD_V9]['k1_judge'][label]
    assert found['format'] == {
        **older['format'], 'violation': EXPECTED[label],
        'violation_at_9_10': older['format']['violation'],
        'violation_below_half': BELOW_HALF[label], 'rule': rule.RULE,
    }
    assert found['version'] == p.kind('judge-v2-9-6')
    assert found['scorer'] == 'execskill-judge-v2-9-6'
    assert {key: value for key, value in found.items() if key not in ('format', 'version', 'scorer')} == {
        key: value for key, value in older.items() if key not in ('format', 'version', 'scorer')}


@pytest.mark.parametrize('configuration', sorted(BEFORE['configurations']))
@pytest.mark.parametrize('label', sorted(EPISODES))
def test_k1_every_snapshotted_parent_judge_output_is_byte_identical(configuration, label):
    parent = BEFORE['configurations'][configuration]
    runtime = rule.bind(parent['runtime'], configuration)
    assert wire(runtime) == wire(parent['runtime'])
    assert wire(run_episode(label, runtime)) == wire(parent['k1_judge'][label])


@pytest.mark.parametrize('configuration', p.CONFIGURATIONS)
def test_configuration_rule_and_runtime_binding(configuration):
    source = {'existing_runtime': {'value': 1}}
    runtime = rule.bind(source, configuration)
    child = p.is_v296(configuration)
    assert p.alfworld_format_rule(configuration) == (rule.RULE if child else 'alfworld-admissible-9-10')
    assert p.ALFWORLD_ADMISSIBLE_MIN == Fraction(9, 10)
    assert rule.validate(runtime, configuration) is child
    assert rule.validate(runtime) is child
    assert runtime is not source and source == {'existing_runtime': {'value': 1}}
    assert runtime == ({**source, 'execskill_configuration': configuration, 'alfworld_format_rule': rule.RULE}
                       if child else source)
    assert rule.bind(runtime, configuration) == runtime
    before = deepcopy(runtime)
    assert rule.environment_runtime(runtime) == source
    assert runtime == before


@pytest.mark.parametrize('runtime', [
    {'execskill_configuration': 'alfworld-v10'},
    {'alfworld_format_rule': rule.RULE},
    {'execskill_configuration': 'alfworld-v10', 'alfworld_format_rule': None},
    {'execskill_configuration': 'alfworld-v10', 'alfworld_format_rule': '9/10'},
    {'execskill_configuration': 'alfworld-v10', 'alfworld_format_rule': 'unknown-rule'},
    {'execskill_configuration': 'alfworld-v10', 'alfworld_format_rule': 'alfworld-admissible-majority-v2-9-6'},
    {'execskill_configuration': 'alfworld-v9', 'alfworld_format_rule': rule.RULE},
    {'execskill_configuration': 'unknown', 'alfworld_format_rule': rule.RULE},
    {'execskill_configuration': None, 'alfworld_format_rule': rule.RULE},
    {'execskill_configuration': ['alfworld-v10'], 'alfworld_format_rule': rule.RULE},
    {'execskill_configuration': 'alfworld-v10', 'alfworld_format_rule': [rule.RULE]},
])
def test_unknown_partial_or_mismatched_runtime_is_refused_by_judge_and_binder(runtime):
    for check in (lambda: rule.validate(runtime), lambda: rule.bind(runtime, p.ALFWORLD_V10),
                  lambda: rule.environment_runtime(runtime),
                  lambda: run_episode('7_of_8', runtime)):
        with pytest.raises(ValueError, match='ALFWorld format runtime'):
            check()


def test_new_run_cannot_validate_a_missing_runtime_binding():
    with pytest.raises(ValueError, match='format runtime is required'):
        rule.validate({}, p.ALFWORLD_V10)


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS if not p.is_v296(name)])
def test_new_runtime_cannot_be_used_for_any_older_run(configuration):
    runtime = rule.bind({}, p.ALFWORLD_V10)
    with pytest.raises(ValueError, match='historical runtime'):
        rule.validate(runtime, configuration)
    with pytest.raises(ValueError, match='historical runtime'):
        rule.bind(runtime, configuration)


def test_unknown_cells_keep_none_even_with_invalid_action_reason():
    case = deepcopy(EPISODES['unknown'])
    case['prediction']['reason'] = 'invalid_action_format'
    found = run_episode('unknown', rule.bind({}, p.ALFWORLD_V10), case=case)
    assert found['format']['violation'] is found['format']['violation_at_9_10'] is found['format']['violation_below_half'] is None


def test_invalid_reason_without_any_shell_has_no_primary_format_verdict():
    case = deepcopy(EPISODES['invalid_no_steps'])
    case['prediction'].pop('shell')
    found = run_episode('invalid_no_steps', rule.bind({}, p.ALFWORLD_V10), case=case)
    assert found['format'] == {
        'steps': None, 'admissible_steps': None, 'violation': None,
        'violation_at_9_10': True, 'violation_below_half': True, 'rule': rule.RULE,
    }


@pytest.mark.parametrize('how', ['tag_exact', 'whole_level1', 'case_folded', 'other_canonicalisation'])
def test_every_non_unchanged_canonicaliser_value_counts_as_admissible(how):
    case = deepcopy(EPISODES['4_of_8'])
    case['prediction']['shell']['alfworld_steps'] = [{'how': how}] * 4 + [{'how': 'unchanged'}] * 4
    found = run_episode('4_of_8', rule.bind({}, p.ALFWORLD_V10), case=case)
    assert found['format']['admissible_steps'] == 4
    assert found['format']['violation'] is False
    assert found['format']['violation_at_9_10'] is True
    assert found['format']['violation_below_half'] is False


def test_runtime_binding_does_not_change_other_benchmark_judge_records():
    from tests.test_execskill_judge import available, receipt
    public = {'question': 'Which city?', 'context': ['Paris']}
    private = {'answers': ['Paris']}
    prediction = available('<answer>Paris</answer>')
    receipts = [receipt('<answer>Paris</answer>')]
    before = judge.judge('searchqa', public, private, prediction, receipts, runtime={})
    after = judge.judge('searchqa', public, private, prediction, receipts,
                        runtime=rule.bind({}, p.ALFWORLD_V10))
    assert wire(after) == wire(before)
