"""typed-v2 reply reader (DESIGN 3.3; spec/reply.md section 4; addendum O8): the fixture table F1..F12 (the two
typed-v1 losses of F6 among them), parity with the REAL frozen route-B reader on well-formed replies, never raises,
never executes, tolerance does not weaken the static screen, the problem sentence and the format-retry request per
problem code, the retry budget and ``read_with_retry``, the pins. Literal strings only: no network, no Docker, no
/data, no model call."""
import ast
import hashlib
import importlib
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, engineer_reader, package, policy, profiles
from skillopt.execskill.typed import MACHINERY, replies

SCRATCH = Path('/tmp/typed2-neutral')   # a plain name: the sealed-path guard refuses paths containing 'test'
DESIGN = Path(__file__).resolve().parents[1] / 'docs' / 'handoff' / 'typed-v2' / 'DESIGN.md'


@pytest.fixture
def scratch():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='replies-', dir=SCRATCH))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- texts -----------------------------------------------------------------------------------------------------
HOOKED = ('def applies(view):\n    return "question" in view\n\n\n'
          'def before_call(view, state):\n    return {"facts": ["the question names one entity"]}\n')
OTHER = HOOKED.replace('one entity', 'two entities')                 # a second, different program
BINDINGS = ('def applies(view):\n    return True\n\n\n'
            'def bindings(view):\n    return {"bindings": []}\n')
BROKEN = 'def applies(view)\n    return True\n'                         # a syntax error: no program
BAD = 'import os\n\n' + HOOKED                                          # a program the static screen refuses
NEW = {'kind': 'new', 'description': 'Counts entity mentions', 'hooks': ['applies', 'before_call'],
       'max_note_chars': 600, 'replay_tests': []}
UNDER_REPAIR = {'entry': dict(NEW), 'source': BAD}                      # the change a fix call repairs
# A copy of typed-v1's T/smoke.py DEFAULT_PROGRAM (the scripted canonical proposal; copied so that this file does not
# import the smoke module while other steps edit it).
SMOKE_DEFAULT_PROGRAM = ('```json\n{"changes": [{"kind": "new", "id": "scripted-helper", '
                         '"description": "Lists a caution for the solver before it answers.", '
                         '"hooks": ["applies", "before_call"]}]}\n```\n\n'
                         '```python\ndef applies(view):\n    return True\n\n\n'
                         'def before_call(view, state):\n    return {"warnings": ["Read the whole task before '
                         'answering."]}\n```')
PROSE = 'I could not find a safe change, sorry.'
TYPED_ONLY_RULES = {'manifest_outside_fence', 'manifest_absent_inherited', 'alias_change', 'single_change_wrapped',
                    'bare_change', 'bare_list', 'fence_not_program_ignored', 'fence_unassigned_ignored',
                    'fix_kind_ignored', 'inline_not_program_ignored', 'echo_source_dropped'}
NORMALIZE_RULES = {'relocated', 'unknown_key_ignored', 'inherited_change', 'inherited_parent', 'derived',
                   'schema_default', 'integer_boolean', 'lossless_type_conversion', 'advisory_list_wrapped'}


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fence(tag, body):
    return '```%s\n%s```' % (tag, body if body.endswith('\n') else body + '\n')


def manifest(value, tag='json'):
    return fence(tag, json.dumps(value))


def joined(*parts):
    return '\n\n'.join(parts)


def two_fence(changes, sources):
    """The canonical shape of tests/test_typed_writers.py: one json fence, then one python fence per change."""
    blocks = ['```json\n' + json.dumps({'changes': changes}, sort_keys=True) + '\n```']
    return '\n\n'.join(blocks + ['```python\n' + source + '```' for source in sources])


def program_of(chars, word):
    """A legal hooked program of exactly ``chars`` characters."""
    head = ('def applies(view):\n    return True\n\n\n'
            'def before_call(view, state):\n    return {"facts": ["%s"]}\n' % word)
    return head + '# ' + 'x' * (chars - len(head) - 3) + '\n'


def typed(text, mode='propose', *, parent_ids=(), change=UNDER_REPAIR):
    if mode == 'fix':
        return replies.read_fix(text, change=change)
    return replies.read_proposals(text, parent_ids=parent_ids)


def frozen(text, mode='propose', *, parent=None, change=UNDER_REPAIR):
    """The frozen route-B reader exactly as typed-v1's writers called it (mode single, configuration main-v10)."""
    ctx = SimpleNamespace(parent=parent or package.Package((), 'typed/G/s1', 'engineering_fixture'), mode='single',
                          configuration=MACHINERY)
    fix = engineer.Change(1, 'new', dict(change['entry']), change['source'], 'a' * 64) if mode == 'fix' else None
    return engineer_reader.read(text, ctx, fix_change=fix)


def check_shape(result):
    """Result, record, problem and read shapes; JSON-serialisable; every repair rule known."""
    assert set(result) == {'records', 'problem', 'repairs', 'reply_sha256', 'reader'}
    assert result['reader'] == replies.READER and len(result['reply_sha256']) == 64
    json.dumps(result)
    problems = [result['problem']] if result['problem'] else []
    if result['problem']:
        assert result['records'] == [] and result['problem']['change'] is None
    for n, record in enumerate(result['records'], 1):
        assert set(record) == {'n', 'kind', 'entry', 'source', 'problem', 'repairs', 'read'} and record['n'] == n
        assert set(record['read']) == {'source_from', 'is_program', 'hooks_defined', 'ignored', 'reply_sha256',
                                       'reader'}
        assert record['read']['reply_sha256'] == result['reply_sha256']
        assert record['read']['source_from'] in ('fence', 'inline', 'inline_and_fence_equal', None)
        for ignored in record['read']['ignored']:
            assert set(ignored) == {'from', 'chars', 'sha256', 'why'} and ignored['why'] in replies.IGNORED_WHY
        if record['problem']:
            assert record['problem']['change'] == n and record['source'] is None
            problems.append(record['problem'])
        if record['source'] is not None:
            assert record['kind'] == 'new' and isinstance(record['entry'], dict) and record['source'].strip()
            assert record['read']['is_program'] == replies.is_program(record['source'])
        else:
            assert record['read']['source_from'] is None and record['read']['is_program'] is False
        for row in record['repairs']:
            assert set(row) >= {'rule', 'path'} and row['rule'] in set(replies.REPAIR_RULES) | NORMALIZE_RULES
    for problem in problems:
        assert set(problem) == {'code', 'detail', 'change'} and problem['code'] in replies.PROBLEM_CODES
        assert problem['detail'].endswith('.') and '\n' not in problem['detail']
    return result


def rules(record):
    return [row['rule'] for row in record['repairs']]


def only(result):
    check_shape(result)
    assert result['problem'] is None and len(result['records']) == 1
    return result['records'][0]


# ---- F1..F12 (spec/reply.md section 4) -------------------------------------------------------------------------
def f1(mode):
    result = typed(joined(manifest({'change': {'id': 'p1', 'description': 'Counts entity mentions'}}),
                          fence('python', HOOKED)), mode)
    record = only(result)
    assert record['problem'] is None and record['source'] == HOOKED and record['read']['source_from'] == 'fence'
    assert {'alias_change', 'single_change_wrapped'} <= set(rules(record))
    assert record['entry']['description'] == 'Counts entity mentions' and record['entry']['kind'] == 'new'
    assert replies.readable(result)


def f2(mode):
    record = only(typed(joined(manifest({'changes': [{'id': 'p1', 'source': 'PLACEHOLDER'}]}),
                               fence('python', HOOKED)), mode))
    assert record['problem'] is None and record['source'] == HOOKED and record['read']['source_from'] == 'fence'
    assert record['read']['ignored'] == [{'from': 'inline', 'chars': 11, 'why': 'not_program',
                                          'sha256': sha('PLACEHOLDER')}]
    assert 'inline_not_program_ignored' in rules(record) and record['read']['is_program'] is True
    assert record['read']['hooks_defined'] == ['applies', 'before_call']


def f3(mode):
    result = typed(joined(manifest({'changes': [{'id': 'p1', 'source': HOOKED}]}), fence('python', OTHER)), mode)
    record = only(result)
    assert record['problem']['code'] == 'ambiguous_source' and record['source'] is None
    assert '%d characters' % len(HOOKED) in record['problem']['detail']
    assert '%d characters' % len(OTHER) in record['problem']['detail']
    assert sorted(item['why'] for item in record['read']['ignored']) == ['ambiguous', 'ambiguous']
    assert not replies.readable(result)


def f3b(mode):
    record = only(typed(joined(manifest({'changes': [{'id': 'p1', 'source': BAD}]}), fence('python', HOOKED)), mode))
    assert record['problem'] is None and record['source'] == HOOKED and 'echo_source_dropped' in rules(record)
    assert record['read']['ignored'] == [{'from': 'inline', 'chars': len(BAD), 'sha256': sha(BAD), 'why': 'echo'}]


def f4(mode):
    result = check_shape(typed(PROSE, mode))
    assert result['records'] == [] and result['problem'] == {
        'code': 'no_manifest', 'change': None,
        'detail': 'No JSON object was found (fenced code blocks: 0; other text: 38 characters).'}


def f5(mode):
    for text in (SMOKE_DEFAULT_PROGRAM, two_fence([NEW], [HOOKED])):
        record = only(typed(text, mode))
        expected = frozen(text, mode)[0]
        assert not TYPED_ONLY_RULES & set(rules(record)) and record['problem'] is None and expected['error'] is None
        drop = lambda entry: {key: value for key, value in entry.items() if key != 'replay_tests'}   # noqa: E731
        assert drop(record['entry']) == drop(expected['entry']) and record['source'] == expected['source']


def f6(mode):
    single = only(typed(joined(manifest({'changes': dict(NEW)}), fence('python', HOOKED)), mode))
    assert single['source'] == HOOKED and 'single_change_wrapped' in rules(single)
    bare = only(typed(joined(manifest(dict(NEW)), fence('python', HOOKED)), mode))
    assert bare['source'] == HOOKED and 'bare_change' in rules(bare)
    second = dict(NEW, hooks=['applies', 'bindings'], description='Binds numbers')
    result = check_shape(typed(joined(manifest([dict(NEW), second]), fence('python', HOOKED),
                                      fence('python', BINDINGS)), mode))
    assert [record['source'] for record in result['records']] == [HOOKED, BINDINGS]   # A1: by position
    assert all('bare_list' in rules(record) for record in result['records'])


def f7(mode):
    result = check_shape(typed(fence('python', HOOKED), mode))
    if mode == 'fix':
        record = only(result)
        assert record['source'] == HOOKED and 'manifest_absent_inherited' in rules(record)
        assert {key: record['entry'][key] for key in NEW} == NEW       # the entry under repair is reused
    else:
        assert result['problem']['code'] == 'no_manifest' and result['records'] == []
        assert result['problem']['detail'] == ('No JSON object was found (fenced code blocks: 1; other text: '
                                               '0 characters).')


def f8(mode):
    record = only(typed(joined(manifest({'changes': [dict(NEW)]}), fence('python', BROKEN)), mode))
    assert record['problem'] is None and record['source'] == BROKEN
    assert record['read']['is_program'] is False and record['read']['source_from'] == 'fence'
    assert record['read']['hooks_defined'] == []


def f9(mode):
    result = check_shape(typed(two_fence([dict(NEW)] * 4, [HOOKED, OTHER, BINDINGS, HOOKED]), mode))
    assert result['records'] == [] and result['problem']['code'] == 'too_many_changes'
    assert result['problem']['detail'] == ('The reply has 4 changes; at most 3 are allowed, so none of them was '
                                           'read.')


def f10(mode):
    result = typed(manifest({'changes': [{'id': 'p1', 'source': ''}]}), mode)
    record = only(result)
    assert record['problem']['code'] == 'no_source' and record['source'] is None
    assert BAD not in json.dumps(result)                                 # the failed source is never returned
    assert not replies.readable(result)


def f11(mode):
    result = check_shape(typed(two_fence([dict(NEW, description='d%d' % i) for i in range(3)], [HOOKED, OTHER]), mode))
    assert [record['problem']['code'] for record in result['records']] == ['blocks_not_assignable'] * 3
    assert all('3 new changes and 2 fenced code blocks' in record['problem']['detail'] for record in result['records'])
    assert not replies.readable(result)


def f12(mode):
    result = check_shape(typed(manifest({'changes': []}), mode))
    assert result['records'] == [] and result['problem'] is None and replies.readable(result)


FIXTURES = {'F1': (f1, ('fix',)), 'F2': (f2, ('fix',)), 'F3': (f3, ('fix',)), 'F3b': (f3b, ('fix',)),
            'F4': (f4, ('fix', 'propose')), 'F5': (f5, ('propose',)), 'F6': (f6, ('propose',)),
            'F7': (f7, ('fix', 'propose')), 'F8': (f8, ('fix',)), 'F9': (f9, ('propose',)), 'F10': (f10, ('fix',)),
            'F11': (f11, ('propose',)), 'F12': (f12, ('propose',))}


@pytest.mark.parametrize('case', [(name, mode) for name, (_, modes) in FIXTURES.items() for mode in modes],
                         ids=lambda case: '%s-%s' % case)
def test_fixture_table(case):
    name, mode = case
    FIXTURES[name][0](mode)


def test_the_two_typed_v1_losses_are_read():
    """F6: the frozen reader refused a fix reply with top-level ``change`` and screened a placeholder inline source
    instead of the fenced program; the typed reader reads both replies as the program."""
    alias = joined(manifest({'change': {'id': 'p1', 'description': 'Counts entity mentions'}}), fence('python', HOOKED))
    with pytest.raises(engineer_reader.Unusable):
        frozen(alias, 'fix')
    placeholder = joined(manifest({'changes': [{'id': 'p1', 'source': 'PLACEHOLDER'}]}), fence('python', HOOKED))
    assert frozen(placeholder, 'fix')[0]['source'] == 'PLACEHOLDER'
    for text in (alias, placeholder):
        assert only(typed(text, 'fix'))['source'] == HOOKED


# ---- parity with the frozen reader on well-formed replies ------------------------------------------------------
NEW2 = dict(NEW, description='Binds numbers', hooks=['applies', 'bindings'])
PARITY = {
    'smoke_default_program': (SMOKE_DEFAULT_PROGRAM, 'propose'),
    'two_fence': (two_fence([NEW], [HOOKED]), 'propose'),
    'two_fence_fix': (two_fence([NEW], [HOOKED]), 'fix'),
    'untagged_json_fence': (joined('```\n' + json.dumps({'changes': [NEW]}) + '\n```', fence('python', HOOKED)),
                            'propose'),
    'inline_only': (json.dumps({'changes': [dict(NEW, source=HOOKED)]}), 'propose'),
    'inline_only_fix': (json.dumps({'changes': [dict(NEW, source=HOOKED)]}), 'fix'),
    'inline_fenced': (manifest({'changes': [dict(NEW, source='```python\n' + HOOKED + '```')]}), 'propose'),
    'inline_code_alias': (json.dumps({'changes': [dict(NEW, code=HOOKED)]}), 'propose'),
    'two_changes_two_fences': (two_fence([NEW, NEW2], [HOOKED, BINDINGS]), 'propose'),
    'three_changes': (two_fence([NEW, NEW2, dict(NEW, description='Third')], [HOOKED, BINDINGS, OTHER]), 'propose'),
    'extra_json_block': (joined(manifest({'example': 1}), two_fence([NEW], [HOOKED])), 'propose'),
    'extra_top_level_key': (joined(manifest({'notes': 'one program', 'changes': [NEW]}), fence('python', HOOKED)),
                            'propose'),
    'json_comment': (joined('```json\n{"changes": [' + json.dumps(NEW) + ']} // one change\n```',
                            fence('python', HOOKED)), 'propose'),
    'value_conversions': (two_fence([dict(NEW, max_note_chars='600', requests_second_call=0)], [HOOKED]), 'propose'),
    'kind_missing': (two_fence([{key: value for key, value in NEW.items() if key != 'kind'}], [HOOKED]), 'propose'),
    'unknown_revision': (two_fence([dict(NEW, kind='revision', revises='p-unknown-1-1')], [HOOKED]), 'propose'),
    'broken_sibling_block': (two_fence([NEW, dict(NEW, description='Second')], [HOOKED, BROKEN]), 'propose'),
    'inline_sibling_and_broken_block': (two_fence([dict(NEW, source=BINDINGS), dict(NEW, description='Second'),
                                                   dict(NEW, description='Third')], [HOOKED, BROKEN]), 'propose'),
    'trailing_prose': (two_fence([NEW], [HOOKED]) + '\n\nThis program lists one fact.', 'propose'),
}


@pytest.mark.parametrize('name', sorted(PARITY))
def test_parity_with_frozen_reader(name):
    """Well-formed replies: the same records as the real frozen reader (entry, source, kind and repair rows)."""
    text, mode = PARITY[name]
    expected = frozen(text, mode)
    result = check_shape(typed(text, mode))
    assert result['problem'] is None and len(result['records']) == len(expected)
    for record, frozen_record in zip(result['records'], expected):
        assert frozen_record['error'] is None and record['problem'] is None
        assert record['entry'] == frozen_record['entry'] and record['source'] == frozen_record['source']
        assert record['repairs'] == frozen_record['repairs'] and record['kind'] == frozen_record['entry']['kind']
        assert not TYPED_ONLY_RULES & set(rules(record))
    if name == 'broken_sibling_block':   # a sibling's broken block costs no readable program (A2')
        assert [record['source'] for record in result['records']] == [HOOKED, BROKEN]
    if name == 'inline_sibling_and_broken_block':
        assert [record['source'] for record in result['records']] == [BINDINGS, HOOKED, BROKEN]


def test_a_block_is_never_forced_on_a_change_with_its_own_inline_program():
    """Three blocks for two changes that need one (the third change has an inline program): no rule assigns them, the
    two changes get blocks_not_assignable and the change with its own program is still read."""
    text = two_fence([dict(NEW, source=BINDINGS), dict(NEW, description='Second'), dict(NEW, description='Third')],
                     [HOOKED, BROKEN, 'Example output: 3 facts\n'])
    result = check_shape(typed(text))
    assert [record['source'] for record in result['records']] == [BINDINGS, None, None]
    assert [(record['problem'] or {}).get('code') for record in result['records']] == [
        None, 'blocks_not_assignable', 'blocks_not_assignable']
    assert replies.readable(result) and [row['rule'] for row in result['repairs']] == ['fence_unassigned_ignored']


def test_kinds_follow_the_frozen_rules():
    """Kind as the frozen reader resolves it; other kinds come back without source and without normalisation."""
    parent = package.Package((package.Procedure(
        id='p-searchqa-1-1', origin='searchqa', description='d', hooks=('applies', 'before_call'), source=HOOKED,
        evidence='engineering_fixture', max_note_chars=600, lineage={'parent': None, 'revises': None,
                                                                     'engineer_call': 'a' * 64},
        policy_version=profiles.POLICY_VERSIONS[MACHINERY]),), 'typed/G/s1', 'engineering_fixture')
    changes = [{'id': 'p-searchqa-1-1', 'description': 'edit', 'source': OTHER},      # no kind, parent id: revision
               {'kind': 'deletion', 'id': 'p-searchqa-1-1'},
               {'kind': 'revision', 'revises': 'p-unknown-9-9', 'description': 'x'}]    # unknown target: new
    text = joined(manifest({'changes': changes}), fence('python', HOOKED))
    expected = [item['entry']['kind'] for item in frozen(text, parent=parent)]
    result = check_shape(typed(text, parent_ids=parent.order))
    assert [record['kind'] for record in result['records']] == expected == ['revision', 'deletion', 'new']
    revision, deletion, new = result['records']
    assert revision['source'] is None and revision['entry'] == {'id': 'p-searchqa-1-1', 'description': 'edit',
                                                                'kind': 'revision'}
    assert revision['read']['ignored'] == [{'from': 'inline', 'chars': len(OTHER), 'sha256': sha(OTHER),
                                            'why': 'unread'}]
    assert deletion['source'] is None and deletion['problem'] is None
    assert new['source'] == HOOKED and 'unknown_revision_is_new' in rules(new) and 'revises' not in new['entry']
    unknown = check_shape(typed(joined(manifest({'changes': [{'kind': 'improve'}]}), fence('python', HOOKED))))
    assert unknown['records'][0]['problem']['code'] == 'unknown_kind'
    fixed = only(typed(two_fence([dict(NEW, kind='deletion')], [HOOKED]), 'fix'))
    assert fixed['kind'] == 'new' and fixed['source'] == HOOKED and 'fix_kind_ignored' in rules(fixed)


# ---- two programs are a problem, never a guess -----------------------------------------------------------------
@pytest.mark.parametrize('shape', ['two_fences', 'inline_and_fence', 'source_and_code', 'fix_echo_and_two_new'])
def test_two_different_programs_are_a_problem_never_a_guess(shape):
    mode, text = {
        'two_fences': ('propose', joined(manifest({'changes': [NEW]}), fence('python', HOOKED), fence('py', OTHER))),
        'inline_and_fence': ('propose', joined(manifest({'changes': [dict(NEW, source=HOOKED)]}),
                                               fence('python', OTHER))),
        'source_and_code': ('propose', manifest({'changes': [dict(NEW, source=HOOKED, code=OTHER)]})),
        'fix_echo_and_two_new': ('fix', joined(manifest({'changes': [dict(NEW, source=BAD)]}), fence('python', HOOKED),
                                               fence('python', OTHER))),
    }[shape]
    result = typed(text, mode)
    record = only(result)
    assert record['problem']['code'] == 'ambiguous_source' and record['source'] is None
    assert record['problem']['detail'].startswith('Change 1 gives two different programs: ')
    assert not replies.readable(result)


def test_equal_programs_count_once():
    """The same program twice (fence and inline, or two fences differing only in surrounding blank lines) is one
    program; the inline text is returned as the frozen reader returns it."""
    record = only(typed(joined(manifest({'changes': [dict(NEW, source=HOOKED)]}), fence('python', HOOKED))))
    assert record['source'] == HOOKED and record['read']['source_from'] == 'inline_and_fence_equal'
    assert record['read']['ignored'] == [{'from': 'fence 1', 'chars': len(HOOKED), 'sha256': sha(HOOKED),
                                          'why': 'same_program'}]
    record = only(typed(joined(manifest({'changes': [NEW]}), fence('python', HOOKED), fence('python', '\n' + HOOKED))))
    assert record['source'] == HOOKED and record['read']['source_from'] == 'fence'


def test_non_program_blocks_beside_programs_are_recorded():
    text = joined(manifest({'changes': [NEW]}), fence('text', 'Example output: 3 facts'), fence('python', HOOKED))
    result = check_shape(typed(text))
    assert result['records'][0]['source'] == HOOKED
    row = [row for row in result['repairs'] if row['rule'] == 'fence_not_program_ignored']
    assert row == [{'rule': 'fence_not_program_ignored', 'path': '$', 'count': 1,
                    'blocks': [{'block': 1, 'chars': 24, 'sha256': sha('Example output: 3 facts\n')}]}]
    stray = check_shape(typed(joined(manifest({'changes': [dict(NEW, source=HOOKED)] * 2}), fence('python', OTHER))))
    assert [record['source'] for record in stray['records']] == [HOOKED, HOOKED]
    assert [row['rule'] for row in stray['repairs']] == ['fence_unassigned_ignored']


def test_manifest_json_positions_count_in_the_text_that_was_parsed():
    """The parser position of a broken manifest counts lines of the reply itself when there is no fence."""
    result = check_shape(typed('\n\n{"changes": [}'))
    assert result['problem']['detail'] == ('The reply could not be parsed as JSON: Expecting value at line 3, column '
                                           '14.')
    result = check_shape(typed(joined('{"changes": [}', fence('text', 'notes'))))
    assert result['problem']['detail'] == ('The text outside the fenced blocks could not be parsed as JSON: Expecting '
                                           'value at line 1, column 14.')
    result = check_shape(typed('```json\n{"a": 1, "a": 2}\n```'))
    assert result['problem']['detail'] == ("The fenced JSON block could not be parsed as JSON: the key 'a' appears "
                                           "twice in one object.")


def test_manifest_outside_the_fences():
    record = only(typed(joined('Here is the change: ' + json.dumps({'changes': [NEW]}) + ' and its code:',
                               fence('python', HOOKED))))
    assert record['source'] == HOOKED and 'manifest_outside_fence' in rules(record)
    plain = only(typed(json.dumps({'changes': [NEW]}) + '\n' + fence('python', HOOKED)))
    assert plain['source'] == HOOKED and 'manifest_outside_fence' in rules(plain)


# ---- never raises, never executes, never weakens the screen ----------------------------------------------------
ADVERSARIAL = [
    '', ' ', '{', '}', '[', '```', '```json\n```', '```json\n{\n```', '[' * 100 + ']' * 100,
    fence('json', '[' * 100 + ']' * 100), '{"a": ' * 100 + '1' + '}' * 100, '{"changes": [], "changes": []}',
    manifest({'changes': [1, 'x', None, True]}), '{"changes": [{"kind": ["new"]}, {"kind": {"a": 1}}]}',
    joined(manifest({'changes': [dict(NEW, description=['x'])]}), fence('python', HOOKED)),
    joined('{"changes": [{"kind": "new", "max_note_chars": "' + '9' * 5000 + '"}]}', fence('python', HOOKED)),
    'x' * 2_000_000, '\ud800', manifest({'changes': [dict(NEW, description='\ud800')]}),
    '{"changes": [{"max_note_chars": NaN}]}', '{"changes": [' + '[' * 100 + ']' * 100 + ']}',
    '{"changes": [{"description": ' + '{"a": ' * 100 + '1' + '}' * 100 + '}]}',
    '```python\nx\n```\n' * 500, '```python\n' + HOOKED, '~~~python\n' + HOOKED + '```\n', 'def applies(view):\x00\n',
    fence('json', '{"changes": [{"source": "def applies(view):\\n    return True\\n"}]}') * 3,
    joined(manifest({'changes': {'source': 5, 'code': None}})), manifest({'changes': [{'source': '```python\n```'}]}),
    '{"plan": {"changes": []}}', '"just a string"', '42', 'null', '[]', '[{}]', '{}', '{"source": ""}',
    '{"change": [], "changes": {}}', fence('json5', "{'changes': [{'kind': 'new',},],}"),
]


def fuzz_replies(count, seed=20261112):
    """Random replies: shuffled manifests (several envelopes), fences, programs and junk fragments."""
    rng = random.Random(seed)
    values = {'kind': ['new', 'revision', 'deletion', 'narrowing', 'New', None, ['new'], {'a': 1}, 3],
              'source': [HOOKED, OTHER, BROKEN, BAD, '', 'PLACEHOLDER', '```python\n' + HOOKED + '```', 5, None],
              'code': [HOOKED, OTHER, BROKEN, ''], 'id': ['p-searchqa-1-1', 'p1', 7],
              'revises': ['p-searchqa-1-1', 'p-unknown'], 'hooks': [['applies', 'before_call'], 'applies', None, [1]],
              'max_note_chars': [600, '600', -1, 'x', 1e300], 'description': ['d', '', ['x'], {'y': 1}],
              'requests_second_call': [True, 0, 'true', 'maybe'], 'replay_tests': [[], [{'hook': 'x'}], 'x'],
              'extra': [1, {'changes': []}]}
    fragments = ['```json\n', '```python\n', '```\n', '~~~\n', '{', '}', '[', ']', '"', "'", '\\', '\n', ',', ':',
                 '{"changes": [', '"source": ', '// c\n', '/* c', 'NaN', '1e999', HOOKED, BROKEN, '\x00', 'é', '9' * 40]
    for _ in range(count):
        changes = []
        for _ in range(rng.randint(0, 4)):
            keys = rng.sample(sorted(values), rng.randint(0, 6))
            changes.append({key: rng.choice(values[key]) for key in keys} if rng.random() > 0.1 else
                           rng.choice(['x', 1, None, []]))
        first = changes[0] if changes else {}
        envelope = rng.choice([{'changes': changes}, {'change': first}, changes, {'changes': changes, 'change': first},
                               {'plan': changes}, first])
        text = json.dumps(envelope)
        head = rng.choice([fence('json', text), fence('', text), text, 'Here: ' + text + ' done.', ''])
        parts = [head] + [fence(rng.choice(['python', '', 'py', 'text']),
                                rng.choice([HOOKED, OTHER, BROKEN, BAD, '', 'print(1)\n', BINDINGS]))
                          for _ in range(rng.randint(0, 4))]
        if rng.random() < 0.3:
            rng.shuffle(parts)
        if rng.random() < 0.3:
            parts.append(''.join(rng.choice(fragments) for _ in range(rng.randint(1, 12))))
        yield '\n\n'.join(parts)


def test_reader_never_raises():
    """No reply content makes a reader raise: every input gives problems or records, a sentence for every problem,
    and every returned source is text of the reply itself (a block body, or an inline value)."""
    for text in ADVERSARIAL + list(fuzz_replies(400)):
        for mode, parent_ids in (('propose', ()), ('propose', ('p-searchqa-1-1',)), ('fix', ())):
            result = check_shape(typed(text, mode, parent_ids=parent_ids))
            for record in result['records']:
                source = record['source']
                assert source is None or source in text or json.dumps(source)[1:-1] in text
            if not replies.readable(result):
                problems = [result['problem']] if result['problem'] else [r['problem'] for r in result['records']]
                request = replies.retry_request(mode, 'searchqa', problems, text)
                assert request is None or json.loads(request[1])['previous_reply'] == text
    assert typed('x' * 2_000_000)['problem']['code'] == 'oversize'


def test_resources_is_a_problem_not_an_exception(monkeypatch):
    def exhausted(reply):
        raise RecursionError('maximum recursion depth exceeded')
    monkeypatch.setattr(replies, '_blocks', exhausted)
    result = check_shape(typed(two_fence([NEW], [HOOKED])))
    assert result['problem'] == {'code': 'resources', 'change': None, 'detail': (
        'The reply could not be read within the reader limits (RecursionError); send it again shorter and with less '
        'nesting.')}


def test_reader_does_not_execute(scratch):
    """Programs and manifests are parsed only: a module-level write, an import and an expression in the manifest
    leave no trace."""
    canary = scratch / 'written.txt'
    program = ('import typed2_replies_canary\n\nopen(%r, "w").write("ran")\n\n\n' % str(canary)) + HOOKED
    texts = [two_fence([NEW], [program]), json.dumps({'changes': [dict(NEW, source=program)]}),
             manifest({'changes': [dict(NEW, source='```python\n' + program + '```')]}),
             '```json\n{"changes": [__import__("os").system("touch %s")]}\n```' % canary,
             '{"changes": [open(%r, "w")]}' % str(canary)]
    for text in texts:
        for mode in ('propose', 'fix'):
            check_shape(typed(text, mode))
    record = only(typed(texts[0]))
    assert record['source'] == program and record['read']['is_program'] is True
    assert not canary.exists() and 'typed2_replies_canary' not in sys.modules


def test_tolerance_does_not_weaken_screen():
    """An F2-shaped reply (placeholder inline source) whose fenced program imports os reaches the frozen static
    screen byte for byte, which refuses it with the same violations as the canonical reply of the same source."""
    version = profiles.POLICY_VERSIONS[MACHINERY]
    tolerant = joined(manifest({'changes': [dict(NEW, source='PLACEHOLDER')]}), fence('python', BAD))
    canonical = two_fence([NEW], [BAD])
    screened = [v.to_json() for v in policy.check(BAD, version=version)]
    assert screened and any(row['rule'] == 'import' for row in screened)
    for mode in ('propose', 'fix'):
        records = [only(typed(text, mode)) for text in (tolerant, canonical)]
        assert [record['source'] for record in records] == [BAD, BAD]
        for record in records:
            assert [v.to_json() for v in policy.check(record['source'], version=version)] == screened


# ---- problem sentences and the format retry --------------------------------------------------------------------
def a_program_of_chars(chars):
    return program_of(chars, 'one')


SENTENCES = {   # code: (mode, reply, the exact detail)
    'oversize': ('propose', 'x' * (engineer_reader.MAX_REPLY_BYTES + 1),
                 'The reply has 1,048,577 bytes; at most 1,048,576 bytes are read, so nothing in it was read.'),
    'several_manifests': ('propose', joined(manifest({'a': 1}), manifest({'b': 2}), fence('python', HOOKED)),
                          'The reply has 2 JSON blocks or objects and 0 of them have a `changes` or `change` key; '
                          'exactly one is expected.'),
    'no_manifest': ('propose', 'a' * 411 + '.',
                    'No JSON object was found (fenced code blocks: 0; other text: 412 characters).'),
    'manifest_json': ('propose', joined('```json\n{"changes": [}\n```', fence('python', HOOKED)),
                      'The fenced JSON block could not be parsed as JSON: Expecting value at line 1, column 14.'),
    'ambiguous_envelope': ('propose', manifest({'changes': [NEW], 'change': {'kind': 'new', 'description': 'x'}}),
                           'The JSON object has both `changes` and `change`, with different contents (changes: 1; '
                           'change: 1); send only `changes`.'),
    'no_changes_key': ('propose', '```json\n{"plan": "one helper", "notes": "none"}\n```',
                       "The JSON object has the top-level keys ['plan', 'notes']; none of them is `changes`."),
    'change_not_object': ('propose', manifest({'changes': [NEW, 'x']}), 'Change 2 is a JSON string, not an object.'),
    'too_many_changes': ('propose', two_fence([NEW] * 4, [HOOKED] * 4),
                         'The reply has 4 changes; at most 3 are allowed, so none of them was read.'),
    'fix_change_count': ('fix', two_fence([NEW, NEW], [HOOKED, OTHER]),
                         'A fix reply must hold exactly one change; this reply holds 2 changes.'),
    'unknown_kind': ('propose', joined(manifest({'changes': [{'kind': 'improve', 'description': 'x'}]}),
                                       fence('python', HOOKED)),
                     'Change 1 has a `kind` that is none of new, revision, deletion, narrowing; a new program has '
                     '"kind": "new".'),
    'blocks_not_assignable': ('propose', two_fence([NEW] * 3, [HOOKED, OTHER]),
                              'Change 1 cannot be matched to a fenced block: the reply has 3 new changes and 2 fenced '
                              'code blocks (2 of them define a hook function); give one python block per change, in '
                              'the same order.'),
    'ambiguous_source': ('fix', joined(manifest({'changes': [dict(NEW, source=a_program_of_chars(1204))]}),
                                       fence('python', program_of(1377, 'two'))),
                         'Change 1 gives two different programs: inline `source` (1,204 characters) and fenced block '
                         '1 (1,377 characters). Send exactly one.'),
    'no_source': ('fix', manifest({'changes': [{'id': 'p1', 'source': ''}]}),
                  'Change 1 has no program text that can be taken (its fenced code blocks: 0, none defining a hook '
                  'function; inline `source`: 0 characters).'),
    'entry_field': ('propose', joined(manifest({'changes': [dict(NEW, description=['x'])]}), fence('python', HOOKED)),
                    'Change 1 has an entry field that cannot be used: $.description must have type str, got list.'),
}


def problems_of(result):
    return [result['problem']] if result['problem'] else [r['problem'] for r in result['records'] if r['problem']]


@pytest.mark.parametrize('code', sorted(SENTENCES))
def test_problem_sentence(code):
    mode, text, detail = SENTENCES[code]
    result = check_shape(typed(text, mode))
    found = [problem for problem in problems_of(result) if problem['code'] == code]
    assert found and found[0]['detail'] == detail and not replies.readable(result)


def test_every_problem_code_has_one_sentence():
    assert len(replies.PROBLEM_CODES) == 15 and set(replies.PROBLEM_SENTENCES) == set(replies.PROBLEM_CODES)
    assert set(SENTENCES) | {'resources'} == set(replies.PROBLEM_CODES)
    # the three forms DESIGN 3.3 / spec/reply.md item 21 fixed, rendered from the templates
    sentences = replies.PROBLEM_SENTENCES
    assert sentences['no_changes_key'].format(value='object', keys=repr(['plan', 'notes'])) == (
        "The JSON object has the top-level keys ['plan', 'notes']; none of them is `changes`.")
    assert sentences['no_manifest'].format(blocks='0', chars='412') == (
        'No JSON object was found (fenced code blocks: 0; other text: 412 characters).')
    assert sentences['ambiguous_source'].format(
        change=1, count='two', programs='inline `source` (1,204 characters) and fenced block 1 (1,377 characters)') == (
        'Change 1 gives two different programs: inline `source` (1,204 characters) and fenced block 1 (1,377 '
        'characters). Send exactly one.')


@pytest.mark.parametrize('code', sorted(SENTENCES))
def test_retry_request_text(code):
    mode, text, detail = SENTENCES[code]
    problems = problems_of(typed(text, mode))
    request = replies.retry_request(mode, 'searchqa', problems, text)
    if len(text.encode('utf-8')) > replies.RETRY_PREVIOUS_REPLY_BYTES:
        assert request is None
        return
    system, user = request
    assert system == replies.FORMAT_RETRY_SYSTEM
    assert user == json.dumps(json.loads(user), ensure_ascii=False, sort_keys=True)      # canonical JSON
    assert json.loads(user) == {'request': 'format_retry', 'purpose': mode, 'bench': 'searchqa',
                                'problems': [{'code': p['code'], 'change': p['change'], 'detail': p['detail']}
                                             for p in problems],
                                'expected_format': replies.REPLY_FORMAT[mode], 'previous_reply': text}
    assert detail in [p['detail'] for p in json.loads(user)['problems']]


def test_retry_request_bounds_and_caller_mistakes():
    problem = {'code': 'no_manifest', 'change': None, 'detail': 'x.'}
    assert replies.retry_request('fix', 'officeqa', [problem], 'a' * 200_000) is not None
    assert replies.retry_request('fix', 'officeqa', [problem], 'a' * 200_001) is None
    assert replies.retry_request('fix', 'officeqa', [problem], 'é' * 100_001) is None      # bytes, not characters
    for purpose, bench, problems, previous in (('write', 'searchqa', [problem], 'x'), ('fix', '', [problem], 'x'),
                                               ('fix', 'searchqa', [], 'x'), ('fix', 'searchqa', [{'code': 'x'}], 'x'),
                                               ('fix', 'searchqa', [problem], None)):
        with pytest.raises(ValueError):
            replies.retry_request(purpose, bench, problems, previous)


def test_caller_mistakes_raise_value_error():
    for call in (lambda: replies.read_proposals(None), lambda: replies.read_proposals(b'x'),
                 lambda: replies.read_proposals('x', parent_ids=(1,)),
                 lambda: replies.read_fix('x', change={'entry': {}}), lambda: replies.read_fix('x', change=None),
                 lambda: replies.read_fix('x', change={'entry': {'kind': 'revision'}, 'source': 'x'}),
                 lambda: replies.read_with_retry('x', 'a', purpose='write', bench='searchqa', send=None,
                                                 budget=replies.RetryBudget(), read=replies.read_proposals)):
        with pytest.raises(ValueError):
            call()


# ---- the retry budget and read_with_retry ----------------------------------------------------------------------
class Sender:
    """send(system, user) -> (reply | None, request sha256), replying from a list; records every call."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.answers.pop(0), sha(system + '\0' + user)


def test_retry_budget_is_one_per_unit_attempt():
    budget = replies.RetryBudget()
    assert replies.FORMAT_RETRIES_PER_UNIT == 1 and budget.take() is True
    assert budget.take() is False and budget.take() is False


def test_readable_reply_sends_no_retry():
    send = Sender()
    outcome = replies.read_with_retry(two_fence([NEW], [HOOKED]), 'a' * 64, purpose='propose', bench='searchqa',
                                      send=send, budget=replies.RetryBudget(), read=replies.read_proposals)
    assert send.calls == [] and outcome['format_retry'] is None and outcome['request_sha256'] == 'a' * 64
    assert outcome['result']['records'][0]['source'] == HOOKED
    empty = replies.read_with_retry(manifest({'changes': []}), 'b' * 64, purpose='propose', bench='searchqa',
                                    send=send, budget=replies.RetryBudget(), read=replies.read_proposals)
    assert send.calls == [] and empty['result']['records'] == [] and empty['format_retry'] is None
    silent = replies.read_with_retry(None, 'c' * 64, purpose='fix', bench='searchqa', send=send,
                                     budget=replies.RetryBudget(), read=replies.read_proposals)
    assert send.calls == [] and silent == {'result': None, 'request_sha256': 'c' * 64, 'format_retry': None}


def test_unreadable_reply_gets_one_retry_and_the_retry_call_is_the_lineage():
    send = Sender(two_fence([NEW], [HOOKED]))
    outcome = replies.read_with_retry(PROSE, 'a' * 64, purpose='propose', bench='zebralogic', send=send,
                                      budget=replies.RetryBudget(), read=replies.read_proposals)
    assert len(send.calls) == 1
    system, user = send.calls[0]
    assert (system, user) == replies.retry_request('propose', 'zebralogic', problems_of(typed(PROSE)), PROSE)
    retry_sha = sha(system + '\0' + user)
    assert outcome['request_sha256'] == retry_sha and outcome['result']['records'][0]['source'] == HOOKED
    assert outcome['format_retry'] == {'first_request_sha256': 'a' * 64, 'request_sha256': retry_sha,
                                       'problems': problems_of(typed(PROSE)), 'no_reply': False, 'readable': True,
                                       'problems_after': []}


def test_retry_still_unreadable_or_not_delivered():
    send = Sender('still no manifest')
    outcome = replies.read_with_retry(PROSE, 'a' * 64, purpose='propose', bench='searchqa', send=send,
                                      budget=replies.RetryBudget(), read=replies.read_proposals)
    retry = outcome['format_retry']
    assert len(send.calls) == 1 and retry['readable'] is False and retry['no_reply'] is False
    assert retry['problems_after'][0]['code'] == 'no_manifest' and outcome['request_sha256'] == retry['request_sha256']
    assert not replies.readable(outcome['result'])
    send = Sender(None)
    outcome = replies.read_with_retry(PROSE, 'a' * 64, purpose='propose', bench='searchqa', send=send,
                                      budget=replies.RetryBudget(), read=replies.read_proposals)
    assert len(send.calls) == 1 and outcome['format_retry']['no_reply'] is True
    assert outcome['request_sha256'] == 'a' * 64 and outcome['result']['problem']['code'] == 'no_manifest'


def test_the_budget_is_shared_by_the_proposal_and_every_fix_read():
    """One budget per programs unit attempt: the first unreadable reply (here a fix reply) takes the retry; a later
    unreadable reply is recorded as budget_spent and sends nothing."""
    budget, send = replies.RetryBudget(), Sender(two_fence([NEW], [HOOKED]))
    fix = lambda text: replies.read_fix(text, change=UNDER_REPAIR)   # noqa: E731
    first = replies.read_with_retry(two_fence([NEW], [BAD]), 'a' * 64, purpose='propose', bench='searchqa',
                                    send=send, budget=budget, read=replies.read_proposals)
    assert first['format_retry'] is None                       # a screen failure is the fix call's job, not a retry
    second = replies.read_with_retry(PROSE, 'b' * 64, purpose='fix', bench='searchqa', send=send, budget=budget,
                                     read=fix)
    assert second['format_retry']['readable'] is True and second['result']['records'][0]['source'] == HOOKED
    third = replies.read_with_retry(PROSE, 'c' * 64, purpose='fix', bench='searchqa', send=send, budget=budget,
                                    read=fix)
    assert third['format_retry'] == {'skipped': 'budget_spent', 'problems': problems_of(fix(PROSE))}
    assert len(send.calls) == 1 and third['request_sha256'] == 'c' * 64
    assert json.loads(send.calls[0][1])['expected_format'] == replies.REPLY_FORMAT['fix']


def test_a_too_large_reply_is_not_retried_and_keeps_the_budget():
    budget, send = replies.RetryBudget(), Sender()
    large = 'a' * 200_001
    outcome = replies.read_with_retry(large, 'a' * 64, purpose='propose', bench='searchqa', send=send, budget=budget,
                                      read=replies.read_proposals)
    assert outcome['format_retry'] == {'skipped': 'reply_too_large', 'problems': problems_of(typed(large))}
    assert send.calls == [] and budget.take() is True


def test_send_exceptions_pass_through():
    class Stop(Exception):
        pass

    def send(system, user):
        raise Stop('cap reached')
    with pytest.raises(Stop):
        replies.read_with_retry(PROSE, 'a' * 64, purpose='propose', bench='searchqa', send=send,
                                budget=replies.RetryBudget(), read=replies.read_proposals)


# ---- pins and boundaries ---------------------------------------------------------------------------------------
PINNED = {'format_retry_system': '8b0e72cfeaede6d8be7f96248b151875748e3103b2cdae22a4a548e82856d579',
          'problem_sentences': 'cb5cc536b271544048a80ff7e689840ce8ab653bd3958126e58327c6eb7b6b73',
          'reply_format.fix': '34bf0e0892d2b3318fb2e840a5f99d8010b76eeca1ea4b45dd5a8cfa9c0066b6',
          'reply_format.propose': '65248e276b3819a25b9d83e3eb8087212fc52563f804faea0fe04b393da6f517'}


def test_reply_pins():
    assert replies.READER == 'typed-reply-reader-1' and replies.RETRY_PREVIOUS_REPLY_BYTES == 200_000
    assert replies.computed_pins() == replies.PINS == PINNED and replies.verify() == []
    assert sha(replies.FORMAT_RETRY_SYSTEM) == PINNED['format_retry_system']
    assert sha(json.dumps(replies.PROBLEM_SENTENCES, ensure_ascii=False, sort_keys=True)) == PINNED['problem_sentences']


def test_pinned_texts_are_the_design_wording():
    """FORMAT_RETRY_SYSTEM and REPLY_FORMAT are the texts of DESIGN 3.3, word for word."""
    if not DESIGN.exists():
        pytest.skip('the design document is not in this tree')
    lines = DESIGN.read_text(encoding='utf-8').splitlines()
    found = {name: line[len(name) + 2:] for line in lines
             for name in ('FORMAT_RETRY_SYSTEM', "REPLY_FORMAT['propose']", "REPLY_FORMAT['fix']")
             if line.startswith(name + ': ')}
    assert found == {'FORMAT_RETRY_SYSTEM': replies.FORMAT_RETRY_SYSTEM,
                     "REPLY_FORMAT['propose']": replies.REPLY_FORMAT['propose'],
                     "REPLY_FORMAT['fix']": replies.REPLY_FORMAT['fix']}


def test_machinery_symbols_resolve_and_the_module_imports_only_them():
    for module, names in replies.MACHINERY_SYMBOLS.items():
        loaded = importlib.import_module(module)
        assert all(hasattr(loaded, name) for name in names), module
    tree = ast.parse(Path(replies.__file__).read_text(encoding='utf-8'))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported |= {(node.level, node.module, alias.name) for alias in node.names}
        elif isinstance(node, ast.Import):
            imported |= {(0, None, alias.name) for alias in node.names}
    frozen_names = {name for level, module, name in imported if module == 'skillopt.execskill'}
    assert frozen_names == {'engineer', 'engineer_reader', 'profiles'}
    assert {name for level, module, name in imported if level == 1} == {'MACHINERY'}
    assert not {'writers', 'engineer_prompt'} & {name for _, _, name in imported}
    used = {(node.value.id, node.attr) for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id in ('engineer', 'engineer_reader', 'profiles')}
    declared = {(module.rsplit('.', 1)[1], name) for module, names in replies.MACHINERY_SYMBOLS.items()
                for name in names}
    assert used == declared
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {'eval', 'exec', 'compile', '__import__'}


# ---- Codex review round 1 (2026-11-12): manifest choice and block ownership ------------------------------------
def _all_rules(result):
    return [row['rule'] for row in result['repairs']] + [row['rule'] for record in result['records']
                                                         for row in record['repairs']]


def test_a_changes_block_and_a_change_block_with_two_programs_are_several_manifests():
    """Rule 3 (b): the single block with `changes` OR `change`; two such blocks are never settled by preferring one
    key, which would drop the other block's program without a format retry (finding 1)."""
    text = joined(manifest({'changes': [dict(NEW, source=HOOKED)]}), manifest({'change': dict(NEW, source=OTHER)}))
    result = typed(text)
    assert result['problem'] is not None and result['problem']['code'] == 'several_manifests'
    assert result['records'] == []


def test_the_one_parsing_json_block_is_the_manifest_beside_a_malformed_one():
    """Rule 3 (a), exactly one candidate parses: a malformed block cannot be a manifest, so the other one is read
    without spending the format retry (finding 2)."""
    text = joined('```json\n{"changes": [}\n```', manifest(dict(NEW, source=HOOKED)))
    result = check_shape(typed(text))
    assert result['problem'] is None and [record['source'] for record in result['records']] == [HOOKED]
    assert 'extra_json_blocks_ignored' in _all_rules(result) and 'bare_change' in _all_rules(result)


def test_a_prose_fence_never_takes_a_position_beside_a_program():
    """Rule 7 (A2') only over python-tagged fences: two changes without a source, a text fence and one program give
    blocks_not_assignable for both (the format retry may repair it); the prose is never change 1's source and the
    program never lands on change 2's entry (finding 3)."""
    text = joined('```json\n' + json.dumps({'changes': [NEW, dict(NEW, description='Second')]}, sort_keys=True)
                  + '\n```', fence('text', 'This program counts the facts of the question.\n'), fence('python', HOOKED))
    result = check_shape(typed(text))
    assert [(record['problem'] or {}).get('code') for record in result['records']] == ['blocks_not_assignable'] * 2
    assert [record['source'] for record in result['records']] == [None, None]


def test_an_untagged_broken_block_does_not_take_a_position_either():
    """The python-tag condition of A2' also covers an untagged fence: only ```python / ```py / ```python3 fences keep
    the frozen reader's positional reading of a broken sibling block."""
    text = joined('```json\n' + json.dumps({'changes': [NEW, dict(NEW, description='Second')]}, sort_keys=True)
                  + '\n```', fence('python', HOOKED), fence('', BROKEN))
    result = check_shape(typed(text))
    assert [(record['problem'] or {}).get('code') for record in result['records']] == ['blocks_not_assignable'] * 2
