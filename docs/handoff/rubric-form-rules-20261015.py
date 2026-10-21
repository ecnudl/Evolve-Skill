"""Zero-call: which kinds of rules each arm's candidate ADDED in each block of the rubric-form study, next to the
candidate's selection-set passes -- a mechanism check for the descriptive lead of global_text (did its candidates
carry a 'follow the rounding/format instruction literally' rule more often, given that 77% of the generated items
ask for a rounded computation?). Reads sealed proposal records (candidate and parent texts) and outcomes.
Usage: rules.py <study dir>:<block> [...]"""
import collections
import difflib
import json
import os
import re
import sys

ARMS = ("scalar", "labelled", "default_text", "global_text", "cluster_text", "format_text", "format_code", "compliance_code")
RULES = [
    ("rounding/format literal", r"round|decimal|hundredth|tenth|significant|format(ting)? (instruction|sentence|rule)|literally"),
    ("unit/scale", r"\bunits?\b|billion|million|thousand|percent"),
    ("second-route verification", r"second route|verify|re-?check|double-check|sanity"),
    ("missing data", r"not (in|on) the (context|supplied|provided)|absent|missing|does not contain|not present"),
    ("duplicate/vintage choice", r"duplicate|overlapping|vintage|revised|multiple (bulletin|issue|edition)"),
    ("statistics procedure", r"standard deviation|geometric mean|growth rate|cagr|z-score|trimmed|median|mean\b"),
    ("period/series mapping", r"period|fiscal|calendar|quarter|series|range of years|inclusive"),
]


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def added(parent, candidate):
    return [line[1:] for line in difflib.unified_diff(parent.splitlines(), candidate.splitlines(), lineterm="", n=0)
            if line.startswith("+") and not line.startswith("+++")]


def main(argv):
    rows = []
    per_rule = {arm: collections.Counter() for arm in ARMS}
    blocks = 0
    for spec in argv:
        root, block = spec.rsplit(":", 1)
        block = int(block)
        blocks += 1
        label = os.path.basename(os.path.dirname(root.rstrip("/"))).replace("fivebench-g-20261014-officeqa-rubric-form-", "")
        outcome = read(os.path.join(root, "blocks", str(block), "outcome.json"))
        parent_pass = outcome["evaluations"]["parent"]["pass"]
        for arm in ARMS:
            path = os.path.join(root, "native", str(block), arm, "result.json")
            if not os.path.exists(path):
                rows.append((label, arm, None, parent_pass, set()))
                continue
            result = read(path)
            parent = read(os.path.join(root, "native", str(block), arm, "identity.json"))["parent_skill"]
            text = "\n".join(added(parent, result.get("candidate_skill") or "")).lower()
            kinds = {name for name, pattern in RULES if re.search(pattern, text)}
            for kind in kinds:
                per_rule[arm][kind] += 1
            rows.append((label, arm, outcome["arms"][arm]["pass"], parent_pass, kinds))
    print("block  arm              pass (parent)  added rule kinds")
    for label, arm, passes, parent_pass, kinds in rows:
        print("%-6s %-16s %4s (%3d)       %s" % (label, arm, passes if passes is not None else "-", parent_pass, ", ".join(sorted(kinds)) or "-"))
    print("\nblocks whose candidate added a rule of each kind (of %d):" % blocks)
    kinds = [name for name, _ in RULES]
    print("%-16s " % "arm" + " ".join("%-24s" % k[:24] for k in kinds))
    for arm in ARMS:
        print("%-16s " % arm + " ".join("%-24d" % per_rule[arm][k] for k in kinds))
    # within each arm: mean passes of blocks WITH vs WITHOUT a rounding/format-literal rule (descriptive)
    print("\nmean passes with vs without a 'rounding/format literal' rule (pooled over arms and blocks, descriptive):")
    with_rule = [p for _, _, p, _, k in rows if p is not None and "rounding/format literal" in k]
    without = [p for _, _, p, _, k in rows if p is not None and "rounding/format literal" not in k]
    print("  with: n=%d mean %.1f | without: n=%d mean %.1f" % (len(with_rule), sum(with_rule) / max(1, len(with_rule)),
                                                                   len(without), sum(without) / max(1, len(without))))


if __name__ == "__main__":
    main(sys.argv[1:])
