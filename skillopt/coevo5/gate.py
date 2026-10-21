"""The heuristic X v2 gate (registration §5) as pure functions of one round's bounds table (``stats.bounds``).

The benefit criterion (C1) compares a rule with the parent and with irrelevant-text controls at the rule's own
placement; harm criteria (C2, C3) compare it with the parent only, bench by bench, within registered tolerances; a
similar placement also needs the rule to do no worse than the parent on every similar target's check panel (C4', no
controls). A rule is judged on its conservative rate L (unknown = fail), the parent and the controls on H (unknown =
pass). No error rate is guaranteed or estimated.

v3 (registration delta §3): a pool item on which no arm that scheduled it in a round got any reply -- e.g. a provider's
content filter -- leaves every criterion of that round (the caller, ``step.shared_unanswered``, drops it from every item
set); a rule left with fewer than ``min_trigger`` trigger items (the caller passes ``MIN_TRIGGER``) is undetermined. v3
§7: ``held``, the rule's own evidence items, leave C2 but still count in its unknown share.
"""
from __future__ import annotations

from fractions import Fraction

from skillopt.continual_eval.core import require

from .protocol import (
    FORWARD_PANEL,
    MAX_EXTRA_VIOLATIONS,
    MAX_SKILL_BYTES,
    MAX_UNKNOWN_SHARE,
    MIN_GAIN,
    MIN_SIMILAR_DELTA,
)
from .stats import total, unknown_share


def round_complete(table, guards):
    """``guards``: {arm: [items]} for the parent and every control of the round. False when any of them has more than
    10% infrastructure-unknown runs: the round is infrastructure-incomplete and the chain pauses (§5.4, §13.4)."""
    return all(unknown_share(table, arm, items, infrastructure_only=True) <= MAX_UNKNOWN_SHARE
               for arm, items in guards.items())


def _too_few(trigger, criteria):
    """v3 §3: a trigger set the exclusion left with fewer than ``min_trigger`` items cannot be judged."""
    criteria["trigger_after_exclusion"] = len(trigger)
    return {"status": "undetermined", "margin": 0, "priority": 0, "criteria": _plain(criteria)}


def _benefit(table, arm, parent, controls, items):
    """C1: gain over the parent >= 1 item and strictly above every control. Returns (ok, gain, margin)."""
    rule = total(table, arm, items, "L")
    gain = rule - total(table, parent, items, "H")
    best = max(total(table, c, items, "H") for c in controls)
    return gain >= MIN_GAIN and rule > best, gain, rule - best


def _no_harm(table, arm, parent, items, tolerance):
    delta = total(table, arm, items, "L") - total(table, parent, items, "H")
    return delta >= -tolerance, delta


def _regression(table, arm, parent, regression):
    """C3 per earlier bench: {bench: {"items", "tolerance", "violations": (arm violations incl. unknown, parent's)}}.
    Panel sizes and tolerances come from the manifest (60 items; every qualified SpreadsheetBench item if fewer)."""
    rows = {}
    for bench, panel in sorted(regression.items()):
        require(panel["items"] and type(panel["tolerance"]) is int and panel["tolerance"] >= 0,
                "A regression panel has items and a tolerance")
        ok, delta = _no_harm(table, arm, parent, panel["items"], panel["tolerance"])
        extra = panel["violations"][0] - panel["violations"][1]
        rows[bench] = {"ok": ok and extra <= MAX_EXTRA_VIOLATIONS, "delta": delta, "extra_violations": extra}
    return rows


def _scheduled(*groups):
    return [i for group in groups for i in group]


def _status(table, arm, items, ok, criteria):
    """"undetermined" when more than 10% of the arm's runs this round are unknown (§5.4): such an arm is never accepted."""
    share = unknown_share(table, arm, items)
    if share > MAX_UNKNOWN_SHARE:
        criteria["unknown_share"] = share
        return "undetermined"
    return "pass" if ok else "fail"


def _similar(table, arm, parent, targets, regression):
    """C4' per similar target: {bench: items of its check panel} -- a backward target's regression panel (the very
    items of C3), a forward target's frozen panel of 8-12 generated items. Returns {bench: {"ok", "delta"}}."""
    require(targets, "A similar arm has at least one similar target")
    rows = {}
    for bench, items in sorted(targets.items()):
        if bench in regression:
            require(list(items) == list(regression[bench]["items"]),
                    "A backward target is checked on its regression panel")
        else:
            require(FORWARD_PANEL[0] <= len(items) <= FORWARD_PANEL[1] and len(set(items)) == len(items),
                    "A forward target is checked on a frozen panel of 8-12 items")
        delta = total(table, arm, items, "L") - total(table, parent, items, "H")
        rows[bench] = {"ok": delta >= MIN_SIMILAR_DELTA, "delta": delta}
    return rows


def verdict(table, *, arm, parent, controls, trigger, rest, tolerance, regression, targets=None, min_trigger=None,
            held=()):
    """One rule arm in one round: C1-C3, and C4' for a similar arm. ``controls``: the four same-placement control arms,
    measured on ``trigger``; ``targets``: a similar arm's check panels, {bench: items} (``_similar``).

    Returns {"status": "pass" | "fail" | "undetermined", "margin": C1 margin, "priority": the C1 margin plus, for a
    similar arm, every target's delta (§5.7 step 4), "criteria": ...}. v3 §3: ``min_trigger``, the fewest trigger items
    a verdict may rest on once shared-unknown items left the round (fewer: undetermined); ``held``, scheduled items no
    criterion reads (the rule's evidence, left out of C2), which still count in the arm's unknown share."""
    require(len(controls) == 4, "Four controls at the rule's placement")
    if min_trigger is not None and len(trigger) < min_trigger:
        return _too_few(trigger, {})
    require(trigger and not set(trigger) & set(rest) and not set(held) & (set(trigger) | set(rest)),
            "Trigger items are nonempty and disjoint from the rest and from the held items")
    c1, gain, margin = _benefit(table, arm, parent, controls, trigger)
    c2, rest_delta = _no_harm(table, arm, parent, rest, tolerance)
    c3 = _regression(table, arm, parent, regression)
    criteria = {"C1": {"ok": c1, "gain": gain, "margin": margin}, "C2": {"ok": c2, "delta": rest_delta}, "C3": c3}
    ok = c1 and c2 and all(row["ok"] for row in c3.values())
    rank = margin
    if targets is not None:
        c4 = _similar(table, arm, parent, targets, regression)
        criteria["C4'"] = c4
        ok = ok and all(row["ok"] for row in c4.values())
        rank = margin + sum(row["delta"] for row in c4.values())
    items = _scheduled(trigger, rest, held, *(p["items"] for p in regression.values()),
                       *(items for bench, items in sorted((targets or {}).items()) if bench not in regression))
    status = _status(table, arm, items, ok, criteria)
    return {"status": status, "margin": margin, "priority": rank, "criteria": _plain(criteria)}


def placement(similar, local):
    """The tentative placement after the screen (§5.7 step 2): similar if the similar arm passed C1-C3 and C4', else the
    bench's own section if that arm passed C1-C3, else none."""
    if similar is not None and similar["status"] == "pass":
        return "similar"
    if local is not None and local["status"] == "pass":
        return "local"
    return None


def confirmation_arms(tentative, screen_local):
    """The arms a rule's confirmation round tests (§5.7 step 3): a tentatively similar rule its similar arm, and its own
    arm too when that one passed the screen; a tentatively local rule its own arm."""
    if tentative == "similar":
        return ["similar"] + (["local"] if screen_local is not None and screen_local["status"] == "pass" else [])
    return ["local"] if tentative == "local" else []


def final_placement(tentative, *, screen_local, confirm_similar=None, confirm_local=None):
    """The final placement (§5.7 step 3): similar when the tentatively similar rule's similar arm passed again; else the
    bench's own section when its own arm passed C1-C3 in both rounds; else not accepted."""
    if tentative == "similar" and confirm_similar is not None and confirm_similar["status"] == "pass":
        return "similar"
    if (screen_local is not None and screen_local["status"] == "pass" and confirm_local is not None
            and confirm_local["status"] == "pass"):
        return "local"
    return None


def priority(margins):
    """Rule ids ordered by their screen priority (``verdict``'s "priority" of the tentative placement's arm), largest
    first; ties by rule id (registration §5.7)."""
    return sorted(margins, key=lambda rule: (-Fraction(margins[rule]), rule))


def fitting_subset(order, size, cap=MAX_SKILL_BYTES):
    """§5.7 step 5, fixed before the composition round: walk the confirmed rules in priority order and keep each one
    whose addition leaves the rendered Skill within the cap. ``size(rules)`` is the byte size of the parent with
    ``rules`` appended. Every rule fits on its own (longer ones are dropped before the gate), so the first one stays."""
    chosen = []
    for rule in order:
        if size(chosen + [rule]) <= cap:
            chosen.append(rule)
    require(list(order[:1]) == chosen[:1], "The highest-priority rule fits on its own")
    return chosen


def composite(table, *, arm, parent, members, rest, tolerance, regression, panels=None, min_trigger=None, held=()):
    """The composition round on the fixed text S: ``members`` = [{"id", "trigger"}]; ``rest`` is the focal panel without
    any member's trigger items; ``panels``: every check panel S's similar rules involve, {name: items} (a backward
    target's regression panel once, however many rules name it; each similar rule's own forward panels). Every member
    keeps a gain >= 1 on its own trigger items, the rest and every earlier bench stay within tolerance, and S does no
    worse than the parent on every check panel. ``held``: as in ``verdict`` (the members' evidence items)."""
    require(len(members) >= 2, "A composite has at least two members")
    short = {m["id"]: len(m["trigger"]) for m in members if min_trigger is not None and len(m["trigger"]) < min_trigger}
    if short:
        return {"status": "undetermined", "criteria": {"trigger_after_exclusion": short}}
    rows, ok = {}, True
    for member in members:
        gain = total(table, arm, member["trigger"], "L") - total(table, parent, member["trigger"], "H")
        rows[member["id"]] = {"trigger_gain": gain, "ok": gain >= MIN_GAIN}
        ok = ok and gain >= MIN_GAIN
    c2, rest_delta = _no_harm(table, arm, parent, rest, tolerance)
    c3 = _regression(table, arm, parent, regression)
    checks = {}
    for name, items in sorted((panels or {}).items()):
        delta = total(table, arm, items, "L") - total(table, parent, items, "H")
        checks[name] = {"ok": delta >= MIN_SIMILAR_DELTA, "delta": delta}
    ok = ok and c2 and all(row["ok"] for row in c3.values()) and all(row["ok"] for row in checks.values())
    criteria = {"members": rows, "C2": {"ok": c2, "delta": rest_delta}, "C3": c3, "C4'": checks}
    items = _scheduled(rest, held, *(m["trigger"] for m in members), *(p["items"] for p in regression.values()),
                       *(items for _, items in sorted((panels or {}).items())))
    status = _status(table, arm, list(dict.fromkeys(items)), ok, criteria)
    return {"status": status, "criteria": _plain(criteria)}


def accepted(subset, composite_status=None):
    """The rules a stage merges (§5.7): none; the single fitting rule; the whole fitting subset S when its composition
    round passed; else the first (highest-priority) rule of S. The merged text is exactly the one that was tested."""
    if len(subset) <= 1:
        return list(subset)
    require(composite_status in ("pass", "fail", "undetermined"), "Two or more rules need a composition round")
    return list(subset) if composite_status == "pass" else list(subset[:1])


def placebo_passage(table, controls, trigger_sets, parent):
    """Descriptive only (§5.8): in one round, each control in turn plays a rule against the other three on every rule's
    trigger items, C1 only. Returns {control: {rule: passed?}}. Not an estimate of any false-acceptance rate: real
    rules face four controls, are written against failures and are selected over two rounds and a placement."""
    require(len(controls) == 4, "Four controls")
    out = {}
    for candidate in controls:
        others = [c for c in controls if c != candidate]
        out[candidate] = {}
        for rule, items in sorted(trigger_sets.items()):
            rule_l = total(table, candidate, items, "L")
            gain = rule_l - total(table, parent, items, "H")
            best = max(total(table, c, items, "H") for c in others)
            out[candidate][rule] = gain >= MIN_GAIN and rule_l > best
    return out


def _plain(value):
    """JSON-safe copy: exact fractions as strings."""
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value
