"""Learned, constants-only cards. Parsing and composition never execute source."""
from __future__ import annotations

import ast
import hashlib
import json
import re

from skillopt.continual_eval.core import require
from skillopt.coevo5 import leakage

VERSION = 'learned-card-v2-25'
MAX_CARD_CHARS = 3000
MAX_CARD_BULLETS = 12
MAX_CARDS = 5
MAX_CARD_EDITS = 4
CARD_JOIN = '\n\n'
CARD_ROUNDS = 3
CARD_WRITER_INPUT_CHARS = 120000
CARD_ACCEPT_ITEMS = {'searchqa': 60, 'officeqa': 32, 'zebralogic': 40, 'spreadsheetbench': 36}
CARD_CONFIRM_ITEMS = 40
BENCHES = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld')

CARD_WRITE_SYSTEM = (
    'You write the instruction card (a "Skill") that is placed in the system prompt of another '
    'language model which solves tasks of one kind; the fixed answer-format block shown to you is always placed after your '
    'card, unchanged. You are given the public description of the task kind, that format block, the card the solver currently '
    'receives (possibly empty), and examples of the solver\'s attempts on practice tasks of this kind with their scored outcome '
    '(for failed attempts also the reference answer).\n\nWrite the guidance that will most improve the solver on NEW tasks of '
    'this kind: what to pay attention to, how to use the supplied material, which recurring mistakes the examples show and how '
    'to avoid them, and how to decide when unsure. Keep it general for the task kind. Never quote or copy an example\'s text, '
    'names, numbers, identifiers or reference answers, and never refer to a specific example: the card is checked against the '
    'examples and their references and is rejected if it contains any of them. Do not restate or change the answer format, and '
    'do not write answer, action or calc tags or code fences: the format block owns the output contract.\n\nOutput only the card '
    'text in plain Markdown, at most 12 bullet points and at most 3,000 characters, with no preamble and no closing remark.'
)
CARD_REVISE_SYSTEM = (
    'You revise the instruction card (a "Skill") that is placed in the system prompt of another '
    'language model which solves tasks of one kind; the fixed answer-format block shown to you is always placed after your '
    'card, unchanged. You are given the public description of the task kind, that format block, your previous card, the counts '
    'of its test on practice tasks (tasks it fixed and broke, the rule it had to meet and the clause it missed), and examples of '
    'the solver\'s attempts WITH your previous card on practice tasks, with their scored outcome (for failed attempts also the '
    'reference answer).\n\nRevise the card so that it fixes the recurring failures without losing what worked. Keep it general '
    'for the task kind. Never quote or copy an example\'s text, names, numbers, identifiers or reference answers, and never '
    'refer to a specific example: the card is checked against the examples and their references and is rejected if it contains '
    'any of them. Do not restate or change the answer format, and do not write answer, action or calc tags or code fences: the '
    'format block owns the output contract.\n\nOutput only the revised card text in plain Markdown, at most 12 bullet points and '
    'at most 3,000 characters, with no preamble and no closing remark.'
)
CARD_RETRY = ('Your reply could not be used as the card: {reason}. Reply again with only the card text, '
              'following every rule of the system message.')
RETRY_REASONS = {
    'length': 'it is empty, longer than 3,000 characters or has more than 12 bullet points',
    'format_markers': 'it contains an answer, action or calc tag or a code fence',
    'item_identity': 'it contains a task identifier or a file path',
    'references': 'it contains a reference answer or a value from one',
    'copied_examples': 'it copies text from an example',
}
ZEBRA_TASK_CARD = (
    'Task kind: logic grid puzzles (the ZebraLogic benchmark): houses in a row, numbered from left to right, each with '
    'one value of every listed characteristic, every value used by exactly one house; numbered clues constrain the assignment, '
    'and exactly one assignment satisfies them all.\nInput the solver receives: one user message holding the benchmark\'s fixed '
    'template: a small worked example with its answer, the puzzle to solve (5 or 6 houses, 2 to 6 characteristics), and the '
    'instruction to present the reasoning and the solution in a JSON object with the fields "reasoning" and "solution" (each '
    'house mapped to its value of every characteristic).\nFixed instructions the solver always receives: "Solve the supplied '
    'task using only the supplied public information." and the template\'s own instruction.\nScoring (public metric): the '
    'solution is parsed from the reply\'s JSON object and compared with the reference cell by cell; the puzzle counts as solved '
    'only when every cell matches; a reply whose solution cannot be parsed counts as wrong.'
)


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def card_source(home, route, text):
    require(home in BENCHES and route in BENCHES and isinstance(text, str), 'A card has registered home, route and text')
    return "V225_CARD = 'learned-card-v2-25'\nCARD_HOME = %r\nCARD_ROUTE = %r\nCARD_TEXT = %r\n" % (home, route, text)


def parse_source(source):
    """Only the exact four-assignment template is admitted, never evaluated code."""
    if not isinstance(source, str):
        return None
    try:
        nodes = ast.parse(source).body
        names = ('V225_CARD', 'CARD_HOME', 'CARD_ROUTE', 'CARD_TEXT')
        if len(nodes) != len(names) or any(not isinstance(n, ast.Assign) or len(n.targets) != 1
                or not isinstance(n.targets[0], ast.Name) or n.targets[0].id != key
                for n, key in zip(nodes, names)):
            return None
        values = dict(zip(names, (ast.literal_eval(n.value) for n in nodes)))
        home, route, text = (values[k] for k in names[1:])
        if values['V225_CARD'] != VERSION or home not in BENCHES or route not in BENCHES or not isinstance(text, str):
            return None
        if source != card_source(home, route, text):
            return None
        return {'home': home, 'route': route, 'text': text}
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def metadata(procedure):
    from .policy import POLICY_VERSION_V225
    if getattr(procedure, 'policy_version', None) != POLICY_VERSION_V225:
        return None
    return parse_source(getattr(procedure, 'source', None))


def is_card(procedure):
    return metadata(procedure) is not None


card_metadata = metadata


def make_card(home, text, *, route=None, k=1, round=1, ordinal=None, evidence='engineering_fixture', writer_sha256=None):
    from .package import Procedure
    from .profiles import SUPPORTED_BENCHES
    from .policy import POLICY_VERSION_V225
    route = home if route is None else route
    return Procedure(id=f'p-{home}-{k}-{100 + round if ordinal is None else ordinal}', origin=home,
        description='Learned instruction card (v2.25)', hooks=(), source=card_source(home, route, text),
        evidence=evidence, excluded_benches=tuple(b for b in SUPPORTED_BENCHES if b != route),
        lineage={'parent': None, 'revises': None, 'engineer_call': writer_sha256}, policy_version=POLICY_VERSION_V225)


def compose(bench, base_card, package):
    require(isinstance(base_card, str), 'The base card is text')
    card = package.card_for(bench)
    if base_card == '' or card is None:
        return base_card
    return metadata(card)['text'] + CARD_JOIN + base_card


def card_edit(edit):
    return any(p is not None and is_card(p) for p in (edit.old, edit.new))


def _reference_values(value):
    if isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        try:
            decoded = json.loads(value)
        except ValueError:
            pass
        else:
            if isinstance(decoded, (dict, list)):
                yield from _reference_values(decoded)
                return
    if isinstance(value, dict):
        for part in value.values():
            yield from _reference_values(part)
    elif isinstance(value, (list, tuple)):
        for part in value:
            yield from _reference_values(part)
    elif value is not None and not isinstance(value, bool):
        yield str(value)


# A path has a root, a drive, a backslash or a file extension. Plain word/word, as in a/an/the or city/state, is ordinary English.
PATH_LIKE = re.compile(r'(?<![\w/.])(?:\.{1,2}/|~/|/)[\w.-]+|[A-Za-z]:\\|\w\\\w|://|\b[\w.-]+/[\w./-]*\.\w{1,5}\b')


def card_violation(text, *, bench, corpus, shown, task_card, format_block, practice_ids):
    """Ordered deterministic checks over caller-provided practice evidence only."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CARD_CHARS or sum(
            bool(re.match(r'^\s*(?:[-*+•]|\d+[.)])\s+', line)) for line in text.splitlines()) > MAX_CARD_BULLETS:
        return 'length'
    if any(marker in text.lower() for marker in ('<answer', '</answer', '<action', '</action', '<calc', '</calc', '```')):
        return 'format_markers'
    paths = text
    for name in ('input.xlsx', 'output.xlsx'):
        if name in task_card:
            paths = re.sub(r'(?<![\w.])' + re.escape(name) + r'(?!\w)', '', paths)
    if ('task_id' in text.lower() or PATH_LIKE.search(text) or re.search(r'\.json|\.xlsx', paths, re.I)
            or any(re.search(r'(?<!\w)' + re.escape(str(key)) + r'(?!\w)', text, re.I) for key in practice_ids if str(key))):
        return 'item_identity'
    from .engineer import absent_findings
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


def engineer_sentence():
    from .v222_cards import ENGINEER_SENTENCE
    old = 'Main-v8 instructions are routed note segments in the package.'
    new = ("Main-v9: the bench's instruction card was written by a separate writer from practice examples and judged by "
           'the same rules before these rounds; it is fixed for this step, reaches this bench only, and is shown in card '
           'followed by the fixed format block. Procedures must add what the card cannot do (computed, situation-specific '
           'checks and state), never restate it.')
    require(ENGINEER_SENTENCE.count(old) == 1 and ENGINEER_SENTENCE.count('Format blocks are fixed and cannot be edited.') == 1,
            'The two inherited engineer sentences each occur exactly once')
    priority = ("Coverage does not outrank a complete solution: when an item's whole answer can be computed and verified "
                'from its public input, propose that program first and keep repairing it across rounds, even at low '
                'coverage. A note that does not settle the answer leaves the answering model to re-solve, so its fixed '
                'and broken counts may only measure re-run noise; do not treat a near miss from such a note as progress.')
    return ENGINEER_SENTENCE.replace(old, new).replace('Format blocks are fixed and cannot be edited.',
        'The card and the format block are fixed and cannot be edited by you.') + '\n' + priority + '\n'


def prompt_pins():
    values = {'CARD_WRITE_SYSTEM': CARD_WRITE_SYSTEM, 'CARD_REVISE_SYSTEM': CARD_REVISE_SYSTEM,
              'CARD_RETRY': CARD_RETRY, 'ZEBRA_TASK_CARD': ZEBRA_TASK_CARD,
              'ENGINEER_SENTENCE_V225': engineer_sentence(),
              **{'CARD_RETRY_' + key: text for key, text in RETRY_REASONS.items()}}
    return {key: {'text': text, 'sha256': sha256(text)} for key, text in values.items()}


ENGINEER_SENTENCE_V225 = engineer_sentence()
