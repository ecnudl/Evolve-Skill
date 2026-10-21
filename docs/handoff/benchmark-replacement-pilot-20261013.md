# Replacing BigCodeBench and KOR-Bench: headroom pilot on LiveMathematicianBench (2026-10-13)

Written before any pilot call. Context: on 10/13 the owner decided to replace BigCodeBench and KOR-Bench (no
accepted update by any method; a generic or learned Skill text moves them by a few points at most) by two of the
benchmarks of the SkillOpt paper, and after a read-only survey chose **OfficeQA** and **LiveMathematicianBench**
(DocVQA is image-only; the toolchain's client sends two text messages). OfficeQA is gated on Hugging Face and the
operator's account has not accepted its terms yet, so this memo covers LiveMathematicianBench only.

## 1. Why a pilot first

Porting a benchmark into the learning toolchain means a new split, a new study protocol and new versions of the
frozen packages. The project page of the SkillOpt paper reports, for an unnamed solver, no Skill 26.7, a
model-written Skill 29.1, a human-written Skill 28.1 and the SkillOpt Skill 42.9 on this benchmark -- the pattern
this project needs (an instruction is not enough, experience adds) -- with five options per item (chance 0.20), the
gains differ widely between solvers (+4.0 to +29.6), and our solver is GLM-5.3 at low effort. Two things have to
be known before the port: is the frozen solver above the floor at all, and does a zero-shot instruction already
close the gap to a Skill learned from experience?

## 2. Data

Upstream `LiveMathematicianBench/LiveMathematicianBench` at revision `6f53c5ff7227633ea954b2847cd590314d582047`
(public, 608 items in eight monthly files, five options each -- a record lists four wrong options and,
separately, the correct one -- one paper per item; no licence stated on the page:
the files stay on the operator's machine and the experiment machine and are not published). The paper's split
(`data/livemathematicianbench_id_split`, 35 / 17 / 125 items) lies entirely in the months 2025-11 to 2026-02. The
pilot draws **50 items from each of the four later months** (2026-03 to 2026-06, 431 eligible) by a hash order with
seed 20261013; every month that has an item of the paper's split is excluded as a whole, so no test item of the
paper is read and the paper's checkpoint Skill has seen none of the pilot's items. Upstream the correct option always
carries the label A and the wrong ones B to E, so each item's five options are put in a hash-drawn order that is
frozen in the prepared record. The solver receives the question and the options; `theorem` and `sketch` never leave the source files.

## 3. Arms (all solve the same 200 items once; `scripts/pilot_livemath_headroom.py`)

| arm | Skill text |
|---|---|
| `empty` | none |
| `bzero` | a zero-shot instruction: one call of the analyst model on a public task card (fixed solver instructions, input fields, metric), generated once, not selected -- the same writer prompt as the SearchQA `bzero` |
| `human` | `skillopt/envs/livemathematicianbench/skills/initial.md` (1,018 bytes), the hand-written starting Skill of the original codebase |
| `paper` | `ckpt/livemath/gpt5.5_skill.md` (3,343 bytes), the Skill SkillOpt learned with GPT-5.5 as the solver on the paper's training items and selected on its validation items |

The solver prompt is the toolchain's own form (`backends.solve`): the fixed sentence, the "Frozen skill guidance"
block, the line "Choose exactly one of the listed options and return only its letter inside <answer>...</answer>.",
and the public view as JSON. Model, effort, transport and retry policy are the F study's solver record; calls go
through the frozen client directly (the learning ledger does not know this benchmark), with one length recovery
like the solver role's. The zero-shot instruction is ONE call without a recovery.

Scoring is strict and frozen here: exactly one letter A to E inside the last answer tag (case, surrounding space
and one trailing `.`, `)` or `:` ignored) against the correct option's letter. A delivered reply in any other form
-- no tag, the option's text, two letters -- is a wrong answer and is counted per arm as `invalid_format`, so a
format problem cannot hide as a reasoning result. (The original evaluator also accepts an untagged last line and
an option's text; the toolchain's contract is the tag.)

Delivery and accounting. Every position writes a sealed intent before its call and a sealed outcome right after
it; a position with an intent and no outcome is reported as unknown and as an open intent. The run stops, sealed
pending, BEFORE its margins can be exceeded: at most 16 positions without a usable reply and at most 96 HTTP
attempts that delivered nothing over the whole run, a batch never being larger than the remaining margins cover
when every position in it takes its worst case of six attempts (two client calls of three). Costs are summed over
all HTTP attempts: the tokens of every attempt that reported usage, and the number of attempts that did not. A
client call that ends in an exception leaves no receipt: it is recorded as an unresolved call (spending unknown),
charged to the failed-attempt margin at its worst case of three attempts, and the result then carries
`costs_complete: false`. Nothing is resumed; a repetition is a new directory.

## 4. Reading (fixed now)

Descriptive. Read only from a COMPLETED run; a contrast is read only if at least 180 of the 200 items are known
for both arms, and its missing-outcome bounds must lie on the side of any statement made about it. Intervals are
Tango 95% intervals for a pair (conditional on these two texts) and Wilson 95% intervals for one arm; 200 items
resolve about seven to ten points for a pair. The items are an equally weighted mixture of the four months.

* **Floor.** Each arm's pass rate over its known outcomes with its Wilson interval, against five-way chance
  (0.20). An arm is "above the floor" only if the lower limit is above 0.20. If no arm is above the floor, the
  statement is "this pilot does not show the frozen solver above chance on this benchmark" -- not that it cannot
  do the task -- and the port is not started on this pilot's strength.
* **Headroom.** `paper` - `bzero` (and `paper` - `empty` next to it). "A Skill learned from experience beats the
  zero-shot instruction here" only if the interval of `paper` - `bzero` lies above zero. Then the port goes ahead.
* **Small headroom.** "A learned Skill adds less than five points over the instruction here" only if the upper
  limit of `paper` - `bzero` is below +0.05. Then the port is reconsidered with the owner before any engineering.
* **Inconclusive** -- anything else, in particular a `paper` - `bzero` interval that contains zero and reaches
  +0.05: reported with all four pass rates and both contrasts, and decided with the owner. Neither "saturated" nor
  "headroom" is claimed.

This pilot decides an engineering investment. It is not evidence about the method, and nothing is selected on it.

## 5. Disclosures

The 200 items become used development items. `paper` was written for a different solver and, by its headings and
first section, partly encodes how this benchmark builds its wrong options (a test-taking prior); a gain of `paper`
shows room for a Skill, not that the room is mathematical. `human` was written by people who knew the benchmark.
One draw, one solve per item and arm; a run that stops is sealed pending and repeated, if at all, in a new
directory. Not published: the upstream files, the prepared `items.json` (questions, options and answer
keys), the client's cache of prompts and replies; only counts, intervals and hashes leave the machines. Later
months are not guaranteed to be free of near-duplicates of earlier ones, and the solver may have seen the source
papers; neither is checked here.

Review (Codex, first round NO-GO, five required findings, all changed above and in the tool before any call): the
parser had been the original evaluator's with empty option texts (an option's text inside the tag could be read as
a letter) -- now the strict rule; the stop after undelivered calls was checked only after a whole batch -- now
bounded before submission; outcomes were written per batch -- now per position, with intents; costs counted only
the last attempt of a call -- now every attempt; the reading rules claimed "cannot do the task" and "saturation"
from intervals that cannot show either and had no coverage rule or floor interval -- rewritten in section 4.
Second round: three more (a call that raised was a zero-cost outcome; the writer's staging files could break the
collection after an interruption; a rejected zero-shot text lost its usage) -- changed as described in section 3.
Correction before any call (found by the zero-call preparation on the real files): an item has FIVE options, not
four -- the tool had read only the list of wrong options; options, letters A to E and chance 0.20 are now right.

## 6. OfficeQA: the same pilot in a one-call form (written 2026-10-13 16:10, before any call)

Terms. The owner accepted the dataset's access terms on Hugging Face on 10/13. Two things apply: the licence
(CC-BY-SA 4.0: attribution, and ShareAlike with a change notice for anything shared that adapts the data) and a
separate ACCESS RESTRICTION: "do not use the answer keys to train models evaluated on OfficeQA or to artificially
inflate benchmark scores". This pilot uses the answers only to score; it does, however, include as one arm a
checkpoint Skill that others learned from these answers. **Whether learning a Skill with training-part answers as
feedback falls under that restriction is NOT settled by this memo**: held-out reporting, unchanged model weights
and the SkillOpt paper's precedent do not establish permission, and not publishing the data does not settle a use
restriction. The owner has to decide (or ask the dataset's maintainers) before a port that learns from answers.
Nothing of the data is published by this pilot.

**Task form -- not the paper's.** In the paper the solver searches the Treasury Bulletin text files with tools
over up to 24 turns. This toolchain's solver makes one call, so the pilot (and a first port) uses the original
environment's "oracle parsed pages" form: the question plus the parsed page(s) its own source hints point to (at
most 24,000 characters per page, 80,000 in all), i.e. reading tables and calculating, without retrieval. Numbers
are not comparable with the paper's 31.0 (no Skill) to 52.4 (SkillOpt).

**Data.** `databricks/officeqa` at revision `763a8366abf2a3605c381d53586d844dc60fa756`: 246 questions (133 "hard",
113 "easy"), parsed pages of 697 bulletins. The paper's split is 50 / 24 / 172. The pilot reads out ONLY the 74
training and validation items (all 74 resolve to parsed pages; contexts of 430 to 58,916 characters, median 7,755,
none cut). The question file is read into memory as a whole, but the 172 test items are never selected, sent to a
model or written out; the gold answers of the 74 selected items are written into the prepared `items.json`
(private part, on the experiment machine only), and model messages carry only the question and the context.
Nonempty, uncut contexts do not prove complete evidence: the original renderer skips a missing or empty page
silently, ignores table spans and can lose text outside table cells -- limitations of the form, not defects
shown on these items. Source URLs appear in the context as location hints; nothing is fetched.

**Arms** (`scripts/pilot_officeqa_headroom.py`, the reviewed call, margin, intent and cost machinery of the
LiveMath pilot): `empty`; `bzero` (one call on a public task card that states the input, the fixed instructions
and the scorer's normalisation); `human` (`skillopt/envs/officeqa/skills/initial.md`, 887 bytes -- its retrieval
section has no object in this form); `paper` (`ckpt/officeqa/gpt5.5_skill.md`, 6,456 bytes). **`paper` was
learned and selected on exactly these 74 items** (with GPT-5.5, in the tool form): its arm is an optimistic
reference, not a clean measurement of what experience gives.

**Scoring.** The original environment's normalised exact match on the text inside the last answer tag (lower
case; commas and most punctuation removed; unit words removed; NO numeric tolerance -- `12.5` and `12.50`
differ), kept as it is. Known consequences, in both directions: it accepts some wrong answers (`5 million` equals
`5 billion`, an accounting `(5)` equals `5`, `1/2` equals `12`) and rejects some right ones (`7 percent` against
`7%`, a Unicode minus against `-`, `7.` against `7`); a whole sentence inside the tag is compared as a whole and
usually fails without being flagged. A delivered reply without an answer tag is wrong and counted as
`invalid_format`.

**Reading (fixed now).** Descriptive; read from a completed run; a contrast needs at least 67 of the 74 items
known for both arms and missing-outcome bounds on the side of any statement; Tango and Wilson 95% intervals; 74
items resolve about twelve to fifteen points for a pair. There is no chance level.

* **Workable form.** If neither `empty` nor `bzero` has a pass rate whose Wilson lower limit is above 0.10, the
  statement is "workability of the one-call form with this scorer is not established" (12 of 74 would give about
  0.10 to 0.26) -- not that the form is unusable -- and pages, cuts and answer forms are looked into before any
  port.
* **What an instruction gives.** `bzero` - `empty`, and `human` - `empty`.
* **The checkpoint Skill against the instruction.** `paper` - `bzero`. `paper` was fitted to these very items for
  another solver and another task form: it is an optimistic REFERENCE, not an upper bound on what learning could
  give here. If the interval lies above zero: this checkpoint helps on these reused items -- room for a Skill in
  this form, no evidence of generalisation. If its upper limit is below +0.05: this checkpoint adds little over a
  zero-shot instruction here -- which bounds this checkpoint only; the port is then discussed with the owner
  before any engineering. Anything else is inconclusive and decided with the owner.
* Pass counts by the benchmark's "easy" / "hard" label are given with their known and unknown denominators.

Only 246 labelled items exist. A port would need its own split (the paper's 50-item training part is too small
for this project's stages), which gives up comparability with the paper's test numbers; this is exactly the
situation in which generated test questions from the bulletin pages could stand in for a validation part.

Review of the OfficeQA pilot (Codex, 16:10-16:20): no regression in the copied execution paths (margins, intents,
per-attempt costs, no resume, exception hygiene; the implementation-hash check is stricter than the original's);
NO-GO on the first wording of this section, GO for the descriptive pilot after four corrections, all made above:
the checkpoint arm is a reference and not an upper bound, and a missed threshold is "not established"; the access
restriction is separate from the licence and a learning port is not implied to be permitted; test items are
"never selected, sent or exported" and the renderer's limits are stated; the scorer's wrong acceptances and
rejections are listed.

Owner's decision on the access restriction (2026-10-13, about 16:15, after the question above was put to them):
proceed as the SkillOpt paper does -- a Skill learner may receive the answers of TRAINING items as feedback;
held-out items are only scored. This is the owner's reading of the terms they accepted; the caveat above stays on
record, the data and the answer keys are not published, and model weights are never trained.

## 7. Amendment of 2026-10-13 17:00: the LiveMath run was stopped and is repeated with rolling submission

What happened. The pilot (`livemath-pilot-a`, tool version v1, snapshot `20261013-r`) submitted its positions in
batches of up to sixteen and waited for each batch as a whole. Most replies took seconds (median about 1,300
tokens), but a single reply can reason towards its 65,536-token limit for half an hour, and each such reply held
its whole batch back: after 66 minutes 80 of the 800 positions had been submitted (20 per arm: the first twenty
items) and one reply had been in flight for 34 minutes. At that rate the pilot would have taken most of the night
while holding the shared lock.

The stop was an operator decision for THROUGHPUT, taken from the queue log, the token counts and the number of
positions in flight; before it only the pooled count over all arms had been seen (21 passes among 79 outcomes).
The run was stopped at 17:01 and sealed with the code that ran it: status pending,
`interrupted_run_no_automatic_resume`; 80 intents, 79 outcomes, one open intent (a `paper` position whose reply
was abandoned -- its spending is unknown), 182,969 tokens in the 79 known calls, no failed attempt. The sealing
command printed the per-arm counts of those twenty items (6, 4, 8 and 3 passes of 20 for `empty`, `bzero`,
`human`, `paper`): they have been seen, they are far too few to mean anything, and **no outcome of this run
enters any reading**. The queue z7 (OfficeQA) had not started anything.

What changes (tool version v2, snapshot `20261013-t`; Codex delta review: GO): submission is rolling -- at most
eight positions in flight, a new one as soon as one returns -- with the same margins enforced before every
submission, every position in flight counted at its worst case (so neither margin can be exceeded); the
connectivity gate is asked before a submission at most every ten seconds. Nothing else changes: `livemath-pilot-b`
(queue z8) solves all 800 positions anew for the SAME 200 items in the same frozen option orders, with the same
four Skill texts (the zero-shot instruction generated at 15:55 is reused, not regenerated), model, caps, retries,
scorer and reading rules of sections 3 and 4. The OfficeQA pilot follows in the same queue with the rolling loop.

Disclosures. This is an amended development pilot, not an independent replication. Rolling submission keeps the
queue order (arms rotate per ten items), but which positions are in flight during a network outage now depends on
reply times, so exposure is balanced by position, not by wall clock. A reply that runs to its token limit is
followed by one recovery call at 131,072 tokens (the solver role's rule), which can take an hour: such positions
finish late but no longer delay the others.
