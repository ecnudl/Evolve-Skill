"""Read-only chain-end extraction for the two-chain five-bench runs, with the pre-registered secondary analysis
(docs/handoff/main-v5-identical-request-prereg-20261031.md, written 2026-10-31 03:1x before any main-v5 test directory
existed): for every reported contrast (F-C, C-B, F-B, each stage arm minus C and minus the previous stage arm), a run on
which both arms' solver requests are present and byte-identical (every call's request sha256, in order; a shared cell
uses the requests of the cell it reads) counts 0. The registered readout stays the primary analysis.

Runs it accepts:
  main-v5  opening needs the owner's approval of that read (owner rule: test aggregates stay unopened without a per-run
           approval); refuses unless BOTH chains have ended (registered isolation).
  main-v4  already opened with the owner's 10/30 11:3x approval; re-run only to validate this script: its readout
           record must equal the 10/31 03:05 extraction (same label, so the same record sha256).
Loads each completed unit's cells as evaluation.unseal does, WITHOUT its gates and writes (no owner-continuation record,
so the registered unseal/report, which writes the root scan and marker, is not run; nothing is written under the run
root); learned, procedures and the stage rows are derived as readout.report() derives them, and readout.readout() is
called with the same keywords. Secondary estimates use readout.estimate with the read's design, without the bootstrap.
Run from the run's code snapshot with PYTHONPATH set to it, python -B. Usage: fivebench-readout.py CONFIGURATION OUT.json"""
import json, os, sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from skillopt.continual_eval.core import read_json
from skillopt.execskill import readout, profiles
from skillopt.execskill.package import empty, load
from skillopt.execskill.protocol import verified
RUNS = {"main-v5": ("/data/execskill-20261031-main-v5", "/data/execskill-20261031-main-v5-manifest.json",
                    "owner_approved_read_only_extraction_main_v5_not_registered_unseal"),
        "main-v4": ("/data/execskill-20261029-main-v4", "/data/execskill-20261029-main-v4-manifest.json",
                    "owner_approved_read_only_extraction_20261030_not_registered_unseal")}
CHAINS = ("G", "D")
# Older snapshots (main-v4 is v2.11.1) predate these helpers; their absence means "not that kind of run".
IS_V213 = getattr(profiles, "is_v213", lambda configuration: False)
IS_ZEBRA_FC = getattr(profiles, "is_zebra_fc", lambda configuration: False)
MAINS = tuple(getattr(profiles, n) for n in ("MAIN_V3", "MAIN_V4", "MAIN_V5") if hasattr(profiles, n))
CONF, OUT = sys.argv[1], sys.argv[2]
ROOT, MANIFEST, LABEL = RUNS[CONF]
assert not os.path.exists(OUT), "output exists"
for chain in CHAINS:
    assert any(os.path.exists("%s/%s/%s" % (ROOT, chain, n)) for n in ("chain-complete.json", "chain-terminated.json")), \
        "chain %s has not ended: test scores stay sealed" % chain
manifest = verified(read_json(MANIFEST), "manifest")
assert manifest["configuration"] == CONF and manifest["root"] == ROOT
run, evidence = manifest[profiles.RECORD_HASH], manifest["evidence"]
result = {"run_root": ROOT, "run": run, "configuration": CONF, "label": LABEL, "chains": {},
          "secondary_rule": "docs/handoff/main-v5-identical-request-prereg-20261031.md"}


def resolved(sha, shared, key):
    """The request hashes of the cell an (arm, item, run) reads: its own, or those of the cell it shares."""
    seen = set()
    while shared.get(key) is not None:
        assert key not in seen, "a sharing cycle"
        seen.add(key); key = shared[key]
    return sha[key]


def pair(cells, sha, shared, first, second):
    """Primary (readout.differences) and secondary differences of first - second, with the tie counts."""
    items = readout._items(cells, first, second)
    d = readout.differences(cells, first, second, items)
    d2, structural, identical = [], 0, 0
    for item in items:
        runs = readout._runs(cells, first, item)
        assert runs and runs == readout._runs(cells, second, item)
        total, same_cell, same_request = Fraction(0), 0, 0
        for r in runs:
            if readout._source(cells, first, item, r) == readout._source(cells, second, item, r):
                same_cell += 1
                continue
            f, s = resolved(sha, shared, (first, item, r)), resolved(sha, shared, (second, item, r))
            if f and f == s and all(f):
                same_request += 1
                continue
            total += (readout._score(cells[(first, item, r)]["v2"], readout.side(first))
                      - readout._score(cells[(second, item, r)]["v2"], readout.side(second)))
        structural += same_cell == len(runs)
        identical += same_cell < len(runs) and same_cell + same_request == len(runs)
        d2.append(total / len(runs))
    design = readout._design(cells, items)
    est = (lambda x: readout.estimate(x, design=design) if len(x) >= 2 else None)
    count = (lambda x: {"better": sum(v > 0 for v in x), "worse": sum(v < 0 for v in x), "tied": sum(v == 0 for v in x)})
    return {"n": len(items), "items_reading_one_cell": structural, "items_tied_by_identical_requests": identical,
            "primary": {**count(d), "estimate": est(d)}, "secondary": {**count(d2), "estimate": est(d2)}}


for chain in CHAINS:
    chain_root = "%s/%s" % (ROOT, chain)
    out = result["chains"][chain] = {}
    if not os.path.exists(chain_root + "/test-read.json"):
        out["test_read"] = None; continue
    read = verified(read_json(chain_root + "/test-read.json"), "test-read")
    out["test_read"] = {"status": read["status"], "package_sha256": read.get("package_sha256")}
    if read["status"] != "read":
        continue
    start = empty(step="%s/s0" % chain, evidence=evidence)
    final = start if read["package_sha256"] == start.sha256 else load(
        Path(chain_root) / "packages" / (read["package_sha256"] + ".json"))
    procedures = {p.id: p.origin for p in final.procedures}
    roster = profiles.read_benches(CONF)
    learned = [b for b in roster if b in procedures.values() and not IS_V213(CONF)
               and not (CONF in MAINS and b == "alfworld")]
    out.update(procedures=procedures, learned=learned)
    units, hashes, sharing, stages, missing = {}, {}, {}, {}, []
    for bench in roster:
        unit_root = "%s/test/%s" % (chain_root, bench)
        if not os.path.exists(unit_root + "/unit.json"):
            missing.append(bench); continue
        own = verified(read_json(unit_root + "/unit.json"), "evaluation")
        assert own["chain"] == chain and own["run"] == run and own["bench"] == bench, "unit of another chain/run"
        cells, arm_of, key_of, sha, shared = {}, {}, {}, {}, {}
        for cell in own["cells"]:
            value = verified(read_json("%s/%s/cells/%s.json" % (unit_root, own["attempt"], cell)), "evaluation-cell")
            key = (value["cell"]["arm"], value["cell"]["task_id"], value["cell"]["run"])
            assert key not in cells, "one cell per arm, item and run"
            arm_of[value["cell"]["id"]], key_of[value["cell"]["id"]] = value["cell"]["arm"], key
            judged = value["judge"]
            cells[key] = {"token": value["final"]["token"], "v2": judged["v2"], "official": judged["official"],
                          "final": judged["final"], "lenient": judged["lenient"], "kind": value["final"]["kind"],
                          "shared_with": value["shared_with"], "answered": value["answered"],
                          "enabled": value["enabled"], "block": value["cell"]["block"],
                          "room": value["cell"].get("room"),
                          "format": judged["format"], "flags": judged["flags"], "carrier": judged["carrier"],
                          "fault_kinds": value["fault_kinds"], "worst_delivery": value["worst_delivery"],
                          "dispatch_ts": value["dispatch_ts"], "finish_ts": value["finish_ts"],
                          "completion_tokens": [c["completion_tokens"] for c in value["calls"]],
                          "solver_route": value.get("solver_route")}
            sha[key] = tuple(c.get("request_sha256") for c in value["calls"])
        for key, value in cells.items():
            value["shared_arm"] = None if value["shared_with"] is None else arm_of[value["shared_with"]]
            shared[key] = None if value["shared_with"] is None else key_of[value["shared_with"]]
        units[bench], hashes[bench], sharing[bench] = cells, sha, shared
        if "stages" in own:
            stages[bench] = list(own["stages"]["rows"])
    out["units_present"], out["units_missing"] = sorted(units, key=profiles.SUPPORTED_BENCHES.index), missing
    if not units:
        continue
    rows = {tuple(found) for found in stages.values()}
    assert len(rows) <= 1 and (not rows or set(stages) == set(units)), "every read unit names the same stage rows"
    rows = list(rows.pop()) if rows else None
    out["stage_rows"] = rows
    record = readout.readout(units, learned=learned, procedures=procedures, label=LABEL, evidence=evidence,
                             stages=rows, **({"configuration": CONF}
                                             if profiles.is_v210(CONF) or IS_ZEBRA_FC(CONF) else {}))
    out["readout_record_sha256"] = record[profiles.RECORD_HASH]
    out["readout"] = record
    per = out["per_bench"] = {}
    for bench, cells in units.items():
        arms = sorted({a for a, _, _ in cells})
        wanted = [(a, b) for a, b in (("F", "C"), ("C", "B"), ("F", "B")) if a in arms and b in arms]
        for k, arm in enumerate(rows or []):
            if arm != "C":
                wanted.append((arm, "C"))
            if k and rows[k - 1] != arm:
                wanted.append((arm, rows[k - 1]))
        wanted = list(dict.fromkeys(wanted))
        items = readout._items(cells, *arms)
        per[bench] = {"arms": arms, "items_all_arms": len(items),
                      "acc": {a: readout._accuracy(cells, a, items, readout.side(a)) for a in arms},
                      "side": {a: readout.side(a) for a in arms},
                      "solver_models": dict(Counter((v.get("solver_route") or {}).get("model") for v in cells.values())),
                      "pairs": {a + "-" + b: pair(cells, hashes[bench], sharing[bench], a, b) for a, b in wanted}}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=1, default=str)
for chain, out in result["chains"].items():
    for bench, row in (out.get("per_bench") or {}).items():
        for name, p in row["pairs"].items():
            e1, e2 = p["primary"]["estimate"], p["secondary"]["estimate"]
            f = (lambda e: "n/a" if e is None else "%+.1f [%+.1f, %+.1f] p=%.3g" % (
                100 * float(e["mean"]), 100 * float(e["ci95"][0]), 100 * float(e["ci95"][1]), float(e["p_t"])))
            print(chain, bench, name, "n", p["n"], "one-cell", p["items_reading_one_cell"], "tied",
                  p["items_tied_by_identical_requests"], "| primary", f(e1), "%d/%d" % (p["primary"]["better"], p["primary"]["worse"]),
                  "| secondary", f(e2), "%d/%d" % (p["secondary"]["better"], p["secondary"]["worse"]))
print("WROTE", OUT)
