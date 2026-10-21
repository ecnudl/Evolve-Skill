# Design contract (2026-10-11, afternoon): an in-sample shadow reading next to decision rule v2

Extends `active-evidence-decision-v2-design-20261010.md`. Snapshot `20261011-i` = `h` plus this change. Frozen
before any stage with the new limit is launched. Direction review by Codex (GPT-6-Astra, ultra, read-only):
proceed as a FALSIFICATION PILOT; its required changes are incorporated below.

## 1. Why

The owner's yardstick is good results without a validation set. Decision rule v2 decides keep / park / revert on a
fresh panel drawn from a fixed reserved development pool: no canonical validation split is touched, but the pool
is a validation-like use of data, and it has little power where the training split is tiny (SpreadsheetBench 80
tasks, ALFWorld 39). The sealed method-mode stages already hint that the training rows carry the same direction:
on SearchQA the 8 local-fix rows went 4/0, 4/0, 6/0, 2/0, 4/0, 3/0, 3/0 (candidate wins / losses) in seven `keep`
histories; on BigCodeBench 0/1 and 0/0 in two `park` histories; on KOR m1 1/1 (`park`). Those sets are selected on
the parent's outcome and far too small to test anything. This change measures the question properly:
**would a decision made on training rows alone have agreed with the reserved-pool decision, and is the in-sample
effect inflated relative to the fresh one?**

Post-hoc sealed evidence found after this memo was frozen and before any pilot outcome existed (zero-call,
[active-evidence-screen-insample-20261011.py](active-evidence-screen-insample-20261011.py); ledger 10/11 14:55):
last night's nine screened stages solved all 128 step rows under two parent controls and the native candidate.
For first steps from the empty Skill the in-sample effect matched the held-out one (SearchQA sel1 +0.13 on
training rows against +0.10 held out; BigCodeBench -0.02 / -0.04 against -0.03; ms1's held-out number concerns the
screen's selected variant, not the native candidate, so it is same-sign only); for second-step refinements both
were noise-level. No history showed a significant in-sample gain with a negative held-out
effect. This is descriptive background, not part of the pilot's reading.

## 2. What is added (default off; the acting decision is unchanged)

Optional limit `train_panel_rows` (absent by default; a default stage's limits, draw, outcome and decision have no
new key). When present (method challenge arm only):

* **Draw** -- after the candidate is frozen, an outcome-blind seeded sample of the step's WHOLE task roster (rows
  whose step evaluation was unknown included), stratified round-robin over the step families, drawn independently
  of replay and local-fix, whose membership (and therefore the acting replay-harm veto) is unchanged. Each entry
  records the status of its own step evaluation (membership information for a stratified report, never used by a
  rule). Before anything runs the stage rebuilds the panel from the sealed manifest, the panel file and its own
  sealed step evaluations and requires the recorded one to be exactly that (entries, order, count, annotations).
* **Sampling identity** -- every challenge draw and execution order is seeded by the manifest hash the stage would
  have WITHOUT the optional limit, so the fresh panel, its order and the balanced halves of the acting sets do not
  depend on whether a train panel is asked for (replay and local-fix are seeded samples over rows ordered by their
  evaluation-record hash, which belongs to each stage's own manifest and its own rollout).
* **Evaluation** -- every task is solved once per Skill: a panel position that is also a replay or local-fix
  position reuses that position's two evaluations; the others are solved under the same two rollout keys in their
  own balanced ABBA order.
* **Summary** -- `train_panel`: the same family-level paired summary as `fresh`, plus counts by step status and
  the number of reused positions; `fresh_size_matched`: the same summary on the first n positions of the sealed
  fresh draw order (n = panel positions) -- a sensitivity reading at an equal number of positions (it equalizes
  task counts, not the power of the family test, the family composition or the exposure); unavailable, and
  recorded as such, when the fresh panel has fewer positions than the train panel.
* **Decision record** -- `in_sample_shadow`: the action rule v2's table returns with the train panel in place of
  the fresh panel (identical replay precedence, coverage ceil(90%) of the panel, family tests at the same alpha,
  aggregate guard, adverse completion), and the same for `fresh_size_matched`. Flagged `decision_input: False`.
  The stage's action, the next Skill and every existing input stay rule v2 on the fresh panel.

## 3. Reading (fixed now)

Per learning history, from the sealed records (zero-call script
[active-evidence-shadow-summary-20261011.py](active-evidence-shadow-summary-20261011.py)): the acting action and
reason; the shadow action and reason; the size-matched fresh action; paired effects (wins, losses, net / jointly
known) on the fresh panel and on the train panel, their difference, unknown positions and family denominators; the
train-panel counts by step status. For multi-task families (KOR) the effect is the equal-family mean of
within-family differences on both panels.

Per domain: a contingency count of (acting action, shadow action). The cell that matters most is
**shadow keep while the reserved pool does not keep** (an in-sample rule that would deploy what the fresh panel does
not support). The opposite cell (fresh keep, shadow not) can come from the smaller panel, its composition, the
training exposure, unknown positions or noise; it is read together with the size-matched fresh action and is not
by itself evidence for or against either rule.

What this can and cannot show:

* It is a falsification pilot. A shadow `keep` against an acting `park`/`revert`, or an in-sample effect clearly
  above the fresh one, counts against a training-rows-only rule. Agreement does NOT promote the rule: with one
  domain-wide behaviour per domain so far (SearchQA keeps, BigCodeBench parks) agreement may merely reproduce
  that; the fresh decision itself is noisy development evidence.
* The train-fresh gap mixes training exposure (the analysts saw the known rows), task difficulty, family
  composition and sampling noise; it is not an isolated optimism estimate.
* In-sample sign-test p-values are operational heuristics: the fresh panel's error statement (independent fair
  non-tied family signs conditional on the frozen candidate) does not transfer to rows the candidate was built from.
* No pooled agreement interval across histories (they share pools and tasks). No rule is changed by this pilot; a
  training-rows-only acting rule would be a new version with its own prospective comparison of training-only,
  reserved-pool and ungated policies on data that none of them used.

## 4. Runs (pass/fail feedback, one step, `update_mode native`, parent none, snapshot i, no test cell)

In this order (one per domain before any further seed): SearchQA seed 20261011 (`train_panel_rows=64` of 128 step
rows), BigCodeBench seed 20261007 (64 of 128), KOR-Bench seed 20261008 (45 of 90: 30 step rules, at least one row
of every rule), then further SearchQA seeds 20261012 / 20261013 as time allows. Seeds chosen so that every history
is a new draw of step families for its domain under the pass/fail method-mode policy. Expectations written before
any of them ran (not criteria): SearchQA keep / shadow keep; BigCodeBench park / shadow park; KOR park / shadow park
(both panels have little power on at most 20-30 rule families). Added cost: at most 2 x 64 (2 x 45) solver
positions per stage.

Order changed at 15:00, before any outcome existed (queue o2 replaces o1, which was cancelled while its first stage
was still waiting for the stage lock): a KOR method-mode stage takes about three hours (m1: 189 minutes), so the
KOR stage runs LAST instead of third, and one more BigCodeBench seed (20261008) is added -- BigCodeBench is where
the reserved pool parks, i.e. where a shadow `keep` would count against a training-rows-only rule. Final order:
SearchQA 20261011, BigCodeBench 20261007, SearchQA 20261012 and 20261013, BigCodeBench 20261008, KOR 20261008.
This departs from "one stage per domain before further seeds" for scheduling only; no setting changed.

Exploratory extension added at 15:10, AFTER the first pilot outcome (SearchQA seed 20261011: acting keep, shadow
keep) and after the zero-call screen tabulation; Codex direction check: GO. Three SearchQA SECOND-STEP method-mode
stages with the panel (queue p1): parent = the pass/fail one-step Skill of last night's matched studies rep2 / rep3
/ rep4 (`m:<study>:comparator`), seeds 20261006 / 07 / 08 (the parent's own seed: the step families are the ones
the parent was learned from, the reserved pool is disjoint from them), pass/fail feedback, native,
`train_panel_rows=64`. Second steps are where the effect is expected to be near zero and where a decision made on
training rows alone is most likely to keep what the reserved pool does not support (one of last night's six
refinements looked significant on training rows against one control with a held-out effect of +0.017).
Expectation written before any of them ran (not a criterion): acting park, shadow park. A shadow keep with an
acting park is the prespecified operational failure signal -- not proof of a false positive, since a fresh park can
be low power; effects, unknowns, reasons and the size-matched action are read together, all three stages are
reported, and three agreements would not validate a training-rows-only rule. Disclosures: the pools were the
holdouts of those studies (the base Skill was already evaluated on most of these tasks; nothing was selected by
those outcomes); "near zero" is plausible, not established (earlier intervals allow small gains).

More histories of the same two settings added at 15:31 (queue q1), after two first-step outcomes existed (sh11
keep / shadow keep; bsh07 park / shadow park): the short stages take 7 and 22 minutes while the KOR stage takes
about three hours and runs last anyway. Nothing is chosen by an outcome: the second-step parents become EVERY
pass/fail one-step Skill of last night's 128-row matched SearchQA studies (rep1 and ctl1 in addition to rep2 / rep3
/ rep4; the three seed-06 parents share step rows and pool, so they are not independent histories), and the
BigCodeBench seeds continue 07, 08 with 09, 10 (the last one runs after KOR, by the lock's arrival order).

Post-hoc design change at 16:15 (queue r1), after seven pilot outcomes existed -- first steps sh11 keep / shadow
keep, sh12 keep / keep, sh13 keep / shadow PARK; second steps s2sh06 park / park, s2sh06r1 park / park, s2sh07
keep / shadow PARK; BigCodeBench bsh07 park / park (no shadow keep against an acting park; two acting keeps that the
64-row shadow did not reach, its panel holding only 10 and 7 rows the parent had failed in the step): a FULL-ROSTER
panel, `train_panel_rows=128` (every step row), on new seeds -- SearchQA 20261014 / 15 / 16 and BigCodeBench
20261011. A training-rows-only rule would naturally use all step rows (at about the cost of today's reserved-pool
rule), and a larger panel also has more power to keep FALSELY, which is what the pilot tries to provoke. The 64-row
and 128-row stages are reported in separate rows; the change is disclosed as outcome-informed. The KOR stage
(panel 45, unchanged) stays last; queue o2 was cancelled while its next stage was waiting (not begun) and its tail
re-issued in r1 with the same settings.

Budget qualification: the panel adds protected solver capacity to the reserve taken before the update. Under a
binding budget a stage with the panel could skip diagnosis cases or stop pending where the same stage without it
would not; "the acting decision is unchanged" therefore holds given the same completed step and candidate, not
across budgets. In these runs the budget is far from binding (about 420-550 metric calls against 12,000, and no
diagnosis in the pass/fail arm).

Disclosures: reused development pools (F evaluated every development task under other Skills; earlier v11 stages
drew panels from the same pools); the design follows the tabulation in section 1, so the pilot is adaptive
development evidence; one history per parent / seed configuration (the three second-step histories of seed 06 share
step rows and pool).
