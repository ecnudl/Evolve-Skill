# E6 - Graded / partial-credit scoring as a way to cut gate variance: feasibility report

Direction E6 (second batch). Serves purpose 2 (the measurement behind "evolve on one benchmark, evaluate on the
others"); section 9 adds the by-product for purpose 1 (the verification-side rubric).
Written 2026-10-21 by the E6 explorer. All numbers below were measured on stored training-side solver outputs unless
marked "estimate" or "claim". No test, holdout, evaluation or calibration-reserve file was opened.

## 0. Bottom line

**Feasibility as a variance-reduction lever: LOW (measured; the main result is negative).** The scores are cheap to
build and to compute, but none of them reaches the target: none lowers the number of items needed to detect a real
effect. On top of that, the scores that forgive answer form reward the wrong thing.

1. **(a) Pass/fail boundary.** No graded score ever fails an official pass (0 of 6,008 EM passes). They only add credit
   to official failures. Format-robust EM passes 327 of 2,777 EM failures (Cohen kappa 0.911). "Gold + <= 3 words"
   passes 1,083 (kappa 0.681), token-F1 >= 0.5 passes 1,585 (0.507), and the GLM-5.3 judge rates 2,076 of 2,767 EM
   failures (75.0%) as semantically CORRECT (kappa 0.313). In a single-auditor check those CORRECT labels were right
   about 87-93% of the time.
2. **(b) Noise floor between parent:A and parent:B (the same text).** Every graded score has a smaller same-text
   difference in raw units. Relative to the spread between items the reduction is modest: sd(B-A)/item spread is
   0.334 for EM, 0.320 for F1, 0.265 for EM+half-credit, 0.264 for the mechanical ladder and 0.209 for the binary judge
   (199 items, full data).
3. **(c) Separation of ids-full from the parent.** No score robustly needs fewer items than EM. Ratios are items needed
   for 80% power at a 5% same-text false-pass rate, relative to EM, with item-bootstrap 95% intervals:
   - EM + half credit for judge-correct but mis-formatted answers: 0.85 [0.52, 1.32].
   - Token F1: 0.88 [0.43, 1.42].
   - Lenient: 2.45x [1.13, 23.9].
   - Mechanical ladder: 1.69x [0.89, 7.65].
   - Binary judge: 1.83x [0.51, 18.2].
   - Rubric: 2.17x [0.68, 30.2].
   - Rubric ENTITY=2: 8.1x [1.4, inf].
4. **Why.** On SearchQA, answer FORM carries both the noise and the signal.
   - Noise: when the same text disagrees with itself, the failing side is judge-CORRECT in 83% of cell pairs (75 of
     90 run-paired A/B pairs) and 86.7% of within-arm flips (1,145 of 1,320).
   - Signal: 64% of the positive control's EM gain is answer form.
   - So a score that forgives form removes noise and signal together.
5. **Rewarding the wrong thing (measured twice).**
   - On cal-1, the format-forgiving scores turn the two format-breaking texts from EM losses into gains. For `cand`
     (the v3 E-ds s1-r1 rule) EM is -0.028; format-robust EM is +0.068 and the judge is +0.020.
   - **A replay of all 13 recorded v3 gate verdicts.** Under EM the replay reproduces every recorded C1 gain, C1
     margin and C2 delta exactly. Under EM+half-credit, format-robust EM or "lenient", s1-r1 would have passed confirm
     and entered the composite/merge step; v3 rejected it at confirm. Its fully powered 200-item effect in cal-1 is
     -0.026 [-0.072, +0.020] on the official score, and -0.004 on EM+half-credit itself.
   - No score revives any rule whose benefit is established.
6. **OfficeQA and LiveMath.**
   - OfficeQA (74 items): "within 1%" numeric credit looked better (SNR 0.330 vs 0.226; n80 76 vs 149). But the
     interval includes 0, the chain contrast is confounded with dispatch time, and 1% credit rewards wrong document
     values (501 for 498, 1302 for 1299).
   - OfficeQA, precision-respecting and year-safe credit: no gain (n80 186).
   - LiveMath: the stored data hold only the letter. There is no partial credit to give, and no format failure is
     recoverable.
7. **A bigger variance source that scoring does not fix.**
   - Byte-identical requests (the empty scaffold on the same 200 items) scored 6.1 EM points lower in cal-1
     (2026-10-20 16:07-19:52) than in the v3 train unit (00:07-00:18): 12 up / 38 down items, sign p = 0.0003. The
     graded versions of the gap are -3.4 (ladder) to -3.75 (lenient) points.
   - The seeded text did not move (-0.13 points, 12/12).
   - Within cal-1's four-hour window there is no trend (late - early -0.008 +- 0.012), and disagreement does not
     grow with the time between dispatches.
8. **Recommendation.**
   - Keep the official binary scores for C1, C2, C3 and C4' and for every test claim. Do not adopt a graded C1.
   - Add a frozen, cached "form vs substance" layer as a diagnostic: executable checks, gold-based lenient match,
     and a 3-vote GLM judge per distinct answer. It costs about 0.65M GLM tokens per 8,800-cell round, i.e. 2.4% of
     the ledger-charged solver tokens.
   - Feed it to the examiner and analyst (purpose 1).
   - Report it next to every cross-benchmark delta, so that answer-form transfer is not read as knowledge transfer
     (purpose 2).
   - Variance reduction should come from the D1/D5/D8 levers instead: more items and runs, interleaved same-window
     arms, and fresh batches.

## 1. The question and how it serves the owner's purposes

The v3 gate decides on official pass/fail scores. A text re-run at temperature 0 moves 16% of items (30 of 194, from
context). Discordant items per trigger panel are 0-5. A graded score (partial credit for nearly right answers) might
reduce this noise. It would do so by giving the 25 "dead" items (0 in every arm) some variance, and by turning
discrete flips into small steps.

The assignment asked for three measurements on the cal-1 predictions:
- (a) agreement with exact match at the pass/fail boundary;
- (b) the same-text noise floor (parent:A vs parent:B);
- (c) the number of items needed to separate ids-full from the parent.

It also asked for a survey and a statement of how the gate criteria would change and the risk of rewarding the
wrong thing.

- Purpose 2 (generalization metric): the gate statistic and the cross-benchmark evaluation are the same
  measurement. A score that is less noisy at equal validity would let a single-benchmark evolution show its effect
  on the other benchmarks with fewer items.
- Purpose 1 (co-evolution, verification-side "coding rubric"): the same machinery is a form/substance classifier
  for failures. Section 9 measures how much of it can be executable code.

## 2. Data and provenance

- **cal-1 SearchQA unit (complete).** 11 arms x 200 training items x 4 runs = 8,800 cells, read from
  `/data/coevo5-20261020-cal1/cal1/searchqa/attempt-{1,2}/cells` (read-only; a later attempt overrides an earlier
  one).
  - attempt-1: 7,189 cells with a verdict (4,901 pass / 2,273 fail / 15 unknown; 16 files had no verdict and were
    re-run).
  - attempt-2: 1,611 cells (1,107 / 504 / 0).
  - Total: 6,008 pass / 2,777 fail / 15 unknown (HTTP 503). 8 failures are non-completions with no prediction;
    they score 0 everywhere.
  - Note: context.md gives 2,268 failures for attempt-1, but 4,901 + 2,268 + 15 = 7,184, not 7,189. The files hold
    2,273.
- **Checks.**
  - My re-implementation of the official SearchQA scorer reproduces the stored em/f1/sub_em and the verdict for all
    8,777 scored cells.
  - The registered C1 arithmetic on pool (i) at n = 11 gives 0.756. The registered `analysis.json` gives 0.7575
    (2,000 draws, Monte Carlo se 0.009). On the pre-round pool I get 0.944 vs 0.941.
- **Items.** All 200 cal-1 items appear in the pinned training files (train panel 127 + val items 73), with identical
  questions and golds in my v3 item file. 198 items have one gold alias, 1 has two, 1 has three.
- **Analysis sets.**
  - "Full" = all 8,800 cells. "attempt-1" = the 7,189 cells the assignment named.
  - Judged analyses use the 199 items where every score exists in every arm (attempt-1: 193). One item lost judge
    labels to persistent HTTP 400 replies.
  - Both versions are reported: [attempt-1 | full], or "full" when only one is given.
- **v3 training-side cells.** Read from `/data/coevo5-20261019-v3-run/{E-ds,I-ds}/{s1,s2,s3}/{train,screen,confirm}`;
  an assertion stops the run if a path contains a forbidden word.
  - SearchQA s1 train: 200 items x 2 runs x 2 chains.
  - OfficeQA s2 train: 74 x 2 x 2.
  - LiveMath s3 train: 100 x 2 x 2.
  - All screen/confirm cells of s1-s3: 10,178 rows in total.
  - The gate replay uses the recorded `unit.json` verdicts and the prepared rules' evidence lists, which C2 holds
    out.
- **Dispatch times.** Taken from the send receipts.
  - cal-1: attempt-1 16:07-18:05, attempt-2 19:06-19:52, both on 2026-10-20.
  - v3 SearchQA train: E-ds 00:07-00:18 on 2026-10-20; I-ds 23:26-23:37 on 2026-10-19.

## 3. The scores that were built

### 3.1 SearchQA (per cell, in [0, 1])

| name | definition | model call? |
|---|---|---|
| EM (official) | SQuAD-normalised exact match of the last `<answer>` tag, or the last non-empty line, against any gold alias | no |
| em_rob | EM after format-robust extraction: tag > JSON inside tag > JSON `"answer"` field > `answer:` prefix > last line without markdown | no |
| lenient | normalised gold contained in the normalised answer with <= 3 extra words; official extraction (as coevo5 scoring §5.9, descriptive) | no |
| F1 | SQuAD token F1, max over golds, official extraction | no |
| sub_em | normalised gold is a substring of the answer | no |
| ladder | 1 EM; 0.9 em_rob; 0.7 lenient (robust); 0.4 substring or F1 >= 0.5; 0.2 any token overlap; 0 otherwise | no |
| jC | GLM-5.3 3-vote majority label CORRECT (1) vs PARTIAL/WRONG (0); no majority -> PARTIAL; non-completion -> WRONG | yes |
| j3 | the same labels as 1 / 0.5 / 0 | yes |
| em_half | 1 if EM, else 0.5 x jC (a semantically right but mis-formatted answer gets half credit; keeps a format penalty) | yes |
| rub | GLM rubric (TYPE 0/1 + ENTITY 0/1/2 + SPECIFIC 0/1) / 4, mean of 2 votes | yes |
| rubE2 | rubric ENTITY = 2 (same entity), mean of 2 votes | yes |
| format flags | tag present, number of tags, JSON wrapper, words in answer, hedge marks | no |

Judge prompts:
- v1: Jeopardy-trivia answer equivalence. Aliases, abbreviations, spelling variants, articles, titles and short
  non-changing qualifiers count as CORRECT. Lists, hedges, extra facts, and broader or narrower answers count as
  PARTIAL. The prompt is in `/data/feasibility/E6/judge.py`, md5 cc0f5e015bd01c11b65eeb60cf2dcb61, identical on both
  copies.
- rubric: three independent criteria (`judge_v2.py`).
- Both prompts see the clue, the gold aliases and the robust-extracted candidate, not the snippets.
- Settings: thinking on, reasoning low, temperature 0. Labels are cached per distinct (item, normalised answer)
  pair. The 8,785 known cal-1 cells contain only 542 distinct pairs (6.2%). So each answer string gets one fixed
  label, the same in every arm and run.

### 3.2 OfficeQA

- Official EM: normalised exact match of the last tag, with no numeric tolerance; a missing tag fails.
- Numeric checks on the LAST number in the answer (the delivered value, so a list earns nothing):
  - relative error;
  - scale error (x10^+-3/6/9 within 0.5%);
  - num_equal (numerically equal, different string);
  - within_1pct;
  - sigfig_yearsafe (rounded to the gold's decimals, with exact equality required for year-like or text-bearing
    golds).
- Ladder: 1 / 0.95 numerically equal / 0.8 within 0.5% / 0.5 within 5% / 0.4 scale error / 0.2 within 25% / 0.

### 3.3 LiveMath

Official letter EM, a valid-letter flag and a format-robust letter. The stored private fields are only `answer` and
`source_sha256`, so option-level partial credit is impossible.

## 4. SearchQA results (cal-1)

### 4.1 Per-arm levels, full data (known cells, about 800 per arm)

| arm | EM | em_rob | lenient | F1 | ladder | judge CORRECT | em_half | rubric | untagged / JSON-wrapped cells | mean answer words |
|---|---|---|---|---|---|---|---|---|---|---|
| parent:A | 0.680 | 0.697 | 0.789 | 0.791 | 0.808 | 0.909 | 0.794 | 0.930 | 81 / 16 | 3.18 |
| parent:B | 0.688 | 0.693 | 0.794 | 0.799 | 0.814 | 0.909 | 0.798 | 0.934 | 87 / 7 | 3.41 |
| ids-full | 0.773 | 0.773 | 0.841 | 0.866 | 0.856 | 0.943 | 0.858 | 0.958 | 1 / 0 | 1.80 |
| seed-only | 0.770 | 0.775 | 0.842 | 0.859 | 0.855 | 0.940 | 0.854 | 0.954 | 11 / 4 | 1.96 |
| seed-rule | 0.685 | 0.708 | 0.795 | 0.806 | 0.817 | 0.926 | 0.804 | 0.942 | 189 / 21 | 2.60 |
| seed-rule3 | 0.650 | 0.727 | 0.816 | 0.805 | 0.825 | 0.927 | 0.789 | 0.943 | 276 / 76 | 2.53 |
| cand (v3 E-ds s1-r1) | 0.655 | 0.765 | 0.822 | 0.815 | 0.836 | 0.929 | 0.791 | 0.948 | 311 / 118 | 2.20 |
| control:1 | 0.644 | 0.670 | 0.779 | 0.775 | 0.800 | 0.908 | 0.776 | 0.931 | 107 / 23 | 3.76 |
| control:2 | 0.715 | 0.733 | 0.826 | 0.826 | 0.832 | 0.923 | 0.819 | 0.941 | 61 / 16 | 2.20 |
| control:3 | 0.581 | 0.693 | 0.776 | 0.761 | 0.791 | 0.902 | 0.742 | 0.930 | 185 / 126 | 3.08 |
| control:4 | 0.681 | 0.699 | 0.797 | 0.797 | 0.811 | 0.913 | 0.797 | 0.935 | 83 / 17 | 3.00 |

The empty scaffold is semantically right on 90.9% of cells (judge) but formally right on only 68.0% (EM). The
headroom that any text can address is therefore mostly answer form.

### 4.2 (a) Agreement with official EM at the pass/fail boundary (pass = score >= 0.5; attempt-1 in brackets)

| score | agreement | Cohen kappa | EM failures passed | EM passes failed |
|---|---|---|---|---|
| EM, format-robust extraction | 0.963 [0.963] | 0.911 [0.910] | 327 of 2,777 [269 of 2,273] | 0 [0] |
| lenient (gold + <= 3 words) | 0.877 [0.876] | 0.681 [0.680] | 1,083 of 2,777 [889 of 2,273] | 0 [0] |
| token F1 | 0.820 [0.819] | 0.507 [0.505] | 1,585 of 2,777 [1,302 of 2,273] | 0 [0] |
| mechanical ladder (robust) | 0.876 [0.876] | 0.680 [0.680] | 1,086 of 2,777 [890 of 2,273] | 0 [0] |
| judge CORRECT (binary) = sem-or-EM | 0.762 [0.763] | 0.313 [0.316] | 2,076 of 2,767 [1,692 of 2,264] | 0 [0] |
| judge 3-level | 0.742 [0.743] | 0.236 [0.242] | 2,257 of 2,767 [1,835 of 2,264] | 0 [0] |
| GLM rubric /4 | 0.718 [0.719] | 0.144 [0.150] | 2,463 of 2,767 [2,005 of 2,264] | 0 [0] |
| rubric ENTITY = 2 | 0.773 [0.772] | 0.351 [0.348] | 1,983 of 2,767 [1,627 of 2,264] | 0 [0] |

em_half equals EM at the "== 1" threshold (kappa 1.000); at ">= 0.5" it behaves like jC.

**Where the judge disagrees with EM.** EM failures by mechanical category x judge label (cells):

| category | CORRECT | PARTIAL | WRONG | total |
|---|---|---|---|---|
| A wrapper (em_rob = 1, e.g. `{"answer": "U2"}`) | 324 | 0 | 0 | 324 |
| B lenient (gold + <= 3 words) | 711 | 48 | 0 | 759 |
| C token overlap (gold words inside a sentence, alias with shared words) | 883 | 47 | 65 | 995 |
| D no token overlap | 158 | 86 | 437 | 681 |
| non-completion | 0 | 0 | 8 | 8 |
| **all EM failures** | **2,076 (75.0%)** | 181 | 510 | 2,767 |

**Single-auditor precision check of "EM failure judged CORRECT".** I read 56 distinct (item, answer) pairs:
- category A: checked mechanically; the robust extraction equals a gold exactly, so 324/324.
- category B: 15 of 48 pairs; 14-15 of 15 defensible (Fragonard, M*A*S*H (1970), William Wordsworth, ice hockey ...;
  "hasty pudding" for "pudding" is borderline).
- category C: 25 of 178 pairs; 22-24 of 25 defensible (the right entity inside a sentence: "The answer is
  **Georgia** ...", "Patty Hearst" for "Patricia Hearst"). A paraphrase of "Better safe than sorry" was wrongly
  accepted.
- category D: all 16 pairs; only 4-5 of 16 defensible (Marie-Antoinette, fungus, Adirondack Mountains, bullet train).
  Over-lenient: "TGV" / "TGV and Shinkansen" for "trains", "giblet gravy" for "giblets", "double" for "a look-alike",
  and a sentence about Dijon for "French".

Weighting by cells gives a precision of roughly 87-93% (estimate; one auditor, pair samples). Lists were labelled
PARTIAL, as the prompt requires (e.g. "Minsk, Monrovia, Manama" for "Minsk").

### 4.3 (b) Same-text noise floor: parent:B - parent:A, per-item means over 4 runs [attempt-1 193 items | full 199]

| score | sd(B-A) | sd / item spread | test-retest r | run-paired cell flip rate | discordant items up/down |
|---|---|---|---|---|---|
| official EM | 0.1441 / 0.1397 | 0.340 / 0.334 | 0.942 / 0.945 | 0.116 / 0.114 | 19/15 / 20/16 |
| em_rob | 0.1432 / 0.1364 | 0.342 / 0.327 | 0.942 / 0.947 | 0.111 / 0.105 | 15/16 / 15/16 |
| lenient | 0.1390 / 0.1204 | 0.381 / 0.329 | 0.928 / 0.946 | 0.089 / 0.086 | 11/13 / 13/10 |
| token F1 | 0.1121 / 0.0995 | 0.360 / 0.320 | 0.935 / 0.949 | 0.155 / 0.164 | 24/23 / 27/26 |
| ladder | 0.0858 / 0.0772 | 0.297 / 0.264 | 0.957 / 0.966 | 0.132 / 0.138 | 22/21 / 25/22 |
| em_half | 0.0920 / 0.0794 | 0.308 / 0.265 | 0.953 / 0.965 | 0.120 / 0.120 | 19/18 / 20/19 |
| judge CORRECT | 0.0912 / 0.0562 | 0.344 / 0.209 | 0.941 / 0.978 | 0.019 / 0.025 | 3/3 / 4/3 |
| judge 3-level | 0.0707 / 0.0501 | 0.312 / 0.216 | 0.952 / 0.978 | 0.023 / 0.034 | 5/3 / 6/3 |
| rubric /4 | 0.0559 / 0.0434 | 0.320 / 0.240 | 0.953 / 0.974 | 0.074 / 0.080 | 13/11 / 13/13 |
| rubric ENTITY = 2 | 0.0597 / 0.0509 | 0.224 / 0.187 | 0.975 / 0.983 | 0.039 / 0.042 | 5/5 / 7/5 |

- The registered A2 (EM, L/H, 200 items) is sd 0.1438, 22 up / 18 down / 160 tie, 20% discordant items.
- The judge's same-text sd rests on 6-7 discordant items, so it is unstable between the attempt-1 and full data.
- Single-run reliability within (arm, item) over all arms is similar for every score: ICC(1) EM 0.767, em_rob 0.822,
  F1 0.806, ladder 0.836, judge 0.826, em_half 0.807; 4-run Spearman-Brown 0.93-0.95.
- Graded scores give the 25 EM-dead items a value: only 4-6 items stay at 0 in every arm and run under F1, ladder,
  judge and em_half. That variance did not turn into power (4.4).

### 4.4 (c) Separating ids-full (the five task-card seeds) from parent:A [attempt-1 | full]

n80 = items needed for 80% power, one-sided, at a false-pass rate set by the same-text null:
((1.645 sd_null + 0.842 sd_signal) / (mean_signal - mean_null))^2.

| score | mean diff | dz | SNR vs null sd | n80 analytic | n80 simulated (grid) | bootstrap n80 ratio to EM, full [95%] | P(SNR better than EM) |
|---|---|---|---|---|---|---|---|
| official EM | +0.0894 / +0.0930 | 0.278 / 0.298 | 0.575 / 0.612 | 37.5 / 33.2 | 40 / 40 | 1 | - |
| em_rob | +0.0717 / +0.0766 | 0.236 / 0.256 | 0.536 / 0.589 | 40.9 / 35.1 | 40 / 40 | 1.06 [0.86, 1.35] | 0.334 |
| lenient | +0.0371 / +0.0515 | 0.144 / 0.192 | 0.307 / 0.386 | 108.9 / 83.3 | 80 / 60 | 2.45 [1.13, 23.92] | 0.024 |
| token F1 | +0.0662 / +0.0743 | 0.279 / 0.317 | 0.568 / 0.673 | 36.4 / 29.1 | 30 / 30 | 0.88 [0.43, 1.42] | 0.756 |
| ladder | +0.0386 / +0.0479 | 0.178 / 0.219 | 0.426 / 0.542 | 78.1 / 55.3 | 60 / 50 | 1.69 [0.89, 7.65] | 0.245 |
| em_half | +0.0557 / +0.0634 | 0.247 / 0.287 | 0.580 / 0.752 | 40.9 / 28.1 | 40 / 30 | 0.85 [0.52, 1.32] | 0.967 |
| judge CORRECT | +0.0220 / +0.0339 | 0.112 / 0.165 | 0.261 / 0.604 | 175.8 / 61.1 | 100 / 50 | 1.83 [0.51, 18.18] | 0.482 |
| judge 3-level | +0.0143 / +0.0257 | 0.077 / 0.132 | 0.168 / 0.439 | 526.8 / 126.2 | 150 / 80 | 3.92 [0.83, inf] | 0.230 |
| rubric /4 | +0.0247 / +0.0275 | 0.162 / 0.182 | 0.345 / 0.543 | 130.4 / 71.0 | 100 / 60 | 2.17 [0.68, 30.17] | 0.366 |
| rubric ENTITY = 2 | +0.0186 / +0.0188 | 0.096 / 0.099 | 0.264 / 0.308 | 275.9 / 241.5 | 120 / 120 | 8.13 [1.42, inf] | 0.082 |

About the bootstrap (1,000 item resamples, 199 items):
- The first run had NaN-contaminated quantiles for the judge's SNR difference, because 2 resamples had a zero null
  sd. `bootstrap_sq_v2.py` drops those resamples; this changed no n80 ratio.
- Item-level sign tests for ids-full: EM 46/13 (p < 1e-4); judge 14/4 (p 0.031).

**C1-type passage on the registered pool (i)** (the archived v3 check-half failures: attempt-1 25 items, full 27;
n = 11; 2,000 draws). "Matched null" = the 95th percentile of the parent:B - parent:A sum.

| score | ids-full power at matched null (attempt-1 / full) | actual null pass rate at that threshold (full) | AUC ids-full vs null (full) | P(gain >= 1 item), full: ids-full / null / cand / seed-rule3 |
|---|---|---|---|---|
| official EM | 0.847 / 0.832 | 1.6% | 0.949 | 0.756 / 0.000 / 0.061 / 0.000 |
| token F1 | 0.890 / 0.881 | 5.0% | 0.968 | 0.787 / 0.004 / 0.140 / 0.000 |
| em_half | 0.857 / 0.894 | 3.5% | 0.971 | 0.770 / 0.000 / 0.101 / 0.000 |
| judge CORRECT | 0.788 / 0.857 | 4.6% | 0.945 | 0.773 / 0.000 / 0.451 / 0.165 |
| rubric /4 | 0.541 / 0.644 | 4.1% | 0.878 | 0.488 / 0.004 / 0.318 / 0.028 |
| ladder | 0.567 / 0.645 | 4.9% | 0.838 | 0.446 / 0.003 / 0.164 / 0.001 |
| lenient | 0.455 / 0.513 | 3.8% | 0.758 | 0.513 / 0.038 / 0.287 / 0.218 |

The "matched" thresholds are not exactly matched. EM is discrete: at pool (i), n = 11, its actual null pass rate is
1.6%, against 3.5-5.0% for the continuous scores. So the small power advantage of F1 and em_half at this pool is
partly a looser threshold. On the whole 199-item pool at n = 11, power is:
- EM 0.539 (null 4.6%), F1 0.566 (5.0%), em_half 0.543 (2.4%), judge 0.410, ladder 0.484, lenient 0.344.

At n = 20 it is:
- EM 0.644, F1 0.711, em_half 0.726, judge 0.597.

**Verdict on (c).** F1 and em_half are within noise of EM: a 10-15% item saving at best, with intervals that include
a loss. Every score that forgives form, and every judge-only score, needs more items. No graded score robustly
reduces the items needed.

### 4.5 Why: the noise and the signal are both answer form

Same-text noise, signal and failure rates, using the judge label to separate "form" (EM fails but judge CORRECT)
from "substance":

| quantity | value |
|---|---|
| run-paired parent:A vs parent:B cell pairs | 792 |
| EM-discordant A/B pairs | 90; failing side judged CORRECT in 75 (83%), WRONG in 14, PARTIAL in 1 |
| semantic-discordant A/B pairs | 20 |
| within-arm run pairs, all arms | 13,075 |
| within-arm EM flips | 1,320 (10.1%); failing side CORRECT in 1,145 (86.7%) |
| within-arm semantic flips | 332 (2.5%) |
| ids-full vs parent:A | EM +0.0930, semantic +0.0339: **semantic share 36%**; form-failure rate 23.0% -> 17.1%, semantic-failure rate 9.1% -> 5.7% |
| seed-only vs parent:A | EM +0.0888, semantic +0.0302 (34%) |
| cand vs parent:A | EM -0.0276 but semantic +0.0201 (11 up / 7 down items, n.s.); form-failure rate 23.0% -> 27.6% |
| seed-rule3 vs parent:A | EM -0.0276, semantic +0.0176 (10/4, n.s.) |
| control:3 (recipe placebo) vs parent:A | EM -0.1005, semantic -0.0075: almost pure format damage (126 JSON-wrapped, 185 untagged of 800) |

Per-arm EM and semantic flip rates between runs of the same (arm, item):

| arm | EM flips | semantic flips |
|---|---|---|
| parent:A | 0.119 | 0.029 |
| parent:B | 0.104 | 0.027 |
| ids-full | 0.050 | 0.008 |
| seed-only | 0.053 | 0.030 |
| cand | 0.159 | 0.035 |
| control:3 | 0.162 | 0.024 |

The other arms fall between 0.075 and 0.122 (EM) and between 0.017 and 0.031 (semantic). Semantic flips are 1.8-6.8x
rarer than EM flips in every arm.

So the gate's unit of measurement, an exact-form answer, flips between runs mostly through form. The positive
control's gain is also mostly form. A score that forgives form shrinks the noise and the effect together. That is
why em_half, which keeps half of the form penalty, is the only judge-based score that does not lose power.

### 4.6 Rewarding the wrong thing: measured

1. **Format-breaking texts look good.**
   - cand: EM -0.028 (35/44 items). Under em_rob it is +0.068 (42/17), lenient +0.032, judge +0.020, ladder +0.027,
     F1 +0.022. Only em_half (-0.004) keeps it near zero.
   - seed-rule3: EM -0.028 (24/36). Under em_rob +0.030, lenient +0.026, judge +0.018.
   - control:3: EM -0.101. Under em_rob -0.005, lenient -0.014, rubric +0.000; under the forgiving scores it becomes
     harmless.
   - In the pool (i) simulation at n = 11 the matched-null "pass" probability of cand is:
     - EM 0.107;
     - em_rob 0.431;
     - judge 0.621;
     - rubric 0.476;
     - lenient 0.314;
     - ladder 0.306;
     - em_half 0.274;
     - F1 0.242.

     For seed-rule3 it is 0.004 under EM and 0.372 under the judge.
2. **Replay of the actual v3 gate (all 13 recorded verdicts of stages s1-s3).** The replay uses protocol arithmetic:
   rule L (unknown = 0), parent and controls H (unknown = 1); C1 on the trigger items; C2 over the rest without the
   rule's evidence items, at the unchanged tolerances 7/6/9. Under EM it reproduces every recorded C1 gain, C1 margin
   and C2 delta exactly. Results under the other scores:

   | rule (unit) | EM (recorded) | em_rob | F1 | lenient | ladder | judge | em_half |
   |---|---|---|---|---|---|---|---|
   | E-ds s1-r1 screen | C1 pass (gain 1.75) | pass (2.25) | fail (0.60) | fail (0.75) | fail (0.93) | fail (0.50) | pass (1.12) |
   | E-ds s1-r1 confirm | C1 pass (2.00), **C2 fail (-7.5)** -> rejected | C1 2.25, C2 +6.0 -> **passes confirm** | C1 fail | C1 1.25, C2 +1.0 -> **passes confirm** | C1 fail | C1 fail (0.00) | C1 1.00, C2 -2.75 -> **passes confirm** |
   | E-ds s1-r3 screen | fail (0.75) | fail | fail | **pass (1.50)** | fail | fail (1.25, margin -1.25) | fail (1.00, margin -0.38) |
   | I-ds s1-r2 screen | fail (0.75) | fail | **pass (1.05)** | **pass (1.25)** | **pass (1.00)** | fail | fail (0.50) |
   | other 9 verdicts (E-ds s1-r2, s1-r4; I-ds s1-r1, s1-r4; OfficeQA s2-r2, s2-r3; LiveMath s3-r2, s3-r3, I-ds s3-r2) | fail | fail under every score | | | | | |

   - E-ds s1-r1 is the cal-1 arm `cand`. Its fully powered effect on all 200 items is official EM -0.026
     [-0.072, +0.020], em_half -0.004 (38/44), judge +0.020 (n.s.).
   - So EM+half-credit, format-robust EM and lenient would each have turned v3's zero confirmed rules into one
     confirmed rule. With no other passer it would have gone to composite/merge. That rule shows no gain even on the
     graded score that confirmed it. EM rejected it; that is the correct
     decision on present evidence.
   - E-ds s1-r3 and I-ds s1-r2 never reached confirm, and their full-panel effects are unknown.
   - No v3 OfficeQA rule passes under any OfficeQA score; LiveMath has only EM.
   - 41 of the 5,350 SearchQA stage-1 gate cells lack a judge label (persistent HTTP 400). The rule arm gets EM credit
     for them; parent and controls get judge-CORRECT credit.
3. **Lists and hedges.** sub_em, F1 and lenient credit "Minsk, Monrovia, Manama" for "Minsk". By SimpleQA's grading
   rule, multiple candidates count as incorrect, so a rule teaching "list a few candidates" would gain under those
   scores.
4. **Judge leniency toward related entities** (4.2, category D): "TGV" for "trains", "giblet gravy" for "giblets".
   A proposer that learns to name an associated entity would be rewarded about 3 times in 4 in that category.

### 4.7 Drift between sessions (a variance source that no score removes)

Byte-identical requests: all 200 request_sha256 values are equal, with the same model and max_tokens. The empty
scaffold on the same 200 items in the v3 E-ds s1 train unit (2026-10-20 00:07-00:18, 2 runs) vs cal-1 (16:07-19:52,
4 runs):

| comparison | EM | em_rob | lenient | F1 | ladder | sub_em |
|---|---|---|---|---|---|---|
| cal-1 parent:A - v3 | -0.0612 (se 0.0205), 12/38, sign p 0.0003 | -0.0475 | -0.0375 | -0.0491 | -0.0341 | -0.0175 (n.s.) |
| cal-1 parent:B - v3 | -0.0537, 14/34, p 0.0055 | -0.0512 | -0.0325 | -0.0418 | -0.0281 | -0.0138 (n.s.) |
| cal-1 ids-full - v3 I-ds train (seeded text) | -0.0013, 12/12, p 1.0 | -0.0013 | -0.0063 | +0.0010 | -0.0022 | +0.0013 |

- The shift hits the empty scaffold and mostly its answer form. The graded scores halve it, but they halve the signal
  too.
- Within cal-1 there is no trend: parents late (>= 17:30) minus early -0.0077 (se 0.012, 21/25).
- Disagreement between two dispatches of the same (arm, item) does not grow with the time between them: EM |diff|
  0.090-0.110 across gaps from < 10 min to > 2 h (13,155 run pairs).
- Per-arm flip rates are not stable either. In cal-1 the empty scaffold flips 11.9% and the seeds 5.0%. In the v3
  train units (each chain about 11 minutes, 2 runs) the empty scaffold flips 3.5% and the seeds 9.0%.
- The v3 I-ds vs E-ds train contrasts were dispatched 0.7-1.6 hours apart (s1 23:26 vs 00:07; s2 01:03 vs 02:17; s3
  01:16 vs 02:50), so they are confounded with session. Within cal-1 no session effect was visible over 4 hours, but
  the 16-hour shift above shows that one can exist. This matters for 5 below.
- Implication: compare arms only within one interleaved session (cal-1 does), and never across stored runs. This is
  D5/D8 territory and not a scoring question.

## 5. OfficeQA (v3 training units; 74 items x 2 runs x 2 chains = 296 cells)

| score | E-ds | I-ds | I - E [95% CI] | items up/down | run-to-run flip | SNR | n80 |
|---|---|---|---|---|---|---|---|
| official EM | 0.203 | 0.250 | +0.047 [-0.016, +0.110] | 9/5 | 0.088 | 0.226 | 149 |
| numerically equal (sigfig, year-safe) | 0.223 | 0.270 | +0.047 [-0.021, +0.116] | 11/7 | 0.115 | 0.199 | 186 |
| within 1% (year-safe = naive here) | 0.304 | 0.385 | +0.081 [-0.001, +0.163] | 15/7 | 0.122 | 0.330 | 76 |
| ladder | 0.364 | 0.396 | +0.032 [-0.038, +0.103] | 19/15 | 0.230 | 0.142 | 385 |

Cell census (296 cells):

| category | cells |
|---|---|
| pass | 67 |
| far wrong (> 25%) | 98 |
| 5-25% | 39 |
| 0.5-5% | 36 |
| gold not a single number | 27 |
| rounding <= 0.5% | 17 |
| numerically equal but string differs (e.g. "39.31%" vs 39.31) | 6 |
| non-completion (truncated) | 4 |
| x1000 scale error | 1 |
| tag without a number | 1 |

- Close-but-wrong examples: 1973 vs 1987, "August 1986" vs "June 1992", 501 vs 498, 1302 vs 1299, 0.976 vs 0.999.
  In a document-lookup benchmark a value within 1% is usually a different row or year, not a rounding of the right
  value.
- So "within 1%" raises the apparent SNR by about 1.5x (and halves n80) by rewarding near-misses. Its interval still
  includes 0, and the I-E contrast is confounded with session (4.7).
- The defensible graded credit (numerically equal or precision-rounded, year-safe) changes 6-17 cells and gives no
  SNR gain.
- Upstream: the OfficeQA reference scorer (databricks/officeqa `reward.py`) takes a relative tolerance argument whose
  default is exact, with 0.1% / 1% / 5% as options. The project's frozen scorer is exact normalised string match.
  Whether upstream would pass the 6 "numerically equal" cells is not verified here.

## 6. LiveMath (v3 training units; 100 items x 2 runs x 2 chains = 400 cells)

- Census: pass 141, wrong letter 251, no answer tag 7, truncated 1.
- Format-robust letter recovery changes no verdict, so em_rob = EM.
- E-ds 0.375, I-ds 0.330; I - E -0.045 [-0.101, +0.011] (9/15).
- Run-to-run flips: 0.130 (E-ds) and 0.160 (I-ds).
- The pinned private fields are only `answer` and `source_sha256`, so there is no option structure to give partial
  credit on.
- The one continuous score with a literature basis is the probability the model puts on the gold letter (Miller 2024,
  §3.2, for evals without chain of thought). It needs `logprobs` from the PJLAB deepseek route, which was not tested.

## 7. Judge reliability and cost

- **v1 label prompt, 3 votes.** Unanimous on 480 of 539 pairs (89.1%).
- **Rubric prompt, 2 votes.** All three criteria equal on 78.8% of 538 pairs; ENTITY 89.2%, TYPE 95.2%, SPECIFIC
  90.7%.
- **v1 label vs rubric ENTITY (538 pairs).**
  - CORRECT: ENTITY 2 386, 1 27, 0 3.
  - PARTIAL: 2 13, 1 32, 0 2.
  - WRONG: 2 1, 1 7, 0 67.
  - Exact agreement 0.901; binary 0.918.
- **The rubric's TYPE criterion carries little information.** TYPE = 1 on 100% of EM passes, 87.4% of EM failures and
  54.5% of judge-WRONG failures. Mechanical answer typing of the golds (123 capitalised names or titles, 76 lowercase
  phrases, 1 year) is too coarse to help.
- **Persistent HTTP 400 replies** (same inputs every time): 12 v1 votes on cal-1, 8 rubric votes, 9 votes on v3 gate
  pairs. They cost 1 cal-1 item and 41 v3 gate cells their labels.
- **Tokens (GLM-5.3, this direction in total): 1,324,475 tokens over 3,268 calls**, about 405 per call.
  - Earlier incarnation, v1 on cal-1 attempt-1: 1,545 calls, 614,905 tokens.
  - v1 fill for the attempt-2 pairs: 84 calls, 34,920.
  - Retries: 13 calls, 382.
  - Rubric, including smoke and retries: 1,107 calls, 462,651.
  - v1 on the 173 v3 gate pairs missing from the cache: 519 calls, 211,617.
  - No deepseek call was made.
- **Cost in a round.** 542 distinct pairs cover 8,785 cells, so 3 votes cost about 0.65M GLM tokens per 8,800-cell
  round, about 74 tokens per solver cell. That is 2.4% of the cal-1 ledger charge (27,481,897 tokens) or 4.6% of the
  receipt-reported prompt + completion tokens (14.0M). The cache grows across rounds and steps, so the marginal cost
  falls.

## 8. Literature (each item checked against its abstract or paper)

- **Kamalloo et al., ACL 2023, "Evaluating Open-Domain QA in the Era of LLMs"** (arXiv 2305.06984). Lexical matching
  substantially underestimates QA models; under human judgment InstructGPT zero-shot gains nearly +60%; more than half
  of lexical-matching failures are semantically equivalent answers. Our 75% semantically correct EM failures point the
  same way.
- **Bulian et al., EMNLP 2022, "Tomayto, Tomahto" (BEM)** (arXiv 2202.07654). Token F1 gives misleading partial credit
  and ignores the question; they propose a learned answer-equivalence model. Consistent with F1's 1,585 boundary
  crossings and its credit for lists.
- **Li et al. 2024, PEDANTS** (arXiv 2402.11161). Answer-equivalence rubrics derived from trivia-community rules
  (NAQT, Jeopardy!). This is the natural source for a frozen SearchQA judge prompt, since SearchQA clues are Jeopardy!
  clues.
- **Wei et al. 2024, SimpleQA** (arXiv 2411.04368). The grader allows hedging only if the gold is fully contained and
  nothing contradicts it; several candidate answers are graded incorrect; numbers must be correct to the gold's last
  significant figure. These are the rules our lenient/F1 violate and our sigfig credit follows.
- **Schaeffer et al., NeurIPS 2023** (arXiv 2304.15004). Discontinuous metrics such as exact match create apparent
  jumps that continuous metrics (token edit distance) smooth out. This is the theoretical case for graded scores; our
  data show the smoothing removes signal as well as noise when the signal is itself form.
- **Heineman et al. 2025, "Signal and Noise"** (arXiv 2508.13144). Decisions should be judged by the signal-to-noise
  ratio; switching to metrics with better SNR (e.g. bits-per-byte/perplexity) helps. We applied exactly this test;
  the candidate metrics did not improve SNR.
- **Madaan et al. 2024, "Quantifying Variance in Evaluation Benchmarks"** (arXiv 2406.10229). Continuous metrics can
  reduce seed variance compared with discrete ones; IRT-style item methods struggle to reduce variance.
- **Miller 2024, "Adding Error Bars to Evals"** (arXiv 2411.00640). §3.1 resampling (k answers per question),
  §3.2 next-token probabilities for non-CoT evals, §4.2 paired analysis. Resampling and pairing are what our gate
  already does; next-token probabilities are the untested LiveMath option.
- **Zheng et al. 2023, MT-Bench / Chatbot Arena** (arXiv 2306.05685). LLM judges show position, verbosity and
  self-enhancement biases.
- **"One Token to Fool LLM-as-a-Judge"** (arXiv 2507.08794). Generative reward models give false positives on
  "master key" replies such as bare punctuation or reasoning openers. A judge used as a gate is an optimisation target.
- **Arora et al. 2025, HealthBench** (arXiv 2505.08775; 48,562 physician-written rubric criteria, weighted -10..10,
  graded by GPT-4.1) and **Gunjal et al. 2025, "Rubrics as Rewards"** (arXiv 2507.17746; rubric rewards beat
  Likert-judge rewards, up to 31% relative on HealthBench). Rubric scoring pays off where outputs are long and
  multi-faceted. Our outputs are single short answers, where rubric criteria are redundant (TYPE) or noisy (79%
  all-criteria repeatability).
- **OfficeQA** (Databricks, arXiv 2603.08655; github.com/databricks/officeqa `reward.py`). Relative-tolerance numeric
  scoring as an option, exact by default.

## 9. By-product for purpose 1: how much of a "coding rubric" can be executable code?

The v3 examiner already keeps an evolving SearchQA rubric. In E-ds s1 `prepare` it has 9 items:
- R1 `answer_tag_present`, R2 `answer_max_words(n=10)` and R3 `answer_no_percent` are executable checks.
- R4-R9 are text criteria judged by GLM.
- A revision is accepted on balanced accuracy (11/20 -> 13/20 in E-ds s1).

I measured on the 8,785 known cal-1 cells how well gold-free executable checks predict the official verdict:

| check | flags EM failures | flags EM passes | balanced accuracy | judge labels of the flagged failures |
|---|---|---|---|---|
| R1 no answer tag | 871 (31.4%) | 513 (8.5%) | 0.614 | CORRECT 766, PARTIAL 29, WRONG 67 |
| R2 > 10 words | 314 (11.3%) | 0 | 0.557 | CORRECT 233, PARTIAL 46, WRONG 29 |
| R3 percent sign | 1 | 0 | 0.500 | - |
| JSON wrapper | 424 (15.3%) | 0 | 0.576 | CORRECT 372 |
| R1 or R2 or R3 (the v3 executable items) | 963 (34.7%) | 513 (8.5%) | 0.631 | CORRECT 811, PARTIAL 60, WRONG 83 |
| any of six checks, including > 3 words | 1,253 (45.1%) | 785 (13.1%) | 0.660 | CORRECT 954, PARTIAL 139, WRONG 151 |

- R1 fires on 513 official passes because the official scorer falls back to the last line when the tag is missing.
  This is the "format check vs scorer fallback" inconsistency that v4 is fixing.
- Executable gold-free checks catch about one third of the failures. 84% of what they catch is form, i.e. the
  answer is semantically right.
- 1,524 failures carry no flag; 1,122 of them (74%) are still form failures (aliases, extra words).
- On training items the gold is available, so gold-based mechanical checks are legitimate for diagnosis. em_rob plus
  lenient flag 1,083 failures (39% of all failures) as form. The judge calls 1,035 of them CORRECT (95.6%), 48
  PARTIAL and none WRONG.
- Reading for the owner's "coding rubric":
  - The executable half is reproducible across versions and cheap. It can grow by adding checks: JSON wrapper,
    several tags, > k words, numeric equality and scale for OfficeQA, letter validity for LiveMath.
  - The LLM half (semantic equivalence) is noisier (89% vote unanimity; 79% rubric repeatability). It changes the
    measurement scale whenever it is revised, so it must be frozen per protocol version and archived cells re-scored.
  - For these short-answer benchmarks, the executable reading is the more promising verification-side artifact. The
    LLM judge is best used as a frozen classifier of the remainder, never as an evolving gate statistic.

## 10. How the gate criteria would change

| criterion | v3 now (protocol.py) | if a graded statistic were adopted (only em_half is defensible) | recommended for v5 |
|---|---|---|---|
| C1 benefit | sum over trigger items of (rule L - parent H) >= MIN_GAIN = 1 item, and rule L > every control H, on official pass/fail; TRIGGER_RUNS 4 | same arithmetic on em_half; a missing judge label counts as EM for L and as judge-CORRECT for H; MIN_GAIN re-set from a same-text null round per benchmark; with MIN_GAIN = 1 kept, the pool (i) null pass rate stays 0.000 | keep official EM |
| C2 no harm | sum over the rest (L - H) >= -TOLERANCE_FOCAL (searchqa 7, officeqa 6, livemath 9), at GATE_RUNS 2 | tolerance recomputed with the registered `calibrate` routine (EM's same-text sd scales by about 0.57x for em_half, 0.71x for F1, 0.40x for the judge); plus a focal format guard, because forgiving scores no longer see format harm | keep official EM |
| C3 regression | >= -TOLERANCE_REGRESSION and <= MAX_EXTRA_VIOLATIONS = 2 extra format violations (REQUIRED_FORMAT, regression panels only) | extend the violation count to trigger + rest panels | keep; also report focal format counts |
| C4' similar targets | delta >= MIN_SIMILAR_DELTA = 0 on official scores | unchanged | keep; add the form/substance split to every transfer number |
| new diagnostic (not a criterion) | - | - | per arm and round: EM, em_rob, form failures (EM fail & judge CORRECT), substance failures (judge WRONG), format flags; OfficeQA near-miss census; frozen judge prompt hash and cache |

What adopting em_half would buy and cost, measured on cal-1 and v3:
- On pool (i), n = 11: ids-full C1 passage 0.756 -> 0.770 (+1.4 points). cand 0.061 -> 0.101.
- At the matched null on the same pool: ids-full 0.832 -> 0.894. cand 0.107 -> 0.274.
- In the v3 replay: one rule passes confirm (s1-r1) whose 200-item effect is null or negative; no rule with an
  established benefit is gained.
- Net: not worth a protocol version.

F1 is excluded because it credits lists and wrappers. em_rob, lenient and the ladder are excluded because they erase
the format penalty that carries most of the true effect. Judge-only scores are excluded because their power is lower
and they reward related-entity answers.

## 11. Design that follows from the evidence (what I would build for v5)

1. **Scoring layer, per cell, stored next to the official verdict** (never replacing it):
   - SearchQA: EM, em_rob, lenient, F1, and format flags (tag, tags count, JSON wrapper, words, hedge).
   - OfficeQA: EM, last-number relative error, numerically equal, rounding <= 0.5%, scale error, year flag.
   - LiveMath: EM and valid letter.
   - All of it in `e6score.py` form: pure functions, version-stamped.
2. **Frozen semantic judge for SearchQA failures only.**
   - Use the v1 prompt, or a PEDANTS/SimpleQA-style version of it, frozen by hash.
   - 3 votes, majority, cached per (item, normalised answer). EM passes skip the judge: 0 of 6,008 were judged
     non-CORRECT.
   - Missing label: EM credit for a rule arm, judge credit for parent and controls.
   - Expected cost about 2-5% of solver tokens (section 7).
3. **Form/substance report per arm and round,** given to the examiner and analyst (purpose 1). Example: "this rule's
   EM change is -22 cells: +16 substance, -38 form; 118 JSON-wrapped answers". cal-1's cand is exactly this case.
   The analyst can then repair the form side, or drop a rule whose only effect is form.
4. **Transfer tables** (purpose 2). For a Skill evolved on bench X and evaluated on Y, report the official delta plus
   the form/substance split on Y, so that "transfer" through tag compliance is not mistaken for transferable
   knowledge.
5. **Variance reduction** comes from design, not scoring: interleaved same-session arms, more runs and items (D5/D8),
   fresh batches (D1). Calibrate MIN_GAIN and the tolerances with a same-session null pair (parent:A/parent:B) in
   every round, because the null moves between sessions (4.7).

## 12. Pilot actually run

- **Ran: yes.** GLM-5.3 judge calls on training items only; no solver calls.
  1. Earlier incarnation of this direction: the v1 label prompt on all distinct cal-1 attempt-1 pairs, 3 votes:
     `python judge.py --out /data/feasibility/E6/judge.jsonl --votes 3 --workers 6` (new machine, proxy on). 1,545
     calls, 614,905 tokens.
  2. This session, the v1 fill for attempt-2 pairs plus the rubric prompt, 2 votes:
     `nohup bash -ic 'proxy_on >/dev/null 2>&1; /data/feasibility/E6/v2/run_judges.sh' > /data/feasibility/E6/v2/out/judges.log 2>&1 &`.
     That is 1,191 calls and 497,571 tokens, plus 13 retry calls (382 tokens).
  3. The v1 prompt on the 173 v3 gate pairs missing from the cache:
     `cd /data/feasibility/E6/v2 && nohup bash -ic "proxy_on >/dev/null 2>&1; /root/continual-alf-prep-20260928/env/bin/python judge_v3cells.py --workers 6" > out/judge_v3cells.log 2>&1 &`.
     519 calls, 211,617 tokens.
- Total 1,324,475 GLM tokens (3,268 calls), concurrency 6, within the ~4M pilot budget. The first call was checked
  before release in each launch. Nothing was blocked by the permission system.
- Everything else (scoring, statistics, replay, drift, audit) is arithmetic on stored cells.

## 13. Risks

1. **Goodhart through format.** Forgiving scores make format-breaking rules look positive (cand, seed-rule3,
   control:3). Measured in 4.6, including one false confirmation in the v3 replay.
2. **Judge leniency on related entities.** About 3 in 4 "no-overlap CORRECT" pairs were wrong. Judge precision for
   EM failures overall is about 87-93% (single auditor).
3. **Judge nondeterminism and gaps.**
   - 10.9% of pairs are not unanimous over 3 votes at temperature 0.
   - Persistent HTTP 400 on some inputs (29 votes).
   - Caching makes labels deterministic per answer string, but a new judge version or provider change would change
     the scale.
4. **Judge exploitability.** Master-key attacks on LLM judges are documented. A gate statistic built on a judge is
   an optimisation target for the analyst.
5. **Wrong-value credit on OfficeQA.** Relative tolerance credits different document values.
6. **Lists and hedges credited** by substring/F1/lenient scores.
7. **Comparability.** All frozen baselines and v3 results are official EM. A graded protocol needs a new version and
   output directory (AGENTS.md), and cannot relabel old runs.
8. **Statistical caveats of this study.**
   - One benchmark (SearchQA) with a fully crossed design.
   - One strong positive control (ids-full; seed-only is nearly the same text).
   - Discrete-vs-continuous thresholds are only approximately matched.
   - Small OfficeQA and LiveMath samples (74/100 items) with session-confounded contrasts.

## 14. Cost estimate

- **Diagnostic layer** (recommended):
  - About 405 GLM tokens per vote, 3 votes per new distinct (item, answer) pair.
  - About 6% of cells are new pairs in a cal-1-sized round, so about 74 tokens per solver cell: 2.4% of
    ledger-charged or 4.6% of receipt-reported solver tokens.
  - At v3 scale (139M tokens), roughly 3-6M GLM tokens (estimate).
  - Mechanical checks are free.
- **If em_half were adopted anyway:**
  - the same judge cost;
  - one same-session null round per benchmark to recalibrate MIN_GAIN and the tolerances. A cal-1-like round
    restricted to parent:A/parent:B on 200 items x 4 runs is 1,600 cells, about 5.4M ledger tokens (estimate from
    3,400 per cell).
- **Optional LiveMath probability pilot:** about 400 cells x ~3,400 tokens = 1.4M tokens, if the PJLAB route returns
  `logprobs` (unverified).

## 15. Recommendation

1. Do not use graded or judge scores in C1/C2/C3/C4' or in any test claim. Keep the official binary scores (purpose 2
   validity).
2. Build the form/substance diagnostic layer (section 11). Use it to sharpen the examiner/analyst loop (purpose 1) and
   to decompose transfer gains (purpose 2).
3. Treat the executable part as the "coding rubric" that may evolve by adding checks. Freeze the LLM judge per
   protocol version.
4. Put variance-reduction effort into D5/D8/D1 designs. The same-text noise is 83-87% answer-form flips, which every
   EM-anchored score keeps, and the largest measured shift is between sessions (-6.1 points), which no score removes.
5. If the owner still wants a graded gate, pre-register em_half as a new protocol version, with a focal format guard,
   per-benchmark recalibration of MIN_GAIN and the tolerances from a same-session null round, and a replay of the v3
   verdicts as a negative control. The replay already shows one false confirmation.

## 16. Unknowns and limits

- Whether graded credit helps where answer form is not the dominant failure (OfficeQA numbers) under a same-session,
  interleaved design. The present OfficeQA contrast is confounded and underpowered.
- Whether a stricter judge prompt (SimpleQA/PEDANTS rules) would fix the related-entity leniency without losing
  alias recall. Not tested.
- Whether the PJLAB deepseek route returns token probabilities (LiveMath continuous score). Not tested.
- The judge-precision figure rests on one auditor reading 56 sampled pairs.
- E-ds s1-r3 and I-ds s1-r2 (which would pass screen under lenient/F1/ladder) have unknown full-panel effects.

## 17. Artifacts and how to reproduce

Local (Mac) scratchpad `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E6/`:
- `report.md` (this file).
- `judge.py` and `judge.jsonl`: earlier v1 judge and its votes.
- `v2/` scripts:
  - extraction: `extract_cal1.py`, `extract_v3.py`, `extract_times.py`;
  - scoring: `e6score.py`, `score_cells.py`;
  - judges: `judge_v2.py`, `make_v3_pairs.py`, `judge_v3cells.py`;
  - analysis: `analyze_sq.py`, `bootstrap_sq.py`, `bootstrap_sq_v2.py`, `analyze_v3.py`, `drift.py`, `decompose.py`,
    `judge_reliability.py`, `time_analysis.py`, `gate_replay.py`, `rubric_checks.py`, `officeqa_refined.py`,
    `per_arm_flips.py`, `v3_chain_flips.py`, `audit_sample.py`, `report_tables.py`.
  - The last five were recovered verbatim from inline commands, and each re-run reproduced its log byte for byte.
- `v2/data/`:
  - `cal1_cells.jsonl` (8,800 rows), `cal1_items.json`, `cal1_times.json`;
  - `v3_cells.jsonl` (10,178 rows), `v3_items.json`;
  - `v3_gate_units.json`, `v3_prepare_units.json`, `registered_pools.json`, `cal1_analysis_registered.json`.
- `v2/out/`:
  - `cal1_scored.jsonl`, `cal1_scored_judged.jsonl`, `v3_scored.jsonl`;
  - `sq_{attempt-1,all}[_judged].{json,log}`, `bootstrap_v2_all_judged.json`;
  - `gate_replay.{json,log}`, `drift.log`, `decompose.log`, `time_analysis.log`, `rubric_checks.log`;
  - `v3_graded.{json,log}`, `officeqa_refined.log`, `per_arm_flips.log`, `v3_chain_flips.log`,
    `judge_reliability.log`, `audit_sample.txt`, `report_tables.md`;
  - judge outputs `judge_v1_fill.jsonl`, `judge_v1_retry.jsonl`, `judge_rubric.jsonl`, `judge_v1_v3cells.jsonl`.

New machine: `/data/feasibility/E6/` (`report.md`, `judge.py`, `judge.jsonl`) and `/data/feasibility/E6/v2/` (the
same scripts, data and outputs; `run_judges.sh`). Old machine: `/data/feasibility-scratch/E6/v2/` (the cal-1
extraction and dispatch times).

To reproduce the analysis locally from `v2/`:

```
python3 score_cells.py
python3 analyze_sq.py --attempts all --judges
python3 bootstrap_sq_v2.py --judged --B 1000
python3 gate_replay.py
python3 -I rubric_checks.py
```
