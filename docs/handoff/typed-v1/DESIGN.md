# typed-v1 (类型技能库): design of the new learner module

Status: 2026-11-10 contract v2 (owner confirmed the architecture on 11/10; §5 decided; implementation in progress). Working tree
`<repo-root>` (branch `research/typed-skills-v1`, base 46bad46 = route B v2.26).
Evidence behind the design: `docs/handoff/arch-probes-20261109/README.md` (three practice-only probes, 11/09).

## 0. What is new, in one paragraph

A skill library whose entries are either a **card** (prompt text) or a **program** (a route-B procedure), each with a
model-facing **name** and a frozen **description**, and each belonging to one **task type**. Task types are found from
public task inputs only: level 1 = structural signature of the public view, level 2 = data source clusters inside a
structure (centroid of sentence embeddings, p95 unknown threshold). A **router** mounts a type's skills on every item:
the type's card goes into the system message (probe 1: moving it to the end of the user message never helped and hurt
ZebraLogic by 28 points on deepseek), the type's programs are offered by name + description and the solver model
chooses which to enable (probe 3: 0 wrong-bench and 0 distractor picks in 1,440 selections). Items of an unseen
structure, or too far from every known source, get no learned skill. Learning happens bench by bench on practice data
only; candidates (a new card, new programs) pass a per-type gate whose threshold comes from same-request noise; a
new source that shares a structure with an existing type is merged into it only if the existing skills do not harm it.
After every step all five test panels are read fresh (binding 5x5 definition). Everything reuses the route-B solver
shells, judge/scorers, sandbox, client factories and consent-gated test reads; nothing in route B's chain/step/acceptance
machinery is used.

## 1. Objects and records

### 1.1 Skill
```
{"skill_id": "card-t01-s1" | "prog-t01-s1-a",   # stable, opaque
 "name": "<kebab-case, model-facing, unique>",   # e.g. "evidence-answer-card", "grid-constraint-solver"
 "description": "<= 450 chars, written once by the meta model from the body + 3 practice examples, frozen",
 "kind": "card" | "program",
 "home_type": "t01",
 "body": {"text": "..."}                         # card
       | {"procedure": {<route-B Procedure record: id, origin, description, hooks, source, evidence,
                         excluded_benches, lineage, policy_version>}},   # program
 "origin": {"chain": "G", "step": 1, "bench": "searchqa", "writer_call_sha256": "...", "accepted_at": "..."},
 "sha256": "<sha256 of canonical body>"}
```
A type has at most one **active** card (replacing it keeps the old skill in the library with `"retired_at_step": k`)
and any number of programs. Library versions are immutable files `library/library-s{k}.json` (s0 = empty); the
chain never rewrites a past version.

### 1.2 Type map (frozen per step: `typing/typemap-s{k}.json`)
```
{"version": "typed-v1-typemap", "step": k, "embedding": {"model": ..., "revision": ..., "dim": 384},
 "sources": {"src-<sha8 of pool pin>": {"signature": "question/context", "centroid": [...384...],
             "threshold_p95": 0.97, "members": 400, "pool_pin": {...}}},
 "types": {"t01": {"signature": "question/context", "sources": ["src-..."], "card": "card-t01-s1" | null,
                   "programs": ["prog-t01-s1-a", ...], "created_step": 1}},
 "assignment_rule": "signature match, nearest source centroid, distance <= that source's p95 else unknown"}
```
Routing never sees a benchmark name, a task id or a path: only the public view's keys and text.

### 1.3 Mount record (one per solved item, stored with the cell)
```
{"signature": "...", "type": "t01" | null, "source": "src-..." | null, "distance": 0.81, "unknown_reason": null | "unseen_signature" | "distance_above_p95",
 "card_skill": "card-t01-s1" | null, "system_card_sha256": "...",
 "programs_offered": ["prog-..."], "selection": {"use": [...], "status": "ok|parse_failure|not_needed", "request_sha256": "...", "tokens": n} | null,
 "programs_enabled": ["prog-..."]}
```

### 1.4 Cell record
The route-B cell shape is kept where the shell/judge produce it (prediction, judge v2 token, format counters, costs,
shell record) plus `mount`, `request_sha256` list and `tokens`. Cells are written atomically; unknown outcomes keep
their reason and are never scored as wrong.

## 2. Protocol per chain (G = GLM-5.3, D = deepseek-v4-flash northgate, thinking disabled)

Bench order: searchqa, officeqa, zebralogic, spreadsheetbench, alfworld. Practice pools as in the probes
(`/data/execskill-20261021-pre/pools/*.json` pinned by `pools.json`; ZebraLogic `zebralogic.load_pool()` minus
`EXCLUDED_IDS`, 173 items; ALFWorld = the 322 practice games with a registered routing view). Seeded slices per bench,
fixed at `prepare`:

| bench | learn | gate | source for typing |
|---|---|---|---|
| searchqa | 100 | 100 | 400 (learn+gate+200 more) |
| officeqa | 34 | 40 | 74 |
| zebralogic | 73 | 100 | 173 |
| spreadsheetbench | 41 | 50 | 91 |
| alfworld | 20 | 40 | 322 |

`learn` and `gate` are disjoint. Test panels are the registered five test panels of main-v10, read only inside
consent-gated read units.

Step 0 (anchors): read **C0** (format-only shell, empty library) and **C** (the historical cards; ZebraLogic has
none, so C = C0 there) on all five panels.

Step k = 1..5 (bench b):
1. **Noise calibration** on b's gate slice: C0 twice (identical requests). Paired difference d_i per item; the
   threshold of this type for the whole run is `tau_b = max(3.0 points, 2 * SE(d))` with SE the paired standard
   error. Recorded in `steps/s{k}/noise.json`.
2. **Typing update**: embed b's source (all its practice items' public text); if a type with the same signature
   exists, run the **no-harm check** on b's gate slice: that type's current mount vs C0 (paired); drop > tau_b →
   b becomes a new type; otherwise b's source joins that type (shared skills). Without a same-signature type, b is a
   new type. Freeze `typemap-s{k}.json`.
3. **Outcomes with the current mount** on learn ∪ gate (fresh; the gate part is the "current" arm of every gate below).
4. **Card candidate**: writer = GLM-5.3 (both chains), prompts `v225_cards.CARD_WRITE_SYSTEM` / `CARD_REVISE_SYSTEM`
   with the bench task-kind text, the format block, the current card and learn-slice outcomes (public excerpt, reply,
   verdict, reference for failures). Screens: length, bullets, format markers, item identity, references, copied
   examples (v225 functions); one retry on a screen failure. Gate: candidate mount vs current on the gate slice
   (paired): accept iff mean gain >= tau_b and better > worse. If rejected, one revision round (CARD_REVISE_SYSTEM with
   the counts) and one more gate; then stop.
5. **Program candidates** (<= 2 per step): writer = GLM-5.3 with the route-B engineer contract (JSON change schema,
   hooks, policy screens) but a typed payload: task kind, format block, the **skill index (names + descriptions only;
   never a card body)**, outcomes produced WITH the accepted card. Each proposal: policy screen → sandbox smoke on 3
   learn items (any fault → rejected, recorded) → gate on the gate slice with mount = accepted card + candidate
   forced on (its `applies` predicate decides firing): accept iff gain on fired items >= tau_b, better > worse on fired
   items, and whole-slice mean change >= -tau_b (non-regression guard). Accepted programs get a frozen description
   (describer prompt from probe 3) and enter the library.
6. **Reads**: the five test panels with the new library (fresh cells, per-item mount records).

Model selection of programs happens inside the mount whenever the type has >= 1 program: one call with the P3 system
prompt and the type's program index; `{"use": [...]}`; parse failure after one format retry → no programs enabled for
that item (recorded). Types without programs make no selection call.

Caps (hard, pause at cap): chain G 150,000,000 tokens, chain D 170,000,000 tokens, with a per-unit reservation ledger
(charge before send, settle on receipt, keep the bound when usage is missing). Expected: ~17M learning + ~76M reads per
chain (G), from the probes' per-item costs.

## 3. Data boundary and sealing

- Learning, typing and gates read practice pools only (paths pinned; names containing test/holdout/held_out/final/
  sealed/reserve/verifier_calibration are refused except the spreadsheet item's private `test_files` answer workbooks).
- Test panels are read only by read units under `shared/consent.json` (same fields as main-v10: by, date,
  test_evaluation, sheet_test_qualification, multi_arm_arms, note); their cells live in sealed unit directories whose
  names carry `test`; the chain's learning code never opens them; aggregates stay closed until the owner opens them.
- No validation set. Nothing from a read unit flows back into learning.
- The run root is new (`/data/execskill-<launch date>-typed-v1`); the smoke uses its own root and held-out practice
  items in place of panels, so it needs no consent.

## 4. Module layout (`skillopt/execskill/typed/`)

| file | responsibility |
|---|---|
| `__init__.py` | VERSION `typed-v1`, constants (bench order, slice sizes, caps, tau rule, thresholds, seeds) |
| `tasktypes.py` | structural signature, public text extractor, embedding via the separate venv (`embed_service.py` subprocess), TypeMap fit/assign/freeze, no-harm bookkeeping |
| `embed_service.py` | standalone script run with `/data/arch-probe-env/bin/python` (HF offline): JSON texts in → normalized vectors out |
| `library.py` | Skill/Library records, versions, index text (names + descriptions) for the engineer and for selection, description generation (describer prompt + parse) |
| `mount.py` | per-item mount: type assignment → system card composition → selection call → Package of enabled programs → `solver.solve` with a sandbox worker → judge/score (sheet score context) → cell record |
| `writers.py` | card writer (v225 prompts + screens + retry), program writer (route-B engineer payload/reader/policy with the typed payload), describer |
| `gates.py` | noise calibration, paired statistics (Student-t without SciPy, bootstrap), tau rule, card/program gate decisions, no-harm decision; all decisions recorded with denominators |
| `units.py` | (written) atomic unit directories, cell execution with a thread pool (widths: QA/Zebra 3, sheet 2, ALF 2), resume (done units skipped), the token ledger |
| `prepare.py` | run root + own sealed manifest (machinery manifest copy, snapshots, slices, pins), root guards |
| `chain.py` | the step sequence (anchors, steps 1-5), state file, pause on cap/configuration error |
| `reads.py` | consent-gated five-panel reads (route-B TestAccess/panel loaders), sealed outputs, routing fractions |
| `readout.py` | 5x5 tables (F vs C0, F vs C, per step), per-step library listing, routing/unknown fractions, costs, CL metrics |
| `smoke.py` | tiny end-to-end run on practice items (no consent) exercising every unit type |
| `scripts/run_typed.py` | CLI: prepare, smoke, run (resumable), readout, status |

Registration outside the module: a configuration constant `TYPED_V1 = 'typed-v1'` where the reader digest says it is
needed (profiles/protocol), nothing else in route B is modified.

## 5. Interfaces (the contract between modules)

Core modules already written (tests in `tests/test_typed_core.py`): `typed/__init__.py` (constants), `tasktypes.py`,
`embed_service.py`, `gates.py`, `library.py`. Their public functions are the ones to call; do not duplicate them.

### 5.1 tasktypes.py
- `structural_signature(view) -> str`, `public_text(view) -> str`, `alfworld_goal(observation) -> str`.
- `embed_texts(texts, *, embedder=None) -> list[list[float]]` (normalized; subprocess into the CPU venv unless an
  `embedder(texts)` callable is given; batch once per unit, never per item in production).
- `source_id(pool_pin) -> 'src-xxxxxxxx'`.
- `TypeMap()`: `add_source(pool_pin, signature, vectors, *, step) -> sid`; `new_type(sid, *, step) -> tid`;
  `merge_source(sid, tid, *, step, evidence)`; `types_with_signature(sig)`; `type_of_source(sid)`; `set_card(tid, skill_id, *, step)`;
  `add_program(tid, skill_id, *, step)`; `assign(signature, vector) -> {'type','source','distance','threshold','unknown_reason'}`;
  `assign_view(view, *, embedder=None)`; `freeze(path, *, step) -> sha`; `TypeMap.load(path)`; `summary()`.

### 5.2 library.py
- `make_skill(*, skill_id, name, kind, home_type, body, origin, description=None) -> dict`; `body_text(skill)`.
- `Library()`: `add(skill)`, `retire_card(home_type, *, step)`, `active_card(home_type)`, `programs(home_type)`, `active()`,
  `index(*, home_type=None, kinds=('card','program'), described_only=True) -> [{'name','description'}]`,
  `next_id(kind, home_type, step)`, `save(path, *, step) -> sha`, `Library.load(path)`, `summary()`, `get(skill_id)`, `by_name(name)`.
- Prompts/parsers: `description_request(skill, examples) -> {'system','user','request_sha256'}`, `parse_description(reply)`;
  `selection_request(index, public_text)`, `selection_format_retry(req)`, `parse_selection(reply, allowed_names) -> {'use','why'}`.

### 5.3 gates.py
- `paired_statistics(differences)`, `student_t_quantile975(df)`.
- `noise_threshold(pairs) -> {'tau_points', 'se_points', 'flip_rate', 'n', 'excluded_unknown', ...}` where pairs are
  `(item_id, run1_correct, run2_correct)` of two identical-request runs.
- `card_decision(pairs, tau_points)`, `program_decision(pairs, fired_item_ids, tau_points)`, `no_harm_decision(pairs, tau_points)`;
  pairs are `(item_id, current_correct, candidate_correct)` with `None` = unknown (excluded, counted).

### 5.3b units.py (written; tests in `tests/test_typed_units.py`)
- `Stop(RuntimeError)`; `checked_path(path, *, allow_sealed=False)` refuses `FORBIDDEN_PATH_WORDS` in any component
  unless `allow_sealed`; `write_json`/`read_json` (atomic, same guard).
- `Ledger(path, cap, *, resume=False, allow_sealed=False)`: `before_send(system, user, max_tokens, *, cell, unit) ->
  (key, bound)` (bound = bytes + 512 + max_tokens, charged immediately; `Stop` at cap), `settle(key, receipt, *,
  max_tokens, prompt_bound)` (charges reported usage; keeps the bound when usage is missing; `Stop` on a reservation
  breach), `stop(reason)`, `stopped()`, `observe_infrastructure(unknown)` (8 consecutive -> stop), `state` persisted on
  every change, `rerun_cells` (cells whose pending calls were interrupted; a resumed ledger keeps their bounds).
- `CallRecorder(client_call, ledger, *, max_tokens, tag, unit, out_path, transform=None, allow_sealed=False)`: the
  `call(system, user) -> receipt` handed to `solver.solve`/selection/writers; records every send (request sha, receipt
  allow-list `RECEIPT_KEYS`) to `out_path`; `tokens()`, `infrastructure_unknown()` (transport/http/receipt-guard, never
  `MODEL_SIDE_ERRORS`), `.receipts` list for `judge.judge`.
- `cell_tag(bench, item_id, arm)`, `arm_order(item_id, arms)`, `unit_done(unit_dir)`,
  `run_unit(unit_dir, jobs, *, widths, build_cell, ledger, resume=False, allow_sealed=False, meta=None) -> (cells,
  stop_reason)`: `jobs = [(bench, item, arms)]`, `build_cell(bench, item, arm, tag) -> cell dict` (must contain
  `bench, item_id, arm, correct, failure, configuration_error, infrastructure_unknown, tokens, sends`); the first cell
  of each bench runs alone until a model response is confirmed; thread pool width per bench; stops on cap, infra streak
  or a first-cell configuration failure (`failure.json`); cells at `<unit_dir>/cells/<tag>.json`, `unsubmitted/`,
  `done.json` with counts and the ledger snapshot; a done unit is returned from disk; an unfinished one reuses its cells.

### 5.4 Decided reuse of route B (binding for every module)
- **Identity**: `typed-v1` is NOT added to `profiles.CONFIGURATIONS`; no route-B file is edited. Every route-B call
  that takes a configuration gets the *machinery* configuration `profiles.MAIN_V10` (`typed.MACHINERY`): `solver.solve`,
  `judge.judge`/`select_answer`, `manifest.solver_block/routes.pin/check_clients/make_solver`, `Worker(...,
  instruction_configuration='main-v10')`. Route-B objects that need an admitted evidence label (`Package`, `Procedure`,
  `protocol.record`) use `typed.ROUTE_B_EVIDENCE = {'run': 'pilot_real_run', 'smoke': 'smoke', 'test': 'engineering_fixture'}`;
  typed-v1's own records carry `evidence` `typed_v1_real_run` / `typed_v1_smoke` / `engineering_fixture`.
- **Clients** (`scripts/arch_probes.py:323-400` is the working template): solver blocks via `manifest.solver_block("G",
  env_path=ROLES_REPO, configuration=MAIN_V10)` and `solver_block("D", env_path=client.NORTHGATE_ENV, branch=routes.BRANCH,
  longest=routes.S1B_CEILING, configuration=MAIN_V10)` + `routes.pin("D","B", ...)`; `manifest.check_clients`;
  `manifest.make_solver(settings, chain, bench, "B" if chain == "D" else None)` (D = thinking disabled). Bound B =
  `settings['clients']['solver']['G']['B'][bench]` (G) / `settings['clients']['routes']['D']['B']['B'][bench]` (D); chain D
  passes `nominal_tokens = M[bench]` of its block. Role client (card writer, program writer, describer; both chains) =
  GLM-5.3: `client.unpooled(scripts.weak_solver_probe.Client(ROLES_REPO, "glm-5.3", proxy=GATEWAY, max_tokens=N,
  read_timeout=900), proxy=GATEWAY, read_timeout=900)` with N = 32768 (writers) / 16384 (describer, selection is made by
  the solver client). Close every client with `client.http.close()`. Credential files are read by path only.
- **Runtime table, pinned data, sandbox limits, slot root**: copied at `prepare` from the main-v10 smoke manifest
  (`/data/execskill-20261109-main-v10-smoke/G-manifest.json`: top-level `runtime` {bench: {...}}, `data.pinned` =
  {'paths', 'sha256', 'zebralogic': {'path','sha256'}}, `sandbox.limits/measured/image_id`, `slot_root`); the sheet runtime
  carries `recalculation` bound to the main-v10 code snapshot, so on dl every typed process imports `skillopt` from
  `/data/execskill-code-20261109-main-v10` (same base commit 46bad46) and extends `skillopt.execskill.__path__` with the
  typed snapshot's `skillopt/execskill` so that `skillopt.execskill.typed` loads from the typed tree (`scripts/run_typed.py
  --machinery-snapshot`). Sheet readiness before paid sheet cells: `arch_probes.spreadsheet_probe_readiness` pattern
  (pop `code_extraction_version`, `backends.readiness`).
- **Slots and locks**: `slots.pools(slot_root, sizes=manifest._slot_sizes(m))` (machine-wide at `/data/execskill-slots`):
  `pools['native']` held around SpreadsheetBench container runs and host scoring, the episode pool for ALFWorld, exactly as
  `arch_probes.p1_cell` / `cells._shell` do. Memory-heavy lock per unit that contains sheet (EX) or ALFWorld (SH) cells:
  `chain.heavy(SimpleNamespace(extra={'slot_root': slot_root, 'configuration': 'default'}), bench)`.
- **Sandbox worker** (programs only): one UNSTARTED `sandbox.client.Worker(docker=Docker(), limits=<manifest limits>,
  image=<image_id>, scratch=<unit scratch>, tag=sandbox.unit_tag(chain, unit), hashseed=0, instruction_configuration=
  'main-v10', diagnostics_configuration='zebra-pc-v15' for zebralogic else None)` per solve; `solver.solve` starts and
  closes it; `worker=None` when no program is enabled for the item. Replicate the option set `manifest.setting_of`
  builds for main-v10 (read `manifest.py` `_sandbox`/`setting_of`), not more.
- **ALFWorld**: `os.environ['ALFWORLD_DATA'] == runtime['alfworld']['alfworld_data']`; env processes spawn, so every
  entry point has an `if __name__ == '__main__'` guard; widths 2; practice items = the 322 with a registered
  `routing_view`; test tasks get their routing view built in memory the way `evaluation` does for the read
  (`alfworld_reset`/`_with_views`), inside the read unit only.
- **Scoring**: `judge.judge(bench, public, private, prediction, receipts, runtime=runtime[bench], score=score)` with
  `score=None` except SpreadsheetBench status 'available': `backends.score(..., runtime={**rt, '_score_context': {...}})`
  with a fresh `position = digest(request)`, `request = {'benchmark','unit','cell','scoring'}` and `artifact_dir =
  <unit_dir>/host_only/scorer_artifacts/<position>` (arch_probes.p1_cell lines 565-580). `correct = token == 'pass'`,
  `None` for every `unknown*` token (never scored as wrong; counted).
- **Procedure objects**: rebuilt from the stored record exactly as `package.load` does; typed programs carry
  `origin=bench`, `excluded_benches=()`, `policy_version=profiles.POLICY_VERSIONS[MAIN_V10]`, `lineage={'parent': None,
  'revises': None, 'engineer_call': <64-hex request sha>}`, `evidence=ROUTE_B_EVIDENCE[mode]`. Mount package =
  `Package(procedures=tuple(enabled), step='typed/<chain>/s<k>', evidence=...)` (direct construction, <= 24 procedures);
  card-only mount = `package.empty(step=..., evidence=...)`.

### 5.5 mount.py
- `format_block(bench) -> str`: `zebralogic.CARD_TEXT` for zebralogic else `v222_cards.format_text(bench)`.
- `historical_card(bench) -> str`: `v222_cards.historical_text(bench)`; zebralogic -> `format_block`.
- `system_card(bench, card_text) -> str`: `card_text + v225_cards.CARD_JOIN + format_block(bench)` when `card_text`, else
  `format_block(bench)`.
- `ARMS = ('F', 'C0', 'C', 'cand_card', 'cand_program')`.
- `mount(bench, item, *, arm, typemap, library, vector, selector=None, candidate=None) -> dict` (design §1.3 plus
  `'arm'`, `'card_text'`, `'system_card'`, `'enabled'`: [procedure records]): `C0` -> no type lookup, empty; `C` ->
  historical card, empty; `F` -> `typemap.assign(structural_signature(view), vector)`; if typed, the active card of the
  type; if the type has programs and `selector` is given: `library.selection_request(index, public_text(view))` ->
  `selector(system, user)` (one `selection_format_retry` on parse failure) -> enabled = named programs;
  `cand_card` -> as F but `candidate['text']` replaces the card (programs as in F); `cand_program` -> as F plus
  `candidate['procedure']` forced on, no selection call for it.
- `solve(bench, item, mounted, *, call, runtime, worker_factory, native, nominal_tokens, unit, tag, scorer_root) -> dict`
  (design §1.4): builds the package, `worker = worker_factory() if mounted['enabled'] else None`, runs `solver.solve`,
  scores, returns `{'bench','item_id','arm','mount','prediction_status','output_excerpt'(<= 2000 chars),'reply'(full,
  stored),'correct','token','official','format','flags','fired':[ids],'faults':[...],'tokens','sends':[...],
  'request_sha256':[...],'configuration_error': bool,'infrastructure_unknown': bool,'failure': str|None}`.
  Chain D nominal truncation rule and `BalanceExhausted` propagate as in route B.
- `view_of(bench, item, runtime) -> dict`: `solver.routing_view(bench, item['public'], runtime=runtime[bench])` (the
  same keys the hooks and `structural_signature` see).

### 5.6 writers.py
- `outcomes_for_writer(cells, items, *, bench, max_failures=12, max_successes=6, seed) -> [example]`, example =
  `{'task_id','view'(<= 3000 chars of the public text),'reply'(300 head + 1200 tail),'outcome': 'pass'|'fail',
  'reference'(failures, <= 300 chars; ALFWorld: 'won'/'lost' + steps + the last observation instead)}` in the seeded
  order of `data.ranked` (failures first, as `v225_writer.select_examples`).
- `write_card(*, bench, runtime, current_text, examples, corpus, practice_ids, call, round, previous=None, result=None)
  -> {'text': str|None, 'attempts': [{'request_sha256','violation','chars'}], 'request': {...}}`: request keys as
  `v225_writer.build_request` ('write' for round 1 with `CARD_WRITE_SYSTEM`, 'revise' with `CARD_REVISE_SYSTEM` and the
  gate counts for round 2), `task_card = v225_writer.task_card(bench, runtime)` (ALFWorld: `texts.CARDS['alfworld']`),
  reply -> `texts.instruction_text` -> `v225_cards.card_violation(...)`; one retry with `CARD_RETRY`.
- `propose_programs(*, bench, runtime, skill_index, examples, hook_view, parent, call, max_candidates=2, evidence) ->
  [{'procedure': record|None, 'entry': {...}, 'source': str, 'screen': {'passed': bool, 'reason': str|None},
  'request_sha256': str}]`: system = `profiles.engineer_prompt(MAIN_V10, bench, 'single', 'propose')`
  (ALFWorld: `engineer_v295.system(profiles.ALFWORLD_V11, train=False)`, falling back to V9 if V11 is refused); user
  = `{'request':'propose','bench', 'task_card', 'format_block', 'skill_index': [{'name','kind','description'}],
  'trajectories': [examples in engineer._shown_view shape: kind, bench, task_id, token, reference, calls:[{'purpose':
  'first','user': json of the solver user message}], replies], 'hook_views': hook_view, 'detectors': {}, 'previous': None}`
  -> `engineer_payload.trim` -> `coevo5.roles.fit(user, 'trajectories', ROLE_INPUT_BYTES)`; reply ->
  `engineer_reader.read(reply, SimpleNamespace(parent=parent, mode='single'))`; keep kind 'new' only; build the
  `Procedure` (§5.4) = the policy/structure screen; on failure ONE fix call (`engineer_prompt(..., 'fix')`, user
  `{'request':'fix','bench','change': entry+source,'failed': {'check','detail'}}`) and re-screen.
- `describe(skill, examples, call) -> {'description', 'request_sha256', 'attempts'}` via `library.description_request` /
  `parse_description` (one retry; cap 450).

### 5.7 chain.py
- `run(root, chain, *, settings, clients, embedder=None, smoke=False, resume=False) -> state`: resumable state machine;
  `state.json` = done units, current step, pauses, ledger totals; the first paid call of the chain is the connectivity
  probe (`protocol.FIRST_CALL_SYSTEM/USER`) written once to `<chain>/confirm.json`. Units (dirs under `<root>/<chain>/`):
  `anchors/C0-<bench>` and `anchors/C-<bench>` are READ units (§5.8); `s<k>/noise`, `s<k>/typing`, `s<k>/outcomes`,
  `s<k>/card-r<j>` (cand_card cells), `s<k>/program-<i>-smoke`, `s<k>/program-<i>-gate`, `s<k>/decisions.json`,
  `s<k>/library.json` + `s<k>/typemap.json` (frozen), then `test-read-s<k>-<bench>` x 5 (§5.8). Steps follow `ORDER`.
  Pauses: ledger cap, 8 infra unknowns, first-cell configuration failure, exceptions -> `state['paused'] = {reason,
  unit}`; `resume=True` requires `<root>/<chain>/recovery.json` `{by: 'owner', date, decision}` (consumed into
  `recovery-consumed-<n>.json`); one automatic retry after 60 s only for a pure infrastructure pause.
- Gate inputs: pairs `(item_id, current_correct, candidate_correct)` from the gate-slice cells; `gates.card_decision`,
  `gates.program_decision(pairs, fired_ids, tau)`, `gates.no_harm_decision`; `tau` from `gates.noise_threshold` of the
  step's noise unit. Accepted card -> `library.add` + `typemap.set_card` (+ `retire_card`); accepted program ->
  `describe` -> `library.add` + `typemap.add_program`. Descriptions are frozen at acceptance.
- Read events per step: all five benches in a thread pool of 5 units (each unit's inner width per `WIDTHS`), heavy
  lock per unit.

### 5.8 reads.py
- `consent(shared) -> dict`: `shared/consent.json` with exactly `protocol.CONSENT_FIELDS`, `by == 'owner'`,
  `test_evaluation is True`, `sheet_test_qualification is True`, `multi_arm_arms == list(READ_ARMS)` with
  `READ_ARMS = ('C0','C','S1','S2','S3','S4','S5')`, non-blank date/note. Refuses otherwise (no panel is opened).
- `panel_tasks(shared, pinned, bench, unit, *, runtime, native, evidence) -> tasks`: `consent` first; `data.TestAccess(unit)`
  created here only; `zebralogic.test_panel(pinned['zebralogic'], access=)` / `coevo5.data.test_panel(pinned, bench,
  access=)`; registry entry via `evaluation._registry(shared, bench, entry, evidence)` (same entry as
  `evaluation.test_tasks`); SpreadsheetBench: `evaluation._sheet_qualification(shared, tasks, runtime['spreadsheetbench'],
  allowed=consent, native=native, workers=2, evidence=evidence)` (configuration None branch) and the same
  `task_hashes`/`qualified` filtering as `evaluation.test_tasks:455-467`; ALFWorld routing views built in memory.
- `read_panel(root, chain, event, bench, *, library, typemap, ...) -> status`: unit dir `<root>/<chain>/test-read-<event>-<bench>`
  (sealed by name; `allow_sealed=True` for its files only); `event` in `('C0','C','S1'..'S5')`; arm F for `S<k>`;
  embeddings for the panel in one batch; `units.run_unit` with per-item mount records; `<unit>/aggregate.json` (sealed);
  an OPEN mirror `<root>/<chain>/read-status/<event>-<bench>.json` with counts only (cells, unknown by kind, tokens,
  typed/unknown fractions, selection stats; never pass counts). The smoke replaces `panel_tasks` by held-out practice
  items and needs no consent (`panel=` injection), writing under `practice-read-...` names instead.

### 5.9 readout.py, smoke.py, prepare.py, scripts/run_typed.py
- `prepare.prepare(root, *, machinery_manifest, roles_repo, pools_root, smoke=False) -> manifest`: writes
  `<root>/manifest.json` (own sealed record: configuration, machinery, snapshot provenance of both trees, `pinned`,
  `runtime`, `sandbox`, `slot_root`, `cards`, `pools` pins, `slices` (seeded item ids per bench, learn/gate disjoint),
  `arms`, `caps`, `seed`, `clients` settings (no secrets)), `shared/` dirs; refuses a root equal to or under any
  `profiles.RUN_ROOTS` value or `NEVER_WRITTEN`, and an existing root.
- `readout.build(root, *, open_sealed=False) -> dict` + markdown: without `open_sealed` only the open status (units,
  counts, tokens, library/typemap per step, routing fractions); with it the 5x5 tables (accuracy L/H per event x bench,
  paired S<k>-C0, S<k>-C, S<k>-S<k-1> with `gates.paired_statistics`), unknown counts, CL metrics (per bench: final
  minus C0; forgetting = max over earlier steps minus final; backward transfer), costs. Written to
  `<root>/readout/<timestamp>/`.
- `smoke.run(root, chain, *, limits)`: `chain.run(..., smoke=True)` on `<root>-smoke` with `SMOKE_SLICES`
  (learn 2, gate 3, panel 2 per bench), one card round, <= 1 program candidate, evidence 'smoke'; `--fake` wires fake
  solve/judge/embedder for local end-to-end runs without Docker or network.
- CLI `scripts/run_typed.py {prepare,smoke,run,readout,status} --root R [--chain G|D] [--machinery-snapshot P]
  [--resume] [--open-sealed]`; exit codes 0 complete, 3 paused, 5 awaiting owner.

### 5.10 As built (2026-11-10 build workflow; these supersede 5.4-5.9 where they differ)
- **Program gate baseline**: every program candidate is gated against the card-mounted current arm
  (`s<k>/outcomes-card` = arm F with the step's accepted card on learn and gate); when no card was accepted the step-3
  outcomes are that arm. Without this, a no-op program would inherit the card's gain. The second candidate of a step
  mounts from a snapshot of the library/type map taken before the candidate loop (it never rides on candidate 1).
- **Revision round**: after a rejected round-1 card the rejected card is run on the LEARN slice
  (`s<k>/card-r1-learn`, arm cand_card) and round 2's examples come from those cells (failures the card broke first,
  as v2.25); the gate slice never reaches a writer.
- **Engineer index** lists every active skill of every type (name, kind, frozen description, opaque home_type).
- **Cell records**: `sends` = the shell's sends only; the selection call is kept apart (`selection_sends`,
  `selection_request_sha256`, `selection_tokens`, `selection_infrastructure_unknown`); `tokens` = solver + selection.
  Writers read the solver request only.
- **Stops and pauses**: route-B stop kinds (`errors.STOP_KINDS`: sandbox, balance, package, cleanup, configuration)
  inside a unit write `<unit>/stop.json`, stop the ledger and pause the chain with that kind; a unit with missing cells
  pauses (`incomplete_unit:missing_cells`, `incomplete_read:missing_cells`) before any decision or the next event;
  `noise_uncalibrated` when fewer than half the gate items have known noise pairs; `describer_unavailable` after one
  retry of an infrastructure no-reply; a ledger stop inside a role call pauses with the ledger's reason. Every pause
  records `awaiting_owner: True` (CLI exit 5); resume requires `<root>/<chain>/recovery.json` from the owner, consumed
  once; one automatic retry after 60 s only for pure infrastructure stops (learning units and test reads). Resumed or
  reopened units re-run their infrastructure-unknown cells (old records archived under `<unit>/rerun/`).
- **Sandbox**: workers get main-v10's `cleanup_grace_seconds`/`ready_timeout_seconds`; every cell unit and read unit is
  drained (`sandbox.drain_unit`, `<unit>/drain.json`). The memory-heavy lock is held per CELL (as main-v10's
  `cells.run_cell`) and around the SpreadsheetBench test qualification.
- **Test-read scorer artifacts** (recalculated reference workbooks) live under `<read unit>/transient/` and are deleted at
  unit end with a deletion manifest (`transient-deleted.json`: file count + hashes, no content).
- **Readout**: forgetting is signed (negative when a bench ends above every earlier step), as route B's vendored
  cl_metrics FGT.
- **Services** (chain.py) has no `panel_tasks` (reads.read_panel is the only panel path) and has `drain(unit)` and
  `worker_options`; `mount.solve` takes `mode` ('run'|'smoke'|'test') and optional `step`/`episodes`.

- **Codex review 11/10 (one read-only review, then one focused review of the data/effect fixes)**: (1) test material
  stays where route B keeps it: the SpreadsheetBench test qualification in the sealed `shared/test/` (artifacts deleted
  on every exit), the frozen shells' and scorers' transient files in self-deleting temporary directories; each chain
  process runs with its own `TMPDIR=/tmp/typedrun-<phase>-<chain>` (removed after exit). (2) The ledger reserves route
  B's four attempt bounds per call and settles each attempt by `coevo5.ledger.settle` (a timed-out attempt that reached
  the provider is charged its bound, a refused one nothing); receipts keep their `attempts`. (3) A candidate names its
  home type and is applied only to items routed to that type (others keep arm F), so a gate measures what acceptance
  deploys. (4) Recovery re-runs configuration-failed cells as well as infrastructure unknowns; such a cell never
  confirms a bench. (5) An accepted card whose describer reply never parses gets the frozen fallback description
  (public structure only; `origin.description_source`). (6) Recovered reservations are attributed to their units.
  (7) Accepted cards record the writer attempt that produced them. (8) The owner's recovery record is consumed by one
  atomic rename and marked applied afterwards; a consumed-but-unapplied record is applied by the next resume.

- **Smoke 11/10 (practice items only, `/data/execskill-20261110-typed-v1-smoke`)**: both chains complete (D 18:48,
  1,001,498 tokens; G 19:11, 841,516 tokens), no pause, ledger fully settled; card accepted and rejected, no-harm merge
  (G: OfficeQA joined SearchQA's type) and split (D), program rejections by policy screen, sandbox fault and no fired
  gain. A separate live check (`/data/typed-v1-ops/selection_check.py`, 2 items per chain) exercised the selection call:
  the solver model picked the offered program, which fired in the real sandbox. Real root prepared from the same
  snapshot (`/data/execskill-20261110-typed-v1`, manifest sha 20e31c27...).
- **Point 4 as implemented**: the no-harm check of a same-structure source runs when that source's practice items arrive
  (its own step); before it, test items of that source that fall within an existing type's distance threshold get that
  type's skills (e.g. OfficeQA at S1 gets SearchQA's card), so those S_k cells measure unchecked transfer. Checking
  earlier would need future benches' practice data.
- **Known latent minor (next version)**: `writers.build_procedure` called with an entry that lacks `max_note_chars`
  bounds the missing cap to 1 (every note then faults); the real proposal path always passes the route-B reader's
  normalized entry, whose default is the full note cap, so runs are unaffected.

## 6. Tests

Fakes only (no network, no /data): typing (signature, assignment, thresholds, merge/split), library versions and index,
mount composition bytes per bench (card in system message = probe-1 "sys" layout; C0 when unknown), selection parsing,
writer screens, gate decisions with the tau rule, unit atomicity/resume/ledger, consent gating of reads (refuses without
consent), readout tables from synthetic cells, CLI dry runs. Run with `<python> -m pytest -q
-p no:cacheprovider tests/test_typed_*.py` and on Linux with the experiment python (no scipy/sklearn there).

## 7. Operations (dl)

Code snapshot copied to `/data/execskill-code-<date>-typed-v1`; the sheet scorer's recalculation qualification is bound
to the main-v10 snapshot's engine source, so the run imports the sheet engine from that snapshot (as the probes did via
`run_snapshot.py`) or re-qualifies; `ALFWORLD_DATA` set; `PYTHONDONTWRITEBYTECODE=1`; one tmux session per chain;
`proxy_on` in the same shell; status/watch scripts as for the probes.
