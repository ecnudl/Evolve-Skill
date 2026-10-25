"""Scorer v2, the completion-aware verdict and the format flags of one cell (docs/handoff/execskill-registration-v1-
20261021.md §4.4 "评分器 v2" after Codex F7, §2.4, §6.3, §6.4 J4; implementation plan §1 judge row, §2.3 ``judge``,
§8.1 T-JUDGE-1..5).

One answer per reply, chosen without looking at the reference (``select_answer``):
(1) the official carrier when it holds a usable answer -- SearchQA: the frozen extraction (the last ``<answer>`` tag,
    else the last non-empty line; searchqa/evaluator.py:28-39) when it is not itself a JSON object and its SQuAD
    normalisation (evaluator.py:19-25) is not empty; OfficeQA: the last ``<answer>`` tag (checks.py:12-21) with
    non-blank content that is not itself a JSON object; LiveMath: that tag holds one letter by the frozen rule
    (checks.py:24-39, backends.py:501-504); SpreadsheetBench: the frozen code extraction finds a program
    (code_delivery.extract_python); ALFWorld: the frozen action rule finds an action (backends.py:752-754) -- and
    then ONLY that answer;
(2) otherwise, on the three QA benches only, the JSON answer (``json_answer``): the "answer" of the last top-level JSON
    object of the reply -- one inside a ```json fence or forming a tag's whole content included -- when it is a
    string or a number;
(3) otherwise none.
A second format never buys a second guess: ``<answer>A</answer> {"answer": "B"}`` is judged on A alone.

The JSON answer is judged by the bench's frozen comparison: ``backends.score`` on the answer inside an answer tag
(SearchQA's SQuAD exact match, OfficeQA's normalised exact match, LiveMath's single-letter rule). v2 passes a cell when
its completion-aware official verdict (``final``: ``outcomes_ext`` over the frozen table, finalised) passes, or when
that verdict is a scored fail, the official carrier was unusable and the JSON answer passes; SpreadsheetBench and
ALFWorld have no JSON channel (v2 = final). The invariants v2 >= final and v2 >= official are asserted for every cell.
The decision metric is v2 (completion-aware: a truncated, filtered or empty reply, an invalid action and an
undelivered program stay wrong). Recorded next to it: the official score (the frozen scorer's output), the final
verdict, the lenient score (descriptive only: coevo5 ``scoring.lenient`` on the selected answer), the format flags
with the J4 ``violation`` and the cell flags. The output holds tokens, booleans, counts and fixed vocabulary only --
never reply, answer or reference text -- so a sealed evaluation record can keep it (plan §2.10, Codex F16).

SearchQA, one guess per reply (statistics review 6, registrar decision 2026-10-22): the frozen scorer reads a reply
without any tag on its last non-empty line, so that line is SearchQA's official carrier. When it holds an answer, v2
judges that answer alone and never the JSON beside it: ``{"answer": "Paris"}\nLyon`` fails. The JSON answer counts
only when the carrier holds none -- an empty tag, a last line that is the JSON object itself, or one that normalises to
nothing, such as the closing line of a ```json fence or of a JSON object written over several lines.
"""
from __future__ import annotations

import json
import re

from skillopt.coevo5 import outcomes, scoring
from skillopt.coevo5.checks import ANSWER, NUMBER, answer_single_letter, code_present, last_answer
from skillopt.coevo5.outcomes import SCORED, Verdict, finalize
from skillopt.continual_eval import backends
from skillopt.continual_eval.code_delivery import extract_python
from skillopt.continual_eval.core import require
from skillopt.envs.searchqa.evaluator import extract_answer, normalize_answer

from . import outcomes_ext
from .protocol import ALFWORLD_ADMISSIBLE_MIN, BENCHES, QA, kind

SCORER = "execskill-judge-v2"  # §4.4: the scorer's own version
CARRIERS = ("official", "json", "none")
TAG = "<answer>%s</answer>"
ACTION = re.compile(r"<action>(.*?)</action>", re.S)  # the frozen extraction (backends.py:752)
MAX_ACTION_CHARS = 1000  # backends.py:754
UNKNOWN_TOKENS = frozenset(t for t in outcomes_ext.TOKENS if t.startswith("unknown"))
NOT_SCORED = {"status": None, "reason": "not_scored:decided_before_scoring"}  # cells.py:227-229
FLAGS = ("completed_without_text", "filtered", "json_rescued", "numeric_equal_string_unequal", "over_nominal",
         "reasoning_mismatch", "second_call_fallback", "truncated")
FILTERED_ERRORS = frozenset({"finish_sensitive", "finish_content_filter"})


def judge(bench, public, private, prediction, receipts=(), *, runtime, score=None, verdict=None, deciding=None):
    """``{"version", "scorer", "official", "final", "v2", "lenient", "format", "flags", "carrier"}`` of one cell.

    ``prediction``, ``receipts``, ``runtime``: as for the frozen scorer and table. ``score``: the official score when the
    runner has it; computed here (host only) on the QA benches, ALFWorld and an undelivered SpreadsheetBench program,
    while a delivered SpreadsheetBench program is scored by its runner (native containers under the native slot,
    cells.py:152-163) and None there means the cell was decided before scoring. ``verdict``: the cell's final verdict when the runner has one (after its remedies); else ``outcomes_ext``
    decides it here (preflight, then classify) and it is finalised. ``deciding``: the deciding receipt
    (``outcomes_ext.deciding_receipt`` by default)."""
    require(bench in BENCHES, "Unknown benchmark")
    require(isinstance(prediction, dict) and isinstance(private, dict), "A prediction and a private part are mappings")
    receipts = list(receipts)
    if deciding is None:
        deciding = outcomes_ext.deciding_receipt(prediction, receipts)
    outcomes_ext.check_deciding(receipts, deciding)
    if score is None and (bench != "spreadsheetbench" or prediction.get("status") != "available"):
        score = backends.score(bench, public, private, prediction, runtime=runtime)  # host only
    if verdict is None:
        verdict = outcomes_ext.preflight(bench, prediction, receipts, deciding=deciding)
        if verdict is None:
            require(score is not None, "A SpreadsheetBench cell is scored by its runner before it is judged")
            verdict = outcomes_ext.classify(bench, prediction, score, receipts, deciding=deciding)
        verdict = finalize(verdict)
    require(isinstance(verdict, Verdict) and verdict.remedy is None, "The judge reads a final verdict")
    require(score is None or isinstance(score, dict), "An official score is a mapping")
    official = NOT_SCORED if score is None else {"status": score.get("status"), "reason": score.get("reason")}
    final = outcomes_ext.token(verdict)
    reply = _reply(bench, prediction)
    answer, carrier = _carrier(bench, prediction, reply)
    rescued = (bench in QA and carrier == "json" and final == "fail" and verdict.kind == SCORED
               and _passes(bench, public, private, answer, runtime))
    v2 = "pass" if rescued else final
    require(v2 == final or (final == "fail" and v2 == "pass"), "Scorer v2 below the completion-aware verdict")
    require(v2 == "pass" or official["status"] != "pass", "Scorer v2 below the official score")
    lenient = scoring.lenient(bench, private, {"status": "available", "output": TAG % answer}
                              if carrier == "json" else prediction)
    revised = runtime.get("code_extraction_version") == "explicit-python-fences-v2"
    return {"version": kind("judge-v2-3" if revised else "judge"),
            "scorer": "execskill-judge-v2-3" if revised else SCORER, "official": official,
            "final": {"token": final, "outcome": verdict.outcome, "kind": verdict.kind, "row": verdict.row,
                      "public": outcomes.public(verdict)},
            "v2": {"token": v2}, "lenient": {"pass": lenient},
            "format": _format(bench, prediction, reply, answer, final),
            "flags": _flags(bench, private, prediction, receipts, deciding, final, v2, lenient), "carrier": carrier}


def select_answer(bench, reply, *, configuration="default"):
    """``(answer, carrier)`` of one reply by the reference-independent precedence (module docstring); carrier is one of
    ``CARRIERS``, answer None for ``none``."""
    require(bench in BENCHES, "Unknown benchmark")
    require(type(reply) is str, "A reply is text")
    if bench == "spreadsheetbench":
        from . import protocol

        if protocol.CODE_EXTRACTION[configuration] == "explicit-python-fences-v2":
            from .code_delivery import extract_python as extract_v2

            extracted = extract_v2(reply, multiple=protocol.MULTIPLE_PYTHON_BLOCKS[configuration])
        else:
            extracted = extract_python(reply)
        return (extracted["code"], "official") if extracted["status"] == "available" else (None, "none")
    if bench == "alfworld":
        match = ACTION.search(reply)
        action = match.group(1).strip() if match else reply.strip()
        return (action, "official") if action and len(action) <= MAX_ACTION_CHARS else (None, "none")
    tag = _official_text(bench, reply)
    if _usable_tag(bench, reply, tag):
        return tag, "official"
    found = json_answer(reply)
    return (found, "json") if found is not None else (None, "none")


def json_answer(reply):
    """The JSON answer of a reply, or None: the value of the "answer" key of the LAST top-level JSON object that has
    one (objects are read left to right; an object nested in another is part of it), when that value is a string or a
    number (written as in the reply) that is not blank and survives inside an answer tag unchanged. The last such object
    alone counts: an unusable value there is no answer, never a reason to read an earlier object."""
    require(type(reply) is str, "A reply is text")
    if '"answer"' not in reply:
        return None
    decoder = _decoder()
    index, found, value = 0, False, None
    while True:
        start = reply.find("{", index)
        if start < 0:
            break
        try:
            parsed, end = decoder.raw_decode(reply, start)
        except (ValueError, RecursionError):  # not a JSON object here (or nested beyond the parser's depth)
            index = start + 1
            continue
        if "answer" in parsed:
            found, value = True, parsed["answer"]
        index = end
    if not found or type(value) is not str or not value.strip() or last_answer(TAG % value) != value.strip():
        return None
    return value


def _decoder():
    """Numbers keep their text (an answer "12.50" stays 12.50); NaN and Infinity are not JSON answers."""
    def reject(constant):
        raise ValueError("Not a JSON number: " + constant)

    return json.JSONDecoder(parse_float=str, parse_int=str, parse_constant=reject)


def _json_object(text):
    """True when ``text`` as a whole is one JSON object."""
    try:
        return isinstance(_decoder().decode(text), dict)
    except (ValueError, RecursionError):
        return False


def _official_text(bench, reply):
    """The official carrier's text: SearchQA's frozen extraction ("" when its SQuAD normalisation is empty: no answer),
    elsewhere the last answer tag (None without one)."""
    if bench != "searchqa":
        return last_answer(reply)
    carrier = extract_answer(reply)
    return carrier if normalize_answer(carrier) else ""


def _usable_tag(bench, reply, tag):
    if not tag or _json_object(tag):
        return False
    return bench != "livemath" or answer_single_letter(reply) is True


def _reply(bench, prediction):
    """A QA cell's delivered reply text (the frozen scorer's input, backends.py:436), else None."""
    output = prediction.get("output")
    available = prediction.get("status") == "available" and type(output) is str
    return output if bench in QA and available else None


def _carrier(bench, prediction, reply):
    if bench in QA:
        return select_answer(bench, reply) if reply is not None else (None, "none")
    # SpreadsheetBench and ALFWorld: the shell applied the frozen extraction; an available prediction carries its
    # program, or every action of its episode
    return None, "official" if prediction.get("status") == "available" else "none"


def _passes(bench, public, private, answer, runtime):
    """The bench's frozen comparison on one answer (the official scorer on it inside an answer tag)."""
    wrapped = {"status": "available", "output": TAG % answer, "costs": {}, "reason": "model_response_available"}
    return backends.score(bench, public, private, wrapped, runtime=runtime).get("status") == "pass"


def _format(bench, prediction, reply, answer, final):
    """The format flags of the cell; ``violation`` is J4's (§6.4: QA no usable answer tag, LiveMath not one letter,
    SpreadsheetBench no program, ALFWorld an admissible share below 0.9), None for an unknown cell (J4 counts those by
    arm, coevo5 step.py:160-181)."""
    unknown = final in UNKNOWN_TOKENS
    if bench == "spreadsheetbench":
        output = prediction.get("output") if prediction.get("status") == "available" else None
        delivered = code_present(output) is True
        cases = output.get("cases") if delivered and isinstance(output.get("cases"), list) else []
        return {"program_delivered": delivered, "cases": len(cases),
                "cases_available": sum(isinstance(c, dict) and c.get("status") == "available" for c in cases),
                "violation": None if unknown else not delivered}
    if bench == "alfworld":
        return _alfworld_format(prediction, unknown)
    if reply is None:
        return {"reply": False, "violation": None if unknown else True}
    tag = last_answer(reply)
    usable = _usable_tag(bench, reply, tag)
    flags = {"reply": True, "tag_count": len(ANSWER.findall(reply)), "tag_present": tag is not None,
             "tag_usable": usable, "json_in_tag": bool(tag) and _json_object(tag),
             "json_answer": json_answer(reply) is not None}
    if bench == "searchqa":
        flags["last_line_fallback"] = tag is None
    elif bench == "officeqa":
        flags["single_number"] = answer is not None and len(NUMBER.findall(answer)) == 1
    else:
        flags["single_letter"] = answer_single_letter(reply) is True
        flags["boxed"] = "\\boxed{" in reply
    flags["violation"] = None if unknown else not usable
    return flags


def _alfworld_format(prediction, unknown):
    """The executed actions' admissible share, from the shell's step log (``shell.alfworld_steps[i].how`` of the
    level-1 canonicaliser: every value but ``unchanged`` executed an admissible command); None without a shell."""
    shell = prediction.get("shell")
    hows = None
    if isinstance(shell, dict):
        steps = shell.get("alfworld_steps")
        require(isinstance(steps, list) and all(isinstance(s, dict) and "how" in s for s in steps),
                "An ALFWorld shell logs every step's canonicalisation")
        hows = [s["how"] for s in steps]
    admissible = None if hows is None else sum(how != "unchanged" for how in hows)
    if unknown:
        violation = None
    elif prediction.get("reason") == "invalid_action_format":
        violation = True
    elif not hows:
        violation = None
    else:
        violation = admissible * ALFWORLD_ADMISSIBLE_MIN.denominator < ALFWORLD_ADMISSIBLE_MIN.numerator * len(hows)
    return {"steps": None if hows is None else len(hows), "admissible_steps": admissible, "violation": violation}


def _flags(bench, private, prediction, receipts, deciding, final, v2, lenient):
    """The registered ``FLAGS`` that apply to the cell, sorted."""
    reason = prediction.get("reason")
    error = receipts[deciding].get("error_type") if receipts and isinstance(receipts[deciding], dict) else None
    shell = prediction.get("shell")
    reference = private.get("answer")
    found = {
        "completed_without_text": reason == "model_response_completed_without_text",
        "filtered": reason == "model_response_filtered" or error in FILTERED_ERRORS,
        "json_rescued": final == "fail" and v2 == "pass",
        "numeric_equal_string_unequal": (bench == "officeqa" and v2 == "fail" and lenient is True
                                         and type(reference) is str and scoring._number(reference) is not None),
        "over_nominal": any(isinstance(r, dict) and r.get("over_nominal") is True for r in receipts),
        "reasoning_mismatch": any(isinstance(r, dict) and r.get("subtype") == "reasoning_mismatch" for r in receipts),
        "second_call_fallback": isinstance(shell, dict) and bool(shell.get("fallback")),
        "truncated": reason == "model_response_truncated" or error in outcomes_ext.TRUNCATED_ERRORS,
    }
    return sorted(name for name in FLAGS if found[name])
