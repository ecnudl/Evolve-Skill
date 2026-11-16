"""Training side only. For each procedure in each G/s3-zebralogic unit: on the items where THAT procedure delivered a
non-empty note, how many S' fixed / broke versus S. S is paired within the unit; a parent cell missing from a unit
(reused from an earlier unit with the same request) is taken from the earliest earlier unit of the same parent that has
it. The unit totals are checked against the unit's own verdict."""
import json, glob, collections
B = "/data/execskill-20261031-main-v5/G/s3-zebralogic/"
PARENT = "db55b5a2baa7e542d25b3ea2e8ddbceebb1ca4812029ecb93691df42f21c174f"
UNITS = ["train-r1", "train-r2", "confirm-r2", "train-r3", "confirm-r3", "train-r4"]
pool = {}
for u in UNITS:
    own_s, sp_rows = {}, []
    for f in glob.glob(B + u + "/attempt-1/trajectories/*.json"):
        d = json.load(open(f))
        if d["arm"] == "S":
            own_s[(d["package_sha256"], d["task_id"], d["run"])] = d.get("token")
        elif d["arm"] == "S'":
            notes = {n["id"]: len(n.get("delivered_text") or "") for n in (d.get("shell") or {}).get("notes") or []}
            sp_rows.append((d["task_id"], d["run"], d.get("token"), notes))
    def s_of(task, run):
        k = (PARENT, task, run)
        return own_s[k] if k in own_s else pool.get(k)
    tot_f = tot_b = 0
    for task, run, sp, notes in sp_rows:
        s = s_of(task, run); tot_f += (s == "fail" and sp == "pass"); tot_b += (s == "pass" and sp == "fail")
    v = json.load(open(B + u + "/unit.json"))["result"]
    vv = v.get("verdict") or v.get("confirm") or {}
    vf = len(vv["fixed"]) if isinstance(vv.get("fixed"), list) else vv.get("fixed")
    vb = len(vv["broken"]) if isinstance(vv.get("broken"), list) else vv.get("broken")
    procs = sorted({p for r in sp_rows for p in r[3]})
    out = []
    for p in procs:
        fx = br = n = 0
        for task, run, sp, notes in sp_rows:
            if notes.get(p, 0) <= 0:
                continue
            s = s_of(task, run); n += 1
            fx += (s == "fail" and sp == "pass"); br += (s == "pass" and sp == "fail")
        out.append("%s note_items=%d fixed=%d broken=%d" % (p, n, fx, br))
    print("%s totals %d/%d verdict %s/%s %s | %s" % (u, tot_f, tot_b, vf, vb, "OK" if (tot_f, tot_b) == (vf, vb) else "MISMATCH", " ; ".join(out)))
    for k, t in own_s.items():
        pool.setdefault(k, t)
