"""The card screen of typed-v2 (docs/handoff/typed-v2/DESIGN.md 3.1, decision D2) and the card writer's retry texts.

The writer is still TOLD 3,000 characters and 12 bullet points (the bound v2.25 prompts, unchanged); a card is
rejected for length only when there is no text, more than ``CARD_HARD_CHARS`` content characters or more than
``CARD_MAX_BULLETS`` bullet lines. Content characters are those of the stripped text: the final newline that
``texts.instruction_text`` appends is not counted, and the stored text keeps it. 4,500 is never named to the writer.
The four content screens are a marked copy of the bound ``v225_cards.card_violation`` after its length rule
(``skillopt/execskill/v225_cards.py:169-201`` of main-v10); ``COPIED_SOURCE_SHA256`` pins those lines as the bound
function holds them (``copied_source``). The frozen module is read and called here, never edited.
"""
from __future__ import annotations

import hashlib
import inspect
import re

from skillopt.coevo5 import leakage
from skillopt.continual_eval.core import require
from skillopt.execskill import v225_cards

CARD_TOLD_CHARS, CARD_HARD_CHARS, CARD_MAX_BULLETS = 3000, 4500, 12
require(CARD_TOLD_CHARS == v225_cards.MAX_CARD_CHARS and CARD_MAX_BULLETS == v225_cards.MAX_CARD_BULLETS,
        'The told card limits are the limits the bound v2.25 prompts state')
BULLET = re.compile(r'^\s*(?:[-*+•]|\d+[.)])\s+')        # copied from X/v225_cards.py:167
# sha256 of the copied lines as the bound function holds them (``copied_source``), computed when this was written.
COPIED_SOURCE_SHA256 = '796aa276975b2f449d97e329c37a20848536352fb95492157b3dae458f56ea2c'
LIMITS_RECORD = {'told_chars': CARD_TOLD_CHARS, 'hard_chars': CARD_HARD_CHARS, 'max_bullets': CARD_MAX_BULLETS,
                 'count': 'content characters without the final newline'}

# The retry texts (spec/card.md 1.2). RETRY_FRAME and RETRY_SHORT equal the bound CARD_RETRY / RETRY_REASONS, so a
# retry after a content screen is byte-identical to typed-v1; only a length retry is new text.
RETRY_FRAME = ('Your reply could not be used as the card: {reason}. Reply again with only the card text, '
               'following every rule of the system message.')
REASON_TOO_LONG = 'it has {chars} characters, but a card may have at most {target}; cut at least {cut} characters'
REASON_TOO_MANY_BULLETS = ('it has {bullets} bullet points, but a card may have at most {max_bullets}; '
                           'merge or remove at least {extra}')
REASON_NO_TEXT = ('it was empty or was cut off before its end, so no card text was received; keep the card '
                  'within {target} characters and {max_bullets} bullet points')
REASON_JOIN = '; in addition, '
RETRY_SHORT = {'length': 'it is empty, longer than 3,000 characters or has more than 12 bullet points',
               'format_markers': 'it contains an answer, action or calc tag or a code fence',
               'item_identity': 'it contains a task identifier or a file path',
               'references': 'it contains a reference answer or a value from one',
               'copied_examples': 'it copies text from an example'}

# The two bound names the copy reads unchanged.
PATH_LIKE = v225_cards.PATH_LIKE
_reference_values = v225_cards._reference_values


def content_chars(text) -> int:
    """The content characters of a card text: ``len(text.strip())``; 0 for no text (not a string, or blank)."""
    return len(text.strip()) if isinstance(text, str) else 0


def bullet_count(text) -> int:
    """The lines of ``text.splitlines()`` that start a bullet point (``BULLET``); 0 when not a string."""
    return sum(1 for line in text.splitlines() if BULLET.match(line)) if isinstance(text, str) else 0


def content_violation(text, *, bench, corpus, shown, task_card, format_block, practice_ids) -> str | None:
    """The four v2.25 content screens in their order (format_markers, item_identity, references, copied_examples) on a
    non-blank card text as stored: the first failing key, else None. ``bench`` is unused, as in the bound function."""
    require(isinstance(text, str) and text.strip() != '', 'The content screens read a non-blank card text')
    # BEGIN COPY of skillopt/execskill/v225_cards.py:169-201 (main-v10 card_violation after its length rule), verbatim
    # except the import of absent_findings, which names its package here. Pinned by COPIED_SOURCE_SHA256.
    if any(marker in text.lower() for marker in ('<answer', '</answer', '<action', '</action', '<calc', '</calc', '```')):
        return 'format_markers'
    paths = text
    for name in ('input.xlsx', 'output.xlsx'):
        if name in task_card:
            paths = re.sub(r'(?<![\w.])' + re.escape(name) + r'(?!\w)', '', paths)
    if ('task_id' in text.lower() or PATH_LIKE.search(text) or re.search(r'\.json|\.xlsx', paths, re.I)
            or any(re.search(r'(?<!\w)' + re.escape(str(key)) + r'(?!\w)', text, re.I) for key in practice_ids if str(key))):
        return 'item_identity'
    from skillopt.execskill.engineer import absent_findings
    public = task_card + '\n' + format_block
    corpora = corpus.values() if isinstance(corpus, dict) else corpus if isinstance(corpus, (tuple, list)) else (corpus,)
    if any(c is not None and absent_findings(text, c, public) for c in corpora):
        return 'references'
    # Shown references supplement the run-slice corpora (including rendered sheet values).
    tokens, known = leakage.normalize(text).split(), leakage.normalize(public).split()
    numbers = set(leakage._numbers(text)) - set(leakage._numbers(public))
    for example in shown:
        for value in _reference_values(example.get('reference')):
            phrase = leakage.normalize(value).split()
            if phrase and (len(phrase) >= 2 or len(phrase[0]) >= leakage.LEAK_MIN_SINGLE_WORD):
                if any(tokens[i:i + len(phrase)] == phrase for i in range(len(tokens) - len(phrase) + 1)) and not any(
                        known[i:i + len(phrase)] == phrase for i in range(len(known) - len(phrase) + 1)):
                    return 'references'
            numeric = leakage._numeric(value)
            if numeric is not None and leakage._significant(numeric) >= leakage.LEAK_MIN_SIGNIFICANT_DIGITS:
                if leakage._value(numeric) in numbers:
                    return 'references'
    grams = leakage._grams(tokens) - leakage._grams(known)
    if any(grams & leakage._grams(leakage.normalize(str(example.get(key, ''))).split())
           for example in shown for key in ('view', 'reply')):
        return 'copied_examples'
    return None
    # END COPY


def card_screen(text, *, bench, corpus, shown, task_card, format_block, practice_ids) -> dict:
    """{'violation': None | 'length' | a content key, 'chars': content characters, 'bullets': bullet lines}. The length
    rule comes first: no text, more than CARD_HARD_CHARS content characters or more than CARD_MAX_BULLETS bullet
    lines is 'length'; any other text goes, as stored, through the four content screens."""
    chars, bullets = content_chars(text), bullet_count(text)
    if chars == 0 or chars > CARD_HARD_CHARS or bullets > CARD_MAX_BULLETS:
        violation = 'length'
    else:
        violation = content_violation(text, bench=bench, corpus=corpus, shown=shown, task_card=task_card,
                                      format_block=format_block, practice_ids=practice_ids)
    return {'violation': violation, 'chars': chars, 'bullets': bullets}


def _count(value):
    return type(value) is int and value >= 0


def retry_text(seen, *, room) -> str:
    """The sentence appended (after two newlines) to the first user message for the second attempt; ``seen`` is the
    first attempt's ``card_screen`` result. A content key gets the v2.25 sentence. 'length' names the measured cause:
    no text, or the content characters, the told target and how many to cut, and/or the bullet points and how many to
    merge or remove (both causes joined, length first). The detailed sentence is used only when it fits in ``room``
    characters (the writer's input ceiling minus the first message and the two newlines), else the v2.25 'length'
    sentence, for which the examples' reserve always leaves room."""
    violation = seen.get('violation') if isinstance(seen, dict) else None
    require(type(violation) is str and violation in RETRY_SHORT and _count(seen.get('chars'))
            and _count(seen.get('bullets')) and type(room) is int, 'A retry follows a screen failure')
    if violation != 'length':
        return RETRY_FRAME.format(reason=RETRY_SHORT[violation])
    chars, bullets, target = seen['chars'], seen['bullets'], format(CARD_TOLD_CHARS, ',')
    if chars == 0:
        reason = REASON_NO_TEXT.format(target=target, max_bullets=CARD_MAX_BULLETS)
    else:
        causes = []
        if chars > CARD_HARD_CHARS:
            causes.append(REASON_TOO_LONG.format(chars=format(chars, ','), target=target,
                                                 cut=format(chars - CARD_TOLD_CHARS, ',')))
        if bullets > CARD_MAX_BULLETS:
            causes.append(REASON_TOO_MANY_BULLETS.format(bullets=bullets, max_bullets=CARD_MAX_BULLETS,
                                                         extra=bullets - CARD_MAX_BULLETS))
        require(causes, 'A length failure names its measured cause')
        reason = REASON_JOIN.join(causes)
    detailed = RETRY_FRAME.format(reason=reason)
    return detailed if len(detailed) <= room else RETRY_FRAME.format(reason=RETRY_SHORT['length'])


def copied_source() -> str:
    """The lines ``content_violation`` copies, as the BOUND ``v225_cards.card_violation`` holds them (its source after
    the ``return 'length'`` line); their sha256 must equal ``COPIED_SOURCE_SHA256``. Empty when that line is missing."""
    lines = inspect.getsource(v225_cards.card_violation).splitlines(keepends=True)
    ends = [i for i, line in enumerate(lines) if line.strip() == "return 'length'"]
    return ''.join(lines[ends[0] + 1:]) if ends else ''


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def pins() -> dict:
    """The pinned texts of this module: sha256 per retry constant (RETRY_SHORT per key), the limits record and the
    pin of the copied source."""
    return {'RETRY_FRAME': _sha256(RETRY_FRAME), 'REASON_TOO_LONG': _sha256(REASON_TOO_LONG),
            'REASON_TOO_MANY_BULLETS': _sha256(REASON_TOO_MANY_BULLETS), 'REASON_NO_TEXT': _sha256(REASON_NO_TEXT),
            'REASON_JOIN': _sha256(REASON_JOIN),
            'RETRY_SHORT': {key: _sha256(text) for key, text in RETRY_SHORT.items()},
            'LIMITS_RECORD': dict(LIMITS_RECORD), 'COPIED_SOURCE_SHA256': COPIED_SOURCE_SHA256}
