"""Lenient-match diagnostics (registration §5.9): descriptive only, never used by the gate or by any claim.

Only the text of the LAST answer tag counts (no search through the rest of the reply), and it must hold a single answer:

- searchqa: after the official normalisation the tag text equals a reference answer, or contains it as whole tokens
  while having at most that answer's word count + 3 words;
- officeqa: the tag holds exactly one number, which equals the reference numerically once thousands separators, "$",
  "%" and unit words are removed; a non-numeric reference compares normalised characters;
- livemath: the tag holds exactly one standalone letter A-E, the correct option;
- spreadsheetbench, alfworld: none (None).

The reported quantity is the gap lenient minus official. Removing "%" or units can change a number's meaning, so the
gap is not "the formatting part" of an error.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from skillopt.envs.officeqa.evaluator import normalize_answer as officeqa_normalize
from skillopt.envs.searchqa.evaluator import normalize_answer as searchqa_normalize

from .checks import NUMBER, last_answer

UNIT_WORDS = re.compile(r"\b(million|millions|billion|billions|thousand|thousands|dollars|dollar|nominal|percent|"
                        r"per\s+cent|usd)\b")
MAX_EXTRA_WORDS = 3


def _searchqa(text, answers):
    given = searchqa_normalize(text).split()
    for answer in answers:
        gold = searchqa_normalize(answer).split()
        if not gold:
            continue
        if given == gold:
            return True
        if len(given) <= len(gold) + MAX_EXTRA_WORDS and any(given[i:i + len(gold)] == gold
                                                            for i in range(len(given) - len(gold) + 1)):
            return True
    return False


def _number(text):
    cleaned = UNIT_WORDS.sub(" ", text.lower()).replace("$", " ").replace("%", " ").replace(",", "").strip()
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _squeeze(value):
    return re.sub(r"[^0-9a-z%.-]", "", officeqa_normalize(value))


def _officeqa(text, reference):
    gold = _number(reference)
    if gold is None:
        return bool(_squeeze(reference)) and _squeeze(text) == _squeeze(reference)
    numbers = NUMBER.findall(text)
    if len(numbers) != 1:
        return False
    try:
        return Decimal(numbers[0].replace(",", "")) == gold
    except InvalidOperation:
        return False


def _livemath(text, reference):
    letters = re.findall(r"(?<![A-Za-z])([A-Ea-e])(?![A-Za-z])", text)
    return len(letters) == 1 and letters[0].upper() == reference.strip().upper()


def lenient(benchmark, private, prediction):
    """True/False for the three answer formats; None without a delivered reply, an answer tag or a decomposition."""
    if type(prediction) is not dict or prediction.get("status") != "available":
        return None
    output = prediction.get("output")
    if benchmark not in ("searchqa", "officeqa", "livemath") or type(output) is not str:
        return None
    text = last_answer(output)
    if text is None:
        return False
    if benchmark == "searchqa":
        answers = private.get("answers")
        valid = type(answers) is list and answers and all(type(a) is str for a in answers)
        return _searchqa(text, answers) if valid else None
    reference = private.get("answer")
    if type(reference) is not str:
        return None
    return _officeqa(text, reference) if benchmark == "officeqa" else _livemath(text, reference)
