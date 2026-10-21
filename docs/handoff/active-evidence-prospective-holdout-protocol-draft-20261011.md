# DRAFT (2026-10-11, afternoon; NOT executed, NOT frozen): the one prospective hold-out read for learning v11

Status: a proposal for the owner. The owner approved ONE read on the condition that its hold-out status cannot be
questioned. Nothing here has been run; no test or reserve task has been read for it. Direction review by Codex
(GPT-6-Astra, ultra, read-only) is incorporated: its main objection is that the canonical test split alone cannot
carry that condition.

## 1. Why the canonical test split alone is not enough

* Its aggregate scores have been read before and development continued afterwards: the F baseline table (10/6),
  the v8/v9/v10 chains (10/7-10/8) and the v11 `r`/`t` stages on BigCodeBench (10/9). No test task content ever
  entered learning, but method choices were made by people and agents who had seen those scores. New learning
  seeds do not erase that.
* The split manifest itself says so (`data/fivebench_split/split_manifest.json`, field `exposure`): "held out from
  study F" is not "historically unexposed". For SearchQA every native item (today's val, test AND reserve)
  received predictions in the project's earlier GPT reproduction of native SkillOpt.

So a read of the canonical test can be an honest *prospective secondary* evaluation (everything frozen first, one
read, disclosed history), but not the unquestionable confirmation.

## 2. What data could carry the condition (zero-call audit of 10/11)

| Domain | Candidate primary hold-out | Exposure found | Status |
|---|---|---|---|
| KOR-Bench | `reserve` = 250 tasks = 25 rules never in train/val/test | no solving record found; call bodies scanned on 10/11 evening: no fingerprint hit (22 of 25 rules covered; audit below) | candidate primary hold-out |
| BigCodeBench | `reserve` = 128 tasks | no solving record found; call bodies scanned on 10/11 evening: only single-phrase collisions for 6 tasks (audit below); 4 tasks shown to a research subagent on 9/25 | candidate primary hold-out, 124 tasks after exclusion |
| SearchQA | none inside the native subset (all of it was predicted earlier) | recorded exposure | needs a NEW sample from the original SearchQA corpus outside the native SkillOpt subset (a download; not started) |
| SpreadsheetBench | no reserve; test 280 = native test | "earlier use outside study F not audited" | secondary only, unless audited |
| ALFWorld | no reserve; test 134 = valid_unseen | same | secondary only, unless audited |

**Exposure audit of 10/11 (15:45; read-only, zero model calls, no task content displayed; delegated agent, two
key claims spot-checked by hand; machine-readable result on the development machine:
`/root/audit-reserve-20261011/result.json`).** Searched 389 top-level entries under `/root` (559,006 text/JSON
files) by three nets: every spelling of task / family ids; every 64-hex token against 26,293 reference task hashes
built from the canonical panels; 40-character text fingerprints of reserve prompts and rules.

* BigCodeBench reserve (128): no solving record of a reserve task was found in the searched material (prompt-level
  exposure is not excluded: the call-cache bodies were not read); 112,544
  `task_hash` fields resolve to train / val / test and 0 to reserve. ONE documented non-solver exposure: on 9/25 a
  Dataset Viewer lookup showed solution / test excerpts of BigCodeBench/0..17 to a research subagent
  (`docs/results/bigcodebench-readiness-20260925.json`); four of those are in reserve (BigCodeBench/1, 2, 4, 16) and
  must be excluded from a primary hold-out (124 tasks remain).
* KOR-Bench reserve (250 tasks, 25 rules): no solving record found either (prompt-level exposure likewise not
  excluded); 103,059 `task_hash` fields resolve to train / val / test
  and 0 to reserve. The public upstream checkout on the machine contains the dataset and third-party models'
  published outputs (not produced by this project); the project's KOR pilots used train rules only.
* Limits, so this is not overstated: the bodies of the API call caches (323,012 files, 4.0 GB -- where analyst,
  diagnoser and Research prompts live) were not read; for them the evidence is indirect (every adjacent panel,
  plan, evaluation and verifier record is train / val / test). Fingerprints covered all 128 BigCodeBench tasks but
  only 21 of 25 KOR rules. Archives, binaries, another project's tree, deleted runs, other machines and the
  solver model's pretraining (both datasets are public) are out of reach. Before the read, the call-cache bodies
  should be checked by hash of the reserve task texts (zero-call), and the result sealed with the protocol.

**Follow-up of 10/11 evening (zero-call; ids and counts only; `/root/audit-reserve-20261011/fp_api_agg.json`,
`fp_api2_agg.json`, `s23.out`).** The call bodies have now been scanned: every directory named `calls` /
`call_intents` under `/root` (98,376 directories, 510,216 files, 6.09 GB) with 1,274 in-memory text fingerprints
(40-character windows of reserve prompts / rules / questions that occur in no non-reserve task text; 80 of them
positive controls from the training part).

* KOR-Bench reserve: 0 files carry a rule or question fingerprint.
* BigCodeBench reserve: fingerprints of 6 tasks (80, 274, 282, 290, 704, 825) occur in 138 files, each time as ONE
  window (two for task 80) out of the task's 6-14 unique windows -- single-phrase collisions, not a prompt that
  contains the task. Positive control: in 2,353 of 2,355 file-by-task hits of training-task fingerprints ALL of the
  task's unique windows are present (the other two: 70-79%).
* Coverage: all 128 BigCodeBench reserve tasks; 22 of the 25 KOR reserve rule families (21 by rule text, one by
  question text). The operation rules whose rule text is a one-line formula have no 40-character window; an
  exact-string pass (`s25_short_rules.py`, `fp_short_agg.json`) covered them: the whole rule text and all 40 whole
  question texts of the four reserve operation rules without a rule fingerprint (5, 9, 11, 15; three spellings each,
  131 patterns absent from every non-reserve text) have 0 hits in 510,411 files, while the same construction for
  six training operation rules is found for all six (rule text for five of them, 7-10 of 10 questions each) -- the
  exact-string net is not perfectly sensitive for rule texts. All 25 reserve rules now have a text-level check.
* KOR rule texts: none of the 125 rule families share a normalized rule text; no training-rule pair and no reserve
  rule shares 20% of its 8-word shingles with another part, except boilerplate among cipher rules (6-18% of a
  reserve cipher rule's shingles; one val rule shares 22% with a reserve cipher rule).

So, within fingerprint coverage, no prompt-level exposure of a reserve task was found. Still out of reach:
archives, binaries, another project's tree, deleted runs, other machines, pretraining.

## 3. What is evaluated: one multi-arm read (no need to freeze the method into one arm first)

Policies, each complete (learning + its own decision; a parked policy is evaluated as what it deploys, i.e. the
parent): P0 no Skill; P1 pass/fail one step + decision v2; P2 diagnosis package one step + decision v2;
P3 pass/fail one step, ungated (always deployed). If the in-sample shadow pilot of 10/11 survives its falsification
runs, P4 = pass/fail one step decided on training rows only. **Added 10/11 evening: PG = a fixed, hand-written,
dataset-agnostic generic instruction (no learning; the frozen text of
`active-evidence-generic-control-design-20261011.md`).** Until 10/11 every v11 comparison was against the empty
Skill only; the read keeps PG whatever tonight's development controls show, and "learned policy minus PG" is
reported next to "learned policy minus P0" for every learned policy. The primary contrast is named in advance (proposal:
P1 - P0 per domain); P2 - P1, P3 - P1 and P4 - P1 are secondary. This lets the single read answer "does the
simple policy generalize", "does the diagnosis package add anything" and "does the decision need a reserved pool"
at once, instead of spending the read on whichever arm was frozen.

## 4. To be sealed BEFORE the read (one record, hashed; nothing released until every cell has finished)

Code snapshot hash and package/tool hashes; model, scorer, runtime and retry/missingness rules; domains; learning
seeds never used in development (proposal: 20261101-20261103) and the number of histories; budgets; the final
Skill hash of every (policy, seed) cell -- learning finishes first, on train only; the hold-out task list hashes;
the contrasts, their statistics (task-level paired difference with a Tango interval where families are single
tasks; equal-family mean with a t interval for KOR), multiplicity handling and what counts as success or failure
for each; the exposure audit of section 2; the disclosure text of section 1.

Evaluation mechanics: every distinct final Skill and the no-Skill control solve the same hold-out tasks in an
interleaved, balanced order under one model-service identity (not accepted-updates-only against a historical
no-Skill number, which is what the current test runner does -- that runner must be extended and reviewed first).

## 5. Cost (serialized stages, one at a time)

Learning: 3 domains x 3-4 policies x 3 seeds; P1/P3 share one learning history per seed, P2 needs its own:
about 6 histories per domain = SearchQA 1.5 h, BigCodeBench 4 h, KOR 9 h. Hold-out solving: KOR 250 tasks is
about one hour per distinct Skill, BigCodeBench 124 eligible tasks (after the exclusions) about 15 minutes, SearchQA about 10 minutes per 400.
Roughly 25-30 hours in total unless the hold-out cells may run outside the single stage lock.

## 6. Decisions the owner still has to make

1. Accept "candidate reserve hold-outs (KOR, BigCodeBench; subject to the outstanding call-cache audit and the
   disclosed limitations) + a new SearchQA sample as PRIMARY, canonical test as
   disclosed SECONDARY" -- or spend the one read on the canonical test alone and accept the disclosure.
2. The arm list and the primary contrast of section 3.
3. Whether SpreadsheetBench / ALFWorld are in (they need the wiring listed in
   `active-evidence-sheet-alf-wiring-notes-20261011.md` first) and whether their tests count as primary.
4. Whether downloading a fresh SearchQA sample is acceptable.
