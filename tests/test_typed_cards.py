"""typed-v2 card screen (docs/handoff/typed-v2/DESIGN.md 3.1, decision D2): content characters without the final
newline, the 4,500 hard limit while the writer is still told 3,000, the retry texts and their room rule, the marked
copy of the bound v2.25 content screens (drift corpus against the frozen function, copy pin), and the bound solver
path of a 4,500-character card. Fakes only: no network, no Docker, no /data, no file written."""
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from skillopt.coevo5 import leakage, texts
from skillopt.execskill import package, solver, v222_cards, v225_cards, v225_writer
from skillopt.execskill.corpus import Corpus
from skillopt.execskill.typed import MACHINERY, cards


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


FILLER = ('Weigh every supplied passage before you commit to a final entity, and prefer the reading that several '
          'independent passages support over one isolated mention. ')


def clean_text(n):
    """A clean card text of exactly ``n`` content characters (no surrounding whitespace, no final newline)."""
    text = (FILLER * (n // len(FILLER) + 1))[:n]
    return text[:-1] + '.' if text.endswith(' ') else text


def stored(reply):
    """A reply as the card writer stores it: ``texts.instruction_text`` (stripped content plus one newline)."""
    return texts.instruction_text(reply)


# The route-B screen context of tests/test_execskill_v225_cards.py (its ``screen`` helper).
PLAIN = {'bench': 'searchqa', 'corpus': {}, 'shown': [], 'task_card': 'Public task information.',
         'format_block': 'Keep the output concise.', 'practice_ids': ['authored-identifier']}


def plain(**changes):
    return {**PLAIN, **changes}


# The typed card writer's context of tests/test_typed_writers.py: practice items, the item corpus (``corpus_for``),
# the shown examples in the v2.25 writer shape (failures with their reference), the public card and format block.
CONTEXT_1 = ('Mount Kilimanjaro is the tallest free standing mountain in the world and rises above the plains of '
             'northern Tanzania near the border with Kenya; its summit Uhuru Peak is the highest point in Africa.')
ITEMS = [
    {'benchmark': 'searchqa', 'task_id': 'sq-1', 'public': {'question': 'tallest mountain in africa', 'context': CONTEXT_1},
     'private': {'answers': ['Mount Kilimanjaro']}},
    {'benchmark': 'searchqa', 'task_id': 'sq-2', 'public': {'question': 'river through cairo', 'context': 'The Nile flows north through Cairo to the Mediterranean delta.'},
     'private': {'answers': ['Nile']}},
    {'benchmark': 'searchqa', 'task_id': 'sq-3', 'public': {'question': 'author of war and peace', 'context': 'Leo Tolstoy wrote the novel over six years in the 1860s.'},
     'private': {'answers': ['Leo Tolstoy']}},
    {'benchmark': 'searchqa', 'task_id': 'sq-4', 'public': {'question': 'largest lake in africa', 'context': 'Lake Victoria is shared by Uganda, Kenya and Tanzania.'},
     'private': {'answers': ['Lake Victoria']}},
]


def _view(i):
    return json.dumps(ITEMS[i]['public'], ensure_ascii=False)


SHOWN = [{'view': _view(0), 'reply': 'The answer is <answer>Mount Kenya</answer>', 'outcome': 'fail',
          'reference': json.dumps(['Mount Kilimanjaro'])},
         {'view': _view(2), 'reply': '<answer>Dostoevsky</answer>', 'outcome': 'fail', 'reference': json.dumps(['Leo Tolstoy'])},
         {'view': _view(1), 'reply': '<answer>Nile</answer>', 'outcome': 'pass'},
         {'view': _view(3), 'reply': '<answer>Lake Victoria</answer>', 'outcome': 'pass'}]
WRITER = {'bench': 'searchqa', 'corpus': Corpus('searchqa', ITEMS), 'shown': SHOWN,
          'task_card': v225_writer.task_card('searchqa', {}), 'format_block': v222_cards.format_text('searchqa'),
          'practice_ids': [item['task_id'] for item in ITEMS]}

OFFICE = leakage.Corpus('officeqa', [{'benchmark': 'officeqa', 'task_id': 'one',
                                      'public': {'question': 'How much?', 'context': 'Supplied material.'},
                                      'private': {'answer': '847391'}}])
PHRASE = 'carefully observe the supplied distinct objects before selecting an answer'
TWELVE = '\n'.join('- guidance' for _ in range(12))
THIRTEEN = '\n'.join('- guidance' for _ in range(13))

# Fixed drift corpus: (text, screen context, the key both screens must return). Every text is also screened with one
# final newline (the stored shape).
DRIFT_CORPUS = [
    # the fourteen content cases of tests/test_execskill_v225_cards.py:50-56
    ('Use <ANSWER> tags', PLAIN, 'format_markers'), ('Use </calc>', PLAIN, 'format_markers'),
    ('Use <action>', PLAIN, 'format_markers'), ('```plain', PLAIN, 'format_markers'),
    ('Remember authored-identifier', PLAIN, 'item_identity'), ('use task_id', PLAIN, 'item_identity'),
    ('read secret.json', PLAIN, 'item_identity'), ('read secret.xlsx', PLAIN, 'item_identity'),
    ('visit folder/name.txt', PLAIN, 'item_identity'), ('visit folder\\name', PLAIN, 'item_identity'),
    ('open /data/folder/name', PLAIN, 'item_identity'), ('open ./folder/name', PLAIN, 'item_identity'),
    ('open ~/folder', PLAIN, 'item_identity'), ('see https://example.org', PLAIN, 'item_identity'),
    # the reference cases of :68-74 and the shown eight-gram cases of :77-81
    ('Prefer the number 847391.', plain(corpus={'officeqa': OFFICE}), 'references'),
    ('Prefer the number 847391.', plain(corpus=OFFICE, task_card='Public constant 847391.'), None),
    ('Prefer Verdant Mountain.', plain(shown=[{'reference': 'Verdant Mountain'}]), 'references'),
    ('Prefer 847391.', plain(shown=[{'reference': '847391'}]), 'references'),
    (PHRASE, plain(shown=[{'view': PHRASE, 'reply': ''}]), 'copied_examples'),
    (PHRASE, plain(shown=[{'view': '', 'reply': PHRASE}]), 'copied_examples'),
    (PHRASE, plain(shown=[{'view': PHRASE}], task_card=PHRASE), None),
    # the four content cases of tests/test_typed_writers.py:156-159 in the card writer's context
    ('- Put the final entity inside <answer> tags.\n', WRITER, 'format_markers'),
    ('- Example sq-3 shows a wrong author.\n', WRITER, 'item_identity'),
    ('- When asked for a mountain, the answer is often Mount Kilimanjaro.\n', WRITER, 'references'),
    ('- Remember that the tallest free standing mountain in the world and rises above the plains.\n', WRITER,
     'copied_examples'),
    # clean cards: one line, exactly twelve bullets, 2,999 content characters, the public workbook names
    ('Compare the evidence before deciding.', PLAIN, None), (TWELVE, PLAIN, None),
    ('- Read every snippet before deciding.\n- Prefer the entity that several snippets support.\n', WRITER, None),
    (clean_text(2999), PLAIN, None), (clean_text(2999), WRITER, None),
    ('Inspect the bulletin and the receptacle. Read input.xlsx and write output.xlsx.',
     plain(task_card='Read input.xlsx and write output.xlsx.'), None),
]


def shapes(text):
    bare = text.rstrip('\n')
    return (bare, bare + '\n')


# ---- public names ------------------------------------------------------------------------------------------------
SCREEN_KEYWORDS = ('bench', 'corpus', 'shown', 'task_card', 'format_block', 'practice_ids')


def signature(function):
    return [(p.name, p.kind, p.default is inspect.Parameter.empty)
            for p in inspect.signature(function).parameters.values()]


def test_public_names_and_signatures_of_design_3_1():
    positional, keyword = inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY
    screen = [('text', positional, True)] + [(name, keyword, True) for name in SCREEN_KEYWORDS]
    assert signature(cards.card_screen) == screen and signature(cards.content_violation) == screen
    assert signature(cards.content_chars) == signature(cards.bullet_count) == [('text', positional, True)]
    assert signature(cards.retry_text) == [('seen', positional, True), ('room', keyword, True)]
    assert signature(cards.pins) == [] and signature(cards.copied_source) == []
    assert (cards.CARD_TOLD_CHARS, cards.CARD_HARD_CHARS, cards.CARD_MAX_BULLETS) == (3000, 4500, 12)
    assert cards.LIMITS_RECORD == {'told_chars': 3000, 'hard_chars': 4500, 'max_bullets': 12,
                                   'count': 'content characters without the final newline'}
    assert cards.BULLET.pattern == r'^\s*(?:[-*+•]|\d+[.)])\s+'
    assert list(cards.RETRY_SHORT) == ['length', 'format_markers', 'item_identity', 'references', 'copied_examples']
    assert all(isinstance(getattr(cards, name), str) for name in
               ('RETRY_FRAME', 'REASON_TOO_LONG', 'REASON_TOO_MANY_BULLETS', 'REASON_NO_TEXT', 'REASON_JOIN'))
    assert len(cards.COPIED_SOURCE_SHA256) == 64 and int(cards.COPIED_SOURCE_SHA256, 16) >= 0


# ---- counting and the length rule --------------------------------------------------------------------------------
@pytest.mark.parametrize('n,verdict', [(1, None), (2999, None), (3000, None), (3001, None), (4499, None),
                                       (4500, None), (4501, 'length'), (4502, 'length'), (6000, 'length')])
def test_content_count_and_the_4500_hard_limit(n, verdict):
    text = clean_text(n)
    replies = (text, '\n\n  ' + text + '  \n', '```markdown\n' + text + '\n```')
    for reply in replies:
        card = stored(reply)
        assert card == text + '\n' and cards.content_chars(card) == len(card) - 1 == n
    for shape in (text, text + '\n', text + '\n\n', '  ' + text):
        assert cards.content_chars(shape) == n
        assert cards.card_screen(shape, **WRITER) == {'violation': verdict, 'chars': n, 'bullets': 0}


def test_a_final_newline_changes_nothing_and_the_typed_v1_loss_is_gone():
    for n in (3000, 3001, 4500, 4501):
        assert cards.card_screen(clean_text(n), **WRITER) == cards.card_screen(clean_text(n) + '\n', **WRITER)
    exact = stored(clean_text(3000))  # typed-v1 counted this card as 3,001 characters and rejected it (F6)
    assert len(exact) == 3001 and v225_cards.card_violation(exact, **WRITER) == 'length'
    assert cards.card_screen(exact, **WRITER) == {'violation': None, 'chars': 3000, 'bullets': 0}


def test_bullet_lines_and_the_bullet_limit():
    assert cards.bullet_count(TWELVE) == 12 and cards.card_screen(TWELVE, **PLAIN)['violation'] is None
    assert cards.card_screen(THIRTEEN + '\n', **PLAIN) == {'violation': 'length', 'chars': len(THIRTEEN), 'bullets': 13}
    kinds = ['- a', '* b', '+ c', '• d', '1. e', '2) f', '  12. g', '\t- h']
    assert cards.bullet_count('\n'.join(kinds)) == len(kinds)
    assert cards.bullet_count('\n'.join(['-a', '1.e', 'Use - sparingly', 'x * y', '1990 was a year', '--- rule', ''])) == 0
    both = '\n'.join(['- ' + clean_text(400)] * 13)
    assert cards.card_screen(both, **PLAIN) == {'violation': 'length', 'chars': len(both), 'bullets': 13}
    assert len(both) > cards.CARD_HARD_CHARS


@pytest.mark.parametrize('text', [None, '', '   ', '\n\t \n', 123, b'- bytes'])
def test_no_text_is_a_length_failure_with_zero_counts(text):
    assert cards.content_chars(text) == 0 and cards.bullet_count(text) == 0
    assert cards.card_screen(text, **PLAIN) == {'violation': 'length', 'chars': 0, 'bullets': 0}
    with pytest.raises(ValueError):
        cards.content_violation(text, **PLAIN)


# ---- the copied content screens ------------------------------------------------------------------------------------
@pytest.mark.parametrize('text,context,key', DRIFT_CORPUS, ids=range(len(DRIFT_CORPUS)))
def test_content_screens_match_the_bound_function_on_the_fixed_corpus(text, context, key):
    for shape in shapes(text):
        assert len(shape) <= v225_cards.MAX_CARD_CHARS
        assert v225_cards.card_violation(shape, **context) == key
        assert cards.content_violation(shape, **context) == key
        seen = cards.card_screen(shape, **context)
        assert seen == {'violation': key, 'chars': len(shape.strip()), 'bullets': cards.bullet_count(shape)}


def test_the_three_length_cases_of_the_bound_screen():
    for text in ('', THIRTEEN):
        assert v225_cards.card_violation(text, **PLAIN) == cards.card_screen(text, **PLAIN)['violation'] == 'length'
    # the one documented difference: above the told 3,000 and within 4,500 the typed screen passes a clean card
    assert v225_cards.card_violation('x' * 3001, **PLAIN) == 'length'
    assert cards.card_screen('x' * 3001, **PLAIN) == {'violation': None, 'chars': 3001, 'bullets': 0}


@pytest.mark.parametrize('key,sentence', [
    ('format_markers', ' Put the final entity inside <answer> tags.'),
    ('item_identity', ' Example sq-3 shows a wrong author.'),
    ('references', ' When asked for a mountain, the answer is often Mount Kilimanjaro.'),
    ('copied_examples', ' Remember that the tallest free standing mountain in the world and rises above the plains.'),
])
@pytest.mark.parametrize('n', [3001, 3400, 4500])
def test_long_cards_still_fail_their_content_screen(key, sentence, n):
    card = stored(clean_text(n - len(sentence)) + sentence)
    assert cards.card_screen(card, **WRITER) == {'violation': key, 'chars': n, 'bullets': 0}
    assert v225_cards.card_violation(card, **WRITER) == 'length'  # the bound screen stops at its 3,000 rule


def test_copied_source_and_sentences_are_pinned():
    source = cards.copied_source()
    assert sha256(source) == cards.COPIED_SOURCE_SHA256
    bound_lines = Path(v225_cards.__file__).read_text(encoding='utf-8').splitlines(keepends=True)
    assert source == ''.join(bound_lines[168:201])  # X/v225_cards.py:169-201 of main-v10
    assert source.startswith('    if any(marker in text.lower()') and source.endswith('    return None\n')
    # the marked block of T/cards.py is that source, verbatim except the import line that names its package
    lines = Path(cards.__file__).read_text(encoding='utf-8').splitlines(keepends=True)
    begin = [i for i, line in enumerate(lines)
             if line.lstrip().startswith('# BEGIN COPY of skillopt/execskill/v225_cards.py:169-201')]
    end = [i for i, line in enumerate(lines) if line.strip() == '# END COPY']
    assert len(begin) == 1 and len(end) == 1
    first = begin[0]
    while lines[first].lstrip().startswith('#'):
        first += 1
    block, original = lines[first:end[0]], source.splitlines(keepends=True)
    assert len(block) == len(original) == 33
    assert [(a, b) for a, b in zip(block, original) if a != b] == [
        ('    from skillopt.execskill.engineer import absent_findings\n', '    from .engineer import absent_findings\n')]
    assert cards.PATH_LIKE is v225_cards.PATH_LIKE and cards._reference_values is v225_cards._reference_values
    # the bound sentences and limits; the bullet rule is the bound one
    assert cards.RETRY_FRAME == v225_cards.CARD_RETRY
    assert cards.RETRY_SHORT == v225_cards.RETRY_REASONS and list(cards.RETRY_SHORT) == list(v225_cards.RETRY_REASONS)
    assert (cards.CARD_TOLD_CHARS, cards.CARD_MAX_BULLETS) == (v225_cards.MAX_CARD_CHARS, v225_cards.MAX_CARD_BULLETS)
    assert cards.BULLET.pattern in inspect.getsource(v225_cards.card_violation)
    # the new sentences, word for word (spec/card.md 1.2); none names the enforced 4,500
    assert cards.REASON_TOO_LONG == ('it has {chars} characters, but a card may have at most {target}; '
                                     'cut at least {cut} characters')
    assert cards.REASON_TOO_MANY_BULLETS == ('it has {bullets} bullet points, but a card may have at most '
                                             '{max_bullets}; merge or remove at least {extra}')
    assert cards.REASON_NO_TEXT == ('it was empty or was cut off before its end, so no card text was received; keep '
                                    'the card within {target} characters and {max_bullets} bullet points')
    assert cards.REASON_JOIN == '; in addition, '
    written = (cards.RETRY_FRAME, cards.REASON_TOO_LONG, cards.REASON_TOO_MANY_BULLETS, cards.REASON_NO_TEXT,
               cards.REASON_JOIN, *cards.RETRY_SHORT.values())
    assert not any(number in text for text in written for number in ('4,500', '4500'))
    pins = cards.pins()
    assert pins == {'RETRY_FRAME': sha256(cards.RETRY_FRAME), 'REASON_TOO_LONG': sha256(cards.REASON_TOO_LONG),
                    'REASON_TOO_MANY_BULLETS': sha256(cards.REASON_TOO_MANY_BULLETS),
                    'REASON_NO_TEXT': sha256(cards.REASON_NO_TEXT), 'REASON_JOIN': sha256(cards.REASON_JOIN),
                    'RETRY_SHORT': {key: sha256(text) for key, text in v225_cards.RETRY_REASONS.items()},
                    'LIMITS_RECORD': cards.LIMITS_RECORD, 'COPIED_SOURCE_SHA256': cards.COPIED_SOURCE_SHA256}
    assert json.loads(json.dumps(pins)) == pins
    pins['LIMITS_RECORD']['hard_chars'] = 0
    assert cards.LIMITS_RECORD['hard_chars'] == 4500


# ---- the retry ---------------------------------------------------------------------------------------------------
FRAME = ('Your reply could not be used as the card: %s. Reply again with only the card text, following every rule '
         'of the system message.')
ROOM = 10 ** 6


def retry(chars, bullets, *, room=ROOM):
    return cards.retry_text({'violation': 'length', 'chars': chars, 'bullets': bullets}, room=room)


def test_retry_sentences_name_the_measured_length_the_target_and_the_cut():
    too_long = FRAME % 'it has 4,501 characters, but a card may have at most 3,000; cut at least 1,501 characters'
    assert retry(4501, 0) == too_long and len(too_long) == 213
    assert retry(5212, 3) == FRAME % 'it has 5,212 characters, but a card may have at most 3,000; cut at least 2,212 characters'
    assert retry(12345, 0) == FRAME % 'it has 12,345 characters, but a card may have at most 3,000; cut at least 9,345 characters'
    assert retry(1200, 15) == FRAME % 'it has 15 bullet points, but a card may have at most 12; merge or remove at least 3'
    assert retry(4501, 15) == FRAME % ('it has 4,501 characters, but a card may have at most 3,000; cut at least 1,501 '
                                       'characters; in addition, it has 15 bullet points, but a card may have at most '
                                       '12; merge or remove at least 3')
    assert retry(0, 0) == FRAME % ('it was empty or was cut off before its end, so no card text was received; keep the '
                                   'card within 3,000 characters and 12 bullet points')
    for sentence in (retry(4501, 0), retry(5212, 0), retry(1200, 15), retry(4501, 15), retry(0, 0)):
        assert '4,500' not in sentence and '4500' not in sentence
    # from real screen results, as the writer's second attempt builds it
    for text, expected in ((stored(clean_text(4501)), retry(4501, 0)), (None, retry(0, 0)),
                           (THIRTEEN, retry(len(THIRTEEN), 13))):
        assert cards.retry_text(cards.card_screen(text, **PLAIN), room=ROOM) == expected


@pytest.mark.parametrize('key', ['format_markers', 'item_identity', 'references', 'copied_examples'])
def test_a_content_retry_is_the_typed_v1_sentence_at_any_room(key):
    typed_v1 = v225_cards.CARD_RETRY.format(reason=v225_cards.RETRY_REASONS[key])  # the typed-v1 retry (W:284-285)
    for room in (0, 199, ROOM):
        assert cards.retry_text({'violation': key, 'chars': 120, 'bullets': 2}, room=room) == typed_v1


def test_room_rule_falls_back_to_the_v225_length_sentence():
    short = v225_cards.CARD_RETRY.format(reason=v225_cards.RETRY_REASONS['length'])
    reserve = 2 + max(len(v225_cards.CARD_RETRY.format(reason=r)) for r in v225_cards.RETRY_REASONS.values())
    assert len(short) == 199 and reserve == 201  # the reserve of writers._fit_examples stays 2 + 199
    assert all(len(cards.RETRY_FRAME.format(reason=reason)) <= 199 for reason in cards.RETRY_SHORT.values())
    for chars, bullets in ((4501, 0), (0, 0), (100, 13), (9000, 40)):
        detailed = retry(chars, bullets)
        assert detailed != short and len(detailed) > 199
        assert retry(chars, bullets, room=len(detailed)) == detailed
        assert retry(chars, bullets, room=len(detailed) - 1) == short
        assert retry(chars, bullets, room=199) == short
        # the room of the second attempt: the writer ceiling minus the first message and the two newlines
        message = 'm' * (v225_cards.CARD_WRITER_INPUT_CHARS - reserve)
        sentence = retry(chars, bullets, room=v225_cards.CARD_WRITER_INPUT_CHARS - len(message) - 2)
        assert sentence == short and len(message) + 2 + len(sentence) <= v225_cards.CARD_WRITER_INPUT_CHARS


@pytest.mark.parametrize('seen,room', [
    ({'violation': None, 'chars': 10, 'bullets': 0}, 500),
    ({'violation': 'too_long', 'chars': 5000, 'bullets': 0}, 500),
    ({'violation': 'length', 'chars': 4500, 'bullets': 12}, 500),  # a length failure without a measured cause
    ({'violation': 'length', 'chars': True, 'bullets': 0}, 500),
    ({'violation': 'length', 'chars': -1, 'bullets': 0}, 500),
    ({'violation': 'length', 'chars': 5000}, 500),
    ({'violation': 'length', 'chars': 5000, 'bullets': 0}, 500.0),
    ({'violation': ['length'], 'chars': 5000, 'bullets': 0}, 500),
    ('length', 500),
])
def test_retry_text_refuses_what_is_no_screen_failure(seen, room):
    with pytest.raises(ValueError):
        cards.retry_text(seen, room=room)


# ---- frozen consumers ----------------------------------------------------------------------------------------------
def test_the_bound_solver_path_takes_a_4500_character_card_whole():
    """A typed mount hands the system card (card, blank line, format block) to the bound ``solver.solve``: ``compose``
    returns it unchanged for a package without a v2.25 card procedure, and the solver's system message carries it
    whole (plain concatenation, no length rule)."""
    card = stored(clean_text(4500))
    assert len(card) == 4501 and cards.card_screen(card, **WRITER)['violation'] is None
    typed_package = package.empty(step='G/s0', evidence='engineering_fixture')
    for bench in v225_cards.BENCHES:
        system_card = card + v225_cards.CARD_JOIN + v222_cards.format_text(bench)
        assert v225_cards.compose(bench, system_card, typed_package) == system_card
        assert system_card in solver._system(bench, system_card, {}, configuration=MACHINERY)
