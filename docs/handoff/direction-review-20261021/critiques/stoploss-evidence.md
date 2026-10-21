# Evidence-fidelity critique: the stop-loss / devil's-advocate proposal

Critic: adversarial evidence-fidelity critic. Date: 2026-10-21.
Proposal under review: `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/direction/proposals/stoploss.md` (126 lines).

Ground rules followed: read-only, no model calls, no SSH, no test pool opened. I traced every row of the claims table (#1–#39) and every number in sections 1–5 to the cited file, at the cited line or JSON field. Wherever the proposal's reading differs from its source, the source text is quoted below.

Abbreviations:
- RL = `docs/results-and-lessons.md`.
- FS = `docs/handoff/feasibility-20261021/`.
- "l." = line number.

The only computation I did myself is the decision-rule simulation in section C, F2. It is a normal approximation with its assumptions stated there; there are no other new numbers.

## Verdict: needs_revision

**What holds.** Most numbers are transcribed correctly:
- 30 of the 39 claims-table rows check out as written.
- The core stop list survives on independent evidence.

**What does not hold.** The defects are in what the numbers are said to show:
- Several results carry the labels "real-item", "fresh-item", "learned" or "transfer", but are actually:
  - generated-item results;
  - results on reused items;
  - hand-written-card effects;
  - GLM-only findings.
- The v4 cost argument reads a programme-level GLM budget ceiling as the cost of running v4.
- The ALFWorld reading contradicts the D14 report it cites. D14 is unfinished and unreviewed.
- Exp 1 is the "decisive" experiment, and it has three defects:
  - Its power uses a 2-run standard deviation, but the design has 1 run per item.
  - Its decision rule turns a true +3-point effect into "NULL" about 40% of the time.
  - It runs only where headroom is smallest, so a NULL cannot support the proposed headline "experience adds nothing measurable on top of a task card".

## A. Refuted or misframed claims (source text quoted)

**R1. "Three solvers, real items: −1.8 to +0.6, n.s. [R; 5]"** (section 1.1; claims #5)
- RL l.195: "SearchQA（上一条已给合并数字）：三机都在0.90–0.94天花板附近，learned−bzero全部n.s.或负（范围−1.8到+0.6 pp）".
- The entry referred to as "上一条", RL l.197: "SearchQA生成题168题：空0.795、指令0.914、qa_s1 0.917、qa_v9 0.899（n.s.）".
- RL l.182: "OfficeQA 198题＝124生成＋50 train＋24 val，SearchQA 168题".
- So the −1.8…+0.6 range comes from 168 **generated** SearchQA items, at the ceiling.
- The real-item part is OfficeQA only. RL l.192: "三机真题train上learned−bzero全部p>0.1、方向不一致、点估计落在±2题/50内".
- Those OfficeQA items were reused: "OfficeQA的真题train/val是前期学习与门控曾看过的分区" (RL l.195, limitation b).
- The "learned" texts were gate-rejected candidates: "本条用的`learned`候选是10/14 OfficeQA生成题门阶段被**拒**的候选" (limitation c).

**R2. "On 750 fresh items an earlier +2.7 did not replicate [M; 4]"**, listed as evidence about learned text on top of a good instruction (section 1.1; #4)
- RL l.220: "v11一步、只给对/错、不经选择、父为空 … 主对比`lp`−`le` +0.004 … 首轮探索里的+2.7个点（四个旧种子、250题）没有复现".
- The +2.7 was a learner-prompt contrast (lp − le). Both arms learned from an **empty** parent.
- This experiment shows that one learning step from empty reaches the zero-shot instruction (lp − bzero +0.001, le − bzero −0.003). It says nothing about learning on top of an instruction.

**R3. "Large effects are measured reliably"** (section 1.1)
- E6 critic R3: "the v3 single-arm train units (I-ds vs E-ds, same 200 items) … the same contrast is only +0.0325 [-0.004, +0.069], 20/11 items, not significant. The cal-1 +0.093 arises largely because the interleaved empty scaffold loses its answer tag".
- The same card-vs-scaffold contrast has been measured four times:

  | measurement | result |
  |---|---|
  | v3 single-arm training | +3.25, not significant |
  | cal-1 | +9.4 |
  | E5, 180 fresh items | +8.9 |
  | D1, 130 fresh items (unreviewed) | +16.2 |

- E10 critic R6: "Under alias-lenient scoring the real ids-full effect falls from +0.0925 to +0.061".
- Correct reading:
  - The direction is detected in interleaved sessions.
  - The size ranges from 3 to 16 points, depending on dispatch mode, session and scorer.
  - Much of the effect is answer form.
  - So it is not a clean calibration showing that the instrument can see content.

**R4. "every measured SearchQA Skill effect is answer surface form [A; 10]"** (section 1.2)
- This holds only under E7 critic #5's sub_em scorer ("gold contained in the answer, or the reverse").
- E10 critic, confirmed_claims: "On real items ids-full keeps +0.061 [+0.026, +0.098] under lenient scoring (35 items up, 8 down)". R6: "about a third of the real effect is answer form".
- The two critics disagree. Depending on the lenient scorer, the surface-form share is anywhere from about one third to all of the effect.

**R5. "Learned conventions transfer negatively: other benches' Skills cost SearchQA 3–8 points, the LiveMath card costs OfficeQA 9.5, and on test the instruction (66.7) ≥ SkillOpt (66.0) > GEPA (63.5)"** (section 1.2; #15–16; repeated in Objective 2)

None of the three cited supports shows a learned convention transferring negatively on the deployment solver:

- **(a) The 3–8-point harm is GLM-only.**
  - `docs/project-status.md` section 0: "跨数据集互换 Skill 在 deepseek 上不害，GLM-5.3 上的"有害"没有复现，属于模型族差异".
  - RL l.181 says the same.
- **(b) The −9.46 is a whole hand-written card, and the harm is regime-dependent.**
  - E9 critic R3: "every measured harm comes from a whole task card, 4-7x a rule's length, added to an EMPTY scaffold … Bleed of rule-sized text on a seeded parent is unmeasured".
  - E9 critic R4: "E9 window minus v3 window = +20.3 points … Veto decisions are therefore regime-conditional".
- **(c) The v1 test is not a transfer measurement.**
  - It ran on GLM.
  - RL l.173 gives "SkillOpt − GEPA +2.4 [−0.4, +5.2]", so the ">" is not established.

The nearest real support is a different result. `docs/handoff/coevo5-v1-results-20261019.md` l.12: "学来的 Skill 让 SpreadsheetBench 下降 2–8 点（只有 GEPA-glm 的区间整个在 0 以下）". That is GLM, with one significant cell.

**R6. ALFWorld's headroom read as "not learnable content", "solver-capability failures" (Stop 2) and "only as no-drop controls" (Keep 6)**
- The numbers are right:
  - D14 report l.71: "Every failure is a 50-step timeout".
  - l.90–91: "E-glm 102/114 (89.5%) … the weak, non-reasoning solver is the bottleneck".
- But D14 is unfinished and unreviewed:
  - overnight report l.68: "报告写到一半被停止 … 结果表未填";
  - l.87: "未审查";
  - `report.md` still has seven placeholders, including `[[BOTTOM_LINE]]` and `[[ALF_TABLE]]`.
- D14 itself argues the opposite of "not learnable":
  - l.153: "the failures are not a memory problem that a sentence can fix ('never revisit'), but a search-order problem".
  - l.218: "ALFWorld: yes, in principle -- but not with what v3 proposed, and not through today's unguarded loop".
  - l.226: "keep it in the text-skill programme, but change the protocol".
  - l.69: the card "is the only text that measurably moved ALFWorld in v3" (+0.105 [+0.026, +0.184]).
- D3 critic #5: "About half of the looping is a policy failure that a text rule … could target".
- The ALFWorld decision must wait for D14's pilot tables. The raw files are on disk, so filling them costs nothing.

**R7. "For GLM the 975-item result bounds it [the true increment over a good card] near 2 points"** (section 1.3; #3)
- The numbers are correct. The scope is not.
- RL l.222 describes the learner: "都是v11一步、只给对/错、不经选择".
- It limits its own conclusion: "这是这两份初始文本、这一流程、这一数据集上的结论，不是该数据集的上限".
- Its registered verdict: "缺失条件下未分辨".
- bzero is GLM's zero-shot instruction, not the deepseek five-section card.
- The result bounds one learner, not the learnable increment in general.

**R8. Exp 3: "learned-over-card ≈0 (fresh items, two solvers)"**
- On deepseek, every learned-on-card number comes from reused items:
  - D9 evidence E: "+0.000 [−0.036, +0.036], +0.004 [−0.019, +0.026], +0.015 [−0.011, +0.044]" on v3 focal panels that the proposal itself calls optimistic;
  - D1's replay of archived v3 cells.
- The fresh deepseek runs test something else:
  - D1's 130 items and E5-P1's 180 items test card vs scaffold, or a learned rule on the **scaffold** (E5: "cand -8.61 [-14.17, -3.06]").
  - E5 critic #6: "It tests neither cross-benchmark generalisation …, nor a learned rule, nor a rule on top of a good instruction".
- The upper confidence bounds reach +2.6 to +4.4 points.
- Only GLM, on its 975 fresh items, gives a fresh-item learned-on-instruction reading (≈0 ± 2).

**R9. "Running it is the cost: caps of 11.6–11.7亿 tokens" (Stop 1) and "≈4% of v4's cap" (Change 3)**
- 11.6亿 is the programme-level GLM-5.3 ceiling, not the cost of a v4 run.
- `docs/handoff/v4-plans-20261021/G4.v2.md` l.1842–1846: "OVERALL_CEILING: v3's 1,170M less v3's actual GLM-5.3 spend … = 1,160M; the sum of the chain caps exceeds it, so it binds. Expected, not caps: roughly 3-6M of roles per SearchQA step … v3's ten formal steps used 7.8M in all."
- l.2051–2052: "Expected usage, not a cap: 2-6M of roles per step".
- Each deepseek learning chain is capped at 121M (l.2047–2049).
- Precedent: v3 spent "deepseek 139,024,462 … 合计上限 4.3 亿" (RL l.142).
- v4 should be stopped on the evidence (unchanged thresholds, rule-sized effects below what the gate can see), not on an 11.6亿 "cost".

**R10. Stop 7, "Variants measured non-positive"**

These stops can stand, but the label is wrong. They are "not shown to help" or "tested defectively", not "measured non-positive".

| variant | what the sources show |
|---|---|
| Switching solvers (cand vs card, deepseek −14.8) | The −14.8 is the strict scorer failing JSON-wrapped answers. E7 critic: "cand minus ids-full -0.010" under JSON-aware scoring. E7 critic also found flash the quieter instrument: "flash: sd 0.168 … format-fixed deepseek: sd 0.243". |
| D3 tracker | Positive but confounded. D3 critic #4: "T-glm 26/42 vs C 16/42: 11 vs 1, p=0.0063, +0.238 [0.092, 0.385]" in the canonicalising loop. It failed only under frozen verbatim parsing (#2). Claims row #39 is accurate; the heading is not. |
| Distilled rules replacing the card ("a tie") | A tie on SearchQA only. E8 verdict_cn: "D 比 I 低 10.4 点［−22.6，+1.7］：统计上不显著，但在两半题目上方向一致" (OfficeQA). |
| Case memory −1 [−6, +4] | D2 critic missing #1–2: "No placebo or shuffled-memory arm … The pilot tested a bank the project's own leakage layer would reject". |

**R11. "Drift/format artefacts of 5–10 points" (Risks), "≥2-min duplicate spacing" (Keep 1); #30 cites overnight report l.49**
- l.49 is the synthesis as written before the critics reviewed it.
- D5 critic notes_cn: "只看答案都写进标签的题，时段差只剩0.4分，对照扣分只剩0.5分".
- E6 critic R2: "the anomaly is the single-arm train unit versus every interleaved round, not 16 hours of drift".
- E4 critic R2: "SearchQA card arms flip MORE when lagged: 11/106 (10.4%) vs 6/94 (6.4%) back-to-back".
- What survives:
  - On SearchQA: the JSON loss of scaffold-type arms, plus the single-arm vs interleaved difference.
  - Separately: the OfficeQA 22–24-point session swing (D12, D11).
- Spacing requests 2 minutes apart is harmless, but it does not reduce noise.

**R12. "OfficeQA 172, the LiveMath evaluation block and SearchQA C/D stay sealed" (Exp 3); "keep the sealed holdouts unread"** (cites project-status l.117)
- The "未读" sentence is at l.118 (the proposal cites l.117). It is superseded by l.119: "10/16 15:03 负责人同意：五 bench 主实验每一步在各 bench 的测试集上评测（含 OfficeQA 172、LiveMath 125）".
- The v1 test was opened on 10/19. `coevo5-v1-results-20261019.md` l.75–78 shows OfficeQA "29.1（50/172）… 49.4（85/172）" and LiveMath "40.0（50/125）".
- Claims row #16 itself says the v1 test was "opened with consent".
- What is actually unread:
  - SearchQA blocks C and D;
  - v3's step-0 test scores, which were computed but not opened.

**R13. "SpreadsheetBench: the card itself has no effect [A; 13]"**
- True for deepseek on training items (D14 l.95–96).
- Not true on GLM:
  - D14 l.102–103: "I-glm 65/91 (paired 23 vs 4, p = 0.0003; partly a v1 layout effect)";
  - v1 test: "SpreadsheetBench 指令 +9.2 [+2.6, +16.0]" (RL l.173).
- The effect depends on the solver.

**R14. Objective 1 "deprioritized" and Keep 7 "D10's measurement-paper framing" are presented as settled**
- D10 critic R13: "the measurement-paper framing serves neither of the owner's two purposes (co-evolution; generalisation). 'Adopt now' should be the owner's decision."
- Objective 1 is the owner's own wording (brief): "1. 协同进化，skill进化，验证端coding rubric进化".
- The claim "On exact-reference benches the verifier reduces to item generation" is overstated:
  - E1 critic R10: "Untested: SpreadsheetBench … codes D1 no workbook, D2 empty/wrong range and D3 hardcoded can be checked without the reference … a content check that transferred: binary_op_arithmetic".
  - E5 critic #2: "untestable with 74 real items, not 'invalid'".
  - E10 critic R7: CURE rewards the tester for "reward precision".
- This must be presented as a recommendation for the owner to decide. It should also list the cheapest verifier-side work that remains (E10 critic missing #3–4):
  - outcome-blind validity audits;
  - a false-positive test using null-effect arms.

**Minor**
- m1. Row #3: the missing-result bound is [−0.031, +0.032], not ±0.032.
- m2. Exp 0 fallback: "400 × 2 runs, MDE ≈3.1". With the proposal's own SD of 0.243, 2.8 × 0.243 / √400 = 3.4.
- m3. The test MDEs "3.7 / 6.3 / 7.3 / 6.5 / 8.0" (E5 critic #4) need three caveats:
  - They are for 2 runs per item, with scaffold-based SDs.
  - The registered tests use 1 run. D5 critic missing #4: "About 4-5 points on SearchQA, 6.6-7.7 on OfficeQA, 10-11 on LiveMath, 7-7.7 on SpreadsheetBench and 9-10 on ALFWorld".
  - Two factors work the other way:
    - Contrasts on a card parent need about half the items (E5 critic #5: "MDE 4.9 points at 200 items (E5: 6.8)").
    - Evaluation-only benches can use larger public item sets (E4 critic R6: "ALFWorld has 3,553 training games and 274 evaluation games. It is limited by cost, not by items").
- m4. "≈73% of card failures are strictness" is one rater's reading. D9 critic missing: there is no two-rater or LLM audit.
- m5. v3's "0 rules accepted" is tagged [M]. It is a real-run, training-side gate outcome, so [R] is the right tag. Under JSON-aware rescoring the E-ds s1-r1 rule would plausibly have passed: E7 critic #1, "screen goes from +0.75 to +13.75 items of 200, confirm from -2.50 to +12.25". But that rule "restates the task card", and "At most 1-2 of the 7 screened SearchQA rules are affected", so the I-ds null stands. This supports the proposal's thesis and deserves one sentence.
- m6. Stop 6 (the LiveMath meta option) reverses v4 spec section 3, item C1 (l.169–174), which provisionally allows "task_structure" rules. The proposal should say it is reversing a pending owner decision.
- m7. D1, D12 and D14 are unreviewed (overnight report l.74, l.85, l.87). Flag every figure taken from them:
  - +16.2;
  - card placebos 0.000 / −0.023;
  - 880 cells/h;
  - 16.4M per ALFWorld round;
  - 50.8% → 26.7%;
  - 122/122.
- m8. Units: v3's 139M is an official-ledger figure, while the proposal budgets in real tokens. For card-sized cells the ledger is close to receipts (v3 4,088 per cell vs E5 3,995). So "≈⅓ of v3" is roughly right, but the unit should be named. cal-1's 2× gap (E7 critic #8: "receipts sum to 14.0M (17.6M charged), but its ledger settled 27.5M") comes mostly from scaffold-sized cells.

## B. Confirmed claims (by claims-table row)

- **#1** cal-1 (`cal1-registration-20261020.md` l.129–140):
  - 8,800 cells; ledger 27,481,897;
  - card vs scaffold +0.0938 [0.0505, 0.137], 48 up / 13 down / 139 tie;
  - C1 pass rate 75.8% at n = 11; 47.9% / 99.0% at n = 6 / 20; null 0%.
- **#2**
  - D1 pilot: +0.162 [+0.104, +0.223] on 130 never-used items; card placebos 0.000 / −0.023 (unreviewed).
  - E5-P1: +8.89 [4.44, 13.06] on 180 never-used items.
- **#3** 975-item point estimates and intervals (RL l.222).
- **#6** v3: 0 accepted; deepseek 139,024,462; GLM 7,804,250 (RL l.142).
- **#7**
  - D9 evidence E: +0.000 / +0.004 / +0.015.
  - D1: "All 7 I-ds rule arms: -0.107 to +0.005"; 880 cells/h; ALFWorld round ≈16.4M.
- **#8** RL l.137: +0.046 on a reused development pool; RL l.139: nothing established.
- **#9** D9 critic: ≈73% (single rater); ≈6 points substantive; no card+rule arm; defective proposer.
- **#10**
  - E7 critic: SD 0.243 (from 2-run item means), card+rule never run.
  - E7 result: cand vs card −0.5 / −3.1 / −14.8 (strict scorer).
  - I-ds 100% tagged.
- **#11** D2 verdict: case memory −1 [−6, +4]; inconsistent answer style.
- **#12**
  - LiveMath meta option in 129/283 items, always correct; 58/68 dead failures.
  - Benchmark paper: "the correct option is replaced with the meta-option".
  - OfficeQA card pass rate "25-29%" (D9 critic missing).
- **#13** D14 l.71 / l.90 / l.96, all as quoted.
- **#14** D12: 50.8% vs 26.7%, same text, same 60 items; D11: 22–24 points.
- **#16** v1 test: 66.7 / 66.0 / 63.5, opened with consent.
- **#17** E5 critic #4: 2-run MDEs as quoted; pooled ≈3.0 when evolving on OfficeQA.
- **#18** E6 critic R3 and D8 critic missing: no rule-on-card positive control was ever run.
- **#19**
  - spec l.177: "Out of scope for v4 (explicitly NOT to implement): fresh-batch version-level acceptance, changes to C1-C4' thresholds".
  - overnight report l.38: 11 of 12 reviews "需修订".
  - l.135: caps of 11.6 / 11.7亿 (as caps; see R9).
- **#20** D13 verdict_cn quote is verbatim.
- **#21** D4 critic: 2.3×, +34M.
- **#22** Per-cell tokens: 4,088 / 3,995 / 3,969 / 7,927 (D6 critic #5; E5 cost_estimate "ids-full 3,995").
- **#23** E1: balanced accuracy 0.47–0.55; content separation 0/23; the stall where S_t = S_{t−1}.
- **#24** D12 rec #2: 122/122; E9: scaffold 0.891.
- **#25** RL l.197: generated items 30 better / 6 worse vs real items 11/12 and 9/9.
- **#26** E2 critic: ≈292M / 523M; joint success 5.5%.
- **#27** overnight report l.53 (step ②); E9 critic.
- **#28** E6 rec #1.
- **#29** E8: 0 [−3.7, +3.7] officially; −13.5 under tag-only scoring.
- **#31** D5 critic: control:3 −0.100 → −0.005; D9 critic: card tag drop 0.1%.
- **#32** E3 figures.
- **#33** D8 cost_estimate: "ledger, which charged 26.5M vs 14.0M real in cal-1".
- **#34** 59/600 vs 300: the conflict exists and the proposal flags it.
- **#36** D10 critic missing #8.
- **#37** Registration v6 section 2 (l.84–88): 600/400; 74/172; 283/125; 120 (91 judgeable)/279; 57/134.
- **#38** E10 critic R7: "In V4, 8 validator updates gave 5 valid and 3 invalid candidates and 0 promotions".
- **#39** D3 critic: the tracker gained only in a redesigned loop.
- **Arithmetic**:
  - Exp 1: 3,200 × 4,088 ≈ 13.1M; 1,232 × 3,969 ≈ 4.9M; 4,532 cells ≈ 5.2 h at 880 cells/h.
  - Exp 4: 900 cells × 1.4–1.8k ≈ 1.3–1.6M.

## C. Feasibility issues

**F1. Exp 1 power is overstated.**
- The SD of 0.243 is the SD of per-item differences of **2-run** means. In the E7 critic's `power.py`: `d=[L(s,a,i,[0,1])-L(s,b,i,[0,1]) ...]`. Exp 1 uses 1 run per item.
- Two ways to estimate the 1-run SD:
  - From E5 critic #5's card-parent run variance (0.027 per arm): SD ≈ √(0.059 − 0.027 + 2 × 0.027) ≈ 0.29.
  - From D1's ratios of k = 1 to k = 2 SDs (0.402/0.344 to 0.326/0.222): 0.28–0.36.
- At 800 items × 1 run:

  | | proposal | corrected |
  |---|---|---|
  | MDE80 | 2.4 | ≈2.9–3.5 |
  | 95% half-width | 1.7 | ≈2.0–2.5 |
  | Holm-adjusted half-width | — | ≈2.3–2.8 |

**F2. The decision rule leans toward NULL.**

My normal-approximation simulation. Assumptions:
- the placebo's true effect equals the card's;
- LiveMath's true effect is 0, with an SE of 2.5 points;
- C − TC and C − placebo are correlated at 0.5.

Results at SD 0.293:

| true effect | final POSITIVE | declared NULL | extension triggered |
|---|---|---|---|
| 0 | 0 | 1.00 | 27% |
| +2 | 0.17 | 0.83 | 73% |
| +3 | 0.61 | 0.39 | 51% |
| +4 | 0.94 | 0.06 | 18% |

- At SD 0.357, a true +3 is declared NULL 41% of the time.
- The effective MDE80 of the rule is about +3.7 to +4 points.
- The 13M extension is triggered 27–41% of the time even at a true zero.
- Fixes:
  - pre-register NULL as an equivalence statement ("no gain ≥ 3 points for this package");
  - report "still not POSITIVE" as unresolved, not as NULL.

**F3. Only the card arm is checked for answer tags.**
- F is "answer conventions only".
- On the scaffold, form sentences dropped the answer tag in 23.7% / 34.5% / 39.0% of replies (D9 critic: "The form-sentence arms on the scaffold drop the <answer> tag …").
- Under the official strict score, a format loss in F or C reads as "no effect". This is the same mechanism that masked E-ds s1-r1.
- Fixes:
  - monitor the tag rate in every arm;
  - hold the package arms to the same ≥99% rule;
  - or pre-register JSON-aware scoring as a co-primary measure.

**F4. One placebo is not enough.**
- The card placebos measured so far are 0.000 and −0.023 (D1, unreviewed).
- D11 critic #7: "A single placebo is one draw from that spread … At least 3-4 texts are needed".
- The rule "package − placebo lower bound > 0" depends on which placebo is drawn. Use 2–3 placebos and compare against their mean.

**F5. The rule "duplicates within 2 SE" is not a validity test.**
- E2 critic R6: "A byte-identical canary has an expected difference of exactly 0 under any exchangeable dispatch. It therefore cannot detect the text-dependent drift … fires on about 5% of valid rounds by construction".
- Log it as a diagnostic; do not use it to trigger reruns.
- Text-by-session regime switches need a separate monitor: reply length and short-reply share per arm. E9 critic R4 found +20.3 points on the same hash and the same items.

**F6. The NULL result has a narrow scope.**
- Exp 1 runs only where headroom is smallest:
  - SearchQA: about 6 points of substantive headroom, by the proposal's own count.
  - LiveMath non-meta: MDE about 7.
- OfficeQA is excluded, although the card passes only 25–29% there. So is ALFWorld, where D14 proposes a state-conditioned rule.
- A NULL therefore licenses only: "no gain of 3 points or more from one hindsight package on SearchQA, and no large gain on LiveMath non-meta items".
- It does not license "experience adds nothing measurable on top of a task card", and it does not license stopping on all five benches.

**F7. The LiveMath arm is weak.**
- The 154 non-meta items are reused: v3 stage 3, D7, D9 and D10 all analysed their failures.
- "point < +3" at an SE of about 2.5 is a weak NULL. A true +5 still gives a point estimate below 3 in 21% of runs; a true +3 does so in 50%.
- D7 critic #3: the same text on the non-meta items swung "47/70 vs 42/70".

**F8. Drawing the SearchQA rows needs care.**
- The 800 never-sampled rows need id-level exclusion of:
  - blocks A and B (already used);
  - blocks C and D (sealed);
  - the 600-item pool;
  - the 400-item test.
- It also needs a new registration and owner sign-off. The proposal notes the sign-off.
- Exp 0's fallback, the 400 non-focal items, is mostly used already. E5 critic missing #7: "Never-used training items are down to 59 of 600".

**F9. Exp 4 misses half the benches that have real headroom.**
- At 300 items × 1 run, the rule "≥ +5 and lower bound > 0" passes only 50% of the time at a true +5 (SE ≈1.7–2.1 points), and 83–88% at a true +7.
- E3 critic R2: "110–250 items at 2 runs for 5 points".
- E3 critic R3: multi-section cards cost ×1.5–3 more.

**F10. One writer.**
- A NULL bounds only that writer's package. The proposal concedes this.
- The D9 annotations given to the writer come from one rater.
- Use a second independent writer, or measure the writer's in-sample gain, so that a NULL can be separated from a weak writer.

## D. What survives

1. **Stop implementing v4 as specified.** The reasons stand:
   - v4 keeps the C1–C4' thresholds and excludes version-level fresh-batch acceptance (spec l.177).
   - cal-1 shows that rule-sized effects are invisible to the gate.
   - D13: "效果太小 … 提示词改不了".

   Only the cost framing must change (R9).
2. **Run a card + strong-package vs card test on fresh items before any learner.** No such arm exists anywhere (critics of D9, E5, E6, E7, D8 and E8). It is the cheapest informative step, once F1–F5 are fixed and the NULL scope is narrowed (F6).
3. **Stop these:**
   - new five-bench chains;
   - the full E2 transfer matrix;
   - generated panels or model-written checks as gates or as evidence (122/122; scaffold 0.891; blind to the −9.5 harm; RL l.197);
   - veto-only checks on a similar bench's training items.
4. **Keep these:**
   - interleaving, tag monitoring, and treating truncation as unknown;
   - the D11 reporting template;
   - the ledger rule of reporting learning against an instruction baseline;
   - the frozen v3 and cal-1 artefacts;
   - LiveMath results split into meta and non-meta.
5. **These numbers are correct:**
   - the 975-item GLM null for a one-step learner (≈0 ± 2);
   - v3's 0 / 0 acceptances;
   - "gains appear only against weak starts" (le − bhand +4.7, lh − bhand +4.9).

   One caveat: bhand "是10/11读过学到的Skill后手写的" (RL l.222).
