# D1 — Version-level acceptance on fresh batches: feasibility report

Explorer D1, round r3 (2026-10-21 04:40–05:40 HKT). Supersedes `report-attempt1-20261020-1918.md` in this folder (written
when cal-1 was 82% complete). Every number below is tagged **[M]** measured (arithmetic on cell records), **[E]** estimated
(simulation or formula on measured inputs, assumptions stated) or **[C]** claim/design proposal. No test or holdout pool
was read or listed (v3 walks touched only `train/`, `screen/`, `confirm/` cells; selftest cells were not opened); no
repository file was modified; no credential was printed. No paid call was made in this round: the fresh-batch pilot
analysed here was run by the previous D1 round (§10).

## 0. Verdict

Version-level acceptance on fresh batches is **statistically sound, simpler than the v3 gate, cheaper per decision, and more
sensitive to broad effects** — but it is not a way around the noise and it does not create effects.

- **Noise [M]** (cal-1, 200 SearchQA training items × 4 runs): the per-item paired-difference SD is **0.222 at 2 runs and
  0.144 at 4 runs for the same text re-run** (pure noise), but **0.344 at 2 runs and 0.310 at 4 runs for the real +0.094
  effect** of the task-card seeds. Every text change on the empty scaffold, including irrelevant placebo sentences, adds a
  between-item spread τ = 0.12–0.28 that extra runs cannot remove (0.06–0.14 for two placebos on the good instruction).
- **Items needed [E]** (one-sided 95% item-bootstrap lower bound > 0 with 80% power, simulated on the cal-1 items):
  at 2 runs **+0.05 needs 213–274 items, +0.03 needs 487–733, +0.02 needs 1,016–1,637**; at 4 runs 156–209, 315–535 and
  593–1,127. Type-I error measured 0.035–0.057 (nominal 0.05).
- **What the pools allow [E]**: SearchQA (600) certifies ≈ +0.04–0.05, LiveMath (283) ≈ +0.05–0.06; OfficeQA (74),
  SpreadsheetBench (91 qualified) and ALFWorld (57) only ≈ +0.10–0.15. No design certifies +0.02–0.03 except on SearchQA
  with ≥ 1,000 items, which the pool does not have.
- **Replays [M]**: on cal-1 it accepts both seed texts and rejects the duplicate parent, the three rule-shaped texts and
  three of four placebos; **one placebo (+0.036, lower bound +0.011) is accepted on the empty scaffold**. On a fresh batch
  of 130 never-used items (pilot) it accepts the task-card seed (+0.162) and rejects the duplicate and both placebos on the
  good-instruction parent. Replayed on v3's own screen data, **D1 would have accepted one rule v3 rejected** (E-ds s1-r2,
  an answer-format rule: +0.081 on its 99-item check half, one-sided p = 0.003, while v3 rejected it for a 1/4-item gain
  on its 6 trigger items) and **none of the 7 rule arms of the good-instruction chain** (−0.107 to +0.005).
- **Cost [M/E]**: one D1 acceptance round costs 1.5M (empty-scaffold chain) / 4.7M (seeded chain) receipt tokens on
  SearchQA vs 4.5M / 7.4M measured for the v3 screen+confirm; summed over the five stages 12.0M vs 14.0M and 34.1M vs
  60.2M for the bare two-arm round (v3's figures include its own four placebo arms per screened rule). Controls cost
  extra: a parent duplicate and one placebo arm in the chain's first round give 13.5M / 38.9M; in every stage's first
  round 19.9M / 58.7M, i.e. more than v3 on the empty-scaffold chain. A futility look at half the batch saves 27–46% of
  a round on null or harmful packages for ≤ 1 point of power.
- **No fixed validation set [C]**: the acceptance batch is training-side, re-drawn every step, never shown to a model role,
  and returned to the pool afterwards — the same category as v3's check half (registration §2.2, owner decision of 10/16).
  It does use labelled training items to decide, exactly as v3 did.

Feasibility: **high** as a mechanism (fewer moving parts than v3, validated by three replays and a completed fresh-batch
pilot); its expected yield on the good-instruction chain is low, because no measured rule there has a version-level effect.

## 1. Data and provenance

| source | where | content | used for |
|---|---|---|---|
| cal-1 main round | old machine `/data/coevo5-20261020-cal1/cal1/searchqa/attempt-{1,2}/cells` | 11 arms × 200 items × 4 runs = **8,800 verdict cells** (7,205 + 1,611 records; 16 records without verdict overridden by attempt 2); 15 unknown verdicts (0.17%), 8 truncated sends | noise, heterogeneity, power, replay |
| D1 fresh-batch pilot | new machine `/data/feasibility/D1/v2/pilot/d1v2pilot/searchqa` (unit status `complete`) | 6 arms × 130 fresh items × 2 runs = **1,560 cells**, 0 unknown, 0 truncation, 0 non-200 sends | fresh-batch replication |
| v3 run, learning units | new machine `/data/coevo5-20261019-v3-run/{E-ds,I-ds}/s1..s5/{train,screen,confirm}` | 14,178 cell records | costs, per-bench noise, replay of v3 rules |
| v3 halves and rules | `…/s*/prepare/unit.json` (result.halves, result.rules) | proposal/check halves, evidence and trigger items | out-of-sample replay |
| v3 ledger | `…/shared/ledger/events.jsonl` (settle events) | per-step deepseek and GLM charges | costs |

Checks [M]: cal-1 per-arm totals reproduce the registered `analysis.json` (parent:A 543/4, parent:B 549/4, ids-full
309/2, seed-only 307/2, cand 261/2, seed-rule3 519/4, control:1 515/4); the registered noise floor (mean +0.0075, sd
0.1438, 22/18/160) and positive effect (+0.0938, 48/13/139) are reproduced exactly. The pilot arms are the cal-1 texts by
two hash conventions (arm-text sha asserted in the pilot script; cell-level `skill_sha256` E = parent:A `cc516459810a`,
S = seed-only `dc9beac7eac4`, E+P3 = control:3 `c18e4a140904`). The pilot's 130 items are disjoint from cal-1's 200 and
from all 231 SearchQA items any v3 non-test unit touched (train 200 ∪ regression 60); they were drawn by `data.pool`,
which loads only the historical train and val parts. Cal-1's run-index labels carry no dispatch-time pairing (median gap
between the two arms' run r of one item 1.1 h, the same for matched and unmatched runs), so all run subsets are
exchangeable.

## 2. The step flow [C]

Vocabulary. A **version** is a complete Skill text. The **parent** S_t is the current version; the **candidate** S'_t is
S_t plus the whole package of rules that survive the step's preparation, merged as they would be deployed (one text, one
hash). **Flagged** items are items that served as proposal material in any earlier step of this chain. k = runs per
(arm, item); n_a = acceptance-batch size.

**Inputs of step t on bench b**: S_t; the bench's training pool P_b (historical train + val, SpreadsheetBench qualified
part — registration §2.2, unchanged); the chain's flag table F_b and usage counter U_b; registered (n_p, n_a, k, n_min,
δ_use, α) for b (table below); the earlier benches' pools for regression panels; seed and step tag.

1. **Proposal batch.** Draw B_p (n_p items, seeded order) from P_b \ F_b while |P_b \ F_b| ≥ n_p + n_a, else from F_b
   (re-using flagged items for learning is allowed). Flag B_p entirely: F_b ← F_b ∪ B_p.
2. **Learn (as v4).** Parent on B_p × k_p runs → examiner revision and per-item diagnosis on B_p only → analyst proposals →
   preparation (consistency, leakage, length) → selftest on evidence items (⊂ B_p). Nothing in this step reads any other
   item. If no rule survives, the step ends with S_{t+1} = S_t and no acceptance round ("empty package").
3. **Freeze the candidate.** Merge every surviving rule (registered order, 20 KB cap applied before the round). The tested
   text is the deployed text: no per-rule arms, no composite round, no pruning after the round.
4. **Acceptance batch.** Draw B_a (n_a items) from P_b \ F_b, least-used first (U_b), seeded order. If
   |P_b \ F_b| < n_min the step is recorded as `underpowered` with its pre-registered power and makes no decision.
5. **Acceptance round** (one round, seeded interleaved dispatch, same route and settings): parent and candidate on B_a × k;
   in the chain's first round also a parent duplicate and one length-matched placebo arm (the pipeline's own null check
   and the placebo reference of §9; every round re-estimates re-run noise from each arm's own k ≥ 2 runs); regression panels of
   every earlier bench (60 items each, redrawn per step; parent 2 runs, candidate 1 run as in v3); forward/similar-target
   panels when D6 supplies them. Parent cells are never reused from another round (§6).
6. **Decision** (pre-registered, one per step):
   - A1 benefit: d_i = ȳ_i(S'_t) − ȳ_i(S_t) over B_a (items no arm answered are excluded, as v3 §3); candidate unknown =
     fail, parent unknown = pass; one-sided 95% percentile item bootstrap (items resampled, runs nested; B = 10,000, seeded)
     **LB₉₅(d̄) > 0 and d̄ ≥ δ_use = 0.02**.
   - A2 no regression: per earlier bench LB₉₅(d̄_b) > −m_b (margins from D8) and ≤ 2 extra format violations (v3 C3).
   - A3 similar targets: no-worse readout on forward panels, descriptive until D6 validates them.
   - Infrastructure: the v3 pause rules (unknown share > 10% in any arm) apply unchanged.
   - Optional futility look: after n_a/2 items, stop and reject if d̄ ≤ 0 (§7.3).
   Accept ⇒ S_{t+1} = S'_t. Reject ⇒ S_{t+1} = S_t; the package and its estimate are archived.
7. **Return to the pool.** B_a stays unflagged (U_b += 1): it may be acceptance material again and proposal material later
   (then it is flagged). B_p stays flagged: learning material only, never acceptance material again. No model role ever
   sees B_a's outcomes; the analyst may at most be told "accepted/rejected" (one bit per step, the Ladder principle).
8. **Outputs**: the version record (texts, hashes), the decision record (n, k, d̄, CI, LB, up/down/tie, unknowns,
   truncations, the duplicate's null when present), F_b, U_b, per-rule descriptive attribution (§2.1), then the test
   evaluation when the Skill changed (unchanged from v3).

**Steps per stage and pool accounting.** n_a is fixed per bench. B_p is drawn from never-used items while the unflagged
pool holds n_p + n_a, afterwards from flagged items (the analyst then re-learns from items it has seen, under the new
parent); the unflagged pool therefore never falls below n_a, and B_a may be the same items in several steps. Each such
re-use is recorded. It is safe as long as no model role sees B_a's outcomes — the candidates are then generated
independently of B_a, so each decision keeps its 5% false-acceptance rate; feeding back at most the accept/reject bit
bounds the leak to one bit per decision (the Ladder argument of Blum & Hardt 2015) — and a registered maximum of steps per
stage (proposed 3) bounds the number of decisions taken on one batch.

| bench | pool | n_p | n_a × k | unflagged after the fresh-proposal steps | steps with fresh proposal material |
|---|---|---|---|---|---|
| SearchQA | 600 | 100 | 300 × 2 (or 500 × 1 at step 1) | 500 / 400 / 300 | 3 |
| LiveMath | 283 | 50 | 183 × 2 (233 × 2 if one step only) | 233 / 183 | 2 |
| OfficeQA | 74 | 37 | 37 × 4 | 37 | 1 |
| SpreadsheetBench | 91 | 45 | 46 × 2 | 46 | 1 |
| ALFWorld | 57 | 28 | 29 × 2 | 29 | 1 |

(n_p = the v3 proposal-half size, which supplied the analyst's 16–40 shown failures.) Why "never proposed on" and not
merely "not proposed on in this step": a candidate refines its parent's rule lineage, whose earlier rules were written from
earlier proposal batches; scoring the refinement on those items measures the lineage in-sample. The relaxed rule would let
later steps use earlier proposal items as acceptance material (more distinct acceptance items on the small pools), at the
cost of that bias; if adopted it must be registered and disclosed.

### 2.1 Attribution (only after acceptance; descriptive) [C]

- **Free**: the v4 applicability judge marks, from item texts only (no labels), which B_a items each rule applies to; report
  d̄ on applicable vs other items per rule with bootstrap CIs. §5.4 shows why this matters: the one rule v3 passed at screen
  fixed its own 8 evidence items (+0.266) but cost −0.047 [−0.094, −0.003] on the other 186 items [M].
- **Leave-one-out arms** S'_t − r_j, run in the *next* step's acceptance round on its fresh batch (unbiased for each rule's
  marginal contribution inside the accepted version), only for packages of ≤ 3 rules or when a subgroup estimate is
  negative. Cost m × n_a × k cells (§7). A rule's share of a +0.05 package (~0.01–0.02) is not detectable at any feasible
  n (§4), so these are point estimates with CIs, never decisions.
- **Removal** of a rule that looks harmful is itself a new candidate version, decided by the same rule on a later fresh
  batch. No version is ever edited on the batch that judged it.

## 3. Measured noise and heterogeneity

### 3.1 cal-1: per-item paired-difference SD at k runs [M]

Direct SD = SD over the 200 items of d_i computed from k-run subsets (average variance over all subset pairs; item
bootstrap 95% CI). τ = SD of the true per-item effect from the decomposition Var(d^(4)) = τ² + W/4, W = summed per-run
Bernoulli variance of the two arms (unbiased per item). All versus parent:A unless stated.

| comparison | mean [95% CI] | up/down/tie | τ | SD₁ | SD₂ | SD₄ |
|---|---|---|---|---|---|---|
| parent:B − parent:A (same text) | +0.0075 [−0.014, +0.026] | 22/18/160 | 0 (τ² −0.008 [−0.016, +0.001]) | 0.326 [0.287, 0.362] | **0.222** [0.191, 0.251] | **0.144** [0.114, 0.173] |
| ids-full (five task-card seeds) | +0.094 [+0.053, +0.136] | 48/13/139 | 0.273 [0.217, 0.320] | 0.402 [0.353, 0.442] | **0.344** [0.297, 0.388] | **0.310** [0.263, 0.355] |
| ids-full − parent:B | +0.086 [+0.045, +0.130] | 46/14/140 | 0.279 | 0.397 | 0.343 | 0.313 |
| seed-only (SearchQA card) | +0.089 [+0.051, +0.126] | 47/10/143 | 0.226 | 0.375 | 0.309 | 0.271 |
| cand (v3 E-ds s1-r1) | −0.026 [−0.073, +0.020] | 37/44/119 | 0.271 | 0.463 | 0.380 | 0.330 |
| seed-rule | +0.004 [−0.031, +0.040] | 26/24/150 | 0.188 | 0.382 | 0.301 | 0.251 |
| seed-rule3 | −0.030 [−0.068, +0.006] | 26/38/136 | 0.184 | 0.398 | 0.310 | 0.255 |
| control:1 / :2 / :3 / :4 (placebos) | −0.035 / +0.036 / −0.098 / +0.003 | 20/33, 39/16, 16/58, 28/21 | 0.119 / 0.146 / 0.203 / 0.154 | 0.35 / 0.35 / 0.43 / 0.35 | 0.262 / 0.266 / 0.334 / 0.270 | 0.204 / 0.215 / 0.277 / 0.220 |
| seed-only − ids-full (two good texts) | −0.005 [−0.036, +0.026] | 15/19/166 | 0.193 | 0.303 | 0.254 | 0.226 |

Reading: under pure re-run noise the SD falls as 1/√k (0.33 → 0.22 → 0.14); under any text change it hardly falls
(seeds 0.40 → 0.34 → 0.31) because most of the variance is between items — the text fixes some items completely and breaks
others. Even an irrelevant sentence produces τ = 0.12–0.20, and two good instructions that differ only by other benches'
task cards produce τ = 0.19. **Items, not runs, buy power for real effects.**

### 3.2 Fresh batch (pilot, 130 never-used items, 2 runs) [M]

| comparison | mean [95% CI] | up/down/tie | τ | SD₁ | SD₂ |
|---|---|---|---|---|---|
| S − E (SearchQA task card vs empty scaffold) | **+0.162** [+0.104, +0.223] | 28/2/100 | 0.294 | 0.404 | 0.353 [0.289, 0.398] |
| S:dup − S (same good instruction) | +0.004 [−0.023, +0.031] | 6/4/120 | 0 | 0.264 | **0.159** [0.098, 0.214] |
| S+P2 − S (hex-colour placebo on the good instruction) | 0.000 [−0.035, +0.035] | 7/7/116 | 0.064 | 0.271 | 0.197 [0.138, 0.248] |
| S+P3 − S (recipe placebo on the good instruction) | −0.023 [−0.062, +0.015] | 7/10/113 | 0.138 | 0.284 | 0.223 [0.159, 0.283] |
| E+P3 − E (recipe placebo on the empty scaffold) | **−0.081** [−0.142, −0.023] | 7/24/99 | 0.267 | 0.418 | 0.351 [0.283, 0.415] |

The heterogeneity measured on the cal-1 items transfers to fresh items (seeds SD₂ 0.353 vs 0.309–0.344; the recipe
placebo replicates its cal-1 harm, −0.081 vs −0.098). Two new facts: the good-instruction parent is quieter (same-text
SD₂ 0.159 vs 0.222 for the scaffold; 10 of 130 items discordant (7.7%) vs 15.3% at 2 runs for the scaffold in cal-1) and moves less under placebos (|mean| ≤ 0.023,
τ 0.06–0.14). The difference-in-differences for the recipe placebo, (S+P3 − S) − (E+P3 − E) = +0.058 [−0.012, +0.127],
is suggestive, not established (2 placebos × 130 items).

### 3.3 Other benchmarks (v3 training rollouts, parent, 2 runs) [M]

Within-item noise of the parent, W_arm = flip rate / 2: SearchQA 0.018 (E) / 0.045 (I); OfficeQA 0.041 / 0.047 (74 items,
pass 0.20 / 0.25, 70–76% of items fail every run); LiveMath 0.065 / 0.080 (100 items, pass 0.375 / 0.33);
ALFWorld 0.070 / 0.070 (57 items, pass 0.40 / 0.51); SpreadsheetBench ran 1 run (91 items, pass 0.51 / 0.52), noise
unknown. Heterogeneity τ was never measured outside SearchQA (no positive control); §4.3 assumes τ ∈ [0, 0.27].

## 4. Items needed

### 4.1 Analytic bounds [E]

n = ((z₀.₉₅ + z₀.₈₀) · SD_k / δ)² with the measured SDs. The pure-noise SD is the optimistic bound (an effect spread
evenly over items, which binary items cannot deliver); the seeds' SD the pessimistic one.

| SD used | k | n₈₀ for δ = 0.02 / 0.03 / 0.05 | n₅₀ (expected LB = 0) |
|---|---|---|---|
| same text, empty scaffold | 2 | 762 / 339 / 122 | 333 / 148 / 53 |
| same text, empty scaffold | 4 | 320 / 142 / 51 | 140 / 62 / 22 |
| real effect (seeds) | 2 | 1,826 / 811 / 292 | 799 / 355 / 128 |
| real effect (seeds) | 4 | 1,490 / 662 / 238 | 652 / 290 / 104 |
| same text, good instruction (pilot) | 2 | 389 / 173 / 62 | 170 / 76 / 27 |
| placebo churn on the good instruction (pilot) | 2 | 771 / 343 / 123 | 337 / 150 / 54 |

### 4.2 Bootstrap over items [E]

Fully empirical simulation (`r3/power_sim.py`): a simulated acceptance batch draws n items with replacement from the 200
cal-1 items; each arm's k runs are drawn without replacement from that item's 4 measured runs (a random k-subset of iid runs
is distributed as k fresh runs); a fraction w = δ/0.090 of drawn items are "effect items" (candidate = ids-full runs,
parent = a random parent measurement). The other items are either **mix** — the two identical-text parent measurements in
random order (noise only) — or **mixchurn** — a random rule-shaped/placebo arm vs a random parent, sign-flipped at random
(the churn of a typical rule text, mean 0). Decision = one-sided 95% percentile item bootstrap LB > 0 (1,000 resamples,
drawn as exact multinomial counts over the 2k+1 possible per-item differences); 2,000 batches per point; n grid 50–4,000.

| δ | model | n₈₀, k = 1 | n₈₀, k = 2 | n₈₀, k = 4 | power at n = 300, k = 2 | power at n = 200, k = 4 |
|---|---|---|---|---|---|---|
| 0 (type I) | both | 0.035–0.056 | 0.042–0.057 | 0.038–0.057 | 0.05 | 0.05 |
| 0.02 | mix / mixchurn | 1,895 / 2,327 | **1,016 / 1,637** | **593 / 1,127** | 0.36 / 0.28 | 0.41 / 0.28 |
| 0.03 | mix / mixchurn | 881 / 1,116 | **487 / 733** | **315 / 535** | 0.60 / 0.49 | 0.62 / 0.46 |
| 0.05 | mix / mixchurn | 346 / 406 | **213 / 274** | **156 / 209** | 0.89 / 0.84 | 0.88 / 0.78 |
| 0.09 (≈ seeds) | mix / mixchurn | 123 / 127 | 91 / 89 | 71 / 74 | 1.00 / 1.00 | 0.99 / 1.00 |

- The simulated n₈₀ lie between the analytic bounds; the percentile bootstrap and the normal approximation agree within
  0.02 in power at k ≥ 2 (0.04–0.08 at k = 1 with small n).
- **Per solver call, one run on more items is the most efficient** (cells per arm for 80% power at δ = 0.05: 346–406 at k = 1,
  426–548 at k = 2, 624–836 at k = 4). Use k = 1 where the pool is large, k = 2–4 only where items run out. On SearchQA,
  500 items × 1 run (power 0.88–0.91 at δ = 0.05) matches 300 × 2 (0.84–0.89) with 17% fewer cells.
- **Winner's curse**: the acceptance-time estimate of an accepted version is inflated when power is low — E[d̄ | accept]/δ
  = 1.34–1.51 at δ = 0.03, n = 300, k = 2, and 1.78–2.06 at δ = 0.02. Acceptance estimates are selection estimates; effect
  claims must come from the test evaluation (or a later fresh batch).

### 4.3 What each pool can certify [E]

Smallest effect with 80% power, δ₈₀ = 2.487 · √(τ² + W_pair/k) / √n_a, W_pair = 2 × the I-chain W_arm of §3.3
(SpreadsheetBench assumed 0.14):

| bench | n_a, k | τ = 0 | τ = 0.15 | τ = 0.20 | τ = 0.27 | whole pool at k = 4 (impossible under the strict rule), τ = 0.20 |
|---|---|---|---|---|---|---|
| SearchQA | 300 × 2 | 0.030 | 0.037 | 0.042 | 0.049 | 0.025 |
| LiveMath | 233 × 2 (183 × 2: × 1.13) | 0.046 | 0.052 | 0.056 | 0.064 | 0.042 |
| OfficeQA | 37 × 4 | 0.063 | 0.088 | 0.103 | 0.127 | 0.073 |
| SpreadsheetBench | 46 × 2 | 0.097 | 0.112 | 0.122 | 0.139 | 0.071 |
| ALFWorld | 29 × 2 | 0.122 | 0.141 | 0.153 | 0.175 | 0.090 |

D1 is honest but nearly toothless on the three small pools: it can only accept packages worth ≥ 10–15 points there.
The v3 gate is not better: cal-1 measured its C1 passage at the registered 11 trigger items as 75.8% for a +9-point
intervention and ~0% for anything rule-sized (registration cal-1, A1).

## 5. Replays of the D1 rule on measured arms

### 5.1 cal-1 (200 items; candidate vs parent:A) [M]

| arm | k = 4: mean [95% CI] | LB₉₅ | up/down | D1 at k = 4 | share of the 36 two-run subset pairs that accept |
|---|---|---|---|---|---|
| parent:B (same text) | +0.0075 [−0.013, +0.028] | −0.009 | 22/18 | reject | 13.9% (0% with parent:B as parent) |
| ids-full | +0.094 [+0.053, +0.136] | +0.058 | 48/13 | **accept** | 100% |
| seed-only | +0.089 [+0.053, +0.128] | +0.058 | 47/10 | **accept** | 100% |
| seed-rule | +0.004 [−0.033, +0.038] | −0.026 | 26/24 | reject | 0% |
| seed-rule3 | −0.030 [−0.065, +0.004] | −0.060 | 26/38 | reject | 0% |
| cand (passed the v3 screen) | −0.026 [−0.073, +0.019] | −0.064 | 37/44 | reject | 0% |
| control:1 / :3 / :4 | −0.035 / −0.098 / +0.003 | < 0 | | reject | 0% |
| **control:2 (hex-colour placebo)** | **+0.036 [+0.006, +0.066]** | **+0.011** | 39/16 | **accept** | 61% (47% vs parent:B) |

Caveat: cal-1's items are the v3 E-ds stage-1 training items, so they are *in-sample* for cand (it was written from
their proposal half) — and cand still loses at the version level. An irrelevant sentence clears the bound on the empty
scaffold; whether it would on a good-instruction parent is the open question §5.2 starts to answer.

### 5.2 Fresh batch (pilot; 130 never-used items, k = 2) [M]

| candidate vs parent | mean | LB₉₅ | up/down | D1 |
|---|---|---|---|---|
| S vs E (task card vs empty scaffold) | +0.162 | +0.112 | 28/2 | **accept** |
| S:dup vs S (same good text) | +0.004 | −0.019 | 6/4 | reject (correct) |
| S+P2 vs S (placebo on the good text) | 0.000 | −0.027 | 7/7 | reject |
| S+P3 vs S (placebo on the good text) | −0.023 | −0.054 | 7/10 | reject |
| E+P3 vs E (placebo on the scaffold) | −0.081 | −0.131 | 7/24 | reject |

### 5.3 v3's own gate data, rule by rule [M]

Per screened rule arm: per-item mean over its runs minus the parent's in the same round (focal bench only). The **check
half** was never shown to the analyst, so it is out-of-sample for the rule (its trigger items lie inside it).
One-sided bootstrap p (20,000 resamples); Bonferroni threshold over the 17 replayed arms 0.0029.

| chain/stage | round | rule | all focal items: n, mean (net items) | check half: n, mean, p₁ | check half minus triggers |
|---|---|---|---|---|---|
| E-ds s1 SearchQA | screen | s1-r1 | 200, +0.004 (+0.75) | 99, +0.048, 0.087 | 93, +0.032 |
| E-ds s1 | confirm | s1-r1 | 200, −0.013 (−2.5) | 99, −0.010, 0.63 | 93, −0.032 |
| E-ds s1 | screen | **s1-r2** | 200, **+0.055 (+11.0)**, LB +0.024 | 99, **+0.081, 0.0034**, LB +0.030, 19 up/9 down | 93, +0.083 |
| E-ds s1 | screen | s1-r3 / s1-r4 | +0.001 / +0.011 | +0.023 / +0.018 (p 0.26 / 0.30) | |
| E-ds s2 OfficeQA | screen | s2-r2 / s2-r3 | +0.024 / −0.003 | 37, +0.020 / −0.020 | |
| E-ds s3 LiveMath | screen | s3-r2 / s3-r3 | +0.028 / **+0.048** | 49, +0.025 / **−0.005** | |
| E-ds s4 Sheet | screen | s4-r4 | +0.028 | 45, +0.033 (p 0.32) | |
| I-ds s1 SearchQA | screen | s1-r1 / r2 / r4 | +0.000 / +0.004 / +0.015 | 100, −0.030 / −0.008 / +0.005 | |
| I-ds s3 LiveMath | screen | s3-r2 | −0.022 | 49, +0.005 | |
| I-ds s4 Sheet | screen / confirm | s4-r2 | −0.033 / +0.028 | 45, −0.044 / −0.011 | |
| I-ds s5 ALFWorld | screen | s5-r1 | **−0.140** | 28, −0.107 | |

Readings: (1) v3 rejected s1-r2 ("put exactly one short answer inside <answer>…") because C1 found a 1/4-item gain on its
6 trigger items, while its effect lay outside them (C2 recorded +41/4 items on the rest); a version-level rule would have
accepted it at α = 0.05 (borderline under Bonferroni over 17, p 0.0034 vs 0.0029). It is a format rule on the empty
scaffold, i.e. it re-learns task-card content. (2) The one rule v3 passed at screen (s1-r1) regresses on its check half from +0.048 (screen)
to −0.010 (confirm) to −0.020 (cal-1, §5.4): the winner's curse in miniature. (3) E-ds s3-r3's +0.048 lives
entirely in its proposal half (check half −0.005): in-sample optimism that a fresh batch removes. (4) **On the
good-instruction chain no rule shows a version-level effect** (7 arms, check-half means −0.107 to +0.005): D1 would not
have changed I-ds's outcome.

### 5.4 One rule, three subgroups [M]

cal-1, the v3 E-ds s1-r1 text ("cand") minus the mean of the two parent measurements, 4 runs, split by the v3 halves of the
same 200 items:

| items | n | mean [95% CI] | up/down |
|---|---|---|---|
| its 8 evidence items (selftest material) | 8 | **+0.266** [+0.063, +0.500] | 4/0 |
| its 6 trigger items (v3 C1 panel) | 6 | +0.104 [−0.042, +0.292] | 2/1 |
| the other 186 items | 186 | **−0.047** [−0.094, −0.003] | 37/46 |
| proposal half / check half | 101 / 99 | −0.040 / −0.020 | 20/25, 23/22 |
| all 200 | 200 | −0.030 [−0.074, +0.013] | 43/47 |

The rule does what it was written for and costs more elsewhere: exactly the case a per-rule gate on its own trigger items
can pass (v3 screen) and a version-level rule rejects.

## 6. Drift of the same text across days [M] — a design constraint

Same 200 items, same texts: v3 stage-1 training rollouts (2026-10-19, 2 runs) vs cal-1 (2026-10-20, 4 runs).

| quantity | 10/19 | 10/20 | difference [95% CI] |
|---|---|---|---|
| empty scaffold pass rate | 0.743 | 0.683 | **−0.060 [−0.098, −0.021]** (15 up / 48 down) |
| five-seed Skill pass rate | 0.775 | 0.773 | −0.003 [−0.021, +0.016] |
| seeds − scaffold within the day | **+0.033 [−0.003, +0.068]** | **+0.090 [+0.047, +0.130]** | |
| within-arm run disagreement (scaffold / seeds) | 0.035 / 0.09 | 0.11–0.12 / 0.05 | |

The size of a "known" effect and the noise level both depend on the day, through the parent. Consequences: the two arms
must be measured in one interleaved round; parent cells are never reused across rounds; every round re-estimates the
re-run noise from the arms' own repeated runs (k ≥ 2) and re-checks the power statement against it; a parent duplicate
in the chain's first round (and in any round run at k = 1) tests the pipeline's false-acceptance rate directly.

## 7. Cost per step

### 7.1 v3 gate, measured [M] vs D1 acceptance round, estimated [E]

v3 = solver receipt tokens (prompt + completion) of the screen + confirm cells. D1 = 2 arms × n_a × k focal cells (design of
§2) + 180 regression cells per earlier bench (v3 schedule), priced at the per-cell receipts measured for the same chain and
bench in v3 (focal parent/train cells: SearchQA 1.24k E / 3.9–4.1k I; OfficeQA 4.6k / 7.9k; LiveMath 1.3–1.6k / 4.0–4.6k;
SpreadsheetBench 1.6–2.0k / 4.3–4.7k; ALFWorld 28k / 106–116k per episode).

| chain, stage | v3 gate cells | v3 receipts | rule arms judged | D1 cells | D1 receipts | + parent duplicate | + LOO, 3 rules |
|---|---|---|---|---|---|---|---|
| E-ds s1 SearchQA | 3,430 | 4.54M | 5 (4 screen + 1 confirm) | 1,200 | **1.50M** | +0.75M | +2.25M |
| E-ds s2 OfficeQA | 1,168 | 4.50M | 2 | 476 | 1.59M | +0.69M | +2.06M |
| E-ds s3 LiveMath | 1,282 | 2.79M | 2 | 1,292 | 2.39M | +0.67M | +2.02M |
| E-ds s4 Sheet | 872 | 2.14M | 1 | 724 | 1.61M | +0.17M | +0.50M |
| E-ds s5 ALFWorld | 0 | 0 | 0 | 836 | 4.91M | +1.65M | +4.95M |
| I-ds s1 SearchQA | 1,922 | 7.42M | 3 | 1,200 | **4.72M** | +2.36M | +7.09M |
| I-ds s2 OfficeQA | 0 | 0 | 0 | 476 | 3.04M | +1.17M | +3.52M |
| I-ds s3 LiveMath | 880 | 4.64M | 1 | 1,292 | 6.18M | +2.01M | +6.02M |
| I-ds s4 Sheet | 1,744 | 9.31M | 2 (1 + 1) | 724 | 3.76M | +0.41M | +1.22M |
| I-ds s5 ALFWorld | 974 | 38.85M | 1 | 836 | 16.41M | +6.36M | +19.09M |
| **five stages** | | **E 13.97M / I 60.22M** | | | **E 12.00M / I 34.13M** | E 15.9M / I 46.4M with a duplicate every step | |

(D1 runs a round only when a package survives preparation; v3 cost 0 where nothing was screened.) Two structural
differences: v3 runs every rule arm over the whole focal panel (E-ds s1: 415 cells per rule arm on 200 items at 2 runs plus
4–11 trigger items at 4) and then decides C1 on 4–11 items of which ~29% are informative; D1 runs one candidate arm
whatever the package size and decides on all n_a items.

Controls [E]: a parent duplicate or a placebo arm each costs the "+ parent duplicate" column. Both in the chain's first
round only: E 13.50M / I 38.85M over five stages (cheaper than v3 on both chains); both in every stage's first round:
E 19.85M / I 58.75M (more than v3's 13.97M on E, about equal to its 60.22M on I). The D1 totals assume a round at every
step, including the two steps where v3 spent nothing.

### 7.2 Training rollout [E]

D1's rollout covers only B_p (the acceptance batch must stay unseen): SearchQA 100 instead of 200 items, OfficeQA 37 of
74, LiveMath 50 of 100, SpreadsheetBench 45 of 91, ALFWorld 28 of 57. Measured v3 rollouts cost E 4.87M / I 16.0M over the
five stages; D1 about half (≈ 2.4M / 8.0M). GLM role calls (examiner, analyst, adjudication; v3 0.24–1.54M per step) and
selftest are unchanged.

### 7.3 Futility look [E]

Interim after n_a/2 items; reject if d̄ ≤ 0; otherwise finish and decide on all items (futility-only stopping cannot raise
type I). Simulated on cal-1 (mix model, k = 2, 2,000 batches):

| true δ | n_a | stops at interim | share of round cells spent | power fixed → with futility |
|---|---|---|---|---|
| −0.03 (harmful, like most measured rules) | 300 | 92% | 54% | 0 → 0 |
| 0 | 300 | 53% | 73% | 0.056 → 0.056 |
| +0.03 | 300 | 9% | 95% | 0.603 → 0.597 |
| +0.05 | 300 | 2% | 99% | 0.893 → 0.885 |

### 7.4 Wall-clock [M]

The pilot ran 1,560 cells in 6,373 s with 6 workers on the new machine (≈ 880 cells/h): a 1,200-cell SearchQA round takes
≈ 1.4 h at that rate.

## 8. Why this does not violate "no fixed validation set"

Precise statement [C]: D1 never designates any labelled item as validation data for the run. At step t the acceptance batch
is drawn, from the same training pool the method learns from, among items that played no part in constructing the step-t
candidate; after the decision it is returned to the pool and stays available as learning material for later steps.
Hence:

1. **Nothing is reserved**: no item is held out from learning for the run; at most it is held out for one decision. Items
   move only from "eligible to judge" to "learning only", the reverse of a validation set.
2. **Selection material is re-drawn every step** and sized by a pre-registered power rule, not by a split.
3. **Same labelled pool as the baselines**: train + val of the five training pools (registration §2.2).
4. **Isolation unchanged**: test sets and not-yet-reached benchmarks are never touched; acceptance labels are never shown to
   any model role.
5. **It is the registered category**: registration `coevo5-registration-20261016.md` §2.2 (lines 101–105) states the claim
   as "no separate held-out validation partition", explicitly *not* "no labelled selection data", and calls the check half
   "training-side, process-adaptive selection material, re-drawn every step"; the owner decided on 10/16 that the gate uses
   the pass rate on real training items (`docs/project-status.md` lines 32–33). D1 keeps that category and changes the
   unit (version, not rule), the size (power, not trigger count) and the freshness guarantee (never proposed on, across
   the chain, not only within a step).
6. **Contrast with the val-gated baselines**: GEPA keeps a candidate if it improves on the minibatch it was reflected on (the
   same data) and then scores it on D_pareto, "a validation set used for candidate selection" (arXiv 2507.19457, §3.1,
   Algorithm 1, as quoted from the arXiv HTML). D1 has no fixed D_pareto and never accepts on the reflection data.

What D1 does not satisfy, stated plainly: it uses labelled training items to accept or reject, exactly as v3 did. If "no
fixed validation set" is read as "no labelled real item may decide acceptance" — the owner raised this on 10/15 18:30
(`docs/project-status.md` lines 409–410) before deciding otherwise on 10/16 — then neither v3 nor D1 qualifies, and the only
alternative is generated items (D6), whose fidelity must itself be checked on real training items.

## 9. What the paper's claim becomes [C]

- **Mechanism**: "Each step proposes one new Skill version. It is accepted only if, on a fresh batch of training items that
  played no part in constructing it, its paired accuracy gain over the current version has a one-sided 95% lower confidence
  bound above zero, with non-inferiority on the earlier benchmarks. Batch sizes come from a pre-registered power analysis
  of the solver's measured re-run noise and of a positive control."
- **Unit of evidence = the version.** Per-rule statements become descriptive (subgroups, leave-one-out with CIs). The claim
  "every accepted rule was proven on held-out items" is withdrawn; "every accepted version was proven on fresh training
  items with ≤ 5% false-acceptance per decision" replaces it. With T decisions per chain the expected number of false
  acceptances under a global null is ≤ 0.05·T (T = 10 → 0.5); report T (D8 may spend α across steps).
- **Effect sizes**: acceptance-time estimates are selection estimates (inflated 1.3–2× at low power); effect and
  generalisation claims rest on the test evaluations of all five benches (transfer matrix, similar vs dissimilar),
  unchanged from v3.
- **Negative results become quantified**: "no version was accepted on SearchQA; at n = 300 × 2 runs the design had 84–89%
  power for +0.05 and 49–60% for +0.03" — the v3 gate could not state its power.
- **Content attribution needs a placebo reference**, because an irrelevant sentence reached +0.036 (LB +0.011) on the empty
  scaffold: either a standing per-stage placebo calibration (cost §7.1; 1–2 length-matched placebo versions on the stage's first
  acceptance batch; on the good-instruction parent the two placebos tested moved 0.000 and −0.023) or, for the paper, a
  placebo chain (accept a length-matched irrelevant text whenever the method accepts; the test-set difference is the content
  effect).

## 10. Pilot

**Ran** (launched by the previous D1 round on the new machine, 2026-10-20 23:56:59 → 2026-10-21 01:43:12, unit status
`complete`; analysed for the first time in this round). Script `/data/feasibility/D1/v2/d1v2_pilot.py` (imports the frozen
v3 snapshot and the v3 launch manifest read-only; own output root, ledger and slot files). Design: 6 arms × 130 fresh
SearchQA training items × 2 runs = 1,560 cells; arms E (empty scaffold = cal-1 parent:A), E+P3 (= cal-1 control:3), S
(scaffold + SearchQA task card = cal-1 seed-only), S:dup, S+P2, S+P3. Fresh = the 600-item pool minus the 231 items any v3
non-test unit used, seeded order `d1v2-fresh:searchqa`, first 130 (92 historical-train, 38 historical-val parts).
Cost: **2,388,219 ledger tokens** (= receipts; no 503 reservations), 1,531 per cell. Earlier D1 spending: the 10/20 19:08
pilot attempt (stopped incomplete to leave the route to the cal-1 resume, not interpretable) 112,525 tokens incl. its smoke;
the v2 smoke 18,549. Total D1 spend 2.52M. Results: §3.2 and §5.2. No new paid call in this round.

Reconstructed launch (from the script's arguments and the log): `ssh <datatools-login> "bash
-ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/D1/v2 && /root/continual-alf-prep-20260928/env/bin/python
d1v2_pilot.py --out /data/feasibility/D1/v2/pilot --items 130 --workers 6 --slots 6 --cap 3600000' > pilot.log 2>&1"`.

The next pilot worth running (not run; ≈ 2.1M tokens): the version-level effect of a *real learned package on the
good-instruction parent* (e.g. the merged I-ds s1 package vs the five-seed Skill, 2 arms × 130 fresh items × 2 runs ×
~3.9k tokens), which would pin τ for the realistic case — the one heterogeneity value this report could not measure.

## 11. Risks and open points

1. **Small pools**: OfficeQA, SpreadsheetBench and ALFWorld can only certify ≥ 0.10–0.15, and only their first step gets
   fresh proposal material; later steps recycle proposal items and re-use the same acceptance batch.
   Generated items (D6) add items from a different population; the relaxed freshness rule adds steps with an in-sample bias.
2. **No effect to find**: on the good-instruction chain no measured rule has a version-level effect (§5.3), and cal-1's
   rule-shaped texts are ≤ 0; a D1 chain may accept nothing. D1 fixes the instrument, not the proposals (D13) or the
   headroom (D9).
3. **Placebo acceptance** on a weak parent (§5.1); a placebo reference is needed for content claims (§9).
4. **Heterogeneity hides harm**: a package can help 30% of items and hurt 20%; report up/down counts and subgroups.
5. **Drift** (§6): a +0.033 vs +0.090 swing of the same comparison between two days; same-round measurement is mandatory and
   test-day conditions may differ from acceptance-day conditions.
6. **Winner's curse** (§4.2): acceptance estimates overstate effects; never report them as effect sizes.
7. **Regression checks are weak at 60 items** (non-inferiority resolution ≈ 0.07–0.11 at 80% power); larger panels cost more
   (D8).
8. **Assumptions in the power model**: heterogeneity measured on SearchQA only and on the empty scaffold for real effects;
   other benches use assumed τ; the simulation resamples 200 items (a population of 200).
9. **Route capacity**: ≈ 880 cells/h at 6 workers; one ALFWorld round costs ≈ 16.4M tokens on the seeded chain (4.9M on
   the empty-scaffold chain), most of it the 116 focal episodes at ≈ 110k tokens each.

## 12. Recommendation

Adopt D1 as the v5 acceptance rule: one merged candidate per step; acceptance on a fresh, never-proposed-on batch in one
interleaved round; LB₉₅ > 0 and d̄ ≥ 0.02; non-inferiority on earlier benches with D8's margins; a parent duplicate and one
length-matched placebo arm in the chain's first round (in every stage's first round only if the budget allows:
19.9M E / 58.7M I over five stages instead of 13.5M / 38.9M); a futility look at half the batch; attribution
descriptive and only after acceptance. Registered sizes: SearchQA 300 × 2 (or 500 × 1), LiveMath 183–233 × 2, the three small pools all
unflagged × 2–4 with their δ₈₀ printed in the registration. Start the chain from the task-card instruction (the owner's
yardstick), and pre-register the expectation that it may accept nothing — with the power statement of §9 as the result.

## 13. References

- Registration `docs/handoff/coevo5-registration-20261016.md` §2.2 (lines 90–105), §4 (lines 124–143); cal-1 registration
  `docs/handoff/cal1-registration-20261020.md` (results lines 134–150); `docs/project-status.md` lines 32–33, 70, 409–412;
  frozen v3 code `/data/coevo5-20261019-v3-source-f/skillopt/coevo5/{protocol.py (constants, lines 54–126), step.py
  (runs_plan 184–195, halves 216–225, _round 642–717), data.py (pool 155–166, training_items 188–196, regression_items
  199–205)}`.
- Agrawal, L. A. et al. (2025). GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning. arXiv:2507.19457
  (acceptance rule checked in the arXiv HTML, §3.1 and Algorithm 1).
- Dwork, C., Feldman, V., Hardt, M., Pitassi, T., Reingold, O., Roth, A. (2015). The reusable holdout: Preserving validity
  in adaptive data analysis. Science 349(6248), 636–638 [volume/pages from memory]; technical version "Generalization in Adaptive Data Analysis and Holdout
  Reuse", NeurIPS 2015, arXiv:1506.02629.
- Blum, A., Hardt, M. (2015). The Ladder: A reliable leaderboard for machine learning competitions. ICML 2015, PMLR 37:1006–1014.
- Miller, E. (2024). Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations. arXiv:2411.00640
  (paired differences; clustering by question when questions are sampled repeatedly). [from memory]
- Dawid, A. P. (1984). Statistical theory: the prequential approach. J. Royal Statistical Society A 147(2), 278–292;
  Gama, J., Sebastião, R., Rodrigues, P. P. (2013). On evaluating stream learning algorithms. Machine Learning 90, 317–346
  (test-then-train). [from memory]
- Efron, B., Tibshirani, R. J. (1993). An Introduction to the Bootstrap. Chapman & Hall. [from memory]
- Athey, S., Imbens, G. (2016). Recursive partitioning for heterogeneous causal effects. PNAS 113(27) (honest estimation:
  separate samples select and estimate). [from memory]

## 14. Files

Mac scratchpad `…/scratchpad/feas/D1/r3/` (copied to `/data/feasibility/D1/r3/` on the new machine; the cal-1 extraction
also lives in `/data/feasibility-scratch/D1/r3/` on the old machine):
`extract_unit.py`, `walk_v3_gate.py`, `ledger_scopes.py` (read-only extraction); `common.py`; `describe.py` →
`desc_cal1.json`, `desc_pilot.json`; `sd_analysis.py` → `sd_cal1.json`, `sd_pilot.json`; `run_pairing.py` →
`run_pairing_cal1.json`; `power_sim.py` + `cfg_full.json` → `power_full.json`, `power_full_table.json` (`power_table.py`);
`analytic.py` → `analytic.json`; `replay.py` → `replay_cal1_parent{A,B}.json`, `replay_pilot_{E,S}.json`; `did.py` →
`did_pilot.json`; `drift.py` → `drift.json`; `v3_costs_r3.py` → `v3_costs_r3.json`; `d1_costs.py` → `d1_costs_r3.json`;
`v3_train_noise.py` → `v3_train_noise_r3.json`; `replay_v3.py`, `replay_v3_p.py` → `replay_v3_r3.json`,
`replay_v3_p_r3.json`; `cand_halves.py`; `futility_sim.py` → `futility_r3.json`; extracted tables `cal1_cells_r3.tsv`,
`pilot_cells_r3.tsv`, `v3_gate_cells_r3.tsv`, `v3_halves_all.json`, `v3_ledger_scopes_r3.json`.
