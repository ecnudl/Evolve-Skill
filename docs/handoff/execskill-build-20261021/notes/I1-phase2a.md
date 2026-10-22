# I1 phase 2a (integrator, route B): the trimmed smoke, S3 rewired, the pilot-readiness wiring

Agent I1, 2026-10-22, 13:27-14:32 (dl clock). Protocol fivebench-execskill-v1. Build tree `/data/execskill-dev`
(= the Mac mount `/Users/dulin/remote/dl`). **Zero model calls, no network, no docker, no git write.** No test pool
read, nothing written under `/data/coevo5-*`, `/data/execskill-20261021-pre`, `/data/execskill-history` or a real run
root; frozen code untouched. Throwaway pytest roots `/tmp/i1-*` on dl were deleted. Progress log:
`notes/I1-progress.md` (the lines first labelled "14:5x" were estimates; the clock read 14:30 when I corrected them).

## Status

| Item (coordinator's 2a list, then addendum 14:3x, then the 14:3x FYI) | State |
|---|---|
| 1. Trimmed smoke (13:0x, 13:4x): summary on S0, S1, S2, S3, S-E6; S-E6 from S2 and S3; smoke-make inputs optional | done, tested |
| 2. PR-C61-1: sheet engines and LiveMath's checker in `manifest.services_of` | done, tested |
| 3. PR-C31-1 CLI, PR-C31-2 (via P2-A3-2), PR-C31-3 (1b) `recover` release (via P2-A3-1) | done, tested |
| 4. PR-C12-2 items 1-2: mutation entries, e2e docstring | done; item 3 (code-map re-pins) is 2b |
| 5. OPS1 supply provenance: `make-items --bench searchqa` records `exclude_sha256` and `datasets_version` | done, tested |
| 6. smoke-runbook.md for the trim, C7e-2 rule, C7c-2 row per C7e.md | done |
| 7. Own and directly affected tests | done (counts below) |
| 14:3x (1) C7d-2: WorkerChecker in `step.Services`, bound to the unit's tag | binding done; the session around `examiner.build` is ticket I1-2 (step.py is not mine) |
| 14:3x (2) C7d-3: `smoke-run --fake` names no credential | done, tested |
| 14:3x (3) C7d-1: S3 in `BUILT_STAGES` and in the rehearsal | done, tested |
| 14:3x (4) S3's own run unit | done in 2a, tested (deviation 1) |
| 14:3x (5) S3's GLM limit 2M, guard and `smoke:glm:s3` kept | done in 2a, tested |
| 14:3x (6) S-E6 projects every GLM scope of both pilot chains | done in 2a, tested (interpretations 4-5) |
| FYI tickets: P2-A1-1, P2-A2-1, P2-A3-4 | done (P2-A2-1 option A only) |
| FYI row 12 (14:10): pilot-runbook §3.1 field shapes | smoke-runbook §5 done; the tests' manifests are 2b |

## Files changed (line numbers as of 14:30)

- `scripts/run_execskill.py`: `_searchqa_items` (:216) records `exclude_sha256` and `datasets_version`;
  `make_canaries` (:250) delegates to `evaluation.select_canaries`; `smoke_make` (:314) takes optional
  `--control-cells` (default []) and `--noise-anchor`; `smoke_run` (:443) refuses `--fake` with a credential and the
  parser's `--env-path` has no default (a real run falls back to `protocol.ELUCID_ENV`); `recover` (:552) calls
  `evaluation.release_check` before writing the frozen-format `recovery.json` (my own `RELEASE`/`_release` removed,
  ticket P2-A3-1); `monitor` (:582) lists per scan attempt `{hits, paused, decided, record_sha256}` (:595); usage text.
- `skillopt/execskill/runcli.py`: `report` catches the scan's `Pause` (:57) and prints `{"paused","reason","at"}`;
  exit `EXIT_AWAITING` (5) for `awaiting_owner_decision`, else `EXIT_PAUSED` (3).
- `skillopt/execskill/manifest.py`: `Services` (:452), a frozen subclass of `step.Services` whose `checker` is a
  `livemath.WorkerChecker` over its own `workers`, made again in `__post_init__` when `_Step.unit` re-binds the
  workers to the unit's tag (`dataclasses.replace`); `services_of` (:466) passes `engine =
  engines.sheet_engines(runtime["spreadsheetbench"], native=..., evidence=...)`.
- `skillopt/execskill/smoke.py`: `SMOKE_STAGES`, `TRIMMED` (:111-112); `make` (:167) records `stages`,
  `noise_anchor` (null + reason) and `control_cells`; `sn1_noise` (:373) measures without an anchor; `summary` (:417)
  passes on the spec's `stages`, others `not_required`, sealed once; `BUILT_STAGES` (:704) with S3; `_s2_judged`
  (:879) adds `ledger` and `concurrent_s3`; `_ledger_rows` (:920) judges this process's reservations, lists
  `others_open`; `S3_PROCESS`, `_s3_tags`, `_leftover` (:936-971) list S3's process and containers apart;
  `SE6_STAGES = ("S2", "S3")` (:1074); `MAX_ROLE_CALLS` (:1078); `_cell_records` (:1088) reads S3's run and
  confirmation cells; `se6_projection` (:1180) adds the GLM rows and block; `_s3_calls` (:1256),
  `role_calls_measured` (:1268), `_glm_fit` (:1283), `glm_projection` (:1288).
- `skillopt/execskill/smoke_roles.py` (C7d's file, mine since C7d finished): `S3_GLM_CAP = SMOKE_CAPS["glm"]` (:83);
  `run_root` (:105) replaces `input_units`; `own_run` (:110), S3's own run unit; `_calls` (:391) adds
  `request_bytes`; `unit` (:430) reads its own completed run unit (parent trajectories for the detector); `run`
  (:487) runs `own_run` first; `CARD_ARM` removed; docstring.
- `skillopt/execskill/readout.py` (routed by the coordinator, ticket P2-A2-1 option A): `answer_tag_share` is None in
  a window without any `tag_present` (:469); alias `windows = _windows` (:478).
- `skillopt/execskill/evaluation.py`: one line, alias `completion_tokens = _completion_tokens` (:322, ticket P2-A2-1).
- Tests: `test_execskill_cli.py` (smoke-run refusals, searchqa provenance, trimmed smoke-make, recover release on
  P2-A3's messages, monitor format), `test_execskill_runcli.py` (Pause → 3/5), `test_execskill_manifest.py` (services:
  engine and checker; `test_c7d_2_the_livemath_checker_follows_the_units_tag_bound_workers`),
  `test_execskill_engines.py` (P2-A1-1), `test_execskill_smoke.py` (5 new: trimmed spec, summary, S2 ledger row,
  S2 leftover row, GLM projection),
  `test_execskill_smoke_roles.py` (fixture runs `own_run` instead of S2/S4; S3 needs no other stage; own_run
  credential refusal), `test_execskill_smoke_rehearsal.py` (S3 in the rehearsal; S-E6 GLM rows), `test_execskill_e2e.py`
  (P2-A3-2 patch, optional scan assertion, PR-C12-2 docstring), `test_execskill_integration_b5.py` (P2-A3-3),
  `test_execskill_mutations.py` (entries 31-36), `test_execskill_readout.py` (1 new, P2-A2-1).
- Docs: `smoke-runbook.md` (rewritten for the trim), `pilot-runbook.md` §7.4 (ticket P2-A3-4 verbatim; sha256
  `64531ae6…` before, `ad845ec2…` after), `tickets/I1-2.md` (new), `notes/I1-progress.md`, this note.

## Public API changes

- `smoke.make(root, *, items, selftest, control_cells=(), noise_anchor=None, stages=SMOKE_STAGES, ...)`; the result
  of `smoke.summary` has `required` and stages `not_required`; `smoke.BUILT_STAGES` includes S3.
- `smoke._leftover(docker, *, fake, root=None)` now returns `(verdict, concurrent)`; `smoke._ledger_rows` returns
  `{reserved, settled, others_open}`. The S2 record gains `ledger` and `concurrent_s3`.
- `smoke.MAX_ROLE_CALLS`, `smoke.role_calls_measured(calls)`, `smoke.glm_projection(measured, pilot=PILOT)`; the
  S-E6 record gains GLM rows and a `glm` block {scopes, measured, max_calls, s3 spend, smoke_glm}; `passed` needs
  every GLM scope to fit.
- `smoke_roles.run_root(spec)`, `smoke_roles.own_run(spec, m, manifest_path, *, fake=False, env_path=None,
  roles_repo=None)`; `smoke_roles.input_units` and `CARD_ARM` are gone; a role call record has `request_bytes`.
- `manifest.Services`; `manifest.services_of` returns one with `engine` and `checker` set.
- CLI: `smoke-make` flags optional; `smoke-run --fake` with `--env-path`/`--roles-repo` is refused; `recover` uses
  `evaluation.release_check`; `monitor`'s `root_scans` entries are dicts; `report` exits 3/5 on a paused scan.
- `readout.windows`, `evaluation.completion_tokens` (aliases); `answer_tag_share` None without an answer tag.

## Deviations and interpretations (for the registrar)

1. **S3's run unit runs 20 cells, not about 60.** 14:3x says "the S4 mini-step's run sub-step only (the 60 S4
   SearchQA items ...) ... About 60 solver cells." The mini-step's run sub-step (`step._slices` smoke cut,
   `protocol.S4_SLICES = {"run": 20, "accept": 40}`) runs the first 20 of the 60, one run each (`SLICES["searchqa"]
   ["run"][1]`), parent arm only (the empty package fires nothing, so no C arm), plus one confirmation cell: 21
   solver calls. The engineer is shown at most 18 run trajectories in any step (`ENGINEER_SHOWN` 12 + 6), so S3
   still measures a full-shaped engineer request. I kept the registered cut; running all 60 would need another cut.
   Paths: `<root>/units/S3/s1-searchqa/run` (label `smoke/s1-searchqa/run`, the same label as S4's run unit under
   `units/S4`), registry `<root>/units/S3/history`, confirmation units `<root>/units/S3/confirm-<n>`.
2. **The detector reads S3's own run unit** (its parent trajectories, the production `_diagnose` input), not S2's C
   arm as in C7d. That is what makes S3 independent of S2, as "S2 ∥ S3" requires.
3. **S2 ∥ S3 rows.** S2's ledger row requires that THIS process's reservations on `smoke:solver` are all settled
   (open entries matched by the frozen budget's owner pid/host/start); another process's open amount is listed as
   `others_open`. S2's leftovers row excludes S3's process (`smoke-run ... --stage S3`), processes naming S3's
   containers and S3's containers (named for S3's unit tags), listed as `concurrent_s3`; any other route-B process or
   container still fails the row. S-E6 still requires nothing open at all. The slot pools are machine-wide lock files
   (`protocol.SLOT_ROOT`), so S2 and S3 share the deepseek/GLM/sandbox limits. Fallback in the runbook: run S3 after
   S2.
4. **GLM maxima per step** (`smoke.MAX_ROLE_CALLS`): engineer `ENGINEER_CALLS` 6; examiner `DETECTOR_CALLS +
   POLICY_CALLS + GENERATOR_CALLS × BAND_ROUNDS` = 9 (protocol.py's calc-T11 comment); examiner research
   `MAX_RESEARCH_REQUESTS × RESEARCH_MAX_CALLS` = 24 × 8 = 192 (calc T11); leakage 2 × `MAX_CHANGES` = 6 and
   describer `MAX_CHANGES` = 3 are **derived** (one adjudication per check, a change checked as proposed and as fixed;
   one describer call per added or revised procedure), not registered numbers. Please confirm.
5. **The next reservation** is the frozen formula 4 × (bytes + 512 + 16,384) on the largest request S3 sent for the
   scope's roles (the addendum's "S3 is the only measurement of real role-request sizes"). Per-call tokens are S3's
   SearchQA measurements applied to the SpreadsheetBench and OfficeQA steps. A pilot role request can carry up to
   `ROLE_INPUT_BYTES` = 220,000 B of input (≈ 0.95M reserved), more than SearchQA's may. Disclosed in the runbook
   §0, not corrected. The GLM ratio is 1: a role call's charge is the ledger's settlement.
6. **A noise anchor given without S-N1** is still recorded (lenient); S-N1 without an anchor measures and judges no
   ratio.
7. **P2-A2-1**: option A only (None where no cell of the window has `tag_present`). Option B (a bench-neutral
   `format_share`) is the registrar's choice and is not built. `acceptance.series` still imports the private names;
   switching it to the new aliases is one line each in acceptance.py (not mine).

## Tickets

- Closed: C7d-1; C7d-2 (binding; session → I1-2); C7d-3; PR-C61-1; PR-C31-1 (CLI part); PR-C31-2 (via P2-A3-2, entry
  31); PR-C12-2 items 1-2; P2-A1-1; P2-A2-1 (option A + aliases); P2-A3-1, P2-A3-2 (entries 34-36), P2-A3-3, P2-A3-4;
  OPS1 provenance; 13:4x smoke-make inputs; 13:5x C7e-2 runbook text; C7c-2 runbook row (per C7e.md).
- Opened: **I1-2** (owner of step.py): `checker.session()` around `examiner.build` in `step._build`, exact patch in
  the ticket; optional public run-only step entry for `smoke_roles.own_run`.
- Still open elsewhere: C7e-2 enforcement in `recover` (14:10 row 17, P2C); C7e-1 (G_acc scope, parallel workflow).

## Tests (dl, zero calls, zero network)

- cli + integration_b5 + canaries + evaluation + manifest + smoke + runcli + engines: **123 passed** (22.6 s).
- e2e: **11 passed** (332.5 s), after the P2-A3-2 patch.
- mutations, the six new entries (`-k "31 or ... or 36"`): **6 passed** (16.6 s); the module fixture first ran the
  named tests of all 37 entries unmutated on the copy, and each new mutation makes its named test fail. The other 31
  mutation runs were not repeated (2b whole suite).
- readout + acceptance + evaluation + canaries + cli after P2-A2-1 and the docstring edits: **107 passed** (69.8 s).
- smoke_roles + rehearsal + smoke + manifest + runcli + engines + integration_b5 (final): **77 passed** (126.0 s), the
  last run at 14:3x on the tree as it then was (P2C editing in parallel).
- Not run: the whole suite and the frozen gate-(iii) tests (2b).

## Phase 2b (for the coordinator)

- Fresh-copy whole suite + gate (iii) frozen tests; the whole mutation suite (37 entries).
- Full CLI fake rehearsal S0 → S1 → S2 → S3 → S-E6 → summary (`smoke-run --fake` now works without credentials).
- Re-pin code maps (PR-C12-2 item 3): changed since the last pins at least `solver.py`, `cells.py`, `examiner.py`,
  `evaluation.py`, `readout.py`, `manifest.py`, `smoke.py`, `smoke_roles.py`, `step.py`, `acceptance.py`,
  `scripts/run_execskill.py`, plus P2C's `chain.py`/`protocol.py`.
- Row 12 (14:10): the tests' manifests get pilot-runbook §3.1 shapes (cards = texts).
- acceptance.py: switch to `readout.windows` / `evaluation.completion_tokens` (owner's call).
- Integration fixes after P2C. P2C may now edit `scripts/run_execskill.py` (`recover`, row 17) and
  `tests/test_execskill_mutations.py`: my 2a edits there are complete.
