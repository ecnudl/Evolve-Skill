# C7c progress (C7b2-3 + C6b-1 leftover, S-E6, S4, S3, fake-mode rehearsal)

- item 1 DONE: describer imports DEFAULT_TARGET from protocol; FakeNative.precheck(tag=None, docker=None); smoke.py
  wrapper dropped (precheck.precheck = native.precheck).
- item 2 DONE: protocol.MAX_SCHEDULE_CELLS / TEST_READ_CELLS (calc T4/T5 recomputed by a test, T6 caps reproduced);
  smoke.run_stage(..., "SE6") = se6_projection (zero calls) judged by se6_cost.
- item 3 DONE: step.run_step(..., smoke=SmokeStep); smoke.run_stage(..., "S4") with FaultSwitch at
  protocol.S4_DRILL_CALL; write_recovery + add_arguments/recovery_cli (smoke-recovery); s4_judged -> s4_ministep.
- item 5 DONE for S2/SN1/S4/SE6 (rehearsal 8 passed); unit tests added in test_execskill_smoke.py, test_execskill_step.py.
- item 4 (S3) NOT BUILT (out of time): see notes/C7c.md, last section.
- whole route-B suite: 1020 passed in 659.20s (before the last small patch); after it, the touched files: 67 passed.
- tickets: C7c-1 (CLI smoke_run KeyError + smoke-recovery wiring), C7c-2 (whole-round redo vs §9.3 one block).
- FINAL: notes/C7c.md written; row closed 2026-10-22 12:2x.
