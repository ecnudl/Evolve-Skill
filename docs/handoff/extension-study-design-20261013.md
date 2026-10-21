# Extension study: LiveMathematicianBench and OfficeQA in the learning toolchain (2026-10-13)

Written before any stage or evaluation of the extension ran. The owner replaced BigCodeBench and KOR-Bench by
LiveMathematicianBench (`livemath`) and OfficeQA (`officeqa`) on 10/13 and decided that Skill learning on them
works as in SkillOpt: answers of TRAINING items may be given to the learner as feedback, held-out items are only
scored. The five-benchmark study F, its split and every earlier artifact stay untouched and valid under their own
code snapshots; the extension is a new protocol, a new split and a new snapshot.

## 1. What is added

**Benchmarks (hashed sources, changed once, together).** `continual_eval/datasets.py`: schemas (`livemath`
public `question`, `choices`; `officeqa` public `question`, `context`; private `answer` for both), panel
validation and importers, in a separate roster `EXTENSION_BENCHMARKS` (the five-benchmark roster and the
evaluation plans built on it are unchanged). `continual_eval/backends.py`: the solver contract (officeqa uses
SearchQA's answer-tag line; livemath "Choose exactly one of the listed options and return only its letter inside
<answer>...</answer>."), raw replies passed through, readiness, and one strict host scorer `_score_answer_tag`:
only the text inside the LAST answer tag counts and a delivered reply without a usable tag is a WRONG answer
(`invalid_format`), never an unknown -- livemath: exactly one letter A-E; officeqa: the original environment's
normalised exact match (no numeric tolerance). "Delivered" includes a reply the provider COMPLETED without any
text (finish reason `stop`, complete stream, usage reported): for these two benchmarks it is an answer in no valid
form and is scored wrong; an undelivered, truncated, filtered or oversized (above 262,144 bytes) reply stays
unknown, as for every benchmark -- and so does a completed blank reply whose usage is not reported, because a
delivered answer must be an accounted one. (The headroom pilots counted a completed blank reply as unknown; none occurred there so far.) `continual_eval/core.py`: a second roster `LEARNING_EXTENSIONS`
that only allows a runtime entry of these benchmarks in a learning manifest's configuration, and the OfficeQA
evaluator joins the hashed scorer sources. `continual_learning/feedback.py`: public fields and the labelled
feedback text (`expected_text` = the answer; for livemath the correct option's letter, the options being in the
public task text). `continual_learning/skillopt.py`: the labels of failed training rows for the leak check (a
one-letter or short numeric label is below the check's 12-character minimum, so the check is inert for them, as
for any short label). `continual_learning/verifier.py`: default rubrics, task text and public view for the two
domains (learning v10; both use the judge path without research, like SearchQA; the OfficeQA rubric is about
answer form and question scope only, because obligations are quoted from the question and the pages are shown
clipped). `active_evidence/profiles.py`: two supported profiles that list their implemented arm -- pass/fail
feedback without a post-update step -- and the manifest refuses every other arm for them before any call (the
diagnosis tables of that package do not cover the new domains).

The solver's messages for the two benchmarks are byte-identical to those of the headroom pilots
(`scripts/pilot_livemath_headroom.py`, `scripts/pilot_officeqa_headroom.py`); a test asserts it.

**Study protocol and split (`scripts/make_extension_study.py`, zero calls).** `data` materialises one benchmark's
items into a development panel, a validation panel and evaluation blocks and seals the layout; `study` writes the
extension study protocol (`extension-study-v1`): study F's model record, learning service, client options, native
lock and Skill budget verbatim, the new development panels bound by path and hash, no reference plans and no
evaluation sources; `split` writes the split manifest (`extension-split-v1`). The stage tool's `_study` accepts
the extension version and, at every load, re-verifies what it carries from study F and that each benchmark's
pinned, sealed layout still is what the study binds (layout hash, development panel path and hash);
`check_split` requires an extension split to BE that layout (parts, families, panel hashes, evaluation blocks,
counts) -- a record's own hash proves only itself -- and `check_evaluation_block` lets the panel tool evaluate
only the layout's own, unchanged blocks; `dev_panel_path` replaces the inlined lookup; `test` refuses an extension
study (no test cells yet). The panel evaluation tool
imports the two benchmarks' item files; the zero-shot generator has their public task cards (the pilots').

## 2. Data layout

**LiveMathematicianBench** (608 items at revision `6f53c5ff...`, five options, one family per item = per paper):
test = the 125 test items of the SkillOpt paper's split, listed by id only and never rendered; evaluation blocks
= the 200 items of the headroom pilot (months 2026-03..06), outside the split, rendered exactly as there;
validation = 128 of the remaining 283 items by a hash order; training pool = the other 155 (a stage draws 128 of
them). Option orders are the pilot's hash-drawn orders for every item.

**OfficeQA**: the benchmark is wired in the sources, its layout is not built yet. Only 246 items exist; a layout
needs its own split (the paper's 50-item training part is too small). Plan: the sealed test from the 81 items
whose source bulletins are shared with no other item group (58 document components made only of the paper's test
items, never read out), the other 165 items for training, validation and evaluation blocks; decided after the
headroom pilot.

## 3. What is not provided

Test cells for the extension benchmarks (`test` refuses; the sealed test parts exist only as ids); generated
validation for them (the generator is SearchQA's); the multi-turn retrieval form of OfficeQA; the diagnosis arms
of learning v11 for the new domains (their tables are not extended; `scalar / none` needs none of them).

## 4. Known risks

* **Reply time on LiveMath.** A solve occasionally reasons to the 65,536-token cap and is then recovered once at
  131,072 tokens: up to about an hour for one call. A rollout of 128 rows waits for all rows, so stages will be
  slow there (hours per stage) unless a later protocol lowers the caps for this benchmark.
* **Gate power.** One family per item; 128 validation items with a pass rate not far above five-way chance: the
  two-pass family sign test will often reject.
* **Labels.** For livemath the label is one letter: informative only together with the options in the task text.
* **Scorers.** Strict on purpose: a format slip is a wrong answer, so part of any Skill gain may be answer form.
* **Identity.** Every manifest sealed before these edits is unreadable for `learn` / `run` in this snapshot
  (completed stages stay readable); prepare and run on the same machine (the learning v11 code closure differs
  between a case-insensitive and a case-sensitive file system).

## 5. Review

Codex code review, first round: NO-GO for preparing stages, six required findings, all fixed before anything was
built on the experiment machine: the study loader did not verify its pinned layouts and the split check trusted a
resealed split (both now compare with the sealed layout); a completed blank reply became unknown (now a wrong
answer for the two benchmarks, with the client's `empty_content` receipt handled); the unimplemented learning-v11
arms could be prepared (now refused in the manifest); panel validation accepted a `choices` text without five
options and a list as OfficeQA context (now refused); the OfficeQA v10 rubric spoke of page evidence that the
judge cannot quote (now question-only). Tests: twelve in `tests/test_continual_learning_extension_study.py`,
among them offline runs of the SkillOpt, Rubric+Research and one-step learners on both benchmarks; the evaluation
and learning suites pass (1,535).
Second round: the six closed; three new required findings, fixed: a resealed split could add a source and bring
in another validation panel (the split's sources must now be exactly the pinned panels, and an extension stage's
validation source must be the layout's own file); a completed blank reply above the response size bound was
promoted (now bounded); a completed blank reply without reported usage would have been an answer outside the
ledger's delivered-without-usage stop (now it stays unknown).

## 6. First learning runs on LiveMath (written 2026-10-13 17:45, before any stage; the headroom pilot was still running and none of its outcomes by arm had been read)

Purpose: the first end-to-end learning on a new benchmark, as the owner ordered -- SkillOpt-style learning with
the answers of training items as feedback, next to this project's learners -- and a first look at whether any of
them adds to a zero-shot initial instruction there. Launched only if the headroom pilot does not come out as
"not above chance for every arm" (section 4 of the pilot memo); in that case the owner decides first.

Common: the extension study `study-livemath` and its split; snapshot `20261013-v` (= `u` plus one change in the
stage tool: in an extension study a v9 / v10 stage may start from a fixed initial instruction with the real
validation panel -- there are no chains and no test cells there, and an initial instruction is the default
starting point by the owner's decision); each stage draws 128 of the 155 training items by its seed; the
validation gate uses the 128 validation items; `bzero` is the zero-shot instruction generated once for the
headroom pilot (`livemath-bzero/skill.md`).

| stage | learner | feedback the analyst sees | parent | seeds |
|---|---|---|---|---|
| `lm-e41`..`lm-e43` | learning v11, one step, no selection | pass / fail | empty | 20261041-43 |
| `lm-z41`..`lm-z43` | learning v11, one step, no selection | pass / fail | `bzero` | 20261041-43 |
| `lm-v9-z41` | SkillOpt v9, up to three steps, validation gate | failed training rows with the correct option's letter | `bzero` | 20261041 |
| `lm-v10-z41` | Rubric+Research v10, up to three steps, validation gate | verifier reports (no labels) | `bzero` | 20261041 |
| `lm-v9-e41` | SkillOpt v9 as above | as above | empty | 20261041 |

Order: the six one-step stages, then `lm-v9-z41`, `lm-v10-z41`, `lm-v9-e41` (the gated stages make about two
thousand solves each and wait for their slowest reply in every rollout: hours per stage). Then one panel
evaluation on the 200 evaluation items (blocks E01..E08, the headroom pilot's items), all arms in the same runs:
`empty`, `bzero`, `human`, `paper` (the pilot's four texts, measured again) and the Skill of every completed stage.

Reading (fixed now). Per gated stage: the gate's action at each step with its wins and losses on the validation
items -- whether anything is accepted on top of `bzero` is the first thing these runs show; a completed stage
without an accepted update carries its parent. On the evaluation items: each learned Skill minus its parent and
minus `bzero` (Tango interval, conditional on the texts); the one-step groups `lm-z` and `lm-e` (three histories
each) minus `bzero` and minus `empty` with the crossed interval of the learn-from-B memo. Planned denominator
200; a contrast is read only with at least 180 jointly known items and from completed runs; "adds to the
instruction" only if the interval lies above zero with the missing-outcome bounds on the same side; everything
else is reported as it is. One seed per gated learner and three per one-step group: descriptive development
evidence on items that the pilot has already used once; nothing is selected on the evaluation items.

Multiplicity. Nine learned Skills and several group contrasts are read against the same 200 items with NOMINAL
95% intervals: these are **unadjusted exploratory comparisons**. An interval above zero for one Skill is a lead to
replicate with new seeds, not a finding, and no experiment-wide conclusion of the form "some learner works on
LiveMath" is drawn from the best of them. A stage that accepted nothing carries its parent: its contrast with the
parent's own arm measures sampling variation only and is reported as such. A group contrast needs all three of
its histories completed. An evaluation block that ends pending is repeated once in a new directory; every
attempt's cost stays in the record.

Launch condition (the pilot memo's floor rule): the completed pilot must show at least one arm whose Wilson lower
limit is above 0.20 (with its coverage and missing-outcome conditions); otherwise the queue is not released and
the owner decides.

Disclosures. `paper` and `human` were written for another solver by people or a learner who knew this benchmark's
conventions; they are references. The validation items are used by three gated stages. The one-letter label of
SkillOpt's feedback is below the label-leak check's minimum length (the check is inert here by design). A stage
that stops is not resumed; a repetition is a new directory and is disclosed.

Launch review (Codex, 17:45-17:52): code change and queue GO; one required finding on this section -- nominal
intervals over nine Skills without a statement on multiplicity -- answered by the "Multiplicity" paragraph above.

## 7. OfficeQA: the SkillOpt paper's split, and its first learning runs (written 2026-10-13 20:00, before any OfficeQA stage)

Owner's decision (19:50, after the LiveMath pilot had been read and while the OfficeQA pilot was running): try
OfficeQA now rather than after LiveMath's long stages, and split it the way SkillOpt does. This replaces the plan
of section 2 (a document-disjoint split of our own).

**Layout** (`make_extension_study.py data --benchmark officeqa`): training = the 50 training items of the paper's
split, validation = its 24 validation items, both rendered in the one-call form by the headroom pilot's own
`draw` (the same items and texts the pilot solves); test = its 172 test items, ids only, never rendered. There are
no evaluation blocks: every item is in the split, so the panel evaluation tool has nothing it may evaluate. One
family per item; the paper's split is not document-disjoint (bulletins are shared between parts: 40 files between
training and test). A stage draws 48 of the 50 training items by its seed (learning v11 needs a non-empty rest).

**What can be read without the test part.** Only the gated learners give a signal before a test read: the gate's
wins and losses of each candidate against its parent on the 24 validation items (a two-pass family sign test:
the first pass lets a candidate through from four wins without a loss; the fresh confirmation, at 0.05 over the
three allowed steps, needs six wins without a loss or, for example, nine wins against one loss -- with 24 items
only large gains pass). A one-step Skill is adopted
without selection and has no held-out measurement at all here. **The held-out measurement of every OfficeQA Skill
is the 172 test items -- as in the SkillOpt paper -- and that is a test read: it is not part of this queue, it
needs the owner's explicit go-ahead and a release mechanism that does not exist yet (the tools refuse test
cells and split members today).**

**Runs** (queue z10, snapshot `20261013-w` = `v` plus the OfficeQA layout in the builder and the 48-item draw;
`bzero` = the zero-shot instruction generated once for the headroom pilot, `officeqa-bzero/skill.md`; seeds
20261041-43):

| stage | learner | feedback | parent |
|---|---|---|---|
| `oq-v9-z41` | SkillOpt v9, up to three steps, validation gate | failed training rows with their reference answers | `bzero` |
| `oq-v10-z41` | Rubric+Research v10, same gate | verifier reports (form and scope, no labels) | `bzero` |
| `oq-v9-e41` | SkillOpt v9 | as above | empty |
| `oq-z41`..`oq-z43`, `oq-e41`..`oq-e43` | learning v11, one step, no selection | pass / fail | `bzero` / empty |

The gated stages run first because they are the ones that say something tonight.

Reading (fixed now). Per gated stage and step: the gate's action with its wins and losses on the validation items
and the Skill's size; whether anything is accepted on top of `bzero`. Nothing else is claimed from this queue:
three single histories with a 24-item gate are descriptive, a rejection says only that no gain of the size this
gate can see was measured, and an acceptance is a candidate for the test read, not a result.

Disclosures. Training and validation items were solved once by four fixed texts in the headroom pilot (whose
outcome may be known when these stages run; it changes nothing in them); one of those texts, the paper's
checkpoint Skill, was itself learned and selected on these same 74 items. `Z10-EXIT` in the queue log means the
queue finished, not that every stage completed. The training answers are given to
SkillOpt's analyst as feedback -- the owner's decision on the dataset's access restriction (pilot memo, section
6). The scorer is the original strict exact match. The task form is the one-call form, not the paper's retrieval
task, so no number here is comparable with the paper's.

Launch review (Codex, 19:55-20:05): layout, draw and queue GO; two required corrections of text, made: the gate's
thresholds above, and the workflow document, which still described the superseded document-disjoint plan.
