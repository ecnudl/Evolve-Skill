"""Zero-call reading ACROSS several KOR-Bench matched-branch study stages (one learning history each) of the design
in active-evidence-kor-study-design-20261011.md. Counts and intervals only; development holdouts; never test data.

Every stage is first read exactly as active-evidence-family-summary-20261011.py reads it (the per-history numbers
printed here must equal that script's). Then, per contrast, two readings across histories, both fixed in the memo's
addendum of 2026-10-11 evening before any replication outcome existed:

* rule-clustered: for every rule family that was a holdout family in at least one eligible history, the mean over
  those histories of its within-family difference of pass rates on jointly known positions (kept as exact
  fractions); then the equal-weight mean over rules with a t interval over rules and the exact two-sided sign test
  over non-tied rules. Rules and histories are CROSSED (a Skill is shared by the 20 holdout rules of its history,
  and step rules overlap between seeds), so the interval and the p-value are WORKING-INDEPENDENCE summaries, not
  calibrated inference about the procedure: they understate the uncertainty by an unknown amount.
* history-level: the list of per-history family means and how many are positive (no interval).

Estimand: the equal-weight mean, over the observed eligible holdout rules, of the realized one-step updates'
within-rule effect -- not an equal-history average, not the effect of one Skill, not the reliability of the
procedure, and not a confirmation: the pools are reused development data. A history is eligible for a contrast
when the per-history script would call that contrast primary or an available-family estimate (same rules,
re-implemented here; the parent reference is required only by the contrasts that use it); ineligible histories
are listed and left out. The reading is printed for all given stages and, when asked with --also-without <name>,
again without the named stage (the sensitivity reading that leaves out the already known first history)."""
import collections
import json
import math
import os
import sys
from fractions import Fraction

MISSING_FAMILY_SHARE = 0.1
MIN_KNOWN_SHARE = 0.9
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}
BRANCHES = {"comparator": "current", "treatment": "candidate"}
CONTRASTS = (("comparator", "parent"), ("treatment", "parent"), ("treatment", "comparator"))


def all_contrasts(stages):
    """The three study contrasts, then -- for every NAMED reference any stage evaluated (e.g. the fixed generic
    instruction of active-evidence-generic-control-design-20261011.md) -- reference minus parent and each branch
    minus that reference. A history that did not evaluate the reference is listed as not eligible for those."""
    names = set()
    for stage in stages:
        path = stage.rstrip("/") + "/learning/challenge/0/references.json"
        if os.path.exists(path):
            for p in J(path).get("positions") or []:  # a not_run reference record has no positions
                names.update(p["reference"])
    extra = []
    for name in sorted(names - {"parent"}):
        extra += [(name, "parent"), ("comparator", name), ("treatment", name)]
    return CONTRASTS + tuple(extra)


def J(path):
    return json.load(open(path))


def t975(df):
    if df in T975:
        return T975[df]
    if df < 1:
        return float("nan")
    z = 1.959964
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2)


def sign_two_sided(a, b):
    n = a + b
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(a, b) + 1)) / 2 ** n)


def interval(values):
    """Mean and t interval; signs are classified on the exact fractions by the callers, never on these floats."""
    values = [float(v) for v in values]
    n = len(values)
    mean = sum(values) / n if n else float("nan")
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else float("nan")
    half = t975(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    return mean, mean - half, mean + half


def history(stage, contrasts=CONTRASTS):
    """{contrast: (reason or None, {family: within-family difference})} for one stage, or None when unreadable."""
    L = stage.rstrip("/") + "/learning"
    if not os.path.exists(L + "/challenge/0/outcome.json"):
        return None
    fresh = [p for p in J(L + "/challenge/0/outcome.json").get("positions") or [] if p["set"] == "fresh"]
    if not fresh:  # a holdout that was not run (or drew nothing) is unavailable, never an eligible empty history
        return None
    matched = (J(L + "/chain/0.json").get("matched") or {}) if os.path.exists(L + "/chain/0.json") else {}
    status = {b: {p["task_hash"]: p[key]["status"] for p in fresh} for b, key in BRANCHES.items()}
    if os.path.exists(L + "/challenge/0/references.json"):  # needed only by the contrasts that name a reference
        for p in J(L + "/challenge/0/references.json").get("positions") or []:
            for ref, cell in p["reference"].items():
                status.setdefault(ref, {})[p["task_hash"]] = cell["status"]
    sealed = ((matched.get("references") or {}).get("branches")) or {}
    changed = {b: (sealed.get(b) or {}).get("updated") is True for b in BRANCHES}
    out = {}
    for a, b in contrasts:
        reason = None
        if not matched:
            reason = "no sealed study record"
        elif a not in status or b not in status:
            reason = "no %s record" % (a if a not in status else b)
        elif (a, b) == ("treatment", "comparator") and matched.get("candidates_identical"):
            reason = "identical Skill texts"
        elif (a, b) == ("treatment", "comparator") and (matched.get("delivery") or {}).get("problem"):
            reason = "treatment package not delivered"
        elif any(x in BRANCHES and not changed[x] for x in (a, b)):
            reason = "a branch is not recorded as a Skill that differs from the parent"
        fam = collections.defaultdict(lambda: [0, 0, 0])
        known = 0
        for p in fresh:
            cell = fam[p["family_id"]]
            x, y = (status.get(a) or {}).get(p["task_hash"]), (status.get(b) or {}).get(p["task_hash"])
            if x in ("pass", "fail") and y in ("pass", "fail"):
                known += 1
                cell[0] += 1
                cell[1] += x == "pass"
                cell[2] += y == "pass"
        missing = [f for f, c in fam.items() if not c[0]]
        if reason is None and known < math.ceil(MIN_KNOWN_SHARE * len(fresh)):
            reason = "%d of %d positions jointly known" % (known, len(fresh))
        if reason is None and len(missing) > math.floor(MISSING_FAMILY_SHARE * len(fam)):
            reason = "%d of %d families missing" % (len(missing), len(fam))
        out[(a, b)] = (reason, {f: Fraction(c[1] - c[2], c[0]) for f, c in fam.items() if c[0]})
    return out


def main(stages):
    read = {}
    contrasts = all_contrasts(stages)
    for stage in stages:
        name = stage.rstrip("/").split("fivebench-g-")[-1]
        h = history(stage, contrasts)
        if h is None:
            print("%s | no holdout outcome (missing, not run or empty): left out" % name)
            continue
        read[name] = h
    table(read, contrasts)


def table(read, contrasts):
    for a, b in contrasts:
        print("== %s - %s" % (a, b))
        by_rule = collections.defaultdict(list)
        means = []
        for name, h in read.items():
            reason, diffs = h[(a, b)]
            if reason:
                print("    %-40s NOT ELIGIBLE (%s)" % (name, reason))
                continue
            mean, low, high = interval(list(diffs.values()))
            up = sum(d > 0 for d in diffs.values())
            down = sum(d < 0 for d in diffs.values())
            print("    %-40s families %2d  mean %+.3f  t95 [%+.3f, %+.3f]  improving/regressing/tied %d/%d/%d"
                  % (name, len(diffs), mean, low, high, up, down, len(diffs) - up - down))
            means.append(sum(diffs.values(), Fraction(0)) / len(diffs))  # exact: its sign is classified below
            for family, d in diffs.items():
                by_rule[family].append(d)
        if not means:
            print("    no eligible history")
            continue
        rule = [sum(v, Fraction(0)) / len(v) for v in by_rule.values()]
        mean, low, high = interval(rule)
        up = sum(v > 0 for v in rule)
        down = sum(v < 0 for v in rule)
        print("    rule-clustered: rules %d (histories per rule %s)  mean %+.3f  t95 [%+.3f, %+.3f]  "
              "improving/regressing/tied %d/%d/%d  sign p %.3f"
              % (len(rule), sorted(collections.Counter(len(v) for v in by_rule.values()).items()), mean, low, high,
                 up, down, len(rule) - up - down, sign_two_sided(up, down)))
        print("    history-level: %d histories, family means %s, positive %d, negative %d, exactly zero %d"
              % (len(means), ["%+.3f" % float(m) for m in means], sum(m > 0 for m in means),
                 sum(m < 0 for m in means), sum(m == 0 for m in means)))


if __name__ == "__main__":
    arguments = sys.argv[1:]
    without = None
    if "--also-without" in arguments:
        at = arguments.index("--also-without")
        without = arguments[at + 1]
        arguments = arguments[:at] + arguments[at + 2:]
    main(arguments)
    if without:
        print("#### sensitivity: the same reading without %s" % without)
        main([stage for stage in arguments if without not in stage])
