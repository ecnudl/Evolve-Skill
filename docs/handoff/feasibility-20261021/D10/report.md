# D10: Paper positioning and related work

Explorer report, 2026-10-21 (Beijing time); the final version was written at 05:00. The repository is read only. Branch:
`research/active-evidence-skill-evolution`.

Every number carries its source and its denominator. Each claim carries a label:
- **[M]** measured, from our records or from a pilot I ran.
- **[E]** estimated from measured data under a stated model.
- **[C]** a claim or judgement.
- **[P]** taken from a cited paper and checked against its arXiv page, HTML or PDF text.

Terms used throughout:
- "Task card" is the I-ds/I-glm one-shot instruction seed, written from the public task card only.
- "Empty scaffold" is the empty five-section Skill.
- "Released Skill" is SkillOpt's published GPT-5.5 artifact (`ckpt/<bench>/gpt5.5_skill.md`).

This report supersedes the earlier `report_part1.md` and `report_part3.md` in this folder. They were written by an
earlier run of this explorer that stopped before its pilot was analysed. Section 12 lists the corrections.

## 1. Verdict

- **A method paper is not supportable on current evidence [C].**
  - On our five benchmarks, no learned Skill beats a one-shot task-card instruction. This holds for ours, for the
    SkillOpt and GEPA runs on GLM-5.3, and for SkillOpt's own released GPT-5.5 Skills when moved to our solver.
  - The validation-free v3 protocol accepted 0 of 49 proposals.
- **An honest measurement / negative-result paper is supportable, and feasibility is high for that framing [C].**
  Its thesis, with the evidence:
  1. Experience-learned Skills beat an empty prompt (+4.8 to +7.4 points, v1 test). They do not beat a task card:
     every estimate is 0 ± 2–3 points.
  2. Same-text re-runs and irrelevant placebo text move accuracy as much as learned rules do.
     - At temperature 0, about 10% of items flip between two single runs of identical text.
     - Four length-matched irrelevant rules move SearchQA by −9.8 to +3.6 points; the two extremes are significant.
  3. Under this noise, the common "accept if strictly better on the selection set" gate accepts a no-op 33–46% of the
     time on selection sets of 17–200 items [E].
  4. The gains that do exist come from three sources: answer-format conventions, one benchmark-construction shortcut,
     and generated test items that flatter the learner on OfficeQA.
- **Today's pilot adds two clean anatomy results [M]** (section 5; deepseek-v4-flash; training items only).
  - **SearchQA.** SkillOpt's released GPT-5.5 Skill scores −9.1 [−13.5, −4.9] points below our task card and equal to
    the empty scaffold.
    - Almost all of the deficit is answer-tag non-compliance: 16.5% of its replies lack the `<answer>` tag, versus
      2.0% under the task card.
    - With untagged replies read leniently, the gap is −1.8 [−5.3, +1.5].
    - This holds although all 200 items are in SkillOpt's own training or selection split.
  - **LiveMath.** The released Skill raises meta-option items by +27.8 [+15.6, +40.0] points.
    - Two bullets about the meta option carry all of that gain. Without them the effect is +2.2 [−7.8, +12.2].
    - The same Skill costs −17.1 [−34.3, 0.0] on items without the meta option.
    - Weighted to the pool's 45.6% meta share, the net is +3.3 [−7.2, +13.9].
    - By the benchmark's own construction, the meta option replaces the correct answer whenever it appears
      (LiveMathematicianBench paper, Section 2).
    - SkillOpt attributes its whole LiveMath gain (GPT-5.5: 37.6 → 66.9) to a single accepted edit whose rule
      prefers the "stronger result" option.
- **No checked method paper has the controls that would expose this [P].**
  - 0 of 14 optimizer and memory papers run an identical-text re-run control.
  - 0 of 14 run an irrelevant-text placebo.
  - 4 of 14 report run-to-run or fold variance for their main comparison.
  - 2 of 14 compare against a curated or structured instruction: SkillOpt's human Skills and Dynamic Cheatsheet's
    DC-∅.
  - Four close 2025–26 evaluation papers point at the gap:
    - Zhao et al. 2026 (2610.22984): self-evolving agents repair failures but do not generalise. No variance, no
      instruction baseline.
    - SkillsBench (2602.12670): self-generated Skills do not help. It names length-matched random or irrelevant text
      as missing future work.
    - Liu et al. 2026 (2608.02636): same five-benchmark suite. "Evolution is sparse" (55 of 388 candidates).
    - SkillBoost (2607.26643): skill overfitting.
- **The single experiment that would most strengthen the paper [C]** is one pre-registered confirmatory audit.
  - **What it compares.** Several learned Skills, each against the task card.
    - The learned Skills: our E-glm, SkillOpt-glm, GEPA-glm, and SkillOpt's released GPT-5.5 Skills with their own
      format lines removed.
    - The controls: an identical-text duplicate of the task card, the empty scaffold and two length-matched
      placebos.
  - **Items.** Unseen items, sized for an equivalence test:
    - about 450 items per benchmark at 4 runs for a ±3-point margin;
    - about 1,000 items at 4 runs for ±2;
    - at 1 run, about 800 and 1,800 items respectively.
  - **Scoring.** The strict official scorer is primary; a pre-registered lenient reader is secondary.
  - **Cost [E].** About 56M deepseek tokens without OfficeQA, and about 111M with OfficeQA's protected test split
    (owner consent needed).
  - Section 8 has the full design.
- **Venue [C].**
  - Best fit: TMLR (rolling; its acceptance criteria do not require novelty) or COLM 2027 ("A Sober Look", COLM 2025,
    is the precedent). The COLM 2027 call is not out; the deadline is about late March 2027 [E].
  - Next: the NeurIPS 2027 Evaluations & Datasets track (about May 2027, [E]) or ICML 2027. ICML 2027's call is not
    out; one aggregator projects about 22 Jan 2027 [E].
  - A workshop version can go first: ICBINB, or Insights from Negative Results if a 2027 edition runs.
  - ICLR 2027 has passed (25 Sep 2026, official call).

## 2. What I did (and did not do)

1. **Context.** Read the shared context (`context.md`, `context-batch2.md`).
   - Ledger entries read (`docs/results-and-lessons.md`): 10/11, 10/12, 10/13, 10/16 and 10/19.
   - Also read: `docs/project-status.md`, the cal-1 registration with its appended readout
     (`docs/handoff/cal1-registration-20261020.md`), `ckpt/README.md`, `data/README.md` and the two released Skills.
   - Cross-checked against the D5 and D7 sibling reports.
2. **Literature, 2023–2026.**
   - The earlier run checked about 40 papers against arXiv abstracts, HTML, PDF text (`pdftotext` for Promptbreeder
     and Dynamic Cheatsheet) or proceedings pages. Its notes are in `notes.md`.
   - Today I re-checked the load-bearing items:
     - SkillOpt: Table 1, the gate rule, no variance reported, the LiveMath edit history.
     - Zhao et al.: frameworks, recovery numbers, stream filter, no variance.
     - SkillsBench: both versions.
     - GEPA, ACE, MAGE, RLMOpt and p1.
     - "A Sober Look" (venue).
     - The Dynamic Cheatsheet DC-∅ table, from the PDF text.
   - Added three papers: LiveMathematicianBench's construction of the meta option, Liu et al. 2026 (2608.02636)
     and SkillBoost (2607.26643).
   - Items I could not verify are marked and are not used in counts.
3. **Re-analysis of the complete cal-1 round, at zero cost.**
   - Data: 8,800 cells = 11 arms × 200 SearchQA training items × 4 runs; deepseek-v4-flash, temperature 0; 8,785 cells
     with a verdict.
   - Source: D9's dump `/data/feasibility/D9/v2/cal1_cells.jsonl`. Its per-arm tallies match the registered readout.
   - What I computed:
     - re-run "recovery" matched to Zhao et al.'s stream filter (new today);
     - per-item difference SDs and the item counts an equivalence test needs (new today);
     - literature-style gates under an exchangeable no-op null (`d10_gate_null.py`, from the earlier run, logic
       re-checked).
4. **Overlap with SkillOpt's upstream splits**, using only the released train and val ID lists; the test list was
   never opened.
   - All 200 cal-1 SearchQA items are in upstream train (127) or upstream selection (73).
   - Of the 80 LiveMath pilot items, 15 are in upstream train/val. The other 65 come from months 2026-03 to 06, after
     the upstream months 2025-11 to 2026-02.
5. **Paid pilot** (section 5): SkillOpt's released GPT-5.5 Skills against our task card under deepseek-v4-flash, on
   training-pool items.
   - The earlier run launched it at 01:01. It finished at 02:47 and was never analysed. I analysed it today.
   - Cost: 2,578,134 tokens (LiveMath 925,232 + SearchQA 1,652,902), within the ~3M cap. NEW machine, 6 workers.
6. **Not done.**
   - No test or holdout pool was read, listed or copied.
   - The LiveMath pilot used the coevo5 training pool, which is the historical `train` + `val` parts by construction
     (`skillopt/coevo5/data.py: pool()`).
   - No repository file was modified; no credential was printed.

## 3. Literature survey

The column "strongest instruction-like baseline" names the strongest hand-written or one-shot prompt a paper compares
against, as opposed to another optimizer. Effects are in each paper's own metric.

### 3.1 Prompt and Skill optimizers [P]

| Method (venue) | What is accepted, by which rule | Dev / validation data the rule relies on | Strongest instruction-like baseline → reported effect | Variance reported? |
|---|---|---|---|---|
| OPRO (Yang et al., ICLR 2024) | Meta-prompt keeps the top-20 instructions by **training** accuracy | Fixed training subset (GSM8K 3.5% of train; BBH 20% per task); no separate val | "Let's think step by step", empty string → up to +8 (GSM8K), up to +50 (BBH) | Main tables: single values. Ablations: mean ± SD over 3 repeats. Notes training accuracy often 5–20 above test |
| ProTeGi / APO (Pryzant et al., EMNLP 2023) | Beam search (b = 4, 6 steps) + bandit arm selection | Training minibatches; 50 dev / 150 test per task | One-line engineer prompt → +15.3% average (up to 31%); +3.9 over the best competing method | Mean of 3 trials (no SD in main table); appendix SE over 12 replicates |
| PromptAgent (Wang et al., ICLR 2024) | MCTS; best node on the highest-reward path | Held-out subset of training data (default 150) | Short human task prompts, zero-/few-shot → +28.9% **relative** (BBH); +11.2% relative over APE | Single point estimates |
| Promptbreeder (Fernando et al., ICML 2024) | Binary-tournament GA; the fittest of the whole run goes to test | Random batch of 100 training examples; no val | PS+ (PaLM 2-L) GSM8K 60.5 → 83.9 (OPRO's prompt 80.2). The winning prompt was the single word "SOLUTION" | None |
| MIPRO / MIPROv2 (Opsahl-Ong et al., EMNLP 2024) | TPE over (instruction, demos); top minibatch candidates re-scored on the full train set | Train (e.g. HotPotQA 500/500/2000 train/dev/test); dev used to iterate on methods | Unoptimised program → instruction-only gains ≈ +0.7 to +8.6 (demos matter most) | 5 runs per method + Wilcoxon test; no SD in tables |
| TextGrad (Yuksekgonul et al., Nature 2025) | Update kept only if better than the previous iteration on validation | 50/100/100 train/val/test (BBH tasks) | Zero-shot CoT → Object Counting 77.8 → 91.9 (DSPy 84.9); Word Sorting 76.7 → 79.8 (= DSPy); GSM8K 72.9 → 81.1 (= DSPy) | None for prompt rows (5 seeds only for code optimisation) |
| GEPA (Agrawal et al., ICLR 2026 Oral; arXiv 2507.19457 v2) | A new candidate must improve on a **minibatch of 3** (no margin), then is scored on the Pareto/val set | D_pareto = val (HotpotQA, HoVer, IFBench 300; PUPA 111; AIME ≈ 45) | Base DSPy program → Qwen3-8B average 45.2 → 54.9 (MIPROv2 47.8); GPT-4.1-mini 53.0 → 65.2 (MIPROv2 58.7). Abstract: "+10% over MIPROv2", "+6% over GRPO" | None (single points) |
| **SkillOpt** (Yang et al., Microsoft; arXiv 2605.23904 v2; preprint; our upstream) | An edit is accepted only if the selection score is "strictly greater ... ties are rejected"; parent score cached | Selection split: released manifests 200 (SearchQA), 17 (LiveMath), 24 (OfficeQA), 40 (SpreadsheetBench), 18 (ALFWorld), 53 (DocVQA). Ratio stated inconsistently (2:1:7 in Appendix C, 4:1:5 in the Table 2 caption) | **Human expert Skills and one-shot LLM Skills.** GPT-5.5 direct chat (no Skill / human / one-shot / SkillOpt): SearchQA 77.7 / 81.8 / 80.9 / 87.3; OfficeQA 33.1 / 66.9 / 51.7 / 72.1; SpreadsheetBench 41.8 / 72.9 / 43.2 / 80.7; LiveMath 37.6 / 38.4 / 40.0 / 66.9; ALFWorld 83.6 / 91.8 / 93.3 / 95.5; DocVQA 78.8 / 90.1 / 89.6 / 91.2 | None: no seeds, SD, CI or test; no ablation of the gate |
| EvoSkill (Alzubi et al., arXiv 2603.02766) | Keeps a Skill only if held-out validation improves (Pareto frontier) | Held-out validation | No-Skill agent → OfficeQA 60.6 → 67.9; SealQA 26.6 → 38.7 | Not checked (excluded from counts) |

Derived from SkillOpt's own GPT-5.5 table [M, arithmetic on P]:
- Its average margin over the better of the human and one-shot Skills is +8.1 points across six benchmarks (sum
  48.7).
- **LiveMath contributes 26.9 of the 48.7 summed points (55%).** Without LiveMath the average margin is +4.4.
- SkillOpt states that the LiveMath Skill grew from 154 to 379 tokens through **one** accepted edit, and that the
  LiveMath gain "arises from a single accepted edit". Its Figure 4 rule is: "In strongest-statement MCQs, rank choices
  by theorem strength ...", preferring a justified stronger-result option.

### 3.2 Experience and memory agents [P]

| Method (venue) | What is accepted, by which rule | Dev / val | Baseline → effect | Variance |
|---|---|---|---|---|
| ACE (Zhang et al., ICLR 2026; arXiv 2510.04618 v3) | **No gate.** Curator deltas merged by non-LLM logic + embedding de-dup; "without labeled supervision" | Offline adaptation on the train split; no validation use described | DeepSeek-V3.1 AppWorld ReAct 42.4 → 59.4 (GEPA 46.4); finance 69.1 → 81.9. Dynamic Cheatsheet without labels 65.4 < base 69.1 | Single values |
| AWM (Wang et al., ICML 2025) | Online workflows gated only by an LM success evaluator | None | WebArena 23.5 → 35.5; Mind2Web 36.2 → 45.1 | None |
| ExpeL (Zhao et al., AAAI 2024) | Insight importance counts (add / edit / up-vote / down-vote; removed at 0); no held-out gate | Fold design (train on one half, test on the other) | HotpotQA ReAct 28.0 ± 1.4 → 39.0 ± 1.7; ALFWorld 40.0 ± 0.3 → 59.0 ± 0.3 | SE over folds |
| Dynamic Cheatsheet (Suzgun et al., arXiv 2504.07952) | Self-curated memory, no ground truth | None | **Has a structure-only control DC-∅**: "structured problem-solving and explicit tool-use instructions but no memory". Claude 3.5 Sonnet AIME 2020–24: baseline 6.7 → DC-∅ 30.1 → DC-RS 40.6, so 69% of the gain needs no memory. GPT-4o Game24: 10 → 19 → 99 | Single runs |
| Reflexion (Shinn et al., NeurIPS 2023) | Per-task retries (episodic, not cross-task) | Ground truth or tests per task | HumanEval 80.1 → 91.0 | SD for one model, appendix only |
| Voyager (Wang et al., TMLR 2024) | GPT-4 self-verification before a code skill is stored | None | AutoGPT, ReAct, Reflexion | 3 trials ± SD |

### 3.3 Continual and lifelong prompt / skill learning [P, abstracts]

| Work | Setting | Acceptance / validation | Relevant finding |
|---|---|---|---|
| StreamBench (Wu et al., NeurIPS 2024 Datasets & Benchmarks) | Online input stream with feedback | No gate; streaming baselines | Simple streaming memory baselines; establishes online-feedback evaluation |
| Evo-Memory (Wei et al., arXiv 2511.20857) | Sequential task streams, >10 memory modules, 10 datasets | Answer-correctness feedback | ExpRAG (retrieve-experience) baseline; ReMem |
| ContinualSkillBench (Guan et al., arXiv 2608.03874 v3) | 5 domains × 100 tasks | Explicit skill maintenance vs raw context | "retaining context and feedback without skill maintenance yields nearly the same mean performance as maintaining an explicit skill library"; agents struggle "to consolidate experience into robust, transferable skills" |
| Do Self-Evolving Agents Forget? (Yu et al., arXiv 2605.09315) | Workflow / skill / model / memory evolution | -- | Capability erosion on earlier tasks |

### 3.4 Evaluations of skill and memory learning: closest prior and concurrent work [P]

| Paper | Finding | Controls / variance | What we add |
|---|---|---|---|
| **Zhao et al. 2026**, "Self-Evolving Agents Can Repair Failures but Struggle to Generalize from Them" (arXiv 2610.22984, 16 Oct 2026) | Studies ReasoningBank, **SkillOpt** and Evo-Harness under failure-only evolution. Repair (one retry after an update) recovers 3.5–15.4% (WebArena-Verified) and 2.5–11.8% (WebShop); held-out gains small or negative | Each held-out task run once; no seeds, SD, CI or test; no hand-written instruction baseline. Stream tasks must fail 3 preliminary ReAct rollouts, which partly controls chance recovery | **A matched chance baseline.** With no update, after three same-text failures a fourth identical run passes **4.95%** of the time (106 / 2,142, cal-1, all 11 arms; per arm 0.7–9.4%). Unconditionally 15.9% (1,318 / 8,286). Their range straddles our chance level. We also add an instruction baseline and placebos |
| **SkillsBench** (Li et al., arXiv 2602.12670; two versions) | **arXiv v4 (14 Jun 2026):** 87 tasks; curated Skills 33.9 → 50.5 (+16.6 pp); self-generated Skills −8.1, −11.3 and −11.5 pp vs no Skills on the three dedicated-harness configurations. **NeurIPS 2026 poster:** 84 tasks; curated +16.4 pp; self-generated "net −1.3pp" | 3 trials per cell, 95% CIs in figures. No length-matched or irrelevant-text control: v4 §6.1 lists "stronger length-matched baselines, such as random or irrelevant text" as future work | We supply those placebo and identical-text controls, and study Skills *learned from experience*, not one-shot written ones |
| **Liu et al. 2026**, "Rethinking Self-Evolving Agent Skills: Feedback Dynamics over Multiple Rounds" (arXiv 2608.02636, 31 Jul 2026) | Same suite as ours (SearchQA, OfficeQA, SpreadsheetBench, LiveMath, DocVQA; SkillOpt-Lite splits); GPT-5.5, Gemini 3.1 Pro, DeepSeek V4-Pro. "Evolution is sparse: only 55 of 388 candidates establish byte-distinct validation bests"; validation picked an evolved Skill in 11/14 settings, 9 improved test | Strict-improvement best-checkpoint rule on validation sets of 35–200 items. Probe scores average 3 deployments; one same-Skill SD reported (Gemini, OfficeQA, 8 evaluations: 3.92 points). No CI or tests; no hand-written instruction baseline | Their 3.92-point same-Skill SD on a frontier solver suggests our noise floor is not a weak-solver artefact. We add the instruction baseline, placebos and the gate-under-noise analysis |
| SkillBoost (Lin et al., arXiv 2607.26643 v2) | "data-driven skill optimization is prone to overfitting"; 23 model–benchmark configurations incl. LiveMath, SpreadsheetBench, ALFWorld, DocVQA, BFCL-v4; beats human, one-shot, Trace2Skill and SkillOpt | Gate on the same set that generated the failures; single point estimates | Their largest gain is also on LiveMath (Claude-opus-4-6 76.0 vs human 37.8). **[C, hypothesis]** That gain may route through the same meta option; testable from their Skill text |
| MAGE (Singh, arXiv 2607.11944) | "in low-data regimes (Ntrain=30), well-designed fixed prompts outperform all reflective optimizers" | 5 seeds (GSM8K-Hard, gpt-4o-mini; SD 7.3 vs 7.0) | Same conclusion with explicit placebo and same-text controls |
| RLMOpt (Satheesha et al., arXiv 2608.10471) | GEPA "fell below its starting point twice" in 11 matched benchmark-seed comparisons | Matched seeds | -- |
| p1 (Gao et al., arXiv 2604.08801 v2) | Prompt optimisation "fails when variance among responses dominates the variance of the system prompts" | -- | We *measure* that variance for an API solver and replay real gates on it |
| Ma et al. 2024 (arXiv 2402.02101) | LLM optimisers misdiagnose error causes (search summary; not re-verified, not counted) | -- | -- |
| Huang et al., ICLR 2024 | Self-correction gains relied on oracle stopping labels | -- | Our generated-item vs real-item inflation on OfficeQA |
| Revisiting OPRO (Zhang et al., Findings ACL 2024) | Small optimiser LLMs give marginal gains over zero-shot CoT | -- | -- |

Irrelevant text moves accuracy in both directions:
- Shi et al., ICML 2023 (GSM-IC): irrelevant context lowers accuracy.
- Cuconasu et al., SIGIR 2024: random documents in RAG raised accuracy, up to 35%.
- Our placebos do the same: −9.8 to +3.6 points.

The benchmark-construction fact [P]. The LiveMathematicianBench paper (arXiv 2604.01754, Section 2) says that "for a
configurable fraction of items, the correct option is replaced with the meta-option: 'One of the remaining options is
correct, but a stronger result can be proven.'" Its presence therefore identifies the answer by design. In our
283-item LiveMath training pool, it appears in 129 items and is the reference in 129 of 129 [M, re-checked today].

### 3.5 Measurement, negative-result and pre-registration precedents [P]

| Precedent | Lesson for us |
|---|---|
| DomainBed (Gulrajani & Lopez-Paz, ICLR 2021) | With model selection fixed (no test-domain oracle), "no algorithm ... outperforms ERM by more than one point". The template: a strong simple baseline + a fixed selection protocol |
| Agarwal et al., NeurIPS 2021 (outstanding paper) | Few-run point estimates mislead; use CIs over runs and robust aggregates |
| Sclar et al., ICLR 2024; Mizrahi et al., TACL 2024 | Formatting or template alone moves accuracy by up to 76 points and reorders models. Our format-convention effects are of this kind |
| Madaan et al. 2024 (arXiv 2406.10229); Miller 2024 (arXiv 2411.00640); Heineman et al., "Signal and Noise", NeurIPS 2025 | Seed variance; paired and clustered SEs; signal-to-noise as a benchmark property (D11 covers the reporting standard) |
| Hochlehnert et al., "A Sober Look at Progress in LM Reasoning", COLM 2025 (arXiv 2504.07086 v2, "Accepted to COLM 2025") | Most reasoning-RL gains are "only modest improvements--far below prior claims". **Closest venue precedent** |
| Pre-registration in ML workshop, NeurIPS 2020 (PMLR 148) and 2021 | Precedent for pre-registered ML studies with negative outcomes |
| ICBINB (ICLR 2026 workshop); Insights from Negative Results in NLP (6th edition, NAACL 2025) | Workshop homes for negative results |

### 3.6 Cross-literature patterns, counted over the 14 method papers in 3.1–3.2 (EvoSkill excluded) [P]

1. **Identical-text re-run control: 0 of 14.**
   - No method paper re-runs the unchanged prompt to measure how many items flip by chance.
   - Among the evaluation papers, Liu et al. 2026 report same-Skill deployment variability (3 repeats; one SD of
     3.92 points), and SkillsBench uses 3 trials per cell.
2. **Irrelevant-text or length-matched placebo: 0 of 14.**
   - Dynamic Cheatsheet's DC-∅ is a structure-only control, and it alone carries 69% of the gain in one setting.
   - SkillsBench asks for placebos as future work.
3. **Run-to-run or fold variance for the main comparison: 4 of 14.**
   - Reported: ProTeGi, MIPRO, ExpeL, Voyager.
   - Partial (3): OPRO (ablations only), Reflexion (one model, appendix), TextGrad (code task only).
   - None (7): PromptAgent, Promptbreeder, GEPA, SkillOpt, ACE, AWM, Dynamic Cheatsheet.
4. **Curated or structured per-task instruction baseline: 2 of 14** (SkillOpt's human Skills; DC's DC-∅).
   - PromptAgent uses short human task prompts.
   - The rest compare against a generic one-liner, an unoptimised DSPy signature, ReAct, or another optimizer.
   - SkillOpt's margin over that baseline is +4.4 points averaged over five benchmarks once LiveMath is set aside.
5. **Gates are small or absent.**
   - Validation-gated methods decide on 3 items (GEPA minibatch) up to 300 (GEPA Pareto set). Selection sets are
     17–200 items for SkillOpt and 35–200 for Liu et al. All use a single evaluation per candidate.
   - Memory agents (ACE, ExpeL, Dynamic Cheatsheet, AWM) accept without any held-out test.
   - No method pre-registers its acceptance rule or reports what the rule does on a no-op candidate.

## 4. Our evidence (verified against the ledger and the cal-1 registered readout)

### 4.1 Learned Skill vs a good instruction (the main comparison) [M]

- **v1 five-benchmark test** (ledger 10/19 10:52; opened with owner consent).
  - Setup: GLM-5.3. Test items: SearchQA 400, OfficeQA 172, LiveMath 125, SpreadsheetBench 204, ALFWorld 134 (1,035
    in total). 1 run per item, 1 history per chain.
  - Macro averages:

    | Arm | Macro average [95% CI] |
    |---|---|
    | Empty | 58.6 [55.6, 61.6] |
    | Instruction (I-glm) | **66.7** [63.8, 69.7] |
    | SkillOpt-glm | 66.0 [63.1, 68.9] |
    | E-glm (ours) | 63.7 [60.7, 66.8] |
    | GEPA-glm | 63.5 [60.5, 66.5] |

  - Paired differences (post hoc, descriptive): instruction − SkillOpt +0.6 [−2.3, +3.4]; instruction − GEPA +3.2
    [+0.3, +6.0]; instruction − empty +8.1 [+5.2, +11.0].
  - Registered learning gains vs empty: E +4.9, SkillOpt +7.4, GEPA +4.8. "Exceeds the instruction" was not
    established for any method.
  - Cost: 172.2M GLM tokens.
- **SearchQA, 975 fresh items** (ledger 10/13 07:05; GLM-5.3; 1 run per item; 5 histories per learner):
  - one step of learning from the zero-shot instruction: `lz` − `bzero` **+0.1** [−1.6, +1.8], missing-result bound
    [−3.1, +3.2];
  - validation-gated SkillOpt v9 − `bzero`: +1.0 [−0.5, +2.6];
  - zero-shot instruction − empty: +13.4 [+11.1, +15.7] (140 items up / 10 down);
  - every method lands at 0.82–0.85;
  - learning helped only from a weaker start: `lh` − `bhand` +4.9 [+2.0, +7.8].
- **Generic-instruction controls** (ledger 10/11–10/12; GLM-5.3; 240 commonly known held-out items per history):
  - A 416-byte, three-line generic text gives +7.5 [+3.6, +12.1] and +9.2 [+5.5, +13.7] over empty on SearchQA.
  - **Almost all of that comes from the single line "answer in the requested form, as briefly as possible"**:
    `generic_form` − empty +6.2 and +6.7; the "reason step by step" lines add ≈ 0.
  - Learned − generic: +4.6 [+0.5, +9.0] and +2.9 [−1.2, +7.3], not stable. It is mostly a more thorough answer form,
    judged by the failure taxonomy.
  - One learning step on top of the generic text: +2.9 [−1.1, +7.2].
  - BigCodeBench: every interval contains 0.
  - KOR's +7 did not replicate: pooled +3.3 [−1.3, +7.9] over 39 rules.
- **OfficeQA, generated vs real items** (ledger 10/15–10/16).
  - Generated items (124): learned beat `bzero` in the GLM family (GLM-5.3: 30 better / 6 worse, p = 7e-5). On
    deepseek the advantage vanished (9 / 9).
  - Real items (50 train + 24 val): p > 0.1 for all 3 solvers, within ±2 items of 50.
  - **Scope:** on SearchQA (10/13 E1) the generated-item comparisons did replicate the real-item ones; the generated
    items were about 8 points easier. The inflation is therefore an OfficeQA finding, not a general one.

### 4.2 Re-run noise of a temperature-0 API solver [M]

Source: cal-1 (deepseek-v4-flash; 200 SearchQA training items × 4 runs). The registered readout is from
`cal1_analyse.py`, run 10/20 23:43.

- **Identical-text arms.** `parent:A` and `parent:B` are the same empty scaffold, submitted twice.
  - Registered difference: +0.75 [−1.25, +2.75] points; 22 up / 18 down / 160 tie.
  - 20% of items are discordant in their 4-run means; the SD of the per-item difference is 0.144.
- **Single-run discordance** for identical text: 10.2% of items. For two different texts it is 12–21%
  (`cal1_positioning.json` A4).
- **Non-deterministic items.** 50 of 200 items are not deterministic across the 8 identical-text runs.
- **Re-run "repair" with no update.**
  - P(a failed cell passes on a re-run of the same text) = 0.184 (parent:A, 765 ordered pairs); 0.159 over all arms
    (8,286 pairs).
  - After three consecutive same-text failures, which is Zhao et al.'s stream filter: **0.050** (106 / 2,142, all
    arms).
  - The identical-text pooled 8-run estimate is 0.056; its cases overlap.
- **v3, independently** (main-session analysis of 10/20; not re-verified by me): the identical Skill re-measured in
  screen and in confirm moved 30 of 194 items.
- **Single-run paired MDE80 [E]**, i.e. the effect a single-run paired comparison detects with 80% power at α = 0.05:

  | Comparison | n = 100 | n = 300 | n = 500 | n = 1,400 |
  |---|---|---|---|---|
  | Identical text | 8.9 | 5.2 | 4.0 | 2.4 |
  | Two different texts | 9.6–12.8 | 5.6–7.4 | 4.3–5.7 | 2.6–3.4 |

  Most effects in Table 3.1 that compare against strong baselines are +3 to +6 points on 100–300-item test sets.
  These are below the thresholds above *if* those solvers are as noisy as ours. Their noise is unreported.
- **Items needed for an equivalence test [E]** (TOST, two one-sided tests; α = 0.05 each side; 80% power at a true
  difference of 0). This is new today, in `equivalence_power.json`.
  - For two *different* texts of equal accuracy (`ids-full` vs `seed-only`; placebo `control:4` vs empty), the SD of
    the per-item difference is 0.29–0.34 at 1 run and 0.22 at 4 runs.

    | Runs per item | ±3-point margin | ±2-point margin |
    |---|---|---|
    | 4 | ≈ 450 items | ≈ 1,000 items |
    | 1 | ≈ 810–1,100 items | ≈ 1,830–2,470 items |

  - Per cell, 1 run with more items is cheaper. Items are plentiful on SearchQA and scarce on OfficeQA and LiveMath.

### 4.3 Placebo text moves accuracy as much as learned rules do [M]

- Source: cal-1 registered A3 and A5 readout, differences vs `parent:A`, per 100 items.
- Each placebo is one irrelevant rule of 768–788 bytes: a haiku format, an uppercase hex colour, a recipe layout or
  Latin.

| Arm | Difference vs empty scaffold |
|---|---|
| Recipe placebo (`control:3`) | **−9.8** [−13.6, −5.9] (16 up / 58 down) |
| Haiku placebo (`control:1`) | −3.5 [−6.3, −0.7] |
| Hex-colour placebo (`control:2`) | **+3.6** [+0.6, +6.6] (39 / 16; sign p = 0.003) |
| Latin placebo (`control:4`) | +0.3 [−2.8, +3.3] |
| v3 learned rule (`cand`; E-ds's only screen passer) | −2.6 [−7.2, +2.0] |
| One seed bullet (`seed-rule`) | +0.4 [−3.1, +3.9] |
| Three seed bullets (`seed-rule3`) | −3.0 [−6.6, +0.6] |
| Task-card SearchQA section (`seed-only`) | **+8.9** [+5.1, +12.7] |
| Full five-section task card (`ids-full`) | **+9.4** [+5.1, +13.7] |

**The protocol's power, measured with a positive control [M].** The full task card passes the v3 gain criterion C1:
- at the registered n = 11 trigger items, in **75.8%** of resamples ("inconclusive" by the pre-registered table);
- at n = 6, in **47.9%**;
- at n = 20, in 99.0%;
- the null (`parent:B`) passes in 0%.

The v3 trigger sets had 4–11 items. "0 of 49 accepted" is therefore partly a power result: even a +9-point effect is
accepted about half the time at the typical trigger size. Rule-sized effects (≤ 3 points) are not detectable at all.

### 4.4 What literature-style gates do under this noise [E]

Source: `gate_null.json`. Model: an exchangeable no-op null. For each item, the candidate and the parent both draw
independent runs from the 8 pooled identical-text runs.

- **One strict-improvement comparison** (candidate > parent, ties rejected) accepts a pure no-op with this
  probability:

  | Selection set | n = 3 (GEPA minibatch) | 17 (SkillOpt LiveMath) | 24 (OfficeQA) | 40 (SpreadsheetBench) | 100 | 200 (SearchQA) |
  |---|---|---|---|---|---|---|
  | P(accept no-op) | 11.8% (ties 76%) | 32.9% | 35.7% | 39.1% | 43.8% | 46.1% |

  The values agree with (1 − P(tie)) / 2 within Monte-Carlo error.
- **The SkillOpt-style ratchet.** The selection set is fixed, the parent score is cached and each candidate is scored
  once. K no-op proposals give:

  | Setting | Accepted no-ops | P(at least one) | Phantom selection gain |
  |---|---|---|---|
  | n = 200, K = 40 | 2.63 | 0.96 | +3.2 points |
  | n = 17, K = 4 | 0.72 | 0.60 | +5.5 points |
  | n = 24, K = 40 | 1.60 | 0.90 | +8.3 points |

  The phantom gain is the cached score above the true mean. Test scores are not inflated by this, but the accepted
  text is.
- **Measured arms as single candidates** (P(accept)):

  | Candidate | Its true effect vs empty | n = 40 | n = 200 |
  |---|---|---|---|
  | Hex-colour placebo | +3.0 | 63% | 92% |
  | Latin placebo | −0.4 | 37% | 37% |
  | v3 learned rule | −3.1 | 26% | 7.5% |
  | Task-card section | +8.5 | 91% | 100% |

- **Caveat [C].** This is our solver's noise, on one benchmark and one route. The claim is "this is what the rule
  does at this noise level, and no paper reports its noise level". It is not "their results are noise". Liu et al.'s
  3.92-point same-Skill SD on Gemini 3.1 Pro (OfficeQA) indicates that frontier solvers are not noise-free.

### 4.5 Where the gains that do exist come from [M]

- **Answer-format conventions.**
  - v1: E's SearchQA-learned writing rules raised OfficeQA by +20.3 [+12.2, +28.5]. The instruction (+20.3),
    SkillOpt (+20.9) and GEPA (+19.2) gave the same rise. It is a writing convention, not learned transfer.
  - On SearchQA, the whole generic-text gain is the "answer form" line (4.1).
- **Cross-benchmark harm.**
  - SpreadsheetBench vs empty: E −7.2 [−14.7, 0.0]; GEPA −7.8 [−15.3, −0.5]; the instruction +9.2 [+2.6, +16.0].
  - Cross-dataset Skills on SearchQA: −3 to −8 points vs its instruction. `lm_z41` ("answer only the letter") scored
    −63.6 (ledger 10/14).
  - GEPA's QA format hint forced onto KOR: 152 vs 187 (11 up / 46 down). Forced onto ALFWorld: 93 vs 120 (1 up / 26
    down) (ledger 10/6).
- **A benchmark-construction shortcut (LiveMath).**
  - The meta option is the answer by construction (3.4). SkillOpt's LiveMath gain is one edit about that option
    (3.1).
  - Our own SkillOpt-glm LiveMath Skill learned the same regularity. On v1 LiveMath test (n = 125) it scored +2.4
    [−6.4, +11.2] vs empty, which is not distinguishable.
  - D7's pilot (deepseek): a structural meta rule raises meta cells 6 / 90 → 17 / 90 (+12.2 [+4.4, +20.0]) and costs
    about −5.7 on non-meta items.
  - Section 5 decomposes the released Skill.
- **Generated items** flatter the learner on OfficeQA (4.1).

### 4.6 The validation-free protocol's own outcome [M] (v3, deepseek solver, ledger 10/20)

- Funnels:
  - I-ds: 24 proposals → 10 past the entry check → 6 past self-test → 1 past screen → 0 past confirm.
  - E-ds: 25 → 18 → 9 → 1 → 0.
- Cost: 139.0M deepseek tokens + 7.8M GLM tokens.
- The generated-task pathway never ran: every proposal was placed `local`.
- With ≈ 10% single-run flips, placebo effects of −10 to +4 points and C1 power of 48% at n = 6 for a +9-point effect,
  a gate that refuses noise-sized wins refuses almost everything.

## 5. Pilot: auditing SkillOpt's released GPT-5.5 Skills on our solver [M]

**Design.**
- Prepared and launched by the earlier run at 01:01 on the NEW machine; analysed today.
- Solver: deepseek-v4-flash, `pjlab_token` route, temperature 0, max_tokens 32768, 6 workers.
- The released files are SkillOpt's `ckpt/searchqa/gpt5.5_skill.md` (sha256 `4e0a19d4…`) and
  `ckpt/livemath/gpt5.5_skill.md` (`53073aa5…`). Their hashes match the repository copies.
- SkillOpt's README presents these files as "portable artifacts".
- Training items only.
- Cost: 2,578,134 tokens, 1,160 cells.
- Wall clock: LiveMath 81.5 min for 560 cells (394 HTTP-429 retries); SearchQA 24.6 min for 600 cells (122 retries).

### 5.1 SearchQA (200 cal-1 items; all in SkillOpt's own train or selection split, so in-sample for the released Skill)

**Arms.**
- The released Skill, verbatim, × 2 runs.
- The task-card section `seed-only`, × 1 run, as a same-round drift check against cal-1's 4 runs.
- The request layout was replicated exactly: `seed-only` request hashes equal cal-1's on 200 of 200 items.

**Results.**

| Arm | Pass / cells | Rate |
|---|---|---|
| Released Skill | 273 / 400 | 68.3% |
| Task card, same round | 157 / 200 | 78.5% |
| Task card, cal-1 | 614 / 797 | 77.0% |
| Empty scaffold, cal-1 | 543 / 798 | 68.0% |

**Paired item-level differences** (10,000 bootstrap resamples):

| Comparison | Difference [95% CI] | Items up / down |
|---|---|---|
| Released − task card (pooled 5 runs) | **−9.05 [−13.45, −4.92]** | 15 / 38 |
| Released − task card (same round) | −10.25 [−15.0, −5.75] | 9 / 35 |
| Released − empty scaffold | +0.12 [−4.5, +4.75] | 33 / 27 |
| Released − hex placebo | −3.25 [−8.12, +1.5] | -- |
| Released − Latin placebo | +0.12 [−4.88, +5.12] | -- |
| Drift check: task card same round − cal-1 | +1.54 [−0.96, +4.08] | -- |

No drift was detected. The released Skill's single-run re-run discordance is 25 / 200 (12.5%).

**Format decomposition** (repository evaluator; `searchqa_format.json`):
- Replies without an `<answer>` tag: released **66 / 399 (16.5%)** vs task card **4 / 199 (2.0%)**. The scorer then
  falls back to the last line, typically "The answer is **X** ..." or a JSON object.
- 38 of the released Skill's 41 untagged failures contain the gold answer as the bold, JSON or "The answer is"
  candidate.
- Pass rate among tagged replies: 74.5% vs 80.0%.
- A lenient re-score reads that candidate (diagnostic, designed after seeing failures): released 77.9% vs task card
  79.9%; paired **−1.76 [−5.28, +1.51]**.
- The released Skill carries no output-format instruction. Its 9.9 KB of answer-normalisation advice nevertheless
  makes the solver drop the host's tag contract.
- Mean prompt tokens: 3,088 vs 1,617.

**Reading.**
- Moved to a different solver, the released Skill is worth the empty scaffold, and that is on items it was selected
  on.
- Its deficit vs the task card is almost all an answer-format interaction. Its content, once the format is repaired,
  is indistinguishable from a one-shot task card.

### 5.2 LiveMath (D7's 80 training items: 45 meta, 35 non-meta)

**Items.** 15 are in upstream train/val; 65 come from months 2026-03 to 06, after the upstream months.

**Arms.**
- `parent`: the task-card seed, × 2 runs.
- `ckpt-nofmt`: the released Skill minus its "single option label only" line, which conflicts with the host's
  `<answer>` contract; × 2.
- `ckpt-nofmt-nometa`: the same, minus the two bullets that name the meta option; × 2.
- `ckpt`: the released Skill verbatim, × 1.

Strict scorer: one letter in the last `<answer>` tag; a truncated reply is a fail.

| Arm | Meta items, pass / cells | Non-meta items, pass / cells |
|---|---|---|
| parent | 6 / 89 (6.7%) | 47 / 70 (67.1%) |
| ckpt-nofmt | 31 / 89 (34.8%) | 35 / 70 (50.0%) |
| ckpt-nofmt-nometa | 8 / 90 (8.9%) | 42 / 70 (60.0%) |
| ckpt (verbatim, 1 run) | 5 / 45 | 17 / 35 |

**Paired item-level differences, strict scorer:**

| Comparison | Meta items (45) | Non-meta items (35) |
|---|---|---|
| ckpt-nofmt − parent | **+27.8 [+15.6, +40.0]** (20 up / 1 down) | **−17.1 [−34.3, 0.0]** (6 / 14) |
| ckpt-nofmt-nometa − parent | +2.2 [−7.8, +12.2] | −7.1 [−21.4, +7.1] |
| ckpt-nofmt − ckpt-nofmt-nometa | **+25.6 [+11.1, +40.0]** | −10.0 [−27.1, +7.1] |
| ckpt (verbatim) − parent | +4.4 [−5.6, +15.6] | −18.6 [−32.9, −4.3] |

- **Lenient reader** (a bare letter on the last line counts when the tag is missing; diagnostic):
  - ckpt-nofmt − parent: meta +31.1 [+18.9, +43.3]; non-meta −10.0 [−25.7, +7.1].
  - ckpt-nofmt-nometa − parent: non-meta +2.9 [−12.9, +17.1].
  - Untagged replies: parent 1 / 159, ckpt-nofmt 11 / 159, ckpt-nofmt-nometa 23 / 160.
- **Pool-weighted net** (meta share 129 / 283 = 45.6%; stratified bootstrap):
  - ckpt-nofmt − parent: **+3.3 [−7.2, +13.9]** strict; +8.7 [−2.0, +19.7] lenient.
  - ckpt-nofmt-nometa − parent: −2.9 [−12.0, +6.2] strict.
  - Verbatim − parent: −8.1 [−17.4, +0.9] strict.
- **Out of sample** (the 65 later-month items; 36 meta and 29 non-meta items):

  | Arm | Meta cells | Non-meta cells |
  |---|---|---|
  | parent | 4 / 72 | 40 / 58 |
  | ckpt-nofmt | 25 / 71 | 27 / 58 |
  | ckpt-nofmt-nometa | 5 / 72 | 36 / 58 |

  The regularity and its exploitation persist after the upstream data.
- **Noise.** Same-text run-0-vs-run-1 discordance: parent 11 / 79 (13.9%), ckpt-nofmt 16 / 79 (20.3%),
  ckpt-nofmt-nometa 14 / 80 (17.5%). D7's own parent cells, with the same text and layout: meta 6 / 90, non-meta
  42 / 70.

**Reading.**
- For this solver on these items, the released Skill's large meta-item gain is carried entirely by the two
  meta-option bullets.
- Those bullets exploit a documented construction rule: the meta option appears only as the answer.
- The rest of the Skill and the bullets themselves cost accuracy on non-meta items. That cost is partly answer-tag
  loss and not established after lenient reading.
- The pool-weighted net effect is not distinguishable from 0.
- The verbatim Skill's format line both clashes with the host contract and, unexplained, removes the meta gain (one
  run of 45 items). A single line can flip the sign of a Skill's effect.

**What the pilot cannot say [C].**
- It used another solver. SkillOpt optimises per target model.
- The SearchQA items are in-sample for the released Skill.
- The LiveMath sample is 80 training items at 2 runs.
- We never looked at any test item.
- It supports "published Skills are not portable across solvers in this setting, and their largest gain routes
  through a construction rule". It does not support "SkillOpt's reported GPT-5.5 results are wrong".

## 6. Which claims our evidence supports

### Supported, with denominators

| # | Claim | Evidence | Label |
|---|---|---|---|
| S1 | Learned Skills (ours, SkillOpt-glm, GEPA-glm) do not beat a one-shot task-card instruction on our five benchmarks | v1 test, 1,035 items: I 66.7 vs SkillOpt 66.0 / E 63.7 / GEPA 63.5; I − SkillOpt +0.6 [−2.3, +3.4]. SearchQA 975 items: `lz` − `bzero` +0.1 [−1.6, +1.8] | M |
| S2 | Learning helps from weak starts | v1: +4.8 to +7.4 vs empty; `lh` − `bhand` +4.9 [+2.0, +7.8] | M |
| S3 | The instruction is the dominant effect | I − empty +8.1 [+5.2, +11.0] (v1 macro); +13.4 [+11.1, +15.7] (SearchQA 975); +9.4 [+5.1, +13.7] (cal-1, deepseek) | M |
| S4 | A temperature-0 API solver is not reproducible per item, and re-runs "repair" failures with no update | 10.2% single-run discordance; 50 / 200 items non-deterministic; P(pass \| fail) 0.159–0.184; 0.050 after 3 consecutive fails | M |
| S5 | Irrelevant one-line rules move accuracy −9.8 to +3.6 points; learned rules sit inside that range | cal-1, 200 items × 4 runs; 3 of 4 placebo CIs exclude 0 | M |
| S6 | Strict-improvement gates accept no-ops 33–46% of the time per proposal at n = 17–200, and accumulate phantom selection gains of 3–9 points | Exchangeable null on measured noise | E |
| S7 | The transferable part of learned Skills is answer-format convention, which also harms other benchmarks | v1 OfficeQA +19.2 to +20.9 for all arms incl. the instruction; SpreadsheetBench −2.0 to −7.8; `generic_form` line; `lm_z41` −63.6 | M |
| S8 | A LiveMath construction rule is learnable and was learned by SkillOpt (GPT-5.5) and by our SkillOpt-glm | Benchmark paper §2; 129 / 129 training items; SkillOpt's one-edit account; released Skill text | M + P |
| S9 | Generated items inflated learned-vs-instruction comparisons on OfficeQA (not on SearchQA) | OfficeQA 124 generated items 30 / 6 (p = 7e-5) vs 74 real items p > 0.1 on 3 solvers; SearchQA E1 replicated | M |
| S10 | A pre-registered validation-free gate with placebos accepted nothing, and had low power for rule-sized effects | v3 0 / 49; C1 power 47.9% at n = 6, 75.8% at n = 11 for a +9-point positive control | M |
| S11 | A published optimized Skill is not portable to another solver; its deficit is an answer-format interaction | Pilot 5.1: −9.05 [−13.45, −4.92] strict → −1.76 [−5.28, +1.51] lenient; untagged 16.5% vs 2.0%; in-sample items | M |
| S12 | The released LiveMath Skill's gain routes through the meta option and costs non-meta items; net ≈ 0 | Pilot 5.2: meta +27.8 → +2.2 without the bullets; non-meta −17.1; weighted +3.3 [−7.2, +13.9]; holds on 65 later-month items | M |

### Not supported (the paper must not claim)

| # | Not supported | Why |
|---|---|---|
| N1 | "Experience learning beats a good instruction" | Never established; every estimate is 0 ± 2–3 points |
| N2 | "Learned Skills transfer to similar benchmarks" | The only transfer (+20 on OfficeQA) is a format effect the instruction gives equally |
| N3 | "SkillOpt's published gains are noise or wrong" | We never ran GPT-5.5; their noise is unknown |
| N4 | "The meta option explains SkillOpt's GPT-5.5 *test* result" | Plausible from their own one-edit account and the benchmark's construction, but we never looked at test items. It is a hypothesis to state, not a finding |
| N5 | "Validation gates are useless" | No gate ablation. On SearchQA, the validation-gated and ungated one-step updates were equal on one dataset only |
| N6 | Anything about frontier solvers | Only GLM-5.3 and deepseek-v4-flash. Liu et al.'s SD hints that the noise persists, nothing more |
| N7 | "v3 shows that no rule can help" | v3's C1 power for rule-sized effects is ≈ 0; the null is partly a power result |
| N8 | "Equivalence with the instruction" | No equivalence test has been run. The intervals are ±2–3 points and mostly post hoc |

## 7. What the honest paper looks like

**Working title [C].** "Do Learned Skills Beat a Good Instruction? Noise, Placebos and Shortcuts in Experience-Driven
Prompt Optimisation". Alternative: "What Survives a Task Card: Re-run Noise, Placebo Text and a Construction Shortcut
in Skill Evolution".

**Type.** A measurement and negative-result paper with a released protocol and cell-level data. It is not a method
paper.

**Thesis (one paragraph).**
- Setting: five public benchmarks and two API solvers.
- Result: Skills learned from task experience beat an empty prompt but not a one-shot task-card instruction. This
  holds whether they are learned validation-free (ours) or with a validation gate (SkillOpt, GEPA), and it includes a
  published, optimised Skill moved to our solver.
- At temperature 0, identical text flips about 10% of items between two runs. Irrelevant one-line rules shift
  accuracy by −10 to +4 points. Under this noise, the common strict-improvement gate accepts no-op edits a third to a
  half of the time.
- The gains that survive are of three kinds: answer-format conventions that a task card already supplies (and that
  harm other benchmarks), a benchmark-construction shortcut, and gains on generated items that vanish on real ones.
- Recommendation: identical-text, placebo and instruction controls; k-run paired designs; pre-registered acceptance
  for any claim that a learned Skill helps.

**Contributions** (these map to S1–S12):
1. A controlled comparison of learned Skills against a strong instruction, across five benchmarks and four learners.
   It includes an audit of a published external artifact (section 5, scaled up in section 8).
2. Measured re-run noise and placebo effects for API solvers, and what they do to the acceptance rules in the
   literature (4.2–4.4).
3. An anatomy of the gains that exist: format interactions, cross-benchmark harm, the LiveMath construction shortcut,
   and generated-item inflation (4.5, 5).
4. A pre-registered validation-free protocol with a positive-control power calibration and its honest null: 0 of 49
   accepted, with C1 power stated, and every gate decision released.

**Outline.**
1. Introduction.
2. Related work: section 3.
3. Setup: benchmarks; splits and their overlap with upstream; solvers; arms; controls.
4. Noise and placebos.
5. Main comparison, plus the confirmatory audit.
6. Where gains come from.
7. Gates under noise.
8. The validation-free protocol and its null.
9. A reporting checklist (with D11).
10. Limitations.

**Figures.**
- A forest plot of every learned Skill minus the task card, per benchmark, with the identical-text band and the
  placebo band.
- P(accept no-op) against selection-set size.
- Phantom gain against the number of proposals.
- The LiveMath meta / non-meta decomposition.
- The SearchQA strict vs lenient format decomposition.
- The v3 funnel with C1 power.

**What is missing before submission.**
- The confirmatory audit (section 8).
- A per-benchmark noise measurement on OfficeQA (the pilot covered LiveMath's 2-run discordance).
- Release hygiene: frozen data manifests, the arm texts, the cell-level records.

## 8. The single experiment that would most strengthen it

**A pre-registered confirmatory audit: learned Skills vs the task card, with identical-text and placebo controls, on
unseen items, sized for equivalence.**

**Why this one [C].** Reviewers of a negative result first ask whether the null comes from a weak learner, from low
power, or from noise. This audit answers all three in one launch.
- **Learner objection:** it includes SkillOpt's own released artifacts and the SkillOpt and GEPA runs.
- **Power objection:** it runs an equivalence test with a stated margin. Current intervals only say "not shown
  better" (N8).
- **Noise objection:** it carries an identical-text duplicate and placebos in every benchmark. Today they exist only
  for SearchQA.
- **Shortcut question:** it carries the LiveMath meta / non-meta stratification.
- A frontier-solver replication would answer the solver objection, but no such route is available. It is stated as a
  limitation.

**Arms, per benchmark section (9–10):**
1. The empty scaffold.
2. The task card (I-ds seed).
3. A task-card duplicate: identical text, separate arm. It is the round-validity check.
4. SkillOpt's released GPT-5.5 Skill with its own output-format lines removed and the host contract kept. On
   LiveMath, also the variant without the two meta bullets.
5. The v1 final Skills: SkillOpt-glm, GEPA-glm and E-glm.
6. Two length-matched placebos appended to the task card.

**Items, each unseen by every learner and by SkillOpt's splits.**
- **SearchQA:** about 1,000 items from a fresh block outside the upstream IDs and every project block. The ledger
  names untouched blocks C and D; whether to use them is the owner's call, and I did not open them. Use 1–2 runs per
  item, which costs fewer cells than 4 runs when items are plentiful (4.2).
- **LiveMath:** items from months no project run or upstream split used, at 4 runs, stratified meta / non-meta.
  Whether months after 2026-06 are published is to be checked.
- **OfficeQA:** no fresh items exist. The 172-item protected test split is usable only with owner consent, at 4 runs.

**Solver.** deepseek-v4-flash (the v3 solver); optionally GLM-5.3 on SearchQA, to connect to v1.

**Estimand.** The per-benchmark paired item-level mean difference (artifact − task card), with a 95% bootstrap CI over
items. On OfficeQA, items are clustered by source file.

**Scoring.**
- Primary: the strict official scorer.
- Secondary, pre-registered: a lenient reader of untagged replies, as in section 5.

**Pre-registered rules.**

| Rule | Condition |
|---|---|
| R1 "beats the instruction" | Lower bound > 0 **and** the point estimate is above the largest placebo − task card difference in the same round |
| R2 "equivalent to the instruction" | TOST at ±3 points, primary. ±2 points is secondary where n allows |
| R3 "shortcut-explained" (LiveMath) | Non-meta CI contains 0 or is negative, and the meta gain vanishes without the meta bullets |
| R4 "format-explained" | Strict CI excludes 0 while the lenient CI contains 0 |
| R5 round validity | The duplicate − task card CI contains 0; otherwise the round is flagged |

**Power [E]** (from the cal-1 SDs in 4.2): TOST at ±3 points needs about 450 items at 4 runs; ±2 points needs about
1,000.

**Cost [E].** Measured per-cell tokens: SearchQA 1.8k (task card) to 3.2k (released Skill); LiveMath 1.5–1.6k.
OfficeQA is ≈ 10k per cell, taken from an earlier probe and not re-verified today.

| Benchmark | Cells | Tokens |
|---|---|---|
| SearchQA: 1,000 items × 10 arms × 2 runs | 20,000 | ≈ 50M |
| LiveMath: ≈ 150 items × 6 arms × 4 runs | 3,600 | ≈ 6M |
| OfficeQA: 172 × 8 arms × 4 runs (if consented) | 5,504 | ≈ 55M |

- Total ≈ 56M without OfficeQA and ≈ 111M with it. v3 used 139M.
- Wall clock is the binding cost. Measured today: 7–24 cells per minute at 6 workers, because the route was shared.
  The design therefore takes about 1–3 days.
- Design note: register before launch, and add any new arm only before any result is read.

**Owner decisions needed.**
1. A fresh SearchQA block (C or D) or the protected test split.
2. OfficeQA test-split consent.
3. Whether GLM-5.3 is a second solver.
4. When the route is free.

## 9. Venue fit [C; dates labelled]

| Venue | Fit | Date status |
|---|---|---|
| **TMLR** | Best fit for a careful negative result. Criteria: claims supported by evidence, and of interest; "novelty ... not a necessary criterion" (jmlr.org/tmlr acceptance criteria) | Rolling |
| **COLM 2027** | LM-centred. "A Sober Look" (COLM 2025) is the template for a sceptical re-evaluation | No call yet; ≈ late March 2027 by analogy with 2025–26 [E] |
| NeurIPS 2027 Evaluations & Datasets | If framed as an evaluation protocol with released cells. The 2026 track asked submissions to state their claims, assumptions and limitations | ≈ May 2027 [E] |
| ICML 2027 | Possible as an analysis paper; harder for a pure negative result | No official call; an aggregator projects ≈ 22 Jan 2027 [E] |
| ACL / EMNLP via ARR | Prompt optimisation is common there (ProTeGi EMNLP 2023, MIPRO EMNLP 2024, Revisiting OPRO Findings ACL 2024) | Next ARR cycles TBA; the 12 Oct 2026 cycle has passed |
| Workshops: ICBINB; Insights from Negative Results | A fast first version | Depends on 2027 editions |
| ICLR 2027 | -- | Passed (25 Sep 2026) |

Recommended sequence:
1. Run the section-8 audit.
2. Draft the paper; a workshop version is optional.
3. Submit to ICML 2027 if ready by late January; otherwise to COLM 2027 or TMLR.

## 10. Risks

- **Objection: weak solvers.** Not addressable on our routes. Liu et al.'s same-Skill SD of 3.92 on Gemini 3.1 Pro
  suggests the noise point is general; frame every claim as conditional on the solver.
- **Objection: "you moved a GPT-5.5 Skill to deepseek".** True. The audit relies on the README's "portable artifacts"
  framing, on in-sample items (an upper bound) and on the construction shortcut, which is solver-independent. It never
  claims the GPT-5.5 results are wrong (N3).
- **The lenient readers were designed after seeing failures.** They are diagnostic only and must be pre-registered in
  the audit.
- **The pilot is small.** 80 LiveMath items at 2 runs; SearchQA in-sample.
- **Owner-goal mismatch.** The owner wants a co-evolution method paper. The evidence supports a measurement paper. A
  method paper needs a positive confirmatory result first (D1, D2 and D7 are the candidates). Combining them is
  possible only if one of them passes a pre-registered test.
- **Literature drift.** This field moves weekly (four relevant 2026 papers appeared in July–October). Re-check
  before submission.
- **Citation accuracy.** Two errors in the earlier draft were caught today (section 12). Every number must be
  re-checked against camera-ready versions.

## 11. Files and reproduction

On the Mac, the folder `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D10/`
holds:
- `report.md`: this report.
- `notes.md`: the literature notes.
- `out/analysis/*.json`: the pilot analyses (`searchqa_pilot.json`, `searchqa_format.json`, `livemath_pilot.json`,
  `livemath_lenient.json`, `livemath_pilot_manifest.json`), plus `chance_recovery.json` and
  `equivalence_power.json`.
- `out/gate_null.json` and `out/cal1_positioning.json`.
- `scripts/`: every script, including today's `d10_searchqa_format.py`, `d10_livemath_lenient.py`,
  `d10_chance_recovery.py`, `d10_equivalence_power.py` and `d10_upstream_overlap.py`.

On the NEW machine:
- `/data/feasibility/D10/`: the pilot cells, in `pilot-searchqa-r2/cells.jsonl` and `pilot-livemath-r2/cells.jsonl`
  (with manifests and arm texts); the analyses, in `analysis/`; `scripts/`; and the upstream train/val ID lists only,
  in `upstream-ids/`.
- The pilot was launched with:

  ```
  bash -ic 'proxy_on >/dev/null 2>&1; setsid nohup bash /data/feasibility/D10/scripts/run_pilots.sh > /data/feasibility/D10/run_pilots.log 2>&1 < /dev/null &'
  ```

## 12. Corrections to the earlier draft (`report_part1.md`, `report_part3.md`)

1. **SkillsBench** has two versions with different numbers.
   - Self-generated Skills are −8.1 to −11.5 pp in arXiv v4 (87 tasks), but "net −1.3pp" in the NeurIPS 2026 poster
     (84 tasks).
   - The draft had attached the poster venue to the v4 numbers.
2. **Zhao et al.'s repair rates** were compared with our unconditional 18.4% re-run recovery.
   - Their tasks must fail three preliminary rollouts first. The matched chance rate is 5.0%, which their 2.5–15.4%
     straddles.
3. **"0 of 14 identical-text re-run controls"** holds for method papers only. Liu et al. 2026 (an evaluation) report
   same-Skill deployment variability.
4. **Curated-instruction baselines** are 2 of 14, not 1: Dynamic Cheatsheet's DC-∅ counts.
5. **Generated-item inflation** (S9) is scoped to OfficeQA; SearchQA's generated items replicated the real-item
   comparisons.
6. **cal-1 figures** now use the registered readout (e.g. placebos −9.8 / +3.6; positive control +9.4). C1 power
   (75.8% at n = 11, 47.9% at n = 6) is added, which changes the reading of the v3 null (N7).
7. **New sources:** the benchmark's own description of the meta option, SkillOpt's one-edit account (verified), and
   SkillOpt's LiveMath share of its margin (55%).
