# Method first: what the co-evolution mechanism should become

**Lens:** 方法优先.

**Tags:** [run] model run on training items; [replay] archived-cell re-analysis; [pilot] exploratory run; [lit] critic-reported, unchecked.

[S#] refers to §6. No test pool was opened, and the repository is unchanged.

## 1. 诊断 Diagnosis

### 1. The evolved unit is smaller than the instrument can resolve

- Rule-sized texts move SearchQA by about 0 (+0.004, −0.030, −0.026). They pass C1 0–7.7% of the time, while the +9.4-point card passes 75.8% [S1–S3, run].
- v3 accepted 0 of 49 proposals [S6]. On never-seen halves, all seven I-ds rules score between −0.107 and +0.005 [S8, replay].
- Detecting a 4.8-point rule-on-card effect takes 200 items [S11], and v4 keeps the per-rule test [S24].

### 2. Text moves answer form, and form breaks transfer

- Under containment scoring, every SearchQA effect vanishes, the card's included [S12].
- About 73% of the card's remaining failures are acceptable answers that exact match rejects (a critic agent's single-rater reading). About 6 points are substantive [S13].
- Foreign cards cost OfficeQA −20 and −27 through answer-only replies, and the LiveMath card costs it −9.5 [S15, S16, pilot].
- No increment over a good instruction exists anywhere [S5].

### 3. The instrument drifts and fresh items are spent

- Terse and verbose regimes alternate [S17].
- The same Skill on the same 74 OfficeQA items moved +20.3 points across windows [S18].
- v3 harvested at 1.0% untagged replies but gated at 6.5–10.1% [S19].
- 59 of 600 SearchQA items are unused [S20]; the pools certify only effects ≥4.2/5.6/10.3/12.2/15.3 points [S10].

### 4. The verifier lacks a ground-truth anchor

- Generated items saturate (scaffold 0.891), missed a real −9.5 harm, and showed effects real items did not (30/6 vs 11/12, 9/9) [S16, S27].
- Model-written checks reach a balanced accuracy of 0.47–0.55, and only the form checks held [S22].
- 0 promotions, 0 new natural detections [S25, S26]; a code anchor held [S29].

### 5. Where rule effects land is unresolved

- v3's harm on the card parent sat in scope (10 up / 21 down, post hoc), and E-ds's s1-r1 lost 0.047 off its evidence items [S7, S8].
- But the card's own effect ignored a task-feature condition: +0.053 inside it against +0.174 outside [S7].
- Card + learned rule versus card was never run [S14].

### Answers to the four questions

- **Unit:** a package of rules gated by input-only code predicates, accepted once per version on a large unseen source batch against card and placebos; gating itself is tested, not assumed. **Verifier:** executable checks with ground-truth fitness on source items, never solver gains [S30, S31]. **v4:** bug fixes only, no chain. **Next:** M1.

## 2. 停 / 留 / 改

### Stop

- ST1. Chains that gate each rule with C1, including the v4 chain (cap 1.16–1.17B) [S3, S24, S28].
- ST2. Using generated items as gates or as transfer evidence, until admitted checks certify them [S16, S27].
- ST3. Using LLM judges or lenient scores as gate statistics. Lenient scoring gives s1-r1 +0.068, against −0.026 officially [S21].
- ST4. Using target-bench pools as in-loop guards. That amounts to a validation set in disguise [S23, S43].
- ST5. Using SearchQA as the source [S12, S13, S20].
- ST6. Running the five-step sequential chain next [S10].
- ST7. Learning from the LiveMath meta option before the card states it. The option is the key in all 129 items that carry it [S32].

### Keep

- K1. The card as parent, and the yardstick "learned versus good instruction" [S5, S14].
- K2. The five-link flow, with every change inside a link [S33].
- K3. Interleaving; duplicates ≥2 minutes apart (resends caused 5 of the card's 6–8 "gains" [S55]); ≥2 placebos with placebo-relative acceptance (D1's absolute rule accepted a placebo [S34]).
- K4. D1's acceptance procedure: one frozen package and one interleaved round on never-proposed items, accepted when LB95 > 0 and mean ≥ 0.02. No role sees the outcomes [S9].
- K5. when/do/otherwise, and v4's fixes B1–B17 [S24].
- K6. Official binary metrics, and one consented test read after freeze [S35].

### Change

**CH1. Unit = gated rule package.**
- Each rule is a deterministic predicate over what the solver sees, plus a format-neutral text of at most 600 characters.
- A rule is injected only where its predicate fires. Elsewhere the prompt is byte-identical to the card.
- Cards are gated as well, so each bench sees only its own card. With the five-card parent, OfficeQA gained +4.7; with OfficeQA's own card, +13.5 and +17.6. Whether that gap is bleed or regime is unresolved [S18].
- Code conditions need no judge: one condition agreed 97/97, though it read the reply [S36].

**CH2. One gate per version**, on an unseen source batch, against the card and two placebos [S9].

**CH3. Verifier = executable check suite with ground-truth fitness (M3).**
- It is coupled to the Skill only through data: failures and rule texts feed check proposals, and admitted checks decide which rules and generated items enter.
- This follows DecoEvo and CURE [S30, S31, lit].

**CH4. New scorer version.** JSON-aware extraction for all arms, plus a regime tag per cell. This is the owner's decision under §5(d) [S37].

**CH5. v4-min.** B1–B17, P2, P5 and P6. Code predicates replace P1's three-vote judge. No chain [S24, S38].

**CH6. Source chosen by rule.**
- Requirements: ≥1,000 unseen training items; ≥15% content failure under the card; ≤2k tokens per cell; an official metric not dominated by surface form.
- No registered pool qualifies.
- FinQA does [S39–S42]: 6,251 training items, a card content score of .787, 1.1–1.9k tokens per cell, a numbers-only metric, and executable programs.
- Precedent: the 10/13 bench swap [S44].
- This needs an owner decision, with sim(FinQA) = {OfficeQA}.

## 3. 接下来的实验序列 (4–6 weeks)

### E0. Instrument build (week 1)

- **Purpose:** make M1, M3 and M4 valid.
- **Design:**
  - v4-min, the scorer version, and a cross-pool item ledger.
  - A predicate compiler and a gated renderer.
  - Hand-written admission checks: format neutrality, conflict with each bench's public answer contract, and predicate safety.
  - A FinQA port as a new protocol version: official metric with the card checked against it; pinned draw (300 proposal items, five 1,000-item acceptance batches, reserve); sealed test split; licence check [S42, S43].
- **Items:** none solved.
- **Cost:** 0 solver tokens. About 3 h of agent work [S38], 1–2 days for the scorer [S40], and one Codex review.
- **Decision rule:** FinQA approved → M1 on FinQA; otherwise on up to ≈99 non-meta LiveMath items outside v3's draw (card fails 48/110 such runs), pre-registered as low-powered [S13, S32]. If fewer than half the conditions compile to input-only predicates, drop A2.
- **Pivot:** if the FinQA card fails its scorer check twice, port TAT-QA (13,251 items) [S40].

### M1. Decisive mechanism test (weeks 2–3)

- **Purpose:** test whether a learned, format-neutral package beats the card and a placebo on unseen items, and whether gating helps.
- **Design:**
  - Harvest card failures on 300 items × 2 runs.
  - One analyst pass produces at most 5 rules, which must pass admission.
  - One interleaved session on 1,000 unseen items (duplicates ≥120 s apart): A0 card ×2; A0d duplicate ×1; A1 package always on ×2; P1, P2 always-on length-matched placebos ×2 each.
  - On fired items only (≈400 at share 0.4): A2 gated package ×2; Pg gated placebo ×2.
- **Items:** 1,300 FinQA training items. The fallback harvest comes from archived v3 LiveMath cells.
- **Cost:**
  - 11,200 cells × 1.1–1.9k [S40], plus at most 0.75k of package text, comes to about 17–26M receipts.
  - Ledger cap 55M, because cal-1's ledger was about 2× its receipts [S4].
  - GLM 0.2–0.5M, based on E8 at 0.19M and D13 at 0.18M [S45].
  - Fallback: about 1,050 × 3,969 ≈ 4.2M [S46].
- **Decision rule** (one-sided 97.5% item bootstrap):
  - **Ha GO**, on all items: LB(A1−A0) > 0, LB(A1 − mean(P1, P2)) > 0, and A1−A0 ≥ +2 points.
  - **Hg GO**, on fired items: LB(A2−A0) > 0, LB(A2 − mean(Pg, P1)) > 0, and share × (A2−A0) ≥ +2 points.
  - The test can resolve about 1.9 points (all items) and about 3 points (fired items), scaled from 142 items per 5 points [S41].
  - **NULL:** UB95(A1−A0) < +2 and UB95(A2−A0) < +5.
  - **Otherwise:** one 1,000-item extension, only if a point estimate reaches +2 (all) or +3 (fired), then the same rules once. Without an extension the verdict is "no detectable gain".
- **Pivot:** Hg GO → gated unit to M4. Ha only → always-on acceptance, no "no drop by construction" claim. NULL → stop text-rule learning for this solver class; the last option is state-gated ALFWorld procedures on an expanded public training block (105.7k tokens per episode [S47]), the owner's call.

### M3. Verifier evolution on ground truth (weeks 2–4, GLM only)

- **Purpose:** the verifier half of objective 1, kept uncoupled from solver scores.
- **Design:**
  - The fixture uses source items only: M1's harvest and A0 cells.
  - Seeded variants are added: swapped key, removed referent, or a changed table value whose re-executed program changes the gold answer [S41].
  - Unmodified items are known-valid; items split into write and score halves.
  - In each of three rounds, GLM proposes at most 3 code checks from the suite's write-half errors.
  - A check is admitted iff score-half recall rises at fixed precision (LB95 > 0) and known-valid false rejects stay ≤2%.
- **Items:** about 2,600 cells, plus about 300 variants per round. Other benches appear only descriptively.
- **Cost:** 0 solver tokens. GLM 0.6–1.5M, based on E1 at 0.86M and E6 at 1.32M [S22, S45].
- **Decision rule:** "the verifier evolves" iff at least one check is admitted in at least 2 of the 3 rounds. Otherwise report it as a fixed, hand-written instrument.
- **Pivot:** checks that only restate the card's format rules → claim no co-evolution. Working checks → execution-verified variants may enter M4 as harvest material, never as acceptance evidence [S51].

### M4. One-source chain + one transfer read (weeks 4–6, only after GO)

- **Purpose:** objective 2.
- **Design:**
  - At most 3 versions, each accepted as in M1 on a new 1,000-item batch and each harvesting the previous batch's failures.
  - The verifier is frozen within a version and updated between versions by M3's rule.
  - Then, with consent, one read of the five registered tests (400/172/125/279/134 [S49]) plus sealed FinQA: card once on every item; card + package and card + gated placebo on fired items only (non-fired prompts are byte-identical); OfficeQA in two windows [S18].
- **Cost:** 11–21M per version; test read ≈22M for the card arm (ALFWorld's ≈14M skipped if nothing fires) plus ≈14M for fired arms at share 0.3. Whole-plan worst case ≈160M, close to v3's 139M [S6]; ≈20–50M if M1 stops it.
- **Decision rule:**
  - "The evolved bench improves" if the source-test LB95 > 0.
  - "A similar bench improves" if OfficeQA's fired-subset estimate is > 0 in both windows. This is descriptive only, given an MDE of 6.6–7.7 [S50].
  - Each dissimilar bench must drop by at most 3 points, or never fire.
- **Pivot:** if the source-test CI includes 0, M1 did not replicate. Stop.

## 4. 如何服务两个目标

### Objective 1 (co-evolution)

- Each artefact has its own ground-truth fitness: the Skill, acceptance on unseen source items against card and placebos; the verifier, defect recall and false rejects on a source fixture.
- The coupling runs both ways, through data. Skill failures and rule texts become fixture rows and check proposals, and admitted checks gate which rules and generated items enter. This is the text-plus-code rubric the owner asked for [S51].
- **Limit:** M3 can show that the verifier evolves. Whether that helps the Skill can only be tested after a GO.

### Objective 2 (one source, no validation set)

- No target item enters any decision [S43, S52]. "No drop on dissimilar benches" holds by construction where predicates stay silent and is contract-checked where they fire; similar-bench gains are read once, on sealed tests.
- This lens **deprioritises the positive-transfer half** until there is a gain on the source: before any acceptance, every transfer cell is 0 [S53].

## 5. 风险与证伪

1. **Gating may cut off diffuse effects** [S7]. The A1 versus A2 comparison tests this.
2. **Input-format gates also cover OfficeQA, TAT-QA and FinQA** [S54]. Only the contract check and the final read protect similar targets.
3. **Harm within scope** [S7]. The placebo-relative gate guards against it.
4. **Regime × text interaction survives interleaving** [S17, S18]. A regime-stratified read is pre-registered.
5. **Port risk.** E3's scorers were approximations, and its % rule was invented [S39, S42].
6. **Low prior.** Under FinQA's numeric metric expert − card was 0.0, and the E3 critic rates feasibility "low" [S42]. NULL is the likely M1 outcome; it settles the question for 20–50M instead of a 1.16B chain and is no reason to tune.
7. **Verifier triviality.** Labels derived from gold are directly computable. Only gold-free uses count as evolution: rule admission and generated-item validity.

**Falsified if:** M1 returns NULL on a source with at least 15% content failure, M3 admits no check, or M4's source test fails to replicate M1.

## 6. 事实清单

Path keys (under docs/):
- `Xr` is handoff/feasibility-20261021/X/result.json, and `Xc` is the critic-result.json in the same folder.
- CAL is handoff/cal1-registration-20261020.md.
- RL is results-and-lessons.md.
- PS is project-status.md.
- V6 is handoff/coevo5-registration-v6-20261017.md.
- CW is current-workflow.md.

| # | Claim | Source |
|---|---|---|
| S1–S3 | Card vs the empty scaffold on 200 SearchQA items × 4: +0.0938 [0.0505, 0.137]. Bridges: +0.0037, −0.030, −0.026. C1 passage at n=11: card 75.8%; rule-sized arms 0%, 0%, 7.7%; null 0% | CAL L40, L137–139 |
| S4 | Ledger 27,481,897 tokens for 8,800 cells; receipts 14.0M | CAL L130; E7c refuted #8 |
| S5 | No increment established over a reasonable instruction; +0.1 [−1.6, +1.8] on bzero | RL L139; PS L156, L167 |
| S6 | Both v3 funnels end at 0; 139,024,462 deepseek tokens | RL L142 |
| S7 | Card effect +0.053 in scope vs +0.174 out of scope; I-ds rules 10 up / 21 down in scope (post hoc) | D4c missing #1; refuted_claims #3 |
| S8–S10, S34 | I-ds rules −0.107 to +0.005 on check halves; E-ds s1-r1 −0.047 on 186 other items. Pilot: card +0.162 accepted, placebos rejected. Accept iff LB95 > 0 and mean ≥ 0.02. Certifiable effects 0.042/0.056/0.103/0.122/0.153. The replay accepted control:2 | D1r evidence, pilot, design §6 |
| S11, S12, S14 | Rule-vs-card SD 0.243, MDE 4.8 at 200 items; under sub_em every SearchQA effect is surface form; card + rule vs card never run | E7c refuted #4, #5, missing |
| S13 | About 73% acceptable (single rater), about 6 points substantive; LiveMath non-meta 62/110 | D9c refuted, missing |
| S15, S32, S55 | Foreign cards on OfficeQA −26.7/−20.0. Meta option in 129/283 items, the key in all of them. No flips at ≥2 minutes; 5 of 6–8 gains came from resends | E4r evidence, verdict_cn §5, §7; E4c R5 |
| S16 | Generated panel: scaffold 0.891; missed the −9.46 harm | E9r evidence |
| S17 | Terse and verbose regimes alternate | E8c refuted #1 |
| S18, S23 | +20.3 across windows on 74 items; five-seed +4.7 vs card +13.5/+17.6; OfficeQA is SearchQA's only similar bench | E9c R1, R4, missing #2; V6 L71 |
| S19 | Untagged replies 1.0%/9.0%/6.5%/10.1% | E6c R2 |
| S20 | 59/600 unused | E5c missing #7 |
| S21, S35 | s1-r1 official −0.026 vs em_rob +0.068; official binary scores for gates | E6r evidence, recommendation |
| S22, S30 | Checks BA 0.474–0.548, only form checks held, 859,911 GLM tokens; DecoEvo [lit] | E1r; E1c missing #1 |
| S24 | v4 keeps C1–C4'; version acceptance out of scope; P1 three-vote judge | handoff/v4-plans-20261021/spec.md L122–141, L177 |
| S25, S27, S29, S31 | September V4 0 promotions; generated 30/6 vs real 11/12 and 9/9; the code filter held; CURE [lit] | E10c R3, R7, confirmed |
| S26 | V16: 0 new natural detections | CW L388 |
| S28 | v4 cap 1.16–1.17B | handoff/overnight-report-20261021.md L135 |
| S33, S35 | Method flow fixed; one consented test read | PS L116, L118 |
| S36 | Judge vs code 97/97 (reply overlap) | D13c confirmed |
| S37, S38 | Pending decision (d); v4 about 3 h plus one Codex review | PS L344, L179 |
| S39, S40 | FinQA card .700/.787 (80 × 2, approximate scorers); FinQA 6,251 and TAT-QA 13,251 items; 1.1–1.9k per cell; scorer 1–2 days | E3r evidence, design, risks, cost_estimate |
| S41–S43, S54 | 142 items per 5 points; executable programs; official FinQA compares numbers only; % rule invented; expert − card 0.0; feasibility low; seal tests; targets out of acceptance; OfficeQA's gate covers FinQA | E3c R2, R4, R9, M1, M3, M10, corrected_feasibility |
| S44 | BCB/KOR replaced on 10/13 | CW L56 |
| S45, S48 | GLM tokens: E8 194,566; D13 175,147; E6 1,324,475 | E8r, D13r pilot, E6r cost_estimate |
| S46 | LiveMath cell 3,969 tokens | D6c refuted #5 |
| S47 | ALFWorld 105.7k tokens per card episode | handoff/feasibility-20261021/D14/report.md L87 |
| S49 | Pools 600/74/283/120/57; tests 400/172/125/279/134 | V6 L84–88 |
| S50 | OfficeQA test MDE 6.6–7.7 | D5c missing #4 |
| S51 | Owner: mimic-train generation is a fake validation set; the verifier must evolve | PS L396, L403 |
| S52 | No held-out validation partition | V6 L124 |
| S53 | Transfer cells stay 0 | E2c refuted |

## summary_cn

诊断：现在的做法是"一条规则单独过门"，可单条规则的效果比测量误差还小，在校准实验 cal-1 里规则大小的文字几乎过不了门。能测到的提升几乎都来自答案格式，而格式文字恰恰让别的题库掉分。验证端自动出的题太容易，模型写的判卷程序接近瞎猜。

建议：
1. 进化单位改成"规则包"。每条规则配一段程序判断是否适用，只在适用的题上加进提示。整包在源题库（用来进化的题库）没见过的新题上一次验收，并和等长的无关文字（安慰剂）比较。
2. 验证端只进化能用标准答案或人为埋错来打分的检查程序，不拿做题分数当奖励。
3. 第4版协议 v4 只修 bug，不开正式运行。
4. 关键试验 M1 放在题多、错误以内容为主的财报计算题库 FinQA 上，需您同意新增；不同意就退到数学题库 LiveMath。M1 约花 1,700–2,600 万 token，若无效就停掉文字规则这条路线。
