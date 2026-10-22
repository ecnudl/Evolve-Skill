# C6b (completion): today's registrar decisions in the protocol, the notes screen, the pre-check, the records, the supply and the rounds

Agent C6b, 2026-10-22. Build tree `/data/execskill-dev` (mount `/Users/dulin/remote/dl`). Protocol
`fivebench-execskill-v1`. Inputs: the C4 gate note and ledger, tickets A3-1, A9-3, A10-1, C1-1, C5-2, C5-3, C5-4, C5-5,
C3-2, fixer-9, notes C5, C3, C1, A10, A3, fixer, and `docs/handoff/execskill-registrar-decisions-20261022.md`.

How the work was done: no model call, no network call, no credential or `.env` opened, no test-pool data read, no git
state change, no frozen file edited, no file outside this row's list edited. Every file was written whole (temporary
file + rename) by a patch script that first checks each replacement site occurs exactly once. Tests run on dl with
`python -B`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`. Everything here is an engineering fixture on fakes,
not evidence of a method effect.

## Files written (only these)
- `skillopt/execskill/protocol.py`: A3-1 rule (`LEXICON_SUFFIXES`, `LEXICON_VERBATIM`, new `LEXICON_MATCH` text);
  A10-1 constants (`NOTE_HOOKS`, `TRACKER_AGREEMENT`, `STATE_FACTS`, `PROPERTY_KINDS`, `MUTATIONS`, `MAX_TESTS`,
  `MAX_PROPERTY_TEXT`, `MAX_FRAGMENTS`, `SHOWN_TAG`, `DEFAULT_TARGET`); C1-1 constants (`GENERATOR_CALLS`,
  `POLICY_CALLS`, `MAX_SPECS`, `EXAMINER_PROBE_TAG`, `MAX_RATIONALE`, `MAX_CONCEPT_CHARS`, `MAX_QUESTION_CHARS`);
  A9-3 `MDE_POINTS`; `EXCLUSION_DIR`. No existing value changed.
- `skillopt/execskill/notes.py`: inflections, the verbatim exemption, `Screened`, `lexicon_record` (+ `suffixes`,
  `verbatim`).
- `skillopt/execskill/solver.py`: screen with the item's public text; shell record `sandbox`; the record re-sealed
  after the worker closed; pre-check gets the worker's unit tag.
- `skillopt/execskill/precheck.py`: `container_name`, sandbox-form names, removal by `sandbox.cleanup` (bounded
  retries), `cleanup_seconds`; `run`/`precheck` take `tag=None, docker=None`.
- `skillopt/execskill/cells.py`: cell record `sandbox` (`_sandbox`), also in `share_cell`.
- `skillopt/execskill/exclusion.py`: `exclude_tests` records `supply_sha256`; `persisted(root, run)`;
  `apply_exclusion(supply, root, *, record_sha256=None)` returns a sealed `searchqa-kept` record (`KEPT_KIND`).
- `skillopt/execskill/supply.py`: `slices(..., *, kept=None)` refuses SearchQA tail items without the kept record.
- `skillopt/execskill/rounds.py`: `balance` removed (and its imports, the docstring bullet).
- Tests: `tests/test_execskill_notes.py`, `test_execskill_protocol.py`, `test_execskill_solver.py`,
  `test_execskill_cells.py`, `test_execskill_rounds.py`, `test_execskill_exclusion.py`.
- Tickets `C6b-1`, `C6b-2`, `C6b-3`, `C6b-4`; this note; `notes/C6b-progress.md`.
- Not changed (no change needed): `precheck_worker.py`, `sandbox/client.py`, `sandbox/worker.py`,
  `sandbox/policy.json` (its content and hash untouched), `test_execskill_supply.py`, `test_execskill_sandbox.py`.
  There is no separate pre-check test file: `precheck.py` is covered by `tests/test_execskill_solver.py` (T-SOLVER-5 and
  the new C5-2 tests), so the new tests went there.

## Public API changes
- `notes.screen(fields, *, bench, public_text=None) -> (Screened, dropped)`. `public_text` None screens every text
  (unchanged behaviour). With the item's public text, a table cell or a binding's `quote` found in it verbatim
  (case-sensitive substring, as `check_bindings` verifies quotes) is not screened.
- `notes.Screened(dict)`: the kept fields plus `.public_text`. `notes.render(fields, *, bench, header)` is unchanged in
  signature; it re-screens a `Screened` against its own public text, a plain dict against nothing.
- `notes._texts` became `_shape` (typed, capped) + `_screened` (which texts the lexicon reads); both private.
- `precheck.container_name(tag=None)`; `precheck.run(request, runtime, *, evidence, tag=None, docker=None)`;
  `precheck.precheck(program, workbook, answer_position, runtime, *, evidence, tag=None, docker=None)`; the report's
  `execution_costs` gains `cleanup_seconds`.
- Shell record (`fivebench-execskill-v1-shell`) gains `sandbox`: `{"restarts": [...], "cleanups": [...]}` copied from
  the worker after it closed, or None without a worker. `solver.solve` returns `{**prediction, "shell": <re-sealed>}`
  (the key keeps its place).
- Cell record gains `sandbox`: `{"restarts": [{..., "step"}], "cleanups": [{..., "step"}]}` over the cell's shell
  runs; empty lists for a shared cell or a cell without a worker.
- `exclusion.persisted(root, run)`; `exclusion.apply_exclusion(supply, root, *, record_sha256=None)` (was
  `(supply, value)`; its only caller was its own test); `exclusion.KEPT_KIND = "searchqa-kept"`; `exclude_tests`'s
  record gains `supply_sha256`.
- `supply.slices(bench, order_items, sizes, consumed=frozenset(), *, kept=None)`.
- `rounds.balance` removed.

## What each delivery does
1. **A3-1 (both options).**
   - (a) A term that starts and ends with a letter matches on word boundaries with an optional suffix `s|es|ed|d|ing`,
     its last letter optionally doubled before `ed`/`ing`, and a term ending in `s` also matches without the `s`
     (no suffix there). Substring terms (`<answer`, `<action`, three backticks) already matched every inflection.
   - (b) `screen(..., public_text=)`: verbatim table cells and binding quotes are skipped; facts, candidates, warnings,
     binding names and values, and any non-verbatim cell or quote are still screened.
   - Tests: every inflection of ticket A3-1 ("answers", "answered", "responds", "outputs", "returned", "returns",
     "rounded", "rounding", "formatted", "formats", "decimal place") plus "outputting", "single letters", "unit",
     "bared" on four benches, and SpreadsheetBench's `format` exemption; "Rounded to two places, in millions" is now
     dropped; "barely", "United States", "formation", "around"/"surrounding" still pass. Each of "Total return on
     investment", "in units of 1,000" and "round lots" passes as a verbatim table cell, and a verbatim binding quote
     passes, while the same words as facts, candidates or warnings are caught; a non-verbatim cell or rephrased quote
     and a lexicon binding name are caught; without the public text everything is screened; a plain copy of exempted
     fields is refused by `render`.
   - `test_matching_rule_is_the_registered_one` pinned the old rule ("The answers listed below" and "Returns of 1990"
     passing); both now count as hits, as the registrar decided. This is the registered rule changing, not a
     weakened test.
   - The lexicon's one hash is now `a007ee266909803d13b10bde9030bd20ada6d676060b4b71633d5a799793ff4b`, pinned as
     `LEXICON_SHA256` in `tests/test_execskill_notes.py` (see deviation 1).
2. **Constants (A10-1, C1-1, A9-3).** Moved by value (names as in the modules; the examiner's `PROBE_TAG` is
   `EXAMINER_PROBE_TAG`, as C1-1 asks). `test_moved_constants_equal_their_module_twins` asserts value and type
   equality of all 17 twins (including `package.NOTE_HOOKS`) and the calc T11 examiner bound (2 + 1 + 2 x 3 = 9).
   `test_registered_mde_points` pins `MDE_POINTS`. The import switches are ticket C6b-1.
3. **C5-2.** The pre-check container is `execskill-sbx-<chain>-<unit12>-<uuid4 hex>` when the cell's worker has a unit
   tag, else `execskill-sbx-<uuid4 hex>`: exactly the sandbox's registered forms (C5-3 item 4), so `client.NAME`
   accepts it, `client.drain_unit`/`drain_check` and the S2 `leftovers` row (prefix `execskill-sbx-`) list it, and its
   removal is `client.cleanup`'s 3 tries of `rm --force` + exact-name `ps`, 10 s each, 1 s apart (C5-3 item 5),
   `CleanupUnconfirmed` only after the last. The `docker run` argv stays the frozen one but the name. Tests (FakeDocker
   for the removal): the frozen-argv test now asserts the route-B name and one `rm`; a removal confirmed at the third
   try; a sticky one raising `CleanupUnconfirmed` after 3 tries, found by that unit's drain and the machine-wide check
   but not by the other chain's drain; the shell passes the worker's tag (and none without a tagged worker).
4. **C5-4.** `solver._Shell.sandbox()` copies `restarts` and `cleanups`; `solve` re-seals the shell record after
   `shell.close()`, so the final removal is in it. `cells._sandbox` gathers the events of every shell run with its
   step. Tests: a worker with one restart and a closing removal shows both in the shell record (verified seal) and in
   the cell record (steps `solve`), with no fault and a pass; no-worker cells carry None / empty lists; a shared cell
   empty lists.
5. **C3-2 item 1.** `apply_exclusion` reads the SearchQA record only from `<root>/shared/exclusion/
   searchqa_test_exclusion.json` and refuses: no file, a broken seal, a record of another supply (by the new
   `supply_sha256`, also for a same-size supply), a record other than the manifest's when `record_sha256` is given. It
   returns a sealed `searchqa-kept` record; `supply.slices` refuses any `part == "tail"` item without it or outside its
   kept items (so a dropped test item cannot be cut), and requires its seal. Pool items are unaffected.
6. **C5-5.** No caller of `rounds.balance` in `skillopt/`, `scripts/` or `tests/` besides `tests/test_execskill_rounds.py`
   (grep). Removed with its test; the round test's duration assertion now reads the cells' timestamps directly and
   asserts that `rounds` has no `balance`.

## Verified against frozen code (mirror at 010d453)
- `skillopt/continual_eval/backends.py:153` `_native`; `:158` its name `"continual-eval-" + uuid.uuid4().hex`;
  `:186-192` its single `rm --force` in `finally` and the `cleaned` check (what the pre-check replaced); `:169-178` the
  argv `precheck.native_command` copies (unchanged).
- `skillopt/continual_eval/core.py:30` `require`, `:35` `safe_path`, `:42` `read_json`, `:60` `write_json`;
  `skillopt/validator_pilot/api.py:40` `digest`, `:45` `write_immutable_json` (write-once).
- Route-B code read, not edited: `sandbox/client.py` (`PREFIX`, `TAG`, `NAME`, `unit_tag`, `cleanup`, `drain_check`,
  `drain_unit`, `Worker.restarts/cleanups/tag`, `_discard`), `replay.py:49-80` and `:604`, `engineer.py:52-57`, `:223`,
  `describer.py:26`, `:37`, `:75`, `examiner.py:67-81`, `:95`, `:360`, `:403`, `package.py:37`, `donors.py:161`,
  `placebo.py:86`, `step.py:194-196`, `:755`, `scripts/run_execskill.py:95`, `:184-268`, `prelaunch.py:110-115` (via
  C5-2), `tests/test_execskill_integration_b1.py:296-301`, `tests/test_execskill_mutations.py:25-45`.

## Deviations, with reasons
1. **No `protocol.LEXICON_SHA256`.** `tests/test_execskill_integration_b1.py:301` (not mine) asserts protocol carries
   no `LEXICON*SHA256` name: the lexicon has one hash, `notes.lexicon_sha256()`, which the manifest binds as
   `lexicon_sha`. The new value is pinned in `tests/test_execskill_notes.py` instead, so any later change to the screen
   fails that test. The record also carries the suffixes and the verbatim fields.
2. **Two registered inflections beyond the literal suffix list.** The decision names `s, es, ed, d, ing`; ticket A3-1's
   list, which the decision says (a) closes, includes "formatted" and "decimal place", which that list alone does not
   reach. So the last letter may be doubled before `ed`/`ing`, and a term ending in `s` also matches without it (with
   no suffix, so "units" never matches "united"). Both are written into `LEXICON_MATCH` and the hashed record; they only
   widen the screen. A line for the v1.1 note.
3. **`Screened` instead of a `public_text` keyword on `render`.** Mutation site 03 of
   `tests/test_execskill_mutations.py:34-37` pins the solver's `notes.render(...)` line verbatim, so that line could not
   change. `screen` returns a dict subclass that remembers the public text; `render` re-screens against it, so its
   guard stays complete and no `render` call site changes.
4. **Verbatim = case-sensitive substring of the joined public text**, the same test `check_bindings` already applies to
   a quote (`quote in public_text`). An empty cell is trivially verbatim (it holds no term).
5. **Shams stay fully screened.** The shell shows a sham with `public_text=None`; donors seal sham content with the
   default screen. So a donor's verbatim quote with a lexicon word is left out of its sham rather than faulting the
   placebo arm (ticket C6b-2).
6. **The kept-supply proof sits at `slices`, not `write_supply`.** `exclude-tests` reads the written tail supply as its
   input, so `write_supply` cannot require the exclusion record that is made from it. The tail can be cut only with
   the sealed `searchqa-kept` record that `apply_exclusion` makes from the persisted file.
7. **The pre-check uses the sandbox's names, not a separate `execskill-pre-` form.** One name form keeps one leftovers
   prefix and one drain; `prelaunch.py` needs no change.
8. **Fakes are duck-typed.** The shell reads `worker.tag/restarts/cleanups` with `getattr` defaults because the tests'
   `FakeSandbox` has none; the pre-check gets `tag=` only when the worker has one, because `FakeNative.precheck` (and
   the e2e's fake) do not accept it yet (ticket C6b-2).

9. **Residual (LiveMath, formal chain only).** On LiveMath the C4 meta-option terms belong to the lexicon, so a
   verbatim option text in a table cell or quote is not screened for them either (the decision exempts verbatim
   item text from screening). Such text is already in the solver's view; J7 still guards the options-only
   shortcut on the real batch. A line for the v1.1 note, or a narrower ruling.

## Tickets raised
- **C6b-1** (integrator/C6): the exact import switches in `replay.py`, `engineer.py`, `describer.py`, `examiner.py`;
  `step.py:755` `mde=None` → `protocol.MDE_POINTS[st.bench]`; the manifest binding of the engineer/describer (and
  examiner) prompt hashes; the new lexicon hash.
- **C6b-2** (integrator/C6, C7a): `notes.screen(public_text=)` call sites: `replay.py:310` must pass
  `public_text=reference`; `donors.py:161` and `placebo.py:86` keep the default; `FakeNative.precheck`
  (`tests/execskill_fakes_env.py`) and the e2e fake (`tests/test_execskill_e2e.py:214`) must accept `tag=None` before
  or with C5-1's tag wiring.
- **C6b-3** (integrator, C7b): SearchQA tail wiring (`apply_exclusion(tail, root, record_sha256=<manifest>)` and
  `slices(kept=)`), the CLI's `EXCLUSION_DIR` import, and where S2 reads the new `sandbox` fields.
- **C6b-4** (integrator/C6, owner of `tests/test_execskill_integration_b4.py`): the fixture
  `DESCRIPTION = "Before the question is answered, ..."` (b4:61, imported by `test_execskill_step.py:44` and
  `test_execskill_e2e.py:71`) now hits the term `answer` under A3-1 (a) ("answered" is on ticket A3-1's own list), so
  the describer drops it and three non-owned tests fail (below). Fix: the one word "answered" -> "solved"; no assertion
  changes.

## pytest (dl)
All runs on dl: `cd /data/execskill-dev && PYTHONDONTWRITEBYTECODE=1
/root/continual-alf-prep-20260928/env/bin/python -B -m pytest -q -p no:cacheprovider <files>`.
- `tests/test_execskill_notes.py tests/test_execskill_protocol.py`: `74 passed in 1.15s`
- `tests/test_execskill_solver.py tests/test_execskill_notes.py`: `85 passed in 1.53s`
- `tests/test_execskill_cells.py`: `12 passed in 0.55s`
- `tests/test_execskill_rounds.py`: `6 passed in 0.51s`
- `tests/test_execskill_exclusion.py tests/test_execskill_supply.py` with the CLI and registry tests:
  `41 passed in 2.33s`
- Final, this row's eight test files plus `tests/test_execskill_mutations.py` (after the whole-suite run):
  `202 passed in 53.12s`
- Whole route-B suite, once at the end (`tests/test_execskill_*.py`): `6 failed, 956 passed in 555.46s (0:09:15)`.
  - 3 failures in `tests/test_execskill_fixtures.py` (C7a's file, edited at the same time). Re-run once
    (fixtures + b4 + step): `2 failed, 18 passed in 54.12s`; every fixtures test passed, and the 2 failures are the
    b4 and step tests below. Not mine; reported, not fixed.
  - 3 failures from one cause, ticket C6b-4:
    `tests/test_execskill_integration_b4.py::test_b4_examiner_engineer_and_describer_on_real_run_slice_trajectories`,
    `tests/test_execskill_step.py::test_step1_one_fake_officeqa_step_through_the_eight_sub_steps`,
    `tests/test_execskill_e2e.py::test_both_chains_complete_the_pilot_and_accept_the_same_procedures`.
    On dl: `notes.lexicon_hits(DESCRIPTION, bench=b)` -> `['answer']` for each of the five benches;
    `describer.screened(DESCRIPTION, BENCHES)` -> `('', 1)`, and with "solved" the sentence is kept (0 dropped).
  - Check in a throwaway copy of the tree on dl (`/tmp/c6b-check`, removed afterwards), with only "answered" ->
    "solved" changed at b4:61; b4 + step + e2e + describer: `23 passed in 402.89s (0:06:42)`.
