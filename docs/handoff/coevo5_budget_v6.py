"""Zero-call cost planning for coevo5, registration v6 (§13), in GLM-5.3 tokens (prompt + completion).

Same accounting as ``coevo5_budget.py`` (v5), with the v6 method: no shared section; a rule may be placed at the
similar sections of its stage (§3, §5) when it does no worse than the parent on every similar target that can be
checked there -- a backward target's regression panel (solved by every full arm anyway), a forward target's generated
panel (§8); no control text solves a target panel. In the confirmation round a similar candidate is tested at both
placements. The research role checks and rewrites the proposed rules (step 5b, §7) and supplies source material for
the forward panels. Prints, per stage, the literal maximum schedule (cells and method-role calls) and two planning
scenarios, "expected" and "high-cost". Neither scenario is a maximum; the hard caps (§13) are enforced separately by
reservation.

    python docs/handoff/coevo5_budget_v6.py
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
MAX_RULES, MAX_SIMILAR, CONTROLS, PROBES, PROBE_RUNS = 5, 2, 4, 12, 2
# the similarity map (§1.1): per stage, the similar targets a rule can be checked on
FORWARD = {0: "officeqa", 1: "livemath"}  # generated panels in the style of a similar bench not yet learned
BACKWARD = {1: ("searchqa",), 2: ("officeqa",), 3: ("officeqa",)}  # regression panels of similar learned benches
QUESTIONS, CALLS_PER_QUESTION = 2, 8  # research per rule (step 5b): questions, model calls per question (§7)
GENERATION_CALLS, ITEMS_PER_CALL = 5, 3  # forward panel: generation calls per candidate, items requested per call


def similar_stage(k):
    return k in FORWARD or k in BACKWARD


SCENARIOS = {
    # Skill tokens per call (E chain, I chain), ALFWorld actions per episode, tokens per method-role call,
    # retry/re-execution overhead, and the share of the literal maximum schedule that is executed
    "expected": dict(skill={"E": 500, "I": 3300}, alf=15, method=5000, retry=1.05, full_arms=11, control_arms=8,
                     union=30, similar=1, method_calls=lambda t, k: int(1.5 * t) + 190 + (60 if k in FORWARD else 0)),
    "high-cost": dict(skill={"E": 2500, "I": 5000}, alf=25, method=8000, retry=1.15, full_arms=None, control_arms=None,
                      union=None, similar=MAX_SIMILAR, method_calls=None),  # None: the literal maximum
}


def literal(k):
    """The literal maximum schedule of stage k: cells (solver executions) and method-role calls (§4-§5, §7-§8)."""
    bench = ORDER[k]
    n, runs = GATE[bench]
    tn, truns = TRAIN[bench]
    half = math.ceil(n / 2)  # trigger items lie in the check half
    extra = MAX_SIMILAR if similar_stage(k) else 0  # a similar candidate: both placements, in both rounds
    full_arms = (1 + MAX_RULES + extra) + (1 + MAX_RULES + extra) + 2  # screen, confirm, composition
    groups = 2 if similar_stage(k) else 1  # control groups per round: the bench's section, the similar sections
    control_arms = 2 * groups * CONTROLS  # controls solve the trigger items only
    probes = 0
    if k in FORWARD:  # per round: the parent every candidate's panel, a similar arm its own
        probes = (2 * 2 * MAX_SIMILAR * PROBES + 2 * MAX_SIMILAR * PROBES) * PROBE_RUNS  # + composition
    judged = tn * truns if bench in EXAMINER else 0
    method = (judged + (40 + 8 if bench in EXAMINER else 0)  # judge every answer; second rubric on the panel; revision
              + tn * truns + 2 + MAX_RULES  # diagnosis of failed answers (at most all), analyst, leakage verdicts
              + MAX_RULES * (QUESTIONS * CALLS_PER_QUESTION + 1)  # research per rule, then its rewrite (step 5b)
              + (MAX_SIMILAR * GENERATION_CALLS * (1 + CALLS_PER_QUESTION + ITEMS_PER_CALL) if k in FORWARD else 0))
    return {"train": tn * truns, "full": full_arms * (n * runs + REGRESSION * k),
            "controls": control_arms * half * runs, "probes": probes, "method": method,
            "full_arms": full_arms, "control_arms": control_arms}


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
    if k not in FORWARD:
        probes = 0
    elif s["similar"] == MAX_SIMILAR:
        probes = lit["probes"]
    else:  # one similar candidate, screened and confirmed: the parent and its similar arm
        probes = 2 * (1 + 1) * PROBES * PROBE_RUNS
    method_calls = lit["method"] if s["method_calls"] is None else s["method_calls"](tn * truns, k)
    full_arms = lit["full_arms"] if s["full_arms"] is None else s["full_arms"]
    control_arms = (lit["control_arms"] if s["control_arms"] is None
                    else s["control_arms"] if similar_stage(k) else s["control_arms"] // 2)
    learning = (tn * truns * cell
                + full_arms * (n * runs * cell + regression_tokens(k, skill, alf))
                + control_arms * union * runs * cell
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
    calls = literal(k)["method"] if s["method_calls"] is None else s["method_calls"](tn * truns, k)
    return calls * s["method"] * s["retry"]


def main():
    print("Literal maximum schedule per stage (cells; ALFWorld cells are episodes of up to %d actions):"
          % ALF_MAX_ACTIONS)
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
                rows.append("%s %.1fM+%.1fM" % (bench, learning / 1e6, ev / 1e6))
                total += learning + ev
            print("%s-chain %-9s stage0 eval %.0fM | %s | total %.0fM"
                  % (chain, name, evaluation(chain, name) / 1e6, "; ".join(rows), total / 1e6))
    for name in SCENARIOS:
        per_stage = [method_only(k, name) for k in range(len(ORDER))]
        print("deepseek chain GLM roles %-9s %s | total %.0fM"
              % (name, " ".join("%.1fM" % (x / 1e6) for x in per_stage), sum(per_stage) / 1e6))


if __name__ == "__main__":
    main()
