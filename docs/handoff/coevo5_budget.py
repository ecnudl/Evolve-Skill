"""Zero-call cost planning for coevo5 (registration §13), in GLM-5.3 tokens (prompt + completion).

Prints, per stage: the literal maximum schedule in cells (what the protocol may execute at most) and two planning
scenarios, "expected" and "high-cost". Neither scenario is a maximum: an ALFWorld episode may run to 50 actions, a
20,000-byte Skill can exceed 5,000 tokenizer tokens, and calls may be retried. The hard caps (§13) are enforced
separately, by reserving a bounded allowance before every dispatch; finishing a chain within them is not guaranteed.

Per-call costs are historical GLM-5.3 figures (ledger; 10/6 test evaluation; 10/13-10/16 studies).

    python docs/handoff/coevo5_budget.py
"""
from __future__ import annotations

import math

ORDER = ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")
BASE = {"searchqa": 1100, "officeqa": 6000, "livemath": 4300, "spreadsheetbench": 1700}  # tokens per call, no Skill
ALF_BASE, ALF_MAX_ACTIONS = 750, 50  # tokens per ALFWorld action call without a Skill; the backend's action limit
TRAIN = {"searchqa": (200, 2), "officeqa": (74, 2), "livemath": (100, 2), "spreadsheetbench": (120, 1),
         "alfworld": (57, 2)}  # (items, runs) of the training execution
GATE = {"searchqa": (200, 2), "officeqa": (74, 2), "livemath": (100, 2), "spreadsheetbench": (120, 1),
        "alfworld": (57, 1)}  # (items, runs per arm) of the focal panel; SpreadsheetBench: before qualification
REGRESSION = 60  # items x 1 run per earlier bench, on every full arm
TEST = {"searchqa": 400, "officeqa": 172, "livemath": 125, "spreadsheetbench": 279, "alfworld": 134}
EXAMINER = set(ORDER[:4])  # no rubric judging/revision on ALFWorld
MAX_RULES, MAX_SHARED, CONTROLS, PROBES, PROBE_RUNS = 5, 2, 4, 6, 2

SCENARIOS = {
    # Skill tokens per call (E chain, I chain), ALFWorld actions per episode, tokens per method-role call,
    # retry/re-execution overhead, and the share of the literal maximum schedule that is executed
    "expected": dict(skill={"E": 500, "I": 3300}, alf=15, method=5000, retry=1.05, full_arms=10, control_arms=8,
                     union=30, shared=1, method_calls=lambda t: int(1.5 * t) + 150),
    "high-cost": dict(skill={"E": 2500, "I": 5000}, alf=25, method=8000, retry=1.15, full_arms=16, control_arms=16,
                      union=None, shared=MAX_SHARED, method_calls=None),
}


def literal(k):
    """The literal maximum schedule of stage k in cells (solver executions) and method-role calls (§4, §5, §8)."""
    bench = ORDER[k]
    n, runs = GATE[bench]
    tn, truns = TRAIN[bench]
    half = math.ceil(n / 2)  # trigger items lie in the check half
    full_arms = (1 + MAX_RULES + MAX_SHARED) + (1 + MAX_RULES) + 2  # screen, confirm, composition
    control_arms = 2 * 2 * CONTROLS  # bench-section and shared controls, in the screen and in the confirmation
    # probes: the parent solves every shared candidate's probes, a shared arm its own, the shared controls all of
    # them; the composition re-measures the parent and the composite on the shared members' probes
    per_round = (MAX_SHARED * PROBES) + MAX_SHARED * PROBES + CONTROLS * MAX_SHARED * PROBES
    probe_cells = (2 * per_round + 2 * MAX_SHARED * PROBES) * PROBE_RUNS
    judged = tn * truns if bench in EXAMINER else 0
    method = (judged + (40 + 8 if bench in EXAMINER else 0)  # judge every answer; second rubric on the panel; revision
              + tn * truns + 2 + MAX_RULES  # diagnosis of failed answers (at most all), analyst, leakage verdicts
              + MAX_SHARED * ((2 + PROBES) + (2 + PROBES * 8)))  # probe writing/checking; SearchQA-style research
    return {"train": tn * truns, "full": full_arms * (n * runs + REGRESSION * k), "controls": control_arms * half * runs,
            "probes": probe_cells, "method": method, "full_arms": full_arms, "control_arms": control_arms}


def per_cell(bench, skill, alf):
    return alf * (ALF_BASE + skill) if bench == "alfworld" else BASE[bench] + skill


def regression_tokens(k, skill, alf):
    return sum(REGRESSION * per_cell(b, skill, alf) for b in ORDER[:k])


def stage(k, chain, name):
    s, bench = SCENARIOS[name], ORDER[k]
    skill, alf = s["skill"][chain], s["alf"]
    n, runs = GATE[bench]
    tn, truns = TRAIN[bench]
    cell = per_cell(bench, skill, alf)
    lit = literal(k)
    union = math.ceil(n / 2) if s["union"] is None else min(s["union"], math.ceil(n / 2))
    probe_cell = max(per_cell(b, skill, alf) for b in ("searchqa", "officeqa", "livemath"))
    if s["shared"] == MAX_SHARED:
        probes = lit["probes"]
    else:  # one shared candidate, screened and confirmed: parent, its arm, four shared controls
        probes = 2 * (1 + 1 + CONTROLS) * PROBES * PROBE_RUNS
    method_calls = lit["method"] if s["method_calls"] is None else s["method_calls"](tn * truns)
    learning = (tn * truns * cell
                + s["full_arms"] * (n * runs * cell + regression_tokens(k, skill, alf))
                + s["control_arms"] * union * runs * cell
                + probes * probe_cell
                + method_calls * s["method"]) * s["retry"]
    return learning, evaluation(chain, name)


def evaluation(chain, name):
    s = SCENARIOS[name]
    return sum(TEST[b] * per_cell(b, s["skill"][chain], s["alf"]) for b in ORDER) * s["retry"]


def method_only(k, name):
    """GLM-5.3 method-role tokens of one stage of a deepseek chain (the solver runs on deepseek)."""
    s = SCENARIOS[name]
    tn, truns = TRAIN[ORDER[k]]
    calls = literal(k)["method"] if s["method_calls"] is None else s["method_calls"](tn * truns)
    return calls * s["method"] * s["retry"]


def main():
    print("Literal maximum schedule per stage (cells; ALFWorld cells are episodes of up to %d actions):" % ALF_MAX_ACTIONS)
    for k, bench in enumerate(ORDER):
        lit = literal(k)
        print("  %-16s train %4d | %2d full arms %6d | %2d control arms %5d | probes %3d | method calls %4d"
              % (bench, lit["train"], lit["full_arms"], lit["full"], lit["control_arms"], lit["controls"],
                 lit["probes"], lit["method"]))
    for chain in ("E", "I"):
        for name in SCENARIOS:
            rows, total = [], evaluation(chain, name)
            for k, bench in enumerate(ORDER):
                learning, ev = stage(k, chain, name)
                rows.append("%s %.0fM+%.0fM" % (bench, learning / 1e6, ev / 1e6))
                total += learning + ev
            print("%s-chain %-9s stage0 eval %.0fM | %s | total %.0fM"
                  % (chain, name, evaluation(chain, name) / 1e6, "; ".join(rows), total / 1e6))
    for name in SCENARIOS:
        per_stage = [method_only(k, name) for k in range(len(ORDER))]
        print("deepseek chain GLM roles %-9s %s | total %.0fM"
              % (name, " ".join("%.1fM" % (x / 1e6) for x in per_stage), sum(per_stage) / 1e6))


if __name__ == "__main__":
    main()
