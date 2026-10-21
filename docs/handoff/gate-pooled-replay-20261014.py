"""Zero-call replay over recorded two-pass gates (SkillOpt v9 / Rubric+Research v10 stage steps that carry a
confirmation pass; GEPA's gate records have another form and are not read): the frozen rule accepts when the FRESH
confirmation pass alone reaches p <= alpha/tries; a pooled rule would test both passes together (one-sided family
sign test over the two passes' discordant families) at the same threshold. A p-only counterfactual: the frozen
gate's other guards (coverage, task-level net wins) are not replayed. Lists every candidate that reached the
confirmation pass; the column "pos" is the number of selection POSITIONS (tasks), the signs are per family. Reads
result.json only; a begun stage without result.json is read from its step files."""
import glob, json, os
from math import comb

def p(w, l):
    n = w + l
    return 1.0 if n == 0 else sum(comb(n, k) for k in range(w, n + 1)) / 2 ** n

rows = []
for d in sorted(glob.glob("/root/fivebench-g-2026*")):
    if not os.path.isdir(d + "/learning"):
        continue
    steps = []
    rp = d + "/learning/result.json"
    if os.path.exists(rp):
        try:
            steps = json.load(open(rp)).get("steps") or []
        except Exception:
            continue
    else:
        for sp in sorted(glob.glob(d + "/learning/steps/*.json")):
            steps.append(json.load(open(sp)))
    for s in steps:
        fp = s.get("first_pass")
        if not isinstance(fp, dict) or "confirmation_rollout" not in s:
            continue
        # signs are counted per FAMILY, as the frozen gate counts them (one task per family except on KOR-Bench)
        w1, l1, w2, l2 = fp["families_improving"], fp["families_regressing"], s["families_improving"], s["families_regressing"]
        alpha = s.get("accept_alpha_effective")
        if alpha is None:
            continue
        rows.append((os.path.basename(d).replace("fivebench-g-", ""), s["step"], s.get("selection_positions"), w1, l1, p(w1, l1), w2, l2, p(w2, l2),
                     p(w1 + w2, l1 + l2), alpha, s.get("gate_action"), os.path.exists(rp)))
print("%-52s st pos  pass1     p1     pass2     p2     pooled-p  alpha   frozen               pooled" % "stage")
flips = 0
for name, step, n, w1, l1, p1, w2, l2, p2, pp, alpha, action, done in rows:
    pooled = "accept" if pp <= alpha and (w1 + w2) > (l1 + l2) else "reject"
    flip = (pooled == "accept") != (action == "accept_confirmed")
    flips += flip
    print("%-52s %d %4s %3d/%-3d %.4f  %3d/%-3d %.4f  %.5f  %.4f  %-20s %s%s%s" % (
        name[:52], step, n, w1, l1, p1, w2, l2, p2, pp, alpha, action, pooled, "  <-- differs" if flip else "", "" if done else "  (stage still running)"))
print("candidates that reached a confirmation pass:", len(rows), "| decisions that differ under the pooled rule:", flips)
