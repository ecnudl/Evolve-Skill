# Reflection and proposal (2026-10-11): measured patch attribution on step rows (learning v11)

Status: proposal for discussion with the reviewer before any code. The owner's request: improve the Skill-evolution
module, find and fix verification-module parts that do not work or work poorly, keep experimenting; budget is not a
constraint (GLM-5.3 low, at most 10 concurrent calls). The standing yardstick: generalization across datasets and good
results without a canonical validation split; no per-dataset tuning.

## 1. What the sealed records say (audit of 2026-10-11, zero-call)

Results so far (development holdouts / fresh panels only; no test read by v11 since 10/9):

* BigCodeBench: two matched studies and one method-mode stage -- updated Skills indistinguishable from each other and
  from no Skill (0 to +4 points, every interval contains 0); decision v2 parked the m1 candidate (5 wins / 4 losses).
* SearchQA: one unselected update step = +10.4 / +11.3 points over no Skill (242-task holdout), on par with the
  validation-gated v10 Skill, 3-4 points below the label-feedback SkillOpt v9 Skill; decision v2 kept the m1
  candidate (13 wins / 0 losses of 95). The diagnosis package did not differ from pass/fail feedback (M - S +0.008).
* KOR-Bench: m1 candidate parked (task level 11 wins / 9 losses; 4 improving / 5 regressing rule families).

Verification (diagnosis) module, from the sealed check records:

1. Coverage: hypotheses and checks exist for 16 representative cases only; rows with a report: 4-9 of 128 on BCB,
   16 on SearchQA, 14 on KOR. In BCB m1 each of the four hypotheses explains one case and 10 of 16 cases (4 failures)
   are referenced by no hypothesis, so they get no check.
2. BCB executed checks do not discriminate: on FAILED outputs they mostly pass (y2 4 pass / 1 error; r 2 pass; v 1
   pass; m1 1 fail / 1 pass / 1 error). Seven stages: one `confirmed_violation`, task-specific.
3. Probe attrition: strict validation (quote not a substring, inexact fields, wrong hypothesis id, structure quote
   without the expected labels) plus review drops leave 4-8 executed checks per stage.
4. Judged domains: the judge has signal that the pipeline throws away. SearchQA (two runs): 5 of 8 failed cases get a
   failing judged check, 0 of 8 passed cases do; KOR: 3 of 6 vs 0 of 5. But judged checks are capped at `pending`, so
   the step summary always says "0 confirmed violations ... prefer no change or a minimal clarification; do not add
   rules for pending items", and analysts quote that sentence when returning an empty patch.
5. Case views truncate long KOR rules; the diagnoser then hypothesizes about "the truncated portion".
6. Research: unreachable on judged domains by construction; reached once in seven BCB stages (a trivial fact).
   Declared fact needs are mostly about scorer or third-party-library behavior the whitelist cannot answer.

Updater (Skill-evolution) module:

7. One patch per minibatch, almost always `append`; the native merge often folds every failure-side edit into one or
   two large sections; the edit budget (4) rarely binds; success-side "keep doing this" sections take up to 3 of 4
   selected edits (KOR).
8. **Nothing measures what an individual patch does.** Selection is by model ranking and support counts; the
   candidate is compared with the parent once, as a whole, at the end.

Reading. The diagnosis module was built to hand the analysts discriminating evidence. On BCB the public contract
cannot supply it; on judged domains nothing can be executed, so nothing can be confirmed. Yet the stage already
owns a trusted, discriminating instrument that needs no private data in any prompt: the native scorer on step rows.

## 2. Proposal: patch attribution by intervention on step rows

Hypothesis -> intervention -> observation, with the native scorer as the trusted computation.

* Units: the raw minibatch patches of the step's reflection (17 on BCB / SearchQA, 13 on KOR), each applied alone to
  the parent ("micro-candidate").
* Rows: every FAILED step row plus a seeded sample of PASSED step rows (default 32).
* Control: the parent re-solved on the same rows under a fresh rollout key (an identical Skill run twice flips 6-10%
  of positions; a patch is compared with the control re-run, never with the historical status).
* Observation per unit: paired wins (unit passes, control fails) and losses on those rows; exact one-sided sign test.
* Selection: a unit is admitted when its paired net is positive and p <= alpha_attr (proposed 0.10). No admitted unit
  -> `no_update` without spending the fresh panel.
* Composition: the native merge -> rank -> select -> apply pipeline, restricted to the admitted patches. Everything
  downstream (decision v2 on a fresh panel from the reserved pool) is unchanged and remains the only evidence of gain;
  attribution is selection on analyst-seen rows and is reported as such, never as an effect estimate.
* Information boundary: unchanged class of information -- pass/fail of the solver's own outputs on development step
  rows. No hidden test, traceback or reference answer reaches any prompt; analysts see nothing new in this version
  (attribution only filters their patches). The number of native scorer queries per step row rises from 1 to
  1 + units + 1.
* Cost per step: (units + 1) x (failed + 32) solver calls: SearchQA about 18 x 73 = 1,300 calls (about 3M tokens,
  ~12 min at 8 workers); BCB about 18 x 94 = 1,700; KOR about 14 x 57 = 800 (slow calls, hours).

Why this and not the alternatives considered:

* Inner refinement loop (re-reflect on still-failing rows): SkillOpt v9 / v10 ran three gated iterations on SearchQA
  and accepted one, so later iterations did not show detectable gains there.
* More step rows (256 instead of 128): legitimate reallocation of the data a validation split would use, but it does
  not address item 8 and changes the comparison with the baselines' 128 training rows.
* Label feedback (reference answers / test messages to analysts): closes the SearchQA gap by construction and was
  shown not to help on BCB (x4); it is the baselines' information source, not this method's.
* Repairing the probe / judge checks alone (items 1-6): cheap and worth doing, but two matched studies say the
  analysts' package does not change the outcome; it cannot be the main lever.

Smaller repairs in the same round (verification module):

* R1 judged domains: the summary must not turn "nothing was executable" into "prefer no change"; report judged
  verdicts as leads with their counts on failed vs passed cases, and drop the no-change advice when no check could
  be executed at all.
* R2 raise the case-view task-text bound so KOR rules are not truncated (bounded by the prompt-size limit).
* R3 hypothesis prompt: mechanisms must span cases where possible and every representative case must be assigned to
  a hypothesis or to an explicit "unexplained" bucket (so every case gets checks).

Later, if attribution works: diagnoser hypotheses carry a candidate rule and enter attribution as extra units
(hypotheses tested by the same trusted computation); attribution results fed back to a second reflection.

## 3. How it would be evaluated

Matched design with the reflection shared: one rollout, one reflection (raw patches), then two selections from the
SAME raw patches -- comparator = today's native selection (merge -> rank -> select on all patches), treatment =
attribution-restricted selection -- both frozen candidates plus the parent and the two sealed SearchQA references
(`skillopt_v9`, `main_v10`) on the same drawn 242-task holdout (study v2 machinery, balanced order). Prespecified
reading: treatment minus comparator (does measured selection beat model ranking), each minus parent, each minus
references. First on SearchQA (has headroom), then BigCodeBench (expected: no admitted unit or no effect -- "no
update" is the correct outcome there), KOR-Bench last because of its run time. Method-mode stages afterwards.

## 4. Questions for the reviewer

1. Is attribution on analyst-seen step rows a sound selection device given the final fresh-panel decision, or does
   it invite a failure mode I am missing (e.g. selecting patches that repair those rows by memorized specifics; the
   transfer preamble forbids task-specific content but nothing enforces it)?
2. Units: raw minibatch patches (proposed) vs merged edits vs diagnoser hypotheses -- which is the right first unit?
3. The admission rule (net > 0 and one-sided p <= 0.10, no multiplicity adjustment because the fresh panel decides):
   too strict (drops small real effects), too lenient, or should it be a ranking with a cap?
4. Is anything in the information-boundary statement wrong: more scorer queries per development row, same kind of
   information, nothing new in any prompt?
5. Which of R1-R3 belong in this round, and is there a verification-module defect in section 1 that deserves more
   than a repair?
6. A better lever than attribution that the evidence supports?
