"""Addendum I2: only complete child inline fences unwrap; historical parsing is frozen."""
import re

import pytest

from skillopt.execskill import engineer_reader as reader, profiles as p
from tests.test_execskill_v24_engineer import GOOD
from tests.test_execskill_v292_reader import REPLIES, ctx, reply


CHILDREN = (p.ZEBRA_PC_V9, p.ALFWORLD_V6)


def inline(program, field='source', configuration=p.ZEBRA_PC_V9):
    row = reader.read(reply([{'kind': 'new', field: program}]), ctx(configuration))[0]
    return row, {repair['rule'] for repair in row['repairs']}


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('delimiter', ('`', '~'))
@pytest.mark.parametrize('opened,closed,unfenced', ((4, 3, False), (3, 4, True)))
def test_complete_opening_run_cannot_backtrack_into_info_string(configuration, field, delimiter,
                                                               opened, closed, unfenced):
    program = ' \n' + delimiter * opened + 'python\n' + GOOD + delimiter * closed + '\n '
    row, rules = inline(program, field, configuration)
    assert row['source'] == (GOOD if unfenced else program)
    assert ('inline_source_unfenced' in rules) is unfenced
    assert ('inline_code_alias' in rules) is (field == 'code')
    assert row['original'][field] == program


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('info', ('py`thon', '`python', 'python`', ' python `example`'))
def test_backtick_info_with_any_backtick_stays_untouched(field, info):
    program = '```' + info + '\n' + GOOD + '```'
    row, rules = inline(program, field)
    assert row['source'] == program and 'inline_source_unfenced' not in rules


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('info', ('python`example`', '`python', 'py~thon'))
def test_tilde_info_can_contain_backticks_or_later_tildes(field, info):
    program = '~~~' + info + '\n' + GOOD + '~~~'
    row, rules = inline(program, field)
    assert row['source'] == GOOD and 'inline_source_unfenced' in rules


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('delimiter', ('`', '~'))
@pytest.mark.parametrize('inner_kind', ('shorter_same', 'other_character'))
def test_nested_inner_fences_remain_literal_under_a_complete_outer_fence(field, delimiter, inner_kind):
    inner = (delimiter if inner_kind == 'shorter_same' else '~' if delimiter == '`' else '`') * 3
    body = ('def before_call(view, state):\n    """A literal fenced example.\n' + inner +
            'python\nexample\n' + inner + '\n    """\n    return {}\n')
    program = delimiter * 4 + 'python\n' + body + delimiter * 4
    row, rules = inline(program, field)
    assert row['source'] == body and 'inline_source_unfenced' in rules
    assert reader.defined_hooks(row['source']) == ['before_call']


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('delimiter', ('`', '~'))
def test_same_length_inner_close_with_trailing_material_is_not_one_complete_block(field, delimiter):
    fence = delimiter * 4
    program = fence + 'python\n' + GOOD + fence + '\ntrailing program\n' + fence
    row, rules = inline(program, field)
    assert row['source'] == program and 'inline_source_unfenced' not in rules


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('delimiter', ('`', '~'))
def test_multiple_inline_blocks_are_not_unfenced_when_closers_are_longer(field, delimiter):
    block = delimiter * 3 + 'python\n' + GOOD + delimiter * 4
    program = block + '\n' + block
    row, rules = inline(program, field)
    assert row['source'] == program and 'inline_source_unfenced' not in rules


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('delimiter', ('`', '~'))
def test_a_different_closing_character_never_completes_the_inline_block(field, delimiter):
    other = '~' if delimiter == '`' else '`'
    program = delimiter * 3 + 'python\n' + GOOD + other * 4
    row, rules = inline(program, field)
    assert row['source'] == program and 'inline_source_unfenced' not in rules


@pytest.mark.parametrize('field', ('source', 'code'))
@pytest.mark.parametrize('delimiter', ('`', '~'))
@pytest.mark.parametrize('premature_close', (False, True))
def test_crlf_fences_keep_body_bytes_and_do_not_hide_an_earlier_close(field, delimiter, premature_close):
    body = GOOD.replace('\n', '\r\n')
    program = delimiter * 3 + 'python\r\n' + body + delimiter * 4
    if premature_close:
        program += '\r\ntrailing program\r\n' + delimiter * 4
    program += '\r\n'
    row, rules = inline(program, field)
    assert row['source'] == (program if premature_close else body)
    assert ('inline_source_unfenced' in rules) is (not premature_close)


@pytest.mark.parametrize('label', ('propose', 'format-retry/propose/1', 'format-retry/propose/2'))
def test_real_engineer_replies_keep_exact_program_bytes(label):
    text = REPLIES[label]
    rows = reader.read(text, ctx())
    if label == 'propose':
        expected = [reader.FENCE.fullmatch(row['original']['code'].strip()).group(3) for row in rows]
        assert all('inline_source_unfenced' in {repair['rule'] for repair in row['repairs']} for row in rows)
    else:
        expected = [match.group(3) for match in reader.FENCE.finditer(text)
                    if match.group(2).strip().lower() == 'python']
    assert len(rows) == len(expected) == 2
    assert [row['source'] for row in rows] == expected
    assert all(row['error'] is None for row in rows)


@pytest.mark.parametrize('configuration', (p.ZEBRA_PC_V7, p.ALFWORLD_V4, p.ZEBRA_PC_V8, p.ALFWORLD_V5))
@pytest.mark.parametrize('field', ('source', 'code'))
def test_parent_inline_program_behavior_remains_unchanged(configuration, field):
    program = '````python\n' + GOOD + '```'
    row, rules = inline(program, field, configuration)
    if field == 'source':
        assert row['source'] == program
    else:
        assert row['source'] is None and row['error'] == 'no procedure source block'
    assert not {'inline_code_alias', 'inline_source_unfenced'} & rules
    assert 'original' not in row


def test_reply_level_fence_expression_and_historical_backtracking_are_unchanged():
    pattern = r"^[ \t]*(`{3,}|~{3,})([^\n]*)\n(.*?)^[ \t]*\1[ \t]*$"
    assert reader.FENCE.pattern == pattern and reader.FENCE.flags == re.compile(pattern, re.M | re.S).flags
    # The fix belongs only to child inline source handling, not this historical parser.
    found = reader.FENCE.fullmatch('````python\n' + GOOD + '```')
    assert found.group(1) == '```' and found.group(2) == '`python'
    assert found.group(3) == GOOD
