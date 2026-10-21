# Design contract (2026-10-11, second round, revision 2): a frozen-base refinement pilot on SearchQA

Extends `active-evidence-screen-design-20261011.md` (the composition-aware screen, `update_mode = "screened"`).
Revision 2 replaces the integrated "refinement round" of revision 1 (reviewer verdict: do not build it; run a
frozen-base pilot that isolates refinement first). New stages only. Frozen before any outcome of the new runs is read.

## 1. Evidence that motivates it (zero-call, sealed records of 10/11)

* SearchQA selection study sel1, screen on the 127 known step rows: parent controls 88 / 89 pass (A/A 6 wins / 5
  losses), native candidate 105, leave-one-out variants 98 and 101 -- the screen measures a clear step-row effect and
  agrees with the native candidate.
* The candidate's 22 residual failures on those TRAINING rows (reference answers of development step rows read by
  the researcher for this classification only; never shown to any model): 12 are answer-form mismatches where the
  output contains the reference or the reverse ("Chester A. Arthur" vs "Arthur", "SCTV Network" vs "SCTV",
  "kings of Spain" vs "Spain", "meander" vs "Meandering"), 3 share tokens ("Patty Hearst" vs "Patricia Hearst"),
  7 name a different entity. The validation-gated label-feedback baseline (SkillOpt v9, 3-4 points above the
  unselected v11 branches on the 242-task holdout) carries rules of exactly this kind ("surname only when the clue
  uses the surname", "prefer the most common name, not the most complete one").
* The diagnoser already proposes such form hypotheses from outputs and pass/fail alone (sel1 / m1: "extraneous
  material", "wrong surface form: plural instead of singular, descriptive phrase instead of the canonical term"),
  but nothing ever TESTS a hypothesis against the scorer; its checks are capped at `pending`.

Reading: the missing information is which surface form the scorer accepts. A label-feedback method reads it from
reference answers. This method does not put reference-answer fields into prompts -- but it can ask the scorer: state
a hypothesis as Skill text, let the solver re-answer the step rows under it, and count. That is SCORE-SUPERVISED
search, not a "label-free" method: pass/fail depends on the reference, and a passing solver answer shown with its
PASS is an accepted-answer example.

Information boundary, exact wording: reference-answer fields, hidden-test content and tracebacks are withheld from
models. The optimizer receives solver-generated answers and reference-dependent pass/fail feedback on development
training rows, then selects exact Skill texts using additional scorer queries. This is adaptive, score-supervised
Skill search. Its design was informed by researcher inspection of training references (the classification above)
and of earlier label-feedback Skills (v9's rules); those reference-derived examples are kept out of every model
input. Training selection does not establish generalization. Re-answering tests a whole Skill intervention, not the
truth of a form hypothesis (a shortening instruction can change entity choice, reasoning and surface form together).

## 2. The pilot: one more measured step from a frozen, clean base (no new orchestration)

Base B = the scalar branch candidate of SearchQA study a (`m:<study a>:comparator`; 4,658 bytes; an UNSELECTED
one-step update from the same 128 step rows; pass/fail feedback only, so it never carried the leaked
checker-abstention sentence). It is frozen and sealed; nothing is edited by hand.

The pilot is an ordinary v11 stage started FROM B (`--parent m:<study a>:comparator`, a new parent form bound to the
study's sealed records) with the existing, reviewed machinery:

1. Step rollout under B on the same 128 step rows (B's training outputs).
2. Diagnosis (repaired package: judged leads, whole contracts, no rubric sentence) and the native analysts, who see
   B's exact text, every failed and passed step row under B in their minibatches, and are told (screened mode only,
   `SCREENED_PREAMBLE`) that their edits will be measured individually and that distinct hypotheses about what the
   checker accepts should be separate edits. One frozen proposal batch; no re-proposing.
3. Screen v2 on all known step rows, interleaved: TWO FRESH B controls, the native candidate, each leave-one-out
   variant and (with three or more applied edits) each edit alone. Exact measured texts; no generative merge after
   measurement. Selection `screen-selection-v2`: eligible = against BOTH fresh B controls a positive task-level net
   and a family-level one-sided sign p <= 0.10, with JOINTLY known coverage >= 90% for each comparison; largest summed
   net; ties to the shorter text; otherwise abstain (B stays). The p-values are a screening heuristic; every tested
   arm, rejection and abstention is kept. An outcome-blind heuristic audit of the added text (step-row outputs it
   quotes) is sealed in the inventory before any arm is scored and decides nothing.
4. Holdout (selection study, 242 drawn pool tasks, balanced order between the two branches, then the references):
   comparator = the native candidate, treatment = the screen's selection (B itself on abstention), references =
   the parent B (always), `skillopt_v9`, `main_v10`.

Estimands, named separately:

| question | contrast |
|---|---|
| does the measured refinement improve the frozen base? (PRIMARY) | treatment minus the parent reference B |
| does an unmeasured second native step improve it? | comparator minus the parent reference B |
| does measured selection beat native selection of that step? | treatment minus comparator |
| where does the result stand against the gated Skills? (descriptive) | each minus `skillopt_v9` / `main_v10` |

Reading, fixed now: the paired difference with its Tango 95% interval is primary; the practical target for a
refinement is +2 points (about 5 of 242 tasks) with an interval that excludes 0; the historical 5-point classes are
reported for continuity (a real 3-point gain reads `inconclusive` under them). Same-text pairs (abstention against
the parent reference, policy agreement) are replicates, not effects. A null, a wide interval or an abstention says
nothing about refinement in general: one proposal history, append-biased edits, one benchmark. Narrowing the gap to
v9 would not isolate label access (different learning histories).

Disclosures to be written with the result: study a evaluated B, v9 and v10 on 242 of the 272 pool tasks (none was
chosen by those outcomes); F evaluated all development tasks earlier under other Skills; tonight's designs were
shaped by earlier results on this pool, so this is reused, adaptive development evidence -- not independent
confirmation, and no test data is opened. Reference batches run after the two branches (not interleaved).

## 3. Code changes (all small; no new orchestration)

* `scripts/run_fivebench_g_stage.py`: `--parent m:<study dir>:comparator|treatment` (`parent_skill` /
  `_study_branch`: the completed study stage's own sealed step-0 chain, proposal and Skill hashes; a selection study
  offers its native candidate only); the same loader serves `--reference name=m:...`.
* `screen.py` (v2): single-edit arms, jointly-known coverage, the text audit in the inventory.
* `updater.py`: `SCREENED_PREAMBLE` appended to both analyst systems in screened mode only (every other mode's
  package is byte-identical to before); `reports.py`: the rubric's "exceptions" sentence is no longer quoted in the
  analysts' summary (in every SearchQA stage of 10/10-10/11 with the diagnosis package it came back as a Skill rule
  "abstain rather than guess"; no abstention-like output was found on the sealed holdouts, so no cost was measured).

## 4. Runs (settings frozen here; `G_SKIP_TEST=1`; no test read)

1. `refine1`: SearchQA, `--parent m:<study a>:comparator`, `diagnosis_research / matched_selection_branch /
   screened`, references `skillopt_v9`, `main_v10`, seed 20261006.
2. `rep2`: SearchQA matched-scalar study (parent none) with the repaired package including the rubric-sentence
   removal, same references -- a re-test of the diagnosis package against pass/fail feedback.
Not planned tonight: integrating a refinement round into the stage loop, extending it to another domain -- both
wait for evidence from the pilot.

## 5. Addendum (frozen 04:35 on 10/11, before refine2 or any run below finished)

Same pilot, same reading, no code change; settings recorded here so the later runs are not read as new designs.

3. `refine2` (queued 03:06): base = the unselected repaired-diagnosis branch of rep1 (`--parent m:<rep1>:treatment`,
   seed 20261006), references `skillopt_v9`, `main_v10`.
4. `refine3` (queued 04:31): the pilot on another seed -- base = the unselected repaired-diagnosis branch of rep3
   (`--parent m:<rep3>:treatment --seed 20261007`); no named references (the gated baselines trained on
   seed-20261006 families). refine1 started from a scalar-origin Skill, refine2 / refine3 from diagnosis-origin ones.
5. `refine3s` (queued 04:31; the reviewer's replacement for the coverage run `cov1`, which is dropped for time):
   as refine3 with `feedback = scalar` -- does plain pass/fail feedback plus measured selection improve the same
   frozen base? Its comparison with refine3 is descriptive (different rollout and proposal histories).

6. `refine4` / `refine4s` (queued 04:37, before rep4 started): the same pair as refine3 / refine3s on seed 20261008,
   base = the unselected repaired-diagnosis branch of rep4; prepared by the queue only after rep4 has completed as a
   study (the base is bound to its sealed records) and skipped otherwise. No named references.

Queue note: the first queue script holding refine3 / refine3s (`i1`, 04:31) was cancelled at 04:37 while its first
stage was still waiting for the shared lock (no learning directory, no call) and replaced by `i2` with the same
frozen settings plus item 6, so that the KOR-Bench study stays strictly last.

Reading for all of them (unchanged): PRIMARY = treatment (the screen's selection) minus the freshly evaluated parent
reference; target at least +2 points with an interval that excludes 0; secondary = native candidate minus parent and
selection minus native candidate; a same-text pair is a replicate. If the intervals still contain 0 the statement
is "refinement and selection were exercised; an incremental gain is not established", and integrating a refinement
round into the main loop stays pending. Reused, adaptive development evidence; no test read.
