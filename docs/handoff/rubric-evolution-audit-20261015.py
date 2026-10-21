"""Zero-call audit (10/15, owner's question "why does the rubric barely change, why has (Deep)Research not been
exercised, why do candidates not pass the gate"): for every learning-v10 (Rubric+Research) stage, per step:
  - the rubric (verifier policy) record: planner status (investigate / no_update / insufficient_evidence), synthesis
    status, whether the policy hash changed, research arm, pages fetched, failure category;
  - calibration: authorized, detections / host-fail rows, false rejections / host-pass rows;
  - the gate: first pass (screen) wins/losses/families/p, confirmation if run, action;
  - the candidate's size against its parent.
Reads sealed learning records only (never test data). Usage: rubric_audit.py <stage dir> [...]"""
import json
import os
import sys


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def short(text, n=90):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def main(argv):
    for stage in argv:
        learning = os.path.join(stage, "learning")
        if not os.path.exists(os.path.join(learning, "result.json")):
            print("%s: no learning result" % os.path.basename(stage))
            continue
        result = read(os.path.join(learning, "result.json"))
        manifest = read(os.path.join(stage, "manifest.json"))
        print("=== %s | benchmark %s | status %s | accepted steps %s | parent bytes %d" % (
            os.path.basename(stage), manifest.get("benchmark"), result["status"], result.get("accepted_steps"),
            len(manifest["parent_skill"].encode("utf-8"))))
        steps = {s["step"]: s for s in result.get("steps", [])}
        verifier_root = os.path.join(learning, "verifier")
        for step in sorted(int(s) for s in os.listdir(verifier_root)) if os.path.isdir(verifier_root) else []:
            folder = os.path.join(verifier_root, str(step))
            policy = read(os.path.join(folder, "policy.json")) if os.path.exists(os.path.join(folder, "policy.json")) else None
            summary = read(os.path.join(folder, "summary.json")) if os.path.exists(os.path.join(folder, "summary.json")) else None
            if policy is not None:
                plan = [t for t in policy["trace"] if t.get("stage") == "plan" and "status" in t and "information_origin" in t]
                plan_status = plan[0]["status"] if plan else ([t.get("status") for t in policy["trace"]] or ["-"])[-1]
                fetched = [s for s in policy.get("sources", []) if s.get("status") == "available"]
                changed = policy["policy_hash"] != policy["parent_policy_hash"]
                print("  step %d rubric: arm %s | planner %s | result %s | changed %s | pages %d/%d | %s%s" % (
                    step, policy["arm"].replace("adaptive_", ""), plan_status, policy["status"], changed, len(fetched),
                    len(policy.get("sources", [])), short(policy.get("reason", ""), 80),
                    (" | failure %s" % policy["failure_category"]) if policy.get("failure_category") else ""))
                if changed:
                    print("         new mechanism: %s" % short(policy["policy"].get("mechanism", ""), 140))
            if summary is not None:
                print("         calibration: authorized %s | detections %s/%s | false rejections %s/%s" % (
                    summary.get("authorized"), summary.get("detections"), summary.get("host_fail_rows"),
                    summary.get("false_rejections"), summary.get("host_pass_rows")))
            s = steps.get(step)
            if s is not None:
                first = s.get("first_pass") or {}
                confirm = s.get("confirmation_pass") or {}
                print("         gate: screen %s/%s (families +%s/-%s, p=%s) | confirmation %s | action %s | candidate %s" % (
                    first.get("wins"), first.get("losses"), first.get("families_improving"), first.get("families_regressing"),
                    None if first.get("family_p_value") is None else round(first["family_p_value"], 4),
                    ("%s/%s (families +%s/-%s, p=%s)" % (confirm.get("wins"), confirm.get("losses"), confirm.get("families_improving"),
                                                         confirm.get("families_regressing"),
                                                         None if confirm.get("family_p_value") is None else round(confirm["family_p_value"], 4))) if confirm else "-",
                    s.get("gate_action"), "accepted" if s.get("accepted") else "not accepted"))


if __name__ == "__main__":
    main(sys.argv[1:])
