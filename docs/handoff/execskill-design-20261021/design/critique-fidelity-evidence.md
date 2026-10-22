# Critique of spec-fidelity.md -- LENS 1: evidence and statistics

Critic: adversarial reviewer (lens 1, evidence and statistics), read-only. Date: 2026-10-21.
Target: /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/design/spec-fidelity.md
Status: COMPLETE.

Conventions: every number is marked "measured (source)" or "estimate (assumptions)". Citations are path:line
(SP/ = /private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/execskill/).
Findings are for implementers (English); the owner summary at the end is plain Chinese.

Inputs read: the spec (all 1,003 lines), SP/design-v0.md, SP/understand/map.md (sections 0-5), the relevant facts of
SP/understand/feasibility-prototypes.md (F15-F18, F35-F55, K1-K11) and data-and-pools.md (F9-F15, sections 5-7),
docs/handoff/direction-recommendation-20261021.md sections 1-7, docs/handoff/related-work-execskill-20261021.md
sections 5-7. Numbers I computed are marked "estimate (assumptions)"; my calculations are inline Python runs whose
assumptions are stated next to each number (nothing was written to disk except this file).

## Findings (numbered; severity in brackets; most severe first)

Verdict: **needs_revision** (1 fatal, 9 major, 8 minor). The data plumbing (one seeded order, consecutive slices,
write-once registry, the A* request-hash subset, the IUT, the fair compute/repair shams) is sound. The rules that carry
the examiner-side and transfer claims are not: as registered they mostly measure noise, and one pass condition can be
met by construction.

### F1 [FATAL] The predictive-validity gate (G4) cannot tell a valid generator from a useless or biased one, yet it carries novelty claim 1
- Attacked text: spec-fidelity.md:719-723 ("eligible iff `|d_real| >= 0.05`; agreement iff `sign(d_gen) == sign(d_real)`
  (`d_gen = 0` counts as disagreement). Two consecutive eligible disagreements retire the generator"); :732 ("Examiner
  validated (the headline claim of the examiner side) iff >= 1 generator has >= 1 eligible agreement and no retirement");
  :687 (generator inputs are "from the run slices"); :813 (novelty (1) = "the examiner's predictive-validity gate").
- Why it is wrong:
  1. The yardstick is itself noise. The eligibility margin 0.05 is about 1 SE of `d_real` (SE ≈ 0.049 on SB 46×2,
     0.041 on OQ 37×4, 0.038 on ALF 134×1: estimate, SE = MDE/2.487 from the spec's own MDE column, spec:371-375). With
     no real effect, `|d_real| >= 0.05` still happens 19-31% of the time and its sign is a coin flip.
  2. The test is biased toward the failure it was meant to catch. Acceptance and engineering both push `d_real` positive,
     so a generator whose items always favour the candidate (the E1 pattern: +13 generated vs 0 real, FP F50,
     feasibility-prototypes.md:353-361) agrees whenever `d_real >= 0.05`. My inline simulation (estimate: `d_real ~
     N(delta, SE)`; `d_gen` on 40 generated items (20 games), 1 run, discordance 0.25; "E1-biased" = `d_gen` mean +0.13
     whatever the real effect) gives this. At a true real effect of +0.05, P(agree | eligible) is 0.91 (SB) / 0.93 (OQ)
     / 0.83 (ALF) for the biased generator, 0.66 / 0.68 / 0.59 for a valid one and 0.44 / 0.44 / 0.41 for a useless one.
     The biased generator is the MOST likely to be called "validated" (P = 0.47 per generator on SB/OQ against 0.34 for
     a valid one). With no real effect, all three are indistinguishable (P(agree | eligible) 0.41-0.48).
  3. The bias is the default, not a corner case. `G_acc` is drawn from run-slice items (:687), the items whose failures
     the engineer studied with references (:465, :552), and the generators target the same categories the engineer was
     told to fix (:545-546). This is the E1 set-up: generated variants of the learner's own training items.
  4. On SB/OQ/LM a generator gets at most one comparison (:725-728), so an E1-type generator can never be retired there,
     and the headline needs only one lucky agreement. The previous run of this review (SP/design/critic-fe-calc/sim-output.txt
     section C) estimated P("examiner validated") = 0.27-0.33 for the default pilot with useless or biased generators
     and no real effect, and 0.57-0.75 at +0.05. As registered, the headline is unfalsifiable in practice.
- Fix (modifies working assumption A8, so it needs the main agent's or owner's sign-off):
  (a) Run each `G_acc` draw under EVERY arm of the acceptance round (S', S, C, P and the twins), not only S' and S. One
      round then yields 4-6 (real, generated) contrast pairs. They include a negative control, P − S, which a valid
      generator must show near 0 on both sides; an "always +" generator fails it. Cost on SB: about +0.5M per round
      (estimate, 40 items × 2 extra arms × 3,000 tokens × 2 generators).
  (b) Draw `G_acc` sources from items the engineer never saw. Run the frozen generator code inside the registrar's
      sandbox on the acceptance slice's own public views (no role sees the outputs before the decision), or on a
      registered "generator-source" slice where supply allows (SearchQA, ALFWorld, LiveMath tier 2).
  (c) Replace sign agreement with a calibrated rule over the pooled pairs of a generator, all collected before the end of
      the run: "predictive" iff the slope of `d_gen` on `d_real` (errors-in-variables, or a rank correlation) has a
      one-sided 95% lower bound > 0. Require at least 8 pairs; with fewer, the status is `not evaluable`. Retire a
      generator when `|d_gen − d_real| > 1.96 × sqrt(SE_gen² + SE_real²)` on two pairs, not when the signs differ.
  (d) "Examiner validated" may be claimed only under (c). Otherwise the report says "not evaluable at these sizes",
      never "validated".

### F2 [MAJOR] On ALFWorld (and partly on QA/Sheet) the examiner's pass conditions can be met by construction
- Attacked text: :669-670 (the detector view contains `steps: [...]`, `format_flags`, `extracted_answer`); :674-676
  (acceptance on precision lift, binomial test and recall); :705-707 (ALFWorld "generator" = "a selection program over
  the GEN region ... truth = the simulator's `won`"); :712-718 (G2 band, G3 "N/A" on ALFWorld); :731 ("Examiner evolved
  ... iff >= 1 model-written detector passed 6.1, or >= 1 model-written generator passed G1-G3"); owner text :924 ③
  ("两个 bench 都有程序或模拟器算出的真值，考官两半都能进化").
- Why it is wrong:
  - Every ALFWorld failure is a 50-step timeout (68/68 and 56/56), and wins take a median of 9-10.5 steps
    (FP F15-F16, feasibility-prototypes.md:109-118). So `len(traj["steps"]) == 50` IS the verdict. Any model-written
    ALFWorld detector that reads the episode length reaches precision ≈ 1 and passes 6.1 trivially, which breaks the
    "no reference access" premise (A7) in substance.
  - On QA/Sheet, `format_flags` (`truncated`, `answer_tag_present`, `program_delivered`) are near-certain failure proxies
    under the decision metric (:478, 3.3). A model-written detector that restates a mechanical category passes 6.1
    and counts as "examiner evolved", although the mechanical one is excluded from that count (:528).
  - ALFWorld "generated items" are real training games picked by a program. G1 = simulator truth, G2 is met by random
    games (I-ds wins 50.9%, FP F15), and G3 is N/A. So "generator passed G1-G3" holds by construction, and the only
    bench where G4 retirement can bite (R17, :914) compares two samples of REAL games. That is effect homogeneity, not
    the validity of generated items.
  - Under the recommended pilot (ALFWorld → SB, :920-924) the examiner-side headlines are therefore guaranteed or
    tautological, and the owner text says the opposite.
- Fix: (1) Detectors receive the trajectory prefix up to a registered horizon (for example the first 20 steps, or the
  steps before the last 5 for QA multi-call cells). Episode length, terminal observation, `truncated`, the tag and
  program flags and `extracted_answer` presence are removed. (2) A model-written detector counts as evolution only if it
  shows significant lift on CHECK cells that no mechanical detector flags. (3) Report ALFWorld selection programs as
  "selection validity" and exclude them from "generated items predict real effects" and from "examiner validated".
  (4) Correct summary item 6 and 11.1 ③: ALFWorld 出题 = 挑选没用过的真实游戏局，不是生成新题.

### F3 [MAJOR] The self-test sieve (4.5) is a noise gate and can end a one-step bench for nothing
- Attacked text: :566-569 ("A set on which no procedure of `S' ∖ S` ... can fire is skipped" by hook legality; "Pass iff,
  on every set with >= 20 items, `mean(S' − S) >= −0.05`", :570); :572 (fail → one fix, a new draw, one re-run, then no
  candidate); :567-568 (the persisted `G_self` sets of earlier benches).
- Why it is wrong:
  - At 1 run on 20-40 items the threshold −0.05 is about 0.6 SE (SE = sqrt(q/n) ≈ 0.07-0.1 at discordance q 0.15-0.25:
    estimate).
  - "Can fire" means hook legality, not actual firing. A set where the candidate's predicates fire on no item sends
    byte-identical requests in both arms and still counts. On such a set, serving noise alone fails the sieve with
    probability 0.08-0.28 per set (q 0.05-0.15, n 20-40), or 0.15-0.63 over 2-3 sets (estimate, normal approximation;
    q = same-text single-run disagreement 0.049-0.161 measured in cal-1, FP F45, feasibility-prototypes.md:309-314).
  - Killing a null candidate is harmless, but this sieve kills real ones at the same rate. On SB/OQ a kill ends the bench:
    R is consumed and the slice pair no longer fits (:369-375, :590-591). The previous run of this review estimated
    P(no candidate after fix + redraw | null) at 0.12-0.50 for 2-4 sets (sim-output.txt section A).
  - Persisted `G_self` sets reused at every later step, with their numbers fed to `engineer_fix` (:458, :572), are a fixed,
    adaptively used generated validation set.
- Fix: restrict every self-test set to items where the requests of S' and S differ (as 5.4a does for A*). Skip sets with
  fewer than 20 such items. Fail only if the one-sided 95% upper bound of the fired-item mean is below −0.05, or pool
  the sets and test once. Redraw earlier benches' sets at each step instead of persisting them. Register the expected
  false-kill rate.

### F4 [MAJOR] The scope rule (4.7) is decided by noise and rests on the instrument E9 showed blind to cross-bench harm
- Attacked text: :582-584 ("Scope ... `"<b>"` if, on some earlier bench's `G_self` set where p fires on >= 10 items, the
  self-test delta of 4.5 was < −0.05 ... Scope uses generated items only"); :784 (`this bench only` iff it fires on < 20
  test items elsewhere); :656 ("τ_p ... feeds freeze evidence (4.7)").
- Why it is wrong:
  - A null procedure on a 10-item, 1-run set is restricted with probability 0.31-0.39 (estimate, q 0.1-0.3). The delta
    is the joint S' − S contrast, so other new procedures firing on the same items contaminate it.
  - A restricted procedure then fires nowhere else, so 7.4 labels it 仅本 bench. Noise becomes a reported label.
  - The instrument is the wrong one. E9's generated OfficeQA panel was saturated (empty scaffold 0.891) and missed the
    real −9.5 harm (UB +1.78) (FP F52, feasibility-prototypes.md:371-380). DR §4 requires that "通用" pass a measured
    "does not change the answer format" check (direction-recommendation-20261021.md:48) and stops generated items as
    gates (:31). The spec uses generated-item accuracy, the measure shown to fail.
  - :656 contradicts :584 and "one decision per batch": a per-procedure reading of the acceptance batch must not change
    the package.
- Fix: default scope "all" (predicate-gated). Restrict scope only by a truth-free format check on earlier benches'
  generated sets: tag rate, JSON-only rate, answer-only/terse share and reply length. That is the E9 mechanism (answer-only
  replies 23% → ~60%, FP F52) and needs no generated truth. Use a CI-based threshold. Delete "freeze evidence" from :656.
  Label hook-restricted procedures "cannot act on b (by construction)", not 仅本 bench.

### F5 [MAJOR] The note/state/advise placebos are not fair controls; D2 is weakest exactly when the placebo hurts
- Attacked text: :594-606 (note sham = "deterministic irrelevant text with the same byte length ... cut from a registered
  placebo corpus (the eight v3 placebo texts)"; state = length-matched irrelevant text; advise = entries of the literal
  `"none"`); :623 (D2); :900 (R3: "S' − P is the information effect").
- Why it is wrong:
  - The corpus is known to be non-inert and heterogeneous: −9.8 to +3.6 points in cal-1 (CM F47), and the recipe placebo
    cost the scaffold −8.1 [−14.2, −2.3] in D1 (FP F37, feasibility-prototypes.md:250-254).
  - S' − P = (S' − S) + (S − P). When the sham hurts (S − P > 0), D2 is almost implied by D1 and adds no protection.
    When the sham helps, D2 costs power. Its strength is therefore uncontrolled.
  - For `advise`, "none" entries are a no-op, so D2 ≡ D1. For a 34-step ALFWorld episode, up to 1,500 B of recipe text
    per step is a large distractor, likely harmful, and again makes D2 vacuous.
  - Genre is not matched. Prose about recipes does not control for "a structured note about this item", which is the
    salience channel through which a content-free note helps.
  - DR §4 requires at least two length-matched placebos (direction-recommendation-20261021.md:39); the spec has one.
  - The known dominant confound is not controlled. Most measured gains came from generic instructions; one learned step
    over a zero-shot instruction was +0.1 [−1.6, +1.8] (direction-recommendation-20261021.md:15). A note procedure that
    emits a near-constant generic tip is a text rule in a code wrapper and would pass D1 ∧ D2.
- Fix: (1) Report P − S with a CI every round. Register: if its upper bound < 0, the round's D2 is "uninformative"
  and the claim is "beats parent" only. (2) Add a second, genre-matched sham for note/state: p's own output for a
  DIFFERENT item of the same batch (registered derangement), or p's note with its numbers and entities permuted. Run the
  IUT against both shams (still level 0.05). (3) Mark a note procedure whose output is (nearly) constant across items as
  a "text rule". (4) Rename the contrasts honestly: note = "over an irrelevant-text control", repair = "over a retry
  control" (its sham still carries the failure bit). Keep the compute sham: same trigger, same call count, results
  withheld. It is a clean information control.

### F6 [MAJOR] Per-procedure transfer labels have no multiplicity control, and 仅本 bench needs no own-bench evidence
- Attacked text: :781-786 (`transfers to b` at one-sided 0.05 per (p, b) with |W_p| >= 20; `general` iff it transfers to
  >= 1 non-origin bench and is harmful on none; `this bench only` iff it fires on < 20 items elsewhere, "or transfers
  nowhere and is harmful nowhere").
- Why it is wrong:
  - Under a global null, a procedure tested on 2-4 non-origin benches is labelled `general` with probability 0.09-0.17.
    Among 3-6 such procedures, P(at least one false `general`) = 0.25-0.57 (estimate: independent one-sided 0.05
    tests; "harmful" at two-sided 0.05).
  - `harmful` has very low power at |W_p| ≈ 20-60 (τ_p resolves only about ±11-25 points, spec :660), so "harmful on
    none" is almost free.
  - A procedure with no effect anywhere gets 仅本 bench, which tells the owner it works on its own bench. That is untested:
    τ_p on the origin test bench is not required.
- Fix: Holm over all (p, b) cells of the table, or BH at q = 0.10 if registered as exploratory. `general` requires a
  corrected transfer on >= 1 non-origin bench AND a registered non-inferiority bound on the others. `this bench only`
  requires τ_p LB > 0 on the origin test bench. Otherwise `no measurable effect` / `unresolved` / `cannot act elsewhere
  (by construction)`.

### F7 [MAJOR] LiveMath's "stronger conclusion" artefact is closed to generators but open to procedures, and it is not split at test
- Attacked text: :687-690 (only generators are forbidden from using STRONGER_OPTION); 3.5 engineer prompt (:490-498)
  forbids "facts about particular items", not dataset-wide label regularities; 7.4 has no meta-option split.
- Why it is wrong:
  - D9 measured the meta option in 129/283 LiveMath training items, the key in all 129; "pick it whenever present" was
    estimated at 76% vs the task card's 33% (FP F44, feasibility-prototypes.md:300-307).
  - The E4 critic attributed 42-84% of LiveMath gains to it (FP F51). DR §4 lists learning it as "not learning"
    (direction-recommendation-20261021.md:35).
  - The engineer sees run-slice failures with references (:465, :552) and will find it. A one-line `note` ("prefer the
    option stating a stronger conclusion") depends only on what the solver sees, passes the prompt rule and probably the
    literal leakage check (a short regex need not collide with pool surfaces). It would be accepted on LM and show as an
    F − C gain at test.
  - DR §5 step 3 requires LiveMath results to be split by meta-option presence (about 68 test items without it,
    direction-recommendation-20261021.md:80).
- Fix: a registered static and leakage rule that rejects any procedure whose predicate or emission matches
  STRONGER_OPTION or a paraphrase (`leak_adjudicate` asked explicitly). On LM, compute D1/D2 and τ_p on A* items
  without the meta option (or stratified). Report the LM test readout split by meta-option presence.

### F8 [MAJOR] The registered disclosure (0.6) understates prior use, and a new SearchQA draw is declared not to need the owner
- Attacked text: :93-95 ("Pool items of ... LiveMath (142/283) and SearchQA (555/600) were inputs to the v1 baselines,
  older learners, v3 or the 10/20-21 feasibility studies [DP §5]"); :382 ("Special supplies (no owner release needed)").
- Why it is wrong:
  - DP §5 gives "absolute never used: 0" for both benches (data-and-pools.md:348, :350). The v1 baselines received all
    283 LiveMath items (data-and-pools.md:155-162), and all 600 SearchQA items were in the v1-baseline or 10/12 learner
    panels. D9 also scanned the labels of all 283 LiveMath items (FP F44).
  - 142 and 555 are the method-side execution counts. The text conflates them with "inputs to the v1 baselines", the
    opposite of the honest-provenance rule in AGENTS.md.
  - The new SearchQA block was an owner decision in DR (direction-recommendation-20261021.md:55 "由你签字", :101 decision
    3), and DP marks it "owner approval and registered exclusion needed" (data-and-pools.md:348). A1 says otherwise.
    The registration should not settle this silently.
- Fix: replace the counts with both columns per bench (absolute and method-side) plus the D9 label scan. List "new
  SearchQA block, ids-only sign-off" as an owner confirmation. Add to the exclusion list any SearchQA ids drawn after
  10/12 by other scripts.

### F9 [MAJOR] The MDE and power statement is not honest at the chosen sizes
- Attacked text: :371-372 (SB "≈ 12 pts", OQ "≈ 10 pts" from D1's computation); :377-379 ("certifies only effects of
  about 10-12 points or more"); :640-645 (the decision runs on A*, |A*| >= 15); :661 (5.6 the registered minimum effect
  = the 2.1 column); :629-631 (IUT ≈ 1.1-1.2 × MDE).
- Why it is wrong:
  - (a) Wrong noise source. D1's figures use same-text paired SDs (0.326/0.222/0.144 at 1/2/4 runs) measured on SearchQA
    with deepseek-v4-flash, mostly on the scaffold (FP F40, feasibility-prototypes.md:272-276). DP's bench-specific
    scaling gives OQ 37/37 = 14.2-16.6 and SB 46/45 = 17.2-19.0 (two-sided, 1 run; data-and-pools.md:349, :351). The
    column mixes one-sided D1 numbers (SB/OQ/LM) with two-sided DP numbers (SQ/ALF) and never names the convention. The
    new model's noise is unmeasured.
  - (b) Wrong estimand. The test runs on A*, the items where N fires, while 5.6 registers whole-batch MDEs that assume
    A* = A. At |A*| = 15 × 2 runs the per-fired-item MDE is about 19 points (estimate: 2.487 × 0.30 / sqrt(15)).
  - (c) Power at realistic effects is not stated. For a true whole-batch +5, IUT acceptance is ≈ 0.13 (SB), 0.18 (OQ),
    0.21 (ALF); D1 alone 0.27 / 0.33 / 0.37 (estimate: normal approximation, SE = MDE/2.487, corr(S' − S, S' − P) = 0.5,
    placebo inert). For the default pilot, P(nothing accepted | +5 on both) ≈ 0.71 and ≈ 0.17 at +10. DR already warned
    that OQ as a source gives a true +5 rule ≈ 0.19 (direction-recommendation-20261021.md:91).
  - (d) OQ serving regimes are ignored. The same text swings 20+ points across windows (60 items, 4 windows, SD 11.4;
    direction-recommendation-20261021.md:17), and DR §5 step 3 requires OQ to be read in two windows, stratified by
    response regime (:80). The spec does neither, for the default pilot's second bench.
- Fix: register per bench the convention, the σ source and the power at +3/+5/+10 in both whole-batch and A* units.
  Add an in-round same-text duplicate arm on each bench's first acceptance round (≈ 0.24M SB, ≈ 0.8M OQ: estimate) to
  measure σ in-window and flag instability. On SB step 1, S = C already plays this role (:607-608); give it a
  registered stop rule. Pre-register OQ regime strata (by arm C's terse share per 15-min bin) and a stratified estimator
  for the decision. The owner summary must say that the default pilot most likely accepts nothing.

### F10 [MAJOR] The code-vs-text comparator (F_text) is a strawman and its reading is one-sided
- Attacked text: :749-751 ("F_text (C plus the accepted procedures' descriptions rendered as text guidance, no code");
  :776-778 ("if F_text >= F off the own benches, the code form did not transfer better").
- Why it is wrong: descriptions are engineer-written descriptions of a program (:145), not guidance written for the
  solver. Gating is unspecified. If every description is shown on every item, F_text recreates v3's whole-Skill
  rendering, which E4/E9 measured at −9.5 to −33 on OQ (FP F51-F52). That biases the comparison towards code, so the
  Break It Down risk (consequence iii) cannot show up.
- Fix: at freeze, a fixed pinned prompt (GLM, temperature 0) rewrites each accepted procedure once into a solver-facing
  instruction. It is shown only where p's predicate fires, in the same notes slot, inside a registered length band.
  Register both readings: F − F_text LB > 0 means "code adds over its own text"; otherwise "no evidence that code
  transfers better".

### F11 [minor] Budget reasoning contradicts its own source; one estimate breaks its stated assumption
- Attacked text: :831-833 ("the ledger is a lower bound ... (27.5M ledger, ≈ 17.6M billed, ≈ 14M actual)"); :823 (OQ S'
  6,500 "half the cells make a compute second call"); :825 (SB "a quarter make a repair call"); :39 ("按 2 倍预留").
- Why: the cited numbers show the ledger OVER-counted about 2× (direction-recommendation-20261021.md:47), so a cap of
  ≈ 2× in ledger units has ≈ no margin in actual usage. Call 2 re-sends the whole public view (:269-270), so S' ≈ 5,300
  × 1.5 ≈ 8,000 per OQ cell, not 6,500 (estimate). The SB "quarter" has no anchor. 100M / 28M is 3.6×, not 2×. A
  BudgetStop inside the single OQ/SB acceptance round splits a one-shot round across serving windows.
- Fix: correct the wording and the OQ estimate. Add a pre-round completability check: start an acceptance round only if
  the remaining scope cap covers its full reservation.

### F12 [minor] D1's percentile bootstrap is slightly anti-conservative near the |A*| = 15 floor
- My simulation (estimate: null, per-item pass ~ Beta(0.5, ICC), 1,500 replicates, MC SE ≈ 0.006) gave false-accept
  rates of 0.054-0.059 at n = 15-23, ICC 0.6, against 0.007-0.024 for the exact sign-flip test. Fix: use the exact
  paired sign-flip (randomization) lower bound when |A*| < 50.

### F13 [minor] Detector statistics ignore clustering and multiplicity
- :674-677: the binomial treats both runs of an item as independent (ICC 0.6-0.86 measured, FP F45), and up to 6
  detectors are tried per step without correction. The previous run of this review estimated 0.02-0.03 per null
  detector, ≈ 0.10-0.17 for >= 1 of 6 (sim-output.txt section E). Fix: an item-level test (cluster by item), Holm over
  the step's detectors, and the run-0 reading made binding.

### F14 [minor] ALFWorld acceptance and test come from different distributions
- Acceptance uses `train` games, while the test is (inferred) `valid_unseen`, i.e. unseen scenes (data-and-pools.md:204-226).
  GRASP's in-domain-only finding applies. Pre-state that an ALFWorld own-bench test gain is an out-of-distribution claim.

### F15 [minor] Smoke items and the exact-fit supplies
- :883 and S4 take items from the step-1 run slice "registered as slice `smoke`". SB (91 = 46 + 45) and OQ (74 = 37 + 37)
  fit exactly, so any smoke entry in the run root's registry makes the slice pair fail to fit (:590-591). Fix: state that
  smoke registrations live in the smoke root only and that R may reuse those items (R is not decision material).

### F16 [minor] v2 can give a hedged untagged reply two chances
- 3.3: with no tag, official scores the last non-empty line (SearchQA) while v2 also accepts a JSON `"answer"`. A reply
  holding two different candidates therefore passes if either is right. Fix: if both channels are present and disagree,
  score the official channel only, and log a flag.

### F17 [minor] Two internal inconsistencies in the decision machinery
- :723-724: the secondary per-procedure G4 needs twin arms on `G_acc`, which 4.6 does not schedule (:576-579).
- :637-640: A* = "some procedure of N ∪ retired(S') fires" misses items where only the OLD version of a revised
  procedure fires. Define A* as the items whose S' and S request hashes differ (already computed, :638).

### F18 [minor] ALFWorld withholding is costly for what it resolves
- About 11.5M per step for about ±14-point per-procedure resolution (:658-660, :841; estimate). A registered factorial
  withholding (one twin per game, each procedure of N withheld independently with p = 1/2, main effects by regression)
  uses 134 episodes instead of 201 and puts every game into every τ_p estimate.

## Best ideas worth keeping in the synthesis
1. A* via the sealed firing plan and request-hash identity (:637-645): it removes items that carry only noise
   (whole-batch MDE × sqrt(|A*|/|A|)), selects on public views only, and returns undispatched items to the supply.
2. One seeded order per bench cut into consecutive slices, the write-once registry written before dispatch, unconsumed
   acceptance slices kept at the front, and "a pause never re-decides a batch" (:361-367, :403-410).
3. D1 ∧ D2 as an intersection-union test with an honest power penalty, and the L/H convention for unknowns (:615-631).
4. The compute and repair shams: same trigger, same call count, information withheld (:600-603). A clean control.
5. "Identical by construction ⇒ not run, reported as such" (:753-757), and S = C at step 1 as a same-round duplicate (:607-608).
6. The structural-limit statement for G4 on one-step benches (:725-728, R17 :914), and the post-treatment warning on
   ALFWorld `shadow_fired` (:653-655).
7. Contradiction paragraphs C1-C11 (:99-133), especially C1's re-reading of the probe log and C11's D3 caveats.
8. Every procedure fault fails open to parent behaviour, with a 2% candidate cap and new outcome rows (:343-358, :625).
9. A pre-stated expectation of near-zero transfer, and labels never assigned from enable rates (:786-789).

## 给负责人的白话摘要

我是反方审查员，这次只看"证据与统计"一个角度。审的是设计员 A 写的登记稿（spec-fidelity）。结论：需要修改，
有 1 处致命问题、9 处重要问题、8 处小问题。下面括号里的代号第一次出现时都解释一下。

1. **致命：考官"预测效度"这条检验测不出东西。**
   - 它是登记稿宣称的第一条新意。"预测效度"指：验收时，新旧两版包的分差在考官生成的题上和在真实新题上方向一致，
     就算出题程序"有效"。
   - 按现在的写法，真实分差只要到 5 分就拿来比方向。但这个大小只相当于一次测量的误差，方向本身就近似抛硬币。
   - 生成题又是从工程师看过的训练题改出来的。像 E1 那样"生成题上 +13、真题上 0"的出题程序，反而最容易被判"有效"
     （我估算：真实效果 +5 分时，它被判有效的概率约 0.9；真正有效的出题程序只有约 0.66）。
   - 修法：① 验收时让生成题在所有对照组（包括安慰剂）下都跑一遍，一轮就能得到多组比较，其中有本应为零的对照；
     ② 生成题改用工程师没见过的题作来源；③ 用带误差范围的统计代替"比方向"；比较次数不够时只写"无法评估"，
     不写"有效"。
2. **ALFWorld（文字家务游戏）上，考官的几道关不用本事也能过。**
   - 失败的局全是走满 50 步超时，所以检测器只要数一下步数，就能百分之百认出失败。
   - ALFWorld 的"出题"其实是挑选没用过的真实游戏局，不是生成新题，所以"真值、难度、捷径"三道关自动通过。
   - 因此您摘要第 6 条和第 11 节决定 1 里"考官两半都能进化"的说法要改。
3. **自测这道筛子基本在筛噪声。**"自测"指在生成题上比新旧包，只当筛子。它把"新包比旧包低 5 分"当作不合格，但在
   20–40 道题、各跑一次的条件下，这只相当于半个误差。连新包根本没起作用、请求一字不差的题集也算进去。表格和
   OfficeQA 每个只够走一步，被误筛掉就白走了。
4. **"通用 / 仅本 bench"的标签，实际由噪声决定。**
   - 一条过程能否带到别的 bench，是按生成题上 10 道题跑一次的结果定的。
   - 而 E9 已经证明生成题看不出跨 bench 的真实伤害。
   - 最后的标签也没有做多重比较校正（我估算：3–6 条其实无效的过程里，至少一条被误标"通用"的概率是 25%–57%）。
   - 另外，"仅本 bench"这个标签发出去时，并没有证据表明它在本 bench 有效。
5. **安慰剂对照只对"精确计算""修复回合"两类公平。**
   - "安慰剂"指占同样位置、触发同样多调用、但不给有用信息的假过程。
   - 对"笔记"类过程，它用无关文字（菜谱之类）冒充。这些文字本身会掉分（以前测到 −8 分），导致"比安慰剂好"这条
     几乎白送。
   - 建议加第二种同格式的假笔记（例如把另一道题的笔记换过来），并且每轮都报告安慰剂本身的作用。
6. **其余重要问题：**
   - LiveMath 选择题里"更强结论"选项永远是答案。登记稿只禁止出题程序利用它，没禁止工程师写过程去利用它。
   - 关于以前哪些题被用过的说明写少了：LiveMath 实际 283 道全被 v1 基线用过，SearchQA 600 道也全用过。
   - 最小可分辨效果借用了 SearchQA 的噪声。没写实际把握有多大：真实效果 +5 分时，表格和 OfficeQA 各只有约
     13%–18% 的机会被收下，默认试点大概率一条也收不下。
   - OfficeQA 没有按以前的建议在两个服务时段读、并按回答状态分开算。
   - "文字形式说明"这一对照组设计偏向代码一方。
7. **值得保留的好设计**：
   - 只在新过程真正起作用的题上比较（省掉纯噪声的题）；
   - 一个固定顺序切片，每批只用一次并先登记；
   - 新包必须同时赢旧包和安慰剂；
   - "请求一字不差就不重复测、照实写明"；
   - 精确计算和修复回合的安慰剂设计；
   - 预先写明"跨 bench 迁移大概率接近零"。

Status: COMPLETE (written 2026-10-21).
