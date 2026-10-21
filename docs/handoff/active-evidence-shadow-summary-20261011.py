"""Zero-call reading of method-mode stages that carry the in-sample train panel (design memo
active-evidence-in-sample-shadow-design-20261011.md). Counts, actions and paired effects only; development data.

Per stage: the acting action (rule v2, fresh panel from the reserved pool), the in-sample shadow action (train
panel), the size-matched fresh action, and the paired candidate-minus-parent effect on both panels -- task level
(net wins / jointly known) and, for multi-task families, the equal-family mean of within-family differences. Then a
per-domain contingency count of (acting, shadow). No pooled interval across histories. The cell to look at first:
shadow keep while the reserved pool does not keep."""
import collections
import json
import os
import sys


def J(path):
    return json.load(open(path))


def effect(positions):
    """(wins, losses, jointly known, unknown, task-level net share, equal-family mean, families with a known pair)."""
    fam = collections.defaultdict(lambda: [0, 0])
    wins = losses = known = unknown = 0
    for p in positions:
        if p["pair"] not in ("win", "loss", "tie"):
            unknown += 1
            continue
        known += 1
        wins += p["pair"] == "win"
        losses += p["pair"] == "loss"
        cell = fam[p["family_id"]]
        cell[0] += 1
        cell[1] += (p["pair"] == "win") - (p["pair"] == "loss")
    family_mean = sum(net / n for n, net in fam.values()) / len(fam) if fam else float("nan")
    return wins, losses, known, unknown, (wins - losses) / known if known else float("nan"), family_mean, len(fam)


def main(stages):
    table = collections.defaultdict(collections.Counter)
    for stage in stages:
        L = stage.rstrip("/") + "/learning"
        name = stage.rstrip("/").split("fivebench-g-")[-1]
        if not os.path.exists(L + "/challenge/0/decision.json"):
            print(name, "| no sealed decision: nothing to read")
            continue
        decision = J(L + "/challenge/0/decision.json")
        benchmark = J(stage.rstrip("/") + "/stage.json")["benchmark"]
        shadow = decision.get("in_sample_shadow")
        print("%s | %s | acting %s (%s)" % (name, benchmark, decision["action"], decision["reason"]))
        # a stage without a candidate has a decision but no challenge outcome; one without the optional limit has no
        # shadow: both are reported as a missing comparison, never counted in the contingency table
        if shadow is None or not os.path.exists(L + "/challenge/0/outcome.json"):
            print("    no in-sample comparison in this stage (%s)" % (
                "no challenge outcome" if not os.path.exists(L + "/challenge/0/outcome.json") else "no train panel"))
            continue
        outcome = J(L + "/challenge/0/outcome.json")
        sets = collections.defaultdict(list)
        for p in outcome["positions"]:
            sets[p["set"]].append(p)
        rows = {}
        for label in ("fresh", "train_panel"):
            rows[label] = effect(sets[label])
            w, l, known, unknown, share, family_mean, families = rows[label]
            print("    %-12s w/l %2d/%2d  jointly known %3d  unknown %d  net/known %+.3f  equal-family mean %+.3f (%d families)"
                  % (label, w, l, known, unknown, share, family_mean, families))
        print("    train - fresh: task level %+.3f, equal-family %+.3f" % (
            rows["train_panel"][4] - rows["fresh"][4], rows["train_panel"][5] - rows["fresh"][5]))
        print("    shadow %s (%s) | size-matched fresh %s (%s) | one-sided family sign p: panel %.4f, fresh %.4f"
              % (shadow["action"], shadow["reason"], shadow["size_matched_fresh"]["action"],
                 shadow["size_matched_fresh"]["reason"], shadow["evidence"]["family_p_value"],
                 decision["inputs"]["fresh"]["family_p_value"]))
        print("    train panel by step status: %s | reused positions %d" % (
            {k: "%d/%d of %d" % (v["wins"], v["losses"], v["positions"]) for k, v in shadow["by_step_status"].items()},
            shadow["reused_positions"]))
        table[benchmark][(decision["action"], shadow["action"])] += 1
    for benchmark in sorted(table):
        print("%s (acting, shadow) counts: %s" % (benchmark, dict(table[benchmark])))
        flagged = sum(n for (acting, shade), n in table[benchmark].items() if shade == "keep" and acting != "keep")
        print("    shadow keep while the reserved pool does not keep: %d" % flagged)


if __name__ == "__main__":
    main(sys.argv[1:])
