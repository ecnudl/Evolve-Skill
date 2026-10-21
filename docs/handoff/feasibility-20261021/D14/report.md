# D14 -- ALFWorld and SpreadsheetBench under the text-skill paradigm

Explorer D14, 2026-10-21 (Asia/Shanghai). Machine: datatools (`/data/feasibility/D14/`, read-only on the v3 run and on the
repository copy). Training pools only: no file under any test/holdout/evaluation path was opened. Labels used below:
**measured** (computed by me from files or from my pilot runs), **estimated** (a computation on measured numbers under a
stated assumption), **claim** (reported by a paper or by another explorer, not re-measured by me).

[[BOTTOM_LINE]]

## 1. What I did

1. Read the v3 coevo5 records of stage 4 (SpreadsheetBench) and stage 5 (ALFWorld) for both chains (E-ds = empty
   scaffold, I-ds = five task cards): train cells and artifacts (ALFWorld traces), examiner diagnoses, analyst proposals,
   prepare/selftest/screen/confirm/merge decisions (`/data/coevo5-20261019-v3-run/{E-ds,I-ds}/{s4,s5}/*/unit.json`, cells,
   artifacts, `prepare/attempt-1/diagnoses.json`). Also the v1 GLM-5.3 run (`/data/coevo5-20261017-run`) for a stronger
   solver on the same harness.
2. Re-derived failure anatomy from the traces (receptacle coverage, revisits, close/"Nothing happens" shares, failure
   stage, step-hazard of wins, object location from the game walkthrough metadata of the TRAINING games).
3. Read the frozen solver loops (`skillopt/continual_eval/backends.py` in `/data/coevo5-20261019-v3-source-f`): ALFWorld
   one action per call with a 5-step history window; SpreadsheetBench one program, executed once, no feedback.
4. Literature: ExpeL, Reflexion, AutoGuide, AWM, ReAct, StateAct, AutoManual, AdaPlanner; SpreadsheetBench, SheetCopilot;
   two 2026 arXiv claims (MindMemOS, SkillBoost). PDFs of ExpeL and Reflexion were read in full text.
5. Pilots (paid, deepseek-v4-flash + GLM-5.3, all on training pools, frozen v3 code paths unless stated):
   P1 (one targeted ALFWorld text rule, frozen loop, with a same-day no-rule control), P3/P3b (the same rule with a
   one-sentence format guard; the rule in a canonicalising loop; format-guard-only; canonicalised no-rule control),
   P2 (SpreadsheetBench: item-specific hint ceiling) and P2x (placebo: another item's hint).

## 2. The frozen setting (what any text rule must work through)

* **ALFWorld** (`_solve_alfworld`): system prompt "Act in the text environment. Return a single action inside
  <action>...</action>." + the Skill; per step the solver sees `{initial_observation, observation, admissible_commands,
  recent_history}` with `recent_history` = the last **5** (observation, action) pairs; the action is the text inside the
  first `<action>` tag, **else the whole reply verbatim** (no validation against `admissible_commands`); 50 steps; the
  Skill is re-sent on every step. deepseek-v4-flash with thinking disabled, temperature 0. Measured on the v3 traces: the
  solver writes 12.9-13.6 completion tokens per action (no reasoning text).
* **SpreadsheetBench**: one call, view = instruction + preview of the first input workbook (first 5 rows x 20 columns per
  sheet) + paths + answer position; one Python program, executed once per case in docker, scored by the qualified v7
  recalculation scorer; the solver never sees an execution result.

## 3. v3 stage-4/5 records (measured)

### 3.1 The proposal funnel (both chains, stages 4 and 5)

| unit | proposed | evidence_invalid | insufficient | supported | selftest pass | screen pass | confirm pass |
|---|---|---|---|---|---|---|---|
| E-ds s4 (Sheet) | 5 | 1 | 1 | 3 | 1 (r4, after revision, 1 vs 0) | 0 | - |
| E-ds s5 (ALF) | 5 | 2 | 0 | 3 | 0 | - | - |
| I-ds s4 (Sheet) | 5 | 1 | 2 | 2 | 1 (r2, 1 vs 0) | 1 (r2) | 0 |
| I-ds s5 (ALF) | 5 | 0 | 1 | 4 | 1 (r1, 1 vs 0) | 0 | - |
| total | 20 | 4 | 4 | 12 | 3 | 1 | 0 |

Selftest counts are items solved on the rule's own evidence items, rule vs parent: all 12 decisions rested on 0-3
solved items, and the three passes were 1-vs-0 differences (e.g. fails: E-ds s5-r1 2 vs 3, I-ds s5-r2 revised 0 vs 1).
Screen/confirm: C1 gain and margin as recorded by the gate; in brackets my recount of solved trigger items (mean of 2
runs, unknown cells counted as unsolved) for rule / parent / the four placebo controls:

* E-ds s4-r4 (per-row formulas), screen: gain +1/2, margin -1 [5.0 / 4.5 / 4.0, 6.0, 5.5, 5.0] -> fail.
* I-ds s4-r2 (normalised key matching), screen: gain +1, margin +1/2 [3.5 / 2.5 / 2.5 each] -> pass; confirm: gain
  +1/2, margin -3/2 [2.0 / 1.5 / 3.0, 2.5, 3.0, 2.5] -> fail: the placebo controls beat the rule.
* I-ds s5-r1 ("mental checklist, visit each receptacle once"), screen: gain -2, margin -7/2, C2 delta -5
  [0.0 / 2.0 / 1.0, 3.5, 2.5, 1.0] -> fail: the rule solved none of its 14 trigger items.
* Trigger sets: 15, 15, 15, 14 items; items with no pass under any arm: 6/15, 6/15, 7/15, 10/14.

Nothing was accepted on either benchmark in either chain.

### 3.2 ALFWorld failure anatomy (57 training games x 2 runs per chain)

* Wins: E-ds 46/114 (40.4%), I-ds 58/114 (50.9%). Per item, I-ds minus E-ds = +0.105 [95% bootstrap CI +0.026,
  +0.184], 12 items better / 3 worse, sign test p = 0.035: the hand-written task card is the only text that measurably
  moved ALFWorld in v3. Run-to-run disagreement of the same text: 8/57 items per chain.
* Every failure is a 50-step timeout (68/68 E-ds, 56/56 I-ds). Diagnoses: D3 "search loop" 43/68 (E-ds), 45/56 (I-ds).
* Failure stage: the target object was **never seen** in 49/68 (E-ds) and 46/56 (I-ds) failed episodes. Failed episodes
  visit on average 6.0 of 26.1 (E-ds) / 6.3 of 25.9 (I-ds) receptacles; 0 failed episodes cover all receptacles; 59/68
  and 47/56 cover fewer than half. Revisits are 44.7% / 51.3% of failed-episode steps, 60-62% of them within 5 steps
  (inside the visible history window); `close` is 12% of failed steps; "Nothing happens" 10-13%.
* Where the object is: by the walkthrough metadata of the training games, the object lies on an **open surface** in
  55/57 games (2 in closable containers); failing agents reached that location in only 16/68 (E-ds) and 10/56 (I-ds)
  episodes. In the won v3 episodes (public trajectories), the first object was taken from an open surface in 31/46
  (E-ds) and 37/58 (I-ds), from the fridge in 10/46 and 12/58.
* Wins are short: median 10.5 (E-ds) / 9 (I-ds) steps; only 1/46 and 4/58 wins needed >= 40 steps. The expert
  walkthrough needs 5.9 steps on average (max 9). Win hazard per 10-step block: E-ds 20.2/18.7/6.8/0.0/1.4%, I-ds
  32.5/16.9/3.1/3.2/6.7%; unsolved at step 50: 59.6% / 49.1%. **Estimated** (the late per-block hazard -- last block,
  mean of the last 2 or 3 blocks -- held constant for 50 more steps): doubling the budget to 100 steps would add +2 to
  +8 points for E-ds and +10 to +14 points for I-ds, at roughly double the cost of every failing episode. The late
  hazards rest on 0-2 wins per block, so these are rough; more steps are a secondary lever.
* Worst type: cool (2/18 E-ds, 4/18 I-ds wins); cool failures anchor on the fridge and the destination.
* Cost: E-ds 807 prompt tokens per step (28.5k per episode, 3.24M per 114 episodes); I-ds 3,364 per step (105.7k per
  episode, 12.04M per 114): the Skill is re-sent on every step, so every 1k characters of ALFWorld guidance costs about
  250 tokens x ~35 steps per episode.
* Stronger solver, same harness (v1 run, GLM-5.3 with reasoning): E-glm 102/114 (89.5%), I-glm 101/114; 4 items failed
  all runs in each chain. The harness is solvable; the weak, non-reasoning solver is the bottleneck.

### 3.3 SpreadsheetBench failure anatomy (91 qualified training items x 1 run per chain)

* E-ds 46 pass / 44 fail / 1 unknown; I-ds 47 / 43 / 1. Task card effect: I-ds minus E-ds pooled over parent-like runs
  -0.002 [-0.052, +0.048] (23 vs 16 discordant, p = 0.34); train-only paired 10 vs 9 (p = 1.0): **no effect**.
* Failures are wrong values, not crashes: value mismatch 37/44 (E-ds) and 35/43 (I-ds); program errors 4; truncation 2/1;
  no code 1/2. Diagnoses: D4 "wrong logic" 27/44 and 25/43.
* Items dead under every parent-like run: 32 (E-ds, 3.45 runs per item), 23 (I-ds, 5.9 runs per item); same-text flips
  13/89 (E-ds), 19/89 (I-ds).
* Workbooks wider than the 20-column preview (n = 12): pass rate 0.30 (E-ds) / 0.41 (I-ds) vs 0.545 / 0.537 overall;
  row count is not predictive.
* Stronger solver (v1, GLM-5.3): E-glm 45/90, I-glm 65/91 (paired 23 vs 4, p = 0.0003; partly a v1 layout effect:
  delivery/crash failures 16 -> 4).

### 3.4 What the proposals tried, and why they died

* **ALFWorld** (10 proposals). Search discipline that needs memory: "list every receptacle, visit each exactly once, never
  revisit" (E-ds r1, I-ds r1), "never revisit / never re-open / never close" (I-ds r5), "after Nothing happens never
  repeat" (E-ds r2, I-ds r2), exact object type (E-ds r3, I-ds r4), transformation recipe (E-ds r4), "once held go to the
  appliance" (E-ds r5), `move` vs `put` phrasing (I-ds r3). Two proposals already asked for plain admissible commands
  without an `action:` prefix or copied verbatim from `admissible_commands` (E-ds r2: evidence_invalid on code
  bookkeeping; the E-ds r1 revision: selftest 2 vs 3; the I-ds r2 revision: selftest 0 vs 1).
  None used the distributional fact of 3.2 (objects lie on open surfaces; search them first, do not cycle containers).
  The memory-dependent rules cannot be executed by a solver that sees 5 steps of history and writes ~13 tokens per action;
  the one that reached the screen solved 0 of its 14 trigger items.
* **SpreadsheetBench** (10 proposals): generic coding hygiene -- map the workbook first, treat example sheets as ground
  truth, follow stated ordering, per-row formulas, normalised key matching, `data_only` loading, write every answer cell.
  The failures they target are item-specific logic errors (D4), which a generic sentence does not fix (see P2/P2x).
* The gate did not kill a good rule: no proposal showed an effect larger than the placebo controls. Its power is low,
  though: 14-15 trigger items with 40-71% dead items leave 4-9 informative items, and in three of the four gate rounds
  the best of the four placebo controls beat the parent by +1.5 items (tied in the fourth) -- measured -- so a rule
  needs a gain of roughly +2 items or more (estimated) to pass C1.

## 4. Literature: what learned text guidance achieves

| work | setting (as reported) | result | relevance to us |
|---|---|---|---|
| ReAct (Yao et al., ICLR 2023) | PaLM-540B, 134 unseen ALFWorld games, 2 exemplars per task type | Act 45, ReAct 57 (best of 6 prompts 71), BUTLER 37 | exemplar trajectories + reasoning, not learned rules |
| Reflexion (Shinn et al., NeurIPS 2023) | text-davinci-003, 134 games, memory = last 3 reflections **of the same game** across trials | 130/134 after 12 trials (+22 points absolute) | retry memory on the same item: answer repair, not transfer to new items |
| ExpeL (Zhao et al., AAAI 2024) | agent gpt-3.5-turbo-0613, insights by gpt-4-0613, 134 games, four-fold | ReAct 40.0 +- 0.3 -> ExpeL 59.0 +- 0.3; retrieve-only 54.5; insights-only about 49 (my weighting of their per-type Table 5; the same weighting gives 36 for ReAct vs its reported 40.0, so the table and headline are not fully consistent); with Reflexion R3 64.2 | text insights alone give roughly +9 points; trajectory retrieval gives more; the paper itself says ALFWorld "is better derived from past experiential trajectories" |
| AutoGuide (Fu et al., NeurIPS 2024) | gpt-3.5-turbo agent, guidelines by gpt-4-1106-preview from 100 training tasks, 50 steps, top-2 context-conditioned guidelines | ReAct 54.5, ExpeL 59.0, AutoGuide 79.1 (+Reflexion 67.2 / 71.6 / 88.1) | state-conditioned text guidelines retrieved per step: the strongest evidence that text can move ALFWorld |
| AWM (Wang et al., 2024) | Mind2Web, WebArena | +24.6% / +51.1% relative | no ALFWorld or spreadsheet result |
| StateAct (2024) | ALFWorld | > 10 points over ReAct (abstract) | explicit state tracking in text |
| AutoManual (Chen et al., NeurIPS 2024) | ALFWorld, 1 demonstration | 97.4% GPT-4-turbo, 86.2% GPT-3.5-turbo | rules + coded plans (executable), interactive rule building |
| AdaPlanner (Sun et al., NeurIPS 2023) | ALFWorld | +3.73 points over prior best | code-style plans, refined from feedback |
| SpreadsheetBench (Ma et al., NeurIPS 2024 D&B) | 912 instructions, 2,729 cases | GPT-4o soft 18.35 single-round, 16.96 multi-round (ReAct + execution feedback, <= 5 rounds); GPT-3.5 2.34 -> 7.09; human 71.33; Copilot in Excel 20.00, SheetCopilot 14.00 (5% sample) | execution feedback is not automatically a gain for a strong model |
| SheetCopilot (Li et al., NeurIPS 2023) | 221 tasks, atomic actions | GPT-3.5 pass@1 44.3 (exec@1 87.3); GPT-4 55.0 on a 10% subset; external API documentation +10.0 pass@1 | documentation (generic text) helps when it fills a knowledge gap |
| MindMemOS (arXiv 2608.12428, **claim**) | SpreadsheetBench 400 verified, 3 runs, online stream, base model not stated | no skill 51.3 +- 0.8, initial skill 48.0 +- 1.4, evolved 55.3 +- 0.9 / 57.2 +- 2.4 | +4 to +6 points for evolved skills; a hand-made initial skill hurt |
| SkillBoost (arXiv 2607.26643, **claim**) | DeepSeek-v4-pro, thinking disabled; ALFWorld 50 steps, 2-step history; Sheet up to 6 code turns | Sheet 49.6 (none) / 70.4 (human skill) / 70.0 (LLM skill) / 80.0 (theirs); ALFWorld 55.2 / 54.5 / 57.1 / 64.3 | split sizes and runs not stated; multi-turn Sheet loop differs from our single shot |

Reading: published gains on ALFWorld come from (a) exemplar or retrieved trajectories, (b) per-step, state-conditioned
guidelines, (c) same-item retries, or (d) executable plans. A single static rule list in a non-reasoning solver's
system prompt is the weakest of these designs, yet still has room when the rule encodes a regularity the solver lacks
(see P1/P3). On spreadsheets, published gains come from multi-turn execution loops and documentation; nobody reports a
large gain for static text in a single-shot program writer.

## 5. Pilots (measured; training pools only)

### 5.1 ALFWorld: one targeted text rule (P1, P3, P3b)

**Why this rule.** Section 3.2 says the failures are not a memory problem that a sentence can fix ("never revisit"),
but a search-order problem: the object is on an open surface in 55/57 games, while failing agents cycle drawers and
cabinets, open/close them and anchor on the task's appliance before holding anything. A memoryless policy can follow
a rule that is conditioned on the current state ("not holding the object yet" vs "holding it"). I wrote one such rule
(generic, no item names):

> **R1** (575 characters): "When you do not yet hold the object the task names: never use 'close' and do not visit the
> fridge, microwave or sinkbasin; go to the open surfaces of the room description in the listed order (countertop,
> diningtable, desk, sidetable, coffeetable, dresser, shelf, bed, sofa, armchair, stoveburner, garbagecan, toilet): on
> arrival you see all objects on them. Open drawers and cabinets only after those. When you hold it: go to the
> appliance the task needs (cool: fridge, heat: microwave, clean: sinkbasin, look: desklamp), use it, then go to the
> destination and move it there."

> **R2** (590 characters, within the v3 600-character rule limit) = a leading format sentence + R1 shortened: "Reply
> exactly <action>COMMAND</action>, COMMAND verbatim from admissible_commands; never write 'action:'. Until you hold
> the task's object: never close, skip fridge, microwave and sinkbasin, and go to the open surfaces in the room's
> listed order (...same list...); arriving shows all objects on them. Open drawers and cabinets later. Once held: use
> the needed appliance (...same map...), then go to the destination and move it there."

> **F** (105 characters): the format sentence of R2 alone.

**Caveat on R1/R2: in-sample.** I wrote them after reading aggregate statistics of these same 57 training games,
including the walkthrough object locations (training metadata, never shown to the solver). The pilot therefore measures
an upper bound of what one rule of this kind can do, not the effect of a rule learned by the method, and nothing about
the 134 test games (not touched).

**Arms** (each rule added to the ALFWorld section of the E-ds parent Skill, sha256 cc516459...; Skill hashes: R1
ab9bb0ad35fc..., R2 f347c4cbfec5..., F 22d8287a536c...):

* *Frozen loop* = `backends.solve` -> `_solve_alfworld` from the v3 frozen source with the v3 runtime (50 steps, seed 42,
  split train, deepseek-v4-flash, max_tokens 32768, the same client class, route and temperature 0 as v3).
  V = the v3 E-ds s5 training cells (no rule, 2 runs per item, 2026-10-20 05:00-06:36); C = no rule, today;
  T = R1; F = format sentence only; T2 = R2.
* *Canonicalising loop* = the D3 r2 "design B" loop (same system prompt, view, 5-step window and 50 steps, plus
  max_tokens 512 and a reply canonicaliser: strip an `action:`-style wrapper, map case-insensitively to an admissible
  command, else take the earliest admissible command named in the reply). D3C = D3 r2 arm C (no rule, 2026-10-21
  00:33-03:18, read from D3's files); K0 = the same loop, no rule, today, on the two of my items D3C lacks; KC = D3C
  where it exists, else K0; K = R1.
* Items: the 57 training games shuffled with `Random(20261021)`; all arms are compared on the **first 12** of that order
  (one run per arm and item; the arms were stopped there to stay within budget). Same-item comparisons below; sign test
  on discordant items, bootstrap CI over items.

[[ALF_TABLE]]

[[ALF_FINDINGS]]

### 5.2 SpreadsheetBench: how much can text fix? (P2, P2x)

**Design.** Population: the 44 failed E-ds s4 training cells (qualified items, parent = empty scaffold, 1 run each).
For each item GLM-5.3 (reasoning) wrote one hint of at most 550 characters from what the v3 diagnosis sees: the task
view, the failed program and the grader comparison (expected / written / recalculated answer cells), with the
requirement to describe the method and include no expected value (mechanical leak check against the expected values,
values present in the public task text exempt, one re-ask). deepseek-v4-flash then solved the item through the frozen v3
path (one program, docker execution, qualified v7 recalculation scorer):
H = parent + the item's own hint as a SpreadsheetBench rule; S = the parent alone (a fresh re-solve: how often a v3
failure passes on a second sample); X (P2x, placebo) = parent + the hint written for a *different* item (the item
n/2 positions later in the sorted list of hinted items). H is **answer repair** by text -- an item-specific ceiling,
not a Skill; X asks whether a hint-shaped rule helps an item it was not written for.

[[SHEET_TABLE]]

[[SHEET_FINDINGS]]


## 6. Conclusion: can text rules move these two benchmarks in our setting?

**ALFWorld: yes, in principle -- but not with what v3 proposed, and not through today's unguarded loop.**
[[ALF_CONCLUSION]]

**SpreadsheetBench: not with generic text in the single-shot harness.**
[[SHEET_CONCLUSION]]

## 7. What would have to change (ranked by expected value per cost)

ALFWorld (keep it in the text-skill programme, but change the protocol -- as a new version, never retro-fitted to v3):

1. **Guard the action interface** in the frozen loop for every arm: validate the reply against `admissible_commands`
   and canonicalise wrappers such as `action: ...` (the D3 r2 canonicaliser, about 30 lines), or at least put the format
   sentence into the frozen base prompt. Today's provider behaviour makes the unguarded loop lose most episodes for
   reasons unrelated to any Skill (section 5.1). Cost: none per call. Without it, every new ALFWorld comparison against
   v3 records is confounded.
2. **Give the proposer cross-episode statistics, not just single trajectories.** v3 showed the analyst at most 40
   failures (last 30 steps each, 300 characters per step) and 4 successes. The decisive regularity -- where objects are
   found in won episodes (open surfaces 31/46 and 37/58 of first pick-ups in v3) versus what failing episodes visit
   (closed containers, open/close cycles, the appliance before the object) -- is an aggregate over many episodes. A
   deterministic summary table of the training half (receptacle types visited/never visited, where objects were taken,
   close/revisit shares) costs nothing to compute and is public-trajectory information.
3. **Ask for state-conditioned rules** ("while not holding X: ...; once holding X: ...") and forbid rules that need
   memory beyond the 5-step window ("never revisit", "keep a checklist"): the solver writes about 13 tokens per action
   and cannot execute them (the v3 checklist rule solved 0/14 of its triggers).
4. **Test ALFWorld rules on all training games** (the search failure is universal: D3 was the code of 43/68 and 45/56
   failures), with 2 runs per arm; the present 14-15-item trigger sets would also pass a rule of the size seen here, but
   all 57 games give a reliable estimate at modest cost (section 9).
5. Executable state (D3's tracker field: **claim** from D3 r2, 28/42 vs 16/42 in the canonicalising loop) is
   stronger and complementary, but leaves the text-only paradigm; trajectory retrieval (ExpeL, AutoGuide) is the
   published route between the two.
6. More steps per episode: estimated +2 to +14 points at double cost for failing episodes (section 3.2) -- last.

SpreadsheetBench (do not invest further in static generic rules for this solver and harness):

1. Keep it in the chain as a no-drop control; report its result as "no generic text effect", not as a failure of the
   gate.
2. If the owner wants it to move, the change must bring item-specific information to the solver at solve time:
   an execution/verification loop (SpreadsheetBench's own multi-round setting; D3 r2 **claim**: one repair round with
   execution feedback 14/48 vs 11/48 for a plain re-solve, 8 vs 5 discordant -- small), retrieval of notes from
   similar solved items (D2's case memory), a wider workbook view (items wider than the 20-column preview pass 0.30-0.41
   vs 0.54 overall), or a stronger solver (GLM-5.3 on the v1 harness: 65/91 with the card).

## 8. Risks and caveats

* **In-sample rules.** R1/R2 were written by me from aggregate statistics of the same 57 training games (including
  walkthrough metadata the solver never sees). The pilot is an upper-bound probe of "one rule of this kind", not an
  estimate of what the method would learn, and says nothing yet about the 134 test games.
* **Small n, one run per arm.** 12 items per arm; v3 shows 8/57 items per chain disagreeing between two runs of the
  same text, so single differences are noise; only the large, same-direction contrasts are interpreted.
* **Provider drift.** A same-day no-rule control (C) is the only valid comparison for frozen-loop arms; comparing any
  new run with the v3 records (V) mixes the rule with the drift. Whether the drift persists, or depends on time of day
  or load, is unknown.
* **K differs from the frozen protocol** in two ways (canonicaliser and max_tokens 512); its control D3C was run
  2-5 hours earlier by another explorer; K0 covers only 2 items.
* **SpreadsheetBench hints saw the reference.** The leak check catches only literal expected values; the hints carry the
  item's logic (24 of the first 26 name concrete cells or columns). H is answer repair, never evidence of a Skill.
* **Stopped processes.** To keep the budget I stopped arms after the first 12 items; the tokens of episodes in flight
  at a stop are partly unlogged (bounded below).

## 9. Costs

* **This explorer's pilots** (measured from the episode/job files and process logs): [[SPEND]]
* **Per-unit costs** (measured): an ALFWorld episode with the E-ds parent costs about 30-45k deepseek tokens today
  when it fails (all 50 steps) and 14-18k with R1/R2 (episodes end after a median of about 7-9 steps); v3 measured
  28.5k (E-ds) and 105.7k (I-ds, longer Skill) per episode. A SpreadsheetBench solve costs about 1-2k tokens; a GLM-5.3
  hint about 1.5k.
* **A proper ALFWorld follow-up** (estimated): protocol v4 with the action guard, the aggregate-statistics view for the
  analyst and state-conditioned rule templates; one rule vs parent vs two placebos on all 57 training games x 2 runs =
  456 episodes x about 25k = about 11M deepseek tokens (about 4 h at 6 concurrent episodes, 3 min each), plus about
  0.1M GLM tokens for proposals. Any reading of the 134 test games (about 268 episodes, about 7M tokens for rule vs
  parent, one run) belongs to the main session's test discipline, not to an explorer.
* **SpreadsheetBench**: no paid follow-up recommended under the text-only paradigm.


## 10. Files

On the Mac (copied from the remote machine):
`/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D14/`
* `report.md` -- this report.
* `scripts/` -- every script I ran (analysis `a_units.py` ... `g_stats.py`, `h_pilot_alf.py`, `j_pilot_all.py`,
  `k_pilot_sheet.py`, `m_tables.py`; pilots `p1_alf_rule.py`, `p3_alf_variants.py`, `p3b_alf_variants.py`,
  `p2_sheet_hint.py`, `p2x_sheet_cross.py`; helpers `stop_at12.sh`, `after_p2.sh`, `wait_*.sh`, `fetch.sh`).
* `out/` -- analysis outputs: `units_s45.json` (stage-4/5 funnel), `alf_rows.json` (per-episode v3 ALFWorld metrics),
  `alf_locations.json`, `items_s45.json`, `sheet_size_rows.json`, `pilot_all_rows.json`,
  `pilot_all_summary_first12.json`, `pilot_sheet_summary.json`, `pilot_sheet_x_summary.json`.
* `pilots/` -- raw pilot outputs: `pilot-alf/` (P1: episodes, run.log, skills.json, stop.log), `pilot-alf-v/` (P3/P3b),
  `pilot-alf-smoke/`, `pilot-sheet/` (P2 jobs with hints, programs and verdicts), `pilot-sheet-smoke/`, `pilot-sheet-x/`
  (P2x).
* `lit/` -- ExpeL and Reflexion PDFs with text extractions.

On the remote machine: the same under `/data/feasibility/D14/` (scorer artifacts only there, under `*/host_only/`).


