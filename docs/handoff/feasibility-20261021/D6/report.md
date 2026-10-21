# D6: Generated tasks with guaranteed answers (feasibility report)

Explorer D6, 2026-10-21. All numbers are **measured** unless marked *(estimated)* or *(claim)*. Training material only:
no test, holdout, val, layout or split-manifest file was opened, and no repository was modified. Scripts and outputs are
on the new machine under `/data/feasibility/D6/` and copied to this directory (§12).

## 0. Bottom line

**Verdict: feasible, medium confidence.** Generated items with *executable* references are cheap and, after a
layered audit, nearly always correct. "Two models agree" is demonstrably not a guarantee. The open questions are
fidelity (do generated panels respond to rules like the real target does?) and the two unpiloted styles that matter
most for the similar-target check: OfficeQA and SpreadsheetBench.

**Measured:**

- **LiveMath-style** (2 runs, 72 GLM specs, 52 valid items). Independently audited with my own code:
  - **keys 52/52** (95% CI 0.93–1.00); references 51/52 (one code bug with a key correct by coincidence);
  - the independent executable cross-check (deepseek writes its own program from the item text) matched **31/31
    correct values** and produced the true value against **4/4 generator code bugs**;
  - a 2-of-3 tiebreak would raise run 2's yield **from 22/36 to 30/36 with 0 wrong values**;
  - the solver's failures on meta-key items reproduce the real D1 pattern (it picked the true weaker claim in 16/16
    failures), but the items are easier (5/21 solved against 1/100 real meta-key cells).
- **SearchQA-style** (2 runs, 45 valid items):
  - run 2 keys **22/25 correct at page scope** (conjunction family 14/14, superlative family 8/11);
  - the 3 defects are scope errors (one truncated table, two single tables of multi-table pages);
  - the deepseek row checker **agreed on 25/25, including all 3 wrong keys**;
  - all 3 defects are caught by a free mechanical page-scope re-derivation;
  - with context the items are too easy: 21/23 against 74–78% on the real pool.
- **The frozen v3 forward pathway** (smoke test of the code that never ran):
  - **both panels came out short** (7 and 3 items, below the minimum of 8), so the similar pathway would have been
    blocked again;
  - its items are near-trivial (2/7 state the answer; 4/7 are single-cell lookups; 3/3 LiveMath-style "formulas" are
    bare literals, all keyed "A"), and the solver passed 14/14 OfficeQA-style cells.
- **Pilot cost: 482,281 tokens** (cap 1.5M).

**Estimated:**

- About **200 fresh items per similar target per decision** are needed: C4' on 8–12 items passes a harmless rule
  60–65% and an 8-point harm 23%. Non-inferiority on 200 items with a 3-point margin passes 94–95% and 0.7%
  respectively.
- That costs **≈ 1.5M tokens per target-step** for LiveMath- or SearchQA-style panels and ≈ 4.5M for OfficeQA-style
  panels.

**Recommendation:**

1. Build a per-benchmark family library (typed spec → executable reference → template rendering) with the audit
   protocol of §5.
2. Before wiring the library into C4', run a **panel-validity study**: does Δ on generated panels predict Δ on the
   target's real training pool across existing Skill variants?
3. Keep generated items as selection material and mechanically diagnosed trigger sets, never as transfer evidence.

## 1. What I did

All work used training material only: the generators wrote new items, the item statistics come from training-pool files (LiveMath
and OfficeQA `dev_panel.json`, partition "development"; the SearchQA study panel), and the solver
statistics come from the v3 run's stage-entry training cells. I opened no test, holdout, val or layout file and no split
manifest. I modified no repository. Every script and output is under `/data/feasibility/D6/` on the new machine, with
copies in this directory.

1. **Code reading.** I read `skillopt/coevo5/forward.py` (443 lines), `research.py` (702 lines), `protocol.py`
   (constants, `SIMILAR_PAIRS`, `FORWARD_STYLES`, `TAXONOMY`), `gate.py` (`_similar`, C4'), `step.py`
   (`_forward`, how a short panel is handled), `roles.py`, `scoring.py`, `continual_eval/backends.py` (official solve
   and score), the SearchQA evaluator, and the registration v6 sections §1.1, §7, §8, §12.8 and §20.1.
2. **Target statistics** (free). These are format and difficulty facts about each benchmark that a generator must
   reproduce. They cover the training pools, the v3 failure-code mix, and the stage-entry solver pass rates, including
   LiveMath split by whether the "meta" option is the key.
3. **Smoke test of the frozen v3 forward pathway** (79,229 tokens). The v3 run never exercised this pathway. The frozen
   `research.material` and `forward.build_panel` ran unchanged on the live Wikipedia API for two real v3 rules, and every
   kept item was then solved twice with the official prompt and scorer.
4. **Pilot run 1** (earlier session, 217,601 tokens). It generated 30 valid LiveMath-style items (GLM writes the
   definition and the code; a sandbox executes it) and 20 valid SearchQA-style items (lookups on Wikipedia tables). Each
   item got a deepseek check, a solve and a hand audit.
5. **Pilot run 2** (this session). Its builders were rewritten after the run-1 audit:
   - LiveMath-style: option texts are rendered from typed claims by a template; the item form is scheduled
     (M+ / N / M−); GLM's own stated value must equal the executed value; the independent check is an executable
     deepseek program.
   - SearchQA-style: the table parser handles row and column spans and drops footnotes and hidden sort keys; there are
     two item families (F1 conjunction, F2 superlative within a group); near-miss rows go into the context.
6. **Tiebreak probe.** I took 16 specs: the 10 run-2 specs dropped for a code/belief mismatch or a missing exact
   value, and 6 run-1 specs with a code bug or a disputed check. An independent deepseek program was asked to
   compute each value. This measures whether a 2-of-3 rule would rescue the dropped specs and catch the code bugs.
7. **Independent hand audit.** I re-derived every LiveMath-style reference with my own code (brute force or a closed
   form I wrote myself) and re-derived every option's truth tag. I checked every SearchQA-style key mechanically
   against the archived parsed tables, with matching that ignores case, accents and punctuation and with my own number
   parser.
8. **Power simulation** of C4' (`c4_power.py`). The item noise is calibrated to the measured re-run flip rate of
   30/194 items.

## 2. The v3 forward pathway: what it does and what it lacks

### 2.1 What the code does (read from source)

- **Forward targets.** `FORWARD_STYLES = ("officeqa", "livemath")`, and `similar_targets(bench)` returns the forward
  targets that are later in the stage order and have a style. A SearchQA-stage rule is therefore checked forward on
  OfficeQA only. An OfficeQA-stage rule is checked forward on LiveMath only: the protocol comment says "no
  SpreadsheetBench panel can be generated". SearchQA is never a forward target.
- **Panel construction.** `build_panel` runs up to `FORWARD_ATTEMPTS = 5` rounds. Each round requests material once
  (`research.material`: a GLM researcher with at most 3 rounds and at most 8 calls on the live Wikipedia API). It then
  makes one GLM generation call for `FORWARD_PER_CALL = 3` items and one GLM consistency-check call per surviving item.
  It keeps the first 12 distinct valid items.
- **Short panels.** A panel with fewer than 8 items is "short". `step.py` then sets
  `similar_status = "forward_panel_short"` and the rule silently stays local.
- **OfficeQA style.** The question is about a Wikipedia table copied verbatim. The reference answer is a formula whose
  literals must be table cells, evaluated in exact rational arithmetic:
  - operators `+ - * /` and `**` with an integer exponent of at most 10;
  - functions abs, min, max, floor, ceil, factorial, comb, perm, gcd and lcm;
  - rounding half away from zero.

  A GLM check must produce a formula that rounds to the same value.
- **LiveMath style.** The question is a five-option item on a Wikipedia quote. The formula value must equal exactly one
  option, and the check is a GLM yes/no consistency call. There is **no meta option and no "strongest statement"
  structure** (grep of `forward.py`: no occurrence of "stronger", "strongest" or "meta").
- **The C4' test.** `gate._similar` passes the rule when `Σ rule L − Σ parent H ≥ 0` on the frozen 8–12-item panel
  (`MIN_SIMILAR_DELTA = 0`, so ties pass), with `FORWARD_RUNS = 2` runs per arm.
- **Status of the items.** Registration §8 and §12.8: forward items are selection material, never evidence of transfer.
- **Table parser.** `research._Page` parses tables without row or column span handling. This is verified below.

### 2.2 Smoke test of the frozen code (measured; `/data/feasibility/D6/v2/out/v3forward/`)

I ran two (rule, target) pairs, with rule texts read verbatim from the v3 run record: E-ds s1-r5 → OfficeQA style, and
E-ds s2-r3 → LiveMath style. The run took 69 calls, 79,229 tokens and 3.0 minutes, with no invalid role reply.

| | OfficeQA style | LiveMath style |
|---|---|---|
| material requests (found) | 5 (4 found) | 5 (1 found: "Significant figures") |
| items generated / valid | 12 / 7 | 3 / 3 |
| drops | literal_not_in_table 3, check_literal_not_in_table 1, check_mismatch 1 | — |
| panel status | **short (7 < 8)** | **short (3 < 8)** |
| solver passes (2 runs/item) | 14 / 14 cells | 5 / 6 cells |

Both rules would therefore have been marked `forward_panel_short`, and neither would have reached C4'. The similar
pathway that died in v3 at placement would have died again at panel construction. This is a measurement on n = 2 builds,
not a rate.

**Hand audit of the 10 kept items** (all 10 numerically correct):

- **OfficeQA style (7 items).** I recomputed each item on the archived page HTML with a span-aware parser
  (`verify_v3_office.py`).
  - 7/7 values are correct.
  - **2/7 state the answer in the question** ("the natural increase was –220,726. Verify this by computing …").
  - **4/7 are single-cell lookups**, where the formula is a bare literal (`112`, `106`, `14.4`, `376871`).
  - The v3 parser misaligns rows that have `rowspan` cells. On "List of largest companies by revenue" (revid
    1377107474) it returns 8 cells for Walmart (headquarters missing), 8 for CNPC (industry missing) and 7 for Sinopec,
    while the span-aware parse gives 9 for each of these rows. The 7 kept items happened to read unaffected cells.
  - The solver passed 14/14 cells. Real OfficeQA stage-entry training cells pass 37/148 (I-ds) and 30/148 (E-ds).
    This panel cannot detect harm because it is at ceiling.
- **LiveMath style (3 items).**
  - All three are arithmetic word problems ("Three measurements are added: 5.2 kg, 3.15 kg, 0.065 kg …").
  - **All three keys are "A".**
  - **All three formulas are bare literals** (`8.4`, `790`, `2257`). The "exact program check" therefore checks
    nothing: the generator computed the answer in its head and the program only restates it.
  - One item is ambiguous: 3,400 − 2,615 = 785 "rounded to 2 significant figures" is 790 under half-up and 780 under
    half-even rounding, and 785, 790 and 780 are all options.
  - None of the three has LiveMath's structure (a meta option, statements ordered by strength).

### 2.3 Gaps (what a v5 forward pathway needs)

| Gap | Evidence | Consequence |
|---|---|---|
| Yield: 8–12 items per (rule, target), material-limited | smoke: 7 and 3 valid; material found 4/5 and 1/5 | panels short, so C4' never runs |
| Power: 8–12 items × 2 runs | simulation, §7: a harmless rule passes 0.60–0.65 and an 8-point harm passes 0.23 | C4' is close to a coin flip |
| Fidelity: Wikipedia tables and quotes instead of Treasury-Bulletin tables and theorem-strength options | §3 target facts; smoke items | the panel does not test what a rule could break on the real target |
| Answer provenance: the generator writes the formula from its own belief; a bare literal passes | 4/7 + 3/3 bare-literal formulas | "exact arithmetic" is vacuous for most items |
| Leakage: answer stated in the question | 2/7 | trivial items |
| Parser: no row/column spans | verified on archived HTML | silent wrong cells on spanned tables |
| Answer-letter balance | 3/3 keys "A" | a letter prior can pass C4' |
| No SpreadsheetBench style | `FORWARD_STYLES` | OfficeQA → SpreadsheetBench is never checked |
| One consistency call by the same model family | design | a filter, not a guarantee (§5) |

## 3. Target facts a generator must mirror (training material, measured)

**LiveMath** (`/root/extension-20261013/livemath/dev_panel.json`, 155 tasks, partition "development")

- Every item has 5 options. Answer letters: A 25, B 34, C 34, D 22, E 40.
- The meta option "One of the remaining options is correct, but a stronger result can be proven." appears in **68/155**
  items (at position A 12, B 10, C 17, D 11, E 18). It is **the key in 68/68 of the items where it appears**: in this
  pool, "meta present" implies "meta is the key".
- 114/155 questions contain "strongest". Question length: median 598 characters (137–1,992). 14 of 775 options are
  40 characters or shorter: the options are theorem-strength statements, not numbers.
- **Stage-entry solver cells** (v3, step 1, both chains, 2 runs): 66/200 and 75/200 pass. Of the stage's 100 items, 57
  are in `dev_panel.json`. On those, cells where the meta option is the key pass **1/100** (95% CI 0.000–0.054), and
  cells with no meta option pass **71/128** (0.555, CI 0.464–0.643). I did not inspect the other 43 items.
- **Failure codes** (examiner, both chains, n = 259):
  - D1 "missed stronger result" 63%, D3 14%, D4 15%, D5 3%.
  - **D2 "wrongly chose the stronger result" 0/259**, as expected when meta present always means meta is the key.

**SearchQA** (`/root/continual-searchqa-long-20261001-study/data/panel.json`, 400 tasks)

- Jeopardy clues, median 85 characters. Context: median 3,884 characters (maximum 4,592), median 11 snippet docs.
- One reference answer per item, median 2 words. Scoring is EM after SQuAD normalisation, with a last-line fallback.
- **Stage-entry cells:** 310/400 (I-ds) and 297/400 (E-ds) pass.
- **Failure codes** (n = 193): answer-form codes take 69% (D1 extra words 37%, D2 other form 25%, D3 not one answer 7%);
  D4 wrong candidate 13%, D5 wrong kind 10%; the rest are format or non-completion codes.

**OfficeQA** (`/root/extension-20261013/officeqa/dev_panel.json`, 50 tasks)

- The documents are pre-parsed U.S. Treasury Bulletin pages (header "### treasury_bulletin_1944_01.txt page 18,
  Source URL: https://fraser…").
- 39/50 answers are numeric. Context: median 7,713 characters, maximum 29,325.
- The questions ask for totals, geometric means, OLS regressions and percentages over long financial tables.
- A keyword estimate finds up to 20/50 questions that need operations outside v3's formula language: standard deviation
  or variance 6, compound or annual growth 6, log/exp/root 4, geometric mean 3, correlation or elasticity 3,
  regression 2.
- **Stage-entry cells:** 37/148 and 30/148 pass.
- **Failure codes** (n = 229): D1 wrong data 27%, D2 wrong method 38%, D3 calculation slip 17%, D4 answer form 6%,
  D5 not in document 9%.

**SpreadsheetBench** (80 tasks)

- Public fields: instruction, input_files, answer_position. Private field: test_files.
- **Failure codes** (n = 87): D4 wrong logic 60%, D2 7, D1 6, D5 7, D6 5 (counts).

**ALFWorld** (39 tasks, 6 task types)

- The pool's games come from ALFWorld `json_2.1.1/train`. That split holds 2,435 task folders and 3,553 games across
  7 types.
- **Failure codes** (n = 124): D3 71%.

These facts set three requirements:

1. A **mirror panel** must reproduce the answer structure (meta present in 44% of items and always the key when
   present; single-answer exact match; numeric answers with stated rounding).
2. It must target the dominant failure codes (LiveMath D1, SearchQA answer form and D4, OfficeQA D1/D2).
3. Its difficulty must not sit at ceiling.

## 4. Design: typed spec → executable reference → constrained rendering

### 4.1 Common architecture and what "guaranteed" can mean

Every item passes through seven stages.

1. **Spec.** A JSON object in a family-specific schema. The spec is either drawn mechanically from a frozen source (a
   table row, a workbook schema, an ALFWorld game) or proposed by GLM (a mathematical definition plus code).
2. **Executable reference.** The answer is computed by a program run in a sandbox: an import whitelist, CPU and memory
   limits, and an exact result type (Integer or Rational, never float). For a lookup, deterministic code runs over a
   frozen, span-aware parse of a source identified by its revision. **No language model ever states the answer.**
3. **Constrained rendering.** Every checkable element is rendered by a template from the spec: option texts, fact
   values, operation and rounding phrases, answer-format instructions. Model-written text is allowed only for the
   "carrier" (the definition prose, the clue sentence, an instruction paraphrase), and that text is checked.
4. **Mechanical validity checks.** Exactness, uniqueness (exactly one correct option, a unique row, a unique arg-max),
   no answer leak, non-triviality, distinct options, the form schedule, and a balanced key letter.
5. **Independent executable cross-check.** A second model (deepseek) writes its own program from the *rendered text
   alone*, plus the table where there is one. Its value must equal the reference exactly. Disagreements go to a 2-of-3
   tiebreak (§5).
6. **Sampled audit.** An auditor with their own code checks a sample (§5).
7. **Freeze.** The item is stored with its spec, code, source revision or hash, model versions and value; the record is
   immutable and versioned.

The pipeline gives three levels of guarantee:

- **G-construct.** The answer is f(spec) and the checkable text is template(spec). The item can be wrong only if the
  library's template or function is wrong; unit tests remove that once per family. Applies to: SearchQA facts,
  LiveMath options, OfficeQA operations and SpreadsheetBench references.
- **G-exec2.** The answer comes from model-written code for a model-written definition, so the definition and the code
  can disagree. Two independently written programs (different models) that agree are a **filter**: both can misread
  the same ambiguous sentence in the same way. The residual rate is bounded only by the audit. Applies to: the
  LiveMath definition.
- **G-source.** A lookup answer is correct relative to the frozen source revision, not necessarily in the world. This
  is the right notion when the solver receives that source as context (SearchQA, OfficeQA).

### 4.2 LiveMath-style (piloted, runs 1 and 2)

- **Spec.** GLM receives one of 12 topic families: number theory, combinatorics, partitions, labelled graphs,
  polynomials, linear algebra, permutation groups, exact sums, integrals and series, discrete probability, lattice
  points, recurrences. It returns `{definition, code, value, claims[7]}`:
  - the definition defines a computable quantity Q;
  - the code computes Q exactly;
  - the value is GLM's own belief about Q;
  - the claims are typed and evaluated by the machine: `eq / lt / le / gt / ge / between / even / odd /
    divisible_by`, one exact, two true-but-weaker and four false.
- **Reference.** The sandboxed code computes Q. Each claim's truth comes from Q by exact comparison. GLM's stated value
  must equal Q; in v5 a mismatch should go to the 2-of-3 tiebreak instead of being dropped (§6.3).
- **Rendering.** Option texts come from a template (`$Q = 825$`, `$800 \le Q \le 850$`, `$Q$ is an integer divisible
  by $5$`). The real pool's meta sentence is used verbatim, and the real closing question is appended. Claims that pin
  an integer ("between" an interval that contains one integer) or duplicate another claim's text are skipped. The
  definition must not state Q.
- **Forms.** Each one tests a code from the taxonomy:
  - **M+** (meta is the key): one true weaker claim, three false claims and the meta option. It tests D1, the dominant
    real failure.
  - **N** (no meta option): the exact claim, up to two weaker true claims and false claims. The key is the exact claim.
    It tests D3/D4.
  - **M−** (meta present but false): the exact claim, three false claims and the meta option. It tests D2.

  M− is a **counterfactual**: the real pool never has it (meta present always means meta is the key, 68/68; D2 0/259).
- **Panel composition.**
  - **Mirror panel:** M+ and N items in the real proportion, 68 : 87 (44% : 56%).
  - **Contrast panel:** M− items, reported separately. A *structural* rule ("before choosing a true bounded statement,
    check whether a stronger statement, such as an exact value, is derivable; the meta option asserts exactly that")
    helps on all three forms. An *answer-distribution* shortcut ("pick the meta option whenever present", which the
    real pool rewards 68/68) is caught by M− items. This is the distinction D7 needs between allowed rules and leaking
    ones.
- **Distractors.** GLM's *wrong* beliefs make realistic false options. In run 2 it believed 2,016 for 2,352, 84 for 192
  and 210 for 315 (it forgot the class of four transpositions). These are "common-error" values; once the truth is
  executable, they can be inserted as false claims.
- **Key letter.** Assign it from a balanced schedule (Latin square), not by shuffling. Shuffling gave D 9/22 in run 2,
  and run 1 had A 18/30.
- **Families to exclude or fix.** In run 2, integrals and series produced 0 valid items out of 6 specs:
  - sympy left 2 integrals unevaluated;
  - 1 series result could not be parsed;
  - 3 exact-sum specs were lost to a bug in my value parser (it rejected "Fraction(...)" text).

  Prefer finite or combinatorial families, or validate closed forms numerically at 50 digits and accept them only as a
  sympy-simplified exact constant.
- **Fidelity limit (claim, partly measured).** The items mirror LiveMath's answer *structure* (an order by strength
  plus the meta option), not its content (research-level analysis). Measured: on M+ items the solver fails in the same
  way as on real meta-key items (it picked the true weaker claim in 16/16 M+ failures), but it fails less often (5/21
  solved against 1/100 real cells). N items are easier than real meta-absent items (17/24 against 71/128).

### 4.3 SearchQA-style (piloted, runs 1 and 2)

- **Source.** Wikipedia list pages, frozen by revision ID. A span-aware HTML table parser handles rowspan and colspan,
  drops `<sup>` footnotes and hidden sort keys (`display:none`), and records links.
- **Key and attributes.** The key column is the column where every cell is one link whose text equals the cell text,
  with distinct, non-numeric values. Attributes are "atomic": 1–40 characters, no brackets or semicolons, at most one
  year, not a dash or N/A.
- **Families.**
  - **F1 conjunction:** two attribute values that jointly identify exactly one row. The generator prefers values that
    other rows share, so that neither value alone suffices. Up to 3 near-miss rows per value go into the context. This
    targets **D4 wrong candidate**.
  - **F2 superlative within a group:** the row with the highest or lowest numeric measure among the 2–6 rows that share
    a categorical value (or a year). The arg-max must be unique, and all group rows go into the context.
  - **F3 answer form (proposed, not piloted).** It targets D1/D2/D3, which make up 69% of real failures. The key is
    the table's link text, the shortest common name. Variant surface forms (the link title, the lead sentence, a form
    with title or first name) go into the context, and scoring stays single-answer EM. Its purpose is to make the
    panel sensitive to answer-form rules: 6 of the 10 v3 SearchQA-stage proposals were answer-form rules (from the v3
    rule texts).
- **Context.** Snippets in the SearchQA format `[DOC] [TLE] title - Wikipedia [PAR] text`. The required docs (the
  target row and the near-miss or group rows) are always included whole. Distractor docs (other rows, other pages'
  rows, page leads) are added up to 4,600 characters, about the real maximum of 4,592.
- **Clue.** GLM writes one declarative sentence of at most 200 characters, copying the fact values verbatim. Mechanical
  checks: length 20–230 characters; no "Wikipedia/table/row/column"; every value present verbatim; a superlative word
  for F2; no answer token.
- **Checks.**
  1. Mechanical uniqueness, exact and after normalisation.
  2. Key cleanliness (no footnote markers).
  3. A deepseek row checker (table + clue → row, unique, unsupported).
  4. The solver with context and blind (no context), for difficulty, not validity.
- **Fixes required by the run-2 audit** (§6.2; all free and mechanical):
  1. never truncate a table (my pilot generator kept 80 rows, which produced one key defect);
  2. re-derive every key over *all* tables of the page and by group *containment* (multi-country cells);
  3. allow F2 superlatives only on closed lists (complete by construction: national parks by state, World Cup
     finals by team), or render the scope from the table's section heading ("among volcanoes of 3,000–4,000 m");
  4. render the period (year table) into the clue;
  5. drop `visibility:hidden` spans;
  6. take a sign from the icon's alt text or `data-sort-value`.
- **Use.** SearchQA is never a forward target in v3, but these items serve three purposes:
  1. fresh SearchQA training items (D1's fresh batches);
  2. forward panels if the stage order changes. The owner's purpose (2) allows evolving on OfficeQA and evaluating on
     SearchQA;
  3. a backward check that does not reuse the regression panel.

### 4.4 OfficeQA-style (designed, not piloted beyond the v3 smoke)

- **Source.** Treasury-Bulletin pages, the real OfficeQA source:
  - Option (a): pages of the public OfficeQA corpus (claim: the benchmark distributes the parsed bulletins), excluding
    every page that any test item uses. The exclusion must be done by protocol code that has test access, comparing
    `source_sha256` or page identifiers, never by the operator.
  - Option (b): other public statistical tables (FRED, BLS, Census) converted to the same parsed-text format.

  Option (a) gives fidelity; option (b) gives zero overlap risk.
- **Spec.** `{page, table id (span-aware), operand cells by row and column header path (e.g. "Veterans Administration"
  × "FY 1934"), operation family, parameters, rounding, unit, answer format}`.
- **Operation library**, implemented once in Python with exact fractions or 50-digit mpmath, then rounded as stated:
  - sum, difference, ratio, percent change against percent difference;
  - mean, geometric mean;
  - population against sample standard deviation;
  - CAGR against simple growth;
  - OLS slope or prediction, correlation;
  - compound against continuous growth.

  These cover the up to 20/50 real questions that v3's formula language cannot express.
- **Rendering.** A template ("According to <table title> in the <date> Treasury Bulletin, what is the <operation
  phrase> of <row label> for <periods>? Report in <unit>, rounded to <k> decimal places.") plus an optional GLM
  paraphrase. A paraphrase is checked by **back-translation**: a second model maps it back to a spec, which must
  evaluate to the same value.
- **Targeting the failure codes.**
  - D1 wrong data: put near-miss operands in the same table (adjacent periods, fiscal against calendar year).
  - D2 wrong method: families whose method distinction is stated explicitly.
  - D3 calculation slip: multi-step logs and roots.
  - D4 answer form: explicit units, decimals and percent sign, scored by the official normalised EM.
- **Checks.**
  1. Every operand is a verbatim table cell (v3 already has this).
  2. **The answer value must not appear in the question.**
  3. Non-trivial: at least 2 operands, or a single-cell lookup capped at the real lookup share.
  4. A deepseek program written from the question and the table agrees after rounding.
  5. Ties at the rounding boundary are rejected, which removes the 785 → 780/790 class.

### 4.5 SpreadsheetBench-style (designed, not piloted)

- **Spec.** `{schema, data seed, operation family, parameters, answer_position}`:
  - The schema lists columns with types: text keys with duplicates, trailing spaces or case variants; numbers stored as
    text; dates both as serial numbers and as strings; blanks.
  - Operation families: lookup or join on a key (D6), conditional aggregation in SUMIFS style (D4), a per-row derived
    column (D3), filter or sort into a range, text normalisation, date bucketing (D5).
- **Reference.** A pandas or pure-Python function computes the expected cells. A **second, independent path**
  (openpyxl-written formulas recalculated by LibreOffice in the docker image) must give the same values.
- **Multiple test workbooks.** Generate k = 3 variants per spec from different data seeds, like the real private
  `test_files`. The solver's program must pass on all variants, which catches hard-coding (D3) mechanically.
- **Rendering.** An instruction template ("In sheet X, fill D2:D41 with … for each row where …") plus an optional
  paraphrase with back-translation.
- **Cost.** The reference needs no language model; GLM is used only for paraphrases. The engineering estimate is 1–2
  days (estimated).
- **Effect on v3.** The `FORWARD_STYLES` restriction would be lifted, so OfficeQA → SpreadsheetBench becomes checkable.

### 4.6 ALFWorld (no generation needed)

- The simulator's goal check (PDDL goal satisfaction) is the reference, so a fresh game's answer is guaranteed by
  construction.
- `json_2.1.1/train` holds 3,553 games across 7 types, against 39 in our pool. Overlap with the test panel is unknown,
  so the exclusion (by game-file hash) must be done by protocol code that has test access.
- Generating new PDDL problems with ALFWorld's generation scripts is possible but unnecessary.
- ALFWorld has no similar pair. Its fresh games serve only as fresh training batches (D1) and as dissimilar
  no-harm panels.

## 5. Audit protocol: a filter is not a guarantee

### 5.1 Layers

| Layer | When | What | Cost |
|---|---|---|---|
| L0 library tests | once per family, and on every change | parser on archived pages (spans, footnotes); claim evaluator and templates; operation library against hand cases; sandbox limits | free |
| L1 mechanical checks | every item | exact type; uniqueness; leak; non-triviality; distinct options; form and letter schedule; rounding-tie rejection; source revision recorded | free |
| L2 independent executable cross-check | every item | a second model writes a program from the rendered text (and table) only; exact agreement; on disagreement, a 2-of-3 tiebreak among {generator code, generator stated value, cross-check program} that accepts a value only when two sources agree and at least one of them is a program; otherwise drop | ≈ 0.4k tokens per item (LiveMath, measured mean 397) |
| L3 acceptance audit | before a family is admitted, and after any change | an auditor with their own code re-derives n items; admit the family at 0 defects in n | n = 60 gives a defect rate < 5% at 95% confidence (n = 30: < 9.5%) |
| L3' continuing sample | every step | m = 5 items per family per step; on any key defect, quarantine the family, re-audit 30 items, fix, bump the version | about 5 audits per family per step |
| L4 in-use triage | every round | prioritise for audit the items no arm passes in any run ("dead": too hard, or wrong); prune items every arm passes | free |

Defect classes, worst first:

1. **Key defect:** the keyed answer is wrong.
2. **Reference defect:** the computed value is wrong but the key happens to be right.
3. **Text defect:** the item is ambiguous, ill-posed or garbled, but the key is right.
4. **Leak:** the answer is stated in the item.
5. **Triviality.**

### 5.2 Why agreement is only a filter (measured)

- **A yes/no model audit is not a check.** In run 1, deepseek's "does the code match the question?" verdict said yes
  for 30/30 items, including the one defective reference (#34, F_2 = 2, which computes F_31 instead of F_30).
- **The reasoning recompute is a noisy filter.**
  - It caught that defect.
  - It raised false alarms on correct references: 1/29 in run 1 (ménage number U_8 = 4,738, recomputed as 12,528) and
    **4/22 in run 2** (#4, #8, #10, #15; all four references verified correct).
  - Pooled false-alarm rate: **5/51 = 9.8%** (95% CI 3.3–21.4%).
- **The generator's own belief disagreed with its code in 8/30 run-2 specs that had a parseable exact value.** In 6 of
  the 8 the code was right and GLM's arithmetic wrong; in 1 (#31, convex-hull interior) the code was wrong, counting
  the 4 boundary vertices (91 against the true 87, verified with Pick's theorem and brute force); in 1 (#26) sympy left
  the integral unevaluated. Dropping on mismatch is therefore safe but discards 6 correct items to remove 2 unusable ones.
- **The independent executable cross-check** agreed with every correct code value it saw: 31/31 (CI 0.888–1.000). It
  also produced the true value against all 4 code bugs of the two runs (4/4, including run-1 #34, which the truth
  table and the yes/no audit had passed). Tiebreak probe, §6.3.
- **SearchQA: agreement on a shared view.** The deepseek row checker agreed with the generator on 25/25 run-2 items and
  flagged no unsupported statement, yet 3 of those keys are wrong at page scope (§6.2). The checker received the same
  single, truncated table as the generator. A check that sees what the generator sees cannot catch the generator's
  scope errors.

These are the reasons the protocol puts an executable cross-check plus an audit sample in front of every family, and
never treats "two models agree" as proof.

## 6. Pilot results (all measured; the solver is deepseek-v4-flash with the official prompt and the official scorer)

### 6.1 LiveMath-style items

| | Run 1 (earlier session) | Run 2 (this session) |
|---|---|---|
| GLM generation calls / specs | 14 / 36 | 12 / 36 |
| valid items | 30 | 22 (forms M+ 7, N 8, M− 7) |
| drops | truth table 5 (2 code bugs: #6, #33; 2 GLM belief errors: #18, #19; 1 claim-construction error: #35, two true claims); code error 1 | belief mismatch 8, Fraction-parse 3 (my parser bug), code error 1, result parse 1, unevaluated result 1 |
| **keys correct (independent hand audit)** | 30/30 | 22/22 |
| **references correct** | 29/30 (#34: F_2 = 2 in GLM's code gives F_31 = 1,346,269 for F_30 = 832,040; the key, meta, is correct by coincidence because "divisible by 8" is true for the real value) | 22/22 |
| answer letters | A 18/30 (biased construction) | A 2, B 4, C 2, D 9, E 5 (random shuffle; χ² p ≈ 0.11) |
| solver correct | 14/30: exact-value items 12/16; meta-key items 2/14 | 14/22: M+ 3/7; N 5/8; M− 6/7 |
| how the solver failed | all 12 meta-key failures picked the true weaker claim (D1) | M+: picked weaker 4/4 (D1); N: weaker 1, false 2 (#13: concluded there are 2 real roots; #19: concluded the S9 class does not split in A9); M−: picked meta 1/1 (D2) |
| deepseek yes/no code audit | "yes" 30/30, including #34 | not used |
| deepseek reasoning recompute | disagreed on 2/30: #34 (true defect) and #3 (false alarm) | disagreed on 4/22: #4, #8, #10, #15 (all false alarms) |
| deepseek executable program from the definition alone | not run | **agreed 22/22** |
| tokens | 115,101 | 103,170 (GLM 56,862; deepseek 46,308) |

**My audit of run 2** (`audit/verify_run2_livemath.py`; `brute19.py`). Each Q was recomputed with my own code:

- brute force for #0, 1, 3, 4, 5, 7, 8, 9, 10, 11, 20, 27, 29, 32, 33;
- closed forms or exact determinants for #12, 15, 16, 17, 34;
- a sign-change count on a 0.01 grid for the degree-5 polynomial in #13 (5 sign changes, so exactly 5 real roots);
- a full A9 orbit for #19 (12,096).

All 22 Q values match. Every option's tag (exact / weaker / false) was then re-derived from my Q, and the keyed letter
re-derived under the "strongest statement" semantics: 22/22 agree.

**Text defects that do not affect the key:**

- 2/22 in run 2:
  - #13 has a leftover fragment ("…∈ ℚ[x], counted with multiplicity over ℂ"), although Q counts distinct real roots.
  - #20 has a self-correcting sentence ("a Sylow 3-subgroup … order 9… more precisely, define Q as…").
- In run 1, model-written option texts disagreed with their typed claims twice:
  - #31: "2 < Q < 3" was rendered for the claim "between [2,3]";
  - #35: "divisible by 11 and Q > 1000" was rendered for "between 1001–1071", giving two true claims.

  Template rendering in run 2 removes that class by construction.

**Pooled LiveMath-style audit:**

- **keys 52/52** (95% CI 0.932–1.000);
- **references 51/52** (CI 0.897–1.000);
- no ambiguity-induced key defect found (upper bound 5.6% at 0 in 52).

**Fidelity to the real target (difficulty and failure pattern):**

- M+ items solved 5/21 (0.24, CI 0.08–0.47), against real meta-key cells 1/100.
- Exact or N items solved 17/24 (0.71), against real meta-absent cells 71/128 (0.55).
- The *failure pattern* matches, with the true weaker claim picked in 16/16 M+ failures.
  - In at least 3 of the 4 run-2 M+ failures the solver had computed Q exactly and still chose the weaker listed claim
    (#3: "B says a stronger result can be proven—which is true, but B is not the exact answer"; #9 and #12 likewise).
  - So the failure lies in reading the meta option, as in the real D1, not in the arithmetic.
- The *difficulty* is lower: the items are computational, and the solver can compute Q.

### 6.2 SearchQA-style items

| | Run 1 (earlier session) | Run 2 (this session) |
|---|---|---|
| pages with a usable table / queries | — | 10 / 20 |
| specs / valid | 27 / 20 (one family: two facts) | 26 / 25 (F1 14, F2 11; 1 drop: fact not verbatim) |
| **keys correct** | 19/20 at table scope (#21 key "…ChargersA", a footnote letter) | **22/25 at page scope**: F1 14/14, F2 8/11 |
| key defects | 1 (parser: footnote letter) | 3: **#15** (my generator kept only the first 80 of 109 rows; the true table-scope answer is Estádio do Arruda, not Grêmio Arena); **#18, #21** (the chosen table is one elevation band of a multi-table page; at page scope the answers are Arenal Volcano and Monte Pissis or Ojos del Salado, not Turrialba and Tromen) |
| text defects (key unaffected) | 4/20: #0 adds a false fact ("in the Himalaya" for a Hindu Kush peak); #1, #8 garbled non-atomic values ("2 (1916, 1936, 1972)"); #15 footnote letter in a value ("$3,600,000R") | 4/25: #23, #24 omit the year on a page with six yearly tables; #12 loses the sign (−1.0% rendered as "01.0%": the sign is an icon the parser drops); #3 keeps a hidden padding digit ("00.4%"). Run 2 removed the run-1 classes (atomic values, `<sup>` dropped) |
| two-of-two filter (checker agrees AND solver correct) | kept 18/20: it removed the defective key #21 and the checker error #26, but by construction it removes every item the solver fails | not used |
| deepseek row checker | agreed 19/20 (#26 a checker error) | **agreed 25/25 and flagged "unsupported" 0/25**, *including all 3 key defects and the sign loss* |
| solver with context | 19/20 | 21/23 successful calls (2 calls failed with http_429 and are excluded); both failures answered the measure ("13,051", "1,666 ft") instead of the entity (D5 wrong kind) |
| solver blind (no context) | 8/20 | 8/25 |
| context chars median (max); docs median | — | 3,304 (4,438); 14 (real: 3,884 (4,592); 11) |
| tokens | 102,500 | 76,731 (GLM 7,388; deepseek 69,343; 4 http_429) |

**How the run-2 keys were audited** (free; `audit/audit_searchqa2.py`, `page_scope_check.py`, `cell_markup.py`):

1. Every key was re-derived from the archived parsed table with matching that ignores case, accents and punctuation,
   and with my own number parser: 25/25 hold at the generator's own scope.
2. Every page was re-fetched at the recorded revision. **All** of its tables were parsed in full, and each key was
   re-derived over every table carrying the needed columns, both by exact group value and by group containment (e.g.
   "Argentina/Chile" counts as Argentina). This found the 3 key defects above.
3. Two airport cells' raw markup was inspected. It confirmed that the padding digit sits in a
   `visibility:hidden` span (the parser removes only `display:none`) and that the sign of "% change" is carried by a
   "Decrease"/"Increase" icon (JFK: `data-sort-value="-1"`).

All three key defects passed every model check, because the row checker saw the same single, truncated table as the
generator. This is the clearest measured case of agreement acting as a filter, not a guarantee: 25/25 agreement, 3/25
wrong keys (0.12; CI 0.03–0.31). All three are now detectable mechanically at no cost (§4.3 fixes).

**Fidelity:**

- With context the items are easier than real SearchQA: 21/23 (0.91), against 297–310/400 (0.74–0.78) at stage entry.
- Blind, the solver recalls about a third of the answers (8/25), so famous list pages carry a memorisation risk.
- The answer-form codes that dominate real failures (69%) are not exercised by F1/F2; this is why family F3 is proposed.

### 6.3 Tiebreak probe: would a 2-of-3 rule rescue drops and catch code bugs? (16 deepseek calls, 5,550 tokens)

For each case the truth was fixed first by my independent computation. The probe then added only the deepseek program
value (`tiebreak_probe.py`, `out/tiebreak/probe.json`).

| Case set | n | deepseek program = truth | 2-of-3 decision (a value two sources share, one of them a program) |
|---|---|---|---|
| run-2 belief mismatches, code right (#2, 6, 18, 28, 30, 35) | 6 | 6/6 | 6/6 accepted with the correct value |
| run-2 belief mismatch, code wrong (#31: 91 instead of 87) | 1 | 1/1 (87) | accepted with the correct value 87 |
| run-2 code gave no exact value (#24 series; #25, #26 integrals) | 3 | 1/3 (#24, π²/18; the 2 integrals were left unevaluated by deepseek's sympy too) | 1 rescued correctly, 2 dropped |
| run-1 code bugs (#6 p(15,5) for p(20,5); #33 and #34 F_2 = 2) | 3 | 3/3 | all 3 rejected (program ≠ code; no stated value to break the tie) |
| run-1 correct code with a disputed check or GLM claims (#3, #18, #19) | 3 | 3/3 | 3/3 accepted |

- The executable cross-check **agreed with every correct code value it saw: 31/31** (22 run-2 valid + 6 + 3; CI
  0.888–1.000).
- It **produced the true value against all 4 code bugs: 4/4**, including run-1 #34, which the generator's truth
  table and deepseek's yes/no audit let through (the reasoning recompute also caught it, but at a 9.8% false-alarm
  rate).
- With the 2-of-3 rule, run 2's yield rises **from 22/36 to 30/36** (8 of the 10 drops rescued, 0 wrong). Fixing my
  `Fraction(...)` parser would add up to 3 more (estimated: those specs were not re-run).

### 6.4 The frozen v3 pathway (smoke test, §2.2)

- 2 builds, both short (7 and 3 items, below the minimum of 8).
- 10/10 kept items are numerically correct, but:
  - 2/7 OfficeQA-style items state the answer;
  - 4/7 are single-cell lookups;
  - all 3 LiveMath-style formulas are bare literals, with all 3 keys "A";
  - 1 item is ambiguous at a rounding tie;
  - none has LiveMath's structure;
  - rowspan misalignment was confirmed in the parser.
- The solver passed 14/14 OfficeQA-style cells, against about 22% on real OfficeQA.

### 6.5 Failure-mode catalogue (what goes wrong, in order of frequency in this pilot)

| Failure mode | Where measured | Rate | Caught by | Fix |
|---|---|---|---|---|
| Generator's stated value wrong (code right) | LiveMath | 8/72 specs (run 1: 2, run 2: 6) | belief = code check | 2-of-3 tiebreak keeps the item; use the wrong value as a distractor |
| Generator's code wrong | LiveMath | 4/72 (#6, #33, #34 in run 1; #31 in run 2) | truth table 2/4; belief check 1/1; **executable cross-check 4/4** | executable cross-check on every item |
| Tool cannot produce an exact value (integrals, series) | LiveMath | 3/36 in run 2 (+3 harness parse bug) | exactness check | exclude or restrict analysis families; fix the parser |
| Text/claim mismatch with model-written options | LiveMath run 1 | 2/36 | hand audit only | template rendering (0 in run 2 by construction) |
| Garbled or self-correcting definition text (key unaffected) | LiveMath run 2 | 2/22 | hand audit only | a carrier-text lint (fragments, "more precisely", "…"); a second-model read-back of Q |
| Letter imbalance | both runs | A 18/30; D 9/22 | — | balanced key schedule |
| Scope defect: one table of a multi-table page, or a truncated table | SearchQA run 2 | 3/25 keys | **page-scope re-derivation (free)**; not by the row checker | never truncate; re-derive over all tables; F2 only on closed lists, or scope rendered from the section heading |
| Underspecified period | SearchQA run 2 | 2/25 | hand audit | render the table's year or section into the clue |
| Lost sign or hidden padding (icons, `visibility:hidden`) | SearchQA run 2 | 2/25 | raw-markup inspection | use the icon's alt text or `data-sort-value`; drop `visibility:hidden` spans |
| Footnote letters, non-atomic values | SearchQA run 1 | 1/20 key, 3/20 values | hand audit | fixed in run 2 (`<sup>` dropped, atomic values) |
| Added false fact in the clue | SearchQA run 1 | 1/20 ("Himalaya") | not by the run-1 checker | "unsupported" flag (0 in run 2); facts-only clue template |
| Forward-panel yield too low | v3 smoke | 2/2 builds short | panel status | bulk generation from family libraries (§4) |
| Answer stated in the question; bare-literal formulas | v3 smoke | 2/7; 7/10 | — | leak check; minimum of 2 operands |

## 7. How many items per step (power of C4'; estimated by simulation)

The model (`c4_power.py`; output in `audit/c4_power_output.txt`) works as follows:

- Each item has a pass probability.
- Unstable items are calibrated to the measured re-run flip rate of 30/194 = 15.5%. Mix A puts the unstable items at
  p = 0.5; mix B spreads them over 0.2–0.8.
- Each arm runs 2 times per item, as in v3.
- A harm lowers only the unstable items, so that the panel mean drops by the stated number of points.

| Test | n | harmless rule passes | 3-point harm passes | 5-point harm passes | 8-point harm passes |
|---|---|---|---|---|---|
| v3 C4' (Σ rule − Σ parent ≥ 0, ties pass) | 8 | 0.65 / 0.64 | — | — | — |
| v3 C4' | 12 | 0.62 / 0.60 | — | 0.35 | 0.23 |
| non-inferiority, margin 3 points | 50 | 0.82 | 0.56 | 0.36 | 0.12 |
| non-inferiority, margin 3 points | 100 | 0.87 | 0.55 | 0.26 | 0.04 |
| non-inferiority, margin 3 points | **200** | **0.94–0.95** | 0.53 | **0.17** | **0.007** |
| non-inferiority, margin 3 points | 400 | 0.99 | 0.52 | 0.08 | 0.000 |

- On 8–12 items C4' is a coin flip: a harmless rule fails it 35–40% of the time, and an 8-point harm passes it 23% of
  the time.
- **About 200 items per similar target per decision** keeps harmless rules (fails 5%) while rejecting a 5-point harm
  83% of the time and an 8-point harm almost always. A 3-point harm, the size of the margin itself, is a coin flip at
  every n, as it should be.
- **Assumption:** generated items have the same instability as the real benchmark. This is not measured: each pilot
  item was solved once. A cheap first measurement is 2 runs of the parent on the pilot items (§11).
- The statistical form (margin, one-sided bound, multiplicity over 2 similar rules) belongs to D8. The number of items
  is the D6 input: **≈ 200 fresh generated items per similar target per step**, shared by the parent and every similar
  rule as a paired panel.

## 8. How generated panels become the similar-target test and a training signal

**As the C4' test (selection material, registration §12.8):**

1. Each step draws a **fresh mirror panel** per forward target from the audited family library.
   - The real proportions are reproduced: for LiveMath, M+ : N = 68 : 87; for OfficeQA, the operation families'
     shares and the numeric/list answer forms.
   - The panel is frozen before any arm is solved.
   - It is never reused for a decision.
2. Difficulty is set by family parameters, calibrated once on a separate calibration batch. It is **not** set by
   filtering on solver success. The run-1 SearchQA-style filter required the solver to answer correctly; it removed
   the one defective key, but it also removes every item the solver fails, which keeps only easy items.
   Target: the parent passes 50–80% on the panel.
3. A **contrast sub-panel** (LiveMath M−; SearchQA items whose context contains a tempting near-miss) is reported
   separately. It vetoes shortcut rules: "pick meta whenever present" passes the mirror panel and fails M−. Whether it
   vetoes or only informs is an owner decision.
4. C4' passes when the rule is non-inferior to the parent within the margin on the mirror panel (§7).
5. **These panels are never transfer evidence.** The transfer claim stays on the real target's test panel at the end
   of the run, as registered.

**As a training signal:**

- *Diagnoses for free.* On a generated item the structure of every option is known, so the failure code is
  mechanical:
  - picked the weaker true claim in an M+ item = D1;
  - picked meta in an M− item = D2;
  - answered the measure value instead of the entity = D5.

  This removes the examiner's noise for those items.
- *Trigger sets on demand.* For a rule that targets a code, generate items that contain the rule's condition: M+ items
  for a D1 rule, near-miss rows for a D4 rule. This removes "insufficient_support" (MIN_TRIGGER = 4), which killed the
  only `similar` proposal in v3.
- *Limit.* Generated items differ from the real distribution: computational against research-level LiveMath, and
  famous list pages against Jeopardy clues. A rule must still be accepted on real training items. Generated items widen
  the evidence; they do not replace it.

**As the co-evolving verification side** (the owner's purpose 1, the "coding rubric"):

- The rubric is the family library: spec schema, reference program, rendering template and checks. It is literally
  code.
- Its evolution step works as follows:
  1. map the current failure-code mix to families;
  2. allocate the generation budget in proportion to that mix;
  3. add a family when a frequent code has none (SearchQA answer form, F3, is the first example);
  4. retire families that are saturated (every arm passes) or dead (no arm passes);
  5. version and re-audit (L3) every change.
- A measurable success criterion for the rubric, free of test data: a **panel-validity study.** For K Skill variants
  already in hand, compare Δ(variant − parent) on the generated mirror panel with Δ on
  the target's real *training* pool. Sign agreement and correlation across variants tell whether the generated panel
  predicts the real target. Suitable variants are the cal-1 texts: the empty scaffold against the task-card seeds is a
  known large positive effect, and the placebo controls are known null effects. If it does not, C4' on that panel is meaningless however correct its answers are.
- This study is the missing link between "correct answers" and "a useful similar-target test". It is the first
  experiment I recommend (§11).

## 9. Cost

**Measured pilot cost: 482,281 tokens in total**, against a cap of 1.5M.

| Part | Tokens |
|---|---|
| run 1 | 217,601 |
| v3 smoke | 79,229 |
| run-2 LiveMath | 103,170 |
| run-2 SearchQA | 76,731 |
| tiebreak probe | 5,550 |
| page-scope check, markup check | 0 model tokens (Wikipedia API only) |

Wall time: run-2 LiveMath took 24.9 minutes, mostly waiting on the deepseek route (503 and 429 errors); SearchQA took
11.5 minutes.

**Measured per-item costs:**

- LiveMath-style:
  - GLM generation: 4,738 tokens per call for 3 specs, or 2,585 per valid item at run-2 yield (about 1,895 with the
    tiebreak yield of 30/36, estimated);
  - executable cross-check: 397;
  - solve: 811 per cell.
- SearchQA-style:
  - clue: 284;
  - row checker: 1,541 (optional once the page-scope check is in);
  - solve with context: 1,075 per cell;
  - blind: 243.

**Estimated cost per similar target per step** (n = 200, 2 runs, parent plus up to 2 similar rules = 1,200 cells):

| Target | generation and checks | C4' solving | total |
|---|---|---|---|
| LiveMath-style | ≈ 0.45–0.6M | ≈ 1.0M | **≈ 1.5M** |
| SearchQA-style | ≈ 0.06–0.4M | ≈ 1.3M | **≈ 1.5M** |
| OfficeQA-style (contexts of about 7.7k characters, about 3–4k tokens per cell; not piloted) | ≈ 0.6M | ≈ 4M | **≈ 4.5M** |

Only one stage at a time has forward targets (OfficeQA at the SearchQA stage; LiveMath, and SpreadsheetBench if added,
at the OfficeQA stage), so this is the per-step increment.

**One-time costs (estimated):**

- engineering for the family libraries: about 2–4 days for OfficeQA and SpreadsheetBench; the LiveMath and SearchQA
  builders exist as pilot code;
- L3 acceptance audits of 60 items per family;
- the panel-validity study: K = 6 variants × 400 items × 2 runs ≈ 4,800 cells per target ≈ 4–6M tokens.

## 10. Risks

1. **Fidelity is the main risk, not correctness.** A panel with perfect answers that does not respond to rules the way
   the real target does makes C4' meaningless. Measured: LiveMath-style difficulty is lower (M+ 24% solved against 1%
   on real items); SearchQA-style is easier with context (91% against 74–78%). The answer-form codes (69% of real
   SearchQA failures) are not yet exercised. Mitigation: family F3, difficulty parameters, and the panel-validity study.
2. **Shared-view errors.** Checks that see the generator's view inherit its scope errors (the row checker agreed 25/25
   with 3 wrong keys). Every independent check must see a strictly wider or different view: the whole page, the
   rendered text only, or a second implementation path.
3. **Source-relative against world truth.** Lookup keys are correct for the frozen revision, not necessarily in the
   world: counts change with events after the revision, and many lists are thresholded (a "lowest-capacity stadium in
   Brazil" among the listed ones is not a world fact). Fine when the context carries the source; risky when a rule
   teaches "trust your own knowledge".
4. **Memorisation.** Blind solves reach 8/20 and 8/25 on famous list pages, so long-tail sources are preferable.
5. **Test-pool overlap.** OfficeQA pages, ALFWorld games and SpreadsheetBench templates may coincide with test items.
   The exclusion must be done by protocol code with test access (hash lists), never by the operator. This pilot used
   only Wikipedia and self-generated mathematics.
6. **Shortcut rules versus mirror fidelity.** The real LiveMath pool rewards "pick meta when present" (68/68). A
   mirror panel cannot penalise it; only a contrast panel can. Whether that rule is allowed is the owner's and D7's
   call.
7. **Infrastructure noise.** The deepseek route returned 429 and 503 errors (2/25 SearchQA solves failed outright). A
   failed call must be recorded as unknown, never as a solver failure (this pilot excluded them).
8. **My own pilot bugs.** The 80-row truncation (one key defect), the `Fraction(...)` parser (3 lost specs) and the
   `visibility:hidden` padding all came from the pilot generators. They show that L0 library tests and L3 audits are
   needed, not optional.

## 11. Recommendation

**Build it, as a family library with executable references, and make its validity the first experiment.**

1. **Library first** (v5, about 1 week; estimated):
   - LiveMath-style: the run-2 builder plus the 2-of-3 tiebreak, the parser fix, balanced letters, a lint for the
     carrier text, finite families only, and GLM's wrong beliefs used as distractors.
   - SearchQA-style:
     - no truncation;
     - page-scope re-derivation;
     - icon alt text and `data-sort-value` for signs; drop `visibility:hidden` spans;
     - F2 only on closed lists, or the scope rendered from the section heading;
     - the year or section rendered into the clue;
     - the F3 answer-form family.
   - OfficeQA-style: Treasury-Bulletin-like sources, the operation library, a span-aware parser, back-translated
     paraphrases.
   - SpreadsheetBench-style: openpyxl schemas, k = 3 data variants, a second reference path through LibreOffice.
   - ALFWorld: fresh train games, excluded by hash.
2. **Audit protocol** (§5):
   - L0 library tests;
   - L1 mechanical checks, including the page-scope check;
   - L2 executable cross-check with a 2-of-3 tiebreak. Drop the yes/no audit and the reasoning recompute;
   - L3 acceptance at 0 defects in 60 per family, plus 5 items per family per step;
   - L4 dead-item triage.
3. **First experiments:**
   - (a) **Panel validity.** Correlate Δ on generated mirror panels with Δ on the target's real training pool across
     about 6 existing Skill variants. Estimated 4–6M tokens per target.
   - (b) **Instability.** The parent re-run twice on 200 generated items, to replace the assumed 15.5% flip rate in §7.
     Estimated 0.4M per target.
4. **Wire it into C4'** only if (a) shows sign agreement:
   - about 200 fresh items per similar target per step;
   - non-inferiority with a margin (statistics from D8);
   - a separate contrast sub-panel;
   - generated failures used as mechanically diagnosed trigger sets.

   Keep the registration's rule that these items are selection material and never transfer evidence.
5. **What not to claim:**
   - "Guaranteed answers" means executable references with audited residual error rates (LiveMath-style keys 52/52;
     SearchQA-style page-scope keys 22/25 before the fixes), not proof.
   - An accepted generator is not evidence that a rule transfers.

## 12. Artifacts, commands and references

**Report and copies (Mac):** `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D6/`

- `report.md` (this file).
- `pilot/`: run-1 scripts `common.py`, `gen_livemath.py`, `gen_searchqa.py`, `sandbox_runner.py`.
- `out/`: run-1 outputs.
- `v2/`:
  - run-2 scripts `gen_livemath2.py`, `gen_searchqa2.py`, `run2.sh`;
  - `v3_forward_smoke.py`, `tiebreak_probe.py`, `page_scope_check.py`, `cell_markup.py`, `c4_power.py`;
  - statistics scripts `stats_livemath.py`, `stats_searchqa.py`, `stats_other.py`, `officeqa_ops.py`,
    `diag_counts.py`;
  - `verify_v3_office.py`, `audit_view2.py`.
- `v2/out/{livemath,searchqa,v3forward,tiebreak,scope}/`: results.json, items.json, summary.json, ledger.json,
  pages.json, pages_full.json, scope_report.json, probe.json.
- `v2/audit/`:
  - my independent audits `verify_run2_livemath.py`, `brute19.py`, `audit_searchqa2.py` (output in
    `audit_searchqa2_output.txt`);
  - `cp.py` (exact intervals; outputs `cp_output2.txt`);
  - `c4_power_output.txt`.
- `v2/audit_*_run*.txt`: compact audit views.
- `v2/logs_copy/`: run logs and status files.

**Remote (new machine):** `/data/feasibility/D6/pilot/` (run 1, with `pylib/` holding sympy 1.14 for the sandbox) and
`/data/feasibility/D6/v2/` (everything else, with `logs/`).

**Commands** (new machine, `ssh -o BatchMode=yes <datatools-login>`, proxy on in the same
shell):

```
cd /data/feasibility/D6/v2 && nohup bash -ic 'bash run2.sh' &     # run 2 (run2.sh runs proxy_on, then LiveMath, then SearchQA)
nohup bash -ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/D6/v2 && /root/continual-alf-prep-20260928/env/bin/python v3_forward_smoke.py > logs/v3forward.log 2>&1' &
nohup bash -ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/D6/v2 && /root/continual-alf-prep-20260928/env/bin/python tiebreak_probe.py > logs/tiebreak.log 2>&1' &
nohup bash -ic 'proxy_on >/dev/null 2>&1; cd /data/feasibility/D6/v2 && PYTHONPATH=/data/skillopt-work /root/continual-alf-prep-20260928/env/bin/python page_scope_check.py > logs/scope.log 2>&1' &
python3 -I v2/audit/verify_run2_livemath.py ; python3 -I v2/audit/audit_searchqa2.py v2/out ; python3 -I v2/c4_power.py   # local, free
```

**Code read** (repository, read-only):

- `skillopt/coevo5/forward.py` (module docstring; `build_panel`; `_office` / `_live`);
- `skillopt/coevo5/research.py` (`Wikipedia`, `_Page`, `material`);
- `skillopt/coevo5/protocol.py` (lines 15–28 `SIMILAR_PAIRS`, `FORWARD_STYLES`, `similar_targets`;
  `MIN_SIMILAR_DELTA = 0`; `TAXONOMY`);
- `skillopt/coevo5/gate.py` (`_similar`, lines 83–99);
- `skillopt/coevo5/step.py` (lines 584–598: `forward_panel_short`);
- `skillopt/continual_eval/backends.py` (`LIVEMATH_CONTRACT`, `score`);
- `skillopt/envs/searchqa/evaluator.py`;
- `docs/handoff/coevo5-registration-v6-20261017.md` §1.1, §7, §8, §12.8.

**References:**

- Clopper & Pearson (1934), exact binomial intervals.
- Hanley & Lippman-Hand (1983), "If nothing goes wrong, is everything all right?" (the zero-defect bound
  1 − 0.05^(1/n), about 3/n).
- Gao et al. (2023), PAL: program-aided language models; Chen et al. (2022), Program of Thoughts. Both compute answers
  with code instead of model arithmetic.
- Wang et al. (2023), Self-Instruct: model-generated tasks need filtering.
- Ma et al. (2024), SpreadsheetBench: several test spreadsheets per instruction, OJ-style.
- Shridhar et al. (2021), ALFWorld.
- Dunn et al. (2017), SearchQA.
- Stojanovski et al. (2025), Reasoning Gym: procedurally generated tasks with verifiers *(claim; not re-checked in this
  session)*.
- Standard results used in my audit: Pick's theorem (#31); Smith's gcd-matrix determinant (#16); Cayley's formula
  (#11); the splitting of S_n classes in A_n (#19).
