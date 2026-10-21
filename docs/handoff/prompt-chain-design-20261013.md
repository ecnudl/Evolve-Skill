# Design contract (2026-10-13): a first prompt-chain experiment -- an analyst "generalization requirement"

Owner's idea of 10/13: optimize the prompts of the whole chain for generalization (over our benchmarks); even
showing that this helps would give a direction. Written before any stage with the new prompt ran.

## 1. What is changed, and what is not

One link of the chain, one text. The analysts' system prompt (the upstream analyst prompt + the transfer
requirement + the evidence note) gets an optional addendum, the profile `generalize_v1`
(`skillopt/active_evidence/updater.py`, `ANALYST_PROFILES`; diff `prompt-chain-analyst-profile-20261013.diff`):
sort the batch's problems into answer-contract / procedure / one-off and edit only for the first two; write every
edit as one conditional rule of at most two sentences; require the support of two trajectories; prefer sharpening
an existing rule over appending; keep the Skill short. The text is benchmark-agnostic (it names no dataset, answer
or rule) but it is INFORMED: it was written after the results of 10/9-10/12 (gains that are mostly answer form,
long Skills with narrow rules, no gain on code).

Unchanged: the solver's prompt, the merge and ranking prompts, the trajectories, the edit budget, the update
mechanics. The default profile `native` is the package as it was (default manifests keep their shape). The profile
is limited to pass/fail feedback with the native update.

A second chain-level prompt effect needs no new run: the INITIAL text. The learn-from-B study already compares
one step from the empty Skill, from the hand-written generic instruction and from the zero-shot task-card
instruction on 1,000 fresh tasks (`lz` − `le`, `lh` − `le`).

## 2. Run (snapshot `20261013-p` = `o` + this change)

SearchQA, arms `scalar / none` (one pass/fail step adopted without selection), parent empty, seeds 20261023-27
with `--analyst-profile generalize_v1`: `lp23`..`lp27`. Same seeds, hence the same 128 training rows, as the
existing `le23`..`le27` (native prompt); the trajectories on those rows are solved afresh. Evaluation with the panel tool on 250 fresh tasks (block B, R01..R10):
`empty`, `bzero`, `le23`..`le27`, `lp23`..`lp27`.

## 3. Reading (fixed now)

Primary: `lp` − `le`, paired by seed (estimate, task-level, history-level and crossed interval as in the
learn-from-B memo). Secondary: `lp` − `empty`, `lp` − `bzero`; descriptive: Skill bytes and the scorer's failure
classes per arm. The reading rules of the learn-from-B memo apply as they are: 250 planned tasks, at least 225
jointly known, at least three shared seeds, and the missing-outcome bounds on the side of any claim. "Improves" is
claimed only if the crossed interval of `lp` − `le` lies above zero; with 250 tasks
one history resolves only five to six points, so a null is "not resolved", and a negative crossed interval is
reported as a loss. One domain: nothing here says the profile helps on code or rule tasks; those runs follow only
if SearchQA shows a gain.

## 4. Execution notes

01:28-02:50 (queue y1): `lp23`..`lp26` completed; `lp27` stopped and is lost (not resumed), so the paired reading
uses seeds 23 to 26 (four histories; the minimum of three holds). 03:00: queue y1 was stopped by the operator at
02:57 while it waited for ten quiet minutes before the first evaluation run (no run in progress, nothing
prepared). The evaluation runs in queue z1 with the same snapshot, arms, blocks and retry rule; a run starts
after twelve consecutive successful probes (about two minutes) instead of sixty, for the reason given in section
12 of the learn-from-B memo. No evaluation outcome existed when this was written.

## 5. Confirmation run (written 2026-10-13 11:15 and revised 11:22, before any of its stages; ordered by the owner at about 11:10)

What was known. On the 250 tasks R01..R10 the profile's four paired histories gave `lp` - `le` = +0.027 (per seed
+0.036, +0.012, +0.008, +0.052; crossed interval [-0.017, +0.071]): not resolved under the rule of section 3,
with the history count as the binding limit. The 975-task reading of the same night put one-step Skills learned
from the empty Skill level with the zero-shot instruction (`le` - `bzero` -0.005, crossed [-0.023, +0.012]).

Runs (queue z5, snapshot `20261013-p`, the stage tool and launcher exactly as in queue y1; revised after the
Codex launch review of 11:17-11:22 and before any stage):

* sixteen new one-step stages, seeds 20261028..20261035 (the next eight integers after the first study's seeds;
  no choice): `le28`..`le35` with the native analyst prompt and `lp28`..`lp35` with `--analyst-profile
  generalize_v1`, arms scalar / none, parent empty -- for each seed the same 128 training rows for both prompts;
  the order of the two stages alternates by seed. A stage that stops is lost: it is neither resumed nor replaced,
  and a seed enters the evaluation only if BOTH its stages completed.
* evaluation `c1-s01..s30` on 750 tasks that no run has used: positions 251 to 1000 of block B of the fresh
  sample, in thirty blocks of 25 (hashes in `prompt-chain-confirmation-blocks-20261013.json`). Arms in the same
  runs: `empty`, `bzero` and every complete NEW pair, the order of the two members alternating by seed. The
  histories of the first study (`le23`..`le27`, `lp23`..`lp26`) are NOT evaluated here: they motivated this run,
  and fresh tasks would not remove that dependence.

Reading (fixed now). Planned denominator 750 (`--planned-tasks 750`); a contrast is read only with at least 675
jointly known tasks. Every primary conclusion below also needs at least SIX complete pairs; lost pairs are listed
separately (the missing-outcome bounds cover missing tasks, not missing seeds).
Primary: `lp` - `le` paired by seed over the complete new pairs -- new seeds and new tasks, so nothing in it was
seen before this section was written.

* "The profile improves the one-step Skill" only if the crossed interval lies above zero and the missing-outcome
  lower bound is above zero.
* "The profile makes it worse" only if the crossed interval lies below zero and the missing-outcome upper bound is
  below zero.
* "No gain of one point or more" only if the crossed interval's upper limit is below +0.01 and the missing-outcome
  upper bound is below +0.01.
* Anything else is "not resolved", reported with the estimate, the per-seed values and the three intervals.

Secondary: `lp` - `bzero` (does one step with the profile beat the zero-shot instruction), `le` - `bzero`, `lp` -
`empty`; descriptive: Skill bytes per arm, and the first study's estimate next to this one (no pooled test).

Expected resolution, stated in advance: with eight pairs and 750 tasks the crossed half-width is about two points,
so a true gain of the size seen so far (+2.7) is at the edge of what this run can establish; a null stays "not
resolved" unless the interval is tight around zero.

Disclosures. The decision to run this depended on the first four seeds, which is why they are excluded. Within an
evaluation run the tool rotates the arm order over three offsets per block; the two members of a pair are
adjacent and their order alternates by seed, which balances but does not randomise their position. One domain,
one learning step, parent empty: nothing here says the profile helps the validation-gated learner, code or rule
tasks. The 750 tasks become used development evidence once read. Blocks C and D of the sample stay untouched; no
test data. Review: first round NO-GO on the claim contract (a pooled primary over old and new seeds is not an
independent confirmation; the loss claim lacked its missing-outcome condition; the pair minimum did not cover
every conclusion) -- all three are changed above; queue mechanics and seed pairing passed.
Confirmation review (11:23-11:25): both findings closed, no new required finding, GO. The queue was released at
11:23, after the revision and a local dry check of its arm-list logic and a few minutes BEFORE this confirmation
came back (the owner was about to close the laptop; the stage commands were unchanged from the reviewed version).
The header comment of the queue script still says 11:30; the times in this section are the correct ones.

## 6. Result of the confirmation run (read 2026-10-13 16:00)

All sixteen stages completed (eight complete pairs); all thirty blocks completed on their first run; 747 of 750
tasks jointly known. `lp` - `le` = **+0.004** (per seed +0.008, -0.004, +0.008, +0.023, +0.001, +0.008, -0.003,
-0.012; task-level [-0.002, +0.010], history-level [-0.005, +0.012], crossed [-0.008, +0.015], missing-outcome
bounds [0.000, +0.007]). By the rules of section 5: not "improves" (the crossed interval contains zero), not
"worse", and not "no gain of one point or more" (the crossed upper limit is +0.015) -- **not resolved**, with an
estimate of +0.4 points. The +2.7 points of the first study did not replicate. Secondary: `lp` - `bzero` +0.001
(crossed [-0.014, +0.015]), `le` - `bzero` -0.003 (crossed [-0.020, +0.014]), `lp` - `empty` +0.138. Descriptive:
Skill bytes 2.5-3.7 KB with the profile against 3.9-6.2 KB without it, at the same accuracy. First study next to
it (not pooled): +0.027 on four seeds and 250 tasks.
