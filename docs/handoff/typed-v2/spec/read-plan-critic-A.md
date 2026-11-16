# read-plan.md, critic A (sealing, identity, false equality)

2026-11-12. Target: `docs/handoff/typed-v2/spec/read-plan.md` (draft for D9-D12). Method: default "this is wrong",
then the real code. `T/` = `skillopt/execskill/typed/`, `X/` = `skillopt/execskill/`. Marks: [V] = opened and read at
the given file:line in this tree; [I] = inferred, not read. Severity: blocker / must-fix / minor.

STATUS: FINAL for the points checked. 17 findings (1 blocker for the carry, 12 must-fix, 4 minor). Open points are
in "NOT DONE" at the end. No code, test or other spec file was edited.

## Short answers to the five questions

1. False equality: A1, A2, A3, A12, A13, A15. The request side of the identity (R9) is sound IF it is computed by
   the real mount code; the draft computes it by a copy (A1). Scoring and solver settings are not covered for the
   carry (A3, A15). The readout would manufacture equality in its statistics (A13).
2. False difference: A4 (kills every carry), A5 (kills the plan on resume or replay), A15 (kills chain G carries).
3. Sealing: A7 (order not enforced), A11 (carry and replay CLIs), A10 (open plan, checked, minor).
4. Consent, registry, qualification: content and write-once hold [V]; an interrupted qualification inside the
   pass has no working recovery path as the draft is written (A9).
5. "Every (event, bench) has cells": A6, A13, A14, A17; the existing tests assert 35 units and 35 mirrors (A6).

## Findings

**A1. (must-fix, false equality by construction) The identity is a second implementation of the mount, compared
with the real mount only on the representative.**
Evidence: the draft computes identities with a new `mount.identity(...)` (R16) and compares with the real mount only
after the representative was read (R41). A non-representative member is never mounted for real, so a difference
between the copy and the real mount for that member is never seen. Fixture test T2 does not cover real panels.
The real per-item mount is `mount.mount` -> `_routed_mount` -> `_select` [V T/mount.py:154-177, :190-238, :266-291].
R17's reason for not calling it ("requires a selector and calls it") does not hold: the selector is called only at
[V T/mount.py:274]; a selector that records the request and returns a not-ok receipt makes `_select` store the first
request hash in `attempts[0]` [V T/mount.py:275], choose nothing [V :286-288] and return. `mount.mount` then returns
`system_card_sha256` [V :176] and `programs_offered` [V :220] under the MEMBER's library with zero sends.
The copy is already incomplete on paper: R16's helper list has no `_signature(view, strict=routed)`
[V T/mount.py:166, :180-187: a routed arm RAISES on an unregistered view shape, arm C0 does not] and not the vector
requirement [V T/mount.py:194-196]. An item for which the real arm-F mount raises can get the C0 identity from the
copy and be aliased with C0.
Correction: no parallel implementation. The pass calls the real `mount.mount` for every (event, item) with a capture
selector (a plain function, no client, no recorder file) and builds the identity from the returned record. It keeps
hashes only: the selection record holds `raw_excerpt` and `failure = str(error)` [V T/mount.py:284, :289-291] and
must be dropped. Any exception of the real mount for a member makes that (event, bench) its own class (read fresh),
recorded with a fixed reason code. Test: the capture selector sends nothing; the identity of a member equals the
stored mount fields when that member is read fresh.

**A2. (must-fix, false equality) The package label `typed/<unit>` is event-specific and it does reach the sandbox.**
Evidence: a read cell calls `solve` without `step` [V T/reads.py:342-345], so `label = step_label('typed/' + unit)`
and `package = package_for(mounted['enabled'], step=label, ...)` [V T/mount.py:353-354]. The label is a package field
and is inside the package hash [V X/package.py:51, :328-338]. The load request sent into the container carries
`package_sha256` [V X/sandbox/client.py:434]; the worker reads it and echoes it in the load reply, and does not put
it into its state (`state.update(loaded=loaded, limits=limits)`) [V X/sandbox/worker.py:698, :731-733].
So a label-dependent value crosses the container boundary for every item with an enabled program. That it stops
there is [I]: `handle_call`, the hook process and `worker_v222.py` were not read, and which worker file the bound
machinery uses is [I]. The solver request text does not use `package.step` or `package.sha256` [V by grep of
X/solver.py; only `package.evidence` at :539, :557]. The draft's two guards do not close the gap: R41 compares mount
records, which hold no hook input (R41 field list); T7 as drafted runs on this tree's `X/`, while a bound run loads
`X/` from the frozen snapshot (D1) [I that the two copies differ].
Correction: T7 becomes a hard precondition, run against the BOUND machinery (not this tree's copy): two packages that
differ only in `step` give byte-identical requests and byte-identical hook inputs and outputs. Until it passes, an
item whose `programs` list is not empty carries the event in its identity (it never aliases across events). The
receipt of `prepare` records the result.

**A3. (must-fix, false equality for the carry) Scoring is in no identity and in no carry check.**
Evidence: a cell's score comes from `_sheet_score(...)` and `judge.judge(bench, item['public'], item['private'],
prediction, recorded.receipts, runtime=bench_rt, score=score)` [V T/mount.py:377-381]; the row stores
`judge_version` [V T/mount.py:414]. Inside one run the scorer is one constant and no arm or event reaches it
[V T/mount.py:366-368, :377-381], so aliasing inside the run is safe. The carry is different: carried cells were
scored by typed-v1 code; K1-K11 compare requests and manifest fields, not the scoring code, not `judge_version`.
Addendum O1 changes how a model-side unknown is counted in typed-v2.
Correction: K12 per cell `judge_version` equal to this tree's value; K13 the typed scoring functions (`solve`,
`_sheet_score`, `_judged`, `_failed`, `_costs` in T/mount.py) byte-equal to typed-v1's, or a written list of the
differences with the fields the typed-v2 readout re-derives from the cell. The receipt names exactly what was
compared ("scoring equality: machinery list + judge version + typed scoring diff").

**A4. (blocker for D11, false difference, fails safe) K7 compares the manifest field `evidence`, which typed-v2
changes on purpose.**
Evidence: `prepare` writes `'evidence': EVIDENCE[mode]` [V T/prepare.py:271]; today `EVIDENCE = {'run':
'typed_v1_real_run', 'smoke': 'typed_v1_smoke', ...}` [V T/__init__.py:63]; identity.md:21 and :146 rename both to
`typed_v2_*`. K7's `EQUAL_FIELDS` contains `evidence`. No carry can pass. D11 silently becomes "every C fresh", and
smoke step S5 (carried path) can not pass either. Second field: `machinery_manifest` stores `path`,
`record_sha256` and `evidence` [V T/prepare.py:277-278]; a typed-v2 root prepared against another manifest file path
fails K7 for a reason that is not a request difference [I that the path differs].
Correction: compare `route_b_evidence` and the content fields (`record_sha256` of the machinery manifest, not its
path). Move `evidence` to the "different by construction, recorded only" list. A test builds a typed-v1 style and a
typed-v2 style manifest and requires K7 to pass.

**A5. (must-fix, false difference that voids the plan) Byte equality of recomputed sealed files (R32 a, R45 P2/P3,
R47).**
Evidence: the sealed identity file holds `view_sha256` and the un-hashed fields `type`, `unknown_reason`,
`card_skill`, `offered` (3.3). All depend on values recomputed in every process: the routing view
[V T/reads.py:164-167], the embedder batch [V T/reads.py:170-175], the ALFWorld resets [V T/reads.py:229-230].
A resume or a replay in another process must reproduce every byte, else `read_plan_failed` / `read_plan_changed`.
R30 runs the embedder twice inside ONE pass; it says nothing about a later process. The vectors come from a
subprocess in another venv [V T/tasktypes.py:90-102] and the type is decided by a strict float comparison
`distance > src['threshold']` [V T/tasktypes.py:231]. One float that moves one item across that threshold, or one
changed preview byte, voids the plan after paid reads were made under it. That the embedder is bit-stable across
processes is [I]; nobody measured it.
Second point: the pass computes views and vectors once per bench (R26), every read unit computes its own
[V T/reads.py:268-279 as cited by R24]. Only the representative's are ever compared (R41).
Correction: the first pass stores views and vectors in the sealed directory; resume, replay and the fresh read of a
representative load them from there (hash checked). Equality is required on the identity lists and the class table
only. A changed descriptive field is a recorded difference, not a void plan. Embedder determinism across processes
is then a measured fact (replay prints the count of changed vectors), not a precondition.

**A6. (must-fix, D10 f can become unreachable; false "read done") Alias pairs get the same done marker as fresh
reads.**
Evidence: R39 and 3.6 mark an alias pair `read-<M>-<bench>` in `done_units`. `reads()` skips every bench whose marker
is present [V T/chain.py:594]. `_read_complete` accepts any dict without `stop_reason` / `missing_cells` /
`status` [V T/chain.py:248-251], so the alias state entry counts as a complete read. R44 says "the plan is void ...
every UNSETTLED pair is read fresh": pairs already settled as aliases keep a marker that rests on a plan which
failed its own replay. The draft does not say what they become. Either they stay valid (an equality claim resting
on a plan nobody can reproduce), or they are invalid: R46 needs "a valid alias record", a record is valid only
against the plan (R44), so the chain pauses with `read_plan_incomplete` and no path reads the pair. Open consumers count
markers: `done units: len(...)` [V T/readout.py:696], `state_summary` [V scripts/run_typed.py:191-199]; a monitor that
counts `read-` markers reports 35 reads done when fewer were made [I for scripts outside the tree]. Existing tests
pin the full shape: 35 events in order, 35 unit directories, 35 mirrors, exact `done_units`
[V tests/test_typed_chain.py:190-195, :247, :673, :709-712; tests/test_typed_e2e.py:199-204].
Correction: a separate marker `alias-<event>-<bench>` (and `carried-<event>-<bench>`), never `read-...`. A pair is
settled by a complete mirror OR a verified alias record. A void plan or an invalid record removes the alias marker
in the same step and the pair is read fresh in the same resume. Tests: void plan after two aliases -> both pairs
read fresh, chain completes; the 35-unit tests keep running under `read_plan = full`, named so.

**A7. (must-fix, sealing order) Nothing makes learning impossible after the planning pass.**
Evidence: today `step(k, bench)` re-runs its body whenever `step-<k>` is not in `done_units`; there is no phase
[V T/chain.py:637-653, :978-983]. `anchors` rewrites `s0/library.json` and `s0/typemap.json` when missing
[V T/chain.py:626-630]. Schedule-lock keeps this: on resume "the same loop is re-entered" and a step without its
receipt "re-runs its body ... and writes the missing files" [V spec/schedule-lock.md:56-59]; under `learn_first`
the loop is `learn(1..5)` and then the reads [V spec/schedule-lock.md:166], so `learn(1..5)` is evaluated on every
resume of the read phase; `learn(k)` has no phase condition, it SETS the phase [V spec/schedule-lock.md:163].
The draft checks receipts at the pass (R33) and at a resume with a BOUND plan (R44); the order of R44 and the loop
is not stated. At P2 and P3 (sealed identity files exist, panels were
opened, plan not bound) nothing stops a resume from re-entering `learn(k)` when a receipt is missing or unreadable.
The plan's own sealing argument (3.2: "No learner can read them: under learn_first all learning has ended before the
pass runs") depends on this order.
Correction: `learn(k)` is a hard error, not a pause a recovery can pass, when any of these holds: `read-plan` in
`done_units`; the sealed plan directory exists; any read unit directory exists; `state['phase'] == 'reading'`. The
pass sets `state['phase'] = 'reading'` and `current_unit = 'read-plan'` and saves the state BEFORE the consent check
and the first `panel_tasks` call. A missing receipt in phase `reading` pauses; it never re-runs a step. Test: resume
with `s3/frozen.json` removed at P2, P3 and P5 -> zero role calls, zero writes under `s3/`.

**A8. (minor, checked) The sealed name `test-read-plan` shares the prefix of read units.**
Evidence: `parse_read_name('test-read-plan')` is None because `plan` is no event [V T/readout.py:109-117], so
`read_units_of` ignores the directory [V T/readout.py:340-351]. `_is_read_unit_name` is a substring test on ledger
unit names [V T/readout.py:135-150]; a ledger unit named `...test-read-plan` would be counted as a read unit, but the
pass charges nothing (R33). No defect today.
Correction: one test that fixes both facts; a sentence in R33: "the pass never creates a ledger unit".

**A9. (must-fix) A qualification pause raised inside the pass has no working recovery as the draft is written.**
Evidence, what holds: the registry entry has no label [V T/reads.py:133-134]; `_registry` is write-once under an
exclusive lock and a later caller must present an equal entry [V X/evaluation.py:243-252]; the qualification
pointer is written once and later callers verify its hash [V X/evaluation.py:255-299]; `TestAccess` keeps the label
in memory only [V coevo5/data.py:232-239]. So content is the same whoever opens first.
Evidence, what breaks: (i) R33 says "any other error that prevents writing the plan pauses with `read_plan_failed`".
The recovery forwarding binds only when the pause DETAIL contains `qualification_paused` [V T/chain.py:383], and
that detail exists only when the machinery `Pause` reaches the generic handler, which writes
`_pause_detail(error)` = class name + kind [V T/chain.py:254-258, :988-989]. A pass that wraps the error loses the
detail. (ii) Without an owner `recovery.json` INSIDE the attempt directory `_next_attempt` returns None for ever
[V coevo5/evaluation.py:173-187] and every resume of either chain raises the same pause [V X/evaluation.py:270].
A process killed inside the qualification leaves exactly this state. (iii) The pass is not free of side effects:
when no pointer exists `_sheet_qualification` creates an attempt and runs the qualification with the native pool
and workers [V T/reads.py:152-160; X/evaluation.py:255-299]. "The pass charges nothing" (R33) is true for tokens
only. (iv) The pass opens all five panels before any read; a half-finished pass leaves registry entries and maybe a
qualification attempt with no read unit behind them. Same files as typed-v1, but a resume must find equal panels
(`_registry` requires an equal entry) [V X/evaluation.py:243-252]. Note: a read unit stops the ledger on an
exception [V T/chain.py:576-587]; the pass has no ledger unit, so its pause record is the only trace.
Correction: R33 re-raises the machinery `Pause` and every stop class unchanged; `read_plan_failed` is for the
pass's own errors only. The pass runs inside the same `try` as the reads, with `current_unit = 'read-plan'`.
T12 becomes mandatory and uses the real `Pause` class: qualification fails in the pass -> pause detail contains
`qualification_paused` -> `recover` forwards `recovery.json` into the attempt -> the next resume qualifies and
writes the plan. A second test kills the pass after two registry entries: the resume writes no second entry and
the same plan. Open the panels in chain order and write nothing sealed before all five are open.

**A10. (minor, sealing, checked) Open plan and alias record.**
The open plan holds hash commitments (`identity_list_sha256`, `first_request_list_sha256`, `item_set_sha256`) and
panel-level routing counts (3.2). The open mirror of typed-v1 already holds mount counts and
`aggregate_sha256` [V T/reads.py:456-473], so `representative_aggregate_sha256` in the alias record (3.4) adds no new
exposure. The sealed aggregate holds item ids and request hash lists [V T/reads.py:446-450], so its open hash can not
be guessed from the pass counts. Two conditions keep this harmless: A7 (order) and a closed vocabulary for every `reason` /
`fallback` field. Correction: reasons are constants from one tuple in the code, never `str(error)`, as
`_pause_detail` does [V T/chain.py:254-258]; a test greps the plan, alias records and state for item ids.

**A11. (must-fix, sealing of the two new CLIs) The carry and the replay handle full test prompts, replies and
correctness outside the chain's exception handling.**
Evidence: a typed-v1 cell file holds `sends` with `system`, `user` and the receipt `response`
[V T/units.py:213-222, :33-34; T/mount.py:428-429; T/reads.py:363] and `reply`, `output`, `output_excerpt`,
`correct`, `score` [V T/mount.py:403-416]. The carry parses and copies these files (K5, K6, R54). The chain protects
itself by `except Exception -> pause(type(error).__name__)` [V T/chain.py:988-989]; a new CLI (`carry`, R47
`plan-replay`) has no such handler unless written. An uncaught `KeyError(item_id)` or a `require(...)` text that
quotes a value prints test content to the terminal and to the ops log.
Correction: both CLIs catch everything at the top and print the class name and a fixed reason code only. The carry
reads named fields only (`request_sha256`, `unit`, `event`, `judge_version`, per-send receipt keys of A15). Tests
grep stdout, stderr, the receipt, the refusal record and `state.json` for item ids, texts and scores, including a
case with a corrupt cell file.

**A12. (must-fix, false equality) R41 can pass on cells that never sent, and it does not cover the view.**
Evidence: R41 says "a cell without a send cannot occur in a complete unit". That holds for a cell that raises
OUTSIDE the shell (it is `unsubmitted`, among the missing cells) [V T/reads.py:434-435]. It does not hold inside the
shell: every non-stop exception there becomes a RECORDED failed cell, not a pause [V T/mount.py:369-372], counted
under `configuration_errors` / `infrastructure_unknown` [V T/reads.py:443-444]; the ALFWorld view mismatch is one
such error [V X/solver.py:838-840; that it is raised before the first request is I]. The unit is complete when
`stop_reason is None and missing_cells == 0` [V T/reads.py:461; T/chain.py:248-251]. The mount record of such a cell was computed before the solve, so its mount
keys still equal the plan. The stored mount keys hold no view hash and no vector [V T/reads.py:47-48], and R19b
(first-request capture for S events) is only "recommended". A representative with infrastructure failures passes
R41, and its failures are multiplied to every member of its class.
Correction: R19b is mandatory wherever it is zero-call. R41 requires per item at least one send whose
`request_sha256[0]` equals the planned hash where one exists, and adds the view hash of the view the cell really
used. A representative whose mirror shows `infrastructure_unknown`, `configuration_errors` or `unsubmitted` above 0
writes no alias until the owner rule for that case is written in the spec (default: R42).

**A13. (must-fix, false equality in the statistics) R64 hands the representative's cells to the alias event.**
Evidence: R64: "`_load_read_unit` returns, for an alias pair, the representative's unit". Existing functions then
see two events with identical cells. `_paired` returns mean 0.0, 0 better, 0 worse [V T/readout.py:412-425].
`_same_request_noise` counts every item as an identical request with zero flips: a zero-noise estimate
[V T/readout.py:444-454]. `_open_mount_check` compares the representative's skills with the alias event's own step
library [V T/readout.py:545-563]. R66-R70 patch the functions one by one; every function missed, and every consumer
outside the tree (dashboard generators, ops scripts) [I], prints "0 better / 0 worse" as a measurement.
Correction: an alias is absence plus a pointer. No cell is ever placed under an alias event's key; `by_bench` holds
fresh units only. The resolver maps an event to its representative for value tables and refuses a pair of one
class. Unpatched code then gets None, which the existing functions already tolerate
[V T/readout.py:428-441, :444-447, :457-480]. Test: an economy fixture run through the UNPATCHED typed-v1 functions
gives None for every same-class pair and never a zero.

**A14. (minor) R65 merges alias records into `_mirrors`; the closed mount check then misreads them.**
Evidence: `_closed_mount_check` walks every mirror whose name parses and needs a key naming typed / mount / routing /
fraction / selection [V T/readout.py:285-306]. The alias record (3.4) has no such key. Result: `all_present` false
for every economy run, or the alias pairs dropped without a word if their names do not parse
[V for the code; which branch applies depends on R65's naming, I].
Correction: alias records stay out of `_mirrors`. The closed report lists alias pairs in their own block; the closed
mount check counts fresh units only and says so.

**A15. (must-fix, carry: false equality and false difference) K10 checks solver settings on the first call of the
chain only, and fails chain G for a harmless reason.**
Evidence: request hashes cover system and user text only [V T/units.py:213; T/mount.py:309]. Model, token bound
and thinking are not in them. K10 (ii) reads `confirm.json`, which records the FIRST call of the run and is not
repeated on resume [V T/chain.py:536-538]. Every cell receipt stores `returned_model` and `reasoning_chars`
[V T/units.py:33-34; T/mount.py:319] and every send stores `charge_bound` [V T/units.py:213-214]. A typed-v1 C cell
answered with reasoning (the 11/06 drift class) or under another token bound would be carried as equal.
False difference: K10 (ii) demands `reasoning_chars == 0`, but chain G has no reasoning check (`'reasoning': None
if chain == 'G'`) [V T/chain.py:216-218] and stores whatever the receipt gave [V T/chain.py:555]; equality of
`returned_model` is stricter than the run's own echo-set rule [V T/chain.py:199-207].
Correction: K10 per send of every carried cell: `returned_model` in the destination echo set; `reasoning_chars`
0 or absent for chain D; `charge_bound` equal to the typed-v2 bound of the bench. Confirm files are compared through
`checks` only, per chain.

**A16. (minor) `constants_sha256` claims more than it can hash.**
Evidence: R32 (c) hashes "worker options", but `services.worker_options` holds no sandbox `limits` and no pools;
the factory adds `limits` and the unit tag later [V T/chain.py:1116-1118, :1151-1159]. The solver client settings
are built at process start from frozen code and credential files and are in no record [V T/chain.py:1017-1029,
:1101-1102].
Correction: state that inside one run these follow from the manifest hash and the frozen code (already bound), list
the hashed keys by name, and do not use `constants_sha256` as proof of equal solver settings in the carry (A15).

**A17. (must-fix, crash) R64 scans `carried/typed-v1/` with `read_units_of`, which refuses two units for one pair.**
Evidence: `require(parsed not in found, 'Two read units for one event and bench: ...')`
[V T/readout.py:349]. The draft plans exactly that case twice: P10 (a fresh C unit and a carried C shown as a
replicate) and R69 (a carried C0 replicate beside the always-fresh C0).
Correction: carried units are loaded by their own function into their own map (`('typed-v1', event, bench)`); they
never enter `read_units_of`. Test: a root with a fresh and a carried unit of one pair renders.

## Checked, no defect found

- No call transform exists on the read path: nobody passes `transform` [V grep T/*.py; T/reads.py:222-226].
- The arm and the event do not reach the solver or the judge [V T/mount.py:366-368, :377-381].
- A read cell passes no step-specific value except the label [V T/reads.py:324-348].
- The ALFWorld view is inside `item['public']`, so inside `public_sha256` [V X/evaluation.py:524-537].
- Exit codes use `complete` and `paused` only [V scripts/run_typed.py:177-190, by grep].
- The consent is read, never written, by the pass: `panel_tasks` checks it before `TestAccess` [V T/reads.py:126,
  :131]; its six fields do not change (spec/identity.md:97-101). The open question of identity.md (a copied typed-v1
  consent passes) is not made worse by this draft.
- The registry and the qualification pointer are write-once under exclusive locks, so two chains entering the pass
  at the same time create each exactly once [V X/evaluation.py:243-252, :255-299].
- The smoke uses `practice-read-plan`, which keeps the "no path with test" property of the fixture runs
  [V draft R25, R32 a; tests/test_typed_chain.py:709].

## NOT DONE

- T/library.py not read. T/tasktypes.py: only `embed_texts` :90-102 and `assign` :221-235 seen; embedder
  determinism across processes is not measured (A5 rests on [I]).
- X/sandbox: `handle_call`, the hook process and `worker_v222.py` not read; which worker the bound machinery uses
  (A2).
- `route_b_manifest.limits_of`, `qualify.qualify`, `data.test_panel` bodies; the v221 qualification branch.
- T/smoke.py; the bodies of scripts/run_typed.py (grep only).
- The four test files were grepped for `done_units` and 35 only, not read.
- Ops helpers and dashboard generators outside the tree (A6, A13 consumers are [I]).
- Where exactly the ALFWorld view mismatch is raised relative to the first request (A12).
- The draft's sections 1.E (R48-R62 other than K5-K11) and 4 (tests) were read once, not re-checked line by line
  against the code in this pass.
