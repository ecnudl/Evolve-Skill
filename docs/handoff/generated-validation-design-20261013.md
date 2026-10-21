# Design contract (2026-10-13): generated test tasks instead of a validation set for the Rubric+Research method

Owner's direction of 10/13 00:25: go back to the Rubric+Research version (learning v10: Rubric -> probe -> Research
verifier, analyst, validation gate) and change one thing -- the gate should not need a validation set; it should
be fed by GENERATED test tasks. Written before any stage with generated validation ran.

## 1. What changes and what does not

Nothing in the learner changes. `skillopt/continual_learning/*` (verifier, updater, the two-pass sign-test gate
with at most three iterations) is the frozen v10 code. The gate already takes its tasks from the manifest's
selection role; until now the stage tool filled that role with the canonical validation partition. New:

* `scripts/generate_searchqa_tasks.py` writes test tasks from a stage's TRAINING tasks only (same seed, same 128
  tasks): for each training task the writer sees its public fields (question, retrieved snippets) and writes up to
  two new clue-style questions about OTHER facts in those snippets, with the answer as a verbatim span and a
  supporting quote; deterministic filters (verbatim answer and quote, answer not in the question, lengths, no
  duplicate of a development or earlier generated question) and an independent reviewer call (supported, unique,
  shortest natural form) decide admission. No reference answer, no validation / test / reserve item and no solver
  outcome enters a prompt; no filter looks at a solver's answer, so the pool is not conditioned on being solved.
  A generated task = the source task's snippets + the new question + the proposed answer as its only reference;
  it is scored by the frozen exact-match scorer.
* `run_fivebench_g_stage.py prepare --generated-val <generation dir>` (instead of `--val-source`): binds a
  COMPLETED generation made from exactly this stage's training tasks as the selection set. The stage record says
  `selection_source: generated_from_this_stage_training_tasks`; no canonical validation data is read.

So "validation without a validation set" here means: without a separately supplied canonical validation set --
every real labelled task the stage uses is a training task, and the gate's tasks are synthesized from them.
Synthetic labelled selection tasks still exist; the gate does not run without data, and the generated tasks are
not independent of the training tasks (same snippets). Questions written from the same training task are one
FAMILY for the gate's sign test (one sign per source task, not per question). The reviewer also sees the source
question and rejects paraphrases of it.

## 2. What has to be shown (and can fail)

A generated gate is only useful if performance differences on generated tasks track differences on real tasks.
Known risks: generated questions may be easier (the answer is a verbatim span by construction), their reference
strings follow the writer's conventions rather than the dataset's, and they share snippets with training rows.

* **E1 -- do generated tasks rank Skills like real tasks do?** The twenty frozen Skill texts of the learn-from-B
  study (no Skill, two initial instructions, fifteen one-step Skills, the two validation-gated methods' Skills)
  solve the generated tasks with the panel evaluation tool; the contrasts are compared with the same contrasts on
  the 1,000 fresh real tasks. Descriptive: pass rate without a Skill (a ceiling would leave the gate no power),
  the sign and size of learned-minus-empty and learned-minus-initial-instruction on both task kinds.
* **E2 -- the method itself.** One learning-v10 `rubric_research` SearchQA stage with seed 20261006 (the training
  rows of the original v10 SearchQA stage) and the generated tasks as its selection set, parent empty. (A fresh
  run against the historical v10 stage cannot isolate the effect of the gate's source -- the candidates differ --
  so the comparison is descriptive.) Read: which
  steps the gate accepts (the original stage with the real validation partition accepted step 0 with 33 wins and
  2 losses and rejected steps 1 and 2), and then the resulting Skill against the original v10 Skill and no Skill
  on real fresh tasks.

Interpretation fixed now: E1 and E2 are development evidence on one domain. If generated tasks show a ceiling or
do not reproduce the real contrasts, the generator (not the learner) is what has to change, and that is reported
as such. Agreement on SearchQA does not show that generated validation works on BigCodeBench or KOR-Bench: those
need their own generators (executable tests for code; the existing rule-instance generator for KOR-Bench) and are
not built yet.

## 3. Disclosures

Generated tasks reuse training snippets; the writer and the reviewer are the same model as the solver; one
generation per seed, no selection among generations; the first generation run is also the generator's first real
exercise (a stop is an engineering finding).

## 4. Execution notes

01:17-02:08 (queue v1): the generation and the E2 stage ran as planned (168 accepted tasks in 112 source
families; stage `searchqa-v10gen-a` completed with step 0 accepted). 03:00: queue v1 was stopped by the operator
at 02:57 while it waited for ten quiet minutes before the first evaluation run (no run in progress, nothing
prepared). The E2 read and E1 run in queue z1 with the same snapshot, arms, blocks and retry rule; a run starts
after twelve consecutive successful probes (about two minutes) instead of sixty, for the reason given in section
12 of the learn-from-B memo. No evaluation outcome existed when this was written.

Scope of E1 as queued (queue v1 at 01:17, unchanged in z1; no evaluation outcome existed): section 2 names the
twenty Skill texts of the learn-from-B study; the queue runs TEN of them -- `empty`, `bhand`, `bzero`, the five
one-step Skills learned from the empty Skill (`le23`..`le27`), `old_v10` and `old_v9` -- on the first 150 of the
168 generated tasks (six blocks of 25 in generation order; the last 18 are not evaluated). The contrasts compared
with the fresh real tasks are therefore `bhand`/`bzero`/`le`/`old_v10`/`old_v9` minus `empty` and `le` minus the
two initial instructions; the ten Skills learned on top of an initial instruction are not part of E1.

Review of queue z1 (Codex, 03:02-03:09, before the parts concerned started): three required findings. (1) The
cross-benchmark part read a run's state from a text match; it now reads the SEALED records (result bound to
`cross.json` by `cross_hash`, exact version and status) and halts a direction on any other state. (2) Exit states:
the cross-benchmark part and E1 now exit with an aggregated status; the master script was already running and is
NOT changed, so the `(exit N)` field of its log is meaningless and is not read by anything -- part logs and the
tools' sealed statuses are the record. (3) E1 could have skipped blocks silently; its six blocks are now written
and verified as a whole or the part halts. Confirmation review: findings 1 and 3 closed, the master's field
accepted as a disclosed non-blocking defect, GO. The scripts as launched at 03:01 are kept on the machine as
`w3.sh.as-launched-0301` and `v1c.sh.as-launched-0301` (neither ran).

## 5. Replication of E2 on two more seeds (written 03:15, after the first history was read, before any new run)

What was known: the E2 stage's gate actions (step 0 accepted, step 1 rejected at the screen, step 2 not reached)
and the E2 read on 250 fresh real tasks (one history): `v10gen` 214/250, `old_v10` 204 of 243 known, `bzero`
207/250, `empty` 172/250; `v10gen` - `old_v10` +0.021 (task-level interval [-0.008, +0.050]), `v10gen` - `bzero`
+0.028 ([+0.005, +0.051]). One history cannot separate the gate's source from the luck of one set of candidates,
so the same pipeline is repeated on the next two seeds, 20261007 and 20261008 (no choice among seeds), queue z2:

* per seed: generation from that seed's 128 training tasks (same generator, two questions per task), then the
  frozen learning-v10 `rubric_research` stage with `--generated-val`, parent empty, learn only;
* evaluation `e2b-r01..r10` on the same 250 fresh tasks, all arms in the same runs: `empty`, `bzero`, `old_v10`,
  `v10gen` (seed 20261006, measured a second time) and every new history that completed (`v10gen07`, `v10gen08`).

Reading (fixed now): per history, the gate's actions and the generated tasks' counts; group `vg` = the completed
generated-gate histories. With three histories the crossed interval of the learn-from-B memo applies to `vg` -
`bzero`, `vg` - `empty` and `vg` - `old_v10`; with fewer, only per-history task-level intervals are given and the
result stays descriptive. Every history is reported whatever it shows, including a stage that accepts nothing (its
Skill is then the empty Skill) or stops. The first read of `v10gen` stays in the record; the second measurement is
reported next to it, not instead of it. There is still only ONE real-validation counterpart (`old_v10`, seed
20261006): real-validation stages for the new seeds are not part of this queue, so "generated gate versus real
gate" remains a single descriptive pair. No test data; development evidence on one domain.

Launch review of queue z2 (Codex, 03:15-03:17): no required finding, GO. Its reading of this section, adopted
here: the replication is a prospective extension decided AFTER the first result, not an independent three-history
confirmation; the report keeps both measurements of the first history, names the 250 reused tasks, separates
planned / completed / accepted-update histories, and gives denominators, missing outcomes, repetitions and costs.
A completed stage without an accepted update enters as the empty Skill (a difference from the `empty` arm is then
sampling, not learning). The quiet window is checked before a run is submitted; the run may then still wait for
the shared lock.

## 6. E3: the same learner starting from a zero-shot initial instruction (written 06:30, before any E3 stage)

What was known. E2 (first history, read at 03:12): the Skill gated on generated tasks minus the one gated on the
validation partition is +0.021 with a task-level interval of [-0.008, +0.050] -- the difference is unresolved
(neither equivalence nor non-inferiority is established) -- and most of either Skill's gain over the empty Skill
is also given by the zero-shot instruction `bzero` (`bzero` - `empty` +0.140; `v10gen` - `bzero` +0.028
[+0.005, +0.051], one history; `old_v10` - `bzero` +0.004). The two replication stages accepted step 0 as well; their evaluation was
running. From the other queues (read 06:15): one-step Skills learned from the empty Skill are level with `bzero`
on the same tasks (`le` - `bzero` -0.008), and two code-only Skill texts lift SearchQA by six to seven points over
the empty Skill. A gate whose parent is the EMPTY Skill therefore also passes gains that any careful instruction
gives. The question for the method the owner wants to return to: **with generated validation, what does the
Rubric+Research learner add on top of a reasonable initial instruction?**

Runs (queue z4, snapshot `20261013-q` = `p` plus one change in the stage tool: a fixed-text parent is accepted
outside learning v11 only together with `--generated-val`, for the SkillOpt and Rubric+Research learners; diff
`generated-validation-fixed-parent-20261013.diff`; the frozen learner is untouched; such a stage has no test
cell and is read only with the panel evaluation tool):

* `searchqa-v10gen-b06`, `-b07`, `-b08`: the frozen learning-v10 `rubric_research` stage with
  `--parent f:<bzero>` and `--generated-val` on the generated sets `gen06`, `gen07`, `gen08` already made for E2
  (same seeds, hence the same 128 training tasks per seed as the from-empty histories). Learn only.
* evaluation `e3-r01..r10` on the 250 tasks R01..R10, all arms in the same runs: `empty`, `bzero`, the three
  from-empty generated-gate Skills (`v10gen`, `v10gen07`, `v10gen08`), every from-`bzero` stage that completed
  (`vb06`, `vb07`, `vb08`), `old_v10`, `old_v9`.

Reading (fixed now). Per history: the gate's action at each step -- the first thing this run shows is whether
anything is accepted on top of `bzero` at all. A completed stage without an accepted update enters the evaluation
as `bzero` itself (its difference from the `bzero` arm is then sampling, and is reported as such). Group `vb` =
the completed from-`bzero` histories, `vg` = the from-empty ones. Primary: `vb` - `bzero`. Secondary: `vb` - `vg`
paired by seed, `vb` - `old_v10`, `vb` - `old_v9`. With three histories and 250 tasks the crossed interval is wide
(t with two degrees of freedom): "learning adds to the instruction" is claimed only if the crossed interval of
`vb` - `bzero` lies above zero, "adds less than three points" only if its upper limit is below +0.03, and anything
else is "not resolved" with the estimate and the per-history values given. As in the learn-from-B memo, either
claim also needs the planned denominator of 250 tasks with at least 225 jointly known, all three histories
completed, and missing-outcome bounds on the same side as the claim; if any of these fails the result is
descriptive. Whatever it shows, this is exploratory evidence on development tasks that have been read several
times tonight, not a confirmation. Expected in advance: not resolved unless the effect is large; the gate's
actions are the main information.

Disclosures. Decided after the readings listed above. `bzero` was generated once from a public task card (no task
outcome). The generated sets are reused: they were the selection sets of the from-empty stages and select again
here: selection data both times, never the data a learned Skill is judged on (the first 150 tasks of `gen06` are
also the tasks of the diagnostic E1, which measures the generated tasks themselves, not a selection). On generated
tasks the parent is now `bzero`, which is expected to be closer to the ceiling than the empty Skill (empty: 0.77
to 0.81); its actual pass rate on each generated set is read from the stage records and reported with the gate's
actions. R01..R10 are reused
development tasks. One domain; no test data; nothing is deployed.

Review of E3 (Codex, 06:21-06:27): first round NO-GO with four required findings -- learning v8 was admitted by the
relaxed guard; the `test` command and the stage report assumed a no-update stage's parent had been measured; "at
least as good" overstated E2; the reading contract did not restate the denominator, coverage, history and
missing-outcome conditions. All four are fixed above and in the diff (the guard names v9 / v10, a fixed-parent
v9 / v10 stage refuses `test`, the report says its parent was not measured); the test now also checks that the
gate's parent on the generated tasks is the fixed text and that a rejected candidate leaves that text in place.
Confirmation review (06:26-06:29): all four findings closed, no new required finding; code GO, queue z4 GO for the
reviewed snapshot and unchanged script. Noted limitation: the two Linux launch wrappers still assume a test cell
and must not be used for these stages (z4 calls prepare / learn / status directly). Released 06:29; the queue
then waits for the fresh-task part of queue z1 to end.
