# typed-v2: implementation order (merged with the addendum and the build as done)

> **Integration status (2026-11-13, coordinator):** this file folds the addendum through RP13 (merge of 2026-11-12 ~20:4x, one fidelity check). Later decisions RP14 (open points of this merge: reset wrap in Step 6, O7 order as built, Step 7 last, memory sampler mandatory), RP15 (D16 members include routed benches) and RP16 (Codex round 2: recompute convention, binding [import] wording) and the as-built reports of batch 3 (impl/6s.md, rp-int.md, rp-ro.md, 7g.md, fix-c.md) are in DECISIONS-ADDENDUM-20261112.md, which keeps precedence over this file.


Companion of `DESIGN.md` (same directory; section numbers below refer to it). Written 2026-11-12 before any code
edit; merged the same evening with `DECISIONS-ADDENDUM-20261112.md` (build split [BS], module placement [MP], D15 to
D17, O10, RP1 to RP13) and with the build as it was actually done (implementer reports `impl/*.md` and
`impl/rp-core.md`, the git history of `<repo-root>` and its worktrees, observed at
about 19:55). Marks as in `DESIGN.md`: a source id in brackets for folded decisions, "Changed by <id>: <what>" where
the addendum replaced a line, [impl <id>] for a build fact, [I] for an inference or a proposal of this merge;
[workflow] marks a rule of the build workflow's implementer prompts (`SkillOpt-scratch/typed-v2-build/workflow-A.js`:
its precedence line and "HARD RULES"), not an addendum decision. The step ids 1a .. 5x come from the addendum [BS, D16, D17] and rp-core from
the report name in RP13; the name "batch 3", the ids 6s, rp-int, rp-ro, 7g and "Step R" are this merge's [I].
`T/` = `skillopt/execskill/typed/`, `X/` = `skillopt/execskill/`, `C` = `T/chain.py`, `W` = `T/writers.py`. Line
numbers are those of the untouched tree (commit 8375ecb); they move after each step, so find a site by its function
name. Local test command, always from the tree root:

    TMPDIR=/tmp/typed2-neutral <python> -m pytest -q -p no:cacheprovider <files>

(`/tmp/typed2-neutral` must exist and its name must stay plain: a directory name containing `test` is refused by the
sealed-path guard. Delete its contents after a large run.) The full typed selection is `tests/test_typed_*.py
tests/test_typed2_*.py`. The Mac has Python 3.13 and 3.10 (no 3.11); the code must run on Python 3.11 (dl) and 3.13.

Why this order. Five files are shared by several areas: `C` (all six areas), `W` (card, reply, engineer),
`T/smoke.py` (reply, engineer, gate, schedule), `T/prepare.py` and `T/readout.py` (gate, identity, schedule), plus
their tests. The steps are strictly sequential, one area at a time, each ending with green tests. Step 1 changes the
literals that every test pins and makes the one pass over `Services` and its fakes; the reply reader comes before
the engineer step because the prompt embeds `replies.REPLY_FORMAT` and both rewrite the same three functions of `W`;
the gate comes after card and engineer because it rewrites the bodies they touch in `C`; schedule comes last because
it only reorders finished units. Before step 1 the coordinator answers O1 and O4 of DESIGN section 8.

Changed by [BS]: the steps stay strictly one after the other for every file that two steps share; work on files nobody
else edits at that moment runs beside them: new modules with their new test files (`T/machinery.py`, `T/replies.py`,
`T/cards.py`, `T/gatestats.py`, `T/engineer_prompt.py`) and the split of `_routed_mount` in `T/mount.py`. Each piece
writes a report `docs/handoff/typed-v2/impl/<step id>.md`. Changed by D16, D17, O10: three pieces were added after the
first plan (5b for D17, 5x for D16, and the read plan), and the read plan is no longer "a later, separate change"
outside this order: it is built after step 6 [O10] (Step R below; its grouping into "batch 3" is a merge proposal [I]).
O1 and O4 were answered before step 1, as asked above [O1, O4]; the other open points later (DESIGN 8).

## Build as actually done

Rules of every piece. From the build split [BS]: the strict step order holds for every file that two steps share;
work runs beside it only on files nobody else edits at that moment; each piece writes one report
`docs/handoff/typed-v2/impl/<step id>.md`. From the build workflow's implementer prompts, not addendum decisions
[workflow; partly also the first plan's "Do not touch"]: edit only the files the piece names as its own; nothing under
`skillopt/` outside `T/`; no ssh, no network, no paid call; no git write by an implementer (git status, diff, log and
show only; the coordinator commits [I]); never delete or weaken a test (a pin moved on purpose is named in the
report); the code runs on Python 3.11 and 3.13; precedence for the implementers: addendum coordinator sections >
`DESIGN.md` > `spec/*.md` (the precedence of DESIGN's header).

### Batch 1: commit cdf85b6 on branch research/typed-skills-v2 (18:51)

Eleven implementers in three staged rounds; typed tests 126 before, 484 after; nothing under `skillopt/` outside
`T/` changed. The commit also holds the addendum up to RP12, D16, D17, the corrected `spec/read-plan.md` and the
eleven reports.

| Id | Part of | Round (after) | Files touched (NEW = created) |
|---|---|---|---|
| 1a | Step 1: version literals, `own_root`, sealed constants, test pins | 1 | `T/__init__.py` (`VERSION`, `CONFIGURATION`, `EVIDENCE`, `is_typed_v2`, `MAX_PROGRAM_PROPOSALS`, `GATE_REPEATS`, `SCHEDULES` / `MEMORY_LOCKS` with defaults, `LEARN_WIDTHS` [D15]); `T/library.py`, `T/tasktypes.py` (version literals; loads refuse another version or module); `T/prepare.py` (`ROOT_NAME`, `own_root`, `draw_keys`, `sealed_constants`, checks in `load_manifest`); `T/reads.py` (`read_panel` calls `own_root`; consent texts); `T/readout.py` (title); `W` (`EXAMPLE_TAG` comment, docstrings); docstrings only in `T/units.py`, `T/gates.py`, `T/mount.py`, `T/embed_service.py`, `C`, `T/smoke.py`; `scripts/run_typed.py` (`own_roots` for every command; `bind_machinery` refuses a `typed` package or module); the nine existing `tests/test_typed_*.py` (scratch path, version pins); NEW `tests/test_typed2_identity.py` |
| 1m | Step 1: machinery guard | 1 | NEW `T/machinery.py` (checks 1 to 5; check 6 a stub until step 7); NEW `tests/test_typed2_machinery.py` |
| 3 | Step 3: reply reader | 1 | NEW `T/replies.py` (with the twelve sentences of O8); NEW `tests/test_typed_replies.py` |
| 2a | Step 2: card module | 1 | NEW `T/cards.py`; NEW `tests/test_typed_cards.py` |
| 5s | Step 5: gate statistics, pure [MP] | 1 | NEW `T/gatestats.py`; NEW `tests/test_typed_gate_stats.py` |
| 1b | Step 1: `Services` pass, start checks, sealed code identity, learning widths [D15] | 2 (1a, 1m) | `C` (`DEFAULT_LIMITS` with five keys, `Services` fields, `cells` at `LEARN_WIDTHS`, `container_scope_of`, `start_checks`, `_open_state`, `run`, `real_services`); `T/prepare.py` (`TYPED_CODE`, `typed_code`, `machinery_code`, sealing, `_check_code_identity`); `T/smoke.py` (`fake_services`, `synthetic_manifest`, `SMOKE_LIMITS`); `tests/test_typed_reads.py`, `tests/test_typed2_identity.py`; NEW `tests/test_typed2_services.py` |
| 4a | Step 4: engineer prompt module | 2 (3, 1a) | NEW `T/engineer_prompt.py`; NEW `tests/test_typed_engineer_prompt.py` |
| 5m | Step 5: mount identity split | 2 (1a) | `T/mount.py` (`_route`, `_routed_mount`, `_forced_record`, `mount_identity`); NEW `tests/test_typed_mount_identity.py` |
| 2b | Step 2: card integration | 3 (1b, 2a) | `W` (`screen_card`, `write_card`); `C` (the `chars` of `card_decision` and of the skill origin); `tests/test_typed_writers.py`, `tests/test_typed_chain.py` |
| 4b | Step 4: writers | 3 (2b, 4a) | `W` (engineer part: `engineer_system`, `_bounded_entry`, the hooks check in `build_procedure`, one rewrite of `_row` / `_fix_once` / `propose_programs` with `read_with_retry` and the promotion loop; `ALFWORLD_PROMPTS` and `alfworld_prompt_configuration` deleted); `tests/test_typed_writers.py` |
| 4c | Step 4: chain and smoke | 3 (4b, 5m, 5s) | `C` (`programs` over all rows, zero-call decision rows, `program_decision` base); `T/smoke.py` (`program_reply`, `DEFAULT_PROGRAM`, `ALFWORLD_PROGRAM`, the promotion bench); `tests/test_typed_chain.py`, `tests/test_typed_e2e.py` |

Codex review round 1 of batch 1: four major findings, three in `T/replies.py` (rules 3 and 7 of DESIGN 3.3) and one in
`T/readout.py` (the public entries `build`, `status`, `chain_readout` lacked the version guard). Fixes: commit e2cf9e7
on branch typed-v2-codex1-fixes (worktree `<repo-root>`): `T/replies.py`,
`T/readout.py`, `tests/test_typed_replies.py`, `tests/test_typed_readout.py` (five regression tests). Not in the main
tree at about 19:55 (DESIGN 8, still open 4).

### Batch 2: main tree, uncommitted at about 19:55 (on top of cdf85b6)

| Id | Part of | After | Files touched |
|---|---|---|---|
| 5b | D17, base card C [D17, Q23] | batch 1; before 5w | `T/__init__.py` (`MOUNT_ARMS` with `B`, `BASE_CARDS`, `BASE_CARD_DEFAULT`); `T/mount.py` (`base_text`, `system_card(..., base_card=)`, arm `B`, unknown and card-less items through `system_card(bench, '')`, also in `mount_identity`); `T/prepare.py` (`base_card_of`, sealed `base_card`); `C` (`_base_card`, `builder` passes the base, interim noise `Ba` / `Bb` and no-harm `B`, both writers get the base, the state records it); `T/reads.py` (read mounts take the manifest's base); `W` (`BASE_CARD_MEANING`, `base_card_block`, `_screen_public`, the base key in the card request and the proposal payload); `T/engineer_prompt.py` (`BASE_CARD_MEANING`); `T/smoke.py` (either base); `scripts/run_typed.py` (`--base-card` on `prepare` and `smoke`); NEW `tests/test_typed2_base.py`; `tests/test_typed_mount_identity.py`, `tests/test_typed_mount.py`, `tests/test_typed_chain.py`, `tests/test_typed_reads.py`, `tests/test_typed2_identity.py`, `tests/test_typed_cli.py`. Tests 484 to 500 |
| 5w | Step 5 wiring with B [D5, D17, O1, O5, O6, O11, O12, PG, MP] | 5b | `T/gates.py` (typed-v1 decisions dropped, `T/gatestats.py` names re-exported); `T/units.py` (rerun entries per (unit, tag), `run_unit(..., unit=)`, records moved to `rerun/`, `reruns_of`, `require_unit`); `T/reads.py` (unit names); `C` (`identity_fn`, `identities`, `gate_arm`, `plan.json`, `register_stored`, `compare`, `noise` with `B#1..3`, `no_harm` against `B@noise` returning the stored record, `outcomes`, `cards`, `programs`, the decisions, `finalize`); `T/prepare.py` (`tau_rule()` with `repeats`, `se`); `T/readout.py` (`GATE_NOISE_KEYS`, decision rows, labels folded, step table); `T/smoke.py` (`repeat_of_tag`, `fake_solve`, `identity_fn`); `W` (`revision_result`); NEW `tests/test_typed2_gate.py`; `tests/test_typed_core.py`, `tests/test_typed_units.py`, `tests/test_typed_chain.py`, `tests/test_typed_e2e.py`, `tests/test_typed_readout.py`, `tests/test_typed_writers.py`, `tests/test_typed2_base.py` (golden runs re-pinned, the 5b values kept as history), `tests/test_typed2_services.py`. Tests 500 to 512 |
| 5x | D16, shared types [D16] | 5w | in progress at about 19:55. Planned [D16 f; impl 5x plan]: `C` (members, member learn and gate units, the member comparison after the home rule, `member_harm`); `W` (member example blocks, the member sentence, the revision summary); `T/engineer_prompt.py` (member sentence and examples); `T/gatestats.py` (member verdicts, `recompute`); `T/readout.py` (related gains); NEW `tests/test_typed2_shared.py` |

The batch-2 reviewers cover 5b, 5w and 5x [D16 f].

### Read-plan core: separate worktree

Worktree `<repo-root>`, branch typed-v2-readplan-core, base 8375ecb, commit
3f7e933 (19:52). Files: NEW `T/readplan.py` (1,410 lines; imports only `T/__init__`, `T/library`, `T/units`), NEW
`tests/test_typed_readplan_core.py` (56 tests), `docs/handoff/typed-v2/impl/rp-core.md`,
`docs/handoff/typed-v2/impl/rp-core-review.md`. One adversarial review, four minor findings fixed. It touches no file
of the main tree; its five spec points are answered by RP13. It is merged into the main tree before rp-int [I].

### Batch 3: planned (not started at about 19:55); a proposal of this merge [I]

The addendum fixes only that the read plan is built after step 6 [O10; RP header of 17:29] and lists the remaining
work as "step 5 wiring, steps 6 and 7 and the read plan" [BS]; the RP decisions "do not touch Steps 1 to 7". The name
"batch 3", the ids 6s, rp-int, rp-ro and 7g, the table below and its order are this merge's proposal [I], not addendum
decisions. Proposed order: 6s, then rp-int, then rp-ro, then 7g (step 7 last, so that its `REQUIRED` scan covers all
of `T/`, `T/readplan.py` included). Whether step 7 runs before or after the read plan is open (DESIGN 8, still open
9): the spec's change list books the read plan's `REQUIRED` additions and its bound-driver lines as read-plan changes,
which fits step 7 before it. The rows below name those lines under both pieces, each with its condition. rp-ro shares
with rp-int only the `state_summary` lines of `scripts/run_typed.py`, so it can run beside rp-int if those lines go
to one of them; the spec puts this area's readout edits last on `T/readout.py`, after those of 5b, 5w, 5x and step 6
(spec 5.5).

| Id | Part of | Files (from DESIGN 3.6, 3.7, the spec's change list, and step 7) |
|---|---|---|
| 6s | Step 6: schedule and memory lock [D8, D9, D13] | `C` (`_Run`: `freeze_anchor`, `read_anchors`, `learn`, `read_step`, `learned`, `freeze`, `load_frozen`, `bind_read`; `step`, `anchors`, `reads`, `load_state`, `run`; `heavy_for`, `lock_setting`, the unit passed to `heavy`); `T/reads.py` (`_read`, `_cell_builder`: the unit to `heavy`; the reset wrap of `_from_services` as Step 6 lists it, unless the coordinator moves the wrap into the read-plan piece, DESIGN 8, still open 1); `T/prepare.py` (`schedule`, `memory_lock` sealed and checked); `scripts/run_typed.py` (`--schedule`, `--memory-lock` on `prepare`); `T/readout.py` (`status`, `_md_state`); `T/smoke.py` (`fake_services`); NEW `tests/test_typed_schedule.py`; `tests/test_typed_reads.py`, `tests/test_typed_cli.py` |
| rp-int | Read-plan integration [D9, D10, D12, RP1..RP13] | the merge of 3f7e933; `T/readplan.py` (the pass, the capture call, the replay core without the heavy lock, the R44 helpers, the `checkpoint` calls); `T/__init__.py` (re-exports of R1 [RP13]); `T/prepare.py` (`read_plan`, `read_plan_probe`, pair checks); `T/reads.py` (`open_panel`, R24; the reset wrap only if the coordinator moves it here, DESIGN 8, still open 1); `C` (state keys R5, solver settings R75, learning guard R79, `plan()`, replay child R76, stop R77, `read_classes()` R35..R39, R42, `reads(event, benches=None)`, R44 recovery, R33 d void, R46 completeness); `T/smoke.py` (smoke manifest fields, `fake_solve` `public_hash`, the pass on the practice panel, stop and resume, fake replay, kill points R92); `T/machinery.py` (`REQUIRED` additions for machinery symbols first used here, spec section 2: needed only if step 7 runs before the read plan; with 7g last, its AST scan covers them, DESIGN 8, still open 9); `tests/typed2_bound_driver.py` (`mount_identity`, the capture and T7 under `bind_machinery`, spec section 2: here only if step 7 runs before the read plan); `scripts/run_typed.py` (`prepare --read-plan`, `--read-plan-probe`, `run` / `smoke --stop-after-plan`, `smoke --resume`, `--fake-kill-at`, `plan-replay` with R47b); NEW `tests/test_typed_readplan.py`; `tests/test_typed_reads.py`, `tests/test_typed_schedule.py` or `tests/test_typed_chain.py` (T16, T17), `tests/test_typed_cli.py` (T24, kill points) |
| rp-ro | Read-plan readout [RP4, RP5, RP7] | `T/readout.py` (R63..R74, R89, R90: resolver, alias map, `_aliases`, marks with `u/i/c`, export objects, dash rule, RP4 rule, two macro columns, split-phase reference block, identical-request labels, unit times, `_project`, classes block, status); `scripts/run_typed.py` (`state_summary` read counts, R73); `tests/test_typed_readout.py` (T20) |
| 7g | Step 7: bound interpreter test and machinery guard | `T/machinery.py` (`REQUIRED` from an AST scan of `T/`; check 6 pins; the `scripts.*` modules the bound run imports [Q19, RP12]); NEW `tests/typed2_bound_driver.py` (with the read plan's `mount_identity`, capture and T7 under `bind_machinery` only when 7g runs last, a spec placement moved by this merge [I]); `tests/test_typed2_machinery.py` (the bound test and the guard cases) |

After launch, outside the batches [RP1]: NEW `T/replicate.py` (about 180 lines), the `replicate` command in
`scripts/run_typed.py` (about 25), NEW `tests/test_typed_replicate.py` (about 220, T27).

## The steps

The step texts below are the plan of the first integration; the "As built" and "Changed by" lines after each step
record what the merge changed.

## Step 1. Version, identity, services pass (DESIGN 3.5, 4.4)

- `T/__init__.py`: `VERSION`, `CONFIGURATION` (`:9-10`), `EVIDENCE` (`:63`), `is_typed_v1` (`:72`); add
  `MAX_PROGRAM_PROPOSALS = 3`, `GATE_REPEATS = 3`, `SCHEDULES`, `MEMORY_LOCKS` and their defaults. `SEED` stays.
- `T/library.py:15` `LIBRARY_VERSION`; `T/tasktypes.py` type-map version; `T/readout.py:49` follows `VERSION`.
- `T/prepare.py`: `ROOT_NAME` (`:34`); new `own_root(root)`; `prepare` (`:255`) seals `caps`, `draw_keys`,
  `machinery_code`, `provenance.typed_code`; `load_manifest` (`:293`) checks them. `SLICE_TAG` (`:39`) stays.
- `T/machinery.py` (new): `LIST`, `LIST_SHA256`, `LIST_FILES`, `REQUIRED` (names known so far), `listed`, `compare`,
  `loaded`, `require_symbols`, `check(*, real)` with checks 1 to 5; check 6 (pins) is completed in step 7.
- `C`: `Services` (`:98`) gets ALL new fields and signatures of all areas now: `cap` from the manifest,
  `machinery_code`, `container_scope`, `heavy(bench, unit=None)`, `lock_setting`, the five `limits` keys (`DEFAULT_LIMITS`, `:61`);
  `_open_state` (`:939`); `run` (`:953`) calls new `start_checks` before the ledger opens; `real_services` (`:1075`):
  `sandbox.unit_tag(chain, scope + unit)` (`:1155`), `sandbox.drain_unit(chain, scope + unit, ...)` (`:1164`).
- `T/reads.py`: `read_panel` (`:179`) calls `own_root`; message texts of `consent` (`:91`) name typed-v2, its rules
  do not change. `scripts/run_typed.py`: every command calls `own_root`; `bind_machinery` (`:35`) refuses a snapshot
  with a `typed` package. `T/smoke.py` `fake_services` (`:293`) and every fake `Services` in `tests/`: one pass.
- Tests: new `tests/test_typed2_identity.py`, `tests/test_typed2_machinery.py` (list pinned, tree equals list,
  altered file refused, extra module under the tree's `X/` refused, missing name refused, `start_checks`); version
  pins and `/tmp/typed-neutral` updated in all `tests/test_typed_*.py`.
- Run: all `tests/test_typed_*.py tests/test_typed2_*.py`.
- Accept when: no `typed-v1` literal is left in `T/` except the two draw tags and comments naming history; a
  typed-v1 root, manifest, state, library and type map are each refused by a test; the two versions get different
  container tags for the same chain and unit; every fake `Services` is built in one helper per test file.
- As built: 1a, 1m, 1b (batch 1). Changed by D15: step 1 also introduced `LEARN_WIDTHS` and sealed `widths` and
  `learn_widths` (1a: constants and sealing; 1b: use in `cells`). `machinery_code` and `provenance.typed_code` are
  sealed by 1b; `base_card` came with 5b [D17], `schedule` / `memory_lock` come with step 6, `read_plan` with the read
  plan (merge ids 6s and rp-int [I]).
  Check 6 of `machinery.check` stays a stub until step 7 [impl 1m].

## Step 2. Card length (DESIGN 3.1)

- `T/cards.py` (new, complete as in 3.1). `W`: import (`:30`), `screen_card` (`:269`), `write_card` (`:275`).
  `C`: import (`:54`), `card_decision` (`:773`, the `chars` field at `:784`).
- Tests: new `tests/test_typed_cards.py`; change `tests/test_typed_writers.py` (length cases near `:136-182`:
  3,001 becomes 4,501) and the fake card writer in `tests/test_typed_chain.py` (near `:102`).
- Run: `tests/test_typed_cards.py tests/test_typed_writers.py tests/test_typed_chain.py`.
- Accept when: 3,000 and 4,500 content characters pass and 4,501 fails; a trailing newline changes nothing; the
  first-attempt request and a content-violation retry are byte-identical to typed-v1 (golden test); `chars` is the
  content count in the attempt row, the decision and the skill.
- As built: 2a, 2b (batch 1). Changed by D17 (5b): the first-attempt card request stays byte-identical to typed-v1 only
  under `base_card = 'format'` and on ZebraLogic; under 'historical' it carries the base-card block, and the D2 limits
  count the learned text only.

## Step 3. Reply reader (DESIGN 3.3)

- `T/replies.py` (new, standalone; `W` is not edited in this step). Word the twelve open `PROBLEM_SENTENCES` (O8).
- Tests: new `tests/test_typed_replies.py`.
- Run: `tests/test_typed_replies.py`.
- Accept when: both F6 losses (`change` for `changes`; placeholder inline source beside a fenced program) are read;
  well-formed replies give the same records as the frozen reader; no fixture makes the reader raise or execute text;
  two different programs for one change are a problem, never a guess.
- As built: 3 (batch 1), with the extra step A2' of rule 7; O8 done (the twelve sentences pinned). The Codex review
  round 1 changed rules 3 and 7 (e2cf9e7, not in the main tree at about 19:55; DESIGN 3.3).

## Step 4. Engineer prompt and promotion (DESIGN 3.2)

- `T/engineer_prompt.py` (new). `W`: delete `ALFWORLD_PROMPTS` (`:40`), `alfworld_prompt_configuration` (`:299`),
  `engineer_system` (`:310`); `_bounded_entry` (`:359`); `build_procedure` (`:396`, hooks check); ONE rewrite of
  `_row` (`:436`), `_fix_once` (`:442`), `propose_programs` (`:469`) with `replies.read_with_retry`, the fix request
  of 3.2 and the promotion loop. `C`: `programs` (`:841`) iterates over all rows, `program_decision` base (`:889`);
  the gate lines inside stay as they are until step 5. `T/smoke.py`: `SMOKE_LIMITS` (`:28`), `DEFAULT_PROGRAM`
  (`:36`) and the scripted writer replies (`:170`) in the new reply format.
- Tests: new `tests/test_typed_engineer_prompt.py`; change `tests/test_typed_writers.py` (engineer cases near
  `:237-350`), `tests/test_typed_chain.py` (fake writer near `:105`, program cases), `tests/test_typed_e2e.py`.
- Run: `tests/test_typed_engineer_prompt.py tests/test_typed_replies.py tests/test_typed_writers.py
  tests/test_typed_chain.py tests/test_typed_e2e.py`.
- Accept when: each of the 22 rule rows has a legal and an illegal example checked by the real `policy.check`; a
  dropped row never reaches a gate unit and a promoted third row does; at most 5 writer calls per unit attempt; an
  interruption inside the loop keeps every send in the calls file; smoke or gate failures promote nothing; the
  frozen `policy.check` call is unchanged.
- As built: 4a, 4b, 4c (batch 1). O7 binds the typed-side hooks check before the frozen `policy.check`, whose call is
  unchanged [O7]; 4b built it after it (source, policy, hooks, structure) [impl 4b]. This deviates from O7 until the
  coordinator either confirms O7 (4b moves the check) or corrects O7's order (DESIGN 8, still open 3). Changed by
  D17 (5b): the proposal payload carries the base-card block; by D16 (5x): both writers carry member examples. The
  ten system texts and `PINS` are unchanged by 5b.

## Step 5. Gate (DESIGN 3.4, 4.1)

- `T/gates.py`: new helpers and new bodies of `card_decision`, `program_decision`, `no_harm_decision`; keep
  `paired_statistics`, `split_pairs`, `noise_threshold`. `T/mount.py`: split `_routed_mount` (`:190`) into `_route`
  and `mount_identity` (no request may change: golden test of mount records). `T/units.py`: rerun entries per
  (unit, tag), consumed on re-run (`:116-117`, `mark_infrastructure_reruns` `:301`, `run_unit` `:324`); the re-run
  predicate at `:316` stays. `C`: `cells` (`:477`), new `gate_arm`, `identities`, `noise` (`:655`), `no_harm`
  (`:712`), `outcomes` (`:726`), `cards` / `card_decision` (`:731, :773`), `programs` / `program_decision`
  (`:841, :886`), `finalize` (`:917`). `T/prepare.py` `tau_rule`. `T/readout.py` (`:61, 153, 174, 219, 707`).
  `T/smoke.py` `fake_solve` (`:263`). `W` `revision_result` (`:222`) reads the new decision fields.
- Tests: gate cases of DESIGN section 5 in `tests/test_typed_core.py`, `tests/test_typed_chain.py`,
  `tests/test_typed_e2e.py`, `tests/test_typed_readout.py`, `tests/test_typed_mount.py`.
- Run: all `tests/test_typed_*.py tests/test_typed2_*.py`.
- Accept when: the integer forms equal the D5 formulas in a property test; every decision is reproduced by
  `gates.recompute` from its stored record; no unit sends more than R requests per item and arm except archived
  infrastructure re-runs, which are counted; a model-side unknown cell is never re-run; shared arms run no cell and
  `plan.json` is identical after a resume; `no_harm` returns the stored record; read units still run once per item.
- As built: 5s and 5m (batch 1, beside the other steps [BS]), then 5b (D17) and 5w (batch 2), then 5x (D16). Changed
  by [MP]: the new helpers and decision bodies live in `T/gatestats.py`; `T/gates.py` re-exports them and keeps
  `paired_statistics`, `split_pairs`, `noise_threshold`. Changed by D17: wherever this step says C0 on the learning
  side, B is used: noise `B#1..3`, the no-harm baseline `B@noise`, the first arm of the sharing search. Changed by O11:
  the property test covers binary scores only. Added by 5w: the pause `gate_plan_changed`; `noise_uncalibrated` and
  `MIN_NOISE_PAIRS_FRACTION` removed.
- Step 5b (D17), accept when [impl 5b]: under 'format' every request is byte-identical to batch 1 (golden; cell tags
  differ only by the label B); under 'historical' every B cell sends C and every learned cell C or `T + CARD_JOIN +
  C`; unknown and card-less items mount C [Q23]; C0 and C read mounts unchanged; the base is sealed, a missing or
  unknown value refused, a resume with another base refused.
- Step 5x (D16), accept when [D16; impl 5x plan]: a type with one bench gives every request, unit and cell of 5w
  (golden); for a shared type the member units run, a member regression rejects with `member_harm` naming the bench,
  the member baseline after an accepted card is that card's member runs, `recompute` reproduces the member verdicts,
  the readout shows related gains, and no gate item reaches a writer.

## Step 6. Schedule and memory lock (DESIGN 3.6)

- `C`: `_Run` gains `freeze_anchor`, `read_anchors`, `learn`, `read_step`, `learned`, `freeze`, `load_frozen`,
  `bind_read`; `step` (`:637`), `anchors` (`:624`), `reads` (`:589`), `load_state` (`:451`), `run` (`:953`); new
  `heavy_for`, used at `:1131`. `T/reads.py` (`_read` `:253`, `_cell_builder` `:324`): pass the unit to `heavy`;
  `_from_services` (`:229-230`): with `unit_shared` wrap the ALFWorld reset with `v218_lock.call` (addendum D13).
  `T/prepare.py` (`prepare`, `load_manifest`): `schedule`, `memory_lock`. `scripts/run_typed.py`: `--schedule`,
  `--memory-lock` on `prepare`. `T/readout.py` `status` (`:645`), `_md_state` (`:689`).
- Tests: new `tests/test_typed_schedule.py`; change `tests/test_typed_reads.py`, `tests/test_typed_cli.py`.
- Run: all `tests/test_typed_*.py tests/test_typed2_*.py`.
- Accept when: with default fields the order of units and every request equal those after step 5; `learn_first`
  sends the same requests in the other order; a changed frozen file pauses; the default lock call is unchanged;
  with `unit_shared` the read-unit reset runs inside the lock, with `per_cell_plain` it stays bare.
- Planned as 6s (merge id, batch 3 [I]). Changed by D9: the real run and the smoke use `learn_first`; under
  `read_plan = economy` the read part of `learn_first` is replaced by the read plan (Step R), so 6s builds
  `learn_first` with `full`, and R79's learning guard comes with the read plan. Open (DESIGN 8, still open 1): R24
  (spec) wants the reset wrap and the extraction of `reads.open_panel` in one change of `T/reads.py`; O10 says only
  that the read plan shares `T/reads.py` with the D13 wrap, and the RP decisions do not touch Steps 1 to 7 [RP header
  of 17:29]. So this step keeps the wrap as listed above unless the coordinator moves it into the read-plan piece;
  it does not take the `open_panel` extraction, a read-plan change. D15 needs nothing more here (done in 1a and 1b).
  The phase names are `learn` and `read` (DESIGN 3.6).

## Step R. Economy read plan (DESIGN 3.7; spec/read-plan.md; after step 6 [O10])

The name "Step R" and the split into rp-int and rp-ro are this merge's [I]; the RP decisions bind the spec and do not
touch Steps 1 to 7 [RP header of 17:29].

- Core (done): `T/readplan.py` and `tests/test_typed_readplan_core.py` (rp-core, commit 3f7e933, separate worktree).
  Merged into the main tree before rp-int [I].
- rp-int: the files of the batch-3 table. Accept when: T1..T6, T8..T12, T16..T19, T21..T26 pass; `full` is unchanged
  (T17: `learn_first` + `full` gives step 6's units, order and request hashes; the existing 35-unit tests pass); a
  fresh unit under `economy` equals the same unit under `full` (T18); the pass sends nothing and leaves the ledger
  byte-equal (T11); the pass mounts with the loaded frozen objects [RP13]; the fake smoke S2 (a) to (c) passes, the
  three kill points included.
- rp-ro: T20 passes: the unpatched typed-v1 `_open` yields no number for any same-class pair; every table and export
  carries the marks; a `full` root renders as today.
- Run: all `tests/test_typed_*.py tests/test_typed2_*.py`.
- After launch, not part of batch 3: the `replicate` command (DESIGN 3.7 E; T27).

## Step 7. Bound interpreter test and machinery guard (DESIGN 3.5, 5)

- Complete `machinery.REQUIRED` from an AST scan of `T/` (every attribute read on an imported frozen module) and
  check 6: compute and pin `engineer_prompt.PINS`, `cards.COPIED_SOURCE_SHA256`, the reply and retry texts.
- `tests/typed2_bound_driver.py` (new child script) and the bound test in
  `tests/test_typed2_machinery.py`: stand-in snapshot from the 564 listed files plus the 64 data files, fresh
  interpreter, `bind_machinery`, import of every `T/` module, `machinery.check(real=True)`, ten prompts rendered,
  one card screened, one reply read; guard cases of DESIGN section 5.
- Run: all `tests/test_typed_*.py tests/test_typed2_*.py`, then the complete local suite once.
- Accept when: the guard refuses each altered case; no `skillopt` module outside `typed` is loaded from this tree
  in the child; `git status` shows changes only under `T/`, `scripts/`, `tests/`, `docs/`; the tree still equals the
  564-row list. Handed to operations, not done locally: the data list from the snapshot on dl
  (`DATA_LIST_SHA256`), the Linux suite run alone, the bound driver against the real snapshot (Python 3.11), the cap
  projection, `prepare` (with `--memory-lock unit_shared` for smoke and run, D13), the memory sampler, smoke.
- Planned as 7g (merge id, batch 3 [I]); "last" is this merge's proposal, and whether step 7 runs before or after the
  read plan is open (DESIGN 8, still open 9). Added by Q19 [RP12], the one Step 7 change the addendum itself makes:
  the machinery check also pins the `scripts.*` modules the bound run imports, at least `scripts/weak_solver_probe.py`.
  Spec placement, not an addendum decision: `spec/read-plan.md` section 2 books, as read-plan changes, +40 lines in
  `tests/typed2_bound_driver.py` (`mount_identity`, the capture and T7 under `bind_machinery`; T7 must pass before
  the smoke, R14) and any `REQUIRED` additions for symbols the read plan first uses; step 7 writes them only if it
  runs after the read plan. Changed by F11: the data list is done and `DATA_LIST_SHA256` pinned; changed by F12: the
  cap projection is done. Still handed to operations: the Linux suite run alone, the bound driver against the real
  snapshot (Python 3.11), `prepare --schedule learn_first --read-plan economy --memory-lock unit_shared --base-card
  historical`, the memory sampler, the smoke (DESIGN 6).

## Do not touch

- Any file under `skillopt/` outside `skillopt/execskill/typed/` (the 564 listed `.py` files and the 64 data
  files): `X/policy.py`, `X/engineer_reader.py`, `X/v225_cards.py`, `X/package.py`, `X/sandbox/*`,
  `skillopt/coevo5/*` and all others. They are read and called, never edited; a new module under this tree's `X/`
  is refused by the guard.
- The static screen call `policy.check(source, version=POLICY_VERSION)`, the sandbox, the consent rules and the
  sealing of read units. The two static-screen relaxations are deferred (DESIGN section 1).
- The draw keys `SEED`, `SLICE_TAG`, `EXAMPLE_TAG`; the bench order, slice sizes, models, read arms, `CARD_ROUNDS`,
  `CARD_ATTEMPTS`, the describer and selection requests, the first-attempt card request.
- `docs/handoff/typed-v1/` and the typed-v1 tree, root, records and ops helpers; `DECISIONS.md` and the sections in
  `spec/`; `machinery-main-v10.sha256`.
- `.env` files, credential files, environment variables with keys: never read, printed or searched.
- No ssh, no paid call, no git commit or push from an implementation step; the read path beyond what steps 1 and 6
  name (the economy read plan of the addendum D9 to D12 is a later, separate change).
- Changed by D17: "the first-attempt card request" is untouched only under `base_card = 'format'`; D17 has precedence
  and adds the base-card block under 'historical' [impl 5b, choice 6].
- Changed by O10 and [BS]: "the read path beyond what steps 1 and 6 name (the economy read plan ... is a later,
  separate change)" is now built after step 6 (Step R; "batch 3" is a merge proposal [I]). The RP decisions do not
  touch Steps 1 to 7 [RP header of 17:29]. The read plan's own limits: `T/mount.py` gets nothing from it,
  `T/reads.py` only the extraction of `open_panel`, `C` no change to `read_one`, `read_event`, `confirm` or the
  learning code apart from R79's guard (spec section 2).
- Added [RP1]: no piece writes into the typed-v1 root; only the post-read `replicate` command reads it, after launch.
