"""Zero-call summary of the solver-strength probes (scripts/weak_solver_probe.py; 10/15): for every model and item set
(OfficeQA generated selection items, OfficeQA real train/val items, SearchQA generated items), each Skill's pass rate
over known cells, the spread between Skills, item stability classes of the zero-shot instruction, and item-level
contrasts (instruction - empty, each learned Skill - instruction) with their exact sign tests. Reads sealed probe
records only. Usage: summary.py <probe dir> [<probe dir> ...]"""
import collections
import json
import math
import sys
from pathlib import Path


def sign_test(a, b):
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def item_set(label):
    if label in ("skill_confirmation",):
        return "generated"
    if label in ("train", "val"):
        return "real"
    return str(label)


def main(dirs):
    rows = []
    for d in map(Path, dirs):
        config = json.loads((d / "config.json").read_text())
        summary = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
        records = [json.loads(p.read_text()) for p in sorted((d / "records").rglob("*.json"))]
        rows.append((d, config, summary, records))
    print("model            bench     set        skill      pass/known   rate   unknown")
    for d, config, summary, records in rows:
        status = summary.get("status", "running")
        by = collections.defaultdict(lambda: collections.defaultdict(dict))  # (set, skill) -> item -> run -> status
        for r in records:
            by[(item_set(r.get("label")), r["skill"])][r["item"]][r["run"]] = r["status"]
        sets = sorted({k[0] for k in by})
        for s in sets:
            rates = {}
            for skill in sorted(config["skills"]):
                cells = [v for item in by[(s, skill)].values() for v in item.values()]
                known = cells.count("pass") + cells.count("fail")
                rates[skill] = cells.count("pass") / known if known else None
                print("%-16s %-9s %-10s %-10s %4d/%-5d %s  %d%s" % (
                    config["model"], config["benchmark"], s, skill, cells.count("pass"), known,
                    "%.3f" % rates[skill] if known else " N/A ", cells.count("unknown"), "" if status == "completed" else "  (" + status + ")"))
            known_rates = [v for v in rates.values() if v is not None]
            if len(known_rates) > 1:
                print("%-16s %-9s %-10s spread (max - min) %.3f" % (config["model"], config["benchmark"], s, max(known_rates) - min(known_rates)))
            ref = "bzero" if "bzero" in config["skills"] else None
            if ref:
                classes = collections.Counter()
                for item, runs in by[(s, ref)].items():
                    values = list(runs.values())
                    if any(v not in ("pass", "fail") for v in values) or len(values) < config["runs"]:
                        classes["with_unknown_or_missing"] += 1
                    else:
                        classes["always_pass" if all(v == "pass" for v in values) else "always_fail" if all(v == "fail" for v in values) else "flaky"] += 1
                print("%-16s %-9s %-10s zero-shot instruction item classes %s" % (config["model"], config["benchmark"], s, dict(classes)))
                for other in sorted(config["skills"]):
                    if other == ref:
                        continue
                    a, b = (ref, other) if other == "empty" else (other, ref)
                    better = worse = tied = 0
                    for item in by[(s, a)]:
                        net = 0
                        known = 0
                        for run, sa in by[(s, a)][item].items():
                            sb = by[(s, b)].get(item, {}).get(run)
                            if sa in ("pass", "fail") and sb in ("pass", "fail"):
                                known += 1
                                net += (sa == "pass") - (sb == "pass")
                        if known:
                            better += net > 0
                            worse += net < 0
                            tied += net == 0
                    print("%-16s %-9s %-10s   %s - %s: items better %d worse %d tied %d, p=%.4f" % (
                        config["model"], config["benchmark"], s, a, b, better, worse, tied, sign_test(better, worse)))


if __name__ == "__main__":
    main(sys.argv[1:])
