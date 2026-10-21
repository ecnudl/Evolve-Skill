# Design memo: matched-branch study v2 with holdout reference Skills, first run on SearchQA (learning v11)

Status: design + implementation for review (2026-10-10). Supersedes nothing: the v4 memo
(`active-evidence-label-study-design-20261010.md`) stays the definition of the matched design; this memo adds the
reference branches and fixes the reading of the SearchQA run before it is launched.

## 0. Why

The two matched studies on BigCodeBench (x4, y2) compared two updated Skills with each other and both were
`inconclusive`. A zero-call, post-hoc look (F's No-Skill development baseline on the same holdout tasks) then showed
that neither Skill is distinguishable from NO Skill there (0 to +4 points, all eight intervals contain 0). The design
had no contemporaneous no-update branch, so it could answer "is package A better than package B" but not "does a
no-validation update help at all", which is the project's actual claim (good results without a validation set). Across
the project the only domain with a clearly measurable Skill effect is SearchQA (test: No-Skill 291/400, validation-gated
SkillOpt v9 / GEPA v9 347, validation-gated main method v10 341). The next measurement therefore runs the unchanged v11
method on SearchQA with reference branches. No method change is made for SearchQA.

## 1. Questions (prespecified, in this order)

* Q1 -- no-validation update vs no update: scalar branch S minus parent P, treatment branch M minus P.
* Q2 -- feedback content: M minus S (the v4 primary contrast, unchanged).
* Q3 -- these no-validation Skills vs these validation-gated Skills: S and M each minus B, for B in
  {`skillopt_v9`, `main_v10`}: is the branch "not more than 5 percentage points worse" (the whole Tango 95% interval
  above -0.05) on the contrast's jointly known positions.

* Instrument check (not a question): each named reference minus P. The gated baselines' gain over no Skill is known
  from the test split (about +12 points). "Visible" means the class of that reference's `reference_minus_parent`
  contrast is `useful_gain`; Q3 against a reference is read only when ITS instrument check is `useful_gain` (each
  reference is judged separately; otherwise Q3 for it is reported as not interpretable on this holdout).

Every contrast reports wins/losses/ties/unknowns, d, Tango (1998) 95% score interval, exact two-sided sign test,
the worst-case sensitivity (every unknown counted as a loss of the first-named side), and the v4 outcome class
(`useful_gain` / `harmful_change` / `inconclusive` / `failed_delivery`). All contrasts (seven plus the two instrument checks) are EXPLORATORY and
descriptive: fixed thresholds, no multiplicity adjustment, one training history, one realized candidate per branch.
No claim of a ceiling, and no test number.

## 2. What changes in the code (study v2)

* `protocol.py`: the manifest extension gains `reference_skills` (<= 4 named frozen Skills, each with a provenance
  record; only with `post_update = matched_scalar_branch`); `information_boundaries` gains `holdout_references` for the
  study arm. `validate_manifest` rebuilds it like every other field.
* `challenge.run_references`: after the S and M batches, each reference Skill -- the stage's parent first, then the
  named ones -- solves the SAME drawn `fresh` positions once under its own rollout key
  (`1000 + 10*step + 3 + index`), sealed in `challenge/<step>/references.json` with per-position statuses and the
  paired counts of each branch against each reference. Evaluation only: nothing is selected or deployed from it; no
  additional named reference's text reaches a diagnoser, analyst or Research prompt (the solver sees it as its frozen
  Skill; the parent is the ordinary starting Skill of both updater branches and is of course shown to the analysts).
* `matched.py`: `paired_class` (the v4 statistics/class, factored out, plus a `non_inferiority` flag at the 0.05
  margin); `reference_comparisons`; `STUDY_VERSION = matched-scalar-branch-study-v2`; the matched record carries
  `references`. Chain version v3; identity gate `..._with_holdout_references_nothing_deployed_v2`.
* `stage.reserve_capacity`: the reserve taken before any update expenditure now also holds
  `references x fresh` evaluations (and their length recoveries).
* Tool: `prepare --reference name=g:<finished G stage dir>` (repeatable). `reference_skill()` reads that stage's
  sealed `stage.json` / `learned.json`, requires the same study protocol hash and split hash, a COMPLETED stage whose
  recorded Skill hash matches, and that the stage's `train_families` are disjoint from this stage's challenge pool.
  It does NOT re-verify that stage's learning evidence (stated in the provenance record): the Skill is only solved,
  never used as a parent.
* `diagnosis.py` / `matched.treatment_delivery_problem` (Codex round 1): per-case delivery accounting
  (`checks` / `format_failure` / `no_checks`) sealed in the case record, the summary and the chain; the matched study
  stops pending before any updater call when the treatment package is not delivered, and the matched record's
  `delivered` flag uses the same rule. The method's own arms keep their behavior.
* Codex round 2: the delivery class and the not-applicable records are built from the EFFECTIVE response (the repaired
  reply when a repair parsed) and its own rejection map -- a repair that validly proposes nothing is `no_checks`, and a
  repaired not-applicable item is recorded (this also fixes a pre-existing lookup of repaired items in the first
  reply's rejections); `matched.not_measured` marks unchanged/identical-Skill contrasts and clears both
  non-inferiority flags of every unmeasured contrast.
* Tests: 39 + 3 (was 35 + 2); offline smoke of the study arm writes `references.json`.

## 3. The SearchQA run

* Stage: `--benchmark searchqa --parent none --seed 20261006 --arm-feedback diagnosis_research
  --arm-post-update matched_scalar_branch`, references
  `skillopt_v9=g:/root/fivebench-g-20261006-searchqa-chain-skillopt-v9c` and
  `main_v10=g:/root/fivebench-g-20261006-searchqa-chain-rubric_research-e`.
* Data: F's SearchQA development panel, 400 single-task families (family = exact normalized question); step subset
  128 (the tool's outcome-blind draw), challenge pool 272, holdout 242 drawn after both candidates are frozen,
  `min_paired_known = 218`. One task per family, so the v4 statistics apply unchanged.
* On SearchQA the diagnosis arm is: diagnoser hypotheses -> judge checks (frozen judge prompt with the diagnostic
  focus; graded at most `pending_explanation`) -> itemized reports + step summary. There is no execution and no review
  step on a judged domain, so Research cannot be reached; `diagnosis_research` equals `diagnosis` here. This is the
  method as it is, not a SearchQA adaptation.
* Reference provenance (checked zero-call on the development machine): both reference stages have seed 20261006 and
  the identical 128 train families (hash 45c3f7a02861...), the same study and split, parent = their chain's BCB stage
  which made no update (empty Skill), `selected_update`, Skill 5,357 B and 4,873 B. Their validation data (200 val
  tasks) is not in the development panel. So neither reference was trained or selected on a holdout task.
* Asymmetries, disclosed: the references ran up to 3 update iterations and were SELECTED by a validation gate; S and M
  are one unselected update step each. The F study solved all 400 development tasks under other Skills earlier (never
  shown to this stage's analysts). Reference batches run after S and M, not interleaved.
* The v11 diagnosis path has only run on SearchQA fixtures so far; an infrastructure or format stop is a pending
  record (no automatic resume; a new stage directory after review).
* Budget: 128 step rows + diagnosis (<= ~100 verifier calls) + two updater branches (~40 reflection calls) + 5 x 242
  holdout solves = about 1,500 logical calls; SearchQA calls average ~2.7k tokens (prior QA stages: 4.5-4.9M tokens
  per 1,650-2,040 calls), so about 4M tokens, 60-90 minutes. `G_SKIP_TEST=1`; no final data is read.

## 4. Reading the result (fixed before launch)

* Three states are kept apart for every contrast: `failed_delivery` (the contrast was not measured -- for M minus S:
  undelivered treatment package, treatment proposal not ready, or identical candidates; for a branch minus a
  reference: the branch produced no update (its "Skill" is the unchanged parent, so the pair is a same-Skill noise
  replicate) or is byte-identical to that reference; for a reference minus the parent: the reference is identical to
  the parent; for any contrast: more than 10% unknown positions or fewer than 218 jointly known -- counts and
  intervals are then kept as descriptive diagnostics and no non-inferiority flag can hold), `inconclusive` with
  `interval_includes_both` (unresolved), and `inconclusive` with `worthwhile_gain_excluded` (a gain of 5 points is
  excluded on the jointly known positions).
* Q1 `useful_gain` for S and/or M: this single no-validation update realized a gain over no update on this holdout.
  Anything else is "not shown here", not "no gain exists".
* Q2 as in v4: only `useful_gain` supports "the diagnosis package beats scalar feedback".
* Q3: `non_inferiority.holds` says "this branch's realized Skill is not more than 5 percentage points worse than
  that reference Skill on the jointly known positions of the contrast". A statement about the whole draw additionally
  needs `holds_with_unknowns_as_losses`. It is one-sided (not equivalence), not a test-set claim, and NOT holding does
  not establish inferiority. The comparison is between realized Skills: the references came from up to three
  validation-selected iterations, the branches from one unselected step, so the contrast cannot isolate the effect of
  removing validation -- it can only show whether these ungated Skills reached the level of those gated ones.
* Delivery rule (Codex round 1): if the diagnosis did not complete, attached no row report, or lost more than half of
  its attempted cases to format failures, the step stops pending BEFORE any updater call or holdout evaluation
  (`treatment_package_not_delivered:<reason>`); pending / not-applicable judgments are legitimate results, not
  delivery failures. The per-case accounting is sealed in the diagnosis summary and the chain.
* Budget: the estimate is about 4M tokens and 1,500 logical calls; the configured ceilings (60M tokens, 12,000 API
  calls, 12,000 metric calls) are safety stops far above it, not the plan.
* Whatever the outcome, the method changes that follow are judged across domains with one configuration, not tuned
  to this run.

## 5. Not in this run

KOR-Bench (families are rules: 20 pool rules x 10 tasks, so the one-task-per-family statistics do not apply; a
cluster-level analysis is needed first) and any cross-domain reference (a Skill learned on another domain solved on
this holdout) -- the code allows the latter, the first run does not use it.
