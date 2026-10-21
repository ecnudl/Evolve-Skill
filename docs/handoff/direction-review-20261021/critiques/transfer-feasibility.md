# Critique of `proposals/transfer.md` (lens 泛化评测优先), from the feasibility / cost / protocol side

2026-10-21. Read-only: no model calls, no SSH, no test pools opened. `P l.N` means a line of the proposal
(`.../scratchpad/direction/proposals/transfer.md`). `F/` is `docs/handoff/feasibility-20261021/`. RL is
`docs/results-and-lessons.md`.

**Verdict: needs_revision.** The diagnosis holds, and so do most of the method choices: no screening on other
benches' training items, I5 as the interleaved reference, at least two placebos, D1 version-level acceptance,
evolving on SearchQA only, and stating in advance that a null is the likely result.

The plan is not executable as costed or as gated:
- **Costs.** Several cost figures compare delivered tokens with ledger tokens. The T1 cap repeats the cal-1 cap stop.
- **Gating rules.** Three T1 gating rules either fire almost surely or depend on luck with the serving regime. The
  T1-V qualification criteria contradict each other.
- **Prompt order.** v4's prompt change (B13/P7) is added after the calibration that it invalidates.
- **Test pools.** T3 is described as a first, one-time test read, but v1 already read the same pools.
- **Spending order.** Most of T1's money is spent before anyone knows whether T2 will accept anything.

Corrected cost: about 175–225M charged deepseek tokens, against the proposal's 170M. Dispatch: about 36–66 h at no
more than 6 workers. Only T0, plus possibly a small SearchQA calibration, fits in 1–3 overnight sessions.

---

## 1. Experiment-by-experiment check

### T0: instrument repair (P l.50–54, "0 tokens")
- **(c) Protocol.** Correct: no test-pool reads, no relabelling, and the registration is frozen before v3's sealed
  test scores are opened.
- **(e) Engineering is missing.** X4 requires an item-blocked dispatcher, a regime sentinel and a content scorer
  before T1 can run, and T0 does not list them. None of them exists:
  - D11's R8 and Tango tests are unimplemented [F/D11/critic-result.json `refuted_claims` 3–4].
  - cal-1 interleaved the arms but did not block them by item [docs/handoff/cal1-registration-20261020.md l.113–117].
  - Every item needs a Codex review plus offline tests [docs/project-status.md l.122].
- **(b) Cost.** It is "0 tokens" only if content scoring is deterministic (sub_em or alias rules). With a GLM judge,
  re-scoring the archived failures costs GLM tokens. E6's judge used 1,324,475 GLM tokens for 3,268 calls
  [F/E6/critic-result.json `confirmed_claims` C2].
- **(c) Move two v4 items into T0.** B7 and B13/P7 belong here, not in T2 (see R10).
- **(d) Partial duplicate.** Part of the JSON-aware and content re-scoring is already done:
  - E7's critic re-scored cal-1 and v3 E-ds s1 [F/E7/critic-result.json R1, `confirmed_claims`];
  - D5's critic re-scored cand at +6.4 under content scoring [F/D5/critic-result.json `missing` 2].
  T0 should reuse these, not redo them. The cost is zero either way.

### T1 "tcal-1" (P l.56–62)
- **(a) Item counts.** 120 / 74 / 100 / 91 items fit the training pools [V6 l.84–88].
  - Per-target MDE at these sizes is about 8.5–10 points. D1 certifies 0.103 for OfficeQA at 37×4, 0.056 for
    LiveMath at 233×2 and 0.122 for SpreadsheetBench at 46×2 [F/D1/result.json `evidence`]; scaled to 100×2 and
    91×2 these give ≈8.5–8.7.
  - The bleed arms A4/A6/A7 on the targets can therefore only bound bleed at ±8–10 points. That says nothing about the
    2–4-point transfers that matter.
- **(b) Cost.**
  - The cell arithmetic is right: 6,752 cells and 35.7M.
  - **The rates are medians.** cal-1's card arm cost 3,846 tokens per cell at the median but 4,669 at the mean
    [F/E9/critic-result.json R6].
  - **OfficeQA's 8.4k is answer-only-mode cost.** It is the v3 seed cost [F/D11/critic-result.json R6], and v3's
    OfficeQA units were answer-only in 8 of 9 cases [F/E9/critic-result.json R4]. A verbose session adds about 3.6k
    per cell (5,847 → 9.4k) [F/D12/result.json `cost_estimate`], and rule (b) needs exactly such a computing-mode
    window.
  - **Charged cost is therefore ≈37–46M, which reaches the 45M cap.**
  - **The comparison with cal-1 mixes measures.** "1.3× cal-1" sets delivered tokens against ledger tokens:
    - cal-1's receipts were 14.0M, the charged total 17.6M, and the ledger settled at 27.5M
      [F/E7/critic-result.json `refuted_claims` 8];
    - cal-1 paused on its cap at 7,205 of 8,800 cells because the real cost was twice the estimate
      [cal1-registration l.113–117].
    - Like for like, T1 costs ≈2.5× cal-1.
- **(f) Decision rules.**
  - **(b) and (c) depend on regime luck.**
    - Regime spells last from 30 min (OfficeQA verbose 01:30–02:00) to 7.5 h (SearchQA terse 02:15–09:45)
      [F/D11/result.json `evidence`, terse-share table].
    - In an answer-only window the harm cannot show [F/E9/critic-result.json R4].
    - If both OfficeQA windows are answer-only, rule (b) demotes the only similar target to descriptive-only.
    - Rule (c) is undefined when both windows fall in the same regime.
  - **(e) probably fires.**
    - At 120×2 the SE is ≈1.5–2.3 points, so "upper 95% bound < +3" fires unless A6's estimate is at least about +0.6.
    - D1's replay of the seven I-ds rules gave −10.7 to +0.5 [F/D1/result.json `evidence`].
    - So T2 probably starts from G-start, which is a near-duplicate of the 10/12 experiment: one step on top of a
      generic instruction, +0.029 [−0.011, +0.072], not established [RL l.139].
  - **(g) fires almost surely.**
    - A true-zero placebo exceeds 2 points by chance: P ≈ 17–24% on SearchQA (SE ≈1.45–1.7, from SD2 0.159),
      ≈50–60% on OfficeQA (SE ≈3–3.5), ≈30–50% on LiveMath and SpreadsheetBench.
    - Over 2 placebos × 4 benches, P(rule g fires) ≳ 90–98%.
    - It has effectively already fired: an I5-parent placebo moved SearchQA by −2.3 at 130×2 [F/D1/result.json
      `evidence`].
    - Consequence: T3 gets 4 placebos.
  - **(d) conflicts with T3's fixed co-primary.** "That target primary in T3" clashes with X3/T3's fixed co-primary
    (self + pooled LiveMath/SpreadsheetBench no-drop); how it changes T3's rules and multiplicity is unspecified.
- **(c) Fallback.** If the owner declines the use of target training data, the "archived E2/E4/E9 cells" fallback
  cannot run rules (b), (d), (f) or (g) (see R9).
- **(d) Duplication.**
  - A4/A5 repeat E9's and E2's answer-only harm. That is legitimate as a same-window positive control.
  - A6 is D1's proposed 2.1M pilot [F/D1/result.json `cost_estimate`].
  - A7 is a version of E2's D0 replay, which E2's critic rated low value [F/E2/critic-result.json `missing` 10].

### T1-V: generator qualification (P l.64–69)
- **(f) The criteria contradict each other.**
  - Requiring difficulty 0.3–0.7 puts the same-text noise SD at 0.16–0.25 [F/D1/result.json `evidence`: SD2 0.159
    on the card, 0.222 on the scaffold]. At 80×2 the SE is then 1.8–2.8 points, so a *perfect* generator fails
    "A1−A0 within ±2" 27–48% of the time.
  - A saturated panel passes the ±2 test (E9's generated null SD was 0.06) but fails the difficulty window.
- **Prior attenuation is far below the bar.** Earlier generated panels showed 0.23 (E9) and 0.27 (E2 window) of the
  real LiveMath-card harm on OfficeQA, against the ≥0.5 required [F/E9/result.json `evidence`, G/R ratios].
- **No generator has reached the difficulty window.**
  - D6's OfficeQA-style items were solved 14/14, against ≈22% on real OfficeQA [F/D6/result.json `pilot`].
  - Generated tables run 491–914 characters, while the real median is 7,755 [F/E1/critic-result.json R8].
  - All 23 of E1's kept items came from 3 distinct tables [F/E1/critic-result.json R1].
- **Prior evidence points the other way.** The 10/15–10/16 ledger already found generated items to be a biased
  transfer measure [F/E1/critic-result.json R6].
- **(c) Owner re-registration is needed** for three things [F/D6/critic-result.json, re-registration item]:
  - qualifying against OfficeQA training data;
  - drawing items from the real OfficeQA (Treasury) corpus, which is also the test pool's source;
  - checking test-hash overlap.
- **(b) Cost is overestimated.** It is ≈1.7M, not 3.3M, because generated cells cost 670 / 1,294 tokens
  [F/E9/result.json `cost_estimate`]. This is harmless, and engineering is about 1 week [F/D6/result.json
  `cost_estimate`].
- **Net: qualification is unlikely.** Since T1-V is the proposal's only live thread for objective 1, objective 1 is
  in practice paused.

### T2: single-source evolution (P l.71–77)
- **(a) Pool.** Three steps per chain use the 600-item pool exactly [F/E2/critic-result.json R3]. Only 59 items were
  never used [F/E5/critic-result.json `missing` 7].
- **(b) Cost.**
  - The 56M is plausible to generous. E2's 27.9M per chain is 3 × v3's measured 9.29M SearchQA step
    [F/E2/result.json `cost_estimate`; F/E3/critic-result.json R3].
  - D1-style steps cost ≈5.5M, plus +4.72M once for the round-1 duplicate and placebo
    [F/D1/result.json `cost_estimate`: 34.13M → 38.85M].
  - Estimate: 42–56M.
  - Minor correction: D1's 4.72M round is *estimated*, not measured ("D1 is estimated, v3 is measured").
- **(f) Power.**
  - At 300×2, power is ≈0.45–0.6 for +3 points and ≈0.25–0.35 for +2 [F/D1/result.json n80 table: 487/733 items
    for +3, 1,016/1,637 for +2]. Headroom over the card is 0–3 points [D9, as cited in F/E8/critic-result.json `refuted_claims` 7].
  - Type I error is 0.035–0.057 per decision, and the winner's curse inflates accepted estimates 1.34–1.51×
    [F/D1/result.json `evidence`].
  - With up to 6 decisions, there is ≈15–25% chance of a false acceptance under a global null, and each false
    acceptance triggers a T3 costing ≈93–120M (see R12).
- **(c) Placement is undefined.** A rule under the SearchQA "Applies when" header is inert elsewhere by design
  [F/E7/critic-result.json `missing`]. Placement cannot be "decided on SearchQA evidence", because both placements
  act the same on SearchQA. If every accepted rule lands in the SearchQA section, T3 measures text-presence bleed,
  not learned transfer. The placement policy must be registered.
- **(c) Owner reading of "no validation set".** The claim "no validation set by construction" (P l.96) depends on the
  owner treating D1's fresh labelled SearchQA acceptance batches as allowed [F/D1/result.json `risks` 11]. It needs
  explicit confirmation.
- **(e) Engineering.**
  - The stage-to-bench mapping is hard-wired: 127 `ORDER` occurrences in 15 files; `bench = ORDER[stage-1]` in
    `step.py` and at `baseline.py:93` and `:268` [F/E2/critic-result.json `confirmed_claims`].
  - Plus the D13 proposer, the firewall and hash audit, and the B5/B17 ports.
  - This is several Codex-reviewed items.

### T3: sealed confirmatory transfer (P l.79–90)
- **(a) Items** are the full test pools. ALFWorld gets the seeded half, 1 run, and 3 arms, so its MDE is ≈11–16 points
  (from E5's 8.0 at 134×2): a gross-harm check only.
- **(b) Cost.** 75M holds for 6 arms at median rates. Corrections:
  - rule (g): +2 placebo arms;
  - rule (e): +G-start;
  - mean-versus-median rates;
  - computing-mode OfficeQA.
  - Corrected: **≈93–120M**.
  - Savings available:
    - I5b with 1 run on SearchQA + OfficeQA only, ≈3M instead of 8.9M. That still detects the −7.0 canary artefact E2
      saw [F/E2/result.json `risks` 2].
    - If a chain is unchanged, its "final" is I5 and should not be run twice: −9M, plus −7M on ALFWorld.
- **(c) Protocol: this is not the first read** (see R8).
- **(c) "Within one regime" is ambiguous.** If either regime counts, that is two tests. Pre-specify the
  computing-mode regime as primary.
- **(f) Reachability.**
  - F̄ averages both finals. If only one chain changed, the effect halves.
  - At an optimistic true +3 points, P(self ∧ no-drop ∧ above both placebos) is ≈0.3–0.45 with one changed chain and
    ≈0.55–0.65 with two. At +1.5–2 points it is ≈0.1–0.3.
  - No-drop at a true zero passes ≈0.72 (power 0.8 × four per-target guards at 0.975⁴).
  - M is set by power. For the pooled LiveMath + SpreadsheetBench readout it comes to ≈4 [F/D6/critic-result.json
    `refuted_claims` 3] or ≈5 (E5's per-bench components). Either way, the owner must accept M on substantive
    grounds.
  - The LiveMath meta option is the key by design in test items too [F/D7/critic-result.json, citing the benchmark
    paper §2]. Whether meta items are included must be fixed in advance; without them LiveMath has ≈68 test items
    (estimated from the 129/283 training share).
- **(c) Baselines.** GEPA and SkillOpt are absent, so even a positive row cannot be compared with existing methods. On
  deepseek these baselines do not exist yet [F/E7/critic-result.json `missing`]. Their optimisation costs about 11M
  per source [F/E2/critic-result.json R2], plus about 9–11M per T3 arm.

### Totals and time (P l.92)
- **Cost.** ≈37–46 (T1) + 1.7 (T1-V) + 42–56 (T2) + 93–120 (T3) ≈ **175–225M charged deepseek**, plus ≈8M GLM, plus
  content-judge GLM tokens.
  - The proposal compares its total with v3's 139M, which is a ledger figure [RL l.142].
  - Ledger exceeds delivered by 1.15× (E2's I5 sweep, 18.6M versus ledger 21.3M [F/E2/result.json `cost_estimate`])
    up to ~2× (cal-1).
- **Dispatch time.**
  - Throughput at ≤6 workers is ≈3.4–4.8M tokens/h: 523M takes 4.5–6.5 days [F/E2/critic-result.json `missing` 3],
    or ≈880 cells/h [F/D1/result.json `risks` 10].
  - That gives T1 ≈8–14 h, T2 ≈9–16 h, T3 ≈19–35 h; ≈36–66 h of dispatch in all.
- **What fits in 1–3 overnight sessions.** Only:
  - the T0 engineering: scoring version and content scorer, item-blocked dispatcher, sentinel, R8 and the exact test,
    the B7 and B13/P7 ports, registrations, each with one Codex review round;
  - optionally, a small SearchQA calibration.
- **Constraints on long runs.**
  - Workflow agents are limited to <45 min and restart from scratch after a 5-hour usage limit, so dispatch must be
    detached on Linux.
  - T3 also needs owner consent to read the test pools.
- **Overall.** The proposal's own 4–6 weeks is realistic.

---

## 2. Refuted or corrected claims

| # | Claim (proposal) | Why it fails | Source |
|---|---|---|---|
| R1 | T1 ≈35.7M = "1.3× cal-1's 27.5M", cap 45M (l.56, l.60) | Delivered/median rates versus a ledger total. Like for like ≈2.5× cal-1; charged ≈37–46M reaches the cap. cal-1 paused on its cap for the same reason. | F/E7/critic-result.json R8; cal1-registration l.113–131; F/E9/critic-result.json R6; F/E5/result.json `cost_estimate` |
| R2 | T3 ≈75M; total ≈170M (l.83, l.92) | Rule (g) fires ≳90%: +2 arms. Rule (e) likely adds G-start. Mean rates and computing-mode OfficeQA add more. T3 ≈93–120M; total ≈175–225M. | F/D1/result.json `evidence`; F/D11/critic-result.json R6; F/D12/result.json `cost_estimate` |
| R3 | "Similar improves" needs ≥6 points (l.18, S7) | 6.3 pools all 172 items. A per-regime readout halves n (≈8.9 at 50/50), and "either regime" needs a multiplicity correction. | F/E5/critic-result.json R4; F/D11/result.json `evidence` |
| R4 | A7 (v1 GEPA text) is a known-harm control (l.58) | The −7.8 came from the GLM solver, a whole Skill against blank, on the test pool. T1 uses deepseek and places it inside I5's SearchQA section, where its effect is unknown (0.0 ±16.7 at 24 items). Selecting an arm on a test result is test-adaptive. | RL l.173; F/E2/critic-result.json R9, R11, `missing` 10 |
| R5 | T1-V can qualify a panel (l.64–68) | The ±2 criterion fails a perfect generator 27–48% of the time at 0.3–0.7 difficulty. Prior attenuation was 0.23–0.27, against ≥0.5 required. Generated OfficeQA-style items were solved 14/14 and use short tables. | F/E9/result.json `evidence`; F/D6/result.json `pilot`; F/E1/critic-result.json R1, R6, R8 |
| R6 | The regime "flips about hourly"; rule (b) finds a computing window (l.13, l.61, l.106) | Spells last 30 min to 7.5 h; 8 of 9 v3 OfficeQA units were answer-only. T1 can miss computing mode altogether, and rule (c) is undefined for two windows in the same regime. | F/D11/result.json `evidence`; F/E9/critic-result.json R4 |
| R7 | Identical twins ≥120 s apart (l.44) | E4's "0 flips at ≥120 s" holds only for the scaffold; card arms flip more when lagged (11/106 vs 6/94). Agreement is 0.88 at 1–10 min and 0.74 beyond 1 h. | F/E4/critic-result.json R2; F/E2/critic-result.json `confirmed_claims` |
| R8 | T3 reads the test pools once (K4, l.96) | v1's test scores on the same denominators (400/172/125/204/134) were opened 10/19, and this design uses them (C1, A7). v3's step-wise test scores exist under seal. project-status l.117 "未读" (unread) is stale. D10's audit competes for the same pools. | RL l.173; docs/project-status.md l.117–119; F/D10/critic-result.json R2 |
| R9 | Without owner sign-off, T1 falls back on archived E2/E4/E9 target cells (l.96) | The archives hold whole cards (1.8–2.9 KB) on mostly the scaffold, no I5 + rule-sized arms, and no same-window twin, placebo or H arm on targets. Rules (b), (d), (f) and (g) cannot run. | F/E9/critic-result.json R3; F/E4/critic-result.json R4; C6 |
| R10 | Add B5/B7/B13/B17 in T2 (l.73) | B13/P7 rewrites the framing sentence of every request, and B7 changes the format predicate. T1's calibration would belong to the old prompt. Move B7 and B13/P7 into T0. | v4 spec l.69–75, l.99–103; F/D5/critic-result.json `missing` 3 |
| R11 | "Learned transfer" label on content scoring (l.88) | Content scoring is undefined for LiveMath, SpreadsheetBench and ALFWorld. On SearchQA the card's effect under sub_em is ≈0 on deepseek; about 73% of strict-EM failures are acceptable answers, and substantive errors total ≈6 points. The judge audit was done by a model, not a human. | F/E6/critic-result.json M4, R6; F/E7/critic-result.json R5; F/D9/critic-result.json R4; F/E10/critic-result.json R6 |
| R12 | "T3 runs only if some final differs from its start" (l.76) | Up to 6 decisions at α 0.035–0.057 each: ≈15–25% false-trigger risk under a null, and a winner's curse of 1.34–1.51×. | F/D1/result.json `evidence` |
| R13 | D1's "measured" acceptance round 4.72M (l.75) | It is an estimate priced at v3 receipts; round 1 with a duplicate and a placebo is ≈9.4M. | F/D1/result.json `cost_estimate` |
| R14 | T1-V ≈3.3M (l.67) | Generated cells cost 670–1,294 tokens, giving ≈1.7M. Harmless overestimate. | F/E9/result.json `cost_estimate` |

## 3. Confirmed

These claims check against their sources: C1–C9, C13–C16, C18–C26, C28–C32, C34–C44, and all cell arithmetic.

Caveats:
- **C1** was measured with the GLM solver.
- **C11** uses variance components measured against the scaffold, and a card parent may need fewer items
  [F/E5/critic-result.json R5].
- **C12** is an estimate.
- **C17**'s rates are answer-only-mode medians.
- **C26**'s "unread" wording is stale.
- **C27**'s 4.72M is estimated.
- **C33**'s per-cell average mixes real and generated cells.

Further confirmations:
- **S1.** v4 excludes version acceptance and any test-side change [spec l.177–178].
- **C44.** The hard-wiring is real [skillopt/coevo5/step.py l.198, also l.321/502/645/767/818/833; baseline.py l.93, l.268].

## 4. Suggested re-ordering (same science, less money at risk)

1. **T0.** Include the B7 and B13/P7 ports, the dispatcher, the sentinel and a frozen content-score definition. Freeze
   all T3 rules here, with M taken from archived components (E5/D11/E2).
2. **T1-S.** SearchQA only: A0, A1, A2, A3 and A6 at 120×2, which is 1,200 cells, ≈4.7–5.6M. This decides rules (a)
   and (e), and it is D1's suggested pilot plus controls.
3. **X6 from the start.** Make X6 mandatory and register the placement policy. This removes rule (d)'s T2 branch and
   the target-data input into T2's machinery.
4. **T2** as proposed. Choose and register either an explicit acceptance of the false-trigger risk or a Bonferroni
   bound.
5. **Only if T2 accepted a version:**
   - T1-target with A0/A1/A2/A3/A5, OfficeQA scheduled by the sentinel in computing mode, ≈17–21M;
   - then T3, with 4 placebos and I5b reduced.

If nothing is learned, this saves ≈30–40M; if something is, the cost is about the same. T1-V stays off the critical
path.

## 5. 给综合者的更正（corrections_cn，可原样采用）

1. 【费用口径与上限】T1（方案第二步“用效果已知的文字标定量尺”，代号tcal-1）估的3570万token是按每题实际送达token的中位数算的；拿来比较的cal-1（10/20做的校准实验）2750万却是账本结算数，含为失败重试预留而没退回的额度，cal-1实际送达只有约1400万。同一口径下T1约是cal-1的2.5倍，不是1.3倍。按平均数并考虑OfficeQA（财政文档问答）在“边算边写”服务模式下每题多约3600 token，T1实际计费约3700万–4600万，已碰到4500万上限；cal-1当初正是因为实际成本是估计的两倍而中途触顶暂停。改为：上限至少设为送达估计的2倍（约7000万–8000万账本token），或先修好“失败调用的预留额度不退回”的记账问题。
2. 【总费用】把“共约1.7亿token”改为“约1.75亿–2.25亿（按计费算，账本数可能更高），约为v3（第3版协同进化实验，账本1.39亿）的1.3–1.6倍”。原因：T1的规则(g)（任一无关文字对照让某个数据集变动超过2分，T3就把无关文字对照从2个加到4个）在这些题量下几乎一定触发——同一段文字重跑的抽样误差本身就有1.5–3.5分，SearchQA上已经观察到一个无关文字对照变动−2.3分；规则(e)很可能让T2从G-start（五张任务卡里把SearchQA那节换成三行通用说明的版本）起步，T3又多一组；再加上按平均数计价、OfficeQA“边算边写”更贵。T3因此约0.93亿–1.2亿，不是7500万。
3. 【“相似数据集变好”的门槛】方案说“从SearchQA出发，OfficeQA不到6分测不出”。6.3分是172道测试题合在一起算的；方案自己要求OfficeQA按服务模式（只报答案/边算边写）分开读，每种模式只有约一半的题，最小可检测差距约8–9分；若“任一模式成立就算”还要做多重比较校正。改为“约8–9分；事先指定以‘边算边写’模式为主读数”。
4. 【提示改动的顺序】v4（第4版计划）里的B13/P7会改写每次请求开头那句解题说明，B7会改变“答案格式违规”的判定。方案把它们放到T2（进化步骤）才加，而T1是在旧提示下标定噪声、无关文字波动和余量M的，换了提示这些数就不适用。改为：B7和B13/P7移到T0（不花钱的修复步骤），T1起全部用新提示；B5（带验证反馈重问一次）和B17（答案被截断时重发一次）可以留在T2。
5. 【A7不能当“已知伤分”的对照】A7是v1（第1版实验）里GEPA基线在SearchQA上学到的文字。它让SpreadsheetBench（表格操作题）掉7.8分，是在GLM-5.3解题模型、整段替换空白技能、在测试集上测到的；T1里换成deepseek解题、放进五卡的SearchQA小节（该小节写明“适用于SearchQA”，在别的数据集上按设计不起作用），效果未知（同类小样本测量为0.0±16.7分）。而且“因为它在测试集上伤过分才选它”本身用了测试集结果。改为：删去A7，或标为“探索性”、不进任何判据。
6. 【T1-V的资格判据】T1-V是“自动生成的仿OfficeQA题能否当否决检查”的资格考试，几条判据互相冲突、很难通过：要求空白技能通过率在0.3–0.7之间，而这种难度下同一段文字重跑在80道题上的误差有1.8–2.8分，“两份完全相同的文字差距在±2分以内”对一个完美的出题器也有约27%–48%的概率判不合格；以往的生成题只显示出真实伤害的0.23–0.27倍（要求至少0.5倍）；D6（类型化出题器方向）生成的仿OfficeQA题解题模型14道全对（真实OfficeQA约22%），生成表格只有491–914个字符，真实材料中位数7,755个字符；用OfficeQA真实训练题做资格考试、用OfficeQA原始文档出题，都需负责人重新登记。改为：把“±2分以内”改成“差值的95%区间包含0”，并事先写明它大概率不通过。
7. 【测试集不是“第一次读”】v1的测试成绩10/19已经经负责人同意打开，用的正是T3要用的同一批题（SearchQA 400、OfficeQA 172、LiveMath 125、SpreadsheetBench 204、ALFWorld 134）；本方案也用了这些结果（例如选A7、判断OfficeQA +20分来自答题写法）。v3每一步的测试成绩也已算出、只是封着。T3应写成“同一批测试题的再次读取，对v1结果有适应性”。project-status第117行仍写这些题“未读”，与10/19报告矛盾，需先更正。D10（写测量论文的方向）的审计也要用同一批测试题，两者冲突，需负责人决定。
8. 【花钱顺序】T1约3600万里有约2500万–3000万花在目标数据集标定上；若T2什么都没接受（方案自己说这是最可能的结果），T3不跑，这笔钱就白花了。建议：T0 → 只做SearchQA部分的小标定（A0五卡原样、A1完全相同的副本、A2/A3两段无关文字、A6合并后的v3规则包，120题×2次，约470万–560万，相当于D1建议的210万试验加对照）→ 从一开始就把X6（放进“通用”小节的规则必须通过“不改答题格式”的可执行检查）设为必须（不花钱，规则(d)对T2的分支随之取消）→ T2 → 只有T2真接受了版本，才做目标数据集标定（约1700万–2100万，OfficeQA由哨兵在“边算边写”时段触发）和T3。余量M和T3全部判据仍在T2开始前用已有存档的方差数据冻结。这样“什么都没学到”时可省约3000万–4000万，学到东西时总花费基本不变。
9. 【T2到T3的触发要控制误判】两条链最多做6次“是否接受”的判断，每次误接受率3.5%–5.7%（D1实测），在“其实什么都没学到”时约有15%–25%的概率至少误接受一次，从而启动约1亿token的T3；被接受的效果估计还会被放大1.34–1.51倍（“赢家诅咒”）。T3的自身提升检验会挡住错误结论，但钱已花了。二选一写进登记：(a) 明确接受这个风险；(b) T2每次判断用更严的标准（例如单侧显著性0.05/6），代价是检出力从约0.5降到约0.3。
10. 【“不掉分”主判据要写清】(a) LiveMath（数学选择题）里的“元选项”（大意是“以上都不完全对”的选项）按基准论文设计经常就是正确答案，测试题也一样；主判据要事先写明含不含这类题，不含的话LiveMath测试题只剩约68道，余量M升到约4.5–5分。(b) M是按“检出力够不够”倒推的（约4–5分），负责人需确认“其他数据集平均掉M分以内可以接受”本身是否合理。(c) 加上四个目标数据集“区间整体低于0就报警”的检查，在真不掉分时整个“不掉分”判据约72%能通过，要写明。
11. 【从G-start起步时的对照】若T2从G-start起步，进化出的规则很可能只是把任务说明卡的内容学回来（以往从空白出发的E-ds链，唯一过筛的规则就是在复述任务卡）；10/12已做过“在通用说明上再学一步”（+2.9分，区间[−1.1, +7.2]，未建立）。T3必须同时报告最终版相对I5（五张任务卡原样）的差距，主标题应是“是否胜过人写的任务卡”，并注明与10/12实验部分重复。
12. 【ALFWorld和副本组】ALFWorld（家务文字游戏）在T3里只测67题、1次、没有无关文字对照，却要约2200万token（约占T3四分之一），只能发现11–16分以上的大幅下降，应明确叫“大伤害检查”。完全相同的副本组I5b（发现发送流程出错的对照）可只在SearchQA和OfficeQA上跑1次（约300万，而非890万），仍能发现以往见过的−7分那种发送问题。若某条链什么都没接受，它的“最终版”就是I5本身，T3里不必再跑（省约900万，ALFWorld再省约700万）。
13. 【“按内容评分”先定义清楚】“学到的迁移”标签只在“按内容评分、相对起点版本也成立”时才给。必须在T0定义并冻结每个数据集的内容评分，并事先告诉负责人：LiveMath、SpreadsheetBench、ALFWorld没有“格式/内容”之分（内容评分就等于严格评分）；在SearchQA上，换成宽松评分后整张任务卡在deepseek上的效果约为0，严格评分判错的题里约73%其实答得对，真正答错的总共只占约6分。所以从SearchQA出发，“学到的迁移”几乎不可能拿到，最可能的结论是“格式迁移”或“未建立”。若内容评分用GLM模型当裁判，要计入GLM费用；之前“87%–93%站得住”的抽查是模型做的，不是人工。
14. 【目标1实际上暂停了，要负责人拍板】目标1是“技能和验证端的编码评分规则一起进化”。方案里X6是一次写好、不再进化的固定检查，T1-V又大概率不通过，所以目标1这几周实际上停了，必须作为负责人要决定的事项写明，不能写成“保留”。若负责人要保留目标1，最便宜的做法是：让验证端只在SearchQA训练题上进化“答案格式检查”（以往能留住的都是这类：月份年份、百分号、整句作答、括号别名），按能否预测事先冻结的评分标签决定接受，不碰任何目标数据集。
15. 【时间】未来1–3个通宵只够做T0：新评分版本和内容评分、按题成组交错发送、服务模式哨兵、R8和精确检验（D11提出的报告规则）、B7和B13/P7移植、登记文档，每项都要先过一轮Codex审查和离线测试；最多再加一个小的SearchQA标定。T1全量约需8–14小时连续发送；T2要先改代码（“第几步对应哪个数据集”写死在代码里，ORDER在15个文件里出现127次），再跑约9–16小时；T3约19–35小时，还要负责人同意读测试集。整个序列约36–66小时发送加工程，方案写的4–6周是现实的，但不在几个通宵之内。
16. 【没有目标训练题时的退路不成立】若负责人不同意用目标数据集的训练题做标定，退路“改用E2/E4/E9存档的目标数据”行不通：存档里只有整张任务卡（1.8–2.9 KB）的搬移，且大多加在空白技能上，没有“五卡＋规则大小文字”（规则一般约400字符）的组合，也没有同一时段的副本、无关文字和答题指令组；规则(b)(d)(f)(g)都无法执行，T1只剩SearchQA部分。应如实写明。
17. 【规则(c)(d)补全】规则(d)说“该目标在T3里成为主读数”，与T3已固定的主判据（SearchQA自身提升＋LiveMath和SpreadsheetBench合并不掉分）冲突，也没写多重比较怎么校正；若按第8条让X6从一开始就必须，这条分支可删去。规则(c)在两个OfficeQA时段落在同一种服务模式时没有定义；服务模式一段可持续30分钟到7.5小时，不是“大约每小时切换一次”，T1可能整晚碰不到“边算边写”时段，规则(b)就会把唯一的相似数据集降为“只描述”。改为：由哨兵触发，在“边算边写”时段补测OfficeQA。
18. 【规则放哪一节要事先登记】放在SearchQA小节（“适用于SearchQA”标题下）的规则，在其他数据集上按设计不起作用，T3量到的只是“多了一段文字”的影响，不是学到的迁移；而“放哪一节”没法用SearchQA的数据决定（两种放法对SearchQA效果一样）。改为：由提出规则的一方给每条规则标“通用”或“仅SearchQA”，标“通用”的必须通过X6，并事先登记这条规则。
19. 【缺少现有方法基线】T3里没有GEPA和SkillOpt（两个现有方法）。即使结果为正，也说不出比现有方法好。用deepseek解题时这两个基线还没有（只有GLM-5.3版）；补上需每个约1100万token的优化，再加T3里每组约900万–1100万。应作为负责人决定写明。
20. 【小的事实更正】(a) 两次完全相同请求的“孪生组”间隔“≥120秒”的依据已被推翻：带任务卡的组间隔越久翻转越多（10.4%对6.4%），间隔越久一致率越低（1–10分钟0.88，超过1小时0.74）；改为同一题组内、相隔不超过约10分钟。(b) “D1实测一轮接受检验花472万”应为“估算”；第一轮若加副本和无关文字对照约940万。(c) T1-V的330万高估了，生成题每次约700–1300 token，约170万，不影响结论。
21. 【只有一条链改动时的估计量】T3把两条链的最终版逐题平均。若只有一条链接受了改动，效果被减半：即使乐观假设真实提升+3分，“自身提升＋不掉分＋高于两个无关文字对照”同时成立的概率也只有约0.3–0.45（两条链都改动时约0.55–0.65）；真实+1.5–2分时只有约0.1–0.3。应事先写明这种情况下用哪个估计量（例如只检验改动过的链、按链数校正，平均值作次要读数），并把这些通过概率告诉负责人。

## 6. 仍然站得住的部分（what_survives_cn）

诊断基本正确：至今没有测到“学到的文字”跨数据集迁移；v1（第1版实验）的“迁移成功”来自答题写法；v3（第3版）一条规则都没收下，相似检查一次没跑；登记的“相似”关系都指向OfficeQA（只有74道训练题，同一段文字换个时段能差20多分）。“v4（第4版计划）原样不该是下一次付费实验”成立（v4计划明确不含整版接受和测试侧改动）。以下做法都应保留：不在其他数据集的训练题上筛规则（否则就是变相的验证集）；以五张任务卡（I5，官方给每个数据集写的任务说明）为参照、同一时段逐题交错发送；至少两段无关文字对照；测试集只在冻结后、经负责人同意读取；按D1的方法整版接受（每步新抽训练题，单侧下界大于0且至少高2分）；T0不花钱的修复；只在SearchQA（检索问答）上进化；事先承认最可能的结果是“自身提升小或没有、不掉分、相似未建立”。T1和T3每组的题数和token算术本身是对的。需要改的是：费用口径与上限、几条判据的可达性、提示版本的先后、测试集读取的说法、花钱的先后顺序，以及目标1的暂停必须由负责人拍板。
