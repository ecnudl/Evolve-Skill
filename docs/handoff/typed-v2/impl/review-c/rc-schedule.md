# rc-schedule review notes (read-only reviewer; lens: schedule, lock, resume)

Started 2026-11-12. Code under review: `git diff de7346c` (batch 3) in context of `git diff 8375ecb`.

## Plan
- [ ] Read binding docs: ADDENDUM (D9-D17, RP1-RP12), DESIGN schedule parts, spec/schedule-lock.md, IMPLEMENTATION-ORDER Step 6
- [ ] Read C (chain.py) diff: learn_first / interleaved scheduler, receipts, R79 guard, resume
- [ ] Read machinery.py diff: unit_shared lock, heavy cells, ALFWorld read reset
- [ ] Read reads.py / readout.py / readplan.py interplay with schedule (read phase start marker)
- [ ] Read scripts/run_typed.py CLI flags
- [ ] Check: same requests in both orders (identity, cell tags, decisions order-independent)
- [ ] Check: frozen receipts and their checks
- [ ] Check: R79 through every resume path
- [ ] Check: lock coverage, deadlock/starvation between two chains (L4)
- [ ] Check: kill/resume never repeats a finished paid cell nor skips one
- [ ] Run tests (test_typed_schedule.py etc.)
- [ ] Final findings

## Findings (draft)

Progress (ticked as I go):
- [x] Binding docs read (ADDENDUM, DESIGN 3.6, spec/schedule-lock.md, read-plan R20-R47, R79, IMPLEMENTATION-ORDER Step 6)
- [x] chain.py: run order, learn/read_step/read_anchors/freeze_anchor, freeze/load_frozen/bind_read/learning_closed, heavy_for, economy methods
- [x] reads.py: open_panel, preparation_reset, lock(bench, unit) sites; v218_lock.environment semantics
- [x] Baseline tests: test_typed_schedule.py + test_typed_reads.py: 37 passed
- [x] Order equivalence: no request/identity/tag/decision input depends on order (state['step'] unused by reads; ledger snapshots bookkeeping only; learning of k+1 always from load_frozen(k))
- [x] Receipts: freeze/learned/load_frozen/frozen_state/_receipt_valid/bind_read; refusal to re-make a mounted state's receipt
- [x] R79: phase 'read' persisted by bind_read before any panel opens (full: read_anchors; economy: plan()); learn/freeze_anchor guarded; no other learning entry point
- [x] Lock: every cell (learning builder, read _cell_builder), sheet qualification and ALFWorld resets (read units + pass) go through heavy(bench, unit) / v218_lock.call; lock taken before slots everywhere; no nesting; registry lock released before resets
- [x] Kill/resume: unit-level resume (run_unit resume=True), reads() marks after completion, economy settle/void/unsettle crash windows re-converge
- [x] Tests: test_typed_readplan.py + test_typed_chain.py + test_typed2_shared.py: 81 passed
- [x] Full typed suite run once
- [x] Final findings

## Done

Read-only review of batch 3 (`git diff de7346c`) in the context of `git diff 8375ecb`, lens schedule / lock / resume.
Code read: T/chain.py (`run`, `_open_state`, `heavy_for`, `consent_first`, `confirm`, `freeze_anchor`,
`read_anchors`, `learn`, `read_step`, `learned`, `freeze`, `load_frozen`, `frozen_state`, `_frozen_hashes`,
`_receipt_valid`, `bind_read`, `learning_closed`, `builder`, `cells`, `reads`, `read_event`, `plan`, `pass_failed`,
`void_plan`, `unsettle`, `replay_plan`, `verify_read_plan`, `recover_aliases`, `read_classes`, `settle`, `void_bench`,
`complete_reads`, `replay_child`, `replay_services`, `plan_replay`, `real_services`), T/reads.py (`open_panel`,
`preparation_reset`, `_from_services`, `_read`, `_cell_builder`, `panel_tasks`, `consent`), T/readplan.py
(`open_plan_panels`, `run_pass`, `recompute_files`, `replay`, `capture_first_request`), T/prepare.py, T/smoke.py,
scripts/run_typed.py, and the frozen X/v218_lock.py, X/chain.py `heavy`, X/evaluation.py `_registry`,
`_sheet_qualification`, `alfworld_reset`, `_with_views`.

Verified (no defect found):
1. Order equivalence. No request, identity, cell tag, unit name or decision input depends on the schedule:
   learning of step k always starts from `load_frozen(k-1)` in both orders; every read event mounts
   `load_frozen(k)`; read cells carry no step (`state['step']` is not read by the read path); ledger snapshots in
   decisions.json / done.json are bookkeeping and feed no request; D16 `members_of` uses only earlier benches'
   practice data. Interleaved keeps the typed-v1 done-unit sequence (no new marker).
2. Receipts. Written as the last act of every freeze (finalize, freeze_anchor), atomic replace, exact keys, own hash,
   version/chain/step checked; `load_frozen` compares both file sha256 and both loaded record hashes; `bind_read`
   compares the mounted file hashes on every re-entry; `freeze` refuses to re-make a receipt for a step any read
   mounted. The plain `load_state` on done steps is never used for a later request.
3. R79. Under learn_first the phase 'read' is persisted by `bind_read` before any panel opens (full: read_anchors;
   economy: plan(), before consent and the pass); an exception before that persist is persisted by `pause`; no code
   sets the phase back; `learn` and `freeze_anchor` are the only learning entry points and both are guarded; the
   directory check covers test-read-*, practice-read-*, test-read-plan, practice-read-plan, read-plan.json.
4. Lock coverage. Every learning cell (`builder`, incl. D16 member units on the cell's own bench), every read cell
   (`_cell_builder`), the sheet qualification in `open_panel` (read units and the pass) take `heavy(bench, unit)`;
   ALFWorld preparation resets of read units and of a first pass go through `preparation_reset` (v218_lock.call,
   SH, per game) under unit_shared and stay bare under per_cell_plain; the replay and the capture open no
   environment. per_cell_plain is byte-identical to the typed-v1 call (8375ecb:1131-1132).
5. Deadlock. Lock before slots everywhere (mount + selection call end before the lock; the reset wraps
   `episodes.hold()` inside the lock); no nested acquisition in one thread; the route-B registry lock is released
   before `_with_views`; the qualification lock is taken inside the env lock by every holder (same order); the
   replay child takes no env lock and the pointer exists before it runs. Starvation is finite (unit-long EX/SH
   holds, spec L4/Q5, accepted by D13).
6. Kill/resume. Units resume cell by cell (`run_unit(resume=True)`), `reads` marks only after every wanted unit is
   complete, a done unit returns its stored status without a call; economy crash windows (between bind and pass,
   pass and binding, alias write and mark, inside void_bench / void_plan) re-converge without a second fresh read
   of a pair and without settling a pair that was not checked.

## Tests

`mkdir -p /tmp/typed2-neutral && cd <repo-root> && TMPDIR=/tmp/typed2-neutral
<python> -m pytest -q -p no:cacheprovider tests/test_typed_*.py tests/test_typed2_*.py`
Last line: `707 passed in 81.79s (0:01:21)` (Python 3.13; no 3.11 on this Mac).

## Choices

- Reported only defects with a concrete failure scenario in this lens; none survived.
- Not reported (pre-existing, not data-affecting): a SIGINT during a read event waits for a worker thread blocked
  in a kernel flock (the other chain's holder) before the process exits; true for cells under per_cell_plain in
  typed-v1 as well, and now also for the wrapped ALFWorld reset under unit_shared.

## Disagreements

None.

## Left for later steps

- RP15 routed members in `members_of` (fix-c) are not built yet; they use only earlier benches' stored practice
  vectors, so they stay order-independent if built that way.
