"""Zero-call: how far apart are one-step candidates proposed from IDENTICAL analyst inputs? In the rubric-form and
binding studies an arm whose rubric was not authorized in a block (and a bound arm whose binding was not applied)
gets exactly the scalar arm's (or its base arm's) analyst inputs -- same traces, same systems, same seeds -- so the
selection-set passes of such arms differ only by analyst sampling and evaluation sampling. Arms are grouped by the
digest of their sealed proposal identity's input fields; every pair inside a group is a same-input difference.
Usage: noise.py <study dir>:<block> [...]"""
import collections
import itertools
import json
import math
import os
import sys

from skillopt.validator_pilot.api import digest

INPUT_FIELDS = ("parent_skill", "traces_hash", "analyst_systems", "seed", "minibatch_size", "edit_budget", "rollout",
                "verifier_reports_hash")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv):
    differences, groups_seen, spreads = [], 0, []
    for spec in argv:
        root, block = spec.rsplit(":", 1)
        block = int(block)
        label = os.path.basename(os.path.dirname(root.rstrip("/"))).replace("fivebench-g-2026101", "")
        outcome = read(os.path.join(root, "blocks", str(block), "outcome.json"))
        groups = collections.defaultdict(list)
        for arm, value in outcome["arms"].items():
            path = os.path.join(root, "native", str(block), arm, "identity.json")
            if not os.path.exists(path) or value["evaluated"] != "candidate":
                continue  # a failed proposal stays on the parent: not a candidate
            identity = read(path)
            groups[digest({k: identity.get(k) for k in INPUT_FIELDS})].append((arm, value["pass"], value["evaluation_slot"]))
        for members in groups.values():
            if len(members) < 2:
                continue
            groups_seen += 1
            passes = [p for _, p, _ in members]
            mean = sum(passes) / len(passes)
            spreads.append((len(passes), sum((p - mean) ** 2 for p in passes)))
            shared = sorted({slot for _, _, slot in members})
            for (a, pa, sa), (b, pb, sb) in itertools.combinations(members, 2):
                if sa != sb:  # two distinct candidate texts, each scored on its own rollout
                    differences.append(pa - pb)
            print("%s:%d same-input group %s (distinct evaluations %d)" % (label, block, [(a, p) for a, p, _ in members], len(shared)))
    if not differences:
        print("no same-input pairs")
        return
    pooled = sum(ss for _, ss in spreads) / sum(n - 1 for n, _ in spreads)
    print("\ngroups %d | pairwise same-input differences %d: %s" % (groups_seen, len(differences), sorted(differences)))
    print("absolute difference: median %.1f, max %d | pooled within-group SD of passes %.2f (difference SD ~ %.2f)" % (
        sorted(abs(d) for d in differences)[len(differences) // 2], max(abs(d) for d in differences),
        math.sqrt(pooled), math.sqrt(2 * pooled)))


if __name__ == "__main__":
    main(sys.argv[1:])
