# Design memo v2: post-update decision rule v2 (learning v11) -- a family-level sign test on a fresh challenge panel

Status: design, revision 3 (2026-10-10; Codex design round 1: NOT ACCEPTABLE with seven must-fix items -- see
section 6; round 2: algorithm sufficiently specified, one remaining must-fix on the error statements, fixed here). Replaces the frozen v1 table (`active-evidence-decision-v1`) for NEW stages
only; sealed stages keep their own code snapshot and records.

## 0. Evidence that v1 must change (zero-call, from sealed records)

v1: after an update, both Skills re-solve 24 fresh challenge-pool tasks, 16 replay rows and 8 local-fix rows; keep
when fresh net wins >= 2 and replay regressions <= 2; revert when regressions > 2 or fresh net < 0; else park.

* Same-configuration BCB stages r / s / v ended fresh net +4 / 0 / 0; x4's 242-task holdout net +3 (95% interval
  [-0.038, +0.064]) would have been "keep".
* Table below (`active-evidence-decision-rule-oc-20261010.py`, exact, count-only). It gives CONDITIONAL RESAMPLING
  FREQUENCIES from fixed, realized, jointly known paired outcomes of the three matched studies -- sampling n
  positions without replacement from the realized 240-242 positions ("finite"), and independent draws at the same
  plug-in rates ("independent"). It evaluates only the FRESH COMPONENTS (v1's net-wins rule on 24 positions; v2's
  one-sided sign tests on 96 positions), not either complete procedure: no replay veto, no unknown positions,
  single-task families only. The frequencies contain no new solver randomness and no candidate-generation
  uncertainty and do not establish future power or error rates. The BigCodeBench No-Skill rows use F's baseline of
  2026-10-01: non-contemporaneous, added retrospectively, not a prospective null control.

  | realized contrast (candidate minus parent; wins / losses) | v1 fresh: keep | v1 fresh: revert | v2 fresh gain test | v2 fresh harm test |
  |---|---:|---:|---:|---:|
  | SearchQA S minus empty parent (observed +10.4 points; 28 / 3) | 0.725 (0.713) | 0.018 | 0.931 (0.882) | 0.000 |
  | SearchQA M minus empty parent (observed +11.3 points; 29 / 2) | 0.769 (0.756) | 0.010 | 0.973 (0.938) | 0.000 |
  | SearchQA M minus S (observed +0.8 points; 6 / 4) | 0.080 | 0.204 | 0.005 (0.023) | 0.000 |
  | BCB S or M minus No-Skill replicate 0 (observed 0 to +1.7 points; four contrasts) | 0.18-0.25 | 0.30-0.38 | 0.007-0.030 (0.026-0.070) | 0.001-0.007 |
  | BCB S or M minus No-Skill replicate 1 (observed +2.9 to +4.1 points; four contrasts) | 0.31-0.38 | 0.18-0.24 | 0.071-0.150 (0.125-0.210) | 0.000 |
  | BCB No-Skill replicate 1 minus replicate 0 (observed -2.5 / -3.3 points) | 0.05-0.07 | 0.52-0.57 | 0.000 | 0.056-0.103 |
  | BCB M minus S (observed +1.2 / +0.4 points) | 0.19-0.25 | 0.33-0.35 | 0.010-0.022 (0.034-0.057) | 0.003-0.004 |

  (finite-population frequency; independent-draw frequency in parentheses where it differs materially; the
  independent-draw harm frequencies of the two No-Skill replicate contrasts are 0.108 and 0.164.)
  What the table supports: on these realized outcomes, v1's fresh component keeps an observed +10 point difference
  about three times in four and keeps or reverts contrasts compatible with zero with frequency 0.2-0.4 each -- its
  thresholds sit inside same-Skill noise (an identical Skill run twice flips 6-10% of positions). What it does not
  support: any statement about the complete v2 procedure's operating characteristics on future candidates.

## 1. The rule (v2)

**Unit of evidence: the family.** For each family with at least one jointly known position in a set, its net is
(candidate wins - candidate losses) over that family's jointly known positions; the family is improving (net > 0),
regressing (net < 0) or tied. Single-task families (BigCodeBench, SearchQA): the per-task paired outcome. KOR-Bench
(family = rule, several tasks per rule): the per-rule direction.

**Test and its null.** Exact one-sided sign test on improving vs regressing families,
`p_gain = P(X >= improving | improving + regressing, 1/2)`, `p_harm` symmetric. The effective denominator is the
number of NON-TIED families. Null: conditional on the eligible challenge pool, the frozen allocation (round-robin
over families, tasks drawn by an earlier step of the same stage excluded) and on a family being non-tied, family
signs are independent and fair. For single-task families this is the usual paired directional test. For multi-task
families it tests RULE DIRECTIONS, not aggregate accuracy (15 rules gaining one task and 5 rules losing four each
give p_gain = 0.021 with total net -5); therefore keep additionally requires the **aggregate guard**: the
task-level net wins over all jointly known fresh positions is strictly positive.

**Unknown positions.** Inference is about the jointly observed positions; unknowns stay recorded as unknown. Keep
must additionally survive the **adverse completion**: every fresh position with an unknown side is counted as a
candidate loss, family nets and the aggregate net are recomputed, and both the sign test (`p_gain_adverse <= alpha`)
and the aggregate guard must still hold. Harm flags are computed on jointly known positions only (revert and park
both carry the parent, so no sensitivity is needed there).

**Execution order (new).** v1 ran the parent's whole batch before the candidate's, so service drift between batches
could masquerade as an effect. v2 freezes a balanced order per set: the drawn positions are split into two halves by
a seeded shuffle (seed from the manifest hash, step and set name); half A runs parent then candidate, half B runs
candidate then parent (ABBA); with an odd count half A has the extra position. Each Skill keeps its own rollout
key; the half membership and the block order are sealed in the outcome (`execution_order: balanced_abba_v1`). The
balanced order counterbalances a monotone drift between batches; it does not prove exchangeability, family
independence, or immunity to nonlinear drift or unequal batch durations -- exchangeability under no effect remains
an assumption. A statistic that cannot be computed (an empty set) is recorded as null with its reason.

**Replay.** Rows the parent passed on the step rollout, both Skills re-run. It is a HARM-only test (the analysts saw
these rows, so replay is never evidence of gain), and its conclusion concerns those selected rows, not harm across
the domain. Re-running both Skills removes the historical-pass baseline bias; symmetry of fresh paired outcomes
under no effect is the exchangeability assumption above.

**Precedence (top to bottom; alpha = 0.05):**

1. no candidate, or identical to the parent -> `no_update`
2. the arm runs no post-update challenge -> `accepted_without_challenge`
3. the challenge did not run (the draw has no eligible fresh task) -> `park` (insufficient evidence); nothing is
   evaluated in that case -- replay and local-fix rows alone never decide. (A missing budget reserve is an
   infrastructure stop: the stage goes pending, outside this table.)
4. replay `p_harm <= alpha` -> `revert` (`replay_harm_significant`)
5. fewer jointly known fresh positions than `min_paired_known` -> `park` (`fresh_decision_inadmissible`)
6. fresh `p_harm <= alpha` -> `revert` (`fresh_harm_significant`)
7. fresh `p_gain <= alpha` AND aggregate guard AND adverse completion -> `keep`
8. anything else -> `park`

`revert` = harm was shown on the stated rows; `park` = no admissible evidence of gain; both carry the parent. Every
decision record stores both harm flags, `p_gain`, `p_gain_adverse`, the aggregate nets and the drawn / jointly known
/ tied / non-tied family denominators, whatever the action.

**Error statements -- for ONE candidate-decision step.** Null, applied to EACH set separately (fresh; replay):
conditional on the frozen candidate and all preceding history -- for the fresh set on the eligible pool and the
frozen allocation, for the replay set additionally on the historical-pass selection of its rows -- the observed
non-tied family signs are independent and fair. The balanced order motivates fairness under no effect; it does not
establish independence across families, which is an assumption. Under these nulls, for one step: keep requires
rejection by the single fresh gain test, so P(keep) <= alpha; each of the two harm tests rejects with probability
<= alpha, so P(revert) <= 2 alpha by the union bound (no independence between the two tests is needed). Every
tested step of every stage is one such decision; a multi-step stage or a chain runs several, and neither a
stage-wide nor a chain-wide 5% guarantee is claimed without additional multiplicity control.

**Limits (sealed before any challenge outcome exists).** Requested `fresh_tasks = 96`, `replay_rows = 32`,
`local_fix_rows = 8` (reported, never a decision input), `decision_alpha_permille = 50`; `min_net_wins` and
`max_regressions` are removed. Effective counts are fixed by the tool at preparation and written into the manifest:
`n_eff = min(requested fresh, eligible challenge-pool tasks)` and `min_paired_known = ceil(0.90 * n_eff)` (87 for
96; the matched study on KOR-Bench's 200-task pool gets 200 / 180 instead of 242 / 218); the protocol validates
`min_paired_known >= ceil(0.90 * fresh_tasks)`. Replay and local-fix counts are capped separately by the available
passed / failed step rows at draw time and never reduce the fresh count. Preparation refuses a challenge arm whose
pool is empty from the start; a pool exhausted by earlier steps of a multi-step stage gives an empty fresh draw ->
the challenge is `not_run` (`no_eligible_fresh_tasks`, nothing evaluated) -> park (step 3). Later steps of a multi-step stage may find the pool depleted: fewer drawn positions
than `min_paired_known` -> park (step 5). A smaller pool lowers power; alpha is never relaxed (KOR-Bench: at most 20
evidence units).

## 2. How the operating point was chosen

A uniform rule for every domain; nothing in it depends on the benchmark. The operating point (n = 96, alpha = 0.05)
was chosen using development evidence, including the SearchQA study's observed discordance (about 13% of positions),
and is frozen prospectively from here on. That is not independent validation of the rule. The three method-mode
stages below are a prospective end-to-end exercise, not a calibration: three runs cannot verify a 5% error rate.

## 3. Cost

Per step: 2 x (96 + 32 + 8) = 272 solver calls after the 128-row (KOR-Bench: 90-row) step rollout, against 96 under
v1. No sequential stopping in this version (it would add looks and boundaries; on domains without an effect it uses
the maximum sample anyway).

## 4. What is and is not claimed

* The decision uses **a fresh panel sampled from a fixed reserved development challenge pool** (families disjoint
  from the step families, fixed at preparation) -- no canonical validation split and no repeated full-panel
  validation passes. The reserved pool does serve a selection function; "drawn after the candidate is frozen"
  describes sampling time, not the absence of a held-out partition. "Fresh" means not drawn by an earlier step of
  the SAME stage; separate stages can reuse pool tasks. Documents use this wording, not "without validation data".
* The SearchQA study's branches S and M were single UNSELECTED update steps (no decision rule at all); that result
  is about an ungated update, and the realized-Skill comparison there cannot isolate the contribution of validation
  gating (ledger, unchanged).
* v2 does not improve the diagnosis arm: on BCB (y2) and SearchQA these realized candidate comparisons did not
  establish a difference between the diagnosis package and the scalar package. v2 replaces a decision that acted at
  noise level on the realized outcomes with one whose assumptions and error statements are explicit.

## 5. Implementation plan

* `decision.py`: `RULE_VERSION = active-evidence-decision-v2`; `decide()` reads the sealed challenge summary; the
  record carries the fields listed in section 1.
* `challenge.py`: balanced ABBA execution order in `run`; `_summary` adds `family_harm_p_value`, tied / non-tied
  family counts and the adverse-completion summary; decision inputs come only from the sealed outcome.
* `protocol.py`: limits schema of section 1 (`decision_alpha_permille` in [1, 200]; the 90% validation).
* Tool: effective limits computed before `ae.manifest(...)`, recorded in `stage.json` together with the requested
  values.
* Tests: every precedence branch, single-task and multi-task families (including the 15-vs-5 aggregate-guard case),
  adverse completion (5 wins, 0 losses, 82 ties, 9 unknown must NOT keep), the balanced order, the caps, depletion,
  and the existing end-to-end fixtures moved to the new limits; offline smoke.
* Then three method-mode stages with the unchanged method (`diagnosis_research / challenge_replay`, parent none,
  `G_SKIP_TEST=1`): BigCodeBench, SearchQA, KOR-Bench. Settings are frozen before launch and every outcome is kept.
  Expectations stated beforehand, NOT success criteria: SearchQA keep, BigCodeBench park, KOR-Bench open. No test
  cell is read; a test read is left for when the method is declared frozen.

## 6. Design round 1 must-fix items and where they are addressed

1. Null and estimand (rule directions vs aggregate) -> section 1 "Test and its null", aggregate guard.
2. Unknowns and execution order -> "Unknown positions" (adverse completion), "Execution order" (balanced ABBA),
   "Replay" (scope and exchangeability assumption).
3. Table relabelled and narrowed; exact enumeration; both sampling models -> section 0.
4. Development-informed parameter choice disclosed -> section 2; the "only makes the decision reliable" sentence is
   replaced in section 4.
5. Cap specified (n_eff, ceil(0.90 n_eff) = 87, separate replay / local-fix caps, zero eligible, depletion, KOR
   study 200 / 180, effective limits before manifest validation) -> section 1 "Limits".
6. "Fixed reserved development challenge pool" wording; "fresh" qualified -> section 4; the ledger paragraph of
   10/10 16:20 carries it already, the workflow and v11 documents are aligned together with the implementation.
7. Precedence: replay harm before the fresh-coverage gate; park vs revert defined; P(revert) <= 2 alpha; no
   chain-wide guarantee -> section 1 "Precedence" and "Error statements".

## Addendum (2026-10-11 05:45-06:20, frozen before any of these stages ran): more method-mode stages, rule unchanged

Decision rule v2, its limits and its error statement are unchanged; these are further one-step method-mode stages
(`G_SKIP_TEST=1`, no test read), queued behind the shared lock:

* `searchqa-active-ms1` (snapshot h): `diagnosis_research / challenge_replay` with `update_mode = screened`, seed
  20261008 -- the first method-mode stage with the composition-aware screen (run item 3 of the screen design memo).
  An abstention of the screen ends the step as `no_update` without spending the fresh panel.
* `searchqa-active-sm06` ... `sm10` (snapshot h): `scalar / challenge_replay / native`, parent none, seeds 20261006
  to 20261010 -- pass/fail feedback only, no diagnosis package, no screen. The synthesis review of 05:40 named
  "scalar one-step update + decision v2, screen off" as the default candidate for a frozen policy; until now
  decision v2 had only been exercised together with the diagnosis package (m1, m2).
* `bigcodebench-active-bsm06` (snapshot h): the same arms on BigCodeBench, seed 20261006.

Expectation written beforehand (not a success criterion): SearchQA keep, BigCodeBench park. Reading: each stage is
one candidate-decision step with its own fresh panel of 96 from the reserved development pool; decisions are listed
per stage with wins / losses / the family-level p-value; a keep is a decision of the rule on reused development
data, not an independent confirmation, and the frequency of keeps over five seeds is descriptive (seeds share most
of the pool). Queue note: the lock grants in arrival order; queue i2 was replaced by i3 at 06:21 (its waiting stage
had not begun) so that the six-hour KOR-Bench study starts only after every short stage has finished.
