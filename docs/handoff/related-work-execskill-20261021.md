# Related-work check for route B: executable skill libraries, tool creation, and execution-anchored co-evolution (2026-10-21)

Status: literature check only. No experiments, no paid API calls, no code or protocol changes. Written for the route B
design review (design draft v0, owner-approved shape 2026-10-21 16:4x).

Scope. This note covers the branch the earlier notes did not:
- D10 (`feasibility-20261021/D10/report.md`) covered prompt optimizers, experience/memory agents and skill evaluations.
- E10 (`feasibility-20261021/E10/report.md`) covered co-evolution as a game (R-Zero, Absolute Zero, SPIRAL, AutoBencher,
  POET, Dynabench, LM-as-examiner).
- D3 checked Voyager, AdaPlanner, ASI, SkillWeaver and StateAct at abstract level. This note re-checks the code-skill
  papers in full text.
Papers already summarised there appear here only as one-line pointers.

Method. I fetched arXiv metadata (title, authors, date, comments field) for about 60 papers. For about 38 of them I
searched the full text (pdftotext) for the acceptance rule and any transfer experiment. CoEvoSkills was read through the
arXiv HTML. Industry items come from the vendors' own pages. Evidence tags:
- **[F]** the relevant passage was read in the full text this session;
- **[A]** abstract or metadata only;
- **[S]** secondary source or search summary;
- **[mem]** from memory, not re-checked;
- **[D10] / [E10] / [D3]** covered in that note.

Name mapping for the request list:
- "Learning to Use Tools via Self-Verification" = ToolVerifier [17], the closest title match.
- "Training Language Model Agents without Modifications of LLM" = the arXiv v1 title of the AgentOptimizer paper [8]
  ("Training Language Model Agents without Modifying Language Models"). The final title is "Offline Training of
  Language Model Agents with Functions as Learnable Weights".
- "Skill-set learning" = Skill Set Optimization (SSO) [16].

---

## 0. Bottom line

1. **The branch is crowded, and in 2026 it has direct neighbours of route B.**
   - Code skills verified by execution have been standard since 2023: Voyager, LATM, CRAFT, TroVE, ReGAL, and later ASI
     and SkillWeaver.
   - Four 2026 papers come close to the route B design:
     - **FlowEvo** [22]: executable skills with preconditions and replay tests, plus a per-skill contrastive utility
       (applied vs. matched withheld episodes).
     - **CoEvoSkills** [21]: skill packages plus a co-evolving "surrogate verifier" that writes executable tests,
       anchored by an oracle pass/fail bit.
     - **GRASP** [23]: acceptance on an out-of-sample probe from the training split, with a fresh re-run of the parent
       and a hard regression budget.
     - **SAPO** [24]: matched rollout groups, base vs. base plus one candidate skill.
2. **Claim by claim** (details in §5):
   - (1) Executable procedures with programmatic applicability conditions: **not new**.
   - (2) An anchored, co-evolving examiner: **the parts exist**. What I did not find is a **predictive-validity gate**
     on task generators (the generated-item verdict must agree in sign with the fresh-real-item verdict). I also did
     not find failure detectors written as code and accepted by held-out precision/recall.
   - (3) No validation set, a one-shot fresh batch, and a placebo arm: **the combination is new, the parts are not**.
     The nearest is GRASP. Placebo arms appear in 2026 *evaluation* papers, but in no *acceptance rule* I found.
   - (4) Per-procedure transfer across benchmarks: **not found**. Package-level transfer across benchmarks is common
     (DGM, ADAS, GRASP, ClawTrace). Per-skill utility exists only within one benchmark: FlowEvo explicitly starts each
     benchmark from an empty bank.
3. **Evidence against route B's hopes, which the design must absorb.**
   - A 2026 controlled study finds that **code skills transfer worse than text skills**, and that task-level skills
     mostly fall below no memory [29].
   - GRASP finds its gate lifts in-domain scores but **none out of distribution** [23].
   - Three placebo-controlled evaluations find generated skills roughly equal to length-matched irrelevant text
     [31, 32, 33].
   - All of this agrees with design-v0's first risk: executable procedures are bench-specific, and transfer may be near
     zero.
4. **Suggested positioning.**
   - Do not claim a "first executable skill library", a "first co-evolving verifier" or "first cross-benchmark
     transfer".
   - Claim the measurement and gating contributions instead:
     - the examiner's predictive-validity gate;
     - placebo-controlled, one-shot fresh-batch acceptance on training items;
     - per-procedure cross-benchmark attribution, made causal by randomised withholding.
   - The related-work section must compare head-on with FlowEvo, CoEvoSkills, GRASP, Self-Challenging and DGM/ADAS.

---

## 1. Tool creation and code-skill libraries (2023-2025)

| Work [ref] | What it does; what is learned | Acceptance / validation | Examiner side evolves? | Transfer measured? | Tag |
|---|---|---|---|---|---|
| Voyager [1] | Minecraft agent. An LLM-written automatic curriculum proposes the next task. The **skill library holds executable JavaScript programs**, indexed by an embedding of each program's description and retrieved for new tasks | Iterative prompting with environment feedback and execution errors. A program is committed only after a GPT-4 **self-verification** step judges the task done. No validation set | The curriculum proposer adapts to exploration progress, but its tasks are not validity-checked or anchored | Library reused zero-shot in a **new world**; the library also helps AutoGPT | F |
| LATM [2] | A GPT-4 "tool maker" writes a Python function for a *task type* from 3 demos. A GPT-3.5 "tool user" applies it, and a dispatcher LLM keeps a "functional cache" | **Unit tests on 3 validation samples**. Unit-test call errors are retried; the tool is dropped after a threshold. Made once per task type | No | Reused across instances of one task type only | F |
| CREATOR [3] | Per-problem tool creation, then decision, execution, and rectification driven by error messages | Answers judged against gold; rectification on execution errors | No | Transfer experiment: a tool made for one problem of a 3-problem cluster, applied to the other two. Accuracy 63.0% → 78.3% (100 clusters; 39 better, 2 worse) | F |
| CRAFT [4] | Offline toolset per task. GPT-4 solves sampled **training (problem, answer) pairs**; the code is abstracted into tools and retrieved at inference | **Run the tool on its source problem; discard it if the answer is wrong** (training-label anchor). Then deduplicate | No | Within task; "plug-and-play" claim, but no cross-task toolset transfer experiment | F |
| TroVE [5] | Online toolbox grown over the *test* question stream. Each question gets K samples in import / create / skip modes | **Execution-output agreement** (self-consistency), then the fewest operations. Periodic trimming of low-use functions. "Zero additional training or supervision"; no validation set | No | Each of 11 datasets separately; human verification 31% faster | F |
| ReGAL [6] | Refactors programs into a code bank of helper functions | A refactored program must **reproduce the verified execution result**. Helpers are edited or pruned by failure rate | No | Held-out test within each domain: LOGO / Date / TextCraft +11.5 / +26.1 / +8.1 absolute (CodeLlama-13B) | F |
| LILO [7] | LLM synthesis plus Stitch symbolic compression plus AutoDoc names and docstrings, giving a library of abstractions | Programs checked against task specifications (DreamCoder line) | No | Within domain (REGEX, CLEVR, LOGO) | A |
| AgentOptimizer [8] | An agent's **function set treated as learnable weights**. An LLM optimizer adds, revises or removes functions | **Roll back** if training-set performance drops; early stop. No separate validation set | No | MATH sub-domains: same-domain training best in 2 of 3; geometry training worst | F |
| ToolMaker [9] | Turns paper code repositories into callable tools | Closed-loop self-correction. Benchmark of 15 tasks, scored with >100 benchmark-supplied unit tests; 80% implemented correctly | No | n/a | F |
| Alita [10] | Generalist agent that creates and reuses MCP (Model Context Protocol) servers, kept in an "MCP Box" | Reported on the GAIA *validation* set (74.0% pass@1) | No | Reuse across tasks claimed | A |
| ASI [11] [D3] | Web agent that induces **programmatic skills** | Accept only if re-execution solves the task **per an LLM evaluator** (no gold), uses at least one new skill, and each skill call changes the environment | No | Skills transferred to other websites; common skills transfer | F |
| SkillWeaver [12] [D3] | Propose skills; practise them (an **LLM reward model** judges success); synthesise APIs; hone them with LLM-generated unit tests and debugging | Model-judged; self-generated tests | No | APIs from strong agents help weaker agents, up to +54.3% on WebArena | F |
| WorldCoder [13] | Writes a Python world model and reward model, then plans with it | The program must explain **every transition in the replay buffer** (replay tests), plus an optimism constraint. The LLM is re-prompted with the inconsistent transitions | No | Across environments, by editing old programs (Sokoban, MiniGrid, ALFWorld) | F |
| Generalized planning [14] | GPT-4 writes Python generalized plans for PDDL (Planning Domain Definition Language) domains | Automated debugging: validated on as few as 2 training tasks, re-prompted on errors up to 4 times | No | Held-out, larger tasks of the same domain | F |
| AutoManual [15] | Planner writes code plans; Builder maintains a typed rule system from trajectories; Formulator writes a manual | Rules updated online from interaction outcomes | No | ALFWorld 97.4% (GPT-4-turbo), MiniGrid | A |
| SSO [16] | **Text** skills (subgoal plus instructions) mined from high-reward sub-trajectories | Kept only while they keep producing high environment reward, otherwise pruned | No | "Transfer" mode: train on 10 variants, test on held-out variants (ScienceWorld, NetHack) | F |
| ToolVerifier [17] | Tool *use*, not creation. Self-asked contrastive questions during tool selection and parameter generation; fine-tuned on synthetic data | Self-questioning, not execution | No | 17 unseen tools in 4 ToolBench tasks: +22% over few-shot | F |
| TRICE [18] | Learns when and how to call tools, from execution feedback | Execution feedback | No | — | A |
| ToolAlpaca [19], ToolGen [20] | Tool-use learning, not creation. ToolAlpaca: a simulated tool-use corpus. ToolGen: each tool as a vocabulary token (>47k tools) | Fine-tuning | No | Unseen tools | A |
| ExpeL, AWM | Text insights; text workflows | No held-out gate; AWM gates with an LM evaluator | No | ExpeL HotpotQA → FEVER; AWM cross-website (E2) | D10 |

Pattern. Every system in this table verifies each artefact by one of four means:
- executing it against its own source item, which needs labels (CRAFT, ReGAL, CREATOR);
- unit tests on a few validation samples (LATM);
- self-consistency of execution outputs (TroVE);
- an LLM judge (Voyager, ASI, SkillWeaver).

None tests whether *accepting* an artefact helps on fresh items, and none has an evolving, anchored examiner.

---

## 2. The 2026 skill-package wave (closest neighbours)

| Work [ref] | What it does; what is learned | Acceptance / validation | Examiner side evolves? | Transfer measured? | Tag |
|---|---|---|---|---|---|
| **CoEvoSkills** [21] (v1 title "EvoSkills"; COLM 2026) | A Skill Generator writes multi-file skill packages (Anthropic-style). A **Surrogate Verifier** (a separate LLM session on the same backbone) writes deterministic test assertions. It sees only the instruction and the output files, never the hidden ground-truth tests | A **ground-truth oracle returns only a pass/fail bit**, and only when the surrogate tests pass. At most 5 oracle rounds per task (mean 2.4). The best snapshot by oracle score is kept. **No validation set.** Evolution runs per SkillsBench task with that task's own oracle, so the reported scores are in-sample | **Yes**: when the oracle fails a skill that passed, the verifier escalates its tests | **Cross-model only** (+35.8 to +44.1 pp on six other models); no cross-task or cross-benchmark transfer. 71.1% vs. 30.6% (no skill) and 53.5% (human skills); 41.1% without the surrogate | F |
| **FlowEvo** [22] (COLM 2026) | Compiles successful workflows into **callable skills** in a persistent bank. Skills run directly or serve as context | Admission checks three things: **interface and preconditions**; **replay tests plus held-out checks**; safety (banned imports and calls). After admission, a **per-skill contrastive utility** compares success with the skill applied against **matched episodes with it withheld**, and skills with negative transfer are suppressed | No | **Explicitly none across benchmarks**: "Each benchmark runs independently from an empty initial bank". ALFWorld learned online over its 134 tasks; also HumanEval, MBPP, GSM8K, MATH-500 | F |
| **GRASP** [23] (EMNLP 2026) | Bounded library of text skills, edited from failures (FHIR clinical benchmarks; FHIR = Fast Healthcare Interoperability Resources) | Accept only on a net gain on a **balanced probe** of previously failing and previously passing items. The probe comes from the **development (training) split** and is out-of-sample to the proposing batch. The current library is **re-run for a fresh causal baseline**, under a hard regression budget | No | MedAgentBench ↔ v2, plus DBBench as a non-clinical control. Skill writing **without validation ≈ no skills**. The same gate given to baselines lifts them **in-domain, none out of distribution** | F |
| SAPO [24] ("Co-Evolving Skill Generation and Policy Optimization") | Skill-augmented RL; the policy itself is trained as the skill generator | **Pre-storage validation**: the rollout budget is split into matched groups (base vs. base plus one candidate skill) on the same task and retrieval context. The reward gap estimates marginal utility | No | Interactive decision-making and search QA (not checked in detail) | A |
| SkillFoundry [25] | Mines scientific repositories, APIs and notebooks into **executable skill packages** with contracts and tests | Closed-loop validation: expand, repair, merge, prune | No | Helps on 5 of 6 MoSciBench datasets | A |
| MUSE-Autoskill [26] | Full skill lifecycle: create, store, manage, evaluate, refine | Per-skill accumulated experience | No | Transfer to another harness (Hermes 51.90%) | A |
| SkillAxe [27] | Unsupervised refinement of skill documents. Scored on four dimensions, including **trigger precision** | No labels, tests or rewards | No | SpreadsheetBench "in the wild" | A |
| ClawTrace [28] | Cost-attributed traces turned into typed patches (preserve / prune / repair) | 30 held-out SpreadsheetBench tasks × 2 seeds | No | SpreadsheetBench → 84-task SkillsBench. All three quality regressions trace to the preserve lane. Argues for **evaluation at the rule-type level**, not whole packages | A |
| Break It Down [29] | Controlled study: task- vs. subtask-level induction × text vs. code format. AppWorld, OfficeBench, KramaBench; 11 models | — | No | Task-level skills mostly **below no memory**; subtask-level above. **Text transfers better than code** | A/F |
| SoK: Agentic Skills [30] | Survey that formalises a skill as S = (C, π, T, R). C : O × G → {0, 1} is an **applicability condition**, which the paper relates to the options framework's initiation set. Seven design patterns, including executable code skills and self-evolving libraries | — | — | — | F |
| GraphSkillEvo [36], VeriSkill [37] | Evolutionary optimisation of graph-structured skills; self-evolving program-verification skills | Gates on task performance | No | Cross-model only | A |

**Placebo-controlled skill evaluations (2026)** [31, 32, 33]:
- **SkillCenter** [31] has a "+Placebo" arm of three fixed, length-matched but deliberately irrelevant skills.
  Keyword-retrieved skills were statistically indistinguishable from it [F].
- **Huang 2026** [32] compares generated data-science skills with no skill and with a token-matched control of
  task-irrelevant text: Full 67.5% vs. No-Skill 68.3% vs. control 66.9% (504 majority-vote outcomes per condition) [F].
- **skill-placebo** [33] is an informal GitHub benchmark. 2 of 9 popular coding skills beat a same-length neutral
  placebo, both at Holm-adjusted p = 0.049. It used 450 trials with claude-opus-5-5 in Claude Code, measured
  2026-09-30 [S].

Placebos are now an accepted *evaluation* control for skills. I found none inside a learning loop's *acceptance* rule.

**Industry formats.**
- **Anthropic Agent Skills** [34], 16 Oct 2025; open standard published 18 Dec 2025 at agentskills.io:
  - A skill is a folder with a SKILL.md file and optional scripts.
  - Each skill's name and description sit in the system prompt, and **the model decides relevance** (progressive
    disclosure).
  - Bundled scripts run as tools.
  - The post names "create, edit, and evaluate Skills on their own" as a future goal [F].
- **AGENTS.md** [35] is a repository-level instruction file for coding agents. OpenAI contributed it to the Agentic AI
  Foundation under the Linux Foundation on 9 Dec 2025 [S].

Neither format specifies learning, acceptance tests or programmatic triggers. Route B's code-evaluated applicability
conditions are therefore a deliberate departure from the industry default of description-triggered skills.

---

## 3. Program evolution and agent-design search with a fixed evaluator

| Work [ref] | What is learned | Acceptance / validation | Evaluator evolves? | Transfer measured? | Tag |
|---|---|---|---|---|---|
| FunSearch [38] | Programs, evolved by an LLM over an island-based program database | Fixed, user-written automated evaluator | No | Programs are inspectable; cap sets and bin packing | S |
| AlphaEvolve [39] | Whole programs or code blocks | User-provided evaluation function h. An **evaluation cascade** runs test ensembles of increasing difficulty; optional LLM feedback. The paper names the need for machine-gradeable tasks as a limitation | No | Per problem | F |
| ADAS [40] | Agents written in code by a meta agent; an archive of discoveries | Candidates scored on **validation data**; median and 95% bootstrap CI on a held-out test | No | **Math → held-out math and non-math** (e.g. reading comprehension); across models | F |
| AFlow [41] | Code-represented workflows, searched by MCTS (Monte Carlo tree search) | 20% validation / 80% test split. The validation subset keeps the high-variance problems; each workflow is run 5 times on it | No | Within benchmark | F |
| DGM [42] (Darwin Gödel Machine) | A coding agent that rewrites its own code; an archive of variants | **Staged evaluation on benchmark subsets** (10 → 60 → 200 tasks). SWE-bench 20.0% → 50.0%; Polyglot 14.2% → 30.7% | No | Across foundation models; **SWE-bench ↔ Polyglot ("completely held-out benchmark")**; Python → other languages. Documents objective hacking | F |
| Eureka [43] | Reward-function code | Evolutionary search; fitness is the simulator task metric | No | 29 environments | A |
| DSPy [44] / GEPA / SkillOpt | Prompts and demos in LM programs | A metric on training or validation sets; GEPA and SkillOpt gates in D10 | No | Within benchmark (E2: GEPA −16.7 vs. cards on SpreadsheetBench) | A, D10 |

Relevance to route B. AlphaEvolve's cascade and DGM's staged evaluation are the published precedent for design step 5:
a cheap self-test on generated items used as a sieve, not as acceptance. Both still accept on the same fixed benchmark
subsets they report, which route B's one-shot fresh batch avoids.

---

## 4. Co-evolving verifiers and task generators anchored on execution

R-Zero (no anchor; its labels decay) and Absolute Zero (executor anchor, learnability band) are in [E10]. So are POET,
AutoBencher and Dynabench.

| Work [ref] | Examiner / verifier side | Anchor | Validity and difficulty control | Transfer | Tag |
|---|---|---|---|---|---|
| **Self-Challenging** [45] | A challenger explores a tool environment and writes **Code-as-Task**: instruction + verification function + example solution + failure cases | Code executor | Keep only tasks where **the example passes and the failure cases fail**. Then RL: more than 2× on M3ToolEval and TauBench (Llama-3.1-8B-Instruct) | Within the two benchmarks | F |
| CURE [46] | Coder and unit tester co-evolve by RL from an execution table | The dataset's **ground-truth unit tests** (no ground-truth code). The tester is rewarded for separating right from wrong code | — | The trained tester is later used as a label-free reward | F |
| Sol-Ver [47] | Self-play solver and verifier for code and tests | Dual execution agreement; no human annotation | — | — | A/F |
| CodeT [48] | Generated tests, used only to select code (no co-evolution) | Dual execution agreement | — | — | A |
| RL Tango [49] | Generator and generative process verifier co-trained by RL | Verifier rewarded **only by outcome correctness** (gold answers) | — | Verifier evaluated on ProcessBench | F |
| SSR [50] (Self-play SWE-RL, ICML 2026) | One model plays bug injector and solver in real repositories | Bug artifacts (bug patch + test-weakening patch) pass **consistency checks** against the tests | **Higher-order bugs built from the solver's failed repairs** (weakness-targeted) | SWE-bench Verified, SWE-Bench Pro | F |
| SPICE [51] | A challenger mines documents to write questions | **Corpus grounding** | Ablation without the corpus is weaker | — | F |
| Agent0 [52] | Curriculum agent rewarded by the executor's uncertainty (self-consistency) and tool-use frequency | **Majority-vote pseudo-labels**. A code interpreter is in the loop, but there is no label anchor (R-Zero-like) | Uncertainty band | — | F |
| **OMNI-EPIC** [53] | A foundation model writes **environment code + reward + `get_success()` checker code**. A model of interestingness compares each task against an archive | Simulator plus the code success checker. VLM (vision-language model) detectors were "not yet accurate enough", hence code | "Learnable" (neither too easy nor too hard) and novel. A **human study (50 participants)** checks detector agreement | Archive-based | F |
| EnvGen [54] | An LLM generates environment configurations, then **adapts them to the skills the RL agent is weak at**, using the agent's performance as feedback | Simulator | Feedback loop | Crafter, Heist | A |
| PAIRED / UED [55] | An adversary generates environments; an antagonist agent keeps them solvable (unsupervised environment design) | Simulator | Regret objective | Zero-shot transfer | A |
| PAE [56], SEAgent [57] | Task proposer plus a **model-based evaluator** (VLM judge; world-state model) | Model judgement only | Curriculum | — | A |
| AC/DC [58] | Co-evolution of models (by merging) and synthetic tasks | Synthetic data | Archive and coverage | Downstream benchmarks | A |
| GSM-Symbolic [59], Functional MATH() [60] | **Program-computed answer variants** of real items (templates; numbers changed) | Answers recomputed by program | — | Accuracy drops when only the numbers change; "reasoning gap" of 58–80% on MATH() | A |
| Synthetic data as a benchmark [61] | — | — | Post-hoc check: synthetic data tracks methods on simple tasks (intent), not complex ones (NER). Small generators favour their own data | — | A |
| Who&When [62], MAST [63] | Automated failure attribution; a failure taxonomy | Human annotation | Best attribution method: 53.5% at agent level, 14.2% at step level. MAST: 14 failure modes; human inter-annotator kappa = 0.88 | — | A |

Pattern.
- Every anchored examiner here filters items for **correctness** (executor, tests, simulator, corpus) and **difficulty**
  (a band, regret, learnability).
- Two papers come closest to validating the validators. CoEvoSkills checks its verifier only against an oracle bit on
  the same task. OMNI-EPIC checks its success checker against humans.
- **No paper checks a generator by whether its items reproduce the decision that fresh real items would make.** E10
  reached the same conclusion for its nine papers. The only direct study of generated-vs-real agreement [61] is a
  post-hoc benchmark analysis, not a gate.

Related precedents for applicability conditions and replayable programs:
- **Ada** [64] learns a library of operators with preconditions and effects (Mini Minecraft, ALFRED).
- **PoE-World** [65] composes small programmatic experts into a world model.
- **GIF-MCTS** [66] debugs code world models against unit tests and trajectories.
- WorldCoder [13] requires consistency with every recorded transition, which is the closest precedent for route B's
  replay tests.

---

## 5. What would be new in route B

### Claim 1: executable procedures, each with a programmatic applicability condition, a description and replay tests; a cumulative package run by a fixed router and shell

**Already present.**
- Code skills learned from experience and verified by execution: [1], [2], [4]–[6], [11], [12].
- Stored **preconditions + replay tests + held-out checks + banned imports**: FlowEvo [22].
- Consistency with all recorded trajectories (= replay tests): WorldCoder [13].
- The applicability condition as a formal predicate C : O × G → {0, 1}, equated with the options framework's
  initiation set: SoK [30]. Planning operators with preconditions: Ada [64], generalized planning [14].
- Bundled executable scripts with description-triggered loading: Anthropic Agent Skills [34].
- State tracking for ALFWorld: StateAct [D3].

**Not found.**
- A *deterministic* router that evaluates every learned condition and logs every enable decision, so the solver never
  chooses a procedure. (FlowEvo's retriever and Anthropic's model-judged triggers both leave the choice to a model.)
- The specific shell contract as the learned unit: hooks before and after each solver call that rewrite context,
  compute deterministically, or veto actions.

Both are engineering choices. They are useful because they make use observable, but they are not research novelties on
their own.

**Nearest prior:** FlowEvo [22]; then ASI [11]; SoK [30]; the LATM dispatcher [2].

**Verdict: not new.** Suggested wording: "we adopt the executable-skill representation (cf. FlowEvo, ASI) with
deterministic applicability predicates, so that every enable decision is logged".

### Claim 2: the examiner also evolves and is anchored (code failure detectors; task generators with program- or simulator-computed truth; pass-rate band; predictive validity; shortcut check)

**Already present.**
- Executor-anchored task generation with validity filters: Absolute Zero [E10]; Self-Challenging's example-solution
  and failure-case filter [45].
- Generated environments with code success checkers and a learnability band: OMNI-EPIC [53]; POET [E10].
- Weakness-targeted generation: EnvGen [54]; SSR's higher-order bugs [50].
- Co-evolving test writers: CURE [46] (anchored on ground-truth tests); Sol-Ver [47] (execution agreement).
- **A co-evolving verifier for skill packages, anchored by an oracle bit: CoEvoSkills [21].**
- Difficulty bands: R-Zero, Absolute Zero, POET [E10].
- Program-computed answer variants: GSM-Symbolic [59], MATH() [60].

**Not found.**
- (a) Accepting or retiring a task generator by **predictive validity**: the candidate-vs-parent difference must have
  the same sign on generated items as on fresh real items.
- (b) **Failure detectors written as code and accepted by pre-registered precision and recall** on held-out,
  outcome-labelled trajectories, with no answer access at run time. The closest work is LLM-based failure attribution,
  which is weak (53.5% / 14.2% [62]), and human-validated taxonomies (MAST [63]).
- (c) An options-only shortcut check as a generator filter. This is similar in spirit to hypothesis-only baselines in
  NLI (natural language inference) [mem: Poliak et al. 2018; Gururangan et al. 2018; not re-checked].

**Nearest prior:** CoEvoSkills [21] (closest overall); Self-Challenging [45]; OMNI-EPIC [53]; SSR [50]. For
predictive validity, only a post-hoc study exists [61].

**Verdict: partly new.** The predictive-validity gate is the one examiner element without a found precedent, so it
should be the headline of the examiner side. Code detectors validated by precision/recall are a modest second point.

Two warnings:
- If the gate rejects every generator (design-v0 risk 3), the examiner story shrinks to detectors. That outcome must be
  reported as such.
- A reviewer will say CoEvoSkills already co-evolves a verifier with skills. The contrast to draw is that CoEvoSkills'
  anchor is the oracle of the *same task* it is optimising, whereas route B's anchors are a fixed referee on items
  never used before.

### Claim 3: no validation set; each version decision uses one fresh batch of real training items, used once, with four interleaved arms (candidate, parent, task-card only, placebo procedure) and pre-set minimum effects

**Already present.**
- Learning with no validation set is common, but in forms that do not test the decision on held-out items:
  - online learning on the test stream (TroVE [5]; FlowEvo's 134 ALFWorld tasks [22]; ACE and AWM [D10]);
  - LLM or self-verification (Voyager [1], ASI [11], SkillWeaver [12]);
  - training-set roll-back (AgentOptimizer [8]).
- Gated methods reuse fixed validation sets (GEPA, SkillOpt [D10]; AFlow [41]; ADAS [40]) or fixed benchmark subsets
  (DGM [42]).
- Matched comparisons for skill acceptance exist:
  - **GRASP** [23]: out-of-sample probe from the training split, fresh re-run of the parent, hard regression budget;
  - **SAPO** [24]: matched rollout groups, base vs. base + candidate;
  - **FlowEvo** [22]: applied vs. matched withheld episodes, after admission.
- Length-matched placebo arms appear in 2026 evaluations [31, 32, 33]. SkillsBench asks for them, and DC-∅ is a
  structure-only control [D10].
- The "use each holdout once" principle has a theoretical precedent in adaptive data analysis [mem: Dwork et al.,
  "The reusable holdout", Science 2015; not re-checked].

**Not found.** An acceptance rule that does all three of the following:
- spends each batch of real training items exactly once;
- interleaves candidate, parent, an instruction-only arm and a **placebo-procedure arm** in the same time window;
- uses pre-registered per-benchmark minimum effects.

In particular, a placebo *procedure* (same prompt slot, same number of calls, no information) inside a learning loop's
acceptance rule was not found.

**Nearest prior:** GRASP [23] (the paper a reviewer will compare against; it reuses probe items across decisions and has
no placebo or instruction-only arm); SAPO [24]; FlowEvo [22]. For placebos: SkillCenter [31], Huang [32].

**Verdict: the combination is new; the parts are not.** GRASP's own finding should be cited honestly: its gate helps
in-domain and not out of distribution. That is a reason to keep route B's dissimilar-bench non-inferiority readout as
the primary transfer claim.

### Claim 4: one cumulative package travels across five benchmarks; transfer is read per procedure from the router's enable logs

**Already present.**
- Package- or agent-level transfer across benchmarks: DGM SWE-bench ↔ Polyglot [42]; ADAS math → non-math [40];
  GRASP MedAgentBench ↔ v2 [23]; ClawTrace SpreadsheetBench → SkillsBench [28]; Break It Down across tasks of three
  benchmarks [29].
- Transfer of code across environments: WorldCoder [13]; Voyager's new world [1]; CREATOR's problem clusters [3].
- Cross-model transfer: CoEvoSkills [21], GraphSkillEvo [36], VeriSkill [37]; SkillWeaver strong → weak [12].
- Per-skill usage or utility *within* a benchmark: TroVE usage counts [5]; SSO executed skills [16]; **FlowEvo
  contrastive per-skill utility** [22].
- Rule-type-level attribution: ClawTrace [28].
- Sequential multi-domain benchmarks: ContinualSkillBench [D10]; SkillLearnBench and LifelongAgentBench, cited by MUSE
  [26] and not checked here.

**Not found.** Per-procedure transfer estimates across benchmarks, from deterministic enable logs, within one
cumulative package. FlowEvo, the nearest system, states that "no skills or memories transfer across benchmarks".

**Caveats.**
- Enable logs alone give an *observational* contrast: the items where a procedure fires differ from those where it does
  not. A causal per-procedure reading needs randomised withholding of fired procedures on a fraction of target items,
  as FlowEvo does within a benchmark.
- Break It Down [29] predicts small transfer for code-form skills.

**Nearest prior:** FlowEvo [22] (mechanism, within a benchmark); ClawTrace [28] (typed attribution across benchmarks);
DGM [42] and ADAS [40] (package-level transfer across benchmarks).

**Verdict: likely new as a measurement.** It is only credible with randomised withholding, and the paper should expect
and report near-zero transfer outside the table/number cluster.

### Overall

At the representation level, route B is a recombination of FlowEvo-style executable skills, CoEvoSkills-style verifier
co-evolution, Self-Challenging/OMNI-EPIC-style executable task generation and GRASP-style fresh-baseline acceptance. Its
defensible novelty lies in **measurement and gating**, which is also where this project's evidence is strongest:
- the predictive-validity gate on the examiner;
- placebo-controlled, one-shot fresh-batch acceptance on training items;
- per-procedure cross-benchmark attribution with randomised withholding.

---

## 6. Design implications (proposals only, for the opposing review; nothing here is registered)

1. **Make per-procedure transfer causal.** In the test reads, withhold each enabled procedure at random on a
   pre-registered fraction of target items (FlowEvo's matched withholding [22]). Otherwise the enable-log table is
   observational. Cost: it adds item-level arms, so budget it with the five-domain test reads.
2. **Register predictive validity as the examiner's primary metric**, with its failure handling (generators retired
   after two sign disagreements, as in design-v0) and an explicit plan to report "the gate rejected everything".
3. **Keep frozen format guards and instruction-only arms.** The 2026 placebo studies [31, 32, 33] and SkillsBench show
   that generated skills often equal irrelevant text, so the placebo-procedure arm is the control reviewers now expect.
4. **Contrast with CoEvoSkills' in-sample loop** [21]: route B's referee never sees the items it is optimising on.
5. **Cite AlphaEvolve's evaluation cascade and DGM's staged evaluation** [39, 42] as the precedent for "self-test as a
   sieve, not as acceptance".
6. **Lower the transfer expectation in the registration**, citing Break It Down [29] (code < text for transfer) and
   GRASP [23] (gate gains in-domain only).

## 7. Limits of this check

- Venues marked [mem] or [S] were not confirmed on the publisher's page.
- These were not read beyond the abstract: SAPO's benchmarks, SkillFoundry, MUSE-Autoskill, SkillAxe, ClawTrace,
  GraphSkillEvo and VeriSkill.
- Not searched: SkillLearnBench, LifelongAgentBench, Trace2Skill, weak-supervision "labeling function" work (Snorkel,
  Snuba, the natural precedent for code detectors accepted by precision/recall), or safe-RL shielding (the precedent for
  action veto).
- arXiv identifiers from 2026 are as served by arxiv.org on 2026-10-21. Several of those papers are recent preprints
  without peer review.
- Local working copies (PDF text and abstracts) are in the session scratchpad, not in the repository.

---

## 8. 给负责人的中文摘要（10 行）

1. 这次补查的是上次没查的一支文献：让大模型（LLM，大语言模型）自己写可执行的小程序当“技能”，以及“出题、判卷的一方也一起进化，但用程序或模拟器算出的真答案当锚”的方法。共核对约 60 篇，其中约 38 篇读了全文的关键段落。
2. 总的结论：路线 B 的四条新意，没有一条是完全没人做过的；真正还空着的，是“怎么验收、怎么测量”的那部分。
3. 第一条“学可执行过程，带程序写的适用条件和回放测试”：已有人做。2023 年的 Voyager（在《我的世界》游戏里积累代码技能库）就是代码技能；2026 年的 FlowEvo（COLM 2026，COLM 是语言模型方向的学术会议）几乎是同一个东西：可调用技能、前置条件、回放测试、禁止危险导入。一篇 2026 年的综述还把“适用条件”写进了技能的标准定义。
4. 第二条“考官一方也进化并被锚住”：零件都有人做过，包括：用代码执行器筛题（Absolute Zero、Self-Challenging）；在模拟器里生成环境、用代码判成败（OMNI-EPIC）；专挑弱点出题（EnvGen、SSR，SSR 是“自博弈修程序错误”的训练法）；和技能一起进化的“代理验证器”（CoEvoSkills）。没找到的是“预测效度”这道关：生成题上新旧版本谁好谁坏，必须和真实新题上的结论方向一致，不一致就淘汰出题程序。这条可以当考官一方的主打。
5. 第三条“不用验证集，每次决定只用一批没用过的真题，四组同时交错，其中一组是安慰剂”：最接近的是 GRASP（EMNLP 2026，EMNLP 是自然语言处理会议）。它也从训练集里取“没用来提方案”的样本当探针，并当场重跑父版本；但探针会反复使用，也没有安慰剂组和“只给任务卡”组。安慰剂对照在 2026 年的技能评测论文里已经出现，但还没人放进学习循环的验收规则里。所以四组的组合是新的，单个零件不是。
6. 第四条“一个累积的包跨五个测试集走，按每条过程的启用日志读迁移”：整包级别的跨测试集迁移已有人量过，例如 DGM（会改写自身代码的编程智能体）、ADAS（自动设计智能体）、GRASP、ClawTrace；按单条技能算效用也有（FlowEvo），但它明说每个测试集都从空库开始、不跨测试集。按单条过程读跨测试集迁移，没找到先例。
7. 要注意：只比较“启用了这条过程的题”和“没启用的题”，得到的是相关，不是因果。FlowEvo 的做法是随机把一部分题上已启用的技能拿掉做对照，建议照搬，否则审稿人会质疑。
8. 对我们不利的证据也要正视：2026 年一篇对照研究（Break It Down）发现，代码形式的技能跨任务迁移比文字形式差；GRASP 发现验收关卡只提高同分布的成绩，不提高分布外的；几篇带安慰剂的评测里，模型自己生成的技能和同长度的无关文字差不多。这和设计稿里“可执行过程偏专用，迁移可能接近零”的风险判断一致。
9. 建议论文这样定位：不说“第一个可执行技能库”“第一个协同进化的验证器”“第一个跨测试集迁移”；主打三点：考官的预测效度关卡、带安慰剂的一次性新题验收、按过程的跨测试集归因（加随机撤除对照）。
10. 相关工作里最该正面对比的五篇：FlowEvo、CoEvoSkills、GRASP、Self-Challenging、DGM。全文和文献清单见本文件第 1 到 5 节和第 9 节。

---

## 9. References

Code-skill and tool-creation papers (§1):

1. Guanzhi Wang, Yuqi Xie, Yunfan Jiang, Ajay Mandlekar, Chaowei Xiao, Yuke Zhu, Linxi Fan, Anima Anandkumar. "Voyager:
   An Open-Ended Embodied Agent with Large Language Models." TMLR 2024 [S]; arXiv 2305.16291.
   https://arxiv.org/abs/2305.16291 [F]
2. Tianle Cai, Xuezhi Wang, Tengyu Ma, Xinyun Chen, Denny Zhou. "Large Language Models as Tool Makers." ICLR 2024; arXiv
   2305.17126. https://arxiv.org/abs/2305.17126 [F]
3. Cheng Qian, Chi Han, Yi R. Fung, Yujia Qin, Zhiyuan Liu, Heng Ji. "CREATOR: Tool Creation for Disentangling Abstract
   and Concrete Reasoning of Large Language Models." Findings of EMNLP 2023; arXiv 2305.14318.
   https://arxiv.org/abs/2305.14318 [F]
4. Lifan Yuan, Yangyi Chen, Xingyao Wang, Yi R. Fung, Hao Peng, Heng Ji. "CRAFT: Customizing LLMs by Creating and
   Retrieving from Specialized Toolsets." ICLR 2024; arXiv 2309.17428. https://arxiv.org/abs/2309.17428 [F]
5. Zhiruo Wang, Daniel Fried, Graham Neubig. "TroVE: Inducing Verifiable and Efficient Toolboxes for Solving Programmatic
   Tasks." ICML 2024 [S]; arXiv 2401.12869. https://arxiv.org/abs/2401.12869 [F]
6. Elias Stengel-Eskin, Archiki Prasad, Mohit Bansal. "ReGAL: Refactoring Programs to Discover Generalizable
   Abstractions." ICML 2024; arXiv 2401.16467. https://arxiv.org/abs/2401.16467 [F]
7. Gabriel Grand, Lionel Wong, Maddy Bowers, Theo X. Olausson, Muxin Liu, Joshua B. Tenenbaum, Jacob Andreas. "LILO:
   Learning Interpretable Libraries by Compressing and Documenting Code." ICLR 2024; arXiv 2310.19791.
   https://arxiv.org/abs/2310.19791 [A]
8. Shaokun Zhang, Jieyu Zhang, Jiale Liu, Linxin Song, Chi Wang, Ranjay Krishna, Qingyun Wu. "Offline Training of
   Language Model Agents with Functions as Learnable Weights" (v1: "Training Language Model Agents without Modifying
   Language Models"). ICML 2024 (PMLR 235); arXiv 2402.11359. https://arxiv.org/abs/2402.11359 [F]
9. Georg Wölflein, Dyke Ferber, Daniel Truhn, Ognjen Arandjelović, Jakob Nikolas Kather. "LLM Agents Making Agent Tools."
   ACL 2025; arXiv 2502.11705. https://arxiv.org/abs/2502.11705 [F]
10. Jiahao Qiu, Xuan Qi, Tongcheng Zhang, Xinzhe Juan, Jiacheng Guo, et al. "Alita: Generalist Agent Enabling Scalable
    Agentic Reasoning with Minimal Predefinition and Maximal Self-Evolution." arXiv 2505.20286, 2025.
    https://arxiv.org/abs/2505.20286 [A]
11. Zora Zhiruo Wang, Apurva Gandhi, Graham Neubig, Daniel Fried. "Inducing Programmatic Skills for Agentic Tasks." COLM
    2025; arXiv 2504.06821. https://arxiv.org/abs/2504.06821 [F]
12. Boyuan Zheng, Michael Y. Fatemi, Xiaolong Jin, Zora Zhiruo Wang, Apurva Gandhi, Yueqi Song, Yu Gu, Jayanth Srinivasa,
    Gaowen Liu, Graham Neubig, Yu Su. "SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills."
    arXiv 2504.07079, 2025. https://arxiv.org/abs/2504.07079 [F]
13. Hao Tang, Darren Key, Kevin Ellis. "WorldCoder, a Model-Based LLM Agent: Building World Models by Writing Code and
    Interacting with the Environment." NeurIPS 2024 [S]; arXiv 2402.12275. https://arxiv.org/abs/2402.12275 [F]
14. Tom Silver, Soham Dan, Kavitha Srinivas, Joshua B. Tenenbaum, Leslie Pack Kaelbling, Michael Katz. "Generalized
    Planning in PDDL Domains with Pretrained Large Language Models." AAAI 2024; arXiv 2305.11014.
    https://arxiv.org/abs/2305.11014 [F]
15. Minghao Chen, Yihang Li, Yanting Yang, Shiyu Yu, Binbin Lin, Xiaofei He. "AutoManual: Constructing Instruction
    Manuals by LLM Agents via Interactive Environmental Learning." NeurIPS 2024; arXiv 2405.16247.
    https://arxiv.org/abs/2405.16247 [A]
16. Kolby Nottingham, Bodhisattwa Prasad Majumder, Bhavana Dalvi Mishra, Sameer Singh, Peter Clark, Roy Fox. "Skill Set
    Optimization: Reinforcing Language Model Behavior via Transferable Skills." ICML 2024 (PMLR 235); arXiv 2402.03244.
    https://arxiv.org/abs/2402.03244 [F]
17. Dheeraj Mekala, Jason Weston, Jack Lanchantin, Roberta Raileanu, Maria Lomeli, Jingbo Shang, Jane Dwivedi-Yu.
    "TOOLVERIFIER: Generalization to New Tools via Self-Verification." arXiv 2402.14158, 2024 (venue not checked).
    https://arxiv.org/abs/2402.14158 [F]
18. Shuofei Qiao, Honghao Gui, Chengfei Lv, Qianghuai Jia, et al. "Making Language Models Better Tool Learners with
    Execution Feedback." NAACL 2024; arXiv 2305.13068. https://arxiv.org/abs/2305.13068 [A]
19. Qiaoyu Tang, Ziliang Deng, Hongyu Lin, Xianpei Han, Qiao Liang, Boxi Cao, Le Sun. "ToolAlpaca: Generalized Tool
    Learning for Language Models with 3000 Simulated Cases." arXiv 2306.05301, 2023. https://arxiv.org/abs/2306.05301 [A]
20. Renxi Wang, Xudong Han, Lei Ji, Shu Wang, Timothy Baldwin, Haonan Li. "ToolGen: Unified Tool Retrieval and Calling
    via Generation." ICLR 2025; arXiv 2410.03439. https://arxiv.org/abs/2410.03439 [A]

The 2026 skill-package wave (§2):

21. Hanrong Zhang, Shicheng Fan, Henry Peng Zou, Yankai Chen, Zhenting Wang, et al. "CoEvoSkills: Self-Evolving Agent
    Skills via Co-Evolutionary Verification" (v1: "EvoSkills"). COLM 2026; arXiv 2604.01687.
    https://arxiv.org/abs/2604.01687 [F]
22. Zeyu Ren, Ling Yue, Ran Li, Yishu Wang, Shengxiang Xu, et al. "FlowEvo: Self-Evolving Agents through the
    Co-Evolution of Workflows and Executable Skills." COLM 2026; arXiv 2607.21596. https://arxiv.org/abs/2607.21596 [F]
23. Johannes Moll, Jean-Philippe Corbeil, Jiazhen Pan, Martin Hadamitzky, Daniel Rueckert, et al. "GRASP: Gated
    Regression-Aware Skill Proposer for Self-Improving LLM Agents." EMNLP 2026; arXiv 2605.29668.
    https://arxiv.org/abs/2605.29668 [F]
24. Zhiwei Zhang, Yudi Lin, Nikki Lijing Kuang, Linlin Wu, Xiaomin Li, et al. "Co-Evolving Skill Generation and Policy
    Optimization" (method name SAPO). arXiv 2606.08755, 2026. https://arxiv.org/abs/2606.08755 [A]
25. Shuaike Shen, Wenduo Cheng, Mingqian Ma, Alistair Turcan, Martin Jinye Zhang, et al. "SkillFoundry: Building
    Self-Evolving Agent Skill Libraries from Heterogeneous Scientific Resources." arXiv 2604.03964, 2026.
    https://arxiv.org/abs/2604.03964 [A]
26. Huawei Lin, Peng Li, Jie Song, Fuxin Jiang, Tieying Zhang, et al. "MUSE-Autoskill: Self-Evolving Agents via Skill
    Creation, Memory, Management, and Evaluation." arXiv 2605.27366, 2026. https://arxiv.org/abs/2605.27366 [A]
27. Srishti Gautam, Arjun Radhakrishna, Sumit Gulwani. "SkillAxe: Sharpening LLM-Authored Agent Skills Through
    Evaluation-Guided Self-Refinement." arXiv 2606.10546, 2026. https://arxiv.org/abs/2606.10546 [A]
28. Boqin Yuan, Yue Su, Renchu Song, Sen Yang, Jing Qin, et al. "ClawTrace: Cost-Aware Tracing for LLM Agent Skill
    Distillation." Agent Skills '26 Workshop (CAIS 2026); arXiv 2604.23853. https://arxiv.org/abs/2604.23853 [A]
29. Yiyang Feng, Biddut Sarker Bijoy, Niranjan Balasubramanian, Jiawei Zhou. "Break It Down, Pass It On: Cross-Task
    Skill Transfer in LLM Agents." arXiv 2608.20274, 2026. https://arxiv.org/abs/2608.20274 [A/F]
30. Yanna Jiang, Delong Li, Haiyu Deng, Baihe Ma, Xu Wang, et al. "SoK: Agentic Skills -- Beyond Tool Use in LLM
    Agents." arXiv 2602.20867, 2026. https://arxiv.org/abs/2602.20867 [F]
31. Tianming Sha, Yue Zhao, Lichao Sun, Yushun Dong, et al. "SkillCenter: A Large-Scale Source-Grounded Skill Library
    for Autonomous AI Agents." arXiv 2607.07676, 2026. https://arxiv.org/abs/2607.07676 [F, placebo arm]
32. Wei-Jung Huang. "Do LLM-Generated Skills Make Better AI Data Scientists? A Component Ablation Across Data-Science
    Workflows." KDD 2026 Workshop on AI Data Scientist; arXiv 2607.07504. https://arxiv.org/abs/2607.07504 [F]
33. simonether. "skill-placebo: Placebo-controlled benchmark of the most-starred coding agent skills." GitHub (informal,
    not peer-reviewed; measured 2026-09-30). https://github.com/simonether/skill-placebo [S]
34. Barry Zhang, Keith Lazuka, Mahesh Murag (Anthropic). "Equipping agents for the real world with Agent Skills." 16 Oct
    2025 (open-standard update 18 Dec 2025).
    https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills [F]; https://agentskills.io [S]
35. OpenAI. "Agentic AI Foundation" (AGENTS.md contributed to the Linux Foundation's Agentic AI Foundation), 9 Dec 2025.
    https://openai.com/index/agentic-ai-foundation/ [S]
36. Rui Sun, Zhi Zheng, Zhenkun Wang, Zhichao Lu. "GraphSkillEvo: Evolutionary Optimization of Graph-Structured Agent
    Skills." arXiv 2609.21749, 2026. https://arxiv.org/abs/2609.21749 [A]
37. Changguo Jia, Tianqi Zhao, Zhiyou Xiao, Weiming Zhang, Minghui Zhou, et al. "VeriSkill: A Self-Evolution Framework
    for Program Verification Skills." arXiv 2607.27733, 2026. https://arxiv.org/abs/2607.27733 [A]

Program evolution and agent-design search (§3):

38. Bernardino Romera-Paredes et al. "Mathematical discoveries from program search with large language models"
    (FunSearch). Nature, 2024. doi:10.1038/s41586-023-06924-6 [S]
39. Alexander Novikov, Ngân Vũ, Marvin Eisenberger, Emilien Dupont, Po-Sen Huang, et al. (Google DeepMind). "AlphaEvolve:
    A coding agent for scientific and algorithmic discovery." arXiv 2506.13131, 2025. https://arxiv.org/abs/2506.13131 [F]
40. Shengran Hu, Cong Lu, Jeff Clune. "Automated Design of Agentic Systems." ICLR 2025; arXiv 2408.08435.
    https://arxiv.org/abs/2408.08435 [F]
41. Jiayi Zhang, Jinyu Xiang, Zhaoyang Yu, Fengwei Teng, Xionghui Chen, et al. "AFlow: Automating Agentic Workflow
    Generation." ICLR 2025; arXiv 2410.10762. https://arxiv.org/abs/2410.10762 [F]
42. Jenny Zhang, Shengran Hu, Cong Lu, Robert Lange, Jeff Clune. "Darwin Godel Machine: Open-Ended Evolution of
    Self-Improving Agents." ICLR 2026 (per the PDF header); arXiv 2505.22954. https://arxiv.org/abs/2505.22954 [F]
43. Yecheng Jason Ma, William Liang, Guanzhi Wang, De-An Huang, Osbert Bastani, et al. "Eureka: Human-Level Reward Design
    via Coding Large Language Models." ICLR 2024; arXiv 2310.12931. https://arxiv.org/abs/2310.12931 [A]
44. Omar Khattab, Arnav Singhvi, Paridhi Maheshwari, Zhiyuan Zhang, Keshav Santhanam, et al. "DSPy: Compiling Declarative
    Language Model Calls into Self-Improving Pipelines." ICLR 2024 [mem]; arXiv 2310.03714.
    https://arxiv.org/abs/2310.03714 [A]. (GEPA arXiv 2507.19457 and SkillOpt arXiv 2605.23904 are in D10.)

Co-evolving verifiers and task generators (§4):

45. Yifei Zhou, Sergey Levine, Jason Weston, Xian Li, Sainbayar Sukhbaatar. "Self-Challenging Language Model Agents."
    arXiv 2506.01716, 2025 (venue not checked). https://arxiv.org/abs/2506.01716 [F]
46. Yinjie Wang, Ling Yang, Ye Tian, Ke Shen, Mengdi Wang. "Co-Evolving LLM Coder and Unit Tester via Reinforcement
    Learning" (CURE). NeurIPS 2025 Spotlight; arXiv 2506.03136. https://arxiv.org/abs/2506.03136 [F]
47. Zi Lin, Sheng Shen, Ilia Kulikov, Jingbo Shang, Jason Weston, Yixin Nie. "Learning to Solve and Verify: A Self-Play
    Framework for Code and Test Generation" (Sol-Ver). arXiv 2502.14948, 2025. https://arxiv.org/abs/2502.14948 [A/F]
48. Bei Chen, Fengji Zhang, Anh Nguyen, Daoguang Zan, Zeqi Lin, Jian-Guang Lou, Weizhu Chen. "CodeT: Code Generation with
    Generated Tests." ICLR 2023 [mem]; arXiv 2207.10397. https://arxiv.org/abs/2207.10397 [A]
49. Kaiwen Zha, Zhengqi Gao, Maohao Shen, Zhang-Wei Hong, Duane S. Boning, Dina Katabi. "RL Tango: Reinforcing Generator
    and Verifier Together for Language Reasoning." NeurIPS 2025; arXiv 2505.15034. https://arxiv.org/abs/2505.15034 [F]
50. Yuxiang Wei, Zhiqing Sun, Emily McMilin, Jonas Gehring, David Zhang, Gabriel Synnaeve, Daniel Fried, Lingming Zhang,
    et al. "Toward Training Superintelligent Software Agents through Self-Play SWE-RL." ICML 2026; arXiv 2512.18552.
    https://arxiv.org/abs/2512.18552 [F]
51. Bo Liu, Chuanyang Jin, Seungone Kim, Weizhe Yuan, Wenting Zhao, et al. "SPICE: Self-Play In Corpus Environments
    Improves Reasoning." arXiv 2510.24684, 2025. https://arxiv.org/abs/2510.24684 [F]
52. Peng Xia, Kaide Zeng, Jiaqi Liu, Can Qin, Fang Wu, Yiyang Zhou, Caiming Xiong, Huaxiu Yao. "Agent0: Unleashing
    Self-Evolving Agents from Zero Data via Tool-Integrated Reasoning." COLM 2026; arXiv 2511.16043.
    https://arxiv.org/abs/2511.16043 [F]
53. Maxence Faldor, Jenny Zhang, Antoine Cully, Jeff Clune. "OMNI-EPIC: Open-endedness via Models of human Notions of
    Interestingness with Environments Programmed in Code." ICLR 2025; arXiv 2405.15568. https://arxiv.org/abs/2405.15568 [F]
54. Abhay Zala, Jaemin Cho, Han Lin, Jaehong Yoon, Mohit Bansal. "EnvGen: Generating and Adapting Environments via LLMs
    for Training Embodied Agents." COLM 2024; arXiv 2403.12014. https://arxiv.org/abs/2403.12014 [A]
55. Michael Dennis, Natasha Jaques, Eugene Vinitsky, Alexandre Bayen, Stuart Russell, et al. "Emergent Complexity and
    Zero-shot Transfer via Unsupervised Environment Design" (PAIRED). NeurIPS 2020 [mem]; arXiv 2012.02096.
    https://arxiv.org/abs/2012.02096 [A]
56. Yifei Zhou, Qianlan Yang, Kaixiang Lin, Min Bai, et al. "Proposer-Agent-Evaluator (PAE): Autonomous Skill Discovery
    For Foundation Model Internet Agents." arXiv 2412.13194, 2024. https://arxiv.org/abs/2412.13194 [A]
57. Zeyi Sun, Ziyu Liu, Yuhang Zang, Yuhang Cao, et al. "SEAgent: Self-Evolving Computer Use Agent with Autonomous
    Learning from Experience." arXiv 2508.04700, 2025. https://arxiv.org/abs/2508.04700 [A]
58. Andrew Dai, Boris Meinardus, Ciaran Regan, Yingtao Tian, Yujin Tang. "Discovering Novel LLM Experts via
    Task-Capability Coevolution" (AC/DC). ICLR 2026; arXiv 2604.14969. https://arxiv.org/abs/2604.14969 [A]
59. Iman Mirzadeh, Keivan Alizadeh, Hooman Shahrokhi, Oncel Tuzel, Samy Bengio, et al. "GSM-Symbolic: Understanding the
    Limitations of Mathematical Reasoning in Large Language Models." ICLR 2025; arXiv 2410.05229.
    https://arxiv.org/abs/2410.05229 [A]
60. Saurabh Srivastava, Annarose M B, Anto P V, Shashank Menon, Ajay Sukumar, et al. "Functional Benchmarks for Robust
    Evaluation of Reasoning Performance, and the Reasoning Gap." arXiv 2402.19450, 2024. https://arxiv.org/abs/2402.19450 [A]
61. Gaurav Maheshwari, Dmitry Ivanov, Kevin El Haddad. "Efficacy of Synthetic Data as a Benchmark." arXiv 2409.11968,
    2024. https://arxiv.org/abs/2409.11968 [A]
62. Shaokun Zhang, Ming Yin, Jieyu Zhang, Jiale Liu, et al. "Which Agent Causes Task Failures and When? On Automated
    Failure Attribution of LLM Multi-Agent Systems" (Who&When). ICML 2025 [mem]; arXiv 2505.00212.
    https://arxiv.org/abs/2505.00212 [A]
63. Mert Cemri, Melissa Z. Pan, Shuyi Yang, Lakshya A. Agrawal, et al. "Why Do Multi-Agent LLM Systems Fail?" (MAST).
    arXiv 2503.13657, 2025. https://arxiv.org/abs/2503.13657 [A]
64. Lionel Wong, Jiayuan Mao, Pratyusha Sharma, Zachary S. Siegel, Jiahai Feng, et al. "Learning adaptive planning
    representations with natural language guidance" (Ada). arXiv 2312.08566 (ICLR 2024 [mem]).
    https://arxiv.org/abs/2312.08566 [A]
65. Wasu Top Piriyakulkij, Yichao Liang, Hao Tang, Adrian Weller, Marta Kryven, et al. "PoE-World: Compositional World
    Modeling with Products of Programmatic Experts." arXiv 2505.10819, 2025. https://arxiv.org/abs/2505.10819 [A]
66. Nicola Dainese, Matteo Merler, Minttu Alakuijala, Pekka Marttinen. "Generating Code World Models with Large Language
    Models Guided by Monte Carlo Tree Search" (GIF-MCTS). NeurIPS 2024; arXiv 2405.15383.
    https://arxiv.org/abs/2405.15383 [A]

Pointers to the earlier notes: Absolute Zero (arXiv 2505.03335) and R-Zero (arXiv 2508.05004) in E10 §2 and §10; GEPA,
SkillOpt, ExpeL, AWM, ACE, Dynamic Cheatsheet, SkillsBench (arXiv 2602.12670), ContinualSkillBench and EvoSkill (arXiv
2603.02766, a different paper from CoEvoSkills) in D10 §3; StateAct, AdaPlanner and SpreadsheetBench in D3.
