# Evidence-fidelity critique: instrument.md (lens 量尺优先, instrument first)

Critic: adversarial evidence-fidelity critic, 2026-10-21. Read-only. No model calls, no SSH, no test pools.

Read in full:
- brief.md and the proposal.
- docs/handoff/overnight-report-20261021.md (all), feasibility-exploration-20261021-cn.md and cal1-registration-20261020.md.
- Ledger lines 137, 139, 140, 142, 144, 146, 148 and 222 of docs/results-and-lessons.md.
- result.json for every direction that has one, critic-result.json for all 21 directions that have one, and D1/D5/D14 report.md where needed.
- v4 spec.md lines 1-196, project-status.md §0 and §1, registration v6 lines 80-92, and skillopt/coevo5/protocol.py lines 10-30.

Every F-row was opened at its cited source. Line numbers below are file line numbers.

**Verdict: needs_revision.** Most numbers in the claims table are quoted correctly. But five load-bearing statements are refuted by on-disk records the proposal does not cite (A1-A5). Several others overreach their source (A6-A12). Four design points conflict with critic findings or with the v4 spec (D-a to D-d). The core plan survives in a narrower form (section E).

---

## A. Refuted or materially misleading claims

### A1. "every placebo sat on the scaffold (F18)"; "The owner's contrast is uncalibrated" (§1(c))
REFUTED by the D1 pilot, which the proposal itself cites as F19.
- D1/report.md line 170: "| S+P2 − S (hex-colour placebo on the good instruction) | 0.000 [−0.035, +0.035] | 7/7/116 |"
- Line 171: "| S+P3 − S (recipe placebo on the good instruction) | −0.023 [−0.062, +0.015] | 7/10/113 |"
- Lines 175-176: "the good-instruction parent is quieter (same-text SD₂ 0.159 vs 0.222 for the scaffold …) and moves less under placebos (|mean| ≤ 0.023, τ 0.06–0.14)."
- D1/result.json pilot.result: "Same good text twice: +0.004 … Hex-colour placebo on the good text: 0.000 … Recipe placebo on the good text: -0.023".

The D11 critic's #7 ("Those placebos were scaffold + placebo text; the effect on top of the Seed was never measured") and the D10 critic's R4 were written about cal-1's four arms only. The null and placebo side of the card regime has been measured once: 130 fresh items × 2 runs. What is genuinely missing is a known-POSITIVE rule on top of the card (E6 critic R3; D8 critic missing). "No card + rule arm" holds for learned rules only. Content-free "card + rule" arms exist.

### A2. F21 and the §3 fallback (3): "a solver regime where learned − generic was +4.6/+6.7 (GLM, F21)"
REFUTED as a description of a regime where learning beats an instruction.

1. Same Skill, same pool, not independent.
   - Ledger line 139 (fg17): "fromempty（gen17的pass/fail分支）198 … fromempty−父 +0.067［+0.025,+0.113］". This is the same gen17 Skill as the +4.6 of line 137, re-measured on the same 242-item pool ("同一池、不独立" is the ledger's own note on that block).
   - The D9 critic, the proposal's source, itself writes "(fg17; same dev pool; …)". The proposal drops that qualifier.
2. The independent second history and the learn-on-top study are null.
   - Line 139: "pass/fail−通用指令为+0.046、+0.029（一条区间下端+0.005、一条含0）——…没有稳定建立"
   - Line 139: "pass/fail分支−父 +0.029［−0.011,+0.072］…“在通用指令之上再学一步”的增益没有建立"
3. The comparison was not what the fallback implies.
   - Line 137: "这是“从空Skill学到的Skill”与“通用文本”两个备选的比较，**不是**“学习在通用指令之上还能加多少”"
   - The "generic" text was a 3-line instruction written after reading a learned Skill.
   - Its references ran in blocks after the branches. Line 137: "各参照按块排在分支之后（服务漂移可能偏置参照对比）". That is the non-interleaved dispatch the proposal's own Change 2 and Stop 3 forbid.
4. The high-resolution GLM study is null (line 222).
   - "**P1 `lz`−bzero +0.001｜［−0.016,+0.018］**"
   - "“从任务经验学习”相对一份不看任何任务结果的零样本指令的增量为0±2个百分点；只有从较弱的初始指令出发时学习才有可见增益（把它补到同一水平）".
   - Design: 975 fresh items, 20 arms interleaved.
5. Real OfficeQA items, three solvers. project-status.md §0: "真题 74 道上 learned 对 bzero 跨 3 个模型全部零增量".

So F21's type tag "RUN" should read "adaptive dev evidence" (lines 137 and 139: "开发池被多次复用，属自适应的开发证据"). The GLM option in §3 has no evidential support.

### A3. §1 opening: "has never been put to an instrument able to answer it"
REFUTED for the GLM solver.
- Ledger line 222 put "one learning step on top of a task-card-derived zero-shot instruction" to an instrument resolving about ±2 points: 975 fresh items, 20 interleaved arms, 5 histories per arm. The answer was +0.1 [−1.6, +1.8].
- It is recorded "缺失条件下未分辨" only because the worst-case missing-outcome bound reached +3.2.
- True only for deepseek-v4-flash in the I-ds (task-card start) regime, and for learned-rule transfer.
- This also bears on the lens falsifier in §5(1). The one time the instrument was adequate, the method's increment was ≈0.

### A4. Misreading of cal-1
Claims: "the gate cannot see rule-sized effects … the rule-sized bridges pass 0% and cand 7.7% (F1, F2)" (§1(a)); summary_cn "C1 … 认不出1–3分的规则"; "C1 passes it only 75.8%".

What cal-1 itself says:
- cal1-registration lines 150-152: "The rule-shaped bridges carry no detectable effect at all, so nothing rule-sized was available to calibrate C1 on".
- Lines 83-84: "Detecting the broad seed does not exonerate C1 for narrow effects; the bridge arms are the only rule-shaped evidence and are themselves unvalidated."
- Line 138: the bridges are +0.0037 / −0.030 / −0.026; cand is −0.026 [−0.072, +0.020].

So 0% passage for null arms is correct behaviour, not blindness. cand's 7.7% is passage of a null-or-harmful arm.

The "cannot detect 1-3 points" claim rests on D8's SIMULATION only. D8/result.json recommendation: "per-step power for rule-sized (+0.3 to +3 pt) effects stays at 0.19-0.26". It should be cited as such.

75.8% is, by the pre-registered table, "between 50% and 80%: inconclusive … close to the upper bound" (lines 148-150). That is neither "only" nor "认得出". Also, passage depends on the eligibility pool: 54.3%-94.1% on the other pools (line 141).

### A5. summary_cn "v3 收下0条规则只说明‘没测出来’，不是‘没用’"; §1(a) "not established, not absent"
MISLEADING to the owner. The proposal omits the version-level replay of v3's own I-ds rules on out-of-sample halves.
- D1/report.md §5.3: "**On the good-instruction chain no rule shows a version-level effect** (7 arms, check-half means −0.107 to +0.005): D1 would not have changed I-ds's outcome."
- D9/critic-result.json confirmed_claims (re-derived): "I-ds SearchQA +0.000 / +0.004 / +0.015; LiveMath −0.022; SpreadsheetBench −0.044 (screen) / +0.027 (confirm); ALFWorld −0.140 [−0.254, −0.035]".
- D1 risk 2: "There may be no effect to find … D1 fixes the measuring instrument, not the proposals."
- D13 critic: "旧规则失败主因是效果太小，提示词改不了".

The honest reading: these specific rules showed no benefit even when measured at version level on about 100 unseen items, and one was significantly harmful. Effects below about 4-5 points remain unresolved. "不是没用" overstates.

### A6. "The score mixes three nuisances" and "regime confounding" as a binding constraint in the owner's regime (§1(b), Diagnosis)
OVERGENERALISED. In the card regime the dispatch/serving nuisance is OfficeQA-specific.
- F7's numbers are the empty scaffold (E6 critic R2: "the same text inside the v3 run on the same 200 items: single-arm train unit … 1.0% untagged … v3 screen parent … 9.0% … v3 confirm … 6.5% … cal-1, 16 h later … 10.1%").
- So "gated them in interleaved rounds (6.5–10.1%)" mixes cal-1 (10.1%) into v3's gate rounds (6.5-9.0%).
- The task card tags 0.1% (D9 critic #2) and the I-ds parent 1.000 (E7 critic #1).
- On SearchQA the card is robust across days and modes:
  - E4 critic R7: "The drift is specific to the scaffold: -5.9 [-9.9,-1.9] (n=200). The five-card Skill moved only -0.5 [-2.8,+1.6] (n=199)."
  - D11 critic #9: "Seed, terse vs verbose window: +0.25 [−2.91, +3.41]", and on LiveMath/SpreadsheetBench/ALFWorld "no regime effect was detected".
- The card-regime regime effect is real on OfficeQA:
  - E9 critic R4: +20.3, 8 of 9 units answer-only.
  - D12 evidence: SD 11.4 for I-ds, but 1.3 for E-ds.

### A7. F11 "Rule-vs-card per-item SD is 0.243, so +5 / +3 points need ~186 / 515 items", used as the owner's contrast (§1(c))
Number quoted correctly, APPLIED TO THE WRONG CONTRAST.
- E7 critic #4 computes "rule vs task card", where the rule is cand on the empty scaffold. E7 critic missing #1: "The owner's actual I-ds contrast, task card + learned rule vs task card, was not run on any solver."
- In-regime estimates already exist:
  - D1/report.md §4.1: "placebo churn on the good instruction (pilot) | 2 | 771 / 343 / 123" (n₈₀ for +2/+3/+5 at 2 runs);
  - "same text, good instruction (pilot) | 2 | 389 / 173 / 62";
  - E5 critic #5 proxy (ids-full − seed-only): "n ≈ 196 at 2 runs for a 5-point effect".

### A8. S3 "(registered exception: no method role has seen them)"; F14 "59 never-used SearchQA"
NO CHECKABLE SOURCE for the first part (defaults to refuted).
- "59" is the E5 critic's accounting. Missing #7: "Never-used training items are down to 59 of 600 (200 focal, 31 regression, 130 D1-v2, 180 E5-P1)."
- That count does not list E8's "SearchQA (100 fresh training items x 2 runs, 600 cells, 0 unknown)" (E8/result.json evidence) or E4's 30-41 SearchQA training items. The true number may be lower.
- GLM method roles touched SearchQA training items in several pilots:
  - D2: cases from 30 proposal-half failures;
  - D9: GLM wrote hints on 60 items with the answers in view;
  - E8: GLM read 65 v3 failures.
- Whether any of these fall in S2's 300 is unverified.

### A9. §4 "the instrument as an executable rubric … validated on frozen labels (D9's 54-item audit; E6 critic's ~95% form/substance agreement)"
OVERSTATED. No human labels exist.
- D9 critic #4: "I read, by hand … This is a single-rater judgement." The rater is the critic agent.
- E6 critic R5: the ~95% is agreement between the examiner's codes and the explorer's GLM judge labels, two model outputs.
- E6 critic R6: "The audit was the explorer model reading 56 pairs, not a human … not human-validated precision."
- F15's "one rater" should say "one AI reviewer".

### A10. §3 (2) "OfficeQA's card failure mass is +35.8 points"
MISLABELLED.
- D9/result.json evidence row: "OfficeQA: 74 | 29.1% | 52.5 | 26.0 (50%) | 18.5 (35%) | 8.0 (15%) | +35.8 pts". The last column is "ceiling if every non-dead item were fixed".
- The failure mass is 52.5 item-equivalents (≈71 points), half of it dead items.
- D9 critic missing: "The OfficeQA half of D9 was never run."

### A11. Internal contradiction: Stop 4 vs S2 row D and S3 round 1
- Stop 4: "Byte-identical canaries as drift alarms: expected difference exactly 0 under exchangeable dispatch, ~5% alarms by construction (F27)" (E2 critic R6).
- S2 row D: "D1 accepts P′, or the P′−P CI excludes 0 → dispatch broken, fix". S3: "Round 1 adds P′".
- Row D is the same device, with the same ≈5% false alarm. It is useful only as a check of back-to-back ordering, which must then be stated, with the order inside item blocks specified.

### A12. S4 "'no drop' iff LB > −margin (OfficeQA 10, LiveMath 9, SpreadsheetBench 15; D8)"
D8 critic R1: "the C2' margins (6/10/9/15/25) as protection. Yet v5's 25-point ALFWorld margin lets a 10-point harm pass more often than v3 does (0.63 vs 0.56)."

A 15-point margin cannot support the owner's "dissimilar benches do not drop". Report it as "a drop larger than X points is ruled out".

---

## B. Minor citation and precision problems
- F2: the n=6/n=20 figures are on cal1 line 140, not 139.
- F4 paraphrase. "414/424 also carry the same answer in a tag" reads as if the JSON reply itself is tagged. The D5 critic says "the identical answer string also appears inside an <answer> tag on the same item, and in 324 of those 414 the tagged version passed", i.e. in other replies. E7 critic #2: JSON is only ~38% of untagged cand replies, ~30% overall.
- F13 is a SIM with an assumed τ = 0.20. D1/report.md §4.3 assumes SpreadsheetBench W = 0.14. D1 risk 8: "the real-effect heterogeneity only on the empty scaffold; the other benches use an assumed tau". D1 was never critic-reviewed (overnight-report §6.5: "D1 | 高 | 未审查"), yet Keep 4 makes it the lead gate.
- F27: the 0.88 bin has n = 25. The E2 critic calls it "样本不大，只能算旁证".
- F30: "[0.40, 0.81]" is a p10-p90 band (E10 critic R4), not a 95% interval.
- F33/§3 anchors. "LiveMath 4.4k, OfficeQA 8.4k" are the D11 critic's #6 ("SearchQA 3.9k, OfficeQA 8.4k, LiveMath 4.4k, SpreadsheetBench 4.3k"). The cited D6 critic #5 gives 3,969 / 7,927.
- "(E7 critic: safe)" for "answer contract at both ends" is an assertion, not a measurement (E7 critic #3).
- D10 critic missing #8 is "A holdout plan: draw a new SearchQA block from never-sampled rows". It is about a test block, not the fresh TRAINING block the proposal attributes to it.
- Stop 2 "a gate blind at this size" overstates. cal-1 is inconclusive at 75.8% for +9.4. D8 gives low power (0.19-0.26), not blindness.
- M1's `content` field is "official comparison on a JSON-aware extraction", i.e. still strict EM. F15 and F16 show strict EM rewards surface form, so the label "content" will mislead the owner.

---

## C. Confirmed (opened at the cited source; quotes abbreviated)

cal-1 and the ledger:
- F1: cal1 line 137, "`ids-full` mean +0.0938 [0.0505, 0.137] … `seed-only` +0.0887".
- F2: cal1 line 139 ("75.8% … `seed-rule` 0%, `seed-rule3` 0%, `cand` 7.7%, `parent:B` (null) 0%") and line 140 ("47.9% / 99.0%"); overnight line 19.
- F20: ledger line 142, "进初筛 15 条，过 2 条，过复核 0 条 … deepseek 139,024,462 … GLM 7,804,250".
- F32: cal1 line 130 ("ledger settled 27,481,897"); E7 critic #8 ("receipts sum to 14.0M (17.6M charged)"). 27.48/17.6 = 1.56.

Critic re-analyses:
- F5: E7 critic confirmed_claims, "cand +0.0675, control:3 -0.0025 … control:2 still +0.036".
- F6: E7 critic #1, "parent and all 3 screened rules … tag share 1.000 and 0 JSON … screen goes from +0.75 to +13.75 … confirm from -2.50 to +12.25".
- F7 numbers: E6 critic R2 (scope caveat in A6).
- F8: E6 critic R3, "+0.0325 [-0.004, +0.069], 20/11 … No positive control exists for that regime".
- F9: E9 critic R4, "+20.3 points (SE 5.2; 19 up / 3 down)", "8 of 9 OfficeQA units were 'answer-only'".
- F11 number: E7 critic #4 (scope caveat in A7).
- F12: D8 recommendation (0.19-0.26); D8 critic R3 (Clark 1973); R2 (detection 0.001 → 0.965 at n=40).
- F15 number: D9 critic #4, "about 73%" (rater caveat in A9).
- F16: E7 critic #5, "on glm-5.3 and deepseek about 0 … every measured SearchQA skill effect is answer surface form". This is a replay of the 98-item E7 pilot.
- F17: D9 critic #1, "None of the 11 texts is 'TC + a rule'".
- F26 logic: E9 critic R1.
- F27: E2 critic R6 ("expected difference of exactly 0 … about 5%") and confirmed table 0.88 / 0.84 / 0.74.
- F30 number: E10 critic R4, "120x2 ceiling is tau 0.63".
- F33 v3 values: D6 critic #5. ids-full 4,669 and scaffold 2,780: E9 critic R6.

Direction results:
- F10: D12 evidence, "50.8%, 26.7%, 26.7%, 34.2% … 11.4 points for I-ds OfficeQA, 1.3 for E-ds".
- F13 numbers: D1 evidence [E], "SearchQA 0.042 (300 x 2), LiveMath 0.056 (233 x 2), OfficeQA 0.103 (37 x 4), SpreadsheetBench 0.122 (46 x 2), ALFWorld 0.153 (29 x 2)".
- F19: D1 pilot, "130 never-used … 1,560 cells … +0.162 … accepted … cost_tokens 2388219 … did not test a learned rule package".
- F24: D14/report.md line 228, "Guard the action interface in the frozen loop for every arm". The report is unfinished and unreviewed.
- F25: D7 evidence, "reference in 129/129".
- F28: D12 pilot, "122 of 122 cells passed".
- F29: E1 pilot, "0.487-0.539 on SearchQA … 0.474-0.548 on OfficeQA".

Repository documents:
- F14 sizes: registration v6 lines 84-88 (600/74/283/120 qualified/57; tests 400/172/125/279 qualified/134); "59": E5 critic missing #7 (caveat in A8).
- F22: spec line 138 ("Gate criteria C1-C4' are otherwise unchanged") and lines 177-178 ("Out of scope … fresh-batch version-level acceptance").
- F23: spec lines 69-74.
- F26: protocol.py line 18 (`SIMILAR_PAIRS`; OfficeQA is in all three pairs).
- F31: project-status line 118.

Other attributions that check out:
- E4 critic R2 (spacing ≥2 min "does not lower the 8-10% flip floor") and R4 ("absence of evidence as evidence of absence").
- E2 critic missing #4 (regime from reference arms only).
- E5 critic #4 ("~3.0 points when evolving on OfficeQA").
- E1 critic on DecoEvo (rubric not to be revised on solver scores, 13 of 15 worse) and R5 (S_t = S_{t−1} stalls the loop).
- D8 critic on "21 unknown runs" → 15.

Cost arithmetic:
- S1: 1,110 cells × 8.4k = 9.3M.
- S2: 4,200 × 4.7k = 19.7M. About 5 h at D1's "about 880 cells/h at 6 workers".
- S3: 0.94M per step for the rollout plus 5.64M per two-arm round.
- S4: 7.46 + 4.98 + 2.06 ≈ 14.5M.

Evidence typing: the proposal labels pilots, replays and simulations, and says none is method-effect evidence. That holds except F21 (A2).

---

## D. Feasibility issues

**D-a. "v4 scope: B-fixes + M1 now; P1/P4/P5/P6 wait" (Change 7) cannot be implemented as specified.**
- Spec line 51: B4 "(B6/P4 format, 3 votes)".
- Lines 66-67: B6 uses "the rule's `when`/`do` (P1)" and "3 votes (P4)".
- Line 78: B8 "trigger/precision in P1".
- Line 82: "B9 … v4 = P5 (per-code calls)".
- Line 99: "B13 = P7".
- Overnight line 39: "G4 先做，因为 G1/G2/G3 要用它的投票和重问助手".
- B4, B6, B8 and B9 need P-free rewrites, or must move with P1/P4/P5.

**D-b. S3 reuses one 300-item acceptance batch for ≤3 decisions, then calls "beats the card again next round" "established".**
- D8 critic R4: step-wise reuse "is a de facto fixed validation set, which the owner forbids".
- D1 risk 11 and the owner's rule (project-status §1).
- Winner's curse 1.34-1.51× at δ = 0.03, n = 300, k = 2 (D1 §4.2).
- A re-win on the same items is not replication on new items. It is the fixed-panel problem the proposal raises against C1 (F12).

**D-c. S1 chooses the base prompt on OfficeQA's 74 training items, and S4 reads transfer on the same 74.**
- E2 critic missing #7: "The OfficeQA training pool has been reused by four pilots … a de facto development set; disclose this or make the test panels primary."
- The owner already approved per-step test evaluation (project-status lines 119-121, 10/16 15:03).

**D-d. S2's positive control can be vacuous, and row A sits on the threshold.**
- "every A_j whose CI excludes 0 has its add-back accepted" is vacuously true if no single-bullet removal is detectable. Then row A rests on planted (simulated) power alone. cal-1's single card sentences on the scaffold were +0.004 / −0.030 (cal1 line 138).
- The cal-1 table already has the right rule: "the positive effect does not reproduce → the positive control failed to qualify" (line 80).
- D1 §4.2 already gives power 0.60 (mix) / 0.49 (mixchurn) for δ = 0.03 at n = 300, k = 2, against the 0.6 threshold.

**D-e. SearchQA as the S2/S3 arena.**
- D9 critic confirmed_claims: "SearchQA should not host a 'learned rule beats the instruction' claim".
- E7 critic #5: SearchQA effects are surface form with "Nothing suggests it would carry over to OfficeQA numbers or LiveMath option letters".
- M1's strict-EM `content` would accept J! Archive conventions. S2+S3 are ≈50M charged (≈80M ledger) on that bench. The S4 sub-EM pivot is the right guard; it should also be an S3 acceptance condition (report sub-EM for every accepted version).

**D-f. Total cost.**
- S1-S4 ≈ 74.5M charged + 3M GLM, ≈ 116M ledger at ×1.56, caps 150M. That is comparable to v3's 139M (ledger line 142).
- If S2 lands in row B, S0-S2 ≈ 29M charged ≈ 45M ledger.
- Baseline reruns are not costed (risk 7). Stop 2 should not frame 139M as waste without stating this.

**D-g. S0 data location.** cal-1 attempt-2 exists only on the old machine (ledger line 144: "attempt-2 只在老机器"; overnight §4). S0's "cal-1 (8,800)" needs that copy first.

---

## E. What survives

- Per-rule C1 on 6-11-item trigger panels has low power for rule-sized effects (D8 SIM 0.19-0.26). cal-1 is inconclusive at +9.4. Moving the decision to the version level on fresh items is supported.
- JSON-aware extraction as a new registered scoring version, with format and correctness recorded separately. It fixes E-ds s1-r1, not the I-ds null (E7 #1).
- Interleave rollout and gate in one dispatch mode (E6 R2).
- Regime covariates, with regime computed from reference arms (E2 missing #4).
- Investigate or pin OfficeQA's answer-only regime before any OfficeQA readout (E9 R4; D11 confirmed).
- Split LiveMath into meta and non-meta items (D7).
- ALFWorld action guard for every arm (D14 line 228; D3 critic).
- Keep the similarity map (E4 R4).
- Stop generated-panel and ladder fitness for now (D12, E1, E10).
- Do not pick flash for its effect size (E7 #5).
- The fallback "write the calibrated null as a measurement paper" (D10).

S2 is still worth running, but in a narrower form:
- The null/placebo side of the card regime is already partly measured (D1 pilot: copy +0.004, placebos 0.000/−0.023, SD₂ 0.159).
- The unique value of S2 is a working POSITIVE control on top of the card.

The GLM-regime fallback and "never tested with an adequate instrument" do not survive. Neither does "v3 null = 没测出来不是没用". The expected yield of S3 should be stated as low:
- D1 §5.3 replay: 7 I-ds rules −10.7 to +0.5 points.
- Ledger line 222: GLM learned − zero-shot ≈ 0 ± 2.

---

## F. corrections_cn（给综合者，可原样采用）

1. 删掉“所有安慰剂都放在空骨架上”。
   - D1（“整版验收、每步换新题”那个探索方向）的试跑，已在任务卡上加过两段无关文字（安慰剂）和一份逐字相同的副本。
   - 试跑规模：130 道从没用过的 SearchQA 训练题，每题 2 次。
   - 结果：两段安慰剂 0.000、−0.023，副本 +0.004。
   - 任务卡下同一文字重跑的逐题标准差是 0.159，空骨架是 0.222。
   - 所以“任务卡之上”的空对照已经量过一次。真正缺的是“任务卡之上加一条已知有效的规则”这种正对照。（来源：feasibility-20261021/D1/report.md 第 170–178 行）

2. 删掉“GLM 做题模型上学到的文字比通用指令高 4.6/6.7 分”这一备选，也不要据此建议换回 GLM。
   - +4.6 和 +6.7 是同一份学到的 Skill、在同一批 242 道开发题上的两次读数，不是两次独立结果。
   - 独立的第二条历史只有 +2.9 分，区间含 0。“在通用指令之上再学一步”也只有 +2.9 分，区间含 0。账本原话是“没有稳定建立”。
   - 那份“通用指令”只是读过学到的 Skill 后手写的三行字，而且对照组是分块后跑的，不是交错跑的。
   - 10/13 的大实验（975 道新题、20 种文字同时段交替）同样用 GLM 做题：“从任务经验学一步”比一份只看任务卡写的零样本指令只多 +0.1 分，区间 [−1.6, +1.8]。
   - 10/15–16 在 OfficeQA 74 道真题上，三个做题模型（含 GLM-5.3）学到的 Skill 比零样本指令都是零增量。
   - （来源：docs/results-and-lessons.md 第 137、139、222 行；docs/project-status.md §0）

3. 把“负责人的问题从来没有用够格的量尺测过”改成下面这句。
   “对现在的做题模型 deepseek-v4-flash、从任务卡出发的主链，确实还没有用够格的量尺测过。但 10/13 在 GLM 做题模型、SearchQA 上，已经用够格的量尺测过一次‘学一步对零样本指令’。那次是 975 道题，误差范围约 ±2 分，结果约等于 0。”（来源：docs/results-and-lessons.md 第 222 行）

4. 关于标定实验 cal-1，改成下面这段，不要写成 cal-1 测出了“认不出 1–3 分的规则”。
   “C1 门（每条规则只在 6–11 道触发题上比）对 +9.4 分的整套任务卡，通过率 75.8%。按事先登记的表，这属于‘无法下结论’，接近上限。三段规则大小的桥接文字本身就没有效果（+0.4、−3.0、−2.6 分），所以 cal-1 没有能用来检验‘认不认得出 1–3 分规则’的材料。‘认不出 1–3 分’来自 D8（统计规程方向）的模拟：这种大小的效果，每步检出把握只有 0.19–0.26。”
   （来源：cal1-registration-20261020.md 第 83–84、148–152 行；D8/result.json recommendation）

5. 删掉“v3 收下 0 条规则只说明‘没测出来’，不是‘没用’”。改成下面这段。
   “v3（第三版协议）主链从任务卡出发，有 7 条受检规则。放到提规则的模型没看过的那一半训练题上重算（SearchQA 100 道，其他 28–49 道），效果在 −10.7 到 +0.5 分之间。ALFWorld 那条在全部 57 局上显著有害：−14.0 分，区间 [−25.4, −3.5]。所以这些具体规则没有显示出任何好处。能说的只是：比 4–5 分更小的好处，现有量尺看不见。”
   （来源：D1/report.md §5.3；D9/critic-result.json confirmed_claims）

6. “时段和发送方式会扭曲分数”要按数据集分开写。
   - SearchQA：这个问题只在空骨架上测到过。单独跑时 1% 没写答案标签，交错跑时 6.5–9.0%（cal-1 是 10.1%）。五张任务卡组成的 Skill 换一天只差 −0.5 分 [−2.8, +1.6]，换“简短/啰嗦”时段只差 +0.25 分。
   - OfficeQA：任务卡版本确实随时段大幅变化。同一文字同 74 题差 20.3 分；同 60 题四个时段的标准差是 11.4 分。
   - 结论：在负责人关心的“任务卡之上”情形里，“时段混杂”目前只在 OfficeQA 上成立。
   - （来源：E6/critic-result.json R2；E4/critic-result.json R7；D11/critic-result.json 第 9 条；E9/critic-result.json R4；D12/result.json evidence）

7. “规则对任务卡的逐题标准差 0.243、看出 +5/+3 分要 186/515 道题”要加注明。
   - 这是“空骨架加一条规则”对“任务卡”的比较，不是“任务卡加一条规则”对“任务卡”。
   - 按 D1 试跑里任务卡加安慰剂测到的波动，看出 +3/+5 分约需 343/123 道题（每题 2 次）。
   - S2 的题量应以这组数和 S2 自己的测量为准。
   - （来源：E7/critic-result.json 第 4 条、missing 第 1 条；D1/report.md §4.1）

8. S3 说“S2 的 300 道题没有任何方法角色看过”，这句话没有出处。方法角色指提规则、诊断等由 GLM 担任的角色。
   - 登记前要逐题查清：每道题被哪些实验、哪些角色用过。
   - “只剩 59 道从没用过”是 E5 审查员的统计，没算 E8 的 100 道“新”SearchQA 题和 E4 的 30–41 道，实际可能更少。
   - （来源：E5/critic-result.json missing 第 7 条；E8/result.json evidence）

9. S3 设计相当于反复使用固定验证集，需要改。
   - 现在的做法：用同一批 300 道题做最多 3 次“收不收”的决定；下一轮再在这批题上“再赢任务卡一次”，就记为“成立”。
   - 这等于反复使用固定验证集。D8 的审查员明确指出这是负责人不允许的。另外，刚收下时的估计会偏高 1.3–1.5 倍（D1 的模拟）。
   - 两种改法：每次决定换一批新题（题不够就写明只能做 1–2 次）；或者把“成立”改成冻结后在测试集上读一次来判断。
   - （来源：D8/critic-result.json R4；D1/report.md §4.2；docs/project-status.md §1）

10. S1 和 S4 用了同一批 OfficeQA 题，挑选和读数混在一起。
    - S1 在 OfficeQA 的 74 道训练题上挑基础提示词，S4 又在这 74 道题上读迁移结果。
    - E2 的审查员已经指出，这 74 道题被四个试跑反复用过，实际上已是开发集。
    - 负责人 10/16 已同意每一步都在测试集上评测，所以 S4 可以改用测试集（OfficeQA 172 道、LiveMath 125 道）。至少要在报告里写明这 74 道是开发用过的题。
    - （来源：E2/critic-result.json missing 第 7 条；docs/project-status.md 第 119–121 行）

11. S4 不要写“没掉分”。
    - 现在按 10/9/15 分的允许幅度判“不掉分”。D8 的审查员指出，这些幅度起不到保护作用。
    - 结果应写成“排除了大于 X 分的下降”，并给出 X。
    - （来源：D8/critic-result.json R1）

12. S2 判定行 D 的副本检查和前文“停止”第 4 条矛盾。
    - 判定行 D 用“逐字相同的副本与原文的差，区间不含 0”来判断发送有问题。这正是第 2 节“停止”第 4 条说没用的做法：交错发送时两者期望差恰好为 0，按构造约 5% 会误报。
    - 要么删掉；要么写明它只检查“紧挨着连发”这一种顺序问题，并事先接受约 5% 的误报。
    - （来源：E2/critic-result.json R6）

13. S2 判定行 A 的正对照可能形同虚设。
    - 现在的条件是“每个区间不含 0 的减项都要被加回并收下”。减项指去掉一条任务卡要点。如果去掉哪一条都测不出变化，这个条件自动成立，A 行就只剩模拟出来的检出力。
    - 应改成：至少有一条减项的区间不含 0，正对照才算合格；否则按 cal-1 的规矩，记为“正对照不合格，不下仪器结论”。
    - 另外，D1 的模拟已经给出：300 题 × 2 次时，+3 分的检出把握约 0.49–0.60，正好卡在 0.6 的门槛上。
    - （来源：cal1-registration-20261020.md 第 80 行；D1/report.md §4.2）

14. 第 2 节“改”第 7 条（v4 先做 B 类 bug 修复，P1/P4/P5/P6 以后再做）按规格做不到。
    - B4、B6 写明要用 P4 的“先说理由再给标签、三票多数”；B6 还要用 P1 的“当…时/做…”字段。
    - B8 引用 P1；B9 本身就是 P5；B13 就是 P7。
    - 夜间汇报也说 G4（投票和重问助手）必须先做。
    - 要么把 B4、B6、B8、B9 和 P1/P4/P5 一起做，要么为这几项重写不依赖 P 的版本。
    - （来源：v4-plans-20261021/spec.md 第 51、66–67、78、82、99 行；overnight-report-20261021.md 第 39 行）

15. §4 不要说“可执行评分细则已用冻结标签验证过”。目前没有任何人工标注。
    - D9 那 54 道题的“写法还是内容”判断，是一个 AI 审查员单独读的。
    - E6 的约 95% 一致，是诊断员的错误分类和 GLM 评审标签之间的一致，两边都是模型输出。
    - 要说“验证过”，需要先做至少两人的人工标注。
    - “一位评分者”也要写明是 AI，不是人。
    - （来源：D9/critic-result.json 第 4 条；E6/critic-result.json R5、R6）

16. “OfficeQA 任务卡的失败量是 +35.8 分”要改。
    - +35.8 分是 D9 算的乐观上限：假设所有“不是永远做错”的题都能救回来。
    - 任务卡在那 74 道题上的总失败量约 71 分，其中一半是所有文字都做错的题。
    - D9 的 OfficeQA 余量探针并没有跑。
    - （来源：D9/result.json evidence；D9/critic-result.json missing）

17. M1（新的判分层）里叫 content（内容）的那一栏，其实仍是官方的逐字匹配，只是先把 JSON 里的答案取出来。它照样奖励“写法和标准答案一样”。给负责人看时，叫“修好格式后的官方分”，不要叫“内容分”。（来源：E7/critic-result.json 第 5 条；D9/critic-result.json 第 4 条）

18. 成本要写全，不要只拿 v3 的 1.39 亿当“浪费”来对比。
    - S1–S4 合计约 7,450 万计费 token，按 1.56 倍折合约 1.16 亿账本 token；各步上限合计 1.5 亿。这和 v3 一次运行的 1.39 亿相当。
    - 如果 S2 落在 B 行、只跑 S0–S2，约 2,900 万计费，折合约 4,500 万账本。
    - 基线重跑还没算在内。
    - （来源：提案 §3 各步数字；docs/results-and-lessons.md 第 142 行；cal1-registration 第 130 行；E7/critic-result.json 第 8 条）

19. 几处小错要改正：
    - OfficeQA 和 LiveMath 的单格成本 8.4k/4.4k 来自 D11 审查员第 6 条，不是 D6 审查员（D6 给的是 7,927/3,969）。
    - E10 的 0.63 [0.40, 0.81] 是 10%–90% 分位范围，不是 95% 区间。
    - D1 方向没有经过反方审查，却被用作主门槛，要写明。
    - “答案要求在提示开头和结尾各写一遍是安全的”只是 E7 审查员的判断，没有测过。
    - D10 审查员 missing 第 8 条说的是新建留出测试块，不是新训练块。
    - cal-1 的 n=6/n=20 数字在登记文件第 140 行，不是第 139 行。
    - cal-1 续跑部分的数据只在旧机器上，S0 要先拷过来。
