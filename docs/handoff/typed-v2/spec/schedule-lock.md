# typed-v2 spec: schedule and memory lock (decision D8)

Status: COMPLETE DRAFT, 2026-11-12 ("NOT DONE" at the end lists what was not verified). Author: design-team member
"schedule-lock". T/ = skillopt/execskill/typed/, X/ = skillopt/execskill/. [V] = opened and read in this tree,
[I] = inferred. Paths are relative to `<repo-root>`.

## 0. Blockers

No blockers. Both parts of D8 fit in T/, scripts/ and tests/ (F1: X/chain.py, X/v218_lock.py, X/profiles.py are only
read and called). Limit of evidence, not a blocker: this tree holds no measured memory use of any run, so the lock
default stays the typed-v1 behaviour (L6, L7).

## 1. Behaviour

### Part A. Schedule

S1. `prepare` writes a sealed manifest field `schedule`: `interleaved` (default) or `learn_first`. It is set only by
    `prepare --schedule`, is covered by the manifest record hash, and `run` / `smoke` read it from the manifest.
    There is no run-time option; a resume cannot change it.
S2. `interleaved` is the typed-v1 order: confirm; freeze s0; events C0, C; `step-0`; then for k = 1..5 the learning
    units of step k, freeze s<k>, event S<k>, `step-<k>`. `done_units` is the typed-v1 sequence (no new marker), so
    `tests/test_typed_chain.py:190-195` [V] stays valid.
S3. `learn_first`: confirm; freeze s0; for k = 1..5 the learning units of step k and freeze s<k>; then events C0, C,
    `step-0`; then for k = 1..5 event S<k>, `step-<k>`. Every event reads all five panels with fresh calls; nothing
    is skipped or reused (F5).
S4. Input of a read unit today [V]: `read_one` (T/chain.py:566-574) passes root, chain, event, bench, the in-memory
    `self.library` / `self.typemap` and `services`. The two objects come from `s<k>/library.json` and
    `s<k>/typemap.json` through `load_state(k)` (T/chain.py:451-453), called right before `reads('S<k>')`
    (:651-652) and as `load_state(0)` before C0 and C (:631-633). Inside the unit: owner consent, panel, per-unit
    panel views and vectors, unit name (T/reads.py:253-298). Nothing else of `_Run` enters: read cells pass no
    `step` (T/reads.py:342-345), so their package label is `typed/<unit name>` (T/mount.py:353), and
    `state['reads']` is only written (T/chain.py:602, its single use).
S5. The per-step state survives later steps unchanged on disk [V]: both files are written once (`if not exists`
    guards, T/chain.py:627-630, :933-936) by temp file plus replace, with a self-hash checked at load
    (T/library.py:161-180, T/tasktypes.py:247-266); later steps write only under `s<k+1>/`; `load_state` builds new
    objects, so later learning cannot leak through memory.
S6. Stored in addition (new, both orders): (i) a write-once receipt `s<k>/frozen.json`, k = 0..5, with the record
    hashes and file sha256 of both files, written as the last act of the freeze (today no record holds these
    hashes; `decisions.json` has summaries only, T/chain.py:917-936 [V]); (ii) `state['read_mounts'][event]` = step
    plus the two file hashes, set before the event's first unit and compared on every re-entry. An event starts
    only after `load_frozen(k)` matched the files with the receipt; a difference pauses the chain
    (`frozen_state_changed`) before any call.
S7. Same units, requests, identities in both orders [V]: unit names depend only on (event, bench)
    (T/reads.py:64-68) or (k, round); cell tag = sha256(bench, item id, arm) (T/units.py:253-254); request hash =
    sha256(system NUL user) (T/units.py `CallRecorder`); system and user come from the mount record, a function of
    (bench, item, arm, typemap, library, vector, view) (T/mount.py:154-177, :190-238); read meta holds chain, event,
    bench, arm, unit, smoke, items and no step (T/reads.py:253-298); learning of step k+1 starts from
    `load_state(k)` in both orders (T/chain.py:638). Consent: every non-smoke read unit calls `consent(shared)`
    before the panel opens (T/reads.py:91-141); a finished unit returns its stored status without a call
    (:264-265). C0 is the first event in both orders, so the write-once panel registry and the SpreadsheetBench test
    qualification are created by the same unit (`test-read-C0-<bench>`).
S8. What differs (bookkeeping; no request, identity or decision content): order of `done_units`; ledger
    `logical_call` numbers (running `sends` counter, already thread-timing dependent); ledger snapshots in
    `done.json` and `decisions.json` (`ledger`, `at`: under `learn_first` without earlier steps' read tokens); time
    stamps; where a cap or infrastructure stop lands; when consent is first checked (Q2).
S9. Resume, both orders: the same loop is re-entered. `learn(k)` is skipped when `s<k>/frozen.json` exists; that
    later steps need only the frozen files is shown by typed-v1's own skip path (T/chain.py:639-641 [V]). A step
    interrupted before its receipt re-runs its body as typed-v1 does for a step without `step-<k>` (finished units
    return their records; that this replay sends no call is [I], not re-opened) and writes the missing files.
    `read_anchors` / `read_step` skip finished benches through the existing `wanted` filter (T/chain.py:594-596);
    `mark` already ignores a repeated name (:307-310). A pause inside an event under `learn_first` resumes that
    event, then the later ones; no learning unit is touched. A state whose `schedule` differs from the manifest is
    refused.
S10. Status (`readout.status`, T/readout.py:645-656 [V]) shows `schedule`, `phase` (`learning` / `reading`),
    `current_unit` (`read-<event>` during an event) and the read mirrors. Under `learn_first`, steps 1..5 present
    without any mirror is normal. `state['step']` is not changed in the read phase.
S11. Size: small and well contained, not invasive. About 70 to 90 changed lines in T/chain.py, 10 each in
    T/prepare.py and scripts/run_typed.py, 6 in T/readout.py, 3 in T/smoke.py, 3 in T/reads.py (lock signature
    only); about 250 lines of tests.

### Part B. Memory lock

L1. Lock taken today [V]. Function: `route_b_chain.heavy(setting, bench)` with `extra = {'slot_root': ...,
    'configuration': 'default'}` (T/chain.py:1131-1132). `uses_environment_lock('default')` is false
    (X/profiles.py:1005-1018), so the plain branch runs (X/chain.py:134-145): a new descriptor on
    `<slot_root>/memory-heavy.lock`, blocking `flock`, untimed, unlogged. Mode by bench (X/chain.py:86, :115-122):
    spreadsheetbench exclusive (EX), alfworld shared (SH), other benches none.

| Unit type | Call site | Lock and duration |
|---|---|---|
| every learning cell unit (noise, typing no-harm, outcomes, card rounds, card learn, program smoke, program gate) | T/chain.py:469 | per cell, from after the mount (selection call outside, :464-467) to the end of `solve_fn`; model calls, sandbox worker, native scoring inside. Sheet EX, ALFWorld SH |
| read unit, SpreadsheetBench | T/reads.py:272, :342 | EX around `panel_tasks` (test qualification), released, then EX per cell around `solve_fn` (:342-345) |
| read unit, ALFWorld | T/reads.py:342 | SH per cell; the preparation resets (:229-230) take no lock |
| any unit on searchqa / officeqa / zebralogic | same sites | none (`heavy_mode` is None) |

    Each `flock` has its own descriptor, so two sheet cells of one unit exclude each other: width 2
    (T/__init__.py:50) is unused inside the lock and one sheet cell runs on the whole machine at a time. The comment
    at T/chain.py:469 ("as main-v10's cells.run_cell holds it") is inexact: main-v10 shared EX inside a unit (L2 b).
L2. Existing machinery lock functions a T/ call site can select [V]:
    (a) `X/chain.heavy` with configuration `default`: the plain lock (today).
    (b) `X/chain.heavy` with a configuration whose `uses_environment_lock` is true (main-v6..main-v10, cross-v5;
        typed already uses `MACHINERY = 'main-v10'`, T/__init__.py:56): X/chain.py:129-133 delegates to
        `v218_lock.environment` (X/v218_lock.py:76-180). Threads of one unit share EX (:123-125); one descriptor
        per process, closed when no thread is inside (:173-180); holder file (:108, :148-149); wait lines in
        `<root>/<chain>/chain.log` (:67-73), receipts in `<root>/<chain>/lock-waits.jsonl` (:161-165). Needs
        `setting.root` (a missing attribute is not caught by `_best_effort`, :37-41) and `memory_lock_chain` /
        `memory_lock_unit` (:97-100).
    (c) `v218_lock.call` / `workers` / `engine` (X/v218_lock.py:181-205): lock one native operation or one workbook
        worker, model calls outside. Needs edits inside `T/mount.py` `solve` and a new analysis. Deferred.
    Not admissible under D8(b): the map's native-pool wrapper and turnstile file (new mechanisms).
L3. Memory arithmetic. Ceilings [V]: sandbox worker 768 MB, 0.5 CPU, no swap (X/sandbox/client.py:125, :153-154);
    native scoring container 4096 MB, 1 CPU (skillopt/continual_eval/backends.py:119-121, :171); recalculation
    container 1024 MB, 1 CPU, no swap (skillopt/continual_eval/sheet_recalc.py:406, :456); ALFWorld environment =
    spawned host process, no limit (backends.py:605-615). Pools [V]: native 3 (2 in low-memory mode), episodes 6,
    live sandboxes 6, 2 per sheet unit (X/protocol.py:163, :715-717). Ceilings are limits, not measured use; the
    sums assume one cell's worker, scoring and recalculation containers alive together (conservative).

| | P `per_cell_plain` (typed-v1, option a) | U `unit_shared` (option b, per cell) |
|---|---|---|
| sheet cells inside the lock, whole machine | 1 | 2 (same unit) |
| ceiling of the locked sheet work | 768 + 4096 + 1024 = 5,888 MB | 11,776 MB |
| live workers of other cells (never locked) | up to 5 x 768 = 3,840 MB | up to 4 x 768 = 3,072 MB |
| sum of ceilings of 15,360 MB (15 GiB) | 9,728 MB, about 5.5 GiB left | 14,848 MB, about 0.5 GiB left |
| CPU ceiling of the locked sheet work, of 7 | 2.5 | 5 |
| ALFWorld (SH in both) | 2 cells per unit, 4 with two chains, pool limit 6; unmeasured host processes plus a 768 MB worker when a program is enabled; never together with a sheet cell | same |

    By ceilings U leaves too little for two chain processes, Docker and page cache; it is safe only if real use is
    far below the ceilings. X/protocol.py:717 (native pool 3 to 2 when the measured native peak exceeds 2 GiB)
    suggests native peaks near 2 GiB; U's locked sheet work would then be about 2 x (768 + 2,048 + 1,024) =
    7,680 MB. Code-level precedent [V]: the test qualification scores with width 2 under one EX hold
    (T/reads.py:154-155 `workers=SHEET_WORKERS`, :45, :272; X/evaluation.py:275-276; X/qualify.py:93
    `run_parallel(score, jobs, workers=workers)`), once per root, without solver workers. That each job starts one
    native container is [I] (`score` not opened).
L4. Deadlock and starvation.
    - P deadlock: the plain lock is not re-entrant (a second descriptor of the same thread blocks for ever). No
      nesting today [V]: the qualification lock ends before the cells (T/reads.py:272), the builder takes it once
      (T/chain.py:469), T/mount.py has no lock call. Test T10 guards this.
    - U deadlock: the same thread nests by a counter (X/v218_lock.py:117-121); a shared-to-exclusive upgrade raises
      `ValueError` (:118-119, :127-129), a pause instead of a hang; a typed cell names one bench, so no upgrade.
    - Lock against slot pools, both: lock first, then episode / live / call / model / native (X/slots.py:39). No T/
      code waits for the lock while holding a slot: the mount and its selection call end before the lock
      (T/chain.py:464-467, T/reads.py:340-341) [V]. No cycle.
    - P starvation: `flock` is not fair; overlapping SH holders (2 to 4 ALFWorld cells) can keep a sheet cell
      waiting for a whole ALFWorld unit, while ALFWorld cells can enter between two serial sheet cells.
    - U starvation, new: with two overlapping cells the process keeps EX until no thread of the unit is inside, in
      practice the whole unit. The other chain's sheet and ALFWorld cells wait on the kernel lock, and in a read
      event (`READ_WORKERS = 5`, T/chain.py:59) the same chain's ALFWorld read unit waits on the in-process
      condition (:126-131). Finite and visible (`lock-waits.jsonl`, holder file), but possibly hours.
L5. Tripled gate cells (D5, R = 3 inside one unit). Gate slices 50 (SpreadsheetBench) and 40 (ALFWorld)
    (T/__init__.py:17-23): 150 sheet cells and 120 episodes per gate arm. P: a sheet arm takes 150 x t_cell,
    serial on the machine, no ALFWorld cell anywhere meanwhile. U: about half, but the unit-long EX hold triples
    too. ALFWorld, both: the SH overlap lasts three times longer, so the other chain's sheet cells wait longer.
    No option changes a call count. `t_cell` is not known in this tree.
L6. Earlier use of the shared mode. Code [V]: main-v6..main-v10 and cross-v5 select it (X/profiles.py:1005-1018);
    route B builds it per cell (`lambda bench, unit: v218_lock.environment(setting, bench, unit=unit)`,
    X/units.py:251) and holds it around the whole cell, model calls included (X/cells.py:436-444); 22 tests in
    `tests/test_execskill_v218_locks.py` (e.g. :84). So five versions ran shared EX on the 15 GiB machine named at
    X/chain.py:86. Missing here: any memory measurement or incident record of those runs (no ssh in this task).
L7. Recommendation: default `per_cell_plain`, exactly the typed-v1 call. The evidence for U is "used by earlier
    versions", not "measured safe", and the ceilings leave no headroom, so D8(b)'s condition for a new default is
    not met. Implement U as an opt-in sealed manifest value (about 25 lines), chosen before `prepare` only after
    the zero-cost checks of Q3.

## 2. Change list

| # | File, place today | Change | New names |
|---|---|---|---|
| 1 | T/__init__.py:50-66 | add constants | `SCHEDULES = ('interleaved', 'learn_first')`, `SCHEDULE_DEFAULT = 'interleaved'`, `MEMORY_LOCKS = ('per_cell_plain', 'unit_shared')`, `MEMORY_LOCK_DEFAULT = 'per_cell_plain'` |
| 2 | T/prepare.py:255-290 `prepare` (fields :269-285), `load_manifest` :293-302 | two keyword parameters, membership check, written into `fields` before `seal`; `load_manifest` refuses a missing or unknown value | `prepare(..., schedule=SCHEDULE_DEFAULT, memory_lock=MEMORY_LOCK_DEFAULT)`; manifest fields `schedule`, `memory_lock` |
| 3 | scripts/run_typed.py `_prepare` :118-121, `prepare` :207-216, parser :262-263, `state_summary` :191-199 | options on `prepare` only, passed through `_prepare`; summaries show `schedule`, `memory_lock`, `phase` | `--schedule`, `--memory-lock` |
| 4 | T/chain.py:939-950 `_open_state` | new keys; refuse a resume whose state schedule differs from the manifest | `state['schedule']`, `state['phase']`, `state['read_mounts']` |
| 5 | T/chain.py:624-634 `anchors` | split: `freeze_anchor()` = :626-630 plus receipt; `read_anchors()` = `load_frozen(0)`, `bind_read`, events C0 and C, `mark('step-0')` | `_Run.freeze_anchor`, `_Run.read_anchors` |
| 6 | T/chain.py:637-653 `step` | split: `learn(k, bench)` = skip when `learned(k)`, else `load_frozen(k - 1)`, set step and phase, lines :644-650 unchanged; `read_step(k)` = when `step-<k>` is done `load_state(k)` and return (as :639-641), else `load_frozen(k)`, `bind_read`, `reads('S<k>')`, `mark('step-<k>')` | `_Run.learn`, `_Run.read_step`, `_Run.learned` |
| 7 | T/chain.py:917-936 `finalize` | after `typemap.json`, write the receipt once from the files on disk | `FROZEN = 'frozen.json'`, `_Run.freeze(k, bench)` |
| 8 | T/chain.py:451-453 `load_state` | unchanged; new `load_frozen(k)`: check the receipt's own hash, `load_state(k)`, compare both file hashes, pause on a difference, return the receipt | `_Run.load_frozen`, `_Run.bind_read(event, k, receipt)`; pause reasons `frozen_state_changed`, `read_mount_changed` |
| 9 | T/chain.py:979-982 in `run` [V] | by `manifest['schedule']`: interleaved = confirm, freeze_anchor, read_anchors, then learn(k) and read_step(k) per k; learn_first = confirm, freeze_anchor, learn(1..5), read_anchors, read_step(1..5); `phase` None at completion | none |
| 10 | T/chain.py:97-162 `Services.heavy` (:113, :145), :1131-1132 in `real_services` | `heavy(bench, unit=None)` from a helper: `per_cell_plain` = exactly today's call (unit ignored); `unit_shared` = `route_b_chain.heavy(SimpleNamespace(root=<run root>, extra={'slot_root': ..., 'configuration': MACHINERY, 'memory_lock_chain': chain, 'memory_lock_unit': chain + '/' + unit}), bench)` | `chain.heavy_for(manifest, root, chain)` |
| 11 | T/chain.py:469 (`builder`, parameter `unit` :456 [V]) | `with s.heavy(bench, unit):` | none |
| 12 | T/reads.py:269, :272, :342 | fallback lambda and both `lock(...)` calls take `(bench, unit)` | none |
| 13 | T/smoke.py:305 `fake_services` | fake lock accepts `unit=None`; the smoke manifest carries both fields | none |
| 14 | T/readout.py:645-656 `status`, :689-697 `_md_state` | print `schedule`, `phase`; the new files are already tolerated (scans at :103-104, :256, :346 take directories only [V]) | none |

Not changed by this area: `reads`, `read_one`, `read_event` (T/chain.py:566-622), the rest of T/reads.py, T/units.py,
T/mount.py.

## 3. Records and identity

- Manifest: new fields `schedule`, `memory_lock`, covered by the record hash. That hash already differs for every
  prepared root (`root`, `prepared_at` are fields, T/prepare.py:269-285 [V]) and enters the panel registry entry as
  `run=` (T/reads.py:274) in the same way in both orders.
- `state.json`: new keys `schedule`, `phase`, `read_mounts` (open file; names and hashes only).
- New record `s<k>/frozen.json` (write-once): `version`, `chain`, `step`, `bench` (None for s0),
  `library_record_sha256`, `typemap_record_sha256`, `library_file_sha256`, `typemap_file_sha256`, `at`,
  `record_sha256`.
- Shape unchanged by this area: `decisions.json`, proposals, writer records, ledger, read aggregate and mirror
  (T/reads.py:432-475), `done.json`, cell rows. Their order-dependent values are listed in S8.
- Option U only: open files `<slot_root>/memory-heavy.lock.holder-<pid>.json`, `<root>/<chain>/chain.log` (new:
  T/ writes no file of that name today [V]), `<root>/<chain>/lock-waits.jsonl` (unit names, process ids, times).

Byte-identical to typed-v1 in both orders and both lock options (apart from other areas' changes): all request
texts, prompt pins, cell tags, request hashes, mount records, package labels, unit names, consent checks, panel
registry content. How I know: S7, and the lock wraps `solve_fn` and passes nothing into it (T/chain.py:469-473,
T/reads.py:342-345 [V]). Assumption [I]: the embedder is deterministic per text, as typed-v1 resume assumes.

## 4. Tests

New (`tests/test_typed_schedule.py`):
- T1 `test_prepare_schedule_and_lock_fields`: defaults, both values, unknown refused, hash covers both.
- T2 `test_interleaved_done_units_are_the_typed_v1_sequence`: expectations of `tests/test_typed_chain.py:190-195`.
- T3 `test_learn_first_same_units_requests_identities`: one fake script, two roots, two schedules: equal sets of
  `done_units`; per unit equal cell tags, request hashes, mount records, row labels, read meta; only order differs.
- T4 `test_learn_first_reads_mount_each_steps_frozen_state`: event S<k> gets the hashes of `s<k>/frozen.json`
  although `s5` exists; C0 and C get s0.
- T5 `test_changed_frozen_file_pauses_before_any_call`: another valid library in `s2/` pauses S2 with zero calls.
- T6 `test_learn_first_resume_in_learning_and_in_reads`: crash in s3, later in S2; nothing finished is redone.
- T7 `test_resume_refuses_a_different_schedule`.
- T8 `test_consent_is_checked_in_every_read_unit_in_both_orders`: real `panel_tasks` path, no consent, no panel opens.
- T9 `test_status_shows_schedule_and_phase` (`readout.status`, `state_summary`).
- T10 `test_default_lock_is_the_typed_v1_call`: a spy sees `extra == {'slot_root': ..., 'configuration': 'default'}`
  for learning and read cells; no holder or wait file; AST check that T/mount.py and T/units.py hold no lock call.
- T11 `test_unit_shared_two_cells_overlap_and_another_unit_waits`: temporary slot root, threads, holder file.
- T12 `test_unit_shared_setting_names_root_chain_unit`: a missing unit raises (X/v218_lock.py:99-100).
- T13 fresh interpreter under `bind_machinery` (pattern `tests/test_typed_cli.py:80-105` [V]; snapshot = temporary
  copy of this tree's `skillopt/` without `execskill/typed`): `route_b_chain` and `v218_lock` load from the
  snapshot; mode P really locks `<slot_root>/memory-heavy.lock` (a non-blocking `flock` from outside fails); mode U
  writes the holder file; a fake `learn_first` chain and a fake `interleaved` chain end with equal `done_units` sets.

Existing tests that must change:
- `tests/test_typed_reads.py:226-227`: fake `heavy_lock(self, bench)` gets `unit=None`; the counts at :264, :384,
  :445 stay (per-cell holds unchanged).
- `tests/test_typed_reads.py:581`, :628 (prepare tests): add the two fields if they compare the key set [I].
- `tests/test_typed_cli.py:110-115`: the `_prepare` fake takes `**kw` [V]; its expected keywords gain two names [I].
- `tests/test_typed_chain.py:190-195`: no change from this area. Tests using `smoke.fake_services` keep working
  through change 13 ([I]: call sites not re-opened).

## 5. Interfaces to other areas

- Gate (D5): I rely on repeats staying inside one unit and on `cells()` / `builder` remaining the single path of
  learning cells (one lock line, T/chain.py:469). A repeat index in tags or labels concerns neither lock nor schedule.
- Version (D6), machinery check (D1): `prepare` fields and `load_manifest` are edited by several areas; merge in one
  step. Caps are unaffected: both orders send the same requests.
- Beside typed-v1 (D7): P and U lock the same file with the same kernel lock (X/chain.py:138, X/v218_lock.py:101
  [V]), so a typed-v2 chain in either mode excludes typed-v1 and route-B processes correctly; the slot root is shared.
- Readout: new state keys, new file `s<k>/frozen.json`; under `learn_first` no read mirror until learning is done.
- Others may rely on: the constants of change 1; `Services.heavy(bench, unit=None)`; `_Run.learn`, `_Run.read_step`,
  `_Run.read_anchors`; unchanged names `read-<event>-<bench>`, `test-read-<event>-<bench>`, `step-<k>`, `s<k>/...`.
- Owner hooks (DECISIONS section 3, not designed): a read policy would attach only in `read_anchors` and `read_step`.

## 6. Risks and open questions

Q1. Schedule of the real run? Recommended: `interleaved`. Under `learn_first` every step is still read on all five
    panels with fresh calls, but only after all learning; a chain stopped early has no read at all, which conflicts
    with the main-experiment rule unless the owner accepts it. Its gains: reads cannot stall learning, and all
    events lie close in time.
Q2. Under `learn_first` consent is first checked after all learning. Recommended: one zero-call
    `reads.consent(shared)` check at chain start (mode `run`, schedule `learn_first`); it reads only the owner's
    consent record; per-unit checks unchanged.
Q3. Lock of the real run? Recommended: `per_cell_plain`. Choose `unit_shared` only if the coordinator finds on the
    Linux machine, before `prepare`: the measured native peak and the native pool size in use, no memory kill in the
    main-v9 / main-v10 period, their `lock-waits.jsonl`, and typed-v1 sheet cell durations showing that serial
    sheet gates are the long pole.
Q4. ALFWorld preparation resets of read units take no lock today (T/reads.py:229-230); main-v9 / main-v10 locked
    each reset (X/v225_read.py:322 [V]). Recommended: keep typed-v1 behaviour in the default mode and record the
    exposure; with `unit_shared`, wrap the reset with `v218_lock.call` in the same change.
Q5. Fairness: no existing lock function is fair; with tripled ALFWorld gate units the other chain's sheet cells can
    wait for a whole unit. A turnstile is a new mechanism, outside D8(b). Recommended: accept for typed-v2; judge a
    stall by cadence and the kernel lock table before stopping anything.

## NOT DONE

- Not opened: `score` inside X/qualify.py, the writer replay on resume (S9), T/readout.py beyond the cited lines,
  the bodies of the existing tests marked [I].
- Length: this file is longer than the requested 230 lines; nothing was cut, to keep the evidence.
- Not available in this tree: measured memory use, per-cell durations, run logs of main-v6..main-v10.
