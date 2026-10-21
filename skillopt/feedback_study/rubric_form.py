"""Rubric-form study (``fivebench-rubric-form-study-v1``; 2026-10-14, owner's question of 20:30): in the main
method's own flow -- train execution -> rubric feedback -> analyst -> candidate -> selection -- which FORM of the
rubric (host-executed checks vs text judged by the model) and which GRANULARITY (one global rubric, the benchmark's
default, a rubric with a section per question type, a rubric derived from the parent Skill's own rules) produces
the better one-step candidate, everything else held fixed?

The instrument is the L3 matched-feedback block (``matched_feedback.run_block``), re-implemented here for the
extension benchmarks and more arms: in every block ONE fresh train rollout of the parent Skill is shared by all
arms; each arm turns that evidence into its own feedback, proposes one candidate with the frozen native updater
(same analyst prompts, parser, retries), and every distinct candidate is scored on the SAME selection set in the
same block. Arms:

  scalar           pass/fail only (the control)
  labelled         failed rows carry the reference answer (learning v9's feedback)
  default_text     the benchmark's frozen default rubric (learning v10), judged by the model
  global_text      one benchmark-agnostic rubric, judged by the model
  cluster_text     one rubric with a section per question type (lookup / arithmetic / statistics / date or text /
                   chart), judged by the model -- a "rubric per cluster of tasks"
  format_text      the host's format checks written as a rubric, judged by the model
  format_code      the same format checks EXECUTED by the host (no call)      <- form contrast: code vs text
  compliance_code  checks derived by hand from the parent Skill's own rules, executed by the host -- a "rubric per
                   Skill" (not model-generated in this study)

A text arm's reports follow learning v10 exactly (judge prompts, calibration, authorization: unauthorized -> scalar
feedback, recorded). A code arm's reports are produced by ``HostRubricVerifier`` with the same record tree,
calibration rule and report shape, from the public fields and the output only -- no reference answer enters any
check or any report. The analyst's note for a failed row is v10's (``_checker_note``): status, the verifier text,
and for the labelled arm the expected answer. A proposal that fails (the analyst's JSON rejected, a parse
incomplete) leaves that arm on the parent for the block and the block continues (recorded as such); any other
stop leaves the study pending, never resumed.

Reading: exploratory, one parent, one benchmark, a generated selection set; pre-registered contrasts in ANALYSIS
(exact block sign-flip over blocks is the only confirmatory statistic; per-position paired counts are descriptive).
A candidate scored higher on the selection set is not a Skill accepted by any gate and not a held-out result.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import warnings
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.contracts import VERIFIER_METHOD, check_skill, skill_budget
from skillopt.continual_learning.feedback import artifacts as learning_artifacts
from skillopt.continual_learning.feedback import benchmark_for, expected_text, project, task_description, verifier_enabled
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import DELIVERY_VERSIONS, POLICY_V10, client_options
from skillopt.continual_learning.skillopt import native_sources
from skillopt.continual_learning.verifier import VERSION as VERIFIER_VERSION
from skillopt.continual_learning.verifier import MAX_REPORT_CHARS, Verifier, default_policy_record
from skillopt.validator_pilot.api import CachedAPI, digest

from .common import bind_rows, local_rubric, run_cells, study_manifest, study_sources, validate_rubric_record
from .fixed_rubric import arm_metrics, sign_flip_two_sided
from .matched_feedback import _counts

PROTOCOL = "fivebench-rubric-form-study-v1"
BENCHMARKS = ("officeqa", "searchqa")  # the judge path of the v10 verifier, no probe execution, no Research
ARMS = ("scalar", "labelled", "default_text", "global_text", "cluster_text", "format_text", "format_code", "compliance_code")
TEXT_ARMS = ("default_text", "global_text", "cluster_text", "format_text")
CODE_ARMS = ("format_code", "compliance_code")
RUBRIC_ARMS = TEXT_ARMS + CODE_ARMS
SLOTS = ("parent", *ARMS)
MODULES = ("__init__.py", "common.py", "fixed_rubric.py", "matched_feedback.py", "rubric_form.py")
PLAN_SEED = 20261014
EDIT_BUDGET = 4
BUDGET = {"max_metric_calls": 12000, "max_reflection_calls": 1200, "max_api_calls": 30000,
          "max_reported_tokens": 80_000_000, "max_iterations": 1, "minibatch_size": 8, "solver_max_tokens": 65536,
          "reflection_max_tokens": 8192, "max_verifier_calls": 2400, "verifier_max_tokens": 4096}
# per benchmark: the ONE ledger of a study counts every block; six blocks of 128 training rows judged by four text
# arms are 3,072 judge calls before retries on SearchQA (48 rows: 1,152 on OfficeQA); selection passes of up to nine
# texts on 168 generated tasks are 1,512 solver calls per block
BUDGETS = {"officeqa": BUDGET,
           "searchqa": {**BUDGET, "max_verifier_calls": 4800, "max_metric_calls": 16000, "max_api_calls": 40000,
                        "max_reported_tokens": 120_000_000}}
ANALYSIS = {
    "unit": "block: one shared fresh train rollout of the parent, one candidate per arm, every distinct candidate "
            "scored once on the whole selection set of the block",
    "confirmatory": {"test": "exact_block_sign_flip_two_sided_on_pass_count_differences", "alpha": 0.05,
                     "note": "with fewer than six blocks no contrast can reach alpha; the study is then descriptive"},
    "descriptive": "per-position paired wins/losses pooled over blocks (positions of one block share a candidate: "
                   "not independent), unknown sensitivity bounds",
    "contrasts": [["format_code", "format_text"], ["cluster_text", "default_text"], ["global_text", "default_text"],
                  ["compliance_code", "scalar"], ["default_text", "scalar"], ["labelled", "scalar"],
                  ["format_code", "scalar"], ["format_text", "scalar"], ["cluster_text", "scalar"],
                  ["global_text", "scalar"]],
    "verifier_endpoints": "per rubric arm: authorized blocks, pooled detection rate and false-rejection rate on the "
                          "shared rollouts (code arms: host checks; text arms: the model judge)",
    "form_contrast": "format_code vs format_text compares two feedback PACKAGES built from the same check list: the "
                     "host executes every applicable check and reports each; the frozen v10 judge returns at most two "
                     "checks anchored in question quotes and may abstain. A difference is not attributable to the "
                     "executor alone.",
    "claim_limits": "one parent Skill, one benchmark, a generated selection set that is easier than the real "
                    "validation items, candidates never gated or evaluated held-out; a difference between arms is "
                    "a difference between the candidates their feedback produced on these blocks, nothing more",
}
NO_UPDATE = ("no_update", "rejected_inadmissible_over_budget")


def tolerated_proposal_failure(exc):
    """The reason when a failed proposal is the ANALYST'S doing -- its reply rejected by the strict JSON parser
    (after the bounded retry), a parse that produced too few patches, an oversized candidate -- and None for every
    other stop (a budget exhausted, an undelivered or unknown response, a transport failure), which keeps its own
    classification and stops the study. The WHOLE exception chain is read first: any disqualifying cause anywhere
    in it wins, whatever the wrapper says."""
    from skillopt.continual_learning.ledger import BudgetExhausted
    from skillopt.continual_learning.reflection_json import NativeJSONError

    chain, cause = [], exc
    while cause is not None and len(chain) < 16:
        chain.append(cause)
        cause = cause.__cause__
    if not chain or not isinstance(chain[0], LearningPending):
        return None
    if any(isinstance(c, BudgetExhausted) or not isinstance(c, (LearningPending, NativeJSONError)) for c in chain):
        return None  # a budget, an undelivered call, a transport or any other failure: never the analyst's doing
    if any(isinstance(c, LearningPending) and (str(c).startswith("native_optimizer_response_unknown")
                                              or str(c).startswith("earlier_native_optimizer_failure")) for c in chain):
        return None
    reason = str(chain[0])
    if reason in ("native_reflection_parse_incomplete", "native_candidate_exceeds_skill_budget"):
        return reason
    if reason in ("native_reflection_incomplete", "native_optimizer_incomplete"):
        for c in chain[1:]:
            if isinstance(c, LearningPending) and str(c).startswith("native_optimizer_json_rejected"):
                return reason + ":" + str(c).split(":", 1)[0]
    return None


# ----------------------------------------------------------------------------- the rubrics
def _policy(mechanism, applicability, exceptions, evidence, generation, uncertainty):
    return {"mechanism": mechanism, "obligation": "requested_behavior", "applicability": applicability,
            "exceptions": exceptions, "evidence_required": evidence, "check_generation": generation,
            "uncertainty": uncertainty}


GLOBAL_POLICY = _policy(
    "Answer the question that was asked, in the form it asks for, from the supplied material only.",
    "Any question-answering task with a supplied context and a public answer form; nothing benchmark-specific.",
    "Abstain when the question does not determine the check or the answer form is not stated.",
    "The response text compared with the question's explicit demands; the supplied context for scope.",
    "Check at most two obligations: (1) the final answer is one value of the kind the question asks for (number, "
    "date, name, list), with the unit, scale and rounding the question states and nothing else inside the answer "
    "tag; (2) the answer addresses the asked item (the same quantity, period and entity), not a neighbouring one.",
    "Without the reference answer a judge can tell form and scope, not whether the value is right.")
CLUSTER_POLICY = _policy(
    "Apply the section that matches the question's type; each type has its own obligations.",
    "LOOKUP (a single printed value): the right table, row, column, period and unit. ARITHMETIC (a difference, "
    "sum, ratio, share, change, conversion): every input is a printed value of the asked period, the operation is "
    "the asked one, the rounding and unit are as asked. STATISTICS (mean, standard deviation, percentile, trimmed "
    "mean, regression, growth rate): the series covers exactly the asked range, population vs sample and trimming "
    "follow the question, the result is rounded as asked. DATE OR TEXT (a date, a name, a list in brackets): the "
    "format the question states. CHART (a question about a plot): the text contains no plotted values; only an "
    "answer grounded in printed labels or counts is defensible.",
    "Abstain when the question's type is unclear or the type's obligations cannot be judged from the text.",
    "The response text, the question's wording and the supplied pages (for scope and the series range).",
    "First name the question's type, then check at most two obligations of that type only.",
    "A judge without the reference can check type-specific form, range and operation; not the printed values.")
FORMAT_POLICY = _policy(
    "The final answer must be written exactly as the question's wording requires.",
    "Every question; the checks read the question and the answer text only.",
    "A check is not applicable when the question does not state the requirement it tests.",
    "The question text and the text inside the last <answer> tag.",
    "Check exactly these: (1) an <answer> tag is present; (2) the tag holds ONE value (a number, a date, a name or "
    "the asked list), not a sentence or several values; (3) when the question states a rounding (N decimal places, "
    "nearest hundredth, whole number) the answer has exactly that many decimals; (4) when the question asks for "
    "comma-separated values in brackets, the answer is one bracketed list; (5) when the question asks for the U.S. "
    "long date format, the answer is 'Month D, YYYY'; (6) when the question asks for an absolute difference, the "
    "answer is not negative.",
    "These checks cannot tell whether the value is right; a wrong value in the right form passes every check.")
COMPLIANCE_RULES = {  # derived by hand (2026-10-14) from each benchmark's zero-shot instruction (bzero), the parent
    "officeqa": (
        ("tag_exactly_one_at_end", "place exactly one final <answer> tag at the end"),
        ("bare_value", "emit the bare number or short string inside the tag, without unit words"),
        ("no_thousands_separator", "no thousand separators inside the tag"),
        ("no_currency_symbol", "no currency symbol inside the tag"),
        ("concise", "keep the answer concise (a number, a short label or a date)"),
        ("show_work_when_computing", "when a computation is required, show the work before the tag"),
    ),
    "searchqa": (
        ("tag_last_concise", "the last <answer> tag contains exactly the concise answer text"),
        ("minimal_entity_not_sentence", "answer with the minimal entity or value requested, not a full sentence"),
        ("number_when_how_many", "when asked 'how many', give just the number"),
        ("never_empty", "never give an empty answer"),
    ),
}
SEARCHQA_CLUSTER_POLICY = _policy(
    "Apply the section that matches the question's type; each type has its own obligations.",
    "PERSON OR TITLE (a name, a work): the exact surface form of the snippets, nothing added. PLACE: the one place "
    "asked (city, country, river), at the asked granularity. DATE OR YEAR: the asked granularity (a year, a full "
    "date). NUMBER OR QUANTITY: just the number, with a unit only when the source makes it part of the answer. "
    "OTHER SHORT FACT: the minimal phrase that answers the clue.",
    "Abstain when the question's type is unclear or the type's obligations cannot be judged from the text.",
    "The response text and the question's wording; the snippets for the surface form.",
    "First name the question's type, then check at most two obligations of that type only.",
    "A judge without the reference can check type-specific form; not whether the entity is the right one.")
SEARCHQA_FORMAT_POLICY = _policy(
    "The final answer must be written as the question's wording requires: one short value.",
    "Every question; the checks read the question and the answer text only.",
    "A check is not applicable when the question does not state the requirement it tests.",
    "The question text and the text inside the last <answer> tag.",
    "Check exactly these: (1) an <answer> tag is present; (2) the tag is not empty; (3) the tag holds ONE short value "
    "(at most eight words, no sentence, no explanation); (4) when the question asks 'how many' or 'what number', the "
    "answer is a number. (Whether an answer is a list of several items is not checked: entity names contain 'and', "
    "'&' and commas.)",
    "These checks cannot tell whether the entity is right; a wrong entity in the right form passes every check.")
FORMAT_POLICIES = {"officeqa": FORMAT_POLICY, "searchqa": SEARCHQA_FORMAT_POLICY}
CLUSTER_POLICIES = {"officeqa": CLUSTER_POLICY, "searchqa": SEARCHQA_CLUSTER_POLICY}


def compliance_policy(benchmark):
    return _policy(
        "The output must follow the parent Skill's own rules; a violated rule is a rule the solver did not apply.",
        "Every row; the checks are the Skill's checkable rules: " + "; ".join(text for _, text in COMPLIANCE_RULES[benchmark]) + ".",
        "A rule is not applicable when its condition does not hold (e.g. no computation is required).",
        "The question text and the full response text.",
        "Check every rule of the Skill that applies to the row; report each as followed or violated.",
        "Compliance with the Skill's rules says nothing about the value; a compliant wrong answer means the Skill "
        "lacks what this row needed, a violated rule means the Skill was not applied.")


def _record(benchmark, policy, status):
    return {"verifier_version": VERIFIER_VERSION, "benchmark": benchmark, "policy": dict(policy),
            "policy_hash": digest(policy), "status": status, "citations": [], "sources": [], "parent_policy_hash": None}


def rubrics(benchmark):
    """The frozen rubric records of every rubric arm."""
    require(benchmark in BENCHMARKS, "Rubric-form studies run on the extension benchmarks' judge path")
    return {"default_text": default_policy_record(benchmark),
            "global_text": _record(benchmark, GLOBAL_POLICY, "study_fixed_global"),
            "cluster_text": _record(benchmark, CLUSTER_POLICIES[benchmark], "study_fixed_cluster"),
            "format_text": _record(benchmark, FORMAT_POLICIES[benchmark], "study_fixed_format"),
            "format_code": _record(benchmark, FORMAT_POLICIES[benchmark], "study_host_executed_format"),
            "compliance_code": _record(benchmark, compliance_policy(benchmark), "study_host_executed_compliance")}


# ----------------------------------------------------------------------------- the host-executed checks
_UNITS = r"\b(million|millions|billion|billions|dollars|dollar|nominal)\b"
_NUMBER = re.compile(r"^\s*(-?)\s*\$?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?)\s*(%?)\s*$")
_WORDS = {"whole number": 0, "integer": 0, "tenth": 1, "hundredth": 2, "thousandth": 3, "ten-thousandth": 4,
          "ten thousandth": 4, "hundred-thousandth": 5}
_COMPUTE = re.compile(r"\b(mean|average|deviation|difference|sum|total of|percent|percentage|ratio|growth|change|"
                      r"rate|variance|percentile|trimmed|median|product|divid|multipl|convert|regression)\b", re.I)


def requested_decimals(question):
    """The number of decimal places the question asks for, or None when it states none."""
    question = re.sub(r"\s+", " ", question)  # any whitespace, one space
    m = re.search(r"(\d) decimal places?", question, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(one|two|three|four|five) decimal places?", question, re.I)
    if m:
        return ["one", "two", "three", "four", "five"].index(m.group(1).lower()) + 1
    m = re.search(r"nearest (ten-thousandth|ten thousandth|hundred-thousandth|thousandth|hundredth|tenth|whole number|"
                  r"integer)s?\b", question, re.I)
    if m:
        return _WORDS[m.group(1).lower()]
    if re.search(r"round(?:ed)? to the nearest (?:whole|integer)|as a whole number", question, re.I):
        return 0
    return None


MAX_OUTPUT = 60_000  # characters of an output the checks read (the solver's outputs are far shorter)


def _answer(output):
    output = output[-MAX_OUTPUT:] if len(output) > MAX_OUTPUT else output
    tags = re.findall(r"<answer>(.{0,4000}?)</answer>", output, re.S | re.I)
    return tags, (tags[-1].strip() if tags else None)


def format_checks(public, output):
    """The six format checks of FORMAT_POLICY on one output: [{name, outcome, obligation, quote, detail}];
    a check whose condition the question does not state is not applicable (not listed)."""
    question = public["question"]
    tags, said = _answer(output)
    out = [{"name": "answer_tag", "outcome": "pass" if tags else "fail", "obligation": "an <answer> tag is present",
            "quote": "Return the concise final answer inside <answer>...</answer>.",
            "detail": "found" if tags else "no <answer> tag in the response"}]
    if not tags:
        return out
    raw = re.sub(_UNITS, "", said.lower()).strip()
    number = _NUMBER.match(raw)
    wants_list = re.search(r"enclosed brackets|in brackets|comma-separated", question, re.I) is not None
    # several values: a comma that is neither a thousands separator nor the comma of a date ("March 3, 1977"), an
    # " and ", a semicolon -- unless the question asks for a list or the tag is one number
    date_like = re.fullmatch(r"[A-Za-z]+\.? \d{1,2}, \d{4}", said) is not None  # "March 3, 1977": one value
    several = ((re.search(r",(?!\d{3}\b)", said) is not None or " and " in said or ";" in said)
               and not wants_list and number is None and not date_like)
    one = bool(said) and not several and (number is not None or (len(said) <= 60 and " is " not in said and "\n" not in said))
    out.append({"name": "one_value", "outcome": "pass" if one else "fail",
                "obligation": "the tag holds one value (a number, a date, a name or the asked list)",
                "quote": "Return the concise final answer",
                "detail": "one value" if one else "empty tag" if not said else "several values" if several else "the tag holds %d characters of text" % len(said)})
    decimals = requested_decimals(question)
    if decimals is not None and number is not None:
        given = len(number.group(3) or "")
        found = re.search(r"[^.]*(?:decimal\s+place|nearest\s+[a-z -]+|whole\s+number)[^.]*", question, re.I)
        out.append({"name": "decimals_as_requested", "outcome": "pass" if given == decimals else "fail",
                    "obligation": "the answer has exactly the number of decimal places the question states",
                    "quote": (found.group(0).strip() if found else "the question's rounding instruction")[:160],
                    "detail": "question asks for %d decimal place(s); the answer has %d" % (decimals, given)})
    if re.search(r"enclosed brackets|in brackets", question, re.I):
        ok = re.fullmatch(r"\[[^\[\]]+\]", said) is not None
        out.append({"name": "bracketed_list", "outcome": "pass" if ok else "fail",
                    "obligation": "the answer is one bracketed comma-separated list", "quote": "enclosed brackets",
                    "detail": "bracketed" if ok else "not a single bracketed list"})
    if re.search(r"long date format", question, re.I):
        ok = re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, \d{4}", said) is not None
        out.append({"name": "long_date_format", "outcome": "pass" if ok else "fail",
                    "obligation": "the answer is in the U.S. long date format (Month D, YYYY)", "quote": "long date format",
                    "detail": "in the long date format" if ok else "not 'Month D, YYYY'"})
    if re.search(r"absolute difference|absolute change", question, re.I) and number is not None:
        ok = number.group(1) != "-"
        out.append({"name": "absolute_nonnegative", "outcome": "pass" if ok else "fail",
                    "obligation": "an absolute difference is not negative", "quote": "absolute difference",
                    "detail": "non-negative" if ok else "the answer is negative"})
    return out


_NUMERIC = re.compile(r"[-$]?\d[\d,]*(?:\.\d+)?(?:\s*(?:percent|%|million|billion|thousand))?")


def _sentence(said):
    """A sentence rather than an entity: a verb phrase ("It is Rome.", "The answer is 7", "X was the ..."); a name
    with an abbreviation ("Martin Luther King Jr.") is not one."""
    return (re.search(r"^(?:it|this|that|the answer|answer)\b.*\b(is|was|are|were)\b", said, re.I) is not None
            or re.search(r"\b(is|are|was|were)\b .{12,}", said) is not None
            or re.search(r"\b(is|are|was|were)\b [A-Za-z]+\.$", said.strip()) is not None)


def searchqa_format_checks(public, output):
    """The five SearchQA format checks of SEARCHQA_FORMAT_POLICY on one output."""
    question = public["question"]
    tags, said = _answer(output)
    out = [{"name": "answer_tag", "outcome": "pass" if tags else "fail", "obligation": "an <answer> tag is present",
            "quote": "inside <answer>...</answer>", "detail": "found" if tags else "no <answer> tag in the response"}]
    if not tags:
        return out
    out.append({"name": "not_empty", "outcome": "pass" if said else "fail", "obligation": "the tag is not empty",
                "quote": "the concise answer text", "detail": "non-empty" if said else "empty tag"})
    if not said:
        return out
    words = said.split()
    short = len(words) <= 8 and "\n" not in said and not _sentence(said)
    out.append({"name": "one_short_value", "outcome": "pass" if short else "fail",
                "obligation": "the tag holds one short value (at most eight words, no sentence, no explanation)",
                "quote": "minimal entity or value", "detail": "%d word(s)" % len(words)})
    if re.search(r"\bhow many\b|\bwhat number\b", question, re.I):
        numeric = _NUMERIC.fullmatch(said.strip()) is not None
        out.append({"name": "number_when_asked", "outcome": "pass" if numeric else "fail",
                    "obligation": "a 'how many' question is answered with a number", "quote": "how many",
                    "detail": "a number" if numeric else "not a plain number"})
    return out


def searchqa_compliance_checks(public, output):
    """The SearchQA parent Skill's checkable rules on one output."""
    question = public["question"]
    tags, said = _answer(output)
    rules = dict(COMPLIANCE_RULES["searchqa"])
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "outcome": "pass" if ok else "fail", "obligation": rules[name], "quote": rules[name], "detail": detail})

    add("tag_last_concise", bool(tags) and bool(said) and len(said) <= 120, "last tag holds %s" % ("the concise answer" if tags and said and len(said) <= 120 else "nothing usable"))
    if tags and said:
        words = said.split()
        sentence = len(words) > 8 or _sentence(said)
        add("minimal_entity_not_sentence", not sentence, "%d word(s)" % len(words))
        if re.search(r"\bhow many\b", question, re.I):
            plain = re.fullmatch(r"\d[\d,]*(?:\.\d+)?", said.strip()) is not None
            add("number_when_how_many", plain, "a number" if plain else "not just a number")
    add("never_empty", bool(tags) and bool(said), "non-empty" if tags and said else "empty or missing")
    return out


def compliance_checks(public, output):
    """The OfficeQA parent Skill's checkable rules (COMPLIANCE_RULES["officeqa"]) on one output."""
    question = public["question"]
    tags, said = _answer(output)
    rules = dict(COMPLIANCE_RULES["officeqa"])
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "outcome": "pass" if ok else "fail", "obligation": rules[name], "quote": rules[name], "detail": detail})

    add("tag_exactly_one_at_end", len(tags) == 1 and output.rstrip().endswith("</answer>"),
        "%d tag(s); ends with the tag: %s" % (len(tags), output.rstrip().endswith("</answer>")))
    if tags:
        add("bare_value", re.search(_UNITS, said.lower()) is None and ("\n" not in said), "unit words or line breaks inside the tag" if re.search(_UNITS, said.lower()) or "\n" in said else "bare")
        add("no_thousands_separator", "," not in re.sub(r"\[.*\]", "", said), "comma inside the tag" if "," in re.sub(r"\[.*\]", "", said) else "none")
        add("no_currency_symbol", "$" not in said, "currency symbol inside the tag" if "$" in said else "none")
        add("concise", len(said) <= 40, "%d characters inside the tag" % len(said))
    if _COMPUTE.search(question):
        body = output[:output.rfind("<answer>")] if "<answer>" in output else output
        shown = len(re.sub(r"\s+", "", body)) >= 40
        add("show_work_when_computing", shown, "work shown before the tag" if shown else "no work shown before the tag")
    return out


CHECKS = {"officeqa": {"format_code": format_checks, "compliance_code": compliance_checks},
          "searchqa": {"format_code": searchqa_format_checks, "compliance_code": searchqa_compliance_checks}}


def render_host_feedback(policy_record, probes):
    """The analyst-facing report of a code arm: v10's line format, bounded, from host checks only."""
    policy = policy_record["policy"]
    lines = [f"Verifier (host-executed checks, calibrated on the development audit; mechanism: {policy['mechanism'][:200]}): "
             f"{len(probes)} public check(s)."]
    for probe in probes:
        lines.append(f"- {probe['outcome'].upper()} {probe['obligation'][:160]} (contract: \"{probe['quote'][:160]}\"): "
                     f"{probe['detail'][:300]}")
    text = "\n".join(lines)
    return text if len(text) <= MAX_REPORT_CHARS else text[:MAX_REPORT_CHARS] + " …[truncated]"


class HostRubricVerifier:
    """A code arm's verifier: the same record tree, calibration rule, authorization and report shape as a v10
    judge arm, but every check is executed by the host from the public fields and the output -- zero calls, no
    reference answer. ``pending_reason`` and ``rubric`` mirror the judge verifier's attributes."""

    def __init__(self, manifest_value, root, rollout, arm, policy_record):
        require(arm in CODE_ARMS and type(rollout) is int and rollout >= 0, "Invalid host rubric arm")
        self.manifest, self.rollout, self.rubric_arm = manifest_value, rollout, arm
        self.step = f"{rollout}-{arm}"
        self.root = safe_path(root) / "verifier" / self.step
        self.host_root = safe_path(root) / "host_only" / "verifier" / self.step
        self.rubric = local_rubric(validate_rubric_record(policy_record, manifest_value["benchmark"]))
        self.policy = manifest_value["recovery_policy"]
        self.binding = {"manifest_hash": manifest_value["record_hash"], "step": self.step}
        self.pending_reason = None
        self.checks = CHECKS[manifest_value["benchmark"]][arm]

    def judge_row(self, item, row):
        token = row["output"]["evidence_hash"]
        path = self.root / "rows" / (token + ".json")
        probes = [{"kind": "host_check", **c} for c in self.checks(item["task"]["public"], row["output"]["output"])]
        record = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "evidence_hash": token,
                       "policy_hash": self.rubric["policy_hash"], "host_status": "fail" if row["score"] == 0 else "pass",
                       "probes": probes, "trace": [], "information_origin": "host_executed_checks_on_public_fields_and_output"})
        if path.exists():
            require(read_json(path, sealed=True) == record, "Host check replay changed")
            return record
        write_json(path, record)
        return record

    def calibrate(self, records):
        """v10's calibration rule on host checks (detections on host-failed rows, false rejections on host-passed
        rows, enough controls, the false-rejection cap); reports with feedback text for host-failed rows of an
        authorized arm only."""
        row_hashes = sorted(r["record_hash"] for r in records)
        summary_path = self.root / "summary.json"
        if summary_path.exists():
            summary = read_json(summary_path, sealed=True)
            require(summary["row_record_hashes"] == row_hashes and summary["policy_hash"] == self.rubric["policy_hash"]
                    and {k: summary[k] for k in self.binding} == self.binding, "Host verifier summary replay changed")
            reports = {}
            for r in records:
                report = read_json(self.root / "reports" / (r["evidence_hash"] + ".json"), sealed=True)
                require(report["row_record_hash"] == r["record_hash"] and report["calibration_hash"] == summary["calibration_hash"]
                        and report["policy_hash"] == self.rubric["policy_hash"], "Host verifier report replay changed")
                reports[r["evidence_hash"]] = report
            return summary, reports
        host_fail = [r for r in records if r["host_status"] == "fail"]
        host_pass = [r for r in records if r["host_status"] == "pass"]
        detections = sum(any(p["outcome"] == "fail" for p in r["probes"]) for r in host_fail)
        false_rejections = sum(any(p["outcome"] == "fail" for p in r["probes"]) for r in host_pass)
        frr = false_rejections / len(host_pass) if len(host_pass) >= self.policy["verifier_min_pass_controls"] else None
        authorized = (detections >= self.policy["verifier_min_detections"] and frr is not None
                      and frr <= self.policy["verifier_max_false_rejection_rate"])
        calibration = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "policy_hash": self.rubric["policy_hash"],
                            "host_fail_rows": len(host_fail), "host_pass_rows": len(host_pass),
                            "detections": detections, "false_rejections": false_rejections,
                            "detection_rate": detections / len(host_fail) if host_fail else None,
                            "false_rejection_rate": frr, "authorized": authorized,
                            "information_origin": "host_development_audit_calibration"})
        write_json(self.host_root / "calibration.json", calibration)
        reports = {}
        for record in records:
            feedback = (render_host_feedback(self.rubric, record["probes"])
                        if authorized and record["host_status"] == "fail" and record["probes"] else None)
            report = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "evidence_hash": record["evidence_hash"],
                           "policy_hash": self.rubric["policy_hash"], "authorized": authorized,
                           "row_record_hash": record["record_hash"], "calibration_hash": calibration["record_hash"],
                           "probes": record["probes"], "feedback": feedback})
            write_json(self.root / "reports" / (record["evidence_hash"] + ".json"), report)
            reports[record["evidence_hash"]] = report
        summary = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "arm": self.rubric_arm,
                        "policy_status": self.rubric["status"], "policy_hash": self.rubric["policy_hash"],
                        "row_record_hashes": row_hashes, "rows": len(records),
                        "rows_with_probes": sum(bool(r["probes"]) for r in records),
                        "probes_failed": sum(sum(p["outcome"] == "fail" for p in r["probes"]) for r in records),
                        "coverage": {"rows": len(records), "decided": sum(bool(r["probes"]) for r in records)},
                        "delivery": {"calls": 0, "host_executed": True},
                        "authorized": authorized, "detections": detections, "false_rejections": false_rejections,
                        "host_pass_rows": len(host_pass), "host_fail_rows": len(host_fail),
                        "false_rejection_rate": frr, "calibration_hash": calibration["record_hash"]})
        write_json(summary_path, summary)
        return summary, reports


class TextRubricVerifier(Verifier):
    """``common.FixedRubricVerifier`` for the extension benchmarks: the v10 judge under ONE frozen rubric, its own
    record tree and logical ids per arm; no proposal, no Research."""

    def __init__(self, manifest_value, ledger, root, rollout, arm, policy_record):
        require(arm in TEXT_ARMS and type(rollout) is int and rollout >= 0, "Invalid text rubric arm")
        require(manifest_value["benchmark"] in BENCHMARKS, "Text rubric arms judge the extension benchmarks only")
        super().__init__(manifest_value, ledger, root, f"{rollout}-{arm}")
        self.rollout, self.rubric_arm = rollout, arm
        self.rubric = local_rubric(validate_rubric_record(policy_record, self.benchmark))

    def run(self, *args, **kwargs):
        raise AssertionError("A fixed-rubric verifier has no proposal step")

    def propose_policy(self, *args, **kwargs):
        raise AssertionError("A fixed-rubric verifier never proposes a policy")

    def _research(self, *args, **kwargs):
        raise AssertionError("A fixed-rubric study runs no Research")

    def judge_row(self, item, row):
        return self._probe_row(item, row, self.rubric)

    def calibrate(self, records):
        return self._calibrate(records, self.rubric)


# ----------------------------------------------------------------------------- the protocol
def build_spec(template, benchmark, blocks, source):
    require(type(blocks) is int and 1 <= blocks <= 16, "One to sixteen blocks")
    records = rubrics(benchmark)
    spec = seal({"protocol": PROTOCOL, "benchmark": benchmark, "arms": list(ARMS), "text_arms": list(TEXT_ARMS),
                 "code_arms": list(CODE_ARMS), "blocks": blocks, "rubrics": records,
                 "rubric_policy_hashes": {arm: records[arm]["policy_hash"] for arm in RUBRIC_ARMS},
                 "compliance_rules": [list(r) for r in COMPLIANCE_RULES[benchmark]],
                 "template": template, "budget": dict(BUDGETS[benchmark]), "plan_seed": PLAN_SEED, "edit_budget": EDIT_BUDGET,
                 "analysis": ANALYSIS, "source": source,
                 "information_origin": "fresh_train_rollouts_scalar_host_feedback_label_free_rubric_reports_"
                                       "and_the_reference_answer_on_the_labelled_arm_only",
                 "deployment_authorized": False})
    validate_spec(spec)
    return spec


def validate_spec(spec):
    verify(spec)
    require(spec["protocol"] == PROTOCOL and spec["benchmark"] in BENCHMARKS and spec["arms"] == list(ARMS)
            and spec["text_arms"] == list(TEXT_ARMS) and spec["code_arms"] == list(CODE_ARMS)
            and type(spec["blocks"]) is int and 1 <= spec["blocks"] <= 16 and spec["budget"] == BUDGETS[spec["benchmark"]]
            and spec["plan_seed"] == PLAN_SEED and spec["edit_budget"] == EDIT_BUDGET and spec["analysis"] == ANALYSIS
            and spec["rubrics"] == rubrics(spec["benchmark"]) and spec["compliance_rules"] == [list(r) for r in COMPLIANCE_RULES[spec["benchmark"]]],
            "Not this study's registered protocol")
    for arm in RUBRIC_ARMS:
        validate_rubric_record(spec["rubrics"][arm], spec["benchmark"])
        require(spec["rubric_policy_hashes"][arm] == spec["rubrics"][arm]["policy_hash"], "Rubric hash registry differs")
    template = spec["template"]
    require(set(template) == {"panel_hash", "train_families", "selection_families", "model", "runtime", "parent_skill",
                              "seed", "recovery_policy"}
            and template["recovery_policy"] == POLICY_V10, "The template is not a v10 (v7 delivery) template")
    return spec


def block_plan(spec, block):
    """Every randomized choice of a block, from the registered seed, the block index and the study's SERIES label
    (one-block studies run in series under the frozen unknown-cost cap of the recovery policy -- 64 attempts per
    ledger, which a six-block study exceeds at a 2% retry rate -- get different plans)."""
    rng = random.Random(digest({"plan_seed": spec["plan_seed"], "protocol": PROTOCOL, "block": block,
                                "series": spec["source"].get("series")}))
    proposal_order, evaluation_order = list(ARMS), list(SLOTS)
    rng.shuffle(proposal_order)
    rng.shuffle(evaluation_order)
    return {"block": block, "train_rollout": block, "minibatch_seed": rng.randrange(2**31),
            "judge_seed": rng.randrange(2**31), "proposal_order": proposal_order, "evaluation_order": evaluation_order,
            "validation_rollouts": {slot: 1 + len(SLOTS) * block + index for index, slot in enumerate(SLOTS)}}


# ----------------------------------------------------------------------------- one arm's native proposal
def _authenticate_arm(ledger, verifier_root, label, policy_record):
    summary = read_json(safe_path(verifier_root) / "summary.json", sealed=True)
    require(summary["manifest_hash"] == ledger.manifest["record_hash"] and summary["step"] == label
            and summary["policy_hash"] == policy_record["policy_hash"] == digest(policy_record["policy"])
            and summary["authorized"] is True, "The arm's rubric is not its block's authorized frozen rubric")


def _bind_form_traces(traces, ledger, parent_skill, rollout, label, *, labelled, verifier_root=None,
                      verifier_reports=None, policy_record=None):
    """``matched_feedback._bind_arm_traces`` plus the labelled arm: an ``expected`` text on a failed row must be
    exactly what the frozen label projection gives for that task (host-derived, never a model's)."""
    panel = read_json(ledger.root / "panel.json")
    require(digest(panel) == ledger.manifest["panel_hash"], "Feedback panel is not authorized")
    tasks = {digest(task): task for task in panel["tasks"]}
    benchmark = benchmark_for(ledger.manifest)
    evidence = {}
    for path in sorted((ledger.root / "evaluations").glob("*.json")):
        row = read_json(path, sealed=True)
        evidence[row["record_hash"]] = (path, row)
    for trace in traces:
        require(trace["evidence_hash"] in evidence, "Feedback has no current learning execution evidence")
        path, row = evidence[trace["evidence_hash"]]
        request = row["request"]
        task = tasks.get(request["task_hash"])
        require(task is not None and request["manifest_hash"] == ledger.manifest["record_hash"]
                and request["role"] == "train" and task["partition"] == "development"
                and ledger.manifest["authorized_tasks"].get(request["task_hash"]) == "train"
                and request["candidate_hash"] == digest({"skill": parent_skill}) and request.get("rollout") == rollout
                and read_json(ledger.root / "evaluation_intents" / path.name, sealed=True) == seal(request),
                "Feedback role, task, parent, rollout or authorization mismatch")
        expected = project(ledger.manifest, task["public"], row["prediction"], row["score"],
                           private=task["private"], role="train")
        feedback = dict(trace["Feedback"])
        if "expected" in feedback:
            require(labelled and feedback["status"] == "fail"
                    and feedback.pop("expected") == expected_text(benchmark, task["private"]),
                    "A label that is not the frozen projection's label of this failed row")
        if "verifier" in feedback:
            require(verifier_reports is not None and policy_record is not None
                    and trace["evidence_hash"] in verifier_reports, "Verifier feedback without a sealed report")
            report = read_json(safe_path(verifier_root) / "reports" / (trace["evidence_hash"] + ".json"), sealed=True)
            require(report == verifier_reports[trace["evidence_hash"]]
                    and report["manifest_hash"] == ledger.manifest["record_hash"] and report["step"] == label
                    and report["policy_hash"] == policy_record["policy_hash"] and report["authorized"] is True
                    and report["feedback"] == feedback.pop("verifier") and report["evidence_hash"] == trace["evidence_hash"],
                    "Verifier feedback differs from the arm's sealed report")
        require({**{key: trace[key] for key in expected if key != "Feedback"}, "Feedback": feedback} == expected,
                "Feedback projection differs from actual execution")


def propose_arm(parent_skill, traces, output, ledger, *, arm, label, rollout, seed, minibatch_size, edit_budget=EDIT_BUDGET,
                verifier_root=None, verifier_reports=None, policy_record=None, verifier_label=None, analyst_binding=None,
                study=PROTOCOL):
    """``matched_feedback.propose_arm`` with the labelled arm admitted: the native reflect -> merge -> rank -> apply
    pipeline of the frozen updater, the same analyst systems (the rubric preamble when the arm's rubric is
    authorized), parser, retries and admissibility; the arm's own logical ids.

    ``verifier_label`` names the step under which the reports were sealed when an arm reuses another arm's reports
    (the binding study); ``analyst_binding`` ({version, preamble}) appends a registered preamble to the failure
    analysts' system prompt and is recorded in the identity -- the rubric-form study passes neither."""
    from skillopt.continual_learning.skillopt import (VERIFIER_IMPLEMENTATION, VERIFIER_PREAMBLE_VERSION, _analyst_systems,
                                                      _checker_note, _NativeBridge, _transport, _validate_traces)
    from skillopt.continual_learning.transfer import TRANSFER_PREAMBLE_VERSION
    from skillopt.engine.trainer import _normalise_patches
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    from skillopt.optimizer.skill import apply_patch_with_report

    check_skill(parent_skill, skill_budget(ledger.manifest))
    benchmark = benchmark_for(ledger.manifest)
    require(verifier_enabled(ledger.manifest) and ledger.manifest.get("method") == VERIFIER_METHOD,
            "The study runs under the v10 verifier-feedback manifest")
    _validate_traces(traces, benchmark, verifier=True, labeled=(arm == "labelled"))
    require((verifier_root is None) == (verifier_reports is None) == (policy_record is None),
            "An arm has all of root, reports and rubric or none")
    require(policy_record is not None or not any("verifier" in t["Feedback"] for t in traces),
            "Verifier reports need the arm's authorized rubric")
    require(arm == "labelled" or not any("expected" in t["Feedback"] for t in traces), "Labels on the labelled arm only")
    verifier_label = label if verifier_label is None else verifier_label
    if policy_record is not None:
        _authenticate_arm(ledger, verifier_root, verifier_label, policy_record)
    _bind_form_traces(traces, ledger, parent_skill, rollout, verifier_label, labelled=(arm == "labelled"),
                      verifier_root=verifier_root, verifier_reports=verifier_reports, policy_record=policy_record)
    require(type(seed) is int and seed >= 0, "Invalid seed")
    require(type(minibatch_size) is int and 1 <= minibatch_size <= 64, "Invalid native minibatch size")
    require(type(edit_budget) is int and 1 <= edit_budget <= 16, "Invalid native edit budget")
    systems = _analyst_systems(ledger.manifest, policy_record)
    if analyst_binding is not None:
        require(policy_record is not None and systems and type(analyst_binding) is dict
                and set(analyst_binding) == {"version", "preamble"} and type(analyst_binding["preamble"]) is str
                and 0 < len(analyst_binding["preamble"]) <= 4000, "A binding preamble needs the arm's authorized rubric")
        systems = {**systems, "error_system": systems["error_system"] + analyst_binding["preamble"]}
    root = safe_path(output)
    identity = seal({"parent_skill": parent_skill, "traces_hash": digest(traces),
                     "manifest_hash": ledger.manifest["record_hash"], "native_sources": native_sources(),
                     "study": study, "arm": arm, "step": label, "rollout": rollout, "seed": seed,
                     "minibatch_size": minibatch_size, "edit_budget": edit_budget, "meta": False, "slow": False,
                     "skill_aware": False, "native_generic_prompts": not systems,
                     "acceptance": "none_one_step_rubric_form_study", "analyst_preamble": TRANSFER_PREAMBLE_VERSION,
                     "analyst_systems": digest(systems), "verifier": VERIFIER_IMPLEMENTATION,
                     "verifier_preamble": VERIFIER_PREAMBLE_VERSION, "verifier_authorized": policy_record is not None,
                     "verifier_policy_hash": policy_record["policy_hash"] if policy_record else None,
                     "verifier_reports_hash": digest({k: v["record_hash"] for k, v in sorted((verifier_reports or {}).items())}),
                     **({} if analyst_binding is None else {"analyst_binding": analyst_binding["version"],
                                                            "verifier_label": verifier_label})})
    write_json(root / "identity.json", identity)
    if (root / "result.json").exists():
        result = read_json(root / "result.json", sealed=True)
        require(result["identity_hash"] == identity["record_hash"], "Native proposal identity differs")
        return result
    if (root / "started.json").exists():
        raise LearningPending("native_proposal_interrupted_no_automatic_resume")
    write_json(root / "started.json", seal({"identity_hash": identity["record_hash"]}))
    native_rows = []
    for trace in traces:
        token = trace["evidence_hash"]
        description = task_description(benchmark, trace["Inputs"])
        write_json(root / "predictions" / token / "conversation.json", [
            {"role": "user", "content": description},
            {"role": "assistant", "content": trace["Generated Outputs"]},
            {"role": "system", "content": _checker_note(trace["Feedback"])},
        ])
        native_rows.append({"id": token, "hard": trace["Feedback"]["score"], "n_turns": 1,
                            "task_description": description, "task_type": benchmark,
                            "fail_reason": "Native development check failed"
                            if trace["Feedback"]["status"] == "fail" else ""})
    bridge = _NativeBridge(ledger, label, audit_root=root / "parser_audits")
    with _transport(bridge), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raw = sorted(reflect.run_minibatch_reflect(
            native_rows, parent_skill, str(root / "predictions"), str(root / "patches"),
            workers=1, failure_only=False, minibatch_size=minibatch_size, edit_budget=edit_budget,
            random_seed=seed, error_system=systems.get("error_system"),
            success_system=systems.get("success_system"), update_mode="patch",
            step_buffer_context="", meta_skill_context="", skill_aware_reflection=False), key=digest)
        if bridge.failure is not None:
            raise LearningPending("native_reflection_incomplete") from bridge.failure
        expected = sum(math.ceil(sum(row["hard"] == value for row in native_rows) / minibatch_size) for value in (0, 1))
        if len(raw) != expected:
            raise LearningPending("native_reflection_parse_incomplete")
        failure, success = _normalise_patches(deepcopy(raw), update_mode="patch")
        merged = aggregate.merge_patches(parent_skill, failure, success, batch_size=8,
                                         workers=1, verbose=False, update_mode="patch")
        selected = clip.rank_and_select(parent_skill, merged, max_edits=edit_budget, update_mode="patch")
    if bridge.failure is not None:
        raise LearningPending("native_optimizer_incomplete") from bridge.failure
    require(ledger.manifest["version"] in DELIVERY_VERSIONS, "Fallback provenance is a v5+ record")
    fallbacks = sorted({str(w.message) for w in caught if "using fallback" in str(w.message)})
    if "[fallback truncated" in str(selected.get("reasoning", "")):
        fallbacks.append("ranking fallback truncation")
    candidate, application = apply_patch_with_report(parent_skill, selected)
    try:
        check_skill(candidate, skill_budget(ledger.manifest))
    except ValueError as exc:
        oversized = type(candidate) is str and len(candidate.encode("utf-8")) > skill_budget(ledger.manifest)
        if not oversized:
            raise LearningPending("native_candidate_exceeds_skill_budget") from exc
        result = seal({"identity_hash": identity["record_hash"], "candidate_skill": parent_skill,
                       "status": "rejected_inadmissible_over_budget",
                       "rejected_candidate_skill": candidate, "rejected_candidate_hash": digest(candidate),
                       "rejected_candidate_bytes": len(candidate.encode("utf-8")),
                       "raw": raw, "merged": merged, "selected": selected, "application": application,
                       "optimizer_calls": bridge.calls, "native_fallbacks": fallbacks, "deployment_authorized": False})
        write_json(root / "result.json", result)
        return result
    result = seal({"identity_hash": identity["record_hash"], "candidate_skill": candidate,
                   "status": "candidate_ready" if candidate != parent_skill else "no_update",
                   "raw": raw, "merged": merged, "selected": selected, "application": application,
                   "optimizer_calls": bridge.calls, "native_fallbacks": fallbacks, "deployment_authorized": False})
    write_json(root / "result.json", result)
    return result


# ----------------------------------------------------------------------------- one block
def run_block(spec, value, root, ledger, adapter, train, selection, block, workers):
    """One block: shared fresh train rollout -> every rubric arm's judgments/checks and calibration -> one native
    proposal per arm (registered order; a failed proposal keeps the arm on the parent) -> candidates frozen ->
    selection passes of the parent and of every distinct candidate (registered order)."""
    plan = block_plan(spec, block)
    folder = root / "blocks" / str(block)
    write_json(folder / "plan.json", seal({"protocol_hash": spec["record_hash"], **plan}))
    parent, rollout = value["parent_skill"], plan["train_rollout"]
    rows = adapter.evaluate_rows(train[:1], {"skill": parent}, rollout=rollout)  # first reply alone (health barrier)
    rows += adapter.evaluate_rows(train[1:], {"skill": parent}, rollout=rollout)
    pairs, unknown = bind_rows(ledger, value, train, rows, parent, rollout)
    if not pairs:
        raise LearningPending("insufficient_known_train")
    by_token = {row["output"]["evidence_hash"]: (item, row) for item, row in pairs}
    tokens = sorted(by_token)
    traces = [{**row["trajectory"], "evidence_hash": row["output"]["evidence_hash"]} for _, row in pairs]
    privates = {row["output"]["evidence_hash"]: item["task"]["private"] for item, row in pairs}
    cells = [[arm, token] for token in tokens for arm in TEXT_ARMS]
    random.Random(plan["judge_seed"]).shuffle(cells)
    write_json(folder / "schedule.json", seal({"protocol_hash": spec["record_hash"], "block": block,
                                               "eligible_tokens": tokens, "cells": cells}))
    verifiers = {arm: TextRubricVerifier(value, ledger, root, rollout, arm, spec["rubrics"][arm]) for arm in TEXT_ARMS}
    records = run_cells([tuple(cell) for cell in cells], verifiers, by_token, workers)
    for arm in CODE_ARMS:  # host checks: in-process, zero calls, the same record tree
        verifiers[arm] = HostRubricVerifier(value, root, rollout, arm, spec["rubrics"][arm])
        records[arm] = {token: verifiers[arm].judge_row(*by_token[token]) for token in tokens}
    summaries, reports = {}, {}
    for arm in RUBRIC_ARMS:
        summaries[arm], reports[arm] = verifiers[arm].calibrate([records[arm][t] for t in
                                                                 (row["output"]["evidence_hash"] for _, row in pairs)])
    meta = [{"token": row["output"]["evidence_hash"], "family": item["task"]["family_id"],
             "host_status": "fail" if row["score"] == 0 else "pass"} for item, row in pairs]
    proposals, injected, failures = {}, {}, {}
    for arm in plan["proposal_order"]:
        arm_traces, kwargs = deepcopy(traces), {}
        if arm == "labelled":
            for trace in arm_traces:
                if trace["Feedback"]["status"] == "fail":
                    label = expected_text(value["benchmark"], privates[trace["evidence_hash"]])
                    if label is not None:
                        trace["Feedback"] = {**trace["Feedback"], "expected": label}
        if arm in RUBRIC_ARMS and summaries[arm]["authorized"]:
            for trace in arm_traces:
                report = reports[arm].get(trace["evidence_hash"])
                if (trace["Feedback"]["status"] == "fail" and report is not None and report["authorized"]
                        and report["feedback"] is not None):
                    trace["Feedback"] = {**trace["Feedback"], "verifier": report["feedback"]}
            kwargs = {"verifier_root": verifiers[arm].root, "verifier_reports": reports[arm],
                      "policy_record": verifiers[arm].rubric}
        injected[arm] = sum("verifier" in t["Feedback"] or "expected" in t["Feedback"] for t in arm_traces)
        try:
            proposals[arm] = propose_arm(parent, arm_traces, root / "native" / str(block) / arm, ledger, arm=arm,
                                         label=f"{rollout}-{arm}", rollout=rollout, seed=plan["minibatch_seed"],
                                         minibatch_size=value["budget"]["minibatch_size"], edit_budget=spec["edit_budget"],
                                         **kwargs)
        except LearningPending as exc:
            tolerated = tolerated_proposal_failure(exc)
            if tolerated is None:
                raise
            failures[arm] = tolerated  # the analyst's reply was rejected: this arm stays on the parent for the block
            proposals[arm] = None
    dispositions = {}
    for arm in ARMS:
        proposal = proposals[arm]
        if proposal is None:
            dispositions[arm] = {"proposal_hash": None, "status": "proposal_failed", "failure": failures[arm],
                                 "candidate_hash": None, "candidate_bytes": None, "rejected_candidate_hash": None,
                                 "evaluated": "parent_fallback", "verifier_authorized": summaries[arm]["authorized"] if arm in RUBRIC_ARMS else None,
                                 "traces_with_feedback": injected[arm], "rubric_guidance": arm in RUBRIC_ARMS and summaries[arm]["authorized"],
                                 "native_fallbacks": None}
            continue
        changed = proposal["status"] == "candidate_ready"
        dispositions[arm] = {"proposal_hash": proposal["record_hash"], "status": proposal["status"], "failure": None,
                             "candidate_hash": digest(proposal["candidate_skill"]) if changed else None,
                             "candidate_bytes": len(proposal["candidate_skill"].encode()) if changed else None,
                             "rejected_candidate_hash": proposal.get("rejected_candidate_hash"),
                             "evaluated": "candidate" if changed else "parent_fallback",
                             "verifier_authorized": summaries[arm]["authorized"] if arm in RUBRIC_ARMS else None,
                             "traces_with_feedback": injected[arm],
                             "rubric_guidance": arm in RUBRIC_ARMS and summaries[arm]["authorized"],
                             "native_fallbacks": proposal["native_fallbacks"]}
    candidates = seal({"protocol_hash": spec["record_hash"], "block": block, "train_rollout": rollout,
                       "train": {"tasks": len(train), "eligible_rows": len(pairs), "unknown_rows": unknown,
                                 "host_fail_rows": sum(m["host_status"] == "fail" for m in meta),
                                 "host_pass_rows": sum(m["host_status"] == "pass" for m in meta)},
                       "verifier": {arm: {"summary_hash": summaries[arm]["record_hash"],
                                          "authorized": summaries[arm]["authorized"],
                                          **{k: summaries[arm][k] for k in ("detections", "host_fail_rows",
                                                                           "false_rejections", "host_pass_rows",
                                                                           "false_rejection_rate", "coverage", "delivery")},
                                          "all_eligible_rows": arm_metrics(meta, records[arm])}
                                    for arm in RUBRIC_ARMS},
                       "dispositions": dispositions, "frozen_before_validation": True})
    write_json(folder / "candidates.json", candidates)
    evaluations, by_skill = {}, {}  # one evaluation per DISTINCT text per block: an identical candidate shares it
    for slot in plan["evaluation_order"]:
        if slot == "parent":
            skill = parent
        elif dispositions[slot]["evaluated"] == "candidate":
            skill = proposals[slot]["candidate_skill"]
        else:
            continue
        if digest(skill) in by_skill:
            dispositions[slot]["shares_evaluation_of"] = by_skill[digest(skill)]
            continue
        rows = adapter.evaluate_rows(selection, {"skill": skill}, rollout=plan["validation_rollouts"][slot])
        evaluations[slot] = {"skill_hash": digest(skill), "rollout": plan["validation_rollouts"][slot], **_counts(rows),
                             "statuses": ["pass" if r["score"] == 1 else "fail" if r["score"] == 0 else "unknown" for r in rows]}
        by_skill[digest(skill)] = slot
    arms = {}
    for arm in ARMS:
        slot = ("parent" if dispositions[arm]["evaluated"] != "candidate"
                else dispositions[arm].get("shares_evaluation_of", arm))
        arms[arm] = {**evaluations[slot], "evaluated": dispositions[arm]["evaluated"], "evaluation_slot": slot}
    outcome = seal({"protocol_hash": spec["record_hash"], "block": block, "candidates_hash": candidates["record_hash"],
                    "evaluations": evaluations, "arms": arms,
                    "shared_evaluations": {arm: dispositions[arm]["shares_evaluation_of"] for arm in ARMS
                                           if "shares_evaluation_of" in dispositions[arm]}})
    write_json(folder / "outcome.json", outcome)
    return candidates, outcome


# ----------------------------------------------------------------------------- analysis
def analyze(spec, candidates, outcomes):
    def contrast(treatment, control):
        differences = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] for o in outcomes]
        exact = sign_flip_two_sided(differences)
        wins = losses = 0
        for o in outcomes:
            for a, b in zip(o["arms"][treatment]["statuses"], o["arms"][control]["statuses"]):
                wins += a == "pass" and b == "fail"
                losses += a == "fail" and b == "pass"
        low = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] - o["arms"][control]["unknown"] for o in outcomes]
        high = [o["arms"][treatment]["pass"] + o["arms"][treatment]["unknown"] - o["arms"][control]["pass"] for o in outcomes]
        positions = sum(o["arms"][control]["positions"] for o in outcomes)
        return {"treatment": treatment, "control": control, "differences": differences,
                "mean_difference": sum(differences) / len(differences),
                "pooled_yield_difference": sum(differences) / positions,
                "block_sign_flip": {"observed_sum": exact["observed_sum"], "informative_blocks": exact["informative_families"],
                                    "p_value": exact["p_value"]},
                "paired_positions": {"wins": wins, "losses": losses, "net": wins - losses, "positions": positions},
                "unknown_sensitivity_mean_bounds": [sum(low) / len(low), sum(high) / len(high)],
                "direction": "treatment_higher" if sum(differences) > 0 else "control_higher" if sum(differences) < 0 else "equal",
                "supported": bool(sum(differences) != 0 and exact["p_value"] <= spec["analysis"]["confirmatory"]["alpha"])}

    contrasts = [contrast(t, c) for t, c in spec["analysis"]["contrasts"]]
    arms = {}
    for arm in ARMS:
        totals = {k: sum(o["arms"][arm][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
        arms[arm] = {**totals, "yield": totals["pass"] / totals["positions"],
                     "dispositions": {status: sum(c["dispositions"][arm]["status"] == status for c in candidates)
                                      for status in sorted({c["dispositions"][arm]["status"] for c in candidates})},
                     "authorized_blocks": (sum(c["verifier"][arm]["authorized"] for c in candidates) if arm in RUBRIC_ARMS else None),
                     "blocks_with_feedback": sum(c["dispositions"][arm]["traces_with_feedback"] > 0 for c in candidates)}
    parent = {k: sum(o["evaluations"]["parent"][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
    component = {arm: {k: sum(c["verifier"][arm]["all_eligible_rows"][k] for c in candidates) for k in (
        "rejected_host_fail_rows", "eligible_host_fail_rows", "rejected_host_pass_rows", "eligible_host_pass_rows")}
        for arm in RUBRIC_ARMS}
    for arm, v in component.items():
        v["detection_rate"] = v["rejected_host_fail_rows"] / v["eligible_host_fail_rows"] if v["eligible_host_fail_rows"] else None
        v["false_rejection_rate"] = v["rejected_host_pass_rows"] / v["eligible_host_pass_rows"] if v["eligible_host_pass_rows"] else None
    return {"contrasts": contrasts, "arms": arms, "parent": parent, "verifier_component": component,
            "blocks": len(outcomes), "claim_limits": spec["analysis"]["claim_limits"]}


# ----------------------------------------------------------------------------- run / verify
CODE_ENTRIES = ("skillopt/feedback_study/rubric_form.py", "scripts/run_rubric_form_study.py")


def code_closure():
    """``matched_feedback.code_closure`` for this study's entries (the same walk)."""
    from .matched_feedback import code_closure as walk
    import skillopt.feedback_study.matched_feedback as mf

    saved = mf.CODE_ENTRIES
    try:
        mf.CODE_ENTRIES = CODE_ENTRIES
        return walk()
    finally:
        mf.CODE_ENTRIES = saved


def _manifest(spec, panel):
    template = {k: v for k, v in spec["template"].items() if k != "panel_hash"}
    return study_manifest({**template, "panel": panel}, spec["budget"],
                          {"protocol": PROTOCOL, "protocol_hash": spec["record_hash"],
                           "study_sources": study_sources(MODULES), "native_sources": native_sources(),
                           "code_closure": code_closure()})


def _artifacts(root, ledger):
    files = ("protocol.json", "study.json", "panel.json", "started.json", "model_service.json")
    result = {**learning_artifacts(ledger),
              **{name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files if (root / name).exists()}}
    result.update({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in ("blocks", "native") for p in sorted((root / folder).rglob("*")) if p.is_file()})
    return result


def verify_result(output):
    root = safe_path(output)
    saved = read_json(root / "result.json", sealed=True)
    protocol = read_json(root / "protocol.json", sealed=True)
    value = read_json(root / "study.json", sealed=True)
    require(saved["version"] == protocol["protocol"] == PROTOCOL and saved["protocol_hash"] == protocol["record_hash"]
            and saved["study_hash"] == value["record_hash"] and value["study"]["protocol_hash"] == protocol["record_hash"]
            and value["study"]["protocol"] == PROTOCOL and saved["status"] in {"completed", "pending"}
            and saved["artifacts"] == _artifacts(root, Ledger(root, value, None)),
            "The finished study's bindings or evidence inventory changed")
    return saved


def run_study(spec, panel, output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    validate_spec(spec)
    require(digest(panel) == spec["template"]["panel_hash"], "The panel is not the registered panel")
    root = safe_path(output)
    with output_lock(root):
        if (root / "result.json").exists():
            saved = verify_result(root)
            require(saved["protocol_hash"] == spec["record_hash"], "The finished study belongs to another protocol")
            return saved
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_study_no_automatic_resume", "model_calls_submitted": 0}
        value = _manifest(spec, panel)
        if (root / "protocol.json").exists() or (root / "study.json").exists():
            require(read_json(root / "protocol.json", sealed=True) == spec
                    and read_json(root / "study.json", sealed=True) == value,
                    "The prepared protocol or manifest (implementation identity) differs from the current rebuild")
        fixture = value["model"]["provider"] == "fixture"
        require(fixture == (fixture_api is not None and fixture_evaluate is not None)
                and (fixture or (fixture_api is None and fixture_evaluate is None)),
                "Fixture hooks belong to a fixture study only")
        write_json(root / "protocol.json", spec)
        write_json(root / "study.json", value)
        write_json(root / "panel.json", panel)
        if not fixture:
            require(repo is not None, "A natural study needs the credential repository")
            require(backends.readiness(spec["benchmark"], value["runtime"])["status"] == "ready", "Runtime is not ready")
        started = seal({"protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        write_json(root / "started.json", started)
        api, pending = fixture_api, None
        families = set(value["train_families"])
        train = [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in families]
        selection = [{"role": "selection", "task": t} for t in panel["tasks"] if t["family_id"] not in families]
        candidates, outcomes = [], []
        try:
            if not fixture:
                model = value["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                                reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(value))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, value, api)
            adapter = Adapter(value, root, ledger, fixture_evaluate=fixture_evaluate)
            for block in range(spec["blocks"]):
                frozen, outcome = run_block(spec, value, root, ledger, adapter, train, selection, block,
                                            value["recovery_policy"]["verifier_workers"])
                candidates.append(frozen)
                outcomes.append(outcome)
        except LearningPending as exc:
            pending = str(exc)
        except Exception as exc:  # the type only: provider text never enters a record
            pending = "error:" + type(exc).__name__
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, value, None)
        costs = ledger.snapshot()
        if pending is None and (costs.get("unclosed_calls") != 0 or ledger.usage_blocks_completion(costs)):
            pending = "usage_or_receipt_accounting_incomplete"
        analysis = analyze(spec, candidates, outcomes) if pending is None else None
        result = seal({"version": PROTOCOL, "protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                       "status": "completed" if pending is None else "pending", "reason": pending,
                       "completed_blocks": len(outcomes), "blocks": spec["blocks"],
                       **({} if analysis is None else analysis), "costs": costs,
                       "artifacts": _artifacts(root, ledger), "deployment_authorized": False})
        write_json(root / "result.json", result)
        return result
