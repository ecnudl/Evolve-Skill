# E10 -- The co-evolution loop as a game: stability, collapse, stop rules

Direction E10, explorer report, 2026-10-21 (written 04:40-05:45 CST). Serves **purpose 1** (co-evolution: the Skill
evolves AND the verification side -- the "coding rubric" -- evolves), with the objective defined by **purpose 2**
(generalisation: evolve on ONE benchmark, evaluate on the rest).
Labels used throughout: **[measured]** = computed by me from data in this session or read from a verified record with its
denominator; **[cited]** = read in the cited paper's text in this session (page text extracted with pdftotext);
**[estimate]** = my arithmetic from measured unit costs; **[claim]** = my design proposal or judgement, not evidence.

All work products: new machine `/data/feasibility/E10/` (scripts/, out/, logs/); Mac copy of scripts and literature
under `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/E10/`.
No repository file was modified; no test/holdout pool was read (the pilot uses the SearchQA training pool through the
frozen v3 `data.pool`, which loads only the historical train+val parts, minus the 200 cal-1 items).

## 0. Bottom line

1. **A zero-sum "verifier tries to beat the Skill" game is the wrong game for this project's objective.** Every
   self-play or adaptive item-generation system surveyed rewards the item writer for difficulty or learnability
   (self-play: R-Zero, Absolute Zero, SPIRAL; adaptive benchmarks: AutoBencher, Dynabench). Where the answer key comes from the players themselves, harder items get less reliable
   keys (R-Zero: pseudo-label accuracy 79.0% -> 69.0% -> 63.0% over three iterations, performance collapse after 1-3
   iterations); SPIRAL reports "thinking collapse" and exploitation of fixed opponents; only the systems anchored in
   an executor or simulator (Absolute Zero, POET) avoid key decay [cited]. This project has already measured the matching failure on the solver side:
   OfficeQA candidates that looked +13 points better on 124 generated items were +0 on 74 real items (30/6, p=0.0001
   vs 11/12 and 9/9, p=1.0) [measured, ledger 10/15 17:37]. The verifier must therefore be rewarded for **measuring
   the Skill's real behaviour well** (fidelity), with difficulty only a band constraint, never the objective [claim].
2. **The one measurement that shows the verifier side is improving: content-scale ladder fidelity.** Freeze a ladder
   of Skill texts (and one solver-model contrast) whose real effects on the source benchmark are measured once on
   real training items (cal-1 does this for SearchQA: 11 arms x 200 items x 4 runs; ids-full +0.0925 [+0.050,
   +0.135], control:3 -0.100 [-0.138, -0.060], same-text parent:B +0.0075) [measured]. Each verifier version's panel
   is solved by the same ladder; the verifier improves when, at a fixed panel size (>= 120 items) and audited validity
   >= 90%, the rank agreement (Kendall tau, plus correct signs on the large contrasts) between panel effects and real
   effects rises toward the real-item noise ceiling -- computed on items valid by two judges and with a
   format-robust scorer, so that answer-format effects cannot carry it. The ceiling on REAL items is tau 0.71 at 30
   items x 2 runs, 0.81 at 100 x 2, 0.86 at 150 x 2 [measured, cal-1 resampling]; the pilot shows why the two
   qualifiers are needed (with alternative forms accepted, v0's agreement with the real ladder vanishes). Harder items,
   more rubric rewrites or a higher detection count are NOT evidence of verifier progress.
3. **Pilot e10p1 (real calls, this session, ~1.97M tokens)**: the 10/13 SearchQA generator as verifier v0, then two
   revision rounds under a difficulty-only policy (F) and an anchored policy (A); 102 generated items x 3 cal-1 arms x
   2 runs = 612 scored cells (0 unknown), every item audited by GLM-5.3 (twice for rounds 1-2), every item with a
   failure hand-checked by me.
   (a) On the items that BOTH judges call valid, the solver made **0 content errors in 468 cells** (78 items); all 93 content
   failures sit on the 24 items non-valid by either judge (alias answers, two-referent questions, a wrong key). The
   text-level verifier makes items "hard" only through output format and invalid items. (b) Non-valid share: v0
   5/30 (17%); F 4/18 then 3/18; A 7/18 then 5/18 -- noisy, not monotonic, not significant (B0 vs A1 Fisher p = 0.10).
   (c) The drift is in what the revisers ask for: the difficulty-only reviser invented scorer exploitation by itself
   ("ensure only the exact snippet form is correct ... so formatting mismatche[s]") and in round 2 asked for answers
   "never" stated verbatim (contradicting the generator's own validity rule) while the GLM reviewer still accepted
   26/27 of its candidates; the anchored reviser avoided that but produced two-referent questions, and in round 2 it
   wrote a list of validity rules -- a coding rubric in prose -- whose own items still broke it (and its "shortest
   form" rule created the mirror-image alias traps: cycling). (d) The GLM auditor is stable (72/72 identical labels on
   retest) but blind to most two-referent flaws (missed 3 of 5; its non-valid set was always a subset of mine).
   (e) The generated panel reproduces the real ladder's signs in 4 of 5 batches (A1 lost one), but with alternative answer
   forms accepted every v0 contrast is exactly 0: the agreement is an agreement on answer format, not content.
4. **Minimal v5 loop** (section 7): source = **OfficeQA** (executable calculation items can be valid AND hard; three
   registered similar targets), with SearchQA kept as the cheap machinery test bed; build an OfficeQA ladder first;
   K <= 4 rounds; the Skill is accepted only on fresh REAL source batches (D1); a verifier version is accepted only
   if audited validity >= 90%, content-scale ladder fidelity is not worse, and its difficulty is inside a band;
   validity rules are code, not prose; five stop rules. Cost about 65-90M tokens on OfficeQA (30-40M on SearchQA),
   including the one-time ladder and the sealed final evaluation [estimate from measured unit costs].
5. **Feasibility: medium for the loop, low for "a verifier that gets better by pushing difficulty".** The mechanics
   exist and are cheap; the pilot says the verifier side improves only if it is optimised for validity and fidelity
   with executable checks, and that SearchQA cannot show content-level verifier progress at all. Whether the verifier
   may be calibrated once on target TRAINING items is an owner decision (7.5).

## 1. Formalisation: the players, the payoffs, and where transfer enters

**Objects.** Source benchmark s; target set T = the other four benchmarks; registered similar pairs (searchqa, officeqa),
(officeqa, livemath), (officeqa, spreadsheetbench). Solver = fixed model M (deepseek-v4-flash) + Skill text S.
mu_b(S) = expected score of (M, S) on real items of benchmark b. Verifier V = (generator spec g, criteria/rubric c,
checker code k); it emits a panel P_V of items (x, y, metadata) in the style of some benchmark, with y guaranteed by k.

**The unobservable objective (purpose 2).** J(S) = sum over similar targets t of [mu_t(S) - mu_t(S_0)], subject to
mu_t(S) >= mu_t(S_0) - eps on dissimilar targets. J is measured once, at the end, on sealed test panels. During
evolution the loop can observe only (i) real source training items and (ii) the verifier's panels.

**Skill player.** Proposes edits to S from failures (real source failures, plus generated-item failures as extra
training material). Its acceptance payoff must be a real-source quantity: the paired gain on a fresh batch of real
source training items (D1). [claim]

**Verifier player.** Proposes V' (new generator guidance, new typed item families, new checks). Three candidate
payoffs, and what each one does:
- Adversarial (zero-sum, "fool the Skill"): R-Zero's uncertainty reward 1 - 2|p - 1/2| [cited], AZR's learnability
  1 - r for 0 < r < 1 [cited], SPIRAL's zero-sum win [cited], AutoBencher's difficulty = 1 - best accuracy [cited],
  Dynabench's model-fooling rate [cited]. These maximise training signal, and they push items toward the
  validity boundary (section 3, mode M1).
- Benchmark-quality (AutoBencher): difficulty + separability + novelty, where novelty = LOW rank correlation with
  existing benchmarks [cited]. For a transfer instrument this is backwards: we need panels whose rankings of Skill
  versions AGREE with real benchmarks.
- **Measurement (proposed)**: payoff = fidelity(P_V) = agreement between effects measured on P_V and effects measured on
  real items, over a frozen ladder L of Skill texts with independently measured real effects; subject to
  validity >= 90% (audited), a difficulty band (the current Skill passes 25%-85% of items), and coverage of the real
  failure features. The game is then cooperative, not zero-sum: the verifier wins when it measures the Skill's real
  generalisation better, not when the Skill loses. [claim]

**Where transfer enters.** (a) The final metric J (sealed). (b) During evolution, rules with placement `similar` are
checked for no-harm/gain on the verifier's target-style panels (v3 C4'), but such panels count only after the
target-style generator passed a fidelity check against real target items -- otherwise the 10/15 bias (generated gain
!= real gain) applies in full. (c) The verifier's fidelity on the SOURCE benchmark is the only fidelity measurable
without touching target data; whether a one-time, frozen instrument check on target TRAINING items is allowed is an
owner decision (7.5). [claim]

**The two readings of "coding rubric".** (i) Text criteria that drive generation and judging. This project ran it
(learning v10 `rubric_research`): the rubric was rewritten in 16 of 27 steps, but its content stayed locked on "answer
in the requested form and scope"; its own uncertainty field said it could not judge numerical correctness; detection
was OfficeQA 0-4/20, SearchQA 0-3/21, LiveMath 0/80 [measured, ledger 10/15 10:00]. (ii) Executable item
specifications and checks: a typed task spec, a program that computes the reference answer, then question rendering
(D6); v3 `forward.py` already decides validity by exact rational arithmetic, never by a model alone [measured, code
header]; AZR's executor checks (syntax, forbidden modules, determinism by running twice) [cited]. **Reading (ii) is
more promising**, because validity then holds by construction and cannot drift under difficulty pressure; reading (i)
inherits the correlated-error problem of a same-model writer/reviewer/solver. The pilot below tests a reading-(i)
verifier on purpose, because that is where drift is expected to show. [claim]

## 2. Survey: stability mechanisms and reported failure modes [cited unless marked]

Papers read this session (pdftotext copies under `.../feas/E10/lit/`): R-Zero (arXiv 2508.05004, ICLR 2026), Absolute
Zero Reasoner (arXiv 2505.03335), SPIRAL (arXiv 2506.24119, ICLR 2026), AutoBencher (arXiv 2407.08351, ICLR 2025),
Promptbreeder (Fernando et al. 2023), Dynabench (Kiela et al. 2021), LM-as-an-Examiner (Bai et al. 2023), POET (Wang et
al. 2019), Substitution of the Fittest (coevolutionary disengagement; it cites Hillis's sorting networks, Watson &
Pollack 2001 on disengagement, Rosin & Belew 1997 Hall of Fame).

| System | What co-evolves | How validity is protected | How difficulty is controlled | Diversity | Reported failure modes |
|---|---|---|---|---|---|
| R-Zero | Challenger and Solver, two models from one base | Majority-vote pseudo-label over m=10 samples; keep a question only if 3-7 of 10 answers match (delta=0.25) | Uncertainty reward 1-2abs(p-1/2) | BLEU-cluster repetition penalty (tau=0.5) | Performance degrades after a few iterations: 0.6B peaks at iteration 1, 4B "sharp drop at Step 60" after three; pseudo-label accuracy (GPT-4o oracle, 200 questions per iteration) 79.0% -> 69.0% -> 63.0%; static solver accuracy on the questions 59.0% -> 47.0% (harder); single shared model: label accuracy 63.4% vs 71.0%, peaks after iteration 1; removing the filter costs >6 points general-domain |
| Absolute Zero (AZR) | One model as proposer and solver | Python executor: syntax, forbidden modules (os.sys, sys, shutil...), determinism (run j=2 times, outputs equal) | Learnability: 0 if solve rate is 0 or 1, else 1 - solve rate (G Monte Carlo rollouts) | K reference triplets sampled from growing buffers | "Uh-oh moment": Llama-3.1-8B produced concerning chains of thought |
| SPIRAL | One policy playing both sides of zero-sum games | Game rules (environment) | Self-play (opponent improves with the learner) | Several games | Without role-conditioned advantage: "thinking collapse" within 100 iterations (reasoning traces ~2,000 chars -> near 0; general reasoning 44% -> 40%); fixed opponents get exploited (win rate vs Gemini 0% -> 62.5%) and gains plateau; random opponents "cause collapse" |
| Promptbreeder | Task-prompts and mutation-prompts | Fitness on a random batch of training data | none (fitness only) | Population, binary tournament; EDA mutation lists exclude prompts with BERT cosine > 0.95 to another | Motivated by APE's diminishing returns and diversity loss; in preliminary experiments an LLM shown fitness values "did not understand" them and "resorted to generating copies" |
| AutoBencher | Dataset descriptions (topics) | Privileged information for the writer (retrieval, Python); human check: 5% label error (math/econ 3%, history 6.7%, science 7.2%) | Objective: difficulty (1 - best accuracy) + separability + novelty, salience constraint | Novelty = low rank correlation with existing benchmarks | Without privileged information: hallucinated answers, difficulty capped by the writer's own ability, well-known topics; ChatGPT 97%+ on LM-Examiner items vs ~60% on AutoBencher's |
| Dynabench | Human writers vs models in the loop | Other humans validate model-fooling examples (validated model error rate) | Writers try to fool the current model | Rounds | "Cyclical progress": improved models forget earlier rounds when writers focus on one weakness; unnatural distributions; recommendation: evaluate on ALL rounds plus any static test set, "a bad idea to throw away old tests" |
| LM-as-an-Examiner | Examiner LM writes questions and judges | Human check: 100/100 examiner answers correct; 85% human-GPT-4 agreement on 100 questions | Follow-up questions for depth | Peer-examination (several examiners) | Single-examiner bias (the reason for peer-examination); items easy for strong models (97%+ per AutoBencher) |
| POET | Environments and agents | Environment simulator | Minimal criterion: a child environment is kept only if 50 <= score <= 300 for the current agents | Novelty ranking of environments | Paper's own argument: transfer of agents between environments is essential to progress |
| Classic coevolution (via SoF) | Hosts and parasites (Hillis) | n/a | Arms race | Hall of Fame archive (Rosin & Belew 1997) | Disengagement (one side dominates, gradient vanishes), cycling, loss of old competences |

Three cross-cutting lessons [claim, from the table]: (1) every working system has an **external validity anchor that
the players cannot move** -- an executor (AZR), game rules (SPIRAL), a simulator (POET), humans (Dynabench), privileged
documents (AutoBencher); R-Zero, whose anchor is the solver's own majority vote, is the one that documents label decay.
(2) Difficulty is always **band-limited** (R-Zero 3-7/10, AZR 0<r<1, POET 50-300), never maximised. (3) Long runs
need an **archive**: old rounds stay in the evaluation (Dynabench, Hall of Fame), otherwise progress cycles.
None of the surveyed systems optimises the verifier for **predictive validity of transfer**; AutoBencher optimises the
opposite (novelty). That is a gap this project can occupy honestly.

## 3. This project's own evidence on the verifier side (all measured; ledger / status entries)

| Date | What was measured | Result | Collapse mode it illustrates |
|---|---|---|---|
| 10/15 17:37 (GLM-5.3) | Learned OfficeQA candidates oq_s1/oq_s2 vs zero-shot instruction on 124 generated vs 74 real items | Generated: 0.859/0.847 vs 0.730 (30 better/6 worse, p=0.0001); real: 0.595/0.622 vs 0.601 (11/12 and 9/9, p=1.0) | M3: Skill overfits generated items |
| 10/16 overnight (deepseek) | Pruning check of oq_s2's clauses beyond bzero | +7 to +9 points on generated items, not measurable on real items | M3 |
| 10/15-16 (3 solvers) | learned - bzero, 74 real OfficeQA items vs 124 generated | Real: zero gain on all 3 solvers (p>0.1); generated: lead replicates within GLM family, vanishes on deepseek-v4-flash (9/9, p=1) | M3, and model-family dependence of generated-item effects |
| 10/15 10:00 audit | Item stability of generated panels | OfficeQA 124 generated items x 12 runs: 48% always right, 49% flip, 2% always wrong; real OfficeQA 74 items: 28% stable failures; SearchQA 168 generated items x 2 runs: 89% right both times | M2: trivial / non-discriminating items |
| 10/15 10:00 audit | Text rubric evolution (v10) | Rewritten in 16/27 steps, content locked on "form and scope"; detection OfficeQA 0-4/20, SearchQA 0-3/21, LiveMath 0/80 | Verifier "evolves" without gaining power |
| 10/16 12:37 | Feature-aware OfficeQA generator v3, pre-registered go/no-go | Fidelity (total variation vs real profile; limits 0.25/0.20/0.25): D 0.335/0.250/0.375, T 0.380/0.231/0.346 -> fail; difficulty: generated 0.717/0.718 vs real 0.569 (+0.147/+0.149, limit 0.10) -> fail; 3.6M GLM tokens | Validity rules (state the rounding, one computed number) conflict with realism |
| 10/19-20 v3 run | Generated-task pathway in the protocol | Never ran: all 49 proposals got placement `local` | The verifier side had no exercise at all |

Reading [claim]: the project has already seen modes M2 (too easy) and M3 (overfitting generated items) on real
data, and seen that a text rubric can be rewritten every step without becoming more discriminating. It has NOT yet
seen M1 (drift to invalid items under difficulty pressure) because no loop ever pushed a verifier toward difficulty;
that is what the pilot tests.

## 4. Collapse modes, the mechanism that prevents each, and the observable that triggers a stop

| Mode | What happens | Evidence | Prevention [claim] | Observable / stop trigger [claim] |
|---|---|---|---|---|
| M1 Drift to invalid/unsolvable | Pressure for "harder" makes items ambiguous, wrongly keyed or unanswerable | R-Zero 79->63% label accuracy [cited]; AutoBencher hallucinated answers without privileged info [cited] | Validity by construction (executor / verbatim quote + deterministic filters); difficulty only as a band; invalid items count as verifier failures; independent audit sample each round | Audited invalid share of a 30-item sample > 10% (>= 4/30) -> reject V' |
| M2 Drift to trivial / disengagement | Items the current Skill always passes; no discrimination | 10/15: 89% SearchQA generated items right twice; v3 generator 15 points easier than real [measured] | Band filter on the CURRENT Skill and on the ladder; target mixed share | Current-Skill pass rate outside [0.25, 0.85] or mixed share < 30% -> re-band, V' not accepted |
| M3 Skill overfits generated items | Edits that help generated items only | 10/15: +13 pts generated, 0 real [measured] | Acceptance only on fresh REAL source batches (D1); generated items are training material and diagnostics only | Generated-panel gain exceeds fresh-real gain by > 2 SE in 2 consecutive rounds -> stop the loop |
| M4 Agreement on wrong answers (collusion) | Writer, reviewer, solver share a blind spot; wrong key accepted, solver "agrees" | R-Zero single model: 63.4% vs 71.0% label accuracy [cited]; LM-Examiner peer-examination [cited]; 10/14 generator: writer, reviewer, solver the same model [measured, workflow doc] | Never use solver agreement as ground truth; reviewer/auditor from another model family or a human sample; scorer-robustness check (alternative correct forms) | Audit: "pass on an item labelled wrong/ambiguous/unanswerable" counted and reported; > 5% -> reject V' |
| M5 Cycling / forgetting | Skill fixes this round's weakness, loses earlier ones | Dynabench [cited]; Hall of Fame [cited] | Archive of all accepted panels; Skill measured on all past panels + static real set | Any past-panel score drop beyond its non-inferiority margin -> reject the Skill version |
| M6 Red Queen (relative progress only) | Both sides "improve" relative to each other, nothing absolute | Coevolution literature [cited via SoF]; SPIRAL fixed-opponent exploitation [cited] | Fixed anchors: the frozen ladder and real source batches never change | Fidelity on the frozen ladder, not win rate, decides verifier acceptance |

## 5. Free analysis: how large must a verifier panel be before "ladder fidelity" means anything? [measured]

Data: E7's read-only compact export of the completed cal-1 unit (`/data/feasibility/E7/run2/cal1_cells_compact.json`,
8,800 cells; 185 of the 200 items have all 4 runs for all 11 arms). I first re-ran the earlier E10 ladder script on it
(`scripts/cal1_ladder.py`, output `out/cal1_ladder.json`): per-arm paired effects vs parent:A over 200 items reproduce
exactly -- seed-only +0.0883, ids-full +0.0925 [+0.050, +0.135] (46 up/13 down), control:2 +0.0338, parent:B +0.0075
[-0.011, +0.026] (same text: 20 up/16 down), seed-rule +0.0029, control:4 0.0, cand -0.0275, seed-rule3 -0.0312,
control:1 -0.0375, control:3 -0.100 [-0.138, -0.060] (14 up/58 down); over all 11 arms 50 items always pass, 25 always
fail, 125 mixed. Then `scripts/ladder_power.py` (output `out/ladder_power.json`) resampled REAL panels of n items with r
runs per arm (400 draws each) and asked how well a panel reproduces the full-data arm effects:

| Panel | Kendall tau, median [p10, p90] | P(ids-full effect > 0) | P(control:3 effect < 0) | P(95% CI of ids-full excludes 0) |
|---|---|---|---|---|
| 30 items x 2 runs | 0.714 [0.50, 0.86] | 0.915 | 0.930 | 0.36 |
| 60 x 2 | 0.773 [0.66, 0.91] | 0.975 | 0.990 | 0.52 |
| 100 x 2 | 0.814 [0.68, 0.91] | 0.995 | 1.000 | 0.735 |
| 150 x 2 | 0.860 [0.73, 0.95] | 1.000 | 1.000 | 0.92 |
| 200 x 2 | 0.864 [0.77, 0.96] | 1.000 | 1.000 | 0.97 |
| 200 x 4 | 0.864 [0.81, 0.96] | 1.000 | 1.000 | 0.988 |

Reading: this is the best any generated panel could do if its items behaved exactly like real ones (an optimistic,
in-sample ceiling). Tau saturates near 0.86 because 7 of the 10 arms have |effect| < 0.04 and their order is noise. A
30-item panel can confirm only the signs of the two large contrasts; ~150 items x 2 runs are needed to resolve the
+0.09 effect itself. Verifier versions must therefore be compared at >= 120-150 items, or with a ladder of larger
spread.

## 6. Pilot e10p1: does difficulty pressure collapse a text-level verifier, and do anchors prevent it? [measured]

**Design (fixed before launch; `out/e10p1/prereg.json`, sha256 0f077544...; launch deviations in
`out/e10p1/launch-notes.json`).** Verifier v0 = the 10/13 SearchQA generator (`scripts/generate_searchqa_tasks.py`,
version generated-searchqa-tasks-v1): its WRITER and REVIEWER prompts read verbatim by `ast`, its deterministic filters
re-implemented verbatim, acceptance = all four review verdicts true; GLM-5.3 (thinking on, effort low, temperature 0).
Source items: SearchQA training pool (historical train 400 + val 200 through the frozen v3 `data.pool`), minus the 200
cal-1 items (asserted equal to E7's cal-1 item set), shuffled with seed 20261021 into disjoint source blocks per batch.
Batches: B0 = v0 with no guidance (target 30 items); then two revision policies append a <= 1,200-character guidance
block to the WRITER prompt, written by a GLM-5.3 reviser from the last batch: **F** (difficulty only: sees each item's
reference, the current Skill's 2-run outcome and answers; told to make the solver fail more often) and **A**
(anchored: additionally sees the audit label of every item, six real clues as style anchors and the real answer-form
profile; told to aim for "sometimes right", stay valid and realistic, and that every non-valid item is a failure).
Round 1 = F1 and A1 (18 items each), round 2 = F2 and A2 (time permitting). Every kept item is solved by three cal-1
arms (SHA-256 checked) x 2 runs with the cal-1 solver configuration (deepseek-v4-flash, thinking off, temperature 0,
max_tokens 32768, frozen v3 `backends.solve`/`score`, layout contract-first-v2): parent:A (empty scaffold), ids-full
(the five task-card seeds = the "current Skill" shown to the reviser), control:3 (a placebo text). parent:A and
control:3 are never shown to any verifier role. Audit: one GLM-5.3 call per item (reason, then valid / alt_forms /
ambiguous / wrong / unanswerable, and a correctness judgement of every distinct solver answer). I also spot-checked by
hand every B0 item on which any arm failed (13 items).
Launch log: launch 1 (04:44) stalled on the single-cell gate (no deepseek reply for > 3.5 min); launch 2 (04:50) removed
the gate (the 04:43 smoke had confirmed a real reply), deepseek read timeout 900 -> 240 s; launch 3 (04:55) reduced the
round targets from 24 to 18 items for time. The B0 items were generated once (launch 1) and reused; the source blocks of
F/A batches therefore differ from those listed in prereg.json (the actual sources are in each batch's
generation_log.json). Pass/fail cells are cached and never re-run.

### 6.1 Results, B0 and round 1 (all cells scored; 0 unknown cells)

| Measure | B0 (v0, no guidance) | F1 (difficulty only) | A1 (anchored) | Real cal-1 reference |
|---|---|---|---|---|
| Items kept / sources used / writer candidates | 30 / 30 / 58 | 18 / 12 / 22 | 18 / 18 / 36 | -- |
| Deterministic filter drops (quote not verbatim or lacks answer) | 17/58 | 4/22 | 12/36 | -- |
| Reviewer acceptance | 39/41 | 18/18 | 23/24 | -- |
| GLM audit: valid / alt_forms / ambiguous / wrong / unanswerable | 25/5/0/0/0 | 14/3/1/0/0 | 13/4/1/0/0 | -- |
| Non-valid by GLM audit OR my hand check | 5/30 (17%) | 4/18 (22%) | 7/18 (39%) | -- |
| Pass rate parent:A / ids-full / control:3 (strict scorer) | 0.833 / 0.917 / 0.700 | 0.833 / 0.861 / 0.667 | 0.639 / 0.806 / 0.639 | 0.681 / 0.774 / 0.581 |
| ids-full - parent:A, strict [95% item bootstrap] | +0.083 [-0.017, +0.200] (4 up/1 down) | +0.028 [-0.056, +0.111] (2/1) | +0.167 [0.000, +0.361] (5/1) | +0.0925 [+0.050, +0.135] |
| control:3 - parent:A, strict | -0.133 [-0.250, -0.033] (1/7) | -0.167 [-0.333, -0.028] (0/4) | 0.000 [-0.111, +0.111] (2/2) | -0.100 [-0.138, -0.060] |
| ids-full - parent:A, JSON-aware rescoring | +0.067 [-0.017, +0.167] | +0.028 [-0.056, +0.111] | +0.139 [-0.028, +0.333] | +0.0775 [+0.038, +0.121] (E7) |
| control:3 - parent:A, JSON-aware | +0.017 [-0.033, +0.067] | 0.000 [-0.083, +0.083] | +0.056 [-0.056, +0.167] | -0.0025 [-0.035, +0.028] (E7) |
| All three arms pass when alternative forms are accepted (lenient) | 0.95 / 0.95 / 0.95 | 0.889 / 0.917 / 0.889 | 0.778 / 0.861 / 0.806 | -- |
| Items all-pass / all-fail / mixed (6 cells) | 17 / 1 / 12 | 11 / 1 / 6 | 9 / 2 / 7 | 50 / 25 / 125 of 200 (11 arms) |
| Failed cells: content / alt-form / JSON / no tag (mechanical; 'content' = tagged answer neither equal to nor containing/contained in the reference) | 7 / 13 / 11 / 2 (of 33) | 11 / 5 / 7 / 0 (of 23) | 15 / 9 / 5 / 4 (of 33) | -- |
| Mean question length (chars); pairwise token Jaccard | 77.5; 0.082 | 116.4; 0.072 | 107.9; 0.089 | -- |
| Answers of 1 / 2 / >=3 words; with a digit | 30% / 43% / 27%; 6.7% | 39% / 33% / 28%; 22% | 50% / 33% / 17%; 5.6% | 45.9% / 38.6% / 15.4%; 1.2% (246 real items) |

**Headline [measured].** Over the 66 items of B0 and round 1 (396 scored cells; five-batch totals in 6.2), the 50 items that BOTH judges (the GLM audit
and my hand check) call valid produced **0 content failures in 300 cells** (all 21 of their failures are output-format
failures: a JSON answer or no answer tag). All 60 content failures fall on the 16 items that at least one judge calls
non-valid (96 cells). In other words, on this benchmark a text-level verifier v0 creates difficulty for the actual
solver ONLY through format and through invalid items; one round of revision raised the non-valid share (17% -> 22% /
39%; B0 vs A1 Fisher p = 0.10, B0 vs F1 p = 0.71, B0 vs round 1 pooled 11/36 p = 0.25 -- directional, not
significant).

**How each policy drifted [measured, qualitative].** The difficulty-only reviser (F1 guidance, 1,200 characters)
asked for obscure entities, less-central attributes, heavy paraphrase, distractors -- and, unprompted, for scorer
exploitation: "(6) When the answer has variant forms, ensure only the exact snippet form is correct (e.g., full birth
name vs. pen name) so formatting mismatche[s ...]". Its items then included a wrong key (question asks for "this
Beverly Hills landmark", reference "May 12, 1912"; every arm answered "The Beverly Hills Hotel") and date-format traps
("Jan. 14, 1898" vs "January 14, 1898"). The anchored reviser (A1) correctly diagnosed B0's alternative-form problem
("Guidance now mandates canonical shortest forms...") and forbade obscurity, but its "combine two facts" instruction
produced questions with two "this" referents ("This dance and the schottische both came ... from Bohemia, unlike the
waltz and this German import" -> reference galop, every arm but one answered polka; "This singer died ... at this age"
-> reference 44, solvers answered Billie Holiday), plus new alternative-form answers ("Seventh U.S. Cavalry" vs "7th
Cavalry Regiment", "Earl Hamner" vs "Earl Hamner, Jr."). Anchoring changed the route of the drift, not its direction.

**Judges [measured].** The GLM audit agrees with my hand labels on 9 of the 11 round-1 items I flagged, and labels as
valid 2 of my 3 two-referent questions (the "44" and "galop" items) -- exactly the items on which the writer, reviewer
and auditor (all GLM-5.3) share a reading that the solver (deepseek) does not. A second GLM audit call per item (early
audit, `audit_early.json`) reproduced the pilot's audit labels on 36/36 round-1 items (72/72 with round 2): the auditor is stable, so these are
consistent blind spots, not noise (mode M4).

**Ladder fidelity [measured].** B0 reproduces the signs of both large real contrasts under the strict scorer and the
null of control:3 under JSON-aware rescoring; F1 keeps both signs; A1 loses control:3's sign. With 18-30 items the
noise ceiling (section 5) allows only sign checks, so no verifier version can be called better or worse in fidelity
from these data. With alternative forms accepted, B0's contrasts are exactly 0: the agreement with the real ladder is
an agreement on format effects.

**Limitations of the pilot [measured facts about the design].** (1) The Skill side was frozen (the "current Skill" is
the cal-1 ids-full text); this is a test of verifier drift under a fixed solver, not a co-evolution run. (2) My hand
check covered only items on which some arm failed (13 in B0, 11 in round 1); items that all six cells passed were taken
as valid when the GLM audit said so, so the non-valid shares are lower bounds (an ambiguous item answered with the
reference by every arm is invisible here). This cannot change the headline, since all-pass items contain no failures.
(3) One solver (deepseek-v4-flash) and one model for every verifier role (GLM-5.3); one hand checker (me, a third
model family). (4) 18-30 items per batch: policy differences are directional only. (5) Launch deviations (single-cell
gate removed, shorter read timeouts, round targets 24 -> 18) are recorded in `launch-notes.json`; none changes a
prompt, a model setting or the scorer.

### 6.2 Round 2 (F2, A2) -- complete (108/108 cells each, 0 unknown; pilot status `complete`, ledger 539,873 GLM + 1,305,202 deepseek tokens)

| Measure | F2 (difficulty only) | A2 (anchored) |
|---|---|---|
| Writer calls / candidates / filter drops / reviewer acceptance | 18 / 34 / 7 / 26 of 27 | 18 / 35 / 11 / 24 of 24 |
| Guidance (excerpt) | "Never name the target entity ... chain of attributes"; "Prefer answers that require computing or transforming ... where only raw materials appear verbatim, never the final answer"; "Prefer obscure topics" | "STRICTLY avoid answers with equally correct alternate forms ... no Jr./Sr./numeral suffixes ... no 'Seventh' vs '7th' ... no variant spellings ... no quantities with units ... avoid questions where the ask-about noun is ambiguous" |
| Example answers | "Henry John Temple, 3rd Viscount Palmerston"; "One hour of service" (question says "a 60-minute block"); "Sir Robert Walpole"; "Permian High School Panthers" | "tarsier"; "Platyrrhini"; "Thor"; "Hyrrokkin"; "Ghosts" (question "This 1882 Ibsen play ... titled this word": two referents again); "Mt Bogong" |

Reading [measured, qualitative]: the difficulty-only chain escalates exactly as R-Zero's label-decay story predicts --
its round-2 guidance contradicts the generator's own validity rule (answer verbatim in the snippets) and pushes toward
long, alias-prone answers -- while the GLM reviewer, the only gate, accepts 26 of 27 candidates. The anchored chain
spends its guidance budget on a list of validity rules; that list is a coding rubric written in prose, and its items
still show the two-referent and alias failures it forbids.

**Round-2 hand check [measured; all failing items read].** Every failing item I read falls in the same two classes.
F2: alias answers ("Lord Palmerston"/"Palmerston" vs reference "Henry John Temple, 3rd Viscount Palmerston";
"Benjamin Franklin" vs "Ben Franklin"; "60 minutes"/"1 hour" vs "One hour of service") -- non-JSON failures appear only
on these. A2: despite its own explicit ban, alias answers ("Mount Bogong" vs "Mt Bogong"), and its new "shortest
canonical form" rule overshot into new traps ("Richard Cordray" vs reference "Cordray", "Fattal Hotels" vs "Fattal",
"toast them" vs "toast"); one more two-referent question ("This 1882 Ibsen play ... titled this word": ids-full answered
"An Enemy of the People", arguably the better reading). The items on which some arm failed but which are valid (Peggy
Wood, Ben Kingsley, Medici, Iggy Pop, Andre Harrell, Bush) failed only through JSON-format answers. So the reviser
fixes last round's failure in prose and creates the mirror-image failure next round (B0's references were too short
for the solver's fuller answers in some items and too long in others; A2 then forced "shortest" and lost the other
side) -- a small instance of cycling (mode M5). The underlying fix is code, not prose: the verifier should emit an
alias SET per item (every acceptable form found in the snippets, as SearchQA's `answers` list already allows) and a
two-referent check, instead of trying to word its way around a single-string exact-match key.

**Round-2 numbers [measured].** F2: pass parent:A / ids-full / control:3 0.861 / 0.889 / 0.750; ids-full - parent:A
+0.028 [-0.083, +0.167], control:3 - parent:A -0.111 [-0.250, 0.000]; all-pass/all-fail/mixed 13/1/4; JSON-aware
+0.028 / 0.000; lenient +0.083 / +0.028; failed cells content/alt-form/JSON 11/3/4. A2: 0.806 / 0.861 / 0.611; +0.056
[-0.111, +0.222], -0.194 [-0.389, -0.028]; 9/1/8; JSON-aware +0.056 / 0.000; lenient -0.028 / 0.000; failed cells
12 alt-form / 7 content / 7 JSON. GLM audit F2 15 valid / 3 alt_forms, A2 14 / 4 (identical on retest, 18/18 each).
Non-valid by the GLM audit OR my hand check: F2 3/18 (17%), A2 5/18 (28%). Over all five batches (102 items, 612
cells): items valid by both judges (78) -> **468 cells, 0 content failures** (31 format failures: JSON answer or no
tag); items non-valid by either judge (24) -> 144 cells, 93 content failures. The non-valid share is noisy rather than monotonic
(F: 17% -> 22% -> 17%; A: 17% -> 39% -> 28%; rounds 1-2 pooled 19/72 = 26% vs v0 5/30 = 17%), so the evidence for
drift is the content of the guidance (F2's instruction to avoid verbatim answers; the alias traps both chains created),
not the share itself. The GLM auditor's non-valid set was a subset of mine in every batch (5/5, 4/4, 5/7, 3/3, 4/5);
it missed 3 of the 5 referent-type flaws I found (two-"this" questions), never the reverse. The analysis scripts in section 11
regenerate every number from `out/e10p1/` (final summaries: `out/e10p1_analysis_final.json`, `out/e10p1_jsonaware.json`,
`out/e10p1_failtypes.json`).

## 7. Proposed minimal v5 loop (one source benchmark, evaluation on the rest) [claim unless marked]

### 7.1 Choice of source (revised after the pilot)
**Recommended: OfficeQA as the co-evolution source; SearchQA only as the cheap test bed for the machinery.**
SearchQA has the only finished real known-effect ladder (cal-1) [measured], but the pilot shows that its generated
items -- answer verbatim in the snippets by construction -- carry no content signal: 0 content failures in 300 cells
on items valid by two judges (section 6.1). Its real failures are mostly knowledge failures that no generated item of
this kind can reproduce (v3: 50.3% of trigger items "dead" for all arms) [measured, context]. OfficeQA's generated items
are executable calculations over real tables (v3 `forward.py` style, exact rational arithmetic), so a VALID item can
still be genuinely hard (calculation and table-reading errors); the 10/15 audit found 49% of 124 generated OfficeQA
items flip between runs for GLM-5.3 [measured, ledger]. OfficeQA is also the hub of the registered similar pairs
(SearchQA, LiveMath, SpreadsheetBench), so "evolve on one, evaluate on the rest" gives three similar targets and one
dissimilar target (ALFWorld). Cost of the switch: OfficeQA needs its own real ladder first (7.3, 7.6), and its
feature-aware generator failed the 10/16 fidelity limits (rounding stated in 100% of generated vs 72% of real items;
15 points easier), so the verifier's first job on OfficeQA is fidelity, not difficulty.

### 7.2 One round (k = 1..K, K <= 4)
1. **Skill half (solver side).** The v4 step on real source training items (train 200 x 2 -> per-code diagnosis ->
   conditional rules). Generated items of the current verifier V_k are ADDITIONAL training material: their failures
   are diagnosed with the same taxonomy and can be cited as evidence, but never decide acceptance. Acceptance =
   version-level paired gain on a FRESH batch of never-proposed-on real training items (D1, statistical rules from D8).
2. **Verifier half (rubric side).** A reviser proposes V_{k+1} from V_k's measured weaknesses (anchored policy: the
   audit labels, the ladder outcome and real-item anchors are shown; invalid items count as failures). In the
   coding-rubric reading, V_{k+1} may add typed item families with executable reference answers (D6), add checks
   (e.g. an alias/alternative-form check, the B0 failure mode), or change rendering guidance.
   V_{k+1} emits a panel P_{k+1} of >= 120 items on source material NOT used by the fresh acceptance batches.
   Validity rules that the reviser writes as text (as the A2 guidance did) are turned into executable checks (alias /
   alternative-form detector, two-referent detector, verbatim-key rule) and kept only if they lower the audited
   non-valid share without lowering fidelity -- the coding-rubric reading (ii).
3. **Verifier acceptance.** Solve P_{k+1} with the frozen ladder L (7.3) x 2 runs; audit a random 30 items (GLM judge
   with reason-then-label + an independent second-family or human check on 10 of them). Accept V_{k+1} iff ALL of:
   validity >= 90% (<= 3/30 non-valid) and "pass on wrong/ambiguous/unanswerable" = 0; ladder fidelity not worse than
   V_k (every large contrast keeps its real sign; Kendall tau not lower by more than 0.15, the 10th-90th percentile
   width of the 120-item noise ceiling); current-Skill pass rate in [0.25, 0.85] and mixed share >= 30%; question
   diversity (mean pairwise token Jaccard) not above the archive's by more than 0.05. Otherwise keep V_k.
4. **Archive.** Every accepted panel is kept; each Skill version is also scored on all archived panels (no-forgetting
   check, Dynabench's recommendation, Hall of Fame).
5. **Transfer entry.** Only the final sealed evaluation measures transfer (purpose 2). Rules with placement `similar`
   may use OfficeQA-style forward panels (v3 `forward.py`) as a no-harm screen, but only if the owner allows the
   one-time instrument check of 7.5; otherwise forward panels stay diagnostics (as v3 §12.8 already says).

### 7.3 The frozen ladder (what the verifier is calibrated against)
On SearchQA, format-scale arms with real effects known from cal-1 [measured]: parent:A (reference), ids-full (+0.0925 strict,
+0.0775 JSON-aware), control:3 (-0.100 strict, -0.0025 JSON-aware: a pure JSON-format effect), parent:B (same text,
+0.0075: the noise yardstick). These validate the verifier only as a format instrument. For OfficeQA the whole ladder must be built once (empty scaffold, task-card seeds, a JSON-inducing placebo, the
same-text duplicate, and a model contrast) on ~150 real training items x 2 runs. **Content-scale arm to add** (both):
the same parent Skill solved by a weaker and a stronger model (e.g. glm-4-flash or glm-5.3-flash vs deepseek-v4-flash),
whose real difference must be measured once on ~150 real training items x 2 runs (SearchQA about 0.6M tokens;
OfficeQA more, see 7.6) [estimate]; a model contrast changes knowledge/reading, not format, so a panel that reproduces it measures content.
The 10/15 OfficeQA history shows why this matters: generated items reproduced the format-scale contrast (bzero vs empty,
significant on generated and real alike in 6/6 model x bench cells) but not the learned-clause contrast (+13 vs 0)
[measured, ledger].

### 7.4 Stop rules
- **S1 Skill stagnation**: stop after 2 consecutive rounds with no Skill version accepted on fresh real batches.
- **S2 Verifier collapse (M1/M4)**: a verifier candidate with > 3/30 non-valid items, or any pass on an item audited
  wrong/ambiguous/unanswerable, is rejected; 2 consecutive rejections freeze the verifier for the rest of the run.
- **S3 Divergence (M3)**: stop the loop if, for 2 consecutive rounds, the accepted Skill's gain on the current
  generated panel exceeds its gain on the fresh real batch by more than 2 standard errors (the 10/15 pattern).
- **S4 Disengagement (M2)**: a verifier candidate whose current-Skill pass rate is outside [0.25, 0.85] or whose mixed
  share is < 30% is re-banded, not accepted (POET minimal criterion / R-Zero band analogue).
- **S5 Budget and horizon**: K = 4 rounds maximum (R-Zero peaks after 1-3 iterations [cited]); per-round and total
  token caps in the ledger (the pilot's ledger pattern).
- **Convergence** = S1 or S5 reached with the verifier frozen or accepted; the run then goes to the sealed final
  evaluation (step-0 Skill vs final Skill on the four target benchmarks, paired, D11 reporting).

### 7.5 Owner decision needed: may the verifier be calibrated on target TRAINING items?
Option A (strict "evolve on one"): no target data before the final evaluation; verifier fidelity is measured on the
source only; transfer is only the final number. Option B (declared instrument calibration): once, before the loop, the
frozen ladder is solved on ~150 real OfficeQA training items; each round only the target-style panel's aggregate
fidelity is computed against it (the Skill never sees target items, the verifier never sees item-level target
outcomes). B is the only way the verifier can show it "measures generalisation better" during the run (purpose 1's
wording), but it does use target-domain data and must be declared as such.

### 7.6 Cost [estimate from measured unit costs]
Unit costs measured in this pilot (ledger `out/e10p1/ledger.jsonl`): GLM-5.3 writer 1,584 tokens/call, reviewer 1,370,
auditor 1,644, reviser 6,670; deepseek-v4-flash solver cell 2,133 tokens on average over the three arms (parent:A and
control:3 ~1.2-1.4k, ids-full ~3.9k, matching cal-1's 1,683 / 1,287 / 4,168). Yield: ~1 kept item per writer call.

| Block (SearchQA source) | Calls / cells | Tokens |
|---|---|---|
| Verifier half per round: 120 items (120 writer + ~170 review calls) | ~290 GLM calls | ~0.42M |
| Ladder solving: 120 items x 4 arms (incl. the content-scale model arm) x 2 runs | 960 cells | ~2.0M |
| Audit 30 items + reviser | 31 GLM calls | ~0.06M |
| Skill half per round: train 200 x 2 + per-code diagnosis + analyst | ~400 cells + ~100 GLM calls | ~2.5M |
| Fresh-batch acceptance (D1): 150 items x 2 arms x 2 runs | 600 cells | ~1.8M |
| Archive no-forgetting check: each archived panel 120 x 1 run | 120 cells per panel | ~0.25M per panel |
| **Per round** | | **~7M** |
| One-time content-scale ladder arm on real SearchQA training items (150 x 2) | 300 cells | ~0.6M |
| One-time OfficeQA ladder on real OfficeQA training items (150 x 4 arms x 2), needed if OfficeQA is the source (and the same size for Option B on a target) | 1,200 cells | ~9.5M (7.9k/cell, below) |
| Final sealed evaluation (step-0 vs final Skill on four target test panels) | depends on panel sizes | ~5-10M (not measured here) |
| **Total, K = 4, SearchQA source** | | **~30-40M tokens** |
| **Total, K = 4, OfficeQA source (recommended)**: real-item cells cost 7.9k instead of ~2-4k, so ~12-17M per round, plus the ~9.5M ladder and the final evaluation | | **~65-90M tokens** |

OfficeQA cell cost [measured]: v3 run, chain I-ds, stage s2 (OfficeQA) training execution, 148 cells: deepseek charged
tokens mean 7,927, median 6,252, p90 13,818, max 38,647 (median request 21 KB); the same chain's SearchQA training
cells (s1, 400 cells): mean 4,088. Generated OfficeQA-style items (one Wikipedia table) should be cheaper than real
OfficeQA documents; not measured.

The v3 run (three chains, five stages, 139M tokens) is the comparison point: one source benchmark with K <= 4 rounds is
roughly a quarter (SearchQA) to two thirds (OfficeQA) of it. Wall-clock is dominated by the deepseek route: in this pilot it delivered 313 cells in ~15
minutes at concurrency 6 with stalls of 1-3 minutes (launch log), i.e. ~20 cells/min; 960 ladder cells take ~50 min.

## 8. Risks and unknowns

1. **The verifier may have nothing real to measure on SearchQA.** On v0's valid items the arms pass 0.96-1.00 (except
   the JSON placebo); the generated panel is essentially a format instrument. Content failures of real SearchQA items
   (answer absent from the snippets; 50.3% "dead" trigger items in v3) cannot be reproduced by items whose answer is
   verbatim in the snippets by construction. A verifier that "improves" on SearchQA may only become a better format
   checker -- exactly the non-transferable part.
2. **Fidelity on format-scale contrasts is cheap and can mislead.** B0 reproduced the cal-1 signs under both the
   strict and the JSON-aware scorer, but with alternative forms accepted every contrast is 0. The 10/15 OfficeQA
   history shows the opposite failure on a content-scale contrast (+13 generated vs 0 real). Without a content-scale
   ladder arm (7.3) the headline measurement can be passed for the wrong reason.
3. **Correlated judges.** Writer, reviewer, reviser and auditor are all GLM-5.3. My hand check agreed with the GLM
   audit on 12 of 13 B0 items (the Divina/Divine item is debatable), which is a small, single-checker sample. A
   second model family or a human sample is needed before the audit can gate anything.
4. **Small pilot denominators.** B0 has 30 items, F1/A1 18 each; all differences between policies are directional
   (section 6), not significant. 
5. **Exact-match scoring is a lever both players can pull.** The F reviser discovered on its own that variant answer
   forms make items "hard". Any difficulty-seeking verifier on an exact-match benchmark will find this; an alias /
   alternative-form check must be part of the verifier's code, and "alt_forms" must count as invalid.
6. **Transfer is unmeasurable during the run under Option A.** Then purpose 1's "the verifier measures generalisation
   better and better" can only be shown on the source side; the owner must choose 7.5.
7. **Route throughput.** The deepseek token route stalls for minutes at a time (this pilot; context §6), so a 4-round
   loop is a multi-hour run that needs resumable caches (the pilot's per-batch cache pattern works).

## 9. Recommendation

1. **Do not run a difficulty-seeking verifier loop** (zero-sum "make the Skill fail"). Literature and pilot agree that
   it drifts to invalid items within 1-3 rounds; in the pilot both policies drifted within ONE round, and the
   difficulty-only reviser discovered scorer exploitation on its own.
2. **Define the verifier's objective as measurement quality**: content-scale ladder fidelity at >= 120 items, subject
   to audited validity >= 90% and a difficulty band. Report it each round next to the real-item noise ceiling.
3. **Make the coding rubric code.** Convert every validity rule the reviser writes in prose into an executable check
   (an alias SET per item instead of one exact-match string, a two-referent detector, verbatim-key and determinism
   rules, AZR-style); keep a
   check only if it lowers the audited non-valid share. Use a second model family (or a 10-item human sample) for the
   audit; never use solver agreement as ground truth.
4. **Evolve on OfficeQA, evaluate on SearchQA, LiveMath, SpreadsheetBench (similar) and ALFWorld (dissimilar)**,
   after building an OfficeQA ladder once (5 arms incl. a model contrast, ~150 real training items x 2 runs). Use
   SearchQA and the existing cal-1 ladder to test the machinery cheaply first (the pilot scripts already do most of it).
5. **Accept Skill versions only on fresh real source batches (D1)**; generated items are training material and
   diagnostics; keep an archive of all accepted panels for no-forgetting checks; apply stop rules S1-S5 (7.4); K <= 4.
6. **Owner decision**: Option A vs Option B of 7.5 (may the verifier be calibrated once on target TRAINING items?).
7. **Next free/cheap steps** (each < 4M tokens): (i) the content-scale arm on SearchQA (model contrast, 300 cells);
   (ii) re-run e10p1's A-policy with the A2 validity list implemented as code checks, 120 items, to test whether
   code checks stop the drift; (iii) cost one OfficeQA cell and build the OfficeQA ladder (Option-independent: it uses
   source training items only).

## 10. References (read this session; local text copies under `.../feas/E10/lit/`)

- Huang et al., "R-Zero: Self-Evolving Reasoning LLM from Zero Data", arXiv 2508.05004 (ICLR 2026): uncertainty reward,
  3-7/10 filter, BLEU repetition penalty, Fig. 3 iteration collapse, Table 5 pseudo-label accuracy 79.0/69.0/63.0%,
  Table 6 single-model 63.4% vs 71.0%.
- Zhao et al., "Absolute Zero: Reinforced Self-play Reasoning with Zero Data", arXiv 2505.03335: learnability reward
  (Eq. 4), executor validation (syntax, forbidden modules Fig. 10, determinism j=2 Fig. 15), "uh-oh moment".
- Liu et al., "SPIRAL: Self-Play on Zero-Sum Games Incentivizes Reasoning...", arXiv 2506.24119 (ICLR 2026): RAE,
  thinking collapse (Fig. 6), fixed-opponent exploitation (Table 3).
- Li et al., "AutoBencher: Towards Declarative Benchmark Construction", arXiv 2407.08351 (ICLR 2025): salience,
  difficulty, separability, novelty; privileged information; 5% human-rated error rate.
- Fernando et al., "Promptbreeder: Self-Referential Self-Improvement via Prompt Evolution", 2023.
- Kiela et al., "Dynabench: Rethinking Benchmarking in NLP", NAACL 2021 (vMER; cyclical progress; keep old rounds).
- Bai et al., "Benchmarking Foundation Models with Language-Model-as-an-Examiner", NeurIPS 2023 D&B (peer-examination).
- Wang et al., "Paired Open-Ended Trailblazer (POET)", 2019 (minimal criterion 50 <= score <= 300; transfer).
- "Substitution of the Fittest: ... Mitigating Disengagement in Coevolutionary Genetic Algorithms" (disengagement;
  Hall of Fame, Rosin & Belew 1997; Watson & Pollack 2001).
- Project records: `docs/results-and-lessons.md` entries 10/15 10:00, 10/15 17:37, 10/16 12:37; `docs/project-status.md`
  §0 (10/15-16 findings); `skillopt/coevo5/forward.py` header; context.md §3 (v3 facts).

## 11. Artifacts

New machine `/data/feasibility/E10/`:
- `scripts/e10_pilot_v2.py` (the pilot; launcher `scripts/launch.sh`), `scripts/e10_analyse.py`, `scripts/json_aware.py`,
  `scripts/fail_types.py`, `scripts/early_audit.py` (launchers `launch_early_audit.sh`, `launch_early_audit_r2.sh`),
  `scripts/ladder_power.py`, `scripts/cal1_ladder.py`. Re-run: `python3 -I scripts/e10_analyse.py out/e10p1 OUT.json`;
  `python3 -I scripts/json_aware.py out/e10p1 B0 F1 A1 F2 A2`; `python3 -I scripts/fail_types.py out/e10p1 B0 F1 A1 F2 A2`.
- `out/e10p1/` (prereg.json, launch-notes.json, ledger.jsonl, and per batch B0/F1/A1/F2/A2: items.json,
  generation_log.json, guidance.json, cells.jsonl, audit.json, audit_early.json; status.json), `out/e10p1_analysis_final.json`,
  `out/e10p1_jsonaware.json`, `out/e10p1_failtypes.json`, `out/ladder_power.json`, `out/cal1_ladder.json`.
- Logs: `logs/e10p1.log`, `logs/e10p1-launch1.log`, `logs/e10p1-launch2.log`, `logs/early_audit.log`,
  `logs/early_audit_r2.log`, `logs/smoke.log`. Token use: pilot ledger 1,845,075 (GLM 539,873, deepseek 1,305,202),
  early audits 121,482, smoke 2,617: ~1.97M in total (in-flight calls lost at the two restarts are not counted).
Mac scratchpad `.../feas/E10/`: this report, `scripts/` (copies), `lit/` (papers and text), `results/`.
