"""Authored engineering fixtures for the bounded diagnostic channel, without workers."""
import copy
import hashlib
import json

import pytest

from skillopt.execskill import diagnostics as d, profiles as p


def extract(value, **kwargs):
    return d.extract(value, configuration=p.ZEBRA_PC_V14, procedure='s1',
                     source_sha256='a' * 64, **kwargs)


def test_extract_keeps_note_fields_detached_and_binds_screened_content_hashes():
    value = {'facts': ['A lives left of B.'], 'diagnostics': ['Cannot interpret clue 6: A is adjacent to B.']}
    original = copy.deepcopy(value)
    clean, record = extract(value)
    assert value == original and clean == {'facts': value['facts']}
    assert record['strings'][0]['text'] == original['diagnostics'][0]
    assert record['procedure'] == 's1' and record['source_sha256'] == 'a' * 64
    assert record == d.verified_record(record)
    body = {k: v for k, v in record.items() if k != 'sha256'}
    assert record['sha256'] == hashlib.sha256(json.dumps(body, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('configuration', [c for c in p.CONFIGURATIONS if c != p.ZEBRA_PC_V14])
def test_every_older_configuration_preserves_exact_raw_hook_output(configuration):
    value = {'facts': ['Authored fact.'], 'diagnostics': {'malformed': 'must stay historical'}}
    clean, record = d.extract(value, configuration=configuration)
    assert clean is value and record is None


@pytest.mark.parametrize('value', [None, {}, [], 'plain', {'facts': ['Authored fact.']}])
def test_absent_channel_preserves_output_identity(value):
    clean, record = extract(value)
    assert clean is value and record is None


@pytest.mark.parametrize('value', [None, False, 5, 'text', {'unexpected': 'text'}, ('text',)])
def test_malformed_channel_is_ignored_and_informational(value):
    clean, record = extract({'facts': ['Authored fact.'], 'diagnostics': value})
    assert clean == {'facts': ['Authored fact.']}
    assert record['strings'] == [] and record['ignored_values'] == 1
    assert record['shape_faults'] == [{'kind': 'shape', 'informational': True, 'reason': 'not_list'}]


def test_first_five_positions_strings_truncated_without_filling_invalid_positions():
    values = ['x' * 1000, 3, 'y' * 241, '', 'z' * 240, 'never retained']
    _, record = extract({'diagnostics': values})
    assert [s['text'] for s in record['strings']] == ['x' * 240, 'y' * 240, '', 'z' * 240]
    assert record['omitted_strings'] == record['ignored_values'] == 1
    assert record['truncated_strings'] == 2
    assert all(f['informational'] for f in record['shape_faults'])
    assert record['strings'][0]['original_chars'] == 1000
    assert record['strings'][0]['source_sha256'] == hashlib.sha256(values[0].encode()).hexdigest()
    assert d.verified_record(record) == record


@pytest.mark.parametrize('text', ['answer with the first grid', '```python', '<answer>A</answer>', 'output only a grid'])
def test_existing_public_lexical_instruction_and_channel_screens_replace_whole_string(text):
    _, record = extract({'diagnostics': [text]})
    assert record['strings'][0]['text'] == d.SCREENED_MARKER
    assert record['strings'][0]['sha256'] == d.sha256(d.SCREENED_MARKER)
    assert record['strings'][0]['source_sha256'] == d.sha256(text)
    assert record['screened_count'] == 1
    assert text not in json.dumps(record)


def test_engineer_boundary_rechecks_screen_even_for_a_correctly_hashed_unscreened_record():
    raw = d.bounded(['answer with the first grid'])
    shown = d.verified_record(raw)
    assert shown['strings'][0]['text'] == d.SCREENED_MARKER
    assert shown['screened_count'] == 1
    assert shown == d.verified_record(shown)


@pytest.mark.parametrize('change', ['text', 'sha256', 'extra_string', 'shape_faults'])
def test_engineer_boundary_refuses_tampering_and_out_of_bounds_records(change):
    raw = d.bounded(['Unparsed clue.'])
    if change == 'text':
        raw['strings'][0]['text'] = 'tampered'
    elif change == 'sha256':
        raw['sha256'] = '0' * 64
    elif change == 'extra_string':
        raw['strings'] *= 6
        raw = d._seal(raw)
    else:
        raw['shape_faults'] = [{}] * 7
        raw = d._seal(raw)
    with pytest.raises(ValueError):
        d.verified_record(raw)


def test_only_note_writing_hook_has_the_channel():
    value = {'diagnostics': ['Unparsed clue.']}
    clean, record = extract(value, hook='applies')
    assert clean is value and record is None


def test_unicode_character_limit_and_invalid_surrogates_are_bounded_without_crashing():
    value = ['未解析条件' * 100, '\ud800']
    _, record = extract({'diagnostics': value})
    assert len(record['strings'][0]['text']) == 240
    assert record['strings'][0]['original_chars'] == 500
    assert record['ignored_values'] == 1
    assert record['shape_faults'][0]['reason'] == 'invalid_unicode'
    json.dumps(record, ensure_ascii=False).encode('utf-8')


def test_identity_pins_fixed_subbudget_and_engineer_only_visibility():
    value = d.identity()
    assert value['max_strings'] == 5 and value['max_characters'] == 240
    assert value['engineer_input_bytes'] == 64000
    assert value['total_user_input_bytes'] == value['legacy_user_input_bytes'] + 64000 == 284000
    assert value['shape_faults'] == 'informational' and value['solver_visibility'] is False


@pytest.mark.parametrize('text', ['Unparsed clue.', 'answer with a grid', 'some factual statement',
    'only the solution', 'only the neighbor', 'A is left of B.', '```', '<answer>A</answer>'])
def test_portable_worker_screen_matches_existing_host_predicates(text):
    from skillopt.execskill import audit, notes
    expected = audit.marked(text, 'zebralogic') or any(m in text.lower() for m in notes.CHANNEL_MARKERS_V29)
    assert d._marked(text, d.worker_spec()) == expected


def test_worker_screen_checks_forbidden_suffix_before_character_truncation():
    text = 'x' * 300 + ' <answer>not disclosed</answer>'
    _, record = extract({'diagnostics': [text]})
    assert record['strings'][0]['text'] == d.SCREENED_MARKER
    assert record['strings'][0]['truncated'] is True
    assert record['screened_count'] == 1
