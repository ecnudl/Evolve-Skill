# Evidence-fidelity critique of `proposals/paper.md` (lens 论文优先)

Critic: paper-evidence (adversarial, evidence fidelity). Verdict: **needs_revision**.

Method: I opened every source cited in the proposal's fact list ⟨1⟩–⟨38⟩ and the critic files behind them. I quote the exact source text below. Read-only: no model calls, no SSH, no test pools or evaluation directories opened. I wrote only this file.

Aliases: RL = `docs/results-and-lessons.md`; H = `docs/handoff/`; F = `docs/handoff/feasibility-20261021/`.

Evidence tags in this file:
- [R] registered real run on training/dev data
- [C] calibration
- [P] pilot
- [A] archived replay or critic recount
- [E] estimate
- [L] literature

## 0. Bottom line

**The core diagnosis survives.** The proposal's numbers are almost all copied correctly. These four findings hold up:
- On GLM-5.3, a good instruction takes nearly all of the gain.
- v3 accepted 0 of 49 rules.
- cal-1 was inconclusive.
- JSON answers and serving windows produce artefacts as large as the effects being looked for.

**About 20 statements overstate or misdescribe their sources.** The main failure is that framing outruns the evidence. Several of these errors favour the proposal's own plan:
- X1's items are called "fresh", but only 59 of 369 are untouched.
- X1's power uses a mislabelled SD measured at 4 runs.
- "Rule-shaped texts had no effect" is contradicted by the proposal's own X0 prediction.
- The cost anchors mix ledger figures with receipt figures.
- X3 adopts an acceptance rule that has no placebo arm. The proposal's own Change list forbids that, and the rule's own replay accepted a placebo.
- Two key inputs (D1, D12) were never critic-reviewed, and the proposal never says so.

None of this reverses the paper verdict, but the plan text must be corrected before it reaches the owner.

## 1. Refuted or misstated claims (exact source text)

### R1. X1 items are not "fresh" or "没用过的"
**Proposal**
- Heading: "X1: card + rule calibration on fresh SearchQA items".
- summary_cn: "X1 在369道没用过的 SearchQA 训练题上".
- The body correctly says "that v3 never used (D1's 130, E5's 180, the last 59)", so the heading and summary contradict the body.

**Source**
- F/E5/critic-result.json `.missing` #7: "SearchQA never-used: 59 of 600 (200 focal, 31 regression, 130 D1-v2, 180 E5-P1)".
- F/D1/result.json `.evidence`: "Pilot, 130 fresh SearchQA training items x 2 runs, 6 arms". The arms were card, card duplicate, two placebos on the card, scaffold, and recipe-on-scaffold. These are the same contrasts as X1's A1–A5.

**Why it matters**
- 310 of the 369 items were already read under related arms.
- D1's results on 130 of them set X1's power (SD 0.159).
- The items are out of sample relative to v3's rules, but they are not fresh. The registration must say this and report the 59 untouched items separately.

### R2. ⟨26⟩ "≈3.4 pts at the distinct-text SD (0.2255)"
**Source**
- F/D10/critic-result.json R1: "The SD behind this (0.22 at 4 runs) comes from near-identical text pairs. `ids-full` vs `seed-only` share the same SearchQA section". The distinct-text SDs are 0.326 (`cand` vs `parent:A`, 4 runs) and 0.383 (released Skill vs card, 1 run).
- F/D9/critic-result.json: "0.2255 (seed-only − ids-full), giving MDE 2.8 / 4.5 pts at n = 200".

**Why it matters**
- The number is a 4-run SD, but X1 runs each item twice.
- With E5 critic's card-addition tau 0.191 (F/E5/critic-result.json #5: "tau 0.191 ... MDE 4.9 points at 200 items"), the 2-run SD is about 0.255. That gives MDE80 ≈ 3.7 pts at 369 items (my derivation).
- The 2.3-pt figure (same-text SD 0.159) applies only to the duplicate check, not to H1.

### R3. "Rule-shaped texts had no effect, so the gate was never calibrated at rule size"
Also the related headline "The gate cannot see rule-sized effects".

**Source**
- H/cal1-registration-20261020.md L150–151: "The rule-shaped bridges carry no detectable effect at all, so nothing rule-sized was available to calibrate C1 on". This is absence of evidence: the CIs span about ±3–4.6 pts.
- F/E7/critic-result.json:
  - JSON-aware scoring: "cand +0.0675, control:3 -0.0025, cand minus ids-full -0.010, control:2 still +0.036".
  - For v3 E-ds s1-r1: "screen goes from +0.75 to +13.75 items of 200, confirm from -2.50 to +12.25".
  - "the artifact explains the secondary chain's single best rule (which restates the task card), not the primary chain's null".
- H/overnight-report-20261021.md L51: "修好后 v3 次链那条被拒的规则大概率会被收下".
- The proposal's own X0 predicts the same thing: "If E-ds s1-r1 passes under v2 (predicted ⟨6⟩)".

**Why it matters**
- The secondary-chain (E-ds) null is partly a scorer artefact.
- What is measured is low per-step power, not invisibility. D8 gives per-step power 0.19–0.26 for 0.3–3-pt rules.
- "Never calibrated at rule size" is the part that stands.

### R4. ⟨8⟩ The "+8.1 on its 99-item check half" replay is presented as a gate miss
**Source**: F/D1/result.json `.evidence`: "E-ds s1-r2 (an answer-format rule) scored +0.081 on its 99-item never-shown check half (p1 = 0.0034; the Bonferroni threshold over 17 arms is 0.0029)". D1 also gives a winner's-curse inflation of 1.34–1.51x.

**What the proposal omits**
- This is the post-hoc best of 17 replayed arms, and it misses the multiplicity threshold.
- It is a format rule on the empty-scaffold chain. There the interleaved scaffold loses its answer tag 10% of the time, against 0.1% for the card (F/E6/critic-result.json R3).

### R5. "I-ds rules replay −10.7 to +0.5 on 99-item halves"
This appears in Gaps and in Stop.

**Source**
- F/D1/result.json: "All 7 I-ds rule arms: -0.107 to +0.005 on their check halves". The halves differ in size by bench; they are not all 99 items.
- F/D9/critic-result.json, per bench:
  - SearchQA "+0.000 / +0.004 / +0.015"
  - LiveMath "−0.022"
  - SpreadsheetBench "−0.044 / +0.027"
  - ALFWorld "−0.140 [−0.254, −0.035]"

**Why it matters**: on SearchQA, the bench of X1 and of A6's s1-r1/r2/r4, the I-ds rules are null to small, not harmful. The bottom of the range comes from small non-SearchQA halves.

### R6. ⟨27⟩ "a harmful text passes 23/23 generated items, −5.3 on real"
**Source**
- F/D12/result.json: "-5.3 points [-12.3, +1.8], sign test p=0.375, not significant" (57 paired real items).
- H/overnight-report-20261021.md table 6.5 lists D12 as "未审查".

**Why it matters**: harm on the real items is not established, and this input has no critic review.

### R7. "identical requests ≥2 min apart ⟨20⟩"
**Source**
- D11 (⟨20⟩) does not contain this. The claim is E4's.
- F/E4/critic-result.json R2: "The 0/23 holds only for the SearchQA scaffold. SearchQA card arms flip MORE when lagged: 11/106 (10.4%) vs 6/94 (6.4%) back-to-back ... Spacing sends is harmless, but it does not lower the 8-10% flip floor."
- F/E2/critic-result.json: same-arm agreement is 0.88 at 1–10 min, 0.84 at 10–60 min and 0.74 beyond 1 h.

**Correction**: keep spacing only as a harmless precaution, not as evidence-based noise control.

### R8. ⟨19⟩ "Cross-bench Skills on SearchQA −7.2 to −8.4 (lm_z41 −63.6); OfficeQA n.s."
**Source**
- RL L206 also lists "`oq_z41` −2.8 [−6.8, +0.9]（未见损害）" and "`qa_v9` +1.6".
- RL L209: on OfficeQA "区间都含0，记'未见损害'". These CIs are about ±12 pts on 74 items.

**Correction**: the range is −2.8 to −8.4, with 3 of the 4 non-catastrophic texts showing harm. The results are GLM-5.3 on a 250-item block, not a test. The OfficeQA "n.s." is absence of evidence.

### R9. The cost anchors mix accounting bases
**Proposal**: X1 = "7 arms × 738 × 4.1k + 2 arms × 738 × 3.1k ≈ 25.8M", under a cap of 35M. "Null path ≈36M; positive path ≈62M (v3 used 139M)."

**Source**
- The 3.12k figure is the cal-1 ledger average across all 11 arms. H/cal1 L129–131: "ledger settled 27,481,897 tokens (cap in force 35,000,000; declared 25,000,000). Resume cost 2,613,063 tokens (1,622 per cell)".
- The 4.1k and 3,969/7,927 figures are measured per-call costs of v3 training cells. F/D6/critic-result.json #5: "Measured v3 stage-entry training cells under the task-card parent (I-ds) cost 3,969 tokens (LiveMath), 4,088 (SearchQA), 7,927 (OfficeQA)".
- F/E7/critic-result.json #8: "This compares an estimate of receipt usage with a ledger figure ... cal-1's own receipts sum to 14.0M (17.6M charged), but its ledger settled 27.5M ... cal-1 paused on its cap for exactly this reason".
- F/D8/critic-result.json R5: "The ledger can charge about 1.9x real".
- F/E9/critic-result.json R6: cal-1 charged means were scaffold 2,780 and ids-full 4,669.
- v3's 139M is a deepseek ledger figure. It excludes GLM 7.80M and includes "I-ds stage-0 evaluation 21.33M; ALFWorld I-start step 59.43M" (F/E2/critic-result.json).

**Why it matters**
- The proposal itself warns that "The ledger may charge ~2× usage; caps apply to the ledger", but it does not apply that warning.
- On a ledger basis X1 is about 28–45M, so the 35M cap can stop it mid-run.
- The comparison with v3 is not like-for-like.

### R10. ⟨29⟩ / §4 "Even the 172-item OfficeQA test then resolves only ≈6.3 pts"
**Source**
- F/E5/critic-result.json #4: "There the population MDE at 2 runs is 3.7 / 6.3 / 7.3 / 6.5 / 8.0 points".
- The registered test runs each item once. RL L173: "每格每题 1 次".
- F/D5/critic-result.json missing #4 ("TEST_SIZES 400 / 172 / 125 / 279 / 134, 1 run"): "About 4-5 points on SearchQA, 6.6-7.7 on OfficeQA, 10-11 on LiveMath, 7-7.7 on SpreadsheetBench and 9-10 on ALFWorld".
- F/D11/critic-result.json #2, with Holm correction: "SearchQA about 4.6-7.3, OfficeQA about 8.2-9.6, LiveMath, SpreadsheetBench and ALFWorld about 11.6-12.9 points".

**Why it matters**: the proposal quotes the most optimistic set. The direction holds and the corrected numbers make the conclusion stronger.

### R11. "Keep: The D11 template R1–R12 with its scripts"
**Source**: F/D11/critic-result.json #4:
- "(a) R8 is not implemented".
- "(b) The R3 Tango switch, the R6/R7 sensitivity flags, the R10 transfer and non-inferiority verdicts, and the R11 placebo column are all missing".
- "(c) ... `signflip_test(d)`, flips single items rather than OfficeQA clusters".

**Why it matters**: the template is a plan, not a working tool. X0's "Run D11 `stage_table`" depends on these missing parts.

### R12. Unreviewed inputs (D1, D12) are carried as established, and X3's acceptance rule is used without a placebo
**Source**
- H/overnight-report-20261021.md table 6.5: D1 "未审查", D12 "未审查".
- F/D1/result.json `.evidence` (D1's own replay on cal-1): "It also accepts the control:2 placebo (+0.036, LB +0.011)".

**Why it matters**
- X1's items and power, X3's acceptance rule and X3's power all rest on D1.
- X3 runs "accept if LB95 > 0 and the gain is ≥2 pts" with no placebo arm. The proposal's own Change list requires "Every comparison gets ≥3 placebos and a duplicate on top of the parent".

### R13. X2 power basis
**Proposal**: "The partial probe saw 4/16 vs 0/19 ⟨24⟩; a true rise from 3% to 13% ... ≈80% power at α = 0.01". Also "Non-meta accuracy carries its MDE (6–8 pts)" and "GLM's rate is unmeasured".

**Source**
- F/D10/critic-result.json `.missing` #1: "With the two meta bullets, the solver picked the false meta option 4/16 times. Under the task card: 0/19. Without the bullets: 0/21". Also: "Caveat: all 4 false picks came where the meta option sat right after the correct option (4/7, versus 0/9 elsewhere). The full version needs balanced positions and at least 2 runs (about 0.3M tokens)".
- That probe used a different Skill (the released SkillOpt Skill's bullets) on a different solver (deepseek), with 1 run.
- The 3%→13% rates and the "6–8 pts" figure have no source.
- F/D10/critic-result.json R1 gives LiveMath distinct-text SDs of 0.389–0.483. That implies ≈9–11 pts for B2 vs card at 154 items × 2 runs (my derivation).
- GLM-5.3 was already the LiveMath solver in v1 (RL L173 costs), so its rate can be derived at 0 tokens.

### R14. X3 power and data
**Proposal**: "Certifiable effects: SearchQA 4.2 pts, OfficeQA 10.3, LiveMath 5.6 ⟨9⟩".

**Source**
- These are D1's source-side acceptance figures for 300×2 / 37×4 / 233×2 batches. They are not figures for X3's transfer read, which is 74×2 Skill vs card.
- F/E4/critic-result.json missing #6: "an SD of 0.25 and an effect of 3 points need about 540 items, which OfficeQA cannot supply".
- F/E2/critic-result.json #7: the OfficeQA pool "has been reused by four pilots ... a de facto development set".
- F/E9/critic-result.json R4: "Same Skill hash (cc516459), same 74 items ... +20.3 points ... Interleaving removes level shifts but not this text-by-session interaction".
- docs/project-status.md L414, the owner on 10/15: "用真题与'不需要验证集'的说法有冲突".

**Why it matters**: the proposal stops E2 because "OfficeQA certifies only 10.3 pts", yet X3 has the same limitation.

### R15. "v4 is plumbing"
**Source**
- H/v4-plans-20261021/spec.md L122–132 (P1): "Conditional rule template and condition-derived triggers ... trigger := the items judged applicable".
- spec.md L148 (P4, votes), L155 (P5, one analyst call per code cluster), L160 (P6, balanced evidence).
- spec.md L99: "B13 = P7 ... the solver's framing sentence".
- F/D5/critic-result.json missing #3: "v4's B13/P7 rewrites the solver framing sentence in every request. All cal-1 noise and drift numbers belong to the v3 prompt and must be re-measured".

**What survives**: L177–178 put acceptance and thresholds out of scope, so "v4 likely accepts 0 again" stands. But v4 also changes how rules and trigger sets are made, and it changes the solver prompt.

### R16. F2 ("scorer v2 flips I-ds verdicts") is largely pre-empted
**Source**: F/E7/critic-result.json: "in the s1 SearchQA screen, the parent and all 3 screened rules (s1-r1, s1-r2, s1-r4) have tag share 1.000 and 0 JSON replies. I-ds s3 is ≥0.93 with 0 JSON". Also: "At most 1-2 of the 7 screened SearchQA rules are affected." The proposal's own ⟨6⟩ already says "I-ds rules fully tagged".

**Correction**: F2 can test only E-ds and the stages not yet checked.

### R17. Claim B "Published-style gates underpowered — Supported"
**Source**
- All the cited evidence (⟨1⟩, ⟨2⟩, ⟨8⟩) is the project's own registered gate.
- For published strict-improvement gates, F/D10/result.json says only: "ESTIMATED: - A strict-improvement gate accepts a no-op 33-46% of the time on selection sets of 17-200 items". This is unreviewed: the D10 critic does not check it. It also points the other way: too permissive, not underpowered.
- The 14–17% self-pass was refuted: F/D8/critic-result.json R1 gives a registered FWER of 0.004–0.008.

**Correction**: split claim B into two parts:
- Our registered gate is underpowered (measured).
- Published strict-improvement gates are estimated to accept no-ops often (not measured).

### R18. summary_cn "校准实验 cal-1 显示验收门槛只认得出约9分的改动"
**Source**: H/cal1 L148–150: "passage at the registered n = 11 is 75.8%, i.e. **between 50% and 80%: inconclusive by the pre-registered table**". Passage is 47.9% at n = 6. On other pools it ranges 54.3–94.1% (L141).

**Why it matters**: the gate does not reliably detect even the 9-pt card; the registered result is "无法下结论" (inconclusive).

### R19. The "calibrated gate (positive control + identical twin)" anchor is mostly format
**Source**
- F/E6/critic-result.json R3: "the same contrast is only +0.0325 [-0.004, +0.069] ... The cal-1 +0.093 arises largely because the interleaved empty scaffold loses its answer tag (10%) while ids-full never does (0.1%)".
- F/E10/critic-result.json R6: alias-lenient scoring gives +0.0925 → +0.061.

**Why it matters**: under scorer v2 the anchor shrinks. X1's validity rule "A1 − A8 ≥ +5 (official scorer)" mainly measures the scaffold's tag loss.

### R20. Smaller fidelity slips
- **⟨13⟩ registered label omitted.** The registered P1 reading is "缺失条件下未分辨". The bound is [−0.031, +0.032] (RL L222).
- **⟨15⟩ registered label omitted.** RL L173 marks "E−I[0] −2.8 [−5.5, −0.1]（不确定）" and "每条链一条历史，区间只反映测试题抽样".
- **⟨18⟩ caveats missing.** The result is GLM-5.3. The candidates were partly selected on generated items (E1 critic R6). On deepseek the gap is +0.6, "untestable with 74 real items, not 'invalid'" (E5 critic #2).
- **⟨35⟩ "same suite" overstated.** F/D10/report.md L184 itself reads "Same suite as ours (SearchQA, OfficeQA, SpreadsheetBench, LiveMath, DocVQA ...)". That is 4 of our 5 benches: DocVQA in place of ALFWorld. The source's wording is "55 of 388 candidates establish byte-distinct validation bests".
- **⟨28⟩ citation.** "E1-X 6–8M" is in the E1 critic's refuted list, not in `.missing` #1.
- **Objective 1 section incomplete.** It omits the project's own history. F/E10/critic-result.json R7: "In V4, 8 validator updates gave 5 valid and 3 invalid candidates and 0 promotions". Also "V16 had 0 new natural detections".
- **"Validation-free" renaming presented as settled.** The proposal lists it as a Stop and Change item, but H/expert-feedback-digest-and-plan-20261012.md L45 says "需要负责人定". The owner's stated preference runs the other way: RL L89 on 10/11 ("最好不削弱'基本不需要验证集'的说法") and docs/project-status.md L115 ("不靠验证集也有好结果").

## 2. Confirmed claims (number matches the cited source)

**v3 and cal-1**
- ⟨1⟩ RL L142 gives the funnels "24 → 10 → 6 → 1 → 0 → 0" and "25 → 18 → 9 → 1 → 0 → 0" (0/49), and deepseek 139,024,462 tokens. This is the deepseek ledger only.
- ⟨2⟩⟨3⟩⟨4⟩ H/cal1 L130 and L137–148:
  - ids-full +0.0938 [0.0505, 0.137]
  - bridges +0.0037 / −0.030 / −0.026
  - C1 passage 75.8% / 47.9% / 99.0%
  - null passage 0%
  - ledger 27,481,897 tokens
  - noise +0.0075 [−0.0125, 0.0275], SD 0.144

**Scorer and pilots**
- ⟨5⟩ JSON answers score 0/364 (D5 critic).
- ⟨6⟩ The JSON-aware figures and "I-ds rules fully tagged" match the E7 critic.
- ⟨7⟩ The D1 pilot figures match: +0.162 [+0.104, +0.223], +0.004, 0.000 / −0.023, SD2 0.159, 2,388,219 tokens. D1 is unreviewed.
- ⟨8⟩ The figures match: +0.081, and "rejected it on a 1/4-item C1 gain from 6 trigger items". The surrounding description is criticised in R4 and R5.
- ⟨9⟩ D1's certifiable effects are 0.042 / 0.056 / 0.103 and a round costs 4.72M (a receipt-based figure).
- ⟨10⟩⟨11⟩⟨12⟩ match: 59 of 600 never used; pools 600 / 74 / 283 / 120 / 57; tests 400 / 172 / 125 / 279 / 134; the similarity map.

**SearchQA instruction studies and the v1 test**
- ⟨13⟩ RL L222: lz − bzero +0.001 [−0.016, +0.018]; lh − bhand +0.049 [+0.020, +0.078]; le − empty +0.130; 3,739万 tokens.
- ⟨14⟩ RL L220: le − bzero −0.003 [−0.020, +0.014]. The "+2.7 not replicated" refers to the lp − le prompt tier.
- ⟨15⟩⟨16⟩ RL L173: macro 58.6 / 66.7 / 66.0 / 63.7 / 63.5; learning gains +4.8 to +7.4; "Q2 相似 +4.1 ... 是作答写法的作用"; the SkillOpt LiveMath Skill contains "元选项常是答案".
- ⟨17⟩ RL L139.
- ⟨18⟩ RL L197, with the caveats in R20.

**Other feasibility directions**
- ⟨20⟩ The D11 figures (+22.5 [+11.5, +33.5], −6.00, π_rep, 42/42) are reproduced by the D11 critic.
- ⟨21⟩ E4 and its critic: "absence of evidence".
- ⟨22⟩ The overnight report L51 correction.
- ⟨23⟩ The meta option is the reference in 129/129 items (also recounted by the D10 critic).
- ⟨24⟩ 4/16 vs 0/19 and 0/21.
- ⟨25⟩ D10 critic R1, R4, R8, R13 and `.missing` #8.

**Costs, v4 and project status**
- ⟨28⟩ DecoEvo "fell below SkillOpt in 13 of 15 cells".
- ⟨30⟩ D6 critic per-cell costs, and the .pyc side note.
- ⟨31⟩ D10 critic R11, ≈4.1k per cell.
- ⟨32⟩ JSON-aware extraction really is **not** in v4. spec L69–73 (B7 aligns only the format predicate) and L177–178 confirm this. The proposal is right here. The E7 critic notes_cn ("这件事已经在 v4 的修复清单里") and the synthesis report H/feasibility-exploration-20261021-cn.md §E7 are wrong.
- ⟨33⟩ docs/project-status.md L118, L344 (d), L347.

**Owner feedback and literature**
- ⟨34⟩ H/expert-feedback-20261012.md L195–197 and the digest L40–47 (protocols 1 and 2; report the MDE beside every null). The renaming is an owner decision (R20).
- ⟨35⟩ F/D10/report.md:
  - L184: Liu et al. 55/388; SD 3.92 on Gemini, OfficeQA, 8 evaluations.
  - L217–223: "0 of 14" identical-text and placebo controls.
  - L715–726: TMLR rolling; "ICML 2027 | Possible as an analysis paper; harder for a pure negative result | ... ≈ 22 Jan 2027 [E]".
  - The venue claim is sourced. The proposal should keep the caveat "harder for a pure negative result".
- ⟨36⟩ Registered FWER 0.004–0.008 (D8 critic R1).
- ⟨37⟩ All seven named directions are corrected_feasibility = low.
- ⟨38⟩ E2: 2.9亿 / 15.7亿 tokens; OfficeQA cannot be a source.

**Arithmetic**
- X1 25.8M; X2 2,622 cells and 10.4M; X3 26.4M; totals 36M and 62M; MDE 2.3 at SD 0.159 over 369 items. All are correct as computed.

**"Do not restate" list**: it is consistent with the critics.

## 3. Feasibility issues

**X1**
1. **Cost cap.** On a ledger basis X1 is about 28–45M against a 35M cap, so it may pause mid-run. cal-1 paused on its cap.
2. **Run time and serving regimes.**
   - X1 needs 6,642 cells. At 7–24 cells/min (F/D10/report.md L701) that is about 4.6–15.8 h.
   - "The serving regime flipped about hourly" (E2 critic).
   - The text × regime interaction is measured: D11 gives −6.00 [−10.45, −1.55], and E9 critic R4 gives +20.3 for the same hash.
   - So X1 needs a regime-stratified readout registered before launch.
3. **Validity rules.**
   - The duplicate canary "cannot detect the text-dependent drift ... alarm fires on about 5% of valid rounds by construction" (E2 critic). With no rerun allowed, that is about a 5% chance of voiding a valid run.
   - A1 − A8 ≥ +5 (official scorer) mostly checks the scaffold's tag loss.
4. **H1 power.**
   - The realistic MDE is about 3.7–3.9 pts, plus the hurdle of beating the maximum of three placebo differences.
   - The SearchQA I-ds rules replay at +0.0 / +0.4 / +1.5.
   - Under a true null, "bounded (UB95 < +3)" is reached only about 60% of the time (half-width ≈2.6 pts at SD ≈0.255).
   - So "undetermined" is a likely outcome and should be planned for.
5. **H2/H2a scorer.** H2a's positive control is an answer-format rule. With scorer v2 primary, its effect may shrink by construction, so the scorer for H2/H2a must be pre-registered.
6. **Items.** Only 59 truly untouched SearchQA training items remain. After X1 there are none, and any new block needs owner approval and a new registration.

**X2**
7. **Basis and realism.**
   - The power basis is a different Skill and solver, with a position confound.
   - The non-meta MDE against the card is about 9–11 pts.
   - "A false meta distractor never occurs in the real benchmark" (D7 critic). The benchmark paper §2 says the meta option replaces the correct answer by construction (D7 critic R4).
   - So X2 answers a counterfactual about the model's prior. It is not a claim about the real benchmark.

**X3**
8. **Acceptance and data.**
   - D1's acceptance rule has no placebo arm and accepted a placebo in replay.
   - OfficeQA's 74 items are a de facto development set.
   - The transfer MDE on 74 × 2 is about 10–12.5 pts.
   - Target pools used as panels and a new SearchQA block both need owner decisions, and the owner flagged the conflict with the no-validation claim.

**X0**
9. **D11 parts missing.** X0 depends on D11 rules that are not implemented, and the cluster-level p-value is missing.

**Owner decisions**
10. **Renaming.** Renaming "validation-free" to "protocol 2" is an owner decision against the owner's stated preference. The plan must present it as a recommendation, not as a step.

## 4. What survives

- **A good instruction takes nearly all of the gain (GLM-5.3, SearchQA).** One step on top of bzero gives +0.1 on 975 items and −0.3 on 750 items. Learning helps only from weak starts: +4.9 and +13.0. In the v1 five-bench test, no learned method beats the card.
- **The registered gate failed.** v3 accepted 0/49 rules. cal-1 was inconclusive (75.8%), and nothing rule-sized has been calibrated.
- **Artefacts match the effects in size.** JSON answers score 0/364. The same text differs by +22.5 across serving windows. Placebos move scores; even after the JSON fix, control:2 stays at +3.6.
- **Generated items are an unvalidated proxy.**
- **Objective 1 (verifier co-evolution) has no supporting evidence.** The project's September history makes this stronger.
- **The plan is worth keeping with changes.** A "calibrated measurement + negative result" paper is the supportable deliverable. X0, the zero-token scorer-v2 re-reading, is the right first step, and the JSON fix is indeed outside v4. X1, a placebo band on the card, is worth running once its framing, power, cost basis and regime handling are corrected. X2 and X3 need redesign and owner decisions before any spend.
