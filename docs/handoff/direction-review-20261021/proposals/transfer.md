# Proposal, lens 泛化评测优先: make "evolve on one bench, evaluate on the others" measurable and honest

2026-10-21; read-only, no model calls. `[Cn]` → §6; `F/` = docs/handoff/feasibility-20261021/. Pool sizes: v6 registration [C9].

## 1. 诊断 Diagnosis

**No learned text has ever been measured transferring.**
- v1's transfer criteria held (self +2.5, similar +4.1, rest −0.6) only because every Skill, the non-learning instruction included, lifted OfficeQA ~20 points through answer writing; similar placement was never used [C1].
- v3 accepted 0 rules (139M deepseek tokens), so its later transfer cells are Δ≡0; its similar check never ran (0 forward panels in 10 chain-steps; 47 of 49 proposals local) [C2, C3].
- E4, E9 and E2 moved whole cards (1.8–2.9 KB), mostly onto the empty scaffold, and mainly show answer-channel harm: texts pushing answer-only replies cost OfficeQA 8–27 points [C4]. The "+7 generic gain" is tag repair plus the LiveMath meta option [C5]. "Card + learned rule vs card" was never run on any target [C6].

**Why transfer is undetectable today.**
- (a) *Star map on the weakest bench.* OfficeQA is the only similar bench of every other source [C7]; its 74 + 172 items are the whole public benchmark [C8]; the same text moves 20–24 points between windows (answer-only vs computing regime, flipping about hourly) [C10].
- (b) *Cross-session readouts.* The registered readout differences cells from different windows (estimated similar-class SE 5.8 vs 0.8 paired) [C12]; v3's chains were 0% co-scheduled [C13].
- (c) *Effects below resolution.* cal-1's rule-sized bridges did not beat even the empty scaffold under strict scoring (+0.4/−3.0 points) [C14]; seven I-ds rules on the card parent scored −10.7 to +0.5 [C15]; learning over a generic instruction was not established in 10/12 [C16]. Test MDEs at 2 runs for one pre-named contrast: 3.7/6.3/7.3/6.5/8.0 (SearchQA/OfficeQA/LiveMath/SpreadsheetBench/ALFWorld), 1.3× larger under Holm over 10 cells [C11, C17].
- (d) *Wrong reference, leaky proxies.* Against the empty scaffold, transfer flips sign (v1 off-diagonal +2 to +3 vs blank, −3 to −4 vs cards) [C19]; generated OfficeQA-style items are saturated and miss the real −9.5 harm [C3, C4]; screening on another bench's training items is a validation set in disguise and would consume the only similar target [C7, C20].

**Bottom line.** Objective 2's bottleneck is the missing transfer instrument, not the proposer. A same-window paired design on these pools can detect gross harm (≥8 points) and a pooled ~4-point drop over LiveMath + SpreadsheetBench test (~300 items × 2 runs) [C11, C18]. "Similar improves" from SearchQA needs ≥6 points on OfficeQA, more than anything learned so far.

## 2. 停 / 留 / 改 Stop / Keep / Change

**Stop**
- S1. v4 as specified (five-stage chain, per-rule C1–C4′ gates, ~1.16B cap) as the next paid run: it excludes version acceptance and any test-side change, so its transfer readout is again Δ≡0 or cross-session [C21, C2, C12]. Port only B5, B7, B13/P7, B17.
- S2. Transfer claims against the empty scaffold or No-Skill [C1, C19].
- S3. Generated forward panels as similar evidence or guard [C3, C4].
- S4. Screening rules on another bench's training items [C7, C20].
- S5. Arm contrasts not interleaved item by item [C10, C13].
- S6. LiveMath as a source (the meta option is the key in 129/129) [C22].
- S7. Expecting "similar improves" below 6 points on OfficeQA from a SearchQA source [C11].

**Keep**
- K1. The owner's map, unchanged, as the pre-registered hypothesis; E4 cannot speak to learned rules [C23, C43].
- K2. The five task cards (I5) as interleaved reference; across days on SearchQA, I5 moved −0.5 and the scaffold −5.9 [C24].
- K3. ≥2 length-matched placebos [C25].
- K4. Test pools read once, after freeze, with owner consent [C26].
- K5. D1 version-level acceptance on fresh source batches [C27].
- K6. D11's report template with its critic's fixes [C13, C17].
- K7. A veto-only in-method format-break screen on generated items (no target data) [C4].

**Change**
- X1. Calibrate the transfer instrument with known texts before evolving (T1).
- X2. Evolve on SearchQA only (600 items; the only pool with fresh batches for ~3 steps) [C27, C28]: two replicate chains, ≤3 steps. OfficeQA as source would give the best similar readout (pooled MDE ~3.0) but its 74 items certify only ≥10-point steps and drift by regime [C11, C27].
- X3. Co-primary: self gain; no drop on unseen dissimilar benches (pooled non-inferiority, margin M). Secondary: similar gain, MDE printed beforehand.
- X4. Item-blocked interleaving; identical twin ≥120 s apart; 2 runs (ALFWorld 1); regime sentinel from the reference arm only [C29]; OfficeQA per regime; JSON-aware + strict + content scores as a new scoring version [C30].
- X5. Confirmatory readouts on target test pools only; target training pools used once, pre-run, with fixed texts, disclosed as development data [C31].
- X6. General-section rules must pass an executable format-neutrality check built from the public cards (no answer-channel, tag or length directive), the one harm mechanism surviving Holm [C4, C32].

## 3. 接下来的实验序列 Sequence (4–6 weeks)

**T0 Instrument repair, zero-cost re-reads (week 1; 0 tokens).**
- Purpose: fix scoring and dispatch before spending; size the OfficeQA regime from archives.
- Design: register the scoring version; re-score cal-1, E2, E4, E9 and v3 training cells (no relabelling); implement D11's R8 and exact-test switch [C13]; reference-arm terse share per 15-minute bin for archived OfficeQA/SearchQA units; finish D14 from records; freeze the T1–T3 registration before v3's sealed test scores are opened.
- Decision: a v3 gate verdict flipping under JSON-aware scoring is recorded as a scoring artefact; an OfficeQA regime change in ≥1 of 3 hourly windows → T1/T3 measure OfficeQA in two windows.
- Pivot: regime not identifiable from reply length → OfficeQA similar readout registered per regime only.

**T1 Transfer calibration "tcal-1" (week 2; ≈36M deepseek, cap 45M).**
- Purpose: measure per target, with the real parent and realistic text sizes: harm sensitivity, placebo band, bleed base rate, regime dependence, margin M.
- Arms (parent I5; text in the SearchQA section unless stated): A0 I5; A1 byte-identical copy (dispatch check only, blind to text-dependent drift [C39]); A2/A3 length-matched placebos; A4 answer-only directive H (~120 chars); A5 H in a General section (harm positive control); A6 the merged v3 I-ds step-1 rule package D1 proposed [C27]; A7 the v1 SearchQA-learned GEPA text (hurt SpreadsheetBench test −7.8 vs blank [C1]).
- Items (training; 2 runs): SearchQA 120/600; OfficeQA 74 (second window for A0, A4, A5, A7); LiveMath 100/283 (meta strata); SpreadsheetBench 91 qualified; no ALFWorld.
- Cost: 6,752 cells × measured five-card per-cell costs 3.9k/8.4k/4.4k/4.3k [C17] = 7.5+14.9+7.0+6.3 ≈ 35.7M (1.3× cal-1's 27.5M [C14]).
- Decision rules: (a) A1−A0 inside the 99% band per target, else re-run that target in a fresh window; (b) A5 harm (95% CI < 0) on OfficeQA in ≥1 computing-mode window, else OfficeQA is descriptive-only in T3; (c) A5 differs between regimes by >2 SE → two OfficeQA windows in T3, reported per regime; (d) A4, A6, A7 all inside the placebo band (max |A2|,|A3| + 2 SE) on every target → no per-rule guard in T2; any below → X6 mandatory and that target primary in T3; (e) A6's upper 95% bound over I5 on SearchQA < +3 → T2 starts from G-start (I5 with its SearchQA section replaced by a 3-line generic instruction), which joins T3; (f) M = smallest margin with ≥0.8 power at a true zero for T3's pooled readout (expected ≈4 [C18]); (g) a placebo moving any target >2 points → four placebos in T3.
- Pivot: (a) fails twice, or nothing (A5 included) is detectable on any target → stop objective-2 runs on these benches; go to the measurement paper (D10) and a benchmark-family decision (E3).

**T1-V Generator qualification for objective 1 (with T1; ≈3.3M deepseek, budget 5M; ≤0.5M GLM).**
- Purpose: can a generated OfficeQA-style panel, built only from public material, be a veto-only harm screen (the only claim-clean route to similar-target evidence [C20])?
- Design: D6-style typed spec → executable reference, 2-of-3 cross-check; difficulty by construction (≥2 operations, multi-row tables); 80 items × T1's arms × 2 runs in T1's window; one-time pre-run qualification with fixed texts, never re-validated per step [C20].
- Cost: 1,280 cells × ~2.6k (E9 pilot: 2.87M / 1,124 cells) ≈ 3.3M, plus ~2.7k GLM per kept item [C33].
- Decision: qualifies only if A0 passes 0.3–0.7, A5 harm is detected at ≥0.5 of its real-pool size, A1−A0 is within ±2 points, and ≥60 audited items remain. A qualified panel is a gross-harm screen, never transfer evidence.
- Pivot: fail → no generated screen in T2; generator work continues off the critical path.

**T2 Single-source evolution row (weeks 3–4; ≈56M deepseek, ≈7M GLM).**
- Purpose: learned Skill versions on SearchQA without any target data.
- Design: two chains (different batch seeds), ≤3 steps, start I5 (or G-start per T1e). D1 acceptance: proposal batch 100 (flagged, never reused); acceptance batch 300 × 2 unseen by the proposer (returned to the pool); accept if one-sided LB95 > 0 and mean ≥ 0.02; parent re-measured in the same round; duplicate + placebo arms in round 1; futility look at half batch. Add v4's B5/B7/B13/B17 and D13's per-code conditional proposer; General placement only via X6, decided on SearchQA evidence. Firewall: role-prompt builders refuse target ids; post-run hash audit of all role transcripts. Optional T2-V: one extra chain with the qualified screen (~28M).
- Items: SearchQA training pool only.
- Cost: 2 × E2's per-chain estimate (27.9M deepseek + 3.6M GLM for three SearchQA steps) [C34]; D1's measured acceptance round was 4.72M [C27].
- Decision: T3 runs only if some chain's final differs from its start; stop both chains if neither accepts at step 1 and both estimates are ≤ 0.
- Pivot: nothing accepted from I5 (and from G-start if tried) → no learnable change on SearchQA for this solver; stop evolution on the five benches; the owner chooses between the measurement paper and E3 family B (procedural content) [C35].

**T3 Sealed confirmatory transfer evaluation (week 5; ≈75M; 0 if T2 changed nothing).**
- Purpose: the first honest "evolve on one, evaluate on the rest" row.
- Arms: I5 (reference), I5b (dispatch check), P, Q (placebos), F1, F2 (finals); G-start if T2 used it; optional placement-swap control and T2-V final.
- Items (test, sealed until the run ends; 2 runs): SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 177–204 of 279; ALFWorld seeded half 67/134, 1 run, I5/F1/F2 only. Strict, content and JSON-aware scores; LiveMath meta strata; OfficeQA clustered by source file and split by regime.
- Cost: 8.9M per arm on the four QA/table pools [C17] × 6 ≈ 53M; ALFWorld 201 episodes × ~110k ≈ 22M [C36]; ≈75M (0.54× v3), consistent with E2's one-run I5 sweep of all five test pools, 18.6M with 76% ALFWorld [C34].
- Decision rules (frozen after T1, before T2):
  - Self: F̄ − start on SearchQA, one-sided LB95 > 0, and F̄ above both placebos.
  - No drop (co-primary): mean Δ over LiveMath + SpreadsheetBench, one-sided LB95 > −M; no target (OfficeQA, ALFWorld included) with a two-sided 95% CI wholly < 0; every target's MDE printed.
  - Similar (secondary): OfficeQA one-sided LB95 > 0 and above both placebos, within one regime.
  - Labels: "learned transfer" only on content scoring vs the start Skill; a gain only vs No-Skill or only on strict scoring = "format transfer"; inside the placebo band = "text-presence effect"; else "not established", with power.
  - F̄ averages both chains' finals item by item (inference conditional on two histories); each chain reported; the better chain is never picked.
- Pivot: a drop → strengthen X6 before any sequential chain; self + no-drop without similar → similar is underpowered by design, fixable only with more similar-format test items registered before a new run; all three → the owner's cumulative five-stage chain under this protocol.

**Totals:** ≈36+3+56+75 ≈ 170M deepseek + ~8M GLM (v3: 139M + 7.8M [C2]); up to ~250M with optional arms; several days of dispatch at ≤6 workers [C37].

## 4. 如何服务两个目标 How this serves the two objectives

**Objective 2 (evolve on one, evaluate on the rest, no validation set): main line.** Controls separate learned transfer from format, text presence and serving drift; "no drop" becomes a non-inferiority test. The owner learns beforehand what these benches can resolve: self gain and no drop at ~4 points; "similar improves" only at ≥6. "No validation set" holds by construction: (1) acceptance uses SearchQA training batches only; (2) T2's firewall keeps every target item, train or test, out of every method role; (3) target training pools are used only as in X5, to set M, the placebo band and the regime rule; this needs owner sign-off, else T1 uses archived E2/E4/E9 target cells plus SearchQA; (4) source, targets, M and labels are frozen before T2 and before any new test score is opened; (5) T3 reads test pools once; later redesigns on the same pools are labelled adaptive.

**Objective 1 (co-evolving the Skill and the verifier rubric): deprioritise as a main line for these weeks.** No evidence shows the verifier side improving: model-written checkers are near chance (BA 0.47–0.55), a difficulty-seeking generator exploited the scorer, and generated items are saturated [C38, C3]. Co-evolution can only be shown with a transfer instrument that does not yet exist. Kept cheaply: T1-V qualifies the only data-free source of similar-target evidence; X6 writes each bench's answer contract as an executable check (the coding rubric in its most transfer-relevant form); if T1-V passes, T2-V + T3 give a first, unpowered co-evolution readout.

## 5. 风险与证伪 Risks and falsification

- R1. T2 changes nothing (D1's replay found no gain [C15]) → T3 skipped, "not testable". SearchQA mostly teaches its own answer granularity [C40], which does not transfer: the likeliest honest outcome is "self small or null, no drop, similar not established".
- R2. OfficeQA's regime may leave the similar readout uninterpretable even per regime [C10].
- R3. A placebo band as wide as the learned effects makes "learned transfer" impossible to label [C25].
- R4. Pool reuse: only 59 SearchQA training items were never used [C41]; target training pools already shaped the design [C31] (disclosed).
- R5. Cost/time: capped pipelines reserve up to ~2× delivered tokens [C42]; 429s and ≤6 workers stretch T3 to 1–2 days while the regime flips about hourly [C37, C10]; the single-source row is new code (stage→bench is hard-wired) [C44].
- R6. Two histories only; between-chain variance unestimated.
- Falsifiers: (i) T1 cannot detect even A5 on any target → these benches cannot measure transfer; change benchmarks or write the measurement paper. (ii) A6 moves a target ≥5 points → per-rule transfer guards matter and the version-level-only stance is wrong. (iii) T3 shows a ≥6-point similar gain → "similar is underpowered" was too pessimistic.

## 6. 事实清单 Claims

RL = docs/results-and-lessons.md; V6 = docs/handoff/coevo5-registration-v6-20261017.md; OR = docs/handoff/overnight-report-20261021.md; `l.` = line.

|#|Claim|Source|
|---|---|---|
|C1|v1: OfficeQA +20 for any Skill; similar placement unused; GEPA SearchQA text −7.8 on SpreadsheetBench|RL l.173|
|C2|v3: 0 rules; 139,024,462 deepseek + 7,804,250 GLM tokens|RL l.142|
|C3|47/49 proposals local; 0 forward panels in 10 steps; generated 122/122 pass|F/D12/result.json `evidence`, `pilot`|
|C4|LiveMath card→OfficeQA −9.46/−8.11; answer-only 0.23→~0.6; generated panel misses it; ALFWorld/Sheet cards −26.7/−20.0|F/E9/result.json `evidence`; F/E4/result.json `evidence`|
|C5|"+7" = tag repair + meta option|F/E4/critic-result.json `refuted_claims` R1|
|C6|No cal-1 arm is card + rule; rule-sized bleed on a seeded parent unmeasured|F/D9/critic-result.json `refuted_claims`; F/D8/critic-result.json `missing`; F/E9/critic-result.json R3|
|C7|OfficeQA is the only similar bench of every non-hub source|skillopt/coevo5/protocol.py l.18; V6 l.71; F/E9/critic-result.json R1|
|C8|74+172=246 = whole OfficeQA|F/E10/critic-result.json `refuted_claims`|
|C9|Train/test 600/400, 74/172, 283/125, 120 (91 qualified)/279, 57/134|V6 l.84–88; docs/project-status.md l.187|
|C10|Same text, other window +22.5/+24.2/+20.3; regime flipped ~hourly|F/D11/result.json `evidence`; F/E9/critic-result.json R4; F/E2/critic-result.json `missing` 3|
|C11|Test MDE 3.7/6.3/7.3/6.5/8.0; pooled similar 3.0 (OfficeQA source) vs 6.3 (SearchQA)|F/E5/critic-result.json `refuted_claims` 4|
|C12|Similar-class SE 5.79 vs 0.84 paired (estimated)|F/D12/result.json `evidence`|
|C13|v3 chains 0% co-scheduled; R8/Tango unimplemented|F/D11/result.json `evidence`; F/D11/critic-result.json `refuted_claims` 3–4|
|C14|cal-1 27,481,897 tokens; bridges (scaffold + one bullet) +0.0037/−0.030, strict scoring|docs/handoff/cal1-registration-20261020.md l.128–146|
|C15|Seven I-ds rules −0.107…+0.005|F/D1/result.json `evidence`|
|C16|Learning over a generic instruction not established|RL l.139|
|C17|Holm ×1.30; per-cell 3.9k/8.4k/4.4k/4.3k/116k|F/D11/critic-result.json `refuted_claims` 2, 6|
|C18|NI margin 3 pts ≈550×2, 4 pts ≈300×2|F/D6/critic-result.json `refuted_claims`|
|C19|v1 off-diagonal +3.2/+2.0/+3.2 vs none, −3.2/−4.4/−3.2 vs cards|F/E2/result.json `evidence`|
|C20|Next bench's pool never sampled; generated panel the only clean route; per-step re-validation = validation set|F/D12/result.json `recommendation` 3; F/E9/critic-result.json `missing` 1, 3, 6; F/E3/critic-result.json M10|
|C21|v4 excludes version acceptance and test-side change; 1.16B cap|docs/handoff/v4-plans-20261021/spec.md l.177; OR l.38|
|C22|Meta option key in 129/129; don't evolve on LiveMath|F/D7/result.json `evidence`; F/E4/critic-result.json R8|
|C23|E4's H1 is silent on learned rules|F/E4/critic-result.json R4|
|C24|Compare card+rules with card; I5 −0.5 vs scaffold −5.9 across days|F/E3/critic-result.json C9; F/E4/critic-result.json R7; F/E4/result.json `recommendation` 2|
|C25|One placebo is one draw (cal-1 spread SD 5.7); I5-parent placebos 0.000/−0.023|F/D11/critic-result.json `refuted_claims` 7; F/D1/result.json `evidence`|
|C26|Tests only after freeze, never in method roles|docs/project-status.md l.118–121|
|C27|D1 certifies 0.042 (SearchQA)/0.103 (OfficeQA); round 4.72M; merged-package pilot|F/D1/result.json `evidence`, `cost_estimate`, `design`|
|C28|SearchQA supports 3 fresh steps, OfficeQA 1|F/E2/critic-result.json R3; F/E5/critic-result.json `missing` 8|
|C29|Regime strata from reference arms only|F/E2/critic-result.json `missing` 4|
|C30|JSON replies 0/364; artefact on E-ds only; I-ds tag share 1.000|F/D5/critic-result.json `refuted_claims`; F/E7/critic-result.json `refuted_claims`|
|C31|OfficeQA training pool reused by four pilots|F/E2/critic-result.json `missing` 7|
|C32|Only answer-only harm survives Holm|F/E2/critic-result.json R7|
|C33|E9 2,867,869 tokens / 1,124 cells; 2,670 GLM per kept item|F/E9/result.json `pilot`, `cost_estimate`|
|C34|Per chain 27.9M deepseek / 3.6M GLM; I5 test sweep 18.6M at 1 run|F/E2/result.json `cost_estimate`|
|C35|Classic benches give no content gain; family B fits verifier work|F/E3/critic-result.json C10, M3|
|C36|ALFWorld I-ds 105.7k tokens per episode|F/D14/report.md l.87|
|C37|v3 9–13M tokens/h at 16 workers; now ≤6|F/E2/critic-result.json `missing` 3|
|C38|Checkers BA 0.47–0.55; difficulty-only reviser exploits the scorer|F/E1/result.json `evidence`; OR l.67|
|C39|Identical twin: expected Δ 0, ~5% alarms, blind to text-dependent drift|F/E2/critic-result.json R6|
|C40|~73% of card failures on SearchQA are acceptable answers strict EM rejects|F/D9/critic-result.json `refuted_claims`|
|C41|59 of 600 SearchQA training items never used|F/E5/critic-result.json `missing` 7|
|C42|Capped pipeline needs up to ~2× over delivered tokens|F/E5/result.json `cost_estimate`|
|C43|Map fixed before launch; never redefine "similar" afterwards|V6 l.67, 78; /Users/dulin/.claude/projects/-Users-dulin-Documents-Paper-SkillOpt/memory/research-goal-generalization-no-val.md|
|C44|`bench = ORDER[stage - 1]` hard-wired|skillopt/coevo5/step.py l.198; skillopt/coevo5/baseline.py l.93|

## summary_cn（给负责人）

建议：先把"在一个数据集上进化、在其余数据集上评测"的量尺做准，再花钱进化。理由：至今没测过学到的文字能否迁移。第1版实验（v1）的"迁移成功"其实来自答题格式；第3版（v3）一条规则都没收下，相似检查一次没跑。登记的"相似"关系都连到OfficeQA（财政文档问答，仅74道训练题），同一段文字换个时段能差20多分。步骤：①不花钱修评分（JSON即结构化格式的答案也算对）和发送规则；②约3600万token（模型计费单位）用效果已知的文字标定量尺；③只在SearchQA（检索问答）上进化两条链，各最多3步；④在五个数据集的测试题上一次性评测，同一道题的各版本连着发，对照人写的任务说明卡和两段无关文字。共约1.7亿token。能测准的是"其他数据集平均是否掉了4分以上"，"相似数据集变好"不到6分测不出。验证端出题器只做一次合格检验。第4版（v4）五步长链先别跑。
