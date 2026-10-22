# C7b-1 progress (S0 driver, limits rule, escape rows, CLI wiring)

- 11:01 (dl clock): started. Read registration §10/§2.6/§3.1/§3.4/§8.1; plan §5/§6/§8/§10/§11; the registrar decisions; notes C3/C7a/C6b; tickets C6b-3/C3-2/fixer-8/fixer-9/C5-3.
- About 11:25: s0.py, the escape-probe worker section, the CLI wiring (including C6-2's runcli wiring) and the tests are written. The S0 and CLI tests pass on dl (43 passed).
- 11:2x–11:41: throwaway real zero-call rows in /tmp/c7b1-root. Escape, sandbox, determinism, measurements, pool views, replay and leftovers pass. Equivalence passes after the wall-time fix. The sheet row is blocked by v3's path-bound v7 qualification (C7b1-3).
- 11:41: whole route-B suite: 1011 passed, 0 failed in 607 s.
- 11:47: done. Wrote the runbook, tickets C7b1-1..3 and notes/C7b1.md. The throwaway root is deleted. Final tests: 49 passed (s0, cli, runcli).
