# Evidence-fidelity critique of proposals/method.md (lens: 方法优先)

Critic: adversarial evidence-fidelity reviewer, 2026-10-21. Read-only; no API calls, no SSH, no test pools opened.
Proposal: `scratchpad/direction/proposals/method.md` (line numbers below are that file's `cat -n` lines).
Every source below was opened and the quoted text copied from it. Paths are relative to
`/Users/dulin/Documents/Paper/SkillOpt/docs/`; `Xr` = `handoff/feasibility-20261021/X/result.json`,
`Xc` = the `critic-result.json` beside it.

## 0. What I did

1. Read the brief, the proposal, the overnight report (all 141 lines), the 13-direction synthesis, the cal-1
   registration with its dispatch log, ledger entries L139 (10/12), L142, L144, L146, project-status §0/§1/§4/§5
   lines cited, v4 spec.md (all 196 lines), v6 registration L71/L84–88/L124, current-workflow L56/L388.
2. Opened `result.json` and `critic-result.json` for every direction the proposal cites (D1, D4, D5, D6, D9,
   D13, D14 report, E1, E2, E3 + report, E4, E5, E6, E7, E8, E9, E10), and D7's report for the LiveMath draw.
3. Checked each of the 55 table entries (S1–S55) and each number in the text against its cited field/line.

Tally: of 55 table rows, 44 check out exactly; 7 are accurate as numbers but are used for a reading the sources
contradict (S1–S3 reading, S5, S7/S8 s1-r1 part, S12, S14, S21 label, S55); 4 have minor numeric/label errors
(S19, S22, S28-as-cost, S38-scope). Three load-bearing text claims have no checkable source (fired share 0.4/0.3,
M4 per-version 11–21M, test read ≈22M; the last two are plausible arithmetic).

## 1. Verdict: needs_revision

The proposal is unusually well sourced, and most of its numbers are right. But its **central diagnosis (§1.1,
"the evolved unit is smaller than the instrument can resolve") misreads cal-1** and rests on official-scorer numbers
that the proposal's own CH4 treats as an artefact; it **repeats an E4 claim the E4 critic refuted** (send spacing);
it says an arm was **"never run" that v3 ran** and that the proposal itself cites; it upgrades "**not established**"
to "**does not exist**"; and its **cost figures for the owner use receipts and treat a cap as a cost**. The
experimental direction (one version-level acceptance on a large unseen batch vs card + placebos; ground-truth
verifier; v4 = fixes only; stop per-rule C1 chains) is not refuted, but several of its stated reasons must change.

## 2. Refuted or must-be-qualified claims

### R1. "The evolved unit is smaller than the instrument can resolve" (L11, L13; S1–S3) — misreads cal-1
Proposal: "Rule-sized texts move SearchQA by about 0 (+0.004, −0.030, −0.026). They pass C1 0–7.7% of the time,
while the +9.4-point card passes 75.8%."
- The numbers are right (cal1-registration L138–139). The reading is not. cal-1's own pre-registered reading,
  L148–152: "passage at the registered n = 11 is 75.8%, i.e. **between 50% and 80%: inconclusive by the
  pre-registered table** ... The rule-shaped bridges carry no detectable effect at all, so **nothing rule-sized was
  available to calibrate C1 on**". A 0% passage for a text with no effect is a correct rejection, not evidence that
  the instrument cannot see rule-sized effects.
- Under JSON-aware scoring (which the proposal adopts in CH4) the bridges are not ≈0. E7r `evidence` H
  (re-score of all 8,800 cal-1 cells): "cand: -0.026 to **+0.0675 [0.030, 0.106]**, 44/19 - seed-rule3: -0.030 to
  +0.031 [0.003, 0.061]"; E7c `confirmed_claims`: "The 200x4 arithmetic checks: cand +0.0675". D5c `missing` #2:
  "The cand rule rescores to +6.4 points (t 3.35)".
- Even under official scoring a learned rule-sized text was resolvable: D1r `evidence`: "E-ds s1-r2 (an
  answer-format rule) scored +0.081 on its 99-item never-shown check half (p1 = 0.0034 ...)"; D9c
  `confirmed_claims`: "E-ds s1-r2 +0.055 [+0.020, +0.091]" and, on the card parent, "ALFWorld −0.140 [−0.254,
  −0.035]" (a resolvable harm).
- Why it matters: §1.1 motivates CH1 (package) as a fix for resolution. The evidence instead says rule-sized text
  is resolvable against an empty scaffold; what has never been seen is a gain **over the card**, and E7c says the
  best rule's content "restates the task card"; the E8 summary (overnight report L66) says "提炼的 14 条规则 6 条重复要点". Packaging rules does not
  create headroom over the card. What survives of §1.1: per-rule C1 on 6–11-item trigger panels is underpowered
  (S11 MDE 4.8 at 200 items is right; cal-1 inconclusive even for +9).

### R2. "Card + learned rule versus card was never run" (L41; S14; also K1) — false as stated, internally contradictory
- The cited source is scoped to E7: E7c `missing`: "The owner's actual I-ds contrast, task card + learned rule vs
  task card, was not run on any solver" (i.e. in E7's pilot).
- v3's main chain I-ds (parent = the card) ran exactly this contrast in its gates. D1r `evidence`: "All 7 I-ds rule
  arms: -0.107 to +0.005 on their check halves." D9c `confirmed_claims`: "I-ds SearchQA +0.000 / +0.004 / +0.015;
  LiveMath −0.022; SpreadsheetBench −0.044 (screen) / +0.027 (confirm); ALFWorld −0.140 [−0.254, −0.035]". E7c
  refuted #1: "in the s1 SearchQA screen, the parent and all 3 screened rules (s1-r1, s1-r2, s1-r4) have tag share
  1.000". The proposal itself cites the I-ds check-half numbers at L14 (S8).
- Correct statement: never run as a large (≥200 fresh items), pre-registered calibration arm — cal-1 (D9c refuted
  #1: "None of the 11 texts is 'TC + a rule'"), E7, E8 (E8c #4: "That arm was prepared but not run"), D9 lacked it,
  and D1's ~2.1M-token package-on-card pilot was not run (D1r `pilot`).

### R3. "No increment over a good instruction exists anywhere" (L22; S5) — upgrades "not established" to "absent"
- The cited ledger line says the opposite of "exists nowhere": results-and-lessons L139: "**在现有三个域、这个求解器与
  242题量级的留出集上，"从任务经验学习"相对"一段合理的初始指令"的增量目前没有任何一处被建立**；242题只能分辨约5–6个
  百分点以上的差，所以这是"未建立"，不是"已证明没有"。" Same line: "pass/fail−通用指令为+0.046、+0.029（一条区间下端
  +0.005、一条含0）".
- D9c refuted #1: "learned minus generic +4.6 [+0.5, +9.0] (gen17); Skill learned from empty minus generic +6.7
  [+2.5, +11.3] (fg17 ...) ... The ledger itself says '未建立，不是已证明没有' ... It does not support a 0-3 pt
  ceiling."
- What the evidence supports: not established anywhere; one history positive (gen17) did not replicate (gen19);
  against bzero on SearchQA (GLM-5.3, 975 items) the bound is tight, +0.1 [−1.6, +1.8] (project-status L156). This
  is the same over-reading the D9 critic refuted for D9's "0–3 points".

### R4. K3 / S55: "resends caused 5 of the card's 6–8 gains"; "No flips at ≥2 minutes" — refuted by E4c R2
- The proposal cites "E4c R5"; R5 is about the SpreadsheetBench card's mechanism on OfficeQA. The relevant item is
  E4c R2: "The 0/23 holds only for the SearchQA scaffold. SearchQA card arms flip MORE when lagged: 11/106 (10.4%)
  vs 6/94 (6.4%) back-to-back ... 2 of the 7 untagged SearchQA scaffold replies came 120 s or more after their twin
  ... In E4 the send gap is fully confounded with the launch period ... So this is a one-arm, one-benchmark
  association. Spacing sends is harmless, but it does not lower the 8-10% flip floor." The overnight report §6.5
  (L91) records the same: "“隔 2 分钟不翻转”站不住".
- What stands: E4c R1 — the card's SearchQA gain in E4 "sits on the 7 complete items where the scaffold gave an
  untagged reply". Spacing duplicates may stay as a harmless rule; its stated justification must go.

### R5. ST3: "Lenient scoring gives s1-r1 +0.068, against −0.026 officially" (L53; S21) — mislabelled and self-contradictory
- E6r `evidence`: "cand under em_rob +0.068, lenient +0.032, judge +0.020." +0.068 is format-robust exact match
  (em_rob), not "lenient". E6c R1: "under lenient, E-ds s1-r1 FAILS the screen round".
- em_rob ≈ the JSON-aware extraction that CH4 adopts: E7r H gives cand +0.0675 [0.030, 0.106] under it, and E7c
  `confirmed_claims`: "v3 E-ds s1-r1 really is damaged by format drift. JSON-aware it would net +12 to +14 items in
  both screen and confirm, so its C2 failure (-15/2) is plausibly an artifact." So the example shows the old scorer
  misreading JSON answers, not a lenient score rewarding a bad rule. ST3 may still stand on other E6 evidence
  (E6r: OfficeQA "Within 1% ... It rewards wrong values").

### R6. §1.5: "E-ds's s1-r1 lost 0.047 off its evidence items" (L39; S8) — rests on the JSON artefact
- D1r: "s1-r1: +0.266 on its 8 evidence items but -0.047 [-0.094, -0.003] on the other 186" (official scorer). Per
  E7c (quoted in R5) the off-evidence loss is plausibly the format artefact; under the proposal's own CH4 scorer
  the 200-item effect is +0.0675. It cannot be used as evidence about where rule effects land. The other half of
  §1.5 stands (D4c `missing` #1: card "+0.053 per item in scope vs +0.174 out of scope"; D4c refuted #3: I-ds harm
  "10 up / 21 down in scope ... post hoc, ... about 0.04 after Bonferroni").

### R7. S12: "Under containment scoring, every SearchQA effect vanishes, the card's included" (L19) — needs qualification
- Source E7c refuted #5 is real but small and scorer-specific: 98 pilot items, sub_em; it also says "(and F1 about
  +7)". Contrary evidence on 200 items: E10c `confirmed_claims`: "On real items ids-full keeps +0.061 [+0.026,
  +0.098] under lenient scoring (35 items up, 8 down)"; E10c R6: "about a third of the real effect is answer form";
  E6r: "ids-full's EM gain is 36% semantic (+0.034 of +0.093)". Correct: most (one-third to two-thirds) of the
  card's SearchQA effect is answer form; "every effect vanishes" holds only under containment on 98 items.

### R8. §1.2 "form breaks transfer" (L17, L21) generalised from whole cards on an empty scaffold
- E9c R3: "every measured harm comes from a whole task card, 4-7x a rule's length, added to an EMPTY scaffold ...
  Bleed of rule-sized text on a seeded parent is unmeasured." E4c R4: "the dissimilar cells use placements the
  protocol never makes". E4r `evidence`: "cal-1 four other cards in their own sections: +0.2 [-3.1,+3.6] (n=199)".
  The −20/−27/−9.5 numbers are right (E4c confirmed; E9c confirmed "L -9.46"); the generalisation to learned rules
  on the card parent is not measured. Also relevant to CH1's card gating: the only bleed measurement on SearchQA is
  ≈0; the OfficeQA +4.7 vs +13.5/+17.6 gap is confounded with regime (E9c `missing` #2, which the proposal notes).

### R9. CH6 "FinQA does [qualify]" (L89) — qualification rests on E3's own lenient scorer
- E3 report L183–184: "FinQA: strict = exactly one number, equal after rounding, with "%" present exactly when the
  gold has it; lenient = within 1% of gold, gold/100, gold x 100 or exe_ans." L188: content = lenient on the tag
  or a fallback. E3r `pilot`: "approximate (non-official) TAT-QA/FinQA scorers"; 80 items x 2 runs.
- E3c R4: the official script "only tests exe_res == exe_ans (prediction rounded to 5 decimals) ... parses "5%" as
  0.05." So the card's .787 "content score" forgives a 1% error and ×100/÷100, which the official metric does not.
  Whether FinQA meets "≥15% content failure" and "not dominated by surface form" (rounding precision is a form
  issue) under the official metric is unmeasured; E3r also lists 905 items per 5 points under its strict scorer vs
  142 at content level (E3c R2). The proposal's risk 5 and E0 pivot partly acknowledge this; CH6's "FinQA does"
  must read "FinQA may qualify; unverified under the official metric".

### R10. Cost anchors addressed to the owner (L178 risk 6; summary_cn L238; L151)
- "settles the question for 20–50M instead of a 1.16B chain": 1.16–1.17B is the v4 **cap** (overnight report L135
  "v4 总上限（11.6 亿还是 11.7 亿 token）"; L38). v3's **actual** ledger spend was 139,024,462 with "合计上限 4.3 亿"
  (results-and-lessons L142). The fair comparison is 20–55M vs ≥139M (a chain that accepts rules costs more).
- summary_cn "M1 约花 1,700–2,600 万 token" is receipts. E7c refuted #8: "cal-1's own receipts sum to 14.0M (17.6M
  charged), but its ledger settled 27.5M"; the owner was told cal-1 cost "2,748 万" (overnight L16, ledger basis).
  On the ledger basis M1 ≈ 35–55M (the proposal's own cap is 55M), i.e. 1.3–2x cal-1, not cheaper than it.
- "Whole-plan worst case ≈160M, close to v3's 139M" mixes M1's ledger cap with receipt-style estimates for M4,
  compared with v3's ledger figure. Restate on one basis.

### R11. Unsourced load-bearing assumptions (default refuted)
- "On fired items only (≈400 at share 0.4)" (L115) and "share 0.3" (L151): no source. The only measured
  code-computable condition fired on 14 of 97 judged items (D13r `pilot`: "It applies to 14 of 97 judged check-half
  items"), and it reads the reply. At share 0.14 the Hg rule "share × (A2−A0) ≥ +2" needs ≈+14 points on fired
  items.
- "The test can resolve about 1.9 points (all items)" (L125): scaling 142 items/5 points is arithmetic-correct but
  ignores the conjunctive rule (LB>0 AND LB vs placebo mean>0 AND point estimate ≥ +2). E1c R1 on the same
  structure: "a true effect of exactly 0.10 gives power of about 0.50". D1r: "+2 at 80% power, k = 2: 1,016 /
  1,637 items". Realistic 80%-power resolution at 1,000 items is ≈2.5–3 points (all) and >3 (fired).

### R12. Minor numeric/label errors
- S19/L28 "gated at 6.5–10.1%": E6c R2 gives v3 screen 9.0%, confirm 6.5%; 10.1% is cal-1 "16 h later". v3 gated
  at 6.5–9.0%.
- S22 "859,911 GLM tokens": E1r `cost_estimate`: "Pilot 2: 618,598 GLM. Pilot 3: 21,327 GLM + 29,867 deepseek.
  Pilot 3b: 46,284 GLM + 143,835 deepseek." GLM ≈ 686k; 859,911 is the total.
- S38 "v4 about 3 h": project-status L179 prices the **full** v4 from the existing G1–G6.v2 plans, not "v4-min"
  plus new components (see feasibility F1).
- L13 omits that 75.8% is the pre-registered inconclusive band (cal-1 L148–150).
- CH1 "Code conditions need no judge" generalises from one condition (D13c `confirmed_claims`: "agree 97/97 with a
  mechanical check (word overlap between final answer and question)"), which is reply-reading, not input-only, and
  whose rule nets "+2 / -3" when applied literally (D13c refuted #5).

### R13. Reliance on an unreviewed direction
- K4, CH2, S8–S10, S34 all rest on D1, which had no adversarial review (overnight report L74: "D1 | 高 | 未审查").
  D1's pilot validated only that a +16-point card is accepted and duplicates/placebos rejected (D1r `pilot`:
  "It did not test a learned rule package on the good-instruction parent").

## 3. Confirmed claims (checked against the cited field or line)

| # | Claim | Verified at |
|---|---|---|
| S1–S3 | +0.0938 [0.0505, 0.137]; bridges +0.0037/−0.030/−0.026; C1 75.8%, 0/0/7.7%, null 0% | cal1-registration L137–139 |
| S4 | ledger 27,481,897 for 8,800 cells; receipts 14.0M | cal1 L130; E7c refuted #8 |
| S6 | 0 of 49 accepted; 139,024,462 deepseek tokens | RL L142 (24 + 25 proposals) |
| S7 | +0.053 in scope vs +0.174 out; I-ds 10 up / 21 down in scope, post hoc | D4c missing #1, refuted #3 |
| S8–S10, S34 | I-ds −0.107…+0.005; card +0.162 accepted, placebos rejected; LB95>0 & mean ≥0.02; certifiable 0.042/0.056/0.103/0.122/0.153; control:2 accepted | D1r evidence, pilot, design |
| S11 | rule-vs-card sd 0.243, MDE 4.8 at 200 items | E7c refuted #4 |
| S13 | ≈73% acceptable (single rater), ≈6 points substantive; LiveMath non-meta 62/110 | D9c refuted #4, missing |
| S15, S32 | OfficeQA −26.7 / −20.0; meta option key in 129/129 | E4c confirmed; D7, E4c confirmed |
| S16 | generated panel scaffold .891; −9.46 harm missed | E9c confirmed ("P .891", "L -9.46 ... vetoed" on R only) |
| S17 | terse/verbose regimes alternate | E8c refuted #1 |
| S18, S23 | +20.3 across windows on 74 items; +4.7 vs +13.5/+17.6 unresolved; sim(SearchQA) = {OfficeQA} | E9c R4, missing #2; V6 L71 |
| S20 | 59/600 unused | E5c missing #7 |
| S24 | v4 keeps C1–C4'; fresh-batch acceptance out of scope; P1 3-vote judge | spec.md L129–138, L177 |
| S25, S27, S29, S31 | V4 0 promotions; 30/6 vs 11/12, 9/9; code anchor held; CURE [lit] | E10c R7, confirmed, R3 |
| S26 | V16 0 new natural detections | current-workflow L388 |
| S33, S35 | method flow fixed; one consented test read | project-status L116, L118 |
| S36 | 97/97 judge vs code (reply overlap) | D13c confirmed |
| S37 | pending decision (d) on JSON/interleave/spacing | project-status L344 |
| S39–S43, S54 | FinQA 6,251; TAT-QA 13,251; 1.1–1.9k/cell; scorer 1–2 days; 142 items/5 pts (content); official = numbers only; % rule invented; expert − card 0.0; feasibility low; seal tests; targets out of acceptance; OfficeQA gate covers FinQA | E3r evidence/cost; E3c R2, R4, R9, M1, M3, M10 |
| S44 | BCB/KOR replaced 10/13 | current-workflow L56 |
| S45 | GLM: E8 194,566; D13 175,147; E6 1,324,475 | E8r cost, D13r pilot, E6r cost |
| S46 | LiveMath I-ds cell 3,969 tokens | D6c refuted #5 |
| S47 | ALFWorld 105.7k per I-ds episode | D14/report.md L87 |
| S49 | pools 600/74/283/120/57; tests 400/172/125/279/134 (SpreadsheetBench: qualified subsets) | V6 L84–88 |
| S50 | OfficeQA test MDE 6.6–7.7 | D5c missing #4 |
| S51 | mimic-train generation = fake validation set; evaluation must evolve | project-status L396, L403 |
| S52 | no held-out validation partition | V6 L124 |
| S53 | learned transfer cells identically 0 | E2c R4 |
| L105 | ≈99 non-meta LiveMath items outside v3's draw (154 − 55), card fails 48/110 | D7 report L96 ("100 items (45 meta, 55 non-meta)"), L307 (D7 pilot used items inside the draw); D9c missing |
| M1 cells | 11,200 cells = 600 + 9,000 + 1,600 | arithmetic checks |
| Fallback | 1,050 × 3,969 ≈ 4.2M | arithmetic checks |

## 4. Feasibility issues (evidence-anchored)

- F1. E0 effort is understated. "About 3 h" (project-status L179) is for implementing the full v4 from the six
  revised plans; overnight report L39: "G4 先做，因为 G1/G2/G3 要用它的投票和重问助手". v4-min drops P4, yet spec B4
  ("B6/P4 format, 3 votes") and B6 ("3 votes (P4)") depend on it. B15's premise was refuted (overnight L38:
  "规格里“RESEARCH_MAX_ROUNDS = 3 从不生效”这个前提是错的"). B2/B10/B14/B16 fix per-rule chain machinery that ST1/ST6
  stop. New, unplanned components: predicate compiler, gated renderer, admission checks, cross-pool item ledger,
  scorer version, and a FinQA port, which E3c M6 says is a new registration, "far more than 1-2 days".
- F2. M4 "each dissimilar bench must drop by at most 3 points" cannot be certified on 125/279/134-item tests
  (D5c missing #4: MDE "10-11 on LiveMath, 7-7.7 on SpreadsheetBench and 9-10 on ALFWorld"); D8's margins were
  6/10/9/15/25 points (synthesis L76). Only a descriptive point-estimate check or "never fires" is possible.
- F3. M3's decision rule ("at least one check admitted in 2 of 3 rounds") does not exclude gold-derived checks,
  which the proposal's own risk 7 says are trivial; seeded defect types are designer-chosen, so admission can be
  circular. It is a fixture result and must not be labelled co-evolution evidence (AGENTS.md: "an accepted verifier
  is not an accepted Skill").
- F4. The 1,000-item extension after seeing a point estimate (L127) is an interim look; without a pre-registered
  alpha split the one-sided 97.5% level is not kept (D8 recommended explicit futility/Holm control).
- F5. The A0d duplicate arm has no stated use; E2c R6: "A byte-identical canary has an expected difference of
  exactly 0 under any exchangeable dispatch. It therefore cannot detect the text-dependent drift".
- F6. K6 "official binary metrics" vs CH4's new scorer: E7c `missing`: "Any scorer change must be applied to every
  arm and baseline, and it departs from comparability with native SearchQA exact match."
- F7. Cost basis: state everything on the ledger basis (≈2x receipts in cal-1) before comparing with v3's 139M.

## 5. What survives

- Stopping per-rule C1 chains (incl. a v4 chain): supported (cal-1 inconclusive even for +9; D8 per-step power
  0.19–0.26 for +0.3…+3-point effects; v3 0/49), but the reason is "per-rule gate underpowered, and no rule has
  shown a gain over the card", not "rule-sized texts have ≈0 effect".
- One frozen version, one interleaved round on never-proposed items, card + ≥2 length-matched placebos,
  placebo-relative acceptance: supported by D1 (unreviewed) and D8, E2c, E4c R7; spacing duplicates is harmless.
- No generated items as gates/transfer evidence until certified: supported (E9, E10, E1c R6, ledger 10/15–16).
- No target-bench pools as in-loop guards: supported (E9c R1, E3c M10).
- Verifier as executable checks with ground-truth fitness, never solver gains: a reasonable design hypothesis
  (E1c missing #4, E10c "code anchor held", DecoEvo/CURE [lit]); untested.
- FinQA as source: a candidate only, low prior (E3c: expert − card 0.0, feasibility low), unverified official metric.
- Gating by input predicates: an untested hypothesis (D4c missing #2) with direct counter-evidence that real
  effects land outside task-feature conditions (+0.053 vs +0.174); M1's A1-vs-A2 contrast is the right test.
- v4 = bug fixes only: survives in spirit; the "v4-min" composition needs re-planning (F1).

## 6. corrections_cn (for the synthesizer; plain Chinese)

1. 诊断第 1 条要改写。原文说"规则大小的文字几乎不动分数、C1 门几乎不放行，所以进化单位太小、量尺分辨不出"，这个读法不成立。校准实验 cal-1（11 种文字 × 200 道 SearchQA 训练题 × 每题 4 次）里，三段"规则大小"的桥接文字按现行评分是 +0.004、−0.030、−0.026；但 cal-1 登记文件自己的结论是"桥接文字本身没有可测效果，所以根本没有规则大小的真实效果可用来标定 C1 门"（C1 门＝验收单条规则的第一道检验）。没有效果的文字过不了门，是门判对了，不是门看不见。评分器改成也认 JSON 格式的答案后（E7 方向的诊断性重算），v3 次链的那条规则 cand 是 +6.75 分 [3.0, 10.6]，另一段桥接文字 +3.1 分 [0.3, 6.1]；v3 次链 E-ds（从空白模板出发的那条链）的规则 s1-r2 在 99 道没见过的题上 +8.1 分。所以规则大小的文字对空白模板是测得出效果的；测不出的是"在任务卡之上再加规则"的增益。瓶颈更像是"任务卡已经说过这些、任务卡之上没有被证实的余量"，不只是"单位太小"。仍然成立的部分：逐条检验的题太少（6–11 道），连 +9 分的任务卡也只有 75.8% 的通过率，落在事先定好的"无法下结论"区间（50–80%）。
2. "任务卡加学到的规则 对比 任务卡，从来没跑过"这句话不对。v3 主链 I-ds（从任务卡出发的那条链）在门槛检验里比的正是这个：D1 方向回放 v3 记录，7 条 I-ds 规则在没见过的检查题上是 −0.107 到 +0.005；D9 方向的审查员重算：SearchQA +0.000、+0.004、+0.015，LiveMath −0.022，SpreadsheetBench −0.044 和 +0.027，ALFWorld −0.140 [−0.254, −0.035]（显著变差）。提案自己第 1 条诊断就引用了这组数。正确说法：这种对比从没在 200 道以上的新题上、事先登记地跑过（cal-1、E7、E8、D9 都没有这一组，D1 准备好的约 210 万 token 的试跑也没跑）。
3. "在好指令之上的增量哪里都不存在"要改成"哪里都没有建立"。账本 10/12 条原话是："这是'未建立'，不是'已证明没有'"。同一条记录里，一条历史（gen17）学到的 Skill 比三行通用指令高 4.6 分，区间下端 +0.5；另一条历史（gen19）+2.9 分，区间含 0，没有复现。对照任务卡式的零样本指令 bzero：SearchQA 975 道题上再学一步是 +0.1 分 [−1.6, +1.8]（做题模型 GLM-5.3），说明在那里即使有增益也很小。
4. "两次请求隔 2 分钟以上就不翻转"和"任务卡 6–8 道增益里有 5 道是重发造成的"，已被 E4 方向的反方审查推翻（审查第 R2 条；提案引的 R5 讲的是另一件事）：0/23 不翻转只在"SearchQA 加空白模板"这一组成立；带任务卡的组隔开发送反而翻转更多（10.4% 对 6.4%）；7 次没写答案标签的回答里有 2 次是隔了 120 秒以上才发的；而且发送间隔和开跑时段完全重合，分不清原因。可以保留"重复请求隔开发送"这条（没有坏处），但不能写成"它消除了翻转"或"增益是它造成的"；同一文字重跑约 8–10% 的题会翻转，这个噪声底不变。
5. 停用清单第 3 条（不用宽松打分当门槛）的例子要换。+0.068 不是"宽松打分"，而是"格式稳健的精确匹配"；真正的宽松打分是 +0.032，而且在宽松打分下这条规则初筛就过不了。更要紧的是，提案自己在改动第 4 条里要换成"也认 JSON 答案"的评分器，按它算这条规则正好是 +0.0675 [0.030, 0.106]。所以这个例子说明的是"旧评分器读不出 JSON 答案"，不是"宽松打分会放过坏规则"。若要保留这条停用理由，请改用 E6 方向的其他证据，例如 OfficeQA 上"误差 1% 以内算对"会把查错行的数也算对。
6. 诊断第 5 条里"E-ds 的规则 s1-r1 在证据题之外掉 0.047"不能当作"规则效果落在哪里"的证据。E7 方向的审查员查了原始记录：这条规则受 JSON 格式问题影响，按也认 JSON 的评分，它在 v3 的初筛和复核里都净多对 12–14 道题，当初"伤了其余题"很可能是格式假象。同一条诊断里"任务卡的效果在适用条件内 +0.053、条件外 +0.174"和"I-ds 规则的伤害集中在适用题（10 好 21 差，事后分析）"这两点仍然成立。
7. "改用包含式评分后，SearchQA 上所有效果都消失，包括任务卡"只在 E7 的 98 道试跑题、最宽松的"互相包含就算对"判法下成立。E10 方向的审查员在 cal-1 的 200 道题上用"认别名的宽松判法"重算，任务卡仍有 +6.1 分 [+2.6, +9.8]（35 题变好、8 题变差），约三分之一是答案写法；E6 方向用 GLM 判卷，认为任务卡 9.3 分里约 3.4 分是实质内容。正确说法：任务卡在 SearchQA 上的效果大部分（约三分之一到三分之二）来自答案写法，不是全部。
8. "答案格式的文字会让别的题库掉分"这一条，证据都是整张任务卡（约 1,800–2,900 字符）加在空白模板上测出来的（E9 审查第 R3 条；E4 里很多"不相似"格子的摆放方式，真实流程不会出现）。学到的规则（不超过 600 字符）加在任务卡上会不会渗到别的题库，没有测过。cal-1 里其余四张卡放在各自分区，对 SearchQA 的影响是 +0.2 分 [−3.1, +3.6]，没有看到渗透。
9. "FinQA（财报计算题库）符合条件"目前只是纸面上的。任务卡 .787 的"内容得分"是 E3 方向自己写的宽松评分：数值误差 1% 以内、或者差 100 倍（百分数和小数混用）都算对，而且只测了 80 题 × 2 次。FinQA 官方评分程序按数值比较、保留 5 位小数，不给这些宽容。在官方判法下任务卡的失败率是多少、分数是否被"保留几位小数"这类写法主导，都还没有测过。E3 的审查员把可行性定为"低"，并指出在 FinQA 上手写专家技能比任务卡是 0.0。
10. 给您的花费数字要统一成"账本口径"。M1（关键试验）"约 1,700–2,600 万 token"是模型回答本身的用量；cal-1 的经验是账本记账约为它的 2 倍（回答用了 1,400 万，账本记了 2,748 万），所以按账本约 3,500–5,500 万，大约是 cal-1 的 1.3–2 倍，这也是提案自己把上限设成 5,500 万的原因。另外"只花 2,000–5,000 万，而不是一条 11.6 亿的链"这个比较不对：11.6–11.7 亿是第 4 版协议 v4 的预算上限，不是实际花费；第 3 版 v3 整次运行实际花了 1.39 亿（账本），如果真收下了规则还会更贵。"整个计划最坏约 1.6 亿、接近 v3 的 1.39 亿"混用了账本上限和回答用量，应换成同一口径再比较。
11. M1 的检测力说高了。它的通过规则要求三条同时满足：提升的下界大于 0、比两段安慰剂文字的平均也大于 0、点估计至少 +2 分。真实提升正好 2 分时，光"点估计 ≥ 2 分"这一条就只有约一半机会满足（E1 的审查员对同样的两段式规则算出的把握约 0.5）。按 D1 实测的噪声，每题跑 2 次、要有八成把握认出 +2 分，需要 1,016–1,637 道题。所以 1,000 道题能稳定认出的大约是 2.5–3 分，而不是 1.9 分。"适用题占 40%"没有来源：目前唯一一条能用程序判断的条件只命中 97 道题里的 14 道（约 14%），而且它要读模型的回答；如果只有 14%，"门控规则包"要在适用题上高出约 14 分才能过。
12. 第一周准备工作 E0 的工作量说低了。"约 3 小时代理工作"是按已经写好的完整 v4 方案估的；提案的"v4 精简版"去掉了三票表决的公共助手（规格里叫 P4），但规格里的修复 B4、B6 都要用它，修订稿里 G1–G3 三组也依赖 G4 组的投票助手；修复 B15 的前提已被 G6 组的审查证明是错的；另外还要新写"适用条件的程序化判断"、"只在适用题上加规则"的渲染、准入检查、跨题库的题目台账，以及完整的 FinQA 接入（E3 的审查员指出：接入一个新基准等于重新登记一版协议，远不止 1–2 天）。应如实写成"需要重新出方案，工作量尚未估算"。
13. 第 4 步"每个不相似的题库最多掉 3 分"在现有测试集上测不出来：测试集能分辨的最小差别约为 LiveMath 10–11 分、SpreadsheetBench 7–7.7 分、ALFWorld 9–10 分（D5 审查）；D8 方向建议的"不伤害"容差是 6 到 25 分。只能写成"点估计不低于 −3 分（仅作描述）"，或者"规则在这些题库上从不触发"。
14. 验证端试验 M3 的判定"至少两轮各收下一条检查就算验证端在进化"要加限制。提案自己承认"用标准答案直接推出的检查是可直接计算的，不算进化"，但判定规则没有排除这类检查；而且埋进去的错误类型是我们自己设计的，检查程序可能只是把它们认回来。应写明：只有不看标准答案的检查（例如判断一道生成题是否有效、一条规则是否和目标题库的答案格式冲突）被收下，才算验证端进化；并注明这是在人工构造的测试集上得到的结果，不是方法有效的证据。
15. 其他需要注明或改正的地方：①提案大量依靠 D1 方向（整版验收）的数字和规程（K4、CH2 和 S8–S10、S34），而 D1 是少数没有经过反方审查的方向之一（夜间汇报 6.5 表写着"未审查"），D1 的试跑也只验证了"+16 分的任务卡会被收下、重复文本和无关文字会被拒"，没有测学到的规则包。②v3 收集失败题时，没写答案标签的回答占 1.0%；门槛的两轮是 9.0% 和 6.5%；10.1% 是 16 小时后的 cal-1，不是 v3 的门槛。③E1 方向的 859,911 token 里约 17 万是 deepseek（做题模型），GLM 约 69 万。④引用 cal-1 的 75.8% 时应说明它落在事先登记的"无法下结论"区间。
