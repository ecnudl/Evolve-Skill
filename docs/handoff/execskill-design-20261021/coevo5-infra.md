# coevo5 protocol-agnostic infrastructure map (for route B: executable-skill co-evolution)

Status: COMPLETE (all six sections written; ~40 min budget).
Reader: read-only subagent, 2026-10-21. Repo: /Users/dulin/Documents/Paper/SkillOpt (working tree as found).
Linux: dl (`ssh -o BatchMode=yes dl.dulin+root.ailab-datatools.ws@h.pjlab.org.cn`), read-only listing/`python3 -I -c` key dumps only; no test item, evaluation/ cell or shared/test/ file was opened.
Citations: `path:line` repo-relative; absolute paths are on dl. "verified" = read in source or on disk; "inferred" = deduced.

## 1. Scope and files read

Read in full (lines): `skillopt/coevo5/protocol.py` 357, `calls.py` 279, `ledger.py` 103, `budget.py` 351, `cells.py` 263,
`units.py` 157, `evaluation.py` 455, `data.py` 358, `outcomes.py` 402, `manifest.py` 154, `prelaunch.py` 545,
`qualify.py` 144, `stats.py` 74, `checks.py` 105, `leakage.py` 291, `smoke.py` 435, `chain.py` 314, `__init__.py` 8,
`scripts/run_coevo5.py` 311.
Read in part: `skillopt/coevo5/step.py` (861; lines 1-230, 825-861 + def index), `baseline.py` (CONFIG l.52, `checked`
l.342-345), `report.py` (`of_manifest` l.64-68), `scripts/weak_solver_probe.py` (l.71-100, 227-350),
`skillopt/continual_eval/core.py` (l.28-62), `skillopt/coevolution_v5/core.py` (l.40-60),
`skillopt/validator_pilot/api.py` (l.36-75), `tests/coevo5_fakes.py` (53, def index), `tests/` listing (22 coevo5 files).
On dl (read-only): layout of /data/coevo5-20261019-v3-run (pruned at `*/evaluation/*` and `shared/test*`), key shapes of
one training cell /data/coevo5-20261019-v3-run/E-ds/s1/train/attempt-1/cells/*.json, ledger state/event counts, v3 manifest
provenance counts (/data/coevo5-20261019-v3-run-manifest.json), ops scripts /data/coevo5-20261019-v3-ops/prep-v3.sh and
/data/coevo5-20261019-v3-ops/f/{prep-launch-v3.sh,launch-v3.sh,run-chain-v3.sh,consent-note.txt,consent.log},
/data/coevo5-20261020-cal1-ops/{cal1.py (imports + main), run-cal1.sh}, smoke dir /data/coevo5-20261019-v3-pre/smoke-3,
`nproc`/`free`/`docker info`.

## 2. Facts

### Identity, snapshot, versions
- F1 (verified) Protocol identity is `VERSION = "fivebench-coevolution-v3"` (protocol.py:10). `skillopt/coevo5/__init__.py:8`
  still says `"fivebench-coevolution-v1"`; every module imports VERSION from `.protocol` (grep), nothing reads the package
  attribute (grep for `coevo5.VERSION` / `from skillopt.coevo5 import VERSION`: no hit). Stale but harmless.
- F2 (verified) Every record kind stamped with VERSION: `-cell` (cells.py:222), `-unit` (units.py:154), `-test-panel`
  (evaluation.py:199), `-evaluation` (evaluation.py:367, 396), `-sheet-qualification` written AND required on load
  (qualify.py:124, 136), `-manifest` written (prelaunch.py:508) and required by `manifest.load` (manifest.py:119) and
  `report.of_manifest` (report.py:67), `-texts`/`-texts-import` (prelaunch.py:134-136; `IMPORTABLE =
  ("fivebench-coevolution-v1-texts",)` 135), `-smoke` written (smoke.py:112) and required (smoke.py:129,
  prelaunch.py:469), `-chain` (chain.py:275), `-report` (report.py:413). Other identity strings: data split
  `"fivebench-split-v2"`, layout `"extension-layout-v1"` (data.py:40-41), run id = manifest `record_hash`
  (manifest.py:146), smoke run id = smoke spec `record_hash` (smoke.py:155).
- F3 (verified by sha256) The local working-tree copies of all 32 `skillopt/coevo5/*.py`, `scripts/run_coevo5.py`,
  `scripts/weak_solver_probe.py`, `skillopt/continual_eval/backends.py` (35 files) are byte-identical to the frozen v3
  snapshot /data/coevo5-20261019-v3-source-f (the source the v3 chains and cal-1 ran from). Locally `skillopt/coevo5/` and
  `scripts/run_coevo5.py` are untracked (`git status --short`: `??`).
- F4 (verified) `seal(value)` adds `record_hash = digest(value)` and refuses an already sealed value
  (coevolution_v5/core.py:46-51); `read_json(path, sealed=True)` verifies it (continual_eval/core.py:42-57, core.py:54-60).
  `digest` = sha256 of `json.dumps(sort_keys, ensure_ascii=False, separators=(",",":"))` (validator_pilot/api.py:40-41).
  `write_json` is write-once: an existing file with different JSON raises `ValueError("Immutable artifact differs; use
  a new output directory")` (validator_pilot/api.py:44-71). `safe_path` refuses `..` and any symlink component
  (continual_eval/core.py:35-39).

### calls.py (concurrency + call wrapper)
- F5 (verified) Only protocol imports: `MAX_RESENDS, RESEND_COOLDOWN_SECONDS` (calls.py:32) = 2 and 300 s
  (protocol.py:87-88).
- F6 (verified) `Slots` = one flock file per slot `<root>/<name>.<i>.lock`, plus `<name>.gather.lock` and
  `<name>.many.lock` (calls.py:39-122). The pool is per root directory, not machine-wide: the run uses
  `<run>/shared/slots` (manifest.py:149), the smoke `<P>/slots` (smoke.py:161), cal-1 its own `<out>/shared/slots`
  (/data/coevo5-20261020-cal1-ops/cal1.py:129-131). Processes with different roots do not share concurrency limits.
- F7 (verified) `Endpoint` takes the ledger halt generation at construction (calls.py:145): one endpoint per unit
  attempt; any halt since then refuses every later reservation, even after a resume (budget.py:294-297).
- F8 (verified) `Recorder.__call__(system, user)` re-sends the identical request up to `MAX_RESENDS` times after
  `endpoint.cooldown` when `outcomes.undelivered(receipt)` (calls.py:268-279); every send (with receipt, charge,
  reservation, seconds, request sha256/bytes, model, max_tokens) is appended to `recorder.sends` (calls.py:153-154,
  198-221). Only fixed categories reach the shared ledger (`_detail`, calls.py:238-258).
- F9 (verified) A breach (reported usage beyond the reservation's bound) latches the endpoint, settles at the reported
  amount with `breach=BREACH`, halts the ledger and raises `AssumptionBroken` (calls.py:183-184, 212-217; budget.py:95-96).
  Any ledger failure latches the endpoint and raises `LedgerFailure` (calls.py:171-174, 223-235).

### ledger.py / budget.py (token accounting)
- F10 (verified) Reservation = `CLIENT_ATTEMPTS * (request_bytes + RESERVATION_OVERHEAD + max_tokens)` = 4 x (bytes +
  512 + max_tokens) (ledger.py:26-36; protocol.py:278-279). `settle(receipt, size, max_tokens)` requires 1..4 attempts
  (ledger.py:59-60): reported usage on the last attempt, 0 for refused attempts (ConnectError/ConnectTimeout/
  PoolTimeout or HTTP 4xx, ledger.py:23, 46-48), else the attempt bound; breach if prompt > size+512 or completion >
  max_tokens (ledger.py:67). CLIENT_ATTEMPTS=4 matches the probe client's `BACKOFF = (10, 30, 60)` loop (1+3 attempts,
  weak_solver_probe.py:92-93, 305-344).
- F11 (verified) budget.py imports no protocol constant (budget.py:22-36). Scope names are strings: `"overall"`,
  `"deepseek"` (38-39), `chain_scope(c) = "chain:"+c` (44-45), `step_scope(c, step, kind) = "step:c:step:kind"` with
  kind in ("learning","evaluation") (67-71), `deepseek_scope(c, step, kind)` = `"deepseek[:c[:step:kind]]"` (48-56).
  `rooted(scopes)`: GLM calls name `overall` and no deepseek scope; deepseek calls name `deepseek` and only
  deepseek-prefixed scopes (59-64). `reserve` accepts any declared scope string satisfying `rooted` (288-300).
- F12 (verified) Durability: one `.lock` flock, `events.jsonl` (fsync) then `state.json` cache with byte offset;
  torn tail truncated; failed reservation/settlement quarantined by one `halt` event that closes what it left open
  (budget.py:128-222). Orphans (reserving process dead, via `os.kill` + `/proc/<pid>/stat` start time; other hosts
  assumed alive) are settled at the full amount (budget.py:74-81, 248-273).
- F13 (verified, dl) v3 run ledger: 41 declared scopes; events `declare` 41, `reserve` 56,220, `settle` 56,220, no halt
  (halts 0, open 0). Settled: `deepseek` 139,024,462; `deepseek:I-ds` 106,601,730; `deepseek:E-ds` 27,361,728;
  `deepseek:NoSkill-ds` 5,061,004; GLM `overall` 7,804,250. Caps: `overall` 1,168,566,218 (= OVERALL_CEILING 1,170M -
  prior 1,433,782), `deepseek` 430,000,000 (/data/coevo5-20261019-v3-run/shared/ledger/state.json, events.jsonl).

### cells.py / units.py (cell runner, unit attempts)
- F14 (verified) protocol imports: `MAX_EPISODE_RESTARTS, MAX_REEXECUTIONS, MAX_RESCORES, VERSION` (cells.py:42);
  `LIMITS` (44), `STOP_KINDS` (45-46).
- F15 (verified) `cell_id(unit, arm, task_id, run) = digest({...})[:32]` (cells.py:84-85). A cell is claimed by
  `O_EXCL` creation of `cells/<id>.claim` (88-94) and writes `cells/<id>.json` once (169-171, 231); predictions/scores are
  stored once by hash in `artifacts/<sha>.json` (97-101).
- F16 (verified) The model interface of a cell: `backends.solve(benchmark, deepcopy(task["public"]), skill, recorder,
  runtime=deepcopy(context.runtime[benchmark]))` -- the solver receives the Recorder as `call(system, user)`
  (cells.py:122-136). SpreadsheetBench takes a native slot right after the reply (`on_reply`, 127-129); ALFWorld holds
  an episode slot for the whole solve (130-131). Scoring: `backends.score(benchmark, public, private, prediction,
  runtime=...)` (152-163); SpreadsheetBench scores in `<attempt>/host_only/scorer_artifacts/<position>` (160-161).
- F17 (verified) Remedies: re-execute replays the stored reply and requires the identical request hash (cells.py:139-149);
  rescore; ALFWorld restart = a fresh `_solve` (209-214). Limits 2/2/2 (protocol.py:89-91).
- F18 (verified) Record shape (cells.py:221-230; confirmed on dl): keys `attempts, cell, final, official, record_hash,
  refused, remedies, sends, skill_sha256, spent, stop, version`; `cell` = {id, unit, arm, benchmark, task_id, run};
  `attempts[i]` = {step, prediction{sha256,status,reason[,cases]}, score{sha256,status,reason,cleanup_confirmed[,cases]}
  |null, verdict|null}; `final` = Verdict fields + `token`; `official` = {status, reason}; `stop` = {kind, reason}|null;
  `sends[i]` = {request_sha256, request_bytes, model, max_tokens, started, reserved, charged, assumption_broken,
  seconds, receipt}; receipt keys on dl: attempts, finish_reason, ok, reasoning_chars, response, returned_model, seconds,
  status, usage, usage_valid.
- F19 (verified) `run_parallel` stops dispatching after the first error, lets running jobs finish and re-raises the
  first error (cells.py:237-258). `exclusive(path, wait=False)` flock ownership; second owner -> `ValueError("Another
  process owns ...")` (57-71).
- F20 (verified) units.py imports `READ_TIMEOUT_SECONDS, RESEND_COOLDOWN_SECONDS, ROLE_MAX_TOKENS, ROLE_MODEL,
  ROLE_READ_TIMEOUT_SECONDS, SOLVER_MAX_TOKENS, VERSION` (units.py:27-35); hardcodes `CHAINS` (8 chains: solver, start,
  caps kind; 37-46); `endpoints()` imports `chain.deepseek_scopes` lazily (85).
- F21 (verified) `run_unit` (units.py:126-157): `exclusive(unit_root/.lock)` (fail fast); a complete `unit.json` of the
  same run+identity is returned (another identity raises, 115-123); else next `attempt-N` (only if the previous attempt
  has the owner's `recovery.json`), `started.json`, `work(attempt)`; Pause -> `status.json` {status: paused, kind, reason,
  cell}; other exception -> `diagnostics.log` traceback + `status.json` (kind from STOP_KINDS, ValueError ->
  "configuration", else "exception") and `Pause`. Unit record = {version, run, identity, status: "complete", attempt,
  result, record_hash} (confirmed on dl: identity keys after, benchmark, chain, parent_sha256, stage, unit).

### evaluation.py (test sets)
- F22 (verified) protocol imports: `MAX_UNKNOWN_SHARE, SHARED_STAGE0, VERSION` (evaluation.py:41); `SHARED_STAGE0 = {}`
  in v3 (protocol.py:283).
- F23 (verified) Only evaluation creates `data.TestAccess(unit)` (evaluation.py:231; data.py:232-239). `test_tasks`
  requires `shared/consent.json` with exactly {test_evaluation, sheet_test_qualification, by, date, note}, by=="owner",
  test_evaluation is True (evaluation.py:43, 152-159, 230); registers a write-once panel entry {run, benchmark,
  panel_hash, tasks, excluded_without_pages, source_files} at `shared/test/<bench>.json` (190-199, 232-235); for
  SpreadsheetBench runs the test-side qualification once for all chains (write-once pointer
  `shared/test/spreadsheetbench-qualification.json`, attempts under `shared/test/spreadsheetbench-qualification/`,
  202-224) and keeps only qualified items; none qualified -> `Pause("no_qualified_test_items")` (241-242).
- F24 (verified) `evaluate()` is ONE arm per unit: jobs use `arm=chain`, `run=0`, `cell_id(unit, chain, task_id, 0)`
  (evaluation.py:376-378); reuse when the Skill text digest equals the predecessor's (365-369); infrastructure unknowns >
  1/10 of cells pause (392-395); `configuration()` = digest of benchmark, model, max_tokens, runtime (308-311).
- F25 (verified) Containment: while a unit runs, fd 1/2 and sys.stdout/err go to
  `shared/host_only/diagnostics/<host>-<pid>.log` (evaluation.py:56-149); escaping errors are replaced by fresh
  exceptions without context; messages are kept only if raised from a file in the coevo5 package directory (`_own`,
  262-267; `_public_exception` 289-305). The chain runs every evaluation unit in a child process whose stdout/stderr is
  a sealed file `shared/host_only/diagnostics/child-<name>-<ns>.log` (chain.py:153-177).
- F26 (verified) `unseal()` requires `chain-complete.json` or `chain-terminated.json` and returns `{unit: {task_id:
  token}}` (or detail) -- keyed by task_id only (evaluation.py:429-455). `monitor()` gives counts, never scores (414-426).

### data.py (pools, pins, draws)
- F27 (verified) protocol imports `MAX_UNKNOWN_SHARE, ORDER, PARENT_REGRESSION_RUNS, POOLS, REGRESSION_ITEMS,
  REGRESSION_RUNS, SHEET_MIN_QUALIFIED, TEST_SIZES, TRAIN_ROLLOUT` (data.py:25-35). `DEV_MACHINE` hardcodes /root/...
  input paths (45-64); they exist on dl (checked split_manifest.json and officeqa dev_panel.json).
- F28 (verified) `pin(config)` checks the key sets (train/val == set(ORDER), layouts == {officeqa, livemath}, test ==
  ORDER minus those) and hashes 16 files without parsing (data.py:76-82; dl manifest `data.sha256` has 16 entries).
- F29 (verified) `pool(pinned, b)` = historical train+val items `{benchmark, task_id, family_id, part, public, private}`;
  asserts `POOLS[b]` = (400,200) searchqa, (50,24) officeqa, (155,128) livemath, (80,40) spreadsheetbench, (39,18) alfworld
  (data.py:155-166; protocol.py:63-64). Every non-test reader refuses test ids (`_refuse_tests`, 120-124).
- F30 (verified) Draws are prefixes of one seeded hash order: `ranked(items, seed, tag)` (173-176);
  `training_items(items, b, seed, size=None)` = first TRAIN_ROLLOUT[b][0] (SpreadsheetBench: all qualified), `size` only
  for the smoke (188-196); `regression_items` = first min(60, n) of tag "regression:<b>", none for `ORDER[-1]` (199-205).
  In coevo5 the gate's focal panel IS the training draw (protocol.py:58). There is no reader for fresh/disjoint batches
  and no record of consumed items (verified: full function list data.py:67-358).
- F31 (verified) `sheet_tolerances` executes `docs/handoff/coevo5_power_sim_v2.py` at call time (data.py:208-228).
- F32 (verified) `test_panel(pinned, b, *, access)`: SearchQA/SpreadsheetBench/ALFWorld from frozen 10/5 panels;
  OfficeQA/LiveMath rendered from upstream after `_proof` re-renders the training panels identically; OfficeQA items
  without pages excluded, at most 1/10 (data.py:303-358).
- F33 (verified, dl) v3 training-side SpreadsheetBench qualification: 120 items, 91 qualified (22
  reference_recalculation_failed, 6 read_view_unverifiable, 1 reference_cache_mismatch) (manifest provenance).

### outcomes.py (decision table)
- F34 (verified) Only protocol import: `MAX_WORKBOOK_BYTES, MAX_WORKBOOK_EXPANDED_BYTES` (outcomes.py:36). Rows: 1
  configuration (raise), 2 budget (raise), 3 cleanup (raise), 4 undelivered -> unknown/infrastructure, 5 noncompletion
  -> fail, 6 malformed -> fail, 7 ALFWorld env error before any call -> restart, 8 ALFWorld env error -> unknown, 9a-9d
  SpreadsheetBench generation/workbook/scorer/combination, 10 scored pass/fail, 11 unclassified -> unknown (counted as
  infrastructure) (outcomes.py:52-92, 185-205, 293-402). Tokens: pass, fail, unknown, unknown_artifact
  (`Verdict.token`, 132-138; stats.py:16).

### manifest.py / prelaunch.py / qualify.py / smoke.py / chain.py / CLI
- F35 (verified) manifest.py imports `DEEPSEEK_ROUTE, ORDER, OVERALL_CEILING, SLOTS, VERSION` (manifest.py:30) and
  modules baseline, data, qualify, research, texts, examiner. `FIELDS` = {version, root, data, sheet_qualification,
  regression, tolerance, cards, instructions, rubrics, runtime, clients, research, baseline, workers, code, provenance,
  record_hash} (34-35). `pin_code()` hashes every file under skillopt/ and scripts/ (44-48; 672 files in the v3
  manifest). `loaded_code()` hardcodes `skillopt/coevo5/*.py` + `scripts/run_coevo5.py` (37, 51-61). `verify_code`
  also binds python/openpyxl (71-81; v3: 3.11.16 / 3.1.5).
- F36 (verified) `_clients` routes only `model == "deepseek-v4-flash"` to the PJLAB token route (manifest.py:108-109);
  proxy must be None or `GATEWAY` (98). Probe allow-list `MODELS` has no "deepseek-v4.1-flash-1017" (grep in scripts/
  and skillopt/: no hit), `ROUTES = {"pjlab_token": {"deepseek-v4-flash": ...}}` (weak_solver_probe.py:76-88); unknown
  model -> `SystemExit` (232-233). design-v0.md:55 asks the smoke to use deepseek-v4.1-flash-1017.
- F37 (verified) prelaunch.py imports ANALYST_ATTEMPTS, BASELINE_BUDGET, BASELINE_PROTOCOL, DATA_SEED, ORDER, ROLE_*,
  RUNTIME, SLOTS, SOLVER_MAX_TOKENS, TITLES, TOLERANCE_FOCAL, TOLERANCE_REGRESSION, VERSION, M (prelaunch.py:49-66);
  `PRELAUNCH_CAP = 30 * M` (131); pre-launch ledger is `<P>/ledger` beside texts/smoke dirs (130, 248-257).
- F38 (verified) qualify.py imports only VERSION (qualify.py:24); `PASSES = 2` (26); zero model calls; new directory per
  qualification (91-94); `load()` refuses another VERSION (134-138).
- F39 (verified) smoke.py: `CHAIN = "I-ds"`, `BENCHES = ORDER[:2]`, `DRAW = {"searchqa": 60, "officeqa": 50}`, format check
  `FORMAT_ITEMS = 20` on `ORDER[:4]`, floor 9/10, margin 1/20 (smoke.py:62-77). `run()` declares `chain.caps(name,
  PRELAUNCH_CAP)` on the pre-launch ledger, then `format_check` (unit s0/format-check), `step.learn` stage 1, `paths`
  (s1/smoke-paths), `step.learn` stage 2, `write_summary` -> `<P>/<name>/summary.json` (316-337, 429-435). On dl
  smoke-3: I-ds/{s0,s1,s2}, s1 = merge, prepare, screen, selftest, smoke-paths, train.
- F40 (verified) chain.py: `SHARED = "stage0-glm"`, exits 0/3/4/5, `RUNNER_LOCK = ".runner.lock"` (chain.py:57-62);
  `run()` writes `chain.json`, declares caps, runs stage 0 (test-side sheet qualification child first, 226-237), then
  per stage learn + 5 evaluation children side by side, `chain-complete.json` at the end (261-292); a pinned-file
  mismatch after start writes `chain-terminated.json` (251-258); `terminate()` needs an idle chain (303-314).
- F41 (verified) `run_coevo5.py run` refuses unless `baseline.checked(setting)` (run_coevo5.py:80; baseline.py:342-345,
  `shared/baselines-checked.json` on dl); `consent` resolves the run via `reports.of_manifest` (216-218); `recover` writes
  `{"by":"owner","date":today,"decision"}` to the last attempt (221-226).
- F42 (verified, dl) Actual v3 launch order: see section 3.9 (prep-v3.sh, f/prep-launch-v3.sh, f/launch-v3.sh,
  f/run-chain-v3.sh). Tests run on the snapshot first: `pytest -q -p no:cacheprovider tests/test_coevo5_*.py
  tests/test_weak_solver_probe.py` must exit 0 (prep-v3.sh:7-10).
- F43 (verified, dl) Precedent for reuse with a new identity: cal-1 (/data/coevo5-20261020-cal1-ops/cal1.py) imports the
  unchanged v3 package (`data, manifest, step`, `Budget`, `Slots`, `Pause`, `run_unit, solver_endpoint`; l.28-34), loads
  the frozen v3 manifest with code verification (l.126), then `dataclasses.replace(setting, root=out, shared=out/
  "shared", budget=Budget(out/"shared"/"ledger"), slots=..., workers=...)` (l.127-131), declares its own scopes
  `("deepseek", "deepseek:cal1")` (l.39, 128), runs `step.run_round` + `step.guard` inside `run_unit(..., run="cal1:" +
  manifest_hash[:16], identity={..., "version": "cal-1", ...})` (l.150-186), refuses to write under the v3 run (l.124).
  Its cell/unit records are still stamped `fivebench-coevolution-v3-cell/-unit` (inferred from F2).
- F44 (verified, dl) Machine: 7 CPUs, 15 GB RAM, Docker 26.1.3 (matches protocol.py:325-326). Python of the runs:
  /root/continual-alf-prep-20260928/env/bin/python (prep-v3.sh:1).
- F45 (verified) Test doubles exist: tests/coevo5_fakes.py (`USAGE`, `reply(value, *, finish="stop")`, `undelivered()`,
  `class Script`, `roles(tmp_path, replies, *, model="glm-5.3")`); 21 test_coevo5_*.py files incl. calls, cells, ledger,
  units, evaluation, data, outcomes, prelaunch, smoke, chain.
- F46 (verified) checks.py states "no model-written code is ever executed" (checks.py:3); the only native execution of
  model output is SpreadsheetBench programs inside the frozen backend (runtime image/timeouts, protocol.py:345-354).

## 3. Interfaces an implementer would call or must replace

Notation: "P:" = protocol constants the module imports (`from .protocol import`), all resolved against
`skillopt.coevo5.protocol` (relative imports: a new package importing these modules gets coevo5's values).

### 3.1 calls.py  (P: MAX_RESENDS, RESEND_COOLDOWN_SECONDS)
- `Slots(root, name, count, *, poll=0.5, sleep=time.sleep)`; `hold()` -> ctx yielding slot index; `hold_many(count)` ->
  ctx yielding sorted indices (one gatherer per pool). name must be alnum after removing `-` and `.`. Side effect: lock
  files under root.
- `Endpoint(client, *, model, max_tokens, slots, budget=None, scopes=(), cooldown=RESEND_COOLDOWN_SECONDS,
  sleep=time.sleep)`; `client` needs only `call(system, user) -> receipt dict`. `recorder(*, label, on_reply=None)
  -> Recorder`; `send(system, user, recorder) -> receipt`. Raises `BudgetStop` (budget refused), `AssumptionBroken`
  (halted / breach), `LedgerFailure`; re-raises client exceptions after recording. Attributes `halted`, `failed`,
  `generation`. Construct one per unit attempt (halt generation).
- `Recorder(endpoint, label, on_reply)`: `__call__(system, user) -> receipt` (resend loop); fields `receipts`, `sends`,
  `refused`, `invalid`, `broken`, `failed`, `label`.
- `_request_hash(system, user)` (sha256 of system + NUL + user) -- private but used by cells.py:29, prelaunch.py:47.
- Constants `BREACH = "reported_usage_beyond_reservation_bound"`.

### 3.2 ledger.py  (P: CLIENT_ATTEMPTS, RESERVATION_OVERHEAD, BASELINE_* (baseline helpers only))
- `request_bytes(system, user)`, `attempt_bound(size, max_tokens)`, `reservation(size, max_tokens)`,
  `settle(receipt, size, max_tokens) -> (charged:int, broken:bool)` (ValueError if attempts not 1..4),
  `baseline_worst_case()`, `settle_baseline(calls)`. Pure functions.

### 3.3 budget.py  (P: none)
- Scope helpers: `OVERALL="overall"`, `DEEPSEEK="deepseek"`, `chain_scope(chain)`, `step_scope(chain, step, kind)`,
  `deepseek_scope(chain=None, step=None, kind=None)`, `rooted(scopes)`.
- `Budget(root, *, poll=5.0, sleep=time.sleep)`: `declare(caps: {scope: int})` (idempotent; a different cap for a
  declared scope raises), `raise_cap(scope, cap, *, deviation)`, `generation() -> int` (AssumptionBroken while halted),
  `reserve(scopes, amount, *, label, generation) -> rid` (waits / BudgetStop / AssumptionBroken / LedgerFailure),
  `settle(rid, charged, *, detail, breach=None)`, `halt(reason, *, label)`, `resume(*, decision)`, `close_orphans() ->
  open count`, `snapshot() -> {scope: {"cap","settled","open"}, ["halted": {...}]}`. Files: `<root>/{.lock,
  events.jsonl, state.json}`; event kinds declare/raise/reserve/settle/orphan/halt(+close[])/resume/refuse.

### 3.4 cells.py  (P: MAX_EPISODE_RESTARTS, MAX_REEXECUTIONS, MAX_RESCORES, VERSION)
- `Pause(kind, reason, cell)` (attrs kind/reason/cell); `exclusive(path, *, wait=False)`;
  `Context(*, store, endpoint, runtime, native, episodes)`; `cell_id(unit, arm, task_id, run) -> 32 hex`;
  `run_cell(context, cell, task, skill) -> record` with `cell = {"id","unit","arm","benchmark","task_id","run"}`, `task =
  {"public","private"}`, `skill` = the text passed to `backends.solve`; writes `<store>/cells/<id>.{claim,json}`,
  `<store>/artifacts/<sha>.json`, SpreadsheetBench `<store>/host_only/scorer_artifacts/<pos>/`; raises `Pause` after
  writing on rows 1-3 / assumption / ledger / unexpected exception.
- `run_parallel(function, jobs, *, workers) -> results in job order`; `run_cells(context, jobs, *, workers)` with jobs
  `(cell, task, skill)`.

### 3.5 units.py  (P: READ_TIMEOUT_SECONDS, RESEND_COOLDOWN_SECONDS, ROLE_MAX_TOKENS, ROLE_MODEL,
ROLE_READ_TIMEOUT_SECONDS, SOLVER_MAX_TOKENS, VERSION)
- `CHAINS` (dict, units.py:37-46); `Setting` dataclass: `run: str, root: Path, shared: Path, pools: dict, regression:
  dict, tolerance: dict, cards: dict, rubrics: dict, instructions: dict, runtime: dict, clients: object (callable
  (model, max_tokens, read_timeout) -> client), budget: object, slots: dict, sources: object, workers: int = 16, seed: int
  = 20261017, cooldown: int = RESEND_COOLDOWN_SECONDS, extra: dict` (units.py:49-75). v3-specific fields: regression,
  tolerance, rubrics, instructions, sources.
- `scopes(chain, stage, kind)`, `endpoints(setting, chain, stage, kind="learning") -> (solver_endpoint, role_endpoint)`
  (role = ROLE_MODEL glm-5.3 on `setting.slots["glm-5.3"]`), `solver_endpoint(setting, solver, charged)` (charged None ->
  uncharged), `cell_context(setting, attempt, endpoint)` (uses slots "spreadsheet-native", "alfworld-episode"),
  `unit_path(chain_root, stage, name) -> <chain_root>/s<stage>/<name>`, `complete(unit_root, *, run, identity)`,
  `run_unit(unit_root, *, run, identity, work) -> unit record` (`identity["unit"]` required; `work(attempt_dir) ->
  JSON-safe dict`).

### 3.6 evaluation.py  (P: MAX_UNKNOWN_SHARE, SHARED_STAGE0, VERSION)
- `contained(shared)` ctx -> sealed diagnostics path; `ContainmentFailure`; `consent(shared) -> dict`; `attempts(root)`,
  `recovered(attempt)`, `_next_attempt(root)` (private; used by units.py:26, chain.py:40, run_coevo5.py:92).
- `test_tasks(shared, pinned, benchmark, unit, *, run, runtime, native, workers) -> [task]` (consent, TestAccess,
  registry, sheet qualification). `configuration(context, benchmark)`.
- `evaluate(unit_root, *, run, shared, pinned, chain, stage, benchmark, skill, context, workers, previous=None) ->
  record` (context.store must be `_next_attempt(unit_root)`, not yet created). Raises Pause / sanitized ValueError /
  KeyboardInterrupt-like unchanged.
- `monitor(unit_roots) -> rows`; `unseal(chain_root, chain, unit_roots, *, run, detail=False)`.

### 3.7 data.py  (P: see F27)
- `sha(path)`, `pin(config) -> {"paths","sha256"}`, `test_ids(pinned, b)`, `pool(pinned, b) -> [item]`,
  `item_hash(item)`, `ranked(items, seed, tag)`, `qualified(items, qualification)`, `training_items(items, b, seed,
  size=None)`, `regression_items(items, b, seed)`, `sheet_tolerances(qualified_count)`, `TestAccess(unit)`,
  `test_panel(pinned, b, *, access) -> (tasks, report{benchmark, tasks, excluded_without_pages,
  training_items_identical, panel_hash, unit, source_files})`. Constants `DEV_MACHINE`, `TEST_PARTITION = "final"`.

### 3.8 outcomes.py, qualify.py, stats.py, checks.py, leakage.py
- outcomes (P: MAX_WORKBOOK_BYTES, MAX_WORKBOOK_EXPANDED_BYTES): `Verdict(outcome, kind, reason, row, remedy=None,
  exhausted=None)` + `.token`; `classify(benchmark, prediction, score=None, receipts=(), *, refused=False,
  spent=frozenset())`; `preflight(benchmark, prediction, receipts=(), *, refused=False, spent=frozenset())`;
  `undelivered(receipt)`, `public(final) -> "row:kind:detail"`, `public_error(error)`, `finalize(verdict)`; exceptions
  `ConfigurationError, BudgetStop, CleanupUnconfirmed, AssumptionBroken, LedgerFailure(reason, events=(), *,
  quarantined=False)`.
- qualify (P: VERSION): `qualify(tasks, root, runtime, *, side, native, workers) -> sealed record {version, side, tasks,
  qualified, excluded, counts, scorings_per_item, model_calls: 0, scorer, recalculation, task_hashes}`, `load(path)`,
  `summary(record)`, `reference_prediction(task)`, `category(reason)`.
- stats (P: none): `bounds(cells{(arm,item): [token]}) -> {(arm,item): (L, H, unknown, runs, infra)}`, `total(table, arm,
  items, side)`, `unknown_share(table, arm, items, infrastructure_only=False)`, `sign_test(wins, losses)`,
  `bootstrap(strata, statistic, *, resamples=10000, seed=20261017, level=0.95) -> (lo, hi)`.
- checks (P: none): `CHECKS` {answer_tag_present, answer_single_letter, answer_pure_number(allow_percent),
  answer_no_percent, answer_no_letters, answer_max_words(n 1..50), code_present}; `validate(spec)`, `run(spec, output)
  -> True/False/None`, `last_answer(output)`.
- leakage (P: DATA_SEED, LEAK_*, ORDER): `normalize(text)`, `surface(benchmark, item, *, task_text=None)`,
  `Corpus(benchmark, items, *, alfworld_texts=None)` (`.evidence(words)`), `findings(text, corpus)`, `mechanical(text,
  corpus)`, `answer_values(answers, limit=60)`, `adjudicate(roles, text, *, label, colliding=None, values=None)` (GLM
  call via `roles.ask`).

### 3.9 Generic round primitives that live in step.py (importing step pulls in the whole v3 method stack)
- `key(bench, task_id) -> "<bench>/<task_id>"`, `bench_of(item)`, `pool_tasks(setting, benches)`,
  `run_round(setting, attempt, endpoint, unit, arms{arm: skill text}, schedule{arm: [(item, runs)]}, tasks, *, tag) ->
  {(arm, item): [record per run]}` -- all arms' cells in ONE seeded shuffled job list (step.py:105-121): this is the
  existing "same time window, item-interleaved" mechanism; `table_of(cells)`, `answered(record)`,
  `shared_unanswered(cells, items)`, `guard(cells, arms, unit)` (>1/10 infrastructure unknown of a parent/control arm ->
  Pause), `violations(store, cells, arm, items, bench, *, unknown_counts)` (step.py:124-181).

### 3.10 Run directory layout (verified on dl /data/coevo5-20261019-v3-run and code)
```
<root>/                               manifest["root"] (must not exist at make-manifest, prelaunch.py:482)
  shared/
    consent.json                      record_consent (prelaunch.py:532-538)
    baselines-checked.json            baseline.check (required by `run`)
    ledger/{.lock,events.jsonl,state.json}
    slots/<pool>.<i>.lock, <pool>.gather.lock[, <pool>.many.lock]   pools = SLOTS keys
    test/<bench>.json + <bench>.lock  write-once panel registry (evaluation.py:190-199)
    test/spreadsheetbench-qualification.json (+ .lock, + dir/attempt-N/{qualification.json,scores/,host_only/})
    host_only/diagnostics/<host>-<pid>.log, child-<sha16>-<ns>.log   sealed process output
    host_only/specs/<sha16>.json      evaluation-unit child specs (chain.py:169-177)
  <chain>/  chain.json, .runner.lock, chain-complete.json | chain-terminated.json
    s0/evaluation/<bench>/            evaluation unit
    s<k>/{train,prepare,selftest,screen,confirm,composite,merge}/   learning units (v3 names, step.py)
    s<k>/evaluation/<bench>/
  every unit dir: unit.json (sealed, once), .lock, attempt-<n>/ {cells/<id>.claim, cells/<id>.json, artifacts/<sha>.json,
    host_only/scorer_artifacts/<pos>/, status.json (paused), recovery.json (owner), and for learning units
    started.json, diagnostics.log, roles.json, research.json, ...}
```
Evaluation attempts have no started.json (evaluation.py:364). Unit name strings: `"<chain>/s<k>/<name>"`
(step.py:100), evaluation `"<chain>/s<k>/evaluation/<bench>"` (evaluation.py:328, 353).

### 3.11 Launch end to end (verified from dl ops scripts; all commands `PYTHONPATH=$S $PY scripts/run_coevo5.py ...`
run from the frozen snapshot S, PY = /root/continual-alf-prep-20260928/env/bin/python)
0. Snapshot S (copy of repo; sha256 list e.g. /data/coevo5-20261019-v3-ops/f/source-v3f.sha256); pytest of
   tests/test_coevo5_*.py + tests/test_weak_solver_probe.py must exit 0 (prep-v3.sh:7-10).
1. Engine qualification (zero calls): `python -m scripts.replay_sheet_v6 qualify --output Q --image sha256:f7f6...
   --legacy-qualification ... --comparison-fixture-qualification ... --native-lock ... --engine-version v7`, then
   `qualify-train-sheet --engine-qualification Q/qualification.json --out T` (prep-v3.sh:12-18).
2. `proxy_on`; `build-archive --out A --previous <v2 archive>` (prep-v3.sh:19-21).
3. `import-texts --out P/texts --source <v1 texts.json>` (v1: `prepare-texts --out P/NEWDIR --repo R --existing B=DIR`)
   (prep-v3.sh:22-23).
4. Ops first-response probe (probe-v3.py, not in repo) (prep-v3.sh:24-25).
5. `smoke-make --out P/smoke --texts P/texts/texts.json --archive A --repo R --deepseek-env ENVF --engine-qualification
   Q/qualification.json --sheet-qualification T/sheet/qualification.json --chain I-ds`; `smoke --spec P/smoke/smoke.json`
   (exit 3 when paused) (prep-v3.sh:30-35).
6. `smoke-summary --spec ...`; `make-manifest --out M --root RUN --sheet-qualification ... --engine-qualification ...
   --texts ... --smoke P/smoke-3 --archive A --baseline-protocol /root/continual-fivebench-20261003-f-study/protocol.json
   --repo R --deepseek-env ENVF --gepa-source G`; `check-baselines --manifest M`; `consent --manifest M --date D --note
   "$(cat consent-note.txt)"` (f/prep-launch-v3.sh:5-15).
7. One tmux session per chain: `bash -i run-chain-v3.sh C` -> `proxy_on; run --manifest M --chain C`
   (f/launch-v3.sh, f/run-chain-v3.sh).
8. Operations: `monitor --manifest M`, `recover --unit-root U --decision TEXT`, `terminate --manifest M --chain C
   --decision TEXT`, `resume-ledger --manifest M --decision TEXT`, `report --manifest M --out NEWDIR`
   (run_coevo5.py:3-15). Children: `evaluate-unit --manifest M --spec S`, `qualify-test-sheet --manifest M`.

### 3.12 How the smoke is specified (smoke.py)
`make(out, *, texts_record, archive, repo, proxy, research_proxy, workers, deepseek_env, router_env=None, draw=None,
data_config=None, chain_name=CHAIN, engine_qualification=None, sheet_qualification=None)` writes the sealed spec
`<P>/<name>/smoke.json` = {version VERSION-smoke, root, chain, draw, data (pinned), runtime, sheet_qualification, texts,
research, clients, workers, code (pin_code), environment} (smoke.py:86-122); its record_hash is the smoke's run id.
`setting(path)` rebuilds a `Setting` with the pre-launch ledger `<P>/ledger` and slots `<P>/slots`, `extra={"draw":
...}` (125-162). `run(path)`: declares `chain.caps(name, PRELAUNCH_CAP)`, runs `format_check` (zero GLM calls: 3 Skills
x first 20 items of the registered draw of 4 benches, `REQUIRED_FORMAT` shares, floor 9/10, margin 1/20), then stage 1
SearchQA (60 items) via `step.learn`, `paths` (forces research/forward/revision paths once if unreached), stage 2 OfficeQA
(50 items), writes `summary.json` (status complete | paused | format_check_failed) (275-337, 404-435). `prelaunch._smoke`
requires summary status "complete" and the same pre-launch ledger and records code `changed_since` (463-474).

## 4. Reusable unchanged for route B vs must be generalized

Key mechanism (verified): every module does `from .protocol import ...` at import time, so importing a coevo5 module
from a new package always yields coevo5's constants and stamps `fivebench-coevolution-v3-*` (F2). Nothing can be
re-parameterized without editing or copying (monkeypatching module globals would silently change a frozen protocol's
semantics -- not recommended).

ORDER sensitivity (verified): order-insensitive -- calls, ledger, budget, cells, units.run_unit, evaluation.evaluate,
outcomes, qualify, stats, checks, data.pool/pin/ranked/test_panel (only `set(ORDER)` checks, data.py:79-81;
`regression_items` uses `ORDER[-1]`, which is ALFWorld in both v3 and route-B orders), leakage (membership only),
manifest.load (iterates ORDER for pools). Order-sensitive (stage k = ORDER[k-1]): chain.py:282-285, step.py:100, 198,
smoke.py:64 (`ORDER[:2]`), protocol `similar_targets` (protocol.py:23-28), report/readout.

| Module | Verdict for route B | What it bakes in |
|---|---|---|
| budget.py | import unchanged | nothing protocol-specific. Per-role or per-activity ceilings = extra declared scope strings (allowed by `reserve`, budget.py:288-300); but `step_scope`/`deepseek_scope` accept only kind "learning"/"evaluation" (budget.py:55, 70) -> write a new scope helper, keep `rooted` rule. |
| ledger.py | import unchanged IF the new solver client keeps <= 4 attempts per call and the receipt shape (attempts[], usage{prompt,completion,total}) | CLIENT_ATTEMPTS=4, RESERVATION_OVERHEAD=512 (protocol.py:278-279) |
| stats.py | import unchanged | bootstrap seed default 20261017 (stats.py:56; overridable) |
| checks.py | import unchanged (verifies the fixed format guards) | per-bench `REQUIRED_FORMAT` lives in protocol.py:127-128 -> own mapping |
| outcomes.py | import unchanged for solver cells | per-bench rows 7-9; NO row for shell/procedure/router failures; row 11 turns any unknown reason into an infrastructure unknown |
| calls.py | import unchanged | MAX_RESENDS=2 inside `Recorder.__call__` (calls.py:270); cooldown injectable (Endpoint arg) |
| cells.py | import (stamps v3-cell) or copy with new VERSION | `backends.solve(benchmark, public, skill_text, call)` is the only solver interface (cells.py:134); remedies LIMITS; record shape F18 |
| units.py | `run_unit`, `complete`, `unit_path`, `cell_context` reusable (stamps v3-unit); `CHAINS`, `endpoints`, `solver_endpoint`, `Setting` must be generalized | CHAINS (units.py:37-46), ROLE_MODEL glm-5.3, SOLVER_MAX_TOKENS/SLOTS keyed by model id "deepseek-v4-flash" (protocol.py:327, 331), `Setting` v3 fields (regression, tolerance, rubrics, instructions, sources) |
| evaluation.py | reusable: `contained`, `consent`, `attempts`, `recovered`, `_next_attempt`, `test_tasks`, `_registry`, `_sheet_qualification`, `monitor`. Must generalize: `evaluate`, `unseal`, `_predecessor`, `configuration`, `_own` | one arm per unit, cells keyed (chain, task_id, run 0) (evaluation.py:376-378); unseal keyed by task_id only (451-454); reuse by Skill-text digest only (366); config = model+max_tokens+runtime (308-311); SHARED_STAGE0; `_own` = coevo5 package dir (267) |
| qualify.py | reusable logic; VERSION-bound load | a copy with a new VERSION cannot load the v3 records (/data/coevo5-20261019-v3-sheet-train-f/sheet/qualification.json etc.) unless it accepts an explicit importable-version list (like prelaunch IMPORTABLE, prelaunch.py:135) |
| data.py | reusable: `pin`, `pool`, `ranked`, `qualified`, `test_ids`, `TestAccess`, `test_panel`, `item_hash`. Must add: disjoint one-time batches + consumption registry; generated-item schema | POOLS sizes asserted (data.py:163-164); TRAIN_ROLLOUT draw = gate panel (protocol.py:58-61); `DEV_MACHINE` /root paths (45-64); `sheet_tolerances` runs a v3 power rule file (208-228) |
| leakage.py | `normalize`, `Corpus`, `findings`, `mechanical` reusable as a screen of procedure source/literals and descriptions; adjudicator prompt is rule-text specific (leakage.py:73-90) | ORDER membership, per-bench answer schemas (searchqa answers list, officeqa answer, livemath letter) |
| manifest.py | copy + rewrite | FIELDS (34-35), VERSION check (119), `loaded_code` hardcodes `skillopt/coevo5/*.py` + `scripts/run_coevo5.py` (37, 54), `_clients` hardcodes model "deepseek-v4-flash" (108), `load` builds the v3 Setting (rubrics via examiner, research archive, baseline block, prior tokens) |
| prelaunch.py | reuse `engine_runtime`, `qualify_training_sheet`, `ledger_of`, `prelaunch_budget`, `prior_usage`, `record_consent`, `role_client`, `fetcher`/`build_archive`/`check_archive` (only if an archive is used); replace texts, tolerances, baselines, `_smoke`, `generate` | PRELAUNCH_CAP 30M, v3 texts versions, baseline protocol hash, archive roster |
| smoke.py | replace; keep the pattern (sealed spec = smoke run id, pre-launch ledger, unit-by-unit summary, `changed_since`) and the zero-GLM `format_check` idea | CHAIN I-ds, BENCHES ORDER[:2], DRAW 60/50, step.learn |
| chain.py | replace; keep patterns: evaluation in child processes with sealed stdout (`_child`, `launch_child`, `_failed_start`, `_status`), terminal markers, idle-only `terminate`, `_verified` code check before every stage | CHAINS/caps/ORDER/learn loop, SHARED stage 0, `scripts/run_coevo5.py evaluate-unit` path (chain.py:159) |
| run_coevo5.py | replace with an own CLI (same subcommand pattern) | `run` requires baselines-checked (run_coevo5.py:80); `consent` goes through report.of_manifest (216-218) |
| step.py primitives | copy `run_round`, `guard`, `table_of`, `shared_unanswered`, `answered`, `violations`, `key`, `bench_of`, `pool_tasks` (~100 lines) rather than import step (which imports analyst, examiner, forward, gate, research, roles, skill) | DATA_SEED-seeded job order (step.py:79-80, 115) |

Identity options for the new package (designer's choice; facts only):
- (a) cal-1 style (F43): import the unchanged v3 modules, own root/ledger/slots and own `run`/identity strings. Zero
  porting cost, but every cell/unit/evaluation/qualification record is stamped `fivebench-coevolution-v3-*` and
  `manifest.load` only accepts a `fivebench-coevolution-v3-manifest` -> route B would have to bypass `manifest.load` or
  reuse the v3 manifest (as cal-1 did) -- AGENTS.md requires a new version for new behaviour.
- (b) Copy the infrastructure as a CLOSED set into the new package with its own protocol.py VERSION, port the matching
  tests (tests/test_coevo5_{calls,ledger,cells,units,evaluation,outcomes,data,...}.py, fakes tests/coevo5_fakes.py).
- (c) Parameterize coevo5 in place: changes files of a frozen protocol (the v3 snapshot on dl keeps its own copy, F3).
- Pitfall for any mix of (a) and (b) (verified mechanism, inferred consequence): `cells.STOP_KINDS` and
  `units.run_unit` map exception CLASSES (cells.py:45-46, units.py:149); `budget.py` raises
  `coevo5.outcomes.BudgetStop/AssumptionBroken/LedgerFailure` (budget.py:36). A copied cells/units paired with the
  imported coevo5 budget would classify a budget stop as "exception". Import or copy calls+ledger+budget+outcomes+cells+
  units+evaluation+qualify together.

## 5. Gaps and risks for route B in this area

- G1 No sandbox for model-written code. coevo5 never executes model-written code outside the SpreadsheetBench solver
  program in the frozen Docker backend (checks.py:3; F46). Route B executes engineer-written procedures + applicability
  conditions on every solver request (ALFWorld: every step) and examiner-written detectors/generators. Needs: process
  isolation, CPU/memory/time limits, determinism (re-execution must reproduce identical requests: cells.py:144),
  no access to `task["private"]` (the shell must hand procedures only `public`), native slot accounting (dl has 7 CPUs,
  15 GB; SLOTS spreadsheet-native=3, alfworld-episode=6).
- G2 Decision table has no rows for shell/procedure/router failures. A procedure exception, timeout or veto loop would
  surface as an unknown reason -> row 11 "unclassified" -> counted as infrastructure (outcomes.py:304) -> >1/10 pauses the
  unit (evaluation.py:392; step.guard). Registration must decide: procedure failure = fail of the candidate arm (Skill
  defect) vs infrastructure, and add rows.
- G3 No activation log in cell records. Transfer reading needs per-(cell, procedure) "applicable / fired / changed
  context / vetoed" records. The full prediction is stored by hash (cells.py:187) so a shell could add a field to the
  prediction dict; nothing reads it today (`_prediction_summary` keeps status/reason/cases only, cells.py:108-112).
- G4 Multi-call QA cells. Exact-computation tags need a second model call inside one QA cell; `backends.solve` receives
  one `call` and the Recorder records every send, but `outcomes._delivery` judges the LAST receipt the solver received
  (outcomes.py:256-263). A shell that calls the Recorder several times and returns one receipt must return the last
  real one (or the table must change). Every extra call is reserved/charged normally (the reservation is computed on
  the bytes actually sent, calls.py:152-161) -- shell-injected context must be added BEFORE the Recorder.
- G5 Evaluation cannot interleave arms. `evaluate()` runs one arm per unit and `unseal()` keys by task_id (F24, F26); the
  design's "five test sets read once, interleaved with task-card-only and placebo arms" needs a multi-arm evaluation
  unit (cells already key by arm: `cell_id(unit, arm, task_id, run)`). Reuse-by-digest (evaluation.py:366) and
  `configuration()` must include the procedure library + shell/router/guard code hashes, else a changed package with
  identical text could be wrongly reused.
- G6 No fresh-batch reader or consumption ledger (F30). Route B's "every batch used once" (execution batch, acceptance
  batch, detector hold-out) needs disjoint `ranked` slices per (bench, step, purpose) plus a write-once registry of
  consumed ids; with POOLS 74 OfficeQA / 57 ALFWorld / 91 qualified SpreadsheetBench (F29, F33) a two-batch split leaves
  ~25-45 items per batch.
- G7 Generated tasks have no data path. Scoring goes through `backends.score(benchmark, public, private, prediction)`;
  generated items must reproduce each benchmark's frozen item schema (validated by `datasets.validate_panel`,
  data.py:145) to be scored by the frozen scorers. ALFWorld environment generation is outside `data.py` (episodes come
  from `alfworld_data` game files, protocol.py:355). `leakage.Corpus` and `_refuse_tests` assume pool items.
- G8 New solver model id. design-v0.md:55 names deepseek-v4.1-flash-1017; it is absent from `MODELS`/`ROUTES`
  (weak_solver_probe.py:76-88; Client refuses unknown models, 232-233), from `SOLVER_MAX_TOKENS`, `SLOTS`
  (protocol.py:327-331) and from `manifest._clients` (manifest.py:108). The probe module is imported read-only by sealed
  runs (coevo5/__init__.py docstring l.3-4) -> a new route needs either a versioned probe change or a new client, and the
  ledger requires the client's attempts to stay within CLIENT_ATTEMPTS=4.
- G9 Slots are per root (F6). A route-B run with its own `shared/slots` does not share the provider concurrency limit
  with any other run on dl (e.g. a cal-1-like job) -> rate-limit (HTTP 429) risk; decide a machine-wide slot root or
  exclusive scheduling.
- G10 Per-role ceilings. Today only overall / chain / step x kind scopes exist; engineer vs examiner (both GLM) share
  one role endpoint (units.py:91-93). Separate caps need separate endpoints with separate scopes.
- G11 Budget constants are v3's. OVERALL_CEILING 1,170M (protocol.py:322), DEEPSEEK_CEILING 430M, DEEPSEEK_CHAIN_CAP
  200M (317-318), PRELAUNCH_CAP 30M (prelaunch.py:131). Route B's estimate (design-v0.md:46: pilot 60-100M, full 400-600M,
  test reading ~52-57M per step) needs new registered caps; v3 actually spent 139.0M deepseek + 7.8M GLM (F13).
- G12 Qualification and test registry are run-local. A new run root starts with an empty `shared/test/` -> the
  SpreadsheetBench test-side qualification reruns (zero calls, Docker time) and needs consent; reusing v3's records hits
  the VERSION-bound `qualify.load` (F38).
- G13 Error-message containment keys on the package directory (`_own`, evaluation.py:267): a new package's own
  messages would be dropped (only type + code locations) unless the check is updated in the copy.
- G14 Smoke/pre-launch chain is coupled to v3 texts, rubrics, research archive and baselines (`manifest.load`
  requires all FIELDS, manifest.py:119-140; `run` requires baselines-checked). Route B needs its own pre-launch list.
- G15 ALFWorld cost: the Skill is resent on every action (protocol.py:48 comment); shell-injected state blocks grow every
  step's prompt and reservation (4 x bound per call) -> per-step reservations could hit caps early; size bounds needed.
- G16 Determinism of the job order and of procedures: `run_round` shuffles all arms' cells by DATA_SEED (step.py:115);
  procedures with nondeterminism would break the re-execution identity check (cells.py:144) and paired comparisons.

## 6. Open questions for the designer (not verifiable by reading)

- Q1 Identity strategy: (a) import unchanged as cal-1 did (records stamped v3), (b) closed-set copy with a new VERSION,
  or (c) parameterize coevo5? AGENTS.md asks for a new version and output directory for new behaviour.
- Q2 Does the PJLAB token route serve "deepseek-v4.1-flash-1017", with which response model id(s), thinking mode,
  max_tokens, retry count? (Needed for MODELS/ROUTES, SOLVER_MAX_TOKENS, SLOTS, CLIENT_ATTEMPTS.)
- Q3 New token ceilings (deepseek and GLM, overall/pilot/per role) and whether the owner's old coevo5 envelope (1.44B,
  protocol.py:319-322) still applies.
- Q4 Reuse the v3 engine/training-side SpreadsheetBench qualifications (qualified 91/120) and the v3 research archive,
  or re-derive them under the new version?
- Q5 Which sandbox runs procedures/detectors/generators (the SpreadsheetBench native Docker image, a new image, or a
  subprocess jail), and how many native slots on the 7-CPU dl machine?
- Q6 How are procedure failures classified in the decision table (candidate fail vs infrastructure unknown), and does
  the conservative L/H rule (unknown = fail for the candidate, pass for parent/controls; stats.py:3-6) carry over to
  acceptance?
- Q7 Batch registry scope: per chain or shared by all arms/chains; may a pilot's consumed items be reused by the full run?
- Q8 Test reading per step vs once at the end (design-v0.md:46): with per-step reading, how is evaluation reuse defined
  for packages that differ only in procedure code?
- Q9 Should the placebo procedure and task-card-only arms of acceptance also appear in test reading (design step 8),
  i.e. a multi-arm evaluation unit with its own consent wording?
- Q10 Slot root: share a machine-wide `slots/` directory across concurrent experiments, or schedule exclusively?
