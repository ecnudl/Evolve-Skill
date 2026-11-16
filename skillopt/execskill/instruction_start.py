"""Frozen coevo5 instruction start, only for the two route-B v2.10 profiles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from skillopt.continual_eval.core import require

FIXTURE = Path(__file__).resolve().parents[2] / 'docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json'
FIXTURE_SHA256 = '175b0715909eeecb3fec356838b84566ade20b28f6a9b12cf985ad7de720ae5f'
START = 'historical_card_is_the_instruction'
ENGINEER_SENTENCE = ('The instruction is already given to the solver; procedures must add what the instruction '
                     'cannot do (computed, situation-specific checks and state), never restate it.')


def pins():
    raw = FIXTURE.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256, 'Frozen instruction fixture hash differs')
    entries = json.loads(raw)['instructions']
    from .profiles import BENCHES
    require(set(entries) == set(BENCHES), 'Five instruction pins required')
    for entry in entries.values():
        require(hashlib.sha256(entry['text'].encode()).hexdigest() == entry['sha256']
                and len(entry['text']) == entry['chars'], 'Instruction text/hash differs')
    return entries


def active_cards(cards, configuration):
    from .profiles import is_v210, is_v214, is_v222
    if is_v222(configuration):
        from .v222_cards import format_text, historical_text
        require(all(text in (format_text(bench), historical_text(bench)) for bench, text in cards.items()),
                "main-v8 active cards are fixed format blocks or pinned whole historical fallbacks")
        return dict(cards)
    if not is_v210(configuration):
        return dict(cards)
    instructions = pins()
    if is_v214(configuration):
        from .zebralogic import BENCH, CARD_TEXT
        instructions = {**instructions, BENCH: {'text': CARD_TEXT,
                        'sha256': hashlib.sha256(CARD_TEXT.encode()).hexdigest()}}
    require(set(cards) <= set(instructions), 'Instruction start supports the five registered benches only')
    for bench, text in cards.items():
        entry = instructions[bench]
        require(text == entry['text'] and hashlib.sha256(text.encode()).hexdigest() == entry['sha256'],
                'Historical solver card must equal the frozen instruction: ' + bench)
    return dict(cards)


def original_card(bench, active_text):
    from .zebralogic import BENCH, CARD_TEXT
    if bench == BENCH:
        require(active_text == CARD_TEXT, 'The neutral Zebra card is unchanged')
        return active_text
    require(active_text == pins()[bench]['text'], 'Historical solver card must equal the frozen instruction: ' + bench)
    return active_text


def original_cards(cards, configuration):
    from .profiles import is_v222
    if is_v222(configuration):
        from .v222_cards import historical_text
        active_cards(cards, configuration)
        return {bench: historical_text(bench) for bench in cards}
    return active_cards(cards, configuration)


def blank_definition():
    """The v2.10 B arm supplies no guidance text and runs no procedure."""
    return {'card': '', 'kind': 'blank'}


def engineer_system(configuration, *, train=False):
    from .engineer import ENGINEER_SYSTEM_V23, ENGINEER_SYSTEM_SINGLE_V23
    from .profiles import is_v210
    require(is_v210(configuration), 'Instruction engineer belongs to v2.10')
    return (ENGINEER_SYSTEM_V23 if train else ENGINEER_SYSTEM_SINGLE_V23) + '\n' + ENGINEER_SENTENCE


def engineer_sha256(configuration, *, train=False):
    return hashlib.sha256(engineer_system(configuration, train=train).encode()).hexdigest()
