"""Zero-call audit: recompute screen selections and decision-v2 outcomes from the sealed per-position records with an
independent implementation (no package import) and compare with what the stage sealed. Counts only."""
import glob
import json
import math
import os
import sys


def J(p):
    return json.load(open(p))


def sign_one_sided(up, down):
    n = up + down
    return 1.0 if n == 0 else sum(math.comb(n, i) for i in range(up, n + 1)) / 2 ** n


def paired(a, b, fams):
    """a minus b on jointly known rows; family-level directions (one task per family here, but computed by family)."""
    wins = losses = known = 0
    by = {}
    for x, y, f in zip(a, b, fams):
        if x not in ("pass", "fail") or y not in ("pass", "fail"):
            continue
        known += 1
        wins += x == "pass" and y == "fail"
        losses += x == "fail" and y == "pass"
        by[f] = by.get(f, 0) + (x == "pass") - (y == "pass")
    up = sum(v > 0 for v in by.values()); down = sum(v < 0 for v in by.values())
    return wins, losses, known, up, down, sign_one_sided(up, down)


problems = 0
print("== SCREENS")
for stage in sorted(glob.glob("/root/fivebench-g-20261011-*-active-*")):
    L = stage + "/learning"
    for out_path in sorted(glob.glob(L + "/screen/*/outcome.json")):
        name = os.path.basename(stage)[21:]
        outcome = J(out_path); inv = J(os.path.dirname(out_path) + "/inventory.json")
        rows = outcome["positions"]; fams = [r["family_id"] for r in rows]
        scored = [a for a in inv["arms"] if a["disposition"] == "scored"]
        ids = [a["id"] for a in scored]
        notes = []
        if outcome["inventory_hash"] != inv["record_hash"]:
            notes.append("inventory hash mismatch")
        if os.path.getmtime(os.path.dirname(out_path) + "/inventory.json") > os.path.getmtime(out_path):
            notes.append("inventory written after outcome")
        if any(set(r["arms"]) != set(ids) for r in rows):
            notes.append("row without every scored arm")
        if inv["expected_metric_positions"] != len(ids) * len(rows):
            notes.append("expected positions mismatch")
        keys = sorted(a["rollout"] for a in inv["arms"])
        if len(set(keys)) != len(keys) or not all(2000 <= k < 12000 for k in keys):
            notes.append("rollout keys not distinct / out of range %s" % keys)
        blocks = inv["schedule"]["blocks"]
        covered = sorted(i for b in blocks for i in b["rows"])
        if covered != list(range(len(rows))) or any(sorted(b["arms"]) != sorted(ids) for b in blocks):
            notes.append("schedule does not cover every row x arm once")
        col = {i: [r["arms"][i]["status"] for r in rows] for i in ids}
        need = math.ceil(0.9 * len(rows))
        alpha = inv["alpha"]
        best = None
        for a in scored:
            if a["id"] in ("parent_a", "parent_b"):
                continue
            wa = paired(col[a["id"]], col["parent_a"], fams); wb = paired(col[a["id"]], col["parent_b"], fams)
            ok = all(w[0] - w[1] > 0 and w[5] <= alpha and w[2] >= need for w in (wa, wb))
            if ok:
                key = (-(wa[0] - wa[1] + wb[0] - wb[1]), a["skill_bytes"], a["skill_hash"])
                if best is None or key < best[0]:
                    best = (key, a["id"])
        mine = "parent" if best is None else best[1]
        sealed = outcome["selection"]["id"]
        if mine != sealed:
            notes.append("SELECTION DIFFERS: recomputed %s sealed %s" % (mine, sealed))
        problems += len(notes)
        print("%-34s rows %3d arms %2d blocks %2d selection %-10s recomputed %-10s %s" % (
            name, len(rows), len(ids), len(blocks), sealed, mine, "OK" if not notes else notes))
print("== DECISIONS (method mode)")
for stage in sorted(glob.glob("/root/fivebench-g-2026101[01]-*-active-*")):
    L = stage + "/learning"
    if not os.path.exists(L + "/challenge/0/decision.json") or not os.path.exists(stage + "/stage.json"):
        continue
    if J(stage + "/stage.json")["arms"]["post_update"] != "challenge_replay":
        continue
    name = os.path.basename(stage)[12:]
    d = J(L + "/challenge/0/decision.json"); o = J(L + "/challenge/0/outcome.json")
    notes = []
    res = {}
    for key in ("fresh", "replay"):
        pos = [p for p in o["positions"] if p["set"] == key]
        cand = [p["candidate"]["status"] for p in pos]; cur = [p["current"]["status"] for p in pos]
        fams = [p["family_id"] for p in pos]
        w, l, known, up, down, p_gain = paired(cand, cur, fams)
        p_harm = sign_one_sided(down, up)
        res[key] = (w, l, known, up, down, p_gain, p_harm, len(pos), cand, cur, fams)
    f = res["fresh"]; r = res["replay"]
    alpha = d["limits"]["alpha"]; need = d["limits"]["min_paired_known"]
    adverse = paired(["fail" if c not in ("pass", "fail") or u not in ("pass", "fail") else c for c, u in zip(f[8], f[9])],
                     ["pass" if c not in ("pass", "fail") or u not in ("pass", "fail") else u for c, u in zip(f[8], f[9])], f[10])
    if r[7] and r[6] <= alpha:
        mine = "revert"
    elif f[2] < need:
        mine = "park"
    elif f[6] <= alpha:
        mine = "revert"
    elif f[5] <= alpha and f[0] - f[1] > 0 and adverse[5] <= alpha:
        mine = "keep"
    else:
        mine = "park"
    s = o["summary"]["fresh"]
    if (s["wins"], s["losses"], s["jointly_known"]) != (f[0], f[1], f[2]) or abs(s["family_p_value"] - f[5]) > 1e-12:
        notes.append("fresh summary differs")
    if mine != d["action"]:
        notes.append("DECISION DIFFERS: recomputed %s sealed %s" % (mine, d["action"]))
    order = o["execution_order"]["halves"]["fresh"]
    if abs(len(order["parent_first"]) - len(order["candidate_first"])) > 1:
        notes.append("unbalanced order")
    problems += len(notes)
    print("%-36s fresh %2d/%-2d known %2d p %.2g harm p %.2g adverse p %.2g | replay %d/%d | sealed %-6s recomputed %-6s %s" % (
        name, f[0], f[1], f[2], f[5], f[6], adverse[5], r[0], r[1], d["action"], mine, "OK" if not notes else notes))
print("problems:", problems)
