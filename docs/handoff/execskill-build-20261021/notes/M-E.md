# M round builder E progress (Codex #2, #11, #12)

Started 2026-10-22 18:06 CST. Target 20:06, hard stop 20:36. All items done 18:4x.
Owned: skillopt/execskill/engineer.py, detectors.py, router.py, acceptance.py (twin cell accounting only); their tests.
Mutation numbers reserved: 84-87 (all used).

## Status
- [x] #2 SB reference copy check (engineer.py) + adjudicator payload with values -- 18:4x done (see Notes)
- [x] #11 exact detector recall boundary (detectors.py) -- 18:2x done: rows carry recall_counts/jaccard_max_counts, _verdict compares exact Fractions; tests/test_execskill_detectors.py 9 passed
- [x] #12 twin eligibility on A (router.py) + twin cell accounting (acceptance.py) -- 18:25 done: router.plan counts/draws inherited twins on A, new plan field twin_only; acceptance: twin_only()/dispatched() helpers, schedule runs S' + twin on twin-only items, dispatch/settle consume them, decide: tau over A* + answered twin-only (n_outside_astar), twins_cap.outside_astar, _rates/worst_delivery_rates on A* only; tests: router 6 passed, acceptance 28 passed
- [x] mutation entries 84-87 -- appended after 83 in tests/test_execskill_mutations.py; each checked on a throwaway /tmp copy on dl (named tests pass unmutated, 4 passed; each mutation: rc 1, 1 failed)
- [x] targeted tests run (18:39): engineer 13 passed, detectors 9 passed, router 6 passed, acceptance 28 passed; frozen diff (coevo5, continual_eval, weak_solver_probe.py) empty

## Notes
- #2 design (engineer.py): `disclosed(ctx)` = the SB reference values the proposal payload actually carried
  (`run` records `ctx.sheet["shown"]` from the fitted payload; a direct `check` recomputes `payload(ctx)`), minus
  trivial values (blank, booleans, numbers < 3 significant digits, texts < 5 word characters; frozen thresholds
  LEAK_MIN_SIGNIFICANT_DIGITS / LEAK_MIN_SINGLE_WORD) and values public in their own item (request view + every cell
  value/formula of its public workbook, read like `public_workbook()`). `sheet_findings` flags a disclosed value in
  the description, header, every literal and every rendered note unless the text's own public context has it (FA-F12:
  a note -> its view, stored pre-check report and workbook; description/header/literals -> the replay-test-named
  trajectories'). Hits join the ONE frozen adjudication; it gets `values=` (matched first, <= 60) and, when an SB hit
  exists, the procedure code (to tell a copied constant from a value computed on the public workbook). Years are
  checked (unlike the frozen rule check). The header is now checked too (also by the corpus check).
- Open: a note that legitimately writes a value computed from the public workbook (equal to an answer cell) goes to
  adjudication (possible false veto; mitigated by showing the code). Smoke S4 consumption check uses plan A* only:
  fine at s1 (no inherited procedures -> no twin-only items), would need `acceptance.dispatched(sealed)` if reused.
