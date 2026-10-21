# D2 feasibility report: case / experience memory instead of (or beside) rules

Explorer D2, 2026-10-20/21. Every number is labelled **measured** (computed from run data or produced by the pilot),
**estimated** (arithmetic on measured quantities) or **claim** (from a cited paper, checked against the paper's own
text on arXiv/ACL Anthology during this session). Training items only: no test/holdout/evaluation path was listed,
read or copied; the repository (local and `/data/skillopt-work`) was not modified; nothing was written under a run
directory. Paid tokens used: **1,913,778 of the 2,000,000 allowed** (measured; breakdown in section 5.6).

## 0. Verdict in one paragraph

Feasibility as a replacement for rules: **low**. Engineering is easy (the whole pilot was built from existing v3
records in a few hours), but the evidence is negative. On 100 SearchQA training items x 2 runs, adding the two
lexically retrieved cases to the task-card Skill gave **5 up / 7 down / 88 ties, mean -1.0 point, 95% CI [-6.0, +4.0]**
(measured). That is the size of the run-to-run noise: re-running the same parent text moved 10 items (3 up / 7 down).
The only item fixed in both runs was an **answer leak** (a case's own reference "Sir Francis Drake" is the evaluated
item's answer). The harm came from contradictory answer-form lessons applied where they do not fit ("surname only"
turned "Ronald Reagan" into "Reagan"). An oracle that picks cases by the item's own diagnosis code, which a solver can
never know, gained 3 up / 1 down on the 27 failed items (+7.4 points on that subset, CI [-1.9, +20.4]): at most
about +2 points on the 100-item panel (estimated). The literature agrees with this picture. Experience memory wins big
in recurring environments (ALFWorld, WebArena, AppWorld) but adds about +3 points on short-answer QA, against weak
baselines. Cross-dataset transfer (ExpeL HotpotQA -> FEVER) is carried by abstracted insights, i.e. rules, not by
retrieved cases. A case bank is local to one benchmark by construction, so it does not serve the owner's "evolve on
one, evaluate on the others" yardstick. Recommendation: keep rules as the learned artifact and import three mechanisms
from the memory literature into them (applicability predicates with abstention, helpful/harmful counters with
history-based deletion, abstract examples with a leak check against every pool answer). Test case memory only on
ALFWorld, as a within-benchmark comparison, if the paper needs a memory baseline.

## 1. Assignment and how this report was produced

Assignment: survey ExpeL, Agent Workflow Memory, Dynamic Cheatsheet, ACE, Reflexion and related 2024-2026 work
(memory form, retrieval, reported gains on QA/agent benchmarks); design a case bank built from the v3 training
failures (examiner outputs and prepare records), injected at solve time within the Skill byte limit, gated without a
validation set; pilot (<= 2M tokens): 30-60 cases from E-ds/I-ds SearchQA stage-1 failures written by GLM, lexical
retrieval, top-2 injected into the system prompt, deepseek on 100 SearchQA TRAINING items x 2 runs vs the parent,
paired up/down/ties and the mean difference with a bootstrap CI.

A first D2 attempt in this workflow had built the bank, run the pilot (finished 2026-10-20 19:28 on the new machine)
and left a draft (`report_draft.md`) without results or verdict. This report **supersedes that draft**. Every script
was re-read, every number recomputed from the raw v3 records and the pilot cells with independent code (`verify/`),
local and remote copies were checksum-identical, and the literature numbers were re-checked against the papers.
Corrections relative to the draft:

1. I-ds stage-1 had **3** replies truncated at 32,768 tokens (all scored `noncompletion` fails), not 1.
2. The SearchQA pool has **21** normalised answers shared by two items (official SQuAD normalisation), not 16 (the
   draft used lower-casing only). The list includes "sir francis drake", "sir isaac newton", "adirondacks", "ronald reagan".
3. Primary scoring now follows v3: a truncated reply is a **fail** (`skillopt/coevo5/outcomes.py`, row 5,
   `model_response_truncated` -> FAIL/noncompletion). The draft excluded truncated runs; both versions are reported.
4. The draft's oracle comparison (n = 10, 0 up / 1 down) was computed at 19:15, before the main pilot finished (19:28),
   so most parent cells were missing. Recomputed on all 27 items: **3 up / 1 down, +7.4 points**.
5. Measured prompt growth is **+349 tokens per cell** (draft estimate +450).
6. Literature: AutoGuide WebArena-Reddit is 47.1 (not 43.7); Learn-by-Interact reports up to 12.2% for ICL with
   Claude-3.5 (not 11.1); ACE's HotpotQA remark is about "concise, high-level instructions" (the "single rule" remark
   is about Game of 24). Venues that the arXiv pages do not state were removed. The unverifiable secondary claims
   (Memora, MemoryAgentBench, LongMemEval-V2, KATE answer-overlap leakage) were dropped.
7. The single robust "up" item of the pilot is an answer leak (section 5.4).

## 2. Verified facts about the v3 data (measured)

Sources (new machine): `/data/coevo5-20261019-v3-run/{I-ds,E-ds}/s1/train/unit.json`, the cells and prediction
artifacts under `train/attempt-1/`, `s1/prepare/attempt-1/diagnoses.json` (one code per failed run) and
`s1/prepare/unit.json` (halves, proposals). Collected into `v3_s1_train_rows.json` (800 rows) and
`searchqa_train200.json` (the 200 training-execution items: public text plus training answers). Raw re-count: I-ds
310 pass / 90 fail, one Skill digest `ee9b737f...`, 90 diagnoses; E-ds 297 / 103, digest `cc516459...`, 103 diagnoses.

### 2.1 SearchQA stage 1

| | E-ds (empty scaffold) | I-ds (task-card seeds) |
|---|---|---|
| Training execution | 200 items x 2 runs | 200 items x 2 runs |
| Items failing >= 1 run / both runs | 55 / 48 | 54 / 36 |
| Run pairs pass-pass / fail-fail / mixed | 145 / 48 / 7 | 146 / 36 / 18 |
| Failed runs (all diagnosed) | 103 | 90 |
| Codes per failed run | D1 37, D2 20, D3 14, D4 14, D5 10, other 5, answer_tag_present 3 | D1 35, D2 28, D4 12, D5 9, noncompletion 3, other 3 |
| Halves proposal / check | 101 / 99 | 100 / 100 |
| Stage-1 proposals | 5, all `supported`, all `local` | 5: 3 `supported`, 1 `leak_adjudicated_word`, 1 `dropped_pre_dispatch`, all `local` |
| Prompt tokens per cell, mean / max | 1,220 / 1,401 | 3,776 / 3,957 |
| Completion tokens per cell, mean / max | 16 / 255 | 312 / 32,768 (3 truncations) |

Codes (v3 taxonomy, SearchQA): D1 extra words (right thing, fuller form), D2 other form (part missing, inflection,
synonym, spelling), D3 not one answer (list, sentence), D4 wrong candidate, D5 wrong kind of answer.

Failure form, using the official normaliser on the failed runs. "Extra <= 3" means the reference is a contiguous
sub-span of the answer with at most 3 extra words; "missing <= 3" is the reverse.

| Failed runs | extra <= 3 | missing <= 3 | partial overlap | different | no reply / no tag |
|---|---|---|---|---|---|
| I-ds (90) | 29 | 13 | 17 | 28 | 3 |
| E-ds (103) | 32 | 12 | 24 | 32 | 3 |

So 42 of 90 I-ds failed runs (47%) name the right entity in the wrong form. The right form is not observable from
the task. It depends on the reference annotation, and it goes both ways: the bank's own source items need "Arthur"
(not "Chester A. Arthur") and "Fragonard" (not "Jean-Honore Fragonard"), but "Sir Francis Drake" (not "Francis
Drake") and "Sir Isaac Newton" (not "Isaac Newton").

### 2.2 All five stages (training execution, failed runs and their codes)

| Stage, bench | Chain | Items x runs | pass / fail | items all-fail / mixed / none-fail | dominant codes (failed runs) |
|---|---|---|---|---|---|
| s1 SearchQA | I-ds | 200 x 2 | 310 / 90 | 36 / 18 / 146 | D1 35, D2 28, D4 12 |
| s2 OfficeQA | I-ds | 74 x 2 | 37 / 111 | 52 / 7 / 15 | D2 wrong method 41, D1 wrong data 30, D3 calculation slip 20 |
| s3 LiveMath | I-ds | 100 x 2 | 66 / 134 | 59 / 16 / 25 | D1 missed "stronger result" option 85, D4 23, D3 17 |
| s4 SpreadsheetBench | I-ds | 91 x 1 | 47 / 43 (+1 unknown) | 43 / 0 / 48 | D4 wrong logic 25 |
| s5 ALFWorld | I-ds | 57 x 2 | 58 / 56 | 24 / 8 / 25 | D3 search loop 45 |
| s1 SearchQA | E-ds | 200 x 2 | 297 / 103 | 48 / 7 / 145 | D1 37, D2 20, D3 14, D4 14 |
| s2 OfficeQA | E-ds | 74 x 2 | 30 / 118 | 56 / 6 / 12 | D2 46, D1 32, D3 20 |
| s3 LiveMath | E-ds | 100 x 2 | 75 / 125 | 56 / 13 / 31 | D1 79, D3 18, D4 16 |
| s4 SpreadsheetBench | E-ds | 91 x 1 | 46 / 44 (+1 unknown) | 44 / 0 / 47 | D4 27 |
| s5 ALFWorld | E-ds | 57 x 2 | 46 / 68 | 30 / 8 / 19 | D3 43, D1 12 |

ALFWorld episode cost (measured, s5 training cells, all sends): I-ds mean 105,651 tokens per episode (median 154,646;
31.3 model calls), E-ds mean 28,463. The 12.7 KB Skill is re-sent with every call.

### 2.3 Pool structure (what a retriever could exploit)

- SearchQA: 600 training-pool items in 600 singleton families; 21 normalised answers shared by exactly two items.
- OfficeQA: 74 training items (all singleton families) cite 114 distinct Treasury Bulletin issues. 95 issues are cited
  by one item, 14 by two, 5 by three. 29 of 74 items share at least one cited issue with another item.
- LiveMath: 100 training-execution items in 100 singleton families.

Unlike WebArena/AppWorld/ALFWorld in the memory literature, the QA pools have no recurring environment. OfficeQA's
shared bulletin issues are the only partial exception.

## 3. Literature survey (claims; every number checked against the paper during this session)

| Work | Memory form | Retrieval / injection | Labels needed | Reported results |
|---|---|---|---|---|
| Reflexion (arXiv 2303.11366) | verbal reflection on the previous failed attempt of the SAME task | prepended on the next trial | binary success per trial (HotpotQA: exact-match grading; ALFWorld: environment) | HotpotQA (100 Qs) ReAct 0.26 -> 0.38 (gpt-3.5-turbo), 0.39 -> 0.51 (gpt-4); CoT(GT) 0.57 -> 0.71, 0.68 -> 0.80; ALFWorld 130/134 after 12 trials, +22 points; self-reflection +8 over episodic memory alone |
| ExpeL (2308.10144) | insight list + pool of successful trajectories | kNN (all-mpnet-base-v2, Faiss); k = 6 HotpotQA, 2 ALFWorld, 2 WebShop, 3 FEVER | gold feedback in the training phase only | HotpotQA ReAct 28.0 -> 39.0 (insights only 36, retrieval only 31); ALFWorld 40.0 -> 59.0 (insights only 50, retrieval only 55); HotpotQA -> FEVER transfer ReAct 63 -> 70 **by insights only** ("we do not have an experience pool to retrieve from"); agent gpt-3.5-turbo-0613, insights by gpt-4-0613 |
| AutoGuide (2403.08978) | context-conditioned guidelines from contrastive success/failure pairs | current context is the key, an LLM picks top-k = 2; no matching context -> no guideline | a context-identification call per step | ALFWorld ReAct 54.5 / ExpeL 59.0 / AutoGuide 79.1; WebShop SR 30 / 35 / 46 (ReAct+Reflexion 51); WebArena-Reddit 8.0 / 21.8 / 47.1; WebShop ablation: context only 36, guidelines without context 37, both 46; k = 0/1/2/3/5 -> 30/42/46/47/43 |
| LEAP (2402.05403) | principles from the model's own mistakes on few-shot examples | appended to every prompt | none at test | GPT-4 vs standard few-shot: DROP +7.5, HotpotQA +3.3 |
| RICP (2407.05682, EMNLP 2024) | teacher insights from student mistakes; task-level clusters + question-level retrieval | per-question similarity retrieval | none at test | CSQA / StrategyQA gains -0.2 to +4.3 points per prompting baseline (maths -0.2 to +7.0); students Qwen-Turbo, GPT-3.5-Turbo; teacher GPT-4-Turbo |
| AWM (2409.07429) | abstract workflows induced from successful trajectories | in the agent's memory/prompt (7.4 induced per example on WebArena, 7.3 on Mind2Web) | online: LM-judged success | WebArena GPT-4: BrowserGym 23.5 -> 35.5 (+51.1% relative), 7.9 -> 5.9 steps; Mind2Web step SR cross-task 36.2 -> 45.1 offline / 43.6 online, cross-website 30.1 -> 33.7 / 33.9, cross-domain 18.6 -> 32.6 / 35.5; concrete retrieved trajectories (Synapse) 30.6 vs AWM 34.6 (gpt-3.5); abstract 45.1 vs rule-based 43.4 |
| Learn-by-Interact (2501.10893) | synthesised trajectories with backward-constructed instructions | agentic retrieval | none at test | up to +12.2% (ICL, Claude-3.5), up to +19.5% (training, Codestral-22B) on SWE-bench, WebArena, OSWorld, Spider2-V |
| Dynamic Cheatsheet (2504.07952) | curated memory of strategies and code | DC-Cu whole memory; DC-RS top-3 by text-embedding-3-small, then synthesis | none (self-judged) | Claude 3.5 Sonnet AIME-24 23.3 -> 50.0 / 46.7, GPQA-D 59.6 -> 61.1 / 68.7, MMLU-Pro Eng 61.2 -> 66.8 / 67.6; GPT-4o Game of 24 10 -> 93 / 99, GPQA-D 57.1 -> 58.1 / 57.1, MMLU-Pro Eng 53.2 -> **44.0** / 51.2; GPT-4o-mini AIME-24 16.7 -> **13.3** / 13.3, GPQA-D 34.3 -> 33.8 / 32.3; tokens per query 370 -> 1,035 (RS) / 1,831 (Cu) |
| Memento (2508.16153) | case bank (state, plan, binary reward) | SimCSE cosine top-K, or a learned Q-function | reward for the online selector | DeepResearcher F1 59.9 -> 66.6; SimpleQA 81.0 -> 84.7; HLE 22.2 -> 26.7; out-of-distribution +4.7 to +9.6 (MuSiQue, Bamboogle, PopQA); K = 0/1/2/4/8/32 -> 59.9/63.6/63.7/64.5/64.1/63.9; planner GPT-4.1, executor o4-mini/o3 |
| ReasoningBank (2509.25140) | items distilled from successes AND failures | gemini-embedding-001 cosine, k = 1 | LLM-as-judge (72.7% agreement with ground truth on Shopping) | WebArena Gemini-2.5-flash: no memory 40.5, Synapse 42.1, AWM 44.1, ReasoningBank 48.8; SWE-Bench-Verified 34.2 -> 38.8 (flash), 54.0 -> 57.4 (pro); k = 0..4 -> 39.0 / 49.7 / 46.0 / 45.5 / 44.4; adding failures: Synapse 40.6 -> 41.7, AWM 44.4 -> **42.2**, ReasoningBank 46.5 -> 49.7 |
| ACE (2510.04618) | playbook of itemised bullets with helpful/harmful counters; delta updates | in context | generator / reflector / curator; with or without GT labels | AppWorld (DeepSeek-V3.1) avg: ReAct 42.4, ICL 46.0, GEPA 46.4, DC online 51.9, ACE offline 59.4 (GT) / 57.2 (no GT), ACE online 59.5; finance avg: base 69.1, GEPA 72.5, ACE offline 81.9 (GT) / 77.1 (no GT), DC online without GT **65.4**; limitation: "Tasks like HotPotQA often benefit more from concise, high-level instructions ... than from long contexts" |
| Xiong et al. (2505.16067, ACL 2026, pp. 623-645) | query/execution records with addition and deletion policies | retrieved demonstrations | a trajectory evaluator | experience-following: output similarity tracks input similarity (Pearson r ~ 1 at high similarity); add-all and coarse evaluators "exhibit flat or declining success rates, suggesting accumulation of flawed records"; "future task evaluations can serve as free quality labels"; history-based deletion helps with a reliable evaluator |
| KATE (2101.06804) | labelled demonstrations | kNN over the input | none | retrieval "consistently outperforms the random baseline"; NQ +45.5% and ToTTo +41.9% (relative) |

What the survey implies for this project:

1. **Big wins need a recurring environment.** ALFWorld +19 to +25 points (ExpeL, AutoGuide), WebArena +8 to +12,
   AppWorld +17, Mind2Web cross-domain +14 to +17. There a memory item encodes a procedure or a state-action
   regularity that recurs across tasks (same website, same app API, same household layouts).
2. **Short-answer QA gains are small** and come mostly from the abstracted part: ExpeL HotpotQA retrieval-only +3
   vs insights +8; LEAP +3.3; RICP -0.2 to +4.3 on commonsense QA; Memento SimpleQA +3.7 F1 with a tool-using deep
   research agent. ACE's authors say HotpotQA benefits more from concise instructions than from long contexts.
   Reflexion's HotpotQA gains need retries of the SAME question with an exact-match success signal, which a
   single-shot test evaluation forbids.
3. **Baselines are weak.** The reported gains are over few-shot or ReAct prompts with no task-card instruction. The
   owner's yardstick (beat a GOOD instruction) is stricter; the project's v8-v11 line already measured +3 to +5,
   not significant, for learned clauses on top of a good instruction.
4. **More memory is not better; unlabelled memory can hurt.** ReasoningBank is best at k = 1 (49.7, then 44.4 at
   k = 4); Memento peaks at K = 4; AutoGuide drops at k = 5 (47 -> 43). Unlabelled curation lost points in DC (GPT-4o
   MMLU-Pro Eng -9.2, GPT-4o-mini AIME -3.4) and DC-online on finance (65.4 vs base 69.1). AWM got worse with
   failures (44.4 -> 42.2). Add-all banks flatten or decline (Xiong et al.).
5. **Transfer goes through abstraction.** ExpeL's only cross-dataset result transfers insights, not cases. AWM's
   abstract workflows beat concrete ones (45.1 vs 43.4) and retrieved concrete trajectories (34.6 vs 30.6).
   AutoGuide's gain comes from conditioning guidelines on an applicability context (37 -> 46 on WebShop).

## 4. Design: a case bank from the v3 failures

### 4.1 What a case is (as piloted, and as it should be)

As piloted: one case per diagnosed TRAINING failure item, written by GLM-5.3 (thinking on, low effort, temperature 0)
from the question, the snippets (clipped to 2,500 characters), the solver's wrong answer(s), the reference answer(s)
and the examiner's code with its meaning. Fields: `situation` <= 220 characters (what the solver can observe, never
the answer), `mistake` <= 160, `lesson` <= 260 (a general instruction that depends only on what the solver sees),
plus a concrete anchor: the question clipped to 150 characters, the wrong answer, the reference. Rendered texts were
611-798 characters (mean 708; measured). The writer validates JSON, lengths and a mechanical leak check (the item's
own reference must not occur in `situation` or `lesson`), re-asks once with the validation error, then a tolerant
pass re-asks up to 4 times and clips at a sentence boundary. Result: 30 of 30 source items gave a case (21 on the
first pass, 9 on the tolerant pass, 4 of those clipped); 68,356 GLM tokens (measured).

As it should be (from the pilot's failure modes):
- **Abstract anchor.** Never the literal reference string ("the reference kept the honorific", not "Sir Isaac
  Newton"). The pilot's concrete anchors leaked an evaluated item's answer (section 5.4). AWM also finds abstract
  beats concrete.
- **Leak check against every pool answer**, not only the item's own: 21 normalised SearchQA answers occur in two pool
  items.
- **An observable `applies_when` predicate** in the v4 conditional-rule form ("when <observable condition>: <bounded
  action>; otherwise <default>"). A case is then a rule plus its provenance; this is what AutoGuide's context key is.
- Source material is the v4 per-ITEM diagnosis (one code per failed item), from the PROPOSAL half only.

### 4.2 Retrieval

Three possible keys, in increasing cost:
1. **Lexical similarity** (BM25 over the question + 800 characters of snippets vs the case's question + situation +
   mistake + lesson; free). Piloted, and **rejected** by the data. On trivia, lexical overlap carries topic, not
   failure type: of the 27 evaluated items that failed in v3, only 14 got a retrieved case with a matching code. One
   "hub" case (c20) was retrieved for 23 of 100 items.
2. **Applicability judge** over the cases' `applies_when` predicates: one GLM call per task (about 3-5k tokens,
   estimated), top-1 or top-2, with **abstention** when nothing applies (AutoGuide's rule; the k-ablations above
   favour k = 1-2). This is D4's predicate machinery reused.
3. **Failure-type classifier first** (D4), then the best case within the code. Its ceiling is bounded by the pilot's
   oracle arm, which used the item's TRUE v3 code: +2 points on the panel at most (section 5.3). For SearchQA's
   dominant codes (D1 extra words, D2 other form) no pre-solve classifier can reach that ceiling, because the code is
   defined relative to the reference answer.

Per benchmark: OfficeQA could key on the cited bulletin issue or table title (29 of 74 items share an issue);
ALFWorld should use AutoGuide's form (state -> guideline), retrieved once per episode or per step; SpreadsheetBench
could key on the instruction's operation type (D3/D14 territory).

### 4.3 Injection within the Skill byte limit

The pilot appended the block to the end of the SearchQA section, before `## OfficeQA`. Its header was "Similar past
cases from training (use a case only if the same situation applies to the current task; the example answers belong
to other tasks):", followed by 2 cases. Measured on the 12,681-byte I-ds Skill: rendered Skills of 14,116-14,419 bytes
(cap 20,000) and +349 prompt tokens per cell (3,765 -> 4,114, +9.3%). For later stages the carried Skill grows, so
the memory block needs its own reserved budget, for example <= 2 cases x <= 800 characters = 1.6 KB per section
(estimated).

**Consequence for the protocol:** the solver text becomes task-dependent. v3 identifies an arm by one frozen text
(`skill_sha256` per cell) and reuses a test evaluation when the Skill is unchanged. A case memory is a **policy**
(bank + retriever + header + k), so the identity must be a policy hash, plus the rendered-text hash and the case ids
on every cell. The pilot recorded both.

### 4.4 Gating without a validation set

1. Build the bank from the proposal half's diagnosed failures (as the analyst's evidence is today).
2. Decide on the **package**, not per case: one paired comparison per step on a **fresh batch** of training items
   never used for case writing at this step (D1's design). Arms: parent; parent + retrieved memory; parent + the
   same bank with **shuffled assignment** (the control for "does retrieval relevance matter", same length and form).
   Accept when the one-sided lower 95% bound of (memory - parent) > 0 and of (memory - shuffled) > 0, plus the C2/C3
   analogues on the regression panels with D8's non-inferiority margins. This removes the per-rule trigger panels
   (MIN_TRIGGER = 4) that starved the v3 rule gate.
3. **Size** (measured SD of per-item differences 0.245, 2 runs per item, one-sided 5%, 80% power): +5 points needs
   about 149 items, +3 points about 412, +2 points about 926. The same-text SD (0.198) gives 97 / 269 / 605. A
   SearchQA step (200-item training draw, 600-item pool) can therefore only accept memories worth about +5 points.
   The pilot and the literature put the plausible effect at 0 to +3.
4. **After acceptance only:** per-case paired tallies from the retrieval log (helpful/harmful counters as in ACE),
   and history-based deletion of net-negative cases at the next step (Xiong et al.: future task evaluations are free
   quality labels). Items return to the pool after the decision (no fixed validation set).
5. **Transfer (owner's yardstick):** cases are retrieved by similarity to the current benchmark's tasks, so a
   SearchQA bank contributes nothing by construction to OfficeQA or the others. Only its abstraction into a rule
   could transfer, which returns to the rule pathway.

### 4.5 Leakage policy

A concrete case states its own item's reference answer, which conflicts with the current mechanical leak check (a
pool answer in the rule text drops the rule). Measured in the pilot: 3 of 100 evaluated items had their reference
inside a retrieved case. Recommended: abstract anchors only, and a leak check of every case against all pool answers
(not only its own item's). The current policy then holds unchanged. LiveMath has a specific clash: a case teaching
the meta option ("a stronger result can be proven") quotes option text and hits the option-text leak rule, the same
registered contradiction D7 analyses.

### 4.6 Cost per step (estimated from measured unit costs)

- Case writing: 2.28k GLM tokens per failed item on SearchQA (68,356 / 30, measured). I-ds failed items per stage:
  SearchQA 54, OfficeQA 59, LiveMath 75, SpreadsheetBench 43, ALFWorld 32. With longer OfficeQA/ALFWorld contexts,
  that is about 1-1.5M GLM tokens per chain for all five banks.
- Applicability judge: about 4k GLM tokens per task -> about 0.8M per 200-item batch.
- Package gate, SearchQA: 150 items x 2 runs x 3 arms x 4.1k tokens = about 3.7M solver tokens per step (pilot cells
  measured 4,048 tokens each).
- Test-time overhead: +349 tokens per SearchQA cell (+9.3%, measured). ALFWorld re-sends the Skill on every call
  (31 per I-ds episode), so +150-350 tokens per call for short guidelines, or +2-8k per call for full trajectory
  demonstrations.

## 5. Pilot (measured)

### 5.1 Set-up

- Bank: 30 cases (above) from the 30 items of the I-ds **proposal** half that failed in either chain at v3 stage 1.
  Codes: D1 11, D2 8, D5 5, D4 3, D3 1, noncompletion 1, other 1.
- Evaluation: the 100 I-ds **check-half** items (overlap with case sources: 0), 2 runs each, 2 arms: **parent** =
  the I-ds step-0 Skill (12,681 bytes; digest `ee9b737f...`, identical to the v3 cells' `skill_sha256`); **cases** =
  parent + header + top-2 BM25 cases (k1 1.5, b 0.75).
- Solver: deepseek-v4-flash through the PJLAB token route, thinking disabled, temperature 0 (the client is identical
  to the v3 snapshot). Prompt: contract-first-v2, reproduced from the frozen v3 `backends.solve` (system = fixed
  sentence + answer contract + "Frozen skill guidance" + Skill; user = JSON {question, context}). Score: the official
  `evaluate(response, answers)["em"]`, the same call v3 makes. **Deviation:** max_tokens 8,192 instead of 32,768.
- Execution: new machine, 6 workers, 400 cells, all delivered (394 first try, 6 second). Two cells hit the 8,192 cap:
  both runs of the parent on item `07623a13`, which passed both v3 runs. The main pilot ran 19:04-19:28 on 2026-10-20; the oracle arm ran 19:12-19:15, concurrently.

### 5.2 Main result

| Comparison (100 items, 2 runs; truncation = fail, as v3) | up / down / ties | mean difference | 95% bootstrap CI | sign test p |
|---|---|---|---|---|
| **cases - fresh parent** | **5 / 7 / 88** | **-0.010** | **[-0.060, +0.040]** | 0.77 |
| fresh parent - v3 parent (same text: noise reference) | 3 / 7 / 90 | -0.030 | [-0.070, +0.005] | 0.34 |
| cases - v3 parent | 5 / 11 / 84 | -0.040 | [-0.085, +0.005] | 0.21 |
| cases - fresh parent, truncated runs excluded (99 items) | 4 / 7 / 88 | -0.015 | [-0.061, +0.035] | 0.55 |
| cases - fresh parent, without the 3 answer-overlap items (97) | 4 / 7 / 86 | -0.021 | [-0.067, +0.026] | - |

Arm accuracy: parent 149/200 = 0.745, cases 147/200 = 0.735. Cell level (same item and run): 140 both pass, 44 both
fail, 9 parent only, 7 cases only. The case block changed the normalised final answer in 22 of 200 runs (15 items).

By the item's v3 pattern (the cases arm helps where the parent failed, and hurts where it was right):

| v3 pattern | items | up / down | parent mean -> cases mean |
|---|---|---|---|
| both runs passed | 73 | 2 / 5 | 0.973 -> 0.945 |
| mixed | 9 | 2 / 1 | 0.333 -> 0.444 |
| both runs failed | 18 | 1 / 1 | 0.028 -> 0.028 |

### 5.3 Oracle bound (diagnostic, not a policy)

On the 27 check-half items that failed at least once in v3, the two injected cases were chosen by the item's OWN
dominant v3 diagnosis code (BM25 breaks ties), 2 runs, 54 cells. This bounds code-matched retrieval from above,
because the code is not observable before solving.

| Comparison (27 v3-failed items) | up / down / ties | mean difference | 95% CI | p |
|---|---|---|---|---|
| oracle-code cases - fresh parent | 3 / 1 / 23 | +0.074 (0.130 -> 0.204) | [-0.019, +0.204] | 0.63 |
| lexical cases - fresh parent (same items) | 3 / 2 / 22 | +0.037 | [-0.056, +0.148] | 1.00 |
| oracle, the 24 items where both cases match the code | 3 / 1 / 20 | +0.083 | [-0.021, +0.229] | 0.63 |

Projected to the 100-item panel, assuming no harm on the 73 items not run with the oracle arm: +2.0 points
(estimated). That is below what a single gate step could detect (section 4.4), even before the harm the lexical arm
caused on passing items.

### 5.4 Mechanism (measured, from the discordant items)

- **Contradictory form lessons applied out of place.** c20 comes from an item whose clue names "Chester" (reference
  "Arthur"). Its lesson: "When the clue already supplies the first name ..., respond with just the surname". It was
  retrieved for 23 of 100 items and produced "Reagan" (reference "Ronald Reagan", both runs), "Alley" ("Kirstie
  Alley", both runs) and "Bush" ("George Bush", one run). c10 ("give the shortest identifying form, usually the
  surname alone"; source reference "Fragonard") produced "Kahlo" for "Frida Kahlo" (one run). The bank also holds the opposite
  lessons: c28 ("prefer the fullest standard form, including honorifics"; "Sir Francis Drake") and c03 ("include the
  title if the reference likely does"; "Sir Isaac Newton").
- **The one robust gain is a leak.** Item `4b2b7d9b` (reference "(Sir Francis) Drake") flipped 0 -> 1 in both runs.
  The retrieved c28's anchor states its own reference "Sir Francis Drake", which normalises to this item's answer
  (one of the 21 shared answers). Two more evaluated items had their answer inside a retrieved case ("Dalai Lama" via
  c18's anchor; "the leaves" via c22's text), but both arms passed them anyway.
- The remaining "up" items are not attributable to the retrieved lesson: "Marie Antoinette" vs "Marie-Antoinette"
  arrived with two unrelated cases, and the parent's two truncations on `07623a13` were scored as fails.
- This is the experience-following effect of Xiong et al.: the solver applies retrieved lessons whether or not the
  situation matches, despite the header's "use a case only if the same situation applies".

### 5.5 Power

Item-level SD of (cases - parent) = 0.245, measured. The 95% CI half-width at 100 items x 2 runs is about 5 points.
Detecting +3 points at 80% power needs about 412 items (section 4.4).

### 5.6 Tokens (measured, including retries)

Main pilot 1,619,278 (prompt 1,575,804 + completion 43,474; 4,048 per cell); oracle arm 226,144 (54 cells); GLM case
writing 54,891 + 13,465 = 68,356. **Total 1,913,778.** No further paid call was made in this session.

### 5.7 Limitations of the pilot

One benchmark (SearchQA), one chain's halves (I-ds), 30 cases, lexical retrieval only, concrete anchors, 2 runs,
max_tokens 8,192 (two parent truncations on one item; the verdict is the same under either policy), no
shuffled-memory or placebo arm, one solver. The oracle arm was run only on the 27 failed items, so its harm on
passing items is unmeasured. None of these can turn a 5-up / 7-down result into a detectable gain: even the oracle
bound is +2 points.

## 6. Risks

1. Answer leakage through concrete anchors and shared pool answers (measured: 3/100 evaluated items; the only robust
   gain was a leak).
2. Over-application (experience-following): measured harm concentrated on items the parent already solved (2 up /
   5 down on 73 both-pass items).
3. Inconsistent reference conventions make form lessons self-contradictory; a bank cannot fix annotation
   inconsistency (47% of I-ds SearchQA failures are form errors in both directions).
4. Protocol identity: a task-dependent prompt breaks the one-text-per-arm identity and the reuse of unchanged test
   evaluations; it needs a policy hash and per-cell case ids.
5. Power: a single-step package gate detects only effects >= about +5 points on SearchQA-sized batches.
6. Cost: an applicability judge per task; on ALFWorld every call carries the memory (31 calls per I-ds episode).
7. Strategic: a case bank is local to its benchmark by construction, so it cannot produce the cross-benchmark
   generalisation the owner treats as the metric. It also does not exercise the co-evolution (generated-task) pathway.

## 7. Recommendation

1. **Do not replace rules with case memory in v5** for SearchQA, OfficeQA or LiveMath. The SearchQA measurement is
   null-to-negative, the oracle bound is about +2 points, the failure structure is form-dominated and inconsistent,
   the pools are singleton families, and cases do not transfer across benchmarks.
2. **Import three memory mechanisms into the rule pathway** (cheap, and aligned with v4's conditional template and
   D4):
   (a) every rule carries an observable applicability predicate and the solver abstains when it does not hold
   (AutoGuide);
   (b) accepted rules keep helpful/harmful paired tallies from later steps' training runs, with history-based
   deletion (ACE; Xiong et al.);
   (c) examples inside rules are abstract, and each rule is leak-checked against every pool answer (the pilot's
   realised leak).
3. **Keep the case writer and the oracle-code probe as a headroom diagnostic** (cross-reference D9). On SearchQA, for
   about 70k GLM + 230k solver tokens, they bound what failure-type-matched advice can add on that benchmark's
   failed items.
4. **If the paper needs a memory baseline, run it on ALFWorld only**, as a within-benchmark comparison (cross-reference
   D14). The literature is strongest there (ExpeL 40 -> 59, AutoGuide 54.5 -> 79.1), and 45 of 56 I-ds failures are
   search loops. Use short state-conditioned guidelines or leave-one-out successful trajectories by task type, and
   arms parent / memory / shuffled memory. 57 items x 2 runs x 3 arms is about 36M tokens with short guidelines, up to
   about 70M with full trajectories (estimated from 105,651 tokens per I-ds episode). Report it as within-benchmark
   evidence, not as generalisation.
5. OfficeQA is the only QA benchmark with partial document recurrence (29 of 74 items share a bulletin issue). A
   same-document case retrieval there is an untested hypothesis. With 74 items it cannot reach the power in section
   4.4; do not prioritise it.

## 8. References (all checked in this session)

- Shinn et al., Reflexion: Language Agents with Verbal Reinforcement Learning, arXiv:2303.11366.
- Zhao et al., ExpeL: LLM Agents Are Experiential Learners, arXiv:2308.10144.
- Fu et al., AutoGuide: Automated Generation and Selection of Context-Aware Guidelines for LLM Agents, arXiv:2403.08978.
- Zhang et al., In-Context Principle Learning from Mistakes (LEAP), arXiv:2402.05403.
- Sun et al., Retrieved In-Context Principles from Previous Mistakes (RICP), EMNLP 2024, arXiv:2407.05682.
- Wang et al., Agent Workflow Memory, arXiv:2409.07429.
- Su et al., Learn-by-Interact, arXiv:2501.10893.
- Suzgun et al., Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory, arXiv:2504.07952.
- Zhou et al., Memento: Fine-tuning LLM Agents without Fine-tuning LLMs, arXiv:2508.16153.
- Ouyang et al., ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory, arXiv:2509.25140.
- Zhang et al., Agentic Context Engineering (ACE), arXiv:2510.04618.
- Xiong et al., How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior,
  Proceedings of ACL 2026 (Vol. 1), pp. 623-645, arXiv:2505.16067.
- Liu et al., What Makes Good In-Context Examples for GPT-3? (KATE), arXiv:2101.06804.
- Project code read: frozen v3 snapshot `/data/coevo5-20261019-v3-source-f` (`skillopt/continual_eval/backends.py`
  solve/_response, `skillopt/coevo5/outcomes.py` row 5, `skillopt/coevo5/data.py` pool/training_items,
  `skillopt/envs/searchqa/evaluator.py`, `scripts/weak_solver_probe.py` Client).

## 9. Artifacts

New machine `/data/feasibility/D2/`: `collect.py`, `v3_s1_train_rows.json`, `searchqa_train200.json`,
`skill_I-ds_step0.txt`, `skill_E-ds_step0.txt`, `build_cases.py`, `retry_dropped.py`, `cases.json` (30 cases),
`cases_dropped.json`, `cases_dropped_final.json`, `cases.log`, `retry.log`, `pilot.py`, `analyse.py`,
`oracle_probe.py`, `pilot/{retrieval.json, cells.jsonl, analysis.json, analysis.log, pilot.log, retrieval_oracle.json,
cells_oracle.jsonl, analysis_oracle.json, oracle.log}` (the first attempt's analysis files keep its superseded
numbers), and `verify/` (this report's independent re-analysis: `facts.py`, `reanalyse.py` + `reanalysis.json`,
`discordant.py`, `leaks.py`, `power.py`, `stages.py`, `officeqa_docs.py`, `officeqa_issues.py`, `shared_answers.py`
and their logs).
Mac: `/private/tmp/claude-501/-Users-dulin-Documents-Paper-SkillOpt/e7258b97-b430-4dd5-959d-eb871e7c777f/scratchpad/feas/D2/`
holds this `report.md`, the superseded `report_draft.md`, `scripts/`, `data/` (copies of the above), `verify/` and
`acl2026_memory_mgmt.txt` (text of Xiong et al.).
