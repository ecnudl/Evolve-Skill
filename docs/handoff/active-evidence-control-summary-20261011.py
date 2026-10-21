"""Zero-call reading of matched-study stages that carry named evaluation-only references, in particular the fixed
generic-instruction controls of active-evidence-generic-control-design-20261011.md. Counts, intervals and usage
only; development holdouts; never test data. Run with PYTHONPATH = the stage's source snapshot (the paired
difference and its Tango interval are the package's own `matched.paired_difference`).

Per stage:
* every arm that solved the holdout (parent = no Skill, comparator = pass/fail branch, treatment = diagnosis
  branch, each named reference): pass / fail / unknown, mean reasoning tokens, mean completion tokens and the
  median / mean length of the visible answer (descriptive: what the Skill changes in the solver's behaviour and what
  it costs);
* paired contrasts in the memo's reading order -- the study's own three, then for every named reference:
  reference minus parent, comparator minus reference, treatment minus reference -- and, descriptively, every pair
  of named references. Single-task families (SearchQA, BigCodeBench): task-level wins / losses and the Tango 95%
  interval. For KOR-Bench the task-level interval ignores the clustering of tasks in rules and is DESCRIPTIVE; the
  family-level reading is active-evidence-family-summary-20261011.py / active-evidence-kor-pooled-20261011.py.
The numbers for the contrasts the study itself sealed must equal the sealed study record (printed by
study_summary.py); this script adds the reference-versus-reference pairs and the usage columns."""
import collections
import glob
import json
import os
import statistics
import sys

from skillopt.active_evidence.matched import paired_difference, sign_test_p


def J(path):
    return json.load(open(path))


def main(stage):
    L = stage.rstrip("/") + "/learning"
    name = stage.rstrip("/").split("fivebench-g-")[-1]
    if not (os.path.exists(L + "/challenge/0/outcome.json") and os.path.exists(L + "/challenge/0/references.json")):
        print(name, "| no holdout outcome or no reference record: nothing to read")
        return
    outcome, refs = J(L + "/challenge/0/outcome.json"), J(L + "/challenge/0/references.json")
    fresh = [p for p in outcome.get("positions") or [] if p["set"] == "fresh"]
    if not fresh or not refs.get("positions"):
        print(name, "| holdout or references not run: nothing to read")
        return
    families = collections.Counter(p["family_id"] for p in fresh)
    clustered = max(families.values()) > 1
    status = {"comparator": {p["task_hash"]: p["current"]["status"] for p in fresh},
              "treatment": {p["task_hash"]: p["candidate"]["status"] for p in fresh}}
    for p in refs["positions"]:
        for ref, cell in p["reference"].items():
            status.setdefault(ref, {})[p["task_hash"]] = cell["status"]
    rollout = {"comparator": outcome["rollouts"]["current"], "treatment": outcome["rollouts"]["candidate"],
               **{r["name"]: r["rollout"] for r in refs["references"]}}
    named = [r["name"] for r in refs["references"] if r["name"] != "parent"]
    arms = ["parent", "comparator", "treatment"] + named
    usage = collections.defaultdict(list)
    wanted = {v: k for k, v in rollout.items()}
    hashes = {p["task_hash"] for p in fresh}
    for path in glob.glob(L + "/evaluations/*"):
        record = J(path)
        request = record["request"]
        if request["task_hash"] in hashes and request["rollout"] in wanted:
            use = (record["prediction"].get("costs") or {}).get("usage") or {}
            usage[wanted[request["rollout"]]].append((
                (use.get("completion_tokens_details") or {}).get("reasoning_tokens"), use.get("completion_tokens"),
                len(record["prediction"].get("output") or "")))
    print("%s | holdout %d positions, %d families%s" % (
        name, len(fresh), len(families), " (several tasks per family: task-level intervals are DESCRIPTIVE)" if clustered else ""))
    print("  %-16s %5s %5s %7s | %14s %14s | %s" % ("arm", "pass", "fail", "unknown", "reasoning tok", "completion tok", "visible chars median / mean"))
    for arm in arms:
        values = list(status[arm].values())
        rows = usage.get(arm) or []
        mean = lambda k: ("%.0f" % statistics.mean(r[k] for r in rows if r[k] is not None)) if any(r[k] is not None for r in rows) else "n/a"
        print("  %-16s %5d %5d %7d | %14s %14s | %s" % (
            arm, values.count("pass"), values.count("fail"), len(values) - values.count("pass") - values.count("fail"),
            mean(0), mean(1), ("%d / %.0f" % (statistics.median(r[2] for r in rows), statistics.mean(r[2] for r in rows))) if rows else "n/a"))
    pairs = [("comparator", "parent"), ("treatment", "parent"), ("treatment", "comparator")]
    for ref in named:
        pairs += [(ref, "parent"), ("comparator", ref), ("treatment", ref)]
    pairs += [(a, b) for i, a in enumerate(named) for b in named[i + 1:]]
    for a, b in pairs:
        wins = losses = ties = 0
        for h in hashes:
            x, y = status[a].get(h), status[b].get(h)
            if x in ("pass", "fail") and y in ("pass", "fail"):
                wins += x == "pass" and y == "fail"
                losses += x == "fail" and y == "pass"
                ties += x == y
        known = wins + losses + ties
        d = paired_difference(wins, losses, known)
        low, high = d["ci95"] if d["ci95"] else (float("nan"), float("nan"))
        print("  %-34s w/l/t %3d/%3d/%3d  known %3d  d %+.3f  ci95 [%+.3f, %+.3f]  sign p %.4f" % (
            "%s - %s" % (a, b), wins, losses, ties, known, d["estimate"] if d["estimate"] is not None else float("nan"),
            low, high, sign_test_p(wins, losses)))


if __name__ == "__main__":
    for stage in sys.argv[1:]:
        main(stage)
