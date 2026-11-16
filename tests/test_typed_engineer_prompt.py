"""typed-v2 program-writer prompt (DESIGN 3.2, decision D3; spec/engineer.md section 4; addendum O7): the 22 rule
rows, each with a legal and an illegal example checked by the REAL frozen screen; every screen rule stated; the
rendered lists and limits are the bound ones; the ten texts render, equal the DESIGN wording and their pins; the
embedded reply format; hook signatures; the fix evidence. Literal strings only: no network, no Docker, no /data, no
model call, no file written."""
import ast
import hashlib
import importlib
import inspect
import re
from pathlib import Path

import pytest

from skillopt.execskill import package, policy, profiles, protocol
from skillopt.execskill.typed import MACHINERY, MAX_PROGRAM_CANDIDATES, MAX_PROGRAM_PROPOSALS, ORDER
from skillopt.execskill.typed import engineer_prompt as ep
from skillopt.execskill.typed import replies

DESIGN = Path(__file__).resolve().parents[1] / 'docs' / 'handoff' / 'typed-v2' / 'DESIGN.md'
KEYS = [(bench, purpose) for bench in ORDER for purpose in ('propose', 'fix')]

# The ten pins, the values Step 7's machinery check 6 compares (DESIGN 4.3); a text change needs new values here,
# in engineer_prompt.PINS and a new PROMPT_VERSION. typed-engineer-prompt-2 (fix-b, coord-1): the [import] row states
# that a from-import of a banned member is rejected (IMPORT_DELTA below); every other byte is DESIGN 3.2's.
PINNED = {
    ('searchqa', 'propose'): '2922c9d9a035b4f43867ec85a7e8dbc07b58caf737230104792ddddf16dc2246',
    ('searchqa', 'fix'): '7c65003537d122b2f7aa44d281958960116f00a54b79942c61c99cf3ef700c11',
    ('officeqa', 'propose'): '4b9817730e2d9fe8b314028652ac7f574672d7a7001fbd9606377da7d88d6947',
    ('officeqa', 'fix'): 'd6fb75ee3398bb30a3ab78d9fdec0a39e313eee996921a3067cf732512a34dbd',
    ('zebralogic', 'propose'): '1a8bf9a409861ce11e17ee2fd4b138c69981c5f1ab578ab756357bc3fab8243e',
    ('zebralogic', 'fix'): 'b7db80956e3410c386e8333b197c9106d473e7dab37416ac7e3e58856b94f31b',
    ('spreadsheetbench', 'propose'): '62ed78f84b98390e2de63b8add4da499dca77efdf5a0d47886102f86b6c38dde',
    ('spreadsheetbench', 'fix'): '3f0c0d4d9e1f3ed275c5f14927d4c80c092d690adca1b6dd536177006012f345',
    ('alfworld', 'propose'): '20108ba71865560182c09d8cf6ff9106f1eb51944041cf0f57d949e1bff34f4e',
    ('alfworld', 'fix'): '8a06fbbb1260f77571360ad32f88d23caaf76567b8bd1f01c6474ba43cb4a07b',
}
ROW_KEYS = ('size', 'syntax', 'top_level', 'constant_value', 'constant_word_set', 'constant_regex', 'constant_other',
            'constant_size', 'statement', 'decorator', 'import', 'name', 'attribute', 'attribute_type_name',
            'attribute_data', 'numpy_random', 'clock', 'sympify', 'dunder_string', 'meta_option', 'bulletin_literal',
            'receptacle_literal')
PARENTS = {'constant_value': {'constant_word_set', 'constant_regex', 'constant_other'},
           'attribute': {'attribute_type_name', 'attribute_data'}}
# fix-b (coord-1): the frozen screen rejects a from-import of a member the name or attribute rules ban, or of a blocked
# module name (time and random included), with rule 'import'. DESIGN 3.2's [import] sentence called every such
# from-import allowed; typed-engineer-prompt-2 inserts INSERTED before 'No "import *"' and replaces the row's rewrite.
IMPORT_MEMBER_LINES = ('from datetime import time', 'from pandas import read_csv', 'from numpy import random')
INSERTED = ('In "from M import name" the name must not be one that the [name] or [attribute] rules below ban, nor a '
            'blocked module name (random and time included): "from datetime import time", "from pandas import '
            'read_csv" and "from numpy import random" are rejected. ')
IMPORT_DELTA = {'insert_before': 'No "import *", no other submodule', 'inserted': INSERTED,
                'rewrite_old': 'leave type hints out or use the built-in names (list, dict).',
                'rewrite_new': ('leave type hints out or use the built-in names (list, dict); for a banned member '
                                'import the module and write the member after a dot where the [attribute] rule '
                                'allows it (import datetime, then datetime.time).')}


def coord1(design_line):
    """DESIGN 3.2's [import] line as typed-engineer-prompt-2 states it (the coordinator's fix-b change coord-1)."""
    assert design_line.count(IMPORT_DELTA['insert_before']) == 1 and design_line.endswith(IMPORT_DELTA['rewrite_old'])
    line = design_line.replace(IMPORT_DELTA['insert_before'], INSERTED + IMPORT_DELTA['insert_before'])
    return line[:-len(IMPORT_DELTA['rewrite_old'])] + IMPORT_DELTA['rewrite_new']


def screen(text):
    """The frozen screen exactly as the typed code calls it: no bench, the main-v10 policy version."""
    return [v.to_json() for v in policy.check(text, version=ep.POLICY_VERSION)]


def program(top=(), body=()):
    return (''.join(line + '\n' for line in top) + 'def before_call(view, state):\n'
            + ''.join('    ' + line + '\n' for line in body) + '    return {}\n')


def paragraphs(text):
    return text[:-1].split('\n\n')


def screen_lines(text):
    return paragraphs(text)[6].split('\n')


def line_of(text, start):
    found = [line for line in screen_lines(text) if line.startswith(start)]
    assert len(found) == 1, start
    return found[0]


# ---- names, signatures, the rule table ---------------------------------------------------------------------------
def test_public_names_and_signatures():
    assert ep.PROMPT_VERSION == 'typed-engineer-prompt-2'   # -1 until fix-b coord-1 (the [import] row)
    assert ep.PURPOSES == ('propose', 'fix')
    assert ep.EVIDENCE_ROWS == 8 and ep.SOURCE_LINE_CHARS == 240
    assert ep.POLICY_VERSION == profiles.POLICY_VERSIONS[MACHINERY] == policy.POLICY_VERSION_V222
    assert ep.CHECKS == ('policy', 'hooks', 'structure', 'source')
    assert ep.NOTE_HOOKS_BY_BENCH == {'searchqa': ('before_call', 'bindings'), 'officeqa': ('before_call', 'bindings'),
                                      'zebralogic': ('before_call',),
                                      'spreadsheetbench': ('before_call', 'sheet_feedback'),
                                      'alfworld': ('alf_before_step',)}
    assert set(ep.CHECK_WORDS) == {'hooks', 'structure', 'source'}
    assert ep.CHECK_WORDS['hooks']['rule'] == 'no_hook_function'
    assert set(ep.PINS) == set(KEYS)
    signatures = {'system': ['bench', 'purpose'], 'rule_key_for': ['rule', 'detail', 'source_line'],
                  'screen_evidence': ['failed', 'source', 'bench'], 'verify': [], 'evidence_record': ['evidence']}
    for name, parameters in signatures.items():
        assert list(inspect.signature(getattr(ep, name)).parameters) == parameters, name
    assert ep.Rule._fields[:7] == ('key', 'rule', 'sentence', 'rewrite', 'legal', 'illegal', 'parent')


def test_rule_table_shape():
    assert tuple(row.key for row in ep.RULES) == ROW_KEYS
    sentence_rows = [row for row in ep.RULES if row.parent is None]
    rewrite_rows = [row for row in ep.RULES if row.parent is not None]
    assert len(ep.RULES) == 22 and len(sentence_rows) == 17 and len(rewrite_rows) == 5
    assert {row.key: row.parent for row in rewrite_rows} == {
        'constant_word_set': 'constant_value', 'constant_regex': 'constant_value', 'constant_other': 'constant_value',
        'attribute_type_name': 'attribute', 'attribute_data': 'attribute'}
    for row in ep.RULES:
        assert row.rule in policy.RULES, row.key
        assert isinstance(row.legal, str) and isinstance(row.illegal, str) and row.legal != row.illegal
        if row.key in PARENTS:
            assert row.rewrite is None and isinstance(row.sentence, str), row.key     # the two parents
        elif row.parent is not None:
            assert row.sentence is None and isinstance(row.rewrite, str), row.key
            assert ep.RULES[[r.key for r in ep.RULES].index(row.parent)].rule == row.rule
        else:
            assert isinstance(row.sentence, str) and isinstance(row.rewrite, str), row.key
    assert len({row.rewrite for row in ep.RULES if row.rewrite is not None}) == 20       # evidence_record's lookup


@pytest.mark.parametrize('key', ROW_KEYS)
def test_rule_examples_match_screen(key):
    """Each row: the legal program passes the REAL screen; the illegal one is rejected with the row's checker id, and
    that violation maps back to the row (a parent row: to one of its rewrite rows)."""
    row = {r.key: r for r in ep.RULES}[key]
    assert screen(row.legal) == []
    found = screen(row.illegal)
    lines = re.split(r'\r\n|\r|\n', row.illegal)
    mapped = {ep.rule_key_for(v['rule'], v['detail'], lines[v['line'] - 1].strip() if v['line'] else None)
              for v in found if v['rule'] == row.rule}
    assert mapped, found
    assert mapped & PARENTS.get(key, {key}), (key, mapped)
    assert 'before_call' in row.legal and 'before_call' in row.illegal      # every example defines a note hook


def test_import_row_names_the_banned_member_forms_the_real_screen_rejects():
    """fix-b, coord-1: the [import] row may not call a from-import allowed that the REAL screen rejects. Each
    from-import it names as rejected (from datetime import time, from pandas import read_csv, from numpy import
    random) is rejected with rule 'import' and maps back to the [import] row; the legal form its rewrite names
    (import datetime, then datetime.time) passes; a from-import of an allowed member still passes."""
    row = {r.key: r for r in ep.RULES}['import']
    assert ep.IMPORT_MEMBER_EXAMPLES == IMPORT_MEMBER_LINES
    for line in IMPORT_MEMBER_LINES:
        found = screen(program(top=[line]))
        assert [v['rule'] for v in found] == ['import'], (line, found)
        assert ep.rule_key_for('import', found[0]['detail'], line) == 'import'
        assert '"%s"' % line in row.sentence
    for top, body in ((['import datetime'], ['t = datetime.time(12, 0)']), (['from datetime import datetime'], ()),
                      (['from numpy.random import default_rng'], ['rng = default_rng(7)'])):
        assert screen(program(top=top, body=body)) == [], top
    assert screen(ep.IMPORT_MEMBER_LEGAL) == [] and 'import datetime, then datetime.time' in row.rewrite
    # every member the screen bans in a from-import is a name the [name] or [attribute] row bans, or a blocked module
    # name (random and time included), as the sentence says; one example of each kind is rejected
    for line in ('from re import compile', 'from json import load', 'from pandas import to_datetime',
                 'from collections import _sys'):
        assert [v['rule'] for v in screen(program(top=[line]))] == ['import'], line
    assert INSERTED.rstrip() in row.sentence and row.rewrite == IMPORT_DELTA['rewrite_new']


def test_verify_raises_when_the_screen_stops_rejecting_a_named_import_example(monkeypatch):
    """verify() runs the [import] row's named examples through the screen: if the bound screen no longer rejected
    one of them, the text would claim a rule the code does not have."""
    monkeypatch.setattr(policy, 'FORBIDDEN_MODULES', tuple(m for m in policy.FORBIDDEN_MODULES if m != 'time'))
    with pytest.raises(RuntimeError, match="does not reject 'from datetime import time'"):
        ep.verify()


def test_every_screen_rule_is_stated():
    assert {row.rule for row in ep.RULES} == set(policy.RULES)
    for key in KEYS:
        lines = screen_lines(ep.system(*key))
        assert lines[0] == ep.SCREEN_HEAD
        assert lines[1:] == [ep._screen_line(row) for row in ep.RULES]
        for row in ep.RULES:
            if row.parent is not None:
                assert 'Rewrite, %s: %s' % (row.label, row.rewrite) in lines
            elif row.rewrite is None:
                assert '[%s] %s' % (row.label, row.sentence) in lines
            else:
                assert '[%s] %s Rewrite: %s' % (row.label, row.sentence, row.rewrite) in lines
    labels = [row.label for row in ep.RULES if row.parent is None]
    assert labels[2:4] == ['module_level, statements', 'module_level, constant values']
    assert [label for label in labels if ',' not in label] == [row.key for row in ep.RULES
                                                               if row.parent is None and row.rule == row.key]


# ---- rendered from the bound modules -------------------------------------------------------------------------
def test_rendered_lists_are_the_bound_lists():
    ordinary = set(policy.ORDINARY_ATTRIBUTES)
    for key in KEYS:
        text = ep.system(*key)
        imported = line_of(text, '[import] ')
        assert 'Only these modules may be imported: %s. ' % ', '.join(policy.IMPORTABLE) in imported
        for module, members in policy.FROM_ONLY.items():
            assert '"from %s import %s"' % (module, ', '.join(members)) in imported
        assert ': %s. No name may start' % ', '.join(policy.FORBIDDEN_NAMES) in line_of(text, '[name] ')
        attribute = line_of(text, '[attribute] ')
        assert '(3) these names: %s;' % ', '.join(policy.FORBIDDEN_ATTRIBUTES) in attribute
        blocked = [name for name in policy.FORBIDDEN_MODULES if name not in ordinary]
        assert '(4) a name equal to a blocked module name: %s.' % ', '.join(blocked) in attribute
        assert not any(re.search(r'\b%s\b' % name, attribute.split('(4)')[1]) for name in ordinary)
        assert '"drawer 3"): %s.' % ', '.join(policy.RECEPTACLES) in line_of(text, '[receptacle_literal] ')
        assert 'at most {:,} bytes'.format(policy.source_limit(ep.POLICY_VERSION)) in line_of(text, '[size] ')
        assert 'at most {:,} characters'.format(policy.MAX_CONSTANT_CHARS) in line_of(text, '[constant_size] ')
        for name in policy.IMPORTABLE + policy.FORBIDDEN_NAMES + policy.FORBIDDEN_ATTRIBUTES + policy.RECEPTACLES:
            assert name in text
        returned = paragraphs(text)[2]
        assert returned.startswith('WHAT YOU RETURN. ' + replies.REPLY_FORMAT[key[1]] + '\n')
        if key[1] == 'propose':
            assert ('Propose at most %d programs' % MAX_PROGRAM_PROPOSALS) in returned
            assert ('the first %d that pass the static screen' % MAX_PROGRAM_CANDIDATES) in returned
            assert 'at most %d characters;' % profiles.MAX_DESCRIPTION_CHARS in returned
            assert 'at most %d characters, or ""' % profiles.MAX_HEADER_CHARS in returned
            cap = max(profiles.MAX_NOTE_CHARS.values())
            assert '1 to %d (left out or 0 means %d)' % (cap, cap) in returned
            if key[0] == 'alfworld':
                state = package.MAX_STATE_BYTES
                assert '1 to %d bytes of JSON (left out or 0 means %d)' % (state, state) in returned
        if key[0] == 'alfworld':
            assert ('limited to %d characters in all' % profiles.MAX_NOTE_CHARS['alfworld']) in paragraphs(text)[3]
    fields = importlib.import_module('skillopt.execskill.notes').FIELD_TYPES
    noted = paragraphs(ep.system('searchqa', 'propose'))[4]
    assert fields['facts']['max_chars'] == fields['warnings']['max_chars']     # one cap stated for both
    assert ('"facts" and "warnings": lists of strings, each at most %d characters; "candidates": list of strings, each '
            'at most %d characters; "table": list of rows, at most %d rows by %d columns, every cell a string of at '
            'most %d characters; "bindings": list of {"name", "quote", "value"}, each a string of at most %d '
            'characters.' % (fields['facts']['max_chars'], fields['candidates']['max_chars'],
                             fields['table']['max_rows'], fields['table']['max_columns'],
                             fields['table']['max_chars'], fields['bindings']['max_chars'])) in noted
    assert fields['bindings']['keys'] == ['name', 'quote', 'value']
    assert set(fields) == {'facts', 'warnings', 'candidates', 'table', 'bindings'}


def _with(sequence, extra):
    return tuple(sequence) + (extra,)


BOUND_CHANGES = [
    (policy, 'FORBIDDEN_NAMES', lambda v: _with(v, 'zzforbiddenname'), 'zzforbiddenname'),
    (policy, 'IMPORTABLE', lambda v: _with(v, 'zzmodule'), 'zzmodule'),
    (policy, 'FORBIDDEN_ATTRIBUTES', lambda v: _with(v, 'zzattribute'), 'zzattribute'),
    (policy, 'FORBIDDEN_MODULES', lambda v: _with(v, 'zzblocked'), 'zzblocked'),
    (policy, 'ORDINARY_ATTRIBUTES', lambda v: ('random',), 'subprocess, sys, sysconfig, tarfile, tempfile, threading, '
                                                             'time, traceback'),
    (policy, 'RECEPTACLES', lambda v: _with(v, 'zzreceptacle'), 'zzreceptacle'),
    (policy, 'FROM_ONLY', lambda v: {**v, 'zz.sub': ('zzmember',)}, '"from zz.sub import zzmember"'),
    (policy, 'MAX_CONSTANT_CHARS', lambda v: 2345, 'at most 2,345 characters'),
    (profiles, 'MAX_DESCRIPTION_CHARS', lambda v: 611, 'at most 611 characters'),
    (profiles, 'MAX_HEADER_CHARS', lambda v: 211, 'at most 211 characters'),
    (package, 'MAX_STATE_BYTES', lambda v: 4321, '1 to 4321 bytes of JSON'),
]


@pytest.mark.parametrize('module, name, change, expected', BOUND_CHANGES, ids=[c[1] for c in BOUND_CHANGES])
def test_a_changed_bound_value_changes_the_rendered_text_and_fails_verify(monkeypatch, module, name, change,
                                                                          expected):
    """The texts are rendered from the bound modules, never typed (DESIGN 3.2; DESIGN 5: the one case that patches a
    bound list, never run in the bound child process)."""
    stored = dict(ep._TEXTS)
    monkeypatch.setattr(module, name, change(getattr(module, name)))
    rendered = ep._render_all(ep._rules())
    assert any(expected in text for text in rendered.values())
    assert any(rendered[key] != stored[key] for key in KEYS)
    assert ep.system('alfworld', 'propose') == stored[('alfworld', 'propose')]        # the process's texts stay
    with pytest.raises(RuntimeError, match='engineer_prompt'):
        ep.verify()


def test_a_changed_reply_format_changes_the_text_and_fails_verify(monkeypatch):
    monkeypatch.setitem(replies.REPLY_FORMAT, 'fix', replies.REPLY_FORMAT['fix'] + ' Changed.')
    assert 'program. Put no program text inside the JSON. Changed.\n' in ep._render(
        'searchqa', 'fix', ep._rules())
    with pytest.raises(RuntimeError, match=r'\.fix text rendered now differs'):
        ep.verify()


def test_reply_format_embedded():
    """The first sentences of WHAT YOU RETURN are replies.REPLY_FORMAT[purpose], embedded by reference (reply.md)."""
    for bench, purpose in KEYS:
        text = ep.system(bench, purpose)
        assert ('WHAT YOU RETURN. ' + replies.REPLY_FORMAT[purpose] + '\n') in text
        assert text.count('WHAT YOU RETURN. ') == 1
    assert 'from . import replies' in Path(ep.__file__).read_text(encoding='utf-8')


# ---- the ten texts ----------------------------------------------------------------------------------------------
def test_all_ten_texts_render():
    heads = ('', 'WHAT YOU RECEIVE (user message, JSON). ', 'WHAT YOU RETURN. ', 'HOOKS. ', 'NOTES. ', 'CONTENT. ',
             'STATIC SCREEN. ')
    lengths = {}
    for bench, purpose in KEYS:
        text = ep.system(bench, purpose)
        lengths[(bench, purpose)] = len(text)
        assert text.endswith('\n') and not text.endswith('\n\n')
        assert text.isascii() and '\t' not in text and '\r' not in text
        assert not any(line != line.rstrip() or not line for line in text[:-1].split('\n') if line)
        parts = paragraphs(text)
        assert len(parts) == 7 and all(part.startswith(head) for part, head in zip(parts, heads))
        assert '\n\n\n' not in text
        assert text.count(bench) == 1 and ('on %s tasks' % bench) in parts[0]
        assert parts[0] == ep.INTRO[purpose] % bench and parts[1] == ep.RECEIVE[purpose]
        assert parts[5] == ep.CONTENT
        assert parts[5:] == paragraphs(ep.system('searchqa', 'propose'))[5:]      # CONTENT and STATIC SCREEN
        assert parts[3:5] == paragraphs(ep.system(bench, 'propose'))[3:5]          # HOOKS and NOTES per bench
        other = 'fix' if purpose == 'propose' else 'propose'
        assert parts[:3] != paragraphs(ep.system(bench, other))[:3]
    for purpose in ('propose', 'fix'):
        assert ep.system('officeqa', purpose) == ep.system('searchqa', purpose).replace('searchqa', 'officeqa')
    # DESIGN 3.2: 10,076 to 11,216 characters; typed-engineer-prompt-2 adds the 402 characters of IMPORT_DELTA (coord-1)
    delta = len(INSERTED) + len(IMPORT_DELTA['rewrite_new']) - len(IMPORT_DELTA['rewrite_old'])
    assert delta == 402
    assert min(lengths.values()) == lengths[('zebralogic', 'fix')] == 10076 + delta
    assert max(lengths.values()) == lengths[('alfworld', 'propose')] == 11216 + delta
    for bad in ((None, 'propose'), ('livemath', 'propose'), ('searchqa', 'repair'), ('searchqa', None),
                (['searchqa'], 'fix'), ('SearchQA', 'fix')):
        with pytest.raises(ValueError):
            ep.system(*bad)


def _design_blocks():
    if not DESIGN.exists():
        pytest.skip('the design document is not in this tree')
    text = DESIGN.read_text(encoding='utf-8')
    section = text[text.index('### 3.2 '):text.index('### 3.3 ')]
    blocks = re.findall(r'```text\n(.*?)```', section, re.S)
    assert len(blocks) == 3
    return blocks


def test_texts_are_the_design_wording():
    """system('searchqa', 'propose') is DESIGN 3.2's text word for word, except its [import] line, which is DESIGN's
    line with the coordinator's fix-b change coord-1 (``coord1``: one inserted sentence, the new rewrite); the fix
    purpose's first three paragraphs and the bench-dependent parts of zebralogic, spreadsheetbench and alfworld are
    DESIGN's too."""
    whole, parts, fix = _design_blocks()
    design_lines = whole.split('\n')
    (index,) = [i for i, line in enumerate(design_lines) if line.startswith('[import] ')]
    design_lines[index] = coord1(design_lines[index])
    assert ep.system('searchqa', 'propose') == '\n'.join(design_lines)
    assert ep.system('searchqa', 'propose') != whole and line_of(ep.system('searchqa', 'propose'), '[import] ') == (
        design_lines[index])
    for bench in ORDER:
        fixed = paragraphs(ep.system(bench, 'fix'))
        assert '\n\n'.join(fixed[:3]) + '\n' == fix.replace('searchqa', bench).replace(
            '"max_note_chars").', '"max_note_chars"%s).' % {'spreadsheetbench': ', "requests_second_call"',
                                                               'alfworld': ', "state_bytes"'}.get(bench, ''))
    found = re.findall(r'^\[(\w+)\] "none of" list: (.*?)\. Smallest returns: (.*?)\. '
                       r'(?:Added to the entry sentence: (.*?)\. )?Hook lines after "applies":\n((?:[^\[].*\n)+)',
                       parts, re.M)
    assert [row[0] for row in found] == ['zebralogic', 'spreadsheetbench', 'alfworld']
    for bench, none_of, smallest, added, hook_lines in found:
        text = ep.system(bench, 'propose')
        hooks = paragraphs(text)[3].split('\n')
        assert hooks[0].endswith('A program that defines none of %s can never write a note and is rejected.' % none_of)
        assert hooks[1] == ep.APPLIES_LINE
        assert hooks[2:] == hook_lines.rstrip('\n').split('\n')
        assert ('Smallest valid returns: %s. ' % smallest) in paragraphs(text)[4]
        entry = paragraphs(text)[2].split('\n')[1]
        assert entry.endswith('; %s.' % added if added else '(left out or 0 means 4000).')


def test_pins():
    assert ep.PINS == PINNED
    for key in KEYS:
        assert hashlib.sha256(ep.system(*key).encode('utf-8')).hexdigest() == PINNED[key]
    assert ep.verify() == {'version': 'typed-engineer-prompt-2',
                           'pins': {'%s.%s' % key: PINNED[key] for key in sorted(PINNED)}}


def test_verify_raises_on_a_one_character_edit(monkeypatch):
    key = ('zebralogic', 'fix')
    monkeypatch.setitem(ep._TEXTS, key, ep._TEXTS[key][:-2] + 'X\n')
    with pytest.raises(RuntimeError, match='zebralogic.fix'):
        ep.verify()


def test_verify_raises_on_a_changed_pin(monkeypatch):
    monkeypatch.setitem(ep.PINS, ('alfworld', 'propose'), '0' * 64)
    with pytest.raises(RuntimeError, match='alfworld.propose text differs from PINS'):
        ep.verify()


@pytest.mark.parametrize('breakage, message', [
    (lambda r: r._replace(legal=r.illegal) if r.key == 'clock' else r, 'legal example of row clock'),
    (lambda r: r._replace(illegal=r.legal) if r.key == 'sympify' else r, 'illegal example of row sympify'),
    (lambda r: r._replace(illegal=program(body=['rows = view.to_dict()'])) if r.key == 'attribute_type_name' else r,
     'does not map back to its row'),
    (lambda r: r._replace(rule='syntax') if r.key == 'receptacle_literal' else r, 'the rows state'),
])
def test_verify_runs_the_examples_through_the_screen(monkeypatch, breakage, message):
    broken = tuple(breakage(row) for row in ep.RULES)
    monkeypatch.setattr(ep, '_rules', lambda: broken)
    monkeypatch.setattr(ep, 'RULES', broken)
    with pytest.raises(RuntimeError, match=message):
        ep.verify()


# ---- hooks, views, stale text -------------------------------------------------------------------------------
def test_hook_signatures():
    named = {'searchqa': {'applies', 'before_call', 'bindings'}, 'officeqa': {'applies', 'before_call', 'bindings'},
             'zebralogic': {'applies', 'before_call'},
             'spreadsheetbench': {'applies', 'before_call', 'sheet_feedback'},
             'alfworld': {'applies', 'alf_before_step', 'alf_after_step'}}
    assert tuple(ep.NOTE_HOOKS_BY_BENCH) == ORDER
    for bench, hooks in ep.NOTE_HOOKS_BY_BENCH.items():
        assert set(hooks) <= set(package.NOTE_HOOKS)
        for purpose in ('propose', 'fix'):
            lines = paragraphs(ep.system(bench, purpose))[3].split('\n')
            signatures = [re.match(r'(\w+)\(([^)]*)\) -> ', line) for line in lines[1:]]
            found = {m.group(1): len(m.group(2).split(', ')) for m in signatures if m}
            assert set(found) == named[bench]
            assert all(name in protocol.HOOKS and count == package.HOOK_PARAMETERS[name]
                       for name, count in found.items()), found
            assert lines[0].endswith('defines none of %s can never write a note and is rejected.' % ', '.join(hooks))
    assert protocol.HOOKS == profiles.HOOKS


def test_hook_views_named_in_the_text_are_the_frozen_views():
    backends = importlib.import_module('skillopt.continual_eval.backends')
    solver = importlib.import_module('skillopt.execskill.solver')
    zebralogic = importlib.import_module('skillopt.execskill.zebralogic')
    for bench in ('searchqa', 'officeqa'):
        assert backends._PUBLIC[bench] == ('question', 'context')
        assert 'view = {"question", "context"}' in ep.system(bench, 'propose')
    assert list(zebralogic.public_view({'question': 'q', 'columns': ['Name']})) == ['question', 'columns']
    assert 'view = {"question", "columns"}' in ep.system('zebralogic', 'propose')
    assert 'run_report = {%s}' % ', '.join('"%s"' % k for k in solver.REPORT_KEYS) in ep.system('spreadsheetbench',
                                                                                                'fix')
    assert ('applies reads view = {%s}' % ', '.join('"%s"' % k for k in protocol.ALFWORLD_ROUTING_VIEW)
            in ep.system('alfworld', 'fix'))
    source = inspect.getsource(solver)
    for keys in (('"initial_observation"', '"observation"', '"admissible_commands"', '"recent_history"'),
                 ('"step"', '"action"', '"observation"', '"admissible_commands"')):
        assert all(key in source for key in keys)
        assert '{%s}' % ', '.join(keys) in ep.system('alfworld', 'propose')


def test_no_stale_route_b_text():
    for key in KEYS:
        text = ep.system(*key)
        for stale in ('J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7', 'replay', 'claims_fix', 'main-v', 'zebra-pc',
                      'excluded_benches', 'revision', 'deletion', 'narrowing', 'adopt', 'confirmation', 'livemath'):
            assert stale not in text, (key, stale)


def test_limits_agree_with_the_reader():
    assert MAX_PROGRAM_PROPOSALS == profiles.MAX_CHANGES == 3      # the reader reads at most 3 changes
    assert MAX_PROGRAM_CANDIDATES == 2


# ---- the words are held to the code ----------------------------------------------------------------------------
def rejected(text, rule):
    return any(v['rule'] == rule for v in screen(text))


def test_words_of_the_rules_are_held_by_the_screen():
    """The rules stated in words (forms, prefixes, phrases, patterns, the constant grammar) agree with the screen."""
    # [module_level, statements]: allowed forms pass, each named form is rejected
    assert screen('"""Doc."""\nimport re\nLIMIT = 3\n' + program()) == []
    for line in ('A, B = 1, 2', 'A: int = 1', 'A = 1\nA += 1', 'len("x")', 'if True: pass', 'for i in []: pass',
                 'while False: pass', 'try:\n    pass\nexcept ValueError:\n    pass', 'with open: pass',
                 'class Box: pass', 'A = B = 1', 'X = 1\n"""late docstring"""'):
        assert rejected(line + '\n' + program(), 'module_level'), line
    # [module_level, constant values]: forms (a) to (d) pass after a plain import re; the named others are rejected
    for line in ('A = (1, "x", b"y", True, False, None, [1, {2: {3}}])', 'A = 1\nB = A', 'A = "ab" + "cd"',
                 'A = [1, 2] + [3]', 'A = set([1])', 'A = frozenset("ab")', 'A = tuple([1])', 'A = list((1,))',
                 'A = dict([("a", 1)])', 'A = sorted([2, 1])', 'A = "a b c".split()', 'A = "a,b".split(",")',
                 'A = ", ".join(["a", "b"])', 'A = re.compile("p")', 'A = re.compile("p", re.I | re.M)'):
        assert screen('import re\n' + line + '\n' + program()) == [], line
    for line in ('A = frozenset("a b".split())', 'A = f"{1}"', 'A = [x for x in (1, 2)]', 'A = lambda: 1',
                 'A = 2 * 3', 'A = "%d" % 3', 'A = "{}".format(1)', 'A = len("x")', 'B = 1\nA = B + 1',
                 'B = "x"\nA = [B]', 'UNIT = "kg"\nA = re.compile("p" + UNIT)'):
        assert rejected('import re\n' + line + '\n' + program(), 'module_level'), line
    assert rejected('import re as regex\nA = regex.compile("p")\n' + program(), 'module_level')
    # [statement], [decorator]
    for line in ('class Box: pass', 'def f():\n    global X', 'def f():\n    x = 1\n    def g():\n        nonlocal x',
                 'async def f(): pass', 'async def f():\n    await g()'):
        assert rejected(line + '\n' + program(), 'statement'), line
    assert rejected('import functools\n@functools.cache\ndef f(x): return x\n' + program(), 'decorator')
    # [import]: the listed forms pass, the named modules and forms are rejected
    for line in ('import numpy', 'import numpy as np', 'from collections import Counter',
                 'from numpy.random import default_rng', 'import openpyxl.utils',
                 'from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, '
                 'get_column_letter, range_boundaries'):
        assert screen(line + '\n' + program()) == [], line
    for module in ('typing', 'dataclasses', 'os', 'sys', 'io', 'time', 'random', 'pathlib'):
        assert rejected('import %s\n' % module + program(), 'import'), module
    for line in ('from math import *', 'import numpy.linalg', 'from numpy.random import rand', 'from . import x'):
        assert rejected(line + '\n' + program(), 'import'), line
    # [name]: every listed name and a double-underscore name, in each named position
    for name in policy.FORBIDDEN_NAMES:
        assert rejected(program(body=['x = %s' % name]), 'name'), name
    for line in ('def id(x): return x', 'def f(hash): return hash', 'import json as eval', '__x = 1'):
        assert rejected(program(top=[line]) if '__x' not in line else program(body=[line]), 'name'), line
    # [attribute]: the two prefixes, the listed names, the blocked module names; the ordinary module names pass
    for attribute in ('_cache', '__dict__', 'read_csv', 'to_numeric') + policy.FORBIDDEN_ATTRIBUTES:
        assert rejected(program(body=['x = view.%s' % attribute]), 'attribute'), attribute
    for module in policy.FORBIDDEN_MODULES:
        found = rejected(program(body=['x = view.%s' % module]), 'attribute')
        assert found == (module not in policy.ORDINARY_ATTRIBUTES), module
    assert screen(program(top=['import datetime'], body=['t = datetime.time(1, 2)'])) == []
    # [numpy_random]
    assert screen(program(top=['import numpy'], body=['rng = numpy.random.default_rng(7)'])) == []
    for line in ('rng = numpy.random.default_rng()', 'rng = numpy.random.default_rng(None)', 'x = numpy.random.rand()',
                 'rng = numpy.random.default_rng(seed=7)'):
        assert rejected(program(top=['import numpy'], body=[line]), 'numpy_random'), line
    # [clock]: the three calls with either text; .now / .today / .utcnow after a dot
    for call in ('Timestamp', 'Period', 'datetime64'):
        for word in ('now', 'today', ' Now '):
            assert rejected(program(top=['import pandas'], body=['t = pandas.%s("%s")' % (call, word)]), 'clock')
    for attribute in ('now', 'today', 'utcnow'):
        assert rejected(program(top=['import datetime'], body=['t = datetime.datetime.%s()' % attribute]),
                        'attribute')
    # [sympify]
    assert rejected(program(top=['import sympy'], body=['e = sympy.S("x")']), 'sympify')
    for attribute in ('sympify', 'parse_expr', 'lambdify'):
        assert rejected(program(top=['import sympy'], body=['e = sympy.%s' % attribute]), 'attribute')
    # [dunder_string], [meta_option]: both phrases and every four consecutive words of the stated sentence
    assert rejected(program(body=['k = "x __init__ y"']), 'dunder_string')
    sentence = 'one of the remaining options is correct but a stronger result can be proven'
    assert ' '.join(re.findall(r'[a-z0-9]+', policy.STRONGER_OPTION.casefold())) == sentence
    words = sentence.split()
    assert policy.META_SHINGLE_WORDS == 4 and policy.META_PHRASES == ('stronger result', 'stronger statement')
    for phrase in list(policy.META_PHRASES) + [' '.join(words[i:i + 4]) for i in range(len(words) - 3)]:
        assert rejected(program(top=['# ' + phrase.upper()]), 'meta_option'), phrase
    assert screen(program(top=['# of the remaining'])) == []           # three words pass
    assert rejected(program(top=['# of the remaining', '# options']), 'meta_option')   # the words span lines
    # [bulletin_literal], [receptacle_literal]: in any string literal, docstrings included, on every bench
    for literal in ('page 12', 'pp. 3', 'March 1985', 'may 1999', 'Sept. 2001', 'treasury bulletin 3',
                    'Treasury_Bulletin_1985'):
        assert rejected(program(body=['s = "%s"' % literal]), 'bulletin_literal'), literal
        assert rejected('"""%s"""\n' % literal + program(), 'bulletin_literal'), literal
    for literal in ('March 1799', 'page', 'pages of text', r'page\s*(\d+)'):
        assert screen(program(body=['s = r"%s"' % literal])) == [], literal
    for receptacle in policy.RECEPTACLES:
        assert rejected(program(body=['s = "go to %s 12"' % receptacle]), 'receptacle_literal'), receptacle
    assert screen(program(body=['s = "the drawer"'])) == []


# ---- rule_key_for -----------------------------------------------------------------------------------------------
F6_WORD_SET = ('UNITS = frozenset("million billion thousand percent dollars".split())\n\n\n'
               'def before_call(view, state):\n'
               '    found = [w for w in view.get("question", "").lower().split() if w in UNITS]\n'
               '    return {"facts": ["unit words: " + ", ".join(found)]} if found else {}\n')
F6_REGEX = ('import re\n\nNUMBER = r"(\\d+(?:\\.\\d+)?)"\nMONEY = re.compile(r"\\$\\s*" + NUMBER)\n\n\n'
            'def before_call(view, state):\n'
            '    amounts = MONEY.findall(view.get("context", ""))\n'
            '    return {"facts": ["amounts: " + ", ".join(amounts[:5])]} if amounts else {}\n')
F6_TYPE_NAME = ('def before_call(view, state):\n'
                '    try:\n'
                '        value = float(view.get("question", ""))\n'
                '    except Exception as error:\n'
                '        return {"warnings": ["not a number: " + type(error).__name__]}\n'
                '    return {"facts": ["value %s" % value]}\n')


def test_rule_key_for():
    """The three F6 shapes (word set, regex constant, exception type name) get their rewrite rows; the other ids
    their rows; never a parent row."""
    for source, key in ((F6_WORD_SET, 'constant_word_set'), (F6_REGEX, 'constant_regex'),
                        (F6_TYPE_NAME, 'attribute_type_name')):
        evidence = ep.screen_evidence({'check': 'policy'}, source, 'searchqa')
        assert [row['key'] for row in ep.evidence_record(evidence)['rows']] == [key]
    assert ep.rule_key_for('module_level', ep.CONSTANT_DETAIL, 'W = set("a b".split())') == 'constant_word_set'
    assert ep.rule_key_for('module_level', ep.CONSTANT_DETAIL, 'W = sorted("a b".split())') == 'constant_other'
    assert ep.rule_key_for('module_level', ep.CONSTANT_DETAIL, 'P = re.compile(A + "x")') == 'constant_regex'
    assert ep.rule_key_for('module_level', ep.CONSTANT_DETAIL, None) == 'constant_other'
    for detail in ('If', 'Expr', 'AugAssign', 'AnnAssign', 'ClassDef', 'Assign'):
        assert ep.rule_key_for('module_level', detail, 'W = frozenset("a".split())') == 'top_level'
    for detail in ep.TYPE_NAME_ATTRIBUTES:
        assert ep.rule_key_for('attribute', detail, None) == 'attribute_type_name'
    for detail in ('__dict__', '_cache', 'to_dict', 'now', 'os'):
        assert ep.rule_key_for('attribute', detail, None) == 'attribute_data'
    for rule in policy.RULES:
        if rule not in ('module_level', 'attribute'):
            assert ep.rule_key_for(rule, 'x', 'x') == rule
    keys = {ep.rule_key_for(rule, detail, line) for rule in policy.RULES
            for detail in (ep.CONSTANT_DETAIL, '__name__', 'x') for line in ('a.split( set(', '.compile(', '', None)}
    assert keys == set(ROW_KEYS) - set(PARENTS)
    for rule in ('card_template', 'no_hook_function', None, ''):
        with pytest.raises(ValueError):
            ep.rule_key_for(rule, 'x', 'x')


# ---- screen_evidence ----------------------------------------------------------------------------------------
TEN = ('import os\n'                                          # 1 import
       'WORDS = frozenset("alpha beta".split())\n'            # 2 module_level (constant)
       'def before_call(view, state):\n'
       '    kind = type(view).__name__\n'                      # 4 attribute __name__
       '    rows = view.to_dict()\n'                           # 5 attribute to_dict
       '    found = hasattr(view, "question")\n'               # 6 name hasattr
       '    s = "open drawer 3"\n'                             # 7 receptacle_literal
       '    t = "see page 12"\n'                               # 8 bulletin_literal
       '    k = "__main__"\n'                                  # 9 dunder_string
       '    print(kind)\n'                                     # 10 name print
       '    return {"facts": [eval("1")]}\n')                  # 11 name eval


def test_screen_evidence_shows_eight_rows_in_checker_order_and_counts_the_rest():
    found = screen(TEN)
    assert len(found) == 10
    evidence = ep.screen_evidence({'check': 'policy', 'detail': found[:5], 'repairs': []}, TEN, 'officeqa')
    assert set(evidence) == {'check', 'detail', 'more'} and evidence['check'] == 'policy'
    assert evidence['more'] == 2 and len(evidence['detail']) == ep.EVIDENCE_ROWS
    assert [(r['rule'], r['line'], r['detail']) for r in evidence['detail']] == [
        (v['rule'], v['line'], v['detail']) for v in found[:8]]
    lines = TEN.split('\n')
    text = ep.system('officeqa', 'fix')
    for row in evidence['detail']:
        assert set(row) == {'rule', 'line', 'detail', 'source_line', 'rule_text', 'rewrite'}
        assert row['source_line'] == lines[row['line'] - 1].strip()
        assert row['rule_text'] in text and row['rewrite'] in text
    record = ep.evidence_record(evidence)
    assert [row['key'] for row in record['rows']] == ['import', 'constant_word_set', 'attribute_type_name',
                                                      'attribute_data', 'name', 'receptacle_literal',
                                                      'bulletin_literal', 'dunder_string']
    assert record['more'] == 2 and all(set(row) == {'rule', 'key', 'line', 'detail', 'source_line'}
                                       for row in record['rows'])
    by_key = {row.key: row for row in ep.RULES}
    second = evidence['detail'][1]
    assert second['rule_text'] == by_key['constant_value'].sentence           # the parent's sentence
    assert second['rewrite'] == by_key['constant_word_set'].rewrite           # the rewrite row's rewrite


def test_screen_evidence_calls_the_frozen_screen_as_the_typed_code_does(monkeypatch):
    calls = []
    real = policy.check

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(policy, 'check', spy)
    ep.screen_evidence({'check': 'policy'}, TEN, 'alfworld')
    assert calls == [((TEN,), {'version': ep.POLICY_VERSION})]


def test_screen_evidence_line_zero_and_long_lines():
    big = program(top=['# ' + 'x' * policy.source_limit(ep.POLICY_VERSION)])
    evidence = ep.screen_evidence({'check': 'policy'}, big, 'searchqa')
    assert [(r['rule'], r['line'], r['source_line']) for r in evidence['detail']] == [('size', 0, None)]
    meta = program(top=['# a stronger result can be proven'])
    rows = ep.screen_evidence({'check': 'policy'}, meta, 'zebralogic')['detail']
    assert {r['rule'] for r in rows} == {'meta_option'} and all(r['line'] == 0 and r['source_line'] is None
                                                                  for r in rows)
    words = ' '.join('word%d' % i for i in range(60))                     # a long word set: .split( after column 240
    source = program(top=['WORDS = frozenset("%s".split())' % words])
    evidence = ep.screen_evidence({'check': 'policy'}, source, 'searchqa')
    row = evidence['detail'][0]
    assert len(row['source_line']) == ep.SOURCE_LINE_CHARS and '.split(' not in row['source_line']
    assert ep.evidence_record(evidence)['rows'][0]['key'] == 'constant_word_set'
    crlf = 'X = 1\r\nclass Box: pass\r\n' + program()
    rows = ep.screen_evidence({'check': 'policy'}, crlf, 'searchqa')['detail']
    assert {(r['line'], r['source_line']) for r in rows} == {(2, 'class Box: pass')}
    broken = program(body=['return {"facts": [}'])
    rows = ep.screen_evidence({'check': 'policy'}, broken, 'searchqa')['detail']
    assert [(r['rule'], r['source_line']) for r in rows] == [('syntax', 'return {"facts": [}')]


def test_screen_evidence_of_the_other_checks():
    hooks = {'check': 'hooks', 'detail': [{'rule': 'no_hook_function', 'line': 0, 'detail': 'defined: applies'}],
             'repairs': []}
    for bench in ORDER:
        evidence = ep.screen_evidence(hooks, 'def applies(view):\n    return True\n', bench)
        assert evidence['check'] == 'hooks' and evidence['more'] == 0 and len(evidence['detail']) == 1
        row = evidence['detail'][0]
        assert row['rule'] == 'no_hook_function' and row['line'] == 0 and row['source_line'] is None
        assert row['detail'] == 'defined: applies'
        assert row['rule_text'] in ep.system(bench, 'fix')                  # the HOOKS sentence, word for word
        assert ', '.join(ep.NOTE_HOOKS_BY_BENCH[bench]) in row['rewrite']
        assert ep.evidence_record(evidence) == {'rows': [{'rule': 'no_hook_function', 'key': 'hooks', 'line': 0,
                                                          'detail': 'defined: applies', 'source_line': None}],
                                                'more': 0}
    structure = ep.screen_evidence({'check': 'structure', 'detail': 'A description is 1-600 characters',
                                    'repairs': []}, program(), 'searchqa')
    assert [(r['rule'], r['detail'], r['line']) for r in structure['detail']] == [
        ('structure', 'A description is 1-600 characters', 0)]
    source = ep.screen_evidence({'check': 'source', 'detail': 'no procedure source block'}, None, 'alfworld')
    assert [(r['rule'], r['detail']) for r in source['detail']] == [('source', 'no procedure source block')]
    assert ep.screen_evidence({'check': 'structure', 'detail': {'odd': 1}}, '', 'searchqa')['detail'][0]['detail'] == ''
    stale = ep.screen_evidence({'check': 'policy'}, TEN, 'searchqa')
    stale['detail'][0] = dict(stale['detail'][0], rewrite='an older wording')
    with pytest.raises(ValueError):
        ep.evidence_record(stale)


def test_check_words_are_the_reviewed_wording():
    """The words of the three non-policy checks enter the fix request (not the ten pinned texts): pinned here word
    for word, so a change is a visible, versioned change."""
    assert ep.CHECK_WORDS == {
        'hooks': {'rule': 'no_hook_function',
                  'rule_text': 'A program that defines none of %s can never write a note and is rejected.',
                  'rewrite': ('define at least one of %s as a top-level function with exactly the parameters given '
                              'under HOOKS; where it has nothing reliable to say it returns the smallest valid value '
                              'given under NOTES.')},
        'structure': {'rule': 'structure',
                      'rule_text': 'The entry and the hooks must fit together; detail names the requirement that '
                                   'failed.',
                      'rewrite': ('change the entry or the program so that this requirement holds; keep the entry '
                                  'fields in their stated forms.')},
        'source': {'rule': 'source', 'rule_text': 'A program text must be found in the reply.',
                   'rewrite': 'give the complete program in one fenced python block after the JSON block.'},
    }
    assert ep.CHECK_WORDS['hooks']['rule_text'] == ep.NO_HOOK_SENTENCE


def test_screen_evidence_refuses_caller_mistakes():
    for failed, source, bench in (({'check': 'policy'}, TEN, 'livemath'), ({'check': 'policy'}, TEN, None),
                                  ({'check': 'smoke'}, TEN, 'searchqa'), (None, TEN, 'searchqa'),
                                  ('policy', TEN, 'searchqa'), ({'check': 'policy'}, program(), 'searchqa'),
                                  ({'check': 'policy'}, None, 'searchqa')):
        with pytest.raises(ValueError):
            ep.screen_evidence(failed, source, bench)


# ---- module boundaries ------------------------------------------------------------------------------------------
def test_machinery_symbols_resolve_and_the_module_imports_only_them():
    for module, names in ep.MACHINERY_SYMBOLS.items():
        loaded = importlib.import_module(module)
        assert all(hasattr(loaded, name) for name in names), module
    tree = ast.parse(Path(ep.__file__).read_text(encoding='utf-8'))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported |= {(node.level, node.module, alias.name) for alias in node.names}
        elif isinstance(node, ast.Import):
            imported |= {(0, None, alias.name) for alias in node.names}
    frozen = {name for level, module, name in imported if module == 'skillopt.execskill'}
    assert frozen == {'notes', 'package', 'policy', 'profiles'}
    assert {name for level, module, name in imported if level == 1} == {
        'MACHINERY', 'MAX_PROGRAM_CANDIDATES', 'MAX_PROGRAM_PROPOSALS', 'ORDER', 'replies'}
    assert 'writers' not in {name for _, _, name in imported}
    used = {(node.value.id, node.attr) for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id in ('notes', 'package', 'policy', 'profiles')}
    declared = {(module.rsplit('.', 1)[1], name) for module, names in ep.MACHINERY_SYMBOLS.items() for name in names}
    assert used == declared
