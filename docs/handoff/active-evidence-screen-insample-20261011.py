"""Zero-call: in-sample (step rows, sealed screen records) versus held-out (study holdout / fresh panel) effect of the
NATIVE candidate against its parent, for every screened stage. The screen solved every step row under two parent
controls (a, b), the native candidate and one variant per edit. Counts only; development data."""
import glob, json, math, os, sys
def J(p): return json.load(open(p))
def sign1(a, b):
    n = a + b
    return 1.0 if n == 0 else sum(math.comb(n, i) for i in range(a, n + 1)) / 2 ** n
def paired(x, y, fams):
    w = l = k = 0; by = {}
    for a, b, f in zip(x, y, fams):
        if a not in ("pass", "fail") or b not in ("pass", "fail"): continue
        k += 1; d = (a == "pass") - (b == "pass"); w += d > 0; l += d < 0; by[f] = by.get(f, 0) + d
    up = sum(v > 0 for v in by.values()); dn = sum(v < 0 for v in by.values())
    return w, l, k, sign1(up, dn)
print("%-26s %-12s | in-sample cand-ctlA  cand-ctlB  (ctlA-ctlB noise) | held-out native-parent" % ("stage", "selection"))
for stage in sorted(glob.glob("/root/fivebench-g-20261011-*-active-*")):
    L = stage + "/learning"
    for out_path in sorted(glob.glob(L + "/screen/*/outcome.json")):
        o = J(out_path); rows = o["positions"]; fams = [r["family_id"] for r in rows]
        col = lambda i: [r["arms"][i]["status"] for r in rows]
        a = paired(col("candidate"), col("parent_a"), fams); b = paired(col("candidate"), col("parent_b"), fams)
        n = paired(col("parent_a"), col("parent_b"), fams)
        held = "-"
        chain = J(L + "/chain/0.json")
        m = chain.get("matched")
        if m and (m.get("references") or {}).get("comparisons"):
            pass
        try:
            refs = J(L + "/challenge/0/references.json"); out = J(L + "/challenge/0/outcome.json")
            fresh = [p for p in out["positions"] if p["set"] == "fresh"]
            par = {p["task_hash"]: p["reference"]["parent"]["status"] for p in refs["positions"]}
            h = paired([p["current"]["status"] for p in fresh], [par[p["task_hash"]] for p in fresh], [p["family_id"] for p in fresh])
            held = "%2d/%2d of %3d (%+.3f)" % (h[0], h[1], h[2], (h[0] - h[1]) / h[2])
        except FileNotFoundError:
            try:
                out = J(L + "/challenge/0/outcome.json")
                fresh = [p for p in out["positions"] if p["set"] == "fresh"]
                h = paired([p["candidate"]["status"] for p in fresh], [p["current"]["status"] for p in fresh], [p["family_id"] for p in fresh])
                held = "%2d/%2d of %3d (%+.3f) [selected Skill vs parent, fresh panel]" % (h[0], h[1], h[2], (h[0] - h[1]) / h[2])
            except FileNotFoundError:
                pass
        f = lambda t: "%2d/%2d (%+.3f, p %.3f)" % (t[0], t[1], (t[0] - t[1]) / t[2], t[3])
        print("%-26s %-12s | %s  %s  (%d/%d) | %s" % (os.path.basename(stage)[21:], o["selection"]["id"], f(a), f(b), n[0], n[1], held))
