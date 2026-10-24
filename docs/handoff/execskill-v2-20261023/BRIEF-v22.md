You are reviewing code, read-only, ONE round. Repository: a byte mirror of the dev tree (this directory), branch
research/exec-skill-v2-train, HEAD f27e16e (v2.1) plus uncommitted v2.2 changes. The complete v2.2 diff is
v22-review.diff in this directory (= `git diff f27e16e -- skillopt scripts tests` plus the new, untracked
tests/test_execskill_v22.py). Do not run model/API calls; you may run Python offline (pytest may not work here: no
sandbox image; on the dev machine the targeted tests pass, the full registered selection is running). Never open files
under data/ (excluded here) or any data file whose name contains test|holdout|final|reserve other than Python sources
and pytest files.

CONTEXT. Route B ("executable-skill co-evolution", protocol fivebench-execskill-v1) learns, per benchmark, a package of
small sandboxed Python procedures whose hooks add typed notes to the solver's request. Configuration main-v2-1
("train then accept": training rounds adopt a candidate on the run slice, then a self-test, then a sealed acceptance
round) is running since 2026-10-24 04:05. In 8 hours almost nothing passed: the training sign test rejected small
wins, one acceptance was not run because |A*| = 12 < 30, and one (+9.0 points over the whole batch, p 0.003) was
rejected by J2 because a length-matched yoked sham did nearly as well. The owner judged the gates too strict ("a
5-point accuracy change counts as an effect") and approved v2.2 (2026-10-24 12:1x). Specification as implemented,
with the owner's words, the rationale and the registered limits: docs/handoff/execskill-v2-20261023/spec-v22.md. Code:
skillopt/execskill/{acceptance,protocol,router,routes,step}.py. Launch scripts: ops/main22-*.sh and ops/main22_delta.py,
generated from the reviewed and used ops/main21-* (diff them against those; V22_PATCH_SHA256 is filled in once commit h
exists).

REVIEW FOR (most important first):
1. Every existing configuration (default, recommended, main, main-v2, main-v2-1) and every existing record must behave
   exactly as before: training verdicts and unit results, sealed acceptance records and their hashes, firing plans,
   decisions re-derived from stored sealed records and cells (`decide` on a round sealed without `rule`), reasons,
   smoke behaviour, prompts, namespaces, caps. Name any path where v2.2 code changes an older configuration's output.
2. The practical rule (`acceptance._practical`, the `gate` branch of `decide`, `minimum_astar`, `router.plan(...,
   minimum=)`, `not_run`): exact arithmetic and the whole-batch definition (answered A* items, divided by |A|);
   SearchQA's significance path; interplay with J3-J7, the undetermined path, the harmful-sham branch (the registered
   J1 used alpha/2 when the sham is harmful; v2.2's J1 does not use p at all off SearchQA) and the reason strings;
   the floor formula, its ALFWorld rooms part, and whether any downstream code (dispatch, schedule, twins, yoke,
   g_acc, probe, `_design`, the t-test requirement "more answered items than blocks") breaks or becomes degenerate for
   an A* as small as 3-8 items.
3. The pruning (`step.prune_idle` and its wiring in `_train_eval`, `_train`, `_line`): is the pruned candidate really
   routed identically on every evaluated item (any cross-procedure interaction in router.route, narrowed scopes,
   describer entries, second-call requests, shared worker state, fault attribution)? Package validity after
   `withhold` (retired, narrowed, describer, parent hash, MAX_CHANGES); the saved package and resume/idempotence
   after a pause in the unit; every consumer of the candidate after a round (adoption into the incumbent, the next
   round's engineer/rebase and history, feedback, `engineer._combined_train` / dropped_in_combination, the step
   buffer, the self-test, acceptance, the step record); the fate `pruned_no_firing`.
4. The training rule without the sign test: any reader of `verdict["gain"]["sign"]` or of the old verdict shape
   (records, summaries, smoke checks, schemas) that breaks when it is absent; any other consequence for main-v2-2.
5. Plumbing: protocol tables (CONFIGURATIONS/PILOTS, LEARNING, FIX_ECHO, META_COUNTERFACTUAL, STAGE_READ,
   TEST_READ_CELLS, every CONFIG_* table, COST_CHECK_PAUSES, EVIDENCE, REAL_RUN_EVIDENCE, RUN_ROOTS, NAMESPACES,
   CHAIN_NAMESPACES, TRAIN_SIGN, PRUNE_NON_FIRING, ACCEPT_RULES, ACCEPT_FRESHNESS), the freshness label
   `route_b_v2_1_slices_reused` (is it accepted everywhere a freshness is validated or reported?), routes.check_pins,
   budgets/smoke/manifest functions keyed by configuration, CLI choices, chain.read_estimate_record.
6. The launch scripts: the e -> h delta checks (snapshot lists incl. the added test file, git parents and the three
   reviewed patch hashes, code map, clients, runtime, echo sets, sheet qualification q23-h), the "priced as main-v2"
   argument for reusing the smoke of record's S-E6 projection and test-read estimate, the consent written under the
   owner's delegation (main22-consent.sh), and anything that would make the launch crash, stall, overspend, run the
   wrong snapshot/configuration, or silently produce a meaningless result.

OUTPUT: first line "VERDICT: ACCEPTABLE" or "VERDICT: NOT ACCEPTABLE". Then numbered findings, most severe first, each:
severity (BLOCKER / MAJOR / MINOR), file:line, the concrete failure scenario, and the fix. At most 15 findings; no style
nits. If you ran anything offline, say what.
