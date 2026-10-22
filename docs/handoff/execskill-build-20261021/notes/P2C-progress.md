# P2C progress (route B, fivebench-execskill-v1)

- 2026-10-22 start: read task prompt; reading decisions/runbook/registration/code next.
- 14:4x read decisions (14:10 rows 7/8/9/17), runbook §0/§3.4/§5.3/§7.1, registration §4.1/§8.1/§9.3/§9.4, chain.py,
  protocol.py, budgets.py, units.py, manifest.py (_clients), client.py, frozen calls/ledger/budget, smoke._confirm,
  smoke.se6_projection, acceptance (settle/earlier_blocks/decide), step._accept, runcli, run_execskill recover.
- Design notes: (a) `<c>:confirm` NOT added to budgets.chain_caps: smoke.se6_projection requires every chain_caps
  scope that is not GLM/root to have maximum-schedule cells, so adding it there breaks S-E6 (smoke.py is I1's file).
  Declared by chain.run beside chain_caps (budgets.first_call_caps) and listed in budgets.caps() (manifest).
  (b) exact high-anchor estimate = 272,045,432/5 -> 54,409,087. (c) fixture prompt = S1-a's (101 bytes);
  one reservation at B = 65,536 = 264,596.
- 14:5x coordinator: "I1 2a done" received -> run_execskill.py and test_execskill_mutations.py are editable.
- 15:0x protocol.py: FIRST_CALL_SYSTEM/USER/BENCH/CAP (row 7), FIRED_SHARES, TEST_READ_ESTIMATE_ARMS, fired_share,
  estimate_test_read (row 8; named without a test_ prefix so pytest never collects it). budgets.py: CONFIRM,
  first_call_scopes, first_call_caps (in caps(), not in chain_caps). chain.py: first_call (+confirm.json /
  confirm-failed-<n>.json), read_estimate_record, latest_cap_check, read_budget (G factor, returns the gate recorded in
  test-read.json), read_consent (+read-waiting.json), run() wiring. Next: acceptance.finished_round, CLI, tests.
- 15:3x acceptance.finished_round (row 17) + run_execskill.py (test-read-estimate command; recover refusal). fakes:
  first_call_solvers / with_first_call. test_execskill_chain.py: 20 new tests (row 7 pass/reuse/no-concurrency, 8
  failure modes, config/cap failure, relaunch pin check, 5 stub-client guards; row 8 gate x3; row 9 consent) -> 29
  passed on dl. step.cost_projection now skips `G:confirm` (spent before the first unit; else listed as a projected
  scope); test_execskill_step updated. integration_b5 (first-call solvers + chain-G cap check in its stand-in step)
  and e2e (Answers answers the fixture prompt; asserts confirm.json + gate) updated: b5+e2e+step 23 passed (7.4 min).
  Next: protocol / CLI / acceptance tests, mutations, runbook, notes, whole suite.
- 16:0x protocol tests (+13: exact 54,409,087, fired shares vs TEST_READ_CELLS, 10 refusals, first-call constants) ->
  33 passed; acceptance tests (+2, finished_round) and CLI tests (+2: test-read-estimate, recover refusal) ->
  acceptance/cli/budgets/manifest/runcli/canaries 111 passed. Mutation entries 37-55 added (19): each named test
  passes unmutated and fails mutated -> 19 passed (35 s). Next: runbook, notes, tickets, whole suite.
- 16:2x pilot-runbook.md updated (rows 7/8/9/17 closed, 5.3 kept as fallback; 3.1-3.5 test-read-estimate command
  before the pins and make-manifest, gate, <c>:confirm cap; 5.2-5.3; 6.1-6.3; 7.1-7.2). notes/P2C.md written;
  tickets P2C-1 (step-unit bypasses the confirmation) and P2C-2 (read gate re-applied after the read started).
  Whole suite started on dl (log /tmp/p2c-whole-suite.log there).
- 16:4x whole route-B suite on dl (tests/test_execskill_*.py, timeout 1500): 1183 passed in 824 s, exit 0 (mutation
  entries 1-55 included). During the run only a docstring bullet of chain.py changed (ledger declaration wording; no
  code). DONE -> report to the coordinator.
