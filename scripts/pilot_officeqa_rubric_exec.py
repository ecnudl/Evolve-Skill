#!/usr/bin/env python3
"""Exploratory pilot (2026-10-14): an EXECUTABLE rubric at solve time on OfficeQA -- NOT a method result, NOT Skill
evolution, and a change of the solve form (docs/handoff/rubric-exploration-20261014.md, section 4).

Question: when the solver is asked to show its inputs and its computation in a machine-readable form, and the host
re-checks the inputs against the pages and recomputes the answer exactly, how much of the remaining error of the
zero-shot instruction (mostly near-miss arithmetic) is recovered -- and how much does the contract alone change?

    prepare --study F --repo R --upstream U --id-split S --revision SHA
            --arm name=none|f:<file>[:struct] ... --output DIR          (zero calls)
    run     --output DIR
    report  --output DIR [--contrast a-b ...]

An arm ``name=<skill>:struct`` solves with the STRUCTURED contract: before the answer tag the reply must carry
<figures> (a JSON list of {name, value as printed, verbatim quote}), <expression> (over the figure names, in a
closed grammar with abs/min/max/sqrt/ln/exp/pow/sum/mean/gmean/pstdev/sstdev) and <decimals>. Such an arm yields a
second, DERIVED arm ``name_exec`` without any further call: the host checks every figure is the whole content of a
table cell of the supplied pages at the quote (the OfficeQA generator's whitelist), parses the expression against
the closed grammar (an AST walk; nothing is executed), evaluates it with interval arithmetic over the rationals
(exact for + - * / and integer powers; sqrt/ln/exp/pow at 80 digits on both bounds, widened), certifies the text at
the asked decimals only when both bounds round to it, and scores THAT value when every check passed and the model's
own answer is one number of another value, else the model's own answer. An arm
without ``:struct`` solves with the plain contract of the headroom pilot (the control). Scoring: the frozen OfficeQA
normalized exact match on the last answer tag, as in the headroom pilot.

Data discipline, calls, margins, intents, costs and "nothing is resumed": exactly the headroom pilot's (imported).
Only the paper's train and validation items are rendered, written and solved; the question file is read as a whole
(the headroom pilot's reader) and its 172 test rows are neither written out nor supplied to the solver.
"""
from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import json
import re
import sys
from decimal import Decimal, DecimalException, localcontext
from fractions import Fraction
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_officeqa_tasks as gen  # noqa: E402
from scripts import pilot_livemath_headroom as base  # noqa: E402
from scripts import pilot_officeqa_headroom as oq  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json  # noqa: E402

VERSION = "officeqa-rubric-exec-pilot-v1"
KIND = "officeqa-rubric-exec-pilot-solver"
STRUCT_CONTRACT = (
    "\nBefore the final answer, show the inputs and the computation in this exact machine-readable form:\n"
    "<figures>[{\"name\": \"a\", \"value\": \"<the number exactly as printed in the pages, e.g. 4,908 or -18 or "
    "4.73>\", \"quote\": \"<a verbatim excerpt of the pages containing it, e.g. the table row>\"}, ...]</figures>\n"
    "<expression>an arithmetic expression over the figure names, using only + - * / parentheses, plain numbers and "
    "the functions abs(x), min(...), max(...), sqrt(x), ln(x), exp(x), pow(x, y), sum(...), mean(...), gmean(...), "
    "pstdev(...), sstdev(...)</expression>\n"
    "<decimals>the number of decimal places the question asks the answer to be rounded to, or the word printed "
    "when the answer is a value as printed</decimals>\n"
    "List every printed figure the answer depends on (a figure name may appear in the expression any number of "
    "times). When the answer is not a number computed from printed figures (a date, a name, a chart reading), write "
    "<figures>none</figures> and omit the other two tags.\n"
    "Then return the concise final answer inside <answer>...</answer>.")
FUNCTIONS = {"abs", "min", "max", "sqrt", "ln", "exp", "pow", "sum", "mean", "gmean", "pstdev", "sstdev"}
MAX_FIGURES, MAX_EXPRESSION, MAX_DECIMALS, MAX_DEPTH, PRECISION, MAX_ANSWER = 120, 4000, 10, 24, 80, 64
_EXPRESSION = re.compile(r"[A-Za-z0-9_+\-*/^(), .]*")  # one line, ASCII; no other character at all
IMPLEMENTATION = (*oq.IMPLEMENTATION, "scripts/pilot_officeqa_headroom.py", "scripts/generate_officeqa_tasks.py")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arm_spec(spec):
    """(name, skill text, provenance, structured?) of ``name=none|f:<file>`` with an optional ``:struct`` suffix."""
    structured = spec.endswith(":struct")
    name, text, provenance = base.skill_spec(spec[:-len(":struct")] if structured else spec)
    return name, text, {**provenance, "contract": "structured" if structured else "plain"}, structured


def system_prompt(skill, structured):
    system = "Solve the supplied task using only the supplied public information."
    if skill.strip():
        system += "\n\nFrozen skill guidance (use only where applicable):\n" + skill
    return system + (STRUCT_CONTRACT if structured else oq.CONTRACT)


def _tag(text, name):
    found = re.findall(r"<%s>(.*?)</%s>" % (name, name), text, re.DOTALL | re.IGNORECASE)
    return found[-1].strip() if found else None


LIMIT, TINY = Fraction(10) ** 20, Fraction(1, 10 ** 20)  # every value: zero, or 1e-20 <= |x| <= 1e20
MAX_BITS = 4096  # of numerator plus denominator of every bound (about 1,200 decimal digits)
EPSILON = Fraction(1, 10 ** 75)  # relative half-width added around every 80-digit function result (and 1e-75 absolute)
# Why 1e-75 suffices (reviewed 2026-10-14): a Fraction is converted to an 80-digit decimal with relative error at
# most 5e-80 (only the division rounds); sqrt/ln/exp are correctly rounded at 80 digits and C pow is bounded below
# 0.6 ulp (libmpdec). sqrt halves a relative error (< 1e-79 relative); ln turns a relative error into an absolute
# one (< 2.4e-78 absolute); exp turns an absolute error into a relative one (< 2.4e-78 relative for arguments up to
# 46, far smaller for negative arguments); pow(b, e) = exp(e ln b) with |e| <= 64 and |e ln b| <= 46 amplifies
# both operands' conversion errors by about (64 + 46) * 5e-80 (< 5.7e-78 relative). All inside 1e-75 * (1 + |x|).


def _bits(value):
    return value.numerator.bit_length() + value.denominator.bit_length()


def _check(interval):
    """Every value is an INTERVAL (lo, hi) of Fractions that certainly contains the mathematical value. Exact
    operations (+ - * / integer powers, abs, min, max, sums, means) propagate the bounds exactly; sqrt/ln/exp/pow
    are computed at 80 digits on both bounds and widened by EPSILON. Both bounds are of ordinary magnitude and
    bounded size, so no chain of operations can grow them without limit -- and an error that a later operation
    amplifies shows up as a WIDER interval, never as a wrong certified value."""
    lo, hi = interval
    require(lo <= hi, "Bounds out of order")
    for value in (lo, hi):
        require(value == 0 or TINY <= abs(value) <= LIMIT, "Value outside the admitted magnitude")
        require(_bits(value) <= MAX_BITS, "Value too large to represent")
    return interval


def _exact(value):
    return (value, value)


def _widen(value):
    """An 80-digit decimal result as a Fraction interval that contains the true value."""
    require(value.is_finite(), "Not a finite value")
    x = Fraction(value)
    delta = abs(x) * EPSILON + EPSILON
    return (x - delta, x + delta)


def _decimal(x):
    return Decimal(x.numerator) / Decimal(x.denominator)


def _monotone(name, interval, exponent=None):
    """sqrt / ln / exp (monotone increasing) and pow with a positive base, on an interval: computed on the bounds
    (for pow on the four corners) with 80-digit decimals, widened by EPSILON; the domain is checked first."""
    lo, hi = interval
    with localcontext() as context:
        context.prec = PRECISION
        if name == "sqrt":
            require(lo >= 0, "Square root of a negative")
            lows, highs = _widen(_decimal(lo).sqrt()), _widen(_decimal(hi).sqrt())
        elif name == "ln":
            require(lo > 0, "Logarithm of a non-positive")
            lows, highs = _widen(_decimal(lo).ln()), _widen(_decimal(hi).ln())
        elif name == "exp":
            require(hi <= 46, "Exponent too large")  # exp(46) ~ 1e20
            lows, highs = _widen(_decimal(lo).exp()), _widen(_decimal(hi).exp())
        else:
            elo, ehi = exponent
            require(lo > 0, "Power of a non-positive base")
            # |exponent| <= 64 as for integer powers: the 1e-80 conversion error of the base is amplified by at
            # most 64 in exp(e * ln b), which the 1e-75 widening covers
            require(-64 <= elo and ehi <= 64, "Exponent too large")
            corners = []
            for b in (lo, hi):
                for e in (elo, ehi):
                    d, x = _decimal(b), _decimal(e)
                    require(abs(x * d.ln()) <= 46, "Power too large")
                    corners.append(_widen(d ** x))
            return _check((min(c[0] for c in corners), max(c[1] for c in corners)))
    return _check((lows[0], highs[1]))


def _add(a, b):
    return _check((a[0] + b[0], a[1] + b[1]))


def _sub(a, b):
    return _check((a[0] - b[1], a[1] - b[0]))


def _mul(a, b):
    products = [a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1]]
    return _check((min(products), max(products)))


def _div(a, b):
    require(b[0] > 0 or b[1] < 0, "Division by an interval containing zero")
    return _mul(a, (1 / b[1], 1 / b[0]))


def _ipow(a, n):
    """An integer power of an interval, |n| <= 64, size-checked before anything is computed."""
    require(max(_bits(a[0]), _bits(a[1])) * abs(n) <= MAX_BITS, "Power too large to represent")
    if n < 0:
        return _ipow(_div(_exact(Fraction(1)), a), -n)
    if n == 0:
        require(a[0] > 0 or a[1] < 0, "Zero to the power zero")
        return _exact(Fraction(1))
    lo, hi = a[0] ** n, a[1] ** n
    if n % 2 == 0 and a[0] < 0 < a[1]:
        return _check((Fraction(0), max(lo, hi)))
    return _check((min(lo, hi), max(lo, hi)))


def evaluate(expression, values):
    """The interval (lo, hi) that certainly contains the value of an expression over the named figures inside the
    closed grammar, or (None, reason). The text is parsed and walked only; no model text is ever executed.
    ``values`` maps names to Fractions."""
    if len(expression) > MAX_EXPRESSION or _EXPRESSION.fullmatch(expression) is None:
        return None, "expression_too_long_or_outside_character_set"
    text = expression.replace("^", "**")  # the only rewriting; offsets below refer to this text
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None, "expression_not_parsable"
    used = set()

    def series(args, depth):
        require(args, "Empty series")
        return [walk(a, depth + 1) for a in args]

    def total(xs):
        acc = _exact(Fraction(0))
        for x in xs:
            acc = _add(acc, x)
        return acc

    def walk(node, depth):
        require(depth <= MAX_DEPTH, "Expression too deep")
        return _check(_walk(node, depth))

    def _walk(node, depth):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            spelling = text[node.col_offset:node.end_col_offset]
            require(re.fullmatch(r"\d{1,20}(?:\.\d{1,20})?", spelling) is not None, "Constant outside the grammar")
            return _exact(Fraction(spelling))
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise KeyError(node.id)  # a name that is not one of the listed figures
            used.add(node.id)
            return _exact(values[node.id])
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.USub, ast.UAdd):
            value = walk(node.operand, depth + 1)
            return (-value[1], -value[0]) if type(node.op) is ast.USub else value
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow):
            left, right = walk(node.left, depth + 1), walk(node.right, depth + 1)
            if type(node.op) is ast.Pow:
                return _power(left, right)
            return {ast.Add: _add, ast.Sub: _sub, ast.Mult: _mul, ast.Div: _div}[type(node.op)](left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            name, args = node.func.id, node.args
            if name in ("abs", "sqrt", "ln", "exp"):
                require(len(args) == 1, "One argument")
                x = walk(args[0], depth + 1)
                if name == "abs":
                    return (Fraction(0), max(-x[0], x[1])) if x[0] < 0 < x[1] else (min(abs(x[0]), abs(x[1])), max(abs(x[0]), abs(x[1])))
                return _monotone(name, x)
            if name == "pow":
                require(len(args) == 2, "Two arguments")
                return _power(walk(args[0], depth + 1), walk(args[1], depth + 1))
            xs = series(args, depth)
            n = _exact(Fraction(len(xs)))
            if name == "min":
                return (min(x[0] for x in xs), min(x[1] for x in xs))
            if name == "max":
                return (max(x[0] for x in xs), max(x[1] for x in xs))
            if name == "sum":
                return total(xs)
            if name == "mean":
                return _div(total(xs), n)
            if name == "gmean":
                return _monotone("exp", _div(total(_monotone("ln", x) for x in xs), n))
            m = _div(total(xs), n)
            ss = total(_ipow(_sub(x, m), 2) for x in xs)
            if name == "pstdev":
                return _monotone("sqrt", _div(ss, n))
            require(len(xs) > 1, "Sample deviation needs two values")
            return _monotone("sqrt", _div(ss, _exact(Fraction(len(xs) - 1))))
        raise ValueError("Outside the expression grammar")

    def _power(base, exponent):
        if exponent[0] == exponent[1] and exponent[0].denominator == 1 and abs(exponent[0]) <= 64:
            return _ipow(base, int(exponent[0]))
        return _monotone("pow", base, exponent)

    try:
        value = walk(tree.body, 0)
    except KeyError:
        return None, "figure_unused_or_unknown_name"
    except (ValueError, ZeroDivisionError, OverflowError, RecursionError, DecimalException, TypeError) as exc:
        return None, "expression_" + type(exc).__name__.lower()
    if used != set(values):
        return None, "figure_unused_or_unknown_name"
    return value, None


def _render(value, decimals):
    """(text, tie?) of ONE exact Fraction: ``decimals`` places rounded half away from zero (trailing zeros kept,
    as a reference rounded to that many places is written), an exact half reported as a tie; for ``printed`` the
    exact digits of a terminating decimal, rendered with integer arithmetic only."""
    if decimals == "printed":
        denominator, places = value.denominator, 0
        for prime in (2, 5):
            while denominator % prime == 0:
                denominator //= prime
                places += 1
        require(denominator == 1, "Not a terminating decimal")
        scaled = abs(value) * 10 ** places
        require(scaled.denominator == 1, "Not a terminating decimal")
        digits = str(scaled.numerator).rjust(places + 1, "0")
        text = (digits[:-places] + "." + digits[-places:]).rstrip("0").rstrip(".") if places else digits
        return ("-" + text if value < 0 and text != "0" else text), False
    scaled = abs(value) * 10 ** decimals
    whole = scaled.numerator // scaled.denominator
    rest = scaled - whole
    tie = rest == Fraction(1, 2)
    whole += rest >= Fraction(1, 2)
    digits = str(whole).rjust(decimals + 1, "0")
    text = digits[:-decimals] + "." + digits[-decimals:] if decimals else digits
    return ("-" + text if value < 0 and whole else text), tie


def formatted(interval, decimals):
    """(text, certain?) of an interval: the text is certified only when both bounds render to the same text and no
    rounding boundary (a half at the asked places) lies inside the interval; otherwise the value cannot be told
    apart from its neighbours at this precision and nothing is certified. ``printed`` needs an exact value."""
    lo, hi = interval
    if decimals == "printed":
        require(lo == hi, "Not an exact value")
        return _render(lo, decimals)[0], True
    (text_lo, tie_lo), (text_hi, tie_hi) = _render(lo, decimals), _render(hi, decimals)
    if text_lo != text_hi or tie_lo or tie_hi:
        return text_lo, False
    # the same text from both bounds, and -- rounding being monotone -- no half strictly between them: certified
    return text_lo, True


def rubric(reply, context):
    """The executable rubric on one structured reply: {verdict, reason, figures, recomputed}. ``verified`` only
    when every figure is the whole content of a table cell of the pages at its quote, the expression is inside the
    grammar and uses every figure, and the decimals field is well-formed."""
    figures_text = _tag(reply, "figures")
    if figures_text is None:
        return {"verdict": "no_structure", "reason": "no_figures_tag", "figures": 0, "recomputed": None}
    if figures_text.strip().lower() == "none":
        return {"verdict": "not_applicable", "reason": "model_declared_no_figures", "figures": 0, "recomputed": None}
    try:
        figures = json.loads(figures_text)
    except ValueError:
        return {"verdict": "malformed", "reason": "figures_not_json", "figures": 0, "recomputed": None}
    if (type(figures) is not list or not 1 <= len(figures) <= MAX_FIGURES
            or any(type(f) is not dict or any(type(f.get(k)) is not str for k in ("name", "value", "quote")) for f in figures)):
        return {"verdict": "malformed", "reason": "figures_shape", "figures": 0, "recomputed": None}
    if len({f["name"] for f in figures}) != len(figures) or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,15}", f["name"]) for f in figures):
        return {"verdict": "malformed", "reason": "figure_names", "figures": len(figures), "recomputed": None}
    pages, starts = gen.lines(context)
    values = {}
    for f in figures:
        value = gen.figure(f["value"].strip()) if len(f["value"]) <= gen.MAX_VALUE else None
        if value is None:
            return {"verdict": "failed", "reason": "figure_not_a_printed_number:" + f["name"], "figures": len(figures), "recomputed": None}
        quote = gen.base._squash(f["quote"])
        if not 1 <= len(quote) <= 2000 or not gen.printed(f["value"].strip(), quote, pages, starts):
            return {"verdict": "failed", "reason": "figure_not_a_whole_table_cell_at_quote:" + f["name"], "figures": len(figures), "recomputed": None}
        try:
            values[f["name"]] = _check((value, value))[0]
        except ValueError:
            return {"verdict": "failed", "reason": "figure_outside_magnitude:" + f["name"], "figures": len(figures), "recomputed": None}
    expression, decimals_text = _tag(reply, "expression"), _tag(reply, "decimals")
    if expression is None or decimals_text is None:
        return {"verdict": "malformed", "reason": "expression_or_decimals_tag_missing", "figures": len(figures), "recomputed": None}
    if decimals_text.strip().lower() == "printed":
        decimals = "printed"
    elif re.fullmatch(r"\d{1,2}", decimals_text.strip()) and int(decimals_text) <= MAX_DECIMALS:
        decimals = int(decimals_text)
    else:
        return {"verdict": "malformed", "reason": "decimals_field", "figures": len(figures), "recomputed": None}
    value, reason = evaluate(expression, values)
    if value is None:
        return {"verdict": "failed", "reason": reason, "figures": len(figures), "recomputed": None}
    try:
        recomputed, certain = formatted(value, decimals)
    except (ValueError, DecimalException):
        return {"verdict": "failed", "reason": "value_not_representable", "figures": len(figures), "recomputed": None}
    if not certain:
        return {"verdict": "failed", "reason": "rounding_not_certified", "figures": len(figures), "recomputed": None}
    if len(recomputed) > MAX_ANSWER:
        return {"verdict": "failed", "reason": "recomputed_text_too_long", "figures": len(figures), "recomputed": None}
    return {"verdict": "verified", "reason": None, "figures": len(figures), "expression": expression[:400],
            "decimals": decimals, "recomputed": recomputed}


def scored_answer(found, verdict):
    """What the derived arm scores: the model's own answer unless the rubric verified a value and the model's
    answer is ONE number whose value differs from it -- then the recomputed text, keeping the model's own percent
    sign (its reading of the question's unit). A correct number in another spelling ("69%", "$2,760.44") is never
    replaced; an answer that is not one number (a date, a list) is never replaced."""
    if verdict["verdict"] != "verified" or found is None:
        return found, "model_answer"
    # ONE number, read on the raw text: an optional minus and currency sign, digits with or without thousands
    # separators, a decimal part, an optional percent sign, the unit words the scorer removes -- nothing else
    # (a list, a date, a fraction or a formula is not a number, whatever its normalization looks like)
    raw = re.sub(r"\b(million|millions|billion|billions|dollars|dollar|nominal)\b", "", found.strip().lower())
    match = re.fullmatch(r"\s*(-?)\s*\$?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(%?)\s*", raw)
    if match is None:
        return found, "model_answer_not_one_number"
    if Fraction(match.group(1) + match.group(2).replace(",", "")) == Fraction(verdict["recomputed"]):
        return found, "model_answer_same_value"
    return verdict["recomputed"] + match.group(3), "recomputed"


def prepare(study, repo, upstream, id_split, output, arms, *, revision):
    root, protocol, service = base._model(study)
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    require(len(revision) == 40, "Give the 40-character source revision")
    items, dropped, pages = oq.draw(upstream, id_split)
    require(len(dropped) * 10 <= len(items) + len(dropped), "More than a tenth of the items have no parsed page")
    named = [arm_spec(s) for s in arms]
    names = [n for n, _, _, _ in named] + [n + "_exec" for n, _, _, s in named if s]
    require(len(named) >= 2 and len(set(names)) == len(names) and any(s for _, _, _, s in named),
            "Give at least two distinct arms, at least one structured")
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "items.json", seal({"items": items}))
    write_json(out / "skills.json", seal({"skills": [{"name": n, "skill": t, "structured": s} for n, t, _, s in named]}))
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "repo": str(safe_path(repo)), "benchmark": "officeqa", "variant": "one_call_oracle_parsed_pages",
                   "source": {"revision": revision,
                              "files": {"officeqa_full.csv": _sha(safe_path(upstream) / "officeqa_full.csv")},
                              "parsed_pages_sha256": hashlib.sha256(json.dumps(sorted(pages.items())).encode()).hexdigest(),
                              "parsed_page_files": len(pages),
                              "id_split_manifest_sha256": _sha(safe_path(id_split) / "split_manifest.json")},
                   "implementation_sha256": {name: _sha(PROJECT_ROOT / name) for name in IMPLEMENTATION},
                   "parts": list(oq.PARTS), "items": len(items), "dropped_without_parsed_page": dropped,
                   "items_hash": read_json(out / "items.json", sealed=True)["record_hash"],
                   "skills_hash": read_json(out / "skills.json", sealed=True)["record_hash"],
                   # solved arms call the model; a derived arm re-scores a structured arm's replies (no call)
                   "solved_arms": [{"name": n, "skill_bytes": len(t.encode()), "skill_sha256": hashlib.sha256(t.encode()).hexdigest(), **p}
                                   for n, t, p, _ in named],
                   "arms": [{"name": n, "skill_bytes": len(t.encode()), "derived_from": None} for n, t, _, _ in named]
                           + [{"name": n + "_exec", "skill_bytes": len(t.encode()), "derived_from": n} for n, t, _, s in named if s],
                   "plain_contract": oq.CONTRACT, "structured_contract": STRUCT_CONTRACT,
                   "rubric": "figures are whole table cells of the pages at their quotes (generate_officeqa_tasks.printed); "
                             "expression inside the closed grammar {+ - * / ** parentheses, decimal constants, %s}, "
                             "walked on the AST only; interval arithmetic over the rationals (+ - * / integer powers "
                             "exact; sqrt/ln/exp/pow at %d digits on both bounds, widened by 1e-75); every bound in "
                             "[1e-20, 1e20] or zero and of bounded size; the text at the asked decimals is certified "
                             "only when both bounds round to it and no half lies in between (else no substitution); "
                             "the recomputed value is scored only when every check passed and the model's own answer "
                             "is one number of another value" % (", ".join(sorted(FUNCTIONS)), PRECISION),
                   **service, "data_scope": "the paper's train and validation items only are rendered, written and "
                                           "solved; the question file is read as a whole and its test rows are "
                                           "neither written out nor supplied to the solver",
                   "tool_sha256": _sha(Path(__file__))})
    write_json(out / "pilot.json", record)
    return record


def _row(record, arm, item, status, found, reason, receipts, raised, extra):
    """``found`` is the MODEL's answer tag (also for a derived row: whether a tag was there is the model's doing)."""
    return seal({"pilot_hash": record["record_hash"], "arm": arm, "item": item["id"], "status": status,
                 "invalid_format": extra.get("delivered", False) and found is None, "reason": reason,
                 "request_hashes": [r.get("request_hash") for r in receipts],
                 "finish_reasons": [r.get("finish_reason") for r in receipts], **base._usage(receipts, raised), **extra})


def _write(out, kind, arm, item, row):
    target = out / kind / arm / base._position(item["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, row)


def solve_one(api, record, out, arm, skill, structured, item):
    """One position of a solved arm: sealed intent, the call(s), sealed outcome; for a structured arm also the
    derived arm's intent and outcome (the rubric on the same reply, no call, zero cost)."""
    from skillopt.envs.officeqa.evaluator import exact_match

    key = "%s:%s:%s" % (record["record_hash"][:16], arm, item["id"])
    _write(out, "intents", arm, item, seal({"pilot_hash": record["record_hash"], "arm": arm, "item": item["id"], "key": key}))
    if structured:
        _write(out, "intents", arm + "_exec", item, seal({"pilot_hash": record["record_hash"], "arm": arm + "_exec",
                                                           "item": item["id"], "key": key, "derived": True}))
    text, reason, receipts, raised = base.reply(api, record, key, system_prompt(skill, structured),
                                                json.dumps(item["public"], ensure_ascii=False), kind=KIND)
    status, found = "unknown", None
    if text is not None:
        found = oq.answer(text)
        status = "pass" if found is not None and exact_match(found, item["private"]["answer"]) == 1.0 else "fail"
    row = _row(record, arm, item, status, found, reason, receipts, raised, {"delivered": text is not None})
    _write(out, "calls", arm, item, row)
    if structured:
        verdict = rubric(text, item["public"]["context"]) if text is not None else {"verdict": "unknown", "reason": reason,
                                                                                     "figures": 0, "recomputed": None}
        scored, source = scored_answer(found, verdict) if text is not None else (None, "undelivered")
        exec_status = "unknown" if text is None else (
            "pass" if scored is not None and exact_match(scored, item["private"]["answer"]) == 1.0 else "fail")
        derived = _row(record, arm + "_exec", item, exec_status, found, reason, [], 0,
                       {"delivered": text is not None, "derived_from": arm, "rubric": verdict,
                        "model_answer": found, "scored_answer": scored, "scored_source": source,
                        "model_status": status})
        # a derived row carries no cost of its own (the receipts are the solved arm's)
        _write(out, "calls", arm + "_exec", item, derived)
    return row


def run(output, *, fixture_api=None, probe=None):
    out = safe_path(output)
    record = read_json(out / "pilot.json", sealed=True)
    require(record["version"] == VERSION and record["tool_sha256"] == _sha(Path(__file__))
            and all(_sha(PROJECT_ROOT / name) == value for name, value in record["implementation_sha256"].items()),
            "Tool changed")
    items = read_json(out / "items.json", sealed=True)
    skills = read_json(out / "skills.json", sealed=True)
    require(items["record_hash"] == record["items_hash"] and skills["record_hash"] == record["skills_hash"],
            "Pilot inputs changed")
    fixture = record["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None), "Fixture client only for a fixture study")
    texts = {s["name"]: (s["skill"], s["structured"]) for s in skills["skills"]}
    arms = [a["name"] for a in record["solved_arms"]]
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        with output_lock(out / "calls"):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            reason = None
            if (out / "started.json").exists():
                reason = "interrupted_run_no_automatic_resume"
            else:
                try:
                    if not fixture:
                        tool._sequence().check_client_service(
                            record["repo"], record["model"], out / "client-check",
                            record["learning_model_service"], client_options=record["client_options"])
                    write_json(out / "started.json", seal({"pilot_hash": record["record_hash"]}))
                    api = fixture_api if fixture else base._client(record, out, 1)
                    try:
                        if not fixture:
                            write_json(out / "model_service.json", seal(api.service))
                            if probe is None:
                                from scripts.run_active_evidence_panel_eval import bounded, network_gate, tunnel_probe

                                proxy, host = record["model"].get("proxy"), api.service["host"]
                                probe = network_gate(lambda: bounded(lambda: tunnel_probe(proxy, host), 20.0))
                        rows = items["items"]
                        queue = []
                        for start in range(0, len(rows), base.CHUNK):
                            shift = (start // base.CHUNK) % len(arms)
                            queue += [(arm, item) for arm in arms[shift:] + arms[:shift]
                                      for item in rows[start:start + base.CHUNK]]
                        reason = base.execute(
                            queue, lambda job: solve_one(api, record, out, job[0], *texts[job[0]], job[1]), probe)
                    finally:
                        if not fixture:
                            api.close()
                except Exception as exc:
                    reason = "error:" + type(exc).__name__
            statuses, counts, costs = base.collect(out, record)
            if reason is None and (any(c["not_run"] for c in counts.values()) or costs["open_intents"]):
                reason = "incomplete"
            result = seal({"version": VERSION, "pilot_hash": record["record_hash"],
                           "status": "completed" if reason is None else "pending", "reason": reason,
                           "items": len(statuses), "arms": counts, "costs": costs,
                           "costs_complete": not (costs["unresolved_calls"] or costs["attempts_without_usage"]
                                                  or costs["open_intents"])})
            write_json(out / "result.json", result)
            return result


def report(output, contrasts=()):
    """Zero calls: the headroom pilot's report (counts, Wilson intervals, paired contrasts with coverage and
    missing-outcome bounds, counts by difficulty) plus, per derived arm, what the rubric did: verdict counts and the
    transitions of the scored answer against the model's own (fixed / broke / same)."""
    value = base.report(output, contrasts)
    value.pop("chance")
    out = safe_path(output)
    record = read_json(out / "pilot.json", sealed=True)
    statuses, _, _ = base.collect(out, record)
    levels = {i["id"]: i["meta"]["difficulty"] for i in read_json(out / "items.json", sealed=True)["items"]}
    value["by_difficulty"] = {
        level: {"items": sum(v == level for v in levels.values()),
                **{a["name"]: {"pass": sum(statuses[i].get(a["name"]) == "pass" for i in statuses if levels[i] == level),
                               "known": sum(statuses[i].get(a["name"]) in ("pass", "fail") for i in statuses if levels[i] == level)}
                   for a in record["arms"]}}
        for level in sorted(set(levels.values()))}
    value["rubric"] = {}
    for a in record["arms"]:
        if not a["derived_from"]:
            continue
        verdicts, sources = {}, {}
        transitions = {"fixed": 0, "broke": 0, "same_pass": 0, "same_fail": 0}
        for path in base._published(out / "calls"):
            row = read_json(path, sealed=True)
            if row["arm"] != a["name"] or row["status"] == "unknown":
                continue
            verdicts[row["rubric"]["verdict"]] = verdicts.get(row["rubric"]["verdict"], 0) + 1
            sources[row["scored_source"]] = sources.get(row["scored_source"], 0) + 1
            model = statuses[row["item"]].get(a["derived_from"])
            transitions["fixed" if (model, row["status"]) == ("fail", "pass") else
                        "broke" if (model, row["status"]) == ("pass", "fail") else
                        "same_pass" if row["status"] == "pass" else "same_fail"] += 1
        value["rubric"][a["name"]] = {"verdicts": verdicts, "scored_from": sources, "transitions": transitions}
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for name in ("study", "repo", "output", "upstream", "id-split", "revision"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--arm", action="append", default=[])
    sub.add_parser("run").add_argument("--output", required=True)
    r = sub.add_parser("report")
    r.add_argument("--output", required=True)
    r.add_argument("--contrast", action="append", default=[])
    args = parser.parse_args(argv)
    if args.command == "prepare":
        record = prepare(args.study, args.repo, args.upstream, args.id_split, args.output, args.arm, revision=args.revision)
        value = {k: record[k] for k in ("version", "items", "dropped_without_parsed_page", "record_hash")}
        value["arms"] = [a["name"] for a in record["arms"]]
    elif args.command == "run":
        result = run(args.output)
        value = {k: result[k] for k in ("status", "reason", "items", "arms", "costs")}
    else:
        value = report(args.output, args.contrast)
    print(json.dumps(value, ensure_ascii=False))
    return 0 if args.command != "run" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
