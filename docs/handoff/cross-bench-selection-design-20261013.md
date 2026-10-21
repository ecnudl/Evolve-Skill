# Design contract (2026-10-13): SkillOpt with training tasks from one benchmark and the validation gate on another

Owner's request of 10/13: to see what is transferable in the evolution, run SkillOpt with one benchmark's tasks as
the training set and ANOTHER benchmark's tasks as the validation set, evaluate the evolved Skill on both
benchmarks and compare with the usual evolution (training and validation from the same benchmark). Written before
any such run.

## 1. Design

* Learner: the frozen SkillOpt baseline loop of learning v9 -- rollout of the training rows under the current
  Skill; analysts see task, answer, pass/fail and, for FAILED training rows, the reference answer (SearchQA,
  KOR-Bench) or the sanitized execution evidence (BigCodeBench); native proposal; the two-pass family sign-test
  gate (screen at p <= 0.10 with positive net wins, then a fresh pass of both Skills decides at p <= 0.05 / 3); at
  most three iterations. `scripts/run_cross_bench_selection.py` re-runs this loop step by step with the frozen
  functions (`propose_native`, `confirm_selection`, the adapters and ledgers of two prepared v9 stages): training
  rows from benchmark A, the gate on benchmark B's validation partition. Nothing in `continual_learning` changes.
* A candidate learned from A's failures is therefore kept only if it measurably improves B's validation tasks.
* Held-out evaluation inside the same run, on rows neither learning nor selection touched: A's validation
  partition and B's 128 training tasks, each solved by the empty Skill, the final Skill and the named references.
* Seed 20261006 on both sides: the training rows of the baseline chains' stages.

## 2. Runs

1. `x-qa-bcb`: train SearchQA (128 tasks), gate on BigCodeBench validation (128 tasks); reference `same_qa` =
   the Skill the same-benchmark SkillOpt v9 SearchQA stage deployed.
2. `x-bcb-qa`: train BigCodeBench (128 tasks), gate on SearchQA validation (200 tasks); the same reference.
3. KOR-Bench as either side is left for later: one pass over its 250 validation tasks takes close to an hour and
   a gate needs several.

Comparison with the usual evolution, from sealed records: with same-benchmark validation SkillOpt accepted step 0
on SearchQA (34 wins / 2 losses on the SearchQA validation rows) and nothing on BigCodeBench.

## 3. Reading (fixed now)

Per run: the gate's action for each of the three candidates with its wins and losses on B's validation rows; the
final Skill; then, on the two held-out sets, final minus empty and reference minus empty (paired counts).

* A candidate accepted under cross-benchmark selection is, by construction, text learned on A that measurably
  helps B: that is what "transferable" means here, and the accepted text itself is the object to look at.
* A completed statistical rejection by the gate (screen or confirmation) means no transfer was measurable at this
  gate's power (128 or 200 tasks, a strict two-pass sign test) -- not that nothing transfers. A step that ends for
  another reason (label leakage, size budget, coverage, an infrastructure stop) says nothing about transfer.
* `same_qa` was selected on the SearchQA validation rows, so its number on that set is optimistic; on the
  BigCodeBench rows it is a clean transfer measurement.
* One history per direction, one seed: descriptive. No Skill is deployed.

## 4. Disclosures

The loop is a re-implementation of the frozen stage loop's v9 path around the frozen functions (reviewed for
equivalence); the two prepared stage directories are inputs only and are never begun; SkillOpt here is this
project's adapted baseline, not the upstream system; development and validation partitions only, no test data.

Review: Codex found the loop equivalent to the frozen v9 path in every enumerated respect and required two
additions before launch, both made: both manifests are re-validated against the current sources before the run,
and a run completes only when both ledgers' usage accounting is complete.

Execution note (01:40): a run that ends with a sealed pending result is repeated ONCE in a new directory (`-r1`,
queue w2), from the same two prepared stages; the pending run is reported and not used; a second pending result
leaves that direction without a result. `cross-qa-bcb` ended pending at 01:33 (`unknown_cost_attempt_cap`: a burst
of HTTP 429 answers during the second training rollout, 44 failed attempts in one minute) after its step 0 had
been rejected by the frozen label-leakage rule (the candidate copied a reference answer of a failed training row)
and before any candidate reached the BigCodeBench validation rows.

Execution note (03:00, before any repetition began; no held-out outcome and no validation-gate decision exists
yet): `cross-bcb-qa` ended pending at 02:24 (`native_optimizer_incomplete`: one merge call was not delivered in a
minute of stalled TLS handshakes) inside its step 0, before a candidate existed. Both first runs therefore
stopped for infrastructure reasons before any candidate reached the other benchmark's validation rows. Queue w2 never began a run (it waited for ten quiet minutes from
02:24; outages came every five to ten minutes) and was stopped by the operator at 02:57 while waiting;
`cross-qa-bcb-r1` is prepared and not begun and is run as prepared.

Amended retry rule: a direction is repeated after a sealed pending result up to THREE times (`-r1`, `-r2`, `-r3`),
each in a new directory from the same two prepared stages; every run is reported with its reason; only a completed
run is read; a direction whose four runs all end pending has no result. Reason: a run makes about 1,500 to 3,000
calls on two ledgers whose cap on failed attempts is cumulative, so one bad minute ends it whatever the Skill is;
the stopping reason is the network, not an outcome. Launch window: thirty consecutive successful probes (about
five minutes). Queue z1 runs `-r1` of both directions first and any further repetition after its other parts.

Review of queue z1 (Codex, 03:02-03:09, before the parts concerned started): three required findings. (1) The
cross-benchmark part read a run's state from a text match; it now reads the SEALED records (result bound to
`cross.json` by `cross_hash`, exact version and status) and halts a direction on any other state. (2) Exit states:
the cross-benchmark part and E1 now exit with an aggregated status; the master script was already running and is
NOT changed, so the `(exit N)` field of its log is meaningless and is not read by anything -- part logs and the
tools' sealed statuses are the record. (3) E1 could have skipped blocks silently; its six blocks are now written
and verified as a whole or the part halts. Confirmation review: findings 1 and 3 closed, the master's field
accepted as a disclosed non-blocking defect, GO. The scripts as launched at 03:01 are kept on the machine as
`w3.sh.as-launched-0301` and `v1c.sh.as-launched-0301` (neither ran).

## 5. Follow-up, exploratory: BigCodeBench-trained Skill texts on fresh SearchQA tasks (written 04:22, before it ran)

What was known when this was written. `cross-qa-bcb-r1` completed (03:42): step 0's SearchQA-trained candidate was
rejected at the screen on the BigCodeBench validation rows (9 wins / 7 losses), steps 1 and 2 by the label-leakage
rule; nothing accepted; the reference `same_qa` on the 128 BigCodeBench training rows 64 against 62 without a
Skill. `cross-bcb-qa-r1` ended PENDING at 04:20 (an undelivered call inside step 2's proposal) and is not the
result of that direction (its repetition `-r2` follows in queue z1). Its sealed step records show: step 0's
BigCodeBench-trained candidate (9,986 bytes) rejected at the screen on the SearchQA validation rows (17 wins / 11
losses), and step 1's candidate (12,436 bytes, text only about writing code: signatures, plots, edge cases,
imports) ACCEPTED (first pass 18 / 10, fresh confirmation 20 / 6).

Question: is that acceptance content that transfers, the generic effect of having any careful instruction (on
10/11 a three-line generic instruction already gave +7.5 and +9.2 points over the empty Skill on SearchQA), or a
lucky draw on those 200 rows? Queue z3 (snapshot `20261013-o`, the panel evaluation tool as it is) measures seven
frozen texts on the 250 fresh SearchQA tasks R01..R10, all arms in the same runs (`xt-r01..r10`): `empty`, `bhand`
(the three-line generic instruction), `bzero` (the zero-shot SearchQA instruction), `old_v9` (= `same_qa`, the
same-benchmark SkillOpt Skill), and three BigCodeBench-trained texts as fixed-text files written by
`extract_foreign_texts.py` from sealed records with their hashes: `xbcb0` and `xbcb1` (the two candidates above)
and `xbcbp` (the Skill adopted without selection by the completed one-step stage `bigcodebench-active-pfix1`,
8,352 bytes).

Reading (fixed now, revised after the Codex launch review and before the run): single texts, descriptive. For
each of `xbcb0`, `xbcb1`, `xbcbp`: the contrast with `empty`, with `bhand` and with `old_v9` (estimate, task-level
interval, wins / losses, planned 250 against jointly known tasks, missing-outcome bounds). No equivalence is
claimed: 250 tasks resolve about five to six points for one pair. The words used: "above `empty`" only if the
interval of text minus `empty` lies above zero; otherwise "benefit not shown on these tasks" -- which does NOT
establish that the gate's acceptance was luck. A text that is above `empty` and whose contrast with `bhand` has
an interval containing zero is "consistent with a generic-instruction explanation; mechanism unresolved": it
neither shows a generic mechanism nor excludes learned content. Everything else is "inconclusive".

Disclosures. R01..R10 are development tasks that are disjoint from every source's learning and selection data
("fresh" means only that); they are reused here after the E2 read, the prompt-profile evaluation and the E2
replication, whose results were or will have been read. `bhand` was written by hand on 10/11 after reading a
learned Skill (an informed, post-hoc compression). `xbcb1` was SELECTED on SearchQA validation rows (its number on
these tasks is clean, but it is the favoured one of two candidates); `xbcb0` and `xbcb1` come from one history
(the same training rows, consecutive steps of a pending run); `xbcbp` comes from a different method (learning v11,
diagnosis feedback, adopted without selection): these are not three independent SkillOpt histories. Intervals are
conditional on these seven texts. Not included: an experience-free coding instruction of matched length and style
(suggested in the review; it would separate "any long coding guidance" from "guidance learned from experience");
without it the mechanism stays open whatever the numbers are. The follow-up was decided after reading the pending
run's step records; it does not replace the direction's result; runs, repetitions, unknowns and costs are
reported; model GLM-5.3 low, snapshot `20261013-o`; no test data.

Launch review of queue z3 (Codex, 04:22-04:25): execution mechanics passed (the helper only reads sealed records
and writes a new directory; a pending run's sealed candidate is a valid fixed-text arm for a separate descriptive
measurement); NO-GO on the first wording of the reading rule and disclosures, GO after corrections -- the two
paragraphs above are the corrected text; the helper now also checks each candidate text against the hash in its
step record. Released 04:25.
