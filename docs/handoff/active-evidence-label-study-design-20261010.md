# Design memo v4: bounded development failure-message feedback, matched-branch study (learning v11)

v4 = v3 with the one remaining must-fix item of the third review resolved: A1 now prespecifies Tango's (1998) score
interval for the paired difference (used for classification AND the worst-case sensitivity bound) instead of the
Wald interval. Sections A2-A5 and the body (B) are unchanged from v3.

## A. Amendments (second-review must-fix items 1-5)

**A1. Statistics (items 1 and 7-of-v1; revised in v4).** Estimand: the paired pass difference, treatment M minus
comparator S, over JOINTLY KNOWN holdout positions. Reported: wins (b) / losses (c) / ties / unknowns; the point
estimate d = (b - c) / n; its 95% interval = **Tango's (1998) score interval for a paired difference of
proportions** (score statistic (b - c - n·delta) / sqrt(n(2·p21~ + delta(1 - delta))) with p21~ the restricted MLE of
the loss-type discordant probability under H0: difference = delta; bounds by bisection; at delta = 0 it is the
McNemar statistic); an exact TWO-sided sign test on discordant pairs. Both are implemented in `matched.py`; the
challenge summary's `family_p_value` keeps using the frozen ONE-sided `skillopt.sign_test_p` and is recorded as such,
never used for the outcome class. Validation of the implementation (scratchpad run, seed 7, 2000 replications per
scenario, n = 218): coverage 0.943-0.960 for (p12, p21) in {(0.05, 0), (0.08, 0.03), (0.03, 0.03), (0.15, 0.10),
(0.12, 0.07; n = 242)}, 0.994-1.0 for the degenerate (0.01, 0) and (0, 0); the reviewer's counterexample b = 6,
c = 0, n = 218 gives [0.0097, 0.0587] (0.05 NOT excluded); under true difference 0.05 with no possible losses the
rule "upper bound < 0.05" fires in 1.8% of replications (<= alpha/2). The same interval is used for the worst-case
sensitivity bound. The Clopper-Pearson win-share interval, the Wald interval and the "net-wins interval" are dropped.
Outcome classes:
* `useful_gain`: d >= 0.05 AND two-sided p <= 0.05 AND the Tango lower bound > 0; additionally flagged
  `robust_to_unknowns` only if the worst-case bound (every unknown position counted as a treatment loss, interval
  recomputed over known + unknown) still satisfies d >= 0.05 with lower bound > 0.
* `harmful_change`: mirror image (d <= -0.05, p <= 0.05, Tango upper bound < 0).
* `inconclusive`: otherwise; `worthwhile_gain_excluded` is stated ONLY when the Tango upper bound < 0.05 (a
  statement about jointly known positions, not about all 242; valid at zero discordance -- with n = 218 concordant
  pairs the interval is [-0.0173, 0.0173]); otherwise `interval_includes_both`. The discordant count is always reported.
* No claim is a "channel ceiling"; a null is one candidate pair under one updater.

**A2. Unknowns (item 2).** Conclusions are restricted to jointly known positions, stated in every record. The step
is a `failed_delivery` (`insufficient_jointly_known_holdout_pairs`) when unknowns exceed 10% of drawn positions or
known < `min_paired_known` (set to 218 = 90% of 242, not 100). Unknown counts per side (`candidate_unknown`,
`current_unknown`, `both_unknown`) and the worst-case sensitivity above are always reported.

**A3. Extraction boundary (item 3).** No fallback: a traceback without a line matching the exception-class pattern
is ambiguous and is NOT released (counted `tests_withheld`). After extraction every message and the assembled row text
must pass a forbidden-content check -- `Traceback (most recent call last)`, `File "`, `line N, in`, absolute paths,
and any line indented by two or more spaces (source lines) -- or it is withheld; a row with nothing left is not
released (counted). The sealed `release_audit.json` records, per row, `source_details_hash`,
`released_payload_hash`, tests total/shown/withheld/truncated and message classes; the stage checks the audit
(`rows_released >= 50% of host-fail rows`) BEFORE any updater call and otherwise stops the step as
`failed_delivery` (pending record, no automatic resume, parent carried).

**A4. Holdout framing (item 4).** The 272-task pool already supplied the 24-task fresh challenges of r, s, t and v
(up to 96 distinct pool tasks solved under earlier Skills, results in those stages' ledgers; never shown to any
analyst). The new draw is therefore a REUSED development evaluation, not untouched data: the zero-call report
records the overlap of the drawn 242 with each earlier stage's fresh draw. One task per family by construction;
family independence is an ASSUMPTION of the sign test and interval, stated as such (no semantic-independence
audit). Memorisation of step-task specifics cannot be excluded in principle for semantically similar pool tasks;
the claim is only that pool tasks are disjoint from the 128 step tasks.

**A5. Mechanism (item 5).** An explicit-attribution audit (zero-call): does the reasoning of the selected edits (and
of the per-minibatch raw proposals) cite released content -- a test name, an exception class, a quoted value or the
words "hidden test"/"failure message"? Attribution present -> "messages cited by the edits"; absent -> **mechanism
unknown**. Reported separately from delivery (`release_audit`), candidate difference (hashes, bytes, diff lines)
and the holdout outcome class; never collapsed into "messages did not shape the edits".

## B. Body (v2, with superseded passages marked)

### 0. Question
Holding the parent Skill, the training rollout, the updater, seed, minibatch grouping, edit budget and the (absent)
selection policy fixed, does adding the final exception messages of the failing hidden tests of FAILED development
step rows to the analysts' [verification] turn produce a candidate Skill that beats the matched scalar-feedback
candidate on a drawn development holdout (reused pool)? Exploratory; two realized candidates; one training history.

### 1. Naming and outcome classes
Intervention: **bounded development failure-message feedback**. Classes `failed_delivery` (released rows < 50% of
host-fail rows; identical candidates; treatment proposal not ready; holdout unknowns > 10% or known < 218),
`useful_gain`, `harmful_change`, `inconclusive` -- definitions in A1/A2 (supersede v2's Clopper-Pearson rule).

### 2. The frozen contrast
One stage, one rollout (parent = empty Skill, same 128 development step tasks and seed as r/s/v), two updater
branches from the SAME bound traces: branch S = `propose_with_evidence(traces without evidence, reports=None,
summary=None)` (byte-identical analyst package to the r-scalar control); branch M = the same call with the label
reports and the fixed LABEL summary/preamble (estimand = the whole feedback package). Same seed, minibatch grouping,
edit budget (4), reflect -> merge -> rank -> apply; no challenge-based selection on either side. Both frozen
candidates solve the same drawn holdout; the step's decision record names M "candidate" and S "current" so the
existing paired machinery applies; it is a study record, nothing is deployed (`current` never advances;
`learned.json` = `completed_no_update`; `G_SKIP_TEST=1`). Implementation: `post_update = "matched_scalar_branch"`,
registered only together with `feedback = "hidden_failure"` (and vice versa), branch S in `native_matched/<step>/`,
branch M in `native/<step>/`; chain records both proposal/candidate hashes, edit counts, fallbacks, prompt-system
digests, byte sizes and the unified-diff line count.

### 3. Protocol-level authorization
`manifest()` seals arm-specific `information_boundaries` (the `private_scoring_data` promise is replaced for this
arm) and a `release_profile` (`development-failure-messages-v1`: constants, ordering, forbidden-content check, who
sees what): analysts of branch M only -- test names and final exception messages (expected/actual values inside
messages ARE released) of FAILED development step rows; hidden test code, canonical solutions, reference answers:
never; solver: frozen Skill + ordinary task input; diagnoser/reviewer/Research: not run; branch S analysts: pass/fail
only; holdout tasks: solved by both Skills, never shown to analysts; final/held-out: never read. New output
directory and protocol hash; frozen runs untouched; `profiles.INFORMATION_PERMISSIONS["never"]` made arm-conditional
in the sealed manifest.

### 4. Extraction policy and audit
Source `score.metrics.details` (dict test name -> traceback; non-dict/empty -> nothing, counted; keys taken as
given). Per traceback: LAST exception-class line starts the message (chained -> final); blank lines collapsed; frame
headers removed; absolute paths -> `<path>`; bounded 400 chars; sorted test names, first 4, header states totals and
withheld counts. Forbidden-content check and no-fallback rule per A3. Dry run on stage r's sealed rollout (v2
policy): 66/66 failed rows with details, 225 failing tests, 184 shown / 41 omitted by the cap, 10 truncated;
classes of shown messages: typed_error 85, value_diff 65, other_assertion 14, bare_assertion 11, not_raised 9
(s and v rollouts: the same shape). Figures under the v3 policy are recomputed before launch and recorded.
Acknowledged: v8/v9 BCB learning already released exception class, failure location and candidate source lines; the
new information is the message content.

### 5. Holdout and paired analysis
`fresh_tasks = 242` drawn family-stratified from the 272-task pool after both candidates are frozen; `replay_rows =
0`, `local_fix_rows = 0`, `min_paired_known = 218`. Rollout keys 1000 + {0: S, 1: M}; requests per Skill in two
consecutive batches within the same hour and model-service identity (interleaving not implemented; drift risk
stated). Statistics per A1; unknowns per A2; framing per A4.

### 6. Information-to-behavior chain
Sealed: released rows and hashes; rows that reached analyst prompts (`conversation.json` system turns; proposal
identity `evidence_rows`); raw per-minibatch proposals, merged patch, ranking, selected edits, fallbacks, parser
audits; both candidates' hashes/bytes/diff; analyst system digests; model/runtime identity; costs. Attribution audit
per A5 (mechanism known / unknown).

### 7. Generality claim
Benchmark-specific supervised learning is explicitly permitted: the M Skill may encode BigCodeBench hidden-test
conventions; that is what the holdout measures. `label_echo` (quoted literals >= 4 chars and test names from released
messages found verbatim in the M Skill) is a descriptive count only.

### 8. Test reuse disclosure
The final panel has been read for reporting by every BCB chain and by the r/t cells on 10/9; the direction of this
study was informed by those numbers. This study reads no final data and produces no test number; any later test
cell from this line would be a disclosed exploratory single cell; historical scores stay frozen.

### 9. Step 0 wording
Prompt sensitivity, not rule compliance; dependent comparisons; exploratory features; "no confirmed violation in six
stages, Research never reached" replaces "learning signal empty"; r/r-diag statuses keep their documented
qualification.

### 10. Budget
~128 + 2 x ~22 + 2 x 242 = ~660 logical calls, ~0.7-0.9M tokens, ~45 min; no test cell; pending on infrastructure
failure (no automatic resume).
