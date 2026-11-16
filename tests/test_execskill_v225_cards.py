"""Authored constants, static screening and independent card capacity bounds."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from skillopt.coevo5.leakage import Corpus
from skillopt.execskill import engineer, policy, profiles as p, v225_cards as c
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Package, Procedure, empty, with_, validate, procedure_benches


def base():
    return empty(step='G/s0', evidence='engineering_fixture')


def card(bench='searchqa', **kw):
    return c.make_card(bench, kw.pop('text', 'Compare the evidence before deciding.'), **kw)


def screen(text, **kw):
    return c.card_violation(text, **{'bench': 'searchqa', 'corpus': {}, 'shown': [],
        'task_card': 'Public task information.', 'format_block': 'Keep the output concise.',
        'practice_ids': ['authored-identifier'], **kw})


def test_template_roundtrip_and_card_never_executes():
    proc = card(writer_sha256='a' * 64)
    assert c.is_card(proc)
    assert c.parse_source(proc.source) == {'home': 'searchqa', 'route': 'searchqa', 'text': c.metadata(proc)['text']}
    assert Procedure.from_json(proc.to_json()) == proc
    assert not policy.check(proc.source, version=policy.POLICY_VERSION_V225)
    assert procedure_benches(proc) == p.SUPPORTED_BENCHES
    assert proc.lineage == {'parent': None, 'revises': None, 'engineer_call': 'a' * 64}
    assert proc.hooks == () and not proc.replay_tests and not proc.header and proc.state_bytes == 0


@pytest.mark.parametrize('suffix', ['\n', '# comment\n', 'print(CARD_TEXT)\n', 'def applies(v):\n return True\n'])
def test_any_altered_source_is_not_a_card(suffix):
    proc = card()
    fake = SimpleNamespace(policy_version=policy.POLICY_VERSION_V225, source=proc.source + suffix)
    assert not c.is_card(fake)
    assert policy.check(fake.source, version=policy.POLICY_VERSION_V225)


@pytest.mark.parametrize('text,rule', [('', 'length'), ('x' * 3001, 'length'),
    ('\n'.join('- guidance' for _ in range(13)), 'length'),
    ('Use <ANSWER> tags', 'format_markers'), ('Use </calc>', 'format_markers'),
    ('Use <action>', 'format_markers'), ('```plain', 'format_markers'),
    ('Remember authored-identifier', 'item_identity'), ('use task_id', 'item_identity'),
    ('read secret.json', 'item_identity'), ('read secret.xlsx', 'item_identity'),
    ('visit folder/name.txt', 'item_identity'), ('visit folder\\name', 'item_identity'),
    ('open /data/folder/name', 'item_identity'), ('open ./folder/name', 'item_identity'),
    ('open ~/folder', 'item_identity'), ('see https://example.org', 'item_identity')])
def test_each_static_rule(text, rule):
    assert screen(text) == rule


def test_clean_domain_words_and_public_workbook_names_are_allowed():
    text = 'Inspect the bulletin and the receptacle. Read input.xlsx and write output.xlsx.'
    assert screen(text, task_card='Read input.xlsx and write output.xlsx.') is None
    assert policy.check(c.card_source('officeqa', 'officeqa', 'Read bulletin 291 and receptacle 2.'),
                        version=policy.POLICY_VERSION_V225) == []


def test_reference_number_and_phrase_are_rejected_without_public_exemption():
    corpus = Corpus('officeqa', [{'benchmark': 'officeqa', 'task_id': 'one',
        'public': {'question': 'How much?', 'context': 'Supplied material.'}, 'private': {'answer': '847391'}}])
    assert screen('Prefer the number 847391.', corpus={'officeqa': corpus}) == 'references'
    assert screen('Prefer the number 847391.', corpus=corpus, task_card='Public constant 847391.') is None
    assert screen('Prefer Verdant Mountain.', shown=[{'reference': 'Verdant Mountain'}]) == 'references'
    assert screen('Prefer 847391.', shown=[{'reference': '847391'}]) == 'references'


def test_shown_eightgram_rejected_but_public_template_allowed():
    phrase = 'carefully observe the supplied distinct objects before selecting an answer'
    assert screen(phrase, shown=[{'view': phrase, 'reply': ''}]) == 'copied_examples'
    assert screen(phrase, shown=[{'view': '', 'reply': phrase}]) == 'copied_examples'
    assert screen(phrase, shown=[{'view': phrase}], task_card=phrase) is None


def test_composition_order_blank_passthrough_and_routes():
    pkg = with_(base(), step='G/s1', add=[card()])
    assert c.compose('searchqa', 'FORMAT', pkg) == c.metadata(card())['text'] + '\n\nFORMAT'
    assert c.compose('searchqa', '', pkg) == ''
    assert c.compose('officeqa', 'FORMAT', pkg) == 'FORMAT'
    assert not pkg.for_bench('searchqa') and not pkg.for_bench('officeqa')
    assert pkg.card_for('officeqa') is None


def procedure(n):
    # Enough legal literal source to exercise the independent 64k budget.
    return Procedure(id=f'fx-ordinary-{n}', origin='searchqa', evidence='engineering_fixture',
        description='Authored procedure', hooks=(), source='TEXT = ' + repr('x' * 1300) + '\nMORE = ' + repr('x' * 1300) + '\n',
        policy_version=policy.POLICY_VERSION_V29)


def test_cards_outside_procedure_count_source_bytes_and_change_bounds():
    ordinary = [procedure(n) for n in range(24)]
    pkg = Package(tuple(ordinary) + (card(text='c' * 3000),), 'G/s1', 'engineering_fixture')
    assert len(pkg.procedures) == 25
    assert sum(len(x.source.encode()) for x in pkg.procedures) > p.MAX_PACKAGE_BYTES
    parent = Package(tuple(ordinary[:3]), 'G/s0', 'engineering_fixture')
    child = with_(parent, step='G/s1', remove=parent.order,
                  add=[card(b, ordinal=101 + i) for i, b in enumerate(c.BENCHES[:4])])
    validate(child, parent)
    ctx = SimpleNamespace(base=parent, parent=child)
    assert engineer.budget(ctx)['used'] == 3
    assert engineer.budget(ctx)['step_procedures'] == []


def test_five_cards_and_four_card_edits_are_separate_hard_caps():
    all_cards = [card(b, ordinal=101 + i) for i, b in enumerate(c.BENCHES)]
    pkg = Package(tuple(all_cards), 'G/s1', 'engineering_fixture')
    assert len(pkg.procedures) == c.MAX_CARDS == 5
    with pytest.raises(PackageInvalid, match='four card edits'):
        with_(base(), step='G/s1', add=all_cards)
    with pytest.raises(PackageInvalid, match='one per route'):
        Package(tuple(all_cards) + (card(ordinal=118),), 'G/s1', 'engineering_fixture')
    with pytest.raises(PackageInvalid, match='one per route'):
        Package((card(), card('officeqa', route='searchqa')), 'G/s1', 'engineering_fixture')


def test_card_hooks_and_describer_entries_cannot_be_smuggled_in():
    with pytest.raises(PackageInvalid):
        replace(card(), hooks=('applies',))
    with pytest.raises(PackageInvalid):
        Package((card(),), 'G/s1', 'engineering_fixture', describer={card().id: {
            'text_sha256': 'a' * 64, 'prompt_sha256': 'b' * 64}})


def test_old_package_hashes_and_policy_records_stay_exact():
    from skillopt.execskill import v222_cards
    fixture = Path(__file__).parent / 'fixtures/execskill/v225_cards/legacy-package.json'
    old = v222_cards.initial_package(evidence='engineering_fixture', step='G/s0')
    assert old.to_json() == json.loads(fixture.read_text())
    assert policy.policy_sha256(version=policy.POLICY_VERSION_V222) == json.loads(
        (fixture.parent / 'pins.json').read_text())['legacy_policy_sha256']


def test_engineer_paragraph_replaces_only_two_exact_sentences():
    from skillopt.execskill import v222_cards, engineer_v221
    old = v222_cards.ENGINEER_SENTENCE
    assert old.count('Main-v8 instructions are routed note segments in the package.') == 1
    assert old.count('Format blocks are fixed and cannot be edited.') == 1
    new = c.engineer_sentence()
    assert new in engineer_v221.system('searchqa', train=True, configuration=p.MAIN_V9)
    assert old in engineer_v221.system('searchqa', train=True, configuration=p.MAIN_V8)
    assert c.prompt_pins()['ENGINEER_SENTENCE_V225']['text'] == new


@pytest.mark.parametrize('text',('normalize a/an/the before comparing','give the bare city/state/number','and/or','N/A','km/h','a ratio of 1/2',
    'either / or','use person/place/thing here'))
def test_ordinary_slashes_are_not_file_paths(text):
    assert screen(text) != 'item_identity'


def test_practice_ids_match_as_whole_words_only():
    assert screen('compare with 6698 rows', practice_ids=['6698']) == 'item_identity'
    assert screen('compare with 166985 rows', practice_ids=['6698']) != 'item_identity'
