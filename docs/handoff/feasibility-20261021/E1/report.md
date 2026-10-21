# E1 -- Verifier-side rubric co-evolution: text rubric and executable "coding rubric"

Explorer report, 2026-10-21. Direction E1 of the second feasibility batch.
Serves **purpose 1** (the verification side co-evolves with the Skill and its evolution shows up as generated test items
that measure generalisation better and better, feeding back what is learnable). It touches **purpose 2** (evolve on one
benchmark, evaluate on the others) only through the predictiveness fitness F3 (section 3), which must stay post hoc on
the target benchmarks.

Labels used throughout: **[measured]** = computed in this exploration from data or from a paid pilot, with denominators;
**[verified]** = read in the code, the registration documents or the cited paper; **[estimate]** = my projection;
**[claim]** = what a paper reports, not reproduced here.

Hard rules kept: no test/holdout pool was read (only the registered training pools = historical train + val, and the
v3 train cells); no credential was printed; nothing in the repository or in a completed run directory was modified;
all scripts and outputs are under `/data/feasibility/E1/` on the new machine (and `/data/feasibility-scratch/E1/` on
the old one for the cal-1 read).

---

## 0. Bottom line

1. **The executable reading used as a reference-free verifier of real replies does not work beyond form checks.**
   [measured, pilot 2] Ten checks per seed were derived by GLM-5.3 from training failures (3 seeds per benchmark,
   30 checks per benchmark, all ten loaded and ran in 5 of 6 seeds without repair). On the held-out half of the items
   the selected checks reached balanced accuracy (BA) 0.487-0.539 on SearchQA and 0.474-0.548 on OfficeQA, no better
   than the frozen v3 library checks (0.512-0.653) and below the v3 text judge (SearchQA 0.546-0.570, OfficeQA
   0.740-0.842). The single round of evidence-driven revision (v0 -> v1) was never accepted (BA gain 0.000-0.013 on
   the derivation half against the registered +0.05). What transfers to held-out items is form/consistency
   (answer is a sentence, lists alternatives, has a parenthetical alias, carries a percent sign, a month-year instead of
   a number); content failures (wrong candidate, wrong row, wrong method -- the majority) are invisible without the
   reference.
2. **On training items a reference-free verifier is not needed**: the official scorer with the reference exists there.
   The verification side has real work only where no reference exists: **generated items**. There, code is the right
   reading -- but on the *item* side (an exact answer computed by the program, validity checks, independent check
   formula, exact-match scoring), which `skillopt/coevo5/forward.py` already implements and which had **never run** in
   any coevo5 run before this exploration.
3. **Text criteria should drive *what* is generated; executable item specs should guarantee *that it is right*.**
   The promising rubric object is a "criterion card" = criterion text + item style/spec + host validity checks +
   scorer + fitness record. The text part evolves; the code part is host-fixed (model-written item checks admitted only
   through Code-as-Task style tests with known failure cases).
4. **Fitness = discrimination between solver configurations on fresh generated items** (F2), with validity (F1) as a
   constraint and predictiveness of real transfer (F3) as the post-hoc yardstick. Update = one rewrite per
   low-fitness criterion, accepted only on fresh items generated in the same round for both versions.
5. **Generated items, version 0, are valid but too easy and do not separate Skills on content** [measured, pilots 3
   and 3b, first ever run of the forward machinery]: 23 kept items (of 36 generated), solved 4 times each (S+ = I-ds
   start Skill, S- = E-ds scaffold, 2 runs each): 20 saturated, 1 dead (an invalid item the checks missed), 2 mixed;
   the single item that separates the two Skills does so through a percent sign (answer form); counting form failures
   as passes, 0 of 23 items discriminate. Real OfficeQA training items under the same pair are the opposite: 45 of 70
   dead, 11 saturated, 3 fully separating. ~2.4k GLM tokens per kept item, ~1.9k deepseek tokens per solved cell.
6. Feasibility **medium**: the machinery exists and is cheap per item; the open risks are saturation of generated
   items, the Wikipedia rate limit through the shared gateway (57 of 69 searches returned HTTP 429 in pilot 3), and
   whether discrimination on generated items predicts transfer on real items (not yet measured anywhere).

---

## 1. What exists today (inventory, verified against code and data)

### 1.1 The v3 examiner rubric (reading (a) with a fixed (b) library)

[verified] `skillopt/coevo5/examiner.py`, `checks.py`, `protocol.py` (RUBRIC_* constants), registration §6 and v3
delta §5-§8:

- A per-benchmark rubric of items `{id, text (<= 450 chars), check (optional, from a fixed host library), basis}`
  plus a fixed general rubric. Library (`checks.py`): `answer_tag_present`, `answer_single_letter`,
  `answer_pure_number(allow_percent)`, `answer_no_percent`, `answer_no_letters`, `answer_max_words(n 1-50)`,
  `code_present`.
- The judge (GLM-5.3) sees the question, the public context and the reply, **never the reference**. Host checks run
  first.
- Revision: at most 3 edits built from <= 20 proposal-half disagreements; accepted only if BA on a selection panel of
  the check half (<= 20 pass + <= 20 fail, minority >= 8) rises by >= 0.05 and correct verdicts by >= 2. The revised
  rubric is used only for that stage's diagnosis (failure codes for the analyst).
- **No model-written code is ever executed.**
- Diagnosis order: decision table -> format checks -> LiveMath table codes -> GLM picks a frozen TAXONOMY code (this
  call does see the reference).

[measured, free, v3 train cells] How the v3 judge did on the training cells it judged (failures caught / passes
wrongly flagged):

| Benchmark | I-ds chain | E-ds chain |
|---|---|---|
| SearchQA | 7/87 caught, 7/310 flagged (recall 8%) | 15/103, 7/297 |
| OfficeQA | 92/108, 7/37 | 111/117, 7/30 |
| LiveMath | 5/133, 2/66 | 11/125, 4/75 |
| SpreadsheetBench | 23/36, 8/47 | 23/37, 9/46 |

[measured, free] v3 revisions over the 8 revisable stages: 2 accepted, 3 rejected, 1 insufficient panel, 2 with no
valid edit.

| Stage | Outcome |
|---|---|
| I-ds s1 SearchQA | rejected (BA 11/20 -> 23/40, +1 correct) |
| I-ds s2 OfficeQA | rejected (293/360 -> 38/45, +0); one proposed item: "The numeric value inside the answer tag matches the reference value exactly" |
| I-ds s3 LiveMath | **accepted** (1/2 -> 58/85, +8); the added item "The selected letter matches the reference (correct) answer" cannot be applied by a judge that never sees the reference |
| I-ds s4 SpreadsheetBench | no valid edits |
| E-ds s1 SearchQA | accepted (11/20 -> 13/20, +4) |
| E-ds s2 OfficeQA | insufficient panel |
| E-ds s3 LiveMath | rejected |
| E-ds s4 SpreadsheetBench | no valid edits |

Lesson [measured]: when the revision is scored by agreement with the official verdict, the reviser drifts towards
"matches the reference" items (EvalGen's criteria drift). Such an item can only raise BA by turning the judge into a
second solver -- the gain then measures the judge's own solving, not the rubric.

[measured, free] Cost of the v3 verification roles per stage (I-ds): judge SearchQA 453 sends, 845,041 tokens
(~1,865 per call); OfficeQA 153 sends, 640,816 tokens (~4,188 per call); one revise call 15-25k tokens; analyst
34-82k per call. An executable check costs 0 model calls at use; deriving 10 checks cost ~30-50k tokens (SearchQA) or
~94k (OfficeQA) per call.

### 1.2 Forward items (the item-side code that already exists)

[verified] `skillopt/coevo5/forward.py`, `research.py`, registration §7-§8:

- OfficeQA style: a numeric Wikipedia table (2-60 rows, 2-15 columns) fetched through the frozen API parameters; the
  generator writes `{question, formula, decimals, answer}`; the formula may use only number literals copied from
  table cells and a fixed grammar; exact rational `evaluate`; rounding half away from zero; the answer must equal the
  rounded formula value; then an **independent check call** writes its own formula from the table and question, and
  the item is kept only if both round to the same answer.
- LiveMath style: five exact options; the formula's value equals exactly one option; a yes/no check call.
- A panel per (rule, target): at most 5 rounds x 3 items, kept 8-12; identity = hash of normalised material + question.
- Research (`material`): per round one request of at most 3 rounds of query/pick/conclude (<= 8 calls, <= 3 pages).
- [verified] **Never exercised before this exploration**: `docs/handoff/coevo5-midrun-analysis-20261019.md` line 167
  ("所以前向题一道没出" -- not a single forward item was produced in v1), and the v3 run has no forward record
  (the analyst never chose the similar placement).

### 1.3 The earlier line (continual_learning)

[verified] `skillopt/continual_learning/verifier.py` ("rubric-probe-research-verifier-v7") and `feedback.py`: a
seven-field domain policy; probes (BigCodeBench executable; QA/KOR/OfficeQA/LiveMath judged by a model without a
reference); calibration against the host audit (>= 1 detection, false-rejection rate <= 0.25); research only for
BigCodeBench.

[verified, docs/results-and-lessons.md 10/14-10/15 and docs/handoff/rubric-*-2026101[45].md] Earlier rubric results:
default text rubric detection OfficeQA 0-4 of 20, SearchQA 0-3 of 21, LiveMath 0 of 80; host format checks on
OfficeQA precision 0.98, recall 0.22; rubric-form study (OfficeQA, 6 blocks x 124 = 744 positions) format_code -
format_text [+12, +1, -6, +12, -7, -10], p = 0.97; global_text - default [+3, +5, 0, +6, +1, +18], p = 0.062; binding
study undeterminable (same-input proposal noise median |diff| 6 of 124); solve-time executable rubric P1 +2.7
[-7.8, +13.4]; 124 generated OfficeQA items over 12 parent runs: 48% always pass, 49% flip, 2% always fail, parent
pass rate 0.77 on generated vs 0.58-0.61 on real items; SearchQA 168 generated items 89% pass on both runs.

---

## 2. The rubric artifact in two readings

| | (a) Text criteria | (b) Executable checks |
|---|---|---|
| Judge real replies without reference | v3 judge: OfficeQA BA 0.74-0.84, SearchQA 0.55-0.57 [measured]; ~1.9-4.2k tokens per call | form checks only; derived checks held-out BA 0.47-0.55 [measured]; free at use |
| Judge training replies | unnecessary: the official scorer has the reference | unnecessary |
| Decide *what* to generate | **natural** (the forward generator's `topic`) | awkward (code cannot say what situation matters) |
| Guarantee a generated item is right | weak (a model's yes/no) | **strong** (exact arithmetic, literals from the table, independent formula) |
| Score generated items | weak | **exact match on a program-computed answer** |
| Diagnose failures cheaply | GLM picks a code (~2-7k tokens per failure) | deterministic form codes (D3 SearchQA, D4 OfficeQA) |

**Proposed artifact: the criterion card.**

```
criterion card = {
  id, version, parent,
  text:        the situation to test, <= 600 chars, one block (drives generation; doubles as a judge item);
  target:      the generated style (officeqa | livemath), i.e. a similar benchmark not yet learned;
  spec:        the item contract of forward.py (material kind, answer type, formula grammar, rounding);
  validity:    host checks (evaluate, literals-in-table, answer == rounded(formula), independent check formula);
               optional model-written item checks admitted only if they pass a Code-as-Task test:
               the example solution passes and every listed failure case fails;
  scorer:      the official scorer of the style (normalised exact match on the last answer tag);
  evidence:    F1/F2/F3 with denominators, item ids, round, the Skill pair used;
}
```

**Which reading is more promising for purpose 1:** the *combination*, with the roles split: text evolves (it says
which situations the next items must exercise), code is fixed on the item side (it makes every generated item correct
and scorable). The executable "coding rubric" as a reference-free judge of replies should stay a frozen form library
-- pilot 2 shows the model cannot write content checks that generalise, and on training items the reference makes
them unnecessary.

---

## 3. Fitness

Notation: a criterion c yields items i in I_c; each item is solved under two solver configurations S+ (the more
skilled, e.g. the current Skill S_t) and S- (the less skilled, e.g. the previous Skill S_{t-1} or the empty scaffold),
m runs each; p_i(S) = share of runs that pass under the official scorer; p_i = pooled share over the 2m cells.

**F1 -- validity** (precondition). V_c = kept / generated, with the drop reasons of `forward.DROPS`. For reply-side
checks: item-level precision on fresh items, counted by distinct items (>= 3 items), never by rows.

**F2 -- discrimination** (the fitness that drives evolution).
- d_i = p_i(S+) - p_i(S-), computed on **content-only** outcomes: a cell whose only fault is answer form (its answer
  number equals the reference once %, separators and words are removed) counts as a pass. Pilot 3b is the reason: the
  only separation between the two Skills on version-0 items was a percent sign, and a writing-form effect is not
  learned transfer (v1 results).
- Primary fitness of a criterion: D_c = mean of d_i over its fresh items -- 0 under the null at any difficulty, so a
  rewrite cannot gain by merely moving items to mid difficulty.
- Secondary: the null-corrected share of discriminating items, (#{i: d_i >= delta} - E_null(c)) / |I_c|, with
  delta = 1/2 at m = 4 and E_null(c) = sum_i P(d_i >= delta | k_i) under random reassignment of item i's 2m cells to
  the two arms (exact or by permutation). With m = 2 an item with k = 1 or 3 passes of 4 has |d| = 1/2 with
  probability 1 under the null and an item with k = 2 has |d| = 1 with probability 1/3, so "|d| >= 1/2" carries no
  information at m = 2.
- Auxiliary per item: R-Zero uncertainty u_i = 1 - 2|p_i - 1/2| [verified, R-Zero 2508.05004]; Absolute-Zero
  learnability l_i = 0 if p_i(S-) in {0, 1} else 1 - p_i(S-) [verified, AZR 2505.03335]; R-Zero's repetition penalty
  lambda * |C_k| / B over near-duplicate clusters (BLEU >= 0.5), because the forward identity hash catches only exact
  duplicates.
- Saturated (all 2m pass) and dead (all fail) items carry no information about either Skill.

**F3 -- predictiveness of transfer** (the purpose-2 yardstick). For K Skill variants v_1..v_K, the rank agreement
(Kendall tau / BenchBench-style agreement [verified, 2407.13696]) between their scores on the generated suite of
style T and on the real items of benchmark T. In-loop F3 may use only the **source** benchmark's own style (or its
training pool); on targets it is post hoc only, otherwise the "evolve on one, evaluate on the others" protocol leaks.

---

## 4. Update rule from evidence

1. After a round, every criterion with D_c below its threshold (or V_c below its floor) gets **one** rewrite call
   (GLM-5.3): input = criterion text, its items with per-arm outcomes (S+ and S- replies, pass/fail), its F1/F2
   numbers, the saturated and dead items marked as such; output = a new text (<= 600 chars). Nothing about test items
   or benchmark identities enters.
2. **Acceptance on fresh items only.** In the next round both v0 and v1 generate fresh items (fresh material requests,
   same budget), paired by criterion; v1 is accepted iff D(v1) - D(v0) >= 0.10 with an item-bootstrap (clustered by
   source table) 90% lower bound > 0, and V(v1) >= V(v0) - 0.10. Never score v1 on the items that motivated the
   revision -- pilot 2 shows why: the selected checks had in-sample BA 0.566-0.630 and held-out 0.487-0.539.
3. Retention (DR Tulu / RLER style [verified, 2511.19399]): keep a buffer of items with d_i != 0 and drop
   zero-variance items; items that S+ fails but some variant passes are exported to the analyst as "learnable"
   evidence (the co-evolution link to the Skill side).
4. Reply-side checks: frozen library; a model-derived form check is admitted only if on fresh items it fires on >= 3
   distinct failing items with item-level precision lower bound above the base fail rate.

---

## 5. Minimal v5 loop

| Step | Input | Output | Cost driver [measured unit costs] |
|---|---|---|---|
| R1 generate | criterion cards (initially phrased from the *source* benchmark's frequent TAXONOMY codes), target style | <= 12 valid items per card (forward.build_panel + research.material, paced client) | GLM: 2.4k tokens per kept item (pilot 3b; 5.3k in pilot 3 with its failed rounds) |
| R2 solve | items; S+ = S_t, S- = S_{t-1} (or the scaffold); m = 4 runs per arm | per-item d_i, F1, F2 (content-only and official) | deepseek: 1.89k tokens per cell (173,702 tokens / 92 cells, pilots 3 + 3b) -> ~15k per item at m = 4 |
| R3 revise and test | low-fitness cards | v1 cards; fresh v0 and v1 items; accept/reject (section 4) | one rewrite call (~15-25k) per card + R1 + R2 again |
| R4 export | accepted cards; discriminating and learnable items | analyst evidence for the next Skill step | free |

Per learning step with 3 cards and 1 target [estimate]: R1 36 items x 2.4k GLM = ~0.09M; R2 36 x 8 cells x 1.9k =
~0.55M; R3 fresh v0 and v1 = ~1.28M plus 3 rewrites ~0.06M; total **~2.0M tokens per step and target**, about 2.4
times the v3 judge's SearchQA cost per stage (845k), dominated by solving and linear in m.

Acceptance of a rubric change = section 4 point 2. A rubric change never changes the Skill directly; it changes which
items the next step's analyst sees.

Fixes needed before the loop can run [measured in pilots 3/3b]: a new research-client version with request pacing
and HTTP 429 retries; semantic de-duplication and a per-table cap; one extra check that the question asks for exactly
one quantity (item K1:5 passed exact arithmetic and the independent check although it asks for two).

---

## 6. The smallest experiment that shows the rubric side improves (E1-X)

Design (OfficeQA style, one round of fitness feedback; everything below pre-registered before launch):

- Criteria: 4 cards phrased from OfficeQA TAXONOMY D1 (wrong data), D2 (wrong method), D3 (calculation slip),
  D4 (answer form).
- Skill pair: S+ = the I-ds start Skill (12,648 chars; its OfficeQA section gives row/column, units, signs and format
  guidance), S- = the E-ds scaffold (593 chars, headings only). They differ on real items (SearchQA 198 items: abs(d)
  = 1 on 8 items vs 3.0 expected under the null, permutation p = 0.0007; OfficeQA 70 items: 3 vs 1.33, p = 0.11; after
  counting form failures as passes 2 vs 1.0, p = 0.26) [measured, free]. Optional guard against the rubric learning one
  Skill's quirks: score round 1 also with a second pair not used in round 0 (e.g. S+ plus one v3 candidate rule vs S+).
- Round 0: v0 cards, 12 items each (48), m = 4 -> F2 per card -> one rewrite per card.
- Round 1: fresh items for v0 **and** v1, 15 per card each (60 + 60), m = 4.
- **Primary end point**: content-only mean d (form failures counted as passes) of v1-fresh minus v0-fresh, item
  bootstrap clustered by source table; success if the difference is >= 0.10 with a 95% interval excluding 0 **and**
  validity (kept / generated) does not fall by more than 0.10. Mean d is used rather than the share of discriminating
  items because the chance rate of "d >= 1/2" rises steeply as items move to mid difficulty (at a pass probability
  of 1/2, d >= 1/2 happens by chance in 31% of null items with two runs per arm and 15% with four), whereas the mean of d is 0 under the null
  at any difficulty.
- Secondary: null-corrected share of discriminating items (section 3); official-score mean d; saturation and dead
  shares; per-card acceptance under section 4.

Cost [estimate from the measured unit costs]: generation 168 items x 2.4k GLM = ~0.4M plus 4 rewrite calls ~0.1M;
solving 168 x 8 cells x 1.9k = ~2.6M deepseek; total **~3.1M tokens**; wall time ~2-3 h at concurrency 6 (pilot 3b:
generation ~5 min per pair of panels; solving slowed by the shared route's rate limits, median 9 s and maximum 304 s
per call).

Power [estimate]: v0's content-only mean d was 0.000 on 23 pilot items (all saturated or dead), so the comparison is
essentially v1 against 0. If v1 reaches mean d = 0.10 with a per-item SD of 0.30 (real OfficeQA items: SD ~0.28 at
m = 2), SE = 0.30 / sqrt(60) = 0.039, z = 2.6, power ~0.73 at alpha 0.05 two-sided; n = 84 per arm gives ~0.86.
For the secondary share end point, exact one-sided Fisher tests at alpha 0.025 (4,000 simulated replications,
independent items): v0 rate 0 vs v1 0.15 -> power 0.90 (n = 60) / 0.99 (n = 84); 0.02 vs 0.15 -> 0.65 / 0.85;
0.05 vs 0.20 -> 0.63 / 0.81. Clustering by table (3 items per generation call share a table; intraclass correlation
0.2 gives a design effect 1.4) makes n = 84 behave like ~60 independent items.

**What E1-X does not show:** that items which separate S+ from S- predict transfer on real benchmarks (F3). That
needs E1-Y: K >= 6 Skill variants (cal-1 arms, chain checkpoints) scored on the real OfficeQA training pool (74 items x
2 runs x ~6.3k tokens = ~0.93M per variant [measured mean cell size of the v3 OfficeQA train cells]) and on the
generated suite; Kendall tau between the two rankings. ~6-7M tokens. Only E1-Y addresses purpose 2.

---

## 7. Pilots and free analyses (all measured)

Models: GLM-5.3 (thinking enabled, reasoning low, temperature 0) for every method role; deepseek-v4-flash (pjlab_token
route, thinking disabled, temperature 0, max_tokens 32768) as solver -- the v3 run's settings. Data: the registered
training pools only (SearchQA 600 = historical 400 panel + 200 val; OfficeQA 74 = 50 dev + 24 val) and the v3 train
cells. Before use, every joined cell was re-scored with `skillopt.continual_eval.backends.score`: all decided rows
match (SearchQA I-ds 310 pass / 87 fail + 3 no-reply; E-ds 297 / 103; OfficeQA I-ds 37 / 108 + 3; E-ds 30 / 117 + 1).

### 7.1 Pilot 2 -- executable checks derived from training failures (the task's requested pilot)

Script `/data/feasibility/E1/scripts/e1_pilot.py`, post-analysis `e1_post.py`; outputs
`/data/feasibility/E1/pilot2/<bench>/{split.json, summary.json, post.json, seedN/}`.

Design (fixed before the run):
- Split: items hashed (seed 20261020) into a derivation half and an evaluation half (SearchQA 100/100 items, OfficeQA
  37/37 items); all rows of an item stay together.
- Derivation, per seed (3 seeds): one GLM call shown 24 failed and 8 passed derivation-half I-ds replies (failures
  round-robin over their diagnosis codes; question, clipped context, reply, answer tag, reference, verdict, code) and
  asked for 10 Python checks `check(question, context, reply, answer) -> bool` that must not use the reference.
  Validation: AST allow-list (re, math, fractions, statistics, datetime, json, string, collections, itertools,
  unicodedata, decimal, difflib), forbidden names/underscore attributes; execution in a separate `python -I -S`
  process (RLIMIT_AS 2 GB, 0.5 s per call); one repair call if a check fails to load or raises on > 10% of rows.
- Selection: tp >= 3 on the derivation half and one-sided 90% Wilson lower bound of precision above the derivation
  base fail rate.
- Revision v1: one GLM call shown each check's derivation statistics, 3 false positives per check and 12 missed
  failures; accepted iff derivation-half BA gain >= 0.05 and >= 2 more correct verdicts.
- Evaluation: the held-out half, on the I-ds rows (same solver configuration) and on the E-ds rows (another Skill).
- Baselines on the same rows: the frozen library checks of the v3 rubric (SearchQA: answer_tag_present,
  answer_max_words(10), answer_no_percent; OfficeQA: answer_tag_present, answer_pure_number(allow_percent),
  answer_no_percent); the v3 GLM text judge's verdicts; judge OR checks. Intervals: item-cluster bootstrap, 2,000
  resamples.
- Cost: SearchQA 167,251 GLM tokens, OfficeQA 451,347; **618,598 in total; every call ok**; 30 checks per benchmark
  loaded and ran (one OfficeQA seed needed its single repair call).

Results, held-out half. SearchQA eval-I-ds = 198 rows, 41 failures on 25 items; eval-E-ds = 200 rows, 48 failures on
25 items.

| SearchQA classifier | eval-I-ds tp/fp, recall, BA [95% CI] | eval-E-ds tp/fp, BA |
|---|---|---|
| Library checks (frozen) | 1/0, 0.024, 0.512 [0.500, 0.546] | 2/1, 0.518 |
| v3 text judge | 6/1, 0.146, 0.570 [0.522, 0.629], kappa 0.20 | 5/2, 0.546 |
| Selected derived checks v0, seeds 1/2/3 | 3/1, 0/0, 0/4 -> BA 0.533, 0.500, 0.487 | 5/4, 2/0, 2/2 -> 0.539, 0.521, 0.514 |
| Selected derived checks v1, seeds 1/2/3 | 1/0, 0/0, 2/6 -> 0.512, 0.500, 0.505 | 2/2, 0/0, 4/6 -> 0.514, 0.500, 0.522 |
| Union of all 30 v0 checks | 7/46 (precision 0.13 < base 0.21), BA 0.439 [0.359, 0.534] | 15/46, 0.505 |
| Union of all 30 v1 checks | 6/12, BA 0.535 [0.465, 0.622] | 9/15, 0.544 |
| Judge OR v1 union | 10/13, BA 0.581 | 11/15, 0.565 |

In-sample (derivation half, 199 rows) the selected unions had BA 0.566-0.630: the drop to 0.49-0.54 held out is the
selection effect. Revision acceptance: BA gain +0.013, +0.007, 0.000 -> **none accepted**.

OfficeQA eval-I-ds = 72 rows, 59 failures on 31 items; eval-E-ds = 73 rows, 63 failures on 33 items.

| OfficeQA classifier | eval-I-ds | eval-E-ds |
|---|---|---|
| Library checks (frozen) | 18/0, recall 0.305, BA 0.653 [0.571, 0.737]; hits on 9 items | 25/1, BA 0.648 |
| v3 text judge | 51/5, recall 0.864, specificity 0.615, BA 0.740 [0.536, 0.932], kappa 0.44; 28 of 31 failing items | 62/3, BA 0.842, kappa 0.75 |
| Selected derived checks (v0 = v1), seeds 1/2/3 | 1 / 0 / 1 checks kept: BA 0.534, 0.500, 0.508 | 0.474, 0.500, 0.548 |
| Union of all 30 v0 checks | 15/2, precision 0.88, recall 0.25, BA 0.550 [0.392, 0.661]; 9 items | 17/1, BA 0.585 [0.425, 0.687] |
| Judge OR v0 union | 53/6, BA 0.718 | 62/3, BA 0.842 (= judge alone) |

Revision acceptance: BA gain 0.000 in all three seeds -> none accepted; v1 changed almost nothing.

Which checks hold up on held-out items (tp/fp on eval-I-ds and eval-E-ds): OfficeQA `month_and_year_answer` 4/0 and
4/0, `percent_sign` 4/0 and 3/1, `binary_op_arithmetic` 4/2, `suspicious_zero` 1/0 and 6/0; SearchQA
`parenthetical_alias` (E-ds 5/0), `answer_is_sentence` 1/0 and 3/0, `multiple_alternatives` (E-ds 6/2). Checks keyed
to item quirks only misfire: `recurring_collocate` 0/33 and 0/31, `plural_for_this_clue` 0/4, `blank_fill_ampersand`
0/2. Recall by failure code (v0 union, eval-I-ds): SearchQA D1 5/16, D2 0/10, D4 2/8, D5 0/7; OfficeQA D1 8/18,
D2 3/23, D3 2/8, D4 0/4, D5 1/5.

Reading: a reference-free executable check can see only the *form* of a reply; the failures that matter on these
benchmarks are content failures (wrong candidate D4, wrong data D1, wrong method D2), which no reference-free check
found at useful recall. The selection rule (registered before the run) was too strict for OfficeQA (base fail rate
0.671) and counted rows rather than items; the corrected design counts distinct items (section 4 point 4).

### 7.2 Pilot 3 and 3b -- generated OfficeQA-style items, version 0 (purpose 1's measuring instrument)

Scripts `/data/feasibility/E1/scripts/e1_forward_pilot.py` (pilot 3) and `e1_forward_pilot_b.py` (pilot 3b),
post-analysis `e1_forward_post.py`; outputs `/data/feasibility/E1/pilot3/` and `/data/feasibility/E1/pilot3b/`
(panels with every role call, archived Wikipedia sources, one JSON per solved cell, `analysis.json`, `ledger.json`,
`post.json`). The design is fixed in the script header before launch.

Design.
- Two criteria phrased as guidance rules from the frozen OfficeQA taxonomy (rubric reading (a)):
  K1 from D1 "wrong data" (locate each value by matching row label and column heading; a neighbouring year, a
  similarly named category or a subtotal row is a plausible wrong value); K2 from D2 "wrong method" (compute exactly
  the derived quantity asked: change vs level, ratio of totals vs average of ratios, share of the stated total,
  average over exactly the stated periods). Both mention public-finance statistics so that the material search finds
  tables close to OfficeQA's Treasury documents.
- One panel per criterion through the **unchanged** `forward.build_panel` with `research.material` as the per-round
  material request (protocol constants: <= 5 rounds x 3 items, <= 12 kept; English Wikipedia through the explicit
  gateway; no archive), GLM-5.3 at the protocol's role settings (max_tokens 16,384).
- Each kept item solved by deepseek-v4-flash under S+ = the I-ds start Skill and S- = the E-ds scaffold, runs 0 and
  1 (4 cells per item), scored by `backends.score('officeqa')`. The Skill digests were checked against the v3 train
  cells, so the generated items and the real items of 7.3 are solved by exactly the same configurations.
- Pilot 3b = pilot 3 with one deviation, decided after pilot 3 lost most searches to HTTP 429: every Wikipedia
  request passes one process-wide lock, >= 2 s apart, and a 429 is retried after 15, 30, 60 and 120 s (frozen
  request parameters and User-Agent unchanged).

Generation [measured]:

| | Pilot 3 (protocol client) | Pilot 3b (paced client) |
|---|---|---|
| Wikipedia | 69 searches, **57 HTTP 429** (83%) | 53 requests, 8 retried after a 429, 0 lost |
| Material requests (one per round) | 10 -> 3 tables | 10 -> 10 tables |
| Items generated | 6 (one generation reply invalid: a list of more than 3 items) | 30 |
| Kept (exact-arithmetic valid and independently checked) | 4 (K1 3, K2 1) | 19 (K1 12, K2 7) |
| Dropped | answer_mismatch 2 | K1: check_mismatch 2, panel_full 1; K2: literal_not_in_table 4, answer_mismatch 3, check_literal_not_in_table 1 |
| Panels | both short (< 8 items) | K1 full (12); K2 short (7) |
| GLM-5.3 | 21,327 tokens, 40 calls | 46,284 tokens, 62 calls (~2.4k per kept item) |
| Wall time of generation | 66 s and 57 s | 159 s and 298 s |

Validity yield in pilot 3b: K1 12 of the 14 evaluated items survived both the program's checks and the independent
check call (86%; a 15th arrived after the panel was full); K2 7 of 15 (47%), the losses being formulas with numbers
not in the table (4), answers not equal to the formula (3) and a check formula with a number not in the table (1).
Of the 23 kept items, one (K1:5, below) is nevertheless invalid: 22 of 23 valid on reading.

What the items look like (all 23 kept items read): almost all are **one subtraction of two cells** of the same table
("By how many percentage points did debt held by the public as a percentage of GDP in 2020 exceed the 2018 value?" ->
100.3 - 77.6 = 22.7); K2 adds a few one-step ratios ("ratio of China's budget (PPP) to the United States' budget",
8761782 / 9818534 = 0.892) and one ratio of sums. Tables: United States federal budget (several revisions/pages),
National debt of the United States, List of countries by government budget. The same quantity recurs across criteria
and rounds (23 kept items carry only 20 distinct (answer, literals) pairs: "outlays minus revenue in 2020 = 14.9" in pilot 3 and again in pilot 3b, and "debt held by the public, 2020 minus 2019 = 20.9" three times in pilot 3b, under both criteria; the identity hash (material + question wording) catches none of them).

Solving [measured]:

| Items (2 runs per arm) | items | pass S+ / S- | saturated (4 of 4 pass) | dead (0 of 4) | mixed | d = +1 / d = -1 | null expectation of abs(d) = 1 | permutation p (abs(d) = 1 count) | mean d [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| Generated, pilot 3 | 4 | 1.000 / 1.000 | 4 | 0 | 0 | 0 / 0 | 0 | 1.0 | 0 |
| Generated, pilot 3b | 19 | 0.947 / 0.868 | 16 | 1 | 2 | 1 / 0 | 0.33 | 0.33 | +0.079 [0.000, +0.211] |
| Generated, pooled | 23 | 0.957 / 0.891 | 20 | 1 | 2 | 1 / 0 | 0.33 | 0.34 | +0.065 [0.000, +0.174] |
| Generated, pooled, form failures counted as passes | 23 | 0.957 / 0.957 | 22 | 1 | 0 | 0 / 0 | 0 | 1.0 | 0 |
| Real OfficeQA training items (7.3) | 70 | 0.257 / 0.214 | 11 | 45 | 14 | 3 / 0 | 1.33 | 0.11 | +0.043 [-0.021, +0.114] |
| Real OfficeQA, form failures counted as passes | 70 | 0.264 / 0.229 | 11 | 43 | 16 | 2 / 0 | 1.00 | 0.26 | +0.036 [-0.029, +0.100] |

("Form failure" = the last answer tag holds one number exactly equal to the reference once a percent sign, thousands
separators and words are removed. On the real items only 1 of 108 S+ failures and 2 of 117 S- failures are form
failures under this strict definition.)

- All 7 failing generated cells (of 92) are explained. 3 are S- answers with a percent sign ("-2.2%", "-5.5%" twice)
  to "percentage points" questions -- a form failure under exact match that the S+ OfficeQA card's format guidance
  avoids. 4 are the four cells of item K1:5, an **invalid item**: the question asks for a year *and* a difference
  ("In which year shown did Revenue as a percentage of GDP equal 16.4%, and what was Outlays in that year minus Outlays
  in the other year ...?") while the program's reference is only the difference 0.8, so every reply
  "2018 and 2019; 0.8" fails. Exact arithmetic and the independent check formula cannot see that a question asks for
  more than the formula computes.
- **On version-0 generated items the only separation between the skilled and the unskilled configuration is answer
  form; content discrimination is 0 of 23 items.** Generated items are too easy (87% saturated, pass rates 0.96 and
  0.89); real OfficeQA items are too hard for this solver (64% dead, pass rates 0.26 and 0.21); neither discriminates
  on content. This is the starting point a discrimination fitness must move, and the reason the primary end point of
  E1-X counts form failures as passes (a writing-form effect is exactly what the v1 results showed is not learned
  transfer: `docs/handoff/coevo5-v1-results-20261019.md` line 169).
- Cost: pilot 3b 46,284 GLM + 143,835 deepseek = **190,119 tokens** (76 cells, all delivered: ~1,890 tokens per cell;
  median call 9 s, maximum 304 s under the shared route's rate limits -- four other feasibility pilots were running on
  the same machine; wall time 30 min, of which generation 5 min); pilot 3: 21,327 GLM + 29,867 deepseek = **51,194 tokens**
  (16 cells).

### 7.3 Free: how real items discriminate between solver configurations

Same solver, same two Skills as pilot 3, 2 runs per arm (the v3 train cells; the Skill digests in the cells were
checked: I-ds start `ee9b737f...`, E-ds scaffold `cc516459...`). k = passes of an item's 4 cells; d = p(S+) - p(S-).

| Real items | items | pass S+ / S- | saturated k=4 | dead k=0 | mixed | d=+1 / d=-1 | null expectation of abs(d)=1 | permutation p (abs(d)=1 count) | mean d [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| OfficeQA (4 items with an unknown cell dropped) | 70 | 0.257 / 0.214 | 11 | 45 | 14 | 3 / 0 | 1.33 | 0.11 | +0.043 [-0.021, +0.114] |
| SearchQA (2 dropped) | 198 | 0.780 / 0.745 | 135 | 32 | 31 | 6 / 2 | 3.00 | 0.0007 | +0.035 [0.000, +0.071] |

80% of real OfficeQA items and 84% of real SearchQA items are dead or saturated for this Skill pair; only 3/70 and
8/198 items separate the two Skills completely.

cal-1 (old machine, SearchQA 200 training items, 11 arms, items with >= 3 runs in both arms, read-only): the
same-text null contrast parent:A vs parent:B moves 3 of 144 items by |d| >= 0.5 (2.1%; 81% have d = 0; 28 dead, 80
saturated); ids-full vs parent:A moves 20 of 140 (14.3%; 17 up, 3 down; mean d +0.084); cand vs parent:A 21 of 134
(15.7%; 6.7% up, 9.0% down; mean -0.026); seed-rule3 vs seed-only mean d -0.122 (133 items). This is the noise floor a
discrimination fitness must beat: ~2% of items move under identical text at m >= 3.

---

## 8. Literature (verified against the papers' abstracts or text; what each contributes)

Rubric as reward / checklists / validating the validators:
- Rubrics as Rewards (Gunjal et al., arXiv 2507.17746): checklist rubrics as RL rewards; [claim] up to +31% relative
  on HealthBench, +7% GPQA-Diamond. Contributes: rubric items as decomposed, weighted criteria.
- CheckEval (Lee et al., arXiv 2403.18771, EMNLP 2025): decomposed yes/no checklist questions; [claim] agreement with
  humans +0.45 on average across evaluator models. Contributes: binary items, which make agreement measurable.
- EvalGen, "Who Validates the Validators?" (Shankar et al., arXiv 2404.12272, UIST 2024): criteria drift -- the
  criteria depend on the outputs seen; assertions must be re-validated on new outputs. Matches the v3 revision drift.
- SPADE (Shankar et al., arXiv 2401.03038, PVLDB 17): assertion selection for LLM pipelines; [claim] -14% assertions,
  -21% false failures. Contributes: select assertions by coverage on failures, as in section 4 point 4.
- RLCF, "Checklists Are Better Than Reward Models" (Viswanathan et al., arXiv 2507.18624); TICK (Cook et al., arXiv
  2410.03608: [claim] exact agreement 46.4% -> 52.2% with generated checklists); OpenRubrics (arXiv 2510.07743:
  contrastive rubric generation + a preference-label-consistency filter); CheckList (Ribeiro et al., ACL 2020:
  behavioural test templates).
- DR Tulu / RLER (arXiv 2511.19399): an evolving rubric buffer per prompt; zero-variance rubrics dropped, top-K by
  reward standard deviation kept -- the retention rule of section 4 point 3.
- 2026 rubric co-evolution cluster (abstracts only, unverified beyond them): SkillRubric (NeurIPS 2026, Jiang et al.:
  actor guidance and evaluator rubric revised alternately, each frozen while the other moves), EvoRubrics 2606.23038,
  EvoLM 2605.03871, DynamicRubric 2607.20083, EvoRubric 2605.29847, Rubric-ARM 2602.01511.

Benchmarks that evolve:
- Dynabench (Kiela et al., NAACL 2021, arXiv 2104.14337): human-and-model-in-the-loop item collection; items kept when
  they fool the current model and are validated.
- AutoBencher (Li et al., arXiv 2407.08351, ICLR 2025): an LM proposes dataset descriptions optimising salience,
  novelty and difficulty, with privileged information for correctness; [claim] 22% more model errors than existing
  benchmarks. Contributes: description-level search (= criterion text) with item-level checking.
- Fluid benchmarking (arXiv 2509.11106): IRT 2PL with Fisher-information item selection -- the formal version of F2.
- BenchBench (Perlitz et al., arXiv 2407.13696): benchmark agreement testing -- the formal version of F3.

Challenger-solver co-evolution:
- R-Zero (Huang et al., arXiv 2508.05004, ICLR 2026): challenger rewarded by uncertainty 1 - 2|p - 1/2| over m = 10
  solver samples, repetition penalty over BLEU clusters (tau 0.5), majority pseudo-labels, solver trained only on items
  with 3-7 of 10 agreeing; [claim] +6.49 math, +7.54 general reasoning for Qwen3-4B-Base.
- Absolute Zero (Zhao et al., arXiv 2505.03335): proposer reward = 0 if the solver's mean success is 0 or 1, else
  1 - mean; a code executor validates proposed tasks (integrity, safety, determinism over 2 runs).
- SPIRAL (Liu et al., arXiv 2506.24119, ICLR 2026): self-play on zero-sum games; [claim] Kuhn Poker alone +8.6% math,
  +8.4% general reasoning.
- SPIN (Chen et al., arXiv 2401.01335, ICML 2024): self-play against one's previous iterate.
- CURE (Wang et al., arXiv 2506.03136, NeurIPS 2025): coder and unit tester co-evolve; the tester is rewarded for
  tests that expose the coder's mistakes -- the executable-verifier analogue of F2.
- Self-Challenging Agents (Zhou et al., arXiv 2506.01716, NeurIPS 2025): Code-as-Task = instruction + verification
  function + example solution + failure cases; kept only if the solution passes and every failure case fails --
  the admission test for model-written item checks.
- Sol-Ver (Lin et al., arXiv 2502.14948): solver-verifier self-play for code and tests.
- Self-Questioning LMs (Chen et al., arXiv 2508.03682); "Self-Play Only Evolves When ... Learnable Information Gain"
  (Liu, Qi, Du, He, arXiv 2603.02218): self-play stalls when the proposer's items carry no learnable signal -- the
  argument for the learnability term.

What the literature does not supply: any evidence that items generated to separate solver configurations on one
benchmark style predict transfer on real items of other benchmarks. R-Zero and SPIRAL report transfer of the
*trained model*, not of the item generator as a measuring instrument.

---

## 9. Risks

1. **Saturation of generated items** [measured: see 7.2]; pushing difficulty by obscure lookups instead of learnable
   situations. Mitigation: learnability term (S+ must pass sometimes), no reward for dead items.
2. **Circularity / Goodhart**: if S+ is the current Skill, F2 rewards items the Skill's own rules already handle, and
   the rubric learns the Skill instead of the benchmark. Mitigation: S+ = current, S- = previous step's Skill, and an
   F3 check against real items; never let the rubric see the Skill text.
3. **Criteria drift to reference-matching** [measured in v3 revisions]: rubric items that need the reference turn the
   judge into a second solver.
4. **Validity is internal consistency, not meaning**: exact arithmetic proves the answer equals the formula, and the
   independent check catches some mismatches (pilot 3b: 2 check_mismatch among the 14 evaluated K1 items), but two
   model calls can share the same misreading of the question, and item K1:5 passed both although it asks for two
   quantities (a year and a difference) and the reference holds one.
5. **Wikipedia rate limit through the shared gateway** [measured]: 57 of 69 searches got HTTP 429 in pilot 3 (no
   retry in `research.Wikipedia`), 10 material requests -> 3 tables; with one lock, >= 2 s spacing and 15/30/60/120 s
   retries (pilot 3b), 53 requests, 8 retried, 0 lost, 10 of 10 requests found a table. The frozen protocol needs a new
   research-client version before any forward item can be produced reliably.
6. **Low diversity**: the generator returns to the same table and the same cells across criteria and rounds (pilot
   3b: the item "debt held by the public, 2020 minus 2019 = 20.9" three times among 19 kept items; the identity hash
   catches only exact duplicates). Needs semantic deduplication and a per-table cap.
7. **Run noise**: with m = 2, |d| = 1/2 is pure noise for items with 1 or 3 passes; m >= 4 is needed.
8. **Leakage into purpose 2**: criteria phrased from the *target's* failures would carry target information into
   learning; criteria must come from the source benchmark's failures (or generic taxonomies), and F3 on targets stays
   post hoc.
9. **F3 is unmeasured**: nothing yet shows that generated-item discrimination predicts transfer on real items.

---

## 10. Cost

Spent in this exploration [measured]: pilot 2 618,598 GLM tokens; pilot 3 51,194 (21,327 GLM + 29,867 deepseek);
pilot 3b 190,119 (46,284 GLM + 143,835 deepseek); **total 859,911 tokens** of the 2M pilot budget (plus under
1,000 tokens of connectivity probes). The free analyses (re-scoring, v3
revisions and role costs, real-item and cal-1 discrimination) cost nothing.

Projected [estimate]:
- Minimal v5 loop: ~2.0M tokens per learning step and forward target (3 cards, m = 4), dominated by solving.
- E1-X (smallest rubric-side experiment, section 6): ~3.1M tokens, ~2-3 h.
- E1-Y (predictiveness F3 on real OfficeQA training items, K = 6 Skill variants): ~6-7M tokens.
- A reply-side check program (more pilot-2 style derivations): not recommended at any cost.

## 11. Recommendation

1. **Stop investing in model-written reply checks** as a verifier (pilot 2 negative on both benchmarks, 3 seeds, no
   accepted revision). Keep the frozen form library; use it for cheap deterministic form diagnosis and to split
   discrimination into form-driven and content-driven parts.
2. **Make the item side the verification side that co-evolves**: criterion cards (text) over the existing forward
   item code. Before any run: a new research-client version with request pacing and HTTP 429 retries (pilot 3b's
   client), semantic deduplication and a per-table cap, a single-quantity check on each question, m = 4 runs per arm,
   and the content-only discrimination fitness of section 3 (mean d; the null-corrected share as secondary).
3. **Run E1-X (~3.1M tokens)** as the go/no-go for purpose 1: does one round of fitness feedback raise the
   content-only discrimination (mean d) of valid generated items, measured on fresh items, without lowering validity?
   Pre-register the end point and the acceptance rule of section 4.
4. Only if E1-X is positive, **run E1-Y (~6-7M)** for purpose 2: does generated-item discrimination rank Skill
   variants the way real items do? Without E1-Y, no claim about "measuring generalisation better" is warranted.
5. Cross-references: D6 (generated tasks with guaranteed answers) supplies the item machinery and should share the
   research-client fix; D5 (noise floor) and D8 (statistical protocol) supply m, the null correction and the
   acceptance test; D12 (measuring cross-domain transfer) is where E1-Y belongs; D3/D4 (executable skills, rules as
   classifiers) should not reuse pilot 2's reply-check approach as a verifier.

## 12. Artifacts

On the new machine (`/data/feasibility/E1/`):
- `scripts/phase_a_join.py`, `verify_join.py` -- join and re-score the v3 train cells (training pools only);
  `data/{searchqa,officeqa}-{I-ds,E-ds}.jsonl`, `data/phase_a_stats.json`.
- `scripts/v3_revisions.py`, `scripts/role_costs.py` -> `data/v3_revisions.json`, `data/v3_role_costs.json`.
- `scripts/e1_pilot.py`, `scripts/e1_post.py` -> `pilot2/<bench>/{split,summary,post}.json`, `pilot2/<bench>/seedN/`
  (prompts, replies, checks, per-row results).
- `scripts/e1_forward_pilot.py` -> `pilot3/` (panels, sources, cells, analysis.json, ledger.json);
  `scripts/e1_forward_pilot_b.py` -> `pilot3b/` (same layout); `scripts/e1_forward_post.py` -> `pilot3b/post.json`
  (form/content split, pooled statistics, near duplicates); `scripts/e1_real_form.py` ->
  `data/real_officeqa_form.json`; logs in `logs/`.
On the old machine: `/data/feasibility-scratch/E1/cal1_discrimination.json` (script `cal1_discrimination.py`).
On the Mac: this report; copies of the result JSON under
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E1/results/`;
the scripts under
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E1/scripts2/`.
