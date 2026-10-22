# M-V progress (builder V, M round, 2026-10-22 evening)

Items: Codex #1 BLOCKER (SB test routing + placebo-length replay without workbook mounts), #3 MAJOR (qualification
artifacts cleaned on every exit; interrupted attempts swept). Files owned: skillopt/execskill/evaluation.py,
skillopt/execskill/qualify.py and their tests. Mutation numbers reserved: 78-80.

## Log
- 18:1x started; read M-coordination, registrar decisions (15:5x, R7, I1-3, 17:0x/17:3x), Codex #1/#3.
- 18:3x code for #1 and #3 written in evaluation.py (qualify.py unchanged so far):
  #1 `public_inputs(bench, {item: task})` (read-local map item -> public view's input_files[0]; a path the private
     `test_files` names is refused) + `mounting(workers, inputs)` (fresh `solver._inputs_dir` copy as the only
     /input/input.xlsx, `workers(package, item, inputs_dir=)`, removed after); wired in `test_plan` (routing) and in
     `placebo_arm.arm` (placebo-length replay); `_route_worker(..., *, inputs_dir=None)` passes it to with_worker.
  #3 `_sheet_qualification`: `_swept_qualifications(root)` under the lock before the pointer check (sweep record
     `scorer-artifacts-swept.json`), try/except/finally around `qualify.qualify` -> `_qualification_cleaned(attempt,
     when)` on every exit (record `scorer-artifacts-deleted.json`, kind transient-deletion, {files, manifest_sha256,
     entries, when}); keeps only QUALIFICATION_KEPT (qualification.json, status.json, recovery.json, scores/, the two
     records); then requires no kept file is a workbook (zip magic). Non-Pause exceptions now also write status.json
     (kind configuration/exception, type name only) when the attempt dir exists.
  Existing tests: evaluation + qualify + canaries 40 passed after the change. Next: new tests file
  tests/test_execskill_evaluation_sheet.py, then mutation entries 78-80.
- 18:4x FOUND + FIXED (my file): `placebo_arm` seeded `donors.pair` with "<unit>:<item>", which `protocol.yoke_tag`
  refuses (TAG_PART admits no ':'), so EVERY P_F arm raised ValueError at its first job -> every test read with an
  accepted procedure would pause as `configuration` (never exercised end to end before: the evaluation tests pass their
  own P_F function, the canaries test fakes `evaluate`). Now `yoke_seed(unit, item)` = "<unit>/<sha256(item)[:16]>".
- Tests: new tests/test_execskill_evaluation_sheet.py (9 tests): full SB read through `evaluate` (qualification, real
  `placebo_arm` with a donor corpus, workbook-reading hooks via the worker's own `public_workbook` helper), placebo
  lengths with/without mount, reference never mounted, yoke_seed, qualification success / failed (configuration,
  exception; drain-ordered with an Event) / interrupted-retry sweep / workbook among kept results refused.
- Mutation entries 78-80 added (between 77 and W's 81); verified on a /tmp copy: site once, unmutated pass, mutated fail.
  Ad-hoc negative checks (no sweep, no reference guard, old yoke seed, no workbook check, success keeps host_only,
  mount dir not removed) each make their test fail.
- Targeted run: evaluation + evaluation_sheet + qualify + canaries + placebo + runcli = 62 passed.
- 18:4x final: qualify.py docstring notes the test-side cleanup (no behaviour change). ruff (repo config) clean on my
  files apart from the package-wide compact-import I001 style (46 hits across skillopt/execskill, pre-existing, left).
  Mutation 80's replacement split below 120 chars; 78-80 re-verified (unmutated 4 passed, each mutation fails its test).
  e2e + integration_b5 12 passed (they read OQ; mounting is a no-op there). Frozen diff vs 010d453 empty. Items logged
  in M-coordination. DONE (no remaining V work; open questions in the final report / coordination log).
