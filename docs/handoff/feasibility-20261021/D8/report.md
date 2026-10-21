# D8 — Statistical acceptance protocol for v5 (feasibility report, 2026-10-21)

Direction D8 of the v5 feasibility exploration. Author: a feasibility explorer subagent (workflow step), not a protocol
decision. Nothing here changes the frozen v3 protocol, its runs or its scores; everything proposed is for a new version
with its own output directory.

Labels used throughout: **[M] measured** (counted from recorded cells), **[E] estimated** (simulation, counterfactual
or formula on measured inputs; the model is stated), **[C] claim/proposal** (design judgement). Every rate is given with
its denominator. Points = percentage points of pass rate. "Items" = item-level pass-rate sums (an item at 4 runs
contributes 0, 0.25, ..., 1).

This report supersedes the 2026-10-20 19:12 draft (written on 82% of cal-1; preserved at
`run2/superseded/report-draft-20261020-1912.md`). Several of its numbers and two of its recommendations changed with the
complete data (Section 12).

---------------------------------------------------------------------------------------------------------------------

## 0. Verdict

**Feasibility: high for the protocol itself; it does not create statistical power the data do not have.**
Every component is a standard method (exact stratified test, Holm, non-binding futility, fixed-margin
non-inferiority, a positive/negative-control fixture with a control chart), implementable in about 200 lines on top of
the existing cell records, and was computed here on existing cells with no model calls except one 2,000-cell pilot.
Replays reproduce every frozen v3 verdict (17 judged rule arms) and cal-1's registered numbers.

What the numbers say (SearchQA unless stated; deepseek-v4-flash, temperature 0):
1. **The registered gate has no stated error level.** Its "gain >= 1 item" threshold false-passes a null rule 1.8%-6.9%
   depending on panel size [E], and 13.6%-17.3% in a measured split-half null at 2 runs without the placebo condition [M, pilot]; the exact test
   holds 0.5%-3.1% at nominal 5% in both. Its no-harm check (C2) lets a 10-point harm pass 38%-39% of the time on
   OfficeQA and LiveMath [E]. Its unknown convention turns outages into evidence against the rule (5% random unknowns
   cut a seed-sized rule's pass rate from 0.863 to 0.702) [E].
2. **The v5 design** (Section 4): exact stratified test on pooled screen + confirm data with Holm over the step's <= 5
   proposals, "gain >= 1 item" and "beats both kept placebos"; non-binding futility after two trigger runs; NI margins
   C2' 6 / 10 / 9 / 15 / 25 points and C3' 9 / 13 / 16 / 14 points (SearchQA / OfficeQA / LiveMath / SpreadsheetBench /
   ALFWorld); delta_min 4.8 / 5.7 / 9.0 / 6.3 / 10.0 points; unknowns by kind (infrastructure: pairwise exclusion;
   grader artifact: fail for both; truncation: scored). Estimated [E]: power for a seed-sized effect 0.637 vs 0.568
   registered at a family-wise error of 0.005-0.009 (0.683 and 0.014-0.024 without the placebo condition); futility
   would have saved about 50% of v3's rule-arm tokens (net -13.4M of 27.0M) and stopped none of the 3 arms that passed
   the registered C1.
3. **Honest limits.** A real rule-sized effect is not detectable per step: seed-rule (the seed's answer-form
   sentence as a 108-character rule; +0.3 to +0.4 points over 200 items) passes 0.19-0.26 of steps; per-rule no-harm can only screen gross harm (6-25 points);
   the project's 3-point margin is testable only at the version level (about 640 items x 4 runs per benchmark on
   SearchQA alone, or a macro test costing about 20.5M-72M real tokens per step, mostly ALFWorld).
4. **Pilot (ran; 2,000 cells, 2.93M tokens, 0 unknown) changed the fixture.** The planned positive control, a
   "spike" rule stating six reference answers, recovered its targets (22 / 24 runs vs 8 / 24; p = 3.9e-6) but also
   raised the 194 items it does not mention by +5.8 points [+2.0, +9.7] (all of it on items that had failed before:
   +16.5 points on 68 such items, 0.0 on 126 others), so it is not a known-effect standard. It also passes C1' and the
   C2' no-harm test, which shows that statistics cannot replace the leakage check. The task-card seed, in contrast,
   reproduced its effect in a second session (+9.50 vs +8.25 points, difference +1.25, se 1.96) and becomes the
   standing positive control (40-item panel, 2 runs, ~0.14M tokens per SearchQA round); the spike is kept only as a
   wiring check and a leakage canary.

Recommendation: adopt Sections 4.1-4.9 as a new protocol version (after one Codex review), budget the version-level
test explicitly, and report Z' and power next to every verdict. Do not expect the protocol to turn v3's zero accepted
rules into acceptances: it fixes the error accounting and saves tokens; detecting +1 to +3 point rules needs larger
version-level panels or larger effects (D1, D9).

---------------------------------------------------------------------------------------------------------------------

## 1. Data, denominators, provenance

| source | what | denominators | where |
|---|---|---|---|
| cal-1 (complete) | 11 arms (parent:A, parent:B, ids-full, seed-only, seed-rule, seed-rule3, cand, control:1-4) x 200 SearchQA training items x 4 runs, one interleaved round, 2026-10-20 | 8,800 main cells (6,008 pass / 2,777 fail / 15 unknown) + 400 pre-round cells (parent:A, 2 runs: 270/130) | old machine `/data/coevo5-20261020-cal1/cal1/searchqa/attempt-1,2` (read-only); flattened copy `run2/data/cal1_full_cells.json` |
| v3 run (training side only) | units train / prepare / screen / confirm / composite / merge of both chains (I-ds seeded, E-ds empty scaffold) | 14,178 cells; 17 judged rule arms (15 screen + 2 confirm verdicts) | new machine `/data/coevo5-20261019-v3-run` (read-only); `run2/data/v3_cells.json` |
| D8 pilot (this work) | one "standing-fixture" round: parent:C, spike6, seed-only on the same 200 items | 2,000 cells, complete (0 unknown, 4 truncated) | old machine `/data/feasibility-scratch/D8/run2/pilot`; `run2/pilot/` |

Provenance and exclusions [M]:
- No test/holdout pool, evaluation unit or file with final/test/holdout/reserve in its name or label was opened. The v3
  `selftest` units were skipped entirely because their name contains "test" (literal reading of the hard rule), so the
  reason why E-ds step 1's fifth supported rule (s1-r5) has no screen arm is **not established** here.
- The gate replays below reproduce the frozen verdicts exactly: C1 gain and C2 delta for all 17 judged v3 rule arms
  (`b9_worked_v3.py`), and cal-1's pre-registered A1-A3 numbers (`a2_reproduce.py`; e.g. ids-full +0.0938
  [0.0505, 0.1370], 48 up / 13 down / 139 tied; parent:B +0.0075, 22/18/160).
- The cal-1 "cand" arm is the E-ds step-1 rule s1-r1 (its 288-character text is contained in cand's 885-character
  text; checked against `arms-cal1-searchqa.json`).
- Unknown cells: cal-1 15 / 8,800 (0.17%), all `model_call_unavailable:http_503` after 3 sends, all in attempt-1,
  spread over 7 arms (max 3 per arm). The cal-1 dispatch log in `docs/handoff/cal1-registration-20261020.md` (line 129)
  says "21 unknown runs"; the cells, the pre-registered `analysis.json` and the frozen unit record's own summary
  (`unit.json`, unknown_runs per arm summing to 15) all show 15. The 16 cells present in both attempts had no verdict
  in attempt-1 (re-dispatched: 12 pass, 4 fail), so they are not unknown runs. The doc line conflicts with the frozen
  record and should be corrected by the main session (not edited here; `run3/v9_unknown_discrepancy.py`). Truncated replies (finish = length): 8 / 8,800, all scored fail (not unknown).
  v3: 18 / 14,178 extracted cells are `unknown_artifact`, all SpreadsheetBench grader outcomes
  (`general_formula_read_view_unverified`, `recalculation_changed_formula`, ...), i.e. produced by the reply content.
- Costs: "real" = provider-reported prompt + completion tokens; "ledger" = the frozen budget's charge, which charges a
  send's full reservation (~150k) when no usage is returned. cal-1 main round: real 14.00M, ledger 26.53M [M].

---------------------------------------------------------------------------------------------------------------------

## 2. Measured noise structure that the protocol must handle (SearchQA unless stated; deepseek-v4-flash, temperature 0)

### 2.1 Run noise of the same text [M]
parent:B - parent:A (byte-identical text, same round, 200 items): mean +0.0075. SD of per-item differences
0.319 at 1 run (average of 16 run pairings), 0.219 at 2 runs, 0.139 at 4 runs; discordant items 13% / 16.5% / 18%.
Same-text item-effect variance sigma_tau^2 = -0.008 [-0.016, +0.0001]: indistinguishable from pure run (Bernoulli)
noise. Temperature 0 does not make runs deterministic: two runs of the same item disagree with probability 0.117 on
average (parent; the mean over items of 2p(1-p)).

### 2.2 Text x item idiosyncrasy: different texts move items in both directions [M]
sigma_tau (spread of true per-item effects) for texts that differ from the parent: cand 0.269, ids-full 0.275,
seed-only 0.235, seed-rule 0.187, seed-rule3 0.184, placebos 0.118-0.201. The four placebo texts (rule-length,
irrelevant content) change the 200-item pass rate by -3.75, +3.38, -10.0 and 0.0 points (pairwise; SD across the
four 5.7 points). Any rule-sized text change therefore moves individual items both ways; a rule's net effect is a
small difference of large opposing moves.

### 2.3 Session effects on byte-identical requests [M]
The empty scaffold on the same 200 SearchQA items in five sessions (six measurements; cal-1's two parent copies share
one round): v3 E-ds train (10-20 00:07-00:18) 0.7425, v3 screen
parent 0.686, v3 confirm parent 0.700, cal-1 pre-round 0.675, cal-1 parent:A 0.681, parent:B 0.688. Paired against
cal-1 A+B pooled: the v3 train session +5.75 points [+1.9, +9.6] (44 items up, 15 down); the others +0.1, +1.5, -1.0.
Within cal-1, attempt-2 - attempt-1 +0.31 points (se 0.78, 1,195 arm-item pairs) and late - early +0.11 (se 0.63):
drift within one interleaved round is negligible. OfficeQA, I-ds parent on the same 60 regression items with identical
requests: 0.508 in one session (s3 screen; median completion 232 tokens, 6 truncations) vs 0.267, 0.267, 0.342 in three
others (median completion ~10 tokens); paired difference +24.2 points (se 5.8, 20 up / 2 down). Within that session
the rule arm moved identically (0.517, median 224 tokens), so the within-round comparison was protected. Returned model
always deepseek-v4-flash, reasoning_chars 0. The seeded I-ds text itself (same SHA in all three) scored 0.775 (v3
train), 0.778 (v3 screen, runs 0-1) and 0.774 (cal-1 ids-full), so its estimated effect over the scaffold depends on
which session's scaffold it is paired with: within cal-1 +8.87 points (se 2.2, vs parent:A+B); with the v3 screen-round
scaffold +9.00 (se 2.3); with the anomalous v3 training-session scaffold +3.25 (se 1.8).
Consequence [C]: every acceptance comparison must be within one interleaved round; cross-session comparisons of stored
results are not admissible evidence of an effect.

### 2.4 Effects are local and opposite inside and outside the trigger pool [M]
cal-1 pre-round eligibility pool (74 items with >= 1 failed parent run of 2) vs the other 126 items: cand (= v3 s1-r1)
+10.9 points (+8.1 items) vs -10.8 (-13.6 items); seed-only +20.5 vs +1.9; ids-full +25.8 vs -0.6; control:2 +5.4 vs
+2.2; control:3 -4.1 vs -13.5. A rule can pass a trigger-panel test and still be net harmful (cand: -2.75 points over
200 items pairwise; registered analysis -2.62); the no-harm test is not optional.

### 2.5 Dead items [M]
25 / 200 items pass in no arm and no run (0 / 44 runs each); all 25 lie inside the 74-item eligibility pool (34% of
it). In an exact stratified test they are non-informative strata (they cost runs but cannot bias the test).

### 2.6 Cost per cell, real usage [M]
SearchQA scaffold ~1,300 (cal-1 parent:A 1,302; v3 E-ds screen parent 1,247), seeded ~3,850; OfficeQA 4,570 / 8,200;
LiveMath 1,520 / 4,410; SpreadsheetBench 1,630 / 4,350; ALFWorld 28,500 (E-ds train) / 116,000 (I-ds screen parent).
v3 screen and confirm rounds cost 1.2M-7.4M real tokens each on QA/SpreadsheetBench and 38.9M on ALFWorld; the four
placebo arms were 6%-45% of a round (`b10`, per-unit table in `b10_out.json` and Section 8).

---------------------------------------------------------------------------------------------------------------------

## 3. Operating characteristics of the registered v3 gate under the measured noise

### 3.1 C1 (trigger gain >= 1 item and above the best of four placebos) [M] and [E]
- v3, all 17 judged rule arms [M]: C1 passed 3 (E-ds s1-r1 screen and confirm, I-ds s4-r2 screen); 14 failed on
  "gain < 1"; the placebo margin was never the sole blocker (0 / 17).
- Realized-panel resampling on cal-1 (2,000 panels of 11 items, measured 4-run cells) [M-based]: pool (ii) = 74
  pre-round eligible items: registered C1 passes ids-full 0.951, seed-only 0.865, cand 0.496, control:2 0.325,
  parent:B 0.007. Pool (i) = 27 items of the v3 check half: ids-full 0.746, seed-only 0.648, null 0.
- Fresh-run simulation [E] (per item a Beta posterior of each arm's pass probability from cal-1, new Bernoulli runs;
  one shared p0 for the two parent copies): the registered rule's null pass rate is **not tied to any stated level**;
  it depends on panel size and composition: pool (i) 1.8% / 3.4% / 6.9% at n = 6 / 11 / 20, pool (ii) 3.8% at n = 11
  and 3.0% at n = 20. A fixed 1-item threshold means a different test on every panel, because the null SD of the gain
  changes with the panel (0.55 / 0.79 / 0.98 items at n = 6 / 11 / 20 on pool (ii), `b14`). The exact stratified test
  of Section 4.2 holds its level by construction: 1.5% / 1.9% / 2.9% (pool i), 2.5% (pool ii, n = 11), 3.1% (pool ii,
  n = 20) at nominal 5%.

### 3.2 C2 (focal no-harm: sum_rest L(rule) - sum_rest H(parent) >= -t) [E from measured SDs]
The registered C2 is a threshold on a point estimate, not a test. Using the 17 judged v3 arms' rest panels (median SD
of per-item rule - parent differences; normal approximation):

| benchmark | judged rules | rest items (median) | s_d | SE (pt) | registered t: items / points | P(reject \| harmless) | P(reject \| -5 pt) | P(reject \| -10 pt) | implied NI margin at one-sided 5% (pt) |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| SearchQA (2 runs) | 8 | 186 | 0.271 | 1.99 | 7 / 3.76 | 0.029 | 0.733 | 0.999 | 7.0 |
| OfficeQA (2 runs) | 2 | 58 | 0.239 | 3.14 | 6 / 10.3 | 0.000 | 0.044 | 0.456 | 15.5 |
| LiveMath (2 runs) | 3 | 88 | 0.283 | 3.02 | 9 / 10.2 | 0.000 | 0.042 | 0.470 | 15.2 |
| SpreadsheetBench (1 run) | 3 | 73 | 0.419 | 4.91 | 9 / 12.3 | 0.006 | 0.068 | 0.318 | 20.4 |
| ALFWorld (1 run) | 1 | 35 | 0.494 | 8.34 | 5 / 14.3 | 0.043 | 0.133 | 0.304 | 28.0 |

Cross-check on SearchQA with cal-1 texts (bootstrap over a 192-item rest, 2 runs, 4,000 resamples) [M-based]: registered
C2 passes parent:B 0.999, control:4 0.934, seed-rule 0.948, cand 0.613, seed-rule3 0.462, control:1 0.273, control:3
0.000. Only SearchQA's C2 detects a 5-point harm with useful probability; on the other four benchmarks the registered C2
catches a 10-point harm 30%-47% of the time.

### 3.3 C3 (regression panels: 60 items, rule 1 run vs parent 2 runs) [E from measured SDs]
s_d from 9 / 7 / 4 / 1 v3 regression panels (SearchQA / OfficeQA / LiveMath / SpreadsheetBench): 0.202 / 0.277 /
0.358 / 0.307; SE 2.6 / 3.6 / 4.6 / 4.0 points. Registered tolerances 5 / 6 / 8 / 6 items (8.3 / 10 / 13.3 / 10
points): harmless false rejection 0.1% / 0.3% / 0.2% / 0.6%; detection of a 10-point regression 74% / 50% / 24% / 50%;
of a 15-point regression 99.5% / 92% / 64% / 90%. C3 is a gross-failure detector; it does not test the 3-point
version-level margin. Measured rule effects on v3 regression panels lay within about +-9 points.

### 3.4 Unknown-cell convention (L for the rule, H for the parent) [M] and [E]
On the complete cal-1 unit (0.17% unknown) the conventions agree within 0.3 points (seed-only: pairwise +8.75,
per-arm +8.83, L(rule)-H(parent) +8.62, L-L +8.87). Injected unknowns, n = 11 panels of pool (ii), seed-only as the
rule, 2,000 panels [E]:

| injected unknown share | registered C1 pass | mean registered gain (items) | exact test, pairwise exclusion | exact test fed L/H |
|---|---:|---:|---:|---:|
| none | 0.863 | +2.28 | 0.782 | 0.782 |
| 2% both arms (at random) | 0.807 | +2.02 | 0.777 | 0.696 |
| 5% both arms | 0.702 | +1.62 | 0.758 | 0.518 |
| 10% both arms | 0.495 | +0.91 | 0.712 | 0.255 |
| 5% rule arm only (outage) | 0.795 | +1.98 | 0.757 | 0.693 |
| 10% rule arm only | 0.746 | +1.78 | 0.760 | 0.629 |

The L/H convention turns infrastructure failures into evidence against the rule (at 5% random unknowns it removes
0.66 of the 2.28-item mean gain); pairwise exclusion keeps the gain unbiased (+2.29) and loses only the dropped runs.

### 3.5 Where v3's rule-arm tokens went [M]
Rule-arm real tokens over the 17 judged arms: 27.01M. Rest and regression cells of the 14 arms that failed C1: 18.29M
(68%) (screen: trigger 430 cells 6.00M, rest 3,229 cells 13.70M, regression 900 cells 3.25M; confirm: regression 180
cells 1.00M, rest 76 cells 0.34M). These cells could not change any verdict, because C1 had already failed.

---------------------------------------------------------------------------------------------------------------------

## 4. The v5 statistical acceptance protocol [C], with formulas

### 4.0 Principles
1. **Within-round only.** Every comparison is between arms dispatched interleaved in one round (same session), paired
   by item and run index. Stored results from another round are never a comparator (Section 2.3: +5.75 and +24.2-point
   session shifts on byte-identical requests).
2. **One test per question, with a stated level.** Benefit (C1') is an exact conditional test with a family-wise
   level; no-harm (C2', C3') is a non-inferiority (NI) test with a margin fixed before the run; transfer (C4') is
   reported with its interval and its stated power.
3. **The gate's family is the step.** Up to 5 rules per step (MAX_RULES) share one parent and one family-wise error
   budget (alpha = 0.05). Screen and confirm are two looks at the same hypotheses, not two independent filters.
4. **Calibrate every round.** A positive control of known direction (the task-card seed toggle), a negative control
   (a parent copy) and a wiring/leakage canary run inside every gate round (Section 4.8); a round whose controls fail
   is not allowed to produce verdicts.
5. **The fine no-harm margin (3 points) is a version-level claim.** Per-rule panels cannot resolve it (Section 4.4).

### 4.1 Notation
Items i of a panel; rounds r (screen = 1, confirm = 2); arm a in {R (rule), P (parent), N, S, placebos}; Y_{a,i,r,k} in
{1 pass, 0 fail, unknown}. r̄_{a,i,r} = mean of a's known runs of item i in round r. Per-item difference
d_{i,r} = r̄_{R,i,r} - r̄_{P,i,r}; pooled d_i = mean over the rounds in which i was measured. Gain in items
G = sum_i d_i. s_d = SD of the d_i, SE = s_d / sqrt(n).

### 4.2 C1' — benefit on the trigger panel: exact stratified conditional test
Strata s = (item, round). In stratum s the rule has k_R known runs with x_s passes, the parent k_P runs with y_s passes;
m_s = x_s + y_s, N_s = k_R + k_P (runs dropped pairwise when unknown, Section 4.7).

```
H0: within each round, the rule changes no trigger item's pass probability.
Under H0, conditional on m_s:   x_s ~ Hypergeometric(N_s, m_s, k_R),   independent over strata.
T = sum_s x_s ;   p = P_H0(T >= t_obs)    (exact: convolution of the stratum pmfs; strata with m_s in {0, N_s} carry no
                                            information and drop out)
E0 = sum_s k_R m_s / N_s ;   V0 = sum_s k_R k_P m_s (N_s - m_s) / (N_s^2 (N_s - 1)) ;   z_MH = (T - E0) / sqrt(V0)
```
This is the exact conditional form of the Cochran-Mantel-Haenszel test for 2 x 2 x K tables (Mantel & Haenszel 1959;
the exact version conditions on every stratum's margins, Agresti 2002, implemented as `mantelhaen.test(exact = TRUE)`;
Mehta, Patel & Gray 1985). It is valid at any panel size, needs no normal approximation (panels have 4-17 items, many
items at 0/4 or 4/4), and is conservative because the statistic is discrete. It answers a fixed-panel question ("does
the rule help on these items"), which is the right question for C1'; generalization is tested by C2'-C4' and at the
version level. Implementation: `run2/scripts/d8lib.py::cmh_exact` (about 30 lines); checked against brute-force
enumeration of all stratum outcomes on 300 random 2 x 2 x K cases (maximum difference 1.7e-15) [M].

**Decision C1'** (on the pooled screen + confirm strata of the rules that reach the final analysis):
```
C1' passes  <=>  Holm-adjusted p <= 0.05 over the step's m proposals        (family-wise level, Section 4.6)
            and  G >= 1 item  (pooled over rounds; MIN_GAIN, the minimum useful trigger effect)
            and  sum_i r̄_R,i > sum_i r̄_c,i for both kept placebos c      (rule beats generic text; secondary)
```
m counts every supported proposal of the step; a proposal stopped early or never judged enters Holm with p = 1.

### 4.3 Futility (non-binding) and C1-first sequencing
```
Look 1 (screen, after trigger runs 0-1 of R and P):     stop R if G_1 = sum_i (r̄_R,i - r̄_P,i) <= 0
Look 2 (end of screen, 4 trigger runs; rest measured):   stop R if G_2 <= 0, or if the rest estimate d̄_rest <= -delta_C2
Final (after confirm):                                    C1', C2', C3', C4' on pooled data
```
- Sequencing: dispatch the trigger cells of every arm first; the rest, regression and forward panels only for rules
  that pass look 1.
- Non-binding: the final level is computed as if the futility rules did not exist; stopping can only remove
  rejections, so the family-wise error stays <= alpha (Jennison & Turnbull 2000; Snapinn et al. 2006). Look 1 is the
  classic "stop if the observed effect is not in the favourable direction" rule applied before half information
  (Wieand, Schroeder & O'Fallon 1994); conditional-power rules (Lan, Simon & Halperin 1982) and the linear inefficacy
  boundary (Freidlin, Korn & Gray 2010) are the standard more elaborate alternatives and are not needed at these sizes.
- Measured effect on cost (counterfactual on v3's 17 judged arms, `b13`) [E]: look 1 would have stopped 10 / 17 arms,
  none of which passed the registered C1, and avoided 15.60M of the 27.01M rule-arm real tokens (58%; 3,451 cells).
- Measured effect on power (single round, n = 11 trigger items from pool (ii), final at 4 runs, 2,000 panels, `b6`)
  [E]: look 1 stops 58.5% of null rules, 66% of seed-rule3, 23.6% of cand, 8.0% of seed-only and 3.2% of ids-full;
  final passes lost to stopping <= 0.4 percentage points under the exact test (<= 2.2 under the registered rule). A
  stricter stop (interim p > 0.3) loses up to 7.5 points and is not recommended.
- Power cost of the two looks in the pooled two-round design (`b12b`, independent replicate, 3,000 steps of 5 rules)
  [E]: power for seed-only 0.690 with looks 1 + 2 vs 0.699 with no futility at all (seed-rule 0.259 vs 0.265), i.e.
  about 1 point; rest + regression passes per step 3.5-4.6 vs 10.0, rule-arm trigger cells per step 221-256 vs 440.

### 4.4 No-harm: non-inferiority with explicit margins (C2', C3', C4', version level)
**Test.** One-sided NI on the per-item differences (Schuirmann 1987's one-sided test; FDA 2016 guidance on NI trials):
```
H0: mean(d) <= -delta    vs    H1: mean(d) > -delta
pass  <=>  LB = d̄ - t_{1-alpha, n-1} * s_d / sqrt(n)  >  -delta,      alpha = 0.05 one-sided
```
**Margin rule.** The margin is fixed per benchmark before the run, from prior data, by a stated harmless-pass
requirement (a truly harmless rule, mean(d) = 0, passes with probability 1 - beta) **for the analysis actually used**,
i.e. the pooled screen + confirm differences:
```
delta = ceil( (z_{1-alpha} + z_{1-beta}) * SE_pooled,ref ),   SE_pooled = SE_one-round * sqrt((1 + rho) / 2)
C2' (one focal rest panel):                    beta = 0.05        ->  delta = 3.29 * SE_pooled
C3' (J earlier-benchmark panels, all must pass): beta = 0.05 / J  ->  J = 4: delta = 3.89 * SE_pooled
```
SE_one-round from the 17 judged v3 rule arms (Section 3.2-3.3); rho is the cross-round correlation of the same rule's
per-item rest differences, measured on the only two v3 rules with both rounds: 0.57 (E-ds s1-r1, 186 SearchQA items,
2 runs per round) and 0.30 (I-ds s4-r2, 73 SpreadsheetBench items, 1 run). The larger value is used for every benchmark:
it gives the larger pooled SE, hence the wider margin and a harmless pass of at least the stated 95%.
(A first version of this table used one-round SEs; that is wrong for a pooled final analysis and gave margins 1-3
points wider: 7 / 11 / 10 / 17 / 28 instead of 6 / 10 / 9 / 15 / 25.) A point threshold "sum >= -t" (the registered form) is the same kind of
test with delta_implied = t/n + z_{1-alpha} SE.

Whole-gate operating characteristics, registered (threshold must hold in screen AND confirm) vs v5 (one NI test on
pooled data), probability that the check is PASSED for a rule with true effect 0 / -3 / -5 / -10 / -15 points
(`b16`; bivariate normal round estimates with the measured SE and rho) [E]:

| check | benchmark | SE 1 round / pooled (pt) | registered threshold | **v5 delta** | pass at 0 (reg / v5) | -3 | -5 | -10 | -15 |
|---|---|---|---|---:|---|---|---|---|---|
| C2 | SearchQA | 1.99 / 1.76 | -7 items of 186 (3.8 pt) | **6** | 0.948 / 0.960 | 0.51 / 0.52 | 0.14 / 0.14 | 0.00 / 0.00 | 0 / 0 |
| C2 | OfficeQA | 3.14 / 2.78 | -6 of 58 (10.3 pt) | **10** | 0.999 / 0.973 | 0.98 / 0.80 | 0.92 / 0.55 | 0.39 / 0.05 | 0.02 / 0.00 |
| C2 | LiveMath | 3.02 / 2.68 | -9 of 88 (10.2 pt) | **9** | 0.999 / 0.956 | 0.99 / 0.72 | 0.93 / 0.43 | 0.38 / 0.02 | 0.02 / 0.00 |
| C2 | SpreadsheetBench | 4.91 / 4.35 | -9 of 73 (12.3 pt) | **15** | 0.989 / 0.963 | 0.95 / 0.86 | 0.89 / 0.74 | 0.55 / 0.30 | 0.16 / 0.05 |
| C2 | ALFWorld | 8.34 / 7.39 | -5 of 35 (14.3 pt) | **25** | 0.925 / 0.955 | 0.86 / 0.90 | 0.79 / 0.85 | 0.56 / 0.63 | 0.31 / 0.37 |
| C3 (J = 4) | SearchQA | 2.61 / 2.31 | -5 of 60 (8.3 pt) | **9** | 0.999 / 0.987 | 0.96 / 0.82 | 0.84 / 0.52 | 0.14 / 0.02 | 0.00 / 0.00 |
| C3 (J = 4) | OfficeQA | 3.58 / 3.17 | -6 of 60 (10 pt) | **13** | 0.995 / 0.992 | 0.96 / 0.93 | 0.87 / 0.80 | 0.35 / 0.23 | 0.03 / 0.01 |
| C3 (J = 4) | LiveMath | 4.62 / 4.09 | -8 of 60 (13.3 pt) | **16** | 0.996 / 0.987 | 0.98 / 0.93 | 0.94 / 0.85 | 0.65 / 0.42 | 0.22 / 0.08 |
| C3 (J = 4) | SpreadsheetBench | 3.97 / 3.52 | -6 of 60 (10 pt) | **14** | 0.989 / 0.990 | 0.93 / 0.93 | 0.83 / 0.81 | 0.35 / 0.30 | 0.04 / 0.03 |

With J = 1 earlier panel (stage 2) the C3' margins are 8 / 11 / 14 / 12 points (`b16_out.json`). Reading:
- SearchQA's registered C2 is already a sound NI test (v5 restates it as a 6-point margin; same behaviour).
- On OfficeQA and LiveMath the registered C2 passes a 10-point harm 38%-39% of the time; v5's margins (10 / 9) cut
  that to 2%-5% at the price of about 3%-4% harmless rejections.
- C3' is stricter than the registered C3 everywhere (a 10-point regression passes 2%-42% instead of 14%-65%).
- ALFWorld (35 rest items, 1 run) and, partly, SpreadsheetBench cannot be screened for harm below ~15-25 points by
  either design; v5 says so instead of implying protection. On ALFWorld v5's 25-point margin is slightly looser than
  the registered threshold (a 10-point harm passes 0.63 vs 0.56) because it is sized for a 95% harmless pass
  (registered: 0.925).
- Neither design stops a 3-point harm at the rule level on SearchQA (pass ~0.5 under both).

**What per-rule no-harm cannot do [E].** The standard fixed-margin method (FDA 2016: M1 = the active control's effect
at its lower confidence limit, M2 = the fraction of it that must be preserved) gives, with the cal-1 seed as the active
control (+8.87 points, 95% CI lower limit +5.1) and 50% preservation, delta = 2.6 points. A rule-level rest panel
supports that margin only with n = (3.29 x 0.271 / 0.026)^2 ~ 1,180 items at 2 runs; SearchQA's rest has 186. On
ALFWorld (35 rest items, 1 run) even a 10-point margin needs n = (3.29 x 0.494 / 0.10)^2 = 264 items, more than the
benchmark's 57 training items. Per-rule no-harm is therefore a gross-harm screen with the margins above, and the
3-point claim must be made on a version-level panel.

**Version level (the 3-point margin; D1's acceptance test, sized here) [E].** The composed step (all accepted rules
together) vs its parent, interleaved, 4 runs each, on items not used to propose the rules. Per-benchmark NI at 3 points
needs n = (3.29 x s_d / 0.03)^2: SearchQA (s_d at 4 runs 0.231 for rule-sized texts in cal-1) 642 items (508 at 90%
harmless pass). A macro NI test (mean of the five benchmark differences, the registered NI_MARGIN form) at 3 points on
the five focal training panels (200 / 74 / 100 / 120 / 57 items, 4 runs; s_d at 4 runs scaled from the measured 1- or
2-run values by the SearchQA ratio) has SE_macro ~ 1.13 points, harmless pass ~ 0.84 and detects a 3-point macro harm
with ~ 0.95. Cost ~ 20.5M real tokens for a scaffold parent and ~ 72M for a seeded one, 63% / 74% of it ALFWorld
(Section 8). The panel must exclude the items the rules were proposed on (D1's design question).

**C4' (similar-benchmark transfer) [E].** Forward panels of 8-12 items x 2 runs have SE ~ 8-10 points (s_d ~ 0.27-0.30
at 2 runs): the registered "sum >= 0" is close to a coin flip for a harmless rule. v5 reports the C4' estimate with its
95% interval and treats it as descriptive; a transfer claim needs a version-level panel.

### 4.5 Minimum useful effect delta_min per benchmark [E]
```
delta_min,b = max( 3 points  [registered NI_MARGIN: the smallest effect the project treats as material],
                   MDE80,b   [the smallest version effect the benchmark's test split resolves] )
MDE80,b = (z_0.95 + z_0.80) * s_d,b / sqrt(N_test,b) = 2.486 * s_d,b / sqrt(N_test,b)   (1 run, one-sided 5%)
```
s_d,b = SD of per-item text-vs-parent differences at 1 run (SearchQA: cal-1 texts; others: v3 focal rule-vs-parent).
N_test are the registered TEST_SIZES (arithmetic only; no test data was read).

| benchmark | s_d (1 run) | N_test | MDE80 one-sided (pt) | two-sided 95% (pt) | at 2 runs (pt) | **delta_min** | same effect in items of the focal training panel | text-perturbation RMS on v3 trigger unions (pt, effects) |
|---|---:|---:|---:|---:|---:|---:|---|---|
| SearchQA | 0.384 | 400 | 4.8 | 5.4 | 3.9 | **4.8** | 9.5 of 200 | 3.6 (16) |
| OfficeQA | 0.299 | 172 | 5.7 | 6.4 | 4.5 | **5.7** | 4.2 of 74 | 1.9 (4) |
| LiveMath | 0.405 | 125 | 9.0 | 10.1 | 6.7 | **9.0** | 9.0 of 100 | 14.1 (8) |
| SpreadsheetBench | 0.422 | 279 | 6.3 | 7.1 | - | **6.3** | 7.6 of 120 | 6.2 (12) |
| ALFWorld | 0.467 | 134 | 10.0 | 11.3 | - | **10.0** | 5.7 of 57 | 7.6 (4) |

Reading: a step (all its accepted rules together) is worth claiming on a benchmark only if its expected effect there is
>= delta_min; a single rule must show G >= 1 item on its trigger panel (C1'). On the 200-item SearchQA panel the four
placebo texts alone moved the score by -10.0 to +3.4 points (Section 2.2): an effect below ~5 points is inside the
range that content-free text produces, which is why the placebo comparison stays in C1'.

### 4.6 Multiplicity over <= 5 rules per step
Family = the step's supported proposals (m <= 5), one one-sided hypothesis per rule. Holm (1979) step-down on the final
pooled exact p-values: order p_(1) <= ... <= p_(m); reject H_(j) while p_(j) <= alpha / (m - j + 1); stop at the first
failure. Holm controls the family-wise error under any dependence (the rules share the parent's runs, so their
statistics are positively dependent); Benjamini-Hochberg (1995) controls the false discovery rate under independence or
positive regression dependence (Benjamini & Yekutieli 2001), which is plausible for one-sided tests against a shared
control but not proven for discrete exact tests. Because an accepted rule persists in every later text of the chain,
v5 uses family-wise control (Holm), not FDR.

Operating characteristics, fresh-run simulation on cal-1 pool (ii), n = 11 trigger items, 4 runs per round, 5 rules
per step, 3,000 steps per scenario (`b12`) [E]:

| design | FWER over null rules | power: seed-only | ids-full | seed-rule | cand | control:2 (a placebo) | rest+regression passes per step |
|---|---:|---:|---:|---:|---:|---:|---:|
| registered (C1 at screen and again at confirm, 4 placebos) | 0.004-0.008 | 0.568 | 0.729 | 0.127 | 0.274 | 0.096 | 5.15-5.93 |
| v5: looks 1-2 + pooled exact test + Holm + G >= 1 | 0.014-0.022 (replicate: 0.019-0.024) | **0.683** (replicate 0.690) | **0.824** | 0.255 (0.259) | 0.388 | 0.236 | 3.48-4.67 |
| v5 + "beats both kept placebos" | 0.005-0.009 | 0.637 | 0.792 | 0.186 | 0.332 | 0.162 | 3.48-4.67 |

Single-round alternatives (`b8`, `b11`, 4,000 steps): unadjusted 0.05 FWER 0.065-0.086 (power seed-only 0.65-0.66);
Holm in one round FWER 0.013-0.019 (power 0.47-0.49); BH q = 0.10 in one round FWER 0.035-0.073 (power 0.55-0.61);
screen 0.05 then confirm 0.05 FWER 0.001-0.004 (power 0.52-0.53). Pooling the two rounds is what buys the power; Holm
keeps the level. Every gain in power is also a gain for the placebo-like text control:2 (which genuinely raised cal-1's
pass rate: +3.4 points pairwise; registered analysis +3.6 [+0.6, +6.6], sign test p 0.003): a more sensitive test detects any real positive effect, so the placebo
comparison stays as the guard against "any text helps".

### 4.7 How undetermined (unknown) cells enter
Three kinds of non-answer, treated differently:

| kind | definition | measured frequency | v5 treatment |
|---|---|---|---|
| infrastructure unknown | no usable model reply after MAX_RESENDS (HTTP 5xx/429, transport, timeout) | cal-1 15 / 8,800 (0.17%, all HTTP 503); v3 0 | resend first (registered: 2 resends, 300 s cooldown); primary = **pairwise exclusion** of that (item, run) from both compared arms; an item with no remaining run leaves the comparison (registered shared_unanswered) |
| artifact unknown | a reply exists but the grader cannot verify it | v3 18 / 14,178, all SpreadsheetBench | primary = **fail for both arms** ("not verifiably solved", L vs L); it is caused by the reply, so it must not be excluded |
| truncation | finish = length | cal-1 8 / 8,800; graded fail | an answer, scored by the grader as is; counted and reported per arm |

Sensitivity and thresholds:
1. Direction rule (registered §12.6): a favourable verdict (C1' pass, C2'/C3' pass) must also hold under the
   unfavourable imputation (rule unknown = fail, parent unknown = pass); an unfavourable verdict must also hold under
   the favourable imputation. A verdict that flips is `undetermined:unknowns`.
2. Per arm and round: unknown share > 2% -> re-dispatch those cells before judging; > 10% -> `undetermined`
   (registered MAX_UNKNOWN_SHARE); rule vs parent imbalance (one-sided Fisher exact test on unknown counts, p < 0.01)
   -> treat the rule's unknowns as artifact unknowns.
3. Arithmetic of the registered L/H convention: one unknown trigger run at 4 runs moves 0.25 item off the rule and 0.25
   onto the parent (0.5 item against a 1-item threshold); at a 5% outage the mean gain of a seed-sized rule falls from
   2.28 to 1.62 items and its pass rate from 0.863 to 0.702 (Section 3.4).

### 4.8 Positive-control calibration as a standing fixture (revised after the pilot, Section 6)
**What.** Four fixture components in every gate round, scheduled exactly like rule arms (same session, interleaved):
- **N (negative control)**: the parent text dispatched as a second arm (byte-identical text, separate cells) on the
  trigger union. It must not pass C1'; when the optional 60-item rest sample is run (Section 8), it must also pass C2'.
- **P (positive control, standing)**: the benchmark's task-card seed toggled relative to the parent (added when the
  parent lacks it, removed when the parent has it), on a **40-item calibration panel** drawn once per step, with a
  seeded order, from the parent's training-round failures (items with >= 1 failed parent run of the step's train
  unit; no extra cells needed to define it), 2 runs, interleaved with the parent. Pass: one-sided exact stratified
  test (Section 4.2) p <= 0.05 in the expected direction. Measured basis [M]: on SearchQA the seed's effect over the
  scaffold was +8.25 (cal-1) and +9.50 (pilot) points at 2 runs over 200 items (difference +1.25, se 1.96), +18.9 /
  +24.3 points on the eligible items; a 40-item eligible panel at 2 runs rejected in 98.0% / 100% of resampled panels
  (realized cells, optimistic because the runs are not re-drawn). Its estimate also feeds the control chart.
- **W (wiring check and leakage canary)**: the spike rule (<= 600 characters stating the reference answers of K = 6
  items of the calibration panel; Section 6) run on those 6 items only, 4 runs, against the parent's 4 runs there.
  Pass: >= 75% of the target runs pass (measured 22 / 24 vs parent 8 / 24). In addition its text is fed to the
  leakage layer at zero solver cost and must be rejected (if it is not, the leakage layer is broken). W is a deliberate
  leak used only as a measurement standard: invisible to every role (analyst, examiner, researcher), never in a Skill,
  a prompt or a cache shared with them, never built from test or holdout items. W does **not** calibrate C1': its
  off-target effect was +5.8 points [+2.0, +9.7] on 194 non-targets (Section 6).
- **Two placebos** (text-perturbation controls, kept from v3's four) for C1's "beats generic text" condition.
- Constructibility: N and P work on every benchmark; W only where an answer is a short string (SearchQA, OfficeQA,
  LiveMath). SpreadsheetBench (answer is a file) and ALFWorld (multi-step actions) have no W; their rounds report
  "no wiring check".
- **Anchor / control chart (no extra cells)**: per benchmark and round, the parent's per-item pass rates on the focal
  panel are compared, paired by item, with the chain's reference measurement of the same text, and its median
  completion length with the reference median (Shewhart/Westgard-style rules, Westgard et al. 1981: flag a paired mean
  difference beyond +-3 paired SE, or a median completion length > 3 x the reference). With the measured same-text SD
  (0.219 at 2 runs, 200 items: 3 SE = 4.6 points) the E-ds s1 training session (+5.75 points) is flagged; the OfficeQA
  s3 session (+24.2 points, 3 SE = 17 points on 60 items; median completion 232 vs ~10 tokens) is flagged by both rules;
  the pilot's parent:C session (-1.87 points, 3 SE = 3.13) is not. Where the parent text changed (an accepted rule),
  the chart restarts from the new text's first round.

**Round status (decided before any rule verdict is read).**
| status | condition | consequence |
|---|---|---|
| calibrated | P detected, W passes (where it exists), N passes neither C1' nor fails C2' | verdicts stand |
| insensitive | P not detected | every rule rejection in the round becomes `undetermined:insensitive`; re-run with more runs or items |
| noisy | N passes C1' or fails C2' | acceptances in the round are void; re-run the round |
| broken | W fails to recover its targets, or the leakage layer accepts W's text | no verdicts; fix the harness (dispatch, scoring or leakage) |
| anomalous | control-chart flag | verdicts held; re-run in a fresh session |
| unreferenced | P never measured on this benchmark under this protocol version | verdicts stand, labelled unreferenced |

**How often.** N, W and the two placebos in every screen and confirm round on every benchmark with a rule under test
(the session effects of Section 2.3 mean a calibration does not carry over between sessions). P in every round on the
three QA benchmarks; on SpreadsheetBench and ALFWorld only in the periodic calibration (P costs 80 cells; ALFWorld cells
cost 28.5k-116k tokens). A full calibration of the cal-1 type (two parent copies, seed toggle, 4 runs on 200 items) per
benchmark when the solver route, model or protocol version changes -- in particular after v4's SearchQA format/scorer
fix, because the pilot's flips are mostly answer form (Section 6).

**Cost per round [E] (measured per-cell real usage x cells).** SearchQA with a scaffold parent: N 25 items x 4 runs =
100 cells (0.13M), P 80 cells (0.14M; the parent's cells on the panel are already part of the focal panel), W 24 + 24
cells (0.07M): about **0.34M per round** (a v3 screen or confirm round cost 1.2M-7.4M). Seeded parent: about 0.9M.
OfficeQA (N on 24 trigger items): 224 cells, 1.0M (scaffold) to 1.8M (seeded). LiveMath (N on 10 trigger items):
0.26M to 0.74M. SpreadsheetBench and ALFWorld: N only per round (0.05M-0.13M and 0.8M-3.3M: half the two-arm trigger-union
costs in Section 8). Replacing two of v3's four placebos by N and W makes the marginal cost about P alone.

**Assay quality (descriptive) [E].** Z' = 1 - 3 (sd_S + sd_N) / |mean_S - mean_N| (Zhang, Chung & Oldenburg 1999) on
the C1' gain, fresh runs, pool (ii), 4 runs: with the seed as positive control Z' = -2.95 / -1.91 / -1.05 / -0.69 /
-0.20 at n = 6 / 11 / 20 / 30 / 50 items (ids-full: -2.25 / -1.36 / -0.73 / -0.36 / 0.00). By the screening convention
(Z' > 0.5 excellent, 0-0.5 marginal, < 0 unsuitable for single-shot calls) a single round does not reliably separate
a seed-sized effect from noise at any trigger-panel size up to 50 items; the protocol must rely on replicated, pooled
tests (Section 4.6), and the paper should report Z' and power, not only nominal error rates.

### 4.9 What every round must log
Per arm: per-item passes per run, unknown and truncation counts by kind, real and ledger tokens, median completion
length. Per rule: G, T, E0, z_MH, exact p (round and pooled), Holm-adjusted p, futility look results, d̄_rest with its
one-sided 95% LB, C3' LBs, C4' estimate and interval, verdict per criterion. Per round: N, P and W results and the round
status, control-chart values. Per step: the Holm table and the version-level NI result.

---------------------------------------------------------------------------------------------------------------------

## 5. Worked example with real numbers: v3, E-ds chain, step 1 (SearchQA), replayed under v5 [M inputs, C rules]

Setting [M]: empty-scaffold parent; 5 supported proposals (s1-r1 ... s1-r5); s1-r1 to s1-r4 judged in the screen
(s1-r5 has no screen arm; Section 1). Screen: rule and parent 4 runs on each trigger item, 2 runs on the 200-item focal
panel; confirm (s1-r1 only, as registered) the same in a fresh round. No N/P/W fixture existed in v3, so under v5 this
round would be labelled `unreferenced` (no P, N or W arms); Section 6 shows what the fixture measures.

**Step A, look 1 (trigger runs 0-1).** Interim gains G_1: s1-r1 +1.5, s1-r2 -0.5, s1-r3 +1.0, s1-r4 0.0 items.
s1-r2 and s1-r4 stop (G_1 <= 0). Their remaining cells (trigger runs 2-3, rest, regression) are not sent:
0.56M + 0.52M = 1.08M real tokens avoided [E], of the 1.12M these two arms used in v3.

**Step B, end of screen (4 runs).** Per-item passes rule/parent on the trigger panel (4 runs each):

| rule | n | passes rule/parent per item | T | E0 | exact p | G (items) | registered screen verdict |
|---|---:|---|---:|---:|---:|---:|---|
| s1-r1 | 6 | 0/0 1/1 4/0 0/0 1/0 2/0 | 8 | 4.50 | 0.0077 | +1.75 | pass (gain 7/4, C2 -4) |
| s1-r3 | 11 | 4/0 0/1 0/0 0/0 0/0 0/1 0/0 0/1 2/0 0/0 0/0 | 6 | 4.50 | 0.224 | +0.75 | fail (gain 3/4 < 1) |
| (s1-r2, stopped) | 6 | 0/0 0/0 3/2 0/0 0/0 0/0 | 3 | 2.50 | 0.500 | +0.25 | fail |
| (s1-r4, stopped) | 7 | 0/0 0/0 0/0 0/0 4/4 0/0 0/0 | 0 | 0 | 1.000 | 0 | fail |

Look 2: s1-r1 (G +1.75, rest d̄ -2.15 > -6) and s1-r3 (G +0.75, rest d̄ -0.55) continue to confirm. Under the
registered gate only s1-r1 continued; under v5 s1-r3 costs one more confirm arm (about 0.6M real tokens, the size of its screen arm [E]).

**Step C, confirm and the pooled final analysis (s1-r1).** Confirm alone: T = 8, E0 = 4.00, p = 0.0005, G = +2.0.
Pooled over 12 strata (6 items x 2 rounds): T = 16, E0 = 8.50, z_MH = 4.30, exact p = 7.8e-6, pooled G = +1.88 items.
Holm over m = 5 (s1-r3's confirm is not in the v3 record; it enters with p = 1 for this illustration, as do the two
stopped rules and s1-r5): p_(1) = 7.8e-6 <= 0.05/5 = 0.01 -> reject H0 for s1-r1; p_(2) >= 0.224 > 0.0125 -> stop.
Placebos: s1-r1 beat all four placebos in both rounds (registered margins 7/4 and 3/2). **C1' passes.**

**C2' (rest = 186 focal items outside s1-r1's trigger and evidence items; 2 runs per round):**

| data | mean d̄ (pt) | SE (pt) | one-sided 95% LB (pt) | v5 (delta = 6) | registered (sum >= -7 items) |
|---|---:|---:|---:|---|---|
| screen | -2.15 | 2.47 | -6.23 | (not a decision; look 2 only checks d̄ > -6: continue) | pass (-4 items) |
| confirm | -4.03 | 2.35 | -7.91 | (not a decision) | **fail** (-7.5 items) |
| pooled screen + confirm | -3.09 | 2.13 | -6.62 | **fail** (LB < -6) | - |

Per-item rest differences correlate r = 0.57 between the two rounds (true per-item effects persist across sessions),
so pooling two rounds shrinks the SE by only ~12% (2.13 vs 2.41), not by the 29% that independent rounds would give.

**Outcome.** Both gates reject s1-r1, for different stated reasons: the registered gate because its confirm round
missed the C2 tolerance by 0.5 item; v5 because the pooled rest estimate cannot exclude a harm of 6.62 points (margin 6).
The verdict is borderline in both designs (with the one-round margin of 7 points that an earlier version of Section 4.4
used, v5 would have accepted it). An independent re-measurement exists: cal-1's "cand" arm is this rule, 4 runs on the
same 200 items in a third session [M]: trigger gain +0.50 items (exact p 0.32), rest mean -4.44 points (SE 2.37,
LB -8.35), all 200 items -2.75 points (SE 2.31, LB -6.57), and -10.8 points on the 126 items outside the eligibility
pool. Pooling all three rounds gives rest mean -3.54, LB -6.78 (fails a 6-point margin). Two conclusions:
1. Neither gate reliably rejects a ~3-point harm at the rule level: a rule with true rest effect -3 points passes the
   no-harm check with probability 0.51 (registered, both rounds) and 0.52 (v5 pooled) on SearchQA [E, `b16`]. This rule
   was rejected by both, but with about even odds.
2. The fine margin belongs to the version-level test: on cal-1's 200 items x 4 runs the LB is -6.57 points, well below
   -3 [M]. (Caveat [E]: at 200 items a harmless version would also fail a 3-point margin 64% of the time; the macro
   version-level panel of Section 4.4 is needed for a fair test.)

**Unknown arithmetic on a real case (I-ds step 4, SpreadsheetBench, s4-r2) [M].** Screen: one artifact unknown in the
rule arm on trigger item ...37456 run 0 (`general_formula_read_view_unverified`) and one in the parent on a rest item;
confirm: the rule arm again on item ...37456 (run 1): the same item under the same rule both times, i.e. caused by the
reply (artifact), not by the infrastructure. C1 gain: L/H +1.00, fail-for-both +1.00, pairwise exclusion +1.00 (screen);
+0.50 under all three (confirm). C2 rest (74 items): L/H -5.00, fail-for-both -4.00 (tolerance -9). Exact p 0.319
(screen), 0.500 (confirm). Registered: screen pass (gain 1), confirm fail (gain 1/2). v5: G_2 = +1.0 > 0, so the rule
continues to confirm, and the pooled exact test fails (p > 0.3); same final decision, reached for a stated reason.

---------------------------------------------------------------------------------------------------------------------

## 6. Pilot: one standing-fixture round on SearchQA (run 2026-10-21 on the old machine)

**Status [M]: ran to completion.** 2,000 / 2,000 cells (2026-10-21 00:05-02:07, old machine, 7,308 s), 0 unknown,
4 truncated (scored fail), 333 cells needed HTTP 429 resends (all eventually 200). Cost: 2,923,449 real tokens
(prompt + completion) for the round plus 9,242 for the 6-cell smoke = 2,932,691 ledger tokens (cap 4.5M; ledger = real,
because every send returned usage). Request bytes of parent:C and seed-only are identical to cal-1's parent:A and
seed-only for all 1,200 cells (request SHA-256 checked), so session is the only difference to cal-1.

**Design (pre-registered in `run2/pilot/d8_pilot.py::PLAN` before dispatch).** The same 200 SearchQA training items as
cal-1, one interleaved round: parent:C = the empty scaffold (byte-identical to cal-1 parent:A/B), 4 runs; spike6 =
scaffold + one 581-character rule that states the reference answers of K = 6 targets drawn in a seeded order from
cal-1's frozen pre-round eligibility pool (74 items with >= 1 failed parent run of 2), 4 runs; seed-only = scaffold +
the SearchQA task-card seed (byte-identical to cal-1 seed-only), 2 runs. Analyses P1-P5 as registered; everything
marked EXPLORATORY was added after the data were seen.

**Results [M] (pre-registered P1-P5; `run2/pilot/pilot_analysis.json`, `pilot_stdout.txt`).**

| check | result | reading |
|---|---|---|
| P1 recovery on the 6 targets | spike 22 / 24 target runs pass vs parent:C 8 / 24; per target spike 1.00, 1.00, 1.00, 1.00, 1.00, 0.50 vs parent 0.75, 0.00, 0.75, 0.25, 0.25, 0.00; net +3.50 items of the 4.00 recoverable; exact stratified p = 3.9e-6 | the instrument registers a targeted rule; telling the solver the answer still failed 2 of 4 runs on one target ("The 'Cyclone State'" -> Kansas) |
| P2 collateral on the 194 non-targets | **+5.80 points [+1.95, +9.65]**, 39 items up / 17 down (sd 0.272) | **the spike is not a clean known-effect control**: it moves items it does not mention |
| P3 registered C1 / exact test on panels of n items from the eligibility pool with m targets (2,000 panels each; realized cells) | with **m = 0 targets**: registered gain >= 1 passes 0.556 / 0.817 / 0.978 and the exact test p <= 0.05 passes 0.437 / 0.661 / 0.890 at n = 6 / 11 / 20; with m >= 3 targets both pass >= 0.94 | the spike "passes C1" on panels that contain none of its targets, because of P2 |
| P4 session drift, parent:C - cal-1 parent:A+B (200 items) | -1.87 points (se 1.04), 21 up / 31 down; parent:C 0.666 vs 0.684 | within the control chart's 3-SE band (3.13 points): not flagged; median completion 41 vs 41 tokens |
| P5 positive-control stability, seed-only - parent (runs 0-1) | pilot **+9.50 points (se 2.25)** vs cal-1 **+8.25 (se 2.12)**; difference +1.25 (se 1.96); per-item effects correlate r = 0.60 | the task-card seed reproduces its effect in a second session |

**EXPLORATORY analyses [M] (`run3/v5_pilot_extras.py`, `run3/v7_flip_texts.py`, `run3/v8_flip_counts.py`; stdout files beside them).**
- Where the spike's collateral effect sits: +16.5 points [+8.5, +24.6] on the 68 eligible non-targets (23 up / 5 down,
  +11.25 items) and exactly 0.00 [-3.7, +3.7] on the 126 items that never failed in the pre-round (16 up / 12 down).
  Of the spike's total +14.75 items over 200 (0.666 -> 0.740), 3.50 come from its targets and 11.25 (76%) from items it
  does not mention. The seed behaves the same way: +24.3 (pilot) and +18.9 (cal-1) points on the 74 eligible items,
  +0.8 and +2.0 on the other 126.
- What the collateral flips are: 79 (item, run) cells over 42 non-target items pass under spike6 and fail under
  parent:C on the same run. In 11 / 79 the parent replied with a JSON answer object (e.g. `{"answer": "pulp"}`,
  `{"answer": "Blackbeard"}`) that the exact-match scorer failed while the spike arm's reply passed. In the first
  cell of 12 flip items read by hand: JSON answer object 4; a longer or qualified name 3 (parent "Palazzo Pitti (Pitti
  Palace)", "Marcus Junius Brutus", "William Wordsworth" vs spike "Pitti Palace", "Brutus", "Wordsworth"); the
  entity inside a longer sentence 2; hedged between two answers 1 ("vicar or rector"); no difference visible in the
  reply's first 140 characters 2. The other flip cells were not classified. Reading [C]: on SearchQA the six "clue -> short answer" pairs act as few-shot demonstrations of the
  expected answer form; much of the measurable headroom of the empty scaffold is answer form, which v4's SearchQA
  format/scorer fix (Section 4 of the context file) may change -- the positive-control effect must be re-measured
  under v4/v5 before it is frozen.
- Demonstrations vs instruction [M, two within-round contrasts from different sessions]: the six clue -> answer
  pairs moved the 194 non-targets by +5.8 points, while the seed's own answer-form sentence as a 108-character rule
  (cal-1 seed-rule) moved the 200-item panel by +0.3 points (registered +0.37 [-3.1, +3.9]) and the full seed by +8.75.
  In this solver, examples carry the answer-form effect that a one-sentence instruction does not (relevant to D9/D13).
- The statistical gate cannot see leakage: the spike (a rule made of six reference answers) passes C1' on its targets
  (p = 3.9e-6) and passes the v5 C2' no-harm test on its 194 non-targets (one-sided 95% LB +2.57 points > -6; it even
  shows superiority, p = 0.002). Only the leakage layer stands between such a rule and the Skill.
- Seed control on a small calibration panel (realized-panel resampling of the measured 2-run cells, 2,000 panels; run
  noise is not re-drawn, so these are optimistic): n items drawn from the 74 eligible items, exact stratified test
  p <= 0.05: cal-1 session 0.708 / 0.886 / **0.980** at n = 20 / 30 / **40**; pilot session 0.943 / 0.997 / **1.000**.
- Split-half null inside the pilot (parent:C runs 0-1 vs runs 2-3 of the same text, eligibility-pool panels, 2,000
  each): the registered "gain >= 1 item" passes 0.136 / 0.167 / 0.173 at n = 6 / 11 / 20 (2 runs per side, no placebo
  condition); the exact test passes 0.005 / 0.018 / 0.005 at nominal 0.05. The fixed 1-item threshold is a different
  test at every panel size and run count; the exact test keeps its level.

**What the pilot changes in the protocol [C].**
1. The spike is demoted from "positive control" to two cheap integrity checks: a **wiring check** (it must recover its
   own targets: measured 22 / 24 runs) and a **leakage canary** (its text must be rejected by the leakage layer when
   fed to it; no solver call). It no longer calibrates C1'.
2. The standing **positive control is the task-card seed toggle** on a 40-item calibration panel at 2 runs (Section 4.8,
   revised): a known-direction, rule-like diffuse effect that reproduced across two sessions (+8.25 / +9.50 points)
   and that a 40-item panel detects in 98-100% of resampled panels.
3. Interim analyses on incomplete rounds must not use the L/H imputation for cells that were simply not yet returned:
   the 01:06 interim file of this pilot (904 of 2,000 cells, kept as `pilot_analysis_interim_904cells.json`) showed a
   spurious "spike gain -2.8 to -9.8 items" because missing spike runs were counted as fail and missing parent runs as
   pass. Not-yet-returned cells are missing, not unknown.

---------------------------------------------------------------------------------------------------------------------

## 7. Risks, limits, what is not established

1. **Simulation model [E].** Fresh-run operating characteristics draw each item's pass probability from a Beta
   posterior of its cal-1 runs and then independent Bernoulli runs. Correlated runs inside a round (batching, a session
   switch mid-round) would raise the real false-positive rate. The within-round evidence is reassuring (same-text
   sigma_tau^2 ~ 0; within-cal-1 drift +0.3 points, se 0.8), and the per-round N arm is the running empirical check.
2. **One solver, one route, one benchmark for most numbers.** Variance components, the eligibility pool and every
   power number are SearchQA / deepseek-v4-flash / temperature 0. The other benchmarks contribute only SDs from 1-8
   judged rules each (OfficeQA 2, ALFWorld 1): their margins are rough and should be re-estimated, then frozen, before
   a v5 run.
3. **Per-rule no-harm is weak by necessity.** With 35-186 rest items, a rule-level NI margin below 6 points
   (SearchQA) or 9-25 points (others) cannot be supported at 95% harmless pass. A ~3-point harmful rule passes the
   rule-level no-harm check on SearchQA with probability ~0.5 under either design (Section 4.4). The 3-point guarantee exists only if the version-level test is run
   and funded (~20-72M real tokens per step, mostly ALFWorld).
4. **The positive control is large and diffuse; the spike is not a known-effect standard.** The seed toggle (+8 to
   +10 points on SearchQA, two sessions) is far larger than any learned rule measured so far (+0.3 to +3 points), so
   "P detected" proves the round can see large effects, not that it can see a rule-sized one; realistic power for small
   rules comes only from the simulations, and exists only for SearchQA. The spike (W) moved non-target items by +5.8
   points in the pilot, so it checks wiring and leakage only. Both controls' effects are mostly answer form on SearchQA
   (Section 6): v4's format/scorer fix may shrink them, so they must be re-measured under v4/v5 before being frozen.
   For OfficeQA, LiveMath, SpreadsheetBench and ALFWorld no within-round seed-toggle measurement exists yet (the
   earlier line's "+10 to +20 points for any reasonable instruction" is a test-split result from another protocol).
   W's text contains reference answers of training items: invisible to every role, never in a Skill or shared cache,
   never built from test or holdout items.
5. **Pooling assumes a comparable effect across sessions.** Under H0 the stratified test stays valid whatever the
   session does, but the pooled effect size is an average over sessions; a session in an unusual mode (OfficeQA
   verbose replies) can make the average unrepresentative. The control chart flags such rounds; they are re-run, not
   pooled.
6. **Holm with p = 1 for stopped proposals is conservative**, and it costs power in steps with many weak proposals.
   The simulation says the pooled design still beats the registered one (seed-only power 0.683 vs 0.568), at a
   family-wise error of 0.014-0.022 instead of 0.004-0.008: v5 deliberately spends more of the 5% budget.
7. **More sensitive also means more placebo-like acceptances.** control:2 passes C1' with probability 0.236 under v5
   vs 0.096 registered (0.162 with the placebo requirement). This is a real positive effect of a content-free text in
   that session, not a false positive of the test; only replication across sessions, no-harm and transfer separate it
   from a useful rule.
8. **Record discrepancy (resolved against the frozen record):** the registration log says 21 unknown runs in cal-1;
   the cells, `analysis.json` and the frozen `unit.json` summary say 15 (Section 1). The log line needs a correction.
9. **Not established:** spike constructions for SpreadsheetBench and ALFWorld; the reason s1-r5 was not screened;
   whether session anomalies are frequent enough to make the control chart's re-runs costly.

---------------------------------------------------------------------------------------------------------------------

## 8. Cost estimate

| item | tokens (real usage) | status |
|---|---|---|
| fixture per round (revised, Section 4.8): N + W replacing 2 of 4 placebos, plus P | SearchQA ~0.34M (scaffold) / ~0.9M (seeded); OfficeQA 1.0M / 1.8M; LiveMath 0.26M / 0.74M; marginal cost about P alone (0.14M / 0.31M on SearchQA) | [E] from measured per-cell usage |
| two trigger-union arms per round (e.g. N plus one placebo) if added instead of replacing placebos (2 arms x trigger union x trigger runs) | SearchQA 0.25M (scaffold) / 0.77M (seeded); OfficeQA 0.88M / 1.57M; LiveMath 0.12M / 0.35M; SpreadsheetBench 0.10M / 0.26M; ALFWorld 1.59M / 6.51M | [E] from measured per-cell usage and v3 trigger unions (25 / 24 / 10 / 15 / 14 items) |
| N on a 60-item rest sample x 2 runs (C2' calibration, optional) | SearchQA 0.15M / 0.46M; OfficeQA 0.55M / 0.98M; LiveMath 0.18M / 0.53M | [E] |
| anchor / control chart | 0 (uses the parent's own cells) | [C] |
| futility look 1 + C1-first sequencing, v3 counterfactual | -15.6M of 27.0M rule-arm tokens (-58%); minus ~2.2M for the 3 extra confirm arms v5 would add (s1-r3, E-ds s2-r2, E-ds s4-r4) -> net ~ -13.4M (~-50%) | [E] |
| version-level macro NI (3 points), per step | ~20.5M (scaffold parent) / ~72M (seeded); ALFWorld 63% / 74% | [E] |
| periodic full calibration (cal-1 type, 4 arms x 200 SearchQA items x 4 runs) | ~5M (cal-1: 14.0M real for 11 arms) | [E] |
| this D8 work | pilot: 2,000 cells + 6 smoke cells = 2,932,691 ledger tokens (= real usage), 7,308 s; analysis and verification: no model calls | [M] |

Ledger caution [M]: the frozen budget charges a send's full reservation (~150k tokens) when the provider returns no
usage; in cal-1 this doubled the ledger relative to real usage (26.53M vs 14.00M). Caps for v5 runs must be set on the
ledger, not on real usage.

---------------------------------------------------------------------------------------------------------------------

## 9. Recommendation [C]

Adopt the following as a **new** protocol version (v5; new output directory; v3 records untouched):
1. **Within-round comparisons only**, paired by item and run; stored results from other rounds are never comparators.
2. **C1' = exact stratified (CMH-type) one-sided test on pooled screen + confirm strata, Holm at 0.05 over the step's
   proposals, plus G >= 1 item and "beats both kept placebos".** Estimated: power for a seed-sized effect 0.637 (0.683
   without the placebo condition) vs 0.568 registered, family-wise error 0.005-0.022.
3. **Non-binding futility:** look 1 after two trigger runs (stop if G <= 0), look 2 at the end of the screen; send
   rest/regression/forward cells only to look-1 survivors. Estimated saving ~50% of rule-arm tokens on v3's record.
4. **No-harm as NI tests on pooled data with pre-registered margins** (C2': 6 / 10 / 9 / 15 / 25 points for SearchQA /
   OfficeQA / LiveMath / SpreadsheetBench / ALFWorld; C3' at J = 4: 9 / 13 / 16 / 14 points), stated with their power;
   present per-rule no-harm as a gross-harm screen.
5. **A version-level macro NI test at 3 points per step** on items not used for proposing (D1), budgeted explicitly
   (ALFWorld dominates its cost); without it, no "no-harm" claim below the per-rule margins may be made.
6. **Standing fixture in every gate round (revised by the pilot):** N (parent copy) on the trigger union; P (the
   task-card seed toggle on a 40-item calibration panel of the parent's training failures, 2 runs; every round on the
   QA benchmarks, periodic on SpreadsheetBench/ALFWorld); W (six-answer spike on its own 6 items, 4 runs, as a wiring
   check, plus its text as a leakage canary; QA benchmarks only); two placebos; a pass-rate / completion-length
   control chart; the round-status rule. A full calibration per benchmark when the route, model or protocol changes
   (first after v4's SearchQA format/scorer fix).
7. **Unknowns by kind:** infrastructure -> pairwise exclusion (L/H direction rule as sensitivity); artifact -> fail for
   both arms; truncation -> scored answer. Re-dispatch above 2%, undetermined above 10%.
8. **delta_min** (4.8 / 5.7 / 9.0 / 6.3 / 10.0 points) as the smallest step effect worth claiming per benchmark.
9. Before adoption: one Codex review of this protocol (the owner's one-review-per-item rule), a spike-construction smoke
   on OfficeQA and LiveMath, and re-estimation (then freezing) of the non-SearchQA margins.

---------------------------------------------------------------------------------------------------------------------

## 10. References (bibliographic details verified by web search on 2026-10-21 unless marked)

- Agresti A. (2002). *Categorical Data Analysis*, 2nd ed. Wiley. (Exact conditional test for 2 x 2 x K tables; cited by
  R's `mantelhaen.test(exact = TRUE)` documentation, checked.)
- Benjamini Y., Hochberg Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple
  testing. *JRSS B* 57(1):289-300.
- Benjamini Y., Yekutieli D. (2001). The control of the false discovery rate in multiple testing under dependency.
  *Annals of Statistics* 29(4):1165-1188.
- Berger R.L. (1982). Multiparameter hypothesis testing and acceptance sampling. *Technometrics* 24(4):295-300
  (intersection-union tests: all criteria must pass).
- Card D., Henderson P., Khandelwal U., Jia R., Mahowald K., Jurafsky D. (2020). With little power comes great
  responsibility. *EMNLP 2020*, 9263-9274.
- Dror R., Baumer G., Shlomov S., Reichart R. (2018). The hitchhiker's guide to testing statistical significance in
  natural language processing. *ACL 2018*, 1383-1392.
- FDA (2016). *Non-Inferiority Clinical Trials to Establish Effectiveness. Guidance for Industry* (November 2016)
  (fixed-margin M1/M2 method; details of M1/M2 checked via secondary sources only).
- Freidlin B., Korn E.L., Gray R. (2010). A general inefficacy interim monitoring rule for randomized clinical trials.
  *Clinical Trials* 7(3):197-208.
- Holm S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*
  6(2):65-70.
- ICH E10 (2000; FDA guidance May 2001). *Choice of Control Group and Related Issues in Clinical Trials* (assay
  sensitivity of non-inferiority comparisons).
- Jennison C., Turnbull B.W. (2000). *Group Sequential Methods with Applications to Clinical Trials*. Chapman & Hall/CRC
  (non-binding futility boundaries).
- Lakens D., Scheel A.M., Isager P.M. (2018). Equivalence testing for psychological research: a tutorial. *Advances
  in Methods and Practices in Psychological Science* 1(2):259-269 (smallest effect size of interest).
- Lan K.K.G., Simon R., Halperin M. (1982). Stochastically curtailed tests in long-term clinical trials.
  *Communications in Statistics C: Sequential Analysis* 1(3):207-219.
- Madaan L. et al. (2024). Quantifying variance in evaluation benchmarks. arXiv:2406.10229.
- Mantel N., Haenszel W. (1959). Statistical aspects of the analysis of data from retrospective studies of disease.
  *JNCI* 22(4):719-748.
- Mehta C.R., Patel N.R., Gray R. (1985). Computing an exact confidence interval for the common odds ratio in several
  2 x 2 contingency tables. *JASA* 80:969-973.
- Miller E. (2024). Adding error bars to evals: a statistical approach to language model evaluations.
  arXiv:2411.00640.
- Schuirmann D.J. (1987). A comparison of the two one-sided tests procedure and the power approach for assessing the
  equivalence of average bioavailability. *J. Pharmacokinetics and Biopharmaceutics* 15(6):657-680.
- Snapinn S., Chen M.-G., Jiang Q., Koutsoukos T. (2006). Assessment of futility in clinical trials. *Pharmaceutical
  Statistics* 5(4):273-281.
- Westgard J.O., Barry P.L., Hunt M.R., Groth T. (1981). A multi-rule Shewhart chart for quality control in clinical
  chemistry. *Clinical Chemistry* 27:493-501.
- Wieand S., Schroeder G., O'Fallon J.R. (1994). Stopping when the experimental regimen does not appear to help.
  *Statistics in Medicine* 13:1453-1458 (half-information futility rule; checked via a protocol that cites it; page
  range not verified).
- Zhang J.-H., Chung T.D.Y., Oldenburg K.R. (1999). A simple statistical parameter for use in evaluation and validation
  of high throughput screening assays. *J. Biomolecular Screening* 4(2):67-73.

---------------------------------------------------------------------------------------------------------------------

## 11. Artifacts

Mac (scratchpad, `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D8/`):
- `report.md` (this file); `run2/superseded/report-draft-20261020-1912.md` (previous draft).
- `run2/scripts/d8lib.py` (exact stratified test, registered C1 replay, NI t-test, Holm, BH), `a1-a7*.py`, `b1-b16*.py`
  (every number above; outputs in `run2/data/b*_out.json`, `b2_stdout.txt`, `b12_stdout.txt`, `b12b_stdout.txt`,
  `b15_stdout.txt`; `s1r1.txt` is the text of rule E-ds s1-r1).
- `run2/scripts/extract_cal1.py`, `extract_v3.py`, `extract_officeqa_receipts.py` (read-only extraction; selftest
  units skipped by name).
- `run2/pilot/d8_pilot.py` (pre-registered PLAN and launcher), `run-d8-pilot.sh`, `extract_pilot.py`,
  `analyse_pilot.py`, `inspect_item.py` (prints one training item's field structure; no model call),
  `pilot_cells.json` (one row per pilot cell, complete: 2,000 rows), `pilot_analysis.json` (complete data),
  `pilot_analysis_interim_904cells.json` (superseded interim, kept), `pilot_stdout.txt`.
- `run3/` (this session's independent verification and exploratory pilot analyses): `v1_source_counts.py`,
  `v2_cal1_headlines.py`, `v3_worked_bruteforce.py`, `v4_worked_rest.py`, `v5_pilot_extras.py` (+ stdout),
  `v6_predictions.py`, `v7_flip_texts.py`, `v8_flip_counts.py` (+ stdout), `v9_unknown_discrepancy.py` (+ stdout),
  `report-before-run3-edits.md` (the report as left by the earlier pass), `edits/` (inserted sections).
Old machine: `/data/feasibility-scratch/D8/run2/` (pilot output root `pilot/`, ops `pilot-ops/`, cal-1 extraction).
New machine: `/data/feasibility/D8/run2/` (v3 extraction; copy of this report).

---------------------------------------------------------------------------------------------------------------------

## 12. What changed relative to the 2026-10-20 draft

- Complete cal-1 data: cand's 200-item effect is -2.75 points pairwise (registered L-L -2.62), not -4.2.
- Multiplicity: the draft recommended no Holm for C1 and BH for the screen-to-confirm step. The complete simulation
  shows that Holm on pooled screen + confirm data is both more powerful (0.683 vs 0.568 for a seed-sized effect) and
  level-controlled; the recommendation is now Holm on pooled data.
- No-harm: the draft kept the registered C2 thresholds; now they are restated as NI margins on pooled data (same
  behaviour on SearchQA, tighter on OfficeQA / LiveMath / SpreadsheetBench, slightly looser and explicitly weak on
  ALFWorld) with stated power, plus a C3' rule that splits the harmless-pass budget across panels.
- Unknowns: artifact unknowns (SpreadsheetBench) are now separated from infrastructure unknowns.
- (Earlier pass, superseded by the next bullet:) the fixture's positive control became a rule-sized spike-in, to be
  piloted (Section 6), with the seed control moved to the periodic calibration.
- The complete pilot (Section 6) overturned the spike-in positive control: it recovers its targets but moves the other
  failing items by +16.5 points, so it is now a wiring check and leakage canary; the standing positive control is the
  task-card seed toggle, which reproduced across two sessions. The interim pilot file (904 cells) was misleading
  because not-yet-returned cells were imputed as unknowns.

---------------------------------------------------------------------------------------------------------------------

## 13. Verification log (2026-10-21, second pass of this direction)

Independently recomputed in this pass with new code (not `d8lib.py`), all matching the report [M]:
- cal-1 verdict counts read directly from the 8,816 source cell files (8,800 distinct cells; 6,008 / 2,777 / 15) and
  the per-arm unknowns of the frozen `unit.json`; pairwise contrasts vs parent:A (cand -2.75, control:1..4 -3.75 /
  +3.38 / -10.00 / 0.00, parent:B +0.75, ids-full +9.17, seed-only +8.75, seed-rule +0.29, seed-rule3 -3.12 points);
  ids-full vs parent:A+B +8.87 (se 2.16); 25 dead items, all inside the 74-item eligibility pool; same-text SD 0.139
  at 4 runs, 36 discordant items.
- Worked example: brute-force enumeration of the exact conditional test on the recorded s1-r1 cells: screen
  T = 8, p = 0.00765; confirm T = 8, p = 0.00051; pooled T = 16, p = 7.75e-6, pooled gain +1.875 items; s1-r3
  p = 0.224. Rest panel (186 items): screen -2.15 (se 2.47; the earlier pass had 2.44), confirm -4.03 (se 2.35, LB
  -7.91), pooled -3.09 (se 2.13, LB -6.62), cross-round r = 0.570; frozen sums -4 and -15/2 items reproduced.
- Margin and delta_min arithmetic (Sections 4.4-4.5) and the sample sizes 1,176 / 264 / 642 recomputed from the
  stated SEs; protocol constants (MAX_RULES, TEST_SIZES, TRIGGER_RUNS, tolerances, MIN_GAIN, MAX_UNKNOWN_SHARE,
  MAX_RESENDS, NI_MARGIN) read from `skillopt/coevo5/protocol.py`.
- v3 replay: the earlier pass's `b9_out.json` C1 gains and C2 deltas compared with the frozen unit verdicts of all
  17 judged rule arms: 17 / 17 identical (statuses too: 2 pass, 15 fail at their round).
- Pilot: re-extracted from its own output root after completion; pre-registered analysis re-run on all 2,000 cells.
Not re-run in this pass (produced by the earlier pass's scripts `run2/scripts/b*.py`, outputs `run2/data/b*_out.json`;
all [E]): the fresh-run simulations behind the operating characteristics (Sections 3.1-3.4, 4.3, 4.6, Z'), of which
`b12b` is itself an independent replicate of `b12` (power 0.690 vs 0.683 for seed-only).
