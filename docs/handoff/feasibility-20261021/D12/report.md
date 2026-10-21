# D12: Measuring cross-domain transfer without a validation set (design for coevo5 v5)

Explorer report, 2026-10-21. English, full detail. Every number is labelled **measured** (counted from data or
code in this exploration), **estimated** (arithmetic on measured components; the assumptions are stated), or
**claim** (a design proposal or an author's statement). Denominators are given. No test or holdout pool was read.

## 0. Bottom line

1. **v3 never exercised its transfer machinery.** Measured from the v3 records: 0 forward panels were built in
   10 chain-steps, because 47 of 49 proposals were local, 1 row was invalid, and the single "similar" rule (E-ds s3-r5)
   died at support (trigger 2 < 4) before the self-test that builds forward panels. v1 (GLM chains): 3 similar
   proposals, 0 forward panels.
2. **The forward pathway would also have failed if it had run.** Measured: the v3 Wikipedia client (no throttle, no
   retry) gets HTTP 429 on 38 of 48 requests at 6 threads. In an unthrottled 6-thread pilot that ran the frozen v3
   `research.material` + `forward.build_panel`, 17 of 18 panels came back with 0 items (89 of 90 material requests
   found nothing) at a cost of 105,667 GLM tokens. v3 runs panels with `workers = 16`.
3. **Panels of 8-12 items cannot show transfer and only catch large harm.** Measured by resampling real cal-1
   SearchQA cells (within one session): at n = 12 a real +9.1-point instruction effect is detected 17% of the time,
   a neutral text passes the registered C4' check 66% (one round) / 43% (two rounds), and a -10-point harmful text
   still passes 25% / 9%. Detecting +3.4 points needs more than 400 items (73% power at n = 400).
4. **Serving drift between sessions is larger than the effects we want to measure.** Measured on the same text
   (I-ds parent, hash ee9b737f16b8) and the same 60 OfficeQA training items: 50.8% pass in one session, 26.7% in two
   later sessions, 34.2% in a fourth (120 cells each). The registered transfer readout subtracts test scores taken
   in different sessions, so it inherits this drift. Estimated T_sim standard error: 5.8 points with the I-ds drift
   components, versus 1.1 points when parent and child are evaluated paired in one session.
5. **Generated items are not the target benchmark.** Measured on the items: generated OfficeQA-style items are
   one-step arithmetic on small Wikipedia tables (all 9 kept items of one smoke panel came from a single page,
   "World population", which supplied 3 of its 5 rounds); real OfficeQA items are long Treasury Bulletin pages. Generated LiveMath-style items are
   five numeric options computed by a formula; real LiveMath items are research-level theorem-strength multiple choice
   with a meta-option ("One of the remaining options is correct, but a stronger result can be proven.").
6. **Design (claim).** Split the three jobs that v3 gives to one forward panel. (a) A *selection guard*: a generated,
   rule-independent target-level panel per target per step, larger (about 40 items, 2 runs), drawn before proposals,
   used only to block visible harm, and only once a hardened generator has shown on a frozen bank that its items
   reproduce the real benchmark's mix of solved and unsolved items (the current generator does not: item 8). (b) A *co-evolution signal*: a separate generated stream that the roles may see.
   (c) *Measurement*: the sealed real test sets of the similar targets, parent and child re-evaluated paired in one
   session, with controls (same rule placed locally, a length-matched placebo, and the good-instruction baseline).
   Do not sample the next benchmark's training pool for selection: it would break registration section 2.2 and make
   that pool a validation set, which the owner's yardstick forbids.
7. **Minimal change for v3 to run every step (claim, code-located).** Build panels for *every* supported rule at a
   checkable step (`step.py` line 585 filters on `placement == "similar"`), run C4' as a logged shadow check that does
   not change the local verdict, throttle Wikipedia, and stop voiding the analyst reply over the `transfer` slot.
   Measured on v3: this would have exercised C4' at 7 of 8 checkable chain-steps, with generated panels at only 3 of
   them (I-ds s1, E-ds s1, E-ds s2); the other checks use real regression panels. Step 5 (ALFWorld) has no similar
   target under the registered map, so "every step" can mean steps 1-4 only.

8. **Pilot: generated panels are saturated (measured, small n).** On 23 generated OfficeQA-style items the frozen
   solver passed 92 of 92 cells with the good instruction, with no instruction, and with the rule placed similar;
   a text written to hurt decimal answers ("round to whole numbers") also passed 23 of 23; only "write numbers in
   words" (format breakage) registered (3 of 23 pass). On the real OfficeQA training pool the same decimal-hurting text lost 4 items and
   gained 1 (57 paired items; -5.3 points [-12.3, +1.8], not significant), and 65% of real items are failed by both
   good and empty instructions. 10 generated LiveMath-style items: 30 of 30 cells passed. Three throttled
   target-level panels (2 LiveMath-style, 1 OfficeQA-style) were all short (7, 3, 7 valid items).

Feasibility: **medium**. The measurement half (paired, same-session test re-evaluation with controls) is
straightforward and uses machinery that already exists. The selection half is the weak link: with the current
generator a forward guard on a not-yet-learned benchmark is close to vacuous (saturated items, short panels), and
the only stronger alternative (the next benchmark's real training items) gives up registration 2.2. A forward guard
therefore needs either a much harder generator, shown to reproduce the real benchmark's mix of solved and unsolved
items, or an explicit owner decision to accept "transfer with target validation data".

## 1. What I did

- Read `skillopt/coevo5/forward.py` (443 lines), `research.py` (702), `protocol.py`, `step.py`, `gate.py`, `stats.py`,
  `readout.py`, `evaluation.py`, `analyst.py`, `skill.py`, `cells.py`, `continual_eval/backends.py`; verified by md5
  that the coevo5 files are byte-identical in the local repository, `/data/skillopt-work`, and the frozen v3 snapshot
  `/data/coevo5-20261019-v3-source-f`.
- Read the registration v6 (sections 1, 2, 2.2, 3, 4, 5.1-5.9, 7, 8, 9, 10, 12.1-12.8, 20), the v2 delta (section 4,
  the transfer slot), the v3 delta (sections 0-2), the cal-1 registration, `docs/handoff/coevo5_transfer_sim.py`, and
  the v1 report.
- Measured from v3 records (training side only; the `selftest` unit was skipped because its name contains "test"):
  14,178 cells flattened (`cells.jsonl`), per-cell costs, instruction effects, same-text session drift, flip rates,
  C4' pass rates of real rule arms. Re-ran the earlier explorer's `v3_funnel.py` and `smoke_forward.py`; both outputs
  were byte-identical.
- cal-1 (old machine, read-only): extracted 8,800 cells (6,008 pass, 2,777 fail, 15 unknown; 16 duplicate records
  handled) and ran a resampling power study per panel size and decision rule.
- Literature: verified the transfer metrics and protocols of GEM, TRACE, ExpeL, AWM, OPRO, MetaSPO, GEPA, ACE,
  Dynamic Cheatsheet, Miller (2024), GSM-Symbolic, DyVal, from the papers themselves (arXiv HTML or PDF).
- Pilots (paid, new machine, 2,006,195 recorded tokens): generation of forward panels with the frozen v3 code
  (gen1 unthrottled, gen2 throttled and stopped, gen3 rule-independent target-level panels), solving of generated
  OfficeQA- and LiveMath-style items by the frozen v3 solver with positive controls, and a real-pool contrast on the
  OfficeQA training pool. See section 4.6.

## 2. How v3 measures transfer today (code-verified)

- **Map.** `similar_targets(bench)` returns (backward, forward). SearchQA step: forward OfficeQA. OfficeQA step:
  backward SearchQA, forward LiveMath (SpreadsheetBench is registered as similar to OfficeQA but is not in
  `FORWARD_STYLES`, so it is never checked forward). LiveMath step: backward OfficeQA. SpreadsheetBench step:
  backward OfficeQA. ALFWorld step: none.
- **Placement.** The analyst gives each rule `placement` local or similar (`MAX_SIMILAR_RULES = 2`). A similar rule is
  the same text in its home section plus every checkable similar target section (`Rule.also`). The analyst also fills
  a `transfer` slot ({"rule": n} or {"none": reason <= 300 chars}); a malformed slot voids the whole reply.
- **Forward panels** (`forward.py`): per similar rule and forward target, `research.material` fetches a Wikipedia
  table (OfficeQA style) or definition (LiveMath style) "on the topic of the rule"; one GLM call writes 3 items "that
  exercise the situation the guidance rule addresses"; one independent check call per item; answers are exact
  `Fraction` arithmetic over table-cell literals. `FORWARD_ATTEMPTS = 5` rounds, panel = first 12 valid distinct
  items, fewer than 8 = "short", and a short panel silently turns the rule into a local-only rule
  (`similar_status = "forward_panel_short"`). Built only in `selftest` (`step.py` 584-600), with
  `run_parallel(..., workers=setting.workers)`; the v3 manifest has 16 workers.
- **Gate C4'** (`gate.py` `_similar`): on each similar target, sum L(rule) - sum H(parent) >= 0 (L counts unknown as
  fail for the rule, H counts unknown as pass for the parent), no controls. Backward targets use the 60-item
  regression panel (parent 2 runs, rule 1 run); forward targets use the generated panel at `FORWARD_RUNS = 2`.
  `gate.py` line 93 requires `FORWARD_PANEL[0] <= len(items) <= FORWARD_PANEL[1]`.
- **Readout** (registration 12.8): Delta A[s][b] = A[s][b] - A[s-1][b] on test sets, 1 run per item per stage; an
  unchanged Skill reuses records (Delta = 0 exactly). Similar cells: (1,OfficeQA), (2,LiveMath), (2,SearchQA),
  (3,OfficeQA), (4,OfficeQA); (2,SpreadsheetBench) is counted as "rest". Q1 self > 0, Q2 T_sim one-sided 95% lower
  bound > 0, Q3 rest > -2. Test sizes: SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 279, ALFWorld 134.
- **Registered position** (sections 5.1, 8): C4' only blocks visible worsening; forward items are selection material,
  never evidence of transfer; evidence is the test set only. Section 2.2: a benchmark not yet learned has had none of
  its real items or labels used (only public task cards and researched public material).
- **Registered simulations.** Section 5.6: a neutral rule passes C4' in both rounds with probability 0.31-0.41, a
  +5-point rule 0.52-0.64, a -5-point rule on an 8x2 forward panel 0.21-0.26. Section 12.8: T_sim SE about 1.5
  points; P(Q2) about 0.25-0.27 when similar cells gain about +1.5, 0.40-0.42 at about +2.1.

## 3. What v3 actually exercised (measured)

| Run | Chain-steps | Proposals | Similar proposals | Forward panels built |
|---|---|---|---|---|
| v3 (deepseek, I-ds and E-ds) | 10 (8 checkable) | 49 (47 local, 1 invalid row) | 1 (E-ds s3-r5, died at support: trigger 2 < 4) | 0 |
| v1 (GLM, E-glm and I-glm) | - | - | 3 (E-glm s2-r5 and I-glm s2-r5 insufficient support; I-glm s1-r5 dropped before dispatch) | 0 |

- Transfer slot over the 8 checkable v3 steps: 5 "none", 2 named a local rule (recorded "not_a_similar_rule":
  I-ds s2 rule 4, E-ds s2 rule 3), 1 named the similar rule (E-ds s3).
- 2 of 13 v3 analyst calls were voided for the slot alone (I-ds s1 and s2, attempt 1: a "none" reason of 307 and 321
  characters, limit 300). Each void forced a full re-ask (about 60k and 82k tokens). Both voided replies had
  all-local placements.
- v1 transfer readout: Q2 T_sim +4.1 (lower bound +2.7) was reported as passing while "similar placement was unused".
  The E-glm chain accepted two LOCAL SearchQA rules at stage 1 and its OfficeQA test went 50 -> 85 / 172
  (+20.3 [+12.2, +28.5]); SkillOpt-glm (+4.2) and GEPA-glm (+3.8) show similar T_sim. So the registered T_sim can be
  passed by local text and by baselines: it is not specific to the similar mechanism (as the v1 report itself says).

## 4. Measured facts that constrain the design

### 4.1 Forward-panel generation: yield, cost, and a concurrency defect

- Smoke panels (pre-run directories; sequential, one panel at a time): 9, 10, and 4 valid items of a 12-item maximum
  (1 of 3 short). Drops in the first: 3 `literal_not_in_table`; material "none" in 1 of 5 rounds. GLM cost per
  5-round panel: 35,368 / 22,975 / 31,868 tokens, i.e. about 2.3-8 k tokens per valid item.
- gen1 (frozen v3 code, 6 panels in parallel, as `run_parallel` would): 18 panels (6 topics x 3 replicates), 17 with
  0 items; 89 of 90 material requests "none"; 271 GLM calls, 105,667 tokens. Diagnosis: sequential Wikipedia requests
  succeed; one material request alone found a table in round 1 with 3 calls; 6 concurrent threads got HTTP 429 on
  38 of 48 requests. The v3 `Wikipedia._get` raises `FetchError("http_429")` with no retry, and `request()` consumes
  the round. In the v3 run only 4 research requests were made (16 searches, all ok), so the defect never surfaced.
- gen2 (same, with a documented pilot deviation: one Wikipedia request at a time, >= 1 s apart, up to 5 retries on
  429): see section 4.6.

### 4.2 Construct gap between generated and real items (measured on the items)

- OfficeQA: generated = short questions over small Wikipedia tables (e.g. "By how many millions did Africa's
  population grow between 1950 and 1999?", answer 562, formula 783 - 221). Real = long Treasury Bulletin pages with
  table lookups. The generator is instructed to target the rule's situation, so panels are rule-specific, not a sample
  of the target distribution.
- LiveMath: generated = definition-based questions with five numeric options from a formula. Real = research-level
  theorem-strength statements with the meta-option quoted above. This is a construct mismatch, not a sampling issue.
- Literature agrees that generated variants are not exchangeable with originals: GSM-Symbolic (100 templates x 50
  instances) found lower accuracy on variants (e.g. Gemma2-9B 85.3 -> 79.1) and over 12 points between the best and
  worst instantiation for some models.

### 4.3 Noise: within-session flips and between-session serving drift (measured)

- Within one session, share of items whose two runs of the same text disagree: I-ds OfficeQA 0.125, LiveMath 0.162,
  SearchQA 0.033, SpreadsheetBench 0.175; E-ds OfficeQA 0.067, SearchQA 0.042, LiveMath 0.128.
- Between sessions, same text and same items (I-ds parent on the 60 OfficeQA regression items, 120 cells each):

| Session (2026-10-20) | Median completion tokens | Verbose share | Pass |
|---|---|---|---|
| s3 screen 01:35-02:04 | 232 | 0.89 | 50.8% |
| s4 screen 02:28-03:09 | 10 | - | 26.7% |
| s4 confirm 03:13-03:58 | 10 | - | 26.7% |
| s5 screen 06:35-10:11 | - | 0.35 | 34.2% |

- SD of session means for the same text: I-ds OfficeQA 11.36 points (4 sessions), I-ds LiveMath 11.84 (includes an
  18-item subset; less reliable), I-ds SearchQA 2.66, E-ds OfficeQA 1.27 (3 sessions, all terse), E-ds SearchQA 3.57.
  With 3-4 sessions these SDs are themselves imprecise (relative SE roughly 40%).
- Inside one round the arms share the serving mode (I-ds s3 screen: parent verbose share 0.89, rule arm 0.78, both
  about 51% pass). So within-round paired comparisons are protected; comparisons across sessions are not.
- cal-1 versus v3, same 200 SearchQA items, same two texts (ids-full vs scaffold): +9.12 [+5.0, +13.38] (4 runs, one
  session) in cal-1 but +3.2 [-0.2, +7.0] (2 runs) on the v3 training units. Effect sizes themselves move between
  sessions.

### 4.4 Power per panel size (measured by resampling cal-1, SearchQA, within one session)

Items resampled with replacement from the 200 cal-1 items; runs split without replacement into disjoint rounds;
4,000 resamples; configuration (candidate runs, parent runs) = (1, 2) unless stated. "C4'" = registered rule
(sum L - sum H >= 0) in one round / two disjoint rounds; "SUP" = one-sided paired t, p < 0.05; "NI3" = one-sided 95%
lower bound > -3 points; true effects are the full-sample differences vs parent:A.

| n items | Neutral text (+0.5): C4' pass | -3.8 text: C4' pass | -10.0 text: C4' pass | +9.1 (ids-full): SUP | +3.4 (control:2): SUP | Neutral: NI3 |
|---|---|---|---|---|---|---|
| 12 | 0.66 / 0.43 | 0.44 / 0.23 | 0.25 / 0.09 | 0.17 | 0.07 | 0.22 |
| 24 | 0.63 / 0.38 | 0.34 / 0.14 | 0.12 / 0.03 | 0.34 | 0.14 | 0.21 |
| 60 | 0.61 / 0.35 | 0.20 / 0.05 | 0.03 / 0.00 | 0.63 | 0.23 | 0.29 |
| 100 | 0.60 / 0.35 | 0.12 / 0.02 | 0.00 / 0.00 | 0.83 | 0.29 | 0.37 |
| 200 | 0.64 / 0.37 | 0.04 / 0.00 | 0.00 / 0.00 | 0.97 | 0.49 | 0.57 |
| 400 | 0.66 / 0.42 | 0.01 / 0.00 | 0.00 / 0.00 | 1.00 | 0.73 | 0.82 |

- (2, 2) runs change little (e.g. n = 60: ids-full SUP 0.68, neutral C4' 0.62 / 0.35); (4, 4) helps small effects
  (n = 60: ids-full SUP 0.75; control:2 SUP 0.34; neutral NI3 0.62; n = 200: neutral NI3 0.97).
- False positives of SUP for the neutral text: 0.03-0.08 up to n = 200 (0.11 at n = 400, a resampling artifact of the
  +0.5 sample difference).
- The empirical neutral C4' pass rate (two rounds 0.35-0.43) is a little above the registered model's 0.31-0.41
  because ties pass.
- Real rule arms on v3 regression panels (one round, later stages, rule vs parent): 16 of 21 passed C4' (SearchQA
  7/9, OfficeQA 5/7, LiveMath 3/4, SpreadsheetBench 1/1).
- Caveat: SearchQA has the lowest flip rate (0.033). OfficeQA and LiveMath flip 2-5 times as often, so the same n
  gives less power there (estimated).

### 4.5 How large are instruction effects on these benchmarks (measured, v3 training units, deepseek)

I-ds seeds (task-card instructions) versus the E-ds scaffold, same items, same units:

| Benchmark | Items x runs | Effect (points) | 95% CI | Up / down / tie | Note |
|---|---|---|---|---|---|
| SearchQA | 200 x 2 | +3.2 | [-0.2, +7.0] | 20 / 11 / 169 | 33 dead, 135 saturated |
| OfficeQA | 74 x 2 | +4.7 | [-1.4, +11.5] | 9 / 5 / 60 | 48 of 74 (65%) dead in both arms |
| LiveMath | 100 x 2 | -4.5 | [-10.0, +1.0] | 9 / 15 / 76 | 50 dead |
| SpreadsheetBench | 91 x 1 | +1.1 | [-8.8, +9.9] | - | - |
| ALFWorld | 57 x 2 | +10.5 | [+2.6, +18.4] | 12 / 3 | sign test p = 0.035 |

Only ALFWorld is significant. Rule-sized effects (v3: no rule accepted; cal-1 rule-carrying arms seed-rule +0.1, cand -2.9, seed-rule3 -3.2) are smaller
still, so a transfer measurement must resolve 2-3 points to be useful.

### 4.6 Pilot: generation yield and whether generated panels discriminate

All pilot calls ran on the new machine with the frozen v3 code, model routes and solver settings (GLM-5.3 for
generation; deepseek-v4-flash, thinking disabled, temperature 0, max_tokens 32768, layout `contract-first-v2`, native
OfficeQA scorer). The texts are the exact v3 texts: the I-ds parent and the E-ds scaffold were rebuilt from the v3
merge records and checked against the hash every v3 parent and training cell recorded (ee9b737f16b8 and cc516459810a).
Concurrency limit (6 on the new machine): for about 4 minutes a first solve attempt (`solve1`, 6 threads) ran
alongside gen2 (6 threads), exceeding the limit; I stopped it when I noticed (it had saved no cells) and kept every
later combination at 6 or below.

**Phase 1, generation (measured).**

- gen1 (frozen v3 code, 6 panels at once): 17 of 18 panels empty; 105,667 GLM tokens (section 4.1).
- gen2 (throttled Wikipedia, 6 topics x 3 replicates: 2 rule-independent "target" topics and 4 v3 rule texts):
  stopped by me after 17 minutes because it would not finish before the 05:59 hand-over and because a parallel solve
  run would have exceeded the concurrency limit. 11 of 18 panels had started; none had finished writing (the script
  wrote at the end). Indicative only: the throttled client cached 165 Wikipedia responses for those 11 panels, against
  36 for all 18 panels in gen1. Its GLM token use was not recorded.
- gen3 (rule-independent target-level panels, 2 LiveMath-style + 1 OfficeQA-style, written per panel): all 3 panels were **short** (fewer than the 8-item minimum): LiveMath 7 and 3 valid items, OfficeQA 7 valid
  (12 + 9 + 12 generated; drops: options 3 + 6, literal_not_in_table 5, answer_mismatch 1, check_rejected 1). 75 GLM
  calls, 111,728 tokens (about 6.6k per valid item); 117 Wikipedia requests with 53 HTTP-429 retries even when
  serialized at >= 1 s spacing, 0 failures after retry; 290-374 s per panel. Under v3 each of these panels would
  have turned its rule into a local-only rule. The LiveMath-style items are elementary number theory from one page
  ("Fundamental theorem of arithmetic" supplied 4 of 5 rounds in one panel): e.g. the largest prime factor of
  2024, the number of divisors of 60. The OfficeQA-style target-level items came from "United States federal
  budget" (4 of 5 rounds) and contain a near-duplicate (two items with the same formula 31.1 - 21.0, worded
  "increase" and "change"), which text-level de-duplication does not catch. Across all six throttled or sequential
  panels observed (3 smoke + 3 gen3), 2 of 6 reached the 8-item minimum.

**Phase 2, do generated panels discriminate? (measured)** Items: the 23 generated OfficeQA-style items of the three
pre-run smoke panels (9 + 10 + 4), all built for SearchQA rules (forward target OfficeQA).

| Arm (text) | Cells | Pass | Note |
|---|---|---|---|
| P: I-ds parent (good instruction) | 46 (2 runs) | 46 | 0 of 23 items flipped between runs |
| E: E-ds scaffold (no instruction) | 23 | 23 | |
| R: P + the panel's own rule at similar placement | 23 | 23 | |
| H1: P + "round every numeric answer to a whole number" (written to hurt decimal answers) | 23 | 23 | the solver followed each question's own rounding instruction |
| H2: P + "write numeric answers in English words" (breaks exact match) | 23 | 3 | only blatant format harm registers |
| PL: P + registered placebo 1 (haiku text) | 23 | 23 | |

- 92 of 92 cells passed for P, E and R: zero discordant items, so C4' (sum L - sum H >= 0) passes every text that
  keeps the answer format, and the panel cannot tell the good instruction from no instruction. On the real OfficeQA
  training pool the same two texts differ by +4.7 points [-1.4, +11.5] (74 items x 2 runs) and 65% of real items are
  failed by both: the generated panel is saturated where the real benchmark is mostly unsolved.
- With 0 failures in 92 cells, the per-cell failure rate of these generated items is below about 3.3% (95%, rule of
  three). Even at that upper bound a 40-item panel would hold about 1.3 failed cells per arm and run, so almost no
  discordant items.
- **Real-item contrast** (same positive control on the real OfficeQA training pool, 74 items from the v3 manifest's
  train and val panel files, P vs H1, 1 run each, interleaved; stopped at 130 of 148 cells at the hand-over because
  the shared deepseek route was rate-limiting): P passed 33 of 65 cells, H1 28 of 65 (unknown 5 and 2). On the 57
  items with both arms, H1 - P = -5.3 points [-12.3, +1.8]; H1 lost 4 items and gained 1 (sign test p = 0.375, not
  significant). All 4 lost items have decimal answers (0.063, 0.3535, 0.05, a list of decimals): the harm the text was
  written to cause, which the generated panel (23 of 23 passed) did not register. This is a direction, not an
  established effect.
- **LiveMath style:** the 10 generated LiveMath-style items of gen3 (both panels short) were also saturated: P 20 of
  20 cells, E 10 of 10. Real LiveMath training items: 50 of 100 failed by both texts (4.5).
- Cost (recorded): generated-item cells averaged 3,496 total tokens for P (median completion 63.5), 936 for E,
  3,332-4,700 for R; 264,950 tokens for the P/E/R run, 243,333 for the positive controls, 61,541 for the LiveMath
  items; real OfficeQA pool cells averaged 9.4k tokens (1,218,976 for 130 cells; this session served verbose
  replies, median completion 197-210 tokens). Pilot total recorded: 2,006,195 tokens (GLM 217,395; deepseek
  1,788,800); not recorded: gen2 (stopped before writing its call log; estimated 0.2-0.4M GLM from gen3's rate), the
  stopped solve1 (fewer than 20 cells) and the diagnostics (about 10k).

Reading (claim, small n): with the frozen solver, generated forward panels as built by v3 are a format check, not
a transfer guard, for both OfficeQA and LiveMath styles: they saturate (122 of 122 cells for the parent, scaffold and
rule arms) where the real benchmarks are mostly unsolved, and they miss a subset harm that real items show in
direction. This weakens design option A (6.1) unless the generator is made much harder (multi-step lookups over long
official tables; research-level statements for LiveMath) and its items are shown, before use, to reproduce the real
benchmark's mix of solved and unsolved items.

## 5. How other work measures transfer (verified from the papers)

| Work | What is transferred | How transfer is measured | Uncertainty reported |
|---|---|---|---|
| GEM (Lopez-Paz & Ranzato 2017), section 2 | Continual learner over T tasks | Matrix R[i][j] = test accuracy on task j after learning task i; ACC = mean of last row; BWT = (1/(T-1)) sum_i (R[T][i] - R[i][i]); FWT = (1/(T-1)) sum_{i>=2} (R[i-1][i] - b_i), b = test accuracy of the untrained model | - |
| TRACE (Wang et al. 2023) | Continual fine-tuning of LLMs on 8 tasks | OP and BWT on each task's test set (2,000 test examples per task), plus General Ability, Instruction Following and Safety Deltas against the initial model | - |
| ExpeL (Zhao et al. 2023), sections 4.4/5.4 | Insights learned on HotpotQA | Applied to FEVER after gpt-4-0613 rewrites them using the target's few-shot examples (k = 3); compared with Act, ReAct and "Transfer w/o task demos" | success rate mean +- SD (e.g. 70 +- 0.7 vs ReAct 63 +- 0.4) |
| AWM (Wang et al. 2024) | Workflows induced on Mind2Web training data | Cross-task, cross-website, cross-domain test splits; offline (from training) and online (from test queries, judged by an LM evaluator, no labels) | single runs at temperature 0, no CIs |
| OPRO (Yang et al. 2023), section 5.2.4 | Instructions optimized on 3.5% of GSM8K train (about 260 problems) | Evaluated on MultiArith and AQuA against "Let's think step by step" | single numbers |
| MetaSPO (2025) | System prompt meta-learned on source tasks | Unseen target tasks per domain (distinct subsets) and an unseen-domain setting (optimize on 3 domains, test on others); gain vs source-target similarity (Pearson +0.56) | 3 runs, t-test p <= 0.05, test <= 500 items per task |
| GEPA (Agrawal et al. 2025) | Optimized prompts | Cross-model only (Qwen3-8B -> GPT-4.1-mini, +9.00 aggregate over 6 benchmarks); no cross-benchmark experiment | none for the main results |
| ACE (2025) | Playbook contexts | Offline (train -> test) and online (sequential on test) per benchmark; no cross-benchmark transfer | - |
| Dynamic Cheatsheet (Suzgun et al. 2025) | Test-time memory | No cross-benchmark transfer; cross-model memory transfer gave "mixed results" | - |
| Miller (2024) "Adding error bars to evals" | (methodology) | Clustered SEs, question-level paired differences ("a free reduction in estimator variance"), K resamples per question, sample-size formula n = (z_a/2 + z_b)^2 (w^2 + s_A^2/K_A + s_B^2/K_B) / d^2 | recommends >= 1,000 questions for good signal |
| GSM-Symbolic (2024), DyVal (2023) | (generated evaluation) | Generated variants with computed answers; variants score lower and vary widely across instantiations | distributions over 50 instantiations |

What follows from this (claim):

1. The common practice measures transfer on the **target's held-out test set** against a **baseline that did not
   learn** (GEM's b, TRACE's initial model, OPRO's "Let's think step by step", ExpeL's ReAct). Our closest analogue of
   b is the good-instruction Skill (I-ds seeds) evaluated in the same session, not the empty Skill.
2. None of these works uses generated similar-target items as evidence of transfer. Generated items appear only as
   evaluation in their own right (DyVal, GSM-Symbolic), and those papers show such items shift accuracy.
3. Where target data enter adaptation (ExpeL's few-shot rewrite, AWM online), the papers say so and report it as a
   different setting. Sampling the next benchmark's training pool into our gate would be that different setting.
4. Most papers report single numbers. MetaSPO (3 runs, t-tests) and Miller (paired, clustered) are the exceptions;
   our serving drift makes their practice necessary, not optional.

## 6. Design for v5 (claims, with the evidence that motivates each)

### 6.1 Separate three jobs

| Job | Question | Material | Who may see it | Counts as evidence |
|---|---|---|---|---|
| A. Selection guard (C4') | Does this candidate visibly hurt a similar target? | Generated target-level panel (forward targets); real regression panel (backward targets) | gate only; roles see only accept/reject status | no |
| B. Co-evolution signal | Where does the Skill fail, and what rule would fix it? | A separate generated stream with guaranteed answers (the "generated tasks every step" pathway) | the roles (analyst, rewriter) | no |
| C. Measurement | Did the accepted Skill transfer to similar benchmarks, without drops elsewhere? | Sealed real test sets of the similar (and dissimilar) targets | nobody during the run | yes |

v3 makes one rule-specific forward panel do A and implicitly C. The registration already says the forward items are
not evidence (sections 5.1, 8); the design makes the separation physical (namespaces, directories, path guards).

### 6.2 Similar-target panels: generated vs sampled from the next benchmark's training pool

| | Generated (v3 `forward.py`) | Sampled from next benchmark's training pool |
|---|---|---|
| Registration 2.2 (unlearned benchmarks unused) | kept | broken |
| Owner yardstick (no validation set; evolve on one, evaluate on the rest) | kept | broken: the pool becomes a validation set for the current step |
| Construct validity | low (4.2) | high |
| Supply | unlimited in principle; measured: 2 of 6 sequential or throttled builds reached the 8-item minimum (9, 10, 4, 7, 3, 7 valid); 1 of 18 panels non-empty under 6-thread unthrottled concurrency | OfficeQA pool 74 items, 60 already the regression panel (14 left); LiveMath 283; SearchQA 600 |
| Cost | about 2.3-8 k GLM tokens per valid item (measured), plus cells | cells only |
| Later reuse | none | the same items are trained on at their own step after having filtered earlier rules (adaptive reuse) |
| Discriminates on the frozen solver? | no in the pilot: 92 of 92 cells passed for parent, scaffold and rule arms; a decimal-hurting text passed 23 of 23 (4.6) | yes (real items; 4.4 tables; the same decimal-hurting text lost items on the real pool, 4.6) |

Recommendation (claim): **generated for selection, real test sets for measurement; do not sample the next
benchmark's training pool.** If the owner wants a stronger guard than generated items can give ("采用效果好一点的方法"),
the honest stronger option is not the training pool but a larger generated panel plus the paired test measurement,
because the training-pool option changes what the experiment claims (it would become "transfer with target
validation data", like ExpeL's few-shot rewrite).

### 6.3 When panels are drawn

- **Selection panel (A):** one rule-independent target-level panel per (chain, step, target), drawn at the start of
  the step before the analyst replies; generation prompt names the target style but not the rule; seeded by the hash
  of (run, chain, step, target); built once and shared by every candidate and control of the step. Sharing gives
  paired comparisons between candidates and cuts generation cost from one panel per rule per target to one per target.
  Better still: a frozen bank generated before the chain starts (Wikipedia material archived by revision id, which
  v3 already records), from which each step draws a fresh disjoint slice. This removes live-fetch failures (4.1) and
  makes panels reproducible.
- **Rule-targeted panel (optional):** the v3 kind, drawn after the proposal, reported only as a mechanism diagnostic
  ("does the rule do what it says where it applies"), never gated on.
- **Co-evolution stream (B):** drawn every step from a different seed space and material slice; deduplicated against
  A by normalized question text and source page.
- **Measurement (C):** after the step's merge decision, only when the Skill changed.

### 6.4 How panels are scored

- Same frozen solver and native scorer as the real target (`backends.solve` / `backends.score`, layout
  `contract-first-v2`), same answer contract, L/H bounds as registered.
- All arms of a round interleaved in random order in one session; completion length recorded per cell so serving mode
  can be audited (4.3). Parent 2 runs, candidate 2 runs (4.4: (2, 2) costs little more than (1, 2)).
- Decision for A: keep C4' (both rounds) as a harm guard. Report per target the paired difference, its bootstrap CI,
  up / down / tie counts, and the dead and saturated shares. A panel with fewer than the minimum valid items is
  recorded as "unchecked", never silently as local-only.
- Measurement C, per similar cell: re-evaluate parent and child **paired in one session** on the target's test set,
  k runs per arm (k = 2 recommended); report the paired difference with CI; T_sim = mean of the similar cells. Controls
  in the same session: (i) the same rule with local placement only, which tells similar placement apart from bleed of
  local text (v1 showed local text moving OfficeQA by +20 points); (ii) a length-matched placebo; (iii) the
  good-instruction Skill as GEM's b.

### 6.5 Power per panel size (what each size buys)

From 4.4 (measured on SearchQA, the least noisy benchmark):

- **12 items (v3 maximum):** blocks only blatant harm (-10 points passes 9% over two rounds) and lets a -3.8-point
  text pass 23%; no evidence of help (+9.1 detected 17%).
- **40 items, 2 runs (proposed A):** between the 24- and 60-item rows: -3.8 passes about 0.10-0.14 (two rounds),
  -10 passes about 0.01, neutral passes about 0.37. A useful harm guard if the generated items behave like real ones.
- **To show help on one target:** +9 points needs about 100 items (0.83); +3.4 points needs more than 400 (0.73 at
  400). No similar test set except SearchQA (400) is that large, so single-cell transfer claims of a few points are
  out of reach; only the pooled T_sim can get there.

T_sim (estimated; `tsim_power.py`; null-rule run noise from the measured flip rates, session drift from the measured
session SDs; real effect heterogeneity would add variance):

| Design | I-ds components: SE / MDE80 (points) | E-ds components: SE / MDE80 |
|---|---|---|
| Registered readout, measured session drift | 5.79 / 14.4 | 1.47 / 3.7 |
| Registered readout, half that drift | 3.04 / 7.6 | 1.06 / 2.6 |
| Registered readout, no drift (registration assumption) | 1.06 / 2.7 | 0.87 / 2.2 |
| Paired same-session, k = 1 per arm | 1.19 / 3.0 | 0.96 / 2.4 |
| Paired same-session, k = 2 | 0.84 / 2.1 | 0.68 / 1.7 |
| Paired same-session, k = 4 | 0.60 / 1.5 | 0.48 / 1.2 |

(MDE80 = one-sided 5%, 80% power. The no-drift row is below the registered simulation's 1.5 because it omits effect
heterogeneity.) The paired design removes the drift term entirely, which is what makes T_sim interpretable.

### 6.6 Keeping panels out of the training signal

1. Namespaces: selection items `fwd:`, co-evolution items `sig:`, measurement items are real test ids. Separate
   directories; measurement records live where no unit reads (a path guard like the existing TestAccess).
2. No role sees selection or measurement items, per-item outcomes, or scores; at most the accept/reject status.
   The selection generator never sees the candidate rule (target-level panel).
3. Fresh draws: no selection panel is reused at a later step (adaptive reuse leaks through repeated filtering).
4. Deduplicate A against B (normalized text and source revision); a page may feed only one stream.
5. The next benchmark's training pool is untouched until its own step (keeps 2.2).
6. Post-run audit: hash every selection and measurement item and search all role transcripts (`roles.json`) for
   them; any hit voids that step's measurement.

## 7. Minimal change that makes the v3 machinery run every step

Code location (verified): `skillopt/coevo5/step.py` lines 584-600:

```python
supported = [i for i in plan["supported"] if rules[i]["status"] == "supported"]
similar = [i for i in supported if rules[i]["placement"] == "similar" and targets]
jobs = [(i, t) for i in similar for t in ahead]
```

Minimal change (a new protocol version; frozen v3 untouched):

1. **Check every supported rule:** `similar = [i for i in supported if targets]`, but run C4' as a **shadow** check
   that is logged and does not change the rule's local verdict (so the method is unchanged and only the measurement
   machinery runs). Making it decisive ("force similar") is a method change: it copies text into target sections and
   would exceed `MAX_SIMILAR_RULES = 2` (E-ds s1 had 4 supported rules).
2. **One target-level panel per target per step** instead of one per rule (fewer generations, paired comparisons).
3. **Throttle Wikipedia** (serialize, >= 1 s spacing, retry 429 with backoff): required, see 4.1.
4. **Do not void the analyst reply over the `transfer` slot** (2 of 13 v3 replies were voided for a reason over 300
   characters, costing about 60-82k tokens each); with every rule checked, the slot can become optional.
5. **Panel size:** raise `FORWARD_PANEL` (and `FORWARD_ATTEMPTS`) and the matching check at `gate.py` line 93; record
   a short panel as "unchecked".

Effect on v3 (measured from the funnel's self-test lists):

| Chain | s1 (fwd OfficeQA) | s2 (bwd SearchQA, fwd LiveMath) | s3 (bwd OfficeQA) | s4 (bwd OfficeQA) | s5 (none) |
|---|---|---|---|---|---|
| I-ds | 3 rules | 0 rules | 1 rule | 1 rule | 1 rule, no target |
| E-ds | 4 rules | 2 rules | 2 rules | 1 rule | 0 rules |

So C4' would have run at 7 of 8 checkable chain-steps. Generated panels would have been needed at 3 (I-ds s1 and
E-ds s1 for OfficeQA, E-ds s2 for LiveMath): 9 panels in the per-rule design or 3 in the shared design. The other
checks use the real 60-item regression panels. "Generated items every step" is therefore not what the v3 map gives:
steps 3-4 look backward to an already-learned benchmark, and step 5 has no similar target. If the owner wants
generated items at every step, they belong to job B (co-evolution signal), not to the transfer check.

## 8. Risks

- **Construct validity of generated panels** (4.2): a guard on small-table arithmetic may not predict harm on Treasury
  Bulletin pages; for LiveMath the generated items test a different skill.
- **Drift:** any comparison across sessions (the registered readout, cal-1 vs v3) can move by 10-25 points on OfficeQA
  for the same text (4.3). Paired same-session evaluation is the only remedy measured here.
- **Cost of paired re-evaluation** (section 9) roughly doubles the test cost of each changed step.
- **Small similar test sets:** OfficeQA 172 and LiveMath 125 cannot resolve 3-point single-cell effects (6.5).
- **Map validity:** the "similar" pairs are declared, not measured; MetaSPO found gain correlates with measured
  source-target similarity (Pearson +0.56), so a measured similarity (embedding or bag-of-words) per pair is worth
  recording.
- **Shadow checks cost tokens without changing decisions:** justified only if they are read as measurement of the
  guard, which they are.

## 9. Cost estimate (estimated from measured per-cell costs)

Mean total tokens per cell (v3 training side): SearchQA 2,353, OfficeQA 5,847, LiveMath 2,994, SpreadsheetBench
4,232, ALFWorld 2,786 per call.

- Selection panel of 40 generated items per target per step: generation about 0.1-0.3M GLM tokens (measured 2.3-8k
  per valid item in smoke panels, 6.6k in gen3); cells (parent 2 + each candidate 2) x 40 at about 3.5k tokens per
  generated-item cell (measured, P arm) = about 0.3M per candidate.
- Paired measurement at k = 2 per arm on the similar targets of one changed step: OfficeQA 172 x 4 x 5,847 = 4.0M;
  LiveMath 125 x 4 x 2,994 = 1.5M; SearchQA 400 x 4 x 2,353 = 3.8M. All five similar cells of one chain if every step
  changed: about 17M tokens. At k = 1: about 8.7M. Steps where the Skill did not change cost nothing (reuse).
- Shadow C4' for v3-like funnels: 9 rule-panel pairs per run (or 3 shared panels), plus backward checks that v3
  already runs on real regression panels.

## 10. Recommendation

1. Register v5 transfer **measurement** as paired same-session re-evaluation of parent and child on the similar
   targets' test sets, k = 2, with the local-placement control, a placebo, and the good-instruction baseline; report
   T_sim with its paired CI (MDE about 2 points, estimated). Keep the 12.8 readout only as a secondary, labelled
   drift-exposed number.
2. Do **not** rely on the v3-style generated forward panel as a guard: the pilot found it saturated (92 of 92 cells
   passed for three different texts) and short in 4 of 6 builds. Keep it only as a format check, or replace it with a
   hardened generator (multi-step lookups over long official tables; LiveMath-style items built from research-level
   statements) that must first pass a qualification: on a frozen bank, the parent's pass rate and the share of items
   that the good instruction and the scaffold disagree on must be close to the real benchmark's (real OfficeQA
   training items: 65% failed by both). If it qualifies: target-level, shared per step, about 40 items x 2 runs, from a
   frozen material bank with a throttled client; recorded as unchecked when short.
3. Do not sample the next benchmark's training pool for anything before its own step.
4. To see the machinery run at all: implement the shadow version of section 7 (about 20 lines plus a version bump)
   and run it once on the v3 chains' supported rules, which would exercise 7 of 8 checkable steps.
5. Backward targets (already learned) keep the real 60-item regression panels; they are the only similar-target
   guard with real items that does not break 2.2. Their power is in the 60-item row of 4.4.

## 11. References

- Lopez-Paz, D. and Ranzato, M. (2017). Gradient Episodic Memory for Continual Learning. arXiv:1706.08840 (section 2,
  equations 2-4).
- Wang, X. et al. (2023). TRACE: A Comprehensive Benchmark for Continual Learning in Large Language Models.
  arXiv:2310.06762.
- Zhao, A. et al. (2023). ExpeL: LLM Agents Are Experiential Learners. arXiv:2308.10144 (sections 4.4, 5.4, table 1).
- Wang, Z. et al. (2024). Agent Workflow Memory. arXiv:2409.07429 (table 4).
- Yang, C. et al. (2023). Large Language Models as Optimizers (OPRO). arXiv:2309.03409 (section 5.2.4, table 6).
- Choi et al. (2025). System Prompt Optimization with Meta-Learning (MetaSPO). arXiv:2505.09666.
- Agrawal, L. A. et al. (2025). GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning.
  arXiv:2507.19457.
- Zhang, Q. et al. (2025). Agentic Context Engineering (ACE). arXiv:2510.04618.
- Suzgun, M. et al. (2025). Dynamic Cheatsheet. arXiv:2504.07952.
- Miller, E. (2024). Adding Error Bars to Evals. arXiv:2411.00640 (sections 2.2, 3.1, 4.2, 5; equations 9-10).
- Mirzadeh, I. et al. (2024). GSM-Symbolic. arXiv:2410.05229.
- Zhu, K. et al. (2023). DyVal: Dynamic Evaluation of Large Language Models for Reasoning Tasks. arXiv:2309.17167.
- Project: `docs/handoff/coevo5-registration-v6-20261017.md` (2.2, 5.1, 5.6, 8, 12.8), v2 and v3 deltas,
  `docs/handoff/coevo5_transfer_sim.py`, `docs/handoff/coevo5-v1-report-20261019.md`,
  `docs/handoff/cal1-registration-20261020.md`.

## 12. Artifacts

New machine (`<datatools-login>`), `/data/feasibility/D12/mine/`: `d12_cells.py`,
`cells.jsonl` (14,178 training-side v3 cells), `d12_real.py` / `real.json` (costs, instruction effects, drift, flip
rates, C4' of real rule arms), `pilot_generate.py` with `gen1/` (unthrottled) and `gen2/` (throttled, stopped),
`pilot_generate3.py` with `gen3/` (target-level panels; `each/` holds one JSON per panel, `calls.json`,
`wikipedia.json`), `pilot_solve.py` with `solve2/` (P/E/R on 23 generated OfficeQA-style items; `solve1/` is the
stopped first attempt), `pilot_solve_harm.py` with `solve3/` (H1/H2/placebo), `pilot_real_harm.py` with
`real_harm/` (P vs H1 on the 74-item real OfficeQA training pool), `pilot_solve_live.py` with `solve_live/`
(generated LiveMath-style items), `wiki_diag.py`, `wiki_conc.py`, `material_diag.py`, `probe.py`; logs `*.log`.
Earlier explorer files reused after re-running: `/data/feasibility/D12/{v3_funnel.py,.json, smoke_forward.py,.txt}`.
Old machine: `/data/feasibility-scratch/D12/cal1_extract.py`, `cal1_cells.json`.
Mac: `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D12/`
(`report.md`; `mine/` with `cal1_power.py`, `cal1_power.json`, `tsim_power.py`, `tsim_power.json`, `cal1_cells.json`,
`verdict_cn.txt`; `mine/remote/` with copies of the new-machine scripts, `real.json`, logs, and the `gen1/`, `gen3/`,
`solve2/`, `solve3/`, `real_harm/`, `solve_live/` outputs).
