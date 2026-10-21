# Critique of `proposals/paper.md` (lens 论文优先): feasibility / cost / protocol

Critic: paper-feasibility (adversarial feasibility, cost and protocol review). Read-only: no model calls, no SSH, no
test pools. Aliases: RL = docs/results-and-lessons.md; PS = docs/project-status.md; H = docs/handoff/;
F = docs/handoff/feasibility-20261021/; P = the proposal (line numbers of paper.md). "My arithmetic" marks numbers I
computed from the cited inputs; every other number carries its source. Every citation below was re-checked against
the file.

## 0. Verdict: needs_revision

The core is the right missing experiment and can run in about two overnight sessions:
- X0: register a JSON-aware scorer.
- X1: task card + v3 rules vs task card, with placebos and a duplicate, on the SearchQA training items v3 did not use.

Several parts do not hold as written:
- one cited fact is mislabelled (D1's "card" is the SearchQA section alone);
- one step cannot be done at its stated cost (H2a);
- the X1 validity rule anchors on the contrast most sensitive to the serving regime;
- the X1 cap margin is thin given how the ledger behaves;
- X2 is under-costed (its "GLM rate unmeasured" premise is wrong) and lacks the controls the proposal itself requires;
- one X0 item reads v3 test cells unless it is restricted to training cells;
- X3's transfer rule cannot be reached with 74 OfficeQA items, a SearchQA-section rule is inert on OfficeQA by
  construction, and X3's cost omits the controls and items D1's own design requires.

Neither owner objective gets an experiment that could come out positive. The synthesis must put that to the owner as
an explicit choice.

## 1. Item counts and power

### X1 (P L109-129)

**Item count.** Correct.
- 369 = 600 − 231. D1's fresh set is "the 600-item pool minus the 231 items any v3 non-test unit used"
  (F/D1/report.md L449-450).
- Breakdown: 200 focal / 31 regression / 130 D1 / 180 E5 / 59 never used (F/E5/critic-result.json `.missing` #7).
- 9 × 369 × 2 = 6,642 cells.

**"Fresh" (P L109 heading; L117) is wrong for 310 of the 369 items.**
- D1 measured the scaffold, recipe placebo on scaffold, seed-only, its duplicate, seed-only + hex placebo and
  seed-only + recipe placebo on 130 of them (F/D1/report.md L448-449). The hex and recipe placebos are cal-1
  control:2/control:3.
- E5-P1 measured scaffold, ids-full, control:3 and cand on 180 (F/E5/result.json `.pilot`).
- This does not bias a measurement of frozen v3 texts. But:
  - (a) A3-A5's placebo indices must come from a rule that ignores outcomes (all four registered placebos, or fixed
    indices), never from D1's control:2/control:3 results on those 130 items;
  - (b) earlier-session cells must not be pooled with X1 (F/D11/result.json `.recommendation` 3).

**Mislabel in fact ⟨7⟩ (used at P L31, L67, L121).**
- D1's "task card" S is "scaffold + SearchQA task card = cal-1 seed-only" (F/D1/report.md L449), 2,442 bytes
  (H/cal1-registration-20261020.md L98).
- It is not the five-section ids-full card, 12,681 bytes (same file, L97), which is X1's A1 and the I-ds parent.
- So "placebos on the card 0.000/−0.023", "duplicate +0.004", "SD2 0.159" and "card − scaffold +16.2" are all
  seed-only numbers (F/D1/report.md L164-177).
- **Placebos on the five-section card have never been measured.** This is not fatal for noise: the cal-1 single-run
  flip rate is ids-full 0.049 vs seed-only 0.052 (F/D11/result.json `.evidence` A).

**Power (P L121).**
- 2.3 points uses the same-text SD (0.159). No text change gets that low: "Every text change, placebos included, has
  tau 0.12-0.28" (F/D1/result.json `.evidence`).
- 3.4 points uses 0.2255, which is the 4-run SD₄ (F/D9/critic-result.json `.confirmed_claims`; F/D1/report.md L157).
  X1 uses 2 runs.
- Measured 2-run SDs for two different texts:
  - 0.254 for seed-only − ids-full (F/D1/report.md L157);
  - 0.197 and 0.223 for the two placebos on seed-only (F/D1/report.md L170-171);
  - 0.243 for a rule-shaped text alone vs the card (F/E7/critic-result.json `.refuted_claims` #4).
- The SD of card + rule vs card has never been measured. No cal-1 arm is "card + rule" (F/D9/critic-result.json
  `.refuted_claims` #1; F/D8/critic-result.json `.missing`; F/E5/critic-result.json `.missing` #2;
  F/E7/critic-result.json `.missing`).
- Plausible 2-run range 0.19-0.25. The low end is placebo-like heterogeneity (tau 0.06-0.14 on the quieter card
  parent, F/D1/report.md L177); the high end is rule-shaped heterogeneity (tau 0.184-0.188, L154-155).
- My arithmetic: MDE80 ≈2.8-3.7 points two-sided at n = 369. With Holm over three one-sided tests plus the "beat the
  best placebo" condition it is ≈3.5-4.5.
- Same order as E4's critic: SD 0.25 and a 3-point effect need ≈540 items (F/E4/critic-result.json `.missing` #6).

**Can H1's outcomes be reached?** (my arithmetic; SE = SD/√369 = 0.99-1.30 points)
- P("bounded", UB95 < +3 | true 0) ≈ 64-86% two-sided, 75-92% one-sided.
- P("adds" | true +3) ≈ 57-82% before the placebo condition.
- P states none of: these a-priori probabilities; whether UB95 is one- or two-sided; which tests form the Holm family
  (P L123-127).

**H2 (difference-in-differences).**
- My arithmetic: SE ≈2.0 points, assuming SD ≈0.30 for scaffold contrasts and no credit for covariance, so the
  MDE80 is ≈5-5.6 points.
- Reachable for E-ds s1-r2 if the rule is ≈0 on the card. It measured +5.5 [+2.0, +9.1]
  (F/D9/critic-result.json `.confirmed_claims`), and +8.1 on a 99-item half (F/D1/result.json `.evidence`).

**H2a cannot be done as written (P L127: "rerun cal-1's subset analysis at n = 6/11/20 (0 tokens)").**
- cal-1's A1 needs the judged arm, parent:A and the four controls on the same items at TRIGGER_RUNS = 4
  (H/cal1-registration-20261020.md L25, L51-58).
- E-ds s1-r2 was never a cal-1 arm. X1 measures it on other items, at 2 runs, with no placebos on the scaffold.
- Doing it properly means a same-session parent:A + 4 controls + s1-r2 on cal-1's 200 items × 4 runs: 4,800 cells.
  - Real: ≈6M at 1.24-1.29k per scaffold-family cell (F/E5/result.json `.cost_estimate`).
  - Ledger: ≈13M at cal-1's scaffold charged mean of 2,780 per cell (F/E9/critic-result.json R6).
- The only other option is a redefined gate, which is not registered.

**Validity rule "A1 − A8 ≥ +5 (official scorer)" (P L124).** It anchors on the most regime-sensitive contrast, under
the scorer that causes the sensitivity.
- In a terse window the scaffold scored +6.1 [+2.1, +10.2] on the same 200 items while the card moved +0.1
  (F/D11/result.json `.evidence` C).
- Across days the scaffold moved −5.9 [−9.9, −1.9] and the five-card Skill −0.5 (F/E4/critic-result.json R7).
  Five cards − scaffold was +3.3 on 10/19 and +9.0 on 10/20 (F/D1/result.json `.evidence`, Drift).
- The effect sits on untagged/JSON replies (F/D5/critic-result.json `.refuted_claims` #5).
- SearchQA terse shares reached 60-96% in night windows (F/D11/result.json `.evidence` C).
- Three other terse scaffold sessions showed no gain (−3.45 / 0 / −1.72 on 29 items; D5 critic, same item), so the
  risk is material, not certain. But a void throws away the whole ≈23-33M run with no rerun (P L124, L209).

**Regime scope.**
- X1 is a single interleaved session (P L113).
- A text × regime interaction has been measured: −6.00 [−10.45, −1.55] (F/D11/result.json `.evidence` C).
- D11's own rule: "a paper claim needs either measurement in two windows or an explicit regime qualifier"
  (F/D11/result.json `.risks`).

**P's own control rule is not met.** P L75 requires ≥3 placebos and a duplicate for every comparison. A9 − A8
(P L115) has neither, so H2 and H2a fail it.

**Spacing (P L74).**
- Repeated runs are byte-identical requests (F/D11/result.json `.evidence` C). So each item has 13 identical pairs:
  6 among A1/A2's four requests and 1 in each other arm.
- In a uniformly shuffled 2-hour dispatch, ≈3% of those pairs (≈160) would fall within 2 minutes by chance
  (my arithmetic). The rule therefore needs a scheduler, not just a shuffle.
- Spacing is harmless but does not lower the 8-10% flip floor (F/E4/critic-result.json R2).

**Scope of the bound.** It covers only the three SearchQA rules I-ds screened at step 1, s1-r1/r2/r4
(F/E7/critic-result.json `.refuted_claims` #1). It is not "what v3 learned" (P L111).

### X2 (P L131-156)

**Counts.** 129 meta + 154 non-meta = 283 (F/D7/critic-result.json `.confirmed_claims`); 437 × 3 × 2 = 2,622 cells.
Correct.

**Power.**
- For a rise from 3% to 13% on 154 × 2 at α = 0.01, power is ≥0.95 (my arithmetic, SE ≈1.4 points). The stated
  "≈80%" is conservative.
- But the effect size is borrowed. 4/16 vs 0/19 (⟨24⟩) is the D10 critic's partial probe of the released SkillOpt
  GPT-5.5 Skill, with and without its two meta bullets, on deepseek-v4-flash (F/D10/report.md L423-425, L484-486;
  F/D10/critic-result.json `.missing` #1). It is not v1 SkillOpt-glm on GLM-5.3.
- All 4 false picks sat right after the correct option (4/7 vs 0/9 elsewhere, same source). Counterbalancing the
  position will dilute that.

**Construct.**
- B2 is the v1 SkillOpt-glm final Skill, 15,174 bytes, updated at steps 1 and 3 (H/coevo5-v1-results-20261019.md
  L257).
- Its item 6 says the meta option "is very frequently the intended key". It also says "the meta-option is a trap" when
  a concrete option reproduces the theorem, and "do not pick the meta-option reflexively either" (L322). So X2 is
  informative, not tautological.
- B3 must be fixed in advance: meta content sits in the intro (L300) and in item 6 (L322).

**Insertion mechanics are unspecified (P L143).**
- B2 states "4–5 lettered options (A–E)" (L300) and "respond with ONLY the single option letter" (L330). The scorer
  needs exactly one letter in the last answer tag (RL L219).
- Adding the false meta as a new option makes 5-option items 6-option, outside B2's own A–E. Whether the strict scorer
  accepts "F" is unverified.
- Replacing a distractor keeps five options but changes difficulty. It must never replace the weaker-but-true option
  the benchmark always includes (F/D7/critic-result.json `.refuted_claims` #4).
- The insertion rule must be fixed before launch.

**Controls.** There is no B2 duplicate and no length-matched deletion control, contrary to P L75. So B2 − B3 confounds
"meta content removed" with "≈1-1.5 KB of procedure removed".

**Service risks.**
- BigModel's content filter refused 2% of SearchQA items in E7 (F/E7/result.json `.risks` 8).
- D9's small GLM pilot logged 146 HTTP 429 retries (F/D9/critic-result.json `.confirmed_claims`).
- GLM concurrency is capped at 10 (PS L123).
- Refused or unknown cells must be pre-registered as missing, not as fails.

### X3 (P L158-179)

**The transfer rule cannot be reached.**
- OfficeQA: 74 × 2, per-item SD 0.385-0.486 (F/E4/critic-result.json R6; F/E9/critic-result.json R2a). That gives
  SE ≈4.5-5.6 points, so LB > 0 needs an observed ≈9-11 points; the MDE80 is ≈12-16 (my arithmetic).
- P L175's "OfficeQA 10.3" is D1's figure for a 37 × 4 acceptance batch at an assumed tau 0.2 (F/D1/result.json
  `.evidence`). It is not X3's 74 × 2 transfer read.
- A ≥2-point SearchQA package is unlikely to move OfficeQA by ≥9 over the card. The SearchQA instruction itself moved
  OfficeQA by −4 to −7 (n.s.) (H/feasibility-exploration-20261021-cn.md L116).

**Placement.** A rule under the SearchQA "Applies when" header is inert on OfficeQA by design (F/E7/critic-result.json
`.missing`; F/E4/critic-result.json `.missing` #4). X3 does not say where accepted text goes.

**Regime.** The same Skill hash on the same 74 OfficeQA items differed by +20.3 points across windows
(F/E9/critic-result.json R4).

**Data.**
- D1's design (F/D1/result.json `.design` steps 1, 4, 5, 7):
  - each step takes a 100-item proposal batch, flagged permanently;
  - each round uses an acceptance batch of 300 items × 2 runs, reusable for at most 3 steps;
  - the chain's first round adds a parent duplicate and a length-matched placebo arm.
- So three steps need ≈600 new items.
- The pool cannot host this. The unflagged items left (369 + 31) are X1's items, and accepting on items where X1
  already decided "adds" would use the same items twice.
- A new block needs owner approval and an exclusion of v6 test items and blocks C/D (PS L118). That exclusion reads
  test identifiers outside evaluation, which needs re-registration (F/D6/critic-result.json `.refuted_claims` #8).

**Code.**
- D1's fresh-batch acceptance is explicitly out of v4's scope (H/v4-plans-20261021/spec.md L177-178).
- v4 itself is not implemented: ≈3 agent-hours plus Codex (H/overnight-report-20261021.md L39).
- The alternative is to knowingly reuse v3's proposer: 21 of 49 v3 proposals were eliminated before formal testing,
  mostly over minor format or process defects (same report, L62).

**If nothing is accepted,** skip the transfer evaluation (≈10.2M).

### X0 (P L89-107)

**"Run D11 stage_table with its co-scheduling column" (P L96).**
- stage_table is built for v3's NoSkill-ds/I-ds/E-ds evaluation cells (F/D11/result.json `.recommendation` 2).
- D11 "could not check whether the v3 test cells … were co-scheduled, because the hard rules forbid me to read them"
  (`.risks`).
- Opening v3's test scores awaits the owner (PS L347).
- Restricted to training cells, the item only reproduces D11.

**Re-scoring cal-1 and v3 E-ds s1 is after the fact.** E7's critic already computed:
- cand +0.0675 and control:3 −0.0025 (`.confirmed_claims`);
- E-ds s1-r1 screen +0.75 → +13.75 items of 200, confirm −2.50 → +12.25 (`.refuted_claims` #1).

So this is a registered re-reading, not a pre-registered test. v3's registered "0 accepted" stays as it is (AGENTS.md:
no retrospective relabel).

**"If v2 flips an I-ds verdict" (P L104) is nearly empty.** The I-ds s1 parent and its three screened rules had tag
share 1.000 and 0 JSON replies (same source, `.refuted_claims` #1).

**Logistics.**
- cal-1 attempt-2 data are not yet on the new machine (H/overnight-report-20261021.md L26).
- Scorer v2 needs one Codex round plus offline tests (PS L123).
- X1's arm list must be frozen after X0 and before dispatch.

## 2. Cost recomputed from measured actuals

**Anchors.**
- cal-1's ledger settled at 27,481,897 for 8,800 cells (H/cal1-registration-20261020.md L130).
- Main-round real usage was 14.00M against a 26.53M ledger. The frozen budget charges a send's full ≈150k reservation
  when no usage comes back (F/D8/report.md L86, L674-676). E7's critic gives receipts 14.0M, charged 17.6M, ledger
  27.5M (F/E7/critic-result.json `.refuted_claims` #8).
- P L83's "3.12k per cell" is therefore a ledger average. Real usage was ≈1.6k per cell (my arithmetic).
- D1's pilot ledger equalled its receipts: no 503 reservations, 1,531 per cell (F/D1/report.md L451).
- E5-P1's cost equalled its pre-launch median, and part of it ran on the old machine (F/E5/result.json `.pilot`).
  E5 warns: "A capped pipeline needs a margin of up to about 2x over delivered tokens" (`.cost_estimate`).
- Real tokens per SearchQA cell (E5-P1): scaffold 1,236, ids-full 3,995, control:3 1,254, cand 1,287
  (F/E5/result.json `.cost_estimate`).
- cal-1 charged means: scaffold 2,780, ids-full 4,669. Medians: 1,264 / 3,846 (F/E9/critic-result.json R6).
- GLM-5.3 on LiveMath (RL L217, L219):
  - headroom pilot: 806 calls for 2.27M, 2.8k per call (arms: none, zero-shot instruction, the human Skill,
    SkillOpt's released Skill);
  - one-step stages with 5.0-9.3 KB Skills: ≈151 calls for 0.42-0.60M each, 2.8-4.0k per call;
  - gated stages: 1,483 calls for 6.05M and 1,756 calls for 8.93M, 4.1k and 5.1k per call;
  - single replies at the 65,536-token cap delayed one queue by ≈3.5 h.

| item | proposal | real (recomputed) | ledger (recomputed) | note |
|---|---|---|---|---|
| X1 | 25.8M, cap 35M | 7×738×4.1k + 2×738×1.27k ≈ 23.1M | 23.1M with no undelivered sends (as in D1/E5); 28.2M at cal-1's charged means per arm; 32.5M at cal-1's +1.42k per cell; ≈44M at cal-1's 1.9× | P prices the scaffold arms at cal-1's ledger average (3.1k); their real cost is ≈1.27k. The 35M cap leaves 2-7M in a cal-1-like session, though P L214 itself warns of ~2×. cal-1 paused on its cap |
| X2 | ≈10.4M GLM ("rate unmeasured"), cap 2× | 2,622 × 4.5-6.5k ≈ 11.8-17.0M, plus replies that hit the token cap | GLM overhead unknown (sends without usage: 54 of 13,500 and 205 of 19,500 calls, RL L220, L222) | B arms carry 12.7-15.2 KB texts (cal-1 registration L97; v1 results L257). Fits 20M without the missing controls; with them (+1,748 cells, +5-11M) it does not |
| X3 | ≈26M, cap 40M | 14.2 acceptance + 4.7 first-round duplicate/placebo (D1 design step 5; 2.36M per arm, `.cost_estimate`) + ≈2.5 proposal-batch rollouts + ≈1-1.5 selftests + ≤2 GLM + 10.2 transfer ≈ 30-35M | ≈41-46M at +1.42k per cell; ≈57-67M at 1.9× | plus implementation; −10.2M if nothing is accepted |
| without X3 | ≈36M | ≈35-40M | ≈40-50M cal-1-like; up to ≈75M if both routes run at 1.9× | |
| with X3 | ≈62M | ≈65-75M | ≈80-95M cal-1-like; ≈140M at 1.9× everywhere, i.e. about v3's 139M ledger (RL L142) | |

**Reading.**
- X1's point estimate is fine; its cap is thin.
- X2 is likely 15-65% above P's estimate, and its premise "GLM's rate is unmeasured" is wrong.
- X3 is ≈15-35% above P's estimate in real tokens and 1.6-2.5× on the ledger.

## 3. Protocol

**Test pools.**
- X1 and X2 use registered training pools only. SearchQA's 600 are train + val; LiveMath's 283 are dev + val
  (F/D9/critic-result.json `.confirmed_claims`, "Data access is legitimate").
- The X0 stage_table item is the only one that can touch v3 test cells (§1).
- X3's new SearchQA block needs a registered exclusion step against v6 test items and blocks C/D that never reads
  their content.

**No validation set smuggled in.**
- X3 reads OfficeQA/LiveMath training items only after freezing, and "target items never select anything" (P L171).
  Correct.
- Stopping E9's veto (P L57) agrees with E9 critic R1. Correct.
- X1's outcome only decides whether X3 runs; it selects no rule. Correct, provided X3 never accepts on X1's items
  (§1).

**Frozen protocols.**
- Scorer v2, X1, X2 and X3 each need a new version string and output directory. P says so only for scorer v2 (P L94).
- v3's registered result stays "0 accepted". Every scorer-v2 reading is labelled as done after the fact.

**Code rule.**
- Every code change needs a Codex review plus offline tests before launch (PS L123), and a started paid run is never
  resumed automatically (PS L126).
- P budgets a Codex round only for X3 (P L173). The X0 scorer, the X1 dispatcher and the X2 variant builder each need
  one.

**The owner's two objectives.**
- Objective 1 gets no experiment (P L187-190).
- Objective 2 gets only X3, whose transfer rule cannot be reached.
- D10's critic already said a measurement-paper framing serves neither objective and adoption is the owner's call
  (F/D10/critic-result.json R13). P says this only in a risk line (P L213).
- The synthesis must put it to the owner as an explicit choice, with the cheapest objective-1 test priced: a
  controlled E1-X costs ≈6-8M (F/E1/critic-result.json R13), and it must compare card + candidate rule against the
  card, not the card against the empty scaffold (R5).

## 4. Duplication

**X1 is not a duplicate.**
- It fills the "task card + learned rule vs task card" gap that four critics named
  (F/E7/critic-result.json `.missing`; F/D8/critic-result.json `.missing`; F/D9/critic-result.json
  `.refuted_claims` #1; F/E5/critic-result.json `.missing` #2).
- It is D1's suggested 2.1M pilot, scaled up (F/D1/result.json `.cost_estimate`).
- A1 − A8 re-measures what cal-1 (+9.4) and E5-P1 (+8.9) already measured. That is acceptable only as an in-session
  anchor.

**H2's redundancy reading is largely established on GLM.** On block A, one learning step adds +4.9 over a weak
instruction and +0.1 over bzero (RL L222). A8/A9 cost ≈1.9M real; keep them only if the deepseek replication is
wanted.

**X2 extends earlier probes.**
- It builds on D7, D10 and the D10 critic's 56-cell probe (≈80k tokens).
- Finishing that probe on deepseek with balanced positions and 2 runs costs ≈0.3M (F/D10/critic-result.json
  `.missing` #1). That is a cheap first look, but only X2's GLM pairing matches the solver the Skill was learned for.

**X0's JSON re-scoring repeats what the D5/E7 critics did after the fact.** Registering it is still worth doing.

## 5. Time (1-3 overnight sessions; agents under 45 minutes; 5-hour limits)

- **X0 ≈1 session:** scorer v2 with tests and a Codex round; re-scoring adapters for ≈8 sources (my estimate: the
  pilots wrote their own cell formats); audits over SSH; several short agents writing intermediate files.
- **X1 and X2 in parallel ≈1 session** (different providers):
  - X1 ≈2 h at 12 deepseek slots. cal-1 did 7,205 cells between 16:07 and 18:13 (H/cal1-registration-20261020.md
    L112-113). At 6 workers it is ≈7.5 h (F/D1/result.json `.risks` 10).
  - X2 ≈5 h at the 10/13 GLM rate of 806 calls in 91 minutes (RL L219), plus possible multi-hour tails (RL L217).
  - Conditions: build them from cal1.py, d1v2_pilot.py and the D10 critic's scripts; run them as Linux background jobs;
    approve their caps in advance.
- **X3 ≥2 more sessions,** plus the code beyond v4, the new data registration and owner approvals.

So the path without X3 fits 2 sessions, or 3 if a review round needs fixes. P's week-level schedule is consistent with
this.

## 6. Decision rules

**X1.** It says "fixed now", but leaves out:
- the Holm family;
- whether UB95 is one- or two-sided;
- an outcome-blind placebo-index rule;
- a regime qualifier;
- whether the pivot's "placebo band exceeds ±3 pts" (P L129) refers to point estimates or CI ends. With CI ends it
  fires almost surely: the half-width is ≈2.0-2.3 points per placebo.

In addition: H2a cannot be delivered; the validity anchor depends on the regime; a-priori P(bounded | 0) ≈ 2/3-9/10
and P(adds | +3) ≈ 1/2-4/5.

**X2.** Its rules can be reached:
- a prior shift has power ≥0.95 for a 10-point rise;
- "discriminating" needs UB95 < +5, reachable with SE ≈1.4.

The insertion rule and the controls must be fixed first.

**X3.**
- Acceptance (LB95 > 0 and ≥2 points at 300 × 2) certifies about 4.2 points (F/D1/result.json `.evidence`).
- OfficeQA transfer LB > 0 cannot be reached.
- LiveMath gives only a no-drop bound.

## 7. Refuted or corrected claims

| claim in P | why it fails | source |
|---|---|---|
| ⟨7⟩ / L31, L67: placebos "on the card" 0.000/−0.023, duplicate +0.004, SD 0.159, +16.2 | D1's "card" is seed-only (2,442 bytes), not the five-section card (12,681 bytes) | F/D1/report.md L448-449, L164-177; H/cal1-registration-20261020.md L97-98 |
| L121: MDE 2.3 at the same-text SD; 3.4 at SD 0.2255 | no text change has the same-text SD; 0.2255 is a 4-run SD; at 2 runs the MDE is ≈2.8-3.7 two-sided, ≈3.5-4.5 with Holm + placebo | F/D1/report.md L157, L170-171; F/D9/critic-result.json `.confirmed_claims`; F/D1/result.json `.evidence` |
| L127: H2a re-runs cal-1's subset analysis for 0 tokens | cal-1's A1 needs candidate, parent:A and 4 controls on the same items at 4 runs; X1 provides none; ≈6M real / ≈13M ledger | H/cal1-registration-20261020.md L25, L51-58; F/E5/result.json `.cost_estimate`; F/E9/critic-result.json R6 |
| L124, L209: A1 − A8 ≥ +5 (official scorer) as the validity check | the scaffold gains ≈6 points in terse windows while the card stays put; card − scaffold was +3.3 on 10/19 | F/D11/result.json `.evidence` C; F/D1/result.json `.evidence` Drift; F/E4/critic-result.json R7 |
| L119: X1 ≈25.8M within a 35M cap | real ≈23M, but the ledger charges ≈150k per send without usage: ≈28-33M cal-1-like, ≈44M worst | F/D8/report.md L86, L674-676; F/E9/critic-result.json R6; F/E5/result.json `.cost_estimate` |
| L147: "GLM's rate is unmeasured"; ≈10.4M | GLM-5.3 on LiveMath was measured at 2.8-5.1k per call; the B arms add 12.7-15.2 KB; ≈11.8-17M plus cap-length tails | RL L217, L219; H/coevo5-v1-results-20261019.md L257; H/cal1-registration-20261020.md L97 |
| L149: X2 power from 4/16 vs 0/19 | that probe used another Skill (released GPT-5.5) on another solver (deepseek); all 4 picks were position-specific | F/D10/report.md L423-425, L484-486; F/D10/critic-result.json `.missing` #1 |
| L175, L177: OfficeQA certifies 10.3; transfer iff OfficeQA LB > 0 | 10.3 is D1's 37×4 figure; 74×2 at SD 0.385-0.486 needs ≥9-11 observed points; SearchQA-section rules are inert on OfficeQA; +20.3 regime flips | F/D1/result.json `.evidence`; F/E4/critic-result.json R6, `.missing` #4; F/E9/critic-result.json R2a, R4; F/E7/critic-result.json `.missing` |
| L173: X3 ≈26M | omits D1's first-round duplicate + placebo (2.36M per arm), proposal-batch rollouts and selftests; ≈30-35M real; needs ≈600 new items; code outside v4's scope, v4 not built | F/D1/result.json `.design`, `.cost_estimate`; H/v4-plans-20261021/spec.md L177-178; H/overnight-report-20261021.md L39 |
| L89, L95-96: X0 is training-side, 0 tokens, incl. "run D11 stage_table" | stage_table is built for v3 evaluation cells; opening them awaits the owner | F/D11/result.json `.recommendation` 2, `.risks`; PS L347 |
| L109, L117: "fresh SearchQA items" | 310 of 369 were measured by the D1 and E5 pilots; 59 never used | F/E5/critic-result.json `.missing` #7; F/D1/report.md L448-450; F/E5/result.json `.pilot` |
| L75: every comparison gets ≥3 placebos and a duplicate | not met by X1's scaffold contrast, X2 or X3 | P L115, L135-138, L168 |
| L104-105: scorer-v2 branches as tests | the I-ds rules were 100% tagged (branch nearly empty); the E-ds re-score is already known (post hoc) | F/E7/critic-result.json `.refuted_claims` #1, `.confirmed_claims` |

## 8. Confirmed (checked against the sources)

**v3 and cal-1.**
- v3: 0 rules in both chains; funnels 24→10→6→1→0→0 and 25→18→9→1→0→0; 139,024,462 deepseek ledger tokens
  (RL L142).
- cal-1 (H/cal1-registration-20261020.md L130-148):
  - ids-full +0.0938 [0.0505, 0.137];
  - bridges +0.0037 / −0.030 / −0.026;
  - C1 75.8% (n 11), 47.9% (n 6), 99.0% (n 20); null 0%;
  - 27,481,897 tokens;
  - same-text +0.0075, SD 0.144.

**Pools, scoring and gates.**
- Pool accounting 200/31/130/180/59; the counts 369, 6,642 and 2,622 (F/E5/critic-result.json `.missing` #7;
  F/D7/critic-result.json `.confirmed_claims`).
- JSON replies score 0 in every arm, 0/364 (F/D5/critic-result.json `.refuted_claims` #1).
- JSON-aware scoring: cand +0.0675, control:3 −0.0025, control:2 +0.036; the I-ds s1 rules are fully tagged
  (F/E7/critic-result.json `.confirmed_claims`, `.refuted_claims` #1).
- Registered gate false-positive rate for identical text 0.004-0.008 (F/D8/critic-result.json R1).
- v4 leaves out fresh-batch acceptance and threshold changes (spec L177-178). B7 only aligns the format predicate
  (spec L69-73).
- Folding the JSON fix into v4 is an open owner decision (PS L344 (d)). P's "not in v4" is right. The E7 critic's
  "这件事已经在 v4 的修复清单里" (F/E7/critic-result.json `.notes_cn`), repeated in the synthesis
  (H/feasibility-exploration-20261021-cn.md L111), is not.

**Costs and resolution.**
- Per-cell costs, card / scaffold: SearchQA 4,088 / 1,236; LiveMath 3,969 / 1,251; OfficeQA 7,927 / 4,690
  (F/D6/critic-result.json `.refuted_claims` #5).
- Certifiable effects 0.042 / 0.056 / 0.103; one round 4.72M (F/D1/result.json `.evidence`, `.cost_estimate`).
- E2: minimal row ≈292M, full table 1,574M (F/E2/critic-result.json R2; F/E2/result.json).
- Test-panel MDEs 3.7/6.3/7.3/6.5/8.0; pooled similar targets ≈3.0 (F/E5/critic-result.json `.refuted_claims` #4).

**Other critics and windows.**
- D10 critic (F/D10/critic-result.json R1, R2, R4, R8, R13):
  - a ±3 equivalence test needs ≈1,400 one-run items;
  - blocks C/D are the one-time holdout;
  - cal-1's placebos sat on the scaffold;
  - the compared Skills were learned for other solvers;
  - the measurement framing serves neither objective.
- E1 critic: controlled E1-X ≈6-8M; DecoEvo (F/E1/critic-result.json R13, `.missing` #1).
- D11 serving windows: OfficeQA +22.5; text × regime interaction −6.00 (F/D11/result.json `.evidence` C).

**GLM results and LiveMath.**
- RL L139, L220, L222:
  - generic − empty +0.075 / +0.092;
  - step over generic +0.029;
  - lz − bzero +0.001; lh − bhand +0.049; le − bzero −0.003.
- v1 macro 58.6 / 66.7 / 66.0 / 63.7 / 63.5; E − I[0] −2.8 [−5.5, −0.1] (RL L173).
- LiveMath meta option = key in 129/129 training items, by design per the benchmark paper (F/D7/critic-result.json
  `.confirmed_claims`, `.refuted_claims` #4).
- The v1 SkillOpt-glm Skill holds meta-option experience (H/coevo5-v1-results-20261019.md L322).

**Lists.** The stop list and the "do not restate" list agree with the critics.

## 9. Corrections for the synthesizer (plain Chinese, apply as written)

1. 把“D1 试跑里任务卡上两段无关文字 0.0 和 −2.3 分、同一文字重复 +0.4 分、任务卡比空骨架 +16.2 分”改成：
   - 这些数是在只含 SearchQA 那一段的说明（2,442 字节）上测的，不是五段完整任务卡（12,681 字节）；
   - 五段任务卡上加无关文字的效果，至今没有人测过；
   - D1 是探索阶段的一个小试跑；空骨架＝只有五个空标题的 Skill。
2. X1 是在 SearchQA 训练题上测“任务卡＋v3 学到的规则”对比“任务卡”的实验。它的“最小能测出的差别约 2.3 分”改为约
   2.8 到 3.7 分（369 道题、每题两次）。
   - 再加上多重比较校正（Holm 法）和“必须超过最好的那段无关文字”这一条，实际约 3.5 到 4.5 分。
   - 2.3 分是同一段文字和自己比的数，换任何文字都达不到。
   - 3.4 分用的波动是每题跑 4 次的数，而 X1 每题只跑 2 次。
3. X1 写明“事先概率”：
   - 即使真实效果正好是 0，“确定增益小于 3 分”这个结论也只有约三分之二到九成的机会得出；
   - 真有 3 分的增益，也只有约一半到八成的机会被认出来。
   同时写明三件事：
   - 区间上端用单侧还是双侧；
   - 多重比较校正包括哪几项检验；
   - “无关文字的波动超过 ±3 分”指的是点估计还是区间端点。若指区间端点，几乎一定会触发。
4. 删掉 H2a，即 X1 里“规则在空骨架上有效时，零花费重算 cal-1 子集分析”这一步。
   - cal-1 是校准实验：11 种文字 × 200 道题 × 每题 4 次。它的那项分析，要求同一批题上同时有候选规则、父版本和
     四段无关文字，每题答 4 次；X1 一样都没有。
   - 要做，就得在同一时段另跑约 4,800 格：实际约 600 万 token，账本约 1,300 万。
   - 否则必须明说，用的是改过的、没登记的判据。
5. X1 的“有效性条件”不要用“官方评分器下，任务卡比空骨架高至少 5 分”。
   - 原因：在模型“只答一句”的时段，空骨架自己会涨约 6 分，任务卡不动，整轮可能因此作废而且不重跑。
   - 改为：用认 JSON 的新评分器算这个差，要求高至少 2 分且区间下端大于 0。
   - 再加一个事先定好的“只答一句”回答比例的允许范围。
6. X1 的花费写成几档：
   - 按实际回答用量，约 2,300 万 token；
   - 账本上约 2,800 万到 3,300 万：发出后没返回用量的请求，账本会按约 15 万扣预留；
   - 最坏约 4,400 万。
   上限定为 4,500 万，并事先批准“停在上限后怎样续跑”：已开始的付费运行不能自动续跑，免得像 cal-1 那样中途停住、
   等人工处理。另外，提案里空骨架两组按每格 3,100 算，那是 cal-1 的账本平均；实际每格约 1,270。
7. X1 的“新题”改为“v3 没用过的题”。
   - 369 道里有 310 道已被 D1、E5 两个试跑测过，从未用过的只有 59 道。
   - 三段无关文字按固定规则选（例如登记的四段全用，或固定用前三段），不能参考 D1 在其中 130 道题上的结果。
   - 以前试跑的结果不能和 X1 合并。
8. X1 的结论加一句“只在这一个服务时段测得”。如果论文主结论要靠它，再在另一个时段补跑三组：任务卡、它的重复、
   整包规则（约 900 万 token）。
9. X1 的范围和对照写准：
   - X1 能给出的上界，是“v3 主链第一步那 3 条 SearchQA 规则的上界”，不要写成“v3 学到的全部”。
   - X1 里空骨架上的那组对比（A9 对 A8）没有重复组和无关文字，不满足提案自己“每个比较都要有至少三段无关文字和
     一个重复组”的规矩。要么补上，要么注明。
10. X2 是 LiveMath 数学选择题上，对“更强结论”这个固定选项做的反事实检验。它的花费改为约 1,200 万到 1,700 万 GLM
    token。
    - 提案说“GLM 的单价没测过”，不对。GLM-5.3 在 LiveMath 上已经测过，每次约 2,800 到 5,100 个 token。
    - 这里每次还要附 12.7 到 15.2 KB 的说明文字。
    - 偶尔还有推理到 65,536 上限的超长回答，曾把整条队列拖慢约 3.5 小时。
    - 上限按 60 次冒烟的实测值再定。
11. X2 按提案自己定的规矩补两个对照组（约多 1,748 格，约多花 500 万到 1,100 万 GLM token）：
    - 一个和 B2 完全相同的重复组（B2＝第 1 版里 SkillOpt-glm 学到的 Skill）；
    - 一个“删掉同样长度、但与这个选项无关的一段”的对照组。
    不补的话，要明说 X2 不满足这条规矩，B2 减 B3 的差里混着“删了 1 KB 多的解题步骤”。
12. X2 事先写清楚，怎样把“更强结论”选项放进原本没有它的题：
    - 是替换掉一个错误选项（仍保持五个选项），还是加成第六个选项。
    - B2 自己写着“4 到 5 个选项（A 到 E）”“只回答一个字母”。加成第六个会和它不一致，评分器接不接受 F 也没核实过。
    - 如果是替换，要说替换哪一个。题里总有一个“较弱但正确”的选项，不能换掉它。
    另外注明：功效估计借用的“16 次里选错 4 次，对比 19 次里 0 次”，来自另一份 Skill（SkillOpt 公开的 GPT-5.5 版）和
    另一个做题模型（deepseek），而且那 4 次全都出现在该选项紧跟正确选项之后。
    还要事先规定：被内容过滤拒答或限流失败的格，记为缺失，不记为答错；GLM 并发不超过 10。
13. X0 是零花费地登记新评分器并重算的那一步。其中“跑 D11 的阶段表”只能用训练侧数据：这个程序原本是为 v3 的测试格
    设计的，负责人同意打开 v3 测试分数之前，不能拿它读测试格。
14. X0 对 cal-1 和 v3 次链第一步的重新评分，是结果已知之后的重读，不能算事先登记的检验。审查员已经算出：次链那条
    规则在 200 道题上，从多对 0.75 道变成多对 13.75 道。
    - v3 登记的结论“0 条规则被收下”不变，只另写“按新评分器的事后重读结果”。
    - 主链（I-ds，从任务卡出发的那条）的规则 100% 写了答案标签，新评分器翻不了它们的判决，这一分支可以删掉。
15. X3 是在 SearchQA 上用“新题整版验收”进化、再到 OfficeQA 和 LiveMath 上看迁移的实验。它的迁移判据（OfficeQA 的
    区间下端大于 0）实际上达不到：
    - 74 道题、每题两次，要观测到约 9 到 11 分以上的迁移才行。提案引用的“10.3 分”是 37 道题、每题 4 次的验收批的
      数，不是这个设计。
    - 规则放在 SearchQA 分区里，按设计对 OfficeQA 根本不起作用。
    - 同一份 Skill 在同样 74 道 OfficeQA 题上，换个时段就差 20.3 分。
    两个改法：要么写明“收下的文字放进共用分区”，要么把 X3 的迁移部分标成“只作描述、不下结论”。
    X3 如果一条规则都没收下，就跳过迁移评测，约省 1,000 万 token。
16. X3 的花费补上每轮的训练执行和自测，以及 D1 设计要求的第一轮重复组和无关文字组：
    - 实际约 3,000 万到 3,500 万；
    - 账本按 cal-1 那样多扣，约 4,100 万到 4,600 万；最坏约 6,700 万。
    另外几件事：
    - 新的 SearchQA 题块要约 600 道：三步各 100 道用来提规则，再加一批 300 道用来验收。
    - 现有池里剩下的题正是 X1 用过的。拿来验收，就成了“同一批题既决定开跑、又决定收下”。
    - 抽题时怎样排除测试题和 C、D 两块，要事先登记，并由负责人批准。
    - “整版验收”的代码，第 4 版规格明确不包括；第 4 版本身也还没实现。
    - 要先决定：是用第 4 版修好的提规则环节，还是带着 v3 的已知毛病跑。v3 的 49 条提案里，有 21 条在正式检验前就
      被淘汰，多数是因为格式或流程上的小毛病。
17. 总预算改为：
    - 不跑 X3：实际约 3,500 万到 4,000 万；账本在 cal-1 那样的时段约 4,000 万到 5,000 万。
    - 跑 X3：实际约 6,500 万到 7,500 万；账本约 8,000 万到 9,500 万。
    - 最坏情况：每一段都像 cal-1 那样、账本是实际的 1.9 倍，约 1.4 亿，与 v3 的 1.39 亿相当。
18. 时间：X0、X1、X2 约需 2 个夜间会话。
    - 前提是复用 cal-1 的派发脚本，以及 D1、D10 审查员的脚本。
    - X1 在 12 路并发下约 2 小时，6 路约 7.5 小时；X2 约 5 小时。
    - 每段新代码先过一轮 Codex 审查和离线测试；付费运行放在 Linux 后台，并事先批准上限。
    - X3 至少还要再加 2 个会话，外加负责人批准。
19. 对负责人写清楚：
    - 这个计划里，没有一个实验能给“目标一（Skill 与验证端评分细则一起进化）”带来正面结果；
    - “目标二（在一个数据集上进化、到其余数据集评测）”只靠 X3，而 X3 的迁移判据基本达不到；
    - “先写测量论文、两个目标暂停”是否接受，要负责人自己决定；
    - 目标一最便宜的直接试验，是加了对照的 E1-X，约 600 万到 800 万 token，而且比较对象必须是“任务卡加候选规则”
      对比“任务卡”，不能是任务卡对比空骨架。

## 10. What survives (plain Chinese)

- 计划的主心骨站得住。先零花费地给评分器加上“认 JSON 答案”，作为新版本登记（X0）；再在 v3 没用过的 369 道
  SearchQA 训练题上，测“任务卡加 v3 规则”对比“任务卡”，带三段无关文字和一个重复组（X1）。
  - 这正是四位审查员都指出“从来没人测过”的那组对比。
  - 一个夜间会话做得完，实际约 2,300 万 token，只用训练题，不碰测试题。
- X2（LiveMath 那个固定选项的反事实检验）用的是匹配的做题模型和全部 283 道训练题，题量够测出 10 个百分点的
  选择率变化。补上花费、对照组和插入规则之后可以做。
- 提案列的“停止项”理由充分：
  - 第 4 版的进化链先不跑；
  - 迁移矩阵 E2 不做；
  - 用相似数据集训练题否决规则的 E9 不做；
  - D2、D4、E3、E6、E7、E8、E10 也都不做。
- “不要再重复的说法”清单准确。
- 事实清单（⟨1⟩ 到 ⟨38⟩）核对下来基本都对，只有两处要改：
  - ⟨7⟩ 把“只含 SearchQA 一段的说明”错叫成“任务卡”；
  - 第 121 行把 ⟨26⟩ 里每题跑 4 次的波动，用在了每题跑 2 次的设计上。
- X3 只能作为“SearchQA 上的方法检验”有条件地保留；它的迁移部分按现在的设计下不了结论。
