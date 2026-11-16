"""OfficeQA made items: fixed code for derivations, number twins and new questions (no model call, no file access).

An OfficeQA practice item is ``{public: {context, question}, private: {answer}}``. A DERIVATION ("trace") says how
an answer follows from the document:

    {"values":  [{"name": "v1", "literal": "10,102", "quote": "totaled $10,102 million", "kind": "data"}, ...],
     "answers": [{"expression": "v1 * 1000000", "decimals": 0}, ...]}

``literal`` is a number exactly as printed in the document, ``quote`` a verbatim piece of the document holding it,
``kind`` "data" (a reported quantity) or "selector" (a year, a page, row or table number: something that only says
what to read). Optional ``steps`` [{"name", "expression"}] name intermediate results (a mean used several times).
One expression per number of the answer, evaluated by the bank's evaluator (``calc``: exact for + - * / and whole
powers, certified for sqrt, ln, the standard deviations, geomean, corr and fractional powers); ``decimals`` 0-6 is
the rounding the question asks for (half away from zero), None means the exact value.

- ``anchor``: a derivation counts only when its computed answer is judged equal to the item's REFERENCE answer by
  the benchmark's own judge ("reproduce the reference first", the rule of ``generators/officeqa.py``). That judge
  is string equality after a light normalisation, with NO numeric tolerance: a made answer is therefore written the
  way the references are (plain digits, the decimals the question fixes, a '%' only when the reference has one) and
  is refused when it would hang on a rounding tie or end in a zero after the point.
- ``make_twin``: every token occurrence of a changed data literal is replaced in the document (one new literal per
  old literal, so a number printed twice stays consistent), the answer is recomputed, and the twin is kept only when
  the OLD answer is judged wrong for it (a twin must tell reading from recalling).
- ``check_new_question``: a writer's question with its derivation; the answer is computed here, never taken from
  the writer.

- the CODE RUBRIC of an item (owner 2026-11-13: "造题的时候可以写明一个code rubric") is its derivation plus coded
  mistakes: ``rubric`` computes, beside the answer, the answer each registered mistake WOULD give (operands
  swapped, an item-specific wrong reading the writer named, ...), and ``classify`` names the mistake a wrong reply
  matches (rounding, unit scale, percent form, sign, order of the parts, a value read but not computed with, a
  registered mistake) or ``other``. The benchmark's judge alone decides right and wrong; the rubric only says where
  a wrong reply went wrong, for the diagnosis step.

Every refusal is a ``Drop(reason)`` with a reason of ``REASONS``; the callers count them.
"""
from __future__ import annotations

import itertools
import re
from fractions import Fraction

from . import calc

REASONS = ('shape', 'not_numeric', 'not_found', 'value_shape', 'value_name', 'literal_unparsable', 'quote_shape',
           'quote_not_in_document', 'literal_not_in_quote', 'answer_shape', 'decimals', 'expression', 'unknown_name',
           'no_document_value', 'not_terminating', 'reference_not_reproduced', 'no_data_value', 'nothing_to_change',
           'answer_unchanged', 'question_shape', 'question_repeats_parent', 'question_repeats_sibling',
           'answer_in_question', 'derivation_repeats_parent', 'constant_answer', 'value_without_effect',
           'rounding_tie', 'trailing_zero', 'constant_from_document', 'percent_sign_asked')
MAX_VALUES = 40                   # a sum over the lines of a table needs many (probe 2026-11-13: 28 agencies)
MAX_STEPS = 20
MAX_ANSWERS = 4
QUOTE_CHARS = (8, 200)
QUESTION_CHARS = (60, 1500)
KINDS = ('data', 'selector')
PERTURB_RANGE = (0.03, 0.20)      # relative change of a data literal, either direction
MAX_LITERAL_OCCURRENCES = 6       # a literal printed more often is too generic to change safely
TWIN_DRAWS = 12                   # redraws of one twin's changes when the answer is a tie, ends in 0 or stays
REPEAT_JACCARD = 0.80             # word-set overlap at or above which two questions count as the same question
MIN_LEAK_CHARS = 3                # an answer string shorter than this is not searched in the question
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,31}')
LITERAL = re.compile(r'(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?')  # unsigned: digits, thousands commas, decimal part
WORD = re.compile(r'[a-z0-9]+')


class Drop(Exception):
    """A derivation, twin or question the fixed code refuses; ``reason`` is one of ``REASONS``."""

    def __init__(self, reason, detail=''):
        assert reason in REASONS, reason
        super().__init__(reason + (': ' + str(detail) if detail else ''))
        self.reason, self.detail = reason, str(detail)


def squash(text):
    """Whitespace runs as one blank: the form in which a quote is searched in the document."""
    return ' '.join(text.split())


def token_pattern(literal):
    """The literal as a whole number token: not inside a longer number (no digit before or after, no digit joined
    by a comma or point on either side)."""
    return re.compile(r'(?<!\d)(?<!\d[.,])' + re.escape(literal) + r'(?!\d)(?![.,]\d)')


PROTECTED = re.compile(r'^(?:### |Source URL:|The following content is pre-parsed)')
PAGE = re.compile(r'^### (\S+) page (\d+)\s*$', re.M)


def body_lines(context):
    """(line, is_body) for every line of a context: page headers (``### <file> page <N>``), ``Source URL:`` lines
    and the evidence note are NOT body -- their digits name the source and never change or count."""
    return [(line, PROTECTED.match(line) is None) for line in context.split('\n')]


def count_tokens(literal, context):
    pattern = token_pattern(literal)
    return sum(len(pattern.findall(line)) for line, body in body_lines(context) if body)


def pages_of(context):
    """{(source file, page number)} named by the context's page headers."""
    return {(name, int(page)) for name, page in PAGE.findall(context)}


def officeqa_judge(prediction, gold):
    """The benchmark's own comparison (``skillopt/envs/officeqa/evaluator.py``): equal after its normalisation, no
    numeric tolerance. True for a match."""
    from skillopt.envs.officeqa.evaluator import exact_match
    return exact_match(prediction, gold) == 1.0


def looks_like_year(literal):
    return bool(re.fullmatch(r'\d{4}', literal)) and 1700 <= int(literal) <= 2100


def _names_used(expression):
    try:
        return calc.names(expression)
    except calc.CalcError as failure:
        raise Drop('expression', failure.reason) from None


def constants(expression):
    """The number literals written in an expression, as written."""
    try:
        return calc.literals(expression)
    except calc.CalcError as failure:
        raise Drop('expression', failure.reason) from None


def document_number(constant, context):
    """True when a constant of an expression is really a number READ from the document: three or more significant
    digits, not a power of ten, and printed in the document body as a token (with or without thousands commas).
    Such a number must be a value with its quote, or a twin could not change it and the rubric could not name it."""
    digits = re.sub(r'\D', '', constant).strip('0')
    if len(re.sub(r'\D', '', constant).lstrip('0')) < 3 or digits in ('', '1'):
        return False
    whole, _, part = constant.partition('.')
    forms = {constant, '{:,}'.format(int(whole)) + ('.' + part if part else '')}
    return any(count_tokens(form, context) for form in forms)


def operations(trace):
    """The arithmetic and the functions a derivation uses, as sorted labels (a fidelity feature)."""
    found = set()
    for row in trace.get('steps', []) + trace['answers']:
        found.update(calc.operations(row['expression']))
    return sorted(found)


def check_trace(trace, context):
    """The derivation in normal form, or ``Drop``. Tolerant where nothing depends on it (unknown keys are ignored, an
    unknown kind counts as data, values no expression uses are left out, a year-like literal is a selector whatever
    the writer said); strict on what the answer rests on (every literal is a number token of its quote, every quote
    is in the document body, every expression parses over the names defined before it, no number of the document
    hides as a constant)."""
    if not isinstance(trace, dict):
        raise Drop('shape')
    for flag in ('not_numeric', 'not_found'):
        if trace.get(flag) is True:
            raise Drop(flag)
    values, answers, steps = trace.get('values'), trace.get('answers'), trace.get('steps') or []
    if not (isinstance(values, list) and 1 <= len(values) <= MAX_VALUES and isinstance(steps, list)
            and len(steps) <= MAX_STEPS and isinstance(answers, list) and 1 <= len(answers) <= MAX_ANSWERS):
        raise Drop('shape')
    document = squash('\n'.join(line for line, body in body_lines(context) if body))
    kept, names = [], set()
    for value in values:
        if not isinstance(value, dict):
            raise Drop('value_shape')
        name, literal, quote = value.get('name'), value.get('literal'), value.get('quote')
        if not (isinstance(name, str) and NAME.fullmatch(name) and name not in calc.FUNCTIONS and name not in names):
            raise Drop('value_name', name)
        if not (isinstance(literal, str) and LITERAL.fullmatch(literal)):
            raise Drop('literal_unparsable', literal)
        if not (isinstance(quote, str) and QUOTE_CHARS[0] <= len(quote) <= QUOTE_CHARS[1]):
            raise Drop('quote_shape', name)
        if squash(quote) not in document:
            raise Drop('quote_not_in_document', name)
        if not token_pattern(literal).search(quote):
            raise Drop('literal_not_in_quote', name)
        kind = value.get('kind') if value.get('kind') in KINDS else 'data'
        names.add(name)
        kept.append({'name': name, 'literal': literal, 'quote': quote,
                     'kind': 'selector' if looks_like_year(literal) else kind,
                     'occurrences': count_tokens(literal, context)})

    def expression_of(row, known):
        if not (isinstance(row, dict) and isinstance(row.get('expression'), str) and row['expression'].strip()):
            raise Drop('answer_shape')
        used = _names_used(row['expression'])
        if not used <= known:
            raise Drop('unknown_name', sorted(used - known))
        for constant in constants(row['expression']):
            if document_number(constant, context):
                raise Drop('constant_from_document', constant)
        return row['expression'].strip(), sorted(used)

    normal_steps, reach = [], {name: {name} for name in names}      # the document values a name rests on
    for step in steps:
        name = step.get('name') if isinstance(step, dict) else None
        if not (isinstance(name, str) and NAME.fullmatch(name) and name not in calc.FUNCTIONS and name not in reach):
            raise Drop('value_name', name)
        expression, used = expression_of(step, set(reach))
        reach[name] = set().union(*[reach[other] for other in used]) if used else set()
        normal_steps.append({'name': name, 'expression': expression, 'names': used})
    normal, used_values = [], set()
    for answer in answers:
        expression, used = expression_of(answer, set(reach))
        decimals = answer.get('decimals')
        if decimals is not None and not (type(decimals) is int and 0 <= decimals <= calc.MAX_DECIMALS):
            raise Drop('decimals', decimals)
        used_values |= set().union(*[reach[other] for other in used]) if used else set()
        normal.append({'expression': expression, 'decimals': decimals, 'names': used})
    kept = [value for value in kept if value['name'] in used_values]
    if not kept:
        raise Drop('no_document_value')
    live = {name for answer in normal for name in answer['names']}
    for step in reversed(normal_steps):                              # a step no answer reaches is left out
        if step['name'] in live:
            live |= set(step['names'])
    normal_steps = [step for step in normal_steps if step['name'] in live]
    return {'values': kept, 'steps': normal_steps, 'answers': normal}


def evaluate_trace(trace, changes=None, bindings=None):
    """[(value, exact)] of the answer parts: the values (a twin's ``changes`` {old literal: new literal} applied,
    ``bindings`` {name: Fraction} overriding), then the steps in order, then the answers."""
    changes = changes or {}
    try:
        bound = {value['name']: calc.number(changes.get(value['literal'], value['literal'])) for value in trace['values']}
        bound.update(bindings or {})
        for step in trace.get('steps', []):
            # an inexact step stays a calc.Approx in ``bound``: its enclosure goes into every expression that uses it
            bound[step['name']], _ = calc.evaluate(step['expression'], bound)
        return [calc.evaluate(answer['expression'], bound) for answer in trace['answers']]
    except calc.CalcError as failure:
        raise Drop('expression', failure.reason) from None


def compute_answers(trace, changes=None):
    """The answer strings of a normal-form derivation; ``changes`` {old literal: new literal} gives a twin's."""
    out = []
    for (value, exact), answer in zip(evaluate_trace(trace, changes), trace['answers']):
        try:
            out.append(calc.text(value, answer['decimals'], exact))
        except calc.CalcError as failure:
            raise Drop(failure.reason if failure.reason in ('not_terminating', 'rounding_tie') else 'expression',
                       failure.detail) from None
    return out


def exact_values(trace, changes=None, bindings=None):
    """The value of every answer part before rounding, as Fractions (an inexact one: the midpoint of its enclosure,
    good to some 50 digits for the well-conditioned expressions a derivation holds)."""
    return [value for value, _ in evaluate_trace(trace, changes, bindings)]


def check_effect(trace):
    """Every value must matter: raising it alone by a tenth changes some answer part. A value without effect is a
    decoration the answer does not rest on (``value_without_effect``)."""
    base = exact_values(trace)
    for value in trace['values']:
        moved = calc.number(value['literal']) * Fraction(11, 10) + Fraction(1, 7)
        try:
            same = exact_values(trace, bindings={value['name']: moved}) == base
        except Drop:
            continue                                                 # the moved value left a function's domain
        if same:
            raise Drop('value_without_effect', value['name'])
    return trace


def check_rounding(trace, changes=None):
    """A made answer must not hang on a rounding convention: no tie at the requested place (an exact tie, or an
    inexact value within the evaluator's margin of one) and no trailing zero after the point (the rules of
    scripts/generate_officeqa_tasks.py, 2026-10-14)."""
    for (value, exact), answer in zip(evaluate_trace(trace, changes), trace['answers']):
        decimals = answer['decimals']
        if decimals is None:
            continue
        if calc.near_tie(value, decimals, Fraction(0) if exact else calc.TIE_MARGIN):
            raise Drop('rounding_tie')
        if decimals and calc.text(value, decimals, exact).endswith('0'):
            raise Drop('trailing_zero')


def gold_text(answers, suffix=''):
    """One number as it is (with the reference's '%' when it carries one); several as the bracket list the
    benchmark's multi-part references use ('[a, b]': the judge deletes the brackets and the comma, so the blank
    after the comma is what separates the parts)."""
    return answers[0] + suffix if len(answers) == 1 else '[' + ', '.join(answers) + ']'


def anchor(trace, context, reference, judge):
    """(normal-form derivation, its computed answer) when the benchmark's judge takes the computed answer for the
    REFERENCE answer; ``Drop`` otherwise. ``judge(prediction, gold)`` is the benchmark's judge, True for correct. A
    part that is an exact rounding tie is tried both ways (the reference's convention is not known)."""
    normal = check_trace(trace, context)
    parts = []
    for (value, exact), answer in zip(evaluate_trace(normal), normal['answers']):
        try:
            parts.append(calc.candidates(value, answer['decimals'], exact))
        except calc.CalcError as failure:
            raise Drop(failure.reason if failure.reason in ('not_terminating', 'rounding_tie') else 'expression',
                       failure.detail) from None
    suffix = '%' if len(parts) == 1 and reference.strip().endswith('%') else ''
    first = None
    for choice in itertools.islice(itertools.product(*parts), 16):
        computed = gold_text(list(choice), suffix)
        first = first or computed
        if judge(computed, reference) is True:
            normal['suffix'] = suffix
            return normal, computed
    raise Drop('reference_not_reproduced', first)


# ---- number twins ------------------------------------------------------------------------------------------------
def perturb_literal(literal, rng):
    """A different number in the same printed form (same decimal places, thousands commas kept, positive), changed
    by PERTURB_RANGE in either direction; small counts move by 1-3. None when the literal is zero."""
    match = LITERAL.fullmatch(literal)
    whole, places = match.group(1), len(match.group(2) or '')
    old = int(whole.replace(',', '') + (match.group(2) or ''))
    if old == 0:
        return None
    for _ in range(40):
        factor = 1 + rng.choice((-1, 1)) * rng.uniform(*PERTURB_RANGE)
        new = int(round(old * factor))
        if new == old:
            new = old + rng.choice((-1, 1)) * rng.randint(1, 3)
        if new <= 0 or new == old:
            continue
        digits = str(new).rjust(places + 1, '0')
        left, right = (digits[:-places], digits[-places:]) if places else (digits, '')
        if ',' in whole:
            left = '{:,}'.format(int(left))
        return left + ('.' + right if places else '')
    return None


def replace_literals(context, changes):
    """Every token occurrence of each old literal in the document BODY replaced by its new one in ONE pass over the
    original text (a single alternation, longest literal first, with a callback): nothing that was written is read
    again, neither a new literal nor a marker (review 2026-11-13: the earlier two-pass form wrote numbered
    markers, and with more than ten changes a later literal such as 10 could rewrite the marker of change 10).
    Page headers and source URLs stay as they are."""
    ordered = sorted(changes, key=lambda literal: (-len(literal), literal))
    if not ordered:
        return context
    pattern = re.compile(r'(?<!\d)(?<!\d[.,])(?:' + '|'.join(re.escape(old) for old in ordered) + r')(?!\d)(?![.,]\d)')
    return '\n'.join(pattern.sub(lambda match: changes[match.group(0)], line) if body else line
                     for line, body in body_lines(context))


def choose_changes(trace, context, question, rng):
    """{old literal: new literal} for the data literals that can change safely: not a selector's literal, not named
    in the question, at least two digits, printed at most MAX_LITERAL_OCCURRENCES times, and the new literal printed
    nowhere in the document or the question."""
    selectors = {value['literal'] for value in trace['values'] if value['kind'] == 'selector'}
    data = [value for value in trace['values'] if value['kind'] == 'data' and value['literal'] not in selectors]
    if not data:
        raise Drop('no_data_value')
    changes = {}
    for value in data:
        old = value['literal']
        if old in changes or value['occurrences'] > MAX_LITERAL_OCCURRENCES or token_pattern(old).search(question):
            continue
        if len(re.sub(r'\D', '', old)) < 2:
            continue
        for _ in range(20):
            new = perturb_literal(old, rng)
            if (new and new not in changes and new not in changes.values()
                    and not token_pattern(new).search(context) and not token_pattern(new).search(question)):
                changes[old] = new
                break
    if not changes:
        raise Drop('nothing_to_change')
    return changes


def make_twin(context, question, trace, old_gold, rng, judge):
    """(new context, new answer, changes) of one number twin of an ANCHORED item, or ``Drop``. The question is the
    parent's, unchanged. The twin is refused when the parent's answer would still be judged correct for it."""
    failure = None
    for _ in range(TWIN_DRAWS):
        changes = choose_changes(trace, context, question, rng)
        try:
            check_rounding(trace, changes)
            gold = gold_text(compute_answers(trace, changes), trace.get('suffix', ''))
        except Drop as refused:
            failure = refused
            continue
        if judge(old_gold, gold) is not False:
            failure = Drop('answer_unchanged', gold)
            continue
        return replace_literals(context, changes), gold, changes
    raise failure


# ---- new questions -----------------------------------------------------------------------------------------------
PERCENT_WORD = re.compile(r'percent|per cent|%', re.I)
_SIGN = r'(?:percent(?:age)?|%)\s*(?:sign|symbol)s?\b'
SIGN_MENTION = re.compile(_SIGN, re.I)
SIGN_ASKED = re.compile(r'(?:includ\w*|with|add\w*|append\w*|show\w*|keep\w*|follow\w* by|end\w* (?:in|with)|use\w*)\s+'
                        r'(?:the\s+|a\s+|its\s+)?' + _SIGN, re.I)
SIGN_REFUSED = re.compile(r'(?:\bno\b|\bnot\b|without|omit\w*|exclud\w*|drop\w*|remov\w*)[^.;?!]{0,40}?' + _SIGN, re.I)
SIGN_EXAMPLE = re.compile(r'(?:e\.g\.|for example|for instance|such as|like|i\.e\.|write|answer)[^;?!]{0,30}?\d\s?%', re.I)
FORM_SENTENCES = ('Report only the value, with no percent sign.', 'Report only the values, with no percent sign.')


def percent_form(question):
    """What a question says about the percent sign of its answer: ``none`` (it names no percent), ``add`` (it names a
    percent and says nothing about the sign: fixed code adds the form sentence), ``stated`` (it already says to
    leave the sign out) or ``conflict`` (it asks for the sign, shows an answer written with it, or mentions the sign
    in a way fixed code cannot read). A made answer never carries '%' (BANK-PILOT B6), so a ``conflict`` question
    would refuse the very answer it asks for and is dropped."""
    if not PERCENT_WORD.search(question):
        return 'none'
    if SIGN_ASKED.search(question) or SIGN_EXAMPLE.search(question):
        return 'conflict'
    if SIGN_MENTION.search(question):
        return 'stated' if SIGN_REFUSED.search(question) else 'conflict'
    return 'add'


def form_sentence(question, parts):
    """The sentence fixed code adds to a made question that names a percent without saying how the answer is
    written; '' when there is nothing to add. The judge compares strings: in the pilot of 2026-11-13, 99 of the
    checker's 230 wrong replies on new questions differed from the made answer by the percent sign alone, because
    165 of 311 questions named a percent and 8 of them said how to write it. The wording is the real items' own
    ("only report the value with no percent sign")."""
    return FORM_SENTENCES[0 if parts == 1 else 1] if percent_form(question) == 'add' else ''


def words(text):
    return set(WORD.findall(text.lower()))


def jaccard(first, second):
    a, b = words(first), words(second)
    return len(a & b) / len(a | b) if a | b else 1.0


def derivation_key(trace):
    """What a derivation computes from: its literals and expressions (order-free), for 'same question' checks."""
    return (tuple(sorted(value['literal'] for value in trace['values'])),
            tuple(sorted(re.sub(r'\s+', '', row['expression']) for row in trace.get('steps', []) + trace['answers'])))


def check_new_question(entry, context, *, parent_question, parent_trace=None, siblings=()):
    """(question, normal-form derivation, computed answer) of one writer entry {question, values, answers}, or
    ``Drop``. ``siblings``: (question, derivation) pairs already kept for this document. The answer is computed
    here; an ``answer`` key in the entry is ignored. The returned question is the writer's, with the fixed sentence
    on the answer's form added where it names a percent (``form_sentence``)."""
    question = entry.get('question') if isinstance(entry, dict) else None
    if not (isinstance(question, str) and QUESTION_CHARS[0] <= len(question.strip()) <= QUESTION_CHARS[1]):
        raise Drop('question_shape')
    question = question.strip()
    normal = check_trace(entry, context)
    if not any(value['kind'] == 'data' for value in normal['values']):
        raise Drop('constant_answer')
    if jaccard(question, parent_question) >= REPEAT_JACCARD:
        raise Drop('question_repeats_parent')
    if parent_trace is not None and derivation_key(normal) == derivation_key(parent_trace):
        raise Drop('derivation_repeats_parent')
    for other_question, other_trace in siblings:
        if jaccard(question, other_question) >= REPEAT_JACCARD or derivation_key(normal) == derivation_key(other_trace):
            raise Drop('question_repeats_sibling')
    check_effect(normal)
    check_rounding(normal)
    answers = compute_answers(normal)
    for answer in answers:
        if len(answer) >= MIN_LEAK_CHARS and token_pattern(answer).search(question):
            raise Drop('answer_in_question', answer)
    if percent_form(question) == 'conflict':
        raise Drop('percent_sign_asked')
    sentence = form_sentence(question, len(answers))
    return question + (' ' + sentence if sentence else ''), normal, gold_text(answers)


# ---- the audit of a derivation -----------------------------------------------------------------------------------
def audit_verdict(found):
    """('accept' | 'refuse' | 'void', [what is marked wrong]) of an auditor's reply object. Accept needs the word AND
    no part marked wrong: a reply that says accept while it marks a value or the computation wrong is a refusal.
    Void: no object, or no verdict among the two words."""
    if not isinstance(found, dict) or found.get('verdict') not in ('accept', 'refuse'):
        return 'void', []
    rows = found.get('values') if isinstance(found.get('values'), list) else []
    wrong = [str(row.get('name'))[:40] for row in rows if isinstance(row, dict) and row.get('right') is False]
    computation = found.get('computation')
    if isinstance(computation, dict) and computation.get('right') is False:
        wrong.append('computation')
    return ('accept' if found['verdict'] == 'accept' and not wrong else 'refuse'), wrong


# ---- the code rubric: coded mistakes and the label of a wrong reply --------------------------------------------------
SCALES = {'percent_form': (2,), 'unit_scale': (3, 6, 9)}       # powers of ten a reply may be off by
MAX_SWAPS = 12                    # coded operand swaps per item (a sum of thirty values has hundreds of pairs)
ROUNDING_PLACES = range(0, 7)
NUMBER_IN_TEXT = re.compile(r'[-\u2212]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[-\u2212]?\.\d+')
LABELS = ('no_answer', 'part_count', 'format', 'order', 'rounding', 'percent_form', 'unit_scale', 'sign',
          'swapped_operands', 'read_not_computed', 'other')


def parse_numbers(text):
    """The numbers of a final answer text, in order, as Fractions (thousands commas and a leading sign read; units,
    currency and percent signs ignored). None when there is no number."""
    found = [Fraction(m.group().replace(',', '').replace('\u2212', '-')) for m in NUMBER_IN_TEXT.finditer(text or '')]
    return found or None


def _round(value, places):
    return calc.round_half_away(value, places)


def swapped(trace, changes=None):
    """{(first, second): exact values} with two data values exchanged, for every pair that changes the answer: the
    coded form of 'the right numbers in the wrong places' (base and comparison swapped, subtraction reversed)."""
    read = {value['name']: calc.number((changes or {}).get(value['literal'], value['literal']))
            for value in trace['values']}
    base, out = exact_values(trace, changes), {}
    for first, second in itertools.combinations(sorted(read), 2):
        if len(out) >= MAX_SWAPS:
            break
        try:
            values = exact_values(trace, changes, bindings={first: read[second], second: read[first]})
        except Drop:
            continue
        if values != base:
            out[(first, second)] = values
    return out


def rubric(trace, changes=None, mistakes=()):
    """The item's code rubric as plain data: the exact value and the requested decimals of every answer part, the
    values read from the document, and the answers of the coded mistakes -- operand swaps (fixed code) and the
    item-specific ``mistakes`` [{label, text, trace}] a writer named, each kept only when it evaluates and differs
    from the right answer. Fractions are written 'numerator/denominator'."""
    exact = exact_values(trace, changes)
    text = lambda values: [str(value) for value in values]
    # The rubric stores a value as one rational (an inexact one: the midpoint of its enclosure) and later rounds it
    # at every place of ROUNDING_PLACES to name a wrong reply. A coded mistake whose enclosure cannot settle one of
    # those roundings is left out: its midpoint could round the other way (second review 2026-11-13: 5/2 - sqrt(4)).
    settled = lambda values: not any(isinstance(value, calc.Approx) and calc.near_tie(value, places)
                                     for value in values for places in ROUNDING_PLACES)
    coded = [{'label': 'swapped_operands', 'text': 'the values %s and %s exchanged' % pair, 'values': text(values)}
             for pair, values in swapped(trace, changes).items() if settled(values)]
    for mistake in mistakes:
        try:
            values = exact_values(mistake['trace'], changes)
        except Drop:
            continue
        if len(values) == len(exact) and values != exact and settled(values):
            coded.append({'label': mistake['label'], 'text': mistake['text'], 'values': text(values)})
    return {'version': 'oqa-rubric-v1', 'exact': text(exact), 'decimals': [a['decimals'] for a in trace['answers']],
            'read': text(calc.number((changes or {}).get(v['literal'], v['literal'])) for v in trace['values']),
            'mistakes': coded}


def _part_label(reply, exact, decimals, read, mistakes, index):
    right = exact if decimals is None else _round(exact, decimals)
    if reply == right:
        return None
    if any(reply == _round(exact, places) for places in ROUNDING_PLACES) or reply == exact:
        return 'rounding'
    if reply == -right or reply == -exact:
        return 'sign'
    for label, powers in SCALES.items():
        for power in powers:
            for factor in (Fraction(10) ** power, Fraction(1, 10 ** power)):
                scaled = exact * factor
                if reply == scaled or any(reply == _round(scaled, places) for places in ROUNDING_PLACES):
                    return label
    for mistake in mistakes:
        wrong = Fraction(mistake['values'][index])
        if reply == wrong or any(reply == _round(wrong, places) for places in ROUNDING_PLACES):
            return mistake['label']
    if reply in read:
        return 'read_not_computed'
    return 'other'


def classify(reply_text, sheet):
    """The label of a reply the judge counted WRONG, from the item's rubric (``rubric``): ``no_answer``,
    ``part_count``, ``order`` (the right parts in another order), else the labels of the wrong parts joined by '+'
    in part order (each: rounding, sign, percent_form, unit_scale, a coded mistake's label, read_not_computed,
    other). A reply whose every part equals the rubric's answer is ``format``: the numbers are right and the judge,
    which compares normalised strings, refused the way they are written (a trailing zero, a unit word, a missing or
    extra '%', brackets for a negative)."""
    reply = parse_numbers(reply_text)
    if reply is None:
        return 'no_answer'
    exact = [Fraction(value) for value in sheet['exact']]
    if len(reply) != len(exact):
        return 'part_count'
    right = [value if places is None else _round(value, places) for value, places in zip(exact, sheet['decimals'])]
    if len(exact) > 1 and reply != right and sorted(reply) == sorted(right):
        return 'order'
    read = {Fraction(value) for value in sheet['read']}
    labels = [_part_label(reply[i], exact[i], sheet['decimals'][i], read, sheet['mistakes'], i)
              for i in range(len(exact))]
    wrong = [label for label in labels if label is not None]
    return '+'.join(wrong) if wrong else 'format'


# ---- fidelity features -------------------------------------------------------------------------------------------
def features(question, gold, trace=None, context=None):
    """What the fidelity report compares between real and made items: only things fixed code can read off."""
    parts = [p.strip() for p in gold.strip('[]').split(',')] if gold.startswith('[') else [gold.strip()]
    numeric = [p for p in parts if LITERAL.fullmatch(p.lstrip('-').replace(' ', '')) or re.fullmatch(r'-?\d[\d,]*\.?\d*%?', p)]
    kind = ('list' if gold.startswith('[') else 'text' if not numeric else
            'percent' if gold.endswith('%') else 'decimal' if '.' in gold else 'integer')
    row = {'question_chars': len(question),
           'rounding_stated': bool(re.search(r'\bround|nearest|decimal place|significant (?:figure|digit)', question, re.I)),
           'answer_kind': kind, 'answer_parts': len(parts), 'negative': gold.lstrip('[').startswith('-')}
    if trace is not None:
        row['values'] = len(trace['values'])
        row['operations'] = operations(trace)
        row['steps'] = len(trace.get('steps', []))
    if context is not None:
        row['pages'] = len(re.findall(r'^### ', context, flags=re.M))
        row['context_chars'] = len(context)
    return row
