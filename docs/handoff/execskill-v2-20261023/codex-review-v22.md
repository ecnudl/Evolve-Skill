# Codex review of route B v2.2 (one round, 2026-10-24 15:0x)

Reviewer: `codexdl exec -m gpt-6-astra -c model_reasoning_effort="ultra" -s read-only` over a mirror of the dev tree
(`skillopt/`, `scripts/`, `tests/`, `docs/handoff/`, the `main22*` launch scripts and `main22_delta.py`; no data, no
`.env`), brief `BRIEF-v22.md` (in this folder: the configuration's equality with main-v2-1 outside the gates, the
practical rule and its exact arithmetic, the |A*| floor, pruning's behaviour preservation, legacy decisions unchanged,
the launch scripts). The full output is kept outside the tree: `/root/ops2-20261022/logs/v22/codex-review-v22.out`.

**Verdict: NOT ACCEPTABLE -- 1 MAJOR, 2 MINOR, no BLOCKER.** The reviewer reproduced all three findings and confirmed
offline: 7,381 legacy training-verdict comparisons, synthetic legacy sealed-record and decision hash comparisons, 77
configuration-table entries, the launch scripts' shell syntax, the pricing equivalence and the available patch
hashes, with no legacy-output difference. It did not run pytest (read-only sandbox), made no model or API call and
read no prohibited data.

| # | Finding | Fix |
|---|---------|-----|
| 1 MAJOR | `acceptance.py` (`decide`; the floor at :147): the smaller ALFWorld floor admits a round whose clustered t-test keeps no degree of freedom once shared-unanswered games leave. A* = 20 games in six rooms sized 5, 5, 4, 4, 1, 1, the four larger rooms in four blocks: both singleton games unanswered (exactly J5's permitted 10 %) leave four answered rooms in four blocks; the item-count `require` passed and `stats_ext.paired_t` raised before any decision was written -- a round that finished-round recovery refuses to redo | under a sealed rule `decide` checks the answered statistical units (rooms on ALFWorld, else items) against the blocks they fall in (`_too_few_units`) before any contrast, and records an explicit `undetermined` decision (header, A*, analysed, shared-unanswered items, provenance; reason "too few answered units for the t-test (k rooms/items in b blocks); the run pauses, the batch is consumed but undecided"), which `settle` pauses like every undetermined round; a round sealed without a rule keeps the legacy `require`. Tests: an OfficeQA round left with one answered item per block is undetermined, reproduces and pauses in `settle`, the same cells under a seal without a rule raise as before, one more answered item is decided (J5 pauses it); the ALFWorld rooms check on a synthetic seal |
| 2 MINOR | `step.py:1483`: after pruning, `training.rounds[].candidate_sha256` still named the engineered package, attributing an effective N's result to N + an idle M (adoption itself used the pruned package) | the round record names the package the cells ran (`evaluated["candidate_sha256"]`) and, in v2.2, the engineered one as `proposed_sha256` with the pruned ids; in every other configuration the record is unchanged (the evaluated hash is the engineered one, no new keys). Tests: both main-v2-2 step tests check the round record |
| 3 MINOR | `acceptance.py:864`: practical-rule decisions still emitted `placebo_rule = "harmful_sham_parent_only_2.5pct"`, although the rule tightens no J1 alpha (reproduced: an accepted OfficeQA five-point gain, p_t about 0.0255, with a harmful sham) | under a sealed rule a harmful sham is labelled `harmful_sham_reported`; a record without a rule keeps the legacy label. Test: the same harmful-sham cells under both seals |

Verification after the fixes: targeted tests (`test_execskill_v22.py` and `test_execskill_acceptance.py`: 42 passed;
`test_execskill_v2_step.py`, `test_execskill_v21.py`, `test_execskill_v2.py`, `test_execskill_protocol.py`: 84
passed); the zero-call what-if on main-v2-1's D s3 round re-run with the fixed code is identical to the one before the
review (`logs/v22/validate-v22-post-codex.json` = `validate-v22.json`); the registered selection was run again before
the commit (`logs/v22/tests-1614.log`; 1,536 passed and 1 failed in 35:01 -- the B1 integration test's exact namespace set, which did not list v2.2's namespaces; with that assertion updated, `test_execskill_integration_b1.py`, `test_execskill_v22.py` and `test_execskill_protocol.py`: 59 passed on the same code (`logs/v22/tests-b1-fix.log`)). The registered selection started at 15:50 on the code before
the fixes was stopped at 76 % without a failure when the fixes were written (`logs/v22/tests-1550.log`).

No second Codex round (registrar rule since 10/17: one round per item; a second only if the smoke fails). The smoke of
record is not re-run: main-v2-2 is priced exactly as main-v2 (`main22_delta.priced_as_main_v2`), the configuration
the smoke's S-E6 projected.
