# Report of piece P2a (item-stage tools), as returned by its builder 2026-11-15 ~02:5x

Only new files, worktree <repo-root> (branch research/typed-skills-v3-items,
base d25619c). New tests 62 passed; whole typed selection 936 passed (874 + 62), 118 s.

## (a) Files and interfaces
Files: skillopt/execskill/typed/items/{__init__,store,plan,zebra_items,select_items,registry}.py;
tests/test_typed3_items_{core(19),plan(14),zebra(12),select(13),leakage(4)}.py.

items (`skillopt.execskill.typed.items`)
- Constants: `ITEM_QUOTAS` (T5 table, `{bench: {'judging': {attack, guard, calibration}, 'shown': {attack, guard}}}`);
  `EVIDENCE_MIN_ITEMS=3`, `EVIDENCE_MIN_FAILED_RUNS=2`, `MIN_KEPT_WEAKNESSES=3`, `REDUCED_ATTACK_SHARE=Fraction(1,5)`,
  `CHECK_MARGIN_POINTS=5`; `SIDES=('shown','judging')`, `CLASSES`, `SOURCES`, `RECORD_KEYS`, `RECORD_VERSION='typed-v3-items-1'`.
- `counts(bench, kept_weaknesses, quotas=ITEM_QUOTAS)` (kept_weaknesses int or ids in plan order) ->
  `{bench, weaknesses, weakness_ids, rule: 'quota'|'reduced_attack'|'no_items', judging, shown, attack_split:
  {'judging': [[w, n], ...], 'shown': [...]}, totals}`. Split: in turn, plan order; the first `total % k` get one
  more. 20 % rule: `total // 5` on each side; judging guard unchanged, rest calibration; shown guard = rest of shown.
  `check_counts(c)` validates a counts record (also a reduced one built for items-2; needs `weakness_ids` whenever
  the split is non-empty).
- `check_plan(attack_pass, attack_n, cal_pass, cal_n)` -> `{holds, reason: 'holds'|'attack_not_harder'|'empty_class',
  attack, calibration, difference_points, rule}` (exact Fractions; an empty class never holds).
- `check_items(judging_records, {item_id: True|False|None})` -> check_plan's result + `by_weakness: [[w, n, pass]]`
  (only True passes).
- `largest_remainder(total, [(key, weight)])` (ties: larger weight, then listed order); `ordered_proportion(total,
  weights)` the same counts as an interleaved sequence.
- `item_sha256(bench, item)`: zebralogic `zebra_build.item_digest`; searchqa task_id + whole public part + private
  answers; other benches task_id + whole public + whole private.
- `item_record(*, item, cls, weakness, side, family, source, certificate, item_sha256)` / `check_record(record)`:
  exactly 8 keys; weakness `w<n>` or None, only on attack items; a made item has a certificate dict, a selected None.
- `MakeInput(bench, plan, counts, pool, pool_pin, learn_ids, gate_ids, outcomes, repeats, identity, registry, store,
  role_call=None, view_of=None, language=None)` with `.check()`; `identity = {'version', 'chain', 'step', 'round'}`
  (round 1 for `items`, 2 for `items-2`; enters every seed and draw tag); `outcomes = {learn id: [R values]}` for
  exactly the learn ids.
- `RoleUnavailable(purpose, tag, failure)`: raised by the SearchQA selector on an infrastructure failure.
- `MAKERS[bench]` (lazy, `registry.py`): `.bench`, `.built`, `.capability_sheet(*, pool, learn_ids, gate_ids)`,
  `.public_kind(item)`, `.make(inp)` -> `{bench, status: 'made'|'no_items', reason: None|'maker_not_built'|'no_quota',
  records: [item records in listing order], slots: [rows], shortfalls: [...], made_counts, record}`; officeqa and
  spreadsheetbench return `no_items` with `maker_not_built` (recorded, no error, nothing written).

items.store
- `ItemStore(unit_dir)`: `.once(parts, compute)` (BankEnv's contract), `.slot(name)`, `.write_item(name, item)`,
  `.item(name)`, `.write_slot(name, *, record, shortfall, attempts, detail)`. Files `items/<slot>.json` (item in
  benchmark form) and `records/<slot>.json` (write-once slot record); all through `units.write_json` (path guard).
  Slot name `<side>-<class>-<w<n>|x>-<nnn>` (`slot_name(side, cls, weakness, number)`).
- `RunRegistry(records=())`: `.add(record)`, `.ids`, `.texts`, `.families`, `.family_sides(f)`; `add` refuses a
  repeated id or text and then changes nothing.

items.plan
- `ANALYST_PURPOSE='item_analyst'`, `ANALYST_SYSTEM`, `ANALYST_RETRY`, `INPUT_BYTES` (= `profiles.ROLE_INPUT_BYTES`, 220000).
- `learn_rows(bench, learn_items, runs, R, *, view_of=None, kind_of=None)` (`runs = {id: [R cells of B, run 1
  first]}`): id, public text (`tasktypes.public_text` cut to `writers.VIEW_CHARS`), outcomes, one wrong-reply
  excerpt (`writers._reply`, cut to `REPLY_HEAD + REPLY_TAIL`). `outcomes_of(runs, R)`.
- `analyst_payload(*, bench, task_card, learn, repeats, experience, capability_sheet, format_block=None,
  revision=None)` -> `(payload, dropped)`; `revision_block(plan, check)` (first plan + counts only).
- `request_plan(call, payload)` -> `{status: 'ok'|'unreadable'|'infrastructure', raw, request_sha256, attempts:
  [{request_sha256, reply, failure, readable}]}` (both replies kept).
- `validate_plan(raw, learn_outcomes, R, sheet)` -> `(plan, record)`; plan `{weaknesses: [{id: 'w1', given_id,
  description, evidence: [counted ids], signature, spec}], guards: [{id: 'g1', description, spec}], note, unreadable}`.
- `check_sheet(sheet)`, `check_spec(spec, sheet)`; `candidates_of_decisions(decisions_json)` (a program row with
  `origin == 'archive'` -> kind 'archive'); `experience_log(earlier_steps)` with input one dict per earlier step
  `{'step', 'bench', 'candidates': [{'kind', 'accepted', 'reason', 'gain_points', 'n', 'attack': {w: {'n',
  'gain_points'}} (optional)}], 'weaknesses': [{'id', 'description'}]}` (fields whitelisted; reasons short labels,
  descriptions cut to 500 characters).

items.zebra_items: `ZebraMaker`; `capability_sheet(sizes)` (sizes / emphasis 0.5-2.0 per clue kind / search
'any'|'needed'); `guard_sizes`, `plan_slots`, `seed_of`, `item_id_of` (`'zm3-' + sha256(seed)[:16]`), `make_puzzle`;
`MAX_ATTEMPTS = 25` per slot; part label 'made'; records `zebralogic/language.json` (via `zebra_build.stage_language`)
and `zebralogic/maker.json`.

items.select_items: `SearchQASelector` (`SELECTOR_PURPOSE='item_selector'`, `BATCH=25`, `SELECTOR_SYSTEM`; one call
per batch via `inp.role_call('selector-NN')`; write-once `selector/batch-NN.json`, then `selection.json`);
`ALFWorldSelector` (no model call; `TYPES`, `game_type(item)` via `supply.task_folder(game_file)`, `type_guards`).

## (b) Tests
`TMPDIR=/tmp/typed3-items-neutral python3 -m pytest tests/test_typed3_items_*.py -q -p no:cacheprovider` -> 62 passed;
`tests/test_typed*.py` -> 936 passed. Outside the suite: 7 mutated constants each fail a test; 4 injected leaks each
fail the leakage test.

## (c) Deviations / decisions
1. Item files are named by SLOT, not item id (pool ids can contain 'test' (ZebraLogic `lgp-test-...`), ':' or '/');
   records keep the real ids. So P2b's `s<k>/items/<item id>.json` will NOT work: use the store's slot files.
2. Kept weaknesses get canonical ids w1, w2, ...; guards g1, g2, ...; the analyst's id kept as `given_id`.
3. A failed run is any outcome that is not True (None counts as failed).
4. The analyst's text is `tasktypes.public_text` of the item's view (not the solver's full first request); the payload
   covers all learn items and is fitted to ROLE_INPUT_BYTES by a stated drop order (from the last item backwards:
   texts of always-right items, then replies, then other texts); fit counts returned.
5. SearchQA family = `family_id` (exact-question hash); a candidate sharing a family with a learn/gate item or an
   earlier pick is excluded.
6. ALFWorld family = room (scene); shown and judging never share a room; candidates in a seeded order.
7. ALFWorld: no type won in every run -> guard types = the two highest pass rates; a weakness whose spec names no
   task types draws from all types.
8. No kept weakness, any bench: attack items drawn like calibration, class 'attack', weakness None.
9. Shortfalls: SearchQA judging attack/guard -> calibration; SearchQA shown -> recorded only; ZebraLogic and ALFWorld
   recorded only, never filled.
10. ZebraLogic seeds also name side, round and attempt; part label 'made'; columns drawn among those the language has
    for the house count.
11. `request_plan` returns 'infrastructure' without spending the format retry; the selector raises RoleUnavailable
    and finished batches are kept.
12. The selector sees opaque labels (d1..., c01...), never item ids or families.

## (d) What P2b must do
- items-plan: sheet = `MAKERS[b].capability_sheet(pool=Services.items[b], learn_ids=..., gate_ids=...)` (same sheet
  to `validate_plan`); rows = `learn_rows(..., view_of=views, kind_of=MAKERS[b].public_kind)`; `task_card =
  writers.task_card(b, runtime)`; `request_plan(_keep_earlier_sends(role_call('item_analyst', unit, 'analyst',
  WRITER_TOKENS)), payload)`; on 'infrastructure' the chain's rule (one automatic retry, then pause) and no plan
  record; otherwise write the call result and the validate_plan output once; skip the analyst when
  `MAKERS[b].built` is False or `counts(...)['rule'] == 'no_items'`.
- items: `counts(b, [w['id'] for w in plan['weaknesses']], sealed_quotas)`, `store = ItemStore(<unit dir>)`,
  `role_call = lambda tag: _keep_earlier_sends(Services.role_call('item_selector', unit, tag, WRITER_TOKENS))`; the
  registry holds the chain's records from OTHER units only (earlier steps, round 1 incl. replaced items); the maker
  re-adds what it reads back on resume; catch RoleUnavailable -> retry-then-pause.
- items-2: `identity['round'] = 2`; pass ZebraLogic's round-1 language record (`ItemStore(items unit).read('zebralogic',
  'language.json')`) as `inp.language`; build a reduced counts record (attack classes only, with `weakness_ids`); P2b
  decides the attack count when plan 2 keeps a different number of weaknesses than plan 1.
- Keep: item files, slot records, language.json, maker.json, selector batch records, selection.json, the plan call
  and the validation record.
- Sealed quotas: start from `ITEM_QUOTAS` with OfficeQA and SpreadsheetBench at 0.
- No change to an existing file is needed by the package.

## (e) Open risks
- SearchQA: the selector's match quality drives the composition (few matches -> shortfalls to calibration, attack
  shrinks, the check may fail); an unreadable plan leaves the shown side with only 8 attack draws.
- ALFWorld: about 262 candidates; keeping rooms on one side can cause shortfalls if some types sit in few rooms.
- ZebraLogic: search 'needed' + heavy emphasis can exhaust 25 attempts (shortfall); 6*6 about 0.9 s a puzzle.
- Determinism relies on CPython `random` seeded with a string (as the bank); rerun ZebraLogic tests on dl's 3.11.
- `plan.learn_rows` uses the private `writers._reply`.

## Round 2 (answer to the one review, 2026-11-15 03:0x)
1. ALFWorld guard types: only types where every learn game was won in all R runs; NO two-highest fallback (that rule
   is ZebraLogic's). None qualifies: the judging guard count joins calibration (gate type proportions), recorded as
   `guard_to_calibration: n` in the selection record; the shown guard count is a recorded shortfall `no_guard_type`.
   `type_guards` returns `([], 'none_all_right')` then.
2. Selector reply values: each value null or one of the batch's description ids; any other shape or an unknown id
   makes the reply unreadable (one format retry, then the batch is unreadable and selects nothing).
   `read_matches(reply, ids)` now takes the ids. A key that is no candidate label is tolerated (`unknown_labels`).
3. Resume after a recorded response: `plan.recorded_receipt` / `plan.send_or_replay` replay a recorded verdict of
   exactly that request (request hash) before sending; only a missing attempt or one that failed for
   infrastructure is sent. Used by the selector AND by `request_plan` (the analyst). Works only when P2b wraps every
   analyst and selector role call in `chain._keep_earlier_sends`.
4. Item files write-once: existing file must equal the canonical bytes, else raise.
5. Item hash tests: each solver-visible field and the reference changed alone changes the digest (three benches).
Tests: 80 item tests pass (core 23, plan 16, zebra 12, select 25, leakage 4); 954 typed tests pass.
