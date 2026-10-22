# C7d: smoke stage S3 (method roles)

From C7d, 2026-10-22. Route B, protocol `fivebench-execskill-v1`, dev tree `/data/execskill-dev` (dl). Sources:
registration §10 S3 row ("S3 角色（GLM ≤ 0.5M）…流程跑通"), §7.2, §21 owner rule (b); plan §10 step 7;
notes/C7c.md ("S3: exactly what is missing"); ticket C6-1. Zero model calls and zero network were used. The only
real run was the throwaway LiveMath checker in the pinned image, recorded below.

## Files

| file | change |
|---|---|
| `skillopt/execskill/smoke_roles.py` | **new**: the S3 unit, its guards and its judge |
| `skillopt/execskill/generators/livemath.py` | **added** `WorkerChecker` (+ `contextmanager` import). `CHECKER_SOURCE`, `SandboxChecker` and the rest are unchanged |
| `skillopt/execskill/smoke.py` | `S3_ROWS` gains `"glm_cap"`. `run_stage` admits S3 and dispatches it to `smoke_roles.run`, with one docstring sentence. The `BUILT_STAGES` comment changed; its value did not (ticket C7d-1) |
| `tests/execskill_fakes_s3.py` | **new** fakes: `S3Script`, `SympyDocker` (+ `SYMPY_STUB`), `S3Rehearsal`, `wrong_model_first`, `PARAMS`/`TRUTHS`. No existing fake changed |
| `tests/test_execskill_smoke_roles.py` | **new**: 8 tests |
| `docs/handoff/execskill-build-20261021/tickets/C7d-1.md`, `C7d-2.md`, `C7d-3.md` | tickets |

## What S3 does (`smoke_roles`, one copied unit `<root>/units/S3/roles`, label `smoke/S3/roles`)

All calls are GLM-5.3 through the frozen client. Each role has its own frozen `Roles` over
`budgets.endpoint(setting, budgets.glm_scopes("smoke", role, None, None) + ("smoke:glm:s3",),
client=setting.clients(ROLE_MODEL, None), max_tokens_bound=ROLE_MAX_TOKENS)`, behind the guard (below). The solver
makes zero calls. In order:

1. **Leakage adjudication: the first call.** `coevo5.leakage.adjudicate` on a registrar-fixed text, the description
   of fixture `fx-note`, with label `leak/smoke/S3/roles/fx-note`. Its first send must come back `ok` with
   `returned_model` in the role client's `response_model_ids`. Otherwise the unit pauses with
   `first_call_not_confirmed`, and the guard refuses every later send and every resend cooldown. Row `leakage`: the
   verdict is valid.
2. **Engineer.** One `engineer.run` (proposal, C1-C9, at most one fix per change, ≤ 6 calls). Its input is the
   stored trajectories of the S4 mini-step's run unit `<root>/units/S4/s1-searchqa/run` (deviation 1). References
   come from its failed items' `private.answer(s)`, the corpus is its items, and `detectors.counts` covers its parent
   cells. Row `engineer`: at least one proposal parsed, it proposed at least one change, and every change went
   through the fixed checks. A change need not survive.
3. **Detector.** `detectors.split` on the card-arm (C) trajectories of S2's SearchQA unit (by item), then
   `examiner.detector_payload` / `detector_write` (k = 1). Next, `detectors.seal_candidates` writes
   `attempt/detectors/candidates.json` before the hold half is read, and `detectors.validate` runs in the sandbox.
   Row `detector`: at least one candidate, and the validation status is `ok`.
4. **Research, then generation (§21 b).**
   - One `research.Researcher(...).family_material(concept="derivative")` on LiveMath. It is screened by
     `leakage.mechanical` against the Setting's LiveMath pool (in the smoke, its 20 LiveMath items). The frozen
     archive comes from `m["data"]["research"]`, opened with its index hash checked. Wikipedia goes through
     `research.Wikipedia(proxy=protocol.GATEWAY)`, which uses `trust_env=False`. Pages are archived write-once
     under `attempt/research/sources/<digest>.json`. The loop is capped at 8 calls (`RESEARCH_MAX_CALLS`).
   - Before generation, `smoke_roles.provenance` re-checks four things: the finding is this attempt's one dispatched
     request, its calls were made through this attempt's roles (`roles.count(label) == calls`), its page is archived
     here under its own digest, and the quote is verbatim on that page. Any failure raises
     `ConfigurationError("generation_without_research…")`, so the unit pauses `configuration`.
   - Then `research.split` → `examiner.generator_payload("livemath", g_self)` → `generator_write` (the examiner) →
     `examiner.build` with generator `g-livemath-1-1`, set `G_self`, and `checker=livemath.WorkerChecker(workers)`
     inside one `session()`.
   - If research finds nothing, nothing is generated (no fallback).
   - Row `generator_research`: provenance passed, generation ran, at least 5 items were kept with a checker-solved
     truth, and the checker solved at least 5 instances exactly.
5. **Describer.** One `describer.describe` call on the engineer's first surviving procedure with a note hook, or on
   the fixture `fx-note` if there is none. Note lengths come from `replay.replay_many` on the S4 parent cells (zero
   calls). Row `describer`: a reply arrived and the screen left text.
6. **Row `glm_cap`.** S3's GLM total is ≤ 0.5M.

Money guard (`Guard` / `Metered`, a wrapper of the frozen `Endpoint` that `Recorder` drives):
- **Before `Endpoint.send` reserves anything,** a send is refused (`BudgetStop`; the unit pauses `budget`; nothing
  is reserved or sent) when S3's spend so far plus the call's single-attempt bound (`ledger.attempt_bound`) exceeds
  `S3_GLM_CAP` = 500,000.
- **Spend across attempts** is exact, from the accounting sub-scope `smoke:glm:s3`. It is declared on the smoke
  ledger at the smoke GLM cap (2M), so it never binds before `smoke:glm` does.
- **Recorded spend:** before, spent, total and per role, plus the first reply (`glm.json` per attempt, the unit
  result and the stage record).

Records of one attempt: `glm.json`, `role-calls.json` (every role call with its sends and receipts),
`detectors/candidates.json`, `research/sources/*.json`, `research-split.json` and `generated-G_self.json`. Then
`unit.json` (result: `pieces`, `glm`, `calls`, `ran`), and the write-once stage record `<root>/stages/S3.json`
(`smoke.record`), whose `result` is `{rows, passed, unit, unit_sha256, glm}`, judged by `smoke.s3_roles`. A unit that pauses gives the stopped report,
the same as S2 (`{"stage", "complete": false, "stopped", "reason", "unit"}`), and nothing is recorded.

## Public API

- `smoke.run_stage(spec, manifest_path, "S3", *, fake=False, env_path=None, roles_repo=None)` calls
  `smoke_roles.run(spec, m, manifest_path, fake=, env_path=, roles_repo=)`. It returns the S3 stage record or the
  stopped report. A recorded S3 is refused ("Stage S3 is recorded").
- `smoke_roles.unit(spec, m, manifest_path, *, fake=False, env_path=None, roles_repo=None, rehearsal=None,
  name="roles", cap=S3_GLM_CAP)` returns the unit record or the stopped report and writes no stage record.
  `smoke_roles.judged(unit_record)` gives the stage result. `smoke_roles.backends(...)`: real mode is
  `smoke._backends(fake=False)`; fake mode is `S3Rehearsal`.
- The S3 record's `result.glm` is `Guard.state()`: cap, scope, before, spent, total, within_cap, by_role, sends,
  first and refused. S-E6's `smoke._roles_measured` (someone else's code) reads spent, total, by_role, sends,
  cap and within_cap from it; all six are present.
- `livemath.WorkerChecker(workers)`: `.session()`, `.solve(spec)` and `.solved`. See ticket C7d-2 for wiring it into
  `step.Services`.
- **Operator needs:** the S2 SearchQA unit and the S4 run unit must be complete; S3 refuses before anything is sent
  otherwise. In real mode, `env_path` must equal the manifest's D `env_path` and `roles_repo` the G `env_path`
  (`smoke._backends` checks both and also runs `verify_unit`). The pinned image must be present. Network goes only
  through the gateway (GLM-5.3 and Wikipedia).

## Operator command (real; on dl, from the verified snapshot, after S4 and SE6, as in notes/C7c.md)

    cd /data/execskill-20261021-source && unset OPENAI_API_KEY OPENAI_BASE_URL && export PYTHONDONTWRITEBYTECODE=1 &&
    /root/continual-alf-prep-20260928/env/bin/python -B scripts/run_execskill.py smoke-run \
      --spec /data/execskill-20261021-pre/smoke/smoke.json --manifest <smoke manifest> --stage S3 \
      --env-path /root/.config/weak-solver/elucid.env --roles-repo <clients.solver.G.env_path>

Exit codes: 0 = passed; 3 = failed, or a stopped report. The Python form is
`smoke.run_stage(SPEC, MANIFEST, "S3", env_path=..., roles_repo=...)`. `--env-path` defaults to
`protocol.ELUCID_ENV` (the same file) and must equal the manifest's `clients.solver.D.env_path`.

A paused S3 attempt runs again only after the owner records a decision in it, as for S2/SN1 (the units rule):
`scripts/run_execskill.py recover --attempt <root>/units/S3/roles/attempt-N --decision '<text>'`, then the same
`smoke-run`. `smoke-recovery` is only for S4's drill.

Expected spend: 8-18 GLM calls (leakage 1, engineer 1-6, detector 1, research 3-8, generator 1, describer 1).
I cannot promise that they fit in 0.5M; that depends on the real request sizes, which no fake shows. A call is
sent only while S3's charged total (the provider's reported prompt + completion tokens, plus the full bound of any
client attempt that failed without being refused) plus its own single-attempt bound (request bytes + 512 + 16,384)
stays at or under 500,000. A maximal 220,000-byte request therefore needs 236,896 of headroom. If the engineer's
calls are all near 220 KB, a later piece can be refused. S3 then pauses `budget`, and `glm.json` names the refused
label with its bound and the total. A new attempt starts from the earlier spend (the sub-scope's settled + open),
so it has less headroom, not more.

## Frozen code relied on (unchanged)

- `skillopt/coevo5/calls.py:147-185`: `Endpoint.recorder` and `Endpoint.send`, which reserves (:161) before
  `client.call` (:177). The guard acts before `send`.
- `skillopt/coevo5/calls.py:261-279`: `Recorder`, whose resend waits `endpoint.sleep(endpoint.cooldown)` (:272;
  `RESEND_COOLDOWN_SECONDS` = 300, coevo5/protocol.py:88). `Metered.sleep` gates first.
- `skillopt/coevo5/ledger.py:30-37`: `attempt_bound` and `reservation` (4 bounds). `:51-75`: `settle`.
- `skillopt/coevo5/budget.py:59-64` (`rooted`), `:224` (`declare`), `:283` (`reserve`), `:344` (`snapshot`).
- `skillopt/coevo5/roles.py:92-142`: `Roles.ask`, `plain` and `count`.
- `skillopt/coevo5/leakage.py:73` (`ADJUDICATE_SYSTEM`), `:272` (`_verdict`), `:280` (`adjudicate`).
- `skillopt/coevo5/cells.py:45-49`: `STOP_KINDS` and `Pause`.
- `scripts/weak_solver_probe.py:77`: glm-5.3 response ids. `:286`: the client refuses another echo.

## Deviations

1. **The engineer reads the S4 run unit, not S2.** `engineer.Context` admits only run-unit trajectories
   (`engineer.py:59` `RUN_UNIT`, `:180-186`), and S2's units are labelled `smoke/S2/<set>`. S3 therefore needs the
   S4 run unit, which completes on S4's first call, before the drill. C7c's operator order already puts S3 after S4.
   The detector reads S2's SearchQA C arm, as asked.
2. **The 0.5M cap is a pre-call guard plus an accounting sub-scope, not a 0.5M ledger scope.** One 220 KB role
   request reserves 4 attempt bounds (~0.95M) by itself. The guard uses the single-attempt bound, so frozen-client
   retries inside one call can take the total past 0.5M. In that case row `glm_cap` fails and the next call is
   refused.
3. **New S3 row `glm_cap`.** CLI and smoke tests build the rows from `S3_ROWS`.
4. **`BUILT_STAGES` value unchanged** (ticket C7d-1).
5. **The research request is fixed by the registrar** (one `family_material`, concept "derivative" → family
   `livemath.derivative`). No examiner policy call chooses it, because the policy call is not among S3's registered
   calls. The generator call is the examiner's own.
6. **The adjudicated rule is fx-note's description** (registrar text), chosen to make the confirmation call small.
7. **The research leakage corpus is the smoke's LiveMath pool** (`setting.pools["livemath"]`, its 20 items), where
   a chain step would screen against the bench's training pool.
8. **Fake mode has its own backends.** `smoke._backends`' fake transport is elucid-only and fails on a glm-5.3
   request.

## Tests

`tests/test_execskill_smoke_roles.py` (8 tests) covers:
- `run_stage(..., "S3", fake=True)` end to end: all six rows true, the spend recorded and equal to the ledger
  sub-scope, the write-once record, `summary` reporting S3 "pass", and a read-back that sends nothing;
- piece order and outputs: leakage first; research query → pick → conclude before the generator; C1…C9; the
  detector validated deterministically; the archive page's digest; 6 checker truths == `TRUTHS`; every container
  drained;
- the first-reply gate (another model's echo, and an undelivered 400 whose resend is blocked): exactly 1 request;
- the 0.5M guard: the engineer's propose is refused, nothing is open, no halt;
- credentials refused in fake mode, the `roles_repo` money guard, and a missing credential in real mode;
- a piece that fails gives a false row (no detector written; research finds nothing → no generator call);
- **mutation:** the research request skipped, or its finding forged, pauses the unit `configuration` with
  `generation_without_research`; no generator call is made and no items are written;
- `WorkerChecker` through SympyDocker (a session uses one worker; outside a session each solve gets its own; faults)
  and through plain FakeDocker (no sympy, so `Drop reference_fn_failed`).

Counts: see "Test runs" below.

## Throwaway real checker run (dl, pinned image `sha256:0a0a5dcb…f0dd`, no network, no model)

Scratch `/tmp/c7d-checker-04LIxH`: `livemath.WorkerChecker` over the real `sandbox.client.Worker` and `Docker`,
tag `unit_tag("c7d", …)`, the registered limits, one generator-kind session. The worker ping reported sympy 1.13.3
and python 3.11.16. Total time 9.48 s (container start included), 7-97 ms CPU per solve. Results (exact | 50
digits; every one passes `livemath.solved`):

| template | exact | digits |
|---|---|---|
| derivative 3x²-2x+1, order 1, at 2 | 10 | 10.000000000000000000000000000000000000000000000000 |
| derivative 5x⁴-3x³+2x²-7x+1, order 2, at 0 | 4 | 4.0000000000000000000000000000000000000000000000000 |
| integral 3x²-2x+1 on [-1, 2] | 9 | 9.0000000000000000000000000000000000000000000000000 |
| integral 2x²-3x+1 on [-2, 1] | 27/2 | 13.500000000000000000000000000000000000000000000000 |
| integral x³-2 on [0, 3] | 57/4 | 14.250000000000000000000000000000000000000000000000 |
| binomial C(30, 15) | 155117520 | 155117520.00000000000000000000000000000000000000000 |
| geometric 3, ratio -1/2, 5 terms | 33/16 | 2.0625000000000000000000000000000000000000000000000 |
| geometric 7, ratio 2/3, 12 terms | 3691415/177147 | 20.838145720785562273140386232902617600072256374649 |

Afterwards `docker ps -a --filter name=execskill-sbx-c7d` listed 0 containers, and the scratch directory was
removed (`ls /tmp/c7d-*`: none).

## Test runs (dl, `/root/continual-alf-prep-20260928/env/bin/python -B -m pytest -q -p no:cacheprovider`)

- `tests/test_execskill_smoke_roles.py`: **8 passed** (41.2 s; the module fixture with S2 + S4 takes 29.2 s, and the
  end-to-end S3 `run_stage` takes 2.07 s).
- Targeted run with no code edited meanwhile: `test_execskill_smoke_roles.py`, `test_execskill_smoke.py`,
  `test_execskill_smoke_rehearsal.py`, `test_execskill_cli.py` and `test_execskill_generators.py` gave **75 passed**
  (150.9 s; 8 + 20 + 8 + 27 + 12). An earlier run showed 8 rehearsal errors ("Files differ from the launch manifest:
  smoke.py, smoke_roles.py"). I had edited code while it ran; the code-map check covers `skillopt/` and `scripts/`.
- Whole route-B suite `tests/test_execskill_*.py` (55 files), once: **1071 passed, 1 failed, 11 errors** (640.7 s).
  None of the 12 is in a C7d file, and all 12 come from PR-C31's run-root canary scan, which is in progress
  (`evaluation.py` changed at 12:55; `evaluation.unseal` → `_root_scanned` → "No registered test canaries in the run
  root"):
  - failed: `test_execskill_integration_b5.py::test_chains_g_and_d_read_once_then_unseal_and_read_out`;
  - errors: all 11 tests of `test_execskill_e2e.py` (the fixture stops at its unseal; rerun alone with the same
    error).

  PR-C31's own note gives the fixture patch (tickets/PR-C31-2.md). C7e's 13:12 run saw the same set.

## Tickets

- C7d-1: run S3 in the rehearsal, then add "S3" to `BUILT_STAGES` (rehearsal owner C7c/C7e).
- C7d-2: wire `WorkerChecker` into `step.Services` with the unit's tag and a session around `examiner.build`
  (integrator; closes C6-1's checker half).
- C7d-3: `smoke-run --fake` passes the default `--env-path`, so every fake stage is refused (CLI owner I1).

## Not done

- No real S3 run (paid; that is the operator's step).
- The rehearsal does not run S3 yet (C7d-1).
- The production Services checker is not wired (C7d-2).
