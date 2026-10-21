# E5 -- Psychometrics of items: difficulty, discrimination, transfer-predictiveness

Explorer report, direction E5 of the second feasibility batch. Retrospective work 2026-10-20 19:20 to 2026-10-21
01:08; the session stopped before the pilot's second half and the write-up were finished. A resumed session
(2026-10-21 04:41-05:20) re-verified the headline numbers with independent code, re-checked the literature, ran the
missing pilot cells and completed this report.

**Purposes served.** Both. Purpose 1 (co-evolution: the verification side must generate and select test items that
measure what a Skill change really does, so that what it feeds back is learnable) needs an item-selection rule and a
validity test for generated items. Purpose 2 (the metric is generalisation: evolve on one benchmark, evaluate on the
others) needs panels whose numbers generalise beyond the panel's own items, at a known item cost. Each proposal below
says which purpose it serves.

Labels: **[measured]** computed in this exploration from cells or from the paid pilot, with denominators;
**[verified]** read in the code, a registration document or the cited paper; **[estimate]** my projection;
**[claim]** what a paper reports, not reproduced here.

Hard rules kept. No test/holdout pool was read, listed or copied. Only these were used: the registered training pools
(`data.pool` = historical train + val parts; it refuses test ids by construction, verified in the code), the cal-1
cells, the v3 non-evaluation cells (train, screen, confirm), and the 10/15-16 probe records (`skill_confirmation`,
`train` and `val` labels only). The `-final` probe directory was not opened. No credential was printed or copied. No
repository file and no completed run directory was written. Scripts and outputs are under `/data/feasibility/E5/v2/` on
the new machine and `/data/feasibility-scratch/E5/` on the old one (for the cal-1 and probe extraction, whose data
lived only there).

Cross-references (batch 1, not duplicated here): D5 (noise floor, nondeterminism), D8 (statistical protocol:
text x item idiosyncrasy, between-session drift, dead items), D6 (generated tasks with guaranteed answers), D12
(cross-domain transfer measurement). Batch-2 siblings with paid transfer pilots (E2 placement, E4 instruction-transfer
matrix) cover the cross-benchmark fixtures; E5 stays on the item level.

---

## 0. Bottom line

1. **A Skill text mostly reshuffles items; it barely shifts the mean.** [measured, cal-1, 11 arms x 200 items x 4 runs]
   On the probability scale the variance splits into item 63.8 %, text main effect 1.3 %, item x text 11.6 % and run
   noise 23.2 %. The SD of the text main effects is 5.4 points, the SD of item x text effects 15.9 points. Every text,
   placebos included, has a reproducible item-level pattern (split-half r 0.21-0.73 against a null 95th percentile of
   0.19-0.24). The identical text in two arms gives r = -0.25 and a true item-effect SD of 0.000.
2. **Gains and harms live in different items, and a cheap parent property predicts where.** [measured] Strata come
   from the scaffold's own runs in independent sessions: always-fail 37, mixed 52 and always-pass 111 items. The
   ids-full gain is +3.5 / +15.1 / -0.9 net items across them. The placebo control:3 is -0.25 / -5.4 / -15.1. The v3
   candidate rule is +3.75 / +2.0 / -12.0. The parent's p(1-p) predicts which items respond to the task-card text,
   with AUC 0.85 [0.76, 0.93] (27 responders). The parent pass rate predicts harm susceptibility only weakly (AUC 0.63).
   Item text features are weak at best: shorter gold answers mark responders (AUC 0.64 when inverted); the other
   text features sit at about 0.5.
3. **IRT-style compression does not fit Skill-text contrasts.** [measured] Item x text interaction is 72 % of the
   excess text deviance (74 % with 16 texts). All 9 of 9 residual dimensions exceed the null. 2PL slopes have split-half
   reliability 0.41 and item-rest correlations 0.33. In the panel simulation, p-IRT gave no gain over random. Anchor
   points helped only for texts that were part of their calibration; on new texts they were biased by -2.5 to +2.6
   points. tinyBenchmarks, metabench and PromptEval [verified] assume a low-dimensional model or no prompt x example
   interaction, which these data violate.
4. **What does work is model-free.** [measured, retrospective]
   - Stratify on the parent stratum and sample with Neyman allocation and population weights. This is unbiased and
     cuts RMSE about 10 %: Neyman n = 60 is about as good as random n = 70.
   - Drop only items that are dead under every calibration text over many runs. The 19 items that failed in all of
     about 28 runs under all 9 texts carry about 0 net. Dropping them is safe.
   - Never drop always-pass items. The 75 always-pass items carry the harm (control:3 -5.0, cand -2.8 net items).
     Removing them makes harmful texts look 1.3-2.6 points better.
   - Never select "the most movable items". That shifts the estimand: ids-full reads +7 points too high at n = 60.
5. **For a generalisation claim, items beat runs.** [measured D-study] The true item-effect SD tau is 0.12-0.28
   (SearchQA texts) and 0.12-0.22 (ids-full minus scaffold on the other four benchmarks). Take a 5-point effect at 80 %
   power. ids-full needs 374 items at 2 runs for the population (unseen-item) estimand, 122 for the fixed-panel
   estimand, and 251 even with infinitely many runs. At the current panel sizes with 2 runs, the minimum effect
   detectable at 80 % power is:

   | benchmark (panel items) | population estimand | fixed panel |
   |---|---|---|
   | SearchQA (200) | 6.8 points | 3.9 points |
   | LiveMath (100) | 8.2 | 7.3 |
   | SpreadsheetBench (91) | 9.1 | 8.4 |
   | OfficeQA (74) | 9.6 | 7.9 |
   | ALFWorld (57) | 12.2 | 9.1 |

   tau is the ids-full one. The learned-rule effects seen so far (+3 to +5 points) are below every population figure.
6. **Generated items are not yet valid for fine contrasts.** [measured, OfficeQA probes] Over 24 contrasts, most of
   them Skill-vs-empty contrasts of +16 to +30 points, generated items agree with real ones (r = 0.93). They read
   +7.0 points higher, though. On the 10 learning-relevant
   contrasts (learned Skill minus bzero) the correlation is -0.24 and the gap is +5.3 points. Selecting generated items
   by GLM-side calibration did not shrink the gap (mean |gap| 4.4-5.5 vs 4.5 points). Item movability carries over
   poorly across solver models (r 0.02-0.31). The generated SearchQA panel (b06) is at ceiling: 112 of 168 items pass
   every deepseek cell.
7. **Transfer-predictiveness is measurable only at the family or stratum level, not per item.** The item-level
   version would be the correlation over calibration texts between an item's delta and the pool delta. It has
   reliability 0.33 with 16 texts. I define a family-level score (TPS-F) and a cross-benchmark variant that need only
   training pools. They need a calibration fixture of about 10 texts on the real training pool. A simulation on real
   items calibrates the bar. A perfectly valid 100-item family, checked with the 9 cal-1 texts, scores TPS-F >= 0.83
   in 95 % of draws, with bias within +-4 points in 90 %. Checking only small-effect texts cannot certify a family
   (5th percentile 0.46).
8. **Pilot E5-P1** [measured]. Paid, pre-registered; 180 never-used SearchQA training items, 1,800 cells, 3.24M
   tokens.
   - **Generalisation replicated.** ids-full minus scaffold is +8.89 points [4.44, 13.06] on fresh items vs +8.88 on
     the focal panel (z = 0.005). control:3 is -11.39 (focal -10.38). cand is -8.61 [-14.2, -3.1] (focal -3.12, not
     significant).
   - **Harm location replicated.** Both harmful texts lose 16.5-17.7 points on the pre-screen always-pass items (CIs
     below 0).
   - **Neyman allocation replicated.** On the 2-run pre-screen strata its RMSE ratio is 0.926 at n = 60 (predicted
     0.94).
   - **Not replicated: the 2-run "mixed" class.** It does not mark responders: AUC 0.51 [0.47, 0.57], predicted 0.64.
     The ids-full gain sits in the 2-run always-fail class (12.5 of 16 net items), so a 2-run pre-screen must never
     be used to drop items: dropping them removes 78 % of the gain. 20 of 73 detail statistics fall outside their
     focal ranges.
   - **Timing deviation, exploratory.** The second half of phase B ran 3.5 h after the pre-screen because of a session
     interruption. No serving drift appeared (paired scaffold offsets -0.6 and +0.6 points), and both halves gave the
     same ids-full effect (+8.89).

Feasibility: **medium**.
- The panel rules (stratify, Neyman, dead-item rule, keep always-pass, items over runs) cost nothing extra. The
  pipeline's train unit already runs the parent on every focal item.
- Item-level transfer-predictive selection is not feasible with current data.
- Generated items need a criterion-validation gate before they can carry fine contrasts.
- The pilot confirmed the zero-cost rules prospectively. The exception: a 2-run pre-screen does not isolate the
  stochastic stratum; it isolates "not always-pass".

---

## 1. Data, identity and denominators

| Source | Content | Cells (denominator) |
|---|---|---|
| cal-1 (old machine, `/data/coevo5-20261020-cal1`) | 11 arms x 200 focal SearchQA items x 4 runs, 2026-10-20 16:07-19:52 | 8,800 (8,785 scored, 15 unknown) |
| cal-1 pre-round | parent:A x 2 runs on the same items, 15:59-16:03 | 400 |
| v3 run (new machine) | E-ds and I-ds train/screen/confirm units, s1-s5, all five benchmarks | SearchQA 6,819 on the focal items; other benchmarks per section 3 |
| 10/15-16 solver-strength probes | OfficeQA 124 generated (`skill_confirmation`) + 74 real (50 train + 24 val); SearchQA 168 generated; deepseek, GLM-5.3, GLM-5.3-flash, GLM-4-flash | 15,096 |
| E5-P1 pilot (this work) | 180 fresh SearchQA training items | section 7 |

Final tokens per cal-1 arm (pass / fail / unknown out of 800):

| arm | pass | fail | unknown |
|---|---|---|---|
| parent:A | 543 | 255 | 2 |
| parent:B | 549 | 249 | 2 |
| ids-full | 618 | 181 | 1 |
| seed-only | 614 | 183 | 3 |
| seed-rule | 546 | 251 | 3 |
| seed-rule3 | 519 | 280 | 1 |
| cand | 522 | 275 | 3 |
| control:1 | 515 | 285 | 0 |
| control:2 | 572 | 228 | 0 |
| control:3 | 465 | 335 | 0 |
| control:4 | 545 | 255 | 0 |

The tokens are the unit record's authority (`result.tokens`). A later attempt's verdict replaces an earlier one, and 0
mismatches were found.

Identity [measured]:
- **Respondent.** The Skill text, identified by the cell `skill_sha256`. The same text has the same hash in cal-1 and
  in v3.
- **Request bytes.** Identical across sessions. Every focal item has exactly 1 distinct request hash per text (200/200
  items for the scaffold and for ids-full).
- **Pilot texts.** Byte-identical to cal-1: the digest of all 4 texts and the request hash on 3 focal items per text
  were checked before any paid call (16/16 checks true).

Training pool [verified, `skillopt/coevo5/data.py`, registration 10/16 section 2]:
- 600 SearchQA items (historical train 400 + val 200).
- Focal 200 = 127 train-part + 73 val-part; the remaining 400 = 273 + 127.
- The 60 regression items: 29 inside the focal set, 31 outside.

## 2. SearchQA item statistics (200 stage-1 focal items)

### 2.1 Difficulty [measured]

Scaffold, pooled over every session (15-26 runs per item, median 16): pass rate 0.680. 35 items never pass, 99 always
pass, 66 are mixed (54 with 0.1 < p < 0.9). ids-full, pooled (median 8 runs): 0.757; 31 never, 139 always, 30 mixed. The
classical difficulty distribution is therefore strongly bimodal. 67 % of the items are constant under the parent.

### 2.2 Same text across sessions [measured]

Item-level agreement of the same text is high:
- parent:A vs parent:B (same round, 4 vs 4 runs): Pearson 0.945, 36 items differ, 0 items with Fisher p < 0.05.
- Scaffold cal-1 vs v3: r = 0.906.
- ids-full cal-1 vs v3: r = 0.937 (24 items differ, 0 significant).

Session offsets, scaffold vs cal-1, paired over items:

| session | offset | 95 % CI | items up / down | p |
|---|---|---|---|---|
| v3 E-ds s1 train (2026-10-20 00:07-00:18) | +5.75 points | [1.9, 9.6] | 44 / 15 | 0.004 |
| v3 screen | +0.13 | | | |
| v3 confirm | +1.5 | | | |
| cal1-pre | -1.0 | | | |

The request bytes are identical, so the train-session offset is serving-side drift; D8 reported the same. Inside cal-1
there is also a run-half offset: runs {0,1} vs {2,3} differ by -0.8 to -3.5 points depending on the text. It sets the
floor of the "independent" panel mode in 2.9.

The ids-full item delta (ids minus scaffold) correlates across sessions (cal-1 vs v3) at r = 0.723 [0.631, 0.803].

### 2.3 Variance components (G-theory on the probability scale, cal-1) [measured]

| set | item | text | item x text | run noise |
|---|---|---|---|---|
| parent:A vs parent:B (identical text) | 75 % | 0 % | 0 % | 25 % |
| all 11 arms | 63.8 % | 1.3 % | 11.6 % | 23.2 % |
| the 4 placebos + scaffold | | 0.9 % | 6.3 % | |

SD of text main effects 5.4 points; SD of item x text 15.9 points. The identical-text pair is the sanity check (no text
and no interaction variance).

### 2.4 Item-level structure of each contrast (cal-1, text 4 runs vs scaffold A+B 8 runs) [measured]

| text | mean delta | net items | items up / down | tau (true item-effect SD) | split-half r of item deltas (2-run halves) [95 % CI] | Spearman-Brown, 4 runs |
|---|---|---|---|---|---|---|
| ids-full | +8.87 | +17.75 | 52 / 15 | 0.283 | 0.734 [0.607, 0.838] | 0.847 |
| seed-only | +8.46 | +16.92 | 52 / 11 | 0.236 | 0.668 [0.530, 0.783] | 0.801 |
| seed-rule | -0.08 | -0.17 | 30 / 31 | 0.192 | 0.459 [0.211, 0.652] | 0.629 |
| seed-rule3 | -3.50 | -7.0 | 27 / 43 | 0.198 | 0.460 [0.305, 0.596] | 0.630 |
| cand (v3 E-ds s1-r1) | -3.12 | -6.25 | 40 / 47 | 0.277 | 0.612 [0.483, 0.716] | 0.759 |
| control:1 | -4.12 | -8.25 | 19 / 39 | 0.123 | 0.212 [-0.032, 0.445], p = 0.057 vs null | 0.350 |
| control:2 | +3.00 | +6.0 | 41 / 19 | 0.147 | 0.473 [0.310, 0.614] | 0.642 |
| control:3 | -10.38 | -20.75 | 18 / 64 | 0.207 | 0.489 [0.339, 0.626] | 0.657 |
| control:4 | -0.38 | -0.75 | 29 / 27 | 0.162 | 0.567 [0.328, 0.738] | 0.724 |
| parent:B (null, same text) | +0.75 | +1.5 | | 0.000 | -0.246 [-0.476, 0.030] | -- |

The parametric i.i.d. null for the split-half r centres at about 0, with 95th percentile 0.19-0.24. A random re-split
of fixed data is not a valid null: it centres at -0.164 because of the induced negative dependence. The Spearman-Brown
4-run reliability of the ids-full pattern is 0.847. A placebo with zero net (control:4, -0.4 points) still has a
reproducible item pattern (0.567). "A text = a reproducible reshuffle + a small net shift" is the right model.

### 2.5 How many items carry the signal [measured]

Items whose pass probability changes at all are estimated by Storey's pi0 on randomised p-values. Plain mid-p values
are biased here: degenerate tables give 0.5. The estimate is a lower bound on any-size changes, out of 200 items:

| text | ids-full | seed-only | seed-rule | seed-rule3 | cand | control:1 | control:2 | control:3 | control:4 | parent:B (null) |
|---|---|---|---|---|---|---|---|---|---|---|
| items changed | 43.5 | 40.7 | 19.7 | 34.3 | 53.9 | 16.0 | 24.2 | 46.6 | 13.5 | 2.6 |

**Replicated movers.** These are items with a same-sign |delta| >= 0.5 in both run halves. ids-full has 21 up / 6 down,
against 2 / 3 for the null pair.

**Cross-validated concentration.** Items are ranked on half 1 and the net is read on half 2, in the effect's
direction:
- ids-full: 14 items carry 50 % of its net, 25 carry 80 %, 35 carry 100 %.
- control:3: its harm is diffuse, 21 / 43 / 94 items.

**Any text.** 75 items are constant over all 44 cal-1 runs (25 all-fail, 50 all-pass). 57 items have a permutation
p < 0.05 for "some text matters".

**Net effect by parent stratum.** The scaffold class comes from independent sessions only (not cal-1): always-fail 37,
mixed 52, always-pass 111 items.

| text | always-fail (37) | mixed (52) | always-pass (111) |
|---|---|---|---|
| ids-full | +3.5 | +15.12 | -0.88 |
| cand | +3.75 | +1.96 | -11.96 |
| control:3 | -0.25 | -5.38 | -15.12 |
| seed-rule3 | | | -6.88 |

Gains come from parent-stochastic items (and some always-fail ones). Harm comes from always-pass items. This is the
single most useful item property found.

### 2.6 IRT with Skill texts as respondents [measured]

**Rasch fit.** cal-1, 10 texts, 125 informative items (75 constant items dropped). Theta spans 2.9 logits: ids-full
1.51, seed-only 1.44, control:3 -1.38.

**Deviance split** (each against a parametric-bootstrap null):

| component | deviance | null mean | null 95th percentile |
|---|---|---|---|
| text main effect | 349.7 | 9.3 | |
| item x text interaction | 1,834.7 | 968.3 | 1,037 |

So 72 % of the excess text deviance is interaction. With the 6 v3 rule texts added (16 texts, 135 items) it is 74 %.

**Residual SVD.** 9 of 9 dimensions exceed parallel-analysis nulls; with 16 texts, 14 dimensions. The first two are
strong: 25.8 and 24.3, against null 14.7 and 13.2.

**Item parameters.**
- 2PL slopes (abilities fixed at the 16-text thetas): median 0.87, IQR [0.35, 1.53], 17 of 135 negative. Split-half
  reliability of the slopes is 0.41.
- Item-rest correlation over 16 texts: median 0.39, split-half reliability 0.33.

"Discrimination" is therefore a weakly reproducible item property in this setting.

### 2.7 Movability and test-free properties [measured]

**Signed movability.** The ids-full half-1 item delta predicts the half-2 item deltas of other texts:

| text | seed-only | seed-rule | seed-rule3 | cand | control:2 | control:3 | control:4 | control:1 |
|---|---|---|---|---|---|---|---|---|
| r with ids-full half-1 delta | 0.544 | 0.322 | 0.351 | 0.302 | 0.243 | 0.118 | 0.13 | -0.065 |

So "items that respond to task-card text" partly generalise across texts. An unsigned movability index (sum |delta|)
has split-half 0.819, but its null is 0.464, so half of it is noise.

**Scaffold stochasticity.** Measured in independent sessions, it correlates with |delta| (Spearman 0.56-0.66).

Test-free targets defined in cal-1:
- T1 = task-card responder (27 items).
- T2 = harm-susceptible (50 items).

| property (no test data, no cal-1 data) | AUC for T1 | AUC for T2 |
|---|---|---|
| parent p(1-p), independent sessions | 0.849 [0.758, 0.927] | 0.54 |
| parent stochastic flag | 0.821 [0.729, 0.893] | 0.54 |
| parent pass rate | 0.224 (i.e. 0.78 inverted) | 0.625 [0.55, 0.69] |
| examiner form-code share (D1-D3) | 0.394 [0.22, 0.59] | 0.537 |
| no-answer-tag share of parent replies | 0.67 | 0.47 |
| item text: gold-answer length in words | 0.364 [0.285, 0.452], i.e. 0.64 inverted: short answers respond | 0.60 [0.51, 0.68] |
| item text: answer mentions in the context | 0.51 [0.39, 0.63] | 0.36 [0.27, 0.45], i.e. 0.64 inverted |
| item text: question words / context words / numeric answer / number of aliases / answer in context | 0.43-0.50, every CI includes 0.5 | 0.49-0.52 |

| parent class | items | T1 rate | T2 rate |
|---|---|---|---|
| stochastic | 52 | 42 % | 31 % |
| always-fail | 37 | 13.5 % | 0 % |
| always-pass | 111 | 0 % | 31 % |

Text features of the item are weak: two reach AUC 0.64 when inverted, the rest sit at about 0.5. The examiner's
diagnosis code gives no evidence (0.39, CI includes 0.5). Responsiveness is not predicted from text; it is measured
by the parent's own runs, which the pipeline already pays for.

### 2.8 Dead items [measured]

Over independent sessions (median 28 runs per item, all 9 calibration texts):
- 19 items fail under every text. All 9 texts net about 0 on them; cand is +0.25. They are safe to drop.
- 75 items pass under every text in those sessions, yet in cal-1 they carry harm: control:3 -5.0, cand -2.83,
  control:1 -2.5, seed-rule3 -1.0 net items. "Constant in calibration" is not "dead in the future" for always-pass
  items. They must stay in any panel that guards against harm.
- D8 reports 25/200 items that pass in no arm and no run of cal-1 (0 of 44 runs each); these are the 25 all-fail
  items of 2.5. Over the independent sessions, 19 items stay dead under all 9 texts.

### 2.9 Panel selection and weighting (retrospective simulation) [measured]

Question: with n of the 200 items, how well does a panel reproduce the 200-item effect of each of the 9 cal-1 texts?
The selection uses only calibration data from independent sessions (the pre-round and every v3 stage-1 cell).
- Mode "shared": the panel and the reference use the same cal-1 runs. This isolates the item-sampling and selection
  error, the tinyBenchmarks metric.
- Mode "independent": the panel uses runs {0,1} and the reference runs {2,3}.

RMSE in points, mean over 9 texts, 2,000 panels per cell. Shared mode:

| policy | n=20 | 40 | 60 | 100 | 150 |
|---|---|---|---|---|---|
| random | 5.35 | 3.55 | 2.73 | 1.77 | 1.03 |
| stratified, proportional | 5.21 | 3.45 | 2.58 | 1.70 | 0.98 |
| stratified, Neyman (parent strata, population weights) | 4.84 | 3.20 | 2.45 | 1.54 | 0.89 |
| drop items dead by calibration (95 items) | 3.63 | 2.41 | 1.82 | 1.13 | -- |
| most movable items (unweighted) | 4.98 | 4.51 | 5.43 | 4.31 | 1.53 |
| anchor points (k-means medoids, weighted) | 4.23 | 3.49 | 1.76 | 1.22 | 1.22 |
| p-IRT on random items | 5.53 | 3.68 | 2.73 | 1.79 | 1.03 |

Independent mode, random: 6.50 / 4.62 / 3.80 / 2.93 / 2.35. The floor at n = 150 is the run-half offset of 2.2, not
item sampling. Neyman gives 6.01 / 4.25 / 3.50 / 2.73 / 2.30.

Biases at n = 60 (shared mode, points):
- **Neyman.** All |bias| <= 0.05.
- **Drop-dead.** control:3 +2.55, cand +1.35, control:1 +1.28; harmless texts about 0. It removes exactly the
  always-pass items that carry harm.
- **Most-movable.** ids-full +6.96, seed-only +9.74, control:3 -6.71. It changes the estimand to "effect on movable
  items".
- **Anchor.** seed-rule3 -2.45, cand -2.12, control:1 +2.57. Its low RMSE on ids-full (0.8) and seed-only (0.7) is
  leakage: ids-full and cand were calibration texts.

Neyman at n = 60 equals random at about n = 70: random needs about 16 % more items, i.e. Neyman saves about 14 % at
equal RMSE, without bias.

### 2.10 D-study: items versus runs, fixed panel versus population [measured components, derived n]

For a contrast "text minus scaffold" measured with r runs per arm on n items, the variance of the mean delta depends on
the estimand:
- **Fixed-panel estimand** (the panel's own items): (s_t^2 + s_s^2) / (r n).
- **Population estimand** (unseen items of the benchmark, the super-population of Miller 2024): (tau^2 + (s_t^2 +
  s_s^2) / r) / n.

The required n is 7.85 V / delta^2 (80 % power, two-sided 5 %). Script `e5_dstudy.py`, output `results/dstudy.json`.

| benchmark / text (vs scaffold) | items | delta (points) | tau | s2 text / scaffold | n needed, 5-point effect, population r=1 / 2 / 4 | fixed panel r=1 / 2 / 4 |
|---|---|---|---|---|---|---|
| SearchQA ids-full (cal-1) | 200 | +8.88 | 0.283 | 0.025 / 0.053 | 495 / 374 / 313 | 243 / 122 / 61 |
| SearchQA seed-only | 200 | +8.46 | 0.236 | 0.027 / 0.053 | 425 / 300 / 237 | 251 / 126 / 63 |
| SearchQA cand | 200 | -3.12 | 0.277 | 0.080 / 0.053 | 658 / 450 / 345 | 418 / 209 / 105 |
| SearchQA control:3 | 200 | -10.38 | 0.207 | 0.080 / 0.053 | 553 / 344 / 239 | 418 / 209 / 105 |
| SearchQA control:1 | 200 | -4.12 | 0.123 | 0.048 / 0.053 | 364 / 206 / 127 | 316 / 158 / 79 |
| SearchQA parent:B (same text) | 200 | +0.75 | 0.000 | 0.051 / 0.059 | 346 / 173 / 87 | 346 / 173 / 87 |
| SearchQA ids-full (v3 cells) | 231 | +6.23 | 0.178 | 0.034 / 0.044 | 343 / 221 / 161 | 243 / 122 / 61 |
| OfficeQA ids-full (v3) | 74 | +7.05 | 0.171 | 0.083 / 0.034 | 460 / 276 / 184 | 368 / 184 / 92 |
| LiveMath ids-full (v3) | 142 | -0.94 | 0.133 | 0.076 / 0.059 | 479 / 267 / 162 | 424 / 212 / 106 |
| SpreadsheetBench ids-full (v3) | 89 | +1.83 | 0.122 | 0.090 / 0.073 | 559 / 303 / 175 | 512 / 256 / 128 |
| ALFWorld ids-full (v3) | 57 | +9.94 | 0.221 | 0.050 / 0.070 | 530 / 342 / 248 | 377 / 189 / 95 |

With infinitely many runs the population estimand still needs 7.85 tau^2 / delta^2 items: 251 for SearchQA ids-full
at 5 points, 98 at 8 points (tau = 0.283).

Minimum detectable effect (80 % power, 2 runs per arm) at the current panel sizes, from the same components [derived]:

| benchmark (panel items) | population estimand | fixed panel | population with infinite runs |
|---|---|---|---|
| SearchQA (200) | 6.8 points (5.3 with the v3 tau) | 3.9 | 5.6 |
| LiveMath (100) | 8.2 | 7.3 | 3.7 |
| SpreadsheetBench (91) | 9.1 | 8.4 | 3.6 |
| OfficeQA (74) | 9.6 | 7.9 | 5.6 |
| ALFWorld (57) | 12.2 | 9.1 | 8.2 | Runs beyond 2 buy little once tau^2 dominates. That is Miller's (2024)
resampling point [verified]: resampling helps "until E[sigma_i^2]/K << Var(x)". For generalisation claims the budget
should go to items: 2 runs per item, as many items as the pool allows.

## 3. The other four benchmarks (v3 cells, ids-full vs scaffold) [measured]

All v3 non-evaluation units were pooled. The v3 train units have 2 runs per item; SpreadsheetBench has 1.

| benchmark | items | scaffold train pass | ids - scaffold (points) [95 % CI] | up / down | items constant under both texts (fail + pass) | items changed (Storey) | contrast reliability train vs later sessions | net by parent class: stochastic / always-fail / always-pass | delivered tokens per cell, scaffold / ids-full |
|---|---|---|---|---|---|---|---|---|---|
| SearchQA (v3 only) | 200 | 0.743 | +6.74 [3.6, 9.87] | 46 / 14 | 29 + 109 | 40.1 | 0.311 | +11.7 / +4.5 / -2.75 | 1,236 / 4,088 |
| OfficeQA | 74 | 0.203 | +7.05 [2.23, 11.87] | 25 / 9 | 31 + 9 = 40 | 20.1 | 0.523 (60 items) | +1.0 / +4.9 / -0.7 | 4,690 / 7,927 |
| LiveMath | 100 | 0.375 | -1.84 [-6.2, 2.51] | 17 / 24 | 42 + 14 = 56 | 9.3 | 0.246 | -2.3 / +2.75 / -2.3 | 1,251 / 3,969 |
| SpreadsheetBench | 91 | 0.511 | +1.81 [-3.6, 7.23] | 18 / 17 | 22 + 33 = 55 | 2.4 | n/a (1 run) | -1.4 / +5.9 / -2.9 | 2,010 / 4,273 |
| ALFWorld | 57 | 0.404 | +9.94 [1.74, 18.14] | 13 / 4 | 22 + 18 = 40 (70 %) | 8.4 | n/a | +0.6 / +5.6 / -0.5 | 28,463 / 106,072 |

Readings:
- The "constant under both texts" counts rest on only 2-8 runs. They are upper bounds on dead items, not the strong
  definition of 2.8.
- On OfficeQA and ALFWorld the gain sits in always-fail items. There the task-card seed fixes systematic failures,
  unlike SearchQA where it fixes stochastic ones. The stratum that carries the gain is benchmark-specific, so strata
  weights must be benchmark-specific.
- LiveMath and SpreadsheetBench have about 2-9 changed items out of 91-100 for this text. Their panels carry almost no
  signal for this contrast at the current sizes.

## 4. Generated versus real items (10/15-16 probes) [measured]

| | generated | real |
|---|---|---|
| **G1 floor/ceiling** under deepseek (about 20 runs per item) | 9 all-fail and 46 all-pass of 124 | 12 and 30 of 73 |
| pass rate under "empty" | 0.478 | 0.586 (harder for generated) |
| unknowns (mostly truncation) | about 1 % | 7-13 % |
| **G2** same text, two deepseek sessions: items that differ | 13-18 % | 3-15 % |
| **G4** item-delta correlation across solver models | 0.02-0.31 | -0.11 to 0.49 |

The movability of an item is largely solver-specific.

**G3, 24 contrasts with matched generated and real measurements.**
- Pearson 0.926, Spearman 0.80, sign agreement 20/24.
- Generated minus real is +6.95 points on average; the slope of real on generated is 0.686.
- These are dominated by "Skill vs empty" contrasts of +16 to +30 points.
- On the 10 learning-relevant contrasts (learned Skill minus bzero, four solver models) the Pearson is -0.235 and
  generated minus real is +5.28 points. Example, glm-5.3 oq_s1 minus bzero: generated +12.9, real -0.7.

**G5, selecting generated items by GLM-side calibration.** Four selections, each judged by the mean |gap| between
the generated and the real contrast over the 9 deepseek contrasts: all 124 items 4.54 points; not at ceiling under
bzero (114) 4.43; neither floor nor ceiling (106) 5.01; movable under GLM (105) 5.54; stable under text (70) 5.31.
Selection
on the generator side's own solver does not fix the bias.

**G6, SearchQA generated b06 panel (168 items).**

| deepseek text | empty | bzero | qa_s1 | qa_v9 | oq_s1 | oq_s2 |
|---|---|---|---|---|---|---|
| pass rate | 0.768 | 0.917 | 0.899 | 0.902 | 0.896 | 0.893 |

112 of 168 items (67 %) pass every deepseek cell. For fine contrasts that panel is near-dead.

These measurements quantify the 10/15-16 finding for the earlier protocol line. Generated items reproduce coarse
contrasts but not the small, learning-relevant ones, and their bias is positive. That is exactly the failure that
matters for purpose 1.

## 5. Literature: what carries over and what does not

Abstract-level claims were re-checked on arXiv in the resumed session (2026-10-21 04:46-04:52) for tinyBenchmarks,
metabench, PromptEval (model form also checked in the paper body), Fluid Benchmarking, Signal and Noise, Anchor
Points, Madaan et al., Miller (section 3.1 resampling condition and sections 2.2, 4.2, 5 checked in the body),
Truong et al. and Perlitz et al. [verified]. The ACL 2021 and psychometrics entries were checked by the earlier part
of this exploration and not re-checked.

| work | what it does [claim] | key assumption | fit for Skill-text contrasts (this data) |
|---|---|---|---|
| tinyBenchmarks, Polo et al., ICML 2024 (arXiv 2402.14992) | "it is sufficient to evaluate this LLM on 100 curated examples" to estimate MMLU accuracy (abstract); IRT-based estimators p-IRT and gp-IRT; the abstract gives no error figure (the about-2 % error is a paper-body claim, not re-read) | many calibration models (hundreds of leaderboard models); a low-dimensional IRT; the new model behaves like the calibration population | poor. Respondents here are Skill texts of one solver; interaction is 72 % of the excess deviance; p-IRT gave no gain (2.9); anchors helped only for texts used in calibration |
| metabench, Kipnis et al., ICLR 2025 (arXiv 2407.12844) | more than 5,000 LLMs; 28,632 items reduced to under 3 %; RMSE 1.24 % per benchmark, 0.58 % total; one latent factor (Spearman 0.94) | unidimensional ability across items | does not hold: 9 of 9 residual dimensions above null |
| Fluid Benchmarking, Hofmann et al., 2025 (arXiv 2509.11106) | IRT plus adaptive item selection by Fisher information; higher validity and lower variance on MMLU with 50x fewer items | a valid IRT model | the idea carries over. Information for a contrast is concentrated where the parent is stochastic, p(1-p). Without a valid IRT model, the model-free version is stratified Neyman allocation |
| Signal and Noise, Heineman et al., 2025 (arXiv 2508.13144; the arXiv page shows no venue) | signal = separating better from worse models; noise = variability between training checkpoints; "filtering noisy subtasks" (subtasks, not items) makes multi-task evaluation more reliable | -- | applies at stratum level. Dead items carry zero signal; always-pass items carry the harm signal, so "noisy" must be judged per question (gain or harm) |
| PromptEval, Polo et al., NeurIPS 2024 (arXiv 2405.17202) | performance quantiles over 100 prompt templates on MMLU at the cost of about 2 single-prompt evaluations; model Y_ij ~ Bernoulli(sigma(f(x_i) - g(z_j))) with prompt and example covariates, additive on the logit scale (checked in the paper body) | no prompt x example interaction | violated. Item x text variance (11.6 %) is 9x the text main effect (1.3 %); Skill texts are prompts in this sense |
| Anchor Points, Vivek et al., EACL 2024 (arXiv 2309.08638) | 1-30 anchor items rank 87 model-prompt pairs | item responses correlate across models | partial. Anchors reproduce calibration texts, not new ones (biases -2.5 to +2.6 points) |
| Rodriguez et al., ACL 2021 | IRT leaderboards: difficulty, discrimination, feasibility | many systems | discriminations are only 0.41 reliable here |
| Vania et al., ACL-IJCNLP 2021 | IRT over 29 datasets and 18 models: which test sets still separate strong models | many models | saturation is the lesson. The generated SearchQA b06 panel (67 % pass every cell) cannot separate texts |
| Madaan et al., 2024 (arXiv 2406.10229; preprint) | variance in evaluation benchmarks; item analysis and IRT "struggle to meaningfully reduce variance" | -- | consistent with 2.6 and 2.9 |
| Miller, 2024 (arXiv 2411.00640) | questions are draws from a super-population; CLT and clustered standard errors; paired differences; resampling helps only until E[sigma_i^2]/K << Var(x); power analysis | -- | directly applicable: the population estimand and the D-study of 2.10 |
| Truong et al., 2025 (arXiv 2503.13335; venue not shown on the page) | amortised difficulty prediction plus a difficulty-conditioned question generator; 22 benchmarks, 172 LMs | difficulty is predictable from item text | for responsiveness the item text is weak here (best AUC 0.64 inverted); the parent's own runs measure difficulty more cheaply |
| Perlitz et al., NAACL 2024 (arXiv 2308.11696) | efficient benchmarking; the DIoR reliability measure; up to x100 compute reduction | -- | reliability-of-decision framing; compatible with the gate view |
| Glas & van der Linden 2003 (Appl. Psych. Meas. 27(4)); Sinharay, Johnson & Williamson 2003 (J. Educ. Behav. Stat. 28(4):295-313); Geerlings, Glas & van der Linden 2011 (Psychometrika 76(2):337-359) | item cloning / rule-based item generation: hierarchical IRT with family-level parameters, family expected response functions | clones of a family are exchangeable | the right frame for generated items: calibrate and validate families, not single items |

Standard references used without re-verification in this session: Brennan, *Generalizability Theory* (2001), for the
variance-component and D-study logic; Lalor, Wu & Yu, EMNLP 2016, "Building an Evaluation Scale using Item Response
Theory" (title and venue verified, abstract not read).

## 6. Proposal: selecting and weighting items

### 6.1 Rules the data support

R1. **Fix the estimand before the panel** (purposes 1 and 2). A gate that accepts a rule because "it helps" makes a
population claim: it should help on future items. The purpose-2 metric is a population claim on each target benchmark.
Use the population variance, tau^2 included, for CIs and power: an item-cluster bootstrap, or tau-hat from a calibration
fixture. Fixed-panel CIs are honest only for statements about that panel's items.

R2. **Items over runs** (1, 2). Use 2 runs per item and spend the rest of the budget on more items: fresh pool items,
or generated families once validated (6.3). Section 2.10 gives the item counts per effect size and benchmark.

R3. **Stratify on the parent stratum, with population weights and Neyman allocation** (1, 2).
- Strata: always-fail, mixed and always-pass, from pooled parent runs. The pipeline's train unit already runs the
  parent twice on every focal item; screen and confirm add more.
- Use same-session or multi-session pooled runs, never a single other session. Section 7.1: a 2-run pre-screen
  from a session with a +5.75-point offset is worthless. Section 7.3: a 3.5-hour-old one without drift kept its
  value. Check the paired scaffold offset in every measurement round, and re-screen beyond about +-4 points.
- A 2-run pre-screen supports allocation and the harm readout (always-pass class). It does not isolate the
  stochastic stratum (AUC 0.51 on fresh items), so the gain stratum needs pooled multi-run parent runs (train +
  screen + confirm).
- Weights: the strata's shares in the full pool. Allocation: proportional to share x calibration SD.
- Retrospective gain: about 14 % fewer items at equal RMSE, no bias.

R4. **Keep always-pass items, never select by movability** (1, 2). They carry the harm signal. Movability selection
changes the estimand (+7 points for ids-full).

R5. **Drop only items dead under the whole calibration fixture over about 20 or more runs** (1, 2). That is 19 of 200
on SearchQA, about 10 %. Report the dropped count. A 2-run pre-screen must never be used to drop items: on the cal-1
analogue, dropping pre-screen-A0 items removes 5.5 of the 9.0 ids-full points.

R6. **Test gain and harm separately, then combine** (1).
- "Does the rule help" is informed by mixed items on SearchQA, and by always-fail items on OfficeQA and ALFWorld.
- "Does it harm" is informed by always-pass items.
- A gate with a per-stratum readout and a population-weighted total avoids both the estimand shift and the hidden-harm
  bias of R4 and R5.

R7. **Benchmark-specific strata** (2). The stratum carrying the gain differs by benchmark (section 3), so strata and
weights are estimated per benchmark, never transferred.

### 6.2 Transfer-predictive item properties measurable without test sets

Definitions. Let K calibration texts t (plus the scaffold) be run on a real training pool R of benchmark b.

- **Item level, within benchmark.** TPS_I(i) = corr over t of (delta_i(t), mean delta over R without i, at t).
  Measured: the item-rest correlation over 16 texts has split-half reliability 0.33, so it is **not usable per item**.
  2PL slopes are no better (0.41).
- **Family level, within benchmark** (the proposal). For a generator family F, regress the real-pool mean delta on the
  family mean delta across t:
  - TPS_F = the correlation over t;
  - beta_F = the calibration slope;
  - alpha_F = the bias.

  A family is *transfer-predictive* when TPS_F is high, beta_F is about 1 and |alpha_F| is small. The criterion uses
  real training items only, so no test set is touched.

  **How high can TPS_F be for a perfectly valid family?** [measured, simulation, `e5_tps_sim.py`,
  `results/tps_sim.json`] Take random subsets of the real focal items as the "family". Measure each with 2 runs per
  arm (text runs {0,1} minus parent:A runs {0,1}). The criterion is the other items with independent runs (text runs
  {2,3} minus parent:B). 2,000 draws per row:

  | calibration texts | n_F | TPS_F, 5th / 50th / 95th percentile | slope beta_F, median | bias alpha_F, 90 % range |
  |---|---|---|---|---|
  | all 9 cal-1 texts | 30 | 0.67 / 0.86 / 0.96 | 0.68 | -6.7 to +7.1 points |
  | all 9 cal-1 texts | 100 | 0.83 / 0.93 / 0.98 | 0.84 | -4.3 to +4.1 |
  | 5 texts (ids-full, seed-only, control:3, cand, seed-rule3) | 100 | 0.89 / 0.97 / 0.995 | 0.89 | -5.7 to +5.0 |
  | 4 small-effect texts only (seed-rule, control:1, :2, :4; effects -4 to +3 points) | 100 | 0.46 / 0.86 / 0.99 | 0.65 | -4.1 to +3.8 |

  So a valid family of 100 items, checked with the 9 cal-1 texts, scores TPS_F >= 0.83 in 95 % of draws. Its bias
  stays within about +-4 points in 90 % of them, and its slope is attenuated to about 0.84 by its own noise. Checking
  only small-effect texts cannot certify a family: the 5th percentile is 0.46.

  For comparison, the generated OfficeQA items on the 10 learning-relevant contrasts gave r = -0.24 and a +5.3-point
  gap (section 4). That is far outside the valid-family distribution, though it comes from another benchmark and
  protocol line.
- **Cross-benchmark.** TPS_X(F, b -> c) = corr over t of (family mean delta on b, real-pool mean delta on c's TRAINING
  pool). It ranks which source-benchmark items and families predict transfer to a similar benchmark. It needs texts
  measured on both benchmarks; E2, E4 and D12 build such fixtures. Final evaluation on c's test split stays untouched
  and post hoc.

Item properties and their measured predictive value:

| property | what it predicts | strength |
|---|---|---|
| parent stochasticity (pooled multi-session runs) | responsiveness to helpful texts | AUC 0.85 |
| parent always-pass | harm exposure | T2 rate 31 % vs 0 % for always-fail |
| same-session 2-run pre-screen | responsiveness | weak (0.64-0.72) |
| cross-session 2-run pre-screen | responsiveness | none (0.53) |
| item text features, examiner diagnosis codes | responsiveness | weak to none (best 0.64 inverted, gold-answer length; examiner code share 0.39, CI includes 0.5) |
| IRT discrimination, item-rest correlation | (reliability) | weak (0.41, 0.33) |
| movability across solver models | responsiveness under another solver | weak (0.02-0.31), so calibrate with the deployment solver |

### 6.3 Procedure for generated items (verification side, purpose 1)

The verification side's evolving artifact can be a set of generator families: rubric-plus-template "coding rubrics",
read as executable item generators with guaranteed answers, as in D6. Its fitness is defined by measurement validity,
not by item counts.

1. **Validity gate per family.** Generate about 100 items with guaranteed answers. Run the parent x 2: this is the
   pre-screen and gives the stratum. Run a calibration fixture of 6-10 texts whose real-pool effects are known; for
   SearchQA the cal-1 arms give 9 texts with known effects. Use 1-2 runs. Compute TPS_F, beta_F and alpha_F against
   the cal-1 real-pool deltas. Admit the family if TPS_F >= 0.80 and |alpha_F| <= 4 points (n_F = 100, 9 texts).
   These thresholds are the 5th percentile and the 90 % range of the valid-family simulation above, so a valid family
   is rejected about 5-10 % of the time. Pre-register them. Cost: about 100 x (2 + 9 x 2) = 2,000 cells, about
   3-4M tokens on SearchQA [estimate]. With the 5 large-effect texts it is about 1,200 cells, but small-effect validity
   is then not tested.
2. **Difficulty matching.** Generated pools are ceiling-heavy: the b06 SearchQA panel has 67 % of items passing every
   cell. Steer generation toward the strata the question needs (mixed and always-fail for gains, always-pass for
   harm). Weight admitted items to the real pool's stratum shares.
3. **Online validity, the co-evolution signal.** Every gate round measures the candidate rules on the real panel
   anyway. Also measure them on admitted families and append the pair (family mean delta, real delta) to each
   family's record. Families whose prediction error exceeds the bound are demoted. The verifier side evolves toward
   families with high TPS_F and high information (a high share of parent-mixed items). This is a learnable fitness for
   the verification side that needs no test set and no extra solver calls beyond the families' own cells.
4. **Hierarchical calibration.** Use the family mean, with item deltas shrunk to it by a random-effects model, as the
   unit of evidence, never single generated items. This is the item-cloning frame of Glas & van der Linden, Sinharay
   et al. and Geerlings et al.

An admitted family is a measurement instrument, not evidence that any Skill rule is good. Following AGENTS.md, an
accepted verifier is not an accepted Skill.

### 6.4 How this serves the two purposes

- **Purpose 1, co-evolution.**
  - The gate uses R1-R6.
  - The verification side's artifact is the set of generator families, scored by TPS_F, alpha_F and information.
  - Its improvement is measurable: TPS_F and calibration error over the rounds.
  - What it feeds back to the Skill side is restricted to strata where effects are detectable (mixed items for gains,
    always-pass items for harm), the "genuinely learnable" part.
- **Purpose 2, generalisation metric.**
  - On every evaluation benchmark, report the population estimand with tau-inclusive CIs, per-stratum readouts and
    benchmark-specific weights.
  - Size panels by the D-study. Under 8 points, current panels can only make fixed-panel statements.
  - Cross-benchmark TPS may choose which training-side items and families of the evolution benchmark to use. It never
    replaces the post-hoc evaluation on the other benchmarks.

## 7. Pilot E5-P1: prospective test of the selection rules on fresh items

### 7.1 Design (pre-registered before launch)

**Question.** Do the rules of section 6, derived on the 200 focal items, hold on items never used before? A 2-run
parent pre-screen is the cheapest form of the parent stratum.

**Items.** 180 SearchQA training items drawn from:
- the 600-item pool,
- minus the 200 focal items,
- minus the 60 regression items,
- minus the 130 items of the D1-v2 fresh batch, to stay disjoint from D1,

which leaves 239. The draw is the seeded hash order tag `e5p1-fresh:searchqa`, first 180: 116 train-part and 64
val-part items. `data.pool` refuses test ids.

**Phases.**
- Phase A (pre-screen): the scaffold x 2 runs. The classes A0 (no pass), A1 (mixed) and A2 (all pass) were frozen to
  `strata.json` before phase B started.
- Phase B (measurement): scaffold, ids-full, control:3 and cand x 2 runs, item-blocked dispatch.

**Fidelity.**
- Arm texts are byte-identical to cal-1: the digest and the request hash on 3 focal items per arm were checked
  (16/16 true).
- deepseek-v4-flash on the PJLAB token route: thinking disabled, temperature 0, max_tokens 32768.
- Frozen solver prompt, native scorer and v3 cell decision table (`outcomes.classify`: truncation = fail,
  undelivered = unknown).

**Pilot simplifications** (as in E4's runner):
- an undelivered call is re-sent at most twice, after 60 s;
- one run-level token cap, 3.9M on the new machine.

**Pre-registration.** Before launch the analysis code `e5p1_analyse.py` computed the expected values of every
statistic on the focal analogue: pre-screen = cal-1 pre-round parent:A runs 0-1; measurement = cal-1 runs 0-1 of the
same 4 texts. It also computed their item-bootstrap replication ranges at n = 180. The code, the plan, the plan notes
and the runner were hashed in `prereg_hashes.txt` (sha256 of `analysis_plan.json` 00e89672..., of `e5p1_analyse.py`
0344f908...).

Hypotheses (from `analysis_plan.json`):
- **H1, generalisation.** Fresh ids-full minus scaffold > 0 (95 % CI above 0). z against the focal full-design
  estimate within +-1.96.
- **H2, gain location.** For ids-full, mean delta(non-A2) - mean delta(A2) > 0 (CI above 0).
- **H3, harm location.** For control:3 and cand, mean delta in A2 < 0 (CI below 0).
- **H4, drop-A0 bias.** About 0 for the harmful texts, negative for ids-full.
- **H5, Neyman.** Neyman/random RMSE at n = 60 below 1.
- **H6, property AUC.** AUC(T1 by A1) > 0.5 (CI above 0.5).
- **H7.** Every scalar inside its focal range, otherwise reported as a non-replication.

**Expected values, focal analogue** (n = 200; ranges at n = 180, 2.5-97.5 %):

| statistic | expected | range at n = 180 |
|---|---|---|
| classes A0 / A1 / A2 | 56 / 18 / 126 (28 / 9 / 63 %) | A0 22-34 %, A1 5-13 %, A2 56-70 % |
| ids-full delta | +9.0 | [+4.7, +13.9] |
| ids-full net by class A0 / A1 / A2 | +11.0 / +7.5 / -0.5 items | A2 mean [-4.6, +3.6] points |
| ids-full mean(non-A2) - mean(A2) | +25.4 | [+14.7, +36.4] |
| control:3 delta | -11.5 | [-16.7, -6.4] |
| control:3 A2 mean | -14.7 | [-20.6, -8.9] |
| cand delta | -3.0 | [-8.9, +2.8] |
| cand A2 mean | -11.1 | [-17.2, -5.4] |
| cand A0 mean | +11.6 | [+0.9, +22.6] |
| drop-A0 bias: ids-full / control:3 / cand | -5.5 / +2.75 / -3.25 | ids [-8.9, -2.5]; ctrl3 [+0.6, +5.6]; cand [-6.7, -0.3] |
| AUC(T1 by A1) | 0.644 | [0.56, 0.73] |
| AUC(T1 by not-A2) | 0.721 | [0.64, 0.81] |
| AUC(T2 by A2) | 0.574 | [0.50, 0.65] |
| Neyman / random RMSE, n = 40 / 60 / 90 | 0.91 / 0.94 / 0.94 | (one realisation; not bootstrapped) |
| focal full-design deltas (8 vs 4 runs): ids-full / control:3 / cand | +8.88 (SE 2.10) / -10.38 (1.84) / -3.12 (2.24) | used for the z of H1 |

**Sensitivity found before launch, recorded in `analysis_plan_notes.json`** [measured]. The pre-screen was replaced by
the v3 E-ds s1 train runs 0-1. That session ran 2026-10-20 00:07-00:18, about 16 hours before cal-1, with a
+5.75-point scaffold offset. The pre-screen then has no value:

| statistic | same-session cal-1 pre-round | v3 train (16 h earlier) |
|---|---|---|
| classes A0 / A1 / A2 | 56 / 18 / 126 | 48 / 7 / 145 |
| ids-full net by class A0 / A1 / A2 | +11.0 / +7.5 / -0.5 | +4.5 / +2.0 / +11.5 |
| AUC(T1 by A1) | 0.64 | 0.528 |
| Neyman / random RMSE at n = 60 | 0.94 | 0.995 |

Items that passed twice in a "good" serving window are where the scaffold later fails, and where ids-full then wins.
**A pre-screen must come from the same serving window, or pool several sessions.** This is the strongest practical
caveat on any stratified design, and it ties to D8's drift finding.

### 7.2 Execution [measured, from the run logs and cell files]

| step | when (2026-10-21, CST) | where | cells | outcome |
|---|---|---|---|---|
| runner v1, phases A then B, 6 workers | 00:43:47-01:00:34 | new machine | 180 of phase A | stopped (exit 143, SIGTERM) and replaced by v1.1; the v1.1 docstring gives the reason as HTTP 429 bursts with 30/90/180 s back-offs |
| runner v1.1 (identical cells; adds `--slice`, `--reference`, `--max-workers`), phase A completed | 01:00:55-01:21:35 | new machine | 360 (180 kept from v1) | strata frozen at 01:21:35: A0 41, A1 9, A2 130 |
| phase B, draw positions 0-90 | 01:21-02:00:05 | new machine | 720 | 0 errors; v1.1 ledger 1,840,457 tokens (includes phase A) |
| planned relay of positions 90-180 to the old machine | -- | -- | 0 | never ran: the session ended first; at 04:41 the old machine had no run directory |
| resumed: phase B positions 90-135 | 04:44:32-05:06:22 | new machine | 360 | 0 errors; 364 calls for 360 cells; 658,244 tokens |
| resumed: phase B positions 135-180 | 04:44:32-05:06:18 | old machine | 360 | 0 errors; 363 calls for 360 cells; 743,223 tokens |

The resumed runs used the unchanged v1.1 runner and the frozen strata. The file was relayed byte-identically (sha256
3a27d071... on both machines). Dry runs on both machines reproduced the same 180-item draw (116 train-part, 64
val-part); the identity checks gave 16/16 true; the first cell of each machine passed validation (pass, finish =
stop).

**Deviation from the plan.** The pre-registered design measured phase B minutes after the pre-screen. The second
half of phase B (positions 90-180, assigned at random by the seeded hash order) ran about 3.4-3.8 hours after the
pre-screen, in another serving window. The pre-registered analysis below uses all 180 items, as registered. The
split by window is exploratory, and its only purpose is the serving-drift question that the pre-launch sensitivity
analysis raised.

Tokens: 3,241,924 over the 1,800 cell files. That equals the two ledgers: new machine 2,498,701 (including the earlier
cells), old machine 743,223. Calls in flight when v1 was stopped (at most 6) are not recorded.

### 7.3 Results [measured; the pre-registered `e5p1_analyse.py pilot`, file hashes as registered]

**Denominators.**
- 180 fresh items.
- Phase A: 360 cells (269 pass / 91 fail).
- Phase B: 1,440 cells (1,036 pass / 404 fail).
- 0 unknown cells and 0 errors. Every item has 2 scored runs in every arm.

| hypothesis | registered criterion | pilot value | verdict |
|---|---|---|---|
| H1 generalisation | ids-full - scaffold > 0 with CI above 0; z vs focal within +-1.96 | +8.89 points [4.44, 13.06], SE 2.21; focal full design +8.88 (SE 2.10); z = 0.005 | **replicated** |
| (same z, other texts) | no directional claim for cand | control:3 -11.39 [-16.40, -6.39], z -0.33; cand -8.61 [-14.17, -3.06], z -1.51 | consistent with focal. cand is more harmful on fresh items; its focal effect was -3.12 [-7.5, +1.3] |
| H2 gain location | ids-full mean(non-A2) - mean(A2) > 0, CI above 0 | +23.7 [10.2, 36.8] | **supported**, but the gain sits in A0 (41 items, +30.5 points, 12.5 of 16 net items), not in A1 (9 items, +5.6, 0.5 net; focal range [16.6, 66.7]) |
| H3 harm location | A2 mean < 0 with CI below 0 (control:3, cand); mean(A2) - mean(A0) < 0 | control:3 A2 -16.5 [-22.6, -11.1], A2-A0 -17.8; cand A2 -17.7 [-23.9, -11.7], A2-A0 -34.8 | **supported** for both. A2 items carry -21.5 of control:3's -20.5 net items and -23.0 of cand's -15.5 |
| H4 drop-A0 bias | within +-1 point for control:3 and cand; negative for ids-full | control:3 -0.28; cand -3.89; ids-full -6.94 | **fails as registered (cand).** The registered +-1 conflicted with the plan's own focal expectation for cand (-3.25, range [-6.67, -0.28]); cand lies inside that range. Dropping the 41 pre-screen all-fail items removes 6.9 of ids-full's 8.9 points (78 %) |
| H5 Neyman | Neyman/random RMSE at n = 60 < 1 | 0.926 (n = 40: 0.962; n = 90: 0.927). Neyman n = 60 is worth random n = 66 | **supported** (focal expectation 0.94) |
| H6 property AUC | AUC(T1 by A1) > 0.5 with CI above 0.5; AUC(T2 by A2) > 0.5 | AUC(T1 by A1) 0.514 [0.470, 0.574] (27 responders); AUC(T2 by A2) 0.652 (57 harm items). Secondary: AUC(T1 by not-A2) 0.751 (focal range [0.641, 0.805]) | **first part not replicated**; second part holds |
| H7 replication ranges | every scalar inside its focal item-bootstrap range at n = 180 | 20 of 73 compared statistics outside (17 of 61 without the duplicated stratum sizes) | **not replicated in detail.** About 4 of 73 would be expected by chance if fresh items were exchangeable with focal ones |

**Where the details did not replicate.**
- **Item mix.** The fresh items are easier for the scaffold. Pre-screen pass rate is 0.747 vs 0.675 focal. A2 is 72.2 % (range 56.1-70.0 %); A1 is 5.0 %, 9 items, at the lower edge.
- **ids-full.** Its gain moved from A1 (focal +41.7 points on 18 items) to A0 (+30.5 on 41). A2 net is +3.0 items (focal -0.5).
- **control:3.** It does not hurt A0 items: +0.5 net (focal -5.5, range [-10, -1]).
- **cand.** It hurts A2 items more: -23.0 net, mean -17.7 (focal -14.0, range [-20, -6]). AUC(T2 by A2) is 0.652, just above its range [0.498, 0.646].

**Exploratory split by serving window** (not pre-registered; `verify/e5p1_halves.py`; draw positions were assigned by
the seeded hash order, so the halves are random halves):

| window | items | A0 / A1 / A2 | scaffold phase B - pre-screen, paired (items up / down) | ids-full | control:3 | cand | AUC(T1 by not-A2) | AUC(T1 by A1) |
|---|---|---|---|---|---|---|---|---|
| positions 0-90, phase B 01:21-02:00 (same window as pre-screen) | 90 | 22 / 6 / 62 | -0.56 [-5.0, 3.3] (5 / 5) | +8.89 [2.2, 15.6] | -11.67 [-19.4, -4.4] | -8.33 [-17.8, 0.6] | 0.781 | 0.545 |
| positions 90-180, phase B 04:44-05:06 (3.5 h later) | 90 | 19 / 3 / 68 | +0.56 [-3.3, 5.0] (6 / 6) | +8.89 [3.9, 14.4] | -11.11 [-17.2, -5.0] | -8.89 [-16.7, -2.2] | 0.717 | 0.481 |

No serving drift appeared between 01:00 and 05:06: the paired scaffold offsets are about 0. The 3.5-hour gap
therefore did not cost stratification value in this run. Section 7.1 found the opposite for the 16-hour-old session,
which had a +5.75-point offset. The rule is therefore a check, not a time limit. The measurement round re-runs the
scaffold anyway. A paired scaffold offset beyond about +-4 points flags a stale pre-screen; +-4 points is the 95 %
CI half-width at 90 items here.

**What the pilot establishes** [measured; one benchmark, 4 texts, 180 items]:
1. **Generalisation within a benchmark holds at the predicted size.** The focal ids-full effect carries to unseen
   items of the same benchmark: +8.89 vs +8.88. The fresh item-bootstrap SE (2.21) matches the focal one (2.10), so
   the population estimand of R1 and the tau-based D-study are the right frame.
2. **Harm sits in pre-screen always-pass items for both harmful texts.** This confirms R4 (keep always-pass items) and
   R6 (a separate harm readout on A2) prospectively.
3. **A 2-run pre-screen has stratification value**, carried by the "not always-pass" split (AUC 0.75). Neyman
   allocation on its classes saves about 9 % of items at n = 60, as predicted.
4. **A 2-run "mixed" class does not mark responders.** It is too small (5 %) and gives AUC 0.51. The focal finding
   that gains come from parent-stochastic items (AUC 0.85) needs pooled multi-run strata (8-18 runs). On fresh items,
   the ids-full gain sits in the 2-run always-fail class. "Always-fail in 2 runs" is therefore not "dead": dropping
   those items removes 78 % of the gain. This confirms R5 (never drop on a 2-run pre-screen).
5. **Detail-level replication is poor** (20 of 73 statistics outside their ranges). Per-stratum magnitudes depend on
   the item sample. Use strata for allocation and readout, not as fixed expectations.

**Cost.**
- 3,241,924 tokens counted in the 1,800 cell files.
- Mean per cell: scaffold 1,236 (phase A 1,234), ids-full 3,995 (max 36,537), control:3 1,254, cand 1,287.
- The total equals the sum of the two machines' ledgers and the pre-launch median estimate of 3.24M.

## 8. Risks and limitations

- **One solver, one benchmark for most numbers.** The item psychometrics are deepseek-v4-flash on the SearchQA pool.
  The stratum that carries a gain differs by benchmark: mixed on SearchQA, always-fail on OfficeQA and ALFWorld.
  Item movability carries over poorly across solvers (r 0.02-0.31).
- **Rules derived on the same 200 items.** Their selection was partly data-driven. E5-P1 is the out-of-sample check,
  but on one benchmark and 4 texts.
- **Serving drift.** There was a +5.75-point offset between sessions 16 h apart, and a -0.8 to -3.5-point run-half
  offset inside cal-1. Any pre-screen or calibration ages. Strata need same-window or pooled runs and must be
  refreshed per round.
- **Few calibration texts** (9 cal-1 texts, 16 with v3). Item-level transfer-predictiveness is unreliable (0.33), and
  family-level TPS needs about 8-10 texts and about 100 items per family (an estimate, untested).
- **Generated-versus-real evidence comes from the earlier protocol line** (10/15-16 probes, prompts of the fivebench-g
  pipeline, OfficeQA mainly). It has not been redone with coevo5 texts and generated items. The b06 generated
  SearchQA panel is at ceiling.
- **Bounds and model assumptions.** Storey estimates of "items changed" are lower bounds that depend on runs. The
  D-study assumes binomial run noise, exchangeable items and no clustering. OfficeQA items share documents, so
  clustered SEs (Miller 2024) would raise its n.
- **Pipeline cost tail.** cal-1's ledger charged 26.5M tokens for 8,800 cells, but delivered replies used 14.0M.
  About 12M are reservations charged for undelivered calls (HTTP 503 chains near the cap stop, up to about 600k per
  cell). Cost estimates below use delivered usage; a capped pipeline run needs the margin.
- **Pilot execution deviated from the plan.**
  - HTTP 429 bursts forced runner v1.1 and a split across two machines; the cells are identical.
  - A session interruption put the second half of phase B 3.5 h after the pre-screen (7.2).
  - The registered H4 criterion (+-1 point) conflicted with the plan's own focal expectation for cand.
  - The pilot covers one benchmark, 4 texts and 180 items. Its per-stratum details replicated poorly (20 of 73
    statistics outside their ranges).

## 9. Costs

- Retrospective analyses (sections 2-4) and the D-study: 0 model tokens.
- Pilot E5-P1: 3,241,924 tokens measured over 1,800 cells, equal to the pre-launch median estimate of 3.24M. The
  estimate used cal-1 median delivered tokens per cell: scaffold 1,265, ids-full 3,846, control:3 1,291, cand 1,323.
- Family validation for a generator family (6.3 step 1): about 1,400 cells, 2-4M tokens on SearchQA [estimate].
  Online TPS (step 3) piggybacks on gate rounds: about 2 x n_F cells per candidate.
- A calibration fixture on another benchmark (purpose 2), for example OfficeQA 74 items x 6 texts x 2 runs = 888
  cells: about 4.2-7.0M tokens at v3's 4,690-7,927 delivered tokens per cell [estimate].
- Delivered tokens per cell by arm in cal-1 (mean, including prompt):
  - scaffold 1,302-1,343;
  - ids-full 3,854;
  - seed-only 1,736;
  - cand 1,396;
  - control:1-4 1,287-1,349;
  - seed-rule 1,282;
  - seed-rule3 1,342.

## 10. Recommendation

Adopt now, at zero extra solver cost (serves purposes 1 and 2):

1. **Declare the estimand of every number.** Gate decisions and stage tables that claim "helps on this benchmark"
   are population claims; report them with tau-inclusive CIs (item-cluster bootstrap, or tau-hat from a calibration
   fixture). Fixed-panel CIs only for statements about the panel's own items. (D8 and D11 own the statistical protocol
   and the reporting template; this report supplies the item-level components.)
2. **Items over runs.** 2 runs per item; spend any further budget on more items. At the current panel sizes the
   population MDE at 2 runs is 6.8 (SearchQA, 200) to 12.2 points (ALFWorld, 57); a +5-point generalisation claim needs
   about 220-370 items per benchmark at 2 runs (2.10).
3. **Stratify every panel by the parent's pooled stratum** (always-fail / mixed / always-pass), Neyman allocation with
   pool-share weights, strata re-estimated per benchmark and per round from same-window or pooled multi-session parent
   runs. Read gain and harm per stratum, then combine with population weights.
4. **Dead-item rule:** drop only items that fail under every text of a >= 9-text calibration fixture over >= 20 runs
   (19/200 on SearchQA). Never drop always-pass items; never select "most movable" items; never drop on a 2-run
   pre-screen.
5. **Do not use IRT compression (tinyBenchmarks, metabench, PromptEval, anchor points) for Skill-text contrasts.**
   Their additive or low-dimensional models are contradicted here (interaction 72 % of excess deviance, 9/9 residual
   dimensions above null, p-IRT no better than random, anchors biased on new texts).

Build next (purpose 1, the verification side):

6. **Make the verifier's evolving artifact a set of generator families with a pre-registered validity gate**
   (TPS_F >= 0.80, |alpha_F| <= 4 points at n_F = 100 against the 9 cal-1 texts' real-pool deltas). First experiment:
   one SearchQA family with guaranteed answers (D6 supplies the generator), about 2,000 cells, 3-4M tokens; admit or
   reject by the pre-registered bar; then one OfficeQA family against a 6-text OfficeQA fixture on the training pool.
   Online: after admission, every gate round appends (family delta, real delta) pairs and demotes families whose
   error leaves the bound. Report TPS_F and calibration error over rounds as the verifier's learning curve.
7. **Steer generation by stratum,** not by count: generated pools are ceiling-heavy (67 % of the b06 SearchQA items
   pass every deepseek cell); request items that the parent solves sometimes (gain evidence) or always (harm evidence),
   and weight admitted items to the real pool's stratum shares.

Purpose 2 (generalisation metric):

8. **Size cross-benchmark panels by the D-study** and report per benchmark: population estimate, tau-inclusive CI,
   per-stratum readout, benchmark-specific strata weights. The cross-benchmark TPS_X (family on b vs real training pool
   of c) may choose which evolution-side items to train on; the post-hoc evaluation on the other benchmarks stays
   untouched.

9. **Pre-screen rule (from the pilot).** Use the parent's 2-run pre-screen for Neyman allocation and for a separate
   harm readout on its always-pass class. Never use it to drop items. Take the gain stratum from pooled multi-run
   parent cells where they exist (train + screen + confirm), and check the paired scaffold offset in every round.
10. **Feasibility of this direction: medium.**
    - The panel rules are free and confirmed on fresh items.
    - Item-level transfer-predictive selection is not feasible: reliability 0.33, IRT contradicted.
    - The family-level validity gate is feasible at about 3-4M tokens per family, but untested on a real generated
      family.

## 11. References (all checked in this session unless marked)

- Polo, Weber, Choshen, Sun, Xu, Yurochkin. tinyBenchmarks: evaluating LLMs with fewer examples. ICML 2024.
  arXiv:2402.14992.
- Kipnis, Voudouris, Schulze Buschoff, Schulz. metabench -- A Sparse Benchmark of Reasoning and Knowledge in Large
  Language Models. ICLR 2025. arXiv:2407.12844.
- Hofmann et al. Fluid Language Model Benchmarking. 2025. arXiv:2509.11106 (AI2).
- Heineman et al. Signal and Noise: A Framework for Reducing Uncertainty in Language Model Evaluation. 2025 (the arXiv
  page shows no venue).
  arXiv:2508.13144.
- Polo et al. Efficient multi-prompt evaluation of LLMs (PromptEval). NeurIPS 2024. arXiv:2405.17202.
- Vivek, Ethayarajh, Yang, Kiela. Anchor Points: Benchmarking Models with Much Fewer Examples. EACL 2024.
  arXiv:2309.08638.
- Rodriguez, Barrow, Hoyle, Lalor, Jia, Boyd-Graber. Evaluation Examples Are Not Equally Informative: How Should That
  Change NLP Leaderboards? ACL 2021 (2021.acl-long.346).
- Vania, Htut, Huang, Mungra, Pang, Phang, Liu, Cho, Bowman. Comparing Test Sets with Item Response Theory.
  ACL-IJCNLP 2021, pp. 1141-1158 (2021.acl-long.92).
- Madaan et al. Quantifying Variance in Evaluation Benchmarks. 2024. arXiv:2406.10229.
- Miller. Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations. 2024. arXiv:2411.00640.
- Truong et al. Reliable and Efficient Amortized Model-based Evaluation. 2025. arXiv:2503.13335 (venue not shown on
  the arXiv page).
- Perlitz et al. Efficient Benchmarking (of Language Models). NAACL 2024. arXiv:2308.11696.
- Glas, van der Linden. Computerized Adaptive Testing With Item Cloning. Applied Psychological Measurement 27(4), 2003.
- Sinharay, Johnson, Williamson. Calibrating Item Families and Summarizing the Results Using Family Expected Response
  Functions. J. Educational and Behavioral Statistics 28(4):295-313, 2003.
- Geerlings, Glas, van der Linden. Modeling Rule-Based Item Generation. Psychometrika 76(2):337-359, 2011.
- Lalor, Wu, Yu. Building an Evaluation Scale using Item Response Theory. EMNLP 2016, pp. 648-657 (title and venue
  checked; abstract not read).
- Brennan. Generalizability Theory. Springer, 2001 (standard text; not re-checked).
- Project documents (read only): `docs/handoff/cal1-registration-20261020.md` (with the 23:43 analysis),
  `docs/handoff/coevo5-registration-20261016.md` section 2, `docs/project-status.md`, `skillopt/coevo5/{protocol,data,
  step,units,cells,outcomes}.py` in the frozen snapshot `/data/coevo5-20261019-v3-source-f`; batch-1 reports D5, D8
  (scratchpad `feas/D5`, `feas/D8`).

## 12. Artifacts

Mac (main session's scratchpad), `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E5/`:

- `report.md` (this report); `report_draft.md` and `report_part{1,2,3}.md` are the earlier drafts, kept unedited.
- `scripts/` (0-token analyses; same copies under `/data/feasibility/E5/v2/scripts/` on the new machine):
  - extraction: `e5_cal1_extract.py`, `e5_probe_extract.py` (ran on the old machine, read-only on the run
    directories), `e5_v3_extract.py` (new machine);
  - analyses: `e5_searchqa.py` (2.1-2.4), `e5_signal.py` (2.5), `e5_irt.py` (2.6), `e5_features.py` (2.7-2.8),
    `e5_panels.py` (2.9), `e5_dstudy.py` (2.10), `e5_otherbench.py` (3), `e5_generated.py` (4), `e5_tps_sim.py` (6.2),
    `e5_checks.py` (identity and session checks), `e5_common.py`;
  - `e5_items.py`, `e5_load.py`, `e5_items_features.py`: first-pass versions, superseded.
- `results/`: `searchqa_summary.json`, `searchqa_signal.json`, `searchqa_irt.json`, `searchqa_irt_items.csv`,
  `searchqa_features.json`, `searchqa_item_properties.csv`, `searchqa_items.csv`, `searchqa_panels.json`,
  `dstudy.json`, `otherbench.json`, `generated_vs_real.json`, `tps_sim.json`, `checks.json`.
- `data/`: `cal1_cells.csv` (8,800 + 400 cells), `probe_cells.csv` (15,096 cells) and their meta files.
- `pilot/`: `e5p1_run.py` (v1), `e5p1_run_v11.py` (v1.1, used), `e5p1_analyse.py`, `analysis_plan.json`,
  `analysis_plan_notes.json`, `cal1_reference.json`, `prereg_hashes.txt`, `relay_and_launch_old.sh` (never ran),
  `strata_run1.json` (frozen strata, sha256 3a27d071...), `final/pilot_results.json` (pre-registered analysis),
  `final/pilot_windows.json` (exploratory per-window split).
- `verify/`: `e5_verify_independent.py` (independent re-computation, section 1), `e5p1_halves.py` (exploratory
  window split), `merge_and_analyse.sh` (merge of the two machines' cells and both analyses),
  `apply_corrections.py` (the corrections applied to the draft).

New machine (`<datatools-login>`):

- `/data/feasibility/E5/v2/`: data, scripts, results, logs; `pilot/run1/` = phase A (360 cells) and phase B draw
  positions 0-135 (1,080 cells), `run1.log` (v1, stopped), `run1-v11.log`, `run1-b2.log` (resumed half).
- `/data/feasibility/E5/v3-final/`: `pilot-merged/run1/` (all 1,800 pilot cells; the old machine's 360 added
  read-only), `pilot_results.json` and `.log`, `pilot_windows.json` and `.log`, `verify/` (independent check and log).

Old machine (`PJ-CL4MIND-DULIN`): `/data/feasibility-scratch/E5/` (extraction scripts and CSVs;
`pilot/run1/` = phase B draw positions 135-180, 360 cells, `run1.log`).
