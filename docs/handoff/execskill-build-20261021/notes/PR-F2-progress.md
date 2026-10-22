# PR-F2 progress (ticket fixer-2: the §8.3 short answer; registrar decision row "fixer-2 short answer")

- 13:5x read: readout.py (`arm_table`, `_windows`), evaluation.unseal cell shape (`completion_tokens` = one entry per
  logical call), cells.py logical calls (first/second/repair/step; replays add none, restarts add an episode),
  registration §6.2/§8.3, decision row + 13:0x addendum, fixer notes and ticket fixer-2.
- 14:0x readout.py: `SHORT_ANSWER = Fraction(1, 4)` (local, cited), `_reply_tokens` (per-call mean; no usage = no call
  or a call without a count), `_median`, `_reference` (window 0; statuses defined / no_cell_with_usage / zero_median),
  `_windows` returns (reference, windows) with `short_answer_share` + `no_usage`; `arm_table` adds
  `short_answer_reference`. Module and function docstrings updated.
- 14:1x tests: 6 `test_fixer_2_*` in tests/test_execskill_readout.py; file 17 passed on dl. Seven mutations (sum,
  <=, later-window stand-in, zero-median share, partial usage, negative count, shared cell counted) each killed by its
  named test (throwaway copy /tmp/PR-F2-mut, deleted).
- 14:2x dl: tests/test_execskill_integration_b5.py 1 passed, tests/test_execskill_e2e.py 11 passed (5:21; both call
  `readout.readout` on real unsealed cells). Ticket PR-F2-1 → C7e: the §6.2 acceptance-round series is missing.
- 14:3x notes/PR-F2.md written; done.
