# Critique of `proposals/stoploss.md`: feasibility, cost and protocol

Critic: stoploss-feasibility. Date: 2026-10-21.

My job was to try to refute the plan, not its prose. I made no model API calls, ran no experiments and used no SSH. I opened no test pool, no C/D block and no sealed artefact. Every number below either carries a source or is my own arithmetic on sourced inputs; my arithmetic is marked **[calc]**.

Abbreviations:
- FS = `docs/handoff/feasibility-20261021/`
- RL = `docs/results-and-lessons.md`
- P = the proposal, `scratchpad/direction/proposals/stoploss.md`
- TC = the five-seed task card (ids-full, 12,681 bytes)
- MDE80 = minimum detectable effect at 80% power and two-sided 5%, which is 2.8·SE

## 0. Verdict: needs_revision

The plan survives in outline:
- the stop list;
- one cheap positive-control experiment on never-sampled SearchQA rows;
- a base cost of about 19M real tokens;
- about 5 hours of compute on one overnight Linux session.

The arm Exp 1 adds (task card plus a rule-sized text, compared with the task card on fresh items) has never been run, so it duplicates nothing.

The numbers and several rules do not hold as written:
- **Power is overstated.** The power figure uses a 2-run SD on 1-run cells.
- **The decision rules are less useful than they look.** They are fixed in advance and well protected against false positives, but a true +3 effect is declared POSITIVE only about 63% of the time even after the extension. The SearchQA extension can also be triggered by LiveMath noise.
- **Three cost statements are wrong:**
  - the v4 "cost" is a GLM ceiling, not a spend;
  - the optional V arm breaks the plan's own 20M-per-run rule and its 38M cap;
  - two plausible paths exceed the 50M budget.
- **The draw mechanism and one sequencing step are infeasible as written.** The plan says "id-level exclusion inside the existing drawing tool", but the tool cannot exclude earlier blocks. The LiveMath packages are frozen in Exp 0 but are written from round-1 failures in Exp 1.
- **Exp 2 leads to a v5 whose acceptance step needs an owner ruling.** That step is fresh-batch acceptance, and the owner's no-validation-set rule may forbid it.
- **The statements about Objective 2 are too strong for SearchQA as a target.** The sealed C/D blocks hold 2,000 rows.

## 1. Item counts and detection power

### 1.1 The SD behind "MDE80 ≈2.4, half-width ≈1.7" (P l.47, l.54) is a 2-run figure applied to 1-run cells

- P takes the per-item SD of 0.243 from E7. That SD is for the cand rule *replacing* the card, compared with the card, at 2 runs per item: FS E7/critic-result.json `refuted_claims` #4, and E7/result.json `evidence` E, "Power (normal approximation, 2 runs…)".
- Exp 1 runs 800 items × **1** run.
- A paired 1-run difference has variance tau² + W_A + W_B, where W is the per-run Bernoulli variance, or half the same-text disagreement rate. The sources:
  - card W ≈0.025–0.027: D1 pilot "same good text twice SD2 0.159"; FS E5/critic-result.json #5 "parent run variance 0.027";
  - tau of a card-sized addition ≤0.191: E5 critic #5;
  - in a noisy session, card same-text disagreement 0.090, so W ≈0.045: FS D5/critic-result.json #4, v3 I-ds s1 rollout.

| Assumption | SD per item, 1 run | SE at 800 | 95% half-width | MDE80 | Holm, 2 tests |
|---|---|---|---|---|---|
| tau from E7's 0.243 net of noise (≈0.08), W 0.025 | 0.238 | 0.84 | 1.65 | 2.36 | 2.59 |
| tau 0.15, W 0.027 | 0.277 | 0.98 | 1.92 | 2.74 | 3.02 |
| tau 0.191 (E5 proxy), W 0.027 | 0.301 | 1.06 | 2.09 | 2.98 | 3.28 |
| noisy session, W 0.045 | 0.335 | 1.18 | 2.32 | 3.32 | 3.65 |

Table: [calc]. All values except the SD column are percentage points.

P's figures sit at the most optimistic row. They should be stated as a range: half-width 1.7–2.1 (up to 2.3) and MDE80 2.4–3.0 (up to 3.3). Exp 0(b), the re-estimate of the instructed-arm SD at K = 1/2, should come before the item count and thresholds are frozen.

### 1.2 What the decision rule actually does (P l.55)

I simulated the rule as written: Holm over SearchQA C and LiveMath C; POSITIVE needs a point estimate ≥ +3 and an adjusted lower bound > 0; NULL needs the SearchQA upper bound < 3 and the LiveMath point < 3; INCONCLUSIVE triggers one 800-row SearchQA extension and is NULL if still not POSITIVE. Inputs were SE at 800 = 0.84–1.18 and LiveMath SE 2.2–2.8 at 154 × 2. [calc, 200k simulated runs]

| True SearchQA effect | Stage-1 POSITIVE | Stage-1 NULL | Extension | Final POSITIVE | Expected Exp 1 cost (real) |
|---|---|---|---|---|---|
| 0 | 0.013–0.018 | 0.64–0.84 | 0.15–0.35 | 0.013–0.018 | 20.4–24.1M |
| +1 | 0.02–0.06 | 0.35–0.59 | 0.39–0.59 | 0.02–0.06 | 23.7–27.5M |
| +2 | 0.13–0.21 | 0.12–0.20 | 0.67–0.68 | 0.14–0.25 | 27.5–28.7M |
| +3 | ≈0.50 | 0.02 | 0.47 | ≈0.63 | 24.8–25.9M |
| +4 | 0.81–0.88 | ≈0 | 0.12–0.19 | 0.92–0.97 | 20.0–22.0M |

- The rule is conservative against false positives, at about 1–2%. That part is confirmed.
- A true +3, which is P's own materiality threshold, ends as NULL about 37% of the time. A true +4 is detected about 92–97% of the time.
- P's text should say plainly that the effective 80% detection threshold is about +3.5 to +4.
- The worst-case Exp 1 spend is base plus extension, 32–33M real or about 64–66M ledger. The 38M cap covers only the first round.

### 1.3 The extension trigger couples two benches, and the pooled readout breaks the one-session rule

- NULL requires *both* SearchQA UB < 3 and LiveMath point < 3. A LiveMath point ≥ 3 has probability 0.09–0.14 at a true 0 [calc]. When that happens, the result is INCONCLUSIVE and P buys 13.5–13.9M of extra SearchQA rows, which cannot resolve LiveMath.
- LiveMath has no extension: all 154 non-meta training items are used, and the 125-item evaluation block is sealed (P l.53; registration v6 §2 table).
- So LiveMath must be decided at stage 1. It is POSITIVE only if its point is ≥ 2.24·SE ≈ 4.9–6.3 [calc]. Its NULL test is weak: at a true +5, P(point < 3) = 0.18–0.24 [calc].
- The pooled 1,600 rows come from two sessions, but the validity rule demands "one session" (P l.55). The rule must pre-specify a session-stratified pooled estimate and a report of between-session heterogeneity.

### 1.4 Fresh-row supply: ample, but the stated mechanism does not exist

- **Supply.** The cached `validation` split has 16,980 rows (`docs/coevolution-v8-public-benchmark-readiness.md` l.7). The tool removes native items and normalized duplicates and has drawn 4,000 rows (blocks A–D of 1,000 each, `docs/current-workflow.md` l.50). About 11k rows remain [calc]. 800, 1,600 or 2,400 more rows are feasible.
- **Mechanism.** P l.77 says "id-level exclusion inside the existing drawing tool". `scripts/make_searchqa_fresh_sample.py` has no such option:
  - its arguments are `--output`, `--native-dir`, `--dataset`, `--revision`, `--count`, `--blocks` and `--seed` (l.114–121);
  - it dedupes only against native items and rows drawn in the same run (l.6, l.65–80).
- The draw is deterministic: seeded order, first `count` eligible rows, contiguous blocks (l.62–99). So `--count 4800 --blocks 6` would make block_f exactly the 800 never-sampled rows. But it would also re-materialize the sealed C/D rows into blocks a–e of a new directory.
- Either option works, but it must be registered:
  - (a) a new script version that reads the A–D manifest ids and writes only the new block;
  - (b) the count-extension, with blocks a–e deleted at once.
- Both must run on the Mac (C/D live there and must not be copied), check overlap by ids only, copy only the new block to Linux, and get owner sign-off as a new block.

### 1.5 Exp 2 and the slim v5

- Exp 2's "C replicates (LB > 0)" at 800 × 1: Exp 1 passes C only at a point ≥ 3, and D1 estimates a winner's curse of 1.34–1.51×. So the true C is probably about 2–2.6 points, and replication power is about 0.65–0.85 [calc]. "C fails → NULL" will discard a real +2.5 effect 15–35% of the time.
- "A − TC ≥ +2 with LB > 0" has about 50% power at a true +2 and about 80% at +3 [calc].
- A v5 with version-level fresh-batch acceptance is feasible **only on SearchQA**, the only bench with fresh rows:
  - a 3-point version-level non-inferiority test needs 642 SearchQA items at 4 runs, more than the 600-item pool (FS D8/critic-result.json R4);
  - OfficeQA, LiveMath, SpreadsheetBench and ALFWorld have 74, 283, 120 and 57 items (registration v6 §2).
- P's Stop #2 ("no new five-bench chain") therefore implies v5 is a SearchQA-only learner, and P should say so.
- If Exp 1 is POSITIVE only on LiveMath, Exp 2's "new LiveMath session" re-runs the same 154 items. That tests session noise, not new items.

### 1.6 Exp 4 rule power and duplication

- 300 × 1 run gives SE ≈1.44–1.73. "≥ +5 with LB > 0" has 50% power at a true +5 [calc]. "≥ +3 with LB > 0" would give 82–92% power at +5.
- The hindsight package must be cross-fitted, or written from a separate writing set. Otherwise it is scored on the items it was written from (winner's curse 1.34–1.51×, FS D1/result.json).
- The port rule can be passed by a pure answer-convention package. On HotpotQA, about 8–12 EM points of the remaining headroom are answer-granularity convention (FS E3/critic-result.json R6). That contradicts P's own rule that form "never counts as something to learn" (P l.55). Exp 4 needs the same F/C split, or content scoring.
- The scaffold arm duplicates E3's NoSkill-vs-card scan (5 candidates, 80 × 2, 3.43M; FS E3/result.json). Dropping it saves a third of the cells.

### 1.7 The Objective 2 power statements (P l.14, l.55, l.68)

- The registered test panels run **1 run per item**: `docs/handoff/coevo5-registration-v6-20261017.md` l.491, "在五个测试集上各测一遍，每题 1 次".
- The quoted "3.7/6.3/7.3/6.5/8.0 at 2 runs" (FS E5/critic-result.json #4) does not describe the registered protocol. At 1 run, FS D5/critic-result.json `missing` #4 gives about 4–5 / 6.6–7.7 / 10–11 / 7–7.7 / 9–10. Holm makes these larger (FS D11 critic).
- **SearchQA as a target is the exception.** The sealed C/D blocks hold 2,000 rows. At 1 run the MDE80 is ≈1.5–1.9, or 2.1 in a noisy session [calc].
- So "since no test panel could show it" (P l.55) is false for SearchQA. P itself keeps C/D sealed "for a future method that works" (l.63).
- The binding constraint for the similarity pair is the **source** side. SearchQA's only similar bench is OfficeQA, which has 74 training items and 22–24-point session swings (FS D12; D11). The accurate statement: OfficeQA → SearchQA transfer could be measured at about 2 points on C/D, if OfficeQA first yields a measurable learning effect and the owner spends the holdout. No other direction can be measured at that level.
- **The host rule (P l.41) cannot be applied as written.** By P's own numbers, SearchQA's substantive headroom is ≈6 points and the test MDE is 3.7, so 6 < 7.4 and SearchQA fails its own rule. Only with C/D (2 × 1.9 = 3.8 ≤ 6) does it qualify. Substantive headroom is not measured for any other bench.

## 2. Costs, recomputed from measured actuals

The anchors are real (receipt) usage per cell:
- SearchQA card-sized: 4,088 (v3 I-ds, FS D6/critic-result.json #5) and 3,995 (FS E5/result.json `cost_estimate`);
- LiveMath: 3,969 (D6 critic #5), or about 4,410 seeded (FS E9/critic-result.json R6);
- a ≤600-byte package adds about 150 tokens per cell [calc, ≈bytes/4].

These reproduce cal-1's real average: 14.0M receipts / 8,800 cells = 1,591 across mixed arms (`docs/handoff/cal1-registration-20261020.md` l.128–131). The brief's "≈3.1k per call" is cal-1's *ledger* average (27,481,897 / 8,800 = 3,123), mixed across arms. P uses the right anchors.

| Item | Cells | Real tokens [calc] | Ledger at 2× |
|---|---|---|---|
| Exp 1 SearchQA, 4 arms + 100 duplicates | 3,300 | 13.5–13.9M | 27–28M |
| Exp 1 LiveMath, rounds 1 + 2 | 1,232 | 4.9–5.4M | 10–11M |
| **Exp 1 base, no V** | 4,532 | **18.4–19.3M** (P: ≈19M) | 37–39M (P cap 38M) |
| optional TC+V | 800 | +3.3M | +6.6M |
| Extension (SearchQA) | 3,300 | 13.5–13.9M | 27–28M |
| Exp 2 (4 arms + proposer) | 3,200 | 14.2–14.5M | 28–29M |
| GLM pivot (Exp 3) | 3,300 | 15–16.5M (P: 13M; see 2.4) | — |
| Exp 4, ≤3 candidates × 900 cells | 2,700 | 3.8–4.9M (2.5–3.2M without the scaffold arm) | — |

### 2.1 "Running v4 is the cost: caps of 11.6–11.7亿 tokens" (P l.21, summary_cn) confuses a ceiling with a spend

- 1,160M / 1,170M is `OVERALL_CEILING`, the overall **GLM-5.3** ceiling that "binds last either way" (`docs/handoff/v4-plans-20261021/G6.v2.md` l.643–647; `G4.v2.md` l.1842–1846).
- G4.v2 states plainly: "Expected usage, not a cap: 2-6M of roles per step (v3: 7.8M for ten steps)" (l.2050–2052).
- v3 spent 139,024,462 deepseek and 7,804,250 GLM ledger tokens (RL l.142).
- A realistic v4 spend is ≈0.19–0.23B tokens [calc]: v3's deepseek, plus the all-in-scope C1 panel at +34M (FS D4/critic-result.json R1), plus 20–60M of GLM roles.
- The stop still stands, but on evidence:
  - thresholds unchanged (spec l.177);
  - a +9.4 card passes C1 only 75.8% of the time at n = 11 (cal-1);
  - rule-on-card effects are 0 to +1.5 (FS D9).
- It does not stand on a 1.16B cost.

### 2.2 "≤50M real ≈⅓ of one v3 run, ≈4% of v4's cap" (P l.42)

- 139M is v3's deepseek *ledger* total. The ledger/receipt ratio was 1.96 in cal-1 and 1.0 in the D8 pilot (FS D8/result.json). So 50M real is ⅓–⅔ of v3's real use.
- Compared with v4's expected spend (≈0.2B), 50M is about ¼. Comparing with a GLM ceiling is meaningless.

Path totals, real tokens, including Exp 0 at ≤1M [calc]:

| Path | Total | Fits ≤50M? |
|---|---|---|
| NULL at stage 1 → Exp 3 + Exp 4 | 23–25M | yes |
| NULL at stage 1 → Exp 3 + Exp 4, with the GLM pivot | 38–42M | yes |
| POSITIVE → Exp 2 | 34–35M | yes |
| INCONCLUSIVE → extension → NULL → GLM pivot + Exp 4 | **52–56M** | no (58–62M with V) |
| INCONCLUSIVE → extension → POSITIVE → Exp 2 + Exp 4 | **51–54M** | no |

Either raise the budget to about 60M or state that the pivot and Exp 4 are alternatives on those paths.

### 2.3 V breaks P's own limits

- With TC+V, Exp 1 needs 21.7–22.6M real and 43–45M ledger.
- That breaks "no run >20M before Exp 1 is positive" (P l.42), if Exp 1 counts as one run, and the 38M cap (l.51).
- V's expected effect is also ≈0: v3 rules on the card measured +0.000/+0.004/+0.015 (FS D9/result.json `evidence` E). It overlaps D1's suggested 2.1M pilot.
- Drop V, or split Exp 1 into two registered runs and raise the cap to about 46M.

### 2.4 GLM pivot ≈13M is unanchored

- The only GLM SearchQA anchor is 19,500 solves for 37.39M tokens, ≈1,917 per solve, with short instructions (RL l.222).
- The 12.7 KB card adds ≈2.9–3.2k prompt tokens. So the pivot is ≈4.5–5k per cell × 3,300 cells ≈ 15–16.5M [calc].
- The BigModel content filter also refuses some SearchQA items in every arm (2 of 100 in FS E7/result.json `evidence`).

### 2.5 Duplicate-based reruns

- "Duplicates within 2 SE, else rerun" uses 100 TC duplicates at 1 run. The 2-SE band is ±4.6 points [calc: 2·√(2·0.027)/√100]. That cannot see the drifts that matter.
- The check also fires about 5% of the time by construction (FS E2/critic-result.json R6), and each firing costs a rerun of about 19M.
- Keep the duplicates as a recorded diagnostic, not a rerun trigger.

## 3. Protocol

1. **Test pools and sealed blocks.** None is read. Exp 3 uses only the opened v1 test results (RL l.173; `docs/project-status.md` §0). The new block is not C/D (P l.52). **Confirmed.**
2. **Draw mechanism.** See §1.4: it needs a new version or the count-extension, on the Mac only, checked by ids only, with owner sign-off and a new block name. Repeated fresh draws (up to 2,400 rows) are development evidence; disclose them, and never reuse a block for a final claim.
3. **The v5 branch is a selection gate on held-out labelled data.**
   - The owner's rule (memory, 10/10) is: never let a development holdout become a selection gate inside the method.
   - Version-level fresh-batch acceptance accepts or rejects Skill versions on new labelled batches.
   - Whether "each batch used once" escapes the rule is the owner's call and must be settled before Exp 2's v5 design. P asks for consent only for the transfer read (l.57).
4. **Exp 2's proposer is undefined.** "The project's proposer" could mean v3's analyst, which D13 audited as defective, or D13's per-code variant, which was never run on the solver (FS D13/critic-result.json). It must be specified and SHA-frozen before Exp 2.
5. **LiveMath sequencing contradicts itself.** Exp 0(c) freezes "one LiveMath content package per cross-fitting fold" at 0 solver tokens (l.49). Exp 1 says round 1 "card ×2" is "for the writer" (l.53).
   - Fix: write the two LiveMath packages after round 1 and SHA-freeze them before round 2.
   - Exp 0 then freezes only SearchQA F, C and the placebos. Archived v3 card cells cover only about 55 non-meta items (FS D9: 62/110 runs), so they cannot replace round 1.
6. **Writer sealing.**
   - Name the writer model and version, the prompt and the exact inputs: the card, the 54 failures and the D9 annotations.
   - Do not give it file-system access to the feasibility outputs. Several pilots evaluated pool items (D1, D2, E5, E7, E8). That matters for the 400-item fallback, which reuses pool items.
   - One placebo cannot match the lengths of both F and C. Name the package it matches, or use one placebo per package.
7. **Format channel.**
   - "Card tag rate ≥99%" covers only TC. Content-form lines on the scaffold raised untagged replies to 21–25% (FS D5/critic-result.json #3), and seed-only tags only 0.986 (E7).
   - Pre-register each arm's tag rate and JSON rate.
   - Pre-register how to read a split verdict, for example "official NULL but JSON-aware positive": content may help and form may hurt; still NULL for the programme.
   - Record the serving regime per time window from the TC arm only (FS E2/critic-result.json `missing` #4) and report a regime-stratified estimate.
8. **What a null F means.** P says an F − TC lower bound > 0 "proves rule-on-card effects are visible" (l.55), but gives no rule for a null F.
   - The CI width already shows the instrument's sensitivity. A null F only says the card already fixes form.
   - Pre-register that C is read on its own CI.
   - Optional: a known-harm short text, such as a "surname only" line, as a sensitivity arm, at about 3.3M.
9. **Stop-list labels.**
   - Stop #7 lists the D3 tracker under "variants measured non-positive". The final D3 result is positive in a redesigned loop: 26/42 vs 16/42, 11 vs 1, p = 0.0063. It is confounded by an added sentence and a new action parser, and ALFWorld has no similar bench (FS D3/critic-result.json #2, #4).
   - The honest label is "confounded and serves neither objective".
10. **Objectives.**
    - The plan parks Objective 1 and advances Objective 2 only if Exp 1 is POSITIVE, and even then only as within-SearchQA evidence.
    - Keep #7, the "measurement-paper framing", was judged by FS D10's critic (R13) to serve neither of the owner's purposes.
    - The owner has to decide whether to change the research goal. The text must say this plainly instead of implying the paper is the default deliverable.

## 4. Duplication

- **Exp 1:** new. No card+rule arm has run on any solver (FS E7/critic-result.json `missing`). E8 prepared a card+rules arm but did not run it (FS E8/result.json). E8's critic sketched a smaller, likely inconclusive version (250–300 × 1, `missing` #1). Exp 1 is the better-powered form of that idea and also subsumes D9's "+3 needs ≈420 × 4 × 2 ≈13M".
- **Exp 0(e), the ≈0.2M semantic audit of the 54 failures:** duplicates E6.
  - E6 already ran a GLM-5.3 3-vote judgement on every distinct official-wrong cal-1 answer (2,767; 75% meaning-correct; 87–93% held up under a human spot check; FS E6/result.json `verdict_cn`).
  - Reuse those labels and drop (e).
- **Exp 0(b):** mostly already computed (E5 critic #5 card-parent proxy; D9 critic SD 0.2255 at 4 runs; E7 critic SD 0.243 at 2 runs). It is free, so keep it as the frozen power basis.
- **Exp 4's scaffold arm:** duplicates E3; drop it (§1.6).
- **GLM pivot:** partly duplicates the 10/13 975-item GLM null (RL l.222), but with different arms (a strong-writer package vs a learned step). It is acceptable only as P frames it, for "an objection beyond Exp 1's reach".
- **TC+V:** duplicates D1's suggested pilot and D9's measured ≈0 (§2.3).

## 5. Time

- At ≈880 cells/h with 6 workers (FS D1/result.json `risks` #10), Exp 1 takes 4,532 cells ≈5.2 h, or 6.1 h with V [calc].
- LiveMath needs a writer pause between rounds.
- The new machine allows at most 6 workers. The shared deepseek route returned HTTP 429 with backoffs of up to 300 s while other pilots ran (FS D12/result.json `pilot.blocked_by`). Budget 8–12 h, run alone, as a Linux background job.
- Follow AGENTS.md: activate the proxy in the same shell and confirm the first real responses before the concurrent release.
- Exp 2 is another single night. Agents only launch and poll sparsely, so the 45-minute agent limit and the 5-hour reset do not bind.
- The 4–6-week calendar is set by owner decisions and one review round, not by compute. **Feasible.**

## 6. Claims I confirmed

- No strong card+rule candidate has been run on fresh items (E7 critic `missing`; E8 `pilot`; E5 critic #5).
- The cost anchors are receipt-based. The ledger ran ≈2× real in cal-1 (27.48M vs 14.0M), so caps at 2× are prudent. Exp 1's base without V comes to 18.4–19.3M real [calc], against P's ≈19M.
- Fresh SearchQA supply is ample: 16,980 validation rows, ≈11k never drawn.
- Exp 1 fits one overnight Linux session (≈5.2 h nominal).
- The plan reads no test pool and no C/D row and changes no frozen artefact.
- v4 excludes fresh-batch acceptance and threshold changes (spec l.177).
- cal-1: the +9.4 card passes C1 75.8% of the time at n = 11.
- v3: 0 accepted rules, 139,024,462 deepseek and 7,804,250 GLM ledger tokens (RL l.142).
- Stop items 3–6 are supported:
  - generated panels saturated (D12 122/122; E1 0/23; E10 critic: 8 validator updates, 0 promotions);
  - E2 ≈292M/523M with 5.5% joint success;
  - E9 critic R1: the veto-only OfficeQA guard spends SearchQA's only similar target;
  - D7 critic: the meta option is the replaced correct answer by benchmark design.
- The Exp 1 rule's false-positive rate is about 1–2% [calc].
- The 400 × 2 fallback has an MDE80 of 2.5–3.5 [calc]; P's 3.1 falls inside that range.
- These citations check out:
  - D14 report l.71/90/96: every ALFWorld failure is a 50-step timeout; GLM 102/114; SpreadsheetBench −0.002;
  - E3: 1.4–1.8k per cell; HotpotQA +1.9;
  - E1: balanced accuracy 0.47–0.55; content 0/23; S_t = S_{t−1} stall;
  - D5 critic: control:3 −0.100 → −0.005;
  - D13: "效果太小…提示词改不了";
  - D2: −1 [−6, +4].

## 7. Corrections (plain Chinese, for the synthesizer)

See the structured field `corrections_cn`; the same items follow.

1. 检测力改成区间。方案用的波动值 0.243 来自 E7 评审，是"单条规则替换任务卡、和任务卡比、每题跑 2 次"的数，可实验 1 每题只跑 1 次。按 10 月 20 日校准实验（cal-1）里任务卡（TC，人写的作答说明）的重跑噪声推算，800 道新题、每题 1 次：95% 区间半宽约 1.7–2.1 分，80% 把握能看出的最小效果约 2.4–3.0 分，两项比较做多重校正后约 2.6–3.3 分。噪声大的时段（像第 3 版正式运行 v3 第 1 步训练轮那样）分别约 2.3、3.3、3.6 分。"约 2.4 分、半宽约 1.7 分"只是最乐观的一端。
2. 判定规则的真实把握写明。判"有效"要求点估计至少 +3 分。只看第一轮：真实 +3 分约一半判有效，真实 +4 分约 81%–88%，真实 +2 分约 12%–21%。算上补测后：真实 +3 分约 63% 判有效、约 37% 被记作"无效"，真实 +4 分约 92%–97%。所以能稳定看出的是约 +4 分以上的效果。规则把假阳性压得很低（约 1%–2%），这点没问题。
3. 补测条件按数据集分开。现在数学题（LiveMath）的点估计只要到 +3 分，就会触发检索问答（SearchQA）补测，约 1,350–1,390 万 token，但补测只加检索问答的题，解决不了数学题。改为：检索问答不确定才补测检索问答。数学题没有更多不含特殊选项的题可补，第一轮就定：点估计约 5–6 分以上且下界大于 0 才算有效，否则记无效。要写明真实 +5 分时，数学题约有两成机会被记成无效。
4. 补测后合并的 1,600 题来自两个时段，和"同一时段"的有效性条件冲突。事先写明：每批各自交错、各自算差值，再按时段分层合并，同时报告两批之间的差异。
5. 把补测算进去后，实验 1 的期望用量约 2,000–2,900 万 token，最坏约 3,300 万（按账本约 6,600 万）。3,800 万的上限只够第一轮，补测要单独登记上限。
6. 新题块的抽法要改写。现有抽题工具没有"排除旧块"的选项。两种办法任选一种并登记：(a) 写一个新版本脚本，读入旧清单里的题号，只输出新块；(b) 用同一种子把抽题数从 4,000 加到 4,800、分 6 块，最后一块就是从没抽过的 800 题，但这会把封存的 C、D 块内容再写出一份，必须当场删掉前 5 块。两种都只在本机（Mac）上跑，只核对题号、不看内容，只把新块拷到开发机，并经负责人签字作为新登记的块。题源够用：原始 validation 划分共 16,980 题，扣掉原生题和已抽的 4,000 题，约还剩 1.1 万题。
7. 可选的 V 组（v3 合并后的规则）建议去掉。加上它，实验 1 真实用量约 2,170–2,260 万，超过方案自己"实验 1 判有效之前，单次运行不超过 2,000 万"的规定；按账本约为真实用量 2 倍算，也超过 3,800 万上限（约需 4,600 万）。v3 的规则加在任务卡上已测得 0 到 +1.5 分（D9 方向），信息量低。
8. "第 4 版（v4，17 个 bug 修复加 7 项提示词改动）要花 11.6–11.7 亿 token"改为："11.6–11.7 亿是方法角色模型 GLM-5.3 的总上限，不是预计花费。v3 在 11.7 亿上限下只用了约 924 万 GLM token 和 1.39 亿 deepseek token。按 v3 的实际用量，加上 v4 新增的面板（约 +3,400 万）和三票裁判，v4 预计约 1.9–2.3 亿 token。"停掉 v4 的理由仍然成立，但理由是门槛不变、学到的规则加在任务卡上只有 0 到 1.5 分，不是成本。
9. "预算约为一次 v3 运行的三分之一、v4 上限的 4%"改为：v3 的 1.39 亿是账本数，按真实用量，5,000 万约为 v3 的三分之一到三分之二；和 v4 比应看预计花费（约 2 亿），约四分之一。另有两条可能的路线超出 5,000 万：①"不确定→补测→无效→GLM 复核＋新数据集预筛"约 5,200–5,600 万（带 V 组约 5,800–6,200 万）；②"不确定→补测→有效→实验 2＋新数据集预筛"约 5,100–5,400 万。要么把总预算提到约 6,000 万，要么写明这两条路线上 GLM 复核和新数据集预筛只能二选一。
10. 数学题写规则包的顺序要改。实验 0 说不花做题费用就把数学题每一折的规则包写好、封存，实验 1 又说第 1 轮"任务卡跑两遍"是给写包模型看的，两处矛盾。改为：实验 1 第 1 轮跑完后，再写数学题的两个规则包，第 2 轮开始前封存哈希。实验 0 只封存检索问答的 F 包（只改作答写法）、C 包（只改内容）和安慰剂文字。
11. 事先写明 F 包没过时怎么解读："F 包相对任务卡的区间下界不大于 0，只说明任务卡已经管住了写法，不能说明量尺看不见规则大小的效果；C 包的结论只看它自己的区间。"可选：加一段已知会伤分的短文字（例如"只写姓"）当灵敏度对照，约 330 万 token。安慰剂要写明是和 F 包还是 C 包等长，或者每个包各配一个。
12. 100 道相同任务卡的重复只记录，不作为重跑条件。100 题时这项检查的允许范围约正负 4.6 分，看不出要紧的漂移，却必然有约 5% 的机会误报，误报一次就要重跑约 1,900 万 token。
13. 每个组都记录答案标签率和 JSON 格式率，不只任务卡组。按"只答一句"和"详细作答"两种服务风格分层报告，风格只按任务卡组的回答判定。事先写明：如果官方评分下 C 包无效、"也认 JSON"的评分下有效，记为"内容可能有用、写法有害"，按方案的规则仍算无效。
14. "目的二按现有题量测不出 3 分以下的效果"要改。登记的测试集每题只做 1 次（登记 l.491）。E5 评审算的 3.7–8.0 分是每题 2 次的数，每题 1 次时更大：检索问答约 4–5 分，办公文档问答（OfficeQA）约 6.6–7.7 分，数学约 10–11 分，表格（SpreadsheetBench）约 7–7.7 分，家务任务（ALFWorld）约 9–10 分。但检索问答作评测目标是例外：封存的 C、D 两块共 2,000 题，每题 1 次时最小可测效果约 1.5–1.9 分。检索问答唯一的相似数据集是办公文档问答，它只有 74 道训练题。准确说法应是："只有'在办公文档问答上进化、在检索问答封存新题上评测'这一种迁移能测到约 2 分，前提是办公文档问答上先学出可测的效果，并经负责人同意动用封存题；其余方向都测不出。"
15. 删去"补测后仍不是有效就记无效，因为任何测试集都看不出"里的后半句：对检索问答这个理由不成立。改为"因为 3 分以下的增量不值得为它重建方法"。
16. "宿主规则"（只在实际余量至少是测试集最小可测效果 2 倍的数据集上主张'学到的胜过任务卡'）现在没法执行。按方案自己的数，检索问答的实际余量约 6 分，测试集最小可测效果 3.7 分，2 倍是 7.4 分，检索问答自己就不合格；其他数据集的实际余量没测过。要写明用哪个测试集（例如检索问答用 C、D 两块：6 分 ≥ 2×1.9，合格），以及余量怎么测。
17. 实验 2 之后的"精简 v5、按版本用新一批题验收"有三处要写清。(a) 只有检索问答有新题可用，其余四个数据集题库太小（D8 评审：3 分的不劣检验要 642 题×4 次，超过检索问答 600 题的题库），所以 v5 只能是检索问答上的学习，不是五数据集链。(b) 每个版本用一批带标签的新题决定收不收，这本身就是方法内部的选择门。负责人定过"开发用的留出题不能变成方法里的选择门"，必须先请负责人明确裁定是否允许。(c) 实验 2 里"项目的提规则模块"要先写明是哪一个（v3 的分析模型，还是 D13 方向的按错误类别逐类提问的新写法）并冻结。
18. 如果实验 1 只在数学题上判有效，实验 2 没有新题可用：154 道不含特殊选项的题已全部用掉，125 道评测块是封存的，"换个时段再跑"只是同一批题重测一遍。要写明这种情况怎么处理。
19. 实验 0 的 (e)"约 20 万 token 的语义审查"和 E6 方向重复。E6 已用 GLM 三票判过校准实验里全部 2,767 个官方判错的答案（包括这 54 道题），直接复用，删去 (e)。
20. 实验 4（新数据集预筛）改三处。(a) 去掉空模板组，E3 方向已测过空模板对任务卡，省三分之一。(b) 事后规则包要交叉拟合（从另一半题的错题写），否则是在写包用的题上评测。(c) "值得移植"的判断不能被纯写法约定通过，例如 HotpotQA 剩下的空间里约 8–12 分是"答案写多长"的标注习惯（E3 评审 R6），所以也要分写法包和内容包，只看内容包。另外，300 题×1 次时，"至少 +5 分且下界大于 0"在真实 +5 分时只有一半把握；改成"至少 +3 分且下界大于 0"，真实 +5 分时约有 82%–92% 把握。
21. GLM 复核的成本"约 1,300 万"缺少依据。唯一的 GLM 检索问答实测是 10/13 的 19,500 次作答用了 3,739 万 token（每次约 1,917，配的是短指令）；换成 12.7 KB 的五份任务卡后每次约 4,500–5,000，3,300 格约 1,500–1,650 万。
22. 停止清单里 D3 方向的"记事小工具"不应写成"测出来不是正向"。在改过的评测循环里它是 26/42 对 16/42 的正向结果，但混进了一句文字指令和新的动作纠错，而且家务任务没有相似数据集。停止理由应写成"结果有混杂，且与两个目的无关"。
23. 对负责人直说：按这个计划，只有实验 1 判有效，两个目的才会推进，而且只是检索问答内部的证据。"测量与负结果论文"本身服务不了负责人的两个目的（D10 评审 R13），走这条路等于改研究目标，需要负责人决定。

## 8. What survives (plain Chinese)

站得住的部分。

一、停止清单的主体成立：
- 不按现有规格实现第 4 版（v4，17 个 bug 修复加 7 项提示词改动），因为它的门槛不变，而学到的规则加在任务卡上只有 0 到 1.5 分。
- 不再开新的五数据集进化链。
- 不用自动生成的题或模型写的检查程序把关，这类题已被测出太简单、分不出好坏。
- 不做迁移矩阵（E2 方向，约 2.9 亿到 5.2 亿 token，成功机会约 5.5%）。
- 不用相似数据集的训练题做“只否决”的检查（E9 方向）。这会用掉检索问答唯一的相似数据集，等于变相的验证集。
- 不去“学”数学题里那个特殊选项。按基准的设计，它就是被替换掉的正确答案，要不要写进任务卡由负责人定。

二、核心实验成立，而且不重复：在 800 道从没用过的检索问答（SearchQA）新题上，比较“任务卡（TC，人写的作答说明）”和“任务卡＋强模型看着训练错题事后写的规则包”，同时加长度相当的无关文字作安慰剂对照。这种“任务卡＋规则”的比较以前从没做过。
- 成本：基础用量约 1,840 万到 1,930 万真实 token，和方案说的约 1,900 万一致；所用的每题单价是真实用量，按账本约 2 倍设上限是谨慎的。
- 时间：一个夜间在开发机后台约 5 小时能跑完，遇到限流约 8 到 12 小时。
- 题源：新题够用，原始题源扣掉已用的题后约还剩 1.1 万题。

三、判定规则事先写死，误判“有效”的机会很低（约 1% 到 2%）。整个计划不读任何测试集，不读封存的 C、D 两块新题，也不改动已冻结的历史结果。

需要改的地方：
- 检测力写成区间；
- 说清判定规则的真实把握（能稳定看出的是约 +4 分以上的效果）；
- 补测按数据集分开，合并时按时段分层；
- 去掉 V 组，或者提高上限；
- 改正 v4 的成本和预算比较；
- 写明新题块的具体抽法；
- 调整数学题写规则包的顺序；
- v5 按版本用新题验收的做法，先请负责人裁定是否算验证集；
- “目的二测不出来”的说法放宽：检索问答作评测目标时，用封存的 2,000 题能看到约 2 分的效果。
