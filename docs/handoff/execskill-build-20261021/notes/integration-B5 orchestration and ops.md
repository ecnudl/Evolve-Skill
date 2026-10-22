# Integration B5 (orchestration and ops): rows A12 and A13 wired together

Integrator B5, 2026-10-22. Rows A12 (`qualify.py`, `evaluation.py`, `readout.py`, `chain.py`) and A13 (`manifest.py`,
`prelaunch.py`, `smoke.py`, `scripts/run_execskill.py`, the mutation suite). The registration
(`execskill-registration-v1-20261021.md`) wins over the plan. No model call, no container start, no credential or
`.env` read, no test-pool data, no state-changing git command, no frozen file edited (`git status` shows no modified
tracked file). Everything here is an engineering fixture (`engineering_fixture`); nothing is evidence of a method
effect.

## Gate (iii): NOT PASSED as registered

Plan §9 gate (iii) asks for the plan §8.2 end-to-end test and the mutation suite (1)-(30) green in a fresh copy.

| Gate item | State |
|---|---|
| Plan §8.2 e2e test (`tests/test_execskill_e2e.py`: run → diagnose → research → generate → engineer → selftest → accept → decision → freeze → test read → unseal → readout, chains G and D) | **missing**. `step.py` (A12, ticket A12-2) and `examiner.py` (A11, B4 open item 1) do not exist, so no step can run. Not written here. |
| Mutation suite (1)-(30) | **28 of 30** covered and green: (1)-(20), (22)-(26), (28)-(30). Missing: (21) and (27). |
| Whole route-B suite in a fresh copy of the working tree | **green**: 915 passed. |
| `run_execskill.py --help`, `smoke-make --dry-run` | **pass** (below). |

What does pass in place of the e2e test: the new `tests/test_execskill_integration_b5.py`. It runs the real chain
runner for chains G and D. Each chain's steps are a stand-in that accepts two OfficeQA fixture procedures. The real
multi-arm read then runs on OfficeQA, followed by the unseal and the readout. See "Integration test" below. It is not
the plan §8.2 test and does not satisfy the gate.

## pytest (dl, `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider`)

- **Before the B5 edits** (dev tree `/data/execskill-dev`): `tests/test_execskill_*.py tests/test_weak_solver_probe.py
  tests/test_coevo5_core.py`: `900 passed in 113.73s`.
- **Fresh copy** (`rsync -a --exclude=.git --exclude=__pycache__ --exclude='.env*'` to `/data/execskill-clonecheck`),
  the same files: **`915 passed in 127.93s`**.
  - Frozen `test_weak_solver_probe.py` and `test_coevo5_core.py`: `90 passed in 0.58s`.
  - Route B: 825.
  - New since the builders' delivery: 12 mutations, 1 integration test, 1 evaluation test, 1 CLI test.
- Gate files in the copy: mutations, integration_b5, cli and evaluation give `44 passed in 30.23s`.
  - The mutation suite alone: 28 passed. The baseline is green, and each mutation makes its named test fail.
- No `.pyc` in the copy or in the dev tree afterwards.
- `python -B scripts/run_execskill.py --help` in the copy: exit 0, every subcommand listed.
- `smoke-make --dry-run` through `cli.main`, from a harness in `/tmp/b5-smoke-dry` (outside the tree):
  - Result: exit 0, `written: false`, 3 synthetic items per set, spec sha256 `ace9f6cd…`, nothing written.
  - The CLI has no flag for fakes, and `smoke.make` otherwise calls `manifest.environment()`, which runs
    `docker image inspect` plus one sandbox ping. The harness therefore replaces the environment probe with the
    fake that `tests/test_execskill_cli.py` uses.

## What I fixed (each edit minimal)

1. **`scripts/run_execskill.py`, delegated subcommands: signature mismatch.** `ENTRY` maps `run` to `chain.run` and
   `terminate` to `chain.terminate`. Both exist now, but they take a `units.Setting`, while the CLI passes the
   manifest dict. `run --manifest M --chain G` would have crashed with a `TypeError` (missing `learn`), and `terminate`
   with an `AttributeError` on `dict.root`. The documented behaviour is a `ConfigurationError` naming ticket A13-1.
   - `_delegated` now accepts only an entry whose first parameter is `manifest`. Any other entry gets that
     `ConfigurationError`, raised before the manifest is loaded.
   - A dict result is printed, so `continuation-check` shows its report.
   - The future adapters need names of their own (for example `chain.run_manifest`), because `chain.run` is the
     Setting runner. `ENTRY` then changes in one line.
2. **`scripts/run_execskill.py consent`: weaker than the read's rule.** The CLI checked only the key set and
   `by == "owner"`. A consent with `multi_arm_arms: ["F", "C"]` was reported "valid", and `evaluation.consent` would
   then refuse the read. The CLI now calls `evaluation.consent(root / "shared")`, a single source of truth (§8.1).
   - In `tests/test_execskill_cli.py::test_consent_validates_without_writing`, the expected message is now `consent`
     (it was `exactly`).
   - The test also gained the wrong-arms case (refused) and a fully valid consent with an exclusion consent (both
     valid). The test is stronger, not weaker.
3. **`evaluation.continuation_check(manifest, *, chain, clock=_now)`** (ticket A13-1/A12-1 item 4). It reports:
   - whether the chain has ended;
   - the owner's continuation decision;
   - the formal addendum;
   - the label an unseal would carry now, or the label it carried once `unsealed.json` exists.

   It reads no score and writes nothing. The case rule is factored out of `_marker` into `_case`, which both use, so
   the report and the unseal cannot disagree. Test:
   `tests/test_execskill_evaluation.py::test_continuation_check_reports_the_label_an_unseal_would_carry_and_reads_no_score`.
4. **Mutation suite `tests/test_execskill_mutations.py`: 16 → 28 mutations.** The added sites each occur exactly once,
   which the suite asserts:
   - (10) consent accepts extra keys → T-EVAL-1.
   - (16) v2 reads the JSON beside a usable tag → T-JUDGE-5.
   - (18) every close also runs the prefix-wide drain → T-SBX-13.
   - (19) the sealed evaluation cell keeps the raw reply → T-EVAL-2/4 (`test_eval2_…seals_hashes_only`).
   - (20) qualify stamps the v3 version → T-QUAL-1.
   - (22) the landmark view includes episodes that end by step 10, terminal observation included → T-TRAJ-1.
   - (23) a logical call stores the first transport send's receipt, which the replay then serves → T-CELLS-4.
   - (24) the IUT decides by the sign-flip p → T-STATS-4.
   - (26) the router plans a third twin per item → T-ROUTE-5.
   - (28) a family builds items without material → T-GEN-6.
   - (29) chains G and D share one consumption file → T-REG-6.
   - (30) `solver_client("glm-5.3")` adds a route → T-CLIENT-6.

   The A13 docstring's "(10) waits for evaluation.py" is now stale and has been replaced.
5. **New `tests/test_execskill_integration_b5.py`** (below).

No module of B1-B4 needed a change.

## Integration test (`tests/test_execskill_integration_b5.py`, 1 test)

The test drives one run root with chains G and D. These parts run for real:
- `chain.run`: the markers, `declare(budgets.caps())`, `read_budget` (the 1.3 × estimate rule), the memory lock and
  `test-read.json`.
- `evaluation.evaluate` on OfficeQA: the real cells, shell, judge, FakeSandbox procedures, `EvaluationStore`, the
  transient deletion and the canary scan.
- The owner's continuation file and the formal addendum, `evaluation.continuation_check`, `evaluation.unseal` and
  `readout.readout`.

The other four benches' read units are stand-in records, which `chain.evaluate` verifies. Their fixture panels would
need the test-side SpreadsheetBench qualification or the ALFWorld environment.

Checked:
- both chains complete;
- each unit names its chain, run and final package;
- both chains read the same items with the same F, C, P_F and T_F cells, and their fake solvers make the same number
  of calls;
- no raw reply text in any file;
- every non-owner JSON file is a `fivebench-execskill-v1-*` record carrying its evidence;
- the unseal label is `interim_read_addendum_before_unseal`, later reads are confirmatory, and `read_label` over both
  chains agrees;
- the readout is a `generalization` record whose Q1 has OfficeQA, and Q3 is None (no dissimilar bench read);
- both chains' scopes are declared in the ledger.

Two contracts surfaced (no code change):
- **`readout.readout(procedures=...)` takes `{procedure id: home bench}`.** `labels` iterates `.items()`, while `q2`
  and `format_withholding` iterate the keys. A list fails with an `AttributeError`. The `report` adapter must pass the
  final package's procedures with their home benches.
- **Twins differ between the chains.** `test_plan` draws them with `router.draw_twins(…, unit)`, where `unit` is
  `"<chain>/test/<bench>"`. The two chains withhold different seeded halves on the same items, while every other arm
  is identical. The registration fixes the same slice items for both chains (§21) and says nothing about twin halves.
  **Registrar/owner question:** should the twin seed drop the chain, so G and D withhold the same halves? It is a
  one-line change in `evaluation.test_plan` (pass `"test/<bench>"`), not made here.

## Tickets

- **A13-1 / A12-1 (CLI entry points): partly resolved.** The `continuation-check` entry works (edit 3). Each delegated
  entry must take the manifest first (edit 1). Still open:
  - `setting_of(manifest, chain)`;
  - the `run` / `terminate` manifest adapters (new names);
  - `step.run_unit_spec`;
  - `evaluation.run_unit_spec` (arms P_F from the sealed donor corpus, T_F per ticket A10-3);
  - `readout.report`.

  Until then, `run`, `terminate`, `step-unit`, `evaluate-unit` and `report` stop with a `ConfigurationError` naming
  A13-1, and no chain can be launched from the CLI.
- **A12-2 (step.py, T-STEP-1, e2e): open.** It is blocked by `examiner.py` and by the A9-3 acceptance wiring.
- **A11-1 (qualify signature): resolved by contract, unchanged.** `qualify.qualify` keeps the frozen signature plus
  `evidence`, and its record carries `qualified` and `scorings_per_item`, which T-QUAL-1 asserts. The generator binds
  it with `functools.partial(qualify.qualify, evidence=…)`, which is `step.py`'s duty.
- **Unchanged and still open:**
  - A5-2: the prefix-wide drain against two concurrent chains. Owner/registrar decision.
  - A9-2 request 2: the dispatch order. Owner.
  - A9-3: the MDE constant. Registrar.
  - A10-1: the protocol constants. A1/registrar.
  - A9-1: donor pre-check reports on SpreadsheetBench. Owner.

## Open (not done in B5)

1. `skillopt/execskill/step.py`, `tests/test_execskill_step.py` (T-STEP-1) and `tests/test_execskill_e2e.py`
   (plan §8.2). With `examiner.py`, they gate (iii).
2. Mutations (21) and (27):
   - (21): placebo content computed from acceptance items or after dispatch → T-PLACEBO-6;
   - (27): research sources accepting a non-frozen host or a changed archive file → T-RES-1.

   Both need a site chosen with the owners of `donors.py` and `research.py`. Out of time.
3. The CLI subcommands A13 did not build:
   - `probe`, `sandbox-selftest`, `import-texts`, `import-sheet-qualification`, `make-items`, `exclude-tests`,
     `make-fixtures`, `replay`;
   - the paid smoke dispatchers (S1 probes, S2/S-N1/S4 cells, S3 role calls, the S4 fault switch).
4. T-CHAINS-1's two-process race test and chain G's zero-call cost arithmetic (A12 "missing").
5. Detector retirement. The descriptive §8.1 readout splits: OfficeQA by answer status and bulletin-in-training;
   LiveMath with and without meta-options.
6. Owner decisions carried from A12/A13:
   - a gap between OfficeQA's two test blocks;
   - the S-N1 per-item noise anchor;
   - the D3/D14 exclusion pattern confirmed at S0;
   - the twin seed per chain (above).

## Files written or changed by B5

- `scripts/run_execskill.py`: `_delegated` (manifest-first guard, printed dict result) and `consent` (calls
  `evaluation.consent`); imports `inspect` and `evaluation`.
- `skillopt/execskill/evaluation.py`:
  - `continuation_check` and `_case`;
  - `_marker` now uses `_case`;
  - `CHAINS` imported, `__all__` extended.
- `tests/test_execskill_mutations.py`: 12 mutations added, docstring updated.
- `tests/test_execskill_cli.py`: the stronger consent test and
  `test_delegated_entries_take_the_manifest_and_print_their_report`.
- `tests/test_execskill_evaluation.py`: the continuation-check test.
- `tests/test_execskill_integration_b5.py`: new.
- This note.
