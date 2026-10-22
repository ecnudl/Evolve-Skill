# Integration B1 (foundations): rows A1-A4 wired together

Protocol `fivebench-execskill-v1`. Plan §5, §8.1 (T-ID-1, T-ID-2) and §9 (integration gates); registration §2.2-§2.4,
§3.4, §4.1, §4.4, §9.3 (where plan and registration disagree, the registration wins). Build tree `/data/execskill-dev`
(mounted on the Mac at `/Users/dulin/remote/dl`), HEAD `010d453` plus the untracked route-B files. Inputs: notes
A1-A4, tickets A2-1, A3-1, A4-1. Done 2026-10-21 23:30 CST. No model call, no credential file opened, no test-pool
data read, no git command that changes state, no `.pyc` written.

## Gate: PASS

- All B1 tests are green: 433/433 route-B tests (`tests/test_execskill_*.py`) and the two frozen files 90/90.
- The exception set is one set (T-ID-1). The five frozen classes come only from `skillopt.coevo5.outcomes`, the three
  route-B classes (`SandboxUnavailable`, `PackageInvalid`, `ConsumptionConflict`) only from `skillopt.execskill.errors`.
  Nothing in the route-B tree defines or imports another copy (checked statically and at run time), and every B1
  module that owns a stop raises it with a kind that the frozen exact-type lookup (cells.py:215-216) understands.
- One registration question stays open for the owner before S2 (ticket A3-1, the lexicon rule). It does not block B1.

## pytest (dl, Python 3.11.16, `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider`)

| File | Before integration | After |
|---|---|---|
| test_execskill_protocol.py (A1) | 17 | 17 |
| test_execskill_budgets.py (A1) | 8 | 8 |
| test_execskill_slots.py (A1) | 7 | 7 |
| test_execskill_client.py (A2) | 73 | 73 |
| test_execskill_package.py (A3) | 65 | 65 |
| test_execskill_policy.py (A3) | 118 | 118 |
| test_execskill_notes.py (A3) | 33 | 33 |
| test_execskill_compute.py (A3) | 60 | 60 |
| test_execskill_canonical.py (A3) | 21 | 21 |
| test_execskill_registry.py (A4) | 8 | 8 |
| test_execskill_supply.py (A4) | 10 | 10 |
| test_execskill_exclusion.py (A4) | 4 | 4 |
| test_execskill_integration_b1.py (integrator, new) | - | 9 |
| **route B** | **424** | **433** |
| test_coevo5_core.py (frozen) | 71 | 71 |
| test_weak_solver_probe.py (frozen) | 19 | 19 |
| **total (0 failed)** | **514** | **523** |

- The gate command (all route-B files plus the two frozen files) passed 523 in about 3.2 s in each of four runs.
- The whole frozen suite (`tests/test_coevo5_*.py` + `tests/test_weak_solver_probe.py`) passed 724 in 60 s. No frozen
  test imports `skillopt.execskill` or `tests/execskill_fakes.py`, so the edits below cannot change that result.
- A4's registry tests, which could not be collected in the build tree when A4 finished (no `errors.py` yet), now
  collect and pass there.
- `git status`: no tracked file is modified; no `__pycache__` or `.pyc` in the tree.

## What was checked across the rows

- Imports and names: every module of the package imports (the T-ID-1 walk imports each one), and every name one row
  imports from another exists with the meaning the importer assumes (A4-1's list, A2-1's names).
- Signatures: `budgets.endpoint(setting, scopes, *, client, max_tokens_bound)` with the clients of
  `client.solver_client` and the fakes; `slots.pools`; `Registry(root, *, evidence)`; `supply.supply_record`; the
  chain `notes.screen` -> `notes.check_bindings` -> `compute.evaluate_tags` -> `notes.render`/`assemble`.
- Record keys: every B1 writer (procedure, package, consumption line, supply record, exclusion record) seals through
  `protocol.record`: `version` = `fivebench-execskill-v1-<kind>`, `evidence`, `record_sha256` (T-ID-2).
- Exception classes: T-ID-1, above.

## Fixes (minimal; each in the file it touches)

1. **`skillopt/execskill/compute.py` (A3's row): the bindings hand-off from the notes.** `evaluate_tags` documents its
   bindings as "the checked ones (notes.check_bindings)", but `_names` ran `dict(bindings)`. Given the records that
   `check_bindings` keeps (`[{"name", "value", "quote"}]`), it escaped with a plain ValueError ("dictionary update
   sequence element #0 has length 3; 2 is required", reproduced on dl), so no `<calc>` tag of a real note could be
   evaluated. `_names` now also takes that list as it is. Each record must hold a str name and a value, each name
   once; otherwise ValueError (a wiring error, never a computation result). The mapping form is unchanged; A3's
   compute and notes tests are unchanged and green. The docstrings of `exact` and `evaluate_tags` name both forms.
2. **`skillopt/execskill/protocol.py` (A1's row): one lexicon hash.** Removed
   `LEXICON_SHA256 = digest({"terms": LEXICON, "match": LEXICON_MATCH})`. It was a second lexicon hash that differs
   from `notes.lexicon_sha256()`. The latter hashes what the screen actually applies (terms, matching rule, LiveMath
   meta-option terms, field types, headers, caps), and the manifest has one `lexicon_sha` (plan §2.9). Nothing used
   the removed constant. A comment in its place names the one hash. `PLACEBO_CORPUS_SHA256` and `TEMPLATES_SHA256`
   are unchanged.
3. **`tests/execskill_fakes.py` (A2's row): one source for chain D's QA settings (ticket A2-1).** `QA_MAX_TOKENS` and
   `QA_READ_TIMEOUT` were the literals `8192, 600`. They now read `protocol.ELUCID_MAX_TOKENS["officeqa"]` and
   `protocol.ELUCID_READ_TIMEOUT["officeqa"]` (same values).
4. **`skillopt/execskill/budgets.py` (A1's row): stale frozen line references** in the `endpoint` docstring:
   "budget.py:300, :195-203" became "budget.py:299, :198-201, :205-222" (the "Undeclared scopes" require, the guarded
   except, `_quarantine`). Docstring only.
5. **New `tests/test_execskill_integration_b1.py` (9 tests, the integrator's file).** Offline and deterministic: the
   real clients behind scripted gateways (`tests/execskill_fakes.py`), a simulated clock, ledgers under `tmp_path`.
   - `test_t_id_1_one_exception_set_across_the_route_b_tree`: an AST scan of `skillopt/execskill/**`,
     `tests/*execskill*.py` and `tests/fixtures/execskill/**` finds no class named after one of the eight stops except
     the three route-B classes in `errors.py`, and every import of a stop name (relative imports resolved) comes from
     `coevo5.outcomes` or `execskill.errors`. At run time every package module that exposes a stop name exposes
     `errors`' object, and `errors` re-exports the frozen objects themselves.
   - `test_t_id_1_each_owner_raises_a_stop_of_its_kind`: registry (a consumption conflict between two D units),
     package (an invalid procedure id), slots (`hold_short` on the per-call sandbox pool past two 600 s windows on a
     simulated clock), client (`solver_client` with an unregistered model: configuration), budgets (a step-scope cap
     of 1,000 through `budgets.endpoint`: BudgetStop before anything is sent), ledger (a completion above B:
     AssumptionBroken). For each, `errors.STOP_KINDS[type(e)]` (the frozen exact-type lookup) equals
     `errors.stop_kind(e)` and the expected kind.
   - `test_t_id_2_every_b1_writer_stamps_the_one_protocol`: a procedure, a package, a consumption line and a supply
     record each pass `protocol.verified(value, kind)`. (Exclusion records use the same `protocol.record`, and
     A4's exclusion test checks their version and evidence.)
   - `test_registered_names_agree_across_the_b1_modules`: hook names (package vs protocol), note fields and headers
     (notes vs protocol), registry namespaces = the chains plus the smoke, a slot pool for every solver and for the
     role model.
   - `test_both_chains_and_a_role_run_through_the_route_b_pools_and_one_ledger`: on `budgets.caps("recommended")`
     (it has ALFWorld): a chain D call (ALFWorld step, branch-E bound 2,048, inside the episode and live-sandbox
     holds), a chain G call (SpreadsheetBench, B 65,536) and an engineer role call (16,384). It asserts the pools held
     during each request (`[(episode, live, deepseek), (glm,), (glm,)]`), the max_tokens each request names, that
     each reservation equals the frozen `ledger.reservation(size, B)`, the reserved scopes, and the settled totals
     (D:solver 15, G:solver 15, D:glm 15, G:glm 0, overall 45), with no halt.
   - `test_a_model_call_while_holding_a_native_slot_is_refused_before_anything_is_sent`: ConfigurationError
     (`slot_lock_order`), no request, no send, no reservation; after the release the same endpoint sends.
   - `test_the_smoke_and_the_probe_keep_their_own_ledgers`: a smoke solver call and a smoke role call; a probe call
     that reserves `reservation(size, B_PROBE)` <= PROBE_CAP; a pilot scope set is refused on both ledgers
     (ConfigurationError, the ledger does not quarantine itself).
   - `test_checked_bindings_feed_the_exact_calculator_and_the_note`: `screen` -> `check_bindings` (a non-verbatim
     binding is dropped) -> `evaluate_tags(tags, checked)` (exact results; the dropped name fails as
     `computation_failed:name`); the mapping form gives the same results; duplicate records are refused;
     `render`/`assemble`.
   - `test_the_lexicon_has_one_hash_covering_the_registered_values`: `notes.lexicon_record()` embeds protocol's
     LEXICON, LEXICON_MATCH, NOTE_HEADERS and caps; `lexicon_sha256() == digest(record)`; protocol defines no other
     lexicon hash.

No test was weakened: no assertion in A1-A4's test files was changed (the only test-side edit is fix 3, the source of
two constants). No frozen file was edited.

## Break-the-code checks (a throwaway copy `/tmp/b1-mut` on dl, deleted afterwards)

Each mutation went into the copy, the integration file was run (it then held 8 of its 9 tests), and the copy was
restored.

| Mutation | Result |
|---|---|
| none (baseline) | 8 passed |
| M1: compute ignores binding records again (`dict(bindings)`) | 1 failed |
| M2: registry defines a local `ConsumptionConflict` | 2 failed |
| M3: a second lexicon hash put back in protocol | 1 failed |
| M4: `LOCK_ORDER` puts the model after native | 1 failed |
| M5: budgets builds the Endpoint with M instead of B | 2 failed |
| restored | 8 passed |

## Frozen code relied on (read-only, mirror at 010d453)

- `coevo5/outcomes.py:95-120`: the five stop classes.
- `coevo5/cells.py:45-46`: STOP_KINDS. `:215-216`: `except tuple(STOP_KINDS)` then `STOP_KINDS[type(exc)]`, an
  exact-type lookup: a subclass of a frozen stop would be caught and then fail with KeyError, so route B raises the
  frozen classes themselves. `:217-218`: any other error is kind "exception".
- `coevo5/units.py:149-150`: an isinstance lookup that maps any other ValueError to "configuration".
- `coevo5/calls.py:136-145` Endpoint; `:150-185` send, with `with self.slots.hold()` at :155 (the integration test
  shows the order check refuses before any reservation); `:198-221` `_record`.
- `coevo5/budget.py:38` OVERALL; `:59-64` rooted; `:121` `Budget(root, *, poll, sleep)`; `:198-201` and `:205-222`
  the quarantine; `:224` declare; `:299` the "Undeclared scopes" require.
- `coevo5/ledger.py:26-36` reservation = 4 x (request bytes + 512 + B); `:51-70` settle, with the breach above B at
  `:67`.
- `coevo5/data.py:169` `item_hash` (hashes the whole item dict); `:232` TestAccess.
- `scripts/weak_solver_probe.py:77` MODELS["glm-5.3"] (65,536 tokens); `:225-257` Client; `:259-266` body.
- `continual_eval/core.py:30-32` require (ValueError); `:40-42` digest; `:60-61` write_json.

## Tickets

- **A2-1 (A2 -> A1): resolved.** A1 registered `ELUCID_MAX_TOKENS` and `ELUCID_READ_TIMEOUT` (protocol.py:96-98) and
  `GLM_SOLVER_TOKENS`, `GLM_READ_TIMEOUT` (:92-93). `tests/test_execskill_protocol.py:120-122` asserts
  `set(SOLVERS) == set(client.CONFIG_KEYS)`, the `CHAINS` mapping and the echo set. `ELUCID_RESPONSE_MODEL_IDS` is
  defined only in `client.py`. The integrator made the fakes read their QA defaults from protocol (fix 3).
- **A4-1 (A4 -> A1): resolved.** `errors.ConsumptionConflict(RuntimeError)` exists (errors.py:34). Every protocol name
  A4 imports exists (the registry, supply and exclusion tests import them and pass in the build tree). `PURPOSES` is
  defined only in `registry.py:36`.
- **A3-1 (A3 -> A1): open; owner decision before S2.** Not decided here: plan §11 lists the lexicon among the
  implementation-time registrations implementers must not decide alone. After fix 2, a change of the rule moves only
  `notes.lexicon_sha256()` (the ticket's `protocol.LEXICON_SHA256` no longer exists). The ticket file is left as A3
  wrote it.

## Open (not closed in B1)

1. Ticket A3-1, the lexicon matching rule: inflections are missed ("answers", "rounded"), and ordinary words in
   verbatim quotes ("return", "units") count as faults toward J3's 2% cap. Options: (a) stems s|es|ed|d|ing; (b) do
   not screen verbatim-checked quotes and table cells; or confirm the rule as registered. Owner, before S2.
2. T-ID-1 in the copied cell loop (B3, A8): the copied `cells.py`/`units.py` must look stops up in
   `errors.STOP_KINDS`/`errors.stop_kind`, not in the frozen tables. With the frozen tables, PackageInvalid becomes
   "configuration" (units.py:149-150) or "exception" (cells.py:217-218), and SandboxUnavailable and
   ConsumptionConflict become "exception". The "BudgetStop in a copied cell" check of T-ID-1 is done for real there.
   Re-run the T-ID-1 scan once those files land (it scans the whole package).
3. T-ID-2 and the integration file: re-run as later batches add writers (sandbox, units, judge, smoke). The T-ID-2
   test names B1's writers explicitly and must be extended with each new record kind.
4. No B1 module raises `LedgerFailure` or `CleanupUnconfirmed`. CleanupUnconfirmed belongs to the B2 sandbox row;
   LedgerFailure stays the frozen ledger's.
5. C4's ban on "code answering by option position/letter pattern" cannot be detected statically in `policy.py`. It is
   left to the C4 checker's owner (A3's note).
6. A4's registrar items:
   - the pre-reset is at most 322 games (20 selection rooms x 5), not 422;
   - the 1,000 SearchQA reserve items are excluded by id only (no pinned input holds their questions);
   - there is no workbook fixture at the S0-measured p99 size until S0 `make-fixtures`;
   - `supply.alfworld_reset` has no unit test (it needs the real ALFWorld env; it runs in S0 `make-items`).
7. A1's implementation-time registrations, to be frozen by sha before S2 (plan §11): NOTE_HEADERS other than "facts",
   NOT_RECOMMENDED_PREFIX, REPAIR_FRAME, the lexicon (A3-1), and the run-root file paths. A1's design choices that
   the owner should see: every route-B scope set names the root `overall` (v3's meaning of OVERALL is not carried
   over); the describer and the leakage calls are charged to the engineer scope; the second-redo rule is enforced by
   count in recovery (the ledger enforces only tokens).
8. Cosmetic: ruff I001 (import formatting only) in budgets.py, package.py, slots.py, tests/test_execskill_package.py
   and tests/test_execskill_protocol.py. Not a mismatch; left to their rows.

## Notes for later batches

- `item_hash` (data.py:169) hashes the whole item dict: register and dispatch the same dict (the registry binds it).
- Build `slots.pools(protocol.SLOT_ROOT)` once per process and pass it as the setting's `slots`. Never call a model
  while holding a native slot: it is refused with ConfigurationError before any reservation.
- Pass the list that `notes.check_bindings` keeps straight to `compute.evaluate_tags`; no conversion is needed.
- `sandbox/policy.json` and `notes.lexicon_record()` are configuration hashed into the manifest, not records: they
  carry `version` but no `evidence`. A row that writes either as a record file goes through `protocol.record`.
- The smoke (A13) subclasses `ElucidClient` for the S1-e control probe. A different echo in S1-a is a v1.1 amendment.
