"""Writers of typed-v2: card writer screens and retry, program writer (engineer contract, typed payload), describer.
Fakes only: scripted replies, no network, no Docker, no /data."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import types
from pathlib import Path

import pytest

from skillopt.coevo5.data import ranked
from skillopt.execskill import (engineer_reader, engineer_v295, package, policy, profiles, v222_cards, v225_cards,
                                v225_writer, zebralogic)
from skillopt.execskill.typed import (MAX_PROGRAM_PROPOSALS, ORDER, SEED, cards, engineer_prompt, gates, library,
                                      replies, units, writers)


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='writers-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- fakes ---------------------------------------------------------------------------------------------------
def receipt(text, *, finish='stop', ok=True):
    return {'ok': ok, 'response': text if ok else None, 'finish_reason': finish if ok else None,
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}, 'error_type': None if ok else 'http_502'}


class Script:
    """call(system, user) replying from a list: a str becomes a delivered receipt, a dict is returned as is."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        return reply if isinstance(reply, dict) else receipt(reply)


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
CLEAN_CARD = '- Read every snippet before deciding.\n- Prefer the entity that several snippets support.\n'


def cell(item, reply, correct, *, bench='searchqa', notes=None, extra_sends=0):
    """A mount cell as the chain stores it: sends with the solver request, the full reply, the judge outcome."""
    view = dict(item['public'])
    if notes:
        view['procedure_notes'] = notes
    user = json.dumps(view, ensure_ascii=False)
    sends = [{'request_sha256': 'x', 'system': 'sys', 'user': user, 'receipt': receipt(reply)}]
    sends += [{'request_sha256': 'y', 'system': 'sys', 'user': json.dumps({'observation': 'You see a mug.'}),
               'receipt': receipt(reply)} for _ in range(extra_sends)]
    return {'bench': bench, 'item_id': item['task_id'], 'arm': 'F', 'correct': correct,
            'token': 'pass' if correct else 'unknown' if correct is None else 'fail', 'reply': reply, 'sends': sends}


def examples_of(items=ITEMS):
    cells = [cell(items[0], 'The answer is <answer>Mount Kenya</answer>', False),
             cell(items[1], '<answer>Nile</answer>', True), cell(items[2], '<answer>Dostoevsky</answer>', False),
             cell(items[3], '<answer>Lake Victoria</answer>', True), cell(items[1], 'x', None)]
    return writers.outcomes_for_writer(cells, items, bench='searchqa')


def two_fence(changes, sources):
    blocks = ['```json\n' + json.dumps({'changes': changes}, sort_keys=True) + '\n```']
    return '\n\n'.join(blocks + ['```python\n' + source + '```' for source in sources])


SOURCE = ('def applies(view):\n    return "question" in view\n\n\n'
          'def before_call(view, state):\n    return {"facts": ["several snippets name the same entity"]}\n')
BAD_SOURCE = 'import os\n\n' + SOURCE
NEW = {'kind': 'new', 'description': 'Counts entity mentions', 'hooks': ['applies', 'before_call'],
       'max_note_chars': 600, 'replay_tests': []}
# typed-v2 (step 4b): one row of s<k>/programs/proposals.json and one fix record (DESIGN 3.2, 4.1)
ROW_KEYS = {'n', 'status', 'slot', 'procedure', 'screen', 'first_screen', 'fix', 'request_sha256', 'read',
            'format_retry', 'entry', 'source', 'kind', 'repairs'}
FIX_KEYS = {'request_sha256', 'parsed', 'reason', 'entry', 'source', 'repairs', 'read', 'format_retry', 'problem',
            'screen_evidence'}


# ---- examples from outcomes ------------------------------------------------------------------------------------
def test_outcomes_for_writer_orders_failures_first_and_skips_unknown():
    items = [{'benchmark': 'searchqa', 'task_id': 'q%02d' % i, 'public': {'question': 'q%d' % i, 'context': 'c' * 4000},
              'private': {'answers': ['a%d' % i]}} for i in range(24)]
    cells = [cell(item, 'r' * 2000, i >= 15) for i, item in enumerate(items)] + [cell(items[0], 'dup', True)]
    cells[3]['correct'] = None  # unknown: never shown (14 failures and 9 successes remain)
    out = writers.outcomes_for_writer(cells, items, bench='searchqa', seed=SEED)
    assert [e['outcome'] for e in out] == ['fail'] * 12 + ['pass'] * 6
    failed = [{'task_id': c['item_id']} for c in cells[:15] if c['correct'] is False]
    expected = [r['task_id'] for r in ranked(failed, SEED, writers.EXAMPLE_TAG + ':searchqa')[:12]]
    assert [e['task_id'] for e in out[:12]] == expected
    first = out[0]
    assert len(first['view']) <= writers.VIEW_CHARS and v225_writer.TRUNCATION_MARK in first['view']
    assert len(first['reply']) == writers.REPLY_HEAD + writers.REPLY_TAIL + len(v225_writer.TRUNCATION_MARK)
    assert first['reference'] == json.dumps(['a%d' % int(first['task_id'][1:])])
    assert first['request_user'].startswith('{"question"') and all('reference' not in e for e in out[12:])
    assert len(first['request_user']) > writers.VIEW_CHARS  # the engineer's trajectories keep the full request
    with pytest.raises(ValueError):
        writers.outcomes_for_writer([cell({'task_id': 'zz', 'public': {}}, 'r', True)], items, bench='searchqa')


def test_alfworld_reference_and_corpus_from_routing_views():
    view = {'initial_observation': 'You are in a kitchen.\n\nYour task is to: put a mug in sink.',
            'admissible_commands_at_reset': ['look', 'go to sink 1'], 'task_text': 'put a mug in sink.'}
    items = [{'benchmark': 'alfworld', 'task_id': 'g1', 'public': {'game_file': '/x/g1', 'routing_view': view}, 'private': {}},
             {'benchmark': 'alfworld', 'task_id': 'g2', 'public': {'game_file': '/x/g2'}, 'private': {}}]
    lost = cell(items[0], '<action>look</action>', False, bench='alfworld', extra_sends=2)
    out = writers.outcomes_for_writer([lost], items, bench='alfworld')
    assert out[0]['reference'] == 'lost after 3 steps; last observation: You see a mug.'
    corpus = writers.corpus_for('alfworld', items)
    assert corpus.benchmark == 'alfworld' and corpus.size == 1
    assert writers.corpus_for('searchqa', ITEMS).phrases == {('mount', 'kilimanjaro'), ('leo', 'tolstoy'), ('lake', 'victoria')}


def test_hook_view_excerpts_like_route_b():
    view = {'question': 'q' * 2000, 'context': ['s'] * 30}
    sample = writers.hook_view_for('searchqa', view)
    assert len(sample['routing_view']['question']) == 1500 and len(sample['hook_view']['context']) == 20
    assert sample['string_chars'] == 1500 and sample['list_entries'] == 20 and 'item' not in sample
    alf = writers.hook_view_for('alfworld', {'initial_observation': 'o', 'admissible_commands_at_reset': ['look'], 'task_text': 't'})
    assert alf['hook_view'] == {'initial_observation': 'o', 'observation': 'o', 'admissible_commands': ['look'], 'recent_history': []}


# ---- the card writer -------------------------------------------------------------------------------------------
def test_write_card_accepts_a_clean_reply_with_the_v225_request_shape():
    examples, corpus = examples_of(), writers.corpus_for('searchqa', ITEMS)
    script = Script([CLEAN_CARD])
    out = writers.write_card(bench='searchqa', runtime={}, current_text='', examples=examples, corpus=corpus,
                             practice_ids=[i['task_id'] for i in ITEMS], call=script, round=1)
    assert out['text'] == CLEAN_CARD and len(out['attempts']) == 1 and out['attempts'][0]['violation'] is None
    assert out['attempts'][0]['request_sha256'] == writers.request_sha256(*script.calls[0])
    # typed-v2 rows: content characters (the final newline of the stored text not counted) and bullet lines
    assert out['attempts'][0]['chars'] == len(CLEAN_CARD) - 1 and out['attempts'][0]['bullets'] == 2
    assert out['card_limits'] == cards.LIMITS_RECORD and out['card_limits'] is not cards.LIMITS_RECORD
    system, user = script.calls[0]
    assert system == v225_cards.CARD_WRITE_SYSTEM
    expected, dropped = v225_writer.build_request(bench='searchqa', runtime={}, current_card='',
                                                  examples=[writers._shown(e) for e in examples], c=1)
    assert out['request'] == expected and json.loads(user) == expected and out['dropped'] == dropped
    assert user == writers._json(expected)  # byte for byte, not only the parsed object
    assert 'request_user' not in json.dumps(out['request']) and out['request']['format_block'] == v222_cards.format_text('searchqa')
    shown = out['request']['examples']
    assert {e['reference'] for e in shown if 'reference' in e} == {'["Mount Kilimanjaro"]', '["Leo Tolstoy"]'}
    assert [e['outcome'] for e in shown] == ['fail', 'fail', 'pass', 'pass'] and set(shown[2]) == {'view', 'reply', 'outcome'}


# typed-v2 (DESIGN 3.1): 'length' is now no text, above 4,500 content characters or above 12 bullet lines (typed-v1:
# above 3,000 characters with the final newline counted), so the length row moved from 3,001 to 4,501 characters and
# its retry names the measured length; the four content rows keep the v2.25 sentence byte for byte.
LENGTH_4501_RETRY = ('Your reply could not be used as the card: it has 4,501 characters, but a card may have at most '
                     '3,000; cut at least 1,501 characters. Reply again with only the card text, following every rule '
                     'of the system message.')
NO_TEXT_RETRY = ('Your reply could not be used as the card: it was empty or was cut off before its end, so no card '
                 'text was received; keep the card within 3,000 characters and 12 bullet points. Reply again with '
                 'only the card text, following every rule of the system message.')


@pytest.mark.parametrize('key,bad', [
    ('length', 'x' * 4501),
    ('format_markers', '- Put the final entity inside <answer> tags.\n'),
    ('item_identity', '- Example sq-3 shows a wrong author.\n'),
    ('references', '- When asked for a mountain, the answer is often Mount Kilimanjaro.\n'),
    ('copied_examples', '- Remember that the tallest free standing mountain in the world and rises above the plains.\n'),
], ids=['length', 'format_markers', 'item_identity', 'references', 'copied_examples'])
def test_write_card_rejects_each_screen_and_retries_once(key, bad):
    examples, corpus = examples_of(), writers.corpus_for('searchqa', ITEMS)
    script = Script([bad, CLEAN_CARD])
    out = writers.write_card(bench='searchqa', runtime={}, current_text='', examples=examples, corpus=corpus,
                             practice_ids=[i['task_id'] for i in ITEMS], call=script, round=1)
    assert [a['violation'] for a in out['attempts']] == [key, None] and out['text'] == CLEAN_CARD
    retry = script.calls[1][1]
    sentence = (LENGTH_4501_RETRY if key == 'length'
                else v225_cards.CARD_RETRY.format(reason=v225_cards.RETRY_REASONS[key]))
    assert retry.endswith(sentence) and retry == script.calls[0][1] + '\n\n' + sentence
    assert retry.startswith(script.calls[0][1])
    first = out['attempts'][0]
    assert first['chars'] == len(bad.strip()) and first['bullets'] == (0 if key == 'length' else 1)
    twice = Script([bad, bad])
    out = writers.write_card(bench='searchqa', runtime={}, current_text='', examples=examples, corpus=corpus,
                             practice_ids=[i['task_id'] for i in ITEMS], call=twice, round=1)
    assert out['text'] is None and [a['violation'] for a in out['attempts']] == [key, key] and len(twice.calls) == 2


def test_write_card_treats_undelivered_receipts_as_no_reply():
    examples, corpus = examples_of(), writers.corpus_for('searchqa', ITEMS)
    script = Script([receipt('- cut off', finish='length'), {'ok': False, 'usage': {}, 'error_type': 'http_502'}])
    out = writers.write_card(bench='searchqa', runtime={}, current_text='', examples=examples, corpus=corpus,
                             practice_ids=[], call=script, round=1)
    assert out['text'] is None and [a['violation'] for a in out['attempts']] == ['length', 'length']
    assert all(a['no_reply'] and a['chars'] == 0 for a in out['attempts'])
    # typed-v2: no bullet lines either, and the retry says that no card text arrived (typed-v1: the v2.25 'length')
    assert all(a['bullets'] == 0 for a in out['attempts'])
    assert script.calls[1][1] == script.calls[0][1] + '\n\n' + NO_TEXT_RETRY
    blank = Script(['  \n\n  ', CLEAN_CARD])  # delivered but blank: no text, though a reply arrived
    out = writers.write_card(bench='searchqa', runtime={}, current_text='', examples=examples, corpus=corpus,
                             practice_ids=[], call=blank, round=1)
    rows = [(a['violation'], a['chars'], a['bullets'], a['no_reply']) for a in out['attempts']]
    assert out['text'] == CLEAN_CARD and rows == [('length', 0, 0, False), (None, len(CLEAN_CARD) - 1, 2, False)]
    assert blank.calls[1][1] == blank.calls[0][1] + '\n\n' + NO_TEXT_RETRY


REVISE_REPEATS_SHA256 = 'b034975c5e318fc562644e40e94b85f3f48ccdfaf63d98a7c60bd518b3038c71'  # step 5w: round-2 request below


def test_revise_request_carries_the_gate_counts_only():
    examples, corpus = examples_of(), writers.corpus_for('searchqa', ITEMS)
    # typed-v2 step 5w: a repeat card decision (DESIGN 3.4, R = 3 runs per item and arm); the unknown item is a
    # model-side unknown run (scored 0, never excluded: excluded_unknown stays 0, addendum O1)
    pairs = [('item-%d' % i, i % 3 == 0, i % 2 == 0) for i in range(30)] + [('item-u', None, True)]
    items = [item for item, _, _ in pairs]
    cells = {(item, label): {'correct': value} for item, current, candidate in pairs
             for arm, value in (('F', current), ('cand_card', candidate)) for label in gates.repeat_labels(arm, 3)}
    kw = {'items': items, 'repeats': 3, 'minimum_points': 3.0, 'multiplier': 2.0}
    decision = gates.card_decision(gates.repeat_statistics(gates.arm_runs(cells, items, 'F', 3),
                                                           gates.arm_runs(cells, items, 'cand_card', 3), **kw))
    script = Script([CLEAN_CARD])
    out = writers.write_card(bench='searchqa', runtime={}, current_text='- old card\n', examples=examples, corpus=corpus,
                             practice_ids=[], call=script, round=2, previous='- old card\n', result=decision)
    system, user = script.calls[0]
    assert system == v225_cards.CARD_REVISE_SYSTEM
    request = json.loads(user)
    assert request['request'] == 'revise' and request['previous_card'] == '- old card\n'
    result = request['result']
    assert result['touched'] == 31 and result['fixed'] == decision['better'] and result['broken'] == decision['worse']
    assert result['net'] == decision['better'] - decision['worse'] and result['excluded_unknown'] == 0
    assert result['required_mean_gain_points'] == decision['tau_points'] and result['decision'] in ('accept', 'reject')
    assert result['mean_gain_points'] == decision['gain_points'] and decision['unknown_final']['baseline'] == 3
    # golden bytes of the round-2 request (DESIGN section 5): item means of R runs, this decision's own tau
    assert result == {'stage': 'gate', 'touched': 31, 'fixed': 11, 'broken': 5, 'net': 6, 'tied': 15,
                      'excluded_unknown': 0, 'mean_gain_points': decision['gain_points'],
                      'required_mean_gain_points': decision['tau_points'],
                      'rule': 'mean gain >= required points and fixed > broken on the gate slice',
                      'decision': 'accept' if decision['accepted'] else 'reject',
                      'failing_clause': None if decision['accepted'] else decision['reason']}
    assert hashlib.sha256(user.encode('utf-8')).hexdigest() == REVISE_REPEATS_SHA256
    with pytest.raises(ValueError):  # a typed-v1 pair decision (no repeats, an excluded item) is refused
        writers.revision_result({**decision, 'repeats': None})
    assert 'item-' not in json.dumps(result) and all(not isinstance(v, (list, dict)) for v in result.values())
    with pytest.raises(ValueError):
        writers.revision_result({'rows': [1, 2]})
    with pytest.raises(ValueError):
        writers.write_card(bench='searchqa', runtime={}, current_text='', examples=examples, corpus=corpus,
                           practice_ids=[], call=Script([CLEAN_CARD]), round=2, previous=None, result=decision)


# ---- card length (typed-v2: DESIGN 3.1, decision D2) -------------------------------------------------------------
CARD_LIMITS = {'told_chars': 3000, 'hard_chars': 4500, 'max_bullets': 12,
               'count': 'content characters without the final newline'}
RULE_LINE = '- Weigh each snippet before you settle on an entity.\n'


def clean_card(chars, *, bullets=0):
    """A card of exactly ``chars`` content characters with ``bullets`` bullet lines (no final newline) that passes
    every content screen against the searchqa fixtures of this file."""
    head = RULE_LINE * bullets
    assert len(head) < chars
    return head + 'y' * (chars - len(head))


def write(replies, *, examples=None):
    """One round-1 card write on the searchqa fixtures; returns (result, script)."""
    script = Script(replies)
    out = writers.write_card(bench='searchqa', runtime={}, current_text='',
                             corpus=writers.corpus_for('searchqa', ITEMS),
                             examples=examples_of() if examples is None else examples,
                             practice_ids=[i['task_id'] for i in ITEMS], call=script, round=1)
    return out, script


def retry_of(reason):
    return ('Your reply could not be used as the card: %s. Reply again with only the card text, following every rule '
            'of the system message.' % reason)


def ceiling_examples(message_chars):
    """One shown failure whose view pads the first card request to exactly ``message_chars`` characters."""
    def size(view):
        request, _ = writers.card_request(bench='searchqa', runtime={}, current_text='', round=1,
                                          examples=[{'view': view, 'reply': '', 'outcome': 'fail'}])
        return len(writers._json(request))
    return [{'view': 'v' * (message_chars - size('')), 'reply': '', 'outcome': 'fail'}]


@pytest.mark.parametrize('chars,bullets', [(3000, 0), (3001, 0), (4500, 0), (3000, 12), (4500, 12)])
def test_write_card_accepts_up_to_4500_content_characters_and_12_bullets(chars, bullets):
    card = clean_card(chars, bullets=bullets)
    for reply in (card, card + '\n', '\n  ' + card + '  \n\n'):  # a final newline (or padding) changes nothing
        out, script = write([reply])
        assert out['text'] == card + '\n' and len(script.calls) == 1 and out['card_limits'] == CARD_LIMITS
        assert out['attempts'] == [{'request_sha256': writers.request_sha256(*script.calls[0]), 'violation': None,
                                    'chars': chars, 'bullets': bullets, 'no_reply': False}]
    # typed-v1 screened with the bound v2.25 function, which counts the stored final newline: 'length' for each
    request = out['request']
    assert v225_cards.card_violation(out['text'], bench='searchqa', corpus=writers.corpus_for('searchqa', ITEMS),
                                     shown=request['examples'], task_card=request['task_card'],
                                     format_block=request['format_block'], practice_ids=[]) == 'length'


@pytest.mark.parametrize('chars,bullets,reason', [
    (4501, 0, 'it has 4,501 characters, but a card may have at most 3,000; cut at least 1,501 characters'),
    (5212, 0, 'it has 5,212 characters, but a card may have at most 3,000; cut at least 2,212 characters'),
    (2000, 13, 'it has 13 bullet points, but a card may have at most 12; merge or remove at least 1'),
    (4501, 15, 'it has 4,501 characters, but a card may have at most 3,000; cut at least 1,501 characters; '
               'in addition, it has 15 bullet points, but a card may have at most 12; merge or remove at least 3'),
], ids=['4501', '5212', '13-bullets', 'both'])
def test_write_card_rejects_above_4500_characters_or_12_bullets_and_names_the_measured_cause(chars, bullets, reason):
    card = clean_card(chars, bullets=bullets)
    runs = []
    for reply in (card, card + '\n', '\n  ' + card + '  \n\n'):  # a final newline (or padding) changes nothing
        out, script = write([reply, CLEAN_CARD])
        assert out['text'] == CLEAN_CARD and out['attempts'][1]['violation'] is None
        assert out['attempts'][0] == {'request_sha256': writers.request_sha256(*script.calls[0]), 'violation': 'length',
                                      'chars': chars, 'bullets': bullets, 'no_reply': False}
        system, retry = script.calls[1]
        assert system == v225_cards.CARD_WRITE_SYSTEM and retry == script.calls[0][1] + '\n\n' + retry_of(reason)
        assert '4,500' not in system + retry and '4500' not in system + retry  # the hard limit is never told
        runs.append((script.calls, out))
    assert runs[0] == runs[1] == runs[2]


def test_length_retry_uses_the_detailed_sentence_only_when_it_fits_the_writer_input_ceiling():
    """The room rule (DESIGN 3.1): the detailed sentence only when first message + 2 + sentence <= 120,000, else the
    v2.25 'length' sentence (typed-v1's retry, for which the examples' reserve always leaves room). ``_fit_examples``
    is unchanged, so the first request is too."""
    ceiling = v225_cards.CARD_WRITER_INPUT_CHARS
    short = v225_cards.CARD_RETRY.format(reason=v225_cards.RETRY_REASONS['length'])
    assert (len(LENGTH_4501_RETRY), len(short)) == (213, 199)
    for size, sentence in ((ceiling - 2 - len(LENGTH_4501_RETRY), LENGTH_4501_RETRY),
                           (ceiling - 1 - len(LENGTH_4501_RETRY), short), (ceiling - 2 - len(short), short)):
        out, script = write(['x' * 4501, CLEAN_CARD], examples=ceiling_examples(size))
        first, retry = script.calls[0][1], script.calls[1][1]
        assert len(first) == size and out['dropped'] == {'successes': 0, 'failures': 0} and out['text'] == CLEAN_CARD
        assert retry == first + '\n\n' + sentence and len(retry) <= ceiling


def test_a_4500_content_character_card_reaches_the_writers_later_consumers_whole(tmp_path):
    """A card the typed screen now keeps (4,500 content characters, stored with its newline: 4,501) is carried whole
    by the revise request (current and previous card; the examples are still fitted under the ceiling), by the
    library record through save and load, and by the describer request (spec/card.md 1.3)."""
    card = clean_card(4500, bullets=12) + '\n'
    reserve = 2 + max(len(v225_cards.CARD_RETRY.format(reason=r)) for r in v225_cards.RETRY_REASONS.values())
    script = Script([CLEAN_CARD])
    out = writers.write_card(bench='searchqa', runtime={}, current_text=card, examples=CEILING_EXAMPLES,
                             corpus=writers.corpus_for('searchqa', ITEMS), practice_ids=[], call=script, round=2,
                             previous=card, result=GOLDEN_RESULT)
    request = json.loads(script.calls[0][1])
    assert request['current_card'] == card and request['previous_card'] == card and out['text'] == CLEAN_CARD
    assert len(script.calls[0][1]) + reserve <= v225_cards.CARD_WRITER_INPUT_CHARS and sum(out['dropped'].values()) > 0
    skill = library.make_skill(skill_id='card-t01-s1', name='evidence-qa-card-s1', kind='card', home_type='t01',
                               body={'text': card}, origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'})
    shelf = library.Library()
    shelf.add(skill)
    shelf.save(tmp_path / 'library.json', step=1)
    stored = library.Library.load(tmp_path / 'library.json').active_card('t01')
    assert stored['body']['text'] == card and stored['sha256'] == skill['sha256']
    described = Script([json.dumps({'description': 'Use for evidence questions over several snippets.'})])
    found = writers.describe(stored, examples_of()[:3], described)
    assert found['description'] and json.loads(described.calls[0][1])['skill_content'] == card


# ---- golden: the card requests typed-v2 keeps byte-identical to typed-v1 (DESIGN 3.1, 4.2) -----------------------
# The committed typed-v1 writer: the git blob of skillopt/execskill/typed/writers.py at 9ca2754 (typed-v1), unchanged
# at 8375ecb (the untouched start of typed-v2), and the sha256 of its bytes. GOLDEN_DIGESTS were produced by running
# that writer on the scenarios below; the live test re-derives them from the blob wherever the checkout has it.
TYPED_V1_WRITERS_BLOB = '646346d02ac7661edd519ed571bf86bf57a5d7e6'
TYPED_V1_WRITERS_SHA256 = '39368635f3bd978a125aa714b52315c86c39da13fd6a75746922ef041b7884b5'
BAD_CARDS = {'format_markers': '- Put the final entity inside <answer> tags.\n',
             'item_identity': '- Example sq-3 shows a wrong author.\n',
             'references': '- When asked for a mountain, the answer is often Mount Kilimanjaro.\n',
             'copied_examples': ('- Remember that the tallest free standing mountain in the world and rises above '
                                 'the plains.\n')}
GOLDEN_EXAMPLES = [
    {'view': json.dumps(ITEMS[0]['public'], ensure_ascii=False), 'reply': 'The answer is <answer>Mount Kenya</answer>',
     'outcome': 'fail', 'reference': '["Mount Kilimanjaro"]'},
    {'view': json.dumps(ITEMS[2]['public'], ensure_ascii=False), 'reply': '<answer>Dostoevsky</answer>',
     'outcome': 'fail', 'reference': '["Leo Tolstoy"]'},
    {'view': json.dumps(ITEMS[1]['public'], ensure_ascii=False), 'reply': '<answer>Nile</answer>',
     'outcome': 'pass'},
    {'view': json.dumps(ITEMS[3]['public'], ensure_ascii=False), 'reply': '<answer>Lake Victoria</answer>',
     'outcome': 'pass'},
]
# 30 long examples: the first request only fits the 120,000-character ceiling after _fit_examples drops some
CEILING_EXAMPLES = [{'view': '"%s" %d' % ('v' * 4600, i), 'reply': 'r' * 1500,
                     'outcome': 'pass' if i % 3 == 0 else 'fail'} for i in range(30)]
# a round-2 result passed through revision_result unchanged (no gate decision record): counts and short labels only
GOLDEN_RESULT = {'stage': 'gate', 'touched': 40, 'fixed': 9, 'broken': 4, 'net': 5, 'tied': 27, 'excluded_unknown': 0,
                 'mean_gain_points': 12.5, 'required_mean_gain_points': 11.18, 'decision': 'reject',
                 'failing_clause': 'mean_gain_below_tau'}
# sha256 of json.dumps([[system, user], ...]) of every call of a scenario, as the typed-v1 writer sent them
GOLDEN_DIGESTS = {
    'write-searchqa': '69137fbb59675ef06a6c07295d8974e5ca2344fc21147862871ee65c7aa392f9',
    'write-searchqa-retry-format_markers': '92ae2ac2de313286275cf6e2a4f7ce6e262cce4e764cb357321479de4284ed86',
    'write-officeqa': 'c8bc0abb4c63dfc2e492190ee5bf46c4e22a29c9eee3a86f910fddd642649067',
    'write-officeqa-retry-format_markers': '0a38eb460084d61fa133c16fef568683fa3cac299cf0f4e49b4ba012f9b35b29',
    'write-zebralogic': '615cb638bd3ce8b9789af31e1b531ba40e20841def2e2605027c0b295809e0b5',
    'write-zebralogic-retry-format_markers': '0bcb199cad367cb62987d6ae81d85e70f9f8f431ca338331ba194874258385df',
    'write-spreadsheetbench': 'dfc4ffe5b006c26aa18ae2b2612060dfecd6b262ac8f8a9ff549f4aae1281e2b',
    'write-spreadsheetbench-retry-format_markers': '8f22fe0a0db7771fb4b81d1cd3e649bc3a816356b9597480da6e21e8633870e1',
    'write-alfworld': 'b675d52e31b0234d89157a8d1ce93095c293b5aa3863a545fbfcdbb1280408a7',
    'write-alfworld-retry-format_markers': '412bc6d081319833a5342ae81b676c9d6d2f051e623e1c4f12763c9826cf8c2a',
    'write-searchqa-retry-item_identity': 'fc31011d4af8cf5b973e515856ba5d308082a4569eab8d78cc339927db226b00',
    'write-searchqa-retry-references': '9453122e6270d8cbc954a43064bf5ba0eed48335466cc3f56a8713770ce919f4',
    'write-searchqa-retry-copied_examples': '5170659563705602938ad8d54f7172ece868069c9fb2f1ed227e6c0ef5833732',
    'write-searchqa-twice-item_identity': 'fc31011d4af8cf5b973e515856ba5d308082a4569eab8d78cc339927db226b00',
    'revise-searchqa': 'f52f6d37311dbd645a847aa4ba96aedde016b5ecfe89bbfc328ba482a7747d5a',
    'revise-searchqa-retry-references': 'd28a0138ba690a30be23735d21d37060ed6fd140e9a26e330a4fcb99cd520acf',
    'write-ceiling-retry-references': '5d0cd8e81a9290fb1b28e5b0386b9ff15054733cb5cc6b00cf6aa3a0b6b8c745',
}


def golden_scenarios():
    """name -> (write_card keyword arguments without ``call``, scripted replies). Literal inputs only, so the digests
    depend on the card writer and the bound v2.25 texts alone."""
    base = {'runtime': {}, 'corpus': writers.corpus_for('searchqa', ITEMS),
            'practice_ids': [i['task_id'] for i in ITEMS]}
    scenarios = {}
    for bench in ORDER:
        write_ = dict(base, bench=bench, current_text='', examples=GOLDEN_EXAMPLES, round=1)
        scenarios['write-%s' % bench] = (write_, [CLEAN_CARD])
        scenarios['write-%s-retry-format_markers' % bench] = (write_, [BAD_CARDS['format_markers'], CLEAN_CARD])
    write_ = dict(base, bench='searchqa', current_text='', examples=GOLDEN_EXAMPLES, round=1)
    for key in ('item_identity', 'references', 'copied_examples'):
        scenarios['write-searchqa-retry-' + key] = (write_, [BAD_CARDS[key], CLEAN_CARD])
    scenarios['write-searchqa-twice-item_identity'] = (write_, [BAD_CARDS['item_identity']] * 2)
    revise = dict(base, bench='searchqa', current_text=CLEAN_CARD, examples=GOLDEN_EXAMPLES, round=2,
                  previous=CLEAN_CARD, result=GOLDEN_RESULT)
    scenarios['revise-searchqa'] = (revise, [CLEAN_CARD])
    scenarios['revise-searchqa-retry-references'] = (revise, [BAD_CARDS['references'], CLEAN_CARD])
    ceiling = dict(base, bench='searchqa', current_text='', examples=CEILING_EXAMPLES, round=1)
    scenarios['write-ceiling-retry-references'] = (ceiling, [BAD_CARDS['references'], CLEAN_CARD])
    return scenarios


def run_writer(module, scenario):
    """(calls [(system, user), ...], result) of ``module.write_card`` on one scenario."""
    options, replies = scenario
    script = Script(replies)
    return script.calls, module.write_card(call=script, **options)


def call_digest(calls):
    return hashlib.sha256(json.dumps([list(call) for call in calls], ensure_ascii=False).encode('utf-8')).hexdigest()


def typed_v1_writers():
    """The committed typed-v1 writer module, executed as a sibling of this package (its relative imports resolve
    here; its card path uses none of them). Skips where the checkout lacks git or the blob (the pins still run)."""
    try:
        source = subprocess.run(['git', 'cat-file', 'blob', TYPED_V1_WRITERS_BLOB],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, check=True,
                                timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip('the typed-v1 writer blob is not available in this checkout')
    assert hashlib.sha256(source).hexdigest() == TYPED_V1_WRITERS_SHA256
    module = types.ModuleType('skillopt.execskill.typed.typed_v1_writers_golden')
    module.__package__ = 'skillopt.execskill.typed'
    exec(compile(source, 'typed-v1/skillopt/execskill/typed/writers.py', 'exec'), module.__dict__)
    return module


def test_card_requests_equal_the_golden_typed_v1_bytes():
    """The first attempt (five benches, both rounds, at the input ceiling) and every retry after a content screen send
    exactly the bytes the committed typed-v1 writer sent (DESIGN 3.1, 4.2: unchanged requests)."""
    scenarios = golden_scenarios()
    assert sorted(scenarios) == sorted(GOLDEN_DIGESTS)
    for name, scenario in scenarios.items():
        calls, out = run_writer(writers, scenario)
        assert call_digest(calls) == GOLDEN_DIGESTS[name], name
        system = v225_cards.CARD_WRITE_SYSTEM if scenario[0]['round'] == 1 else v225_cards.CARD_REVISE_SYSTEM
        assert calls[0] == (system, writers._json(out['request'])), name
    _, out = run_writer(writers, scenarios['write-ceiling-retry-references'])
    assert out['dropped'] == {'successes': 10, 'failures': 1}  # the fitting of examples ran and is unchanged


def test_card_requests_equal_the_committed_typed_v1_writer_except_the_documented_length_retry():
    v1 = typed_v1_writers()
    scenarios = golden_scenarios()
    for name, scenario in scenarios.items():
        old_calls, old = run_writer(v1, scenario)
        new_calls, new = run_writer(writers, scenario)
        assert new_calls == old_calls and call_digest(old_calls) == GOLDEN_DIGESTS[name], name
        assert (new['text'], new['request'], new['dropped']) == (old['text'], old['request'], old['dropped']), name
        assert [(a['request_sha256'], a['violation'], a['no_reply']) for a in new['attempts']] == [
            (a['request_sha256'], a['violation'], a['no_reply']) for a in old['attempts']], name
        # the record change: chars no longer counts the final newline that the stored text keeps
        assert [a['chars'] for a in new['attempts']] == [max(a['chars'] - 1, 0) for a in old['attempts']], name
    # DESIGN 4.2 (1), the one changed request: the retry after a length failure names the measured cause
    base = scenarios['write-searchqa'][0]
    short = v225_cards.CARD_RETRY.format(reason=v225_cards.RETRY_REASONS['length'])
    for replies, sentence in (
            (['x' * 4501, CLEAN_CARD], LENGTH_4501_RETRY),
            ([clean_card(2000, bullets=13), CLEAN_CARD],
             retry_of('it has 13 bullet points, but a card may have at most 12; merge or remove at least 1')),
            ([receipt('- cut off', finish='length'), CLEAN_CARD], NO_TEXT_RETRY)):
        old_calls, _ = run_writer(v1, (base, replies))
        new_calls, _ = run_writer(writers, (base, replies))
        first = old_calls[0]
        assert new_calls[0] == first and old_calls[1] == (first[0], first[1] + '\n\n' + short)
        assert new_calls[1] == (first[0], first[1] + '\n\n' + sentence)
    # the moved boundary: typed-v1 rejected 3,000 content characters (it counted 3,001), typed-v2 keeps them
    old_calls, old = run_writer(v1, (base, [clean_card(3000), CLEAN_CARD]))
    new_calls, new = run_writer(writers, (base, [clean_card(3000), CLEAN_CARD]))
    assert [a['violation'] for a in old['attempts']] == ['length', None]
    assert [a['violation'] for a in new['attempts']] == [None]
    assert new_calls == old_calls[:1] and new['text'] == clean_card(3000) + '\n' and old['text'] == CLEAN_CARD
    # where the detailed sentence does not fit, typed-v2's length retry is typed-v1's, byte for byte
    tight = dict(base, examples=ceiling_examples(v225_cards.CARD_WRITER_INPUT_CHARS - 1 - len(LENGTH_4501_RETRY)))
    old_calls, _ = run_writer(v1, (tight, ['x' * 4501, CLEAN_CARD]))
    new_calls, _ = run_writer(writers, (tight, ['x' * 4501, CLEAN_CARD]))
    assert new_calls == old_calls and new_calls[1][1].endswith('\n\n' + short)


# ---- the program writer ----------------------------------------------------------------------------------------
def parent_package(*procedures):
    return package.Package(tuple(procedures), 'typed/G/s1', 'engineering_fixture')


def propose(script, *, bench='searchqa', parent=None, examples=None, index=None, **options):
    examples = examples_of() if examples is None else examples
    parent = parent_package() if parent is None else parent
    index = [{'name': 'evidence-answer-card', 'kind': 'card', 'description': 'Guides evidence QA.'}] if index is None else index
    view = ITEMS[0]['public'] if bench == 'searchqa' else options.pop('view')
    return writers.propose_programs(bench=bench, runtime={}, skill_index=index, examples=examples,
                                    hook_view=writers.hook_view_for(bench, view), parent=parent, call=script,
                                    evidence='engineering_fixture', **options)


def test_propose_programs_parses_a_two_fence_reply_into_a_typed_procedure():
    script = Script([two_fence([NEW], [SOURCE])])
    rows = propose(script)
    assert len(rows) == 1 and len(script.calls) == 1
    row = rows[0]
    assert row['screen'] == {'passed': True, 'reason': None} and row['kind'] == 'new' and row['fix'] is None
    record = row['procedure']
    assert record['policy_version'] == profiles.POLICY_VERSIONS[profiles.MAIN_V10] == 'fivebench-execskill-v2-22-policy'
    assert record['id'] == 'p-searchqa-1-1' and record['origin'] == 'searchqa' and record['excluded_benches'] == []
    system, user = script.calls[0]
    assert record['lineage'] == {'parent': None, 'revises': None, 'engineer_call': writers.request_sha256(system, user)}
    assert row['request_sha256'] == writers.request_sha256(system, user)
    rebuilt = package.Procedure.from_json(record)
    assert rebuilt.hooks == ('applies', 'before_call') and rebuilt.max_note_chars == 600 and rebuilt.source == SOURCE
    # typed-v2 (step 4b): the typed-owned pinned prompt replaces profiles.engineer_prompt(MAIN_V10, ..., 'propose')
    assert system == engineer_prompt.system('searchqa', 'propose') == writers.engineer_system('searchqa', 'propose')
    assert hashlib.sha256(system.encode('utf-8')).hexdigest() == engineer_prompt.PINS[('searchqa', 'propose')]
    assert system != profiles.engineer_prompt(profiles.MAIN_V10, 'searchqa', 'single', 'propose')
    assert set(row) == ROW_KEYS and row['n'] == 1 and row['status'] == 'passed' and row['slot'] == 1
    assert row['first_screen'] == {'passed': True, 'check': None, 'rules': []} and row['format_retry'] is None
    assert row['read']['source_from'] == 'fence' and row['read']['reader'] == replies.READER
    assert row['entry']['description'] == NEW['description'] and row['source'] == SOURCE
    payload = json.loads(user)
    assert payload['skill_index'] == [{'name': 'evidence-answer-card', 'kind': 'card', 'description': 'Guides evidence QA.'}]
    assert 'card' not in payload and 'package' not in payload and payload['request'] == 'propose'
    assert payload['task_card'] == v225_writer.task_card('searchqa', {}) and payload['hook_views']['string_chars'] == 1500
    shown = payload['trajectories']
    assert [t['kind'] for t in shown] == ['failures', 'failures', 'successes', 'successes']
    assert shown[0]['calls'][0]['purpose'] == 'first' and json.loads(shown[0]['calls'][0]['user'])['question']
    assert shown[0]['reference'] and 'reference' not in shown[2] and shown[0]['shell'] == {'notes': [], 'faults': [], 'procedure_calls': []}
    assert payload['trajectories_omitted'] == 0 and 'payload_trimming' in payload


def test_program_payload_refuses_index_rows_with_bodies():
    with pytest.raises(ValueError):
        writers.program_payload(bench='searchqa', runtime={}, examples=examples_of(), hook_view=None,
                                skill_index=[{'name': 'a-card', 'kind': 'card', 'description': 'd', 'body': 'SECRET'}])


def test_propose_programs_drops_revision_and_deletion_kinds():
    existing, _ = writers.build_procedure(NEW, SOURCE, bench='searchqa', evidence='engineering_fixture',
                                          engineer_call='a' * 64)
    other = SOURCE.replace('several snippets', 'two snippets')
    changes = [{'kind': 'revision', 'revises': 'p-searchqa-1-1', 'description': 'rev', 'hooks': ['applies', 'before_call'],
                'max_note_chars': 600, 'replay_tests': [], 'source': other},
               {'kind': 'deletion', 'id': 'p-searchqa-1-1'},
               {**NEW, 'description': 'A new helper'}]
    script = Script([two_fence(changes, [SOURCE.replace('several', 'many')])])
    rows = propose(script, parent=parent_package(existing))
    assert [r['kind'] for r in rows] == ['revision', 'deletion', 'new']
    assert [r['procedure'] is not None for r in rows] == [False, False, True]
    assert rows[0]['screen']['reason'] == 'kind_not_new:revision' and rows[1]['screen']['reason'] == 'kind_not_new:deletion'
    assert rows[2]['procedure']['id'] == 'p-searchqa-1-2' and len(script.calls) == 1  # 1-1 is taken by the parent
    assert [r['status'] for r in rows] == ['kind_not_new', 'kind_not_new', 'passed'] and [r['n'] for r in rows] == [1, 2, 3]
    assert [r['slot'] for r in rows] == [None, None, 1] and [r['first_screen'] is None for r in rows] == [True, True, False]


def test_propose_programs_screens_policy_and_makes_exactly_one_fix_call():
    fixed = two_fence([NEW], [SOURCE])
    script = Script([two_fence([NEW], [BAD_SOURCE]), fixed])
    rows = propose(script)
    assert len(rows) == 1 and len(script.calls) == 2
    row = rows[0]
    assert row['screen']['passed'] and row['fix']['parsed'] and row['fix']['reason'] is None
    fix_system, fix_user = script.calls[1]
    # typed-v2 (step 4b): the typed fix prompt and the fix request of DESIGN 3.2 (failed_source + screen evidence)
    assert fix_system == engineer_prompt.system('searchqa', 'fix') != profiles.engineer_prompt(
        profiles.MAIN_V10, 'searchqa', 'single', 'fix')
    request = json.loads(fix_user)
    assert request['request'] == 'fix' and request['bench'] == 'searchqa' and request['failed_source'] == BAD_SOURCE
    assert 'source' not in request['change'] and 'code' not in request['change']
    assert request['failed']['check'] == 'policy' and request['failed']['detail'][0]['rule'] == 'import'
    assert set(request) == {'request', 'bench', 'change', 'failed_source', 'failed'}
    assert row['procedure']['lineage']['engineer_call'] == writers.request_sha256(fix_system, fix_user) == row['fix']['request_sha256']
    assert row['procedure']['source'] == SOURCE
    assert row['status'] == 'passed_after_fix' and row['slot'] == 1 and row['procedure']['id'] == 'p-searchqa-1-1'
    assert row['first_screen'] == {'passed': False, 'check': 'policy', 'rules': ['import']}
    # a fix that still violates the policy is rejected without a third call
    again = Script([two_fence([NEW], [BAD_SOURCE]), two_fence([NEW], [BAD_SOURCE])])
    rows = propose(again)
    assert len(again.calls) == 2 and rows[0]['procedure'] is None and not rows[0]['screen']['passed']
    assert rows[0]['screen']['reason'].startswith('policy: ') and '| fix: policy: ' in rows[0]['screen']['reason']
    assert rows[0]['status'] == 'dropped_screen' and rows[0]['slot'] is None
    # no fix reply at all: the row records it and nothing more is sent
    silent = Script([two_fence([NEW], [BAD_SOURCE]), {'ok': False, 'usage': {}, 'error_type': 'http_502'}])
    rows = propose(silent)
    assert len(silent.calls) == 2 and rows[0]['procedure'] is None and rows[0]['fix']['reason'] == 'no_reply'
    assert rows[0]['status'] == 'dropped_screen' and rows[0]['fix']['format_retry'] is None


def test_propose_programs_respects_max_candidates_and_records_unusable_replies():
    sources = [SOURCE, SOURCE.replace('before_call(view, state)', 'bindings(view)').replace('{"facts": ["several snippets name the same entity"]}', 'None'),
               SOURCE.replace('several', 'many')]
    changes = [NEW, {**NEW, 'hooks': ['applies', 'bindings'], 'description': 'binds'}, {**NEW, 'description': 'third'}]
    script = Script([two_fence(changes, sources)])
    rows = propose(script, max_candidates=2)
    assert [r['procedure'] is not None for r in rows] == [True, True, False]
    # typed-v2 (step 4b): 'over_max_candidates' is now status and reason 'not_needed' (not screened, no call)
    assert rows[2]['screen']['reason'] == 'not_needed' and rows[2]['status'] == 'not_needed'
    assert rows[2]['first_screen'] is None and rows[2]['fix'] is None and len(script.calls) == 1
    assert [r['procedure']['id'] for r in rows[:2]] == ['p-searchqa-1-1', 'p-searchqa-1-2']
    assert rows[1]['procedure']['hooks'] == ['applies', 'bindings'] and rows[1]['procedure']['requests_second_call'] is False
    # typed-v2 (step 4b): an unreadable reply gets the unit's one format retry, so prose now costs two calls
    prose = Script(['no fences here, just prose', 'still no fences, sorry'])
    rows = propose(prose)
    assert len(prose.calls) == 2 and prose.calls[1][0] == replies.FORMAT_RETRY_SYSTEM
    assert len(rows) == 1 and rows[0]['procedure'] is None and rows[0]['screen']['reason'].startswith('unparseable')
    assert rows[0]['status'] == 'unreadable' and rows[0]['n'] is None and rows[0]['format_retry']['readable'] is False
    rows = propose(Script([{'ok': False, 'usage': {}, 'error_type': 'http_502'}]))
    assert rows[0]['screen'] == {'passed': False, 'reason': 'no_reply'} and rows[0]['status'] == 'no_reply'
    rows = propose(Script([two_fence(changes, sources)]), step=4)
    assert rows[0]['procedure']['id'] == 'p-searchqa-4-1'


def test_alfworld_programs_use_the_typed_engineer_prompt():
    """Was test_alfworld_programs_use_the_v295_prompt_family: typed-v2 (step 4b) deletes ALFWORLD_PROMPTS and
    alfworld_prompt_configuration; ALFWorld gets the typed-owned prompt like the other four benches."""
    expected = engineer_prompt.system('alfworld', 'propose')
    assert expected == writers.engineer_system('alfworld', 'propose') and 'alf_before_step' in expected
    assert expected != engineer_v295.system(profiles.ALFWORLD_V11, train=False)
    assert not hasattr(writers, 'alfworld_prompt_configuration') and not hasattr(writers, 'ALFWORLD_PROMPTS')
    assert writers.engineer_system('alfworld', 'fix') == engineer_prompt.system('alfworld', 'fix') != expected
    with pytest.raises(ValueError):
        profiles.engineer_prompt(profiles.MAIN_V10, 'alfworld', 'single', 'propose')  # main-v10 has no ALFWorld engineer
    view = {'initial_observation': 'You are in a kitchen.\n\nYour task is to: put a mug in a cabinet.',
            'admissible_commands_at_reset': ['look', 'go to cabinet 1'], 'task_text': 'put a mug in a cabinet.'}
    item = {'benchmark': 'alfworld', 'task_id': 'g1', 'public': {'game_file': '/x/g1', 'routing_view': view}, 'private': {}}
    step_user = json.dumps({'initial_observation': view['initial_observation'], 'observation': view['initial_observation'],
                            'admissible_commands': view['admissible_commands_at_reset'], 'recent_history': []})
    lost = cell(item, '<action>look</action>', False, bench='alfworld', extra_sends=1)
    lost['sends'][0]['user'] = step_user
    examples = writers.outcomes_for_writer([lost], [item], bench='alfworld')
    source = ('def applies(view):\n    return True\n\n\ndef alf_before_step(view, state):\n'
              '    return {"fields": {"facts": ["look around before moving"]}, "discourage": []}\n')
    change = {'kind': 'new', 'description': 'Looks first', 'hooks': ['applies', 'alf_before_step'], 'max_note_chars': 300, 'replay_tests': []}
    script = Script([two_fence([change], [source])])
    rows = propose(script, bench='alfworld', examples=examples, view=view)
    assert script.calls[0][0] == expected and rows[0]['procedure']['origin'] == 'alfworld'
    assert rows[0]['procedure']['hooks'] == ['applies', 'alf_before_step'] and rows[0]['procedure']['policy_version'] == writers.POLICY_VERSION
    assert rows[0]['status'] == 'passed' and rows[0]['slot'] == 1
    payload = json.loads(script.calls[0][1])
    assert payload['trajectories'][0]['reference'].startswith('lost after 2 steps') and payload['hook_views']['hook_view']['recent_history'] == []


def test_build_procedure_bounds_metadata_as_the_registrar_does():
    entry = {'kind': 'new', 'description': 'd' * 700, 'hooks': ['bindings'], 'header': 'h' * 300, 'max_note_chars': 99999,
             'requests_second_call': True, 'state_bytes': 5, 'replay_tests': [{'id': 't'}], 'excluded_benches': ['alfworld']}
    procedure, reason = writers.build_procedure(entry, SOURCE, bench='officeqa', evidence='smoke', engineer_call='c' * 64, step=2, ordinal=3)
    assert reason is None and procedure.id == 'p-officeqa-2-3' and procedure.evidence == 'smoke'
    assert procedure.hooks == ('applies', 'before_call') and len(procedure.description) == 600 and len(procedure.header) == 200
    assert procedure.max_note_chars == 4000 and procedure.requests_second_call is False and procedure.state_bytes == 0
    assert procedure.excluded_benches == () and procedure.replay_tests == ()
    assert writers.build_procedure({}, '', bench='officeqa', evidence='smoke', engineer_call='c' * 64)[1]['check'] == 'source'
    # typed-v2 (step 4b): an applies-only program now fails the typed hooks check (addendum O7) before the structure
    # check, so the structure case needs a program with a note hook
    none, why = writers.build_procedure({}, SOURCE, bench='officeqa', evidence='smoke', engineer_call='nothex')
    assert none is None and why['check'] == 'structure'
    none, why = writers.build_procedure({}, 'def applies(view):\n    return True\n', bench='officeqa', evidence='smoke', engineer_call='nothex')
    assert none is None and why['check'] == 'hooks' and why['detail'] == [
        {'rule': 'no_hook_function', 'line': 0, 'detail': 'defined: applies'}]


def test_zebra_trajectories_survive_the_payload_trim():
    puzzle = ('There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Each house is '
              'occupied by a different person. Each house has a unique attribute for each of the following '
              'characteristics:\n - Each person has a unique name: Arnold, Eric\n\n## Clues:\n1. Eric is in the first house.')
    view = zebralogic.public_view({'question': puzzle, 'columns': ['Name']})
    example = {'task_id': 'z1', 'view': puzzle[:100], 'reply': '{"solution": {}}', 'outcome': 'fail',
               'reference': json.dumps({'House 1': {'Name': 'Eric'}}), 'request_user': zebralogic.render_user(view, '')}
    user = writers.program_payload(bench='zebralogic', runtime={}, skill_index=[], examples=[example],
                                   hook_view=writers.hook_view_for('zebralogic', view))
    assert zebralogic.parse_user(user['trajectories'][0]['calls'][0]['user']) == view
    assert user['task_card'] == v225_cards.ZEBRA_TASK_CARD and user['format_block'] == zebralogic.CARD_TEXT
    shaped = writers.trajectory_examples([example], 'zebralogic')[0]
    assert set(shaped) == {'kind', 'bench', 'task_id', 'token', 'reference', 'calls', 'replies', 'shell'}
    with pytest.raises(ValueError):
        writers.trajectory_examples([{'task_id': 'z', 'view': 'v', 'outcome': 'pass'}], 'zebralogic')


# ---- typed-v2 program writer: fix request, promotion, format retry, call bound (step 4b, DESIGN 3.2 / 3.3) ----
NO_REPLY = {'ok': False, 'usage': {}, 'error_type': 'http_502'}
APPLIES_ONLY = 'def applies(view):\n    return True\n'
MAX_WRITER_CALLS = 1 + MAX_PROGRAM_PROPOSALS + replies.FORMAT_RETRIES_PER_UNIT   # DESIGN 3.2: 1 + 3 + 1 = 5


def good(i):
    return SOURCE.replace('several snippets', 'variant %d snippets' % i)


def bad(i):
    return 'import os\n\n' + good(i)


def entry_of(i):
    return {**NEW, 'description': 'Helper %d' % i}


def proposal(sources):
    return two_fence([entry_of(i) for i in range(1, len(sources) + 1)], sources)


def statuses(rows):
    return [(row['status'], row['slot']) for row in rows]


def kinds_sent(calls):
    return [json.loads(user)['request'] for _, user in calls]


def test_fix_request_carries_the_failed_source_and_the_screen_evidence():
    script = Script([two_fence([NEW], [BAD_SOURCE]), two_fence([NEW], [SOURCE])])
    rows = propose(script)
    entry = rows[0]['entry']
    failed = {'check': 'policy', 'detail': [v.to_json() for v in policy.check(BAD_SOURCE, version=writers.POLICY_VERSION)]}
    evidence = engineer_prompt.screen_evidence(failed, BAD_SOURCE, 'searchqa')
    expected = {'request': 'fix', 'bench': 'searchqa', 'change': entry, 'failed_source': BAD_SOURCE, 'failed': evidence}
    assert script.calls[1] == (engineer_prompt.system('searchqa', 'fix'), writers._json(expected))
    assert 'source' not in entry and entry['kind'] == 'new' and evidence['detail'][0]['rewrite']
    fix = rows[0]['fix']
    assert set(fix) == FIX_KEYS and set(rows[0]) == ROW_KEYS and fix['problem'] is None and fix['format_retry'] is None
    assert fix['screen_evidence'] == engineer_prompt.evidence_record(evidence)
    assert fix['screen_evidence']['rows'][0]['key'] == 'import' and fix['parsed'] and fix['source'] == SOURCE
    assert fix['read']['source_from'] == 'fence' and fix['entry']['kind'] == 'new'
    # ten violations: the fix request shows EVIDENCE_ROWS of them and counts the rest (build_procedure keeps five)
    many = ''.join('import os%d\n' % i for i in range(10)) + '\n' + SOURCE
    script = Script([two_fence([NEW], [many]), two_fence([NEW], [SOURCE])])
    rows = propose(script)
    shown = json.loads(script.calls[1][1])['failed']
    assert len(shown['detail']) == engineer_prompt.EVIDENCE_ROWS == 8 and shown['more'] == 2
    assert rows[0]['fix']['screen_evidence']['more'] == 2 and rows[0]['first_screen']['rules'] == ['import']


@pytest.mark.parametrize('sources,fixes,options,expected,calls', [
    # (a) pass, pass, a third: not needed (not screened, no call)
    ([good(1), good(2), good(3)], [], {}, [('passed', 1), ('passed', 2), ('not_needed', None)], 1),
    # (b) a screen failure whose fix fails: the third proposal is promoted
    ([bad(1), good(2), good(3)], [bad(1)], {}, [('dropped_screen', None), ('passed', 1), ('passed', 2)], 2),
    # (b2) two failures: the third proposal takes slot 1
    ([bad(1), bad(2), good(3)], [bad(1), bad(2)], {}, [('dropped_screen', None), ('dropped_screen', None), ('passed', 1)], 3),
    # (c) a good fix takes the slot
    ([bad(1), good(2), good(3)], [good(1)], {}, [('passed_after_fix', 1), ('passed', 2), ('not_needed', None)], 2),
    # (d) three failures: no slot, four calls
    ([bad(1), bad(2), bad(3)], [bad(1), bad(2), bad(3)], {},
     [('dropped_screen', None), ('dropped_screen', None), ('dropped_screen', None)], 4),
    # (f) one slot
    ([bad(1), good(2), good(3)], [bad(1)], {'max_candidates': 1}, [('dropped_screen', None), ('passed', 1), ('not_needed', None)], 2),
    ([good(1), bad(2), bad(3)], [], {'max_candidates': 1}, [('passed', 1), ('not_needed', None), ('not_needed', None)], 1),
])
def test_promotion_takes_a_later_proposal_only_after_a_screen_failure(sources, fixes, options, expected, calls):
    script = Script([proposal(sources)] + [two_fence([NEW], [fix]) for fix in fixes])
    rows = propose(script, **options)
    assert statuses(rows) == expected and len(script.calls) == calls and script.replies == []
    assert kinds_sent(script.calls) == ['propose'] + ['fix'] * (calls - 1)
    assert [row['n'] for row in rows] == [1, 2, 3] and all(set(row) == ROW_KEYS for row in rows)
    for row in rows:
        assert (row['procedure'] is not None) == (row['slot'] is not None) == row['screen']['passed']
        assert (row['first_screen'] is None) == (row['status'] == 'not_needed')
        assert (row['fix'] is not None) == (row['status'] in ('passed_after_fix', 'dropped_screen'))
        if row['status'] in ('passed', 'passed_after_fix', 'not_needed'):
            assert row['screen']['reason'] == (None if row['slot'] else 'not_needed')
        if row['status'] == 'dropped_screen':
            assert row['screen']['reason'].startswith('policy: ') and ' | fix: policy: ' in row['screen']['reason']
            assert row['first_screen'] == {'passed': False, 'check': 'policy', 'rules': ['import']}


def test_a_dropped_proposal_keeps_its_id_and_ids_are_independent_of_slots():
    # (g) the dropped proposal took p-searchqa-1-1; slot 1 holds p-searchqa-1-2, slot 2 p-searchqa-1-3
    rows = propose(Script([proposal([bad(1), good(2), good(3)]), two_fence([NEW], [bad(1)])]))
    assert [row['procedure']['id'] if row['procedure'] else None for row in rows] == [None, 'p-searchqa-1-2', 'p-searchqa-1-3']
    # a parent's id is never reused either, and a not-needed proposal takes none
    existing, _ = writers.build_procedure(NEW, SOURCE, bench='searchqa', evidence='engineering_fixture', engineer_call='a' * 64)
    rows = propose(Script([proposal([good(1), good(2), good(3)])]), parent=parent_package(existing), step=1)
    assert [row['procedure']['id'] if row['procedure'] else None for row in rows] == ['p-searchqa-1-2', 'p-searchqa-1-3', None]


def test_an_unreadable_record_gets_no_fix_call_and_the_next_takes_the_slot():
    # (e) change 1 has an unknown kind (a reading problem): no screen, no fix call, no slot
    changes = [{'kind': 'bogus', 'description': 'x'}, entry_of(2), entry_of(3)]
    script = Script([two_fence(changes, [good(2), good(3)])])
    rows = propose(script)
    assert statuses(rows) == [('unreadable', None), ('passed', 1), ('passed', 2)] and len(script.calls) == 1
    assert rows[0]['screen']['reason'].startswith('unparseable: unknown_kind: Change 1 has a `kind`')
    assert rows[0]['first_screen'] is None and rows[0]['fix'] is None and rows[0]['read']['reader'] == replies.READER
    assert rows[0]['format_retry'] is None  # one readable record: no format retry


def test_one_retry_budget_per_call_reaches_every_read(monkeypatch):
    # (h) the proposal read and every fix read get the same RetryBudget; the next call of propose_programs a new one
    seen, real = [], replies.read_with_retry

    def spy(reply, sha, **options):
        seen.append((options['purpose'], options['budget']))
        return real(reply, sha, **options)
    monkeypatch.setattr(replies, 'read_with_retry', spy)
    propose(Script([proposal([bad(1), bad(2)]), two_fence([NEW], [bad(1)]), two_fence([NEW], [good(2)])]))
    assert [purpose for purpose, _ in seen] == ['propose', 'fix', 'fix'] and len({id(b) for _, b in seen}) == 1
    first = seen[0][1]
    assert isinstance(first, replies.RetryBudget)
    seen.clear()
    propose(Script([proposal([good(1)])]))
    assert seen[0][1] is not first
    # (i) the reader's change limit is the proposal limit of the prompt
    assert MAX_PROGRAM_PROPOSALS == profiles.MAX_CHANGES == 3 and MAX_WRITER_CALLS == 5


def test_format_retry_once_per_unit_and_lineage_names_the_retry_call():
    script = Script(['I would add a helper that counts mentions.', proposal([good(1)])])
    rows = propose(script)
    (system0, user0), (system1, user1) = script.calls
    problems = [replies.read_proposals('I would add a helper that counts mentions.')['problem']]
    assert (system1, user1) == replies.retry_request('propose', 'searchqa', problems,
                                                     'I would add a helper that counts mentions.')
    retry_sha = writers.request_sha256(system1, user1)
    assert statuses(rows) == [('passed', 1)] and rows[0]['request_sha256'] == retry_sha
    assert rows[0]['procedure']['lineage']['engineer_call'] == retry_sha
    assert rows[0]['format_retry'] == {'first_request_sha256': writers.request_sha256(system0, user0),
                                       'request_sha256': retry_sha, 'problems': problems, 'no_reply': False,
                                       'readable': True, 'problems_after': []}


def test_format_retry_budget_is_shared_with_the_fix_calls():
    # fix 1 unreadable -> the unit's one retry -> a good program; fix 2 unreadable -> budget spent, no further call
    script = Script([proposal([bad(1), bad(2)]), 'Here is the fix: I removed the import.', two_fence([NEW], [good(1)]),
                     'Also fixed, see above.'])
    rows = propose(script)
    assert kinds_sent(script.calls) == ['propose', 'fix', 'format_retry', 'fix'] and script.replies == []
    assert statuses(rows) == [('passed_after_fix', 1), ('dropped_screen', None)]
    retry_sha = writers.request_sha256(*script.calls[2])
    assert rows[0]['fix']['request_sha256'] == retry_sha == rows[0]['procedure']['lineage']['engineer_call']
    assert rows[0]['fix']['format_retry']['readable'] is True and rows[0]['format_retry'] is None
    spent = rows[1]['fix']
    assert spent['format_retry']['skipped'] == 'budget_spent' and spent['problem']['code'] == 'no_manifest'
    assert spent['reason'].startswith('unparseable: no_manifest: ') and not spent['parsed']
    assert rows[1]['screen']['reason'].endswith(' | fix: ' + spent['reason'])


def test_no_format_retry_without_a_reply():
    script = Script([NO_REPLY])
    assert statuses(propose(script)) == [('no_reply', None)] and len(script.calls) == 1
    script = Script([proposal([bad(1)]), NO_REPLY])
    rows = propose(script)
    assert len(script.calls) == 2 and rows[0]['fix']['reason'] == 'no_reply' and rows[0]['fix']['format_retry'] is None
    assert statuses(rows) == [('dropped_screen', None)]
    # an explicit empty list is a readable "no proposal": no row, no retry
    script = Script([two_fence([], [])])
    assert propose(script) == [] and len(script.calls) == 1


@pytest.mark.parametrize('replies_', [
    # the proposal needs the retry, then three screen failures each get their one fix call
    ['Prose first.', proposal([bad(1), bad(2), bad(3)]), two_fence([NEW], [bad(1)]), two_fence([NEW], [bad(2)]),
     two_fence([NEW], [bad(3)])],
    # three screen failures; the first fix needs the retry; the last fix is unreadable with the budget spent
    [proposal([bad(1), bad(2), bad(3)]), 'Prose fix.', two_fence([NEW], [bad(1)]), two_fence([NEW], [bad(2)]),
     'More prose.'],
])
def test_at_most_five_writer_calls_per_unit_attempt(replies_):
    script = Script(list(replies_))
    rows = propose(script)
    assert len(script.calls) == MAX_WRITER_CALLS == 5 and script.replies == []  # a sixth call would pop an empty list
    assert statuses(rows) == [('dropped_screen', None)] * 3


BEHAVIOURS = ('pass', 'fix_pass', 'fix_fail', 'fix_prose', 'fix_none', 'unreadable')


class Writer:
    """A scripted program writer answering by request: the proposal, each fix by its failed source, each format
    retry by its previous reply."""

    def __init__(self, first, retries, fixes):
        self.first, self.retries, self.fixes, self.calls = first, retries, fixes, []

    def __call__(self, system, user):
        self.calls.append((system, user))
        request = json.loads(user)
        if request['request'] == 'propose':
            reply = self.first
        elif request['request'] == 'fix':
            reply = self.fixes[request['failed_source']]
        else:
            reply = self.retries[request['previous_reply']]
        return reply if isinstance(reply, dict) else receipt(reply)


def scripted_unit(behaviours, prose):
    changes, sources, retries, fixes = [], [], {}, {}
    for i, behaviour in enumerate(behaviours, 1):
        if behaviour == 'unreadable':
            changes.append({'kind': 'bogus', 'description': 'x %d' % i})
            continue
        changes.append(entry_of(i))
        sources.append(good(i) if behaviour == 'pass' else bad(i))
        reply = {'fix_pass': two_fence([NEW], [good(i)]), 'fix_fail': two_fence([NEW], [bad(i)]),
                 'fix_prose': 'Prose fix %d.' % i, 'fix_none': NO_REPLY}.get(behaviour)
        fixes[bad(i)] = reply
        if behaviour == 'fix_prose':
            retries['Prose fix %d.' % i] = two_fence([NEW], [good(i)])
    real = two_fence(changes, sources)
    first = 'Prose proposal.' if prose else real
    retries[first] = real
    return Writer(first, retries, fixes)


def expected_unit(behaviours, prose, slots):
    """An independent model of DESIGN 3.2 / 3.3: (statuses with slots, number of calls)."""
    calls, budget, taken, out = 1, 1, 0, []
    if prose or all(b == 'unreadable' for b in behaviours):
        calls, budget = 2, 0
    for behaviour in behaviours:
        if behaviour == 'unreadable':
            out.append(('unreadable', None))
            continue
        if taken >= slots:
            out.append(('not_needed', None))
            continue
        passed = behaviour in ('pass', 'fix_pass')
        if behaviour != 'pass':
            calls += 1
        if behaviour == 'fix_prose' and budget:
            budget, calls, passed = 0, calls + 1, True
        if passed:
            taken += 1
            out.append(('passed' if behaviour == 'pass' else 'passed_after_fix', taken))
        else:
            out.append(('dropped_screen', None))
    return out, calls


def test_every_promotion_scenario_follows_the_rule_and_the_call_bound():
    """All 6**3 behaviours of three proposals, with and without a format retry of the proposal, with one and two
    slots: statuses and slots follow DESIGN 3.2 (an independent model), never more than five writer calls, a slot
    only for a screened pass, never a screen or a call after the slots are full."""
    import itertools
    count = 0
    for behaviours in itertools.product(BEHAVIOURS, repeat=3):
        for prose in (False, True):
            for slots in (1, 2):
                writer = scripted_unit(behaviours, prose)
                rows = propose(writer, max_candidates=slots)
                expected, calls = expected_unit(behaviours, prose, slots)
                assert statuses(rows) == expected, (behaviours, prose, slots)
                assert len(writer.calls) == calls <= MAX_WRITER_CALLS, (behaviours, prose, slots)
                assert [row['slot'] for row in rows if row['slot']] == list(range(1, 1 + sum(1 for r in rows if r['slot'])))
                count += 1
    assert count == 6 ** 3 * 4


class Interrupt(Exception):
    pass


def recorded_call(tmp_path, scripted, *, stop_at):
    """The unit's recorded call as the chain builds it (units.CallRecorder over a ledger, the calls file of the
    programs unit); the client raises at send number ``stop_at``."""
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 9)
    sent = []

    def client(system, user):
        sent.append(1)
        if len(sent) == stop_at:
            raise Interrupt()
        reply = scripted.pop(0)
        return reply if isinstance(reply, dict) else receipt(reply)
    path = tmp_path / 'G' / 's1' / 'programs' / 'calls' / 'writer-program_writer.json'
    return units.CallRecorder(client, ledger, max_tokens=32768, tag='writer', unit='s1/programs', out_path=path), path


@pytest.mark.parametrize('scripted,stop_at,kinds', [
    # inside the promotion loop: during the second fix call
    ([proposal([bad(1), bad(2), good(3)]), two_fence([NEW], [bad(1)])], 3, ['propose', 'fix', 'fix']),
    # right after the format retry: during the first fix call
    (['Prose first.', proposal([bad(1), good(2)])], 3, ['propose', 'format_retry', 'fix']),
    # during the format retry of a fix
    ([proposal([bad(1), good(2)]), 'Prose fix.'], 3, ['propose', 'fix', 'format_retry']),
])
def test_an_interruption_inside_the_loop_keeps_every_send_in_the_calls_file(tmp_path, scripted, stop_at, kinds):
    call, path = recorded_call(tmp_path, list(scripted), stop_at=stop_at)
    with pytest.raises(Interrupt):
        propose(call)
    saved = json.loads(path.read_text())
    assert [json.loads(send['user'])['request'] for send in saved] == kinds and len(saved) == stop_at
    assert all(send['receipt'] is not None for send in saved[:-1]) and saved[-1]['receipt'] is None
    assert saved[-1]['exception'] == 'Interrupt' and saved == call.sends
    # the attempt that follows the interruption starts again from the proposal call and stays within the bound
    again, path = recorded_call(tmp_path / 'again', list(scripted) + [two_fence([NEW], [good(1)])] * 3, stop_at=0)
    rows = propose(again)
    assert 1 <= len(again.sends) <= MAX_WRITER_CALLS and json.loads(again.sends[0]['user'])['request'] == 'propose'
    assert any(row['slot'] for row in rows)


@pytest.mark.parametrize('declared,expected', [(None, 4000), (0, 4000), (-5, 4000), ('600', 4000), (True, 4000),
                                               (1, 1), (600, 600), (4000, 4000), (99999, 4000)])
def test_bounded_entry_gives_the_largest_note_cap_for_an_absent_or_non_positive_one(declared, expected):
    entry = {} if declared is None else {'max_note_chars': declared}
    values, repairs = writers._bounded_entry(entry, SOURCE)
    assert values['max_note_chars'] == expected
    procedure, _ = writers.build_procedure(entry, SOURCE, bench='searchqa', evidence='smoke', engineer_call='c' * 64)
    assert procedure.max_note_chars == expected
    bounded = [row for row in repairs if row['rule'] == 'bounded_metadata']
    before = declared if type(declared) is int else 0
    assert bounded == ([] if before == expected else
                       [{'rule': 'bounded_metadata', 'path': '$.max_note_chars', 'before': before, 'after': expected}])


def test_bounded_entry_state_bytes_and_programs_without_a_note_hook():
    alf = ('def alf_before_step(view, state):\n    return {"fields": {}, "discourage": []}\n\n\n'
           'def alf_after_step(event, state):\n    return {}\n')
    for declared, expected in ((None, 65536), (0, 65536), (-1, 65536), (5, 5), (10 ** 9, 65536)):
        entry = {} if declared is None else {'state_bytes': declared}
        assert writers._bounded_entry(entry, alf)[0]['state_bytes'] == expected
        assert writers._bounded_entry(entry, alf)[0]['max_note_chars'] == 4000
        assert writers._bounded_entry(entry, SOURCE)[0]['state_bytes'] == 0     # no alf_after_step: no state
    state_only = 'def alf_after_step(event, state):\n    return {}\n'
    assert writers._bounded_entry({'max_note_chars': 600}, state_only)[0]['max_note_chars'] == 0   # no note hook
    # through the reader: a missing cap and an explicit 0 both reach the procedure as 4,000 (typed-v1 gave 600 / 1)
    for entry in ({key: value for key, value in NEW.items() if key != 'max_note_chars'}, {**NEW, 'max_note_chars': 0}):
        rows = propose(Script([two_fence([entry], [SOURCE])]))
        assert rows[0]['procedure']['max_note_chars'] == 4000


NOTE_HOOKS = {'searchqa': {'before_call', 'bindings'}, 'officeqa': {'before_call', 'bindings'}, 'zebralogic': {'before_call'},
              'spreadsheetbench': {'before_call', 'sheet_feedback'}, 'alfworld': {'alf_before_step'}}
PARAMETERS = {'before_call': 'view, state', 'bindings': 'view', 'sheet_feedback': 'view, run_report, state',
              'alf_before_step': 'view, state', 'alf_after_step': 'event, state'}


@pytest.mark.parametrize('bench', ORDER)
def test_a_program_without_a_note_hook_of_its_bench_fails_the_hooks_check(bench):
    assert set(engineer_prompt.NOTE_HOOKS_BY_BENCH[bench]) == NOTE_HOOKS[bench]   # addendum O7, DESIGN 3.2
    for hook, parameters in PARAMETERS.items():
        source = APPLIES_ONLY + '\n\ndef %s(%s):\n    return None\n' % (hook, parameters)
        procedure, why = writers.build_procedure({}, source, bench=bench, evidence='smoke', engineer_call='c' * 64)
        if hook in NOTE_HOOKS[bench]:
            assert why is None and procedure.hooks == ('applies', hook)
        else:
            assert procedure is None and why['check'] == 'hooks' and set(why) == {'check', 'detail', 'repairs'}
            assert why['detail'] == [{'rule': 'no_hook_function', 'line': 0, 'detail': 'defined: applies, ' + hook}]
    _, why = writers.build_procedure({}, '"""Nothing."""\n', bench=bench, evidence='smoke', engineer_call='c' * 64)
    assert why['detail'][0]['detail'] == 'defined: none'


def alfworld_case():
    view = {'initial_observation': 'You are in a kitchen.\n\nYour task is to: put a mug in a cabinet.',
            'admissible_commands_at_reset': ['look', 'go to cabinet 1'], 'task_text': 'put a mug in a cabinet.'}
    item = {'benchmark': 'alfworld', 'task_id': 'g1', 'public': {'game_file': '/x/g1', 'routing_view': view}, 'private': {}}
    lost = cell(item, '<action>look</action>', False, bench='alfworld', extra_sends=1)
    return {'examples': writers.outcomes_for_writer([lost], [item], bench='alfworld'), 'view': view}


@pytest.mark.parametrize('bench,inert,fixed', [
    ('searchqa', APPLIES_ONLY, SOURCE),
    ('alfworld', 'def alf_after_step(event, state):\n    return {}\n',
     'def alf_before_step(view, state):\n    return {"fields": {}, "discourage": []}\n'),
])
def test_the_hooks_failure_gets_its_fix_call_with_the_check_words(bench, inert, fixed):
    options = alfworld_case() if bench == 'alfworld' else {}
    script = Script([two_fence([NEW], [inert]), two_fence([NEW], [fixed])])
    rows = propose(script, bench=bench, **options)
    assert statuses(rows) == [('passed_after_fix', 1)] and len(script.calls) == 2
    request = json.loads(script.calls[1][1])
    words = engineer_prompt.CHECK_WORDS['hooks']
    hooks = ', '.join(engineer_prompt.NOTE_HOOKS_BY_BENCH[bench])
    assert request['failed_source'] == inert and request['failed']['check'] == 'hooks' and request['failed']['more'] == 0
    assert request['failed']['detail'] == [{'rule': 'no_hook_function', 'line': 0, 'source_line': None,
                                            'detail': 'defined: ' + ', '.join(engineer_reader.defined_hooks(inert)),
                                            'rule_text': words['rule_text'] % hooks, 'rewrite': words['rewrite'] % hooks}]
    assert request['failed']['detail'][0]['rule_text'] in engineer_prompt.system(bench, 'fix')
    assert rows[0]['first_screen'] == {'passed': False, 'check': 'hooks', 'rules': ['no_hook_function']}
    assert rows[0]['fix']['screen_evidence']['rows'][0]['key'] == 'hooks'


def test_the_frozen_screen_call_is_unchanged(monkeypatch):
    calls, real = [], policy.check

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)
    monkeypatch.setattr(policy, 'check', spy)
    rows = propose(Script([two_fence([NEW], [BAD_SOURCE]), two_fence([NEW], [SOURCE])]))
    assert statuses(rows) == [('passed_after_fix', 1)]
    assert calls and all(len(args) == 1 and kwargs == {'version': writers.POLICY_VERSION} for args, kwargs in calls)
    # build_procedure on the proposal, the screen evidence of the fix request, build_procedure on the fix, and the
    # frozen Procedure's own validation of the accepted source (X/package.py:149, same call form)
    assert [args[0] for args, _ in calls if args[0] in (BAD_SOURCE, SOURCE)] == [BAD_SOURCE, BAD_SOURCE, SOURCE, SOURCE]
    assert writers.POLICY_VERSION == engineer_prompt.POLICY_VERSION == profiles.POLICY_VERSIONS[profiles.MAIN_V10]
    import inspect
    assert 'violations = policy.check(source, version=POLICY_VERSION)\n' in inspect.getsource(writers.build_procedure)


def test_propose_programs_verifies_the_prompt_once_per_process_before_any_request(monkeypatch):
    counted, real = [], engineer_prompt.verify
    monkeypatch.setattr(writers, '_PROMPT_CHECK', {})
    monkeypatch.setattr(engineer_prompt, 'verify', lambda: counted.append(1) or real())
    propose(Script([proposal([good(1)])]))
    propose(Script([proposal([good(1)])]))
    assert len(counted) == 1 and writers._PROMPT_CHECK['verified']['version'] == engineer_prompt.PROMPT_VERSION

    def broken():
        raise RuntimeError('engineer_prompt: the searchqa.propose text rendered now differs')
    monkeypatch.setattr(writers, '_PROMPT_CHECK', {})
    monkeypatch.setattr(engineer_prompt, 'verify', broken)
    script = Script([proposal([good(1)])])
    with pytest.raises(RuntimeError):
        propose(script)
    assert script.calls == []


# ---- the describer ---------------------------------------------------------------------------------------------
def program_skill():
    procedure, _ = writers.build_procedure(NEW, SOURCE, bench='searchqa', evidence='engineering_fixture', engineer_call='a' * 64)
    return library.make_skill(skill_id='prog-t01-s1-a', name='entity-counter', kind='program', home_type='t01',
                              body={'procedure': procedure.to_json()}, origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'})


def test_describe_parses_caps_and_retries_once():
    skill, examples = program_skill(), examples_of()[:3]
    script = Script([json.dumps({'description': 'x' * 451}), '```json\n{"description": "Counts how many snippets name each candidate."}\n```'])
    out = writers.describe(skill, examples, script)
    assert out['description'] == 'Counts how many snippets name each candidate.' and len(out['attempts']) == 2
    assert out['attempts'][0]['error'] and out['attempts'][1]['error'] is None
    assert out['request_sha256'] == writers.request_sha256(*script.calls[1]) == out['attempts'][1]['request_sha256']
    first_system, first_user = script.calls[0]
    assert first_system == library.DESCRIPTION_SYSTEM and script.calls[1][1] == first_user + writers.DESCRIPTION_RETRY
    payload = json.loads(first_user)
    assert payload['skill_content'] == SOURCE and len(payload['public_practice_examples']) == 3
    assert payload['public_practice_examples'][0].startswith('[outcome with this skill: fail]\n')
    assert 'reference' not in first_user and '<answer>' not in first_user  # neither references nor replies reach the describer
    one = writers.describe(skill, ['a', 'b', 'c'], Script([json.dumps({'description': 'Use for QA.'})]))
    assert one['description'] == 'Use for QA.' and len(one['attempts']) == 1
    failed = writers.describe(skill, examples, Script(['not json', {'ok': False, 'usage': {}, 'error_type': 'http_502'}]))
    assert failed['description'] is None and [a['error'] for a in failed['attempts']] == ['Reply is not a JSON object', 'no reply']
    assert failed['infrastructure'] is True and failed['attempts'][1]['no_reply'] == 'infrastructure:http_502'
    # a model-side noncompletion or a parse failure on the last attempt is a description failure, not infrastructure
    cut = writers.describe(skill, examples, Script([{'ok': False, 'usage': {}, 'error_type': 'transport'}, receipt('x', finish='length')]))
    assert cut['description'] is None and cut['infrastructure'] is False and cut['attempts'][1]['no_reply'] == 'model_side:finish_length'
    assert writers.describe(skill, examples, Script(['not json', 'still not json']))['infrastructure'] is False
    assert writers.reply_failure(receipt('ok')) is None and writers.reply_failure(None) == 'infrastructure:invalid_receipt'
    assert writers.reply_failure({'ok': False, 'error_type': 'finish_length'}) == 'model_side:finish_length'
    with pytest.raises(ValueError):
        writers.describe(skill, examples[:2], Script([]))


# ---- the selection call never reaches a writer ------------------------------------------------------------------
def selection_send():
    request = library.selection_request([{'name': 'grid-solver', 'description': 'Solves grids.'}], 'the task text')
    return {'request_sha256': request['request_sha256'], 'system': request['system'], 'user': request['user'],
            'receipt': receipt('{"use": ["grid-solver"], "why": "grid"}')}


def test_writers_skip_a_selection_send_recorded_before_the_solver_request():
    """A cell of a type that holds a program may carry its selection call first; the example view, the engineer's
    trajectories and the ALFWorld reference must read the SOLVER request, not the selection payload."""
    puzzle = ('There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Each house is '
              'occupied by a different person. Each house has a unique attribute for each of the following '
              'characteristics:\n - Each person has a unique name: Arnold, Eric\n\n## Clues:\n1. Eric is in the first house.')
    view = zebralogic.public_view({'question': puzzle, 'columns': ['Name']})
    zebra_item = {'benchmark': 'zebralogic', 'task_id': 'z1', 'public': {'question': puzzle, 'columns': ['Name']},
                  'private': {'answer': {'House 1': {'Name': 'Eric'}}}}
    zebra_cell = cell(zebra_item, '{"solution": {}}', False, bench='zebralogic')
    zebra_cell['sends'][0]['user'] = zebralogic.render_user(view, '')
    zebra_cell['sends'].insert(0, selection_send())
    office_item = {'benchmark': 'officeqa', 'task_id': 'o1', 'public': {'question': 'total receipts?', 'context': 'receipts 30'},
                   'private': {'answer': '30'}}
    office_cell = cell(office_item, '<answer>31</answer>', False, bench='officeqa')
    office_cell['sends'].insert(0, selection_send())
    for bench, item, row in (('zebralogic', zebra_item, zebra_cell), ('officeqa', office_item, office_cell)):
        example = writers.outcomes_for_writer([row], [item], bench=bench)[0]
        assert example['request_user'] == row['sends'][1]['user'] and '"skills"' not in example['view']
        user = writers.program_payload(bench=bench, runtime={}, skill_index=[], examples=[example],
                                       hook_view=writers.hook_view_for(bench, item['public'] if bench != 'zebralogic' else view))
        shown = user['trajectories'][0]['calls'][0]['user']  # the payload trim re-renders a QA request (sorted keys)
        assert (shown if bench == 'zebralogic' else json.loads(shown)) == (row['sends'][1]['user'] if bench == 'zebralogic'
                                                                           else json.loads(row['sends'][1]['user']))
    assert zebralogic.parse_user(writers.trajectory_examples([writers.outcomes_for_writer([zebra_cell], [zebra_item], bench='zebralogic')[0]],
                                                              'zebralogic')[0]['calls'][0]['user']) == view
    alf_view = {'initial_observation': 'You are in a kitchen.\n\nYour task is to: put a mug in sink.',
                'admissible_commands_at_reset': ['look'], 'task_text': 'put a mug in sink.'}
    alf_item = {'benchmark': 'alfworld', 'task_id': 'g1', 'public': {'game_file': '/x/g1', 'routing_view': alf_view}, 'private': {}}
    lost = cell(alf_item, '<action>look</action>', False, bench='alfworld', extra_sends=1)
    lost['sends'].insert(0, selection_send())
    assert writers.outcomes_for_writer([lost], [alf_item], bench='alfworld')[0]['reference'].startswith('lost after 2 steps')


def test_outcomes_for_writer_baseline_orders_changed_items_first():
    """The revision round (v2.25 ordering): failures the candidate card BROKE and successes it FIXED come first,
    the seeded order within each group; without a baseline the seeded order alone."""
    items = [{'benchmark': 'searchqa', 'task_id': 'q%02d' % i, 'public': {'question': 'q%d' % i, 'context': 'c'},
              'private': {'answers': ['a%d' % i]}} for i in range(8)]
    cells = [cell(item, 'r', i % 2 == 0) for i, item in enumerate(items)]  # even items pass with the card
    plain = [e['task_id'] for e in writers.outcomes_for_writer(cells, items, bench='searchqa', seed=SEED)]
    baseline = {'q01': True, 'q03': False, 'q05': True, 'q07': False, 'q00': False, 'q02': True, 'q04': True, 'q06': False}
    ordered = [e['task_id'] for e in writers.outcomes_for_writer(cells, items, bench='searchqa', seed=SEED, baseline=baseline)]
    fails, passes = plain[:4], plain[4:]
    assert ordered[:2] == [i for i in fails if i in ('q01', 'q05')] and ordered[2:4] == [i for i in fails if i in ('q03', 'q07')]
    assert ordered[4:6] == [i for i in passes if i in ('q00', 'q06')] and ordered[6:] == [i for i in passes if i in ('q02', 'q04')]
    assert sorted(ordered) == sorted(plain)


def test_program_payload_admits_the_opaque_home_type_in_the_index():
    user = writers.program_payload(bench='searchqa', runtime={}, examples=examples_of(), hook_view=writers.hook_view_for('searchqa', ITEMS[0]['public']),
                                   skill_index=[{'name': 'a-card', 'kind': 'card', 'description': 'd', 'home_type': 't02'},
                                                {'name': 'b-prog', 'kind': 'program', 'description': 'e'}])
    assert user['skill_index'] == [{'name': 'a-card', 'kind': 'card', 'description': 'd', 'home_type': 't02'},
                                   {'name': 'b-prog', 'kind': 'program', 'description': 'e'}]
