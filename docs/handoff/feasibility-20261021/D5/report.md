# D5: Lowering the measurement noise floor. Feasibility report (2026-10-21)

Explorer: D5 (second, complete pass; it replaces the 2026-10-20 19:17 draft of this file, whose pilot section was never
filled). Scope:
- the per-item nondeterminism of the deepseek-v4-flash solver on the PJLAB token route, from the complete cal-1 cells;
- the parent:A − parent:B null distribution;
- the SD of a 200-item paired mean at 1, 2 and 4 runs;
- what k-vote majority does;
- whether client-side request options (`seed`, `top_p`/`top_k`, concurrency) change reproducibility;
- the Thinking Machines argument, and what a client can do about it;
- the item-count table.

Every statement is labelled:
- **measured**: computed from data or from calls made in this exploration, with denominators;
- **estimated**: a model fitted to measured numbers;
- **claim**: from a cited source, or an inference that was not directly tested.

What was not touched:
- No repository file (local or `/data/skillopt-work`) was modified.
- Nothing was written under `/data/coevo5-*`.
- No test or holdout pool was read, listed or copied. The v3 reads were restricted to the `train`, `screen` and `confirm`
  units, with an assertion against `evaluation/` and `shared/` paths.
- All pilot calls used cal-1 SearchQA **training** items.

## 0. Summary

| question | answer | status |
|---|---|---|
| Per-item flip rate within an arm (same text, same session) | P(two runs of the same item disagree): empty scaffold **0.117 / 0.102** (parent:A / parent:B; pooled 8 runs **0.105**), task-card arms **0.049 / 0.054** (ids-full / seed-only), learned candidate and control:3 **0.161**. Mixed items: 41/200 (parent:A), 18/200 (ids-full). The noise level is a property of the Skill text, not only of the model. | measured (cal-1 complete, 8,800 cells) |
| parent:A − parent:B per item (pure noise) | mean **−0.0075** (−1.5 items of 200), 95 % CI [−0.027, +0.012], 16 up / 20 down / 164 tie, sign p = 0.62. The four one-run "diagonal" realizations give **−12, +7, +2, −3** net items. | measured |
| SD of a 200-item paired mean (pure noise) | **4.6 / 3.3 / 2.3 items** at 1 / 2 / 4 runs per arm (analytic). Resampling the 8 pooled runs gives 4.7 / 3.3 / 2.3. | measured + estimated |
| What limits generalization claims | Item sampling, not run noise. The real arms carry item-heterogeneity variance σ²_het = 0.014–0.077, so the SE for new items is 1.2–2.2× the SE conditional on the panel. More runs cannot remove this; more items can. | estimated from measured |
| k-vote majority (k = 3 of 4 runs) | The exact unbiased variance ratio is **0.759**, against 0.333 for the mean of the same 3 runs. On real comparisons, \|t\| under majority-of-3 falls below mean-of-3 in every arm with a non-trivial effect (7 of 7) and is near the 1-run value. The two exceptions are null effects. **Negative: do not use.** This corrects the earlier draft's biased plug-in figure of 0.507. | measured + estimated |
| Session-to-session serving drift (new) | The **same request bytes** produce sessions in which **6 % to 93 %** of replies are bare answers. The switch happens synchronously for different texts. Effect on the empty scaffold, same 200 items: v3 E-ds s1 train (87 % bare) − cal-1 (13 % bare) = **+0.0575 [+0.019, +0.096]**, 44/15, p = 0.0002. Effect on the format-pinning task card: **+0.000** and **+0.001**, n.s. Inside one session there is no time structure. | measured (observational across sessions) |
| Does the route accept `seed`? | It accepts any value, even `"not-an-integer"`, and ignores it. At temperature 1, `seed=777` gives the same 2/48 identical pairs as no seed. | measured |
| Does `top_p` / `top_k` change reproducibility? | `top_k` is dropped (`top_k="abc"` returns 200; `top_k=1` at T1 gives 0/48 identical). `top_p` is honoured (`top_p=5` returns vLLM's 400 message; `top_p=1e-6` at T1 behaves like greedy, 12/48 vs T0 9/48). At temperature 0 neither can improve on greedy. | measured |
| Concurrency 1 vs 12 | No effect detected. Byte-identical pairs: 16/72 vs 19/72; verdict differs: 27/72 vs 23/72. Combined with the earlier pilot over 36 items: p = 0.20 (text), 0.52 (verdict). | measured (small) |
| Observable serving identity | None. There is no `system_fingerprint`; headers, id format, usage fields and top-level keys are identical for bare and verbose replies. The prefix cache works in 256-token blocks. Its hit/miss state is unrelated to style or reproducibility within items (p = 0.16–0.99). | measured |
| Thinking Machines argument | Nondeterminism comes from load-dependent batch composition (missing batch invariance). The fix is server-side (vLLM `VLLM_BATCH_INVARIANT=1`, SGLang `--enable-deterministic-inference`) at about 1.3–2× cost. No client-side remedy exists. DeepSeek-V4 is not on vLLM's validated list. | claim (cited, verified at source) |
| Cross-check with v3 | cal-1's noise predicts **28.9 ± 3.4** of 194 items to change between two 2-run measurements of the same text. v3 observed **30** (E-ds s1 screen → confirm). The v3 "noise floor" is fully explained by within-session noise. | estimated from measured |

**Feasibility verdict: medium.**
- No request parameter lowers the noise.
- The noise can be lowered at its source only by the route operator (claim; unverified for this route).
- Everything else is design, and it is now priced:
  - average runs, never vote;
  - pair and interleave every comparison in one session;
  - use a format-pinning parent text;
  - size panels from the item-count table, using items rather than runs when the claim is generalization.
- A new and cheap-to-fix bias source was found: serving-mode drift between sessions. It invalidates cross-session
  differences for texts that leave the answer format open.

## 1. Data, provenance, verification

**cal-1, now complete.**
- Location: old machine, `/data/coevo5-20261020-cal1/cal1/searchqa/`.
- attempt-1: 7,205 cell files, 16 without a verdict (interrupted), so 7,189 cells with verdicts.
- attempt-2: 1,611 cells, run 19:06–19:56 CST on 2026-10-20.
- Total 8,800 cells = 11 arms × 200 SearchQA training items × 4 runs. Outcomes: 6,008 pass, 2,777 fail, 15 unknown (all
  `http_503`).
- 8 truncations at 32,768 tokens, all scored fail: parent:A 1, parent:B 2, seed-only 2, cand 2, control:1 1.
- 1,050 cells needed HTTP retries.

**Identity checks (measured).**
- parent:A and parent:B are the same 593-byte text: SHA-256 `717618d4591180a5…` in `arms-cal1-searchqa.json`. In the
  cells both carry the same Skill hash, `cc516459…`.
- Ten distinct texts × 200 items give 2,000 request groups. Each group has exactly one request SHA-256.
- Dispatch was effectively shuffled:
  - the median start time is about 83 min for every run index;
  - attempt-2's share is 17.4–19.5 % of each run index;
  - every arm holds about 1/11 of each 30-minute window.

**Registered analysis, for reference.** This is `/data/coevo5-20261020-cal1/analysis.json` (23:43). I read it and did
not re-run it.
- A2: parent:B − parent:A = +0.0075 [−0.0125, +0.0275], 22/18/160, p = 0.636.
- A1: parent:B, treated as a pseudo-candidate, passes C1 in 0–1.3 % of draws.
- A3: ids-full +0.0938 [+0.0505, +0.137].

**v3, used for per-benchmark noise and for drift.**
- Old and new machine, `/data/coevo5-20261019-v3-run/{E-ds,I-ds}/s[1-5]/{train,screen,confirm}/attempt-*/cells/*.json`,
  parent and train arms only.
- In v3 no rule was ever accepted, so the parent of every stage is the step-0 Skill: the task-card seeds in I-ds, the
  empty scaffold in E-ds.
- For 20 items the request was verified byte-identical between cal-1 parent:A and v3 E-ds s1 train
  (`cal1_req20.json`).

**Pilot requests.** Before any call, each pilot request was rebuilt with the frozen v3 code
(`/data/coevo5-20261019-v3-source-f`). Its SHA-256 was checked against the cal-1 parent:A request of the same item. All
20 items matched.

**The earlier D5 draft** was written 2026-10-20 18:54–19:17 from attempt-1 data only. I re-derived its numbers.
- Its flip rates, its A−B summary and its analytic SDs agree with the complete data to within the extra 1,611 cells:
  ν 0.099 then, 0.105 now.
- Its majority-of-3 variance ratio of **0.507 was a plug-in estimate biased low**: m̂(1−m̂) underestimates m(1−m). The
  exact unbiased value is **0.759** (§5).
- Its single "+8 items" one-run realization (n = 136) is superseded by the complete four realizations: −12, +7, +2, −3
  items.
- Its pilot section was a placeholder. Its own 288-call pilot (2026-10-20 19:04–19:33) is analysed in §8, together with
  this pass's 266 calls.
- Its truncation-by-benchmark table and its adaptive-allocation result (no gain per call) were not re-verified. They are
  cited as from that draft where used.

## 2. Within-session noise per arm (measured)

Definitions:
- For an item with n known runs and p passes, the unbiased probability that two distinct runs disagree is
  2p(n−p)/(n(n−1)).
- ν is the average of this over items.
- An item is "mixed" when 0 < p < n.

| arm | pass rate | mixed / items | ν = P(two runs disagree) | items by passes of 4 (0/1/2/3/4) | reply pairs byte-identical | pairs with same extracted answer | P(verdict differs \| answer differs) |
|---|---:|---:|---:|---|---:|---:|---:|
| parent:A | 0.680 | 41 / 200 | 0.117 | 45/8/18/15/112 | 0.262 | 0.814 | 0.635 |
| parent:B | 0.688 | 37 / 200 | 0.102 | 45/10/12/15/116 | 0.291 | 0.830 | 0.606 |
| ids-full | 0.773 | 18 / 200 | 0.049 | 36/7/5/6/145 | 0.247 | 0.926 | 0.670 |
| seed-only | 0.770 | 19 / 200 | 0.054 | 38/1/7/10/141 | 0.399 | 0.928 | 0.733 |
| seed-rule | 0.685 | 36 / 200 | 0.097 | 47/8/7/20/115 | 0.345 | 0.854 | 0.655 |
| seed-rule3 | 0.650 | 45 / 200 | 0.123 | 50/11/13/21/104 | 0.404 | 0.801 | 0.622 |
| cand | 0.655 | 59 / 200 | 0.161 | 41/17/14/26/99 | 0.416 | 0.773 | 0.700 |
| control:1 | 0.644 | 36 / 200 | 0.096 | 55/11/7/18/109 | 0.314 | 0.811 | 0.507 |
| control:2 | 0.715 | 28 / 200 | 0.077 | 44/8/8/12/128 | 0.285 | 0.889 | 0.692 |
| control:3 | 0.581 | 60 / 200 | 0.161 | 57/17/13/30/83 | 0.336 | 0.748 | 0.637 |
| control:4 | 0.681 | 27 / 200 | 0.074 | 51/8/8/11/122 | 0.316 | 0.858 | 0.523 |

**The scorer is deterministic** (measured). Across all arms, 0 reply pairs had identical text and different verdicts.

**Text level** (measured).
- For parent:A, 73.8 % of same-request pairs differ in text, and only 7.5 % of items have all runs byte-identical.
- Of the differing parent:A pairs, 34.6 % differ from the very first character (a bare answer against a reasoning
  preamble).
- The extracted answer differs in 18.6 % of pairs. When it differs, the verdict differs 51–73 % of the time, depending on
  the arm.

**Per-token divergence** (measured). Pairs are bucketed by the longer reply. Implied hazard = 1 − P(identical)^(1/L).

| longer reply (tokens) | parent pairs | P(identical) | hazard per token |
|---|---:|---:|---:|
| 1–8 | 54 | 0.926 | 0.011 |
| 9–16 | 181 | 0.691 | 0.034 |
| 17–32 | 310 | 0.432 | 0.031 |
| 33–48 | 753 | 0.316 | 0.028 |
| 49–64 | 626 | 0.137 | 0.035 |
| 65–96 | 331 | 0.076 | 0.033 |
| 97–160 | 95 | 0.011 | 0.037 |

- The hazard for ids-full is 0.016–0.025 per token over 33–160 tokens; for cand it is 0.032–0.057.
- A roughly constant per-token hazard is what the batch-variance mechanism predicts (§9). A near-tie token flips under a
  slightly different numeric path, and the continuations then differ.
- A text change matters only when the divergence reaches the answer. This is why the text-level noise (74 % of pairs)
  is seven times the verdict-level noise (10 %).

**Reading** (claim, supported by the table).
- Texts that pin the answer format (ids-full, seed-only) leave half as many items on the model's decision boundary as
  the empty scaffold.
- Texts that add an instruction the item does not need (cand, control:3) push more items onto it.
- So the noise level must be measured per text. Using one ν for all arms understates the noise of candidates.

## 3. parent:A − parent:B: the null distribution (measured)

d_i = (mean pass under parent:A) − (mean pass under parent:B), using all known runs of each (4 + 4, or 3 when a cell is
unknown).

**Summary.**
- n = 200; mean −0.0075 (SE 0.0099); t-CI95 [−0.0268, +0.0118].
- Net −1.5 items; 16 up / 20 down / 164 tie; sign p = 0.62.
- With the registered lower-bound treatment of unknowns: [−0.0274, +0.0124], 18/22/160, p = 0.636. This is the same
  as the registered A2, with the sign flipped.

**Histogram of d_i.**

| d_i | −0.75 | −0.5 | −0.25 | 0 | +0.25 | +0.5 |
|---|---:|---:|---:|---:|---:|---:|
| items | 1 | 3 | 16 | 164 | 13 | 3 |

**Realizations of the same comparison at fewer runs.**
- One run against one run, the four "diagonal" pairings, n = 198–200: **−12.0, +7.0, +2.0, −3.0** net items. SD across
  them 0.041.
- All 16 one-run pairings: SD 0.030, about 6 items.
- All 36 two-run pairings: SD 0.017, about 3.4 items.
- Four runs against four: −0.0077.
- A single 1-run comparison of identical texts can therefore show "+7 items" or "−12 items".

**Dispersion test** (measured). Is there an A-vs-B component beyond run noise?
- Method: 20,000 random 4 + 4 re-splits of each item's 8 pooled runs.
- Observed Σd² = 3.875 against a null mean of 5.274; p_lower = 0.078.
- Items with d = 0: 160 against 157.0 (p = 0.134).
- A and B agree slightly *more* than random splits predict (n.s.). There is no evidence of an arm-level component, so
  the registered null is sound.

**Exchangeability of runs** (measured).
- Run-index pass rates per arm: χ² = 37.5 on 33 df, p = 0.27.
- Pairwise one-run split z-scores: Σz² = 32.5 on 22 df (p = 0.07). Two-run splits: 5.06 on 11 df (p = 0.93).
- Session effect (attempt-2 − attempt-1, within arm × item): +0.004 (1,099 passes against 1,087.7 expected over 1,587
  cells), permutation p = 0.61.
- First call of a request against later calls (text identity): 0.331 vs 0.311, p = 0.18.
- Minority-verdict rate: retried calls 28/137 = 0.204, single-send calls 262/1,023 = 0.256. By latency quartile: 0.231 /
  0.238 / 0.276 / 0.255. No load signature.
- A small run-level component cannot be excluded (p = 0.07), but nothing suggests one.

**Time gap inside cal-1** (measured).
- Byte-identical text is more frequent for pairs less than 10 min apart than for pairs more than 1 h apart: 877/2,412 =
  0.364 vs 2,674/8,770 = 0.305, permutation p < 0.002. Within attempt-1 alone: 0.366 vs 0.311, p < 0.002.
- Verdict disagreement shows **no** time trend: 233/2,412 = 0.097 vs 899/8,770 = 0.103, p = 0.26.
- The serving state drifts slowly within a session, but over these two hours the drift did not move verdicts. Across
  sessions it does (§6).

## 4. SD of the paired mean, variance split, item heterogeneity

### 4.1 SD of a 200-item paired mean under pure noise (same text, both arms r runs)

Analytic: SD = √(ν / (r · n)), with ν = 0.1054 from the 8 pooled parent runs and n = 200. The resampled column draws r
runs per arm without replacement from the 8 pooled runs of each of 196 items.

| estimator per item | analytic SD (items of 200) | resampled (items of 200) | points |
|---|---:|---:|---:|
| 1 run | 4.59 | 4.70 | 2.29 |
| mean of 2 | 3.25 | 3.31 | 1.62 |
| mean of 3 | 2.65 | 2.71 | 1.32 |
| mean of 4 | 2.29 | 2.34 | 1.15 |
| mean of 8 | 1.62 | – | 0.81 |
| mean of 16 | 1.15 | – | 0.57 |
| majority of 3 | 4.08 (exact unbiased) | 4.06 | 2.04 |

### 4.2 Variance split and item heterogeneity (each arm vs parent:A, 4 runs vs 4)

Observed Var(d_i) = run-noise part + σ²_het. The noise part uses each arm's own per-item noise. σ²_het is the variance
across items of the true per-item effect.

Two standard errors are given:
- the SE conditional on the panel, √(noise / n): did the score on *these* items move?
- the SE for new items, √(Var(d_i) / n): does the effect generalize to the item population?

| arm vs parent:A | items | mean effect | Var(d_i) | noise part | σ²_het | SE given these items | SE for new items |
|---|---:|---:|---:|---:|---:|---:|---:|
| ids-full | 197 | +0.0914 | 0.0975 | 0.0207 | 0.0767 | 0.0103 | 0.0222 |
| seed-only | 195 | +0.0897 | 0.0705 | 0.0209 | 0.0496 | 0.0104 | 0.0190 |
| seed-rule | 195 | +0.0064 | 0.0609 | 0.0270 | 0.0338 | 0.0118 | 0.0177 |
| seed-rule3 | 197 | −0.0317 | 0.0650 | 0.0306 | 0.0344 | 0.0125 | 0.0182 |
| cand | 195 | −0.0231 | 0.1071 | 0.0348 | 0.0722 | 0.0134 | 0.0234 |
| control:1 | 198 | −0.0379 | 0.0411 | 0.0269 | 0.0141 | 0.0117 | 0.0144 |
| control:2 | 198 | +0.0341 | 0.0461 | 0.0245 | 0.0216 | 0.0111 | 0.0153 |
| control:3 | 198 | −0.1010 | 0.0760 | 0.0351 | 0.0409 | 0.0133 | 0.0196 |
| control:4 | 198 | +0.0000 | 0.0482 | 0.0242 | 0.0240 | 0.0111 | 0.0156 |
| parent:B | 196 | +0.0077 | 0.0198 | 0.0281 | −0.0083 (≈ 0) | 0.0120 | 0.0101 |

Readings (estimated from measured):
- **ICC.** The share of cell variance that is between items is 0.728 for parent:A (run variance 0.059 of 0.218) and
  0.859 for ids-full. Items differ far more than runs do.
- **σ²_het is zero only for the identical text.** For every real text it is 0.014–0.077, and even the irrelevant-text
  controls carry 0.014–0.041.
- **Item sampling dominates.** For generalization claims, the item-sampling SE is 1.2–2.2× the conditional SE. Extra
  runs shrink only the conditional part, so beyond 2 runs per arm, items are the cheaper currency (§10).
- **Irrelevant texts are not null.** control:3 costs −10.1 points [−12.7, −7.5 conditional]. A different text changes
  the outputs on boundary items, which looks like noise but is reproducible per text. Deterministic serving would not
  remove this (§9).
- **The parent's noise history predicts an arm's noise only partly.** The Pearson r between per-item noise under the
  parent and under an arm is 0.10–0.49, and only 39–74 % of an arm's mixed items were mixed under the parent (ids-full
  7/18, control:4 20/27). This agrees with the earlier draft's negative result that adaptive allocation by the parent's
  history gains nothing per call (not re-run).

### 4.3 Failure-enriched trigger-style panels (measured + estimated)

The 74 items eligible after the cal-1 pre-round (`eligibility-pre.json`, parent failures) are noisier than average:
- ν = 0.175, against 0.1075 for the 196 items with all 8 runs;
- 39 % are mixed;
- 55 % pass 0 of 8.

Pure-noise SD of a "gain" in items:

| runs per arm | n = 6 | n = 11 | n = 20 | n = 50 |
|---|---:|---:|---:|---:|
| 4 runs | 0.51 | 0.69 | 0.94 | 1.48 |
| 2 runs | 0.73 | 0.98 | 1.32 | 2.09 |

So the v3 C1 threshold of "≥ 1 whole item" on an 11-item panel at 4 runs is 1.4 pure-noise SD. Before the control
margin, a null rule clears it about 7 % of the time (normal approximation). Meanwhile 55 % of such items cannot move at
all under any instruction-level change seen so far.

## 5. k-vote majority (negative result)

Method (estimated from measured):
- For each of the 196 items with all 8 pooled parent runs, the majority-of-3 pass probability m and its square were
  estimated **without bias** by U-statistics: all 3-run subsets for m, all pairs of disjoint triples for m².
- The single-run variance is p(n−p)/(n(n−1)).

| estimator | Σ variance over 196 items | ratio to 1 run | SD of 200-item paired mean (items) | calls per item |
|---|---:|---:|---:|---:|
| 1 run | 10.54 | 1.000 | 4.68 | 1 |
| mean of 3 | 3.51 | 0.333 | 2.70 | 3 |
| **majority of 3** | 7.99 | **0.759** | 4.08 | 3 |
| mean of 4 | 2.63 | 0.250 | 2.34 | 4 |

Why majority voting fails:
- Majority helps only on items far from π = 0.5, which carry little variance anyway.
- On the items that carry the noise it does nothing or harm. For π = 0.5 a majority of 3 is still a fair coin.
- Estimated variance contribution by observed pass count (the per-item unbiased estimator is not bounded):

  | passes of 8 | 1 run | majority of 3 |
  |---|---:|---:|
  | 4/8 | 0.286 | 0.371 |
  | 3/8 and 5/8 | 0.268 | 0.286 |
  | 2/8 and 6/8 | 0.214 | 0.107 |

- It also shifts the estimand: mean pass rate 0.685 against majority pass 0.6905.
- It shrinks effects that start from π near 0 (the slope dm/dπ = 6π(1−π) is 0 at π = 0), which is exactly where
  failure-triggered panels live.

**On real comparisons** (measured). Each arm vs parent:A, 3 of 4 runs per arm, averaged over the 16 triple choices.

| arm | effect (mean) | t, 1 run | t, mean of 3 | t, majority of 3 | t, mean of 4 |
|---|---:|---:|---:|---:|---:|
| ids-full | +0.0914 | 3.19 | 3.97 | 2.98 | 4.11 |
| seed-only | +0.0897 | 3.41 | 4.50 | 3.79 | 4.72 |
| seed-rule | +0.0064 | 0.24 | 0.34 | 0.55 | 0.36 |
| seed-rule3 | −0.0317 | −1.15 | −1.63 | −1.04 | −1.75 |
| cand | −0.0231 | −0.73 | −0.94 | −0.65 | −0.98 |
| control:1 | −0.0379 | −1.55 | −2.38 | −1.81 | −2.63 |
| control:2 | +0.0341 | 1.36 | 2.06 | 1.39 | 2.23 |
| control:3 | −0.1010 | −3.34 | −4.80 | −3.25 | −5.15 |
| control:4 | 0.0000 | 0.02 | 0.01 | −0.22 | 0.00 |

- In every arm with a non-trivial effect (\|t\| ≥ 0.9 under mean-of-3: 7 of 9 arms), majority-of-3 has the lower
  \|t\|. The same holds for parent:B (0.27 vs 0.61).
- The two exceptions are null effects: seed-rule (+0.0064, \|t\| 0.34 → 0.55) and control:4 (0.000, 0.01 → 0.22). There
  the estimand shift moves the point estimate (seed-rule +0.0064 → +0.0128); it does not add precision.
- Majority-of-3 is about as powerful as a single run, at three times the cost.
- **Verdict: do not introduce majority voting anywhere in the evaluation layer.** The protocol's averaged-run bounds are
  the right estimator.

## 6. Serving drift between sessions (new finding)

### 6.1 Reply style by session

"Bare" means the whole reply is `<answer>…</answer>` or `{"answer": …}` with no reasoning. The two texts compared are:
- the empty scaffold: E-ds step 0, which equals cal-1 parent:A/B;
- the task card: I-ds step 0, which equals cal-1 ids-full.

Identical system prompts were verified by hash (`ee9b737f16b8` for the task card). Times are CST, 2026-10-20 unless
noted.

| time | session | text | calls / items | bare share | pass | median completion tokens |
|---|---|---|---|---:|---:|---:|
| 10-19 23:26 | v3 I-ds s1 train | task card | 400 / 200 | 0.077 | 0.775 | 62 |
| 00:07–00:18 | v3 E-ds s1 train | scaffold | 400 / 200 | **0.868** | 0.743 | 10 |
| 00:20 | v3 I-ds s1 screen | task card | 430 / 200 | **0.837** | 0.740 | 10 |
| 01:07–02:03 | v3 E-ds s1 screen | scaffold | 450 / 200 | 0.376 | 0.620 | 32 |
| 01:37 | v3 I-ds s3 screen | task card | 120 / 60 | 0.058 | 0.733 | 64.5 |
| 02:04–02:15 | v3 E-ds s1 confirm | scaffold | 412 / 200 | 0.493 | 0.680 | 14 |
| 02:28 | v3 I-ds s4 screen | task card | 120 / 60 | 0.858 | 0.708 | 10.5 |
| 02:30–02:47 | v3 E-ds s2 screen | scaffold | 120 / 60 | 0.925 | 0.692 | 10 |
| 03:11–03:28 | v3 E-ds s3 screen | scaffold | 120 / 60 | 0.892 | 0.708 | 10 |
| 03:13 | v3 I-ds s4 confirm | task card | 120 / 60 | 0.833 | 0.750 | 11 |
| 04:06–04:54 | v3 E-ds s4 screen | scaffold | 120 / 60 | 0.917 | 0.692 | 10 |
| 06:35 | v3 I-ds s5 screen | task card | 120 / 60 | 0.817 | 0.750 | 11 |
| 15:59–16:03 | cal-1 pre-round | scaffold | 400 / 200 | 0.155 | 0.675 | 41 |
| 16:07–18:04 | cal-1 attempt-1 | scaffold | 1,305 / 200 | 0.126 | 0.683 | 42 |
| 16:07–18:04 | cal-1 attempt-1 | task card | 657 / 200 | 0.058 | 0.767 | 61.5 |
| 19:04–19:33 | earlier D5 pilot | scaffold | 288 / 24 | 0.04–0.11 | 0.61–0.68 | 49 |
| 19:11–19:52 | cal-1 attempt-2 | scaffold / task card | 295 / 143 | 0.112 / 0.063 | 0.688 / 0.804 | 41 / 66 |
| 10-21 00:06–00:24 | this pilot (T0) | scaffold | 128 / 20 | 0.06–0.21 | 0.48–0.66 | 39–41 |

(The 60-item regression panels and the pilots use other item sets. Their pass rates are not comparable to the 200-item
rows; their bare shares are.)

Readings (measured):
- The route alternated between a **terse mode** (82–93 % bare: 00:07–00:20 and 02:28–06:35) and a **verbose mode**
  (4–21 % bare: 10-19 23:26, 01:37, and 15:59 to 10-21 00:24), with partly mixed sessions at 01:07–02:15.
- **Both texts switch together.** For example, the task card was 84 % bare at 00:20 and 6 % at 01:37, while the scaffold
  was 87 % at 00:07 and 38 % at 01:07.
- So the style is a property of the serving at that time, not of the text.
- Inside cal-1 there is no time structure:
  - lag-1 autocorrelation of style residuals −0.017 (null SD 0.024), p = 0.47;
  - 10-minute bins range 0.07–0.24 bare.
- Within items, bare runs pass more often under the scaffold: +0.052 (SE 0.021), 42 vs 24 items, sign p = 0.036 (211
  items with both styles, all scaffold sessions pooled).

### 6.2 Effect on verdicts: same items, same request bytes, different sessions (measured)

| comparison (pass rate, A − B) | items | runs A / B | difference [95 % CI] | up / down | sign p |
|---|---:|---|---|---|---:|
| scaffold: v3 E-ds s1 train (87 % bare) − cal-1 parent A+B (13 %) | 200 | 2 / 8 | **+0.0575 [+0.019, +0.096]** | 44 / 15 | 0.0002 |
| scaffold: v3 E-ds s1 train (87 %) − v3 E-ds s1 screen (38 %) | 200 | 2 / ≈2 | **+0.056 [+0.016, +0.096]** | 26 / 12 | 0.034 |
| scaffold: v3 E-ds s1 confirm (49 %) − cal-1 parent | 200 | 2 / 8 | +0.015 [−0.013, +0.043] | 33 / 21 | 0.13 |
| scaffold: cal-1 pre-round − cal-1 main | 200 | 2 / 8 | −0.010 [−0.039, +0.019] | 30 / 21 | 0.26 |
| scaffold: cal-1 attempt-2 − attempt-1 | 156 | 1.9 / 6.1 | +0.012 [−0.024, +0.049] | 21 / 19 | 0.87 |
| task card: v3 I-ds s1 train (8 % bare) − v3 I-ds s1 screen (84 %) | 200 | 2 / ≈2 | **+0.000 [−0.031, +0.031]** | 12 / 13 | 1.0 |
| task card: v3 I-ds s1 train − cal-1 ids-full | 200 | 2 / 4 | +0.001 [−0.017, +0.020] | 12 / 12 | 1.0 |
| regression panels (terse) − cal-1 (verbose), five comparisons (plus one verbose − verbose check, +0.017) | 29 each | – | −0.034 to +0.052, all n.s. | – | ≥ 0.69 |

Readings:
- **Measured.** In a terse session the empty scaffold scores about 5.7 points higher on the same 200 items than in a
  verbose session. The format-pinning task card scores the same in both modes. This is visible in its verdicts, even
  though its *style* switches just as much.
- **Measured.** In v3 the E-ds parent itself moved −5.6 points between train (00:07) and screen (01:07) of the same
  stage: the train rollout and the screen were measured in different modes. This is larger than any rule effect v3
  measured.
- **Mechanism (claim).** The repository's probe notes (`scripts/weak_solver_probe.py` docstring, 2026-10-19, 48 calls
  each) record that "the endpoint mixes a thinking and a non-thinking serving from call to call". With thinking enabled,
  42 of 48 replies were thinking and 6 were not. A time-varying traffic share between at least two servings with
  different default styles fits all of the above. It cannot be verified from the client, because no serving identifier
  is exposed (§8.4).
- **Consequences.**
  - Any difference between numbers from different sessions is confounded by drift for texts that leave the answer
    format open, by up to about 6 points on SearchQA here. This includes stage tables assembled from evaluations run on
    different days, reused step-0 evaluations, and baselines from earlier runs.
  - Inside one session with interleaved dispatch, as cal-1 does it, the drift is common to both arms and cancels in the
    paired difference.
  - ν itself also varies by session. The scaffold's two-run ν was 0.035 in the terse v3 train session and 0.105 in
    cal-1, so a per-session re-estimate is needed.

### 6.3 The v3 noise floor is within-session noise (estimated from measured)

- Prediction: for each item, the unbiased probability that two disjoint 2-run sums differ was taken from cal-1's 8
  pooled parent runs. The average over 200 items is 0.149, which predicts **28.9 ± 3.4** of 194 items to change between
  two 2-run measurements of the same text.
- Observation: v3 recorded **30 of 194** (17 up / 13 down, E-ds s1 screen → confirm, which were two sessions only
  moderately apart in style).
- The registered "16 % non-reproducible" is therefore what ν predicts, with no extra cross-session component needed
  there.

## 7. Per-benchmark noise (v3, parent Skill, training-side units, measured)

Columns:
- "Training rollout" means exactly 2 runs per item in one session, with no selection.
- "Pooled" adds the screen and confirm parent runs, which come from other sessions.
- SpreadsheetBench has 1 training run, so only the pooled figure exists for it.

| chain (Skill) | benchmark | items | ν, training rollout (SE) | identical reply pairs | median completion tokens | pooled: runs per item, ν (SE) |
|---|---|---:|---|---:|---:|---|
| I-ds (task card) | SearchQA | 200 | 0.090 (0.020) | 0.195 | 62 | 5.7, 0.067 (0.012) |
| I-ds | OfficeQA | 74 | 0.095 (0.034) | 0.446 | 10 | 8.5, **0.167** (0.027) |
| I-ds | LiveMath | 100 | 0.160 (0.037) | 0.010 | 276 | 5.4, 0.151 (0.019) |
| I-ds | SpreadsheetBench | 91 | 1 run | – | 373 | 4.7, 0.176 (0.027) |
| I-ds | ALFWorld | 57 | 0.140 (0.046) | 0.228 | 566 | 3.3, 0.099 (0.031) |
| E-ds (scaffold) | SearchQA | 200 | 0.035 (0.013) | 0.735 | 10 | 7.0, 0.087 (0.012) |
| E-ds | OfficeQA | 74 | 0.081 (0.032) | 0.541 | 10 | 7.9, 0.068 (0.018) |
| E-ds | LiveMath | 100 | 0.130 (0.034) | 0.010 | 238 | 3.8, 0.118 (0.021) |
| E-ds | SpreadsheetBench | 89 | 1 run | – | 347 | 2.2, 0.146 (0.035) |
| E-ds | ALFWorld | 57 | 0.140 (0.046) | 0.088 | 592 | 2.0, 0.140 (0.046) |

Readings:
- Long-reply benchmarks (LiveMath, SpreadsheetBench, ALFWorld) are noisier (0.13–0.18) and almost never reproduce text
  (1–5 % identical). This is consistent with the per-token hazard of §2.
- OfficeQA under the task card has a cross-session ν (0.167) well above its within-session ν (0.095). That suggests drift
  there too, with large SEs (estimated).
- All non-SearchQA figures rest on 57–100 items with SEs of 0.03–0.05. They are good enough for budgeting, not for fine
  comparisons.

## 8. The PJLAB deepseek route: parameters, reproducibility, concurrency

All calls in this section were made from the **new machine**, which answered throughout (occasional HTTP 429 when other
explorers loaded the route). They used the frozen client `scripts.weak_solver_probe.Client` with the pjlab_token route,
temperature 0 unless stated, thinking disabled and max_tokens 32,768. Scoring used the frozen native scorer.

Cost of this pass: 266 calls, 310 HTTP sends (44 retried after 429/5xx), **319,043 tokens**. The earlier D5 pilot was
288 calls and 553,507 reported tokens (9 calls without usage, 6 truncated runaways).

### 8.1 P0: parameter acceptance (10 calls, trivial prompt, 2026-10-21 00:05) (measured)

| request extra | HTTP | result |
|---|---:|---|
| none | 200 | `OK` |
| `seed: "not-an-integer"` | 200 | `OK`, accepted with no error |
| `seed: -1` | 200 | `OK` |
| `top_k: "abc"` | 200 | `OK`, accepted with no error |
| `zzz_unknown_field: 1` | 200 | `OK` |
| `n: 2` | 200 | **1** choice returned |
| `logprobs: true, top_logprobs: 3` | 200 | no logprobs returned |
| `top_p: 5.0` | 400 | `top_p must be in (0, 1], got 5.0. (parameter=top_p, value=5.0)` |
| `temperature: 5.0` | 400 | `temperature must be in [0, 2], got 5.0. (parameter=temperature, value=5.0)` |
| `max_tokens: -5` | 400 | `max_tokens must be at least 1, got -5. (parameter=max_tokens, value=-5)` |

What the replies contain:
- No `system_fingerprint`.
- Headers: connection, content-encoding, content-type, date, `server: nginx/1.30.4`, transfer-encoding, vary,
  x-accel-buffering, x-request-id (32 hex).
- id: `chatcmpl-<uuid4>`.
- usage: `prompt_tokens_details{cached_tokens, created_cache_tokens, multimodal_tokens}` and
  `completion_tokens_details{reasoning_tokens}`.

Inference (claim, strongly supported):
- The three 400 messages, including the `(parameter=…, value=…)` suffix, are verbatim from vLLM:
  `SamplingParams._verify_args` in `vllm/sampling_params.py` and `VLLMValidationError.__str__` in `vllm/exceptions.py`,
  both checked at source.
- vLLM's own OpenAI server would reject a non-integer `seed` or `top_k` in request validation.
- So the backend is very probably a recent vLLM behind a gateway. The gateway forwards temperature, top_p and max_tokens,
  and drops seed, top_k, n and logprobs.
- It is not DeepSeek's public API verbatim. That API documents no seed, top_k or n, says top_p is ignored in non-thinking
  mode, and returns a `system_fingerprint`.

### 8.2 P1: does any parameter make repeats reproducible? (160 calls) (measured)

Design: 8 cal-1 training items with medium-length parent replies (median 20–150 completion tokens; none used by the
earlier pilot), × 4 repeats × 5 configurations, shuffled across 4 workers.

| config | identical pairs / 48 | mean pair similarity | distinct replies per item (of 4) | pass rate |
|---|---:|---:|---:|---:|
| T0 (protocol) | 9 (0.188) | 0.674 | 3.00 | 0.656 |
| T1 | 2 (0.042) | 0.409 | 3.75 | 0.688 |
| T1 + `seed=777` | 2 (0.042) | 0.481 | 3.75 | 0.719 |
| T1 + `top_k=1` | 0 (0.000) | 0.382 | 4.00 | 0.750 |
| T1 + `top_p=1e-6` | 12 (0.250) | 0.732 | 2.88 | 0.656 |

Item-level sign tests (items with more / fewer identical pairs):

| comparison | items more / fewer | p | reading |
|---|---|---:|---|
| T1+seed vs T1 | 1 / 1 | 1.0 | seed ignored |
| T1+top_k=1 vs T0 | 0 / 6 | 0.031 | top_k ignored: it behaves like T1, not like greedy |
| T1+top_p vs T1 | 5 / 0 | 0.062 | top_p honoured: it truncates to the top token |
| T1 vs T0 | 1 / 5 | 0.22 | temperature honoured |

- A per-request seed on a vLLM backend would make the T1 repeats near-identical. 2/48 rules that out.
- At temperature 0, `top_p` cannot improve on greedy: T1 + top_p 12/48 against T0 9/48 shows no gain (items 2/2).
- **No request parameter makes T0 repeats reproducible.**

### 8.3 P2: concurrency 1 vs 12 at temperature 0 (96 calls) (measured)

Design:
- 12 items that are mixed under the parent (pooled π 0.25–0.75, at least 6 runs, none used before).
- 4 rounds. Each round has a 12-worker burst of all 12 items and a strictly sequential pass. The order of the two
  alternates by round.

| condition | identical pairs | verdict differs | bare share | pass rate |
|---|---:|---:|---:|---:|
| sequential (c1) | 16 / 72 (0.222) | 27 / 72 (0.375) | 9 / 48 | 0.521 |
| 12 concurrent (c12) | 19 / 72 (0.264) | 23 / 72 (0.319) | 10 / 48 | 0.479 |
| cross pairs | 49 / 192 (0.255) | 58 / 192 (0.302) | – | – |

Item level: c1 had more identical pairs in 5 items and fewer in 3 (p = 0.73), and more verdict disagreement in 3 items
and less in 1 (p = 0.625).

**The earlier D5 pilot** (2026-10-20 19:04–19:33; 24 items: 20 mixed and 4 always-pass; 3 repeats per configuration;
T0). Its three 12-worker configurations were interleaved in one pool and are effectively replicates, because seed and
top_k are dropped and top_p does not act at T0.

| config | identical pairs | verdict differs |
|---|---:|---:|
| base@12 | 12/59 (0.203) | 13/59 (0.220) |
| seed@12 | 17/65 (0.262) | 16/65 (0.246) |
| top_p 0.001 + top_k 1 @12 | 16/66 (0.242) | 14/66 (0.212) |
| base@1 (ran after the others, so time-confounded) | 25/70 (0.357) | 19/70 (0.271) |

**Combined over 36 items** (measured): c1 had more identical pairs in 19 items and fewer in 11 (p = 0.20). Verdict
disagreement was higher under c1 in 13 items and lower in 9 (p = 0.52). **No evidence that sequential dispatch reduces
verdict noise.** This is what one expects: our 12 workers are a small part of the server's batch (claim).

### 8.4 Is there any client-visible serving identity? (measured)

- **Fingerprint.** In the 160 greedy-like pilot calls (P1 T0, P1 T1+top_p, P2), the bare (22) and verbose (138) replies
  are identical in:
  - server header;
  - x-request-id shape;
  - id shape;
  - usage-detail pattern;
  - top-level keys.

  Only latency differs (median 0.35 s vs 0.57 s), and that is explained by reply length.
- **Prefix cache.**
  - cached_tokens takes the values 0 / 512 / 768 / 1,024, so the cache works in 256-token blocks.
  - The first call of every item was a miss (20/20).
  - Misses per item were 4.50 over 20 calls (P1) and 3.75 over 8 calls (P2). Under random routing with persistent
    per-domain caches, this fits **about 4–5 independent cache domains**, probably replicas (estimated; assumes no
    eviction and no shared cache).
- **Cache state predicts nothing** (within-item permutation, 10,000 draws):
  - verdict disagreement, miss-miss 0.394 vs hit-hit 0.202: the null mean difference from item composition is 0.178,
    p = 0.99;
  - text identity: p = 0.23;
  - bare share: p = 0.74;
  - over all 256 P1/P2 calls, non-first calls only: bare replies miss the cache somewhat more often (9/22 vs 52/214
    for verbose replies), p = 0.16. Suggestive of a separate serving at best; not significant.
- **Conclusion.** The client cannot see which serving answered, cannot pin one, and cannot detect a mode switch except
  through the content of the replies. Hence the canary of §11.

## 9. The Thinking Machines argument and what a client can do

**Sources, all verified at source (claim, cited).**
- **He et al., Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference", 2025-09-10.**
  - Floating-point non-associativity plus GPU concurrency is not the operative mechanism: the forward pass is run-to-run
    deterministic for a fixed batch.
  - What varies is the batch a request lands in. Kernels such as RMSNorm, matmul and attention change their reduction
    order with batch size: "the primary reason nearly all LLM inference endpoints are nondeterministic is that the load
    (and thus batch-size) nondeterministically varies".
  - Demonstration: Qwen3-235B-A22B-Instruct-2507, 1,000 completions at temperature 0 give 80 unique completions. The
    most common appears 78 times, and the first divergence is at token 103. With batch-invariant kernels all 1,000 are
    identical.
  - Cost: vLLM 26 s, then 55 s unoptimized, then 42 s with an improved attention kernel.
  - **No client-side remedy is offered.**
- **vLLM, "Batch invariance" (docs, beta).**
  - `VLLM_BATCH_INVARIANT=1`; NVIDIA compute capability ≥ 8.0, AMD, Intel XPU.
  - Validated models: DeepSeek-V3, V3-0324, R1 and V3.1. DeepSeek-V4 is not listed.
  - Tensor-parallel all-reduce caveat; "may impact performance".
- **SGLang (LMSYS blog, 2025-09-22).**
  - `--enable-deterministic-inference` with the FlashInfer, FA3 and Triton backends.
  - Qwen3-8B, 50 trials: 1 unique output, against 2–18 without.
  - Slowdown 25–45 % (average 34.35 %); TP1 and TP2.
  - MoE models including DeepSeek-V3 were "planned". Seeded sampling for temperature > 0.
- **Yuan et al. 2025 (arXiv 2506.09501).** Under bf16, greedy decoding varies by up to 9 % in accuracy and by 9,000
  tokens in length across batch size and GPU count/type. Their remedy, LayerCast, computes in fp32.
- **Atil et al. 2024 (arXiv 2408.04667).** 5 LLMs × 8 tasks × 10 runs under "deterministic" settings: accuracy varies by
  up to 15 %, with best–worst gaps up to 70 %.
- **Miller 2024 (arXiv 2411.00640).** Resampling reduces only the within-question term, and paired differences are
  recommended. The sample-size formula (Eq. 9), n = (z_{α/2}+z_β)²(ω² + σ²_A/K_A + σ²_B/K_B)/δ², is the one used in §10,
  with ω² = σ²_het and σ²_A = σ²_B = ν/2.

**Our measurements fit the argument (measured).**
- The per-token divergence hazard is about 3 % at temperature 0 (§2).
- Our own concurrency does not matter (§8.3).
- Request options cannot reach the batch (§8.1–8.2).
- The 4–5 cache domains and the documented thinking/non-thinking mix add between-serving variation on top of the
  within-serving batch variation (estimated / claim).

**What a client can and cannot do.**
1. **Cannot:** make the server's batch invariant; choose or pin the serving; detect the serving from metadata (§8.4).
   `seed` and `top_k` never reach the backend, and `top_p` cannot beat greedy.
2. **Keep temperature 0.** It is the most reproducible available setting (9/48 identical vs 2/48 at T1), but it is not
   determinism. Report it as such, with the measured ν.
3. **Pin the format in the text.** A format-pinning instruction halves verdict noise (0.05 vs 0.105) and makes verdicts
   immune to the terse/verbose drift (§6.2). This is the strongest client-side lever found.
4. **Make the drift common-mode.** Interleave all arms of a comparison in one shuffled pool in one session, and detect
   mode switches with a content canary (§11).
5. **Use statistics:** averaged runs, paired items, enough items (§10), honest SEs.
6. **Ask the operator** for batch-invariant mode, a single pinned serving and a fingerprint (§11 R7). If granted, the
   same-text noise ν goes to zero and same-text comparisons become exact.
7. **What determinism would not buy** (estimated). Different texts would still change outputs on boundary items. The
   irrelevant-text controls have σ²_het = 0.014–0.041 and effects of −10 to +3 points. So "is this rule better than an
   irrelevant edit" stays a statistical question about items. Determinism removes the ν term of §10, not the σ²_het
   term.

## 10. Item-count tables

Paired design, both arms r runs, normal approximation, power 0.8.
- Two-sided α = 0.05: n = 7.849 · (σ²_het + ν/r) / δ².
- One-sided α = 0.05, in brackets: the factor is 6.183.
- δ is in pass-rate points; 1 point = 2 items of 200.
- ν levels: 0.05 (task card, measured 0.049–0.054), 0.105 (empty scaffold, measured), 0.16 (cand/control:3, measured
  0.161).
- σ²_het = 0 answers "did the score on THESE items move?" (a fixed panel). σ²_het > 0 answers "does it generalize to new
  items?".

**T6a. Fixed panel (σ²_het = 0)**

| ν | r | 1 pt | 2 pts | 3 pts | 5 pts | 10 pts |
|---|---:|---:|---:|---:|---:|---:|
| 0.05 | 1 | 3925 (3092) | 982 (773) | 437 (344) | 157 (124) | 40 (31) |
| 0.05 | 2 | 1963 (1546) | 491 (387) | 219 (172) | 79 (62) | 20 (16) |
| 0.05 | 4 | 982 (773) | 246 (194) | 110 (86) | 40 (31) | 10 (8) |
| 0.05 | 8 | 491 (387) | 123 (97) | 55 (43) | 20 (16) | 5 (4) |
| 0.105 | 1 | 8242 (6492) | 2061 (1623) | 916 (722) | 330 (260) | 83 (65) |
| 0.105 | 2 | 4121 (3246) | 1031 (812) | 458 (361) | 165 (130) | 42 (33) |
| 0.105 | 4 | 2061 (1623) | 516 (406) | 229 (181) | 83 (65) | 21 (17) |
| 0.105 | 8 | 1031 (812) | 258 (203) | 115 (91) | 42 (33) | 11 (9) |
| 0.16 | 1 | 12559 (9893) | 3140 (2474) | 1396 (1100) | 503 (396) | 126 (99) |
| 0.16 | 2 | 6280 (4947) | 1570 (1237) | 698 (550) | 252 (198) | 63 (50) |
| 0.16 | 4 | 3140 (2474) | 785 (619) | 349 (275) | 126 (99) | 32 (25) |
| 0.16 | 8 | 1570 (1237) | 393 (310) | 175 (138) | 63 (50) | 16 (13) |

**T6b. Generalization, σ²_het = 0.02 (irrelevant-text controls, measured 0.014–0.024)**

| ν | r | 1 pt | 2 pts | 3 pts | 5 pts | 10 pts |
|---|---:|---:|---:|---:|---:|---:|
| 0.05 | 1 | 5495 (4328) | 1374 (1082) | 611 (481) | 220 (174) | 55 (44) |
| 0.05 | 2 | 3532 (2783) | 883 (696) | 393 (310) | 142 (112) | 36 (28) |
| 0.05 | 4 | 2551 (2010) | 638 (503) | 284 (224) | 103 (81) | 26 (21) |
| 0.105 | 1 | 9812 (7729) | 2453 (1933) | 1091 (859) | 393 (310) | 99 (78) |
| 0.105 | 2 | 5691 (4483) | 1423 (1121) | 633 (499) | 228 (180) | 57 (45) |
| 0.105 | 4 | 3631 (2860) | 908 (715) | 404 (318) | 146 (115) | 37 (29) |
| 0.16 | 2 | 7849 (6183) | 1963 (1546) | 873 (687) | 314 (248) | 79 (62) |
| 0.16 | 4 | 4710 (3710) | 1178 (928) | 524 (413) | 189 (149) | 48 (38) |

**T6c. Generalization, σ²_het = 0.035 (seed-rule / seed-rule3, measured 0.034)**

| ν | r | 1 pt | 2 pts | 3 pts | 5 pts | 10 pts |
|---|---:|---:|---:|---:|---:|---:|
| 0.05 | 1 | 6672 (5256) | 1668 (1314) | 742 (584) | 267 (211) | 67 (53) |
| 0.05 | 2 | 4710 (3710) | 1178 (928) | 524 (413) | 189 (149) | 48 (38) |
| 0.05 | 4 | 3729 (2937) | 933 (735) | 415 (327) | 150 (118) | 38 (30) |
| 0.105 | 1 | 10989 (8656) | 2748 (2164) | 1221 (962) | 440 (347) | 110 (87) |
| 0.105 | 2 | 6868 (5410) | 1717 (1353) | 764 (602) | 275 (217) | 69 (55) |
| 0.105 | 4 | 4808 (3787) | 1202 (947) | 535 (421) | 193 (152) | 49 (38) |
| 0.16 | 2 | 9027 (7110) | 2257 (1778) | 1003 (790) | 362 (285) | 91 (72) |
| 0.16 | 4 | 5887 (4637) | 1472 (1160) | 655 (516) | 236 (186) | 59 (47) |

**T6d. Generalization, σ²_het = 0.075 (task card or cand vs scaffold, measured 0.072–0.077)**

| ν | r | 1 pt | 2 pts | 3 pts | 5 pts | 10 pts |
|---|---:|---:|---:|---:|---:|---:|
| 0.05 | 2 | 7849 (6183) | 1963 (1546) | 873 (687) | 314 (248) | 79 (62) |
| 0.105 | 1 | 14128 (11129) | 3532 (2783) | 1570 (1237) | 566 (446) | 142 (112) |
| 0.105 | 2 | 10008 (7883) | 2502 (1971) | 1112 (876) | 401 (316) | 101 (79) |
| 0.105 | 4 | 7947 (6260) | 1987 (1565) | 883 (696) | 318 (251) | 80 (63) |
| 0.16 | 4 | 9027 (7110) | 2257 (1778) | 1003 (790) | 362 (285) | 91 (72) |

The full grid (r = 1, 2, 4, 8 for every row) is in `run2/tables.md` and `run2/item_count_table.json`.

**Cost per comparison on SearchQA** (estimated). Both arms; tokens use the measured 1,594 tokens per call averaged over
the cal-1 arms. Long-prompt texts like ids-full cost 3,859 per call.

| σ²_het, ν, δ | r = 1 | r = 2 | r = 4 |
|---|---|---|---|
| 0.035, 0.105, 5 pts | 440 items, 880 calls, 1.40 M | 275 items, 1,100 calls, 1.75 M | 193 items, 1,544 calls, 2.46 M |
| 0.035, 0.105, 3 pts | 1,221 items, 2,442 calls, 3.89 M | 764 items, 3,056 calls, 4.87 M | 535 items, 4,280 calls, 6.82 M |
| 0, 0.105, 3 pts | 916 items, 1,832 calls, 2.92 M | 458 items, 1,832 calls, 2.92 M | 229 items, 1,832 calls, 2.92 M |

- With σ²_het > 0, one run per item on more items is always the cheapest per call.
- For a fixed panel the cost is the same at every r, so r is then set by how many items exist.

**T7. Per benchmark: what the whole training pool can see** (estimated)
- Pool = the train + val parts of the frozen POOLS, as `coevo5/data.py` draws them (never the test pool).
- ν = the larger of the two chains' within-session training-rollout values. SpreadsheetBench uses its cross-session
  pooled value, because it has 1 training run.
- σ²_het = 0.035.

| benchmark | training pool | ν | items for 5 pts (σ²_het 0 / 0.035; 2 runs) | items for 10 pts (0 / 0.035; 2 runs) | smallest detectable effect with the whole pool (2 runs / 4 runs) |
|---|---:|---:|---|---|---|
| SearchQA | 600 | 0.090 | 142 / 252 | 36 / 63 | 3.2 / 2.7 pts |
| OfficeQA | 74 | 0.095 | 149 / 259 | 38 / 65 | **9.3 / 7.9 pts** |
| LiveMath | 283 | 0.160 | 252 / 362 | 63 / 91 | 5.6 / 4.6 pts |
| SpreadsheetBench | 120 | 0.176 | 277 / 387 | 70 / 97 | **9.0 / 7.2 pts** |
| ALFWorld | 57 | 0.140 | 221 / 331 | 56 / 83 | **12.0 / 9.8 pts** |

- On OfficeQA, SpreadsheetBench and ALFWorld, no design that uses only the existing training pool can see an effect
  below about 7–12 points.
- Smaller transfer effects there need one of:
  - more items (generated items, D6);
  - pooling across benchmarks, which changes the estimand;
  - version-level acceptance on fresh batches (D1/D8).

## 11. Recommendations

| # | action | expected effect | cost |
|---|---|---|---|
| R1 | Use the format-pinning task card as the parent/reference text in every measurement-critical comparison. For E-ds-type experiments, add a fixed answer-format instruction to the scaffold. | ν 0.105 → about 0.05, so the fixed-panel item count halves (T6a). Immune in verdicts to the terse/verbose drift (+0.000 / +0.001 vs +0.0575). | 0 |
| R2 | Same-session interleaving. Dispatch every compared arm in one shuffled pool in one session, including candidate, parent, controls and the paper's final stage table (NoSkill, baselines, every stage's Skill). Never difference numbers from different sessions. Re-run reused step-0 evaluations alongside new ones. | Removes up to about 6 points of cross-session bias for format-open texts on SearchQA (more is possible elsewhere). | No new kind of cost; re-running the final table in one session is the price of a fresh evaluation. Running it on test panels is an owner decision. |
| R3 | Drift canary per session/round. Run a fixed 40-item × 2-run block of the empty scaffold at the start and end, and record its bare share, ν and pass rate. Also record every arm's bare share as a free covariate. Flag a session whose canary bare share differs from the reference by more than about 0.15 (SE about 0.05 at 80 calls). | Detects a mode switch inside or between sessions; makes drift reportable. | 160 calls (start + end), about 0.2 M tokens per round |
| R4 | Average runs; never use majority voting. | Mean of 3 has variance 0.333× vs 0.759× for majority of 3. | 0 |
| R5 | For generalization claims, spend on items, not runs (r = 1–2). For fixed-panel gates, use 2–4 runs. | Item sampling dominates (SE ratio 1.2–2.2×). | See the T6 cost table |
| R6 | Size every panel from T6/T7 before launching. Small pools (OfficeQA 74, SpreadsheetBench 120, ALFWorld 57) cannot resolve less than about 7–12 points; state this MDE and use D6/D1/D8 for smaller effects. | Prevents runs whose null outcome is already decided by design (v3: 11-item trigger panels cannot reach p < 0.05). | 0 to plan |
| R7 | One request to the route operator: (a) an evaluation endpoint with batch-invariant or deterministic inference (vLLM `VLLM_BATCH_INVARIANT=1`; note DeepSeek-V4 is not on the validated list); (b) a single pinned serving, with no thinking/non-thinking mix; (c) a serving fingerprint (`system_fingerprint` or a header). Acceptance test: `d5r2_pilot.py --phase P1` (T0 rows) and `--phase P2`. Pass if all T0 repeats are byte-identical and the canary bare share is stable across two sessions a day apart. | If granted, ν → 0 for same-text comparisons, which removes the ν term of every T6 cell; σ²_het remains. | Our side: about 128–256 calls, about 0.16–0.32 M tokens; the operator's cost is about 1.3–2× latency (claim) |
| R8 | Remove seed, top_k, top_p and concurrency tuning from protocols and plans. Keep temperature 0. Use whatever concurrency the rate limit allows. | No measurable effect (§8). | saves effort |
| R9 | Report the SE components (D11): the SE conditional on the panel and the item-sampling SE, ν per session and per text, the canary, and the design's MDE. | Honest error bars; a null is read against its own detection floor. | 0 |

## 12. Risks and limitations

- **Single benchmark.** The cal-1-based numbers (ν per text, A−B null, majority, σ²_het, drift) are all SearchQA. The
  other benchmarks' ν come from 57–100 items × 2 runs with SEs of 0.03–0.05.
- **Pilot size.** The pilots are small: 8 and 12 items, plus the earlier pilot's 24. They can show a large effect, such
  as a seed that is honoured or a deterministic serving. They cannot exclude concurrency effects of a few points. P1's
  p-values are 0.03–0.06 on 8 items.
- **The drift evidence is observational.** Sessions were not randomized; the same requests and the same scorer were
  compared across sessions. Other unknowns may differ between sessions, such as load or provider updates. The direction
  is consistent (terse sessions favour the scaffold, three comparisons; the task card is unaffected, two comparisons),
  but the two-serving mechanism is a hypothesis with no client-visible confirmation.
- **σ²_het rests on these 10 texts.** A real learned rule may be more or less heterogeneous. The controls are not null
  (control:3 −10 points), so "noise" beyond ν partly includes real text effects.
- **The vLLM attribution** rests on verbatim validator messages. A different stack could copy them.
- **The 4–5 cache domains** assume random routing, no eviction and per-replica caches.
- **Run-level exchangeability** is not perfect (one-run split p = 0.07). Inside one session, text identity decays slowly
  with time (0.364 → 0.305), so a long session could straddle a mode switch, as v3 E-ds s1 did between train and screen.
- **The route was shared** with other explorers during the pilots (44 retried sends). This affects latency, not
  validity.
- **Not re-verified** from the earlier draft: the truncation-by-benchmark table and the adaptive-allocation analysis.

## 13. Artifacts

Mac: `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D5/`

- `report.md`: this file.
- `run2/tables.md`: rendered tables T1–T7.
- `run2/noise.txt`, `run2/noise.json`, `run2/noise.log`: §2–§5; from `d5r2_noise.py`. `run2/att1/` holds the same
  analysis on attempt-1 only.
- `run2/noise2.txt`, `run2/noise2.json`: exact majority moments, dispersion test, time gap, hazard, failure-enriched
  panels, tokens per call, item-count grid; from `d5r2_noise2.py`.
- `run2/item_count_table.json`: the full grid.
- `run2/followup.json`: time gap within attempt-1, hazard by the longer reply; from `d5r2_followup.py`.
- `run2/v3_bench_noise.json`: §7; from `d5r2_v3bench.py`.
- `run2/drift.json`, `run2/drift.log`: §6; from `d5r2_drift.py`.
- `run2/mode_pairs.json`: §6.2; from `d5r2_mode_pairs.py`.
- `run2/cal1_compact.json`: 9,200 compact cal-1 cell records; from `d5r2_extract_cal1.py`.
- `run2/cal1_req20.json`: the 20-item request-identity check.
- `run2/run2_items.json`: pilot item selection; from `d5r2_select.py`.
- Pilot (`d5r2_pilot.py`):
  - `run2/pilot/calls.jsonl`: 266 calls, one JSON line each; credential-bearing headers are filtered out.
  - `run2/pilot/summary.json`, `run2/analyse.log`, `run2/p0.log`, `run2/p1.log`, `run2/p2.log`.
- `run2/concurrency.json`: §8.3; from `d5r2_concurrency.py`.
- `run2/cache.json`: §8.4; from `d5r2_cache.py`. `d5r2_fingerprint.py` produced the fingerprint comparison.
- `run2/earlier_pilot/jobs.jsonl`, `run2/earlier_pilot/summary.json`: copies of the earlier pilot.
- Scripts: `d5r2_check_runs.py`, `make_tables.py`, plus the scripts named above.
- Earlier draft files: `d5_*.py`, `d5_*.json`, `pilot_items.json`.

Machines:
- New machine: `/data/feasibility/D5/run2/` (pilot, drift, concurrency, cache, v3 benchmark analysis) and
  `/data/feasibility/D5/pilot/` (earlier pilot).
- Old machine: `/data/feasibility-scratch/D5/run2/` (cal-1 analyses).
- The files `/data/feasibility-scratch/D5/{cells_main.jsonl, cells_pre.jsonl, extract_cells.py}` (23:44) were written by
  another agent and were left untouched.

Re-run commands (new machine, proxy on):

```
ssh -o BatchMode=yes <datatools-login> "cd /data/feasibility/D5/run2; bash -ic 'proxy_on >/dev/null 2>&1; /root/continual-alf-prep-20260928/env/bin/python -I d5r2_pilot.py /data/feasibility/D5/run2/pilot run2_items.json --phase P1'"
```

Replace `P1` with `P0` or `P2` for the other phases. Use `--analyse` to rebuild `summary.json`.
