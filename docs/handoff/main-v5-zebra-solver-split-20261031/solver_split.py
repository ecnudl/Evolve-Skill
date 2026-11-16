"""Training-side only. For each G/s3-zebralogic train/confirm unit: split the S-vs-S' item outcomes by whether the
exact solver delivered a note. S outcomes missing from a unit (cells reused from an earlier unit with the same parent)
are taken from the earlier unit's trajectories of the same parent package and item."""
import json, glob, collections
B = "/data/execskill-20261031-main-v5/G/s3-zebralogic/"
SOLVER = {"train-r1": "p-zebralogic-3-1", "train-r2": "p-zebralogic-3-3", "confirm-r2": "p-zebralogic-3-3",
          "train-r3": "p-zebralogic-3-6", "confirm-r3": "p-zebralogic-3-6", "train-r4": None}
S_POOL = collections.defaultdict(dict)  # (package, task, run) -> token, from every unit
UNITS = {}
for u in SOLVER:
    arms = collections.defaultdict(dict)
    for f in glob.glob(B + u + "/attempt-1/trajectories/*.json"):
        d = json.load(open(f))
        notes = {n["id"]: len(n.get("delivered_text") or "") for n in (d.get("shell") or {}).get("notes") or []}
        arms[(d["task_id"], d["run"])][d["arm"]] = (d.get("token"), notes, d["package_sha256"])
        if d["arm"] == "S":
            S_POOL[(d["package_sha256"], d["task_id"], d["run"])] = d.get("token")
    UNITS[u] = arms
PARENT = "db55b5a2baa7e542d25b3ea2e8ddbceebb1ca4812029ecb93691df42f21c174f"
for u, arms in UNITS.items():
    sol = SOLVER[u]
    c = collections.Counter(); missing = 0; n_sp = 0
    for (task, run), r in arms.items():
        if "S'" not in r:
            continue
        n_sp += 1
        sp_tok, notes, _ = r["S'"]
        s_tok = r["S"][0] if "S" in r else S_POOL.get((PARENT, task, run))
        if s_tok is None:
            missing += 1; continue
        grp = "solver_note" if (sol and notes.get(sol, 0) > 0) else "no_solver_note"
        c[(grp, s_tok, sp_tok)] += 1
    print("==", u, "S' cells", n_sp, "S missing", missing)
    for grp in ("solver_note", "no_solver_note"):
        sub = {k[1:]: v for k, v in c.items() if k[0] == grp}
        n = sum(sub.values())
        fx = sub.get(("fail", "pass"), 0); br = sub.get(("pass", "fail"), 0)
        sp_pass = sub.get(("pass", "pass"), 0) + fx; s_pass = sub.get(("pass", "pass"), 0) + br
        print("   %-15s n=%2d  S pass %2d  S' pass %2d  fixed %2d  broken %2d" % (grp, n, s_pass, sp_pass, fx, br))
