"""Hypothesis-bound diagnostic checks on an already generated output (experiment object A of the design).

BigCodeBench: the frozen v6 probe kinds (expected / equal_relation / raises / structure) through the frozen prompt,
parser, review and container harness, plus this mode's declarative ``state`` kind (the argument object compared by
EXACT JSON-normalized snapshot before and after ONE call; admissible only where the contract quote states input
preservation or in-place modification unambiguously -- a regex cue heuristic, negation-aware, not a semantic
guarantee; an unchanged argument under an in-place obligation is never a confirmed violation because the input may
already be in its final state). Deterministic admissibility (duplicates, the state cue) runs before the
LIMITED-BLINDING review (contract, checks and rubric only; no output, host status, hypothesis verdict or check
rationale -- the implementation-conditioned choice of inputs and expectations remains visible). Text domains: the
frozen judge with the hypotheses as focus; a judged verdict is model judgment and is graded at most as a pending
explanation.

Grading (D2.5): ``confirmed_violation`` / ``confirmed_preserved`` need three separate justifications -- input
legality (review keep), a contract obligation (the quote) and an expected value whose basis is the contract or
documentation -- and an executed decided outcome; everything else is pending, unknown, not applicable or an
error. A failing assertion alone is disagreement with an expectation, not a justified diagnosis."""
from __future__ import annotations

import json
import re

from skillopt.continual_eval.core import require
from skillopt.continual_learning import verifier as vf
from skillopt.validator_pilot.api import digest

STATE_KIND = "state"
STATE_RELATIONS = ("unchanged", "changed")
PRESERVATION_CUES = re.compile(
    r"(not|never|without|n't)\s+(be\s+|being\s+)?(modif|mutat|alter|chang|touch)|unmodified|unchanged|unaltered|"
    r"intact|untouched|returns?\s+(a\s+)?(new|copy)|(a|the)\s+copy\s+of|original\s+(list|dict|dictionary|data|input|"
    r"array|object)\s+(is|are|remains|stays)\s+(not\s+(modif|mutat|alter|chang)|un(modif|alter|chang)|intact|"
    r"unchanged|preserved|untouched|the\s+same)|preserv(e|es|ed|ing)\s+(the\s+)?(input|original)|non-?destructive|"
    r"leaves?\s+(the\s+)?(input|original|given|provided)\s+\w+\s+(intact|unchanged|untouched|as\s+is)", re.I)
INPLACE_CUES = re.compile(
    r"in[-\s]?place|modif(y|ies|ied)\s+(the\s+)?(given|input|original|passed|provided)|mutat(e|es|ed|ing)\s+(the\s+)?"
    r"(given|input|original|passed|provided)|updat(e|es|ed|ing)\s+(the\s+)?(given|input|original|passed|provided)\s+"
    r"(list|dict|dictionary|mapping|array|object)|(sort|append|extend|insert|remove|pop|clear)s?\s+(the\s+)?(given|input|"
    r"original|passed|provided)\s+(list|dict|dictionary|array)\s+(in\s+place|directly)", re.I)
EXECUTED_KINDS = (*vf.PROBE_KINDS, STATE_KIND)
GRADES = ("confirmed_violation", "confirmed_preserved", "pending_explanation", "unknown", "not_applicable",
          "format_or_env_error")
NOT_APPLICABLE = "not_applicable:"
HYPOTHESIS_TAG = re.compile(r"^\s*\[(h\d+|u0)\]\s*")  # u0: the pseudo-hypothesis of an unassigned case
_FOLD = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "`": "'"})


def _fold(text):
    return " ".join(text.translate(_FOLD).lower().split()).strip(" .\u2026\"'")


def relocate_quote(quote, task_text):
    """A contract quote the model altered only in case, quote characters or edge punctuation (10/11 audit: 'quote is
    not a substring' was the most frequent probe rejection): the UNIQUE task line that contains it, verbatim and
    WHOLE, else None. The stored quote is then real task text -- admissibility is not relaxed; a paraphrase, a quote
    matching several lines, or a line longer than 600 characters (it is never cut to a prefix that could drop the
    matched clause or its qualifications) stays rejected."""
    if type(quote) is not str or type(task_text) is not str or vf.quote_in(quote, task_text):
        return None
    needle = _fold(quote)
    if len(needle) < 12:
        return None
    hits = [line.strip() for line in task_text.splitlines() if line.strip() and needle in _fold(line)]
    return hits[0] if len(hits) == 1 and len(hits[0]) <= 600 else None
FOCUS_NOTE = (
    "\n\nDIAGNOSTIC FOCUS. The probes serve the listed hypotheses (diagnostic_focus): each probe carries hypothesis_id "
    "(one of the listed ids) and should produce the observation that supports or excludes that hypothesis; prefer "
    "the observation that adds information over repeating a settled one. A fifth kind \"state\" is allowed: one "
    "call; expected is {\"argument\": <0-based positional index or kwarg name>, \"relation\": \"unchanged\"|"
    "\"changed\"}; the host snapshots that JSON argument (a list or dict) before and after the call and compares. "
    "Use \"unchanged\" ONLY when contract_quote states that the input is not modified / a new object is returned, "
    "and \"changed\" ONLY when it states in-place modification of that argument; when the task says nothing about "
    "it, do not propose a state probe. A focus entry with role \"probe\" is a hypothesis stated for OTHER outputs: "
    "probe on THIS output the obligation it names and let the execution decide -- assume neither outcome."
)
REVIEW_NOTE = (
    "\n\nA fifth kind \"state\" may appear (expected {argument, relation}): keep it only if contract_quote explicitly "
    "states input preservation (relation unchanged) or in-place modification (relation changed) of that argument and "
    "the call is legal. The rationale of every probe is withheld on purpose: judge the contract and the check alone."
)
JUDGE_FOCUS_NOTE = (
    "\n\nDIAGNOSTIC FOCUS. diagnostic_focus lists hypotheses about this response; prefix each check's obligation with "
    "the id of the hypothesis it serves, e.g. \"[h1] ...\". The obligation must still be stated or clearly implied "
    "by the task text; your verdict is a judgment, never a verification of factual correctness. A focus entry with "
    "role \"probe\" is a hypothesis stated for OTHER responses: judge on THIS response the obligation it names and "
    "report what you find -- met or not met -- assuming neither."
)


# ----------------------------------------------------------------------------- prompts
def check_messages(public, output, policy, focus):
    system, user = vf.probe_messages(public, output, policy, [])
    payload = json.loads(user)
    payload["diagnostic_focus"] = focus
    return system + FOCUS_NOTE, json.dumps(payload, ensure_ascii=False, sort_keys=True)


def blind_review_messages(public, probes, policy, *, revision=False):
    """Limited blinding: the reviewer sees contract, checks and rubric; rationale (artifact-conditioned commentary)
    and hypothesis ids are withheld; no output, host status or hypothesis verdict exists in the payload. A revised
    expectation (after Research) is reviewed again with the payload marked ``revision``."""
    stripped = [{**{k: v for k, v in p.items() if k != "hypothesis_id"}, "rationale": "(withheld for blind review)"}
                for p in probes]
    system, user = vf.review_messages(public, stripped, policy)
    if revision:
        payload = json.loads(user)
        payload["revision"] = ("these expectations were revised from documentation excerpts; keep a probe only if the "
                               "revised expectation follows from the task text together with the stated fact")
        user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return system + REVIEW_NOTE, user


def judge_focus_messages(benchmark, public, output, policy, focus):
    system, user = vf.judge_messages(benchmark, public, output, policy)
    payload = json.loads(user)
    payload["diagnostic_focus"] = focus
    return system + JUDGE_FOCUS_NOTE, json.dumps(payload, ensure_ascii=False, sort_keys=True)


# ----------------------------------------------------------------------------- parsing
ONLY_OBLIGATION = "requested_behavior"  # the single obligation a probe may check (frozen parser rule)
OVER_LIMIT = "over_limit"


def _parse_state_probe(row, task_text):
    require(type(row) is dict and set(row) == vf.PROBE_FIELDS, "Exact probe fields required")
    require(row["kind"] == STATE_KIND, "Not a state probe")
    require(row["obligation_id"] == "requested_behavior", "Probes may only check the requested behavior")
    quote = vf._text(row["contract_quote"], 600)
    require(vf.quote_in(quote, task_text), "contract_quote must be an exact substring of the public task")
    vf._text(row["rationale"], 1200)
    calls = row["calls"]
    require(type(calls) is list and len(calls) == 1, "A state probe has exactly one call")
    call = calls[0]
    require(type(call) is dict and set(call) == {"args", "kwargs"} and type(call["args"]) is list
            and type(call["kwargs"]) is dict and all(type(k) is str for k in call["kwargs"]),
            "Each call needs JSON args and kwargs")
    vf._bounded_json(call)
    expected = row["expected"]
    require(type(expected) is dict and set(expected) == {"argument", "relation"}
            and expected["relation"] in STATE_RELATIONS, "A state probe expects {argument, relation}")
    argument = expected["argument"]
    if type(argument) is int and type(argument) is not bool:
        require(0 <= argument < len(call["args"]), "argument index out of range")
        target = call["args"][argument]
    else:
        require(type(argument) is str and argument in call["kwargs"], "argument must be a positional index or a kwarg name")
        target = call["kwargs"][argument]
    require(type(target) in (list, dict), "A state probe observes a mutable JSON argument (list or dict)")
    # negation-aware admission: a quote that states BOTH (e.g. "does not modify the input list in place") or neither
    # does not determine the obligation; only an unambiguous statement admits the probe
    preserved = PRESERVATION_CUES.search(quote) is not None
    inplace = INPLACE_CUES.search(quote) is not None
    if expected["relation"] == "unchanged":
        require(preserved and not inplace,
                NOT_APPLICABLE + " the contract quote does not state input preservation unambiguously")
    else:
        require(inplace and not preserved,
                NOT_APPLICABLE + " the contract quote does not state in-place modification unambiguously")
    return {**row, "calls": vf._bounded_json(calls)}


def _normalize_probe(row, hypothesis_ids, task_text=None):
    """Harmless surface variants the real model produced (10/9 run): a ``select: null`` on a non-structure probe,
    a hypothesis id in another case, an envelope-only key such as ``index``; the probe's substance is untouched.
    10/11: with exactly ONE focus hypothesis a MISSING id is bound to it (a probe that names another hypothesis stays
    rejected: it serves a mechanism this case is not about), and a quote that differs from a unique task line only in
    case / quote characters / edge punctuation is replaced by that line verbatim. 10/11 (bsel1): a MISSING
    ``obligation_id`` is filled with the only admissible value (the field then carries no information; a probe that
    names another obligation stays rejected) -- one case lost both probes to this omission in the reply and again in
    its repair."""
    if type(row) is not dict:
        return row
    row = dict(row)
    if row.get("obligation_id") is None:
        row["obligation_id"] = ONLY_OBLIGATION
    ids = {h.lower(): h for h in hypothesis_ids}
    if type(row.get("hypothesis_id")) is str and row["hypothesis_id"].strip().lower() in ids:
        row["hypothesis_id"] = ids[row["hypothesis_id"].strip().lower()]
    elif len(ids) == 1 and row.get("hypothesis_id") in (None, ""):
        row["hypothesis_id"] = next(iter(ids.values()))
    located = relocate_quote(row.get("contract_quote"), task_text)
    if located is not None:
        row["contract_quote"] = located
    if row.get("kind") != "structure" and "select" in row and row["select"] is None:
        row.pop("select")
    for key in ("index", "id", "case_id", "check_id"):
        row.pop(key, None)
    return row


normalize_probe = _normalize_probe  # the record builder reads a rejected probe the way the parser did


def parse_check_probes(value, task_text, hypothesis_ids, max_checks):
    """The probe envelope with hypothesis binding; one malformed probe drops that probe only. Returns (probes,
    rejected reasons by index, plus ``over_limit`` when the reply held more probes than allowed)."""
    require(type(value) is dict and set(value) == {"probes"} and type(value["probes"]) is list,
            "Exact probes field required")
    probes, rejected = [], {}
    rows = value["probes"]
    if len(rows) > max_checks:
        # 10/11 (bsel1): a reply with three probes was rejected whole and its repair came back with one; the first
        # ``max_checks`` are considered in the order given (deterministic) and the surplus is on record
        rejected[OVER_LIMIT] = f"{len(rows)} probes returned; only the first {max_checks} are considered"
        rows = rows[:max_checks]
    for index, raw in enumerate(rows):
        row = _normalize_probe(raw, hypothesis_ids, task_text)
        try:
            require(type(row) is dict and row.get("hypothesis_id") in hypothesis_ids,
                    "hypothesis_id must name one of the focus hypotheses")
            body = {k: v for k, v in row.items() if k != "hypothesis_id"}
            parsed = (_parse_state_probe(body, task_text) if body.get("kind") == STATE_KIND
                      else vf._parse_probe(body, task_text))
            probes.append({**parsed, "hypothesis_id": row["hypothesis_id"]})
        except (ValueError, TypeError, KeyError) as exc:
            rejected[str(index)] = str(exc)[:200]
    return probes, rejected


def repair_messages(system, user, rejected, reply):
    """ONE repair of a probe reply whose probes were rejected by strict validation: the same material plus the
    rejected reply and the exact field-level errors (the model is told what was wrong, never what to expect)."""
    payload = json.loads(user)
    payload["repair"] = {"previous_reply": reply, "rejected": rejected,
                         "instruction": "Your previous probes were rejected by strict validation for the stated reasons "
                                        "(exact fields: kind, calls, expected, obligation_id, contract_quote, rationale, "
                                        "hypothesis_id -- and select only for structure; contract_quote must be an exact "
                                        "substring of the task text; hypothesis_id one of diagnostic_focus). Return ONLY "
                                        "the corrected JSON object, or {\"probes\": []} if nothing qualifies."}
    return system, json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_judged_checks(value, task_text, hypothesis_ids):
    checks, rejected = vf.parse_checks(value, task_text)
    for check in checks:
        match = HYPOTHESIS_TAG.match(check["obligation"])
        if match:
            # an explicit tag names its hypothesis; a tag outside this case's focus stays unbound (never re-assigned)
            check["hypothesis_id"] = match.group(1) if match.group(1) in hypothesis_ids else None
        else:
            check["hypothesis_id"] = next(iter(hypothesis_ids)) if len(hypothesis_ids) == 1 else None
    return checks, rejected


def deterministic_admissibility(probes):
    """Code-level checks before any model review: duplicates (same kind, calls and expectation) are dropped."""
    kept, rejected, seen = [], {}, set()
    for index, probe in enumerate(probes):
        key = digest({k: probe.get(k) for k in ("kind", "calls", "expected", "select")})
        if key in seen:
            rejected[str(index)] = "duplicate check (same kind, calls and expectation)"
            continue
        seen.add(key)
        kept.append(probe)
    return kept, rejected


# ----------------------------------------------------------------------------- the state harness
def state_test_source(entry_point, probes):
    """A unittest module in the official harness format for state probes only: the argument snapshot before and
    after one call. Failure messages carry the harness nonce exactly like the frozen probe harness, so
    ``verifier.probe_outcomes`` reads them unchanged."""
    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entry_point), "Invalid entry point")
    mark = vf.probe_mark(probes)
    body = []
    for index, probe in enumerate(probes):
        require(probe["kind"] == STATE_KIND, "The state harness takes state probes only")
        call, expected = probe["calls"][0], probe["expected"]
        argument = expected["argument"]
        selector = f"_vf_args[{argument}]" if type(argument) is int else f"_vf_kwargs[{json.dumps(argument)}]"
        label = json.dumps(str(argument))
        lines = [f"    def test_probe_{index}(self):",
                 f"        _vf_args = _vf_json.loads({vf._literal(call['args'])})",
                 f"        _vf_kwargs = _vf_json.loads({vf._literal(call['kwargs'])})",
                 f"        _vf_before = _vf_norm({selector})",
                 f"        _vf_raw = {entry_point}(*_vf_args, **_vf_kwargs)",
                 f"        _vf_after = _vf_norm({selector})"]
        # snapshots compare EXACTLY (JSON-normalized values; no float tolerance): any mutation is a change
        if expected["relation"] == "unchanged":
            lines += ["        if _vf_before != _vf_after:",
                      f"            self.fail('{mark} argument ' + {label} + ' was modified: before ' + "
                      "_vf_json.dumps(_vf_before)[:300] + ' after ' + _vf_json.dumps(_vf_after)[:300])"]
        else:
            lines += ["        if _vf_before == _vf_after:",
                      f"            self.fail('{mark} argument ' + {label} + ' was not modified in place: ' + "
                      "_vf_json.dumps(_vf_after)[:300])"]
        body.extend(lines)
    if not body:
        body.append("    def test_probe_none(self):\n        pass")
    return vf._HARNESS.replace("@VF_NONCE@", vf.harness_nonce(probes)) + "\n".join(body) + "\n"


def state_probe_executor(runtime):
    """Execute kept state probes on one generated program in the pinned container (official harness format)."""
    from skillopt.continual_eval import backends

    def execute(public, output, probes):
        timeout, memory, _ = backends._runtime_limits(runtime)
        test = state_test_source(public["entry_point"], probes)
        result = backends._native({"operation": "bigcodebench", "code": output, "test": test,
                                   "entry_point": public["entry_point"], "memory_mb": memory,
                                   "test_timeout": min(60, max(5, timeout - 15))}, runtime)
        return {"test_sha256": digest(test), **result}
    return execute


# ----------------------------------------------------------------------------- grading
def describe(probe):
    """A bounded, label-free description of what a check asserts (for reports)."""
    kind = probe["kind"]
    calls = "; ".join("args=" + json.dumps(c["args"], ensure_ascii=False)[:120]
                      + (" kwargs=" + json.dumps(c["kwargs"], ensure_ascii=False)[:100] if c["kwargs"] else "")
                      for c in probe.get("calls", []))
    if kind == "expected":
        what = "returns " + json.dumps(probe["expected"], ensure_ascii=False)[:160]
    elif kind == "raises":
        what = "raises " + str(probe["expected"])
    elif kind == "equal_relation":
        what = "both calls return equal results"
    elif kind == "structure":
        what = "returned structure " + json.dumps(probe["expected"], ensure_ascii=False)[:160]
    elif kind == STATE_KIND:
        what = f"argument {probe['expected']['argument']!s} is {probe['expected']['relation']} by the call"
    else:
        what = kind
    return f"{kind}: call {calls}; {what}" if calls else f"{kind}: {what}"


def grade(*, executed, outcome, review, basis, judged=False, probe=None):
    """The D2.5 grade of one check record."""
    if judged:
        return "unknown" if outcome == "unknown" else "pending_explanation"
    if not executed:
        if review is None:
            return "pending_explanation"
        if review.get("fact_question") and review.get("keep"):
            return "unknown"  # an unresolved fact: never executed, never a verdict
        return "pending_explanation"
    if outcome == "error":
        return "format_or_env_error"
    if outcome == "unknown":
        return "unknown"
    justified = bool(review and review.get("keep")) and basis in {"contract", "documentation"}
    if outcome == "fail":
        if probe is not None and probe.get("kind") == STATE_KIND and probe["expected"]["relation"] == "changed":
            # an unchanged argument under an in-place obligation is ambiguous: the input may already be in its
            # final state (an already-sorted list); never a confirmed violation
            return "pending_explanation"
        return "confirmed_violation" if justified else "pending_explanation"
    if outcome == "pass":
        return "confirmed_preserved" if justified else "pending_explanation"
    return "unknown"
