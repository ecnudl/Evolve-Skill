# Critique of spec-engineering.md -- LENS 1: evidence and statistics

Critic: adversarial reviewer (evidence/statistics lens), read-only. Date: 2026-10-21 (restarted 19:20 CST; the 18:08 stub left by an earlier attempt was empty and is replaced).
Target: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/spec-engineering.md
Calculations: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/critic-ee-calc/
Status: COMPLETE (see end).

Conventions: every number is marked "measured (source path:line)" or "estimate (assumptions)". Severity: fatal / major / minor.
Findings are written for implementers (English); the owner summary at the end is plain Chinese.

## Findings

Abbreviations: SPEC = scratchpad/execskill/design/spec-engineering.md; FP = understand/feasibility-prototypes.md;
DP = understand/data-and-pools.md; DIR = docs/handoff/direction-recommendation-20261021.md; CALC = critic-ee-calc/calc-output.txt
(produced by critic-ee-calc/calc.py: pure arithmetic and Monte Carlo, no data, no API). All scratchpad paths are under
/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/.

### F1 [fatal] The LiveMath "stronger result" artefact is forbidden for generators only; the engineer can learn it and it will pass acceptance
- Attacked text: SPEC:766-767 "the `STRONGER_OPTION` meta sentence is forbidden (A8: no training-label regularities ...)" and
  SPEC:907 "balanced keys, no meta-option regularity" -- both sit in the GENERATOR gates. Nothing in the engineer checks
  C1-C9 (SPEC:785-793), the leakage check, the decision rule (SPEC:851-866) or the readouts (SPEC:961-985) mentions it, while
  the engineer is shown "for failed QA/Sheet run items the reference answer" (SPEC:687).
- Why it is wrong: the meta option ("One of the remaining options is correct, but a stronger result can be proven.") occurs in
  129 of 283 LiveMath training items and is the key in all 129 (measured: skillopt/coevo5/protocol.py:220-222; FP:304-305
  "'pick it whenever present' estimated 76% vs TC 33%"); 42-84% of E4's LiveMath gains came from it (measured, FP:366-368).
  A 300-byte procedure (`applies`: the sentence is among the options; note: "the option saying a stronger result can be proven
  is correct") moves LiveMath accuracy from about 33% to about 76% (estimate from D9, FP:304-305, if the solver follows the note), i.e. about 5x the LiveMath
  MDE: it is accepted with near certainty, labelled a learned Skill, becomes an "origin" bench that changes the
  similar/dissimilar sets of the readout, and inflates the LiveMath test score if the test panel has the same construction.
  The evidence base already states that learning this option "is not learning" (DIR:35) and that LiveMath must be reported split by
  the option's presence (DIR:80).
- Fix (registered rule, zero cost): (a) LiveMath decision metric = mean d over NON-meta items only; meta items are run,
  reported separately, never gating (or exclude them from the LiveMath supply: 154 non-meta items remain, estimate from
  283 - 129); (b) a fixed engineer check C10 rejects any procedure whose source, string literals or emitted notes (on all stored
  trajectories) contain the STRONGER_OPTION sentence or a fragment of >= 3 of its words, or that returns different notes for
  items that differ only in the presence of the meta option (fixture pair test); (c) every LiveMath table (acceptance and
  test) is split meta / non-meta with the non-meta stratum primary (DIR:80).

### F2 [fatal] The examiner's predictive-validity gate (claimed novelty #1) cannot retire or validate anything at the registered sizes
- Attacked text: SPEC:910-916 "If |Delta_real| >= m_b with m_b = 0.5 x MDE_b ... agreement iff Delta_gen x Delta_real > 0 ->
  credit; otherwise strike ... Two consecutive strikes retire g. Benches with one step ... can give at most one check per
  generator"; SPEC:924-929 ("validated" = >= 1 credit and no strike); SPEC:987-989 (novelty claim "the examiner's
  predictive-validity gate").
- Why it is unfalsifiable: (1) In the default plan SpreadsheetBench, OfficeQA and LiveMath have ONE step each (SPEC:543-545),
  SearchQA has no generators (SPEC:757), and ALFWorld's "generators" are filters over REAL unused games (SPEC:776-777), so on
  ALFWorld the "generated vs real" comparison is two samples of the same real distribution: agreement there says nothing
  about synthetic task generation. (2) The sieve passes only candidates with Delta_gen >= 0 (SPEC:801), so a "credit" is
  earned exactly when the real effect happens to be >= m_b: the credit measures the CANDIDATE, not the generator.
  Simulation (estimate, CALC §3; real effects drawn around 0 with sd 0.5-1 SE, which matches the evidence that rule-sized
  effects are 0-3 points (DIR:15)): with one check per generator P(retired) = 0 by construction; a USELESS generator
  (validity rho = 0) is "validated" with probability 0.13-0.30 versus 0.19-0.41 for a GOOD one (rho = 0.8); 55-74% of checks
  carry no information; even with 3 checks a useless generator is retired with probability only 0.03-0.09. (3) Delta_gen is
  in-sample: generator material is "3-5 public training items of the run slice" (SPEC:705), the same slice whose failures the
  engineer fixes ("rule echo": topic-chosen material makes the panel echo the rule, measured critique FP:200-201), and the
  engineer may iterate against "per-item generated outcomes" in a fix round (SPEC:802) before Delta_gen is read. (4) Delta_gen
  (self-test unit) and Delta_real (acceptance unit) are measured in different serving windows; regimes alternate within
  15-minute bins and moved the same OfficeQA text by +22.5/+24.2 points between windows (measured, FP:309-314), and E4's
  same-text estimates of two runs correlated -0.50 (measured, FP:365).
- Fix: (a) Measure validity as CONCORDANCE over many contrasts, not one sign: inside every acceptance unit, run a sealed
  generated subset (never shown to the engineer, material drawn only from the detector HOLD half or items the engineer
  never saw) with ALL arms (S', S, C, P, twins) interleaved with the real items; each step then yields 4-8
  (Delta_gen, Delta_real) pairs in one window. Register: validity established iff, pooled over steps and benches,
  >= 12 informative pairs and a one-sided permutation test of Kendall's tau gives p < 0.05; until then every report says
  "generator validity not established". (b) In the pilot the sieve is RECORDED, not gating (see F3), so pairs exist for
  rejected-by-sieve candidates too, removing the one-sidedness the spec itself admits (SPEC:917-920). (c) Retirement:
  a generator whose pooled tau has a one-sided 95% upper bound < 0.2 after >= 12 pairs is retired. (d) Drop the
  predictive-validity gate from the novelty list unless the owner accepts the extra arms' cost on the generated subset
  (estimate: <= 60 generated items x 4-5 arms x 1 run per step, about 0.3-1.5M solver tokens per step at the 8.1 anchors).

### F3 [major] The generated-item sieve vetoes the only real decision on three benches, contradicting the evidence-based "stop" list
- Attacked text: SPEC:799-803 (sieve: "Delta_b(S' - S) >= 0 on (a) ... AND Delta >= -0.05 on every set in (b)"; failing ->
  "skip 4.6") and SPEC:861 (decision condition 5: "the sieve (4.5) passed"); SPEC:776 (ALFWorld "generated" sets are real
  games, used in the same sieve).
- Why it is wrong: (1) DIR:31 lists "using automatically generated items or model-written checkers as a GATE or as evidence"
  under STOP, on E1 (+13 generated vs 0 real, FP:353-356) and E9 (generated panel saturated at 0.891, missed the real -9.5
  harm, FP:371-377). Condition 5 is exactly such a gate. (2) Part (b) is a cross-bench veto-only regression check -- the E9
  direction that DIR:33 calls "a disguised validation set" -- with generated items standing in for real ones. (3) For
  ALFWorld the sieve runs on up to 30 real unused games x 2 runs, i.e. a REAL screen in front of the real acceptance: a
  screen/confirm design with a real validation batch. (4) Cost in power: a sieve with no validity passes a candidate with
  probability ~0.5 regardless of its real effect (estimate), so on the one-step benches it halves an acceptance probability
  that is already low: a true +5-point package is accepted with probability 0.27 (SpreadsheetBench), 0.33 (OfficeQA), 0.52
  (LiveMath), 0.43 (ALFWorld) by a single contrast before IUT and sieve losses (estimate, CALC §1). A sieve-rejected
  acceptance slice is "skipped" (SPEC:585-587) but on a one-step bench there is no later decision, so the bench ends empty.
- Fix: pilot and full run: the sieve gates only on engineering facts (C1-C9, fault rate); the generated-set deltas are
  recorded and feed F2's concordance test. Part (b) is reported, never gating. ALFWorld examiner sets are renamed
  "real screening sets" and either dropped (default) or made part of the acceptance batch (more real items in the one
  decision is strictly better for power than a separate screen).

### F4 [major] Arms that are identical by construction are run separately: avoidable noise inflates every MDE and the default pilot's non-inferiority readout is likely to fail on pure noise
- Attacked text: SPEC:851-866 (decision over ALL acceptance items, every arm run on every item), SPEC:871-874 (twins), SPEC:961-971
  (test readout F - C over all items; dissimilar pooled NI).
- Why it is wrong: routing is deterministic and known before dispatch (SPEC:880-883), and the shell's equivalence test
  guarantees byte-identical requests when no procedure fires (SPEC:214-216). On items where no NEW/REVISED/REMOVED procedure of
  S' applies, S, S' and P send identical request streams; on test items where no procedure of F applies, F and C are identical.
  Running them as separate cells only adds same-text noise (single-run same-text disagreement 0.049-0.161 depending on the text,
  measured cal-1, FP:309-312; "same-text rerun still flips 8-10% of items", DIR:17). Treating those d_i as structural zeros
  (one shared cell, d_i = 0) keeps the estimand (mean over all items) and cuts the MDE by x0.51-0.90 when 20-60% of items fire
  (estimate with D1's variance components, CALC §5): e.g. ALFWorld 134 x 1 at 20% fired: 0.073 -> 0.037. Conversely, without
  it, a package that never fires on ALFWorld still has to pass the pooled NI test there by luck: with origins SpreadsheetBench
  + OfficeQA the registered similarity table (SPEC:962-964) leaves ALFWorld as the ONLY dissimilar bench, and at 134 x 1 a
  package that never fires on it passes NI at -5 points with probability only 0.36-0.57 (estimate, CALC §6). The spec computes
  NI power only for the alternative pilot (SPEC:968-971).
- Fix: register "structural identity": before dispatch the registrar routes every item for every arm; items whose arms have
  identical routed procedure sets (same package code path) run ONE cell assigned to all identical arms and recorded
  `structural_zero`; statistics are computed over all items with these zeros. Twins on items where p is the only changed
  procedure reuse the S cell (S'-p == S there). Keep C as a deliberate duplicate of S only at the chain's first step (noise
  floor, SPEC:831). Report the fired share next to every MDE; the saved cells fund more items on ALFWorld/SearchQA.

### F5 [major] The headline MDEs are mislabelled as "measured" and borrow SearchQA noise for OfficeQA and SpreadsheetBench
- Attacked text: SPEC:543 "12.2 pts (measured design value: D1 smallest certifiable effect at 46 x 2 [FP F40])", SPEC:544 "10.3 pts
  (D1 at 37 x 4)", SPEC:886 "(D1 measured design values [FP F40])"; the column header "Acceptance MDE (1-sided 5%, power .8)"
  over LiveMath/SearchQA/ALFWorld entries copied from DP.
- Why it is wrong: D1's "smallest certifiable effect per pool" is a COMPUTED value from SearchQA same-text paired SDs
  (0.326/0.222/0.144 at k = 1/2/4) plus an assumed between-item spread tau 0.12-0.28, on deepseek-v4-flash and text changes
  (FP:272-276). Nothing was measured on OfficeQA or SpreadsheetBench, and OfficeQA's own noise is far larger: the same text on
  the same 60 OfficeQA items moved +22.5 [+11.5, +33.5] and +24.2 points between windows (measured, FP:313-314), SD 11.4 across
  four windows (DIR:17). DP's own OfficeQA estimate for 37 items is 14.2-16.6 points at one run (DP:349), and 4 runs cut only
  the run-noise share ("more items, not more runs buy power", FP:273). The LiveMath/SearchQA/ALFWorld entries are DP's
  TWO-sided values (DP:362-364: factor 2.80) placed under a one-sided header, and none includes DP's listed omissions (drift
  "2-3x on pi", the delta-squared term: DP:367-371). The new solver (v4.1-flash-1017, reasoning off) has no variance
  measurement at all. So the owner-facing sentence "OfficeQA and SpreadsheetBench can certify only effects of about 10-12
  points" (SPEC:549-551) is, if anything, optimistic, and it is presented with a "measured" label it does not have.
- Fix: relabel every MDE "estimate (assumptions: ...)". Register a zero-extra-cost variance check: the run unit already runs
  S with k >= 2 runs on SpreadsheetBench/OfficeQA (use those same-text pairs); on k = 1 benches add a duplicate-S arm on a
  registered 25% of the run slice (estimate: +0.1-0.6M solver tokens per step). Before dispatching an acceptance unit the
  registrar recomputes the MDE from the measured same-text discordance on the NEW model and writes it into the decision
  record; the report prints a power table for true effects +3/+5/+8/+10 (CALC §1 gives the pre-measurement version: a +5
  effect is accepted with probability 0.27 / 0.33 / 0.52 / 0.43 on SpreadsheetBench / OfficeQA / LiveMath / ALFWorld by one
  contrast). The x1.1-1.2 IUT factor is fine (CALC §2: 1.13-1.16) and should cite its derivation.

### F6 [major] The placebo's extra calls are not "conservative"; a harmful placebo silently turns condition 2 into a no-op; vetoes are uncontrolled
- Attacked text: SPEC:842-846 "P0 makes one second call on EVERY fired QA item ... (controls the 'second look' effect; P
  therefore makes at least as many second calls as S' -- conservative). SpreadsheetBench: one repair call on fired items with
  'Check your program once more.' and no run report. ALFWorld: never vetoes (the veto effect is not placebo-able; reported
  separately)."
- Why it is wrong: (1) "At least as many calls" is conservative only if a content-free second look HELPS. If it hurts
  (intrinsic self-revision without new information often lowers accuracy: literature, not measured in this project; a blind
  "check your program once more" can break a working program), P is pushed DOWN on items where S' never made a second call,
  and condition 2 (LB of S' - P > 0, SPEC:858) becomes easier than condition 1, i.e. no control at all. (2) Placebo texts are
  not inert in either direction: cal-1 -9.8 to +3.6 points (measured, understand/coevo5-method.md:342-344); E+P3 -0.081 on the empty scaffold, S+P3 -0.023
  on the task card (measured, FP:250-254). A placebo whose own effect P - S is negative makes condition 2 strictly weaker
  than condition 1 and the four-arm design collapses to S' vs S without anyone noticing. (3) "Reported separately" for vetoes
  has no matching row in §10 or §7.5: ALFWorld veto procedures are tested against a placebo that controls only note length.
  (4) Minor: P0's note id should be indistinguishable from a real procedure id, and the placebo note has prose form while
  real notes are tables/state lists (form mismatch).
- Fix: (a) matched calls: run S''s `after_reply` / `sheet_feedback` in shadow mode on P's OWN first reply and make P's
  content-free second/repair call exactly where S' would have made one (P then matches S' in call count and selection);
  (b) every decision record prints P - S with its 95% CI, and a registered rule says: if UB95(P - S) < 0 the placebo contrast
  is "non-informative (placebo harmful)" and the acceptance is reported as resting on condition 1 alone; (c) ALFWorld: a veto
  placebo that removes the same NUMBER of commands, drawn by item hash from commands the procedure did not veto and that
  mention neither the goal object nor the goal receptacle of the public task sentence; if the owner rejects it, every
  ALFWorld veto result carries "veto effect not placebo-controlled"; (d) P0's id follows the procedure id grammar and its
  note mimics the dominant note form of S' (e.g. a key/value list of irrelevant facts).

### F7 [major] The transfer labels fire under the null, contradict A11, and skip the measured format check the evidence requires
- Attacked text: SPEC:956-960 '"general": fires on >= 2 benches; on at least one non-origin bench with >= 20 twins, tau point
  estimate > 0 and 95% LB > -Delta_NI'; '"this bench only": fires on < 5% of items of every non-origin bench, or every
  non-origin tau point estimate <= 0'.
- Why it is wrong: a non-inferiority bound is used as evidence of benefit. Under tau = 0 the "general" condition holds per
  bench with probability 0.07-0.42 and, over 2-4 non-origin benches, 0.14-0.89 (estimate, CALC §4: discordance 0.08-0.21,
  20-100 twins). "This bench only" can be assigned from the enable rate alone, which A11 forbids ("never from enable rates
  alone"); and the labels overlap (a procedure can be "general" and "harmful elsewhere" at once). The established evidence
  also requires that any rule labelled general passes a MEASURED "does not change the answer format" check (DIR:48), absent here.
- Fix: three mutually exclusive labels with fixed precedence: "harm established" (Holm-adjusted over procedures x non-origin
  benches, UB95(tau) < 0) > "transfer established" (Holm-adjusted LB95(tau) > 0 on >= 1 non-origin bench AND the format check
  below passes) > "unresolved". "Inactive elsewhere" (fires < 5%) is a descriptive tag, not a transfer label. Format check:
  on the twin items, answer-tag rate, JSON-answer rate and median reply length of F vs F-p differ by less than registered
  tolerances (e.g. 5 points, 5 points, 25%).

### F8 [major] Format can re-enter the learnable part through free-text notes -- the exact mechanism of the measured negative transfer
- Attacked text: SPEC:220-226 (notes are free text appended to the user JSON), SPEC:791-793 (C8 checks only the system-prompt
  sha256 and the reply channel); design-v0 §1 item 4 ("format must not enter the learnable part").
- Why it is wrong: every measured negative transfer in E4/E9 was an answer-form conflict: ALFWorld card -26.7 and
  SpreadsheetBench card -20.0 on OfficeQA, LiveMath seed -9.5/-8.1, mechanism "answer-only replies rise from 23% to ~60%"
  (measured, FP:363-377). A note such as "give only the final number" from an OfficeQA procedure whose predicate ("has numbers
  / has a table") also fires on LiveMath, SearchQA or SpreadsheetBench reproduces that mechanism; C8 does not see it, because
  the system prompt is untouched. On SearchQA, about 3/4 of task-card failures are surface form (FP:302-303), so the only
  gains reachable there by notes are format advice: the SearchQA steps of the alternative pilot mostly test this channel.
- Fix: typed notes (registered schema: extracted values with labels/units, computed values, state summaries, checklists;
  no imperative text about answering), a fixed lexical filter in C9 over every note emitted on all stored trajectories (answer,
  respond, reply, return only, format, letter, tag, JSON, code fence, "only the ..."), and the format check of F7 reported in
  every acceptance and test table per arm.

### F9 [major] The detector gate is base-rate-driven, double-counts runs, and can be passed by restating the outcome
- Attacked text: SPEC:748-750 "n_fired >= 10 cells; ... accept iff Wilson 90% lower bound of precision > base, AND precision /
  base >= 1.2, AND recall >= 0.10"; detector inputs = trajectory views (SPEC:700-704).
- Why it is wrong: (1) At base failure 0.75 (OfficeQA card about one quarter right, design-v0 §1) a detector must be 10/10 or
  15/15 precise to pass; at base 0.5 it needs 8/10 (estimate, CALC §8): acceptance depends on the bench's base rate, not on
  detector quality. (2) "Cells" include both runs of an item (SpreadsheetBench and OfficeQA run slices have 2 runs), so the
  Wilson bound treats correlated cells as independent. (3) Trajectories carry outcome proxies: ALFWorld episodes end early
  when won, so "used all 50 steps" is almost the failure label; QA "no answer tag / truncated" are failures by the scoring
  rule. A model-written detector that restates these passes the gate with zero new information. E1 already found
  model-written checks at balanced accuracy 0.47-0.55 on held-out items with "only form checks transfer" (measured, FP:347-352).
- Fix: detectors see a PREFIX view (ALFWorld: first min(T, 20) steps, no step count, no terminal observation; QA: the
  features of the mechanical categories masked), must show INCREMENTAL lift on cells not flagged by any mechanical detector,
  use an item-clustered interval (items, not cells) and a base-rate-free criterion (odds ratio LB > 1.5), and are deduplicated
  against existing detectors (Jaccard of fired sets < 0.8). Report "detectors accepted: 0" honestly when nothing passes.

### F10 [major] Reading the test sets at the end of a pilot that is also the prefix of the full run makes every later test read a second read; OfficeQA and LiveMath readouts ignore registered evidence
- Attacked text: SPEC:816-817 (§4.8) "Pilot: once at the end of the pilot (A12), arms F, C, P ... + twins"; SPEC:1158 "D9 ... 默认：是"
  (the pilot is the prefix of the full run); SPEC:961-971 (one read per test set, single window, LiveMath not stratified).
- Why it is wrong: the evidence base says the test sets are read once, after the method is frozen, with consent (DIR:40).
  With D9 = yes, the pilot's test read happens mid-chain; every owner decision taken afterwards (continue, order, D7,
  thresholds) is test-informed, and the full run's final read re-reads the same five panels with a package that descends
  from the pilot's. A12 fixes a pilot test read, so this is a CONTRADICTION between A12 and D9's default that the spec does
  not flag. Separately, the established reading rules are not applied: "OfficeQA must be read in two windows, stratified by
  response regime, with the regime pre-specified as primary" and "LiveMath reported separately with and without the
  stronger-result option" (DIR:80); OfficeQA's window effects are +22-24 points (measured, FP:313-314).
- Fix: owner decision with two registered options and costs: (A, recommended) D9 = no: the pilot is exploratory, its test
  read is labelled "exploratory read; panels will be re-read", and the full run's confirmatory claims rest on its own final
  read; (B) D9 = yes but the pilot reads a seeded half of each test panel and the full run reads the sealed other half
  (MDE x1.41; OfficeQA 86 items is then descriptive only). In both: OfficeQA read in two windows with the regime
  stratification of DIR:80 (cost: one extra OfficeQA read, estimate 3 arms x 172 x ~6-8k = 3-4M), LiveMath split per F1.

### F11 [major] Giving the engineer D3's tracker contract re-creates D3's "induction = transcription" confound and contradicts the spec's own R9
- Attacked text: SPEC:780-781 "D3's tracker contract and replay verifier for ALFWorld procedures and fixtures [FP F10, R1-R3]"
  versus SPEC:1124 (R9 mitigation: "the hook API document is generic and contains no procedure; the engineer sees failures,
  not designs").
- Why it is wrong: D3's critic found that the tracker was transcribed from a dictated interface ("EXACTLY these keys:
  'reached' ... 'not_reached_yet' ... 'carrying'" plus v3 failure statistics), which explains its 97.7% agreement (measured,
  FP:65-69, confound 3). If the contract reaches the engineer, an accepted ALFWorld tracker is the designers' idea executed by
  GLM, not learned from failures; and that idea itself came from hindsight over the same 57 pool games that serve as the
  step-1 run slice (D14's 55/57 came from walkthrough metadata, FP:115-120).
- Fix: the D3 contract is used for the fixture `fx-alf-tracker` and the replay harness only; the engineer receives the generic
  hook API. If the owner wants the template in the engineer input, every procedure derived from it is labelled "dictated"
  and excluded from learned-Skill claims (AGENTS.md: code availability is not evidence; transcription is not learning).

### F12 [major, verify with code] ALFWorld acceptance on seen rooms can reward room-specific procedures that cannot transfer to valid_unseen
- Attacked text: SPEC:561-570 (ALFWorld supply = json_2.1.1/train games, stratified by task type only) and the test panel
  `valid_unseen` (SPEC:566, 606-607).
- Why it is risky: by the ALFWorld/ALFRED dataset convention (external fact, not verified in this project) train games reuse a
  limited set of room layouts, the task directory name ends in the scene/floorplan number, and "unseen" means rooms absent from
  train. The engineer sees run-slice observations (receptacle lists, where objects were found). A procedure that fingerprints
  a room by its receptacle list and prioritises its instance names ("cabinet 6", "countertop 2") can pass acceptance on other
  games in the same rooms and transfer nothing to the test rooms. The C4 leakage check (SPEC:787-789) only looks for reference
  answers, not instance literals.
- Fix: (a) `make-items` records the scene id parsed from the game path (registrar only; the engineer never sees paths) and the
  acceptance slice is drawn from scenes disjoint from the run slice and from every trajectory shown to the engineer (supply
  3,514 makes this cheap); verify the parse with code first; (b) C4 for ALFWorld rejects receptacle-instance literals
  (regex `\b(cabinet|drawer|shelf|countertop|sidetable|dresser|desk|garbagecan|fridge|microwave|sinkbasin|stoveburner)\s+\d+\b`);
  (c) report acceptance gains on seen-scene vs unseen-scene items if both occur.

### F13 [major] "One-shot FRESH-batch acceptance" is claimed as novelty, but on the first two benches of the default order the batches are a reused development set
- Attacked text: SPEC:529-532 ("Fresh = never consumed in route B's own history ... Prior use ... DISCLOSED"), SPEC:987-989
  (novelty: "one-shot fresh-batch acceptance with placebo and card-only arms").
- Why it is wrong: A1 legitimately defines freshness method-side, but the evidence says OfficeQA's 74 items "have been used
  repeatedly by four pilots and are in effect a development set" (DIR:91) and DP finds 0 method-side-fresh items on OfficeQA,
  SpreadsheetBench and ALFWorld's pool (DP:349-352). The task cards were written after those items were viewed (DP:399-400) and
  design-v0's procedure ideas (exact computation for OfficeQA, table extraction, open-surfaces-first for ALFWorld) were derived
  from failures on these very items. An acceptance there is not a confirmatory test of those mechanisms, and calling it
  "fresh" in a paper would mislead.
- Fix: every decision record carries `freshness = "route-B-unused; method-side reused (dev set)"` for OfficeQA,
  SpreadsheetBench and the ALFWorld pool, `"never used"` for HF-validation SearchQA rows and unused ALFWorld train games; the
  fresh-batch novelty claim is restricted to the latter; the owner summary says this in plain words. This is one more reason
  for the alternative pilot order (owner decision #1).

### F14 [minor] The 2% fault cap mixes machine contention with procedure faults and is effectively "at most one cell" on SpreadsheetBench
- Attacked text: SPEC:354 (child wall alarm 3 s), SPEC:448-451 ("up to ~9-10 CPU-equivalents at peak (estimate)" on 7 CPUs),
  SPEC:860 (cap 2% of S' cells).
- Why: a wall-clock timeout under bursty oversubscription is booked as a procedure fault; at 46 x 2 = 92 S' cells, two faults
  (2.2%) reject the candidate. Faults also fail open, pulling S' toward S (the spec's R12).
- Fix: a wall timeout whose child CPU time is < 50% of RLIMIT_CPU is `sandbox_contention`: retried once in a fresh child and not
  counted; the cap is "max(2%, 2 cells)" with per-arm fault counts in the decision record.

### F15 [minor] Acceptance twins are causal but uninformative at the registered sizes
- Attacked text: SPEC:871-876 (f_acc = 0.5 of fired items; "causal").
- Why: on SpreadsheetBench/OfficeQA the twin sets are 6-14 items, per-procedure MDE about 18-28 points (estimate, CALC §7); on
  ALFWorld 20-40 games, 15-21 points. Only SearchQA reaches 5-8 points.
- Fix: say "descriptive, MDE X" next to every acceptance twin estimate; on scarce benches twin 100% of fired items (cost is
  fired items only) and reuse S cells where S'-p == S (F4).

### F16 [minor] Test-read runs per item are never stated
- Attacked text: SPEC:606-607, SPEC:933-941. The readout MDEs and the 33-57M test-read cost (SPEC:1009; MAP §4.10 assumes 1 run)
  depend on it. Fix: register runs per test item per bench (default 1; OfficeQA 1 per window x 2 windows per F10).

### F17 [minor] A percentile bootstrap LB at 37-46 items is anti-conservative
- Attacked text: SPEC:853-855. Percentile intervals under-cover at small n (standard result; not measured here), so the
  nominal 5% false-accept rate per contrast is likely a few points higher on OfficeQA/SpreadsheetBench.
- Fix: use an exact paired sign-flip randomization test (or BCa) for d and e on benches with < 100 items, and report the
  realised false-accept rate of the step-1 duplicate C == S as a calibration check.

### F18 [minor] One placebo arm, where the established practice asks for at least two
- Attacked text: SPEC:827-850 (one arm P). DIR:39 requires "at least two equal-length placebos" per comparison. The per-item
  hashed draw averages over texts, but placebo-to-placebo variance (cal-1: -9.8 to +3.6) cannot be estimated from one arm.
- Fix: at least at each bench's first acceptance, add P2 (same rule, different hash salt); report P - P2 as the placebo noise.

### F19 [minor] "The canonicaliser can therefore not flip signs between arms" is wrong as stated
- Attacked text: SPEC:279-280. Applying it to every arm makes arms comparable, but the effect remains CONDITIONAL on it: D3's
  tracker helped with canonicalisation (rescued steps 41.0% vs 13.2%) and "hurt in the frozen loop" (measured, FP:58-64).
- Fix: state "ALFWorld effects are conditional on the registered canonicaliser; route-B ALFWorld scores are not comparable with
  v3's frozen-loop scores"; keep R5's rescue-share rule.

### F20 [minor] Some cost numbers are invented or exceed their own caps
- Attacked text: SPEC:997 (OfficeQA package arms "x1.4: notes + compute round trip on ~40% of items": the 40% is an assumption,
  and the smoke uses OfficeQA fixtures, so it stays unmeasured until the pilot); SPEC:1013 ("The alternative pilot can exceed
  the 100M cap") for the RECOMMENDED pilot; SPEC:1022 ALFWorld accept cap 50M versus 56.7M for 134 games x 4 arms at the
  measured task-card rate (DP:389; that rate included all five cards, FP:121-122, so the spec's 42-50k per episode is a
  plausible but unmeasured derivation).
- Fix: label the 40% "assumption"; register that the pilot's per-step caps are re-derived from the first real cells of each
  bench (1.3 x measured per-cell cost x planned cells) before its acceptance unit; tell the owner in the D1 text that the
  recommended pilot's upper estimate exceeds the cap and which unit is dropped first (the twins, then the P2 arm).

### Contradiction paragraphs (working assumptions versus hard facts)
- A12 + D9 default: see F10 (pilot test read before the method of the full run is frozen).
- A8 + the default order: A8's "two consecutive disagreements retire the generator" cannot fire on one-step benches
  (SpreadsheetBench, OfficeQA, LiveMath) and ALFWorld has no synthetic generators; see F2.
- A11: the spec's "this bench only" label uses enable rates alone; see F7.
- design-v0 "format must not enter the learnable part" versus free-text notes; see F8.
- DIR:31/:33 (stop using generated items as gates; veto-only cross-bench checks are a disguised validation set) versus the
  sieve's condition 5 and part (b); see F3. design-v0 step 5 calls the self-test "only a sieve", which the spec turns into a veto.

## Ideas worth keeping in the synthesis
1. One seeded order per bench cut into consecutive slices plus a write-once consumption registry fsynced before dispatch, with
   `skipped` slices and redo-on-same-items (SPEC:§2.2-2.3, §1.14).
2. IUT decision S' vs S AND S' vs P with the L/H rule, block-stratified bootstrap and the 0.02 minimum (SPEC:851-866) -- after
   the F6 matching fix.
3. C == S at the chain's first step as a built-in same-text noise floor (SPEC:831).
4. Placebo as a DECISION arm, length-matched by shadow-running S''s procedures, texts drawn per item by hash from a registered
   corpus (SPEC:836-841); the related-work note found no learning loop with a placebo in its acceptance rule.
5. The zero-call equivalence test (empty package == frozen solver, byte-identical requests) (SPEC:214-216): it also licenses
   F4's structural zeros.
6. Fail-open procedure faults with a cap, never infrastructure unknowns; deciding-receipt rule for multi-call cells (SPEC:§1.10,
   §1.5.2 step 5).
7. Canonicaliser registered for every ALFWorld arm, rescue share per arm, "interface-mediated" label when shares differ by > 10
   points (SPEC:R5).
8. Honest reporting rules: "not detectable at this size", never "no effect" (SPEC:549-551, R2); positioning table vs FlowEvo,
   CoEvoSkills, GRASP with restricted novelty claims; pre-stated code-form risk with the optional F_desc (code vs description)
   arm (SPEC:§7.5-7.6).
9. The flagged confound in the max_tokens probe (sent with reasoning on) turned into launch blocker S1-b (SPEC:§3.1 note).
10. Engineering fixtures instead of scarce real OfficeQA/LiveMath/SpreadsheetBench items in the smoke (SPEC:§9).
11. ALFWorld acceptance in four blocks with whole-block redo and no splicing across attempts, justified by measured drift
    (SPEC:§1.14).
12. Examiner solver usage charged to its own scopes so probing cannot starve acceptance (SPEC:§1.11).
13. D12's validity audit (accept a sieve-rejected candidate on an ample bench) -- generalise it as in F2/F3.

## Verdict

needs_revision. Two fatal findings (F1 LiveMath artefact unguarded on the Skill side; F2 the predictive-validity gate, a
claimed novelty, has no power to retire or validate a generator at the registered sizes) and eleven major ones. All have
concrete fixes; F1, F3, F5, F7, F10 (option A), F11, F13 are zero-cost registration changes; F4 SAVES budget; F2, F6, F8, F9,
F12 need modest code. None of them requires a model call to fix.

## 给负责人的白话摘要（中文）

这是对"工程与安全优先"那份登记稿（下称"工程稿"）的反方审查，只看"证据与统计"这一面：每个数字站不站得住、每条判定规则会不会被钻空子。
先解释几个代号：S′ 是候选新版本，S 是旧版本，C 是"只有任务卡"，P 是"安慰剂过程"（只给无关文字），F 是最后定下的版本；
"MDE"是在给定题量下有八成把握认出来的最小提升（单位：分）；"孪生格"是把同一道题拿掉某一条过程再跑一次，用来测这条过程本身的作用；
"出题程序"是考官写的、答案由程序算出的生成题；"预测效度"是看生成题上的新旧胜负方向是否和真实新题一致。

结论：需要修改，有两处致命问题，都有便宜的修法。

1. **致命：LiveMath 的"更强结论"选项没有挡住。** 工程稿只禁止"出题程序"利用它，没有禁止"工程师"写的过程利用它。
   LiveMath 训练题里有 129 道带这句选项，而且它在这 129 道里全是正确答案；工程师能看到失败题的参考答案，很容易写出
   "看到这句就选它"的过程，验收时会以大约 40 分的差距（D9 估计：从约 33% 升到约 76%）通过，被当成"学到的 Skill"。10/21 的方向建议已写明：学到这个不算学习。
   修法：LiveMath 的判定只按"不含这句选项"的题算；工程师的过程里出现这句话或按它挑选项，一律不收；读数分两层报告。
2. **致命：考官的"预测效度"关卡在登记的题量下什么也判不出来。** 默认顺序里，表格、财政公报、数学这三个 bench 各只有一次验收，
   规则要求"连续两次不一致才作废"，所以永远作废不了；SearchQA 没有出题程序；ALFWorld 的"生成题"其实是没用过的真实游戏，
   拿两批真题比方向，说明不了生成题好不好。我做的模拟：一个毫无用处的出题程序被判为"有效"的概率是 13% 到 30%，
   一个好的出题程序是 19% 到 41%，几乎分不开。这条又是工程稿列出的三项新意之一。修法：在每次验收的同一时段，
   用一小批封存的生成题同时跑所有组，每步得到 4 到 8 对"生成题差值、真题差值"，跨步骤累计后做一次登记好的一致性检验；
   攒够之前一律写"生成题的有效性未建立"。
3. **重要：生成题筛子成了唯一一次真实验收前的"一票否决"。** 10/21 的方向建议已经写明"不要用生成题当门"
   （E1：生成题上涨 13 分、真题上 0 分；E9：生成题测不出真实的 −9.5 分伤害）。在只有一次验收的 bench 上，这个筛子会随机砍掉
   约一半的机会。建议：试点里筛子只记录、不否决。
4. **重要：可以白捡的统计功效没用上。** 一道题如果没有任何新过程被启用，S′、S、P 三组发出的请求一字不差，分开跑只是在测噪声。
   改成"这类题只跑一次、三组共用"，MDE 可缩小到原来的 0.5 到 0.9 倍，还省钱。不这样做的后果之一：默认试点里唯一"不相似"
   的 bench 是 ALFWorld，一个在 ALFWorld 上根本不启用的包，也只有 36% 到 57% 的机会通过"不掉分"检验，纯属噪声造成的假警报。
5. **重要：几个关键数字标错了来源。** "SpreadsheetBench 12.2 分、OfficeQA 10.3 分"被写成"实测"，其实是用 SearchQA 的噪声推算的；
   OfficeQA 自己的噪声大得多（同一文字换时段差 20 多分）。新模型（deepseek-v4.1-flash-1017，关推理）的噪声完全没测过。
   修法：全部改标"估计"，验收前用跑题阶段的重复格实测一次再定。
6. **重要：安慰剂的"多一次调用"并不保守。** 安慰剂在每道启用题上都多问一次"再看一遍"，但"再看一遍"可能让答案变差，
   这会让"新版本比安慰剂好"更容易成立。修法：安慰剂只在新版本真的会多问的那些题上多问；每次都报告"安慰剂比旧版本"的差，
   如果安慰剂本身有害，就明说这一项对照失效。
7. **重要："通用 / 仅本 bench"的标签在没有任何效果时也常常贴上"通用"**（模拟：每个 bench 7% 到 42%，跨几个 bench 累计更高），
   而且"仅本 bench"可以只凭启用率贴上，违反了事先定的规则；方向建议要求"通用"必须先过"不改答案格式"的实测检查，工程稿没有。
8. **重要：格式会从"提示里的附注"偷偷回到可学习部分。** E4、E9 测到的负迁移全是答案格式冲突；工程稿只检查系统提示和最终回答
   没被改，没检查过程往提示里加的附注里有没有"只写数字"这类格式指令。修法：附注只许是结构化的数据，并加固定的格式词过滤。
9. **重要：试点最后读测试集，同时又把试点当正式运行的开头**，那正式运行最后的读数就成了"第二次读"，中间您做的决定都看过测试分。
   建议二选一：试点不当开头（推荐），或试点只读每个测试集的一半、另一半封存给正式运行。OfficeQA 要分两个时段读，
   LiveMath 按"有无更强结论选项"分开报，这两条是 10/21 方向建议里已有的要求。
10. 其余重要项：工程师不应拿到 D3 现成的"记事工具"接口（否则又是"照抄设计"而不是学习）；ALFWorld 验收题应避开跑题阶段出现过的
    房间布局；表格和财政公报的 91 道、74 道题对路线 B 是"没用过"，但对整个项目是反复用过的开发集，论文里不能叫"新题"。

这些问题里大半是改登记文字、零花费；"共用一次的格"还能省预算。按现有题量，表格和财政公报两个 bench 上真实 +5 分的过程
被收下的概率大约只有三成（再算上筛子和双重对照会更低），这一点应在试点前写清楚，这也支持工程稿自己建议的
"先 SearchQA、后 ALFWorld"的试点顺序（由您决定）。

Status: COMPLETE (2026-10-21).
