#!/usr/bin/env python3
"""Final evaluation reader of the two-architecture experiment (2026-10-16; design
docs/handoff/two-architectures-design-20261016.md section 7). Zero calls; written before any final result.

Reads completed ``scripts/weak_solver_probe.py`` directories. An arm is a (probe directory, Skill name); every arm of
one report must come from probes of the same solver configuration and the same item sources, so that the arms were
measured on exactly the same items. Per item label (the probe's label: "val" for the E items of the pilot file,
"skill_confirmation" for the transfer items, ...), an arm's item rate is its mean pass over its known runs, and a
contrast A - B over the items known for both arms reports: the sum of the per-item differences (unit: items), the
items better / worse / tied, a two-sided sign test over the better and worse items, and a 95% percentile bootstrap
interval of the sum, resampling items with replacement (BOOTSTRAP resamples, seeded).

Registered design (section 7), enforced: E is exactly the pilot file's 24 val items (ids, questions and reference
answers checked against ``--pilot``), every arm has exactly E_RUNS runs per item, all arms the same.

Registered reading (section 7), encoded per contrast: E ("val") is the primary label, T ("skill_confirmation") the
support; any other label (the gate items G, say) is descriptive only. An interval that contains 0 means "not
established", never "no effect"; a positive E contrast is read as an effect only when T's interval is above 0 too,
otherwise "positive on E, not supported by T: not read as an effect".

Usage:
  report_two_architectures.py --pilot <pilot items.json> --arm <name>=<probe dir>:<skill> [...]
      --contrast <A>-<B> [...] [--json <new file>]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import weak_solver_probe as probe  # noqa: E402

VERSION = "two-architectures-report-v1"
BOOTSTRAP, SEED, LEVEL = 10000, 20261016, 0.95
E_LABEL, T_LABEL, E_ITEMS, E_RUNS = "val", "skill_confirmation", 24, 3
ROLES = {E_LABEL: "E (primary)", T_LABEL: "T (support)"}
SOLVER_KEYS = ("version", "backend", "model", "benchmark", "max_tokens", "thinking", "reasoning_effort", "temperature",
               "proxy", "response_model_ids", "session_id_header", "prompt")
KNOWN = ("pass", "fail")


def _probe(directory):
    d = Path(directory)
    config = json.loads((d / "config.json").read_text(encoding="utf-8"))
    summary_path = d / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    if summary.get("status") != "completed" or summary.get("config_hash") != probe.digest(config):
        raise SystemExit("Probe %s: no completed summary of this config" % d.name)
    return d, config


def arm_runs(directory, skill):
    """(config, {item: (label, [statuses by run])}) of one arm; every item needs exactly the probe's runs."""
    d, config = _probe(directory)
    if skill not in config["skills"]:
        raise SystemExit("Probe %s has no Skill %s" % (d.name, skill))
    found = {}
    for path in sorted((d / "records" / skill).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        label, runs = found.setdefault(record["item"], (record["label"], {}))
        if record.get("skill") != skill or record["run"] in runs or record["label"] != label:
            raise SystemExit("Probe %s: inconsistent records of %s" % (d.name, skill))
        runs[record["run"]] = record["status"]
    if len(found) != config["n_items"] or any(sorted(r) != list(range(config["runs"])) for _, r in found.values()):
        raise SystemExit("Probe %s: incomplete runs of %s" % (d.name, skill))
    return config, {item: (label, [runs[k] for k in range(config["runs"])]) for item, (label, runs) in found.items()}


def rate(statuses):
    known = [s for s in statuses if s in KNOWN]
    return sum(s == "pass" for s in known) / len(known) if known else None


def sign_test(better, worse):
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def bootstrap(differences, resamples=BOOTSTRAP, seed=SEED, level=LEVEL):
    """The percentile interval of the sum of ``differences`` over item resamples (None for no item)."""
    if not differences:
        return None
    rng, n = random.Random(seed), len(differences)
    sums = sorted(sum(differences[rng.randrange(n)] for _ in range(n)) for _ in range(resamples))
    tail = (1 - level) / 2
    return [round(sums[int(math.floor(tail * (resamples - 1)))], 6),
            round(sums[int(math.ceil((1 - tail) * (resamples - 1)))], 6)]


def contrast(a, b):
    """A - B over the items of one label known for both arms (``a``/``b``: {item: statuses})."""
    differences, better, worse, tied, unknown = [], 0, 0, 0, 0
    for item in sorted(set(a) | set(b)):
        if item not in a or item not in b:
            raise SystemExit("The arms were not measured on the same items")
        ra, rb = rate(a[item]), rate(b[item])
        if ra is None or rb is None:
            unknown += 1
            continue
        d = ra - rb
        differences.append(d)
        better, worse, tied = better + (d > 0), worse + (d < 0), tied + (d == 0)
    interval = bootstrap(differences)
    total = round(sum(differences), 6)
    return {"items": len(differences), "excluded_unknown": unknown, "sum": total,
            "mean_per_item": round(total / len(differences), 6) if differences else None, "better": better,
            "worse": worse, "tied": tied, "sign_test_p": round(sign_test(better, worse), 6), "interval": interval,
            "reading": ("no item" if interval is None else "not established (interval contains 0)"
                        if interval[0] <= 0 <= interval[1] else "positive" if interval[0] > 0 else "negative")}


def registered_e(pilot):
    """{id: (public, reference answer)} of the pilot file's val items: the registered E."""
    items = json.loads(Path(pilot).read_text(encoding="utf-8"))["items"]
    val = {i["id"]: (i["public"], i["private"].get("answer")) for i in items if i.get("meta", {}).get("part") == E_LABEL}
    if len(val) != E_ITEMS:
        raise SystemExit("The pilot file does not hold the registered %d val items" % E_ITEMS)
    return val


def _check_e(config, expected):
    rows = [row for spec in config["items"] for row in probe.load_items(spec)]
    if probe.digest(sorted(probe.digest(r) for r in rows)) != config["items_hash"]:
        raise SystemExit("A probe's item sources changed")
    e = {r["id"]: (r["public"], r["private"].get("answer")) for r in rows if r["label"] == E_LABEL}
    if e != expected:
        raise SystemExit("The probe's E items are not exactly the registered 24 pilot val items")


def joint(e, t):
    """The registered reading of one contrast from its E and T results."""
    if e is None or e["interval"] is None:
        return "no E item"
    if e["reading"] != "positive":
        return "negative on E" if e["reading"] == "negative" else "not established on E (interval contains 0)"
    if t is not None and t["reading"] == "positive":
        return "effect: positive on E, supported by T"
    return "positive on E, not supported by T: not read as an effect"


def report(arms, contrasts, pilot):
    expected = registered_e(pilot)
    loaded, identity = {}, None
    for spec in arms:
        name, _, source = spec.partition("=")
        directory, _, skill = source.rpartition(":")
        if not name or not directory or not skill or name in loaded:
            raise SystemExit("--arm <unique name>=<probe dir>:<skill>")
        config, runs = arm_runs(directory, skill)
        if config["runs"] != E_RUNS:
            raise SystemExit("Arm %s: %d runs per item, the registration needs %d" % (name, config["runs"], E_RUNS))
        key = ({k: config.get(k) for k in SOLVER_KEYS}, config["items_hash"], config["runs"])
        if identity is None:
            identity = key
        elif key != identity:
            raise SystemExit("Arm %s: another solver configuration, other items or other runs than the first arm"
                             % name)
        _check_e(config, expected)
        loaded[name] = {"probe": str(Path(directory).resolve()), "skill": skill, "skill_hash": config["skills"][skill]["hash"],
                        "config_hash": probe.digest(config), "runs": runs}
    labels = sorted({label for arm in loaded.values() for label, _ in arm["runs"].values()})
    per_label = lambda arm, label: {i: s for i, (lab, s) in loaded[arm]["runs"].items() if lab == label}
    out = {"version": VERSION, "bootstrap": {"resamples": BOOTSTRAP, "seed": SEED, "level": LEVEL},
           "solver": identity[0], "items_hash": identity[1], "runs": identity[2],
           "roles": {label: ROLES.get(label, "descriptive only (not an effect)") for label in labels},
           "arms": {n: {k: v for k, v in a.items() if k != "runs"} for n, a in loaded.items()},
           "pass_rate": {n: {label: _pooled(per_label(n, label)) for label in labels} for n in loaded}, "contrasts": {}}
    for spec in contrasts:
        a, _, b = spec.partition("-")
        if a not in loaded or b not in loaded or a == b:
            raise SystemExit("--contrast <arm>-<arm> over two loaded arms: %s" % spec)
        by_label = {label: contrast(per_label(a, label), per_label(b, label)) for label in labels}
        out["contrasts"][spec] = {"by_label": by_label,
                                  "reading": joint(by_label.get(E_LABEL), by_label.get(T_LABEL))}
    return out


def _pooled(runs):
    known = [s for statuses in runs.values() for s in statuses if s in KNOWN]
    return {"items": len(runs), "known_runs": len(known),
            "pass_rate": round(sum(s == "pass" for s in known) / len(known), 6) if known else None}


def lines(value):
    out = ["%s | solver %s %s | bootstrap %d resamples, seed %d" % (
        value["version"], value["solver"]["model"], value["solver"]["benchmark"], value["bootstrap"]["resamples"],
        value["bootstrap"]["seed"])]
    for name, by_label in value["pass_rate"].items():
        out.append("  %-12s " % name + "  ".join("%s %s (%d runs)" % (label, v["pass_rate"], v["known_runs"])
                                                  for label, v in by_label.items()))
    for spec, c_all in value["contrasts"].items():
        out.append("  %s: %s" % (spec, c_all["reading"]))
        for label, c in c_all["by_label"].items():
            out.append("    %-20s %-18s items %3d sum %+7.3f better %2d worse %2d tied %2d p=%.4g 95%% [%s] -> %s" % (
                label, value["roles"][label], c["items"], c["sum"], c["better"], c["worse"], c["tied"],
                c["sign_test_p"], "" if c["interval"] is None else "%+.3f, %+.3f" % tuple(c["interval"]),
                c["reading"]))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pilot", required=True)
    parser.add_argument("--arm", action="append", required=True)
    parser.add_argument("--contrast", action="append", default=[])
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    value = report(args.arm, args.contrast, args.pilot)
    if args.json:
        with open(args.json, "x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1, sort_keys=True)
    print("\n".join(lines(value)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
