# E2: a single-source transfer matrix (evolve on one benchmark, evaluate on the others)

Explorer E2, batch 2. Written 2026-10-21, 05:10 to 05:30 HKT. It serves the owner's **purpose 2**: the metric is generalisation, so a chain evolves on ONE benchmark and is scored on the OTHER benchmarks.

Labels used throughout:
- **[measured]**: recomputed by me from records on disk, with denominators.
- **[published]**: copied from a repository document that the owner has already opened.
- **[estimate]**: arithmetic from measured inputs plus stated assumptions.
- **[claim]**: a design proposal or an interpretation.

I opened no test or holdout pool. The v1 test-panel numbers below come from the published v1 results document (`docs/handoff/coevo5-v1-results-20261019.md`), not from records.

## 0. Bottom line

1. **The design is buildable but expensive, and today it would measure nothing new.** [claim]
   - Two prerequisites are missing.
     - (a) Learning must actually change the Skill. In v3 both chains accepted 0 rules, so every learned-minus-seed cell of a v3 matrix is exactly 0.
     - (b) Every arm must be evaluated **interleaved in the same serving session**. The current stage-by-stage evaluation, which reuses earlier records, is invalid for comparisons.
   - Feasibility: **medium**.
2. **A first row of the matrix already exists (v1, GLM solver, test panels; SearchQA was the only source at stage 1).** [published]
   - The three single-source Skills learned on SearchQA (our E-glm s1, GEPA s1, SkillOpt s1) all gain **+18.6 to +20.3 points** on OfficeQA versus no Skill.
   - Against the five hand-written task cards (I5) they are **-1.7 to 0.0**.
   - On SpreadsheetBench they are **-13.3 to -16.7 versus the cards** and -4.0 to -7.4 versus no Skill.
   - Mean over the four other benchmarks:
     - versus no Skill: +2.0 (GEPA), +3.2 (SkillOpt), +3.2 (ours);
     - versus the cards: -4.4, -3.2, -3.2.
   - **So the choice of reference flips the sign.** The +19 on OfficeQA is an answer-format effect that any instruction text produces. The v1 report already says so.
   - These three Skills started from the blank Skill, so "versus their seed" equals "versus no Skill". Without OfficeQA their off-diagonal mean is -1.9 to -3.7.
   - The v1 I-start chain (five cards) accepted no rule at any stage, so its learned row is 0.
3. **The reference must be the task-card seed. No Skill is a secondary reference only.** [claim]
   - Add two controls inside the same session:
     - a byte-identical duplicate of the card arm, as a noise canary;
     - a length-matched placebo.
   - Measured reasons:
     - cal-1 placebo texts alone move SearchQA by -10.1 to +3.4 points. [measured]
     - A byte-identical duplicate arm differed by -7.0 points (p = 0.031) on LiveMath in a fully shuffled pilot. [measured]
4. **Serving drift is large and depends on the benchmark.** [measured]
   - The I5 parent's OfficeQA panel (60 items, 60/60 identical request hashes) dropped from 0.508 to 0.267 between two v3 windows (01:35-02:04 and 02:28-03:09). That is -24.2 points, 2 up / 20 down, p = 0.0001. Answer-only replies went from 10% to 84% of cells.
   - In the same windows, the same parent's SearchQA panel did not move (-2.5 / +1.67).
   - On OfficeQA the scaffold also moves about 20 points between the two serving modes (+19.7, earlier pass), so there the shift is roughly common-mode.
   - On SearchQA the shift depends on the Skill text. D5: the scaffold scores about 5.7 points higher in terse than in verbose sessions, while the format-pinning card is unaffected.
   - Item-blocked interleaving, with all arms of an item adjacent in time, is the minimum fix. It cancels the common-mode part. The text-dependent part remains, so results must also be stratified by serving regime.
5. **Where a single-source rule is placed changes transfer by up to 15 points, and the direction depends on the target.** [measured]
   - Moving the SearchQA card from its own section to a "General / any task" section changed OfficeQA by +14.9 [+5.4, +24.3] but LiveMath by -7.0 [-13.0, -2.0].
   - For three v3 candidate rules on LiveMath the placement made no difference: 0.0 [-6, +6].
   - A bench's own section is not a firewall: text under the SearchQA header still moved LiveMath by +6.0 and OfficeQA by -4.1, and it changed the share of answer-only replies.
6. **Power (from cal-1 and v3 noise components).** [estimate]
   - One source row, mean of the 4 off-diagonal deltas, 1 run on the test panels: SE about 1.5-1.7 points, minimum detectable effect (MDE; 80% power, two-sided 5%) about **4.2-4.7 points**.
   - Same row with 2 runs and target test + target training pool (both unseen by that chain): SE about 0.86-1.03, MDE about **2.4-2.9**.
   - The whole 5-row matrix mean: MDE 1.2-1.9.
   - Learned-on-top effects seen so far are about +3 to +5 and not significant (v8-v11). A meaningful matrix therefore needs 2 runs, the extra training-pool items, and at least 2 replicate chains per source.
7. **Cost (deepseek tokens, v3 ledger rates).** [estimate]
   - Minimal SearchQA row with 3 chains: about **264M**.
   - QA core (3 sources x 2 chains x 3 steps): about **381M**.
   - The same with all five targets: about 793M.
   - Full 5x5 matrix: about 1.57 billion.
   - For comparison, the whole v3 run settled 139M deepseek tokens.
   - The cheapest informative first step needs no new learning: re-evaluate the existing v1 single-source Skills in one interleaved session, about 48-95M (section 5.3).
8. **Code change: medium-large, about 800-1,300 lines including tests.** [estimate]
   - `ORDER[stage - 1]` appears about 120 times across 17 modules, and the stage index drives regression panels, similar placement, readouts and reports.
   - A new protocol version and a new output directory are required. v3 stays frozen.
9. **Pilot run this session.** [measured, partial]
   - The SearchQA-learned GEPA Skill, the five cards, both combined, and no Skill, on the OfficeQA training pool (74 items), deepseek-v4-flash, item-blocked in one session.
   - The shared deepseek route rate-limited it (one 300-second all-429 window), and it was cut for the deadline. That left 24 complete item blocks (run 0 only) and 0.93M tokens.
   - **Inconclusive:** CI half-widths are about ±17 points. G - N = 0.0 [-16.7, +16.7]; G - I5 = +8.3 [-8.3, +25.0]; I5G - I5 = +4.2 [-8.3, +20.8].
   - Descriptively, no Skill was not format-deficient with deepseek (N 37.5% = G 37.5%), unlike v1 with GLM.
   - Combining the SearchQA-learned text with the cards made 50% of replies answer-only (cards alone 12.5%, GEPA text alone 0%). See section 2.8.

## 1. What was asked and how this direction serves purpose 2

Owner's purpose 2 (context-batch2): "评测指标是泛化性 … 必须还是要在一个bench上进化，然后其余bench上评测" (the metric is generalisation; the evolution must still happen on one benchmark and be evaluated on the remaining benchmarks).

E2 turns this into a protocol:
- a **k x k transfer matrix** R[s][t] = score on target t of a Skill evolved only on source s;
- a **generalisation score** per row (mean of the off-diagonal deltas), with paired item-level confidence intervals, against the task-card seed and against no Skill;
- registered similar and dissimilar subsets, using the v6 similarity map.

## 2. Verified evidence

### 2.1 The existing single-source row (v1, GLM-5.3 solver, test panels, 1 run) [published]

Source: `docs/handoff/coevo5-v1-results-20261019.md`. Every stage-1 Skill was learned on SearchQA only, so these are SearchQA-source rows.

Test-panel denominators:
- SearchQA 400, OfficeQA 172, LiveMath 125, ALFWorld 134.
- SpreadsheetBench: 194-199 scored items, depending on the arm (No Skill 125/199, cards 142/197, E-glm 112/198, GEPA 108/195, SkillOpt 114/194). The Sheet cells therefore compare slightly different item sets.

Starting points: the E-glm, GEPA and SkillOpt chains all started from the **blank Skill** ("起点：空白 Skill（三条链共用）", the starting point shared by the three chains). For them, "versus the seed" equals "versus no Skill". The I-start chain (I-glm, five cards) accepted **no rule at any of the 5 stages**, so its learned-minus-seed row is 0 everywhere. E-glm accepted 2 rules at stage 1 and none afterwards.

Absolute scores (%):

| Skill | SearchQA | OfficeQA | LiveMath | SpreadsheetBench | ALFWorld |
|---|---|---|---|---|---|
| No Skill | 72.5 | 29.1 | 40.0 | 62.8 | 88.8 |
| Five task cards (I-glm s0) | 87.3 | 49.4 | 36.0 | 72.1 | 88.8 |
| E-glm s1 (ours, 2 SearchQA rules) | 85.3 | 49.4 | 40.8 | 56.6 | 86.6 |
| GEPA-glm s1 (4,325 B SearchQA prompt) | 89.0 | 48.3 | 38.4 | 55.4 | 86.6 |
| SkillOpt-glm s1 (7,526 B) | 88.0 | 47.7 | 35.2 | 58.8 | 91.8 |

Off-diagonal deltas (points; my arithmetic on the published numbers):

| Skill (source SearchQA) | ref | OfficeQA | LiveMath | Sheet | ALFWorld | **mean of 4** |
|---|---|---|---|---|---|---|
| E-glm s1 | vs No Skill | +20.3 | +0.8 | -6.2 | -2.2 | **+3.2** |
| E-glm s1 | vs cards | 0.0 | +4.8 | -15.5 | -2.2 | **-3.2** |
| GEPA s1 | vs No Skill | +19.2 | -1.6 | -7.4 | -2.2 | **+2.0** |
| GEPA s1 | vs cards | -1.1 | +2.4 | -16.7 | -2.2 | **-4.4** |
| SkillOpt s1 | vs No Skill | +18.6 | -4.8 | -4.0 | +3.0 | **+3.2** |
| SkillOpt s1 | vs cards | -1.7 | -0.8 | -13.3 | +3.0 | **-3.2** |
| (cards themselves) | vs No Skill | +20.3 | -4.0 | +9.3 | 0.0 | +6.4 |

How to read this:
- Because the three Skills started blank, their "versus seed" off-diagonal mean is the "versus no Skill" one: +2.0 to +3.2. That mean is driven entirely by OfficeQA. Without OfficeQA, the mean over LiveMath, Sheet and ALFWorld is -2.5 (E-glm), -3.7 (GEPA) and -1.9 (SkillOpt) versus no Skill.
- No item-level confidence intervals exist without opening the test records, which is forbidden. My per-target SE estimate at 1 run on the test panel is 1.7-3.5 points (section 4). It uses deepseek noise components; GLM noise may differ. Single cells within about ±5 are therefore not distinguishable from 0.
- The SpreadsheetBench gap versus the cards (-13 to -17) is far outside that noise. It is negative transfer relative to the cards. The single-source Skills lack the Sheet card, and at least GEPA s1 and E-glm s1 contain explicit "answer with ONLY a short answer in the tags" instructions (read from their v1 learning units). They are also -4.0 to -7.4 below no Skill there.
- The registered E-glm transfer readouts were Q1 (own bench) +2.6 [+1.8, +3.4], Q2 (similar) +4.1 [+2.4, +5.7], Q3 (rest) -0.6 [-1.3, +0.2]. The v1 report itself says these come almost entirely from the two "write a short answer" SearchQA rules lifting OfficeQA from 29.1 to 49.4. The cards and both baselines produce the same lift, so it is an answer-format effect, not learned transfer.
- Earlier (v10, GLM), a rerun of No Skill alone moved BCB by +7 and QA by +6 (`docs/results-and-lessons.md`). Cross-window no-Skill references are unusable.

### 2.2 The reference problem [claim, from 2.1 and 2.6]

"Versus No Skill" off-diagonal transfer is dominated by any-text and format effects:
- every Skill, the cards included, gains about +19-20 on OfficeQA;
- cal-1 placebos move SearchQA by -10.1 to +3.4.

The learned increment is what the paper needs, so the reference must be the **seed** the chain started from (I5 for I-start chains), on the same items in the same session. The no-Skill delta is still reported, as the "absolute usefulness" of the final text.

### 2.3 Serving drift on the training-side panels (v3, deepseek-v4-flash) [measured]

Records: v3 training-side screen and confirm units only (no `evaluation/` paths). Request hashes were recomputed.

| Panel | Window A | Window B | Δ (B-A) | Items up/down | p |
|---|---|---|---|---|---|
| I-ds parent (I5), OfficeQA panel, 60 items | s3 screen 01:35-02:04, answer-only share 0.10, pass 0.508 | s4 screen 02:28-03:09, answer-only 0.842, pass 0.267 | **-24.17 [-35.8, -12.5]** | 2 / 20 | 0.0001 |
| same, s4 confirm | | | -24.17 | | |
| same, s5 screen | | | -16.67 | | 0.0026 |
| I-ds parent, SearchQA panel, same windows | | | -2.5 / +1.67 | | n.s. |
| E-ds parent (scaffold), OfficeQA, v3 terse windows | s2 0.203 | s3 0.242, s4 0.267 | n.s. | | |

- Request identity: 60/60 identical request hashes for the I-ds OfficeQA rows.
- Answer-only means 20 completion tokens or fewer.
- In addition, the earlier E2 pass (not re-recomputed by me) found the scaffold arm in a verbose window (10/20 evening) +19.7 [+9.9, +30.3] (p = 0.0026) above the v3 E-ds train cells, with 74/74 identical request hashes. So the scaffold is also not immune once the window changes from terse to verbose.
- Implications:
  - (i) A comparison between two arms measured in different windows can be off by 20+ points.
  - (ii) The drift is not a constant offset across benchmarks. In the same windows the same parent did not move on SearchQA (-2.5 / +1.67).
  - (iii) It also depends on the Skill text on SearchQA. D5: the scaffold is about 5.7 points higher in terse sessions, while the card is unaffected. Note the direction: terse helps the scaffold on SearchQA but hurts both texts on OfficeQA.
  - (iv) On OfficeQA both texts move about 20 points: the card Skill -24.2 from verbose to terse; the scaffold +19.7 from terse to verbose.
  - (v) Interleaving cancels the common-mode part but not the text-dependent part. Results should be stratified by regime (answer-only share per block).

### 2.4 Placement pilot (earlier E2 pass, my independent recompute; truncation counted as fail) [measured]

- One session, 10/20 19:26-20:16, 1,370 cells, 4,166,774 tokens, deepseek-v4-flash.
- Training pools only: LiveMath 100 items x 2 runs; OfficeQA 74 items x 1 run.
- Arms:
  - P: scaffold, 593 B.
  - S_home: SearchQA card in the SearchQA section.
  - S_general: SearchQA card in a "## General / Applies when: any task" section.
  - O_home: OfficeQA card in its own section.
  - L_home: LiveMath card in its own section.
- The dispatch was fully shuffled.

| Contrast (points) | LiveMath (n=100, r=2) | OfficeQA (n=74, r=1) |
|---|---|---|
| S_home - P | +6.0 [+0.5, +11.5] | -4.05 [-14.9, +6.8] |
| S_general - P | -1.0 [-6.5, +4.5] | +10.81 [+1.35, +21.62], p=0.057 |
| O_home - P | +3.0 | +13.51 [+4.05, +22.97], p=0.013 |
| L_home - P | +7.0 [+1.0, +13.5] | -8.11 [-17.6, +1.35] |
| **S_general - S_home** | **-7.0 [-13.0, -2.0], p=0.035** | **+14.86 [+5.4, +24.3], p=0.0074** |
| O_home - S_general | | +2.7 [-5.4, +10.8] |

OfficeQA answer-only replies by arm (of 74): P 17, S_home 31, S_general 13, O_home 0, L_home 42.

The arms that pushed the solver into terse mode did worst on OfficeQA. The effect of a card on another bench runs largely through the **response mode**, not through its content.

### 2.5 Seeded pilot with learned rules on top of the cards (LiveMath, n=100, r=2) [measured]

- One session, 10/21 00:06-02:49, 1,200 cells, 4,149,499 tokens.
- Arms:
  - P: 593 B.
  - L1: 2,664 B.
  - I5: 12,681 B, sha256 cd3944ac26a2...
  - **I5b: byte-identical to I5**, same sha256.
  - R_home: I5 + 3 SearchQA rules proposed by the v3 I-ds stage-1 step (s1-r1, s1-r2, s1-r4; candidates only, since v3 accepted none) in the SearchQA section, 13,986 B.
  - R_gen: the same rules in a General section, 14,022 B.
- Fully shuffled dispatch with 6 workers.

| Contrast | Δ points [95% CI] | up/down | p |
|---|---|---|---|
| **I5b - I5 (same bytes)** | **-7.0 [-12.5, -1.5]** | 4 / 14 | **0.031** |
| R_home - I5 | -8.0 | | 0.017 |
| R_gen - I5 | -8.0 | | 0.0026 |
| R_home - mean(I5, I5b) | -4.42 [-10.0, +0.83] | | n.s. |
| R_gen - mean(I5, I5b) | -4.42 [-9.1, +0.25] | | n.s. |
| R_gen - R_home | 0.0 [-6, +6] | | |
| L1 - P | +6.0 [-1, +13] | | |
| Cross-window same text (P; L1) | +0.5; -0.5 | | stable |

Lessons:
- A byte-identical arm produced a "significant" -7 points. Had I5b been a learned candidate, it would have been rejected with p = 0.03. Every matrix session therefore needs a duplicate-arm canary, and dispatch should be item-blocked rather than fully shuffled.
- Measured against the pooled two-copy reference, the SearchQA candidate rules change LiveMath by -4.4 (n.s.). No evidence of positive transfer; weak evidence of harm.

### 2.6 cal-1 noise components (old machine, 8,800 cells, 8,785 with verdicts; 200 SearchQA items x 4 runs x 11 arms) [measured]

My recompute matches the earlier one.
- Same text twice (parent:A vs parent:B): +0.77 [-1.15, +2.81]; σ²_int ≈ 0 (-0.008).
- SearchQA card alone - parent: +8.97 [+5.38, +12.69].
- Full five cards - parent: +9.14 [+4.82, +13.45].
- Full - card alone: -0.13 [-3.06, +2.81]. The other four cards are inert on SearchQA.
- Card + one rule-shaped addition - card: -8.76 [-12.4, -5.3]. With three additions: -11.48 [-15.2, -7.9].
- Candidate - parent: -2.31.
- Placebo texts versus parent: -3.79 [-6.8, -1.0], +3.41 [+0.5, +6.4], -10.1 [-14.0, -6.3], 0.0.
- σ²_run (within-item run variance per arm): scaffold 0.052-0.060; card arms 0.024-0.026; rule and placebo arms 0.04-0.08.
- σ²_int (item heterogeneity of a true difference): 0.035-0.077.

### 2.7 Per-bench variance inputs used for power [measured, partly assumed]

- σ²_run comes from the v3 training units (one session, 2 runs), I-ds/E-ds:
  - SearchQA 0.045/0.0175, plus cal-1 card arms 0.025;
  - OfficeQA 0.047/0.041;
  - LiveMath 0.080/0.065;
  - ALFWorld 0.070/0.070;
  - SpreadsheetBench has 1 run only (assumed 0.08).
- σ²_int:
  - SearchQA: cal-1 seed vs seed-rule, 0.048.
  - LiveMath: I5 vs learned-rule arms, 0.016-0.027 (used 0.025).
  - OfficeQA: 0.06-0.18 from the 1-run pilot pairs (**assumed 0.10**).
  - SpreadsheetBench about 0.05 and ALFWorld about 0.015 (**assumed**).
- Inputs (σ²_int, σ²_run): SearchQA (0.048, 0.035), OfficeQA (0.10, 0.044), LiveMath (0.025, 0.065), SpreadsheetBench (0.05, 0.08), ALFWorld (0.015, 0.070).

### 2.8 Row pilot this session: SearchQA-learned text applied to OfficeQA (deepseek, one session, item-blocked) [measured, partial]

Setup:
- Script `/data/feasibility/E2/scripts/pilot_row_officeqa.py`; records in `/data/feasibility/E2/pilot-row-officeqa/`.
- Model: deepseek-v4-flash, temperature 0, max_tokens 32768, PJLAB token route. The client is built the same way as in the placement pilot, whose requests matched v3 byte for byte (74/74).
- Items: the 74 OfficeQA **training-pool** items (`data.training_items`, v3 manifest).
- Arms:
  - N: no Skill.
  - I5: the five cards, 12,681 B. Its digest equals the v3 I-ds parent's (preflight check passed).
  - G: the v1 GEPA-glm stage-1 Skill, learned on SearchQA only, 4,325 B. Its sha256 matches the v1 record (preflight check passed).
  - I5G: G placed as a General section on top of I5, 17,044 B.
- Dispatch: item-blocked, so all 4 arms of an item are adjacent in time. Run 0 for every item comes before run 1. 2 runs were planned, with a 4.6M token cap.
- History:
  - The first launch (fully shuffled, 4 workers) wrote 14 records under HTTP 429 back-off and was stopped.
  - The relaunch at 05:00 (6 workers) aborted at its first cell after 300 s of 429. The receipt is kept in `infra-failures/0507/`.
  - The relaunch at 05:09 (3 workers, 32-minute cap) produced the cells below. I stopped it at 05:26:15 for the workflow deadline (`stop.json`).

Counts:
- Valid records: 105. Infrastructure failures inside the records: 0. Truncated replies, counted as fail: 8.
- Tokens recorded: 927,095, plus a few in-flight calls lost at stops.
- **Complete item blocks: 24** (run 0: 24; run 1: 0), over 24 distinct items. Cell window 04:54:39-05:26:11 HKT.

| arm | pass rate on complete blocks (%) | answer-only share | median completion tokens |
|---|---|---|---|
| N | 37.5 | 0.0 | 450.0 |
| I5 | 29.17 | 0.125 | 357.0 |
| G | 37.5 | 0.0 | 582.0 |
| I5G | 33.33 | 0.5 | 64.0 |

| paired contrast on the same items (points) | Δ [95% bootstrap CI] | items up / down | sign-test p |
|---|---|---|---|
| G - N: SearchQA-learned text vs no Skill | +0.00 [-16.67, +16.67] | 2 / 2 | 1 |
| I5 - N: cards vs no Skill | -8.33 [-25.00, +8.33] | 1 / 3 | 0.625 |
| G - I5: SearchQA-learned text vs cards | +8.33 [-8.33, +25.00] | 3 / 1 | 0.625 |
| **I5G - I5: learned text added on top of the cards** | +4.17 [-8.33, +20.83] | 2 / 1 | 1 |
| I5G - N | -4.17 [-25.00, +16.67] | 3 / 4 | 1 |

Reading (honest):
- **Inconclusive.** 24 items x 1 run gives 95% CI half-widths of about ±17 points, so the pilot can neither confirm nor exclude effects below about 15 points. Run 1 was never reached. This is not a measurement of transfer, and no difference above should be read as an effect.
- Descriptive observation 1: in this deepseek window **no Skill is not format-deficient** on the OfficeQA training pool. N 37.5% equals G 37.5%; G - N = 0.0 with 2 items up and 2 down. The v1 GLM pattern (+19 to +20 for any Skill versus no Skill on OfficeQA) does not appear. The "format effect" is solver- and/or window-dependent. A deepseek D0 may therefore not reproduce the v1 row, and that would itself be a finding about what single-source text carries.
- Descriptive observation 2: **the combination changes the response mode non-additively.**
  - G alone: 0% answer-only, median 582 completion tokens.
  - I5 alone: 12.5% answer-only, median 357.
  - I5G (the GEPA text as a General section on top of the cards): **50% answer-only, median 64 completion tokens.**
  - This mirrors the placement pilot (2.4), where text under another bench's header changed OfficeQA's answer-only share from 17/74 to 31/74. What a single-source text transfers is first of all response format, and its effect depends on what else is in the Skill.
- Cost: 927,095 tokens recorded across 105 valid cells, plus a few in-flight calls lost at the two stops. 8 replies were truncated and counted as fail.
- Caveat: a few blocks combine cells from the first launch (04:54-04:59) with cells from the relaunch (05:09-05:26), so those cells are up to about 30 minutes apart.
- To finish the planned 592 cells, the same command resumes, because existing records are skipped. It needs about 4M more tokens and about 1.5-2 hours at 3 workers on the shared route.

## 3. Protocol design [claim]

### 3.1 Chains

- **Sources.**
  - QA core S = {SearchQA, OfficeQA, LiveMath}: the three single-call question-answering benches. They contain two of the three registered similar pairs, (SearchQA, OfficeQA) and (OfficeQA, LiveMath). The third, (OfficeQA, SpreadsheetBench), needs SpreadsheetBench as a target, which designs B, C and D include.
  - Optionally SpreadsheetBench, and ALFWorld last: an ALFWorld I-start learning step cost 59.4M deepseek tokens in v3.
- **Per source:** R = 2 replicate chains (3 if affordable) of the main method.
  - Each replicate gets a different training-batch seed and K = 3 steps, with a fresh training batch per step (the D1 acceptance protocol).
  - Replicates are needed because learning is stochastic. The between-chain SD τ of the true transfer score is unknown and is measured from the replicates (section 4.3).
- **Start.**
  - **I-start (primary):** the five-card Skill I5 (12,681 B, the v3 I-ds parent). This is the realistic deployment start, and it makes "learned beyond the cards" directly measurable.
  - **E-start (secondary):** the 593 B scaffold. This is where single-source rules most plausibly transfer, but mainly as format effects.
- **Baselines, same source, same seed, same rollout budget:** GEPA and SkillOpt-prior (the repository's earlier SkillOpt baseline, `SkillOpt-glm` in `units.CHAINS`), one run per source.
  - GEPA and SkillOpt output a whole prompt, so it is evaluated two ways:
    - (a) as the whole Skill (what v1 did);
    - (b) embedded in a General section on top of I5 (arms "G" and "I5G" in the 2.8 pilot).
  - Otherwise the baselines lose the other benches' cards and look worse for a trivial reason (the Sheet -13 to -17 in 2.1).
- **References, no learning:**
  - No Skill (N);
  - the seed (I5; the scaffold for E-start);
  - **I5b**, a byte-identical duplicate of I5 that serves as the noise canary;
  - **a length-matched placebo** in the General section (4 KB of irrelevant but well-formed text).

### 3.2 Skill organisation with one source

- Current code: five bench sections with fixed "Applies when" lines, no shared section, rules at most 600 characters, each rule with a `home` and an `also` list. Placement into similar sections (`also`) relies on regression checks on those benches' training items.
- In a single-source design the chain must never see target data. Otherwise the off-diagonal is no longer out-of-sample. So:
  1. **Source section:** the source card (seed) plus rules learned on the source.
  2. **New "General" section** ("Applies when: any task"). A learned rule may be placed here when the learner judges, **from source evidence only**, that it is not source-specific. This is the only legitimate channel for intended transfer.
  3. **Other bench sections:** frozen seeds (cards for I-start, empty for E-start). The learner never writes into them, and `also` placement into similar sections is disabled. With no target data it would be blind.
  4. Rules may carry their own "when" predicate (D4's rules-as-classifiers), so a General rule applies only where its condition holds.
- Evidence that placement must be treated as an experimental factor, not a fixed convention:
  - the ±15-point target-dependent placement effect (2.4);
  - the leakage of "home" text into other benches (S_home moved LiveMath by +6.0 and changed OfficeQA's answer-only share from 17/74 to 31/74).
- Recommendation: for the primary chains, evaluate each final Skill **as learned** and **with every learned rule moved to its home section** (one extra arm per chain). The difference measures how much transfer depends on the General channel.

### 3.3 The learning loop per chain

- Reuse the v3 step machinery unchanged in content: train, halves, examiner, analyst, prepare/leakage, selftest, screen (C1-C4'), confirm, composite, merge.
- Fix `bench = source` for every step.
- Regression and do-no-harm panels come **from the source only**. v3's `regression_keys(stage)` used `ORDER[:stage-1]` (all earlier benches), which would contaminate the targets.
- No per-step five-panel evaluation. In v3 the stage-0 sweep alone cost 21.3M deepseek tokens for I-ds; later stages reused it because the Skill never changed. Per-step sweeps are also invalid for comparisons because of drift and reuse. Per-step monitoring, if wanted, runs on the source's training panels only.
- Acceptance follows D1 (fresh-batch, version-level acceptance). Without an acceptance rule that ever says yes, every learned-minus-seed cell is identically 0.

### 3.4 Evaluation: one matrix round, interleaved

- After all chains finish, one **matrix round** evaluates every arm on every target panel. Arms: learned finals, relocated variants, baselines (as-is and I5+), N, I5, I5b, placebo.
- **Item-blocked dispatch:** items are shuffled once; for each run, for each item, all arms run adjacent in time in random order; run 0 for every item before run 1. A partial round still yields complete paired blocks, and drift is shared within a block.
- **r = 2 runs.**
- Panels:
  - Off-diagonal targets use the target **test panel + target training pool**. Both are unseen by the source chain; the chain never touches target data.
  - The diagonal uses the source test panel only. It is a sanity check that learning happened.
  - Test-only results are reported alongside, as the canonical-split view.
  - Whether the train-pool extension is primary or secondary is an **owner decision** (power versus canonical-split purity, section 4).
- **No record reuse** across sessions or rounds. Reuse is allowed only for identical bytes inside the same round.
- **Drift canaries:**
  - I5b - I5 per target, with a registered tolerance: |Δ| ≤ 2 SE, otherwise the round is flagged.
  - The answer-only share (completion ≤ 20 tokens) per block, logged and used for regime stratification.
- Requests are hashed per cell, as in `pilot_row_officeqa.py`.

### 3.5 Scores

For source s, chain c, final Skill F, seed S0, target t ≠ s, item i, run k, with y ∈ {0, 1}:

- d_i(F, X) = mean_k y(F, i, k) - mean_k y(X, i, k): paired at the item level, same session.
- Cell: Δ_{s→t}(X) = 100 * mean_i d_i(F, X), for these references X:
  - **I5, primary.** The five task cards: the seed of I-start chains, and the hand-written alternative for E-start chains, whose own seed is blank.
  - S0: the chain's own seed, when it differs from I5.
  - N: no Skill, secondary.
- **Row generalisation score:** G_all(s) = mean over the 4 targets of Δ_{s→t}(I5), with equal weight per target. SearchQA's 1,000 items must not dominate.
  - 95% CI: stratified paired bootstrap that resamples items within each target, then averages the target means.
  - p-value: paired permutation test.
- **Similar score:** G_sim(s) = mean over the registered similar targets of s. One-sided: is the effect > 0?
- **Dissimilar no-harm:** D_dis(s) = mean over the other targets. Non-inferiority with margin -3 points: the one-sided 95% lower bound must exceed -3. v6 registered -2 for its pooled Q3; for single rows -2 is underpowered (section 4).
- **Self:** Δ_{s→s}(S0) on the source test panel. A row only counts if the self gain is > 0 with a lower bound > 0. Otherwise nothing was learned to transfer.
- **Matrix summaries:**
  - the GEM-style forward-transfer mean over all off-diagonal cells;
  - a heat map of cells with CIs;
  - replicate pooling (random effect for chain).
- **One pre-registered primary:** the mean over QA sources of G_all(I5) for the main method, compared with the same quantity for GEPA and SkillOpt-prior. Everything else is secondary, with Holm correction across rows. Twenty off-diagonal cells times several arms would otherwise generate false positives; the 2.5 canary already shows a -7 from identical bytes.
- **Placebo-corrected:** Δ_{s→t}(I5) - Δ_placebo(t) is reported for General-section transfer, to separate "useful content" from "any extra text".

### 3.6 Success criteria [claim]

The paper may claim learned single-source generalisation only if all four hold:
- (i) Self(s) > 0;
- (ii) the registered primary (the matrix mean of G_all(I5)) > 0 with its CI excluding 0, and G_all(I5) has the same sign in both replicate chains of every contributing row;
- (iii) D_dis non-inferior at -3;
- (iv) the effect exceeds the placebo and survives regime stratification.

A matrix that shows strong deltas versus N but about 0 versus I5 must be reported as "format/any-instruction transfer, not learned transfer". That is what the v1 row shows today.

## 4. Power [estimate]

Model: SE_t(n, r) = 100 * sqrt((σ²_int + 2σ²_run / r) / n), with the inputs from 2.7.

Assumptions:
- Panel sizes:
  - Test: SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 204 (the published v1 Sheet denominators are 194-199 scored items, which makes no material difference), ALFWorld 134.
  - Qualified training pools: 600, 74, 283, 91, 57. SpreadsheetBench's 91 qualified items are carried from the earlier E2 pass; the protocol's nominal pool is 120.
- The MDE uses 2.80 SE (two-sided 5%, 80% power) or 2.49 SE (one-sided).
- All arms interleaved. Drift is treated as common-mode, which 2.3 shows is optimistic.

### 4.1 Per target (one cell)

| target | SE r1 test | SE r2 test | SE r2 test+train |
|---|---|---|---|
| SearchQA | 1.72 | 1.44 | 0.91 |
| OfficeQA | 3.31 | 2.89 | 2.42 |
| LiveMath | 3.52 | 2.68 | 1.49 |
| SpreadsheetBench | 3.21 | 2.52 | 2.10 |
| ALFWorld | 3.40 | 2.52 | 2.11 |

### 4.2 Per source row

G_all is the mean of 4 off-diagonal deltas; G_sim is the similar-only mean.

| source | G_all SE (MDE) r1 test | G_all SE (MDE) r2 test+train | G_sim MDE (1-sided) r1 test / r2 test+train | NI(-3) power at true 0, r1 test / r2 test+train |
|---|---|---|---|---|
| SearchQA | 1.68 (4.71) | 1.03 (2.88) | 8.23 / 6.02 (OfficeQA only) | 0.46 / 0.86 |
| OfficeQA | 1.53 (4.27) | 0.86 (2.41) | 4.20 / 2.26 (3 similar) | 0.22 / 0.41 |
| LiveMath | 1.49 (4.18) | 0.99 (2.76) | 8.23 / 6.02 | 0.56 / 0.89 |
| SpreadsheetBench | 1.54 (4.31) | 0.91 (2.56) | 8.23 / 6.02 | 0.54 / 0.95 |
| ALFWorld | 1.51 (4.23) | 0.91 (2.55) | none | 0.63 / 0.95 |

Matrix-wide mean of all off-diagonal cells, r2 test+train:
- 5 rows: SE 0.42 (rows independent) to 0.67 (row correlation 0.5); MDE 1.2-1.9.
- 3 QA rows: SE 0.55-0.74; MDE 1.6-2.1.

### 4.3 Replicate chains

If the true G differs between replicate chains with SD τ (base SE 1.03, SearchQA row r2 test+train):

| τ (points) | R = 1 | R = 2 | R = 3 |
|---|---|---|---|
| 0 | 2.88 | 2.49 | 2.35 |
| 1 | 4.02 | 3.18 | 2.85 |
| 2 | 6.30 | 4.68 | 4.00 |
| 3 | 8.88 | 6.44 | 5.39 |

The table shows the MDE in points; SE = MDE / 2.8.

Reading:
- The effects seen so far for learned text on top of a good instruction are about +3 to +5 and not significant (v8-v11, context-batch2). The v1 single-source row versus the cards is -3.2 to -4.4.
- A single row at r = 1 on the test panels (MDE about 4.5) cannot detect a realistic positive effect.
- The minimum useful design is r = 2, test + train panels, and R ≥ 2 chains per source. Even then the per-row MDE is about 3-4.7 if τ is 1-2 points.
- The matrix mean (MDE 1.2-1.9) is the only quantity with good power for small effects. That is why it should be the registered primary.
- The OfficeQA row is weak for every non-inferiority question (power 0.22-0.41). Its 74-item pool also limits learning (v3 I-start OfficeQA step: 1.17M deepseek).

## 5. Cost [estimate]

### 5.1 Unit costs

From the v3 ledger (`shared/ledger/state.json`, settled; deepseek is a lower bound) and the measured per-call token sizes.

One arm, full five-target sweep, r = 1, test panels:
- No Skill or scaffold: about 5.7M (ledger 5.06-6.08).
- I5: about 18.6M (ledger I-ds stage-0 evaluation 21.3M).
- I5 + 4 KB learned text: about 22.8M. **ALFWorld is about 76% of an I5 arm's sweep.**

Learning per step (deepseek M / GLM M):

| source | I-start | E-start |
|---|---|---|
| SearchQA | 9.29 / 1.20 | 5.21 / 1.12 |
| OfficeQA | 1.17 / 1.54 | 5.55 / 1.38 |
| LiveMath | 5.64 / 0.66 | 3.14 / 0.63 |
| SpreadsheetBench | 9.75 / 0.40 | 2.46 / 0.39 |
| ALFWorld | 59.43 / 0.25 | 4.91 / 0.24 |

**Cost per chain** with the current pipeline: K = 3 I-start steps, plus the evaluation of that chain's final Skill in the matrix round at r = 2, using the same token model.

| source | learning, 3 steps (deepseek / GLM) | final arm: off-diagonal non-ALFWorld targets, test + train | + ALFWorld as a target (test only) | diagonal (source test) |
|---|---|---|---|---|
| SearchQA | 27.9M / 3.6M | 11.6M | +35.1M | 4.1M |
| OfficeQA | 3.5M / 4.6M | 17.3M | +35.1M | 3.1M |
| LiveMath | 16.9M / 2.0M | 17.7M | +35.1M | 1.2M |
| SpreadsheetBench | 29.2M / 1.2M | 18.6M | +35.1M | 2.2M |
| ALFWorld | 178.3M / 0.8M | 21.7M | none | 35.1M |

How to use this table:
- A relocated-placement variant of a chain's Skill costs its evaluation again.
- The reference arms (N, I5, I5b, placebo) are shared by all chains in the round.
- ALFWorld is the cost driver both as a source and as a target. That is why the QA-core designs leave it out.

### 5.2 Designs

All designs use r = 2, 4 reference arms (N, I5, I5b, placebo) and 2 baselines per source. Off-diagonal panels are test + train unless noted.

| design | learned arms | learning deepseek / GLM | evaluation deepseek | **total deepseek** |
|---|---|---|---|---|
| D: minimal SearchQA row, 3 chains x 3 steps, targets QA + Sheet | 5 | 84M / 10.8M | 180M | **264M** |
| A: QA core, 3 sources x 2 chains x 3 steps, QA targets | 12 | 97M / 20.4M | 285M | **381M** |
| B: as A, all five targets (ALFWorld test only) | 12 | 97M / 20.4M | 697M | **793M** |
| C: five sources x 2 chains x 3 steps, all targets | 20 | 512M / 24.3M | 1,062M | **1,574M** |

Notes on the table:
- Learning uses the I-start per-step rates for every chain.
- The baselines' own optimisation is **not** included. Add about 11M per source: v1 used 2.66M tokens for GEPA s1 and 8.43M for SkillOpt s1, then with the GLM solver.

For scale, the whole v3 run settled 139.0M deepseek and 7.8M GLM tokens.

### 5.3 Cheapest informative first step: D0, a replay row with no new learning

- Re-evaluate the existing v1 SearchQA-source Skills (E-glm s1, GEPA s1, SkillOpt s1; their learning-unit texts exist on disk) with the deepseek solver.
- Two forms per Skill: as-is and "I5 + text as General" (6 arms), plus N, I5, I5b and placebo.
- Item-blocked in one round, on OfficeQA, LiveMath and SpreadsheetBench test + train, without the SearchQA diagonal.
- About 95M deepseek tokens at r = 2, or about 48M at r = 1. Breakdown at r = 2: Skills alone 22M, I5 + Skill 38M, references 35M. Same token model as `power_cost_e2.py`, including +1k prompt tokens per 4 KB of extra text. It reuses the 2.8 pilot script, generalised to several targets.
- Caveat: these Skills were learned with the GLM solver in v1. A deepseek re-evaluation measures how those texts transfer to the deepseek solver, which is a model transfer as well as a task transfer.

## 6. What the paper claim becomes [claim]

- **Current v1/v3 framing:** sequential five-stage learning with forgetting and "ahead" readouts. The claim was continual learning across benches.
- **E2 framing:** "A Skill evolved on one benchmark, without any access to the others, changes performance on unseen benchmarks by G (CI) beyond the hand-written seed, and does not harm dissimilar ones by more than 3 points."
  - The table is a k x k matrix with per-cell CIs.
  - The baselines (GEPA, SkillOpt-prior) are evaluated under identical, same-session conditions.
  - The comparison is with the seed, not only with no Skill.
- **What we can honestly claim today**, from the v1 row:
  - single-source learned texts (ours and both baselines) carry an answer-format effect that the hand-written cards also carry;
  - versus the cards they are -3.2 to -4.4 points on average over the other four benches, driven by -13 to -17 on SpreadsheetBench.
  - That is a negative result for learned transfer. The E2 protocol would make it a properly measured negative or, after D1, possibly a positive one.
- **If E2 comes out positive** (matrix-mean G > 0 with MDE about 1.5-2), the claim is a forward-transfer result in the sense of GEM's FWT. It is comparable to the cross-task transfer claims of ExpeL, AWM and CLIN, but with stronger controls: same-session interleaving, a duplicate canary and a placebo.
- **If it comes out null**, the paper has a well-powered negative: what single-source evolution transfers is format, not knowledge. The literature supports this as a contribution (MetaSPO and Sclar et al. on prompt overfitting and formatting sensitivity).

## 7. Literature (verified this session unless marked)

**Prompt transfer within a family of tasks**
- OPRO (Yang et al., ICLR 2024, §5.2.4 Table 6): an instruction optimized on GSM8K transfers to MultiArith (95.3 vs 85.7 for "Let's think step by step") and AQuA (54.3 vs 44.9), PaLM 2-L scorer. Positive transfer, but among closely related math tasks.
- SPoT (Vu et al., ACL 2022): soft-prompt transfer over 26 tasks and 160 source-target combinations. Task embeddings derived from the learned prompts predict which source helps a target.
- Vu et al. (EMNLP 2020): 33 tasks. Transfer is often positive even from small or dissimilar sources; its size depends on task similarity, data size and complexity.
- Pruksachatkun et al. (ACL 2020): 110 intermediate-target pairs with RoBERTa. Which intermediate task helps varies widely; tasks requiring high-level inference and reasoning tend to work best (abstract).
- Taskonomy (Zamir et al., CVPR 2018; not re-checked this session): the canonical full transfer matrix among 26 vision tasks.

**Generalisation of learned or optimized prompts**
- MetaSPO (Choi, Baek, Hwang, arXiv 2505.09666): system prompts meta-learned across tasks, evaluated on 14 unseen datasets in 5 domains.
  - Averages: Default 32.2, SPRIG about 35-37, MetaSPO Domain 44.5 / Global 41.4.
  - Its Table 1 (re-checked this session) shows per-dataset negative transfer. The globally meta-learned prompt is **below the default system prompt** on Natural Questions (9.5 vs 15.1) and WebQuestions (7.7 vs 11.6). The domain-matched variant is above it (19.1, 13.7). The text does not discuss this. It is a published case of an averaged gain hiding harm on open-domain QA targets, the same pattern our SpreadsheetBench cells show.
- SPRIG (Zhang et al., arXiv 2410.14826): a single optimized system prompt over 47 task types is on par with task-specific prompts, and combining the two helps.
- Sclar et al. (ICLR 2024): formatting alone spreads accuracy by up to 76 points. This matches our "any text moves OfficeQA by 20" finding.
- Kojima et al. (NeurIPS 2022): a generic instruction ("Let's think step by step") moves MultiArith from 17.7 to 78.7. This is the canonical "generic instruction" baseline effect.
- Instruction Induction (Honovich et al., ACL 2023): 24 tasks; induced instructions reach 65.7% of human performance (InstructGPT).

**Cross-task skill and experience libraries**
- ExpeL (Zhao et al., AAAI 2024): insights from HotpotQA transferred to FEVER, 70 ± 0.7 vs ReAct 63 ± 0.4 vs Act 58.
- AWM (Wang et al., ICML 2025): induced workflows give +8.9 to +14.0 absolute points across tasks, websites and domains.
- CLIN (Majumder et al., COLM 2024): about +4 on new environments and +13 on new tasks, zero-shot.
- Voyager (TMLR 2024): its skill library is reused in a new world.
- GEPA (Agrawal et al., ICLR 2026): +6 points over GRPO and more than +10 over MIPROv2. Its reported gains are within-benchmark (train/validation/test of the same benchmark); cross-benchmark transfer of its prompts is not what it optimizes, which is why the v1 GEPA row in 2.1 (strong on SearchQA and OfficeQA, -16.7 vs cards on SpreadsheetBench) is informative.

**Matrix and metrics**
- GEM (Lopez-Paz & Ranzato, NeurIPS 2017): R_{i,j}; ACC = mean_i R_{T,i}; BWT = (1/(T-1)) Σ_{i<T} (R_{T,i} - R_{i,i}); FWT = (1/(T-1)) Σ_{i≥2} (R_{i-1,i} - b̄_i).
- Our G_all(I5) is FWT with b̄ replaced by the seed on the same items in the same session.

**Not verified in full text; not relied upon:** Gong & Wen (arXiv 2605.26655), TextReg (arXiv 2605.21318), PE2 "Prompt Engineering a Prompt Engineer" (arXiv 2311.05661), on overfitting and model-specificity of optimized prompts.

## 8. Code changes (current repository, `skillopt/coevo5/`) [measured counts, estimated size]

- `ORDER` is referenced about 120 times across 17 modules: readout 24, report 23, prelaunch 13, step 10, chain 9, data 7, skill 6, protocol 6, baseline 4, and others.
- There are about 48 more similar, regression or stage-index references (step.py 20).
- The stage index **is** the bench index today: `bench = ORDER[stage - 1]` in step.py (train, prepare, selftest, _round, composite, merge, learn) and baseline.py:93, 268.

| module | change | size |
|---|---|---|
| protocol.py | new VERSION (e.g. `fivebench-transfer-v1`), SOURCES, STEPS, matrix panels, MATRIX_RUNS, reference arms; v3 constants untouched | S |
| units.py | CHAINS keyed by (method, start, source, replicate); Setting gains `source`, `steps` | S |
| chain.py | `run()` loops over steps of one source, not over ORDER; per-step five-panel `evaluate()` removed or made source-only; caps per step | M |
| step.py | `bench = setting.source` (10 sites); `regression_keys` source-only; `similar_targets`/`also` disabled; per-step fresh batch (with data.py) | M |
| skill.py | General section (render, `Rule.home == "general"`), optional rule predicates | S |
| baseline.py | GEPA/SkillOpt with a source parameter; embed outputs as-is and as I5 + General | S |
| evaluation.py | **new matrix unit**: arms x targets, item-blocked interleaved dispatch, r runs, request hashing, no cross-round reuse, duplicate canary, regime logging | L |
| readout.py / report.py | new matrix readouts (cells, G_all/G_sim/D_dis, stratified bootstrap, replicate pooling, placebo correction); old A[s][b]/forgetting/ahead readouts do not apply | L |
| data.py / prelaunch.py | per-step batch seeds; leakage guard that the chain touches only its source; budgets | M |
| tests | single-source chain, matrix unit, readouts, leakage guard | M |

Total: **about 800-1,300 lines**, medium-large. The new matrix-evaluation unit is useful on its own: same-session interleaving is needed for every comparison in the project, not only for E2. The prototype is `/data/feasibility/E2/scripts/pilot_row_officeqa.py`, about 170 lines.

## 9. Risks

1. **Null learning, so an empty matrix.** v3 accepted 0 rules in both chains. E2 depends on D1 (or another acceptance change), or it can only measure the baselines.
2. **Serving drift:** -24 points for I5 on OfficeQA between windows; text-dependent on SearchQA (D5); a -7.0 same-bytes canary on LiveMath. Interleaving cancels the common-mode part only, so regime stratification is needed.
3. **The reference choice flips the sign** (v1: +2.0 to +3.2 versus no Skill, -3.2 to -4.4 versus the cards). The primary must be fixed in advance.
4. **Format effects masquerade as transfer** (OfficeQA +19-20 for any Skill). The placebo and seed references are mandatory.
5. **Negative transfer to dissimilar benches** (SpreadsheetBench -13 to -17 versus the cards).
6. **Placement sensitivity** (±15 points). It must be measured, not assumed.
7. **Multiplicity:** 20 cells x many arms. Use a single primary and Holm for the rest.
8. **Using target training pools as panels:** valid for row s (unseen by that chain), but they are the training data of the t-source chain, and reviewers expect canonical test splits. Report both; owner decision.
9. **Low power** for single rows and for the OfficeQA row (non-inferiority power 0.22-0.41). The OfficeQA pool (74 items) also limits learning.
10. **Cost and rate limits:** 264M-1.57B deepseek tokens. The shared route returned HTTP 429 for 300 consecutive seconds during this session's pilot.
11. **Model transfer confound** in D0: GLM-learned texts evaluated with deepseek.
12. **Code risk:** about 1,000 changed lines. A new VERSION and output directory are needed, and the frozen v3 protocol and artifacts must not be touched.

## 10. Recommendation

1. **Adopt E2's evaluation layer now, independent of E2's learning.**
   - Build the interleaved, item-blocked matrix unit with duplicate canary and placebo, and stop comparing arms across sessions.
   - This also repairs every other comparison in the project.
2. **Run D0 first** (about 48-95M deepseek, no learning; section 5.3).
   - It gives the first properly controlled single-source row (SearchQA → OfficeQA, LiveMath, SpreadsheetBench) for our method and both baselines, versus the seed, no Skill and placebo, in one session.
   - Expected outcome: v1 (GLM) predicts about +20 versus no Skill on OfficeQA, about 0 versus the cards, and negative on SpreadsheetBench. The deepseek pilot (2.8, inconclusive) did not show the +20 versus no Skill, so the deepseek row may differ.
   - Either way it is a properly controlled baseline row for the paper.
3. **Only after D1 makes learning accept rules:** run design D (264M) or A (381M) with the registered primary "matrix-mean G_all versus the seed". Use R ≥ 2 chains per source, K = 3 fresh-batch steps, a General section, source-only regression panels, and r = 2 on test + train panels.
4. **Owner decisions needed:**
   - (a) whether target training pools may serve as off-diagonal evaluation panels (power) or only the test splits (purity);
   - (b) which sources (QA core first);
   - (c) whether a null matrix is acceptable as a paper result.

## 11. Artifacts

Mac scratchpad: `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E2/`
- `report.md` (this report).
- `v2/pilot_row_officeqa.py`: row pilot, item-blocked, resumable, first-cell guard, token cap.
- `v2/analyse_row_officeqa.py`: paired analysis on complete item blocks.
- `v2/power_cost_e2.py` and `v2/power_cost_e2.json`: power and cost arithmetic.
- `v2/cal1_components.py`, `v2/components_targets.py`: variance components.
- Earlier-pass scripts: `analyse_placement.py`, `analyse_seeded.py`, `serving_drift.py`, `regime_paired.py`, `request_identity.py`, `power_cost.py`, and others.

New machine (`<datatools-login>`):
- `/data/feasibility/E2/pilot-row-officeqa/`: records/<arm>/<item>.<run>.json, config.json, arms.json, resume*.json, and infra-failures/0507/ (the archived HTTP-429 cell and the aborted summary).
- `/data/feasibility/E2/pilot-row-officeqa.log`.
- `/data/feasibility/E2/verify2/`: verify_e2.json, components_targets.json, row_officeqa.json.
- `/data/feasibility/E2/pilot-placement/`, `/data/feasibility/E2/pilot-seeded-leakage/`, `/data/feasibility/E2/analysis/`: the earlier pilots.
- `/data/feasibility/E2/scripts/`: all scripts.

Old machine: `/data/feasibility-scratch/E2/cal1_components.{py,json}`.
