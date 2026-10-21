# Critique: feasibility, cost and protocol of `proposals/instrument.md` (量尺优先)

- Critic: adversarial feasibility / cost / protocol critic. Written 2026-10-21.
- Scope: every experiment in the proposal's §3 sequence (S0–S4), plus the Stop/Keep/Change items that drive them. Each is checked on (a) item counts and power, (b) cost, (c) protocol, (d) duplication, (e) time and (f) decision rules.
- Method: read-only. I made no model calls and used no SSH. I opened no test pool and no file with a test-style name.
- Every number is either quoted from a named source or recomputed by me (marked CALC; the formulas are in §11).
- Evidence labels:
  - RUN: archived real model run.
  - PILOT: paid feasibility pilot.
  - CRITIC: a critic's re-analysis.
  - DOC: registration, spec or status text.
  - SIM: simulation.
  - CALC: my own computation.

**Verdict: needs_revision.** The lens is right. The plan built on it has four problems:
- It spends too much too early.
- Its positive controls are partly circular.
- It is protocol-unsafe in three places.
- It cannot be executed in 1–3 overnight sessions.

## 0 白话结论（给综合者）

这份方案的大方向是"先把量尺修好，再谈方法"，这一点有实测支持，可以保留。但方案有四类问题。

1. **有三条事实写错了。**
   - F18 说"安慰剂只放在空架子上"，这不对。D1 试点（"按版本、在新题上验收"的探索）已经把两段无关文字加在五份任务卡上测过。
   - F17 说"还没有'任务卡＋学到的规则'的读数"，这说过头了。v3（10/19–10/20 跑完的第 3 版正式运行）里，I-ds 链（从五份任务卡出发的学习链）的每条规则都是加在任务卡上测的，结果都接近 0。
   - F21 说"GLM 求解器上学习有 +4.6/+6.7 的增益"，这用错了对比。
2. **先后顺序不划算。** S2 加 S3 约 5,000 万计费 tokens（约 8,000 万账本 tokens），要回答的核心问题是"学到的规则在任务卡之上有没有增益"。针对这个问题，D1 和 E8 已经设计好了只要 200–400 万 tokens 的决定性小试验，应该先做这些。
3. **有三处协议不安全。**
   - S3 的 300 道验收题要用 3 次，而且从不放回当提案材料，这等于一个固定验证集。执行者不能自己把它"登记为例外"。
   - S1 用 OfficeQA 的标注答案挑提示词，而 OfficeQA 是 SearchQA 唯一的相似数据集；S4 又在同一批题上读迁移。
   - 训练按"内容"打分、测试按官方打分，但没有事先写好"格式不能变差"的限值。
4. **有几条决定规则要么结果早已注定，要么是循环论证。** S1 的花费被低估，会顶到上限。整个序列需要 6 周，不是 1–3 个夜间会话。

## 1 Facts in the proposal that do not hold

| # | Proposal claim | Finding | Source |
|---|---|---|---|
| R1 | F18 / §1(c): "every placebo sat on the scaffold"; Keep 5 treats "≥3 placebos on the card" as a new requirement | **Refuted.** D1's paid pilot used 130 never-used SearchQA items × 2 runs × 6 arms, for 2,388,219 tokens. It put two length-matched placebos on the five-card Skill: 0.000 and −0.023, both rejected (hex-colour LB −0.027; recipe LB −0.054). It also ran a byte-identical copy: +0.004, with a per-item SD at 2 runs of 0.159. The D11 critic #7 and D10 critic R4 statements behind F18 missed this pilot. | D1/result.json `pilot` (PILOT); D11/critic-result.json refuted #7 |
| R2 | F17 / §1(c): no "card + rule" arm exists | **Overstated.** Every v3 I-ds rule was gated on the card parent. On full focal panels (optimistic, because each rule's own evidence items are included), SearchQA readings are +0.000 [−0.036, +0.036], +0.004 [−0.019, +0.026] and +0.015 [−0.011, +0.044]. All 7 I-ds rule arms fall between −0.107 and +0.005 on their check halves. v1 I-glm and v3 I-ds accepted 0 rules across 10 stages. What is missing is only a powered card+rule test on fresh items, and D1 and E8 already designed one (§5). | D9/result.json evidence E (RUN re-analysis); D1/result.json replays; E2/critic-result.json R4 |
| R3 | F21 and fallback (3): "a solver regime where learned − generic was +4.6/+6.7 (GLM)" | **Misapplied.** +4.6 (gen17) and +6.7 (fg17, fromempty − parent) both compare one Skill learned from EMPTY against the three-line generic instruction. They are two readings on the same reused development pool: fg17 used gen17's training rows and the same held-out 242 items. gen19's version of the same contrast is +2.9 [−1.2, +7.3]. The owner's actual contrast is learning on top of a reasonable instruction. On GLM that was +2.9 [−1.1, +7.2] (fg17, "没有建立"), and on 975 fresh SearchQA items it was **+0.1 [−1.6, +1.8]** (lz − bzero, 10/13). The GLM regime does not offer a learned increment over a good instruction either. | docs/results-and-lessons.md L139, L222 (RUN); docs/project-status.md L156, L167 |
| R4 | F33 / S1: an OfficeQA five-card cell costs 8.4k charged, so S1 ≈ 9.3M | **Understated for the windows S1 needs.** 8.4k, and v3's 7,927, are averages dominated by answer-only sessions (8 of 9 v3 OfficeQA units ran answer-only). Five-card OfficeQA cells in computing or verbose windows cost more: 9,944 (E8, 10/21); about 10.5–11.2k (E9 critic R6: one-card 8,200–8,856 plus about 2,300 for five seeds); 9.4k (D12, verbose session). B2 deliberately induces computing replies. | E8/result.json; E9/critic-result.json R4, R6; D12/result.json cost (PILOT) |
| R5 | S0 pivot: "if re-scoring flips any I-ds verdict or moves ids-full by >3 points" | **Cannot fire on SearchQA.** In the I-ds s1 parent and its 3 screened rules, the tag share is 1.000 with 0 JSON replies; ids-full's is 0.999. JSON-aware re-scoring moves ids-full's cal-1 effect from +9.4 to +7.8, a change of 1.6 points, under the 3-point trigger. The outcome is predetermined. | E7/critic-result.json #1; E7/result.json F, H (REPLAY) |
| R6 | Change 5 / S2 Row A: card-minus-bullet add-backs as the positive control; "detection 0.001 → 0.965" | **Circular or vacuous.** The add-back effect (P vs A_j) is the same contrast on the same cells as "A_j's CI excludes 0", so that clause nearly implies acceptance. If the bullets are inert, no A_j qualifies and the clause is empty. There is no independently known effect, unlike cal-1's ids-full (test 331 vs 289 of 400). The 0.001 → 0.965 figure is for switching the whole card on or off (card vs scaffold ≈ +16 points), so it only validates large effects. | cal1-registration L42, L137–146 (RUN); D8/critic-result.json R2 (SIM); D1 pilot card − scaffold +0.162 |
| R7 | "Answerable after the fix: learned − card at ≥3–4 points on SearchQA" | **≥4 is the honest floor.** At 300 × 2, per-decision power for a true +3 is 0.48–0.62 by D1's own simulation (n80 = 487 / 733 items) and about 0.67 under the E5 proxy (τ 0.191). For +2 it is 0.29–0.40. D1's smallest certifiable effect is 0.042. Accepted effects are inflated 1.34–1.51× (winner's curse). | D1/result.json evidence [E] (SIM); E5/critic-result.json #5; CALC §11 |
| R8 | S3: "registered exception: no method role has seen them" | **Not the executor's to register.** The 300 items serve S2 and then up to 3 acceptance decisions, and never become proposal material, so they are a held-out partition for the stage. v6 §2.2 says the method sets up no separate held-out validation partition and redraws the check half every step. The D7 and D8 critics call a panel reused at every step a de facto fixed validation set. D1 does allow "at most 3 steps per stage reuse one batch", but in the same design it says selection items are "redrawn every step … go back afterwards … can later become proposal material". D1's risk 11 also notes that a strict reading rejects D1 too. This needs an explicit owner decision. | coevo5-registration-v6-20261017.md §2.2 (DOC); D8/critic-result.json R4; D7 critic; D1/result.json design and risk 11 |
| R9 | S3: "Learned − card established (training side) iff an accepted version beats the card again next round" | **Not a replication.** The same 300 items are used, so the item-level component and the selection inflation both remain; only run noise is fresh. D1's own recommendation says "Effect sizes come from the test evaluations, not the acceptance estimate." | D1/result.json recommendation and [E] |
| R10 | S1 B1: "answer contract at both ends (E7 critic: safe)" | **Untested.** The E7 critic's "is safe" is reasoning, not a measurement. No arm with the contract stated at both ends was ever run. | E7/critic-result.json #3 |
| R11 | S2 "free add-on: replay of v4's C1 on the add-backs" | **Neither free nor defined.** In v4, C1's trigger set comes from P1's applicability judge (GLM, 3 votes per rule × check-half item). Change 7 defers P1, and without P1 the replay is just v3's C1. Card bullets also have no `when` condition to judge. | docs/handoff/v4-plans-20261021/spec.md P1 (≈L127–140), L177–178; proposal Change 7 |

## 2 (a) Item counts and detection power

### 2.1 Pools

**SearchQA**
- The 600 items break down as 200 v3/cal-1 focal + 31 regression + 130 D1 pilot + 180 E5-P1 + 59 never used (E5/critic-result.json #7).
- E8 also evaluated 100 items drawn from the 400 outside v3's draw (E8/result.json). Its overlap with the D1 and E5 items is not recorded, so the never-used count is **at most** 59.
- S2 (300) plus S3's proposal batches (200 + 100) use **all 600**. Nothing is left for a replication, a regression panel or a re-run of a placebo.
- "No method role has seen them" can only be asserted from a per-item usage manifest. No such manifest exists yet, so S0 should produce it.

**OfficeQA**
- The 74 items have already been reused by four pilots (placement, row, E4, E9): a de facto development set (E2/critic-result.json missing #7).
- S1 adds a tuning use, and S4 then reads the same items again.

**Other benches**
- SpreadsheetBench's judgeable training items number 91 (D1 risk 1; E5 critic #8), not 120 as v6 §2 lists.
- LiveMath has 129 of 283 items whose key is the meta option (D7). The non-meta content signal therefore rests on 154 items.

### 2.2 S2 Row A: "planted power ≥ 0.6 for +3 at 300 × 2" (CALC)

Under a normal approximation with one-sided α = 0.05, power for +3 depends heavily on how the effect is planted:

| Assumption | Paired SD | Power for +3 |
|---|---|---|
| Homogeneous planting (copy noise only; D1) | 0.159 | **0.95**: the clause always passes |
| Item × text heterogeneity τ 0.191 (E5 proxy) | 0.249 | **0.67** |
| τ 0.273 (D1's real-effect τ) | 0.316 | **0.50** |
| D1's own simulation (n80 487 mix / 733 mixchurn) | n/a | **0.62 / 0.48** |

Row A versus Row B is therefore decided by the unregistered planting model, not by S2's data. Under realistic churn (D4 critic R3: in scope, 10 up / 21 down), the lower end applies.

### 2.3 S3 (300 × 2 per decision, ≤3 decisions)

- **Power.** A true +3 is detected with probability 0.48–0.67. A true +2 is detected with probability 0.29–0.40, and at most 0.5 because of the "mean ≥ +2" clause.
- **Bounded negative.** If true effects are near 0, the pooled 95% upper bound over three rounds is about +2.0 to +2.7 under τ 0.19–0.27, or +0.9 with no heterogeneity (CALC). The pivot is reachable, but only when the true mean is at most about +0.3 to +1. A small positive true effect would leave it unresolved.
- **Prior.** Everything archived points to a yield near 0:
  - card+rule readings are about 0 (R2);
  - even an oracle that picks the best of 11 texts per item, selected post hoc, gains only +2.75 points [+0.6, +5.5] (D9/result.json D);
  - the E8 critic puts the headroom above the card at 0–3 points (E8/critic-result.json #7).

### 2.4 S1 (74 OfficeQA items × 1 run per window × 5 windows)

**Pure run noise.** The noise SD of a window mean is √(W/74), with W 0.081–0.095 (E9/result.json), so **3.3–3.6 points** (CALC). For the sample SD over 5 windows (df 4), the chance of meeting the "SD ≤ 5" rule is:

| True between-window SD | Chance the rule calls it stable |
|---|---|
| ≈3.5 (perfectly stable variant) | 0.91; a stable variant fails 6–10% of the time |
| 8 | 0.18 |
| 11.4 (D12's session SD) | 0.06 |

**Selection rule.**
- Picking "the smallest of three SDs" between similar variants amounts to picking noise.
- The clause "mean ≥ B0 − 3" has a paired SE of roughly 2–3.5 points.

**Regime coverage.** No clause requires both serving regimes to appear. In v3, 8 of 9 OfficeQA units ran answer-only, while E2 and E9 ran in computing windows (E9 critic R4). All five windows may well land in one regime.

### 2.5 S4 (target training pools)

**OfficeQA (74 × 4)**
- The proposal's own smallest certifiable effect is 10.3 at 37 × 4, which scales to about 7.3 at 74 × 4. The E5 critic puts the SE of a 74-item OfficeQA fixture at 4–5 points.
- With the 10-point margin, "no drop" can only mean "no drop larger than about 10 points".
- "Transfer gain iff LB > 0" needs a true OfficeQA effect of about 7–10 points or more. It would have to come from a SearchQA package accepted at +2 to +4, so it is unreachable in practice.
- One text pair differed by +20.3 (SE 5.2) between sessions (E9 critic R4). A single-session readout can therefore be biased by the serving regime.

**LiveMath**
- The training pool (283) actually resolves better than the test set (125).

**ALFWorld**
- ALFWorld is absent from S4, so the owner's "no drop on dissimilar benches" gets no ALFWorld reading.
- The proposal does not say this.

## 3 (b) Cost, recomputed against measured actuals

| Stage | Proposal (charged) | Recomputed (charged) | Ledger (×1.56) | Cap | Note |
|---|---|---|---|---|---|
| S0 | 0 | 0 | 0 | — | engineering only |
| S1 | 9.3M | **10.4–12.4M** (1,110 cells × 9.4–11.2k) | **16.3–19.4M** (18–21.5M at attempt-1 ratio) | 19M | at or over the cap; a mid-design cap stop leaves windows incomplete |
| S2 | 19.7M | 19.6M (4,200 × 4,669) ✓ | 30.6M (≈34M at attempt-1 ratio) | 40M | fits; headroom 1.2–1.3× |
| S3 | 31M + ≈3M GLM | 31.0M (accept in round 1, card rides along) to **36.7M** (Row C placebo package every round) | 48–57M | 62M | fits |
| S4 | 14.5M | 14.9–17.0M | 23–26.5M | 29M | fits |
| **Total** | ≈75M | **76–86M deepseek + ≈3M GLM** | **≈118–134M** | — | about one v3 run (139,024,462 ledger tokens, results-and-lessons L142) |

How the S3 and S4 figures were built:
- **S3 arithmetic (CALC).**
  - Rollout: 100 × 2 × 4.7k = 0.94M ✓.
  - A two-arm round: 300 × 2 × 2 × 4.7k = 5.64M ✓. This matches D1's 4.72M receipts per 1,200-cell round, about 5.9M charged.
  - Round 1 has 4 arms (card parent, candidate, P′, placebo): 11.28M.
  - Rounds 2 and 3 have 3 arms with the card riding along: 8.46M each.
  - Total: 2.82 + 11.28 + 16.92 = 31.0M.
  - Row C adds a placebo package to rounds 2 and 3: +5.64M.
  - Candidates are longer than the card, which adds prompt tokens; this is not included.
- **S4 cell counts.**
  - OfficeQA: 888 cells × 9.4–11.2k.
  - LiveMath: 1,132 × 4.4k.
  - SpreadsheetBench: 364–480 × 4.3k.
- **SearchQA anchor.** 4.7k per cell is the upper end of the measured range: E8 I 3,825; E5-P1 ids-full 3,995; v3 I-ds 4,088 (D6 critic #5); cal-1 ids-full 4,669. The S2 and S3 figures are therefore conservative.

**The ledger ratio is unstable.**
- Across the whole of cal-1 it was 27,481,897 / 17.6M = 1.56.
- Attempt 1 ran 3,452 ledger tokens per cell (24,868,834 / 7,205). That is about 1.73× charged if charged tokens per cell were at the run average. Attempt 2 ran 1,622 per cell.
- Caps should therefore use the upper ratio (cal1-registration L113–117, L128–131; D5 critic #7; E7 critic #8).

**Uncosted items.** The proposal does not cost any of these:
- a smoke run for every new version (v3's step-1 smoke cost 4,691,573 deepseek + 438,362 GLM tokens; results-and-lessons L140);
- baseline reruns, needed for any new main table once the base prompt changes (proposal risk 7):
  - about 32M to re-measure the v3 table, and 46–66M per changed stage (D11 critic #6);
  - about 170M for SkillOpt/GEPA (E7 critic missing);
- a test readout, which is not planned at all. The option in correction 18(b) costs about 24–26M charged without ALFWorld. ALFWorld's 134 × 1 × 2 adds about 28–31M, at 105.7–116k per episode (D3; D11 critic #6).

## 4 (c) Protocol

1. **S3's acceptance batch is a fixed validation partition (R8).**
   - It needs explicit owner consent.
   - Otherwise, each batch may serve one decision only.
   - Fresh items could then come from never-sampled SearchQA source rows. Any such draw must exclude the test split and the unread blocks C and D (project-status L118). There is precedent: new blocks A and B were drawn on 10/12–10/13 (results-and-lessons L220, L222), so these must be excluded too.
2. **S1 tunes the base prompt on OfficeQA labels.** OfficeQA is the only similar bench of SearchQA (E9 critic R1; protocol.py L18–19).
   - B2 is an OfficeQA-only instruction, selected on training-item pass rates.
   - S4 then reads SearchQA-to-OfficeQA transfer on the same 74 items.
   - This conflicts with several existing rules and findings:
     - the owner's "不做按数据集的过拟合" (project-status L115);
     - v6 §2.2, "还没轮到的 bench：这条学习历史里还没用过它的任何真实题与标注";
     - D12 rec 3 (never sample the next benchmark's training pool before its own step) and D6 critic #8;
     - the E2 critic's de facto development-set warning.
3. **Training gates and tests use different scorers.** Gates use content scoring; tests use the official scorer.
   - A rule that makes the solver answer in JSON loses nothing in training but fails every affected test item (JSON replies pass 0/364 under the official scorer; D5 critic #1).
   - The "channel no-harm count" has no registered margin or power.
4. **S0 is predetermined on SearchQA (R5).** S0 also sizes S2 from v3-prompt archives, while S2 runs on the S1/v4 base. The noise must be re-measured under v4 (D5 critic missing #3). S2's n is in any case fixed by the pool (300), not by the SD.
5. **S4 needs a §2.2 amendment** to read target training pools, and those pools are contaminated (OfficeQA by four pilots plus S1). The protocol-native alternative is the frozen per-step test evaluation the owner consented to on 10/16 15:03 (project-status L119–120): tests are read only after the method and code are frozen, and are never used for design, selection or tuning. That alternative spends the holdout, so the owner chooses.
6. **Frozen protocols.**
   - Base-prompt changes (B13/P7, B1, B2) need a new version and new output directories. They break comparability with the v1 and v3 tables (the proposal's risk 7), and the reruns are uncosted.
   - F24 (the ALFWorld action guard) comes from D14, whose report is unfinished ([[BOTTOM_LINE]], [[ALF_CONCLUSION]] and [[SHEET_CONCLUSION]] are still placeholders) and unreviewed. S0–S4 never exercise it.
7. **Objective 1 is deferred by 4–6 weeks and redefined as "the instrument as an executable rubric".** That is an owner decision.
   - The owner asked for "rubric as code" on 10/14 (project-status L157).
   - The 10/15 studies found no difference between host-executed and model-judged checklists (+0.33 per block, p = 0.97). An executable rubric helped only at solve time, by +2.7 points (L169).
   - The September V2–V18 Coding-Rubric line produced 0 promotions in V4 (E10 critic missing #2).
8. **Objective 2 is weakly served.** The plan offers only S4. That readout is contaminated, resolves only about 10 points on OfficeQA, and has no ALFWorld row.

## 5 (d) Duplication

- **S2's P′ and Q arms enlarge D1's card-regime pilot** from 130 to 300 items. The pilot already supplies the sizing input that S0 is supposed to produce: copy SD at 2 runs of 0.159, card-regime discordance of 7.7% against 15.3% for the scaffold, and placebos on the card of 0.000 and −0.023.
- **The decisive question, whether a learned package helps on top of the card, has already been designed twice.**
  - D1's next pilot: the merged I-ds s1 package vs the five-seed Skill, 2 arms × 130 items × 2 runs, about 2.1M tokens (D1/result.json).
  - The E8 critic's upgraded test: 250–300 items × 1 run, plus a length-matched placebo on the card, interleaved, 3.4–4.1M tokens, detectable effect about 3.5–4 points (E8/critic-result.json missing #1).
  - These resolve about as finely as S2+S3, at roughly 1/12 of the cost.
  - E8's prepared script `scripts2/e8_arm_id.py` (100 items, 2 runs, no placebo, about 1.7M) is underpowered: it expects at most 5 discordant items, while a sign-test p < 0.05 needs at least 6 (E8 critic #7). It should not be run as is.
- **Learning on top of a good instruction has already been measured on GLM**: 0 ± 2 points on 975 fresh items (results-and-lessons L222), and +2.9 [−1.1, +7.2] in fg17 (L139).
- **S4's OfficeQA readout re-measures the noisy single-text session series** that D12 and E9 already established: 50.8 / 26.7 / 26.7 / 34.2%, SD 11.4.

## 6 (e) Time (1–3 overnight sessions; agents under 45 minutes; 5-hour limits)

**Plan length.** The plan itself spans six weeks (S0 in week 1 through S4 in weeks 5–6).

**Unscheduled engineering**
- v4 B-fixes: about 3 hours of agent work plus a Codex review, with 127 comments to handle, 18 of them blocking (overnight-report L38–39).
- M1, the D1 gate, a single dispatch mode, per-cell covariates and the re-scoring pipeline.
- Each piece has to be split into agent tasks under 45 minutes that write intermediate files. Two 5-hour limits each cost about 1.5 hours last night, and the agents restarted from scratch (overnight report §2 and lesson L140).

**Runtimes**
- S1: at least 3 calendar days.
- S2: about 4.8 hours (4,200 cells at 880 cells/hour with 6 workers; D1 risk 10).
- S3: about 6,600 cells, roughly 7.5 hours, plus GLM role time, across 3 sequential steps.
- S4: about 2,500 cells, roughly 3–5 hours, because OfficeQA cells are about twice as long.
- The new machine runs at most 6 workers and returns HTTP 429 (E2 critic missing #3).

**Critical path.** S0 → S1 → S2 → S3 → S4 is serial. S2 waits on S1 only because it takes "base from S1", yet S1's choice concerns OfficeQA.

**Realistic in 1–3 sessions**
- S0.
- v4 B-fixes plus M1, implemented and reviewed.
- One decisive pilot of 2–4M tokens.
- S2, only if it is decoupled from S1 and runs on the generic v4 base.

## 7 (f) Decision rules

| Rule | Fixed in advance? | Reachable / informative at the stated n? | Problem | Fix |
|---|---|---|---|---|
| S0 pivot | yes | cannot fire on SearchQA (R5) | predetermined | per-bench check; state S0's real outputs |
| S1 smallest SD ≤ 5 and mean ≥ B0 − 3 | yes | noise-dominated (§2.4) | uses OfficeQA labels; regime coverage not required | label-free criterion; require both regimes in B0; drop B2 |
| S2 Row D (P′ − P CI excludes 0) | yes | about 5% false alarm by construction | contradicts Stop 4; "fix" undefined | P′ descriptive only; dispatch judged by mechanical checks |
| S2 Row C | partly; the target of "recompute n" is unregistered | fires in about 5–25% of cases under a true null (CALC); card placebos already moved −2.3 (D1) | at +3 the recomputed n is about 515 (E7 critic #4), more than 300, so it collapses to Row B | register the target effect and power; admit Row C ≈ Row B |
| S2 Row A | partly; planting model unregistered | 0.95 vs 0.48–0.67 (§2.2) | branch set by modelling choice; add-back circular (R6) | register D1's churn model; independent positive control |
| S3 accept (LB > 0, mean ≥ +2) | yes | power 0.48–0.67 at +3 | fixed batch (R8) | owner decision, or one decision per batch |
| S3 "established" | yes | always reachable, but not independent | not a replication (R9) | drop; take effect sizes from an independent readout |
| S3 bounded negative | yes | reachable only if the true mean is at most about +0.3 to +1 (UB about +2.0 to +2.7 at a true 0) | undefined when a step yields no candidate; pooling across different candidates | define both cases; state the unresolved outcome |
| S4 no drop (margins 10 / 9 / 15) | yes | only large drops are detectable | weak, and no ALFWorld | state as "no drop > margin" |
| S4 transfer gain (LB > 0) | yes | unreachable in practice | — | drop, or move to the test readout |

## 8 Confirmed claims

**Confirmed against their sources**
- F1 and F2: cal1 L137–140.
- F4: D5 critic #1. F5: E7 result H. F6: E7 critic #1. F7: E6 R2. F8: E6 R3.
- F9: E9 R4. F10: D12. F13: D1 [E].
- F15: D9 critic #4, with one rater. F16: E7 critic #5.
- F19: D1 pilot. F20: L142.
- F22: spec L138 and L177–178. F23: spec L68–74.
- F25: D7. F26: E9 R1. F27: E2 R6 and the agreement figures 0.88 / 0.74.
- F28: D12. F29: E1. F30: E10 R4.
- F31: project-status L118, together with the owner's 10/16 consent at L119–120.
- F32: cal1 L129–130 and E7 critic #8.

**Confirmed with caveats**
- F11 measures candidate vs card, not card+rule.
- F12's 0.965 is a large-effect control only.
- F14's never-used count of 59 is an upper bound.
- F33 holds except the OfficeQA anchor in computing windows (R4).

**Arithmetic that checks out**
- S2 cost and runtime.
- S3's per-step rollout and round figures, and its 31M total.
- S4's 14.5M, which sits at the low end of my range.

**Diagnosis that checks out**
- The binding constraint is decision resolution, regime confounding and tiny fixed trigger panels, as shown by cal-1's C1 passage at n = 11 (75.8% for ids-full, 0% for rule-sized texts) and D8's per-step power of 0.19–0.26.

## 9 What survives

**The lens and diagnosis.**

**Stop list**
- Stops 1, 2, 3, 5, 6, 7 and 8 survive.
- Stop 4 is right; S2 Row D must be rewritten to obey it.

**Keep list:** all items survive.
- Keep 4 (D1 as the lead gate) should also state that its mechanics were validated only against a 16-point effect.

**Change list**
- Change 1 survives as a new-version diagnostic layer with a registered official/format no-harm limit.
- Changes 2, 3 and 4 survive.
- Change 6 survives for its LiveMath meta/non-meta split.
- Change 8 survives using the upper ledger ratio.

**Experiments**
- S0 survives as the zero-cost first step. Its real products are the item manifest, the E-ds re-reading and the regime covariates.
- The fallback "write the calibrated null as a measurement result without spending the holdout" survives.

## 10 Corrections for the synthesizer (plain Chinese; same as `corrections_cn`)

每一条都可单独照抄；第一次出现的代号都已在条内解释。

1. 更正事实 F18。说"所有安慰剂都放在空架子上"不对。
   - D1 方向是"按版本、在从没用过的新题上验收"的探索。它的付费试点用了 130 道从没用过的 SearchQA 训练题。
   - 试点把两段与任务无关、长度相当的文字（安慰剂）加在五份任务卡上测过，差别是 0.000 和 −0.023，都没被收下。
   - 试点还把同一段文字原样跑了两遍，差 +0.004。
   - 因此 S2 里的安慰剂臂和拷贝臂应写成"把 D1 试点从 130 题扩大到 300 题"，而不是"第一次测"。
   - 来源：docs/handoff/feasibility-20261021/D1/result.json 的 pilot 部分。
2. 更正事实 F17。说"还没有'任务卡加学到的规则'对任务卡的读数"，说过头了。
   - v3 是 10/19–10/20 跑完的第 3 版正式运行。其中 I-ds 链（从五份任务卡出发的学习链）的每条规则，都是加在任务卡上测的。
   - SearchQA 上三条规则分别是 +0.0、+0.4、+1.5 个百分点。上界最高 +4.4，而且偏乐观。
   - 7 条规则在各自检验题上的差别是 −10.7 到 +0.5 个百分点。
   - v1 和 v3 的这条链，10 步一共收下 0 条规则。
   - 真正缺的只是"在新题上、题数足够多"的这种对比。
   - 要写明：已有证据强烈预示 S3 一条也收不下。
   - 来源：D9/result.json 证据 E；D1/result.json 回放；E2/critic-result.json R4。
3. 更正事实 F21，并删除或改写备选方案第(3)条"换到 GLM 求解器，那里学习比通用指令高 +4.6/+6.7"。
   - 这两个数比的是同一份"从空白学出来的 Skill"减去"三行通用指令"。它们是在同一批反复用过的开发题上量了两次，不是两个独立结果。
   - 另一条学习历史 gen19 做同一对比，结果是 +2.9［−1.2, +7.3］。
   - 负责人真正关心的是"在合理指令之上再学一步"。这在 GLM 上是 +2.9［−1.1, +7.2］，没有建立；在 975 道新题上是 +0.1［−1.6, +1.8］（10/13 的主读数）。
   - 所以"GLM 上学习有增益"只在从较弱的手写指令出发时成立，不能作为换求解器的理由。
   - 来源：docs/results-and-lessons.md 第 139、222 行；docs/project-status.md 第 156、167 行。
4. 在 S2（第二步标定实验）和 S3（一次按版本验收的学习阶段）花大钱之前，先做一个已经设计好的决定性小试验，花费只要 200–400 万 tokens。二选一：
   - (a) D1 建议的"v3 I-ds 第 1 步合并后的规则包"对"五份任务卡"：2 臂 × 130 题 × 2 次，约 210 万 tokens。
   - (b) E8 审查人建议的升级版："任务卡加规则"对"任务卡"，再加一臂长度相当的安慰剂（加在任务卡上）。用 250–300 道 v3 学习时没用过的题，每题 1 次，三臂交替，约 340–410 万 tokens，能分辨约 3.5–4 个百分点的差别。
   - E8 现成的脚本 scripts2/e8_arm_id.py 只有 100 题、没有安慰剂（约 170 万 tokens），分辨力不够，不要原样跑。
   - 如果规则包效果的上界低于 +3 个百分点，应先请负责人决定：还要不要花约 1.2 亿账本 tokens 走 S1–S4。
5. S3 的验收批，对 SearchQA 这一阶段而言就是一个固定的留出验证集。
   - 这批题是 S2 用过的 300 道 SearchQA 题，要在最多 3 次决定里反复用，而且从不放回去当提案材料。
   - 登记 v6 §2.2 写的是"不设单独的留出验证分区"、"检验半每步重抽"。
   - D7、D8 两份审查也认定：每步复用同一组题，等于事实上的固定验证集。
   - D1 的设计虽然允许同一批题最多用 3 步，但同时要求：选择用的题每步从训练池重抽、用完放回，以后可以当提案材料。
   - 所以这不能由执行者自己"登记成例外"，必须由负责人明确同意。
   - 负责人不同意的话，每批题只做 1 次决定。下一步需要的新题，可以申请从 SearchQA 原始数据里从没抽过的行另抽；要排除测试集、还没读过的 c/d 块，以及 10/12–10/13 已经用过的 A/B 块。
6. 删掉"被收下的版本在下一轮再赢任务卡一次，就算学习增益成立"这条规则。
   - 下一轮用的还是同一批 300 道题，只有运行噪声是新的，所以这不是独立重复。
   - 题目层面的运气还在；"赢家诅咒"也还在：被选中的候选，效果会被高估约 1.34–1.51 倍（D1 的估计）。
   - 效果大小只能来自独立的读数。D1 自己的设计就写着："效果大小来自测试评测，不来自验收估计。"
7. S1（OfficeQA 答题方式定档实验）只比较对所有数据集都通用的写法。
   - 保留 B0（原样）和 B1（第 4 版新的开场句，加上答案格式在提示开头和结尾各说一次）。注意"两头都说"从没实测过，E7 审查只是推理说它安全。
   - 删掉只给 OfficeQA 加的 B2（"先写计算再写标签"）。
   - 挑选标准改成不看标注答案的指标：各时段"只给结果"回复的比例、回复长度、带标签的比例。不要用 OfficeQA 训练题的对错率来挑。
   - 理由一：OfficeQA 是 SearchQA 唯一的相似数据集，S4 又要在同样这 74 道题上读迁移。用它的标注调提示词，就是先把目标数据集当开发集用。
   - 理由二：这与负责人"不为某一数据集过拟合"的要求冲突，也与登记 §2.2"还没轮到的数据集，不用它的真实题与标注"冲突。
   - 理由三：这 74 道题已被四个试点反复用过（E2 审查缺失第 7 条）。
8. S1 加一条前提，并写明它的规则基本在挑噪声。
   - 前提：只有当参照写法 B0 在各时段里两种答题状态（"只给结果"和"写出计算"）都出现过，S1 的结论才算数；否则记为"未定"，延长时段。
   - 理由：v3 里 9 个 OfficeQA 单元有 8 个处在"只给结果"状态（E9 审查 R4），5 个时段很可能全落在同一种状态里。
   - 噪声有多大：74 题 × 1 次下，光是运行噪声就让每个时段的平均分波动约 3.3–3.6 个百分点。
   - 判错的机会：5 个时段时，完全稳定的写法有约 6–10% 的机会被"标准差不超过 5"判为不稳；真实波动 8 个点的写法，有约 18% 的机会被判为稳定。
   - 所以在几种相近写法之间"挑标准差最小的"，基本是在挑噪声。
9. 按实测重算 S1 的花费。
   - OfficeQA 五份任务卡在"写出计算/长回复"时段，每格约 9,400–11,200 计费 tokens（来源：D12、E8、E9 审查 R6），不是 8,400。8,400 和 7,927 主要来自"只给结果"的时段，而 B2 本身就会诱发长回复。
   - 1,110 格约 1,040–1,240 万计费 tokens。按账本约 1.56 倍算，是 1,630–1,940 万，已经顶到 1,900 万的上限。
   - 中途停下会让时段不完整，标准差就算不出来。
   - 上限至少提到 2,500 万，或者只留 B0、B1 两臂（740 格，约 700–830 万计费 tokens）。
10. 改 S2 的 D 行。
    - 现在的写法：拷贝臂 P′（与任务卡逐字节相同的文字）和任务卡 P 之差的区间不含 0，就判"派发坏了"。
    - 这与方案自己的"停止第 4 条"矛盾：两段逐字节相同的文字，区间按构造就有约 5% 的机会不含 0。
    - 改为：P′ 只用来报告噪声下限。"派发坏了"只按机械检查判定：请求哈希、请求顺序、并发分配、读不出结果的比例。
    - 还要写清：修好之后怎么办、是否重跑、花多少。
11. 改 S2 A 行里的阳性对照。
    - "去掉一条任务卡要点，再加回来"是循环的：加回的效果就是在同一批格子上量出来的同一个差，区间不含 0 时几乎必然被"收下"。
    - 任务卡的单条要点很可能本来就没作用：在 cal-1（10/20 的标定实验）里，把任务卡的句子加在空架子上，只差 +0.4 和 −3.0 个点。那样的话这一条件就是空的。
    - 改法一：换成有独立已知效果的对照，比如 cal-1 里的 ids-full，它在测试集上是 331 对 289（满分 400）。
    - 改法二：老实写明现有阳性对照（整份任务卡开/关，检测率从 0.001 到 0.965）只证明仪器看得见十几个点的大效应，看不见规则大小的效应。
12. 事先登记 S2"植入效应"的方式。
    - 若把效应均匀地植入（不考虑不同题目反应不同），300 题 × 2 次对 +3 个百分点的功效约 0.95，A 行这一条必过。
    - 按 D1 自己的模拟（考虑题目之间的差异，以及"有的题变好、有的题变坏"），功效只有 0.48–0.62；按 E5 的代理估计，约 0.67。
    - 也就是说，现在走 A 行还是 B 行，几乎由植入方式决定，而不是由数据决定。
    - 二选一：要么登记 D1 的模型，并接受"大概率走 B 行"；要么把目标改成"只验证 4–5 个百分点以上的效应"。
13. 写明 S2 的 C 行实际上就是 B 行，并补上"重算题数"针对的效应大小和功效。
    - 即使三段安慰剂真的无效，在 300 × 2 下，"任一安慰剂被收下，或与任务卡差 3 个点以上"也有约 5–25% 的机会出现。
    - 实际会更常见：D1 测到，加在任务卡上的安慰剂就差了 −2.3 个点。
    - C 行触发后要求"还要赢过安慰剂包"。按 E7 审查的标准差 0.243 重算，分辨 +3 需要约 515 道题，超过 300 道，按规则就落到 B 行。
14. 把"修好之后能回答的问题"改成"在 SearchQA 上分辨 4 个百分点以上的学习增益"，不是"3–4 个百分点"。
    - 按现有估计，300 题 × 2 次时，单次决定对 +3 的功效约 0.48–0.67，对 +2 约 0.3–0.4。
    - 被收下的效果还会被高估约 1.34–1.51 倍。
    - D9 还测过：即使事后在 11 段文字里给每道题挑最好的那段，也只多 +2.75 个点［+0.6, +5.5］。任务卡之上可学的空间本来只有约 0–3 个点。
15. 写明 SearchQA 的 600 道训练题已基本用尽。
    - 已用的：200 道被 v3/cal-1 用过，31 道是回归题，130 道用于 D1 试点，180 道用于 E5 试点。E8 另抽过 100 道，与前面是否重叠没有记录。
    - 所以从没用过的最多 59 道（E5 审查第 7 条）。
    - S2（300 道）加上 S3 的提案批（200 加 100 道）会把 600 道全部用掉，没有余量做重复验证、回归题组或安慰剂重跑。
    - S0 要先产出一张清单，列出每道题被哪些实验用过几次；有了这张清单，才能写"没有方法角色见过这些题"。
16. 写明 S0（零花费的重新打分）的转向条件对 SearchQA 基本不可能触发。
    - I-ds 回复的带标签比例是 1.000，ids-full（五份任务卡全文）是 0.999。
    - 按"JSON 也能识别"的方式重打分，ids-full 的效果只从 +9.4 变到 +7.8 个点，变化小于 3（E7 审查第 1 条；E7 结果 F/H）。
    - S0 的真正产出是三样：题目使用清单、E-ds（从空架子出发的学习链）结果的重读、每格的答题状态记录。
    - 转向条件改为按数据集分别检查，重点看只认标签的 OfficeQA 和 LiveMath 打分器。
    - 同时写明：S0 的噪声估计来自 v3 的提示词，S2 改用第 4 版提示词后要重新测（D5 审查缺失第 3 条）。
17. "训练时按内容打分、测试时按官方打分"要补一条事先写好的"格式不能变差"的限值。
    - 例如：候选版本里"官方打分器读不出答案"的比例，相对父 Skill 的单侧 95% 上界不得超过 +1 个百分点，否则不收。
    - 否则，一条让模型改用 JSON 作答的规则，在训练时不吃亏，在测试时全错：JSON 格式的回复按官方打分，364 条里 0 条通过（D5 审查第 1 条）。
18. 改 S4（迁移读数）。现在的问题有四个：
    - 它读目标数据集的训练题，这要改登记 §2.2。
    - 读的是 OfficeQA 那 74 道题：已被四个试点反复用过，又被 S1 拿来调提示词。它只能分辨约 7–10 个点，"迁移有增益"那一档实际上达不到。
    - 同一对文字在不同时段可差 +20.3 个点（E9 审查 R4），一个时段的读数可能被答题状态带偏。
    - 没有 ALFWorld 的读数，"对不相似的数据集不下降"就缺了一块。

    两种改法，选一种：
    - (a) 明确 S4 只能说"没有超过约 10 个点的下降"，删掉"迁移增益"那一档。OfficeQA 至少在两个时段读，并记录答题状态。写明不读 ALFWorld。
    - (b) 经负责人同意，改为方法冻结后一次性的配对测试读数：同一时段交替，带任务卡臂和安慰剂臂。
      - 依据：负责人 10/16 已同意主实验每一步都在测试集上评测，测试集只在方法与代码冻结后读（project-status.md 第 119–120 行）。
      - 测试集上能分辨的最小效应约为：SearchQA 3.7、OfficeQA 6.3、LiveMath 7.3、SpreadsheetBench 6.5、ALFWorld 8.0 个点（E5 审查第 4 条）。
      - 花费：不含 ALFWorld 约 2,400–2,600 万计费 tokens；ALFWorld 134 题 × 1 次 × 2 臂，另需约 2,800–3,100 万。
      - 代价：这会用掉测试集的"一次性"，之后任何改动都算看过测试。
19. 把总花费写全。
    - S1 约 1,040–1,240 万；S2 约 1,960 万；S3 约 3,100–3,670 万（C 行每轮都带安慰剂包时取上端），另加约 300 万 GLM；S4 约 1,490–1,700 万。
    - 合计约 7,600–8,600 万计费 tokens，按账本约 1.18–1.34 亿，接近一次 v3 正式运行（账本 1.39 亿）。
    - 还没算进去的：每个新版本的冒烟运行，参考 v3 第 1 步冒烟约 469 万 deepseek、44 万 GLM。
    - 还没算进去的：改了基础提示词后，要出新主表就得重跑基线。重测 v3 表约 3,200 万，每改一个阶段 4,600–6,600 万（D11 审查第 6 条）；SkillOpt/GEPA 约 1.7 亿（E7 审查）。
    - 各步上限按较高的账本比例设：cal-1 第一次每格约 3,450 账本 tokens，约为计费的 1.73 倍。
20. 改时间表。方案本身是 6 周，不是 1–3 个夜间会话。
    - 没排进时间表的工程有：
      - 第 4 版的 B 类 bug 修复：约 3 小时代理工作，加一轮 Codex 评审，要处理 127 条意见，其中 18 条是阻断。
      - M1 打分层、D1 验收门、单一派发方式、每格状态记录、重打分流水线。
    - 每块都要拆成 45 分钟以内、会写中间文件的代理任务；5 小时额度用完时，代理会从头重来。
    - 运行时间：S1 至少 3 个日历日；S2 在 6 个并发下约 4.8 小时（每小时约 880 格，D1 风险第 10 条）；S3 约 6,600 格，约 7.5 小时，再加 GLM 角色的时间。
    - S2 不要等 S1：S2 只用 SearchQA，S1 的选择只关系到 OfficeQA。把 S2 的基础提示词在登记时固定为第 4 版的通用写法，至少能省掉 3 天的串行等待。
    - 1–3 个会话里现实能完成的是三件事：S0；第 4 版 B 类修复与 M1 的实现和评审；第 4 条里的一个 200–400 万 tokens 的决定性试验。
    - 与 S1 脱钩后，S2 才可能放进第 3 个会话。
21. 写明这是负责人的决定，不能由计划直接定：目标一（Skill 与验证端的编码细则一起进化）推迟 4–6 周，并把"测量工具本身当作可执行的细则"算作目标一。同时列出已有的相关结果：
    - 负责人 10/14 要求"每个 Skill 一个细则、细则做成代码"（project-status.md 第 157 行）。
    - 10/15 的形式研究：由程序执行和由模型判定同一张检查清单，没有差别（每块 +0.33，p=0.97）；可执行细则只在求解时有一点用，+2.7 个点（第 169 行）。
    - 9 月的 V2–V18 编码细则系列，在 V4 没有任何晋升（E10 审查缺失第 2 条）。
22. 把 F24（ALFWorld 动作接口保护）标为"未审查的分析"。
    - 它来自 D14，而 D14 的报告没写完，结论段还是占位符，也没有审查人复核。
    - 把它从"改动第 6 条"移到"以后再说"；S0–S4 也从没用到它。
23. 删掉或改写 S2 的"免费附加"：在加回的要点上回放第 4 版的 C1 门（只看触发题的那道门）。
    - 第 4 版 C1 的触发题，由 P1 适用性判定决定：GLM 对每条规则、每道检验题投 3 票。
    - 计划的"改动第 7 条"把 P1 推迟了；不实现 P1，就只能回放第 3 版的 C1。
    - 任务卡的要点也没有"适用条件"可判。
    - 要写明用的是哪一版、要花多少 GLM tokens。

## 11 Method notes (CALC)

- **Power.** One-sided α = 0.05: power = Φ(δ·√n / SD_d − 1.645).
  - SD_d = √(SD_copy² + τ²), with SD_copy = 0.159 at 2 runs (D1 pilot).
  - τ = 0.191 (E5 critic #5) or 0.273 (D1 [E]).
  - From D1's n80: power(n) = Φ(2.487·√(n / n80) − 1.645).
- **Pooled S3 upper bound.** Three rounds on the same 300 items, giving 6 runs per arm: SE ≈ √(τ²/300 + 0.159²·(2/6)/300). This is 0.0122 at τ 0.191 and 0.0166 at τ 0.273, so UB ≈ mean + 0.020 to 0.027.
- **Row C null rates.**
  - Per Q arm, SE runs from 0.0092 (no heterogeneity) to 0.0144 (τ 0.191).
  - P(|Q − P| ≥ 0.03) is 0.1–3.7% per arm.
  - P(D1 accepts Q) is 1.5–5% per arm.
  - Over three arms, the union is about 4.7–24%.
- **S1 SD rule.** With df 4, P(s ≤ 5 | σ) = F_χ²₄(4·25/σ²), where F_χ²₄(x) = 1 − e^(−x/2)(1 + x/2).
- **Ledger.** Recomputed charged figures are multiplied by 1.56 (cal-1 overall). An attempt-1-like session would be about 1.73.
