# E8 - Offline Skill prior distilled from the archives ("warm start")

Explorer report, 2026-10-21 (HKT). Direction E8. Serves purpose 1 (what is learnable from experience) and purpose 2
(generalisation: does what was learned from some items carry over to items it was not learned from).
All numbers below were read from the files listed in section 9; "my reading" marks a judgement, not a measurement.

## 0. Bottom line

- **A warm start distilled from archived failures is not worth it.** Measured with deepseek-v4-flash on training
  items the distiller never saw, the distilled Skill (arm D) never beat the task-card seeds (arm I):
  - SearchQA (100 fresh items x 2 runs). As the repository scorer counts: D = I exactly (171/200 each), D - I = 0.000,
    95% CI [-0.037, +0.037]. Under the task card's own metric (only the text inside the last `<answer>` tag counts):
    D drops to 144/200, D - I = -0.135 [-0.199, -0.071] (1 item up, 21 down), and D is no better than the empty
    scaffold (141/200; D - E = +0.015 [-0.070, +0.100]).
  - OfficeQA (74-item pool, two-fold cross-fitting, 1 run, 67 items completed): D 27/67, E 31/67, I 34/67;
    D - I = -0.104 [-0.226, +0.017] (5 up, 12 down, sign p = 0.14); D - E = -0.060 [-0.171, +0.052].
- **What the distilled rules look like.** All 14 kept rules use the conditional template, but the conditions are broad
  (the distiller's own median estimate: the condition holds on 50% of tasks; two rules are effectively unconditional).
  By my reading 6 of 14 restate a card-derived seed bullet, 5 refine one with a concrete action, 3 are new. Lexically
  they do not restate the short card (median containment 0.05), but they closely re-discover the v3 analyst's
  never-accepted proposals (median containment 0.36, max 0.66).
- **Mechanisms (measured).** The rules change answer FORM, not knowledge. SearchQA: the shortening and "answer the
  category" rules fix some items and break others (net 0 as scored); D omits the `<answer>` tag in 32/200 replies (I:
  0/200), and 27 of those pass only through the scorer's last-line fallback. OfficeQA: with the fold-A rules the solver
  replied with a bare `<answer>number</answer>` on 26/35 fold-B items (empty scaffold 9/35, seeds 3/35); such
  answer-only replies are rarely right.
- **New project-level finding: the archive is stale.** For the SAME request (same Skill digest, identical prompt-token
  counts on 67/67 items; for SearchQA, cal-1's request hashes byte-identical to v3's), the deepseek serving changed
  behaviour between about 2026-10-20 02:00 and 16:00: OfficeQA empty scaffold median reply 10 -> 175 tokens and pass
  rate 21.6% -> 46.3% (19 items up, 1 down); SearchQA empty scaffold median 10 -> 41 tokens and pass 74.3% -> 68.5%.
  The failures this warm start was distilled from came from a solver behaviour that no longer exists.
- **Budget.** 3,021,746 tokens in total (cap 3,000,000), all spent by the earlier E8 instance: distillation 194,566,
  SearchQA 1,424,676, OfficeQA 1,402,504. This session made no paid call; everything it added is free re-analysis.

## 1. The question

Past runs left training-side artifacts with diagnosed failures. If ONE offline distillation pass over them produced a
Skill that starts above the task card, every future chain could start from it. For purpose 1 that would show what is
learnable from experience. For purpose 2, a prior that carries to unseen items or benchmarks would be the cheapest
generalisation gain. The owner's yardstick applies: the learned text must beat a GOOD instruction (the task card), not
an empty prompt.

## 2. Provenance (who did what)

An earlier instance of this E8 exploration (scripts in `scratchpad/feas/E8/scripts/`) wrote the design, ran the
distillation and the paid evaluation on 2026-10-21 00:05-01:18 HKT, and stopped at the 3M-token cap without writing a
report. Its analysis file had been written when only 8 of the 201 OfficeQA cells existed. This session (04:40-05:30
HKT) verified every artifact and re-ran the analysis over all 801 cells. It also added free checks: the
scorer-fallback sensitivity, the cross-day drift check on OfficeQA, verification of the cross-fitting, the reply-form
mechanisms, power, the OfficeQA archive inventory, and a prepared but unlaunched follow-up arm. No API call was made in
this session.

## 3. Archive inventory: what exists and what was used

| Archive | Machine | Content relevant to E8 | Used? |
|---|---|---|---|
| v3 run `/data/coevo5-20261019-v3-run` (10-19/20) | new | chains E-ds (empty scaffold) and I-ds (seeds); s1/train SearchQA 200 items x 2 runs, s2/train OfficeQA 74 items x 2 runs; examiner diagnoses `s*/prepare/attempt-1/diagnoses.json`; 49 proposals | **Yes**: the failure evidence (every failed run diagnosed, 0 undiagnosed) |
| v1 run `/data/coevo5-20261017-run` | new | chains E-glm and I-glm (GLM-5.3 solver, thinking on) on the SAME draws; outcomes only (other taxonomy) | **Yes**, as a per-item "stronger solver correct k of 4" signal |
| v2 `/data/coevo5-20261019-v2-archive` | new | research sources (cards, LibreOffice help pages), no train cells | No (nothing to distil) |
| v8-v11 line `/root/fivebench-g-2026101*` | old | 666 SearchQA-named entries, 232 with a `panel.json`: 80 panels of 400 "development" tasks = exactly the 400 train-part items of the current 600-item pool (127 of them in v3's draw). 135 OfficeQA-named entries, 17 with a `panel.json`: every panel's pool items come from the SAME 74-item pool (72, 50 or 48 items; 3 panels hold 172 tasks, of which 48 are in the pool) | No. SearchQA: these panels cover the train part, and 60 of the 100 evaluation items are train-part, so using them would have overlapped the evaluation draw. OfficeQA: the same 74 items under older prompts and protocols, so more runs but no new items. Of the 232 + 17 inspected panel paths, 0 carried a test/final/holdout/reserve label, and only the `development` and `skill_confirmation` partitions appear |
| F study `/root/continual-fivebench-20261003-f-study` | both | SearchQA, BCB, KOR, SpreadsheetBench, ALFWorld under the 10-03 protocol; no OfficeQA | No (older protocol, other panels) |

Evidence shown to the distiller (`data/evidence/summary.json`):
- SearchQA: 200 items x 4 deepseek runs. E-ds had 297 passes and 103 failures; I-ds had 310 and 90. 65 items had at
  least one failed run; all 65 were shown, covering 193 failed runs. Codes: D1 72, D2 48, D4 26, D5 19, D3 14,
  other 8, answer_tag 3, noncompletion 3. 33 items failed all 4 runs, and GLM never solved 25 of them.
- OfficeQA fold A: 37 items, 112 failed runs, 31 items shown. Fold B: 37 items, 117 failed runs, 32 items shown. Over
  all 74 items: E-ds 30/148 pass, I-ds 37/148. 48 items failed all 4 deepseek runs, and GLM solved 31 of these at
  least once.

## 4. Design (written to `design.json` at 00:05, before any paid call)

- **Distiller.** GLM-5.3 with v3's role settings (thinking on, reasoning low, temperature 0, 16,384 max tokens). One
  call per (benchmark, fold), payload at most 200 KB. The payload holds each failed task as the solver saw it (long
  material cut), the reply, the reference, the failure code, failed-run counts, GLM's success count, the failure
  codes' meanings and counts, and 4 correct contrast replies. The instruction asks for at most 5 rules of at most 600
  characters in the template "When <observable condition>: <bounded action>; otherwise <default>", with no
  task-specific facts and no steering by answer distribution. Each rule declares its codes, 2-8 evidence ids,
  "covered by the card", "adds" and an estimated condition share. One re-ask with the validation errors was allowed;
  it was not needed (3/3 valid on the first attempt).
- **Leakage.** v3's policy, unchanged. Mechanical checks run against the benchmark's whole training pool, and any hit
  other than a single answer word drops the rule. The registered adjudicator then judges every remaining rule; a "yes"
  or an invalid reply drops it.
- **Arms.**
  - E: empty scaffold (digest cc5165..., = v3 E-ds step 0).
  - I: the five task-card seeds (digest ee9b73..., = v3 I-ds step 0; 12,681 bytes).
  - D: scaffold + the kept SearchQA rules + the kept OfficeQA rules of one fold (D_A 4,539 bytes, D_B 4,268 bytes).
- **Evaluation items.** Training pool only: `data.pool` loads only the historical train and val parts and never the
  test part.
  - SearchQA: 100 items drawn by seed from the 400 pool items OUTSIDE v3's 200-item evidence draw (60 train-part, 40
    val-part). 0 of them are evidence items (verified on the cells). D uses D_A; its SearchQA rules are the same in
    D_A and D_B.
  - OfficeQA: the pool has only 74 items, so "100 items" is impossible. A seeded split gives folds A and B (37 + 37),
    then cross-fitting: D on fold-A items uses D_B (rules from fold-B failures) and vice versa. Verified on the cells:
    32 D_B cells on fold A, 35 D_A cells on fold B.
- **Solver.** deepseek-v4-flash through the frozen backends (`contract-first-v2`, temperature 0, 32,768 max tokens,
  thinking disabled), with the v3 decision table and at most 2 resends of undelivered replies. Arms are interleaved
  per item in rotating order; 6 workers; a global 3M-token cap.
- **Runs.** SearchQA: 2 runs. OfficeQA: 1 run. This deviates from the assignment's 2 runs and was chosen up front,
  because an OfficeQA cell costs about 2.6x a SearchQA cell. Even so, the cap stopped OfficeQA at 201/222 cells. The 7
  items not run in any arm are UID0030, UID0065, UID0070, UID0141, UID0150, UID0213 and UID0240.
- **Analysis (pre-registered).** Paired per-item mean differences over items valid in both arms; t and bootstrap 95%
  CIs (10,000 resamples, seed 20261017); exact two-sided sign test. Unknowns are excluded, with "unknown counted as
  fail" as a sensitivity; there were 0 unknowns, so both readings coincide. Added in this session (post hoc, labelled
  as a sensitivity): SearchQA scored with the card's tag rule.

## 5. Results

### 5.1 The distilled rules

15 rules were proposed (5 per job). 1 was dropped by the mechanical leakage check (OfficeQA-B #3: an 8-gram shared
with a pool item). 14 were kept, all adjudicated "no". The kept rules are 290-484 characters long.

| # | Rule (abridged) | codes | claimed share | vs the seed bullets (my reading) |
|---|---|---|---|---|
| SQ1 | When the draft is a full official name, has middle names/initials or an added category word: shorten it to the shortest common form (e.g. surname only) | D1 | 70% | refines seed 6 ("minimal entity"); conflicts with seed 4 ("prefer the verbatim snippet form") |
| SQ2 | When the draft is a nickname or a shortened/reordered form of the snippets' name: use the fuller canonical form the snippets give | D2 | 40% | restates seed 4 (+ seed 10) |
| SQ3 | When the question is only a name, title, quote or list: answer the category or shared attribute it points to | D5 | 20% | new |
| SQ4 | When two or more candidates fit part of the clue: check every clause and answer the one that satisfies all | D4 | 30% | restates seed 9 |
| SQ5 | When the draft has parentheses, an alias, an explanation or alternatives: put just one short answer inside `<answer>` | D3, tag | 25% | restates seeds 6 and 12 and the card's scoring sentence |
| OA1 | When a calendar-year question meets a table with fiscal-year and monthly rows: sum the monthly rows, never use the FY row, check a June row that repeats the FY value | D1, D2 | 45% | refines seed 2 (period labels) |
| OA2 | When the table is cumulative: compute changes as differences of period-end levels | D2, D1 | 25% | new |
| OA3 | When the question states an exact statistical definition: follow it literally | D2 | 50% | new (seed 1 is generic) |
| OA4 | When the computation has several steps: keep full precision, round only at the end, re-check once | D3 | 60% | refines seed 6 |
| OA5 | When writing the final answer: match format, units, scale and sign; "output only the requested values ...; otherwise output the bare value" | D4, D1 | 50% (condition always true) | restates seeds 4, 7, 10 and 12 |
| OB1 | When the question specifies an output format: re-read it, then put exactly one value in that form inside `<answer>` | D4 | 95% | restates seeds 10-12 and the card |
| OB2 | When a computed statistic is asked for: first write one sentence naming the exact quantity (percent vs points, sample vs population, ...) | D2 | 70% | refines seed 1 |
| OB4 | When specific months, years or a fiscal range are named: match the period kind of the rows exactly | D1, D2 | 65% | restates seeds 2 and 8 |
| OB5 | When the computation is multi-step (logs, roots, ...): keep full precision, round at the end, redo the last operation | D3 | 50% | refines seed 6 (same as OA4) |

- **Conditional?** In syntax, yes: 15/15 start with When/If and contain "otherwise". In substance, weakly. The
  "otherwise" branches are defaults ("keep the draft", "proceed directly"). The claimed condition shares have a median
  of 50% (range 20-95%), and OA5 and OB1 are effectively unconditional.
- **Restating the card?** The card (754 and 1,052 characters) only describes input and scoring, so lexical overlap is
  low: the median containment of a rule's content words in its closest card sentence is 0.05, and in its closest seed
  bullet 0.13. By my semantic reading, 6 rules restate a seed bullet, 5 refine one, and 3 are new (SQ3, OA2, OA3). The
  distiller marked "covered by the card: none" for 11 of 14 rules: it saw the card, not the seeds.
- **Re-discovery.** The closest v3 proposal (from v3's analyst, either chain; none of them accepted) has a median
  containment of 0.36 (max 0.66, OA5 vs v3 E-ds s2-r4). The offline pass produced the same rule families as the
  online analyst.
- **Stability.** The two OfficeQA folds, distilled independently from disjoint halves, produced the same theme for 4 of
  5 rules: period matching, format check, multi-step precision, statistic definition. Their best-match Jaccard is
  0.22-0.36, against 0.02 between unrelated SearchQA and OfficeQA rules. Only OA2 (cumulative tables) is
  fold-specific. The rules are generic, not memorised items.
- **Consistency flags** (recorded, but voiding nothing in E8): 5 of the 14 kept rules cite evidence whose codes do not
  include the rule's codes. v3's prepare rule ("inconsistent => void") would have voided them.

### 5.2 SearchQA (100 fresh training items x 2 runs; 600 cells; 0 unknown, 0 truncated, 5 resends)

| Arm | pass, as scored | pass, card tag rule | untagged replies (of which passed via fallback) | tokens/cell |
|---|---|---|---|---|
| E empty scaffold | 144/200 (72.0%) | 141/200 (70.5%) | 29 (3) | 1,246 |
| I task-card seeds | 171/200 (85.5%) | 171/200 (85.5%) | 0 (0) | 3,825 |
| D distilled | 171/200 (85.5%) | 144/200 (72.0%) | 32 (27) | 2,053 |

Paired over the 100 items (per-item mean of 2 runs). Each cell gives: mean [t 95% CI] (bootstrap CI);
items up/down/tied; sign-test p.

| Pair | as scored | card tag rule |
|---|---|---|
| D - I | 0.000 [-0.037, +0.037] (-0.035, +0.040); 2/3/95; p = 1.00 | -0.135 [-0.199, -0.071] (-0.200, -0.075); 1/21/78; p < 0.0001 |
| D - E | +0.135 [+0.074, +0.196] (+0.075, +0.200); 20/1/79; p < 0.0001 | +0.015 [-0.070, +0.100] (-0.070, +0.100); 18/16/66; p = 0.86 |
| I - E | +0.135 [+0.075, +0.195] (+0.080, +0.195); 21/1/78; p < 0.0001 | +0.150 [+0.089, +0.211] (+0.095, +0.210); 24/1/75; p < 0.0001 |

- **The scorer.** `skillopt/envs/searchqa/evaluator.extract_answer` takes the last `<answer>` tag, and otherwise the
  reply's last line. The card says only the tag counts. This is the v4 audit defect "SearchQA format check vs scorer
  fallback". D's parity with I rests on 27 untagged passes.
- **Where D and I differ** (5 items), the rules' actions are visible:
  - SQ3 turned the reference "Billy Bob Thornton" into "Billy Bob Thornton's wives", in both runs.
  - SQ1 cut "Lord Robert Baden-Powell" to "Baden-Powell" in one run.
  - Shortening rescued "July 14" (I answered "July 14, 1789") and "antiperspirant" (an untagged reply).
- **Failure kinds, as scored.** A form near-miss means the reference is contained in the answer or vice versa.
  - E: 56 fails = 40 form near-misses + 11 wrong + 5 partial.
  - I: 29 fails = 9 + 16 + 4.
  - D: 29 fails = 13 + 12 + 4.
  Both instructions gain by fixing answer FORM.
- **Same-day run-to-run disagreement** for the same text: E 14/100 items, I 1/100, D 1/100. At temperature 0 the
  instructed arms are nearly deterministic within a day.

### 5.3 OfficeQA (74-item pool; run 0; 67 items completed; D cross-fitted)

Each pair cell gives: mean [t 95% CI]; items up/down; sign-test p.

| Items | E | I | D | D - I | D - E | I - E |
|---|---|---|---|---|---|---|
| all 67 | 31 (46.3%) | 34 (50.7%) | 27 (40.3%) | -0.104 [-0.226, +0.017]; 5/12; p = 0.14 | -0.060 [-0.171, +0.052]; 5/9; p = 0.42 | +0.045 [-0.045, +0.134]; 6/3; p = 0.51 |
| fold A (32; D = D_B) | 17 | 18 | 17 | -0.031 [-0.225, +0.163]; 4/5; p = 1.0 | 0.000; 4/4 | +0.031; 4/3 |
| fold B (35; D = D_A) | 14 | 16 | 10 | -0.171 [-0.327, -0.016]; 1/7; p = 0.070 | -0.114 [-0.253, +0.024]; 1/5; p = 0.22 | +0.057; 2/0 |

- **Bootstrap CIs** (all 67 items): D - I (-0.224, +0.015); D - E (-0.164, +0.045); I - E (-0.045, +0.134). On fold B,
  D - I is (-0.314, -0.029).
- **Unknowns and truncations.** 0 unknowns. Truncations at 32,768 tokens (scored as fail): E 2, I 6, D 1.
- **Mechanism: answer-only replies.**
  - Replies that start with `<answer>`, i.e. with no visible working: on fold B, D 26/35 vs E 9/35 vs I 3/35; on fold
    A, D 4/32, E 8/32, I 6/32.
  - Replies of at most 30 completion tokens pass 6/30 (D), 3/15 (E) and 1/8 (I). Longer replies pass 21/37, 28/52
    and 33/59.
  - On 5 fold-B items, D's bare answer was wrong while both E and I were right. Of D's 12 losses to I, 7 were bare
    10-11-token answers.
  - Failure kinds: D 33 far misses, 6 close misses (relative error at most 1%), 1 truncation. E: 19 far, 14 close,
    1 without a number, 2 truncations. I: 15 far, 12 close, 6 truncations.
  - The likely trigger is the fold-A rule OA5 ("output only the requested values ...; otherwise output the bare
    value"). D_B's format rule confines the bare value to the inside of the tag, and its OB2 asks for a written
    sentence. Per-rule attribution would need ablation arms, which were not run.
- **Where D loses.** On the 25 items that v3 solved at least once, D passes 16, while E and I pass 20 each.
- **Cost:** E 5,334, I 9,944 and D 5,655 tokens per cell.

### 5.4 Cross-day drift of the solver (measured; free)

| Comparison (same items, same Skill digest) | earlier | later | per-item change |
|---|---|---|---|
| OfficeQA empty scaffold: v3 E-ds (10-20 02:17-02:19) -> E8 E (10-21 00:37-01:18); 67 items, prompt tokens identical on 67/67 | 29/134 = 21.6%; median reply 10 tokens; 90.3% of replies at most 30 tokens | 31/67 = 46.3%; median 175; 22.4% | +0.246; 19 items up, 1 down. v3's two same-day runs disagreed on 5/67 |
| OfficeQA seeds: v3 I-ds (10-20 01:03-01:07) -> E8 I | 35/134 = 26.1%; median 10; 76.9% | 34/67 = 50.7%; median 267; 11.9% | +0.246; 20 up, 3 down. v3 same-day disagreement 7/67 |
| SearchQA empty scaffold: v3 E-ds (10-19 23:26 to 10-20 00:18) -> cal-1 parent:A/B (10-20 16:07-18:13); request hashes byte-identical for 1,981/1,981 cal-1 sends checked | 297/400 = 74.3%; median 10 | 436/637 = 68.5% (A), 453/664 = 68.2% (B); median 41 | -0.060; 35 items worse, 12 better. A vs B on the same day: -0.003, 16/19 |
| SearchQA seeds: v3 I-ds -> cal-1 ids-full | 310/400 = 77.5%; median 62 | 503/656 = 76.7%; median 61 | -0.005; 11 better, 12 worse (no change) |

E8's direct client and v3's endpoint wrap the same `scripts/weak_solver_probe.Client`. Its request body is model,
system + user messages, max_tokens, temperature 0 and thinking disabled. The backends, protocol, outcomes, data, skill,
leakage and cells modules of `/data/skillopt-work` are byte-identical to the frozen v3 snapshot, and reasoning_chars = 0
in every cell. The change is therefore server-side: since roughly the afternoon of 2026-10-20, the serving writes
visible working by default unless the Skill constrains the reply. Consequences:

- Of the 67 E8 OfficeQA items, 42 failed all 4 v3 runs ("dead" in v3). In E8 at least one arm solves 18 of them
  (E 11, I 14, D 11).
- Comparisons within E8 are unaffected, because all arms were interleaved in one window. Comparisons across days
  (archive vs now, v3 vs later runs) are not valid.

### 5.5 Detectable effects (80% power, two-sided 5%, from the observed per-item SDs)

| Pair | n | SD | detectable effect at n | items needed for 5 points | items needed for 3 points |
|---|---|---|---|---|---|
| SearchQA D-I (as scored) | 100 | 0.188 | 5.3 points | 111 | 309 |
| SearchQA D-E | 100 | 0.309 | 8.7 | 299 | 831 |
| SearchQA I-E | 100 | 0.300 | 8.4 | 284 | 787 |
| OfficeQA D-I (1 run) | 67 | 0.497 | 17.0 | 774 | 2,150 |
| OfficeQA I-E (1 run) | 67 | 0.367 | 12.5 | 422 | 1,172 |

Same-day run-to-run noise is small for instructed arms (1 of 100 SearchQA items flips between runs), so extra runs buy
little and the number of items is the binding constraint. OfficeQA's whole training pool (74 items) cannot resolve a
warm-start effect below about 15 points.

### 5.6 Cost

Total: 3,021,746 tokens.
- Distillation: 194,566 (3 GLM calls with 187,783 tokens, plus 14 adjudications with 6,783).
- SearchQA: 600 cells, 1,424,676 (E 249,111, I 764,920, D 410,645).
- OfficeQA: 201 cells, 1,402,504 (E 357,364, I 666,227, D 378,913).

About 70 minutes of running in total. The distillation itself is cheap (about 0.2M tokens for two benchmarks); the
evaluation is what costs.

## 6. Conclusions

1. **Is a warm start worth it? No** (measured on two benchmarks). Replacing the card seeds with distilled rules gives
   at best parity: on SearchQA, and only through a scorer fallback. Under the card's metric it is a loss on SearchQA
   (-13.5 points), and on OfficeQA it is a loss too (-10.4 points, CI up to +1.7). Against the empty scaffold, the
   distilled rules reproduce the seeds' SearchQA form gain only as scored, and do not help on OfficeQA. The one
   positive: D matches I's as-scored SearchQA accuracy at 54% of I's tokens per cell (2,053 vs 3,825). That is an
   efficiency result, not an accuracy result, and it disappears under the tag rule.
2. **What do the rules look like?** Conditional in syntax, broad in substance. They are mostly answer-form and
   calculation-hygiene advice that the card-derived seeds already contain, and nearly the same families as the v3
   analyst's rejected proposals. They are stable across independent halves, so they are generic rather than memorised.
   The genuinely new ones (3 of 14) are narrow, and at least one (SQ3) misfires on fresh items.
3. **Purpose 1 (what is learnable).** One offline pass over about 100 diagnosed failures learns essentially what a
   careful reading of the card already yields. The learnable surplus over the card is invisible at 5-point resolution
   on SearchQA and negative on OfficeQA. This agrees with v3 (0 accepted rules) and with v8-v11 (+3 to +5 points on
   top of a good instruction, not significant).
4. **Purpose 2 (generalisation).** E8 tests transfer across items within one benchmark. The distilled Skill did not
   transfer to fresh items of its own benchmark better than the card, so nothing suggests it would transfer across
   benchmarks.
5. **The archive is not a durable prior.** The solver behaviour it recorded changed within a day (section 5.4). Any
   offline prior must be re-validated against current behaviour, and rules that constrain the reply form interact
   strongly with the solver's verbosity.

## 7. Risks and validity threats

- **OfficeQA is underpowered.** One run on 67/74 items gives wide CIs. The fold-B harm excludes 0 by both t and
  bootstrap, but it is one subgroup of a 2-fold split with sign p = 0.07: weak evidence of harm, not established. The
  overall direction (D at or below I in both folds) is consistent but not significant.
- **The tag-rule reading is post hoc** (not pre-registered), but it applies the card's own stated metric. Both
  readings are reported.
- **One distillation per job.** The distiller was not re-sampled. A different prompt, more evidence or several drafts
  might produce better rules, so the result is about this procedure, not about every possible offline prior.
- **The distiller saw the card, not the seeds.** A distiller shown the seeds might avoid restating them.
- **Drift and comparability.** The arms were interleaved within one window, so the drift does not bias the paired
  comparisons. E8 numbers are, however, not comparable to v3 numbers.
- **The rule-to-seed mapping is my reading** (a judgement), supported by the lexical numbers.
- **The SearchQA "val"-part evaluation items** belong to the registered training pool (`data.pool` = historical train
  + val parts). No test item, test panel or evaluation directory was read.

## 8. Recommendation

1. Start v5 chains from the task-card seeds (I), not from an archive-distilled Skill.
2. Keep the offline distiller at most as a cheap proposal source. Treat its output as one batch of candidate rules,
   placed ON TOP of the seeds, that must pass the same acceptance test as any rule (cross-ref D1). Distil from failures
   of the CURRENT solver behaviour, re-measured the same week. Guard format and verbosity: compare the tag rate and the
   reply-length shift against the parent as a mandatory check.
3. Use the archives for two things:
   - a "known proposals" list that stops the analyst re-proposing families already tried (E8 re-discovered them);
   - item difficulty, but only after re-measurement: 18 of the 42 OfficeQA items that were "dead" in v3 are solved
     now.
4. Fix the SearchQA tag fallback before any comparison (v4 audit item). Until it is fixed, report both metrics.
5. Add a standing drift canary (cross-ref D5, D8, D11): a fixed small panel with fixed texts, re-run at the start of
   every session or step, comparing reply length and pass rate. Never compare arms measured on different days.
6. OfficeQA effects below about 15 points are not measurable on its 74-item pool, so OfficeQA claims need more items
   (cross-ref D6, D12).

**Prepared, not launched** (the budget is exhausted). Arm ID = seeds + distilled rules, compared with I re-measured
interleaved, in `/data/feasibility/E8/scripts2/e8_arm_id.py`. Its free compose step is tested: ID_A 16,627 bytes,
ID_B 16,356 bytes, both within the 20,000-byte limit.
- SearchQA (400 cells, about 1.7M tokens):
  `ssh -o BatchMode=yes <datatools-login> "bash -ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/E8 && nohup /root/continual-alf-prep-20260928/env/bin/python scripts2/e8_arm_id.py evaluate --bench searchqa --runs 0,1 --cap 1900000 > followup-id/eval_searchqa.log 2>&1 &'"`
- OfficeQA (296 cells, about 3.0M tokens): the same command with `--bench officeqa --cap 3200000` and the log
  `followup-id/eval_officeqa.log`.
- Then run `scripts2/e8_arm_id.py analyse`.
- To complete the original OfficeQA run 0 (21 cells, about 0.15M tokens), run
  `scripts/e8_pipeline.py evaluate --bench officeqa --runs 0 --cap 3200000`. E, I and D are interleaved per item, so
  the paired comparison stays valid even if the serving drifts again.

## 9. Files

- Mac scratchpad `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E8/`:
  - `report.md` (this file).
  - `data/`: design.json; skills.json; distill/*/record.json and ledger-000853.json; evidence/summary.json;
    results.json (all 801 cells) and results-0037-searchqa-only.json (the earlier, partial one); mechanism.json;
    drift_officeqa.json; followup.json; strict_searchqa.json; rules_analysis.json; followup-id/skills.json;
    old_drift_check.json; old_drift_check_requests.json; oq_inventory_old.json; cap_stop_officeqa.json.
  - `scripts/` (earlier instance): e8_pipeline.py, e8_evidence.py, e8_mechanism.py, e8_rules.py, drift_check_old.py,
    drift_check_requests.py, v11_overlap_old.py.
  - `scripts2/` (this session): e8_drift.py, e8_followup.py, e8_strict.py, e8_arm_id.py, oq_inventory_old.py.
- New machine `/data/feasibility/E8/`: all of the above, plus cells/ (801 cell records with replies),
  evidence/{searchqa,officeqa}.json, distill payloads, logs, and this report.
- Old machine `/data/feasibility-scratch/E8/`: drift_check*.json, v11_overlap.json, oq_inventory.json and their
  scripts.

## 10. References

- Project registrations: `docs/handoff/coevo5-registration-v3-delta-20261019.md`,
  `docs/handoff/cal1-registration-20261020.md` (read, not edited).
- Code: `skillopt/coevo5/{protocol,data,leakage,outcomes,skill,cells,calls}.py`, `skillopt/continual_eval/backends.py`,
  `skillopt/envs/searchqa/evaluator.py` and `scripts/weak_solver_probe.py` in `/data/skillopt-work`. The modules used
  are byte-identical to `/data/coevo5-20261019-v3-source-f`.
- Zhao, A. et al., "ExpeL: LLM Agents Are Experiential Learners", AAAI 2024, vol. 38, pp. 19632-19642
  (https://ojs.aaai.org/index.php/AAAI/article/view/29936; arXiv 2308.10144). The closest precedent: it pools
  successes and failures, abstracts cross-task insights through ADD/UPVOTE/DOWNVOTE/EDIT operations, and applies them
  at evaluation. E8 differs in testing against a strong instruction baseline (the card seeds) rather than an
  uninstructed agent.
