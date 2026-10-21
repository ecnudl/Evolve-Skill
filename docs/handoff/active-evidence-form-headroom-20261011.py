"""Zero-call: composition of failed SearchQA holdout answers by the scorer's own metrics. Counts only (development
holdout; host-side metrics, never fed to any model). Classes of an EM failure: `sub_em = 1` -- after normalization the
answer and a reference are substrings of one another IN EITHER DIRECTION (the answer contains the reference, or is
only a part of it), so this is not the same as a pure answer-form failure; partial token overlap (f1 > 0); no
overlap. Marginal counts per column: they do not identify which items changed."""
import collections, glob, json, sys
def J(p): return json.load(open(p))
for stage in sys.argv[1:]:
    L = stage.rstrip("/") + "/learning"
    name = stage.rstrip("/").split("fivebench-g-")[-1]
    by_hash = {}
    for f in glob.glob(L + "/evaluations/*.json"):
        e = J(f)
        by_hash[e["record_hash"]] = e["score"]
    out = J(L + "/challenge/0/outcome.json")
    cols = collections.defaultdict(collections.Counter)
    def add(col, h):
        s = by_hash.get(h)
        if s is None or s["status"] not in ("pass", "fail"):
            cols[col]["unknown"] += 1; return
        m = s.get("metrics") or {}
        if s["status"] == "pass": cols[col]["pass"] += 1
        elif m.get("sub_em") == 1: cols[col]["fail_substring_match"] += 1
        elif (m.get("f1") or 0) > 0: cols[col]["fail_partial_overlap"] += 1
        else: cols[col]["fail_no_overlap"] += 1
    for p in out["positions"]:
        if p["set"] != "fresh": continue
        add("pass/fail branch" if "matched" in J(L + "/chain/0.json") and J(L + "/chain/0.json")["matched"] else "parent(current)", p["current"]["evidence_hash"])
        add("diagnosis branch" if "matched" in J(L + "/chain/0.json") and J(L + "/chain/0.json")["matched"] else "candidate", p["candidate"]["evidence_hash"])
    try:
        refs = J(L + "/challenge/0/references.json")
        for p in refs["positions"]:
            for r, cell in p["reference"].items(): add("ref:" + r, cell["evidence_hash"])
    except FileNotFoundError:
        pass
    print(name)
    for col, c in cols.items():
        n = sum(c.values())
        print("   %-18s n=%3d pass %3d | fail: non-exact substring match %2d, partial overlap %2d, no overlap %2d | unknown %d" % (col, n, c["pass"], c["fail_substring_match"], c["fail_partial_overlap"], c["fail_no_overlap"], c["unknown"]))
