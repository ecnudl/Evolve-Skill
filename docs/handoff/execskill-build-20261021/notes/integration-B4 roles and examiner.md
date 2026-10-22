# Integration B4 (method roles + examiner): rows A10 and A11 wired together

Integrator B4, 2026-10-22. Rows A10 (`engineer.py`, `replay.py`, `describer.py`) and A11 (`research.py`,
`generators/*`; `detectors.py` and `examiner.py` were not delivered). Registration `execskill-registration-v1-20261021.md`
wins over the plan. No model call, no container, no test-pool data, no state-changing git. Everything here is an
engineering fixture (`engineering_fixture`); nothing is evidence of a method effect.

## Gate: PASS

| Gate item | Where | Result |
|---|---|---|
| C1-C9 engineer pipeline on fixture procedures with FakeGLM | `tests/test_execskill_engineer.py` (6 tests, A10) and the new `tests/test_execskill_integration_b4.py::test_b4_examiner_engineer_and_describer_on_real_run_slice_trajectories` | pass |
| T-DET-4 | new `tests/test_execskill_detectors.py::test_det4_all_failures_run_50_steps_yet_a_landmark_detector_can_be_accepted` | pass |
| T-GEN | `tests/test_execskill_generators.py` (T-GEN-1..6, 11 tests, A11) | pass |

T-DET-4 needed `detectors.py`, which A11 did not deliver, so the integrator wrote it (below). In T-DET-4:

- Every failure runs 50 steps, so every failure carries the whole-episode category `step_budget_exhausted`.
- Even so, the residual cells, defined by `MECHANICAL_MASKED` on the 10-step landmark view, still hold 16 failures
  among 32 cells.
- The view-only detector "the first action is inventory" is accepted.
- The detector `len(view["steps"]) == 50` never fires and is not accepted (`too_few_alarms`).
- Plan §8.3 mutation (13), residual cells defined by the whole-episode categories, would leave no residual failure,
  and this test would then fail.

## pytest (dl, `/data/execskill-dev`, `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider`)

- `tests/test_execskill_*.py tests/test_weak_solver_probe.py tests/test_coevo5_core.py`:
  **`836 passed in 81.62s`**.
  - Route B: 746. Frozen: `90 passed in 0.49s`.
  - Before the B4 edits: 827 passed (737 + 90).
- The B4 suites alone give `55 passed in 24.87s`:
  - engineer, replay, describer: 22;
  - research, generators: 24;
  - detectors: 7 (new);
  - integration_b4: 2 (new).
- Afterwards there is no `__pycache__` or `.pyc` under `skillopt`, `tests` or `scripts`, and `git status` shows no
  modified tracked file. The frozen files are untouched.

## Files written or changed (each edit minimal)

1. **New `skillopt/execskill/detectors.py`** (A11's undelivered part of the row; registration §5.2, §7.1, Codex F10,
   F11, check C2). Public API:
   - `Detector(id, bench, source, description)`.
     - `id` is `d-<bench>-<k>-<n>`, or `fx-` for fixtures.
     - The source must pass `policy.check(source, bench=)` and define `detect(view)` at module level.
     - The description has at most 600 characters.
     - A violation raises `ValueError` (never a stop class).
   - Mechanical categories:
     - `MECHANICAL[bench]` and `MECHANICAL_MASKED[bench]`, each a `{name: test}` table;
     - `mechanical(trajectory, *, bench)` and `mechanical_masked(view, *, bench)`, each returning a sorted name
       list;
     - `diagnosis(trajectories, *, bench)` returns `{cells, failed, categories{name: {cells, failed}},
       failing{cell: [names]}}`. This is what `engineer.Context(detectors=)` shows the engineer.
   - Split and sealing:
     - `split(trajectories, *, bench, unit, rooms=None)` returns `{unit: item|room, tag, status: ok|cannot_decide,
       write_<unit>s, hold_<unit>s, write, hold}`;
     - `candidates_sha256(detectors)`;
     - `seal_candidates(root, detectors, *, unit, written_from, evidence)` writes `<root>/candidates.json` once,
       as the record `fivebench-execskill-v1-detector-candidates`.
   - Evaluation and decision:
     - `hold_cells(trajectories, *, bench)` returns `({cell: {view, item, failed}}, {reason: n})`;
     - `evaluate(detectors, views, workers, *, hashseed=0, reverse=False)` returns `{id: {fired, faults}}` and uses
       sandbox kind `detector`;
     - `bootstrap_p(...)`, `jaccard(a, b)`;
     - `validate(sealed, detectors, halves, *, bench, library, workers, rooms=None, evidence)` returns the record
       `fivebench-execskill-v1-detector-validation`;
     - `detector_records(validation, detectors, *, written_from, evidence)` returns the plan §2.4 records
       `fivebench-execskill-v1-detector`.
   - The acceptance rules are §7.1 exactly, with the registered constants of `protocol.py:344-356`:
     - fired ≥ 10 residual cells from ≥ 6 items (ALFWorld: also ≥ 4 rooms);
     - item-cluster (ALFWorld: room-cluster) bootstrap, 10,000 draws, one-sided p of
       "precision − base ≤ 0.10", Holm-adjusted over the step's candidates (`stats_ext.holm`), ≤ 0.10;
     - residual recall ≥ 0.15;
     - Jaccard with every accepted detector < 0.8, computed on the WHOLE included hold half before
       residualization;
     - no fault, and the two runs agree (PYTHONHASHSEED 0 in sorted order, 1 in reverse order).
2. **New `tests/test_execskill_detectors.py`** (7 tests, T-DET-1..6):
   - masked views hide answers, run status and step count;
   - category rules;
   - residual metrics and Jaccard on the full hold half (60/72 marks a duplicate that a residual-only Jaccard,
     always 0, would accept);
   - T-DET-4;
   - landmark exclusions by outcome, and the terminal text "You won" is never visible;
   - room split (14 rooms: `cannot_decide`, without touching the sandbox);
   - sealing: a changed candidate is refused, and `candidates.json` is write-once;
   - Holm (0.04 passes alone, but not beside 0.06 and 0.08);
   - faults and hash-seed dependence block acceptance;
   - candidate policy.
3. **New `tests/test_execskill_integration_b4.py`** (2 tests). The cross-row test runs on the 24 REAL parent
   trajectories of the B3 run slice (`run_slice`: real `cells.run_cell` + `TrainingStore`):
   - `detectors.diagnosis`, `split`, `seal_candidates` and `validate` on their masked views, in the real worker
     (FakeDocker);
   - `engineer.run` with a function-scripted FakeGLM:
     - the valid change survives C1-C9;
     - the crashing change fails C6, and fails again after its fix;
     - the leaking change, a run-slice reference answer absent from every public view, fails C4 twice with
       adjudication;
     - the role-call order is engineer, engineer, leak_adjudicate, engineer, leak_adjudicate;
   - the failures shown to the engineer carry their references;
   - the payload shows `detectors.diagnosis`;
   - the engineer's procedure in the REAL shell (`solver.solve` + FakeDocker `Worker`) adds its note in F;
   - `describer.describe` (one call) leads to `with_describer`;
   - T_F shows the frozen text instead of the note;
   - T_F with the procedure withheld shows nothing (ticket A10-3).

   The second test covers ticket A10-2.
4. **`skillopt/execskill/donors.py` `donor_inputs` (ticket A10-2).** The function now accepts an ALFWorld episode
   with one more step request than stored steps. The shell logs a step only after a usable reply
   (`solver._solve_alfworld`), so such an episode arises from a truncated or filtered last step reply:
   - the unanswered request keeps its view (the shell ran `alf_before_step` on it), with no action and no event;
   - the step before it gets its event from that request.

   This is the rule `replay.inputs_of` already applies; the new test asserts that both read such an episode
   identically. Without the change, `donor_corpus` raised `ValueError` on any run slice holding such an episode. The
   docstring is updated.

## Checked across the rows (matched; no change)

- **Real trajectories into replay.**
  - `replay.inputs_of` reads what `trajectories.build` writes: `calls[].purpose/user` and `shell.precheck`.
  - The engineer's C6 (`zero_crash`) and C7 (`run_tests`, non-vacuity by `strip_digits`) run on the real stored
     views in the real worker.
  - The test cites a stored failing cell id (A10 deviation 3).
- **Engineer payload.** `references` are keyed by the trajectory's `task_id`. On run-slice trajectories that is
  `rounds.key` = `<bench>/<task_id>` (the B3 note's open item 3). The caller (`step.py`, A12) must build them that
  way. The integration test does, and checks that every shown failure carries its own reference.
- **C4 on real items.** `leakage.Corpus(bench, run-slice items)` is the frozen corpus. A note's numbers taken from
  the item's own table are subtracted (FA-F12). A run-slice answer absent from every public text is a hit.
- **Shell and sandbox.**
  - The engineer's `Procedure` loads in `sandbox.client.Worker` (kind `cell`) through `solver._Shell`.
  - `generators.families.Bundle`/`Entry` load detector bundles (kind `detector`). The worker accepts any declared
    entry point (`worker.py:598-600`).
- **Describer to package to shell.**
  - `describer.entries` gives `package.with_describer` its input.
  - `describer.texts` gives `solver.solve(text=)` its input.
  - The T_F text replaces the note where the procedure has output.
- **Masked views.** `trajectories.masked_view`/`landmark_view` (A8) are the only views `detectors` reads. ALFWorld
  exclusions use A8's reasons (`ended_by_step_10:<won|done|infrastructure>`, `censored:infrastructure`). An
  infrastructure token on a QA or sheet cell is excluded as `censored:infrastructure`.
- **One exception set.** Every refusal in `detectors` is a `ValueError` (via `require`). The stop classes are
  imported only where they were before; no new exception class.

## Frozen code relied on (read-only; mirror at 010d453; dl copies unchanged)

- `skillopt/coevo5/checks.py:12` (`ANSWER`) and `:16-21` (`last_answer`).
- `skillopt/continual_eval/code_delivery.py:21-75` (`extract_python`: status, `explicit_python_blocks`; a bare
  unfenced reply is a candidate, hence the separate `excel_formula_only` rule).
- `skillopt/coevo5/data.py:173-176` (`ranked`, the seeded split order with `protocol.detsplit_tag`).
- `skillopt/continual_eval/backends.py:727` (`max_steps` default 50, for `step_budget_exhausted`).
- `skillopt/coevo5/leakage.py`: `:146` (`Corpus`) and `:280-291` (`adjudicate`; "yes" drops).
- `skillopt/validator_pilot/api.py`: `:40-42` (`digest`) and `:45-53` (`write_immutable_json`, a differing rewrite
  raises `ValueError`).
- `skillopt/continual_eval/core.py`: `:30-32` (`require`, which raises `ValueError`) and `:60-61` (`write_json`).

## Deviations in `detectors.py` from the plan row (with reasons)

1. **Signatures.**
   - `split` takes `unit` (the tag is `protocol.detsplit_tag(unit)`) and `rooms`, a {trajectory `task_id`: room} map.
     A trajectory does not carry its room; for run-slice trajectories the keys are in the `rounds.key` form.
   - The plan's `accept` is `validate`, which returns one sealed record for the step.
   - `seal_candidates` writes the sealed record, and `candidates_sha256` gives the bare digest.
   - `evaluate` takes the worker factory, because two workers are needed for the determinism check.
2. **Category rules are registrar definitions.** The registration only names the categories (module docstring).
   `level1_canonical_share` fires above 0.2, like the other share categories. This choice is descriptive only:
   it is not in the masked set, so it never touches the residual.
   On the masked views:
   - QA keeps all five categories, with `truncated_or_suspected` reduced to its text part (an open answer tag), and
     reads the view's LAST reply, since the deciding index is not in the view;
   - SpreadsheetBench drops `program_exception_on_public_input` (run status);
   - ALFWorld keeps `revisit_empty_receptacle>=3`, `repeated_action_loop` and `nothing_happens_share>0.2` (the view
     has no step count, admissible list or `how`).
3. **"cannot_decide".** The status is named after the plan row and registration §7.1 ("无法判定"). T-DET-6 says
   "undecidable"; the meaning is the same. A hold half that can never meet the counts is "cannot_decide" outright,
   without running any detector: fewer than 10 included cells, fewer than 6 items, or on ALFWorld fewer than 4
   rooms. Registration §7.1 says "题量太小时直接写'无法判定'".
4. **Jaccard against the library only.** "和已有检测器" means the accepted detectors, not the step's other
   candidates. Multiplicity among candidates is Holm's job.
5. **Library faults and empty bootstrap draws.**
   - A library detector's fault on a hold cell counts as "not fired" for the residual, and the record counts it.
   - A bootstrap resample with no alarm counts for the null, which is conservative.

## Tickets

- **A10-1 (A1, protocol constants): open.** `TRACKER_AGREEMENT`, `STATE_FACTS`, the replay vocabulary, the engineer
  seed tag and `DEFAULT_TARGET` still live in A10's modules. Nothing depends on moving them. The prompt hashes belong
  in A13's manifest (B5).
- **A10-2 (A9, donors): resolved** (edit 4, with a test).
- **A10-3 (A6 / test-read orchestration): resolved by contract, no code change.** The T_F arm of the test read
  (`evaluation.py`, A12, B5) passes `text=describer.texts(records)` and
  `withhold=frozenset(ids of note-hook procedures absent from it)`, and reports their count. A withheld procedure's
  predicate still runs (logged `shadow_fired`), and it shows nothing and runs no hook. The integration test shows
  this through the real shell. A `no_note_hook` procedure may stay unwithheld, since it shows nothing in F either.
- **A11-1 (A12, `qualify.py`; run wiring): open for B5.** `execskill.qualify` does not exist yet. `generators.sheet`
  calls an injected `Engine.qualify` with the frozen signature and reads `qualified`/`scorings_per_item`.
- Earlier tickets are unchanged by B4. Still open from B3: A5-2 (drain check with two chains), A9-2 request 2
  (dispatch order) and A9-3 (MDE).

## Open (not done in B4)

1. **`skillopt/execskill/examiner.py` and `tests/test_execskill_examiner.py`** (A11's row) are not written. This
   covers:
   - `detector_write`, which must turn the model's ≤ 3 sources into `detectors.Detector` and drop invalid ones;
   - `generator_write` (family + parameter ranges + research requests);
   - `research_requests`, `policy_revise`;
   - the gates T (truth), D (band), S (shortcut), L (labels).

   The building blocks exist (`research.Researcher`, `generators.generate`, `detectors.*`). The gate did not
   require them. Without them there is no examiner role call in the step (`step.py`, B5).
2. **Detector retirement.** After two consecutive misses on later hold halves of the bench
   (`DETECTOR_RETIRE_MISSES`), a detector is retired. That is step orchestration: rerun `validate` with the library
   detector as a candidate. Not implemented.
3. **Caller duties (`step.py`, A12).** `references` and `rooms` are keyed by the trajectory `task_id`
   (`rounds.key` form). SpreadsheetBench replay needs `inputs_dirs` (A10 note).
4. **No real-docker or real-model run.** A real sympy checker, real GLM-5.3 and real containers are S0/S3 smoke
   items.
