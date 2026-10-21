"""Zero-call family-level reading of one matched-branch study stage whose holdout has several tasks per family
(KOR-Bench: one rule = one family). Counts and intervals only; development holdout; never test data.

Primary (frozen before any outcome is read, see active-evidence-kor-study-design-20261011.md): the mean over
families of the within-family difference of pass rates on jointly known positions, with an approximate t interval
over families (families assumed independent; conditional on the realized pair of Skills) and the exact two-sided
sign test over non-tied families (a test of directional balance, not of the mean). A family with no jointly known
position is MISSING: it is listed, never counted as a tie; the estimate is then labelled an available-family
estimate, and with more than a tenth of the families missing (the study's 90% coverage rule applied to families:
more than 2 of 20) it is not a primary estimate at all. Task-level counts are descriptive only: their intervals
ignore the clustering of tasks inside rules. Every contrast separately needs ceil(0.9 * positions) jointly known
positions (180 of 200), as the study's own coverage rule does; below it no primary estimate is reported.

Eligibility comes from the sealed study record: identical Skill texts, a branch that did not change the parent, a
failed delivery or insufficient coverage make a contrast diagnostic only (a same-Skill replicate is not an effect)."""
import collections
import json
import math
import os
import sys

MISSING_FAMILY_SHARE = 0.1
MIN_KNOWN_SHARE = 0.9  # the study's coverage rule, applied to every contrast: ceil(0.9 * positions) jointly known
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def J(path):
    return json.load(open(path))


def t975(df):
    """Two-sided 95% critical value of Student's t: the table up to 30 degrees of freedom, beyond it the
    Cornish-Fisher expansion around the normal quantile (error below 0.001 there)."""
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
    k = min(a, b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def contrast(name, rows, families, note):
    """rows: (family, status_a, status_b); the contrast is a minus b on jointly known positions."""
    fam = {family: [0, 0, 0] for family in families}  # jointly known, a pass, b pass
    wins = losses = ties = unknown = 0
    for family, a, b in rows:
        if a not in ("pass", "fail") or b not in ("pass", "fail"):
            unknown += 1
            continue
        cell = fam[family]
        cell[0] += 1
        cell[1] += a == "pass"
        cell[2] += b == "pass"
        wins += a == "pass" and b == "fail"
        losses += a == "fail" and b == "pass"
        ties += a == b
    missing = sorted(f for f, c in fam.items() if not c[0])
    diffs = [(c[1] - c[2]) / c[0] for c in fam.values() if c[0]]
    n = len(diffs)
    mean = sum(diffs) / n if n else float("nan")
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1)) if n > 1 else float("nan")
    half = t975(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    up = sum(d > 0 for d in diffs)
    down = sum(d < 0 for d in diffs)
    known = wins + losses + ties
    need = math.ceil(MIN_KNOWN_SHARE * len(rows))
    if known < need:
        label = "NOT PRIMARY: %d of %d positions jointly known, %d required" % (known, len(rows), need)
    elif len(missing) > math.floor(MISSING_FAMILY_SHARE * len(fam)):
        label = "NOT PRIMARY: %d of %d families missing" % (len(missing), len(fam))
    elif missing:
        label = "AVAILABLE-FAMILY estimate (%d of %d families)" % (n, len(fam))
    else:
        label = "primary"
    if note:
        label = "DIAGNOSTIC ONLY (%s)%s" % (note, "" if label in ("primary",) or label.startswith("AVAILABLE") else "; " + label)
    print("%-24s [%s]" % (name, label))
    print("    families %d (df %d)  mean diff %+.3f  t95 [%+.3f, %+.3f]  improving/regressing/tied %d/%d/%d  sign p %.3f"
          % (n, n - 1, mean, mean - half, mean + half, up, down, n - up - down, sign_two_sided(up, down)))
    print("    tasks (descriptive) w/l/t %d/%d/%d  jointly known %d  unknown %d  task diff %+.3f" % (
        wins, losses, ties, known, unknown, (wins - losses) / known if known else float("nan")))
    print("    jointly known per family: %s%s" % (
        sorted(collections.Counter(c[0] for c in fam.values()).items()),
        "  MISSING families: %s" % missing if missing else ""))


def main(stage):
    L = stage + "/learning"
    name = stage.rstrip("/").split("/")[-1]
    if not os.path.exists(L + "/challenge/0/outcome.json"):
        print(name, "| NO HOLDOUT OUTCOME (the study step did not reach or finish its holdout): nothing to read")
        return
    outcome = J(L + "/challenge/0/outcome.json")
    fresh = [p for p in outcome["positions"] if p["set"] == "fresh"]
    by_task = {p["task_hash"]: p for p in fresh}
    families = collections.Counter(p["family_id"] for p in fresh)
    print(name, "| holdout status", outcome["status"], "| fresh positions", len(fresh), "| families", len(families),
          "| tasks per family", sorted(collections.Counter(families.values()).items()))
    matched = J(L + "/chain/0.json").get("matched") or {} if os.path.exists(L + "/chain/0.json") else {}
    study_outcome = matched.get("outcome") or {}
    print("  sealed study record: class %s (%s) | candidates identical %s | delivery problem %s | holdout %s" % (
        study_outcome.get("outcome"), study_outcome.get("reason"), matched.get("candidates_identical"),
        (matched.get("delivery") or {}).get("problem"), matched.get("holdout")))
    branches = {"comparator": "current", "treatment": "candidate"}
    status = {b: {h: p[key]["status"] for h, p in by_task.items()} for b, key in branches.items()}
    sealed = ((matched.get("references") or {}).get("branches")) or {}
    # the sealed record says whether a branch's Skill differs from the parent; absent -> not established
    changed = {b: (sealed.get(b) or {}).get("updated") is True for b in branches}
    refs = J(L + "/challenge/0/references.json") if os.path.exists(L + "/challenge/0/references.json") else None
    if refs is None:
        print("  INCOMPLETE EVALUATION: no reference record -- the parent contrasts are not available")
    else:
        for p in refs["positions"]:
            for ref, cell in p["reference"].items():
                status.setdefault(ref, {})[p["task_hash"]] = cell["status"]
    for column, values in status.items():
        v = list(values.values())
        print("  %-12s pass %3d fail %3d unknown %d" % (column, v.count("pass"), v.count("fail"),
                                                          len(v) - v.count("pass") - v.count("fail")))

    def note(a, b):
        problems = []
        if not matched:
            problems.append("no sealed study record")
        if (a, b) == ("treatment", "comparator") and matched.get("candidates_identical"):
            problems.append("identical Skill texts: same-Skill replicate")
        if (a, b) == ("treatment", "comparator") and (matched.get("delivery") or {}).get("problem"):
            problems.append("treatment package not delivered")
        for branch in (a, b):
            if branch in branches and matched and not changed[branch]:
                problems.append("%s is not recorded as a Skill that differs from the parent" % branch)
        return "; ".join(problems)

    pairs = [("treatment", "comparator")] + [(b, r) for r in status if r not in branches for b in ("treatment", "comparator")]
    for a, b in pairs:
        contrast("%s - %s" % (a, b), [(by_task[h]["family_id"], status[a].get(h), status[b].get(h)) for h in by_task],
                 list(families), note(a, b))


if __name__ == "__main__":
    for stage in sys.argv[1:]:
        main(stage)
