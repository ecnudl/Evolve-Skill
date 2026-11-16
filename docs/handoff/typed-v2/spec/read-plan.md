# typed-v2 spec: read plan (decisions D9, D10, D11 as revised by RP1, D12)

Status: CORRECTED 2026-11-12 (fix1), then SECOND CHECK applied (fix2: issues I-1..I-16 and ADV1..ADV14 of two
checkers, section 8.2; D16 and D17 of the addendum, added 17:45 and 17:51, are now taken in). Inputs: the draft of
16:06, critic A (A1-A17), critic B (CB1-CB31), the verdicts of seven verifiers
(`SkillOpt-scratch/typed-v2-build/rp-verify/ALL-results.json`, ids vA1, vA2, vB1, vB2, vB3, vQ, vH) and the
coordinator decisions RP1-RP11 (last section of `DECISIONS-ADDENDUM-20261112.md`). Design only; nothing in the tree
is edited. Precedence: addendum coordinator sections > `DESIGN.md` > spec files. Paths relative to
`<repo-root>`; `T/` = `skillopt/execskill/typed/`, `X/` = `skillopt/execskill/`.

Marks. [V] opened and read: `T/`, `scripts/`, `tests/` at commit 8375ecb (the typed-v1 code and the start of the
build; its `T/` equals the typed-v1 source manifest 24 of 24, vB1); `X/` and `skillopt/coevo5/` in the tree (frozen,
F11). A [V] that only a verifier opened names the verifier. [P] a name planned by Step 5m (`mount.mount_identity`,
`mount._route`, `Services.identity_fn`; `spec/gate.md` 1.6) or by schedule-lock Part A (`freeze_anchor`, `learn`,
`learned`, `load_frozen`, `bind_read`, `s<k>/frozen.json`, `state['phase']`, `state['read_mounts']`). [I] inferred.

Terms. Event = C0, C, S1..S5. Pair = one (event, bench); a chain has 35. Unit = the read unit of a pair
(`test-read-<event>-<bench>`; smoke `practice-read-...`). Class = the events of one bench whose per-item mount
identities are equal on every item (D10 b). Representative = the latest event of a class; only its unit is read.
Alias = a pair settled by a record that points to its representative (D10 d). Fallback = a pair made its own class,
read fresh, because of a doubt (D10 f). Settled = R46.

Rule ids R1-R74 of the draft are kept where the rule survives; retired ids are listed at the end of section 8.1. New
rules: R47b, R75-R90; fix2 adds R91 (base card, D17) and R92 (fake-smoke kill points). New risks K-G, K-H; new
questions Q20-Q22, and Q23, Q24 from fix2 (Q19 is now an interface requirement, 5.3; Q1-Q18 of the draft are
answered at the end of section 8.1).

## 0. Blockers

None. Everything fits in `T/`, `scripts/`, `tests/` (D1). Since RP1 nothing in the run reads, copies or depends on
the typed-v1 root. The five readings of the draft are resolved (vQ; RP1, RP2, RP8):

B1. "typed-v1 unit complete, its own record hash valid" (D11). Since RP1 it concerns only the post-read replicate
    command (1.E). Reading: complete iff `done.json` has `stop_reason` null and `missing_cells` 0; every tag under
    `unsubmitted/` also has a record in `cells/` (a stale file of a recovered cell is counted, not refused, vA2-X1);
    the mirror says `complete`; `canonical_sha256(aggregate.json) == mirror['aggregate_sha256']` [V T/reads.py:472];
    and `aggregate['by_arm'][arm]['request_sha256']` equals the sorted list re-derived from `cells/*.json`
    [V T/reads.py:446] (only this ties the hash to the cells, vQ). `done.json` has no self-hash [V T/units.py:428-431].
B2. "same panel registry hash". Replicate command only. The entry holds `run` = the manifest record hash
    [V T/reads.py:133-134], different for every root. Reading: entries equal without `run`, same route-B evidence
    label; for SpreadsheetBench also the qualification records equal on `qualified` (as sets) and `task_hashes`
    [V X/evaluation.py:296-300, vQ]. A consistency check; the per-item match of R84 is the real guard.
B3. "same solver settings in both manifests". Neither manifest holds them: `clients` is two paths
    [V T/prepare.py:276]; the solver blocks are built at start by frozen code [V T/chain.py:1017-1029]. Reading (RP2):
    typed-v2 records them from now on (R75), provenance only; the replicate command prints which settings are
    observed per send and which rest on code equality only (R85).
B4. "same machinery list hash". Partly wrong in the draft: the typed-v1 manifest pins the snapshot through
    `machinery_manifest.record_sha256` and `provenance.machinery` [V T/prepare.py:277-282, vQ]. Reading: the
    replicate command compares these two under the name "same machinery manifest record and snapshot provenance".
    It records `provenance.typed_tree` as different by construction (vQ). `provenance.machinery` is copied by value
    from the same 11/09 manifest in both runs, so it is equal by construction and proves nothing about what either
    run loaded at its own time (vB1 CB5); R85 prints both remarks beside the verdict.
B5. "the item's type under the event's typemap" as an identity input. Reading (RP8): the identity hashes what the
    type selects (card text, selection request, offered program records), never the type id; the id is stored
    beside it un-hashed (R9, R12). Hashing the id would make equal requests look different
    [V T/mount.py:66-69, :200-204, :207, :224-227].

## 1. Behaviour

### 1.A Manifest and chain-start fields (D9; RP2)

R1. Constants in `T/__init__.py`: `READ_PLANS = ('full', 'economy')`, `READ_PLAN_DEFAULT = 'full'`,
    `IDENTITY_VERSION = 'typed-v2-mount-identity-1'`, the record versions of section 3, the pause reasons of 3.6.
R2. `prepare(..., read_plan='full')` puts `read_plan` into the `fields` dict [V T/prepare.py:269-285], so the
    manifest record hash covers it [V T/prepare.py:239-251]. `prepare` refuses, before it creates anything: an unknown
    value; `economy` with `schedule != 'learn_first'`. Allowed pairs: (`interleaved`, `full`), (`learn_first`,
    `full`), (`learn_first`, `economy`).
R3. `load_manifest` [V T/prepare.py:293-302] requires `read_plan in READ_PLANS` and repeats the pair check.
R4. CLI: `prepare --read-plan {full,economy}`, default `full`; `prepare --smoke --read-plan-probe <event>:<bench>`
    (R7). `run` and `smoke` take no read-plan option (they read the sealed manifest); both gain
    `--stop-after-plan` (R77), and `smoke` gains `--resume` (X3: today `smoke` has none and `run --resume` refuses a
    smoke state [V scripts/run_typed.py:124-126, :262-266; T/chain.py:944-945]). New command `plan-replay` (R47).
R5. A new chain state gets `state['read_plan']` (keys in 3.6) with `mode` = the manifest value. A reopened state whose
    `mode` differs from the manifest is a hard error (as schedule-lock T7 does for `schedule`).
R6. With `read_plan = full`: no pass, no plan file, no alias; the units, order and requests of schedule-lock Part A.
    R75 and R79 apply in both modes; the readout resolver marks every pair `fresh`.
R7. The smoke manifest takes the same field. The typed-v2 smoke is prepared with `learn_first`, `economy`, lock
    `unit_shared` (D13), `base_card = 'historical'` (D17; R91) and the run's `widths` / `learn_widths` (D15), plus
    the smoke-only field `read_plan_probe = [event, bench]`, set to `['C0', 'zebralogic']` (4.3 S1). `prepare`
    refuses `read_plan_probe` on a real root and with `full`. The real run is prepared with the same values except
    the probe.
R75. Solver settings record (RP2; B3; CB4 a). At every start and resume, whatever the schedule and read plan, inside
    the `try` of `run` and before `confirm`, the chain builds a credential-free record from the solver block it runs
    with (`run_inputs`, scripts/run_typed.py:129-156 [V]; fakes write their scripted values [I]) and writes it with
    `write_once` (R80) to `<chain>/solver-settings.json` (3.5). Its sha256 is bound in
    `state['solver_settings_sha256']`. A resume whose record is not byte-equal pauses `solver_settings_changed`
    before any call. No URL, key, proxy or credential path. It enters no request, no identity and no gate or read
    decision (RP2). The plan header binds its hash (R32 c). The replay reads the nominal M from it only to rebuild
    `run_constants_sha256` and the capture inputs without opening a credential file (R47); a difference there is a
    replay difference. The replicate command compares typed-v1 send bounds with it (R85).

### 1.B The per-item mount identity (D10 b; RP8, RP9)

R8. Where the requests of a read cell come from:
    (a) `_read` sorts the items by id, builds one view per item, and embeds only for arm F [V T/reads.py:276-279].
    (b) the cell builder calls `mount_fn(bench, item, arm, typemap, library, vector, selector, view)` and then
        `solve_fn` under the per-cell lock, without a `step` [V T/reads.py:334-348].
    (c) `mount.solve` hands the frozen shell: `deepcopy(item['public'])`, `mounted['system_card']`, the package built
        from `mounted['enabled']` with the label `typed/<unit>`, the bench runtime, a worker only when programs are
        enabled, the native pool, `nominal_tokens`, `configuration=MACHINERY` [V T/mount.py:353-368].
    (d) the shell: system text = function of (bench, card text, runtime, configuration) [V X/solver.py:147-167];
        under main-v10 `compose` returns the card unchanged for a typed package, which holds programs only
        [V X/v225_cards.py:103-107, :128-133; X/package.py:322-326; vQ N2]. First user text = the public view plus
        the notes of enabled hooks [V X/solver.py:171-178, :685-700]. Hooks receive view / state / report / event
        only [V X/solver.py:444, :568, :609, :630, vH].
R9. Identity of one item under one event (`IDENTITY_VERSION`):
    `identity = canonical_sha256({'v', 'bench', 'public_sha256', 'view_sha256', 'system_sha256', 'programs',
    'selection_sha256'})` with `canonical_sha256` of T/library.py:36-37 [V] (sorted keys, no spaces). The fields come
    from R16: `system_sha256` and `programs` (the ordered skill `sha256` values of the offered programs) from
    `mount_identity`, `selection_sha256` from the capture-mounted record. Not hashed: type id, skill ids, source,
    distance (R12, R14).
R10. Every input that can change a request, and how it is covered (vH traced one read cell end to end and found
     no input outside this table and no false difference inside the hash):

| # | Input | Where it enters [V] | Covered by |
|---|---|---|---|
| 1 | system text | `mounted['system_card']`: C0 = format block (T/mount.py:169-170); C = historical card (:171-172); F on a typed item = active card of the type + the base card, or the base card alone (`system_card` :66-69, :238; the base is set by `base_card`, D17, R91); F on an item of unknown type = the format block at 8375ecb (:200-204; Q23) | `system_sha256` = `mount_identity['system_card_sha256']` (= the mount record's, :176) |
| 2 | first user text | the public part given to the shell (T/mount.py:366) | `public_sha256 = canonical_sha256(item['public'])` (= the row's `public_hash`, :360) |
| 3 | view | `view_of` (T/mount.py:148-150); ALFWorld: the view made by the panel reset, stored inside `public` (X/evaluation.py:524-537) | `view_sha256 = canonical_sha256(view)` |
| 4 | selection request | `_select`: program index (names, frozen descriptions) + `public_text(view)` (T/mount.py:266-275; T/library.py:138-150, :207-215) | `selection_sha256` = `selection['attempts'][0]` of the capture-mounted record (R17); `None` when the record's `selection` is None (C0, C, unknown type: T/mount.py:166-172, :200-204) or its `attempts` list is empty (status `not_needed`, a type without programs: :224-227). The format retry is a pure function of the first request (T/library.py:218-219) |
| 5 | eligible entries and their order | `library.active_card(tid)`, `library.programs(tid)` in library order (T/mount.py:205-206; T/library.py:125-133) | card: row 1. Programs: `programs` = the skill `sha256` of each OFFERED program in library order, from `mount_identity['programs_offered']`; a skill `sha256` is `canonical_sha256(body)` and the body holds the procedure record (T/library.py:76-80) |
| 6 | enabled programs, package | `package_for(enabled, step=label, evidence)` (T/mount.py:92-98, :353-354); enabled = the selection reply (:228-229, :288) | enabled subset: the reply, unknown at zero calls; equal inputs give one reply distribution, so all OFFERED programs are hashed. Label: NOT hashed (R14) |
| 7 | sandbox / environment configuration | worker options, bench runtime, native pool, `nominal_tokens`, `MACHINERY` (T/mount.py:356-368; T/chain.py:1116-1118, :1151-1159) | run constants per (chain, bench); the frozen state cannot change them. Not in the item hash; `run_constants_sha256` per bench in the plan header (R32 c) over named keys: the bench runtime from the manifest, `services.worker_options` (seven keys), `nominal_tokens(bench)`, `MACHINERY`, `IDENTITY_VERSION`. Sandbox limits, pools, the unit tag and the solver client are not in it; inside one run they follow from the bound manifest hash and the bound frozen code (A16) |
| 8 | vector | `panel_vectors` (T/reads.py:170-175) | not hashed; acts only through `typemap.assign` (T/mount.py:197), whose effect is rows 1, 4, 5. A vector depends on its batch neighbours (embedder batch size 32, vH H3): R24, R26 |
| 9 | type assignment | `typemap.assign(signature, vector)` (T/tasktypes.py:221-235) | not hashed as an id (RP8); its effect is rows 1, 4, 5 |
| 10 | arm | `reads.arm_of(event)` (T/reads.py:44, :58-61) | not hashed; its effect is rows 1, 4, 5. So an S event can join the class of C0 (base `format`) or of C (base `historical`), R91 |
| 11 | API parameters: model, max tokens B, nominal M, thinking | solver client built at start (T/chain.py:1017-1029, :1067, :1101-1102) | constant per (chain, bench) inside a root; recorded in `solver-settings.json` (R75), whose hash the plan header binds |

R11. A candidate arm never occurs in a read: read arms are C0, C, F [V T/reads.py:44, :58-61]. The pass computes
     identities for these three arms only (`forced` is always None).
R12. Stored beside each identity, un-hashed, in the sealed identity file only: `type`, `source`, `unknown_reason`,
     `card_skill`, the offered skill ids. Use: the readout's planned mount columns (R72) and diagnostic counts
     (R30, R41). They never decide a class (H4).
R13. Why a typemap-only change is one class, base `format` (R91 a). Unknown item: `'', format_block(bench)`
     [V T/mount.py:200-204]. Typed item without card: `card_text = ''`, so `system_card` returns the block alone
     [V T/mount.py:207, :66-69]; no programs means no selection call [V T/mount.py:224-227]. Both send the C0 request.
     Under base `historical` (the smoke and the real run) both send the C request only if the unknown branch also
     mounts the base card (R91 b, Q23); otherwise a flip between unknown and typed without skills is a real request
     difference (R91 c).
R91. Base card (D17). The sealed manifest field `base_card` (`format` | `historical`; code default `format`; the smoke
     and the real run set `historical`) decides what `system_card(b, T)` puts under a learned text T and what a typed
     item without a card mounts. The identity rule does not change: it hashes the system text (R9, R10 row 1), so
     both values give correct classes; only which events share a class changes. The read arms are unchanged (C0 =
     format lines, C = historical card). The pass, the replay (R47) and the read units build every mount through
     the same `mount_identity` / `mount` (RP9) with the manifest's `base_card`; the plan header binds `base_card` by
     name (3.2). Classes of one panel with one request change at step k, by case:
     (a) `format` (golden tests): typed without card and unknown both mount the format block (the C0 request).
         Non-ZebraLogic bench never changed: {C0, S1..S5} > S5, {C} > C; changed at step k: {C0, S1..S(k-1)},
         {C}, {S(k)..S5} (k = 1: {C0} alone).
     (b) `historical` with the unknown branch also mounting the base card (Q23, recommended): typed without card and
         unknown both mount `historical_text(b)` (the C request). Never changed: {C0} > C0, {C, S1..S5} > S5;
         changed at step k: {C0}, {C, S1..S(k-1)} > S(k-1) (k = 1: {C} alone), {S(k)..S5} > S5. A type-map-only
         change stays one class.
     (c) `historical` with the unknown branch as at 8375ecb (format block [V T/mount.py:200-204]): an unknown item
         sends the C0 text, a typed item without a card the C text. A panel whose items are all unknown under S(j)
         (typically a bench before its own step: unseen signature) joins C0's class; a panel all typed without cards
         joins C's; a mixed panel is a class of its own. More fresh units, never a false alias.
     (d) ZebraLogic: `historical_card` is the format block [V T/mount.py:61-63] and `v222_cards.historical_text` =
         `format_text` = `zebralogic.CARD_TEXT` [V X/v222_cards.py:127-139], so C0 and C send the same requests
         under every case: never changed {C0, C, S1..S5} > S5; changed at step k: {C0, C, S1..S(k-1)}, {S(k)..S5}.
     A bench changed by more than one step (or by a later member bench's skill, F14, D16) gets one more class per
     change. The layout example (1.F), R40, T3-T6 and the smoke (4.3) use case (b) for the configured run; T3-T6 also
     run case (a).
R14. Event-specific values that are NOT a request difference and are not hashed: event, arm name, unit name, cell
     tag (sha256(bench NUL item id NUL arm) [V T/units.py:253-254]); the package label `typed/<unit>` and
     `package_sha256` [V X/package.py:328-338]; the row field `step`; library and type map record hashes (each save
     writes its step, so an unchanged library has a new hash at every step [V T/library.py:161-170,
     T/tasktypes.py:247-256]); skill ids, type ids, source ids, distances, thresholds; the container name and tag; the
     call record path; the SpreadsheetBench score position [V T/mount.py:473-480]; the memory lock mode and the
     unit widths (D13, D15: they enter no request, cell tag or identity). The label reaches the container
     only as `package_sha256` in the load request [V X/sandbox/client.py:434]; the bound worker `worker_v222.py`
     type-checks and echoes it and keeps only `loaded` and `limits` [V X/sandbox/worker_v222.py:812, :825, :848-849,
     vA1, vH]; procedure code runs in `{__name__, __builtins__, public_workbook, safe_sympify}` [V :374-377, vH];
     the router keeps the hash in its log only [V X/router.py:108]; the container environment holds no unit, label or
     tag [V X/sandbox/client.py:151-158, vQ]. Residual [I]: that the static screen keeps procedures from inspecting
     the worker's frames (`X/policy.py` not opened). Guard: T7 runs in the bound driver and must pass before the
     smoke (vA1, A2); it is a test, not a run-time check. Pre-registered response if T7 fails: items with offered
     programs carry the event in their identity, so they never alias across events (Q2 of the draft).
R15. Real differences and why none is missed:
     (a) a program with the same name and description but another body: row 5.
     (b) card text '' against blank-only text: `system_card` gives the base alone for both (the format block or,
         under `historical`, the historical card; R91); same request, same identity; correct.
     (c) later sends of a cell (repair, compute follow-up, ALFWorld steps after the first) depend on replies and the
         environment: not plannable; equal first inputs give the same distribution.
     (d) a hook's routing on the view: a function of program body and view (rows 3, 5).
     (e) run constants changed between plan and read: the plan binds the manifest hash, `solver_settings_sha256`
         and `run_constants_sha256` (R32 c); the start checks of `spec/identity.md` 1.9 refuse changed code.
     (f) an embedder whose output moves near a threshold in another process (or with other batch neighbours): the
         pass embeds exactly the read unit's list (R26) twice (R30); a representative that routes differently fails
         R41 and voids the aliases of its bench (R42).
     (g) an ALFWorld live reset that differs from the registered view: the shell raises `ConfigurationError`, a stop
         kind, so the unit stops and the chain pauses [V X/solver.py:838-840, :886-894; coevo5/cells.py:45;
         T/mount.py:369-370; T/units.py:359-365, vA1 X1]. It is not a recorded failed cell.
R16. How it is computed (RP9; A1, H1). No third mount implementation. Per (event, bench, item) the pass calls
     (i) `services.identity_fn` = `mount.mount_identity(bench, item, arm=reads.arm_of(event), typemap=..., library=...,
         vector=..., view=view)` [P gate.md 1.6 rule 22 and change row T/mount.py], which shares `_route` with
         `mount()` and returns `{system_card_sha256, programs_offered: [[skill_id, sha256], ...], forced: None}`;
     (ii) `services.mount_fn(bench, item, arm=..., typemap=..., library=..., vector=..., selector=capture_selector,
         view=view)`, the real mount with the capture selector of R17.
     From (ii) the pass keeps `selection_sha256` = `selection['attempts'][0]`, or None when `selection` is None (C0,
     C, unknown type [V T/mount.py:166-172, :200-204]) or `attempts` is empty (`not_needed` [V :224-227]), and the
     fields of R12; it drops `raw_excerpt` and `failure`, which may hold text [V T/mount.py:284, :289-291].
     Self-check: (i) and (ii) agree on `system_card_sha256` and on the offered skill ids, else fallback
     `identity_disagreement`. A stop
     or pause raised by either call propagates unchanged (R33); any other exception makes that (event, bench) a
     fallback `identity_exception` (R31). The real mount (ii) raises wherever arm F cannot mount (strict signature,
     missing vector, `_consistent`, a program without description) [V T/mount.py:166, :180-187, :194-196, :257-263;
     T/library.py:138-150]; (i) raises in the routing cases it shares through `_route` [P]. So such an item can never
     receive the C0 identity.
R17. The capture selector (corrected: the draft's "mount.mount cannot be used by the pass" is refuted, A1). A plain
     function with no client, no recorder file and no ledger: `capture_selector(system, user)` returns
     `{'ok': False, 'error_type': 'read_plan_capture', 'usage': {}}`. `_select` calls it at most
     `SELECTION_ATTEMPTS = 2` times (the request, then the format retry after the parse failure); `attempts[0]` is the
     first selection request hash; the status is `parse_failure` and nothing is enabled [V T/mount.py:40, :266-291].
     Zero sends.
R18. Zero calls and cost. Tokens 0; the ledger is not touched and no ledger unit is created (no `before_send`
     [V T/units.py:177, vA1 A8]). Not zero machine time: per bench one view per item, two embedder batches (a local
     CPU subprocess [V T/tasktypes.py:100-103]), the ALFWorld preparation resets as a read unit does them, and, when
     the pass is the first caller of `panel_tasks`, the SpreadsheetBench test qualification (scoring containers under
     the heavy lock, no tokens) [V X/evaluation.py:255-301, vQ N3].
R19. First-request capture (RP3; X2; vQ-X2). MANDATORY, for every event (C0, C, S1..S5), for every item without
     offered programs on SearchQA, OfficeQA, ZebraLogic and SpreadsheetBench. Not for ALFWorld (RP3, option 1 a, which
     narrows D10 b's full request hash of C0 and C to these four benches); not for items with offered programs
     (their first request follows the selection reply). The pass calls the injected `services.solve_fn` (in the
     real run `mount.solve`; in the fake smoke `smoke.fake_solve`, so the fake cells match, X2) with the
     capture-mounted record of R16 (ii) (nothing enabled, so no worker is needed), the real
     unit name `reads.unit_name(event, bench, smoke=...)`, the real cell tag, the scorer path the real cell would get
     (never created) and a capture call object. The capture call computes `sha256_text(system + '\x00' + user)` as
     `units.CallRecorder` does [V T/units.py:213], keeps the FIRST send's hash only and returns
     `{'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'read_plan_capture'}`; it has
     `sends`, `tokens()` = 0 and `infrastructure_unknown()` = False, which both solve functions read
     [V T/mount.py:422-430; T/smoke.py:263-283]. The shell returns unknown right after the first request
     [V X/solver.py:698-700, :751-753]; no worker or container starts [V T/mount.py:356; X/solver.py:289-292]; the
     sheet's first request opens the public workbook preview only and holds no native slot [V X/solver.py:181-190,
     :728-753]. `mount.solve` then runs `judge.judge` on the unknown prediction in memory; the row is discarded and
     only the hash leaves the capture; `_sheet_score` does not run, the prediction is not `available`
     [V T/mount.py:374-381]. A capture that did not record exactly one send makes that (event, bench) a fallback
     `capture_failed`. Stops raised inside propagate (`mount.solve` re-raises them [V T/mount.py:369-370]).
R19b. Retired: merged into R19 (RP3 makes the capture mandatory for every event).

### 1.C The planning pass (D10 b, g, h)

R20. When. Only with `read_plan = economy`. Run order under economy (CB27): `confirm`, `freeze_anchor`,
     `learn(1..5)` [P], the pass (pseudo-unit `read-plan`), the replay (R76), the optional stop (R77),
     `read_classes()` (R35). `read_anchors` and `read_step` are never called under economy. The pass runs inside the
     same `try` of `run` as the reads [V T/chain.py:978-989]. Before the consent check and before the first
     `panel_tasks` call it sets `state['phase'] = 'read'` (DESIGN 3.6), `current_unit = 'read-plan'` and the seven
     `read_mounts` entries from the frozen receipts (schedule-lock S6; Q14), and persists the state (A7).
R21. Consent first. On a real root the first statement after R20's persist is `reads.consent(shared)`
     [V T/reads.py:91-111]. No consent: its `require` raises, nothing is opened, `run`'s handler pauses the chain as
     for a read unit. (schedule-lock Q2 keeps a zero-call consent check at chain start; this is the binding check.)
R22. Opening the panels; registry and qualification. For each bench in chain order the pass calls
     `reads.open_panel` (R24), i.e. `panel_tasks(root/'shared', manifest['pinned'], bench, '<chain>/test-read-plan',
     ...)` with exactly the arguments `_read` passes [V T/reads.py:266-275] and, for SpreadsheetBench, under the heavy
     lock. The label holds `test-read`, which `panel_tasks` requires [V T/reads.py:124]. Under `economy` the pass of
     whichever chain comes first creates the write-once registry entry and runs the qualification; every later caller
     verifies: the entry holds no label [V T/reads.py:133-134], `_registry` is write-once under an exclusive lock
     that waits and requires an equal entry later [V X/evaluation.py:243-252], the qualification pointer is
     write-once under its own lock [V X/evaluation.py:255-301], `TestAccess` keeps the label in memory only
     [V coevo5/data.py:232-239]. Two chains serialize on these locks; no new lock (Q18, vQ). A failed qualification
     raises route-B `Pause('qualification_paused')` [V X/evaluation.py:270-272]; it propagates unchanged (R33), `run`
     records `exception:Pause` with detail `Pause:qualification_paused` [V T/chain.py:254-258, :988-989], and
     `recover` forwards the owner's record into the attempt because it keys on that detail
     [V T/chain.py:374-411]; the next resume re-runs the pass (T12). The pass opens all five panels, with views and
     vectors, before it writes any sealed file.
R23. ALFWorld views. As a read unit gets them: `evaluation.alfworld_reset(runtime['alfworld'], episodes)`
     [V T/reads.py:229-230], wrapped with `v218_lock.call(reset, lock_setting, 'alfworld', unit=...)` under
     `unit_shared` by the same helper `_from_services` uses (D13; DESIGN 3.6). Kept in memory and in the sealed
     inputs file (R78).
R24. One panel path (H3; Q12 answered: extract, never duplicate). Lines T/reads.py:266-279 [V] of `_read` (manifest,
     view function, lock, panel, sorted items, views, vectors for arm F) move into
     `reads.open_panel(root, chain, bench, unit, *, setup, vectors)` (`setup` = the arguments `_read` receives),
     which `_read` and the pass both call. `_read` keeps its behaviour; the existing read tests pass unchanged. It is
     done in the same change as the D13 reset wrap, so `T/reads.py` is edited once (O10).
R25. Smoke. The smoke opens no test panel: its items are the held-out practice panel slice `_smoke_panel(services,
     bench)` [V T/reads.py:244-250], with no consent and no `TestAccess`. The pass uses the same items through
     `open_panel`, the label `practice-read-plan`, and writes no registry entry.
R26. Views and vectors. One view per item (`services.view_fn`) and one `panel_vectors` batch per bench
     [V T/reads.py:170-175] over exactly the list `_read` embeds: the same item set after qualification and resets,
     sorted by id [V T/reads.py:276-279]. Reused for the five S events (C0 and C use no vector).
R27. Frozen states. C0 and C use the s0 state; S<k> uses the state named by `s<k>/frozen.json` through
     `load_frozen(k)` [P], verified as schedule-lock S6 says. Never the live `self.library` of the chain.
R28. Lists. Per (bench, event): `rows = [[sha256_text(item_id), identity], ...]` in sorted id order and
     `identity_list_sha256 = canonical_sha256({'v': IDENTITY_VERSION, 'bench': bench, 'rows': rows})`. The same form
     for `first_request_list_sha256` over `[[sha256_text(item_id), hash or None], ...]` (None for an item with offered
     programs); it is null for ALFWorld only.
R29. Classes (RP3). Two events of a bench are in one class iff (a) both have status `ok`; (b) their
     `identity_list_sha256` are equal; (c) their `first_request_list_sha256` are equal wherever both are non-null.
     Two `ok` events that meet (b) but not (c) both get status `fallback`, reason `first_request_mismatch` (a defect
     signal, reported as in R42). The representative is the latest member in the order (C0, C, S1..S5). The item set
     is the same for every event of a bench (one panel), and the list hashes include the hashed ids.
R30. Embedder stability (H4; A5). The batch of R26 runs twice per bench, in two subprocesses; both runs' vectors go
     into the inputs file (R78), so the comparison is reproducible from stored inputs. Per S event the identity lists
     computed from the two runs must be equal; an S event whose two lists differ gets status `fallback`, reason
     `embedder_unstable`. Items whose descriptive fields (`type`, `source`, `unknown_reason`) differ while the
     identity is equal are counted (`descriptive_flips`), never a fallback. Identities use the first run.
R31. Fallback inside the pass (D10 f). Status `fallback` with a reason from `READ_PLAN_REASONS` (R81):
     `identity_exception`, `identity_disagreement`, `capture_failed` (R16, R19), `embedder_unstable` (R30),
     `first_request_mismatch` (R29), and in the smoke only `smoke_probe` for the pair named by `read_plan_probe` (R7).
     A fallback pair is its own class and is read fresh. A missing or unequal frozen receipt is a pause
     (`frozen_state_changed`), not a fallback. No fallback ever removes a read.
R32. Outputs.
     (a) Sealed, under `<chain>/test-read-plan/` (smoke: `practice-read-plan/`), with `allow_sealed=True`
         [V T/units.py:45-63] and `write_once` (R80): `inputs-<bench>.json` (R78, written first) and
         `identities-<bench>.json` (3.3). These are the only files with item ids and per-item values.
     (b) Open: `<chain>/read-plan.json` (3.2), hashes and counts only, no time stamp, no path outside the root, no
         host name, so a replay gives the same bytes. Written with `write_once` after every sealed file. Self-hashed:
         `plan_sha256 = canonical_sha256(record without plan_sha256)`.
     (c) Binding: `state['read_plan']` gets `plan_sha256`, `file_sha256` (sha256 of the bytes) and `bound_at`; then
         `mark('read-plan')`. The plan header binds the manifest record hash, `base_card` by name (R91), the seven
         frozen receipts' hashes, `solver_settings_sha256` (R75), per bench `run_constants_sha256` (R10 row 7),
         `registry_sha256` (the entry without `run`; null in a smoke) and the sha256 of every sealed file.
R33. Failure of the pass (RP11; A9, CB22, X1).
     (a) A typed `Paused`, a `units.Stop`, a route-B `Pause` (a plain Exception [V coevo5/cells.py:49-54]) or a
         route-B stop kind raised by any code the pass calls propagates unchanged. Every exception of the panel path
         (consent, `panel_tasks`, registry, qualification, views, embedder, ALFWorld resets) also propagates unchanged
         to `run`'s handlers, which record `exception:<Class>` with `_pause_detail(error)` [V T/chain.py:984-989]:
         such an error would block a `full` read as well.
     (b) A non-stop exception of the per-item identity calls is a fallback (R16, R31), never a pause.
     (c) Only the pass's own detected inconsistencies pause `read_plan_failed`, with a fixed code: `inputs_mismatch`
         (a stored inputs file fails its hash), `view_mismatch` (a non-ALFWorld view recomputed on a re-run differs
         from the view hash stored in the inputs file, R78), `sealed_file_mismatch` (an existing sealed file is not
         byte-equal to the recomputed one), `plan_file_mismatch` (an unbound plan file is not byte-equal),
         `plan_self_check`, and `frozen_state_changed` stays schedule-lock's own reason.
     (d) The first recovery of `read_plan_failed` re-runs the pass. A second failure with the same code does not
         pause: it sets `void = true`, `void_reason = 'pass_failed'`, marks `read-plan`, and all 35 pairs of the chain
         are read fresh in the economy order (R36) through the unchanged read path. Codes are kept in
         `state['read_plan']['failures']`.
     (e) No partial `read-plan.json` exists at any time (R80). The pass charges nothing (R18).
     (f) Not classified by (a) to (c): a non-stop exception raised by the pass's own code after the panel path and
         outside the per-item identity calls (a defect of `T/readplan.py`). Today it reaches `run`'s generic handler
         (`exception:<Class>`) and recurs on every resume, and no code may change inside the root (`spec/identity.md`
         rule 9). Q24 asks the coordinator whether it counts as `read_plan_failed` code `pass_exception` (class name
         only), so that (d) applies. Until decided, it propagates as in (a).
R34. Cost of the pass: no model call; machine time as R18; no ALFWorld capture (RP3).
R76. Automatic replay in a fresh process (RP6; D10 g; CB31 option b). Right after the binding of R32 c, before any
     read unit starts and so before any alias settles, the chain runs `run_typed.py --machinery-snapshot <bound
     snapshot> plan-replay --root <root> --chain <X> [--smoke] [--fake]` as a child process: a fresh interpreter
     under the same bound machinery. Its environment is the launch environment (`run_typed.clean_environment`
     [V scripts/run_typed.py:64-74], which keeps an inherited `PYTHONHASHSEED` [V X/prelaunch.py:40-45]) with
     `PYTHONHASHSEED` set explicitly to a value other than the parent's: the parent's value plus 1 modulo 2^32 when
     the parent's environment sets one, else 1 (the parent then runs with a random seed). The child recomputes the
     plan from the stored sealed inputs (R47) and compares bytes. `equal` (exit 0): `state['read_plan']['replay'] =
     {'verdict': 'equal', 'at', 'hash_seed'}` and the chain goes on. Anything else (exit 3 `different`, an error, a
     timeout) pauses `read_plan_changed` with detail `replay_different` or `replay_error:<code>` (the child's fixed
     code of R47b, or `timeout`, or `exit_<n>`); its recovery is R44's, including the second-error rule (R44 d). A
     resume that finds the plan bound and no `equal` replay runs the replay first. Unit tests with in-memory scripted
     services inject an in-process replay; one test runs the real child (T26).
R77. Stop after the plan (RP6; CB21; X3). `run --stop-after-plan` and `smoke --stop-after-plan` (default off). In
     the process that binds the plan, after the R76 replay is `equal`, the chain raises
     `Paused('stopped_after_plan', 'read-plan')`: a recorded pause, so the CLI exits 5 [V T/chain.py:325-329;
     scripts/run_typed.py:177-188] and the status shows `paused`. It continues with an owner recovery record and
     `run --resume` / `smoke --resume` [V T/chain.py:341-347, :976-977]. The real run does not use the flag; the
     smoke uses it once (4.3).
R78. Sealed inputs (A5). Before any identity is computed, the pass writes per bench `inputs-<bench>.json` (3.3): the
     sorted item ids, one view hash per item, the ALFWorld views, the vectors of both embedder runs (R30), and the
     hashes `views_sha256`, `vectors_sha256`. A re-run of the pass (R45 P2, P3) and every replay (R47) check the file's
     hash, then load from it the ALFWorld views and both vector runs instead of recomputing them; non-ALFWorld views
     are recomputed from the re-opened items (only their hashes are stored) and must equal the stored view hashes.
     A difference is `read_plan_failed` code `view_mismatch` on a pass re-run (R33 c) and `different` in a replay.
     The byte equality of D10 (g) then tests the rule, the frozen states and the code, not the embedder. Read units
     are unchanged: they embed for themselves (R37; R41 and R42 catch a difference).
R79. Learning is closed once reading has begun (A7). Interface rule on schedule-lock S9 / change rows 5, 6, valid for
     `learn_first` with both read plans: `learn(k)` never runs its body and `freeze_anchor` never writes when any of
     these holds: `state['phase'] == 'read'`; `read-plan` in `done_units`; `read-plan.json`, the sealed plan directory
     or any read unit directory exists. A missing or unequal `s<k>` file or receipt then pauses
     `frozen_state_changed`; the chain resumes only after the files are restored to the hashes the plan (or the
     first read event) recorded, never by learning again.
R80. `write_once(path, record)` (CB24). Canonical bytes; write a temporary file in the same directory named
     `.<name>.<pid>.<16 random hex>.part` (never ending in `.json`), fsync, `os.link(tmp, path)`, unlink the temporary
     file. Every reader of these directories (`_aliases`, R44, R46, the replay) accepts only the closed names
     `<event>-<bench>.json` (alias records), `inputs-<bench>.json`, `identities-<bench>.json` and `read-plan.json`, so
     a temporary file left by a kill is never read as a record (ADV11). The pass and the alias settling (R39) remove
     the `.part` files of their own directory when they start. On `FileExistsError` compare bytes; a difference raises
     `WriteOnceMismatch`, which the caller maps to its reason: `read_plan_failed` inside the pass (R33 c),
     `read_plan_changed` for a bound plan file, `read_alias_invalid` for an alias record, `solver_settings_changed`
     for R75. Used for `solver-settings.json`, the sealed inputs and identity files, `read-plan.json` and the alias
     records. `units.write_json` (fixed `.tmp` name, `os.replace`, never exclusive [V T/units.py:55-63]) is not used
     for them.
R81. Closed vocabulary (A10). Every `reason`, `fallback`, `void_reason`, replay detail and recovery outcome comes from
     one tuple `READ_PLAN_REASONS` in `T/readplan.py`. An exception is stored by class name only, as `_pause_detail`
     does [V T/chain.py:254-258], never `str(error)` (an embedder error may quote test text
     [V T/tasktypes.py:104-108, vA2]). The open plan may carry panel-level counts and the class table only because
     the pass runs after the last freeze (R79 is a precondition).
R92. Fake-smoke kill points (ADV7). A fakes-only test seam: the pass and the replay call
     `services.checkpoint(<point>)` at three named points: `after-first-inputs` (the first `inputs-<bench>.json`
     linked), `after-plan-file` (`read-plan.json` linked, not yet bound) and `replay-child` (inside the child, after
     it opened the inputs). Real services have no `checkpoint` (the call is skipped); `smoke.fake_services` defines
     it and, when the CLI option `smoke --fake --fake-kill-at <point>` names that point, sends SIGKILL to its own
     process group (for `replay-child` the parent passes the option on to its `plan-replay --fake` child; both
     commands refuse it without `--fake`), so the parent and a replay child die together and nothing is flushed
     (the test starts the CLI in a new session, so the group holds only the smoke). It enters no request, identity,
     record or file (S2 c).

### 1.D The read phase under `economy` (D10 a, c, d, e, f)

R35. A new method `_Run.read_classes()` reads under `economy` (run order in R20). With `full` the schedule-lock loop
     runs unchanged. Under `economy` nothing opens a panel (no `TestAccess`, no file under `shared/test/`) before the
     pass has set the phase `read` (R20), and no read unit directory exists before `read-plan` is in `done_units`
     (CB27).
R36. Order (D10 e). First sweep: `for event in ('S5', 'S4', 'S3', 'S2', 'S1', 'C', 'C0')`: `benches` = the benches
     in chain order where `event` is the representative of an unsettled class; skip the event when the list is empty.
     S5 is the last event, so it is a representative on all five panels and is read first. Final sweep: every pair
     still unsettled after the first sweep (an alias voided by R42 or R44, a void plan) is read fresh as its own
     class, again in the order S5..C0. Each pair is read fresh at most once. With a void plan every pair is its own
     class from the start. The order enters no request and no identity (R14). The automatic infrastructure retry of
     `reads` is keyed per event [V T/chain.py:610-611], so a final-sweep visit of an event whose retry was used
     pauses instead of retrying (fail-safe).
R37. For each event: bind the event's frozen state as schedule-lock does (`load_frozen`, `bind_read` [P]), then
     `reads(event, benches=benches)`. The only change to `reads` [V T/chain.py:589-622] is the optional argument:
     `wanted = [b for b in self.s.order if (benches is None or b in benches) and not self.done('read-%s-%s' % (event,
     b))]` (today :594). `read_event`, `read_one`, `_read` (apart from R24), `units.run_unit` and every request stay as
     they are: a fresh unit under `economy` is the unit `full` would run for that pair (D10 a).
R38. An alias pair is never in `benches`, so `read_event` / `read_one` never run for it: no unit directory, no cell,
     no mirror, no ledger entry.
R39. Settling a class (A6, CB24, CB28). After `reads(event, benches)` returns (all its units complete
     [V T/chain.py:599-622]), for each bench in `benches`:
     (1) the post-read check R41 on the representative unit;
     (2) passed: for every other member M of the class that is not settled, first check that `read_mounts[M]`
         equals the plan's frozen entry for M (else pause `read_mount_changed`; nothing is written for M, ADV12);
         then write the alias record `<chain>/read-alias/<M>-<bench>.json` (3.4) with `write_once`, set
         `state['reads'][M][bench] = {'kind': 'alias', 'status': 'alias', 'alias_of': event, 'items': n,
         'alias_sha256': <the record's record_sha256>}` and `mark('alias-<M>-<bench>')` (one persist);
     (3) failed: R42.
     The state entry is the only authority on how a pair was settled. An alias record without its state entry is
     re-derived by the next settling (equal bytes: kept) or, after a void, archived (R42, R44). `status: 'alias'`
     makes `_read_complete` false for the entry [V T/chain.py:248-251]. Alias pairs never get a `read-` marker.
R40. Budgets. Only fresh units charge; the cap stays the D6 value. The worst case of `economy` (every pair falls back)
     is the `full` plan, 35 units per chain, for which the caps are sized (F12, Q15; K-D adds D16 and D17). Best
     case: 9 fresh units per chain: S5 on the five panels plus one more class on each of the four benches whose C
     differs from C0 (C0's class under base `historical`, C's under `format`); ZebraLogic one class
     [V T/mount.py:56-63]. Typical, per request change at step k, for the configured run (R91 b): a non-ZebraLogic
     bench changed once has {C0}, {C, S1..S(k-1)}, {S(k)..S5} (3 fresh units; k = 1: {C0}, {C}, {S1..S5}); a bench
     no step changed has {C0}, {C, S1..S5} (2); ZebraLogic {C0, C, S1..S(k-1)}, {S(k)..S5} (2) or one class (1).
     Under `format` the counts are the same with the roles of C0 and C exchanged (R91 a); R91 (c) can add one class
     per bench.
R41. Post-read check (RP3; H4; A12 as verified). Inside the read path, counts only. For the representative unit of
     (event, bench), per planned item, the cell is found by `units.cell_tag(bench, item_id, arm)`
     [V T/units.py:253-254] and compared with the sealed plan on the HASHED components, read from these row keys
     (present in real and fake rows): `mount.system_card_sha256` = `system_sha256` (real rows also carry it at top
     level [V T/mount.py:176, :362]; fake rows only under `mount` [V T/smoke.py:276]); `mount.selection` reduced as
     in R16 (None, or `attempts[0]`) = `selection_sha256`; the ids in `mount.programs_offered` mapped through the
     event's frozen library to their skill `sha256`, in order, = `programs`; `public_hash` = `public_sha256`
     [V T/mount.py:360; `smoke.fake_solve` has no `public_hash` at 8375ecb, T/smoke.py:275-282, and gains it, change
     list]; and, where the plan holds a first-request hash, the cell's
     `request_sha256[0]` [V T/mount.py:422-430; selection sends are stored apart, T/chain.py:227-245]. Type,
     `unknown_reason` and skill ids are counted, never decisive. Result `{'items': n, 'equal': e, 'unequal': u}`;
     passed iff `u == 0` and `e == n`. A cell without a send cannot be in a complete unit: it is written to
     `unsubmitted/` and the unit is incomplete; a cell whose transport failed still holds its request hash
     [V T/units.py:212-216, :371-375; T/reads.py:461, vA2]. Infrastructure unknowns inside a complete representative
     do not block the alias (RP3 option 2 a): the representative's `unknown`, `infrastructure_unknown` and
     `configuration_errors` counts go into every alias record and are shown beside every member (3.4, R73).
R42. Failed check (RP10; D10 f). Fallback without a pause. In one persisted step, EVERY alias of that bench, settled
     or not, is voided: its record is moved to `read-alias/archived/<name>-<n>.json`, its `alias-` marker is
     removed, its state entry becomes `{'kind': 'void_alias', ...}`. Every unsettled pair of the bench then is its own
     class and is read fresh (first sweep if its event is still ahead, else the final sweep), bounded by the `full`
     plan. `state['read_plan']['fallbacks'][bench] = {'event', 'reason': 'post_read_mismatch', 'unequal': u}`; the
     readout reports it as a defect signal. The plan file is not rewritten.
R43. Retired (the carry receipt at C; RP1).
R44. Verification at every start and resume (CB21, CB25). Inside the `try` of `run`, after `recover()`
     [V T/chain.py:976-978], before the pass or `read_classes`, with a bound plan:
     (a) Checks. Read `read-plan.json`; require the sha256 of the bytes = `file_sha256`, the self-hash valid and =
         `plan_sha256`, the manifest hash and every sealed file hash as bound; a difference pauses `read_plan_changed`
         with a fixed detail. The seven frozen receipts and `solver_settings_sha256` are compared with the plan too,
         but a difference keeps its own reason, `frozen_state_changed` (R79, schedule-lock S6) or
         `solver_settings_changed` (R75) (I-16). Each alias record is verified when R46 runs and when the readout
         reads it (bytes, self-hash, `plan_sha256`, equality with the record recomputed from the plan); a missing or
         invalid one pauses `read_alias_invalid`; a record whose `representative_aggregate_sha256` no longer equals the
         representative's mirror (a rebuilt mirror [V T/reads.py:522-531]) is invalid too, never rewritten.
     (b) Recovery (CB25). `recover()` stays as it is. When the last applied recovery was for `read_plan_changed` or
         `read_alias_invalid` [V T/chain.py:356-358 keeps the paused reason], the chain archives (renames, keeps) the
         plan-owned files that failed their check, and only those: `read-plan.json`, the sealed inputs and identity
         files, alias records. Frozen receipts, `s<k>` files, `solver-settings.json` and the manifest are never
         archived; their own pauses are resolved by restoring the files to the bound hashes (R79). A pair whose alias
         record was archived returns to unsettled (state entry and marker removed in one persisted step).
     (c) Then, in this order (ADV6). A sealed inputs or identity file that failed its check (archived or missing)
         voids the plan, `void_reason = 'sealed_file_invalid'`: its views and vectors cannot be recomputed, so every
         later replay would fail. Else, when `read-plan.json` was archived, the chain recomputes the plan in process
         from the stored sealed inputs (zero calls; the pass's own code, as at R45 P3) and restores it with
         `write_once` if the bytes hash to the bound `file_sha256`; other bytes void the plan (`replay_different`).
         Then the child replay of R76 runs as the check: `equal`: R39 re-settles the unsettled members (P6) and the
         run continues; `different`: void (`replay_different`).
     (d) A replay error (`replay_error:<code>`) archives nothing and pauses again. When the previous recovery outcome
         was a replay error with the same code, the second one voids the plan instead, `void_reason = 'replay_error'`
         (I-3: the analogue of RP11 for the replay; D10 f: fallback is read fresh). Codes are kept in
         `state['read_plan']['failures']`.
     (e) Void: EVERY alias of the chain, settled or not, becomes `void_alias` as in R42 and is read fresh in the
         final sweep (R36); the representatives' fresh units stay valid. Each outcome goes to
         `state['read_plan']['recoveries']`.
R45. Pause and resume. Every resume consumes one owner recovery record (`recovery.json`, under the standing
     delegation of 11/11) through `run --resume` / `smoke --resume`, a crash included [V T/chain.py:341-347, :939-947].

     | Point | State on disk | Resume does |
     |---|---|---|
     | P1 before the pass | s5 frozen, no plan | R79 guard, then the pass |
     | P2 inside the pass | some sealed files, no `read-plan.json` | re-runs the pass; loads `inputs-<bench>.json` where present (R78); existing sealed files must be byte-equal, else `read_plan_failed` (R33 c, d) |
     | P3 plan written, not bound | file exists, `plan_sha256` null | recomputes from the stored inputs, requires byte equality (else `read_plan_failed` `plan_file_mismatch`), then binds |
     | P3b bound, replay not equal yet | plan bound | R76 replay |
     | P4 bound, replay equal, no unit started (also after R77) | - | R44, then R36 |
     | P5 inside a fresh unit (a pause or a kill) | cells of some items | R44, then the existing unit resume: done cells kept, infrastructure unknowns re-run [V T/reads.py:286-288] |
     | P6 unit complete, class not settled | `done.json`, no alias record | R44; `reads` has nothing to do; R39 settles |
     | P7 some alias records written | records for part of the class | R39 again: an existing record must be byte-equal (`write_once`; records hold no time stamp) |
     | P8 paused inside `reads` (provider stop and so on) | pause record | R44, then as today [V T/chain.py:599-620] |
     | P9, P10 | retired (carry; RP1) | - |
     | P11 after the last event | all pairs settled | R46 |
     | P12 a void plan or voided aliases | `void` or `void_alias` entries | the final sweep of R36 |
R46. Completeness (A6, CB28). Before `state['complete'] = True` every one of the 35 pairs has a non-empty state entry
     and is settled by kind: fresh: `read-` marker, mirror `status == 'complete'` and `stop_reason` None, and the
     sealed `done.json` (re-read inside the read path) has `cells == expected_cells`, equal to the plan's item count
     when a plan is bound (a plan voided by R33 d may have no file); alias: `alias-` marker, a state entry of kind
     `alias`, a record that verifies (R44), and a representative that passes the fresh rule. `_read_complete` is
     never applied to alias entries. Otherwise the chain pauses
     `read_plan_incomplete`. Then `read_classes` marks `step-0` .. `step-5` in that order, so `done_units` holds the
     same `step-<k>` markers as under `full`.
R47. Replay (D10 g; A5; RP6). Command `plan-replay --root R --chain X [--smoke] [--fake]`: `prepare.own_root`, the
     bound machinery start checks, consent first on a real root, then the pass in memory with zero calls. Its inputs:
     the manifest, whose `base_card` builds every mount (R91; a mount built under another base gives `different`,
     ADV1); the frozen states through their receipts; the inputs files, hash-checked (ALFWorld views and both vector
     runs loaded, non-ALFWorld views recomputed and checked, R78); the nominal M from `solver-settings.json` (R75).
     Panels are re-opened through `open_panel` WITHOUT the heavy lock (`heavy = None` gives `nullcontext`
     [V T/reads.py:269-275]; ADV5): first, on a real root, the replay requires that the five registry entries and
     the SpreadsheetBench qualification pointer `shared/test/<SHEET_QUALIFICATION>.json` exist (the pass created or
     verified them [V X/evaluation.py:264-301]), else verdict `different`, code `qualification_missing`. So
     `panel_tasks` only verifies, no scoring container starts, and the replay never waits for the environment lock
     that the other chain's sheet and ALFWorld units may hold for hours (F9: 8,420 s / 15,388 s); the R76 timeout
     bounds the replay's own work only. ALFWorld gets a reset function that returns the stored views and starts no
     environment (N15). The replay's own code writes nothing; route-B's qualification check may still sweep a
     killed qualification attempt's leftovers under its own lock [V X/evaluation.py:266-267] (route-B
     housekeeping, no plan file). It compares bytes with `read-plan.json` and every sealed identity file and prints
     `equal` / `different` with counts; exit 0 / 3. It also re-embeds and prints how many items would
     get another vector or assignment: information only, never a difference. Used by R76 (automatic, child process),
     by the R44 recovery, and by ops when wanted.
R47b. Sealing of CLI entries (A11). `plan-replay` (and the post-read command of 1.E) wrap everything in
     `except BaseException`, print only `{command, chain, verdict: 'error', error_class: type(error).__name__,
     reason: <fixed code>}`, exit 3 and print no traceback. Today `main` has no handler
     [V scripts/run_typed.py:275-283].

### 1.E The post-read replicate command (not part of the run, built after launch)

R48-R62 of the draft (the carry command, receipts, R58's use of a receipt at C, the timing window R61) are retired
(RP1): no typed-v1 cell is copied into the typed-v2 root, C is read fresh through its class, and the run neither
needs nor waits for anything of this section.
R82. Role. typed-v1's C0 and C readings of 2026-11-11 serve only as an earlier, cross-date replicate (noise and drift
     reference, read under `per_cell_plain`). A zero-call command that reads both roots and writes neither. It
     never writes into the typed-v2 run state and never becomes a baseline, a table row or a readout input.
R83. CLI `replicate --root <typed-v2 root> --chain <G|D> --source <typed-v1 root>`. Runs only on a complete typed-v2
     chain. `own_root` applies to `--root`; `--source` must hold a manifest with `version == configuration ==
     'typed-v1'`, a valid record hash and the same `smoke` flag. This is the one exception to `spec/identity.md` 17
     (no typed-v2 helper names a typed-v1 path), authorized by RP1. Consent must be valid in both roots. Files are
     opened `rb`; no lock, temporary file or directory is created in either root.
R84. Matching. For C0 and C on each bench: the typed-v1 unit `test-read-<event>-<bench>` against the typed-v2 fresh
     unit that read the same requests (the event's own unit, or its representative). Item ids come from the
     typed-v2 sealed identity file; per item the typed-v1 cell `cell_tag(bench, id, arm_of(event))` and the typed-v2
     cell `cell_tag(bench, id, representative arm)` [V T/units.py:253-254] match only if their `request_sha256[0]`
     are equal. Unmatched items are counted by cause (missing on either side, first hash unequal).
R85. Checks, printed as verdicts and counts: B1 completeness of the typed-v1 unit with the counts of `rerun/*`,
     `done-stopped-*`, `stop.json`, `failure.json`, stale `unsubmitted/` files and its file-time window (CB6); B2
     registry and SpreadsheetBench qualification; B4 machinery manifest record and snapshot provenance, with B4's
     two remarks (`typed_tree` different by construction, `provenance.machinery` equal by construction);
     judge-version equality per matched cell, with `None` counted apart (A3), and the typed scoring source pinned
     from commit 9ca2754 against the loaded typed-v2 functions (A3, CB5). Settings observed per send (B3, CB4): sets
     of `returned_model` per side; chain D reasoning counts; typed-v1 max tokens derived as `charge_bound -
     request_bytes(system, user) - RESERVATION_OVERHEAD` [V T/units.py:143-165, :213-214] against B of
     `solver-settings.json`; chain D `nominal_tokens` against M. Listed as resting on code equality only: temperature,
     stop, tools, chain G thinking and effort, provider route, credential file content, later turns and the ALFWorld
     game files (CB8), `scripts/weak_solver_probe.py` (vB1-X1).
R86. Output: per (chain, event, bench): matched items, both correct, both wrong, typed-v1 only correct, typed-v2
     only correct, unknown on either side; headed `earlier replicate (typed-v1, read <window>, lock per_cell_plain):
     noise and drift reference, never a baseline`. No item id, text, reply or per-item score. Stdout only.
R87. Sealing (A11): only the named keys are parsed (`request_sha256`, `unit`, `event`, `judge_version`, `correct`;
     per send `charge_bound`, `receipt.ok`, `receipt.returned_model`, `receipt.reasoning_chars`,
     `receipt.reasoning_tokens`); R47b's handler; tests grep every output for planted ids, texts and score keys.
R88. Size and test source: about 180 lines of code and 220 of tests. The test source root is made at zero cost by
     typed-v1's own `prepare --smoke` and fake smoke from `git archive 9ca2754` in the scratch directory (CB30 a).

### 1.F The readout

Line numbers of T/readout.py were re-checked at 8375ecb: all 22 cited starts match (vQ N6).

R63. Resolver (A13, CB14, CB24). New `readout._resolve(root, chain)` gives every pair `{'source': 'fresh' | 'alias'
     | 'void_alias' | 'pending' | 'invalid', 'of': <event>, 'class': <n>, 'independent': bool}` from the STATE,
     checked against the plan (self-hash) and the alias records (verified as in R44). An alias record without a
     matching state entry is reported as `stale_alias_record` and never shown. `independent` is true only for a fresh
     unit. With `read_plan = full` every pair is `fresh`.
R64. Loading (A13, CB14; A17 and CB9 have no object since RP1). `_load_read_unit` is never called for an alias pair;
     `by_bench[bench][event]` holds fresh typed-v2 units only, under their own event. Alias members live in a separate
     map `alias_of[(event, bench)] = representative event`. A consumer that wants a member's value dereferences it
     on purpose through the resolver, so a consumer that does not gets nothing and prints a dash, never a zero
     [V T/readout.py:428-441, :444-447, :457-480 tolerate absence]. `read_units_of` is unchanged.
R65. Closed mode (A14, E4). `_mirrors` is unchanged and reads `read-status/` only. A new `_aliases(chain_dir)` reads
     the alias records (closed names only, R80) into their own block; `_md_reads_closed` prints alias pairs from it as
     `same requests as <event>`, each with the representative's `unknown` / `infrastructure_unknown` /
     `configuration_errors` counts from the alias record (CB20). `_closed_mount_check` stays over fresh mirrors and
     says so; it lists the alias pairs with the plan's panel-level counts, marked `planned`.
R66. Tables and exports (CB18; RP3 2 a). A fresh pair shows its value; an alias pair shows `=<event>` and no number
     of its own (the representative's reading stands in the same column, D10 d), plus the representative's `unknown`
     / `infrastructure_unknown` / `configuration_errors` counts from the alias record, printed beside every alias
     cell as `u/i/c`, zeros included (RP3: "shown beside every member"; CB20's "optional" is overridden). Every
     exported grid number (5x5 matrices, CL terms, macro values) is an object `{value, source, of, independent,
     kind}`; an alias cell has `value: null` and `of: <event>`; a structural zero has `kind: 'structural'`.
     `accuracy_L` / `accuracy_H` [V T/readout.py:478-479] become such objects, so an old consumer fails loudly; the
     definitions block states the cell shape. A legend is printed under each table.
R67. Deltas and paired counts (CB16, CB17, E1; RP5). Two events of one class: `{'same_class': true, 'delta': null,
     ...}`; every column prints `-`, footnote `same requests, not measured`; never `0.0`, never `0 better / 0 worse`.
     Two events of different classes: computed from the two representatives' fresh units and labelled
     `requests: identical | different (d of n items) | unverified`, decided per item on first inputs (system hash,
     first selection request, offered list, `public_hash`, and `request_sha256[0]` when no program is offered),
     never on full send lists [V T/readout.py:448-450 compares full lists today, E1]. A delta whose items are all
     identical prints `noise sample, not an effect` and feeds R69. A contrast that is not same-phase (R89) is moved to
     a reference block: point difference only, no se, interval or counts, printed with both units' time ranges
     (R90) and the numbers of the recoveries that split it, or `model ids differ` (CB19).
R68. Baselines (RP1). Every "against C0" number uses the fresh representative of the C0 class; every "against C"
     number uses the fresh representative of the C class. No cross-date number enters any table.
R69. Noise (RP7; CB17). `in-run replicates: <n>` is printed beside every contrast, n = the number of deltas labelled
     identical by R67 (0 unless a fallback read two identical classes). `_same_request_noise` gets fresh units only and
     compares first inputs (E1). The practice-side gate noise of each step (`s<k>/noise.json`: `se_points`,
     `tau_points`) is shown beside the read tables. A same-phase ZebraLogic replicate is not built (RP7).
R70. Macro means and continual-learning metrics (RP4; CB13, CB15, E3). Values reach the formulas through the resolver;
     a term between two events of one class is structural, never a sample. `forgetting` and `forgetting_after_home`
     [V T/readout.py:491-496]: if one of the earlier events the max runs over shares the final event's class, print
     the measured maximum over the other classes when it is above 0, else `-` with the count of by-construction terms
     (JSON `{value: 0, kind: 'structural'}`); without such events, the signed measured maximum. Every macro row
     prints two pre-registered columns: (a) the five-bench mean with structural zeros entered as 0, labelled `k of 5
     structural`; (b) the mean over measured benches, labelled `n of 5` [V T/readout.py:514-521, :832-836 print neither
     today]. No standard error uses a structural zero as a sample; a comparison with a five-bench baseline uses (a).
     Neither value is comparable with a `full` run's max over noisy readings; the definitions block says so.
     Split phase (RP5; CB16, CB19; I-2): a term between two fresh representatives that are not same-phase (R89) is
     a reference value only. It is printed in the reference block (R67) as a point value and enters no macro mean and
     no maximum. A macro column (a) or (b) is printed only when every non-structural term is same-phase; otherwise it
     prints `mixed: k same-phase, m split, no mean`. The RP4 maximum of `forgetting` / `forgetting_after_home` runs
     over same-phase terms only and lists the split terms beside it; with no same-phase measured term it prints
     `split only`. The same holds for `gain_over_C0`, `gain_over_C`, `backward_transfer`, `forward_transfer` and
     `plasticity` [V T/readout.py:493-499].
R71. Costs (CB10, CB14). Fresh units only: `read_tokens` [V T/readout.py:580] and every token table exclude alias
     pairs; `_costs` [V T/readout.py:139-150] counts ledger units, which exist for fresh units only. One extra line:
     `economy: <a> pairs aliased, <f> fallbacks, <v> voided aliases`. No "tokens saved" figure is printed.
R72. Mount checks (A13, CB14). `_open_mount_check` [V T/readout.py:545-563] runs over fresh units only; alias pairs get
     the planned type / card / offered columns from the sealed plan (open mode only), marked `planned`.
R73. Blocks and status (CB20, CB29). New `_md_classes`: per bench the classes, members, representative, status,
     fallback reason, post-read check counts and the representative's `unknown` / `infrastructure_unknown` /
     `configuration_errors` counts. `readout.status` [V T/readout.py:645-655], `_md_state` and
     `run_typed.state_summary` [V scripts/run_typed.py:191-199] add `phase`, the mode, the short plan hash and
     `reads: {settled, of: 35, fresh_done, fresh_planned, alias, fallbacks, void_aliases}`. Ops side (no run code):
     the typed-v2 copies of `mounts.py` / `mounts2.py` print settled and alias counts from the state.
R74. Refusals. A pair that is `invalid` or `pending` shows no value. An `economy` root whose plan fails its self-hash
     renders no read table, only the error.
R89. Same phase (RP5; CB19). A contrast between two fresh units is same-phase iff (i) the sets of returned model ids
     over all sends (solver and selection) of the two units are equal, and (ii) no recovery between the earlier
     unit's first start and the later unit's last finish splits. A recovery does not split iff its pause lasted at
     most 24 h (recovery `at` minus `paused.at` [V T/chain.py:328, :356-358]) AND its owner record (kept as
     `recovery-consumed-<n>.json`) carries `same_phase: true`, written before the resume and blind to results,
     stating that no code, configuration, provider route or credential changed; a missing field splits. A crash or a
     kill records no pause (`pause` runs only in `run`'s handlers [V T/chain.py:325-329, :984-989]), so its recovery
     stores `paused: None` [V :357] and has no pause start (I-4). Its outage is then bounded from stored times: from
     the latest modification time earlier than the recovery `at` among the chain's unit files (`cells/*.json`,
     `done.json`, `done-stopped-<n>.json`) and plan files (3.2 to 3.4), to that `at`. Such a recovery does not split
     iff this bound is at most 24 h and the record carries `same_phase: true`; without such a file time it splits. It
     is never treated as 0 h. The automatic 60-s infrastructure retry inside `reads` is no recovery
     [V T/chain.py:610-616]. A split contrast is a reference only (R67). No re-read machinery is built: a re-read
     after a split is a separate owner decision, taken before the sealed reads are opened.
R90. Unit times and projected fields (CB19, E2). A fresh unit's time range = the earliest of `done.json` `started`,
     every `done-stopped-<n>.json` `started` and the oldest `cells/*.json` file time, to the latest finish or cell
     file time [V T/units.py:282-283, :296-297, :347, :428-429; a killed attempt writes no `done.json`]. The readout
     prints each fresh unit's range and model-id counts. `_project` [V T/readout.py:317-337] keeps, as ids and hashes
     only: `returned_model` of every solver and selection send, `mount.system_card_sha256`,
     `mount.selection.attempts[0]`, `mount.programs_offered`, `public_hash`; never text.

Layout example (invented numbers; base `historical` with R91 b, as configured for the run; B1..B5 stand for the
five benches; B1 changed at step 3, B3 at step 4, B5 at step 5; B3 is ZebraLogic, so its C is in the class of C0;
every contrast same-phase; B2's S5 unit has one infrastructure unknown). Under base `format` the C0 and C rows
exchange roles on B1, B2, B4 and B5 (R91 a).

    classes   B1: {C0}>C0 {C,S1,S2}>S2 {S3,S4,S5}>S5     B2: {C0}>C0 {C,S1..S5}>S5
              B3: {C0,C,S1,S2,S3}>S3 {S4,S5}>S5           B4: {C0}>C0 {C,S1..S5}>S5
              B5: {C0}>C0 {C,S1..S4}>S4 {S5}>S5
    fresh units 12 of 35, aliases 23, fallbacks 0, voided aliases 0

    event   B1          B2          B3          B4          B5
    C0      52.0        44.0        =S3 0/0/0   61.5        35.0
    C       =S2 0/0/0   =S5 0/1/0   =S3 0/0/0   =S5 0/0/0   =S4 0/0/0
    S1      =S2 0/0/0   =S5 0/1/0   =S3 0/0/0   =S5 0/0/0   =S4 0/0/0
    S2      62.5        =S5 0/1/0   =S3 0/0/0   =S5 0/0/0   =S4 0/0/0
    S3      =S5 0/0/0   =S5 0/1/0   44.0        =S5 0/0/0   =S4 0/0/0
    S4      =S5 0/0/0   =S5 0/1/0   =S5 0/0/0   =S5 0/0/0   38.0
    S5      65.0        57.0        49.5        71.5        41.0
    =X u/i/c  same requests as event X (not read again); u/i/c = X's unknown / infrastructure / configuration counts

    S5 - C0   +13.0       +13.0       +5.5        +10.0       +6.0                       in-run replicates: 0
    S5 - C    +2.5        -           +5.5        -           +3.0    (- : same requests, not measured)
                                                                                         in-run replicates: 0
    gain_over_C macro:  (a) +2.2, 2 of 5 structural   (b) +3.7, n = 3 of 5
    gain_over_C0 macro: (a) +9.5, 0 of 5 structural   (b) +9.5, n = 5 of 5
    forgetting B1: -  (2 by-construction terms; the other class gives 62.5 - 65.0, not above 0)

## 2. Change list

Estimates are added lines unless a minus is shown. Nothing outside `T/`, `scripts/`, `tests/`, `docs/` changes (D1).
`T/mount.py` gets no new function: the identity uses `mount_identity` / `_route` of Step 5m (RP9), counted there.

Run code (built after Step 6, O10):

| File | Change | Lines |
|---|---|---|
| `T/__init__.py` | `READ_PLANS`, `READ_PLAN_DEFAULT`, `IDENTITY_VERSION`, record versions, pause reasons (R1, 3.6) | +12 |
| `T/prepare.py` | `read_plan` and the smoke-only `read_plan_probe`: parameter, pair checks, `fields`, `load_manifest` (R2, R3, R7) | +20 |
| `T/reads.py` | `open_panel` taken out of `_read` (R24), with the D13 reset wrap in the same change; `_read` calls it | +30 / -14 |
| `T/readplan.py` NEW | the pass (R16-R34), capture selector and capture call (R17, R19), inputs (R78), lists and classes (R28-R31), plan write / load / verify (R32, R44), in-process plan restore (R44 c), replay core without the heavy lock (R47), post-read check (R41), alias records (R39), `write_once` with `.part` names (R80), `READ_PLAN_REASONS` (R81), `checkpoint` calls (R92) | about 460 |
| `T/chain.py` | state keys (R5); solver settings record (R75); learning guard (R79); `plan()`; replay child with its hash seed (R76); stop after plan (R77); `read_classes()` with both sweeps (R35-R39, R42); `reads(event, benches=None)`; R44 verification and recovery branch (own reasons, archive scope, void codes, second replay error); failure codes and void (R33 d); completeness and step markers (R46) | +225 |
| `T/readout.py` | resolver, alias map, `_aliases`, marks with `u/i/c` counts, export objects, dash rule, RP4 rule, two macro columns, split-phase rule and reference block, identical-request labels, same phase with the crash bound, unit times, `_project` fields, classes block, status (R63-R74, R89, R90) | +260 |
| `T/smoke.py` | smoke manifest fields (`economy`, `base_card = 'historical'`, probe `['C0', 'zebralogic']`); `fake_solve` gains `public_hash = canonical_sha256(item['public'])` (ADV8; R41 reads `mount.system_card_sha256`); the pass on the practice panel; `stop_after_plan` and `resume`; fake replay; `checkpoint` and the kill point of R92; assertions of 4.3 | +60 |
| `T/machinery.py` | a machinery symbol first used here goes into `REQUIRED`; none expected | 0 to +3 |
| `scripts/run_typed.py` | `prepare --read-plan`, `--read-plan-probe`; `run` / `smoke --stop-after-plan`; `smoke --resume` (X3); `--fake-kill-at` for `smoke --fake` and `plan-replay --fake` (R92); `plan-replay` with the R47b handler; read counts in `state_summary` | +85 |

Run tests:

| File | Content | Lines |
|---|---|---|
| `tests/test_typed_readplan.py` NEW | T1-T6 (both base values), T8-T12, T18, T19, T21-T23, T25, T26 | about 700 |
| `tests/test_typed_reads.py` | `open_panel` gives the items, views, vectors and registry calls of today's `_read` | +30 |
| `tests/test_typed_schedule.py` (schedule-lock) or `tests/test_typed_chain.py` | economy loop, order, both sweeps, resume points T16, `full` unchanged T17 | +245 |
| `tests/test_typed_readout.py` | T20 | +250 |
| `tests/test_typed_cli.py` | options, `plan-replay`, exit codes, T24, the three kill points of S2 (c) as subprocesses, grep of printed lines | +130 |
| `tests/typed2_bound_driver.py` (identity area) | `mount_identity`, capture and T7 under `bind_machinery` | +40 |

Total run side: about 1,155 lines of code and 1,395 of tests (fix2 added about 75 and 155). The existing 35-unit
tests stay as they are and run under `read_plan = full` (vQ N8).

Post-launch, not needed by the run (1.E): `T/replicate.py` NEW about 180; `scripts/run_typed.py` command `replicate`
+25; `tests/test_typed_replicate.py` NEW about 220 (T27, source from commit 9ca2754).

Untouched by this area: `T/units.py`, `T/library.py`, `T/tasktypes.py`, `T/embed_service.py`, the gate and writer
modules; in `T/mount.py` everything (Step 5m owns `_route` / `mount_identity`, Step 5b owns `base_card` and, if Q23
is answered yes, the unknown branch); in `T/reads.py` everything but the
extraction of R24; in `T/chain.py` `read_one`, `read_event`, `confirm` and all learning code apart from R79's guard.
No request text, cell tag, unit name, ledger identity or library / type map record changes.

## 3. Records and identity

3.1 Manifest. New field `read_plan` (one of `READ_PLANS`) and, in a smoke manifest only, `read_plan_probe`
    (`[event, bench]` or null). Inside the hashed `fields`. They enter no request, cell tag, unit name or identity.
    The field `base_card` belongs to D17 (Step 5b); this area only reads it (R91) and binds it in the plan.

3.2 Open plan `<chain>/read-plan.json`. `write_once`. Hashes and counts only. No time stamp.

    version: 'typed-v2-read-plan-1'      identity_version: 'typed-v2-mount-identity-1'
    chain, smoke, schedule, read_plan, base_card, manifest_record_sha256, solver_settings_sha256
    events: ['C0','C','S1','S2','S3','S4','S5']      order: [bench, ...]
    frozen: {event: {step, library_record_sha256, typemap_record_sha256,
                     library_file_sha256, typemap_file_sha256, receipt_sha256}}    (schedule-lock S6)
    benches: {bench: {items, item_set_sha256, registry_sha256 (entry without `run`; null in a smoke),
                      run_constants_sha256, inputs_sha256, identities_sha256, embed: {runs: 2, descriptive_flips},
                      events: {event: {arm, status, reason, identity_list_sha256, first_request_list_sha256,
                                       captured, typed, unknown, with_card, with_programs}},
                      classes: [{id, members, representative, identity_list_sha256, first_request_list_sha256}]}}
    read_order: [[event, [bench, ...]], ...]
    counts: {pairs, fresh, alias, fallback}
    plan_sha256 = canonical_sha256(all keys above)

    The panel-level counts may be open only because the pass runs after the last freeze (R79, R81).

3.3 Sealed files under `<chain>/test-read-plan/` (smoke: `practice-read-plan/`). `write_once`. They hold item ids.

    inputs-<bench>.json:     version, chain, bench, item_ids (sorted), view_sha256 per item, alfworld_views | null,
                             vectors: [run 1, run 2] | null (R30), views_sha256, vectors_sha256, record_sha256
    identities-<bench>.json: version, chain, bench, item_ids, inputs_sha256,
                             events: {event: {arm, step, status, reason, identity: [...], first_request: [...] | null,
                                      components: [{public_sha256, view_sha256, system_sha256, selection_sha256,
                                                    programs, type, source, unknown_reason, card_skill, offered}]}},
                             record_sha256

3.4 Alias record `<chain>/read-alias/<event>-<bench>.json`. Open, `write_once`, no time stamp.

    version: 'typed-v2-read-alias-1', chain, event, bench, kind: 'alias'
    representative: {event, unit}
    items
    identity_list_sha256: {member, representative}            (equal: the proof of D10 d)
    first_request_list_sha256: {member, representative}       (both null on ALFWorld)
    plan_sha256
    check: {items, equal, unequal}                            (R41 on the representative)
    representative_aggregate_sha256                           (from the representative's mirror)
    representative_counts: {unknown, infrastructure_unknown, configuration_errors}     (RP3 2 a, CB20)
    record_sha256

    Voided records move to `read-alias/archived/<event>-<bench>-<n>.json` (R42, R44).

3.5 Solver settings `<chain>/solver-settings.json` (RP2). Open, `write_once`, credential-free.

    version: 'typed-v2-solver-settings-1', chain
    benches: {bench: {model, route, max_tokens, nominal_tokens (null for G), thinking, reasoning_effort,
                      response_model_ids, read_timeout}}
    record_sha256

3.6 State (open). `state['read_plan'] = {mode, plan_sha256, file_sha256, bound_at, replay: {verdict, at, hash_seed},
    fallbacks: {}, failures: [] (pass and replay codes, R33 d, R44 d), void: false, void_reason: null, recoveries:
    []}`; `state['solver_settings_sha256']`. `state['reads'][event][bench]` gets `kind` (`fresh` implied when absent;
    `alias`, `void_alias`) and `status: 'alias'` for an alias.
    `state['phase']` takes the values of DESIGN 3.6 (`learn`, `read`); the pass sets `read` (R20).
    `done_units` gets `read-plan`, `alias-<event>-<bench>` for alias pairs (never `read-...`), and `step-0`..`step-5`
    at the end (R46). New pause reasons: `read_plan_failed`, `read_plan_changed`, `read_alias_invalid`,
    `read_plan_incomplete`, `stopped_after_plan`, `solver_settings_changed`.

3.7 What is hashed where.

| Value | Hash | Stored in |
|---|---|---|
| one item's request inputs under one event | `identity` (R9) | sealed identities |
| a panel under one event | `identity_list_sha256` (R28) | plan, alias record |
| first solver request of an item without offered programs (not ALFWorld) | sha256(system NUL user) (R19) | sealed identities |
| a panel's first requests | `first_request_list_sha256` | plan, alias record |
| views and vectors of a panel | `views_sha256`, `vectors_sha256` (R78) | sealed inputs; `inputs_sha256` in the plan |
| solver settings | `record_sha256`, file sha256 (R75) | the record, state, plan |
| the plan | `plan_sha256` (canonical) and `file_sha256` (bytes) | plan, state, alias records |
| alias record | `record_sha256` (canonical, without itself) | the record; the state entry keeps it as `alias_sha256` (R39) |

3.8 New open names (`read-plan.json`, `read-alias/`, `read-alias/archived/`, `solver-settings.json`) hold none of the
    words of `FORBIDDEN_PATH_WORDS` [V T/__init__.py:52-53: test, holdout, held_out, final, sealed, reserve,
    verifier_calibration, test_panel, testaccess]. The sealed name `test-read-plan` contains `test` on purpose and is
    written only with `allow_sealed=True`. No `carried` directory exists (RP1).

## 4. Tests

### 4.1 Fixtures

`smoke.fake_services`, `hash_embedder`, `synthetic_manifest` [V T/smoke.py:207, :218, :293] with the gate's fake
`identity_fn` [P gate.md change row T/smoke.py]. A helper writes scripted `s<k>/library.json`, `s<k>/typemap.json` and
`s<k>/frozen.json` for k = 0..5 as schedule-lock S5 / S6 prescribe (each saved with its own step, so record hashes
differ at every step even when nothing changed). Scratch: `/tmp/typed2-neutral`. No test opens a real result root. The
qualification test copies the pattern of tests/test_typed_chain.py:615-638 [V]. The synthetic manifest of every
economy test sets `base_card`: `historical` by default (the configured run, ADV1), and T3-T6 also run with
`format` (R91 a); T10, T26 and the fake smoke use `historical`.

### 4.2 Unit tests

T1  Manifest. `prepare` refuses `economy` + `interleaved`, an unknown value, `read_plan_probe` on a real root or with
    `full`; default `full`; `load_manifest` refuses a missing field or a forbidden pair; a resume whose state mode
    differs is a hard error; the CLI options reach `prepare`.
T2  One routing path (RP9). For arms C0, C, F and five item kinds (unknown type; typed, no card; typed with card;
    typed with programs; card and programs): `mount_identity` fields equal those of the capture-mounted
    `mount.mount` record (`system_card_sha256`, offered ids); `selection_sha256 == attempts[0]`, and None for C0, C
    and unknown items (their `selection` is None) and for `not_needed` (empty `attempts`), never an exception (ADV9);
    the capture selector is called twice at most and nothing is sent. Items where `mount` raises
    (unregistered signature under F but not under C0, missing vector, type map and library inconsistent, program
    without description) give fallback `identity_exception`; `mount_identity` raises too in the first three cases
    (H1).
T3  All events identical. Empty library at every step. Bench without reference card (ZebraLogic): one class
    {C0, C, S1..S5}, representative S5. Other benches: base `historical` (R91 b) {C0} > C0 and {C, S1..S5} > S5; base
    `format` (R91 a) {C0, S1..S5} > S5 and {C} > C. Fresh units = 5 + benches with a reference card = 9 under both
    (R40); every other pair has a verified alias record and an `alias-` marker; `done_units` holds
    `read-plan`, the fresh `read-` markers, the `alias-` markers and `step-0`..`step-5`; the requests sent are exactly
    those of the fresh units. No `TestAccess` and no file under `shared/test/` before the pass sets the phase `read`;
    no read unit directory before `read-plan` is marked (CB27).
T4  One panel changed at step k (k = 1, 2, 3). Card accepted for one type of bench B: base `historical` {C0},
    {C, S1..S(k-1)}, {S(k)..S5} (k = 1 gives {C} alone); base `format` {C0, S1..S(k-1)}, {C}, {S(k)..S5} (k = 1 gives
    {C0} alone). Variants: a program instead of a card (`selection_sha256` and
    `programs` set; no capture for those items); a card for one type among several (some items unchanged: still two
    classes, the all-items rule).
T5  Change at step 5. Base `historical`: {C0}, {C, S1..S4} > S4, {S5} > S5; order: S5 on five panels first, then S4
    on that bench, then C0; C has no unit. Base `format`: {C0, S1..S4} > S4, {C}, {S5} > S5; order S5, S4, then C; C0
    has no unit.
T6  Type-map-only change (items go from unknown to typed without skills, or to `distance_above_p95`). Base `format`,
    and base `historical` with the unknown branch mounting the base card (Q23 yes, R91 b): one class; the sealed
    components show the different `type` values; `descriptive_flips` counted; no extra fresh unit. Variant for Q23
    no (R91 c, the unknown branch of 8375ecb under `historical`): the events before and after the flip have
    different identity lists (a real request difference) and are never one class: an all-unknown panel joins C0's
    class, an all-typed panel C's, a mixed panel is its own class; the fresh count follows R91 (c). The variant
    that matches the coordinator's answer to Q23 is the binding one.
T7  Label neutrality (regression test, bound driver against the bound worker). One state with an enabled program
    whose hook writes a note, solved under two unit names with a recording fake worker: equal hook argument
    sequences, equal solver request hashes for every send, load requests that differ only in `package_sha256`.
T8  Identity collision attempts; different list hashes except (f): (a) two items swap their system texts; (b) program
    body lists [x, y] against [xy], one against two programs; (c) same programs, other library order; (d) equal name
    and description, other body; (e) selection request present against none, same system text; (f) card '' against
    blank-only text: EQUAL; (g) card texts differing by one trailing newline; (h) one item id replaced, identities
    equal; (i) empty panel: refused, never a class; (j) other bench, equal texts; (k) a `fallback` event whose list
    hash equals another event's: still its own class; (l) equal public part, different view; (m) equal identity
    lists, different first-request lists: both `first_request_mismatch` (R29).
T9  Tampering and recovery. (i) one field of an alias record edited: R46 pauses `read_alias_invalid`; the readout
    shows `invalid`. (ii) `read-plan.json` edited: `read_plan_changed`; after the recovery the in-process recompute
    restores the bound bytes with `write_once` and the child replay is `equal` (R44 c). (iii) a sealed inputs or
    identity file edited or deleted: `read_plan_changed`; after the recovery the plan is void with `void_reason =
    'sealed_file_invalid'`, never restored (R44 c). (iv) a settled alias record deleted: R46 pauses
    `read_alias_invalid`; after the recovery the pair is unsettled, the replay is equal and R39 writes the same bytes
    again; a crash between an alias record and
    its state entry: the next settling finds equal bytes and goes on. (v) recovery: replay equal, the run continues;
    replay different, plan void, EVERY alias of the chain (settled ones included) is read fresh in the final sweep
    and the chain completes; replay error, nothing archived, paused again; a second replay error with the same code:
    plan void (`replay_error`), all aliases read fresh, the chain completes (R44 d). (vi) a rebuilt mirror changes
    `representative_aggregate_sha256`: `read_alias_invalid`, never a rewrite. (vii) a changed `s<k>/frozen.json` or
    `solver-settings.json`: pause `frozen_state_changed` / `solver_settings_changed`, nothing archived; the resume
    after restoring the file goes on (I-16).
T10 Replay (manifest `base_card = 'historical'`). Two computations in two processes with different
    `PYTHONHASHSEED` give the same bytes. Mismatches: a changed frozen file, a changed panel, a changed inputs file,
    a recomputed non-ALFWorld view that differs from its stored hash (`view_mismatch` on a pass re-run), a replay
    whose mounts are built with `format` instead of the manifest's base: `plan-replay` prints `different`, exit 3,
    and a resume pauses. A missing qualification pointer on a real-root fixture: `different`, code
    `qualification_missing`, and no qualification is started. A changed embedder output with intact inputs files:
    `equal`, plus a non-zero information count.
T11 Zero calls. The pass runs with services whose solver, role and selector clients raise when used; the ledger file
    is byte-equal before and after; no ledger unit exists for `read-plan` (A8); `parse_read_name` of
    `test-read-plan` and `practice-read-plan` is None and `read_units_of` ignores both. The only new files are the
    sealed inputs and identity files, `read-plan.json`, the registry / qualification files and the state.
T12 Consent, registry, qualification (real `Pause` class and real `recover`). No consent: nothing is opened, the
    chain pauses as a read does. With consent: the pass creates the registry entry and calls the qualification once
    with the plan label; a later read unit verifies; the second chain verifies. A stubbed `_sheet_qualification`
    raising route-B `Pause('qualification_paused', 'attempt-1', ...)` inside the pass: the detail is
    `Pause:qualification_paused`, `recover` writes `attempt-1/recovery.json`, the next resume admits attempt 2,
    qualifies and writes the plan. The pass killed after two registry entries: the resume writes no second entry and
    the same plan. Smoke: no consent call, no registry file. ALFWorld preparation resets of the pass (R23; ADV13,
    I-15): with `unit_shared` and a recording `v218_lock` fake, every reset of the pass runs inside
    `v218_lock.call(reset, lock_setting, 'alfworld', unit=...)`; with `per_cell_plain` it stays bare.
T13-T15 Retired (carry; RP1). The replicate command has T27.
T16 Resume at each point P1..P8 (P3b included), P11, P12 of R45 (a scripted stop at the point; then
    `recovery.json` and `run --resume`): one record consumed per resume (`recovery-consumed-<n>`,
    `recovery-applied-<n>`); the final `done_units`, alias records and the multiset of request hashes equal those of
    an uninterrupted run; no completed cell is sent again. Fresh-pair completeness (R46; I-15): a fresh unit whose
    `done.json` has `cells` != `expected_cells`, or `expected_cells` != the plan's item count, pauses
    `read_plan_incomplete`. Order of R39 (ADV12): a stop between the `read_mounts` check and the record leaves no
    record, state entry or marker of that member. A `.part` file left in `read-alias/` or `test-read-plan/` by a
    scripted crash is never read as a record and is removed by the next pass or settling (R80).
T17 `full` is unchanged: `learn_first` + `full` gives schedule-lock's units, order and request hashes, no
    `read-plan.json`, no `read-alias/`; `interleaved` + `full` the typed-v1 order; the existing 35-unit tests pass.
T18 A fresh unit under `economy` equals the same unit under `full` (unit name, cell tags, request hashes); in the
    fake smoke every fresh C0, C and card-only S cell's `request_sha256[0]` equals the plan's capture (X2).
T19 Fallbacks. An identity call that raises for one event: that pair is its own class, read fresh. A second embedder
    batch that changes one S event's identity list: that event `embedder_unstable`; one that changes only a
    descriptive field: counted, no fallback. Post-read mismatch: every alias of the bench (settled ones included)
    voided and read fresh, no pause (RP10); the representative already read is not read again: each pair is read
    fresh at most once (R36; I-15). A capture that records zero sends or two sends: that (event, bench) is
    `capture_failed` and read fresh (R19; I-15). `read_plan_failed` twice with the same code: void, all 35 pairs
    fresh, the chain completes (RP11). In no case is a read removed.
T20 Readout. A fixture root with fresh, alias, void-alias and fallback pairs. The UNPATCHED typed-v1 `_open` on it
    yields no number for any same-class pair (no 0.0, no 0/0 counts, no zero-flip noise, no false
    `unknown_skill_ids`), one case per consumer: `_panel`, `_pairs`, `_same_request_noise`, `_five_by_five`,
    `_formulas` / `_cl_metrics`, `_macro`, `_open_mount_check`, `read_tokens` (CB14). Patched: every table and export
    carries the marks; every alias pair is listed exactly once; a delta inside a class is `-` and JSON
    `null`; alias cells export `value: null`; `forgetting` follows RP4 (layout example B1 prints `-` with 2
    by-construction terms); both macro columns with k and n; `in-run replicates` beside every contrast; a split-phase
    contrast is in the reference block only, with both time ranges and the splitting recovery numbers (R67); a CL
    term between split representatives enters no mean and no maximum, and a macro with a split term prints `mixed:
    k same-phase, m split, no mean` (R70; I-2); every alias cell shows the representative's `u/i/c` counts, zeros
    included (R66), and closed mode lists them too (R65); `read_tokens` counts fresh units only; closed mode lists
    aliases separately and `all_present` is true when every fresh mirror has its fractions; a stale alias record is
    reported, not shown; a projected cell holds no request or reply text; a `full` root renders as today. Phase
    cases (R89, R90; I-4, I-15): a recovery with `paused: None` (the smoke's kill of S3 b) whose latest earlier unit
    file is 10 min older than the recovery `at` and whose record has `same_phase: true` does not split; the same
    without `same_phase`, or with no earlier unit file, splits; a killed attempt without `done.json` still gets a
    time range from its cell file times.
T21 Learning closed (A7). With `s3/frozen.json` removed at P2, P3 and P5: zero role and writer calls, no write under
    `s3/`, pause `frozen_state_changed`.
T22 `write_once`. Exclusive create; equal bytes accepted; different bytes raise the mapped reason; a crash between
    the temporary file and the link leaves no partial target; the temporary name is `.<name>.<pid>.<hex>.part` and no
    reader lists it (R80; ADV11).
T23 Sealing grep (A10, A11). A fake pass with planted item ids and texts, an embedder failure whose stderr carries a
    planted text, a corrupt sealed file: `read-plan.json`, `read-alias/*`, `solver-settings.json`, `state.json`,
    stdout and stderr hold no id, no string over 64 characters outside hash fields and no reason outside
    `READ_PLAN_REASONS`.
T24 Stop and smoke resume (CB21, X3). `run --stop-after-plan` and `smoke --stop-after-plan` exit 5 with status
    `paused` and reason `stopped_after_plan`; resume without `recovery.json` is a hard error; with it the chain
    continues; a resumed process with the flag does not stop again.
T25 Solver settings (RP2). The record holds no URL, key, proxy or credential path; written once; a resume with a
    changed value pauses `solver_settings_changed` before any call; `full` writes it too.
T26 Automatic replay (RP6). The real child process runs after the binding; `equal` lets the chain continue; a
    planted difference in a sealed identity file pauses `read_plan_changed` (`replay_different`); a child that dies
    pauses with `replay_error:<code>`, and a second death with the same code voids the plan (R44 d); no read unit
    starts before the replay is `equal`. The child gets a `PYTHONHASHSEED` other than the parent's, recorded in
    `state['read_plan']['replay']` (ADV10). The replay never enters the heavy lock: with services whose `heavy` raises
    when entered it completes `equal` (R47; ADV5).
T27 (post-launch, 1.E) `replicate` on a source made by typed-v1 code (R88): counts right; a G source with reasoning
    passes; nothing is written in either root; outputs grep clean. Sealing cases (A11, vA2; I-12): a corrupt cell file,
    a cell without `request_sha256`, a cell naming another unit: each is counted by cause, the command does not
    crash, and a grep of stdout and stderr for the planted item ids, texts and score keys finds nothing.

### 4.3 The smoke run

S1. Manifest. `prepare --smoke` with `schedule = learn_first`, `read_plan = economy`, `memory_lock = unit_shared`
    (D13), `base_card = 'historical'` (D17), the run's widths (D15) and `read_plan_probe = ['C0', 'zebralogic']`
    (ADV4). On ZebraLogic C0 and C send the same requests under every base (R91 d) and C is later, so C0 is never a
    representative there: the probe always turns a would-be alias into a fresh read. (C0 of another bench is its
    own class under `historical` and would exercise nothing.) Smoke read units are `practice-read-<event>-<bench>`
    on held-out practice items, without consent and without `TestAccess` [V T/reads.py:64-68, :244-250]; the pass
    uses the same items (R25).
S2. Fake smoke (local, CI and the Linux pre-check; real pass code, fake solve and embedder). (a) The CLI form `smoke
    --fake --stop-after-plan` on the synthetic manifest, which carries `learn_first`, `economy`, `base_card =
    'historical'` and the probe: exit 5 after the binding and an `equal` replay by the real child process (R76);
    `recovery.json`; `smoke --fake --resume` completes. (b) A scripted test variant (in-process replay, R76) fixes
    the classes (R91 b): one non-ZebraLogic bench never changes (alias path: C, S1..S4 alias S5; C0 fresh); one bench
    gets a card at step 3 (fresh before / after: {C0}, {C, S1, S2} > S2, {S3, S4, S5} > S5); ZebraLogic carries the
    probe (fallback path: C0 fresh with reason `smoke_probe`, C and the S events in their classes); inside the S5
    unit of a text bench an injected interrupt after two cells, then `recovery.json` and resume: the unit completes
    and its done cells are not sent again. End assertions: counts of fresh / alias / fallback equal the script; the
    readout shows `=X`, the fallback and the classes block; zero calls in the pass; the replay is `equal`. (c) Kill
    points with the real pass code (R92; ADV7): `smoke --fake --fake-kill-at <point>` as a subprocess in its own
    session, once for each of `after-first-inputs`, `after-plan-file` and `replay-child`, each followed by
    `recovery.json` and `smoke --fake --resume` (without the option). Asserted against an uninterrupted fake smoke
    with the same script: byte-equal `read-plan.json` and sealed files; no `.part` file is read as a record and none
    remains after the resume; no class is read twice (every fresh cell has one send); the same final `done_units`,
    alias records and multiset of request hashes.
S3. Real smoke on dl (small, paid; both chains; the real pass code on the practice panels). Same manifest.
    (a) `smoke --chain X --stop-after-plan`: exit 5 after the plan is bound and the automatic replay is `equal`; the
        ledger is unchanged across the pass. Ops checks the plan counts (planned fresh units per bench), writes
        `recovery.json` and runs `smoke --chain X --resume`.
    (b) One kill inside a fresh read unit (RP6). An event reads all its pending benches at once (`READ_WORKERS = 5`
        [V T/chain.py:59, :576-587]), and the first sweep reads S5 on all five panels, so a kill inside a text unit
        of S5 also kills sheet and ALFWorld units (ADV3). Kill point, chosen by ops from the bound plan's
        `read_order` at the stop of (a): the first event whose bench list holds text benches only (SearchQA,
        OfficeQA, ZebraLogic), after at least one cell of it is done. If the plan has none, ops kills in S5 once the
        SpreadsheetBench and ALFWorld units of S5 have their `done.json` and a text unit still runs. If that moment
        does not come either, the kill is a declared cleanup test inside S5: before the resume ops lists the
        containers named `execskill-sbx-*`; the resumed units' drains remove their own leftovers (main-v10 cleanup
        grace 120 s [V T/chain.py:1115, :1161-1165; X/profiles.py:206-208; X/sandbox/client.py:292-313]) or pause
        with `CleanupUnconfirmed`, which ops resolves by the existing procedure; an untagged scoring container
        (`execskill-sbx-<uuid4>`, which no unit drain covers [V X/sandbox/client.py:12-15, :29-31]) is reported
        and removed by ops by its exact name. Then `recovery.json` (with `same_phase: true`, R89) and `smoke
        --resume`: the units complete; every done cell keeps its single send.
    (c) The smoke passes only if: the pass sent nothing; at least one alias pair exists and its representative passed
        R41; at least one fresh unit completed; the probe pair was read fresh as its own class with reason
        `smoke_probe`; the probe's `identity_list_sha256` and `first_request_list_sha256` in the plan equal those of
        ZebraLogic's C, so without the probe it would have been an alias and the plan holds one fresh unit more
        (ADV4); (a) and (b) both completed; after the smoke no container whose name starts with
        `execskill-sbx-<chain>-` remains and every container listed in (b) is accounted for (ADV3); the readout
        renders the classes block; R46 passed.
S4. Not exercised before the real run (residual, section 6 K-H): the real `panel_tasks` / registry /
    qualification path of the pass (the smoke opens no test panel), and the pass's live ALFWorld preparation resets
    under `v218_lock.call` (R23): smoke items carry registered views and `_from_services` skips resets in smoke
    mode [V T/reads.py:229] (ADV13). T12 runs both with the real `Pause` and `recover` and a recording `v218_lock`
    fake; a failure there costs a pause, not tokens.

## 5. Interfaces

5.1 schedule-lock Part A (learn_first, frozen receipts). This area builds on it: it adds a guard to S9 (R79) and
    narrows S3 and S7 under `economy` only; S1, S2, S4-S6, S8 and S11 are used as written, and S10 with the phase
    names of DESIGN 3.6 (5.7).
    - Used as specified there: the `schedule` field; `s<k>/frozen.json` (S6); `freeze`, `load_frozen`, `bind_read`;
      the pauses `frozen_state_changed`, `read_mount_changed`; `Services.heavy(bench, unit=None)`; `phase`
      (values of DESIGN 3.6: `learn`, `read`; no new value) and `current_unit` (`read-plan` during the pass). These
      exist in the spec only (N9).
    - Narrowing 1, S7: the first caller of `panel_tasks` under `economy` is the pass (R22); same function, arguments
      and files.
    - Narrowing 2, S3 and change row 9: under `economy` the run order is R20 and the read order R36 (D10 e).
    - S6 `read_mounts`: the pass fills all seven events (Q14); R39 checks a member's entry when it settles it.
    - S9 and change rows 5, 6: R79's guard holds for `learn_first` with both read plans (A7).
    - schedule-lock leaves `T/reads.py` and `T/mount.py` unchanged; this area extracts `open_panel` (R24) and adds
      nothing to `T/mount.py`.
    - Its Q2 (zero-call consent check at chain start) is kept; R21 is the binding check.
5.2 Lock mode (schedule-lock Part B, D13). The pass takes the heavy lock for the SpreadsheetBench panel opening as
    `_read` does and wraps the ALFWorld preparation resets as read units do (R23). The capture takes no lock: no
    container and no native slot (R19). The replay re-opens the panels without the heavy lock (R47). The lock mode
    enters no identity (R14).
5.3 Identity and manifest (`spec/identity.md`). `read_plan` and `read_plan_probe` join `fields` and `load_manifest`.
    `own_root` is the first call of `plan-replay` and `replicate` (for `--root`). The start checks of the bound
    machinery run before the pass; the replay child is bound to the same snapshot (R76). Machinery symbols first used
    here go into `machinery.REQUIRED`. The container scope is not hashed (R14). Bumped library and type map versions
    change record hashes, not requests; the identity uses no record hash. Consent keeps its six fields. Exception to
    rule 17 for `replicate --source` only (R83). Interface requirement on the identity area (vB1-X1, adopted by the
    RP tail; it was Q19): the machinery check of `spec/identity.md` 1.9 also pins the `scripts.*` modules the bound
    run imports, at least `scripts/weak_solver_probe.py`, which sets chain G's thinking, effort and max tokens and
    the request body of both chains and is on neither pinned list (vB1). The solver settings record (R75) stays as
    listed; the post-read command lists the module as code-only (R85).
5.4 Gate (`spec/gate.md` 1.6, D5). The read identity uses the same `mount_identity` / `_route` and
    `Services.identity_fn` as the gate (one routing path, RP9), with `forced = None`. Read cells have no repeat index.
    Every gate decision is taken before the pass; none reads a test cell or an alias (F4, D12).
5.5 Readout. Other areas also edit `T/readout.py` (D5 folds repeat labels; schedule-lock adds `schedule` and `phase`;
    D16 adds the member gains of each accepted skill, step 5x; D17 names the learning base label B, step 5b). This
    area's edits come last; shared functions: `status`, `_md_state`, `chain_readout`, `markdown`, `_project`. Under
    D17 the reference row of learning is C: the readout keeps both `S<k> - C0` and `S<k> - C` (layout example).
5.6 D2 / D3 / D4. No interface. A longer card changes the system text, hence `system_sha256` (R10 row 1).
5.7 Conflicts: none with D9, D10, D12, D13, D15, D16, D17 or schedule-lock Part A. D11 is applied as revised by RP1.
    Where schedule-lock S10 names the phases `learning` / `reading`, DESIGN 3.6 (`learn` / `read`) holds. D16 (d)
    leaves the reads unchanged: a member panel whose requests a later bench's skill changes gets one more class
    (R91, last paragraph); its learning cost is in K-D. D17 changes which events share a class, not the rule (R91);
    the interface point it leaves open is Q23 (5.8).
5.8 Step 5b (D17, base card). This area needs from 5b only `base_card` in the manifest and a `system_card` /
    `mount_identity` / `mount` that read it; the pass, the replay and the read units call them unchanged (RP9). Open
    point: whether the unknown-type branch also mounts the base card (Q23). Either answer keeps the identity correct;
    the answer fixes the binding variant of T6 and the class expectations of R91 (b) or (c).

## 6. Risks and questions for the coordinator

Risks.

K-A. A wrong identity would alias two different request sets and print a false dash. Guards: one routing path (RP9,
     T2); exact first requests for every item without offered programs on four benches (RP3), which also prove the
     members; R29 (c); R41 on every representative; RP10 voids the bench's aliases on any mismatch; the replay.
     Residual: on ALFWorld and for items with offered programs a member's proof is the equality of two values of one
     tested function.
K-B. No in-run replicate (RP7). Small effects cannot be told from noise by read data alone; the readout says so
     beside every contrast. A same-phase ZebraLogic replicate (about 1.0 to 1.2 M tokens per chain) is an owner
     option only.
K-C. The read phase spans most of a day; S5 is read first and the earlier states later. Same phase is defined by
     R89 (24 h bound, RP5); the readout prints every fresh unit's time range.
K-D. A fallback raises the cost up to the `full` plan without a pause (F12 worst case 98.9 / 121.2 M tokens, 66 and
     71 per cent of the caps). D16 adds 1.5 to 4 M and D17 about 10 to 20 M per chain [I, addendum D16 e, D17 cost],
     so the worst case grows to about 123 M of 150 (82 per cent) for G and 145 M of 170 (85 per cent) for D; the caps
     hold (D17). The pass prints the planned number of fresh units.
K-E. Retired (a carried C read on another date; RP1 removed the carry).
K-F. ALFWorld machine time in the pass: the preparation resets once per chain, under the D13 lock; no capture.
K-G. Embedder drift between the pass and a representative's own unit: R41 fails and RP10 voids that bench's aliases
     (extra cost). Residual (ADV14): R41 checks only the representative's routing under the read unit's own vectors.
     A member whose own type map would route an item differently under those vectors is not checked at read time; the
     alias of such a member rests on embedder determinism, measured by R30's two runs in the pass and by the replay's
     information count (R47).
K-H. The pass's real consent / registry / qualification path and its live ALFWorld preparation resets under
     `v218_lock.call` (R23) first run in the real run (the smoke reads practice panels and skips resets; CB31,
     ADV13). Mitigation: T12 with the real `Pause`, the real `recover` and a recording `v218_lock` fake; R33 (a); a
     failure costs a pause, not tokens.

New questions, each with a recommendation.

Q19. Retired: vB1-X1's correction is adopted by the RP tail; it is now an interface requirement on the identity
     area (5.3).
Q20. The smoke-only `read_plan_probe` (R7, R31), set to (C0, zebralogic), a would-be alias under every base (S1),
     is the only way to run the fallback path with the real pass on the real smoke without a code switch.
     Recommended: accept; `prepare` refuses it on a real root.
Q21. A replay child that crashes or times out pauses `read_plan_changed` (detail `replay_error:<code>`, R76), not
     an infrastructure retry; a second error with the same code voids the plan (R44 d; I-3, ADV6), so a
     deterministic replay defect cannot strand the chain after all learning. Recommended: accept (any doubt reads
     fresh).
Q22. `solver_settings_changed` pauses a resume whose recomputed record differs (R75); the owner then decides whether
     the run may go on. Recommended: accept; it is what write-once means for this record.
Q23. (I-1, ADV2; for Step 5b) Under `base_card = 'historical'`, must the unknown-type branch of the routed mount
     return `system_card(bench, '')` (= `historical_text(bench)`, arm C's text) instead of the format block?
     Evidence: at 8375ecb that branch returns `'', format_block(bench)` directly and never calls `system_card`
     [V T/mount.py:200-204; typed items use `system_card` at :238]; D17's build list names only `system_card` by base.
     If only `system_card` changes: (a) before its own step a bench's items are mostly unknown (unseen signature), so
     its S1..S(k-1) rows read the C0 text (format lines only) while C is the reference: the 5x5 would show a drop
     from C toward the no-skill row on benches not yet learned (D17's reason: C gives what C0 lacks, 11 to 20 points
     on three bench-chain pairs; F15), against D17's "a bench whose type learns nothing then reads exactly C" and the
     owner's "no drop on dissimilar benches"; (b) panels that mix unknown and typed-without-card items match neither
     C0 nor C, an extra fresh class per bench (R91 c); (c) a type-map-only change becomes a request change (T6
     variant), and R30's descriptive flips between unknown and typed without skills, the common typed-v1 case (vH),
     become identity flips; (d) on the learning side D17's "shared F of a new type with no skill = B" fails as soon
     as one gate item is unknown under the new type map (for example `distance_above_p95`), because sharing needs
     equal identities on every gate item (gate.md 1.6 rule 22), so `F#1..3` run (cost only) [I]. Recommended: yes; 5b
     changes the unknown branch with `system_card` and tests that an unknown item and a typed item without a card
     mount byte-equal system text under both base values (with `format` both stay the format block, so every golden
     request is unchanged). The read plan is correct under either answer; only R91's case and T6's binding variant
     follow it.
Q24. (I-3 b) A non-stop exception raised by the pass's own code after the panel path and outside the per-item
     identity calls (a defect of `T/readplan.py`) is classified by none of R33 (a) to (c): it pauses
     `exception:<Class>` and recurs on every resume, and `spec/identity.md` rule 9 forbids a code change inside the
     root, so the chain would stay paused after all learning (F12: 32 to 59 M tokens of learning per chain) until a
     new root. RP11 limits `read_plan_failed` to detected inconsistencies, so widening it is a coordinator decision.
     Options: (A) count it as `read_plan_failed` code `pass_exception` (class name only, R81), so that R33 (d) voids
     the plan at the second occurrence and all 35 pairs are read fresh (the `full` reads in the economy order); (B)
     accept the dead end (stop, fix the code, new root, learning again). Recommended: A (safe direction: no alias
     without a plan, no read removed; cost bounded by the `full` plan; exceptions of the panel path keep propagating,
     R33 a).

## 7. NOT DONE

N1.  Closed (vQ): the SpreadsheetBench first request and the capture receipt shape [V X/solver.py:728-753;
     X/backends.py:90-111, :480-482]; R19 is [V].
N2.  Closed (vQ, vH): sandbox, router and `card_for`; R14's residual is only the static screen (N13).
N3.  Closed (vQ): registry, qualification, resets [V X/evaluation.py:243-301, :506-537]; R18, R22, R33.
N4.  Closed (vQ): `run` handles `Paused`, `units.Stop`, then `Exception` with `_pause_detail` [V T/chain.py:978-989];
     R33.
N5.  Closed (vQ): `slot_root` and `history_root` cannot change a C0 / C request [V T/chain.py:1097-1099;
     T/prepare.py:90, :280].
N6.  Closed (vQ): all 22 cited T/readout.py starts match 8375ecb.
N7.  Closed: `FORBIDDEN_PATH_WORDS` (3.8).
N8.  Closed (vQ): the existing tests fix 35 reads and the typed-v1 order [V tests/test_typed_chain.py:190-195, :247,
     :628, :673]; they stay under `full` (T17).
N9.  Closed (vQ): schedule-lock's methods exist only in its spec; this area is built after Step 6 (O10).
N10. Half open (vQ): the cell key of the returned model is [V T/units.py:33-34, :222; T/mount.py:425-429]. Whether the
     typed-v1 smoke root on dl is usable is not checked (no ssh); since RP1 neither the run nor the smoke needs it
     (R88 makes its own source).
N11. Closed by the addendum F12 (token projection); this file adds no estimate.
N12. Not applicable to this correction.
N13. Open: `X/policy.py` was not opened (R14 residual [I]).
N14. Open: `mount_identity` and `_route` do not exist yet (Step 5m); T2 binds the read identity to them.
N15. Open [I]: that `evaluation._with_views` accepts a reset function that returns the stored ALFWorld views (R47
     replay); checked when coding.
N16. Open: embedder determinism across processes is not measured; the replay's information count (R47) measures it.
N17. This correction re-opened at 8375ecb: T/mount.py:40-70, :145-440; T/reads.py:40-350; T/chain.py:240-420, :560-660,
     :936-1000; scripts/run_typed.py:100-290; T/library.py:70-90, :125-155, :200-226; T/smoke.py:95-145, :240-300; and
     X/solver.py:640-700, :725-760 in the tree. Other [V] citations are the verifiers' (named where only they opened
     the file).
N18. fix2 re-opened at 8375ecb: T/mount.py:36-100, :140-300, :300-440; T/smoke.py:200-300; T/chain.py:59, :240-262,
     :300-420, :560-625, :936-1000, :1113-1172; T/reads.py:113-176, :196-300; T/units.py:45-64, :276-300, :340-432;
     T/prepare.py:266-290; scripts/run_typed.py:60-76; and in the tree X/sandbox/client.py:10-34, :140-165,
     :196-330; X/evaluation.py:225-345; X/profiles.py:68-69, :150-153, :206-208; X/prelaunch.py:28-48;
     X/v222_cards.py:127-139. Not opened: `_with_views` (N15), `_swept_qualifications`, the frozen `_native`
     (cited from the client's docstring only), ALFWorld environment processes (whether a SIGKILL can leave one
     behind is [I]; S3 b avoids the case where it can).
N19. Open for the coordinator: Q23 (unknown branch under `historical`) and Q24 (pass-internal exception).

## 8. Critic findings and resolutions

### 8.1 First correction (fix1)

Severity as verified. Outcome: accepted / partially accepted / refuted / dropped with the carry (RP1).

| Id | Severity | Outcome | Where |
|---|---|---|---|
| A1 | must-fix | partially accepted (consequence refuted: a raising F mount stops the unit, vA1) | R16, R17, T2 |
| A2 | minor | partially accepted (the label reaches no hook input or request; interim rule not needed) | R14, T7 |
| A3 | must-fix (carry only) | accepted, applied to the post-read command (RP tail; O1 remark refuted) | R85 |
| A4 | blocker for D11 | dropped with the carry, RP1 | - |
| A5 | must-fix (void and cost, not false equality) | partially accepted | R30, R45, R47, R78 |
| A6 | must-fix | accepted | R39, R42, R44, R46, 3.6, T9, T19 |
| A7 | must-fix | accepted | R20, R79, T21 |
| A8 | minor | accepted | R18, T11 |
| A9 | must-fix | accepted | R18, R22, R33, T12 |
| A10 | minor | accepted | R81, 3.2, T23 |
| A11 | must-fix | accepted, for `plan-replay` and the post-read command | R47b, R87, T23 |
| A12 | must-fix (R19b part) | partially accepted (claims on unsent cells, ALFWorld and view refuted, vA2); RP3 | R19, R29, R41, 3.4 |
| A13 | must-fix | partially accepted; max metrics by RP4 | R63, R64, R67, R70, R72, T20 |
| A14 | minor | accepted | R65, T20 |
| A15 | must-fix | dropped with the carry, RP1; observed settings counted by the post-read command | R85 |
| A16 | minor | accepted | R10 row 7, R32 c |
| A17 | must-fix | dropped with the carry, RP1 (no carried unit exists) | R64 |
| CB1 | blocker | dropped with the carry, RP1 | - |
| CB2 | must-fix | dropped with the carry, RP1; reasoning counts per chain in the post-read command | R85 |
| CB3 | must-fix | dropped with the carry, RP1; model-id sets in R85 and the same-phase rule | R85, R89 |
| CB4 | must-fix | (a) accepted as RP2; (b), (c) carry parts dropped, observed and code-only lists in R85 | R75, R85, 3.5 |
| CB5 | must-fix | accepted, applied to the post-read command | R85 |
| CB6 | must-fix | accepted, applied to the post-read command | R85 |
| CB7 | minor | partially accepted, applied to the post-read command | B2, R85 |
| CB8 | must-fix | dropped with the carry (ALFWorld C is read fresh); later turns listed as code-only | R85 |
| CB9 | blocker | dropped with the carry, RP1 | R64 |
| CB10 | must-fix | dropped with the carry; alias pairs leave the token tables | R71 |
| CB11 | must-fix (decision) | decided by RP1 (option B: read C fresh, replicate only) | 1.E, R68 |
| CB12 | must-fix | dropped with the carry, RP1 (nothing is copied) | - |
| CB13 | blocker for the readout code | partially accepted; rule by RP4 (its extra column is not built) | R70, T20 |
| CB14 | must-fix | accepted | R64, R71, R72, T20 |
| CB15 | must-fix | accepted | R70 |
| CB16 | must-fix | accepted in its option-B form: no cross-date term; split contrasts are references | R67, R68, R89 |
| CB17 | must-fix | accepted, comparing first inputs (E1) | R67, R69 |
| CB18 | must-fix | accepted | R66 |
| CB19 | must-fix (decision) | accepted, option B with a 24 h bound (RP5) | R89, R90 |
| CB20 | minor | accepted | 3.4, R41, R73 |
| CB21 | must-fix | accepted (exit 5, one recovery record per resume, R44 inside the `try`) | R44, R45, R77, T16, T24 |
| CB22 | must-fix | accepted, widened by vB3 (route-B `Pause` is a plain Exception) | R22, R33, T12 |
| CB23 | must-fix | dropped with the carry, RP1 | - |
| CB24 | must-fix | accepted for the plan, sealed files and alias records | R39, R44, R63, R80, T22 |
| CB25 | must-fix | accepted in vB3's stricter form (a void unsettles every alias) | R44, T9 |
| CB26 | must-fix | dropped with the carry, RP1 | - |
| CB27 | minor | accepted | R20, R35, R46, T3 |
| CB28 | must-fix | accepted | R39, R46, 3.6 |
| CB29 | minor | partially accepted | R73 |
| CB30 | must-fix (decision) | carry parts dropped, RP1; the cross-version source (a) serves the post-read command | R88, T27 |
| CB31 | must-fix (decision) | decided by RP6 (automatic replay, no stop in the real run; smoke stop and kill) | R76, R77, 4.3 |
| vA1-X1 | info | accepted (ALFWorld view mismatch is a unit stop) | R15 g |
| vA2-X1 | minor | accepted, in the post-read completeness reading | B1, R85 |
| vB1-X1 | must-fix (identity area) | accepted (RP tail): interface requirement on the identity area; code-only in R85 (fix2, I-8) | 5.3, R85 |
| vB2-E1 | must-fix | accepted | R67, R69 |
| vB2-E2 | must-fix | accepted | R90, T20 |
| vB2-E3 | minor | accepted (with CB15) | R70 |
| vB2-E4 | minor | accepted | R65 |
| vB3-X1 | must-fix | accepted as RP11 | R33, T19 |
| vB3-X2 | minor | accepted | R19, T18 |
| vB3-X3 | must-fix | accepted | R4, R77, T24 |
| vQ-X1 | must-fix | accepted as RP7 | R69, K-B |
| vQ-X2 | minor | accepted (only the hash leaves the capture) | R19 |
| H1 | medium | accepted as RP9 | R16, T2 |
| H2 | low-medium | carry checks dropped; B and M recorded by RP2 and bound in the plan header | R75, R32 c |
| H3 | low | accepted | R24, R26, R15 f |
| H4 | low | accepted | R12, R30, R41 |
| X-A2 | info | accepted | R14 |
| X-B5 | info | accepted as RP8 | B5, R9 |

The drafter's own B1-B5, Q1-Q18 and N1-N10 were answered by vQ: section 0, section 7 and below. Q1 (B5) RP8; Q2
settled by code (R14); Q3 RP1 / RP2; Q4 B1, B2; Q5 RP3; Q6 no ALFWorld capture; Q7 RP7; Q8 RP10; Q9 R30 with
stored inputs (R78); Q10 RP6; Q11 moot; Q12 extract (R24); Q13 moot for the run (N10); Q14 R20, R39; Q15 caps sized
for `full` (R40); Q16 moot (R68); Q17 R82-R87; Q18 settled by code (R22).

Retired ids (never reused): R19b (merged into R19, RP3); R43, R48-R62 (the carry, RP1); P9, P10 of R45 (carry
timing); T13-T15 (carry tests); K-E (carried C); Q19 (fix2: an interface requirement, 5.3). The draft's R17 and R47
keep their subject with corrected content.

### 8.2 Second check (fix2)

Two checkers reviewed the corrected file: chk-cover (coverage and consistency, I-1..I-16; I-11 unused) and chk-adv
(fresh adversary, ADV1..ADV14). Each issue was checked against the file and the code at 8375ecb (N18). Outcome:
accepted (fixed here), partly refuted, or raised to the coordinator (section 6). No decision RP1-RP11 or D9-D17 is
reopened.

| Id | Severity | Outcome | Where |
|---|---|---|---|
| I-1 | must-fix | accepted: D17 taken in; classes, tests and examples given for both base values, the configured run uses R91 (b); the unknown-branch point raised as Q23 | R91 (new), R7, R10 rows 1 and 10, R13, R40, layout example, 4.1, T3-T6, S1, S2, K-D, 5.5, 5.7, 5.8, Q23 |
| I-2 | must-fix | accepted: split-phase terms enter no mean and no maximum; `mixed: k same-phase, m split, no mean` | R70, T20 |
| I-3 | must-fix | (a) accepted: a second replay error with the same code voids the plan; (b) raised as Q24 (widens RP11) | R44 d, R76, T9, T26, Q21; R33 f, Q24 |
| I-4 | must-fix | accepted: `paused: None` has no pause start; outage bounded from stored file times, never 0 h | R89, T20 |
| I-5 | must-fix | accepted: best case 9 fresh units per chain under both base values | R40, T3 |
| I-6 | minor | accepted: RP3 outranks CB20's "optional"; `u/i/c` counts beside every alias cell, zeros included | R66, layout example, T20 |
| I-7 | minor | accepted: reference block with both time ranges and the splitting recoveries; closed-mode counts | R67, R65, T20 |
| I-8 | minor | accepted: vB1-X1 is an interface requirement on the identity area; Q19 retired | 5.3, 8.1 row vB1-X1, Q19 |
| I-9 | minor | accepted: T7 must pass before the smoke; not a run-time check | R14 |
| I-10 | minor | accepted: ALFWorld views and vectors loaded, other views recomputed and checked; new code `view_mismatch` | R78, R33 c, T10 |
| I-12 | minor | accepted (post-launch command): B4's two remarks; T27's three A11 cases with the grep | B4, R85, T27 |
| I-13 | minor | accepted: the record enters no request, identity or decision; the replay reads M only to rebuild hashes | R75 |
| I-14 | minor | accepted: lock mode and widths in R14's list; S10 with DESIGN 3.6 phase names; `alias_sha256` = the record's `record_sha256` | R14, 5.1, R39, 3.7 |
| I-15 | minor | accepted: tests named for `capture_failed`, the pass's reset wrap, read-at-most-once, the fresh `done.json` check, a killed attempt's time range | T19, T12, T16, T20 |
| I-16 | minor | accepted: receipt and settings mismatches keep their own reasons and are never archived; archive limited to plan-owned files | R44 a, b; T9 (vii) |
| ADV1 | must-fix | accepted (with I-1): the replay builds mounts from the manifest's `base_card`; the plan header binds it; T10, T26 and the fake smoke use `historical` | R91, R47, 3.2, 4.1, T10 |
| ADV2 | must-fix | raised as Q23 (an interface decision for Step 5b, not this area's); both answers specified | Q23, R91 b and c, T6, 5.8 |
| ADV3 | must-fix | accepted in substance (an S5 kill inside a text unit also hits sheet and ALFWorld units); evidence partly refuted: the real drain runs with main-v10's 120 s cleanup grace and removes the unit's own leftovers instead of raising at once [V T/chain.py:1115, :1164; X/profiles.py:206-208; X/sandbox/client.py:292-313]; untagged scoring containers are not covered by any drain | S3 b, S3 c |
| ADV4 | must-fix | accepted: probe (C0, zebralogic), a would-be alias under every base; plan-side checks of the probe | R7, S1, S2 b, S3 c, Q20 |
| ADV5 | must-fix | accepted: the replay opens panels without the heavy lock after checking the registry and qualification pointer; the route-B sweep is named | R47, 5.2, T10, T26 |
| ADV6 | must-fix | accepted: restore by in-process recompute; a lost sealed inputs or identity file voids; second replay error voids | R44 c, d; T9 |
| ADV7 | must-fix | accepted: three SIGKILL points in the fake smoke through a fakes-only checkpoint | R92 (new), S2 c, change list |
| ADV8 | minor | accepted: `fake_solve` gains `public_hash`; R41 names its row keys | R41, change row T/smoke.py |
| ADV9 | minor | accepted: `selection_sha256` None when `selection` is None or `attempts` is empty | R10 row 4, R16, T2 |
| ADV10 | minor | accepted: explicit child `PYTHONHASHSEED` other than the parent's, recorded | R76, 3.6, T26 |
| ADV11 | minor | accepted: `.part` temporary names, closed reader names, stale `.part` removal | R80, R65, T16, T22 |
| ADV12 | minor | accepted: `read_mounts` check before any write of the member | R39 (2), T16 |
| ADV13 | minor | accepted: the pass's live ALFWorld resets listed as a residual and unit-tested | S4, K-H, T12 |
| ADV14 | minor | accepted: K-G names the member-routing residual | K-G |

## 9. Coordinator decisions applied

| Id | Decision | Where |
|---|---|---|
| RP1 | no carry into the run; C read fresh through its class; typed-v1 C0 / C only as a post-read replicate | 0, 1.E (R82-R88), R43, R45, R64, R68, 2, 4.2, 8 |
| RP2 | credential-free `solver-settings.json` at chain start, hash bound, provenance only | R75, R32 c, 3.5, T25 |
| RP3 | mandatory first-request hashes for items without offered programs on four benches; none on ALFWorld; infrastructure unknowns keep the alias with counts shown | R19, R29, R41, R65, R66, 3.4, T18, T20 |
| RP4 | max metrics: measured max over other classes if above 0, else `-` with the count; signed max without such events | R70, T20 |
| RP5 | same phase: equal model-id sets and no splitting recovery (24 h bound and `same_phase: true`) | R67, R70, R89 (crash bound), T20 |
| RP6 | no standard stop; automatic replay in a fresh process; `--stop-after-plan` for `run` and `smoke`; smoke stop and kill | R44, R47, R76, R77, 4.3, T24, T26 |
| RP7 | no in-run replicate; `in-run replicates` beside every contrast; gate noise beside the tables | R69, K-B |
| RP8 | identity hashes what the type selects, never the type id | B5, R9, R12, R13 |
| RP9 | one routing path: `mount_identity` / `_route` plus public, view, selection and offered program hashes | R16, R17, R9, T2 |
| RP10 | post-read mismatch: fallback without pause; voids every alias of the bench | R42, T19 |
| RP11 | the pass pauses only on its own inconsistencies; called code's pauses propagate; second same failure voids | R33, T12, T19 |
| D16 | shared types: write and gate on every member; reads unchanged | 5.5, 5.7, K-D, R91 (last paragraph) |
| D17 | base card C: `base_card = 'historical'` for the smoke and the run; read arms unchanged | R91, R7, R40, R47, 3.2, 4.1, T3-T6, 4.3, 5.8, K-D, Q23 |
