"""Generated v2.9.1 note-cap prompt text; offline, no model requests."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from skillopt.execskill import engineer_v291, manifest, notes, profiles as p


CONFIGURATIONS = ('zebra-pc-v8', 'alfworld-v5')
PREFIX = ('Note caps: facts/warnings items ≤ 200 characters each, candidates ≤ 120 characters each, '
          'table ≤ 20 rows × 12 columns with cells ≤ 40 characters, bindings name/quote/value ≤ 200 '
          'characters each; a field over its cap is dropped whole and counts as a fault; rendered notes '
          'must also fit `max_note_chars` and the ')


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
@pytest.mark.parametrize('train', (False, True))
def test_exact_note_cap_sentence_is_in_both_system_modes_and_pinned(configuration, train):
    ending = ('ALFWorld bench cap of 1,500 characters per step.' if p.is_alfworld(configuration)
              else 'ZebraLogic bench cap of 4,000 characters per request.')
    expected = PREFIX + ending
    text = engineer_v291.system(configuration, train=train)
    assert engineer_v291.note_caps_rule(configuration) == expected
    assert text.count(expected) == 1
    pins = engineer_v291.prompt_pins()
    assert pins[configuration + '/note_caps'] == {
        'text': expected, 'sha256': engineer_v291.audit.text_sha256(expected)}
    mode = 'train' if train else 'single'
    assert pins[configuration + '/' + mode]['text'] == text
    assert manifest.prompt_sha(configuration)['v291'] == pins


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_note_cap_sentence_reads_all_runtime_limits_and_binding_keys(monkeypatch, configuration):
    fields = deepcopy(notes.FIELD_TYPES)
    fields['facts']['max_chars'] = fields['warnings']['max_chars'] = 211
    fields['candidates']['max_chars'] = 123
    fields['table'].update(max_chars=47, max_rows=17, max_columns=9)
    fields['bindings'].update(max_chars=199, keys=['label', 'text', 'number'])
    monkeypatch.setattr(notes, 'FIELD_TYPES', fields)
    bench = p.active_benches(configuration)[0]
    monkeypatch.setitem(p.MAX_NOTE_CHARS, bench, 4321)
    text = engineer_v291.note_caps_rule(configuration)
    assert 'facts/warnings items ≤ 211 characters each' in text
    assert 'candidates ≤ 123 characters each' in text
    assert 'table ≤ 17 rows × 9 columns with cells ≤ 47 characters' in text
    assert 'bindings label/text/number ≤ 199 characters each' in text
    assert 'bench cap of 4,321 characters' in text
    assert text in engineer_v291.system(configuration, train=True)


@pytest.mark.parametrize('configuration', CONFIGURATIONS)
def test_different_facts_warning_limits_are_shown_separately(monkeypatch, configuration):
    fields = deepcopy(notes.FIELD_TYPES)
    fields['facts']['max_chars'], fields['warnings']['max_chars'] = 180, 210
    monkeypatch.setattr(notes, 'FIELD_TYPES', fields)
    text = engineer_v291.note_caps_rule(configuration)
    assert 'facts items ≤ 180 characters each, warnings items ≤ 210 characters each' in text
    assert 'facts/warnings' not in text


@pytest.mark.parametrize('configuration', ('zebra-pc-v7', 'alfworld-v4'))
def test_parent_prompt_maps_remain_byte_identical(configuration):
    before = json.loads((Path(__file__).parent / 'fixtures' / 'execskill' / 'v291_parents_before.json').read_text())
    assert manifest.prompt_sha(configuration) == before[configuration]['prompts']
    parent_system = before[configuration]['prompts']['v29']['engineer'][configuration + '/train']['text']
    assert 'Note caps:' not in parent_system
