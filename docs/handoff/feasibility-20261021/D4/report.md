# D4: Rules as classifiers (checkable "when" predicates). Feasibility report

Explorer D4, round 2 (work 2026-10-20 evening to 2026-10-21). This file replaces the first attempt's report. That
report is kept unchanged as `earlier_attempt1_report.md` in the same folder.

- **Data.** The completed v3 run `/data/coevo5-20261019-v3-run`, training paths only, and the frozen code
  `/data/coevo5-20261019-v3-source-f`.
- **Model calls.** GLM-5.3 only: 4,595 judge calls this round, 2,514,148 tokens. No solver (deepseek) calls.
- **Evidence labels.**
  - **[M]**: measured on the data in this work.
  - **[E]**: an estimate derived from measured quantities.
  - **[C]**: a claim from the shared context or the literature, not re-measured here.

## 0. Verdict

**Feasibility: low for what D4 promised.** A small instrumentation subset of it is cheap and worth keeping.

1. **Most rules can be given a checkable condition.** 38 of the 49 v3 proposals get a condition that can be
   evaluated before any solver call. Of these, 28 are judged by an LLM and 10 are exact task features. Of the rest,
   7 rules state no condition at all, 3 are observable only while the task is being solved, and 1 has no target
   code. [M]
2. **The GLM applicability judge is reliable enough for this use.**
   - Three identical votes are unanimous on 792/908 items (87.2%).
   - The 3-vote majority agrees with an independent reader on 160/180 items (88.9%), and on 143/156 (91.7%) of the
     items the reader marked as certain.
   - All 4,595 replies parsed. [M]
3. **The conditions do not do the classifying that D4 needs.**
   - Against the examiner's target codes, the median lift of the 27 judged conditions is 1.02, so their precision is
     at the base rate.
   - Only 4 of the 40 scorable conditions reach p < 0.05, and about 2 would be expected by chance.
   - All 4 are exact structural features, and two of them hold by definition: the "meta-option present" feature
     against the code "did not pick the meta-option". [M]
4. **The conditions do not kill dead items.**
   - They exclude 30/71 dead trigger items and 21/72 of the other trigger items (Fisher p = 0.12).
   - The filtered panel is still 41/92 dead (45%), against 71/143 (50%) before filtering.
   - The cheap "parent and one control fail every run" probe drops all 71 dead items, but it also drops 11 of the 22
     items where the rule beat the parent. [M]
5. **Rules do not act more where their condition holds.**
   - Rule-versus-parent movement is 98/505 (19.4%) in scope and 76/402 (18.9%) out of scope (stratified
     permutation p = 0.60).
   - The parent's own instability is 21.6% in scope and 22.1% out of scope.
   - A scope filter cannot concentrate a signal that is not there. [M]
6. **The v4 plan makes the panel bigger and less informative.** That plan sets the trigger panel to all in-scope
   check-half items.
   - The C1 panel grows 4.5x in items and 4.9x in solver cells, or about 2.7x in solver tokens, most of it ALFWorld.
     [M]/[E]
   - Informative items per 1,000 cells fall from 11.4 to 9.1. [M]
   - The probability that a rule with no effect passes the "gain >= 1 whole item" part of C1 rises from 0.26 to
     0.36. [M]
7. **What to keep and what to drop.**
   - Keep:
     - typed conditions;
     - a 3-vote judge whose unanimity rate serves as a vagueness detector;
     - a zero-solver-cost evidence-coverage check (20 of 38 conditions fail to cover all of their own rule's
       evidence items);
     - a per-rule scope-specificity diagnostic;
     - in-scope harm reporting.
   - Do not adopt the all-in-scope C1 panel with the fixed one-item threshold.
   - Handle dead items in the statistics (D8) and in the sampling (D1/D5), not with a classifier run before the
     solver.

## 1. What D4 claims and how each claim was tested

| D4 claim | test used here | result |
|---|---|---|
| every rule can carry a checkable "when" predicate | wrote one per proposal (49) and typed it | 38/49 checkable before any solver call |
| its precision/recall against the diagnosis codes is measurable before any solver call, and is informative | precision, recall, lift and an exact Fisher test on each stage's check half (48 rules) | measurable; mostly at the base rate |
| it kills dead items | dead and non-dead trigger items excluded by the predicate (15 screened rules) | no (p = 0.12); 45% of the filtered panel is still dead |
| it sizes the trigger panels so that they concentrate informative items | in-scope vs out-of-scope movement with controls; five panel designs with cost and null pass rate | no concentration; the v4 panel costs 4.9x the cells with a lower yield |
| (task) is an LLM applicability judge reliable? | 3 identical votes on 908 items; 180 independent labels; a writer swap | yes for clear conditions; who writes the condition matters more than judge noise |

## 2. Data and provenance

### v3 protocol facts used
Verified in the frozen `step.py` and `protocol.py`:

- **Training.** 200 items x 2 runs (SpreadsheetBench 1 run). The proposal and check halves are re-drawn each step.
  The examiner assigns a taxonomy code to each failed run.
- **Trigger set.** Check-half failed items with a code among the rule's codes; MIN_TRIGGER = 4.
- **Screen.**
  - Rule and parent run on the whole focal panel (proposal half + check half) at GATE_RUNS: SearchQA, OfficeQA and
    LiveMath 2; SpreadsheetBench and ALFWorld 1.
  - Trigger items run at TRIGGER_RUNS = {4, 4, 4, 2, 2}.
  - The four placebo controls run only on the union of the trigger items.

### What was read
All of it is training data:

- `/data/coevo5-20261019-v3-run/{I-ds,E-ds}/s*/prepare/unit.json`: 49 proposals, with texts, codes, evidence,
  trigger sets and statuses.
- `s*/selftest`: the text actually screened. Four rules had a revised plan text, and the judge used the screened
  text.
- `s*/train/attempt-1/cells`: training runs and examiner codes.
- `s*/screen` and `s*/confirm` cells: gate outcomes.
- The SpreadsheetBench input workbooks that training items reference, for answer-range fill and formula cells.

Nothing under `s*/evaluation/`, no test panel, and no file with a test or holdout-type name was opened.

**Check-half sizes:** SearchQA 99-100, OfficeQA 36-37, LiveMath 49, SpreadsheetBench 45, ALFWorld 28.

### Re-verified from the cells [M]
- **Proposals and gate results.** 49 proposals.
  - **15 screened rules.** The shared context's funnel says 14 screened, but its dead-item bullet says 15. The
    cells hold 15 screen arms and 2 confirm arms.
  - 2 rules passed the screen (I-ds s4-r2 and E-ds s1-r1), and 0 were confirmed.
- **Trigger sets.** 143 trigger items. For all 38 rules that reached a trigger computation, the v3 trigger set
  equals my recomputation from the codes.
- **Dead items.** 71 trigger items are dead, under the strict definition that every run of all six arms is a known
  fail.
  - The context counts 72.
  - The difference is spreadsheetbench/37456 under I-ds s4-r2. All its runs failed except one unknown cell.
- **Movement.** 41 trigger items have rule mean != parent mean at the trigger runs: 22 up and 19 down.

### Relation to the first attempt
The first attempt covered the same direction on 2026-10-20, 19:10-19:21. It made 529 GLM calls and used 276,852
tokens; both figures were re-verified from its JSON.

- **What it did.** It wrote regex/heuristic predicates and recommended a "parent + one control" probe for dropping
  dead items.
- **What this round adds.**
  - The conditions are rewritten as judged or mechanical predicates.
  - Movement is measured on the whole check half, not only on trigger items.
  - Parent-instability and other-arm controls are added.
  - Judge stability, writer sensitivity and evidence coverage are measured.
  - The probe recommendation is refuted (section 4.3).

## 3. Method

### 3.1 Conditions
I wrote one "when" condition for each of the 49 proposals, reading only the rule text and not its outcomes
(appendix C). The condition types are:

- **judged (28).** A semantic condition on the task as the solver sees it.
  - 5 of these narrow a rule whose literal text applies to every task: I-ds s1-r4, E-ds s1-r1, E-ds s1-r5,
    E-ds s2-r1 and E-ds s4-r5.
  - For those 5, the literal "always" reading is also scored.
- **mechanical (10).** An exact feature computed from the task, with no model:
  - two or more bulletin editions in the OfficeQA context;
  - a chart or graph mentioned;
  - the meta-option among the LiveMath choices;
  - an example-like sheet name or a partly filled answer range;
  - formula cells in the workbook;
  - an answer range of two or more cells;
  - openable receptacles in the ALFWorld room;
  - a clean, heat or cool task type.
- **always (7).** The rule states no condition.
- **runtime (3).** For example, "the environment answered 'Nothing happens'". This is computed after the fact from
  the parent's training traces, so it cannot select items before a run.
- **none (1).** I-ds s3-r3 has no target code.

A SpreadsheetBench detail: the answer range is already pre-filled in 65 of 91 input workbooks, 51 partly and 14
fully [M]. "Examples available" is therefore defined as an example-like sheet name OR a partly filled answer range.

### 3.2 Applicability judge
- **Model.** GLM-5.3 through `scripts.weak_solver_probe.Client` (thinking on, reasoning effort low, temperature 0,
  max_tokens 4096).
- **System prompt.** The judge decides whether the condition holds for one task, judging from the task as the
  solver sees it and never from the reference answer. It must not solve the task. It must "first reason briefly,
  then decide" and reply with one JSON object `{"reason": ..., "applies": true|false}`.
- **User message.** A one-line benchmark description, the screened rule text, the condition, and the task fields:
  - SearchQA and OfficeQA: the question;
  - LiveMath: the question and the choices;
  - SpreadsheetBench: the instruction, the answer position and the sheet names;
  - ALFWorld: the goal.
- **Coverage.** Each stage's whole check half.
  - The 13 screened judged conditions got 3 identical votes each (908 items).
  - The other 15 judged conditions got 1 vote.
  - The label is the majority vote. The parse rate was 4,595/4,595.

### 3.3 Outcomes
- **Data per item.** From the screen and confirm cells: the rule arm's and the parent's verdicts per run. For
  trigger items, all six arms.
- **Movement.** mean(rule) - mean(parent) over runs 0..GATE_RUNS-1. These are the runs both arms have on every
  focal item.
- **Mover.** An item whose movement is not 0.
- **Dead.** All six arms failed every run. This is known for trigger items only, because the controls never ran on
  other items.

### 3.4 Statistics
- **tpos.** Check-half items with at least one failed run coded with a target code. This equals the v3 trigger set.
- **Classifier measures.**
  - precision = |match and tpos| / |match|;
  - recall = |match and tpos| / |tpos|;
  - base = |tpos| / |check half|;
  - lift = precision / base.
- **Fisher test.** Exact and two-sided, computed with math.comb because there is no scipy on the remote machine.
- **In vs out of scope.** A stratified permutation of the scope labels within each rule: 20,000 permutations,
  seed 7.
- **Agreement.** Raw agreement, Cohen kappa (two raters) and Fleiss kappa (three votes).
- **Null pass probability.** For each rule and design:
  - every observed nonzero movement keeps its size and gets a random sign, which encodes the exchangeability of
    rule and parent under no effect;
  - 20,000 draws;
  - the statistic is P(net >= 1 item).

## 4. Results

### 4.1 Which rules can carry a checkable condition [M]
- **Overall.** 38/49 can be checked before any solver call: 28 judged and 10 mechanical. Of the rest, 7 are
  always, 3 are runtime, and 1 has no target code.
- **Rules with no condition.** Read literally, 12/49 rules (24%) state no condition: the 7 always rules plus the 5
  I narrowed.
- **The 15 screened rules.** 13 judged, 2 always (E-ds s1-r2 and I-ds s5-r1), and none mechanical.
- **Conditions drafted by GLM.** In the first attempt (49 calls, 29,677 tokens), GLM classified the rules as 32
  task-observable, 14 unconditional and 3 runtime. 5 of its replies were malformed JSON and were salvaged.
- **Near-universal conditions are "always" in disguise.** They hold on almost every check-half item:

  | rule | items where the condition holds |
  |---|---|
  | E-ds s3-r2 | 48/49 |
  | E-ds s3-r3 | 48/49 |
  | E-ds s2-r1 | 36/37 |
  | E-ds s2-r4 | 34/37 |
  | I-ds s5-r5 | 27/28 |
  | I-ds s3-r2 | 42/49 |

### 4.2 Precision and recall against the target codes [M]
Appendix A has all 53 rows: 48 primary rows and 5 literal-always rows.

- **Lift.** Of the 40 non-trivial rows with at least one target-code item:
  - 11 have lift >= 1.5, 10 of them with recall >= 0.5;
  - 14 have lift < 1;
  - 2 have lift = 0.
- **Coverage of the check half.** A non-trivial condition matches a median 57% of its check half; for the screened
  rules the median is 62%.
- **Judged conditions.** The 27 judged rows with codes have a median lift of 1.02.
- **Significant rows.** Fisher p < 0.05 for 4 of the 40 rows, against about 2 expected by chance:

| rule | condition (type) | match | precision | recall | base | p |
|---|---|---|---|---|---|---|
| I-ds s3-r1 | meta-option among the choices (mechanical) | 23/49 | 0.96 | 1.00 | 0.45 | < 0.001 |
| E-ds s3-r1 | meta-option among the choices (mechanical) | 22/49 | 0.95 | 1.00 | 0.43 | < 0.001 |
| I-ds s2-r2 | two or more bulletin editions in the context (mechanical) | 19/36 | 0.37 | 0.88 | 0.22 | 0.044 |
| E-ds s5-r4 | clean/heat/cool task type (mechanical) | 15/28 | 0.33 | 1.00 | 0.18 | 0.044 |

- **The two LiveMath rows hold by definition.** Code D1, "did not pick the meta-option", can only occur when the
  meta-option is offered. Both rules were dropped by the leakage layer and never screened. The feature is still
  useful: it is an exact, structural condition of the kind D7 needs.
- **The screened judged conditions sit at the base rate.**
  - I-ds s1-r1 (answer is a person): matched 26/100, precision 0.12 against base 0.11.
  - I-ds s4-r2 (matching by key): 0.32 against 0.33.
  - E-ds s4-r4 (per-row result): 0.33 against 0.33.
  - E-ds s1-r3 (slot or title): 0.04 against 0.11.
- **Interpretation.** The codes describe how the solver failed (answer not minimal, did not verify, wrong period,
  and so on). The task features a rule names are nearly independent of that. The codes are also per-run
  diagnoses, with their own noise, which is not measured here.

### 4.3 Dead trigger items [M]
The 15 screened rules have 143 trigger items: 71 dead (49.7%), 22 where the rule is above the parent (up), 19
below (down), and 31 ties (not dead, rule mean = parent mean). Outcomes are at the trigger runs.

The training pattern against the gate outcome:

| training pattern | items | dead | up | down | tie |
|---|---|---|---|---|---|
| failed both training runs (FF) | 94 | 58 | 14 | 11 | 11 |
| passed one of two training runs (PF) | 19 | 2 | 4 | 5 | 8 |
| SpreadsheetBench, single failed run (F) | 30 | 11 | 4 | 3 | 12 |

- **The training pattern does not solve it either.** FF predicts deadness (58/94 against 2/19 for PF, Fisher
  p < 0.001), but it also contains 14 of the 22 up items.
- **The conditions barely discriminate.**
  - The primary conditions exclude 30/71 dead items and 21/72 others (Fisher p = 0.12).
  - The first attempt's regexes: 25/71 against 17/72 (p = 0.145).
  - The conditions keep 28/41 of the items that are discordant at the trigger runs, and 16/22 of the up items.
  - The scope-filtered panel has 92 items, 41 of them dead (45%).
- **Many trigger items lie outside their own rule's condition.** For the non-trivial rules, 51 of 123 trigger items
  (41%) are out of scope and 72 are in scope. The v3 code-based trigger therefore includes many items the rule does
  not claim to address. The first attempt's manual reading found 18/42 out of scope.
- **The probe is refuted.** The probe drops an item when the parent and control 1 fail every trigger run.
  - It drops 92/143 items: all 71 dead, but also 11 of the 22 up items, where the rule passed at least once and
    neither the parent nor control 1 ever did.
  - This refutes the first attempt's probe recommendation.
  - A cheaper probe with fewer runs would drop even more.
- **Why this matters less than it seems.** A dead item contributes a paired difference of exactly zero. In a paired
  test it costs solver calls, not power, and no task-level condition separates it from the rare informative items.

### 4.4 Do rules act where their condition holds? [M]
The 13 non-trivial screened rules, on the whole check half, with movement at runs 0..GATE_RUNS-1:

| measure | in scope | out of scope | test |
|---|---|---|---|
| the rule's own arm moves (rule mean != parent mean) | 98/505 (19.4%) | 76/402 (18.9%) | permutation p = 0.60 (one-sided, in > out); Fisher p = 0.87 |
| net change, in items | -2.5 | +2.5 | permutation p = 0.72 |
| parent unstable (training runs and screen runs mix pass and fail) | 109/505 (21.6%) | 89/403 (22.1%) | Fisher p = 0.87 |
| the other screened arms of the same stage move, on this rule's scope | 141/788 (17.9%) | 190/875 (21.7%) | Fisher p = 0.057 |

- **I-ds s1-r1 (surname-only answers), the only rule that concentrates** (per-rule rows in Table B).
  - In scope 8/26 against out of scope 6/74 (Fisher p = 0.008).
  - Against the other arms on the same scope: 3/52 (p = 0.005).
  - In scope it is 2 up and 6 down: the rule acts on person clues and mostly harms them.
  - It does not survive a Bonferroni correction over 13 rules (threshold 0.0038).
- **I-ds s4-r2** (the SpreadsheetBench screen passer): 5/28 against 1/17 (p = 0.39); in scope 1 up and 4 down.
- **The movement is at the noise level.** The rate equals the parent's own instability and lies just above the
  context's same-text noise floor of 30/194 (16%) on SearchQA [C, context section 3]. Rule effects cannot be told
  apart from noise either in scope or out of scope.

### 4.5 Replication across halves and rounds [M]
Rule against parent on the check half and on the proposal half, with the rule's own evidence items excluded, at
runs 0..GATE_RUNS-1. A sign test on the up and down items. The largest effects:

| rule | round | check half: up/down, net | proposal half: up/down, net |
|---|---|---|---|
| E-ds s1-r2 | screen | 18/8, +7.5 (p = 0.076) | 7/5, +2.5 (p = 0.77) |
| E-ds s1-r1 (screen pass) | screen | 17/12, +4.5 (p = 0.46) | 6/17, -7.0 (p = 0.035) |
| E-ds s1-r1 | confirm | 12/12, -1.0 | 6/11, -4.5 (p = 0.33) |
| I-ds s3-r2 | screen | 8/6, 0.0 | 0/9, -5.5 (p = 0.004) |
| I-ds s4-r2 (screen pass) | screen | 2/4, -2.0 | 3/5, -2.0 |
| I-ds s4-r2 | confirm | 4/4, 0.0 | 6/3, +3.0 |

Of the 34 half-by-round comparisons (17 arms x 2 halves), two have p < 0.05, against about 1.7 expected. Both
disagree with the other half of the same arm. No effect replicates.

### 4.6 Panel designs: size, informative yield, cost, null pass rate
Scope: the 15 screened rules, each with its primary condition. Definitions for the table:

- **Movers.** Items with rule mean != parent mean at runs 0..GATE_RUNS-1 [M].
- **C1 cells.** Items x 6 arms x TRIGGER_RUNS, i.e. the cost of running the panel the way v3 runs its trigger panel
  (rule, parent and 4 controls) [M].
- **Solver tokens.** Cells x the measured mean solver tokens per gate cell [E]:

  | benchmark | mean tokens per gate cell | cells measured |
  |---|---|---|
  | SearchQA | 2,603 | 1,923 |
  | OfficeQA | 5,626 | 1,066 |
  | LiveMath | 3,043 | 1,093 |
  | SpreadsheetBench | 3,820 | 563 |
  | ALFWorld | 141,157 | 155 |

  The context's figure for a SearchQA cell is about 3,400 tokens [C].
- **Null pass.** The mean, over the 15 rules, of the probability that a rule with no effect would pass the C1 gain
  part (net >= 1 whole item) [M].

| design | items | movers (up/down) | net | C1 cells | movers per 1,000 cells | solver tokens [E] | known-dead items in the panel | null pass | observed panels with net >= 1 (null expectation) |
|---|---|---|---|---|---|---|---|---|---|
| v3 trigger (code-based failures) | 142 | 33 (15/18) | -2.5 | 2,892 | 11.4 | 33.3M | 71 | 0.26 | 4/15 (3.8) |
| v4 plan: all in-scope check-half items | 632 | 129 (68/61) | +2.0 | 14,172 | 9.1 | 89.2M | 41 + unknown | 0.36 | 5/15 (5.4) |
| scope-filtered trigger (v3 trigger AND condition) | 92 | 24 (10/14) | -3.5 | 1,824 | 13.2 | 29.8M | 41 | 0.23 | 3/15 (3.4) |
| in-scope failures, any code | 268 | 57 (27/30) | -2.0 | 5,916 | 9.6 | 46.6M | 41 + unknown | 0.30 | 5/15 (4.5) |
| scope-filtered trigger + an equal number of in-scope passing items [E] | 168 | 41.2 | -5.5 | 3,288 | 12.5 | - | - | - | - |
| whole check half (reference) | 1,034 | 205 | +4.5 | 23,412 | 8.8 | 115.7M | 71 + unknown | 0.39 | 5/15 (5.9) |

Notes on the table:

- **Two-run movers undercount.** On the trigger items, movers at the trigger runs number 41 against 33 at 2 runs, a
  factor of 1.24.
- **The v3 panel has 142 items, not 143,** because spreadsheetbench/37456 has an unknown cell.
- **"+ unknown"**: the controls never ran on non-trigger items, so their deadness is unknown.
- **The null pass rate covers only part of C1.** It models the gain part at gate runs. It does not model the
  control-margin sub-condition or v3's larger run counts on trigger items.
- **The observed number of panels with net >= 1 equals the noise expectation in every design.**
- **Why the v4 plan costs so much.** It adds 490 items, most of them SearchQA and LiveMath. Its token cost is 2.7x
  rather than 4.9x only because the single ALFWorld rule is "always", so its panel merely doubles from 14 to 28
  items. ALFWorld cells cost 141k tokens each.
- **Only the two scope-filtered designs raise the yield per cell, and only by 10-16%.** The scope-filtered trigger
  reaches 13.2 movers per 1,000 cells (measured), and the version with matched passing items reaches 12.5
  (estimated).
  - The scope-filtered trigger saves 37% of the C1 cells but only 10% of the tokens, because the ALFWorld rule is
    unaffected.
  - It loses 9 of the 33 two-run movers, and 6 of the 22 up items at the trigger runs.

### 4.7 Judge reliability [M]
**Vote stability.** 3 identical votes, 13 conditions, 908 items:

- unanimous on 792 items (87.2%);
- the first vote equals the majority on 874 (96.3%);
- Fleiss kappa runs from 0.17 to 0.92.

The low kappas occur only for near-universal conditions: E-ds s3-r3 (0.17) and E-ds s3-r2 (0.49) are both 48/49
positive and unanimous on 45/49 and 48/49 items. This is the known high-agreement, low-kappa paradox [C, Feinstein
and Cicchetti 1990].

| condition | unanimous | Fleiss kappa | majority positive |
|---|---|---|---|
| I-ds s1-r1 answer is a person | 94/100 | 0.90 | 26 |
| E-ds s1-r4 official item / publication / person | 94/99 | 0.92 | 27 |
| I-ds s4-r2 matching by key | 42/45 | 0.91 | 28 |
| I-ds s3-r2 options differ in strength | 45/49 | 0.79 | 42 |
| E-ds s3-r3 a strengthened option | 45/49 | 0.17 | 48 |
| E-ds s3-r2 a weakened option | 48/49 | 0.49 | 48 |
| E-ds s2-r3 multi-step calculation | 33/37 | 0.77 | 30 |
| E-ds s1-r3 slot / title / other fact | 88/99 | 0.80 | 23 |
| E-ds s4-r4 per-row result | 38/45 | 0.78 | 27 |
| I-ds s1-r2 category stated | 83/100 | 0.76 | 65 |
| E-ds s1-r1 name could carry extra words | 81/99 | 0.74 | 66 |
| E-ds s2-r2 aggregate / inclusion-exclusion | 28/37 | 0.68 | 18 |
| I-ds s1-r4 two or more constraints | 73/100 | 0.63 | 57 |

**Agreement with independent readers.**

- **My blind labels.** I labelled 30 random check-half items per condition before seeing the votes.
  - I-ds s1-r4 (two or more constraints): the majority equals my label on 24/30 items, and on 20/25 of the items I
    marked as certain. A single vote matches on 23/30. The judge says "applies" less often than I do (16 against
    22). All 6 disagreements are my "applies" against the judge's "does not", often with split votes, which points
    to a vague condition rather than judge error.
  - E-ds s3-r3 (a strengthened option): 27/30 (26/27 certain); a single vote 28/30.
- **The first attempt's reader.** These labels were written against that attempt's condition wording, so wording
  differences also count as disagreement:

  | condition | agreement | note |
  |---|---|---|
  | person | 29/30 | |
  | aggregate | 27/30 | |
  | small constant | 24/30 | 1 vote |
  | key match | 29/30 | |
  | **total** | **109/120** | 97/104 on the items that reader marked certain |

- **The first attempt's judge** (different wording, 3 votes): 110/120.
- **Pooled.** The majority agrees with an independent reader on 160/180 items (88.9%), and on 143/156 (91.7%) of the
  items the reader marked certain. Per set the range is 24/30 to 29/30.

**Cost per call** (reason, then label):

| benchmark | tokens per call |
|---|---|
| SearchQA | 408 |
| OfficeQA | 456 |
| LiveMath | 1,151 |
| SpreadsheetBench | 502 |
| ALFWorld | 383 |

**Answer to the task's question.** Yes. A reason-then-label GLM judge with a 3-vote majority is reliable enough to
assign items to a condition. Its error is smaller than the disagreement between condition writers (section 4.8).

- **Unanimity flags vague conditions.** A unanimity rate below about 85% identifies the conditions that are hard to
  apply: two or more constraints 73%, aggregate 76%, minimal name 82%, category 83%, per-row 84%.
  - The two weakest agreements with an independent reader were 24/30 each.
  - One was on the least unanimous condition, "two or more constraints".
  - The other was on "small constant", which had only one vote.
  - With only 5 three-vote sets that have independent labels, this association is suggestive, not established.
- **A single vote would be nearly as good.** The first vote equals the 3-vote majority on 96.3% of items.

### 4.8 Writer sensitivity: the same rule, two condition writers [M]
**The first attempt's regex/heuristic predicates against my judged/mechanical conditions.**

- 29 comparable pairs. Excluded: 8 pairs with an identical mechanical feature and 5 pairs where one side is always.
- Median Cohen kappa 0.27; median raw agreement 78%.
- 18/29 pairs are below 0.4, and 7/29 are at or above 0.6.

**Conditions written by GLM (the first attempt's drafts), evaluated by the same r2 judge** (1 vote each, 800 calls,
438,475 tokens), against my conditions (my first vote), on 11 comparable rules:

| rule | items GLM / mine | agree | kappa | precision GLM (base) | trigger items in scope, GLM / mine |
|---|---|---|---|---|---|
| I-ds s1-r1 | 25 / 26 | 98/100 | 0.95 | 0.12 (0.11) | 3 / 3 of 11 |
| I-ds s4-r2 | 27 / 28 | 44/45 | 0.95 | 0.30 (0.33) | 8 / 9 of 15 |
| E-ds s4-r4 | 34 / 27 | 40/45 | 0.74 | 0.32 (0.33) | 11 / 9 of 15 |
| I-ds s1-r2 | 53 / 65 | 87/100 | 0.74 | 0.08 (0.11) | 4 / 6 of 11 |
| E-ds s1-r4 | 23 / 27 | 88/99 | 0.71 | 0.04 (0.07) | 1 / 2 of 7 |
| E-ds s3-r3 | 48 / 48 | 48/49 | 0.66 | 0.13 (0.12) | 6 / 6 of 6 |
| I-ds s1-r4 | 47 / 57 | 79/100 | 0.58 | 0.00 (0.04) | 0 / 1 of 4 |
| E-ds s2-r2 | 17 / 18 | 27/37 | 0.46 | 0.35 (0.46) | 6 / 10 of 17 |
| I-ds s3-r2 | 48 / 42 | 42/49 | 0.19 | 0.13 (0.12) | 6 / 5 of 6 |
| E-ds s1-r3 | 61 / 23 | 52/99 | 0.15 | 0.03 (0.11) | 2 / 1 of 11 |
| E-ds s3-r2 | 22 / 48 | 23/49 | 0.03 | 0.00 (0.10) | 0 / 5 of 5 |

- **Overall.** 628/772 items agree (81%); median kappa 0.66; trigger items in scope 47/108 (GLM) against 57/108
  (mine).
- **One outright misreading.** For E-ds s3-r2, GLM wrote "the meta-option is among the choices" in place of the
  rule's actual condition, "an option is a weakened version of another".
- **GLM's conditions do not discriminate the target codes either.** Their precision is at or below the base rate on
  every rule.
- **I-ds s5-r1 is not in the table.** GLM's condition there, "multiple receptacles listed", holds on 28/28 items, and
  mine is "always".
- **Interpretation.** The panel depends more on who writes the condition than on judge noise. Writer agreement is
  81% (GLM vs me) or 78% (regex vs me), against 87% judge unanimity and 96% vote-to-majority agreement. In v4 the
  analyst writes the condition, so its wording is part of the rule and must be frozen with it.

### 4.9 Evidence coverage: does the rule's own evidence satisfy its condition? [M]
**Setup.** Each judged or mechanical condition is checked on the rule's evidence items, i.e. the proposal-half
failures the analyst cited. Judged conditions get 3 votes (336 calls, 200,525 tokens); the votes are unanimous on
108/112 items.

- **Pooled.** 126/159 evidence items are covered, against 87.3 expected at each condition's check-half rate.
  Conditions are therefore related to their evidence.
- **Incomplete coverage is common.** 20/38 rules have at least one uncovered evidence item, and 3 cover less than
  half:
  - I-ds s2-r4 (chart), 0/3;
  - E-ds s2-r2 (aggregate), 1/4;
  - E-ds s1-r3 (slot), 3/7.
- **Screened conditions.** 51/60 covered. Uncovered items occur in I-ds s1-r1, E-ds s1-r1, E-ds s1-r3 and E-ds s2-r2.
- **Above chance.** Coverage is significantly above chance (binomial, p < 0.05) for 6 rules:
  - I-ds s1-r3;
  - E-ds s1-r4;
  - I-ds s3-r1;
  - E-ds s3-r1;
  - E-ds s3-r4;
  - E-ds s4-r3.
- **Use.** This is an internal-consistency check with zero solver cost. A rule whose cited evidence lies outside its
  own condition is either mis-scoped or cites the wrong evidence. It can go back to the analyst with the uncovered
  items, using v4's re-ask with validator feedback.
- **Caveat.** These are my conditions. With analyst-written conditions the check would test the analyst's own
  consistency, which is the intended use.

## 5. Interpretation
1. **Checkable conditions are feasible and cheap, but they do not classify the targeted failures.** In the v3 data
   the examiner codes and the task features the rules name are nearly independent: median lift 1.02. The only
   high-precision conditions are structural prerequisites of the code.
2. **Dead items are not a scoping problem.** Before the solver runs, dead items look like the rare informative items:
   both mostly failed both training runs. A condition excludes dead items only slightly more often than others
   (42% against 29%, p = 0.12), and a cheap probe throws away half of the up items.
3. **The premise of conditional panels has no support in v3.** That premise is that a rule acts where its condition
   holds. In fact rules move in-scope and out-of-scope items at the same rate, and that rate equals the parent's own
   instability. With effects this small, enlarging the C1 panel to all in-scope items adds noise and cost and loosens
   the fixed one-item gain threshold (null pass 0.26 to 0.36).
4. **The one exception shows the right use.** I-ds s1-r1 acted on person clues and harmed them. The condition is
   useful as a mechanism and harm diagnostic, not as a panel generator.
5. **Untested caveat.** The v3 rules were not written in the v4 conditional template ("when X: do Y; otherwise
   default"). Such a template might confine a rule's side effects to its scope. Testing this needs v4 data; the
   scripts here run on it unchanged once the conditions come from the rules themselves.

## 6. Recommended v5 design (narrowed D4)
1. **Typed condition field.**
   - The types are `mechanical`, `judged`, `always` and `runtime`.
     - `mechanical` is an exact feature computed by code, and is preferred where one exists: the meta-option is
       present; two or more editions; the task type; the size of the answer range.
     - `judged` is a natural-language condition on solver-visible task fields.
   - The condition text is frozen with the rule text.
   - A judged condition that holds on >= 90% of the check half is treated as `always`.
2. **Judge.**
   - GLM, reason-then-label JSON.
   - Two votes, plus a third on disagreement. The expected cost is about 2.1 calls per item, and the result
     reproduces the 3-vote majority.
   - If unanimity on the check half is below 85%, the analyst is asked once to sharpen the condition, with the split
     items shown.
3. **Evidence-coverage gate** (free in solver calls). Every cited evidence item must satisfy the rule's condition;
   otherwise the rule is re-asked with the uncovered items.
4. **Trigger panel: keep v3's code-based failures, intersected with the condition** (the scope-filtered trigger).
   - The panel has 92 instead of 142 items.
   - Yield is 13.2 against 11.4 movers per 1,000 cells.
   - C1 cells fall by 37%, but tokens only by 10%.
   - Out-of-scope code-matched failures are reported separately: they test whether the fix generalizes, not its
     mechanism.
   - This is a modest saving, not a fix.
5. **Scope-specificity diagnostic for every screened rule.** It needs no extra solver calls, because rule and parent
   already run on the whole focal panel.
   - It reports in-scope against out-of-scope discordance, with the parent-instability and other-arm controls.
   - A rule whose in-scope movement is not above both out-of-scope movement and the parent's instability is flagged
     ("no mechanism evidence").
   - It is a report, not a gate, until D8 calibrates it.
6. **C2 harm.** In-scope harm is reported separately; the harm of I-ds s1-r1 sits in scope.
7. **Do not adopt the all-in-scope C1 panel with the fixed "gain >= 1 whole item" threshold.** If v4 keeps that
   panel, the threshold should be replaced by a calibrated paired test (D8). The design costs about 2.7x the solver
   tokens of v3's trigger panel for a lower yield.
8. **Dead items: no pre-classifier.**
   - They do not bias a paired test; they cost calls.
   - Cost control belongs to D1 (fresh batches) and D5 (noise).
   - If cost must be cut, the defensible lever is a smaller number of runs on items that failed both training runs,
     decided by a power analysis (D8). Classifying items by task features is not a defensible lever.
9. **LiveMath.** The exact "meta-option present" feature is a perfect structural predictor of code D1 (precision
   0.95-0.96, recall 1.00 on the check halves). It is the natural condition for the structural rules D7 proposes.

## 7. Risks, unknowns, threats to validity
- **The conditions are post hoc.** I wrote them from the rule texts without looking at outcomes, but knowing the
  project's results. Another writer produces materially different panels (section 4.8).
- **The codes are noisy per-run GLM diagnoses.** Their reliability is not measured here. Precision against a noisy
  code underestimates true precision, but the near-zero in-vs-out movement difference does not depend on the codes.
- **The denominators are small.**
  - 15 screened rules, 13 of them non-trivial.
  - 143 trigger items.
  - Check halves of 28-49 items outside SearchQA.
  - The per-rule tests have little power. The pooled in-vs-out comparison (505 vs 402 item-rule pairs) gives a rough
    unstratified 95% interval for the in-minus-out discordance difference of about -4.6 to +5.6 percentage points
    [E]. An in-scope concentration larger than about 6 points is therefore unlikely.
- **Movement at 2 or 1 runs undercounts movers** (factor 1.24 on trigger items).
- **The v3 rules are not v4 conditional rules** (section 5, point 5).
- **The judge sees the task fields only.** It does not see the SearchQA snippets, the OfficeQA pages or the ALFWorld
  trajectory. Some conditions depend on that unseen content.
- **The judge, examiner and analyst are all GLM-5.3,** so their errors may be correlated.
- **Literature.** AutoGuide (Fu et al., arXiv 2403.08978, NeurIPS 2024) is a precedent: it attaches an applicability
  context to each guideline mined from offline experience and selects guidelines by context at test time [C,
  abstract checked]. As far as the abstract shows, it reports end-task gains (for example WebArena), not the
  precision of the context match against failure diagnoses. D4's negative finding is therefore not contradicted by
  it.

## 8. Cost
**Spent [M].**

| item | calls | tokens |
|---|---|---|
| this round: main judge pass | 3,431 | 1,857,794 |
| this round: smoke test | 28 | 17,354 |
| this round: GLM-written conditions | 800 | 438,475 |
| this round: evidence pass | 336 | 200,525 |
| **this round, total** | **4,595** | **2,514,148** |
| first attempt | 529 | 276,852 |
| **D4 overall** | | **2,791,000** |

There were no solver calls. The pilot budget was about 3M.

**v5 estimate [E].** 5 rules x the check half x 3 votes, per chain over the five stages:

| benchmark | tokens |
|---|---|
| SearchQA | 0.61M |
| OfficeQA | 0.25M |
| LiveMath | 0.85M |
| SpreadsheetBench | 0.34M |
| ALFWorld | 0.16M |
| **total per chain** | **about 2.2M** |

- Both chains: about 4.4M, or about 3% of the v3 run's 139M.
- With 2+1 voting: about 1.55M per chain.
- Evidence-coverage gate: about 0.1M per chain.
- Mechanical conditions: zero.
- Scope-specificity diagnostic: zero solver cost.
- The only option that raises solver cost is the all-in-scope C1 panel, at about 2.7x the trigger-panel tokens
  (section 4.6). It is not recommended.

## 9. Files and reproduction
**Mac.** Folder `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D4/`
holds:

- this `report.md`;
- `earlier_attempt1_report.md` and the first attempt's files (`predicates.py`, `judge_pilot.json`,
  `manual_labels.json`, `glm_predicates.json`, ...);
- `r2/`: all round-2 scripts and their non-item outputs.

**Remote.** The new machine holds `/data/feasibility/D4/`:

- `items/*.json`: training-item extracts, built by the first attempt's `build_items.py`;
- `r2/`: identical scripts plus the judge JSONL files.

**Pipeline**, run from `/data/feasibility/D4/r2` with the environment's python:

1. `dump_texts.py` -> `rules_r2.json`
2. `mech_r2.py` -> `mech_r2.json`
3. `outcomes_r2.py` -> `outcomes_r2.json`
4. `judge_r2.py --votes-screened 3 --votes-other 1 --workers 6 --cap 2600000` (paid; the shell proxy must be on) ->
   `judge_r2.jsonl`
5. `earlier_matches.py` -> `earlier_matches.json`
6. `analyse_r2.py` -> `analysis_r2.json` and `analyse_r2.out`
7. `tables_r2.py` -> `tables_r2.md`
8. `replicate_r2.py` -> `replicate_r2.json`
9. `judge_glmcond_r2.py --workers 6 --cap 700000` (paid) -> `judge_glmcond_r2.jsonl`; then `analyse_glmcond_r2.py`
   -> `glmcond_analysis_r2.json`
10. `judge_evidence_r2.py --workers 6 --cap 450000` (paid) -> `judge_evidence_r2.jsonl`; then
    `analyse_evidence_r2.py` -> `evidence_analysis_r2.json`
11. `cell_tokens_r2.py` -> `cell_tokens_r2.out`
12. `falsepass_r2.py` -> `falsepass_r2.json`
13. `pattern_r2.py` -> `pattern_r2.json`

Steps 12-13 execute only the measurement part of `analyse_r2.py`, so they rewrite none of its outputs.

**Launch form used for the paid steps:**
`ssh -o BatchMode=yes <datatools-login> "(bash -ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/D4/r2 && setsid nohup /root/continual-alf-prep-20260928/env/bin/python judge_r2.py --votes-screened 3 --votes-other 1 --workers 6 --cap 2600000 > judge_r2.log 2>&1 < /dev/null &' >/dev/null 2>&1 &)"`

## Appendix A and B. Rule tables

In the tables, `*` marks a screened rule. A row reading `judged (narrow)` is my narrowing of a rule whose literal text applies to every task; the literal reading follows it as `always(literal)`. Table B counts dead, discordant and up items at the trigger runs, and in-scope and out-of-scope movement at runs 0..GATE_RUNS-1.

### Table A. Every rule-predicate row (check half of its stage; judged = 3-vote majority for screened rules, 1 vote otherwise)

| rule | status | codes | predicate | type | match / check | passed / fail-target / fail-other | tpos (base) | precision | recall | lift | Fisher p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| I-ds/s1/s1-r1 * | supported | D1 | sq_person | judged | 26/100 | 22 / 3 / 1 | 11 (0.11) | 0.12 | 0.27 | 1.05 | 1.00 |
| I-ds/s1/s1-r2 * | supported | D1 | sq_category_stated | judged | 65/100 | 51 / 6 / 8 | 11 (0.11) | 0.09 | 0.55 | 0.84 | 0.51 |
| I-ds/s1/s1-r3 | leak_adjudicated_word | D5 | sq_other_entities | judged | 15/100 | 9 / 1 / 5 | 2 (0.02) | 0.07 | 0.50 | 3.33 | 0.28 |
| I-ds/s1/s1-r4 * | supported | D4 | sq_multi_constraint | judged (narrow) | 57/100 | 42 / 1 / 14 | 4 (0.04) | 0.02 | 0.25 | 0.44 | 0.31 |
| I-ds/s1/s1-r4 * | supported | D4 | always(literal) | always | 100/100 | 73 / 4 / 23 | 4 (0.04) | 0.04 | 1.00 | 1.00 | - |
| I-ds/s1/s1-r5 | dropped_pre_dispatch | D2 | always | always | 100/100 | 73 / 8 / 19 | 8 (0.08) | 0.08 | 1.00 | 1.00 | - |
| E-ds/s1/s1-r1 * | supported | D1 | sq_minimal_name | judged (narrow) | 66/99 | 50 / 6 / 10 | 6 (0.06) | 0.09 | 1.00 | 1.50 | 0.17 |
| E-ds/s1/s1-r1 * | supported | D1 | always(literal) | always | 99/99 | 72 / 6 / 21 | 6 (0.06) | 0.06 | 1.00 | 1.00 | - |
| E-ds/s1/s1-r2 * | supported | D3 | always | always | 99/99 | 72 / 6 / 21 | 6 (0.06) | 0.06 | 1.00 | 1.00 | - |
| E-ds/s1/s1-r3 * | supported | D4,D5,other | sq_slot | judged | 23/99 | 21 / 1 / 1 | 11 (0.11) | 0.04 | 0.09 | 0.39 | 0.45 |
| E-ds/s1/s1-r4 * | supported | D2 | sq_official | judged | 27/99 | 21 / 2 / 4 | 7 (0.07) | 0.07 | 0.29 | 1.05 | 1.00 |
| E-ds/s1/s1-r5 | supported | D4 | sq_multi_condition | judged (narrow) | 58/99 | 44 / 2 / 12 | 4 (0.04) | 0.03 | 0.50 | 0.85 | 1.00 |
| E-ds/s1/s1-r5 | supported | D4 | always(literal) | always | 99/99 | 72 / 4 / 23 | 4 (0.04) | 0.04 | 1.00 | 1.00 | - |
| I-ds/s2/s2-r1 | evidence_invalid | D2 | oq_compound_stat | judged | 15/36 | 1 / 8 / 6 | 14 (0.39) | 0.53 | 0.57 | 1.37 | 0.18 |
| I-ds/s2/s2-r2 | evidence_invalid | D1 | oq_editions2 | mechanical | 19/36 | 3 / 7 / 9 | 8 (0.22) | 0.37 | 0.88 | 1.66 | 0.04 |
| I-ds/s2/s2-r3 | evidence_invalid | D3 | oq_precision | judged | 26/36 | 3 / 8 / 15 | 9 (0.25) | 0.31 | 0.89 | 1.23 | 0.39 |
| I-ds/s2/s2-r4 | insufficient_support | D5,G11 | oq_chart | mechanical | 2/36 | 1 / 1 / 0 | 3 (0.08) | 0.50 | 0.33 | 6.00 | 0.16 |
| I-ds/s2/s2-r5 | insufficient_support | D4 | oq_projection | judged | 14/36 | 2 / 1 / 11 | 2 (0.06) | 0.07 | 0.50 | 1.29 | 1.00 |
| E-ds/s2/s2-r1 | supported | D1 | oq_period_type | judged (narrow) | 36/37 | 6 / 13 / 17 | 13 (0.35) | 0.36 | 1.00 | 1.03 | 1.00 |
| E-ds/s2/s2-r1 | supported | D1 | always(literal) | always | 37/37 | 6 / 13 / 18 | 13 (0.35) | 0.35 | 1.00 | 1.00 | - |
| E-ds/s2/s2-r2 * | supported | D2 | oq_aggregate | judged | 18/37 | 2 / 10 / 6 | 17 (0.46) | 0.56 | 0.59 | 1.21 | 0.33 |
| E-ds/s2/s2-r3 * | supported | D3 | oq_multistep | judged | 30/37 | 3 / 9 / 18 | 9 (0.24) | 0.30 | 1.00 | 1.23 | 0.16 |
| E-ds/s2/s2-r4 | supported | D4 | oq_format | judged | 34/37 | 5 / 4 / 25 | 5 (0.14) | 0.12 | 0.80 | 0.87 | 0.36 |
| E-ds/s2/s2-r5 | evidence_invalid | D5 | oq_absent | judged | 11/37 | 2 / 2 / 7 | 2 (0.05) | 0.18 | 1.00 | 3.36 | 0.08 |
| I-ds/s3/s3-r1 | dropped_pre_dispatch | D1 | lm_meta | mechanical | 23/49 | 1 / 22 / 0 | 22 (0.45) | 0.96 | 1.00 | 2.13 | 0.00 |
| I-ds/s3/s3-r2 * | supported | D4 | lm_strength_diff | judged | 42/49 | 11 / 5 / 26 | 6 (0.12) | 0.12 | 0.83 | 0.97 | 1.00 |
| I-ds/s3/s3-r4 | insufficient_support | D5 | lm_small_constant | judged | 19/49 | 6 / 0 / 13 | 1 (0.02) | 0.00 | 0.00 | 0.00 | 1.00 |
| E-ds/s3/s3-r1 | leak_adjudicated | D1 | lm_meta | mechanical | 22/49 | 1 / 21 / 0 | 21 (0.43) | 0.95 | 1.00 | 2.23 | 0.00 |
| E-ds/s3/s3-r2 * | supported | D3 | lm_weakened | judged | 48/49 | 14 / 5 / 29 | 5 (0.10) | 0.10 | 1.00 | 1.02 | 1.00 |
| E-ds/s3/s3-r3 * | supported | D4 | lm_strengthened | judged | 48/49 | 15 / 6 / 27 | 6 (0.12) | 0.12 | 1.00 | 1.02 | 1.00 |
| E-ds/s3/s3-r4 | supported | D3,D5 | lm_conjunction | judged | 3/49 | 1 / 0 / 2 | 8 (0.16) | 0.00 | 0.00 | 0.00 | 1.00 |
| E-ds/s3/s3-r5 | insufficient_support | answer_single_letter | always | always | 49/49 | 15 / 2 / 32 | 2 (0.04) | 0.04 | 1.00 | 1.00 | - |
| I-ds/s4/s4-r1 | evidence_invalid | D4 | sb_examples | mechanical | 29/45 | 16 / 8 / 5 | 14 (0.31) | 0.28 | 0.57 | 0.89 | 0.52 |
| I-ds/s4/s4-r2 * | supported | D4,D6 | sb_key_match | judged | 28/45 | 17 / 9 / 2 | 15 (0.33) | 0.32 | 0.60 | 0.96 | 1.00 |
| I-ds/s4/s4-r3 | supported | D1,D5 | sb_formula_cells | mechanical | 11/45 | 7 / 2 / 2 | 4 (0.09) | 0.18 | 0.50 | 2.05 | 0.25 |
| I-ds/s4/s4-r4 | insufficient_support | D3 | sb_fill_derived | judged | 32/45 | 15 / 0 / 17 | 0 (0.00) | 0.00 | - | - | - |
| I-ds/s4/s4-r5 | insufficient_support | D2 | sb_multi_cell | mechanical | 38/45 | 19 / 1 / 18 | 2 (0.04) | 0.03 | 0.50 | 0.59 | 0.29 |
| E-ds/s4/s4-r1 | evidence_invalid | D4 | always | always | 45/45 | 23 / 14 / 8 | 14 (0.31) | 0.31 | 1.00 | 1.00 | - |
| E-ds/s4/s4-r2 | supported | D2,D4 | sb_examples | mechanical | 27/45 | 13 / 8 / 6 | 15 (0.33) | 0.30 | 0.53 | 0.89 | 0.54 |
| E-ds/s4/s4-r3 | supported | D4 | sb_order | judged | 4/45 | 2 / 1 / 1 | 14 (0.31) | 0.25 | 0.07 | 0.80 | 1.00 |
| E-ds/s4/s4-r4 * | supported | D3,D4 | sb_per_row | judged | 27/45 | 11 / 9 / 7 | 15 (0.33) | 0.33 | 0.60 | 1.00 | 1.00 |
| E-ds/s4/s4-r5 | insufficient_support | D1,D5 | sb_datetime | judged (narrow) | 10/45 | 5 / 1 / 4 | 2 (0.04) | 0.10 | 0.50 | 2.25 | 0.40 |
| E-ds/s4/s4-r5 | insufficient_support | D1,D5 | always(literal) | always | 45/45 | 23 / 2 / 20 | 2 (0.04) | 0.04 | 1.00 | 1.00 | - |
| I-ds/s5/s5-r1 * | supported | D3 | always | always | 28/28 | 12 / 14 / 2 | 14 (0.50) | 0.50 | 1.00 | 1.00 | - |
| I-ds/s5/s5-r2 | supported | D3,D4 | rt_nothing | runtime | 16/28 | 5 / 9 / 2 | 14 (0.50) | 0.56 | 0.64 | 1.12 | 0.70 |
| I-ds/s5/s5-r3 | insufficient_support | D4 | rt_nothing | runtime | 16/28 | 5 / 3 / 8 | 3 (0.11) | 0.19 | 1.00 | 1.75 | 0.24 |
| I-ds/s5/s5-r4 | supported | D1,D3 | al_confusable | judged | 14/28 | 6 / 8 / 0 | 16 (0.57) | 0.57 | 0.50 | 1.00 | 1.00 |
| I-ds/s5/s5-r5 | supported | D3 | al_openable | mechanical | 27/28 | 12 / 13 / 2 | 14 (0.50) | 0.48 | 0.93 | 0.96 | 1.00 |
| E-ds/s5/s5-r1 | supported | D3 | always | always | 28/28 | 9 / 16 / 3 | 16 (0.57) | 0.57 | 1.00 | 1.00 | - |
| E-ds/s5/s5-r2 | evidence_invalid | D4 | rt_nothing | runtime | 22/28 | 5 / 4 / 13 | 4 (0.14) | 0.18 | 1.00 | 1.27 | 0.55 |
| E-ds/s5/s5-r3 | evidence_invalid | D1 | al_confusable | judged | 16/28 | 4 / 3 / 9 | 4 (0.14) | 0.19 | 0.75 | 1.31 | 0.61 |
| E-ds/s5/s5-r4 | supported | D1,D2 | al_state | mechanical | 15/28 | 4 / 5 / 6 | 5 (0.18) | 0.33 | 1.00 | 1.87 | 0.04 |
| E-ds/s5/s5-r5 | supported | D1,D3 | always | always | 28/28 | 9 / 17 / 2 | 17 (0.61) | 0.61 | 1.00 | 1.00 | - |

### Table B. Screened rules: dead items, informative items and measured movement (primary predicate)

| rule | predicate | trigger (v3) | dead excluded / dead | alive excluded / alive | discordant(4 runs) kept / all | up kept / up | cond. panel | in-scope: n, moved, up, down, net | out-of-scope: n, moved, up, down, net |
|---|---|---|---|---|---|---|---|---|---|
| I-ds/s1/s1-r1 | sq_person | 11 | 5 / 5 | 3 / 6 | 2 / 4 | 1 / 3 | 26 | 26, 8, 2, 6, -3.5 | 74, 6, 3, 3, +0.0 |
| I-ds/s1/s1-r2 | sq_category_stated | 11 | 2 / 5 | 3 / 6 | 1 / 3 | 1 / 2 | 65 | 65, 4, 2, 2, +0.0 | 35, 3, 0, 3, -2.0 |
| I-ds/s1/s1-r4 | sq_multi_constraint | 4 | 2 / 3 | 1 / 1 | 0 / 0 | 0 / 0 | 57 | 57, 4, 1, 3, -1.0 | 43, 5, 3, 2, +1.0 |
| I-ds/s1/s1-r4 | always(literal) | 4 | 0 / 3 | 0 / 1 | 0 / 0 | 0 / 0 | 100 | 100, 9, 4, 5, +0.0 | - |
| E-ds/s1/s1-r1 | sq_minimal_name | 6 | 0 / 1 | 0 / 5 | 3 / 3 | 3 / 3 | 66 | 66, 20, 12, 8, +3.5 | 33, 9, 5, 4, +1.0 |
| E-ds/s1/s1-r1 | always(literal) | 6 | 0 / 1 | 0 / 5 | 3 / 3 | 3 / 3 | 99 | 99, 29, 17, 12, +4.5 | - |
| E-ds/s1/s1-r2 | always | 6 | 0 / 4 | 0 / 2 | 1 / 1 | 1 / 1 | 99 | 99, 26, 18, 8, +7.5 | - |
| E-ds/s1/s1-r3 | sq_slot | 11 | 5 / 6 | 5 / 5 | 0 / 5 | 0 / 2 | 23 | 23, 4, 3, 1, +1.5 | 76, 21, 11, 10, +0.5 |
| E-ds/s1/s1-r4 | sq_official | 7 | 5 / 6 | 0 / 1 | 0 / 0 | 0 / 0 | 27 | 27, 4, 4, 0, +2.5 | 72, 19, 8, 11, -1.0 |
| E-ds/s2/s2-r2 | oq_aggregate | 17 | 4 / 9 | 3 / 8 | 4 / 5 | 3 / 3 | 18 | 18, 4, 3, 1, +1.0 | 19, 4, 2, 2, +0.0 |
| E-ds/s2/s2-r3 | oq_multistep | 9 | 0 / 4 | 0 / 5 | 4 / 4 | 1 / 1 | 30 | 30, 5, 2, 3, -1.0 | 7, 0, 0, 0, +0.0 |
| I-ds/s3/s3-r2 | lm_strength_diff | 6 | 1 / 1 | 0 / 5 | 2 / 2 | 1 / 1 | 42 | 42, 10, 4, 6, -2.0 | 7, 4, 4, 0, +2.0 |
| E-ds/s3/s3-r2 | lm_weakened | 5 | 0 / 4 | 0 / 1 | 1 / 1 | 1 / 1 | 48 | 48, 12, 6, 6, +0.5 | 1, 0, 0, 0, +0.0 |
| E-ds/s3/s3-r3 | lm_strengthened | 6 | 0 / 2 | 0 / 4 | 3 / 3 | 1 / 1 | 48 | 48, 14, 7, 7, -1.0 | 1, 0, 0, 0, +0.0 |
| I-ds/s4/s4-r2 | sb_key_match | 15 | 3 / 5 | 3 / 10 | 2 / 3 | 2 / 2 | 28 | 28, 5, 1, 4, -3.0 | 16, 1, 1, 0, +1.0 |
| E-ds/s4/s4-r4 | sb_per_row | 15 | 3 / 6 | 3 / 9 | 2 / 4 | 1 / 2 | 27 | 27, 4, 2, 2, +0.0 | 18, 4, 2, 2, +0.0 |
| I-ds/s5/s5-r1 | always | 14 | 0 / 10 | 0 / 4 | 3 / 3 | 0 / 0 | 28 | 28, 5, 1, 4, -3.0 | - |

## Appendix C. The 49 conditions (written from the rule text only)

| rule | screened | status | type | judge sees | when (my condition) |
|---|---|---|---|---|---|
| I-ds/s1/s1-r1 | yes | supported | judged | question | The answer the clue asks for is the name of a specific person (real or fictional): the clue uses 'he'/'she'/'his'/'her', or asks for 'this author', 'this president', 'this actress' or another individual human being. |
| I-ds/s1/s1-r2 | yes | supported | judged | question | The clue itself states the category of the answer with a phrase that refers to the answer ('this sport', 'this type of radar', 'these exiles', 'this river'), so the answer is a distinguishing name within that stated category. |
| I-ds/s1/s1-r3 |  | leak_adjudicated_word | judged | question | The clue names a list of several items or gives an example entity ('like X', 'such as X'), and the answer is something other than those named items (e.g. one specific item of the list, the shared role or type, or a place). |
| I-ds/s1/s1-r4 | yes | supported | judged (narrowed; literal: always) | question | The clue states at least two independent constraints that the answer must satisfy at the same time (e.g. a date and a place, a role and a quantity, a description plus a 'named for' fact), or it names two places and asks what they share. |
| I-ds/s1/s1-r5 |  | dropped_pre_dispatch | always | - | every clue (mirror the snippets' surface form) |
| E-ds/s1/s1-r1 | yes | supported | judged (narrowed; literal: always) | question | The answer is a name that could carry extra words: a person's name (titles, first or middle names or initials could be added), or a name whose category the clue already states with a phrase referring to the answer ('this missile', 'this river', 'this magazine'). |
| E-ds/s1/s1-r2 | yes | supported | always | - | every clue (one short answer inside the answer tag) |
| E-ds/s1/s1-r3 | yes | supported | judged | question | The clue asks for a title or for the missing part of a quoted or year-marked fragment of a work, or it names a topic entity (a person, a park) and asks for a different identifying fact about it (such as its country or state). |
| E-ds/s1/s1-r4 | yes | supported | judged | question | The answer is an officially designated item (a state bird, flower, tree, motto or similar symbol), the title of a publication (magazine, journal, newspaper), or the name of a specific person. |
| E-ds/s1/s1-r5 |  | supported | judged (narrowed; literal: always) | question | The clue states at least two independent conditions (a date, a place, a role, a quantity or a 'named for' fact) that the answer must satisfy at the same time. |
| I-ds/s2/s2-r1 |  | evidence_invalid | judged | question | The question asks for a compound derived statistic (compound annual growth rate, geometric mean, value at risk, elasticity, correlation, regression coefficient, standard deviation, duration) rather than a reported value, a sum, a simple difference or a simple percent change. |
| I-ds/s2/s2-r2 |  | evidence_invalid | mechanical | - | the supplied context contains pages from two or more distinct bulletin editions |
| I-ds/s2/s2-r3 |  | evidence_invalid | judged | question | Answering requires a computation with non-integer intermediate results (ratios, percentages, growth rates, logarithms, roots, averages or smoothed values) and the question states the precision or rounding of the final answer. |
| I-ds/s2/s2-r4 |  | insufficient_support | mechanical | - | the question or the supplied pages mention a chart or graph |
| I-ds/s2/s2-r5 |  | insufficient_support | judged | question | The question asks to project, forecast or extrapolate a level (e.g. applying a growth rate to a reported value), or to express a computed level in a stated unit or scale (millions, billions) with a stated number of decimals. |
| E-ds/s2/s2-r1 |  | supported | judged (narrowed; literal: always) | question | The question specifies a period whose type must be matched to the right table row or column: fiscal versus calendar year, a specific month or quarter, or a 'to date' / end-of-period figure. |
| E-ds/s2/s2-r2 | yes | supported | judged | question | The question asks for an aggregate over several entries (a total, sum, combined, cumulative or average figure) or for a figure defined by inclusion or exclusion conditions over rows, rather than a single reported value. |
| E-ds/s2/s2-r3 | yes | supported | judged | question | Answering requires a multi-step calculation (two or more arithmetic operations on extracted values) or a conversion between scales or units (e.g. billions to millions, millions to dollars). |
| E-ds/s2/s2-r4 |  | supported | judged | question | The question gives explicit instructions about the answer's form: number of decimal places, percent versus decimal, units or scale, sign or absolute value, list order or brackets, or comma-separated values. |
| E-ds/s2/s2-r5 |  | evidence_invalid | judged | question | The question asks for a value read from a chart or figure, or depends on information from outside the Treasury Bulletin (an external index, another publication's date, a fact the bulletin's tables do not report). |
| I-ds/s3/s3-r1 |  | dropped_pre_dispatch | mechanical | - | the meta-option is among the choices |
| I-ds/s3/s3-r2 | yes | supported | judged | question, choices | The question asks for the strongest valid (best, sharpest) statement, and at least two of the concrete options (ignore the meta-option) make claims of different strength about the same result, e.g. a sharper exponent or constant, a two-sided instead of one-sided estimate, a dropped hypothesis, or an extra parameter or regime. |
| I-ds/s3/s3-r3 |  | invalid | none | - | the question asks for the strongest provable statement and some options restrict the class or range (no target code) |
| I-ds/s3/s3-r4 |  | insufficient_support | judged | question, choices | At least two of the concrete options state essentially the same claim and differ only in a small explicit constant, index, exponent, boundary value of a parameter, or edge case. |
| E-ds/s3/s3-r1 |  | leak_adjudicated | mechanical | - | the meta-option is among the choices |
| E-ds/s3/s3-r2 | yes | supported | judged | question, choices | The question asks for the strongest valid or an equivalent statement, and at least one concrete option is a weakened version of another (restricted to a subclass or extra hypotheses, a one-directional implication instead of an equivalence, a weaker conclusion, or part of the conclusion dropped). |
| E-ds/s3/s3-r3 | yes | supported | judged | question, choices | At least one concrete option is a strengthened version of another option: it drops a needed hypothesis or an 'almost every'/'generic' qualifier, tightens a constant or exponent, adds 'moreover' clauses (extra structure, two-sided bounds), or extends the claim to endpoint cases. |
| E-ds/s3/s3-r4 |  | supported | judged | question, choices | The question asks for a statement equivalent to (or exactly characterizing) a conjunction of several hypotheses or conditions. |
| E-ds/s3/s3-r5 |  | insufficient_support | always | - | every item (answer-tag format) |
| I-ds/s4/s4-r1 |  | evidence_invalid | mechanical | - | the workbook has an example/expected-style sheet or the answer range is already partly filled in the input workbook |
| I-ds/s4/s4-r2 | yes | supported | judged | instruction, answer_position, sheets | The task requires matching rows or cells by a text or key value: a lookup, a match between two lists, columns or sheets, finding rows whose text equals or contains a given value, or joining records on an identifier. |
| I-ds/s4/s4-r3 |  | supported | mechanical | - | the input workbook contains formula cells |
| I-ds/s4/s4-r4 |  | insufficient_support | judged | instruction, answer_position, sheets | The task asks to append new rows or fill a column of many rows with values that must be taken from matched source rows or aggregates (not a single constant or a single cell). |
| I-ds/s4/s4-r5 |  | insufficient_support | mechanical | - | the answer range has two or more cells |
| E-ds/s4/s4-r1 |  | evidence_invalid | always | - | every task (map the workbook first) |
| E-ds/s4/s4-r2 |  | supported | mechanical | - | the workbook has an example/expected-style sheet or the answer range is already partly filled in the input workbook |
| E-ds/s4/s4-r3 |  | supported | judged | instruction, answer_position, sheets | The instruction (or an example it refers to) fixes the order of output rows or of processing: a sort key, 'same order as', first-in-first-out by date, earliest/latest first, or row-by-row processing in a stated order. |
| E-ds/s4/s4-r4 | yes | supported | judged | instruction, answer_position, sheets | The answer range covers several rows and each row's result must be computed from that row's own cells (a per-row value or formula), rather than one value for the whole range. |
| E-ds/s4/s4-r5 |  | insufficient_support | judged (narrowed; literal: always) | instruction, answer_position, sheets | The task involves date or time values (dates, times, durations, months, timestamps) that must be read, compared or written. |
| I-ds/s5/s5-r1 | yes | supported | always | - | every task (systematic receptacle search) |
| I-ds/s5/s5-r2 |  | supported | runtime | - | the environment answered 'Nothing happens' to an action |
| I-ds/s5/s5-r3 |  | insufficient_support | runtime | - | a placement command was rejected (proxy: any 'Nothing happens') |
| I-ds/s5/s5-r4 |  | supported | judged | goal | The goal names an object type that has a commonly confusable look-alike type in household scenes (e.g. butterknife vs knife, pot vs pan, mug vs cup, apple vs tomato, spray bottle vs soap bottle). |
| I-ds/s5/s5-r5 |  | supported | mechanical | - | the room lists at least one openable receptacle (drawer, cabinet, fridge, microwave, safe) |
| E-ds/s5/s5-r1 |  | supported | always | - | every task (systematic receptacle search) |
| E-ds/s5/s5-r2 |  | evidence_invalid | runtime | - | the environment answered 'Nothing happens' to an action |
| E-ds/s5/s5-r3 |  | evidence_invalid | judged | goal | The goal names an object type that has a commonly confusable look-alike type in household scenes (e.g. butterknife vs knife, pot vs pan, mug vs cup, apple vs tomato, spray bottle vs soap bottle). |
| E-ds/s5/s5-r4 |  | supported | mechanical | - | the task type requires a clean, heat or cool state change |
| E-ds/s5/s5-r5 |  | supported | always | - | every task (stop searching once holding the goal object) |

## Appendix D. Null pass probability of the C1 gain part, per rule and design

Each cell gives: items with known movement / movers / net (items) / P(no-effect rule reaches net >= 1). Movement is measured at runs 0..GATE_RUNS-1, with 20,000 sign-flip draws (from `r2/falsepass_r2.json`).

| rule / condition | v3 trigger | all in-scope (v4 plan) | scope-filtered trigger | in-scope failures | whole check half |
|---|---|---|---|---|---|
| I-ds/s1/s1-r1 sq_person | 11 / 4 / +0.0 / 0.38 | 26 / 8 / -3.5 / 0.34 | 3 / 3 / -0.5 / 0.25 | 4 / 3 / -0.5 / 0.25 | 100 / 14 / -3.5 / 0.37 |
| I-ds/s1/s1-r2 sq_category_stated | 11 / 3 / -0.5 / 0.12 | 65 / 4 / +0.0 / 0.32 | 6 / 2 / +0.0 / 0.25 | 14 / 2 / +0.0 / 0.25 | 100 / 7 / -2.0 / 0.38 |
| I-ds/s1/s1-r4 sq_multi_constraint | 4 / 0 / +0.0 / 0.00 | 57 / 4 / -1.0 / 0.38 | 1 / 0 / +0.0 / 0.00 | 15 / 2 / -1.5 / 0.25 | 100 / 9 / +0.0 / 0.41 |
| E-ds/s1/s1-r1 sq_minimal_name | 6 / 4 / +1.5 / 0.25 | 66 / 20 / +3.5 / 0.37 | 6 / 4 / +1.5 / 0.25 | 16 / 9 / +1.5 / 0.31 | 99 / 29 / +4.5 / 0.39 |
| E-ds/s1/s1-r2 always | 6 / 1 / -0.5 / 0.00 | 99 / 26 / +7.5 / 0.38 | 6 / 1 / -0.5 / 0.00 | 27 / 5 / +0.0 / 0.38 | 99 / 26 / +7.5 / 0.38 |
| E-ds/s1/s1-r3 sq_slot | 11 / 3 / +1.0 / 0.38 | 23 / 4 / +1.5 / 0.25 | 1 / 0 / +0.0 / 0.00 | 2 / 0 / +0.0 / 0.00 | 99 / 25 / +2.0 / 0.44 |
| E-ds/s1/s1-r4 sq_official | 7 / 0 / +0.0 / 0.00 | 27 / 4 / +2.5 / 0.26 | 2 / 0 / +0.0 / 0.00 | 6 / 1 / +1.0 / 0.50 | 99 / 23 / +1.5 / 0.38 |
| E-ds/s2/s2-r2 oq_aggregate | 17 / 4 / +1.0 / 0.32 | 18 / 4 / +1.0 / 0.32 | 10 / 2 / +1.0 / 0.25 | 16 / 4 / +1.0 / 0.31 | 37 / 8 / +1.0 / 0.36 |
| E-ds/s2/s2-r3 oq_multistep | 9 / 3 / -1.0 / 0.38 | 30 / 5 / -1.0 / 0.37 | 9 / 3 / -1.0 / 0.38 | 27 / 5 / -1.0 / 0.39 | 37 / 5 / -1.0 / 0.38 |
| I-ds/s3/s3-r2 lm_strength_diff | 6 / 1 / -1.0 / 0.50 | 42 / 10 / -2.0 / 0.42 | 5 / 1 / -1.0 / 0.50 | 31 / 6 / -1.5 / 0.27 | 49 / 14 / +0.0 / 0.42 |
| E-ds/s3/s3-r2 lm_weakened | 5 / 1 / -0.5 / 0.00 | 48 / 12 / +0.5 / 0.31 | 5 / 1 / -0.5 / 0.00 | 34 / 6 / +1.5 / 0.27 | 49 / 12 / +0.5 / 0.30 |
| E-ds/s3/s3-r3 lm_strengthened | 6 / 3 / -0.5 / 0.25 | 48 / 14 / -1.0 / 0.42 | 6 / 3 / -0.5 / 0.25 | 33 / 9 / +0.5 / 0.31 | 49 / 14 / -1.0 / 0.42 |
| I-ds/s4/s4-r2 sb_key_match | 14 / 1 / +1.0 / 0.49 | 28 / 5 / -3.0 / 0.50 | 9 / 1 / +1.0 / 0.51 | 11 / 1 / +1.0 / 0.50 | 44 / 6 / -2.0 / 0.34 |
| E-ds/s4/s4-r4 sb_per_row | 15 / 3 / -1.0 / 0.50 | 27 / 4 / +0.0 / 0.31 | 9 / 1 / -1.0 / 0.50 | 16 / 2 / -2.0 / 0.25 | 45 / 8 / +0.0 / 0.36 |
| I-ds/s5/s5-r1 always | 14 / 2 / -2.0 / 0.25 | 28 / 5 / -3.0 / 0.50 | 14 / 2 / -2.0 / 0.25 | 16 / 2 / -2.0 / 0.24 | 28 / 5 / -3.0 / 0.51 |
| **mean null pass (observed passes of 15)** | 0.255 (4) | 0.362 (5) | 0.225 (3) | 0.298 (5) | 0.390 (5) |
