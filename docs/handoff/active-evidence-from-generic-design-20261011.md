# Design contract (2026-10-11, late evening): one learning step ON TOP OF the fixed generic instruction

Extends `active-evidence-generic-control-design-20261011.md` (queue t1: the fixed generic texts as evaluation-only
references). Snapshot `20261011-k` = `j` plus two additions to the stage tool. Written while the first stage of
queue t1 (gen17) was still running: no outcome of any generic control was known when sections 1-4 were fixed.

## 1. Why

Queue t1 measures Q-A (generic text minus no Skill) and Q-B (the Skill learned FROM THE EMPTY parent minus the
generic text). Its memo states that Q-B is a comparison of two alternatives and NOT what learning adds on top of a
generic instruction. But that is the question a reader will ask: nobody deploys a solver with no additional
guidance at all (the ordinary task instructions are present in every arm; "empty" means no Skill text), so the
realistic starting point of Skill learning is a short hand-written instruction. This study starts one update step
from that text and measures the step against its own parent.

## 2. What is added

Tool only (`scripts/run_fivebench_g_stage.py`; diff against j: `active-evidence-fixed-parent-20261011.diff`):

* `--parent f:<absolute path of a text file>` (learning v11 only; refused for the older methods): a FIXED
  operator-supplied text is the stage's parent Skill. The stage record seals `parent_action: fixed_text` and the text's sha256; the manifest
  carries the text; every later load of the stage re-reads the file and refuses a changed text.
* `--reference name=none`: the EMPTY Skill as a named evaluation-only reference, allowed only when the parent is
  not empty (with an empty parent the parent reference already is the empty Skill).
* The report tool publishes a fixed-text parent by its file basename and hash.

Nothing in the `active_evidence` package changes (byte-identical to snapshots i and j). A non-empty parent of a
matched study is not new to the package (the refinement stages of 10/10-10/11 started from `m:` parents); a
non-empty parent of the matched-SCALAR study has not been run before, so the first stage is also its first real
exercise (a STOP there is an engineering finding, not a result). Offline, the package test
`test_matched_scalar_study_from_a_non_empty_parent_with_the_empty_skill_as_reference` runs exactly this shape on a
fixture. Review: Codex GO on the diff and this memo, no required change; its optional points (absolute path,
measured-contrast wording, block-order scope, the full-flow test) are adopted.

## 3. Runs (queue t2; matched-scalar study v2, `diagnosis_research / matched_scalar_branch`, native update,
defaults for every limit, `G_SKIP_TEST=1`, no test read)

1. `searchqa-active-fg17`, seed 20261017, parent `f:/root/fivebench-g-20261011-controls/generic.md` (the
   416-byte text of t1, sha256 724d5870...),
   references `empty=none` and `fromempty=m:<gen17>:comparator`.
2. `searchqa-active-fg19`, seed 20261019, the same with `fromempty=m:<gen19>:comparator`. (Amended at 21:50,
   before any from-generic stage began: this was `fg18` with gen18, but gen18 stopped before any update -- see the
   t1 memo's execution notes -- and is replaced by gen19.)

The seeds are those of gen17 / gen19 on purpose: the step rows (the 128 training tasks) and the reserved pool are
the same as in the stage whose pass/fail branch is the `fromempty` reference, so "learned from generic" and
"learned from empty" differ in the parent text and not in the training rows. (The holdout is drawn anew from the
same pool of 272 tasks: 242 of them, so about nine tenths of the positions coincide with gen17's / gen19's
holdout.) Each stage is prepared only after its gen stage has completed (the `m:` reference reads its sealed
records); if that stage stopped, the stage is not prepared and the queue says so.

SearchQA first because its stages are short (about 20 minutes) and its Q-A is known first. Whether BigCodeBench
and KOR-Bench follow is decided after their Q-A is known (bgen12, krepg2-4) and will be disclosed as a later
addition; it is not part of this contract.

## 4. Reading (fixed now, before any generic-control outcome)

Per study, from the sealed study record (paired differences with Tango intervals), in this order:

1. **pass/fail branch (learned from generic) minus parent (generic)** -- PRIMARY: what one pass/fail update step
   adds on top of the generic instruction;
2. diagnosis branch minus parent (generic); diagnosis branch minus pass/fail branch;
3. `empty` minus parent (generic) -- the sign-flipped Q-A on this holdout (a replicate of t1's Q-A, not independent
   of it: same pool);
4. pass/fail branch (from generic) minus `fromempty` -- same step rows, different parent text: does the starting
   text change where one step ends?
5. pass/fail branch (from generic) minus `empty` -- the total, for orientation.

Descriptive per arm: reasoning tokens, visible answer length, reported tokens; the byte length of each Skill.

Interpretation, fixed before any outcome (every statement keeps its interval; no equivalence margin is frozen, so
no equivalence is claimed). An interval is interpreted only for a contrast the study record marks as measured: a
branch whose text is unchanged from the parent or identical to a reference, or a contrast with fewer than 90% of
the positions jointly known, is reported as not delivered (`failed_delivery`) whatever its diagnostic interval
says:

* (1) clearly above zero in both histories: on these holdouts one update step adds to this generic text. It does
  not show that the addition is more than dataset-specific answer conventions, and it is adaptive development
  evidence on reused pools.
* (1) containing zero: no gain on top of this generic text is established; that is not evidence that learning adds
  nothing (two histories of 242 tasks detect only differences of several points), and it is specific to this text,
  which was written with knowledge of what the learned SearchQA Skills say.
* (1) clearly below zero: the update step damaged a text that worked -- to be reported as such.
* (4) is exploratory: two histories.
* Nothing here selects a Skill or a policy; no deployment decision is attached. If (1) is positive, a method-mode
  stage from the generic parent (does decision rule v2 keep the update?) is the natural next step, as a separate
  contract.

Expectations, not criteria (written without knowing Q-A): if the generic text recovers most of the answer-form
gain, (1) is small (0 to +0.05) and (4) is near zero; if it recovers little, (1) is close to the usual
learned-minus-empty gain (+0.10 to +0.14).

## 5. Disclosures

Two histories on training rows already used by gen17 / gen19 (not independent of them); reused development pools;
the arms run in blocks (the two branches, then the parent reference, then the named references; not interleaved
or counterbalanced), so a service drift within a stage can bias EVERY contrast with a reference block, including
the primary contrast (1) and diagnosis-minus-parent (both compare a branch block with the later parent block, as
in every v11 study), and (3)-(5); the generic text's authorship is disclosed in the t1 memo; the `f:` path trusts the supplied
file. Queue t2 shares the stage lock with t1, so its stages run between t1's stages and delay t1's KOR-Bench
stages by their own duration (about 40 minutes in total).

## 6. Timeline (appended)

Sections 1-4 were written, reviewed (Codex GO) and the snapshot built between 21:33 and 21:41, while gen17 was
running; gen17's outcome was read at 21:42, before fg17 was prepared and launched. The only change made after that
reading is the replacement of the stopped gen18 by gen19 in section 3 (and the seed of the second history with
it). The stages run as two queues so that the short SearchQA stages enter the shared lock's waiting line before
t1's KOR-Bench stages: t2 = fg17; t3 = gen19 (snapshot j, the t1 design) and then fg19.
