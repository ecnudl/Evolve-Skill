"""J2 child-only manifest disambiguation; all inputs are authored here or stored fixtures."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer_reader as reader


CHILDREN = ('alfworld-v7', 'zebra-pc-v10')
PARENTS = ('alfworld-v5', 'alfworld-v6', 'zebra-pc-v8', 'zebra-pc-v9')
GOOD = 'def before_call(view, state):\n    return {}\n'
ALF = 'def alf_before_step(view, state):\n    return {"fields": {"facts": []}}\n'
REPLIES = {row['label']: row['reply'] for row in json.loads(
    (Path(__file__).parent / 'fixtures/execskill/alf6_s3b_replies.json').read_text())}


def context(configuration):
    return SimpleNamespace(configuration=configuration, mode='train',
                           parent=SimpleNamespace(order=(), get=lambda identity: None))


def fence(body, language='json'):
    return '```' + language + '\n' + body + ('\n' if not body.endswith('\n') else '') + '```\n'


def manifest(entries=None, language='json'):
    return fence(json.dumps({'changes': [{'kind': 'new', 'id': 'wanted'}] if entries is None else entries}), language)


def ignored(row):
    return [repair for repair in row['repairs'] if repair['rule'] == 'extra_json_blocks_ignored']


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('position', (0, 1, 2))
def test_one_changes_object_is_selected_in_every_json_candidate_position(configuration, position):
    blocks = [fence('[{"id": "advisory-test"}]'), fence('{"comment": "not a manifest"}')]
    blocks.insert(position, manifest())
    rows = reader.read(''.join(blocks) + fence(GOOD, 'python'), context(configuration))
    assert len(rows) == 1 and rows[0]['error'] is None and rows[0]['source'] == GOOD
    assert rows[0]['original']['id'] == 'wanted'
    assert rows[0]['entry']['replay_tests'] == []
    assert ignored(rows[0]) == [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 2}]


@pytest.mark.parametrize('language', ('json', 'jsonc', 'json5', ''))
def test_candidate_rule_recognizes_all_existing_object_languages(language):
    text = fence('{"advice": "ignore"}', language) + manifest(language=language) + fence(GOOD, 'python')
    row = reader.read(text, context(CHILDREN[0]))[0]
    assert row['source'] == GOOD and row['error'] is None
    assert ignored(row)[0]['count'] == 1


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('extra', ('not valid JSON', '{"unterminated":', 'def before_call(view, state):\n    return {}'))
def test_unparseable_extra_json_blocks_are_ignored(configuration, extra):
    text = manifest() + fence(extra) + fence(GOOD, 'python')
    row = reader.read(text, context(configuration))[0]
    assert row['error'] is None and row['source'] == GOOD
    assert ignored(row)[0]['count'] == 1


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('extras', (['{}', '[]'], ['{', 'false'], ['{"advice": 1}', '{"another": 2}']))
def test_no_changes_objects_retains_original_candidate_count_error(configuration, extras):
    with pytest.raises(reader.Unusable, match='^expected one manifest object, found 2$'):
        reader.read(''.join(fence(value) for value in extras), context(configuration))


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('second', ('{"changes": []}', '{"changes": null}', '{"changes": "wrong type"}'))
def test_two_changes_objects_remain_ambiguous_even_when_one_changes_value_is_invalid(configuration, second):
    text = manifest() + fence(second) + fence('[1,2]') + fence(GOOD, 'python')
    with pytest.raises(reader.Unusable, match='^expected one manifest object, found 3$'):
        reader.read(text, context(configuration))


@pytest.mark.parametrize('configuration', CHILDREN)
def test_ignored_json_program_is_never_a_source_block(configuration):
    row = reader.read(manifest() + fence(GOOD), context(configuration))[0]
    assert row['error'] == 'no procedure source block' and row['source'] is None
    assert ignored(row) == [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 1}]


def test_all_json_candidates_are_removed_before_joint_source_ownership(monkeypatch):
    text = (fence('[]') + manifest([{'kind': 'new', 'hooks': ['before_call']},
                                  {'kind': 'new', 'hooks': ['alf_before_step']}]) +
            fence(ALF, 'python') + fence('malformed') + fence(GOOD, 'python') + fence('{"extra": 1}'))
    original, seen = reader._source_owners, []
    def owners(entries, blocks, *args, **kwargs):
        seen.append(blocks)
        return original(entries, blocks, *args, **kwargs)
    monkeypatch.setattr(reader, '_source_owners', owners)
    rows = reader.read(text, context(CHILDREN[0]))
    assert [row['source'] for row in rows] == [GOOD, ALF]
    assert [[(number, language) for number, language, body in blocks] for blocks in seen] == [[(2, 'python'), (4, 'python')]]
    assert all(ignored(row) == [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 3}] for row in rows)


def test_ignored_json_is_also_removed_before_oversized_retry_source_ownership(monkeypatch):
    entries = [{'kind': 'new', 'id': 'wanted'}] + [
        {'kind': 'new', 'id': 'inline-%d' % index, 'source': GOOD} for index in range(3)]
    text = manifest(entries) + fence(ALF) + fence(GOOD, 'python')
    original, seen = reader._large_retry_source_owner, []
    def owners(entries, blocks, *args, **kwargs):
        seen.append(blocks)
        return original(entries, blocks, *args, **kwargs)
    monkeypatch.setattr(reader, '_large_retry_source_owner', owners)
    rows = reader.read(text, context(CHILDREN[0]),
                       selection={'change_id': 'wanted', 'change_count': 4, 'change_index': 1})
    assert len(rows) == 1 and rows[0]['source'] == GOOD and rows[0]['error'] is None
    assert seen == [[(2, 'python', GOOD)]]
    assert ignored(rows[0]) == [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 1}]


def test_ignored_json_is_not_merged_into_changes_or_replay_tests():
    entries = [{'kind': 'new', 'id': 'good', 'source': GOOD}, {'kind': 'unknown', 'id': 'bad'}]
    extras = [fence('[{"kind": "new", "source": "untrusted"}]'),
              fence('{"replay_tests": [{"id": "must-not-merge"}]}')]
    rows = reader.read(manifest(entries) + ''.join(extras), context(CHILDREN[0]))
    assert len(rows) == 2 and rows[0]['entry']['replay_tests'] == []
    assert rows[0]['error'] is None and rows[1]['error'] == "unknown change kind 'unknown'"
    assert all(ignored(row) == [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 2}] for row in rows)
    rows[0]['repairs'][-1]['mutated'] = True
    assert not any('mutated' in repair for repair in rows[1]['repairs'])


def test_only_selected_manifest_tolerance_repairs_are_retained():
    text = fence("{'advice': 1,}") + fence("{'changes': [{'kind': 'new'}],}") + fence(GOOD, 'python')
    row = reader.read(text, context(CHILDREN[0]))[0]
    assert row['error'] is None and row['source'] == GOOD
    assert [repair for repair in row['repairs'] if repair['rule'] == 'tolerant_json'] == [
        {'rule': 'tolerant_json', 'path': '$'}]
    assert ignored(row)[0]['count'] == 1


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('text', (
    json.dumps({'changes': [{'kind': 'new', 'source': GOOD}]}),
    manifest([{'kind': 'new', 'source': GOOD}]),
    manifest() + fence(GOOD, 'python'),
    fence('[]'),
    fence('malformed'),
    fence(GOOD, 'python'),
))
def test_zero_or_one_json_candidate_keeps_parent_path_exactly(configuration, text):
    parent = {'alfworld-v7': 'alfworld-v6', 'zebra-pc-v10': 'zebra-pc-v9'}[configuration]
    def outcome(config):
        try:
            return ('parsed', reader.read(text, context(config)))
        except reader.Unusable as error:
            return ('unusable', str(error))
    assert outcome(configuration) == outcome(parent)


@pytest.mark.parametrize('configuration', PARENTS)
def test_older_configurations_keep_multi_json_rejection(configuration):
    with pytest.raises(reader.Unusable, match='^expected one manifest object, found 2$'):
        reader.read(manifest() + fence('[]') + fence(GOOD, 'python'), context(configuration))


def test_real_alf_proposal_keeps_both_programs_and_ignores_advisory_array():
    rows = reader.read(REPLIES['propose'], context('alfworld-v7'))
    assert [row['original']['id'] for row in rows] == ['alf_progress_tracker', 'alf_task_planner']
    expected = [match.group(3) for match in reader.FENCE.finditer(REPLIES['propose'])
                if match.group(2).strip().lower() == 'python']
    assert [row['source'] for row in rows] == expected
    assert all(row['error'] is None and row['source'] and
               any(hook.startswith('alf_') for hook in reader.defined_hooks(row['source'])) for row in rows)
    assert all(ignored(row) == [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': 1}] for row in rows)


@pytest.mark.parametrize('configuration', ('alfworld-v5', 'alfworld-v6'))
def test_real_alf_parent_proposal_keeps_recorded_manifest_count_error(configuration):
    with pytest.raises(reader.Unusable, match='^expected one manifest object, found 2$'):
        reader.read(REPLIES['propose'], context(configuration))
