# Design contract (2026-10-12): how much does one learning step add to a reasonable initial instruction?

Phase 1 of work package 1 of `expert-feedback-digest-and-plan-20261012.md` (owner's go-ahead on 10/12: "verify
first"). SearchQA only, evaluated on FRESH tasks: 1,000 of them, about four times the earlier holdouts.
Written before any of its stages ran. Snapshot `20261012-l` = `k` plus three new scripts (no change to the stage
tool or to the `active_evidence` package).

## 1. Question

Every earlier v11 number compared a learned Skill with the EMPTY Skill, on 242-task development holdouts that
resolve only differences of five to six points. The controls of 10/11-10/12 showed that a three-line generic
instruction recovers 60-80% of the one-step gain on SearchQA and that the remaining 3-5 points, and one step on
top of the generic text (+2.9, one history), are not established. The question that decides the project's claim:

> Starting from a reasonable initial instruction B, how much does one learning step from task experience add
> over B itself?

## 2. Data

* Training rows: as before, 128 tasks drawn per seed from the study's development panel (canonical train).
* Evaluation: a FRESH SearchQA sample no run of this project has used
  (`scripts/make_searchqa_fresh_sample.py`: 4,000 items drawn with a seeded generator from the `validation` split
  of the locally cached `lucadiliello/searchqa`, revision `c1a979068ba1...`, the split and revision the native
  val / test items come from; all 2,000 native items and every duplicate normalized question excluded; context and
  question lengths match the native test items). Four blocks of 1,000:
  * block A (`cc57de4d...`): this study, cut into halves A1 / A2 of 500 in file order (two independent runs, so
    an interrupted run loses half);
  * block B (`0246bf8d...`): reserved for the follow-up of section 6;
  * blocks C and D: stay on the operator's machine, unread, for the one-time hold-out read.
  Once read here, block A is used development evidence. Nothing is learned from or selected on it.

## 3. Skills (20 arms, all solve the same 1,000 tasks)

| arm | what it is |
|---|---|
| `empty` | no Skill |
| `bhand` | the three-line hand-written generic instruction of 10/11 (416 B, `724d5870...`). Written after reading a learned Skill: an informed, post-hoc compression baseline |
| `bzero` | a zero-shot initial instruction: the analyst model sees ONLY the public task card (the solver's fixed instructions, the input fields, the public metric) and writes guidance once (`scripts/generate_zero_shot_skill.py`); frozen by hash before any task is solved under it; never selected among alternatives |
| `le21`..`le25` | one pass/fail update step from the EMPTY Skill, adopted without any selection (`scalar / none`), seeds 20261021-25 |
| `lh21`..`lh25` | the same from `bhand`, same seeds (so the same 128 training rows per seed) |
| `lz21`..`lz25` | the same from `bzero`, same seeds |
| `old_v10` | the SearchQA Skill deployed by the validation-gated co-evolution method (learning v10, chain e) |
| `old_v9` | the SearchQA Skill deployed by the SkillOpt baseline (reference answers on failed rows, validation gate; chain v9c) |

A learning stage is the existing v11 stage with arms `scalar / none`: the solver solves the 128 rows under the
parent text, the analysts see task text, answer and pass/fail, the native updater proposes one candidate, and it
is adopted without a challenge (no diagnosis, no decision pool, no validation data).

Failure handling, fixed now. A stage that completes without a changed text contributes its parent text (that is
the procedure's output and stays in its group). A stage that ends pending is a lost history: reported, never
resumed, not replaced. The list of surviving arms is frozen once, after the last learning stage, and the same list
is evaluated on both halves. `bzero` is consumed only from a completed generation record whose hash matches the
Skill file (`generate_zero_shot_skill.py check`); if the generation does not complete, the queue stops before any
learning stage.

The public task card of `bzero` states the metric (exact match after SQuAD-style normalization of the text inside
`<answer>`). That makes `bzero` a strong baseline on purpose: it is what a practitioner who read the benchmark's
description would write.

## 4. Evaluation

`scripts/run_active_evidence_panel_eval.py`: every arm solves every task once through the v11 call path (same
solver model and effort, ledger, adapter and scorer as all v11 development evaluations). Arms are interleaved: the
tasks are shuffled once and cut into chunks of 25 (`--chunk 25`, given explicitly in the launch commands), and
inside chunk c the arms run in the listed order rotated by c, so every arm takes every position in the order
equally often (20 arms, 20 chunks per run). Two runs: A1, A2. A run that stops leaves a durable pending result
built from the sealed evaluation records; it is never resumed, and its positions are reported as partial.

## 5. Reading (fixed now; inferential contract revised after the Codex review, before any stage ran)

From the zero-call report over both runs. A group (`le`, `lh`, `lz`) is the per-task mean pass rate of its
completed histories, its members listed in seed order.

What is reported for every contrast, on ONE common task set (the tasks on which every arm involved is known):

* the estimate;
* the task-level 95% interval -- tasks resampled, the realized Skill texts held fixed (a statement about these
  texts);
* for a group against one text, and for two groups paired seed by seed: the per-history values and the
  history-level t interval -- histories resampled, the tasks held fixed;
* for the same contrasts the **crossed interval**: estimate ± t(H−1) · sqrt(se_task² + se_history²). Tasks and
  histories are crossed (every Skill solves every task; a shared baseline text and shared seeds enter every
  history's difference), and this combination is an approximate, deliberately conservative choice: the
  task-by-history interaction is counted in both terms and the critical value is the t of H−1. With five
  histories it does not guarantee exact 95% coverage.
* the missing-outcome bounds: the estimate recomputed over ALL planned positions with every missing outcome
  (unknown, or never run) set against, and then for, the contrast.

Claims. A statement about the PROCEDURE on new tasks ("one learning step adds ...") may rest only on the crossed
interval. The task-level and history-level intervals are diagnostics that say which source dominates. A contrast
between two single texts (`bzero` − `empty`, `old_v10` − `bzero`, ...) has no history dimension: its Tango
interval is conditional on those two texts and is worded so.

Coverage and attrition, fixed now. Coverage is judged against the PLANNED 1,000 positions (`--planned-tasks
1000`): a contrast is read only when at least 900 are jointly known for all arms involved, and a half that is
absent or stopped counts as missing. A group is its completed histories; a group with fewer than three has no
history-level or crossed interval and supports no claim; two groups are paired by the RECORDED seed of their
stages (a seed missing from one group is dropped from the other, and the report lists what was dropped). Every
interval is conditional on the completed histories and on the jointly known tasks, under the assumption that the
missing outcomes are unrelated to the contrast; the 90% rule does not make that assumption true. So the two
claims below also need the missing-outcome bounds on their side: "established" needs the lower bound above zero,
"bounded" needs the upper bound below +0.03. If the bounds disagree with the interval, the contrast is reported as
not resolved under missingness.

Primary:

1. **P1 = `lz` − `bzero`** -- what one learning step adds to the clean initial instruction;
2. **P2 = `lh` − `bhand`** -- the same for the informed hand-written one.

Secondary, in this order: `bzero` − `empty`, `bhand` − `empty` (what an instruction alone gives); `le` − `empty`
(the earlier headline, now on fresh tasks); `le` − `bzero`, `le` − `bhand` (learned from empty against the initial
instructions); `lz` − `le`, `lh` − `le` (paired by seed: does the starting text change where one step ends);
`old_v10` − `bzero`, `old_v10` − `bhand`, `le` − `old_v10`, `old_v9` − `bzero`, `le` − `old_v9` (the
validation-gated methods' Skills on the same fresh tasks; each is ONE text, so its own learning-history variation
is not represented).

Descriptive: per arm the scorer's failure classes (exact-match failure with answer and reference containing one
another / partial overlap / no overlap), reasoning tokens, answer length, Skill bytes. The containment class is a
count-level clue to answer-form effects, not a verdict that the content was right.

Interpretation, fixed before any outcome:

* P1 (or P2) **established**: its crossed interval lies above zero. Then, on fresh SearchQA tasks, one pass/fail
  step adds to that initial instruction. It does not yet show that the addition comes from task experience rather
  than from a second rewriting pass -- that is the follow-up of section 6.
* P1 (or P2) **bounded**: the upper limit of its crossed interval is below +0.03. Then the step adds less than
  three points to that initial instruction -- a statement about these two frozen initial texts, this solver and
  effort level, and this procedure; not a ceiling of the domain and not a statement about the method elsewhere.
  Three points is the practical-effect bound fixed here: it is about what one history can resolve on 1,000 tasks.
* Otherwise **not resolved**: neither a gain nor the bound is established, and the estimate is reported with its
  three intervals.
* A crossed interval below zero (as fg17 hinted: the step from the generic text ended below the step from empty)
  is reported as a loss.
* No Skill, policy or parameter is selected on these outcomes.

Power, as planning arithmetic only: with 1,000 tasks and the observed 10-12% paired disagreement, ONE history
against a fixed text has a minimum detectable difference of roughly 2.8-3.1 points (two-sided 5%, 80% power). The
power of a five-history group contrast depends on the between-history spread and on how the histories covary over
tasks, neither of which is known before the run (earlier one-step gains over the empty Skill ranged over about
four points); no resolution is promised for it.

Expectations, not criteria: `bhand` − `empty` +7 to +9; `bzero` − `empty` at least as large; `le` − `empty` +11 to
+13; P1 and P2 between 0 and +4; `lz` − `le` and `lh` − `le` slightly negative.

## 6. Follow-up reserved for block B (not run now)

If P1 or P2 is positive: the expert's experience-free control -- the same analyst rewrites B once seeing only the
task card and B (no trajectories) -- against the experience step, on block B. If both are near zero: block B stays
unread.

## 7. Disclosures

`bhand` is informed by a learned Skill; `bzero`'s card names the metric; the training rows come from the reused
development panel (only the evaluation tasks are fresh); the five seeds are shared by the three parents (paired by
seed, so the groups are not independent); one domain, one solver, one effort level; the evaluation manifest labels
the fresh tasks `development` because the package admits no other label -- they are development-stage evaluation
data, not a final test; the two scripts trust the supplied text files (hashes are sealed, authorship is this
memo's disclosure).

## 8. Review

Codex (10/12): GO WITH REQUIRED CHANGES on the first version; all eight are adopted before launch -- lifecycle
checks and publication inside both locks; results rebuilt from the sealed evaluation records so that a stopped
run stays reportable; usage accounting must be complete for `completed`; a stage's Skill is taken only after the
stage tool's full parent verification, and the report re-checks the retained evidence inventory; one common task
set per contrast, explicit coverage and attrition rules, paired-seed group contrasts; pooled runs must agree in
model, service and sources and share no family; the inferential contract of section 5 (crossed interval for
claims, a three-point practical bound instead of "little room", the corrected power statement); regression tests
for these paths. Second round: GO WITH REQUIRED CHANGES (six), all adopted -- neither fixture hook can enter a
natural run; groups are paired by recorded seed; coverage counts the planned positions; the queue's failure
handling is written down (section 3) and the generated Skill is consumed only from a completed record; claims are
conditional on completed histories and observed tasks and need the missing-outcome bounds on their side; more
regression tests (10 tests in `tests/test_continual_learning_active_evidence_panel_eval.py`; the crossed interval
is kept and described as approximate and conservative, as the reviewer advised).

## 9. Amendment of 2026-10-12, 14:30 (before any evaluation call; only the completed / pending status of learning stages was known)

What happened. The network path from the development machine to the provider had connect-phase outages of one to
two minutes about every ten to twenty minutes (13:33, 13:43, 13:55; the calls fail with `timeout` in the phase
`connect_or_headers`, three attempts of 20 seconds each). Consequences under the frozen client and ledger: a
learning stage stops when ONE reflection call fails all three attempts (`le21` and `le22` were lost this way,
before any update); an evaluation run would stop as soon as 64 attempts without usage have accumulated, which a
single long outage with eight solver threads reaches. The first queue's evaluation phase (two runs of 500 tasks)
was therefore disabled before it began (placeholder directories; no evaluation call was made).

Changes, all decided on network grounds and on the completed / pending status of stages only:

* **Histories.** The target stays five completed histories per parent. Seeds continue after 25 (26, 27, ... at most
  36), in seed order, for every parent that still has fewer than five completed histories, until each has five.
  The evaluated group of a parent is its first five completed histories in seed order. Lost histories are listed
  and never resumed. Two groups are still paired by recorded seed, so the seed-paired contrasts (`lz` − `le`,
  `lh` − `le`) may rest on fewer than five pairs.
* **Evaluation in ten runs of 100 tasks** (block A in file order: A01..A10; the same 1,000 tasks) with
  `--chunk 10`: ten chunks per run. The order INSIDE a chunk is therefore not balanced any more: arm k takes ten
  of the twenty order positions, the same ten in every run (section 4 promised all twenty). What stays balanced is
  the spread over time: every arm solves every chunk, a chunk being about a minute of wall time. A run that ends
  with a sealed pending result is repeated ONCE, in full, in a new directory; the pending run is reported and not
  used; a block whose repetition is pending too counts as missing against the planned 1,000; a run that leaves no
  valid result stops the queue for operator review.
* **Connectivity gate** (snapshot `20261012-m` = `l` plus this change of the evaluation tool): before each batch
  the tool probes whether a connection to the provider can be opened (through the credential-free gateway of the
  frozen model record; no model call) and, if not, waits for three consecutive successful probes; after an hour
  without connectivity the run ends pending. The gate only delays the submission of a batch; no call, retry or
  accounting rule changes. Learning stages cannot be gated this way (stage tool and package are unchanged); the
  queue merely waits for two quiet minutes of an external probe before each stage and five before each
  evaluation run (the probe must be alive -- its last line at most a minute old -- and the wait is bounded at
  four hours, after which the queue stops).
* Completion can still correlate with run time or with the parent text (a longer reflection phase is exposed
  longer), so the claims stay conditional on the completed histories, and every failed attempt's cost is kept in
  the records.

Nothing else of sections 1-8 changes: the arms, the reading order, the claim rules and the practical bound stand.

Note of 16:10 (before any evaluation outcome was read). Histories as evaluated: `le` = seeds 23, 24, 25, 26, 27
(21 and 22 lost), `lh` = 21, 22, 23, 24, 26 (25 lost), `lz` = 21-25; all three losses are a call that failed its
three connect attempts, before any update. So `lz` − `le` is paired on seeds 23-25 and `lh` − `le` on 23, 24, 26.
Block A01 began at 16:03 with `--chunk 10` and ran at 53 evaluations per minute (a batch of ten on eight solver
threads leaves most of a second wave idle): ten blocks would take about six hours. Blocks A02-A10 are therefore
run by a third queue (u3) with `--chunk 8` -- thirteen chunks per run, same tool, same frozen arm list in the same
order, same repetition rule; u2 was made to stop after A01 with placeholder directories. The change concerns the
batch size only and was decided on the measured rate, not on any outcome.

## 10. Second amendment, 2026-10-12 17:00 (before any per-arm outcome or contrast was read; run totals over all arms were seen)

What happened. Block A01 ended pending twice (`a01`, then its one repetition `a01-r1`), both with
`unknown_cost_attempt_cap`. The sealed receipts show why, and it is not a matter of chance: one task of the block is
refused by the provider's content filter for every Skill (20 failed calls without usage in each run), and each run
also met one short connect failure (24-25 failed attempts; the connectivity gate's probe -- a CONNECT tunnel through
the gateway -- stayed green, so the failure is later in the connection, presumably the TLS handshake, which the
probe does not make). The frozen ledger admits a call only while failed attempts without usage plus a reserve of
three for the call itself and for every call already in flight stay within 64; with eight solver threads the
eighth call needs 24 in reserve, which leaves about 40, the exact margin varying with the concurrency of the
moment. A filtered task costs one attempt per arm (20) in every run that contains it, so a 100-task run with a
filtered task has little margin left for a connection failure (both A01 runs ended at 44-45), and repeating it in
the same form starts with the same handicap. Smaller runs reduce this exposure; they do not guarantee that a run
completes. The runs also proved slow (45-50
evaluations per minute at chunk 10, 34 at chunk 8): the solver's call latency is heavy-tailed and every small batch
waits for its slowest call.

What was inspected before this amendment, exactly: the queue logs; the status and reason of the results of `a01`
and `a01-r1`; per run, the number of calls, the counts of failed HTTP attempts by error type, the number of
unknown evaluation records per task, the ledger's count of attempts without usage, call durations and token
counts, and the TOTAL numbers of pass / fail / unknown evaluation records of a run over all arms together (a01:
167 / 26 / 25; a01-r1: 1,121 / 212 / 25). No pass count of any single arm and no contrast between arms was read.

Changes:

* **Forty runs of 25 tasks** (block A in file order: Q01..Q40, the same 1,000 tasks), `--chunk 25`: one chunk per
  run, i.e. each arm solves the run's 25 tasks in one batch, the arms in the listed order (no rotation inside a
  run any more). All twenty arms still solve the same 25 tasks within about six minutes; what is given up is the
  rotation of the order inside that window. **Limitation:** the arm is now confounded with the position inside
  each run -- `empty`, `bhand`, `bzero` always come first, the `lz` histories and the two old methods' Skills last,
  a few minutes later. If the service's quality drifted systematically within a run, that would enter every
  contrast and no interval or missing-outcome bound here would show it. A different seed only reorders tasks, and
  reordering the arms per run is not compatible with the reviewed report tool; a counterbalanced order needs a
  reviewed change and is left for a later version. A run that leaves a sealed pending result is repeated ONCE in
  a new directory, as before, and a block whose repetition is pending too is missing: this retry rule is frozen
  for Q01..Q40 and will not be set aside again.
* **Block A01's tasks are run again in this form** (Q01..Q04). This sets aside, for A01 only, the rule that a
  block whose repetition is pending counts as missing. The reason for the two pending runs (a filtered task plus a
  connection failure against the attempt cap) does not depend on what any arm answers, and all arms are solved
  again together; that makes the exception defensible, it does not prove that attrition is unrelated to
  performance. `a01` (216 calls) and `a01-r1` (1,356 calls) are kept with all their evidence and costs, reported
  as discarded attempts, and their partial outcomes are never combined with the Q runs.
* **A02.** The 100-task run `a02c8` (chunk 8), begun at 16:40, is cancelled by the operator at the switch to this
  plan, before its outcomes are read: at its measured rate it needed about an hour and carried the same exposure.
  It stays as an interrupted record with its evidence and costs, is not used and is never resumed; its tasks are
  Q05..Q08.
* The queue waits for five quiet minutes of the connectivity probe before each run, as in section 9.
* Planned denominator, coverage rule, arms, reading order and claim rules are unchanged. Filtered tasks stay in
  the denominator as unknown positions for every arm.

## 11. Third amendment, 2026-10-12 17:45 (before any per-arm outcome or contrast was read; run totals over all arms were seen)

What happened under section 10 (queue u4, 16:50-17:29): Q01 ended pending and completed on its repetition; Q02
ended pending twice (once on its very first call, once with the content-filtered task plus connection failures)
and is MISSING under the frozen retry rule; Q03 completed although 29 attempts failed inside it. The queue was
then stopped by the operator before Q04 (placeholder directories). A diagnostic probe that completes the TLS
handshake through the gateway (no request, no credential) was started at 17:21: it timed out from 17:25:30 to
17:26:53 and was slow at 17:27:25 -- the same minutes in which Q03's attempts failed -- while the CONNECT-level
probe of section 9 never failed all day. So the outages are stalled TLS handshakes through the gateway, lasting
about two minutes, and the gate of section 9 could not see them. With `--chunk 25` one such outage can spend the
whole attempt margin inside a single batch.

Inspected before this amendment: queue logs, run statuses and reasons, failed attempts by error type and minute,
the probe logs, and again only run TOTALS of pass / fail / unknown over all arms (no single arm, no contrast).

Changes for Q04..Q40 (snapshot `20261012-n` = `m` plus the probe change):

* The connectivity gate's probe now completes the TLS handshake with the provider through the gateway. It still
  only delays a batch.
* `--chunk 10`: three batches per arm and run (10, 10, 5 tasks), so that an outage that lasts through a whole
  batch costs about thirty failed attempts before the gate holds the next batch (not a guaranteed ceiling:
  earlier failures in the run accumulate, and eight-way admission needs the count to stay at or below 40); the order inside a run rotates again over three offsets.
  Q01 (repetition) and Q03 were run with `--chunk 25` and are used as they are.
* The queue starts a run only after sixty consecutive successful TLS-level probes (one every ten seconds, about
  ten minutes) and waits up to about twelve hours for that. Review: Codex GO on this delta, no launch blocker.
* Retry rule unchanged: one repetition; Q02 stays missing (25 of the planned 1,000 tasks).

## 12. Fourth amendment, 2026-10-13 03:00 (before any per-arm outcome or contrast was read; only run statuses were seen)

Queue u5 ran Q04..Q31 between 17:37 and 02:29: every block completed on its first run except Q27 (sealed pending,
completed on its repetition `q27n-r1`). From 02:12 to 02:51 the TLS-level probe failed every five to ten minutes
(outages of ten to seventy seconds), so the launch rule of section 11 (sixty consecutive successful probes) held
the queue from 02:29 on. The operator stopped queue u5 at 02:57 while it waited (no run in progress, nothing
prepared for Q32).

Change for Q32..Q40 (queue z1, part u6; same snapshot `20261012-n`, same twenty arms in the same order, same
`--chunk 10`): a run starts after TWELVE consecutive successful probes (about two minutes) instead of sixty. The
in-run gate, which holds each batch during an outage, is unchanged, and so is the retry rule (one repetition, then
the block is missing). Reason: a block takes three to six minutes on a working network, so ten quiet minutes
before each block mostly measured the past; the window only has to keep a run from starting inside an outage.
Q02 stays missing; the planned denominator stays 1,000.
