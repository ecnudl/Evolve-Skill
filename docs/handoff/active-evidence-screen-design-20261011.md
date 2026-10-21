# Design contract (2026-10-11): evidence-delivery repairs R1-R3 and the composition-aware screen (learning v11)

Follows the reviewer discussion of `active-evidence-attribution-design-20261011.md` (verdict: change direction --
repair evidence delivery, then composition-aware pruning of exact Skill candidates instead of screening raw
minibatch bundles followed by another generative merge). Everything below is frozen before any outcome of the new
runs is read; new stages only (sealed stages keep their snapshots).

## 1. Scientific question and what is NOT claimed

Primary: does choosing ONE exact, measured Skill text among {parent, native candidate, native candidate minus one
applied edit} by its measured result on the step rows give a better Skill than the native updater's candidate?
Contrast: treatment (the screen's selection, the parent on abstention) minus comparator (the native candidate), on a
drawn development holdout; plus each minus the parent; sealed references are descriptive context.

Two meanings of the owner's yardstick are kept apart: (a) the OPTIMIZER generalizes across datasets = one frozen
algorithm and settings trained separately on each dataset (what these stages test); (b) a learned SKILL transfers
across datasets (needs source-to-target evaluation; not tested here). Screen results are TRAINING SELECTION on
analyst-seen rows: never an effect estimate, never "validated edits". The reserved development challenge pool
performs the selection of the outer decision; no canonical validation split is used. A reused development holdout
is development evidence.

Information boundary (narrowed wording): no reference answer, hidden-test text or traceback enters any prompt; the
screen adds score-derived selection information to the optimizer (which exact text survives), from more native
scorer queries on development step rows. Nothing from the challenge pool or its outcomes returns to the screen.

## 2. Repairs to evidence delivery (applied identically to every arm that runs diagnosis)

* R1 judged verdicts. A judged check keeps its epistemic grade (`pending_explanation`: a model judgment, never a
  confirmed fact) but its stored verdict is now rendered: `JUDGED FAIL` / `JUDGED PASS` / `JUDGED UNKNOWN` lines in
  the row report, and a step-summary section "Judged leads" with, per hypothesis, the number of failed and passed
  cases on which a judged check failed. The summary's edit-scope sentence no longer turns "nothing confirmed" into
  "prefer no change": with no executed check at all it says that the absence of confirmed violations is not evidence
  that nothing should change and that judged leads may motivate general, testable procedures (stated as procedures,
  not as confirmed facts); with executed checks it states how many rows they covered. The analysts' evidence
  preamble explains the JUDGED lines.
* R2 complete contracts. The diagnoser's case view uses an active-evidence bound for task text (rule / question /
  prompt up to 24,000 characters, SearchQA context up to 8,000), records original lengths and truncation flags per
  case, and the hypotheses record seals them; the frozen v10 helper is not changed.
* R3 every representative case has a disposition. A case no hypothesis references gets a generic check attempt
  under the pseudo-hypothesis `u0` ("unassigned: check the main obligations of the public contract"); the summary's
  delivery accounting lists `cases_unassigned`. The hypothesis prompt asks for cross-case mechanisms and for every
  case to be assigned (an explicit `unexplained` hypothesis for the rest).

## 3. The screen (`update_mode = "screened"`)

Runs after the native proposal of a step (reflection -> merge -> rank -> apply, unchanged and sealed once) when that
proposal is `candidate_ready`.

* Variants (exact texts, no generative step): `candidate` = the native candidate; `drop_<i>` = the parent with every
  applied edit of the native selection except edit i re-applied in order (only when the native selection has >= 2
  applied edits). A variant whose re-application reports a failed edit, equals the parent (no-op), exceeds the Skill
  budget, or duplicates another variant's text is recorded with that disposition and not scored (duplicates alias
  the first). At most 1 + 8 variants.
* Controls: the parent solved twice under two rollout keys (`parent_a`, `parent_b`): an A/A replicate.
* Rows: every known row of the step rollout (no failure-enriched sampling).
* Rollout keys: `2000 + 100 * step + arm` with arm 0 = parent_a, 1 = parent_b, 2 = candidate, 3.. = drop variants
  (arm <= 99; step <= 99): disjoint from step keys (0..99) and challenge / reference keys (1000..1999).
* Schedule (sealed in the inventory before any outcome): rows shuffled by a seed from the manifest hash and step,
  cut into blocks of 16; within each block the arms run in a seeded random order (one batch per arm and block), so
  controls and variants are interleaved in time. Solver concurrency stays at the policy's 8 workers; stages run one
  at a time.
* Inventory record `screen/<step>/inventory.json` (sealed first): rows (task hash, family, historical status),
  arms (id, kind, dropped edit index, Skill hash and bytes, application report, disposition, alias), schedule,
  rollout keys, selection rule and alpha, expected metric positions.
* Outcome record `screen/<step>/outcome.json`: per row and arm the evidence hash and status; per arm pass / fail /
  unknown; per scored variant the paired table against each control (wins, losses, ties, unknown; by historical
  status), family improving / regressing counts and the exact one-sided sign p (descriptive); the A/A table
  (parent_b against parent_a); the selection with its reason.
* Selection rule `screen-selection-v1` (a screening heuristic, not a confirmation): a scored variant is ELIGIBLE
  when against BOTH controls its task-level net is positive and its family-level one-sided sign p is <=
  `screen_alpha` (0.10). Among eligible variants the largest (net_a + net_b) wins; ties -> fewer Skill bytes ->
  smaller Skill hash. No eligible variant -> ABSTAIN (the parent). Coverage: each control needs >= 90% known rows,
  otherwise the stage is pending (`screen_control_coverage`); a variant below 90% is ineligible.
* Terminal semantics: completed screen with no eligible variant -> the step's candidate is absent (`no_update`, no
  fresh panel spent in method mode). Interrupted or incomplete screen, missing reserve -> pending (no resume).
* Budget reserve (before any diagnosis or update expenditure): screen positions (2 + 1 + edit_budget) x step rows
  are added to the reserved metric positions and (x 2 for length recovery) to the reserved solver calls.

## 4. Evaluation: the selection study (`post_update = "matched_selection_branch"`, requires `screened`)

One rollout, one diagnosis, one native proposal; comparator = the native candidate; treatment = the screen's
selection (`candidate`, a `drop_<i>` variant, or the parent on abstention). Both solve the drawn holdout (242 fresh
positions; 90% coverage; balanced ABBA order between the two); then the parent and the named sealed references
solve it (as in study v2: after the branches, not interleaved -- stated limitation for the parent / reference
contrasts). Records: study v3.

* treatment == comparator text -> `policy_agreement`: the pair is a same-Skill replicate, recorded as such (not a
  measured contrast); the comparator-vs-parent and reference contrasts still stand.
* treatment == parent (abstention) -> a MEASURED contrast "abstain minus native candidate".
* no native candidate -> nothing to select: the study step is a `failed_delivery` (no holdout).
* Reading, fixed now: `useful_gain` / `harmful_change` / `inconclusive` classes as in study v2 with the same
  5-point margin; a selector is expected to move an already strong update by a few points at most, so
  `inconclusive` with the interval reported is the likely outcome and is NOT evidence against the idea; one run is
  one proposal history. A positive contrast supports "this realized pipeline", not the individual edit attributions.
* Family structure: BigCodeBench and SearchQA holdouts have (almost) one task per family; the study statistics
  assume it. KOR-Bench is NOT run in the study tonight (multi-task families need family-level inference there and a
  KOR study takes about ten hours); a KOR method-mode stage is the most that fits.

## 5. Runs planned (settings frozen here)

1. SearchQA selection study: `--arm-feedback diagnosis_research --arm-post-update matched_selection_branch
   --arm-update screened`, parent none, seed 20261006, references `skillopt_v9` and `main_v10`, `G_SKIP_TEST=1`.
2. BigCodeBench selection study: same arms, no named references.
3. If time remains: method-mode stages (`challenge_replay`, `screened`) -- SearchQA, then KOR-Bench (long).
No test read. Every outcome is kept and reported, including abstentions and nulls.
