"""Zero-call: where the rubric-form arms' candidates win and lose on the selection set, by question type, and whether the
analyst's failure-minibatch reasoning mentions the verification notes at all. Reads sealed evaluation intents/records
(arm = candidate hash + rollout), the study panel (generated selection items: public question text only) and the native
proposal records. Question types come from a regex over the public question (rounding requested / arithmetic words /
list or date form); the private answer is never read. Usage (PYTHONPATH = the study's source snapshot):
positions.py <study dir>:<block> [...]"""
import collections
import json
import os
import re
import sys

from skillopt.validator_pilot.api import digest

PAIRS = (("global_text", "scalar"), ("global_text", "default_text"), ("format_code", "format_text"), ("scalar", "parent"),
         ("global_text", "parent"), ("default_text", "parent"), ("compliance_code", "scalar"), ("labelled", "scalar"))
FORMS = re.compile(r"\[|bracket|comma-separated|list|date|month and day|day of", re.I)
ROUND = re.compile(r"round|decimal|nearest|significant", re.I)
ARITH = re.compile(r"\bsum\b|total|difference|average|mean|median|ratio|growth|change|percent|rate|increase|decrease|"
                   r"divid|multipl|subtract|add(ed|ing)?\b|combined|how many more|times|product|standard deviation|cagr", re.I)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def kind(question):
    arithmetic = bool(ARITH.search(question))
    rounding = bool(ROUND.search(question))
    form = bool(FORMS.search(question))
    return ("computation" if arithmetic else "lookup") + ("+rounding" if rounding else "") + ("+form" if form else "")


def main(argv):
    wins = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))  # pair -> kind -> [wins, losses]
    mentions = collections.defaultdict(lambda: [0, 0])  # arm -> [failure minibatches mentioning verification, failure minibatches]
    kinds_total = collections.Counter()
    for spec in argv:
        root, block = spec.rsplit(":", 1)
        block = int(block)
        panel = read(os.path.join(root, "panel.json"))
        tasks = {}
        for task in panel["tasks"]:
            if task["partition"] != "development":
                tasks[digest(task)] = task["public"].get("question", "")
        outcome = read(os.path.join(root, "blocks", str(block), "outcome.json"))
        plan = read(os.path.join(root, "blocks", str(block), "plan.json"))
        # one selection rollout per arm within a block (the block plan's validation_rollouts; the parent is rollout 1);
        # arms whose candidate shared another arm's evaluation (identical text) point at that arm's rollout
        arms = dict(plan["validation_rollouts"])
        for arm, v in outcome["arms"].items():
            arms[arm] = v["rollout"]
        statuses = collections.defaultdict(dict)  # rollout -> task_hash -> status
        folder = os.path.join(root, "evaluation_intents")
        for name in os.listdir(folder):
            intent = read(os.path.join(folder, name))
            if intent["role"] != "selection":
                continue
            record = read(os.path.join(root, "evaluations", name))
            statuses[intent["rollout"]][intent["task_hash"]] = record["score"]["status"]
        missing = [arm for arm, key in arms.items() if key not in statuses]
        if missing:
            print("block %s: no selection evaluations found for %s (keys %s)" % (spec, missing, sorted(statuses)[:3]))
        label = os.path.basename(os.path.dirname(root.rstrip("/")))
        counts = {arm: sum(1 for s in statuses.get(key, {}).values() if s == "pass") for arm, key in arms.items()}
        print("block %s:%d passes %s" % (label, block, counts))
        for treatment, control in PAIRS:
            if treatment not in arms or control not in arms or arms[treatment] not in statuses or arms[control] not in statuses:
                continue
            a, b = statuses[arms[treatment]], statuses[arms[control]]
            for task_hash in a:
                if task_hash not in b or task_hash not in tasks:
                    continue
                k = kind(tasks[task_hash])
                if a[task_hash] == "pass" and b[task_hash] == "fail":
                    wins[(treatment, control)][k][0] += 1
                elif a[task_hash] == "fail" and b[task_hash] == "pass":
                    wins[(treatment, control)][k][1] += 1
        for task_hash in statuses.get(arms["parent"], {}):
            if task_hash in tasks:
                kinds_total[kind(tasks[task_hash])] += 1
        for arm in outcome["arms"]:
            path = os.path.join(root, "native", str(block), arm, "result.json")
            if not os.path.exists(path):
                continue
            for item in read(path).get("raw", []):
                if item.get("source_type") != "failure":
                    continue
                text = json.dumps(item, ensure_ascii=False).lower()
                mentions[arm][1] += 1
                if re.search(r"verifier|verification note|\[verification\]|flagged|the verification", text):
                    mentions[arm][0] += 1
    print("\nselection items by question type (per block, from the public question text):", dict(kinds_total.most_common()))
    for pair, by_kind in wins.items():
        total = [sum(v[0] for v in by_kind.values()), sum(v[1] for v in by_kind.values())]
        print("%-16s - %-13s wins/losses pooled %d/%d | by type %s" % (
            pair[0], pair[1], total[0], total[1], {k: "%d/%d" % tuple(v) for k, v in sorted(by_kind.items())}))
    print("\nfailure minibatches whose analyst reasoning/summary mentions verification (mentioning/total):")
    for arm, v in mentions.items():
        print("  %-16s %d/%d" % (arm, v[0], v[1]))


if __name__ == "__main__":
    main(sys.argv[1:])
