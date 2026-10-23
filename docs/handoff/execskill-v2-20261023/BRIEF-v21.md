You are reviewing code, read-only, ONE round. Repository: a byte mirror of the dev tree (this directory), branch
research/exec-skill-v2-train, HEAD d44966d plus uncommitted changes. Do not run model/API calls; you may run Python
offline (pytest may not work here: no sandbox image). Never open files under data/ (excluded here) or any data file
whose name contains test|holdout|final|reserve other than Python sources and pytest files.

CONTEXT. Route B ("executable-skill co-evolution", protocol fivebench-execskill-v1) learns, per benchmark, a package of
small sandboxed Python procedures whose hooks add typed notes to the solver's request. Configuration main-v2 ("train
then accept") ran on 2026-10-23/24 and was aborted: chain D wedged on an httpcore connection-pool leak, chain G crashed
on a model-written replay test (a mutation written as an object), and LiveMath training adopted a procedure keyed on
the meta option "One of the remaining options is correct, but a stronger result can be proven." (correct in 129/129
training items) after the fix calls echoed the screen's matched phrase. The owner approved v2.1 (2026-10-24 02:22).
Specification as implemented: docs/handoff/execskill-v2-20261023/spec-v21.md. Diff: docs/handoff/execskill-v2-20261023/
v21.diff (skillopt/execskill/{client,engineer,manifest,protocol,replay,routes,step}.py; tests/test_execskill_v21.py new;
three existing tests adapted). Launch scripts: ops/main21-*.sh and ops/main21_delta.py (adapted from the reviewed
ops/main2f-* of the previous launch; registrar decisions: docs/handoff/execskill-registrar-decisions-20261022.md).

REVIEW FOR (most important first):
1. Behaviour of every existing configuration (default, recommended, main, main-v2) must be unchanged except the two
   registered every-configuration fixes (unlimited connection pools; type guards that turn a crash into a registered
   refusal). In particular: prompts and their hashes, consumption namespaces, caps, records, smoke behaviour.
2. The pool fix: does it really remove the PoolTimeout wedge for every client a chain uses (chain G's GLM solver,
   chain D's route A/B clients, the GLM-5.3 roles client), without changing request/receipt behaviour of the frozen
   client (scripts/weak_solver_probe.py is frozen and unchanged)? Any client constructed elsewhere that still has the
   default limits? Any resource/concurrency risk from max_connections=None?
3. The type guards: are there other places where a model-written value (engineer change entries, replay tests,
   analyst findings, examiner/generator specs, research outputs) is used as a dict key, set member, in a sort, or
   otherwise can raise outside the registered refusals during a main-v2-1 step? Name exact lines.
4. main-v2-1's two rules: (a) the redaction (engineer._redacted) — does any flagged text, matched lexicon term, static
   ban detail or adjudicator reason still reach the engineer in main-v2-1 through any path (fix calls, the next round's
   history/training feedback/lint, analysts' payload)? Is anything needed for a fix wrongly removed? (b) the
   counterfactual (replay.meta_counterfactual wired in engineer.leak_check) — correctness of detection (which entries,
   view vs request_view, mapping back, aspects), determinism, worker/inputs_dirs handling, cost, and false
   positives/negatives that would make the run meaningless; whether p-livemath-3-1 (its source is quoted in spec-v21.md
   in words) would be caught.
5. The configuration plumbing: protocol tables (every CONFIG_* table, EVIDENCE, NAMESPACES, namespace_of,
   REAL_RUN_EVIDENCE, RUN_ROOTS, PILOTS/TEST_READ_CELLS copies), routes.check_pins, step.py's Context construction,
   budgets/smoke/manifest functions keyed by configuration, CLI choices, chain.read_estimate_record (which refuses a
   configuration other than the one S-E6 projected: the launch uses main-v2's projection, see 6).
6. The launch scripts (ops/main21-*.sh, ops/main21_delta.py): the e -> g delta checks (snapshot lists incl. the one
   added test file, git parents and both reviewed patch hashes, code map, clients, runtime, echo sets, sheet
   qualification), the "priced as main-v2" argument for reusing the smoke of record's S-E6 projection and test-read
   estimate, the consent written under the owner's delegation (main21-consent.sh), and anything that would make the
   launch crash, stall, overspend, run the wrong snapshot/configuration, or silently produce a meaningless result.

OUTPUT: first line "VERDICT: ACCEPTABLE" or "VERDICT: NOT ACCEPTABLE". Then numbered findings, most severe first, each:
severity (BLOCKER / MAJOR / MINOR), file:line, the concrete failure scenario, and the fix. At most 15 findings; no style
nits. If you ran anything offline, say what.
