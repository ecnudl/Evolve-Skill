# rp-core report: pure core of T/readplan.py (typed-v2 economy read plan)

Worker id: rp-core, then rp-core-fix for the review (section "Review fixes"). Worktree:
<repo-root> (branch typed-v2-readplan-core, base 8375ecb). 2026-11-12. Nothing
committed; the main tree was not touched. Design read from the main tree: DECISIONS-ADDENDUM-20261112.md (D9, D10,
D12, D16, D17, RP1 to RP12) and spec/read-plan.md (all sections; 0, 1.B, 1.C, 3, 4, 6 closely).

## Review fixes

Review: RPCORE-REVIEW.md (rp-core-review). Each finding was reproduced first, then fixed with a test that fails
before and passes after (evidence under "Tests", "Review-fix evidence").

- F1 (fixed, both parts): `item_components` now takes a required `arm=` (the integrator passes `arm_of(event)`), refuses an arm other than C0, C or F with `identity_exception`, and raises `identity_disagreement` unless the capture-mounted record's `arm` equals it; optional part also done: `event_entry` takes a required `read_mount={step, library_file_sha256, typemap_file_sha256}` (the frozen state actually loaded), and `identities_record(..., frozen=)` turns an entry computed from another state than the plan's `frozen[event]` into a fallback `identity_disagreement`, which `verify_identities` / `build_plan` re-check; reproduced first with probe p5 (officeqa one class, fresh 5) and a new probe p7 (S2 computed from s3 joins S5's class, R41 would pass); tests `test_a_record_mounted_through_another_arm_never_gives_the_event_an_identity`, `test_identities_computed_from_another_frozen_state_never_alias`.
- F2 (fixed): `record_from_bytes` now compares canonical bytes inside the `try`, and it and every verify function catch the new tuple `UNREADABLE` (ValueError, TypeError, KeyError, AttributeError, RecursionError), so an out-of-range number, a lone surrogate or deep nesting gives the reader's fixed code (`plan_file_mismatch`, `inputs_mismatch`, `sealed_file_mismatch`, `read_alias_invalid`, `plan_self_check`); all 3 x 3 byte cases and the 4 verify cases were raw exceptions before; test `test_unreadable_bytes_and_records_raise_the_fixed_code`.
- F3 (fixed, tests only, as the review said): one test per gap, `test_post_read_check_compares_the_planned_first_request` (M1), `test_offered_ids_must_agree_between_the_identity_and_the_mount_record` (M4), `test_components_must_carry_the_stored_view_hashes` (M6), `test_identities_are_bound_to_their_inputs_record` (M7), `test_a_stored_ok_entry_that_breaks_RP3_is_a_fallback` (M10), `test_alfworld_stored_views_are_bound_to_their_view_hashes` (M19), `test_frozen_entries_must_name_the_step_of_their_event` (M20), `test_two_items_that_swap_system_texts_give_other_lists` (T8 a); each one fails under its mutation, which all 44 earlier tests let pass; no module change was needed.
- F4 (fixed): `ReadPlanError` keeps `args = (code, detail)` with the message built in `__str__` (new attribute `.detail`), so pickle, deepcopy and copy rebuild it; the same defect in `WriteOnceMismatch` and `OpenRecordViolation` (they unpickled, but with a doubled or character-split message) is fixed the same way; test `test_errors_survive_pickle_and_copy`.

## Plan (checklist)

- [x] 1. Read DECISIONS-ADDENDUM (D9, D10, D12, D16, D17, RP1..RP12) and spec/read-plan.md (sections 0, 1.B, 1.C, 3, 4, 6; 8/9 history)
- [x] 2. Read the stable helpers at 8375ecb (units.write_json/read_json/checked_path, digest helpers) and mount_identity's output shape
- [x] 3. Write T/readplan.py: identity records + hashing + versions (R8..R15)
- [x] 4. Classes, representatives, both base_card values, ZebraLogic, first-request condition, fallback classes (R28..R31, R81, R91, RP3)
- [x] 5. Plan document: build, canonical bytes, self-hash, write_once, load, verify, sealed inputs schema (R32, R78, R80), replay comparison (R47 core)
- [x] 6. Alias records: build + verify (R39, RP3 counts)
- [x] 7. Forbidden-word check for open records
- [x] 8. tests/test_typed_readplan_core.py covering the required cases
- [x] 9. Run tests on Python 3.13 (and on 3.10 as a lower bound, since this Mac has no 3.11)
- [x] 10. Final report sections

## Done

Files (only these three were written):
- `skillopt/execskill/typed/readplan.py` (new, 1,410 lines after the review fixes; long docstrings and input checks).
  Imports only `T/__init__` (CHAINS, ORDER, READ_ARMS), `T/library` (`canonical_sha256`, `sha256_text`) and
  `T/units` (`checked_path`). No mount, chain, reads, writers; no model call, panel, chain state or subprocess.
- `tests/test_typed_readplan_core.py` (new, 56 tests after the review fixes; 44 before).
- this report.

What the module does:
- Per item (R9, R16, RP8, RP9). `item_components` takes the `mount_identity` output
  `{system_card_sha256, programs_offered: [[skill_id, sha256], ...], forced}`, the capture-mounted `mount.mount`
  record, the event's arm (`arm=arm_of(event)`) and `public_sha256` / `view_sha256`. It runs R16's self-check: the
  record was mounted with that arm, same system hash and same offered ids, and a selection request exists exactly
  when programs are offered. Otherwise it raises `identity_disagreement`. A malformed input, an arm other than C0,
  C or F, or a non-null `forced` raises `identity_exception`. `item_identity` is R9's hash. Type id, source,
  unknown reason, card skill and offered ids are stored next to the identity but are not hashed. `item_record` adds
  the first-request hash.
- Capture (R17, R19). `capture_selector` returns a fixed non-ok receipt. `CaptureCall` hashes
  sha256(system NUL user) for the first send only, charges 0 tokens and never reports an infrastructure unknown.
  `first_request()` returns the hash only when exactly one send happened.
- Per (event, bench). `event_entry` builds the sealed entry. The rules: status `ok`, or `fallback` with a reason
  from R31; RP3's first-request rule (`capture_failed`); R30's second embedder run (`embedder_unstable`, plus a
  count of descriptive flips). It also stores the frozen state the records were computed from (`read_mount`:
  step and the library and type map file hashes), which `identities_record` binds to the plan's `frozen[event]`.
- Lists and classes (R28, R29, R31, R91). The two list hashes follow R28. `compute_classes` applies the
  all-items rule and the first-request condition. Every fallback is its own class, and the representative is the
  latest event. A missing or unreadable summary becomes a fallback `identity_exception`. `first_sweep` gives the
  R36 read order. Both `base_card` values and ZebraLogic are handled by the same rule, because the system text
  carries the difference.
- Sealed records (R78, 3.3). `inputs_record` holds the sorted ids, view hashes, the ALFWorld views, two vector runs
  or null, `views_sha256`, `vectors_sha256` and a self-hash. `identities_record` takes the seven entries and the
  plan header's `frozen`. On the way it turns an inconsistent entry into a fallback `identity_exception` and an
  entry computed from another frozen state into a fallback `identity_disagreement`, applies the smoke probe and
  applies R29 (so every stored status is final), then self-hashes. Verify and load functions sit beside both
  (`verify_identities` binds to the inputs record and, when given, to `frozen`), plus `check_views`
  (`view_mismatch`). Every reader maps unreadable or too deeply nested data to its fixed code (`UNREADABLE`).
- The open plan (3.2, R32). `build_plan` and `plan_files` write all the 3.2 keys. They include `frozen` per event,
  `registry_sha256` (null exactly in a smoke), `run_constants_sha256`, the file hashes of the sealed files,
  `embed`, the per-event panel counts, the classes, `read_order` and `counts`. The plan is self-hashed
  (`plan_sha256`) and checked by the open-record check against every item id.
- Reading a plan back. `verify_plan` rebuilds the classes, read order and counts from the event rows.
  `plan_from_bytes` / `load_plan` accept a file only if: the bytes hash to the bound value, the bytes are exactly
  canonical, the self-hash is valid, and the hash is the bound `plan_sha256`.
- `write_once` (R80). It writes a temporary `.<name>.<pid>.<16 hex>.part`, fsyncs, links it to the final name,
  unlinks the temporary file and fsyncs the directory. Equal bytes are accepted; different bytes raise
  `WriteOnceMismatch`. `record_names` returns only the closed names, and `remove_part_files` cleans up after a kill.
- Replay (R47 core). `replay_compare(stored bytes, recomputed records)` returns `equal` / `different` with counts,
  and reason `replay_different`.
- Alias records (3.4, R39, R41, RP3). `build_alias` refuses a representative, a fallback pair or a failed check. It
  stores both list hashes, the plan hash, the check counts, the representative's aggregate hash and its
  unknown / infrastructure / configuration counts. `verify_alias` rebuilds the record from the plan and can also
  compare it with the mirror's aggregate and counts. `load_alias` also checks that the file name matches the
  (event, bench) inside. Helpers: `alias_state_entry`, `members_of`, `alias_pairs`, `class_of`,
  `frozen_entry_matches`, and for R41 `expected_for_check`, `observed_from_row`, `post_read_check`,
  `check_passed`.
- Open records (R81, 3.8, T23). `open_record_violations` / `check_open_record` report fixed codes and never quote
  content. They flag: a key naming test content, an item id (equal to a value, or inside one), a planted text, a
  string over 64 characters, any float, a reason outside `READ_PLAN_REASONS`, and a verdict outside
  `equal` / `different` / `error`.

## Tests

Command (as given):

    mkdir -p /tmp/typed2-rpcore && cd <repo-root> && TMPDIR=/tmp/typed2-rpcore <python> -m pytest -q -p no:cacheprovider tests/test_typed_readplan_core.py

Last line after the review fixes (Python 3.13.12): `56 passed in 5.53s` (before the fixes: `44 passed in 5.21s`).
Same file under Python 3.10.20 (`<python>`): `56 passed in 10.58s`. This
Mac has no 3.11; 3.10 and 3.13 bracket it, and both parse the files.

Review-fix evidence (scratch only, under /tmp/typed2-rpcore; the pre-fix module and tests are kept in
/tmp/typed2-rpcore/fixbase):
- Before the fixes (probes run on the pre-fix code): p5, C0 mounted through the S1 path, gives officeqa the single
  class {C0, C, S1..S5} > S5 (fresh 5, alias 30); p7 (/tmp/typed2-rpcore/fixprobe/p7_offbyone.py), S2 computed from
  the s3 state, gives officeqa {S2, S3, S4, S5} > S5 with S2 showing `with_card: 3`; p8
  (/tmp/typed2-rpcore/fixprobe/p8_cases.py) shows every F2 case raw (ValueError, UnicodeEncodeError,
  RecursionError for plan, alias and inputs bytes; RecursionError in verify_plan, verify_alias, verify_inputs,
  verify_identities) and ReadPlanError with a detail failing pickle and deepcopy.
- After: p5 gives {C0} alone as fallback `identity_disagreement` (fresh 10, fallback 5); p8 gives the fixed code
  for every case and equal messages after every round trip; the reviewer's p1 and p3 give only ReadPlanError and
  successful round trips.
- The F2 and F4 tests run against the pre-fix module (loaded by a scratch plugin) fail with the review's raw errors
  (`ValueError: Out of range float values`, `ValueError: Unregistered read-plan code`). The other new tests use the
  new `arm=` / `read_mount=` interfaces, so they cannot run there; for those, the mutation runs below stand in for
  the "before".
- Mutation runs (scratch plugin /tmp/typed2-rpcore/fixmut/rpmut.py, chosen by a pytest option, one rule removed per
  run, all 56 tests each time): A1 no arm check, A2 no frozen binding, M1, M4, M6, M7, M10, M19, M20 (the review's
  seven) and T8a (list hash over sorted identities). Every run fails, each by the new test written for it; M7 also
  fails the M6 test (whose stored-record half needs the inputs binding), and T8a also fails the hash-seed test
  (its child interpreters run unmutated code). Without a mutation, 56 pass.

Covered: every case in the task list.
- Identical events form one class, with the latest event as representative.
- Each of these splits the class: card text, selection request, offered programs (same name, other body), view,
  public part.
- A type-id-only difference does not split, and descriptive flips are counted.
- Both base values (R91 a, b): under 'historical', card-less and unknown items get C's identity; under 'format',
  C0's.
- ZebraLogic: C equals C0.
- Card learned at step k = 1, 2, 3 under both bases.
- The first-request condition, including that ALFWorld has no capture.
- Missing, unreadable, raising and disagreeing identities, each becoming its own fallback class; a record mounted
  through another arm and identities computed from another frozen state (review F1).
- `capture_failed` for 0 or 2 sends; `embedder_unstable`; the smoke probe (and its refusal on a real root).
- The T8 collision cases.
- Every byte of a 22.7 KB plan tampered, one at a time: all 22,728 changes detected, with and without the bound file
  hash.
- `verify_plan` recomputing classes, order and counts.
- `write_once` (identical accepted, different refused, `.part` files ignored and removed, sealed name needs
  `allow_sealed`).
- Sealed files round trip and detect changes; `view_mismatch`.
- Replay: `equal` on equal inputs, and `different` on each of 12 input changes (base card, manifest hash, solver
  settings hash, frozen receipts, bench order, a view, a public part, a vector, a learned card, a first request, the
  probe, the item set).
- The same bytes in two child interpreters with `PYTHONHASHSEED` 1 and 2. They get a minimal explicit environment;
  nothing is read from the parent's.
- Alias: build, verify, state entry; refused for a wrong representative, a wrong unit name, a wrong plan hash, an
  unresealed edit, another plan, a changed mirror aggregate or counts, or a record stored under another pair's name.
- R41 counts, including the planned first request (a differing or missing one is unequal).
- The bindings the review found untested (F3): offered ids, stored view hashes, inputs record, RP3 on stored ok
  entries, ALFWorld views, frozen steps, T8 (a).
- Unreadable bytes and too deeply nested records give the fixed codes; the error classes survive pickle and copy.
- Open records: every string in the plan and in an alias record is a hash or a closed word, there is no float, and
  the bytes contain none of the planted ids or texts.
- Unit names and arms equal `reads.unit_name` / `reads.arm_of`; open names hold no `FORBIDDEN_PATH_WORDS`.

Mutation check (scratch script; it puts the module back byte for byte afterwards): 16 rules were broken one at a
time and 15 runs failed. The one that passed removes the explicit plan-hash check in `verify_alias`; the rebuilt
record comparison still catches a wrong plan hash, so that check is redundant defence and behaviour does not change.

## Interfaces for the integrator

All in `skillopt.execskill.typed.readplan`. Names follow the spec where it gives one (`write_once`,
`READ_PLAN_REASONS`, `capture_selector`, `IDENTITY_VERSION`, the record keys of section 3); the rest are mine.

Constants: `IDENTITY_VERSION = 'typed-v2-mount-identity-1'`, `PLAN_VERSION = 'typed-v2-read-plan-1'`,
`ALIAS_VERSION = 'typed-v2-read-alias-1'`, `INPUTS_VERSION`, `IDENTITIES_VERSION`, `EVENTS`, `S_EVENTS`, `PAIRS` (35),
`FIRST_REQUEST_BENCHES`, `BASE_CARDS`, `STATUSES`, `READ_PLAN_REASONS`, and its parts `PASS_FALLBACK_REASONS`,
`FALLBACK_REASONS`, `PASS_FAILURE_CODES`, `VOID_REASONS`, `REPLAY_CODES`, `PAUSE_REASONS`, `RECOVERY_OUTCOMES`;
`REPLAY_VERDICTS`; names `PLAN_UNIT = 'read-plan'`, `PLAN_FILE`, `SEALED_DIR = 'test-read-plan'`,
`SMOKE_SEALED_DIR = 'practice-read-plan'`, `ALIAS_DIR`, `ARCHIVE_DIR`, `PART_NAME`; key tuples `PLAN_KEYS`,
`BENCH_KEYS`, `EVENT_KEYS`, `CLASS_KEYS`, `ALIAS_KEYS`, `FROZEN_KEYS`, `INPUTS_KEYS`, `IDENTITIES_KEYS`, `COUNT_KEYS`,
`CHECK_KEYS`, `ENTRY_KEYS` (now with `library_file_sha256`, `typemap_file_sha256`), `READ_MOUNT_KEYS = ('step',
'library_file_sha256', 'typemap_file_sha256')`; `READ_MOUNT_ARMS = ('C0', 'C', 'F')`; `UNREADABLE` (the exceptions
every reader maps to its fixed code).

Errors: `ReadPlanError(code, detail='')` (a ValueError; `.code` is in READ_PLAN_REASONS, `.detail` a closed word;
`args == (code, detail)`, so it pickles), `WriteOnceMismatch(name)`, `OpenRecordViolation(codes)`.

Names and paths:
- `arm_of(event)`, `step_of(event)`, `read_unit_name(event, bench, *, smoke)`
- `inputs_name(bench)`, `identities_name(bench)`, `alias_name(event, bench)`, `record_kind(name)`
- `plan_path(root, chain)`, `sealed_dir(root, chain, *, smoke)`, `inputs_path(root, chain, bench, *, smoke)`,
  `identities_path(root, chain, bench, *, smoke)`, `alias_path(root, chain, event, bench)`,
  `archived_alias_path(root, chain, event, bench, number)`
- `record_names(directory, *, allow_sealed=False)`, `remove_part_files(directory, *, allow_sealed=False)`

Bytes and files:
- `canonical_text(value)`, `canonical_bytes(value)`, `bytes_sha256(data)`, `file_sha256(record)`
- `record_from_bytes(data, *, code)`, `read_bytes(path, *, allow_sealed=False)`
- `write_once(path, record, *, allow_sealed=False) -> sha256 of the stored bytes`

Hashes of R10:
- `public_sha256(public)`, `view_sha256(view)`, `item_set_sha256(bench, item_ids)`
- `run_constants_sha256(bench, *, runtime, worker_options, nominal_tokens, machinery)`
- `registry_sha256(entry)` (drops `run`)

Capture:
- `capture_selector(system, user)`
- `class CaptureCall`: `__call__(system, user)`, `sends`, `tokens()`, `infrastructure_unknown()`, `first_request()`

Identity:
- `selection_sha256(mounted)`
- `item_components(identity, mounted, *, arm, public_sha256, view_sha256)` (`arm`: `arm_of(event)`; changed by F1)
- `item_identity(bench, components)`, `first_request_required(bench, components)`
- `item_record(bench, components, *, first_request=None)`
- `identity_list_sha256(bench, item_ids, identities)`, `first_request_list_sha256(bench, item_ids, first_requests)`

Events and classes:
- `event_entry(bench, event, item_ids, records, *, read_mount, second=None, reason=None)` (`read_mount`: the
  `{step, library_file_sha256, typemap_file_sha256}` of the frozen state loaded for the event; changed by F1)
- `entry_mounted_from(entry, frozen_entry) -> bool` (an entry against the plan's `frozen[event]`)
- `event_summary(bench, item_ids, entry)`
- `compute_classes(bench, summaries) -> (final, classes)`, `first_sweep(order, classes_by_bench)`

Sealed records:
- `inputs_record(chain, bench, item_ids, view_hashes, *, alfworld_views=None, vectors=None)`
- `verify_inputs(record, *, chain=None, bench=None)`, `check_views(inputs, recomputed)`
- `identities_record(chain, bench, inputs, entries, *, frozen, probe=None)` (`frozen`: the plan header's frozen
  entries; changed by F1)
- `verify_identities(record, *, inputs=None, frozen=None, chain=None, bench=None)`
- `sealed_from_bytes(data, kind, *, file_sha256=None, inputs=None, frozen=None)`,
  `load_sealed(path, kind, *, file_sha256=None, inputs=None, frozen=None)` (kind: 'inputs' or 'identities')

Plan:
- `build_plan(*, chain, smoke, schedule, read_plan, base_card, manifest_record_sha256, solver_settings_sha256,
  order, frozen, benches)`. `benches[b]` = {inputs, identities, registry_sha256, run_constants_sha256}.
- `plan_files(*, <same header>, benches, probe=None) -> {closed name: record}`.
  `benches[b]` = {inputs, entries, registry_sha256, run_constants_sha256}.
- `verify_plan(plan, *, plan_sha256=None)`, `plan_from_bytes(data, *, file_sha256=None, plan_sha256=None)`,
  `load_plan(path, *, file_sha256=None, plan_sha256=None)`
- `replay_compare(stored, recomputed)`
- `frozen_entry_matches(plan, event, *, step, library_file_sha256, typemap_file_sha256)`

Classes of a plan and alias records:
- `class_of(plan, event, bench)`, `members_of(plan, bench, representative)`, `alias_pairs(plan)`
- `expected_for_check(identities, event)`, `observed_from_row(row, program_sha256_of)`,
  `post_read_check(expected, observed)`, `check_passed(check, items)`
- `build_alias(plan, event, bench, *, check, representative_aggregate_sha256, representative_counts)`
- `verify_alias(record, plan, *, representative_aggregate_sha256=None, representative_counts=None)`
- `alias_from_bytes(data, plan, *, ...)`, `load_alias(path, plan, *, ...)` (same keyword arguments as `verify_alias`)
- `alias_state_entry(record)`

Open records:
- `open_record_violations(record, *, item_ids=(), texts=(), allow_floats=False) -> sorted codes`
- `check_open_record(...)` (same arguments; raises `OpenRecordViolation`)
- `is_hash(value)`, `is_reason(value)`, `replay_error_detail(code)`

How the pass is meant to call it per bench (the integration's side, played by `World` in the tests):

1. Write `inputs_record(...)` with `write_once(..., allow_sealed=True)`.
2. Per event: load its frozen state (`load_frozen(step_of(event))`) and keep `read_mount` = that state's step and
   the library and type map file hashes it was verified against. Pass what was actually loaded, not a copy of
   `state['read_mounts'][event]` or of the plan header: the binding is only as good as this value.
3. Per event and per item, with `arm = arm_of(event)` and the loaded library and type map:
   - `ident = services.identity_fn(..., arm=arm, ...)`
   - `mounted = services.mount_fn(..., arm=arm, selector=capture_selector)`
   - `comps = item_components(ident, mounted, arm=arm, public_sha256=..., view_sha256=...)`
   - if `first_request_required(bench, comps)`: run `services.solve_fn(..., call=CaptureCall())` and take
     `first_request()`
   - `item_record(...)`.
   - Catch stops and pauses: they propagate.
   - Map `ReadPlanError` to `event_entry(..., read_mount=read_mount, reason=error.code)`, and any other exception
     to `reason='identity_exception'`.
4. `event_entry(bench, event, ids, records, read_mount=read_mount, second=...)`; for S events, `second=` is the
   second embedder run.
5. Call `plan_files(...)` (it passes the header's `frozen` to `identities_record`). Write the identities files,
   then `read-plan.json`, each with `write_once`. Bind `plan_sha256` and the returned file hash. A pass re-run that
   rebuilds from stored identities calls `load_sealed(..., inputs=..., frozen=header['frozen'])`.

## Choices

1. Placement of constants. R1 puts the constants in `T/__init__.py`. I could only write `readplan.py`, so they are
   defined there; `__init__` can re-export them unchanged.
2. Names the spec leaves open:
   - Versions `typed-v2-read-plan-inputs-1` and `typed-v2-read-plan-identities-1`.
   - `item_set_sha256 = canonical_sha256({'v', 'bench', 'items': [sha256_text(id), ...]})`.
   - Recovery outcomes `pass_rerun`, `plan_restored`, `replay_equal`, `plan_void`, `alias_unsettled`,
     `paused_again`.
   - Replay codes `replay_exception` (an unexpected error in the child, R47b) and `timeout`; the composite
     `replay_error:<code>` admits `exit_<n>`.
3. Canonical bytes are JSON with sorted keys, indent 1, UTF-8, no NaN and a final newline: the same layout as
   `units.write_json`, so the open plan stays readable for ops. Self-hashes use `library.canonical_sha256`
   (compact form); "file hash" always means the sha256 of the stored bytes. Reading is strict: duplicate keys and
   NaN are refused, and the bytes must equal the canonical bytes of what they hold. That is why any byte change is
   detected, whitespace included.
4. Fallback reasons. When several apply, the first wins in this order: the caller's reason, then
   `identity_exception` (a missing or unreadable record; R31 has no separate "missing" code, so I added none), then
   `capture_failed`, then `embedder_unstable`. `capture_failed` also covers a first-request hash present where
   RP3 forbids one (ALFWorld, offered programs). An S event without a second run is `embedder_unstable` (stability
   not shown); an unreadable second-run record is `identity_exception`.
5. R29 handling. The rule is applied inside each group of equal identity lists: when it holds more than one
   distinct non-null first-request hash, every member with a non-null hash falls back. Within one bench, null and
   non-null cannot both occur among ok events (null only on ALFWorld), so the rule is transitive in practice.
   Classes are ordered by their first member and numbered from 1; a class's first-request hash is its
   representative's.
6. Extra consistency checks:
   - Components must carry the inputs' stored view hashes; otherwise that event falls back with
     `identity_exception`.
   - `frozen['C0']` must equal `frozen['C']` (both s0, R27).
   - `registry_sha256` is null exactly in a smoke.
   - The probe is allowed only in a smoke, for at most one pair.
   - Vectors are exactly two runs, or null.
   - `forced` must be None (R11).
7. Additions beyond the spec's records:
   - `descriptive_flips` is stored per event in the sealed identities entry, so the plan (with `embed`) can be
     rebuilt from the sealed files alone.
   - `build_plan` runs the open check against every item id of the five panels. An id that happens to equal a word
     of the plan would make the pass fail (safe direction) rather than leak.
   - (Review F1) The sealed identities entry of 3.3 also holds `library_file_sha256` and `typemap_file_sha256`
     beside `step`: the frozen state its identities were computed from. Every stored entry names the plan's
     `frozen[event]` (a fallback the pass made itself names it too, holding no identity). The open plan (3.2) and
     the alias record (3.4) do not change.
   - (Review F1) Reasons: a record mounted through another arm, or an entry computed from another frozen state, is
     `identity_disagreement` (two sources that must agree do not); an unreadable entry stays `identity_exception`.
   - (Review F1) Residual: the core sees the arm in the mount record but not which library object a mount used.
     An integration that loads and reports one state but mounts with another is not caught here; T3 to T6 against
     the real pass are the guard for that.
8. Open-record check details. Ids are matched inside strings, except short pure-hex ids (for example numbers),
   which are matched by equality only, since they would occur inside hashes by chance. Floats are refused (no
   scores). Reason keys: `reason`, `void_reason`, `fallback`, `detail`, `code`, `outcome`, `failures`.
9. Behaviour details:
   - `observed_from_row` maps a program id that the frozen library does not hold to None (never equal), instead
     of raising.
   - `CaptureCall` records later sends with `request_sha256: None`, so the send count is kept but only the first
     hash.
   - `replay_compare` accepts closed names only, and `equal` requires the plan file to be among them.
   - `write_once` accepts visible `.json` names only.

## Disagreements with the spec

1. R29 "both get status fallback" (a note, not a blocker). Read literally, one event whose first requests differ
   inside an identity group makes the whole group fall back. Example: S4 alone differs, so C, S1, S2, S3 and S5 are
   read fresh too (7 fresh units instead of 3 on that bench). I implemented the literal, safe reading. A narrower
   reading would also be correct: split the group into sub-classes by (identity list, first-request list), which
   keeps aliases whose members also agree on the first requests (the direct proof) and keeps the defect signal.
   That is the coordinator's choice; it changes only `compute_classes`.
2. R44 a, "equality with the record recomputed from the plan". This cannot cover `check`,
   `representative_aggregate_sha256` or `representative_counts`, which come from the representative's unit, not
   the plan. The spec compares only the aggregate hash with the mirror. The u/i/c counts shown beside every alias
   (RP3) should be compared with the mirror too; `verify_alias` accepts them (`representative_counts=`).
3. T23 asks that `state.json` hold "no reason outside READ_PLAN_REASONS". typed-v1's own pause details
   (`exception:<Class>`, `Pause:qualification_paused`, and so on) are outside it. The check can only apply to the
   read-plan parts of the state (`state['read_plan']`, the alias and void entries of `state['reads']`), unless the
   tuple absorbs those typed-v1 details.
4. R81 says recovery outcomes come from the closed tuple, but the spec names none. My names (Choices 2) are a
   proposal. The integrator should report if it needs others, because the tuple lives in this module.
5. Size. The change list estimates `T/readplan.py` at about 460 lines including the pass, the post-read check and
   the replay. The pure core alone is about 1,170 non-blank lines after the review fixes (validation of every input
   and record, and docstrings), so the integration will add to that.

## Left for integration

- The pass (R20 to R27, R33, R92):
  - set the phase and current unit; consent first;
  - open panels through `reads.open_panel`, with registry and qualification;
  - ALFWorld resets under `v218_lock.call`;
  - views, and two embedder runs in subprocesses;
  - frozen states through `load_frozen`, and the loaded state's step and file hashes passed to `event_entry` as
    `read_mount` (review F1);
  - the real `services.identity_fn` / `mount_fn(selector=capture_selector)` / `solve_fn(call=CaptureCall())`, with
    `arm=arm_of(event)` (also passed to `item_components`, review F1), the real unit name, cell tag and an
    uncreated scorer path;
  - the stop and pause propagation of R33 a, and the mapping of the pass's own detections to `read_plan_failed` +
    code (including Q24 `pass_exception`);
  - `remove_part_files` at start; the `checkpoint` seams.
- Binding: `state['read_plan']` gets `plan_sha256`, the `write_once` file hash and `bound_at`; then
  `mark('read-plan')`.
- Replay (R76, R47, R47b): the child process and its hash seed, consent, `own_root`, the qualification-pointer check
  (`qualification_missing`). It reloads inputs with `load_sealed`, calls `check_views` for non-ALFWorld benches,
  recomputes entries, calls `plan_files` and `replay_compare`, and handles exit codes and the information count of
  re-embedding.
- R44 verification and recovery, with archiving under `archived_alias_path`; void handling (R33 d, R44 c to e).
- `read_classes`:
  - both sweeps (R36);
  - per-member `frozen_entry_matches`, else `read_mount_changed`;
  - R41 through `expected_for_check` / `observed_from_row` / `post_read_check` (`program_sha256_of` from the event's
    frozen library);
  - settling with `build_alias` + `write_once` + `alias_state_entry`;
  - R42 voiding, R46 completeness.
- Also left:
  - mapping `WriteOnceMismatch` per R80;
  - `solver-settings.json` (R75, 3.5: its record builder is not here, only `write_once`);
  - `prepare` / manifest fields (R2, R3, R7: the probe is passed to `plan_files(probe=...)`);
  - the readout (R63 to R74, R89, R90);
  - the CLI (`plan-replay`, `--stop-after-plan`, smoke `--resume`, `--fake-kill-at`);
  - re-exporting the constants from `T/__init__.py` (R1);
  - T2 / T7 against the real `mount_identity` once Step 5m exists (N14).
