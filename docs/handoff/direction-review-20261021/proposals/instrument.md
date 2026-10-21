# 量尺优先 — instrument-first proposal (2026-10-21)

Lens: fix the measuring instrument until it can resolve rule-sized effects in the owner's regime (a rule on top of the task cards), then judge methods with it. Read-only analysis; no model calls. Evidence tags: **RUN** registered real run · **PILOT** small feasibility run · **REPLAY** re-score of archived cells · **SIM** simulation/arithmetic · **CRITIC** critic re-analysis of real records. None of these is independent evidence that a learned rule helps. F-numbers point to §6; D*/E* paths are under `docs/handoff/feasibility-20261021/`.

## 1 诊断

The owner's question — does a rule learned from training experience add accuracy on top of the public task card, and does it carry to similar benches without a validation set — has never been put to an instrument able to answer it.

**(a) The gate cannot see rule-sized effects.** In cal-1 the five-card Skill (`ids-full`) beats the scaffold by +9.4 points, yet registered C1 passes it only 75.8% at n=11 trigger items; the rule-sized bridges pass 0% and `cand` 7.7% (F1, F2). Per-step power for +0.3–3-point effects is 0.19–0.26, and C1′ is fixed-panel inference (F12). v3's zero confirmed rules (F20) and the GLM line's learned-over-instruction increment (F21) are therefore *not established*, not *absent*.

**(b) The score mixes three nuisances into content.**
- *Answer channel*: `{"answer": …}` replies pass 0/364 although 414/424 also carry the same answer in a tag (F4); JSON-aware scoring turns the "−9.8 placebo" into −0.25 and `cand` from −2.6 to +6.75 (F5). But the I-ds parent and its three screened rules were 100% tagged (F6): this fix rescues one E-ds rule (whose content restates the card), not the primary null.
- *Dispatch and serving regime*: v3 harvested failures in a single-arm round (1.0% untagged) and gated them in interleaved rounds (6.5–10.1%) (F7); the card effect is +3.25 n.s. inside the single-arm unit (F8). On OfficeQA the same hash on the same 74 items moved +20.3 points between windows, and 8 of 9 v3 OfficeQA units were answer-only (F9); session-mean SD 11.4 points (F10).
- *Strict-EM surface form*: about 73% of the card's SearchQA failures are substantively acceptable (F15, one rater); under sub-EM, deepseek's skill effects vanish (F16).

**(c) The owner's contrast is uncalibrated.** Every positive control is card-vs-scaffold (F8), every placebo sat on the scaffold (F18), and no "card + rule" arm exists (F17). Rule-vs-card per-item SD is 0.243, so +5 / +3 points need ~186 / 515 items (F11).

**What each bench can resolve** (training side, version level, 80% power; F13, F14):

| bench | pool | smallest certifiable | role |
|---|---|---|---|
| SearchQA | 600 (59 never used) | 4.2 pts (300×2) | only source for ~3–4-point decisions |
| LiveMath | 283 (129 meta) | 5.6 (233×2) | coarse; split meta/non-meta (F25) |
| OfficeQA | 74 | 10.3 (37×4) | similarity hub, regime-dominated |
| SpreadsheetBench | ≤120 qualified | 12.2 | no-drop only |
| ALFWorld | 57 | 15.3 | no-drop only, after an action guard (F24) |

**Diagnosis.** The binding constraint is decision resolution in the owner's regime: items per decision, fixed trigger panels, regime confounding. The JSON artefact is real but secondary. v4 keeps C1–C4′ and puts fresh-batch acceptance out of scope (F22), so a v4 chain would most likely return another uninterpretable null, and P1–P6 could not be judged.

## 2 停/留/改

**Stop**
1. Per-rule C1 on 6–11-item trigger panels as the acceptance decision (F2, F12); per-rule tests become descriptive.
2. Any new method chain (v4 as written, v5) before S2: v3 spent 139M deepseek tokens to accept 0 rules on a gate blind at this size (F20).
3. Contrasts across windows or dispatch modes (F7, F9, F10).
4. Byte-identical canaries as drift alarms: expected difference exactly 0 under exchangeable dispatch, ~5% alarms by construction (F27).
5. Real-pool similar-bench guards, or any other bench's training items as a gate: OfficeQA is the only similar bench of the other three, so guard and clean transfer claim cannot coexist (F26).
6. Generated-task or ladder fitness for the verifier, for now: panels saturated 122/122 (F28), model-written checks BA 0.47–0.55 (F29), ladder τ ceiling 0.63 (F30).
7. Reading pooled LiveMath as content: the meta option is the key in 129/129 (F25).
8. Choosing a solver because its effects look largest (flash): those effects are surface form (F16).

**Keep**
1. Official scorers for every test claim; test isolation (F31).
2. I-ds (five task cards) as parent and yardstick; the registered similarity map — retiring it "treats absence of evidence as evidence of absence" (E4 critic R4).
3. v4 bug fixes B1–B17 (correctness; B7 aligns the format predicate with the scorer, F23).
4. D1 version-level fresh-batch acceptance as the lead gate: mechanics passed on 130 fresh items, but only against a 16-point effect (F19).
5. D8 exact pooled tests with Holm as descriptive screens; D8 NI margins; the D11 report template with its critic's fixes (Tango intervals, ≥3 placebos on the card, macro without the trained bench) (F18).
6. cal-1's pattern: registered arms, decision table, subsampled gate passage.

**Change**
1. Scoring layer **M1**, registered as a new version, never used to relabel v3. Each cell records `channel` (tag / JSON / bare / empty), `official`, and `content` (official comparison on a JSON-aware extraction). Training gates use `content`; channel violations get their own no-harm count; tests use `official`.
2. One dispatch mode: rollout and gate both interleaved in item blocks (F7); identical requests agree 0.88 within 10 min vs 0.74 after 1 h (F27). Spacing repeats ≥2 min is free but has no measured benefit (E4 critic R2).
3. Regime covariates per cell (completion tokens, answer-only flag, tag share, timestamp, request hash); regime classified from reference arms only (E2 critic, missing #4).
4. Decision unit = a version (merged package, one hash) on fresh batches sized from the card-regime SD that S2 measures; per-rule attribution descriptive.
5. A positive control in the owner's regime: card-minus-bullet add-backs, plus a pass- or random-panel toggle (detection 0.001 → 0.965; F12).
6. LiveMath reported meta/non-meta; OfficeQA base prompt pinned if S1 finds a pin; ALFWorld action guard for every arm (F24).
7. v4 scope: B-fixes + M1 now; P1/P4/P5/P6 wait until S2 picks the gate, then run as proposer A/B on shared batches.
8. Budgets in ledger tokens: cal-1 settled 27.5M against 17.6M charged (×1.56, F32); every cap = 2× the charged estimate.

## 3 接下来的实验序列

Cost anchors, charged tokens per cell (F33): five-card SearchQA 4.7k (cal-1 `ids-full` mean 4,669), LiveMath 4.4k, OfficeQA 8.4k, SpreadsheetBench 4.3k. Ledger ≈1.56× charged.

**S0 — re-score and regime audit (week 1; 0 model tokens).**
- Design: freeze M1's extraction and covariate code; then apply it to every archived training-side cell — cal-1 (8,800), v3 train/screen/confirm (all stages, both chains), D1/D8/E2/E4/E5/E9/D12 pilots. No evaluation or test directories. Correct cal-1's "21 unknown runs" to 15 (D8 critic).
- Decision: adopt `content` for training gates (correctness fix, F4); size S2 from the re-scored card-regime SD.
- Pivot: if re-scoring flips any I-ds verdict or moves `ids-full` by >3 points, the channel matters in the card regime too → audit OfficeQA/LiveMath tag-only scorers before S1.

**S1 — OfficeQA regime pin (weeks 1–2; ≈9.3M charged, cap 19M).**
- Design: 74 training items × 1 run × 3 card arms × 5 windows over 3 days, item-blocked: B0 = v3 base; B1 = v4 framing (B13/P7) + answer contract at both ends (E7 critic: safe); B2 = B1 + OfficeQA-only "write the calculation, then the tag".
- Decision: adopt the variant with the smallest between-window SD if that SD ≤ 5 points and its mean ≥ B0 − 3; ties → B1.
- Pivot: every variant SD ≥ 8 → OfficeQA readouts need two windows with recorded regime, and the owner decides whether OfficeQA stays the hub.

**S2 — cal-2: calibrate in the card regime (weeks 2–3; ≈19.7M charged, cap 40M).**
- Design: SearchQA, 300 least-used items outside the 200 v3/cal-1 items × 2 runs × 7 interleaved arms, base from S1 (4,200 cells, ~5 h at 6 workers): P = five cards; P′ = byte copy; A1, A2 = P minus one SearchQA-card bullet (fixed in the registration); Q1–Q3 = P + one length-matched content-free rule. Free add-ons: planted-effect power curves (+2/+3/+5) on P/P′ cells; replay of v4's C1 on the add-backs A→P.
- Decision (first match): **D** D1 accepts P′, or the P′−P CI excludes 0 → dispatch broken, fix. **C** D1 accepts any Q, or max|Q−P| ≥ 3 points → acceptance must also beat a co-run placebo package; recompute n; if n exceeds the pool → B. **A** planted power ≥ 0.6 for +3 at 300×2 and every A_j whose CI excludes 0 has its add-back accepted → S3. **B** otherwise.
- Pivot: Row B ends "rule beats card" on SearchQA for this solver. If v4's C1 passes known add-backs < 50% while D1 passes ≥ 80%, recommend D1 replace v4's gate.

**S3 — one version-level learning stage (weeks 3–5; only after Row A or C; ≈31M charged + ≈3M GLM, cap 62M).**
- Design: I-ds on SearchQA with v4 B-fixes + M1, ≤3 steps. Proposal batches of 100 (the 200 v3/cal-1 items, then the 100 remaining). Acceptance batch = S2's 300 items × 2 runs, ≤3 decisions (D1), parent re-run in each round (registered exception: no method role has seen them). Round 1 adds P′ and a length-matched placebo package; after an acceptance the card rides as an extra arm in the next round. Per step 0.94M rollout + 5.64M round.
- Decision: accept iff one-sided 95% item-bootstrap LB > 0 and mean ≥ +2 points (Row C: LB also over the placebo package). "Learned − card established (training side)" iff an accepted version beats the card again next round.
- Pivot: 0 accepted in 3 steps and pooled 95% upper bound of candidate − card < +3 → "no learned increment ≥3 points for this solver", a bounded negative → pivot plan below. Owner option: a fresh SearchQA training block from never-sampled source rows, excluded against the split manifest (D10 critic, missing #8).

**S4 — evaluation-only transfer readout (weeks 5–6; only if S3 accepts and the owner amends registration §2.2; ≈14.5M charged, cap 29M).**
- Design: accepted version vs card, paired in one interleaved session, on the targets' *training* pools read once after the freeze: OfficeQA 74×4 (+ placebo package), LiveMath 283×2 (meta/non-meta), SpreadsheetBench qualified ×2. A readout only: it never edits, scopes or reverts the Skill. No test pools.
- Decision: "no drop" iff LB > −margin (OfficeQA 10, LiveMath 9, SpreadsheetBench 15; D8); "transfer gain" iff LB > 0; MDE printed per row.
- Pivot: SearchQA gain gone under sub-EM and OfficeQA unmoved → report the rules as SearchQA conventions, not generalization (F16).

**Answerable after the fix:** learned − card at ≥3–4 points on SearchQA; whether an accepted gain is content or surface form; proposer variants (v4 P-changes, D13) A/B'd at known power; version-level transfer ≥7–10 points. **Still unanswerable:** single-rule decisions at 1–3 points, rule-sized transfer, any SpreadsheetBench/ALFWorld rule claim.

**If learned − card is still ≈ 0** (Row B, or a bounded S3 negative): (1) write the calibrated null as a measurement paper (D10's direction: resolution, placebos on the card, the bound), spending no holdout; (2) probe content headroom where it exists — OfficeQA's card failure mass is +35.8 points, mostly substantive codes (D9), visible only for version-level effects ≥10 points; (3) owner decisions: a solver regime where learned − generic was +4.6/+6.7 (GLM, F21) with baseline reruns costed, or recast objective 1 as executable scoring checks.

## 4 如何服务两个目标

- **Objective 1 (Skill + verifier-rubric co-evolution): deprioritised for 4–6 weeks.** No measurable fitness for verifier changes exists (F28–F30); with S_t = S_{t−1} there is nothing to co-evolve against, and DecoEvo warns against updating the rubric on solver scores (E1 critic). What survives is the instrument as an executable rubric — channel parser, alias sets, action guard — validated on frozen labels (D9's 54-item audit; E6 critic's ~95% form/substance agreement). That is a different claim; the owner decides whether it counts.
- **Objective 2 (evolve on one, evaluate on others, no validation set): served** by M1's paired co-scheduled readout, S1's OfficeQA pin and S4, with no real-pool guards. Honest limits: SearchQA is the only fine-grained source and its only similar target is OfficeQA, the noisiest gauge; evolving on OfficeQA would give the best pooled transfer resolution (≈3 points at test sizes, E5 critic) but the worst acceptance power. Rule-sized transfer is out of reach; version-level transfer of ~7–10 points is the realistic claim.

## 5 风险与证伪

1. **Lens falsifier:** Row A followed by a tight S3 null → the method, not the instrument, is the bottleneck; method work becomes the priority, now measurable.
2. S0 shows the channel irrelevant in the card regime (expected from F6): the scorer fix helps E-ds only.
3. Card bullets inert and placebos ≈ rules → the card is saturated for this solver.
4. OfficeQA regime unpinnable → hub claims stay regime-conditional. B2 also pre-empts a learnable behaviour and shrinks OfficeQA headroom.
5. Pool depletion and reuse: 59 never-used SearchQA items (F14); S2 items reused in S3 under a registered exception.
6. Cost overrun: cal-1 ran at twice its smoke estimate (cal-1 registration L113–117); caps use ×2.
7. Base-prompt changes (B13/P7, B1/B2) break comparability with v1/v3 baselines; a new main table needs baseline reruns (not costed here).
8. One-session SDs can be 2–3× off (D11 critic: π_rep varies by window); size from the upper band.
9. The owner may refuse S4's use of target training pools or the deprioritisation of objective 1.

## 6 事实清单

| F | claim | source | type |
|---|---|---|---|
| F1 | ids-full +0.094 [0.05, 0.14]; seed-only +0.089 | docs/handoff/cal1-registration-20261020.md L137 | RUN |
| F2 | C1 passage n=11: ids-full 75.8%, seed-rule/seed-rule3 0%, cand 7.7%, null 0%; n=6 47.9%, n=20 99.0% | cal1 L139; docs/handoff/overnight-report-20261021.md L19 | RUN+SIM |
| F4 | JSON replies 0/364 pass; 414/424 also tagged | D5/critic-result.json refuted_claims | CRITIC |
| F5 | JSON-aware: control:3 −0.0975→−0.0025, cand −0.026→+0.0675; −9.8→−0.25 | E7/result.json evidence; overnight L51 | REPLAY |
| F6 | I-ds s1 parent + 3 screened rules tag share 1.000, 0 JSON; E-ds s1-r1 screen +0.75→+13.75, confirm −2.50→+12.25 | E7/critic-result.json refuted_claims #1 | CRITIC |
| F7 | single-arm train 1.0% untagged vs interleaved 9.0/6.5/10.1% | E6/critic-result.json refuted_claims R2 | CRITIC |
| F8 | card−scaffold +0.0325 n.s. single-arm; no positive control for rule-on-card | E6 critic refuted_claims R3 | CRITIC |
| F9 | OfficeQA hash cc516459, 74 items: +20.3 (SE 5.2); 8/9 v3 units answer-only | E9/critic-result.json refuted_claims R4, notes_cn | CRITIC |
| F10 | same text, 60 OfficeQA items: 50.8/26.7/26.7/34.2%; SD 11.4 | D12/result.json evidence | RUN (archived) |
| F11 | rule-vs-card sd 0.243 → 186/515 items for +5/+3 | E7 critic refuted_claims #4 | CRITIC |
| F12 | per-step power 0.19–0.26; C1′ fixed-panel (Clark 1973); toggle 0.001→0.965 | D8/result.json recommendation; D8/critic-result.json refuted_claims R2, R3 | SIM |
| F13 | smallest certifiable 0.042/0.056/0.103/0.122/0.153 | D1/result.json evidence [E] | SIM |
| F14 | pools 600/74/283/≤120q/57, tests 400/172/125/279q/134; 59 never-used SearchQA | docs/handoff/coevo5-registration-v6-20261017.md L84–88; E5/critic-result.json missing #7 | DOC/CRITIC |
| F15 | ~73% of 54 card-failed SearchQA items substantively right (1 rater) | D9/critic-result.json refuted_claims | CRITIC |
| F16 | under sub-EM deepseek effects ≈0; SearchQA effects are surface form | E7 critic refuted_claims #5 | REPLAY |
| F17 | no "TC + rule" arm; 0–3 ceiling not established | D9 critic missing, notes_cn | CRITIC |
| F18 | placebos only on scaffold; ≥3–4 on the Seed needed (~4.5M each) | D11/critic-result.json refuted_claims #7 | CRITIC |
| F19 | D1 pilot 130 fresh × 2 × 6, 2,388,219 tokens: card +0.162 accepted, copy/placebos rejected, no learned package | D1/result.json pilot | PILOT |
| F20 | v3: 15 screened, 2 passed screen, 0 confirm; deepseek 139,024,462, GLM 7,804,250 | docs/results-and-lessons.md L142 | RUN |
| F21 | "未建立，不是已证明没有"; learned − generic +4.6 [+0.5,+9.0], +6.7 [+2.5,+11.3] (GLM) | results-and-lessons.md L139; D9 critic refuted_claims | RUN |
| F22 | v4 keeps C1–C4′; fresh-batch acceptance out of scope | docs/handoff/v4-plans-20261021/spec.md L138, L177–178 | DOC |
| F23 | B7: format predicate = scorer's extraction (JSON still fails) | spec.md L69–74 | DOC |
| F24 | guard the ALFWorld action interface for every arm | D14/report.md L228 | analysis |
| F25 | meta option is the key in 129/129 of 283 | D7/result.json evidence | DATA |
| F26 | OfficeQA in all 3 similar pairs; guard vs clean claim | skillopt/coevo5/protocol.py L18; E9 critic refuted_claims R1 | DOC/CRITIC |
| F27 | canary expected diff 0, ~5% alarms; agreement 0.88 vs 0.74 | E2/critic-result.json refuted_claims, confirmed_claims | CRITIC/PILOT |
| F28 | generated panels 122/122 pass | D12/result.json pilot.result | PILOT |
| F29 | model-written checks BA 0.47–0.55 | E1/result.json pilot.result | PILOT |
| F30 | ladder τ ceiling 0.63 [0.40, 0.81] | E10/critic-result.json refuted_claims | SIM |
| F31 | tests read once after freeze, with consent | docs/project-status.md L118 | DOC |
| F32 | cal-1 ledger 27,481,897; receipts 14.0M, charged 17.6M | cal1 L129–130; E7 critic refuted_claims #8 | RUN |
| F33 | charged/cell: ids-full 4,669, scaffold 2,780; v3 card cells 4,088/3,969/7,927/4,273 | E9 critic refuted_claims R6; D6/critic-result.json refuted_claims #5 | RUN |

## summary_cn

建议先修“量尺”（判分与验收办法），再改方法。标定实验 cal-1（用效果已知的文字检验门槛）显示，现行逐条门槛 C1（每条规则只看6–11道题）认得出+9分的整套任务卡，认不出1–3分的规则；分数还混着无关因素：答案写成 JSON（带花括号的格式）被判错，OfficeQA（文档问答）同一文字换时段差20分。故第三版实验 v3 收下0条规则只说明“没测出来”，不是“没用”。五步：S0 零花费重判旧记录；S1 试用提示词稳住 OfficeQA 的回答方式；S2 在“任务卡上加减一条”的真实场景重做标定，看能否认出3分；S3 认得出才在 SearchQA（检索问答）上学一段，按整版本在没用过的题上验收；S4 收下了才在别的数据集训练题上只读评测迁移（需您同意，不当门槛）。若修好后仍不胜过任务卡，就写成有分辨率保证的负结果，请您定是否换做题模型或调整目标一（技能与评分细则一起进化）。
