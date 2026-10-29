"""main-v4 public disclosure boundaries, structure-preserving truncation and byte ceilings."""
from copy import deepcopy
import json

import pytest

from skillopt.execskill import audit, engineer_v211, profiles as p, v211_audit as child


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa'])
def test_nested_context_preserves_containers_order_and_hashes(bench):
    view = {'question': '头' * 9000 + '尾', 'context': ['A' * 25000, {'public': ['B' * 5000, 'last']}],
            'answer': 'PRIVATE', 'reference': 'PRIVATE', 'private': {'context': 'PRIVATE'}}
    original = deepcopy(view)
    shown, meta = child.disclosure(bench, view)
    assert list(shown) == ['question', 'context'] and view == original
    assert isinstance(shown['context'], list) and list(shown['context'][1]) == ['public']
    assert shown['question'].startswith('头') and shown['question'].endswith('尾')
    assert len(shown['question']) == 8000
    assert meta['question'] == {'original_length': 9001, 'disclosed_length': 8000,
                                 'original_sha256': child.sha(view['question'])}
    assert 'PRIVATE' not in str(shown)
    assert audit.public_view(bench, view, configuration=p.MAIN_V4) == shown


@pytest.mark.parametrize('choices', [
    {str(n): 'choice ' + '界' * 2500 for n in range(30)},
    [{'label': 'Label-' + str(n), 'text': '界' * 2500} for n in range(30)]])
def test_all_choice_labels_order_preserved_even_beyond_legacy_20_entry_limit(choices):
    shown, meta = child.disclosure('livemath', {'question': 'Q', 'choices': choices, 'stronger_option': 'PRIVATE'})
    assert len(shown['choices']) == 30 and 'PRIVATE' not in str(shown)
    if isinstance(choices, dict):
        assert list(shown['choices']) == list(choices)
        assert all(len(v) <= 2000 for v in shown['choices'].values())
    else:
        assert [v['label'] for v in shown['choices']] == [v['label'] for v in choices]
    assert meta


def test_sheet_discloses_only_recorded_helper_view_and_first_100_answer_cells():
    view = {'instruction': 'I' * 9000, 'workbook_preview': [{'sheet': 'S', 'rows': [['界' * 5000]]}],
            'input_path': 'input.xlsx', 'required_output_path': 'output.xlsx', 'required_answer_position': 'A1',
            'previous_program': 'PRIVATE PROGRAM', 'reference_workbook': 'PRIVATE REFERENCE'}
    report = {'status': 'exception', 'exc_type': 'KeyError', 'message': 'E' * 3000,
              'answer_cells': {str(n): n for n in range(150)}, 'grade': 'PRIVATE GRADE'}
    shown, metadata = child.disclosure('spreadsheetbench', view, report=report)
    assert shown['workbook_preview'] == view['workbook_preview']
    assert len(shown['run_report']['answer_cells']) == 100
    assert metadata['run_report/answer_cells']['omitted_count'] == 50
    assert len(shown['run_report']['message']) == 2000 and 'PRIVATE' not in str(shown)


@pytest.mark.parametrize('bench', child.LEARNED)
def test_prompt_pins_include_all_actual_limits_and_no_episode_language(bench):
    assert p.audit_spec(p.MAIN_V4, bench)['field_limits'] == child.LIMITS
    assert audit.system_prompt('B', configuration=p.MAIN_V4, bench=bench) == engineer_v211.audit_system('B')
    assert 'episode_history' not in audit.system_prompt('B', configuration=p.MAIN_V4, bench=bench)
    assert 'unverifiable' in engineer_v211.audit_system('B')


def test_utf8_group_and_complete_request_fit_halves_only_public_text():
    row = {'s': 'S1', 'item': 'item', 'view': {'question': 'Q', 'context': ['界' * 24000]},
           'notes': [{'text': 'Immutable note', 'n': 'N1', 'procedure': 'p'}], 'truncation': {}, 'hook': 'bindings'}
    user, meta = child.fit_prompt('system', lambda rows: json.dumps(rows, ensure_ascii=False), [row], bench='searchqa')
    assert meta['within_limit'] and meta['public_text_scale'] < 1
    assert max(meta['group_bytes'].values()) <= 32000
    assert 'Immutable note' in user and 'bindings' in user
    assert row['view']['context'] == ['界' * 24000]


def test_immutable_note_too_large_is_incomplete_never_dropped():
    row = {'s': 'S1', 'item': 'item', 'view': {'question': 'Q', 'context': []},
           'notes': [{'text': 'N' * 65000, 'n': 'N1', 'procedure': 'p'}], 'truncation': {}}
    user, meta = child.fit_prompt('system', lambda rows: json.dumps(rows), [row], bench='searchqa')
    assert not meta['within_limit'] and 'N' * 65000 in user


def test_real_livemath_string_keeps_every_label_and_clips_each_option():
    from skillopt.continual_eval.datasets import livemath_options
    choices = '\n\n'.join(label + '. ' + label * 5000 for label in 'ABCDE')
    shown, metadata = child.disclosure('livemath', {'question': 'Q', 'choices': choices})
    options = livemath_options(shown['choices'])
    assert len(options) == 5 and all(len(value) == 2000 for value in options)
    assert [value[0] for value in options] == list('ABCDE')
    assert list(metadata) == ['choices/' + label for label in 'ABCDE']


def test_fitting_preserves_original_field_hash_after_further_clipping():
    original = '界' * 50000
    view, metadata = child.disclosure('searchqa', {'question': 'Q', 'context': original})
    row = {'s': 'S1', 'item': 'item', 'view': view, 'notes': [], 'truncation': metadata}
    _, fitted = child.fit_prompt('', lambda rows: json.dumps(rows, ensure_ascii=False), [row], bench='searchqa')
    assert fitted['truncation']['S1']['context']['original_sha256'] == child.sha(original)
    assert fitted['truncation']['S1']['context']['original_length'] == 50000
