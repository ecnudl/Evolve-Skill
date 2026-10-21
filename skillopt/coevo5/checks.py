"""The rubric's code items (registration §6): a fixed library of host-run format checks.

A rubric item names one check and fills its parameters; no model-written code is ever executed. Every check is a pure
function of the solver's prediction output and returns True (satisfied), False (violated) or None (not applicable).
"""
from __future__ import annotations

import re

from skillopt.continual_eval.core import require

ANSWER = re.compile(r"<answer>(.*?)</answer>", re.S | re.I)
NUMBER = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def last_answer(output):
    """The text inside the last <answer>...</answer> tag (the tag every answer-tag scorer reads), or None."""
    if type(output) is not str:
        return None
    found = ANSWER.findall(output)
    return found[-1].strip() if found else None


def _letter(text):
    label = text.upper().strip()
    if label[-1:] in {".", ")", ":"}:
        label = label[:-1].strip()
    return label


def answer_tag_present(output):
    return None if type(output) is not str else last_answer(output) is not None


def answer_single_letter(output):
    if type(output) is not str:
        return None
    text = last_answer(output)
    return text is not None and len(_letter(text)) == 1 and _letter(text) in "ABCDE"


def answer_pure_number(output, allow_percent=False):
    text = last_answer(output)
    if text is None:
        return None
    if allow_percent and text.endswith("%"):
        text = text[:-1].strip()
    return NUMBER.fullmatch(text) is not None


def answer_no_percent(output):
    text = last_answer(output)
    return None if text is None else "%" not in text


def answer_no_letters(output):
    """No alphabetic characters inside the tag (units or words such as "percent", "million" or "approximately")."""
    text = last_answer(output)
    return None if text is None else not any(ch.isalpha() for ch in text)


def answer_max_words(output, n):
    text = last_answer(output)
    return None if text is None else len(text.split()) <= n


def code_present(output):
    if type(output) is not dict:
        return None
    return type(output.get("code")) is str and bool(output["code"].strip())


# name -> (function, {parameter: (type, minimum, maximum) or (bool,)})
CHECKS = {
    "answer_tag_present": (answer_tag_present, {}),
    "answer_single_letter": (answer_single_letter, {}),
    "answer_pure_number": (answer_pure_number, {"allow_percent": (bool,)}),
    "answer_no_percent": (answer_no_percent, {}),
    "answer_no_letters": (answer_no_letters, {}),
    "answer_max_words": (answer_max_words, {"n": (int, 1, 50)}),
    "code_present": (code_present, {}),
}


def validate(spec):
    """A check reference {"name": ..., "params": {...}} with exactly the registered parameters and legal values."""
    require(type(spec) is dict and set(spec) == {"name", "params"}, "A check is {name, params}")
    require(spec["name"] in CHECKS, "Unknown check")
    _, schema = CHECKS[spec["name"]]
    params = spec["params"]
    require(type(params) is dict and set(params) == set(schema), "Check parameters must match the registered schema")
    for key, rule in schema.items():
        value = params[key]
        require(type(value) is rule[0], "Check parameter has the wrong type")
        if rule[0] is int:
            require(rule[1] <= value <= rule[2], "Check parameter out of range")
    return {"name": spec["name"], "params": dict(params)}


def run(spec, output):
    spec = validate(spec)
    function, _ = CHECKS[spec["name"]]
    result = function(output, **spec["params"])
    require(result is None or type(result) is bool, "Checks return True, False or None")
    return result
