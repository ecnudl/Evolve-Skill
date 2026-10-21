"""Zero-call (10/15, owner's question "is the solver too strong, so that Skill differences are hidden?"): the
rubric-form and binding studies evaluated the SAME parent Skill (OfficeQA zero-shot instruction) on the SAME 124
generated selection items once per block, each time with a fresh rollout, and evaluated 4-8 one-step candidates per
block on those items. Twelve blocks give twelve independent parent runs and ~80 candidate runs per item. Per item:
the parent's pass rate p (over its runs) and the candidates' pass rate c (over all candidate runs). Classes:
always-pass (p = 1), always-fail (p = 0), flaky (in between). The question the classes answer: where could a Skill
update show an effect at all, and does any candidate move the items the parent always fails?
Only public question text is read (for the item type); never the private answer. Usage:
item_stability.py <study dir>:<block> [...]"""
import collections
import json
import os
import re
import sys

from skillopt.validator_pilot.api import digest

ROUND = re.compile(r"round|decimal|nearest|significant", re.I)
ARITH = re.compile(r"\bsum\b|total|difference|average|mean|median|ratio|growth|change|percent|rate|increase|decrease|"
                   r"divid|multipl|subtract|combined|how many more|times|product|standard deviation|cagr|geometric|log", re.I)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def kind(question):
    return ("computation" if ARITH.search(question) else "lookup") + ("+rounding" if ROUND.search(question) else "")


def main(argv):
    parent = collections.defaultdict(list)     # task -> [pass booleans] of the parent
    cand = collections.defaultdict(list)       # task -> [pass booleans] of candidates
    by_arm = collections.defaultdict(lambda: collections.defaultdict(list))
    questions = {}
    for spec in argv:
        root, block = spec.rsplit(":", 1)
        block = int(block)
        if not questions:
            for task in read(os.path.join(root, "panel.json"))["tasks"]:
                if task["partition"] != "development":
                    questions[digest(task)] = task["public"].get("question", "")
        outcome = read(os.path.join(root, "blocks", str(block), "outcome.json"))
        slot_of = {v["rollout"]: slot for slot, v in outcome["evaluations"].items()}
        runs = collections.defaultdict(dict)
        folder = os.path.join(root, "evaluation_intents")
        for name in os.listdir(folder):
            intent = read(os.path.join(folder, name))
            if intent["role"] != "selection" or intent["rollout"] not in slot_of:
                continue
            status = read(os.path.join(root, "evaluations", name))["score"]["status"]
            if status in ("pass", "fail"):
                runs[intent["rollout"]][intent["task_hash"]] = status == "pass"
        for rollout, statuses in runs.items():
            slot = slot_of[rollout]
            for task, ok in statuses.items():
                (parent if slot == "parent" else cand)[task].append(ok)
                if slot != "parent":
                    by_arm[slot][task].append(ok)
    tasks = sorted(set(parent) & set(cand) & set(questions))
    n_runs = collections.Counter(len(parent[t]) for t in tasks)
    print("items %d | parent runs per item %s | candidate runs per item %s" % (
        len(tasks), dict(n_runs), dict(collections.Counter(len(cand[t]) for t in tasks).most_common(3))))
    classes = collections.defaultdict(list)
    for t in tasks:
        p = sum(parent[t]) / len(parent[t])
        classes["always_pass" if p == 1 else "always_fail" if p == 0 else "flaky"].append(t)
    total_p = sum(sum(parent[t]) / len(parent[t]) for t in tasks)
    total_c = sum(sum(cand[t]) / len(cand[t]) for t in tasks)
    print("expected passes per run (of %d): parent %.1f | candidates %.1f | difference %+.1f" % (len(tasks), total_p, total_c, total_c - total_p))
    for name in ("always_pass", "flaky", "always_fail"):
        items = classes[name]
        if not items:
            print("  %-12s 0 items" % name)
            continue
        p = sum(sum(parent[t]) / len(parent[t]) for t in items)
        c = sum(sum(cand[t]) / len(cand[t]) for t in items)
        kinds = collections.Counter(kind(questions[t]) for t in items)
        print("  %-12s %3d items | parent expected passes %.1f | candidates %.1f (%+.1f) | types %s" % (
            name, len(items), p, c, c - p, dict(kinds.most_common())))
    # the always-fail items: does ANY candidate fix them, and how often
    fixed = [(t, sum(cand[t]), len(cand[t])) for t in classes["always_fail"] if sum(cand[t]) > 0]
    print("always-fail items that some candidate passed at least once: %d of %d; candidate pass rate on them: %s" % (
        len(fixed), len(classes["always_fail"]), sorted(round(a / b, 2) for _, a, b in fixed)))
    broken = [(t, len(cand[t]) - sum(cand[t]), len(cand[t])) for t in classes["always_pass"] if sum(cand[t]) < len(cand[t])]
    print("always-pass items that some candidate failed at least once: %d of %d; candidate fail rate on them: %s" % (
        len(broken), len(classes["always_pass"]), sorted(round(a / b, 2) for _, a, b in broken)[-12:]))
    # items whose candidate rate differs from the parent rate by >= 0.3 (with >= 6 parent runs)
    big = [(t, sum(parent[t]) / len(parent[t]), sum(cand[t]) / len(cand[t])) for t in tasks]
    up = [x for x in big if x[2] - x[1] >= 0.3]
    down = [x for x in big if x[1] - x[2] >= 0.3]
    print("items with candidate rate >= parent rate + 0.3: %d | <= parent rate - 0.3: %d" % (len(up), len(down)))
    for t, p, c in sorted(up, key=lambda x: x[1] - x[2])[:6]:
        print("    up   p=%.2f c=%.2f | %s" % (p, c, " ".join(questions[t].split())[:150]))
    for t, p, c in sorted(down, key=lambda x: x[2] - x[1])[:6]:
        print("    down p=%.2f c=%.2f | %s" % (p, c, " ".join(questions[t].split())[:150]))
    print("always-fail examples (question text, first 150 chars):")
    for t in classes["always_fail"][:8]:
        print("    c=%.2f | %s" % (sum(cand[t]) / len(cand[t]), " ".join(questions[t].split())[:150]))
    print("per arm, expected passes over the items it was run on, minus the parent's on the same items:")
    for arm, per in sorted(by_arm.items()):
        common = [t for t in tasks if t in per]
        d = sum(sum(per[t]) / len(per[t]) - sum(parent[t]) / len(parent[t]) for t in common)
        print("    %-19s runs/item %s | %+.1f" % (arm, collections.Counter(len(per[t]) for t in common).most_common(1)[0][0], d))


if __name__ == "__main__":
    main(sys.argv[1:])
