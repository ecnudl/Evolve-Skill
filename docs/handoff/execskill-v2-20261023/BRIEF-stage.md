You are reviewing code, read-only, ONE round. Repository: a byte mirror of the dev tree (this directory), branch
research/exec-skill-v2-train, HEAD d8260f1 plus uncommitted changes (the v2 "train then accept" work, already reviewed
in an earlier round, and the NEW change under review). Do not run model/API calls; you may run Python offline. Never
open files under data/ (excluded here) or any file whose name contains test|holdout|final|reserve other than Python
sources and pytest files.

WHAT CHANGED (the item under review). Route B (protocol fivebench-execskill-v1) evolves a cumulative package of
sandboxed Python procedures over five benchmarks in sequence (SearchQA -> OfficeQA -> LiveMath -> SpreadsheetBench ->
ALFWorld). The chain reads the five test sets once, at its end, in five read units (arms F, C, P_F, T_F, twins). The
owner has now defined the main experiment as: after EVERY step, evaluate that step's package on ALL FIVE test sets.
The as-implemented design is docs/handoff/execskill-v2-20261023/stage-reads.md; the diff is
docs/handoff/execskill-v2-20261023/stage-reads.diff (protocol.py stage block and estimate; cells.share_same;
evaluation.consent/stage_rows/stage_plan/_derived/_linked/_stage_arms/_evaluate/run_unit_spec/unseal; chain.run's
read rule, read_consent and read_estimate_record; readout.side/_source/stage_table/readout/report; new tests
tests/test_execskill_stage_read.py; tests/test_execskill_protocol.py's fired-shares test now allows the stage cells).
Only configuration main-v2 has stage reads (protocol.STAGE_READ). Read the surrounding code in this tree as needed
(registration: docs/handoff/execskill-registration-v1-20261021.md; the v2 spec: docs/handoff/execskill-v2-20261023/
spec-v2.md).

REVIEW FOR (most important first):
1. Measurement validity of the sharing rule: is "same enabled procedure ids in order + byte-identical procedures
   (Procedure.sha256) => byte-identical solver request" true in this code (solver.solve / _Shell / router / sandbox
   worker namespaces / compute <calc> round trip / ALFWorld episodes / SpreadsheetBench workbook path)? Is deriving a
   stage package's routes from F's per-procedure entries valid? Any case where a shared stage cell reports a result
   its own package would not produce, or where the fallback check (source cell's recorded `enabled` vs the planned
   route) misses a divergence?
2. v1 behaviour (default/recommended/main) unchanged: consent sets, estimate arms (4), caps, not-read rule, records,
   unseal/readout results for v1 data (shared cells all from C).
3. Correctness of _evaluate with stage arms: job/share/linked construction, the seeded interleaving, the sources map,
   share_cell/share_same preconditions, fallback ordering, counts in the unit record, a resumed attempt after a pause,
   the infrastructure-unknown and canary rules, the lock/drain path.
4. stage_rows: rows/labels from the step records; the start package (never saved) and the edge case of a later step
   deleting every procedure (F empty, an earlier stage non-empty) through chain.run -> launch -> run_unit_spec ->
   _evaluate -> unseal -> readout.report; any path that crashes or silently reads the wrong package.
5. Consent: exactness for main-v2 (a v1 consent must not admit stage arms), and that the form-only checks
   (test_tasks, make_read_canaries, the CLI) cannot be used to bypass the configuration check.
6. Budget: the estimate formula and read_estimate_record for main-v2, the cap rule (608M test read, 2,055M solver), the
   S-E6 projection (smoke.py _scope_cells uses TEST_READ_CELLS[pilot]), and anything that would make the main-v2 read
   pause for budget or overspend.
7. readout.stage_table statistics: sides (stage arms on L like F), differences with shared cells (0 by construction),
   the masked items, contrasts row - C and row - previous row; anything misleading.

OUTPUT: first line "VERDICT: ACCEPTABLE" or "VERDICT: NOT ACCEPTABLE". Then numbered findings, most severe first,
each: severity (BLOCKER / MAJOR / MINOR), file:line, the concrete failure scenario, and the fix. At most 12
findings; no style nits. If you ran anything offline, say what.
