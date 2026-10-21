# 止损与反方 · Stop-loss and devil's advocate

Lens: the most conservative route — what to stop, and the cheapest experiment that could change the decision. Tags: **[M]** fresh-item, pre-registered method-effect evidence; **[R]** real model run, pilot or calibration only; **[A]** archived replay or re-analysis. No test pool was opened. Bracketed numbers point to §6.

## 1. 诊断 Diagnosis

**1.1 "The instrument is the bottleneck" is half true.** Large effects are measured reliably: task card (TC) vs empty scaffold +9.4 points in cal-1 [1], +16.2 on 130 never-used items (D1) and +8.9 on fresh items (E5) [R; 2]; placebos *on the card* move scores 0.0 / −2.3 [2]. What cannot be seen is a 0–3-point effect — and every measurement of learned text on top of a good instruction lands there:
- 975 fresh SearchQA items (GLM-5.3): one learning step from the zero-shot instruction minus that instruction **+0.1 [−1.6, +1.8]**; learning from empty ≈ the instruction (−0.5); two validation-gated methods +0.1 / +1.0 [M; 3]. On 750 fresh items an earlier +2.7 did not replicate [M; 4]. Three solvers, real items: −1.8 to +0.6, n.s. [R; 5].
- v3 (deepseek, 139.0M tokens): **0 rules accepted** in 10 stage-steps [M, training side; 6]; its screened rules re-measured on the card: +0.0 / +0.4 / +1.5 on optimistic focal panels; D1's replay of 7 arms: −10.7 to +0.5 [A; 7].
- Gains appear only against *weak* starts. On the same 975 items, learned-from-empty beats a hand-written 3-line generic text by +4.7 [+2.2, +7.1] (consistent with the reused-dev-pool +4.6 [8]) and one step on that text adds +4.9 [+2.0, +7.8] — yet learned-from-empty vs the zero-shot instruction is −0.5 [−2.3, +1.2] [M; 3]. **Experience substitutes for a missing card; it has not been shown to add to a good one.**

**1.2 The residual headroom is mostly not learnable content.** SearchQA: ~73% of card failures are acceptable answers rejected by strict exact match, ≈6 points substantive [A; 9]; every measured SearchQA Skill effect is answer surface form [A; 10]; the dataset's own answer style is inconsistent [11]. LiveMath: 85% of the card's dead failures are the meta option, which the benchmark paper documents as the replaced correct answer [A; 12]. ALFWorld: all failures are 50-step timeouts; a stronger solver solves 89.5% [A; 13]. SpreadsheetBench: the card itself has no effect [A; 13]. OfficeQA: real headroom (card 25–29%) but 74 training items and 22–24-point session swings on identical text and items [R; 12, 14]. Learned conventions transfer negatively: other benches' Skills cost SearchQA 3–8 points, the LiveMath card costs OfficeQA 9.5, and on test the instruction (66.7) ≥ SkillOpt (66.0) > GEPA (63.5) [15, 16].

**1.3 Default hypothesis (to be tested, not established): the true increment over a good card is ≈0–2 points.** For GLM the 975-item result bounds it near 2 points (missing-result bound 3.2) [3]; for deepseek the evidence says only that >5 points is unlikely [9]. A sharper instrument would tighten the null, not make it positive. Test-panel MDEs at 2 runs are 3.7 / 6.3 / 7.3 / 6.5 / 8.0 (SearchQA / OfficeQA / LiveMath / SpreadsheetBench / ALFWorld) [17]: such an effect could not carry the owner's generalisation claim even if real.

**1.4 The one real gap.** No strong "card + rule" candidate was ever tested [9, 18]: cal-1's arms are the card or scaffold variants, and v3's rules came from an audited, defective proposer. Only this could overturn 1.3, and it is cheap to close (Exp 1).

## 2. 停 / 留 / 改 Stop / keep / change

**停 Stop**
1. **v4 as specified** (B1–B17, P1–P7). It keeps the C1–C4' thresholds and explicitly excludes fresh-batch version-level acceptance [19] — a gate that passes even the +9.4-point card only 75.8% of the time at n = 11, while rule effects are 0–1.5 [1, 7]. D13: rules failed because "效果太小…提示词改不了" [20]. Running it is the cost: caps of 11.6–11.7亿 tokens; the all-in-scope C1 panel alone adds +34M (2.3×) [19, 21]. Archive the spec, plans and v2 revisions unchanged.
2. **Any new five-bench chain** (v3: 139M, zero acceptances [6]; one seeded ALFWorld round ≈16.4M for solver-capability failures [13, 22]).
3. **Generated tasks / model-written checks as gate or evidence**: balanced accuracy 0.47–0.55; content separation 0/23; panels saturated (122/122; scaffold 0.891) and blind to a real −9.5 harm; on 10/15 a candidate was better on generated items and on zero real items [23–25, 30].
4. **The E2 transfer matrix**: ≈292M/523M, joint success 5.5% at true +2/+4 [26].
5. **"Veto-only" checks on a similar bench's training items** (synthesis step ②): a validation set in disguise that spends SearchQA's only similar target [27].
6. **Learning the LiveMath meta option** — an owner card-policy decision [12].
7. **Variants measured non-positive**: case memory −1 [−6, +4] [11]; judge/partial-credit gates [28]; applicability filtering [21]; solver switching (cand vs card: flash −0.5, glm −3.1, deepseek −14.8) [10]; distilled rules replacing the card (a tie) [29]; the D3 tracker (gain only in a redesigned loop) [39].
8. **The headline "量尺是瓶颈"** and its refuted numbers (0–3 ceiling, 14–17% self-pass, "+7 generic", placebo −9.8).

**留 Keep**
1. Same-session interleaving, ≥2-min duplicate spacing, tag monitoring, truncation = unknown [14, 30].
2. The D11 reporting template (0 calls); cal-1 variances as the power basis [1].
3. Ledger rules: learning claims against an instruction baseline; 1–3-point gains need fresh seeds and items [4, 8].
4. Harness, ledger, receipts and all frozen v3/cal-1 artefacts.
5. JSON-aware scoring only as a versioned *secondary* diagnostic: it matters for scaffold arms (placebo −10.0 → −0.5); card arms tag 99.9–100% [10, 31].
6. The D14 write-up (zero cost); ALFWorld and SpreadsheetBench only as no-drop controls.
7. D10's measurement-paper framing.

**改 Change**
1. **Positive control before any learner**: no chain runs until a hindsight-written package on top of the card beats the card on fresh items.
2. **Host rule**: claim "learned beats card" only where the substantive headroom is ≥2× that bench's test MDE.
3. **Budget**: ≤50M real tokens in six weeks (≈⅓ of one v3 run, ≈4% of v4's cap); no run >20M before Exp 1 is positive.
4. **Only if Exp 2 passes**: version-level fresh-batch acceptance (D1/D8) as a new protocol version.

## 3. 接下来的实验序列 Sequence (4–6 weeks)

**Anchors (real tokens per cell)**: SearchQA card-sized 3,995 (E5) / 4,088 (v3); LiveMath 3,969; short-card QA 1.4–1.8k [22, 32]. The ledger charged ≈2× real in cal-1, so ledger caps = 2× the estimates [33]. ≈880 cells/h at 6 workers [7]. Rule-vs-card per-item SD on deepseek: 0.243 [10].

**Exp 0 — Close-out and registration (week 1; 0 solver tokens, ≤1M writer/judge).** (a) Id-level accounting of SearchQA pool use (E5 critic: 59/600 never used; E8 critic: 300 outside v3 and E8 — conflicting) [34]. (b) Re-estimate the instructed-arm SD at K = 1/2 from cal-1/E7 cells. (c) From training failures only, write and SHA-freeze: SearchQA form package **F** (answer conventions only), content package **C** (search/reasoning, no form), one LiveMath content package per cross-fitting fold, and length/position-matched placebos. Writer: the strongest available model, given the card, the 54 failed cal-1 items and the D9 critic's annotations; packages generic (no item entities), ≤600 bytes, each line marked new relative to the card. (d) Finish D14. (e) Optional ≈0.2M semantic audit of the 54 failures [9]. (f) One Codex review round. *Decision*: if 800 clean never-sampled SearchQA rows cannot be drawn, use the 400 non-focal pool items × 2 runs (same cost, MDE ≈3.1, prior use disclosed).

**Exp 1 — Decisive positive control: card + hindsight package vs card (week 2; ≈19M real, cap 38M; ≈5 h).**
- *SearchQA*: 800 never-sampled rows as a new registered block (not C/D [35, 36]), 1 run, interleaved TC, TC+placebo, TC+F, TC+C = 3,200 cells ≈13.1M, plus 100 spaced TC duplicates ≈0.4M. Optional TC+V (v3's merged rules) +3.3M.
- *LiveMath*: the 154 non-meta training items (283 − 129) [12, 37], cross-fitted (each fold gets the package written from the other fold's failures); round 1 card ×2 for the writer, round 2 TC / TC+package / TC+placebo ×2 interleaved = 1,232 cells ≈4.9M.
- *Power*: SearchQA MDE80 ≈2.4, 95% half-width ≈1.7; LiveMath MDE ≈7 (its test MDE is 7.3).
- *Decision rule (official binary score; Holm over C − TC and C_LM − TC)*: **POSITIVE** = point ≥ +3, adjusted lower bound > 0, package − placebo lower bound > 0 → Exp 2. **NULL** = SearchQA upper bound < +3 (the 10/13 materiality threshold [3]) and LiveMath point < +3 → stop rule-learning on these benches → Exp 3 (+ Exp 4). **INCONCLUSIVE** → one extension of 800 fresh rows (≈13M), same rules on the pooled 1,600; still not POSITIVE → NULL for programme decisions, since no test panel could show it [17]. F − TC is the *instrument* control: a lower bound > 0 proves rule-on-card effects are visible, but F is a non-transferable answer convention and never counts as "something to learn". *Validity* (else rerun, never a result): card tag rate ≥99%, one session, duplicates within 2 SE.

**Exp 2 — Can the automated proposer capture it? (weeks 3–4; only after POSITIVE; ≈14M real, cap 28M).** A second fresh 800-row block (or a new LiveMath session), 1 run: TC, TC+C (frozen), TC+A (the project's proposer on the same failures; ≤1M, cf. v3's whole GLM use of 7.8M [6]), TC+placebo. *Decision*: C replicates (lower bound > 0) and A − TC ≥ +2 with lower bound > 0 → a slim v5 with version-level fresh-batch acceptance and a pre-registered post-freeze transfer read (owner consent). C replicates but A does not → the proposer is the bottleneck; iterate offline (≤2M per round). C fails → NULL branch.

**Exp 3 — Measurement / negative-result paper (weeks 2–6; 0 solver tokens).** Headroom ladder per bench; cal-1; card vs scaffold (large); learned-over-card ≈0 (fresh items, two solvers); sources of apparent gains (weak starts, answer conventions, scorer strictness, artefacts, drift); cross-bench harm; the D11 standard. Only already-opened test results [16]; OfficeQA 172, the LiveMath evaluation block and SearchQA C/D stay sealed [35]. *Pivot*: an objection beyond Exp 1's reach → at most Exp 1's SearchQA arms on GLM-5.3 (≈13M).

**Exp 4 — New-bench headroom pre-screen (weeks 3–5; optional; ≈1.3–1.6M per candidate, ≤3).** Eligible: ≥600 labelled training items, a sealable labelled split (HotpotQA/2Wiki/MuSiQue hide test labels), execution- or program-checked answers. 300 items × 1 run × {scaffold, card, card + hindsight package} = 900 cells. Port only if (card + hindsight) − card ≥ +5 with lower bound > 0; E3 found 2–4 points of content headroom everywhere, +1.9 on HotpotQA [32]. If none passes, close the programme and keep the paper.

**If the answer is "nothing to learn"**: stop chains on all five benches; publish the honest claim — *experience substitutes for a task card but adds nothing measurable on top of it; the apparent gains are artefacts*; keep the sealed holdouts unread for a future method that works; port new benches only via Exp 4.

## 4. Objectives

- **Objective 1 (Skill + verifier-rubric co-evolution): deprioritized.** There is no Skill-side effect to co-evolve with; when nothing is accepted S_t = S_{t−1} and the verifier gets no signal [23]. On exact-reference benches the verifier reduces to item generation, which is saturated and misleading [24, 25]; September's co-evolution changed the validator 8 times with 0 promotions [38]. Resume only after Exp 2 passes, or on an Exp 4 bench with open-ended outputs.
- **Objective 2 (evolve on one bench, evaluate on the rest, no validation set): not demonstrable on this suite.** Test MDEs of 3.7–8.0 exceed every plausible learned effect; only OfficeQA (the similarity hub) gives a pooled similar-target MDE ≈3, and it has 74 training items [17]; the learnable content is answer convention, which transfers negatively [15]. The plan serves it by refusing validation-set proxies [27], a post-freeze transfer read only after Exp 2, and honest negative-transfer reporting.

## 5. Risks and falsifiers

- **Falsifier**: Exp 1 POSITIVE → "nothing material to learn" is wrong and the proposer is the bottleneck; Exp 2's A arm passing falsifies it twice.
- **A weak writer could give a false null**: the writer holds more information than any learner, but a null bounds rule-shaped text, not all text.
- **SearchQA content headroom is ≈6 points by construction** [9]; LiveMath sees only ≈7-point effects — as does its test panel.
- **One solver**; GLM's 975-item null covers a second.
- **Drift/format artefacts of 5–10 points** [30] — handled by interleaving, placebos and the tag gate.
- **The new draw must exclude sealed rows**: id-level exclusion inside the existing drawing tool, with owner sign-off.
- **Stop-loss read as giving up** — the paper is a deliverable; Exp 4 keeps a ≈5M door open.

## 6. 事实清单 Claims and sources

RL = `docs/results-and-lessons.md`; FS = `docs/handoff/feasibility-20261021/`; JSON fields in backticks.

| # | Claim | Source |
|---|---|---|
| 1 | cal-1: card vs scaffold +0.0938 [0.0505, 0.137]; C1 passage 75.8% (n=11), 47.9%/99.0% (n=6/20), null 0%; 8,800 cells, 27,481,897 ledger tokens | `docs/handoff/cal1-registration-20261020.md` l.130, 137–140 |
| 2 | D1 card vs scaffold +0.162 [+0.104, +0.223] on 130 never-used items; placebos on card 0.000/−0.023; E5 card +8.9 [4.4, 13.1] | FS D1/result.json `pilot`; FS E5/critic-result.json `refuted_claims` |
| 3 | 975 items: lz−bzero +0.001 [−0.016, +0.018] (bound ±0.032); le−bzero −0.005 [−0.023, +0.012]; le−bhand +0.047 [+0.022, +0.071]; lh−bhand +0.049 [+0.020, +0.078]; v10 +0.001; v9 +0.010; 3-pt threshold | RL l.222 |
| 4 | 750 fresh items: +2.7 not replicated, effect ≤1.5 pts; 1–3-pt gains need fresh seeds + items | RL l.220 |
| 5 | Real items, 3 solvers: learned−bzero n.s. (SearchQA −1.8…+0.6) | RL l.182, 195 |
| 6 | v3: 0 rules accepted; deepseek 139,024,462; GLM 7,804,250 | RL l.142 |
| 7 | v3 rules on card +0.000/+0.004/+0.015; D1 replay −0.107…+0.005; ≈880 cells/h | FS D9/result.json `evidence` E; FS D1/result.json `risks` #2, #10 |
| 8 | gen17 +0.046 on a reused dev pool; report vs generic; 10/12 nothing established | RL l.137, 139 |
| 9 | ≈73% of card failures exact-match strictness, ≈6 pts substantive; no card+rule arm; v3 proposer defective | FS D9/critic-result.json `refuted_claims` #1, #4; `missing` |
| 10 | SearchQA Skill effects = surface form; rule-vs-card SD 0.243; card+rule never run; cand vs card −0.5/−3.1/−14.8; I-ds 100% tagged | FS E7/critic-result.json `refuted_claims` #4–5, `missing`; FS E7/result.json `pilot` |
| 11 | Case memory −1 [−6, +4]; inconsistent answer style | FS D2/result.json `verdict_cn` |
| 12 | Meta option in 129/283 items, always correct; 58/68 dead failures; non-meta card 62/110; OfficeQA card 25–29%; paper: correct option replaced | FS D9/critic-result.json `confirmed_claims`, `refuted_claims` #3, `missing`; FS D7/critic-result.json `refuted_claims` |
| 13 | ALFWorld: all failures 50-step timeouts; GLM 102/114; SpreadsheetBench card −0.002 [−0.052, +0.048] | FS D14/report.md l.71, 90, 96 |
| 14 | Same text, same 60 OfficeQA items: 50.8% vs 26.7%; 22–24 pts | FS D12/result.json `evidence`; FS D11/result.json `verdict_cn` |
| 15 | Foreign Skills on SearchQA −3…−8; LiveMath card → OfficeQA −9.46 | RL l.206; FS E9/result.json `evidence` |
| 16 | v1 test: instruction 66.7, SkillOpt 66.0, GEPA 63.5 (opened with consent) | RL l.173 |
| 17 | Test MDEs 3.7/6.3/7.3/6.5/8.0; pooled similar-target ≈3.0 from OfficeQA | FS E5/critic-result.json `refuted_claims` #4 |
| 18 | No rule-on-card positive control; no seed+rule arm | FS E6/critic-result.json `refuted_claims` R3; FS D8/critic-result.json `missing` |
| 19 | v4 excludes version-level acceptance and threshold changes; 11/12 reviews "needs revision"; caps 11.6/11.7亿 | `docs/handoff/v4-plans-20261021/spec.md` l.177; `docs/handoff/overnight-report-20261021.md` l.38, 135 |
| 20 | "效果太小…提示词改不了" | FS D13/result.json `verdict_cn` |
| 21 | All-in-scope C1 panel 2.3×, +34M | FS D4/critic-result.json `refuted_claims` |
| 22 | Per cell: SearchQA 4,088 (v3) / 3,995 (E5 ids-full), LiveMath 3,969, OfficeQA 7,927; ALFWorld round ≈16.4M | FS D6/critic-result.json `refuted_claims` #5; FS E5/result.json `cost_estimate`; FS D1/result.json `risks` #10 |
| 23 | Checks BA 0.47–0.55; content 0/23; S_t = S_{t−1} stall | FS E1/result.json `verdict_cn`; FS E1/critic-result.json `confirmed_claims`, `refuted_claims` |
| 24 | Generated panel 122/122; scaffold 0.891 on generated items | FS D12/result.json `recommendation` #2; FS E9/result.json `evidence` |
| 25 | 10/15: better on generated items, no extra real item | RL l.197 |
| 26 | E2 ≈292M/523M; joint success 5.5% | FS E2/critic-result.json `refuted_claims` |
| 27 | Synthesis step ② veto-only check; a real-pool guard spends the similar target | overnight-report l.53; FS E9/critic-result.json `missing` #1 |
| 28 | No judge/graded scores in gates | FS E6/result.json `recommendation` #1 |
| 29 | Distilled rules replacing card: 0 [−3.7, +3.7] officially; −13.5 only under tag-only scoring | FS E8/result.json `verdict_cn`; FS E8/critic-result.json `refuted_claims` |
| 30 | Zero-cost fixes; artefacts of 5–10 pts each | overnight-report l.49, 51 |
| 31 | control:3 −0.100 → −0.005 (JSON-aware); card drops tag 0.1% | FS D5/critic-result.json `refuted_claims`; FS D9/critic-result.json `refuted_claims` #2 |
| 32 | 1.4–1.8k per cell; headroom 2–4 pts; hidden labels; HotpotQA +1.9 | FS E3/result.json `evidence`, `risks` #5; FS E3/critic-result.json `missing` M1, M5 |
| 33 | Ledger 26.5M vs 14.0M real | FS D8/result.json `cost_estimate` |
| 34 | Never-used SearchQA items 59/600 vs "300 outside v3's draw and E8's evaluation" | FS E5/critic-result.json `missing` #7; FS E8/critic-result.json `missing` #1 |
| 35 | Holdouts read once after freeze with consent | `docs/project-status.md` l.117 |
| 36 | New block from never-sampled rows, not C/D | FS D10/critic-result.json `missing` #8 |
| 37 | Pools: SearchQA 600/400; OfficeQA 74/172; LiveMath 283/125; SpreadsheetBench 120 (91)/279; ALFWorld 57/134 | `docs/handoff/coevo5-registration-v6-20261017.md` §2 l.84–90 |
| 38 | Sept. co-evolution: 8 validator updates, 0 promotions | FS E10/critic-result.json `refuted_claims` |
| 39 | D3 tracker gain only in a loop redesigned after it failed in the frozen loop | FS D3/critic-result.json `notes_cn`, `direction` |

## summary_cn

先止损。大的差别量得很准（人写的作答说明“任务卡”比空模板高9到16分），但“任务卡之上再加学到的规则”测出来都接近0：975道新题上0±2分；第3版正式运行（v3）花1.39亿token，一条规则都没收下。剩下的空间多是评分太死板或数据集特有写法，搬到别处反而有害。建议：不实现第4版改动（v4：门槛不变，上限约11.6亿token），停掉生成题把关、迁移矩阵。只做一个约1,900万token的判定实验：让最强模型看着训练错题事后手写规则加在任务卡上，在800道没用过的检索问答（SearchQA）新题和154道数学题（LiveMath）上，与任务卡、等长无关文字（安慰剂）比较。连它都提不到3分，就停止在这五个数据集上学规则，改写“测量与负结果”论文；提得到，再测自动方法能否学到。目的一（技能与判卷标准共同进化）暂缓；目的二（一个数据集进化、其他数据集评测）按现有题量测不出3分以下的效果。
