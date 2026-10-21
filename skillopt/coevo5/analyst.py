"""Rule proposals (registration §4 step 5).

The analyst (GLM-5.3) sees only the proposal half: its failure codes with their counts and meanings, a seeded sample of
its diagnosed failures (task, answer, reference, code), the current Skill, the bench's public task card and the
similarity map -- the names and public task cards of the bench's similar benches, and the stage's checkable similar
targets (§1.1). It proposes at most five rules, at most two of them for the similar placement when the stage has a
checkable similar target, each with its text, suggested placement, targeted codes, rationale and at most two research
questions. A reply that is not a valid proposal JSON twice leaves the stage without rules (a method-failure event,
§4). A proposal whose normalized text (case and whitespace) equals a parent rule or a lower-numbered proposal is
dropped.

v2 (registration delta §4): the analyst also sees at most four proposal-half answers that passed (contrast examples);
every rule cites 2-8 distinct task ids of the shown failures as evidence -- each cited item shown with a code the rule
targets, and every targeted code shown on some cited item -- and states what the parent already covers and what the
rule adds; a rule whose evidence fails is kept in the record but not tested (the rest of the reply stands). At a stage
with a checkable similar target the reply names its transfer candidate (a similar-placement rule) or "none" with a
reason. Proposal ids are positions in the reply, fixed before any filtering.

v3 (registration delta §4, §6): the prompt and the payload's ``limits`` state every field's limit; a rule row is
validated on its own -- an invalid row is recorded (``row_status``) and never tested, the rest of the reply stands; the
reply is invalid when its envelope is malformed or no row is valid. Rules may depend only on what the solver sees. The
analyst sees at most ``ANALYST_EXAMPLES`` failures on OfficeQA (with ``ANALYST_CONTEXT_CHARS`` of its pages) and
SpreadsheetBench (whose views carry the workbook preview and the answer-range cells).
"""
from __future__ import annotations

import hashlib
import json

from .examiner import answer_text, reference, task_view
from .protocol import (
    ANALYST_ATTEMPTS,
    ANALYST_CONTEXT_CHARS,
    ANALYST_EXAMPLES,
    APPLIES_WHEN,
    CONTRAST_EXAMPLES,
    EVIDENCE,
    MAX_ADDS_CHARS,
    MAX_COVERED_CHARS,
    MAX_QUESTION_CHARS,
    MAX_RATIONALE_CHARS,
    MAX_RESEARCH_QUESTIONS,
    MAX_RULE_CHARS,
    MAX_RULES,
    MAX_SIMILAR_RULES,
    MAX_TRANSFER_REASON_CHARS,
    ROLE_INPUT_BYTES,
    SIMILAR,
    TITLES,
    similar_targets,
)
from .roles import Invalid, fields, fit, items, text
from .skill import Rule

MAX_EXAMPLES = 40  # diagnosed proposal-half failures shown (seeded, round-robin over codes); v3: ANALYST_EXAMPLES
MAX_RATIONALE = MAX_RATIONALE_CHARS
MAX_QUESTION = MAX_QUESTION_CHARS

ANALYST_SYSTEM = (
    "You improve the guidance text (a \"Skill\") that is appended to the system prompt of a language model solving "
    "tasks of several kinds; each kind has its own section, opened by a line saying when it applies. You receive the "
    "current Skill, the section being improved now, its public task description, diagnosed failures of the solver on "
    "training tasks of that kind (with references), the failure codes with their meanings, and a few answers of the "
    "same kind that were correct. Propose at most five new rules for this section. A rule is one short, general "
    "instruction (at most 600 characters, no headings, no blank lines) that would help on future tasks of this kind; "
    "never state a fact about one specific task or its answer, and never steer the answer by how answers of this "
    "benchmark are usually distributed (for example which option is usually right). A rule may depend only on what "
    "the solver sees while solving -- the task and its supplied material -- never on the reference answer, on whether "
    "an answer is correct, or on a score. Target the remaining failures: "
    "for each rule, cite as evidence 2 to 8 distinct task_id values of the shown failures that it would fix -- each "
    "cited failure must carry one of the codes the rule targets, and every code the rule targets must appear on at "
    "least one cited failure; say in \"covered\" what the current Skill already says about this problem (a short "
    "quote, or \"none\") and in \"adds\" what the rule adds beyond it. A rule must not turn the shown correct answers "
    "into wrong ones. You also receive the kinds of tasks that are similar to this one and which of them a rule can be "
    "checked on. When a rule addresses something these similar kinds share, you may suggest the similar placement: "
    "the same text is then also added to the sections of those similar kinds. When the similar kinds can be checked, "
    "name in \"transfer\" the one rule you propose for the similar placement ({\"rule\": its 1-based position in your "
    "list}), or {\"none\": the reason no shown failure supports such a rule}. For each rule you may add up to two "
    "research questions -- general questions whose answer from public reference material (Wikipedia; Python, "
    "openpyxl or LibreOffice Calc function documentation) would make the rule more accurate; they must not quote or "
    "describe any task. Reply with one JSON object only: {\"rules\": [{\"text\": str, \"placement\": \"local\" or "
    "\"similar\", \"codes\": [failure codes it targets], \"evidence\": [task_id], \"covered\": str, \"adds\": str, "
    "\"rationale\": str, \"questions\": [str]}], \"transfer\": {\"rule\": int} or {\"none\": str}} (omit "
    "\"transfer\" when no similar kind can be checked). Limits, in characters: text 600, covered 200, adds 300, "
    "rationale 500, each question 300, the transfer reason 300; a rule that breaks a limit is discarded.")


def normalized(value):
    return " ".join(value.lower().split())


def _order(values, seed, tag):
    key = lambda v: hashlib.sha256(json.dumps([seed, tag, v]).encode()).hexdigest()  # noqa: E731
    return sorted(values, key=key)


def examples(failures, diagnoses, *, seed, tag, limit=MAX_EXAMPLES):
    """At most ``limit`` (40; v3: ``ANALYST_EXAMPLES``) proposal-half failures: codes by count (largest first, then
    name), one failure per code in turn, each code's failures in a seeded order."""
    by_code = {}
    for answer in failures:
        by_code.setdefault(diagnoses[answer["key"]]["code"], []).append(answer)
    queues = {code: [next(a for a in group if a["key"] == k)
                     for k in _order([a["key"] for a in group], seed, tag + ":" + code)]
              for code, group in by_code.items()}
    order = sorted(queues, key=lambda c: (-len(queues[c]), c))
    out = []
    while len(out) < limit and any(queues.values()):
        for code in order:
            if queues[code] and len(out) < limit:
                out.append(queues[code].pop(0))
    return out


def contrast(passed, *, seed, tag):
    """v2 §4: at most four proposal-half answers that passed, in a seeded order (one per item)."""
    first = {}
    for answer in passed:
        first.setdefault(answer["item"], answer)
    keys = _order(sorted(a["key"] for a in first.values()), seed, tag + ":contrast")[:CONTRAST_EXAMPLES]
    by_key = {a["key"]: a for a in first.values()}
    return [by_key[k] for k in keys]


def payload(benchmark, *, parent_text, failures, diagnoses, meanings, cards, seed, tag, passed=()):
    """The analyst's input (§4 step 5); ``failures``: the proposal half's failed answers; ``cards``: the public task
    card of every bench; v2: ``passed``, the proposal half's passed answers (the contrast examples' source)."""
    backward, forward = similar_targets(benchmark)
    counts = {}
    for answer in failures:
        code = diagnoses[answer["key"]]["code"]
        counts[code] = counts.get(code, 0) + 1
    shown = examples(failures, diagnoses, seed=seed, tag=tag, limit=ANALYST_EXAMPLES.get(benchmark, MAX_EXAMPLES))
    return fit({
        "section": TITLES[benchmark], "applies_when": APPLIES_WHEN[benchmark], "task_card": cards[benchmark],
        "current_skill": parent_text,
        "failures": {"total": len(failures), "by_code": dict(sorted(counts.items()))},
        "codes": [{"code": code, "meaning": meanings[code]} for code in sorted(counts)],
        "examples": [{"task_id": a["item"], "task": task_view(benchmark, a["public"], trace=a.get("trace"),
                                                             context_chars=ANALYST_CONTEXT_CHARS.get(benchmark)),
                      "answer": answer_text(benchmark, a["output"]), "reference": reference(benchmark, a),
                      "code": diagnoses[a["key"]]["code"]} for a in shown],
        "correct_examples": [{"task": task_view(benchmark, a["public"], trace=a.get("trace")),
                              "answer": answer_text(benchmark, a["output"]), "reference": reference(benchmark, a)}
                             for a in contrast(passed, seed=seed, tag=tag)],
        "similar": {"kinds": [{"section": TITLES[b], "task_card": cards[b]} for b in SIMILAR[benchmark]],
                    "checkable": [TITLES[b] for b in backward + forward]},
        "limits": {"rules": MAX_RULES, "similar_rules": MAX_SIMILAR_RULES if backward + forward else 0,
                   "questions_per_rule": MAX_RESEARCH_QUESTIONS, "rule_characters": MAX_RULE_CHARS,
                   "evidence": list(EVIDENCE), "covered_characters": MAX_COVERED_CHARS,
                   "adds_characters": MAX_ADDS_CHARS, "rationale_characters": MAX_RATIONALE,
                   "question_characters": MAX_QUESTION, "transfer_reason_characters": MAX_TRANSFER_REASON_CHARS},
    }, "examples", ROLE_INPUT_BYTES)  # v3 §6: the evidence is checked against the examples actually shown


def shown_codes(value):
    """{task_id: codes of its shown failures} -- what a rule's evidence is checked against (v2 §4)."""
    out = {}
    for example in value["examples"]:
        out.setdefault(example["task_id"], set()).add(example["code"])
    return out


def evidence_problem(evidence, codes, shown):
    """None when ``evidence`` (the rule's cited task ids) supports ``codes`` (the codes it targets) on the shown
    failures, else the reason (v2 §4)."""
    if type(evidence) is not list or not EVIDENCE[0] <= len(evidence) <= EVIDENCE[1]:
        return "evidence_count"
    if any(type(e) is not str for e in evidence) or len(set(evidence)) != len(evidence):
        return "evidence_ids"
    if any(e not in shown for e in evidence):
        return "evidence_not_shown"
    if any(not shown[e] & set(codes) for e in evidence):
        return "evidence_other_code"
    covered = set().union(*(shown[e] for e in evidence)) & set(codes)
    if covered != set(codes):
        return "code_without_evidence"
    return None


def _transfer(value, rules, checkable):
    """v2 §4: the reply's transfer slot -- {"rule": position} of a similar-placement rule or {"none": reason}; required
    at a stage with a checkable similar target (its absence makes the reply invalid), ignored at a stage without one.
    A position that names no similar rule is recorded as such; it never invalidates the reply or another rule."""
    if not checkable:
        return None
    slot = value.get("transfer")
    if type(slot) is not dict or len(slot) != 1 or not set(slot) <= {"rule", "none"}:
        raise Invalid("transfer")
    if "none" in slot:
        return {"none": text(slot["none"], limit=MAX_TRANSFER_REASON_CHARS)}  # "none" needs its reason
    position = slot["rule"]
    if type(position) is not int or not 1 <= position <= len(rules) or rules[position - 1]["placement"] != "similar":
        return {"rule": position if type(position) is int else None, "status": "not_a_similar_rule"}
    return {"rule": position, "status": "named"}


def _row(benchmark, codes, shown, checkable, row):
    """One rule row of the reply, validated on its own (v3 §4); raises ``Invalid`` (or ``ValueError``) when it cannot
    be used."""
    fields(row, ["text", "placement", "codes", "evidence", "covered", "adds", "rationale", "questions"])
    Rule("check", text(row["text"], limit=MAX_RULE_CHARS), benchmark)  # the rule format of §3
    if row["placement"] not in ("local", "similar") or (row["placement"] == "similar" and not checkable):
        raise Invalid("placement")
    targeted = items(row["codes"], limit=len(codes), low=1)
    if any(type(c) is not str or c not in codes for c in targeted) or len(set(targeted)) != len(targeted):
        raise Invalid("codes")
    text(row["covered"], limit=MAX_COVERED_CHARS, empty=True)
    text(row["adds"], limit=MAX_ADDS_CHARS, empty=True)
    text(row["rationale"], limit=MAX_RATIONALE)
    questions = items(row["questions"], limit=MAX_RESEARCH_QUESTIONS)
    for question in questions:
        text(question, limit=MAX_QUESTION)
    problem = evidence_problem(row["evidence"], targeted, shown)
    return {"text": row["text"], "placement": row["placement"], "codes": sorted(targeted),
            "evidence": list(row["evidence"]) if type(row["evidence"]) is list else [],
            "evidence_status": problem or "ok", "row_status": "ok", "covered": row["covered"], "adds": row["adds"],
            "rationale": row["rationale"], "questions": list(questions)}


def _invalid_row(row, reason):
    """v3 §4: the record of a rule row that failed its own validation: never tested; its text kept when it is text."""
    raw = row.get("text") if type(row) is dict else None
    return {"text": raw[:2 * MAX_RULE_CHARS] if type(raw) is str else None, "placement": None, "codes": [],
            "evidence": [], "evidence_status": "not_checked", "row_status": reason, "covered": "", "adds": "",
            "rationale": "", "questions": []}


def _check(benchmark, codes, shown=None):
    checkable = sum(similar_targets(benchmark), ())
    shown = {} if shown is None else shown

    def check(value):
        fields(value, ["rules"], ["transfer"])
        out = []
        for row in items(value["rules"], limit=MAX_RULES):
            try:
                out.append(_row(benchmark, codes, shown, checkable, row))
            except (ValueError, TypeError) as error:  # Invalid is a ValueError; a wrong type is the row's own fault
                out.append(_invalid_row(row, str(error)[:80] or type(error).__name__))
        if out and all(r["row_status"] != "ok" for r in out):
            raise Invalid("no valid rule")
        if sum(r["placement"] == "similar" for r in out) > MAX_SIMILAR_RULES:
            raise Invalid("similar rules")
        return {"rules": out, "transfer": _transfer(value, out, checkable)}
    return check


def propose(roles, benchmark, value, *, stage, codes, label):
    """{"status": "proposed" | "method_failure", "proposals": [{"id", "text", "placement", "codes", "evidence",
    "evidence_status", "row_status", "covered", "adds", "rationale", "questions"}], "transfer"}: at most two calls
    (§4); v3: a row whose own fields are invalid has ``row_status`` its reason (else "ok"). ``codes``:
    every code the analyst may target (``other`` included); the evidence is checked against ``value``'s shown
    failures (v2 §4)."""
    for attempt in range(1, ANALYST_ATTEMPTS + 1):
        reply = roles.ask("analyst", ANALYST_SYSTEM, value, label="%s/attempt%d" % (label, attempt),
                          check=_check(benchmark, set(codes), shown_codes(value)))
        if reply is not None:
            return {"status": "proposed", "attempts": attempt, "transfer": reply["transfer"],
                    "proposals": [{"id": "s%d-r%d" % (stage, n), **rule}
                                  for n, rule in enumerate(reply["rules"], 1)]}
    return {"status": "method_failure", "attempts": ANALYST_ATTEMPTS, "proposals": [], "transfer": None}


def deduplicated(proposals, parent_texts):
    """(kept, dropped ids): a proposal whose normalized text equals a parent rule or a lower-numbered kept proposal is
    dropped (§4 step 5, and again after the research rewrite)."""
    seen, kept, dropped = {normalized(t) for t in parent_texts}, [], []
    for proposal in proposals:
        key = normalized(proposal["text"])
        if key in seen:
            dropped.append(proposal["id"])
            continue
        seen.add(key)
        kept.append(proposal)
    return kept, dropped
