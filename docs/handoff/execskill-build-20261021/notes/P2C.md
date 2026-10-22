# P2C notes: pilot-readiness pieces of the registrar addendum 2026-10-22 14:10 (rows 7, 8, 9, 17)

Builder P2C, 2026-10-22 14:4x-16:xx, dev tree dl:/data/execskill-dev. No model or network call, no commit, no push.
Progress log: `P2C-progress.md`. Open tickets: `tickets/P2C-1.md`, `tickets/P2C-2.md`.

## What was built, and where

**Row 7, first-call confirmation** (`chain.first_call`, called by `chain.run`).

- `protocol.py`: `FIRST_CALL_SYSTEM` / `FIRST_CALL_USER` (the fixture prompt, 101 request bytes, no pool item),
  `FIRST_CALL_BENCH` = `ORDER[0]` (whose registered settings the call uses), `FIRST_CALL_CAP` = 1,100,000 (four full
  reservations at chain G's B = 65,536 = 1,058,384, rounded up to 0.1M), with a comment citing the addendum.
- `budgets.py`: `CONFIRM`, `first_call_scopes(c)` = (overall, `<c>:solver`, `<c>:confirm`), `first_call_caps(c)`;
  `caps()` (the manifest's) includes them. `chain_caps` does NOT: `smoke.se6_projection` requires every chain_caps
  solver scope to have maximum-schedule cells, and the confirmation has no schedule.
- `chain.py`: `first_call(setting, chain, *, before)`. After `chain.json` and the ledger declaration
  (`chain_caps` + `first_call_caps`), inside the runner lock and before step 1: one `Endpoint.send` through
  `setting.clients(model, FIRST_CALL_BENCH)` (chain G: frozen BigModel glm-5.3, M = B = 65,536; chain D: elucid with
  SpreadsheetBench's M and read timeout and the manifest's branch bound). Checks: `reply` (receipt `ok`), `model` (the
  echo in `FIRST_CALL_ECHO`: {glm-5.3} / `client.ELUCID_RESPONSE_MODEL_IDS`), `settled` (ledger charge > 0), `reasoning`
  (chain D only: `reasoning_tokens` in (None, 0) AND `reasoning_chars` == 0; a receipt without the elucid check fails).
  Pass: `confirm.json` (record `first-call`: model, echo, bench, M, B, scopes, request hash and bytes, reply hash,
  reserved, charged, usage, reasoning counts, finish reason, error type, attempts, seconds, checks; no reply text),
  written once and reused by every relaunch (no second call). Failure (any check, or any exception before or during the
  send, e.g. no slot pool or a `BudgetStop` on `<c>:confirm`): `confirm-failed-<n>.json` and
  `Pause("first_call_unconfirmed", ..., "<c>/confirm")` -> `run` returns paused, exit 3; no unit attempt is opened. A
  relaunch of a started chain checks the pins (`_verified`) before calling again; the first launch has just checked them.
- `step.cost_projection` skips `G:confirm` (spent before the first unit, no schedule). Without this it was listed in
  `cap-check-G.json` with a meaningless projection (the breach condition was unchanged).

**Row 8, test-read estimate** (`protocol.estimate_test_read`, `chain.read_estimate_record`, `run_execskill.py
test-read-estimate`, `chain.read_budget`).

- `protocol.py`: `FIRED_SHARES` (1 home, 7/10 similar, 1/2 other), `TEST_READ_ESTIMATE_ARMS` = 4, `fired_share(bench,
  pilot)` (home = the pilot's order; similar = a `SIMILAR_PAIRS` partner of a home bench), `estimate_test_read(per_cell,
  ratio, pilot)` = ceil(ratio x sum_b n_b (card_b + 4 f_b proc_b)) with Fractions and one ceiling; a procedure cell S-E6
  did not measure (`procedure_assumed` or no value) is 8/5 x card. Named without a `test_` prefix so pytest never
  collects it. At the §9.1 high anchors, ratio 1: 272,045,432 / 5 -> **54,409,087**. The fired shares reproduce
  `TEST_READ_CELLS` (procedure cells = 5 n f) for both pilots.
- `chain.read_estimate_record(smoke_root)`: the passed smoke's result (`smoke-result.json`: passed, S-E6 required and
  `pass`, same spec) and S-E6's stage record (`stages/SE6.json`: passed, `result.per_cell` of all five benches,
  `result.ratio`) -> sealed record `test-read-estimate` {smoke hashes, pilot, formula, inputs (ratio, per_cell, n,
  fired, arms, procedure factor), value, `test_read_estimate` {D, G}}.
- `scripts/run_execskill.py`: `test-read-estimate --smoke R --out F` (zero calls) writes F once (refuses an existing
  file) and prints {out, test_read_estimate, record_sha256}.
- `chain.read_budget`: chain G uses ceil(estimate x max(1, factor_G)), factor_G = per_cell / anchor_high of its latest
  `cap-check-G*.json` (`chain.latest_cap_check`: the highest contiguous `cap-check-G-<n>.json`, verified as this run's
  passed chain-G check with finite per_cell and a positive anchor; a missing or failed check refuses). Chain D is
  unchanged. Returns the gate {estimate, factor, cap_check {file, record_sha256}, used, need}, recorded in
  `test-read.json` (`gate`).

**Row 9, chain-level consent check** (`chain.read_consent`, called by `chain.run` before `read_budget`/`evaluate`).
`evaluation.consent(setting.shared)` fails -> `read-waiting.json` (record `read-waiting`: identity, kind
`consent_missing`, read_units 5, read_attempts, units_complete; immutable, so a relaunch rewrites it only with the same
content) and `Pause("consent_missing", ..., "<c>/test")` -> exit 3, no read attempt. The per-child check in
`evaluation.run_unit_spec` is kept.

**Row 17, `recover` refuses a finished acceptance round** (`acceptance.finished_round`, called by `recover` before
`evaluation.release_check`). Finished = the attempt is `attempt-N` of a unit with `sealed.json` (the accept unit's root,
as `step._accept` writes it), every block of `schedule(sealed)` is reused by `earlier_blocks(..., attempt-(N+1))`, and
the attempt's `status.json` kind is `acceptance_undetermined`, or its `decision/decision.json` says `undetermined`, or
its `diagnostics.log` holds a `decide` frame of `skillopt/execskill/acceptance.py` (`DECIDE_FRAME`). Message: "A
finished acceptance round is final (<why>; registrar decision C7e-2): no recovery.json is written, report the pause to
the owner".

## Tests (dl, `PYTHONDONTWRITEBYTECODE=1 ... -m pytest -q -p no:cacheprovider`)

- `tests/test_execskill_chain.py` (+20, helpers changed: every Setting gets fake first-call solvers and the consent;
  the fake step writes chain G's passed cost check): row 7 pass + reuse + nothing sent beside it + fixture prompt +
  ledger; 8 failure modes through the real clients (http_400, transport, 503 x4, another echo, empty, truncated,
  reasoning, zero settled) with a relaunch that confirms; no slot pool and `BudgetStop` on `<c>:confirm`; the pin check
  before a relaunch's call; 5 stub-client cases for the model and reasoning checks alone; row 8 gate (factor 1.5, factor
  below 1, factor 2 pausing G while D reads, latest check, missing/failed check refused); row 9 (no read attempt in the
  five units, read-waiting counts, identical rewrite, changed counts refused, invalid consent, then the read). 29 passed.
- `tests/test_execskill_protocol.py` (+13): the exact 54,409,087, measured vs assumed procedure, ratio scaling, both
  pilots, fired shares vs `TEST_READ_CELLS`, 10 refusals, the first-call constants. 33 passed.
- `tests/test_execskill_acceptance.py` (+2) and `tests/test_execskill_cli.py` (+2: `test-read-estimate` written once,
  refusals of a failed smoke, a failed S3 and a partial S-E6; `recover` refusing a finished round and recovering a round
  paused inside a block).
- Updated for the confirmation: `tests/execskill_fakes.py` (`first_call_solvers`, `with_first_call`),
  `tests/test_execskill_integration_b5.py`, `tests/test_execskill_e2e.py` (the fake solver answers the fixture prompt;
  asserts `confirm.json` and the read gate), `tests/test_execskill_step.py` (cost projection skips `G:confirm`).
- `tests/test_execskill_mutations.py`: entries 37-55 (19), one per new guard; each named test passes unmutated and
  fails mutated (19 passed, 35 s).

## Left open

- Ticket P2C-1: `step-unit` (`step.run_unit_spec`) runs a step without the confirmation (the runbook never launches a
  chain that way).
- Ticket P2C-2: the read gate is re-applied on every relaunch, also after part of the read was spent (pre-existing).
- Minor, pre-existing, not ticketed: `read_budget`'s need is floor(1.3 x used) (at most 1 token below 1.3 x used).
- The confirmations' spend (at most the 1.1M cap) comes out of `<c>:solver` (180M, registered sum 175.1M) and
  `overall`; S-E6 and the cost projection do not count it.
- `pilot-runbook.md` updated: rows 7, 8, 9, 17 closed (5.3 kept as the fallback), 3.1-3.5 (the `test-read-estimate`
  command before the pins and `make-manifest`, the gate, the `<c>:confirm` cap), 5.2-5.3, 6.1-6.3, 7.1-7.2.
