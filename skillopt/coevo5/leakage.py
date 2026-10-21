"""Leakage checks of a rule before it is written (registration §9), and the pre-dispatch check of §4 step 5b.

A rule's text (after the research rewrite) is compared with every item of the stage bench's training pool -- never a
test item: the checker is given no test data. Texts are normalized (NFKC, lower case, punctuation and symbols to spaces,
whitespace collapsed). The mechanical checks (``mechanical``), the first that hits decides:

1. ``shared_8gram``: the rule shares 8 consecutive words with an item's task surface (``surface``: the question with
   the supplied context -- SearchQA's snippets, OfficeQA's pages -- or with the options, or the task instruction); an
   8-gram present in at least 5% of the bench's items is template text and does not count.
2. By answer type -- ``answer_text``: a reference answer of two or more words appears as a whole-word run, one of a
   single word of at least 5 characters as a whole word (SearchQA; OfficeQA's non-numeric answers); ``answer_number``:
   a number in the rule, however written (thousands separators, a leading or trailing point, an exponent, a fraction
   p/q, a sign), equals in absolute value an OfficeQA reference value of at least 3 significant digits (a four-digit
   year 1900-2030 in the rule is not checked); ``option_text``: the content of LiveMath's correct option (at least 4
   characters without whitespace) appears as a substring. Option letters are never checked. SpreadsheetBench and
   ALFWorld (whose surface is the task text of the episode's initial observation) have check 1 only.

The same checks screen a rule's text and its research questions before any research request is sent (§4 step 5b), so
the researcher never sees a training question through them. A rule that passes is put to the adjudicator
(``adjudicate``, GLM-5.3, fixed prompt): "yes" -- it states a fact of one specific task, or maps a specific kind of task
to an answer -- or an invalid reply drops it. The adjudicator's prompt, reply and verdict are kept in the role record.

v2 (registration delta §7): every check runs (``findings``); when the only hits are single-word answers
(``answer_word``), the rule is not dropped mechanically but goes to the adjudicator with at most three colliding
training items (seeded; the question clipped to 600 characters, and the reference answer) -- a veto only, after the
final rewrite; its evidence and reason feed nothing else. Every adjudicated rule is also refused when it steers the
answer by how the benchmark's answers are distributed. Multi-word answers, numbers, option contents and shared 8-grams
stay mechanical drops.

v3 (registration delta §4, §6): the adjudicator also refuses a rule whose advice depends on what the solver cannot see
while solving (the reference answer, whether an answer is correct, a score); on SpreadsheetBench it is shown the
answer-cell values the proposal half's failures expected (``answer_values``, bounded) and refuses a rule that copies
them.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal
from fractions import Fraction

from skillopt.continual_eval.core import require
from skillopt.continual_eval.datasets import LIVEMATH_LABELS, livemath_options

from .protocol import (
    DATA_SEED,
    LEAK_MIN_OPTION_CHARS,
    LEAK_MIN_SIGNIFICANT_DIGITS,
    LEAK_MIN_SINGLE_WORD,
    LEAK_NGRAM,
    LEAK_TEMPLATE_SHARE,
    LEAK_WORD_EVIDENCE_CHARS,
    LEAK_WORD_EVIDENCE_ITEMS,
    ORDER,
)
from .roles import Invalid, fields
from .roles import text as bounded

REASONS = ("shared_8gram", "answer_text", "answer_number", "option_text", "answer_word")  # v2: answer_word last
# a number of the rule (ASCII digits, after NFKC): thousands separators, a decimal part (a leading or a trailing point
# too) and an exponent; a sign is not part of it (values are compared in absolute value)
NUMBER = re.compile(r"(?<![0-9.])(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")
FRACTION = re.compile(r"(?<![0-9/])(?<![0-9][.,])([0-9]{1,30})\s*/\s*([0-9]{1,30})(?![0-9/]|[.,][0-9])")
MAX_EXPONENT = 30  # a number written with a larger decimal exponent equals no reference
YEAR = re.compile(r"[0-9]{4}")
YEARS = (1900, 2030)
# a numeric OfficeQA reference once ",", "$", "%" and surrounding space are removed
REFERENCE_NUMBER = re.compile(r"[-+]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")

ADJUDICATE_SYSTEM = (
    "You review one guidance rule written for a language model that solves benchmark tasks. Decide whether the rule "
    "states a fact about one specific task -- for example a particular question's answer, entity, number, date or "
    "document detail -- or maps a specific kind of task to a specific answer (for example \"when the question "
    "mentions X, answer Y\"), or steers the answer by how the benchmark's answers are distributed rather than by "
    "reasoning about the task (for example \"option C is usually right\" or \"the option saying that none of the "
    "others hold is usually the answer\"), or makes its advice depend on something the solver cannot see while "
    "solving -- the reference answer, whether an answer is correct, or a score (for example \"when the reference is "
    "a pure number, ...\"). General advice on method, reading the material, calculation or the answer format is not "
    "such a statement, even when it gives an illustrative example.\n\n"
    "The user message is a JSON object {\"rule\": the rule's text}, possibly with \"colliding_items\": training "
    "tasks whose reference answer is a word that also occurs in the rule (each with an excerpt of its question and "
    "its answer), and possibly with \"answer_values\": values that training spreadsheet tasks expected in their "
    "answer cells. Then decide also whether the rule gives away those answers or copies those values, or uses a word "
    "only incidentally in general advice. Reply with one JSON object and nothing else: {\"verdict\": \"yes\" or "
    "\"no\", \"reason\": a short reason of at most 300 characters}. \"yes\" means the rule states such a fact, "
    "mapping, answer distribution or unseen condition, gives away a colliding item's answer, or copies an expected "
    "value.")


def normalize(text):
    """NFKC, lower case, every punctuation or symbol character a space, whitespace collapsed."""
    require(type(text) is str, "Only text is normalized")
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join("".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in text).split())


def surface(benchmark, item, *, task_text=None):
    """The item's task surface: its question with the supplied context (SearchQA: the snippets, one per line; OfficeQA:
    the pages) or with the options (LiveMath), SpreadsheetBench's instruction, or ALFWorld's ``task_text`` (the
    episode's initial observation from this step's training execution)."""
    public = item["public"]
    if benchmark in ("searchqa", "officeqa"):
        context = public["context"]
        if type(context) is list:
            require(all(type(c) is str for c in context), "A context is text")
            context = "\n".join(context)
        require(type(public["question"]) is str and type(context) is str, "A QA item is text")
        value = public["question"] + "\n" + context
    elif benchmark == "livemath":
        require(type(public["question"]) is str and type(public["choices"]) is str, "A LiveMath item is text")
        value = public["question"] + "\n" + public["choices"]
    elif benchmark == "spreadsheetbench":
        value = public["instruction"]
    elif benchmark == "alfworld":
        value = task_text
    else:
        raise ValueError("Unknown benchmark")
    require(type(value) is str, "An item's surface is text")
    return value


def _grams(tokens):
    return {tuple(tokens[i:i + LEAK_NGRAM]) for i in range(len(tokens) - LEAK_NGRAM + 1)}


def _significant(number):
    """Significant digits of a decimal as written: its digits without sign, point and leading zeros."""
    return len(number.lstrip("+-").replace(".", "").lstrip("0"))


def _value(written):
    """The exact absolute value of a number as written (separators removed); None beyond the exponent bound."""
    number = Decimal(written.replace(",", ""))
    return abs(Fraction(number)) if abs(number.adjusted()) <= MAX_EXPONENT else None


def _numeric(answer):
    """The reference's value when it is a number once ",", "$", "%" and surrounding space are removed, else None."""
    cleaned = answer.replace(",", "").replace("$", "").replace("%", "").strip()
    return cleaned if REFERENCE_NUMBER.fullmatch(cleaned) else None


class Corpus:
    """What the checks compare a text with: one bench's training pool (``items``: pool items of that bench; ALFWorld:
    ``alfworld_texts`` {task_id: initial observation}, an item without one is skipped)."""

    def __init__(self, benchmark, items, *, alfworld_texts=None):
        require(benchmark in ORDER, "Unknown benchmark")
        require(all(item["benchmark"] == benchmark for item in items), "A corpus holds one bench's items")
        texts = alfworld_texts or {}
        surfaces = []
        for item in items:
            if benchmark == "alfworld":
                if item["task_id"] in texts:
                    surfaces.append(surface(benchmark, item, task_text=texts[item["task_id"]]))
            else:
                surfaces.append(surface(benchmark, item))
        grams = [_grams(normalize(value).split()) for value in surfaces]
        counts = Counter(gram for found in grams for gram in found)
        self.benchmark, self.size = benchmark, len(grams)
        self.template = frozenset(g for g, c in counts.items() if Fraction(c, len(grams)) >= LEAK_TEMPLATE_SHARE)
        self.shared = frozenset(counts) - self.template
        self.phrases, self.words, self.numbers, self.options = set(), set(), set(), set()
        self.word_items = {}  # v2 §7: word -> [(task id, question, answer)] of the items whose answer it is
        for item in items:
            if benchmark == "searchqa":
                answers = item["private"]["answers"]
                require(type(answers) is list and all(type(a) is str for a in answers), "SearchQA answers are text")
                for answer in answers:
                    self._text_answer(answer, item)
            elif benchmark == "officeqa":
                answer = item["private"]["answer"]
                require(type(answer) is str, "An OfficeQA answer is text")
                value = _numeric(answer)
                if value is None:
                    self._text_answer(answer, item)
                elif _significant(value) >= LEAK_MIN_SIGNIFICANT_DIGITS:
                    self.numbers.add(_value(value))
            elif benchmark == "livemath":
                options, letter = livemath_options(item["public"]["choices"]), item["private"]["answer"]
                require(options is not None and type(letter) is str and len(letter) == 1 and letter in LIVEMATH_LABELS,
                        "A LiveMath item has five options and a letter")
                content = "".join(normalize(options[LIVEMATH_LABELS.index(letter)]).split())
                if len(content) >= LEAK_MIN_OPTION_CHARS:
                    self.options.add(content)

    def _text_answer(self, answer, item):
        tokens = tuple(normalize(answer).split())
        if len(tokens) >= 2:
            self.phrases.add(tokens)
        elif len(tokens) == 1 and len(tokens[0]) >= LEAK_MIN_SINGLE_WORD:
            self.words.add(tokens[0])
            self.word_items.setdefault(tokens[0], []).append((item["task_id"], item["public"]["question"], answer))

    def evidence(self, words):
        """v2 §7: at most three colliding training items of ``words`` (seeded by task id), each {"question": its
        first 600 characters, "answer": the reference answer}."""
        found = {}
        for word in sorted(words):
            for task_id, question, answer in self.word_items.get(word, []):
                found.setdefault(task_id, {"question": question[:LEAK_WORD_EVIDENCE_CHARS], "answer": answer})
        order = sorted(found, key=lambda t: hashlib.sha256(json.dumps([DATA_SEED, "leak", t]).encode()).hexdigest())
        return [found[t] for t in order[:LEAK_WORD_EVIDENCE_ITEMS]]


def _numbers(text):
    """The absolute values of the numbers written in ``text`` (a fraction p/q also as its value), except four-digit
    years 1900-2030."""
    text = unicodedata.normalize("NFKC", text)
    for match in NUMBER.finditer(text):
        raw = match.group()
        if YEAR.fullmatch(raw) and YEARS[0] <= int(raw) <= YEARS[1]:
            continue
        value = _value(raw)
        if value is not None:
            yield value
    for match in FRACTION.finditer(text):
        if int(match.group(2)):
            yield Fraction(int(match.group(1)), int(match.group(2)))


def findings(text, corpus):
    """v2 §7: every mechanical check's hits on ``text`` -- {reason: True, ..., "answer_word": [the colliding words]}
    (``answer_text`` is a multi-word answer since v2; a single word is ``answer_word``)."""
    require(type(text) is str and isinstance(corpus, Corpus), "A text and a corpus")
    tokens = normalize(text).split()
    out = {}
    if _grams(tokens) & corpus.shared:
        out["shared_8gram"] = True
    if any(tokens[i:i + len(phrase)] == list(phrase)
           for phrase in corpus.phrases for i in range(len(tokens) - len(phrase) + 1)):
        out["answer_text"] = True
    if corpus.numbers and any(value in corpus.numbers for value in _numbers(text)):
        out["answer_number"] = True
    squeezed = "".join(tokens)
    if any(option in squeezed for option in corpus.options):
        out["option_text"] = True
    words = sorted(corpus.words & set(tokens))
    if words:
        out["answer_word"] = words
    return out


def answer_values(answers, limit=60):
    """v3 §6: the distinct expected answer-cell values (``sheetview``) of SpreadsheetBench answers, in their order, at
    most ``limit``: blanks and booleans left out, numbers as written by Python."""
    out = []
    for answer in answers:
        for cell in ((answer.get("sheet_cells") or {}).get("shown") or []):
            value = cell.get("expected")
            if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
                continue
            value = str(value)
            if value not in out:
                out.append(value)
            if len(out) >= limit:
                return out
    return out


def mechanical(text, corpus):
    """None when ``text`` (a rule, or a research question before dispatch) passes every mechanical check of
    ``corpus``'s bench, else the first hit's reason in ``REASONS`` order -- "answer_word" only when it is the sole hit
    (v2 §7: the caller sends such a rule to the adjudicator with the colliding items instead of dropping it)."""
    found = findings(text, corpus)
    return next((reason for reason in REASONS if reason in found), None)


def _verdict(value):
    fields(value, ("verdict", "reason"))
    if value["verdict"] not in ("yes", "no"):
        raise Invalid("verdict")
    bounded(value["reason"], limit=300, empty=True)
    return value


def adjudicate(roles, text, *, label, colliding=None, values=None):
    """True (keep) when the adjudicator answers "no"; "yes" or an invalid reply drops the rule (§9). v2 §7:
    ``colliding``, the items a single-word answer hit names (``Corpus.evidence``), shown with the rule. v3 §6:
    ``values``, SpreadsheetBench's expected answer-cell values of the shown failures (``answer_values``)."""
    require(type(text) is str and text.strip(), "A rule to adjudicate")
    message = {"rule": text}
    if colliding:
        message["colliding_items"] = list(colliding)
    if values:
        message["answer_values"] = list(values)
    value = roles.ask("leak_adjudicate", ADJUDICATE_SYSTEM, message, label=label, check=_verdict)
    return value is not None and value["verdict"] == "no"
