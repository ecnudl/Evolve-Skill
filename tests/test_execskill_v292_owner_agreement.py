"""I1 ownership proofs: hook priority and exhaustive small/oversized agreement.

The exhaustive alphabet is two hooks: absent, A, B and overlapping A+B.
Blocks include every hook multiset of size0..3 and every labeled permutation,
plus every permutation of a four-block witness covering all hook sets.
Entries include every declared-hook vector and required/inherited-source mask
of size1..3. Each selected inherited entry is also checked with fix inheritance.
Actual hook parsing is cached, not replaced by invented scores.
"""
from functools import lru_cache
from itertools import combinations_with_replacement, permutations, product
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer_reader as reader, profiles as p
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v292_reader import ctx


HOOKS = ('before_call', 'bindings')
HOOK_SETS = ((), (HOOKS[0],), (HOOKS[1],), HOOKS)
AMBIGUOUS = 'ambiguous procedure source blocks; ownership is not unique'
INHERITED = 'def before_call(view, state):\n    return {}\n'


def source(hooks, marker):
    return '# authored block %s\n' % marker + ''.join(
        'def %s(view, state):\n    return {}\n' % hook for hook in hooks)


def blocks_for(hook_sets):
    return tuple((index + 1, 'python', source(hooks, index)) for index, hooks in enumerate(hook_sets))


def padded(entries, count):
    return entries + [{'kind': 'new', 'source': INHERITED, 'id': 'inline-%d' % n} for n in range(count)]


@pytest.mark.parametrize('configuration', (p.ZEBRA_PC_V9, p.ALFWORLD_V6))
def test_review_reversed_python_blocks_keep_hook_owner_after_two_inline_siblings(configuration):
    """The exact review trigger: 2 entries + reversed blocks becomes 4 entries."""
    entries = [{'kind': 'new', 'id': 'wanted', 'hooks': ['before_call']},
               {'kind': 'new', 'id': 'sibling', 'hooks': ['bindings']}]
    wanted = source(('before_call',), 'wanted')
    sibling = source(('bindings',), 'sibling')
    current = ctx(configuration)
    selection = {'change_id': 'wanted', 'change_index': 1, 'change_count': 2}
    small = reader.read(engineer_reply({'changes': entries}, [sibling, wanted]), current,
                        selection=dict(selection))[0]
    large = reader.read(engineer_reply({'changes': padded(entries, 2)}, [sibling, wanted]), current,
                        selection=dict(selection))[0]
    assert small['error'] is large['error'] is None
    assert small['source'].strip() == large['source'].strip() == wanted.strip()
    assert large['source'].strip() != sibling.strip()


def test_identical_declared_before_call_hooks_keep_positional_tie_break():
    entries = [{'kind': 'new', 'id': str(n), 'hooks': ['before_call']} for n in range(2)]
    blocks = blocks_for((('before_call',), ('before_call',)))
    assert reader._large_retry_source_owner(padded(entries, 2), blocks, 1, ctx(), None) == {1: blocks[1]}


def test_every_positional_candidate_needs_maximal_hook_score_not_only_selected():
    entries = [{'kind': 'new', 'hooks': ['before_call']},
               {'kind': 'new', 'hooks': ['bindings']},
               {'kind': 'new', 'hooks': ['bindings']}]
    blocks = blocks_for((HOOKS, ('before_call',), ('bindings',)))
    # The selected entry's first block is individually maximal; the second
    # entry's positional block is not. Matching all3 assigns the middle block.
    assert reader._source_owners(entries, blocks, ctx(), None, selected=0) == {0: blocks[1]}
    with pytest.raises(reader.Unusable, match=AMBIGUOUS):
        reader._large_retry_source_owner(padded(entries, 1), blocks, 0, ctx(), None)


def test_unique_hook_winner_still_rejects_competing_source_needing_sibling():
    entries = [{'kind': 'new', 'hooks': ['before_call']} for _ in range(2)]
    blocks = blocks_for((('before_call',),))
    with pytest.raises(reader.Unusable, match=AMBIGUOUS):
        reader._large_retry_source_owner(padded(entries, 2), blocks, 0, ctx(), None)


def test_oversized_hook_work_stays_linear_and_never_calls_small_matcher(monkeypatch):
    n = 200
    entries = [{'kind': 'new', 'id': str(index), 'hooks': ['before_call']} for index in range(n)]
    blocks = blocks_for([('before_call',)] * n)
    original, calls = reader.defined_hooks, []
    def counted(text):
        calls.append(None)
        return original(text)
    monkeypatch.setattr(reader, 'defined_hooks', counted)
    monkeypatch.setattr(reader, '_source_owners', lambda *args, **kwargs: pytest.fail('exponential matcher called'))
    actual = reader._large_retry_source_owner(entries, blocks, 151, ctx(), None)
    assert actual == {151: blocks[151]}
    assert 0 < len(calls) <= n + 1


def _check_agreement(count, block_cases, monkeypatch):
    original = reader.defined_hooks
    monkeypatch.setattr(reader, 'defined_hooks', lru_cache(maxsize=None)(original))
    attempts = unique = refusals = matched = 0
    for declared in product(HOOK_SETS, repeat=count):
        base = [{'kind': 'new', 'id': 'entry-%d' % index,
                 **({'hooks': list(hooks)} if hooks else {})} for index, hooks in enumerate(declared)]
        for inherited in product((False, True), repeat=count):
            for selected in range(count):
                for selected_fix in ((False, True) if inherited[selected] else (False,)):
                    parents = {'entry-%d' % index: SimpleNamespace(source=INHERITED)
                               for index, present in enumerate(inherited)
                               if present and not (selected_fix and index == selected)}
                    current = SimpleNamespace(parent=SimpleNamespace(order=tuple(parents), get=parents.get))
                    fixing = (SimpleNamespace(kind='new', entry=base[selected], source=INHERITED)
                              if selected_fix else None)
                    minimal = padded(base, p.MAX_CHANGES + 1 - count)
                    larger = padded(base, p.MAX_CHANGES + 8 - count)
                    # Insert inline entries before and between source-needing entries;
                    # keep the rest after them. Source candidate order stays the same.
                    interleaved = []
                    for index, item in enumerate(base):
                        interleaved.extend((larger[count + index], item))
                    interleaved.extend(larger[2 * count:])
                    variants = ((minimal, selected), (larger, selected), (interleaved, 2 * selected + 1))
                    for blocks in block_cases:
                        attempts += 1
                        try:
                            expected = reader._source_owners(base, blocks, current, fixing, selected=selected)
                        except reader.Unusable:
                            continue
                        unique += 1
                        for enlarged, target in variants:
                            try:
                                actual = reader._large_retry_source_owner(enlarged, blocks, target, current, fixing)
                            except reader.Unusable as error:
                                assert str(error) == AMBIGUOUS
                                refusals += 1
                            else:
                                remapped = {target: expected[selected]} if selected in expected else {}
                                assert actual == remapped, (count, declared, inherited, selected, selected_fix,
                                                            blocks, expected, actual)
                                matched += 1
    assert matched + refusals == unique * 3
    assert unique > 0 and matched > 0
    print('I1 exhaustive:', {'entries': count, 'block_cases': len(block_cases), 'baselines': attempts,
                             'unique': unique, 'same_owner': matched, 'refused': refusals})
    return attempts


@pytest.mark.parametrize('count', [1, 2, 3])
def test_exhaustive_small_unique_owner_agrees_after_inline_padding(count, monkeypatch):
    """Every unique small owner stays identical or is conservatively refused.

    Exhaust all declared hook vectors,0..3 block multisets/permutations,
    every source inheritance mask, every selected index, and parent versus fix
    inheritance for the selected entry. Minimal/larger appended padding and
    prefix/interleaved padding never need an external source block.
    """
    block_cases = [blocks for size in range(4)
                   for hook_sets in combinations_with_replacement(HOOK_SETS, size)
                   for blocks in permutations(blocks_for(hook_sets))]
    assert len(block_cases) == 145
    attempts = _check_agreement(count, block_cases, monkeypatch)
    assert attempts == {1: 1740, 2: 27840, 3: 334080}[count]


@pytest.mark.parametrize('count', [1, 2, 3])
def test_four_block_padding_that_activates_full_manifest_order_cannot_change_owner(count, monkeypatch):
    # Four entries after minimal padding activates the absolute-manifest order
    # branch; the original1..3-entry reply has no complete positional mapping.
    block_cases = list(permutations(blocks_for(HOOK_SETS)))
    attempts = _check_agreement(count, block_cases, monkeypatch)
    assert attempts == {1: 288, 2: 4608, 3: 55296}[count]


def test_existing_inline_sibling_and_all_block_permutations_keep_selected_owner():
    entries = [{'kind': 'new', 'id': 'a', 'hooks': ['before_call']},
               {'kind': 'new', 'id': 'b', 'hooks': ['bindings']},
               {'kind': 'new', 'id': 'inline', 'source': INHERITED}]
    blocks = blocks_for((('before_call',), ('bindings',), HOOKS))
    unique = 0
    for ordered in permutations(entries):
        for arranged in permutations(blocks):
            for selected in (index for index, item in enumerate(ordered) if item['id'] != 'inline'):
                try:
                    expected = reader._source_owners(ordered, arranged, ctx(), None, selected=selected)
                except reader.Unusable:
                    continue
                unique += 1
                try:
                    actual = reader._large_retry_source_owner(padded(list(ordered), 1), arranged, selected, ctx(), None)
                except reader.Unusable as error:
                    assert str(error) == AMBIGUOUS
                else:
                    assert actual == expected
    assert unique > 0
