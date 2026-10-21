# E9: Transfer-aware acceptance (accept rules for transfer, not for source fit). Feasibility report, 2026-10-21

Serves the owner's **purpose 2** (the metric is generalisation: evolve on one benchmark, evaluate on the others). It
touches purpose 1 (co-evolution) in one place: the generated similar-target panel is the verification side's artifact,
and §3.1 gives the first measurement of whether it can stand in for a real target.

Tags: **[M]** measured here or in a cited file; **[E]** estimated from measured inputs; **[C]** claim or design choice.

---------------------------------------------------------------------------------------------------------------------

## 0. Bottom line

**Verdict: medium feasibility.** A transfer-aware veto is cheap and easy to build, and it does catch gross harm. At
affordable sizes it cannot certify "no harm" below about 10 points per rule. On v3's data it would change nothing,
because no rule passed the source test.

1. **[M] Negative transfer between similar benchmarks is real, so a source-only acceptance rule is not enough.**
   - The LiveMath task-card seed, placed in its own LiveMath section, lowers the similar target OfficeQA by
     **-8.1 and -9.5 points** in two independent windows (74 OfficeQA training items, 1 run each; one-sided 95% upper
     bounds -0.51 and -0.98, so it is vetoed both times).
   - The SearchQA seed (byte-identical to cal-1's `seed-only`, same SHA-256) gains **+8.8** on its own benchmark (200
     SearchQA items x 4 runs) but moves OfficeQA by **-4.1 / -6.8** (not significant). It helps LiveMath (+6.0, SE 2.9).
   - Mechanism: these texts make OfficeQA replies "answer only". The answer-only share rises from 0.23 to 0.59-0.60,
     even though the text sits in another benchmark's section.
   - Consequence: section scoping does not isolate a rule. Every rule needs the transfer check, not only rules the
     analyst marks `similar` (in v3, 47 of 49 proposals were `local` and had no forward check at all).
2. **[M] Pilot (1,124 cells, 2.87M tokens): a generated OfficeQA-style panel cannot yet stand in for the real
   OfficeQA training pool.**
   - The 69 generated items are saturated. The empty scaffold passes 89%; 61 of 69 items pass on both runs and 7
     fail on both, so one item is mixed.
   - Effects keep their sign (3 of 3 texts) but shrink to **0.23-0.54 times** the real effect.
   - The generated panel misses the real -9.5 harm (upper bound +1.8, no veto). It does catch a format-breaking text:
     -33.3 points, 37 of 138 replies without the answer tag, upper bound -24.4.
   - Use: a gross-harm screen today, not the transfer proxy.
3. **[M/E] Power of a per-rule veto (from the complete cal-1 cells and target noise).**
   - SearchQA- or LiveMath-like proxy, 2 runs per item: a **-10 point harm is vetoed 0.54-0.58 / 0.77-0.84 /
     0.96-0.98** of the time at **30 / 60 / 120 items** (resampled and analytic). A **-5 harm only 0.23-0.24 /
     0.35-0.37 / 0.56-0.58**. Harmless texts are falsely vetoed 2-5%.
   - OfficeQA has only 74 training items in total. At all 74 items x 2 runs: P(veto) is 0.70 at -10, 0.29 at -5.
   - Proving no-harm instead (non-inferiority, NI) at a 5-point margin passes a harmless rule only 0.37 (60 items)
     and 0.58 (120 items). That is unusable. Per-rule transfer protection is a gross-harm screen. Claims of "no drop"
     below about 10 points belong to the version level (D1/D8).
4. **[C] Decision rule** (formulas and numbers in §4): accept a rule iff
   - (0) it is not a restatement (free lexical screen);
   - (A) it gains on fresh source training items (D8's C1' or D1's version test);
   - (V) a veto-only test on the guard target's training pool does not show harm (one or two looks, rule and parent
     interleaved in one window);
   - (V_G) a fresh generated panel does not show gross harm at 1%.
   With 300 source items x 2 runs (per-item SD 0.33) and 60 guard items x 2 runs (per-item SD 0.32), a +5-point
   source rule is accepted as follows:
   - **0.79** if harmless on the target;
   - **0.56** if it costs the target 5 points;
   - **0.18** if it costs the target 10 points (0.03 with 120 guard items);
   - a source-only rule accepts all three cases at 0.84.
5. **[C] Keeping the proxy out of training.**
   - The guard is a veto and never promotes. Its items and replies never reach a method role. It releases one bit
     per rule.
   - Its own numbers are never transfer evidence: they are biased upward by about 0.3-0.6 points per surviving null
     rule.
   - The guarded target is reported as **"guarded"**, apart from the unguarded targets on which the generalisation
     claim is made.
   - Fresh draws per step are possible only where the pool is large: SearchQA 600, LiveMath 283. On OfficeQA (74),
     SpreadsheetBench (120) and ALFWorld (57) the guard reuses the whole pool. That is a fixed validation set in
     substance, so it must be declared as such or replaced by a validated generated panel.
6. **[M] Generic restatement is a real but contained risk.**
   - Verbatim task-card sentences used as rules gave **+0.3 and -3.1 points** against +8.8 for the whole card
     (cal-1, 200 x 4).
   - Only 1-2 of 49 v3 proposals restate their card lexically (median overlap of the best-matching line 0.16).
   - The danger comes from an acceptance rule that rewards transfer gain or uses an empty-scaffold parent; this
     design does neither.
7. **[E] Cost.** For every rule that passes the source test (not every proposal):
   - LiveMath guard (60 x 2, seeded parent): 0.53M tokens;
   - OfficeQA (74 x 2, seeded): 1.21M tokens;
   - generated panel (60 x 2): 0.16M solving plus 0.16M generation per step;
   - plus one parent arm per step on the same items.
   About 1.1-3.6M tokens per step with C1-first sequencing and 1-2 passers (0 when none passes), which is 20-50% of a
   v3 screen round.

---------------------------------------------------------------------------------------------------------------------

## 1. What I did (provenance)

- This report continues an earlier E9 explorer session of the same assignment. That session wrote the scripts in
  `scratchpad/feas/E9/scripts/`, extracted the complete cal-1 cells, ran three free analyses, and designed and
  launched the pilot. Its design is fixed in the header of `e9_proxy_pilot.py`, written before launch. The pilot ran
  2026-10-21 01:11-02:37 on the new machine and finished (`summary.json`: status done). Its pre-registered analysis
  had not been run.
- I re-verified the inputs, ran the pre-registered analysis unchanged (`e9_proxy_analyse.py` -> `proxy_analysis.json`),
  and added three free analyses:
  - the proxy power tables (`e9_proxy_power.py`);
  - training-pool sizes through the repository's own reader, which refuses test items (`e9_pool_sizes.py`);
  - OfficeQA within-window run variance from the v3 training units (D12's extracted table).
- Read: `skillopt/coevo5/gate.py` (C4'), `protocol.py` (SIMILAR_PAIRS, FORWARD_STYLES, REGRESSION_ITEMS,
  MIN_SIMILAR_DELTA), `step.py` (similar placement), `data.py` (test refusal); the cal-1 registration; the D6, D8 and
  E1 reports; E2's placement records (read-only); D12's working data. D12's report does not exist yet: I checked at
  04:41 and 04:51; only scripts and JSON outputs are there.
- Hard rules kept: no test or holdout file was opened (the OfficeQA items came through `data.training_items`, which
  refuses test ids); no credential was printed; nothing was written to the repository or to any completed run
  directory. Outputs are in `/data/feasibility/E9/` (new machine) and `scratchpad/feas/E9/` (Mac).

## 2. What exists today (v3 code, read from source) [M]

- `gate._similar`: **C4'** is applied only to a rule whose placement is `similar`. Per similar target it requires
  `total(rule, L) - total(parent, H) >= MIN_SIMILAR_DELTA = 0`.
  - A backward target (already learned) is checked on its 60-item, 1-run regression panel.
  - A forward target is checked on "a frozen panel of 8-12 generated items" (`FORWARD_PANEL`), with
    `FORWARD_RUNS = 2`.
  - `FORWARD_STYLES = ("officeqa", "livemath")`: SearchQA is never a forward target, and no SpreadsheetBench panel
    can be generated.
- A `local` rule gets no forward check at all: only C2 (focal rest) and C3 (regression on earlier benchmarks). In v3,
  47 of 49 proposals were `local`, 1 `similar`, 1 without placement (`v3_proposals.json`).
- Power of today's C4' (D8 §4.4; D12 working data `power_items.json`): with 8-12 forward items x 2 runs the SE is
  about 8-10 points. One round passes a harmless rule 0.61 of the time and a -10-point harm 0.30 of the time
  (I-ds OfficeQA, n = 8). It is close to a coin flip, and the frozen forward machinery produced short panels in D6's
  smoke test anyway.

## 3. Measured facts that drive the design

### 3.1 Pilot: does a generated similar-target panel agree with the real target? [M]

**Design** (fixed before launch).
- **G** = 69 generated OfficeQA-style items. Panels K1 (12) and K2 (7) come from E1's pilot 3b. K3-K8 (7, 11, 9, 6,
  12, 5) are 50 new items built by the **unchanged** v3 forward machinery (`forward.build_panel` +
  `research.material`, GLM-5.3 at the protocol role settings, English Wikipedia). They follow six rule-agnostic
  OfficeQA-style criteria, e.g. "When a table of public debt ... reports fiscal years, calendar years or quarters ...".
- **R** = the 74-item OfficeQA training pool, which is the whole pool.
- **Arms** (frozen v3 renderer; SHA-256 checked against E2/E4):
  - P = empty scaffold; P2 = the same bytes under another label (null);
  - O_home = OfficeQA seed in the OfficeQA section;
  - L_home = LiveMath seed in the LiveMath section;
  - S_home = SearchQA seed in the SearchQA section;
  - A_O = ALFWorld seed placed in the OfficeQA section.
- **Runs:** G 2 per arm, R 1 per arm. Solver: deepseek-v4-flash, thinking off, temperature 0, max_tokens 32768,
  frozen scorer (truncation = fail).
- **Dispatch:** one seeded shuffle of all G and R cells interleaved, 5 workers.

**Delivery:** 1,124 cells, 0 unknown, 0 stop, 12 truncations (all on R: O_home 7, S_home 3, L_home 2).
- deepseek 2,734,359 tokens;
- GLM 133,510 tokens over 173 calls, about 2,670 tokens per new kept item;
- Wikipedia: 191 requests, 56 retried after HTTP 429, 0 lost;
- wall time 86 minutes.

| | G pass rate (69 x 2) | R pass rate (74 x 1) | G effect vs P, pts [95% bootstrap CI] (up/down) | R effect vs P, pts [CI] (up/down) | G/R | veto G / R |
|---|---|---|---|---|---|---|
| P | 0.891 | 0.405 | - | - | - | - |
| P2 (same text) | 0.899 | - | +0.72 [0.00, 2.17] (1/0) | - | - | no / - |
| O_home | 0.964 | 0.581 | +7.25 [1.45, 14.49] (5/0) | **+17.57** [8.11, 27.03] (15/2) | 0.41 | no / no |
| L_home | 0.870 | 0.311 | -2.17 [-7.25, 2.17] (2/3) | **-9.46** [-20.27, 0.00] (4/11) | 0.23 | **no / yes** |
| S_home | 0.870 | 0.338 | -2.17 [-7.97, 2.90] (2/4) | -6.76 [-18.92, 5.41] (8/13) | 0.32 | no / no |
| A_O | 0.558 | - | **-33.33** [-44.20, -22.46] (2/30) | (E4: -34.6 on 13 real items) | - | **yes** / - |

- **Saturation of G:** under P, 61 of 69 items pass on both runs and 7 fail on both. Under P and P2 together (4 runs)
  the same 61 / 7 hold. Over all six arms x 2 runs, 31 items always pass and 2 always fail.
- **Per-item SD of paired differences:**
  - G (2 runs): 0.06 (null), 0.20-0.26 (seeds), 0.45 (A_O);
  - R (1 run): 0.44-0.53.
  - Within-item run variance on G is tiny (W 0.007-0.022 for seeds), because the items are saturated.
- **Agreement:**
  - Sign: 3 of 3 texts agree.
  - G - R differences: -10.3 (SE 6.1), +7.3 (5.7), +4.6 (6.8).
  - Against E2's earlier R window: G/R = 0.54, 0.27, 0.54.
  - Veto decisions agree on 2 of 3; the disagreement is the real harm. NI at 10 points: G passes L_home and S_home,
    R fails both.
- **The real pool reproduces across windows** (E2 10/20 19:26 vs this window, same texts, same 74 items):
  - O_home +13.51 -> +17.57;
  - L_home -8.11 -> -9.46 (vetoed both times);
  - S_home -4.05 -> -6.76;
  - same-text drift per item: P +1.35 (6 up / 5 down), per-item SD 0.39-0.41.
- **Format** (answer-only share = reply of at most 80 characters on one line):

| | P | O_home | L_home | S_home | A_O |
|---|---|---|---|---|---|
| R | 0.23 | 0.015 | 0.597 | 0.592 | - |
| G | 0.036 | 0.0 | 0.457 | 0.37 | 0.92 |

  - A_O drops the answer tag in 37 of 138 G replies.
  - The harms of L_home and S_home on OfficeQA go with the switch to answer-only replies: the solver stops computing.

**Reading.**
- The real OfficeQA training pool works as a transfer proxy: its effects reproduce across windows, and it vetoes the
  -9 point harm twice, although only just (upper bounds -0.5 and -1.0).
- The version-0 generated panel measures something correlated but compressed, because the items are one-subtraction
  lookups that the empty scaffold already solves (E1 §7.2 found the same on 23 items). It catches format breaks.
- This is the first measurement of D6's "panel-validity study" and E1's fitness F3 for OfficeQA. It has only 3
  comparable texts, so λ (the G/R effect ratio) is poorly determined: 0.23-0.54.

### 3.2 Transfer is target-specific and placement-specific [M]

E2's placement pilot (10/20, read-only):

| text | LiveMath effect (100 x 2) | OfficeQA effect (74 x 1) |
|---|---|---|
| S_home (SearchQA seed, SearchQA section) | **+6.0** (SE 2.87) | -4.05 (5.59) |
| S_general (the same seed under "General / Applies when: any task") | -1.0 (2.84) | **+10.81** (4.93) |
| O_home | +3.0 (3.08) | +13.51 (4.84) |
| L_home | +7.0 (3.33) | **-8.11** (4.62) |

- The same SearchQA text helps one similar target and hurts another. Moving it to a general section reverses the
  OfficeQA sign: the difference is 14.9 points, z about 2 if the two arms are taken as independent. Suggestive, not
  established.
- Consequences:
  - A guard must test a rule in its **actual placement**.
  - It must test it on the **specific** target, not on a pooled "similar" average.
  - A guard on one similar target does not certify the others (§6.4).

### 3.3 Noise numbers for power [M]

- **cal-1** (now complete: 8,800 cells = 11 arms x 200 SearchQA training items x 4 runs; 6,008 pass, 2,777 fail,
  15 unknown; attempt-1 7,189 cells, attempt-2 1,611). Effects vs parent:A in points (SE):
  - parent:B (same text) +0.75 (0.99), up 20 / down 16;
  - ids-full +9.25 (2.20); seed-only +8.83 (1.93);
  - seed-rule +0.29 (1.75); seed-rule3 -3.12 (1.79); cand -2.75 (2.31);
  - control:1 -3.75 (1.43); control:2 +3.38 (1.51); control:3 -10.00 (1.94); control:4 0.00 (1.54).
  - Variance components: W (within-item run variance, both arms) 0.083-0.139; τ (SD of the true per-item effect) 0
    (null) to 0.28. The profile used below is the median: τ 0.18, W 0.11, so the per-item SD at k runs is
    s_d(k) = sqrt(τ² + W/k) = 0.377 / 0.296 / 0.245 for k = 1 / 2 / 4.
- **LiveMath** (E2, 100 x 2): τ 0.17, W 0.13, so s_d(2) = 0.306.
- **OfficeQA:**
  - s_d(1) measured on R: 0.443 / 0.449 / 0.532 (this pilot) and 0.40-0.48 (E2).
  - W from the v3 training units (74 items x 2 runs): E-ds 0.081, I-ds 0.095. I verified this from D12's extracted
    table; 6 and 7 of 74 items flip between runs.
  - So s_d(2) is about 0.397 (central) to 0.486 (pessimistic).
- **Session effects** (D12 working data, `power_items.json`; D12's report pending): the I-ds OfficeQA parent's means
  over 60 items in four v3 sessions were 0.508 / 0.267 / 0.267 / 0.342. That is an SD of 11.4 points against 2.7
  expected from sampling. For SearchQA the session SD is about 1.5 points.
  - **The guard must run rule and parent interleaved in one window.** A parent baseline stored from another session
    is useless on OfficeQA.

### 3.4 Training-pool sizes (rotation constraint) [M]

Through `data.pool` + `data.training_items` (refuses test ids):

| benchmark | pool | v3 panel | fresh 60-item draws possible | fresh 120-item draws possible |
|---|---|---|---|---|
| SearchQA | 600 | 200 | 10 | 5 |
| OfficeQA | 74 | 74 | 1 (no rotation) | 0 |
| LiveMath | 283 | 100 | 4 | 2 |
| SpreadsheetBench | 120 | 120 | 2 | 1 |
| ALFWorld | 57 | 57 | 0 | 0 |

### 3.5 Restatement evidence [M]

- **cal-1** (the arms are empty scaffold + rule, not seed + rule): one verbatim card sentence as a rule ("Answer with
  the minimal entity ...") gave +0.29 (SE 1.75). Three card sentences gave -3.12 (1.79). The whole SearchQA seed
  gave +8.83 (1.93). Restating parts of the card as rules does not reproduce the card's effect; on this evidence a
  restatement fails the source test rather than passing it.
- **v3 proposals** (49): lexical content-word overlap with their own benchmark's task card (`e9_restatement.py`) has
  a median of 0.16 against the best-matching card line and 0.42 against the whole card.
  - Best-line overlap of 0.40 or more: 1 (I-ds s4-r3, 0.45, reached screen).
  - Whole-card overlap of 0.60 or more: 2 (I-ds s4-r3 and s4-r5, both 0.68).
  - Lexical restatement was rare. Semantic restatement is not measured; a GLM judge would be needed.

## 4. The decision rule [C, numbers E from M inputs]

### 4.1 Notation
- p = parent Skill. It **must contain the five task-card seeds** (the I-ds-style parent): the owner's question is
  whether a learned rule beats a good instruction.
- r = candidate rule in its actual section.
- S = source benchmark (the one evolved on).
- Q = guard target: a registered similar benchmark, chosen before the run.
- G_Q = generated panel in Q's style.
- Paired item difference on panel X: d_i = ȳ_i(p ⊕ r) - ȳ_i(p).
  - ȳ = mean of the k scored runs.
  - Unknown cells are excluded pairwise; a truncation is a fail.
  - Both arms are dispatched in **one seeded interleaved shuffle within one window**.
- d̄_X, s_X, SE_X = s_X / sqrt(n_X); z_0.95 = 1.645.

### 4.2 Step 0, admissibility (free)
```
reject r as "restatement"  <=>  overlap_best_line(r, p ∪ card_S) >= 0.40   or   overlap_card(r, card_S) >= 0.60
```
- Would have fired on 1-2 of 49 v3 proposals.
- Plus the v4 conditional template: a checkable "when <observable condition>" is required.

### 4.3 Step A, source gain (D8's C1' per rule, or D1's version test; not re-derived here)
```
A_S  <=>  LB_S = d̄_S - z_{1-α/m} · SE_S > 0    and    d̄_S > max_c d̄_S(placebo c)        (α = 0.05, Holm over m <= 5)
```
- Panel: source training items never shown to a method role. Version-level form: n_S = 300 fresh SearchQA items x
  2 runs, s 0.33, so SE_S = 1.91 points.
- P(A_S | true source effect 0 / +3 / +5 / +8.8 points) = **0.05 / 0.47 / 0.84 / 0.999** [E].
- **C1-first:** only A_S passers go on to Step V. The guard costs nothing for rules that fail at home (v3: 2 of 14
  screened rules passed a screen).

### 4.4 Step V, transfer veto on the guard target's training pool (veto-only)
```
single look   (pool < 2 n_1, e.g. OfficeQA: all 74 items, k = 2):  veto <=> d̄_Q + 1.645 · SE_Q < 0
two looks     (pool >= 2 n_1, e.g. LiveMath, SearchQA; n_1 = 60, k = 2):
   look 1 on n_1 fresh items:                         veto <=> d̄_1 + 1.96 · SE_1 < 0
   if not vetoed and d̄_1 < 0: n_1 more fresh items:    veto <=> d̄_{1+2} + 1.96 · SE_{1+2} < 0
```
Two-look numbers, resampled from the complete cal-1 cells (SearchQA as a proxy population with known text effects)
[E from M]:

| text (true effect, pts) | P(veto), two looks n_1 = 60 | mean items | single look 60 / 120 |
|---|---|---|---|
| parent:B (+0.75, same text) | 0.021 | 79.5 | 0.035 / 0.025 |
| control:4 (0.0) | 0.039 | 85.3 | 0.043 / 0.047 |
| seed-rule (+0.3) | 0.029 | 82.1 | 0.036 / 0.037 |
| cand (-2.75) | 0.129 | 95.2 | 0.123 / 0.167 |
| seed-rule3 (-3.1) | 0.244 | 98.8 | 0.203 / 0.292 |
| control:1 (-3.75) | 0.396 | 100.3 | 0.297 / 0.473 |
| control:3 (-10.0) | **0.933** | 79.1 | 0.784 / 0.963 |

- With n_1 = 30: control:3 0.695, parent:B 0.027, mean items 35-48.
- OfficeQA single look, 74 x 2 (s 0.397 central / 0.486 pessimistic):
  - P(veto | 0) = 0.05;
  - -5: 0.29 / 0.22;
  - -10: 0.70 / 0.55;
  - -15: 0.95 / 0.84.
- Measured on R at 74 x 1: the -8 to -9.5 text was vetoed in 2 of 2 windows. For a -9 harm at SE 5.2 the expected
  rate is about 0.53, so two hits are partly luck.

### 4.5 Step V_G, gross-harm screen on a fresh generated panel (optional while the generator is invalid)
```
veto_G <=> d̄_G + 2.326 · SE_G < 0          (n_G >= 60 fresh items x 2 runs; one-sided 1%)
```
- Measured: the format-breaking A_O text gives d̄ -33.3 and SE 5.43, so the bound is -20.7: vetoed. The -9.5
  content harm gives an upper bound of +1.8 at z 1.645: not vetoed.
- False veto for harmless rules: at most 1%. Cost: 0.08M (scaffold) / 0.16M (seeded) solving per rule, plus about
  0.16M GLM generation per step (shared by all rules).

### 4.6 Acceptance
```
accept r  <=>  admissible(r)  ∧  A_S  ∧  ¬veto_Q  ∧  ¬veto_G
```
False-veto budget for a harmless rule: at most 0.05 + 0.01 = 0.06.

Joint operating characteristics (analytic; source 300 x 2, per-item SD 0.33; guard per-item SD 0.32 at 2 runs, between
the LiveMath profile 0.306 and the SearchQA rule-like texts 0.30-0.38; single look) [E from M]:

| true source / target effect (pts) | guard 60 items | guard 120 items | source-only rule |
|---|---|---|---|
| +5 / +3 | 0.829 | 0.833 | 0.836 |
| +5 / 0 | **0.794** | 0.794 | 0.836 |
| +5 / -3 | 0.687 | 0.612 | 0.836 |
| +5 / -5 | 0.559 | 0.396 | 0.836 |
| +5 / -10 | **0.183** | **0.032** | 0.836 |
| +3 / 0 | 0.448 | 0.448 | 0.472 |
| +3 / -10 | 0.103 | 0.018 | 0.472 |
| 0 / any | <= 0.05 | <= 0.05 | 0.05 |

Reading: the guard costs about 4 points of acceptance for a harmless rule (0.836 -> 0.794). It removes 78% (60
items) or 96% (120 items) of "+5 at home, -10 on the target" rules. A -3 to -5 target harm still passes 40-69% of the
time: that range needs the version-level test.

### 4.7 Version-level transfer report (not a per-rule gate; D1/D8 own the test)
- After the run: the composed Skill vs the parent on every target's TEST split, with paired CIs.
- The guarded target is labelled "guarded". The generalisation claim is made on the unguarded targets.
- Where a per-step version gate is wanted, D8's non-inferiority on 3 points needs about 640 SearchQA items at 4 runs.
  This E9 guard does not replace it.

### 4.8 Variants rejected
- **"Helps the target" (LB_Q > 0) as a requirement:**
  - Power for a real +5 transfer is only 0.35-0.37 at 60 items x 2 runs and 0.56-0.58 at 120, so most transferring
    rules would be rejected.
  - It turns the proxy into a selection set.
  - It preferentially selects generic good-practice text.
- **Non-inferiority per rule:**
  - At a 5-point margin a harmless rule passes 0.37 / 0.58 (60 / 120 items, analytic). Resampling from the real cells
    gives 0.65 at 120 items for the zero-effect placebo control:4.
  - At 10 points it passes 0.84 / 0.98, but that margin is wider than any rule's plausible benefit.
  - Use NI only at the version level (D8).
- **v3's C4' as it stands** (sum >= 0 on 8-12 items): a harmless rule passes about 0.6 and a -10 harm about 0.3
  (D12, D8).

## 5. Power of the proxy at 30 / 60 / 120 items (one-sided 5%, 2 runs per item unless stated) [E from M]

h80 = the harm the veto catches with 80% power = 2.486 x SE.

| proxy (per-item SD) | 30 items: SE / h80 / P(veto at -10) / P(veto at -5) | 60 items | 120 items |
|---|---|---|---|
| SearchQA, cal-1 profile (s_d(2) 0.296), analytic | 5.40 / 13.4 / 0.58 / 0.24 | 3.82 / 9.5 / 0.84 / 0.37 | 2.70 / 6.7 / 0.98 / 0.58 |
| same, resampled from real cells (control:3, -10) | 0.54 | 0.77 | 0.96 |
| same, parametric resampling (adds per-item uncertainty) | 0.27 | 0.42 | 0.64 |
| false veto, parent:B / control:4 (resampled) | 0.043 / 0.046 | 0.034 / 0.045 | 0.021 / 0.052 |
| LiveMath (s_d(2) 0.306) | 5.59 / 13.9 / 0.56 / 0.23 | 3.96 / 9.8 / 0.81 / 0.35 | 2.80 / 7.0 / 0.97 / 0.56 |
| OfficeQA real (s_d(2) 0.397) | 7.25 / 18.0 / 0.40 / 0.17 | 5.12 / 12.7 / 0.62 / 0.25 | impossible (pool 74; at 74: 4.61 / 11.5 / 0.70 / 0.29) |
| OfficeQA real, 1 run (s 0.45) | 8.22 / 20.4 / 0.33 / 0.15 | 5.81 / 14.4 / 0.53 / 0.22 | impossible (at 74: 5.23 / 13.0 / 0.61 / 0.25) |
| generated v0, in real points (s 0.20-0.26, λ 0.23-0.54) | P(veto at real -10) at 69 items: 0.18-0.73 (central λ 0.35, s 0.20: 0.42) | at 120: 0.25-0.91 (central 0.61) | at 200: 0.35-0.99 (central 0.80) |

Items for 80% power:

| proxy | real harm -10 | real harm -5 |
|---|---|---|
| SearchQA (k = 2) | 54 | 217 |
| LiveMath (k = 2) | 58 | 232 |
| OfficeQA (k = 1) | 125 | 501 |
| OfficeQA (k = 2) | 97 | 390 |
| generated v0 (central) | 267 | 1,068 |
| generated v0 (range) | 85-790 | - |

## 6. How the proxy stays out of the training signal [C]

1. **Data firewall.**
   - Guard items are drawn by a dedicated random stream, seed = hash(run, step, "guard"), from the target's training
     pool minus every id ever placed in a role prompt.
   - Their cells go to a separate `guard/` unit. The prompt builders of the examiner, analyst, adjudicator and forward
     checker refuse any id in the guard ledger (an assertion, like `data._refuse_tests`).
   - No guard failure is ever diagnosed.
2. **Output firewall.** The gate receives only veto yes/no (the bound is logged for the report). The proposer never
   learns which rule was vetoed or why. It sees only the next parent and new source failures. So at most one bit per
   rule decision flows into the chain: at most 5 rules x T steps bits.
   - This is the mechanism family of the reusable holdout (Dwork et al. 2015, Thresholdout) and the Ladder (Blum &
     Hardt 2015): answer adaptive queries with a thresholded, low-information output so that a holdout can be reused.
3. **Veto-only.** The proxy can remove a rule, never promote or rank one. Rules cannot be selected for fitting Q's
   items.
   - Residual selection bias, on the guard panel only: a null rule that survives a 5% veto has
     E[d̄_Q | survives] = SE · φ(1.645)/0.95, which is **+0.29 / +0.41 / +0.50 / +0.56 points** at SE 2.7 / 3.8 /
     4.6 / 5.2.
   - Hence the guard panel's own numbers are never reported as transfer evidence. Transfer evidence comes only from
     the TEST split, which is item-disjoint from the guard pool.
4. **Claim labelling.**
   - Using Q's training items makes Q "seen (guard only)". The paper reports Q-test as a guarded result and makes the
     generalisation claim on unguarded targets.
   - Purpose-2 design that keeps an unguarded similar target: evolve on **SearchQA** (600-item pool, so fresh source
     batches are possible) and guard on **OfficeQA-train**, the hub of the registered similarity map.
     - The generalisation claim is made on **LiveMath** and **SpreadsheetBench**, OfficeQA's other neighbours, never
       seen; plus **ALFWorld**, which is dissimilar.
     - This directly tests whether a guard on the hub protects its neighbours. Per §3.2 that is not guaranteed, which
       is exactly what makes the test informative.
   - Evolving on OfficeQA instead, with three similar targets, would leave two unguarded similar targets. But its
     74-item pool gives a source SE of about 6.5 points per half at 2 runs: P(A_S | +5) is about 0.19. Not viable.
5. **Never test.** Guard draws come only through `data.training_items`, which refuses test ids by construction.

## 7. Interaction with "no fixed validation set"

| benchmark as guard | rotation | status under the owner's rule |
|---|---|---|
| SearchQA (600) | fresh 60-120-item draws per step; ids returned to the pool after the decision, as in D1 | compliant: no fixed set, fresh draws |
| LiveMath (283) | 4 fresh 60-item draws, then reshuffle with a new seed | compliant for about 4 steps, then items repeat with fresh runs |
| OfficeQA (74) | none: the whole pool every time, fresh runs only | **a fixed validation set in substance**: declare it, or use G |
| SpreadsheetBench (120) / ALFWorld (57) | none | the same; also too few items for power (ALFWorld at 1 run has s_d about 0.49, so even a 10-point margin needs about 264 items, D8) |
| generated panel G (any style) | fresh items every step by construction | compliant and claim-clean, **but v0 fails validity** (§3.1) |

- The tension is real. The only proxy that is both compliant and claim-clean is the generated panel, and today it is
  saturated and compresses effects to 0.23-0.54.
- Validity criteria a generator must pass before it may replace the real-pool guard (measured once, on calibration
  texts unrelated to the run, such as seeds and placebos; this validates the instrument, not rules):
  - (a) parent pass rate 0.3-0.7 on the generated panel; v0: 0.89;
  - (b) attenuation λ >= 0.6 with the same sign on at least 4 calibration texts against the real training pool;
    v0: 0.23-0.54, sign 3/3;
  - (c) same-text null within ±2 points; v0: +0.7, passes;
  - (d) at least 60 valid items per step; v0: 50 new items for 0.13M GLM tokens, passes with more rounds.
- That is the measurable fitness of the verification side, the co-evolution link to purpose 1 (E1's F3).

## 8. Risk of selecting rules that are generic restatements

- **Where the risk comes from:**
  - a parent without the card: then any card-like text gains at home (cal-1: the full seed +8.8);
  - an acceptance rule that rewards transfer gain, because generic good practice is what helps everywhere.
- **The design closes both:** the parent carries all five cards (§4.1), and the guard is veto-only (§4.6).
- **Evidence the residual risk is small:**
  - verbatim card sentences as rules: +0.3 / -3.1 against +8.8 for the card;
  - v3 lexical restatement: 1-2 of 49 proposals.
- **The risk the guard does create:** a narrow, condition-specific rule is inert on Q, so it passes the veto freely.
  A broad rule changes Q's behaviour (S_home answer-only share 0.23 -> 0.59), so it is the one the guard tests
  hardest. The guard therefore tilts acceptance toward narrow rules, not generic ones. That is the right direction for
  "learned from experience", but it means the guard alone never shows that a rule **transfers**; only the
  version-level test on unguarded targets does.
- **Cheap extra control, optional** (D8 keeps placebos): a length-matched generic-instruction arm (e.g. "Re-read the
  question; verify the answer against the source") on the source panel; require d̄_S(r) > d̄_S(generic). Cost: one
  more arm on the source panel, about 0.8M (scaffold) to 2.3M (seeded) at 300 x 2 per step.

## 9. Cost per step [E from measured per-cell usage]

Per-cell usage:

| benchmark | scaffold parent | seeded parent | source |
|---|---|---|---|
| SearchQA | 1,300 | 3,850 | D8 |
| OfficeQA | 4,830 | 8,200-8,856 | this pilot (P / O_home), D8 |
| LiveMath | 1,520 | 4,410 | D8 |
| generated OfficeQA-style | 670 | 1,294 | this pilot; plus 2,670 GLM tokens per kept item |

| guard design (per guarded rule; the parent arm costs the same once per step) | scaffold parent | seeded parent |
|---|---|---|
| LiveMath 60 x 2 single look | 0.18M | 0.53M |
| LiveMath two looks (mean 80-100 items) | 0.24-0.30M | 0.71-0.88M |
| SearchQA 120 x 2 | 0.31M | 0.92M |
| OfficeQA 74 x 1 | 0.36M | 0.61M |
| OfficeQA 74 x 2 | 0.71M | 1.21M |
| generated 60 x 2 (gross-harm screen) | 0.08M (+0.16M generation per step) | 0.16M (+0.16M) |

- Per step with C1-first sequencing and a seeded parent: 0 when no rule passes A_S; with 1-2 passers about
  **2.4-3.6M** for an OfficeQA guard (parent 1.21M + 1.21M per passer) or **1.1-1.6M** for a LiveMath guard.
- Without C1-first, 5 rules per step: about 7.3M (OfficeQA) or 3.2M (LiveMath).
- Compare: v3 screen and confirm rounds cost 1.2-7.4M each on the QA benchmarks (D8 §2.6).

## 10. Risks and limits

1. **Low power for moderate harm** (-3 to -5 points) per rule, under any affordable design. The per-rule guard is a
   gross-harm screen; the "no drop" claim must be made at the version level.
2. **Moot until rules pass at home:** on v3's data E9 changes nothing (0 rules accepted). Its value depends on v4/v5
   (D1, D4, D8, D13) producing A_S passers.
3. **OfficeQA session effects** (11-point session SD for the seeded parent): decisions are valid only interleaved
   within one window. Cross-window replication on R was good here, but that is only 3 texts and 2 windows.
4. **λ for the generated panel rests on 3 texts x 2 windows**, with no rule-like text among them. Seeds are whole
   sections, larger than a 600-character rule. Rule-sized effects on G may be fully absorbed by saturation.
5. **A guard on one target does not protect another** (§3.2). Guarding on OfficeQA does not certify LiveMath.
6. **Using target training items changes the claim** ("guarded") and, on small pools, amounts to a fixed validation
   set. The owner must decide whether that is acceptable (§11, decision 1).
7. **The pilot's generated items reuse E1's K1/K2 panels** (19 of 69). Wikipedia rate limits still apply (56 of 191
   requests retried).

## 11. Recommendation

**Owner decision 1 (needed):** is a veto-only guard on a similar target's TRAINING items acceptable, provided that
target is reported as "guarded" and the generalisation claim is made on the other targets?
- If yes: guard on OfficeQA-train (74 x 2, single look, interleaved), evolve on SearchQA, and claim on LiveMath,
  SpreadsheetBench and ALFWorld.
- If no: the only compliant proxy is a generated panel, and building a valid one (criteria in §7) comes first.

Engineering steps (for v5, after v4 lands; none needs a new paid run before the owner's decision):
1. Apply the guard to **every** rule, not only `similar`-placed ones (S_home-type bleed, §3.1). Replace C4'
   `sum >= 0` on 8-12 items with the §4.4 veto. Keep C1-first sequencing.
2. Implement the firewall (§6.1-6.2) as assertions, in the same style as the test refusal in `data.py`.
3. Add V_G (§4.5) as a 1% gross-harm screen on fresh generated items. Treat the generator's validity criteria (§7) as
   its fitness: this is the co-evolution measurement for purpose 1.
4. Report: per target, test-split paired CIs with "guarded / unguarded" labels; never the guard panel's own numbers.
5. Next pilot, if wanted (about 3-4M tokens): repeat §3.1 with **rule-sized** texts. Use the 2 v3 screen passers, the
   cand text, and 3 placebos. Use a **difficulty-calibrated** generated panel: generate about 150 items and keep those
   the parent fails at least once in a separate calibration run, then re-measure fresh. This measures λ for rules,
   not seeds.

## 12. References
- Dwork, Feldman, Hardt, Pitassi, Reingold, Roth. "The reusable holdout: Preserving validity in adaptive data
  analysis." Science 349(6248), 2015. Thresholdout: adaptive reuse of a holdout via thresholded answers.
- Blum, Hardt. "The Ladder: A Reliable Leaderboard for Machine Learning Competitions." ICML 2015. Release a new score
  only when it beats the previous one by a margin.
- Schuirmann 1987 (one-sided tests) and the FDA 2016 non-inferiority guidance: margins, as used by D8 §4.4.
- Holm 1979 (step-down multiplicity), as used by D8 §4.6.
- Internal: D6 report §0, §7-8 (about 200 generated items per target-step; panel-validity study); D8 report §2.6,
  §4.4-4.6 (margins, C4' power, costs); E1 report §0 and §7.2 (version-0 generated OfficeQA items saturated, 20 of
  23); E2 placement records; D12 working data `power_items.json` (session SD); cal-1 registration
  (`docs/handoff/cal1-registration-20261020.md`, arms table).

## 13. Artifacts and commands

New machine `/data/feasibility/E9/`:
- `pilot/`: `plan.json`, `summary.json`, `ledger-generation.json`, `items_generated.json`, `gen/K3..K8`,
  `cells/{G,R}/<arm>/run<k>/<item>.json`;
- `pilot-run.log`;
- `proxy_analysis.json` and `proxy_analysis.log`;
- `target_components.json`, `v3_proposals.json`, `task_cards.json`;
- `scripts/`: `e9_proxy_pilot.py`, `e9_proxy_analyse.py`, `e9_target_components.py`, `e9_v3_proposals.py`,
  `e9_pool_sizes.py`, `e9_proxy_power.py`.

Mac `scratchpad/feas/E9/`:
- `report.md`;
- `data/`: `cal1_cells_complete.tsv` (8,800 cells), `guard_oc.json`, `decision_numbers.json`, `proxy_analysis.json`,
  `proxy_analysis.log`, `proxy_power.txt`, `target_components.json`, `v3_proposals.json`, `task_cards.json`, plus the
  pilot's `plan.json`, `summary.json` and `ledger-generation.json`;
- `scripts/`: all of the above plus `e9_extract_cal1.py`, `e9_guard_oc.py`, `e9_decision_numbers.py`,
  `e9_restatement.py`.

Commands:
- Pilot: `e9_proxy_pilot.py check | generate | solve [--retry-unknown] | all`, run on the new machine with
  `proxy_on`; the log is `pilot-run.log`.
- Analysis (free):
  `ssh <datatools-login> "cd /data/feasibility/E9 && /root/continual-alf-prep-20260928/env/bin/python -I scripts/e9_proxy_analyse.py /data/feasibility/E9/proxy_analysis.json"`.
- Power tables (free, local): `python3 -I scratchpad/feas/E9/scripts/e9_proxy_power.py`.
