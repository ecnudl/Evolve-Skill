# Codex 讨论（第 1 轮，2026-10-19 01:12–01:16）：运行中的过程分析与优化方向

> 负责人 10/19 凌晨要求"认真总结并分析数据、提出优化方向，可以和 Codex 讨论"。这是一次讨论，不是代码审查；Codex 只读仓库（read-only），没有接触开发机上的任何运行记录或测试结果。命令：`codex exec -m gpt-6-astra -c model_reasoning_effort='"ultra"' --sandbox read-only`。整理后的分析见 [coevo5-midrun-analysis-20261019.md](coevo5-midrun-analysis-20261019.md)。

## 发给 Codex 的问题（原文）

# Discussion request (not a code review): mid-run analysis of the five-bench coevolution run

You are a second researcher. The owner is asleep for ~8 hours and asked me (Claude) to analyze the running experiment
carefully, propose optimization directions, and discuss them with you. Please think hard, check my claims against
the code in this repo (read-only), and push back where I am wrong. Reply in English, structured as asked at the end.

### Context you can read in the repo
- Registration (the frozen protocol): `docs/handoff/coevo5-registration-v6-20261017.md` (Chinese). Key sections: §0
  (sealing: a chain's test scores are not aggregated or viewed until that chain completes; monitoring reports only
  counts/unknowns; test results never flow back into any method decision), §1 (chains), §2 (data), §4 (step flow),
  §5 (gate X v2: screen, confirm, composite; C1 trigger gain vs parent and 4 placebo texts; C2/C3 no-harm; C4'
  similar targets), §6 (examiner rubric, judging, revision), §7 (research = "DeepResearch", narrowed in v6), §8
  forward questions, §9 leak check, §10 evaluation, §11 baselines, §12 readouts, §13 budget/stop rules, §13.5 slots.
- Code: `skillopt/coevo5/` (examiner.py `_edits`, leakage.py `mechanical`/`Corpus`, analyst.py, research.py,
  step.py, gate.py, calls.py `Slots.hold`/`hold_many`, baseline.py `_held`, protocol.py constants).
- Owner's research goal (10/17): learning bench k should improve bench k AND similar benches (map in §1.1:
  SearchQA–OfficeQA, OfficeQA–LiveMath, OfficeQA–SpreadsheetBench; ALFWorld similar to none), without dropping
  dissimilar benches; no validation set; DeepResearch should only turn training results into better rules/tasks.
  Prior project finding (10/12): experience-learning gain over a reasonable initial instruction has not been
  established anywhere so far.

The run is frozen: nothing in it may be changed. Proposals are for a NEXT protocol version (new version, new dirs),
and must be designable from training-side/process data only (never from test scores, which are sealed and which I
have NOT looked at).

### Run status (process data only; collected 2026-10-19 01:00-01:15 CST)
- Launched 10/18 12:38 (E-glm) and 12:54 (SkillOpt-glm, GEPA-glm, I-glm). E-ds / I-ds not launched: the free
  deepseek router answers HTTP 403 insufficient quota (probed 01:04; a background probe now retries every 20 min).
- Ledger (GLM-5.3 tokens settled): overall 108.8M of cap 1,438.0M (7.6%), 3.3M open. Per chain: E-glm 12.5M (cap
  480M), I-glm 44.3M (745M), SkillOpt-glm 35.9M (715M), GEPA-glm 16.2M (715M). Per step: shared stage-0 evaluation
  3.50M; E s1 learning 6.04M (cap 60M; §13.1 "expected" 14M), E s1 evaluation 2.97M; I s0 evaluation 12.05M; I s1/s2/s3
  learning 10.59M / 9.14M / 12.50M+; SkillOpt s1 learn 8.43M + eval 8.40M, s2 learn 2.68M, s3 learn 11.13M + eval
  5.22M (running); GEPA s1 learn 2.66M + eval 6.95M, s2-s5 learn 0.72/2.84/0.54/2.46M, evals reused.
- GEPA-glm COMPLETE at 01:01. Its learner returned `selected_update` at s1 (SearchQA, skill 4,325 bytes) and
  `completed_no_update` at s2-s5 (so s2-s5 evaluations were byte-identical reuse). Each GEPA step used only 3
  reflection calls; solver calls 1431 / 98 / 824 / 192 / 1339.
- SkillOpt-glm: s1 `selected_update` (1 accepted step, net wins +37 of 200 val positions; then the 128 reflection-call
  cap: `accepted_prefix_kept_after_stop:native_reflection_incomplete`); s2 OfficeQA `pending_carry_parent`
  (`native_reflection_incomplete`: a reflection prompt exceeded the frozen ledger's 240,000-byte prompt cap
  ("Invalid or oversized prompt"), after which every optimizer call raised LearningPending; registered handling as in
  study F); s3 LiveMath `selected_update` (1 accepted step; skill 15,177 bytes); now evaluating s3 (ALFWorld unit).
- I-glm: s1 SearchQA and s2 OfficeQA accepted no rule (evaluations reused); s3 LiveMath screen passed 2 of 4 rules,
  confirm running since 00:26.
- E-glm: s1 accepted 2 rules; s1 evaluation: four benches done by 20:18, the ALFWorld unit (134 episodes) open since
  ~19:20, ~98 cell files by 01:06. (Stage-0 ALFWorld evaluation took 52 min.)
- Unit wall-clock (min): stage-0 eval units 24-52. E s1: train 27, prepare 54, screen 30, confirm 47, composite 131,
  eval 86-99 (+ALFWorld >340). I s1: train 18, prepare 19, screen 74. I s2: train 12, prepare 8, screen 143. I s3:
  train 27, prepare 78, screen 258, confirm >45. SkillOpt learn s1 45, s2 27, s3 338. GEPA learn s1 52, s2 256
  (mostly waiting for the hold_many gate), s3 86, s4 30, s5 54.
- Slots (protocol.py SLOTS: glm-5.3 10, deepseek 12, spreadsheet-native 3, alfworld-episode 6): a baseline learning
  unit holds `hold_many(8)` of the 10 GLM slots for the whole unit (and ALL native slots of its bench for
  SpreadsheetBench/ALFWorld), one such holder at a time, and while it gathers, single holders take no new slot. By my
  count baseline learning held 8/10 GLM slots for ~9.5 of the first 12 hours, so E-glm, I-glm and the baselines'
  evaluations shared 2 slots most of the time. Upcoming: SkillOpt s4 (SpreadsheetBench, all 3 native slots) and s5
  (ALFWorld, all 6 episode slots) will block every other chain's SpreadsheetBench / ALFWorld cells while they run.
- Evaluation unknowns (counts only): SpreadsheetBench 4-10 of 204 cells "9c:artifact:candidate_unjudged" per
  evaluation; all other benches 0. Gate unknowns: SearchQA parent 6-8 cells per round (2 training items are always
  refused with HTTP 400, as in the smoke).

### Training-side learning data (E-glm s1; I-glm s1-s3)
- Training execution (training items, 2 samples each; pass/fail/unknown cells): E s1 SearchQA 259/134/7 of 400;
  I s1 SearchQA 311/81/8; I s2 OfficeQA 89/59/0 of 148; I s3 LiveMath 83/117/0 of 200.
- Examiner revision (§6): E s1 accepted (selection-panel balanced accuracy 11/20 -> 7/10, correct 22 -> 28).
  I s1, s2, s3: `invalid_reply`, reason `invalid:text` each time: one proposed item text exceeded the 300-character
  limit (prompt says "at most 300 characters"), and `_edits` rejects the WHOLE reply (registered: one call, no retry,
  "不修订"). The I s1 reply was otherwise sensible (edit R7 to accept leading articles; add a minimal-canonical-name
  item; add a "specific entity, not a category" item).
- Other method roles: judge 1104/1105 valid (1 HTTP 400); diagnose 335/335; analyst 4/4 valid first try;
  leak_adjudicate 16/16 valid (all "no"); research only in I s1.
- Diagnosis codes of failing answers: E s1 (134): R9 74, R2 39, G9 6, R5 6, R8 3, other 2, ...; I s1 (81): G5 28,
  G9 16, R5 15, other 8, R8 6, ...; I s2 (59): R5 22, R4 18, R6 11, ...; I s3 LiveMath (117): other 116,
  noncompletion 1 (the LiveMath rubric is all format items, so every trigger set T_r is the same 35 check-half items).
- Rules proposed: 20 (5 per step). Analyst-suggested "similar" placement: 2 (I s1-r5, I s2-r5); E s1 and I s3 none.
  Status: supported 13; insufficient_support 3 (incl. I s2-r5, the similar candidate, 0 triggers because its code
  answer_tag_present had no failing check-half answer); dropped_pre_dispatch 4 by the mechanical leak check (§9),
  recomputed offline: E s1-r3 answer_text ("pudding", a real training answer used as an example), E s1-r5
  shared_8gram (quoted a training question), I s1-r5 answer_text ("three" in "one to three words"; the SearchQA pool
  has 217 single-word answers >= 5 chars; this was the only similar candidate of I s1), I s3-r1 option_text (quoted
  the LiveMath meta-option "One of the remaining options is correct, but a stronger result can be proven", which is
  the correct option's content in some training item).
- Research (§7): 2 questions in 4 steps (both I s1, both about Jeopardy answer-name conventions) -> "none"
  (researcher_none; every relevant Wikipedia page has "Jeopardy" in the title and is excluded by design). No research
  question in E s1, I s2, I s3. Forward questions (§8): none generated (no similar candidate reached that stage).
  So the similar placement, C4', forward questions and research have not been exercised at all yet.
- Gate (C1 gain in items = sum L(rule) - sum H(parent) on T_r; margin vs max placebo):
  E s1: r1 screen gain 4 (margin 1/2), confirm 6 (1); r2 screen 9 (4), confirm 8 (3); composite pass -> both merged
  into the SearchQA section ("put ONLY the short answer in the tag, 1-3 words"; "minimal identifying form: surname
  alone ..."). I s1: 4/4 fail C1 (gains 1/2, -1/2, 0, -2). I s2: 3/3 fail C1 (gains 1/2, 0, 1/2). I s3: r2 gain 5
  (margin 5/2), r3 gain 4 (3/2) pass; r4 5/2 (0) and r5 0 fail.
  Placebo-as-rule passes (descriptive, §5.8): E s1 screen 2/8, confirm 1/8; I s1 0/16; I s2 1/12; I s3 4/16.
  E-glm's training pass rate on SearchQA (64.8%) vs I-glm's (77.8%): the instruction already covers what E-glm learned.

### My preliminary reading and candidate directions (please critique, re-rank, add, and make concrete)
1. Throughput: the slot design starves the main chain (E-glm) while baselines learn; projected wall-clock is days.
   Next version: fair-share or capped baseline holds (e.g. <= 4 GLM slots and never all native slots), or run
   baselines in a separate window; priority for multi-turn ALFWorld episodes.
2. Examiner revision: all-or-nothing validation loses 3 of 4 revisions to a length overflow. Next version: validate
   per edit (drop only the bad edit), or one repair turn quoting the validator message, or prompt "<= 250 chars".
3. Leak check false positives: common-word single-word answers ("three") kill generic rules. Next version: exempt
   words that are frequent in the bench's task texts / an English stopword+number-word list, or send single-word
   hits to the LLM adjudicator instead of dropping.
4. Similar placement never used: few proposals, killed by leak/support. Next version: a dedicated "transfer"
   proposal after local acceptance (generalize each accepted local rule for the similar targets; test with C4'
   backward panels / forward questions), and trigger support for similar candidates from the home triggers.
5. LiveMath diagnosis is all "other" -> identical triggers. Next version: a reference-aware error taxonomy for
   reasoning benches (wrong theorem, dropped hypothesis, arithmetic slip, misread option ...).
6. Research nearly unused and structurally blocked for SearchQA. Next version: require questions for rules that make
   factual/domain claims, or drop research for SearchQA and spend the budget on forward questions.
7. I-chain: rules restate the instruction (C1 ~ 0). Next version: tell the analyst which instruction lines already
   cover each failure code and ask only for residual failures.
8. Baseline strength: GEPA learned only once (3 reflection calls per step), SkillOpt hit the reflection cap and the
   240 KB prompt guard; worth reporting budget utilization; for a next version consider equalized budgets.

### What I need from you (please be concrete and brief per item)
A. Verify or refute each factual claim above that the repo can check (slots/hold_many behavior and its effect;
   `_edits` all-or-nothing; leak `words` check; analyst/research behavior; registered handling of `pending_carry_parent`).
B. What else should I analyze from training-side/process data tonight (no test scores) that would change the
   owner's decisions? Name the exact records/fields.
C. Re-rank the directions by expected impact on the owner's goals (self + similar-bench gain, no dissimilar drop) per
   unit of cost/complexity, and for the top 3-4 give a pre-registrable design sketch (what changes, how to keep it
   honest without a validation set, what could go wrong).
D. Risks for the CURRENT run that need the owner's attention when they wake up (pause triggers, budget, time, the
   deepseek chains sharing GLM slots for their method roles, anything else).
E. GEPA-glm is complete, so §0 would allow viewing its test scores now; but its step-0 row is the shared stage0-glm
   record that is also E-glm's and SkillOpt-glm's step 0 (both still sealed). I plan NOT to open the GEPA report
   until the owner decides. Is that the right reading of §0? Any other protocol constraint I am at risk of breaking
   with this mid-run analysis?


## Codex 的回复（原文）

Your main diagnosis is sound: **the run is exposing bottlenecks in candidate generation, admission, and scheduling—not yet establishing learning or transfer effects.** Several interpretations need tightening.

I inspected the registration, implementation, and relevant tests read-only. I did not open runtime reports, test results, or evaluation artifacts. Your runtime counts and timings therefore remain supplied observations.

**A. What the repo verifies—and what it does not**

1. **Slots: confirmed, with an additional problem.** Baseline learning reserves eight GLM slots throughout the learning invocation. Single-slot requests yield during collection, then share the remaining two. Baselines acquire **all native slots before acquiring GLM slots**, so native blockage can start while learning is still waiting. This arrangement is explicitly registered in §24. Your 9.5-hour estimate and attribution of the entire ALFWorld slowdown need timing evidence; the mechanism is credible. Merely changing `hold_many(8)` to `hold_many(4)` would undercount the unchanged eight baseline workers. [calls.py](../../skillopt/coevo5/calls.py#L93), [baseline.py](../../skillopt/coevo5/baseline.py#L135)

2. **Examiner revision: confirmed.** One invalid edit rejects the entire proposed revision; there is no semantic repair turn. However, `invalid:text` alone does not identify an overlong item: both `text` and `basis` use the 300-character validator, which also rejects empty or non-string values. Your raw-reply inspection is needed to establish the precise cause. “Otherwise sensible” does not establish that the remaining edits would pass selection. [examiner.py](../../skillopt/coevo5/examiner.py#L266)

3. **Leakage: confirmed, but distinguish accidental collisions from intended exclusions.** Single-word textual answers of at least five normalized characters are whole-word blockers; “three” qualifies. The frequency exemption applies only to shared eight-grams. LiveMath correct-option content has a separate substring check without that exemption. “Three” is a persuasive accidental collision; an actual answer example and a quoted training question are intended exclusions under this protocol. Broadly exempting words frequent in task texts risks admitting answer entities. [leakage.py](../../skillopt/coevo5/leakage.py#L124)

4. **Similar proposals: optional, and home support already exists.** The analyst may propose up to two similar rules but need not propose any. Every candidate already derives its triggers from **home-bench check-half failures**, regardless of placement. Thus “use home triggers for similar candidates” is not a new fix. The zero-trigger candidate targeted a code absent from those failures. [analyst.py](../../skillopt/coevo5/analyst.py#L36), [step.py](../../skillopt/coevo5/step.py#L299)

5. **LiveMath diagnosis: the missing piece is taxonomy, not reference access.** Diagnosis already receives the reference letter and correct option, but chooses among rubric text-item codes plus `other`. A format-only frozen rubric would explain your observation; its actual contents and the 116/117 count require runtime evidence. Moreover, the reference contains no worked solution, so labels such as “wrong theorem” require visible supporting evidence. [examiner.py](../../skillopt/coevo5/examiner.py#L154)

6. **Research: exercised unsuccessfully, rather than wholly unexercised.** Two requests returning `researcher_none` are research activity. Successful findings, rewriting, forward-material production, and similar gating remain unexercised on your account. The Jeopardy-title exclusion is real, but “every relevant page is excluded” is stronger than the code establishes. In fact, `researcher_none` follows presentation of at least one usable fetched page. Inspect retrieval logs before assigning the cause. [research.py](../../skillopt/coevo5/research.py#L615)

7. **Baseline handling: registered.** `native_reflection_incomplete` belongs to the learner’s own stopping rules and can produce `pending_carry_parent`, with the step treated as completed. Retaining an already accepted prefix is a separate completed outcome. GEPA’s three reflections are consistent with its explicit **three-iteration limit**, rather than evidence that its token allowance was insufficient. Equal token/reflection ceilings do not equalize candidate opportunities. [registration §24](../../docs/handoff/coevo5-registration-v6-20261017.md?plain=1#L988), [GEPA adapter](../../skillopt/continual_learning/gepa.py#L488)

8. **Gate interpretation needs restraint.** Your reported C1 outcomes match the implemented inequalities, including failure when the placebo margin is zero. But identical LiveMath triggers duplicate placebo comparisons across rules: 4/16 is not sixteen independent trials. Likewise, the E/I training-rate contrast is consistent with instruction coverage, but does not establish that redundancy caused I’s rejections. The analyst already sees the full current Skill. [gate.py](../../skillopt/coevo5/gate.py#L33), [analyst payload](../../skillopt/coevo5/analyst.py#L79)

**B. Highest-value analyses tonight**

Use training artifacts and existing process metadata only. Here, paths are relative to a chain’s `s{k}` directory.

| Analysis | Exact records/fields | Decision it informs |
|---|---|---|
| **Proposal/support funnel** | `prepare/unit.json`: `result.halves`, `result.rules[].{id,codes,placement,status,trigger,also,similar_status}`; selected attempt’s `diagnoses.json`: `{code,by}` | Count unique items per code and half, trigger overlap, and attrition by cause. Distinguishes absent mechanisms from admission failures. |
| **Residual-error audit** | `train/unit.json`: `result.cells`, `result.tokens`; training cells’ `final.{token,kind}` and stored answers; parent Skill and proposal `{text,rationale,codes}` | Manually inspect a seeded sample: duplicated instruction, operational improvement, genuinely new mechanism, or insufficient diagnostic evidence. Check clipping of the text actually shown to the analyst. |
| **Recoverable revisions/leak collisions** | `prepare/attempt-N/roles.json`: revision calls’ `sends[].receipt.response`; `revision.json`; `research.json[].{original,status,questions,rewrite}` | Validate each edit’s `text`, `basis`, evidence, and dependencies. Recompute mechanical matches against the home training pool. Report syntactic recoverability, not hypothetical acceptance or gain. |
| **Gate fragility** | `screen`/`confirm` unit `result.verdicts[arm].criteria`; training gate cells’ `cell.{arm,task_id,run}` and `final.{token,kind}` | Separate gains, losses, unknown penalties, and placebo variability. Report unique trigger sets and per-item changes rather than only aggregate margins. |
| **Research failure location** | `research.json[].questions[]`: `{status,reason,calls,pages,log}`; logs’ searches, dropped results, fetched/skipped pages, conclusions and voided quotations | Distinguishes poor questions, exclusion, retrieval failure, irrelevant sources, and justified abstention. |
| **Resource use and baseline stopping** | Global `ledger/events.jsonl`: `{time,event,id,label,scopes,amount,charged}`; baseline `learning/unit.json`: `result.{action,reason,costs,accepted_steps,steps,official_best_is_parent,official_best_rejected,final_margin}` where present | Establish actual limiting resources and candidate opportunities before proposing larger budgets. |

**Timing trap:** `sends[].started` precedes slot acquisition, and `seconds` includes waiting. It is not provider latency. Ledger reservation-to-settlement intervals better approximate dispatched-call time; native lock acquisition is not separately timestamped. [calls.py](../../skillopt/coevo5/calls.py#L149)

**C. Ranking and next-version designs**

For scientific gain per cost, I rank **(5 + 7) residual diagnosis/proposals → 4 transfer opportunity → (2 + 3) admission reliability → 6 targeted research → 8 baseline budget redesign**. Direction **1 is the first operational prerequisite**, although faster completion alone does not improve learned rules.

1. **Separate semantic diagnosis from examiner judging; require residual proposals.**  
   Freeze a compact diagnosis taxonomy from training-side audits, with observable evidence and an `insufficient_evidence` category. Keep reference-free judging separate. Require proposals to identify the instruction already covering the issue and the additional action being introduced; include a bounded sample of successful counterexamples. Preserve the candidate and call budgets. Predeclare any coarse-category fallback before gate observations.

   **Honesty:** training panels remain adaptive selection material; emphasize improvement over the I starting instruction in the next protocol’s effect readouts.  
   **Failure mode:** fabricated causal diagnoses, or overly fragmented codes producing fewer than four supporting items.

2. **Reserve a bounded transfer opportunity before gate results.**  
   Reserve one of the five proposal slots for a transferable mechanism or explicit abstention. Generate it from proposal-half evidence and public target cards. This is cheaper and cleaner than generalizing every accepted rule afterward. If you choose post-acceptance rewriting, the rewritten text is a new candidate requiring full home and target checks.

   Pre-register target-task blueprints and material sampling independently of solver results. Retain C4′ no-harm; if positive transfer drives selection, an explicit additional criterion could require at least one item of conservative gain on a designated target, with nonnegative deltas on the others. Simulate its power before committing.

   **Honesty:** generated-panel success remains selection evidence.  
   **Failure mode:** synthetic tasks reward the rule without representing real target tasks; stricter criteria may make transfer admission rare again.

3. **Repair admission reliability without weakening substantive checks.**  
   For revisions, validate edits individually, preserve order, and validate the resulting rubric as a whole. Alternatively allow one bounded syntax/length repair before any selection feedback. For leakage, route ambiguous lexical collisions to a contextual adjudicator that sees the matched training evidence; retain hard rejection of specific question–answer mappings.

   **Honesty:** freeze policies using labeled engineering cases, including both accidental matches and real leakage; log every rejected or repaired element.  
   **Failure mode:** dependent edits become inconsistent, or contextual adjudication admits memorization. A 250-character prompt target alone is only a mitigation.

4. **Replace whole-unit resource ownership with honest admission accounting.**  
   Use a central per-call/per-native-job scheduler with a declared baseline cap, or reduce actual baseline workers alongside reservations. Ensure every competing chain can progress, and let active ALFWorld episodes obtain subsequent action calls without indefinite delay. Fixed execution windows are simpler but introduce time/provider differences between methods.

   **Honesty:** fix the schedule before launch and compare queue time, utilization, and completed work—not just elapsed learning-unit time.  
   **Failure mode:** counting reserved slots rather than actual workers recreates oversubscription.

I would **not require research questions universally**. Naming/scoring conventions should first use the frozen public task/scorer description. Nor would I increase baseline budgets before separating the iteration limit, prompt overflow, acceptance rule, and useful candidate count.

**D. Current-run issues for the owner**

- **ALFWorld delay warrants infrastructure diagnosis, not an efficacy inference or automatic restart.** Its episode slot spans the episode, while each action reacquires a model slot. Slow wall-clock alone is not a registered pause trigger. Native slots acquired by waiting baselines can compound this delay.
- **Native resource pressure is a registered risk.** Holding all three/six external native slots excludes other chains; it does not throttle the baseline’s internal eight workers to three/six. §24 explicitly flags untested eight-worker native operation on the development machine. [registration](../../docs/handoff/coevo5-registration-v6-20261017.md?plain=1#L1001)
- **Low settled utilization is not guaranteed headroom.** Each baseline learning step needs a 93M reservation upfront. Admission considers settled plus open reservations at step, chain, and overall scopes. Individual caps are not additive entitlements. E’s 6M versus the 14M planning estimate also reflects which branches executed; it is not an efficiency result.
- **Deepseek is only partly separate.** Its method roles share GLM slots and paid budgets; its native jobs share native resources. A successful router probe would not remove those bottlenecks. Verify an actual model response before releasing concurrent work.
- **Keep unknown categories distinct.** Spreadsheet artifact unknowns do not alone trigger the evaluation infrastructure threshold. Parent/control infrastructure unknowns above 10% pause a round; candidate-arm unknowns above 10% across categories make that arm undetermined. Persistent HTTP-400 items can still distort small trigger panels through conservative bounds.
- **Recovery must follow §13.4.** No opportunistic retry of a completed carry-parent step. A genuine paused/interrupted unit requires owner-authorized whole-unit redo, retained failed-attempt costs, and the prescribed cleanup procedure where applicable.

A scientific limitation also deserves attention: **the gates do not guarantee the owner’s literal “no dissimilar drop” objective.** C3 checks earlier benches with tolerances; future dissimilar benches lack training-side protection. OfficeQA→SpreadsheetBench is also excluded from forward checking. C4′ passing establishes neither positive transfer nor universal no-harm.

**E. GEPA unsealing and discussion boundaries**

**Waiting is prudent, but I would not say §0 unambiguously requires it.** The implementation explicitly allows a completed chain to resolve its shared stage-0 source without waiting for the other sharing chains. A test covers this behavior. Thus your concern identifies an ambiguity between chain-based permission and exposure of shared scores—not a clearly implemented all-chains sealing rule. Let the owner resolve it before exposure. [unseal implementation](../../skillopt/coevo5/evaluation.py#L429), [test](../../tests/test_coevo5_evaluation.py#L347)

Your present discussion is compatible with the boundary if it remains read-only and proposes future versions. Avoid running the general report merely to obtain costs: it can now unseal completed GEPA results. Keep evaluation answers, traces, diagnostics, and pass/fail outcomes closed. Do not feed tonight’s observations into current prompts, gates, retries, scheduling changes, or selective termination. Preserve the distinction between **training-side diagnosis, hypothetical recoverability, and independent evidence of improvement**.

---

# Codex 讨论（第 2 轮，2026-10-19 02:58–03:04）：门的检出力模拟、空白起点的固定架子、优化方向重排

> 第 1 轮之后补充的训练侧分析（零调用）交给 Codex 复核与讨论；同样只读仓库、没有接触开发机上的运行记录或测试结果，命令同上（输出 65,732 tokens）。按回复做的修正已写进 [coevo5-midrun-analysis-20261019.md](coevo5-midrun-analysis-20261019.md) §3.8、§3.9、§5、§6：模拟表改称"简化模型下两轮 C1 都过的机会"并只用 I-glm 的规则（E-glm 各臂不一样）；合并两轮判的方案并非花费不变；对照文字"5/6 轮有 1 段能过"不能和单组题的模拟直接比；空白起点的差别还包括做题提示的引导句"Frozen skill guidance"，分不开哪部分起作用，也不能说测试上的提高有多少来自它；第 8 条改为只用提案半的失败。

## 发给 Codex 的问题（原文）

### Discussion request, round 2 (not a code review): new mid-run findings of the five-bench coevolution run

You are a second researcher (we discussed round 1 two hours ago; your reply is archived in
`docs/handoff/coevo5-midrun-discussion-codex-20261019.md`). The owner is still asleep. Since then I added new
training-side analysis to `docs/handoff/coevo5-midrun-analysis-20261019.md` (Chinese; see §1, §2, §3.3–§3.5, §3.8,
§3.9, §5 items 4/5/7/8, §6). Everything is zero-call and training-side; no test score has been opened (§0 sealing);
nothing feeds back into the current frozen run. Please check my new claims against the code (read-only), push back
where I am wrong, and keep the reply focused (this is the last discussion round tonight). Reply in English.

#### New facts (02:55)
1. I-glm s3 (LiveMath) confirm finished 01:30: both screen-passing rules failed C1 (gain 3/2 and 0 vs parent; best
   control +5/2). Nothing accepted; I-glm s1–s3 accepted no rule. In 5 of 6 gate rounds so far, the registered
   placebo-passage description (`gate.placebo_passage`) shows one control would itself pass C1.
2. Examiner revision: 6 calls, 1 accepted (E s1), 5 `invalid:text` -- every one from a >300-char text/basis field
   (lengths 305–395). Per-edit validation would salvage 1 edit in 2 replies; one length-repair turn would salvage 5.
3. Research: 5 questions run, all `none`. I-glm s4 asked about Excel SUMIF wildcards, VLOOKUP exact-match/IFERROR
   and openpyxl max_row; Wikipedia returned unrelated pages; the pinned archive (Python/openpyxl docs, task cards)
   has no spreadsheet function reference. SpreadsheetBench is scored after LibreOffice recalculation.
4. Similar placement: 30 proposals in 6 steps; 3 similar; none reached a gate (1 leak false positive on "three";
   2 targeted the rubric code `answer_tag_present`, which the solver essentially never violates -> 0 trigger items).
5. Slots: SkillOpt-glm s4 learning (SpreadsheetBench) started 01:45 and holds all 3 spreadsheet-native slots; the
   I-glm s4 screen (SpreadsheetBench) stalled at 19 cells since 02:14. One research_query call waited ~772 s for a
   GLM slot with a ~1 s API time.

#### Gate power simulation (analysis doc §3.8; scripts below)
Per rule that went to a gate, on its trigger items: p_i = (passes+0.5)/(known+1) pooled over the parent and the 4
controls in all rounds of that step; simulate parent, 4 controls and the rule with GATE_RUNS runs per item; C1 as in
`gate._benefit` (rule total - parent total >= 1 and rule total > every control total), unknowns ignored (L = H);
two independent rounds. A rule with expected gain D: p_i' = p_i + d(1-p_i), sum = D.
Results (two rounds, current design): null 0.4–1.5% per rule; D=2: 24–74%; D=3: 47–97%; D=5: 84–100%; LiveMath
(35 trigger items, mean p 0.175): 1.5% / 24% / 47% / ~85%. Alternatives: 4 runs/item: null <=1.2%, D=2 41–90%,
D=3 72–100%; pooling the two rounds with gain >= 2: null 2–11%, D=2 64–95%, D=3 85–100%. Null chance that some
control passes the placebo-passage test in one round: 27–58%.

```python
# core of sim.py (sim2.py adds the alternatives)
def simulate(p, runs, D):
    if D > np.sum(1 - p): return float("nan")
    d = D / np.sum(1 - p) if D else 0.0
    q = p + d * (1 - p)
    def draw(prob, k=1):
        return rng.binomial(runs, np.broadcast_to(prob, (N, k, len(prob))), size=(N, k, len(prob))).sum(axis=2) / runs
    parent = draw(p)[:, 0]; controls = draw(p, 4); rule = draw(q)[:, 0]
    return ((rule - parent >= 1) & (rule > controls.max(axis=1))).mean()
```

#### Blank-start effect (analysis doc §3.9)
E-glm s1 (SearchQA), 32 trigger items, totals in items (mean of 2 runs): blank parent 5.5 (screen) / 3.5 (confirm);
the 4 controls 8.5–12.0; the two rules 14.5–16.5. Replies: parent mean 57–64 chars, answers <=3 words 51–58%;
controls 35–41 chars, 73–81%; rules 29–31 chars, 88–94%; I-glm instruction parent 31 chars, 83%. In I-glm, controls
minus parent = -1.25..+1.62. My reading of `skillopt/coevo5/skill.py`: an empty Skill renders as "" (= No-Skill
prompt); any rule or control in the SearchQA section brings the heading and the registered applicability line
"Applies when: ... and asks for a short answer." So E-glm's control arms differ from the parent by heading +
applicability line + irrelevant text, and the data cannot separate them.

#### Questions
A. Is the simulation a faithful (if simplified) model of C1 and of the two-round rule (check `gate.py`, `stats.py`,
   `step.py` for how trigger items, GATE_RUNS, L/H and the confirm round are actually formed -- e.g. are confirm
   trigger items the same as screen's, are parent cells fresh per round)? Any bias in pooling parent+controls for
   p_i, especially for E-glm where controls clearly differ from the parent? Are the conclusions I draw in §3.8
   ("the gate rarely accepts useless rules but often misses +2..+3 item effects; 'no rule passed' != 'rules
   useless'") supported, and is anything overstated?
B. Is my reading of the blank-start effect right (check `skill.py` rendering and how the Skill enters the solver
   prompt)? Does it threaten the registered main comparison (E-glm vs SkillOpt/GEPA non-inferiority; their Skills
   have no applicability lines) or the "learned vs stage 0" readout? What should the final report say, and is a
   "scaffold-only Skill" stage-0 reference the right fix for the next version?
C. Given 1–5 above, re-rank the next-version directions in the doc's §5 (now items 0–8) briefly; flag anything that
   is wrong or that you would drop.
D. Anything I should watch or do in the next ~5 hours of monitoring (pause risks, slot holds, the deepseek chains
   if the quota returns), without touching the frozen run.

## Codex 的回复（原文）

The new evidence strengthens the case for fixing interpretation and admission before increasing budgets. The main corrections are: **the simulation describes C1, not acceptance; scaffold effects remain unidentified; and item 8 must preserve the proposal/check split.**

I checked the repository read-only and inspected the supplied simulation kernel. Runtime counts, reply lengths, and full simulation outputs remain supplied observations; I opened no test results.

**A. Simulation**

The C1 arithmetic is faithful under complete outcomes: sums of per-item rates, gain ≥1 over parent, and strictly above all four controls. Implementation details also support your setup:

- Triggers are frozen, distinct **check-half items** with a failed training response assigned a targeted code. Confirm reuses the same trigger sets.
- Parent and candidate cells are fresh each round. Within a round, candidates share parent/control observations.
- Confirm uses **different control texts** from screen.
- `GATE_RUNS` is 2 for SearchQA/OfficeQA/LiveMath, but 1 for SpreadsheetBench/ALFWorld. ([step.py](../../skillopt/coevo5/step.py#L299), [round construction](../../skillopt/coevo5/step.py#L352), [constants](../../skillopt/coevo5/protocol.py#L55))

Five qualifications matter:

1. **Rename the table “two-round C1 passage under the specified model.”** Production unknowns remain in denominators: candidate L treats them as failures; parent/control H treats them as passes. Unknown guards, C2/C3, placement, and composition impose additional restrictions. Fresh calls also do not establish statistical independence. ([stats.py](../../skillopt/coevo5/stats.py#L19), [gate.py](../../skillopt/coevo5/gate.py#L89))

2. **Pooling is particularly problematic for E.** Controls contribute roughly four times the observations of the parent per round. Its estimated \(p_i\) therefore mostly describes scaffolded controls, while simulated parent performance is raised to that same mixture. Your D becomes gain over the mixture, not over the actual blank parent. The registered null concerns advantage over irrelevant same-placement text; equal performance across *all* arms is a stronger assumption. Separate parent/control probabilities before interpreting E’s percentages. Sparse probability estimates, ignored unknowns, and text-specific effects also need sensitivity analysis; their overall bias has no universal direction.

3. **D does not uniquely determine power.** Your uplift allocates gains proportionally to remaining headroom and harms no items. Concentrated gains or mixed gains/losses can behave differently. Moreover, +2 on 35 triggers is +5.7 percentage points on that selected panel—not +2 points on the benchmark.

4. **Pooling is not necessarily “same cost.”** Current confirm reruns only screen survivors. Achieving unconditional pooled-two-round power requires rerunning initial failures too; retaining the screen filter requires including it in the simulation. Also specify how eight different control texts become pooled comparators. “More runs never increase false acceptance” should likewise remain a simulation-specific observation. ([confirmation](../../skillopt/coevo5/step.py#L439))

5. **The placebo comparison needs matching denominators.** `placebo_passage` compares each control against the other **three**, on each candidate’s trigger panel. “Some control passed somewhere in this round” is a union over overlapping panels. Its 5/6 frequency cannot directly be compared with a single-panel 27–58% simulation; shared cells and selectively reached confirmation rounds further complicate that comparison. ([placebo diagnostic](../../skillopt/coevo5/gate.py#L196))

Your qualitative sensitivity argument is useful. I would replace the stronger conclusions with:

> Under the equal-arm Bernoulli model, two-round C1 passage is uncommon under the null, and modest trigger-panel improvements can frequently be missed. No candidate met the registered admission rule; this does not establish that its true effect is zero.

Specifically, LiveMath’s screen improvement **did not reproduce**. It has not been established that the screen was “accidentally good,” nor does nonacceptance establish the absence of large effects.

**B. Blank start**

Your rendering interpretation is correct, with one additional component: any nonempty Skill activates the backend wrapper **“Frozen skill guidance (use only where applicable):”**. Blank SearchQA already receives an instruction to return a concise answer, so the applicability sentence reinforces existing guidance rather than introducing concision for the first time. Baselines receive the shared wrapper when nonempty, but no automatically imposed section/applicability scaffold. ([renderer](../../skillopt/coevo5/skill.py#L62), [solver prompt](../../skillopt/continual_eval/backends.py#L356))

Thus the observations cannot separate heading, applicability, wrapper, irrelevant-text effects, or their interactions. I-glm is suggestive but not an isolated scaffold control.

This **does not invalidate P1/P2 as registered complete-system comparisons**. It limits attribution to coevolution or learned content. The stage-0 gain interpretation is more directly affected. Preserve the registered calculations and say:

> Any eventual E-versus-empty improvement combines learned content with activation of fixed prompt scaffolding. This run cannot identify their separate contributions.

Do not yet assert that a substantial fraction of **test** improvement comes from the scaffold. Neither that improvement nor its attributable fraction has been observed. The accepted rules did exceed matched scaffold-plus-control arms under the training gate; that still does not decompose their eventual test effect.

Also clarify the **32-item panel**: the displayed totals do not reproduce r1’s archived C1 gains of 4/6. If this is a common diagnostic panel or r2’s panel, label it separately from each rule’s own triggers.

A scaffold-only reference is useful next version, but evaluating all five sections once does not exactly match E s1’s SearchQA-only scaffold. Prefer **holding the scaffold fixed from stage 0 onward**, retaining truly empty No-Skill as a separate reference. If section activation remains dynamic, scaffold ablations should match the active sections. Within-I improvement is a cleaner incremental-learning readout; E-versus-I is not a scaffold ablation.

**C. Revised priorities**

My order is **0 and 7 as prerequisites → 1 → merged 3+8 → inexpensive parts of 4 → 5 → 6**, with gate redesign evaluated separately.

- **0, scheduling:** keep first operationally; reduce actual baseline worker concurrency alongside reservations.
- **7, scaffold reference:** elevate for interpretability, using the matched design above.
- **1, residual diagnosis/proposals:** remains the main scientific priority.
- **3+8, transfer:** merge them, but change **“check-half failures” to “proposal-half failures.”** Require cited proposal evidence and relevant code support, allow “none,” then retain independent check-half admission. Showing check-half failures to guide proposals would weaken the existing split. ([proposal/support separation](../../skillopt/coevo5/step.py#L274))
- **4, admission:** length repair and contextual handling of accidental lexical collisions are cheap priorities. But five replies are **eligible for length repair**, not demonstrably recoverable in one call. Repair success, preserved meaning/evidence, whole-rubric validity, and selection remain unmeasured. ([revision validation](../../skillopt/coevo5/examiner.py#L266))
- **5, research:** pinned Calc documentation matching the scoring engine is sensible. However, “not the research model’s problem” overstates the evidence. Missing sources, query quality, retrieval, and early abstention can coexist. `max_row` is within openpyxl’s nominal scope and deserves separate diagnosis from missing function references. ([archive](../../skillopt/coevo5/prelaunch.py#L77))
- **6, baselines:** diagnose candidate opportunities and stopping reasons before increasing budgets.

Keep **2** as a training-panel matching limitation and reporting priority, rather than a proven SearchQA ceiling. Defer choosing a new gate until the simulation represents unequal arms, unknowns, sequential dispatch, and expected cost.

**D. Next five hours**

- **Watch the blocking chain and subsequent release.** SkillOpt’s native holds precede its eight GLM slots. Check baseline progress, process/lock ownership, resource pressure, and whether I resumes after release. Existing lock files alone do not establish ownership. Expect analogous ALFWorld blockage at s5. ([baseline holds](../../skillopt/coevo5/baseline.py#L135))
- **Monitor pause categories and scoped reservations.** Parent/control infrastructure unknowns above 10% pause a gate; artifact unknowns do not count toward that threshold. Candidate unknowns have separate admission consequences. Watch cleanup failures and the next 93M reservation, not just total settled spend. Slowness alone is not a pause condition.
- **If DeepSeek quota returns, verify an actual usable response under the frozen configuration before releasing concurrent work.** Watch recurrence of 403s. Both chains still consume GLM method-role capacity and shared native resources.
- **Preserve recovery and sealing boundaries.** No automatic restart of paused/interrupted units; owner-authorized whole-unit recovery remains required. Continue using process/count metadata, and keep GEPA’s report and shared stage-0 scores closed pending the owner’s decision. ([recovery rules](coevo5-registration-v6-20261017.md?plain=1#L707))

# Codex 讨论（第 3 轮，2026-10-19 05:18–05:21）：I-glm 跑完、E-glm 第 3 步初筛、回归面板的重复抽样

> I-glm 跑完、E-glm 第 3 步初筛之后的新数据（零调用）交给 Codex，作为今晚最后一轮；同样只读仓库、没有接触开发机上的运行记录或测试结果，命令同上（输出 48,426 tokens）。按回复做的修正已写进 [coevo5-midrun-analysis-20261019.md](coevo5-midrun-analysis-20261019.md) §3.3、§3.6、§3.10、§5 第 9、10 条、§6：I 链"超过指令了吗"按构造为 0、结论"未建立"（登记 §12.6 的共用记录抵消），只说明这次没有发生 Skill 进化；泄漏检查的不对称只说这两条具体文字过了，r2 的有条件说法不一定等于"元选项常是答案"；"负差值主要来自父 Skill 偏高"改为"可能起了作用、分不开"，3%/2% 只是有条件的模拟输出；合并父 Skill 历次结果只是减小方差、不是补对照，有选择偏差等前提，且救不回 r3（40 −（46 + 1）= −7）；第 9 条改称"按协议可检验的触发题不足"，ALFWorld 已用上全部 57 道训练题；新增提醒：登记 §12.5 要求 E-glm 至少 2 步收下规则，现在只有 1 步。更正（05:30）：问题里说 ALFWorld 检验半"有 3 道失败题"，逐条核对诊断记录后是 28 道里 4 道做错过、其中 3 道属于提案针对的那一类；结论不变。

## 发给 Codex 的问题（原文）

Round 3 (final round tonight) of the mid-run discussion on the frozen run `fivebench-coevolution-v1`. You are read-only. Do not open any test score, report, evaluation unit or stage-0 record. Please only (a) point out errors in the claims below, and (b) add at most a few genuinely important points. No further rounds will follow, so be decisive.

Context: the analysis document is docs/handoff/coevo5-midrun-analysis-20261019.md (sections 3.3, 3.10 and 5 items 9-10 are new); rounds 1-2 are in docs/handoff/coevo5-midrun-discussion-codex-20261019.md. Code: skillopt/coevo5/{step.py,gate.py,stats.py,protocol.py,skill.py}. Registration: docs/handoff/coevo5-registration-v6-20261017.md (§12.4 secondary readouts).

New facts since round 2 (training-side and process data only, zero calls):

1. I-glm completed at 05:00. Over five steps: 25 proposals; 13 screened (SearchQA 4, OfficeQA 3, LiveMath 4, SpreadsheetBench 2, ALFWorld 0); 2 passed screen (LiveMath), 0 passed confirm; 2 leak-dropped; 10 had fewer than MIN_TRIGGER=4 trigger items. SpreadsheetBench: the two task-semantic rules (not in the instructions) gained +2 and +1 items on their triggers but did not exceed the best control (margins -1, -2; 1 run per item). ALFWorld: 101/114 training episodes won; only 9 items not all-pass; the check half had 3 failing items, so all 5 proposals were insufficient_support and no screen ran. chain-complete.json: skill = 5 seed sections, 0 rules. Monitor: I-glm evaluation units s1-s5 are all status "reused" (25 units), s0 has 5 complete units (1,035 cells, 7 artifact unknowns, 0 infrastructure). Claim: the registered secondary readout "exceeds the instructions?" = M_I-glm[5] - M_I-glm[0] is identically 0 by construction, so its registered verdict is "not established", and I-chain G_b, F_b, N_b are all 0, all known without opening scores. We still keep the I-glm report closed because the owner requires explicit consent to read test scores.

2. E-glm s3 (LiveMath) screen, 4 rules on the same 35 triggers (all diagnosed "other"): r2 pass (C1 gain 4.5, margin 2), r4 pass (gain 3.5, margin 1), r5 fail C1 (gain 0.5), r3 C1 gain 5.5 margin 3 but failed C3: SearchQA regression delta -10 (tolerance 5) and OfficeQA extra format violations 3 (> MAX_EXTRA_VIOLATIONS 2; OfficeQA delta -6 within 7). Confirm for r2, r4 started 04:58. Both screen-passing texts contain exam-construction heuristics: r2 ends "...or the meta-option if an even stronger result holds" (r1, which quoted the meta-option text verbatim, was dropped_pre_dispatch by the mechanical leak check); r4 says options hedging the conclusion with unnecessary assumptions "are typically distractors". Claim: the meta-option asymmetry vs SkillOpt (whose learned Skill states the meta-option heuristic) is only partial; the current leak check blocks verbatim quotation, not this kind of heuristic.

3. Regression-panel cross-check (C3 panels are fixed 60-item training panels, 1 run per item, rule arms and parent only, no controls; skill.py renders all sections into every prompt). E-glm s2 accepted nothing, so the E parent Skill is identical in s2 and s3. On the same 59 known SearchQA regression items (1 item is HTTP 400 for every arm, which costs each rule -1 through L vs H): E parent 43 (s2 round) vs 49 (s3 round; 7 fail->pass, 1 pass->fail); E rule arms 42, 47, 46, 44 (s2, OfficeQA text added) and 45, 40, 47, 45 (s3, LiveMath text added). r3 vs s3 parent: gained 0, lost 9. I-glm parent (identical Skill all steps) on the same items: 44, 43, 45, 46 over four rounds, 2-5 flips between rounds; its 11 rule arms 44-47. OfficeQA panel: E parent only one regression draw so far (36), E s3 rules 33, 30, 32, 30; I parent 37, 33, 36 with 8-12 flips between rounds. A Bernoulli model with per-item p estimated from the 15 (SearchQA) / 11 (OfficeQA) I-glm draws gives P(a useless rule fails the C3 delta criterion in one round) about 3.3% (SearchQA) and 1.6% (OfficeQA), ignoring the format-violation criterion. Claim: the uniformly negative s3 deltas are most likely driven mainly by a high parent draw (49 is the max of the 10 E draws on that panel), though "adding another bench's section slightly hurts E's short Skill on SearchQA" is not excluded; r3's own harm is not identifiable from one round.

4. Proposed next-version items (analysis §5): item 9, near-ceiling benches leave too few check-half failures (decide in advance: report "nothing testable" as an outcome, or give such benches more training items/runs). Item 10, C3 lacks a reference: cheapest fix is to use the mean of the parent's repeated regression-panel draws (the parent is fixed within a step and often across steps) instead of only the current round's single draw, at zero extra calls; alternatives are a control arm on regression panels or 2 runs per item; tolerances must be recomputed by zero-call simulation; a more radical option (render only the bench's own section) is offered only as a separate ablation because it leaks bench identity, must apply to baselines too, and changes the similar-transfer mechanism.

5. Timing: since the baselines finished (03:30), E-glm s3 train took 4 min, prepare 7 min, screen 53 min; I-glm s5 train 33 min. We re-estimated E-glm completion as 10/19 midday to evening (earlier estimate 1.5-2.5 days). DeepSeek still 403 at 05:05; E-ds/I-ds will start when quota returns.

Questions:
A. Are claims 1-3 correct as stated (especially the "identically 0 / not established" deduction and the parent-draw interpretation)? Correct any overstatement.
B. Is item 10's "pool the parent's repeated draws" sound? Name any bias it introduces (e.g., parent draws used in earlier decisions, cross-step pooling, L/H unknown handling, changed tolerance calibration).
C. Is item 9 framed correctly?
D. Anything important to tell the owner in the morning summary that we are missing? Anything worth computing zero-call in the next ~3 hours?
Answer in English, compactly.

## Codex 的回复（原文）

**A. Claims 1–3**

1. **The zero-change deduction is correct**, taking your process facts as given. Reused evaluations make every defined I-chain \(G_b,F_b,N_b\), and \(M[5]-M[0]\), exactly zero. [§12.6](coevo5-registration-v6-20261017.md) explicitly makes shared unknown records cancel too; paired bootstrap intervals therefore also collapse to zero. The registered verdict is **“not established.”** This establishes no Skill evolution in this run—not that improvement beyond instructions is impossible. No scores need opening.

2. **Partial leakage-policy asymmetry is supported**, but narrow the wording: these particular heuristic-bearing texts passed; that does not establish that the entire leakage pipeline permits such heuristics generally. Also, r2’s conditional “if an even stronger result holds” is not necessarily the same shortcut as “the meta-option is frequently correct.” R4’s “typically distractors” is more clearly an exam-construction heuristic.

3. **“Most likely driven mainly by a high parent draw” is too strong.** Replace it with: “A high shared parent draw plausibly contributes; the data do not separate this from common added-section harm or rule-specific harm.” Being the maximum of ten **different-text** draws does not establish that the parent was anomalously lucky. I’s probabilities cannot calibrate E’s different prompt.

   The 3.3%/1.6% figures are conditional simulation outputs, not established C3 false-rejection rates. Rule-arm pooling assumes those rules have no effect; sparse probability estimates, dependence and omitted format checks further limit interpretation. R3’s zero gains/nine losses is adverse paired evidence, although reproducible expected harm remains uncertain.

**B. Pooling parent draws**

**Sound as a next-version variance-reduction candidate; not a missing-control fix.** C3 already has a parent reference. Pooling cannot distinguish rule content from generic added-section effects.

- Pool only genuine draws of the **identical full parent prompt**, panel and execution configuration, under a prespecified inclusion/window rule. Cross-step pooling additionally assumes stationarity.
- Availability is adaptive: confirmation follows screen success; retaining the same parent across steps follows failed updates. Earlier parent outcomes helped determine those decisions. Consequently, the pool can be selection-biased; the direction is not universal. Sharing the pool also makes screen and confirmation dependent.
- Preserve per-item parent **H**, candidate **L**, and all scheduled denominators. The permanently unknown item still costs −1. Historical observations must not dilute the current infrastructure guard.
- Recalibrate the sequential procedure, including format violations and joint benchmark checks. “Two runs per item” also needs a format-count definition: the current implementation counts raw violating cells.

A useful zero-call check already follows from your numbers: pooling E’s parents gives 46 known successes. R3 becomes \(40-(46+1)=-7\), **still failing tolerance 5**; its OfficeQA format failure also remains. Pooling would not rescue this example.

**C. Item 9**

Use **“insufficient eligible trigger support under this protocol,”** not the document’s “no learnable failures.” Three distinct check-half failures cannot support the registered gate; that is not a benchmark ceiling.

More repetitions can expose additional failing items but cannot guarantee four distinct triggers. ALFWorld already uses all **57 registered training items**, so enlarging its panel requires additional training data. Prespecify any expansion/stopping rule and preserve the proposal/check separation.

**D. Morning summary and remaining zero-call work**

One consequential reminder: [§12.5](coevo5-registration-v6-20261017.md) requires **at least two E steps with accepted updates**; otherwise it labels the method as barely updating and says not to interpret P3/P4. E currently has one such step.

The two worthwhile calculations are:

- A sequential C3 sensitivity analysis comparing current versus pooled parents, including adaptive pool availability, shared-round effects, unknowns and format failures.
- A support analysis based on **distinct eligible check items**, assessing what additional items or repetitions could realistically buy.

Keep these descriptive and prospective; none changes the frozen decisions. I opened only the discussion/analysis documents, registration and source code, with no prohibited records or writes.
