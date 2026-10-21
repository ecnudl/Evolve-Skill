# Paper first: publish the calibrated measurement result, add only what a reviewer will demand

Lens 论文优先; read-only, no model calls. Tags: [T] test opened with consent; [R] registered real run on training/dev data; [C] calibration; [P] pilot; [A] archived replay or critic recount; [L] literature. ⟨n⟩ = §6 row n.

## 1. 诊断 Diagnosis

**Verdict.** The evidence supports one paper: a calibrated measurement and negative-result study of continual Skill evolution. No positive method or transfer paper is supportable, and no experiment fitting 6–8 weeks and the data rules has the power to make one (§3–§4).

**Robust findings**

1. **A good instruction takes almost all of the gain.** Learning recovers that gain from weak starts but has not exceeded it.
   - SearchQA on GLM-5.3, interleaved arms, fresh items:
     - one learning step on top of the zero-shot instruction `bzero`: +0.1 [−1.6, +1.8] pts (975 items, 5 histories) [R]⟨13⟩;
     - one step from empty vs `bzero` on an independent 750-item block with 8 new seeds: −0.3 [−2.0, +1.4] [R]⟨14⟩;
     - the same step adds +4.9 [+2.0, +7.8] over a weak 3-line instruction and +13.0 from empty ⟨13⟩.
   - Five-bench test (v1, GLM) [T]⟨15⟩:
     - no learned method beats the card (macro 66.7 vs SkillOpt 66.0, E 63.7, GEPA 63.5);
     - learning from empty gains +4.8 to +7.4;
     - yet E minus the card is −2.8 [−5.5, −0.1].
2. **The gate cannot see rule-sized effects.**
   - cal-1 [C]⟨2⟩: C1 passes the +9.4-pt card 75.8% of the time at n = 11 and 47.9% at n = 6, with 0% null passage. Rule-shaped texts had no effect, so the gate was never calibrated at rule size.
   - v3 accepted 0 of 49 proposals for 139M tokens [R]⟨1⟩.
   - Replay [A]⟨8⟩: the format rule E-ds s1-r2 scored +8.1 on its 99-item check half, but was rejected on a 1/4-item gain over 6 trigger items.
3. **Artefacts are as large as the effects.**
   - JSON answers score 0 in every arm (0/364) ⟨5⟩. Scored JSON-aware, the cal-1 learned rule goes from −2.6 to +6.75 and the −9.8 placebo to −0.25 ⟨6⟩.
   - The same text on the same OfficeQA items differs by +22.5 [+11.5, +33.5] across serving windows ⟨20⟩.
   - SearchQA card − scaffold: +3.25 across windows, +9.25 interleaved ⟨20⟩.
   - Generated items mislead: +13 on 124 generated OfficeQA items, 0 on 74 real ones ⟨18⟩.

**Gaps a reviewer will hit (all this plan buys)**
- Placebos on the card: 2 texts on 130 items so far ⟨7⟩; cal-1's sit on the scaffold ⟨25⟩.
- v3's rules on the card, out of sample, with power (replay: −10.7 to +0.5 on 99-item halves ⟨8⟩).
- A scorer-robust re-reading (open owner decision; not in v4 ⟨32, 33⟩).
- A causal LiveMath construction-prior test (only a 56-cell probe ⟨24⟩).

**Candidate claims**

| Claim | Status | Needs | Turns positive if |
|---|---|---|---|
| A. Good instruction ≥ learned Skill; learning helps only from weak starts | Supported (GLM), partial (deepseek) | X0, X1; reuse ⟨7, 13–15, 17⟩ | X1 package − card LB > 0 above placebo band |
| B. Published-style gates underpowered; artefacts ≈ effects | Supported | X0, X1 | — |
| C. Learned LiveMath text raises a construction prior | Plausible | X2 | (reverses if X2 finds discrimination) |
| D. Evolve on one, gain on similar | Not supportable in 8 weeks | X3 if X1 positive | OfficeQA LB > 0 prospectively |
| E. Verifier co-evolution | Not supported | none | — |

Venue for A–C as one paper: TMLR (rolling), or ICML 2027 (~22 Jan, estimated) ⟨35⟩.

**Do not restate:** the −9.8 placebo as content; "+7 generic transfer" ⟨22⟩; a 14–17% gate self-pass (registered FWER 0.004–0.008 ⟨36⟩); ±3-pt equivalence (needs ~1,400 one-run items ⟨25⟩); foreign-solver audits as matched; LiveMath "net ≈ 0"; "validation-free" ⟨34⟩; "similarity map refuted" (absence of evidence, whole cards only ⟨21⟩).

**Novelty is crowded** ⟨35⟩: Liu et al. 2608.02636 (same suite; 55/388 candidates beat validation), Zhao et al. 2610.22984, SkillsBench, MAGE, Webson & Pavlick 2022, Atil et al. 2408.04667. Defensible: the calibrated gate (positive control + identical twin), placebo and identical-text controls on a good instruction (0/14 method papers ⟨35⟩), the artefact accounting, the instruction-quality curve.

## 2. 停 / 留 / 改

**Stop**
- **Launching v4 chains next.** v4 is plumbing, with acceptance and thresholds out of scope ⟨32⟩; v3 spent 139M for 0 rules ⟨1⟩; I-ds rules replay at −10.7 to +0.5 ⟨8⟩.
- **The E2 transfer matrix (2.9亿–15.7亿 tokens ⟨38⟩).** Rule effects of 1–3 pts sit below target resolution; OfficeQA certifies only 10.3 pts ⟨9⟩.
- **The similar-bench veto on other benches' training items (E9).** It is a selection gate, i.e. a validation set in disguise.
- **Verifier and generated-task claims.** Panels saturate (122/122); a harmful text passes 23/23 generated items, −5.3 on real ⟨27⟩.
- **D2, D4, E3, E6, E7, E8, E10.** Each critic rated it low ⟨37⟩.
- **Δ vs empty as the headline, and subtraction across windows** ⟨20⟩.
- **The "validation-free" name.** The decision pool is selection data ⟨34⟩.

**Keep**
- cal-1, with its inconclusive reading and noise floor ⟨2, 4⟩.
- The SearchQA instruction-quality studies on blocks A and B ⟨13, 14⟩.
- The v1 test table: registered readings, plus post-hoc deltas labelled as such ⟨15⟩.
- The D1 fresh-batch harness (duplicate +0.4, card placebos 0.0/−2.3, positive control +16.2) ⟨7⟩.
- The D11 template R1–R12 with its scripts ⟨20⟩.
- D7's meta/non-meta split ⟨23⟩, and D10's literature review with the critics' additions ⟨35⟩.

**Change**
- The task card becomes the headline comparator (`bzero` on GLM) ⟨13, 15⟩.
- Register scorer v2: JSON-aware extraction, with format scored separately. Report both scorers ⟨5, 6⟩.
- Interleave all arms in one session; identical requests ≥2 min apart; terse/tag-share monitors per 15 minutes ⟨20⟩.
- Every comparison gets ≥3 placebos and a duplicate on top of the parent ⟨25⟩.
- Evaluate every learned artifact with its matched solver ⟨25⟩.
- Name the protocols as protocol 1 (one fixed step) and protocol 2 (audit on later batches, then learn) ⟨34⟩.
- Every null carries its MDE and the label "bounded" or "undetermined" ⟨34⟩.

## 3. 接下来的实验序列

**Cost anchors**
- cal-1: 27,481,897 tokens for 8,800 cells, i.e. 3.12k per cell ⟨3⟩.
- Card-sized SearchQA cell: ≈4.1k ⟨31⟩.
- deepseek card-parent cell: LiveMath 3,969; OfficeQA 7,927 ⟨30⟩.
- One D1 round of 300 items × 2 runs: 4.72M ⟨9⟩.
- v3 in total: 139M ⟨1⟩.

### X0: scorer v2 and zero-cost re-reading (week 1; 0 tokens)

**Purpose.** Make every number robust to JSON scoring and drift before spending.

**Design**
- Register scorer v2 under a new version and output directory.
- Re-score training-side cells only: cal-1; v3 train/selftest/screen/confirm; pilots D1, D7, D9, D10, E4 and E9.
- Run D11 `stage_table` with its co-scheduling column.
- Audit:
  - X1's item overlap with all v1 and v3 draws;
  - v1's LiveMath draw (X2's in/out-of-sample split) and the meta bullets in SkillOpt-glm's step-3 text;
  - nine `.pyc` files in the frozen v3 snapshot, checked against its hashes ⟨30⟩.

**Decision rule**
- Both scorers are reported everywhere.
- If v2 flips an I-ds verdict, that null is labelled "scoring-sensitive" and the rule joins X1.
- If E-ds s1-r1 passes under v2 (predicted ⟨6⟩), report it as "the only acceptable rule re-learns the card's answer form".

**Pivot.** If the code changed beyond bytecode, stop before reusing v3 artifacts.

### X1: card + rule calibration on fresh SearchQA items (week 2; ≈26M deepseek, cap 35M)

**Purpose.** Supply what A and B lack: a placebo band on the card, an out-of-sample bound on what v3 learned, a rule-sized learned positive control, and a redundancy test.

**Design.** One interleaved session on deepseek-v4-flash at temperature 0. Scorer v2 is primary; the official scorer is secondary.

Arms: A1 card; A2 card duplicate; A3–A5 card + three registered v3 placebos (indices fixed before launch); A6 card + merged I-ds stage-1 package s1-r1/r2/r4 (D1's proposed pilot ⟨9⟩); A7 card + E-ds s1-r2; A8 scaffold; A9 scaffold + E-ds s1-r2.

**Items.** The 369 items of the 600-item SearchQA pool that v3 never used (D1's 130, E5's 180, the last 59) ⟨10, 11⟩. Each runs twice: 6,642 cells.

**Cost.** 7 arms × 738 × 4.1k + 2 arms × 738 × 3.1k ≈ 25.8M.

**Power.** MDE80 is ≈2.3 pts at the card's same-text SD (0.159) ⟨7⟩ and ≈3.4 pts at the distinct-text SD (0.2255) ⟨26⟩. The realised SD is reported.

**Decision rules (fixed now)**
- **Validity.** The A2 − A1 CI contains 0 and A1 − A8 ≥ +5 (official scorer); otherwise the run is void, no automatic rerun.
- **H1.** A6 "adds" iff the Holm one-sided LB > 0 and the estimate exceeds max(A3..A5 − A1). It is "bounded" iff UB95 < +3; otherwise "undetermined at the MDE".
- **H2 (redundancy).** LB of (A9 − A8) − (A7 − A1) > 0.
- **H2a.** If the LB of A9 − A8 > 0, the rule is the first rule-sized learned positive control. Then rerun cal-1's subset analysis at n = 6/11/20 (0 tokens).

**Pivot.** If H1 "adds", go to X3. If the placebo band exceeds ±3 pts, rule content cannot be separated from mere text presence; drop rule-level deepseek claims.

### X2: LiveMath meta-option counterfactual (weeks 2–3; ≈10M GLM, cap 20M)

**Purpose.** Test C causally: does learned meta-option text raise that option's prior regardless of truth?

**Design.** GLM-5.3, the solver matched to the artifact. Three arms:
- B1: the five-section card;
- B2: v1 SkillOpt-glm's step-3 Skill, verbatim (it contains the meta experience ⟨16⟩);
- B3: B2 with the meta bullets deleted.

**Items.** Drawn from the 283-item training pool ⟨11⟩:
- 129 true-meta items;
- 154 non-meta items as they are;
- the same 154 with the meta sentence inserted as a false option, its position counterbalanced by seed.

In total 437 variants × 3 arms × 2 runs = 2,622 cells. In-sample and out-of-sample items are reported separately.

**Cost.** GLM's rate is unmeasured; at deepseek's 3,969 per cell ≈10.4M. A 60-cell smoke measures it first; cap 2×.

**Power.** The partial probe saw 4/16 vs 0/19 ⟨24⟩; a true rise from 3% to 13% on 154 paired items × 2 runs has ≈80% power at α = 0.01.

**Decision rule**
- "Prior shift" iff the false-meta pick rate B2 − B3 > 0 at Holm p < 0.01 (size reported with CI).
- "Discriminating" iff its UB95 < +5 while the true-meta pick difference has LB > 0.
- Otherwise "undetermined". Non-meta accuracy carries its MDE (6–8 pts), never "no harm".

**Pivot.** If the result is "discriminating", reframe C as "a legitimate task-structure rule the card should state" ⟨23⟩.

### X3: conditional prospective evolve-on-SearchQA, then transfer read (weeks 4–5; 0 or ≈26M, cap 40M)

**Purpose.** The only route to claim D; runs only if X1's H1 "adds".

**Design (protocol 2)**
- One stage, starting from the card, under D1's fresh-batch acceptance:
  - one merged package per round;
  - accept if LB95 > 0 and the gain is ≥2 pts;
  - a futility look.
- Data: a never-sampled SearchQA block drawn with owner approval; not blocks C/D, no test data ⟨25⟩.
- Freeze the accepted Skill; evaluate it once against the card and a card duplicate:
  - OfficeQA, 74 items × 2 (registered similar ⟨12⟩);
  - LiveMath, 283 items × 2 (dissimilar).
- Target items never select anything.

**Cost ≈26M:** ≤3 rounds × 4.72M = 14.2M; GLM roles ≤2M; OfficeQA 444 cells × 7.9k = 3.5M; LiveMath 1,698 × 3.97k = 6.7M. Implementation ≈1 week plus one Codex round.

**Power.** Certifiable effects: SearchQA 4.2 pts, OfficeQA 10.3, LiveMath 5.6 ⟨9⟩.

**Decision rule.** Transfer is claimed only if the OfficeQA LB > 0. For LiveMath, "no drop" is stated only as a bound.

**If X1 is not positive,** X3 is writing and release (0 tokens): D11 tables, frozen texts with SHA-256, cell data.

**Totals**
- Null path ≈36M; positive path ≈62M (v3 used 139M).
- Weeks 3–6: writing; TMLR in mid-December, or ICML 2027 if ready by early January.

## 4. 如何服务两个目标

**Objective 1 (co-evolving the Skill and the verifier rubric): deprioritised.**
- With no accepted Skill change (v3: 0/49), the verifier has nothing to co-evolve with; generated items saturate and do not track real ones ⟨18, 27⟩.
- DecoEvo 2607.25675 already co-evolves a solver skill and a rubric generator; score-coupled verifier updates did worse in 13/15 cells ⟨28⟩.
- The paper gives objective 1 a negative-results section (0 tokens). The smallest direct test, a controlled E1-X (6–8M ⟨28⟩), is not scheduled.

**Objective 2 (evolve on one bench, evaluate on the rest, with no validation set): served as measurement, not as a positive claim.**
- The obstacle is structural:
  - SearchQA has 600 training items but only one similar target. Even the 172-item OfficeQA test then resolves only ≈6.3 pts.
  - OfficeQA has three similar targets (pooled ≈3.0) but only 74 training items ⟨29⟩.
- Existing readings are reported with their resolution: v1's Q2 +4.1 is a format effect shared by all arms ⟨15⟩; cross-bench harms ⟨19⟩; whole-card channel conflicts ⟨21⟩.
- X3 provides an evolve-on-one reading only if X1 finds something to transfer.
- "No validation set" is reworded as protocol 2 ⟨34⟩.
- Opening v3's test scores remains a separate owner decision ⟨33⟩.

## 5. 风险与证伪

**Falsifiers**
- F1: X1's H1 "adds": the gate, not learning, was the bottleneck; X3 runs.
- F2: scorer v2 flips I-ds verdicts: the v3 null is partly an artefact.
- F3: X2 is "discriminating": claim C reverses.

**Risks**
- A regime switch voids X1 (~26M); the validity rule catches it, with no automatic rerun.
- Someone publishes placebo-on-instruction controls first.
- Two solvers only; Liu et al.'s 3.92-pt same-Skill SD on a frontier solver ⟨35⟩ suggests the noise is not weak-solver-specific.
- Mostly dev evidence; holdouts stay unread ⟨33⟩.
- Neither owner objective becomes positive ⟨25⟩; adoption is the owner's call.
- The ledger may charge ~2× usage; caps apply to the ledger.
- After X1, SearchQA has no unused training items.

## 6. 事实清单

Aliases: RL = `docs/results-and-lessons.md`; H = `docs/handoff/`; F = `docs/handoff/feasibility-20261021/`.

- ⟨1⟩ v3: 0 rules in both chains (funnels 24→…→0, 25→…→0); deepseek 139,024,462 tokens. [R] RL L142
- ⟨2⟩ cal-1: ids-full +0.0938 [0.0505, 0.137]; bridges +0.0037/−0.030/−0.026; C1 75.8% (n 11), 47.9/99.0% (n 6/20); null 0%. [C] H/cal1-registration-20261020.md L137–148
- ⟨3⟩ cal-1 settled 27,481,897 tokens. [C] same, L130
- ⟨4⟩ Same-text noise +0.0075 [−0.0125, 0.0275]; per-item SD 0.144. [C] same, L143
- ⟨5⟩ JSON answers score 0 in every arm (0/364). [A] F/D5/critic-result.json `.refuted_claims`
- ⟨6⟩ JSON-aware: cand +0.0675, control:3 −0.0025, control:2 +0.036; I-ds rules fully tagged; E-ds s1-r1 would pass. [A] F/E7/critic-result.json `.confirmed_claims`, `.refuted_claims`
- ⟨7⟩ D1 pilot (130 × 2): card − scaffold +0.162; duplicate +0.004; placebos on card 0.000/−0.023; card SD2 0.159; 2,388,219 tokens. [P] F/D1/result.json `.pilot`
- ⟨8⟩ Replay: E-ds s1-r2 +0.081 on 99-item half, rejected on 1/4 of 6; I-ds rules −0.107 to +0.005. [A] F/D1/result.json `.evidence` (Replays)
- ⟨9⟩ Certifiable: SearchQA 0.042, LiveMath 0.056, OfficeQA 0.103; round 4.72M; package pilot. [P] F/D1/result.json `.evidence`, `.cost_estimate`
- ⟨10⟩ SearchQA never-used: 59 of 600 (200/31/130/180). [A] F/E5/critic-result.json `.missing` #7
- ⟨11⟩ v6 pools 600/74/283/120/57; tests 400/172/125/279/134. H/coevo5-registration-v6-20261017.md L84–88
- ⟨12⟩ Similarity map. Same, L69–72
- ⟨13⟩ Block A: lz − bzero +0.001 [−0.016, +0.018]; lh − bhand +0.049 [+0.020, +0.078]; le − empty +0.130; 37.39M tokens. [R] RL L222
- ⟨14⟩ Block B: le − bzero −0.003 [−0.020, +0.014], 750 items, 8 seeds; earlier +2.7 not replicated. [R] RL L220
- ⟨15⟩ v1 test: I-glm 0 rules; macro 58.6/66.7/66.0/63.7/63.5; E − I[0] −2.8 [−5.5, −0.1]; Q2 +4.1 = shared format effect. [T] RL L173
- ⟨16⟩ SkillOpt-glm LiveMath Skill holds meta-option experience. [T] RL L173 (5)
- ⟨17⟩ Generic − empty +0.075/+0.092; step over generic +0.029 [−0.011, +0.072]. [R] RL L139
- ⟨18⟩ OfficeQA candidates +13 generated, 0 real (p = 1.0). [R] RL L197
- ⟨19⟩ Cross-bench Skills on SearchQA −7.2 to −8.4 (lm_z41 −63.6); OfficeQA n.s. [R] RL L206, L209
- ⟨20⟩ Windows: OfficeQA +22.5 [+11.5, +33.5]; interaction −6.00 [−10.45, −1.55]; π_rep 0.119 vs 0.049; 42/42 tests. [A] F/D11/result.json `.evidence` A, C, E
- ⟨21⟩ E4 H1 +0.1 [−5.6, +5.5]; ALFWorld card → OfficeQA −26.7; critic: absence of evidence. [P] F/E4/result.json `.evidence`; F/E4/critic-result.json R4
- ⟨22⟩ "+7" and −9.8 corrected; 10 directions downgraded. [A] H/overnight-report-20261021.md L51
- ⟨23⟩ Meta option = reference in 129/129 training items; card should define it. [A] F/D7/result.json `.evidence`; F/D7/critic-result.json `.missing`
- ⟨24⟩ Probe: false meta 4/16 vs 0/19, 0/21. [A] F/D10/critic-result.json `.missing` #1
- ⟨25⟩ cal-1 placebos on scaffold; foreign-solver arms; ±3 TOST ≈1,400 items; new block, not C/D; owner mismatch. [A] F/D10/critic-result.json R1, R4, R8, R13, `.missing` #8
- ⟨26⟩ Distinct-text SD 0.2255 (4 runs). [A] F/D9/critic-result.json `.refuted_claims`
- ⟨27⟩ Generated panels 122/122; harmful text 23/23 generated, −5.3 real. [P] F/D12/result.json `.evidence`, `.recommendation`
- ⟨28⟩ DecoEvo; score-coupled verifier worse 13/15; E1-X 6–8M. [L] F/E1/critic-result.json `.missing` #1
- ⟨29⟩ Test MDE 3.7/6.3/7.3/6.5/8.0; pooled similar ≈3.0 vs 6.3. [A] F/E5/critic-result.json `.refuted_claims` #4
- ⟨30⟩ Card/scaffold cells: SearchQA 4,088/1,236, LiveMath 3,969/1,251, OfficeQA 7,927/4,690; `.pyc` in snapshot. [A] F/D6/critic-result.json `.refuted_claims`, `.missing`
- ⟨31⟩ Five-section Skills ≈4.1k per SearchQA cell. [A] F/D10/critic-result.json R11
- ⟨32⟩ v4 out of scope: fresh-batch acceptance, thresholds; B7 aligns predicate only. H/v4-plans-20261021/spec.md L69–73, L177–178
- ⟨33⟩ Scorer fix open; v3 test opening pending; holdouts unread. docs/project-status.md L344 (d), L347, L118
- ⟨34⟩ Decision pool = selection data; protocols 1/2; nulls with MDE. H/expert-feedback-20261012.md L195–197; H/expert-feedback-digest-and-plan-20261012.md L40–47
- ⟨35⟩ Liu et al. same suite (55/388; SD 3.92); controls 0/14; venues. [L] F/D10/report.md L184, L217–236, L711–726
- ⟨36⟩ Registered gate FWER 0.004–0.008. [A] F/D8/critic-result.json `.refuted_claims`
- ⟨37⟩ D2, D4, E3, E6, E7, E8, E10: critic feasibility low. [A] F/<ID>/critic-result.json `.corrected_feasibility`
- ⟨38⟩ E2 cost: minimal row 2.9亿 (critic), full matrix 15.7亿; OfficeQA cannot be a source. [A] F/E2/result.json; F/E2/critic-result.json `.notes_cn`

## summary_cn

建议：先别上第4版管线（v4，只修代码），改写一篇“有校准的测量与负结果”论文。证据：写好的任务说明（任务卡或照它写的指令）几乎拿走全部提升，检索问答 SearchQA 上在它之上再学只多0.1分；第3版正式运行（v3）一条规则都没收下；校准实验 cal-1 显示验收门槛只认得出约9分的改动；评分器把 JSON（一种数据写法）答案判错，假象与要找的效果一样大。只补四步：X0 零成本修评分器并重算；X1 在369道没用过的 SearchQA 训练题上测“任务卡＋学到的规则”和无关文字（安慰剂），约2,600万 token；X2 在数学选择题 LiveMath 上把“更强结论”选项故意做成错的，看学到的 Skill（附在提示里的说明）是否只是更爱选它，约1,000万 token；X3 仅当 X1 有真提升才做。目标一（协同进化）写成负结果一节，目标二（泛化）如实说分不出。可投 TMLR 期刊。
